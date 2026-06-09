from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from runtime.swarm.types import clamp01


DEFAULT_AGENT_PROFILE_PATH = ".local/swarm_agent_profiles.json"


@dataclass
class AgentProfile:
    agent_id: str
    tenant_id: str = "default"
    capabilities: dict[str, float] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    reliability: float = 0.65
    constraint_violation_rate: float = 0.0
    recent_failures: list[str] = field(default_factory=list)
    total_runs: int = 0
    successful_runs: int = 0

    def threshold_for(self, task_type: str, default: float) -> float:
        return clamp01(self.thresholds.get(task_type, default))

    def capability_for(self, task_type: str, default: float = 0.5) -> float:
        return clamp01(self.capabilities.get(task_type, default))

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "tenant_id": self.tenant_id,
            "capabilities": self.capabilities,
            "thresholds": self.thresholds,
            "reliability": self.reliability,
            "constraint_violation_rate": self.constraint_violation_rate,
            "recent_failures": self.recent_failures[-10:],
            "total_runs": self.total_runs,
            "successful_runs": self.successful_runs,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AgentProfile":
        return cls(
            agent_id=str(payload.get("agent_id") or payload.get("id") or "unknown"),
            tenant_id=str(payload.get("tenant_id") or "default"),
            capabilities={str(k): clamp01(v) for k, v in (payload.get("capabilities") or {}).items()},
            thresholds={str(k): clamp01(v) for k, v in (payload.get("thresholds") or {}).items()},
            reliability=clamp01(payload.get("reliability", 0.65)),
            constraint_violation_rate=clamp01(payload.get("constraint_violation_rate", 0.0)),
            recent_failures=[str(item) for item in payload.get("recent_failures", [])[-10:]],
            total_runs=int(payload.get("total_runs") or 0),
            successful_runs=int(payload.get("successful_runs") or 0),
        )


class AgentProfileStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.getenv("SWARM_AGENT_PROFILE_PATH", DEFAULT_AGENT_PROFILE_PATH))

    def load_all(self, *, tenant_id: str | None = "default") -> dict[str, AgentProfile]:
        payload = self._read_payload()
        profiles_by_tenant = self._profiles_by_tenant(payload)
        if tenant_id is not None:
            profiles = profiles_by_tenant.get(str(tenant_id), {})
            return {
                str(agent_id): AgentProfile.from_dict({**profile, "agent_id": agent_id, "tenant_id": str(tenant_id)})
                for agent_id, profile in profiles.items()
                if isinstance(profile, dict)
            }
        loaded: dict[str, AgentProfile] = {}
        for profile_tenant_id, profiles in profiles_by_tenant.items():
            for agent_id, profile in profiles.items():
                if not isinstance(profile, dict):
                    continue
                key = str(agent_id) if profile_tenant_id == "default" else f"{profile_tenant_id}:{agent_id}"
                loaded[key] = AgentProfile.from_dict(
                    {**profile, "agent_id": str(agent_id), "tenant_id": profile_tenant_id}
                )
        return loaded

    def save_all(self, profiles: dict[str, AgentProfile], *, tenant_id: str = "default") -> None:
        payload = self._read_payload()
        by_tenant = self._profiles_by_tenant(payload)
        target_tenant = str(tenant_id or "default")
        by_tenant[target_tenant] = {
            agent_id: {**profile.to_dict(), "tenant_id": target_tenant}
            for agent_id, profile in sorted(profiles.items())
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        output = {
            "schema_version": "pheroos.agent_profiles.v2",
            "tenants": {
                profile_tenant_id: {"profiles": profiles}
                for profile_tenant_id, profiles in sorted(by_tenant.items())
                if profiles
            },
        }
        self.path.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def get(self, agent_id: str, *, tenant_id: str = "default") -> AgentProfile:
        profiles = self.load_all(tenant_id=tenant_id)
        return profiles.get(agent_id) or AgentProfile(agent_id=agent_id, tenant_id=tenant_id)

    def update_many(self, updates: dict[str, AgentProfile], *, tenant_id: str = "default") -> None:
        profiles = self.load_all(tenant_id=tenant_id)
        profiles.update(updates)
        for profile in profiles.values():
            profile.tenant_id = tenant_id
        self.save_all(profiles, tenant_id=tenant_id)

    def _read_payload(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {"profiles": payload}

    def _profiles_by_tenant(self, payload: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
        tenants = payload.get("tenants") if isinstance(payload.get("tenants"), dict) else None
        if tenants is not None:
            normalized: dict[str, dict[str, dict[str, Any]]] = {}
            for tenant_id, tenant_payload in tenants.items():
                profiles = tenant_payload.get("profiles") if isinstance(tenant_payload, dict) else {}
                if isinstance(profiles, dict):
                    normalized[str(tenant_id)] = {
                        str(agent_id): profile
                        for agent_id, profile in profiles.items()
                        if isinstance(profile, dict)
                    }
            return normalized
        profiles = payload.get("profiles") if isinstance(payload, dict) else payload
        if not isinstance(profiles, dict):
            return {}
        by_tenant: dict[str, dict[str, dict[str, Any]]] = {}
        for agent_id, profile in profiles.items():
            if not isinstance(profile, dict):
                continue
            tenant_id = str(profile.get("tenant_id") or "default")
            by_tenant.setdefault(tenant_id, {})[str(agent_id)] = profile
        return by_tenant


def update_profile_from_result(
    profile: AgentProfile,
    *,
    task_type: str,
    success: bool,
    hard_veto: bool = False,
    failure_reason: str | None = None,
) -> AgentProfile:
    profile.total_runs += 1
    if success:
        profile.successful_runs += 1
        profile.reliability = clamp01(profile.reliability + 0.01)
        profile.capabilities[task_type] = clamp01(profile.capability_for(task_type) + 0.03)
        profile.thresholds[task_type] = clamp01(profile.threshold_for(task_type, 0.5) - 0.02)
    else:
        profile.reliability = clamp01(profile.reliability - 0.03)
        profile.capabilities[task_type] = clamp01(profile.capability_for(task_type) - 0.02)
        profile.thresholds[task_type] = clamp01(profile.threshold_for(task_type, 0.5) + 0.04)
        if failure_reason:
            profile.recent_failures.append(str(failure_reason))
            profile.recent_failures = profile.recent_failures[-10:]
    if hard_veto:
        profile.capabilities["veto_review"] = clamp01(profile.capability_for("veto_review") + 0.02)
    return profile
