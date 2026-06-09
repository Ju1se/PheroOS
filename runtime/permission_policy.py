from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime.capability_registry import CapabilityManifest


AUTO_GRANT_PERMISSIONS = {
    "data:read",
    "model:chat",
    "skill:read",
    "tool:deterministic-read",
    "network:approved-provider",
    "network:wrds",
    "secret:wrds",
    "secret:model-provider",
}

CONFIRMATION_REQUIRED_PERMISSIONS = {
    "filesystem:write",
    "shell:execute",
    "network:arbitrary",
    "email:send",
    "trade:execute",
    "database:write",
    "credential:export",
}


@dataclass(frozen=True)
class PermissionDecision:
    capability_id: str
    auto_enable: bool
    needs_confirmation: bool
    permission_grants: list[str]
    blocked_permissions: list[str]
    risk_level: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "auto_enable": self.auto_enable,
            "needs_confirmation": self.needs_confirmation,
            "permission_grants": self.permission_grants,
            "blocked_permissions": self.blocked_permissions,
            "risk_level": self.risk_level,
            "reason": self.reason,
        }


def evaluate_capability_permissions(manifest: CapabilityManifest) -> PermissionDecision:
    permissions = set(manifest.permissions)
    blocked = sorted(permissions.intersection(CONFIRMATION_REQUIRED_PERMISSIONS))
    unknown = sorted(permissions - AUTO_GRANT_PERMISSIONS - CONFIRMATION_REQUIRED_PERMISSIONS)
    blocked_permissions = sorted(set(blocked + unknown))
    needs_confirmation = (
        manifest.requires_confirmation
        or manifest.risk_level in {"medium", "high"}
        or bool(blocked_permissions)
    )
    auto_enable = not needs_confirmation
    if auto_enable:
        reason = "low-risk capability with auto-grant permissions"
    elif blocked:
        reason = "dangerous permission requires user confirmation"
    elif unknown:
        reason = "unknown permission requires user confirmation"
    else:
        reason = "capability policy requires user confirmation"
    return PermissionDecision(
        capability_id=manifest.id,
        auto_enable=auto_enable,
        needs_confirmation=needs_confirmation,
        permission_grants=sorted(permissions.intersection(AUTO_GRANT_PERMISSIONS)),
        blocked_permissions=blocked_permissions,
        risk_level=manifest.risk_level,
        reason=reason,
    )


def flatten_permission_grants(value: Any) -> set[str]:
    """Normalize OS-plan/runtime permission grant shapes into a flat set."""
    grants: set[str] = set()
    if value is None:
        return grants
    if isinstance(value, str):
        text = value.strip()
        return {text} if text else grants
    if isinstance(value, dict):
        for key in ("permission_grants", "grants", "permissions"):
            grants.update(flatten_permission_grants(value.get(key)))
        return grants
    if isinstance(value, list | tuple | set):
        for item in value:
            grants.update(flatten_permission_grants(item))
    return {grant for grant in grants if grant}


def is_permission_granted(permission: str, grants: Any) -> bool:
    """Return true when a permission is explicitly granted or safely auto-granted."""
    if permission in AUTO_GRANT_PERMISSIONS:
        return True
    return permission in flatten_permission_grants(grants)
