from __future__ import annotations

from runtime.llm import ModelConfig


LEGACY_SCOPED_AGENT_FIELD_ALIASES = {
    "critic_agent": "critic",
    "red_team": "red_team_agent",
    "red_team_skeptic": "red_team_agent",
    "writer_agent": "writer",
    "final_judge_agent": "final_judge",
}

LEGACY_MODEL_CONFIG_NON_ROLE_FIELDS = frozenset(
    {
        "glm_fallback_models",
        "minimax_fallback_models",
        "default_fallback_models",
        "agent_model_overrides",
    }
)

LEGACY_EXECUTION_MODEL_ROLE_FIELDS = frozenset(
    {
        "executor",
        "market_execution_agent",
        "red_team_agent",
        "committee_challenge",
        "critic",
        "writer",
    }
)

LEGACY_FALLBACK_MODEL_ROLE_FIELDS = frozenset(
    {
        "research_agent_fallback",
        "quant_agent_fallback",
        "committee_member_fallback",
        "investment_committee_fallback",
    }
)


def legacy_scoped_agent_field(field: str) -> str:
    return LEGACY_SCOPED_AGENT_FIELD_ALIASES.get(field, field)


def model_role_fields() -> list[str]:
    return [
        field
        for field in ModelConfig.__dataclass_fields__
        if field not in LEGACY_MODEL_CONFIG_NON_ROLE_FIELDS
    ]


def model_roles_for_single_provider(model: str) -> dict[str, str]:
    return {field: model for field in model_role_fields()}


def model_roles_for_provider_mix(
    *,
    judgment_model: str,
    execution_model: str,
    fallback_model: str,
) -> dict[str, str]:
    roles = {field: judgment_model for field in model_role_fields()}
    for field in LEGACY_EXECUTION_MODEL_ROLE_FIELDS:
        roles[field] = execution_model
    for field in LEGACY_FALLBACK_MODEL_ROLE_FIELDS:
        roles[field] = fallback_model
    return roles
