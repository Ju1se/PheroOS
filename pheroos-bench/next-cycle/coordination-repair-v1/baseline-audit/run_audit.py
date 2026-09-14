"""Read only historical source/JSON audit; all outputs stay beside this file."""
from pathlib import Path
from collections import Counter, defaultdict
from statistics import mean
from hashlib import sha256
import json, sys, subprocess, platform, contextlib, io

OUT = Path(__file__).resolve().parent
CORE = Path('/home/scott/projects/PheroOS')
RUNTIME = Path('/home/scott/projects/PheroOS-runtime')
DOWNLOADS = Path('/mnt/c/Users/24410/Downloads')
sys.dont_write_bytecode = True
sys.path.insert(0, str(CORE / 'pheroos-bench/src'))

def digest(p):
    return sha256(p.read_bytes()).hexdigest()

def save(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')

paths = [DOWNLOADS/n for n in ('PheroOS_Next_Cycle_Codex_Goal.md', 'AUDIT_SCOPE_AND_NEXT_STEPS.md',
                               'independent_analysis.py', 'independent_analysis.json')]
paths += [CORE/p for p in ('AGENTS.md','docs/protocol/current-support.md',
    'pheroos-bench/EXPERIMENTAL-OS-CANDIDATE.md','pheroos-bench/results/master-goal-audit-v1/FINAL-REPORT.md',
    'pheroos-bench/src/pheroos_bench/r1_coordination.py','pheroos-bench/src/pheroos_bench/r2_scheduling.py',
    'pheroos-bench/src/pheroos_bench/r4_tasks.py','pheroos-bench/src/pheroos_bench/r4_session_scaling.py',
    'pheroos-bench/results/r1-coordination-pilot-v2/episodes.jsonl',
    'pheroos-bench/results/r2-pilot-v1/episodes.jsonl',
    'pheroos-bench/results/r4-session-scaling-replication-v1/collection/episodes.jsonl')]
paths += [RUNTIME/p for p in ('AGENTS.md','src/pheroos_runtime/session_v1.py',
                             'src/pheroos_runtime/session_driver_v1.py','docs/session-v1.md')]
identities = {str(p): {'sha256':digest(p),'bytes':p.stat().st_size} for p in paths}
revisions = {str(p):{'head':subprocess.check_output(['git','-C',str(p),'rev-parse','HEAD'], text=True).strip(),
                    'branch':subprocess.check_output(['git','-C',str(p),'branch','--show-current'], text=True).strip(),
                    'status':subprocess.check_output(['git','-C',str(p),'status','--porcelain'], text=True).splitlines()}
             for p in (CORE,RUNTIME)}
publication_identity_matches=[]
for root, published in ((CORE,Path('/tmp/pheroos-pr-publish-core')),
                        (RUNTIME,Path('/tmp/pheroos-pr-publish-runtime'))):
    manifest=json.loads((published/'publication/evidence-v1/manifest.json').read_text())
    files={f['path']:f for f in manifest['files']}
    for p in paths:
        if p.is_relative_to(root) and (rel:=str(p.relative_to(root))) in files:
            assert digest(p)==files[rel]['sha256'],rel
            publication_identity_matches.append({'path':str(p),'sha256':digest(p)})

# Execute the fully read user-supplied reconstruction with ONLY its hardcoded
# output destination redirected. Original source remains unchanged.
original=(DOWNLOADS/'independent_analysis.py').read_text()
old="Path('/mnt/data/pheroos_audit/independent_analysis.json')"
assert original.count(old)==1
adapted=original.replace(old,"Path('/tmp/pheroos-next-cycle-audit/supplied-analysis-rerun.json')")
(OUT/'supplied-analysis-rerun.py').write_text(adapted)
namespace={'__name__':'supplied_independent_analysis'}
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(adapted,str(OUT/'supplied-analysis-rerun.py'),'exec'),namespace)
assert json.loads(json.dumps(namespace['output']))==json.loads((DOWNLOADS/'independent_analysis.json').read_text())

# R1: all 64 raw rows, not reported means.
r1rows=[json.loads(s) for s in (CORE/'pheroos-bench/results/r1-coordination-pilot-v2/episodes.jsonl').read_text().splitlines()]
assert len({(r['arm'],r['seed']) for r in r1rows})==len(r1rows)==64
r1={}
for arm in ('candidate','dedup_ttl'):
    rr=[r for r in r1rows if r['arm']==arm]
    r1[arm]={'episodes':len(rr),'successes':sum(r['success'] for r in rr),
             'deliveries':mean(sum(r['data_deliveries_per_step']) for r in rr),
             'operations':mean(r['cost']['total_accounted_operations'] for r in rr),
             'bytes':mean(r['cost']['total_accounted_bytes'] for r in rr)}
r1['candidate_relative_percent']={k:(r1['candidate'][k]/r1['dedup_ttl'][k]-1)*100
                                  for k in ('deliveries','operations','bytes')}

# R2: compare independent reconstructed results with 480 original raw rows,
# and separately replay the frozen source to compare actual dispatch traces.
from pheroos_bench import r2_scheduling
r2raw=[json.loads(s) for s in (CORE/'pheroos-bench/results/r2-pilot-v1/episodes.jsonl').read_text().splitlines()]
index={(r['seed'],r['world'],r['arm']):r for r in r2raw}
assert len(index)==len(r2raw)==480
dispatch_matches=0
replays={}
for r in namespace['rows']:
    world=r2_scheduling.WORLDS[0 if r['bottleneck'] else 1]
    raw=index[r['seed'],world,r['policy']]
    assert (r['results']==raw['results'] and r['completed']==raw['completed_tasks']
            and r['p95_wait']==raw['p95_wait_ticks']
            and r['duplicate_attempts']==raw['duplicate_attempts']
            and r['pressure_ticks']==raw['pressure_ticks'])
    if r['policy'] in ('capability_fifo','congestion_backpressure'):
        replay=r2_scheduling.run_episode(r['seed'],r['policy'],world,include_trace=True)
        assert replay['trace_sha256']==raw['trace_sha256']
        dispatch=[(e['tick'],e['worker'],e['task']) for e in replay['trace'] if e['kind']=='dispatch']
        assert dispatch==r['dispatch']
        replays[r['seed'],world,r['policy']]=dispatch
for seed in list(range(8))+list(range(100,132)):
    for world in r2_scheduling.WORLDS:
        assert replays[seed,world,'capability_fifo']==replays[seed,world,'congestion_backpressure']
        dispatch_matches+=1
r2={'independent_raw_result_matches':480,'frozen_source_replays':160,
    'raw_trace_hash_matches':160,'candidate_fifo_identical_dispatch_pairs':dispatch_matches,
    'bottleneck_evaluation_pressure_ticks':sum(r['pressure_ticks'] for r in r2raw if r['arm']=='congestion_backpressure' and r['seed']>=100 and r['world']==r2_scheduling.WORLDS[0]),
    'bottleneck_evaluation_mean_extra_pressure_inspections':mean(r['costs']['pressure_inspections'] for r in r2raw if r['arm']=='congestion_backpressure' and r['seed']>=100 and r['world']==r2_scheduling.WORLDS[0])}

# R4: independently read raw JSON only. SQLite/WAL/SHM are not opened.
episodes=[json.loads(s) for s in (CORE/'pheroos-bench/results/r4-session-scaling-replication-v1/collection/episodes.jsonl').read_text().splitlines()]
assert len({(r['condition_id'],r['world_id']) for r in episodes})==len(episodes)==264
feedback=Counter(); stages=Counter(); stage_tokens=Counter(); model_calls=0; tool_calls=0; model_states=Counter()
prompt_tokens=0; actual_tokens=0; rejected_tokens=0; rejected=0; repeats=0; inspections=0
stops=Counter(); statuses=Counter(); pending=Counter(); mixed_tokens=Counter()
inputs={}; response_signatures={}
for ep in episodes:
    stops[ep['stop_reason']]+=1;statuses[ep['status']]+=1
    calls={c['id']:c for c in ep['ledger_calls']}
    im={};rm={};seen=set()
    for c in calls.values():
        if c['action']=='model.generate':
            model_states[c['state']]+=1
            model_calls+=c['state'] in ('received','dispatched')
            if c['state']=='received':
                resp=json.loads(c['response']); req=json.loads(c['request']);step=int(c['id'].split('-')[-1])
                actual_tokens+=c['actual'];prompt_tokens+=resp['prompt_tokens'];
                im[step]={k:req[k] for k in ('messages','seed','model_ref','model_identity','max_new_tokens')}
                rm[step]={k:resp[k] for k in ('text','prompt_tokens','completion_tokens')}
                if '-mixed-' in ep['condition_id']:mixed_tokens[req['model_ref']]+=c['actual']
        elif c['action']=='tool.evaluate' and c['state']=='received':
            tool_calls+=1
            result=json.loads(c['response'])['artifact']; feedback[result['feedback']]+=1
            stage='accepted'
            if not result['valid']:
                rejected+=1;msg=result['feedback']
                if 'unknown test target' in msg or 'unknown source target' in msg:stage='undeclared_target'
                elif 'all three current source inspection receipts' in msg:stage='missing_current_evidence'
                elif 'cite all three exact current sources' in msg:stage='missing_or_stale_citation_metadata'
                elif 'Expecting value:' in msg:stage='transport_format'
                elif 'function did not return an integer' in msg:stage='execution_error'
                elif 'unsupported statement' in msg:stage='public_code_language_rejection'
                elif 'fails a declared public test' in msg:stage='public_test_rejection'
                elif 'choose exactly' in msg or 'code_lines must contain' in msg:stage='action_schema'
                else:raise AssertionError('Unclassified public feedback '+msg)
            stages[stage]+=1
            mc=calls['generate-'+c['id'].split('-')[-1]]
            stage_tokens[stage]+=mc['actual']
            if not result['valid']:rejected_tokens+=mc['actual']
    for r in ep['records']:
        if not r.get('evaluation'):pending['known_response_no_evaluation' if r.get('response') else 'no_recorded_response']+=1
        if r.get('published') and r.get('valid') and r.get('action')=='inspect':
            inspections+=1
            origin=r['origin_identity']
            repeats+=origin in seen
            seen.add(origin)
    inputs[ep['condition_id'],ep['world_id']]=im
    response_signatures[ep['condition_id'],ep['world_id']]=rm
null_pairs=[]
for ep in episodes:
    cond=ep['condition_id']; head, n=cond.rsplit('-n',1)
    if not cond.startswith('fixed_calls-') or int(n)==1 or '-private-' in cond:continue
    reference=head+'-n1';key=(cond,ep['world_id']);ref=(reference,ep['world_id'])
    if ref not in inputs:continue
    a,b=inputs[key],inputs[ref];common=sorted(a.keys()&b.keys())
    null_pairs.append({'condition':cond,'reference':reference,'world':ep['world_id'],
      'equal_step_sets':a.keys()==b.keys(),'common_steps':len(common),
      'same_inputs':sum(a[s]==b[s] for s in common),
      'same_responses':sum(response_signatures[key][s]==response_signatures[ref][s] for s in common)})
r4={'episodes':264,'model_dispatches':model_calls,'model_ledger_states':dict(model_states),'evaluated_actions':tool_calls,'rejected_actions':rejected,
    'actual_tokens':actual_tokens,'prompt_tokens':prompt_tokens,'rejected_action_tokens':rejected_tokens,
    'public_action_primary_stages':dict(stages),'tokens_by_public_action_stage':dict(stage_tokens),
    'raw_feedback_counts':dict(feedback),'stop_reasons':dict(stops),'episode_statuses':dict(statuses),
    'not_evaluated_record_counts':dict(pending),'published_valid_inspections':inspections,
    'repeated_published_valid_inspections_by_origin':repeats,'mixed_tokens':dict(mixed_tokens),
    'same_input_fixed_call_pairs':len(null_pairs),'pairs_all_common_inputs_equal':sum(p['same_inputs']==p['common_steps'] for p in null_pairs),
    'compared_model_input_steps':sum(p['common_steps'] for p in null_pairs),
    'equal_model_input_steps':sum(p['same_inputs'] for p in null_pairs),
    'equal_model_response_steps':sum(p['same_responses'] for p in null_pairs),
    'private_final_version_capacity':namespace['output']['r4_private_evidence_action_capacity'],
    'primary_stage_scope':'Diagnostic classification of historic public-tool feedback; not a replacement historical method. Parse formatting and semantic syntax are distinct. No hidden objective feedback used.'}
assert (model_calls,tool_calls,rejected,actual_tokens,prompt_tokens,rejected_tokens,inspections,repeats)==(7134,7085,6268,3402842,3030343,2970028,398,173), (model_calls,tool_calls,rejected,actual_tokens,prompt_tokens,rejected_tokens,inspections,repeats)

requirements=[
 ('A1','Stable failure taxonomy, raw and normalized actions, actual feedback and full charged denominators; hidden final correctness stays outside policy.'),
 ('A2','Concrete legal target IDs and small shared schema; no executable placeholders or semantic repair; bounded charged retries.'),
 ('A3','Predeclare one D0/D1/D2 actionability campaign on identified development worlds; D0/D1 preparation charged and separate from matched efficacy.'),
 ('A4','Trusted public-tool reference completes each primary condition under identical opportunity limits; label unreachable cases structural negative controls.'),
 ('B1','Scope/source/version immutable evidence index with provenance, supersession, validity; attention TTL does not erase valid evidence.'),
 ('B2','Bounded manifests plus metered retrieval/materialization/serialization; separate bounded private error feedback and preserve private access restrictions.'),
 ('B3','Pure-read version/state-aware reuse and in-flight ownership; no duplicate independent support or automatic unknown dispatch retries.'),
 ('B4','Test duplicate/reordered delivery, concurrent claims, updates, stale cache, cross-scope, cancel/expiry, unknown and late receipt behavior.'),
 ('C1','Shared corrected runtime/interface/tools/accounting/evaluator: single total-budget agent, blackboard dedup TTL N2/N4, candidate N2/N4, allocation/reuse ablations.'),
 ('C2','Real bounded private state and eligible work choices; demonstrated changed assignment/retrieval/composition before larger collection; same-input N relabeling stays null instrument.'),
 ('D','Predeclared eligible prefix relevant/withheld/size-matched irrelevant branches; independently accounted full downstream rollouts, origin lineage, fresh current permissions, setup cost, no hidden selection.'),
 ('M','World-level primary success/cost, nested-fork versioned analysis, prefix/incremental costs separate; unequal cell and nonzero signed cost synthetic checks; unknown cost never zero.'),
 ('Resources','Local existing models only; cycle ceilings 500000 total tokens/1000 dispatches, one actionability and one collaboration campaign; reserve output and retain unresolved upper bounds; no confirmatory study.'),
 ('Hardening','Process-barrier claim/cancel/dispatch/publication tests, late settlement without revival, fake-clock changes/restart, explicit retention limits; no system clock/stack changes.'),
 ('Delivery','Distinct experimental package identity retaining prior cohort; installed-Session integration and relevant regressions; audit, source, tests, diagnostics, frozen configs/raw records, full-rollout evidence, reproduction, report and status.'),
]
assert all(digest(Path(p))==v['sha256'] for p,v in identities.items())
result={'audit_version':'coordination_repair_baseline_audit_v1','status':'COMPLETED_READ_ONLY_BASELINE_AUDIT',
 'counts_toward_verdict':False,'python':platform.python_version(),'repositories':revisions,
 'reviewed_pr_snapshots':{'PheroOS':'3604f5ce358ed6051c67e48906d240ac0b581f14','runtime':'c94a2efd13ace1ac424b5ccb1dc0f885b810f82c'},
 'source_identities':identities,'publication_manifest_identity_matches':publication_identity_matches,
 'supplied_reconstruction_output_identical':True,'r1':r1,'r2':r2,'r4':r4,
 'requirements':[{'id':i,'requirement':r,'completion':'NOT_ASSESSED_NEW_WORK'} for i,r in requirements],
 'source_bytes_unchanged_after_audit':True,'limits':['No model calls, network, historical SQLite access, or package/test suite execution.',
 'R2 independent reconstructed dispatch is compared with frozen-source replay and original stored trace hashes; replay alone is not independent oracle.',
 'R4 diagnostics use 264 raw replication episodes and receipt records, not new inference. Unknown/rejected/unevaluated rows retained.',
 'Audit checks selected source/raw identities against publication manifest, not all archives or repository history.',
 'Current remote PR/branch resolution and installed identities are owned by the root audit; local dirty source manifests identify this read-only input.',
 '4 historical task worlds and deterministic shared prompts cannot establish broad generalization or independent agent intelligence.']}
save('baseline-audit.json',result);save('same-input-pairs.json',null_pairs)
print(json.dumps({'output':str(OUT/'baseline-audit.json'),'r1':r1,'r2':r2,'r4':{k:v for k,v in r4.items() if k not in ('raw_feedback_counts','private_final_version_capacity')}},indent=2))
