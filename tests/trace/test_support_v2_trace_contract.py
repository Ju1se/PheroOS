from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
import pytest

from pheroos.governance._authority_session_v2.contracts import (
    _governance_authority_session_state_v2,
)
from pheroos.governance._support_v2.support_operations import (
    advance_support_state_v2,
    rehydrate_support_state_v2,
)
from pheroos.governance._support_v2.support_state_handle import (
    require_current_support_state_v2,
)
from pheroos.trace import EVENT_LINEAGE_CONTRACTS, TraceEvent, VALID_EVENT_TYPES
from pheroos.trace.schema import trace_schema
from tests.governance.test_support_v2_contracts_evaluation import _support_session
from tests.trace.test_trace_store import (
    _support_root,
    valid_event_context,
    valid_lineage,
)


EVENT_TYPES = (
    "support_state_advanced",
    "support_lease_issued_v2",
    "support_lease_revoked_v2",
)
ROOT = Path(__file__).resolve().parents[2]


def _payload(event_type: str) -> dict[str, Any]:
    protocol_id, target = valid_event_context(event_type)
    return {
        "event_type": event_type,
        "protocol_id": protocol_id,
        "target": target,
        "reason": "test durable Support v2 lineage",
        "lineage": deepcopy(valid_lineage(event_type)),
    }


def _validate_runtime(payload: dict[str, Any]) -> None:
    TraceEvent(**payload).validate()


def _state_for_kind(kind: str) -> dict[str, Any]:
    if kind == "initialize":
        return _payload(EVENT_TYPES[0])
    payload = _payload(EVENT_TYPES[0])
    lineage = payload["lineage"]
    parent = deepcopy(lineage)
    sibling = valid_lineage(
        EVENT_TYPES[1] if kind in {"issue", "switch"} else EVENT_TYPES[2]
    )
    common = (
        "domain_root",
        "scope_ref",
        "stream_ref",
        "transition_id",
        "run_ref",
        "request_ref",
        "request_root",
        "grant_ref",
        "grant_root",
        "grant_binding_ref",
        "operation",
        "observed_epoch",
        "session_binding",
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "authority_policy_root",
        "protocol_ref",
        "target_ref",
        "mutation_issuer_ref",
    )
    for field in common:
        lineage[field] = deepcopy(sibling[field])
    issued = valid_lineage(EVENT_TYPES[1])
    revoked = valid_lineage(EVENT_TYPES[2])
    lineage.update(
        {
            "mutation_kind": kind,
            "revision": 2,
            "initialized_at_step": parent["initialized_at_step"],
            "current_step": 8,
            "mutation_provenance_root": revoked["provenance_root"]
            if kind == "revoke"
            else issued["issuance_provenance_root"],
            "mutation_trace_roots": deepcopy(
                revoked["source_trace_roots"]
                if kind == "revoke"
                else issued["issuance_trace_roots"]
            ),
            "evicted_lease_roots": [],
            "parent_revision": 1,
            "parent_transition_id": parent["transition_id"],
            "parent_snapshot_root": parent["snapshot_root"],
            "parent_history_root": parent["history_root"],
            "parent_history_count": 1,
            "history_count": 2,
            "parent_head_root": "sha256:" + "a" * 64,
            "snapshot_root": "sha256:" + "b" * 64,
            "source_context_root": "sha256:" + "c" * 64,
            "source_verification_root": "sha256:" + "d" * 64,
            "read_set_root": sibling["read_set_root"],
        }
    )
    if kind == "issue":
        lineage.update(
            {
                "issued_lease_root": issued["lease_root"],
                "revoked_lease_root": "",
                "revocation_root": "",
                "membership_stream_ref": issued["membership_stream_ref"],
                "membership_transition_id": issued["membership_transition_id"],
                "membership_snapshot_root": issued["membership_snapshot_root"],
                "active_lease_count": 1,
                "lease_set_root": "sha256:" + "e" * 64,
            }
        )
    elif kind == "revoke":
        lineage.update(
            {
                "issued_lease_root": "",
                "revoked_lease_root": revoked["lease_root"],
                "revocation_root": revoked["revocation_root"],
                "membership_stream_ref": "",
                "membership_transition_id": "",
                "membership_snapshot_root": "",
                "active_lease_count": 0,
                "lease_set_root": (
                    "sha256:23c99380d8b87c91dc9c69d963d0089a2b17f2a1db0b0cb2"
                    "bb108f3023c35fb7"
                ),
            }
        )
    else:
        lineage.update(
            {
                "issued_lease_root": "sha256:" + "f" * 64,
                "revoked_lease_root": revoked["lease_root"],
                "revocation_root": revoked["revocation_root"],
                "membership_stream_ref": issued["membership_stream_ref"],
                "membership_transition_id": issued["membership_transition_id"],
                "membership_snapshot_root": issued["membership_snapshot_root"],
                "active_lease_count": 1,
                "lease_set_root": "sha256:" + "e" * 64,
            }
        )
    _recommit_state(lineage)
    return payload


def _recommit_state(lineage: dict[str, Any]) -> None:
    delta = _support_root(
        "mutation-delta",
        {
            "mutation_kind": lineage["mutation_kind"],
            "transition_id": lineage["transition_id"],
            "mutation_issuer_ref": lineage["mutation_issuer_ref"],
            "observed_epoch": lineage["observed_epoch"],
            "current_step": lineage["current_step"],
            "mutation_provenance_root": lineage["mutation_provenance_root"],
            "mutation_trace_roots": lineage["mutation_trace_roots"],
            "issued_lease_root": lineage["issued_lease_root"],
            "revoked_lease_root": lineage["revoked_lease_root"],
            "revocation_root": lineage["revocation_root"],
            "evicted_lease_roots": lineage["evicted_lease_roots"],
            "membership_stream_ref": lineage["membership_stream_ref"],
            "membership_transition_id": lineage["membership_transition_id"],
            "membership_snapshot_root": lineage["membership_snapshot_root"],
        },
    )
    lineage["mutation_delta_root"] = delta
    count = lineage["parent_history_count"] + 1
    lineage["history_count"] = count
    lineage["history_root"] = _support_root(
        "history-link",
        {
            "parent_history_root": lineage["parent_history_root"],
            "parent_history_count": lineage["parent_history_count"],
            "transition_id": lineage["transition_id"],
            "mutation_delta_root": delta,
            "history_count": count,
        },
    )


@pytest.mark.parametrize("event_type", EVENT_TYPES)
def test_support_v2_trace_is_exact_closed_and_schema_valid(event_type: str) -> None:
    payload = _payload(event_type)

    _validate_runtime(payload)
    Draft202012Validator(trace_schema()).validate(payload)
    assert event_type in VALID_EVENT_TYPES
    assert EVENT_LINEAGE_CONTRACTS[event_type] == frozenset(payload["lineage"])


@pytest.mark.parametrize("event_type", EVENT_TYPES)
def test_support_v2_trace_rejects_unknown_and_missing_fields(event_type: str) -> None:
    unknown = _payload(event_type)
    unknown["lineage"]["caller_extension"] = "not-authority"
    missing = _payload(event_type)
    missing["lineage"].pop("authority_policy_root")

    for payload in (unknown, missing):
        with pytest.raises(ValueError):
            _validate_runtime(payload)
        with pytest.raises(ValidationError):
            Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("revision", True, "revision"),
        ("active_lease_count", 16_385, "active lease count"),
        ("authority_policy_root", "SHA256:bad", "authority_policy_root"),
        ("parent_revision", 1, "parent revision"),
    ],
)
def test_support_state_rejects_bad_exact_types_roots_and_counts(
    field: str,
    value: object,
    message: str,
) -> None:
    payload = _state_for_kind("initialize")
    payload["lineage"][field] = value

    with pytest.raises(ValueError, match=message):
        _validate_runtime(payload)
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


def test_support_state_runtime_rejects_time_before_initialization() -> None:
    payload = _state_for_kind("initialize")
    payload["lineage"]["initialized_at_step"] = 3

    with pytest.raises(ValueError, match="time moves"):
        _validate_runtime(payload)


@pytest.mark.parametrize("kind", ("initialize", "issue", "revoke", "switch"))
def test_all_support_mutations_have_closed_runtime_and_schema_semantics(
    kind: str,
) -> None:
    payload = _state_for_kind(kind)

    _validate_runtime(payload)
    Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value["lineage"].__setitem__(
                "mutation_delta_root", "sha256:" + "0" * 64
            ),
            "mutation delta root",
        ),
        (
            lambda value: value["lineage"].__setitem__(
                "history_root", "sha256:" + "0" * 64
            ),
            "history commitment",
        ),
        (
            lambda value: value["lineage"].__setitem__("membership_stream_ref", ""),
            "membership_stream_ref",
        ),
        (
            lambda value: value["lineage"].__setitem__("active_lease_count", 0),
            "issued lease is not active",
        ),
    ],
)
def test_support_state_rejects_detached_mutation_or_history_substitution(
    mutation: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    payload = _state_for_kind("issue")
    mutation(payload)

    with pytest.raises(ValueError, match=message):
        _validate_runtime(payload)


@pytest.mark.parametrize(
    "field",
    (
        "current_step",
        "mutation_provenance_root",
        "mutation_trace_roots",
    ),
)
def test_support_delta_binds_time_and_mutation_lineage(field: str) -> None:
    payload = _state_for_kind("issue")
    replacements: dict[str, object] = {
        "current_step": payload["lineage"]["current_step"] + 1,
        "mutation_provenance_root": "sha256:" + "0" * 64,
        "mutation_trace_roots": ["sha256:" + "0" * 64],
    }
    payload["lineage"][field] = replacements[field]

    with pytest.raises(ValueError, match="mutation delta root"):
        _validate_runtime(payload)


def test_support_delta_binds_observed_epoch_after_session_consistency() -> None:
    payload = _state_for_kind("issue")
    observed_epoch = payload["lineage"]["observed_epoch"] + 1
    payload["lineage"]["observed_epoch"] = observed_epoch
    payload["lineage"]["session_binding"]["observed_epoch"] = observed_epoch

    with pytest.raises(ValueError, match="mutation delta root"):
        _validate_runtime(payload)


def test_support_state_rejects_noncanonical_arrays_and_resource_overflow() -> None:
    reordered = _state_for_kind("issue")
    reordered["lineage"]["mutation_trace_roots"] = [
        "sha256:" + "f" * 64,
        "sha256:" + "0" * 64,
    ]
    with pytest.raises(ValueError, match="not canonical"):
        _validate_runtime(reordered)

    duplicate = _state_for_kind("issue")
    root = "sha256:" + "1" * 64
    duplicate["lineage"]["evicted_lease_roots"] = [root, root]
    with pytest.raises(ValueError, match="not canonical"):
        _validate_runtime(duplicate)

    oversized = _state_for_kind("issue")
    oversized["lineage"]["mutation_trace_roots"] = [root] * 1025
    with pytest.raises(ValueError, match="count"):
        _validate_runtime(oversized)
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(oversized)


def test_support_state_rejects_invalid_empty_projection_and_switch_reuse() -> None:
    empty = _state_for_kind("revoke")
    empty["lineage"]["lease_set_root"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="empty lease set"):
        _validate_runtime(empty)
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(empty)

    reused = _state_for_kind("switch")
    reused["lineage"]["issued_lease_root"] = reused["lineage"]["revoked_lease_root"]
    _recommit_state(reused["lineage"])
    with pytest.raises(ValueError, match="reuses"):
        _validate_runtime(reused)


@pytest.mark.parametrize(
    ("event_type", "field", "value", "message"),
    [
        (
            EVENT_TYPES[1],
            "mutation_transition_id",
            "transition:support-v2:" + "0" * 64,
            "mutation transition",
        ),
        (EVENT_TYPES[1], "issuance_issuer_ref", "issuer:other", "issuance issuer"),
        (EVENT_TYPES[1], "lease_ref", "lease:support-v2:" + "0" * 64, "lease_ref"),
        (
            EVENT_TYPES[1],
            "membership_stream_ref",
            "authority:membership-v1:" + "0" * 64,
            "membership stream",
        ),
        (
            EVENT_TYPES[2],
            "mutation_transition_id",
            "transition:support-v2:" + "0" * 64,
            "mutation transition",
        ),
        (
            EVENT_TYPES[2],
            "revocation_issuer_ref",
            "issuer:other",
            "revocation issuer",
        ),
        (
            EVENT_TYPES[2],
            "revocation_ref",
            "revocation:support-v2:" + "0" * 64,
            "revocation_ref",
        ),
    ],
)
def test_issue_and_revoke_events_reject_cross_binding_substitution(
    event_type: str,
    field: str,
    value: object,
    message: str,
) -> None:
    payload = _payload(event_type)
    payload["lineage"][field] = value

    with pytest.raises(ValueError, match=message):
        _validate_runtime(payload)


def test_support_issuer_rotation_is_state_not_stream_and_revocation_is_owned() -> None:
    payload = _payload(EVENT_TYPES[2])
    lineage = payload["lineage"]
    stream_ref = lineage["stream_ref"]
    assert lineage["lease_issuance_issuer_ref"] != lineage["revocation_issuer_ref"]

    _validate_runtime(payload)
    assert lineage["stream_ref"] == stream_ref

    successor = _state_for_kind("issue")
    successor["lineage"]["mutation_issuer_ref"] = "issuer:rotated"
    _recommit_state(successor["lineage"])
    _validate_runtime(successor)
    assert successor["lineage"]["stream_ref"] == stream_ref


@pytest.mark.parametrize(
    ("event_type", "field"),
    [
        (EVENT_TYPES[1], "candidate_ref"),
        (EVENT_TYPES[1], "issuance_issuer_ref"),
        (EVENT_TYPES[2], "reason_codes"),
        (EVENT_TYPES[2], "lease_issuance_issuer_ref"),
    ],
)
def test_support_runtime_and_schema_reject_oversized_ascii_text(
    event_type: str,
    field: str,
) -> None:
    payload = _payload(event_type)
    payload["lineage"][field] = ["x" * 4097] if field == "reason_codes" else "x" * 4097

    with pytest.raises(ValueError, match="byte bound"):
        _validate_runtime(payload)
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


def test_support_runtime_enforces_utf8_bytes_beyond_schema_approximation() -> None:
    payload = _payload(EVENT_TYPES[1])
    payload["lineage"]["candidate_ref"] = "界" * 1366

    with pytest.raises(ValueError, match="byte bound"):
        _validate_runtime(payload)


def test_support_specialized_array_bounds_and_lifetimes_are_closed() -> None:
    issued = _payload(EVENT_TYPES[1])
    issued["lineage"]["expires_at_step"] = issued["lineage"]["issued_at_step"]
    with pytest.raises(ValueError, match="lifetime"):
        _validate_runtime(issued)

    revoked = _payload(EVENT_TYPES[2])
    revoked["lineage"]["reason_codes"] = ["reason"] * 129
    with pytest.raises(ValueError, match="count"):
        _validate_runtime(revoked)
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(revoked)


def test_fixed_stream_rejects_manifest_commit_profile_and_target_substitution() -> None:
    for field, value in (
        ("manifest_root", "sha256:" + "0" * 64),
        ("commit_policy_root", "sha256:" + "0" * 64),
        ("profile", "pheroos-certified-commit-v1"),
        ("target_ref", "target:other"),
    ):
        payload = _payload(EVENT_TYPES[0])
        payload["lineage"][field] = value
        with pytest.raises(ValueError):
            _validate_runtime(payload)


def test_real_support_store_commit_and_rehydrate_use_canonical_trace_event() -> None:
    domain, request, source, session = _support_session()
    attempt = advance_support_state_v2(
        request,
        source=source,
        authority_session=session,
    )

    assert attempt.committed_transition is not None
    events = attempt.committed_transition.batch.trace_batch.events
    assert tuple(event.event_type for event in events) == (EVENT_TYPES[0],)
    events[0].validate()
    Draft202012Validator(trace_schema()).validate(
        {
            "event_type": events[0].event_type,
            "protocol_id": events[0].protocol_id,
            "target": events[0].target,
            "reason": events[0].reason,
            "lineage": deepcopy(events[0].lineage),
        }
    )
    state = rehydrate_support_state_v2(
        request.to_dict(),
        domain=domain,
        state_reader=_governance_authority_session_state_v2(session).store,
    )
    assert require_current_support_state_v2(state) == request.snapshot


def test_support_trace_owner_is_independent_and_bounded() -> None:
    source = (ROOT / "pheroos/trace/_contracts/support_authority.py").read_text(
        encoding="utf-8"
    )

    assert "pheroos.governance" not in source
    assert "_support_v2" not in source
    assert len(source.splitlines()) < 600
