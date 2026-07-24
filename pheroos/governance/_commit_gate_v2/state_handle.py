"""Opaque Store-reverified state handles for the two Commit Gate v2 ledgers."""

from __future__ import annotations

from typing import NoReturn, SupportsIndex, cast, final

from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance._authority_session_v2.operations import (
    _canonical_commit_view_v2,
)
from pheroos.governance._authority_store_v2_contracts.foundation import _require_root
from pheroos.governance._commit_gate_v2.permission_contracts import (
    CommitPermissionRequestV2,
    CommitPermissionSnapshotV2,
)
from pheroos.governance._commit_gate_v2.state_records import (
    GateKindV2,
    GateRequestV2,
    _decode_committed_gate_view_v2,
)
from pheroos.governance._commit_gate_v2.stop_contracts import (
    CommitStopRequestV2,
    CommitStopSnapshotV2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceStateReaderV2,
)


class _VerifiedCommitGateStateBaseV2:
    __slots__ = ("_domain", "_reader", "_receipt_root", "_request")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __copy__(self) -> _VerifiedCommitGateStateBaseV2:
        _verified_state_view_v2(self)
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> _VerifiedCommitGateStateBaseV2:
        _verified_state_view_v2(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError(f"{type(self).__name__} is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError(f"{type(self).__name__} is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError(f"{type(self).__name__} is not portable")

    @property
    def request_root(self) -> str:
        return _verified_state_view_v2(self)[0].request_root

    @property
    def stream_ref(self) -> str:
        return _verified_state_view_v2(self)[0].stream_ref

    @property
    def transition_id(self) -> str:
        return _verified_state_view_v2(self)[0].transition_id

    @property
    def receipt_root(self) -> str:
        view = _verified_state_view_v2(self)[1]
        assert view.committed_transition is not None
        return view.committed_transition.receipt.receipt_root

    @property
    def position(self) -> GovernanceCommitPositionV2:
        view = _verified_state_view_v2(self)[1]
        assert view.position_observation is not None
        return view.position_observation.position


@final
class VerifiedCommitStopStateV2(_VerifiedCommitGateStateBaseV2):
    def __new__(cls, *_args: object, **_kwargs: object) -> VerifiedCommitStopStateV2:
        raise TypeError("VerifiedCommitStopStateV2 cannot be constructed directly")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedCommitStopStateV2 is final")

    def __repr__(self) -> str:
        return "<VerifiedCommitStopStateV2 redacted>"

    @property
    def snapshot(self) -> CommitStopSnapshotV2:
        request = _verified_state_view_v2(self)[0]
        assert type(request) is CommitStopRequestV2
        return CommitStopSnapshotV2.from_dict(request.snapshot.to_dict())


@final
class VerifiedCommitPermissionStateV2(_VerifiedCommitGateStateBaseV2):
    def __new__(
        cls, *_args: object, **_kwargs: object
    ) -> VerifiedCommitPermissionStateV2:
        raise TypeError(
            "VerifiedCommitPermissionStateV2 cannot be constructed directly"
        )

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedCommitPermissionStateV2 is final")

    def __repr__(self) -> str:
        return "<VerifiedCommitPermissionStateV2 redacted>"

    @property
    def snapshot(self) -> CommitPermissionSnapshotV2:
        request = _verified_state_view_v2(self)[0]
        assert type(request) is CommitPermissionRequestV2
        return CommitPermissionSnapshotV2.from_dict(request.snapshot.to_dict())


def _rehydrate_gate_state_v2(
    payload: object,
    *,
    domain: AuthorityDomainV2,
    state_reader: GovernanceStateReaderV2,
    kind: GateKindV2,
) -> _VerifiedCommitGateStateBaseV2:
    _require_domain(domain)
    _require_reader(state_reader)
    request = _request_from_portable(payload, kind=kind)
    if (
        request.domain_root != domain.domain_root
        or request.scope_ref != domain.scope_ref
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/domain_root",
        )
    request, view = _load_verified_request_view_v2(
        state_reader,
        domain,
        request,
        expected_receipt_root=None,
        kind=kind,
    )
    assert view.committed_transition is not None
    return _make_verified_state_v2(
        state_reader=state_reader,
        domain=domain,
        request=request,
        receipt_root=view.committed_transition.receipt.receipt_root,
        kind=kind,
    )


def _state_is_current_v2(state: object, *, kind: GateKindV2) -> bool:
    try:
        if _kind_for_state(state) != kind:
            return False
        view = _verified_state_view_v2(state)[1]
        assert view.position_observation is not None
        return view.position_observation.position is GovernanceCommitPositionV2.CURRENT
    except Exception:
        return False


def _require_current_state_v2(state: object, *, kind: GateKindV2) -> GateRequestV2:
    if _kind_for_state(state) != kind:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, ""
        )
    request, view = _verified_state_view_v2(state)
    assert view.position_observation is not None
    if view.position_observation.position is not GovernanceCommitPositionV2.CURRENT:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/position",
        )
    return request


def _verified_state_view_v2(
    state: object,
) -> tuple[GateRequestV2, GovernanceCommitViewV2]:
    kind = _kind_for_state(state)
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
    expected_request_type = (
        CommitStopRequestV2 if kind == "stop" else CommitPermissionRequestV2
    )
    if type(request) is not expected_request_type or type(receipt_root) is not str:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        )
    _require_root(receipt_root, "commit gate state receipt_root")
    detached = _request_from_portable(request.to_dict(), kind=kind)
    return _load_verified_request_view_v2(
        cast(GovernanceStateReaderV2, reader),
        cast(AuthorityDomainV2, domain),
        detached,
        expected_receipt_root=receipt_root,
        kind=kind,
    )


def _load_verified_request_view_v2(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    expected_request: GateRequestV2,
    *,
    expected_receipt_root: str | None,
    kind: GateKindV2,
) -> tuple[GateRequestV2, GovernanceCommitViewV2]:
    try:
        view = _canonical_commit_view_v2(
            reader.load_commit_view_v2(
                expected_request.scope_ref,
                expected_request.stream_ref,
                expected_request.transition_id,
                expected_receipt_root=expected_receipt_root,
            )
        )
    except (KeyError, GovernanceAuthorityBindingErrorV2) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/transition_id",
        ) from exc
    if view.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE:
        code = (
            AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
            if view.failure is None
            else view.failure.code
        )
        path = "/transition_id" if view.failure is None else view.failure.path
        raise GovernanceAuthorityBindingErrorV2(code, path)
    try:
        request, _, _ = _decode_committed_gate_view_v2(
            view, domain, kind=kind, reader=reader
        )
    except GovernanceAuthorityBindingErrorV2:
        raise
    except Exception as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/transition_id",
        ) from exc
    if request.to_dict() != expected_request.to_dict():
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        )
    return request, view


def _make_verified_state_v2(
    *,
    state_reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: GateRequestV2,
    receipt_root: str,
    kind: GateKindV2,
) -> _VerifiedCommitGateStateBaseV2:
    state_type = (
        VerifiedCommitStopStateV2 if kind == "stop" else VerifiedCommitPermissionStateV2
    )
    handle = object.__new__(state_type)
    object.__setattr__(handle, "_reader", state_reader)
    object.__setattr__(handle, "_domain", AuthorityDomainV2.from_dict(domain.to_dict()))
    object.__setattr__(
        handle, "_request", _request_from_portable(request.to_dict(), kind=kind)
    )
    object.__setattr__(handle, "_receipt_root", receipt_root)
    return handle


def _request_from_portable(payload: object, *, kind: GateKindV2) -> GateRequestV2:
    if type(payload) in (CommitStopRequestV2, CommitPermissionRequestV2):
        payload = cast(GateRequestV2, payload).to_dict()
    try:
        if kind == "stop":
            return CommitStopRequestV2.from_dict(payload)
        return CommitPermissionRequestV2.from_dict(payload)
    except (TypeError, ValueError) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        ) from exc


def _kind_for_state(state: object) -> GateKindV2:
    if type(state) is VerifiedCommitStopStateV2:
        return "stop"
    if type(state) is VerifiedCommitPermissionStateV2:
        return "permission"
    raise GovernanceAuthorityBindingErrorV2(
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, ""
    )


def _require_domain(value: object) -> None:
    if type(value) is not AuthorityDomainV2:
        raise TypeError("commit gate rehydration requires exact AuthorityDomainV2")


def _require_reader(value: object) -> None:
    try:
        conforms = isinstance(value, GovernanceStateReaderV2)
    except Exception as exc:
        raise TypeError("commit gate rehydration requires StateReader v2") from exc
    if not conforms:
        raise TypeError("commit gate rehydration requires StateReader v2")


__all__: tuple[str, ...] = ()
