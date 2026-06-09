from __future__ import annotations

from typing import Any


LEGACY_WRDS_PROVIDER = "wrds"
LEGACY_WRDS_TOOL_PREFIX = "wrds_"
LEGACY_FINANCIAL_DATA_KIND = "financial_data_source"
LEGACY_PROFESSIONAL_FINANCIAL_DATABASE_KEY = "professional_financial_database"


def legacy_wrds_capability_exposes_data_source(capability: dict[str, Any]) -> bool:
    return LEGACY_WRDS_PROVIDER in capability.get("connections", []) or any(
        str(tool).startswith(LEGACY_WRDS_TOOL_PREFIX)
        for tool in capability.get("tools", [])
    )


def legacy_wrds_connection_record(record: dict[str, Any]) -> bool:
    return record.get("kind") == LEGACY_FINANCIAL_DATA_KIND and record.get("provider") == LEGACY_WRDS_PROVIDER


def legacy_wrds_active_connection_keys(record: dict[str, Any]) -> set[str]:
    if not legacy_wrds_connection_record(record):
        return set()
    return {
        LEGACY_WRDS_PROVIDER,
        LEGACY_FINANCIAL_DATA_KIND,
        LEGACY_PROFESSIONAL_FINANCIAL_DATABASE_KEY,
    }
