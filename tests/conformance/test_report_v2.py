from __future__ import annotations

from dataclasses import replace

import pytest

from pheroos.conformance import (
    CONFORMANCE_REPORT_SCHEMA_ID,
    CONFORMANCE_REPORT_VERSION,
    CheckResult,
    ConformanceReport,
    ConformanceSubjectKind,
    conformance_report_schema,
    run_source_conformance,
    validate_manifest,
)


def test_manifest_report_is_versioned_and_binds_subject_artifact() -> None:
    report = validate_manifest("examples/toy-protocol/capability.json")
    payload = report.to_dict()

    assert report.report_version == CONFORMANCE_REPORT_VERSION
    assert report.report_schema_id == CONFORMANCE_REPORT_SCHEMA_ID
    assert report.subject_kind is ConformanceSubjectKind.MANIFEST
    assert report.artifact_digest.startswith("sha256:")
    assert payload["check_projection"] == payload["checks"]
    assert payload["$schema"] == CONFORMANCE_REPORT_SCHEMA_ID
    assert len(report.check_projection_digest) == len("sha256:") + 64
    assert ConformanceReport.from_dict(payload) == report


def test_source_report_declares_source_abi_subject_kind() -> None:
    report = run_source_conformance(".")

    assert report.subject_kind is ConformanceSubjectKind.SOURCE_ABI
    assert report.artifact_digest.startswith("sha256:")


def test_report_projection_digest_is_deterministic_and_order_sensitive() -> None:
    checks = (
        CheckResult("first", True),
        CheckResult("second", False, "expected failure"),
    )
    report = ConformanceReport(
        target="fixture",
        profile="profile:v2",
        checks=checks,
        artifact_digest="sha256:" + "0" * 64,
    )
    identical = replace(report)
    reordered = replace(report, checks=tuple(reversed(checks)))

    assert identical.check_projection_digest == report.check_projection_digest
    assert reordered.check_projection_digest != report.check_projection_digest


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("report_version", "pheroos-conformance-report-v999", "version"),
        ("report_schema_id", "https://example.invalid/report.json", "schema"),
        ("subject_kind", "unknown", "subject kind"),
        ("artifact_digest", "sha256:forged", "artifact digest"),
    ],
)
def test_report_rejects_unknown_or_mismatched_identity(
    field: str,
    value: str,
    message: str,
) -> None:
    kwargs = {
        "target": "fixture",
        "profile": "profile:v2",
        "artifact_digest": "sha256:" + "0" * 64,
        field: value,
    }

    with pytest.raises(ValueError, match=message):
        ConformanceReport(**kwargs)


def test_conformance_report_schema_is_closed_and_versioned() -> None:
    schema = conformance_report_schema()

    assert schema["$id"] == CONFORMANCE_REPORT_SCHEMA_ID
    assert schema["additionalProperties"] is False
    assert schema["properties"]["report_version"]["const"] == (
        CONFORMANCE_REPORT_VERSION
    )


@pytest.mark.parametrize("field", ["checks", "check_projection", "ok"])
def test_report_parser_rejects_inconsistent_check_projection(field: str) -> None:
    report = ConformanceReport(
        target="fixture",
        profile="profile:v2",
        checks=(CheckResult("proof", True),),
        artifact_digest="sha256:" + "0" * 64,
    )
    payload = report.to_dict()
    if field == "ok":
        payload[field] = False
    else:
        payload[field][0]["ok"] = False

    with pytest.raises(ValueError, match="inconsistent"):
        ConformanceReport.from_dict(payload)
