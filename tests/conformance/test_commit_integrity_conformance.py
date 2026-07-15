from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pheroos.conformance import run_conformance
from pheroos.conformance.checks import (
    commit_authority_boundary,
    commit_numeric_contract,
    commit_policy_contract,
    commit_trace_contract,
    principal_attestation_contract,
    risk_monotonicity_contract,
)
from pheroos.conformance.profile import (
    CERTIFIED_COMMIT_PROFILE,
    COMMIT_AUTHORITY_CHECKS,
    COMMIT_INTEGRITY_PROFILE,
    COMMIT_STRUCTURAL_CHECKS,
    CORE_PROFILE,
    DISTRIBUTED_COMMIT_PROFILE,
    HYBRID_ATTENTION_CHECKS,
    HYBRID_COMMIT_PROFILE,
    HYBRID_SWARM_PROFILE,
    SWARM_PROFILE,
    profile_for_manifest,
)
from pheroos.conformance.runner import MANIFEST_CHECKS, safe_check
from pheroos.protocol import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_MODEL,
    COMMIT_POLICY_VERSION,
    COMMIT_WIRE_VERSION,
    REQUIRED_COMMIT_RESET_RULES,
    CapabilityManifest,
)
from pheroos.protocol.manifest import capability_manifest_from_dict


ROOT = Path(__file__).resolve().parents[2]
FORMAL_COMMIT_CHECKS = {
    "commit_policy_contract",
    "commit_numeric_contract",
    "principal_attestation_contract",
    "risk_monotonicity_contract",
    "membership_snapshot_contract",
    "observation_binding_contract",
    "counterevidence_contract",
    "challenge_coverage_contract",
    "support_lease_contract",
    "commit_metrics_contract",
    "commit_channel_separation",
    "commit_window_contract",
    "commit_liveness_contract",
    "commit_authority_boundary",
    "commit_trace_contract",
    "commit_certificate_contract",
    "certificate_output_contract",
    "distributed_finality_contract",
    "certificate_conflict_contract",
    "no_assurance_downgrade",
}
TCK_BACKED_COMMIT_CHECKS = FORMAL_COMMIT_CHECKS - {
    "commit_policy_contract",
    "commit_numeric_contract",
    "principal_attestation_contract",
    "commit_trace_contract",
}
def test_formal_commit_registry_is_complete_and_unique() -> None:
    assert len(MANIFEST_CHECKS) == len(set(MANIFEST_CHECKS))
    assert FORMAL_COMMIT_CHECKS.issubset(MANIFEST_CHECKS)
    assert (
        set(COMMIT_AUTHORITY_CHECKS)
        | {
            "commit_channel_separation",
            "distributed_finality_contract",
            "certificate_conflict_contract",
        }
    ) == FORMAL_COMMIT_CHECKS
    assert COMMIT_INTEGRITY_PROFILE.required_checks == (
        *COMMIT_STRUCTURAL_CHECKS,
        *COMMIT_AUTHORITY_CHECKS,
    )
    assert HYBRID_COMMIT_PROFILE.required_checks == (
        *COMMIT_STRUCTURAL_CHECKS,
        *HYBRID_ATTENTION_CHECKS,
        *COMMIT_AUTHORITY_CHECKS,
        "commit_channel_separation",
    )
    assert CERTIFIED_COMMIT_PROFILE.required_checks == (
        *COMMIT_STRUCTURAL_CHECKS,
        *COMMIT_AUTHORITY_CHECKS,
    )
    assert DISTRIBUTED_COMMIT_PROFILE.required_checks == (
        *CERTIFIED_COMMIT_PROFILE.required_checks,
        "distributed_finality_contract",
        "certificate_conflict_contract",
    )

    for profile in (
        COMMIT_INTEGRITY_PROFILE,
        HYBRID_COMMIT_PROFILE,
        CERTIFIED_COMMIT_PROFILE,
        DISTRIBUTED_COMMIT_PROFILE,
    ):
        assert len(profile.required_checks) == len(set(profile.required_checks))
        assert all(
            name == "manifest_schema" or callable(MANIFEST_CHECKS.get(name))
            for name in profile.required_checks
        )
    assert FORMAL_COMMIT_CHECKS == {
        name
        for profile in (
            COMMIT_INTEGRITY_PROFILE,
            HYBRID_COMMIT_PROFILE,
            CERTIFIED_COMMIT_PROFILE,
            DISTRIBUTED_COMMIT_PROFILE,
        )
        for name in profile.required_checks
        if name in FORMAL_COMMIT_CHECKS
    }


def test_legacy_profiles_remain_structurally_unchanged() -> None:
    assert CORE_PROFILE.required_checks == (
        "manifest_schema",
        "candidate_declaration",
        "quorum_policy",
        "recovery_policy",
        "output_contract",
        "trace_contract",
        "driver_contract",
        "kernel_contract",
        "extension_contract",
    )
    assert SWARM_PROFILE.required_checks == (
        *CORE_PROFILE.required_checks,
        "collective_policy",
        "safe_fallback_collective",
        "score_breakdown_contract",
        "pheromone_policy",
        "pheromone_behavior",
        "swarm_trace_contract",
    )
    assert HYBRID_SWARM_PROFILE.required_checks == (
        *SWARM_PROFILE.required_checks,
        "pheromone_subject_scoring",
        "pheromone_kind_profile",
        "pheromone_diffusion",
        "pheromone_reinforcement",
        "pheromone_response_model",
        "layer_coordination_policy",
        "policy_adjustment_bounds",
        "hybrid_trace_contract",
        "hybrid_authority_boundary",
    )


def test_direct_commit_checks_execute_public_contracts() -> None:
    manifest = _manifest(_capability_payload("toy-protocol"))
    observed = [
        module.check(manifest)
        for module in (
            commit_policy_contract,
            commit_numeric_contract,
            principal_attestation_contract,
            commit_authority_boundary,
            commit_trace_contract,
        )
    ]
    results = {result.name: result for result in observed}

    assert set(results) == {
        "commit_policy_contract",
        "commit_numeric_contract",
        "principal_attestation_contract",
        "commit_authority_boundary",
        "commit_trace_contract",
    }
    assert all(result.ok for result in results.values()), results


@pytest.mark.parametrize(
    ("assurance", "expected_profile"),
    (
        ("advisory", "pheroos-commit-integrity-v1"),
        ("evidence_bound", "pheroos-commit-integrity-v1"),
        ("certified", "pheroos-certified-commit-v1"),
        ("distributed", "pheroos-distributed-commit-v1"),
    ),
)
def test_every_assurance_runs_an_active_all_pass_report_without_skip_or_na(
    tmp_path: Path,
    assurance: str,
    expected_profile: str,
) -> None:
    payload = _payload_for_assurance(assurance, hybrid=False)
    manifest_path = _write_payload(tmp_path, payload)
    selected = profile_for_manifest(_manifest(payload))
    report = run_conformance(manifest_path)

    assert selected.version == expected_profile
    assert report.profile == expected_profile
    assert report.ok is True, report.to_dict()
    assert {item.name for item in report.checks} == {
        "manifest_schema",
        *selected.required_checks,
        "profile_contract",
    }
    assert len(report.checks) == len({item.name for item in report.checks})
    assert all(item.ok for item in report.checks)
    assert all(
        marker not in item.detail.lower()
        for item in report.checks
        for marker in (
            "skip",
            "n/a",
            "not applicable",
            "not active",
            "not_active",
        )
    )
    for item in report.checks:
        if item.name in TCK_BACKED_COMMIT_CHECKS:
            assert item.detail.startswith("exact TCK cases:"), item


@pytest.mark.parametrize(
    ("assurance", "expected_profile"),
    (
        ("advisory", "pheroos-commit-integrity-v1"),
        ("evidence_bound", "pheroos-hybrid-commit-v1"),
        ("certified", "pheroos-certified-commit-v1"),
        ("distributed", "pheroos-distributed-commit-v1"),
    ),
)
def test_commit_profile_precedes_legacy_hybrid_authority_for_all_assurances(
    assurance: str,
    expected_profile: str,
) -> None:
    selected = profile_for_manifest(
        _manifest(_payload_for_assurance(assurance, hybrid=True))
    )

    assert selected.version == expected_profile
    assert len(selected.required_checks) == len(set(selected.required_checks))
    assert all(
        name == "manifest_schema" or callable(MANIFEST_CHECKS.get(name))
        for name in selected.required_checks
    )
    assert set(HYBRID_ATTENTION_CHECKS).issubset(selected.required_checks)
    assert "commit_channel_separation" in selected.required_checks
    assert set(COMMIT_AUTHORITY_CHECKS).issubset(selected.required_checks)
    assert {
        "output_contract",
        "trace_contract",
        "score_breakdown_contract",
        "safe_fallback_collective",
        "hybrid_trace_contract",
        "hybrid_authority_boundary",
    }.isdisjoint(selected.required_checks)
    assert (
        "distributed_finality_contract" in selected.required_checks
    ) is (assurance == "distributed")
    assert (
        "certificate_conflict_contract" in selected.required_checks
    ) is (assurance == "distributed")


def test_hybrid_commit_report_executes_the_active_channel_contract(
    tmp_path: Path,
) -> None:
    manifest_path = _write_payload(
        tmp_path,
        _payload_for_assurance("evidence_bound", hybrid=True),
    )

    report = run_conformance(manifest_path)
    checks = {item.name: item for item in report.checks}

    assert report.profile == "pheroos-hybrid-commit-v1"
    assert report.ok is True, report.to_dict()
    assert checks["commit_channel_separation"].ok is True
    assert checks["commit_channel_separation"].detail == "exact TCK cases: 11"
    assert "score_breakdown_contract" not in checks
    assert checks["profile_contract"].ok is True


@pytest.mark.parametrize(
    ("example", "expected_profile", "expected_assurance"),
    (
        (
            "hybrid-commit-protocol",
            "pheroos-hybrid-commit-v1",
            "evidence_bound",
        ),
        (
            "distributed-commit-protocol",
            "pheroos-distributed-commit-v1",
            "distributed",
        ),
    ),
)
def test_checked_in_commit_manifests_select_and_pass_the_declared_profile(
    example: str,
    expected_profile: str,
    expected_assurance: str,
) -> None:
    path = ROOT / "examples" / example / "capability.json"
    manifest = _manifest(json.loads(path.read_text(encoding="utf-8")))
    policy = manifest.protocol.collective_commit_policy
    assert policy is not None
    evidence = policy.evidence_qualification
    support = policy.support_lease
    window = policy.commit_window
    terminal = policy.terminal_outcome

    assert evidence.numeric_scale == 1_000_000
    assert evidence.minimum_positive_evidence == 2_000_000
    assert evidence.minimum_source_diversity == 2
    assert evidence.required_challenge_categories == (
        "independent_replication",
    )
    assert evidence.require_provenance is True
    assert evidence.require_trace is True
    assert support.minimum_support_clusters == 2
    assert support.support_ratio_ppm == 500_000
    assert support.evidence_reference_required is True
    assert support.cluster_verification_required is True
    assert window.minimum_stability_steps == 2
    assert window.run_deadline_steps == 24
    assert set(window.reset_rules) == set(REQUIRED_COMMIT_RESET_RULES)
    assert set(terminal.deliverable_outcomes) == {
        "evidence_commit",
        "safe_fallback",
        "advisory",
        "blocked",
        "invalid",
        "finality_unavailable",
        "safety_violation",
    }

    bands = [policy.risk_bands[name] for name in ("LOW", "MODERATE", "HIGH", "CRITICAL")]
    assert [item.minimum_positive_evidence for item in bands] == [
        2_000_000,
        2_500_000,
        3_000_000,
        4_000_000,
    ]
    assert [item.maximum_counterevidence for item in bands] == [
        500_000,
        400_000,
        300_000,
        200_000,
    ]
    assert [item.minimum_support_clusters for item in bands] == [2, 2, 3, 4]
    assert [item.stability_steps for item in bands] == [2, 3, 4, 5]
    assert [item.minimum_assurance for item in bands] == [
        "evidence_bound",
        "evidence_bound",
        "certified",
        "distributed",
    ]

    report = run_conformance(path)

    assert policy.assurance == expected_assurance
    assert profile_for_manifest(manifest).version == expected_profile
    assert report.profile == expected_profile
    assert report.ok is True, report.to_dict()
    if expected_assurance == "evidence_bound":
        assert policy.certificate.mode == "local_receipt"
        assert policy.distributed is None
        attention = manifest.protocol.collective_decision_policy
        assert attention is not None
        assert attention.pheromone_diffusion_enabled is True
        assert attention.pheromone_feedback_enabled is True
        assert attention.layer_coordination_enabled is True
        assert attention.policy_adjustment_bounds
    else:
        assert policy.certificate.mode == "distributed"
        assert policy.certificate.issuer_attestation_required is True
        assert policy.certificate.independent_verification_required is True
        distributed = policy.distributed
        assert distributed is not None
        assert (
            distributed.membership_size,
            distributed.max_byzantine_faults,
            distributed.witness_quorum,
        ) == (4, 1, 3)
        assert distributed.membership_size >= (
            3 * distributed.max_byzantine_faults + 1
        )
        assert distributed.witness_quorum <= (
            distributed.membership_size - distributed.max_byzantine_faults
        )
        assert 2 * distributed.witness_quorum - distributed.membership_size > (
            distributed.max_byzantine_faults
        )


def test_runner_turns_check_exceptions_into_structured_profile_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = _write_payload(
        tmp_path,
        _payload_for_assurance("evidence_bound", hybrid=False),
    )

    def explode(_manifest: CapabilityManifest) -> object:
        raise RuntimeError("deliberate conformance fault")

    monkeypatch.setitem(MANIFEST_CHECKS, "commit_metrics_contract", explode)
    report = run_conformance(manifest_path)
    checks = {item.name: item for item in report.checks}

    assert report.ok is False
    assert checks["commit_metrics_contract"].ok is False
    assert checks["commit_metrics_contract"].detail == (
        "RuntimeError: deliberate conformance fault"
    )
    assert checks["profile_contract"].ok is False
    assert "failed:commit_metrics_contract" in checks["profile_contract"].detail


def test_safe_check_rejects_wrong_result_type_and_mismatched_name() -> None:
    wrong_type = safe_check("formal", lambda: True)
    wrong_name = safe_check(
        "formal",
        lambda: type(wrong_type)("temporary", True),
    )

    assert wrong_type.ok is False
    assert wrong_type.detail == "invalid check result type: bool"
    assert wrong_name.ok is False
    assert wrong_name.detail == "check returned mismatched name: temporary"


def test_tck_backed_check_fails_on_an_exact_vector_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pheroos.conformance import commit_tck

    manifest = _manifest(_capability_payload("toy-protocol"))
    failed = SimpleNamespace(
        matrix_case=9,
        vector_id="risk-monotonicity",
        ok=False,
        detail="exact expected value mismatch",
    )
    monkeypatch.setattr(
        commit_tck,
        "run_commit_tck",
        lambda *_args, **_kwargs: SimpleNamespace(results=(failed,)),
    )

    result = risk_monotonicity_contract.check(manifest)

    assert result.ok is False
    assert "case 9 (risk-monotonicity)" in result.detail
    assert "exact expected value mismatch" in result.detail


def test_case_35_registry_probe_is_nonrecursive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pheroos.conformance.commit_tck import (
        ReferenceCommitTckAdapter,
        load_commit_tck_vectors,
    )

    vector = next(
        item for item in load_commit_tck_vectors() if item.matrix_case == 35
    )

    def recurse(_manifest: CapabilityManifest) -> object:
        raise AssertionError("case 35 must inspect registration without executing checks")

    monkeypatch.setitem(MANIFEST_CHECKS, "commit_metrics_contract", recurse)
    uncached = replace(vector, id=f"{vector.id}:nonrecursive-proof")

    actual = ReferenceCommitTckAdapter().evaluate(uncached)

    assert actual == vector.expected


def test_commit_policy_contract_fails_actual_manifest_diagnostics() -> None:
    manifest = _manifest(_capability_payload("toy-protocol"))
    policy = manifest.protocol.collective_commit_policy
    assert policy is not None
    mutated = replace(policy, target="decision:undeclared")
    protocol = replace(manifest.protocol, collective_commit_policy=mutated)

    result = commit_policy_contract.check(replace(manifest, protocol=protocol))

    assert result.ok is False
    assert "diagnostic:commit_target_missing" in result.detail
    assert "declared_target" in result.detail


def test_numeric_contract_detects_a_wrong_reference_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest(_capability_payload("toy-protocol"))
    monkeypatch.setattr(commit_numeric_contract, "multiply_scaled", lambda *_: 0)

    result = commit_numeric_contract.check(manifest)

    assert result.ok is False
    assert "numeric_vector:multiply_scaled" in result.detail


def test_principal_contract_detects_cross_scope_matcher_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest(_capability_payload("toy-protocol"))
    monkeypatch.setattr(
        principal_attestation_contract,
        "principal_verification_matches",
        lambda *_args, **_kwargs: True,
    )

    result = principal_attestation_contract.check(manifest)

    assert result.ok is False
    assert "cross_target_replay_accepted" in result.detail
    assert "expired_verification_accepted" in result.detail


def test_action_authority_contract_detects_cross_scope_matcher_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest(_capability_payload("toy-protocol"))
    monkeypatch.setattr(
        commit_authority_boundary,
        "action_permission_matches",
        lambda *_args, **_kwargs: True,
    )

    result = commit_authority_boundary.check(manifest)

    assert result.ok is False
    assert "permission_cross_target_replay_accepted" in result.detail
    assert "expired_permission_accepted" in result.detail


def _manifest(payload: dict[str, object]) -> CapabilityManifest:
    return capability_manifest_from_dict(payload)


def _write_payload(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "capability.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _payload_for_assurance(
    assurance: str,
    *,
    hybrid: bool,
) -> dict[str, object]:
    payload = _capability_payload(
        "hybrid-pheromone-protocol" if hybrid else "toy-protocol"
    )
    policy = payload["protocol"]["collective_commit_policy"]
    policy["assurance"] = assurance
    if assurance == "advisory":
        policy["certificate"]["mode"] = "none"
        policy["terminal_outcome"]["publishable_outcomes"] = []
        for band in policy["risk_bands"].values():
            band["publishable_outcomes"] = []
    elif assurance in {"certified", "distributed"}:
        policy["certificate"]["mode"] = (
            "portable" if assurance == "certified" else "distributed"
        )
        policy["certificate"]["issuer_attestation_required"] = True
        policy["certificate"]["independent_verification_required"] = True
    if assurance == "distributed":
        policy["distributed"] = {
            "fault_model": "byzantine_static_v1",
            "membership_mode": "static_epoch_verified_clusters_v1",
            "membership_size": 4,
            "max_byzantine_faults": 1,
            "witness_quorum": 3,
            "witness_ttl_steps": 4,
            "minimum_failure_domain_diversity": 2,
            "epoch_transition_rule": "prior_quorum_certificate_v1",
            "conflict_rule": "freeze_v1",
        }
    return payload


def _capability_payload(example: str) -> dict[str, object]:
    payload = json.loads(
        (ROOT / "examples" / example / "capability.json").read_text(
            encoding="utf-8"
        )
    )
    quorum = payload["protocol"]["quorum_policy"]
    payload["protocol"]["collective_commit_policy"] = _commit_policy_payload(
        target=quorum["target"],
        fallback=quorum["fallback_candidate"],
    )
    return payload


def _commit_policy_payload(*, target: str, fallback: str) -> dict[str, object]:
    challenges = ["independent_replication"]
    return {
        "policy_version": COMMIT_POLICY_VERSION,
        "model": COMMIT_MODEL,
        "assurance": "evidence_bound",
        "target": target,
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
            "LOW": _risk_band(
                2_000_000, 500_000, 200_000, 2, 500_000, 2, 250_000, 2,
                challenges, "evidence_bound",
            ),
            "MODERATE": _risk_band(
                2_500_000, 400_000, 150_000, 2, 600_000, 2, 300_000, 3,
                challenges, "evidence_bound",
            ),
            "HIGH": _risk_band(
                3_000_000, 300_000, 100_000, 3, 700_000, 3, 400_000, 4,
                [*challenges, "counter_search"], "certified",
            ),
            "CRITICAL": _risk_band(
                4_000_000, 200_000, 50_000, 4, 800_000, 4, 500_000, 5,
                [*challenges, "counter_search", "failure_domain_review"],
                "distributed",
            ),
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
            "safe_fallback_candidate": fallback,
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


def _risk_band(
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
        "required_challenge_categories": deepcopy(challenges),
        "minimum_assurance": assurance,
        "publishable_outcomes": ["evidence_commit"],
        "executable_outcomes": [],
    }
