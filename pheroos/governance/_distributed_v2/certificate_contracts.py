"""Portable distributed quorum certificate contracts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, cast

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2

from pheroos.governance._distributed_v2.common import (
    MAX_DISTRIBUTED_PROPOSALS_V2,
    MAX_DISTRIBUTED_WITNESSES_V2,
    _canonical_bytes,
    _canonical_texts,
    _exact_array,
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_text,
    _root,
)
from pheroos.governance._distributed_v2.proposal_contracts import (
    DistributedCommitValueV2,
)
from pheroos.governance._distributed_v2.witness_contracts import (
    DistributedQuorumWitnessV2,
)


DISTRIBUTED_COMMIT_CERTIFICATE_SCHEMA_V2 = "pheroos-distributed-commit-certificate-v2"


@dataclass(frozen=True, slots=True)
class DistributedCommitCertificateV2:
    certificate_ref: str
    issuer_ref: str
    issued_at_step: int
    provenance_ref: str
    value: DistributedCommitValueV2
    proposal_digests: Sequence[str]
    witnesses: Sequence[DistributedQuorumWitnessV2]
    membership_size: int
    max_byzantine_faults: int
    witness_quorum: int
    minimum_failure_domain_diversity: int
    witness_set_root: str = ""
    schema: str = DISTRIBUTED_COMMIT_CERTIFICATE_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    certificate_root: str = ""

    _root_field: ClassVar[str] = "certificate_root"

    def __post_init__(self) -> None:
        if (
            self.schema != DISTRIBUTED_COMMIT_CERTIFICATE_SCHEMA_V2
            or self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2
        ):
            raise ValueError("distributed certificate version is unsupported")
        for field in ("certificate_ref", "issuer_ref", "provenance_ref"):
            _require_text(getattr(self, field), f"distributed certificate {field}")
        _require_count(self.issued_at_step, "distributed certificate issued_at_step")
        if type(self.value) is not DistributedCommitValueV2:
            raise TypeError("distributed certificate requires exact semantic value")
        proposals = _canonical_texts(
            self.proposal_digests,
            "distributed certificate proposal digests",
            maximum=MAX_DISTRIBUTED_PROPOSALS_V2,
            allow_empty=False,
            roots=True,
        )
        object.__setattr__(self, "proposal_digests", proposals)
        witnesses = _canonical_witnesses(self.witnesses)
        object.__setattr__(self, "witnesses", witnesses)
        self._validate_fault_model(witnesses, proposals)
        expected_set = _root(
            "certificate-witness-set",
            {
                "semantic_value_root": self.value.semantic_value_root,
                "witness_roots": [item.witness_root for item in witnesses],
            },
        )
        if self.witness_set_root not in ("", expected_set):
            raise ValueError("distributed certificate witness_set_root is mismatched")
        object.__setattr__(self, "witness_set_root", expected_set)
        _install_root(
            self,
            "certificate_root",
            self.certificate_root,
            "quorum-certificate",
            self._body(),
        )
        if len(_canonical_bytes(self.to_dict())) > 16 * 1024 * 1024:
            raise ValueError("distributed certificate exceeds its byte bound")

    def _validate_fault_model(
        self,
        witnesses: tuple[DistributedQuorumWitnessV2, ...],
        proposals: tuple[str, ...],
    ) -> None:
        n = _require_count(
            self.membership_size,
            "distributed certificate membership size",
            minimum=1,
            maximum=4_096,
        )
        f = _require_count(
            self.max_byzantine_faults,
            "distributed certificate Byzantine faults",
            maximum=4_096,
        )
        q = _require_count(
            self.witness_quorum,
            "distributed certificate quorum",
            minimum=1,
            maximum=4_096,
        )
        diversity = _require_count(
            self.minimum_failure_domain_diversity,
            "distributed certificate diversity",
            minimum=1,
            maximum=4_096,
        )
        if n < 3 * f + 1 or q > n - f or 2 * q - n <= f:
            raise ValueError("distributed certificate fault model is invalid")
        principals = tuple(item.principal_ref for item in witnesses)
        domains = {item.failure_domain_ref for item in witnesses}
        if len(witnesses) < q or len(principals) != len(set(principals)):
            raise ValueError("distributed certificate lacks distinct-principal quorum")
        if len(domains) < diversity:
            raise ValueError("distributed certificate lacks failure-domain diversity")
        for witness in witnesses:
            if (
                witness.semantic_value_root != self.value.semantic_value_root
                or witness.proposal_digest not in proposals
                or witness.candidate_ref != self.value.candidate_ref
                or witness.claim_root != self.value.claim_root
                or witness.epoch != self.value.epoch
            ):
                raise ValueError("distributed certificate contains cross-bound witness")

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "certificate_ref": self.certificate_ref,
            "issuer_ref": self.issuer_ref,
            "issued_at_step": self.issued_at_step,
            "provenance_ref": self.provenance_ref,
            "value": self.value.to_dict(),
            "proposal_digests": list(self.proposal_digests),
            "witnesses": [item.to_dict() for item in self.witnesses],
            "membership_size": self.membership_size,
            "max_byzantine_faults": self.max_byzantine_faults,
            "witness_quorum": self.witness_quorum,
            "minimum_failure_domain_diversity": (self.minimum_failure_domain_diversity),
            "witness_set_root": self.witness_set_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "certificate_root": self.certificate_root}

    @classmethod
    def from_dict(cls, payload: object) -> DistributedCommitCertificateV2:
        value = _exact_mapping(
            payload,
            frozenset(
                {
                    "schema",
                    "canonical_version",
                    "certificate_ref",
                    "issuer_ref",
                    "issued_at_step",
                    "provenance_ref",
                    "value",
                    "proposal_digests",
                    "witnesses",
                    "membership_size",
                    "max_byzantine_faults",
                    "witness_quorum",
                    "minimum_failure_domain_diversity",
                    "witness_set_root",
                    "certificate_root",
                }
            ),
            "distributed certificate v2",
        )
        decoded = cls(
            schema=cast(str, value["schema"]),
            canonical_version=cast(str, value["canonical_version"]),
            certificate_ref=cast(str, value["certificate_ref"]),
            issuer_ref=cast(str, value["issuer_ref"]),
            issued_at_step=cast(int, value["issued_at_step"]),
            provenance_ref=cast(str, value["provenance_ref"]),
            value=DistributedCommitValueV2.from_dict(value["value"]),
            proposal_digests=cast(
                Sequence[str],
                _exact_array(
                    value["proposal_digests"],
                    "distributed certificate proposal digests",
                    maximum=MAX_DISTRIBUTED_PROPOSALS_V2,
                    allow_empty=False,
                ),
            ),
            witnesses=tuple(
                DistributedQuorumWitnessV2.from_dict(item)
                for item in _exact_array(
                    value["witnesses"],
                    "distributed certificate witnesses",
                    maximum=MAX_DISTRIBUTED_WITNESSES_V2,
                    allow_empty=False,
                )
            ),
            membership_size=cast(int, value["membership_size"]),
            max_byzantine_faults=cast(int, value["max_byzantine_faults"]),
            witness_quorum=cast(int, value["witness_quorum"]),
            minimum_failure_domain_diversity=cast(
                int, value["minimum_failure_domain_diversity"]
            ),
            witness_set_root=cast(str, value["witness_set_root"]),
            certificate_root=cast(str, value["certificate_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "distributed certificate v2"
        )
        return decoded


def _canonical_witnesses(
    witnesses: Sequence[DistributedQuorumWitnessV2],
) -> tuple[DistributedQuorumWitnessV2, ...]:
    if type(witnesses) not in (list, tuple):
        raise TypeError("distributed certificate witnesses require exact sequence")
    values = tuple(witnesses)
    if not values or len(values) > MAX_DISTRIBUTED_WITNESSES_V2:
        raise ValueError("distributed certificate witness count is invalid")
    if any(type(item) is not DistributedQuorumWitnessV2 for item in values):
        raise TypeError("distributed certificate witness is noncanonical")
    roots = tuple(item.witness_root for item in values)
    if len(roots) != len(set(roots)):
        raise ValueError("distributed certificate repeats witness roots")
    return tuple(sorted(values, key=lambda item: item.witness_root.encode("utf-8")))


__all__ = [
    "DISTRIBUTED_COMMIT_CERTIFICATE_SCHEMA_V2",
    "DistributedCommitCertificateV2",
]
