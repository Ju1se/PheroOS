"""Portable authority-leaf commitments for Commit Certificate v2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, cast

from pheroos.governance._commit_certificate_v2.common import (
    MAX_COMMIT_CERTIFICATE_LEAVES_V2,
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
    _root,
)
from pheroos.governance._commit_certificate_v2.enums import (
    CommitCertificateAuthorityRoleV2,
    REQUIRED_COMMIT_CERTIFICATE_AUTHORITY_ROLES_V2,
)


COMMIT_CERTIFICATE_AUTHORITY_LEAF_SCHEMA_V2 = (
    "pheroos-commit-certificate-authority-leaf-v2"
)


@dataclass(frozen=True, slots=True)
class CommitCertificateAuthorityLeafV2:
    """One exact current upstream authority head frozen by the Decision seal."""

    role: CommitCertificateAuthorityRoleV2
    stream_ref: str
    revision: int
    transition_id: str
    snapshot_root: str
    head_root: str
    receipt_root: str
    schema: str = COMMIT_CERTIFICATE_AUTHORITY_LEAF_SCHEMA_V2
    leaf_root: str = ""

    _root_field: ClassVar[str] = "leaf_root"

    def __post_init__(self) -> None:
        if self.schema != COMMIT_CERTIFICATE_AUTHORITY_LEAF_SCHEMA_V2:
            raise ValueError("commit certificate authority leaf schema is unsupported")
        if type(self.role) is not CommitCertificateAuthorityRoleV2:
            raise TypeError("commit certificate authority leaf role is invalid")
        _require_text(self.stream_ref, "commit certificate leaf stream_ref")
        _require_count(self.revision, "commit certificate leaf revision", minimum=1)
        _require_text(self.transition_id, "commit certificate leaf transition_id")
        for field in ("snapshot_root", "head_root", "receipt_root"):
            _require_root(getattr(self, field), f"commit certificate leaf {field}")
        _install_root(self, "leaf_root", self.leaf_root, "authority-leaf", self._body())

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
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "leaf_root": self.leaf_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitCertificateAuthorityLeafV2:
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
                    "leaf_root",
                }
            ),
            "commit certificate authority leaf v2",
        )
        try:
            role = CommitCertificateAuthorityRoleV2(cast(str, value["role"]))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "commit certificate authority leaf role is unsupported"
            ) from exc
        decoded = cls(
            schema=cast(str, value["schema"]),
            role=role,
            stream_ref=cast(str, value["stream_ref"]),
            revision=cast(int, value["revision"]),
            transition_id=cast(str, value["transition_id"]),
            snapshot_root=cast(str, value["snapshot_root"]),
            head_root=cast(str, value["head_root"]),
            receipt_root=cast(str, value["receipt_root"]),
            leaf_root=cast(str, value["leaf_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "commit certificate authority leaf v2"
        )
        return decoded


def canonical_commit_certificate_authority_leaves_v2(
    leaves: Sequence[CommitCertificateAuthorityLeafV2],
) -> tuple[CommitCertificateAuthorityLeafV2, ...]:
    if type(leaves) not in (list, tuple):
        raise TypeError("commit certificate authority leaves must be an exact sequence")
    values = tuple(leaves)
    if not 1 <= len(values) <= MAX_COMMIT_CERTIFICATE_LEAVES_V2:
        raise ValueError("commit certificate authority leaf count is invalid")
    if any(type(item) is not CommitCertificateAuthorityLeafV2 for item in values):
        raise TypeError("commit certificate authority leaves are noncanonical")
    ordered = tuple(sorted(values, key=lambda item: item.role.value.encode("utf-8")))
    roles = tuple(item.role for item in ordered)
    streams = tuple(item.stream_ref for item in ordered)
    if len(roles) != len(set(roles)) or len(streams) != len(set(streams)):
        raise ValueError("commit certificate authority leaves must be unique")
    if frozenset(roles) != REQUIRED_COMMIT_CERTIFICATE_AUTHORITY_ROLES_V2:
        raise ValueError("commit certificate authority leaf set is incomplete")
    return ordered


def commit_certificate_authority_leaf_set_root_v2(
    leaves: Sequence[CommitCertificateAuthorityLeafV2],
) -> str:
    canonical = canonical_commit_certificate_authority_leaves_v2(leaves)
    return _root(
        "authority-leaf-set",
        {
            "leaves": [
                {"role": item.role.value, "leaf_root": item.leaf_root}
                for item in canonical
            ]
        },
    )


__all__ = [
    "COMMIT_CERTIFICATE_AUTHORITY_LEAF_SCHEMA_V2",
    "CommitCertificateAuthorityLeafV2",
    "canonical_commit_certificate_authority_leaves_v2",
    "commit_certificate_authority_leaf_set_root_v2",
]
