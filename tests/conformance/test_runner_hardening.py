from __future__ import annotations

import json
from pathlib import Path

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
