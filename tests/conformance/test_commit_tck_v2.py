from __future__ import annotations

import ast
from copy import deepcopy
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import pytest

from pheroos.conformance.commit_tck import commit_tck_artifact_root
from pheroos.conformance.commit_tck_v2 import (
    CommitTckV2Case,
    PheroosPublicCommitTckV2Adapter,
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
    serve_commit_tck_v2_jsonl,
)
from pheroos.conformance.commit_tck_v2_spec_adapter import (
    IndependentCommitSpecModelAdapter,
    SPEC_MODEL_IMPLEMENTATION_ID,
)


ROOT = Path(__file__).resolve().parents[2]
V1_ARTIFACT = ROOT / "pheroos" / "conformance" / "tck" / "commit-integrity-v1.json"
V2_ARTIFACT = ROOT / "pheroos" / "conformance" / "tck" / "commit-integrity-v2.json"
SPEC_ADAPTER = "pheroos.conformance.commit_tck_v2_spec_adapter"
V1_FILE_SHA256 = "9255ed7e1298841baaaeee8b139a7ba86df457493dd30d6d7312ce600a1d41e3"
V1_SEMANTIC_ROOT = (
    "sha256:0e9cd7fd56087d5cc4987d5a7ed056ed6649512c30ee486685e3dbd45e8b7abe"
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
        (ROOT / "schemas" / "commit-tck-v2.schema.json").read_text(
            encoding="utf-8"
        )
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
    assert all(item.implementation_id == SPEC_MODEL_IMPLEMENTATION_ID for item in report.results)


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
        base.request.manifest["protocol"]["collective_commit_policy"][
            "commit_window"
        ]["run_deadline_steps"]
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
    assert [item.expected["outcome"]["certificate_mode"] for item in assurance_cases] == [
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
        assert selected.expected["outcome"]["attention_top_candidate"] == "candidate:beta"
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
            selected.expected["outcome"][
                "all_authority_leaf_mutations_rejected"
            ]
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
    assert echoed.results[0].actual["failure_code"].startswith(
        "exception:AttributeError:"
    )
    assert input_echoed.ok is False
    assert input_echoed.results[0].actual["failure_code"].startswith(
        "exception:CommitTckV2ProtocolError:"
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
    assert len(
        {
            COMMIT_TCK_JSONL_PROTOCOL_VERSION,
            COMMIT_TCK_REQUEST_VERSION,
            COMMIT_TCK_RESPONSE_VERSION,
            COMMIT_TCK_V2_VERSION,
        }
    ) == 4


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
