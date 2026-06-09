from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pheroos.drivers.base import DriverDescriptor


@dataclass(frozen=True)
class DataProviderDriverDescriptor(DriverDescriptor):
    provider_id: str = ""
    dataset_kind: str = "generic"
    coverage: dict[str, Any] = field(default_factory=dict)
    freshness: dict[str, Any] = field(default_factory=dict)
    license: dict[str, Any] = field(default_factory=dict)
    entitlement_requirements: list[str] = field(default_factory=list)
    normalized_result_schema: str = "open-multi-agent.data_source_result.v0.1"

    def __init__(
        self,
        *,
        provider_id: str,
        dataset_kind: str,
        coverage: dict[str, Any] | None = None,
        freshness: dict[str, Any] | None = None,
        license: dict[str, Any] | None = None,
        entitlement_requirements: list[str] | None = None,
        normalized_result_schema: str = "open-multi-agent.data_source_result.v0.1",
        permissions: list[str] | None = None,
    ) -> None:
        object.__setattr__(self, "driver_id", provider_id)
        object.__setattr__(self, "driver_kind", "data_provider")
        object.__setattr__(self, "version", "0.1.0")
        object.__setattr__(self, "permissions", list(permissions or []))
        object.__setattr__(self, "safety_metadata", {})
        object.__setattr__(self, "provider_id", provider_id)
        object.__setattr__(self, "dataset_kind", dataset_kind)
        object.__setattr__(self, "coverage", dict(coverage or {}))
        object.__setattr__(self, "freshness", dict(freshness or {}))
        object.__setattr__(self, "license", dict(license or {}))
        object.__setattr__(self, "entitlement_requirements", list(entitlement_requirements or []))
        object.__setattr__(self, "normalized_result_schema", normalized_result_schema)

    def to_dict(self) -> dict[str, Any]:
        return {
            **super().to_dict(),
            "provider_id": self.provider_id,
            "dataset_kind": self.dataset_kind,
            "coverage": dict(self.coverage),
            "freshness": dict(self.freshness),
            "license": dict(self.license),
            "entitlement_requirements": list(self.entitlement_requirements),
            "normalized_result_schema": self.normalized_result_schema,
        }
