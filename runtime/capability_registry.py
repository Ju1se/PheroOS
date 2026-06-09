from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from runtime.capability_manifest_security import (
    build_manifest_security_report,
    normalize_sandbox_policy,
    normalize_trust_level,
    redact_signature,
)


DEFAULT_CAPABILITIES_DIR = "capabilities"
DEFAULT_CAPABILITY_STATE_PATH = ".local/capabilities.json"
DEFAULT_TENANT_ID = "default"
RiskLevel = Literal["low", "medium", "high"]

REQUIRED_MANIFEST_FIELDS = {
    "id",
    "name",
    "version",
    "description",
    "capability_types",
    "permissions",
    "risk_level",
}

KNOWN_CAPABILITY_PERMISSIONS = {
    "data:read",
    "model:chat",
    "skill:read",
    "tool:deterministic-read",
    "network:approved-provider",
    "network:wrds",
    "secret:wrds",
    "secret:model-provider",
    "filesystem:write",
    "shell:execute",
    "network:arbitrary",
    "email:send",
    "trade:execute",
    "database:write",
    "credential:export",
}


@dataclass(frozen=True)
class CapabilityManifest:
    id: str
    name: str
    version: str
    description: str
    capability_types: list[str]
    permissions: list[str]
    risk_level: RiskLevel
    requires_confirmation: bool
    connections: list[str]
    required_connections: list[str]
    tools: list[str]
    skills: list[str]
    data_packages: list[str]
    entrypoints: dict[str, str]
    agents_path: str | None
    ui: dict[str, Any]
    path: Path | None
    data_sources: list[dict[str, Any]] = field(default_factory=list)
    swarm: dict[str, Any] = field(default_factory=dict)
    protocol: dict[str, Any] = field(default_factory=dict)
    trust_level: str = "first_party_reviewed"
    sandbox: dict[str, Any] = field(default_factory=dict)
    allowed_imports: list[str] = field(default_factory=list)
    network_allowlist: list[str] = field(default_factory=list)
    signature: dict[str, Any] = field(default_factory=dict)
    checksum: str | None = None
    security_diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        permission_diagnostics = self.permission_diagnostics()
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "capability_types": self.capability_types,
            "permissions": self.permissions,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "connections": self.connections,
            "required_connections": self.required_connections,
            "tools": self.tools,
            "skills": self.skills,
            "data_packages": self.data_packages,
            "data_sources": [dict(item) for item in self.data_sources],
            "entrypoints": self.entrypoints,
            "agents_path": self.agents_path,
            "ui": self.ui,
            "swarm": self.swarm,
            "trust_level": self.trust_level,
            "sandbox": self.sandbox,
            "allowed_imports": self.allowed_imports,
            "network_allowlist": self.network_allowlist,
            "signature": redact_signature(self.signature),
            "checksum": self.checksum,
            "security_diagnostics": self.security_diagnostics,
            "permission_diagnostics": permission_diagnostics,
            "path": str(self.path) if self.path is not None else None,
            "protocol": self.protocol,
        }

    def permission_diagnostics(self) -> dict[str, Any]:
        unknown = sorted(set(self.permissions) - KNOWN_CAPABILITY_PERMISSIONS)
        return {
            "unknown_permissions": unknown,
            "status": "warning" if unknown else "ok",
        }


class CapabilityRegistry:
    """Read-only catalog of locally reviewed AI OS capabilities."""

    def __init__(self, capabilities_dir: str | Path | None = None) -> None:
        self.capabilities_dir = Path(capabilities_dir or os.getenv("CAPABILITIES_DIR", DEFAULT_CAPABILITIES_DIR))

    def load(self) -> tuple[list[CapabilityManifest], list[dict[str, Any]]]:
        if not self.capabilities_dir.exists():
            return [], []
        manifests: list[CapabilityManifest] = []
        diagnostics: list[dict[str, Any]] = []
        seen: dict[str, Path] = {}
        for manifest_path in sorted(self.capabilities_dir.glob("*/capability.json")):
            try:
                manifest = load_manifest(manifest_path)
            except ValueError as exc:
                diagnostics.append(
                    {
                        "path": str(manifest_path),
                        "status": "invalid",
                        "error": str(exc),
                    }
                )
                continue
            if manifest.id in seen:
                raise ValueError(
                    f"duplicate capability id {manifest.id!r}: {seen[manifest.id]} and {manifest_path}"
                )
            seen[manifest.id] = manifest_path
            manifests.append(manifest)
        return manifests, diagnostics

    def catalog(self) -> dict[str, Any]:
        manifests, diagnostics = self.load()
        return {
            "capabilities": [manifest.to_public_dict() for manifest in manifests],
            "diagnostics": diagnostics,
        }

    def get(self, capability_id: str) -> CapabilityManifest | None:
        manifests, _ = self.load()
        for manifest in manifests:
            if manifest.id == capability_id:
                return manifest
        return None

    def resolve_required(self, required_types: list[str]) -> list[CapabilityManifest]:
        required = {str(item) for item in required_types}
        manifests, _ = self.load()
        matched = []
        for manifest in manifests:
            if required.intersection(manifest.capability_types):
                matched.append(manifest)
        return matched

    def list_by_type(self, capability_type: str) -> list[CapabilityManifest]:
        manifests, _ = self.load()
        return [manifest for manifest in manifests if capability_type in manifest.capability_types]

    def missing_required_connections(
        self,
        *,
        capability_id: str,
        active_connection_keys: set[str],
    ) -> list[str]:
        manifest = self.get(capability_id)
        if manifest is None:
            return []
        return [
            connection
            for connection in manifest.required_connections
            if connection not in active_connection_keys
        ]


class CapabilityStateStore:
    """Tenant-scoped enabled capability state.

    The catalog is immutable plugin metadata; this store records which local
    reviewed capabilities are active for a tenant.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.getenv("CAPABILITY_STATE_PATH", DEFAULT_CAPABILITY_STATE_PATH))

    def enabled_ids(self, *, tenant_id: str = DEFAULT_TENANT_ID) -> list[str]:
        tenant = self._tenant(tenant_id)
        enabled = tenant.get("enabled", {})
        if not isinstance(enabled, dict):
            return []
        return sorted(enabled)

    def disabled_ids(self, *, tenant_id: str = DEFAULT_TENANT_ID) -> list[str]:
        tenant = self._tenant(tenant_id)
        disabled = tenant.get("disabled", {})
        if not isinstance(disabled, dict):
            return []
        return sorted(disabled)

    def enable(
        self,
        *,
        capability_id: str,
        tenant_id: str = DEFAULT_TENANT_ID,
        reason: str = "manual",
        permission_grants: list[str] | None = None,
    ) -> dict[str, Any]:
        data = self._read()
        tenant = data.setdefault("tenants", {}).setdefault(tenant_id, {"enabled": {}})
        enabled = tenant.setdefault("enabled", {})
        disabled = tenant.setdefault("disabled", {})
        if isinstance(disabled, dict):
            disabled.pop(capability_id, None)
        enabled[capability_id] = {
            "id": capability_id,
            "status": "enabled",
            "reason": reason,
            "permission_grants": permission_grants or [],
            "enabled_at": utc_now(),
        }
        self._write(data)
        return enabled[capability_id]

    def disable(self, *, capability_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> bool:
        data = self._read()
        tenant = data.setdefault("tenants", {}).setdefault(tenant_id, {"enabled": {}, "disabled": {}})
        enabled = tenant.setdefault("enabled", {})
        existed = capability_id in enabled
        enabled.pop(capability_id, None)
        disabled = tenant.setdefault("disabled", {})
        disabled[capability_id] = {
            "id": capability_id,
            "status": "disabled",
            "disabled_at": utc_now(),
        }
        self._write(data)
        return existed

    def active_capabilities(
        self,
        *,
        registry: CapabilityRegistry,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> list[dict[str, Any]]:
        manifests, _diagnostics = registry.load()
        by_id = {manifest.id: manifest for manifest in manifests}
        output = []
        tenant = self._tenant(tenant_id)
        enabled = tenant.get("enabled", {}) if isinstance(tenant.get("enabled"), dict) else {}
        for capability_id in self.enabled_ids(tenant_id=tenant_id):
            manifest = by_id.get(capability_id)
            if manifest:
                state_record = enabled.get(capability_id) if isinstance(enabled, dict) else {}
                output.append(
                    {
                        **manifest.to_public_dict(),
                        "permission_grants": list((state_record or {}).get("permission_grants") or []),
                        "enabled_reason": (state_record or {}).get("reason"),
                        "enabled_at": (state_record or {}).get("enabled_at"),
                    }
                )
        return output

    def _tenant(self, tenant_id: str) -> dict[str, Any]:
        data = self._read()
        tenant = data.get("tenants", {}).get(tenant_id, {})
        return tenant if isinstance(tenant, dict) else {}

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "tenants": {}}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {"schema_version": 1, "tenants": {}}
        if not isinstance(data, dict):
            return {"schema_version": 1, "tenants": {}}
        data.setdefault("schema_version", 1)
        data.setdefault("tenants", {})
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, self.path)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass


def load_manifest(path: Path) -> CapabilityManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("capability manifest must be a JSON object")

    missing = sorted(REQUIRED_MANIFEST_FIELDS - set(payload))
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")

    risk_level = str(payload.get("risk_level") or "").lower()
    if risk_level not in {"low", "medium", "high"}:
        raise ValueError("risk_level must be one of low, medium, high")

    capability_id = normalize_capability_id(payload.get("id"))
    required_connections = string_list(payload.get("required_connections"))
    legacy_connections = string_list(payload.get("connections"))
    connections = required_connections or legacy_connections
    agents_path = str(payload.get("agents_path") or "").strip() or None
    security_report = build_manifest_security_report(payload, capability_dir=path.parent)
    trust_level = normalize_trust_level(payload.get("trust_level"))
    sandbox = normalize_sandbox_policy(payload.get("sandbox"))
    return CapabilityManifest(
        id=capability_id,
        name=str(payload["name"]).strip(),
        version=str(payload["version"]).strip(),
        description=str(payload["description"]).strip(),
        capability_types=string_list(payload.get("capability_types")),
        permissions=string_list(payload.get("permissions")),
        risk_level=risk_level,  # type: ignore[arg-type]
        requires_confirmation=bool(payload.get("requires_confirmation", False)),
        connections=connections,
        required_connections=connections,
        tools=string_list(payload.get("tools")),
        skills=string_list(payload.get("skills")),
        data_packages=string_list(payload.get("data_packages")),
        data_sources=list_of_dicts(payload.get("data_sources")),
        entrypoints=string_dict(payload.get("entrypoints")),
        agents_path=agents_path,
        ui=string_any_dict(payload.get("ui")),
        path=path,
        swarm=string_any_dict(payload.get("swarm")),
        protocol=string_any_dict(payload.get("protocol") or payload.get("pheroos_protocol") or payload.get("pheroos")),
        trust_level=trust_level,
        sandbox=sandbox,
        allowed_imports=string_list(payload.get("allowed_imports")),
        network_allowlist=string_list(payload.get("network_allowlist")),
        signature=string_any_dict(payload.get("signature")),
        checksum=str(payload.get("checksum") or "").strip() or None,
        security_diagnostics=security_report,
    )


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


def string_any_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
