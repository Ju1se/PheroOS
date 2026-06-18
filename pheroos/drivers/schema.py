from __future__ import annotations

from typing import Any


def driver_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://pheroos.dev/schemas/driver.schema.json",
        "type": "object",
        "required": ["id", "kind", "version"],
        "properties": {
            "id": {"type": "string"},
            "kind": {"type": "string"},
            "version": {"type": "string"},
            "capabilities": {"type": "array", "items": {"type": "string"}},
        },
    }
