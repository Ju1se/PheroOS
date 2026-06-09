from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DATA_PROVIDER_DESCRIPTOR_SCHEMA = "open-multi-agent.data_provider_descriptor.v0.1"
DATA_SOURCE_RESULT_SCHEMA = "open-multi-agent.data_source_result.v0.1"


@dataclass(frozen=True)
class DataProviderDescriptor:
    """Protocol-visible declaration for a capability-owned data provider."""

    provider_id: str
    capability_id: str
    source_kind: str = "data_provider"
    dataset_kind: str = "generic"
    normalized_result_schema: str = DATA_SOURCE_RESULT_SCHEMA
    coverage: dict[str, Any] = field(default_factory=dict)
    freshness: dict[str, Any] = field(default_factory=dict)
    license: dict[str, Any] = field(default_factory=dict)
    reliability_level: str = "declared_by_capability"
    adapter_entrypoint: str | None = None
    required_connections: list[str] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    data_packages: list[str] = field(default_factory=list)
    provenance_policy: dict[str, Any] = field(default_factory=dict)
    adapter_metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_capability_source(
        cls,
        capability: dict[str, Any],
        source: dict[str, Any],
    ) -> "DataProviderDescriptor":
        capability_id = str(capability.get("id") or "").strip()
        connections = string_list(source.get("required_connections")) or string_list(
            capability.get("required_connections")
        ) or string_list(capability.get("connections"))
        tools = string_list(source.get("tools")) or string_list(capability.get("tools"))
        packages = string_list(source.get("data_packages")) or string_list(capability.get("data_packages"))
        provider_id = (
            str(source.get("provider_id") or source.get("id") or "").strip()
            or (connections[0] if connections else capability_id)
        )
        return cls(
            provider_id=provider_id,
            capability_id=capability_id,
            source_kind=str(source.get("source_kind") or "data_provider"),
            dataset_kind=str(source.get("dataset_kind") or source.get("dataset_type") or "generic"),
            normalized_result_schema=str(source.get("normalized_result_schema") or DATA_SOURCE_RESULT_SCHEMA),
            coverage=dict_value(source.get("coverage")),
            freshness=dict_value(source.get("freshness")),
            license=dict_value(source.get("license")),
            reliability_level=str(source.get("reliability_level") or "declared_by_capability"),
            adapter_entrypoint=optional_string(source.get("adapter_entrypoint")),
            required_connections=connections,
            required_permissions=string_list(source.get("required_permissions")) or string_list(capability.get("permissions")),
            tools=tools,
            data_packages=packages,
            provenance_policy=dict_value(source.get("provenance_policy")),
            adapter_metadata=dict_value(source.get("adapter_metadata")),
        )

    @classmethod
    def from_legacy_capability(cls, capability: dict[str, Any]) -> "DataProviderDescriptor":
        capability_id = str(capability.get("id") or "").strip()
        connections = string_list(capability.get("required_connections")) or string_list(capability.get("connections"))
        packages = string_list(capability.get("data_packages"))
        provider_id = connections[0] if connections else capability_id
        return cls(
            provider_id=provider_id,
            capability_id=capability_id,
            source_kind="capability_declared_source",
            dataset_kind="declared_data_packages" if packages else "generic",
            required_connections=connections,
            required_permissions=string_list(capability.get("permissions")),
            tools=string_list(capability.get("tools")),
            data_packages=packages,
            adapter_metadata={"source": "legacy_capability_fields"},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DATA_PROVIDER_DESCRIPTOR_SCHEMA,
            "provider_id": self.provider_id,
            "capability_id": self.capability_id,
            "source_kind": self.source_kind,
            "dataset_kind": self.dataset_kind,
            "normalized_result_schema": self.normalized_result_schema,
            "coverage": dict(self.coverage),
            "freshness": dict(self.freshness),
            "license": dict(self.license),
            "reliability_level": self.reliability_level,
            "adapter_entrypoint": self.adapter_entrypoint,
            "required_connections": list(self.required_connections),
            "required_permissions": list(self.required_permissions),
            "tools": list(self.tools),
            "data_packages": list(self.data_packages),
            "provenance_policy": dict(self.provenance_policy),
            "adapter_metadata": dict(self.adapter_metadata),
        }


@dataclass(frozen=True)
class DataSourceResult:
    """Safe, normalized result envelope returned by provider adapters."""

    provider_id: str
    source_kind: str
    dataset_kind: str
    normalized_payload: dict[str, Any]
    provenance: dict[str, Any]
    coverage: dict[str, Any] = field(default_factory=dict)
    freshness: dict[str, Any] = field(default_factory=dict)
    license: dict[str, Any] = field(default_factory=dict)
    adapter_metadata: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return public_safe_data_source_result(
            {
                "schema_version": DATA_SOURCE_RESULT_SCHEMA,
                "provider_id": self.provider_id,
                "source_kind": self.source_kind,
                "dataset_kind": self.dataset_kind,
                "normalized_payload": dict(self.normalized_payload),
                "provenance": dict(self.provenance),
                "coverage": dict(self.coverage),
                "freshness": dict(self.freshness),
                "license": dict(self.license),
                "adapter_metadata": dict(self.adapter_metadata),
                "ok": self.ok,
                "errors": list(self.errors),
            }
        )


def data_provider_descriptors_from_capability(capability: dict[str, Any]) -> list[DataProviderDescriptor]:
    declared = capability.get("data_sources")
    if isinstance(declared, list):
        descriptors = [
            DataProviderDescriptor.from_capability_source(capability, item)
            for item in declared
            if isinstance(item, dict)
        ]
        if descriptors:
            return descriptors
    if capability_declares_legacy_data_source(capability):
        return [DataProviderDescriptor.from_legacy_capability(capability)]
    return []


def capability_declares_legacy_data_source(capability: dict[str, Any]) -> bool:
    return bool(
        string_list(capability.get("data_packages"))
        or string_list(capability.get("required_connections"))
        or string_list(capability.get("connections"))
    )


def public_safe_data_source_results(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        item
        for item in (public_safe_data_source_result(entry) for entry in value)
        if item
    ]


def public_safe_data_source_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    allowed = {
        "schema_version",
        "provider_id",
        "source_kind",
        "dataset_kind",
        "normalized_payload",
        "provenance",
        "coverage",
        "freshness",
        "license",
        "adapter_metadata",
        "ok",
        "errors",
    }
    output = {key: strip_raw_payload_fields(item) for key, item in value.items() if key in allowed}
    output.setdefault("schema_version", DATA_SOURCE_RESULT_SCHEMA)
    return output


def strip_raw_payload_fields(value: Any) -> Any:
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered.startswith("raw_") or lowered in {"rows", "quarterly_rows", "annual_rows"}:
                continue
            output[str(key)] = strip_raw_payload_fields(item)
        return output
    if isinstance(value, list):
        return [strip_raw_payload_fields(item) for item in value[:100]]
    return value


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def optional_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
