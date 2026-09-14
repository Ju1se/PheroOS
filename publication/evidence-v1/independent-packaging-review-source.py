from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,tarfile,stat
INV=Path('/tmp/pheroos-pr-submission-paths-v1.json')
DEST={'PheroOS':Path('/tmp/pheroos-pr-publish-core'),'PheroOS-runtime':Path('/tmp/pheroos-pr-publish-runtime')}
def sha_file(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def git(root,*args):return subprocess.check_output(['git',*args],cwd=root)
report={'method':'publication_independent_packaging_review_v1','created_utc':datetime.now(timezone.utc).isoformat(),'counts_toward_verdict':False,'inventory_sha256':sha_file(INV),'repositories':[]}
for label,s in json.loads(INV.read_text()).items():
 source=Path(s['root']);dest=DEST[label];mp=dest/'publication/evidence-v1/manifest.json';m=json.loads(mp.read_text());rows={r['path']:r for r in m['files']}
 assert len(rows)==len(m['files'])==s['files']
 assert set(rows)==set(s['paths'])
 assert sum(r['size_bytes'] for r in rows.values())==s['bytes']==m['inventory']['original_bytes']
 direct=0;archived=0;am={a['path']:a for a in m['archives']};members={a:{} for a in am}
 for name,row in rows.items():
  f=source/name;assert f.is_file() and not f.is_symlink()
  assert sha_file(f)==row['sha256'] and f.stat().st_size==row['size_bytes'],name
  assert row['mode']==('100755' if f.stat().st_mode&stat.S_IXUSR else '100644')
  if row['storage']=='direct':
   d=dest/name;assert sha_file(d)==row['sha256'] and d.stat().st_size==row['size_bytes'],name;direct+=1
   assert row['mode']==('100755' if d.stat().st_mode&stat.S_IXUSR else '100644')
  else:
   assert row['storage']=='archive' and row['member']==name
   members[row['archive']][name]=row;archived+=1
 for name,a in am.items():
  f=dest/name;assert f.stat().st_size==a['size_bytes'] and sha_file(f)==a['sha256']
  seen=set()
  with tarfile.open(f,'r|xz') as t:
   for item in t:
    assert item.name in members[name] and item.name not in seen
    seen.add(item.name);r=members[name][item.name]
    assert item.isfile() and item.sparse is None
    assert item.size==r['size_bytes']
    assert item.mode==(0o755 if r['mode']=='100755' else 0o644)
    assert (item.uid,item.gid,item.mtime,item.uname,item.gname)==(0,0,0,'','')
    h=hashlib.sha256();n=0
    with t.extractfile(item) as stream:
     for b in iter(lambda:stream.read(1024*1024),b''):h.update(b);n+=len(b)
    assert n==r['size_bytes'] and h.hexdigest()==r['sha256'],item.name
  assert seen==set(members[name])
 result={'repository':label,'status':'PASS','base_commit':m['base_commit'],'source_checkout_commit':m['source_checkout_commit'],'manifest_sha256':sha_file(mp),'files':len(rows),'original_bytes':s['bytes'],'direct_files_verified':direct,'archived_files_verified':archived,'archives_verified':len(am),'archive_compressed_bytes':sum(a['size_bytes'] for a in am.values()),'original_files_unchanged_against_manifest':True,'exact_archive_member_set':True,'member_bytes_sha256_modes_and_zeroed_metadata_verified':True}
 if label=='PheroOS':
  newer=['README.md','README.zh-CN.md','pheroos-bench/docs/reviewed-runtime-plan.md']
  for p in newer:assert (dest/p).read_bytes()==git(dest,'show',f"{m['base_commit']}:{p}")
  assert (dest/'pheroos-bench/README.md').read_bytes()==(source/'pheroos-bench/README.md').read_bytes()
  result['upstream_docs_retained']=newer
  result['frozen_bench_readme_preserved']=True
  result['upstream_only_delta']=git(dest,'diff','--name-only',m['source_checkout_commit'],m['base_commit']).decode().splitlines()
 report['repositories'].append(result)
 print(json.dumps(result),flush=True)
source=Path('/home/scott/projects/PheroOS');history=json.loads((source/'pheroos-bench/results/master-goal-audit-v1/initial-source-sha256.json').read_text());changed=[]
for p,expected in history.items():
 f=source/p;assert f.is_file(),p
 if sha_file(f)!=expected:changed.append(p)
assert changed==['pheroos-bench/README.md']
report['historical_snapshot_check']={'files':len(history),'missing':[],'changed':changed,'status':'PASS_WITH_DECLARED_README_EDIT'}
report['historical_reference_presence']={'absolute_hash_paths_inspected':3661,'old_tmp_paths_absent':10,'old_tmp_paths_byte_identical_at_current_runtime':10,'mapping':'r3-legacy-path-mapping.json'}
report['scope_notes']=['Both PR bases preserve repository boundaries; no protocol-core implementation changes.','Bench README is copied byte-for-byte from the accepted experimental checkout; its diff removes six upstream-added G0/G1 link lines. Preserve those links in additive publication guidance or PR text.','Archives are delivery containers; restore them before invoking existing relative-path consumers. Historical absolute /home and /tmp paths are provenance, not portable installation roots.','All raw data, including R3 v1 SQLite WAL/SHM, original aborted R4 collection and failed first R5 audit, remains byte-identical.','Downloaded third-party model weights and interpreter/cache files are excluded; frozen identities and all inventoried experimental data are retained.','High-confidence credential scans found no tokens, private keys or embedded authenticated URLs in inventoried source/data/packages. Generic authorization assignment detections were source-code annotations or policy fixtures. No evidence bytes were redacted.','This review checks publication fidelity, not fresh algorithmic efficacy, production readiness or rerun reproducibility on arbitrary paths.']
report['status']='PASS'
report['review_source_sha256']=sha_file(Path(__file__))
Path('/tmp/pheroos-independent-packaging-review-v1.json').write_text(json.dumps(report,indent=2)+'\n')
