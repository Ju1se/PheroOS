from __future__ import annotations

import re
from typing import Any


SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|authorization|bearer|password|passwd|token|secret|credential|cookie|set-cookie)",
    re.IGNORECASE,
)
SECRET_VALUE_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9._-]{12,}"),
    re.compile(r"sk-cp-[A-Za-z0-9._-]{12,}"),
    re.compile(r"[A-Fa-f0-9]{32}\.[A-Za-z0-9._-]{8,}"),
]


def redact_secret_text(value: Any, *, limit: int | None = None) -> str:
    text = str(value or "")
    for pattern in SECRET_VALUE_PATTERNS:
        text = pattern.sub("[redacted]", text)
    text = SENSITIVE_KEY_RE.sub("[redacted]", text)
    if limit is not None and len(text) > limit:
        return text[:limit] + "..."
    return text


def redact_sensitive(value: Any, *, max_string_length: int | None = None) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if SENSITIVE_KEY_RE.search(key_text):
                clean[key] = "[redacted]"
            else:
                clean[key] = redact_sensitive(item, max_string_length=max_string_length)
        return clean
    if isinstance(value, list):
        return [redact_sensitive(item, max_string_length=max_string_length) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item, max_string_length=max_string_length) for item in value)
    if isinstance(value, str):
        return redact_secret_text(value, limit=max_string_length)
    return value
