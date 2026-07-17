from __future__ import annotations

from hashlib import sha256
import json


RUNTIME_SCOPE_VERSION = "pheroos-runtime-scope-v1"


def runtime_scope_ref(tenant_id: str, run_id: str) -> str:
    """Return the opaque deterministic identity for one tenant/run scope."""

    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("runtime scope tenant_id must be a nonblank string")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("runtime scope run_id must be a nonblank string")
    canonical = json.dumps(
        {
            "run_id": run_id,
            "tenant_id": tenant_id,
            "version": RUNTIME_SCOPE_VERSION,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


__all__ = ["RUNTIME_SCOPE_VERSION", "runtime_scope_ref"]
