from __future__ import annotations

from typing import Any


def kernel_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://pheroos.dev/schemas/kernel.schema.json",
        "type": "object",
        "required": ["tenant_id", "request_id", "runtime_ready"],
        "additionalProperties": False,
        "properties": {
            "tenant_id": {"type": "string"},
            "request_id": {"type": "string"},
            "runtime_ready": {"type": "boolean"},
            "degraded": {"type": "boolean"},
        },
    }
