"""Public Commit Wire schema API.

The immutable branch registry and private schema/semantic implementations live
under :mod:`pheroos.governance._schema`.  Keeping these wrappers here preserves
the canonical public owner, call signatures, and import compatibility.
"""

from __future__ import annotations

from typing import Any

from pheroos.governance._schema import (
    commit_schema_document,
    validate_commit_wire_document,
)


def commit_schema() -> dict[str, Any]:
    return commit_schema_document()


def validate_commit_wire_record(record: object) -> list[str]:
    return validate_commit_wire_document(record)


__all__ = ["commit_schema", "validate_commit_wire_record"]
