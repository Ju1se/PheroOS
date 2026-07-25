"""Opaque, Store-reverified Commit Evidence v2 state and Decision adapter."""

from __future__ import annotations

from typing import NoReturn, SupportsIndex, cast, final

from pheroos.protocol.authority_v2 import (
    AuthorityDiagnosticCodeV2,
)

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance._commit_evidence_owner_v2.contracts import (
    CommitEvidenceAdvanceRequestV2,
    CommitEvidenceSnapshotV2,
)
from pheroos.governance._commit_evidence_owner_v2.state_verification import (
    _load_verified_request_view,
)
from pheroos.governance._commit_evidence_projection_v2.projection import (
    CommitEvidenceProjectionV2,
)
from pheroos.governance._commit_evidence_projection_v2.records import (
    CommitEvidenceKindV2,
    CommitEvidenceStatusV2,
    QualifiedCommitEvidenceV2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
)


@final
class VerifiedCommitEvidenceStateV2:
    """Opaque Evidence state whose observations reverify Store history."""

    __slots__ = ("_domain", "_reader", "_receipt_root", "_request")

    def __new__(
        cls, *_args: object, **_kwargs: object
    ) -> VerifiedCommitEvidenceStateV2:
        raise TypeError("VerifiedCommitEvidenceStateV2 cannot be constructed directly")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedCommitEvidenceStateV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedCommitEvidenceStateV2 is immutable")

    def __copy__(self) -> VerifiedCommitEvidenceStateV2:
        _verified_state_view(self)
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> VerifiedCommitEvidenceStateV2:
        _verified_state_view(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedCommitEvidenceStateV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedCommitEvidenceStateV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("VerifiedCommitEvidenceStateV2 is not portable")

    def __repr__(self) -> str:
        return "<VerifiedCommitEvidenceStateV2 redacted>"

    @property
    def snapshot(self) -> CommitEvidenceSnapshotV2:
        request, _ = _verified_state_view(self)
        return CommitEvidenceSnapshotV2.from_dict(request.snapshot.to_dict())

    @property
    def request_root(self) -> str:
        request, _ = _verified_state_view(self)
        return request.request_root

    @property
    def stream_ref(self) -> str:
        request, _ = _verified_state_view(self)
        return request.stream_ref

    @property
    def transition_id(self) -> str:
        request, _ = _verified_state_view(self)
        return request.transition_id

    @property
    def receipt_root(self) -> str:
        _, view = _verified_state_view(self)
        assert view.committed_transition is not None
        return view.committed_transition.receipt.receipt_root

    @property
    def position(self) -> GovernanceCommitPositionV2:
        _, view = _verified_state_view(self)
        assert view.position_observation is not None
        return view.position_observation.position


def commit_evidence_state_is_current_v2(state: object) -> bool:
    try:
        _verified_current_material(state)
        return True
    except Exception:
        return False


def require_current_commit_evidence_state_v2(
    state: object,
) -> CommitEvidenceSnapshotV2:
    request, _, _ = _verified_current_material(state)
    return CommitEvidenceSnapshotV2.from_dict(request.snapshot.to_dict())


def project_current_commit_evidence_v2(
    state: object,
) -> CommitEvidenceProjectionV2:
    """Return portable data; this projection alone grants no authority."""

    request, view, _ = _verified_current_material(state)
    return _projection_from_material(
        request,
        view,
        current_step=request.snapshot.current_step,
    )


def _projection_from_material(
    request: CommitEvidenceAdvanceRequestV2,
    view: GovernanceCommitViewV2,
    *,
    current_step: int,
) -> CommitEvidenceProjectionV2:
    assert view.committed_transition is not None
    snapshot = request.snapshot
    receipt = view.committed_transition.receipt
    return CommitEvidenceProjectionV2(
        domain_root=snapshot.domain_root,
        scope_ref=snapshot.scope_ref,
        manifest_root=snapshot.manifest_root,
        commit_policy_root=snapshot.commit_policy_root,
        evidence_policy=snapshot.evidence_policy,
        profile=snapshot.profile,
        assurance=snapshot.assurance,
        protocol_ref=snapshot.protocol_ref,
        run_ref=snapshot.run_ref,
        target_ref=snapshot.target_ref,
        epoch=snapshot.epoch,
        current_step=current_step,
        stream_ref=snapshot.stream_ref,
        revision=snapshot.revision,
        transition_id=snapshot.transition_id,
        snapshot_root=snapshot.snapshot_root,
        head_root=receipt.head_root,
        receipt_root=receipt.receipt_root,
        membership_stream_ref=snapshot.membership_stream_ref,
        membership_transition_id=snapshot.membership_transition_id,
        membership_head_root=snapshot.membership_head_root,
        membership_snapshot_root=snapshot.membership_snapshot_root,
        membership_root=snapshot.membership_root,
        verification_stream_ref=snapshot.verification_stream_ref,
        verification_transition_id=snapshot.verification_transition_id,
        verification_head_root=snapshot.verification_head_root,
        verification_snapshot_root=snapshot.verification_snapshot_root,
        verification_set_root=snapshot.verification_set_root,
        records=_records_at_step(snapshot, current_step),
    )


def _records_at_step(
    snapshot: CommitEvidenceSnapshotV2,
    current_step: int,
) -> tuple[QualifiedCommitEvidenceV2, ...]:
    records = tuple(
        item
        for item in snapshot.records
        if item.status is CommitEvidenceStatusV2.ACTIVE
        and item.epoch == snapshot.epoch
        and item.qualification_policy_root == snapshot.evidence_policy.policy_root
        and item.membership_root == snapshot.membership_root
        and item.verification_set_root == snapshot.verification_set_root
        and item.observed_at_step <= current_step < item.expires_at_step
    )
    by_root = {item.attestation_root: item for item in records}
    for item in records:
        related = (
            item.result_observation_roots
            if item.kind is CommitEvidenceKindV2.CHALLENGE
            else item.rebuttal_observation_roots
        )
        if any(root not in by_root for root in related):
            return ()
    return records


def _verified_current_material(
    state: object,
) -> tuple[
    CommitEvidenceAdvanceRequestV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
]:
    request, view = _verified_state_view(state)
    assert view.position_observation is not None
    if view.position_observation.position is not GovernanceCommitPositionV2.CURRENT:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/position",
        )
    reader = cast(GovernanceStateReaderV2, object.__getattribute__(state, "_reader"))
    snapshot = request.snapshot
    for stream, revision, root in (
        (
            snapshot.membership_stream_ref,
            snapshot.membership_revision,
            snapshot.membership_head_root,
        ),
        (
            snapshot.verification_stream_ref,
            snapshot.verification_revision,
            snapshot.verification_head_root,
        ),
    ):
        _require_current_dependency_head(
            reader, request.scope_ref, stream, revision, root
        )
    assert view.committed_transition is not None
    receipt = view.committed_transition.receipt
    head = GovernanceHeadV2(
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        stream_ref=request.stream_ref,
        revision=receipt.revision,
        parent_root=receipt.parent_root,
        state_root=receipt.state_root,
        transition_id=receipt.transition_id,
        batch_root=receipt.batch_root,
        head_root=receipt.head_root,
    )
    return request, view, head


def _require_current_dependency_head(
    reader: GovernanceStateReaderV2,
    scope_ref: str,
    stream_ref: str,
    revision: int,
    root: str,
) -> None:
    try:
        head = reader.load_head_v2(scope_ref, stream_ref)
    except KeyError as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/dependencies",
        ) from exc
    if (
        type(head) is not GovernanceHeadV2
        or head.revision != revision
        or head.head_root != root
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/dependencies",
        )


def _verified_state_view(
    state: object,
) -> tuple[CommitEvidenceAdvanceRequestV2, GovernanceCommitViewV2]:
    if type(state) is not VerifiedCommitEvidenceStateV2:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "",
        )
    try:
        reader = object.__getattribute__(state, "_reader")
        domain = object.__getattribute__(state, "_domain")
        request = object.__getattribute__(state, "_request")
        receipt_root = object.__getattribute__(state, "_receipt_root")
    except AttributeError as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "",
        ) from exc
    _require_domain(domain)
    _require_reader(reader)
    if (
        type(request) is not CommitEvidenceAdvanceRequestV2
        or type(receipt_root) is not str
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        )
    detached = CommitEvidenceAdvanceRequestV2.from_dict(request.to_dict())
    return _load_verified_request_view(
        cast(GovernanceStateReaderV2, reader),
        cast(AuthorityDomainV2, domain),
        detached,
        expected_receipt_root=receipt_root,
    )


def _make_verified_state(
    *,
    state_reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: CommitEvidenceAdvanceRequestV2,
    receipt_root: str,
) -> VerifiedCommitEvidenceStateV2:
    state = object.__new__(VerifiedCommitEvidenceStateV2)
    object.__setattr__(state, "_reader", state_reader)
    object.__setattr__(state, "_domain", AuthorityDomainV2.from_dict(domain.to_dict()))
    object.__setattr__(
        state,
        "_request",
        CommitEvidenceAdvanceRequestV2.from_dict(request.to_dict()),
    )
    object.__setattr__(state, "_receipt_root", receipt_root)
    return state


def _require_domain(value: object) -> None:
    if type(value) is not AuthorityDomainV2:
        raise TypeError("commit evidence requires exact AuthorityDomainV2")


def _require_reader(value: object) -> None:
    try:
        conforms = isinstance(value, GovernanceStateReaderV2)
    except Exception as exc:
        raise TypeError("commit evidence requires StateReader v2") from exc
    if not conforms:
        raise TypeError("commit evidence requires StateReader v2")


__all__: tuple[str, ...] = ()
