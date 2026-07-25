from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from pheroos.conformance import run_conformance
from pheroos.conformance.profile import profile_for_manifest
from pheroos.protocol import load_capability_manifest


ROOT = Path(__file__).resolve().parents[2]


def test_unknown_protocol_version_cannot_select_an_existing_profile() -> None:
    manifest = load_capability_manifest(ROOT / "examples/toy-protocol/capability.json")
    protocol = replace(
        manifest.protocol,
        protocol_version="pheroos.protocol.v999",
    )

    with pytest.raises(ValueError, match="protocol version is unsupported"):
        profile_for_manifest(replace(manifest, protocol=protocol))


@pytest.mark.parametrize("protocol_version", ["pheroos.protocol.v999", ""])
def test_conformance_rejects_unknown_or_blank_protocol_versions_without_profile_fallback(
    tmp_path: Path,
    protocol_version: str,
) -> None:
    payload = json.loads(
        (ROOT / "examples/toy-protocol/capability.json").read_text(encoding="utf-8")
    )
    payload["protocol"]["protocol_version"] = protocol_version
    manifest_path = tmp_path / "capability.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    report = run_conformance(manifest_path)
    checks = {check.name: check for check in report.checks}

    assert report.ok is False
    assert report.profile == "pheroos-manifest-v1"
    assert set(checks) == {"manifest_schema", "profile_contract"}
    assert checks["manifest_schema"].ok is False
    assert "$.protocol.protocol_version" in checks["manifest_schema"].detail
    assert checks["profile_contract"].detail == "failed:manifest_schema"


def test_conformance_preserves_combined_schema_failures_in_one_structured_report(
    tmp_path: Path,
) -> None:
    payload = json.loads(
        (ROOT / "examples/toy-protocol/capability.json").read_text(encoding="utf-8")
    )
    payload["protocol"]["protocol_version"] = "pheroos.protocol.v999"
    payload["protocol"]["quorum_policy"]["commit_threshold"] = 0
    manifest_path = tmp_path / "capability.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    report = run_conformance(manifest_path)
    checks = {check.name: check for check in report.checks}

    assert report.ok is False
    assert report.profile == "pheroos-manifest-v1"
    assert "$.protocol.protocol_version" in checks["manifest_schema"].detail
    assert (
        "$.protocol.quorum_policy.commit_threshold" in checks["manifest_schema"].detail
    )
    assert "Traceback" not in json.dumps(report.to_dict())
