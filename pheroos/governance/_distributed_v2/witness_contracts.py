"""Portable witness contracts and provider-neutral trust boundary."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Protocol, cast, runtime_checkable

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2

from pheroos.governance._distributed_v2.common import (
    MAX_DISTRIBUTED_ROOTS_V2,
    _canonical_texts,
    _exact_array,
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
    _root,
)
from pheroos.governance._distributed_v2.proposal_contracts import (
    DistributedCommitProposalV2,
)
from pheroos.governance._support_v2.membership_records import MembershipPrincipalV2


DISTRIBUTED_QUORUM_WITNESS_SCHEMA_V2 = "pheroos-distributed-quorum-witness-v2"


@runtime_checkable
class DistributedWitnessAttestationVerifierV2(Protocol):
    """External trust adapter; core owns no key or signature runtime."""

    def verify_distributed_witness_v2(
        self,
        *,
        principal_ref: str,
        verification_root: str,
        signing_root: str,
        attestation_ref: str,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class DistributedQuorumWitnessV2:
    domain_root: str
    scope_ref: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    epoch: int
    proposal_digest: str
    semantic_value_root: str
    candidate_ref: str
    claim_root: str
    membership_root: str
    verification_set_root: str
    principal_ref: str
    verification_root: str
    cluster_ref: str
    failure_domain_ref: str
    witness_nonce: str
    witnessed_at_step: int
    expires_at_step: int
    provenance_ref: str
    source_trace_roots: Sequence[str]
    attestation_ref: str
    schema: str = DISTRIBUTED_QUORUM_WITNESS_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    signing_root: str = ""
    witness_root: str = ""

    _root_field: ClassVar[str] = "witness_root"

    def __post_init__(self) -> None:
        if (
            self.schema != DISTRIBUTED_QUORUM_WITNESS_SCHEMA_V2
            or self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2
        ):
            raise ValueError("distributed witness version is unsupported")
        for field in _WITNESS_TEXT_FIELDS:
            _require_text(getattr(self, field), f"distributed witness {field}")
        for field in _WITNESS_ROOT_FIELDS:
            _require_root(getattr(self, field), f"distributed witness {field}")
        _require_count(self.epoch, "distributed witness epoch")
        witnessed = _require_count(
            self.witnessed_at_step, "distributed witness witnessed_at_step"
        )
        expires = _require_count(
            self.expires_at_step, "distributed witness expires_at_step"
        )
        if expires <= witnessed:
            raise ValueError("distributed witness expiry must follow witnessing")
        traces = _canonical_texts(
            self.source_trace_roots,
            "distributed witness trace roots",
            maximum=MAX_DISTRIBUTED_ROOTS_V2,
            allow_empty=False,
            roots=True,
        )
        object.__setattr__(self, "source_trace_roots", traces)
        expected_signing = _root("witness-signing", self._signing_body())
        if self.signing_root not in ("", expected_signing):
            raise ValueError("distributed witness signing_root is mismatched")
        object.__setattr__(self, "signing_root", expected_signing)
        _install_root(
            self,
            "witness_root",
            self.witness_root,
            "witness-envelope",
            self._body(),
        )

    def _signing_body(self) -> dict[str, object]:
        body: dict[str, object] = {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "epoch": self.epoch,
            "witnessed_at_step": self.witnessed_at_step,
            "expires_at_step": self.expires_at_step,
            "source_trace_roots": list(self.source_trace_roots),
        }
        for field in _WITNESS_TEXT_FIELDS[:-1] + _WITNESS_ROOT_FIELDS:
            body[field] = getattr(self, field)
        return body

    def _body(self) -> dict[str, object]:
        return {
            **self._signing_body(),
            "attestation_ref": self.attestation_ref,
            "signing_root": self.signing_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "witness_root": self.witness_root}

    @classmethod
    def from_dict(cls, payload: object) -> DistributedQuorumWitnessV2:
        value = _exact_mapping(payload, _WITNESS_FIELDS, "distributed witness v2")
        decoded = cls(
            schema=cast(str, value["schema"]),
            canonical_version=cast(str, value["canonical_version"]),
            domain_root=cast(str, value["domain_root"]),
            scope_ref=cast(str, value["scope_ref"]),
            protocol_ref=cast(str, value["protocol_ref"]),
            run_ref=cast(str, value["run_ref"]),
            target_ref=cast(str, value["target_ref"]),
            epoch=cast(int, value["epoch"]),
            proposal_digest=cast(str, value["proposal_digest"]),
            semantic_value_root=cast(str, value["semantic_value_root"]),
            candidate_ref=cast(str, value["candidate_ref"]),
            claim_root=cast(str, value["claim_root"]),
            membership_root=cast(str, value["membership_root"]),
            verification_set_root=cast(str, value["verification_set_root"]),
            principal_ref=cast(str, value["principal_ref"]),
            verification_root=cast(str, value["verification_root"]),
            cluster_ref=cast(str, value["cluster_ref"]),
            failure_domain_ref=cast(str, value["failure_domain_ref"]),
            witness_nonce=cast(str, value["witness_nonce"]),
            witnessed_at_step=cast(int, value["witnessed_at_step"]),
            expires_at_step=cast(int, value["expires_at_step"]),
            provenance_ref=cast(str, value["provenance_ref"]),
            source_trace_roots=cast(
                Sequence[str],
                _exact_array(
                    value["source_trace_roots"],
                    "distributed witness trace roots",
                    allow_empty=False,
                ),
            ),
            attestation_ref=cast(str, value["attestation_ref"]),
            signing_root=cast(str, value["signing_root"]),
            witness_root=cast(str, value["witness_root"]),
        )
        _require_canonical_wire(payload, decoded.to_dict(), "distributed witness v2")
        return decoded


def verify_distributed_witness_v2(
    witness: DistributedQuorumWitnessV2,
    *,
    proposal: DistributedCommitProposalV2,
    member: MembershipPrincipalV2,
    cluster_ref: str,
    current_step: int,
    witness_ttl_steps: int,
    trusted_verifier: DistributedWitnessAttestationVerifierV2,
) -> bool:
    """Verify portable content; authority still requires the durable source path."""

    if (
        type(witness) is not DistributedQuorumWitnessV2
        or type(proposal) is not DistributedCommitProposalV2
        or type(member) is not MembershipPrincipalV2
    ):
        return False
    if not isinstance(trusted_verifier, DistributedWitnessAttestationVerifierV2):
        return False
    try:
        now = _require_count(current_step, "distributed witness current step")
        ttl = _require_count(
            witness_ttl_steps,
            "distributed witness TTL",
            minimum=1,
        )
    except (TypeError, ValueError):
        return False
    value = proposal.value
    if witness.witnessed_at_step > now or now >= witness.expires_at_step:
        return False
    if witness.witnessed_at_step > (2**53 - 1) - ttl:
        return False
    if witness.expires_at_step != witness.witnessed_at_step + ttl:
        return False
    expected = (
        value.domain_root,
        value.scope_ref,
        value.protocol_ref,
        value.run_ref,
        value.target_ref,
        value.epoch,
        proposal.proposal_digest,
        value.semantic_value_root,
        value.candidate_ref,
        value.claim_root,
        value.membership_root,
        value.verification_set_root,
        member.principal_ref,
        member.verification_root,
        cluster_ref,
        member.failure_domain_ref,
    )
    observed = (
        witness.domain_root,
        witness.scope_ref,
        witness.protocol_ref,
        witness.run_ref,
        witness.target_ref,
        witness.epoch,
        witness.proposal_digest,
        witness.semantic_value_root,
        witness.candidate_ref,
        witness.claim_root,
        witness.membership_root,
        witness.verification_set_root,
        witness.principal_ref,
        witness.verification_root,
        witness.cluster_ref,
        witness.failure_domain_ref,
    )
    if observed != expected:
        return False
    try:
        trusted = trusted_verifier.verify_distributed_witness_v2(
            principal_ref=witness.principal_ref,
            verification_root=witness.verification_root,
            signing_root=witness.signing_root,
            attestation_ref=witness.attestation_ref,
        )
    except Exception:
        return False
    return trusted is True


_WITNESS_TEXT_FIELDS = (
    "scope_ref",
    "protocol_ref",
    "run_ref",
    "target_ref",
    "candidate_ref",
    "principal_ref",
    "cluster_ref",
    "failure_domain_ref",
    "witness_nonce",
    "provenance_ref",
    "attestation_ref",
)
_WITNESS_ROOT_FIELDS = (
    "domain_root",
    "proposal_digest",
    "semantic_value_root",
    "claim_root",
    "membership_root",
    "verification_set_root",
    "verification_root",
)
_WITNESS_FIELDS = frozenset(
    {
        "schema",
        "canonical_version",
        "epoch",
        "witnessed_at_step",
        "expires_at_step",
        "source_trace_roots",
        "signing_root",
        "witness_root",
        *_WITNESS_TEXT_FIELDS,
        *_WITNESS_ROOT_FIELDS,
    }
)


__all__ = [
    "DISTRIBUTED_QUORUM_WITNESS_SCHEMA_V2",
    "DistributedQuorumWitnessV2",
    "DistributedWitnessAttestationVerifierV2",
    "verify_distributed_witness_v2",
]
