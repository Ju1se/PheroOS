from __future__ import annotations

from typing import cast

from pheroos.protocol._validation_commit_constants import (
    CERTIFICATE_MODE_BY_ASSURANCE,
    NON_PUBLISHABLE_TERMINAL_OUTCOMES,
)
from pheroos.protocol._validation_commit_primitives import (
    authority_integer,
    authority_integer_in_range,
)
from pheroos.protocol._validation_primitives import (
    canonical_nonblank_text,
    canonical_string_set,
    validation_error,
)
from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_WIRE_VERSION,
    MAX_AUTHORITY_INTEGER,
    SUPPORTED_CERTIFICATE_MODES,
    SUPPORTED_DEADLINE_OUTCOMES,
    SUPPORTED_TERMINAL_OUTCOMES,
    CertificatePolicy,
    DistributedCommitPolicy,
    TerminalOutcomePolicy,
)
from pheroos.protocol.models import ValidationDiagnostic


def validate_terminal_outcome_policy(
    policy: object,
    *,
    assurance: object,
    path: str,
) -> list[ValidationDiagnostic]:
    if not isinstance(policy, TerminalOutcomePolicy):
        return [
            validation_error(
                "commit_terminal_policy_type_invalid",
                "terminal outcome policy must use the canonical Protocol ABI declaration",
                path,
            )
        ]
    diagnostics = _terminal_identity_diagnostics(policy, path=path)
    diagnostics.extend(_terminal_set_diagnostics(policy, path=path))
    diagnostics.extend(
        _terminal_authority_diagnostics(policy, assurance=assurance, path=path)
    )
    return diagnostics


def _terminal_identity_diagnostics(
    policy: TerminalOutcomePolicy,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    if not canonical_nonblank_text(policy.safe_fallback_candidate):
        diagnostics.append(
            validation_error(
                "commit_fallback_invalid",
                "safe fallback candidate must be canonical and non-blank",
                f"{path}.safe_fallback_candidate",
            )
        )
    if policy.deadline_outcome not in SUPPORTED_DEADLINE_OUTCOMES:
        diagnostics.append(
            validation_error(
                "commit_deadline_outcome_invalid",
                "deadline outcome must be safe_fallback or advisory",
                f"{path}.deadline_outcome",
            )
        )
    if policy.policy_incomplete_outcome != "invalid":
        diagnostics.append(
            validation_error(
                "commit_policy_incomplete_outcome_invalid",
                "policy-incomplete runs must terminate as invalid",
                f"{path}.policy_incomplete_outcome",
            )
        )
    if policy.finality_unavailable_outcome != "finality_unavailable":
        diagnostics.append(
            validation_error(
                "commit_finality_outcome_invalid",
                "missing finality must remain a typed finality_unavailable outcome",
                f"{path}.finality_unavailable_outcome",
            )
        )
    return diagnostics


def _terminal_set_diagnostics(
    policy: TerminalOutcomePolicy,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    for name, outcomes in (
        ("deliverable_outcomes", policy.deliverable_outcomes),
        ("publishable_outcomes", policy.publishable_outcomes),
        ("executable_outcomes", policy.executable_outcomes),
    ):
        if not canonical_string_set(outcomes) or not set(outcomes).issubset(
            SUPPORTED_TERMINAL_OUTCOMES
        ):
            diagnostics.append(
                validation_error(
                    "commit_terminal_outcomes_invalid",
                    f"{name} must contain unique supported terminal outcomes",
                    f"{path}.{name}",
                )
            )
    if set(policy.deliverable_outcomes) != set(SUPPORTED_TERMINAL_OUTCOMES):
        diagnostics.append(
            validation_error(
                "commit_terminal_totality_incomplete",
                "every terminal outcome must remain deliverable",
                f"{path}.deliverable_outcomes",
            )
        )
    if set(policy.publishable_outcomes) & NON_PUBLISHABLE_TERMINAL_OUTCOMES:
        diagnostics.append(
            validation_error(
                "commit_terminal_publication_unsafe",
                "invalid, finality-unavailable, and safety-violation outcomes cannot authorize publication",
                f"{path}.publishable_outcomes",
            )
        )
    if not set(policy.executable_outcomes).issubset({"evidence_commit"}):
        diagnostics.append(
            validation_error(
                "commit_terminal_execution_unsafe",
                "only an evidence commit may be execution-eligible",
                f"{path}.executable_outcomes",
            )
        )
    return diagnostics


def _terminal_authority_diagnostics(
    policy: TerminalOutcomePolicy,
    *,
    assurance: object,
    path: str,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    if assurance == "advisory" and (
        policy.publishable_outcomes or policy.executable_outcomes
    ):
        diagnostics.append(
            validation_error(
                "commit_advisory_authority_invalid",
                "advisory assurance cannot authorize publication or execution",
                path,
            )
        )
    return diagnostics


def validate_certificate_policy(
    policy: object,
    *,
    assurance: object,
    path: str,
) -> list[ValidationDiagnostic]:
    if not isinstance(policy, CertificatePolicy):
        return [
            validation_error(
                "commit_certificate_policy_type_invalid",
                "certificate policy must use the canonical Protocol ABI declaration",
                path,
            )
        ]
    diagnostics: list[ValidationDiagnostic] = []
    if policy.mode not in SUPPORTED_CERTIFICATE_MODES:
        diagnostics.append(
            validation_error(
                "commit_certificate_mode_invalid",
                "certificate mode is unsupported",
                f"{path}.mode",
            )
        )
    expected_mode = CERTIFICATE_MODE_BY_ASSURANCE.get(cast(str, assurance))
    if expected_mode is not None and policy.mode != expected_mode:
        diagnostics.append(
            validation_error(
                "commit_certificate_assurance_mismatch",
                "certificate mode must exactly match the declared assurance",
                f"{path}.mode",
            )
        )
    if policy.wire_version != COMMIT_WIRE_VERSION:
        diagnostics.append(
            validation_error(
                "commit_wire_version_unsupported",
                "commit wire version is unsupported",
                f"{path}.wire_version",
            )
        )
    if policy.canonicalization != COMMIT_CANONICAL_VERSION:
        diagnostics.append(
            validation_error(
                "commit_canonical_version_unsupported",
                "commit canonicalization version is unsupported",
                f"{path}.canonicalization",
            )
        )
    if policy.hash_algorithm != "sha256":
        diagnostics.append(
            validation_error(
                "commit_hash_algorithm_unsupported",
                "commit hash algorithm must be sha256",
                f"{path}.hash_algorithm",
            )
        )
    requires_portable = assurance in {"certified", "distributed"}
    if policy.issuer_attestation_required is not requires_portable:
        diagnostics.append(
            validation_error(
                "commit_certificate_issuer_requirement_invalid",
                "issuer attestation requirement must match the assurance",
                f"{path}.issuer_attestation_required",
            )
        )
    if policy.independent_verification_required is not requires_portable:
        diagnostics.append(
            validation_error(
                "commit_certificate_verification_requirement_invalid",
                "independent verification requirement must match the assurance",
                f"{path}.independent_verification_required",
            )
        )
    return diagnostics


def validate_distributed_commit_policy(
    policy: object,
    *,
    assurance: object,
    path: str,
) -> list[ValidationDiagnostic]:
    if assurance != "distributed":
        return _inactive_distributed_policy_diagnostics(policy, path=path)
    if not isinstance(policy, DistributedCommitPolicy):
        return [
            validation_error(
                "commit_distributed_policy_required",
                "distributed assurance requires the complete distributed policy",
                path,
            )
        ]
    diagnostics = _distributed_declaration_diagnostics(policy, path=path)
    diagnostics.extend(_distributed_numeric_diagnostics(policy, path=path))
    diagnostics.extend(_distributed_topology_diagnostics(policy, path=path))
    return diagnostics


def _inactive_distributed_policy_diagnostics(
    policy: object,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    if policy is None:
        return []
    return [
        validation_error(
            "commit_distributed_policy_inactive",
            "distributed policy is only valid for distributed assurance",
            path,
        )
    ]


def _distributed_declaration_diagnostics(
    policy: DistributedCommitPolicy,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    if policy.fault_model != "byzantine_static_v1":
        diagnostics.append(
            validation_error(
                "commit_fault_model_invalid",
                "distributed commit must use the normative static Byzantine fault model",
                f"{path}.fault_model",
            )
        )
    if policy.membership_mode != "static_epoch_verified_clusters_v1":
        diagnostics.append(
            validation_error(
                "commit_membership_mode_invalid",
                "distributed commit must use static epoch verified clusters",
                f"{path}.membership_mode",
            )
        )
    if policy.conflict_rule != "freeze_v1":
        diagnostics.append(
            validation_error(
                "commit_conflict_rule_invalid",
                "distributed conflicts must freeze finality",
                f"{path}.conflict_rule",
            )
        )
    if not canonical_nonblank_text(policy.epoch_transition_rule):
        diagnostics.append(
            validation_error(
                "commit_epoch_transition_rule_invalid",
                "epoch transition rule must be canonical and non-blank",
                f"{path}.epoch_transition_rule",
            )
        )
    return diagnostics


def _distributed_numeric_diagnostics(
    policy: DistributedCommitPolicy,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    for name, value, minimum in (
        ("membership_size", policy.membership_size, 1),
        ("max_byzantine_faults", policy.max_byzantine_faults, 0),
        ("witness_quorum", policy.witness_quorum, 1),
        ("witness_ttl_steps", policy.witness_ttl_steps, 1),
        (
            "minimum_failure_domain_diversity",
            policy.minimum_failure_domain_diversity,
            1,
        ),
    ):
        if not authority_integer_in_range(value, minimum, MAX_AUTHORITY_INTEGER):
            diagnostics.append(
                validation_error(
                    "commit_distributed_numeric_invalid",
                    f"{name} is outside the declared commit numeric bounds",
                    f"{path}.{name}",
                )
            )
    return diagnostics


def _distributed_topology_diagnostics(
    policy: DistributedCommitPolicy,
    *,
    path: str,
) -> list[ValidationDiagnostic]:
    values = (
        policy.membership_size,
        policy.max_byzantine_faults,
        policy.witness_quorum,
    )
    if not all(authority_integer(value) for value in values):
        return []
    diagnostics: list[ValidationDiagnostic] = []
    n = policy.membership_size
    f = policy.max_byzantine_faults
    q = policy.witness_quorum
    if n < 3 * f + 1:
        diagnostics.append(
            validation_error(
                "commit_byzantine_membership_invalid",
                "membership must satisfy n >= 3f + 1",
                path,
            )
        )
    if q > n - f:
        diagnostics.append(
            validation_error(
                "commit_witness_quorum_too_large",
                "witness quorum must satisfy q <= n - f",
                path,
            )
        )
    if 2 * q - n <= f:
        diagnostics.append(
            validation_error(
                "commit_quorum_intersection_invalid",
                "witness quorum must satisfy 2q - n > f",
                path,
            )
        )
    if (
        authority_integer(policy.minimum_failure_domain_diversity)
        and policy.minimum_failure_domain_diversity > q
    ):
        diagnostics.append(
            validation_error(
                "commit_failure_domain_diversity_unreachable",
                "failure-domain diversity cannot exceed the witness quorum",
                f"{path}.minimum_failure_domain_diversity",
            )
        )
    return diagnostics
