from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from hashlib import sha256
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
import pytest

from pheroos.trace import EVENT_LINEAGE_CONTRACTS, TraceEvent, VALID_EVENT_TYPES
from pheroos.trace.schema import trace_schema


AUTHORITY_EVENTS = frozenset(
    {
        "issuer_grant_activated",
        "issuer_grant_revoked",
        "signal_verified",
        "domain_retired",
    }
)


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _stream(kind: str, *bindings: str) -> str:
    payload = b"\x00".join(binding.encode("utf-8") for binding in bindings)
    return f"authority:{kind}:{sha256(payload).hexdigest()}"


def _session_binding(operation: str, *, target_refs: list[str]) -> dict[str, object]:
    return {
        "domain_root": _root("domain"),
        "scope_ref": "scope:test",
        "run_ref": "run:test",
        "request_ref": "request:test",
        "request_root": _root("request"),
        "operation": operation,
        "observed_epoch": 7,
        "grant_ref": "grant:test",
        "grant_root": _root("grant"),
        "grant_binding_ref": _root("grant-binding"),
        "grant_expected_revision": 1,
        "grant_expected_root": _root("grant-head"),
        "lifecycle_expected_revision": 0,
        "lifecycle_expected_root": _root("lifecycle-head"),
        "target_refs": target_refs,
        "action_refs": [],
    }


def _lineage(event_type: str) -> dict[str, Any]:
    common: dict[str, Any] = {
        "domain_root": _root("domain"),
        "scope_ref": "scope:test",
        "transition_id": "transition:test",
    }
    if event_type in {"issuer_grant_activated", "issuer_grant_revoked"}:
        lineage = {
            **common,
            "stream_ref": _stream("issuer-grant", "scope:test", "grant:test"),
            "profile": "pheroos-scoped-authority-local-v2",
            "grant_ref": "grant:test",
            "grant_root": _root("grant"),
            "grant_binding_ref": _root("grant-binding"),
            "observed_epoch": 7,
            "revocation_generation": 1 if event_type.endswith("revoked") else 0,
        }
        if event_type == "issuer_grant_activated":
            lineage["verification_root"] = None
        return lineage
    session = {
        **common,
        "run_ref": "run:test",
        "request_ref": "request:test",
        "request_root": _root("request"),
        "grant_ref": "grant:test",
        "grant_root": _root("grant"),
        "grant_binding_ref": _root("grant-binding"),
        "observed_epoch": 7,
    }
    if event_type == "signal_verified":
        return {
            **session,
            "stream_ref": _stream(
                "verified-signal",
                "scope:test",
                "signal:test",
                "target:test",
            ),
            "operation": "verify_signal",
            "target_ref": "target:test",
            "signal_ref": "signal:test",
            "signal_root": _root("signal"),
            "evidence_root": _root("evidence"),
            "session_binding": _session_binding(
                "verify_signal",
                target_refs=["target:test"],
            ),
        }
    return {
        **session,
        "stream_ref": "authority:domain-lifecycle",
        "operation": "retire_domain",
        "reason_ref": "reason:test",
        "final_heads_root": _root("final-heads"),
        "seal_root": _root("seal"),
        "session_binding": _session_binding("retire_domain", target_refs=[]),
    }


def _event(event_type: str, lineage: dict[str, Any] | None = None) -> TraceEvent:
    selected = _lineage(event_type) if lineage is None else lineage
    target = {
        "issuer_grant_activated": "grant:test",
        "issuer_grant_revoked": "grant:test",
        "signal_verified": "target:test",
        "domain_retired": "scope:test",
    }[event_type]
    return TraceEvent(
        event_type=event_type,
        protocol_id="pheroos.protocol.v2",
        target=target,
        reason="scoped-authority transition",
        lineage=selected,
    )


def _event_payload(event_type: str) -> dict[str, Any]:
    event = _event(event_type)
    return {
        "event_type": event.event_type,
        "protocol_id": event.protocol_id,
        "target": event.target,
        "reason": event.reason,
        "lineage": deepcopy(event.lineage),
    }


def _event_from_payload(payload: dict[str, Any]) -> TraceEvent:
    return TraceEvent(
        event_type=payload["event_type"],
        protocol_id=payload["protocol_id"],
        target=payload["target"],
        reason=payload["reason"],
        lineage=payload["lineage"],
    )


@pytest.mark.parametrize("event_type", sorted(AUTHORITY_EVENTS))
def test_authority_event_contract_and_schema_accept_valid_lineage(
    event_type: str,
) -> None:
    event = _event(event_type)

    event.validate()
    Draft202012Validator(trace_schema()).validate(_event_payload(event_type))
    assert event_type in VALID_EVENT_TYPES
    assert set(EVENT_LINEAGE_CONTRACTS[event_type]) <= set(event.lineage)


def test_authenticated_activation_requires_exact_verification_root() -> None:
    lineage = _lineage("issuer_grant_activated")
    lineage["profile"] = "pheroos-scoped-authority-authenticated-v2"
    lineage["verification_root"] = _root("verification")
    _event("issuer_grant_activated", lineage).validate()

    lineage["verification_root"] = None
    with pytest.raises(ValueError, match="verification_root"):
        _event("issuer_grant_activated", lineage).validate()


def test_authority_lineage_allows_non_authoritative_additional_projection() -> None:
    lineage = _lineage("signal_verified")
    lineage["x-audit-note"] = {"source": "host:test"}

    _event("signal_verified", lineage).validate()
    payload = _event_payload("signal_verified")
    payload["lineage"] = lineage
    Draft202012Validator(trace_schema()).validate(payload)


def test_authority_schema_does_not_constrain_namespaced_extensions() -> None:
    Draft202012Validator(trace_schema()).validate(
        {
            "event_type": "x-authority-observation",
            "protocol_id": "protocol:extension",
            "target": "target:extension",
            "reason": "extension-owned semantics",
            "lineage": {
                "transition_id": "genesis",
                "session_binding": {"target_refs": ["z", "a", "a"]},
            },
        }
    )


@pytest.mark.parametrize("event_type", sorted(AUTHORITY_EVENTS))
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value.__setitem__("protocol_id", "protocol:other"),
            "protocol_id",
        ),
        (
            lambda value: value["lineage"].__setitem__("transition_id", "genesis"),
            "transition_id is reserved",
        ),
    ],
)
def test_every_authority_event_runtime_and_schema_reject_invalid_envelope(
    event_type: str,
    mutation: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    payload = _event_payload(event_type)
    mutation(payload)

    with pytest.raises(ValueError, match=message):
        _event_from_payload(payload).validate()
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize(
    ("event_type", "mutation", "message"),
    [
        (
            "issuer_grant_revoked",
            lambda value: value["lineage"].__setitem__("revocation_generation", 0),
            "must advance",
        ),
        (
            "issuer_grant_activated",
            lambda value: value["lineage"].__setitem__(
                "verification_root", _root("forged-verification")
            ),
            "cannot claim verification",
        ),
        (
            "issuer_grant_activated",
            lambda value: value["lineage"].update(
                {
                    "profile": "pheroos-scoped-authority-authenticated-v2",
                    "verification_root": None,
                }
            ),
            "verification_root",
        ),
        (
            "domain_retired",
            lambda value: value["lineage"].__setitem__(
                "stream_ref", "authority:domain-lifecycle:forged"
            ),
            "must be lifecycle",
        ),
        (
            "signal_verified",
            lambda value: value["lineage"]["session_binding"].__setitem__(
                "target_refs", ["target:test", "target:test"]
            ),
            "contains duplicates",
        ),
        (
            "signal_verified",
            lambda value: value["lineage"]["session_binding"].__setitem__(
                "target_refs", ["target:z", "target:a"]
            ),
            "canonical UTF-8 order",
        ),
        (
            "signal_verified",
            lambda value: value["lineage"]["session_binding"].__setitem__(
                "action_refs", ["action:forged"]
            ),
            "target/action bounds",
        ),
        (
            "domain_retired",
            lambda value: value["lineage"]["session_binding"].__setitem__(
                "action_refs", ["action:a", "action:a"]
            ),
            "contains duplicates",
        ),
        (
            "domain_retired",
            lambda value: value["lineage"]["session_binding"].__setitem__(
                "action_refs", ["action:z", "action:a"]
            ),
            "canonical UTF-8 order",
        ),
        (
            "signal_verified",
            lambda value: value["lineage"]["session_binding"].__setitem__(
                "action_refs", "action:forged"
            ),
            "must be arrays",
        ),
        (
            "signal_verified",
            lambda value: value["lineage"]["session_binding"].__setitem__(
                "operation", "retire_domain"
            ),
            "session_binding.operation is mismatched",
        ),
        (
            "signal_verified",
            lambda value: value["lineage"].__setitem__(
                "transition_id", " transition:test"
            ),
            "canonical text",
        ),
    ],
)
def test_authority_runtime_and_schema_reject_expressible_invalid_events(
    event_type: str,
    mutation: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    payload = _event_payload(event_type)
    mutation(payload)

    with pytest.raises(ValueError, match=message):
        _event_from_payload(payload).validate()
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize(
    ("event_type", "mutation", "message"),
    [
        (
            "issuer_grant_activated",
            lambda value: value.pop("domain_root"),
            "missing required fields",
        ),
        (
            "issuer_grant_activated",
            lambda value: value.__setitem__("stream_ref", "authority:forged"),
            "stream_ref is not canonical",
        ),
        (
            "issuer_grant_revoked",
            lambda value: value.__setitem__("revocation_generation", 0),
            "must advance",
        ),
        (
            "signal_verified",
            lambda value: value.__setitem__("signal_root", "sha256:ABC"),
            "signal_root",
        ),
        (
            "signal_verified",
            lambda value: value["session_binding"].__setitem__(
                "request_ref", "request:other"
            ),
            "session_binding.request_ref is mismatched",
        ),
        (
            "signal_verified",
            lambda value: value["session_binding"].__setitem__("target_refs", []),
            "target/action bounds",
        ),
        (
            "domain_retired",
            lambda value: value.__setitem__("stream_ref", "authority:other"),
            "must be lifecycle",
        ),
        (
            "domain_retired",
            lambda value: value["session_binding"].__setitem__("unexpected", "forged"),
            "session_binding fields",
        ),
    ],
)
def test_authority_lineage_mutations_fail_closed(
    event_type: str,
    mutation: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    lineage = deepcopy(_lineage(event_type))
    mutation(lineage)

    with pytest.raises(ValueError, match=message):
        _event(event_type, lineage).validate()


def test_authority_event_rejects_wrong_protocol_and_target() -> None:
    event = _event("signal_verified")
    with pytest.raises(ValueError, match="protocol_id"):
        TraceEvent(
            event.event_type,
            "protocol:other",
            event.target,
            event.reason,
            event.lineage,
        ).validate()
    with pytest.raises(ValueError, match="target must match"):
        TraceEvent(
            event.event_type,
            event.protocol_id,
            "target:other",
            event.reason,
            event.lineage,
        ).validate()
