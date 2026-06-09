from __future__ import annotations

from typing import Any


def protocol_errors(diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in diagnostics if item.get("severity") == "error"]


def protocol_warnings(diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(item) for item in diagnostics if item.get("severity") == "warning"]
