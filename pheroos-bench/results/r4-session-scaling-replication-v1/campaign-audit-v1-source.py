"""Independent, read-only outer campaign audit; no runner/runtime imports."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import time

BENCH = Path('/home/scott/projects/PheroOS/pheroos-bench')
OUT = BENCH / 'results/r4-session-scaling-replication-v1'
OLD = BENCH / 'results/r4-session-scaling-pilot-v1'
DEST = OUT / 'campaign-audit-v1.json'
COUNTERS = ('actual_tokens', 'model_calls', 'tool_calls', 'control_operations', 'reserved_tokens', 'unknown_tokens', 'unknown_calls')
inputs, checks = {}, []

def wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)

def decode(text):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            assert k not in result, 'duplicate JSON key'
            result[k] = v
        return result
    return json.loads(text, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))

def hashed(path):
    result = sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()

def bind(path, expected=None):
    path = Path(path).resolve()
    actual = hashed(path)
    assert expected is None or actual == expected, f'input identity differs: {path}'
    assert str(path) not in inputs or inputs[str(path)] == actual, f'input changed: {path}'
    inputs[str(path)] = actual
    return actual

def read(path):
    bind(path)
    return decode(Path(path).read_text())

def equal(a, b, message):
    if type(a) in (set, Counter):
        assert type(a) is type(b) and a == b, message
        return
    assert wire(a) == wire(b), message

def integer(value):
    assert type(value) is int and value >= 0, 'exact nonnegative integer required'
    return value

def checked(name):
    checks.append(dict(check=name, status='PASS'))

def accounting(summary, order):
    source = summary['source_accounting']
    assert type(source) is list and len(source) == 264
    for index, (row, identity) in enumerate(zip(source, order)):
        equal(row['row_index'], index, 'accounting row index differs')
        equal({k: row[k] for k in ('condition_id', 'world_id')}, identity, 'accounting order differs')
    totals = {}
    for key in COUNTERS:
        values, missing = [], []
        for index, row in enumerate(source):
            reported = row['reported_accounting']
            value = None if reported is None else reported.get(key)
            if value is None:
                missing.append(index)
            else:
                values.append(integer(value))
        totals[key] = dict(known_subtotal=sum(values), known_rows=len(values), missing_row_indices=missing)
    return dict(source_status=summary['status'], source_accounting=source, reported_subtotals=totals)

def validate_clock(clock):
    for key in ('realtime_ns', 'monotonic_ns', 'boottime_ns'):
        assert clock[key] is None and key == 'boottime_ns' or integer(clock[key]) >= 0
    equal(datetime.fromtimestamp(clock['realtime_ns'] / 1_000_000_000, timezone.utc).isoformat(), clock['utc'], 'clock UTC binding differs')

def audit():
    report = dict(audit_method='r4_full_grid_campaign_independent_audit_v1', audit_status='AUDIT_ERROR',
        counts_toward_verdict=False, source_status=None, raw_inner_audit_status='NOT_PERFORMED_BY_THIS_AUDIT',
        checks=checks, generated_model_calls=0, started_utc=datetime.now(timezone.utc).isoformat(),
        auditor_interpreter=sys.executable, auditor_python=sys.version,
        scope='Outer campaign identity, retained summary accounting, diagnostic clocks and grid order only. No episode/receipt/SQLite/policy/evaluator acceptance.')
    started = time.monotonic_ns()
    try:
        frozen, summary = read(OUT / 'campaign-freeze.json'), read(OUT / 'campaign-summary.json')
        report['source_status'] = summary['status']
        hashes = read(OUT / 'campaign-artifact-hashes.json')
        equal(set(hashes), {'campaign-freeze.json', 'campaign-summary.json', 'clock-observations.jsonl', 'original-accounting.json'}, 'outer artifact hash set differs')
        for path, expected in hashes.items():
            bind(OUT / path, expected)
        config = read(BENCH / 'scaling-full-grid-replication-v1.json')
        equal(frozen['config'], config, 'campaign config drift')
        equal([frozen['method_version'], summary['method_version'], config['method_version']], ['r4_full_grid_replication_v1'] * 3, 'campaign method differs')
        equal([config['counts_toward_verdict'], frozen['counts_toward_verdict'], summary['counts_toward_verdict']], [False] * 3, 'pilot flag differs')
        equal([summary['campaign_id'], config['campaign_id'], OUT.name], [OUT.name] * 3, 'campaign identity differs')
        equal([config['attempts'], summary['attempts'], summary['attempted']], [1, 1, True], 'attempt count differs')
        equal([summary['status'], summary['collection_status'], summary['original_status'], summary['errors']], ['REPLICATION_COLLECTED_PENDING_INDEPENDENT_AUDIT', 'PILOT_COMPLETE', 'INVALID_ABORT', []], 'outer disposition differs')
        assert 'raw_accounting_recovery' not in summary
        equal(summary['collection_directory'], str(OUT / 'collection'), 'fresh collection directory differs')
        assert not (OUT / 'collection').is_symlink()
        checked('outer hashes, pilot identity, one recorded fresh attempt, terminal collection disposition')

        expected_original = {str(OLD / k): v for k, v in config['original_sha256'].items()}
        expected_original[str(BENCH / config['original_config'])] = config['original_config_sha256']
        audit_path = BENCH / config['original_audit']['path']
        expected_original[str(audit_path)] = config['original_audit']['sha256']
        equal(frozen['original_artifact_sha256'], expected_original, 'original binding closure differs')
        for path, expected in expected_original.items():
            bind(path, expected)
        old_summary, old_freeze = read(OLD / 'summary.json'), read(OLD / 'freeze.json')
        old_audit = read(audit_path)
        equal([old_audit['audit_method'], old_audit['audit_status'], old_audit['source_status'], old_audit['inference_status'], old_audit['counts_toward_verdict'], old_audit['original_evidence_unchanged']],
            ['r4_session_scaling_abort_audit_v1', 'ACCOUNTING_AND_ABORT_INTEGRITY_PASS', 'INVALID_ABORT', 'FULL_GRID_INVALID_NO_USABLE_PAIRED_EXPORT', False, True], 'original independent audit gate differs')
        equal(old_audit['source_config'], old_freeze['config'], 'original audited config differs')
        equal(old_audit['retained_source_accounting'], old_summary['source_accounting'], 'original audited accounting differs')
        for relative, expected in config['original_sha256'].items():
            equal(old_audit['evidence_sha256'][str(OLD / relative)], expected, 'original audit evidence binding differs')
        equal([old_summary['status'], old_summary['reason'], old_summary['aborted_row_indices']], ['INVALID_ABORT', 'source_abort', list(range(204, 264))], 'original abort reclassified')
        failed = read(OLD / config['failed_episode'])
        equal([failed['status'], failed['condition_id'], failed['world_id']], ['INVALID_ABORT', config['failed_condition'], config['failed_world']], 'original failed row replaced')
        checked('original INVALID evidence and exact positive audit-of-INVALID prerequisite retained')

        inner_freeze = read(OUT / 'collection/freeze.json')
        equal(frozen['original_freeze'], old_freeze, 'embedded original freeze differs')
        equal(inner_freeze, old_freeze, 'inner freeze differs')
        equal(inputs[str(OLD / 'freeze.json')], inputs[str(OUT / 'collection/freeze.json')], 'inner freeze is not byte-identical')
        equal(read(BENCH / config['original_config']), old_freeze['config'], 'original config contents differ')
        assert len(frozen['wrapper_source_sha256']) == 4
        equal({Path(p).name for p in frozen['wrapper_source_sha256']}, {'run_scaling_replication.py', 'scaling-full-grid-replication-v1.json', 'SCALING-replication-v1-contract.md', 'test_scaling_replication.py'}, 'campaign source set differs')
        for path, expected in {**frozen['wrapper_source_sha256'], **old_freeze['source_sha256']}.items():
            bind(path, expected)
        model_files = 0
        for name, manifest in old_freeze['model_manifests'].items():
            root = Path(config['model_paths'][name])
            equal(read(root / 'manifest.json'), manifest, 'model manifest binding differs')
            for relative, expected in manifest['sha256'].items():
                bind(root / relative, expected)
                model_files += 1
        checked('byte-identical inner freeze/config, four wrapper files, 641 current source identities and 19 model-file hashes')

        order, original_order = read(OUT / 'collection/order.json'), read(OLD / 'order.json')
        equal(order, original_order, 'seeded order differs')
        equal(inputs[str(OUT / 'collection/order.json')], inputs[str(OLD / 'order.json')], 'order bytes differ')
        inner_config = old_freeze['config']
        assert len(inner_config['conditions']) == 66 and len(inner_config['worlds']) == 4 and inner_config['steps'] == 32
        expected_grid = {(c['id'], w) for c in inner_config['conditions'] for w in inner_config['worlds']}
        assert len(order) == 264 and len(expected_grid) == 264
        equal(Counter((r['condition_id'], r['world_id']) for r in order), Counter(expected_grid), 'full Cartesian order differs')
        inner_summary = read(OUT / 'collection/summary.json')
        equal([inner_summary['status'], inner_summary['n_episodes'], inner_summary['n_worlds'], inner_summary['counts_toward_verdict']], ['PILOT_COMPLETE', 264, 4, False], 'new declared full grid differs')
        old_part, new_part = accounting(old_summary, order), accounting(inner_summary, order)
        equal(summary['original_accounting'], old_part, 'inline original accounting differs')
        equal(read(OUT / 'original-accounting.json'), old_part, 'retained original accounting differs')
        parts = summary['accounting']
        equal(parts['original'], old_part, 'combined original accounting differs')
        equal(parts['replication'], new_part, 'combined replication accounting differs')
        combined = {}
        for key in COUNTERS:
            a, b = old_part['reported_subtotals'][key], new_part['reported_subtotals'][key]
            equal(a['missing_row_indices'], list(range(205, 264)), 'original missing costs relabeled')
            equal(b['missing_row_indices'], [], 'replication accounting missing')
            combined[key] = dict(known_subtotal=a['known_subtotal'] + b['known_subtotal'], unavailable_campaigns=[], missing_rows=dict(original=a['missing_row_indices'], replication=[]))
        equal(parts['across_attempt_reported_subtotals'], combined, 'cross-campaign subtotal differs')
        assert parts['monetary_cost'] is None
        checked('same full 264-position grid and independent reconciliation of both reported accounting tables, preserving 59 original null rows')

        clock_path = OUT / 'clock-observations.jsonl'
        samples = [decode(line) for line in clock_path.read_text().splitlines()]
        clock = summary['clock_observer']
        equal([clock['status'], clock['joined'], clock['errors'], clock['period_seconds'], clock['max_samples']], ['OBSERVED', True, [], 5, 20000], 'observer disposition differs')
        equal(config['clock_observer'], dict(period_seconds=5, max_samples=20000), 'observer bounds differ')
        equal([clock['samples'], clock['serialized_bytes']], [len(samples), clock_path.stat().st_size], 'observer accounting differs')
        assert 2 <= len(samples) <= 20000
        equal([s['sequence'] for s in samples], list(range(len(samples))), 'clock sequence differs')
        equal([s['kind'] for s in samples], ['startup'] + ['periodic'] * (len(samples) - 2) + ['finish'], 'observer lifecycle differs')
        gaps, divergence, boot_divergence = [], [], []
        for i, sample in enumerate(samples):
            validate_clock(sample)
            equal(set(sample), {'sequence', 'kind', 'utc', 'realtime_ns', 'monotonic_ns', 'boottime_ns'} | ({'realtime_minus_monotonic_interval_ns'} if i else set()), 'clock sample schema differs')
            if i:
                previous = samples[i - 1]
                interval = sample['monotonic_ns'] - previous['monotonic_ns']
                integer(interval)
                delta = sample['realtime_ns'] - previous['realtime_ns'] - interval
                equal(sample['realtime_minus_monotonic_interval_ns'], delta, 'reported clock interval differs')
                gaps.append(interval)
                divergence.append(delta)
                if sample['boottime_ns'] is not None and previous['boottime_ns'] is not None:
                    boot_divergence.append(sample['boottime_ns'] - previous['boottime_ns'] - interval)
        equal(clock['maximum_absolute_realtime_minus_monotonic_interval_ns'], max(map(abs, divergence)), 'maximum clock divergence differs')
        equal(clock['first'], {k: v for k, v in samples[0].items() if k not in ('sequence', 'kind')}, 'startup summary differs')
        equal(clock['last'], {k: v for k, v in samples[-1].items() if k not in ('sequence', 'kind')}, 'finish summary differs')
        timing = summary['campaign_timing']
        validate_clock(timing['started']); validate_clock(timing['finished']); validate_clock(frozen['created_clocks'])
        for key in ('monotonic', 'realtime', 'boottime'):
            delta = timing['finished'][key + '_ns'] - timing['started'][key + '_ns']
            equal(timing[key + '_elapsed_ns'], delta, 'campaign clock duration differs')
            integer(delta)
        assert timing['started']['monotonic_ns'] <= frozen['created_clocks']['monotonic_ns'] <= samples[0]['monotonic_ns'] <= samples[-1]['monotonic_ns'] <= timing['finished']['monotonic_ns']
        checked('all 2164 clock samples, serialized bytes, lifecycle, exact interval arithmetic and outer timing reconcile')

        report.update(original_status=old_summary['status'], collection_status=inner_summary['status'],
            identity=dict(original_freeze_sha256=inputs[str(OLD / 'freeze.json')], collection_freeze_sha256=inputs[str(OUT / 'collection/freeze.json')],
                original_audit_sha256=config['original_audit']['sha256'], inner_source_files=len(old_freeze['source_sha256']), model_files=model_files,
                models={k: {field: v[field] for field in ('repository', 'revision', 'precision', 'quantization')} for k, v in old_freeze['model_manifests'].items()},
                original_base_commit=old_freeze['bench_base_commit'], original_source_identity=old_freeze['source_identity']),
            grid=dict(conditions=66, worlds=4, rows=264, global_turn_cap=32, order_byte_identical=True, accounting_order_matches=True),
            accounting=dict(original=old_part['reported_subtotals'], replication=new_part['reported_subtotals'], across_attempt_reported_subtotals=combined, monetary_cost=None,
                interpretation='Reported summary counters reconcile independently. The 59 original unstarted rows remain null, so combined values are known subtotals, not complete cost totals. This audit does not verify raw receipt/ledger accounting.'),
            clock=dict(samples=len(samples), periodic_samples=len(samples)-2, serialized_bytes=clock_path.stat().st_size, period_seconds=5, max_samples=20000,
                startup_utc=samples[0]['utc'], finish_utc=samples[-1]['utc'], joined_reported=clock['joined'], errors=[],
                observed_monotonic_elapsed_ns=samples[-1]['monotonic_ns']-samples[0]['monotonic_ns'],
                minimum_sample_interval_ns=min(gaps), maximum_sample_interval_ns=max(gaps), maximum_absolute_realtime_minus_monotonic_interval_ns=max(map(abs, divergence)),
                maximum_absolute_boottime_minus_monotonic_interval_ns=max(map(abs, boot_divergence)) if boot_divergence else None,
                interpretation='Bounded sampled diagnostics only; no anomaly threshold is applied. Sampling does not prove clock continuity between samples or establish environmental cause. Joined is a retained wrapper observation.'),
            campaign_timing=timing,
            limitations=['This audit does not reopen or validate inner episode SQLite databases, raw receipts, authority decisions, prompts, evaluator results or paired exports.',
                'The wrapper and its observed thread lifecycle remain trusted local execution records. One recorded attempt and an unchanged grid do not prove the absence of unrecorded activity.',
                'Observer sampling and identity checks are separate common campaign control overhead, outside unchanged per-episode call_units. Timing is neither GPU time nor monetary cost.',
                'The original campaign remains INVALID_ABORT. Repeating the same fixture worlds adds no independent worlds or confirmatory evidence.',
                'R4 acceptance and R5 execution still require the separate inner audit and explicit root gate decision.'],
            required_next_gate='Independent full-grid inner raw/SQLite/authority/identity/accounting and export audit, followed by root R4 decision; R5 is not authorized by this report.')
        for path, expected in inputs.items():
            assert hashed(path) == expected, f'input changed during audit: {path}'
        checked('every audited input remains byte-identical after review')
        report.update(audit_status='CAMPAIGN_INTEGRITY_PASS', original_evidence_unchanged=True, engineering_gate='OUTER_CAMPAIGN_ONLY_PASS_INNER_AUDIT_PENDING')
    except Exception as error:
        report.update(audit_status='AUDIT_MISMATCH', engineering_gate='NOT_ACCEPTED', error=f'{type(error).__name__}: {error}')
    report.update(input_sha256=inputs, audit_source=str(Path(__file__).resolve()), audit_source_sha256=hashed(__file__),
        finished_utc=datetime.now(timezone.utc).isoformat(), elapsed_ns=time.monotonic_ns()-started)
    with DEST.open('x') as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps({k: report.get(k) for k in ('audit_status', 'error', 'clock', 'elapsed_ns')}, indent=2))
    return 0 if report['audit_status'] == 'CAMPAIGN_INTEGRITY_PASS' else 2

if __name__ == '__main__':
    assert not DEST.exists(), 'additive exclusive report required'
    raise SystemExit(audit())
