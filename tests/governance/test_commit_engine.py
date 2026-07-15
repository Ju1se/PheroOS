from __future__ import annotations

from dataclasses import dataclass, replace
from concurrent.futures import ThreadPoolExecutor
import gc
import hashlib
import inspect
from itertools import count
import weakref

import pytest

from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.challenge import (
    ChallengeAttestation,
    ChallengeResult,
    verify_challenge_attestation,
)
from pheroos.governance.commit import (
    CandidateCommitInput,
    CommitAssessmentStatus,
    CommitEvaluationError,
    CommitEvaluationFailureKind,
    CommitReasonCode,
    assess_optimal_commit,
    build_commit_replay_receipts,
    candidate_commit_metrics_fingerprint,
    commit_assessment_fingerprint,
    commit_assessment_is_authoritative,
    commit_evaluation_context_fingerprint,
    commit_evaluation_context_is_authoritative,
    issue_commit_evaluation_context,
    rebuild_commit_assessment_roots,
)
from pheroos.governance.commit_state import (
    ReplayNamespace,
    ReplayReceipt,
    initialize_commit_replay_state,
    record_commit_replay_receipts,
)
from pheroos.governance.evidence_binding import bind_evidence
from pheroos.governance.observation import (
    CounterevidenceDispositionKind,
    ObservationAttestation,
    ObservationPolarity,
    counterevidence_disposition_fingerprint,
    issue_counterevidence_disposition,
    verified_observation_fingerprint,
    verify_observation_attestation,
)
from pheroos.governance.permission import issue_action_permission
from pheroos.governance.principal import (
    PrincipalAttestation,
    PrincipalVerification,
    verify_principal_attestation,
)
from pheroos.governance.risk import (
    RiskBand,
    initialize_risk_assessment_chain,
    issue_commit_threshold_snapshot,
    issue_risk_assessment,
)
from pheroos.governance.stop_signal import (
    StopResolution,
    verify_stop_resolution,
)
from pheroos.governance.support_lease import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportLease,
    SupportLeaseProposal,
    SupportLeaseReplayState,
    initialize_support_lease_replay_state,
    issue_eligible_principal_snapshot,
    issue_support_lease,
    revoke_support_lease,
    support_lease_revocation_fingerprint,
)
from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_MODEL,
    COMMIT_POLICY_VERSION,
    COMMIT_WIRE_VERSION,
    REQUIRED_COMMIT_RESET_RULES,
    CertificatePolicy,
    CollectiveCommitPolicy,
    CommitAction,
    CommitAssurance,
    CommitWindowPolicy,
    EvidenceQualificationPolicy,
    RiskBandPolicy,
    SupportLeasePolicy,
    TerminalOutcomePolicy,
)
from pheroos.protocol.commit_wire import (
    commit_manifest_fingerprint,
    commit_policy_fingerprint,
)
from pheroos.protocol.models import (
    CandidateSpec,
    CapabilityManifest,
    CollectiveDecisionPolicy,
    ProtocolManifest,
    QuorumPolicy,
    TargetSpec,
)


PROFILE = "pheroos-commit-integrity-v1"
ASSURANCE = CommitAssurance.EVIDENCE_BOUND
TARGET = "decision:optimal"
PROTOCOL_ID = "protocol:optimal-commit"
EPOCH = 3
CHALLENGE_CATEGORY = "independent_replication"
_SEQUENCE = count(1)


def _fingerprint(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def _band(
    *,
    minimum_positive: int,
    minimum_margin: int,
    minimum_support_clusters: int = 1,
    minimum_support_ratio_ppm: int = 500_000,
    minimum_source_diversity: int = 1,
    required_challenges: tuple[str, ...] = (CHALLENGE_CATEGORY,),
    minimum_assurance: str = "evidence_bound",
) -> RiskBandPolicy:
    return RiskBandPolicy(
        minimum_positive_evidence=minimum_positive,
        maximum_counterevidence=0,
        maximum_counterevidence_ratio_ppm=0,
        minimum_support_clusters=minimum_support_clusters,
        minimum_support_ratio_ppm=minimum_support_ratio_ppm,
        minimum_source_diversity=minimum_source_diversity,
        minimum_margin=minimum_margin,
        stability_steps=2,
        required_challenge_categories=list(required_challenges),
        minimum_assurance=minimum_assurance,
        publishable_outcomes=["evidence_commit"],
        executable_outcomes=[],
    )


def _policy(
    *,
    risk_minimum_positive: int = 1_000_000,
    minimum_margin: int = 500_000,
    risk_minimum_support_clusters: int = 1,
    risk_minimum_support_ratio_ppm: int = 500_000,
    risk_minimum_source_diversity: int = 1,
    risk_required_challenges: tuple[str, ...] = (CHALLENGE_CATEGORY,),
    risk_minimum_assurance: str = "evidence_bound",
) -> CollectiveCommitPolicy:
    return CollectiveCommitPolicy(
        policy_version=COMMIT_POLICY_VERSION,
        model=COMMIT_MODEL,
        assurance="evidence_bound",
        target=TARGET,
        evidence_qualification=EvidenceQualificationPolicy(
            numeric_scale=1_000_000,
            minimum_quality_ppm=500_000,
            minimum_relevance_ppm=500_000,
            positive_group_cap=1_000_000,
            counter_group_cap=1_000_000,
            counter_weight_ppm=1_000_000,
            minimum_positive_evidence=1_000_000,
            maximum_counterevidence=0,
            maximum_counterevidence_ratio_ppm=0,
            domain_contribution_floor=500_000,
            minimum_source_diversity=1,
            required_challenge_categories=[CHALLENGE_CATEGORY],
            observation_ttl_steps=20,
            require_provenance=True,
            require_trace=True,
        ),
        support_lease=SupportLeasePolicy(
            minimum_support_clusters=1,
            support_ratio_ppm=500_000,
            lease_ttl_steps=5,
            membership_mode="verified_snapshot_v1",
            switch_mode="revoke_then_issue_v1",
            equivocation_mode="exclude_conflicts_v1",
            evidence_reference_required=True,
            cluster_verification_required=True,
        ),
        risk_bands={
            name: _band(
                minimum_positive=risk_minimum_positive,
                minimum_margin=minimum_margin,
                minimum_support_clusters=risk_minimum_support_clusters,
                minimum_support_ratio_ppm=risk_minimum_support_ratio_ppm,
                minimum_source_diversity=risk_minimum_source_diversity,
                required_challenges=risk_required_challenges,
                minimum_assurance=risk_minimum_assurance,
            )
            for name in ("LOW", "MODERATE", "HIGH", "CRITICAL")
        },
        commit_window=CommitWindowPolicy(
            minimum_stability_steps=2,
            deliberation_deadline_steps=8,
            maximum_leader_resets=2,
            maximum_epoch_restarts=1,
            run_deadline_steps=12,
            reset_rules=list(REQUIRED_COMMIT_RESET_RULES),
        ),
        terminal_outcome=TerminalOutcomePolicy(
            safe_fallback_candidate="candidate:fallback",
            deadline_outcome="safe_fallback",
            policy_incomplete_outcome="invalid",
            finality_unavailable_outcome="finality_unavailable",
            deliverable_outcomes=[
                "evidence_commit",
                "safe_fallback",
                "advisory",
                "blocked",
                "invalid",
                "finality_unavailable",
                "safety_violation",
            ],
            publishable_outcomes=["evidence_commit", "safe_fallback"],
            executable_outcomes=[],
        ),
        certificate=CertificatePolicy(
            mode="local_receipt",
            wire_version=COMMIT_WIRE_VERSION,
            canonicalization=COMMIT_CANONICAL_VERSION,
            hash_algorithm="sha256",
            issuer_attestation_required=False,
            independent_verification_required=False,
        ),
        distributed=None,
    )


def _manifest(
    policy: CollectiveCommitPolicy,
    *,
    leader_id: str,
    other_id: str,
) -> CapabilityManifest:
    return CapabilityManifest(
        id="capability:optimal-commit",
        name="Optimal Commit Test",
        version="1.0.0",
        protocol=ProtocolManifest(
            protocol_version="1.0.0",
            id=PROTOCOL_ID,
            targets=[TargetSpec(id=TARGET)],
            candidates=[
                CandidateSpec(id=leader_id, target=TARGET),
                CandidateSpec(id=other_id, target=TARGET),
                CandidateSpec(
                    id="candidate:fallback",
                    target=TARGET,
                    safe_fallback=True,
                ),
            ],
            quorum_policy=QuorumPolicy(
                target=TARGET,
                fallback_candidate="candidate:fallback",
            ),
            collective_commit_policy=policy,
        ),
    )


def _principal(
    principal_id: str,
    cluster_id: str,
    *,
    index: int,
    manifest_root: str,
    policy_root: str,
    run_id: str,
) -> PrincipalVerification:
    return verify_principal_attestation(
        PrincipalAttestation(
            principal_id=principal_id,
            attestation_ref=f"opaque:principal:{run_id}:{index}",
            method="identity-verifier-v1",
            issuer_id="issuer:identity",
            issued_at_step=0,
            expires_at_step=30,
            provenance=f"urn:test:principal:{run_id}:{index}",
            nonce=f"nonce:principal:{run_id}:{index}",
            trace_event_id=f"trace:principal:{run_id}:{index}",
        ),
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=run_id,
        target=TARGET,
        epoch=EPOCH,
        cluster_id=cluster_id,
        failure_domain=f"failure:{index}",
        verifier_id="governance:identity",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=1,
        provenance="urn:test:principal-verification",
        trace_event_id=f"trace:principal-verified:{run_id}:{index}",
    )


def _observation(
    principal: PrincipalVerification,
    *,
    candidate_id: str,
    claim: str,
    index: int,
    manifest_root: str,
    policy_root: str,
    policy: CollectiveCommitPolicy,
    run_id: str,
    nonce: str | None = None,
    polarity: ObservationPolarity = ObservationPolarity.SUPPORT,
    materiality_ppm: int = 1_000_000,
    criticality_ppm: int = 0,
):
    attestation = ObservationAttestation(
        observation_id=f"observation:{run_id}:{index}",
        target=TARGET,
        candidate_id=candidate_id,
        claim_fingerprint=claim,
        principal_id=principal.principal_id,
        polarity=polarity,
        independence_group=f"group:{run_id}:{index}",
        source_domain=f"source:{run_id}:{index}",
        payload_fingerprint=_fingerprint(f"payload:{run_id}:{index}"),
        reported_quality_ppm=1_000_000,
        reported_relevance_ppm=1_000_000,
        reported_materiality_ppm=materiality_ppm,
        reported_criticality_ppm=criticality_ppm,
        provenance=f"urn:test:observation:{run_id}:{index}",
        nonce=nonce or f"nonce:observation:{run_id}:{index}",
        observed_at_step=2,
        expires_at_step=15,
        trace_event_id=f"trace:observation:{run_id}:{index}",
    )
    return verify_observation_attestation(
        attestation,
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=run_id,
        target=TARGET,
        candidate_id=candidate_id,
        claim_fingerprint=claim,
        epoch=EPOCH,
        principal_verification=principal,
        evidence_policy=policy.evidence_qualification,
        quality_ppm=1_000_000,
        relevance_ppm=1_000_000,
        materiality_ppm=materiality_ppm,
        criticality_ppm=criticality_ppm,
        verifier_id="governance:evidence",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=3,
        verification_provenance="urn:test:observation-verification",
        verification_trace_event_id=(
            f"trace:observation-verified:{run_id}:{index}"
        ),
        prior_observations=(),
    )


def _challenge(
    principal: PrincipalVerification,
    *,
    candidate_id: str,
    claim: str,
    index: int,
    manifest_root: str,
    policy_root: str,
    run_id: str,
):
    attestation = ChallengeAttestation(
        challenge_id=f"challenge:{run_id}:{index}",
        target=TARGET,
        candidate_id=candidate_id,
        claim_fingerprint=claim,
        principal_id=principal.principal_id,
        category=CHALLENGE_CATEGORY,
        execution_method="declared-counter-search-v1",
        execution_attestation_ref=f"opaque:execution:{run_id}:{index}",
        execution_fingerprint=_fingerprint(f"execution:{run_id}:{index}"),
        result=ChallengeResult.NO_COUNTEREVIDENCE,
        result_fingerprint=_fingerprint(f"result:{run_id}:{index}"),
        result_observation_fingerprints=(),
        provenance=f"urn:test:challenge:{run_id}:{index}",
        nonce=f"nonce:challenge:{run_id}:{index}",
        executed_at_step=2,
        expires_at_step=15,
        trace_event_id=f"trace:challenge:{run_id}:{index}",
    )
    return verify_challenge_attestation(
        attestation,
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=run_id,
        target=TARGET,
        candidate_id=candidate_id,
        claim_fingerprint=claim,
        epoch=EPOCH,
        principal_verification=principal,
        declared_categories=(CHALLENGE_CATEGORY,),
        maximum_ttl_steps=20,
        result_observations=(),
        verifier_id="governance:challenge",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=3,
        verification_provenance="urn:test:challenge-verification",
        verification_trace_event_id=(
            f"trace:challenge-verified:{run_id}:{index}"
        ),
        prior_challenges=(),
    )


def _input(
    *,
    candidate_id: str,
    claim: str,
    observations: tuple,
    challenge,
    manifest_root: str,
    policy_root: str,
    run_id: str,
    counter_observations: tuple = (),
    dispositions: tuple = (),
) -> CandidateCommitInput:
    binding = bind_evidence(
        evidence_id=f"evidence:{run_id}:{candidate_id}",
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=run_id,
        target=TARGET,
        candidate_id=candidate_id,
        claim_fingerprint=claim,
        epoch=EPOCH,
        positive_observations=observations,
        counter_observations=counter_observations,
        dispositions=dispositions,
        challenges=(challenge,),
        issuer_id="governance:evidence-binding",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=4,
        provenance=f"urn:test:evidence:{run_id}:{candidate_id}",
        trace_event_id=f"trace:evidence:{run_id}:{candidate_id}",
    )
    return CandidateCommitInput(
        candidate_id=candidate_id,
        claim_fingerprint=claim,
        evidence_binding=binding,
        positive_observations=observations,
        counter_observations=counter_observations,
        dispositions=dispositions,
        challenges=(challenge,),
    )


def _lease(
    principal: PrincipalVerification,
    observation,
    *,
    candidate_id: str,
    claim: str,
    index: int,
    manifest_root: str,
    policy_root: str,
    policy: CollectiveCommitPolicy,
    run_id: str,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_state: EligibleMembershipEpochState,
    replay_state: SupportLeaseReplayState,
    prior_leases: tuple[SupportLease, ...],
) -> tuple[SupportLease, SupportLeaseReplayState]:
    proposal = SupportLeaseProposal(
        proposal_id=f"support-proposal:{run_id}:{index}",
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=run_id,
        target=TARGET,
        candidate_id=candidate_id,
        claim_fingerprint=claim,
        epoch=EPOCH,
        principal_id=principal.principal_id,
        positive_observation_fingerprints=(
            verified_observation_fingerprint(observation),
        ),
        nonce=f"nonce:lease:{run_id}:{index}",
        proposed_at_step=3,
        provenance=f"urn:test:lease-proposal:{run_id}:{index}",
        trace_event_id=f"trace:lease-proposal:{run_id}:{index}",
    )
    return issue_support_lease(
        proposal,
        principal_verification=principal,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_state,
        replay_state=replay_state,
        positive_observations=(observation,),
        commit_policy=policy,
        lease_id=f"lease:{run_id}:{index}",
        issuer_id=f"governance:support:{run_id}",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=4,
        issuance_provenance=f"urn:test:lease:{run_id}:{index}",
        issuance_trace_event_id=f"trace:lease:{run_id}:{index}",
        prior_leases=prior_leases,
    )


@dataclass(frozen=True)
class _Scenario:
    manifest: CapabilityManifest
    policy: CollectiveCommitPolicy
    context: object
    candidate_inputs: tuple[CandidateCommitInput, ...]
    leases: tuple[SupportLease, ...]
    risk_chain_state: object
    risk_assessment: object
    threshold: object
    membership_snapshot: EligiblePrincipalSnapshot
    membership_state: EligibleMembershipEpochState
    replay_state: object
    support_replay_state: SupportLeaseReplayState
    stop_resolution: object
    permission: object
    leader_principal: PrincipalVerification
    leader_id: str
    other_id: str
    run_id: str
    hidden_replay_refs: tuple[str, ...] = ()


def _scenario(
    *,
    leader_id: str = "candidate:alpha",
    other_id: str = "candidate:beta",
    tie: bool = False,
    risk_minimum_positive: int = 1_000_000,
    shared_observation_nonce: bool = False,
    support_equivocation: bool = False,
    hidden_critical_counterevidence: bool = False,
    other_counterevidence_count: int = 0,
    unrelated_replay_receipts: bool = False,
    risk_minimum_support_clusters: int = 1,
    risk_minimum_support_ratio_ppm: int = 500_000,
    risk_minimum_source_diversity: int = 1,
    risk_required_challenges: tuple[str, ...] = (CHALLENGE_CATEGORY,),
    risk_minimum_assurance: str = "evidence_bound",
) -> _Scenario:
    run_id = f"run:commit-engine:{next(_SEQUENCE)}"
    policy = _policy(
        risk_minimum_positive=risk_minimum_positive,
        risk_minimum_support_clusters=risk_minimum_support_clusters,
        risk_minimum_support_ratio_ppm=risk_minimum_support_ratio_ppm,
        risk_minimum_source_diversity=risk_minimum_source_diversity,
        risk_required_challenges=risk_required_challenges,
        risk_minimum_assurance=risk_minimum_assurance,
    )
    manifest = _manifest(policy, leader_id=leader_id, other_id=other_id)
    manifest_root = commit_manifest_fingerprint(manifest, profile=PROFILE)
    policy_root = commit_policy_fingerprint(policy, profile=PROFILE)
    leader_claim = _fingerprint(f"claim:{run_id}:leader")
    other_claim = _fingerprint(f"claim:{run_id}:other")
    fallback_claim = _fingerprint(f"claim:{run_id}:fallback")

    leader_principal = _principal(
        f"principal:{run_id}:leader",
        f"cluster:{run_id}:leader",
        index=1,
        manifest_root=manifest_root,
        policy_root=policy_root,
        run_id=run_id,
    )
    other_principal = (
        leader_principal
        if support_equivocation
        else _principal(
            f"principal:{run_id}:other",
            f"cluster:{run_id}:other",
            index=2,
            manifest_root=manifest_root,
            policy_root=policy_root,
            run_id=run_id,
        )
    )
    membership_verifications = (
        (leader_principal,)
        if support_equivocation
        else (leader_principal, other_principal)
    )
    membership_snapshot, membership_state = issue_eligible_principal_snapshot(
        membership_verifications,
        snapshot_id=f"membership:{run_id}",
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=run_id,
        target=TARGET,
        epoch=EPOCH,
        issuer_id="governance:membership",
        membership_method="verified-static-epoch-v1",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=2,
        expires_at_step=20,
        provenance=f"urn:test:membership:{run_id}",
        trace_event_id=f"trace:membership:{run_id}",
    )

    leader_observation = _observation(
        leader_principal,
        candidate_id=leader_id,
        claim=leader_claim,
        index=1,
        manifest_root=manifest_root,
        policy_root=policy_root,
        policy=policy,
        run_id=run_id,
    )
    leader_extra = _observation(
        leader_principal,
        candidate_id=leader_id,
        claim=leader_claim,
        index=2,
        manifest_root=manifest_root,
        policy_root=policy_root,
        policy=policy,
        run_id=run_id,
    )
    other_observation = _observation(
        other_principal,
        candidate_id=other_id,
        claim=other_claim,
        index=3,
        manifest_root=manifest_root,
        policy_root=policy_root,
        policy=policy,
        run_id=run_id,
        nonce=(
            leader_observation.nonce if shared_observation_nonce else None
        ),
    )
    other_extra = (
        _observation(
            other_principal,
            candidate_id=other_id,
            claim=other_claim,
            index=4,
            manifest_root=manifest_root,
            policy_root=policy_root,
            policy=policy,
            run_id=run_id,
        )
        if tie
        else None
    )
    leader_challenge = _challenge(
        leader_principal,
        candidate_id=leader_id,
        claim=leader_claim,
        index=1,
        manifest_root=manifest_root,
        policy_root=policy_root,
        run_id=run_id,
    )
    other_challenge = _challenge(
        other_principal,
        candidate_id=other_id,
        claim=other_claim,
        index=2,
        manifest_root=manifest_root,
        policy_root=policy_root,
        run_id=run_id,
    )
    other_counter_observations = tuple(
        _observation(
            other_principal,
            candidate_id=other_id,
            claim=other_claim,
            index=50 + index,
            manifest_root=manifest_root,
            policy_root=policy_root,
            policy=policy,
            run_id=run_id,
            polarity=ObservationPolarity.CONTRADICT,
        )
        for index in range(other_counterevidence_count)
    )
    other_dispositions = tuple(
        issue_counterevidence_disposition(
            observation,
            disposition_id=f"disposition:{run_id}:other:{index}",
            kind=CounterevidenceDispositionKind.UNRESOLVED,
            rebuttal_observations=(),
            resolution_ref="",
            reason_codes=("awaiting_resolution",),
            verifier_id="governance:counterevidence",
            authority=AuthorityLevel.GOVERNANCE,
            current_step=4,
            provenance=f"urn:test:disposition:{run_id}:other:{index}",
            trace_event_id=f"trace:disposition:{run_id}:other:{index}",
        )
        for index, observation in enumerate(
            other_counter_observations,
            start=1,
        )
    )
    leader_input = _input(
        candidate_id=leader_id,
        claim=leader_claim,
        observations=(leader_observation, leader_extra),
        challenge=leader_challenge,
        manifest_root=manifest_root,
        policy_root=policy_root,
        run_id=run_id,
    )
    other_input = _input(
        candidate_id=other_id,
        claim=other_claim,
        observations=(
            (other_observation, other_extra)
            if other_extra is not None
            else (other_observation,)
        ),
        challenge=other_challenge,
        manifest_root=manifest_root,
        policy_root=policy_root,
        run_id=run_id,
        counter_observations=other_counter_observations,
        dispositions=other_dispositions,
    )

    support_replay = initialize_support_lease_replay_state(
        profile=PROFILE,
        protocol_id=PROTOCOL_ID,
        issuer_id=f"governance:support:{run_id}",
        authority=AuthorityLevel.GOVERNANCE,
        initialized_at_step=0,
        provenance=f"urn:test:support-replay:{run_id}",
        trace_event_id=f"trace:support-replay:{run_id}",
    )
    leader_lease, support_replay = _lease(
        leader_principal,
        leader_observation,
        candidate_id=leader_id,
        claim=leader_claim,
        index=1,
        manifest_root=manifest_root,
        policy_root=policy_root,
        policy=policy,
        run_id=run_id,
        membership_snapshot=membership_snapshot,
        membership_state=membership_state,
        replay_state=support_replay,
        prior_leases=(),
    )
    other_lease, support_replay = _lease(
        other_principal,
        other_observation,
        candidate_id=other_id,
        claim=other_claim,
        index=2,
        manifest_root=manifest_root,
        policy_root=policy_root,
        policy=policy,
        run_id=run_id,
        membership_snapshot=membership_snapshot,
        membership_state=membership_state,
        replay_state=support_replay,
        prior_leases=(leader_lease,),
    )
    leases = (leader_lease, other_lease)

    risk_chain = initialize_risk_assessment_chain(
        commit_policy=policy,
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=run_id,
        target=TARGET,
        epoch=EPOCH,
        issuer_id="governance:risk-chain",
        authority=AuthorityLevel.GOVERNANCE,
        initialized_at_step=1,
        expires_at_step=12,
        provenance=f"urn:test:risk-chain:{run_id}",
        trace_event_id=f"trace:risk-chain:{run_id}",
    )
    risk_assessment, risk_chain = issue_risk_assessment(
        risk_chain,
        assessment_id=f"risk:{run_id}",
        risk_band=RiskBand.LOW,
        risk_input_fingerprints=(_fingerprint(f"risk-input:{run_id}"),),
        rationale_codes=("declared_risk",),
        assessment_method="declared-risk-matrix-v1",
        commit_policy=policy,
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=run_id,
        target=TARGET,
        epoch=EPOCH,
        issuer_id="governance:risk",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=2,
        expires_at_step=12,
        provenance=f"urn:test:risk:{run_id}",
        trace_event_id=f"trace:risk:{run_id}",
    )
    threshold = issue_commit_threshold_snapshot(
        risk_assessment,
        chain_state=risk_chain,
        threshold_id=f"threshold:{run_id}",
        commit_policy=policy,
        issuer_id="governance:threshold",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=2,
        provenance=f"urn:test:threshold:{run_id}",
        trace_event_id=f"trace:threshold:{run_id}",
    )

    candidate_inputs = (leader_input, other_input)
    replay_state = initialize_commit_replay_state(
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=run_id,
        current_step=0,
        issuer_id="governance:replay",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:test:replay:{run_id}",
        trace_event_id=f"trace:replay:{run_id}",
    )
    recorded_candidate_inputs = candidate_inputs
    hidden_replay_refs: tuple[str, ...] = ()
    if hidden_critical_counterevidence:
        hidden_counter = _observation(
            leader_principal,
            candidate_id=leader_id,
            claim=leader_claim,
            index=97,
            manifest_root=manifest_root,
            policy_root=policy_root,
            policy=policy,
            run_id=run_id,
            polarity=ObservationPolarity.CONTRADICT,
            materiality_ppm=1_000_000,
            criticality_ppm=1_000_000,
        )
        hidden_disposition = issue_counterevidence_disposition(
            hidden_counter,
            disposition_id=f"disposition:{run_id}:hidden-critical",
            kind=CounterevidenceDispositionKind.UNRESOLVED,
            rebuttal_observations=(),
            resolution_ref="",
            reason_codes=("awaiting_resolution",),
            verifier_id="governance:counterevidence",
            authority=AuthorityLevel.GOVERNANCE,
            current_step=4,
            provenance=f"urn:test:hidden-disposition:{run_id}",
            trace_event_id=f"trace:hidden-disposition:{run_id}",
        )
        recorded_leader_input = replace(
            leader_input,
            counter_observations=(hidden_counter,),
            dispositions=(hidden_disposition,),
        )
        recorded_candidate_inputs = (
            recorded_leader_input,
            other_input,
        )
        hidden_replay_refs = (
            verified_observation_fingerprint(hidden_counter),
            counterevidence_disposition_fingerprint(hidden_disposition),
        )
    receipts = build_commit_replay_receipts(recorded_candidate_inputs, leases)
    if unrelated_replay_receipts:
        receipts = (
            *receipts,
            ReplayReceipt(
                namespace=ReplayNamespace.OBSERVATION,
                record_id=f"observation:{run_id}:unrelated-target",
                nonce=f"nonce:observation:{run_id}:unrelated-target",
                payload_fingerprint=_fingerprint(
                    f"unrelated-target-observation:{run_id}"
                ),
                target="decision:unrelated",
                candidate_id="candidate:unrelated",
                epoch=EPOCH,
                principal_id="principal:unrelated",
            ),
            ReplayReceipt(
                namespace=ReplayNamespace.WITNESS,
                record_id=f"witness:{run_id}:same-scope",
                nonce=f"nonce:witness:{run_id}:same-scope",
                payload_fingerprint=_fingerprint(f"witness:{run_id}"),
                target=TARGET,
                candidate_id=leader_id,
                epoch=EPOCH,
                principal_id="witness:unrelated-plane",
            ),
        )
    if shared_observation_nonce:
        seen_nonces: set[str] = set()
        receipts = tuple(
            item
            for item in receipts
            if not (item.nonce in seen_nonces or seen_nonces.add(item.nonce))
        )
    replay_state = record_commit_replay_receipts(
        replay_state,
        current_step=5,
        receipts=receipts,
    )
    context = issue_commit_evaluation_context(
        manifest,
        context_id=f"context:{run_id}",
        profile=PROFILE,
        assurance=ASSURANCE,
        run_id=run_id,
        target=TARGET,
        epoch=EPOCH,
        candidate_claims={
            leader_id: leader_claim,
            other_id: other_claim,
            "candidate:fallback": fallback_claim,
        },
        risk_chain_state=risk_chain,
        risk_assessment=risk_assessment,
        threshold_snapshot=threshold,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_state,
        replay_state=replay_state,
        support_replay_state=support_replay,
        issuer_id="governance:commit-context",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=5,
        provenance=f"urn:test:context:{run_id}",
        trace_event_id=f"trace:context:{run_id}",
    )
    context_ref = commit_evaluation_context_fingerprint(context)
    stop_resolution = verify_stop_resolution(
        StopResolution(
            target=TARGET,
            action=CommitAction.COMMIT,
            blocked=False,
            reason="all_hard_stops_resolved",
        ),
        resolution_id=f"stop:{run_id}",
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=run_id,
        epoch=EPOCH,
        decision_ref=context_ref,
        certificate_ref="",
        resolved_stop_root=_fingerprint(f"stop-root:{run_id}"),
        verifier_id="governance:stop",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=5,
        expires_at_step=10,
        provenance=f"urn:test:stop:{run_id}",
        trace_event_id=f"trace:stop:{run_id}",
    )
    permission = issue_action_permission(
        permission_id=f"permission:{run_id}",
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=PROTOCOL_ID,
        run_id=run_id,
        target=TARGET,
        action=CommitAction.COMMIT,
        epoch=EPOCH,
        decision_ref=context_ref,
        certificate_ref="",
        allowed=True,
        reason_codes=("policy_authorized",),
        issuer_id="governance:permission",
        policy_ref="policy:commit-action-v1",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=5,
        expires_at_step=10,
        provenance=f"urn:test:permission:{run_id}",
        trace_event_id=f"trace:permission:{run_id}",
    )
    return _Scenario(
        manifest=manifest,
        policy=policy,
        context=context,
        candidate_inputs=candidate_inputs,
        leases=leases,
        risk_chain_state=risk_chain,
        risk_assessment=risk_assessment,
        threshold=threshold,
        membership_snapshot=membership_snapshot,
        membership_state=membership_state,
        replay_state=replay_state,
        support_replay_state=support_replay,
        stop_resolution=stop_resolution,
        permission=permission,
        leader_principal=leader_principal,
        leader_id=leader_id,
        other_id=other_id,
        run_id=run_id,
        hidden_replay_refs=hidden_replay_refs,
    )


def _assess(
    scenario: _Scenario,
    *,
    candidate_inputs: tuple[CandidateCommitInput, ...] | None = None,
    leases: tuple[SupportLease, ...] | None = None,
    revocations: tuple = (),
    assessment_suffix: str = "one",
):
    return assess_optimal_commit(
        scenario.context,
        manifest=scenario.manifest,
        candidate_inputs=(
            scenario.candidate_inputs
            if candidate_inputs is None
            else candidate_inputs
        ),
        leases=scenario.leases if leases is None else leases,
        revocations=revocations,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
        stop_resolution=scenario.stop_resolution,
        commit_permission=scenario.permission,
        assessment_id=f"assessment:{scenario.run_id}:{assessment_suffix}",
        issuer_id="governance:commit",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=5,
        provenance=f"urn:test:assessment:{scenario.run_id}:{assessment_suffix}",
        trace_event_id=f"trace:assessment:{scenario.run_id}:{assessment_suffix}",
    )


def _context_request(scenario: _Scenario) -> tuple[CapabilityManifest, dict]:
    context = scenario.context
    return scenario.manifest, {
        "context_id": context.context_id,
        "profile": context.profile,
        "assurance": context.assurance,
        "run_id": context.run_id,
        "target": context.target,
        "epoch": context.epoch,
        "candidate_claims": {
            item.candidate_id: item.claim_fingerprint
            for item in context.candidate_claims
        },
        "risk_chain_state": scenario.risk_chain_state,
        "risk_assessment": scenario.risk_assessment,
        "threshold_snapshot": scenario.threshold,
        "membership_snapshot": scenario.membership_snapshot,
        "membership_epoch_state": scenario.membership_state,
        "replay_state": scenario.replay_state,
        "support_replay_state": scenario.support_replay_state,
        "issuer_id": context.issuer_id,
        "authority": context.authority,
        "current_step": context.issued_at_step,
        "provenance": context.provenance,
        "trace_event_id": context.trace_event_id,
    }


def test_optimal_commit_reconstructs_metrics_and_issues_tamper_evident_assessment() -> None:
    scenario = _scenario()
    assessment = _assess(scenario)

    assert commit_evaluation_context_is_authoritative(scenario.context)
    assert assessment.status is CommitAssessmentStatus.READY
    assert assessment.unique_leader is True
    assert assessment.leader_candidate_id == scenario.leader_id
    assert assessment.leader_margin == 1_000_000
    assert assessment.leader_ready_for_stability is True
    assert commit_assessment_is_authoritative(assessment)
    assert commit_assessment_fingerprint(assessment).startswith("sha256:")
    assert rebuild_commit_assessment_roots(assessment) == {
        "collective_evidence_root": assessment.collective_evidence_root,
        "collective_challenge_root": assessment.collective_challenge_root,
        "collective_lease_root": assessment.collective_lease_root,
    }

    leader = next(
        item
        for item in assessment.candidate_metrics
        if item.candidate_id == scenario.leader_id
    )
    assert (leader.positive_evidence, leader.counterevidence) == (2_000_000, 0)
    assert (leader.weighted_counterevidence, leader.net_evidence) == (
        0,
        2_000_000,
    )
    assert leader.counterevidence_ratio_ppm == 0
    assert leader.active_support_clusters == 1
    assert leader.eligible_support_clusters == 2
    assert leader.support_threshold_clusters == 1
    assert leader.support_ratio_ppm == 500_000
    assert leader.source_diversity == 2
    assert leader.ready_for_stability is True
    assert candidate_commit_metrics_fingerprint(
        leader,
        profile=PROFILE,
    ).startswith("sha256:")

    forged = replace(assessment, reason_codes=("tampered",))
    assert not commit_assessment_is_authoritative(forged)


def test_leader_margin_uses_zero_baseline_when_every_competitor_is_negative() -> None:
    scenario = _scenario(other_counterevidence_count=2)

    assessment = _assess(scenario)
    metrics = {
        item.candidate_id: item for item in assessment.candidate_metrics
    }

    assert metrics[scenario.leader_id].net_evidence == 2_000_000
    assert metrics[scenario.other_id].net_evidence == -1_000_000
    assert metrics[scenario.leader_id].margin == 2_000_000
    assert assessment.leader_margin == 2_000_000


def test_candidate_record_and_lease_permutations_are_semantically_identical() -> None:
    scenario = _scenario()
    first = _assess(scenario, assessment_suffix="first")
    reversed_inputs = tuple(
        replace(
            item,
            positive_observations=tuple(reversed(item.positive_observations)),
            challenges=tuple(reversed(item.challenges)),
        )
        for item in reversed(scenario.candidate_inputs)
    )
    second = _assess(
        scenario,
        candidate_inputs=reversed_inputs,
        leases=tuple(reversed(scenario.leases)),
        assessment_suffix="second",
    )

    assert first.status is second.status
    assert first.leader_candidate_id == second.leader_candidate_id
    assert first.leader_margin == second.leader_margin
    assert first.candidate_metrics == second.candidate_metrics
    assert first.collective_evidence_root == second.collective_evidence_root
    assert first.collective_challenge_root == second.collective_challenge_root
    assert first.collective_lease_root == second.collective_lease_root


def test_lexical_ids_never_break_ties_or_override_evidence() -> None:
    lexical_loser = _scenario(
        leader_id="candidate:z",
        other_id="candidate:a",
    )
    decisive = _assess(lexical_loser)
    assert decisive.leader_candidate_id == "candidate:z"

    tied = _scenario(
        leader_id="candidate:z",
        other_id="candidate:a",
        tie=True,
    )
    tie_assessment = _assess(tied)
    assert tie_assessment.status is CommitAssessmentStatus.NOT_READY
    assert tie_assessment.unique_leader is False
    assert tie_assessment.leader_candidate_id == ""
    assert set(tie_assessment.tied_candidate_ids) == {"candidate:a", "candidate:z"}
    assert CommitReasonCode.NO_UNIQUE_LEADER.value in tie_assessment.reason_codes


def test_active_risk_threshold_is_reapplied_instead_of_baseline_summary_gate() -> None:
    scenario = _scenario(risk_minimum_positive=3_000_000)
    assessment = _assess(scenario)
    leader = next(
        item
        for item in assessment.candidate_metrics
        if item.candidate_id == scenario.leader_id
    )

    assert leader.positive_evidence == 2_000_000
    assert leader.positive_threshold_satisfied is False
    assert leader.ready_for_stability is False
    assert assessment.status is CommitAssessmentStatus.NOT_READY
    assert (
        CommitReasonCode.POSITIVE_EVIDENCE_INSUFFICIENT.value
        in leader.reason_codes
    )


@pytest.mark.parametrize(
    ("scenario_overrides", "gate_field", "reason_code"),
    (
        (
            {"risk_minimum_support_clusters": 2},
            "support_cluster_satisfied",
            CommitReasonCode.SUPPORT_CLUSTERS_INSUFFICIENT,
        ),
        (
            {"risk_minimum_support_ratio_ppm": 750_000},
            "support_ratio_satisfied",
            CommitReasonCode.SUPPORT_RATIO_INSUFFICIENT,
        ),
        (
            {"risk_minimum_source_diversity": 3},
            "source_diversity_satisfied",
            CommitReasonCode.SOURCE_DIVERSITY_INSUFFICIENT,
        ),
        (
            {
                "risk_required_challenges": (
                    CHALLENGE_CATEGORY,
                    "counter_search",
                )
            },
            "challenge_coverage_satisfied",
            CommitReasonCode.CHALLENGE_COVERAGE_INCOMPLETE,
        ),
        (
            {"risk_minimum_assurance": "certified"},
            "minimum_assurance_satisfied",
            CommitReasonCode.ASSURANCE_INSUFFICIENT,
        ),
    ),
)
def test_every_active_risk_gate_is_reapplied(
    scenario_overrides: dict,
    gate_field: str,
    reason_code: CommitReasonCode,
) -> None:
    scenario = _scenario(**scenario_overrides)
    assessment = _assess(scenario)
    leader = next(
        item
        for item in assessment.candidate_metrics
        if item.candidate_id == scenario.leader_id
    )

    assert getattr(leader, gate_field) is False
    assert reason_code.value in leader.reason_codes
    assert leader.ready_for_stability is False
    assert assessment.status is CommitAssessmentStatus.NOT_READY


def test_context_claim_and_candidate_coverage_fail_closed_with_exact_codes() -> None:
    scenario = _scenario()
    with pytest.raises(CommitEvaluationError) as hidden:
        _assess(
            scenario,
            candidate_inputs=(scenario.candidate_inputs[0],),
        )
    assert hidden.value.reason_code is CommitReasonCode.CANDIDATE_COVERAGE_MISMATCH
    assert hidden.value.kind is CommitEvaluationFailureKind.INVALID

    conflicting = replace(
        scenario.candidate_inputs[0],
        claim_fingerprint=_fingerprint("conflicting-claim"),
    )
    with pytest.raises(CommitEvaluationError) as multiple_claims:
        _assess(
            scenario,
            candidate_inputs=(
                scenario.candidate_inputs[0],
                conflicting,
                scenario.candidate_inputs[1],
            ),
        )
    assert multiple_claims.value.reason_code is CommitReasonCode.CANDIDATE_CLAIM_CONFLICT


def test_context_authority_is_idempotent_strong_concurrent_and_fork_free() -> None:
    scenario = _scenario()
    manifest, request = _context_request(scenario)
    assert issue_commit_evaluation_context(manifest, **request) is scenario.context

    conflicting_claims = dict(request["candidate_claims"])
    conflicting_claims[scenario.leader_id] = _fingerprint("forked-context-claim")
    with pytest.raises(CommitEvaluationError) as claim_fork:
        issue_commit_evaluation_context(
            manifest,
            **{**request, "candidate_claims": conflicting_claims},
        )
    assert claim_fork.value.reason_code is CommitReasonCode.CONTEXT_AUTHORITY_FORK
    assert claim_fork.value.kind is CommitEvaluationFailureKind.SAFETY_FINDING
    assert len(claim_fork.value.references) == 2

    with pytest.raises(CommitEvaluationError) as payload_fork:
        issue_commit_evaluation_context(
            manifest,
            **{**request, "provenance": "urn:test:conflicting-context"},
        )
    assert payload_fork.value.reason_code is CommitReasonCode.CONTEXT_AUTHORITY_FORK
    assert payload_fork.value.kind is CommitEvaluationFailureKind.SAFETY_FINDING

    with ThreadPoolExecutor(max_workers=8) as pool:
        contexts = tuple(
            pool.map(
                lambda _: issue_commit_evaluation_context(manifest, **request),
                range(32),
            )
        )
    assert all(item is scenario.context for item in contexts)

    retained = weakref.ref(scenario.context)
    expected_identity = id(scenario.context)
    del contexts
    del scenario
    gc.collect()
    reissued = issue_commit_evaluation_context(manifest, **request)
    assert retained() is reissued
    assert id(reissued) == expected_identity


def test_tampered_context_binding_and_evidence_root_are_invalid_not_safety_findings() -> None:
    scenario = _scenario()
    forged_context = replace(
        scenario.context,
        risk_policy_root=_fingerprint("forged-risk-root"),
    )
    assert not commit_evaluation_context_is_authoritative(forged_context)
    forged_scenario = replace(scenario, context=forged_context)
    with pytest.raises(CommitEvaluationError) as context_error:
        _assess(forged_scenario)
    assert context_error.value.reason_code is CommitReasonCode.INVALID_CONTEXT
    assert context_error.value.kind is CommitEvaluationFailureKind.INVALID

    object.__setattr__(
        scenario.candidate_inputs[0].evidence_binding,
        "evidence_root",
        _fingerprint("forged-evidence-root"),
    )
    with pytest.raises(CommitEvaluationError) as evidence_error:
        _assess(scenario)
    assert evidence_error.value.reason_code is CommitReasonCode.EVIDENCE_BINDING_INVALID
    assert evidence_error.value.kind is CommitEvaluationFailureKind.INVALID


def test_cross_candidate_replay_and_support_equivocation_are_safety_assessments() -> None:
    replay = _scenario(shared_observation_nonce=True)
    replay_assessment = _assess(replay)
    assert replay_assessment.status is CommitAssessmentStatus.SAFETY_VIOLATION
    assert replay_assessment.replay_conflict_references
    assert replay_assessment.equivocation_finding_ids == ()
    assert replay_assessment.reason_codes == (
        CommitReasonCode.CROSS_RECORD_REPLAY.value,
    )

    equivocation = _scenario(support_equivocation=True)
    equivocation_assessment = _assess(equivocation)
    assert equivocation_assessment.status is CommitAssessmentStatus.SAFETY_VIOLATION
    assert equivocation_assessment.equivocation_finding_ids
    assert (
        CommitReasonCode.SUPPORT_EQUIVOCATION.value
        in equivocation_assessment.reason_codes
    )


def test_unrecorded_disposition_and_revocation_cannot_bypass_central_replay() -> None:
    scenario = _scenario()
    leader_input = next(
        item
        for item in scenario.candidate_inputs
        if item.candidate_id == scenario.leader_id
    )
    counter = _observation(
        scenario.leader_principal,
        candidate_id=scenario.leader_id,
        claim=leader_input.claim_fingerprint,
        index=99,
        manifest_root=scenario.context.manifest_root,
        policy_root=scenario.context.commit_policy_root,
        policy=scenario.policy,
        run_id=scenario.run_id,
        polarity=ObservationPolarity.CONTRADICT,
    )
    disposition = issue_counterevidence_disposition(
        counter,
        disposition_id=f"disposition:{scenario.run_id}:unrecorded",
        kind=CounterevidenceDispositionKind.UNRESOLVED,
        rebuttal_observations=(),
        resolution_ref="",
        reason_codes=("awaiting_resolution",),
        verifier_id="governance:counterevidence",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=4,
        provenance=f"urn:test:disposition:{scenario.run_id}",
        trace_event_id=f"trace:disposition:{scenario.run_id}",
    )
    input_with_hidden_disposition = replace(
        leader_input,
        dispositions=(disposition,),
    )
    disposition_inputs = tuple(
        input_with_hidden_disposition if item is leader_input else item
        for item in scenario.candidate_inputs
    )
    disposition_receipts = build_commit_replay_receipts(
        disposition_inputs,
        scenario.leases,
    )
    disposition_fingerprint = counterevidence_disposition_fingerprint(disposition)
    assert any(
        item.namespace.value == "counterevidence_disposition"
        and item.payload_fingerprint == disposition_fingerprint
        for item in disposition_receipts
    )
    with pytest.raises(CommitEvaluationError) as disposition_error:
        _assess(scenario, candidate_inputs=disposition_inputs)
    assert disposition_error.value.reason_code is CommitReasonCode.REPLAY_COVERAGE_MISMATCH
    assert disposition_fingerprint in disposition_error.value.references

    revocation = revoke_support_lease(
        scenario.leases[0],
        revocation_id=f"revocation:{scenario.run_id}:unrecorded",
        reason_codes=("support_withdrawn",),
        issuer_id="governance:support",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=5,
        provenance=f"urn:test:revocation:{scenario.run_id}",
        trace_event_id=f"trace:revocation:{scenario.run_id}",
    )
    revocation_receipts = build_commit_replay_receipts(
        scenario.candidate_inputs,
        scenario.leases,
        (revocation,),
    )
    revocation_fingerprint = support_lease_revocation_fingerprint(revocation)
    assert any(
        item.namespace.value == "support_revocation"
        and item.payload_fingerprint == revocation_fingerprint
        for item in revocation_receipts
    )
    with pytest.raises(CommitEvaluationError) as revocation_error:
        _assess(scenario, revocations=(revocation,))
    assert revocation_error.value.reason_code is CommitReasonCode.REPLAY_COVERAGE_MISMATCH
    assert revocation_fingerprint in revocation_error.value.references


def test_recorded_hidden_critical_counterevidence_cannot_be_omitted() -> None:
    scenario = _scenario(hidden_critical_counterevidence=True)
    assert len(scenario.hidden_replay_refs) == 2

    with pytest.raises(CommitEvaluationError) as hidden:
        _assess(scenario)
    assert hidden.value.reason_code is CommitReasonCode.REPLAY_COVERAGE_MISMATCH
    assert set(scenario.hidden_replay_refs).issubset(hidden.value.references)
    assert hidden.value.kind is CommitEvaluationFailureKind.INVALID


def test_unrelated_replay_namespaces_and_scopes_do_not_block_commit() -> None:
    scenario = _scenario(unrelated_replay_receipts=True)
    assessment = _assess(scenario)

    assert assessment.status is CommitAssessmentStatus.READY
    assert assessment.leader_candidate_id == scenario.leader_id


def test_optimal_commit_api_has_no_attention_pheromone_or_caller_metric_channel() -> None:
    signature = inspect.signature(assess_optimal_commit)
    forbidden = {
        "attention",
        "pheromone",
        "recruitment",
        "inhibition",
        "metrics",
        "score",
        "summary",
    }
    assert forbidden.isdisjoint(signature.parameters)
    assert all(
        parameter.kind is not inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    candidate_fields = set(CandidateCommitInput.__dataclass_fields__)
    assert forbidden.isdisjoint(candidate_fields)


def test_attention_mutation_has_zero_commit_metric_and_outcome_sensitivity() -> None:
    scenario = _scenario()
    baseline = _assess(scenario, assessment_suffix="attention-baseline")
    attention_policy = CollectiveDecisionPolicy(
        mode="quorum",
        quorum_threshold=999,
        recruitment_enabled=True,
        inhibition_enabled=True,
        pheromone_enabled=True,
        pheromone_evaporation_rate=0.99,
        pheromone_positive_weight=9.0,
        pheromone_negative_weight=8.0,
        pheromone_cautionary_weight=7.0,
        pheromone_novelty_weight=6.0,
        fallback_candidate="candidate:fallback",
    )
    mutated_manifest = replace(
        scenario.manifest,
        protocol=replace(
            scenario.manifest.protocol,
            collective_decision_policy=attention_policy,
        ),
    )
    assert commit_manifest_fingerprint(mutated_manifest, profile=PROFILE) == (
        scenario.context.manifest_root
    )
    mutated = _assess(
        replace(scenario, manifest=mutated_manifest),
        assessment_suffix="attention-mutated",
    )

    assert mutated.status is baseline.status
    assert mutated.leader_candidate_id == baseline.leader_candidate_id
    assert mutated.leader_margin == baseline.leader_margin
    assert mutated.candidate_metrics == baseline.candidate_metrics
    assert mutated.collective_evidence_root == baseline.collective_evidence_root
    assert mutated.collective_challenge_root == baseline.collective_challenge_root
    assert mutated.collective_lease_root == baseline.collective_lease_root
