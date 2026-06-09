from __future__ import annotations

from typing import Any

from runtime.swarm.protocol_manifest import CapabilityPheroOSProtocol
from runtime.swarm.target_registry import canonical_target, target_kind


TRUSTED_BLOCKING_LEVELS = {"first_party_reviewed", "first_party", "trusted", "internal"}


def validate_protocol(
    protocol: CapabilityPheroOSProtocol,
    *,
    trust_level: str = "first_party_reviewed",
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    declared_intents = set(protocol.intents)
    declared_targets = {target.target for target in protocol.targets}
    declared_candidates = {candidate.candidate for candidate in protocol.candidates}

    for intent in protocol.required_capability_types_by_intent:
        if declared_intents and intent not in declared_intents:
            diagnostics.append(
                error(
                    "required_capability_intent_unknown",
                    f"Required capability map references undeclared intent {intent!r}.",
                    intent=intent,
                )
            )

    for intent in protocol.intent_keywords:
        if declared_intents and intent not in declared_intents:
            diagnostics.append(
                error(
                    "intent_keywords_intent_unknown",
                    f"Intent keyword map references undeclared intent {intent!r}.",
                    intent=intent,
                )
            )

    for target in protocol.targets:
        if not target.target or target.target == "run":
            diagnostics.append(error("target_required", "Protocol target declarations must include a canonical target."))
        for intent in target.compatible_intents:
            if declared_intents and intent not in declared_intents:
                diagnostics.append(
                    error(
                        "target_compatible_intent_unknown",
                        f"Target {target.target!r} references undeclared compatible intent {intent!r}.",
                        target=target.target,
                        intent=intent,
                    )
                )
        for alias in target.aliases:
            alias_target = canonical_target(alias)
            if alias_target != alias and alias_target != target.target:
                diagnostics.append(
                    error(
                        "target_alias_conflict",
                        f"Alias {alias!r} canonicalizes to {alias_target!r}, not {target.target!r}.",
                        target=target.target,
                    )
                )

    for candidate in protocol.candidates:
        if candidate.target and target_kind(candidate.target) != "candidate" and candidate.target not in declared_targets:
            diagnostics.append(
                error(
                    "candidate_target_unknown",
                    f"Candidate {candidate.candidate!r} targets undeclared target {candidate.target!r}.",
                    target=candidate.target,
                    candidate=candidate.candidate,
                )
            )
        referenced = [
            *candidate.blocked_by_targets,
            *candidate.required_evidence_targets,
        ]
        for target in referenced:
            if target and target not in declared_targets:
                diagnostics.append(
                    error(
                        "candidate_references_unknown_target",
                        f"Candidate {candidate.candidate!r} references undeclared target {target!r}.",
                        target=target,
                    )
                )

    for candidate in protocol.quorum_policy.candidates:
        if candidate and declared_candidates and candidate not in declared_candidates:
            diagnostics.append(
                error(
                    "quorum_references_unknown_candidate",
                    f"Quorum policy references undeclared candidate {candidate!r}.",
                    candidate=candidate,
                )
            )

    fallback = protocol.quorum_policy.candidate_fallback
    if fallback and declared_candidates and fallback not in declared_candidates:
        diagnostics.append(
            error(
                "quorum_fallback_unknown_candidate",
                f"Quorum fallback references undeclared candidate {fallback!r}.",
                candidate=fallback,
            )
        )

    for recovery in protocol.recovery_protocols:
        for target in recovery.trigger_targets:
            if target and target not in declared_targets:
                diagnostics.append(
                    error(
                        "recovery_references_unknown_target",
                        f"Recovery protocol {recovery.recovery_id!r} references undeclared target {target!r}.",
                        target=target,
                    )
                )
        fallback_candidate = recovery.recovery_failure_candidate
        if fallback_candidate and declared_candidates and fallback_candidate not in declared_candidates:
            diagnostics.append(
                error(
                    "recovery_failure_unknown_candidate",
                    f"Recovery protocol {recovery.recovery_id!r} references undeclared failure candidate {fallback_candidate!r}.",
                    candidate=fallback_candidate,
                recovery_id=recovery.recovery_id,
            )
        )

    stop_policy_targets = set(protocol.stop_signal_policy.blocked_targets)
    tool_policy_targets = set(protocol.tool_policy.allowed_tool_targets) | set(protocol.tool_policy.blocked_tool_targets)
    valid_stop_targets = declared_targets | stop_policy_targets | tool_policy_targets
    for rule in protocol.stop_signal_policy.rules:
        rule_id = str(rule.get("id") or "")
        for target in [canonical_target(item) for item in string_list(rule.get("trigger_targets"))]:
            if target and target not in valid_stop_targets:
                diagnostics.append(
                    error(
                        "stop_signal_references_unknown_target",
                        f"Stop-signal rule {rule_id!r} references undeclared trigger target {target!r}.",
                        target=target,
                        rule_id=rule_id,
                    )
                )

    if protocol.stop_signal_policy.blocking_authority_required >= 3 and trust_level not in TRUSTED_BLOCKING_LEVELS:
        diagnostics.append(
            error(
                "untrusted_blocking_authority",
                "Only trusted capabilities may declare hard-blocking stop-signal authority.",
            )
        )

    if trust_level not in TRUSTED_BLOCKING_LEVELS:
        diagnostics.append(
            warning(
                "third_party_nonblocking_default",
                "Third-party capability signals default to unverified, non-blocking runtime treatment.",
            )
        )

    if protocol.evidence_policy.raw_data_allowed_in_final:
        severity = "error" if trust_level not in TRUSTED_BLOCKING_LEVELS else "warning"
        diagnostics.append(
            diagnostic(
                severity,
                "raw_data_allowed_in_final",
                "Raw data in final output is disabled by default and requires privileged review.",
            )
        )

    if protocol.output_policy.writer_can_create_facts:
        diagnostics.append(
            error(
                "writer_can_create_facts",
                "Writer cannot be authorized to create facts under PheroOS output policy.",
            )
        )

    return diagnostics


def diagnostic(severity: str, code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        **extra,
    }


def error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return diagnostic("error", code, message, **extra)


def warning(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return diagnostic("warning", code, message, **extra)


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []
