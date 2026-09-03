from __future__ import annotations

import ast
from copy import deepcopy
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
import pytest

from pheroos.conformance.commit_tck import commit_tck_artifact_root
from pheroos.conformance.commit_tck_v2 import (
    CommitTckV2Case,
    PheroosPublicCommitTckV2Adapter,
    commit_tck_v2_artifact_root,
    commit_tck_v2_schema,
    load_commit_tck_v2_cases,
    run_commit_tck_v2,
    run_commit_tck_v2_jsonl,
)
from pheroos.conformance.commit_tck_v2_protocol import (
    COMMIT_TCK_JSONL_PROTOCOL_VERSION,
    COMMIT_TCK_REQUEST_VERSION,
    COMMIT_TCK_RESPONSE_VERSION,
    COMMIT_TCK_V2_VERSION,
    CommitTckRequest,
    CommitTckResponse,
    CommitTckV2ProtocolError,
    commit_tck_request_v2_schema,
    commit_tck_response_v2_schema,
    empty_commit_tck_actual,
    loads_commit_tck_json,
    serve_commit_tck_v2_jsonl,
    validate_commit_tck_actual,
)
from pheroos.conformance.commit_tck_v2_spec_adapter import (
    IndependentCommitSpecModelAdapter,
    SPEC_MODEL_IMPLEMENTATION_ID,
)


ROOT = Path(__file__).resolve().parents[2]
V1_ARTIFACT = ROOT / "pheroos" / "conformance" / "tck" / "commit-integrity-v1.json"
V2_ARTIFACT = ROOT / "pheroos" / "conformance" / "tck" / "commit-integrity-v2.json"
SPEC_ADAPTER = "pheroos.conformance.commit_tck_v2_spec_adapter"
V1_FILE_SHA256 = "2c2872b4135d8881b41b61d0028f0c3164da7f5d5068d5b036421016f2ea0343"
V1_SEMANTIC_ROOT = (
    "sha256:376c3dc76fc469e7b77bcba81d32a65f40aec0507669a8e35b3cd61c88e7d2bb"
)
V2_FILE_SHA256 = "0cb38415b5429aec17235eff9ea55867afe44d11be8669e80397277c206af00b"


def _isolated_python() -> str:
    local = ROOT / ".venv" / "bin" / "python"
    return str(local) if local.is_file() else sys.executable


def _spec_command() -> list[str]:
    return [_isolated_python(), "-I", "-m", SPEC_ADAPTER]


def _case(identifier: str) -> CommitTckV2Case:
    return next(
        item for item in load_commit_tck_v2_cases() if item.request.id == identifier
    )


def _request_with(
    source: CommitTckRequest,
    *,
    identifier: str | None = None,
    matrix_case: int | None = None,
    manifest: dict[str, object] | None = None,
) -> CommitTckRequest:
    payload = source.to_dict()
    if identifier is not None:
        payload["id"] = identifier
    if matrix_case is not None:
        payload["matrix_case"] = matrix_case
    if manifest is not None:
        payload["manifest"] = manifest
    return CommitTckRequest.from_dict(payload)


def _request_with_inputs(
    source: CommitTckRequest,
    **updates: object,
) -> CommitTckRequest:
    payload = source.to_dict()
    payload["inputs"].update(updates)
    return CommitTckRequest.from_dict(payload)


def _jsonl_handshake(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "message_type": "handshake",
        "adapter_protocol": COMMIT_TCK_JSONL_PROTOCOL_VERSION,
        "session_id": "protocol-session",
        "tck_version": COMMIT_TCK_V2_VERSION,
        "request_version": COMMIT_TCK_REQUEST_VERSION,
        "response_version": COMMIT_TCK_RESPONSE_VERSION,
        "operations": ["fixed_point_multiply"],
    }
    value.update(updates)
    return value


def _jsonl_input(*messages: object) -> StringIO:
    return StringIO("".join(json.dumps(message) + "\n" for message in messages))


def test_v2_checked_schemas_are_public_exact_and_validate_the_artifact() -> None:
    checked_request = json.loads(
        (ROOT / "schemas" / "commit-tck-request-v2.schema.json").read_text(
            encoding="utf-8"
        )
    )
    checked_response = json.loads(
        (ROOT / "schemas" / "commit-tck-response-v2.schema.json").read_text(
            encoding="utf-8"
        )
    )
    checked_artifact = json.loads(
        (ROOT / "schemas" / "commit-tck-v2.schema.json").read_text(encoding="utf-8")
    )

    assert checked_request == commit_tck_request_v2_schema()
    assert checked_response == commit_tck_response_v2_schema()
    assert checked_artifact == commit_tck_v2_schema()
    for schema in (checked_request, checked_response, checked_artifact):
        Draft202012Validator.check_schema(schema)

    artifact = json.loads(V2_ARTIFACT.read_text(encoding="utf-8"))
    Draft202012Validator(checked_artifact).validate(artifact)
    first = load_commit_tck_v2_cases()[0]
    request = first.request.to_dict()
    response = PheroosPublicCommitTckV2Adapter().evaluate(first.request).to_dict()
    Draft202012Validator(checked_request).validate(request)
    Draft202012Validator(checked_response).validate(response)


def test_v2_adapter_request_is_expected_free_and_fresh() -> None:
    selected = _case("manifest-deadline-at-boundary")
    request = selected.request.to_dict()

    assert request["request_version"] == COMMIT_TCK_REQUEST_VERSION
    assert request["tck_version"] == COMMIT_TCK_V2_VERSION
    assert "expected" not in request
    assert "mutations" not in request
    assert "permutations" not in request

    seen: list[CommitTckRequest] = []

    class InspectingAdapter:
        implementation_id = "inspecting-v2"

        def evaluate(self, value: CommitTckRequest) -> CommitTckResponse:
            assert not hasattr(value, "expected")
            seen.append(value)
            actual = PheroosPublicCommitTckV2Adapter().evaluate(value).actual
            value.inputs["elapsed_steps"] = 0
            assert value.manifest is not None
            value.manifest["id"] = "mutated-by-adapter"
            return CommitTckResponse(
                request_id=value.id,
                implementation_id=self.implementation_id,
                actual=actual,
            )

    first = run_commit_tck_v2((selected,), adapter=InspectingAdapter())
    second = run_commit_tck_v2((selected,), adapter=InspectingAdapter())

    assert first.ok is True
    assert second.ok is True
    assert seen[0] is not seen[1]
    assert selected.request.inputs["elapsed_steps"] == 24
    assert selected.request.manifest is not None
    assert selected.request.manifest["id"] == "commit-tck-v2-manifest"


def test_v1_artifact_and_semantic_root_remain_byte_frozen() -> None:
    assert sha256(V1_ARTIFACT.read_bytes()).hexdigest() == V1_FILE_SHA256
    assert commit_tck_artifact_root() == V1_SEMANTIC_ROOT
    assert sha256(V2_ARTIFACT.read_bytes()).hexdigest() == V2_FILE_SHA256


def test_subject_and_independent_spec_model_match_every_declarative_golden() -> None:
    cases = load_commit_tck_v2_cases()

    assert len(cases) == 23
    assert [item.request.matrix_case for item in cases] == list(range(1, 24))

    subject = run_commit_tck_v2(cases)
    oracle = run_commit_tck_v2(
        cases,
        adapter=IndependentCommitSpecModelAdapter(),
    )

    assert subject.ok is True
    assert oracle.ok is True
    assert subject.implementation_id != oracle.implementation_id
    assert oracle.implementation_id == SPEC_MODEL_IMPLEMENTATION_ID
    assert [item.actual for item in subject.results] == [
        item.actual for item in oracle.results
    ]
    assert [item.actual for item in subject.results] == [
        item.expected for item in cases
    ]


def test_independent_spec_model_uses_real_jsonl_handshake_from_external_cwd(
    tmp_path: Path,
) -> None:
    report = run_commit_tck_v2_jsonl(_spec_command(), cwd=tmp_path)

    assert report.ok is True, report.protocol_error
    assert report.implementation_id == SPEC_MODEL_IMPLEMENTATION_ID
    assert all(
        item.implementation_id == SPEC_MODEL_IMPLEMENTATION_ID
        for item in report.results
    )


def test_spec_model_has_no_governance_or_reference_adapter_dependency() -> None:
    path = ROOT / "pheroos" / "conformance" / "commit_tck_v2_spec_adapter.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert not any(name.startswith("pheroos.governance") for name in imported)
    assert "pheroos.conformance.commit_tck" not in imported
    assert "pheroos.conformance.commit_tck_v2" not in imported
    assert "ReferenceCommitTckAdapter" not in source
    assert "_commit_reference" not in source


def test_manifest_sensitive_pairs_change_the_same_declared_decision() -> None:
    base = _case("manifest-deadline-at-boundary")
    deadline_patch = _case("manifest-patched-run-deadline")
    outcome_patch = _case("manifest-patched-deadline-outcome")

    assert base.request.inputs == deadline_patch.request.inputs
    assert base.request.inputs == outcome_patch.request.inputs
    assert base.expected["outcome"] == {"kind": "safe_fallback"}
    assert deadline_patch.expected["outcome"] == {"kind": None}
    assert outcome_patch.expected["outcome"] == {"kind": "advisory"}
    assert base.request.manifest is not None
    assert deadline_patch.request.manifest is not None
    assert outcome_patch.request.manifest is not None
    assert (
        base.request.manifest["protocol"]["collective_commit_policy"]["commit_window"][
            "run_deadline_steps"
        ]
        == 24
    )
    assert (
        deadline_patch.request.manifest["protocol"]["collective_commit_policy"][
            "commit_window"
        ]["run_deadline_steps"]
        == 25
    )
    assert (
        outcome_patch.request.manifest["protocol"]["collective_commit_policy"][
            "terminal_outcome"
        ]["deadline_outcome"]
        == "advisory"
    )


def test_manifest_threshold_pairs_cover_evidence_support_diversity_and_margin() -> None:
    base = _case("manifest-threshold-ready")
    pairs = {
        "manifest-threshold-positive-evidence-patched": (
            "minimum_positive_evidence",
            "positive_evidence_satisfied",
            2000001,
        ),
        "manifest-threshold-support-patched": (
            "minimum_support_clusters",
            "support_clusters_satisfied",
            3,
        ),
        "manifest-threshold-diversity-patched": (
            "minimum_source_diversity",
            "source_diversity_satisfied",
            3,
        ),
        "manifest-threshold-margin-patched": (
            "minimum_margin",
            "margin_satisfied",
            300000,
        ),
    }

    assert base.expected["outcome"]["ready"] is True
    for identifier, (metric, gate, patched_value) in pairs.items():
        changed = _case(identifier)
        assert changed.request.inputs == base.request.inputs
        assert changed.expected["metrics"][metric] == patched_value
        assert changed.expected["outcome"][gate] is False
        assert changed.expected["outcome"]["ready"] is False


def test_manifest_assurance_and_distributed_fault_model_pairs_are_explicit() -> None:
    assurance_cases = tuple(
        _case(identifier)
        for identifier in (
            "manifest-assurance-advisory",
            "manifest-assurance-evidence-bound",
            "manifest-assurance-certified",
            "manifest-assurance-distributed",
        )
    )
    assert [item.expected["metrics"]["proof_rank"] for item in assurance_cases] == [
        0,
        1,
        2,
        3,
    ]
    assert [
        item.expected["outcome"]["certificate_mode"] for item in assurance_cases
    ] == [
        "none",
        "local_receipt",
        "portable",
        "distributed",
    ]

    ready = _case("manifest-distributed-quorum-ready")
    scaled = _case("manifest-distributed-membership-scaled")
    invalid_fault = _case("manifest-distributed-fault-model-invalid")
    assert ready.request.inputs == scaled.request.inputs == invalid_fault.request.inputs
    assert ready.expected["outcome"]["finality_ready"] is True
    assert scaled.expected["metrics"]["membership_size"] == 7
    assert scaled.expected["metrics"]["witness_quorum"] == 5
    assert scaled.expected["outcome"]["finality_ready"] is False
    assert invalid_fault.expected["outcome"]["fault_model_valid"] is False
    assert invalid_fault.expected["outcome"]["diagnostic_codes"] == [
        "commit_fault_model_invalid"
    ]
    assert invalid_fault.expected["failure_code"] == "commit_fault_model_invalid"


def test_attention_changes_never_change_commit_truth_or_gain_authority() -> None:
    weight_one = _case("attention-truth-invariant-weight-one")
    weight_two = _case("attention-truth-invariant-weight-two")

    assert weight_one.request.inputs == weight_two.request.inputs
    assert (
        weight_one.expected["roots"]["commit_truth_root"]
        == weight_two.expected["roots"]["commit_truth_root"]
    )
    assert (
        weight_one.expected["roots"]["attention_root"]
        != weight_two.expected["roots"]["attention_root"]
    )
    for selected in (weight_one, weight_two):
        assert selected.expected["outcome"]["commit_leader"] == "candidate:alpha"
        assert (
            selected.expected["outcome"]["attention_top_candidate"] == "candidate:beta"
        )
        assert selected.expected["outcome"]["attention_commit_authority"] is False
        assert selected.expected["outcome"]["truth_invariant"] is True


def test_certificate_and_trace_exhaustive_scalar_leaf_audits_are_frozen() -> None:
    certificate = _case("certificate-authority-leaf-binding")
    trace = _case("trace-authority-leaf-binding")

    assert certificate.expected["metrics"] == {
        "authority_leaf_count": 51,
        "rejected_mutation_count": 51,
    }
    assert trace.expected["metrics"] == {
        "authority_leaf_count": 18,
        "rejected_mutation_count": 18,
    }
    for selected in (certificate, trace):
        assert selected.expected["outcome"]["base_valid"] is True
        assert (
            selected.expected["outcome"]["all_authority_leaf_mutations_rejected"]
            is True
        )
        assert selected.expected["failure_code"] is None


def test_hard_coded_case_id_fails_when_manifest_changes_under_the_same_id() -> None:
    base = _case("manifest-deadline-at-boundary")
    assert base.request.manifest is not None
    unseen_manifest = deepcopy(base.request.manifest)
    unseen_manifest["protocol"]["collective_commit_policy"]["commit_window"][
        "run_deadline_steps"
    ] = 26
    unseen_expected = deepcopy(base.expected)
    unseen_expected["progress"] = {
        "elapsed_steps": 24,
        "run_deadline_steps": 26,
        "deadline_reached": False,
    }
    unseen_expected["outcome"] = {"kind": None}
    request = _request_with(
        base.request,
        manifest=unseen_manifest,
    )
    sensitivity_probe = CommitTckV2Case(
        request=request,
        expected=unseen_expected,
    )

    class HardCodedCaseIdAdapter:
        implementation_id = "malicious-case-id-table"

        def evaluate(self, value: CommitTckRequest) -> CommitTckResponse:
            assert value.id == base.request.id
            return CommitTckResponse(
                request_id=value.id,
                implementation_id=self.implementation_id,
                actual=deepcopy(base.expected),
            )

    malicious = run_commit_tck_v2(
        (sensitivity_probe,),
        adapter=HardCodedCaseIdAdapter(),
    )
    subject = run_commit_tck_v2((sensitivity_probe,))
    oracle = run_commit_tck_v2(
        (sensitivity_probe,),
        adapter=IndependentCommitSpecModelAdapter(),
    )

    assert malicious.ok is False
    assert malicious.results[0].actual["outcome"] == {"kind": "safe_fallback"}
    assert subject.ok is True
    assert oracle.ok is True
    assert subject.results[0].actual == oracle.results[0].actual == unseen_expected


def test_expected_echo_input_echo_and_constant_output_adapters_are_rejected() -> None:
    first, second = load_commit_tck_v2_cases()[:2]

    class EchoExpectedAdapter:
        implementation_id = "malicious-expected-echo"

        def evaluate(self, request: CommitTckRequest) -> CommitTckResponse:
            return CommitTckResponse(
                request_id=request.id,
                implementation_id=self.implementation_id,
                actual=getattr(request, "expected"),
            )

    class ConstantAdapter:
        implementation_id = "malicious-constant"

        def evaluate(self, request: CommitTckRequest) -> CommitTckResponse:
            return CommitTckResponse(
                request_id=request.id,
                implementation_id=self.implementation_id,
                actual=deepcopy(first.expected),
            )

    class EchoInputAdapter:
        implementation_id = "malicious-input-echo"

        def evaluate(self, request: CommitTckRequest) -> CommitTckResponse:
            return CommitTckResponse(
                request_id=request.id,
                implementation_id=self.implementation_id,
                actual=deepcopy(request.inputs),
            )

    echoed = run_commit_tck_v2((first,), adapter=EchoExpectedAdapter())
    input_echoed = run_commit_tck_v2((first,), adapter=EchoInputAdapter())
    constant = run_commit_tck_v2((first, second), adapter=ConstantAdapter())

    assert echoed.ok is False
    assert (
        echoed.results[0].actual["failure_code"].startswith("exception:AttributeError:")
    )
    assert input_echoed.ok is False
    assert (
        input_echoed.results[0]
        .actual["failure_code"]
        .startswith("exception:CommitTckV2ProtocolError:")
    )
    assert constant.ok is False
    assert constant.results[0].ok is True
    assert constant.results[1].ok is False


def test_jsonl_harness_rejects_malformed_out_of_order_and_timeout_adapters(
    tmp_path: Path,
) -> None:
    malformed = run_commit_tck_v2_jsonl(
        [sys.executable, "-c", "print('{')"],
        cases=load_commit_tck_v2_cases()[:1],
        timeout=1,
    )
    timeout = run_commit_tck_v2_jsonl(
        [sys.executable, "-c", "import time; time.sleep(1)"],
        cases=load_commit_tck_v2_cases()[:1],
        timeout=0.05,
    )

    script = tmp_path / "out_of_order_adapter.py"
    script.write_text(
        """\
import json
import sys

messages = [json.loads(line) for line in sys.stdin if line.strip()]
handshake = messages[0]
evaluations = messages[1:-1]
implementation_id = "malicious-out-of-order"
ack = {
    "message_type": "handshake_ack",
    "adapter_protocol": handshake["adapter_protocol"],
    "session_id": handshake["session_id"],
    "implementation_id": implementation_id,
    "implementation_version": "1",
    "supported_tck_versions": [handshake["tck_version"]],
    "supported_request_versions": [handshake["request_version"]],
    "supported_response_versions": [handshake["response_version"]],
    "supported_operations": handshake["operations"],
}
print(json.dumps(ack, separators=(",", ":")))
actual = {
    "metrics": {}, "roots": {}, "progress": None, "outcome": None,
    "trace_sequence": [], "certificate": None, "failure_code": None,
}
for message in reversed(evaluations):
    request = message["request"]
    result = {
        "message_type": "result",
        "session_id": handshake["session_id"],
        "response": {
            "response_version": "pheroos-commit-tck-response-v2",
            "request_id": request["id"],
            "implementation_id": implementation_id,
            "actual": actual,
        },
    }
    print(json.dumps(result, separators=(",", ":")))
print(json.dumps({
    "message_type": "closed", "session_id": handshake["session_id"]
}, separators=(",", ":")))
""",
        encoding="utf-8",
    )
    out_of_order = run_commit_tck_v2_jsonl(
        [sys.executable, str(script)],
        cases=load_commit_tck_v2_cases()[:2],
        timeout=1,
    )

    assert malformed.ok is False
    assert "protocol error" in malformed.protocol_error
    assert timeout.ok is False
    assert "timed out" in timeout.protocol_error
    assert out_of_order.ok is False
    assert "out of order" in out_of_order.protocol_error


def test_jsonl_session_has_no_cross_request_state_leakage(tmp_path: Path) -> None:
    base = _case("manifest-deadline-at-boundary")
    changed = _case("manifest-patched-run-deadline")
    repeated = CommitTckV2Case(
        request=_request_with(
            base.request,
            identifier="manifest-deadline-at-boundary-repeat",
            matrix_case=230,
        ),
        expected=deepcopy(base.expected),
    )

    report = run_commit_tck_v2_jsonl(
        _spec_command(),
        cases=(base, changed, repeated),
        cwd=tmp_path,
    )

    assert report.ok is True, report.protocol_error
    assert report.results[0].actual == report.results[2].actual
    assert report.results[0].actual != report.results[1].actual


def test_jsonl_versions_are_distinct_and_negotiated_explicitly() -> None:
    assert COMMIT_TCK_JSONL_PROTOCOL_VERSION == "pheroos-commit-tck-jsonl-v2"
    assert COMMIT_TCK_REQUEST_VERSION == "pheroos-commit-tck-request-v2"
    assert COMMIT_TCK_RESPONSE_VERSION == "pheroos-commit-tck-response-v2"
    assert (
        len(
            {
                COMMIT_TCK_JSONL_PROTOCOL_VERSION,
                COMMIT_TCK_REQUEST_VERSION,
                COMMIT_TCK_RESPONSE_VERSION,
                COMMIT_TCK_V2_VERSION,
            }
        )
        == 4
    )


def test_jsonl_server_rejects_incompatible_handshake_before_evaluation() -> None:
    handshake = {
        "message_type": "handshake",
        "adapter_protocol": COMMIT_TCK_JSONL_PROTOCOL_VERSION,
        "session_id": "incompatible-version",
        "tck_version": COMMIT_TCK_V2_VERSION,
        "request_version": "pheroos-commit-tck-request-v999",
        "response_version": COMMIT_TCK_RESPONSE_VERSION,
        "operations": ["fixed_point_multiply"],
    }
    input_stream = StringIO(json.dumps(handshake) + "\n")
    output_stream = StringIO()

    def unreachable(_request: CommitTckRequest) -> CommitTckResponse:
        raise AssertionError("incompatible handshake must not evaluate")

    with pytest.raises(CommitTckV2ProtocolError, match="request version"):
        serve_commit_tck_v2_jsonl(
            unreachable,
            implementation_id="handshake-test",
            implementation_version="1",
            supported_operations=("fixed_point_multiply",),
            input_stream=input_stream,
            output_stream=output_stream,
        )

    assert output_stream.getvalue() == ""


def test_v2_artifact_loader_rejects_malformed_roots_templates_and_cases(
    tmp_path: Path,
) -> None:
    checked = json.loads(V2_ARTIFACT.read_text(encoding="utf-8"))

    def load_payload(payload: object, name: str) -> tuple[CommitTckV2Case, ...]:
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return load_commit_tck_v2_cases(path)

    malformed_payloads: tuple[tuple[object, str, str], ...] = (
        ([], "root-array", "artifact must be an object"),
        (
            {key: value for key, value in checked.items() if key != "cases"},
            "root-fields",
            "artifact fields are invalid",
        ),
        (
            {**checked, "tck_version": "pheroos-commit-tck-v999"},
            "tck-version",
            "artifact version is unsupported",
        ),
        (
            {**checked, "adapter_protocol": "pheroos-jsonl-v999"},
            "adapter-version",
            "adapter protocol is unsupported",
        ),
        (
            {**checked, "manifest_templates": {}},
            "templates-empty",
            "manifest_templates must be a non-empty object",
        ),
        (
            {**checked, "manifest_templates": []},
            "templates-array",
            "manifest_templates must be a non-empty object",
        ),
        (
            {**checked, "manifest_templates": {"": {}}},
            "template-name",
            "manifest template is invalid",
        ),
        (
            {**checked, "manifest_templates": {"invalid": []}},
            "template-value",
            "manifest template is invalid",
        ),
        (
            {**checked, "cases": []},
            "cases-empty",
            "cases must be a non-empty array",
        ),
        (
            {**checked, "cases": {}},
            "cases-object",
            "cases must be a non-empty array",
        ),
    )
    for payload, name, message in malformed_payloads:
        with pytest.raises(CommitTckV2ProtocolError, match=message):
            load_payload(payload, name)

    malformed = deepcopy(checked)
    malformed["cases"][0]["matrix_case"] = 0
    with pytest.raises(CommitTckV2ProtocolError, match="matrix_case must be positive"):
        load_payload(malformed, "matrix-case")

    malformed = deepcopy(checked)
    malformed["cases"][1]["id"] = malformed["cases"][0]["id"]
    with pytest.raises(CommitTckV2ProtocolError, match="must be unique"):
        load_payload(malformed, "duplicate-id")

    malformed = deepcopy(checked)
    malformed["cases"][2]["manifest_template"] = "missing"
    with pytest.raises(CommitTckV2ProtocolError, match="template is missing"):
        load_payload(malformed, "missing-template")


def test_v2_artifact_manifest_patches_are_exact_and_path_checked(
    tmp_path: Path,
) -> None:
    checked = json.loads(V2_ARTIFACT.read_text(encoding="utf-8"))

    def load_payload(payload: object, name: str) -> tuple[CommitTckV2Case, ...]:
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return load_commit_tck_v2_cases(path)

    malformed = deepcopy(checked)
    malformed["cases"][2]["manifest_patches"] = {}
    with pytest.raises(CommitTckV2ProtocolError, match="patches must be an array"):
        load_payload(malformed, "patches-object")

    malformed = deepcopy(checked)
    malformed["cases"][0]["manifest_patches"] = [
        {"path": ["id"], "replacement": "invalid"}
    ]
    with pytest.raises(CommitTckV2ProtocolError, match="require a template"):
        load_payload(malformed, "patch-without-template")

    malformed = deepcopy(checked)
    malformed["cases"][2]["manifest_patches"] = [None]
    with pytest.raises(CommitTckV2ProtocolError, match="patch must be an object"):
        load_payload(malformed, "patch-not-object")

    malformed = deepcopy(checked)
    malformed["cases"][2]["manifest_patches"] = [{"path": [], "replacement": "invalid"}]
    with pytest.raises(CommitTckV2ProtocolError, match="path must be non-empty"):
        load_payload(malformed, "patch-empty-path")

    malformed = deepcopy(checked)
    malformed["cases"][2]["manifest_patches"] = [
        {"path": ["missing"], "replacement": "invalid"}
    ]
    with pytest.raises(CommitTckV2ProtocolError, match="patch path is missing"):
        load_payload(malformed, "patch-missing-path")

    patched = deepcopy(checked)
    patched["cases"][2]["manifest_patches"] = [
        {
            "path": ["protocol", "targets", 0, "description"],
            "replacement": "Patched target description",
        }
    ]
    loaded = load_payload(patched, "patch-list-path")
    assert loaded[2].request.manifest is not None
    assert loaded[2].request.manifest["protocol"]["targets"][0]["description"] == (
        "Patched target description"
    )


def test_in_process_v2_harness_rejects_adapter_identity_and_response_mismatch() -> None:
    selected = load_commit_tck_v2_cases()[0]

    class MissingIdentityAdapter:
        def evaluate(self, request: CommitTckRequest) -> CommitTckResponse:
            raise AssertionError(f"must not evaluate {request.id}")

    missing_identity = run_commit_tck_v2(
        (selected,),
        adapter=MissingIdentityAdapter(),  # type: ignore[arg-type]
    )
    assert missing_identity.ok is False
    assert "implementation_id is missing" in missing_identity.protocol_error

    class InvalidResponseAdapter:
        implementation_id = "invalid-response"

        def evaluate(self, request: CommitTckRequest) -> object:
            del request
            return object()

    invalid_response = run_commit_tck_v2(
        (selected,),
        adapter=InvalidResponseAdapter(),  # type: ignore[arg-type]
    )
    assert invalid_response.ok is False
    assert "invalid response type" in invalid_response.results[0].actual["failure_code"]

    class WrongRequestAdapter:
        implementation_id = "wrong-request"

        def evaluate(self, request: CommitTckRequest) -> CommitTckResponse:
            return CommitTckResponse(
                request_id=f"{request.id}:other",
                implementation_id=self.implementation_id,
                actual=deepcopy(selected.expected),
            )

    wrong_request = run_commit_tck_v2((selected,), adapter=WrongRequestAdapter())
    assert "request id mismatch" in wrong_request.results[0].actual["failure_code"]

    class WrongImplementationAdapter:
        implementation_id = "declared-implementation"

        def evaluate(self, request: CommitTckRequest) -> CommitTckResponse:
            return CommitTckResponse(
                request_id=request.id,
                implementation_id="different-implementation",
                actual=deepcopy(selected.expected),
            )

    wrong_implementation = run_commit_tck_v2(
        (selected,),
        adapter=WrongImplementationAdapter(),
    )
    assert (
        "implementation id mismatch"
        in (wrong_implementation.results[0].actual["failure_code"])
    )


def test_public_v2_adapter_rejects_unknown_operation_and_exact_type_violations() -> (
    None
):
    adapter = PheroosPublicCommitTckV2Adapter()
    multiply = _case("fixed-point-multiply-floor")

    with pytest.raises(CommitTckV2ProtocolError, match="operation is unsupported"):
        adapter.evaluate(_request_with_inputs(multiply.request, operation="unknown"))
    with pytest.raises(
        CommitTckV2ProtocolError, match="scale must be an exact integer"
    ):
        adapter.evaluate(_request_with_inputs(multiply.request, scale=True))

    deadline = _case("manifest-deadline-at-boundary")
    deadline_payload = deadline.request.to_dict()
    deadline_payload["manifest"] = None
    with pytest.raises(CommitTckV2ProtocolError, match="requires a manifest"):
        adapter.evaluate(CommitTckRequest.from_dict(deadline_payload))
    with pytest.raises(CommitTckV2ProtocolError, match="must be non-negative"):
        adapter.evaluate(_request_with_inputs(deadline.request, elapsed_steps=-1))
    with pytest.raises(CommitTckV2ProtocolError, match="must be an exact boolean"):
        adapter.evaluate(_request_with_inputs(deadline.request, blocked="false"))

    threshold = _case("manifest-threshold-ready")
    with pytest.raises(CommitTckV2ProtocolError, match="risk_band is unsupported"):
        adapter.evaluate(_request_with_inputs(threshold.request, risk_band="unknown"))
    with pytest.raises(CommitTckV2ProtocolError, match="challenge_categories"):
        adapter.evaluate(
            _request_with_inputs(
                threshold.request,
                challenge_categories=["duplicate", "duplicate"],
            )
        )
    with pytest.raises(CommitTckV2ProtocolError, match="must be non-negative"):
        adapter.evaluate(_request_with_inputs(threshold.request, leader_margin=-1))

    attention = _case("attention-truth-invariant-weight-one")
    with pytest.raises(CommitTckV2ProtocolError, match="at least two candidates"):
        adapter.evaluate(
            _request_with_inputs(
                attention.request,
                candidate_evidence={"candidate:alpha": 1},
            )
        )
    with pytest.raises(CommitTckV2ProtocolError, match="must be declared"):
        adapter.evaluate(
            _request_with_inputs(
                attention.request,
                attention_candidate="candidate:missing",
            )
        )


def test_jsonl_v2_harness_rejects_invalid_inputs_processes_and_encoding() -> None:
    selected = load_commit_tck_v2_cases()[:1]

    for command, timeout, session_id, message in (
        ([], 1.0, "session", "command is invalid"),
        ([sys.executable], 1.0, " session ", "session id is invalid"),
        ([sys.executable], 0.0, "session", "timeout is invalid"),
    ):
        report = run_commit_tck_v2_jsonl(
            command,
            cases=selected,
            timeout=timeout,
            session_id=session_id,
        )
        assert report.ok is False
        assert message in report.protocol_error

    missing = run_commit_tck_v2_jsonl(
        ["/definitely/missing/pheroos-commit-tck-adapter"],
        cases=selected,
        timeout=1,
    )
    assert missing.ok is False
    assert "could not start" in missing.protocol_error

    invalid_encoding = run_commit_tck_v2_jsonl(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(bytes([255]))",
        ],
        cases=selected,
        timeout=1,
    )
    assert invalid_encoding.ok is False
    assert "not valid UTF-8" in invalid_encoding.protocol_error

    exited = run_commit_tck_v2_jsonl(
        [
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('adapter failed'); raise SystemExit(7)",
        ],
        cases=selected,
        timeout=1,
    )
    assert exited.ok is False
    assert "exited with 7: adapter failed" in exited.protocol_error

    exited_without_detail = run_commit_tck_v2_jsonl(
        [sys.executable, "-c", "raise SystemExit(8)"],
        cases=selected,
        timeout=1,
    )
    assert exited_without_detail.ok is False
    assert "exited with 8" in exited_without_detail.protocol_error

    oversized = run_commit_tck_v2_jsonl(
        [sys.executable, "-c", "print('x' * (4 * 1024 * 1024 + 1))"],
        cases=selected,
        timeout=2,
    )
    assert oversized.ok is False
    assert "output is too large" in oversized.protocol_error


def test_v2_artifact_root_accepts_an_explicit_artifact_path(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_bytes(b"explicit-artifact")

    assert commit_tck_v2_artifact_root(artifact) == (
        "sha256:" + sha256(b"explicit-artifact").hexdigest()
    )


def test_commit_tck_request_wire_rejects_invalid_fields_types_and_values() -> None:
    request = load_commit_tck_v2_cases()[0].request
    baseline = request.to_dict()
    assert CommitTckRequest.from_dict(baseline).to_dict() == baseline

    for field, value, message in (
        ("request_version", "invalid", "request version is unsupported"),
        ("id", " ", "request id must be a non-blank string"),
        ("tck_version", "", "request TCK version must be a non-blank string"),
        ("title", None, "request title must be a non-blank string"),
        ("profile", " value ", "request profile must be a non-blank string"),
        ("matrix_case", True, "matrix_case must be a positive integer"),
        ("matrix_case", 0, "matrix_case must be a positive integer"),
        ("manifest", [], "manifest must be an object or null"),
        ("prior_authoritative_state", [], "prior state must be an object"),
        ("inputs", [], "inputs must be an object"),
    ):
        malformed = deepcopy(baseline)
        malformed[field] = value
        with pytest.raises(CommitTckV2ProtocolError, match=message):
            CommitTckRequest.from_dict(malformed)

    malformed = deepcopy(baseline)
    malformed["inputs"]["operation"] = ""
    with pytest.raises(CommitTckV2ProtocolError, match="operation"):
        CommitTckRequest.from_dict(malformed)

    with pytest.raises(CommitTckV2ProtocolError, match="must be an object"):
        CommitTckRequest.from_dict([])
    malformed = deepcopy(baseline)
    malformed["unexpected"] = True
    with pytest.raises(CommitTckV2ProtocolError, match="fields are invalid"):
        CommitTckRequest.from_dict(malformed)

    for invalid in (float("nan"), object()):
        malformed = deepcopy(baseline)
        malformed["inputs"]["invalid"] = invalid
        with pytest.raises(CommitTckV2ProtocolError, match="provider-neutral JSON"):
            CommitTckRequest.from_dict(malformed)


def test_commit_tck_response_and_actual_wire_reject_invalid_shapes() -> None:
    actual = empty_commit_tck_actual(
        metrics={"value": 1},
        roots={"root": "sha256:" + "1" * 64},
        progress={"step": 1},
        outcome={"ready": True},
        trace_sequence=("commit",),
        certificate={"verified": True},
        failure_code="expected-failure",
    )
    response = CommitTckResponse(
        request_id="request:1",
        implementation_id="implementation:1",
        actual=actual,
    )
    assert (
        CommitTckResponse.from_dict(response.to_dict()).to_dict() == response.to_dict()
    )

    for field, value, message in (
        ("response_version", "invalid", "response version is unsupported"),
        ("request_id", "", "request_id must be a non-blank string"),
        ("implementation_id", None, "implementation_id must be a non-blank string"),
    ):
        malformed = response.to_dict()
        malformed[field] = value
        with pytest.raises(CommitTckV2ProtocolError, match=message):
            CommitTckResponse.from_dict(malformed)

    with pytest.raises(CommitTckV2ProtocolError, match="must be an object"):
        CommitTckResponse.from_dict([])
    malformed = response.to_dict()
    del malformed["actual"]
    with pytest.raises(CommitTckV2ProtocolError, match="fields are invalid"):
        CommitTckResponse.from_dict(malformed)

    invalid_actual_fields: tuple[tuple[str, object, str], ...] = (
        ("metrics", [], "metrics and roots must be objects"),
        ("roots", [], "metrics and roots must be objects"),
        ("progress", [], "progress must be an object or null"),
        ("outcome", [], "outcome must be an object or null"),
        ("certificate", [], "certificate must be an object or null"),
        ("trace_sequence", {}, "trace_sequence must be a string array"),
        ("trace_sequence", [""], "trace_sequence must be a string array"),
        ("trace_sequence", [7], "trace_sequence must be a string array"),
        ("failure_code", "", "failure_code must be a string or null"),
        ("failure_code", 7, "failure_code must be a string or null"),
    )
    for field, invalid_value, message in invalid_actual_fields:
        malformed = deepcopy(actual)
        malformed[field] = invalid_value
        with pytest.raises(CommitTckV2ProtocolError, match=message):
            validate_commit_tck_actual(malformed)

    malformed = deepcopy(actual)
    malformed["metrics"]["invalid"] = float("inf")
    with pytest.raises(CommitTckV2ProtocolError, match="provider-neutral JSON"):
        validate_commit_tck_actual(malformed)


def test_commit_tck_json_decoder_rejects_duplicates_nonfinite_and_invalid_json() -> (
    None
):
    assert loads_commit_tck_json('{"value":1}') == {"value": 1}

    for encoded, message in (
        ('{"value":1,"value":2}', "duplicate key"),
        ('{"value":NaN}', "non-finite number"),
        ("{", "JSON is invalid"),
    ):
        with pytest.raises(CommitTckV2ProtocolError, match=message):
            loads_commit_tck_json(encoded)

    with pytest.raises(CommitTckV2ProtocolError, match="JSON is invalid"):
        loads_commit_tck_json(None)  # type: ignore[arg-type]


def test_commit_tck_jsonl_server_completes_a_strict_session() -> None:
    request = _case("fixed-point-multiply-floor").request
    output = StringIO()

    def evaluate(value: CommitTckRequest) -> CommitTckResponse:
        return CommitTckResponse(
            request_id=value.id,
            implementation_id="server-implementation",
            actual=empty_commit_tck_actual(metrics={"evaluated": 1}),
        )

    serve_commit_tck_v2_jsonl(
        evaluate,
        implementation_id="server-implementation",
        implementation_version="1",
        supported_operations=("fixed_point_multiply",),
        input_stream=_jsonl_input(
            _jsonl_handshake(),
            {
                "message_type": "evaluate",
                "session_id": "protocol-session",
                "request": request.to_dict(),
            },
            {"message_type": "close", "session_id": "protocol-session"},
        ),
        output_stream=output,
    )

    messages = [loads_commit_tck_json(line) for line in output.getvalue().splitlines()]
    assert [message["message_type"] for message in messages] == [
        "handshake_ack",
        "result",
        "closed",
    ]
    assert messages[0]["supported_operations"] == ["fixed_point_multiply"]
    assert messages[1]["response"]["actual"]["metrics"] == {"evaluated": 1}


def test_commit_tck_jsonl_server_rejects_invalid_configuration_and_handshake() -> None:
    def unreachable(request: CommitTckRequest) -> CommitTckResponse:
        raise AssertionError(f"must not evaluate {request.id}")

    for implementation_id, implementation_version, operations, message in (
        ("", "1", ("fixed_point_multiply",), "implementation id"),
        ("implementation", "", ("fixed_point_multiply",), "implementation version"),
        ("implementation", "1", (), "supported operations"),
        (
            "implementation",
            "1",
            ("fixed_point_multiply", "fixed_point_multiply"),
            "supported operations",
        ),
    ):
        with pytest.raises(CommitTckV2ProtocolError, match=message):
            serve_commit_tck_v2_jsonl(
                unreachable,
                implementation_id=implementation_id,
                implementation_version=implementation_version,
                supported_operations=operations,
                input_stream=_jsonl_input(_jsonl_handshake()),
                output_stream=StringIO(),
            )

    for stream, message in (
        (StringIO(), "handshake is missing"),
        (StringIO(" \n"), "handshake must not be blank"),
    ):
        with pytest.raises(CommitTckV2ProtocolError, match=message):
            serve_commit_tck_v2_jsonl(
                unreachable,
                implementation_id="implementation",
                implementation_version="1",
                supported_operations=("fixed_point_multiply",),
                input_stream=stream,
                output_stream=StringIO(),
            )

    malformed_handshakes = (
        ({"message_type": "handshake"}, "fields are invalid"),
        ({**_jsonl_handshake(), "message_type": "evaluate"}, "first message"),
        ({**_jsonl_handshake(), "adapter_protocol": "invalid"}, "JSONL protocol"),
        ({**_jsonl_handshake(), "response_version": "invalid"}, "response version"),
        ({**_jsonl_handshake(), "tck_version": "invalid"}, "TCK version"),
        ({**_jsonl_handshake(), "session_id": ""}, "session id"),
        ({**_jsonl_handshake(), "operations": []}, "requested operations"),
        (
            {
                **_jsonl_handshake(),
                "operations": ["fixed_point_multiply", "fixed_point_multiply"],
            },
            "requested operations",
        ),
        ({**_jsonl_handshake(), "operations": ["unknown"]}, "operation is unsupported"),
    )
    for handshake, message in malformed_handshakes:
        with pytest.raises(CommitTckV2ProtocolError, match=message):
            serve_commit_tck_v2_jsonl(
                unreachable,
                implementation_id="implementation",
                implementation_version="1",
                supported_operations=("fixed_point_multiply",),
                input_stream=_jsonl_input(handshake),
                output_stream=StringIO(),
            )


def test_commit_tck_jsonl_server_rejects_invalid_session_messages() -> None:
    request = _case("fixed-point-multiply-floor").request

    def valid_response(value: CommitTckRequest) -> CommitTckResponse:
        return CommitTckResponse(
            request_id=value.id,
            implementation_id="implementation",
            actual=empty_commit_tck_actual(),
        )

    def run_messages(
        *messages: object,
        evaluator: object = valid_response,
    ) -> None:
        serve_commit_tck_v2_jsonl(
            evaluator,  # type: ignore[arg-type]
            implementation_id="implementation",
            implementation_version="1",
            supported_operations=("fixed_point_multiply",),
            input_stream=_jsonl_input(_jsonl_handshake(), *messages),
            output_stream=StringIO(),
        )

    with pytest.raises(CommitTckV2ProtocolError, match="ended before close"):
        run_messages()
    with pytest.raises(CommitTckV2ProtocolError, match="line must not be blank"):
        serve_commit_tck_v2_jsonl(
            valid_response,
            implementation_id="implementation",
            implementation_version="1",
            supported_operations=("fixed_point_multiply",),
            input_stream=StringIO(json.dumps(_jsonl_handshake()) + "\n\n"),
            output_stream=StringIO(),
        )
    with pytest.raises(CommitTckV2ProtocolError, match="message must be an object"):
        run_messages([])
    with pytest.raises(CommitTckV2ProtocolError, match="message type is unsupported"):
        run_messages({"message_type": "unknown"})
    with pytest.raises(CommitTckV2ProtocolError, match="evaluate envelope.*fields"):
        run_messages({"message_type": "evaluate"})
    with pytest.raises(CommitTckV2ProtocolError, match="session id mismatch"):
        run_messages(
            {
                "message_type": "evaluate",
                "session_id": "different",
                "request": request.to_dict(),
            }
        )

    wrong_tck = request.to_dict()
    wrong_tck["tck_version"] = "different-tck"
    with pytest.raises(CommitTckV2ProtocolError, match="request version mismatch"):
        run_messages(
            {
                "message_type": "evaluate",
                "session_id": "protocol-session",
                "request": wrong_tck,
            }
        )

    wrong_operation = request.to_dict()
    wrong_operation["inputs"]["operation"] = "unknown"
    with pytest.raises(CommitTckV2ProtocolError, match="operation is unsupported"):
        run_messages(
            {
                "message_type": "evaluate",
                "session_id": "protocol-session",
                "request": wrong_operation,
            }
        )

    evaluation = {
        "message_type": "evaluate",
        "session_id": "protocol-session",
        "request": request.to_dict(),
    }

    def invalid_type(value: CommitTckRequest) -> object:
        del value
        return object()

    with pytest.raises(CommitTckV2ProtocolError, match="invalid response type"):
        run_messages(evaluation, evaluator=invalid_type)

    def wrong_request(value: CommitTckRequest) -> CommitTckResponse:
        return CommitTckResponse(
            request_id=f"{value.id}:wrong",
            implementation_id="implementation",
            actual=empty_commit_tck_actual(),
        )

    with pytest.raises(CommitTckV2ProtocolError, match="request id mismatch"):
        run_messages(evaluation, evaluator=wrong_request)

    def wrong_implementation(value: CommitTckRequest) -> CommitTckResponse:
        return CommitTckResponse(
            request_id=value.id,
            implementation_id="wrong",
            actual=empty_commit_tck_actual(),
        )

    with pytest.raises(CommitTckV2ProtocolError, match="implementation id mismatch"):
        run_messages(evaluation, evaluator=wrong_implementation)

    with pytest.raises(CommitTckV2ProtocolError, match="session id mismatch"):
        run_messages({"message_type": "close", "session_id": "different"})


def test_independent_spec_model_rejects_unknown_and_invalid_numeric_inputs() -> None:
    adapter = IndependentCommitSpecModelAdapter()
    multiply = _case("fixed-point-multiply-floor")
    maximum = (2**53) - 1

    with pytest.raises(CommitTckV2ProtocolError, match="operation is unsupported"):
        adapter.evaluate(_request_with_inputs(multiply.request, operation="unknown"))
    with pytest.raises(CommitTckV2ProtocolError, match="product exceeds"):
        adapter.evaluate(
            _request_with_inputs(
                multiply.request,
                left=maximum,
                right=maximum,
                scale=1,
            )
        )
    with pytest.raises(CommitTckV2ProtocolError, match="non-negative exact integer"):
        adapter.evaluate(_request_with_inputs(multiply.request, left=-1))
    with pytest.raises(CommitTckV2ProtocolError, match="authority bound"):
        adapter.evaluate(_request_with_inputs(multiply.request, left=maximum + 1))
    with pytest.raises(CommitTckV2ProtocolError, match="scale must be positive"):
        adapter.evaluate(_request_with_inputs(multiply.request, scale=0))

    ratio = _case("fixed-point-ratio-floor")
    zero_denominator = adapter.evaluate(
        _request_with_inputs(
            ratio.request,
            numerator=0,
            denominator=0,
            scale=1_000_000,
        )
    )
    assert zero_denominator.actual["metrics"] == {"value": 1_000_000}
    with pytest.raises(CommitTckV2ProtocolError, match="cannot exceed denominator"):
        adapter.evaluate(
            _request_with_inputs(ratio.request, numerator=2, denominator=1)
        )


def test_independent_spec_model_rejects_malformed_manifest_semantics() -> None:
    adapter = IndependentCommitSpecModelAdapter()

    deadline = _case("manifest-deadline-at-boundary")
    payload = deadline.request.to_dict()
    payload["manifest"] = None
    with pytest.raises(CommitTckV2ProtocolError, match="manifest must be an object"):
        adapter.evaluate(CommitTckRequest.from_dict(payload))

    payload = deadline.request.to_dict()
    payload["manifest"]["protocol"]["collective_commit_policy"]["terminal_outcome"][
        "deadline_outcome"
    ] = "unknown"
    with pytest.raises(CommitTckV2ProtocolError, match="deadline_outcome"):
        adapter.evaluate(CommitTckRequest.from_dict(payload))
    with pytest.raises(CommitTckV2ProtocolError, match="exact boolean"):
        adapter.evaluate(_request_with_inputs(deadline.request, invalid="false"))

    threshold = _case("manifest-threshold-ready")
    with pytest.raises(CommitTckV2ProtocolError, match="risk_band"):
        adapter.evaluate(_request_with_inputs(threshold.request, risk_band=""))
    with pytest.raises(CommitTckV2ProtocolError, match="unique non-blank"):
        adapter.evaluate(
            _request_with_inputs(
                threshold.request,
                challenge_categories=["duplicate", "duplicate"],
            )
        )

    assurance = _case("manifest-assurance-advisory")
    payload = assurance.request.to_dict()
    payload["manifest"]["protocol"]["collective_commit_policy"]["assurance"] = "unknown"
    with pytest.raises(CommitTckV2ProtocolError, match="assurance is unsupported"):
        adapter.evaluate(CommitTckRequest.from_dict(payload))

    attention = _case("attention-truth-invariant-weight-one")
    with pytest.raises(CommitTckV2ProtocolError, match="at least two candidates"):
        adapter.evaluate(
            _request_with_inputs(
                attention.request,
                candidate_evidence={"candidate:alpha": 1},
            )
        )
    with pytest.raises(CommitTckV2ProtocolError, match="must be declared"):
        adapter.evaluate(
            _request_with_inputs(
                attention.request,
                attention_candidate="candidate:missing",
            )
        )
    payload = attention.request.to_dict()
    payload["manifest"]["protocol"]["collective_decision_policy"][
        "pheromone_positive_weight"
    ] = True
    with pytest.raises(CommitTckV2ProtocolError, match="positive_weight is invalid"):
        adapter.evaluate(CommitTckRequest.from_dict(payload))


def test_independent_spec_model_reports_every_distributed_policy_failure() -> None:
    adapter = IndependentCommitSpecModelAdapter()
    selected = _case("manifest-distributed-quorum-ready")
    payload = selected.request.to_dict()
    policy = payload["manifest"]["protocol"]["collective_commit_policy"]
    distributed = policy["distributed"]
    policy["assurance"] = "advisory"
    distributed.update(
        {
            "fault_model": "invalid",
            "membership_mode": "invalid",
            "conflict_rule": "invalid",
            "membership_size": 3,
            "max_byzantine_faults": 1,
            "witness_quorum": 2,
            "minimum_failure_domain_diversity": 3,
        }
    )

    result = adapter.evaluate(CommitTckRequest.from_dict(payload)).actual

    assert {
        "commit_distributed_policy_inactive",
        "commit_fault_model_invalid",
        "commit_membership_mode_invalid",
        "commit_conflict_rule_invalid",
        "commit_byzantine_membership_invalid",
        "commit_quorum_intersection_invalid",
        "commit_failure_domain_diversity_unreachable",
    } <= set(result["outcome"]["diagnostic_codes"])

    payload = selected.request.to_dict()
    distributed = payload["manifest"]["protocol"]["collective_commit_policy"][
        "distributed"
    ]
    distributed["membership_size"] = 3
    distributed["max_byzantine_faults"] = 1
    distributed["witness_quorum"] = 3
    result = adapter.evaluate(CommitTckRequest.from_dict(payload)).actual
    assert "commit_witness_quorum_too_large" in result["outcome"]["diagnostic_codes"]


def test_independent_spec_model_fails_closed_on_noncanonical_authority_leaves() -> None:
    adapter = IndependentCommitSpecModelAdapter()
    certificate = _case("certificate-authority-leaf-binding")

    duplicate_refs = certificate.request.to_dict()
    refs = duplicate_refs["inputs"]["certificate_payload"]["issuer_attestation_refs"]
    refs.append(refs[0])
    duplicate_result = adapter.evaluate(
        CommitTckRequest.from_dict(duplicate_refs)
    ).actual
    assert duplicate_result["outcome"]["base_valid"] is False

    extra_scalars = certificate.request.to_dict()
    extra_scalars["inputs"]["certificate_payload"].update(
        {"extra_none": None, "extra_boolean": True}
    )
    scalar_result = adapter.evaluate(CommitTckRequest.from_dict(extra_scalars)).actual
    assert scalar_result["metrics"]["authority_leaf_count"] == 53
    assert scalar_result["outcome"]["base_valid"] is False

    float_leaf = certificate.request.to_dict()
    float_leaf["inputs"]["certificate_payload"]["invalid_float"] = 1.5
    with pytest.raises(CommitTckV2ProtocolError, match="non-JSON scalar"):
        adapter.evaluate(CommitTckRequest.from_dict(float_leaf))

    attention = _case("attention-truth-invariant-weight-one")
    with pytest.raises(CommitTckV2ProtocolError, match="integer bound"):
        adapter.evaluate(
            _request_with_inputs(
                attention.request,
                candidate_evidence={
                    "candidate:alpha": 2**53,
                    "candidate:beta": 1,
                },
            )
        )
