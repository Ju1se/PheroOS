"""Closed dependency projections for Commit Decision v2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, cast

from pheroos.governance.authority_store_v2 import GovernanceCommitPositionV2

from pheroos.governance._commit_decision_v2.common import (
    COMMIT_DECISION_DEPENDENCY_SCHEMA_V2,
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
    _root,
)
from pheroos.governance._commit_decision_v2.enums import (
    CommitDecisionDependencyRoleV2,
)


_FIELDS = frozenset(
    {
        "schema",
        "role",
        "stream_ref",
        "revision",
        "transition_id",
        "snapshot_root",
        "head_root",
        "receipt_root",
        "observed_position",
        "dependency_root",
    }
)


@dataclass(frozen=True, slots=True)
class CommitDecisionDependencyV2:
    role: CommitDecisionDependencyRoleV2
    stream_ref: str
    revision: int
    transition_id: str
    snapshot_root: str
    head_root: str
    receipt_root: str
    observed_position: GovernanceCommitPositionV2
    schema: str = COMMIT_DECISION_DEPENDENCY_SCHEMA_V2
    dependency_root: str = ""

    _root_field: ClassVar[str] = "dependency_root"

    def __post_init__(self) -> None:
        if self.schema != COMMIT_DECISION_DEPENDENCY_SCHEMA_V2:
            raise ValueError("commit decision dependency schema is unsupported")
        if type(self.role) is not CommitDecisionDependencyRoleV2:
            raise TypeError("commit decision dependency role is invalid")
        _require_text(self.stream_ref, "commit decision dependency stream_ref")
        _require_count(self.revision, "commit decision dependency revision")
        _require_text(self.transition_id, "commit decision dependency transition_id")
        for field in ("snapshot_root", "head_root", "receipt_root"):
            _require_root(getattr(self, field), f"commit decision dependency {field}")
        if type(self.observed_position) is not GovernanceCommitPositionV2:
            raise TypeError("commit decision dependency position is invalid")
        if self.revision == 0:
            if (
                self.transition_id != "genesis"
                or self.observed_position is not GovernanceCommitPositionV2.CURRENT
            ):
                raise ValueError("commit decision genesis dependency is invalid")
        elif self.observed_position is not GovernanceCommitPositionV2.CURRENT:
            raise ValueError("commit decision mutation requires current dependencies")
        _install_root(
            self,
            "dependency_root",
            self.dependency_root,
            "dependency",
            self._body(),
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "role": self.role.value,
            "stream_ref": self.stream_ref,
            "revision": self.revision,
            "transition_id": self.transition_id,
            "snapshot_root": self.snapshot_root,
            "head_root": self.head_root,
            "receipt_root": self.receipt_root,
            "observed_position": self.observed_position.value,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "dependency_root": self.dependency_root}

    def root(self) -> str:
        return self.dependency_root

    @classmethod
    def from_dict(cls, payload: object) -> CommitDecisionDependencyV2:
        value = _exact_mapping(payload, _FIELDS, "commit decision dependency v2")
        try:
            value["role"] = CommitDecisionDependencyRoleV2(cast(str, value["role"]))
            value["observed_position"] = GovernanceCommitPositionV2(
                cast(str, value["observed_position"])
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("commit decision dependency enum is unsupported") from exc
        decoded = cls(
            role=cast(CommitDecisionDependencyRoleV2, value["role"]),
            stream_ref=cast(str, value["stream_ref"]),
            revision=cast(int, value["revision"]),
            transition_id=cast(str, value["transition_id"]),
            snapshot_root=cast(str, value["snapshot_root"]),
            head_root=cast(str, value["head_root"]),
            receipt_root=cast(str, value["receipt_root"]),
            observed_position=cast(
                GovernanceCommitPositionV2,
                value["observed_position"],
            ),
            schema=cast(str, value["schema"]),
            dependency_root=cast(str, value["dependency_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "commit decision dependency v2"
        )
        return decoded


def canonical_commit_decision_dependencies_v2(
    dependencies: Sequence[CommitDecisionDependencyV2],
) -> tuple[CommitDecisionDependencyV2, ...]:
    if type(dependencies) not in (list, tuple):
        raise TypeError("commit decision dependencies must be an exact array or tuple")
    values = tuple(dependencies)
    if any(type(item) is not CommitDecisionDependencyV2 for item in values):
        raise TypeError("commit decision dependencies contain a noncanonical record")
    ordered = tuple(sorted(values, key=lambda item: item.role.value.encode("utf-8")))
    roles = tuple(item.role for item in ordered)
    streams = tuple(item.stream_ref for item in ordered)
    if len(roles) != len(set(roles)):
        raise ValueError("commit decision dependency roles must be unique")
    if len(streams) != len(set(streams)):
        raise ValueError("commit decision dependency streams must be unique")
    return ordered


def commit_decision_dependency_set_root_v2(
    dependencies: Sequence[CommitDecisionDependencyV2],
) -> str:
    canonical = canonical_commit_decision_dependencies_v2(dependencies)
    return _root(
        "dependency-set",
        {
            "dependencies": [
                {"role": item.role.value, "root": item.dependency_root}
                for item in canonical
            ]
        },
    )


def commit_decision_frozen_dependency_root_v2(
    dependencies: Sequence[CommitDecisionDependencyV2],
) -> str:
    """Root only decision inputs that a window seal must freeze.

    The rolling decision parent and a later finality owner are deliberately
    excluded: both advance after sealing, while Evidence/Replay/Risk/
    Membership/Principal Verification/Support/Stop/Permission remain
    byte-for-byte frozen.
    """

    canonical = canonical_commit_decision_dependencies_v2(dependencies)
    frozen = tuple(
        item
        for item in canonical
        if item.role
        not in {
            CommitDecisionDependencyRoleV2.PARENT,
            CommitDecisionDependencyRoleV2.CERTIFICATE,
            CommitDecisionDependencyRoleV2.DISTRIBUTED,
        }
    )
    return _root(
        "frozen-dependency-set",
        {
            "dependencies": [
                {"role": item.role.value, "root": item.dependency_root}
                for item in frozen
            ]
        },
    )


def dependency_by_role_v2(
    dependencies: Sequence[CommitDecisionDependencyV2],
    role: CommitDecisionDependencyRoleV2,
) -> CommitDecisionDependencyV2:
    canonical = canonical_commit_decision_dependencies_v2(dependencies)
    matches = tuple(item for item in canonical if item.role is role)
    if len(matches) != 1:
        raise ValueError(f"commit decision dependency role {role.value} is absent")
    return matches[0]


__all__ = (
    "CommitDecisionDependencyV2",
    "canonical_commit_decision_dependencies_v2",
    "commit_decision_dependency_set_root_v2",
    "commit_decision_frozen_dependency_root_v2",
)
