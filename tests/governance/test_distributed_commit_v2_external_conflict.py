from __future__ import annotations

from copy import copy
from dataclasses import replace
import pickle
from typing import cast

import pytest
from jsonschema import Draft202012Validator

from pheroos.conformance.checks._distributed_v2_context_support import (
    capability_v2,
    root_v2,
)
from pheroos.conformance.checks._distributed_v2_vertical_support import (
    DistributedV2Vertical,
    _signed_witness_v2,
    advance_conflict_decision_v2,
    build_verified_distributed_vertical_v2,
    external_witness_conflict_observation_v2,
    freeze_external_witness_conflict_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceDomainRetirementRequestV2,
    governance_issuer_grant_stream_ref_v2,
    open_governance_authority_session_v2,
    retire_governance_domain_v2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitDispositionV2,
)
from pheroos.governance.commit_decision_v2 import CommitDecisionOutcomeKindV2
from pheroos.governance.distributed_commit_v2 import (
    DistributedLaneStatusV2,
    DistributedMutationKindV2,
    DistributedProposalStateV2,
    DistributedWitnessConflictObservationV2,
    DistributedWitnessStateV2,
    VerifiedDistributedAdvanceSourceV2,
    VerifiedDistributedWitnessStateV2,
    advance_distributed_commit_v2,
    distributed_state_is_current_v2,
    open_distributed_authority_session_v2,
    prepare_distributed_witness_conflict_observation_v2,
    prepare_distributed_witness_v2,
    rehydrate_distributed_state_v2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2
from pheroos.trace import InMemoryTraceStore, TraceEvent
from pheroos.trace.schema import trace_schema
from tests.governance._commit_certificate_v2_race_support import (
    DependencyRaceStoreV2,
)


class _SameShapeSource:
    __slots__ = ("request_root",)

    def __init__(self, request_root: str) -> None:
        self.request_root = request_root


def _vertical(label: str) -> DistributedV2Vertical:
    return build_verified_distributed_vertical_v2(
        ReferenceGovernanceStateStoreConformanceAdapterV2(), label
    )


def _prepare_conflict(
    vertical: DistributedV2Vertical,
    observation: DistributedWitnessConflictObservationV2,
    label: str,
    *,
    verifier: object | None = None,
):
    return prepare_distributed_witness_conflict_observation_v2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        epoch_state=vertical.epoch,
        proposal_state=vertical.proposal,
        parent_state=vertical.witness,
        manifest=vertical.context.manifest,
        observation=observation,
        trusted_verifier=vertical.verifier if verifier is None else verifier,
        mutation_ref=f"mutation:external-conflict:{label}",
        mutation_issuer_ref=vertical.context.grant.issuer_ref,
        current_step=10,
    )


def _session(vertical: DistributedV2Vertical, request: object):
    observed_epoch = object.__getattribute__(request, "observed_epoch")
    return open_distributed_authority_session_v2(
        capability_v2(vertical.context, observed_epoch), request
    )


def _trace_payload(event: TraceEvent) -> dict[str, object]:
    return {
        "event_type": event.event_type,
        "protocol_id": event.protocol_id,
        "target": event.target,
        "reason": event.reason,
        "lineage": event.lineage,
    }


def test_external_observation_is_durable_freeze_only_and_decision_visible() -> None:
    vertical = _vertical("external-conflict-vertical")
    conflict = freeze_external_witness_conflict_v2(
        vertical, "external-conflict-vertical"
    )
    snapshot = conflict.witness.snapshot
    state = cast(DistributedWitnessStateV2, snapshot.state)
    assert snapshot.status is DistributedLaneStatusV2.FROZEN
    assert snapshot.mutation_kind is DistributedMutationKindV2.EQUIVOCATION_FROZEN
    assert snapshot.revision == 2
    assert len(state.witnesses) == 2
    assert len(state.equivocations) == 1
    finding = state.equivocations[0]
    assert finding.conflict_observation is not None
    assert finding.conflict_observation.to_dict() == conflict.observation.to_dict()
    assert all(
        item.proposal_digest != conflict.observation.proposal.proposal_digest
        for item in cast(
            DistributedProposalStateV2, vertical.proposal.snapshot.state
        ).proposals
    )
    assert (
        vertical.context.store.load_head_v2(
            vertical.proposal.snapshot.scope_ref, vertical.proposal.stream_ref
        ).revision
        == 1
    )
    assert (
        vertical.context.store.load_head_v2(
            vertical.certificate.snapshot.scope_ref, vertical.certificate.stream_ref
        ).revision
        == 1
    )

    view = vertical.context.store.load_commit_view_v2(
        conflict.witness_request.scope_ref,
        conflict.witness_request.stream_ref,
        conflict.witness_request.transition_id,
    )
    assert view.committed_transition is not None
    event = view.committed_transition.batch.trace_batch.events[0]
    assert event.event_type == "distributed_witness_conflict_v2"
    InMemoryTraceStore().append(event)
    Draft202012Validator(trace_schema()).validate(_trace_payload(event))

    retry = advance_distributed_commit_v2(
        conflict.witness_request,
        source=conflict.witness_source,
        authority_session=_session(vertical, conflict.witness_request),
    )
    assert retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert retry.committed_transition is not None
    assert retry.committed_transition.receipt.receipt_root == (
        view.committed_transition.receipt.receipt_root
    )

    restarted = vertical.context.adapter.restart_store_v2(vertical.context.store)
    restored = rehydrate_distributed_state_v2(
        conflict.witness_request.to_dict(),
        domain=vertical.context.domain,
        state_reader=restarted,
    )
    assert type(restored) is VerifiedDistributedWitnessStateV2
    assert distributed_state_is_current_v2(restored)
    restored_state = cast(DistributedWitnessStateV2, restored.snapshot.state)
    assert restored_state.equivocations[0].conflict_observation is not None
    assert (
        restored_state.equivocations[0].conflict_observation.observation_root
        == conflict.observation.observation_root
    )

    terminal = advance_conflict_decision_v2(
        conflict, "external-conflict-vertical"
    ).snapshot
    assert terminal.outcome is not None
    assert terminal.outcome.kind is CommitDecisionOutcomeKindV2.SAFETY_VIOLATION
    assert terminal.outcome.reason_codes == ("finality:conflict",)


def test_external_observation_requires_trusted_verifier_and_sealed_binding() -> None:
    vertical = _vertical("external-conflict-rejections")
    observation = external_witness_conflict_observation_v2(
        vertical, "external-conflict-rejections"
    )
    with pytest.raises(ValueError, match="attestation is not trusted"):
        _prepare_conflict(
            vertical,
            observation,
            "string-verifier",
            verifier="trusted:by-name",
        )

    bad_witness = replace(
        observation.witness,
        attestation_ref="attestation:unverified",
        witness_root="",
    )
    unsigned = replace(
        observation,
        witness=bad_witness,
        observation_root="",
    )
    with pytest.raises(ValueError, match="attestation is not trusted"):
        _prepare_conflict(vertical, unsigned, "unsigned")

    changed_value = replace(
        observation.proposal.value,
        membership_head_root=root_v2("external:wrong-membership-head"),
        semantic_value_root="",
    )
    changed_proposal = replace(
        observation.proposal,
        value=changed_value,
        proposal_digest="",
    )
    changed_witness, _ = _signed_witness_v2(
        changed_proposal,
        vertical.identity,
        nonce="nonce:external:wrong-membership",
        current_step=10,
    )
    cross_bound = replace(
        observation,
        proposal=changed_proposal,
        witness=changed_witness,
        observation_root="",
    )
    with pytest.raises(ValueError, match="changes sealed authority"):
        _prepare_conflict(vertical, cross_bound, "cross-bound")


def test_external_observation_portable_shape_has_no_source_authority() -> None:
    vertical = _vertical("external-conflict-source")
    observation = external_witness_conflict_observation_v2(
        vertical, "external-conflict-source"
    )
    request, source = _prepare_conflict(vertical, observation, "source")
    assert type(source) is VerifiedDistributedAdvanceSourceV2
    assert copy(source) is source
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(source)
    portable = pickle.loads(pickle.dumps(observation))
    assert portable.to_dict() == observation.to_dict()
    assert (
        DistributedWitnessConflictObservationV2.from_dict(observation.to_dict())
        == observation
    )
    session = _session(vertical, request)
    for forged in (
        observation,
        _SameShapeSource(request.request_root),
        object(),
    ):
        attempt = advance_distributed_commit_v2(
            request,
            source=forged,
            authority_session=session,
        )
        assert attempt.disposition is GovernanceCommitDispositionV2.INVALID
    assert (
        vertical.context.store.load_head_v2(
            request.scope_ref, request.stream_ref
        ).revision
        == 1
    )


def test_external_observation_stale_parent_and_lifecycle_race_fail_closed() -> None:
    stale = _vertical("external-conflict-stale")
    observation = external_witness_conflict_observation_v2(
        stale, "external-conflict-stale"
    )
    conflict_request, conflict_source = _prepare_conflict(stale, observation, "stale")
    proposal = cast(
        DistributedProposalStateV2, stale.proposal.snapshot.state
    ).proposals[0]
    retry_witness, _ = _signed_witness_v2(
        proposal,
        stale.identity,
        nonce="nonce:external:parent-advance",
        current_step=10,
    )
    retry_request, retry_source = prepare_distributed_witness_v2(
        decision_state=stale.decision,
        central_certificate_state=stale.central,
        membership_state=stale.identity.membership,
        epoch_state=stale.epoch,
        proposal_state=stale.proposal,
        parent_state=stale.witness,
        manifest=stale.context.manifest,
        witness=retry_witness,
        trusted_verifier=stale.verifier,
        mutation_ref="mutation:external:parent-advance",
        mutation_issuer_ref=stale.context.grant.issuer_ref,
        current_step=10,
    )
    advanced = advance_distributed_commit_v2(
        retry_request,
        source=retry_source,
        authority_session=_session(stale, retry_request),
    )
    assert advanced.disposition is GovernanceCommitDispositionV2.COMMITTED
    rejected = advance_distributed_commit_v2(
        conflict_request,
        source=conflict_source,
        authority_session=_session(stale, conflict_request),
    )
    assert rejected.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert rejected.failure is not None
    assert rejected.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE

    raced = _vertical("external-conflict-retirement-race")
    raced_observation = external_witness_conflict_observation_v2(
        raced, "external-conflict-retirement-race"
    )
    raced_request, raced_source = _prepare_conflict(
        raced, raced_observation, "retirement-race"
    )
    race_store = DependencyRaceStoreV2(raced.context.store)
    race_context = replace(raced.context, store=race_store)
    grant_stream = governance_issuer_grant_stream_ref_v2(
        raced.context.domain.scope_ref, raced.context.grant.grant_ref
    )
    authority_states = (
        raced.identity.verification,
        raced.identity.membership,
        raced.inputs.replay,
        raced.inputs.risk,
        raced.inputs.support,
        raced.inputs.evidence,
        raced.inputs.stop,
        raced.inputs.permission,
        raced.decision,
        raced.central,
        raced.epoch,
        raced.proposal,
        raced.witness,
        raced.certificate,
    )
    stream_refs = tuple(
        sorted(
            {
                grant_stream,
                *(
                    object.__getattribute__(item, "snapshot").stream_ref
                    for item in authority_states
                ),
            }
        )
    )
    retirement = GovernanceDomainRetirementRequestV2(
        domain_root=raced.context.domain.domain_root,
        scope_ref=raced.context.domain.scope_ref,
        run_ref=raced_observation.proposal.value.run_ref,
        request_ref="request:external-conflict:retire",
        transition_id="transition:external-conflict:retire",
        stream_refs=stream_refs,
        reason_ref="reason:external-conflict:test-complete",
        observed_epoch=raced_request.observed_epoch,
    )
    retirement_session = open_governance_authority_session_v2(
        capability_v2(raced.context, retirement.observed_epoch), retirement
    )
    retirement_attempts = []

    def retire_during_commit() -> None:
        retirement_attempts.append(
            retire_governance_domain_v2(
                retirement, authority_session=retirement_session
            )
        )

    race_store.armed_stream_ref = raced_request.stream_ref
    race_store.before_atomic = retire_during_commit
    raced_session = open_distributed_authority_session_v2(
        capability_v2(race_context, raced_request.observed_epoch), raced_request
    )
    raced_attempt = advance_distributed_commit_v2(
        raced_request,
        source=raced_source,
        authority_session=raced_session,
    )
    assert len(retirement_attempts) == 1
    assert (
        retirement_attempts[0].disposition is GovernanceCommitDispositionV2.COMMITTED
    ), (
        None
        if retirement_attempts[0].failure is None
        else retirement_attempts[0].failure.to_dict()
    )
    assert raced_attempt.disposition is GovernanceCommitDispositionV2.DENIED
    assert raced_attempt.failure is not None
    assert raced_attempt.failure.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED
    )
    assert (
        raced.context.store.load_head_v2(
            raced_request.scope_ref, raced_request.stream_ref
        ).revision
        == 1
    )


__all__: tuple[str, ...] = ()
