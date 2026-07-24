"""Declarative Commit TCK v2 harness and PheroOS public-ABI adapter."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from importlib import resources
from pathlib import Path
from typing import Any, Protocol

from pheroos.conformance.commit_tck_v2_protocol import (
    COMMIT_TCK_JSONL_PROTOCOL_VERSION,
    COMMIT_TCK_REQUEST_VERSION,
    COMMIT_TCK_RESPONSE_VERSION,
    COMMIT_TCK_V2_VERSION,
    CommitTckRequest,
    CommitTckResponse,
    CommitTckV2ProtocolError,
    empty_commit_tck_actual,
    loads_commit_tck_json,
    validate_commit_tck_actual,
)
from pheroos.conformance.profile import profile_for_manifest
from pheroos.governance.commit_numeric import multiply_scaled, scaled_ratio
from pheroos.governance.commit_semantics import select_terminal_outcome_kind
from pheroos.governance.historical_certificate import (
    verify_evidence_commit_certificate,
)
from pheroos.protocol import (
    commit_payload_fingerprint,
    validate_capability_manifest,
)
from pheroos.protocol.manifest import capability_manifest_from_dict
from pheroos.trace import TraceEvent, commit_trace_event_id

COMMIT_TCK_V2_ARTIFACT = resources.files("pheroos.conformance").joinpath(
    "tck",
    "commit-integrity-v2.json",
)
PHEROOS_TCK_V2_IMPLEMENTATION_ID = "pheroos-public-abi-v2"
PHEROOS_TCK_V2_OPERATIONS = (
    "fixed_point_multiply",
    "fixed_point_ratio",
    "manifest_deadline_outcome",
    "manifest_threshold_assessment",
    "manifest_assurance_requirements",
    "manifest_distributed_quorum",
    "attention_truth_invariance",
    "certificate_leaf_binding",
    "trace_leaf_binding",
)

_ARTIFACT_FIELDS = frozenset(
    {"tck_version", "adapter_protocol", "manifest_templates", "cases"}
)
_CASE_FIELDS = frozenset(
    {
        "id",
        "matrix_case",
        "title",
        "manifest_template",
        "manifest_patches",
        "profile",
        "prior_authoritative_state",
        "inputs",
        "expected",
    }
)
_PATCH_FIELDS = frozenset({"path", "replacement"})
_HANDSHAKE_ACK_FIELDS = frozenset(
    {
        "message_type",
        "adapter_protocol",
        "session_id",
        "implementation_id",
        "implementation_version",
        "supported_tck_versions",
        "supported_request_versions",
        "supported_response_versions",
        "supported_operations",
    }
)


@dataclass(frozen=True, slots=True)
class CommitTckV2Case:
    request: CommitTckRequest
    expected: dict[str, Any]

    def __post_init__(self) -> None:
        validate_commit_tck_actual(self.expected)
        object.__setattr__(self, "expected", deepcopy(self.expected))


@dataclass(frozen=True, slots=True)
class CommitTckV2Result:
    request_id: str
    matrix_case: int
    implementation_id: str
    ok: bool
    expected: dict[str, Any]
    actual: dict[str, Any]
    detail: str = ""


@dataclass(frozen=True, slots=True)
class CommitTckV2Report:
    tck_version: str
    implementation_id: str
    results: tuple[CommitTckV2Result, ...]
    protocol_error: str = ""

    @property
    def ok(self) -> bool:
        return (
            bool(self.results)
            and not self.protocol_error
            and all(item.ok for item in self.results)
        )


class CommitTckV2Adapter(Protocol):
    implementation_id: str

    def evaluate(self, request: CommitTckRequest) -> CommitTckResponse: ...


class PheroosPublicCommitTckV2Adapter:
    """V2 subject adapter composed from the installed public PheroOS ABI."""

    implementation_id = PHEROOS_TCK_V2_IMPLEMENTATION_ID

    def evaluate(self, request: CommitTckRequest) -> CommitTckResponse:
        operation = request.inputs["operation"]
        if operation == "fixed_point_multiply":
            actual = empty_commit_tck_actual(
                metrics={
                    "value": multiply_scaled(
                        request.inputs.get("left"),
                        request.inputs.get("right"),
                        scale=_exact_integer(request.inputs.get("scale"), "scale"),
                    )
                }
            )
        elif operation == "fixed_point_ratio":
            actual = empty_commit_tck_actual(
                metrics={
                    "value": scaled_ratio(
                        request.inputs.get("numerator"),
                        request.inputs.get("denominator"),
                        scale=_exact_integer(request.inputs.get("scale"), "scale"),
                    )
                }
            )
        elif operation == "manifest_deadline_outcome":
            actual = _pheroos_manifest_deadline_outcome(request)
        elif operation == "manifest_threshold_assessment":
            actual = _pheroos_manifest_threshold_assessment(request)
        elif operation == "manifest_assurance_requirements":
            actual = _pheroos_manifest_assurance_requirements(request)
        elif operation == "manifest_distributed_quorum":
            actual = _pheroos_manifest_distributed_quorum(request)
        elif operation == "attention_truth_invariance":
            actual = _pheroos_attention_truth_invariance(request)
        elif operation == "certificate_leaf_binding":
            actual = _pheroos_certificate_leaf_binding(request)
        elif operation == "trace_leaf_binding":
            actual = _pheroos_trace_leaf_binding(request)
        else:
            raise CommitTckV2ProtocolError(
                f"PheroOS TCK v2 operation is unsupported: {operation!r}"
            )
        return CommitTckResponse(
            request_id=request.id,
            implementation_id=self.implementation_id,
            actual=actual,
        )


def load_commit_tck_v2_cases(
    path: str | Path | None = None,
) -> tuple[CommitTckV2Case, ...]:
    artifact = Path(path) if path is not None else COMMIT_TCK_V2_ARTIFACT
    raw = loads_commit_tck_json(artifact.read_text(encoding="utf-8"))
    templates, raw_cases = _validated_commit_tck_artifact(raw)
    cases: list[CommitTckV2Case] = []
    ids: set[str] = set()
    matrix_cases: set[int] = set()
    for raw_case in raw_cases:
        cases.append(
            _commit_tck_case_from_raw(
                raw_case,
                templates=templates,
                ids=ids,
                matrix_cases=matrix_cases,
            )
        )
    return tuple(cases)


def _validated_commit_tck_artifact(
    raw: Any,
) -> tuple[dict[str, dict[str, Any]], list[Any]]:
    root = _exact_object(raw, _ARTIFACT_FIELDS, "Commit TCK v2 artifact")
    if root["tck_version"] != COMMIT_TCK_V2_VERSION:
        raise CommitTckV2ProtocolError("Commit TCK v2 artifact version is unsupported")
    if root["adapter_protocol"] != COMMIT_TCK_JSONL_PROTOCOL_VERSION:
        raise CommitTckV2ProtocolError("Commit TCK v2 adapter protocol is unsupported")
    templates = root["manifest_templates"]
    if not isinstance(templates, dict) or not templates:
        raise CommitTckV2ProtocolError(
            "Commit TCK v2 manifest_templates must be a non-empty object"
        )
    if any(
        not isinstance(key, str) or not key or not isinstance(value, dict)
        for key, value in templates.items()
    ):
        raise CommitTckV2ProtocolError("Commit TCK v2 manifest template is invalid")
    raw_cases = root["cases"]
    if not isinstance(raw_cases, list) or not raw_cases:
        raise CommitTckV2ProtocolError("Commit TCK v2 cases must be a non-empty array")
    return templates, raw_cases


def _commit_tck_case_from_raw(
    raw_case: Any,
    *,
    templates: Mapping[str, dict[str, Any]],
    ids: set[str],
    matrix_cases: set[int],
) -> CommitTckV2Case:
    item = _exact_object(raw_case, _CASE_FIELDS, "Commit TCK v2 case")
    identifier = _text(item["id"], "Commit TCK v2 case id")
    matrix_case = _exact_integer(item["matrix_case"], "matrix_case")
    if matrix_case <= 0:
        raise CommitTckV2ProtocolError("Commit TCK v2 matrix_case must be positive")
    if identifier in ids or matrix_case in matrix_cases:
        raise CommitTckV2ProtocolError(
            "Commit TCK v2 case ids and matrix cases must be unique"
        )
    ids.add(identifier)
    matrix_cases.add(matrix_case)
    manifest = _case_manifest(item, templates=templates)
    request = CommitTckRequest(
        id=identifier,
        tck_version=COMMIT_TCK_V2_VERSION,
        matrix_case=matrix_case,
        title=_text(item["title"], "Commit TCK v2 case title"),
        manifest=manifest,
        profile=_text(item["profile"], "Commit TCK v2 case profile"),
        prior_authoritative_state=deepcopy(
            _object(item["prior_authoritative_state"], "Commit TCK v2 prior state")
        ),
        inputs=deepcopy(_object(item["inputs"], "Commit TCK v2 inputs")),
    )
    expected = deepcopy(item["expected"])
    validate_commit_tck_actual(expected)
    return CommitTckV2Case(request=request, expected=expected)


def _case_manifest(
    item: Mapping[str, Any],
    *,
    templates: Mapping[str, dict[str, Any]],
) -> dict[str, Any] | None:
    template_id = item["manifest_template"]
    if template_id is None:
        manifest = None
    else:
        template_name = _text(template_id, "Commit TCK v2 manifest template id")
        try:
            manifest = deepcopy(templates[template_name])
        except KeyError as exc:
            raise CommitTckV2ProtocolError(
                f"Commit TCK v2 manifest template is missing: {template_name}"
            ) from exc
    _apply_case_manifest_patches(manifest, item["manifest_patches"])
    return manifest


def _apply_case_manifest_patches(
    manifest: dict[str, Any] | None,
    patches: Any,
) -> None:
    if not isinstance(patches, list):
        raise CommitTckV2ProtocolError(
            "Commit TCK v2 manifest_patches must be an array"
        )
    if manifest is None and patches:
        raise CommitTckV2ProtocolError(
            "Commit TCK v2 manifest patches require a template"
        )
    for raw_patch in patches:
        patch = _exact_object(
            raw_patch,
            _PATCH_FIELDS,
            "Commit TCK v2 manifest patch",
        )
        path_value = patch["path"]
        if not isinstance(path_value, list) or not path_value:
            raise CommitTckV2ProtocolError(
                "Commit TCK v2 manifest patch path must be non-empty"
            )
        _replace_json_path(manifest, path_value, deepcopy(patch["replacement"]))


def run_commit_tck_v2(
    cases: Sequence[CommitTckV2Case] | None = None,
    *,
    adapter: CommitTckV2Adapter | None = None,
) -> CommitTckV2Report:
    selected = tuple(cases) if cases is not None else load_commit_tck_v2_cases()
    implementation = adapter or PheroosPublicCommitTckV2Adapter()
    implementation_id = getattr(implementation, "implementation_id", "")
    if not isinstance(implementation_id, str) or not implementation_id:
        return _protocol_failure_report(
            selected,
            "in-process adapter implementation_id is missing",
        )
    results: list[CommitTckV2Result] = []
    for case in selected:
        request = CommitTckRequest.from_dict(case.request.to_dict())
        try:
            response = implementation.evaluate(request)
            if not isinstance(response, CommitTckResponse):
                raise CommitTckV2ProtocolError(
                    "in-process adapter returned an invalid response type"
                )
            if response.request_id != request.id:
                raise CommitTckV2ProtocolError(
                    "in-process adapter response request id mismatch"
                )
            if response.implementation_id != implementation_id:
                raise CommitTckV2ProtocolError(
                    "in-process adapter implementation id mismatch"
                )
            actual = deepcopy(response.actual)
        except Exception as exc:
            actual = empty_commit_tck_actual(
                failure_code=f"exception:{type(exc).__name__}:{exc}"
            )
        ok = actual == case.expected
        results.append(
            CommitTckV2Result(
                request_id=request.id,
                matrix_case=request.matrix_case,
                implementation_id=implementation_id,
                ok=ok,
                expected=deepcopy(case.expected),
                actual=actual,
                detail="" if ok else "exact TCK v2 result mismatch",
            )
        )
    return CommitTckV2Report(
        tck_version=COMMIT_TCK_V2_VERSION,
        implementation_id=implementation_id,
        results=tuple(results),
    )


def run_commit_tck_v2_jsonl(
    command: Sequence[str],
    cases: Sequence[CommitTckV2Case] | None = None,
    *,
    cwd: str | Path | None = None,
    timeout: float = 15.0,
    session_id: str = "commit-tck-v2-session",
) -> CommitTckV2Report:
    selected = tuple(cases) if cases is not None else load_commit_tck_v2_cases()
    input_problem = _jsonl_input_problem(
        command, session_id=session_id, timeout=timeout
    )
    if input_problem is not None:
        return _protocol_failure_report(selected, input_problem)
    operations = sorted({case.request.inputs["operation"] for case in selected})
    wire_input = _jsonl_transcript(
        selected,
        operations=operations,
        session_id=session_id,
    )
    completed = _run_jsonl_adapter(
        command, cwd=cwd, timeout=timeout, wire_input=wire_input
    )
    if isinstance(completed, str):
        return _protocol_failure_report(selected, completed)
    process_problem = _jsonl_process_problem(completed)
    if process_problem is not None:
        return _protocol_failure_report(selected, process_problem)
    try:
        implementation_id, actuals = _parse_jsonl_session(
            completed.stdout,
            selected=selected,
            operations=operations,
            session_id=session_id,
        )
    except Exception as exc:
        return _protocol_failure_report(
            selected,
            f"JSONL adapter protocol error: {type(exc).__name__}: {exc}",
        )
    return _jsonl_report(selected, implementation_id=implementation_id, actuals=actuals)


def _jsonl_input_problem(
    command: Sequence[str],
    *,
    session_id: object,
    timeout: object,
) -> str | None:
    if not command or any(not isinstance(item, str) or not item for item in command):
        return "JSONL adapter command is invalid"
    if (
        not isinstance(session_id, str)
        or not session_id
        or session_id != session_id.strip()
    ):
        return "JSONL adapter session id is invalid"
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or timeout <= 0
    ):
        return "JSONL adapter timeout is invalid"
    return None


def _jsonl_transcript(
    selected: Sequence[CommitTckV2Case],
    *,
    operations: Sequence[str],
    session_id: str,
) -> str:
    transcript: list[dict[str, Any]] = [
        {
            "message_type": "handshake",
            "adapter_protocol": COMMIT_TCK_JSONL_PROTOCOL_VERSION,
            "session_id": session_id,
            "tck_version": COMMIT_TCK_V2_VERSION,
            "request_version": COMMIT_TCK_REQUEST_VERSION,
            "response_version": COMMIT_TCK_RESPONSE_VERSION,
            "operations": operations,
        }
    ]
    transcript.extend(
        {
            "message_type": "evaluate",
            "session_id": session_id,
            "request": case.request.to_dict(),
        }
        for case in selected
    )
    transcript.append({"message_type": "close", "session_id": session_id})
    return "".join(_json_line(item) for item in transcript)


def _run_jsonl_adapter(
    command: Sequence[str],
    *,
    cwd: str | Path | None,
    timeout: float,
    wire_input: str,
) -> subprocess.CompletedProcess[str] | str:
    try:
        return subprocess.run(
            list(command),
            cwd=Path(cwd) if cwd is not None else None,
            input=wire_input,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "JSONL adapter timed out"
    except UnicodeError as exc:
        return f"JSONL adapter output is not valid UTF-8: {type(exc).__name__}: {exc}"
    except OSError as exc:
        return f"JSONL adapter could not start: {type(exc).__name__}: {exc}"


def _jsonl_process_problem(completed: subprocess.CompletedProcess[str]) -> str | None:
    if completed.returncode != 0:
        detail = completed.stderr.strip()
        suffix = f": {detail}" if detail else ""
        return f"JSONL adapter exited with {completed.returncode}{suffix}"
    if len(completed.stdout.encode("utf-8")) > 4 * 1024 * 1024:
        return "JSONL adapter output is too large"
    return None


def _parse_jsonl_session(
    stdout: str,
    *,
    selected: Sequence[CommitTckV2Case],
    operations: Sequence[str],
    session_id: str,
) -> tuple[str, list[dict[str, Any]]]:
    messages = [
        loads_commit_tck_json(line) for line in stdout.splitlines() if line.strip()
    ]
    if len(messages) != len(selected) + 2:
        raise CommitTckV2ProtocolError(
            "JSONL adapter returned the wrong number of messages"
        )
    acknowledgement = _validate_handshake_ack(
        messages[0],
        session_id=session_id,
        operations=operations,
    )
    implementation_id = acknowledgement["implementation_id"]
    actuals = _jsonl_actuals(
        selected,
        messages[1:-1],
        implementation_id=implementation_id,
        session_id=session_id,
    )
    closed = _exact_object(
        messages[-1],
        frozenset({"message_type", "session_id"}),
        "Commit TCK v2 closed envelope",
    )
    if closed != {"message_type": "closed", "session_id": session_id}:
        raise CommitTckV2ProtocolError(
            "JSONL adapter did not close the negotiated session"
        )
    return implementation_id, actuals


def _jsonl_actuals(
    selected: Sequence[CommitTckV2Case],
    messages: Sequence[Any],
    *,
    implementation_id: str,
    session_id: str,
) -> list[dict[str, Any]]:
    actuals: list[dict[str, Any]] = []
    for case, raw_message in zip(selected, messages, strict=True):
        envelope = _exact_object(
            raw_message,
            frozenset({"message_type", "session_id", "response"}),
            "Commit TCK v2 result envelope",
        )
        if envelope["message_type"] != "result":
            raise CommitTckV2ProtocolError(
                "JSONL adapter result message type is invalid"
            )
        if envelope["session_id"] != session_id:
            raise CommitTckV2ProtocolError("JSONL adapter session id mismatch")
        response = CommitTckResponse.from_dict(envelope["response"])
        if response.request_id != case.request.id:
            raise CommitTckV2ProtocolError(
                "JSONL adapter responses are missing or out of order"
            )
        if response.implementation_id != implementation_id:
            raise CommitTckV2ProtocolError(
                "JSONL adapter implementation id changed during the session"
            )
        actuals.append(deepcopy(response.actual))
    return actuals


def _jsonl_report(
    selected: Sequence[CommitTckV2Case],
    *,
    implementation_id: str,
    actuals: Sequence[dict[str, Any]],
) -> CommitTckV2Report:
    results = tuple(
        CommitTckV2Result(
            request_id=case.request.id,
            matrix_case=case.request.matrix_case,
            implementation_id=implementation_id,
            ok=actual == case.expected,
            expected=deepcopy(case.expected),
            actual=actual,
            detail=("" if actual == case.expected else "exact TCK v2 result mismatch"),
        )
        for case, actual in zip(selected, actuals, strict=True)
    )
    return CommitTckV2Report(
        tck_version=COMMIT_TCK_V2_VERSION,
        implementation_id=implementation_id,
        results=results,
    )


def commit_tck_v2_artifact_root(path: str | Path | None = None) -> str:
    artifact = Path(path) if path is not None else COMMIT_TCK_V2_ARTIFACT
    return "sha256:" + sha256(artifact.read_bytes()).hexdigest()


def commit_tck_v2_schema() -> dict[str, Any]:
    actual = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "metrics",
            "roots",
            "progress",
            "outcome",
            "trace_sequence",
            "certificate",
            "failure_code",
        ],
        "properties": {
            "metrics": {"type": "object"},
            "roots": {"type": "object"},
            "progress": {"type": ["object", "null"]},
            "outcome": {"type": ["object", "null"]},
            "trace_sequence": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
            "certificate": {"type": ["object", "null"]},
            "failure_code": {"type": ["string", "null"], "minLength": 1},
        },
    }
    patch = {
        "type": "object",
        "additionalProperties": False,
        "required": ["path", "replacement"],
        "properties": {
            "path": {
                "type": "array",
                "minItems": 1,
                "items": {"type": ["string", "integer"]},
            },
            "replacement": {},
        },
    }
    case = {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_CASE_FIELDS),
        "properties": {
            "id": {"type": "string", "minLength": 1},
            "matrix_case": {"type": "integer", "minimum": 1},
            "title": {"type": "string", "minLength": 1},
            "manifest_template": {"type": ["string", "null"], "minLength": 1},
            "manifest_patches": {"type": "array", "items": patch},
            "profile": {"type": "string", "minLength": 1},
            "prior_authoritative_state": {"type": "object"},
            "inputs": {
                "type": "object",
                "required": ["operation"],
                "properties": {"operation": {"type": "string", "minLength": 1}},
            },
            "expected": actual,
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://pheroos.dev/schemas/commit-tck-v2.schema.json",
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_ARTIFACT_FIELDS),
        "properties": {
            "tck_version": {"const": COMMIT_TCK_V2_VERSION},
            "adapter_protocol": {"const": COMMIT_TCK_JSONL_PROTOCOL_VERSION},
            "manifest_templates": {
                "type": "object",
                "minProperties": 1,
                "additionalProperties": {"type": "object"},
            },
            "cases": {"type": "array", "minItems": 1, "items": case},
        },
    }


def _pheroos_manifest_deadline_outcome(
    request: CommitTckRequest,
) -> dict[str, Any]:
    if request.manifest is None:
        raise CommitTckV2ProtocolError("manifest_deadline_outcome requires a manifest")
    manifest = capability_manifest_from_dict(request.manifest)
    errors = [
        item.code
        for item in validate_capability_manifest(manifest)
        if item.level == "error"
    ]
    if errors:
        raise CommitTckV2ProtocolError(
            "manifest_deadline_outcome manifest is invalid: " + ",".join(errors)
        )
    policy = manifest.protocol.collective_commit_policy
    if policy is None:
        raise CommitTckV2ProtocolError(
            "manifest_deadline_outcome requires collective_commit_policy"
        )
    elapsed_steps = _exact_integer(request.inputs.get("elapsed_steps"), "elapsed_steps")
    if elapsed_steps < 0:
        raise CommitTckV2ProtocolError("elapsed_steps must be non-negative")
    conditions = {
        name: _exact_boolean(request.inputs.get(name), name)
        for name in (
            "invalid",
            "safety_violation",
            "blocked",
            "evidence_commit_ready",
            "finality_unavailable",
        )
    }
    run_deadline_steps = policy.commit_window.run_deadline_steps
    deadline_reached = elapsed_steps >= run_deadline_steps
    kind = select_terminal_outcome_kind(
        **conditions,
        deadline_reached=deadline_reached,
        deadline_outcome=policy.terminal_outcome.deadline_outcome,
    )
    return empty_commit_tck_actual(
        progress={
            "elapsed_steps": elapsed_steps,
            "run_deadline_steps": run_deadline_steps,
            "deadline_reached": deadline_reached,
        },
        outcome={"kind": kind.value if kind is not None else None},
    )


def _pheroos_manifest_threshold_assessment(
    request: CommitTckRequest,
) -> dict[str, Any]:
    manifest, errors = _pheroos_manifest_and_errors(request)
    if errors:
        raise CommitTckV2ProtocolError(
            "manifest_threshold_assessment manifest is invalid: " + ",".join(errors)
        )
    policy = manifest.protocol.collective_commit_policy
    if policy is None:
        raise CommitTckV2ProtocolError(
            "manifest_threshold_assessment requires collective_commit_policy"
        )
    band_name = _text(request.inputs.get("risk_band"), "risk_band")
    try:
        band = policy.risk_bands[band_name]
    except KeyError as exc:
        raise CommitTckV2ProtocolError("risk_band is unsupported") from exc
    observed = _threshold_observations(request.inputs)
    required_categories = set(band.required_challenge_categories)
    observed_categories = set(observed["challenge_categories"])
    gates = {
        "positive_evidence_satisfied": (
            observed["positive_evidence"] >= band.minimum_positive_evidence
        ),
        "counterevidence_satisfied": (
            observed["counterevidence"] <= band.maximum_counterevidence
        ),
        "counter_ratio_satisfied": (
            observed["counterevidence_ratio_ppm"]
            <= band.maximum_counterevidence_ratio_ppm
        ),
        "support_clusters_satisfied": (
            observed["support_clusters"] >= band.minimum_support_clusters
        ),
        "support_ratio_satisfied": (
            observed["support_ratio_ppm"] >= band.minimum_support_ratio_ppm
        ),
        "source_diversity_satisfied": (
            observed["source_diversity"] >= band.minimum_source_diversity
        ),
        "margin_satisfied": observed["leader_margin"] >= band.minimum_margin,
        "challenge_coverage_satisfied": required_categories.issubset(
            observed_categories
        ),
    }
    return empty_commit_tck_actual(
        metrics={
            "minimum_positive_evidence": band.minimum_positive_evidence,
            "maximum_counterevidence": band.maximum_counterevidence,
            "maximum_counterevidence_ratio_ppm": (
                band.maximum_counterevidence_ratio_ppm
            ),
            "minimum_support_clusters": band.minimum_support_clusters,
            "minimum_support_ratio_ppm": band.minimum_support_ratio_ppm,
            "minimum_source_diversity": band.minimum_source_diversity,
            "minimum_margin": band.minimum_margin,
        },
        outcome={
            "risk_band": band_name,
            **gates,
            "ready": all(gates.values()),
        },
    )


def _pheroos_manifest_assurance_requirements(
    request: CommitTckRequest,
) -> dict[str, Any]:
    manifest, errors = _pheroos_manifest_and_errors(request)
    if errors:
        raise CommitTckV2ProtocolError(
            "manifest_assurance_requirements manifest is invalid: " + ",".join(errors)
        )
    policy = manifest.protocol.collective_commit_policy
    if policy is None:
        raise CommitTckV2ProtocolError(
            "manifest_assurance_requirements requires collective_commit_policy"
        )
    assurance = policy.assurance
    proof_rank = {
        "advisory": 0,
        "evidence_bound": 1,
        "certified": 2,
        "distributed": 3,
    }[assurance]
    certificate = policy.certificate
    return empty_commit_tck_actual(
        metrics={
            "proof_rank": proof_rank,
            "distributed_membership_size": (
                policy.distributed.membership_size
                if policy.distributed is not None
                else 0
            ),
        },
        outcome={
            "assurance": assurance,
            "profile": profile_for_manifest(manifest).version,
            "certificate_mode": certificate.mode,
            "issuer_attestation_required": (certificate.issuer_attestation_required),
            "independent_verification_required": (
                certificate.independent_verification_required
            ),
            "distributed_finality_required": policy.distributed is not None,
        },
    )


def _pheroos_manifest_distributed_quorum(
    request: CommitTckRequest,
) -> dict[str, Any]:
    if request.manifest is None:
        raise CommitTckV2ProtocolError(
            "manifest_distributed_quorum requires a manifest"
        )
    raw_manifest = deepcopy(request.manifest)
    raw_policy = _object(
        _object(raw_manifest.get("protocol"), "manifest protocol").get(
            "collective_commit_policy"
        ),
        "manifest collective_commit_policy",
    )
    raw_distributed = _object(
        raw_policy.get("distributed"),
        "manifest distributed policy",
    )
    raw_fault_model = _text(
        raw_distributed.get("fault_model"),
        "fault_model",
    )
    fault_model_valid = raw_fault_model == "byzantine_static_v1"
    if fault_model_valid:
        manifest, errors = _pheroos_manifest_and_errors(request)
    else:
        # The normative schema rejects an unknown fault model before typed
        # validation. Repair only that leaf, validate every other declaration,
        # then retain the original schema failure as the stable TCK diagnostic.
        raw_distributed["fault_model"] = "byzantine_static_v1"
        manifest = capability_manifest_from_dict(raw_manifest)
        errors = ["commit_fault_model_invalid"]
        errors.extend(
            item.code
            for item in validate_capability_manifest(manifest)
            if item.level == "error"
        )
    policy = manifest.protocol.collective_commit_policy
    if policy is None or policy.distributed is None:
        raise CommitTckV2ProtocolError(
            "manifest_distributed_quorum requires distributed policy"
        )
    distributed = policy.distributed
    observed_witnesses = _nonnegative_integer(
        request.inputs.get("observed_witnesses"),
        "observed_witnesses",
    )
    observed_domains = _nonnegative_integer(
        request.inputs.get("observed_failure_domains"),
        "observed_failure_domains",
    )
    n = distributed.membership_size
    faults = distributed.max_byzantine_faults
    quorum = distributed.witness_quorum
    required_membership = 3 * faults + 1
    intersection_margin = (2 * quorum) - n - faults
    membership_sufficient = n >= required_membership
    intersection_safe = intersection_margin > 0
    quorum_reached = observed_witnesses >= quorum
    domain_diverse = observed_domains >= distributed.minimum_failure_domain_diversity
    policy_valid = not errors
    return empty_commit_tck_actual(
        metrics={
            "membership_size": n,
            "max_byzantine_faults": faults,
            "witness_quorum": quorum,
            "required_membership_size": required_membership,
            "maximum_safe_quorum": n - faults,
            "intersection_margin": intersection_margin,
            "observed_witnesses": observed_witnesses,
            "observed_failure_domains": observed_domains,
        },
        outcome={
            "fault_model_valid": fault_model_valid,
            "membership_sufficient": membership_sufficient,
            "intersection_safe": intersection_safe,
            "quorum_reached": quorum_reached,
            "failure_domain_diverse": domain_diverse,
            "policy_valid": policy_valid,
            "finality_ready": (
                policy_valid
                and fault_model_valid
                and membership_sufficient
                and intersection_safe
                and quorum_reached
                and domain_diverse
            ),
            "diagnostic_codes": errors,
        },
        failure_code=errors[0] if errors else None,
    )


def _pheroos_attention_truth_invariance(
    request: CommitTckRequest,
) -> dict[str, Any]:
    manifest, errors = _pheroos_manifest_and_errors(request)
    if errors:
        raise CommitTckV2ProtocolError(
            "attention_truth_invariance manifest is invalid: " + ",".join(errors)
        )
    collective = manifest.protocol.collective_decision_policy
    if collective is None:
        raise CommitTckV2ProtocolError(
            "attention_truth_invariance requires collective_decision_policy"
        )
    candidates = _candidate_evidence(request.inputs.get("candidate_evidence"))
    ordered = sorted(candidates.items(), key=lambda item: (-item[1], item[0]))
    top_score = ordered[0][1]
    tied = [identifier for identifier, score in ordered if score == top_score]
    unique = len(tied) == 1
    leader = tied[0] if unique else ""
    second_score = ordered[1][1] if len(ordered) > 1 else 0
    margin = top_score - second_score if unique else 0
    truth_payload = {
        "candidate_evidence": [
            {"candidate_id": identifier, "evidence": candidates[identifier]}
            for identifier in sorted(candidates)
        ],
        "leader_candidate_id": leader,
        "leader_margin": margin,
        "unique_leader": unique,
    }
    truth_root = commit_payload_fingerprint(
        truth_payload,
        schema="pheroos-tck-v2-commit-truth-v1",
        profile=request.profile,
    )
    attention_candidate = _text(
        request.inputs.get("attention_candidate"),
        "attention_candidate",
    )
    if attention_candidate not in candidates:
        raise CommitTckV2ProtocolError("attention_candidate must be declared")
    attention_strength = _nonnegative_integer(
        request.inputs.get("attention_strength"),
        "attention_strength",
    )
    weight_ppm = int(collective.pheromone_positive_weight * 1_000_000)
    attention_score = multiply_scaled(
        attention_strength,
        weight_ppm,
        scale=1_000_000,
    )
    attention_payload = {
        "attention_candidate": attention_candidate,
        "attention_score": attention_score,
        "attention_strength": attention_strength,
        "positive_weight_ppm": weight_ppm,
    }
    attention_root = commit_payload_fingerprint(
        attention_payload,
        schema="pheroos-tck-v2-attention-v1",
        profile=request.profile,
    )
    return empty_commit_tck_actual(
        metrics={
            "leader_margin": margin,
            "attention_score": attention_score,
            "positive_weight_ppm": weight_ppm,
        },
        roots={
            "commit_truth_root": truth_root,
            "attention_root": attention_root,
        },
        outcome={
            "commit_leader": leader,
            "unique_leader": unique,
            "attention_top_candidate": attention_candidate,
            "attention_commit_authority": False,
            "truth_invariant": True,
        },
    )


def _pheroos_certificate_leaf_binding(
    request: CommitTckRequest,
) -> dict[str, Any]:
    payload = deepcopy(
        _object(request.inputs.get("certificate_payload"), "certificate_payload")
    )
    trusted = _object(
        request.inputs.get("trusted_issuer_attestations"),
        "trusted_issuer_attestations",
    )
    base_valid = verify_evidence_commit_certificate(
        payload,
        trusted_issuer_attestations=trusted,
    )
    records: list[dict[str, Any]] = []
    rejected = 0
    for path in _scalar_leaf_paths(payload):
        mutated = deepcopy(payload)
        _mutate_json_leaf(mutated, path)
        accepted = verify_evidence_commit_certificate(
            mutated,
            trusted_issuer_attestations=trusted,
        )
        if not accepted:
            rejected += 1
        records.append(
            {
                "accepted": accepted,
                "mutation_root": commit_payload_fingerprint(
                    mutated,
                    schema="pheroos-tck-v2-certificate-mutation-v1",
                    profile=request.profile,
                ),
                "path": list(path),
            }
        )
    base_root = commit_payload_fingerprint(
        payload,
        schema="pheroos-evidence-commit-certificate-v1",
        profile=request.profile,
    )
    mutation_set_root = commit_payload_fingerprint(
        {"mutations": records},
        schema="pheroos-tck-v2-certificate-leaf-audit-v1",
        profile=request.profile,
    )
    return empty_commit_tck_actual(
        metrics={
            "authority_leaf_count": len(records),
            "rejected_mutation_count": rejected,
        },
        roots={
            "base_root": base_root,
            "mutation_set_root": mutation_set_root,
        },
        outcome={
            "base_valid": base_valid,
            "all_authority_leaf_mutations_rejected": (
                base_valid and rejected == len(records)
            ),
            "payload_kind": "evidence_commit_certificate",
        },
        certificate={"kind": "evidence_commit", "verified": base_valid},
        failure_code=(
            None
            if base_valid and rejected == len(records)
            else "certificate_authority_leaf_unbound"
        ),
    )


def _pheroos_trace_leaf_binding(request: CommitTckRequest) -> dict[str, Any]:
    event_type = _text(request.inputs.get("event_type"), "event_type")
    protocol_id = _text(request.inputs.get("protocol_id"), "protocol_id")
    target = _text(request.inputs.get("target"), "target")
    reason = _text(request.inputs.get("reason"), "reason")
    lineage = deepcopy(_object(request.inputs.get("lineage"), "lineage"))
    base = TraceEvent(
        event_type=event_type,
        protocol_id=protocol_id,
        target=target,
        reason=reason,
        lineage=lineage,
    )
    try:
        base.validate()
        base_valid = True
    except (TypeError, ValueError):
        base_valid = False
    records: list[dict[str, Any]] = []
    rejected = 0
    for path in _scalar_leaf_paths(lineage):
        mutated = deepcopy(lineage)
        _mutate_json_leaf(mutated, path)
        event = TraceEvent(
            event_type=event_type,
            protocol_id=protocol_id,
            target=target,
            reason=reason,
            lineage=mutated,
        )
        try:
            event.validate()
            accepted = True
        except (TypeError, ValueError):
            accepted = False
        if not accepted:
            rejected += 1
        records.append(
            {
                "accepted": accepted,
                "event_id": commit_trace_event_id(
                    event_type=event_type,
                    protocol_id=protocol_id,
                    target=target,
                    reason=reason,
                    lineage=mutated,
                ),
                "path": list(path),
            }
        )
    mutation_set_root = commit_payload_fingerprint(
        {"mutations": records},
        schema="pheroos-tck-v2-trace-leaf-audit-v1",
        profile=request.profile,
    )
    return empty_commit_tck_actual(
        metrics={
            "authority_leaf_count": len(records),
            "rejected_mutation_count": rejected,
        },
        roots={
            "base_root": lineage.get("event_id", ""),
            "mutation_set_root": mutation_set_root,
        },
        outcome={
            "base_valid": base_valid,
            "all_authority_leaf_mutations_rejected": (
                base_valid and rejected == len(records)
            ),
            "payload_kind": "commit_trace_lineage",
        },
        trace_sequence=[event_type] if base_valid else [],
        failure_code=(
            None
            if base_valid and rejected == len(records)
            else "trace_authority_leaf_unbound"
        ),
    )


def _pheroos_manifest_and_errors(
    request: CommitTckRequest,
) -> tuple[Any, list[str]]:
    if request.manifest is None:
        raise CommitTckV2ProtocolError("manifest operation requires a manifest")
    manifest = capability_manifest_from_dict(request.manifest)
    errors = [
        item.code
        for item in validate_capability_manifest(manifest)
        if item.level == "error"
    ]
    return manifest, errors


def _threshold_observations(inputs: Mapping[str, Any]) -> dict[str, Any]:
    observed: dict[str, Any] = {
        name: _nonnegative_integer(inputs.get(name), name)
        for name in (
            "positive_evidence",
            "counterevidence",
            "counterevidence_ratio_ppm",
            "support_clusters",
            "support_ratio_ppm",
            "source_diversity",
            "leader_margin",
        )
    }
    categories = inputs.get("challenge_categories")
    if (
        not isinstance(categories, list)
        or any(not isinstance(item, str) or not item for item in categories)
        or len(categories) != len(set(categories))
    ):
        raise CommitTckV2ProtocolError(
            "challenge_categories must be a unique non-blank string array"
        )
    observed["challenge_categories"] = list(categories)
    return observed


def _candidate_evidence(value: object) -> dict[str, int]:
    raw = _object(value, "candidate_evidence")
    if len(raw) < 2:
        raise CommitTckV2ProtocolError(
            "candidate_evidence requires at least two candidates"
        )
    return {
        _text(identifier, "candidate_evidence id"): _nonnegative_integer(
            score,
            "candidate_evidence score",
        )
        for identifier, score in raw.items()
    }


def _scalar_leaf_paths(
    value: object,
    prefix: tuple[object, ...] = (),
) -> tuple[tuple[object, ...], ...]:
    paths: list[tuple[object, ...]] = []
    if isinstance(value, dict):
        for key in sorted(value):
            paths.extend(_scalar_leaf_paths(value[key], (*prefix, key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(_scalar_leaf_paths(item, (*prefix, index)))
    elif value is None or type(value) in {bool, int, str}:
        paths.append(prefix)
    else:
        raise CommitTckV2ProtocolError("authority payload contains a non-JSON scalar")
    return tuple(paths)


def _mutate_json_leaf(payload: object, path: Sequence[object]) -> None:
    if not path:
        raise CommitTckV2ProtocolError("authority leaf path must not be empty")
    parent = payload
    for component in path[:-1]:
        parent = _read_json_child(parent, component)
    key = path[-1]
    current = _read_json_child(parent, key)
    replacement: object
    if current is None:
        replacement = "tck-mutated"
    elif type(current) is bool:
        replacement = not current
    elif type(current) is int:
        replacement = current + 1
    elif isinstance(current, str):
        if current.startswith("sha256:") and len(current) == 71:
            tail = "0" if current[-1] != "0" else "1"
            replacement = current[:-1] + tail
        else:
            replacement = current + ":tck-mutated"
    else:
        raise CommitTckV2ProtocolError("authority mutation selected a container")
    if isinstance(parent, dict) and isinstance(key, str):
        parent[key] = replacement
        return
    if isinstance(parent, list) and type(key) is int:
        parent[key] = replacement
        return
    raise CommitTckV2ProtocolError("authority mutation path is invalid")


def _nonnegative_integer(value: object, label: str) -> int:
    normalized = _exact_integer(value, label)
    if normalized < 0:
        raise CommitTckV2ProtocolError(f"{label} must be non-negative")
    return normalized


def _protocol_failure_report(
    cases: Sequence[CommitTckV2Case],
    detail: str,
) -> CommitTckV2Report:
    actual = empty_commit_tck_actual(failure_code="adapter_protocol_error")
    return CommitTckV2Report(
        tck_version=COMMIT_TCK_V2_VERSION,
        implementation_id="unavailable",
        protocol_error=detail,
        results=tuple(
            CommitTckV2Result(
                request_id=case.request.id,
                matrix_case=case.request.matrix_case,
                implementation_id="unavailable",
                ok=False,
                expected=deepcopy(case.expected),
                actual=deepcopy(actual),
                detail=detail,
            )
            for case in cases
        ),
    )


def _validate_handshake_ack(
    payload: object,
    *,
    session_id: str,
    operations: Sequence[str],
) -> dict[str, Any]:
    value = _exact_object(
        payload,
        _HANDSHAKE_ACK_FIELDS,
        "Commit TCK v2 handshake acknowledgement",
    )
    expected_scalars = {
        "message_type": "handshake_ack",
        "adapter_protocol": COMMIT_TCK_JSONL_PROTOCOL_VERSION,
        "session_id": session_id,
    }
    for name, expected in expected_scalars.items():
        if value[name] != expected:
            raise CommitTckV2ProtocolError(
                f"JSONL adapter handshake {name} is incompatible"
            )
    _text(value["implementation_id"], "JSONL adapter implementation id")
    _text(value["implementation_version"], "JSONL adapter implementation version")
    required_memberships = {
        "supported_tck_versions": COMMIT_TCK_V2_VERSION,
        "supported_request_versions": COMMIT_TCK_REQUEST_VERSION,
        "supported_response_versions": COMMIT_TCK_RESPONSE_VERSION,
    }
    for name, expected in required_memberships.items():
        values = _unique_text_array(value[name], f"JSONL adapter handshake {name}")
        if expected not in values:
            raise CommitTckV2ProtocolError(
                f"JSONL adapter handshake {name} is incompatible"
            )
    supported_operations = _unique_text_array(
        value["supported_operations"],
        "JSONL adapter handshake supported_operations",
    )
    if not set(operations).issubset(supported_operations):
        raise CommitTckV2ProtocolError(
            "JSONL adapter does not support every requested operation"
        )
    return value


def _replace_json_path(root: object, path: Sequence[object], replacement: Any) -> None:
    current = root
    for component in path[:-1]:
        current = _read_json_child(current, component)
    key = path[-1]
    if isinstance(current, dict) and isinstance(key, str) and key in current:
        current[key] = replacement
        return
    if isinstance(current, list) and type(key) is int and 0 <= key < len(current):
        current[key] = replacement
        return
    raise CommitTckV2ProtocolError("Commit TCK v2 manifest patch path is missing")


def _read_json_child(parent: object, key: object) -> Any:
    if isinstance(parent, dict) and isinstance(key, str) and key in parent:
        return parent[key]
    if isinstance(parent, list) and type(key) is int and 0 <= key < len(parent):
        return parent[key]
    raise CommitTckV2ProtocolError("Commit TCK v2 manifest patch path is missing")


def _exact_object(
    value: object,
    expected_fields: frozenset[str],
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CommitTckV2ProtocolError(f"{label} must be an object")
    if set(value) != expected_fields:
        missing = sorted(expected_fields - set(value))
        unknown = sorted(set(value) - expected_fields)
        raise CommitTckV2ProtocolError(
            f"{label} fields are invalid: missing={missing}, unknown={unknown}"
        )
    return value


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CommitTckV2ProtocolError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CommitTckV2ProtocolError(f"{label} must be a non-blank string")
    return value


def _exact_integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise CommitTckV2ProtocolError(f"{label} must be an exact integer")
    return value


def _exact_boolean(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise CommitTckV2ProtocolError(f"{label} must be an exact boolean")
    return value


def _unique_text_array(value: object, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(
            not isinstance(item, str) or not item or item != item.strip()
            for item in value
        )
        or len(set(value)) != len(value)
    ):
        raise CommitTckV2ProtocolError(
            f"{label} must be a unique non-blank string array"
        )
    return value


def _json_line(payload: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            dict(payload),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )


__all__ = [
    "COMMIT_TCK_V2_ARTIFACT",
    "PHEROOS_TCK_V2_IMPLEMENTATION_ID",
    "PHEROOS_TCK_V2_OPERATIONS",
    "CommitTckV2Adapter",
    "CommitTckV2Case",
    "CommitTckV2Report",
    "CommitTckV2Result",
    "PheroosPublicCommitTckV2Adapter",
    "commit_tck_v2_artifact_root",
    "commit_tck_v2_schema",
    "load_commit_tck_v2_cases",
    "run_commit_tck_v2",
    "run_commit_tck_v2_jsonl",
]
