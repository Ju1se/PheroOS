"""Execute one authorized, source-pinned local phase; never retry a process."""
from pathlib import Path
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
import subprocess
import time

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--phase',choices=('actionability','collaboration'),required=True)
args=parser.parse_args()
repo=Path('/tmp/pheroos-next-cycle-core')
root=repo/'pheroos-bench/next-cycle/coordination-repair-live-v1'
site=Path('/tmp/pheroos-coordination-cli-dev4-site')
source_commit='cbbf105804dca286846771ee7560f245ffcd42e7'
authorization=json.loads((root/'authorization.json').read_text())
assert authorization['source_commit']==source_commit
assert authorization['total_token_cap']==500000 and authorization['total_intent_cap']==1000
assert authorization['additional_intent_cap']==999 and authorization['automatic_rerun_authorized'] is False
ci=json.loads((root/'ci-before-dispatch.json').read_text())
assert ci['terminal'] is True and not ci['failures']
assert ci['pr']['headRefOid']==source_commit
checks={c['name']:c for c in ci['pr']['statusCheckRollup']}
for name in ('quality-gate','release-candidate-dry-run','installed-session-consumer (dev2)','installed-session-consumer (dev3)'):
    assert checks[name]['status']=='COMPLETED' and checks[name]['conclusion']=='SUCCESS',name
assert all(c['status']=='COMPLETED' and c['conclusion'] in ('SUCCESS','SKIPPED') for c in checks.values())
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()==source_commit
assert not subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=repo,text=True).strip()
installed=json.loads((root/'installed-artifacts.json').read_text())
assert installed['site']==str(site)
for artifact in installed['verified_wheels']:
    assert sha256(Path(artifact['wheel']).read_bytes()).hexdigest()==artifact['sha256']
    for name,expected in artifact['installed_members'].items():
        assert sha256((site/name).read_bytes()).hexdigest()==expected,name
config=repo/'pheroos-bench/next-cycle/coordination-repair-cli-v1/pilot-config-proposal.json'
config_value=json.loads(config.read_text())
assert sha256(json.dumps(config_value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==authorization['config_sha256']
output=root/'campaign'
if args.phase=='actionability':
    assert not output.exists(),'Actionability output already exists; no automatic rerun'
else:
    previous=json.loads((root/'actionability-process.json').read_text())
    assert previous['exit_code']==0,'Only a complete admitted diagnostic can proceed'
    assert not (output/'collaboration').exists(),'Collaboration already exists; no automatic rerun'
command=['/home/scott/projects/PheroOS-runtime/.local/venv312/bin/python','-m',
 'pheroos_bench.coordination_repair_v2_pilot','--config',str(config),'--output',str(output),
 '--model-path','/home/scott/projects/PheroOS-runtime/.local/models/qwen2.5-coder-3b',
 '--phase',args.phase,'--predecessor-root',str(repo/'pheroos-bench/next-cycle/coordination-repair-v1'),
 '--authorized-additional-campaign']
env={**os.environ,'PYTHONPATH':str(site),'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','PYTHONUNBUFFERED':'1'}
log=root/(args.phase+'-process.log')
receipt=root/(args.phase+'-process.json')
assert not receipt.exists()
started=time.monotonic_ns()
record={'schema':'coordination_repair_local_process_v1','phase':args.phase,'command':command,'cwd':'/tmp',
 'started_utc':datetime.now(timezone.utc).isoformat(),'source_commit':source_commit,
 'launcher_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
 'ci_evidence_sha256':sha256((root/'ci-before-dispatch.json').read_bytes()).hexdigest(),
 'authorization_sha256':sha256((root/'authorization.json').read_bytes()).hexdigest(),
 'configured_inference_capacity':1,'counts_toward_verdict':False,'paid_api_calls':0}
with log.open('x') as stream:
    process=subprocess.Popen(command,cwd='/tmp',env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=1)
    record['pid']=process.pid
    print(json.dumps({'started_phase':args.phase,'pid':process.pid,'output':str(output)}),flush=True)
    for line in process.stdout:
        stream.write(line);stream.flush()
        print(line.rstrip(),flush=True)
    record['exit_code']=process.wait()
record['elapsed_ns']=time.monotonic_ns()-started
record['completed_utc']=datetime.now(timezone.utc).isoformat()
record['log_sha256']=sha256(log.read_bytes()).hexdigest()
record['log_bytes']=log.stat().st_size
with receipt.open('x') as stream:
    json.dump(record,stream,indent=2);stream.write('\n')
print(json.dumps({'phase':args.phase,'exit_code':record['exit_code'],'elapsed_ns':record['elapsed_ns'],'receipt':str(receipt)}),flush=True)
raise SystemExit(record['exit_code'])
