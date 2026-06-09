from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.legacy_agent_registry import legacy_committee_agent_type


DEFAULT_CAPABILITIES_DIR = "capabilities"
DEFAULT_AGENTS_DIR = "agents"
REQUIRED_AGENT_FIELDS = {"key", "name", "agent_type", "focus"}


@dataclass(frozen=True)
class AgentManifest:
    key: str
    name: str
    agent_type: str
    focus: str
    focus_items: list[str]
    model_attr: str
    description: str
    default_enabled: bool
    order: int
    capability_id: str | None
    committee_role: str | None
    required_capabilities: list[str]
    required_tools: list[str]
    risk_level: str
    tags: list[str]
    accent: str
    short: str
    swarm: dict[str, Any]
    ui: dict[str, Any]
    path: Path

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "agent_type": self.agent_type,
            "focus": self.focus,
            "focus_items": self.focus_items,
            "model_attr": self.model_attr,
            "description": self.description,
            "default_enabled": self.default_enabled,
            "order": self.order,
            "capability_id": self.capability_id,
            "committee_role": self.committee_role,
            "required_capabilities": self.required_capabilities,
            "required_tools": self.required_tools,
            "risk_level": self.risk_level,
            "tags": self.tags,
            "accent": self.accent,
            "short": self.short,
            "swarm": self.swarm,
            "ui": self.ui,
            "path": str(self.path),
        }

    def to_committee_spec(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "model_attr": self.model_attr,
            "focus": self.focus,
            "order": self.order,
            "capability_id": self.capability_id,
            "committee_role": self.committee_role,
            "required_tools": self.required_tools,
            "risk_level": self.risk_level,
            "swarm": self.swarm,
        }


class AgentRegistry:
    """Read-only catalog of agent manifests shipped by local capabilities."""

    def __init__(
        self,
        *,
        capabilities_dir: str | Path | None = None,
        agents_dir: str | Path | None = None,
    ) -> None:
        self.capabilities_dir = Path(capabilities_dir or os.getenv("CAPABILITIES_DIR", DEFAULT_CAPABILITIES_DIR))
        self.agents_dir = Path(agents_dir or os.getenv("AGENTS_DIR", DEFAULT_AGENTS_DIR))

    def load(self) -> tuple[list[AgentManifest], list[dict[str, Any]]]:
        manifests: list[AgentManifest] = []
        diagnostics: list[dict[str, Any]] = []
        seen: dict[str, Path] = {}
        for path, capability_id in self._manifest_paths():
            try:
                manifest = load_agent_manifest(path, capability_id=capability_id)
            except ValueError as exc:
                diagnostics.append({"path": str(path), "status": "invalid", "error": str(exc)})
                continue
            if manifest.key in seen:
                raise ValueError(f"duplicate agent key {manifest.key!r}: {seen[manifest.key]} and {path}")
            seen[manifest.key] = path
            manifests.append(manifest)
        manifests.sort(key=lambda item: (item.order, item.key))
        return manifests, diagnostics

    def catalog(self, *, enabled_capability_ids: set[str] | None = None) -> dict[str, Any]:
        manifests, diagnostics = self.load()
        return {
            "agents": [
                manifest.to_public_dict()
                for manifest in manifests
                if capability_enabled(manifest, enabled_capability_ids)
            ],
            "diagnostics": diagnostics,
        }

    def committee_specs(
        self,
        *,
        selected_keys: list[str] | None = None,
        enabled_capability_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        manifests, _diagnostics = self.load()
        selected = {str(key) for key in selected_keys or [] if str(key).strip()}
        specs = []
        for manifest in manifests:
            if not committee_capable(manifest):
                continue
            if not capability_enabled(manifest, enabled_capability_ids):
                continue
            if selected and manifest.key not in selected:
                continue
            if not selected and not manifest.default_enabled:
                continue
            specs.append(manifest.to_committee_spec())
        return sorted(specs, key=lambda item: (item.get("order", 1000), item.get("key", "")))

    def validate_selected_keys(self, selected_keys: list[str]) -> dict[str, Any]:
        manifests, _diagnostics = self.load()
        known = {manifest.key for manifest in manifests}
        selected = [str(key).strip() for key in selected_keys if str(key).strip()]
        unknown = [key for key in selected if key not in known]
        return {
            "valid": not unknown,
            "selected": selected,
            "unknown": unknown,
        }

    def _manifest_paths(self) -> list[tuple[Path, str | None]]:
        paths: list[tuple[Path, str | None]] = []
        if self.capabilities_dir.exists():
            for path in sorted(self.capabilities_dir.glob("*/agents/*.json")):
                capability_id = path.parent.parent.name
                paths.append((path, capability_id))
        if self.agents_dir.exists():
            for path in sorted(self.agents_dir.glob("*/agent.json")):
                paths.append((path, None))
        return paths


def load_agent_manifest(path: Path, *, capability_id: str | None) -> AgentManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("agent manifest must be a JSON object")
    missing = sorted(REQUIRED_AGENT_FIELDS - set(payload))
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")
    key = normalize_agent_key(payload.get("key"))
    focus_items = normalize_focus(payload.get("focus"))
    ui = string_any_dict(payload.get("ui"))
    risk_level = str(payload.get("risk_level") or "low").strip().lower()
    if risk_level not in {"low", "medium", "high"}:
        raise ValueError("risk_level must be one of low, medium, high")
    return AgentManifest(
        key=key,
        name=str(payload["name"]).strip(),
        agent_type=str(payload["agent_type"]).strip() or "generic_agent",
        focus=", ".join(focus_items),
        focus_items=focus_items,
        model_attr=str(payload.get("model_attr") or key).strip(),
        description=str(payload.get("description") or "").strip(),
        default_enabled=bool(payload.get("default_enabled", True)),
        order=parse_order(payload.get("order")),
        capability_id=str(payload.get("capability_id") or capability_id or "").strip() or None,
        committee_role=str(payload.get("committee_role") or "").strip() or None,
        required_capabilities=string_list(payload.get("required_capabilities")),
        required_tools=string_list(payload.get("required_tools")),
        risk_level=risk_level,
        tags=string_list(payload.get("tags")),
        accent=str(payload.get("accent") or ui.get("accent") or "blue").strip(),
        short=str(payload.get("short") or key[:3]).strip().upper(),
        swarm=string_any_dict(payload.get("swarm")),
        ui=ui,
        path=path,
    )


def committee_capable(manifest: Any) -> bool:
    if isinstance(manifest, dict):
        committee_role = str(manifest.get("committee_role") or "").strip()
        agent_type_value = manifest.get("agent_type")
    else:
        committee_role = str(getattr(manifest, "committee_role", "") or "").strip()
        agent_type_value = getattr(manifest, "agent_type", "")
    if committee_role:
        return True
    return legacy_committee_agent_type(str(agent_type_value or ""))


def capability_enabled(manifest: AgentManifest, enabled_capability_ids: set[str] | None) -> bool:
    if enabled_capability_ids is None or manifest.capability_id is None:
        return True
    return manifest.capability_id in enabled_capability_ids


def normalize_agent_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    normalized = "".join(char if char.isalnum() or char in {"_", "-", "."} else "_" for char in text).strip("._-")
    if not normalized:
        raise ValueError("agent key must not be empty")
    return normalized


def parse_order(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1000


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_focus(value: Any) -> list[str]:
    if isinstance(value, list):
        output = [str(item).strip() for item in value if str(item).strip()]
        if output:
            return output
    text = str(value or "").strip()
    if not text:
        raise ValueError("focus must not be empty")
    return [text]


def string_any_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}
