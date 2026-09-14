"""Verify the reviewed artifacts and record the user's bounded authorization."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,zipfile
root=Path('/tmp/pheroos-next-cycle-core')
out=root/'pheroos-bench/next-cycle/coordination-repair-live-v1'
site=Path('/tmp/pheroos-coordination-cli-dev4-site')
proposal=root/'pheroos-bench/next-cycle/coordination-repair-cli-v1/pilot-config-proposal.json'
config=json.loads(proposal.read_text())
digest=hashlib.sha256(json.dumps(config,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
assert digest=='916e2b2f05e32059b2e0ca35e1ce70f9708b8a98059cc40aface055cb86b6193'
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert head=='cbbf105804dca286846771ee7560f245ffcd42e7'
assert not subprocess.check_output(['git','diff','HEAD','--name-only'],cwd=root,text=True).strip()
art=root/'pheroos-bench/next-cycle/coordination-repair-v1/artifacts'
inputs=json.loads((art/'installation-inputs-dev3.json').read_text())
wheels={art/name:value for name,value in inputs.items()}
wheels[root/'pheroos-bench/next-cycle/coordination-repair-cli-v1/artifacts/accepted/pheroos_bench-0.1.1.dev4-py3-none-any.whl']='19aadbd99992c5baae6f73cad2007b7240a6eb135400436e14c6dd28d88db6c3'
verified=[]
for wheel,expected in wheels.items():
    assert hashlib.sha256(wheel.read_bytes()).hexdigest()==expected
    members={}
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            if name.endswith('/') or name.endswith('.dist-info/RECORD'):
                continue
            data=archive.read(name)
            assert (site/name).read_bytes()==data,name
            members[name]=hashlib.sha256(data).hexdigest()
    verified.append({'wheel':str(wheel),'sha256':expected,'installed_members':members})
auth={'schema':'coordination_repair_operator_authorization_v1','recorded_utc':datetime.now(timezone.utc).isoformat(),
 'user_instruction':'授权继续goal','interpreted_scope':'One additional local actionability campaign after all current-head CI succeeds; one collaboration campaign only if unchanged admission and intervention gates pass.',
 'source_commit':head,'config_version':config['config_version'],'config_sha256':digest,
 'total_token_cap':500000,'total_intent_cap':1000,'predecessor_reserved_intents':1,'additional_intent_cap':999,
 'paid_api_calls_authorized':False,'automatic_rerun_authorized':False,'operator_authorization_is_runtime_authority':False,'counts_toward_verdict':False}
with (out/'authorization.json').open('x') as file:
    json.dump(auth,file,indent=2,ensure_ascii=False);file.write('\n')
with (out/'installed-artifacts.json').open('x') as file:
    json.dump({'site':str(site),'record_exclusion':'pip rewrites dist-info/RECORD; all other wheel members compared byte-for-byte','verified_wheels':verified},file,indent=2);file.write('\n')
print({'source_commit':head,'config_sha256':digest,'verified_wheels':len(verified),'verified_installed_members':sum(len(w['installed_members']) for w in verified),'campaign_directory_exists':(out/'campaign').exists()})
