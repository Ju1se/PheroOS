from __future__ import annotations

from pheroos.protocol.models import CapabilityManifest, ValidationDiagnostic


def validate_capability_manifest(manifest: CapabilityManifest) -> list[ValidationDiagnostic]:
    diagnostics: list[ValidationDiagnostic] = []
    protocol = manifest.protocol
    target_ids = {target.id for target in protocol.targets}
    candidate_ids = {candidate.id for candidate in protocol.candidates}
    safe_candidates = {candidate.id for candidate in protocol.candidates if candidate.safe_fallback}

    if not protocol.targets:
        diagnostics.append(error("missing_targets", "protocol must declare at least one target", "protocol.targets"))
    if not protocol.candidates:
        diagnostics.append(error("missing_candidates", "protocol must declare at least one candidate", "protocol.candidates"))

    for candidate in protocol.candidates:
        if candidate.target not in target_ids:
            diagnostics.append(error("candidate_target_missing", f"candidate {candidate.id} references undeclared target", "protocol.candidates"))

    if protocol.quorum_policy.target not in target_ids:
        diagnostics.append(error("quorum_target_missing", "quorum target must be declared", "protocol.quorum_policy.target"))
    if protocol.quorum_policy.fallback_candidate not in candidate_ids:
        diagnostics.append(error("quorum_fallback_missing", "quorum fallback candidate must be declared", "protocol.quorum_policy.fallback_candidate"))
    if protocol.quorum_policy.fallback_candidate and protocol.quorum_policy.fallback_candidate not in safe_candidates:
        diagnostics.append(error("quorum_fallback_not_safe", "quorum fallback candidate must be marked safe_fallback", "protocol.quorum_policy.fallback_candidate"))

    for recovery in protocol.recovery_protocols:
        for target in recovery.trigger_targets:
            if target not in target_ids:
                diagnostics.append(error("recovery_target_missing", f"recovery target {target} is undeclared", "protocol.recovery_protocols"))
        if recovery.failure_candidate and recovery.failure_candidate not in candidate_ids:
            diagnostics.append(error("recovery_failure_candidate_missing", "recovery failure candidate must be declared", "protocol.recovery_protocols"))

    if protocol.output_policy.writer_may_create_facts:
        diagnostics.append(error("writer_fact_creation", "output policy must not allow writer fact creation", "protocol.output_policy"))

    if protocol.evidence_policy.allow_agent_fact_creation:
        diagnostics.append(error("agent_fact_creation", "evidence policy must not allow agent fact creation", "protocol.evidence_policy"))

    required_trace = {"block", "commit", "recovery", "output"}
    missing_trace = sorted(required_trace - set(protocol.trace_policy.required_events))
    if missing_trace:
        diagnostics.append(error("trace_lineage_incomplete", f"trace policy missing events: {', '.join(missing_trace)}", "protocol.trace_policy"))

    return diagnostics


def validate_ok(manifest: CapabilityManifest) -> bool:
    return not any(item.level == "error" for item in validate_capability_manifest(manifest))


def error(code: str, message: str, path: str) -> ValidationDiagnostic:
    return ValidationDiagnostic(code=code, message=message, path=path)
