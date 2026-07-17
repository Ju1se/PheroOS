from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.check_reference_performance as performance

from scripts.check_reference_performance import (
    BASELINE_VERSION,
    COMMIT_TCK_V1_WARM_CLOCK,
    COMMIT_TCK_V1_WARM_FULL_SAMPLES,
    COMMIT_TCK_V1_WARM_QUICK_SAMPLES,
    HARD_CEILINGS_RATIOS,
    HARD_CEILINGS_SECONDS,
    _commit_tck_v1_warm,
    _process_tree_cpu_seconds,
    _validate_locked_budgets,
)


ROOT = Path(__file__).resolve().parents[2]


def test_reference_performance_budget_is_complete_and_locked() -> None:
    payload = json.loads(
        (ROOT / "docs/process/reference-performance-v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert payload["version"] == BASELINE_VERSION
    _validate_locked_budgets(payload)
    assert set(payload["budget_seconds"]) == set(HARD_CEILINGS_SECONDS)
    assert set(payload["budget_ratios"]) == set(HARD_CEILINGS_RATIOS)
    assert payload["measurement_clocks"] == {
        "audit_baseline_commit_tck_v1_warm": "wall",
        "post_hardening_commit_tck_v1_warm": COMMIT_TCK_V1_WARM_CLOCK,
        "budget_commit_tck_v1_warm": COMMIT_TCK_V1_WARM_CLOCK,
        "historical_and_post_hardening_commit_tck_v1_are_directly_comparable": False,
    }
    assert payload["policy"]["third_party_conformance_requirement"] is False
    assert payload["policy"]["closed_scope_active_authority_records_after_retire"] == 0
    assert payload["policy"]["commit_tck_v1_warm_clock"] == (
        COMMIT_TCK_V1_WARM_CLOCK
    )
    assert payload["policy"]["commit_tck_v1_warm_quick_samples"] == (
        COMMIT_TCK_V1_WARM_QUICK_SAMPLES
    )
    assert payload["policy"]["commit_tck_v1_warm_full_samples"] == (
        COMMIT_TCK_V1_WARM_FULL_SAMPLES
    )


def test_process_tree_clock_includes_parent_and_completed_children(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = SimpleNamespace(
        user=1.0,
        system=2.0,
        children_user=3.0,
        children_system=4.0,
    )
    monkeypatch.setattr(performance.os, "times", lambda: snapshot)

    assert _process_tree_cpu_seconds() == 10.0


def test_tck_warm_uses_full_runs_and_median_process_tree_cpu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pheroos.conformance.commit_tck as commit_tck

    calls: list[tuple[object, ...]] = []

    def run(*args: object, **kwargs: object) -> SimpleNamespace:
        assert kwargs == {}
        calls.append(args)
        return SimpleNamespace(ok=True)

    clock = iter((10.0, 13.0, 20.0, 21.0, 30.0, 32.0))
    monkeypatch.setattr(commit_tck, "run_commit_tck", run)
    monkeypatch.setattr(
        performance,
        "_process_tree_cpu_seconds",
        lambda: next(clock),
    )

    assert _commit_tck_v1_warm(samples=3) == 2.0
    assert calls == [(), (), (), ()]


@pytest.mark.parametrize("samples", (0, -1, True, 1.5))
def test_tck_warm_rejects_invalid_sample_counts(
    samples: object,
) -> None:
    with pytest.raises(
        ValueError,
        match="Commit TCK v1 performance samples must be positive",
    ):
        _commit_tck_v1_warm(samples=samples)  # type: ignore[arg-type]
