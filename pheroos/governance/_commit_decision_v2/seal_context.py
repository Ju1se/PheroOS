"""Opaque Store-verified seal authority consumed by finality owners."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn, SupportsIndex, final

from pheroos.protocol.authority_v2 import GovernanceReadPreconditionV2

from pheroos.governance._authority_session_v2.operations import (
    _canonical_commit_view_v2,
)
from pheroos.governance._commit_decision_v2.enums import (
    CommitDecisionMutationKindV2,
)
from pheroos.governance._commit_decision_v2.seal_inclusion import (
    CommitDecisionSealInclusionV2,
)
from pheroos.governance._commit_decision_v2.snapshot import CommitDecisionSnapshotV2
from pheroos.governance._commit_decision_v2.state_handle import (
    VerifiedCommitDecisionStateV2,
    _verified_state_view_v2,
)
from pheroos.governance._commit_decision_v2.state_records import _head_from_view_v2
from pheroos.governance._commit_decision_v2.state_records import (
    _decode_committed_decision_view_v2,
    _validate_successor,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitPositionV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
)


@dataclass(frozen=True, slots=True)
class _CommitDecisionSealContextMaterialV2:
    domain: AuthorityDomainV2
    reader: GovernanceStateReaderV2
    snapshot: CommitDecisionSnapshotV2
    seal_inclusion: CommitDecisionSealInclusionV2
    current_inclusion: CommitDecisionSealInclusionV2
    decision_precondition: GovernanceReadPreconditionV2
    decision_head: GovernanceHeadV2


@final
class _VerifiedCommitDecisionSealContextV2:
    __slots__ = ("_anchor_root", "_state")

    def __new__(
        cls, *_args: object, **_kwargs: object
    ) -> _VerifiedCommitDecisionSealContextV2:
        raise TypeError("verified commit decision seal context cannot be constructed")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("verified commit decision seal context is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("verified commit decision seal context is immutable")

    def __copy__(self) -> _VerifiedCommitDecisionSealContextV2:
        _verified_commit_decision_seal_context_material_v2(self)
        return self

    def __deepcopy__(
        self, _memo: dict[int, object]
    ) -> _VerifiedCommitDecisionSealContextV2:
        _verified_commit_decision_seal_context_material_v2(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("verified commit decision seal context is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("verified commit decision seal context is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("verified commit decision seal context is not portable")

    def __repr__(self) -> str:
        return "<_VerifiedCommitDecisionSealContextV2 redacted>"


def _verified_commit_decision_seal_context_v2(
    state: object,
) -> _VerifiedCommitDecisionSealContextV2:
    material = _seal_material_v2(state)
    context = object.__new__(_VerifiedCommitDecisionSealContextV2)
    object.__setattr__(context, "_state", state)
    object.__setattr__(
        context,
        "_anchor_root",
        material.current_inclusion.projection_root,
    )
    return context


def _verified_commit_decision_seal_context_material_v2(
    context: object,
) -> _CommitDecisionSealContextMaterialV2:
    if type(context) is not _VerifiedCommitDecisionSealContextV2:
        raise TypeError("commit decision seal context has the wrong exact type")
    try:
        state = object.__getattribute__(context, "_state")
        anchor_root = object.__getattribute__(context, "_anchor_root")
    except AttributeError as exc:
        raise TypeError("commit decision seal context is incomplete") from exc
    material = _seal_material_v2(state)
    if material.current_inclusion.projection_root != anchor_root:
        raise ValueError("commit decision seal context anchor is mismatched")
    return material


def _seal_material_v2(state: object) -> _CommitDecisionSealContextMaterialV2:
    if type(state) is not VerifiedCommitDecisionStateV2:
        raise TypeError("commit decision seal context requires verified state")
    _, snapshot, view = _verified_state_view_v2(state)
    if (
        view.position_observation is None
        or view.position_observation.position is not GovernanceCommitPositionV2.CURRENT
        or view.committed_transition is None
        or snapshot.seal is None
        or snapshot.outcome is not None
    ):
        raise ValueError("commit decision seal must be current and non-terminal")
    domain = object.__getattribute__(state, "_domain")
    reader = object.__getattribute__(state, "_reader")
    if type(domain) is not AuthorityDomainV2:
        raise TypeError("commit decision seal domain is invalid")
    if not isinstance(reader, GovernanceStateReaderV2):
        raise TypeError("commit decision seal reader is invalid")
    head = _head_from_view_v2(view, (domain))
    current_inclusion = _inclusion_v2(snapshot, view)
    sealed_snapshot, sealed_view = _sealed_transition_v2(
        snapshot,
        view,
        domain=(domain),
        reader=(reader),
    )
    seal_inclusion = _inclusion_v2(sealed_snapshot, sealed_view)
    if seal_inclusion.seal_root != current_inclusion.seal_root:
        raise ValueError("commit decision current seal lineage is mismatched")
    return _CommitDecisionSealContextMaterialV2(
        domain=(domain),
        reader=(reader),
        snapshot=CommitDecisionSnapshotV2.from_dict(snapshot.to_dict()),
        seal_inclusion=seal_inclusion,
        current_inclusion=current_inclusion,
        decision_precondition=GovernanceReadPreconditionV2(
            stream_ref=head.stream_ref,
            expected_revision=head.revision,
            expected_root=head.head_root,
        ),
        decision_head=GovernanceHeadV2.from_dict(head.to_dict()),
    )


def _inclusion_v2(
    snapshot: CommitDecisionSnapshotV2,
    view: object,
) -> CommitDecisionSealInclusionV2:
    from pheroos.governance.authority_store_v2 import GovernanceCommitViewV2

    if type(view) is not GovernanceCommitViewV2 or view.committed_transition is None:
        raise TypeError("commit decision seal view is invalid")
    if snapshot.seal is None:
        raise ValueError("commit decision seal snapshot is unsealed")
    receipt = view.committed_transition.receipt
    proof = view.committed_transition.inclusion_proof
    return CommitDecisionSealInclusionV2(
        stream_ref=snapshot.stream_ref,
        revision=snapshot.revision,
        transition_id=snapshot.transition_id,
        snapshot_root=snapshot.snapshot_root,
        receipt_root=receipt.receipt_root,
        head_root=receipt.head_root,
        inclusion_root=proof.inclusion_root,
        seal_root=snapshot.seal.seal_root,
        frozen_dependency_root=snapshot.seal.frozen_dependency_root,
    )


def _sealed_transition_v2(
    snapshot: CommitDecisionSnapshotV2,
    view: object,
    *,
    domain: AuthorityDomainV2,
    reader: GovernanceStateReaderV2,
) -> tuple[CommitDecisionSnapshotV2, object]:
    current_snapshot = snapshot
    current_view = view
    while current_snapshot.mutation_kind is not CommitDecisionMutationKindV2.SEALED:
        if current_snapshot.parent_revision == 0:
            raise ValueError("commit decision seal transition is unavailable")
        parent_view = _canonical_commit_view_v2(
            reader.load_commit_view_v2(
                current_snapshot.scope_ref,
                current_snapshot.stream_ref,
                current_snapshot.parent_transition_id,
            )
        )
        _, parent_snapshot, _ = _decode_committed_decision_view_v2(
            parent_view,
            domain,
            reader=None,
        )
        _validate_successor(current_snapshot, parent_snapshot)
        if (
            parent_snapshot.seal is None
            or snapshot.seal is None
            or parent_snapshot.seal.seal_root != snapshot.seal.seal_root
        ):
            raise ValueError("commit decision seal lineage changed before finality")
        current_snapshot = parent_snapshot
        current_view = parent_view
    return current_snapshot, current_view


__all__: tuple[str, ...] = ()
