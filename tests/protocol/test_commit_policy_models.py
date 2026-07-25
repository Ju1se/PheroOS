from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from pheroos.conformance.profile import profile_for_manifest

from pheroos.protocol import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_MODEL,
    COMMIT_POLICY_VERSION,
    COMMIT_WIRE_VERSION,
    REQUIRED_COMMIT_RESET_RULES,
    CertificatePolicy,
    CollectiveCommitPolicy,
    CommitWindowPolicy,
    DistributedCommitPolicy,
    EvidenceQualificationPolicy,
    RiskBandPolicy,
    SupportLeasePolicy,
    TerminalOutcomePolicy,
    load_capability_manifest,
)


@dataclass
class _MutableExtensionRecord:
    values: list[str]


def evidence_policy() -> EvidenceQualificationPolicy:
    return EvidenceQualificationPolicy(
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
    )


def lease_policy() -> SupportLeasePolicy:
    return SupportLeasePolicy(
        minimum_support_clusters=2,
        support_ratio_ppm=500_000,
        lease_ttl_steps=6,
        membership_mode="verified_snapshot_v1",
        switch_mode="revoke_then_issue_v1",
        equivocation_mode="exclude_conflicts_v1",
        evidence_reference_required=True,
        cluster_verification_required=True,
    )


def band(
    *,
    evidence: int,
    counter: int,
    ratio: int,
    support: int,
    diversity: int,
    margin: int,
    stability: int,
    assurance: str,
) -> RiskBandPolicy:
    return RiskBandPolicy(
        minimum_positive_evidence=evidence,
        maximum_counterevidence=counter,
        maximum_counterevidence_ratio_ppm=ratio,
        minimum_support_clusters=support,
        minimum_support_ratio_ppm=500_000,
        minimum_source_diversity=diversity,
        minimum_margin=margin,
        stability_steps=stability,
        required_challenge_categories=["independent_replication"],
        minimum_assurance=assurance,
        publishable_outcomes=["evidence_commit"],
        executable_outcomes=[],
    )


def policy() -> CollectiveCommitPolicy:
    return CollectiveCommitPolicy(
        policy_version=COMMIT_POLICY_VERSION,
        model=COMMIT_MODEL,
        assurance="evidence_bound",
        target="decision:collective",
        evidence_qualification=evidence_policy(),
        support_lease=lease_policy(),
        risk_bands={
            "LOW": band(
                evidence=2_000_000,
                counter=500_000,
                ratio=200_000,
                support=2,
                diversity=2,
                margin=250_000,
                stability=2,
                assurance="evidence_bound",
            ),
            "MODERATE": band(
                evidence=2_500_000,
                counter=400_000,
                ratio=150_000,
                support=2,
                diversity=2,
                margin=300_000,
                stability=3,
                assurance="evidence_bound",
            ),
            "HIGH": band(
                evidence=3_000_000,
                counter=300_000,
                ratio=100_000,
                support=3,
                diversity=3,
                margin=400_000,
                stability=4,
                assurance="certified",
            ),
            "CRITICAL": band(
                evidence=4_000_000,
                counter=200_000,
                ratio=50_000,
                support=4,
                diversity=4,
                margin=500_000,
                stability=5,
                assurance="distributed",
            ),
        },
        commit_window=CommitWindowPolicy(
            minimum_stability_steps=2,
            deliberation_deadline_steps=8,
            maximum_leader_resets=2,
            maximum_epoch_restarts=1,
            run_deadline_steps=12,
            reset_rules=sorted(REQUIRED_COMMIT_RESET_RULES),
        ),
        terminal_outcome=TerminalOutcomePolicy(
            safe_fallback_candidate="candidate:safe",
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
            executable_outcomes=["evidence_commit"],
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


def test_commit_policy_models_defensively_snapshot_nested_inputs() -> None:
    categories = ["independent_replication"]
    extension_values = ["commit:original"]
    evidence = replace(
        evidence_policy(),
        required_challenge_categories=categories,
        extensions={"x-observer": {"mode": "external"}},
    )
    bands = dict(policy().risk_bands)
    commit_policy = replace(
        policy(),
        evidence_qualification=evidence,
        risk_bands=bands,
        extensions={
            "x-commit": _MutableExtensionRecord(values=extension_values),
        },
    )

    categories.append("late_mutation")
    bands["LOW"] = bands["CRITICAL"]
    extension_values.append("commit:mutated")

    assert commit_policy.evidence_qualification.required_challenge_categories == (
        "independent_replication",
    )
    assert commit_policy.evidence_qualification.extensions["x-observer"] == {
        "mode": "external"
    }
    assert type(commit_policy.risk_bands["LOW"]) is RiskBandPolicy
    assert commit_policy.risk_bands["LOW"].minimum_positive_evidence == 2_000_000
    assert commit_policy.extensions["x-commit"]["values"] == ("commit:original",)


def test_distributed_policy_shape_is_available_without_affecting_legacy() -> None:
    distributed = DistributedCommitPolicy(
        fault_model="byzantine_static_v1",
        membership_mode="static_epoch_verified_clusters_v1",
        membership_size=4,
        max_byzantine_faults=1,
        witness_quorum=3,
        witness_ttl_steps=4,
        minimum_failure_domain_diversity=2,
        epoch_transition_rule="prior_quorum_certificate_v1",
        conflict_rule="freeze_v1",
    )

    assert distributed.witness_quorum == 3
    for path in (
        "examples/toy-protocol/capability.json",
        "examples/swarm-protocol/capability.json",
        "examples/hybrid-pheromone-protocol/capability.json",
    ):
        assert load_capability_manifest(path).protocol.collective_commit_policy is None


def with_commit_policy(
    example: str,
    commit_policy: CollectiveCommitPolicy,
):
    manifest = load_capability_manifest(example)
    return replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            collective_commit_policy=commit_policy,
        ),
    )


def test_commit_profile_precedes_legacy_swarm_and_hybrid_detection() -> None:
    evidence_bound = policy()
    core = with_commit_policy(
        "examples/toy-protocol/capability.json",
        evidence_bound,
    )
    hybrid = with_commit_policy(
        "examples/hybrid-pheromone-protocol/capability.json",
        evidence_bound,
    )

    assert profile_for_manifest(core).version == "pheroos-commit-integrity-v1"
    assert profile_for_manifest(hybrid).version == "pheroos-hybrid-commit-v1"
    assert "pheromone_behavior" in profile_for_manifest(hybrid).required_checks
    assert (
        "score_breakdown_contract" not in profile_for_manifest(hybrid).required_checks
    )
    assert "hybrid_trace_contract" not in profile_for_manifest(hybrid).required_checks
    assert "commit_trace_contract" in profile_for_manifest(hybrid).required_checks

    advisory = replace(
        evidence_bound,
        assurance="advisory",
        certificate=replace(evidence_bound.certificate, mode="none"),
    )
    advisory_hybrid_profile = profile_for_manifest(
        with_commit_policy(
            "examples/hybrid-pheromone-protocol/capability.json",
            advisory,
        )
    )
    assert advisory_hybrid_profile.version == "pheroos-commit-integrity-v1"
    assert "pheromone_behavior" in advisory_hybrid_profile.required_checks
    assert "commit_channel_separation" in advisory_hybrid_profile.required_checks


def test_commit_profile_assurance_matrix_is_fail_closed_and_cumulative() -> None:
    base = policy()
    certified = replace(
        base,
        assurance="certified",
        certificate=replace(
            base.certificate,
            mode="portable",
            issuer_attestation_required=True,
            independent_verification_required=True,
        ),
    )
    distributed_declaration = DistributedCommitPolicy(
        fault_model="byzantine_static_v1",
        membership_mode="static_epoch_verified_clusters_v1",
        membership_size=4,
        max_byzantine_faults=1,
        witness_quorum=3,
        witness_ttl_steps=4,
        minimum_failure_domain_diversity=2,
        epoch_transition_rule="prior_quorum_certificate_v1",
        conflict_rule="freeze_v1",
    )
    distributed = replace(
        certified,
        assurance="distributed",
        certificate=replace(certified.certificate, mode="distributed"),
        distributed=distributed_declaration,
    )

    certified_profile = profile_for_manifest(
        with_commit_policy(
            "examples/hybrid-pheromone-protocol/capability.json",
            certified,
        )
    )
    distributed_profile = profile_for_manifest(
        with_commit_policy("examples/toy-protocol/capability.json", distributed)
    )

    assert certified_profile.version == "pheroos-certified-commit-v1"
    assert "pheromone_diffusion" in certified_profile.required_checks
    assert "commit_certificate_contract" in certified_profile.required_checks
    assert distributed_profile.version == "pheroos-distributed-commit-v1"
    assert "distributed_finality_contract" in distributed_profile.required_checks
    assert "certificate_conflict_contract" in distributed_profile.required_checks


def test_unknown_commit_version_model_or_assurance_never_falls_back() -> None:
    base = policy()
    for invalid in (
        replace(base, policy_version="future-version"),
        replace(base, model="future-model"),
        replace(base, assurance="future-assurance"),
    ):
        manifest = with_commit_policy(
            "examples/hybrid-pheromone-protocol/capability.json",
            invalid,
        )
        with pytest.raises(ValueError, match="unsupported"):
            profile_for_manifest(manifest)
