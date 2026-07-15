from __future__ import annotations

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

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import re
from threading import RLock

from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.certificate import (
    EvidenceCommitCertificate,
    LocalCommitReceipt,
    evidence_commit_certificate_body_root,
    evidence_commit_certificate_fingerprint,
    evidence_commit_certificate_from_payload,
    evidence_commit_certificate_payload,
    issue_evidence_commit_certificate,
    issue_local_commit_receipt,
    output_payload_fingerprint,
)
from pheroos.governance.challenge import (
    ChallengeAttestation,
    ChallengeResult,
    VerifiedChallenge,
    verify_challenge_attestation,
)
from pheroos.governance.commit import (
    CandidateCommitInput,
    CommitAssessment,
    CommitEvaluationContext,
    assess_optimal_commit,
    build_commit_replay_receipts,
    commit_evaluation_context_fingerprint,
    issue_commit_evaluation_context,
)
from pheroos.governance.commit_state import (
    CommitReplayState,
    CommitWindowState,
    ReplayReceipt,
    advance_commit_window_state,
    commit_replay_state_fingerprint,
    initialize_commit_replay_state,
    initialize_commit_window_state,
    record_commit_replay_receipts,
)
from pheroos.governance.distributed_commit import (
    DISTRIBUTED_PROPOSAL_VERSION,
    QUORUM_WITNESS_VERSION,
    WITNESS_VERIFICATION_VERSION,
    DistributedCommitCertificate,
    DistributedCommitProposal,
    DistributedCommitState,
    QuorumWitness,
    WitnessVerification,
    assemble_portable_distributed_commit_certificate,
    distributed_commit_proposal_from_payload,
    distributed_commit_proposal_payload,
    distributed_commit_value_payload,
    distributed_commit_value_root,
    initialize_distributed_commit_state,
    issue_distributed_commit_proposal,
    portable_membership_snapshot_from_eligible,
    quorum_witness_signing_root,
    quorum_witness_fingerprint,
    record_witness_verifications,
    verify_quorum_witness,
)
from pheroos.governance.evidence_binding import (
    EvidenceBinding,
    bind_evidence,
    evidence_binding_fingerprint,
)
from pheroos.governance.observation import (
    CounterevidenceDisposition,
    CounterevidenceDispositionKind,
    ObservationAttestation,
    ObservationPolarity,
    VerifiedObservation,
    issue_counterevidence_disposition,
    verified_observation_fingerprint,
    verify_observation_attestation,
)
from pheroos.governance.permission import (
    ActionPermission,
    action_permission_fingerprint,
    issue_action_permission,
)
from pheroos.governance.principal import (
    PrincipalAttestation,
    PrincipalVerification,
    principal_verification_fingerprint,
    verify_principal_attestation,
)
from pheroos.governance.risk import (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
    RiskBand,
    initialize_risk_assessment_chain,
    issue_commit_threshold_snapshot,
    issue_risk_assessment,
)
from pheroos.governance.stop_signal import (
    StopResolution,
    StopResolutionVerification,
    stop_resolution_verification_fingerprint,
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
    support_lease_replay_state_fingerprint,
)
from pheroos.protocol.commit_models import CommitAction, CommitAssurance
from pheroos.protocol.commit_wire import (
    commit_manifest_fingerprint,
    commit_payload_fingerprint,
    commit_policy_fingerprint,
)
from pheroos.protocol.manifest import capability_manifest_from_dict
from pheroos.protocol.models import CapabilityManifest


REFERENCE_TARGET = "decision:optimal"
REFERENCE_PROTOCOL_ID = "protocol:tck:optimal-commit"
REFERENCE_EPOCH = 3
REFERENCE_CHALLENGE_CATEGORY = "independent_replication"
REFERENCE_LEADER = "candidate:alpha"
REFERENCE_OTHER = "candidate:beta"
REFERENCE_FALLBACK = "candidate:fallback"


_REFERENCE_WINDOW_FIXTURES: dict[str, CommitWindowState] = {}
_REFERENCE_WINDOW_FIXTURES_LOCK = RLock()
_REFERENCE_STABLE_FIXTURES: dict[
    tuple[str, str], ReferenceStableCommit
] = {}
_REFERENCE_STABLE_FIXTURES_LOCK = RLock()
_REFERENCE_ASSESSMENT_FIXTURES: dict[
    tuple[object, ...], CommitAssessment
] = {}
_REFERENCE_ASSESSMENT_FIXTURES_LOCK = RLock()
_REFERENCE_DISTRIBUTED_FIXTURES: dict[
    tuple[str, str, int | None], ReferenceDistributedCommit
] = {}
_REFERENCE_DISTRIBUTED_FIXTURES_LOCK = RLock()


def reference_fingerprint(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def reference_namespace(vector_id: str, variant: str = "base") -> str:
    """Return a deterministic, JSON/text-safe strong-authority namespace."""

    normalized = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", f"{vector_id}:{variant}")
    digest = sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"tck:{normalized}:{digest}"


@dataclass(frozen=True)
class ReferenceScenario:
    namespace: str
    manifest: CapabilityManifest
    policy: object
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    leader_id: str
    other_id: str
    fallback_id: str
    claims: Mapping[str, str]
    principals: tuple[PrincipalVerification, ...]
    membership_snapshot: EligiblePrincipalSnapshot
    membership_state: EligibleMembershipEpochState
    observations: Mapping[str, tuple[VerifiedObservation, ...]]
    challenges: Mapping[str, VerifiedChallenge]
    bindings: Mapping[str, EvidenceBinding]
    candidate_inputs: tuple[CandidateCommitInput, ...]
    leases: tuple[SupportLease, ...]
    support_replay_state: SupportLeaseReplayState
    risk_chain_state: RiskAssessmentChainState
    risk_assessment: RiskAssessment
    threshold: CommitThresholdSnapshot
    replay_state: CommitReplayState
    context: CommitEvaluationContext
    stop_resolution: StopResolutionVerification
    permission: ActionPermission


@dataclass(frozen=True)
class ReferenceStableCommit:
    scenario: ReferenceScenario
    assessments: tuple[CommitAssessment, ...]
    window: CommitWindowState
    output_fingerprint: str
    receipt: LocalCommitReceipt


@dataclass(frozen=True)
class ReferencePortableCommit:
    stable: ReferenceStableCommit
    certificate: EvidenceCommitCertificate
    trusted_issuer_attestations: Mapping[str, str]


@dataclass(frozen=True)
class ReferenceDistributedCommit:
    portable: ReferencePortableCommit
    proposal: DistributedCommitProposal
    state: DistributedCommitState
    verifications: tuple[WitnessVerification, ...]
    trusted_witness_attestations: Mapping[str, str]


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
    """Issue one complete deterministic Optimal Commit authority substrate."""

    manifest = capability_manifest_from_dict(dict(manifest_payload))
    policy = manifest.protocol.collective_commit_policy
    if policy is None:
        raise ValueError("reference scenario requires collective_commit_policy")
    assurance = CommitAssurance(policy.assurance)
    protocol_id = manifest.protocol.id
    target = policy.target
    epoch = REFERENCE_EPOCH
    candidates = tuple(item.id for item in manifest.protocol.candidates)
    leader_id = REFERENCE_LEADER if REFERENCE_LEADER in candidates else candidates[0]
    fallback_id = policy.terminal_outcome.safe_fallback_candidate
    substantive = tuple(
        item for item in candidates if item not in {leader_id, fallback_id}
    )
    if not substantive:
        raise ValueError("reference scenario requires two substantive candidates")
    other_id = substantive[0]
    manifest_root = commit_manifest_fingerprint(manifest, profile=profile)
    policy_root = commit_policy_fingerprint(policy, profile=profile)
    # A JSON mutation that changes authority-bearing manifest semantics must
    # never fork an existing strong process-local head.  Canonical manifest and
    # policy roots isolate those variants while semantic permutations that keep
    # both roots stable continue to exercise exact-replay authority.
    namespace = reference_namespace(
        vector_id,
        f"{variant}:manifest-{manifest_root[7:23]}:policy-{policy_root[7:23]}",
    )
    run_id = f"run:{namespace}"
    claims = {
        candidate_id: reference_fingerprint(f"claim:{namespace}:{candidate_id}")
        for candidate_id in candidates
    }

    if type(minimum_membership_size) is not int or minimum_membership_size < 3:
        raise ValueError("reference membership requires at least three principals")
    membership_size = max(
        minimum_membership_size,
        (
            policy.distributed.membership_size
            if policy.distributed is not None
            else 0
        ),
    )
    principals = tuple(
        issue_reference_principal(
            namespace,
            index=index,
            profile=profile,
            assurance=assurance,
            manifest_root=manifest_root,
            commit_policy_root=policy_root,
            protocol_id=protocol_id,
            run_id=run_id,
            target=target,
            epoch=epoch,
            cluster_id=(
                f"cluster:{namespace}:shared" if shared_cluster else None
            ),
        )
        for index in range(1, membership_size + 1)
    )
    membership_snapshot, membership_state = issue_eligible_principal_snapshot(
        principals,
        snapshot_id=f"membership:{namespace}",
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        issuer_id="governance:tck:membership",
        membership_method="verified-static-epoch-v1",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=2,
        expires_at_step=30,
        provenance=f"urn:pheroos:tck:{namespace}:membership",
        trace_event_id=f"trace:{namespace}:membership",
    )

    if type(leader_observation_count) is not int or leader_observation_count < 2:
        raise ValueError("reference leader requires at least two observations")
    selected_other_count = (
        2 if tie else 1
        if other_observation_count is None
        else other_observation_count
    )
    if type(selected_other_count) is not int or selected_other_count < 1:
        raise ValueError("reference other candidate requires observations")
    leader_observations = tuple(
        issue_reference_observation(
            namespace,
            index=index,
            principal=(principals[0] if index != 2 else principals[2]),
            candidate_id=leader_id,
            claim_fingerprint=claims[leader_id],
            profile=profile,
            assurance=assurance,
            manifest_root=manifest_root,
            commit_policy_root=policy_root,
            protocol_id=protocol_id,
            run_id=run_id,
            target=target,
            epoch=epoch,
            evidence_policy=policy.evidence_qualification,
        )
        for index in range(1, leader_observation_count + 1)
    )
    other_values = [
        issue_reference_observation(
            namespace,
            index=100 + index,
            principal=principals[1],
            candidate_id=other_id,
            claim_fingerprint=claims[other_id],
            profile=profile,
            assurance=assurance,
            manifest_root=manifest_root,
            commit_policy_root=policy_root,
            protocol_id=protocol_id,
            run_id=run_id,
            target=target,
            epoch=epoch,
            evidence_policy=policy.evidence_qualification,
        )
        for index in range(1, selected_other_count + 1)
    ]
    observations = {
        leader_id: leader_observations,
        other_id: tuple(other_values),
    }
    challenges = {
        candidate_id: issue_reference_challenge(
            namespace,
            index=index,
            principal=principals[index - 1],
            candidate_id=candidate_id,
            claim_fingerprint=claims[candidate_id],
            profile=profile,
            assurance=assurance,
            manifest_root=manifest_root,
            commit_policy_root=policy_root,
            protocol_id=protocol_id,
            run_id=run_id,
            target=target,
            epoch=epoch,
        )
        for index, candidate_id in enumerate((leader_id, other_id), start=1)
    }
    bindings = {
        candidate_id: issue_reference_binding(
            namespace,
            candidate_id=candidate_id,
            claim_fingerprint=claims[candidate_id],
            observations=candidate_observations,
            counter_observations=(),
            dispositions=(),
            challenges=(challenges[candidate_id],),
            profile=profile,
            assurance=assurance,
            manifest_root=manifest_root,
            commit_policy_root=policy_root,
            protocol_id=protocol_id,
            run_id=run_id,
            target=target,
            epoch=epoch,
            current_step=4,
        )
        for candidate_id, candidate_observations in observations.items()
    }
    candidate_inputs = tuple(
        CandidateCommitInput(
            candidate_id=candidate_id,
            claim_fingerprint=claims[candidate_id],
            evidence_binding=bindings[candidate_id],
            positive_observations=observations[candidate_id],
            counter_observations=(),
            dispositions=(),
            challenges=(challenges[candidate_id],),
        )
        for candidate_id in (leader_id, other_id)
    )

    support_replay = initialize_support_lease_replay_state(
        profile=profile,
        protocol_id=protocol_id,
        issuer_id=f"governance:tck:support:{namespace}",
        authority=AuthorityLevel.GOVERNANCE,
        initialized_at_step=0,
        provenance=f"urn:pheroos:tck:{namespace}:support-replay",
        trace_event_id=f"trace:{namespace}:support-replay",
    )
    leases: list[SupportLease] = []
    lease_inputs = (
        (leader_id, principals[0], observations[leader_id][0]),
        (other_id, principals[1], observations[other_id][0]),
        (leader_id, principals[2], observations[leader_id][1]),
    )
    for index, (candidate_id, principal, observation) in enumerate(
        lease_inputs,
        start=1,
    ):
        lease, support_replay = issue_reference_lease(
            namespace,
            index=index,
            principal=principal,
            observation=observation,
            candidate_id=candidate_id,
            claim_fingerprint=claims[candidate_id],
            profile=profile,
            assurance=assurance,
            manifest_root=manifest_root,
            commit_policy_root=policy_root,
            protocol_id=protocol_id,
            run_id=run_id,
            target=target,
            epoch=epoch,
            policy=policy,
            membership_snapshot=membership_snapshot,
            membership_state=membership_state,
            replay_state=support_replay,
            prior_leases=tuple(leases),
        )
        leases.append(lease)

    risk_chain = initialize_risk_assessment_chain(
        commit_policy=policy,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        issuer_id="governance:tck:risk-chain",
        authority=AuthorityLevel.GOVERNANCE,
        initialized_at_step=1,
        expires_at_step=30,
        provenance=f"urn:pheroos:tck:{namespace}:risk-chain",
        trace_event_id=f"trace:{namespace}:risk-chain",
    )
    risk_assessment, risk_chain = issue_risk_assessment(
        risk_chain,
        assessment_id=f"risk:{namespace}:low",
        risk_band=RiskBand.LOW,
        risk_input_fingerprints=(reference_fingerprint(f"risk-input:{namespace}"),),
        rationale_codes=("declared_risk",),
        assessment_method="declared-risk-matrix-v1",
        commit_policy=policy,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        issuer_id="governance:tck:risk",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=2,
        expires_at_step=30,
        provenance=f"urn:pheroos:tck:{namespace}:risk",
        trace_event_id=f"trace:{namespace}:risk",
    )
    threshold = issue_commit_threshold_snapshot(
        risk_assessment,
        chain_state=risk_chain,
        threshold_id=f"threshold:{namespace}:low",
        commit_policy=policy,
        issuer_id="governance:tck:threshold",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=2,
        provenance=f"urn:pheroos:tck:{namespace}:threshold",
        trace_event_id=f"trace:{namespace}:threshold",
    )
    replay = initialize_commit_replay_state(
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        current_step=0,
        issuer_id="governance:tck:replay",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:pheroos:tck:{namespace}:replay",
        trace_event_id=f"trace:{namespace}:replay",
    )
    replay = record_commit_replay_receipts(
        replay,
        current_step=5,
        receipts=build_commit_replay_receipts(candidate_inputs, leases),
    )
    context = issue_commit_evaluation_context(
        manifest,
        context_id=f"context:{namespace}",
        profile=profile,
        assurance=assurance,
        run_id=run_id,
        target=target,
        epoch=epoch,
        candidate_claims=claims,
        risk_chain_state=risk_chain,
        risk_assessment=risk_assessment,
        threshold_snapshot=threshold,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_state,
        replay_state=replay,
        support_replay_state=support_replay,
        issuer_id="governance:tck:commit-context",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=5,
        provenance=f"urn:pheroos:tck:{namespace}:context",
        trace_event_id=f"trace:{namespace}:context",
    )
    stop, permission = issue_reference_action_gates(
        namespace,
        context=context,
        action=CommitAction.COMMIT,
        blocked=blocked,
        current_step=5,
        expires_at_step=20,
        suffix="commit",
    )
    return ReferenceScenario(
        namespace=namespace,
        manifest=manifest,
        policy=policy,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        leader_id=leader_id,
        other_id=other_id,
        fallback_id=fallback_id,
        claims=claims,
        principals=principals,
        membership_snapshot=membership_snapshot,
        membership_state=membership_state,
        observations=observations,
        challenges=challenges,
        bindings=bindings,
        candidate_inputs=candidate_inputs,
        leases=tuple(leases),
        support_replay_state=support_replay,
        risk_chain_state=risk_chain,
        risk_assessment=risk_assessment,
        threshold=threshold,
        replay_state=replay,
        context=context,
        stop_resolution=stop,
        permission=permission,
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
    principal_id = f"principal:{namespace}:{index}"
    return verify_principal_attestation(
        PrincipalAttestation(
            principal_id=principal_id,
            attestation_ref=f"opaque:principal:{namespace}:{index}",
            method="identity-verifier-v1",
            issuer_id="issuer:tck:identity",
            issued_at_step=0,
            expires_at_step=30,
            provenance=f"urn:pheroos:tck:{namespace}:principal:{index}",
            nonce=f"nonce:principal:{namespace}:{index}",
            trace_event_id=f"trace:{namespace}:principal:{index}",
        ),
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        cluster_id=cluster_id or f"cluster:{namespace}:{index}",
        failure_domain=failure_domain or f"failure-domain:{namespace}:{index}",
        verifier_id="governance:tck:identity",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=1,
        provenance=f"urn:pheroos:tck:{namespace}:principal-verification:{index}",
        trace_event_id=f"trace:{namespace}:principal-verified:{index}",
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
    expiry = (
        2 + evidence_policy.observation_ttl_steps
        if expires_at_step is None
        else expires_at_step
    )
    attestation = ObservationAttestation(
        observation_id=f"observation:{namespace}:{index}",
        target=target,
        candidate_id=candidate_id,
        claim_fingerprint=claim_fingerprint,
        principal_id=principal.principal_id,
        polarity=polarity,
        independence_group=(
            independence_group or f"group:{namespace}:{index}"
        ),
        source_domain=source_domain or f"source-domain:{namespace}:{index}",
        payload_fingerprint=reference_fingerprint(f"payload:{namespace}:{index}"),
        reported_quality_ppm=quality_ppm,
        reported_relevance_ppm=relevance_ppm,
        reported_materiality_ppm=materiality_ppm,
        reported_criticality_ppm=criticality_ppm,
        provenance=f"urn:pheroos:tck:{namespace}:observation:{index}",
        nonce=nonce or f"nonce:observation:{namespace}:{index}",
        observed_at_step=2,
        expires_at_step=expiry,
        trace_event_id=f"trace:{namespace}:observation:{index}",
    )
    return verify_observation_attestation(
        attestation,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        candidate_id=candidate_id,
        claim_fingerprint=claim_fingerprint,
        epoch=epoch,
        principal_verification=principal,
        evidence_policy=evidence_policy,
        quality_ppm=quality_ppm,
        relevance_ppm=relevance_ppm,
        materiality_ppm=materiality_ppm,
        criticality_ppm=criticality_ppm,
        verifier_id="governance:tck:evidence",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=3,
        verification_provenance=(
            f"urn:pheroos:tck:{namespace}:observation-verification:{index}"
        ),
        verification_trace_event_id=(
            f"trace:{namespace}:observation-verified:{index}"
        ),
        prior_observations=(),
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
    attestation = ChallengeAttestation(
        challenge_id=f"challenge:{namespace}:{index}",
        target=target,
        candidate_id=candidate_id,
        claim_fingerprint=claim_fingerprint,
        principal_id=principal.principal_id,
        category=REFERENCE_CHALLENGE_CATEGORY,
        execution_method="declared-counter-search-v1",
        execution_attestation_ref=f"opaque:execution:{namespace}:{index}",
        execution_fingerprint=reference_fingerprint(
            f"challenge-execution:{namespace}:{index}"
        ),
        result=result,
        result_fingerprint=reference_fingerprint(
            f"challenge-result:{namespace}:{index}:{result.value}"
        ),
        result_observation_fingerprints=tuple(
            verified_observation_fingerprint(item) for item in result_observations
        ),
        provenance=f"urn:pheroos:tck:{namespace}:challenge:{index}",
        nonce=f"nonce:challenge:{namespace}:{index}",
        executed_at_step=2,
        expires_at_step=20,
        trace_event_id=f"trace:{namespace}:challenge:{index}",
    )
    return verify_challenge_attestation(
        attestation,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        candidate_id=candidate_id,
        claim_fingerprint=claim_fingerprint,
        epoch=epoch,
        principal_verification=principal,
        declared_categories=(REFERENCE_CHALLENGE_CATEGORY,),
        maximum_ttl_steps=20,
        result_observations=tuple(result_observations),
        verifier_id="governance:tck:challenge",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=3,
        verification_provenance=(
            f"urn:pheroos:tck:{namespace}:challenge-verification:{index}"
        ),
        verification_trace_event_id=(
            f"trace:{namespace}:challenge-verified:{index}"
        ),
        prior_challenges=(),
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
    selected_resolution_ref = resolution_ref
    if (
        not selected_resolution_ref
        and kind is not CounterevidenceDispositionKind.UNRESOLVED
    ):
        selected_resolution_ref = reference_fingerprint(
            f"counterevidence-resolution:{namespace}:{index}:{kind.value}"
        )
    return issue_counterevidence_disposition(
        counter_observation,
        disposition_id=f"disposition:{namespace}:{index}",
        kind=kind,
        rebuttal_observations=tuple(rebuttal_observations),
        resolution_ref=selected_resolution_ref,
        reason_codes=(f"tck_{kind.value}",),
        verifier_id="governance:tck:counterevidence",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=4,
        provenance=f"urn:pheroos:tck:{namespace}:disposition:{index}",
        trace_event_id=f"trace:{namespace}:disposition:{index}",
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
    suffix = f":{binding_variant}" if binding_variant else ""
    return bind_evidence(
        evidence_id=f"evidence:{namespace}:{candidate_id}{suffix}",
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        candidate_id=candidate_id,
        claim_fingerprint=claim_fingerprint,
        epoch=epoch,
        positive_observations=tuple(observations),
        counter_observations=tuple(counter_observations),
        dispositions=tuple(dispositions),
        challenges=tuple(challenges),
        issuer_id="governance:tck:evidence-binding",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=current_step,
        provenance=(
            f"urn:pheroos:tck:{namespace}:evidence:{candidate_id}{suffix}"
        ),
        trace_event_id=f"trace:{namespace}:evidence:{candidate_id}{suffix}",
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
    proposal = SupportLeaseProposal(
        proposal_id=f"support-proposal:{namespace}:{index}",
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        candidate_id=candidate_id,
        claim_fingerprint=claim_fingerprint,
        epoch=epoch,
        principal_id=principal.principal_id,
        positive_observation_fingerprints=(
            verified_observation_fingerprint(observation),
        ),
        nonce=f"nonce:lease:{namespace}:{index}",
        proposed_at_step=current_step - 1,
        provenance=f"urn:pheroos:tck:{namespace}:lease-proposal:{index}",
        trace_event_id=f"trace:{namespace}:lease-proposal:{index}",
    )
    return issue_support_lease(
        proposal,
        principal_verification=principal,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_state,
        replay_state=replay_state,
        positive_observations=(observation,),
        commit_policy=policy,
        lease_id=f"lease:{namespace}:{index}",
        issuer_id=issuer_id or f"governance:tck:support:{namespace}",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=current_step,
        issuance_provenance=f"urn:pheroos:tck:{namespace}:lease:{index}",
        issuance_trace_event_id=f"trace:{namespace}:lease:{index}",
        prior_leases=tuple(prior_leases),
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
    selected_target = target or context.target
    context_ref = commit_evaluation_context_fingerprint(context)
    certificate_ref = (
        ""
        if action is CommitAction.COMMIT
        else reference_fingerprint(
            f"action-certificate:{namespace}:{suffix}:{action.value}"
        )
    )
    stop = verify_stop_resolution(
        StopResolution(
            target=selected_target,
            action=action,
            blocked=blocked,
            reason="hard_stop" if blocked else "all_hard_stops_resolved",
        ),
        resolution_id=f"stop:{namespace}:{suffix}",
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id,
        epoch=context.epoch,
        decision_ref=context_ref,
        certificate_ref=certificate_ref,
        resolved_stop_root=reference_fingerprint(
            f"stop-root:{namespace}:{suffix}:{blocked}"
        ),
        verifier_id="governance:tck:stop",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=current_step,
        expires_at_step=expires_at_step,
        provenance=f"urn:pheroos:tck:{namespace}:stop:{suffix}",
        trace_event_id=f"trace:{namespace}:stop:{suffix}",
    )
    permission = issue_action_permission(
        permission_id=f"permission:{namespace}:{suffix}",
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id,
        target=selected_target,
        action=action,
        epoch=context.epoch,
        decision_ref=context_ref,
        certificate_ref=certificate_ref,
        allowed=not blocked,
        reason_codes=("denied",) if blocked else ("policy_authorized",),
        issuer_id="governance:tck:permission",
        policy_ref="policy:tck:commit-action-v1",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=current_step,
        expires_at_step=expires_at_step,
        provenance=f"urn:pheroos:tck:{namespace}:permission:{suffix}",
        trace_event_id=f"trace:{namespace}:permission:{suffix}",
    )
    return stop, permission


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
    selected_context = context or scenario.context
    selected_replay = replay_state or scenario.replay_state
    selected_support_replay = (
        support_replay_state or scenario.support_replay_state
    )
    selected_inputs = tuple(candidate_inputs or scenario.candidate_inputs)
    selected_leases = tuple(leases or scenario.leases)
    selected_revocations = tuple(revocations)
    selected_stop = stop_resolution or scenario.stop_resolution
    selected_permission = permission or scenario.permission
    receipt_coordinates = tuple(
        (
            item.namespace.value,
            item.record_id,
            item.nonce,
            item.payload_fingerprint,
            item.target,
            item.candidate_id,
            item.epoch,
            item.principal_id,
        )
        for item in build_commit_replay_receipts(
            selected_inputs,
            selected_leases,
            selected_revocations,
        )
    )
    binding_coordinates = tuple(
        sorted(
            (
                item.candidate_id,
                item.claim_fingerprint,
                evidence_binding_fingerprint(item.evidence_binding),
            )
            for item in selected_inputs
        )
    )
    fixture_key = (
        f"assessment:{scenario.namespace}:{suffix}",
        step,
        commit_evaluation_context_fingerprint(selected_context),
        commit_replay_state_fingerprint(selected_replay),
        support_lease_replay_state_fingerprint(selected_support_replay),
        receipt_coordinates,
        binding_coordinates,
        stop_resolution_verification_fingerprint(selected_stop),
        action_permission_fingerprint(selected_permission),
    )
    with _REFERENCE_ASSESSMENT_FIXTURES_LOCK:
        cached = _REFERENCE_ASSESSMENT_FIXTURES.get(fixture_key)
        if cached is not None:
            return cached
    assessment = assess_optimal_commit(
        selected_context,
        manifest=scenario.manifest,
        candidate_inputs=selected_inputs,
        leases=selected_leases,
        revocations=selected_revocations,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=selected_replay,
        support_replay_state=selected_support_replay,
        stop_resolution=selected_stop,
        commit_permission=selected_permission,
        assessment_id=f"assessment:{scenario.namespace}:{suffix}",
        issuer_id="governance:tck:commit",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=step,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:assessment:{suffix}",
        trace_event_id=f"trace:{scenario.namespace}:assessment:{suffix}",
    )
    with _REFERENCE_ASSESSMENT_FIXTURES_LOCK:
        _REFERENCE_ASSESSMENT_FIXTURES[fixture_key] = assessment
    return assessment


def initialize_reference_window(
    scenario: ReferenceScenario,
) -> CommitWindowState:
    """Return the immutable historical initial window for one scenario."""

    with _REFERENCE_WINDOW_FIXTURES_LOCK:
        cached = _REFERENCE_WINDOW_FIXTURES.get(scenario.namespace)
        if cached is not None:
            return cached
        window = initialize_commit_window_state(
            commit_policy=scenario.policy,
            profile=scenario.profile,
            assurance=scenario.assurance,
            manifest_root=scenario.manifest_root,
            commit_policy_root=scenario.commit_policy_root,
            protocol_id=scenario.protocol_id,
            run_id=scenario.run_id,
            target=scenario.target,
            epoch=scenario.epoch,
            risk_assessment_root=(
                scenario.context.risk_assessment_fingerprint
            ),
            membership_root=scenario.context.membership_root,
            threshold_snapshot=scenario.threshold,
            current_step=4,
            issuer_id="governance:tck:window",
            authority=AuthorityLevel.GOVERNANCE,
            provenance=f"urn:pheroos:tck:{scenario.namespace}:window",
            trace_event_id=f"trace:{scenario.namespace}:window",
        )
        _REFERENCE_WINDOW_FIXTURES[scenario.namespace] = window
        return window


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
    """Append scoped authority inputs and issue a new immutable context head."""

    selected_support_replay = (
        support_replay_state or scenario.support_replay_state
    )
    replay = record_commit_replay_receipts(
        scenario.replay_state,
        current_step=current_step,
        receipts=build_commit_replay_receipts(candidate_inputs, leases),
    )
    context = issue_commit_evaluation_context(
        scenario.manifest,
        context_id=f"context:{scenario.namespace}:{suffix}",
        profile=scenario.profile,
        assurance=scenario.assurance,
        run_id=scenario.run_id,
        target=scenario.target,
        epoch=scenario.epoch,
        candidate_claims=scenario.claims,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=replay,
        support_replay_state=selected_support_replay,
        issuer_id="governance:tck:commit-context",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=current_step,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:context:{suffix}",
        trace_event_id=f"trace:{scenario.namespace}:context:{suffix}",
    )
    stop, permission = issue_reference_action_gates(
        scenario.namespace,
        context=context,
        action=CommitAction.COMMIT,
        blocked=False,
        current_step=current_step,
        expires_at_step=min(30, current_step + 10),
        suffix=f"context-{suffix}",
    )
    return context, replay, selected_support_replay, stop, permission


def build_reference_stable_commit(
    scenario: ReferenceScenario,
    *,
    variant: str = "stable",
) -> ReferenceStableCommit:
    fixture_key = (scenario.namespace, variant)
    with _REFERENCE_STABLE_FIXTURES_LOCK:
        cached = _REFERENCE_STABLE_FIXTURES.get(fixture_key)
        if cached is not None:
            return cached
    window = initialize_reference_window(scenario)
    required = scenario.threshold.stability_steps
    assessments: list[CommitAssessment] = []
    for offset in range(1, required + 1):
        step = 4 + offset
        assessment = assess_reference_scenario(
            scenario,
            step=step,
            suffix=f"{variant}:{step}",
        )
        assessments.append(assessment)
        window = advance_commit_window_state(
            window,
            assessment=assessment,
            commit_policy=scenario.policy,
            threshold_snapshot=scenario.threshold,
            current_step=step,
        )
    output_ref = output_payload_fingerprint(
        {
            "candidate_id": scenario.leader_id,
            "result": "declared-tck-output",
            "variant": variant,
        },
        profile=scenario.profile,
    )
    receipt = issue_local_commit_receipt(
        scenario.context,
        assessments[-1],
        window,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
        output_payload_fingerprint=output_ref,
        receipt_id=f"receipt:{scenario.namespace}:{variant}",
        issuer_id="governance:tck:receipt",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=window.last_evaluated_step,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:receipt:{variant}",
        trace_event_id=f"trace:{scenario.namespace}:receipt:{variant}",
    )
    stable = ReferenceStableCommit(
        scenario=scenario,
        assessments=tuple(assessments),
        window=window,
        output_fingerprint=output_ref,
        receipt=receipt,
    )
    with _REFERENCE_STABLE_FIXTURES_LOCK:
        _REFERENCE_STABLE_FIXTURES[fixture_key] = stable
    return stable


def build_reference_portable_commit(
    stable: ReferenceStableCommit,
    *,
    variant: str = "portable",
) -> ReferencePortableCommit:
    scenario = stable.scenario
    metadata = {
        "certificate_id": f"certificate:{scenario.namespace}:{variant}",
        "issuer_id": "governance:tck:portable-certificate",
        "authority": AuthorityLevel.GOVERNANCE,
        "issued_at_step": stable.window.last_evaluated_step,
        "provenance": (
            f"urn:pheroos:tck:{scenario.namespace}:certificate:{variant}"
        ),
        "trace_event_id": f"trace:{scenario.namespace}:certificate:{variant}",
    }
    body_root = evidence_commit_certificate_body_root(stable.receipt, **metadata)
    attestation_refs = (
        f"attestation:portable:{scenario.namespace}:{variant}:primary",
        f"attestation:portable:{scenario.namespace}:{variant}:backup",
    )
    trusted = {item: body_root for item in attestation_refs}
    certificate = issue_evidence_commit_certificate(
        stable.receipt,
        commit_policy=scenario.policy,
        issuer_attestation_refs=attestation_refs,
        trusted_issuer_attestations=trusted,
        **metadata,
    )
    return ReferencePortableCommit(
        stable=stable,
        certificate=certificate,
        trusted_issuer_attestations=trusted,
    )


def build_reference_distributed_commit(
    portable: ReferencePortableCommit,
    *,
    witness_count: int | None = None,
    variant: str = "distributed",
) -> ReferenceDistributedCommit:
    stable = portable.stable
    scenario = stable.scenario
    fixture_key = (scenario.namespace, variant, witness_count)
    with _REFERENCE_DISTRIBUTED_FIXTURES_LOCK:
        cached = _REFERENCE_DISTRIBUTED_FIXTURES.get(fixture_key)
        if cached is not None:
            return cached
    distributed = scenario.policy.distributed
    if distributed is None:
        raise ValueError("distributed fixture requires distributed commit policy")
    proposal = issue_distributed_commit_proposal(
        stable.receipt,
        portable.certificate,
        scenario.membership_snapshot,
        scenario.membership_state,
        commit_policy=scenario.policy,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        proposal_id=f"proposal:{scenario.namespace}:{variant}",
        proposed_at_step=stable.window.last_evaluated_step,
    )
    state = initialize_distributed_commit_state(
        scenario.membership_snapshot,
        scenario.membership_state,
        commit_policy=scenario.policy,
        current_step=stable.window.last_evaluated_step,
        issuer_id="governance:tck:distributed-state",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:distributed-state",
        trace_event_id=f"trace:{scenario.namespace}:distributed-state",
    )
    trusted_witnesses: dict[str, str] = {}
    verifications = tuple(
        issue_reference_witness(
            scenario,
            proposal,
            principal,
            index=index,
            variant=variant,
            trusted_witness_attestations=trusted_witnesses,
        )
        for index, principal in enumerate(scenario.principals, start=1)
    )
    selected_count = (
        distributed.witness_quorum if witness_count is None else witness_count
    )
    selected = verifications[:selected_count]
    state = record_witness_verifications(
        state,
        selected,
        current_step=stable.window.last_evaluated_step,
    )
    bundle = ReferenceDistributedCommit(
        portable=portable,
        proposal=proposal,
        state=state,
        verifications=verifications,
        trusted_witness_attestations=trusted_witnesses,
    )
    with _REFERENCE_DISTRIBUTED_FIXTURES_LOCK:
        _REFERENCE_DISTRIBUTED_FIXTURES[fixture_key] = bundle
    return bundle


def issue_reference_witness(
    scenario: ReferenceScenario,
    proposal: DistributedCommitProposal,
    principal: PrincipalVerification,
    *,
    index: int,
    variant: str,
    trusted_witness_attestations: dict[str, str],
) -> WitnessVerification:
    step = proposal.proposed_at_step
    witness = QuorumWitness(
        witness_version=QUORUM_WITNESS_VERSION,
        witness_id=(
            f"witness:{scenario.namespace}:{proposal.proposal_id}:{variant}:{index}"
        ),
        profile=proposal.profile,
        assurance=proposal.assurance,
        protocol_id=proposal.protocol_id,
        run_id=proposal.run_id,
        target=proposal.target,
        epoch=proposal.epoch,
        candidate_id=proposal.candidate_id,
        membership_root=proposal.membership_root,
        commit_value_root=proposal.commit_value_root,
        proposal_digest=proposal.proposal_digest,
        principal_id=principal.principal_id,
        principal_cluster_id=principal.cluster_id,
        failure_domain=principal.failure_domain,
        nonce=f"nonce:witness:{scenario.namespace}:{variant}:{index}",
        witnessed_at_step=step,
        expires_at_step=step + scenario.policy.distributed.witness_ttl_steps,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:witness:{variant}:{index}",
        trace_event_id=f"trace:{scenario.namespace}:witness:{variant}:{index}",
        attestation_ref=(
            f"attestation:witness:{scenario.namespace}:{variant}:{index}"
        ),
    )
    trusted_witness_attestations[witness.attestation_ref] = (
        quorum_witness_signing_root(witness)
    )
    return verify_quorum_witness(
        witness,
        proposal,
        principal,
        scenario.membership_snapshot,
        scenario.membership_state,
        commit_policy=scenario.policy,
        trusted_witness_attestations=trusted_witness_attestations,
        verification_id=(
            f"verification:{scenario.namespace}:{variant}:{index}"
        ),
        verifier_id="governance:tck:witness-verifier",
        authority=AuthorityLevel.GOVERNANCE,
        verified_at_step=step,
        provenance=(
            f"urn:pheroos:tck:{scenario.namespace}:witness-verification:"
            f"{variant}:{index}"
        ),
        trace_event_id=(
            f"trace:{scenario.namespace}:witness-verification:{variant}:{index}"
        ),
    )


def issue_reference_distributed_certificate(
    bundle: ReferenceDistributedCommit,
    *,
    witness_count: int,
    variant: str,
) -> DistributedCommitCertificate:
    scenario = bundle.portable.stable.scenario
    step = bundle.portable.stable.window.last_evaluated_step
    return assemble_portable_distributed_commit_certificate(
        bundle.proposal,
        portable_membership_snapshot_from_eligible(
            scenario.membership_snapshot
        ),
        bundle.verifications[:witness_count],
        commit_policy=scenario.policy,
        portable_certificate=bundle.portable.certificate,
        trusted_issuer_attestations=bundle.portable.trusted_issuer_attestations,
        trusted_witness_attestations=bundle.trusted_witness_attestations,
        certificate_id=f"distributed-certificate:{scenario.namespace}:{variant}",
        issuer_id="governance:tck:distributed-certificate",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=step,
        provenance=(
            f"urn:pheroos:tck:{scenario.namespace}:distributed-certificate:{variant}"
        ),
        trace_event_id=(
            f"trace:{scenario.namespace}:distributed-certificate:{variant}"
        ),
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
    """Build a valid portable peer proof for a different commit value."""

    stable = bundle.portable.stable
    scenario = stable.scenario
    step = stable.window.last_evaluated_step
    portable_payload = deepcopy(
        evidence_commit_certificate_payload(bundle.portable.certificate)
    )
    portable_payload[field_name] = field_value
    portable_payload["certificate_id"] = (
        f"certificate:{scenario.namespace}:{variant}"
    )
    portable_payload["local_receipt_ref"] = reference_fingerprint(
        f"remote-receipt:{scenario.namespace}:{variant}"
    )
    issuer_attestation_ref = (
        f"attestation:portable:{scenario.namespace}:{variant}"
    )
    portable_payload["issuer_attestation_refs"] = (
        issuer_attestation_ref,
    )
    portable_body = dict(portable_payload)
    portable_body.pop("issuer_attestation_refs")
    portable_body.pop("certificate_body_root")
    portable_body.pop("certificate_root")
    portable_body_root = commit_payload_fingerprint(
        portable_body,
        schema="pheroos-evidence-commit-certificate-body-v1",
        profile=scenario.profile,
    )
    portable_payload["certificate_body_root"] = portable_body_root
    portable_payload["certificate_root"] = commit_payload_fingerprint(
        {
            "certificate_body_root": portable_body_root,
            "issuer_attestation_refs": (issuer_attestation_ref,),
        },
        schema="pheroos-evidence-commit-certificate-envelope-v1",
        profile=scenario.profile,
    )
    portable = evidence_commit_certificate_from_payload(portable_payload)
    issuer_trust = {
        **bundle.portable.trusted_issuer_attestations,
        issuer_attestation_ref: portable_body_root,
    }

    proposal_payload = distributed_commit_proposal_payload(bundle.proposal)
    proposal_payload[field_name] = field_value
    proposal_payload["proposal_id"] = (
        f"proposal:{scenario.namespace}:{variant}"
    )
    proposal_payload["local_receipt_ref"] = portable.local_receipt_ref
    proposal_payload["portable_certificate_ref"] = (
        evidence_commit_certificate_fingerprint(portable)
    )
    value_payload = distributed_commit_value_payload(bundle.proposal)
    value_payload[field_name] = field_value
    proposal_payload["commit_value_root"] = distributed_commit_value_root(
        value_payload
    )
    proposal_body = dict(proposal_payload)
    proposal_body.pop("proposal_digest")
    proposal_payload["proposal_digest"] = commit_payload_fingerprint(
        proposal_body,
        schema=DISTRIBUTED_PROPOSAL_VERSION,
        profile=scenario.profile,
    )
    proposal = distributed_commit_proposal_from_payload(proposal_payload)

    distributed = scenario.policy.distributed
    if distributed is None:
        raise ValueError("semantic conflict requires distributed assurance")
    witness_trust = dict(bundle.trusted_witness_attestations)
    verifications: list[WitnessVerification] = []
    for index, principal in enumerate(
        scenario.principals[: distributed.witness_quorum],
        start=1,
    ):
        witness = QuorumWitness(
            witness_version=QUORUM_WITNESS_VERSION,
            witness_id=(
                f"witness:{scenario.namespace}:{variant}:{index}"
            ),
            profile=proposal.profile,
            assurance=proposal.assurance,
            protocol_id=proposal.protocol_id,
            run_id=proposal.run_id,
            target=proposal.target,
            epoch=proposal.epoch,
            candidate_id=proposal.candidate_id,
            membership_root=proposal.membership_root,
            commit_value_root=proposal.commit_value_root,
            proposal_digest=proposal.proposal_digest,
            principal_id=principal.principal_id,
            principal_cluster_id=principal.cluster_id,
            failure_domain=principal.failure_domain,
            nonce=f"nonce:{scenario.namespace}:{variant}:{index}",
            witnessed_at_step=step,
            expires_at_step=step + distributed.witness_ttl_steps,
            provenance=(
                f"urn:pheroos:tck:{scenario.namespace}:remote-witness:"
                f"{variant}:{index}"
            ),
            trace_event_id=(
                f"trace:{scenario.namespace}:remote-witness:{variant}:{index}"
            ),
            attestation_ref=(
                f"attestation:witness:{scenario.namespace}:{variant}:{index}"
            ),
        )
        signing_root = quorum_witness_signing_root(witness)
        witness_trust[witness.attestation_ref] = signing_root
        verifications.append(
            WitnessVerification(
                verification_version=WITNESS_VERIFICATION_VERSION,
                verification_id=(
                    f"verification:{scenario.namespace}:{variant}:{index}"
                ),
                witness=witness,
                witness_fingerprint=quorum_witness_fingerprint(witness),
                witness_signing_root=signing_root,
                principal_verification_ref=(
                    principal_verification_fingerprint(principal)
                ),
                verified_at_step=step,
                expires_at_step=step + distributed.witness_ttl_steps,
                verifier_id="governance:tck:remote-witness-verifier",
                authority=AuthorityLevel.GOVERNANCE,
                provenance=(
                    f"urn:pheroos:tck:{scenario.namespace}:"
                    f"remote-verification:{variant}:{index}"
                ),
                trace_event_id=(
                    f"trace:{scenario.namespace}:"
                    f"remote-verification:{variant}:{index}"
                ),
            )
        )
    certificate = assemble_portable_distributed_commit_certificate(
        proposal,
        portable_membership_snapshot_from_eligible(
            scenario.membership_snapshot
        ),
        tuple(reversed(verifications)),
        commit_policy=scenario.policy,
        portable_certificate=portable,
        trusted_issuer_attestations=issuer_trust,
        trusted_witness_attestations=witness_trust,
        certificate_id=(
            f"distributed-certificate:{scenario.namespace}:{variant}"
        ),
        issuer_id="governance:tck:remote-distributed-certificate",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=step,
        provenance=(
            f"urn:pheroos:tck:{scenario.namespace}:"
            f"remote-certificate:{variant}"
        ),
        trace_event_id=(
            f"trace:{scenario.namespace}:remote-certificate:{variant}"
        ),
    )
    return proposal, portable, issuer_trust, witness_trust, certificate


def replay_state_with_receipts(
    scenario: ReferenceScenario,
    receipts: Sequence[ReplayReceipt],
    *,
    step: int,
) -> CommitReplayState:
    return record_commit_replay_receipts(
        scenario.replay_state,
        current_step=step,
        receipts=tuple(receipts),
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
