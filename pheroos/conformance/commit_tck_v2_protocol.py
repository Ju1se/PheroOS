from __future__ import annotations

"""Provider-neutral Commit TCK v2 request/response and JSONL server ABI."""

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Any, TextIO


COMMIT_TCK_V2_VERSION = "pheroos-commit-integrity-tck-v2"
COMMIT_TCK_REQUEST_VERSION = "pheroos-commit-tck-request-v2"
COMMIT_TCK_RESPONSE_VERSION = "pheroos-commit-tck-response-v2"
COMMIT_TCK_JSONL_PROTOCOL_VERSION = "pheroos-commit-tck-jsonl-v2"
COMMIT_TCK_REQUEST_SCHEMA_ID = (
    "https://pheroos.dev/schemas/commit-tck-request-v2.schema.json"
)
COMMIT_TCK_RESPONSE_SCHEMA_ID = (
    "https://pheroos.dev/schemas/commit-tck-response-v2.schema.json"
)

_ACTUAL_FIELDS = frozenset(
    {
        "metrics",
        "roots",
        "progress",
        "outcome",
        "trace_sequence",
        "certificate",
        "failure_code",
    }
)
_REQUEST_FIELDS = frozenset(
    {
        "request_version",
        "id",
        "tck_version",
        "matrix_case",
        "title",
        "manifest",
        "profile",
        "prior_authoritative_state",
        "inputs",
    }
)
_RESPONSE_FIELDS = frozenset(
    {
        "response_version",
        "request_id",
        "implementation_id",
        "actual",
    }
)


class CommitTckV2ProtocolError(ValueError):
    """A malformed or incompatible TCK v2 wire message."""


@dataclass(frozen=True, slots=True)
class CommitTckRequest:
    """Expected-free request visible to an in-process or JSONL adapter."""

    id: str
    tck_version: str
    matrix_case: int
    title: str
    manifest: dict[str, Any] | None
    profile: str
    prior_authoritative_state: dict[str, Any]
    inputs: dict[str, Any]
    request_version: str = COMMIT_TCK_REQUEST_VERSION

    def __post_init__(self) -> None:
        if self.request_version != COMMIT_TCK_REQUEST_VERSION:
            raise CommitTckV2ProtocolError("commit TCK request version is unsupported")
        for label, value in (
            ("id", self.id),
            ("TCK version", self.tck_version),
            ("title", self.title),
            ("profile", self.profile),
        ):
            _require_text(value, f"commit TCK request {label}")
        if type(self.matrix_case) is not int or self.matrix_case <= 0:
            raise CommitTckV2ProtocolError(
                "commit TCK request matrix_case must be a positive integer"
            )
        if self.manifest is not None and not isinstance(self.manifest, dict):
            raise CommitTckV2ProtocolError(
                "commit TCK request manifest must be an object or null"
            )
        if not isinstance(self.prior_authoritative_state, dict):
            raise CommitTckV2ProtocolError(
                "commit TCK request prior state must be an object"
            )
        if not isinstance(self.inputs, dict):
            raise CommitTckV2ProtocolError("commit TCK request inputs must be an object")
        _require_text(
            self.inputs.get("operation"),
            "commit TCK request operation",
        )
        object.__setattr__(self, "manifest", _json_snapshot(self.manifest))
        object.__setattr__(
            self,
            "prior_authoritative_state",
            _json_snapshot(self.prior_authoritative_state),
        )
        object.__setattr__(self, "inputs", _json_snapshot(self.inputs))

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_version": self.request_version,
            "id": self.id,
            "tck_version": self.tck_version,
            "matrix_case": self.matrix_case,
            "title": self.title,
            "manifest": deepcopy(self.manifest),
            "profile": self.profile,
            "prior_authoritative_state": deepcopy(
                self.prior_authoritative_state
            ),
            "inputs": deepcopy(self.inputs),
        }

    @classmethod
    def from_dict(cls, payload: object) -> CommitTckRequest:
        value = _exact_object(payload, _REQUEST_FIELDS, "commit TCK request")
        return cls(
            request_version=value["request_version"],
            id=value["id"],
            tck_version=value["tck_version"],
            matrix_case=value["matrix_case"],
            title=value["title"],
            manifest=deepcopy(value["manifest"]),
            profile=value["profile"],
            prior_authoritative_state=deepcopy(
                value["prior_authoritative_state"]
            ),
            inputs=deepcopy(value["inputs"]),
        )


@dataclass(frozen=True, slots=True)
class CommitTckResponse:
    """Adapter response containing only the implementation's actual result."""

    request_id: str
    implementation_id: str
    actual: dict[str, Any]
    response_version: str = COMMIT_TCK_RESPONSE_VERSION

    def __post_init__(self) -> None:
        if self.response_version != COMMIT_TCK_RESPONSE_VERSION:
            raise CommitTckV2ProtocolError("commit TCK response version is unsupported")
        _require_text(self.request_id, "commit TCK response request_id")
        _require_text(
            self.implementation_id,
            "commit TCK response implementation_id",
        )
        normalized = _json_snapshot(self.actual)
        validate_commit_tck_actual(normalized)
        object.__setattr__(self, "actual", normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_version": self.response_version,
            "request_id": self.request_id,
            "implementation_id": self.implementation_id,
            "actual": deepcopy(self.actual),
        }

    @classmethod
    def from_dict(cls, payload: object) -> CommitTckResponse:
        value = _exact_object(payload, _RESPONSE_FIELDS, "commit TCK response")
        return cls(
            response_version=value["response_version"],
            request_id=value["request_id"],
            implementation_id=value["implementation_id"],
            actual=deepcopy(value["actual"]),
        )


def empty_commit_tck_actual(
    *,
    metrics: Mapping[str, Any] | None = None,
    roots: Mapping[str, Any] | None = None,
    progress: Mapping[str, Any] | None = None,
    outcome: Mapping[str, Any] | None = None,
    trace_sequence: Sequence[str] = (),
    certificate: Mapping[str, Any] | None = None,
    failure_code: str | None = None,
) -> dict[str, Any]:
    value = {
        "metrics": dict(metrics or {}),
        "roots": dict(roots or {}),
        "progress": dict(progress) if progress is not None else None,
        "outcome": dict(outcome) if outcome is not None else None,
        "trace_sequence": list(trace_sequence),
        "certificate": dict(certificate) if certificate is not None else None,
        "failure_code": failure_code,
    }
    validate_commit_tck_actual(value)
    return value


def validate_commit_tck_actual(payload: object) -> None:
    value = _exact_object(payload, _ACTUAL_FIELDS, "commit TCK actual result")
    if not isinstance(value["metrics"], dict) or not isinstance(value["roots"], dict):
        raise CommitTckV2ProtocolError(
            "commit TCK actual metrics and roots must be objects"
        )
    for name in ("progress", "outcome", "certificate"):
        if value[name] is not None and not isinstance(value[name], dict):
            raise CommitTckV2ProtocolError(
                f"commit TCK actual {name} must be an object or null"
            )
    sequence = value["trace_sequence"]
    if not isinstance(sequence, list) or any(
        not isinstance(item, str) or not item for item in sequence
    ):
        raise CommitTckV2ProtocolError(
            "commit TCK actual trace_sequence must be a string array"
        )
    failure = value["failure_code"]
    if failure is not None and (not isinstance(failure, str) or not failure):
        raise CommitTckV2ProtocolError(
            "commit TCK actual failure_code must be a string or null"
        )
    _json_snapshot(value)


def commit_tck_request_v2_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": COMMIT_TCK_REQUEST_SCHEMA_ID,
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_REQUEST_FIELDS),
        "properties": {
            "request_version": {"const": COMMIT_TCK_REQUEST_VERSION},
            "id": {"type": "string", "minLength": 1},
            "tck_version": {"type": "string", "minLength": 1},
            "matrix_case": {"type": "integer", "minimum": 1},
            "title": {"type": "string", "minLength": 1},
            "manifest": {"type": ["object", "null"]},
            "profile": {"type": "string", "minLength": 1},
            "prior_authoritative_state": {"type": "object"},
            "inputs": {
                "type": "object",
                "required": ["operation"],
                "properties": {
                    "operation": {"type": "string", "minLength": 1}
                },
            },
        },
    }


def commit_tck_response_v2_schema() -> dict[str, Any]:
    nullable_object = {"type": ["object", "null"]}
    actual = {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_ACTUAL_FIELDS),
        "properties": {
            "metrics": {"type": "object"},
            "roots": {"type": "object"},
            "progress": nullable_object,
            "outcome": nullable_object,
            "trace_sequence": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
            "certificate": nullable_object,
            "failure_code": {"type": ["string", "null"], "minLength": 1},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": COMMIT_TCK_RESPONSE_SCHEMA_ID,
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_RESPONSE_FIELDS),
        "properties": {
            "response_version": {"const": COMMIT_TCK_RESPONSE_VERSION},
            "request_id": {"type": "string", "minLength": 1},
            "implementation_id": {"type": "string", "minLength": 1},
            "actual": actual,
        },
    }


def serve_commit_tck_v2_jsonl(
    evaluator: Callable[[CommitTckRequest], CommitTckResponse],
    *,
    implementation_id: str,
    implementation_version: str,
    supported_operations: Sequence[str],
    input_stream: TextIO,
    output_stream: TextIO,
) -> None:
    """Serve one strict handshake/evaluate/close JSONL session."""

    _require_text(implementation_id, "commit TCK implementation id")
    _require_text(implementation_version, "commit TCK implementation version")
    operations = tuple(supported_operations)
    if not operations or any(
        not isinstance(item, str) or not item or item != item.strip()
        for item in operations
    ) or len(set(operations)) != len(operations):
        raise CommitTckV2ProtocolError(
            "commit TCK supported operations must be unique non-blank strings"
        )

    first = _read_jsonl(input_stream, "commit TCK handshake")
    handshake_fields = frozenset(
        {
            "message_type",
            "adapter_protocol",
            "session_id",
            "tck_version",
            "request_version",
            "response_version",
            "operations",
        }
    )
    handshake = _exact_object(first, handshake_fields, "commit TCK handshake")
    if handshake["message_type"] != "handshake":
        raise CommitTckV2ProtocolError("commit TCK first message must be handshake")
    if handshake["adapter_protocol"] != COMMIT_TCK_JSONL_PROTOCOL_VERSION:
        raise CommitTckV2ProtocolError("commit TCK JSONL protocol is unsupported")
    if handshake["request_version"] != COMMIT_TCK_REQUEST_VERSION:
        raise CommitTckV2ProtocolError("commit TCK request version is unsupported")
    if handshake["response_version"] != COMMIT_TCK_RESPONSE_VERSION:
        raise CommitTckV2ProtocolError("commit TCK response version is unsupported")
    if handshake["tck_version"] != COMMIT_TCK_V2_VERSION:
        raise CommitTckV2ProtocolError("commit TCK version is unsupported")
    session_id = _require_text(handshake["session_id"], "commit TCK session id")
    requested = handshake["operations"]
    if (
        not isinstance(requested, list)
        or not requested
        or any(
            not isinstance(item, str) or not item or item != item.strip()
            for item in requested
        )
        or len(set(requested)) != len(requested)
    ):
        raise CommitTckV2ProtocolError(
            "commit TCK requested operations must be a unique non-blank string array"
        )
    if not set(requested).issubset(operations):
        raise CommitTckV2ProtocolError("commit TCK operation is unsupported")
    _write_jsonl(
        output_stream,
        {
            "message_type": "handshake_ack",
            "adapter_protocol": COMMIT_TCK_JSONL_PROTOCOL_VERSION,
            "session_id": session_id,
            "implementation_id": implementation_id,
            "implementation_version": implementation_version,
            "supported_tck_versions": [COMMIT_TCK_V2_VERSION],
            "supported_request_versions": [COMMIT_TCK_REQUEST_VERSION],
            "supported_response_versions": [COMMIT_TCK_RESPONSE_VERSION],
            "supported_operations": list(operations),
        },
    )

    for raw_line in input_stream:
        if not raw_line.strip():
            raise CommitTckV2ProtocolError("commit TCK JSONL line must not be blank")
        message = loads_commit_tck_json(raw_line)
        if not isinstance(message, dict):
            raise CommitTckV2ProtocolError("commit TCK JSONL message must be an object")
        message_type = message.get("message_type")
        if message_type == "evaluate":
            envelope = _exact_object(
                message,
                frozenset({"message_type", "session_id", "request"}),
                "commit TCK evaluate envelope",
            )
            if envelope["session_id"] != session_id:
                raise CommitTckV2ProtocolError("commit TCK session id mismatch")
            request = CommitTckRequest.from_dict(envelope["request"])
            if request.tck_version != COMMIT_TCK_V2_VERSION:
                raise CommitTckV2ProtocolError("commit TCK request version mismatch")
            if request.inputs["operation"] not in operations:
                raise CommitTckV2ProtocolError("commit TCK operation is unsupported")
            response = evaluator(request)
            if not isinstance(response, CommitTckResponse):
                raise CommitTckV2ProtocolError(
                    "commit TCK evaluator returned an invalid response type"
                )
            if response.request_id != request.id:
                raise CommitTckV2ProtocolError(
                    "commit TCK response request id mismatch"
                )
            if response.implementation_id != implementation_id:
                raise CommitTckV2ProtocolError(
                    "commit TCK response implementation id mismatch"
                )
            _write_jsonl(
                output_stream,
                {
                    "message_type": "result",
                    "session_id": session_id,
                    "response": response.to_dict(),
                },
            )
            continue
        if message_type == "close":
            close = _exact_object(
                message,
                frozenset({"message_type", "session_id"}),
                "commit TCK close envelope",
            )
            if close["session_id"] != session_id:
                raise CommitTckV2ProtocolError("commit TCK session id mismatch")
            _write_jsonl(
                output_stream,
                {"message_type": "closed", "session_id": session_id},
            )
            return
        raise CommitTckV2ProtocolError(
            f"commit TCK JSONL message type is unsupported: {message_type!r}"
        )
    raise CommitTckV2ProtocolError("commit TCK JSONL session ended before close")


def loads_commit_tck_json(value: str) -> Any:
    try:
        return json.loads(
            value,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
        )
    except CommitTckV2ProtocolError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CommitTckV2ProtocolError(f"commit TCK JSON is invalid: {exc}") from exc


def _read_jsonl(stream: TextIO, label: str) -> Any:
    line = stream.readline()
    if not line:
        raise CommitTckV2ProtocolError(f"{label} is missing")
    if not line.strip():
        raise CommitTckV2ProtocolError(f"{label} must not be blank")
    return loads_commit_tck_json(line)


def _write_jsonl(stream: TextIO, payload: Mapping[str, Any]) -> None:
    stream.write(
        json.dumps(
            dict(payload),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )
    stream.flush()


def _json_snapshot(value: Any) -> Any:
    try:
        rendered = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return json.loads(rendered)
    except (TypeError, ValueError) as exc:
        raise CommitTckV2ProtocolError(
            f"commit TCK value must be finite provider-neutral JSON: {exc}"
        ) from exc


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


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CommitTckV2ProtocolError(f"{label} must be a non-blank string")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise CommitTckV2ProtocolError(
                f"commit TCK JSON contains duplicate key: {key}"
            )
        value[key] = item
    return value


def _reject_nonfinite_constant(value: str) -> None:
    raise CommitTckV2ProtocolError(
        f"commit TCK JSON contains non-finite number: {value}"
    )


__all__ = [
    "COMMIT_TCK_JSONL_PROTOCOL_VERSION",
    "COMMIT_TCK_REQUEST_SCHEMA_ID",
    "COMMIT_TCK_REQUEST_VERSION",
    "COMMIT_TCK_RESPONSE_SCHEMA_ID",
    "COMMIT_TCK_RESPONSE_VERSION",
    "COMMIT_TCK_V2_VERSION",
    "CommitTckRequest",
    "CommitTckResponse",
    "CommitTckV2ProtocolError",
    "commit_tck_request_v2_schema",
    "commit_tck_response_v2_schema",
    "empty_commit_tck_actual",
    "loads_commit_tck_json",
    "serve_commit_tck_v2_jsonl",
    "validate_commit_tck_actual",
]
