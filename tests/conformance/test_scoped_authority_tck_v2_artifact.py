from __future__ import annotations

import ast
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from referencing import Registry, Resource
import pytest

from pheroos.conformance.checks.authority_session_v2_contract import (
    GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    GOVERNANCE_STATE_STORE_FAILURE_STAGES_V2,
    GOVERNANCE_STATE_STORE_TAMPER_CASES_V2,
    GOVERNANCE_STATE_STORE_VIEW_FAILURE_STAGE_V2,
)
from pheroos.conformance.checks.baseline_output_v2_contract import (
    GOVERNANCE_BASELINE_OUTPUT_CONFORMANCE_VERSION_V2,
)
from pheroos.conformance.scoped_authority_tck_v2 import (
    AUTHORITY_SESSION_TCK_CASE_IDS_V2,
    BASELINE_OUTPUT_TCK_CASE_IDS_V2,
    SCOPED_AUTHORITY_TCK_CASE_IDS_V2,
    SCOPED_AUTHORITY_TCK_FAILURE_STAGES_V2,
    SCOPED_AUTHORITY_TCK_INVARIANTS_V2,
    SCOPED_AUTHORITY_TCK_SCHEMA_V2,
    SCOPED_AUTHORITY_TCK_SCHEMA_V2_ID,
    SCOPED_AUTHORITY_TCK_VERSION_V2,
    STATE_STORE_TCK_CASE_IDS_V2,
    ScopedAuthorityTckArtifactCodeV2,
    ScopedAuthorityTckArtifactErrorV2,
    ScopedAuthorityTckArtifactV2,
    ScopedAuthorityTckCaseReportV2,
    ScopedAuthorityTckCaseV2,
    ScopedAuthorityTckReportV2,
    ScopedAuthorityTckRequestV2,
    loads_scoped_authority_tck_document_v2,
    read_scoped_authority_tck_document_v2,
    scoped_authority_tck_v2_schema,
    validate_scoped_authority_tck_document_v2,
)
from pheroos.governance.authority_schema_v2 import (
    AUTHORITY_SCHEMA_V2_ID,
    authority_schema_v2,
)
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDomainV2,
    GovernanceHeadV2,
    PreparedGovernanceTransitionV2,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    GovernanceAuthorityReadSetV2,
    GovernanceReadPreconditionV2,
)


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "schemas" / "scoped-authority-tck-v2.schema.json"
CHECKS = ROOT / "pheroos" / "conformance" / "checks"


def _domain() -> AuthorityDomainV2:
    return AuthorityDomainV2(
        policy_version=AUTHORITY_POLICY_VERSION_V2,
        profile=AUTHORITY_LOCAL_PROFILE_V2,
        wire_version=AUTHORITY_WIRE_VERSION_V2,
        canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref="scope:scoped-authority-tck-v2",
    )


def _case(case_id: str) -> ScopedAuthorityTckCaseV2:
    request = ScopedAuthorityTckRequestV2(
        case_id=case_id,
        operation="create_domain_v2",
        profile=AUTHORITY_LOCAL_PROFILE_V2,
        payload=_domain(),
    )
    return ScopedAuthorityTckCaseV2(
        id=case_id,
        operation=request.operation,
        profile=request.profile,
        request=request,
        required_invariants=(case_id,),
    )


def _transition_with_expected_data() -> PreparedGovernanceTransitionV2:
    domain = _domain()
    stream_ref = "stream:scoped-authority-tck-v2"
    head = GovernanceHeadV2.genesis(domain, stream_ref)
    read_set = GovernanceAuthorityReadSetV2(
        entries=(
            GovernanceReadPreconditionV2(
                stream_ref=stream_ref,
                expected_revision=head.revision,
                expected_root=head.head_root,
            ),
        )
    )
    return PreparedGovernanceTransitionV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=stream_ref,
        transition_id="transition:expected-is-application-data",
        expected_revision=head.revision,
        expected_root=head.head_root,
        read_set_root=read_set.root(),
        state_records={"expected": "application-owned value"},
    )


def _artifact() -> ScopedAuthorityTckArtifactV2:
    return ScopedAuthorityTckArtifactV2(
        cases=tuple(_case(case_id) for case_id in SCOPED_AUTHORITY_TCK_CASE_IDS_V2)
    )


def _case_report(case_id: str, *, ok: bool = True) -> ScopedAuthorityTckCaseReportV2:
    return ScopedAuthorityTckCaseReportV2(
        id=case_id,
        ok=ok,
        observed_invariants=(case_id,) if ok else (),
        diagnostic_code=None,
        failure_stage=None,
        detail="",
    )


def _report() -> ScopedAuthorityTckReportV2:
    return ScopedAuthorityTckReportV2(
        implementation_id="implementation:independent-authority-v2",
        results=tuple(
            _case_report(case_id) for case_id in SCOPED_AUTHORITY_TCK_CASE_IDS_V2
        ),
    )


def _validator() -> Draft202012Validator:
    authority = authority_schema_v2()
    registry = Registry().with_resource(
        AUTHORITY_SCHEMA_V2_ID,
        Resource.from_contents(authority),
    )
    return Draft202012Validator(scoped_authority_tck_v2_schema(), registry=registry)


def _rendered(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _runner_case_ids(
    module_name: str,
    run_name: str,
    prefix: str,
) -> tuple[str, ...]:
    tree = ast.parse((CHECKS / f"{module_name}.py").read_text(encoding="utf-8"))
    runner = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == run_name
    )
    case_ids: list[str] = []
    for node in ast.walk(runner):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id.startswith("_evaluate_")
        ):
            continue
        suffix = node.func.id.removeprefix("_evaluate_")
        if suffix == "vertical_case":
            label = next(
                keyword.value.value
                for keyword in node.keywords
                if keyword.arg == "label"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            )
            case_ids.append(f"{prefix}:{label}")
        else:
            case_ids.append(f"{prefix}:{suffix}")
    return tuple(case_ids)


def test_tck_schema_id_versions_and_checked_artifact_are_exact() -> None:
    schema = scoped_authority_tck_v2_schema()

    Draft202012Validator.check_schema(schema)
    assert SCOPED_AUTHORITY_TCK_SCHEMA_V2 == SCOPED_AUTHORITY_TCK_VERSION_V2
    assert SCOPED_AUTHORITY_TCK_VERSION_V2 == "pheroos-scoped-authority-tck-v2"
    assert SCOPED_AUTHORITY_TCK_SCHEMA_V2_ID == (
        "https://pheroos.dev/schemas/scoped-authority-tck-v2.schema.json"
    )
    assert schema["$id"] == SCOPED_AUTHORITY_TCK_SCHEMA_V2_ID
    assert ARTIFACT.read_bytes() == _rendered(schema)
    assert schema["$defs"]["request"]["properties"]["payload"] == {
        "$ref": AUTHORITY_SCHEMA_V2_ID
    }


def test_case_vocabulary_reuses_all_three_active_matrix_versions_and_registries() -> (
    None
):
    assert len(SCOPED_AUTHORITY_TCK_CASE_IDS_V2) == 33
    assert SCOPED_AUTHORITY_TCK_CASE_IDS_V2 == (
        *STATE_STORE_TCK_CASE_IDS_V2,
        *AUTHORITY_SESSION_TCK_CASE_IDS_V2,
        *BASELINE_OUTPUT_TCK_CASE_IDS_V2,
    )
    assert SCOPED_AUTHORITY_TCK_FAILURE_STAGES_V2 == (
        *GOVERNANCE_STATE_STORE_FAILURE_STAGES_V2,
        GOVERNANCE_STATE_STORE_VIEW_FAILURE_STAGE_V2,
    )
    for stage in SCOPED_AUTHORITY_TCK_FAILURE_STAGES_V2:
        assert f"state_store:failure_stage:{stage}" in (
            SCOPED_AUTHORITY_TCK_INVARIANTS_V2
        )
    for case in GOVERNANCE_STATE_STORE_TAMPER_CASES_V2:
        assert f"state_store:tamper:{case}" in SCOPED_AUTHORITY_TCK_INVARIANTS_V2

    assert STATE_STORE_TCK_CASE_IDS_V2 == _runner_case_ids(
        "authority_store_v2_contract",
        "run_governance_state_store_conformance_v2",
        "state_store",
    )
    assert AUTHORITY_SESSION_TCK_CASE_IDS_V2 == _runner_case_ids(
        "authority_session_v2_contract",
        "run_governance_authority_session_conformance_v2",
        "authority_session",
    )
    assert BASELINE_OUTPUT_TCK_CASE_IDS_V2 == _runner_case_ids(
        "baseline_output_v2_contract",
        "run_governance_baseline_output_conformance_v2",
        "baseline_output",
    )


def test_complete_expected_free_artifact_round_trips_and_validates() -> None:
    artifact = _artifact()
    wire = artifact.to_dict()

    assert "expected" not in json.dumps(wire, sort_keys=True)
    assert _validator().is_valid(wire) is True
    assert ScopedAuthorityTckArtifactV2.from_dict(wire) == artifact
    assert read_scoped_authority_tck_document_v2(wire) == artifact
    validate_scoped_authority_tck_document_v2(wire)
    assert wire["state_store_conformance_version"] == (
        GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2
    )
    assert wire["authority_session_conformance_version"] == (
        GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2
    )
    assert wire["baseline_output_conformance_version"] == (
        GOVERNANCE_BASELINE_OUTPUT_CONFORMANCE_VERSION_V2
    )


def test_actual_only_report_round_trips_is_closed_and_has_no_skip_lane() -> None:
    report = _report()
    wire = report.to_dict()

    assert report.ok is True
    assert _validator().is_valid(wire) is True
    assert ScopedAuthorityTckReportV2.from_dict(wire) == report
    assert read_scoped_authority_tck_document_v2(wire) == report
    results = cast(list[dict[str, Any]], wire["results"])
    assert all(item["ok"] is True for item in results)
    assert "expected" not in json.dumps(wire, sort_keys=True)
    assert "skip" not in json.dumps(wire, sort_keys=True).lower()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: {**value, "unknown": True},
        lambda value: {**value, "tck_version": "pheroos-scoped-authority-tck-v999"},
        lambda value: {**value, "cases": value["cases"][:-1]},
    ],
)
def test_artifact_reader_and_schema_reject_unknown_version_or_partial_case_sets(
    mutation: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    wire = mutation(deepcopy(_artifact().to_dict()))

    assert _validator().is_valid(wire) is False
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2):
        read_scoped_authority_tck_document_v2(wire)


def test_case_reader_rejects_expected_field_and_cross_bound_request() -> None:
    wire = _case(SCOPED_AUTHORITY_TCK_CASE_IDS_V2[0]).to_dict()
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2) as expected:
        ScopedAuthorityTckCaseV2.from_dict({**wire, "expected": {"ok": True}})
    assert expected.value.code is ScopedAuthorityTckArtifactCodeV2.INVALID_FIELDS

    cross_bound = deepcopy(wire)
    request = cast(dict[str, Any], cross_bound["request"])
    request["case_id"] = SCOPED_AUTHORITY_TCK_CASE_IDS_V2[1]
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2, match="bindings"):
        ScopedAuthorityTckCaseV2.from_dict(cross_bound)

    artifact = deepcopy(_artifact().to_dict())
    cases = cast(list[dict[str, Any]], artifact["cases"])
    artifact_request = cast(dict[str, Any], cases[0]["request"])
    artifact_request["case_id"] = SCOPED_AUTHORITY_TCK_CASE_IDS_V2[1]
    assert _validator().is_valid(artifact) is False
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2, match="bindings"):
        read_scoped_authority_tck_document_v2(artifact)


def test_schema_and_reader_both_reject_reordered_complete_case_sets() -> None:
    artifact = deepcopy(_artifact().to_dict())
    cases = cast(list[dict[str, Any]], artifact["cases"])
    cases[0], cases[1] = cases[1], cases[0]

    report = deepcopy(_report().to_dict())
    results = cast(list[dict[str, Any]], report["results"])
    results[0], results[1] = results[1], results[0]

    for wire in (artifact, report):
        assert _validator().is_valid(wire) is False
        with pytest.raises(ScopedAuthorityTckArtifactErrorV2, match="exactly once"):
            read_scoped_authority_tck_document_v2(wire)


def test_expected_free_envelope_does_not_reserve_nested_authority_data_keys() -> None:
    artifact = deepcopy(_artifact().to_dict())
    cases = cast(list[dict[str, Any]], artifact["cases"])
    request = cast(dict[str, Any], cases[0]["request"])
    request["payload"] = _transition_with_expected_data().to_dict()

    assert _validator().is_valid(artifact) is True
    assert read_scoped_authority_tck_document_v2(artifact).to_dict() == artifact


def test_schema_and_typed_report_reader_both_reject_bool_as_int_and_unknown_fields() -> (
    None
):
    report = deepcopy(_report().to_dict())
    results = cast(list[dict[str, Any]], report["results"])
    results[0]["ok"] = 1

    assert _validator().is_valid(report) is False
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2, match="exact boolean"):
        ScopedAuthorityTckReportV2.from_dict(report)

    result = deepcopy(_case_report(SCOPED_AUTHORITY_TCK_CASE_IDS_V2[0]).to_dict())
    result["unexpected"] = False
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2) as captured:
        ScopedAuthorityTckCaseReportV2.from_dict(result)
    assert captured.value.code is ScopedAuthorityTckArtifactCodeV2.INVALID_FIELDS


def test_strict_tck_json_loader_rejects_duplicate_keys_nonfinite_and_bom() -> None:
    wire = json.dumps(_report().to_dict(), sort_keys=True)
    duplicate = wire[:-1] + ',"tck_version":"pheroos-scoped-authority-tck-v2"}'
    nonfinite = wire.replace(
        '"implementation_id":',
        '"nonfinite":NaN,"implementation_id":',
    )

    for value in (
        duplicate,
        nonfinite,
        "\ufeff" + wire,
        b"\xef\xbb\xbf" + wire.encode(),
    ):
        with pytest.raises(ScopedAuthorityTckArtifactErrorV2) as captured:
            loads_scoped_authority_tck_document_v2(value)
        assert captured.value.code is ScopedAuthorityTckArtifactCodeV2.INVALID_JSON


def test_public_tck_records_reject_foreign_mutable_and_noncanonical_values() -> None:
    case_id = SCOPED_AUTHORITY_TCK_CASE_IDS_V2[0]
    request = _case(case_id).request

    with pytest.raises(ScopedAuthorityTckArtifactErrorV2) as payload_error:
        ScopedAuthorityTckRequestV2(
            case_id=case_id,
            operation="create_domain_v2",
            profile=AUTHORITY_LOCAL_PROFILE_V2,
            payload=cast(Any, object()),
        )
    assert payload_error.value.path == "/request/payload"

    with pytest.raises(ScopedAuthorityTckArtifactErrorV2, match="exact TCK type"):
        ScopedAuthorityTckCaseV2(
            id=case_id,
            operation=request.operation,
            profile=request.profile,
            request=cast(Any, _domain()),
            required_invariants=(case_id,),
        )

    with pytest.raises(ScopedAuthorityTckArtifactErrorV2, match="closed enum"):
        ScopedAuthorityTckCaseReportV2(
            id=case_id,
            ok=False,
            observed_invariants=(),
            diagnostic_code=cast(Any, "invented_diagnostic"),
            failure_stage=None,
            detail="adapter rejected the request",
        )

    with pytest.raises(ScopedAuthorityTckArtifactErrorV2, match="immutable case"):
        ScopedAuthorityTckArtifactV2(cases=cast(Any, list(_artifact().cases)))
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2, match="immutable records"):
        ScopedAuthorityTckReportV2(
            implementation_id="implementation:mutable-results",
            results=cast(Any, list(_report().results)),
        )


def test_typed_readers_reject_malformed_nested_shapes_and_diagnostics() -> None:
    request = _case(SCOPED_AUTHORITY_TCK_CASE_IDS_V2[0]).request.to_dict()
    request["payload"] = {"authority_version": "invented"}
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2) as payload_error:
        ScopedAuthorityTckRequestV2.from_dict(request)
    assert payload_error.value.path == "/request/payload"

    case = _case(SCOPED_AUTHORITY_TCK_CASE_IDS_V2[0]).to_dict()
    case["required_invariants"] = "not-an-array"
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2, match="string array"):
        ScopedAuthorityTckCaseV2.from_dict(case)

    result = _case_report(SCOPED_AUTHORITY_TCK_CASE_IDS_V2[0]).to_dict()
    result["diagnostic_code"] = "invented_diagnostic"
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2) as diagnostic_error:
        ScopedAuthorityTckCaseReportV2.from_dict(result)
    assert diagnostic_error.value.path == "/result/diagnostic_code"

    artifact = _artifact().to_dict()
    artifact["cases"] = tuple(cast(list[object], artifact["cases"]))
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2, match="must be an array"):
        ScopedAuthorityTckArtifactV2.from_dict(artifact)

    report = _report().to_dict()
    report["results"] = tuple(cast(list[object], report["results"]))
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2, match="must be an array"):
        ScopedAuthorityTckReportV2.from_dict(report)

    malformed_documents: tuple[object, ...] = (None, [], "not-an-object")
    for value in malformed_documents:
        with pytest.raises(ScopedAuthorityTckArtifactErrorV2) as document_error:
            read_scoped_authority_tck_document_v2(value)
        assert (
            document_error.value.code is ScopedAuthorityTckArtifactCodeV2.INVALID_VALUE
        )

    with pytest.raises(ScopedAuthorityTckArtifactErrorV2) as shape_error:
        ScopedAuthorityTckRequestV2.from_dict(None)
    assert shape_error.value.code is ScopedAuthorityTckArtifactCodeV2.INVALID_FIELDS


@pytest.mark.parametrize(
    ("field", "expected_path"),
    (
        ("state_store_conformance_version", "/state_store_conformance_version"),
        (
            "authority_session_conformance_version",
            "/authority_session_conformance_version",
        ),
        (
            "baseline_output_conformance_version",
            "/baseline_output_conformance_version",
        ),
    ),
)
def test_tck_document_rejects_each_incompatible_component_version(
    field: str,
    expected_path: str,
) -> None:
    wire = _artifact().to_dict()
    wire[field] = "unsupported-conformance-version"

    with pytest.raises(ScopedAuthorityTckArtifactErrorV2) as captured:
        read_scoped_authority_tck_document_v2(wire)

    assert captured.value.code is ScopedAuthorityTckArtifactCodeV2.INVALID_VERSION
    assert captured.value.path == expected_path


@pytest.mark.parametrize(
    ("field", "value", "expected_path"),
    (
        ("case_id", "state_store:undeclared", "/request/case_id"),
        ("operation", "erase_domain_v2", "/request/operation"),
        ("profile", "authority-profile-v999", "/request/profile"),
    ),
)
def test_tck_request_rejects_values_outside_closed_registries(
    field: str,
    value: object,
    expected_path: str,
) -> None:
    wire = _case(SCOPED_AUTHORITY_TCK_CASE_IDS_V2[0]).request.to_dict()
    wire[field] = value

    with pytest.raises(ScopedAuthorityTckArtifactErrorV2) as captured:
        ScopedAuthorityTckRequestV2.from_dict(wire)

    assert captured.value.path == expected_path


@pytest.mark.parametrize(
    "invariants",
    (
        (),
        ("undeclared:invariant",),
        (
            SCOPED_AUTHORITY_TCK_INVARIANTS_V2[0],
            SCOPED_AUTHORITY_TCK_INVARIANTS_V2[0],
        ),
        tuple(reversed(SCOPED_AUTHORITY_TCK_INVARIANTS_V2[:2])),
    ),
)
def test_tck_case_rejects_empty_unknown_duplicate_or_reordered_invariants(
    invariants: tuple[str, ...],
) -> None:
    case_id = SCOPED_AUTHORITY_TCK_CASE_IDS_V2[0]
    request = _case(case_id).request
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2):
        ScopedAuthorityTckCaseV2(
            id=case_id,
            operation=request.operation,
            profile=request.profile,
            request=request,
            required_invariants=invariants,
        )


def test_tck_case_rejects_mutable_invariants_and_unknown_failure_stage() -> None:
    case_id = SCOPED_AUTHORITY_TCK_CASE_IDS_V2[0]
    request = _case(case_id).request
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2, match="immutable tuple"):
        ScopedAuthorityTckCaseV2(
            id=case_id,
            operation=request.operation,
            profile=request.profile,
            request=request,
            required_invariants=cast(Any, [case_id]),
        )
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2, match="failure_stage"):
        ScopedAuthorityTckCaseV2(
            id=case_id,
            operation=request.operation,
            profile=request.profile,
            request=request,
            required_invariants=(case_id,),
            failure_stage="after_unbounded_publication",
        )


@pytest.mark.parametrize(
    "implementation_id",
    ("", " implementation:leading-space", "e\u0301", "bad\x00id", cast(Any, 7)),
)
def test_tck_report_rejects_nonportable_implementation_identity(
    implementation_id: str,
) -> None:
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2):
        ScopedAuthorityTckReportV2(
            implementation_id=implementation_id,
            results=_report().results,
        )


def test_tck_report_rejects_non_utf8_detail_and_non_string_observations() -> None:
    case_id = SCOPED_AUTHORITY_TCK_CASE_IDS_V2[0]
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2, match="encode as UTF-8"):
        ScopedAuthorityTckCaseReportV2(
            id=case_id,
            ok=False,
            observed_invariants=(),
            diagnostic_code=None,
            failure_stage=None,
            detail="\ud800",
        )

    result = _case_report(case_id).to_dict()
    result["observed_invariants"] = [case_id, 7]
    with pytest.raises(ScopedAuthorityTckArtifactErrorV2, match="string array"):
        ScopedAuthorityTckCaseReportV2.from_dict(result)


def test_strict_tck_json_loader_rejects_invalid_utf8_nfd_keys_and_non_text() -> None:
    for value in (b"\xff", 7, object(), "{"):
        with pytest.raises(ScopedAuthorityTckArtifactErrorV2) as captured:
            loads_scoped_authority_tck_document_v2(cast(Any, value))
        assert captured.value.code is ScopedAuthorityTckArtifactCodeV2.INVALID_JSON

    with pytest.raises(ScopedAuthorityTckArtifactErrorV2, match="already use NFC"):
        loads_scoped_authority_tck_document_v2('{"e\\u0301": 1}')

    encoded = bytearray(json.dumps(_report().to_dict()).encode("utf-8"))
    assert loads_scoped_authority_tck_document_v2(encoded) == _report()


def test_factory_and_artifact_are_deterministic_from_an_external_cwd(
    tmp_path: Path,
) -> None:
    code = """
import hashlib, json
from pheroos.conformance.scoped_authority_tck_v2 import scoped_authority_tck_v2_schema
raw=(json.dumps(scoped_authority_tck_v2_schema(),indent=2,sort_keys=True)+'\\n').encode()
print(hashlib.sha256(raw).hexdigest())
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={"PYTHONPATH": str(ROOT)},
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == sha256(ARTIFACT.read_bytes()).hexdigest()
