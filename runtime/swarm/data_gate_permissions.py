from __future__ import annotations

from typing import Any

from runtime.swarm.legacy_data_gate_permissions import (
    legacy_publication_conclusion_target,
    legacy_top_level_conclusion_permission_keys,
)
from runtime.swarm.target_registry import canonical_target


def data_gate_conclusion_permission(gate: dict[str, Any], target: str) -> bool | None:
    permissions = gate.get("conclusion_permissions") if isinstance(gate.get("conclusion_permissions"), dict) else {}
    for key in conclusion_permission_keys(target):
        value = permissions.get(key)
        if isinstance(value, dict) and "allowed" in value:
            return bool(value.get("allowed"))
        if isinstance(value, bool):
            return value
        if key in gate and isinstance(gate.get(key), bool):
            return bool(gate.get(key))
    return None


def conclusion_permission_keys(target: str) -> list[str]:
    canonical = canonical_target(target)
    tail = canonical.split(":", 1)[1] if ":" in canonical else canonical
    normalized = tail.replace("-", "_")
    return dedupe_strings([canonical, normalized, f"{normalized}_allowed"])


def declared_conclusion_permissions(gate: dict[str, Any]) -> list[dict[str, Any]]:
    permissions = gate.get("conclusion_permissions") if isinstance(gate.get("conclusion_permissions"), dict) else {}
    output = []
    for key, value in sorted(permissions.items()):
        if not permission_value_declared(value):
            continue
        target = permission_target(key, value)
        output.append(
            {
                "target": target,
                "canonical_target": canonical_target(target),
                "allowed": permission_allowed(value),
                "label": permission_label(target, value),
            }
        )
    return output


def effective_conclusion_permissions(gate: dict[str, Any]) -> list[dict[str, Any]]:
    output = declared_conclusion_permissions(gate)
    existing_targets = {item["canonical_target"] for item in output}
    for target, key in legacy_top_level_conclusion_permission_keys().items():
        allowed = gate.get(key)
        canonical = canonical_target(target)
        if allowed is None or canonical in existing_targets:
            continue
        output.append(
            {
                "target": target,
                "canonical_target": canonical,
                "allowed": bool(allowed),
                "label": permission_label(target, allowed),
            }
        )
        existing_targets.add(canonical)
    return output


def blocked_conclusion_permissions(gate: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in effective_conclusion_permissions(gate) if item.get("allowed") is False]


def publication_conclusion_permission_target(gate: dict[str, Any]) -> str:
    for permission in declared_conclusion_permissions(gate):
        target = str(permission.get("canonical_target") or permission.get("target") or "")
        if is_publication_target(target):
            return canonical_target(target)
    for permission in effective_conclusion_permissions(gate):
        target = str(permission.get("canonical_target") or permission.get("target") or "")
        if is_publication_target(target):
            return canonical_target(target)
    return legacy_publication_conclusion_target()


def permission_value_declared(value: Any) -> bool:
    return isinstance(value, bool) or (isinstance(value, dict) and "allowed" in value)


def permission_allowed(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value.get("allowed"))
    return bool(value) if value is not None else False


def permission_target(key: str, value: Any) -> str:
    if isinstance(value, dict) and value.get("target"):
        return str(value.get("target"))
    text = str(key or "").strip()
    if ":" in text:
        return text
    if text.endswith("_allowed"):
        text = text[: -len("_allowed")]
    return f"decision:{text}"


def permission_label(target: str, value: Any) -> str:
    if isinstance(value, dict) and value.get("label"):
        return str(value.get("label"))
    tail = canonical_target(target).split(":", 1)[-1]
    return " ".join(tail.replace("-", "_").split("_"))


def is_publication_target(target: str) -> bool:
    tail = canonical_target(target).split(":", 1)[-1].replace("-", "_")
    return (
        tail in {"publish", "publication"}
        or tail.endswith("_publish")
        or tail.startswith("publish_")
        or tail.endswith("_publication")
    )


def writer_action_for_conclusion_target(target: str) -> str:
    tail = canonical_target(target).split(":", 1)[-1].replace("-", "_")
    return f"writer:{tail}"


def dedupe_strings(values: list[str]) -> list[str]:
    output = []
    seen = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
