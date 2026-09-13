from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pheroos_bench import r3_framed_pilot as pilot


PATCH = {"action": "submit", "candidate": {"code_lines": [
    "def clamp(value, lower, upper):", "    return max(lower, min(value, upper))"]}}


class Backend:
    def __init__(self, text=None, fault=None):
        self.text = text if text is not None else "```json\n" + json.dumps(PATCH) + "\n```"
        self.fault = fault
        self.requests, self.ledgers = [], {}

    def request(self, request):
        self.requests.append(deepcopy(request))
        if request['op'] == 'tokenize':
            return {'prompt_tokens': 10}
        if request['op'] == 'publish':
            if self.fault == 'publication':
                raise PermissionError('publication denied')
            return {'authority': 'fake test only'}
        ledger = self.ledgers.setdefault(request['ledger_path'], dict(
            config={key: request[key] for key in ('token_cap', 'max_calls')}, calls=[],
            actual_tokens=0, reserved_tokens=0, unknown_tokens=0, call_count=0))
        if request['op'] == 'ledger':
            return deepcopy(ledger)
        payload = {key: deepcopy(request[key]) for key in
                   ('task_id', 'version', 'call_id', 'messages', 'max_new_tokens', 'seed')}
        if self.fault == 'timeout':
            ledger.update(unknown_tokens=266, call_count=1,
                          calls=[dict(id=request['call_id'], state='dispatched', request=payload,
                                      response=None, reserved=266, actual=None)])
            raise TimeoutError('cancelled or timed out after dispatch')
        raw = dict(text=self.text, prompt_tokens=10, completion_tokens=7,
                   peak_cuda_bytes=1, elapsed_ns=1)
        ledger['actual_tokens'] += 17
        ledger['call_count'] += 1
        ledger['calls'].append(dict(id=request['call_id'], state='received', request=payload,
                                   response=deepcopy(raw), reserved=266, actual=17))
        reply = dict(raw, authority='fake test only', ledger=deepcopy(ledger))
        if self.fault == 'receipt':
            reply['ledger']['calls'][-1]['response']['text'] = 'different receipt'
        if self.fault and self.fault.startswith('request_'):
            key = self.fault.removeprefix('request_')
            reply['ledger']['calls'][-1]['request'][key] = {
                'task_id': 'foreign-task', 'version': 2, 'seed': 999, 'call_id': 'foreign-call',
                'messages': [{'role': 'user', 'content': 'foreign prompt'}],
                'max_new_tokens': 255, 'scope_ref': 'undeclared-extra-field'}[key]
        return reply


@pytest.mark.parametrize('text,admitted,kind', [
    ('{"action":"inspect","target":"above_upper"}', True, 'bare_json'),
    (' \n```json\n{"action":"inspect","target":"above_upper"}\n```\n', True, 'sole_json_fence'),
    ('```json\r\n{}\r\n```', False, 'rejected'),
    ('```json \n{}\n```', False, 'rejected'),
    ('```JSON\n{}\n```', False, 'rejected'),
    ('```python\n{}\n```', False, 'rejected'),
    ('```\n{}\n```', False, 'rejected'),
    ('Here:\n```json\n{}\n```', False, 'rejected'),
    ('```json\n{}\n```\nExplanation', False, 'rejected'),
    ('```json\n{}\n```\n```json\n{}\n```', False, 'rejected'),
    ('```json\n[]\n```', False, 'rejected'),
    ('```json\n{"x":1,"x":2}\n```', False, 'rejected'),
    ('{"x":1,"x":2}', False, 'rejected'),
    ('```json\n{"x":NaN}\n```', False, 'rejected'),
    ('{} {}', False, 'rejected'),
    ('not JSON', False, 'rejected'),
])
def test_exact_common_framing_contract(text, admitted, kind):
    output, diagnostic = pilot.frame(text)
    assert diagnostic['admitted'] is admitted
    assert diagnostic['kind'] == kind
    if not admitted:
        assert output == text


def test_framed_actions_run_same_tasks_and_receipts_bind_raw_text(tmp_path):
    backend = Backend()
    row = pilot.episode(backend, pilot.configuration(), 'code_repair/clamp', 'blackboard', 0, tmp_path)
    assert row['outcome'] == 'success'
    assert row['method_version'] == pilot.METHOD and row['counts_toward_verdict'] is False
    assert row['main_parser'] == {'received': 6, 'admitted': 6, 'public_valid_actions': 6}
    assert row['probe_parser'] == {'received': 2, 'admitted': 2, 'public_valid_actions': 2}
    assert sum(row['main_usage'].values()) == 102
    assert sum(row['probe_usage'].values()) == 34
    assert row['processing_operations'] == 40
    assert row['processing_bytes'] > 0
    traces = [json.loads(line) for line in (tmp_path / 'trace.jsonl').read_text().splitlines()]
    probes = [json.loads(line) for line in (tmp_path / 'probes.jsonl').read_text().splitlines()]
    for trace in traces + probes:
        response = trace['response']
        assert response['raw_text'] == backend.text
        assert json.loads(response['text']) == PATCH
        raw = pilot._raw_response(response)
        assert response['raw_reply_sha256'] == pilot.digest(raw)
        stored = next(call for call in raw['ledger']['calls'] if call['id'] == trace['request']['call_id'])
        assert stored['response']['text'] == response['raw_text']
        cost = response['processing_cost']
        assert cost['total_bytes'] == sum(v for k, v in cost.items() if k.endswith('_bytes') and k != 'total_bytes')
        assert cost['total_operations'] == sum(v for k, v in cost.items() if k.endswith('_operations') and k != 'total_operations')
    assert row['serialized_trace_bytes'] == sum((tmp_path / name).stat().st_size for name in ('trace.jsonl', 'probes.jsonl'))
    assert row['transport_bytes'] == sum(x['request_bytes'] + x['response_bytes'] for x in row['transport_accounting'])
    assert all('probe' not in identity for trace in traces for identity in trace['consumed_ids'])
    assert row['eligible_probes'] == 2 and row['valid_action_changes'] == 0


@pytest.mark.parametrize('arm', pilot.ARMS)
def test_every_arm_uses_identical_framing_and_total_call_cap(tmp_path, arm):
    row = pilot.episode(Backend(), pilot.configuration(), 'code_repair/clamp', arm, 0, tmp_path)
    assert row['main_parser']['admitted'] == row['main_calls'] == 6
    assert row['probe_parser']['admitted'] == row['probe_calls'] == 2
    assert sum(row['main_usage'].values()) + sum(row['probe_usage'].values()) == 136


@pytest.mark.parametrize('candidate', [
    {'action': 'inspect', 'target': 'index_entry'},
    {'action': 'submit', 'candidate': {'code_lines': ['def clamp(value, lower, upper):\n', '    return value']}},
    {'action': 'submit', 'candidate': {'code_lines': ['def clamp(value, lower, upper):', '    return 999']}},
])
def test_json_admission_does_not_repair_semantically_invalid_tasks(tmp_path, candidate):
    backend = Backend('```json\n' + json.dumps(candidate) + '\n```')
    row = pilot.episode(backend, pilot.configuration(), 'code_repair/clamp', 'single', 0, tmp_path)
    assert row['outcome'] == 'failed'
    assert row['main_parser']['admitted'] == 6
    assert row['main_parser']['public_valid_actions'] == 0
    assert not any(r['op'] == 'publish' for r in backend.requests)
    assert sum(row['main_usage'].values()) == 102


@pytest.mark.parametrize('fault', ['publication', 'receipt', 'request_task_id', 'request_version',
                                 'request_seed', 'request_call_id', 'request_messages',
                                 'request_max_new_tokens', 'request_scope_ref'])
def test_partial_received_cost_survives_later_failure(tmp_path, fault):
    backend = Backend(fault=fault)
    row = pilot.episode(backend, pilot.configuration(), 'code_repair/clamp', 'single', 0, tmp_path)
    assert row['outcome'] == 'INVALID_ABORT'
    assert sum(row['main_usage'].values()) == row['main_ledger']['actual_tokens'] == 17
    assert row['probe_calls'] == 0
    trace = json.loads((tmp_path / 'trace.jsonl').read_text())
    assert trace['response']['raw_text'] == backend.text
    if fault != 'publication':
        assert not any(request['op'] == 'publish' for request in backend.requests)


def test_dispatched_timeout_keeps_unknown_reservation(tmp_path):
    row = pilot.episode(Backend(fault='timeout'), pilot.configuration(), 'code_repair/clamp', 'single', 0, tmp_path)
    assert row['outcome'] == 'INVALID_ABORT'
    assert row['main_ledger']['unknown_tokens'] == 266
    assert sum(row['main_usage'].values()) == 0
    assert row['main_calls'] == 1
    assert row['main_parser']['received'] == 0


def test_configuration_and_output_checks_happen_before_model_start(tmp_path, monkeypatch):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps(pilot.configuration()))
    output = tmp_path / 'existing'
    output.mkdir()
    def forbidden(*args, **kwargs):
        raise AssertionError('model/input loader must not run')
    monkeypatch.setattr(pilot, 'verify_inputs', forbidden)
    with pytest.raises(ValueError, match='exclusive'):
        pilot.main(['--config', str(config), '--output', str(output), '--runtime-python', 'python',
                    '--runtime-source', str(tmp_path), '--model-path', str(tmp_path)])
    changed = pilot.configuration()
    changed['steps'] = 6.0
    with pytest.raises(ValueError, match='configuration'):
        pilot.episode(Backend(), changed, 'code_repair/clamp', 'single', 0, tmp_path)


def test_full_paired_grid_and_terminal_accounting_are_required(tmp_path):
    with pytest.raises(ValueError, match='missing or duplicated'):
        pilot.summarize([])
    rows = []
    for index, (world, arm) in enumerate((w, a) for w in pilot.tasks.world_ids() for a in pilot.ARMS):
        output = tmp_path / str(index)
        output.mkdir()
        rows.append(pilot.episode(Backend(), pilot.configuration(), world, arm, index, output))
    report = pilot.summarize(rows)
    assert report['status'] == 'PILOT_COMPLETE'
    assert report['counts_toward_verdict'] is False
    assert sum(arm['main_tokens'] + arm['probe_tokens'] for arm in report['arms'].values()) == 2720
    broken = deepcopy(rows)
    broken[-1]['main_ledger']['unknown_tokens'] = 1
    with pytest.raises(ValueError, match='unresolved'):
        pilot.summarize(broken)
    with pytest.raises(ValueError, match='missing or duplicated'):
        pilot.summarize(rows[:-1] + [rows[0]])


def test_declared_configuration_file_matches_code():
    path = Path(__file__).parents[1] / 'r3-framed-pilot-v3.json'
    assert json.loads(path.read_text()) == pilot.configuration()


def test_input_verification_checks_installed_source_and_model_hashes(tmp_path, monkeypatch):
    runtime = tmp_path / 'runtime'
    package = runtime / 'src/pheroos_runtime'
    package.mkdir(parents=True)
    module = package / '__init__.py'
    module.write_text('')
    installed = {'packages': {}, 'files': {'pheroos-runtime': {
        'pheroos_runtime/__init__.py': {'path': str(module), 'sha256': pilot._file_sha(module)}}}}
    monkeypatch.setattr(pilot.subprocess, 'run', lambda *a, **k: SimpleNamespace(stdout=json.dumps(installed)))
    model = tmp_path / 'model'
    model.mkdir()
    weights = model / 'test-weights'
    weights.write_bytes(b'finite test fixture')
    manifest = dict(pilot.MODEL, sha256={weights.name: pilot._file_sha(weights)})
    (model / 'manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(pilot, 'MODEL_MANIFEST_SHA256', pilot.digest(manifest))
    assert pilot.verify_inputs('unused', runtime, model) == (installed, manifest)
    weights.write_bytes(b'changed')
    with pytest.raises(ValueError, match='digest'):
        pilot.verify_inputs('unused', runtime, model)
    module.write_text('changed source')
    with pytest.raises(ValueError, match='differs'):
        pilot.verify_inputs('unused', runtime, model)


@pytest.fixture(scope='module')
def measured_grid(tmp_path_factory):
    output = tmp_path_factory.mktemp('framed_summary_receipts')
    return [pilot.episode(Backend(), pilot.configuration(), world, arm, index, output)
            for index, (world, arm) in enumerate((world, arm)
                for world in pilot.tasks.world_ids() for arm in pilot.ARMS)]


COUNTER_PATHS = [
    ('main_calls',), ('probe_calls',), ('processing_operations',), ('processing_bytes',),
    ('transport_bytes',), ('serialized_trace_bytes',), ('tool_receipt_bytes',),
    ('elapsed_ns',), ('peak_cuda_bytes',), ('eligible_probes',), ('valid_action_changes',),
    ('main_usage', 'input_tokens'), ('main_usage', 'output_tokens'),
    ('probe_usage', 'input_tokens'), ('probe_usage', 'output_tokens'),
    ('main_parser', 'received'), ('main_parser', 'admitted'), ('main_parser', 'public_valid_actions'),
    ('probe_parser', 'received'), ('probe_parser', 'admitted'), ('probe_parser', 'public_valid_actions'),
    ('main_ledger', 'call_count'), ('main_ledger', 'actual_tokens'),
    ('main_ledger', 'reserved_tokens'), ('main_ledger', 'unknown_tokens'),
    ('probe_ledger', 'call_count'), ('probe_ledger', 'actual_tokens'),
    ('probe_ledger', 'reserved_tokens'), ('probe_ledger', 'unknown_tokens'),
    ('main_ledger', 'calls', 0, 'actual'), ('main_ledger', 'calls', 0, 'reserved'),
    ('probe_ledger', 'calls', 0, 'actual'), ('probe_ledger', 'calls', 0, 'reserved'),
    ('main_ledger', 'calls', 0, 'response', 'prompt_tokens'),
    ('probe_ledger', 'calls', 0, 'response', 'completion_tokens'),
    ('transport_accounting', 0, 'request_bytes'), ('transport_accounting', 0, 'response_bytes'),
    ('curve', 0, 'calls'), ('curve', 0, 'tokens'), ('curve', 0, 'elapsed_ns'),
]


@pytest.mark.parametrize('path', COUNTER_PATHS)
@pytest.mark.parametrize('value', [True, -1, 0.5])
def test_summary_refuses_noninteger_or_negative_accounting(measured_grid, path, value):
    rows = deepcopy(measured_grid)
    target = rows[0]
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    with pytest.raises(ValueError, match='exact nonnegative integers'):
        pilot.summarize(rows)


@pytest.mark.parametrize('corruption', [
    'phase', 'usage_total', 'usage_components', 'ledger_total', 'call_count', 'missing_call',
    'duplicate_call', 'call_actual', 'self_consistent_false_usage', 'missing_receipt',
    'unsettled_call', 'reservation', 'transport_total', 'prefix_tokens', 'parser_counts',
    'request_task', 'request_version', 'request_seed', 'request_call_id',
    'wrong_call_id', 'request_cap', 'extra_request_field', 'aliased_episode_id', 'wrong_probe_id',
])
def test_summary_reconciles_completed_usage_against_independent_receipts(measured_grid, corruption):
    rows = deepcopy(measured_grid)
    row = rows[0]
    ledger = row['main_ledger']
    if corruption == 'phase':
        row['phase'] = 'confirmatory'
    elif corruption == 'usage_total':
        row['main_usage']['input_tokens'] += 1
    elif corruption == 'usage_components':
        row['main_usage']['input_tokens'] += 1
        row['main_usage']['output_tokens'] -= 1
    elif corruption == 'ledger_total':
        ledger['actual_tokens'] += 1
    elif corruption == 'call_count':
        ledger['call_count'] += 1
    elif corruption == 'missing_call':
        ledger['calls'].pop()
    elif corruption == 'duplicate_call':
        ledger['calls'][-1] = deepcopy(ledger['calls'][0])
    elif corruption == 'call_actual':
        ledger['calls'][0]['actual'] += 1
    elif corruption == 'self_consistent_false_usage':
        # Matching mutated totals cannot override the independently retained
        # received response's actual prompt/completion counts.
        ledger['calls'][0]['actual'] += 1
        ledger['actual_tokens'] += 1
        row['main_usage']['input_tokens'] += 1
    elif corruption == 'missing_receipt':
        ledger['calls'][0]['response'] = None
    elif corruption == 'unsettled_call':
        ledger['calls'][0].update(state='dispatched', actual=None, response=None)
        ledger['actual_tokens'] -= 17
        ledger['unknown_tokens'] = 266
    elif corruption == 'reservation':
        ledger['calls'][0]['reserved'] -= 1
    elif corruption == 'transport_total':
        row['transport_bytes'] += 1
    elif corruption == 'prefix_tokens':
        row['curve'][0]['tokens'] += 1
    elif corruption == 'parser_counts':
        row['main_parser']['public_valid_actions'] = 7
    elif corruption == 'request_task':
        ledger['calls'][0]['request']['task_id'] = 'code_repair/chunk_count'
    elif corruption == 'request_version':
        ledger['calls'][0]['request']['version'] = 2
    elif corruption == 'request_seed':
        ledger['calls'][0]['request']['seed'] += 1
    elif corruption == 'request_call_id':
        ledger['calls'][0]['request']['call_id'] = 'other-call'
    elif corruption == 'wrong_call_id':
        ledger['calls'][0]['id'] = ledger['calls'][0]['request']['call_id'] = 'other-call'
    elif corruption == 'request_cap':
        ledger['calls'][0]['request']['max_new_tokens'] -= 1
        ledger['calls'][0]['reserved'] -= 1
    elif corruption == 'extra_request_field':
        ledger['calls'][0]['request']['scope_ref'] = 'not-in-runtime-payload'
    elif corruption == 'aliased_episode_id':
        row['episode_id'] = rows[1]['episode_id']
    elif corruption == 'wrong_probe_id':
        probe = row['probe_ledger']['calls'][0]
        probe['id'] = probe['request']['call_id'] = row['episode_id'] + ':probe:3'
    with pytest.raises(ValueError):
        pilot.summarize(rows)


@pytest.mark.parametrize('fault', ['timeout', 'publication'])
def test_partial_invalid_rows_keep_explicit_abort_and_accounting(measured_grid, tmp_path, fault):
    rows = deepcopy(measured_grid)
    row = pilot.episode(Backend(fault=fault), pilot.configuration(), 'code_repair/clamp', 'single', 0, tmp_path)
    rows[0] = row
    original = deepcopy(rows)
    report = pilot.summarize(rows)
    assert report['status'] == 'INVALID_ABORT'
    assert report['counts_toward_verdict'] is False
    assert report['arms']['single']['invalid'] == 1
    accounting = report['invalid_episode_accounting'][0]
    assert accounting['main_usage'] == row['main_usage']
    assert accounting['main_ledger'] == row['main_ledger']
    assert accounting['probe_ledger'] is None
    assert accounting['main_ledger']['unknown_tokens'] == (266 if fault == 'timeout' else 0)
    assert accounting['main_ledger']['actual_tokens'] == (0 if fault == 'timeout' else 17)
    assert rows == original
