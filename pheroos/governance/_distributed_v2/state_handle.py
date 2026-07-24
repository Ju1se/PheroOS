"""Opaque rehydrated distributed lane states and neutral finality adapter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import NoReturn, SupportsIndex, cast, final

from pheroos.protocol.authority_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceReadPreconditionV2,
)

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance._authority_session_v2.operations import (
    _canonical_commit_view_v2,
)
from pheroos.governance._commit_finality_v2 import (
    CommitFinalityOwnerV2,
    CommitFinalityProjectionV2,
    CommitFinalityStatusV2,
    VerifiedCommitFinalityInputV2,
    _issue_verified_commit_finality_input_v2,
)
from pheroos.governance._distributed_v2.authority_context import (
    _distributed_authority_context_v2,
    _distributed_value_v2,
)
from pheroos.governance._distributed_v2.enums import DistributedLaneV2
from pheroos.governance._distributed_v2.lane_states import (
    DistributedCertificateStateV2,
    DistributedEpochStateV2,
    DistributedProposalStateV2,
    DistributedWitnessStateV2,
)
from pheroos.governance._distributed_v2.request import DistributedAdvanceRequestV2
from pheroos.governance._distributed_v2.state_contracts import (
    DistributedLaneSnapshotV2,
)
from pheroos.governance._distributed_v2.state_records import (
    _decode_committed_distributed_view_v2,
    _head_from_view_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
)


@dataclass(frozen=True, slots=True)
class _DistributedStateMaterialV2:
    domain: AuthorityDomainV2
    reader: GovernanceStateReaderV2
    request: DistributedAdvanceRequestV2
    snapshot: DistributedLaneSnapshotV2
    view: GovernanceCommitViewV2
    head: GovernanceHeadV2


class VerifiedDistributedStateV2:
    """Public opaque base for one Store-verified fixed-lane state handle."""

    __slots__ = ()

    def __new__(cls, *_args: object, **_kwargs: object) -> VerifiedDistributedStateV2:
        raise TypeError("VerifiedDistributedStateV2 cannot be constructed")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("verified distributed state is immutable")

    def __copy__(self) -> VerifiedDistributedStateV2:
        _verified_distributed_state_material_v2(self)
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> VerifiedDistributedStateV2:
        _verified_distributed_state_material_v2(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("verified distributed state is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("verified distributed state is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("verified distributed state is not portable")

    def __repr__(self) -> str:
        return f"<{type(self).__name__} redacted>"

    @property
    def snapshot(self) -> DistributedLaneSnapshotV2:
        return DistributedLaneSnapshotV2.from_dict(
            _verified_distributed_state_material_v2(self).snapshot.to_dict()
        )

    @property
    def stream_ref(self) -> str:
        return _verified_distributed_state_material_v2(self).snapshot.stream_ref

    @property
    def transition_id(self) -> str:
        return _verified_distributed_state_material_v2(self).snapshot.transition_id

    @property
    def receipt_root(self) -> str:
        material = _verified_distributed_state_material_v2(self)
        assert material.view.committed_transition is not None
        return material.view.committed_transition.receipt.receipt_root

    @property
    def position(self) -> GovernanceCommitPositionV2:
        material = _verified_distributed_state_material_v2(self)
        assert material.view.position_observation is not None
        return material.view.position_observation.position


@final
class VerifiedDistributedEpochStateV2(VerifiedDistributedStateV2):
    __slots__ = ("_domain", "_reader", "_receipt_root", "_request")

    def __new__(
        cls, *_args: object, **_kwargs: object
    ) -> VerifiedDistributedEpochStateV2:
        raise TypeError("VerifiedDistributedEpochStateV2 cannot be constructed")


@final
class VerifiedDistributedProposalStateV2(VerifiedDistributedStateV2):
    __slots__ = ("_domain", "_reader", "_receipt_root", "_request")

    def __new__(
        cls, *_args: object, **_kwargs: object
    ) -> VerifiedDistributedProposalStateV2:
        raise TypeError("VerifiedDistributedProposalStateV2 cannot be constructed")


@final
class VerifiedDistributedWitnessStateV2(VerifiedDistributedStateV2):
    __slots__ = ("_domain", "_reader", "_receipt_root", "_request")

    def __new__(
        cls, *_args: object, **_kwargs: object
    ) -> VerifiedDistributedWitnessStateV2:
        raise TypeError("VerifiedDistributedWitnessStateV2 cannot be constructed")


@final
class VerifiedDistributedCertificateStateV2(VerifiedDistributedStateV2):
    __slots__ = ("_domain", "_reader", "_receipt_root", "_request")

    def __new__(
        cls, *_args: object, **_kwargs: object
    ) -> VerifiedDistributedCertificateStateV2:
        raise TypeError("VerifiedDistributedCertificateStateV2 cannot be constructed")


def rehydrate_distributed_state_v2(
    payload: object,
    *,
    domain: AuthorityDomainV2,
    state_reader: GovernanceStateReaderV2,
) -> VerifiedDistributedStateV2:
    _require_domain(domain)
    _require_reader(state_reader)
    request = _request_from_portable(payload)
    if (
        request.domain_root != domain.domain_root
        or request.scope_ref != domain.scope_ref
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH, "/domain_root"
        )
    material = _load_verified_material(
        state_reader, domain, request, expected_receipt_root=None
    )
    assert material.view.committed_transition is not None
    return _make_state(
        request.snapshot.lane,
        state_reader,
        domain,
        request,
        material.view.committed_transition.receipt.receipt_root,
    )


def require_current_distributed_state_v2(
    state: object,
) -> DistributedLaneSnapshotV2:
    material = _verified_distributed_state_material_v2(state)
    if (
        material.view.position_observation is None
        or material.view.position_observation.position
        is not GovernanceCommitPositionV2.CURRENT
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE, "/position"
        )
    return DistributedLaneSnapshotV2.from_dict(material.snapshot.to_dict())


def distributed_state_is_current_v2(state: object) -> bool:
    try:
        require_current_distributed_state_v2(state)
    except Exception:
        return False
    return True


def _verified_distributed_state_material_v2(
    state: object,
) -> _DistributedStateMaterialV2:
    lane = _lane_for_handle(state)
    try:
        reader = object.__getattribute__(state, "_reader")
        domain = object.__getattribute__(state, "_domain")
        request = object.__getattribute__(state, "_request")
        receipt_root = object.__getattribute__(state, "_receipt_root")
    except AttributeError as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, ""
        ) from exc
    _require_domain(domain)
    _require_reader(reader)
    if (
        type(request) is not DistributedAdvanceRequestV2
        or type(receipt_root) is not str
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/request_root"
        )
    material = _load_verified_material(
        cast(GovernanceStateReaderV2, reader),
        cast(AuthorityDomainV2, domain),
        DistributedAdvanceRequestV2.from_dict(request.to_dict()),
        expected_receipt_root=receipt_root,
    )
    if material.snapshot.lane is not lane:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/lane"
        )
    return material


def _load_verified_material(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: DistributedAdvanceRequestV2,
    *,
    expected_receipt_root: str | None,
) -> _DistributedStateMaterialV2:
    try:
        view = _canonical_commit_view_v2(
            reader.load_commit_view_v2(
                request.scope_ref,
                request.stream_ref,
                request.transition_id,
                expected_receipt_root=expected_receipt_root,
            )
        )
    except Exception as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/transition_id",
        ) from exc
    if view.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
            "/transition_id",
        )
    try:
        committed, snapshot, _ = _decode_committed_distributed_view_v2(
            view, domain, reader=reader
        )
        head = _head_from_view_v2(view, domain)
    except Exception as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/transition_id",
        ) from exc
    if committed.to_dict() != request.to_dict():
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/request_root"
        )
    return _DistributedStateMaterialV2(
        domain=AuthorityDomainV2.from_dict(domain.to_dict()),
        reader=reader,
        request=committed,
        snapshot=snapshot,
        view=view,
        head=head,
    )


def _verified_distributed_commit_finality_input_v2(
    certificate_state: object,
    *,
    proposal_state: object,
    witness_state: object,
    epoch_state: object,
    sealed_decision_state: object,
    central_certificate_state: object,
    membership_state: object,
    manifest: object,
    current_step: int,
) -> VerifiedCommitFinalityInputV2:
    certificate = _current_lane(certificate_state, DistributedLaneV2.CERTIFICATE)
    proposal = _current_lane(proposal_state, DistributedLaneV2.PROPOSAL)
    witness = _current_lane(witness_state, DistributedLaneV2.WITNESS)
    epoch = _current_lane(epoch_state, DistributedLaneV2.EPOCH)
    from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2

    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("distributed finality requires exact scoped manifest")
    context = _distributed_authority_context_v2(
        decision_state=sealed_decision_state,
        central_certificate_state=central_certificate_state,
        membership_state=membership_state,
        manifest=manifest,
        current_step=current_step,
    )
    value = _distributed_value_v2(context)
    status, reasons = _finality_status(
        certificate.snapshot,
        proposal.snapshot,
        witness.snapshot,
        epoch.snapshot,
        semantic_value_root=value.semantic_value_root,
        current_step=current_step,
    )
    assert certificate.view.committed_transition is not None
    receipt = certificate.view.committed_transition.receipt
    inclusion = certificate.view.committed_transition.inclusion_proof
    decision = context.decision
    projection = CommitFinalityProjectionV2(
        owner=CommitFinalityOwnerV2.DISTRIBUTED,
        status=status,
        stream_ref=certificate.snapshot.stream_ref,
        revision=certificate.snapshot.revision,
        transition_id=certificate.snapshot.transition_id,
        snapshot_root=certificate.snapshot.snapshot_root,
        head_root=certificate.head.head_root,
        receipt_root=receipt.receipt_root,
        seal_transition_id=decision.seal_inclusion.transition_id,
        seal_root=decision.seal_inclusion.seal_root,
        frozen_dependency_root=decision.seal_inclusion.frozen_dependency_root,
        verified_at_step=current_step,
        reason_codes=reasons,
    )
    return _issue_verified_commit_finality_input_v2(
        projection=projection,
        owner_precondition=GovernanceReadPreconditionV2(
            stream_ref=certificate.head.stream_ref,
            expected_revision=certificate.head.revision,
            expected_root=certificate.head.head_root,
        ),
        owner_receipt_root=receipt.receipt_root,
        owner_inclusion_root=inclusion.inclusion_root,
    )


def verified_distributed_commit_finality_input_v2(
    certificate_state: object,
    *,
    proposal_state: object,
    witness_state: object,
    epoch_state: object,
    sealed_decision_state: object,
    central_certificate_state: object,
    membership_state: object,
    manifest: object,
    current_step: int,
) -> VerifiedCommitFinalityInputV2:
    """Public high-level adapter; return value remains opaque and store-bound."""

    return _verified_distributed_commit_finality_input_v2(
        certificate_state,
        proposal_state=proposal_state,
        witness_state=witness_state,
        epoch_state=epoch_state,
        sealed_decision_state=sealed_decision_state,
        central_certificate_state=central_certificate_state,
        membership_state=membership_state,
        manifest=manifest,
        current_step=current_step,
    )


def _finality_status(
    certificate_snapshot: DistributedLaneSnapshotV2,
    proposal_snapshot: DistributedLaneSnapshotV2,
    witness_snapshot: DistributedLaneSnapshotV2,
    epoch_snapshot: DistributedLaneSnapshotV2,
    *,
    semantic_value_root: str,
    current_step: int,
) -> tuple[CommitFinalityStatusV2, tuple[str, ...]]:
    certificate = certificate_snapshot.state
    proposal = proposal_snapshot.state
    witness = witness_snapshot.state
    epoch = epoch_snapshot.state
    if (
        type(certificate) is not DistributedCertificateStateV2
        or type(proposal) is not DistributedProposalStateV2
        or type(witness) is not DistributedWitnessStateV2
        or type(epoch) is not DistributedEpochStateV2
    ):
        raise TypeError("distributed finality lane state is invalid")
    if certificate.frozen or witness.frozen:
        return CommitFinalityStatusV2.CONFLICT, ("distributed_epoch_frozen",)
    current_epoch = epoch.transition_certificate.to_epoch
    if not (
        certificate.epoch == proposal.epoch == witness.epoch == current_epoch
        and any(
            item.value.semantic_value_root == semantic_value_root
            for item in certificate.certificates
        )
    ):
        return CommitFinalityStatusV2.UNAVAILABLE, ("distributed_value_unavailable",)
    certified = tuple(
        item
        for item in certificate.certificates
        if item.value.semantic_value_root == semantic_value_root
    )
    proposal_digests = {item.proposal_digest for item in proposal.proposals}
    witness_roots = {item.witness_root for item in witness.witnesses}
    if not certified or any(
        any(digest not in proposal_digests for digest in item.proposal_digests)
        or any(
            signed.witness_root not in witness_roots
            or not signed.witnessed_at_step <= current_step < signed.expires_at_step
            for signed in item.witnesses
        )
        for item in certified
    ):
        return CommitFinalityStatusV2.UNAVAILABLE, ("distributed_proof_stale",)
    return CommitFinalityStatusV2.VERIFIED, ("distributed_quorum_verified",)


def _current_lane(
    state: object, lane: DistributedLaneV2
) -> _DistributedStateMaterialV2:
    material = _verified_distributed_state_material_v2(state)
    if (
        material.snapshot.lane is not lane
        or material.view.position_observation is None
        or material.view.position_observation.position
        is not GovernanceCommitPositionV2.CURRENT
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE, "/position"
        )
    return material


def _lane_for_handle(state: object) -> DistributedLaneV2:
    exact = type(state)
    for handle_type, lane in _LANE_BY_HANDLE.items():
        if exact is handle_type:
            return lane
    raise GovernanceAuthorityBindingErrorV2(
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, ""
    )


def _make_state(
    lane: DistributedLaneV2,
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: DistributedAdvanceRequestV2,
    receipt_root: str,
) -> VerifiedDistributedStateV2:
    handle_type = _HANDLE_BY_LANE[lane]
    state = object.__new__(handle_type)
    object.__setattr__(state, "_reader", reader)
    object.__setattr__(state, "_domain", AuthorityDomainV2.from_dict(domain.to_dict()))
    object.__setattr__(
        state, "_request", DistributedAdvanceRequestV2.from_dict(request.to_dict())
    )
    object.__setattr__(state, "_receipt_root", receipt_root)
    return state


def _request_from_portable(value: object) -> DistributedAdvanceRequestV2:
    if type(value) is DistributedAdvanceRequestV2:
        value = value.to_dict()
    try:
        return DistributedAdvanceRequestV2.from_dict(value)
    except (TypeError, ValueError) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/request_root"
        ) from exc


def _require_domain(value: object) -> None:
    if type(value) is not AuthorityDomainV2:
        raise TypeError("distributed state requires exact AuthorityDomainV2")


def _require_reader(value: object) -> None:
    try:
        valid = isinstance(value, GovernanceStateReaderV2)
    except Exception as exc:
        raise TypeError("distributed state requires StateReader v2") from exc
    if not valid:
        raise TypeError("distributed state requires StateReader v2")


_HANDLE_BY_LANE: Mapping[DistributedLaneV2, type[VerifiedDistributedStateV2]] = (
    MappingProxyType(
        {
            DistributedLaneV2.EPOCH: VerifiedDistributedEpochStateV2,
            DistributedLaneV2.PROPOSAL: VerifiedDistributedProposalStateV2,
            DistributedLaneV2.WITNESS: VerifiedDistributedWitnessStateV2,
            DistributedLaneV2.CERTIFICATE: VerifiedDistributedCertificateStateV2,
        }
    )
)
_LANE_BY_HANDLE: Mapping[type[VerifiedDistributedStateV2], DistributedLaneV2] = (
    MappingProxyType({value: key for key, value in _HANDLE_BY_LANE.items()})
)


__all__ = [
    "VerifiedDistributedCertificateStateV2",
    "VerifiedDistributedEpochStateV2",
    "VerifiedDistributedProposalStateV2",
    "VerifiedDistributedStateV2",
    "VerifiedDistributedWitnessStateV2",
    "distributed_state_is_current_v2",
    "rehydrate_distributed_state_v2",
    "require_current_distributed_state_v2",
    "verified_distributed_commit_finality_input_v2",
]
