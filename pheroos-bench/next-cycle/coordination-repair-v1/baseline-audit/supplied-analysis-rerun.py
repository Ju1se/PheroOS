"""Read-only, independent numerical/reconstruction audit of PheroOS PR #35.

This is a new implementation of the published R2 workload and scheduling
rules, not an execution of the repository's test suite. R1/R3/R4 arithmetic
uses explicitly transcribed published aggregates, not extracted raw archives.
No model, network, original SQLite database, or user repository is modified.
Sources: Ju1se/PheroOS commit 3604f5ce358ed6051c67e48906d240ac0b581f14,
pheroos-bench/src/pheroos_bench/r2_scheduling.py and r2-pilot-v1.json.
"""
import json
import math
from random import Random
from statistics import mean
from pathlib import Path
from collections import Counter

WORKERS = ({'compute','inspect'}, {'compute'}, {'inspect'}, {'compute'})
ARMS = ['capability_fifo','work_stealing','priority_queue','central_manager',
        'congestion_backpressure','no_backpressure']

def workload(seed, bottleneck):
    rng=Random(seed)
    jobs=[]
    for chain in range(8):
        arrival=chain*(2 if bottleneck else 10)+rng.randrange(2)
        deadline=arrival+rng.randint(9,15)
        for stage,capability in enumerate(('compute','inspect','compute')):
            jobs.append(dict(id=f'j{chain:02d}.{stage}',arrival=arrival,deadline=deadline,
                             capability=capability,tool=stage==1,
                             duration=rng.randint(2,4) if stage==1 else rng.randint(1,2),
                             dependencies=[] if stage==0 else [f'j{chain:02d}.{stage-1}'],
                             value=rng.randint(1,9),feeds_tool=stage==0))
    return jobs, 36 if bottleneck else 90, [(7,0,12),(17,2,21)] if bottleneck else []

def episode(seed, bottleneck, policy):
    jobs,horizon,failures=workload(seed,bottleneck)
    lookup={j['id']:j for j in jobs}
    ids=[j['id'] for j in jobs]
    ordinal={key:i for i,key in enumerate(sorted(ids))}
    state={key:dict(status='pending',remaining=lookup[key]['duration'],spent=0,
                    attempts=0,wait=0,first_ready=None,failed_at=None) for key in ids}
    running={}; offline={}; completion={}; results={}; dispatch=[]
    lost=0; recovery=[]; pressure_ticks=0; pressure_operations=0
    for tick in range(horizon):
        offline={w:until for w,until in offline.items() if tick<until}
        for ft,w,until in failures:
            if ft==tick:
                offline[w]=until
                if w in running:
                    key=running.pop(w); s=state[key]; lost+=s['spent']
                    s.update(status='ready',remaining=lookup[key]['duration'],spent=0,failed_at=tick)
        for key in ids:
            s=state[key]; j=lookup[key]
            if s['status']=='pending' and j['arrival']<=tick and all(dep in results for dep in j['dependencies']):
                s.update(status='ready',first_ready=tick)
        ready=[key for key in ids if state[key]['status']=='ready']
        pressure=False
        if policy=='congestion_backpressure':
            pressure_operations+=len(ready)
            pressure=sum(lookup[key]['tool'] for key in ready)>=2
            pressure_ticks+=pressure
        for worker,skills in enumerate(WORKERS):
            if worker in offline or worker in running: continue
            busy=sum(lookup[key]['tool'] for key in running.values())
            eligible=[key for key in ready if lookup[key]['capability'] in skills
                      and (not lookup[key]['tool'] or busy<1)]
            def keyfn(key):
                j=lookup[key]; fifo=(j['arrival'],key)
                if policy=='work_stealing': return (ordinal[key]%len(WORKERS)!=worker,*fifo)
                if policy=='priority_queue': return (j['deadline'],*fifo)
                if policy=='central_manager':
                    return (sum(j['capability'] in s for s in WORKERS),j['deadline'],*fifo)
                return (bool(pressure and j['feeds_tool']),*fifo)
            if not eligible: continue
            selected=min(eligible,key=keyfn); ready.remove(selected)
            s=state[selected]; s['status']='running'; s['attempts']+=1
            if s['failed_at'] is not None:
                recovery.append(tick-s['failed_at']); s['failed_at']=None
            running[worker]=selected; dispatch.append((tick,worker,selected))
        assert len(running.values())==len(set(running.values()))
        assert sum(lookup[k]['tool'] for k in running.values())<=1
        for key in ready: state[key]['wait']+=1
        for worker,key in list(running.items()):
            s=state[key]; s['remaining']-=1; s['spent']+=1
            if s['remaining']==0:
                results[key]=lookup[key]['value']+sum(results[d] for d in lookup[key]['dependencies'])
                completion[key]=tick+1; s['status']='done'; del running[worker]
    waits=sorted(s['wait'] for s in state.values() if s['first_ready'] is not None)
    return dict(seed=seed,bottleneck=bottleneck,policy=policy,completed=len(completion),
                on_time=sum(k in completion and completion[k]<=j['deadline'] for k,j in lookup.items()),
                p95_wait=waits[math.ceil(.95*len(waits))-1] if waits else 0,
                duplicate_attempts=sum(max(0,s['attempts']-1) for s in state.values()),
                lost_units=lost,recovery_delays=recovery,dispatch=dispatch,results=results,
                pressure_ticks=pressure_ticks,pressure_operations=pressure_operations)

rows=[episode(seed,bottleneck,arm) for seed in list(range(8))+list(range(100,132))
      for bottleneck in (True,False) for arm in ARMS]
index={(r['seed'],r['bottleneck'],r['policy']):r for r in rows}
paired=[]
for seed in list(range(8))+list(range(100,132)):
    for regime in (True,False):
        a=index[seed,regime,'capability_fifo']; b=index[seed,regime,'congestion_backpressure']
        paired.append(dict(seed=seed,bottleneck=regime,
                           dispatch_identical=a['dispatch']==b['dispatch'],
                           result_identical=a['results']==b['results'],
                           wait_identical=a['p95_wait']==b['p95_wait']))
summary={}
for arm in ARMS:
    selected=[r for r in rows if r['seed']>=100 and r['bottleneck'] and r['policy']==arm]
    summary[arm]=dict(episodes=len(selected), completed=sum(r['completed'] for r in selected),
                     on_time=sum(r['on_time'] for r in selected),
                     mean_episode_p95_wait=mean(r['p95_wait'] for r in selected),
                     duplicate_attempts=sum(r['duplicate_attempts'] for r in selected),
                     mean_lost_units=mean(r['lost_units'] for r in selected),
                     mean_pressure_operations=mean(r['pressure_operations'] for r in selected),
                     pressure_ticks=sum(r['pressure_ticks'] for r in selected))
expected={'capability_fifo':(768,625,8.09375),'work_stealing':(767,603,9.125),
          'priority_queue':(768,620,8.125),'central_manager':(767,632,7.5625),
          'congestion_backpressure':(768,625,8.09375),'no_backpressure':(768,625,8.09375)}
for arm,(completion,on_time,wait) in expected.items():
    assert summary[arm]['completed']==completion
    assert summary[arm]['on_time']==on_time
    assert summary[arm]['mean_episode_p95_wait']==wait
assert all(p['dispatch_identical'] and p['result_identical'] and p['wait_identical'] for p in paired)

r1={'candidate':dict(deliveries=98.75,operations=6356.5,bytes=393127.375),
    'dedup_ttl':dict(deliveries=108.25,operations=5527.75,bytes=327623.375),
    'full_relevant':dict(deliveries=798,operations=7377,bytes=650263.375),
    'matched_sparse_random':dict(deliveries=98.75,operations=4555.25,bytes=306206)}
r1_comparisons={arm:{metric:(r1['candidate'][metric]/value-1)*100 for metric,value in item.items()}
                for arm,item in r1.items() if arm!='candidate'}
r4=dict(success_share=51/264, code_success_share=51/132,
        rejected_evaluated_action_share=6268/7085,
        rejected_tokens_share=2970028/3402842,
        failed_episode_tokens_share=2620849/3402842,
        prompt_token_share=3030343/3402842,
        repeated_inspection_share=173/398,
        mixed_small_token_share=413350/(413350+65612),
        versioned_vs_dedup_token_change=(63312/64362-1)*100,
        versioned_vs_dedup_operation_change=(4441/4462-1)*100,
        aggregate_r4_known_tokens=2824212+3402842,
        fixed_call_total=160*32,
        logical_call_units=7134+7085+220957,
        code_hidden_cases={'bounded_increment':sum((ceiling+1)*16 for ceiling in range(13))-3,
                           'cyclic_offset':sum(size*31 for size in range(1,10))-3})
capacity={n:dict(final_version_turns_per_active_agent=sorted(Counter(step%n for step in range(16,32)).values()),
                 can_one_private_agent_make_three_inspections_and_submit=max(Counter(step%n for step in range(16,32)).values())>=4)
          for n in (1,2,4,8,16,32)}
output=dict(scope='Independent R2 rule reconstruction and arithmetic over published aggregates; not raw-archive or model rerun',
            source_commit='3604f5ce358ed6051c67e48906d240ac0b581f14',
            r2_reconstructed_episodes=len(rows),r2_matched_dispatch_pairs=len(paired),
            r2_all_candidate_fifo_dispatch_identical=True,r2_evaluation=summary,
            r1_relative_percent_change=r1_comparisons,r4_arithmetic=r4,
            r4_private_evidence_action_capacity=capacity)
Path('/tmp/pheroos-next-cycle-audit/supplied-analysis-rerun.json').write_text(json.dumps(output,indent=2))
print(json.dumps(output,indent=2))
