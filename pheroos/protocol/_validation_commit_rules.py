from __future__ import annotations

from collections.abc import Mapping

from pheroos.protocol._validation_commit_constants import (
    COMMIT_CRITICAL_EXTENSION_PREFIXES,
)
from pheroos.protocol._validation_commit_finality_rules import (
    validate_certificate_policy,
    validate_distributed_commit_policy,
    validate_terminal_outcome_policy,
)
from pheroos.protocol._validation_commit_primitives import (
    authority_integer,
    authority_integer_in_range,
)
from pheroos.protocol._validation_commit_risk_rules import validate_risk_bands
from pheroos.protocol._validation_primitives import (
    canonical_nonblank_text,
    canonical_string_set,
    validation_error,
)
from pheroos.protocol.commit_models import (
    COMMIT_MODEL,
    COMMIT_POLICY_VERSION,
    MAX_AUTHORITY_INTEGER,
    REQUIRED_COMMIT_RESET_RULES,
    SUPPORTED_COMMIT_ASSURANCES,
    WEIGHT_SCALE,
    CollectiveCommitPolicy,
    CommitWindowPolicy,
    EvidenceQualificationPolicy,
    SupportLeasePolicy,
    TerminalOutcomePolicy,
)
from pheroos.protocol.extensions import is_namespaced_extension
from pheroos.protocol.models import (
    ProtocolManifest,
    ValidationDiagnostic,
    collective_fallback_id,
)


def validate_collective_commit_policy(
    protocol: ProtocolManifest,
) -> list[ValidationDiagnostic]:
    policy = protocol.collective_commit_policy
    path = "protocol.collective_commit_policy"
    if not isinstance(policy, CollectiveCommitPolicy):
        return [
            validation_error(
                "commit_policy_type_invalid",
                "collective commit policy must use the canonical Protocol ABI declaration",
                path,
            )
        ]

    diagnostics = _commit_identity_diagnostics(policy, path=path)
    diagnostics.extend(_commit_extension_diagnostics(policy, path=path))
    diagnostics.extend(_commit_target_diagnostics(protocol, policy, path=path))
    diagnostics.extend(_commit_component_diagnostics(policy, path=path))
    diagnostics.extend(_validate_commit_fallback_binding(protocol, policy, path))
    if protocol.evidence_policy.require_provenance is not True:
        diagnostics.append(
            validation_error(
                "commit_manifest_provenance_required",
                "collective commit requires protocol evidence provenance",
                "protocol.evidence_policy.require_provenance",
            )
        )
    diagnostics.extend(validate_risk_bands(policy, path=f"{path}.risk_bands"))
    return diagnostics


def _commit_identity_diagnostics(
    policy: CollectiveCommitPolicy,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    if policy.policy_version != COMMIT_POLICY_VERSION:
        diagnostics.append(
            validation_error(
                "commit_policy_version_unsupported",
                "collective commit policy version is unsupported",
                f"{path}.policy_version",
            )
        )
    if policy.model != COMMIT_MODEL:
        diagnostics.append(
            validation_error(
                "commit_model_unsupported",
                "collective commit model is unsupported",
                f"{path}.model",
            )
        )
    if policy.assurance not in SUPPORTED_COMMIT_ASSURANCES:
        diagnostics.append(
            validation_error(
                "commit_assurance_unsupported",
                "collective commit assurance is unsupported",
                f"{path}.assurance",
            )
        )
    if not canonical_nonblank_text(policy.target):
        diagnostics.append(
            validation_error(
                "commit_target_invalid",
                "collective commit target must be canonical and non-blank",
                f"{path}.target",
            )
        )
    return diagnostics


def _commit_extension_diagnostics(
    policy: CollectiveCommitPolicy,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    extension_owners = (
        (policy, path),
        (policy.evidence_qualification, f"{path}.evidence_qualification"),
        (policy.support_lease, f"{path}.support_lease"),
        (policy.commit_window, f"{path}.commit_window"),
        (policy.terminal_outcome, f"{path}.terminal_outcome"),
        (policy.certificate, f"{path}.certificate"),
        *(
            (band, f"{path}.risk_bands.{name}")
            for name, band in policy.risk_bands.items()
        ),
    )
    if policy.distributed is not None:
        extension_owners = (
            *extension_owners,
            (policy.distributed, f"{path}.distributed"),
        )
    diagnostics: list[ValidationDiagnostic] = []
    for owner, owner_path in extension_owners:
        diagnostics.extend(
            validate_commit_extensions(
                getattr(owner, "extensions", None),
                path=f"{owner_path}.extensions",
            )
        )
    return diagnostics


def _commit_target_diagnostics(
    protocol: ProtocolManifest,
    policy: CollectiveCommitPolicy,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    target_ids = {target.id for target in protocol.targets}
    if policy.target not in target_ids:
        diagnostics.append(
            validation_error(
                "commit_target_missing",
                "collective commit target must be declared",
                f"{path}.target",
            )
        )
    if policy.target != protocol.quorum_policy.target:
        diagnostics.append(
            validation_error(
                "commit_target_mismatch",
                "collective commit and quorum targets must match exactly",
                f"{path}.target",
            )
        )
    return diagnostics


def _commit_component_diagnostics(
    policy: CollectiveCommitPolicy,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    diagnostics.extend(
        validate_evidence_qualification_policy(
            policy.evidence_qualification, path=f"{path}.evidence_qualification"
        )
    )
    diagnostics.extend(
        validate_support_lease_policy(
            policy.support_lease, path=f"{path}.support_lease"
        )
    )
    diagnostics.extend(
        validate_commit_window_policy(
            policy.commit_window, path=f"{path}.commit_window"
        )
    )
    diagnostics.extend(
        validate_terminal_outcome_policy(
            policy.terminal_outcome,
            assurance=policy.assurance,
            path=f"{path}.terminal_outcome",
        )
    )
    diagnostics.extend(
        validate_certificate_policy(
            policy.certificate,
            assurance=policy.assurance,
            path=f"{path}.certificate",
        )
    )
    diagnostics.extend(
        validate_distributed_commit_policy(
            policy.distributed,
            assurance=policy.assurance,
            path=f"{path}.distributed",
        )
    )
    return diagnostics


def _validate_commit_fallback_binding(
    protocol: ProtocolManifest,
    policy: CollectiveCommitPolicy,
    path: str,
) -> list[ValidationDiagnostic]:
    terminal = policy.terminal_outcome
    if not isinstance(terminal, TerminalOutcomePolicy):
        return []
    fallback_id = terminal.safe_fallback_candidate
    fallback_path = f"{path}.terminal_outcome.safe_fallback_candidate"
    candidates_by_id = {candidate.id: candidate for candidate in protocol.candidates}
    safe_candidates = {
        candidate.id for candidate in protocol.candidates if candidate.safe_fallback
    }
    diagnostics: list[ValidationDiagnostic] = []
    if fallback_id != protocol.quorum_policy.fallback_candidate:
        diagnostics.append(
            validation_error(
                "commit_fallback_quorum_mismatch",
                "collective commit and quorum fallbacks must match exactly",
                fallback_path,
            )
        )
    if (
        protocol.collective_decision_policy is not None
        and fallback_id != collective_fallback_id(protocol)
    ):
        diagnostics.append(
            validation_error(
                "commit_fallback_collective_mismatch",
                "collective commit and collective decision fallbacks must match exactly",
                fallback_path,
            )
        )
    fallback = candidates_by_id.get(fallback_id)
    if fallback is None:
        diagnostics.append(
            validation_error(
                "commit_fallback_missing",
                "collective commit fallback candidate must be declared",
                fallback_path,
            )
        )
    elif fallback_id not in safe_candidates:
        diagnostics.append(
            validation_error(
                "commit_fallback_not_safe",
                "collective commit fallback candidate must be marked safe",
                fallback_path,
            )
        )
    elif fallback.target != policy.target:
        diagnostics.append(
            validation_error(
                "commit_fallback_target_mismatch",
                "collective commit fallback must target the active commit target",
                fallback_path,
            )
        )
    return diagnostics


def validate_commit_extensions(
    extensions: object,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    """Keep optional metadata open without accepting unknown critical semantics."""

    if not isinstance(extensions, Mapping):
        return [
            validation_error(
                "commit_extensions_type_invalid",
                "commit extensions must be a namespaced metadata object",
                path,
            )
        ]
    diagnostics: list[ValidationDiagnostic] = []
    for key in extensions:
        if not isinstance(key, str) or not is_namespaced_extension(key):
            diagnostics.append(
                validation_error(
                    "commit_extension_namespace_invalid",
                    "commit extension keys must use x- or ext. namespaces",
                    f"{path}.{key}",
                )
            )
            continue
        normalized = key.lower()
        if any(
            normalized == prefix
            or normalized.startswith(prefix + "-")
            or normalized.startswith(prefix + ".")
            for prefix in COMMIT_CRITICAL_EXTENSION_PREFIXES
        ):
            diagnostics.append(
                validation_error(
                    "commit_unknown_critical_extension",
                    "unknown critical commit extensions require a new supported ABI version",
                    f"{path}.{key}",
                )
            )
    return diagnostics


def validate_evidence_qualification_policy(
    policy: object,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    if not isinstance(policy, EvidenceQualificationPolicy):
        return [
            validation_error(
                "commit_evidence_policy_type_invalid",
                "evidence qualification must use the canonical Protocol ABI declaration",
                path,
            )
        ]
    diagnostics: list[ValidationDiagnostic] = []
    if policy.numeric_scale != WEIGHT_SCALE:
        diagnostics.append(
            validation_error(
                "commit_numeric_scale_invalid",
                "commit numeric scale must use the v1 fixed-point scale",
                f"{path}.numeric_scale",
            )
        )
    for name, value, minimum, maximum in (
        ("minimum_quality_ppm", policy.minimum_quality_ppm, 0, WEIGHT_SCALE),
        ("minimum_relevance_ppm", policy.minimum_relevance_ppm, 0, WEIGHT_SCALE),
        ("positive_group_cap", policy.positive_group_cap, 1, MAX_AUTHORITY_INTEGER),
        ("counter_group_cap", policy.counter_group_cap, 1, MAX_AUTHORITY_INTEGER),
        ("counter_weight_ppm", policy.counter_weight_ppm, 1, MAX_AUTHORITY_INTEGER),
        (
            "minimum_positive_evidence",
            policy.minimum_positive_evidence,
            1,
            MAX_AUTHORITY_INTEGER,
        ),
        (
            "maximum_counterevidence",
            policy.maximum_counterevidence,
            0,
            MAX_AUTHORITY_INTEGER,
        ),
        (
            "maximum_counterevidence_ratio_ppm",
            policy.maximum_counterevidence_ratio_ppm,
            0,
            WEIGHT_SCALE,
        ),
        (
            "domain_contribution_floor",
            policy.domain_contribution_floor,
            1,
            MAX_AUTHORITY_INTEGER,
        ),
        (
            "minimum_source_diversity",
            policy.minimum_source_diversity,
            1,
            MAX_AUTHORITY_INTEGER,
        ),
        (
            "observation_ttl_steps",
            policy.observation_ttl_steps,
            1,
            MAX_AUTHORITY_INTEGER,
        ),
    ):
        if not authority_integer_in_range(value, minimum, maximum):
            diagnostics.append(
                validation_error(
                    "commit_evidence_numeric_invalid",
                    f"{name} is outside the declared commit numeric bounds",
                    f"{path}.{name}",
                )
            )
    if not canonical_string_set(
        policy.required_challenge_categories, require_nonempty=True
    ):
        diagnostics.append(
            validation_error(
                "commit_challenge_categories_invalid",
                "required challenge categories must be unique canonical strings",
                f"{path}.required_challenge_categories",
            )
        )
    if policy.require_provenance is not True:
        diagnostics.append(
            validation_error(
                "commit_evidence_provenance_required",
                "commit evidence provenance cannot be disabled",
                f"{path}.require_provenance",
            )
        )
    if policy.require_trace is not True:
        diagnostics.append(
            validation_error(
                "commit_evidence_trace_required",
                "commit evidence trace lineage cannot be disabled",
                f"{path}.require_trace",
            )
        )
    return diagnostics


def validate_support_lease_policy(
    policy: object,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    if not isinstance(policy, SupportLeasePolicy):
        return [
            validation_error(
                "commit_support_policy_type_invalid",
                "support lease policy must use the canonical Protocol ABI declaration",
                path,
            )
        ]
    diagnostics: list[ValidationDiagnostic] = []
    for name, value, minimum, maximum in (
        (
            "minimum_support_clusters",
            policy.minimum_support_clusters,
            1,
            MAX_AUTHORITY_INTEGER,
        ),
        ("support_ratio_ppm", policy.support_ratio_ppm, 1, WEIGHT_SCALE),
        ("lease_ttl_steps", policy.lease_ttl_steps, 1, MAX_AUTHORITY_INTEGER),
    ):
        if not authority_integer_in_range(value, minimum, maximum):
            diagnostics.append(
                validation_error(
                    "commit_support_numeric_invalid",
                    f"{name} is outside the declared commit numeric bounds",
                    f"{path}.{name}",
                )
            )
    for name, observed, required in (
        ("membership_mode", policy.membership_mode, "verified_snapshot_v1"),
        ("switch_mode", policy.switch_mode, "revoke_then_issue_v1"),
        ("equivocation_mode", policy.equivocation_mode, "exclude_conflicts_v1"),
    ):
        if observed != required:
            diagnostics.append(
                validation_error(
                    "commit_support_semantics_invalid",
                    f"{name} must use the normative v1 mode",
                    f"{path}.{name}",
                )
            )
    if policy.evidence_reference_required is not True:
        diagnostics.append(
            validation_error(
                "commit_support_evidence_reference_required",
                "support leases must reference qualified evidence",
                f"{path}.evidence_reference_required",
            )
        )
    if policy.cluster_verification_required is not True:
        diagnostics.append(
            validation_error(
                "commit_support_cluster_verification_required",
                "support leases must use verified principal clusters",
                f"{path}.cluster_verification_required",
            )
        )
    return diagnostics


def validate_commit_window_policy(
    policy: object,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    if not isinstance(policy, CommitWindowPolicy):
        return [
            validation_error(
                "commit_window_policy_type_invalid",
                "commit window policy must use the canonical Protocol ABI declaration",
                path,
            )
        ]
    diagnostics: list[ValidationDiagnostic] = []
    for name, value, minimum in (
        ("minimum_stability_steps", policy.minimum_stability_steps, 1),
        ("deliberation_deadline_steps", policy.deliberation_deadline_steps, 1),
        ("maximum_leader_resets", policy.maximum_leader_resets, 0),
        ("maximum_epoch_restarts", policy.maximum_epoch_restarts, 0),
        ("run_deadline_steps", policy.run_deadline_steps, 1),
    ):
        if not authority_integer_in_range(value, minimum, MAX_AUTHORITY_INTEGER):
            diagnostics.append(
                validation_error(
                    "commit_window_numeric_invalid",
                    f"{name} is outside the declared commit numeric bounds",
                    f"{path}.{name}",
                )
            )
    if set(policy.reset_rules) != set(
        REQUIRED_COMMIT_RESET_RULES
    ) or not canonical_string_set(policy.reset_rules, require_nonempty=True):
        diagnostics.append(
            validation_error(
                "commit_window_reset_rules_invalid",
                "commit window reset rules must exactly cover every normative reset condition",
                f"{path}.reset_rules",
            )
        )
    if (
        authority_integer(policy.minimum_stability_steps)
        and authority_integer(policy.deliberation_deadline_steps)
        and policy.minimum_stability_steps > policy.deliberation_deadline_steps
    ):
        diagnostics.append(
            validation_error(
                "commit_window_unreachable",
                "minimum stability cannot exceed the deliberation deadline",
                path,
            )
        )
    if (
        authority_integer(policy.deliberation_deadline_steps)
        and authority_integer(policy.run_deadline_steps)
        and policy.deliberation_deadline_steps > policy.run_deadline_steps
    ):
        diagnostics.append(
            validation_error(
                "commit_deadline_order_invalid",
                "deliberation deadline cannot exceed the absolute run deadline",
                path,
            )
        )
    return diagnostics
