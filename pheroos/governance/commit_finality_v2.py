"""Draft public authority-neutral Commit Finality v2 ABI.

This module owns the stable public identity of finality projections and opaque
verified inputs shared by Decision, Certificate, and Distributed Commit v2.
It does not issue authority; owner-specific Store adapters issue handles only
after their own current-state verification.
"""

from pheroos.governance._commit_finality_v2 import (
    COMMIT_FINALITY_INPUT_SCHEMA_V2,
    COMMIT_FINALITY_PROJECTION_SCHEMA_V2,
    CommitFinalityOwnerV2,
    CommitFinalityProjectionV2,
    CommitFinalityStatusV2,
    VerifiedCommitFinalityInputV2,
    commit_finality_owner_genesis_snapshot_root_v2,
    commit_finality_owner_stream_ref_v2,
)


_PUBLIC_MODULE = __name__
_PUBLIC_OBJECTS = (
    CommitFinalityOwnerV2,
    CommitFinalityProjectionV2,
    CommitFinalityStatusV2,
    VerifiedCommitFinalityInputV2,
    commit_finality_owner_genesis_snapshot_root_v2,
    commit_finality_owner_stream_ref_v2,
)
for _item in _PUBLIC_OBJECTS:
    _item.__module__ = _PUBLIC_MODULE
del _item


__all__ = [
    "COMMIT_FINALITY_INPUT_SCHEMA_V2",
    "COMMIT_FINALITY_PROJECTION_SCHEMA_V2",
    "CommitFinalityOwnerV2",
    "CommitFinalityProjectionV2",
    "CommitFinalityStatusV2",
    "VerifiedCommitFinalityInputV2",
    "commit_finality_owner_genesis_snapshot_root_v2",
    "commit_finality_owner_stream_ref_v2",
]
