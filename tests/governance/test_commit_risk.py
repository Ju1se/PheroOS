from __future__ import annotations

import gc
from dataclasses import replace
from itertools import count

import pytest

from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.errors import GovernanceError
from pheroos.governance.risk import (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
    RiskBand,
    commit_threshold_snapshot_is_authoritative,
    commit_threshold_snapshot_matches,
    commit_threshold_transition_requires_reset,
    initialize_risk_assessment_chain,
    issue_commit_threshold_snapshot,
    issue_risk_assessment,
    risk_assessment_fingerprint,
    risk_assessment_chain_state_is_authoritative,
    risk_assessment_chain_state_is_current,
    risk_assessment_chain_state_payload,
    risk_assessment_is_authoritative,
    risk_assessment_is_latest,
    risk_assessment_matches,
    risk_policy_root,
    risk_transition_is_monotonic,
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
INPUT_A = "sha256:" + ("2" * 64)
INPUT_B = "sha256:" + ("3" * 64)
TARGET = "decision:review"
PROTOCOL_ID = "protocol:optimal"
RUN_ID = "run:risk"
EPOCH = 7
_RUN_SEQUENCE = count(1)


@pytest.fixture(autouse=True)
def unique_risk_run_scope():
    global RUN_ID
    previous = RUN_ID
    RUN_ID = f"run:risk:test:{next(_RUN_SEQUENCE)}"
    try:
        yield
    finally:
        RUN_ID = previous


def band(
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
    *,
    publish: list[str] | None = None,
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
        publishable_outcomes=(
            ["evidence_commit"] if publish is None else publish
        ),
        executable_outcomes=[],
    )


def policy(*, low_positive: int = 2_000_000) -> CollectiveCommitPolicy:
    challenges = ["independent_replication"]
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
            minimum_positive_evidence=2_000_000,
            maximum_counterevidence=500_000,
            maximum_counterevidence_ratio_ppm=200_000,
            domain_contribution_floor=250_000,
            minimum_source_diversity=2,
            required_challenge_categories=challenges,
            observation_ttl_steps=8,
            require_provenance=True,
            require_trace=True,
        ),
        support_lease=SupportLeasePolicy(
            minimum_support_clusters=2,
            support_ratio_ppm=500_000,
            lease_ttl_steps=6,
            membership_mode="verified_snapshot_v1",
            switch_mode="revoke_then_issue_v1",
            equivocation_mode="exclude_conflicts_v1",
            evidence_reference_required=True,
            cluster_verification_required=True,
        ),
        risk_bands={
            "LOW": band(low_positive, 500_000, 200_000, 2, 500_000, 2, 250_000, 2, challenges, "evidence_bound"),
            "MODERATE": band(max(low_positive, 2_500_000), 400_000, 150_000, 2, 600_000, 2, 300_000, 3, challenges, "evidence_bound"),
            "HIGH": band(max(low_positive, 3_000_000), 300_000, 100_000, 3, 700_000, 3, 400_000, 4, [*challenges, "counter_search"], "certified"),
            "CRITICAL": band(max(low_positive, 4_000_000), 200_000, 50_000, 4, 800_000, 4, 500_000, 5, [*challenges, "counter_search", "failure_domain_review"], "distributed"),
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


def issue_assessment(
    commit_policy: CollectiveCommitPolicy,
    risk_band: RiskBand,
    *,
    issued_at_step: int = 2,
    expires_at_step: int = 20,
    previous: RiskAssessment | None = None,
    assessment_id: str = "risk:1",
    inputs: tuple[str, ...] = (INPUT_A,),
    chain_state: RiskAssessmentChainState | None = None,
    binding_run_id: str | None = None,
) -> tuple[RiskAssessment, RiskAssessmentChainState]:
    if chain_state is None:
        chain_state = initialize_chain(
            commit_policy,
            expires_at_step=expires_at_step,
        )
    return issue_risk_assessment(
        chain_state,
        assessment_id=assessment_id,
        risk_band=risk_band,
        risk_input_fingerprints=inputs,
        rationale_codes=("governance_risk_classification",),
        assessment_method="declared-risk-matrix-v1",
        commit_policy=commit_policy,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=commit_policy_fingerprint(
            commit_policy,
            profile=PROFILE,
        ),
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID if binding_run_id is None else binding_run_id,
        target=TARGET,
        epoch=EPOCH,
        issuer_id="governance:risk",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=issued_at_step,
        expires_at_step=expires_at_step,
        provenance=f"urn:test:{assessment_id}",
        trace_event_id=f"trace:{assessment_id}",
        previous_assessment=previous,
    )


def initialize_chain(
    commit_policy: CollectiveCommitPolicy,
    *,
    initialized_at_step: int = 1,
    expires_at_step: int = 20,
) -> RiskAssessmentChainState:
    return initialize_risk_assessment_chain(
        commit_policy=commit_policy,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=commit_policy_fingerprint(
            commit_policy,
            profile=PROFILE,
        ),
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=TARGET,
        epoch=EPOCH,
        issuer_id="governance:risk-chain",
        authority=AuthorityLevel.GOVERNANCE,
        initialized_at_step=initialized_at_step,
        expires_at_step=expires_at_step,
        provenance="urn:test:risk-chain",
        trace_event_id="trace:risk-chain",
    )


def threshold(
    assessment: RiskAssessment,
    chain_state: RiskAssessmentChainState,
    commit_policy: CollectiveCommitPolicy,
    *,
    threshold_id: str = "threshold:1",
) -> CommitThresholdSnapshot:
    return issue_commit_threshold_snapshot(
        assessment,
        chain_state=chain_state,
        threshold_id=threshold_id,
        commit_policy=commit_policy,
        issuer_id="governance:threshold",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=assessment.issued_at_step,
        provenance=f"urn:test:{threshold_id}",
        trace_event_id=f"trace:{threshold_id}",
    )


def test_risk_and_threshold_are_governance_issued_bound_fresh_and_tamper_evident() -> None:
    commit_policy = policy()
    assessment, chain_state = issue_assessment(commit_policy, RiskBand.LOW)
    snapshot = threshold(assessment, chain_state, commit_policy)

    assert risk_assessment_is_authoritative(assessment)
    assert risk_assessment_chain_state_is_authoritative(chain_state)
    assert risk_assessment_chain_state_is_current(chain_state)
    assert risk_assessment_is_latest(assessment, chain_state=chain_state)
    assert commit_threshold_snapshot_is_authoritative(snapshot)
    assert assessment.risk_policy_root == risk_policy_root(
        commit_policy,
        profile=PROFILE,
    )
    assert risk_assessment_matches(
        assessment,
        chain_state=chain_state,
        commit_policy=commit_policy,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=commit_policy_fingerprint(
            commit_policy,
            profile=PROFILE,
        ),
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=TARGET,
        epoch=EPOCH,
        current_step=19,
    )
    assert not risk_assessment_matches(
        assessment,
        chain_state=chain_state,
        commit_policy=commit_policy,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=commit_policy_fingerprint(
            commit_policy,
            profile=PROFILE,
        ),
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=TARGET,
        epoch=EPOCH,
        current_step=20,
    )
    assert commit_threshold_snapshot_matches(
        snapshot,
        assessment=assessment,
        chain_state=chain_state,
        commit_policy=commit_policy,
        current_step=19,
    )

    forged_assessment = replace(assessment, risk_band=RiskBand.CRITICAL)
    forged_threshold = replace(snapshot, minimum_positive_evidence=1)
    assert not risk_assessment_is_authoritative(forged_assessment)
    assert not commit_threshold_snapshot_is_authoritative(forged_threshold)

    object.__setattr__(snapshot, "minimum_support_clusters", 1)
    assert not commit_threshold_snapshot_is_authoritative(snapshot)


def test_threshold_is_derived_exactly_from_selected_protocol_band() -> None:
    commit_policy = policy()
    assessment, chain_state = issue_assessment(commit_policy, RiskBand.HIGH)
    snapshot = threshold(assessment, chain_state, commit_policy)
    declared = commit_policy.risk_bands["HIGH"]

    assert snapshot.risk_band is RiskBand.HIGH
    assert snapshot.minimum_positive_evidence == declared.minimum_positive_evidence
    assert snapshot.maximum_counterevidence == declared.maximum_counterevidence
    assert (
        snapshot.maximum_counterevidence_ratio_ppm
        == declared.maximum_counterevidence_ratio_ppm
    )
    assert snapshot.minimum_support_clusters == declared.minimum_support_clusters
    assert snapshot.minimum_support_ratio_ppm == declared.minimum_support_ratio_ppm
    assert snapshot.minimum_source_diversity == declared.minimum_source_diversity
    assert snapshot.minimum_margin == declared.minimum_margin
    assert snapshot.stability_steps == declared.stability_steps
    assert set(snapshot.required_challenge_categories) == set(
        declared.required_challenge_categories
    )
    assert snapshot.minimum_assurance is CommitAssurance.CERTIFIED
    assert set(snapshot.publishable_outcomes) == set(declared.publishable_outcomes)
    assert set(snapshot.executable_outcomes) == set(declared.executable_outcomes)


def test_risk_can_only_hold_or_increase_and_increase_requires_window_reset() -> None:
    commit_policy = policy()
    low, low_state = issue_assessment(commit_policy, RiskBand.LOW)
    high, high_state = issue_assessment(
        commit_policy,
        RiskBand.HIGH,
        issued_at_step=3,
        previous=low,
        assessment_id="risk:2",
        inputs=(INPUT_A, INPUT_B),
        chain_state=low_state,
    )
    assert high.previous_assessment_fingerprint == risk_assessment_fingerprint(low)
    assert high.window_reset_required is True
    assert risk_transition_is_monotonic(low, high)

    same, same_state = issue_assessment(
        commit_policy,
        RiskBand.HIGH,
        issued_at_step=4,
        previous=high,
        assessment_id="risk:3",
        inputs=(INPUT_B,),
        chain_state=high_state,
    )
    assert same.window_reset_required is False
    assert risk_transition_is_monotonic(high, same)

    with pytest.raises(GovernanceError, match="cannot decrease"):
        issue_assessment(
            commit_policy,
            RiskBand.MODERATE,
            issued_at_step=4,
            previous=high,
            assessment_id="risk:downgrade",
            chain_state=high_state,
        )
    with pytest.raises(GovernanceError, match="frozen expiry"):
        issue_assessment(
            commit_policy,
            RiskBand.CRITICAL,
            issued_at_step=4,
            expires_at_step=21,
            previous=high,
            assessment_id="risk:extended",
            chain_state=high_state,
        )
    assert risk_assessment_is_latest(same, chain_state=same_state)


def test_high_risk_threshold_cannot_be_weaker_and_nonmonotonic_policy_fails() -> None:
    commit_policy = policy()
    low_assessment, low_state = issue_assessment(commit_policy, RiskBand.LOW)
    low = threshold(low_assessment, low_state, commit_policy)
    high_assessment, high_state = issue_assessment(
        commit_policy,
        RiskBand.HIGH,
        issued_at_step=3,
        previous=low_assessment,
        assessment_id="risk:high",
        chain_state=low_state,
    )
    high = threshold(
        high_assessment,
        high_state,
        commit_policy,
        threshold_id="threshold:high",
    )

    assert high.minimum_positive_evidence >= low.minimum_positive_evidence
    assert high.minimum_support_clusters >= low.minimum_support_clusters
    assert high.minimum_support_ratio_ppm >= low.minimum_support_ratio_ppm
    assert high.minimum_source_diversity >= low.minimum_source_diversity
    assert high.minimum_margin >= low.minimum_margin
    assert high.stability_steps >= low.stability_steps
    assert high.maximum_counterevidence <= low.maximum_counterevidence
    assert (
        high.maximum_counterevidence_ratio_ppm
        <= low.maximum_counterevidence_ratio_ppm
    )

    invalid_bands = dict(commit_policy.risk_bands)
    invalid_bands["HIGH"] = replace(
        invalid_bands["HIGH"],
        minimum_support_clusters=1,
    )
    invalid_policy = replace(commit_policy, risk_bands=invalid_bands)
    with pytest.raises(GovernanceError, match="invalid or non-monotonic"):
        issue_assessment(invalid_policy, RiskBand.HIGH)


def test_cross_policy_and_cross_root_reuse_fail_but_policy_change_resets_window() -> None:
    first_policy = policy()
    first_assessment, first_state = issue_assessment(first_policy, RiskBand.LOW)
    first_threshold = threshold(first_assessment, first_state, first_policy)

    second_policy = policy(low_positive=2_100_000)
    assert not risk_assessment_matches(
        first_assessment,
        chain_state=first_state,
        commit_policy=second_policy,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=commit_policy_fingerprint(
            second_policy,
            profile=PROFILE,
        ),
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=TARGET,
        epoch=EPOCH,
        current_step=3,
    )
    with pytest.raises(GovernanceError, match="binding mismatch"):
        issue_assessment(
            second_policy,
            RiskBand.MODERATE,
            issued_at_step=3,
            previous=first_assessment,
            assessment_id="risk:cross-policy",
            chain_state=first_state,
        )

    second_assessment, second_state = issue_assessment(
        second_policy,
        RiskBand.LOW,
        assessment_id="risk:new-policy",
    )
    second_threshold = threshold(
        second_assessment,
        second_state,
        second_policy,
        threshold_id="threshold:new-policy",
    )
    assert commit_threshold_transition_requires_reset(
        first_threshold,
        second_threshold,
    )


def test_threshold_change_helper_rejects_forged_or_cross_scope_records() -> None:
    commit_policy = policy()
    assessment, chain_state = issue_assessment(commit_policy, RiskBand.LOW)
    snapshot = threshold(assessment, chain_state, commit_policy)
    forged = replace(snapshot, run_id="run:other")

    with pytest.raises(GovernanceError, match="authoritative"):
        commit_threshold_transition_requires_reset(snapshot, forged)


def test_initial_state_is_linear_and_conflicting_high_low_fork_fails_closed() -> None:
    commit_policy = policy()
    initial_state = initialize_chain(commit_policy)
    duplicate_initial_state = initialize_chain(commit_policy)
    assert duplicate_initial_state is initial_state
    low, low_state = issue_assessment(
        commit_policy,
        RiskBand.LOW,
        chain_state=initial_state,
    )

    repeated_low, repeated_state = issue_assessment(
        commit_policy,
        RiskBand.LOW,
        chain_state=initial_state,
    )
    assert repeated_low is low
    assert repeated_state is low_state
    assert not risk_assessment_chain_state_is_current(initial_state)
    assert risk_assessment_chain_state_is_current(low_state)

    with pytest.raises(GovernanceError, match="stale or would fork"):
        issue_assessment(
            commit_policy,
            RiskBand.HIGH,
            assessment_id="risk:conflicting-initial",
            inputs=(INPUT_A, INPUT_B),
            chain_state=duplicate_initial_state,
        )

    assert initialize_chain(commit_policy) is low_state
    with pytest.raises(GovernanceError, match="already has a different base"):
        initialize_chain(commit_policy, expires_at_step=21)


def test_reconstructed_chain_state_has_no_authority_or_linear_cursor() -> None:
    commit_policy = policy()
    state = initialize_chain(commit_policy)
    reconstructed = RiskAssessmentChainState(
        **risk_assessment_chain_state_payload(state)
    )

    assert not risk_assessment_chain_state_is_authoritative(reconstructed)
    assert not risk_assessment_chain_state_is_current(reconstructed)
    with pytest.raises(GovernanceError, match="not authoritative"):
        issue_assessment(
            commit_policy,
            RiskBand.LOW,
            chain_state=reconstructed,
        )


def test_gc_cannot_drop_authoritative_head_or_reopen_initial_issuance() -> None:
    commit_policy = policy()
    high, high_state = issue_assessment(commit_policy, RiskBand.HIGH)
    expected_head = risk_assessment_fingerprint(high)
    del high
    del high_state
    gc.collect()

    recovered = initialize_chain(commit_policy)
    assert recovered.revision == 1
    assert recovered.latest_assessment_fingerprint == expected_head
    assert risk_assessment_chain_state_is_current(recovered)
    with pytest.raises(GovernanceError, match="requires the authoritative latest"):
        issue_assessment(
            commit_policy,
            RiskBand.LOW,
            chain_state=recovered,
        )


def test_stale_state_missing_predecessor_and_second_successor_fail_closed() -> None:
    commit_policy = policy()
    low, low_state = issue_assessment(commit_policy, RiskBand.LOW)

    with pytest.raises(GovernanceError, match="requires the authoritative latest"):
        issue_assessment(
            commit_policy,
            RiskBand.MODERATE,
            issued_at_step=3,
            assessment_id="risk:missing-predecessor",
            chain_state=low_state,
        )

    high, high_state = issue_assessment(
        commit_policy,
        RiskBand.HIGH,
        issued_at_step=3,
        previous=low,
        assessment_id="risk:high-successor",
        chain_state=low_state,
    )
    assert risk_assessment_is_latest(high, chain_state=high_state)

    with pytest.raises(GovernanceError, match="stale or would fork"):
        issue_assessment(
            commit_policy,
            RiskBand.CRITICAL,
            issued_at_step=3,
            previous=low,
            assessment_id="risk:fork-successor",
            inputs=(INPUT_A, INPUT_B),
            chain_state=low_state,
        )


def test_current_chain_rejects_downgrade_and_cross_context_reuse() -> None:
    commit_policy = policy()
    high, high_state = issue_assessment(commit_policy, RiskBand.HIGH)

    with pytest.raises(GovernanceError, match="cannot decrease"):
        issue_assessment(
            commit_policy,
            RiskBand.LOW,
            issued_at_step=3,
            previous=high,
            assessment_id="risk:current-downgrade",
            chain_state=high_state,
        )

    with pytest.raises(GovernanceError, match="chain binding mismatch"):
        issue_assessment(
            commit_policy,
            RiskBand.CRITICAL,
            issued_at_step=3,
            previous=high,
            assessment_id="risk:cross-run",
            inputs=(INPUT_A, INPUT_B),
            chain_state=high_state,
            binding_run_id="run:other",
        )

    forged_state = replace(high_state, latest_risk_band=RiskBand.LOW.value)
    assert not risk_assessment_chain_state_is_authoritative(forged_state)
    assert not risk_assessment_chain_state_is_current(forged_state)


def test_threshold_requires_current_state_and_binds_exact_chain_head() -> None:
    commit_policy = policy()
    low, low_state = issue_assessment(commit_policy, RiskBand.LOW)
    low_threshold = threshold(low, low_state, commit_policy)
    high, high_state = issue_assessment(
        commit_policy,
        RiskBand.HIGH,
        issued_at_step=3,
        previous=low,
        assessment_id="risk:threshold-head",
        inputs=(INPUT_A, INPUT_B),
        chain_state=low_state,
    )

    assert not commit_threshold_snapshot_matches(
        low_threshold,
        assessment=low,
        chain_state=low_state,
        commit_policy=commit_policy,
        current_step=3,
    )
    with pytest.raises(GovernanceError, match="authoritative latest"):
        threshold(
            low,
            low_state,
            commit_policy,
            threshold_id="threshold:stale",
        )
    with pytest.raises(GovernanceError, match="authoritative latest"):
        threshold(
            high,
            low_state,
            commit_policy,
            threshold_id="threshold:mixed-head",
        )

    high_threshold = threshold(
        high,
        high_state,
        commit_policy,
        threshold_id="threshold:current",
    )
    assert commit_threshold_snapshot_matches(
        high_threshold,
        assessment=high,
        chain_state=high_state,
        commit_policy=commit_policy,
        current_step=3,
    )
