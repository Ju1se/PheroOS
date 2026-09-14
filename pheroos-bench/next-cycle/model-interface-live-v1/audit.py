#!/usr/bin/env python3
"""Independent, stdlib-only audit of the fixed model-interface diagnostic.

Read-only input: retained terminal files and isolated immutable SQLite copies.
No runtime, task, tokenizer, CUDA or model imports. Exit 0 means record integrity,
not model capability or admission. Exit 2 means findings/input error; 4 pending.
"""
import argparse
import ast
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile

CONFIG_SHA = 'ed833e52d72e5a042fc56f0616c9ced9c52fe534302cfedc630da3445a3c1a8e'
PREFLIGHT_SHA = '2c12f0eb847a134dc2867f5d0d171b3c34ca9f4d516da6fe07b254b20dfa3086'
TASK_SHA = '715d82fca4a0f7995df8c424e510972716e9d983e47784b2eade10f2d1578d2b'
ARMS = ['direct_json_256', 'compact_action_256', 'envelope_256', 'envelope_1024']
DISPATCHED = {'dispatched', 'received', 'response_rejected'}
TOTAL_FIELDS = ('model_calls', 'tool_calls', 'known_tokens', 'input_tokens', 'output_tokens',
                'control_operations', 'call_units')


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return sha256(wire(value).encode()).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def nonfinite(value):
    raise ValueError('nonfinite JSON number')


def obj(value):
    return json.loads(value, object_pairs_hook=pairs, parse_constant=nonfinite) if isinstance(value, (str, bytes)) else value


class Pending(Exception):
    pass


class Audit:
    def __init__(self, campaign):
        self.campaign = campaign.resolve()
        self.hashes, self.findings, self.notes, self.check_count = {}, [], [], 0
        self.source_snapshots = {}

    def read(self, path):
        path = Path(path).resolve()
        data = path.read_bytes()
        identity = sha256(data).hexdigest()
        if path in self.hashes and self.hashes[path] != identity:
            raise Pending('input changed during audit')
        self.hashes[path] = identity
        return data

    def json(self, path):
        return obj(self.read(path))

    def source(self, original, expected_sha, source_site=None):
        """Resolve accepted wheel files without rewriting the frozen path record."""
        resolved = source_path(original, source_site)
        data = self.read(resolved)
        actual_sha = sha256(data).hexdigest()
        self.source_snapshots[str(original)] = dict(resolved_path=str(resolved),
            expected_sha256=expected_sha, actual_sha256=actual_sha)
        self.check(actual_sha == expected_sha, 'frozen_source_unchanged', original)
        return data

    def check(self, condition, code, location):
        self.check_count += 1
        if not condition:
            self.findings.append({'check': code, 'location': str(location)})

    def note(self, code, location):
        self.notes.append({'observation': code, 'location': str(location)})

    def database(self, path):
        path = Path(path).resolve()
        for suffix in ('-wal', '-journal'):
            sidecar = Path(str(path) + suffix)
            if sidecar.exists() and sidecar.stat().st_size:
                raise Pending('nonempty SQLite sidecar; await settled database')
        with tempfile.TemporaryDirectory(prefix='pheroos-interface-audit-db-') as temp:
            copy = Path(temp) / 'retained.sqlite'
            copy.write_bytes(self.read(path))
            with sqlite3.connect(copy.as_uri() + '?mode=ro&immutable=1', uri=True) as db:
                db.row_factory = sqlite3.Row
                self.check(db.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'sqlite_integrity', path)
                tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                allowed = ('run', 'work', 'calls', 'artifacts', 'events', 'campaign', 'allotments', 'model_slots',
                           'coordination_v1', 'coordination_operations_v1')
                return {t: [dict(r) for r in db.execute('SELECT * FROM ' + t + ' ORDER BY rowid')]
                        for t in allowed if t in tables}

    def stable(self):
        for path, expected in self.hashes.items():
            if not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected:
                raise Pending('retained inputs changed during audit')


def source_path(original, source_site=None):
    original = Path(original)
    if source_site is None:
        return original.resolve()
    site = Path(source_site).resolve()
    matches = [i for i, part in enumerate(original.parts)
               if part in {'pheroos_bench', 'pheroos_runtime', 'pheroos'}]
    if len(matches) != 1:
        raise ValueError('frozen source must contain exactly one known package marker')
    suffix = original.parts[matches[0]:]
    if '..' in suffix or len(suffix) < 2:
        raise ValueError('frozen source package suffix is not a file path')
    resolved = site.joinpath(*suffix).resolve()
    if not resolved.is_relative_to(site):
        raise ValueError('resolved source escapes the supplied wheel site')
    return resolved


def session_snapshot(db):
    calls = db['calls']
    return dict(run=db['run'][0], work=db['work'], calls=calls, artifacts=db['artifacts'],
        events=[obj(e['value']) for e in db['events']],
        actual_tokens=sum(c['actual'] or 0 for c in calls),
        reserved_tokens=sum(c['reserved'] for c in calls if c['state'] == 'reserved'),
        unknown_tokens=sum(c['reserved'] for c in calls if c['state'] == 'dispatched'),
        unknown_calls=sum(c['state'] == 'dispatched' for c in calls), call_count=len(calls))


def coordination_snapshot(db):
    operations = db['coordination_operations_v1']
    return dict(schema='coordination.v1', limits=obj(db['coordination_v1'][0]['limits']), operations=operations,
        control_operations=len(operations), request_bytes=sum(r['request_bytes'] for r in operations),
        materialized_bytes=sum(r['materialized_bytes'] for r in operations),
        serialized_bytes=sum(r['serialized_bytes'] for r in operations),
        denied_operations=sum(r['outcome'] == 'denied' for r in operations))


def grid(config):
    result = []
    for wi, world in enumerate(config['worlds']):
        for si, seed in enumerate(config['seed_bases']):
            offset = (wi + si) % 4
            for arm in ARMS[offset:] + ARMS[:offset]:
                result.append(dict(world=world, arm=arm, seed=seed + 100 * wi))
    return result


def cell(row):
    return row['world_id'], row['arm'], row['seed']


def task_inputs(source):
    # Only public fixture inputs, not _EXPECTED, score or executable task code.
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_INPUTS' for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('public input fixture literal missing')


def documents(world, inputs):
    x, family = inputs[world], world.split('/')[0]
    if family == 'interval_intersection':
        return {'lower_bounds': {'bounds': x['lower']}, 'upper_bounds': {'bounds': x['upper']}, 'preference': {'preferred': x['preferred']}}
    if family == 'dependency_readiness':
        return {'dependency_graph': {'dependencies': x['edges']}, 'completion_state': {'completed': x['completed']}}
    if family == 'inventory_reconciliation':
        return {'opening_balances': {'balances': x['opening']}, 'change_events': {'events': [dict(zip(('event_id', 'batch', 'item', 'delta'), r)) for r in x['changes']]}, 'approved_batches': {'batches': x['approved']}}
    if family == 'version_correction':
        return {'current_values': {'values': x['after']}}
    raise ValueError('unknown family')


def final_answer(world, inputs):
    x, family = inputs[world], world.split('/')[0]
    if family == 'interval_intersection':
        low, high = max(x['lower']), min(x['upper'])
        if low > high:
            raise ValueError('unsupported infeasible interval')
        return {'selection': min(max(x['preferred'], low), high)}
    if family == 'dependency_readiness':
        completed = set(x['completed'])
        return {'ready': sorted(k for k, deps in x['edges'].items() if k not in completed and set(deps) <= completed)}
    if family == 'version_correction':
        return {'value': x['after'][x['query']]}
    totals, seen = dict(x['opening']), set()
    for event, batch, item, delta in x['changes']:
        if batch in x['approved'] and event not in seen:
            totals[item] += delta
            seen.add(event)
    return {'totals': totals}


def answer_shape(world, answer, inputs):
    if type(answer) is not dict:
        return False
    family = world.split('/')[0]
    bounded = lambda x: type(x) is int and abs(x) <= 10**9
    if family in {'interval_intersection', 'version_correction'}:
        name = 'selection' if family == 'interval_intersection' else 'value'
        return set(answer) == {name} and bounded(answer[name])
    if family == 'dependency_readiness':
        ready = answer.get('ready')
        return (set(answer) == {'ready'} and type(ready) is list and all(type(x) is str and x in inputs[world]['edges'] for x in ready)
                and len(set(ready)) == len(ready))
    return (set(answer) == {'totals'} and type(answer['totals']) is dict
            and set(answer['totals']) == set(inputs[world]['opening']) and all(bounded(v) for v in answer['totals'].values()))


def independent_validation(world, arm, raw, evidence, inputs):
    """Independent acceptance/stage calculation; error prose is not duplicated."""
    framing, action = 'plain_json', None
    try:
        if type(raw) is not str or len(raw.encode()) > 16384:
            raise ValueError('not bounded text')
        text = raw.strip()
        if text.startswith('```json\n') and text.endswith('\n```') and text.count('```') == 2:
            text, framing = text[8:-4], 'single_json_fence'
        value = obj(text)
    except (ValueError, TypeError, RecursionError):
        return False, 'transport_format', None, None
    if arm == 'direct_json_256':
        if not answer_shape(world, value, inputs):
            return False, 'action_schema', None, framing
        action = dict(action='submit', answer=value,
                      citations=[{k: r[k] for k in ('source_id', 'source_version')} for r in evidence])
        # The shared action validator parses the syntax-only compiled plain JSON.
        framing = 'plain_json'
    else:
        action = value
    if type(action) is not dict:
        return False, 'action_schema', action, framing
    if action.get('action') == 'inspect':
        stage = 'action_schema'
        if set(action) == {'action', 'target'} and type(action['target']) is str:
            if action['target'] not in set(documents(world, inputs)) | {'unrelated_notice'}:
                stage = 'undeclared_target'
        return False, stage, action, framing
    if action.get('action') != 'submit' or set(action) != {'action', 'answer', 'citations'} or not answer_shape(world, action.get('answer'), inputs):
        return False, 'action_schema', action, framing
    citations = action['citations']
    if (type(citations) is not list or len(citations) > 4
            or any(type(c) is not dict or set(c) != {'source_id', 'source_version'}
                   or type(c['source_id']) is not str or type(c['source_version']) is not int for c in citations)):
        return False, 'action_schema', action, framing
    expected = [{k: r[k] for k in ('source_id', 'source_version')} for r in evidence]
    if wire(sorted(citations, key=wire)) != wire(sorted(expected, key=wire)):
        return False, 'missing_or_stale_evidence', action, framing
    return True, 'accepted', action, framing


def audit_episode(audit, row, item, path, inputs, model_identity, preflight):
    raw_path, db_path = path / 'episode.json', path / 'session.sqlite'
    if not raw_path.exists():
        audit.check(row['status'] == 'INVALID_ABORT' and row.get('metrics') is None and row.get('complete') is False,
                    'missing_raw_requires_abort_unknown_cost', path)
        audit.note('attempt_without_retained_episode_no_quality_estimate', path)
        return None
    raw = audit.json(raw_path)
    audit.check(raw == row, 'aggregate_matches_raw_episode', path)
    audit.check(row['counts_toward_verdict'] is False and row['instrument_only'] is False, 'live_development_exclusion', path)
    audit.check(row['n'] == 1 and row['model_identity'] == model_identity, 'same_model_single_agent', path)
    direct = item['arm'] == 'direct_json_256'
    audit.check(row['citations_origin'] == ('runtime_supplied' if direct else 'model_supplied')
                and row['model_citation_selection_measured'] is (not direct), 'citation_responsibility_explicit', path)
    if not db_path.is_file() or not (path / 'session-snapshot.json').is_file():
        audit.check(row['status'] == 'INVALID_ABORT' and row['objective_success'] is None, 'missing_session_cannot_be_known_quality', path)
        audit.note('session_not_retained_cost_not_independently_recoverable', path)
        return None
    db = audit.database(db_path)
    snapshot = audit.json(path / 'session-snapshot.json')
    audit.check(snapshot == session_snapshot(db), 'session_snapshot_matches_sqlite', path)
    coord = audit.json(path / 'coordination-accounting.json')
    audit.check(coord == coordination_snapshot(db), 'coordination_accounting_matches_sqlite', path)
    calls, events = snapshot['calls'], snapshot['events']
    call_map = {c['id']: c for c in calls}
    audit.check(len(call_map) == len(calls), 'unique_call_id', path)
    audit.check(snapshot['run']['status'] in {'completed', 'cancelled', 'revoked'} and not snapshot['run']['enabled'], 'session_terminal_current_authority_disabled', path)
    audit.check(obj(snapshot['run']['agents']) == ['agent0'], 'single_declared_agent', path)
    limits = obj(snapshot['run']['limits'])
    audit.check(limits['token_cap'] == 2048, 'fixed_episode_token_cap', path)
    models = [c for c in calls if c['action'] == 'model.generate' and c['state'] in DISPATCHED]
    tools = [c for c in calls if c['action'] == 'tool.evaluate' and c['state'] in DISPATCHED]
    publications = sum(e['event_type'] == 'ext.session.published' for e in events)
    metrics = dict(model_calls=len(models), tool_calls=len(tools), known_tokens=snapshot['actual_tokens'],
        unknown_tokens=snapshot['unknown_tokens'], unknown_calls=snapshot['unknown_calls'],
        input_tokens=sum(c['prompt'] for c in models if c['actual'] is not None),
        output_tokens=sum(c['actual'] - c['prompt'] for c in models if c['actual'] is not None),
        control_operations=len(events) + publications, verification_operations=publications,
        preparation_tools=len(row['preparations']), event_bytes=len(wire(events).encode()),
        model_prompt_bytes=len(wire(row['messages']).encode()) if row['messages'] else None,
        materialized_bytes=coord['materialized_bytes'], coordination_request_bytes=coord['request_bytes'])
    metrics['call_units'] = metrics['model_calls'] + metrics['tool_calls'] + metrics['control_operations']
    for field, value in metrics.items():
        audit.check(row['metrics'][field] == value, 'independent_metric_' + field, path)
    audit.check(row['metrics']['monetary_cost'] is None and row['metrics']['monetary_cost_status'] == 'not_measured_local_inference', 'local_monetary_cost_not_zero', path)
    audit.check(not any(e['event_type'] == 'ext.session.message_sent' for e in events), 'no_mailbox_communication_claim', path)
    for call in calls:
        audit.check(call['state'] in DISPATCHED | {'reserved', 'abandoned'}, 'declared_call_state', path)
        if call['state'] in {'reserved', 'dispatched'}:
            audit.check(call['actual'] is None, 'unsettled_tokens_not_zero', path)
        else:
            audit.check(type(call['actual']) is int and call['actual'] >= 0, 'settled_usage_nonnegative_integer', path)
        if call['action'] == 'tool.evaluate' and call['state'] == 'received':
            response = obj(call['response'])
            audit.check(call['actual'] == 0 and response['prompt_tokens'] == response['completion_tokens'] == 0,
                        'tool_has_no_model_token_usage_but_is_counted', path)
    docs = documents(item['world'], inputs)
    version = 2 if item['world'].startswith('version_correction/') else 1
    artifacts = {a['ref']: a for a in snapshot['artifacts']}
    audit.check(len(row['preparations']) == len(row['materialized']), 'one_materialization_per_preparation', path)
    for prep, evidence in zip(row['preparations'], row['materialized']):
        sid = prep['source_id']
        expected_receipt = dict(data_version='coordination_repair_tasks_v1', kind='source_receipt', world_id=item['world'],
                               source_id=sid, source_version=version, content=docs.get(sid))
        expected_receipt['receipt_identity'] = 'sha256:' + digest(expected_receipt)
        audit.check(evidence == expected_receipt, 'actual_current_source_content_and_provenance', path)
        artifact, call = artifacts.get(prep['artifact_ref']), call_map.get(prep['call_id'])
        audit.check(artifact is not None and obj(artifact['value']) == evidence and artifact['publisher'] == 'agent0'
                    and artifact['call_id'] == prep['call_id'], 'materialized_source_published_by_charged_tool', path)
        audit.check(call is not None and call['state'] == 'received' and call['action'] == 'tool.evaluate'
                    and obj(call['response'])['artifact'] == evidence, 'preparation_settled_receipt', path)
        if call:
            request = obj(call['request'])
            audit.check(request['tool_ref'] == 'inspect_source' and request['arguments'] ==
                        dict(world=item['world'], source_id=sid, source_version=version), 'preparation_exact_public_inspection', path)
    prompt = row['messages']
    if prompt is not None:
        audit.check(row['prompt_sha256'] == digest(prompt), 'prompt_raw_hash', path)
        fixture = preflight[(item['world'], item['arm'])]
        audit.check(row['prompt_sha256'] == fixture['prompt_sha256'] and row['preflight_prompt_tokens'] == fixture['prompt_tokens'],
                    'prompt_matches_preapproved_tokenizer_preflight', path)
    maximum = 1024 if item['arm'] == 'envelope_1024' else 256
    audit.check(row['max_new_tokens'] == maximum and row['context_tokens'] == 2048, 'declared_output_context', path)
    audit.check(len(models) <= 1, 'at_most_one_response_attempt_no_retry', path)
    for call in models:
        request = obj(call['request'])
        audit.check(request['messages'] == prompt and request['seed'] == item['seed']
                    and request['max_new_tokens'] == maximum and request['model_identity'] == model_identity,
                    'actual_model_request_fixed_cell_binding', path)
        audit.check(call['maximum'] == maximum and call['reserved'] == call['prompt'] + maximum <= 2048
                    and call['prompt'] == row['preflight_prompt_tokens'], 'actual_context_reservation', path)
        if call['state'] == 'received':
            response = obj(call['response'])
            audit.check(row['response'] == response, 'raw_response_matches_sqlite_receipt', path)
            ids = response['generated_token_ids']
            audit.check(type(ids) is list and all(type(t) is int and t >= 0 for t in ids)
                        and response['completion_tokens'] == len(ids) <= maximum
                        and response['prompt_tokens'] == call['prompt']
                        and call['actual'] == response['prompt_tokens'] + len(ids), 'actual_tensor_token_accounting', path)
            audit.check(response['token_counting_basis'] == 'actual_input_and_generated_tensor_ids'
                        and response['prompt_token_ids_sha256'] == preflight[(item['world'], item['arm'])]['input_ids_sha256'],
                        'prompt_token_ids_bound_to_independent_preflight', path)
            audit.check(row['output_at_cap'] is (len(ids) == maximum), 'output_cap_exact_id_count', path)
    validation, response = row['validation'], row['response']
    if validation is not None:
        call = call_map.get('validate-0')
        audit.check(call is not None and call['state'] == 'received' and obj(call['response'])['artifact'] == validation,
                    'public_validation_settled_tool_binding', path)
        if call:
            request = obj(call['request'])
            audit.check(request['tool_ref'] == 'validate_response' and request['arguments'] ==
                        dict(raw=response['text'], materialized=row['materialized']), 'validator_received_actual_text_and_receipts', path)
        accepted, stage, action, framing = independent_validation(item['world'], item['arm'], response['text'], row['materialized'], inputs)
        audit.check(validation['valid'] is accepted and validation['stage'] == stage and validation['framing'] == framing,
                    'independent_public_acceptance_stage', path)
        if direct and action is not None:
            audit.check(validation['compiled_action'] == action, 'direct_syntax_only_compilation_no_answer_repair', path)
        if accepted:
            expected_submission = dict(data_version='coordination_repair_tasks_v1', kind='submission', world_id=item['world'],
                task_version=version, answer=action['answer'], citations=sorted(action['citations'], key=wire),
                evidence_receipt_identities=[r['receipt_identity'] for r in row['materialized']])
            expected_submission['receipt_identity'] = 'sha256:' + digest(expected_submission)
            audit.check(row['submission'] == validation['artifact'] == expected_submission,
                        'submission_preserves_actual_answer_current_evidence', path)
        else:
            audit.check(row['submission'] is None and validation['artifact'] is None, 'rejected_action_no_submission', path)
    if row['status'] == 'VALID_KNOWN':
        audit.check(row['complete'] is True and row['error'] is None and row['stop'] == 'single_response_complete'
                    and snapshot['unknown_calls'] == snapshot['reserved_tokens'] == 0 and len(models) == 1,
                    'known_complete_terminal_semantics', path)
        audit.check({r['source_id'] for r in row['materialized']} == set(docs) and len(row['materialized']) == len(docs)
                    and len(tools) == len(docs) + 1, 'same_complete_charged_preparation_plus_validation', path)
        audit.check(row['public_accepted'] is validation['valid'], 'public_acceptance_is_not_objective', path)
        answer = row['submission']['answer'] if row['submission'] else None
        if isinstance(answer, dict) and isinstance(answer.get('ready'), list):
            answer = {**answer, 'ready': sorted(answer['ready'])}
        correct = bool(row['submission']) and wire(answer) == wire(final_answer(item['world'], inputs))
        audit.check(row['objective_success'] is correct, 'independent_public_rule_objective', path)
    else:
        audit.check(row['status'] in {'INVALID_ABORT', 'VALID_UNRESOLVED'} and row['complete'] is False
                    and row['objective_success'] is None and row['public_accepted'] is None,
                    'abort_unresolved_not_quality_failure_or_zero', path)
        if snapshot['unknown_calls']:
            audit.check(snapshot['unknown_tokens'] > 0, 'unknown_model_usage_keeps_reservation', path)
    return dict(world_id=item['world'], arm=item['arm'], seed=item['seed'], status=row['status'], **metrics,
                model_intents=sum(c['action'] == 'model.generate' for c in calls), expected_answer=final_answer(item['world'], inputs))


def summary(records, expected):
    valid = ([cell(r) for r in records] == [(r['world'], r['arm'], r['seed']) for r in expected]
             and all(r['status'] == 'VALID_KNOWN' and r['complete'] is True for r in records))
    base = dict(profile='model_interface_descriptive_v1', counts_toward_verdict=False,
                collaboration_admitted=False, independent_unit='world; seeds are repeated observations within world')
    if not valid:
        return dict(status='INVALID', effects=None, reason='incomplete or unresolved declared campaign',
                    counts_toward_verdict=False, collaboration_admitted=False, instrument_only=False)
    groups = {}
    for arm in ARMS:
        rows = [r for r in records if r['arm'] == arm]
        groups[arm] = dict(episodes=len(rows), worlds=len({r['world_id'] for r in rows}),
            public_accepted=sum(r['public_accepted'] for r in rows), objective_successes=sum(r['objective_success'] for r in rows),
            output_cap_hits=sum(r['output_at_cap'] for r in rows),
            failure_stages=dict(Counter(r['validation']['stage'] for r in rows if not r['public_accepted'])),
            totals={k: sum(r['metrics'][k] for r in rows) for k in TOTAL_FIELDS})
    worlds = {}
    for world in sorted({r['world_id'] for r in records}):
        worlds[world] = {}
        for arm in ARMS:
            rows = [r for r in records if r['world_id'] == world and r['arm'] == arm]
            worlds[world][arm] = dict(public_accepted_mean=sum(r['public_accepted'] for r in rows) / len(rows),
                                      objective_success_mean=sum(r['objective_success'] for r in rows) / len(rows))
    return dict(**base, status='VALID_KNOWN', groups=groups, worlds=worlds, instrument_only=False)


def run_audit(campaign, prepared, predecessor, source_site=None):
    campaign, audit = campaign.resolve(), Audit(campaign)
    if not (campaign / 'campaign-completion.json').is_file() or not (campaign / 'summary.json').is_file():
        raise Pending('terminal completion and summary not retained yet')
    config = audit.json(campaign / 'frozen-config.json')
    audit.check(digest(config) == CONFIG_SHA, 'exact_authorized_configuration', campaign)
    audit.check(config == audit.json(prepared / 'pilot-config-proposal.json'), 'proposal_matches_executed_config', campaign)
    freeze = audit.json(campaign / 'freeze.json')
    audit.check(freeze['config_sha256'] == CONFIG_SHA and freeze['counts_toward_verdict'] is False
                and freeze['instrument_only'] is False and freeze['operator_asserted_authorization'] is True
                and freeze['operator_assertion_is_runtime_authority'] is False, 'frozen_identity_and_authority_separation', campaign)
    source_bytes = {path: audit.source(path, expected_sha, source_site)
                    for path, expected_sha in freeze['sources'].items()}
    fixture_paths = [Path(p) for p in freeze['sources'] if Path(p).name == 'coordination_repair_v1_tasks.py']
    audit.check(len(fixture_paths) == 1, 'one_frozen_task_source', campaign)
    fixture_source = source_bytes[str(fixture_paths[0])]
    audit.check(sha256(fixture_source).hexdigest() == TASK_SHA, 'original_public_task_fixture_identity', campaign)
    inputs = task_inputs(fixture_source)
    preflight_rows = audit.json(prepared / 'tokenizer-preflight.json')['rows']
    audit.check(audit.hashes[(prepared / 'tokenizer-preflight.json').resolve()] == PREFLIGHT_SHA,
                'preapproved_tokenizer_preflight_bytes', prepared)
    preflight = {(r['world'], r['arm']): r for r in preflight_rows}
    audit.check(len(preflight) == len(preflight_rows) == 32, 'complete_precollected_tokenizer_preflight', prepared)
    expected = grid(config)
    audit.check(audit.json(campaign / 'expected-grid.json') == expected and len(expected) == 64, 'fixed_64_counterbalanced_grid', campaign)
    records = audit.json(campaign / 'records.json')
    completion = audit.json(campaign / 'campaign-completion.json')
    audit.check(completion['records_sha256'] == digest(records), 'completion_records_hash', campaign)
    audit.check(completion['declared'] == 64 and completion['executed'] == len(records) <= 64, 'whole_grid_denominator', campaign)
    audit.check(len({cell(r) for r in records}) == len(records), 'unique_world_seed_arm', campaign)
    audit.check([cell(r) for r in records] == [(r['world'], r['arm'], r['seed']) for r in expected[:len(records)]],
                'records_are_exact_execution_prefix', campaign)
    unstarted = [{**r, 'outcome': None, 'cost': None} for r in expected[len(records):]]
    audit.check(completion['unstarted'] == unstarted, 'unstarted_cost_and_outcome_null', campaign)
    if (campaign / 'completed.jsonl').is_file():
        journal = [obj(line) for line in audit.read(campaign / 'completed.jsonl').splitlines() if line]
        audit.check(journal == records[:len(journal)] and (len(journal) == len(records) or completion['status'] != 'COMPLETE'),
                    'append_journal_preserves_exact_prefix', campaign)
    identity_path = campaign / 'model-identity.json'
    identity = audit.json(identity_path) if identity_path.is_file() else None
    if identity:
        audit.check(identity['adapter'] == 'recorded_local_v3' and identity['generation'] ==
                    dict(context_tokens=2048, do_sample=True, temperature='0.7', top_p='0.9', top_k=50, max_output_tokens=1024),
                    'same_new_adapter_all_arms', campaign)
        audit.check(identity['model_manifest']['repository'] == config['model']['repository']
                    and identity['model_manifest']['revision'] == config['model']['revision']
                    and identity['model_manifest'] == audit.json(predecessor / 'model-identity.json')['model_manifest'],
                    'same_declared_existing_model_manifest', campaign)
    audited, snapshots = [], {}
    for index, row in enumerate(records):
        item = expected[index]
        path = campaign / f"episode-{index:03d}-{item['arm']}"
        value = audit_episode(audit, row, item, path, inputs, identity, preflight)
        if value:
            audited.append(value)
    audit.check({p.name for p in campaign.glob('episode-*') if p.is_dir()} <=
                {f"episode-{i:03d}-{item['arm']}" for i, item in enumerate(expected[:len(records)])}, 'no_unreported_episode_attempts', campaign)
    index = {cell(r): r for r in records}
    for world in config['worlds']:
        wi = config['worlds'].index(world)
        for base in config['seed_bases']:
            a, b = index.get((world, 'envelope_256', base + 100 * wi)), index.get((world, 'envelope_1024', base + 100 * wi))
            if a and b and a.get('messages') and b.get('messages'):
                audit.check(wire(a['messages']) == wire(b['messages']) and a['model_identity'] == b['model_identity']
                            and a['materialized'] == b['materialized'], 'envelope_pair_only_declared_output_allowance_changes', world)
    accounting = audit.json(campaign / 'accounting.json')
    db = audit.database(campaign / 'campaign.sqlite')
    campaign_row, allotments = db['campaign'][0], db['allotments']
    audit.check(campaign_row['config_digest'] == CONFIG_SHA and campaign_row['token_cap'] == 131072
                and campaign_row['dispatch_cap'] == 64, 'current_campaign_fixed_caps', campaign)
    audit.check(accounting.get('allotments') == allotments, 'all_allotments_retained', campaign)
    for allocation in allotments:
        original = Path(allocation['path'])
        # Relative episode identity is retained when published bytes are audited elsewhere.
        path = campaign / allocation['id'] / 'session.sqlite'
        audit.check(original.parent.name == allocation['id'] and original.name == 'session.sqlite', 'allocation_child_path_identity', campaign)
        audit.check(allocation['tokens'] == 2048 and allocation['model_cap'] == 1, 'one_intent_per_episode_cap', path)
        if not path.is_file():
            audit.check(allocation['state'] == 'allocated' and allocation['known_tokens'] is None
                        and allocation['held_tokens'] == allocation['tokens'], 'missing_child_retains_full_unknown_allocation', path)
            continue
        snap = session_snapshot(audit.database(path))
        intents = {c['id'] for c in snap['calls'] if c['action'] == 'model.generate'}
        slots = [s['call_id'] for s in db['model_slots'] if s['allocation_id'] == allocation['id']]
        audit.check(len(slots) == len(set(slots)) <= 1 and intents <= set(slots), 'model_intents_unique_conservatively_reserved', path)
        if intents != set(slots):
            audit.note('reserved_intent_without_session_call_retained', path)
        limits = obj(snap['run']['limits'])
        audit.check(limits['token_cap'] == allocation['tokens'] and limits['max_calls'] == allocation['calls'], 'child_budget_matches_allotment', path)
        if allocation['state'] == 'terminal':
            audit.check(allocation['snapshot_digest'] == digest(snap), 'terminal_allocation_snapshot_binding', path)
            audit.check(allocation['known_tokens'] == snap['actual_tokens'] and allocation['unknown_tokens'] == snap['unknown_tokens'],
                        'allotment_receipts_match_actual_tokens', path)
            audit.check(allocation['held_tokens'] == snap['actual_tokens'] + snap['unknown_tokens'] + snap['reserved_tokens']
                        and allocation['held_calls'] == len(intents), 'unknown_reserved_usage_not_released', path)
    for field, actual in dict(held_token_upper_bound=sum(a['held_tokens'] for a in allotments),
        held_call_slots=sum(a['held_calls'] for a in allotments), known_tokens=sum(a['known_tokens'] or 0 for a in allotments),
        known_tokens_complete=all(a['known_tokens'] is not None for a in allotments)).items():
        audit.check(accounting.get(field) == actual, 'campaign_accounting_' + field, campaign)
    audit.check(accounting['held_token_upper_bound'] <= 131072 and accounting['held_call_slots'] <= 64, 'no_campaign_cap_violation', campaign)
    prior = dict(known_tokens=65662, retained_intent_slots=114,
                 predecessor_combined_sha256=config['continuation']['prior_files']['combined-accounting.json'])
    audit.check(freeze['predecessor'] == prior, 'closed_prior_cost_identity_retained', campaign)
    for name, expected_sha in config['continuation']['prior_files'].items():
        audit.check(sha256(audit.read(predecessor / name)).hexdigest() == expected_sha, 'predecessor_frozen_raw_bytes', predecessor / name)
    old = audit.json(predecessor / 'combined-accounting.json')
    audit.check(old['held_token_upper_bound'] == 65662 and old['held_intent_slots'] == 114, 'prior_65662_tokens_114_intents', predecessor)
    combined = audit.json(campaign / 'combined-accounting.json')
    audit.check(combined['current'] == accounting and combined['predecessor'] == prior
                and combined['held_token_upper_bound'] == accounting['held_token_upper_bound'] + 65662
                and combined['held_intent_slots'] == accounting['held_call_slots'] + 114
                and combined['total_token_cap'] == 500000 and combined['total_intent_cap'] == 1000,
                'combined_prior_and_new_liability', campaign)
    settled = (accounting['known_tokens_complete'] is True and accounting['violation'] is None
               and all(a['state'] == 'terminal' and a['unknown_tokens'] == 0 for a in allotments))
    complete = completion['failure'] is None and len(records) == 64 and settled
    audit.check((completion['status'] == 'COMPLETE') is complete, 'complete_includes_accounting_and_full_grid', campaign)
    independently_summarized = summary(records, expected) if complete else dict(status='INVALID', effects=None,
        reason='incomplete or unresolved declared campaign', counts_toward_verdict=False, collaboration_admitted=False, instrument_only=False)
    audit.check(audit.json(campaign / 'summary.json') == independently_summarized, 'independent_full_grid_summary_no_subset', campaign)
    audit.check(config['admission_thresholds'] is None and config['collaboration_admitted'] is False
                and not any(campaign.glob('*admission*')), 'diagnostic_never_opens_collaboration', campaign)
    audit.stable()
    return dict(profile='model_interface_independent_audit_v1', status='PASS' if not audit.findings else 'FINDINGS',
        campaign=str(campaign), campaign_status=completion['status'], config_sha256=CONFIG_SHA,
        checks_evaluated=audit.check_count, findings=audit.findings, observations=audit.notes,
        declared_cells=64, retained_cells=len(records), audited_session_cells=len(audited), unstarted_cells=len(unstarted),
        status_counts=dict(Counter(r['status'] for r in records)), episode_accounting=audited,
        audited_known_portion_totals={k: sum(r[k] for r in audited) for k in (*TOTAL_FIELDS, 'unknown_tokens', 'unknown_calls', 'model_intents')},
        totals_cover_all_retained_cells=len(audited) == len(records), independent_summary=independently_summarized,
        accounting=accounting, combined_accounting=combined, input_sha256={str(p): h for p, h in sorted(audit.hashes.items())},
        source_resolution='original_paths' if source_site is None else 'accepted_wheel_site_with_exact_package_suffix',
        source_snapshots=audit.source_snapshots, source_snapshot_sha256=digest(audit.source_snapshots),
        counts_toward_verdict=False, collaboration_admitted=False, limitations=[
            'Read-only post-run record, ledger and public-rule audit; not authorization, efficacy, robustness or admission evidence.',
            'Eight already observed development worlds; two seeds are repeated measurements inside each world.',
            'Public parser acceptance and rule arithmetic independently recomputed; Governance proof semantics are not reimplemented.',
            'Generated token IDs are retained; prompt IDs are retained as a digest checked against frozen CPU-tokenizer preflight, not raw IDs.',
            'No model weights loaded, token decoding/retokenization, CUDA replay, timing calibration, money estimation or network request.',
            'Direct runtime-supplied citations do not measure model citation selection; whole-presentation and joint output-responsibility contrasts remain confounded.',
            'INVALID, unknown and unstarted rows are retained; no valid-subset effect export on an incomplete campaign.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--predecessor', type=Path, required=True)
    parser.add_argument('--source-site', type=Path,
                        help='Optional extracted/installed accepted wheels root; every frozen source hash must match')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    campaign, output = args.campaign.resolve(), args.output.resolve()
    if output.exists() or output.is_relative_to(campaign):
        parser.error('output must be new and outside the campaign')
    try:
        report = run_audit(campaign, args.prepared.resolve(), args.predecessor.resolve(), args.source_site)
    except Pending as exc:
        print(wire(dict(status='PENDING', reason=str(exc), campaign_data_written=False)))
        return 4
    except (OSError, ValueError, TypeError, KeyError, IndexError, sqlite3.Error) as exc:
        print(wire(dict(status='AUDIT_INPUT_ERROR', exception_type=type(exc).__name__, message=str(exc), campaign_data_written=False)))
        return 2
    report['audit_helper_sha256'] = sha256(Path(__file__).read_bytes()).hexdigest()
    with output.open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(wire(dict(status=report['status'], checks=report['checks_evaluated'], findings=len(report['findings']),
                    campaign_status=report['campaign_status'], output=str(output), counts_toward_verdict=False)))
    return 0 if report['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
