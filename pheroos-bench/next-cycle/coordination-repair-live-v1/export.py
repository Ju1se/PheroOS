"""Post-run descriptive export; no inference, threshold changes, or efficacy test."""
import argparse
from collections import Counter
import csv
from hashlib import sha256
import json
from pathlib import Path
import re


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root, output = args.root.resolve(), args.output.resolve()
phase = root / 'campaign/actionability'
records = json.loads((phase / 'records.json').read_text())
completion = json.loads((phase / 'campaign-completion.json').read_text())
process = json.loads((root / 'actionability-process.json').read_text())
assert completion['status'] == 'COMPLETE' and completion['declared'] == completion['executed'] == len(records) == 28
assert not completion['unstarted'] and completion['failure'] is None
assert all(r['status'] == 'VALID_KNOWN' and r['complete_rollout'] for r in records)
assert process['exit_code'] == 3
assert not (root / 'campaign/collaboration').exists()
summable = ('model_calls', 'tool_calls', 'input_tokens', 'output_tokens', 'tokens',
            'control_operations', 'inspection_requests', 'inspection_dispatches',
            'repeated_inspections', 'artifact_reuse', 'settled_receipt_reuse',
            'event_bytes', 'materialized_bytes', 'coordination_request_bytes',
            'prompt_message_exposures', 'repeated_prompt_message_exposures',
            'unknown_calls', 'unknown_tokens', 'elapsed_ns')


def aggregate(rows):
    turns = [t for r in rows for t in r['turns'] if t.get('model_response') is not None]
    counts = {key: sum(r['metrics'][key] for r in rows) for key in summable}
    return dict(episodes=len(rows), public_accepted=sum(r['stop'] == 'public_accepted_submission' for r in rows),
        hidden_objective_successes=sum(r['success'] is True for r in rows),
        successful_families=sorted({r['family'] for r in rows if r['success']}),
        **counts, call_units=counts['model_calls'] + counts['tool_calls'] + counts['control_operations'],
        failure_stages=dict(sum((Counter(r['metrics']['failure_stages']) for r in rows), Counter())),
        output_at_256_token_cap=sum(t['model_response']['completion_tokens'] == 256 for t in turns),
        output_starts_with_agent_envelope_field=sum(bool(re.match(r'^\s*(?:```json\s*)?\{\s*"agent"\s*:', t['model_response']['text'])) for t in turns),
        monetary_cost=None, monetary_cost_status='not_measured_local_inference')


groups = {c: aggregate([r for r in records if r['campaign_component'] == 'capability' and r['condition'] == c])
          for c in ('D0', 'D1', 'D2')}
groups['intervention_probes'] = aggregate([r for r in records if r['campaign_component'] == 'intervention_probe'])
rows = []
for i, record in enumerate(records):
    identity = f"actionability-{i:03d}-{record['arm']}-n{record['n']}-{record['condition']}"
    rows.append(dict(episode=identity, world=record['world_id'], component=record['campaign_component'],
        condition=record['condition'], arm=record['arm'], n=record['n'], status=record['status'],
        public_accepted=record['stop'] == 'public_accepted_submission', success=record['success'],
        stop=record['stop'], **{k: record['metrics'][k] for k in summable},
        monetary_cost=None, monetary_cost_status='not_measured_local_inference', counts_toward_verdict=False))
report = dict(profile='coordination_repair_live_descriptive_v1', counts_toward_verdict=False,
    collection_source_commit=process['source_commit'],
    config_sha256=completion.get('config_sha256') or json.loads((phase / 'freeze.json').read_text())['config_sha256'],
    records_sha256=sha256((phase / 'records.json').read_bytes()).hexdigest(),
    process_elapsed_ns=process['elapsed_ns'], totals=aggregate(records), groups=groups,
    capability_admission=json.loads((phase / 'admission.json').read_text()),
    collaboration=dict(status='UNMEASURED', reason='complete_actionability_not_admitted', episodes=0, model_calls=0,
                       paired_export_emitted=False, method_if_admitted='r_paired_world_mean_v1'),
    notes=['Descriptive counts only: eight fixed development worlds; agents, turns and probes are not independent samples.',
           'Output-cap and leading-agent-field labels are post-run diagnostics, not preregistered efficacy endpoints or causal explanations.',
           'call_units includes model calls, tool calls and control operations; it is not money.',
           'Elapsed episode sums exclude process/model setup; process time includes it. Neither measures parallel scaling.',
           'The monetary_cost CSV cell is empty with an explicit unknown-status column, never zero.',
           'No paired effect is emitted because collaboration was not admitted; that absence is not a null effect.'])
output.mkdir()
with (output / 'summary.json').open('x') as stream:
    json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
    stream.write('\n')
with (output / 'episodes.csv').open('x', newline='') as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
print(json.dumps({'status': 'EXPORTED_DESCRIPTIVE_ONLY', 'episodes': len(rows), 'output': str(output)}))
