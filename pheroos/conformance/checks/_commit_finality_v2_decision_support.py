"""Public-only Decision and policy fixtures for finality Conformance."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from pheroos.conformance.checks._commit_decision_v2_context_support import (
    CANDIDATE_REF,
    CommitDecisionV2ReadyContext,
    ready_context_v2,
)
from pheroos.conformance.checks._support_v2_manifest_support import (
    RUN_REF,
    TARGET_REF,
    root_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_session_v2 import (
    bind_governance_issuer_capability_v2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
)
from pheroos.governance.commit_decision_v2 import (
    CommitDecisionCandidateProposalV2,
    CommitDecisionCommandV2,
    CommitDecisionOutputProposalV2,
    CommitDecisionRequestV2,
    VerifiedCommitDecisionSourceV2,
    VerifiedCommitDecisionStateV2,
    advance_commit_decision_v2,
    open_commit_decision_authority_session_v2,
    prepare_commit_decision_initialize_v2,
    prepare_commit_decision_successor_v2,
    rehydrate_commit_decision_state_v2,
)
from pheroos.protocol import (
    CERTIFIED_COMMIT_PROFILE_VERSION,
    CertificatePolicy,
    CollectiveCommitPolicy,
    CommitAssurance,
    ScopedProtocolManifestV2,
)
from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_WIRE_VERSION,
)


@dataclass(frozen=True, slots=True)
class FinalityDecisionV2Vertical:
    context: CommitDecisionV2ReadyContext
    state: VerifiedCommitDecisionStateV2
    proposal: CommitDecisionCandidateProposalV2


def certified_decision_vertical_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    label: str,
    *,
    scope_ref: str | None = None,
) -> FinalityDecisionV2Vertical:
    return _decision_vertical_v2(
        adapter,
        label,
        profile=CERTIFIED_COMMIT_PROFILE_VERSION,
        assurance=CommitAssurance.CERTIFIED,
        manifest_transform=_certified_manifest_v2,
        grant_action_refs=(),
        scope_ref=scope_ref,
    )


def prepare_decision_successor_v2(
    vertical: FinalityDecisionV2Vertical,
    *,
    parent_state: VerifiedCommitDecisionStateV2 | None = None,
    mutation_ref: str,
    current_step: int,
    verified_finality_input: object | None = None,
) -> tuple[CommitDecisionRequestV2, VerifiedCommitDecisionSourceV2]:
    context = vertical.context
    return prepare_commit_decision_successor_v2(
        parent_state=vertical.state if parent_state is None else parent_state,
        manifest=context.manifest,
        profile=context.profile,
        mutation_ref=mutation_ref,
        current_step=current_step,
        mutation_issuer_ref=context.support_context.grant.issuer_ref,
        command=CommitDecisionCommandV2.EVALUATE,
        candidate_proposals=(vertical.proposal,),
        commit_replay_state=context.replay_state,
        risk_state=context.risk_state,
        membership_state=context.membership_state,
        support_state=context.support_state,
        evidence_state=context.evidence_state,
        stop_state=context.stop_state,
        permission_state=context.permission_state,
        verified_finality_input=verified_finality_input,
    )


def advance_decision_v2(
    vertical: FinalityDecisionV2Vertical,
    request: CommitDecisionRequestV2,
    source: object,
) -> GovernanceCommitAttemptV2:
    return _advance_context_v2(vertical.context, request, source)


def _advance_context_v2(
    context: CommitDecisionV2ReadyContext,
    request: CommitDecisionRequestV2,
    source: object,
) -> GovernanceCommitAttemptV2:
    support = context.support_context
    capability = bind_governance_issuer_capability_v2(
        support.store,
        support.domain,
        support.grant,
        RUN_REF,
        request.observed_epoch,
    )
    session = open_commit_decision_authority_session_v2(capability, request)
    return advance_commit_decision_v2(
        request,
        source=source,
        authority_session=session,
    )


def decision_state_v2(
    vertical: FinalityDecisionV2Vertical,
    request: CommitDecisionRequestV2,
) -> VerifiedCommitDecisionStateV2:
    return _state_context_v2(vertical.context, request)


def _state_context_v2(
    context: CommitDecisionV2ReadyContext,
    request: CommitDecisionRequestV2,
) -> VerifiedCommitDecisionStateV2:
    support = context.support_context
    return rehydrate_commit_decision_state_v2(
        request.to_dict(),
        domain=support.domain,
        state_reader=support.store,
    )


def commit_decision_successor_v2(
    vertical: FinalityDecisionV2Vertical,
    *,
    parent_state: VerifiedCommitDecisionStateV2 | None = None,
    mutation_ref: str,
    current_step: int,
    verified_finality_input: object | None = None,
) -> tuple[GovernanceCommitAttemptV2, VerifiedCommitDecisionStateV2]:
    request, source = prepare_decision_successor_v2(
        vertical,
        parent_state=parent_state,
        mutation_ref=mutation_ref,
        current_step=current_step,
        verified_finality_input=verified_finality_input,
    )
    attempt = advance_decision_v2(vertical, request, source)
    _require_committed(attempt, "successor")
    return attempt, decision_state_v2(vertical, request)


def _decision_vertical_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    label: str,
    *,
    profile: str,
    assurance: CommitAssurance,
    manifest_transform: Callable[[ScopedProtocolManifestV2], ScopedProtocolManifestV2],
    grant_action_refs: tuple[str, ...],
    scope_ref: str | None = None,
) -> FinalityDecisionV2Vertical:
    context = ready_context_v2(
        adapter,
        label,
        profile=profile,
        assurance=assurance,
        manifest_transform=manifest_transform,
        grant_action_refs=grant_action_refs,
        scope_ref=scope_ref,
        attestation_expires_at_step=100,
        gate_expires_at_step=100,
    )
    initialize, source = prepare_commit_decision_initialize_v2(
        domain=context.support_context.domain,
        manifest=context.manifest,
        profile=context.profile,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        observed_epoch=1,
        mutation_ref=f"mutation:finality:{label}:initialize",
        current_step=6,
        mutation_issuer_ref=context.support_context.grant.issuer_ref,
    )
    provisional = FinalityDecisionV2Vertical(
        context=context,
        state=_commit_initial_v2(context, initialize, source),
        proposal=CommitDecisionCandidateProposalV2(
            candidate_ref=CANDIDATE_REF,
            claim_root=context.claim_root,
            evidence=(),
        ),
    )
    state = provisional.state
    for step in (7, 8):
        _, state = commit_decision_successor_v2(
            replace(provisional, state=state),
            mutation_ref=f"mutation:finality:{label}:evaluate:{step}",
            current_step=step,
        )
    output = CommitDecisionOutputProposalV2(
        candidate_ref=CANDIDATE_REF,
        claim_root=context.claim_root,
        output_contract_root=root_v2(f"finality-output-contract:{label}"),
        payload={"answer": "provider-free finality conformance"},
    )
    seal, seal_source = prepare_commit_decision_successor_v2(
        parent_state=state,
        manifest=context.manifest,
        profile=context.profile,
        mutation_ref=f"mutation:finality:{label}:seal",
        current_step=8,
        mutation_issuer_ref=context.support_context.grant.issuer_ref,
        command=CommitDecisionCommandV2.SEAL,
        output_proposal=output,
        commit_replay_state=context.replay_state,
        risk_state=context.risk_state,
        membership_state=context.membership_state,
        support_state=context.support_state,
        evidence_state=context.evidence_state,
        stop_state=context.stop_state,
        permission_state=context.permission_state,
    )
    sealed = replace(provisional, state=state)
    _require_committed(advance_decision_v2(sealed, seal, seal_source), "seal")
    state = decision_state_v2(sealed, seal)
    vertical = replace(provisional, state=state)
    _, heartbeat = commit_decision_successor_v2(
        vertical,
        mutation_ref=f"mutation:finality:{label}:heartbeat:9",
        current_step=9,
    )
    return replace(vertical, state=heartbeat)


def _commit_initial_v2(
    context: CommitDecisionV2ReadyContext,
    request: CommitDecisionRequestV2,
    source: VerifiedCommitDecisionSourceV2,
) -> VerifiedCommitDecisionStateV2:
    attempt = _advance_context_v2(context, request, source)
    _require_committed(attempt, "initialize")
    return _state_context_v2(context, request)


def _certified_manifest_v2(
    manifest: ScopedProtocolManifestV2,
) -> ScopedProtocolManifestV2:
    return _manifest_with_assurance_v2(
        manifest,
        assurance=CommitAssurance.CERTIFIED,
        certificate_mode="portable",
    )


def _manifest_with_assurance_v2(
    manifest: ScopedProtocolManifestV2,
    *,
    assurance: CommitAssurance,
    certificate_mode: str,
) -> ScopedProtocolManifestV2:
    policy = manifest.collective_commit_policy
    if type(policy) is not CollectiveCommitPolicy:
        raise TypeError("finality conformance requires collective commit policy")
    bands = {
        name: replace(band, minimum_assurance=assurance.value)
        for name, band in policy.risk_bands.items()
    }
    updated = replace(
        policy,
        assurance=assurance.value,
        evidence_qualification=replace(
            policy.evidence_qualification,
            observation_ttl_steps=100,
        ),
        support_lease=replace(
            policy.support_lease,
            lease_ttl_steps=100,
        ),
        risk_bands=bands,
        certificate=CertificatePolicy(
            mode=certificate_mode,
            wire_version=COMMIT_WIRE_VERSION,
            canonicalization=COMMIT_CANONICAL_VERSION,
            hash_algorithm="sha256",
            issuer_attestation_required=True,
            independent_verification_required=True,
        ),
        distributed=None,
    )
    return replace(manifest, collective_commit_policy=updated)


def _require_committed(attempt: GovernanceCommitAttemptV2, label: str) -> None:
    if attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        detail = "" if attempt.failure is None else str(attempt.failure.to_dict())
        raise RuntimeError(f"Finality Decision {label} failed: {detail}")


__all__: tuple[str, ...] = ()
