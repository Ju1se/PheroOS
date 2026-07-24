from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
import pytest

from pheroos.trace import EVENT_LINEAGE_CONTRACTS, TraceEvent, VALID_EVENT_TYPES
from pheroos.trace.schema import trace_schema
from tests.trace.test_trace_store import (
    _durable_membership_read_set_root,
    valid_event_context,
    valid_lineage,
)


EVENT_TYPES = (
    "principal_verification_set_advanced",
    "membership_epoch_committed",
)
ROOT = Path(__file__).resolve().parents[2]


def _payload(event_type: str) -> dict[str, Any]:
    protocol_id, target = valid_event_context(event_type)
    return {
        "event_type": event_type,
        "protocol_id": protocol_id,
        "target": target,
        "reason": "test durable membership lineage",
        "lineage": deepcopy(valid_lineage(event_type)),
    }


def _validate_runtime(payload: dict[str, Any]) -> None:
    TraceEvent(**payload).validate()


def _substitute_last_hex(value: str) -> str:
    return value[:-1] + ("0" if value[-1] != "0" else "1")


@pytest.mark.parametrize("event_type", EVENT_TYPES)
def test_durable_membership_trace_is_exact_closed_and_schema_valid(
    event_type: str,
) -> None:
    payload = _payload(event_type)

    _validate_runtime(payload)
    Draft202012Validator(trace_schema()).validate(payload)
    assert event_type in VALID_EVENT_TYPES
    assert EVENT_LINEAGE_CONTRACTS[event_type] == frozenset(payload["lineage"])


@pytest.mark.parametrize("event_type", EVENT_TYPES)
def test_durable_membership_trace_rejects_unknown_and_missing_fields(
    event_type: str,
) -> None:
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
    ("event_type", "mutation", "message"),
    [
        (
            EVENT_TYPES[0],
            lambda value: value["lineage"].__setitem__(
                "authority_policy_root", "SHA256:not-canonical"
            ),
            "authority_policy_root",
        ),
        (
            EVENT_TYPES[0],
            lambda value: value["lineage"].__setitem__("record_count", True),
            "record_count",
        ),
        (
            EVENT_TYPES[0],
            lambda value: value["lineage"].__setitem__("parent_revision", True),
            "parent_revision",
        ),
        (
            EVENT_TYPES[1],
            lambda value: value["lineage"].__setitem__("mutation_issuer_ref", ""),
            "mutation_issuer_ref",
        ),
        (
            EVENT_TYPES[1],
            lambda value: value["lineage"].__setitem__(
                "verification_head_root", "sha256:ABC"
            ),
            "verification_head_root",
        ),
        (
            EVENT_TYPES[1],
            lambda value: value["lineage"].__setitem__(
                "verification_record_count", True
            ),
            "verification_record_count",
        ),
    ],
)
def test_durable_membership_trace_rejects_bad_exact_types_and_roots(
    event_type: str,
    mutation: Callable[[dict[str, Any]], object],
    message: str,
) -> None:
    payload = _payload(event_type)
    mutation(payload)

    with pytest.raises(ValueError, match=message):
        _validate_runtime(payload)
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize("event_type", EVENT_TYPES)
def test_fixed_stream_rejects_context_and_transition_substitution(
    event_type: str,
) -> None:
    stream_substitution = _payload(event_type)
    stream_substitution["lineage"]["stream_ref"] = _substitute_last_hex(
        stream_substitution["lineage"]["stream_ref"]
    )
    transition_substitution = _payload(event_type)
    transition_substitution["lineage"]["transition_id"] = _substitute_last_hex(
        transition_substitution["lineage"]["transition_id"]
    )
    policy_substitution = _payload(event_type)
    policy_field = (
        "verification_policy_root"
        if event_type == EVENT_TYPES[0]
        else "membership_policy_root"
    )
    policy_substitution["lineage"][policy_field] = "sha256:" + "0" * 64

    for payload in (
        stream_substitution,
        transition_substitution,
        policy_substitution,
    ):
        with pytest.raises(ValueError, match="canonical"):
            _validate_runtime(payload)


@pytest.mark.parametrize("event_type", EVENT_TYPES)
def test_membership_text_bounds_reject_oversized_ascii_in_runtime_and_schema(
    event_type: str,
) -> None:
    payload = _payload(event_type)
    oversized = "i" * 4097
    payload["lineage"]["mutation_issuer_ref"] = oversized
    payload["lineage"]["grant_issuer_ref"] = oversized

    with pytest.raises(ValueError, match="byte bound"):
        _validate_runtime(payload)
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize("event_type", EVENT_TYPES)
def test_membership_text_runtime_enforces_utf8_bytes_beyond_schema_approximation(
    event_type: str,
) -> None:
    payload = _payload(event_type)
    oversized_utf8 = "界" * 1366
    payload["lineage"]["mutation_issuer_ref"] = oversized_utf8
    payload["lineage"]["grant_issuer_ref"] = oversized_utf8

    with pytest.raises(ValueError, match="byte bound"):
        _validate_runtime(payload)
    Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize("event_type", EVENT_TYPES)
@pytest.mark.parametrize("field", ("source_context_root", "read_set_root"))
def test_integrity_roots_are_independently_derived(
    event_type: str,
    field: str,
) -> None:
    payload = _payload(event_type)
    payload["lineage"][field] = _substitute_last_hex(payload["lineage"][field])

    with pytest.raises(ValueError, match=field):
        _validate_runtime(payload)
    Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize("event_type", EVENT_TYPES)
def test_grant_issuer_must_match_the_mutation_issuer(event_type: str) -> None:
    payload = _payload(event_type)
    payload["lineage"]["grant_issuer_ref"] = "issuer:detached"

    with pytest.raises(ValueError, match="issuer binding"):
        _validate_runtime(payload)
    Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize(
    ("event_type", "genesis_root", "parent_kind"),
    [
        (
            EVENT_TYPES[0],
            ("sha256:250b6db081d9b7bd133f06b6c3192bb409c2f97e2bb462d2c0302d81bbda7ec5"),
            "principal-verification-v2",
        ),
        (
            EVENT_TYPES[1],
            ("sha256:442d957d649f827ae3be2c4389d9ca281f25c86355f54fb1efc0895c61f3c797"),
            "membership-v2",
        ),
    ],
)
def test_epoch_revision_and_parent_semantics_are_closed(
    event_type: str,
    genesis_root: str,
    parent_kind: str,
) -> None:
    genesis = _payload(event_type)
    assert genesis["lineage"]["parent_snapshot_root"] == genesis_root
    _validate_runtime(genesis)

    wrong_genesis = deepcopy(genesis)
    wrong_genesis["lineage"]["parent_epoch"] = 0
    with pytest.raises(ValueError, match="genesis parent epoch"):
        _validate_runtime(wrong_genesis)
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(wrong_genesis)

    wrong_genesis_revision = deepcopy(genesis)
    wrong_genesis_revision["lineage"]["parent_revision"] = 1
    with pytest.raises(ValueError, match="genesis parent revision"):
        _validate_runtime(wrong_genesis_revision)
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(wrong_genesis_revision)

    successor = deepcopy(genesis)
    successor["lineage"].update(
        {
            "revision": 2,
            "parent_revision": 1,
            "epoch": 2,
            "parent_epoch": 1,
            "parent_transition_id": f"transition:{parent_kind}:" + "1" * 64,
            "parent_snapshot_root": "sha256:" + "2" * 64,
        }
    )
    successor["lineage"]["read_set_root"] = _durable_membership_read_set_root(
        event_type,
        successor["lineage"],
    )
    _validate_runtime(successor)
    Draft202012Validator(trace_schema()).validate(successor)
    successor["lineage"]["epoch"] = 1
    with pytest.raises(ValueError, match="epoch must advance"):
        _validate_runtime(successor)

    revision_gap = deepcopy(genesis)
    revision_gap["lineage"].update(
        {
            "revision": 3,
            "parent_revision": 1,
            "epoch": 2,
            "parent_epoch": 1,
            "parent_transition_id": f"transition:{parent_kind}:" + "1" * 64,
            "parent_snapshot_root": "sha256:" + "2" * 64,
        }
    )
    with pytest.raises(ValueError, match="revision must advance exactly"):
        _validate_runtime(revision_gap)
    Draft202012Validator(trace_schema()).validate(revision_gap)


def test_principal_verification_root_count_is_exact_and_bounded() -> None:
    payload = _payload(EVENT_TYPES[0])
    payload["lineage"]["record_count"] = 1
    with pytest.raises(ValueError, match="verification_roots count"):
        _validate_runtime(payload)

    payload = _payload(EVENT_TYPES[0])
    payload["lineage"]["verification_roots"][0] = "bad-root"
    with pytest.raises(ValueError, match="verification_roots"):
        _validate_runtime(payload)
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)

    payload = _payload(EVENT_TYPES[0])
    payload["lineage"]["verification_roots"].reverse()
    with pytest.raises(ValueError, match="not canonical"):
        _validate_runtime(payload)
    Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("verification_stream_ref", "authority:membership-v2:" + "0" * 64, "stream"),
        (
            "verification_transition_id",
            "transition:membership-v2:" + "0" * 64,
            "transition",
        ),
        ("verification_revision", 0, "revision"),
        ("cluster_count", 0, "counts"),
        ("principal_count", 0, "counts"),
    ],
)
def test_membership_verification_binding_and_counts_are_closed(
    field: str,
    value: object,
    message: str,
) -> None:
    payload = _payload(EVENT_TYPES[1])
    payload["lineage"][field] = value

    with pytest.raises(ValueError, match=message):
        _validate_runtime(payload)
    with pytest.raises(ValidationError):
        Draft202012Validator(trace_schema()).validate(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("verification_policy_root", "sha256:" + "0" * 64, "stream_ref"),
        ("verification_request_ref", "advance:detached", "transition_id"),
        ("verification_current_step", 3, "timeline"),
        ("verification_expires_at_step", 99, "timeline"),
        ("verification_record_count", 1, "count"),
    ],
)
def test_membership_derives_the_complete_verification_binding(
    field: str,
    value: object,
    message: str,
) -> None:
    payload = _payload(EVENT_TYPES[1])
    payload["lineage"][field] = value

    with pytest.raises(ValueError, match=message):
        _validate_runtime(payload)
    Draft202012Validator(trace_schema()).validate(payload)


def test_membership_rejects_canonical_looking_detached_verification_ids() -> None:
    payload = _payload(EVENT_TYPES[1])
    payload["lineage"]["verification_stream_ref"] = (
        "authority:principal-verification-v2:" + "0" * 64
    )
    payload["lineage"]["verification_transition_id"] = (
        "transition:principal-verification-v2:" + "1" * 64
    )

    with pytest.raises(ValueError, match="verification_stream_ref"):
        _validate_runtime(payload)
    Draft202012Validator(trace_schema()).validate(payload)


def test_membership_source_roots_require_canonical_order() -> None:
    payload = _payload(EVENT_TYPES[1])
    payload["lineage"]["source_trace_roots"].reverse()

    with pytest.raises(ValueError, match="not canonical"):
        _validate_runtime(payload)


@pytest.mark.parametrize("event_type", EVENT_TYPES)
def test_epoch_and_issuer_are_state_not_fixed_stream_selectors(event_type: str) -> None:
    payload = _payload(event_type)
    stream_ref = payload["lineage"]["stream_ref"]
    payload["lineage"]["epoch"] = 130
    payload["lineage"]["mutation_issuer_ref"] = "issuer:rotated"
    payload["lineage"]["grant_issuer_ref"] = "issuer:rotated"

    _validate_runtime(payload)
    assert payload["lineage"]["stream_ref"] == stream_ref


def test_trace_owner_is_independent_from_private_governance() -> None:
    for relative in (
        "pheroos/trace/_contracts/membership_authority.py",
        "pheroos/trace/_contracts/membership_integrity.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "pheroos.governance" not in source
        assert "_support_v2" not in source
        assert len(source.splitlines()) < 600


def test_governance_owner_events_match_the_independent_trace_contract() -> None:
    from pheroos.governance._support_v2.membership_contracts import (
        MembershipCommitRequestV2,
    )
    from pheroos.governance._support_v2.membership_state import _membership_event
    from pheroos.governance._support_v2.principal_verification_state import (
        _verification_event,
    )
    from tests.governance.test_membership_v2_contracts_source import (
        _membership_snapshot,
        _prepare_verification,
        _root,
    )

    verification, _ = _prepare_verification()

    def binding(
        request_ref: str,
        request_root: str,
        operation: str,
        observed_epoch: int,
    ) -> dict[str, object]:
        return {
            "domain_root": verification.domain_root,
            "scope_ref": verification.scope_ref,
            "run_ref": verification.run_ref,
            "request_ref": request_ref,
            "request_root": request_root,
            "operation": operation,
            "observed_epoch": observed_epoch,
            "grant_ref": "grant:test",
            "grant_root": _root("grant"),
            "grant_binding_ref": _root("grant-binding"),
            "grant_expected_revision": 1,
            "grant_expected_root": _root("grant-head"),
            "lifecycle_expected_revision": 0,
            "lifecycle_expected_root": _root("lifecycle-head"),
            "target_refs": [verification.target_ref],
            "action_refs": [],
        }

    verification_binding = binding(
        verification.advance_ref,
        verification.request_root,
        "qualify_evidence",
        verification.observed_epoch,
    )
    verification_preview = _verification_event(
        verification,
        verification_binding,
        parent_head_root=_root("verification-parent-head"),
        read_set_root=_root("placeholder-read-set"),
    )
    verification_event = _verification_event(
        verification,
        verification_binding,
        parent_head_root=_root("verification-parent-head"),
        read_set_root=_durable_membership_read_set_root(
            verification_preview.event_type,
            verification_preview.lineage,
        ),
    )
    membership_snapshot = _membership_snapshot(
        verification.snapshot,
        verification_head_root=_root("verification-head"),
        epoch=1,
        revision=1,
        parent=None,
    )
    membership_request = MembershipCommitRequestV2(
        domain_root=membership_snapshot.domain_root,
        scope_ref=membership_snapshot.scope_ref,
        run_ref=membership_snapshot.run_ref,
        target_ref=membership_snapshot.target_ref,
        epoch=membership_snapshot.epoch,
        observed_epoch=membership_snapshot.observed_epoch,
        request_ref=membership_snapshot.request_ref,
        stream_ref=membership_snapshot.stream_ref,
        transition_id=membership_snapshot.transition_id,
        snapshot=membership_snapshot,
    )
    membership_binding = binding(
        membership_request.request_ref,
        membership_request.request_root,
        "evaluate_quorum",
        membership_request.observed_epoch,
    )
    membership_preview = _membership_event(
        membership_request,
        membership_binding,
        parent_head_root=_root("membership-parent-head"),
        read_set_root=_root("placeholder-read-set"),
    )
    membership_event = _membership_event(
        membership_request,
        membership_binding,
        parent_head_root=_root("membership-parent-head"),
        read_set_root=_durable_membership_read_set_root(
            membership_preview.event_type,
            membership_preview.lineage,
        ),
    )

    for event in (verification_event, membership_event):
        event.validate()
        Draft202012Validator(trace_schema()).validate(
            {
                "event_type": event.event_type,
                "protocol_id": event.protocol_id,
                "target": event.target,
                "reason": event.reason,
                "lineage": event.lineage,
            }
        )
        assert EVENT_LINEAGE_CONTRACTS[event.event_type] == frozenset(event.lineage)
