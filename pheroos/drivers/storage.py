from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pheroos.drivers.base import DriverDescriptor


@dataclass(frozen=True)
class StorageDriverDescriptor(DriverDescriptor):
    event_log: str = ""
    trace_store: str = ""
    artifact_store: str = ""
    retention_policy: dict[str, Any] = field(default_factory=dict)
    migration_policy: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        *,
        driver_id: str,
        event_log: str = "",
        trace_store: str = "",
        artifact_store: str = "",
        retention_policy: dict[str, Any] | None = None,
        migration_policy: dict[str, Any] | None = None,
    ) -> None:
        object.__setattr__(self, "driver_id", driver_id)
        object.__setattr__(self, "driver_kind", "storage")
        object.__setattr__(self, "version", "0.1.0")
        object.__setattr__(self, "permissions", [])
        object.__setattr__(self, "safety_metadata", {})
        object.__setattr__(self, "event_log", event_log)
        object.__setattr__(self, "trace_store", trace_store)
        object.__setattr__(self, "artifact_store", artifact_store)
        object.__setattr__(self, "retention_policy", dict(retention_policy or {}))
        object.__setattr__(self, "migration_policy", dict(migration_policy or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            **super().to_dict(),
            "event_log": self.event_log,
            "trace_store": self.trace_store,
            "artifact_store": self.artifact_store,
            "retention_policy": dict(self.retention_policy),
            "migration_policy": dict(self.migration_policy),
        }


@dataclass(frozen=True)
class SecretStoreDriverDescriptor(DriverDescriptor):
    backend: str = ""
    auth_method: str = ""
    rotation_policy: dict[str, Any] = field(default_factory=dict)
    audit_policy: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        *,
        driver_id: str,
        backend: str,
        auth_method: str,
        rotation_policy: dict[str, Any] | None = None,
        audit_policy: dict[str, Any] | None = None,
    ) -> None:
        object.__setattr__(self, "driver_id", driver_id)
        object.__setattr__(self, "driver_kind", "secret_store")
        object.__setattr__(self, "version", "0.1.0")
        object.__setattr__(self, "permissions", [])
        object.__setattr__(self, "safety_metadata", {})
        object.__setattr__(self, "backend", backend)
        object.__setattr__(self, "auth_method", auth_method)
        object.__setattr__(self, "rotation_policy", dict(rotation_policy or {}))
        object.__setattr__(self, "audit_policy", dict(audit_policy or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            **super().to_dict(),
            "backend": self.backend,
            "auth_method": self.auth_method,
            "rotation_policy": dict(self.rotation_policy),
            "audit_policy": dict(self.audit_policy),
        }
