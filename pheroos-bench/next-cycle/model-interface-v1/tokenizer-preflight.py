"""CPU tokenization only; no model construction, generation, or campaign."""
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
from types import SimpleNamespace

from transformers import AutoTokenizer
from pheroos_runtime.r3_local import LocalModel
from pheroos_bench import coordination_repair_v1_tasks as tasks
from pheroos_bench import model_interface_v1 as diagnostic
from pheroos_bench.model_interface_v1_pilot import configuration
from pheroos_bench.coordination_repair_v1 import digest

model = Path('/home/scott/projects/PheroOS-runtime/.local/models/qwen2.5-coder-3b')
output = Path(__file__).with_name('tokenizer-preflight.json')
config = configuration()
manifest = json.loads((model / 'manifest.json').read_text())
assert sha256((model / 'manifest.json').read_bytes()).hexdigest() == config['model']['manifest_sha256']
verified = {}
for name, expected in manifest['sha256'].items():
    if 'safetensors' not in name:
        actual = sha256((model / name).read_bytes()).hexdigest()
        assert actual == expected
        verified[name] = actual
tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True, trust_remote_code=False)
holder = SimpleNamespace(tokenizer=tokenizer)
rows = []
for world in config['worlds']:
    evidence = [tasks.inspect(world, 2, s['source_id']) for s in tasks.public_world(world, 2)['sources'] if s['required']]
    for arm, spec in diagnostic.ARMS.items():
        prompt = diagnostic.build_messages(world, arm, evidence)
        inputs = LocalModel.inputs(holder, prompt)
        ids = inputs['input_ids'][0].tolist()
        assert len(ids) + spec['max_new_tokens'] <= 2048
        rows.append(dict(world=world, arm=arm, prompt_tokens=len(ids), max_new_tokens=spec['max_new_tokens'],
            prompt_sha256=digest(prompt), input_ids_sha256=sha256(json.dumps(ids, separators=(',', ':')).encode()).hexdigest()))
report = dict(profile='model_interface_tokenizer_preflight_v1', status='FIT', rows=rows,
    config_sha256=digest(config), tokenizer_files_verified=verified,
    tokenizer_version=importlib.metadata.version('transformers'), model_weights_loaded=False,
    model_generate_calls=0, campaign_started=False, GPU_inference=False, counts_toward_verdict=False,
    note='Unmetered fixture reads for engineering tokenization only; actual campaign preparation is charged independently.')
with output.open('x') as stream:
    json.dump(report, stream, indent=2)
    stream.write('\n')
print(json.dumps({'status': 'FIT', 'prompt_range': [min(r['prompt_tokens'] for r in rows), max(r['prompt_tokens'] for r in rows)], 'model_generate_calls': 0}))
