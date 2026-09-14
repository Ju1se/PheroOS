"""Execute the single authorized frozen diagnostic exactly once."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time

root = Path('/tmp/pheroos-model-interface-live-v1')
repo = Path('/tmp/pheroos-interface-core')
runtime = Path('/tmp/pheroos-interface-runtime')
site = Path('/tmp/pheroos-interface-dev5-site')
python = '/home/scott/projects/PheroOS-runtime/.local/venv312/bin/python'
auth = json.loads((root / 'authorization.json').read_text())
ci = json.loads((root / 'ci-before-dispatch.json').read_text())
installed = json.loads((root / 'installed-artifacts.json').read_text())
assert ci['ready'] is True and not ci['failures']
assert auth['cells'] == 64 and auth['additional_token_cap'] == 131072 and auth['additional_intent_cap'] == 64
assert auth['automatic_rerun_authorized'] is False and auth['collaboration_authorized'] is False
assert auth['source_commit'] == ci['prs']['core']['headRefOid'] == '4ea5208ae5d7d6cd8c847f89e51f44a914143c8d'
assert auth['runtime_commit'] == ci['prs']['runtime']['headRefOid'] == '2222d59bb05785528e4301dc14d164d538408ac6'
for path, expected in ((repo, auth['source_commit']), (runtime, auth['runtime_commit'])):
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=path, text=True).strip() == expected
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=path, text=True).strip()
assert installed['site'] == str(site)
for artifact in installed['verified_wheels']:
    assert sha256(Path(artifact['wheel']).read_bytes()).hexdigest() == artifact['sha256']
    for name, expected in artifact['installed_members'].items():
        assert sha256((site / name).read_bytes()).hexdigest() == expected, name
config = repo / 'pheroos-bench/next-cycle/model-interface-v1/pilot-config-proposal.json'
config_value = json.loads(config.read_text())
assert sha256(json.dumps(config_value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest() == auth['config_sha256']
output = root / 'collection'
assert not output.exists() and not (root / 'process-start.json').exists(), 'No campaign restart is authorized'
env = {**os.environ, 'PYTHONPATH': str(site), 'HF_HUB_OFFLINE': '1',
       'TRANSFORMERS_OFFLINE': '1', 'PYTHONUNBUFFERED': '1'}
probe = subprocess.run([python, '-c',
    'import importlib.metadata,json,platform,torch; import pheroos,pheroos_runtime,pheroos_bench; '
    'assert torch.cuda.is_available(); '
    'print(json.dumps(dict(python=platform.python_version(),kernel=platform.release(),'
    'torch=torch.__version__,cuda_runtime=torch.version.cuda,gpu=torch.cuda.get_device_name(0),'
    'packages={p:importlib.metadata.version(p) for p in ("pheroos","pheroos-runtime","pheroos-bench","transformers")},'
    'imports=[pheroos.__file__,pheroos_runtime.__file__,pheroos_bench.__file__])))'],
    env=env, cwd='/tmp', text=True, capture_output=True, check=True)
hardware = json.loads(probe.stdout)
assert hardware['packages']['pheroos-runtime'] == '0.1.0.dev4' and hardware['packages']['pheroos-bench'] == '0.1.1.dev5'
assert all(Path(p).is_relative_to(site) for p in hardware['imports'])
hardware['nvidia_smi'] = subprocess.run(['nvidia-smi', '--query-gpu=name,uuid,driver_version,memory.total,memory.used,power.limit', '--format=csv'],
    capture_output=True, text=True, check=True).stdout
hardware.update(observed_utc=datetime.now(timezone.utc).isoformat(), configured_inference_capacity=1,
    synchronous_adapter=True, power_mode='NOT_OBSERVED', free_disk_bytes=shutil.disk_usage(root).free,
    model_inference_in_preflight=False, counts_toward_verdict=False)
with (root / 'execution-preflight.json').open('x') as stream:
    json.dump(hardware, stream, indent=2); stream.write('\n')
command = [python, '-m', 'pheroos_bench.model_interface_v1_pilot', '--config', str(config),
    '--output', str(output), '--model-path', '/home/scott/projects/PheroOS-runtime/.local/models/qwen2.5-coder-3b',
    '--predecessor-root', str(repo / 'pheroos-bench/next-cycle/coordination-repair-live-v1/campaign/actionability'),
    '--authorized-diagnostic']
record = dict(profile='model_interface_single_process_v1', command=command, cwd='/tmp',
    started_utc=datetime.now(timezone.utc).isoformat(), source_commit=auth['source_commit'], runtime_commit=auth['runtime_commit'],
    launcher_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
    authorization_sha256=sha256((root / 'authorization.json').read_bytes()).hexdigest(),
    ci_sha256=sha256((root / 'ci-before-dispatch.json').read_bytes()).hexdigest(),
    installed_artifacts_sha256=sha256((root / 'installed-artifacts.json').read_bytes()).hexdigest(),
    offline_model_files_only=True, automatic_retry=False, counts_toward_verdict=False)
with (root / 'process-start.json').open('x') as stream:
    json.dump(record, stream, indent=2); stream.write('\n')
started = time.monotonic_ns()
log = root / 'process.log'
try:
    with log.open('x') as stream:
        process = subprocess.Popen(command, cwd='/tmp', env=env, stdout=stream, stderr=subprocess.STDOUT, text=True)
        record['pid'] = process.pid
        print(json.dumps(dict(started=True, pid=process.pid, output=str(output))), flush=True)
        record['exit_code'] = process.wait()
except Exception as exc:
    record.update(exit_code=None, launcher_error=dict(type=type(exc).__name__, message=str(exc)))
    raise
finally:
    record.update(completed_utc=datetime.now(timezone.utc).isoformat(), elapsed_ns=time.monotonic_ns() - started,
        log_sha256=sha256(log.read_bytes()).hexdigest() if log.exists() else None)
    with (root / 'process.json').open('x') as stream:
        json.dump(record, stream, indent=2); stream.write('\n')
print(json.dumps(dict(exit_code=record['exit_code'], elapsed_ns=record['elapsed_ns'], receipt=str(root / 'process.json'))), flush=True)
raise SystemExit(record['exit_code'])
