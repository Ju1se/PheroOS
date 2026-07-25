from __future__ import annotations

from copy import deepcopy
from importlib import import_module
from pathlib import Path

from pheroos.conformance._public_api import (
    COMPATIBILITY_MODULES as CONFORMANCE_COMPATIBILITY_MODULES,
)
from pheroos.conformance.public_api_lifecycle import (
    DEFAULT_REMOVE_AFTER,
    PUBLIC_API_GROUPS,
    PUBLIC_API_LIFECYCLE_PATH,
    PUBLIC_API_STABILITIES,
    build_public_api_lifecycle,
    load_public_api_lifecycle,
    public_api_lifecycle_differences,
    public_api_lifecycle_problems,
    render_public_api_lifecycle,
)
from pheroos.conformance.public_api_inventory import PUBLIC_PACKAGES


ROOT = Path(__file__).resolve().parents[2]


WP05_AUTHORITY_REPLACEMENTS = {
    # Hybrid replay authority.
    "HybridCollectiveStep": "pheroos.governance.VerifiedHybridSourceStepV2",
    "HybridReplayState": "pheroos.governance.VerifiedHybridReplayStateV2",
    "evaluate_hybrid_collective_step": (
        "pheroos.governance.evaluate_hybrid_collective_step_v2"
    ),
    "hybrid_collective_step_is_authoritative": (
        "pheroos.governance.VerifiedHybridSourceStepV2"
    ),
    "hybrid_replay_state_is_authoritative": (
        "pheroos.governance.hybrid_replay_state_is_current_v2"
    ),
    "replay_state_from_hybrid_step": (
        "pheroos.governance.advance_hybrid_replay_state_v2"
    ),
    # Commit replay, window, liveness, seal, and finality authority.
    "CommitReplayState": "pheroos.governance.VerifiedCommitReplayStateV2",
    "CommitWindowState": "pheroos.governance.VerifiedCommitDecisionStateV2",
    "CommitWindowSeal": "pheroos.governance.VerifiedCommitDecisionStateV2",
    "CommitLivenessInput": "pheroos.governance.VerifiedCommitDecisionSourceV2",
    "CommitFinalityVerification": ("pheroos.governance.VerifiedCommitFinalityInputV2"),
    "DecisionProgress": "pheroos.governance.VerifiedCommitDecisionStateV2",
    "DecisionOutcome": "pheroos.governance.VerifiedCommitDecisionStateV2",
    "initialize_commit_replay_state": (
        "pheroos.governance.prepare_commit_replay_advance_v2"
    ),
    "record_commit_replay_receipts": (
        "pheroos.governance.advance_commit_replay_state_v2"
    ),
    "commit_replay_state_is_authoritative": (
        "pheroos.governance.commit_replay_state_is_current_v2"
    ),
    "commit_replay_state_is_current": (
        "pheroos.governance.commit_replay_state_is_current_v2"
    ),
    "initialize_commit_window_state": (
        "pheroos.governance.prepare_commit_decision_initialize_v2"
    ),
    "advance_commit_window_state": (
        "pheroos.governance.prepare_commit_decision_successor_v2"
    ),
    "reset_commit_window_state": (
        "pheroos.governance.prepare_commit_decision_successor_v2"
    ),
    "restart_commit_window_epoch": (
        "pheroos.governance.prepare_commit_decision_successor_v2"
    ),
    "commit_window_state_is_authoritative": (
        "pheroos.governance.commit_decision_state_is_current_v2"
    ),
    "commit_window_state_is_current": (
        "pheroos.governance.commit_decision_state_is_current_v2"
    ),
    "commit_window_seal_for_state": (
        "pheroos.governance.require_current_commit_decision_state_v2"
    ),
    "commit_window_seal_is_authoritative": (
        "pheroos.governance.commit_decision_state_is_current_v2"
    ),
    "commit_window_seal_is_current": (
        "pheroos.governance.commit_decision_state_is_current_v2"
    ),
    "commit_window_seal_matches_receipt": (
        "pheroos.governance.require_current_commit_decision_state_v2"
    ),
    "issue_commit_liveness_input": (
        "pheroos.governance.prepare_commit_decision_successor_v2"
    ),
    "reduce_commit_liveness": "pheroos.governance.reduce_commit_decision_v2",
    "commit_liveness_input_is_authoritative": (
        "pheroos.governance.VerifiedCommitDecisionSourceV2"
    ),
    "decision_progress_is_authoritative": (
        "pheroos.governance.require_current_commit_decision_state_v2"
    ),
    "decision_outcome_is_authoritative": (
        "pheroos.governance.require_current_commit_decision_state_v2"
    ),
    "commit_finality_verification_is_authoritative": (
        "pheroos.governance.VerifiedCommitFinalityInputV2"
    ),
    # Risk authority.
    "RiskAssessmentChainState": "pheroos.governance.VerifiedRiskStateV2",
    "RiskAssessment": "pheroos.governance.VerifiedRiskStateV2",
    "CommitThresholdSnapshot": "pheroos.governance.VerifiedRiskStateV2",
    "initialize_risk_assessment_chain": (
        "pheroos.governance.prepare_risk_state_advance_v2"
    ),
    "issue_risk_assessment": "pheroos.governance.advance_risk_state_v2",
    "issue_commit_threshold_snapshot": "pheroos.governance.advance_risk_state_v2",
    "risk_assessment_chain_state_is_authoritative": (
        "pheroos.governance.risk_state_is_current_v2"
    ),
    "risk_assessment_chain_state_is_current": (
        "pheroos.governance.risk_state_is_current_v2"
    ),
    "risk_assessment_is_authoritative": ("pheroos.governance.risk_state_is_current_v2"),
    "risk_assessment_is_latest": "pheroos.governance.risk_state_is_current_v2",
    "commit_threshold_snapshot_is_authoritative": (
        "pheroos.governance.risk_state_is_current_v2"
    ),
    # Membership and Support authority.
    "EligiblePrincipalSnapshot": "pheroos.governance.VerifiedMembershipStateV2",
    "EligibleMembershipEpochState": ("pheroos.governance.VerifiedMembershipStateV2"),
    "SupportLeaseReplayState": "pheroos.governance.VerifiedSupportStateV2",
    "SupportLease": "pheroos.governance.VerifiedSupportStateV2",
    "SupportLeaseRevocation": "pheroos.governance.VerifiedSupportStateV2",
    "issue_eligible_principal_snapshot": (
        "pheroos.governance.commit_membership_epoch_v2"
    ),
    "eligible_principal_snapshot_is_authoritative": (
        "pheroos.governance.membership_state_is_current_v2"
    ),
    "eligible_membership_epoch_state_is_authoritative": (
        "pheroos.governance.membership_state_is_current_v2"
    ),
    "eligible_membership_epoch_state_is_current": (
        "pheroos.governance.membership_state_is_current_v2"
    ),
    "initialize_support_lease_replay_state": (
        "pheroos.governance.prepare_support_initialize_v2"
    ),
    "issue_support_lease": "pheroos.governance.prepare_support_issue_v2",
    "revoke_support_lease": "pheroos.governance.prepare_support_revoke_v2",
    "switch_support_lease": "pheroos.governance.prepare_support_switch_v2",
    "support_lease_is_authoritative": (
        "pheroos.governance.support_state_is_current_v2"
    ),
    "support_lease_revocation_is_authoritative": (
        "pheroos.governance.support_state_is_current_v2"
    ),
    "support_lease_replay_state_is_authoritative": (
        "pheroos.governance.support_state_is_current_v2"
    ),
    "support_lease_replay_state_is_current": (
        "pheroos.governance.support_state_is_current_v2"
    ),
    # Certificate, local receipt, and finality authority.  Portable readers
    # are intentionally not part of this cohort.
    "issue_local_commit_receipt": "pheroos.governance.advance_commit_decision_v2",
    "local_commit_receipt_is_authoritative": (
        "pheroos.governance.require_current_commit_decision_state_v2"
    ),
    "local_commit_receipt_matches": (
        "pheroos.governance.require_current_commit_decision_state_v2"
    ),
    "verify_local_commit_finality": (
        "pheroos.governance.prepare_commit_decision_successor_v2"
    ),
    "issue_evidence_commit_certificate": (
        "pheroos.governance.prepare_commit_certificate_v2"
    ),
    "verify_evidence_commit_finality": (
        "pheroos.governance.verified_commit_certificate_finality_input_v2"
    ),
    "issue_outcome_certificate": "pheroos.governance.advance_commit_decision_v2",
    "outcome_certificate_is_authoritative": (
        "pheroos.governance.require_current_commit_decision_state_v2"
    ),
    # Distributed process-local state and issuers.  Portable records and
    # independent verification remain data-only Draft surfaces.
    "DistributedCommitState": "pheroos.governance.VerifiedDistributedStateV2",
    "initialize_distributed_commit_state": (
        "pheroos.governance.prepare_distributed_epoch_v2"
    ),
    "record_witness_verifications": (
        "pheroos.governance.advance_distributed_commit_v2"
    ),
    "register_distributed_commit_certificate": (
        "pheroos.governance.advance_distributed_commit_v2"
    ),
    "transition_distributed_commit_epoch": (
        "pheroos.governance.prepare_distributed_epoch_v2"
    ),
    "distributed_commit_state_is_authoritative": (
        "pheroos.governance.distributed_state_is_current_v2"
    ),
    "distributed_commit_state_is_current": (
        "pheroos.governance.distributed_state_is_current_v2"
    ),
    "issue_distributed_commit_proposal": (
        "pheroos.governance.prepare_distributed_proposal_v2"
    ),
    "distributed_commit_proposal_is_authoritative": (
        "pheroos.governance.distributed_state_is_current_v2"
    ),
    "verify_quorum_witness": "pheroos.governance.prepare_distributed_witness_v2",
    "witness_verification_is_authoritative": (
        "pheroos.governance.distributed_state_is_current_v2"
    ),
    "issue_distributed_commit_certificate": (
        "pheroos.governance.prepare_distributed_certificate_v2"
    ),
    "distributed_commit_certificate_is_current_final": (
        "pheroos.governance.verified_distributed_commit_finality_input_v2"
    ),
    "verify_distributed_commit_finality": (
        "pheroos.governance.verified_distributed_commit_finality_input_v2"
    ),
    "evaluate_distributed_finality": (
        "pheroos.governance.verified_distributed_commit_finality_input_v2"
    ),
    "distributed_finality_decision_is_authoritative": (
        "pheroos.governance.verified_distributed_commit_finality_input_v2"
    ),
    "issue_epoch_transition_certificate": (
        "pheroos.governance.prepare_distributed_epoch_v2"
    ),
}

WP05_TCK_RUNNERS = {
    "run_governance_hybrid_replay_conformance_v2",
    "run_governance_commit_replay_conformance_v2",
    "run_governance_commit_decision_conformance_v2",
    "run_governance_risk_conformance_v2",
    "run_governance_support_conformance_v2",
    "run_governance_commit_certificate_conformance_v2",
    "run_governance_distributed_commit_conformance_v2",
}

WP05_PORTABLE_OR_HISTORICAL_SURFACES = {
    "LocalCommitReceipt",
    "EvidenceCommitCertificate",
    "OutcomeCertificate",
    "ReplayReceipt",
    "evidence_commit_certificate_body_root",
    "evidence_commit_certificate_fingerprint",
    "evidence_commit_certificate_from_payload",
    "evidence_commit_certificate_payload",
    "verify_evidence_commit_certificate",
    "local_commit_receipt_fingerprint",
    "local_commit_receipt_payload",
    "outcome_certificate_body_root",
    "outcome_certificate_fingerprint",
    "outcome_certificate_from_payload",
    "outcome_certificate_payload",
    "verify_outcome_certificate",
    "DistributedCommitProposal",
    "DistributedCommitCertificate",
    "DistributedFinalityDecision",
    "EpochTransitionCertificate",
    "QuorumWitness",
    "WitnessVerification",
    "WitnessReplayReceipt",
    "assemble_portable_distributed_commit_certificate",
    "distributed_commit_certificate_fingerprint",
    "distributed_commit_certificate_from_payload",
    "distributed_commit_certificate_payload",
    "distributed_commit_proposal_fingerprint",
    "distributed_commit_proposal_from_payload",
    "distributed_commit_proposal_payload",
    "distributed_finality_decision_fingerprint",
    "distributed_finality_decision_from_payload",
    "distributed_finality_decision_payload",
    "epoch_transition_certificate_body_root",
    "epoch_transition_certificate_fingerprint",
    "epoch_transition_certificate_from_payload",
    "epoch_transition_certificate_payload",
    "quorum_witness_fingerprint",
    "quorum_witness_from_payload",
    "quorum_witness_payload",
    "quorum_witness_signing_payload",
    "quorum_witness_signing_root",
    "verify_distributed_commit_certificate",
    "verify_distributed_commit_proposal",
    "verify_epoch_transition_certificate",
    "verify_portable_witness_verification",
    "witness_replay_receipt_fingerprint",
    "witness_replay_receipt_from_payload",
    "witness_replay_receipt_payload",
    "witness_verification_fingerprint",
    "witness_verification_from_payload",
    "witness_verification_payload",
}


def _entries(
    lifecycle: dict[str, object], package: str
) -> dict[str, dict[str, object]]:
    packages = lifecycle["packages"]
    assert isinstance(packages, dict)
    package_lifecycle = packages[package]
    assert isinstance(package_lifecycle, dict)
    exports = package_lifecycle["exports"]
    assert isinstance(exports, list)
    return {item["name"]: item for item in exports}


def test_checked_lifecycle_matches_every_export_and_has_no_orphans() -> None:
    expected = load_public_api_lifecycle(ROOT)

    assert expected == build_public_api_lifecycle(ROOT)
    assert public_api_lifecycle_problems(expected) == []
    assert set(expected["packages"]) == set(PUBLIC_PACKAGES)
    for package_name in PUBLIC_PACKAGES:
        module = import_module(package_name)
        entries = _entries(expected, package_name)
        assert set(entries) == set(module.__all__)
        assert all(item["package"] == package_name for item in entries.values())
        assert all(item["group"] in PUBLIC_API_GROUPS for item in entries.values())
        assert all(
            item["stability"] in PUBLIC_API_STABILITIES for item in entries.values()
        )
        assert all(item["since"] == "0.1.0" for item in entries.values())


def test_removal_ledger_marks_d07_through_d14_without_deprecating_valid_entrypoint() -> (
    None
):
    lifecycle = build_public_api_lifecycle(ROOT)
    driver = _entries(lifecycle, "pheroos.drivers")
    governance = _entries(lifecycle, "pheroos.governance")
    conformance = _entries(lifecycle, "pheroos.conformance")

    for name in (
        "DataProviderDriverDescriptor",
        "ModelDriverDescriptor",
        "SandboxDriverDescriptor",
        "StorageDriverDescriptor",
        "ToolDriverDescriptor",
    ):
        assert driver[name]["stability"] == "deprecated"
        assert driver[name]["replacement"] == "pheroos.drivers.DriverDescriptor"
        assert driver[name]["remove_after"] == DEFAULT_REMOVE_AFTER
    assert driver["DriverHealth"]["replacement"] == (
        "pheroos.drivers.DriverProbeResult"
    )
    assert governance["CanonicalTarget"]["replacement"] == (
        "pheroos.protocol.TargetSpec"
    )
    assert governance["RecoveryTrace"]["replacement"] == ("pheroos.trace.TraceEvent")
    assert governance["evaluate_hybrid_commit_evaluation"]["replacement"] == (
        "pheroos.governance.evaluate_hybrid_commit_step"
    )
    for name in (
        "canonical_commit_payload",
        "canonical_commit_set",
        "commit_payload_fingerprint",
    ):
        assert governance[name]["replacement"] == f"pheroos.protocol.{name}"

    run = conformance["run_conformance"]
    assert run["stability"] == "draft"
    assert run["remove_after"] is None
    assert run["replacement"] is None
    assert run["parameter_lifecycle"] == [
        {
            "name": "root",
            "stability": "deprecated",
            "replacement": "pheroos.conformance.run_source_conformance",
            "remove_after": DEFAULT_REMOVE_AFTER,
        }
    ]

    compatibility = {
        (item["package"], item["name"]): item
        for item in lifecycle["compatibility_surfaces"]
    }
    trace = compatibility[("pheroos.governance", "trace")]
    assert trace["stability"] == "deprecated"
    assert trace["replacement"] == "pheroos.trace"
    assert trace["remove_after"] == DEFAULT_REMOVE_AFTER

    conformance_compatibility = {
        name: item
        for (package, name), item in compatibility.items()
        if package == "pheroos.conformance"
    }
    assert set(conformance_compatibility) == {
        "checks",
        "commit_tck",
        "commit_tck_v2_protocol",
        "profile",
        "public_api_inventory",
        "public_api_lifecycle",
        "report",
        "runner",
    }
    assert set(conformance_compatibility) == set(CONFORMANCE_COMPATIBILITY_MODULES)
    for name, target in CONFORMANCE_COMPATIBILITY_MODULES.items():
        entry = conformance_compatibility[name]
        assert entry["replacement"] == target
        assert entry["stability"] == "draft"
        assert entry["remove_after"] is None


def test_wp05_deprecated_authority_cohort_has_exact_public_v2_replacements() -> None:
    lifecycle = build_public_api_lifecycle(ROOT)
    governance = _entries(lifecycle, "pheroos.governance")

    assert len(WP05_AUTHORITY_REPLACEMENTS) == 86
    for name, replacement in WP05_AUTHORITY_REPLACEMENTS.items():
        entry = governance[name]
        assert entry["group"] == "compatibility"
        assert entry["stability"] == "deprecated"
        assert entry["replacement"] == replacement
        assert entry["remove_after"] == DEFAULT_REMOVE_AFTER
        reason = entry["retained_with_reason"]
        assert isinstance(reason, str)
        assert "Draft v1" in reason
        assert "TCK-backed" in reason

        package_name, replacement_name = replacement.rsplit(".", 1)
        replacement_package = import_module(package_name)
        assert replacement_name in replacement_package.__all__


def test_wp05_deprecation_requires_a_public_reusable_v2_conformance_matrix() -> None:
    conformance = import_module("pheroos.conformance")

    assert WP05_TCK_RUNNERS <= set(conformance.__all__)
    assert all(callable(getattr(conformance, name)) for name in WP05_TCK_RUNNERS)


def test_wp05_portable_codecs_and_historical_verifiers_are_not_authority() -> None:
    lifecycle = build_public_api_lifecycle(ROOT)
    governance = _entries(lifecycle, "pheroos.governance")

    assert WP05_PORTABLE_OR_HISTORICAL_SURFACES.isdisjoint(WP05_AUTHORITY_REPLACEMENTS)
    for name in WP05_PORTABLE_OR_HISTORICAL_SURFACES:
        entry = governance[name]
        assert entry["stability"] == "draft"
        assert entry["replacement"] is None
        assert entry["remove_after"] is None


def test_lifecycle_rejects_missing_and_orphan_compatibility_surfaces() -> None:
    lifecycle = build_public_api_lifecycle(ROOT)
    malformed = deepcopy(lifecycle)
    surfaces = malformed["compatibility_surfaces"]
    surfaces[:] = [
        item
        for item in surfaces
        if (item["package"], item["name"]) != ("pheroos.conformance", "checks")
    ]
    surfaces.append(
        {
            "group": "compatibility",
            "name": "not_a_module",
            "package": "pheroos.conformance",
            "remove_after": None,
            "replacement": "pheroos.conformance.not_a_module",
            "retained_with_reason": "test-only orphan",
            "since": "0.1.0",
            "stability": "draft",
        }
    )

    problems = public_api_lifecycle_problems(malformed)

    assert "compatibility_surfaces:missing:pheroos.conformance:checks" in problems
    assert "compatibility_surfaces:orphan:pheroos.conformance:not_a_module" in problems


def test_lifecycle_rejects_missing_orphan_and_nonreferencable_replacement() -> None:
    lifecycle = build_public_api_lifecycle(ROOT)
    malformed = deepcopy(lifecycle)
    protocol = malformed["packages"]["pheroos.protocol"]
    removed = protocol["exports"].pop()
    protocol["exports"].append(
        {
            **removed,
            "name": "NoSuchExport",
            "stability": "deprecated",
            "replacement": "pheroos.protocol.NoSuchReplacement",
            "remove_after": DEFAULT_REMOVE_AFTER,
        }
    )

    problems = public_api_lifecycle_problems(malformed)

    assert any(
        item.startswith("package:pheroos.protocol:missing:") for item in problems
    )
    assert "package:pheroos.protocol:orphan:NoSuchExport" in problems
    assert "entry:pheroos.protocol.NoSuchExport:replacement" in problems


def test_lifecycle_checks_public_error_types_and_diagnostic_code_registry() -> None:
    lifecycle = build_public_api_lifecycle(ROOT)
    diagnostics = {
        (item["package"], item["family"], item["code"], item["kind"])
        for item in lifecycle["diagnostic_codes"]
    }
    authority_v2 = {
        item["code"]
        for item in lifecycle["diagnostic_codes"]
        if item["package"] == "pheroos.protocol"
        and item["family"] == "scoped-authority-v2"
        and item["kind"] == "exact"
        and item["owner"] == "pheroos.protocol.AuthorityDiagnosticCodeV2"
    }
    assert authority_v2 == {
        "authority_profile_unsupported",
        "authority_session_required",
        "authority_session_store_mismatch",
        "authority_scope_mismatch",
        "authority_operation_denied",
        "authority_binding_mismatch",
        "authority_grant_unverified",
        "authority_grant_expired",
        "authority_grant_revoked",
        "governance_read_set_invalid",
        "governance_read_set_stale",
        "governance_transition_conflict",
        "governance_domain_sealed",
        "governance_finality_unavailable",
        "governance_committed_transition_invalid",
        "governance_action_not_authorized",
        "governance_trace_lineage_invalid",
    }

    assert (
        "pheroos.protocol",
        "manifest-validation",
        "protocol_version_unsupported",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.kernel",
        "kernel-planning",
        "driver_probe_missing",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.protocol",
        "schema-document",
        "capability_schema_version_missing",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.protocol",
        "schema-document",
        "protocol_schema_version_unsupported",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.drivers",
        "driver-schema-document",
        "driver_descriptor_v1_not_migratable",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.drivers",
        "driver-schema-document",
        "driver_descriptor_version_missing",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.kernel",
        "kernel-plan-document",
        "kernel_plan_v1_driver_authority_missing",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.kernel",
        "kernel-plan-document",
        "kernel_plan_version_unsupported",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.kernel",
        "kernel-planning",
        "manifest_*",
        "prefix",
    ) in diagnostics
    assert (
        "pheroos.governance",
        "hybrid-commit-evaluation",
        "invalid_evaluation_request",
        "exact",
    ) in diagnostics
    assert (
        "pheroos.governance",
        "atomic-hybrid-commit",
        "governance_transition_committed",
        "exact",
    ) in diagnostics

    error_types = {(item["package"], item["name"]) for item in lifecycle["error_types"]}
    assert ("pheroos.protocol", "CommitWireError") in error_types
    assert ("pheroos.protocol", "ProtocolSchemaVersionError") in error_types
    assert ("pheroos.drivers", "DriverSchemaVersionError") in error_types
    assert ("pheroos.kernel", "KernelPlanVersionError") in error_types
    assert PUBLIC_API_LIFECYCLE_PATH.parts[:3] == (
        "pheroos",
        "conformance",
        "abi",
    )


def test_lifecycle_render_load_and_bounded_differences_are_checked(
    tmp_path: Path,
) -> None:
    lifecycle = build_public_api_lifecycle(ROOT)
    rendered = render_public_api_lifecycle(lifecycle)
    artifact = tmp_path / PUBLIC_API_LIFECYCLE_PATH
    artifact.parent.mkdir(parents=True)
    artifact.write_text(rendered, encoding="utf-8")

    assert rendered.endswith("\n")
    assert load_public_api_lifecycle(tmp_path) == lifecycle
    assert public_api_lifecycle_differences(
        {"one": 1, "two": 2},
        {"one": 3, "two": 4},
        limit=1,
    ) == ["$.one"]

    artifact.write_text("[]", encoding="utf-8")
    try:
        load_public_api_lifecycle(tmp_path)
    except ValueError as exc:
        assert str(exc) == "public API lifecycle artifact must be a JSON object"
    else:
        raise AssertionError("a non-object lifecycle artifact must fail closed")


def test_lifecycle_rejects_invalid_root_package_and_summary_shapes() -> None:
    lifecycle = build_public_api_lifecycle(ROOT)

    malformed = deepcopy(lifecycle)
    malformed["artifact_version"] = "invalid"
    malformed["groups"] = []
    malformed["stabilities"] = []
    problems = public_api_lifecycle_problems(malformed)
    assert {"artifact_version", "groups", "stabilities"} <= set(problems)

    malformed = deepcopy(lifecycle)
    malformed["packages"] = []
    assert "packages" in public_api_lifecycle_problems(malformed)

    for replacement, expected in (
        (None, "package:pheroos.protocol:invalid"),
        ({"exports": None}, "package:pheroos.protocol:exports_invalid"),
    ):
        malformed = deepcopy(lifecycle)
        malformed["packages"]["pheroos.protocol"] = replacement
        assert expected in public_api_lifecycle_problems(malformed)

    malformed = deepcopy(lifecycle)
    protocol = malformed["packages"]["pheroos.protocol"]
    protocol["exports"].append(None)
    assert (
        "package:pheroos.protocol:duplicate_or_invalid"
        in public_api_lifecycle_problems(malformed)
    )

    malformed = deepcopy(lifecycle)
    protocol = malformed["packages"]["pheroos.protocol"]
    protocol["exports"].append(deepcopy(protocol["exports"][0]))
    assert (
        "package:pheroos.protocol:duplicate_or_invalid"
        in public_api_lifecycle_problems(malformed)
    )

    malformed = deepcopy(lifecycle)
    malformed["packages"]["pheroos.protocol"]["export_count"] = -1
    assert "package:pheroos.protocol:count" in public_api_lifecycle_problems(malformed)

    malformed = deepcopy(lifecycle)
    malformed["summary"] = None
    assert "summary" in public_api_lifecycle_problems(malformed)

    malformed = deepcopy(lifecycle)
    malformed["summary"] = {
        "compatibility_surface_count": -1,
        "diagnostic_code_count": -1,
        "error_type_count": -1,
        "export_count": -1,
        "package_count": -1,
    }
    problems = public_api_lifecycle_problems(malformed)
    assert {
        "summary:compatibility_surface_count",
        "summary:diagnostic_code_count",
        "summary:error_type_count",
        "summary:export_count",
        "summary:package_count",
    } <= set(problems)


def test_lifecycle_rejects_invalid_entry_fields_and_transitions() -> None:
    lifecycle = build_public_api_lifecycle(ROOT)

    malformed = deepcopy(lifecycle)
    entry = malformed["packages"]["pheroos.protocol"]["exports"][0]
    del entry["group"]
    assert any(
        problem.endswith(":fields")
        for problem in public_api_lifecycle_problems(malformed)
    )

    malformed = deepcopy(lifecycle)
    entry = malformed["packages"]["pheroos.protocol"]["exports"][0]
    entry["unexpected"] = True
    assert any(
        problem.endswith(":fields")
        for problem in public_api_lifecycle_problems(malformed)
    )

    malformed = deepcopy(lifecycle)
    entry = malformed["packages"]["pheroos.protocol"]["exports"][0]
    original_name = entry["name"]
    entry.update(
        {
            "package": "pheroos.invalid",
            "name": "",
            "group": "invalid",
            "stability": "invalid",
            "since": "not-a-version",
            "replacement": 7,
            "remove_after": "not-a-version",
            "retained_with_reason": "   ",
        }
    )
    problems = public_api_lifecycle_problems(malformed)
    identity = "pheroos.protocol."
    assert {
        f"entry:{identity}:package",
        f"entry:{identity}:name",
        f"entry:{identity}:group",
        f"entry:{identity}:stability",
        f"entry:{identity}:since",
        f"entry:{identity}:replacement",
        f"entry:{identity}:remove_after",
        f"entry:{identity}:retained_with_reason",
    } <= set(problems)
    assert f"package:pheroos.protocol:missing:{original_name}" in problems

    malformed = deepcopy(lifecycle)
    entry = malformed["packages"]["pheroos.protocol"]["exports"][0]
    identity = f"pheroos.protocol.{entry['name']}"
    entry.update(
        {
            "stability": "deprecated",
            "since": "0.2.0",
            "replacement": None,
            "remove_after": None,
            "retained_with_reason": None,
        }
    )
    problems = public_api_lifecycle_problems(malformed)
    assert f"entry:{identity}:remove_after_missing" in problems
    assert f"entry:{identity}:replacement_missing" in problems

    malformed = deepcopy(lifecycle)
    entry = malformed["packages"]["pheroos.protocol"]["exports"][0]
    identity = f"pheroos.protocol.{entry['name']}"
    entry.update(
        {
            "stability": "deprecated",
            "since": "0.2.0",
            "replacement": "pheroos.protocol.TargetSpec",
            "remove_after": "0.1.0",
        }
    )
    assert f"entry:{identity}:remove_after_order" in public_api_lifecycle_problems(
        malformed
    )

    malformed = deepcopy(lifecycle)
    entry = malformed["packages"]["pheroos.protocol"]["exports"][0]
    identity = f"pheroos.protocol.{entry['name']}"
    entry["remove_after"] = "0.3.0"
    assert f"entry:{identity}:unexpected_remove_after" in public_api_lifecycle_problems(
        malformed
    )


def test_lifecycle_rejects_invalid_parameter_lifecycle_metadata() -> None:
    lifecycle = build_public_api_lifecycle(ROOT)
    conformance = {
        entry["name"]: entry
        for entry in lifecycle["packages"]["pheroos.conformance"]["exports"]
    }
    assert "root" in {
        item["name"] for item in conformance["run_conformance"]["parameter_lifecycle"]
    }

    malformed = deepcopy(lifecycle)
    entries = {
        entry["name"]: entry
        for entry in malformed["packages"]["pheroos.conformance"]["exports"]
    }
    entries["run_conformance"]["parameter_lifecycle"] = {}
    assert any(
        problem.endswith(":parameter_lifecycle")
        for problem in public_api_lifecycle_problems(malformed)
    )

    malformed = deepcopy(lifecycle)
    entries = {
        entry["name"]: entry
        for entry in malformed["packages"]["pheroos.conformance"]["exports"]
    }
    entries["run_conformance"]["parameter_lifecycle"] = [None, {"name": "root"}]
    problems = public_api_lifecycle_problems(malformed)
    assert any(problem.endswith(":parameter_invalid") for problem in problems)
    assert any(problem.endswith(":parameter_fields") for problem in problems)

    malformed = deepcopy(lifecycle)
    entries = {
        entry["name"]: entry
        for entry in malformed["packages"]["pheroos.conformance"]["exports"]
    }
    invalid_parameter = {
        "name": "",
        "stability": "draft",
        "replacement": "not-a-reference",
        "remove_after": "invalid",
    }
    valid_parameter = {
        "name": "root",
        "stability": "deprecated",
        "replacement": "pheroos.conformance.run_source_conformance",
        "remove_after": DEFAULT_REMOVE_AFTER,
    }
    entries["run_conformance"]["parameter_lifecycle"] = [
        invalid_parameter,
        valid_parameter,
        deepcopy(valid_parameter),
    ]
    problems = public_api_lifecycle_problems(malformed)
    assert any(problem.endswith(":parameter_name") for problem in problems)
    assert any(":parameter_orphan:" in problem for problem in problems)
    assert any(problem.endswith(":parameter_stability") for problem in problems)
    assert any(problem.endswith(":parameter_remove_after") for problem in problems)
    assert any(problem.endswith(":parameter_replacement") for problem in problems)
    assert any(problem.endswith(":parameter_duplicate") for problem in problems)


def test_lifecycle_rejects_invalid_compatibility_diagnostic_and_error_registries() -> (
    None
):
    lifecycle = build_public_api_lifecycle(ROOT)

    malformed = deepcopy(lifecycle)
    malformed["compatibility_surfaces"] = None
    assert "compatibility_surfaces" in public_api_lifecycle_problems(malformed)

    malformed = deepcopy(lifecycle)
    malformed["compatibility_surfaces"].append(None)
    assert "compatibility_surfaces:entry_invalid" in public_api_lifecycle_problems(
        malformed
    )

    malformed = deepcopy(lifecycle)
    malformed["compatibility_surfaces"].append(
        deepcopy(malformed["compatibility_surfaces"][0])
    )
    assert "compatibility_surfaces:duplicate" in public_api_lifecycle_problems(
        malformed
    )

    malformed = deepcopy(lifecycle)
    malformed["diagnostic_codes"] = None
    assert "diagnostic_codes" in public_api_lifecycle_problems(malformed)

    malformed = deepcopy(lifecycle)
    malformed["diagnostic_codes"] = [
        None,
        {
            "code": "prefix",
            "family": " ",
            "kind": "prefix",
            "owner": "not-a-reference",
            "package": "pheroos.invalid",
        },
        {
            "code": "duplicate",
            "family": "family",
            "kind": "invalid",
            "owner": "pheroos.protocol.TargetSpec",
            "package": "pheroos.protocol",
        },
        {
            "code": "duplicate",
            "family": "family",
            "kind": "invalid",
            "owner": "pheroos.protocol.TargetSpec",
            "package": "pheroos.protocol",
        },
    ]
    problems = public_api_lifecycle_problems(malformed)
    assert {
        "diagnostic_codes:fields",
        "diagnostic_codes:value",
        "diagnostic_codes:prefix:prefix",
        "diagnostic_codes:owner:not-a-reference",
        "diagnostic_codes:package:pheroos.invalid",
        "diagnostic_codes:kind:invalid",
        "diagnostic_codes:duplicate",
    } <= set(problems)

    malformed = deepcopy(lifecycle)
    malformed["error_types"] = None
    assert "error_types" in public_api_lifecycle_problems(malformed)

    malformed = deepcopy(lifecycle)
    malformed["error_types"] = [
        None,
        {
            "name": "NoSuchError",
            "owner": "invalid-owner",
            "package": "pheroos.invalid",
        },
        {
            "name": "NoSuchError",
            "owner": "invalid-owner",
            "package": "pheroos.invalid",
        },
    ]
    problems = public_api_lifecycle_problems(malformed)
    assert {
        "error_types:fields",
        "error_types:duplicate",
        "error_types:package:pheroos.invalid",
        "error_types:orphan:pheroos.invalid.NoSuchError",
        "error_types:owner:invalid-owner",
    } <= set(problems)
