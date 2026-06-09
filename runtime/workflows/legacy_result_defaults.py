from __future__ import annotations


LEGACY_SKIPPED_ANALYSIS_REASONS = {
    "investment_committee_not_required": "investment committee not required",
    "research_not_required": "research not required",
    "quant_analysis_not_required": "quant analysis not required",
    "domain_judgment_not_required": "domain judgment not required",
    "agent_decision_not_required": "agent decision not required",
    "runtime_preflight_blocked_research": "runtime preflight blocked research",
    "runtime_preflight_blocked_quant_analysis": "runtime preflight blocked quant analysis",
    "runtime_preflight_blocked_domain_analysis": "runtime preflight blocked domain analysis",
    "runtime_preflight_blocked_agent_decision": "runtime preflight blocked agent decision",
    "runtime_preflight_blocked_committee": "runtime preflight blocked committee",
}
LEGACY_RUNTIME_PREFLIGHT_BLOCKED_SUMMARY = (
    "Runtime preflight blocked graph execution before model, tool, WRDS, or committee work."
)
LEGACY_MEMORY_CONTEXT_METADATA_KEYS = (
    "user_profile",
    "preferences",
    "context",
    "course",
    "investment_framework",
    "writing_style",
    "history_summary",
)


def legacy_skipped_analysis_reason(key: str) -> str:
    return LEGACY_SKIPPED_ANALYSIS_REASONS.get(key, key)


def legacy_runtime_preflight_blocked_summary() -> str:
    return LEGACY_RUNTIME_PREFLIGHT_BLOCKED_SUMMARY


def legacy_memory_context_metadata_keys() -> tuple[str, ...]:
    return LEGACY_MEMORY_CONTEXT_METADATA_KEYS
