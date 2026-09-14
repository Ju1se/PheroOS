"""Tokenize retained instrument prompts; never load weights or generate output."""

from copy import deepcopy
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import time

from transformers import AutoTokenizer


ROOT = Path(__file__).resolve().parent
MODEL = Path('/home/scott/projects/PheroOS-runtime/.local/models/qwen2.5-coder-3b')


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def save(path, value):
    with path.open('x') as stream:
        stream.write(wire(value) + '\n')


def main():
    summary = json.loads((ROOT/'summary.json').read_text())
    if summary['source_unchanged'] is not True:
        raise RuntimeError('Cannot characterize changed-source campaign as a single instrument')
    manifest = json.loads((MODEL/'manifest.json').read_text())
    tokenizer_files = ('tokenizer.json', 'tokenizer_config.json', 'vocab.json', 'merges.txt')
    observed = {name: sha256((MODEL/name).read_bytes()).hexdigest() for name in tokenizer_files}
    if any(observed[name] != manifest['sha256'][name] for name in tokenizer_files):
        raise RuntimeError('Tokenizer files differ from accepted local manifest')
    config = {'config_id':'coordination_repair_tokenizer_context_fit_v1',
              'model_repository':manifest['repository'], 'model_revision':manifest['revision'],
              'model_manifest_sha256':sha256((MODEL/'manifest.json').read_bytes()).hexdigest(),
              'tokenizer_sha256':observed,'transformers':importlib.metadata.version('transformers'),
              'runner_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
              'source_campaign_config_sha256':sha256((ROOT/'config.json').read_bytes()).hexdigest(),
              'generation_calls':0,'model_weights_loaded':False,
              'context_limit':2048,'reserved_completion_tokens':256,
              'variants':['actual_saved_prompt','bounded_public_failure_feedback'],
              'feedback_fixture':'two 230-character public syntax/target error strings; no answers or authority',
              'count_basis':'actual accepted tokenizer apply_chat_template with generation prompt'}
    save(ROOT/'context-fit-config.json',config)
    started = time.monotonic_ns()
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True, trust_remote_code=False)
    entries=[]
    prefix_first={}
    for episode_path in sorted(ROOT.rglob('episode.json')):
        episode=json.loads(episode_path.read_text())
        for row in episode.get('turns',[]):
            prompt=row['messages']
            altered=deepcopy(prompt)
            content=json.loads(altered[1]['content'])
            base='Invalid action: return one JSON object and choose a currently declared public target. '
            content['private_feedback']=[(base*4)[:230], (base*4)[:230]]
            assert len(wire(content['private_feedback']).encode()) <=512
            altered[1]['content']=wire(content)
            for label,messages in [('actual_saved_prompt',prompt),('bounded_public_failure_feedback',altered)]:
                ids=tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=True)
                count=len(ids)
                entry={'episode':str(episode_path.parent.relative_to(ROOT)), 'world_id':episode['world_id'],
                       'turn':row['turn'],'variant':label,'prompt_tokens':count,
                       'prompt_plus_reserved_completion':count+256,'fits':count+256<=2048,
                       'prompt_sha256':sha256(wire(messages).encode()).hexdigest(),
                       'token_ids_sha256':sha256(wire(ids).encode()).hexdigest()}
                entries.append(entry)
                if row['turn']==0 and str(episode_path.parent.relative_to(ROOT)).startswith('forks/'):
                    prefix_first[(episode['world_id'], episode_path.parent.name, label)] = count
    differences=[]
    for (world,branch,variant),count in sorted(prefix_first.items()):
        relevant=prefix_first.get((world,'relevant',variant))
        differences.append({'world_id':world,'branch':branch,'variant':variant,'first_prompt_tokens':count,
                            'difference_from_relevant':count-relevant if relevant is not None else None})
    result={'config_id':config['config_id'],'status':'PASS' if all(r['fits'] for r in entries) else 'CONTEXT_BOUND_FAILED',
            'tokenization_operations':len(entries),'model_dispatches':0,'model_weights_loaded':False,
            'entries':entries,'violations':[r for r in entries if not r['fits']],
            'maximum_prompt_tokens':max((r['prompt_tokens'] for r in entries),default=0),
            'maximum_prompt_plus_completion':max((r['prompt_plus_reserved_completion'] for r in entries),default=0),
            'fork_first_prompt_differences':differences,
            'elapsed_seconds':(time.monotonic_ns()-started)/1e9,
            'limitation':'Tokenizer fit covers retained scripted prompts and a bounded public-error fixture. Later live outputs may induce different prompts; runtime preflight remains mandatory.'}
    save(ROOT/'context-fit.json',result)
    print(wire({key:result[key] for key in ('status','tokenization_operations','maximum_prompt_tokens','maximum_prompt_plus_completion','violations')}),flush=True)
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
