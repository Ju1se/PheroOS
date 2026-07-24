from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
import pytest

from pheroos.trace import EVENT_LINEAGE_CONTRACTS, TraceEvent, VALID_EVENT_TYPES
from pheroos.trace.schema import trace_schema


EVENT_TYPE = "hybrid_replay_advanced"
ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_OWNER = ROOT / "pheroos" / "trace" / "_contracts" / "authority.py"


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _stream_ref(
    scope_ref: str,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
) -> str:
    payload = b"\x00".join(
        value.encode("utf-8")
        for value in (scope_ref, protocol_ref, run_ref, target_ref)
    )
    return "authority:hybrid-replay-v2:" + sha256(payload).hexdigest()


def _transition_id(stream_ref: str, advance_ref: str) -> str:
    payload = b"\x00".join(value.encode("utf-8") for value in (stream_ref, advance_ref))
    return "transition:hybrid-replay-v2:" + sha256(payload).hexdigest()


def _session_binding(
    *,
    stream_ref: str,
    advance_ref: str,
    target_ref: str,
) -> dict[str, object]:
    del stream_ref
    return {
        "domain_root": _root("domain"),
        "scope_ref": "scope:hybrid-replay",
        "run_ref": "run:hybrid-replay",
        "request_ref": advance_ref,
        "request_root": _root("request"),
        "operation": "advance_replay",
        "observed_epoch": 7,
        "grant_ref": "grant:hybrid-replay",
        "grant_root": _root("grant"),
        "grant_binding_ref": _root("grant-binding"),
        "grant_expected_revision": 1,
        "grant_expected_root": _root("grant-head"),
        "lifecycle_expected_revision": 0,
        "lifecycle_expected_root": _root("lifecycle-head"),
        "target_refs": [target_ref],
        "action_refs": [],
    }


def _lineage(*, revision: int = 1) -> dict[str, Any]:
    target_ref = "target:hybrid-replay"
    scope_ref = "scope:hybrid-replay"
    protocol_ref = "protocol:hybrid-replay"
    run_ref = "run:hybrid-replay"
    advance_ref = f"advance:hybrid-replay:{revision}"
    stream_ref = _stream_ref(scope_ref, protocol_ref, run_ref, target_ref)
    return {
        "domain_root": _root("domain"),
        "scope_ref": scope_ref,
        "stream_ref": stream_ref,
        "transition_id": _transition_id(stream_ref, advance_ref),
        "run_ref": run_ref,
        "request_ref": advance_ref,
        "request_root": _root("request"),
        "grant_ref": "grant:hybrid-replay",
        "grant_root": _root("grant"),
        "grant_binding_ref": _root("grant-binding"),
        "operation": "advance_replay",
        "observed_epoch": 7,
        "session_binding": _session_binding(
            stream_ref=stream_ref,
            advance_ref=advance_ref,
            target_ref=target_ref,
        ),
        "target_ref": target_ref,
        "advance_ref": advance_ref,
        "protocol_ref": protocol_ref,
        "manifest_root": _root("manifest"),
        "candidate_set_root": _root("candidate-set"),
        "hybrid_policy_root": _root("hybrid-policy"),
        "effective_policy_root": _root("effective-policy"),
        "topology_root": _root("topology"),
        "revision": revision,
        "current_step": revision - 1,
        "parent_transition_id": (
            None if revision == 1 else "transition:hybrid-replay-v2:" + ("1" * 64)
        ),
        "parent_snapshot_root": None if revision == 1 else _root("parent-snapshot"),
        "parent_head_root": _root("parent-head"),
        "snapshot_root": _root("snapshot"),
        "memory_root": _root("memory"),
        "replay_receipt_root": _root("replay-receipts"),
        "source_step_root": _root("source-step"),
        "source_trace_root": _root("source-trace"),
        "read_set_root": _root("read-set"),
    }


def _event(*, revision: int = 1, lineage: dict[str, Any] | None = None) -> TraceEvent:
    return TraceEvent(
        event_type=EVENT_TYPE,
        protocol_id="pheroos.protocol.v2",
        target="target:hybrid-replay",
        reason="atomically advance one durable hybrid replay lineage",
        lineage=_lineage(revision=revision) if lineage is None else lineage,
    )


def _payload(*, revision: int = 1) -> dict[str, Any]:
    event = _event(revision=revision)
    return {
        "event_type": event.event_type,
        "protocol_id": event.protocol_id,
        "target": event.target,
        "reason": event.reason,
        "lineage": deepcopy(event.lineage),
    }


@pytest.mark.parametrize("revision", (1, 2))
def test_hybrid_replay_trace_runtime_and_schema_accept_exact_lineage(
    revision: int,
) -> None:
    event = _event(revision=revision)

    event.validate()
    Draft202012Validator(trace_schema()).validate(_payload(revision=revision))
    assert EVENT_TYPE in VALID_EVENT_TYPES
    assert EVENT_LINEAGE_CONTRACTS[EVENT_TYPE] == frozenset(event.lineage)


def test_hybrid_replay_trace_owner_is_governance_independent() -> None:
    assert "pheroos.governance" not in AUTHORITY_OWNER.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value.__setitem__("protocol_id", "protocol:legacy"),
            "protocol_id",
        ),
        (
            lambda value: value["lineage"].__setitem__("stream_ref", "bad"),
            "stream_ref",
        ),
        (
            lambda value: value["lineage"].__setitem__(
                "transition_id", "transition:bad"
            ),
            "transition_id",
        ),
        (
            lambda value: value["lineage"]["session_binding"].__setitem__(
                "action_refs", ["action:publish"]
            ),
            "target/action bounds",
        ),
        (
            lambda value: value["lineage"]["session_binding"].__setitem__(
                "target_refs", []
            ),
            "target/action bounds",
        ),
    ],
)
def test_hybrid_replay_trace_rejects_envelope_and_binding_substitution(
    mutation: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    payload = _payload()
    mutation(payload)

    with pytest.raises(ValueError, match=message):
        TraceEvent(**payload).validate()
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


def test_hybrid_replay_trace_request_identity_is_cross_bound_at_runtime() -> None:
    lineage = _lineage()
    lineage["request_ref"] = "advance:other"

    with pytest.raises(ValueError, match="request_ref"):
        _event(lineage=lineage).validate()


def test_hybrid_replay_trace_runtime_and_schema_reject_unknown_lineage() -> None:
    lineage = _lineage()
    lineage["caller_extension"] = "must-not-enter-authority-lineage"
    payload = _payload()
    payload["lineage"] = lineage

    with pytest.raises(ValueError, match="unknown fields"):
        _event(lineage=lineage).validate()
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize(
    ("revision", "field", "value", "message"),
    [
        (1, "parent_transition_id", "transition:parent", "genesis parent"),
        (1, "parent_snapshot_root", _root("parent"), "genesis parent"),
        (2, "parent_transition_id", None, "parent_transition_id"),
        (2, "parent_transition_id", "transition:parent", "parent_transition_id"),
        (2, "parent_snapshot_root", None, "parent_snapshot_root"),
        (0, "revision", 0, "revision"),
    ],
)
def test_hybrid_replay_trace_rejects_parent_and_revision_rollback(
    revision: int,
    field: str,
    value: object,
    message: str,
) -> None:
    lineage = _lineage(revision=max(1, revision))
    lineage[field] = value
    if field == "revision":
        lineage["revision"] = revision

    with pytest.raises(ValueError, match=message):
        _event(revision=max(1, revision), lineage=lineage).validate()
    payload = _payload(revision=max(1, revision))
    payload["lineage"] = lineage
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize(
    "field",
    (
        "manifest_root",
        "candidate_set_root",
        "hybrid_policy_root",
        "effective_policy_root",
        "topology_root",
        "parent_head_root",
        "snapshot_root",
        "memory_root",
        "replay_receipt_root",
        "source_step_root",
        "source_trace_root",
        "read_set_root",
    ),
)
def test_hybrid_replay_trace_rejects_every_malformed_root(field: str) -> None:
    lineage = _lineage()
    lineage[field] = "sha256:ABC"

    with pytest.raises(ValueError, match=field):
        _event(lineage=lineage).validate()
    payload = _payload()
    payload["lineage"] = lineage
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


def test_hybrid_replay_trace_rejects_cross_target_envelope() -> None:
    event = TraceEvent(
        event_type=EVENT_TYPE,
        protocol_id="pheroos.protocol.v2",
        target="target:other",
        reason="atomically advance one durable hybrid replay lineage",
        lineage=_lineage(),
    )

    with pytest.raises(ValueError, match="target must match target_ref"):
        event.validate()


@pytest.mark.parametrize(
    "field", ("scope_ref", "protocol_ref", "run_ref", "target_ref")
)
def test_hybrid_replay_trace_runtime_and_schema_reject_nul_identity_aliases(
    field: str,
) -> None:
    lineage = _lineage()
    lineage[field] = f"{lineage[field]}\x00alias"
    payload = _payload()
    payload["lineage"] = lineage

    with pytest.raises(ValueError, match="canonical text"):
        _event(lineage=lineage).validate()
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)
