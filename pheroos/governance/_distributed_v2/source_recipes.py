"""Frozen non-portable recipes retained by distributed source handles."""

from __future__ import annotations

from dataclasses import dataclass

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2

from pheroos.governance._distributed_v2.conflict_contracts import (
    DistributedWitnessConflictObservationV2,
)
from pheroos.governance._distributed_v2.witness_contracts import (
    DistributedQuorumWitnessV2,
    DistributedWitnessAttestationVerifierV2,
)


@dataclass(frozen=True, slots=True)
class _EpochRecipeV2:
    membership_state: object
    manifest: ScopedProtocolManifestV2
    parent_state: object | None
    transition_certificate_ref: str
    mutation_ref: str
    mutation_issuer_ref: str
    current_step: int
    provenance_ref: str
    source_trace_roots: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ProposalRecipeV2:
    decision_state: object
    central_certificate_state: object
    membership_state: object
    epoch_state: object
    parent_state: object | None
    manifest: ScopedProtocolManifestV2
    proposal_ref: str
    proposer_ref: str
    proposal_nonce: str
    provenance_ref: str
    source_trace_roots: tuple[str, ...]
    mutation_ref: str
    mutation_issuer_ref: str
    current_step: int


@dataclass(frozen=True, slots=True)
class _WitnessRecipeV2:
    decision_state: object
    central_certificate_state: object
    membership_state: object
    epoch_state: object
    proposal_state: object
    parent_state: object | None
    manifest: ScopedProtocolManifestV2
    witness: DistributedQuorumWitnessV2
    trusted_verifier: DistributedWitnessAttestationVerifierV2
    mutation_ref: str
    mutation_issuer_ref: str
    current_step: int


@dataclass(frozen=True, slots=True)
class _WitnessConflictObservationRecipeV2:
    decision_state: object
    central_certificate_state: object
    membership_state: object
    epoch_state: object
    proposal_state: object
    parent_state: object
    manifest: ScopedProtocolManifestV2
    observation: DistributedWitnessConflictObservationV2
    trusted_verifier: DistributedWitnessAttestationVerifierV2
    mutation_ref: str
    mutation_issuer_ref: str
    current_step: int


@dataclass(frozen=True, slots=True)
class _CertificateRecipeV2:
    decision_state: object
    central_certificate_state: object
    membership_state: object
    epoch_state: object
    proposal_state: object
    witness_state: object
    parent_state: object | None
    manifest: ScopedProtocolManifestV2
    trusted_verifier: DistributedWitnessAttestationVerifierV2
    certificate_ref: str
    provenance_ref: str
    mutation_ref: str
    mutation_issuer_ref: str
    current_step: int


_RecipeV2 = (
    _EpochRecipeV2
    | _ProposalRecipeV2
    | _WitnessRecipeV2
    | _WitnessConflictObservationRecipeV2
    | _CertificateRecipeV2
)
_RECIPE_TYPES = frozenset(
    {
        _EpochRecipeV2,
        _ProposalRecipeV2,
        _WitnessRecipeV2,
        _WitnessConflictObservationRecipeV2,
        _CertificateRecipeV2,
    }
)


__all__: tuple[str, ...] = ()
