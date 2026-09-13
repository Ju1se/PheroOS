"""Compare G1 semantic acceptance with the published macOS report."""
from hashlib import sha256
import json
from pathlib import Path

root = Path(__file__).resolve().parent
original_path = root.parents[1] / 'results/g1-install-acceptance.json'
fresh_path = root / 'g1-install-acceptance.json'
original = json.loads(original_path.read_text())
fresh = json.loads(fresh_path.read_text())
fields = ('actual_units', 'reserved_units', 'unknown_units', 'remaining_units',
          'tasks_done', 'final_value', 'worker_exitcodes')
comparisons = []
assert original['core_commit'] == fresh['core_commit']
for old, new in zip(original['distributions'], fresh['distributions'], strict=True):
    assert old['artifact'] == new['artifact']
    before = {field: old['cli'][field] for field in fields}
    after = {field: new['cli'][field] for field in fields}
    before['run_status'] = old['cli']['run']['status']
    after['run_status'] = new['cli']['run']['status']
    before['budget'] = old['cli']['run']['budget']
    after['budget'] = new['cli']['run']['budget']
    assert before == after
    assert new['source_independent']
    assert '43 passed' in new['test_output']
    comparisons.append({'artifact': new['artifact'], 'semantic_result_equal': True,
                        'macos_semantics': before, 'wsl2_semantics': after,
                        'macos_test_output': old['test_output'], 'wsl2_test_output': new['test_output']})
snapshot = json.loads((root / 'demo-snapshot.json').read_text())
assert snapshot['run']['status'] == 'completed'
assert (snapshot['actual_units'], snapshot['reserved_units'], snapshot['unknown_units']) == (26, 0, 0)
assert len(snapshot['tasks']) == 13
assert all(task['status'] == 'done' for task in snapshot['tasks'])
assert next(item['value'] for item in snapshot['artifacts'] if item['task_id'] == 'total') == 204
for artifact in json.loads((root / 'artifact-hashes.json').read_text()):
    assert sha256((root / artifact['artifact']).read_bytes()).hexdigest() == artifact['sha256']
for item in fresh['distributions']:
    assert sha256((root / 'artifacts' / item['artifact']).read_bytes()).hexdigest() == item['sha256']
report = {'status': 'G1_TESTED_SEMANTICS_MATCH_MACOS',
          'reference_report_sha256': sha256(original_path.read_bytes()).hexdigest(),
          'replication_report_sha256': sha256(fresh_path.read_bytes()).hexdigest(),
          'runtime_commit': 'b3c0d4977c466c02a200d4fe63857682de53ddfd',
          'core_commit': fresh['core_commit'],
          'python_patch': '3.14.7',
          'distributions': comparisons,
          'independent_cli_snapshot_valid': True,
          'artifact_hashes_valid': True,
          'scope': 'Fixed mock DAG, tested policies and worker counts, tested process-death boundaries; no universal hardware-independence claim.',
          'excluded_from_equality': ['wall time', 'timestamps', 'process identifiers', 'independent event ordering', 'distribution and snapshot hashes'],
          'historical_environment_limit': 'Published macOS evidence says Python 3.14; exact patch and full historical development dependency lock are unavailable.'}
with (root / 'g1-semantic-comparison.json').open('x') as handle:
    json.dump(report, handle, indent=2)
    handle.write('\n')
print(json.dumps(report, indent=2))
