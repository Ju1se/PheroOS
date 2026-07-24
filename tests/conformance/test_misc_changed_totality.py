from __future__ import annotations

from pathlib import Path

import pytest

from pheroos.conformance import runner
from pheroos.conformance.checks import hybrid_authority_boundary
from pheroos.conformance.report import ConformanceReport
from pheroos.protocol import load_capability_manifest


ROOT = Path(__file__).resolve().parents[2]


def test_manifest_runner_reports_a_declared_check_without_an_implementation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = ROOT / "examples/toy-protocol/capability.json"
    manifest = load_capability_manifest(manifest_path)
    required = next(
        name
        for name in runner.profile_for_manifest(manifest).required_checks
        if name != "manifest_schema"
    )
    monkeypatch.setattr(
        runner,
        "MANIFEST_CHECKS",
        {
            name: check
            for name, check in runner.MANIFEST_CHECKS.items()
            if name != required
        },
    )

    report = runner.run_conformance(manifest_path)

    check = next(item for item in report.checks if item.name == required)
    assert check.ok is False
    assert check.detail == "check implementation is not registered"


def test_conformance_report_rejects_noncanonical_check_values() -> None:
    with pytest.raises(
        TypeError,
        match="conformance report checks must be canonical CheckResult values",
    ):
        ConformanceReport(
            target="target",
            checks=(object(),),  # type: ignore[arg-type]
            profile="profile",
            artifact_digest="sha256:" + ("0" * 64),
        )


def test_hybrid_authority_checker_reports_an_absent_exercise_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = load_capability_manifest(
        ROOT / "examples/hybrid-pheromone-protocol/capability.json"
    )
    monkeypatch.setattr(
        hybrid_authority_boundary,
        "exercise_candidate_id",
        lambda _manifest: None,
    )

    result = hybrid_authority_boundary.check(manifest)

    assert result.ok is False
    assert result.detail == "active_target_candidates"
