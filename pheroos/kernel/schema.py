from __future__ import annotations

from typing import Any


def object_schema(properties: dict[str, Any], *, required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "required": required,
        "additionalProperties": False,
        "properties": properties,
    }


def string_array_schema() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


def kernel_schema() -> dict[str, Any]:
    return object_schema(
        {
            "tenant_id": {"type": "string"},
            "request_id": {"type": "string"},
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
            "driver_exposures": {
                "type": "array",
                "items": object_schema(
                    {
                        "driver_id": {"type": "string"},
                        "capability_id": {"type": "string"},
                        "permissions": string_array_schema(),
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
            "capability_resolutions",
            "permission_grants",
            "connection_requirements",
            "driver_exposures",
            "tool_exposures",
            "diagnostics",
            "runtime_ready",
            "degraded",
        ],
    ) | {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://pheroos.dev/schemas/kernel.schema.json",
    }
