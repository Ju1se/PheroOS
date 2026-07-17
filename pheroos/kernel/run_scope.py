from __future__ import annotations

from dataclasses import dataclass

from pheroos._scope import RUNTIME_SCOPE_VERSION, runtime_scope_ref


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
            raise ValueError("runtime scope scope_ref does not match tenant_id and run_id")
        object.__setattr__(self, "scope_ref", expected)


__all__ = ["RUNTIME_SCOPE_VERSION", "RuntimeScope", "runtime_scope_ref"]
