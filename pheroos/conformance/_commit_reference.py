"""Deterministic authority-record fixtures used by the Commit JSON TCK.

This module deliberately contains *issuance plumbing only*.  It constructs a
portable manifest supplied by a vector and submits records to the public
Protocol/Governance ABI.  Commit scoring, window transitions, certificate
verification, distributed quorum logic, and output authorization remain owned
by their respective public governance functions.

Every authority namespace is derived from the vector id plus a named fixture
variant.  Re-running the same vector therefore exercises the ABI's exact-replay
semantics, while unrelated vectors cannot share a strong process-local head.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pheroos.governance.certificate import (
    EvidenceCommitCertificate,
    LocalCommitReceipt as LocalCommitReceipt,
)

from pheroos.governance.challenge import (
    ChallengeResult,
    VerifiedChallenge,
)

from pheroos.governance.commit import (
    CandidateCommitInput,
    CommitAssessment,
    CommitEvaluationContext,
)

from pheroos.governance.commit_state import (
    CommitReplayState,
    CommitWindowState,
    ReplayReceipt,
)

from pheroos.governance.distributed_commit import (
    DistributedCommitCertificate,
    DistributedCommitProposal,
    DistributedCommitState as DistributedCommitState,
    WitnessVerification,
)

from pheroos.governance.evidence_binding import (
    EvidenceBinding,
)

from pheroos.governance.observation import (
    CounterevidenceDisposition,
    CounterevidenceDispositionKind,
    ObservationPolarity,
    VerifiedObservation,
)

from pheroos.governance.permission import (
    ActionPermission,
)

from pheroos.governance.principal import (
    PrincipalVerification,
)

from pheroos.governance.risk import (
    CommitThresholdSnapshot as CommitThresholdSnapshot,
    RiskAssessment as RiskAssessment,
    RiskAssessmentChainState as RiskAssessmentChainState,
)

from pheroos.governance.stop_signal import (
    StopResolutionVerification,
)

from pheroos.governance.support_lease import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportLease,
    SupportLeaseReplayState,
)

from pheroos.protocol.commit_models import CommitAction, CommitAssurance
from pheroos.protocol.models import CapabilityManifest as CapabilityManifest

from pheroos.conformance._commit_reference_fixture.models import (
    REFERENCE_CHALLENGE_CATEGORY,
    REFERENCE_EPOCH,
    REFERENCE_FALLBACK,
    REFERENCE_LEADER,
    REFERENCE_OTHER,
    REFERENCE_PROTOCOL_ID,
    REFERENCE_TARGET,
    ReferenceDistributedCommit,
    ReferencePortableCommit,
    ReferenceScenario,
    ReferenceStableCommit,
    reference_fingerprint as _reference_fingerprint,
    reference_namespace as _reference_namespace,
)


def reference_fingerprint(label: str) -> str:
    return _reference_fingerprint(label)


def reference_namespace(vector_id: str, variant: str = "base") -> str:
    """Return a deterministic, JSON/text-safe strong-authority namespace."""

    return _reference_namespace(vector_id, variant)


from pheroos.conformance._commit_reference_fixture import (  # noqa: E402
    scenario as _scenario_handlers,
)

from pheroos.conformance._commit_reference_fixture import (  # noqa: E402
    evidence as _evidence_handlers,
)

from pheroos.conformance._commit_reference_fixture import (  # noqa: E402
    decision as _decision_handlers,
)

from pheroos.conformance._commit_reference_fixture import (  # noqa: E402
    window as _window_handlers,
)

from pheroos.conformance._commit_reference_fixture import (  # noqa: E402
    distributed as _distributed_handlers,
)

from pheroos.conformance._commit_reference_fixture import (  # noqa: E402
    certificate as _certificate_handlers,
)

from pheroos.conformance._commit_reference_fixture import (  # noqa: E402
    replay as _replay_handlers,
)


def build_reference_scenario(
    vector_id: str,
    manifest_payload: Mapping[str, object],
    *,
    profile: str,
    variant: str = "base",
    tie: bool = False,
    blocked: bool = False,
    shared_cluster: bool = False,
    leader_observation_count: int = 2,
    other_observation_count: int | None = None,
    minimum_membership_size: int = 3,
) -> ReferenceScenario:
    "Issue one complete deterministic Optimal Commit authority substrate."
    return _scenario_handlers.build_reference_scenario(
        vector_id,
        manifest_payload,
        profile=profile,
        variant=variant,
        tie=tie,
        blocked=blocked,
        shared_cluster=shared_cluster,
        leader_observation_count=leader_observation_count,
        other_observation_count=other_observation_count,
        minimum_membership_size=minimum_membership_size,
    )


def issue_reference_principal(
    namespace: str,
    *,
    index: int,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    cluster_id: str | None = None,
    failure_domain: str | None = None,
) -> PrincipalVerification:
    return _evidence_handlers.issue_reference_principal(
        namespace,
        index=index,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        cluster_id=cluster_id,
        failure_domain=failure_domain,
    )


def issue_reference_observation(
    namespace: str,
    *,
    index: int,
    principal: PrincipalVerification,
    candidate_id: str,
    claim_fingerprint: str,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    evidence_policy: object,
    polarity: ObservationPolarity = ObservationPolarity.SUPPORT,
    independence_group: str | None = None,
    source_domain: str | None = None,
    nonce: str | None = None,
    quality_ppm: int = 1_000_000,
    relevance_ppm: int = 1_000_000,
    materiality_ppm: int = 1_000_000,
    criticality_ppm: int = 0,
    expires_at_step: int | None = None,
) -> VerifiedObservation:
    return _evidence_handlers.issue_reference_observation(
        namespace,
        index=index,
        principal=principal,
        candidate_id=candidate_id,
        claim_fingerprint=claim_fingerprint,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        evidence_policy=evidence_policy,
        polarity=polarity,
        independence_group=independence_group,
        source_domain=source_domain,
        nonce=nonce,
        quality_ppm=quality_ppm,
        relevance_ppm=relevance_ppm,
        materiality_ppm=materiality_ppm,
        criticality_ppm=criticality_ppm,
        expires_at_step=expires_at_step,
    )


def issue_reference_challenge(
    namespace: str,
    *,
    index: int,
    principal: PrincipalVerification,
    candidate_id: str,
    claim_fingerprint: str,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    result: ChallengeResult = ChallengeResult.NO_COUNTEREVIDENCE,
    result_observations: Sequence[VerifiedObservation] = (),
) -> VerifiedChallenge:
    return _evidence_handlers.issue_reference_challenge(
        namespace,
        index=index,
        principal=principal,
        candidate_id=candidate_id,
        claim_fingerprint=claim_fingerprint,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        result=result,
        result_observations=result_observations,
    )


def issue_reference_disposition(
    namespace: str,
    counter_observation: VerifiedObservation,
    *,
    index: int,
    kind: CounterevidenceDispositionKind,
    rebuttal_observations: Sequence[VerifiedObservation] = (),
    resolution_ref: str = "",
) -> CounterevidenceDisposition:
    return _evidence_handlers.issue_reference_disposition(
        namespace,
        counter_observation,
        index=index,
        kind=kind,
        rebuttal_observations=rebuttal_observations,
        resolution_ref=resolution_ref,
    )


def issue_reference_binding(
    namespace: str,
    *,
    candidate_id: str,
    claim_fingerprint: str,
    observations: Sequence[VerifiedObservation],
    counter_observations: Sequence[VerifiedObservation],
    dispositions: Sequence[CounterevidenceDisposition],
    challenges: Sequence[VerifiedChallenge],
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    current_step: int,
    binding_variant: str = "",
) -> EvidenceBinding:
    return _evidence_handlers.issue_reference_binding(
        namespace,
        candidate_id=candidate_id,
        claim_fingerprint=claim_fingerprint,
        observations=observations,
        counter_observations=counter_observations,
        dispositions=dispositions,
        challenges=challenges,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        current_step=current_step,
        binding_variant=binding_variant,
    )


def issue_reference_lease(
    namespace: str,
    *,
    index: int,
    principal: PrincipalVerification,
    observation: VerifiedObservation,
    candidate_id: str,
    claim_fingerprint: str,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    policy: object,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_state: EligibleMembershipEpochState,
    replay_state: SupportLeaseReplayState,
    prior_leases: Sequence[SupportLease],
    issuer_id: str | None = None,
    current_step: int = 4,
) -> tuple[SupportLease, SupportLeaseReplayState]:
    return _decision_handlers.issue_reference_lease(
        namespace,
        index=index,
        principal=principal,
        observation=observation,
        candidate_id=candidate_id,
        claim_fingerprint=claim_fingerprint,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        policy=policy,
        membership_snapshot=membership_snapshot,
        membership_state=membership_state,
        replay_state=replay_state,
        prior_leases=prior_leases,
        issuer_id=issuer_id,
        current_step=current_step,
    )


def issue_reference_action_gates(
    namespace: str,
    *,
    context: CommitEvaluationContext,
    action: CommitAction,
    blocked: bool,
    current_step: int,
    expires_at_step: int,
    suffix: str,
    target: str | None = None,
) -> tuple[StopResolutionVerification, ActionPermission]:
    return _decision_handlers.issue_reference_action_gates(
        namespace,
        context=context,
        action=action,
        blocked=blocked,
        current_step=current_step,
        expires_at_step=expires_at_step,
        suffix=suffix,
        target=target,
    )


def assess_reference_scenario(
    scenario: ReferenceScenario,
    *,
    step: int,
    suffix: str,
    candidate_inputs: Sequence[CandidateCommitInput] | None = None,
    leases: Sequence[SupportLease] | None = None,
    revocations: Sequence[object] = (),
    stop_resolution: StopResolutionVerification | None = None,
    permission: ActionPermission | None = None,
    context: CommitEvaluationContext | None = None,
    replay_state: CommitReplayState | None = None,
    support_replay_state: SupportLeaseReplayState | None = None,
) -> CommitAssessment:
    return _decision_handlers.assess_reference_scenario(
        scenario,
        step=step,
        suffix=suffix,
        candidate_inputs=candidate_inputs,
        leases=leases,
        revocations=revocations,
        stop_resolution=stop_resolution,
        permission=permission,
        context=context,
        replay_state=replay_state,
        support_replay_state=support_replay_state,
    )


def initialize_reference_window(
    scenario: ReferenceScenario,
) -> CommitWindowState:
    "Return the immutable historical initial window for one scenario."
    return _window_handlers.initialize_reference_window(
        scenario,
    )


def rotate_reference_context(
    scenario: ReferenceScenario,
    *,
    candidate_inputs: Sequence[CandidateCommitInput],
    leases: Sequence[SupportLease],
    current_step: int,
    suffix: str,
    support_replay_state: SupportLeaseReplayState | None = None,
) -> tuple[
    CommitEvaluationContext,
    CommitReplayState,
    SupportLeaseReplayState,
    StopResolutionVerification,
    ActionPermission,
]:
    "Append scoped authority inputs and issue a new immutable context head."
    return _window_handlers.rotate_reference_context(
        scenario,
        candidate_inputs=candidate_inputs,
        leases=leases,
        current_step=current_step,
        suffix=suffix,
        support_replay_state=support_replay_state,
    )


def build_reference_stable_commit(
    scenario: ReferenceScenario,
    *,
    variant: str = "stable",
) -> ReferenceStableCommit:
    return _window_handlers.build_reference_stable_commit(
        scenario,
        variant=variant,
    )


def build_reference_portable_commit(
    stable: ReferenceStableCommit,
    *,
    variant: str = "portable",
) -> ReferencePortableCommit:
    return _distributed_handlers.build_reference_portable_commit(
        stable,
        variant=variant,
    )


def build_reference_distributed_commit(
    portable: ReferencePortableCommit,
    *,
    witness_count: int | None = None,
    variant: str = "distributed",
) -> ReferenceDistributedCommit:
    return _distributed_handlers.build_reference_distributed_commit(
        portable,
        witness_count=witness_count,
        variant=variant,
    )


def issue_reference_witness(
    scenario: ReferenceScenario,
    proposal: DistributedCommitProposal,
    principal: PrincipalVerification,
    *,
    index: int,
    variant: str,
    trusted_witness_attestations: dict[str, str],
) -> WitnessVerification:
    return _distributed_handlers.issue_reference_witness(
        scenario,
        proposal,
        principal,
        index=index,
        variant=variant,
        trusted_witness_attestations=trusted_witness_attestations,
    )


def issue_reference_distributed_certificate(
    bundle: ReferenceDistributedCommit,
    *,
    witness_count: int,
    variant: str,
) -> DistributedCommitCertificate:
    return _certificate_handlers.issue_reference_distributed_certificate(
        bundle,
        witness_count=witness_count,
        variant=variant,
    )


def issue_reference_semantic_conflict_certificate(
    bundle: ReferenceDistributedCommit,
    *,
    field_name: str,
    field_value: str,
    variant: str,
) -> tuple[
    DistributedCommitProposal,
    EvidenceCommitCertificate,
    dict[str, str],
    dict[str, str],
    DistributedCommitCertificate,
]:
    "Build a valid portable peer proof for a different commit value."
    return _certificate_handlers.issue_reference_semantic_conflict_certificate(
        bundle,
        field_name=field_name,
        field_value=field_value,
        variant=variant,
    )


def replay_state_with_receipts(
    scenario: ReferenceScenario,
    receipts: Sequence[ReplayReceipt],
    *,
    step: int,
) -> CommitReplayState:
    return _replay_handlers.replay_state_with_receipts(
        scenario,
        receipts,
        step=step,
    )


__all__ = [
    "REFERENCE_CHALLENGE_CATEGORY",
    "REFERENCE_EPOCH",
    "REFERENCE_FALLBACK",
    "REFERENCE_LEADER",
    "REFERENCE_OTHER",
    "REFERENCE_PROTOCOL_ID",
    "REFERENCE_TARGET",
    "ReferenceDistributedCommit",
    "ReferencePortableCommit",
    "ReferenceScenario",
    "ReferenceStableCommit",
    "assess_reference_scenario",
    "build_reference_distributed_commit",
    "build_reference_portable_commit",
    "build_reference_scenario",
    "build_reference_stable_commit",
    "issue_reference_action_gates",
    "issue_reference_binding",
    "issue_reference_challenge",
    "issue_reference_disposition",
    "issue_reference_distributed_certificate",
    "issue_reference_semantic_conflict_certificate",
    "initialize_reference_window",
    "issue_reference_lease",
    "issue_reference_observation",
    "issue_reference_principal",
    "issue_reference_witness",
    "reference_fingerprint",
    "reference_namespace",
    "replay_state_with_receipts",
    "rotate_reference_context",
]
