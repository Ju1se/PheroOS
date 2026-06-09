from __future__ import annotations

from typing import Any


LEGACY_COMMITTEE_AGENT_TYPES = {"investment_committee_member", "committee_member"}
LEGACY_COMMITTEE_AGENT_CATALOG_METADATA_KEY = "committee_agent_catalog"
LEGACY_AGENT_PROPOSAL_MODULES = {"committee_agent"}
GENERIC_SELECTED_AGENT_METADATA_KEYS = ("selected_agent_ids", "agent_ids", "selected_agents")
LEGACY_SELECTED_AGENT_METADATA_KEYS = ("committee_member_ids", "committee_members", "selected_committee_members")


def legacy_committee_agent_type(agent_type: str) -> bool:
    normalized = str(agent_type or "").strip().lower().replace("-", "_")
    return normalized in LEGACY_COMMITTEE_AGENT_TYPES or normalized.endswith("_committee_member")


def legacy_committee_agent_catalog_metadata(agents: list[Any]) -> dict[str, Any]:
    return {LEGACY_COMMITTEE_AGENT_CATALOG_METADATA_KEY: agents}


def legacy_agent_proposal_modules() -> set[str]:
    return set(LEGACY_AGENT_PROPOSAL_MODULES)


def legacy_committee_agent_catalog_from_metadata(metadata: dict[str, Any] | None) -> list[Any]:
    if not isinstance(metadata, dict):
        return []
    value = metadata.get(LEGACY_COMMITTEE_AGENT_CATALOG_METADATA_KEY)
    return value if isinstance(value, list) else []


def selected_agent_ids_from_metadata(metadata: dict[str, Any] | None) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    for key in (*GENERIC_SELECTED_AGENT_METADATA_KEYS, *LEGACY_SELECTED_AGENT_METADATA_KEYS):
        selected = normalize_selected_agent_ids(metadata.get(key))
        if selected:
            return selected
    return []


def normalize_selected_agent_ids(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []
