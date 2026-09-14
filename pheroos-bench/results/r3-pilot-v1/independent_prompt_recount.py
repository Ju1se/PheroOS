"""Offline CPU token recount and model-file hash audit; no generation."""
import hashlib
import json
import os
from pathlib import Path

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
from transformers import AutoTokenizer

output = Path(__file__).resolve().parent
model = Path('/tmp/PheroOS-runtime/.local/models/qwen2.5-coder-1.5b')
manifest = json.loads((model / 'manifest.json').read_text())
freeze = json.loads((output / 'freeze.json').read_text())
assert manifest == freeze['model']
for name, expected in manifest['sha256'].items():
    digest = hashlib.sha256()
    with (model / name).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    assert digest.hexdigest() == expected, name
tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True, trust_remote_code=False)
traces = [json.loads(line) for line in (output / 'trace.jsonl').read_text().splitlines()]
total = 0
for trace in traces:
    encoded = tokenizer.apply_chat_template(trace['request']['messages'],
                                           add_generation_prompt=True, tokenize=True)
    assert len(encoded) == trace['response']['prompt_tokens'], trace['request']['call_id']
    total += len(encoded)
print(json.dumps({'status': 'PASS', 'calls_recounted': len(traces),
                  'prompt_tokens_recounted': total, 'model_files_hashed': len(manifest['sha256']),
                  'model_revision': manifest['revision'],
                  'gpu_generation_performed': False}, indent=2))
