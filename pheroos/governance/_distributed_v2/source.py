"""Opaque trusted source preparation for all distributed lane mutations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import NoReturn, SupportsIndex, cast, final

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2

from pheroos.governance._distributed_v2.conflict_contracts import (
    DistributedWitnessConflictObservationV2,
)
from pheroos.governance._distributed_v2.request import DistributedAdvanceRequestV2
from pheroos.governance._distributed_v2.source_builders import _build_recipe_v2
from pheroos.governance._distributed_v2.source_recipes import (
    _CertificateRecipeV2,
    _EpochRecipeV2,
    _ProposalRecipeV2,
    _RECIPE_TYPES,
    _RecipeV2,
    _WitnessConflictObservationRecipeV2,
    _WitnessRecipeV2,
)
from pheroos.governance._distributed_v2.state_contracts import (
    DistributedLaneSnapshotV2,
)
from pheroos.governance._distributed_v2.witness_contracts import (
    DistributedQuorumWitnessV2,
    DistributedWitnessAttestationVerifierV2,
)


# This identity token only proves that a recipe bundle was issued in this process.
# It carries no standalone authority: commit always rebuilds the full replacement,
# reloads every declared dependency, and includes grant/lifecycle heads in one CAS.
_SOURCE_TOKEN_V2 = object()


@final
class VerifiedDistributedAdvanceSourceV2:
    """Non-portable recipe bundle with no standalone authority.

    The private token is only an in-process anti-forgery marker.  A token, recipe,
    request copy, or same-shaped object cannot authorize a write.  Commit rebuilds
    the complete replacement from the opaque recipe, reloads the full dependency
    set, and atomically compares parent, dependencies, grant, and lifecycle heads.
    """

    __slots__ = ("_anchor_root", "_recipe", "_request", "_self_anchor", "_token")

    def __new__(
        cls, *_args: object, **_kwargs: object
    ) -> VerifiedDistributedAdvanceSourceV2:
        raise TypeError("VerifiedDistributedAdvanceSourceV2 cannot be constructed")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedDistributedAdvanceSourceV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedDistributedAdvanceSourceV2 is immutable")

    def __copy__(self) -> VerifiedDistributedAdvanceSourceV2:
        _verified_source_material_v2(self)
        return self

    def __deepcopy__(
        self, _memo: dict[int, object]
    ) -> VerifiedDistributedAdvanceSourceV2:
        _verified_source_material_v2(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedDistributedAdvanceSourceV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedDistributedAdvanceSourceV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("VerifiedDistributedAdvanceSourceV2 is not portable")

    def __repr__(self) -> str:
        return "<VerifiedDistributedAdvanceSourceV2 redacted>"


def prepare_distributed_epoch_v2(
    *,
    membership_state: object,
    manifest: ScopedProtocolManifestV2,
    transition_certificate_ref: str,
    mutation_ref: str,
    mutation_issuer_ref: str,
    current_step: int,
    provenance_ref: str,
    source_trace_roots: Sequence[str],
    parent_state: object | None = None,
) -> tuple[DistributedAdvanceRequestV2, VerifiedDistributedAdvanceSourceV2]:
    recipe = _EpochRecipeV2(
        membership_state=membership_state,
        manifest=manifest,
        parent_state=parent_state,
        transition_certificate_ref=transition_certificate_ref,
        mutation_ref=mutation_ref,
        mutation_issuer_ref=mutation_issuer_ref,
        current_step=current_step,
        provenance_ref=provenance_ref,
        source_trace_roots=tuple(source_trace_roots),
    )
    return _prepared(recipe)


def prepare_distributed_proposal_v2(
    *,
    decision_state: object,
    central_certificate_state: object,
    membership_state: object,
    epoch_state: object,
    manifest: ScopedProtocolManifestV2,
    proposal_ref: str,
    proposer_ref: str,
    proposal_nonce: str,
    provenance_ref: str,
    source_trace_roots: Sequence[str],
    mutation_ref: str,
    mutation_issuer_ref: str,
    current_step: int,
    parent_state: object | None = None,
) -> tuple[DistributedAdvanceRequestV2, VerifiedDistributedAdvanceSourceV2]:
    recipe = _ProposalRecipeV2(
        decision_state=decision_state,
        central_certificate_state=central_certificate_state,
        membership_state=membership_state,
        epoch_state=epoch_state,
        parent_state=parent_state,
        manifest=manifest,
        proposal_ref=proposal_ref,
        proposer_ref=proposer_ref,
        proposal_nonce=proposal_nonce,
        provenance_ref=provenance_ref,
        source_trace_roots=tuple(source_trace_roots),
        mutation_ref=mutation_ref,
        mutation_issuer_ref=mutation_issuer_ref,
        current_step=current_step,
    )
    return _prepared(recipe)


def prepare_distributed_witness_v2(
    *,
    decision_state: object,
    central_certificate_state: object,
    membership_state: object,
    epoch_state: object,
    proposal_state: object,
    manifest: ScopedProtocolManifestV2,
    witness: DistributedQuorumWitnessV2,
    trusted_verifier: DistributedWitnessAttestationVerifierV2,
    mutation_ref: str,
    mutation_issuer_ref: str,
    current_step: int,
    parent_state: object | None = None,
) -> tuple[DistributedAdvanceRequestV2, VerifiedDistributedAdvanceSourceV2]:
    recipe = _WitnessRecipeV2(
        decision_state=decision_state,
        central_certificate_state=central_certificate_state,
        membership_state=membership_state,
        epoch_state=epoch_state,
        proposal_state=proposal_state,
        parent_state=parent_state,
        manifest=manifest,
        witness=witness,
        trusted_verifier=trusted_verifier,
        mutation_ref=mutation_ref,
        mutation_issuer_ref=mutation_issuer_ref,
        current_step=current_step,
    )
    return _prepared(recipe)


def prepare_distributed_witness_conflict_observation_v2(
    *,
    decision_state: object,
    central_certificate_state: object,
    membership_state: object,
    epoch_state: object,
    proposal_state: object,
    parent_state: object,
    manifest: ScopedProtocolManifestV2,
    observation: DistributedWitnessConflictObservationV2,
    trusted_verifier: DistributedWitnessAttestationVerifierV2,
    mutation_ref: str,
    mutation_issuer_ref: str,
    current_step: int,
) -> tuple[DistributedAdvanceRequestV2, VerifiedDistributedAdvanceSourceV2]:
    """Prepare a freeze-only external Byzantine witness observation."""

    recipe = _WitnessConflictObservationRecipeV2(
        decision_state=decision_state,
        central_certificate_state=central_certificate_state,
        membership_state=membership_state,
        epoch_state=epoch_state,
        proposal_state=proposal_state,
        parent_state=parent_state,
        manifest=manifest,
        observation=observation,
        trusted_verifier=trusted_verifier,
        mutation_ref=mutation_ref,
        mutation_issuer_ref=mutation_issuer_ref,
        current_step=current_step,
    )
    return _prepared(recipe)


def prepare_distributed_certificate_v2(
    *,
    decision_state: object,
    central_certificate_state: object,
    membership_state: object,
    epoch_state: object,
    proposal_state: object,
    witness_state: object,
    manifest: ScopedProtocolManifestV2,
    trusted_verifier: DistributedWitnessAttestationVerifierV2,
    certificate_ref: str,
    provenance_ref: str,
    mutation_ref: str,
    mutation_issuer_ref: str,
    current_step: int,
    parent_state: object | None = None,
) -> tuple[DistributedAdvanceRequestV2, VerifiedDistributedAdvanceSourceV2]:
    recipe = _CertificateRecipeV2(
        decision_state=decision_state,
        central_certificate_state=central_certificate_state,
        membership_state=membership_state,
        epoch_state=epoch_state,
        proposal_state=proposal_state,
        witness_state=witness_state,
        parent_state=parent_state,
        manifest=manifest,
        trusted_verifier=trusted_verifier,
        certificate_ref=certificate_ref,
        provenance_ref=provenance_ref,
        mutation_ref=mutation_ref,
        mutation_issuer_ref=mutation_issuer_ref,
        current_step=current_step,
    )
    return _prepared(recipe)


def verify_distributed_source_v2(
    request: DistributedAdvanceRequestV2,
    *,
    source: object,
    committed_parent_snapshot: DistributedLaneSnapshotV2 | None,
) -> DistributedLaneSnapshotV2:
    stored_request, recipe = _verified_source_material_v2(source)
    if stored_request.to_dict() != request.to_dict():
        raise ValueError("distributed source request is mismatched")
    rebuilt = _build_recipe_v2(recipe)
    if rebuilt.snapshot.to_dict() != request.snapshot.to_dict():
        raise ValueError("distributed source replacement changed")
    if (committed_parent_snapshot is None) != (request.parent_revision == 0):
        raise ValueError("distributed committed parent presence is mismatched")
    if committed_parent_snapshot is not None and (
        rebuilt.snapshot.parent_snapshot_root != committed_parent_snapshot.snapshot_root
        or rebuilt.snapshot.parent_transition_id
        != committed_parent_snapshot.transition_id
        or rebuilt.snapshot.parent_revision != committed_parent_snapshot.revision
    ):
        raise ValueError("distributed source parent is mismatched")
    return rebuilt.snapshot


def _prepared(
    recipe: _RecipeV2,
) -> tuple[DistributedAdvanceRequestV2, VerifiedDistributedAdvanceSourceV2]:
    request = _build_recipe_v2(recipe)
    source = object.__new__(VerifiedDistributedAdvanceSourceV2)
    object.__setattr__(
        source, "_request", DistributedAdvanceRequestV2.from_dict(request.to_dict())
    )
    object.__setattr__(source, "_recipe", recipe)
    object.__setattr__(source, "_anchor_root", request.request_root)
    object.__setattr__(source, "_self_anchor", source)
    object.__setattr__(source, "_token", _SOURCE_TOKEN_V2)
    return request, source


def _verified_source_material_v2(
    source: object,
) -> tuple[DistributedAdvanceRequestV2, _RecipeV2]:
    if type(source) is not VerifiedDistributedAdvanceSourceV2:
        raise TypeError("distributed source has wrong exact type")
    try:
        request = object.__getattribute__(source, "_request")
        recipe = object.__getattribute__(source, "_recipe")
        anchor = object.__getattribute__(source, "_anchor_root")
        self_anchor = object.__getattribute__(source, "_self_anchor")
        token = object.__getattribute__(source, "_token")
    except AttributeError as exc:
        raise TypeError("distributed source is incomplete") from exc
    if (
        type(request) is not DistributedAdvanceRequestV2
        or token is not _SOURCE_TOKEN_V2
        or self_anchor is not source
    ):
        raise TypeError("distributed source authority token is invalid")
    if request.request_root != anchor or type(recipe) not in _RECIPE_TYPES:
        raise ValueError("distributed source anchor is mismatched")
    return request, cast(_RecipeV2, recipe)


__all__ = [
    "VerifiedDistributedAdvanceSourceV2",
    "prepare_distributed_certificate_v2",
    "prepare_distributed_epoch_v2",
    "prepare_distributed_proposal_v2",
    "prepare_distributed_witness_v2",
    "prepare_distributed_witness_conflict_observation_v2",
]
