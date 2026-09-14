"""Read-only observation of the exact two reviewed PR heads; never start CI."""
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

out = Path('/tmp/pheroos-model-interface-live-v1')
gh = '/tmp/pheroos-pr-tools/gh'
env = {**os.environ, 'GH_CONFIG_DIR': '/tmp/pheroos-pr-tools/gh-config', 'GH_PROMPT_DISABLED': '1'}
checks = {}
for key, repo, number, expected in (
    ('core', 'Ju1se/PheroOS', '37', '4ea5208ae5d7d6cd8c847f89e51f44a914143c8d'),
    ('runtime', 'Ju1se/pheroos-runtime', '3', '2222d59bb05785528e4301dc14d164d538408ac6'),
):
    result = subprocess.run([gh, 'pr', 'view', number, '--repo', repo, '--json',
        'number,url,state,isDraft,headRefOid,headRefName,statusCheckRollup'], env=env,
        capture_output=True, text=True, timeout=60, check=True)
    value = json.loads(result.stdout)
    assert value['headRefOid'] == expected and value['state'] == 'OPEN' and value['isDraft'] is True
    checks[key] = value
runtime_workflows = json.loads(subprocess.run([gh, 'api', 'repos/Ju1se/pheroos-runtime/actions/workflows'],
    env=env, capture_output=True, text=True, timeout=60, check=True).stdout)
rows = checks['core']['statusCheckRollup']
names = {r.get('name', r.get('context')): r for r in rows}
required = {'quality-gate', 'release-candidate-dry-run', 'installed-session-consumer (dev2)',
            'installed-session-consumer (dev3)', 'model-interface-consumer'}
failures = [r for r in rows + checks['runtime']['statusCheckRollup']
    if (r.get('conclusion') or r.get('state')) in ('FAILURE', 'ERROR', 'CANCELLED', 'TIMED_OUT', 'ACTION_REQUIRED', 'STARTUP_FAILURE')]
complete = bool(rows) and all(r.get('status') == 'COMPLETED' for r in rows)
allowed = all(r.get('conclusion') == 'SUCCESS' or
    (r.get('name') == 'provenance' and r.get('conclusion') == 'SKIPPED') for r in rows)
runtime_ci = checks['runtime']['statusCheckRollup']
runtime_ok = (all(r.get('status') == 'COMPLETED' and r.get('conclusion') == 'SUCCESS' for r in runtime_ci)
    if runtime_ci else runtime_workflows['total_count'] == 0)
ready = complete and allowed and not failures and runtime_ok and required.issubset(names)
record = dict(profile='model_interface_exact_head_ci_v1', observed_utc=datetime.now(timezone.utc).isoformat(),
    ready=ready, prs=checks, required_core_checks=sorted(required), failures=failures,
    counts=dict(Counter(r.get('conclusion') or r.get('status') for r in rows)),
    allowed_skip={'provenance': 'tests.yml runs attestations only for a push to refs/heads/main in Ju1se/PheroOS; the PR event has explicit skipped provenance in quality-gate'},
    runtime_workflows=runtime_workflows,
    runtime_coverage='No standalone workflow configured; actual accepted runtime dev4 wheel is hash-pinned and exercised in the exact-head model-interface-consumer job and retained wheel/sdist acceptance.',
    counts_toward_verdict=False)
with (out / 'ci-observations.jsonl').open('a') as file:
    file.write(json.dumps(record) + '\n')
(out / 'ci-latest.json').write_text(json.dumps(record, indent=2) + '\n')
if ready:
    path = out / 'ci-before-dispatch.json'
    if not path.exists():
        path.write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(dict(ready=ready, counts=record['counts'], failures=len(failures),
    runtime_workflows=runtime_workflows['total_count'])))
