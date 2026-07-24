"""Dynamically verified non-portable Decision v2 state handle."""

from __future__ import annotations

from typing import NoReturn, SupportsIndex, cast, final

from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance._authority_session_v2.operations import (
    _canonical_commit_view_v2,
)
from pheroos.governance._commit_decision_v2.request import CommitDecisionRequestV2
from pheroos.governance._commit_decision_v2.snapshot import CommitDecisionSnapshotV2
from pheroos.governance._commit_decision_v2.state_records import (
    _decode_committed_decision_view_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceStateReaderV2,
)


@final
class VerifiedCommitDecisionStateV2:
    """Opaque view whose observations reverify Store history and position."""

    __slots__ = ("_domain", "_reader", "_receipt_root", "_request")

    def __new__(
        cls, *_args: object, **_kwargs: object
    ) -> VerifiedCommitDecisionStateV2:
        raise TypeError("VerifiedCommitDecisionStateV2 cannot be constructed directly")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedCommitDecisionStateV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedCommitDecisionStateV2 is immutable")

    def __copy__(self) -> VerifiedCommitDecisionStateV2:
        _verified_state_view_v2(self)
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> VerifiedCommitDecisionStateV2:
        _verified_state_view_v2(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedCommitDecisionStateV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedCommitDecisionStateV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("VerifiedCommitDecisionStateV2 is not portable")

    def __repr__(self) -> str:
        return "<VerifiedCommitDecisionStateV2 redacted>"

    @property
    def snapshot(self) -> CommitDecisionSnapshotV2:
        _, snapshot, _ = _verified_state_view_v2(self)
        return CommitDecisionSnapshotV2.from_dict(snapshot.to_dict())

    @property
    def request_root(self) -> str:
        request, _, _ = _verified_state_view_v2(self)
        return request.request_root

    @property
    def stream_ref(self) -> str:
        request, _, _ = _verified_state_view_v2(self)
        return request.stream_ref

    @property
    def transition_id(self) -> str:
        request, _, _ = _verified_state_view_v2(self)
        return request.transition_id

    @property
    def receipt_root(self) -> str:
        _, _, view = _verified_state_view_v2(self)
        assert view.committed_transition is not None
        return view.committed_transition.receipt.receipt_root

    @property
    def position(self) -> GovernanceCommitPositionV2:
        _, _, view = _verified_state_view_v2(self)
        assert view.position_observation is not None
        return view.position_observation.position


def rehydrate_commit_decision_state_v2(
    payload: object,
    *,
    domain: AuthorityDomainV2,
    state_reader: GovernanceStateReaderV2,
) -> VerifiedCommitDecisionStateV2:
    _require_domain(domain)
    _require_reader(state_reader)
    request = (
        CommitDecisionRequestV2.from_dict(payload)
        if type(payload) is dict
        else CommitDecisionRequestV2.from_dict(_require_request(payload).to_dict())
    )
    if (
        request.domain_root != domain.domain_root
        or request.scope_ref != domain.scope_ref
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/domain_root",
        )
    request, _, view = _load_verified_view_v2(
        state_reader,
        domain,
        request,
        expected_receipt_root=None,
    )
    assert view.committed_transition is not None
    state = object.__new__(VerifiedCommitDecisionStateV2)
    object.__setattr__(state, "_reader", state_reader)
    object.__setattr__(state, "_domain", domain)
    object.__setattr__(state, "_request", request)
    object.__setattr__(
        state,
        "_receipt_root",
        view.committed_transition.receipt.receipt_root,
    )
    return state


def commit_decision_state_is_current_v2(state: object) -> bool:
    try:
        _, _, view = _verified_state_view_v2(state)
        assert view.position_observation is not None
        return view.position_observation.position is GovernanceCommitPositionV2.CURRENT
    except Exception:
        return False


def require_current_commit_decision_state_v2(
    state: object,
) -> CommitDecisionSnapshotV2:
    _, snapshot, view = _verified_state_view_v2(state)
    assert view.position_observation is not None
    if view.position_observation.position is not GovernanceCommitPositionV2.CURRENT:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/position",
        )
    return CommitDecisionSnapshotV2.from_dict(snapshot.to_dict())


def _verified_state_view_v2(
    state: object,
) -> tuple[CommitDecisionRequestV2, CommitDecisionSnapshotV2, GovernanceCommitViewV2]:
    if type(state) is not VerifiedCommitDecisionStateV2:
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
    _require_reader(reader)
    _require_domain(domain)
    if type(request) is not CommitDecisionRequestV2 or type(receipt_root) is not str:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        )
    detached = CommitDecisionRequestV2.from_dict(request.to_dict())
    return _load_verified_view_v2(
        cast(GovernanceStateReaderV2, reader),
        cast(AuthorityDomainV2, domain),
        detached,
        expected_receipt_root=receipt_root,
    )


def _load_verified_view_v2(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: CommitDecisionRequestV2,
    *,
    expected_receipt_root: str | None,
) -> tuple[CommitDecisionRequestV2, CommitDecisionSnapshotV2, GovernanceCommitViewV2]:
    try:
        view = _canonical_commit_view_v2(
            reader.load_commit_view_v2(
                request.scope_ref,
                request.stream_ref,
                request.transition_id,
                expected_receipt_root=expected_receipt_root,
            )
        )
    except (KeyError, GovernanceAuthorityBindingErrorV2) as exc:
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
        committed, snapshot, _ = _decode_committed_decision_view_v2(
            view,
            domain,
            reader=reader,
        )
    except Exception as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/transition_id",
        ) from exc
    if committed.to_dict() != request.to_dict():
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        )
    return committed, snapshot, view


def _require_domain(value: object) -> None:
    if type(value) is not AuthorityDomainV2:
        raise TypeError("commit decision requires an exact authority domain")


def _require_reader(value: object) -> None:
    try:
        conforms = isinstance(value, GovernanceStateReaderV2)
    except Exception as exc:
        raise TypeError("commit decision requires StateReader v2") from exc
    if not conforms:
        raise TypeError("commit decision requires StateReader v2")


def _require_request(value: object) -> CommitDecisionRequestV2:
    if type(value) is not CommitDecisionRequestV2:
        raise TypeError("commit decision requires an exact request")
    return value


__all__: tuple[str, ...] = ()
