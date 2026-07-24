"""Non-portable source proof for the durable Support v2 ledger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, SupportsIndex, cast, final

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.authority_v2 import GovernanceReadPreconditionV2

from pheroos.governance._support_v2.support_lease_contracts import (
    SupportLeaseProposalV2,
    SupportLeaseV2,
    SupportObservationV2,
)
from pheroos.governance._support_v2.support_source_binding import (
    _SupportSourceBindingV2,
    _source_binding_from_request,
    _source_roots_from_request,
)
from pheroos.governance._support_v2.support_projection import (
    _validate_transition_delta,
)
from pheroos.governance._support_v2.support_state_access import (
    _membership_parent,
    _support_parent,
)
from pheroos.governance._support_v2.support_state_contracts import (
    SupportAdvanceRequestV2,
    SupportMutationKindV2,
    SupportSnapshotV2,
)
from pheroos.governance._support_v2.support_verification import (
    _validate_request_manifest_context_v2,
    _validated_support_manifest_context_v2,
    active_support_lease_from_parent_v2,
    project_support_lease_v2,
    project_support_revocation_v2,
)


@final
class VerifiedSupportSourceV2:
    """Non-authoritative proof over current Store state and detached assertions."""

    __slots__ = (
        "_binding",
        "_manifest",
        "_membership_state",
        "_observations",
        "_parent_state",
        "_proposal",
        "_request",
    )

    def __new__(cls, *_args: object, **_kwargs: object) -> VerifiedSupportSourceV2:
        raise TypeError("VerifiedSupportSourceV2 cannot be constructed directly")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedSupportSourceV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedSupportSourceV2 is immutable")

    def __copy__(self) -> VerifiedSupportSourceV2:
        _verified_source(self)
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> VerifiedSupportSourceV2:
        _verified_source(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedSupportSourceV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedSupportSourceV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("VerifiedSupportSourceV2 is not portable")

    def __repr__(self) -> str:
        return "<VerifiedSupportSourceV2 redacted>"

    @property
    def context_root(self) -> str:
        return _verified_source(self).binding.context_root


@dataclass(frozen=True, slots=True)
class _VerifiedSupportMaterialV2:
    """One ephemeral, fully checked source view for a single operation."""

    request: SupportAdvanceRequestV2
    binding: _SupportSourceBindingV2
    manifest: ScopedProtocolManifestV2
    parent_precondition: GovernanceReadPreconditionV2 | None
    membership_precondition: GovernanceReadPreconditionV2 | None

    def __reduce__(self) -> NoReturn:
        raise TypeError("verified support material is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("verified support material is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("verified support material is not portable")


def _issue_source(
    *,
    request: SupportAdvanceRequestV2,
    manifest: ScopedProtocolManifestV2,
    parent_state: object = None,
    membership_state: object = None,
    proposal: object = None,
    observations: object = None,
) -> VerifiedSupportSourceV2:
    binding = _source_binding_from_request(request)
    detached_proposal = (
        None
        if proposal is None
        else SupportLeaseProposalV2.from_dict(
            cast(SupportLeaseProposalV2, proposal).to_dict()
        )
    )
    detached_observations = (
        None
        if observations is None
        else tuple(
            SupportObservationV2.from_dict(item.to_dict())
            for item in cast(tuple[SupportObservationV2, ...], observations)
        )
    )
    source = object.__new__(VerifiedSupportSourceV2)
    for name, value in (
        ("_binding", binding),
        ("_manifest", ScopedProtocolManifestV2.from_dict(manifest.to_dict())),
        ("_request", SupportAdvanceRequestV2.from_dict(request.to_dict())),
        ("_parent_state", parent_state),
        ("_membership_state", membership_state),
        ("_proposal", detached_proposal),
        ("_observations", detached_observations),
    ):
        object.__setattr__(source, name, value)
    return source


def _verified_source(
    source: object,
) -> _VerifiedSupportMaterialV2:
    if type(source) is not VerifiedSupportSourceV2:
        raise TypeError("support source proof is invalid")
    try:
        binding = object.__getattribute__(source, "_binding")
        manifest = object.__getattribute__(source, "_manifest")
        request = object.__getattribute__(source, "_request")
        parent_state = object.__getattribute__(source, "_parent_state")
        membership_state = object.__getattribute__(source, "_membership_state")
        proposal = object.__getattribute__(source, "_proposal")
        observations = object.__getattribute__(source, "_observations")
    except AttributeError as exc:
        raise TypeError("support source proof is incomplete") from exc
    if (
        type(binding) is not _SupportSourceBindingV2
        or type(manifest) is not ScopedProtocolManifestV2
        or type(request) is not SupportAdvanceRequestV2
    ):
        raise TypeError("support source proof shape is invalid")
    parent_precondition, membership_precondition = _validate_source_upstreams(
        request,
        manifest=manifest,
        parent_state=parent_state,
        membership_state=membership_state,
        proposal=proposal,
        observations=observations,
    )
    expected_binding = _source_binding_from_request(request)
    if binding != expected_binding:
        raise ValueError("support source roots are mismatched")
    return _VerifiedSupportMaterialV2(
        request=SupportAdvanceRequestV2.from_dict(request.to_dict()),
        binding=binding,
        manifest=ScopedProtocolManifestV2.from_dict(manifest.to_dict()),
        parent_precondition=parent_precondition,
        membership_precondition=membership_precondition,
    )


def _validate_source_upstreams(
    request: SupportAdvanceRequestV2,
    *,
    manifest: object,
    parent_state: object,
    membership_state: object,
    proposal: object,
    observations: object,
) -> tuple[
    GovernanceReadPreconditionV2 | None,
    GovernanceReadPreconditionV2 | None,
]:
    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("support source manifest is invalid")
    context = _validated_support_manifest_context_v2(
        manifest,
        profile=request.snapshot.profile,
        target_ref=request.snapshot.target_ref,
    )
    _validate_request_manifest_context_v2(request, context)
    kind = request.mutation_kind
    if kind is SupportMutationKindV2.INITIALIZE:
        if any(
            item is not None
            for item in (
                parent_state,
                membership_state,
                proposal,
                observations,
            )
        ):
            raise ValueError("support initialize source contains undeclared upstreams")
        return None, None
    parent, parent_precondition = _support_parent(parent_state)
    if parent.snapshot_root != request.snapshot.parent_snapshot_root:
        raise ValueError("support source parent is mismatched or stale")
    _validate_transition_delta(request, parent)
    revoked_prior = None
    if kind in (SupportMutationKindV2.REVOKE, SupportMutationKindV2.SWITCH):
        revoked_prior = _validate_revocation_projection(request, parent)
    if kind is SupportMutationKindV2.REVOKE:
        if any(item is not None for item in (membership_state, proposal, observations)):
            raise ValueError("support revoke source contains caller lease material")
        return parent_precondition, None
    membership, membership_precondition = _membership_parent(membership_state)
    lease = request.issued_lease
    if lease is None:
        raise ValueError("support issuance source has no issued lease material")
    rebuilt = project_support_lease_v2(
        parent=parent,
        membership=membership,
        proposal=cast(SupportLeaseProposalV2, proposal),
        positive_observations=cast(tuple[SupportObservationV2, ...], observations),
        manifest=context.manifest,
        mutation_transition_id=request.transition_id,
        issuance_issuer_ref=lease.issuance_issuer_ref,
        current_step=request.snapshot.current_step,
        prior_lease=revoked_prior,
        issuance_provenance_root=lease.issuance_provenance_root,
        issuance_trace_roots=tuple(lease.issuance_trace_roots),
    )
    if rebuilt.to_dict() != lease.to_dict():
        raise ValueError("support source issuance projection is mismatched")
    return parent_precondition, membership_precondition


def _validate_revocation_projection(
    request: SupportAdvanceRequestV2,
    parent: SupportSnapshotV2,
) -> SupportLeaseV2:
    prior = active_support_lease_from_parent_v2(
        parent,
        request.revoked_lease_root,
        current_step=request.snapshot.current_step,
    )
    committed = request.revocation
    recorded_prior = request.revoked_lease
    if committed is None or recorded_prior is None:
        raise ValueError("support revocation source has incomplete mutation material")
    if recorded_prior.to_dict() != prior.to_dict():
        raise ValueError("support revoked lease record does not match its parent")
    rebuilt = project_support_revocation_v2(
        prior,
        mutation_transition_id=request.transition_id,
        reason_codes=tuple(committed.reason_codes),
        revocation_issuer_ref=committed.revocation_issuer_ref,
        current_step=request.snapshot.current_step,
        provenance_root=committed.provenance_root,
        source_trace_roots=tuple(committed.source_trace_roots),
    )
    if rebuilt.to_dict() != committed.to_dict():
        raise ValueError("support source revocation projection is mismatched")
    return prior


def verify_support_request_source_v2(
    request: SupportAdvanceRequestV2, *, source: object
) -> GovernanceReadPreconditionV2 | None:
    if type(request) is not SupportAdvanceRequestV2:
        raise TypeError("support source verification requires exact request v2")
    material = _verified_source(source)
    if material.request.to_dict() != request.to_dict():
        raise ValueError("support source belongs to another request")
    return material.membership_precondition


def _verified_source_manifest_v2(source: object) -> ScopedProtocolManifestV2:
    return _verified_source(source).manifest


def _expected_source_roots(
    request: SupportAdvanceRequestV2,
    source: VerifiedSupportSourceV2,
) -> tuple[
    str,
    str,
    GovernanceReadPreconditionV2 | None,
    GovernanceReadPreconditionV2 | None,
]:
    material = _verified_source(source)
    if material.request.to_dict() != request.to_dict():
        raise ValueError("support source belongs to another request")
    return (
        material.binding.context_root,
        material.binding.source_verification_root,
        material.parent_precondition,
        material.membership_precondition,
    )


def _expected_source_roots_from_request(
    request: SupportAdvanceRequestV2,
) -> tuple[str, str]:
    return _source_roots_from_request(request)


__all__: tuple[str, ...] = ()
