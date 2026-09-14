"""Freeze bounded authorization and verify accepted installations; no inference."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import zipfile

repo = Path('/tmp/pheroos-interface-core')
runtime = Path('/tmp/pheroos-interface-runtime')
out = Path('/tmp/pheroos-model-interface-live-v1')
site = Path('/tmp/pheroos-interface-dev5-site')
source_commit = '4ea5208ae5d7d6cd8c847f89e51f44a914143c8d'
runtime_commit = '2222d59bb05785528e4301dc14d164d538408ac6'
phase = repo / 'pheroos-bench/next-cycle/model-interface-v1'
config = json.loads((phase / 'pilot-config-proposal.json').read_text())
digest = sha256(json.dumps(config, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
assert digest == 'ed833e52d72e5a042fc56f0616c9ced9c52fe534302cfedc630da3445a3c1a8e'
for path, expected in ((repo, source_commit), (runtime, runtime_commit)):
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=path, text=True).strip() == expected
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=path, text=True).strip()
inputs = json.loads((phase / 'installation-inputs.json').read_text())
wheels = {repo / 'pheroos-bench' / x['path']: x['sha256'] for x in inputs}
wheels[phase / 'artifacts/accepted/pheroos_bench-0.1.1.dev5-py3-none-any.whl'] = 'eaf9ad0c637152c6c9f4b12f708ca76de40881096d86f6a984ed55134e4285fc'
verified = []
for wheel, expected in wheels.items():
    assert sha256(wheel.read_bytes()).hexdigest() == expected
    members = {}
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.endswith('/') or name.endswith('.dist-info/RECORD'):
                continue
            data = archive.read(name)
            assert (site / name).read_bytes() == data, name
            members[name] = sha256(data).hexdigest()
    verified.append(dict(wheel=str(wheel), sha256=expected, installed_members=members))
assert not out.exists(), 'Preparation namespace already exists; inspect, do not overwrite'
out.mkdir()
def save(name, value):
    with (out / name).open('x') as file:
        json.dump(value, file, indent=2, ensure_ascii=False)
        file.write('\n')
save('authorization.json', dict(
    profile='model_interface_operator_authorization_v1', recorded_utc=datetime.now(timezone.utc).isoformat(),
    user_instruction='授权执行这一次 model_interface_local_diagnostic_v1 本地诊断。',
    scope='One explicit additional exception to the historical campaign-count limit, conditional on exact reviewed-head necessary CI and accepted installation verification.',
    source_commit=source_commit, runtime_commit=runtime_commit, config_id=config['config_version'], config_sha256=digest,
    worlds=8, seeds_per_world=2, arms=list(config['base_arm_order']), cells=64, n=1, responses_per_cell=1,
    additional_token_cap=131072, additional_intent_cap=64, prior_tokens=65662, prior_intent_slots=114,
    combined_max_tokens=196734, combined_max_intents=178, total_token_cap=500000, total_intent_cap=1000,
    automatic_rerun_authorized=False, paid_api_authorized=False, remote_model_authorized=False,
    new_model_download_authorized=False, extra_seeds_authorized=False, collaboration_authorized=False,
    merge_authorized=False, stable_release_authorized=False,
    stop_rule='Retain ordinary wrong/invalid model answers and continue; stop on source/config drift, permissions, corrupted collection, budget violation or unresolved accounting. Preserve unstarted cells and never restart.',
    operator_authorization_is_runtime_authority=False, counts_toward_verdict=False))
save('installed-artifacts.json', dict(profile='model_interface_installed_identity_v1', status='VERIFIED',
    site=str(site), record_exclusion='pip rewrites dist-info/RECORD; all other wheel members compared byte-for-byte',
    verified_wheels=verified, source_commit=source_commit, runtime_commit=runtime_commit,
    counts_toward_verdict=False))
print(json.dumps(dict(status='VERIFIED', installed_members=sum(len(x['installed_members']) for x in verified),
    source_commit=source_commit, runtime_commit=runtime_commit, config_sha256=digest, model_calls=0)))
