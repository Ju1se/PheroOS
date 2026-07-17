from __future__ import annotations

from typing import Any

from pheroos.kernel._versions import (
    KERNEL_PLAN_VERSION_V2,
    KERNEL_SCHEMA_V1_ID,
    KERNEL_SCHEMA_V2_ID,
)


def object_schema(properties: dict[str, Any], *, required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": required,
        "additionalProperties": False,
        "properties": properties,
    }


def string_array_schema() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


def _kernel_v2_shape() -> dict[str, Any]:
    return object_schema(
        {
            "tenant_id": {"type": "string"},
            "request_id": {"type": "string"},
            "run_id": {"type": "string"},
            "scope_ref": {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
            },
            "capability_resolutions": {
                "type": "array",
                "items": object_schema(
                    {
                        "capability_id": {"type": "string"},
                        "available": {"type": "boolean"},
                        "reason": {"type": "string"},
                    },
                    required=["capability_id", "available"],
                ),
            },
            "permission_grants": {
                "type": "array",
                "items": object_schema(
                    {
                        "capability_id": {"type": "string"},
                        "permission": {"type": "string"},
                        "granted": {"type": "boolean"},
                        "reason": {"type": "string"},
                    },
                    required=["capability_id", "permission"],
                ),
            },
            "connection_requirements": {
                "type": "array",
                "items": object_schema(
                    {
                        "capability_id": {"type": "string"},
                        "connection": {"type": "string"},
                        "required": {"type": "boolean"},
                    },
                    required=["capability_id", "connection"],
                ),
            },
            "connection_readiness": {
                "type": "array",
                "items": object_schema(
                    {
                        "connection": {"type": "string", "minLength": 1},
                        "available": {"type": "boolean"},
                        "detail": {"type": "string"},
                    },
                    required=["connection", "available"],
                ),
            },
            "driver_probe_snapshots": {
                "type": "array",
                "items": object_schema(
                    {
                        "driver_id": {"type": "string", "minLength": 1},
                        "available": {"type": "boolean"},
                        "detail": {"type": "string"},
                        "version": {"type": "string", "minLength": 1},
                        "capabilities": string_array_schema(),
                    },
                    required=["driver_id", "available", "version", "capabilities"],
                ),
            },
            "driver_exposures": {
                "type": "array",
                "items": object_schema(
                    {
                        "driver_id": {"type": "string"},
                        "capability_id": {"type": "string"},
                        "permissions": string_array_schema(),
                        "capabilities": string_array_schema(),
                    },
                    required=["driver_id", "capability_id"],
                ),
            },
            "tool_exposures": {
                "type": "array",
                "items": object_schema(
                    {
                        "tool_id": {"type": "string"},
                        "capability_id": {"type": "string"},
                        "permissions": string_array_schema(),
                    },
                    required=["tool_id", "capability_id"],
                ),
            },
            "diagnostics": {
                "type": "array",
                "items": object_schema(
                    {
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "severity": {"type": "string"},
                    },
                    required=["code", "message"],
                ),
            },
            "runtime_ready": {"type": "boolean"},
            "degraded": {"type": "boolean"},
        },
        required=[
            "tenant_id",
            "request_id",
            "run_id",
            "scope_ref",
            "capability_resolutions",
            "permission_grants",
            "connection_requirements",
            "connection_readiness",
            "driver_probe_snapshots",
            "driver_exposures",
            "tool_exposures",
            "diagnostics",
            "runtime_ready",
            "degraded",
        ],
    ) | {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": KERNEL_SCHEMA_V1_ID,
    }


def kernel_schema() -> dict[str, Any]:
    """Return the frozen legacy-v1 OSPlan schema."""

    schema = _kernel_v2_shape()
    properties = schema["properties"]
    for name in (
        "run_id",
        "scope_ref",
        "connection_readiness",
        "driver_probe_snapshots",
    ):
        properties.pop(name)
        schema["required"].remove(name)
    properties["driver_exposures"]["items"]["properties"].pop("capabilities")
    return schema


def kernel_schema_v2() -> dict[str, Any]:
    """Return the scope- and readiness-bound Kernel plan v2 schema."""

    schema = _kernel_v2_shape()
    schema["$id"] = KERNEL_SCHEMA_V2_ID
    schema["properties"]["plan_version"] = {"const": KERNEL_PLAN_VERSION_V2}
    schema["required"].insert(0, "plan_version")
    return schema


__all__ = ["kernel_schema", "kernel_schema_v2"]
