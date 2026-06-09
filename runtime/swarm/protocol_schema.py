from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from runtime.swarm.legacy_protocol_fields import (
    legacy_quorum_force_fallback_value,
    legacy_quorum_policy_keys,
)
from runtime.swarm.legacy_tool_policy import legacy_source_policy_blocked_tool_target_values
from runtime.swarm.target_registry import canonical_target, target_kind


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def optional_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


@dataclass(frozen=True)
class TargetDeclaration:
    target: str
    target_type: str
    description: str = ""
    required: bool = True
    default_pressure: float = 0.7
    aliases: list[str] = field(default_factory=list)
    source: str = "capability_protocol"
    lifecycle_policy: dict[str, Any] = field(default_factory=dict)
    allowed_signal_types: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    compatible_intents: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Any, *, source: str = "capability_protocol") -> "TargetDeclaration | None":
        if isinstance(payload, str):
            raw_target = payload
            data: dict[str, Any] = {}
        elif isinstance(payload, dict):
            data = dict(payload)
            raw_target = str(data.get("target") or data.get("canonical_target") or "").strip()
        else:
            return None
        target = canonical_target(raw_target)
        if not raw_target or target == "run":
            return None
        return cls(
            target=target,
            target_type=str(data.get("target_type") or data.get("target_kind") or target_kind(target)),
            description=str(data.get("description") or data.get("summary") or data.get("content") or ""),
            required=bool_value(data.get("required"), True),
            default_pressure=max(0.0, min(1.0, float_value(data.get("default_pressure") or data.get("demand_strength"), 0.7))),
            aliases=string_list(data.get("aliases")),
            source=str(data.get("source") or source),
            lifecycle_policy=dict_value(data.get("lifecycle_policy")),
            allowed_signal_types=string_list(data.get("allowed_signal_types")),
            keywords=string_list(data.get("keywords")),
            compatible_intents=string_list(data.get("compatible_intents")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "canonical_target": self.target,
            "target_type": self.target_type,
            "target_kind": target_kind(self.target),
            "description": self.description,
            "summary": self.description,
            "required": self.required,
            "default_pressure": self.default_pressure,
            "demand_strength": self.default_pressure,
            "aliases": list(self.aliases),
            "source": self.source,
            "lifecycle_policy": dict(self.lifecycle_policy),
            "allowed_signal_types": list(self.allowed_signal_types),
            "keywords": list(self.keywords),
            "compatible_intents": list(self.compatible_intents),
        }


@dataclass(frozen=True)
class CandidateDeclaration:
    candidate: str
    description: str = ""
    target: str = ""
    compatible_intents: list[str] = field(default_factory=list)
    blocked_by_targets: list[str] = field(default_factory=list)
    required_evidence_targets: list[str] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    default_priority: float = 0.5
    safe_fallback: bool = False
    label: str = ""

    @classmethod
    def from_dict(cls, payload: Any) -> "CandidateDeclaration | None":
        if isinstance(payload, str):
            data: dict[str, Any] = {}
            candidate = payload
        elif isinstance(payload, dict):
            data = dict(payload)
            candidate = str(data.get("candidate") or data.get("id") or data.get("label") or "").strip()
        else:
            return None
        if not candidate:
            return None
        target = str(data.get("target") or candidate).strip()
        return cls(
            candidate=canonical_target(candidate),
            description=str(data.get("description") or data.get("summary") or ""),
            target=canonical_target(target),
            compatible_intents=string_list(data.get("compatible_intents")),
            blocked_by_targets=[canonical_target(item) for item in string_list(data.get("blocked_by_targets"))],
            required_evidence_targets=[canonical_target(item) for item in string_list(data.get("required_evidence_targets"))],
            required_permissions=string_list(data.get("required_permissions")),
            default_priority=float_value(data.get("default_priority"), 0.5),
            safe_fallback=bool_value(data.get("safe_fallback"), False),
            label=str(data.get("label") or data.get("candidate") or data.get("id") or candidate),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate,
            "id": self.candidate,
            "label": self.label or self.candidate,
            "description": self.description,
            "target": self.target,
            "compatible_intents": list(self.compatible_intents),
            "blocked_by_targets": list(self.blocked_by_targets),
            "required_evidence_targets": list(self.required_evidence_targets),
            "required_permissions": list(self.required_permissions),
            "default_priority": self.default_priority,
            "safe_fallback": self.safe_fallback,
        }


@dataclass(frozen=True)
class QuorumPolicy:
    candidates: list[str] = field(default_factory=list)
    quorum_threshold: float = 0.6
    min_independent_sources: int = 1
    source_independence_weight: float = 0.0
    source_quality_weight: float = 0.0
    unresolved_risk_penalty: float = 0.0
    stop_signal_penalty: float = 0.0
    evidence_coverage_weight: float = 0.0
    candidate_fallback: str | None = None
    force_fallback_when_blocked: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Any, *, candidate_ids: list[str] | None = None) -> "QuorumPolicy":
        data = dict_value(payload)
        candidates = string_list(data.get("candidates")) or list(candidate_ids or [])
        fallback = data.get("candidate_fallback") or data.get("fallback_candidate")
        return cls(
            candidates=[canonical_target(item) for item in candidates],
            quorum_threshold=float_value(data.get("quorum_threshold"), 0.6),
            min_independent_sources=int_value(data.get("min_independent_sources"), 1),
            source_independence_weight=float_value(data.get("source_independence_weight"), 0.0),
            source_quality_weight=float_value(data.get("source_quality_weight"), 0.0),
            unresolved_risk_penalty=float_value(data.get("unresolved_risk_penalty"), 0.0),
            stop_signal_penalty=float_value(data.get("stop_signal_penalty") or data.get("stop_signal_weight"), 0.0),
            evidence_coverage_weight=float_value(data.get("evidence_coverage_weight"), 0.0),
            candidate_fallback=canonical_target(fallback) if fallback else None,
            force_fallback_when_blocked=bool_value(
                data.get("force_fallback_when_blocked") or legacy_quorum_force_fallback_value(data),
                False,
            ),
            extra={key: value for key, value in data.items() if key not in QUORUM_POLICY_KEYS},
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "candidates": list(self.candidates),
            "quorum_threshold": self.quorum_threshold,
            "min_independent_sources": self.min_independent_sources,
            "source_independence_weight": self.source_independence_weight,
            "source_quality_weight": self.source_quality_weight,
            "unresolved_risk_penalty": self.unresolved_risk_penalty,
            "stop_signal_penalty": self.stop_signal_penalty,
            "evidence_coverage_weight": self.evidence_coverage_weight,
            "candidate_fallback": self.candidate_fallback,
            "force_fallback_when_blocked": self.force_fallback_when_blocked,
        }
        return {**data, **self.extra}


QUORUM_POLICY_KEYS = {
    "candidates",
    "quorum_threshold",
    "min_independent_sources",
    "source_independence_weight",
    "source_quality_weight",
    "unresolved_risk_penalty",
    "stop_signal_penalty",
    "stop_signal_weight",
    "evidence_coverage_weight",
    "candidate_fallback",
    "fallback_candidate",
    "force_fallback_when_blocked",
    *legacy_quorum_policy_keys(),
}


@dataclass(frozen=True)
class StopSignalPolicy:
    blocked_targets: list[str] = field(default_factory=list)
    blocking_authority_required: int = 0
    blocking_lifetime: str = "until_resolved"
    resolution_policy: dict[str, Any] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    action_effects: dict[str, Any] = field(default_factory=dict)
    applies_to_tools: bool = True
    applies_to_writer: bool = True
    applies_to_final_judge: bool = True
    applies_to_candidates: bool = True
    blocked_actions: list[str] = field(default_factory=list)
    action_markers: list[dict[str, Any]] = field(default_factory=list)
    rules: list[dict[str, Any]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Any) -> "StopSignalPolicy":
        data = dict_value(payload)
        return cls(
            blocked_targets=[canonical_target(item) for item in string_list(data.get("blocked_targets"))],
            blocking_authority_required=int_value(
                data.get("blocking_authority_required") or data.get("authority_level_required"),
                0,
            ),
            blocking_lifetime=str(data.get("blocking_lifetime") or "until_resolved"),
            resolution_policy=dict_value(data.get("resolution_policy")),
            aliases={str(key): canonical_target(value) for key, value in dict_value(data.get("aliases")).items()},
            action_effects=dict_value(data.get("action_effects")),
            applies_to_tools=bool_value(data.get("applies_to_tools"), True),
            applies_to_writer=bool_value(data.get("applies_to_writer"), True),
            applies_to_final_judge=bool_value(data.get("applies_to_final_judge"), True),
            applies_to_candidates=bool_value(data.get("applies_to_candidates"), True),
            blocked_actions=string_list(data.get("blocked_actions")),
            action_markers=list_of_dicts(data.get("action_markers") or data.get("action_cues")),
            rules=list_of_dicts(data.get("rules")),
            extra={key: value for key, value in data.items() if key not in STOP_SIGNAL_POLICY_KEYS},
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "blocked_targets": list(self.blocked_targets),
            "blocking_authority_required": self.blocking_authority_required,
            "authority_level_required": self.blocking_authority_required,
            "blocking_lifetime": self.blocking_lifetime,
            "resolution_policy": dict(self.resolution_policy),
            "aliases": dict(self.aliases),
            "action_effects": dict(self.action_effects),
            "applies_to_tools": self.applies_to_tools,
            "applies_to_writer": self.applies_to_writer,
            "applies_to_final_judge": self.applies_to_final_judge,
            "applies_to_candidates": self.applies_to_candidates,
            "blocked_actions": list(self.blocked_actions),
            "action_markers": [dict(marker) for marker in self.action_markers],
            "rules": [dict(rule) for rule in self.rules],
        }
        return {**data, **self.extra}


STOP_SIGNAL_POLICY_KEYS = {
    "blocked_targets",
    "blocking_authority_required",
    "authority_level_required",
    "blocking_lifetime",
    "resolution_policy",
    "aliases",
    "action_effects",
    "applies_to_tools",
    "applies_to_writer",
    "applies_to_final_judge",
    "applies_to_candidates",
    "blocked_actions",
    "action_markers",
    "action_cues",
    "rules",
}


@dataclass(frozen=True)
class RecoveryProtocol:
    recovery_id: str
    trigger_targets: list[str] = field(default_factory=list)
    trigger_signal_types: list[str] = field(default_factory=list)
    max_rounds: int = 1
    allowed_agent_roles: list[str] = field(default_factory=list)
    allowed_capability_tags: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    recovery_success_condition: str = ""
    recovery_failure_candidate: str | None = None
    evidence_requirements: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Any) -> "RecoveryProtocol | None":
        if isinstance(payload, str):
            data: dict[str, Any] = {"recovery_id": payload}
        elif isinstance(payload, dict):
            data = dict(payload)
        else:
            return None
        recovery_id = str(data.get("recovery_id") or data.get("id") or data.get("name") or data.get("hook") or "").strip()
        if not recovery_id:
            return None
        trigger_targets = string_list(data.get("trigger_targets"))
        if not trigger_targets:
            raw_targets = data.get("targets")
            if isinstance(raw_targets, list):
                trigger_targets = [
                    str(item.get("target") or item.get("canonical_target") or "").strip()
                    for item in raw_targets
                    if isinstance(item, dict)
                ]
            else:
                trigger_targets = string_list(data.get("target"))
        failure = data.get("recovery_failure_candidate")
        return cls(
            recovery_id=recovery_id,
            trigger_targets=[canonical_target(item) for item in trigger_targets],
            trigger_signal_types=string_list(data.get("trigger_signal_types")),
            max_rounds=int_value(data.get("max_rounds"), 1),
            allowed_agent_roles=string_list(data.get("allowed_agent_roles")),
            allowed_capability_tags=string_list(data.get("allowed_capability_tags")),
            required_tools=string_list(data.get("required_tools") or data.get("retry_tools")),
            recovery_success_condition=str(data.get("recovery_success_condition") or ""),
            recovery_failure_candidate=canonical_target(failure) if failure else None,
            evidence_requirements=dict_value(data.get("evidence_requirements")),
            extra={key: value for key, value in data.items() if key not in RECOVERY_PROTOCOL_KEYS},
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "recovery_id": self.recovery_id,
            "id": self.recovery_id,
            "trigger_targets": list(self.trigger_targets),
            "targets": [{"target": target, "canonical_target": target} for target in self.trigger_targets],
            "trigger_signal_types": list(self.trigger_signal_types),
            "max_rounds": self.max_rounds,
            "allowed_agent_roles": list(self.allowed_agent_roles),
            "allowed_capability_tags": list(self.allowed_capability_tags),
            "required_tools": list(self.required_tools),
            "recovery_success_condition": self.recovery_success_condition,
            "recovery_failure_candidate": self.recovery_failure_candidate,
            "evidence_requirements": dict(self.evidence_requirements),
        }
        return {**self.extra, **data}


RECOVERY_PROTOCOL_KEYS = {
    "recovery_id",
    "id",
    "name",
    "hook",
    "trigger_targets",
    "targets",
    "target",
    "trigger_signal_types",
    "max_rounds",
    "allowed_agent_roles",
    "allowed_capability_tags",
    "required_tools",
    "retry_tools",
    "recovery_success_condition",
    "recovery_failure_candidate",
    "evidence_requirements",
}


@dataclass(frozen=True)
class AgentSelectionPolicy:
    target_affinity_weights: dict[str, float] = field(default_factory=dict)
    required_roles: list[str] = field(default_factory=list)
    optional_roles: list[str] = field(default_factory=list)
    forbidden_roles: list[str] = field(default_factory=list)
    activation_threshold: float = 0.5
    utility_weights: dict[str, float] = field(default_factory=dict)
    maturity_requirements: dict[str, Any] = field(default_factory=dict)
    trust_requirements: dict[str, Any] = field(default_factory=dict)
    fallback_strategy: str = "legacy_default"

    @classmethod
    def from_dict(cls, payload: Any) -> "AgentSelectionPolicy":
        data = dict_value(payload)
        weights = {
            canonical_target(key): float_value(value, 0.0)
            for key, value in dict_value(data.get("target_affinity_weights")).items()
        }
        return cls(
            target_affinity_weights=weights,
            required_roles=string_list(data.get("required_roles")),
            optional_roles=string_list(data.get("optional_roles")),
            forbidden_roles=string_list(data.get("forbidden_roles")),
            activation_threshold=float_value(data.get("activation_threshold"), 0.5),
            utility_weights={str(key): float_value(value, 0.0) for key, value in dict_value(data.get("utility_weights")).items()},
            maturity_requirements=dict_value(data.get("maturity_requirements")),
            trust_requirements=dict_value(data.get("trust_requirements")),
            fallback_strategy=str(data.get("fallback_strategy") or "legacy_default"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_affinity_weights": dict(self.target_affinity_weights),
            "required_roles": list(self.required_roles),
            "optional_roles": list(self.optional_roles),
            "forbidden_roles": list(self.forbidden_roles),
            "activation_threshold": self.activation_threshold,
            "utility_weights": dict(self.utility_weights),
            "maturity_requirements": dict(self.maturity_requirements),
            "trust_requirements": dict(self.trust_requirements),
            "fallback_strategy": self.fallback_strategy,
        }


@dataclass(frozen=True)
class EvidencePolicy:
    claim_types: list[str] = field(default_factory=list)
    evidence_node_types: list[str] = field(default_factory=list)
    required_evidence_for_final_claims: list[str] = field(default_factory=list)
    allow_caveated_claim_without_evidence: bool = True
    source_independence_required: bool = False
    citation_required: bool = False
    raw_data_allowed_in_final: bool = False
    raw_data_markers: list[str] = field(default_factory=list)
    unsupported_claim_action: str = "caveat_or_block"

    @classmethod
    def from_dict(cls, payload: Any) -> "EvidencePolicy":
        data = dict_value(payload)
        return cls(
            claim_types=string_list(data.get("claim_types")),
            evidence_node_types=string_list(data.get("evidence_node_types")),
            required_evidence_for_final_claims=[
                canonical_target(item) for item in string_list(data.get("required_evidence_for_final_claims"))
            ],
            allow_caveated_claim_without_evidence=bool_value(data.get("allow_caveated_claim_without_evidence"), True),
            source_independence_required=bool_value(data.get("source_independence_required"), False),
            citation_required=bool_value(data.get("citation_required"), False),
            raw_data_allowed_in_final=bool_value(data.get("raw_data_allowed_in_final"), False),
            raw_data_markers=string_list(data.get("raw_data_markers") or data.get("raw_output_markers")),
            unsupported_claim_action=str(data.get("unsupported_claim_action") or "caveat_or_block"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_types": list(self.claim_types),
            "evidence_node_types": list(self.evidence_node_types),
            "required_evidence_for_final_claims": list(self.required_evidence_for_final_claims),
            "allow_caveated_claim_without_evidence": self.allow_caveated_claim_without_evidence,
            "source_independence_required": self.source_independence_required,
            "citation_required": self.citation_required,
            "raw_data_allowed_in_final": self.raw_data_allowed_in_final,
            "raw_data_markers": list(self.raw_data_markers),
            "unsupported_claim_action": self.unsupported_claim_action,
        }


@dataclass(frozen=True)
class ToolPolicy:
    allowed_tool_targets: list[str] = field(default_factory=list)
    blocked_tool_targets: list[str] = field(default_factory=list)
    source_policy_blocked_tool_targets: list[str] = field(default_factory=list)
    tool_aliases: dict[str, str] = field(default_factory=dict)
    source_mode: str | None = None
    source_mode_guidance: str | None = None
    source_policy_block_message: str | None = None
    source_policy_constraint_message: str | None = None
    required_permissions: list[str] = field(default_factory=list)
    required_connections: list[str] = field(default_factory=list)
    risk_level: str = "low"
    quarantine_external_outputs: bool = True
    tool_failure_recovery: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Any) -> "ToolPolicy":
        data = dict_value(payload)
        return cls(
            allowed_tool_targets=[canonical_target(item) for item in string_list(data.get("allowed_tool_targets"))],
            blocked_tool_targets=[canonical_target(item) for item in string_list(data.get("blocked_tool_targets"))],
            source_policy_blocked_tool_targets=[
                canonical_target(item)
                for item in string_list(
                    data.get("source_policy_blocked_tool_targets")
                    or legacy_source_policy_blocked_tool_target_values(data)
                )
            ],
            tool_aliases={str(key): canonical_target(value) for key, value in dict_value(data.get("tool_aliases")).items()},
            source_mode=optional_string(data.get("source_mode") or data.get("source_policy")),
            source_mode_guidance=optional_string(data.get("source_mode_guidance") or data.get("source_policy_guidance")),
            source_policy_block_message=optional_string(data.get("source_policy_block_message")),
            source_policy_constraint_message=optional_string(data.get("source_policy_constraint_message")),
            required_permissions=string_list(data.get("required_permissions")),
            required_connections=string_list(data.get("required_connections")),
            risk_level=str(data.get("risk_level") or "low"),
            quarantine_external_outputs=bool_value(data.get("quarantine_external_outputs"), True),
            tool_failure_recovery=dict_value(data.get("tool_failure_recovery")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_tool_targets": list(self.allowed_tool_targets),
            "blocked_tool_targets": list(self.blocked_tool_targets),
            "source_policy_blocked_tool_targets": list(self.source_policy_blocked_tool_targets),
            "tool_aliases": dict(self.tool_aliases),
            "source_mode": self.source_mode,
            "source_mode_guidance": self.source_mode_guidance,
            "source_policy_block_message": self.source_policy_block_message,
            "source_policy_constraint_message": self.source_policy_constraint_message,
            "required_permissions": list(self.required_permissions),
            "required_connections": list(self.required_connections),
            "risk_level": self.risk_level,
            "quarantine_external_outputs": self.quarantine_external_outputs,
            "tool_failure_recovery": dict(self.tool_failure_recovery),
        }


@dataclass(frozen=True)
class OutputPolicy:
    allowed_output_modes: list[str] = field(default_factory=list)
    blocked_phrases: list[str] = field(default_factory=list)
    required_caveats: list[str] = field(default_factory=list)
    committed_candidate_conflicts: list[dict[str, Any]] = field(default_factory=list)
    final_claim_evidence_required: bool = True
    defect_memo_on_block: bool = True
    defect_memo_markers: list[str] = field(default_factory=list)
    writer_can_create_facts: bool = False
    final_judge_required_checks: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: Any) -> "OutputPolicy":
        data = dict_value(payload)
        return cls(
            allowed_output_modes=string_list(data.get("allowed_output_modes")),
            blocked_phrases=string_list(data.get("blocked_phrases")),
            required_caveats=string_list(data.get("required_caveats")),
            committed_candidate_conflicts=list_of_dicts(data.get("committed_candidate_conflicts")),
            final_claim_evidence_required=bool_value(data.get("final_claim_evidence_required"), True),
            defect_memo_on_block=bool_value(data.get("defect_memo_on_block"), True),
            defect_memo_markers=string_list(data.get("defect_memo_markers")),
            writer_can_create_facts=bool_value(data.get("writer_can_create_facts"), False),
            final_judge_required_checks=string_list(data.get("final_judge_required_checks")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_output_modes": list(self.allowed_output_modes),
            "blocked_phrases": list(self.blocked_phrases),
            "required_caveats": list(self.required_caveats),
            "committed_candidate_conflicts": [dict(item) for item in self.committed_candidate_conflicts],
            "final_claim_evidence_required": self.final_claim_evidence_required,
            "defect_memo_on_block": self.defect_memo_on_block,
            "defect_memo_markers": list(self.defect_memo_markers),
            "writer_can_create_facts": self.writer_can_create_facts,
            "final_judge_required_checks": list(self.final_judge_required_checks),
        }


@dataclass(frozen=True)
class SwarmLoopPolicy:
    max_rounds: int = 2
    target_pressure_threshold: float = 0.5
    evidence_gap_threshold: float = 0.5
    recovery_rounds: int = 1
    quorum_check_frequency: int = 1
    stop_signal_check_frequency: int = 1
    tool_health_check_frequency: int = 1
    arousal_signal_template: str = ""
    social_immunity_arousal_signal_template: str = ""
    social_immunity_recommendations: dict[str, str] = field(default_factory=dict)
    homeostasis_signal_template: str = ""
    homeostasis_recommendations: dict[str, str] = field(default_factory=dict)
    lane_policy: dict[str, Any] = field(default_factory=dict)
    maturity_policy: dict[str, Any] = field(default_factory=dict)
    independent_scout_policy: dict[str, Any] = field(default_factory=dict)
    controller_action_policy: dict[str, Any] = field(default_factory=dict)
    tool_health_recommendations: dict[str, str] = field(default_factory=dict)
    encounter_rate_recommendations: dict[str, str] = field(default_factory=dict)
    outcome_feedback_enabled: bool = True

    @classmethod
    def from_dict(cls, payload: Any) -> "SwarmLoopPolicy":
        data = dict_value(payload)
        return cls(
            max_rounds=int_value(data.get("max_rounds") or data.get("max_swarm_rounds"), 2),
            target_pressure_threshold=float_value(data.get("target_pressure_threshold"), 0.5),
            evidence_gap_threshold=float_value(data.get("evidence_gap_threshold"), 0.5),
            recovery_rounds=int_value(data.get("recovery_rounds"), 1),
            quorum_check_frequency=int_value(data.get("quorum_check_frequency"), 1),
            stop_signal_check_frequency=int_value(data.get("stop_signal_check_frequency"), 1),
            tool_health_check_frequency=int_value(data.get("tool_health_check_frequency"), 1),
            arousal_signal_template=str(data.get("arousal_signal_template") or "").strip(),
            social_immunity_arousal_signal_template=str(
                data.get("social_immunity_arousal_signal_template") or ""
            ).strip(),
            social_immunity_recommendations={
                str(key): str(value)
                for key, value in dict_value(data.get("social_immunity_recommendations")).items()
                if str(key).strip() and str(value).strip()
            },
            homeostasis_signal_template=str(data.get("homeostasis_signal_template") or "").strip(),
            homeostasis_recommendations={
                str(key): str(value)
                for key, value in dict_value(data.get("homeostasis_recommendations")).items()
                if str(key).strip() and str(value).strip()
            },
            lane_policy=dict_value(data.get("lane_policy")),
            maturity_policy=dict_value(data.get("maturity_policy")),
            independent_scout_policy=dict_value(data.get("independent_scout_policy")),
            controller_action_policy=dict_value(data.get("controller_action_policy")),
            tool_health_recommendations={
                str(key): str(value)
                for key, value in dict_value(data.get("tool_health_recommendations")).items()
                if str(key).strip() and str(value).strip()
            },
            encounter_rate_recommendations={
                str(key): str(value)
                for key, value in dict_value(data.get("encounter_rate_recommendations")).items()
                if str(key).strip() and str(value).strip()
            },
            outcome_feedback_enabled=bool_value(data.get("outcome_feedback_enabled"), True),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_rounds": self.max_rounds,
            "target_pressure_threshold": self.target_pressure_threshold,
            "evidence_gap_threshold": self.evidence_gap_threshold,
            "recovery_rounds": self.recovery_rounds,
            "quorum_check_frequency": self.quorum_check_frequency,
            "stop_signal_check_frequency": self.stop_signal_check_frequency,
            "tool_health_check_frequency": self.tool_health_check_frequency,
            "arousal_signal_template": self.arousal_signal_template,
            "social_immunity_arousal_signal_template": self.social_immunity_arousal_signal_template,
            "social_immunity_recommendations": dict(self.social_immunity_recommendations),
            "homeostasis_signal_template": self.homeostasis_signal_template,
            "homeostasis_recommendations": dict(self.homeostasis_recommendations),
            "lane_policy": dict(self.lane_policy),
            "maturity_policy": dict(self.maturity_policy),
            "independent_scout_policy": dict(self.independent_scout_policy),
            "controller_action_policy": dict(self.controller_action_policy),
            "tool_health_recommendations": dict(self.tool_health_recommendations),
            "encounter_rate_recommendations": dict(self.encounter_rate_recommendations),
            "outcome_feedback_enabled": self.outcome_feedback_enabled,
        }
