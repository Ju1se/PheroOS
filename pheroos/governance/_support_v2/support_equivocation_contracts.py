"""Portable equivocation findings derived from the Support v2 ledger."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypedDict, cast

from pheroos.governance._authority_store_v2_contracts.foundation import _require_root
from pheroos.governance._support_v2.common import (
    _require_bounded_text_v2,
    _require_canonical_wire_v2,
    _require_count_v2,
    _require_exact_array_v2,
    _require_exact_mapping_v2,
)
from pheroos.governance._support_v2.support_evidence_contracts import (
    _bounded_root_tuple,
    _bounded_text_tuple,
    _exact_version,
    _install_root,
)
from pheroos.governance._support_v2.support_lease_contracts import (
    MAX_SUPPORT_LEASES_V2,
    SUPPORT_EQUIVOCATION_SCHEMA_V2,
)


class _SupportEquivocationDecodedV2(TypedDict):
    target_ref: str
    claim_root: str
    epoch: int
    principal_cluster_ref: str
    support_snapshot_root: str
    lease_set_root: str
    conflicting_candidate_refs: tuple[str, ...]
    conflicting_lease_roots: tuple[str, ...]
    first_overlap_step: int
    schema: str
    finding_root: str


@dataclass(frozen=True, slots=True)
class SupportEquivocationV2:
    target_ref: str
    claim_root: str
    epoch: int
    principal_cluster_ref: str
    support_snapshot_root: str
    lease_set_root: str
    conflicting_candidate_refs: Sequence[str]
    conflicting_lease_roots: Sequence[str]
    first_overlap_step: int
    schema: str = SUPPORT_EQUIVOCATION_SCHEMA_V2
    finding_root: str = ""

    def __post_init__(self) -> None:
        _exact_version(
            self.schema,
            SUPPORT_EQUIVOCATION_SCHEMA_V2,
            "support equivocation schema",
        )
        for field in ("target_ref", "principal_cluster_ref"):
            _require_bounded_text_v2(
                getattr(self, field),
                f"support equivocation {field}",
            )
        for field in ("claim_root", "support_snapshot_root", "lease_set_root"):
            _require_root(getattr(self, field), f"support equivocation {field}")
        _require_count_v2(self.epoch, "support equivocation epoch")
        _require_count_v2(
            self.first_overlap_step,
            "support equivocation overlap step",
        )
        candidates = _bounded_text_tuple(
            self.conflicting_candidate_refs,
            "support equivocation candidates",
            limit=MAX_SUPPORT_LEASES_V2,
        )
        roots = _bounded_root_tuple(
            self.conflicting_lease_roots,
            "support equivocation leases",
            limit=MAX_SUPPORT_LEASES_V2,
        )
        if len(candidates) < 2 or len(roots) < 2:
            raise ValueError("support equivocation requires at least two conflicts")
        object.__setattr__(self, "conflicting_candidate_refs", candidates)
        object.__setattr__(self, "conflicting_lease_roots", roots)
        _install_root(
            self,
            "finding_root",
            self.finding_root,
            "equivocation",
            self._body(),
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "target_ref": self.target_ref,
            "claim_root": self.claim_root,
            "epoch": self.epoch,
            "principal_cluster_ref": self.principal_cluster_ref,
            "support_snapshot_root": self.support_snapshot_root,
            "lease_set_root": self.lease_set_root,
            "conflicting_candidate_refs": list(self.conflicting_candidate_refs),
            "conflicting_lease_roots": list(self.conflicting_lease_roots),
            "first_overlap_step": self.first_overlap_step,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "finding_root": self.finding_root}

    @classmethod
    def from_dict(cls, payload: object) -> SupportEquivocationV2:
        fields = frozenset(
            {
                "schema",
                "target_ref",
                "claim_root",
                "epoch",
                "principal_cluster_ref",
                "support_snapshot_root",
                "lease_set_root",
                "conflicting_candidate_refs",
                "conflicting_lease_roots",
                "first_overlap_step",
                "finding_root",
            }
        )
        value = _require_exact_mapping_v2(
            payload,
            fields,
            "support equivocation v2",
        )
        value["conflicting_candidate_refs"] = tuple(
            _require_exact_array_v2(
                value["conflicting_candidate_refs"],
                "support equivocation candidates",
                limit=MAX_SUPPORT_LEASES_V2,
            )
        )
        value["conflicting_lease_roots"] = tuple(
            _require_exact_array_v2(
                value["conflicting_lease_roots"],
                "support equivocation leases",
                limit=MAX_SUPPORT_LEASES_V2,
            )
        )
        decoded = cls(**cast(_SupportEquivocationDecodedV2, value))
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "support equivocation v2",
        )
        return decoded


__all__ = ["SupportEquivocationV2"]
