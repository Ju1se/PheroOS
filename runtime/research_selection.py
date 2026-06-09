from __future__ import annotations

from typing import Any

from runtime.legacy_research_selection import (
    legacy_company_financial_data_capability_type_markers,
    legacy_company_financial_data_metadata_flags,
    legacy_company_financial_data_skill_names,
    legacy_direct_wrds_data_capability_type_markers,
    legacy_direct_wrds_data_metadata_flags,
    legacy_direct_wrds_data_skill_names,
    legacy_investment_research_capability_type_markers,
    legacy_investment_research_metadata_flags,
    legacy_investment_research_skill_names,
    legacy_public_web_research_capability_type_markers,
    legacy_public_web_research_metadata_flags,
    legacy_public_web_research_skill_names,
    legacy_research_capability_type_markers,
    legacy_research_metadata_flags,
    legacy_research_skill_names,
)


def research_skill_selected(selected_skills: list[Any] | set[str]) -> bool:
    if isinstance(selected_skills, set):
        return bool(legacy_research_skill_names() & selected_skills)
    return any(skill_requests_research(skill) for skill in selected_skills)


def skill_requests_research(skill: Any) -> bool:
    if any(skill_flag(skill, flag) is True for flag in legacy_research_metadata_flags()):
        return True
    capability_types = skill_capability_types(skill)
    if capability_types.intersection(legacy_research_capability_type_markers()):
        return True
    if any(is_research_capability_type(capability_type) for capability_type in capability_types):
        return True
    return skill_name(skill) in legacy_research_skill_names()


def skill_requests_public_web_research(skill: Any) -> bool:
    if any(skill_flag(skill, flag) is True for flag in legacy_public_web_research_metadata_flags()):
        return True
    capability_types = skill_capability_types(skill)
    if capability_types.intersection(legacy_public_web_research_capability_type_markers()):
        return True
    return skill_name(skill) in legacy_public_web_research_skill_names()


def selected_skills_request_company_financial_data(selected_skills: list[Any]) -> bool:
    return any(skill_requests_company_financial_data(skill) for skill in selected_skills)


def skill_requests_company_financial_data(skill: Any) -> bool:
    if any(skill_flag(skill, flag) is True for flag in legacy_company_financial_data_metadata_flags()):
        return True
    capability_types = skill_capability_types(skill)
    if capability_types.intersection(legacy_company_financial_data_capability_type_markers()):
        return True
    return skill_name(skill) in legacy_company_financial_data_skill_names()


def selected_skills_request_investment_research(selected_skills: list[Any]) -> bool:
    return any(skill_requests_investment_research(skill) for skill in selected_skills)


def skill_requests_investment_research(skill: Any) -> bool:
    if any(skill_flag(skill, flag) is True for flag in legacy_investment_research_metadata_flags()):
        return True
    capability_types = skill_capability_types(skill)
    if capability_types.intersection(legacy_investment_research_capability_type_markers()):
        return True
    return skill_name(skill) in legacy_investment_research_skill_names()


def selected_skills_request_direct_wrds_data(selected_skills: list[Any]) -> bool:
    return any(skill_requests_direct_wrds_data(skill) for skill in selected_skills)


def skill_requests_direct_wrds_data(skill: Any) -> bool:
    if any(skill_flag(skill, flag) is True for flag in legacy_direct_wrds_data_metadata_flags()):
        return True
    capability_types = skill_capability_types(skill)
    if capability_types.intersection(legacy_direct_wrds_data_capability_type_markers()):
        return True
    return skill_name(skill) in legacy_direct_wrds_data_skill_names()


def skill_name(skill: Any) -> str:
    if isinstance(skill, str):
        return skill.strip()
    if isinstance(skill, dict):
        return str(skill.get("name") or "").strip()
    return str(getattr(skill, "name", "") or "").strip()


def skill_capability_types(skill: Any) -> set[str]:
    if isinstance(skill, dict):
        raw_types = skill.get("capability_types") or skill.get("capabilities") or []
    else:
        raw_types = getattr(skill, "capability_types", []) or getattr(skill, "capabilities", []) or []
    return {str(item).strip() for item in raw_types if str(item).strip()}


def skill_flag(skill: Any, flag: str) -> Any:
    if isinstance(skill, dict):
        return skill.get(flag)
    return getattr(skill, flag, None)


def is_research_capability_type(value: str) -> bool:
    normalized = value.strip().lower().replace("-", "_")
    return normalized.endswith("_research") or normalized.endswith(".research")
