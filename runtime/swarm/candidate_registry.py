from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from runtime.swarm.legacy_protocol_fields import legacy_candidate_registry_missing_policy_reason
from runtime.swarm.target_registry import canonical_target


@dataclass(frozen=True)
class CandidateTemplate:
    id: str
    label: str
    target: str = ""
    blocked_by_targets: tuple[str, ...] = field(default_factory=tuple)
    required_evidence_targets: tuple[str, ...] = field(default_factory=tuple)
    safe_fallback: bool = False
    source: str = "capability_protocol"


@dataclass(frozen=True)
class CandidateRegistryResult:
    candidates: list[CandidateTemplate]
    source: str
    generated_legacy_candidate_fallback: bool
    trace: list[dict[str, Any]]
    fallback_candidate_id: str | None = None
    fallback_candidate_label: str | None = None
    candidate_type: str | None = None
    force_fallback_when_blocked: bool = False


def candidate_registry_from_state(state: dict[str, Any]) -> CandidateRegistryResult:
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    candidate_policy = swarm_plan.get("candidate_policy") if isinstance(swarm_plan.get("candidate_policy"), dict) else {}
    quorum_policy = swarm_plan.get("quorum_policy") if isinstance(swarm_plan.get("quorum_policy"), dict) else {}

    declared = candidate_templates_from_policy(candidate_policy, source="capability_protocol")
    if not declared:
        declared = candidate_templates_from_quorum_policy(quorum_policy, source="quorum_policy")
    if declared:
        fallback = fallback_candidate(declared, candidate_policy=candidate_policy, quorum_policy=quorum_policy)
        return CandidateRegistryResult(
            candidates=declared,
            source="capability_protocol",
            generated_legacy_candidate_fallback=False,
            trace=[
                {
                    "event_type": "candidate_registry.loaded_declared_candidates",
                    "candidate_count": len(declared),
                    "candidate_type": candidate_policy.get("candidate_type") or quorum_policy.get("candidate_type"),
                    "policy_sources": candidate_policy.get("policy_sources") or quorum_policy.get("policy_sources") or [],
                }
            ],
            fallback_candidate_id=fallback.id if fallback else None,
            fallback_candidate_label=fallback.label if fallback else None,
            candidate_type=str(candidate_policy.get("candidate_type") or quorum_policy.get("candidate_type") or "").strip() or None,
            force_fallback_when_blocked=bool(quorum_policy.get("force_fallback_when_blocked")),
        )

    return CandidateRegistryResult(
        candidates=[],
        source="missing_candidate_declaration",
        generated_legacy_candidate_fallback=False,
        trace=[
            {
                "event_type": "candidate_registry.needs_candidate_policy",
                "reason": legacy_candidate_registry_missing_policy_reason(),
            }
        ],
    )


def candidate_templates_from_policy(policy: dict[str, Any], *, source: str) -> list[CandidateTemplate]:
    declared = policy.get("candidates") if isinstance(policy.get("candidates"), list) else []
    templates: list[CandidateTemplate] = []
    for item in declared:
        template = candidate_template_from_value(item, source=source)
        if template is not None:
            templates.append(template)
    return dedupe_candidate_templates(templates)


def candidate_templates_from_quorum_policy(policy: dict[str, Any], *, source: str) -> list[CandidateTemplate]:
    declared = policy.get("candidates") if isinstance(policy.get("candidates"), list) else []
    templates: list[CandidateTemplate] = []
    for item in declared:
        template = candidate_template_from_value(item, source=source)
        if template is not None:
            templates.append(template)
    return dedupe_candidate_templates(templates)


def candidate_template_from_value(value: Any, *, source: str) -> CandidateTemplate | None:
    if isinstance(value, str):
        data: dict[str, Any] = {}
        candidate_id = value
        raw_label = value
    elif isinstance(value, dict):
        data = dict(value)
        candidate_id = str(data.get("id") or data.get("candidate") or data.get("label") or "").strip()
        raw_label = str(data.get("label") or data.get("candidate") or data.get("id") or candidate_id).strip()
    else:
        return None
    if not candidate_id:
        return None
    label = friendly_candidate_label(candidate_id, raw_label)
    target = canonical_target(data.get("target") or candidate_id)
    blocked_by_targets = tuple(canonical_target(item) for item in string_list(data.get("blocked_by_targets")))
    required_evidence_targets = tuple(canonical_target(item) for item in string_list(data.get("required_evidence_targets")))
    safe_fallback = bool(data.get("safe_fallback"))
    return CandidateTemplate(
        id=canonical_target(candidate_id),
        label=label,
        target=target,
        blocked_by_targets=blocked_by_targets,
        required_evidence_targets=required_evidence_targets,
        safe_fallback=safe_fallback,
        source=source,
    )


def dedupe_candidate_templates(candidates: list[CandidateTemplate]) -> list[CandidateTemplate]:
    output = []
    seen = set()
    for candidate in candidates:
        if candidate.id in seen:
            continue
        seen.add(candidate.id)
        output.append(candidate)
    return output


def fallback_candidate(
    candidates: list[CandidateTemplate],
    *,
    candidate_policy: dict[str, Any],
    quorum_policy: dict[str, Any],
) -> CandidateTemplate | None:
    explicit = (
        quorum_policy.get("candidate_fallback")
        or quorum_policy.get("fallback_candidate")
        or candidate_policy.get("candidate_fallback")
        or candidate_policy.get("fallback_candidate")
    )
    if explicit:
        match = candidate_by_value(explicit, candidates)
        if match is not None:
            return match
    for candidate in candidates:
        if candidate.safe_fallback:
            return candidate
    return None


def candidate_by_value(value: Any, candidates: list[CandidateTemplate]) -> CandidateTemplate | None:
    normalized = normalized_candidate_label(value)
    if not normalized:
        return None
    for candidate in candidates:
        if normalized in candidate_match_keys(candidate):
            return candidate
    return None


def selected_candidate_label(value: Any, registry: CandidateRegistryResult) -> str:
    declared = declared_candidate_label(value, registry.candidates)
    if declared:
        return declared
    if not str(value or "").strip() and registry.fallback_candidate_label:
        return registry.fallback_candidate_label
    return ""


def declared_candidate_label(value: Any, candidates: list[CandidateTemplate]) -> str | None:
    normalized = normalized_candidate_label(value)
    if not normalized:
        return None
    for candidate in candidates:
        if normalized in candidate_match_keys(candidate):
            return candidate.label
    return None


def candidate_match_keys(candidate: CandidateTemplate) -> set[str]:
    return {
        normalized_candidate_label(candidate.id),
        normalized_candidate_label(candidate.label),
        normalized_candidate_label(candidate_short_label(candidate.id)),
        normalized_candidate_label(canonical_target(candidate.id)),
    }


def candidate_short_label(candidate_id: Any) -> str:
    text = str(candidate_id or "").strip()
    if not text:
        return ""
    tail = text.split(":")[-1]
    return " ".join(tail.replace("-", "_").split("_"))


def friendly_candidate_label(candidate_id: Any, label: Any) -> str:
    label_text = str(label or "").strip()
    id_text = str(candidate_id or "").strip()
    if label_text and normalized_candidate_label(label_text) != normalized_candidate_label(id_text):
        return label_text
    short = candidate_short_label(id_text)
    if short:
        return " ".join(word if word.isupper() else word.capitalize() for word in short.split())
    return label_text or id_text


def fallbackish_candidate_text(value: Any) -> bool:
    normalized = normalized_candidate_label(value)
    return (
        "insufficient" in normalized
        or "insufficient evidence" in normalized
        or "insufficient data" in normalized
        or "数据不足" in normalized
    )


def legacy_fallbackish_candidate_allowed(quorum_trace: dict[str, Any]) -> bool:
    source = str(quorum_trace.get("candidate_source") or "").strip()
    if source == "capability_protocol":
        return False
    return not bool(quorum_trace.get("candidate_registry_trace"))


def normalized_candidate_label(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
