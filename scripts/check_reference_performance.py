#!/usr/bin/env python3
"""Measure locked PheroOS reference-performance and lifecycle budgets.

The measurements are implementation regression gates, not third-party ABI
requirements.  Budget ceilings are duplicated in code so replacing the JSON
baseline with slower numbers cannot silently relax CI.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from hashlib import sha256
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "docs" / "process" / "reference-performance-v1.json"
BASELINE_VERSION = "pheroos-reference-performance-v1"
HARD_CEILINGS_SECONDS = {
    "governance_cold_import_median": 0.120,
    "manifest_load_validate_median": 0.020,
    "commit_tck_v1_warm": 3.200,
    "commit_tck_v2": 15.000,
    "trace_append_10000": 2.500,
    "authority_retire_10000": 2.500,
}
HARD_CEILINGS_RATIOS = {
    "diffusion_double_size_ratio": 3.0,
}
COMMIT_TCK_V1_WARM_CLOCK = "process-tree-cpu"
COMMIT_TCK_V1_WARM_QUICK_SAMPLES = 3
COMMIT_TCK_V1_WARM_FULL_SAMPLES = 5


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="use fewer statistical samples while retaining every budget",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    baseline = _load_baseline()
    _validate_locked_budgets(baseline)
    observed = measure_reference_performance(quick=args.quick)
    failures = _budget_failures(observed, baseline)
    payload = {
        "version": BASELINE_VERSION,
        "ok": not failures,
        "observed": observed,
        "failures": failures,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for name, value in observed.items():
            print(f"{name}: {value:.6f}")
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
    return 1 if args.check and failures else 0


def measure_reference_performance(*, quick: bool = False) -> dict[str, float]:
    samples = 3 if quick else 7
    measurements: dict[str, float] = {}
    measurements["governance_cold_import_median"] = _cold_import_median(samples)
    measurements["manifest_load_validate_median"] = _manifest_median(
        5 if quick else 15
    )
    measurements["commit_tck_v1_warm"] = _commit_tck_v1_warm(
        samples=(
            COMMIT_TCK_V1_WARM_QUICK_SAMPLES
            if quick
            else COMMIT_TCK_V1_WARM_FULL_SAMPLES
        )
    )
    measurements["commit_tck_v2"] = _commit_tck_v2()
    measurements["trace_append_10000"] = _trace_append_10000()
    measurements["authority_retire_10000"] = _authority_retire_10000()
    measurements["diffusion_double_size_ratio"] = _diffusion_scaling_ratio(
        small=96 if quick else 160
    )
    return measurements


def _cold_import_median(samples: int) -> float:
    code = (
        "from time import perf_counter;"
        "start=perf_counter();"
        "import pheroos.governance;"
        "print(perf_counter()-start)"
    )
    values = []
    for _ in range(samples):
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        values.append(float(completed.stdout.strip()))
    return statistics.median(values)


def _manifest_median(samples: int) -> float:
    from pheroos.protocol import (
        load_capability_manifest,
        validate_capability_manifest,
    )

    path = ROOT / "examples" / "hybrid-pheromone-protocol" / "capability.json"
    values = []
    for _ in range(samples):
        started = perf_counter()
        manifest = load_capability_manifest(path)
        diagnostics = validate_capability_manifest(manifest)
        elapsed = perf_counter() - started
        if diagnostics:
            raise RuntimeError("reference manifest no longer validates")
        values.append(elapsed)
    return statistics.median(values)


def _commit_tck_v1_warm(*, samples: int) -> float:
    from pheroos.conformance.commit_tck import run_commit_tck

    if type(samples) is not int or samples < 1:
        raise ValueError("Commit TCK v1 performance samples must be positive")
    first = run_commit_tck()
    if not first.ok:
        raise RuntimeError("Commit TCK v1 reference adapter failed")
    values = []
    for _ in range(samples):
        started = _process_tree_cpu_seconds()
        report = run_commit_tck()
        elapsed = _process_tree_cpu_seconds() - started
        if not report.ok:
            raise RuntimeError("Commit TCK v1 reference adapter failed")
        values.append(elapsed)
    return statistics.median(values)


def _process_tree_cpu_seconds() -> float:
    """Return CPU seconds consumed by this process and completed children."""

    snapshot = os.times()
    return (
        snapshot.user
        + snapshot.system
        + snapshot.children_user
        + snapshot.children_system
    )


def _commit_tck_v2() -> float:
    from pheroos.conformance.commit_tck_v2 import run_commit_tck_v2

    started = perf_counter()
    report = run_commit_tck_v2()
    elapsed = perf_counter() - started
    if not report.ok:
        raise RuntimeError("Commit TCK v2 public adapter failed")
    return elapsed


def _trace_append_10000() -> float:
    from pheroos.trace import InMemoryTraceStore, TraceEvent

    store = InMemoryTraceStore()
    events = tuple(
        TraceEvent(
            event_type="ext.performance",
            protocol_id="protocol:performance",
            target="decision:performance",
            reason="reference append budget",
            lineage={"sequence": index},
        )
        for index in range(10_000)
    )
    started = perf_counter()
    for event in events:
        store.append(event)
    elapsed = perf_counter() - started
    if len(store.records) != 10_000:
        raise RuntimeError("TraceStore append benchmark lost records")
    return elapsed


def _authority_retire_10000() -> float:
    from pheroos.governance._authority.ledger import InMemoryGovernanceStateStore

    store = InMemoryGovernanceStateStore()
    scopes = tuple(
        "sha256:" + sha256(f"performance-scope:{index}".encode()).hexdigest()
        for index in range(10_000)
    )
    started = perf_counter()
    for scope_ref in scopes:
        store.retire(scope_ref)
    elapsed = perf_counter() - started
    if store.active_domain_count != 0 or store.retained_authority_record_count != 0:
        raise RuntimeError("authority retirement retained an active object graph")
    if store.tombstone_count != 10_000:
        raise RuntimeError("authority retirement lost replay tombstones")
    return elapsed


def _diffusion_scaling_ratio(*, small: int) -> float:
    small_elapsed = _median_runtime(lambda: _diffuse_chain(small), samples=3)
    large_elapsed = _median_runtime(lambda: _diffuse_chain(small * 2), samples=3)
    if small_elapsed <= 0:
        raise RuntimeError("diffusion scaling timer has no resolution")
    return large_elapsed / small_elapsed


def _diffuse_chain(size: int) -> None:
    from pheroos.governance.pheromone import (
        PheromoneDiffusionPolicy,
        PheromoneEdge,
        PheromoneNeighborhood,
        PheromonePolicy,
        PheromoneSubject,
        PheromoneTrail,
        diffuse_pheromone_trails,
    )

    target = "decision:performance"
    candidate = "candidate:performance"
    subjects = [
        PheromoneSubject("route", f"route:{index}", candidate, target)
        for index in range(size)
    ]
    edges = [
        PheromoneEdge(
            "route",
            f"route:{index}",
            "route",
            f"route:{index + 1}",
            attenuation=1.0,
        )
        for index in range(size - 1)
    ]
    trail = PheromoneTrail(
        candidate_id=candidate,
        strength=1.0,
        subject_type="route",
        subject_id="route:0",
        target=target,
        kind="positive",
        source_id="agent:performance",
        source_role="scout",
        evidence_id="evidence:performance",
        provenance="urn:pheroos:performance",
        trace_event_id="trace:performance:root",
    )
    result = diffuse_pheromone_trails(
        [trail],
        PheromoneNeighborhood(subjects=subjects, edges=edges),
        PheromonePolicy(
            enabled=True,
            max_strength=10.0,
            per_source_cap=float(size * 2),
            per_round_deposit_cap=float(size * 2),
            scored_subject_types=["route"],
        ),
        PheromoneDiffusionPolicy(
            enabled=True,
            max_hops=size,
            attenuation=1.0,
        ),
        target=target,
    )
    if len(result) != size:
        raise RuntimeError("diffusion scaling benchmark did not visit the chain")


def _median_runtime(operation: Callable[[], None], *, samples: int) -> float:
    values = []
    for _ in range(samples):
        started = perf_counter()
        operation()
        values.append(perf_counter() - started)
    return statistics.median(values)


def _load_baseline() -> dict[str, Any]:
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != BASELINE_VERSION:
        raise RuntimeError("reference performance baseline version is invalid")
    return payload


def _validate_locked_budgets(payload: dict[str, Any]) -> None:
    seconds = payload.get("budget_seconds")
    ratios = payload.get("budget_ratios")
    if not isinstance(seconds, dict) or set(seconds) != set(HARD_CEILINGS_SECONDS):
        raise RuntimeError("reference performance time budgets are incomplete")
    if not isinstance(ratios, dict) or set(ratios) != set(HARD_CEILINGS_RATIOS):
        raise RuntimeError("reference performance ratio budgets are incomplete")
    for name, ceiling in HARD_CEILINGS_SECONDS.items():
        value = seconds[name]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise RuntimeError(f"reference performance budget is invalid: {name}")
        if value > ceiling:
            raise RuntimeError(
                f"reference performance budget exceeds locked ceiling: {name}"
            )
    for name, ceiling in HARD_CEILINGS_RATIOS.items():
        value = ratios[name]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise RuntimeError(f"reference performance ratio is invalid: {name}")
        if value > ceiling:
            raise RuntimeError(
                f"reference performance ratio exceeds locked ceiling: {name}"
            )
    policy = payload.get("policy")
    if not isinstance(policy, dict):
        raise RuntimeError("reference performance policy is missing")
    if policy.get("commit_tck_v1_warm_clock") != COMMIT_TCK_V1_WARM_CLOCK:
        raise RuntimeError("Commit TCK v1 performance clock policy is invalid")
    if (
        policy.get("commit_tck_v1_warm_quick_samples")
        != COMMIT_TCK_V1_WARM_QUICK_SAMPLES
        or policy.get("commit_tck_v1_warm_full_samples")
        != COMMIT_TCK_V1_WARM_FULL_SAMPLES
    ):
        raise RuntimeError("Commit TCK v1 performance sample policy is invalid")


def _budget_failures(
    observed: dict[str, float],
    baseline: dict[str, Any],
) -> list[str]:
    failures = []
    budgets = {**baseline["budget_seconds"], **baseline["budget_ratios"]}
    for name in sorted(budgets):
        value = observed[name]
        budget = budgets[name]
        if value > budget:
            failures.append(f"{name}={value:.6f} exceeds {budget:.6f}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
