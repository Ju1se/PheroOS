from __future__ import annotations

import gc
from collections.abc import Iterator
from dataclasses import replace
from itertools import count
from weakref import ref as weak_ref

import pytest

from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.errors import GovernanceError
from pheroos.governance.observation import (
    ObservationAttestation,
    ObservationPolarity,
    VerifiedObservation,
    verified_observation_fingerprint,
    verify_observation_attestation,
)
from pheroos.governance.principal import (
    PrincipalAttestation,
    PrincipalVerification,
    verify_principal_attestation,
)
from pheroos.governance.support_lease import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportLease,
    SupportLeaseProposal,
    SupportLeaseReplayState,
    SupportLeaseStatus,
    eligible_membership_epoch_state_fingerprint,
    eligible_membership_epoch_state_is_authoritative,
    eligible_membership_epoch_state_is_current,
    eligible_principal_snapshot_fingerprint,
    eligible_principal_snapshot_is_authoritative,
    eligible_principal_snapshot_matches,
    evaluate_support_leases,
    expire_support_lease,
    initialize_support_lease_replay_state,
    issue_eligible_principal_snapshot,
    issue_support_lease,
    revoke_support_lease,
    support_lease_is_authoritative,
    support_lease_replay_state_fingerprint,
    support_lease_replay_state_is_authoritative,
    support_lease_replay_state_is_current,
    support_lease_status,
    switch_support_lease,
)
from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_MODEL,
    COMMIT_POLICY_VERSION,
    COMMIT_WIRE_VERSION,
    REQUIRED_COMMIT_RESET_RULES,
    CertificatePolicy,
    CollectiveCommitPolicy,
    CommitAssurance,
    CommitWindowPolicy,
    EvidenceQualificationPolicy,
    RiskBandPolicy,
    SupportLeasePolicy,
    TerminalOutcomePolicy,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint


PROFILE = "pheroos-commit-integrity-v1"
MANIFEST_ROOT = "sha256:" + ("1" * 64)
CLAIM_ROOT = "sha256:" + ("2" * 64)
TARGET = "decision:review"
PROTOCOL_ID = "protocol:optimal"
RUN_ID = "run:lease"
EPOCH = 3
_AUTHORITY_SCOPE_SEQUENCE = count()


@pytest.fixture(autouse=True)
def _isolate_process_local_authority_scope() -> Iterator[None]:
    global PROTOCOL_ID, RUN_ID
    prior_protocol_id = PROTOCOL_ID
    prior_run_id = RUN_ID
    sequence = next(_AUTHORITY_SCOPE_SEQUENCE)
    PROTOCOL_ID = f"protocol:optimal:test:{sequence}"
    RUN_ID = f"run:lease:test:{sequence}"
    try:
        yield
    finally:
        PROTOCOL_ID = prior_protocol_id
        RUN_ID = prior_run_id


def commit_policy(*, target: str = TARGET) -> CollectiveCommitPolicy:
    evidence = EvidenceQualificationPolicy(
        numeric_scale=1_000_000,
        minimum_quality_ppm=500_000,
        minimum_relevance_ppm=500_000,
        positive_group_cap=1_000_000,
        counter_group_cap=1_000_000,
        counter_weight_ppm=1_000_000,
        minimum_positive_evidence=2_000_000,
        maximum_counterevidence=500_000,
        maximum_counterevidence_ratio_ppm=200_000,
        domain_contribution_floor=250_000,
        minimum_source_diversity=2,
        required_challenge_categories=["independent_replication"],
        observation_ttl_steps=30,
        require_provenance=True,
        require_trace=True,
    )
    support = SupportLeasePolicy(
        minimum_support_clusters=2,
        support_ratio_ppm=500_000,
        lease_ttl_steps=6,
        membership_mode="verified_snapshot_v1",
        switch_mode="revoke_then_issue_v1",
        equivocation_mode="exclude_conflicts_v1",
        evidence_reference_required=True,
        cluster_verification_required=True,
    )
    challenges = ["independent_replication"]
    bands = {
        "LOW": risk_band(2_000_000, 500_000, 200_000, 2, 500_000, 2, 250_000, 2, challenges, "evidence_bound"),
        "MODERATE": risk_band(2_500_000, 400_000, 150_000, 2, 600_000, 2, 300_000, 3, challenges, "evidence_bound"),
        "HIGH": risk_band(3_000_000, 300_000, 100_000, 3, 700_000, 3, 400_000, 4, [*challenges, "counter_search"], "certified"),
        "CRITICAL": risk_band(4_000_000, 200_000, 50_000, 4, 800_000, 4, 500_000, 5, [*challenges, "counter_search", "failure_domain_review"], "distributed"),
    }
    return CollectiveCommitPolicy(
        policy_version=COMMIT_POLICY_VERSION,
        model=COMMIT_MODEL,
        assurance="evidence_bound",
        target=target,
        evidence_qualification=evidence,
        support_lease=support,
        risk_bands=bands,
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


def risk_band(
    positive: int,
    counter: int,
    ratio: int,
    support: int,
    support_ratio: int,
    diversity: int,
    margin: int,
    stability: int,
    challenges: list[str],
    assurance: str,
) -> RiskBandPolicy:
    return RiskBandPolicy(
        minimum_positive_evidence=positive,
        maximum_counterevidence=counter,
        maximum_counterevidence_ratio_ppm=ratio,
        minimum_support_clusters=support,
        minimum_support_ratio_ppm=support_ratio,
        minimum_source_diversity=diversity,
        minimum_margin=margin,
        stability_steps=stability,
        required_challenge_categories=challenges,
        minimum_assurance=assurance,
        publishable_outcomes=["evidence_commit"],
        executable_outcomes=[],
    )


def policy_root(policy: CollectiveCommitPolicy) -> str:
    return commit_policy_fingerprint(policy, profile=PROFILE)


def principal(
    principal_id: str,
    cluster_id: str,
    *,
    index: int,
    policy: CollectiveCommitPolicy,
    target: str = TARGET,
    epoch: int = EPOCH,
) -> PrincipalVerification:
    attestation = PrincipalAttestation(
        principal_id=principal_id,
        attestation_ref=f"opaque:principal:{index}",
        method="external-verifier-v1",
        issuer_id="issuer:identity",
        issued_at_step=0,
        expires_at_step=40,
        provenance=f"urn:test:principal:{index}",
        nonce=f"nonce:principal:{index}",
        trace_event_id=f"trace:principal:{index}",
    )
    return verify_principal_attestation(
        attestation,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=policy_root(policy),
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=target,
        epoch=epoch,
        cluster_id=cluster_id,
        failure_domain=f"failure-domain:{index % 2}",
        verifier_id="governance:identity",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=1,
        provenance="urn:test:principal-verification",
        trace_event_id=f"trace:principal:verified:{index}",
    )


def membership(
    verifications: tuple[PrincipalVerification, ...],
    *,
    policy: CollectiveCommitPolicy,
    expires_at_step: int = 20,
    target: str = TARGET,
    epoch: int = EPOCH,
) -> tuple[EligiblePrincipalSnapshot, EligibleMembershipEpochState]:
    return issue_eligible_principal_snapshot(
        verifications,
        snapshot_id=f"membership:epoch:{epoch}",
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=policy_root(policy),
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=target,
        epoch=epoch,
        issuer_id="governance:membership",
        membership_method="verified-static-epoch-v1",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=2,
        expires_at_step=expires_at_step,
        provenance="urn:test:membership",
        trace_event_id="trace:membership:3",
    )


def replay_state() -> SupportLeaseReplayState:
    return initialize_support_lease_replay_state(
        profile=PROFILE,
        protocol_id=PROTOCOL_ID,
        issuer_id="governance:support",
        authority=AuthorityLevel.GOVERNANCE,
        initialized_at_step=0,
        provenance="urn:test:support-replay",
        trace_event_id="trace:support-replay",
    )


def observation(
    verification: PrincipalVerification,
    *,
    candidate_id: str,
    index: int,
    policy: CollectiveCommitPolicy,
    polarity: ObservationPolarity = ObservationPolarity.SUPPORT,
    claim_fingerprint: str = CLAIM_ROOT,
    target: str = TARGET,
    epoch: int = EPOCH,
) -> VerifiedObservation:
    attestation = ObservationAttestation(
        observation_id=f"observation:{index}",
        target=target,
        candidate_id=candidate_id,
        claim_fingerprint=claim_fingerprint,
        principal_id=verification.principal_id,
        polarity=polarity,
        independence_group=f"group:{index}",
        source_domain=f"source:{index}",
        payload_fingerprint="sha256:" + (f"{index:x}"[-1] * 64),
        reported_quality_ppm=800_000,
        reported_relevance_ppm=900_000,
        reported_materiality_ppm=700_000,
        reported_criticality_ppm=100_000,
        provenance=f"urn:test:observation:{index}",
        nonce=f"nonce:observation:{index}",
        observed_at_step=2,
        expires_at_step=15,
        trace_event_id=f"trace:observation:{index}",
    )
    return verify_observation_attestation(
        attestation,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=policy_root(policy),
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=target,
        candidate_id=candidate_id,
        claim_fingerprint=claim_fingerprint,
        epoch=epoch,
        principal_verification=verification,
        evidence_policy=policy.evidence_qualification,
        quality_ppm=800_000,
        relevance_ppm=900_000,
        materiality_ppm=700_000,
        criticality_ppm=100_000,
        verifier_id="governance:evidence",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=3,
        verification_provenance="urn:test:observation-verification",
        verification_trace_event_id=f"trace:observation:verified:{index}",
        prior_observations=(),
    )


def proposal(
    verification: PrincipalVerification,
    evidence: VerifiedObservation,
    *,
    candidate_id: str,
    index: int,
    policy: CollectiveCommitPolicy,
    proposed_at_step: int = 3,
    target: str = TARGET,
    epoch: int = EPOCH,
) -> SupportLeaseProposal:
    return SupportLeaseProposal(
        proposal_id=f"support-proposal:{index}",
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=policy_root(policy),
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=target,
        candidate_id=candidate_id,
        claim_fingerprint=evidence.claim_fingerprint,
        epoch=epoch,
        principal_id=verification.principal_id,
        positive_observation_fingerprints=(
            verified_observation_fingerprint(evidence),
        ),
        nonce=f"nonce:lease:{index}",
        proposed_at_step=proposed_at_step,
        provenance=f"urn:test:lease-proposal:{index}",
        trace_event_id=f"trace:lease-proposal:{index}",
    )


def issue_lease(
    verification: PrincipalVerification,
    evidence: VerifiedObservation,
    snapshot: EligiblePrincipalSnapshot,
    membership_state: EligibleMembershipEpochState,
    current_replay_state: SupportLeaseReplayState,
    *,
    candidate_id: str,
    index: int,
    current_step: int,
    policy: CollectiveCommitPolicy,
    prior_leases: tuple[SupportLease, ...] = (),
) -> tuple[SupportLease, SupportLeaseReplayState]:
    return issue_support_lease(
        proposal(
            verification,
            evidence,
            candidate_id=candidate_id,
            index=index,
            policy=policy,
            target=snapshot.target,
            epoch=snapshot.epoch,
        ),
        principal_verification=verification,
        membership_snapshot=snapshot,
        membership_epoch_state=membership_state,
        replay_state=current_replay_state,
        positive_observations=(evidence,),
        commit_policy=policy,
        lease_id=f"lease:{index}",
        issuer_id="governance:support",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=current_step,
        issuance_provenance=f"urn:test:lease:{index}",
        issuance_trace_event_id=f"trace:lease:{index}",
        prior_leases=prior_leases,
    )


def test_membership_collapses_sybil_principals_and_is_permutation_deterministic() -> None:
    policy = commit_policy()
    alpha = principal("principal:alpha", "cluster:a", index=1, policy=policy)
    alias = principal("principal:alpha-alias", "cluster:a", index=2, policy=policy)
    beta = principal("principal:beta", "cluster:b", index=3, policy=policy)

    first, first_state = membership((alpha, alias, beta), policy=policy)
    second, second_state = membership((beta, alias, alpha), policy=policy)

    assert len(first.eligible_clusters) == 2
    assert tuple(item.cluster_id for item in first.eligible_clusters) == (
        "cluster:a",
        "cluster:b",
    )
    assert tuple(
        item.principal_id for item in first.eligible_clusters[0].principals
    ) == ("principal:alpha", "principal:alpha-alias")
    assert first.membership_root == second.membership_root
    assert second is first
    assert second_state is first_state
    assert eligible_principal_snapshot_fingerprint(first) == (
        eligible_principal_snapshot_fingerprint(second)
    )
    assert eligible_principal_snapshot_is_authoritative(first)
    assert eligible_membership_epoch_state_is_authoritative(first_state)
    assert eligible_membership_epoch_state_is_current(first_state)
    assert first_state.snapshot_fingerprint == (
        eligible_principal_snapshot_fingerprint(first)
    )
    assert eligible_principal_snapshot_matches(
        first,
        epoch_state=first_state,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=policy_root(policy),
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=TARGET,
        epoch=EPOCH,
        current_step=19,
    )
    assert not eligible_principal_snapshot_matches(
        first,
        epoch_state=first_state,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root="sha256:" + ("f" * 64),
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=TARGET,
        epoch=EPOCH,
        current_step=19,
    )
    assert not eligible_principal_snapshot_matches(
        first,
        epoch_state=first_state,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=policy_root(policy),
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=TARGET,
        epoch=EPOCH,
        current_step=20,
    )

    object.__setattr__(first, "membership_root", "sha256:" + ("e" * 64))
    assert not eligible_principal_snapshot_is_authoritative(first)
    assert not eligible_principal_snapshot_matches(
        first,
        epoch_state=first_state,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=policy_root(policy),
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=TARGET,
        epoch=EPOCH,
        current_step=19,
    )


def test_membership_rejects_forged_duplicate_and_short_lived_identity() -> None:
    policy = commit_policy()
    alpha = principal("principal:alpha", "cluster:a", index=1, policy=policy)
    forged = replace(alpha, cluster_id="cluster:forged")

    with pytest.raises(GovernanceError, match="forged"):
        membership((forged,), policy=policy)
    with pytest.raises(GovernanceError, match="repeats a principal"):
        membership((alpha, alpha), policy=policy)
    with pytest.raises(GovernanceError, match="outlive"):
        membership((alpha,), policy=policy, expires_at_step=41)


def test_membership_epoch_rejects_conflicting_duplicate_initialization() -> None:
    policy = commit_policy()
    alpha = principal("principal:alpha", "cluster:a", index=1, policy=policy)
    beta = principal("principal:beta", "cluster:b", index=2, policy=policy)
    snapshot, state = membership((alpha,), policy=policy)

    identical_snapshot, identical_state = membership((alpha,), policy=policy)
    assert identical_snapshot is snapshot
    assert identical_state is state
    with pytest.raises(GovernanceError, match="conflicting immutable snapshot"):
        membership((beta,), policy=policy)

    forged_state = replace(state, provenance="urn:test:membership:forged")
    assert not eligible_membership_epoch_state_is_authoritative(forged_state)
    assert not eligible_membership_epoch_state_is_current(forged_state)


def test_replay_state_duplicate_initialization_and_tampering_fail_closed() -> None:
    initial = replay_state()
    identical = replay_state()

    assert identical is initial
    assert support_lease_replay_state_is_authoritative(initial)
    assert support_lease_replay_state_is_current(initial)
    assert support_lease_replay_state_fingerprint(initial) == (
        support_lease_replay_state_fingerprint(identical)
    )

    forged = replace(initial, provenance="urn:test:support-replay:forged")
    assert not support_lease_replay_state_is_authoritative(forged)
    assert not support_lease_replay_state_is_current(forged)
    with pytest.raises(GovernanceError, match="different immutable base"):
        initialize_support_lease_replay_state(
            profile=PROFILE,
            protocol_id=PROTOCOL_ID,
            issuer_id="governance:support",
            authority=AuthorityLevel.GOVERNANCE,
            initialized_at_step=0,
            provenance="urn:test:support-replay:conflict",
            trace_event_id="trace:support-replay",
        )


def test_support_lease_requires_authoritative_positive_bound_evidence_and_exact_ttl() -> None:
    policy = commit_policy()
    alpha = principal("principal:alpha", "cluster:a", index=1, policy=policy)
    snapshot, membership_state = membership((alpha,), policy=policy)
    current_replay_state = replay_state()
    positive = observation(alpha, candidate_id="candidate:a", index=1, policy=policy)
    lease, current_replay_state = issue_lease(
        alpha,
        positive,
        snapshot,
        membership_state,
        current_replay_state,
        candidate_id="candidate:a",
        index=1,
        current_step=4,
        policy=policy,
    )

    assert support_lease_is_authoritative(lease)
    assert lease.expires_at_step == 10
    assert lease.principal_cluster_id == "cluster:a"
    assert lease.membership_root == snapshot.membership_root

    contradict = observation(
        alpha,
        candidate_id="candidate:a",
        index=2,
        policy=policy,
        polarity=ObservationPolarity.CONTRADICT,
    )
    bad_proposal = proposal(
        alpha,
        contradict,
        candidate_id="candidate:a",
        index=2,
        policy=policy,
    )
    with pytest.raises(GovernanceError, match="positive"):
        issue_support_lease(
            bad_proposal,
            principal_verification=alpha,
            membership_snapshot=snapshot,
            membership_epoch_state=membership_state,
            replay_state=current_replay_state,
            positive_observations=(contradict,),
            commit_policy=policy,
            lease_id="lease:2",
            issuer_id="governance:support",
            authority=AuthorityLevel.GOVERNANCE,
            current_step=4,
            issuance_provenance="urn:test:lease:2",
            issuance_trace_event_id="trace:lease:2",
        )

    replayed, replayed_state = issue_lease(
        alpha,
        positive,
        snapshot,
        membership_state,
        current_replay_state,
        candidate_id="candidate:a",
        index=1,
        current_step=5,
        policy=policy,
        prior_leases=(lease,),
    )
    assert replayed is lease
    assert replayed_state is current_replay_state

    forged = replace(lease, principal_cluster_id="cluster:forged")
    assert not support_lease_is_authoritative(forged)
    forged_receipt = replace(
        lease,
        replay_receipt_fingerprint="sha256:" + ("f" * 64),
    )
    assert not support_lease_is_authoritative(forged_receipt)
    object.__setattr__(lease, "candidate_id", "candidate:tampered")
    assert not support_lease_is_authoritative(lease)


def test_authoritative_replay_state_rejects_cross_scope_id_and_nonce_collisions() -> None:
    policy = commit_policy()
    alpha = principal("principal:alpha", "cluster:a", index=1, policy=policy)
    snapshot, membership_state = membership((alpha,), policy=policy)
    current_replay_state = replay_state()
    evidence = observation(
        alpha,
        candidate_id="candidate:a",
        index=1,
        policy=policy,
    )
    lease, current_replay_state = issue_lease(
        alpha,
        evidence,
        snapshot,
        membership_state,
        current_replay_state,
        candidate_id="candidate:a",
        index=1,
        current_step=4,
        policy=policy,
    )

    alternate_target = "decision:alternate"
    alternate_epoch = EPOCH + 1
    alternate_policy = commit_policy(target=alternate_target)
    beta = principal(
        "principal:beta",
        "cluster:b",
        index=2,
        policy=alternate_policy,
        target=alternate_target,
        epoch=alternate_epoch,
    )
    alternate_snapshot, alternate_membership_state = membership(
        (beta,),
        policy=alternate_policy,
        target=alternate_target,
        epoch=alternate_epoch,
    )
    alternate_evidence = observation(
        beta,
        candidate_id="candidate:b",
        index=2,
        policy=alternate_policy,
        target=alternate_target,
        epoch=alternate_epoch,
    )
    alternate_proposal = proposal(
        beta,
        alternate_evidence,
        candidate_id="candidate:b",
        index=2,
        policy=alternate_policy,
        target=alternate_target,
        epoch=alternate_epoch,
    )

    common_arguments = {
        "principal_verification": beta,
        "membership_snapshot": alternate_snapshot,
        "membership_epoch_state": alternate_membership_state,
        "replay_state": current_replay_state,
        "positive_observations": (alternate_evidence,),
        "commit_policy": alternate_policy,
        "issuer_id": "governance:support",
        "authority": AuthorityLevel.GOVERNANCE,
        "current_step": 5,
        "issuance_provenance": "urn:test:lease:alternate",
        "issuance_trace_event_id": "trace:lease:alternate",
        "prior_leases": (),
    }
    with pytest.raises(GovernanceError, match="replay is a safety violation"):
        issue_support_lease(
            alternate_proposal,
            lease_id=lease.lease_id,
            **common_arguments,
        )
    with pytest.raises(GovernanceError, match="replay is a safety violation"):
        issue_support_lease(
            replace(alternate_proposal, nonce=lease.nonce),
            lease_id="lease:alternate",
            **common_arguments,
        )


def test_stale_replay_state_cannot_fork_even_with_empty_caller_history() -> None:
    policy = commit_policy()
    alpha = principal("principal:alpha", "cluster:a", index=1, policy=policy)
    snapshot, membership_state = membership((alpha,), policy=policy)
    initial_replay_state = replay_state()
    evidence_a = observation(
        alpha,
        candidate_id="candidate:a",
        index=1,
        policy=policy,
    )
    _, current_replay_state = issue_lease(
        alpha,
        evidence_a,
        snapshot,
        membership_state,
        initial_replay_state,
        candidate_id="candidate:a",
        index=1,
        current_step=4,
        policy=policy,
    )
    evidence_b = observation(
        alpha,
        candidate_id="candidate:b",
        index=2,
        policy=policy,
    )

    with pytest.raises(GovernanceError, match="stale or would fork"):
        issue_lease(
            alpha,
            evidence_b,
            snapshot,
            membership_state,
            initial_replay_state,
            candidate_id="candidate:b",
            index=2,
            current_step=5,
            policy=policy,
            prior_leases=(),
        )
    assert support_lease_replay_state_is_current(current_replay_state)


def test_membership_and_replay_authority_survive_gc_for_idempotent_retry() -> None:
    policy = commit_policy()
    alpha = principal("principal:alpha", "cluster:a", index=1, policy=policy)
    snapshot, membership_state = membership((alpha,), policy=policy)
    snapshot_reference = weak_ref(snapshot)
    membership_state_reference = weak_ref(membership_state)
    del snapshot, membership_state
    gc.collect()

    resumed_snapshot, resumed_membership_state = membership(
        (alpha,),
        policy=policy,
    )
    assert resumed_snapshot is snapshot_reference()
    assert resumed_membership_state is membership_state_reference()

    evidence = observation(
        alpha,
        candidate_id="candidate:a",
        index=1,
        policy=policy,
    )
    initial_replay_state = replay_state()
    lease, current_replay_state = issue_lease(
        alpha,
        evidence,
        resumed_snapshot,
        resumed_membership_state,
        initial_replay_state,
        candidate_id="candidate:a",
        index=1,
        current_step=4,
        policy=policy,
    )
    lease_reference = weak_ref(lease)
    replay_state_reference = weak_ref(current_replay_state)
    del initial_replay_state, lease, current_replay_state
    gc.collect()

    resumed_replay_state = replay_state()
    retried_lease, retried_replay_state = issue_lease(
        alpha,
        evidence,
        resumed_snapshot,
        resumed_membership_state,
        resumed_replay_state,
        candidate_id="candidate:a",
        index=1,
        current_step=5,
        policy=policy,
        prior_leases=(),
    )
    assert retried_lease is lease_reference()
    assert retried_replay_state is replay_state_reference()
    assert retried_replay_state is resumed_replay_state


def test_support_cluster_collapse_and_ratio_are_not_sybil_amplified() -> None:
    policy = commit_policy()
    alpha = principal("principal:alpha", "cluster:a", index=1, policy=policy)
    alias = principal("principal:alpha-alias", "cluster:a", index=2, policy=policy)
    beta = principal("principal:beta", "cluster:b", index=3, policy=policy)
    snapshot, membership_state = membership((alpha, alias, beta), policy=policy)
    current_replay_state = replay_state()
    alpha_evidence = observation(
        alpha,
        candidate_id="candidate:a",
        index=1,
        policy=policy,
    )
    alias_evidence = observation(
        alias,
        candidate_id="candidate:a",
        index=2,
        policy=policy,
    )
    beta_evidence = observation(
        beta,
        candidate_id="candidate:a",
        index=3,
        policy=policy,
    )
    alpha_lease, current_replay_state = issue_lease(
        alpha,
        alpha_evidence,
        snapshot,
        membership_state,
        current_replay_state,
        candidate_id="candidate:a",
        index=1,
        current_step=4,
        policy=policy,
    )
    alias_lease, current_replay_state = issue_lease(
        alias,
        alias_evidence,
        snapshot,
        membership_state,
        current_replay_state,
        candidate_id="candidate:a",
        index=2,
        current_step=4,
        policy=policy,
        prior_leases=(alpha_lease,),
    )

    one_cluster = evaluate_support_leases(
        (alias_lease, alpha_lease),
        revocations=(),
        membership_snapshot=snapshot,
        membership_epoch_state=membership_state,
        replay_state=current_replay_state,
        commit_policy=policy,
        candidate_id="candidate:a",
        claim_fingerprint=CLAIM_ROOT,
        current_step=5,
    )
    assert one_cluster.eligible_cluster_count == 2
    assert one_cluster.active_support_cluster_count == 1
    assert one_cluster.support_ratio_ppm == 500_000
    assert one_cluster.policy_support_threshold_clusters == 2
    assert one_cluster.policy_support_met is False

    beta_lease, current_replay_state = issue_lease(
        beta,
        beta_evidence,
        snapshot,
        membership_state,
        current_replay_state,
        candidate_id="candidate:a",
        index=3,
        current_step=4,
        policy=policy,
        prior_leases=(alpha_lease, alias_lease),
    )
    full = evaluate_support_leases(
        (beta_lease, alpha_lease, alias_lease),
        revocations=(),
        membership_snapshot=snapshot,
        membership_epoch_state=membership_state,
        replay_state=current_replay_state,
        commit_policy=policy,
        candidate_id="candidate:a",
        claim_fingerprint=CLAIM_ROOT,
        current_step=5,
    )
    assert full.active_support_cluster_count == 2
    assert full.support_ratio_ppm == 1_000_000
    assert full.policy_support_met is True


def test_cross_candidate_overlap_excludes_all_conflicts_deterministically() -> None:
    policy = commit_policy()
    alpha = principal("principal:alpha", "cluster:a", index=1, policy=policy)
    beta = principal("principal:beta", "cluster:b", index=2, policy=policy)
    snapshot, membership_state = membership((alpha, beta), policy=policy)
    current_replay_state = replay_state()
    evidence_a = observation(
        alpha,
        candidate_id="candidate:a",
        index=1,
        policy=policy,
    )
    evidence_b = observation(
        alpha,
        candidate_id="candidate:b",
        index=2,
        policy=policy,
    )
    lease_a, current_replay_state = issue_lease(
        alpha,
        evidence_a,
        snapshot,
        membership_state,
        current_replay_state,
        candidate_id="candidate:a",
        index=1,
        current_step=4,
        policy=policy,
    )
    lease_b, current_replay_state = issue_lease(
        alpha,
        evidence_b,
        snapshot,
        membership_state,
        current_replay_state,
        candidate_id="candidate:b",
        index=2,
        current_step=5,
        policy=policy,
        prior_leases=(lease_a,),
    )

    with pytest.raises(GovernanceError, match="lease set is incomplete"):
        evaluate_support_leases(
            (lease_a,),
            revocations=(),
            membership_snapshot=snapshot,
            membership_epoch_state=membership_state,
            replay_state=current_replay_state,
            commit_policy=policy,
            candidate_id="candidate:a",
            claim_fingerprint=CLAIM_ROOT,
            current_step=6,
        )

    first = evaluate_support_leases(
        (lease_a, lease_b),
        revocations=(),
        membership_snapshot=snapshot,
        membership_epoch_state=membership_state,
        replay_state=current_replay_state,
        commit_policy=policy,
        candidate_id="candidate:a",
        claim_fingerprint=CLAIM_ROOT,
        current_step=6,
    )
    second = evaluate_support_leases(
        (lease_b, lease_a),
        revocations=(),
        membership_snapshot=snapshot,
        membership_epoch_state=membership_state,
        replay_state=current_replay_state,
        commit_policy=policy,
        candidate_id="candidate:a",
        claim_fingerprint=CLAIM_ROOT,
        current_step=6,
    )

    assert first.active_support_cluster_count == 0
    assert len(first.equivocation_findings) == 1
    finding = first.equivocation_findings[0]
    assert set(finding.conflicting_candidates) == {"candidate:a", "candidate:b"}
    assert len(finding.conflicting_lease_fingerprints) == 2
    assert finding.first_overlap_step == 5
    assert first.lease_root == second.lease_root
    assert first.equivocation_findings == second.equivocation_findings


def test_same_candidate_conflicting_claims_fail_closed() -> None:
    policy = commit_policy()
    alpha = principal("principal:alpha", "cluster:a", index=1, policy=policy)
    snapshot, membership_state = membership((alpha,), policy=policy)
    current_replay_state = replay_state()
    alternate_claim = "sha256:" + ("a" * 64)
    evidence_a = observation(
        alpha,
        candidate_id="candidate:a",
        index=1,
        policy=policy,
    )
    evidence_b = observation(
        alpha,
        candidate_id="candidate:a",
        index=2,
        policy=policy,
        claim_fingerprint=alternate_claim,
    )
    lease_a, current_replay_state = issue_lease(
        alpha,
        evidence_a,
        snapshot,
        membership_state,
        current_replay_state,
        candidate_id="candidate:a",
        index=1,
        current_step=4,
        policy=policy,
    )
    lease_b, current_replay_state = issue_lease(
        alpha,
        evidence_b,
        snapshot,
        membership_state,
        current_replay_state,
        candidate_id="candidate:a",
        index=2,
        current_step=5,
        policy=policy,
        prior_leases=(),
    )

    with pytest.raises(GovernanceError, match="conflicting claims"):
        evaluate_support_leases(
            (lease_a, lease_b),
            revocations=(),
            membership_snapshot=snapshot,
            membership_epoch_state=membership_state,
            replay_state=current_replay_state,
            commit_policy=policy,
            candidate_id="candidate:a",
            claim_fingerprint=CLAIM_ROOT,
            current_step=6,
        )


def test_revoke_switch_boundary_is_not_equivocation_and_expiry_is_automatic() -> None:
    policy = commit_policy()
    alpha = principal("principal:alpha", "cluster:a", index=1, policy=policy)
    beta = principal("principal:beta", "cluster:b", index=2, policy=policy)
    snapshot, membership_state = membership((alpha, beta), policy=policy)
    current_replay_state = replay_state()
    evidence_a = observation(
        alpha,
        candidate_id="candidate:a",
        index=1,
        policy=policy,
    )
    evidence_b = observation(
        alpha,
        candidate_id="candidate:b",
        index=2,
        policy=policy,
    )
    lease_a, current_replay_state = issue_lease(
        alpha,
        evidence_a,
        snapshot,
        membership_state,
        current_replay_state,
        candidate_id="candidate:a",
        index=1,
        current_step=4,
        policy=policy,
    )
    switch, current_replay_state = switch_support_lease(
        lease_a,
        proposal(
            alpha,
            evidence_b,
            candidate_id="candidate:b",
            index=2,
            policy=policy,
        ),
        principal_verification=alpha,
        membership_snapshot=snapshot,
        membership_epoch_state=membership_state,
        replay_state=current_replay_state,
        positive_observations=(evidence_b,),
        commit_policy=policy,
        revocation_id="revocation:1",
        revocation_reason_codes=("candidate_switch",),
        lease_id="lease:2",
        issuer_id="governance:support",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=5,
        revocation_provenance="urn:test:revocation:1",
        revocation_trace_event_id="trace:revocation:1",
        issuance_provenance="urn:test:lease:2",
        issuance_trace_event_id="trace:lease:2",
        prior_leases=(lease_a,),
    )
    assert support_lease_status(
        lease_a,
        current_step=5,
        revocations=(switch.revocation,),
    ) is SupportLeaseStatus.REVOKED
    assert support_lease_status(
        switch.lease,
        current_step=5,
    ) is SupportLeaseStatus.ACTIVE

    result = evaluate_support_leases(
        (lease_a, switch.lease),
        revocations=(switch.revocation,),
        membership_snapshot=snapshot,
        membership_epoch_state=membership_state,
        replay_state=current_replay_state,
        commit_policy=policy,
        candidate_id="candidate:b",
        claim_fingerprint=CLAIM_ROOT,
        current_step=6,
    )
    assert result.active_support_cluster_count == 1
    assert result.equivocation_findings == ()

    expiration = expire_support_lease(switch.lease, current_step=11)
    assert expiration.expired_at_step == 11
    assert support_lease_status(
        switch.lease,
        current_step=11,
    ) is SupportLeaseStatus.EXPIRED
    with pytest.raises(GovernanceError, match="has not expired"):
        expire_support_lease(switch.lease, current_step=10)


def test_stale_membership_fails_closed() -> None:
    policy = commit_policy()
    alpha = principal("principal:alpha", "cluster:a", index=1, policy=policy)
    stale, stale_state = membership((alpha,), policy=policy, expires_at_step=10)
    current_replay_state = replay_state()
    evidence = observation(
        alpha,
        candidate_id="candidate:a",
        index=1,
        policy=policy,
    )
    with pytest.raises(GovernanceError, match="membership"):
        issue_lease(
            alpha,
            evidence,
            stale,
            stale_state,
            current_replay_state,
            candidate_id="candidate:a",
            index=1,
            current_step=10,
            policy=policy,
        )


def test_empty_membership_is_policy_incomplete() -> None:
    policy = commit_policy()
    empty, empty_state = membership((), policy=policy)
    current_replay_state = replay_state()
    with pytest.raises(GovernanceError, match="policy is incomplete"):
        evaluate_support_leases(
            (),
            revocations=(),
            membership_snapshot=empty,
            membership_epoch_state=empty_state,
            replay_state=current_replay_state,
            commit_policy=policy,
            candidate_id="candidate:a",
            claim_fingerprint=CLAIM_ROOT,
            current_step=5,
        )


def test_cross_policy_root_membership_fails_closed() -> None:
    policy = commit_policy()
    alpha = principal("principal:alpha", "cluster:a", index=1, policy=policy)
    other_policy = replace(
        policy,
        support_lease=replace(policy.support_lease, lease_ttl_steps=7),
    )
    snapshot, membership_state = membership((alpha,), policy=policy)
    current_replay_state = replay_state()
    with pytest.raises(GovernanceError, match="policy root"):
        evaluate_support_leases(
            (),
            revocations=(),
            membership_snapshot=snapshot,
            membership_epoch_state=membership_state,
            replay_state=current_replay_state,
            commit_policy=other_policy,
            candidate_id="candidate:a",
            claim_fingerprint=CLAIM_ROOT,
            current_step=5,
        )
