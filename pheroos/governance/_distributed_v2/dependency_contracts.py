"""Closed dependency leaves used by every Distributed Commit mutation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, cast

from pheroos.governance._distributed_v2.common import (
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
    _root,
)
from pheroos.governance._distributed_v2.enums import DistributedDependencyRoleV2


DISTRIBUTED_DEPENDENCY_SCHEMA_V2 = "pheroos-distributed-dependency-v2"


@dataclass(frozen=True, slots=True)
class DistributedDependencyV2:
    role: DistributedDependencyRoleV2
    stream_ref: str
    revision: int
    transition_id: str
    snapshot_root: str
    head_root: str
    receipt_root: str
    inclusion_root: str
    schema: str = DISTRIBUTED_DEPENDENCY_SCHEMA_V2
    dependency_root: str = ""

    _root_field: ClassVar[str] = "dependency_root"

    def __post_init__(self) -> None:
        if self.schema != DISTRIBUTED_DEPENDENCY_SCHEMA_V2:
            raise ValueError("distributed dependency schema is unsupported")
        if type(self.role) is not DistributedDependencyRoleV2:
            raise TypeError("distributed dependency role is invalid")
        _require_text(self.stream_ref, "distributed dependency stream_ref")
        revision = _require_count(self.revision, "distributed dependency revision")
        _require_root(self.head_root, "distributed dependency head_root")
        if revision == 0:
            if any(
                (
                    self.transition_id,
                    self.snapshot_root,
                    self.receipt_root,
                    self.inclusion_root,
                )
            ):
                raise ValueError("distributed genesis dependency carries inclusion")
        else:
            _require_text(self.transition_id, "distributed dependency transition_id")
            for field in ("snapshot_root", "receipt_root", "inclusion_root"):
                _require_root(getattr(self, field), f"distributed dependency {field}")
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
            "inclusion_root": self.inclusion_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "dependency_root": self.dependency_root}

    @classmethod
    def from_dict(cls, payload: object) -> DistributedDependencyV2:
        value = _exact_mapping(
            payload,
            frozenset(
                {
                    "schema",
                    "role",
                    "stream_ref",
                    "revision",
                    "transition_id",
                    "snapshot_root",
                    "head_root",
                    "receipt_root",
                    "inclusion_root",
                    "dependency_root",
                }
            ),
            "distributed dependency v2",
        )
        try:
            role = DistributedDependencyRoleV2(cast(str, value["role"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("distributed dependency role is unsupported") from exc
        decoded = cls(
            schema=cast(str, value["schema"]),
            role=role,
            stream_ref=cast(str, value["stream_ref"]),
            revision=cast(int, value["revision"]),
            transition_id=cast(str, value["transition_id"]),
            snapshot_root=cast(str, value["snapshot_root"]),
            head_root=cast(str, value["head_root"]),
            receipt_root=cast(str, value["receipt_root"]),
            inclusion_root=cast(str, value["inclusion_root"]),
            dependency_root=cast(str, value["dependency_root"]),
        )
        _require_canonical_wire(payload, decoded.to_dict(), "distributed dependency v2")
        return decoded


def canonical_distributed_dependencies_v2(
    dependencies: Sequence[DistributedDependencyV2],
) -> tuple[DistributedDependencyV2, ...]:
    if type(dependencies) not in (list, tuple):
        raise TypeError("distributed dependencies require exact sequence")
    values = tuple(dependencies)
    if len(values) > len(DistributedDependencyRoleV2):
        raise ValueError("distributed dependency set exceeds its closed roles")
    if any(type(item) is not DistributedDependencyV2 for item in values):
        raise TypeError("distributed dependency is noncanonical")
    ordered = tuple(sorted(values, key=lambda item: item.role.value.encode("utf-8")))
    roles = tuple(item.role for item in ordered)
    streams = tuple(item.stream_ref for item in ordered)
    if len(roles) != len(set(roles)) or len(streams) != len(set(streams)):
        raise ValueError("distributed dependencies repeat role or stream")
    return ordered


def distributed_dependency_set_root_v2(
    dependencies: Sequence[DistributedDependencyV2],
) -> str:
    values = canonical_distributed_dependencies_v2(dependencies)
    return _root(
        "dependency-set",
        {
            "dependencies": [
                {"role": item.role.value, "dependency_root": item.dependency_root}
                for item in values
            ]
        },
    )


__all__ = [
    "DISTRIBUTED_DEPENDENCY_SCHEMA_V2",
    "DistributedDependencyV2",
    "canonical_distributed_dependencies_v2",
    "distributed_dependency_set_root_v2",
]
