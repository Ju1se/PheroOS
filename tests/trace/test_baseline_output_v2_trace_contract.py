from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
import pytest

from pheroos.trace import EVENT_LINEAGE_CONTRACTS, TraceEvent, VALID_EVENT_TYPES
from pheroos.trace.schema import trace_schema


BASELINE_OUTPUT_EVENTS = frozenset(
    {
        "baseline_manifest_activated",
        "baseline_evidence_qualified",
        "baseline_stop_resolved",
        "baseline_decision_evaluated",
        "baseline_action_permission_issued",
        "baseline_output_committed",
    }
)
ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_OWNER = ROOT / "pheroos" / "trace" / "_contracts" / "authority.py"


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _operation(event_type: str) -> str:
    return (
        "authorize_output"
        if event_type == "baseline_output_committed"
        else "issue_action_permission"
    )


def _session_binding(operation: str) -> dict[str, object]:
    return {
        "domain_root": _root("domain"),
        "scope_ref": "scope:baseline-output",
        "run_ref": "run:baseline-output",
        "request_ref": "request:baseline-output",
        "request_root": _root("request"),
        "operation": operation,
        "observed_epoch": 7,
        "grant_ref": "grant:baseline-output",
        "grant_root": _root("grant"),
        "grant_binding_ref": _root("grant-binding"),
        "grant_expected_revision": 1,
        "grant_expected_root": _root("grant-head"),
        "lifecycle_expected_revision": 0,
        "lifecycle_expected_root": _root("lifecycle-head"),
        "target_refs": ["target:baseline-output"],
        "action_refs": ["action:publish"],
    }


def _lineage(event_type: str) -> dict[str, Any]:
    operation = _operation(event_type)
    lineage: dict[str, Any] = {
        "domain_root": _root("domain"),
        "scope_ref": "scope:baseline-output",
        # Governance has not yet frozen the six canonical stream derivations.
        # Trace therefore validates this as canonical text, not a guessed hash.
        "stream_ref": f"authority:baseline-output:{event_type}",
        "transition_id": f"transition:{event_type}",
        "run_ref": "run:baseline-output",
        "request_ref": "request:baseline-output",
        "request_root": _root("request"),
        "grant_ref": "grant:baseline-output",
        "grant_root": _root("grant"),
        "grant_binding_ref": _root("grant-binding"),
        "operation": operation,
        "observed_epoch": 7,
        "session_binding": _session_binding(operation),
        "target_ref": "target:baseline-output",
        "action_ref": "action:publish",
        "manifest_root": _root("manifest"),
        "output_policy_root": _root("output-policy"),
    }
    if event_type == "baseline_manifest_activated":
        lineage["protocol_ref"] = "protocol:baseline-output"
    elif event_type == "baseline_evidence_qualified":
        lineage.update(
            evidence_root=_root("evidence"),
            qualified_signal_count=2,
        )
    elif event_type == "baseline_stop_resolved":
        lineage["stop_root"] = _root("stop")
    else:
        lineage.update(
            evidence_root=_root("evidence"),
            stop_root=_root("stop"),
            decision_root=_root("decision"),
            candidate_ref="candidate:accepted",
            terminal_status="evidence_commit",
        )
    if event_type == "baseline_action_permission_issued":
        lineage.update(
            effect="publish",
            output_payload_root=_root("output-payload"),
            permission_root=_root("permission"),
            permission_disposition="authorized",
            expires_at_epoch=11,
        )
    elif event_type == "baseline_output_committed":
        lineage.update(
            effect="publish",
            output_payload_root=_root("output-payload"),
            permission_root=_root("permission"),
            result_root=_root("result"),
            delivery_disposition="deliverable",
            action_disposition="authorized",
            read_set_root=_root("read-set"),
        )
    return lineage


def _event(event_type: str, lineage: dict[str, Any] | None = None) -> TraceEvent:
    return TraceEvent(
        event_type=event_type,
        protocol_id="pheroos.protocol.v2",
        target="target:baseline-output",
        reason="record one scoped baseline output authority transition",
        lineage=_lineage(event_type) if lineage is None else lineage,
    )


def _payload(event_type: str) -> dict[str, Any]:
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


@pytest.mark.parametrize("event_type", sorted(BASELINE_OUTPUT_EVENTS))
def test_baseline_output_event_runtime_and_schema_accept_exact_lineage(
    event_type: str,
) -> None:
    event = _event(event_type)

    event.validate()
    Draft202012Validator(trace_schema()).validate(_payload(event_type))
    assert event_type in VALID_EVENT_TYPES
    assert EVENT_LINEAGE_CONTRACTS[event_type] == frozenset(event.lineage)


def test_baseline_output_trace_owner_remains_governance_independent() -> None:
    source = AUTHORITY_OWNER.read_text(encoding="utf-8")

    assert "pheroos.governance" not in source


@pytest.mark.parametrize("event_type", sorted(BASELINE_OUTPUT_EVENTS))
@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value.__setitem__("protocol_id", "protocol:legacy"),
            "protocol_id",
        ),
        (
            lambda value: value["lineage"].__setitem__("transition_id", "genesis"),
            "transition_id is reserved",
        ),
        (
            lambda value: value["lineage"].__setitem__("stream_ref", " "),
            "stream_ref",
        ),
    ],
)
def test_every_baseline_output_event_rejects_invalid_envelope_in_runtime_and_schema(
    event_type: str,
    mutation: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    payload = _payload(event_type)
    mutation(payload)

    with pytest.raises(ValueError, match=message):
        _event_from_payload(payload).validate()
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize("event_type", sorted(BASELINE_OUTPUT_EVENTS))
def test_baseline_output_event_requires_exact_operation_and_session_cardinality(
    event_type: str,
) -> None:
    wrong_operation = (
        "issue_action_permission"
        if _operation(event_type) == "authorize_output"
        else "authorize_output"
    )
    for mutation in (
        lambda value: value.__setitem__("operation", wrong_operation),
        lambda value: value["session_binding"].__setitem__(
            "operation", wrong_operation
        ),
        lambda value: value["session_binding"].__setitem__("target_refs", []),
        lambda value: value["session_binding"].__setitem__("action_refs", []),
    ):
        lineage = deepcopy(_lineage(event_type))
        mutation(lineage)
        payload = _payload(event_type)
        payload["lineage"] = lineage

        with pytest.raises(ValueError):
            _event(event_type, lineage).validate()
        with pytest.raises(ValidationError):
            Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize("event_type", sorted(BASELINE_OUTPUT_EVENTS))
def test_baseline_output_runtime_matches_session_and_event_target_values(
    event_type: str,
) -> None:
    request_mismatch = deepcopy(_lineage(event_type))
    request_mismatch["session_binding"]["request_root"] = _root("other-request")
    with pytest.raises(ValueError, match="session_binding.request_root is mismatched"):
        _event(event_type, request_mismatch).validate()

    target_bound_mismatch = deepcopy(_lineage(event_type))
    target_bound_mismatch["session_binding"]["target_refs"] = ["target:other"]
    with pytest.raises(ValueError, match="target/action bounds"):
        _event(event_type, target_bound_mismatch).validate()

    action_bound_mismatch = deepcopy(_lineage(event_type))
    action_bound_mismatch["session_binding"]["action_refs"] = ["action:execute"]
    with pytest.raises(ValueError, match="target/action bounds"):
        _event(event_type, action_bound_mismatch).validate()

    event = TraceEvent(
        event_type=event_type,
        protocol_id="pheroos.protocol.v2",
        target="target:other",
        reason="record one scoped baseline output authority transition",
        lineage=_lineage(event_type),
    )
    with pytest.raises(ValueError, match="target must match target_ref"):
        event.validate()


@pytest.mark.parametrize(
    ("event_type", "mutation", "message"),
    [
        (
            "baseline_manifest_activated",
            lambda value: value.__setitem__("protocol_ref", ""),
            "protocol_ref",
        ),
        (
            "baseline_evidence_qualified",
            lambda value: value.__setitem__("qualified_signal_count", True),
            "qualified_signal_count",
        ),
        (
            "baseline_stop_resolved",
            lambda value: value.__setitem__("stop_root", "sha256:ABC"),
            "stop_root",
        ),
        (
            "baseline_decision_evaluated",
            lambda value: value.__setitem__("terminal_status", "pending"),
            "terminal_status",
        ),
        (
            "baseline_action_permission_issued",
            lambda value: value.__setitem__("effect", "broadcast"),
            "effect",
        ),
        (
            "baseline_action_permission_issued",
            lambda value: value.__setitem__("permission_disposition", "pending"),
            "permission_disposition",
        ),
        (
            "baseline_action_permission_issued",
            lambda value: value.__setitem__("expires_at_epoch", -1),
            "expires_at_epoch",
        ),
        (
            "baseline_output_committed",
            lambda value: value.__setitem__("delivery_disposition", "hidden"),
            "delivery_disposition",
        ),
        (
            "baseline_output_committed",
            lambda value: value.__setitem__("action_disposition", "pending"),
            "action_disposition",
        ),
        (
            "baseline_output_committed",
            lambda value: value.__setitem__("read_set_root", "sha256:ABC"),
            "read_set_root",
        ),
    ],
)
def test_baseline_output_field_constraints_have_runtime_schema_parity(
    event_type: str,
    mutation: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    lineage = deepcopy(_lineage(event_type))
    mutation(lineage)
    payload = _payload(event_type)
    payload["lineage"] = lineage

    with pytest.raises(ValueError, match=message):
        _event(event_type, lineage).validate()
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize(
    ("event_type", "disposition_field"),
    [
        ("baseline_action_permission_issued", "permission_disposition"),
        ("baseline_output_committed", "action_disposition"),
    ],
)
def test_blocked_baseline_output_cannot_claim_action_authority(
    event_type: str,
    disposition_field: str,
) -> None:
    lineage = deepcopy(_lineage(event_type))
    lineage["terminal_status"] = "blocked"
    lineage[disposition_field] = "authorized"
    payload = _payload(event_type)
    payload["lineage"] = lineage

    with pytest.raises(ValueError, match="blocked output cannot authorize"):
        _event(event_type, lineage).validate()
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)

    lineage[disposition_field] = "denied"
    _event(event_type, lineage).validate()
    payload["lineage"] = lineage
    Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize("event_type", sorted(BASELINE_OUTPUT_EVENTS))
def test_baseline_stream_derivation_is_shape_only_until_governance_freezes_it(
    event_type: str,
) -> None:
    """Do not guess a canonical stream hash before the Governance ABI owns it."""

    lineage = deepcopy(_lineage(event_type))
    lineage["stream_ref"] = "authority:baseline-output:declared-stream"
    payload = _payload(event_type)
    payload["lineage"] = lineage

    _event(event_type, lineage).validate()
    Draft202012Validator(trace_schema()).validate(payload)
