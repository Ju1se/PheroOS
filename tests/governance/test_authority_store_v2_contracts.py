from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from hashlib import sha256
import json
from typing import Any

import pytest

from pheroos.governance.authority_store_v2 import (
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_GENESIS_PARENT_ROOT_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDiagnosticCodeV2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitInclusionProofV2,
    GovernanceCommitPositionObservationV2,
    GovernanceCommitPositionV2,
    GovernanceCommitReceiptV2,
    GovernanceCommitViewV2,
    GovernanceCommittedTransitionV2,
    GovernanceDomainSealV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
    GovernanceStateStoreV2,
    GovernanceStateWriterV2,
    GovernanceTraceBatchV2,
    PreparedGovernanceTransitionV2,
    governance_authority_state_root_v2,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    AuthorityDiagnosticCodeV2 as ProtocolAuthorityDiagnosticCodeV2,
    GovernanceAuthorityReadSetV2,
    GovernanceReadPreconditionV2,
)
from pheroos.trace import TraceEvent


ROOT_PREFIX = "pheroos-governance-authority-v2:"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _root(kind: str, body: object) -> str:
    return (
        "sha256:"
        + sha256((ROOT_PREFIX + kind).encode() + b"\x00" + _canonical(body)).hexdigest()
    )


def _domain(profile: str = AUTHORITY_LOCAL_PROFILE_V2) -> AuthorityDomainV2:
    return AuthorityDomainV2(
        policy_version=AUTHORITY_POLICY_VERSION_V2,
        profile=profile,
        wire_version=AUTHORITY_WIRE_VERSION_V2,
        canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref="scope:alpha",
    )


def _event(
    *,
    scope_ref: str = "scope:alpha",
    stream_ref: str = "authority:decision",
    transition_id: str = "transition:1",
    **lineage: Any,
) -> TraceEvent:
    return TraceEvent(
        event_type="x-authority-v2-commit",
        protocol_id="protocol:authority-v2",
        target="target:decision",
        reason="atomic authority transition",
        lineage={
            "scope_ref": scope_ref,
            "stream_ref": stream_ref,
            "transition_id": transition_id,
            **lineage,
        },
    )


def _committed_fixture() -> tuple[
    AuthorityDomainV2,
    GovernanceHeadV2,
    PreparedGovernanceTransitionV2,
    GovernanceTraceBatchV2,
    GovernanceCommitBatchV2,
    GovernanceCommitReceiptV2,
    GovernanceCommitInclusionProofV2,
    GovernanceCommittedTransitionV2,
    GovernanceCommitPositionObservationV2,
]:
    domain = _domain()
    head = GovernanceHeadV2.genesis(domain, "authority:decision")
    read_set = GovernanceAuthorityReadSetV2(
        entries=(
            GovernanceReadPreconditionV2(
                stream_ref=head.stream_ref,
                expected_revision=head.revision,
                expected_root=head.head_root,
            ),
        )
    )
    transition = PreparedGovernanceTransitionV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=head.stream_ref,
        transition_id="transition:1",
        expected_revision=head.revision,
        expected_root=head.head_root,
        read_set_root=read_set.root(),
        state_records={"decision": {"candidate": "candidate:a", "weight": 1}},
    )
    trace_batch = GovernanceTraceBatchV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=head.stream_ref,
        transition_id=transition.transition_id,
        events=(_event(),),
    )
    batch = GovernanceCommitBatchV2(
        domain=domain,
        scope_ref=domain.scope_ref,
        stream_ref=head.stream_ref,
        transition_id=transition.transition_id,
        kind="transition",
        read_set=read_set,
        trace_batch=trace_batch,
        transition=transition,
    )
    committed_head = GovernanceHeadV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=head.stream_ref,
        revision=1,
        parent_root=head.head_root,
        state_root=transition.state_root,
        transition_id=transition.transition_id,
        batch_root=batch.batch_root,
    )
    receipt = GovernanceCommitReceiptV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=head.stream_ref,
        transition_id=transition.transition_id,
        revision=1,
        parent_root=head.head_root,
        head_root=committed_head.head_root,
        state_root=transition.state_root,
        read_set_root=read_set.root(),
        trace_root=trace_batch.trace_root,
        batch_root=batch.batch_root,
    )
    inclusion = GovernanceCommitInclusionProofV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=head.stream_ref,
        transition_id=transition.transition_id,
        revision=receipt.revision,
        batch_root=batch.batch_root,
        receipt_root=receipt.receipt_root,
        head_root=receipt.head_root,
    )
    committed = GovernanceCommittedTransitionV2(
        batch=batch,
        receipt=receipt,
        inclusion_proof=inclusion,
    )
    position = GovernanceCommitPositionObservationV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=head.stream_ref,
        transition_id=transition.transition_id,
        receipt_root=receipt.receipt_root,
        observed_revision=receipt.revision,
        observed_head_root=receipt.head_root,
        position=GovernanceCommitPositionV2.CURRENT,
    )
    return (
        domain,
        head,
        transition,
        trace_batch,
        batch,
        receipt,
        inclusion,
        committed,
        position,
    )


def _seal_fixture() -> tuple[GovernanceDomainSealV2, GovernanceCommitBatchV2]:
    domain = _domain()
    lifecycle = GovernanceHeadV2.genesis(
        domain,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    )
    decision = GovernanceHeadV2.genesis(domain, "authority:decision")
    read_set = GovernanceAuthorityReadSetV2(
        entries=tuple(
            sorted(
                (
                    GovernanceReadPreconditionV2(
                        lifecycle.stream_ref,
                        lifecycle.revision,
                        lifecycle.head_root,
                    ),
                    GovernanceReadPreconditionV2(
                        decision.stream_ref,
                        decision.revision,
                        decision.head_root,
                    ),
                ),
                key=lambda item: item.stream_ref.encode(),
            )
        )
    )
    seal = GovernanceDomainSealV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        transition_id="transition:seal",
        expected_revision=lifecycle.revision,
        expected_root=lifecycle.head_root,
        final_heads=(
            {
                "stream_ref": decision.stream_ref,
                "revision": decision.revision,
                "head_root": decision.head_root,
            },
        ),
    )
    traces = GovernanceTraceBatchV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=lifecycle.stream_ref,
        transition_id=seal.transition_id,
        events=(
            _event(
                stream_ref=lifecycle.stream_ref,
                transition_id=seal.transition_id,
                seal_root=seal.seal_root,
            ),
        ),
    )
    return seal, GovernanceCommitBatchV2(
        domain=domain,
        scope_ref=domain.scope_ref,
        stream_ref=lifecycle.stream_ref,
        transition_id=seal.transition_id,
        kind="seal",
        read_set=read_set,
        trace_batch=traces,
        seal=seal,
    )


def _all_root_records() -> tuple[tuple[Any, str, str], ...]:
    (
        domain,
        head,
        transition,
        trace_batch,
        batch,
        receipt,
        inclusion,
        committed,
        position,
    ) = _committed_fixture()
    failure = GovernanceFailureV2(
        code=AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        path="/read_set/entries/0",
        stage=GovernanceFailureStageV2.PRECONDITION,
    )
    attempt = GovernanceCommitAttemptV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        disposition=GovernanceCommitDispositionV2.COMMITTED,
        failure=None,
        committed_transition=committed,
        position_observation=position,
    )
    view = GovernanceCommitViewV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        expected_receipt_root=receipt.receipt_root,
        disposition=GovernanceCommitDispositionV2.COMMITTED,
        failure=None,
        committed_transition=committed,
        position_observation=position,
        observed_revision=position.observed_revision,
        observed_head_root=position.observed_head_root,
    )
    seal, _ = _seal_fixture()
    return (
        (domain, "domain_root", "domain"),
        (head, "head_root", "head"),
        (transition, "transition_root", "transition"),
        (trace_batch, "trace_root", "trace-batch"),
        (batch, "batch_root", "commit-batch"),
        (receipt, "receipt_root", "receipt"),
        (inclusion, "inclusion_root", "inclusion"),
        (
            committed,
            "committed_transition_root",
            "committed-transition",
        ),
        (position, "observation_root", "position-observation"),
        (failure, "failure_root", "failure"),
        (attempt, "attempt_root", "attempt"),
        (view, "view_root", "view"),
        (seal, "seal_root", "seal"),
    )


def test_governance_uses_protocol_owned_diagnostic_and_read_set_types() -> None:
    assert AuthorityDiagnosticCodeV2 is ProtocolAuthorityDiagnosticCodeV2
    assert len(AuthorityDiagnosticCodeV2) == 17
    assert set(GovernanceCommitDispositionV2) == {
        "committed",
        "denied",
        "retry_required",
        "finality_unavailable",
        "invalid",
    }
    assert set(GovernanceCommitPositionV2) == {
        "current",
        "superseded",
        "sealed",
    }


def test_domain_requires_every_exact_selector_and_has_independent_root() -> None:
    domain = _domain(AUTHORITY_AUTHENTICATED_PROFILE_V2)
    body = domain.to_dict()
    root = body.pop("domain_root")
    assert root == _root("domain", body)
    assert domain.root() == root
    assert domain.canonical_bytes() == _canonical(domain.to_dict())
    assert AuthorityDomainV2.from_dict(domain.to_dict()) == domain

    mutated = domain.to_dict()
    mutated["profile"] = AUTHORITY_LOCAL_PROFILE_V2
    with pytest.raises(ValueError, match="domain_root"):
        AuthorityDomainV2.from_dict(mutated)

    class TextSubclass(str):
        pass

    with pytest.raises(ValueError, match="profile"):
        AuthorityDomainV2(
            policy_version=AUTHORITY_POLICY_VERSION_V2,
            profile=TextSubclass(AUTHORITY_LOCAL_PROFILE_V2),
            wire_version=AUTHORITY_WIRE_VERSION_V2,
            canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
            ledger_version=AUTHORITY_LEDGER_VERSION_V2,
            state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
            trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
            read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
            scope_ref="scope:alpha",
        )


@pytest.mark.parametrize("index", range(13))
def test_every_public_root_record_uses_exact_separator_nul_formula(index: int) -> None:
    value, root_field, kind = _all_root_records()[index]
    body = value.to_dict()
    stored_root = body.pop(root_field)
    assert stored_root == _root(kind, body)
    assert value.root() == stored_root


@pytest.mark.parametrize("invalid_root", [None, False, 0])
def test_every_public_root_record_rejects_non_string_wire_root(
    invalid_root: object,
) -> None:
    for value, root_field, _ in _all_root_records():
        wire = value.to_dict()
        wire[root_field] = invalid_root
        with pytest.raises((TypeError, ValueError), match="root"):
            type(value).from_dict(wire)


def test_root_autofill_requires_exact_string_empty_sentinel() -> None:
    class EmptyTextSubclass(str):
        pass

    class EqualToEmpty:
        def __eq__(self, other: object) -> bool:
            return other == ""

    domain = _domain()
    trace = _committed_fixture()[3]
    for invalid_root in (EmptyTextSubclass(""), EqualToEmpty()):
        with pytest.raises((TypeError, ValueError), match="root"):
            AuthorityDomainV2(
                policy_version=domain.policy_version,
                profile=domain.profile,
                wire_version=domain.wire_version,
                canonical_version=domain.canonical_version,
                ledger_version=domain.ledger_version,
                state_store_version=domain.state_store_version,
                trace_batch_version=domain.trace_batch_version,
                read_set_version=domain.read_set_version,
                scope_ref=domain.scope_ref,
                domain_root=invalid_root,
            )
        with pytest.raises((TypeError, ValueError), match="root"):
            GovernanceTraceBatchV2(
                canonical_version=trace.canonical_version,
                domain_root=trace.domain_root,
                scope_ref=trace.scope_ref,
                stream_ref=trace.stream_ref,
                transition_id=trace.transition_id,
                events=trace.events,
                schema=trace.schema,
                trace_root=invalid_root,
            )


def test_genesis_and_complete_state_root_are_exact_and_scope_bound() -> None:
    domain = _domain()
    head = GovernanceHeadV2.genesis(domain, "authority:decision")
    assert head.parent_root == GOVERNANCE_GENESIS_PARENT_ROOT_V2
    assert head.batch_root == GOVERNANCE_GENESIS_PARENT_ROOT_V2
    assert head.transition_id == "genesis"
    assert head.state_root == governance_authority_state_root_v2(
        domain.scope_ref,
        head.stream_ref,
        {},
    )
    body = head.to_dict()
    assert body.pop("head_root") == _root("head", body)
    assert GovernanceHeadV2.from_dict(head.to_dict()) == head


def test_genesis_head_rejects_forged_nonempty_state_even_with_matching_head_root() -> (
    None
):
    domain = _domain()
    wire = GovernanceHeadV2.genesis(domain, "authority:decision").to_dict()
    wire["state_root"] = governance_authority_state_root_v2(
        domain.scope_ref,
        "authority:decision",
        {"forged": True},
    )
    wire.pop("head_root")
    wire["head_root"] = _root("head", wire)

    with pytest.raises(ValueError, match="genesis head fields"):
        GovernanceHeadV2.from_dict(wire)


def test_prepared_transition_cannot_target_reserved_lifecycle_stream() -> None:
    domain = _domain()
    head = GovernanceHeadV2.genesis(
        domain,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    )
    read_set = GovernanceAuthorityReadSetV2(
        entries=(
            GovernanceReadPreconditionV2(
                head.stream_ref,
                head.revision,
                head.head_root,
            ),
        )
    )

    with pytest.raises(ValueError, match="cannot target lifecycle stream"):
        PreparedGovernanceTransitionV2(
            domain_root=domain.domain_root,
            scope_ref=domain.scope_ref,
            stream_ref=GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
            transition_id="transition:forged-lifecycle",
            expected_revision=head.revision,
            expected_root=head.head_root,
            read_set_root=read_set.root(),
            state_records={"forged": True},
        )


@pytest.mark.parametrize(
    "index",
    range(9),
)
def test_root_bearing_transition_records_round_trip(index: int) -> None:
    fixture = _committed_fixture()
    values = (
        fixture[0],
        fixture[1],
        fixture[2],
        fixture[3],
        fixture[4],
        fixture[5],
        fixture[6],
        fixture[7],
        fixture[8],
    )
    value = values[index]
    restored = type(value).from_dict(value.to_dict())
    assert restored == value
    assert restored.canonical_bytes() == _canonical(value.to_dict())
    assert restored.root() == value.root()


def test_state_and_trace_inputs_are_defensive_and_float_free() -> None:
    domain = _domain()
    head = GovernanceHeadV2.genesis(domain, "authority:decision")
    read_set = GovernanceAuthorityReadSetV2(
        entries=(GovernanceReadPreconditionV2(head.stream_ref, 0, head.head_root),)
    )
    state: dict[str, Any] = {"nested": {"items": [1, 2]}}
    transition = PreparedGovernanceTransitionV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=head.stream_ref,
        transition_id="transition:1",
        expected_revision=0,
        expected_root=head.head_root,
        read_set_root=read_set.root(),
        state_records=state,
    )
    original_root = transition.root()
    state["nested"]["items"].append(3)
    assert transition.root() == original_root
    assert transition.to_dict()["state_records"] == {"nested": {"items": [1, 2]}}

    lineage: dict[str, Any] = {
        "scope_ref": domain.scope_ref,
        "stream_ref": head.stream_ref,
        "transition_id": "transition:1",
        "nested": {"value": 1},
    }
    event = TraceEvent("x-authority-v2", "protocol:v2", "target:a", "reason", lineage)
    traces = GovernanceTraceBatchV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=head.stream_ref,
        transition_id="transition:1",
        events=(event,),
    )
    lineage["nested"]["value"] = 2
    detached = traces.events[0]
    detached.lineage["nested"]["value"] = 3
    assert traces.events[0].lineage["nested"]["value"] == 1

    with pytest.raises(TypeError, match="floating-point"):
        PreparedGovernanceTransitionV2(
            domain_root=domain.domain_root,
            scope_ref=domain.scope_ref,
            stream_ref=head.stream_ref,
            transition_id="transition:float",
            expected_revision=0,
            expected_root=head.head_root,
            read_set_root=read_set.root(),
            state_records={"not_canonical": 1.0},
        )
    float_event = _event(weight=0.5)
    with pytest.raises(TypeError, match="floating-point"):
        GovernanceTraceBatchV2(
            domain_root=domain.domain_root,
            scope_ref=domain.scope_ref,
            stream_ref=head.stream_ref,
            transition_id="transition:1",
            events=(float_event,),
        )
    assert governance_authority_state_root_v2(
        domain.scope_ref,
        head.stream_ref,
        {"": "empty keys remain valid canonical JSON"},
    ).startswith("sha256:")


def test_trace_batch_allows_ordered_repeated_canonical_events() -> None:
    domain = _domain()
    event = _event()
    batch = GovernanceTraceBatchV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref="authority:decision",
        transition_id="transition:1",
        events=(event, event),
    )
    assert len(batch.events) == 2


def test_trace_batch_rejects_declared_cross_domain_lineage() -> None:
    domain = _domain()
    event = _event(domain_root="sha256:" + "9" * 64)

    with pytest.raises(ValueError, match="domain_root"):
        GovernanceTraceBatchV2(
            domain_root=domain.domain_root,
            scope_ref=domain.scope_ref,
            stream_ref="authority:decision",
            transition_id="transition:1",
            events=(event,),
        )


@pytest.mark.parametrize("invalid_root", [None, False, 0])
def test_from_dict_rejects_non_string_stored_roots(invalid_root: object) -> None:
    domain = _domain()
    wire = domain.to_dict()
    wire["domain_root"] = invalid_root
    with pytest.raises((TypeError, ValueError), match="root"):
        AuthorityDomainV2.from_dict(wire)


def test_failure_is_typed_and_json_pointer_indexes_are_canonical() -> None:
    failure = GovernanceFailureV2(
        code=AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        path="/read_set/entries/0/expected_root",
        stage=GovernanceFailureStageV2.PRECONDITION,
    )
    assert GovernanceFailureV2.from_dict(failure.to_dict()) == failure
    assert failure.to_dict()["code"] == "governance_read_set_stale"
    with pytest.raises(ValueError, match="canonical base-10"):
        GovernanceFailureV2(
            code=AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_INVALID,
            path="/read_set/entries/01",
            stage=GovernanceFailureStageV2.VALIDATION,
        )


def test_all_17_diagnostics_map_to_one_exact_total_disposition() -> None:
    expected = {
        AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED: GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED: GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH: GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH: GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED: GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH: GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED: GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED: GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED: GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_INVALID: GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE: GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT: GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED: GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE: GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID: GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_ACTION_NOT_AUTHORIZED: GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_TRACE_LINEAGE_INVALID: GovernanceCommitDispositionV2.INVALID,
    }
    assert set(expected) == set(AuthorityDiagnosticCodeV2)
    assert {stage.value for stage in GovernanceFailureStageV2} == {
        "validation",
        "reconciliation",
        "precondition",
        "trace",
        "commit",
        "finality",
        "load",
        "seal",
    }
    domain = _domain()
    for code, disposition in expected.items():
        attempt = GovernanceCommitAttemptV2(
            domain_root=domain.domain_root,
            scope_ref=domain.scope_ref,
            stream_ref="authority:decision",
            transition_id="transition:failed",
            disposition=disposition,
            failure=GovernanceFailureV2(
                code=code,
                path="",
                stage=GovernanceFailureStageV2.VALIDATION,
            ),
            committed_transition=None,
            position_observation=None,
        )
        assert attempt.disposition is disposition
    with pytest.raises(ValueError, match="escape"):
        GovernanceFailureV2(
            code=AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_INVALID,
            path="/read_set/~2bad",
            stage=GovernanceFailureStageV2.VALIDATION,
        )


def test_attempt_and_view_enforce_total_result_exclusivity() -> None:
    *_, committed, position = _committed_fixture()
    batch = committed.batch
    attempt = GovernanceCommitAttemptV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        disposition=GovernanceCommitDispositionV2.COMMITTED,
        failure=None,
        committed_transition=committed,
        position_observation=position,
    )
    assert GovernanceCommitAttemptV2.from_dict(attempt.to_dict()) == attempt
    view = GovernanceCommitViewV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        expected_receipt_root=committed.receipt.receipt_root,
        disposition=GovernanceCommitDispositionV2.COMMITTED,
        failure=None,
        committed_transition=committed,
        position_observation=position,
        observed_revision=position.observed_revision,
        observed_head_root=position.observed_head_root,
    )
    assert GovernanceCommitViewV2.from_dict(view.to_dict()) == view

    stale = GovernanceFailureV2(
        code=AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        path="/read_set/entries/0",
        stage=GovernanceFailureStageV2.PRECONDITION,
    )
    retry = GovernanceCommitAttemptV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        disposition=GovernanceCommitDispositionV2.RETRY_REQUIRED,
        failure=stale,
        committed_transition=None,
        position_observation=None,
    )
    assert retry.committed_transition is None
    with pytest.raises(ValueError, match="mapping"):
        GovernanceCommitAttemptV2(
            domain_root=batch.domain_root,
            scope_ref=batch.scope_ref,
            stream_ref=batch.stream_ref,
            transition_id=batch.transition_id,
            disposition=GovernanceCommitDispositionV2.INVALID,
            failure=stale,
            committed_transition=None,
            position_observation=None,
        )


def test_aggregate_records_defensively_clone_nested_contracts() -> None:
    (
        domain,
        _,
        transition,
        _,
        batch,
        _,
        _,
        committed,
        position,
    ) = _committed_fixture()
    batch_wire = batch.to_dict()
    object.__setattr__(domain, "scope_ref", "scope:mutated")
    object.__setattr__(transition, "transition_id", "transition:mutated")
    assert batch.to_dict() == batch_wire

    committed_wire = committed.to_dict()
    object.__setattr__(batch, "transition_id", "transition:mutated")
    assert committed.to_dict() == committed_wire

    attempt = GovernanceCommitAttemptV2(
        domain_root=committed.batch.domain_root,
        scope_ref=committed.batch.scope_ref,
        stream_ref=committed.batch.stream_ref,
        transition_id=committed.batch.transition_id,
        disposition=GovernanceCommitDispositionV2.COMMITTED,
        failure=None,
        committed_transition=committed,
        position_observation=position,
    )
    attempt_wire = attempt.to_dict()
    object.__setattr__(committed, "committed_transition_root", "sha256:" + "f" * 64)
    object.__setattr__(position, "observed_revision", 99)
    assert attempt.to_dict() == attempt_wire


def test_batch_kind_requires_exact_str_and_wire_union_is_not_malleable() -> None:
    *_, batch, _, _, _, _ = _committed_fixture()

    class TextSubclass(str):
        pass

    with pytest.raises(ValueError, match="kind"):
        GovernanceCommitBatchV2(
            domain=batch.domain,
            scope_ref=batch.scope_ref,
            stream_ref=batch.stream_ref,
            transition_id=batch.transition_id,
            kind=TextSubclass("transition"),
            read_set=batch.read_set,
            trace_batch=batch.trace_batch,
            transition=batch.transition,
        )

    wire = batch.to_dict()
    wire["transition_root"] = None
    with pytest.raises(ValueError, match="closed union"):
        GovernanceCommitBatchV2.from_dict(wire)
    with pytest.raises(ValueError, match="unreachable"):
        GovernanceCommitViewV2(
            domain_root=batch.domain_root,
            scope_ref=batch.scope_ref,
            stream_ref=batch.stream_ref,
            transition_id=batch.transition_id,
            expected_receipt_root=None,
            disposition=GovernanceCommitDispositionV2.DENIED,
            failure=GovernanceFailureV2(
                code=AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
                path="/domain",
                stage=GovernanceFailureStageV2.LOAD,
            ),
            committed_transition=None,
            position_observation=None,
            observed_revision=None,
            observed_head_root=None,
        )


def test_legal_successor_is_superseded_not_invalid() -> None:
    *_, committed, _ = _committed_fixture()
    receipt = committed.receipt
    successor_root = "sha256:" + "a" * 64
    position = GovernanceCommitPositionObservationV2(
        domain_root=receipt.domain_root,
        scope_ref=receipt.scope_ref,
        stream_ref=receipt.stream_ref,
        transition_id=receipt.transition_id,
        receipt_root=receipt.receipt_root,
        observed_revision=receipt.revision + 1,
        observed_head_root=successor_root,
        position=GovernanceCommitPositionV2.SUPERSEDED,
    )
    view = GovernanceCommitViewV2(
        domain_root=receipt.domain_root,
        scope_ref=receipt.scope_ref,
        stream_ref=receipt.stream_ref,
        transition_id=receipt.transition_id,
        expected_receipt_root=None,
        disposition=GovernanceCommitDispositionV2.COMMITTED,
        failure=None,
        committed_transition=committed,
        position_observation=position,
        observed_revision=position.observed_revision,
        observed_head_root=position.observed_head_root,
    )
    assert view.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert view.position_observation is not None
    assert view.position_observation.position is GovernanceCommitPositionV2.SUPERSEDED


def test_seal_union_covers_lifecycle_plus_all_non_lifecycle_heads() -> None:
    seal, batch = _seal_fixture()
    assert batch.transition is None
    assert batch.seal_root == seal.seal_root
    assert GovernanceCommitBatchV2.from_dict(batch.to_dict()) == batch

    broken = batch.to_dict()
    broken["transition_root"] = "sha256:" + "b" * 64
    with pytest.raises(ValueError, match="closed union"):
        GovernanceCommitBatchV2.from_dict(broken)


def test_public_records_are_frozen_slotted_and_protocols_are_structural() -> None:
    domain, *_ = _committed_fixture()
    assert is_dataclass(domain)
    assert not hasattr(domain, "__dict__")
    with pytest.raises(FrozenInstanceError):
        domain.scope_ref = "scope:other"  # type: ignore[misc]

    class Adapter:
        state_store_version = GOVERNANCE_STATE_STORE_VERSION_V2

        def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
            raise NotImplementedError

        def load_state_v2(self, scope_ref: str, stream_ref: str) -> dict[str, Any]:
            raise NotImplementedError

        def load_commit_view_v2(
            self,
            scope_ref: str,
            stream_ref: str,
            transition_id: str,
            *,
            expected_receipt_root: str | None = None,
        ) -> GovernanceCommitViewV2:
            raise NotImplementedError

        def atomic_commit_v2(
            self,
            batch: GovernanceCommitBatchV2,
        ) -> GovernanceCommitAttemptV2:
            raise NotImplementedError

    adapter = Adapter()
    assert isinstance(adapter, GovernanceStateReaderV2)
    assert isinstance(adapter, GovernanceStateWriterV2)
    assert isinstance(adapter, GovernanceStateStoreV2)
