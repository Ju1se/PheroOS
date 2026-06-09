from __future__ import annotations

from typing import Any


LEGACY_INDEPENDENT_SCOUT_POLICY_SOURCE = "legacy_independent_scout_policy"
LEGACY_SOURCE_FAMILY_RULES = [
    {"family": "risk", "terms": ["risk", "red_team"]},
    {"family": "data", "terms": ["data", "quant"]},
    {"family": "analyst", "terms": ["fundamental", "industry"]},
    {"family": "market", "terms": ["market"]},
]
LEGACY_DEFAULT_SOURCE_FAMILY = "agent"
LEGACY_MIN_INDEPENDENCE_SCORE = 0.5
LEGACY_FORCE_FALLBACK_WHEN_LOW_INDEPENDENCE = True
LEGACY_FALLBACK_CANDIDATE_LABEL = "fallback candidate"
LEGACY_INDEPENDENT_SCOUT_SIGNAL_TEMPLATE = "Independent scout diversity is {source_diversity}."
LEGACY_LOW_INDEPENDENCE_REASON_TEMPLATE = "source diversity below quorum policy threshold"
LEGACY_FORCED_FALLBACK_REASON_TEMPLATE = "low independent support diversity; forced {fallback_label}"
LEGACY_CONTROLLER_QUORUM_POLICY_OVERRIDE_FIELDS = {
    "min_independence_score",
    "force_fallback_when_low_independence",
    "candidate_fallback",
    "fallback_candidate",
}


def legacy_independent_scout_policy_source() -> str:
    return LEGACY_INDEPENDENT_SCOUT_POLICY_SOURCE


def legacy_independent_scout_policy() -> dict[str, Any]:
    return {
        "source_family_rules": [
            {"family": str(rule["family"]), "terms": list(rule["terms"])}
            for rule in LEGACY_SOURCE_FAMILY_RULES
        ],
        "default_source_family": LEGACY_DEFAULT_SOURCE_FAMILY,
        "min_independence_score": LEGACY_MIN_INDEPENDENCE_SCORE,
        "force_fallback_when_low_independence": LEGACY_FORCE_FALLBACK_WHEN_LOW_INDEPENDENCE,
        "signal_template": LEGACY_INDEPENDENT_SCOUT_SIGNAL_TEMPLATE,
        "low_independence_reason_template": LEGACY_LOW_INDEPENDENCE_REASON_TEMPLATE,
        "forced_fallback_reason_template": LEGACY_FORCED_FALLBACK_REASON_TEMPLATE,
    }


def legacy_controller_quorum_policy_override_fields() -> set[str]:
    return set(LEGACY_CONTROLLER_QUORUM_POLICY_OVERRIDE_FIELDS)


def legacy_independent_scout_signal_template() -> str:
    return LEGACY_INDEPENDENT_SCOUT_SIGNAL_TEMPLATE


def legacy_independent_scout_low_independence_reason_template() -> str:
    return LEGACY_LOW_INDEPENDENCE_REASON_TEMPLATE


def legacy_independent_scout_forced_fallback_reason_template() -> str:
    return LEGACY_FORCED_FALLBACK_REASON_TEMPLATE


def independent_scout_fallback_label(candidate: dict[str, Any] | None) -> str:
    if not isinstance(candidate, dict):
        return LEGACY_FALLBACK_CANDIDATE_LABEL
    return str(candidate.get("label") or candidate.get("id") or LEGACY_FALLBACK_CANDIDATE_LABEL)


def source_family_for_agent(agent: str, policy: dict[str, Any]) -> str:
    text = agent.lower()
    for rule in policy.get("source_family_rules") if isinstance(policy.get("source_family_rules"), list) else []:
        if not isinstance(rule, dict):
            continue
        family = str(rule.get("family") or "").strip()
        terms = [str(term).strip().lower() for term in rule.get("terms") or [] if str(term).strip()]
        if family and any(term in text for term in terms):
            return family
    return str(policy.get("default_source_family") or LEGACY_DEFAULT_SOURCE_FAMILY).strip() or LEGACY_DEFAULT_SOURCE_FAMILY


def render_independent_scout_template(template: str, values: dict[str, Any]) -> str:
    fallback_label = values.get("fallback_label") or independent_scout_fallback_label(values.get("fallback_candidate"))
    replacements = {
        "{source_diversity}": str(values.get("source_diversity") or 0),
        "{support_count}": str(values.get("support_count") or 0),
        "{independent_support_count}": str(values.get("independent_support_count") or 0),
        "{correlation_penalty}": str(values.get("correlation_penalty") or 0),
        "{min_independence_score}": str(values.get("min_independence_score") or 0),
        "{fallback_label}": str(fallback_label),
    }
    text = str(template or "")
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    return text.strip()
