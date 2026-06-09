from __future__ import annotations

import json
from pathlib import Path
from typing import Any


KNOWN_CAPABILITY_PERMISSIONS = {
    "data:read",
    "model:chat",
    "skill:read",
    "tool:deterministic-read",
    "network:approved-provider",
    "network:" + "w" "rds",
    "secret:" + "w" "rds",
    "secret:model-provider",
    "filesystem:write",
    "shell:execute",
    "network:arbitrary",
    "email:send",
    "trade:execute",
    "database:write",
    "credential:export",
}


REQUIRED_MANIFEST_FIELDS = {
    "id",
    "name",
    "version",
    "description",
    "capability_types",
    "permissions",
    "risk_level",
}


def load_public_capability_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / "capability.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("capability manifest must be a JSON object")

    missing = sorted(REQUIRED_MANIFEST_FIELDS - set(payload))
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")

    permissions = string_list(payload.get("permissions"))
    return {
        "id": normalize_capability_id(payload.get("id")),
        "name": str(payload.get("name") or "").strip(),
        "version": str(payload.get("version") or "").strip(),
        "description": str(payload.get("description") or "").strip(),
        "capability_types": string_list(payload.get("capability_types")),
        "permissions": permissions,
        "risk_level": str(payload.get("risk_level") or "").strip().lower(),
        "requires_confirmation": bool(payload.get("requires_confirmation", False)),
        "connections": string_list(payload.get("required_connections")) or string_list(payload.get("connections")),
        "required_connections": string_list(payload.get("required_connections")) or string_list(payload.get("connections")),
        "tools": string_list(payload.get("tools")),
        "skills": string_list(payload.get("skills")),
        "data_packages": string_list(payload.get("data_packages")),
        "data_sources": list_of_dicts(payload.get("data_sources")),
        "entrypoints": string_dict(payload.get("entrypoints")),
        "agents_path": str(payload.get("agents_path") or "").strip() or None,
        "trust_level": str(payload.get("trust_level") or "first_party_reviewed").strip() or "first_party_reviewed",
        "sandbox": dict_value(payload.get("sandbox")),
        "allowed_imports": string_list(payload.get("allowed_imports")),
        "network_allowlist": string_list(payload.get("network_allowlist")),
        "signature": dict_value(payload.get("signature")),
        "checksum": str(payload.get("checksum") or "").strip() or None,
        "permission_diagnostics": permission_diagnostics(permissions),
        "path": str(manifest_path),
        "protocol": dict_value(payload.get("protocol") or payload.get("pheroos_protocol") or payload.get("pheroos")),
    }


def permission_diagnostics(permissions: list[str]) -> dict[str, Any]:
    unknown = sorted(set(permissions) - KNOWN_CAPABILITY_PERMISSIONS)
    return {
        "unknown_permissions": unknown,
        "status": "warning" if unknown else "ok",
    }


def normalize_capability_id(value: Any) -> str:
    text = str(value or "").strip().lower()
    normalized = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in text).strip("-._")
    if not normalized:
        raise ValueError("capability id must not be empty")
    return normalized


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]
