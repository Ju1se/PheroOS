"""Authority-neutral projection of a Store-verified Decision seal inclusion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, cast

from pheroos.governance._commit_decision_v2.common import (
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
)


COMMIT_DECISION_SEAL_INCLUSION_SCHEMA_V2 = "pheroos-commit-decision-seal-inclusion-v2"
_FIELDS = frozenset(
    {
        "schema",
        "stream_ref",
        "revision",
        "transition_id",
        "snapshot_root",
        "receipt_root",
        "head_root",
        "inclusion_root",
        "seal_root",
        "frozen_dependency_root",
        "projection_root",
    }
)


@dataclass(frozen=True, slots=True)
class CommitDecisionSealInclusionV2:
    """Portable facts whose authority comes only from a verified source handle."""

    stream_ref: str
    revision: int
    transition_id: str
    snapshot_root: str
    receipt_root: str
    head_root: str
    inclusion_root: str
    seal_root: str
    frozen_dependency_root: str
    schema: str = COMMIT_DECISION_SEAL_INCLUSION_SCHEMA_V2
    projection_root: str = ""

    _root_field: ClassVar[str] = "projection_root"

    def __post_init__(self) -> None:
        if self.schema != COMMIT_DECISION_SEAL_INCLUSION_SCHEMA_V2:
            raise ValueError("commit decision seal inclusion schema is unsupported")
        _require_text(self.stream_ref, "commit decision seal inclusion stream_ref")
        _require_count(
            self.revision,
            "commit decision seal inclusion revision",
            minimum=1,
        )
        _require_text(
            self.transition_id,
            "commit decision seal inclusion transition_id",
        )
        for field in (
            "snapshot_root",
            "receipt_root",
            "head_root",
            "inclusion_root",
            "seal_root",
            "frozen_dependency_root",
        ):
            _require_root(
                getattr(self, field),
                f"commit decision seal inclusion {field}",
            )
        _install_root(
            self,
            "projection_root",
            self.projection_root,
            "seal-inclusion",
            self._body(),
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "stream_ref": self.stream_ref,
            "revision": self.revision,
            "transition_id": self.transition_id,
            "snapshot_root": self.snapshot_root,
            "receipt_root": self.receipt_root,
            "head_root": self.head_root,
            "inclusion_root": self.inclusion_root,
            "seal_root": self.seal_root,
            "frozen_dependency_root": self.frozen_dependency_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "projection_root": self.projection_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitDecisionSealInclusionV2:
        value = _exact_mapping(
            payload,
            _FIELDS,
            "commit decision seal inclusion v2",
        )
        decoded = cls(
            stream_ref=cast(str, value["stream_ref"]),
            revision=cast(int, value["revision"]),
            transition_id=cast(str, value["transition_id"]),
            snapshot_root=cast(str, value["snapshot_root"]),
            receipt_root=cast(str, value["receipt_root"]),
            head_root=cast(str, value["head_root"]),
            inclusion_root=cast(str, value["inclusion_root"]),
            seal_root=cast(str, value["seal_root"]),
            frozen_dependency_root=cast(
                str,
                value["frozen_dependency_root"],
            ),
            schema=cast(str, value["schema"]),
            projection_root=cast(str, value["projection_root"]),
        )
        _require_canonical_wire(
            payload,
            decoded.to_dict(),
            "commit decision seal inclusion v2",
        )
        return decoded


__all__ = (
    "COMMIT_DECISION_SEAL_INCLUSION_SCHEMA_V2",
    "CommitDecisionSealInclusionV2",
)
