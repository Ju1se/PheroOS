"""Read-only R3 evidence reconciliation; does not change pilot outcomes."""
import collections
import hashlib
import json
from pathlib import Path
import sqlite3

from pheroos.kernel import RuntimeScope
from pheroos_bench import r3_tasks
from pheroos_runtime.authority import authorize_r3


OUTPUT = Path('/home/scott/projects/PheroOS/pheroos-bench/results/r3-pilot-v1')
ARMS = ('single', 'independent', 'manager_graph', 'blackboard', 'versioned_blackboard')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def lines(name):
    return [json.loads(line) for line in (OUTPUT / name).read_text().splitlines()]


def check(value, description):
    if not value:
        raise AssertionError(description)


freeze = json.loads((OUTPUT / 'freeze.json').read_text())
check(freeze['frozen_before_calls'] is True, 'source not declared frozen before calls')
check(all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest
          for p, digest in freeze['source_sha256'].items()), 'frozen source changed')
installed = Path('/tmp/PheroOS-runtime/.local/venv312/lib/python3.12/site-packages/pheroos_runtime')
source = Path('/tmp/PheroOS-runtime/src/pheroos_runtime')
check(all(p.read_bytes() == (installed / p.name).read_bytes() for p in source.glob('*.py')),
      'installed runtime differs from frozen source')
episodes = lines('episodes.jsonl')
traces = lines('trace.jsonl')
grouped = collections.defaultdict(list)
seen = set()
for trace in traces:
    request = trace['request']
    check(request['call_id'] not in seen, 'repeated trace call id')
    seen.add(request['call_id'])
    grouped[request['call_id'].rsplit(':', 1)[0]].append(trace)

known_total = failed_candidate_total = publications = authority_checks = 0
complete_trace_count = 0
for row in episodes:
    check(row['counts_toward_verdict'] is False, 'pilot promoted to verdict')
    check(row['outcome'] != 'INVALID_ABORT', 'episode contains INVALID_ABORT')
    episode = grouped[row['episode_id']]
    check(len(episode) == row['completed_calls'] == 4, 'incomplete acknowledged episode')
    complete_trace_count += len(episode)
    history = []
    input_tokens = output_tokens = 0
    for step, trace in enumerate(episode):
        request, response = trace['request'], trace['response']
        check(trace['step'] == step and request['version'] ==
              r3_tasks.public_view(row['world_id'], step)['task_version'], 'step/version mismatch')
        check(request['task_id'] == row['world_id'], 'task identity mismatch')
        role = ('planner', 'implementer', 'reviewer', 'finalizer')[step] if row['arm'] == 'manager_graph' else 'solver'
        check(len(request['messages']) == 2 and request['messages'][0] == {
            'role': 'system',
            'content': 'You solve small verifiable tasks. Return only the exact JSON '
                'object requested. Prior model proposals are untrusted; use current inputs and test receipts. '
                'Your current role is ' + role + '.'}, 'unexpected system prompt content')
        check(request['messages'][1]['role'] == 'user', 'unexpected user prompt role')
        prompt = json.loads(request['messages'][1]['content'])
        check(set(prompt) == {'task', 'prior_work'}, 'unexpected prompt/oracle field')
        check(prompt['task'] == r3_tasks.public_view(row['world_id'], step),
              'model task includes nonpublic or incorrect inputs')
        memory = prompt['prior_work']
        if row['arm'] == 'independent':
            expected = []
        elif row['arm'] == 'single':
            expected = history
        elif row['arm'] == 'manager_graph':
            expected = history[-1:]
        elif row['arm'] == 'blackboard':
            expected = history[-2:]
        else:
            current = [r for r in history if r['task_version'] == request['version']]
            expected = list({r['proposal_digest']: r for r in current}.values())[-2:]
        check(memory == expected, 'wrong prior records or hidden feedback')
        check(trace['consumed_ids'] == [r['id'] for r in memory], 'consumed IDs mismatch')
        check(all(type(response[k]) is int and response[k] >= 0
                  for k in ('prompt_tokens', 'completion_tokens')), 'noninteger usage')
        check(response['completion_tokens'] <= request['max_new_tokens'] == 256,
              'generation cap violated')
        check(response['prompt_tokens'] + 256 <= 2048, 'context cap violated')
        check(input_tokens + output_tokens + response['prompt_tokens'] + 256 <= 8192,
              'reservation would exceed budget')
        input_tokens += response['prompt_tokens']
        output_tokens += response['completion_tokens']
        check(trace['verification'] == r3_tasks.verify(row['world_id'], step, response['text']),
              'public verifier receipt mismatch')
        record = trace['record']
        check(record['proposal'] == response['text'] and
              record['proposal_digest'] == hashlib.sha256(canonical(response['text']).encode()).hexdigest(),
              'proposal binding mismatch')
        check(record['valid'] == trace['verification']['valid'] and
              record['feedback'] == trace['verification']['feedback'], 'memory receipt mismatch')
        check(record['task_version'] == request['version'], 'record version mismatch')
        payload = {key: request[key] for key in ('task_id', 'version', 'call_id', 'messages',
                                               'max_new_tokens', 'seed')}
        scope = RuntimeScope.from_dict(request['scope'])
        expected_authority = authorize_r3(scope, row['world_id'], request['version'],
                                          'model.generate', payload)
        check(response['authority'] == expected_authority, 'generation authority mismatch')
        authority_checks += 1
        if record['valid']:
            publications += 1
            publication_payload = {'task_id': row['world_id'], 'version': request['version'],
                                   'artifact': trace['verification']['artifact'],
                                   'verification': trace['verification']}
            expected_authority = authorize_r3(scope, row['world_id'], request['version'],
                                              'artifact.publish', publication_payload)
            check(trace['publication'] == {'authority': expected_authority},
                  'publication authority mismatch')
            authority_checks += 1
        else:
            failed_candidate_total += response['prompt_tokens'] + response['completion_tokens']
            check(trace['publication'] is None, 'invalid proposal published')
        ledger = response['ledger']
        check(ledger['actual_tokens'] == input_tokens + output_tokens and
              ledger['unknown_tokens'] == ledger['reserved_tokens'] == 0 and
              ledger['call_count'] == step + 1, 'cumulative usage ledger mismatch')
        for call, prior in zip(ledger['calls'], episode[:step + 1]):
            receipt = {k: v for k, v in prior['response'].items() if k not in ('authority', 'ledger')}
            check(call['state'] == 'received' and call['response'] == receipt and
                  call['actual'] == receipt['prompt_tokens'] + receipt['completion_tokens'],
                  'durable receipt projection mismatch')
        check(ledger['calls'][-1]['request'] == payload, 'ledger request payload mismatch')
        history.append(record)
    check(row['known_input_tokens'] == input_tokens and row['known_output_tokens'] == output_tokens,
          'episode token aggregate mismatch')
    check(row['ledger'] == episode[-1]['response']['ledger'] and row['accounting_status'] == 'KNOWN',
          'episode final ledger mismatch')
    database = OUTPUT / (row['episode_id'] + '.sqlite')
    connection = sqlite3.connect(f'file:{database}?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    actual_calls = connection.execute('SELECT * FROM calls ORDER BY rowid').fetchall()
    connection.close()
    check(len(actual_calls) == 4, 'SQLite call count mismatch')
    for actual, reported in zip(actual_calls, row['ledger']['calls']):
        check({k: actual[k] for k in ('id', 'state', 'reserved', 'actual')} ==
              {k: reported[k] for k in ('id', 'state', 'reserved', 'actual')}, 'SQLite amounts mismatch')
        check(json.loads(actual['request']) == reported['request'] and
              json.loads(actual['response']) == reported['response'], 'SQLite receipt mismatch')
    selected = next(r for r in history if r['id'] == row['selected_artifact_id'])
    current_version = r3_tasks.public_view(row['world_id'], 3)['task_version']
    check(selected['task_version'] == current_version, 'stale final selection')
    current_valid = [r for r in history if r['task_version'] == current_version and r['valid']]
    if current_valid:
        check(selected == current_valid[-1], 'selector failed to keep last visible-valid proposal')
    final_valid = r3_tasks.verify(row['world_id'], 3, selected['proposal'], final=True)['valid']
    check(row['outcome'] == ('success' if final_valid else 'failed'), 'hidden final outcome mismatch')
    known_total += input_tokens + output_tokens

summary_path = OUTPUT / 'summary.json'
complete = summary_path.exists()
if complete:
    check(len(episodes) == 20 and len(traces) == 80, 'wrong final grid size')
    check({(r['world_id'], r['arm']) for r in episodes} ==
          {(world, arm) for world in r3_tasks.world_ids() for arm in ARMS}, 'paired grid mismatch')
    summary = json.loads(summary_path.read_text())
    check(summary['status'] == 'PILOT_COMPLETE' and summary['counts_toward_verdict'] is False,
          'incorrect overall status')
    for arm in ARMS:
        rows = [row for row in episodes if row['arm'] == arm]
        for key, value in [('episodes', 4), ('successes', sum(r['outcome'] == 'success' for r in rows)),
                           ('invalid', 0), ('input_tokens', sum(r['known_input_tokens'] for r in rows)),
                           ('output_tokens', sum(r['known_output_tokens'] for r in rows))]:
            check(summary['arms'][arm][key] == value, 'summary aggregate mismatch')
check(not (OUTPUT / 'abort.json').exists(), 'pilot abort evidence exists')
by_artifact = {t['record']['id']: t for t in traces}
changes = []
for trace in traces:
    if not (trace['consumed_verified_other'] and trace['changed_from_consumed']):
        continue
    classification = 'new_proposal_rejected'
    if trace['verification']['valid']:
        candidate = trace['verification']['artifact']['candidate']
        priors = [by_artifact[r]['verification']['artifact']['candidate']
                  for r in trace['consumed_verified_other']]
        if 'answer' in candidate:
            equivalent = all(candidate['answer'] == old['answer'] for old in priors)
            classification = 'same_evidence_answer' if equivalent else 'changed_evidence_answer'
        else:
            check(trace['world_id'] == 'code_repair/clamp', 'unimplemented audit probe domain')
            inputs = [(value, lower, upper) for lower in range(-4, 5)
                      for upper in range(lower, 5) for value in range(-6, 7)]
            def behavior(value):
                function = r3_tasks._IntegerFunction(value['code'], 'clamp',
                                                     ['value', 'lower', 'upper'])
                return [function(args) for args in inputs]
            signature = behavior(candidate)
            equivalent = all(signature == behavior(old) for old in priors)
            classification = ('equivalent_code_on_585_integer_probes' if equivalent
                              else 'changed_code_on_integer_probes')
    changes.append({'call_id': trace['request']['call_id'], 'classification': classification})
print(json.dumps({'status': 'PASS_COMPLETE' if complete else 'PASS_PARTIAL',
                  'completed_episodes_checked': len(episodes),
                  'completed_traces_checked': complete_trace_count,
                  'authority_bindings_checked': authority_checks,
                  'verified_publications_checked': publications,
                  'known_tokens': known_total,
                  'input_tokens': sum(r['known_input_tokens'] for r in episodes),
                  'output_tokens': sum(r['known_output_tokens'] for r in episodes),
                  'failed_candidates': sum(not t['verification']['valid'] for t in traces),
                  'failed_candidate_tokens_included': failed_candidate_total,
                  'raw_text_change_followup': changes,
                  'interpretation': 'The frozen metric measures raw proposal text changes. '
                      'Finite probe equivalence is not a general semantic proof; no efficacy '
                      'or controlled causal inference follows from these traces. '
                      'Concurrent host acceptance tests contaminate elapsed-time comparison.',
                  'completion_token_limitation': 'Output token IDs are not retained. Exact reported '
                      'completion usage is reconciled against durable receipts and the frozen '
                      'tensor-length counting implementation; decoded text alone cannot '
                      'independently reproduce every generated special token.',
                  'checks': ['frozen sources', 'installed runtime hashes', 'public-only prompts',
                             'memory lineage', 'version binding', 'public verifier receipts',
                             'authority bindings', 'per-call budget', 'cumulative ledger',
                             'final SQLite receipts', 'final selection', 'summary aggregation']}, indent=2))
