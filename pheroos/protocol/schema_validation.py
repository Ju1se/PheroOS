from __future__ import annotations

import re
from typing import Any


def validate_json_schema(value: Any, schema: dict[str, Any], *, path: str = "$") -> list[str]:
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type is not None and not type_matches(value, str(expected_type)):
        return [f"{path}: expected {expected_type}"]

    if "enum" in schema and value not in schema["enum"]:
        allowed = ", ".join(str(item) for item in schema["enum"])
        errors.append(f"{path}: expected one of {allowed}")

    if isinstance(value, dict):
        errors.extend(validate_object(value, schema, path=path))
    elif isinstance(value, list):
        errors.extend(validate_array(value, schema, path=path))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        errors.extend(validate_number(value, schema, path=path))
    return errors


def validate_object(value: dict[str, Any], schema: dict[str, Any], *, path: str) -> list[str]:
    errors: list[str] = []
    properties = schema.get("properties") or {}
    required = schema.get("required") or []
    pattern_properties = schema.get("patternProperties") or {}
    additional_properties = schema.get("additionalProperties", True)

    for required_key in required:
        if required_key not in value:
            errors.append(f"{path}.{required_key}: missing required field")

    for key, item in value.items():
        key_text = str(key)
        item_path = f"{path}.{key_text}"
        if key_text in properties:
            errors.extend(validate_json_schema(item, properties[key_text], path=item_path))
            continue
        pattern_schema = matching_pattern_schema(key_text, pattern_properties)
        if pattern_schema is not None:
            errors.extend(validate_json_schema(item, pattern_schema, path=item_path))
            continue
        if additional_properties is False:
            errors.append(f"{item_path}: unknown field")
    return errors


def validate_array(value: list[Any], schema: dict[str, Any], *, path: str) -> list[str]:
    item_schema = schema.get("items")
    if not isinstance(item_schema, dict):
        return []
    errors: list[str] = []
    for index, item in enumerate(value):
        errors.extend(validate_json_schema(item, item_schema, path=f"{path}[{index}]"))
    return errors


def validate_number(value: int | float, schema: dict[str, Any], *, path: str) -> list[str]:
    errors: list[str] = []
    if "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: must be >= {schema['minimum']}")
    if "maximum" in schema and value > schema["maximum"]:
        errors.append(f"{path}: must be <= {schema['maximum']}")
    return errors


def matching_pattern_schema(key: str, pattern_properties: dict[str, Any]) -> dict[str, Any] | None:
    for pattern, schema in pattern_properties.items():
        if re.match(pattern, key):
            return schema if isinstance(schema, dict) else {}
    return None


def type_matches(value: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True
