from __future__ import annotations

import math
import re
from typing import Any


def validate_json_schema(
    value: Any, schema: dict[str, Any], *, path: str = "$"
) -> list[str]:
    errors: list[str] = []
    one_of_error = _validate_one_of(value, schema, path=path)
    if one_of_error is not None:
        return [one_of_error]
    errors.extend(_validate_all_of(value, schema, path=path))

    expected_type = schema.get("type")
    if expected_type is not None and not type_matches(value, str(expected_type)):
        return [f"{path}: expected {expected_type}"]
    if schema.get("x-pheroos-exact-integer") is True and type(value) is not int:
        return [f"{path}: must be an integer without numeric coercion"]

    if "enum" in schema and value not in schema["enum"]:
        allowed = ", ".join(str(item) for item in schema["enum"])
        errors.append(f"{path}: expected one of {allowed}")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']}")

    errors.extend(_validate_value_shape(value, schema, path=path))
    return errors


def _validate_one_of(value: Any, schema: dict[str, Any], *, path: str) -> str | None:
    one_of = schema.get("oneOf")
    if not isinstance(one_of, list):
        return None
    matches = [
        candidate
        for candidate in one_of
        if isinstance(candidate, dict)
        and not validate_json_schema(value, candidate, path=path)
    ]
    if len(matches) != 1:
        return f"{path}: expected exactly one declared schema shape"
    return None


def _validate_all_of(value: Any, schema: dict[str, Any], *, path: str) -> list[str]:
    all_of = schema.get("allOf")
    if not isinstance(all_of, list):
        return []
    errors: list[str] = []
    for candidate in all_of:
        if isinstance(candidate, dict):
            errors.extend(validate_json_schema(value, candidate, path=path))
    return errors


def _validate_value_shape(
    value: Any, schema: dict[str, Any], *, path: str
) -> list[str]:
    if isinstance(value, dict):
        return validate_object(value, schema, path=path)
    if isinstance(value, list):
        return validate_array(value, schema, path=path)
    if isinstance(value, str):
        return validate_string(value, schema, path=path)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return validate_number(value, schema, path=path)
    return []


def validate_object(
    value: dict[str, Any], schema: dict[str, Any], *, path: str
) -> list[str]:
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
            errors.extend(
                validate_json_schema(item, properties[key_text], path=item_path)
            )
        matching_schemas = matching_pattern_schemas(key_text, pattern_properties)
        for pattern_schema in matching_schemas:
            errors.extend(validate_json_schema(item, pattern_schema, path=item_path))
        if key_text in properties or matching_schemas:
            continue
        if isinstance(additional_properties, dict):
            errors.extend(
                validate_json_schema(item, additional_properties, path=item_path)
            )
        elif additional_properties is False:
            errors.append(f"{item_path}: unknown field")
    return errors


def validate_array(value: list[Any], schema: dict[str, Any], *, path: str) -> list[str]:
    errors: list[str] = []
    if "minItems" in schema and len(value) < schema["minItems"]:
        errors.append(f"{path}: must contain at least {schema['minItems']} items")
    if "maxItems" in schema and len(value) > schema["maxItems"]:
        errors.append(f"{path}: must contain at most {schema['maxItems']} items")
    errors.extend(_validate_array_uniqueness(value, schema, path=path))
    errors.extend(_validate_array_contains(value, schema, path=path))
    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
        for index, item in enumerate(value):
            errors.extend(
                validate_json_schema(item, item_schema, path=f"{path}[{index}]")
            )
    return errors


def _validate_array_uniqueness(
    value: list[Any], schema: dict[str, Any], *, path: str
) -> list[str]:
    errors: list[str] = []
    if schema.get("uniqueItems") is True:
        for index, item in enumerate(value):
            if any(item == previous for previous in value[:index]):
                errors.append(f"{path}[{index}]: duplicate array item")
    return errors


def _validate_array_contains(
    value: list[Any], schema: dict[str, Any], *, path: str
) -> list[str]:
    contains = schema.get("contains")
    if not isinstance(contains, dict):
        return []
    matches = sum(
        not validate_json_schema(item, contains, path=f"{path}[{index}]")
        for index, item in enumerate(value)
    )
    minimum = schema.get("minContains", 1)
    maximum = schema.get("maxContains")
    if matches < minimum:
        expected = (
            f" matching constant {contains['const']}" if "const" in contains else ""
        )
        return [f"{path}: must contain at least {minimum} item(s){expected}"]
    if isinstance(maximum, int) and matches > maximum:
        return [f"{path}: must contain at most {maximum} matching items"]
    return []


def validate_string(value: str, schema: dict[str, Any], *, path: str) -> list[str]:
    errors: list[str] = []
    if "minLength" in schema and len(value) < schema["minLength"]:
        errors.append(f"{path}: must contain at least {schema['minLength']} characters")
    if "maxLength" in schema and len(value) > schema["maxLength"]:
        errors.append(f"{path}: must contain at most {schema['maxLength']} characters")
    pattern = schema.get("pattern")
    if isinstance(pattern, str) and re.search(pattern, value) is None:
        errors.append(f"{path}: does not match required pattern")
    return errors


def validate_number(
    value: int | float, schema: dict[str, Any], *, path: str
) -> list[str]:
    errors: list[str] = []
    if not math.isfinite(value):
        return [f"{path}: must be finite"]
    if "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: must be >= {schema['minimum']}")
    if "maximum" in schema and value > schema["maximum"]:
        errors.append(f"{path}: must be <= {schema['maximum']}")
    return errors


def matching_pattern_schemas(
    key: str, pattern_properties: dict[str, Any]
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for pattern, schema in pattern_properties.items():
        if re.match(pattern, key):
            matches.append(schema if isinstance(schema, dict) else {})
    return matches


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
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and float(value).is_integer()
        )
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True
