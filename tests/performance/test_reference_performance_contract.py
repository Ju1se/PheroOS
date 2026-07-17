from __future__ import annotations

import json
from pathlib import Path

from scripts.check_reference_performance import (
    BASELINE_VERSION,
    HARD_CEILINGS_RATIOS,
    HARD_CEILINGS_SECONDS,
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
    assert payload["policy"]["third_party_conformance_requirement"] is False
    assert payload["policy"]["closed_scope_active_authority_records_after_retire"] == 0
