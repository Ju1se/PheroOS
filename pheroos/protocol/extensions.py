from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any


EXTENSION_PREFIXES = ("x-", "ext.")
SECRET_KEY_PARTS = frozenset(
    {
        "api_key",
        "apikey",
        "access_key",
        "private_key",
        "secret",
        "token",
        "password",
        "credential",
        "credentials",
    }
)


def is_namespaced_extension(value: str) -> bool:
    return any(value.startswith(prefix) and len(value) > len(prefix) for prefix in EXTENSION_PREFIXES)


def collect_extensions(payload: dict[str, Any]) -> dict[str, Any]:
    extensions: dict[str, Any] = {}
    explicit = payload.get("extensions")
    if isinstance(explicit, dict):
        extensions.update(explicit)
    for key, value in payload.items():
        if is_namespaced_extension(str(key)):
            extensions[str(key)] = value
    return extensions


def is_secret_like_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_").replace(".", "_")
    return any(part in normalized for part in SECRET_KEY_PARTS)


def secret_like_paths(value: Any, *, path: str = "") -> list[str]:
    paths: list[str] = []
    if is_dataclass(value):
        for item in fields(value):
            item_path = dotted(path, item.name)
            paths.extend(secret_like_paths(getattr(value, item.name), path=item_path))
        return paths
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            item_path = dotted(path, key_text)
            if is_secret_like_key(key_text):
                paths.append(item_path)
            paths.extend(secret_like_paths(item, path=item_path))
        return paths
    if isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(secret_like_paths(item, path=f"{path}[{index}]" if path else f"[{index}]"))
    return paths


def reject_secret_like_fields(payload: dict[str, Any]) -> None:
    paths = secret_like_paths(payload)
    if paths:
        raise ValueError(f"secret-like manifest fields are not allowed: {', '.join(paths)}")


def dotted(prefix: str, item: str) -> str:
    return f"{prefix}.{item}" if prefix else item
