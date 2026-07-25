from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
import unicodedata

from pheroos._scope import (
    RUNTIME_SCOPE_COMPONENT_MAX_LENGTH,
    RUNTIME_SCOPE_SCHEMA_V1_ID,
    RUNTIME_SCOPE_VERSION,
    runtime_scope_ref,
)
from pheroos._unicode import contains_surrogate_code_point


_RUNTIME_SCOPE_FIELDS = frozenset(
    {"scope_version", "tenant_id", "run_id", "request_id", "scope_ref"}
)


def _portable_component(value: object, *, name: str) -> str:
    if type(value) is not str:
        raise ValueError(f"runtime scope {name} must be a string")
    if not value or value != value.strip():
        raise ValueError(
            f"runtime scope {name} must be nonblank and have no outer whitespace"
        )
    if "\x00" in value:
        raise ValueError(f"runtime scope {name} must not contain NUL")
    if contains_surrogate_code_point(value):
        raise ValueError(
            f"runtime scope {name} must contain only Unicode scalar values"
        )
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError(f"runtime scope {name} must already use Unicode NFC")
    if len(value) > RUNTIME_SCOPE_COMPONENT_MAX_LENGTH:
        raise ValueError(f"runtime scope {name} exceeds the portable length bound")
    return value


@dataclass(frozen=True)
class RuntimeScope:
    tenant_id: str
    run_id: str
    request_id: str
    scope_ref: str = ""

    def __post_init__(self) -> None:
        for name in ("tenant_id", "run_id", "request_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"runtime scope {name} must be a nonblank string")
        expected = runtime_scope_ref(self.tenant_id, self.run_id)
        if self.scope_ref and self.scope_ref != expected:
            raise ValueError(
                "runtime scope scope_ref does not match tenant_id and run_id"
            )
        object.__setattr__(self, "scope_ref", expected)

    def to_dict(self) -> dict[str, str]:
        """Return the exact portable v1 wire document for this scope."""

        tenant_id = _portable_component(self.tenant_id, name="tenant_id")
        run_id = _portable_component(self.run_id, name="run_id")
        request_id = _portable_component(self.request_id, name="request_id")
        expected = runtime_scope_ref(tenant_id, run_id)
        if self.scope_ref != expected:
            raise ValueError(
                "runtime scope scope_ref does not match tenant_id and run_id"
            )
        return {
            "scope_version": RUNTIME_SCOPE_VERSION,
            "tenant_id": tenant_id,
            "run_id": run_id,
            "request_id": request_id,
            "scope_ref": expected,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RuntimeScope:
        """Read one closed, version-selected portable v1 scope document."""

        if not isinstance(payload, Mapping):
            raise ValueError("runtime scope payload must be a mapping")
        document = dict(payload)
        keys = frozenset(document)
        if keys != _RUNTIME_SCOPE_FIELDS:
            missing = sorted(_RUNTIME_SCOPE_FIELDS - keys)
            unknown = sorted(keys - _RUNTIME_SCOPE_FIELDS, key=str)
            if missing:
                raise ValueError(
                    f"runtime scope payload is missing fields: {', '.join(missing)}"
                )
            raise ValueError(
                "runtime scope payload has unknown fields: "
                + ", ".join(str(item) for item in unknown)
            )
        if document["scope_version"] != RUNTIME_SCOPE_VERSION:
            raise ValueError("runtime scope version is unsupported")
        tenant_id = _portable_component(document["tenant_id"], name="tenant_id")
        run_id = _portable_component(document["run_id"], name="run_id")
        request_id = _portable_component(document["request_id"], name="request_id")
        scope_ref = document["scope_ref"]
        if type(scope_ref) is not str:
            raise ValueError("runtime scope scope_ref must be a string")
        expected = runtime_scope_ref(tenant_id, run_id)
        if scope_ref != expected:
            raise ValueError(
                "runtime scope scope_ref does not match tenant_id and run_id"
            )
        return cls(
            tenant_id=tenant_id,
            run_id=run_id,
            request_id=request_id,
            scope_ref=scope_ref,
        )


__all__ = [
    "RUNTIME_SCOPE_SCHEMA_V1_ID",
    "RUNTIME_SCOPE_VERSION",
    "RuntimeScope",
    "runtime_scope_ref",
]
