from __future__ import annotations

import json
from pathlib import Path

import pytest

from pheroos.conformance import run_conformance, run_source_conformance
from pheroos.conformance.runner import MANIFEST_CHECKS


ROOT = Path(__file__).resolve().parents[2]


def test_manifest_conformance_executes_only_active_profile_checks() -> None:
    report = run_conformance(ROOT / "examples/toy-protocol")
    names = {check.name for check in report.checks}

    assert report.profile == "pheroos-core-v1"
    assert "pheromone_behavior" not in names
    assert "hybrid_trace_contract" not in names
    assert "domain_neutrality_public_core" not in names


def test_ignored_root_parameter_is_a_warning_compatibility_alias() -> None:
    target = ROOT / "examples/toy-protocol"

    with pytest.warns(DeprecationWarning, match="run_source_conformance"):
        legacy = run_conformance(target, root=ROOT)
    canonical = run_conformance(target)

    assert legacy.to_dict() == canonical.to_dict()


def test_runner_converts_check_exceptions_and_continues(monkeypatch: object) -> None:
    def explode(manifest: object) -> object:
        del manifest
        raise RuntimeError("controlled failure")

    monkeypatch.setitem(MANIFEST_CHECKS, "candidate_declaration", explode)  # type: ignore[attr-defined]
    report = run_conformance(ROOT / "examples/toy-protocol")
    checks = {check.name: check for check in report.checks}

    assert report.ok is False
    assert checks["candidate_declaration"].ok is False
    assert checks["candidate_declaration"].detail == "RuntimeError: controlled failure"
    assert checks["quorum_policy"].ok is True
    assert "Traceback" not in json.dumps(report.to_dict())


def test_source_conformance_uses_separate_versioned_profile() -> None:
    report = run_source_conformance(ROOT)

    assert report.ok is True, report.to_dict()
    assert report.profile == "pheroos-source-v3"
    assert {check.name for check in report.checks} >= {
        "source_surface",
        "domain_neutrality_public_core",
        "package_import_boundary",
        "driver_lifecycle_boundary",
        "authority_ledger_contract",
        "trace_store_contract",
        "public_abi_boundary",
        "profile_contract",
    }


def test_source_conformance_fails_missing_surfaces_instead_of_empty_scan(
    tmp_path: Path,
) -> None:
    report = run_source_conformance(tmp_path)
    checks = {check.name: check for check in report.checks}

    assert report.ok is False
    assert checks["source_surface"].ok is False
    assert "pheroos/protocol" in checks["source_surface"].detail
    assert checks["package_import_boundary"].ok is False


def test_source_conformance_rejects_empty_named_surface_directories(
    tmp_path: Path,
) -> None:
    for relative in (
        "pheroos/protocol",
        "pheroos/kernel",
        "pheroos/governance",
        "pheroos/drivers",
        "pheroos/trace",
        "pheroos/conformance",
        "pheroos/cli",
    ):
        (tmp_path / relative).mkdir(parents=True)

    report = run_source_conformance(tmp_path)
    checks = {check.name: check for check in report.checks}

    assert report.ok is False
    assert checks["source_surface"].ok is False
    assert "pheroos/protocol" in checks["source_surface"].detail


def test_fallback_only_hybrid_manifest_returns_full_structured_report(
    tmp_path: Path,
) -> None:
    payload = json.loads(
        (ROOT / "examples/hybrid-pheromone-protocol/capability.json").read_text(
            encoding="utf-8"
        )
    )
    payload["protocol"]["candidates"] = [
        candidate
        for candidate in payload["protocol"]["candidates"]
        if candidate.get("safe_fallback")
    ]
    manifest_path = tmp_path / "capability.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    report = run_conformance(manifest_path)

    assert report.ok is True, report.to_dict()
    assert report.profile == "pheroos-hybrid-swarm-v1"
    assert {check.name for check in report.checks} >= {
        "manifest_schema",
        "pheromone_behavior",
        "pheromone_subject_scoring",
        "pheromone_kind_profile",
        "pheromone_diffusion",
        "pheromone_reinforcement",
        "pheromone_response_model",
        "layer_coordination_policy",
        "policy_adjustment_bounds",
        "hybrid_trace_contract",
        "hybrid_authority_boundary",
        "profile_contract",
    }
    assert "Traceback" not in json.dumps(report.to_dict())


def test_multi_target_hybrid_conformance_ignores_foreign_candidate_ordering(
    tmp_path: Path,
) -> None:
    payload = json.loads(
        (ROOT / "examples/hybrid-pheromone-protocol/capability.json").read_text(
            encoding="utf-8"
        )
    )
    payload["protocol"]["targets"].insert(0, {"id": "decision:foreign"})
    payload["protocol"]["candidates"].insert(
        0,
        {"id": "candidate:foreign", "target": "decision:foreign", "label": "Foreign"},
    )
    manifest_path = tmp_path / "capability.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    report = run_conformance(manifest_path)

    assert report.ok is True, report.to_dict()
    assert report.profile == "pheroos-hybrid-swarm-v1"


def test_hybrid_conformance_exercises_each_declared_response_model(
    tmp_path: Path,
) -> None:
    source = json.loads(
        (ROOT / "examples/hybrid-pheromone-protocol/capability.json").read_text(
            encoding="utf-8"
        )
    )

    for model in ("linear", "saturating", "threshold", "competitive"):
        payload = json.loads(json.dumps(source))
        policy = payload["protocol"]["collective_decision_policy"]
        policy["pheromone_response_model"] = model
        policy["pheromone_competition_mode"] = (
            "normalize" if model == "competitive" else "none"
        )
        for profile in policy["pheromone_kind_profiles"].values():
            profile["response_model"] = model
        manifest_path = tmp_path / model / "capability.json"
        manifest_path.parent.mkdir()
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")

        report = run_conformance(manifest_path)

        assert report.ok is True, report.to_dict()
        assert {check.name: check for check in report.checks}[
            "pheromone_response_model"
        ].ok is True
