from __future__ import annotations

from pheroos.governance.errors import GovernanceError


def is_nonblank_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def require_nonblank_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GovernanceError(f"{field_name} must be a non-blank string")
    return value
