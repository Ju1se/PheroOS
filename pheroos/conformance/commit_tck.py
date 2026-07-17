from __future__ import annotations

"""Stable public facade for the Commit Integrity v1 TCK.

The implementation is split by responsibility under ``_commit_tck``.  This
module intentionally contains no reference semantics or mutable registries;
it preserves the original import path and canonical public object ownership.
"""

from importlib import resources

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
from pheroos.conformance._commit_tck.reference_adapter import (
    ReferenceCommitTckAdapter,
)
from pheroos.conformance._commit_tck.runner import run_commit_tck


# Constants remain direct facade declarations because their canonical owner is
# part of the frozen public shape.  Private engines use equivalent private
# constants without changing the public binding owner.
COMMIT_TCK_VERSION = "pheroos-commit-integrity-tck-v1"
COMMIT_TCK_ARTIFACT = resources.files("pheroos.conformance").joinpath(
    "tck",
    "commit-integrity-v1.json",
)
COMMIT_TCK_SCHEMA_ID = "https://pheroos.dev/schemas/commit-tck.schema.json"


# These are type-identical aliases, not wrappers.  Preserve the canonical
# owner used by signatures, repr/pickle, ABI inventory, and existing clients.
_CANONICAL_MODULE = __name__
for _public_object in (
    CommitTckAdapter,
    CommitTckReport,
    CommitTckResult,
    CommitTckVector,
    ReferenceCommitTckAdapter,
    commit_tck_artifact_root,
    commit_tck_schema,
    load_commit_tck_vectors,
    run_commit_tck,
    _request_from_vector,
    _variant_vector,
):
    _public_object.__module__ = _CANONICAL_MODULE
del _public_object


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
