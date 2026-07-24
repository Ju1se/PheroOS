from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from hashlib import sha256
import hmac
import json
import pickle
from typing import cast

import pytest
from jsonschema import Draft202012Validator

from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from tests.governance._commit_certificate_v2_store_support import (
    _capability,
    _root,
)
from tests.governance._distributed_v2_store_support import (
    distributed_context,
    finalize_distributed_decision,
    sealed_distributed_decision,
)
from tests.governance._distributed_v2_conflict_support import (
    assert_conflict_recovery_and_trace_v2,
)
from tests.governance.test_commit_certificate_v2_operations import (
    _commit_certificate,
    _prepared_certificate,
)

from pheroos.governance.authority_store_v2 import (
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)
from pheroos.governance.commit_certificate_v2 import (
    VerifiedCommitCertificateStateV2,
    rehydrate_commit_certificate_state_v2,
)
from pheroos.governance.commit_decision_v2 import rehydrate_commit_decision_state_v2
from pheroos.governance.distributed_commit_v2 import (
    DistributedAdvanceRequestV2,
    DistributedCertificateStateV2,
    DistributedLaneStatusV2,
    DistributedMutationKindV2,
    DistributedProposalStateV2,
    DistributedQuorumWitnessV2,
    DistributedWitnessStateV2,
    VerifiedDistributedCertificateStateV2,
    VerifiedDistributedEpochStateV2,
    VerifiedDistributedProposalStateV2,
    VerifiedDistributedWitnessStateV2,
    advance_distributed_commit_v2,
    distributed_state_is_current_v2,
    open_distributed_authority_session_v2,
    prepare_distributed_certificate_v2,
    prepare_distributed_epoch_v2,
    prepare_distributed_proposal_v2,
    prepare_distributed_witness_v2,
    rehydrate_distributed_state_v2,
    require_current_distributed_state_v2,
    verified_distributed_commit_finality_input_v2,
)
from pheroos.governance.support_v2 import rehydrate_membership_state_v2
from pheroos.trace import InMemoryTraceStore, TraceEvent
from pheroos.trace.schema import trace_schema


class _WitnessVerifier:
    @staticmethod
    def attestation_ref(
        principal_ref: str, verification_root: str, signing_root: str
    ) -> str:
        material = b"\x00".join(
            item.encode("utf-8")
            for item in (principal_ref, verification_root, signing_root)
        )
        return "attestation:sha256:" + sha256(material).hexdigest()

    def verify_distributed_witness_v2(
        self,
        *,
        principal_ref: str,
        verification_root: str,
        signing_root: str,
        attestation_ref: str,
    ) -> bool:
        return hmac.compare_digest(
            attestation_ref,
            self.attestation_ref(principal_ref, verification_root, signing_root),
        )


@dataclass(frozen=True, slots=True)
class _Vertical:
    context: object
    inputs: object
    decision: object
    central_request: object
    central: VerifiedCommitCertificateStateV2
    epoch_request: DistributedAdvanceRequestV2
    epoch: VerifiedDistributedEpochStateV2
    proposal_request: DistributedAdvanceRequestV2
    proposal: VerifiedDistributedProposalStateV2
    witness_request: DistributedAdvanceRequestV2
    witness: VerifiedDistributedWitnessStateV2
    certificate_request: DistributedAdvanceRequestV2
    certificate: VerifiedDistributedCertificateStateV2
    verifier: _WitnessVerifier


def _commit_distributed(context, request, source):
    session = open_distributed_authority_session_v2(
        _capability(context, request.observed_epoch), request
    )
    return (
        advance_distributed_commit_v2(
            request,
            source=source,
            authority_session=session,
        ),
        session,
    )


def _signed_witness(proposal, membership, *, nonce: str) -> tuple[object, object]:
    cluster = membership.snapshot.clusters[0]
    member = cluster.principals[0]
    value = proposal.value
    verifier = _WitnessVerifier()
    witness = DistributedQuorumWitnessV2(
        domain_root=value.domain_root,
        scope_ref=value.scope_ref,
        protocol_ref=value.protocol_ref,
        run_ref=value.run_ref,
        target_ref=value.target_ref,
        epoch=value.epoch,
        proposal_digest=proposal.proposal_digest,
        semantic_value_root=value.semantic_value_root,
        candidate_ref=value.candidate_ref,
        claim_root=value.claim_root,
        membership_root=value.membership_root,
        verification_set_root=value.verification_set_root,
        principal_ref=member.principal_ref,
        verification_root=member.verification_root,
        cluster_ref=cluster.cluster_ref,
        failure_domain_ref=member.failure_domain_ref,
        witness_nonce=nonce,
        witnessed_at_step=10,
        expires_at_step=30,
        provenance_ref=f"urn:test:distributed:witness:{nonce}",
        source_trace_roots=(_root(f"trace:distributed:witness:{nonce}"),),
        attestation_ref="attestation:discovery",
    )
    signed = replace(
        witness,
        attestation_ref=verifier.attestation_ref(
            member.principal_ref,
            member.verification_root,
            witness.signing_root,
        ),
        witness_root="",
    )
    return signed, verifier


def _build_vertical(scope: str) -> _Vertical:
    context = distributed_context(scope)
    decision, inputs = sealed_distributed_decision(context, _root(f"claim:{scope}"))
    central_request, central_source = _prepared_certificate(
        context,
        decision,
        mutation_ref=f"mutation:{scope}:central",
    )
    central_attempt, _ = _commit_certificate(context, central_request, central_source)
    assert central_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    central = rehydrate_commit_certificate_state_v2(
        central_request,
        domain=context.domain,
        state_reader=context.store,
    )
    epoch_request, epoch_source = prepare_distributed_epoch_v2(
        membership_state=inputs.membership,
        manifest=context.manifest,
        transition_certificate_ref=f"certificate:{scope}:epoch",
        mutation_ref=f"mutation:{scope}:epoch",
        mutation_issuer_ref=context.grant.issuer_ref,
        current_step=10,
        provenance_ref=f"urn:test:{scope}:epoch",
        source_trace_roots=(_root(f"trace:{scope}:epoch"),),
    )
    epoch_attempt, _ = _commit_distributed(context, epoch_request, epoch_source)
    assert epoch_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    epoch = cast(
        VerifiedDistributedEpochStateV2,
        rehydrate_distributed_state_v2(
            epoch_request,
            domain=context.domain,
            state_reader=context.store,
        ),
    )
    proposal_request, proposal_source = prepare_distributed_proposal_v2(
        decision_state=decision,
        central_certificate_state=central,
        membership_state=inputs.membership,
        epoch_state=epoch,
        manifest=context.manifest,
        proposal_ref=f"proposal:{scope}:one",
        proposer_ref="principal:alpha",
        proposal_nonce="nonce:distributed:proposal:one",
        provenance_ref=f"urn:test:{scope}:proposal",
        source_trace_roots=(_root(f"trace:{scope}:proposal"),),
        mutation_ref=f"mutation:{scope}:proposal",
        mutation_issuer_ref=context.grant.issuer_ref,
        current_step=10,
    )
    proposal_attempt, _ = _commit_distributed(
        context, proposal_request, proposal_source
    )
    assert proposal_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    proposal = cast(
        VerifiedDistributedProposalStateV2,
        rehydrate_distributed_state_v2(
            proposal_request,
            domain=context.domain,
            state_reader=context.store,
        ),
    )
    proposal_record = cast(
        DistributedProposalStateV2, proposal.snapshot.state
    ).proposals[0]
    signed, verifier = _signed_witness(
        proposal_record, inputs.membership, nonce="nonce:distributed:witness:one"
    )
    witness_request, witness_source = prepare_distributed_witness_v2(
        decision_state=decision,
        central_certificate_state=central,
        membership_state=inputs.membership,
        epoch_state=epoch,
        proposal_state=proposal,
        manifest=context.manifest,
        witness=cast(DistributedQuorumWitnessV2, signed),
        trusted_verifier=cast(_WitnessVerifier, verifier),
        mutation_ref=f"mutation:{scope}:witness",
        mutation_issuer_ref=context.grant.issuer_ref,
        current_step=10,
    )
    witness_attempt, _ = _commit_distributed(context, witness_request, witness_source)
    assert witness_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    witness = cast(
        VerifiedDistributedWitnessStateV2,
        rehydrate_distributed_state_v2(
            witness_request,
            domain=context.domain,
            state_reader=context.store,
        ),
    )
    certificate_request, certificate_source = prepare_distributed_certificate_v2(
        decision_state=decision,
        central_certificate_state=central,
        membership_state=inputs.membership,
        epoch_state=epoch,
        proposal_state=proposal,
        witness_state=witness,
        manifest=context.manifest,
        trusted_verifier=cast(_WitnessVerifier, verifier),
        certificate_ref=f"certificate:{scope}:distributed",
        provenance_ref=f"urn:test:{scope}:certificate",
        mutation_ref=f"mutation:{scope}:certificate",
        mutation_issuer_ref=context.grant.issuer_ref,
        current_step=10,
    )
    certificate_attempt, _ = _commit_distributed(
        context, certificate_request, certificate_source
    )
    assert certificate_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    certificate = cast(
        VerifiedDistributedCertificateStateV2,
        rehydrate_distributed_state_v2(
            certificate_request,
            domain=context.domain,
            state_reader=context.store,
        ),
    )
    return _Vertical(
        context=context,
        inputs=inputs,
        decision=decision,
        central_request=central_request,
        central=central,
        epoch_request=epoch_request,
        epoch=epoch,
        proposal_request=proposal_request,
        proposal=proposal,
        witness_request=witness_request,
        witness=witness,
        certificate_request=certificate_request,
        certificate=certificate,
        verifier=cast(_WitnessVerifier, verifier),
    )


def _trace_payload(event: TraceEvent) -> dict[str, object]:
    return {
        "event_type": event.event_type,
        "protocol_id": event.protocol_id,
        "target": event.target,
        "reason": event.reason,
        "lineage": deepcopy(event.lineage),
    }


def test_real_store_vertical_semantic_retries_restart_and_finalization() -> None:
    vertical = _build_vertical("scope:distributed-v2:vertical")
    context = vertical.context
    inputs = vertical.inputs
    trace_store = InMemoryTraceStore()
    advanced_events: list[TraceEvent] = []
    for request in (
        vertical.epoch_request,
        vertical.proposal_request,
        vertical.witness_request,
        vertical.certificate_request,
    ):
        view = context.store.load_commit_view_v2(
            request.scope_ref, request.stream_ref, request.transition_id
        )
        assert view.committed_transition is not None
        event = view.committed_transition.batch.trace_batch.events[0]
        trace_store.append(event)
        advanced_events.append(event)
    conflict_events = assert_conflict_recovery_and_trace_v2(vertical)
    for event in conflict_events:
        trace_store.append(event)
    all_events = (*advanced_events, *conflict_events)
    assert {event.event_type for event in all_events} == {
        "distributed_epoch_advanced_v2",
        "distributed_proposal_advanced_v2",
        "distributed_witness_advanced_v2",
        "distributed_certificate_advanced_v2",
        "distributed_witness_conflict_v2",
        "distributed_certificate_conflict_v2",
    }
    validator = Draft202012Validator(trace_schema())
    for event in all_events:
        validator.validate(_trace_payload(event))
    for state, expected_type in (
        (vertical.epoch, VerifiedDistributedEpochStateV2),
        (vertical.proposal, VerifiedDistributedProposalStateV2),
        (vertical.witness, VerifiedDistributedWitnessStateV2),
        (vertical.certificate, VerifiedDistributedCertificateStateV2),
    ):
        assert type(state) is expected_type
        assert state.position is GovernanceCommitPositionV2.CURRENT
        assert distributed_state_is_current_v2(state)
        assert require_current_distributed_state_v2(state).revision == 1
        with pytest.raises(TypeError, match="not portable"):
            pickle.dumps(state)

    proposal_retry_request, proposal_retry_source = prepare_distributed_proposal_v2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=inputs.membership,
        epoch_state=vertical.epoch,
        manifest=context.manifest,
        proposal_ref="proposal:distributed:retry",
        proposer_ref="principal:alpha",
        proposal_nonce="nonce:distributed:proposal:retry",
        provenance_ref="urn:test:distributed:proposal:retry",
        source_trace_roots=(_root("trace:distributed:proposal:retry"),),
        mutation_ref="mutation:distributed:proposal:retry",
        mutation_issuer_ref=context.grant.issuer_ref,
        current_step=10,
        parent_state=vertical.proposal,
    )
    proposal_retry_attempt, _ = _commit_distributed(
        context, proposal_retry_request, proposal_retry_source
    )
    assert proposal_retry_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    proposal_retry = cast(
        VerifiedDistributedProposalStateV2,
        rehydrate_distributed_state_v2(
            proposal_retry_request,
            domain=context.domain,
            state_reader=context.store,
        ),
    )
    proposal_state = cast(DistributedProposalStateV2, proposal_retry.snapshot.state)
    assert proposal_retry.snapshot.mutation_kind is (
        DistributedMutationKindV2.PROPOSAL_SEMANTIC_RETRY
    )
    assert len(proposal_state.proposals) == 2
    assert len({item.proposal_digest for item in proposal_state.proposals}) == 2
    assert (
        len({item.value.semantic_value_root for item in proposal_state.proposals}) == 1
    )

    proposal_record = proposal_state.proposals[0]
    retry_signed, _ = _signed_witness(
        proposal_record,
        inputs.membership,
        nonce="nonce:distributed:witness:retry",
    )
    witness_retry_request, witness_retry_source = prepare_distributed_witness_v2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=inputs.membership,
        epoch_state=vertical.epoch,
        proposal_state=proposal_retry,
        manifest=context.manifest,
        witness=cast(DistributedQuorumWitnessV2, retry_signed),
        trusted_verifier=vertical.verifier,
        mutation_ref="mutation:distributed:witness:retry",
        mutation_issuer_ref=context.grant.issuer_ref,
        current_step=10,
        parent_state=vertical.witness,
    )
    witness_retry_attempt, _ = _commit_distributed(
        context, witness_retry_request, witness_retry_source
    )
    assert witness_retry_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    witness_retry = cast(
        VerifiedDistributedWitnessStateV2,
        rehydrate_distributed_state_v2(
            witness_retry_request,
            domain=context.domain,
            state_reader=context.store,
        ),
    )
    witness_state = cast(DistributedWitnessStateV2, witness_retry.snapshot.state)
    assert (
        witness_retry.snapshot.mutation_kind is DistributedMutationKindV2.WITNESS_RETRY
    )
    assert len(witness_state.witnesses) == 2
    assert not witness_state.frozen

    certificate_retry_request, certificate_retry_source = (
        prepare_distributed_certificate_v2(
            decision_state=vertical.decision,
            central_certificate_state=vertical.central,
            membership_state=inputs.membership,
            epoch_state=vertical.epoch,
            proposal_state=proposal_retry,
            witness_state=witness_retry,
            manifest=context.manifest,
            trusted_verifier=vertical.verifier,
            certificate_ref="certificate:distributed:retry",
            provenance_ref="urn:test:distributed:certificate:retry",
            mutation_ref="mutation:distributed:certificate:retry",
            mutation_issuer_ref=context.grant.issuer_ref,
            current_step=10,
            parent_state=vertical.certificate,
        )
    )
    certificate_retry_attempt, retry_session = _commit_distributed(
        context, certificate_retry_request, certificate_retry_source
    )
    assert (
        certificate_retry_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    )
    assert (
        advance_distributed_commit_v2(
            certificate_retry_request,
            source=certificate_retry_source,
            authority_session=retry_session,
        ).to_dict()
        == certificate_retry_attempt.to_dict()
    )
    certificate_retry = cast(
        VerifiedDistributedCertificateStateV2,
        rehydrate_distributed_state_v2(
            certificate_retry_request,
            domain=context.domain,
            state_reader=context.store,
        ),
    )
    certificate_state = cast(
        DistributedCertificateStateV2, certificate_retry.snapshot.state
    )
    assert certificate_retry.snapshot.mutation_kind is (
        DistributedMutationKindV2.CERTIFICATE_RETRY
    )
    assert certificate_retry.snapshot.status is DistributedLaneStatusV2.VERIFIED
    assert len(certificate_state.certificates) == 2

    finality = verified_distributed_commit_finality_input_v2(
        certificate_retry,
        proposal_state=proposal_retry,
        witness_state=witness_retry,
        epoch_state=vertical.epoch,
        sealed_decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=inputs.membership,
        manifest=context.manifest,
        current_step=10,
    )
    terminal = finalize_distributed_decision(
        context, vertical.decision, inputs, finality
    ).snapshot
    assert terminal.outcome is not None
    assert terminal.outcome.kind.value == "evidence_commit"
    assert terminal.outcome.delivery_eligible

    restarted = ReferenceGovernanceStateStoreConformanceAdapterV2().restart_store_v2(
        context.store
    )
    restarted_decision = rehydrate_commit_decision_state_v2(
        object.__getattribute__(vertical.decision, "_request"),
        domain=context.domain,
        state_reader=restarted,
    )
    restarted_central = rehydrate_commit_certificate_state_v2(
        vertical.central_request,
        domain=context.domain,
        state_reader=restarted,
    )
    restarted_membership = rehydrate_membership_state_v2(
        object.__getattribute__(inputs.membership, "_request"),
        domain=context.domain,
        state_reader=restarted,
    )
    restarted_states = tuple(
        rehydrate_distributed_state_v2(
            request,
            domain=context.domain,
            state_reader=restarted,
        )
        for request in (
            vertical.epoch_request,
            proposal_retry_request,
            witness_retry_request,
            certificate_retry_request,
        )
    )
    assert all(distributed_state_is_current_v2(state) for state in restarted_states)
    assert type(restarted_decision).__name__ == "VerifiedCommitDecisionStateV2"
    assert type(restarted_central) is VerifiedCommitCertificateStateV2
    assert restarted_membership.snapshot.membership_root == (
        inputs.membership.snapshot.membership_root
    )

    raw = json.loads(json.dumps(certificate_retry_request.to_dict()))
    assert (
        type(
            rehydrate_distributed_state_v2(
                raw,
                domain=context.domain,
                state_reader=context.store,
            )
        )
        is VerifiedDistributedCertificateStateV2
    )
    raw["request_root"] = _root("distributed:forged:request")
    with pytest.raises(Exception):
        rehydrate_distributed_state_v2(
            raw,
            domain=context.domain,
            state_reader=context.store,
        )
