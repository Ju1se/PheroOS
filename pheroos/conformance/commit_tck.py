"""Stable, dependency-light public facade for the Commit Integrity v1 TCK."""

from __future__ import annotations

from importlib import import_module as _import_module, resources
from threading import RLock as _RLock
from typing import TYPE_CHECKING, Any

from pheroos.conformance._commit_tck.artifacts import (
    commit_tck_artifact_root,
    commit_tck_schema,
    load_commit_tck_vectors,
)
from pheroos.conformance._commit_tck.models import (
    CommitTckAdapter,
    CommitTckReport,
    CommitTckResult,
    CommitTckVector,
    request_from_vector as _request_from_vector,
)
from pheroos.conformance._commit_tck.mutations import (
    variant_vector as _variant_vector,
)
from pheroos.conformance._commit_tck.runner import run_commit_tck


if TYPE_CHECKING:
    from pheroos.conformance._commit_tck.reference_adapter import (
        ReferenceCommitTckAdapter as ReferenceCommitTckAdapter,
    )

del TYPE_CHECKING


COMMIT_TCK_VERSION = "pheroos-commit-integrity-tck-v1"
COMMIT_TCK_ARTIFACT = resources.files("pheroos.conformance").joinpath(
    "tck", "commit-integrity-v1.json"
)
COMMIT_TCK_SCHEMA_ID = "https://pheroos.dev/schemas/commit-tck.schema.json"


_CANONICAL_MODULE = __name__
for _public_object in (
    CommitTckAdapter,
    CommitTckReport,
    CommitTckResult,
    CommitTckVector,
    commit_tck_artifact_root,
    commit_tck_schema,
    load_commit_tck_vectors,
    run_commit_tck,
    _request_from_vector,
    _variant_vector,
):
    _public_object.__module__ = _CANONICAL_MODULE
del _public_object


_LAZY_PUBLIC_API = {
    "ReferenceCommitTckAdapter": (
        "pheroos.conformance._commit_tck.reference_adapter",
        "ReferenceCommitTckAdapter",
    )
}
_LAZY_PUBLIC_API_LOCK = _RLock()


def __getattr__(name: str) -> object:
    target = _LAZY_PUBLIC_API.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    with _LAZY_PUBLIC_API_LOCK:
        if name in globals():
            return globals()[name]
        module_name, attribute = target
        value = getattr(_import_module(module_name), attribute)
        setattr(value, "__module__", _CANONICAL_MODULE)
        globals()[name] = value
        return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_PUBLIC_API))


__all__ = [
    "COMMIT_TCK_ARTIFACT",
    "COMMIT_TCK_SCHEMA_ID",
    "COMMIT_TCK_VERSION",
    "CommitTckAdapter",
    "CommitTckReport",
    "CommitTckResult",
    "CommitTckVector",
    "ReferenceCommitTckAdapter",
    "commit_tck_artifact_root",
    "commit_tck_schema",
    "load_commit_tck_vectors",
    "run_commit_tck",
]
