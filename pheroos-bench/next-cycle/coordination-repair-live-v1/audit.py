#!/usr/bin/env python3
"""Read-only, standard-library audit of the terminal, authorized dev4 A campaign.

No runtime/model imports, provider calls, or writes under the campaign directory.
SQLite is opened only after copying retained bytes to an isolated temporary dir.
Exit 4 means collection/audit inputs are not yet stable; 2 means audit findings;
0 means accounting/record integrity passed, NOT admission or research efficacy.
"""
import argparse
import ast
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile

CORE = Path('/tmp/pheroos-next-cycle-core/pheroos-bench')
DEFAULT_CAMPAIGN = CORE / 'next-cycle/coordination-repair-live-v1/campaign'
CONFIG_SHA = '916e2b2f05e32059b2e0ca35e1ce70f9708b8a98059cc40aface055cb86b6193'
DISPATCHED = {'dispatched', 'received', 'response_rejected'}
TERMINAL = {'public_accepted_submission', 'diagnostic_one_submission_opportunity', 'budget_deadline_stop'}


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return sha256(wire(value).encode()).hexdigest()


def strict_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate JSON key')
        out[key] = value
    return out


def obj(value):
    return json.loads(value, object_pairs_hook=strict_pairs) if isinstance(value, (str, bytes)) else value


class Pending(Exception):
    pass


class Audit:
    def __init__(self, campaign):
        self.campaign = campaign.resolve()
        self.hashes, self.findings, self.notes, self.check_count = {}, [], [], 0

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
        with tempfile.TemporaryDirectory(prefix='pheroos-independent-db-') as temp:
            copied = Path(temp) / 'retained.sqlite'
            copied.write_bytes(self.read(path))
            with sqlite3.connect(copied.as_uri() + '?mode=ro&immutable=1', uri=True) as db:
                db.row_factory = sqlite3.Row
                self.check(db.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'sqlite_integrity', path)
                tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                # Only these fixed identifiers ever enter SQL.
                allowed = ('run', 'work', 'calls', 'artifacts', 'events', 'campaign', 'allotments', 'model_slots')
                return {t: [dict(r) for r in db.execute('SELECT * FROM ' + t + ' ORDER BY rowid')]
                        for t in allowed if t in tables}

    def stable(self):
        for path, expected in self.hashes.items():
            if not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected:
                raise Pending('retained inputs changed during audit')


def session_snapshot(db):
    calls = db['calls']
    return dict(run=db['run'][0], work=db['work'], calls=calls, artifacts=db['artifacts'],
        events=[obj(e['value']) for e in db['events']],
        actual_tokens=sum(c['actual'] or 0 for c in calls),
        reserved_tokens=sum(c['reserved'] for c in calls if c['state'] == 'reserved'),
        unknown_tokens=sum(c['reserved'] for c in calls if c['state'] == 'dispatched'),
        unknown_calls=sum(c['state'] == 'dispatched' for c in calls), call_count=len(calls))


def grid(config):
    spec = config['actionability']
    rows = [dict(world=w, arm='single', n=1, condition=c, component='capability', **limits)
            for w in spec['worlds'] for c, limits in spec['conditions'].items()]
    p = spec['intervention_probes']
    return rows + [dict(world=w, arm=a, n=p['n'], condition='D2', component='intervention_probe',
                       steps=p['steps'], token_cap=p['token_cap']) for w in p['worlds'] for a in p['policies']]


def key(row):
    return row['world_id'], row['arm'], row['n'], row['condition'], row['campaign_component']


def independent_gate(records, config, complete):
    """Reimplement fixed thresholds; do not import the collection's gate functions."""
    cap = [r for r in records if r['campaign_component'] == 'capability']
    probes = [r for r in records if r['campaign_component'] == 'intervention_probe']
    spec, checks = config['actionability'], {}
    threshold = spec['admission']
    expected = {(w, c) for w in spec['worlds'] for c in spec['conditions']}
    observed = [(r['world_id'], r['condition']) for r in cap]
    checks['complete_known_records'] = (len(observed) == len(set(observed)) and set(observed) == expected
                                         and all(r['status'] == 'VALID_KNOWN' for r in cap))
    d0, d2 = [r for r in cap if r['condition'] == 'D0'], [r for r in cap if r['condition'] == 'D2']
    fractions = dict(d0_public_submission=sum(r.get('stop') == 'public_accepted_submission' for r in d0) / len(d0) if d0 else 0,
        d0_objective=sum(r['success'] is True for r in d0) / len(d0) if d0 else 0,
        d2_objective=sum(r['success'] is True for r in d2) / len(d2) if d2 else 0)
    stages, actions = Counter(), 0
    for record in cap:
        for turn in record.get('turns', []):
            if turn.get('model_response') is not None:
                actions += 1
                validation = turn.get('validation')
                if validation and validation['valid'] is False:
                    stages[validation['stage']] += 1
    interface = sum(stages[k] for k in ('transport_format', 'action_schema', 'undeclared_target')) / actions if actions else 1
    families = sorted({r['family'] for r in d2 if r['success'] is True})
    checks.update(d0_public_submission=fractions['d0_public_submission'] >= threshold['min_d0_public_submission_fraction'],
        d0_objective=fractions['d0_objective'] >= threshold['min_d0_objective_fraction'],
        interface_rejection=interface <= threshold['max_interface_rejection_fraction'],
        d2_objective=fractions['d2_objective'] >= threshold['min_d2_objective_fraction'],
        d2_families=len(families) >= threshold['min_d2_successful_families'])
    comparisons, p = [], spec['intervention_probes']
    probe_keys = [(r['world_id'], r['arm']) for r in probes]
    probes_complete = len(probe_keys) == len(set(probe_keys)) and set(probe_keys) == {(w, a) for w in p['worlds'] for a in p['policies']}
    for world in p['worlds']:
        pair = {r['arm']: r for r in probes if r['world_id'] == world}
        if set(pair) != {'blackboard', 'candidate'} or any(r['status'] != 'VALID_KNOWN' for r in pair.values()):
            comparisons.append(dict(world=world, valid=False, changed=None))
            continue
        def functional(record):
            return [(t['validation']['normalized_action'] if t.get('validation') else None,
                     t['materialized_receipts']) for t in record['turns']]
        baseline, candidate = pair['blackboard'], pair['candidate']
        comparisons.append(dict(world=world, valid=True, changed=functional(baseline) != functional(candidate),
            blackboard_tool_calls=baseline['metrics']['tool_calls'], candidate_tool_calls=candidate['metrics']['tool_calls'],
            inspection_dispatch_change=candidate['metrics']['inspection_dispatches'] - baseline['metrics']['inspection_dispatches']))
    checks['intervention_relevance'] = (probes_complete and all(p['valid'] for p in comparisons)
        and sum(p['changed'] is True or p.get('inspection_dispatch_change', 0) != 0 for p in comparisons) >= spec['intervention_probes']['minimum_changed_pairs'])
    expected_full = {(r['world'], r['arm'], r['n'], r['condition'], r['component']) for r in grid(config)}
    observed_full = [key(r) for r in records]
    full = (len(observed_full) == len(set(observed_full)) and set(observed_full) == expected_full
        and all(r['status'] == 'VALID_KNOWN' and r.get('complete_rollout') is True for r in records))
    checks['full_declared_grid'] = full
    result = dict(admitted=complete and all(checks.values()), checks=checks, fractions=fractions,
        interface_rejection_fraction=interface, stages=dict(stages), model_action_denominator=actions,
        d2_successful_families=families, intervention_comparisons=comparisons, counts_toward_verdict=False)
    if not actions:
        result['empty_denominator_gate_sentinels'] = dict(fractions=fractions, interface_rejection_fraction=interface)
        result['fractions'] = {k: None for k in fractions}
        result['interface_rejection_fraction'] = None
    result['measurement_status'] = 'UNMEASURED' if not actions else 'COMPLETE' if full else 'INCOMPLETE'
    return result


def task_literals(source):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_INPUTS' for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('task fixture literals missing')


def documents(world, inputs, version):
    x, family = inputs[world], world.split('/')[0]
    if family == 'interval_intersection':
        docs = {'lower_bounds': {'bounds': x['lower']}, 'upper_bounds': {'bounds': x['upper']}, 'preference': {'preferred': x['preferred']}}
    elif family == 'dependency_readiness':
        docs = {'dependency_graph': {'dependencies': x['edges']}, 'completion_state': {'completed': x['completed']}}
    elif family == 'inventory_reconciliation':
        docs = {'opening_balances': {'balances': x['opening']}, 'change_events': {'events': [dict(zip(('event_id', 'batch', 'item', 'delta'), r)) for r in x['changes']]}, 'approved_batches': {'batches': x['approved']}}
    else:
        docs = {'current_values': {'values': x['after' if version == 2 else 'before']}}
    return docs


def final_answer(world, inputs):
    x, family = inputs[world], world.split('/')[0]
    if family == 'interval_intersection':
        return {'selection': min(max(x['preferred'], max(x['lower'])), min(x['upper']))}
    if family == 'dependency_readiness':
        return {'ready': sorted(k for k, dependencies in x['edges'].items() if k not in x['completed'] and set(dependencies) <= set(x['completed']))}
    if family == 'version_correction':
        return {'value': x['after'][x['query']]}
    totals, seen = dict(x['opening']), set()
    for event, batch, item, delta in x['changes']:
        if batch in x['approved'] and event not in seen:
            totals[item] += delta
            seen.add(event)
    return {'totals': totals}


def audit_episode(audit, row, item, path, config, inputs):
    raw_path = path / 'episode.json'
    if not raw_path.exists():
        raw_path = path / 'INVALID_ABORT.json'
    if not raw_path.exists():
        audit.check(row['status'] == 'INVALID_ABORT' and row.get('metrics') is None and row.get('complete_rollout') is False,
                    'missing_raw_cannot_be_known_or_zero_cost', path)
        audit.note('attempted_episode_without_retained_raw_record', path)
        return None
    raw = audit.json(raw_path)
    v2_path = path / 'episode-v2.json'
    if not v2_path.exists():
        audit.check(row['status'] == 'INVALID_ABORT' and row.get('metrics') is None, 'missing_derivative_cannot_be_known', path)
        audit.note('attempted_episode_without_derivative', path)
        return None
    v2 = audit.json(v2_path)
    audit.check(row == {**v2, 'campaign_component': item['component']}, 'aggregate_matches_retained_episode', path)
    audit.check(v2['raw_record'] == {'file': raw_path.name, 'sha256': audit.hashes[raw_path.resolve()]}, 'raw_derivative_byte_binding', path)
    audit.check(raw.get('counts_toward_verdict') is False and v2.get('counts_toward_verdict') is False, 'pilot_exclusion', path)
    snapshot_path = path / 'session-snapshot.json'
    snapshot = audit.json(snapshot_path) if snapshot_path.exists() else raw.get('authoritative_snapshot')
    if snapshot is None:
        audit.check(v2['status'] == 'INVALID_ABORT' and v2.get('complete_rollout') is False, 'missing_snapshot_explicit_abort', path)
        audit.note('no_authoritative_snapshot_cost_remains_unresolved', path)
        return None
    if (path / 'session.sqlite').exists():
        recovered = session_snapshot(audit.database(path / 'session.sqlite'))
        audit.check(recovered == snapshot, 'snapshot_equals_isolated_sqlite_read', path)
    else:
        audit.check(False, 'retained_session_database_missing', path)
    calls = snapshot['calls']
    call_map = {c['id']: c for c in calls}
    dispatched = [c for c in calls if c['state'] in DISPATCHED]
    models = [c for c in dispatched if c['action'] == 'model.generate']
    tools = [c for c in dispatched if c['action'] == 'tool.evaluate']
    inspections = [c for c in tools if obj(c['request'])['tool_ref'] == 'inspect_source']
    metrics = dict(model_calls=len(models), tool_calls=len(tools), tokens=snapshot['actual_tokens'],
        unknown_tokens=snapshot['unknown_tokens'], unknown_calls=snapshot['unknown_calls'],
        input_tokens=sum(c['prompt'] for c in models if c['actual'] is not None),
        output_tokens=sum(c['actual'] - c['prompt'] for c in models if c['actual'] is not None))
    if row.get('metrics') is not None:
        for field, value in metrics.items():
            audit.check(row['metrics'].get(field) == value, 'raw_usage_' + field, path)
        # This counter increments after receipt, not at a failed tool dispatch.
        settled_inspections = sum(c['state'] == 'received' for c in inspections)
        audit.check(row['metrics']['inspection_dispatches'] == settled_inspections, 'inspection_counter_settled_boundary', path)
        if len(inspections) != settled_inspections:
            audit.note('inspection_counter_excludes_unsettled_attempts_actual_tool_calls_retain_them', path)
        audit.check(row['metrics']['monetary_cost'] is None, 'unmeasured_money_stays_unknown', path)
        audit.check(row['metrics']['actual_inference_concurrency'] == int(bool(models)), 'observed_dispatch_concurrency', path)
    audit.check(snapshot['run']['status'] in {'completed', 'cancelled', 'revoked'}, 'session_terminal', path)
    audit.check(len({c['id'] for c in calls}) == len(calls), 'unique_call_ids', path)
    for c in calls:
        audit.check(c['state'] in DISPATCHED | {'reserved', 'abandoned'}, 'declared_call_state', path)
        if c['state'] in {'reserved', 'dispatched'}:
            audit.check(c['actual'] is None, 'unsettled_usage_not_zero', path)
        if c['state'] in {'received', 'response_rejected', 'abandoned'}:
            audit.check(type(c['actual']) is int and c['actual'] >= 0, 'settled_usage_integer', path)
    turns = raw.get('turns', [])
    audit.check([t['turn'] for t in turns] == list(range(len(turns))) and len(turns) <= item['steps'], 'bounded_turn_prefix', path)
    required = set(documents(item['world'], inputs, 1))
    history = {h['ref']: h for h in raw.get('artifact_history', [])}
    artifacts = {r['ref']: r for r in snapshot['artifacts']}
    for ref, h in history.items():
        value = h['value']
        version = value['source_version']
        docs = documents(item['world'], inputs, version)
        docs['unrelated_notice'] = {'subject': 'archive_label', 'label': 'circular', 'task_evidence': False}
        base = {k: v for k, v in value.items() if k != 'receipt_identity'}
        audit.check(value['content'] == docs.get(value['source_id']) and value['receipt_identity'] == 'sha256:' + digest(base), 'source_fixture_and_content_digest', path)
        actual = artifacts.get(ref)
        audit.check(actual is not None and obj(actual['value']) == value and actual['publisher'] == h['publisher'], 'source_published_in_ledger', path)
        if actual:
            c = call_map[actual['call_id']]
            audit.check(c['state'] == 'received' and obj(c['response'])['artifact'] == value, 'source_settled_tool_lineage', path)
    preparations = raw.get('preparations', [])
    if item['condition'] == 'D2':
        audit.check(not preparations, 'd2_no_supplied_evidence', path)
    elif row['status'] == 'VALID_KNOWN':
        values = [history[p['artifact_ref']]['value'] for p in preparations]
        audit.check(all(p['kind'] == 'supplied_current_evidence' for p in preparations) and {v['source_id'] for v in values} == required
            and len(values) == len(required), 'd0_d1_complete_preparation', path)
        audit.check(all(v['source_version'] == (2 if item['world'].startswith('version_correction/') else 1) for v in values), 'd0_d1_final_version_preparation', path)
        audit.check(sum(c['id'].startswith('tool--1-') for c in inspections) == len(required), 'd0_d1_charged_preparation', path)
    seen_messages, exposures, repeats, responses = set(), 0, 0, 0
    for c in models:
        request = obj(c['request'])
        audit.check(c['maximum'] == 256 and c['reserved'] == c['prompt'] + 256 <= 2048, 'same_bounded_model_context', path)
        for message in request['messages']:
            identity = digest(message)
            exposures += 1
            repeats += identity in seen_messages
            seen_messages.add(identity)
        if c['state'] == 'received':
            response = obj(c['response'])
            audit.check(response['prompt_tokens'] == c['prompt'] and response['completion_tokens'] == len(response['generated_token_ids'])
                and c['actual'] == response['prompt_tokens'] + response['completion_tokens'], 'actual_tensor_usage_reconciles', path)
    for t in turns:
        audit.check(t['environment_step'] == max(2 if item['condition'] in {'D0', 'D1'} else 0, t['turn']), 'condition_environment_step', path)
        audit.check(t['prompt_sha256'] == digest(t['messages']), 'retained_prompt_digest', path)
        c = call_map.get('model-' + str(t['turn']))
        if c:
            audit.check(obj(c['request'])['messages'] == t['messages'] and c['prompt'] == t['preflight_prompt_tokens'], 'turn_model_request_binding', path)
            world_index = config['actionability']['worlds'].index(item['world'])
            audit.check(obj(c['request'])['seed'] == config['seed'] + 100 * world_index + t['turn'], 'paired_generation_seed', path)
        if t.get('model_response') is not None:
            responses += 1
            audit.check(c is not None and c['state'] == 'received' and obj(c['response']) == t['model_response'], 'turn_actual_response_binding', path)
        validation = t.get('validation')
        if validation:
            vc = call_map.get('validate-' + str(t['turn']))
            audit.check(vc is not None and vc['state'] == 'received' and obj(vc['response'])['artifact'] == validation, 'actual_public_validation_binding', path)
            if vc:
                materialized = obj(vc['request'])['arguments']['materialized']
                audit.check([v['receipt_identity'] for v in materialized] == t['materialized_receipts'], 'actual_validation_evidence_binding', path)
                available = {h['value']['receipt_identity'] for h in history.values() if h['turn'] < t['scheduler_turn']}
                audit.check(set(t['materialized_receipts']) <= available, 'materialized_evidence_previously_published', path)
                audit.check(obj(vc['request'])['arguments']['raw'] == t['model_response']['text'], 'actual_response_enters_validator', path)
            if item['condition'] == 'D0' and validation['valid']:
                audit.check(validation['normalized_action']['action'] == 'submit', 'd0_submit_only_public_tool', path)
    sent = sum(e['event_type'] == 'ext.session.message_sent' for e in snapshot['events'])
    if row.get('metrics') is not None:
        m = row['metrics']
        for k, value in dict(mailbox_messages_sent=sent, prompt_message_exposures=exposures,
                             repeated_prompt_message_exposures=repeats).items():
            audit.check(m[k] == value, 'communication_' + k, path)
        audit.check(m['message_duplicate_count'] is None if sent else m['message_duplicate_count'] == 0, 'unused_or_unknown_mailbox_count', path)
        audit.check(m['message_duplicate_rate'] is None, 'no_false_measured_mailbox_rate', path)
        if item['condition'] in {'D0', 'D1'} and row['status'] == 'VALID_KNOWN':
            audit.check(m['first_verified_progress']['phase'] == 'preparation', 'preparation_aware_first_progress', path)
    if row['status'] == 'VALID_KNOWN':
        control_operations = len(snapshot['events']) + len(turns) + sum(e['event_type'] == 'ext.session.published' for e in snapshot['events'])
        audit.check(row['metrics']['control_operations'] == control_operations, 'complete_record_control_operations', path)
        submission = raw.get('submission')
        answer = submission.get('answer') if isinstance(submission, dict) else None
        if isinstance(answer, dict) and isinstance(answer.get('ready'), list):
            answer = {**answer, 'ready': sorted(answer['ready'])}
        version = 2 if item['world'].startswith('version_correction/') else 1
        correct = isinstance(submission, dict) and submission.get('world_id') == item['world'] and submission.get('kind') == 'submission' and submission.get('task_version') == version and wire(answer) == wire(final_answer(item['world'], inputs))
        audit.check(row['success'] is correct, 'independent_fixture_objective', path)
        audit.check(row.get('complete_rollout') is True and snapshot['unknown_calls'] == 0 and row['stop'] in TERMINAL, 'known_complete_terminal_definition', path)
    elif row['status'] == 'INVALID_ABORT':
        audit.check(row['success'] is None and row.get('complete_rollout') is False, 'abort_is_not_failed_quality_or_complete', path)
    else:
        audit.check(row['status'] == 'VALID_UNRESOLVED' and row.get('complete_rollout') is False, 'unresolved_not_complete', path)
    return dict(identity=path.name, **metrics, model_intents=sum(c['action'] == 'model.generate' for c in calls),
        retained_control_operations=(row.get('metrics') or {}).get('control_operations'),
        call_units=(len(models) + len(tools) + row['metrics']['control_operations']) if row.get('metrics') else None,
        response_action_denominator=responses, model_dispatches_without_returned_response=len(models) - responses,
        observed_inspection_dispatches=len(inspections), preparations=len(preparations),
        status=row['status'], success=row['success'], condition=item['condition'], component=item['component'])


def run_audit(campaign, task_source):
    phase, audit = campaign / 'actionability', Audit(campaign)
    if not (phase / 'campaign-completion.json').is_file() or not (phase / 'admission.json').is_file():
        raise Pending('actionability collection has no terminal completion plus admission records')
    config = audit.json(campaign / 'frozen-config.json')
    audit.check(digest(config) == CONFIG_SHA, 'exact_preapproved_config_identity', campaign)
    expected = grid(config)
    freeze = audit.json(phase / 'freeze.json')
    audit.check(freeze['config_sha256'] == digest(config) and freeze['counts_toward_verdict'] is False, 'frozen_config_binding', phase)
    for path, expected_sha in freeze['sources'].items():
        audit.check(sha256(audit.read(path)).hexdigest() == expected_sha, 'source_unchanged_since_freeze', path)
    source = audit.read(task_source)
    frozen_task_sha = [h for p, h in freeze['sources'].items() if Path(p).name == task_source.name]
    audit.check(frozen_task_sha == [sha256(source).hexdigest()], 'independent_fixture_source_identity', task_source)
    inputs = task_literals(source)
    audit.check(audit.json(phase / 'expected-grid.json') == expected, 'full_declared_grid_unchanged', phase)
    records, completion = audit.json(phase / 'records.json'), audit.json(phase / 'campaign-completion.json')
    audit.check(completion['records_sha256'] == digest(records), 'completion_records_digest', phase)
    audit.check(completion['declared'] == len(expected) == 28 and completion['executed'] == len(records) <= 28, 'full_grid_denominators', phase)
    audit.check(len({key(r) for r in records}) == len(records), 'unique_episode_cells', phase)
    audit.check([key(r) for r in records] == [(r['world'], r['arm'], r['n'], r['condition'], r['component']) for r in expected[:len(records)]], 'executed_grid_prefix', phase)
    unstarted = [{**r, 'outcome': None, 'cost': None, 'reason': 'collection_stopped_after_invalid_or_unresolved_work'} for r in expected[len(records):]]
    audit.check(completion['unstarted'] == unstarted, 'explicit_unstarted_null_outcome_cost', phase)
    complete = completion['status'] == 'COMPLETE'
    audit.check(complete == (completion['failure'] is None and len(records) == len(expected)), 'completion_terminal_accounting', phase)
    if (phase / 'completed.jsonl').exists():
        journal = [obj(line) for line in audit.read(phase / 'completed.jsonl').splitlines() if line]
        audit.check(journal == records[:len(journal)] and (len(journal) == len(records) or not complete), 'append_journal_prefix', phase)
    summaries = []
    for index, row in enumerate(records):
        item = expected[index]
        identity = f"actionability-{index:03d}-{item['arm']}-n{item['n']}-{item['condition']}"
        summary = audit_episode(audit, row, item, phase / identity, config, inputs)
        if summary:
            summaries.append(summary)
    expected_dirs = {f"actionability-{i:03d}-{r['arm']}-n{r['n']}-{r['condition']}" for i, r in enumerate(expected[:len(records)])}
    audit.check({p.name for p in phase.glob('actionability-*') if p.is_dir()} <= expected_dirs, 'no_unreported_episode_directories', phase)
    audit.check(audit.json(phase / 'fork-records.json') == [], 'no_forks_in_capability_phase', phase)
    accounting = audit.json(phase / 'accounting.json')
    cdb = audit.database(campaign / 'campaign.sqlite')
    campaign_row, rows = cdb['campaign'][0], cdb['allotments']
    audit.check(campaign_row['config_digest'] == digest(config) and campaign_row['token_cap'] == 500000 and campaign_row['dispatch_cap'] == 999, 'campaign_limits_identity', campaign)
    retained = accounting.get('allotments', [])
    audit.check(rows[:len(retained)] == retained, 'retained_allotments_equal_database_prefix', phase)
    if len(rows) > len(retained):
        audit.note('campaign_contains_later_phase_allotments_excluded_from_actionability_snapshot', campaign)
    for allocation in retained:
        session_path = Path(allocation['path'])
        audit.check(session_path.resolve().is_relative_to(phase.resolve()), 'allotment_path_inside_phase', phase)
        if not session_path.is_file():
            audit.check(allocation['state'] == 'allocated' and allocation['known_tokens'] is None and allocation['held_tokens'] == allocation['tokens'], 'missing_child_retains_full_reservation', phase)
            audit.note('missing_child_unsettled_cost', session_path)
            continue
        snapshot = session_snapshot(audit.database(session_path))
        limits, calls = obj(snapshot['run']['limits']), snapshot['calls']
        intents = {c['id'] for c in calls if c['action'] == 'model.generate'}
        slots = {s['call_id'] for s in cdb['model_slots'] if s['allocation_id'] == allocation['id']}
        audit.check(intents <= slots and len(slots) <= allocation['model_cap'], 'unique_reserved_model_intents', session_path)
        if slots != intents:
            audit.note('claimed_intent_without_session_call_observed', session_path)
        audit.check(limits['token_cap'] == allocation['tokens'] and limits['max_calls'] == allocation['calls'], 'child_limits_equal_allotment', session_path)
        if allocation['state'] == 'terminal':
            audit.check(allocation['snapshot_digest'] == digest(snapshot), 'allotment_terminal_snapshot_digest', session_path)
            audit.check(allocation['known_tokens'] == snapshot['actual_tokens'] and allocation['unknown_tokens'] == snapshot['unknown_tokens'], 'allotment_token_receipts', session_path)
            audit.check(allocation['held_tokens'] == snapshot['actual_tokens'] + snapshot['unknown_tokens'] + snapshot['reserved_tokens']
                and allocation['held_calls'] == len(intents), 'allotment_conservative_holds', session_path)
        else:
            audit.note('unsettled_or_violating_allotment_not_released', session_path)
    for field, actual in dict(held_token_upper_bound=sum(r['held_tokens'] for r in retained), held_call_slots=sum(r['held_calls'] for r in retained),
        known_tokens=sum(r['known_tokens'] or 0 for r in retained), known_tokens_complete=all(r['known_tokens'] is not None for r in retained)).items():
        audit.check(accounting.get(field) == actual, 'phase_accounting_' + field, phase)
    audit.check(accounting['held_token_upper_bound'] <= 500000 and accounting['held_call_slots'] <= 999, 'phase_budget_caps', phase)
    predecessor = audit.json(campaign / 'predecessor-accounting.json')
    audit.check(predecessor['token_upper_bound'] == predecessor['known_tokens'] == predecessor['observed_model_dispatches'] == 0
        and predecessor['retained_intent_slots'] == 1 and predecessor['settled_preparation_tools'] == 3, 'historical_abort_liability_retained', campaign)
    combined = audit.json(phase / 'combined-accounting.json')
    audit.check(combined['current'] == accounting and combined['predecessor'] == predecessor
        and combined['held_token_upper_bound'] == accounting['held_token_upper_bound']
        and combined['held_intent_slots'] == accounting['held_call_slots'] + 1
        and combined['total_token_cap'] == 500000 and combined['total_intent_cap'] == 1000, 'combined_historical_and_current_budget', phase)
    recomputed = independent_gate(records, config, complete)
    audit.check(audit.json(phase / 'admission.json') == recomputed, 'independent_gate_equals_saved_admission', phase)
    audit.stable()
    sums = {field: sum(r[field] for r in summaries) for field in ('model_calls', 'tool_calls', 'tokens', 'unknown_tokens', 'unknown_calls', 'model_intents', 'response_action_denominator', 'model_dispatches_without_returned_response')}
    return dict(audit_profile='coordination_repair_actionability_independent_audit_v1',
        status='PASS' if not audit.findings else 'FINDINGS', campaign=str(campaign), campaign_status=completion['status'],
        config_sha256=digest(config), checks_evaluated=audit.check_count, findings=audit.findings, observations=audit.notes,
        declared_cells=len(expected), retained_cells=len(records), audited_session_cells=len(summaries), unstarted_cells=len(unstarted),
        status_counts=dict(Counter(r['status'] for r in records)), condition_counts=dict(Counter(r['condition'] for r in records)),
        audited_known_portion_totals=sums, totals_cover_all_retained_cells=len(summaries) == len(records),
        episode_accounting=summaries, independent_admission=recomputed, phase_accounting=accounting,
        combined_accounting=combined, input_sha256={str(p): h for p, h in sorted(audit.hashes.items())},
        counts_toward_verdict=False, limitations=[
            'This is a post-run read-only accounting and fixed-gate audit, not permission to dispatch or evidence of efficacy.',
            'Tasks are eight fixed development worlds; independent arithmetic uses AST-read frozen input literals, not a population sample.',
            'Public validation is bound to actual settled tool responses; this helper does not reimplement every parser or Governance proof.',
            'No model retokenization, CUDA replay, elapsed-time calibration, paid-cost estimation, or provider request is performed.',
            'Capability admission excludes intervention probes from the interface denominator; all probes remain in accounting.',
            'Inference-dispatch concurrency is not GPU utilization; exact prompt repetitions are not mailbox deliveries.',
            'Later collaboration and nested forks require a separate audit; no full-goal-complete claim.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, default=DEFAULT_CAMPAIGN)
    parser.add_argument('--task-source', type=Path, default=CORE / 'src/pheroos_bench/coordination_repair_v1_tasks.py')
    parser.add_argument('--output', type=Path, required=True, help='New audit JSON outside campaign; never overwritten')
    args = parser.parse_args()
    campaign, output = args.campaign.resolve(), args.output.resolve()
    if output.is_relative_to(campaign) or output.exists():
        parser.error('output must be a new file outside the campaign directory')
    try:
        report = run_audit(campaign, args.task_source.resolve())
    except Pending as error:
        print(json.dumps({'status': 'PENDING', 'reason': str(error), 'campaign_data_written': False}))
        return 4
    except (OSError, ValueError, KeyError, TypeError, IndexError, sqlite3.Error) as error:
        print(json.dumps({'status': 'AUDIT_INPUT_ERROR', 'exception_type': type(error).__name__, 'campaign_data_written': False}))
        return 2
    report['audit_helper_sha256'] = sha256(Path(__file__).read_bytes()).hexdigest()
    with output.open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'output': str(output), 'findings': len(report['findings']),
                      'admitted': report['independent_admission']['admitted'], 'counts_toward_verdict': False}))
    return 0 if report['status'] == 'PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
