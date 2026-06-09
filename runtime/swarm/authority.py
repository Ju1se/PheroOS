from __future__ import annotations

from enum import IntEnum
from typing import Any

from runtime.agent_registry import AgentRegistry, committee_capable
from runtime.legacy_agent_registry import legacy_agent_proposal_modules


class AuthorityLevel(IntEnum):
    OBSERVER = 1
    AGENT = 2
    TRUSTED_AGENT = 3
    VERIFIED_SYSTEM = 4
    CORE_CONTROL = 5


CORE_AUTHORITY_LEVELS = {
    "system_policy": AuthorityLevel.CORE_CONTROL,
    "permission_policy": AuthorityLevel.CORE_CONTROL,
    "os_kernel": AuthorityLevel.CORE_CONTROL,
    "data_gate": AuthorityLevel.CORE_CONTROL,
    "patroller_gate": AuthorityLevel.CORE_CONTROL,
    "deterministic_tool": AuthorityLevel.VERIFIED_SYSTEM,
    "metric_registry": AuthorityLevel.VERIFIED_SYSTEM,
    "swarm_signal_verifier": AuthorityLevel.VERIFIED_SYSTEM,
    "final_judge": AuthorityLevel.VERIFIED_SYSTEM,
    "encounter_rate": AuthorityLevel.VERIFIED_SYSTEM,
    "bottleneck_recruitment": AuthorityLevel.VERIFIED_SYSTEM,
    "social_immunity": AuthorityLevel.CORE_CONTROL,
    "worker_policing": AuthorityLevel.CORE_CONTROL,
    "receiver_normalizer": AuthorityLevel.VERIFIED_SYSTEM,
    "evidence_steward": AuthorityLevel.VERIFIED_SYSTEM,
    "tool_health_sentinel": AuthorityLevel.CORE_CONTROL,
    "capability_sandbox_auditor": AuthorityLevel.CORE_CONTROL,
    "outcome_memory_steward": AuthorityLevel.VERIFIED_SYSTEM,
    "quorum_marshal": AuthorityLevel.CORE_CONTROL,
    "trust_badge": AuthorityLevel.VERIFIED_SYSTEM,
    "arousal_controller": AuthorityLevel.VERIFIED_SYSTEM,
    "lane_scheduler": AuthorityLevel.CORE_CONTROL,
    "homeostasis": AuthorityLevel.VERIFIED_SYSTEM,
    "maturity_lifecycle": AuthorityLevel.VERIFIED_SYSTEM,
    "independent_scout": AuthorityLevel.VERIFIED_SYSTEM,
    "artifact_cues": AuthorityLevel.VERIFIED_SYSTEM,
    "critic": AuthorityLevel.TRUSTED_AGENT,
    "writer": AuthorityLevel.OBSERVER,
}


FACT_AUTHORITY_LEVEL = AuthorityLevel.VERIFIED_SYSTEM
BLOCKING_AUTHORITY_LEVEL = AuthorityLevel.VERIFIED_SYSTEM
AGENT_PROPOSAL_MODULE = "capability_agent"
AGENT_PROPOSAL_MODULES = {AGENT_PROPOSAL_MODULE, "swarm_execution_loop", *legacy_agent_proposal_modules()}


def authority_level(source_module: Any = None, source_agent: Any = None) -> int:
    """Return the governance authority level for a signal or trace actor.

    Agent outputs are deliberately weaker than system verifier outputs. Capability
    agents can propose evidence and stop-signals, but only the governance layer
    can promote those proposals into blocking facts.
    """

    module = str(source_module or "").strip()
    agent = str(source_agent or "").strip()
    if module in CORE_AUTHORITY_LEVELS:
        return CORE_AUTHORITY_LEVELS[module]
    if agent in CORE_AUTHORITY_LEVELS:
        return CORE_AUTHORITY_LEVELS[agent]
    agent_level = manifest_agent_authority_level(agent)
    if agent_level is not None:
        return int(agent_level)
    if module:
        return int(AuthorityLevel.AGENT)
    if agent:
        return int(AuthorityLevel.AGENT)
    return int(AuthorityLevel.OBSERVER)


def signal_authority_level(signal: dict[str, Any]) -> int:
    return authority_level(signal.get("source_module"), signal.get("source_agent"))


def can_create_fact(signal: dict[str, Any]) -> bool:
    if is_agent_self_assertion(signal):
        return False
    return signal_authority_level(signal) >= FACT_AUTHORITY_LEVEL


def can_create_blocker(signal: dict[str, Any]) -> bool:
    if is_agent_self_assertion(signal):
        return False
    return signal_authority_level(signal) >= BLOCKING_AUTHORITY_LEVEL


def is_agent_self_assertion(signal: dict[str, Any]) -> bool:
    metadata = signal.get("metadata") if isinstance(signal.get("metadata"), dict) else {}
    source_agent = normalized_text(signal.get("source_agent"))
    source_module = normalized_text(signal.get("source_module"))
    if metadata.get("agent_emitted"):
        return True
    if not source_agent:
        return False
    if not source_module:
        return True
    if source_module == source_agent:
        return True
    return source_module in AGENT_PROPOSAL_MODULES


def agent_can_request_blocker(agent_key: Any) -> bool:
    key = str(agent_key or "").strip()
    return manifest_agent_can_request_blocker(key) or authority_level(source_agent=key) >= BLOCKING_AUTHORITY_LEVEL


def manifest_agent_authority_level(agent_key: str) -> AuthorityLevel | None:
    manifest = agent_manifest(agent_key)
    if manifest is None:
        return None
    swarm = manifest.swarm if isinstance(manifest.swarm, dict) else {}
    trust_level = normalized_text(swarm.get("trust_level"))
    agent_type = normalized_text(manifest.agent_type)
    if trust_level == "core_system":
        return AuthorityLevel.CORE_CONTROL
    if agent_type in {"deterministic_governance", "security_governance"}:
        return AuthorityLevel.CORE_CONTROL if trust_level == "core_system" else AuthorityLevel.VERIFIED_SYSTEM
    permissions = {normalized_text(item) for item in swarm.get("signal_emit_permissions") or []}
    can_block = bool(swarm.get("can_block"))
    role_terms = manifest_terms(
        manifest.agent_type,
        manifest.committee_role,
        manifest.description,
        manifest.focus,
        manifest.tags,
        manifest.required_capabilities,
        manifest.required_tools,
    )
    if "evidence_steward" in role_terms or "verifier" in role_terms or "governance_verifier" in role_terms:
        return AuthorityLevel.VERIFIED_SYSTEM
    if can_block and "stop_signal" in permissions:
        return AuthorityLevel.TRUSTED_AGENT if committee_capable(manifest) else AuthorityLevel.VERIFIED_SYSTEM
    if {"evidence", "risk", "quorum", "negative"} & permissions:
        return AuthorityLevel.TRUSTED_AGENT if committee_capable(manifest) else AuthorityLevel.AGENT
    return AuthorityLevel.AGENT


def manifest_agent_can_request_blocker(agent_key: str) -> bool:
    manifest = agent_manifest(agent_key)
    if manifest is None:
        return False
    swarm = manifest.swarm if isinstance(manifest.swarm, dict) else {}
    permissions = {normalized_text(item) for item in swarm.get("signal_emit_permissions") or []}
    return bool(swarm.get("can_block")) and "stop_signal" in permissions


def agent_manifest(agent_key: str) -> Any | None:
    if not agent_key:
        return None
    manifests, _diagnostics = AgentRegistry().load()
    for manifest in manifests:
        if manifest.key == agent_key:
            return manifest
    return None


def normalized_text(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def manifest_terms(*values: Any) -> set[str]:
    output: set[str] = set()
    for value in values:
        items = value if isinstance(value, list) else [value]
        for item in items:
            text = normalized_text(item)
            if not text:
                continue
            output.add(text)
            output.update(part for part in text.replace("/", "_").split("_") if part)
    return output
