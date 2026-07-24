"""Provider-free manifest fixture for public Support v2 Conformance."""

from __future__ import annotations

from hashlib import sha256

from pheroos.protocol import (
    BASELINE_OUTPUT_POLICY_VERSION_V2,
    COMMIT_CANONICAL_VERSION,
    COMMIT_INTEGRITY_PROFILE_VERSION,
    COMMIT_MODEL,
    COMMIT_POLICY_VERSION,
    COMMIT_WIRE_VERSION,
    PROTOCOL_VERSION_V2,
    REQUIRED_COMMIT_RESET_RULES,
    BaselineOutputActionPolicyV2,
    BaselineOutputPolicyV2,
    CandidateSpec,
    CertificatePolicy,
    CollectiveCommitPolicy,
    CommitAssurance,
    CommitWindowPolicy,
    EvidencePolicy,
    EvidenceQualificationPolicy,
    QuorumPolicy,
    RiskBandPolicy,
    ScopedAuthorityPolicyV2,
    ScopedProtocolManifestV2,
    SupportLeasePolicy,
    TargetSpec,
    TerminalOutcomePolicy,
    TracePolicy,
)


RUN_REF = "run:support-v2-conformance"
TARGET_REF = "decision:support-v2"
FALLBACK_REF = "candidate:support-v2:safe"
ACTION_REF = "action:support-v2:publish"
ISSUER_REF = "issuer:support-v2:a"
PROFILE = COMMIT_INTEGRITY_PROFILE_VERSION

_BASELINE_TRACE_EVENTS = (
    "baseline_action_permission_issued",
    "baseline_decision_evaluated",
    "baseline_evidence_qualified",
    "baseline_manifest_activated",
    "baseline_output_committed",
    "baseline_stop_resolved",
)


def manifest_v2(authority_profile: str) -> ScopedProtocolManifestV2:
    return ScopedProtocolManifestV2(
        protocol_version=PROTOCOL_VERSION_V2,
        id="protocol:support-v2-conformance",
        targets=(TargetSpec(TARGET_REF, "durable Support v2 target"),),
        candidates=(
            CandidateSpec("candidate:support-v2:accept", TARGET_REF),
            CandidateSpec(FALLBACK_REF, TARGET_REF, True),
        ),
        quorum_policy=QuorumPolicy(TARGET_REF, FALLBACK_REF, 2),
        authority_policy=ScopedAuthorityPolicyV2(
            policy_version="pheroos-scoped-authority-policy-v2",
            profile=authority_profile,
            wire_version="pheroos-authority-wire-v2",
            canonical_version="pheroos-authority-canonical-v2",
            ledger_version="pheroos-governance-authority-ledger-v2",
            state_store_version="pheroos-governance-state-store-v2",
            trace_batch_version="pheroos-governance-trace-batch-v2",
            read_set_version="pheroos-governance-authority-read-set-v2",
        ),
        output_policy=BaselineOutputPolicyV2(
            BASELINE_OUTPUT_POLICY_VERSION_V2,
            "quorum",
            (
                BaselineOutputActionPolicyV2(
                    ACTION_REF,
                    "publish",
                    TARGET_REF,
                    ("evidence_commit", "safe_fallback"),
                ),
            ),
        ),
        trace_policy=TracePolicy(list(_BASELINE_TRACE_EVENTS)),
        evidence_policy=EvidencePolicy(),
        collective_commit_policy=_commit_policy_v2(),
    )


def _commit_policy_v2() -> CollectiveCommitPolicy:
    return CollectiveCommitPolicy(
        policy_version=COMMIT_POLICY_VERSION,
        model=COMMIT_MODEL,
        assurance=CommitAssurance.EVIDENCE_BOUND.value,
        target=TARGET_REF,
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
            required_challenge_categories=["independent_replication"],
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
            name: _band_v2(assurance)
            for name, assurance in (
                ("LOW", CommitAssurance.EVIDENCE_BOUND.value),
                ("MODERATE", CommitAssurance.EVIDENCE_BOUND.value),
                ("HIGH", CommitAssurance.CERTIFIED.value),
                ("CRITICAL", CommitAssurance.DISTRIBUTED.value),
            )
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
            safe_fallback_candidate=FALLBACK_REF,
            deadline_outcome="safe_fallback",
            policy_incomplete_outcome="invalid",
            finality_unavailable_outcome="finality_unavailable",
            deliverable_outcomes=[
                "advisory",
                "blocked",
                "evidence_commit",
                "finality_unavailable",
                "invalid",
                "safe_fallback",
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


def _band_v2(assurance: str) -> RiskBandPolicy:
    return RiskBandPolicy(
        minimum_positive_evidence=2_000_000,
        maximum_counterevidence=500_000,
        maximum_counterevidence_ratio_ppm=200_000,
        minimum_support_clusters=2,
        minimum_support_ratio_ppm=500_000,
        minimum_source_diversity=2,
        minimum_margin=250_000,
        stability_steps=2,
        required_challenge_categories=["independent_replication"],
        minimum_assurance=assurance,
        publishable_outcomes=["evidence_commit"],
        executable_outcomes=[],
    )


def root_v2(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


__all__: tuple[str, ...] = ()
