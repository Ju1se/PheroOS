"""StateStore authority owner for durable PrincipalVerificationSet v2."""

from __future__ import annotations

from typing import Any, NoReturn, SupportsIndex, cast, final

from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceAuthoritySessionV2,
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerOperationV2,
    _governance_authority_session_state_v2,
    _governance_issuer_capability_state_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    _bound_failure_attempt,
    _canonical_commit_view_v2,
    _commit_transition_events,
    _current_session_grant_failure,
    _current_session_lifecycle_failure,
    _open_governance_authority_session_binding_v2,
    _read_set,
    _reconcile,
    _require_store,
    _scoped_manifest_authority_matches_domain_v2,
    _session_binding,
    _session_domain,
    _session_grant_precondition,
    _session_lifecycle_precondition,
)
from pheroos.governance._authority_store_v2_contracts.foundation import (
    GovernanceFailureStageV2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
    GovernanceStateStoreV2,
)
from pheroos.governance._support_v2.principal_verification_contracts import (
    PrincipalVerificationSetAdvanceRequestV2,
    PrincipalVerificationSetSnapshotV2,
)
from pheroos.governance._support_v2.principal_verification_source import (
    VerifiedPrincipalVerificationSourceV2,
    _verified_source_manifest_v2,
    verify_principal_verification_source_v2,
)
from pheroos.governance._support_v2.principal_verification_state import (
    _continuity_failure,
    _decode_committed_view_shallow,
    _load_verified_request_view,
    _state_records,
    _validate_history,
    _verification_event,
)


@final
class VerifiedPrincipalVerificationSetStateV2:
    """Opaque state handle that re-verifies Store inclusion on every use."""

    __slots__ = ("_domain", "_reader", "_receipt_root", "_request")

    def __new__(
        cls, *_args: object, **_kwargs: object
    ) -> VerifiedPrincipalVerificationSetStateV2:
        raise TypeError("VerifiedPrincipalVerificationSetStateV2 cannot be constructed")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedPrincipalVerificationSetStateV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedPrincipalVerificationSetStateV2 is immutable")

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedPrincipalVerificationSetStateV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedPrincipalVerificationSetStateV2 is not portable")

    @property
    def snapshot(self) -> PrincipalVerificationSetSnapshotV2:
        request, _ = _verified_state_view(self)
        return PrincipalVerificationSetSnapshotV2.from_dict(request.snapshot.to_dict())

    @property
    def request_root(self) -> str:
        return _verified_state_view(self)[0].request_root

    @property
    def stream_ref(self) -> str:
        return _verified_state_view(self)[0].stream_ref

    @property
    def transition_id(self) -> str:
        return _verified_state_view(self)[0].transition_id

    @property
    def receipt_root(self) -> str:
        view = _verified_state_view(self)[1]
        assert view.committed_transition is not None
        return view.committed_transition.receipt.receipt_root

    @property
    def position(self) -> GovernanceCommitPositionV2:
        view = _verified_state_view(self)[1]
        assert view.position_observation is not None
        return view.position_observation.position


def open_principal_verification_authority_session_v2(
    capability: GovernanceIssuerCapabilityV2,
    request: PrincipalVerificationSetAdvanceRequestV2,
) -> GovernanceAuthoritySessionV2:
    _require_request(request)
    session = _open_governance_authority_session_binding_v2(
        capability,
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        request_ref=request.advance_ref,
        request_root=request.request_root,
        operation=GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
        run_ref=request.run_ref,
        observed_epoch=request.observed_epoch,
        target_refs=(request.target_ref,),
        action_refs=(),
    )
    state = _governance_authority_session_state_v2(session)
    if not _issuer_matches(request, state):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/snapshot/mutation_issuer_ref",
        )
    return session


def advance_principal_verification_set_v2(
    request: PrincipalVerificationSetAdvanceRequestV2,
    *,
    source: object = None,
    authority_session: object = None,
) -> GovernanceCommitAttemptV2:
    _require_request(request)
    session, failure = _validated_session(authority_session, request)
    if failure is not None:
        return failure
    assert session is not None
    store = cast(GovernanceStateStoreV2, session.store)
    domain = _session_domain(session)
    existing = _reconcile(
        store,
        domain,
        request.stream_ref,
        request.transition_id,
        lambda view: _committed_view_matches(view, request, session),
    )
    if existing is not None:
        return existing
    if type(source) is not VerifiedPrincipalVerificationSourceV2:
        return _failure(
            request, AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/source"
        )
    try:
        manifest = _verified_source_manifest_v2(source)
        verify_principal_verification_source_v2(request, source=source)
    except Exception:
        return _failure(
            request, AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/source"
        )
    if not _scoped_manifest_authority_matches_domain_v2(manifest, domain):
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED,
            "/manifest/authority_policy",
        )
    grant_failure = _current_session_grant_failure(session)
    if grant_failure is not None:
        return _failure(request, *grant_failure)
    lifecycle_failure = _current_session_lifecycle_failure(session)
    if lifecycle_failure is not None:
        return _failure(request, *lifecycle_failure)
    loaded = _load_parent(store, domain, request)
    if isinstance(loaded, GovernanceCommitAttemptV2):
        return loaded
    parent, parent_head = loaded
    continuity = _continuity_failure(request, parent)
    if continuity is not None:
        return _failure(request, *continuity)
    observed = (
        parent_head,
        _session_grant_precondition(session),
        _session_lifecycle_precondition(session),
    )
    read_set = _read_set(observed)
    binding = _session_binding(session)
    event = _verification_event(
        request,
        binding,
        parent_head_root=parent_head.head_root,
        read_set_root=read_set.root(),
    )
    return _commit_transition_events(
        store=store,
        domain=domain,
        stream_ref=request.stream_ref,
        transition_id=request.transition_id,
        write_head=parent_head,
        observed_heads=observed,
        state_records=_state_records(request, binding),
        events=(event,),
    )


def rehydrate_principal_verification_set_state_v2(
    payload: object,
    *,
    domain: AuthorityDomainV2,
    state_reader: GovernanceStateReaderV2,
) -> VerifiedPrincipalVerificationSetStateV2:
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
    request, view = _load_verified_request_view(
        state_reader, domain, request, expected_receipt_root=None
    )
    assert view.committed_transition is not None
    return _make_state(
        state_reader,
        domain,
        request,
        view.committed_transition.receipt.receipt_root,
    )


def require_current_principal_verification_set_v2(
    state: object,
) -> PrincipalVerificationSetSnapshotV2:
    request, view = _verified_state_view(state)
    assert view.position_observation is not None
    if view.position_observation.position is not GovernanceCommitPositionV2.CURRENT:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE, "/position"
        )
    return PrincipalVerificationSetSnapshotV2.from_dict(request.snapshot.to_dict())


def principal_verification_set_is_current_v2(state: object) -> bool:
    try:
        require_current_principal_verification_set_v2(state)
        return True
    except Exception:
        return False


def _load_parent(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: PrincipalVerificationSetAdvanceRequestV2,
) -> (
    tuple[PrincipalVerificationSetSnapshotV2 | None, GovernanceHeadV2]
    | GovernanceCommitAttemptV2
):
    snapshot = request.snapshot
    if snapshot.parent_revision == 0:
        return None, GovernanceHeadV2.genesis(domain, request.stream_ref)
    try:
        view = _canonical_commit_view_v2(
            reader.load_commit_view_v2(
                request.scope_ref, request.stream_ref, snapshot.parent_transition_id
            ),
            invalid_path="/snapshot/parent_transition_id",
        )
        if (
            view.position_observation is None
            or view.position_observation.position
            is not GovernanceCommitPositionV2.CURRENT
        ):
            return _failure(
                request,
                AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
                "/snapshot/parent_transition_id",
            )
        parent_request, _ = _decode_committed_view_shallow(view, domain)
        _validate_history(reader, domain, parent_request)
        parent_head = _head_from_view(view, domain)
    except GovernanceAuthorityBindingErrorV2 as exc:
        return _failure(request, exc.code, exc.path)
    except (KeyError, TypeError, ValueError):
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/snapshot/parent_transition_id",
        )
    return parent_request.snapshot, parent_head


def _head_from_view(
    view: GovernanceCommitViewV2, domain: AuthorityDomainV2
) -> GovernanceHeadV2:
    if view.committed_transition is None:
        raise ValueError("principal verification parent is not committed")
    receipt = view.committed_transition.receipt
    return GovernanceHeadV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=receipt.stream_ref,
        revision=receipt.revision,
        parent_root=receipt.parent_root,
        state_root=receipt.state_root,
        transition_id=receipt.transition_id,
        batch_root=receipt.batch_root,
        head_root=receipt.head_root,
    )


def _validated_session(
    candidate: object,
    request: PrincipalVerificationSetAdvanceRequestV2,
) -> tuple[Any | None, GovernanceCommitAttemptV2 | None]:
    try:
        session = _governance_authority_session_state_v2(candidate)
        _require_store(cast(GovernanceStateStoreV2, session.store))
    except GovernanceAuthorityBindingErrorV2 as exc:
        return None, _failure(request, exc.code, exc.path)
    except TypeError:
        return None, _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
            "/authority_session",
        )
    observed = (
        session.operation,
        session.domain_root,
        session.scope_ref,
        session.run_ref,
        session.request_ref,
        session.request_root,
        session.observed_epoch,
        session.target_refs,
        session.action_refs,
    )
    expected = (
        GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
        request.domain_root,
        request.scope_ref,
        request.run_ref,
        request.advance_ref,
        request.request_root,
        request.observed_epoch,
        (request.target_ref,),
        (),
    )
    if observed != expected or not _issuer_matches(request, session):
        return None, _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        )
    return session, None


def _issuer_matches(
    request: PrincipalVerificationSetAdvanceRequestV2, session: Any
) -> bool:
    capability = _governance_issuer_capability_state_v2(session.capability)
    return bool(request.snapshot.mutation_issuer_ref == capability.grant.issuer_ref)


def _committed_view_matches(
    view: GovernanceCommitViewV2,
    request: PrincipalVerificationSetAdvanceRequestV2,
    session: Any,
) -> bool:
    try:
        committed, binding = _decode_committed_view_shallow(
            view, _session_domain(session)
        )
    except Exception:
        return False
    return committed.to_dict() == request.to_dict() and binding == _session_binding(
        session
    )


def _verified_state_view(
    state: object,
) -> tuple[PrincipalVerificationSetAdvanceRequestV2, GovernanceCommitViewV2]:
    if type(state) is not VerifiedPrincipalVerificationSetStateV2:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, ""
        )
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
    detached = PrincipalVerificationSetAdvanceRequestV2.from_dict(request.to_dict())
    return _load_verified_request_view(
        reader, domain, detached, expected_receipt_root=receipt_root
    )


def _make_state(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: PrincipalVerificationSetAdvanceRequestV2,
    receipt_root: str,
) -> VerifiedPrincipalVerificationSetStateV2:
    state = object.__new__(VerifiedPrincipalVerificationSetStateV2)
    object.__setattr__(state, "_reader", reader)
    object.__setattr__(state, "_domain", AuthorityDomainV2.from_dict(domain.to_dict()))
    object.__setattr__(
        state,
        "_request",
        PrincipalVerificationSetAdvanceRequestV2.from_dict(request.to_dict()),
    )
    object.__setattr__(state, "_receipt_root", receipt_root)
    return state


def _request_from_portable(value: object) -> PrincipalVerificationSetAdvanceRequestV2:
    if type(value) is PrincipalVerificationSetAdvanceRequestV2:
        value = value.to_dict()
    try:
        return PrincipalVerificationSetAdvanceRequestV2.from_dict(value)
    except (TypeError, ValueError) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/request_root"
        ) from exc


def _failure(
    request: PrincipalVerificationSetAdvanceRequestV2,
    code: AuthorityDiagnosticCodeV2,
    path: str,
) -> GovernanceCommitAttemptV2:
    return _bound_failure_attempt(
        request.domain_root,
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
        code,
        path,
        GovernanceFailureStageV2.PRECONDITION,
    )


def _require_request(value: object) -> None:
    if type(value) is not PrincipalVerificationSetAdvanceRequestV2:
        raise TypeError("principal verification operation requires exact request")


def _require_domain(value: object) -> None:
    if type(value) is not AuthorityDomainV2:
        raise TypeError("principal verification requires exact AuthorityDomainV2")


def _require_reader(value: object) -> None:
    try:
        valid = isinstance(value, GovernanceStateReaderV2)
    except Exception as exc:
        raise TypeError("principal verification requires StateReader v2") from exc
    if not valid:
        raise TypeError("principal verification requires StateReader v2")


__all__ = [
    "VerifiedPrincipalVerificationSetStateV2",
    "advance_principal_verification_set_v2",
    "open_principal_verification_authority_session_v2",
    "principal_verification_set_is_current_v2",
    "rehydrate_principal_verification_set_state_v2",
    "require_current_principal_verification_set_v2",
]
