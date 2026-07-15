from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from pheroos.protocol import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_MODEL,
    COMMIT_POLICY_VERSION,
    COMMIT_WIRE_VERSION,
    MAX_AUTHORITY_INTEGER,
    REQUIRED_COMMIT_RESET_RULES,
    CollectiveCommitPolicy,
    CollectiveDecisionPolicy,
    DistributedCommitPolicy,
    commit_manifest_fingerprint,
    commit_policy_fingerprint,
    load_capability_manifest,
    validate_capability_manifest,
)
from pheroos.protocol.manifest import (
    capability_manifest_from_dict,
    protocol_manifest_from_dict,
)
from pheroos.protocol.schema import capability_schema, protocol_schema
from pheroos.protocol.schema_validation import validate_json_schema


ROOT = Path(__file__).resolve().parents[2]


def capability_payload() -> dict[str, object]:
    payload = json.loads(
        (ROOT / "examples/toy-protocol/capability.json").read_text(encoding="utf-8")
    )
    payload["protocol"]["collective_commit_policy"] = commit_policy_payload()
    return payload


def commit_policy_payload() -> dict[str, object]:
    challenges = ["independent_replication"]
    return {
        "policy_version": COMMIT_POLICY_VERSION,
        "model": COMMIT_MODEL,
        "assurance": "evidence_bound",
        "target": "decision:review",
        "evidence_qualification": {
            "numeric_scale": 1_000_000,
            "minimum_quality_ppm": 500_000,
            "minimum_relevance_ppm": 500_000,
            "positive_group_cap": 1_000_000,
            "counter_group_cap": 1_000_000,
            "counter_weight_ppm": 1_000_000,
            "minimum_positive_evidence": 2_000_000,
            "maximum_counterevidence": 500_000,
            "maximum_counterevidence_ratio_ppm": 200_000,
            "domain_contribution_floor": 250_000,
            "minimum_source_diversity": 2,
            "required_challenge_categories": challenges,
            "observation_ttl_steps": 8,
            "require_provenance": True,
            "require_trace": True,
        },
        "support_lease": {
            "minimum_support_clusters": 2,
            "support_ratio_ppm": 500_000,
            "lease_ttl_steps": 6,
            "membership_mode": "verified_snapshot_v1",
            "switch_mode": "revoke_then_issue_v1",
            "equivocation_mode": "exclude_conflicts_v1",
            "evidence_reference_required": True,
            "cluster_verification_required": True,
        },
        "risk_bands": {
            "LOW": risk_band(2_000_000, 500_000, 200_000, 2, 500_000, 2, 250_000, 2, challenges, "evidence_bound"),
            "MODERATE": risk_band(2_500_000, 400_000, 150_000, 2, 600_000, 2, 300_000, 3, challenges, "evidence_bound"),
            "HIGH": risk_band(3_000_000, 300_000, 100_000, 3, 700_000, 3, 400_000, 4, [*challenges, "counter_search"], "certified"),
            "CRITICAL": risk_band(4_000_000, 200_000, 50_000, 4, 800_000, 4, 500_000, 5, [*challenges, "counter_search", "failure_domain_review"], "distributed"),
        },
        "commit_window": {
            "minimum_stability_steps": 2,
            "deliberation_deadline_steps": 8,
            "maximum_leader_resets": 2,
            "maximum_epoch_restarts": 1,
            "run_deadline_steps": 12,
            "reset_rules": sorted(REQUIRED_COMMIT_RESET_RULES),
        },
        "terminal_outcome": {
            "safe_fallback_candidate": "candidate:insufficient_evidence",
            "deadline_outcome": "safe_fallback",
            "policy_incomplete_outcome": "invalid",
            "finality_unavailable_outcome": "finality_unavailable",
            "deliverable_outcomes": [
                "evidence_commit",
                "safe_fallback",
                "advisory",
                "blocked",
                "invalid",
                "finality_unavailable",
                "safety_violation",
            ],
            "publishable_outcomes": ["evidence_commit", "safe_fallback"],
            "executable_outcomes": [],
        },
        "certificate": {
            "mode": "local_receipt",
            "wire_version": COMMIT_WIRE_VERSION,
            "canonicalization": COMMIT_CANONICAL_VERSION,
            "hash_algorithm": "sha256",
            "issuer_attestation_required": False,
            "independent_verification_required": False,
        },
        "distributed": None,
    }


def risk_band(
    evidence: int,
    counter: int,
    ratio: int,
    support: int,
    support_ratio: int,
    diversity: int,
    margin: int,
    stability: int,
    challenges: list[str],
    assurance: str,
) -> dict[str, object]:
    return {
        "minimum_positive_evidence": evidence,
        "maximum_counterevidence": counter,
        "maximum_counterevidence_ratio_ppm": ratio,
        "minimum_support_clusters": support,
        "minimum_support_ratio_ppm": support_ratio,
        "minimum_source_diversity": diversity,
        "minimum_margin": margin,
        "stability_steps": stability,
        "required_challenge_categories": challenges,
        "minimum_assurance": assurance,
        "publishable_outcomes": ["evidence_commit"],
        "executable_outcomes": [],
    }


def test_complete_commit_policy_loads_and_validates_without_changing_legacy_fields() -> None:
    manifest = capability_manifest_from_dict(capability_payload())
    policy = manifest.protocol.collective_commit_policy

    assert validate_capability_manifest(manifest) == []
    assert isinstance(policy, CollectiveCommitPolicy)
    assert policy.policy_version == COMMIT_POLICY_VERSION
    assert policy.risk_bands["CRITICAL"].minimum_assurance == "distributed"
    assert policy.terminal_outcome.deliverable_outcomes == (
        "evidence_commit",
        "safe_fallback",
        "advisory",
        "blocked",
        "invalid",
        "finality_unavailable",
        "safety_violation",
    )
    assert manifest.protocol.quorum_policy.commit_threshold == 1


def test_commit_policy_preserves_noncritical_namespaced_extensions() -> None:
    payload = capability_payload()
    policy = payload["protocol"]["collective_commit_policy"]
    policy["x-acme.policy"] = {"runtime": "external"}
    policy["evidence_qualification"]["extensions"] = {
        "x-acme.evidence": {"adapter": "outside-core"}
    }

    manifest = capability_manifest_from_dict(payload)
    loaded = manifest.protocol.collective_commit_policy

    assert loaded is not None
    assert validate_capability_manifest(manifest) == []
    assert loaded.extensions["x-acme.policy"] == {"runtime": "external"}
    assert loaded.evidence_qualification.extensions["x-acme.evidence"] == {
        "adapter": "outside-core"
    }
    baseline = capability_manifest_from_dict(
        capability_payload()
    ).protocol.collective_commit_policy
    assert baseline is not None
    assert commit_policy_fingerprint(
        loaded,
        profile="pheroos-commit-integrity-v1",
    ) == commit_policy_fingerprint(
        baseline,
        profile="pheroos-commit-integrity-v1",
    )


@pytest.mark.parametrize(
    "critical_key",
    ("x-critical-finality", "ext.critical.commit"),
)
def test_unknown_critical_commit_extensions_fail_closed(
    critical_key: str,
) -> None:
    payload = capability_payload()
    policy = payload["protocol"]["collective_commit_policy"]
    policy["evidence_qualification"]["extensions"] = {
        critical_key: {"required": True}
    }

    manifest = capability_manifest_from_dict(payload)
    diagnostics = validate_capability_manifest(manifest)

    assert any(
        item.code == "commit_unknown_critical_extension"
        and critical_key in item.path
        for item in diagnostics
    )


@pytest.mark.parametrize(
    ("mutate", "expected_path"),
    [
        (
            lambda policy: policy["evidence_qualification"].pop("numeric_scale"),
            "evidence_qualification.numeric_scale",
        ),
        (
            lambda policy: policy["support_lease"].__setitem__("lease_ttl_steps", 1.0),
            "support_lease.lease_ttl_steps",
        ),
        (
            lambda policy: policy["commit_window"].__setitem__("maximum_leader_resets", True),
            "commit_window.maximum_leader_resets",
        ),
        (
            lambda policy: policy["risk_bands"]["LOW"]["required_challenge_categories"].append("independent_replication"),
            "risk_bands.LOW.required_challenge_categories",
        ),
        (
            lambda policy: policy.__setitem__("assurance", "unknown"),
            "collective_commit_policy.assurance",
        ),
        (
            lambda policy: policy.__setitem__("target", " decision:review"),
            "collective_commit_policy.target",
        ),
        (
            lambda policy: policy.__setitem__("unexpected", True),
            "collective_commit_policy.unexpected",
        ),
    ],
)
def test_commit_policy_raw_shape_is_rejected_by_schema_and_loader(
    mutate: object,
    expected_path: str,
) -> None:
    payload = capability_payload()
    mutate(payload["protocol"]["collective_commit_policy"])

    errors = validate_json_schema(payload, capability_schema())

    assert any(expected_path in item for item in errors)
    with pytest.raises(ValueError, match="manifest schema invalid") as exc:
        capability_manifest_from_dict(payload)
    assert expected_path in str(exc.value)


def test_commit_parser_rejects_integral_float_without_coercing_authority_value() -> None:
    payload = capability_payload()
    payload["protocol"]["collective_commit_policy"]["evidence_qualification"][
        "positive_group_cap"
    ] = 1_000_000.0

    with pytest.raises(ValueError, match="must be an integer: positive_group_cap"):
        protocol_manifest_from_dict(payload["protocol"])


def test_commit_parser_rejects_non_nfc_authority_text() -> None:
    payload = capability_payload()
    payload["protocol"]["collective_commit_policy"]["target"] = (
        "de\u0301cision:review"
    )

    with pytest.raises(ValueError, match="canonical non-blank string: target"):
        protocol_manifest_from_dict(payload["protocol"])


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (lambda policy: replace(policy, policy_version="v0"), "commit_policy_version_unsupported"),
        (lambda policy: replace(policy, assurance="unknown"), "commit_assurance_unsupported"),
        (lambda policy: replace(policy, target="decision:other"), "commit_target_missing"),
        (
            lambda policy: replace(
                policy,
                terminal_outcome=replace(
                    policy.terminal_outcome,
                    safe_fallback_candidate="candidate:accept",
                ),
            ),
            "commit_fallback_quorum_mismatch",
        ),
        (
            lambda policy: replace(
                policy,
                risk_bands={
                    **policy.risk_bands,
                    "HIGH": replace(
                        policy.risk_bands["HIGH"],
                        minimum_positive_evidence=1,
                    ),
                },
            ),
            "commit_risk_monotonicity_invalid",
        ),
        (
            lambda policy: replace(
                policy,
                commit_window=replace(
                    policy.commit_window,
                    reset_rules=["leader_change"],
                ),
            ),
            "commit_window_reset_rules_invalid",
        ),
        (
            lambda policy: replace(
                policy,
                certificate=replace(policy.certificate, mode="portable"),
            ),
            "commit_certificate_assurance_mismatch",
        ),
    ],
)
def test_direct_commit_policy_mutations_fail_semantic_validation(
    mutation: object,
    expected_code: str,
) -> None:
    manifest = capability_manifest_from_dict(capability_payload())
    mutated = mutation(manifest.protocol.collective_commit_policy)
    protocol = replace(manifest.protocol, collective_commit_policy=mutated)

    codes = {
        item.code
        for item in validate_capability_manifest(replace(manifest, protocol=protocol))
    }

    assert expected_code in codes


def test_distributed_policy_enforces_static_byzantine_quorum_intersection() -> None:
    manifest = capability_manifest_from_dict(capability_payload())
    base = manifest.protocol.collective_commit_policy
    assert base is not None
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
    policy = replace(
        base,
        assurance="distributed",
        certificate=replace(
            base.certificate,
            mode="distributed",
            issuer_attestation_required=True,
            independent_verification_required=True,
        ),
        distributed=distributed,
    )
    protocol = replace(manifest.protocol, collective_commit_policy=policy)

    assert validate_capability_manifest(replace(manifest, protocol=protocol)) == []

    broken = replace(policy, distributed=replace(distributed, witness_quorum=2))
    broken_protocol = replace(manifest.protocol, collective_commit_policy=broken)
    codes = {
        item.code
        for item in validate_capability_manifest(
            replace(manifest, protocol=broken_protocol)
        )
    }
    assert "commit_quorum_intersection_invalid" in codes


def test_commit_policy_integer_overflow_is_rejected_at_schema_boundary() -> None:
    payload = capability_payload()
    payload["protocol"]["collective_commit_policy"]["risk_bands"]["CRITICAL"][
        "minimum_positive_evidence"
    ] = MAX_AUTHORITY_INTEGER + 1

    with pytest.raises(ValueError, match="minimum_positive_evidence"):
        capability_manifest_from_dict(payload)


def test_generated_protocol_schema_exposes_complete_commit_policy_shape() -> None:
    schema = protocol_schema()
    commit = schema["properties"]["collective_commit_policy"]

    assert "collective_commit_policy" not in schema["required"]
    assert commit["required"] == [
        "policy_version",
        "model",
        "assurance",
        "target",
        "evidence_qualification",
        "support_lease",
        "risk_bands",
        "commit_window",
        "terminal_outcome",
        "certificate",
        "distributed",
    ]
    assert commit["properties"]["policy_version"] == {
        "const": COMMIT_POLICY_VERSION
    }
    assert commit["properties"]["risk_bands"]["required"] == [
        "LOW",
        "MODERATE",
        "HIGH",
        "CRITICAL",
    ]
    assert commit["properties"]["commit_window"]["properties"]["reset_rules"][
        "uniqueItems"
    ] is True


def test_legacy_manifests_remain_commit_policy_free_and_validation_clean() -> None:
    for relative in (
        "examples/toy-protocol/capability.json",
        "examples/e2e-protocol/capability.json",
        "examples/swarm-protocol/capability.json",
        "examples/hybrid-pheromone-protocol/capability.json",
    ):
        manifest = load_capability_manifest(ROOT / relative)
        assert manifest.protocol.collective_commit_policy is None
        assert validate_capability_manifest(manifest) == []


def test_commit_policy_input_permutation_is_semantically_stable() -> None:
    first = capability_payload()
    second = deepcopy(first)
    bands = second["protocol"]["collective_commit_policy"]["risk_bands"]
    second["protocol"]["collective_commit_policy"]["risk_bands"] = dict(
        reversed(list(bands.items()))
    )

    first_policy = capability_manifest_from_dict(first).protocol.collective_commit_policy
    second_policy = capability_manifest_from_dict(second).protocol.collective_commit_policy

    assert first_policy == second_policy


def test_commit_authority_roots_exclude_extensions_attention_and_legacy_threshold() -> None:
    first_payload = capability_payload()
    second_payload = deepcopy(first_payload)
    second_payload["protocol"]["collective_commit_policy"]["x-observer"] = {
        "ignored": True
    }
    second_payload["protocol"]["quorum_policy"]["commit_threshold"] = 999
    second_payload["protocol"]["candidates"] = list(
        reversed(second_payload["protocol"]["candidates"])
    )

    first = capability_manifest_from_dict(first_payload)
    second = capability_manifest_from_dict(second_payload)
    attention_mutated = replace(
        first,
        protocol=replace(
            first.protocol,
            collective_decision_policy=CollectiveDecisionPolicy(
                mode="hybrid",
                pheromone_enabled=True,
                pheromone_diffusion_enabled=True,
                pheromone_feedback_enabled=True,
                layer_coordination_enabled=True,
                fallback_candidate="candidate:insufficient_evidence",
            ),
        ),
    )
    profile = "pheroos-commit-integrity-v1"

    assert commit_manifest_fingerprint(first, profile=profile) == (
        commit_manifest_fingerprint(second, profile=profile)
    )
    assert commit_manifest_fingerprint(first, profile=profile) == (
        commit_manifest_fingerprint(attention_mutated, profile=profile)
    )
    assert commit_policy_fingerprint(
        first.protocol.collective_commit_policy,
        profile=profile,
    ) == commit_policy_fingerprint(
        second.protocol.collective_commit_policy,
        profile=profile,
    )


def test_commit_manifest_root_binds_output_trace_and_signal_authority() -> None:
    manifest = capability_manifest_from_dict(capability_payload())
    profile = "pheroos-commit-integrity-v1"
    baseline = commit_manifest_fingerprint(manifest, profile=profile)

    output_mutated = replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            output_policy=replace(
                manifest.protocol.output_policy,
                writer_may_create_facts=True,
            ),
        ),
    )
    trace_mutated = replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            trace_policy=replace(
                manifest.protocol.trace_policy,
                required_events=(
                    *manifest.protocol.trace_policy.required_events,
                    "risk_assessed",
                ),
            ),
        ),
    )
    signal = manifest.protocol.signals[0]
    signal_mutated = replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            signals=(replace(signal, authority_required="agent"),),
        ),
    )

    assert commit_manifest_fingerprint(output_mutated, profile=profile) != baseline
    assert commit_manifest_fingerprint(trace_mutated, profile=profile) != baseline
    assert commit_manifest_fingerprint(signal_mutated, profile=profile) != baseline


def test_commit_authority_roots_change_for_critical_policy_leaf_not_set_order() -> None:
    base_payload = capability_payload()
    critical_payload = deepcopy(base_payload)
    critical_payload["protocol"]["collective_commit_policy"][
        "evidence_qualification"
    ]["positive_group_cap"] += 1
    reordered_payload = deepcopy(base_payload)
    reordered_payload["protocol"]["collective_commit_policy"]["risk_bands"][
        "CRITICAL"
    ]["required_challenge_categories"].reverse()

    base = capability_manifest_from_dict(base_payload).protocol.collective_commit_policy
    critical = capability_manifest_from_dict(
        critical_payload
    ).protocol.collective_commit_policy
    reordered = capability_manifest_from_dict(
        reordered_payload
    ).protocol.collective_commit_policy
    profile = "pheroos-commit-integrity-v1"

    assert commit_policy_fingerprint(base, profile=profile) != commit_policy_fingerprint(
        critical,
        profile=profile,
    )
    assert commit_policy_fingerprint(base, profile=profile) == commit_policy_fingerprint(
        reordered,
        profile=profile,
    )
