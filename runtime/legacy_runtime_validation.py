from __future__ import annotations

from typing import Any


LEGACY_WRDS_CAPABILITY_ID = "wrds-financial-data"
LEGACY_WRDS_STATUS_TOOL_NAME = "wrds_status"

LEGACY_WRDS_MISSING_CONNECTION_ISSUE = {
    "code": "wrds_capability_without_connection",
    "severity": "blocking",
    "message": "WRDS capability is enabled but no active WRDS connection is configured.",
}

LEGACY_WRDS_TOOLS_NOT_REGISTERED_ISSUE = {
    "code": "wrds_tools_not_registered",
    "severity": "blocking",
    "message": "WRDS capability is enabled but WRDS tools were not registered.",
}

LEGACY_WRDS_VALIDATION_ISSUE_CODES = frozenset(
    {
        LEGACY_WRDS_MISSING_CONNECTION_ISSUE["code"],
        LEGACY_WRDS_TOOLS_NOT_REGISTERED_ISSUE["code"],
    }
)


def legacy_wrds_capability_enabled(capabilities: list[dict[str, Any]]) -> bool:
    return any(capability.get("id") == LEGACY_WRDS_CAPABILITY_ID for capability in capabilities)


def legacy_wrds_status_tool_name() -> str:
    return LEGACY_WRDS_STATUS_TOOL_NAME


def legacy_wrds_missing_connection_issue() -> dict[str, str]:
    return dict(LEGACY_WRDS_MISSING_CONNECTION_ISSUE)


def legacy_wrds_tools_not_registered_issue() -> dict[str, str]:
    return dict(LEGACY_WRDS_TOOLS_NOT_REGISTERED_ISSUE)


def legacy_wrds_validation_issue_codes() -> set[str]:
    return set(LEGACY_WRDS_VALIDATION_ISSUE_CODES)
