from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.check_engineering_baseline import (
    ABSOLUTE_MINIMA,
    BASELINE_PATH,
    BASELINE_VERSION,
    baseline_failures,
    build_observation,
    load_baseline,
    refresh_regressions,
    render_baseline,
    write_baseline,
)


ROOT = Path(__file__).resolve().parents[2]


def test_checked_engineering_baseline_matches_current_tree() -> None:
    baseline = load_baseline()
    observation = build_observation()

    assert baseline["version"] == BASELINE_VERSION
    assert baseline_failures(baseline, observation) == []


def test_baseline_locks_exact_roots_and_one_way_quality_metrics() -> None:
    baseline = load_baseline()
    observation = deepcopy(baseline["observation"])

    observation["quality"]["ruff"]["findings_total"] += 1
    observation["quality"]["ruff"]["by_code"]["WP00"] = 1
    observation["quality"]["mypy"]["errors"] += 1
    observation["quality"]["mypy"]["by_code"]["wp00"] = 1
    observation["quality"]["complexity"]["over_threshold_count"] += 1
    observation["dependencies"]["runtime_count"] += 1
    observation["dependencies"]["forbidden_core_import_count"] += 1
    observation["tests"]["collected"] -= 1
    first_schema = sorted(observation["schemas"])[0]
    observation["schemas"][first_schema]["sha256"] = "0" * 64

    failures = baseline_failures(baseline, observation)

    assert any("quality.ruff.findings_total" in failure for failure in failures)
    assert any("quality.ruff.by_code.WP00" in failure for failure in failures)
    assert any("quality.mypy.errors" in failure for failure in failures)
    assert any("quality.mypy.by_code.wp00" in failure for failure in failures)
    assert any(
        "quality.complexity.over_threshold_count" in failure for failure in failures
    )
    assert any("dependencies.runtime_count" in failure for failure in failures)
    assert any(
        "dependencies.forbidden_core_import_count" in failure for failure in failures
    )
    assert any("tests.collected" in failure for failure in failures)
    assert any("schemas" in failure for failure in failures)


def test_baseline_renderer_and_writer_are_byte_deterministic(
    tmp_path: Path,
) -> None:
    observation = load_baseline()["observation"]
    reason = "deterministic WP-00 test fixture"

    first = render_baseline(observation, reason=reason)
    second = render_baseline(deepcopy(observation), reason=reason)
    assert first == second

    target = tmp_path / "baseline.json"
    write_baseline(target, observation=observation, reason=reason)
    first_bytes = target.read_bytes()
    write_baseline(target, observation=observation, reason=reason)
    assert target.read_bytes() == first_bytes == first


@pytest.mark.parametrize("reason", ["", "   "])
def test_baseline_writer_requires_nonblank_reason(
    tmp_path: Path,
    reason: str,
) -> None:
    with pytest.raises(ValueError, match="reason"):
        write_baseline(
            tmp_path / "baseline.json",
            observation=load_baseline()["observation"],
            reason=reason,
        )


def test_cli_write_requires_reason_and_check_is_clean() -> None:
    before = BASELINE_PATH.read_bytes()
    missing_reason = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/check_engineering_baseline.py"),
            "--write",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert missing_reason.returncode != 0
    assert "--reason" in missing_reason.stderr

    checked = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/check_engineering_baseline.py"),
            "--check",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert BASELINE_PATH.read_bytes() == before


def test_known_limitations_are_explicitly_draft_characterizations() -> None:
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    limitations = {item["id"]: item for item in payload["known_limitations"]}

    assert set(limitations) == {
        "WP00-CHAR-001",
        "WP00-CHAR-002",
        "WP00-CHAR-003",
    }
    assert all(item["status"] == "characterized_draft" for item in limitations.values())
    assert limitations["WP00-CHAR-001"]["replacement_wp"] == "WP-03"
    assert limitations["WP00-CHAR-002"]["replacement_wp"] == "WP-04"
    assert limitations["WP00-CHAR-003"]["replacement_wp"] == "WP-02"


@pytest.mark.parametrize(
    "payload",
    (
        '{"version": NaN}',
        '{"version": Infinity}',
        '{"version": "first", "version": "second"}',
    ),
)
def test_baseline_loader_rejects_nonfinite_values_and_duplicate_keys(
    tmp_path: Path,
    payload: str,
) -> None:
    target = tmp_path / "malformed-baseline.json"
    target.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError):
        load_baseline(target)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True])
def test_in_memory_baseline_metrics_fail_closed(value: object) -> None:
    baseline = load_baseline()
    baseline["observation"]["quality"]["ruff"]["findings_total"] = value

    with pytest.raises(ValueError, match="non-negative integer"):
        baseline_failures(baseline, load_baseline()["observation"])


def test_hard_test_floor_cannot_be_relaxed_in_the_json() -> None:
    baseline = load_baseline()
    baseline["observation"]["tests"]["collected"] = (
        ABSOLUTE_MINIMA["tests.collected"] - 1
    )

    failures = baseline_failures(baseline, load_baseline()["observation"])

    assert any("absolute floor" in failure for failure in failures)


def test_hard_per_code_ceiling_cannot_be_relaxed_in_the_json() -> None:
    baseline = load_baseline()
    baseline["observation"]["quality"]["ruff"]["by_code"]["WP00"] = 1

    failures = baseline_failures(baseline, load_baseline()["observation"])

    assert any("absolute code ceiling" in failure for failure in failures)


def test_refresh_can_migrate_an_older_artifact_to_a_tighter_hard_floor() -> None:
    baseline = load_baseline()
    baseline["observation"]["tests"]["collected"] = (
        ABSOLUTE_MINIMA["tests.collected"] - 1
    )

    assert refresh_regressions(baseline, load_baseline()["observation"]) == []
