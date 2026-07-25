"""Canonical Sybil-collapsed records for durable Membership v2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _canonical_bytes,
    _compute_root,
    _require_root,
)
from pheroos.governance._support_v2.common import (
    _canonical_utf8_order_v2,
    _require_bounded_text_v2,
    _require_canonical_wire_v2,
    _require_exact_array_v2,
    _require_exact_mapping_v2,
)


MEMBERSHIP_PRINCIPAL_SCHEMA_V2 = "pheroos-membership-principal-v2"
MEMBERSHIP_CLUSTER_SCHEMA_V2 = "pheroos-membership-cluster-v2"
MAX_MEMBERSHIP_PRINCIPALS_V2 = 4096
MAX_MEMBERSHIP_CLUSTERS_V2 = 1024


@dataclass(frozen=True, slots=True)
class MembershipPrincipalV2:
    principal_ref: str
    verification_root: str
    verified_issuer_ref: str
    verification_method: str
    failure_domain_ref: str
    schema: str = MEMBERSHIP_PRINCIPAL_SCHEMA_V2
    principal_root: str = ""

    _root_field: ClassVar[str] = "principal_root"

    def __post_init__(self) -> None:
        if self.schema != MEMBERSHIP_PRINCIPAL_SCHEMA_V2:
            raise ValueError("membership principal schema is unsupported")
        for field in ("principal_ref", "verified_issuer_ref", "verification_method"):
            _require_bounded_text_v2(getattr(self, field), f"membership {field}")
        _require_bounded_text_v2(
            self.failure_domain_ref,
            "membership failure_domain_ref",
            allow_empty=True,
        )
        _require_root(self.verification_root, "membership verification_root")
        expected = _compute_root("membership-v2:principal", self._body())
        if self.principal_root not in ("", expected):
            raise ValueError("membership principal_root is mismatched")
        object.__setattr__(self, "principal_root", expected)

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "principal_ref": self.principal_ref,
            "verification_root": self.verification_root,
            "verified_issuer_ref": self.verified_issuer_ref,
            "verification_method": self.verification_method,
            "failure_domain_ref": self.failure_domain_ref,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "principal_root": self.principal_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.principal_root

    @classmethod
    def from_dict(cls, payload: object) -> MembershipPrincipalV2:
        value = _require_exact_mapping_v2(
            payload,
            frozenset(
                {
                    "schema",
                    "principal_ref",
                    "verification_root",
                    "verified_issuer_ref",
                    "verification_method",
                    "failure_domain_ref",
                    "principal_root",
                }
            ),
            "membership principal v2",
        )
        decoded = cls(**value)  # type: ignore[arg-type]
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "membership principal v2",
        )
        return decoded


@dataclass(frozen=True, slots=True)
class MembershipClusterV2:
    cluster_ref: str
    principals: Sequence[MembershipPrincipalV2]
    schema: str = MEMBERSHIP_CLUSTER_SCHEMA_V2
    cluster_root: str = ""

    def __post_init__(self) -> None:
        if self.schema != MEMBERSHIP_CLUSTER_SCHEMA_V2:
            raise ValueError("membership cluster schema is unsupported")
        _require_bounded_text_v2(self.cluster_ref, "membership cluster_ref")
        if type(self.principals) not in (list, tuple):
            raise TypeError("membership principals require exact array or tuple")
        principals = tuple(self.principals)
        if not principals or len(principals) > MAX_MEMBERSHIP_PRINCIPALS_V2:
            raise ValueError("membership cluster principal count is outside its bound")
        if any(type(item) is not MembershipPrincipalV2 for item in principals):
            raise TypeError("membership cluster contains a non-exact principal")
        refs = tuple(item.principal_ref for item in principals)
        roots = tuple(item.verification_root for item in principals)
        if len(refs) != len(set(refs)) or len(roots) != len(set(roots)):
            raise ValueError("membership cluster repeats principal meaning")
        by_ref = {item.principal_ref: item for item in principals}
        canonical = tuple(by_ref[ref] for ref in _canonical_utf8_order_v2(refs))
        object.__setattr__(self, "principals", canonical)
        expected = _compute_root("membership-v2:cluster", self._body())
        if self.cluster_root not in ("", expected):
            raise ValueError("membership cluster_root is mismatched")
        object.__setattr__(self, "cluster_root", expected)

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "cluster_ref": self.cluster_ref,
            "principals": [item.to_dict() for item in self.principals],
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "cluster_root": self.cluster_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.cluster_root

    @classmethod
    def from_dict(cls, payload: object) -> MembershipClusterV2:
        value = _require_exact_mapping_v2(
            payload,
            frozenset({"schema", "cluster_ref", "principals", "cluster_root"}),
            "membership cluster v2",
        )
        raw = _require_exact_array_v2(
            value["principals"],
            "membership cluster principals",
            limit=MAX_MEMBERSHIP_PRINCIPALS_V2,
        )
        value["principals"] = tuple(
            MembershipPrincipalV2.from_dict(item) for item in raw
        )
        decoded = cls(**value)  # type: ignore[arg-type]
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "membership cluster v2",
        )
        return decoded


def canonical_membership_clusters_v2(
    clusters: Sequence[MembershipClusterV2],
) -> tuple[MembershipClusterV2, ...]:
    if type(clusters) not in (list, tuple):
        raise TypeError("membership clusters require exact array or tuple")
    values = tuple(clusters)
    if len(values) > MAX_MEMBERSHIP_CLUSTERS_V2:
        raise ValueError("membership cluster count exceeds its bound")
    if any(type(item) is not MembershipClusterV2 for item in values):
        raise TypeError("membership contains a non-exact cluster")
    if sum(len(item.principals) for item in values) > MAX_MEMBERSHIP_PRINCIPALS_V2:
        raise ValueError("membership principal count exceeds its bound")
    cluster_refs = tuple(item.cluster_ref for item in values)
    principal_refs = tuple(
        principal.principal_ref for item in values for principal in item.principals
    )
    verification_roots = tuple(
        principal.verification_root for item in values for principal in item.principals
    )
    if (
        len(cluster_refs) != len(set(cluster_refs))
        or len(principal_refs) != len(set(principal_refs))
        or len(verification_roots) != len(set(verification_roots))
    ):
        raise ValueError("membership repeats cluster or principal meaning")
    by_ref = {item.cluster_ref: item for item in values}
    return tuple(by_ref[ref] for ref in _canonical_utf8_order_v2(cluster_refs))


__all__ = [
    "MAX_MEMBERSHIP_CLUSTERS_V2",
    "MAX_MEMBERSHIP_PRINCIPALS_V2",
    "MEMBERSHIP_CLUSTER_SCHEMA_V2",
    "MEMBERSHIP_PRINCIPAL_SCHEMA_V2",
    "MembershipClusterV2",
    "MembershipPrincipalV2",
    "canonical_membership_clusters_v2",
]
