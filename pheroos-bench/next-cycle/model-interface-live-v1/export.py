#!/usr/bin/env python3
"""Export the full fixed grid only after independent read-only integrity audit.

No app/model imports. Unstarted/invalid/unknown cells retain null quality/cost.
An incomplete campaign gets all 64 CSV rows but no arm/world effect estimates.
"""
import argparse
from collections import Counter
import csv
from hashlib import sha256
import json
from pathlib import Path

from audit import ARMS, CONFIG_SHA, TOTAL_FIELDS, cell, digest, obj, wire

FIELDS = ['ordinal', 'world_id', 'family', 'seed', 'arm', 'n', 'status', 'complete',
          'public_accepted', 'objective_success', 'output_at_cap', 'validation_stage',
          'citations_origin', 'model_citation_selection_measured', 'max_new_tokens',
          *TOTAL_FIELDS, 'unknown_tokens', 'unknown_calls', 'verification_operations',
          'preparation_tools', 'event_bytes', 'model_prompt_bytes', 'materialized_bytes',
          'coordination_request_bytes', 'elapsed_ns', 'model_elapsed_ns', 'peak_cuda_bytes',
          'monetary_cost', 'monetary_cost_status', 'submitted_answer_json', 'expected_answer_json',
          'prompt_sha256', 'episode_sha256', 'counts_toward_verdict']
RESOURCE_FIELDS = [*TOTAL_FIELDS, 'unknown_tokens', 'unknown_calls', 'verification_operations',
                   'preparation_tools', 'event_bytes', 'model_prompt_bytes', 'materialized_bytes',
                   'coordination_request_bytes', 'elapsed_ns', 'model_elapsed_ns']
QUALITY_FIELDS = ['public_accepted', 'objective_success', 'output_at_cap']


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def csv_save(path, rows, fields):
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build_rows(grid, records, audited):
    record_map = {cell(r): r for r in records}
    if len(record_map) != len(records):
        raise ValueError('duplicate records cannot be exported')
    accounted = {(r['world_id'], r['arm'], r['seed']): r for r in audited}
    rows = []
    for ordinal, item in enumerate(grid):
        key = item['world'], item['arm'], item['seed']
        record = record_map.get(key)
        row = dict.fromkeys(FIELDS)
        row.update(ordinal=ordinal, world_id=item['world'], family=item['world'].split('/')[0],
                   arm=item['arm'], seed=item['seed'], n=1, status='UNSTARTED', complete=False,
                   counts_toward_verdict=False, max_new_tokens=1024 if item['arm'] == 'envelope_1024' else 256,
                   citations_origin='runtime_supplied' if item['arm'] == 'direct_json_256' else 'model_supplied',
                   model_citation_selection_measured=item['arm'] != 'direct_json_256')
        if record:
            for field in ('status', 'complete', *QUALITY_FIELDS, 'prompt_sha256'):
                row[field] = record.get(field)
            row.update({k: record.get('metrics', {}).get(k) for k in RESOURCE_FIELDS if k not in {'model_elapsed_ns'}}
                       if record.get('metrics') else {})
            metrics, response = record.get('metrics') or {}, record.get('response') or {}
            row.update(monetary_cost=metrics.get('monetary_cost'), monetary_cost_status=metrics.get('monetary_cost_status'),
                       model_elapsed_ns=response.get('elapsed_ns'), peak_cuda_bytes=response.get('peak_cuda_bytes'),
                       validation_stage=(record.get('validation') or {}).get('stage'), episode_sha256=digest(record))
            if record.get('submission'):
                row['submitted_answer_json'] = wire(record['submission']['answer'])
            if key in accounted:
                row['expected_answer_json'] = wire(accounted[key]['expected_answer'])
        rows.append(row)
    return rows


def describe(rows):
    base = dict(profile='model_interface_independent_descriptive_export_v1', config_sha256=CONFIG_SHA,
                counts_toward_verdict=False, collaboration_admitted=False,
                independent_unit='world; two seeds are repeated observations within each world',
                declared_cells=64, retained_status_counts=dict(Counter(r['status'] for r in rows)))
    if len(rows) != 64 or any(r['status'] != 'VALID_KNOWN' or r['complete'] is not True for r in rows):
        return dict(**base, status='INVALID', effects=None, arm_summaries=None, world_seed_means=None,
                    reason='No subset quality or resource comparisons from incomplete/unresolved campaign')
    world_means = []
    for world in sorted({r['world_id'] for r in rows}):
        for arm in ARMS:
            group = [r for r in rows if r['world_id'] == world and r['arm'] == arm]
            if len(group) != 2 or len({r['seed'] for r in group}) != 2:
                raise ValueError('world-arm requires exactly two declared seeds')
            means = {k + '_mean': sum(r[k] for r in group) / len(group) for k in (*QUALITY_FIELDS, *RESOURCE_FIELDS)}
            world_means.append(dict(world_id=world, family=world.split('/')[0], arm=arm, repeated_seeds=2, **means))
    arm_summaries = {}
    for arm in ARMS:
        group = [r for r in rows if r['arm'] == arm]
        wgroup = [r for r in world_means if r['arm'] == arm]
        arm_summaries[arm] = dict(episodes=len(group), worlds=len(wgroup),
            counts={k: sum(r[k] for r in group) for k in QUALITY_FIELDS},
            world_mean_rates={k: sum(r[k + '_mean'] for r in wgroup) / len(wgroup) for k in QUALITY_FIELDS},
            resource_totals={k: sum(r[k] for r in group) for k in RESOURCE_FIELDS},
            failure_stages=dict(Counter(r['validation_stage'] for r in group if not r['public_accepted'])),
            wrong_public_accepted=sum(r['public_accepted'] and not r['objective_success'] for r in group),
            monetary_cost=None, monetary_cost_status='not_measured_local_inference')
    contrasts = []
    for a, b in zip(ARMS, ARMS[1:]):
        deltas = []
        for world in sorted({r['world_id'] for r in rows}):
            left = next(r for r in world_means if r['world_id'] == world and r['arm'] == a)
            right = next(r for r in world_means if r['world_id'] == world and r['arm'] == b)
            deltas.append(dict(world_id=world, **{k: right[k + '_mean'] - left[k + '_mean']
                                                for k in (*QUALITY_FIELDS, *RESOURCE_FIELDS)}))
        contrasts.append(dict(a=a, b=b, direction='b_minus_a', independent_worlds=len(deltas), world_differences=deltas,
            paired_world_mean_difference={k: sum(r[k] for r in deltas) / len(deltas) for k in (*QUALITY_FIELDS, *RESOURCE_FIELDS)},
            inference_status='DESCRIPTIVE_ONLY_NO_CONFIDENCE_INTERVAL_OR_CONFIRMATORY_VERDICT'))
    return dict(**base, status='VALID_KNOWN', arm_summaries=arm_summaries, world_seed_means=world_means,
                contrasts=contrasts, effects_status='DESCRIPTIVE_DEVELOPMENT_DIAGNOSTIC',
                limitations=['64 execution cells are eight development worlds, not 64 independent tasks.',
                    'Direct and compact change output responsibility plus citations; compact and envelope change a presentation bundle.',
                    'Only the two envelope arms isolate output allowance under identical messages and adapter.',
                    'Runtime-supplied direct citations do not measure model citation selection.',
                    'No efficacy, heldout, scaling, robustness or previous NOT_ADMITTED reversal follows from this export.',
                    'No R0 method semantics changed; these are raw paired world descriptive means without a confirmatory test.',
                    'CSV empty numeric/boolean cells mean unknown or unstarted, never zero. Monetary cost remains unmeasured.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='Fresh directory outside campaign')
    args = parser.parse_args()
    audit_bytes = args.audit.read_bytes()
    audit = obj(audit_bytes)
    campaign, output = Path(audit['campaign']).resolve(), args.output.resolve()
    if output.exists() or output.is_relative_to(campaign):
        parser.error('export output must be a new directory outside the retained campaign')
    if audit['status'] != 'PASS' or audit['config_sha256'] != CONFIG_SHA:
        parser.error('independent integrity audit must pass for exact configuration')
    for path, expected in audit['input_sha256'].items():
        if sha256(Path(path).read_bytes()).hexdigest() != expected:
            parser.error('an audited input changed; export refused')
    records, grid = obj((campaign / 'records.json').read_bytes()), obj((campaign / 'expected-grid.json').read_bytes())
    rows = build_rows(grid, records, audit['episode_accounting'])
    report = describe(rows)
    report.update(audit_sha256=sha256(audit_bytes).hexdigest(), export_helper_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                  campaign_status=audit['campaign_status'], combined_accounting=audit['combined_accounting'])
    output.mkdir(parents=True)
    csv_save(output / 'episodes.csv', rows, FIELDS)
    save(output / 'summary.json', report)
    if report['status'] == 'VALID_KNOWN':
        csv_save(output / 'world-seed-means.csv', report['world_seed_means'], list(report['world_seed_means'][0]))
    save(output / 'manifest.json', dict(profile='model_interface_independent_export_files_v1',
        files={p.name: sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir()) if p.is_file()},
        audit_sha256=report['audit_sha256'], counts_toward_verdict=False))
    print(wire(dict(status=report['status'], rows=len(rows), output=str(output), counts_toward_verdict=False)))
    return 0 if report['status'] == 'VALID_KNOWN' else 2


if __name__ == '__main__':
    raise SystemExit(main())
