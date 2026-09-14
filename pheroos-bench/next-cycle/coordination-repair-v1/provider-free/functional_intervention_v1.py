"""Independent descriptive check: ignore agent labels and suggested labels."""
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def wire(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)

broad=json.loads((ROOT/'intervention-relevance.json').read_text())
rows=[]
for row in broad:
    def functional(steps):
        return [{'action':t['normalized_action'], 'materialized_receipts':t['materialized_receipts']}
                for t in steps]
    control,candidate=functional(row['control']),functional(row['candidate'])
    rows.append({'world_id':row['world_id'],'n':row['n'],
                 'changed_executed_work_or_materialized_evidence':wire(control)!=wire(candidate),
                 'broad_changed_including_agent_labels':row['behavior_changed'],
                 'control':control,'candidate':candidate})
result={'method':'functional_intervention_relevance_v1','source':'intervention-relevance.json',
        'source_sha256':sha256((ROOT/'intervention-relevance.json').read_bytes()).hexdigest(),
        'runner_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'cases':len(rows),'functional_changes':sum(r['changed_executed_work_or_materialized_evidence'] for r in rows),
        'rows':rows,'counts_toward_verdict':False,
        'interpretation':'A changed executed action/provenance sequence demonstrates intervention relevance in this scripted instrument. An unchanged sequence remains an expected-null observation. Neither establishes learned efficacy.'}
with (ROOT/'functional-intervention.json').open('x') as stream:
    stream.write(wire(result)+'\n')
print(wire({'cases':result['cases'],'functional_changes':result['functional_changes'],'rows':[{k:r[k] for k in ('world_id','n','changed_executed_work_or_materialized_evidence')} for r in rows]}))
