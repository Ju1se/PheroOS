"""Stable TCK value models and JSON result primitives.

This module is deliberately dependency-light.  It owns no artifact loading,
reference semantics, or execution policy, so every other private TCK module
can depend on it without creating a cycle.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Any, Protocol

from pheroos.conformance.commit_tck_v2_protocol import (
    CommitTckRequest as _CommitTckRequest,
)


EXPECTED_FIELDS = frozenset(
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


@dataclass(frozen=True)
class CommitTckVector:
    id: str
    tck_version: str
    matrix_case: int
    title: str
    manifest: dict[str, Any] | None
    profile: str
    prior_authoritative_state: dict[str, Any]
    inputs: dict[str, Any]
    expected: dict[str, Any]
    mutations: tuple[dict[str, Any], ...] = ()
    permutations: tuple[dict[str, Any], ...] = ()


def request_from_vector(vector: CommitTckVector) -> _CommitTckRequest:
    """Return a fresh adapter request without harness-owned expectations."""

    return _CommitTckRequest(
        id=vector.id,
        tck_version=vector.tck_version,
        matrix_case=vector.matrix_case,
        title=vector.title,
        manifest=deepcopy(vector.manifest),
        profile=vector.profile,
        prior_authoritative_state=deepcopy(vector.prior_authoritative_state),
        inputs=deepcopy(vector.inputs),
    )


@dataclass(frozen=True)
class CommitTckResult:
    vector_id: str
    matrix_case: int
    ok: bool
    expected: dict[str, Any]
    actual: dict[str, Any]
    detail: str = ""
    variant_failures: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommitTckReport:
    tck_version: str
    results: tuple[CommitTckResult, ...]

    @property
    def ok(self) -> bool:
        return bool(self.results) and all(item.ok for item in self.results)


class CommitTckAdapter(Protocol):
    """Structural adapter contract for the input-only v2 request view."""

    def evaluate(self, request: _CommitTckRequest) -> Mapping[str, Any]: ...


def result(
    *,
    metrics: Mapping[str, Any] | None = None,
    roots: Mapping[str, Any] | None = None,
    progress: Any = None,
    outcome: Any = None,
    trace_sequence: Sequence[str] = (),
    certificate: Any = None,
    failure_code: str | None = None,
) -> dict[str, Any]:
    return {
        "metrics": dict(metrics or {}),
        "roots": dict(roots or {}),
        "progress": progress,
        "outcome": outcome,
        "trace_sequence": list(trace_sequence),
        "certificate": certificate,
        "failure_code": failure_code,
    }


def json_result(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project an adapter result onto the JSON TCK value model."""

    rendered = json.dumps(
        dict(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=False,
        separators=(",", ":"),
    )
    projected = json.loads(rendered)
    if not isinstance(projected, dict):
        raise ValueError("commit TCK adapter result must be a JSON object")
    return projected


def validate_expected_shape(value: Mapping[str, Any], *, label: str) -> None:
    if set(value) != EXPECTED_FIELDS:
        raise ValueError(f"{label} must contain the exact normative result fields")
    if not isinstance(value["metrics"], dict) or not isinstance(value["roots"], dict):
        raise ValueError(f"{label} metrics and roots must be objects")
    for name in ("progress", "outcome", "certificate"):
        if value[name] is not None and not isinstance(value[name], dict):
            raise ValueError(f"{label} {name} must be an object or null")
    if not isinstance(value["trace_sequence"], list) or not all(
        isinstance(item, str) and item for item in value["trace_sequence"]
    ):
        raise ValueError(f"{label} trace_sequence must be a string array")
    failure = value["failure_code"]
    if failure is not None and (not isinstance(failure, str) or not failure):
        raise ValueError(f"{label} failure_code must be a string or null")


def object_value(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def text_value(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-blank string")
    return value


def integer_value(value: object, label: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{label} must be an exact integer")
    return value


__all__ = [
    "CommitTckAdapter",
    "CommitTckReport",
    "CommitTckResult",
    "CommitTckVector",
]
