"""Public-only durable Distributed Commit v2 verified and conflict verticals."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import hmac
from typing import cast

from pheroos.conformance.checks._distributed_v2_context_support import (
    CANDIDATE_REF,
    PROFILE,
    DistributedV2Context,
    DistributedV2Identity,
    capability_v2,
    context_v2,
    identity_v2,
)
from pheroos.conformance.checks._distributed_v2_decision_support import (
    decision_and_central_v2,
)
from pheroos.conformance.checks._distributed_v2_input_support import (
    DistributedV2DecisionInputs,
    decision_inputs_v2,
)
from pheroos.conformance.checks._support_v2_manifest_support import root_v2
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitDispositionV2,
)
from pheroos.governance.commit_certificate_v2 import (
    VerifiedCommitCertificateStateV2,
)
from pheroos.governance.commit_decision_v2 import VerifiedCommitDecisionStateV2
from pheroos.governance.commit_decision_v2 import (
    CommitDecisionCandidateProposalV2,
    CommitDecisionCommandV2,
    advance_commit_decision_v2,
    open_commit_decision_authority_session_v2,
    prepare_commit_decision_successor_v2,
    rehydrate_commit_decision_state_v2,
)
from pheroos.governance.commit_finality_v2 import VerifiedCommitFinalityInputV2
from pheroos.governance.distributed_commit_v2 import (
    DistributedAdvanceRequestV2,
    DistributedCommitProposalV2,
    DistributedProposalStateV2,
    DistributedQuorumWitnessV2,
    DistributedWitnessConflictObservationV2,
    VerifiedDistributedCertificateStateV2,
    VerifiedDistributedEpochStateV2,
    VerifiedDistributedProposalStateV2,
    VerifiedDistributedWitnessStateV2,
    advance_distributed_commit_v2,
    open_distributed_authority_session_v2,
    prepare_distributed_certificate_v2,
    prepare_distributed_epoch_v2,
    prepare_distributed_proposal_v2,
    prepare_distributed_witness_conflict_observation_v2,
    prepare_distributed_witness_v2,
    rehydrate_distributed_state_v2,
    verified_distributed_commit_finality_input_v2,
)


@dataclass(frozen=True, slots=True)
class DistributedV2Vertical:
    context: DistributedV2Context
    identity: DistributedV2Identity
    inputs: DistributedV2DecisionInputs
    claim_root: str
    decision: VerifiedCommitDecisionStateV2
    central: VerifiedCommitCertificateStateV2
    epoch_request: DistributedAdvanceRequestV2
    epoch: VerifiedDistributedEpochStateV2
    proposal_request: DistributedAdvanceRequestV2
    proposal: VerifiedDistributedProposalStateV2
    witness_request: DistributedAdvanceRequestV2
    witness: VerifiedDistributedWitnessStateV2
    certificate_request: DistributedAdvanceRequestV2
    certificate: VerifiedDistributedCertificateStateV2
    verifier: DistributedWitnessVerifierV2


@dataclass(frozen=True, slots=True)
class DistributedV2ConflictVertical:
    baseline: DistributedV2Vertical
    observation: DistributedWitnessConflictObservationV2
    witness_request: DistributedAdvanceRequestV2
    witness_source: object
    witness: VerifiedDistributedWitnessStateV2


class DistributedWitnessVerifierV2:
    @staticmethod
    def attestation_ref(
        principal_ref: str,
        verification_root: str,
        signing_root: str,
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


def build_verified_distributed_vertical_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    label: str,
) -> DistributedV2Vertical:
    context = context_v2(adapter, label)
    identity = identity_v2(context, label)
    claim_root = root_v2(f"claim:distributed-v2:{label}")
    inputs = decision_inputs_v2(
        context,
        identity,
        label=label,
        claim_root=claim_root,
    )
    decision = decision_and_central_v2(
        context,
        inputs,
        label=label,
        claim_root=claim_root,
    )
    epoch_request, epoch_source = prepare_distributed_epoch_v2(
        membership_state=identity.membership,
        manifest=context.manifest,
        transition_certificate_ref=f"certificate:distributed:epoch:{label}",
        mutation_ref=f"mutation:distributed:epoch:{label}",
        mutation_issuer_ref=context.grant.issuer_ref,
        current_step=10,
        provenance_ref=f"urn:pheroos:conformance:distributed:epoch:{label}",
        source_trace_roots=(root_v2(f"distributed:epoch:trace:{label}"),),
    )
    _advance_v2(context, epoch_request, epoch_source)
    epoch = cast(
        VerifiedDistributedEpochStateV2,
        _rehydrate_v2(context, epoch_request),
    )
    proposal_request, proposal_source = prepare_distributed_proposal_v2(
        decision_state=decision.state,
        central_certificate_state=decision.central,
        membership_state=identity.membership,
        epoch_state=epoch,
        manifest=context.manifest,
        proposal_ref=f"proposal:distributed:{label}:baseline",
        proposer_ref="principal:alpha",
        proposal_nonce=f"nonce:distributed:{label}:proposal:baseline",
        provenance_ref=f"urn:pheroos:conformance:distributed:proposal:{label}",
        source_trace_roots=(root_v2(f"distributed:proposal:trace:{label}"),),
        mutation_ref=f"mutation:distributed:proposal:{label}:baseline",
        mutation_issuer_ref=context.grant.issuer_ref,
        current_step=10,
    )
    _advance_v2(context, proposal_request, proposal_source)
    proposal = cast(
        VerifiedDistributedProposalStateV2,
        _rehydrate_v2(context, proposal_request),
    )
    record = cast(DistributedProposalStateV2, proposal.snapshot.state).proposals[0]
    witness, verifier = _signed_witness_v2(
        record,
        identity,
        nonce=f"nonce:distributed:{label}:witness:baseline",
        current_step=10,
    )
    witness_request, witness_source = prepare_distributed_witness_v2(
        decision_state=decision.state,
        central_certificate_state=decision.central,
        membership_state=identity.membership,
        epoch_state=epoch,
        proposal_state=proposal,
        manifest=context.manifest,
        witness=witness,
        trusted_verifier=verifier,
        mutation_ref=f"mutation:distributed:witness:{label}:baseline",
        mutation_issuer_ref=context.grant.issuer_ref,
        current_step=10,
    )
    _advance_v2(context, witness_request, witness_source)
    witness_state = cast(
        VerifiedDistributedWitnessStateV2,
        _rehydrate_v2(context, witness_request),
    )
    certificate_request, certificate_source = prepare_distributed_certificate_v2(
        decision_state=decision.state,
        central_certificate_state=decision.central,
        membership_state=identity.membership,
        epoch_state=epoch,
        proposal_state=proposal,
        witness_state=witness_state,
        manifest=context.manifest,
        trusted_verifier=verifier,
        certificate_ref=f"certificate:distributed:{label}:verified",
        provenance_ref=f"urn:pheroos:conformance:distributed:certificate:{label}",
        mutation_ref=f"mutation:distributed:certificate:{label}:verified",
        mutation_issuer_ref=context.grant.issuer_ref,
        current_step=10,
    )
    _advance_v2(context, certificate_request, certificate_source)
    certificate = cast(
        VerifiedDistributedCertificateStateV2,
        _rehydrate_v2(context, certificate_request),
    )
    return DistributedV2Vertical(
        context=context,
        identity=identity,
        inputs=inputs,
        claim_root=claim_root,
        decision=decision.state,
        central=decision.central,
        epoch_request=epoch_request,
        epoch=epoch,
        proposal_request=proposal_request,
        proposal=proposal,
        witness_request=witness_request,
        witness=witness_state,
        certificate_request=certificate_request,
        certificate=certificate,
        verifier=verifier,
    )


def verified_finality_v2(
    vertical: DistributedV2Vertical,
) -> VerifiedCommitFinalityInputV2:
    return verified_distributed_commit_finality_input_v2(
        vertical.certificate,
        proposal_state=vertical.proposal,
        witness_state=vertical.witness,
        epoch_state=vertical.epoch,
        sealed_decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        manifest=vertical.context.manifest,
        current_step=10,
    )


def external_witness_conflict_observation_v2(
    vertical: DistributedV2Vertical,
    label: str,
) -> DistributedWitnessConflictObservationV2:
    """Build portable evidence; this object deliberately carries no authority."""

    proposal_state = cast(DistributedProposalStateV2, vertical.proposal.snapshot.state)
    current = proposal_state.proposals[0]
    alternate_value = replace(
        current.value,
        decision_current_revision=current.value.decision_current_revision + 1,
        decision_current_transition_id=f"transition:external-byzantine:{label}",
        decision_current_snapshot_root=root_v2(f"external:snapshot:{label}"),
        decision_current_head_root=root_v2(f"external:head:{label}"),
        decision_current_receipt_root=root_v2(f"external:receipt:{label}"),
        decision_current_inclusion_root=root_v2(f"external:inclusion:{label}"),
        semantic_value_root="",
    )
    alternate = DistributedCommitProposalV2(
        proposal_ref=f"proposal:distributed:external-conflict:{label}",
        proposer_ref="principal:external-observer",
        proposal_nonce=f"nonce:distributed:external-conflict:{label}",
        proposed_at_step=10,
        provenance_ref=f"urn:pheroos:conformance:external-proposal:{label}",
        source_trace_roots=(root_v2(f"external:proposal:trace:{label}"),),
        value=alternate_value,
    )
    witness, _ = _signed_witness_v2(
        alternate,
        vertical.identity,
        nonce=f"nonce:distributed:external-witness:{label}",
        current_step=10,
    )
    return DistributedWitnessConflictObservationV2(
        observation_ref=f"observation:distributed:witness-conflict:{label}",
        proposal=alternate,
        witness=witness,
        observed_at_step=10,
        provenance_ref=f"urn:pheroos:conformance:external-observation:{label}",
        source_trace_roots=(root_v2(f"external:observation:trace:{label}"),),
    )


def freeze_external_witness_conflict_v2(
    vertical: DistributedV2Vertical,
    label: str,
) -> DistributedV2ConflictVertical:
    """Commit one fully verified, freeze-only external conflict observation."""

    observation = external_witness_conflict_observation_v2(vertical, label)
    request, source = prepare_distributed_witness_conflict_observation_v2(
        decision_state=vertical.decision,
        central_certificate_state=vertical.central,
        membership_state=vertical.identity.membership,
        epoch_state=vertical.epoch,
        proposal_state=vertical.proposal,
        parent_state=vertical.witness,
        manifest=vertical.context.manifest,
        observation=observation,
        trusted_verifier=vertical.verifier,
        mutation_ref=f"mutation:distributed:witness-conflict:{label}",
        mutation_issuer_ref=vertical.context.grant.issuer_ref,
        current_step=10,
    )
    _advance_v2(vertical.context, request, source)
    frozen = cast(
        VerifiedDistributedWitnessStateV2,
        _rehydrate_v2(vertical.context, request),
    )
    return DistributedV2ConflictVertical(vertical, observation, request, source, frozen)


def conflict_finality_v2(
    conflict: DistributedV2ConflictVertical,
) -> VerifiedCommitFinalityInputV2:
    baseline = conflict.baseline
    return verified_distributed_commit_finality_input_v2(
        baseline.certificate,
        proposal_state=baseline.proposal,
        witness_state=conflict.witness,
        epoch_state=baseline.epoch,
        sealed_decision_state=baseline.decision,
        central_certificate_state=baseline.central,
        membership_state=baseline.identity.membership,
        manifest=baseline.context.manifest,
        current_step=10,
    )


def advance_conflict_decision_v2(
    conflict: DistributedV2ConflictVertical,
    label: str,
) -> VerifiedCommitDecisionStateV2:
    baseline = conflict.baseline
    proposal = CommitDecisionCandidateProposalV2(
        candidate_ref=CANDIDATE_REF,
        claim_root=baseline.claim_root,
        evidence=(),
    )
    request, source = prepare_commit_decision_successor_v2(
        parent_state=baseline.decision,
        manifest=baseline.context.manifest,
        profile=PROFILE,
        mutation_ref=f"mutation:distributed:conflict-decision:{label}",
        current_step=10,
        mutation_issuer_ref=baseline.context.grant.issuer_ref,
        command=CommitDecisionCommandV2.EVALUATE,
        candidate_proposals=(proposal,),
        commit_replay_state=baseline.inputs.replay,
        risk_state=baseline.inputs.risk,
        membership_state=baseline.inputs.membership,
        support_state=baseline.inputs.support,
        evidence_state=baseline.inputs.evidence,
        stop_state=baseline.inputs.stop,
        permission_state=baseline.inputs.permission,
        verified_finality_input=conflict_finality_v2(conflict),
    )
    attempt = advance_commit_decision_v2(
        request,
        source=source,
        authority_session=open_commit_decision_authority_session_v2(
            capability_v2(baseline.context, request.observed_epoch), request
        ),
    )
    if attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise RuntimeError("Distributed conflict Decision successor failed")
    return rehydrate_commit_decision_state_v2(
        request.to_dict(),
        domain=baseline.context.domain,
        state_reader=baseline.context.store,
    )


def _signed_witness_v2(
    proposal: object,
    identity: DistributedV2Identity,
    *,
    nonce: str,
    current_step: int,
) -> tuple[DistributedQuorumWitnessV2, DistributedWitnessVerifierV2]:
    value = object.__getattribute__(proposal, "value")
    digest = object.__getattribute__(proposal, "proposal_digest")
    cluster = identity.membership.snapshot.clusters[0]
    member = cluster.principals[0]
    verifier = DistributedWitnessVerifierV2()
    witness = DistributedQuorumWitnessV2(
        domain_root=value.domain_root,
        scope_ref=value.scope_ref,
        protocol_ref=value.protocol_ref,
        run_ref=value.run_ref,
        target_ref=value.target_ref,
        epoch=value.epoch,
        proposal_digest=digest,
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
        witnessed_at_step=current_step,
        expires_at_step=current_step + 20,
        provenance_ref=f"urn:pheroos:conformance:{nonce}",
        source_trace_roots=(root_v2(f"trace:{nonce}"),),
        attestation_ref="attestation:discovery",
    )
    return (
        replace(
            witness,
            attestation_ref=verifier.attestation_ref(
                member.principal_ref,
                member.verification_root,
                witness.signing_root,
            ),
            witness_root="",
        ),
        verifier,
    )


def _advance_v2(
    context: DistributedV2Context,
    request: DistributedAdvanceRequestV2,
    source: object,
) -> None:
    attempt = advance_distributed_commit_v2(
        request,
        source=source,
        authority_session=open_distributed_authority_session_v2(
            capability_v2(context, request.observed_epoch), request
        ),
    )
    if attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        detail = "" if attempt.failure is None else str(attempt.failure.to_dict())
        raise RuntimeError(f"Distributed Commit v2 lane setup failed: {detail}")


def _rehydrate_v2(
    context: DistributedV2Context,
    request: DistributedAdvanceRequestV2,
) -> object:
    return rehydrate_distributed_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )


__all__: tuple[str, ...] = ()
