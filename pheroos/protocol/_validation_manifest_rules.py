from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pheroos.protocol._validation_collective_rules import validate_collective_rules
from pheroos.protocol._validation_primitives import (
    canonical_nonblank_text,
    duplicate_values,
    positive_integer,
    validation_error,
)
from pheroos.protocol.extensions import secret_like_paths
from pheroos.protocol.models import (
    SUPPORTED_PROTOCOL_VERSIONS,
    CandidateSpec,
    CapabilityManifest,
    ProtocolManifest,
    ValidationDiagnostic,
)


_CommitPolicyValidator = Callable[[ProtocolManifest], list[ValidationDiagnostic]]


@dataclass(frozen=True)
class _ManifestValidationContext:
    manifest: CapabilityManifest
    protocol: ProtocolManifest
    target_ids: frozenset[str]
    candidate_ids: frozenset[str]
    candidates_by_id: dict[str, CandidateSpec]
    safe_candidates: frozenset[str]
    commit_policy_validator: _CommitPolicyValidator


_ManifestRule = Callable[[_ManifestValidationContext], list[ValidationDiagnostic]]


def validate_capability_manifest_v1_rules(
    manifest: CapabilityManifest,
    commit_policy_validator: _CommitPolicyValidator,
) -> list[ValidationDiagnostic]:
    """Evaluate the legacy manifest rules in their frozen diagnostic order."""

    context = _validation_context(manifest, commit_policy_validator)
    return [diagnostic for rule in _MANIFEST_RULES for diagnostic in rule(context)]


def _validation_context(
    manifest: CapabilityManifest,
    commit_policy_validator: _CommitPolicyValidator,
) -> _ManifestValidationContext:
    protocol = manifest.protocol
    return _ManifestValidationContext(
        manifest=manifest,
        protocol=protocol,
        target_ids=frozenset(target.id for target in protocol.targets),
        candidate_ids=frozenset(candidate.id for candidate in protocol.candidates),
        candidates_by_id={candidate.id: candidate for candidate in protocol.candidates},
        safe_candidates=frozenset(
            candidate.id for candidate in protocol.candidates if candidate.safe_fallback
        ),
        commit_policy_validator=commit_policy_validator,
    )


def _validate_protocol_version(
    context: _ManifestValidationContext,
) -> list[ValidationDiagnostic]:
    version = context.protocol.protocol_version
    if not canonical_nonblank_text(version):
        return [
            validation_error(
                "protocol_version_invalid",
                "protocol version must be canonical non-blank text",
                "protocol.protocol_version",
            )
        ]
    if version not in SUPPORTED_PROTOCOL_VERSIONS:
        return [
            validation_error(
                "protocol_version_unsupported",
                "protocol version is not explicitly supported",
                "protocol.protocol_version",
            )
        ]
    return []


def _validate_secret_fields(
    context: _ManifestValidationContext,
) -> list[ValidationDiagnostic]:
    return [
        validation_error(
            "secret_like_manifest_field",
            "manifest must not contain secret-like fields",
            secret_path,
        )
        for secret_path in secret_like_paths(context.manifest)
    ]


def _validate_declarations(
    context: _ManifestValidationContext,
) -> list[ValidationDiagnostic]:
    protocol = context.protocol
    diagnostics = [
        validation_error(
            "duplicate_target",
            f"target {target_id} is declared more than once",
            "protocol.targets",
        )
        for target_id in duplicate_values(target.id for target in protocol.targets)
    ]
    diagnostics.extend(
        validation_error(
            "duplicate_candidate",
            f"candidate {candidate_id} is declared more than once",
            "protocol.candidates",
        )
        for candidate_id in duplicate_values(
            candidate.id for candidate in protocol.candidates
        )
    )
    if not protocol.targets:
        diagnostics.append(
            validation_error(
                "missing_targets",
                "protocol must declare at least one target",
                "protocol.targets",
            )
        )
    if not protocol.candidates:
        diagnostics.append(
            validation_error(
                "missing_candidates",
                "protocol must declare at least one candidate",
                "protocol.candidates",
            )
        )
    diagnostics.extend(
        validation_error(
            "candidate_target_missing",
            f"candidate {candidate.id} references undeclared target",
            "protocol.candidates",
        )
        for candidate in protocol.candidates
        if candidate.target not in context.target_ids
    )
    return diagnostics


def _validate_quorum(
    context: _ManifestValidationContext,
) -> list[ValidationDiagnostic]:
    policy = context.protocol.quorum_policy
    target = policy.target
    fallback_id = policy.fallback_candidate
    diagnostics: list[ValidationDiagnostic] = []
    if not isinstance(target, str) or not target:
        diagnostics.append(
            validation_error(
                "quorum_target_invalid",
                "quorum target must be non-empty",
                "protocol.quorum_policy.target",
            )
        )
    elif target not in context.target_ids:
        diagnostics.append(
            validation_error(
                "quorum_target_missing",
                "quorum target must be declared",
                "protocol.quorum_policy.target",
            )
        )
    if not isinstance(fallback_id, str) or not fallback_id:
        diagnostics.append(
            validation_error(
                "quorum_fallback_invalid",
                "quorum fallback candidate must be non-empty",
                "protocol.quorum_policy.fallback_candidate",
            )
        )
    elif fallback_id not in context.candidate_ids:
        diagnostics.append(
            validation_error(
                "quorum_fallback_missing",
                "quorum fallback candidate must be declared",
                "protocol.quorum_policy.fallback_candidate",
            )
        )
    if not positive_integer(policy.commit_threshold):
        diagnostics.append(
            validation_error(
                "quorum_commit_threshold_invalid",
                "quorum commit threshold must be a positive integer",
                "protocol.quorum_policy.commit_threshold",
            )
        )
    if (
        isinstance(fallback_id, str)
        and fallback_id
        and fallback_id not in context.safe_candidates
    ):
        diagnostics.append(
            validation_error(
                "quorum_fallback_not_safe",
                "quorum fallback candidate must be marked safe_fallback",
                "protocol.quorum_policy.fallback_candidate",
            )
        )
    fallback = (
        context.candidates_by_id.get(fallback_id)
        if isinstance(fallback_id, str)
        else None
    )
    if fallback is not None and fallback.target != target:
        diagnostics.append(
            validation_error(
                "quorum_fallback_target_mismatch",
                "quorum fallback candidate must target the quorum target",
                "protocol.quorum_policy.fallback_candidate",
            )
        )
    return diagnostics


def _validate_signals(
    context: _ManifestValidationContext,
) -> list[ValidationDiagnostic]:
    return [
        validation_error(
            "signal_target_missing",
            f"signal {signal.type} references undeclared target",
            "protocol.signals",
        )
        for signal in context.protocol.signals
        if signal.target not in context.target_ids
    ]


def _validate_collective(
    context: _ManifestValidationContext,
) -> list[ValidationDiagnostic]:
    policy = context.protocol.collective_decision_policy
    if policy is None:
        return []
    return validate_collective_rules(
        context.protocol,
        policy,
        candidate_ids=context.candidate_ids,
        candidates_by_id=context.candidates_by_id,
        safe_candidates=context.safe_candidates,
    )


def _validate_collective_commit(
    context: _ManifestValidationContext,
) -> list[ValidationDiagnostic]:
    if context.protocol.collective_commit_policy is None:
        return []
    return context.commit_policy_validator(context.protocol)


def _validate_recovery(
    context: _ManifestValidationContext,
) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    for recovery in context.protocol.recovery_protocols:
        diagnostics.extend(
            validation_error(
                "recovery_target_missing",
                f"recovery target {target} is undeclared",
                "protocol.recovery_protocols",
            )
            for target in recovery.trigger_targets
            if target not in context.target_ids
        )
        if (
            recovery.failure_candidate
            and recovery.failure_candidate not in context.candidate_ids
        ):
            diagnostics.append(
                validation_error(
                    "recovery_failure_candidate_missing",
                    "recovery failure candidate must be declared",
                    "protocol.recovery_protocols",
                )
            )
        failure_candidate = context.candidates_by_id.get(recovery.failure_candidate)
        if failure_candidate is not None and failure_candidate.target not in set(
            recovery.trigger_targets
        ):
            diagnostics.append(
                validation_error(
                    "recovery_failure_candidate_target_mismatch",
                    "recovery failure candidate must target a recovery trigger target",
                    "protocol.recovery_protocols",
                )
            )
    return diagnostics


def _validate_output_policy(
    context: _ManifestValidationContext,
) -> list[ValidationDiagnostic]:
    policy = context.protocol.output_policy
    diagnostics: list[ValidationDiagnostic] = []
    if policy.writer_may_create_facts:
        diagnostics.append(
            validation_error(
                "writer_fact_creation",
                "output policy must not allow writer fact creation",
                "protocol.output_policy",
            )
        )
    diagnostics.extend(
        validation_error(
            "output_gate_disabled",
            "output authorization gates are mandatory and cannot be disabled",
            f"protocol.output_policy.{field_name}",
        )
        for field_name, enabled in (
            ("requires_committed_candidate", policy.requires_committed_candidate),
            ("requires_evidence_contract", policy.requires_evidence_contract),
            ("requires_stop_resolution", policy.requires_stop_resolution),
            (
                "requires_publication_permission",
                policy.requires_publication_permission,
            ),
        )
        if enabled is not True
    )
    return diagnostics


def _validate_evidence_policy(
    context: _ManifestValidationContext,
) -> list[ValidationDiagnostic]:
    if not context.protocol.evidence_policy.allow_agent_fact_creation:
        return []
    return [
        validation_error(
            "agent_fact_creation",
            "evidence policy must not allow agent fact creation",
            "protocol.evidence_policy",
        )
    ]


def _validate_trace_policy(
    context: _ManifestValidationContext,
) -> list[ValidationDiagnostic]:
    missing = sorted(
        {"block", "commit", "recovery", "output"}
        - set(context.protocol.trace_policy.required_events)
    )
    if not missing:
        return []
    return [
        validation_error(
            "trace_lineage_incomplete",
            f"trace policy missing events: {', '.join(missing)}",
            "protocol.trace_policy",
        )
    ]


_MANIFEST_RULES: tuple[_ManifestRule, ...] = (
    _validate_protocol_version,
    _validate_secret_fields,
    _validate_declarations,
    _validate_quorum,
    _validate_signals,
    _validate_collective,
    _validate_collective_commit,
    _validate_recovery,
    _validate_output_policy,
    _validate_evidence_policy,
    _validate_trace_policy,
)
