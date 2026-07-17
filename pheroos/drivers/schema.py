from __future__ import annotations

from typing import Any

from pheroos.drivers._versions import (
    DRIVER_DESCRIPTOR_VERSION_V2,
    DRIVER_SCHEMA_V1_ID,
    DRIVER_SCHEMA_V2_ID,
)


EXTENSION_KEY_PATTERN = r"^(x-|ext\.).+"


def driver_schema() -> dict[str, Any]:
    """Return the frozen legacy-v1 Driver descriptor schema.

    The unversioned ID is a compatibility artifact.  New validation semantics
    belong in :func:`driver_schema_v2`, never in this document.
    """

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": DRIVER_SCHEMA_V1_ID,
        "type": "object",
        "required": ["id", "kind", "version"],
        "patternProperties": {EXTENSION_KEY_PATTERN: {}},
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "kind": {"type": "string"},
            "version": {"type": "string"},
            "capabilities": {"type": "array", "items": {"type": "string"}},
            "permissions": {"type": "array", "items": {"type": "string"}},
            "config_ref": {"type": "string"},
            "extensions": {"type": "object"},
        },
    }


def driver_schema_v2() -> dict[str, Any]:
    """Return the strict, discriminator-backed Driver descriptor v2 schema."""

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": DRIVER_SCHEMA_V2_ID,
        "type": "object",
        "required": ["descriptor_version", "id", "kind", "version"],
        "patternProperties": {EXTENSION_KEY_PATTERN: {}},
        "additionalProperties": False,
        "properties": {
            "descriptor_version": {"const": DRIVER_DESCRIPTOR_VERSION_V2},
            "id": {"type": "string", "minLength": 1},
            "kind": {"type": "string", "minLength": 1},
            # Provider version and descriptor ABI version are intentionally
            # separate axes.
            "version": {"type": "string", "minLength": 1},
            "capabilities": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "uniqueItems": True,
            },
            "permissions": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "uniqueItems": True,
            },
            "config_ref": {"type": "string"},
            "extensions": {"type": "object"},
        },
    }


__all__ = ["driver_schema", "driver_schema_v2"]
