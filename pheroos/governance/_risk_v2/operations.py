"""StateStore-backed operations for one durable Risk v2 lineage."""

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
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
    GovernanceStateStoreV2,
)
from pheroos.governance._risk_v2.contracts import (
    RiskStateAdvanceRequestV2,
    RiskStateSnapshotV2,
)
from pheroos.governance._risk_v2.source import (
    VerifiedRiskSourceV2,
    _verified_source_manifest_v2,
    verify_risk_state_request_source_v2,
)
from pheroos.governance._risk_v2.state_support import (
    _committed_view_matches_request,
    _continuity_failure,
    _decode_committed_view,
    _load_verified_request_view,
    _risk_events,
    _state_records,
)


@final
class VerifiedRiskStateV2:
    """Opaque Risk v2 view whose every observation re-verifies Store history."""

    __slots__ = ("_domain", "_reader", "_receipt_root", "_request")

    def __new__(cls, *_args: object, **_kwargs: object) -> VerifiedRiskStateV2:
        raise TypeError("VerifiedRiskStateV2 cannot be constructed directly")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedRiskStateV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedRiskStateV2 is immutable")

    def __copy__(self) -> VerifiedRiskStateV2:
        _verified_state_view(self)
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> VerifiedRiskStateV2:
        _verified_state_view(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedRiskStateV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedRiskStateV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("VerifiedRiskStateV2 is not portable")

    def __repr__(self) -> str:
        return "<VerifiedRiskStateV2 redacted>"

    @property
    def snapshot(self) -> RiskStateSnapshotV2:
        request, _ = _verified_state_view(self)
        return RiskStateSnapshotV2.from_dict(request.snapshot.to_dict())

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


def open_risk_authority_session_v2(
    capability: GovernanceIssuerCapabilityV2,
    request: RiskStateAdvanceRequestV2,
) -> GovernanceAuthoritySessionV2:
    """Open one exact QUALIFY_EVIDENCE target/epoch/request binding."""

    _require_request(request)
    session = _open_governance_authority_session_binding_v2(
        capability,
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        request_ref=request.advance_ref,
        request_root=request.request_root,
        operation=GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
        run_ref=request.run_ref,
        observed_epoch=request.epoch,
        target_refs=(request.target_ref,),
        action_refs=(),
    )
    state = _governance_authority_session_state_v2(session)
    if not _risk_issuer_matches_session(request, state):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/snapshot/assessment/issuer_ref",
        )
    return session


def advance_risk_state_v2(
    request: RiskStateAdvanceRequestV2,
    *,
    source: object = None,
    authority_session: object = None,
) -> GovernanceCommitAttemptV2:
    """Atomically publish one risk assessment and complete replacement state."""

    _require_request(request)
    session, failure = _validated_session_or_failure(authority_session, request)
    if failure is not None:
        return failure
    assert session is not None
    store = cast(GovernanceStateStoreV2, session.store)
    domain = _session_domain(session)

    # Exact recovery is deliberately first.  A response lost after publication
    # remains recoverable after the grant is revoked or the domain is sealed.
    existing = _reconcile(
        store,
        domain,
        request.stream_ref,
        request.transition_id,
        lambda view: _committed_view_matches_request(view, request, session),
    )
    if existing is not None:
        return existing
    source_failure = _risk_source_failure(request, source, domain)
    if source_failure is not None:
        return source_failure
    grant_failure = _current_session_grant_failure(session)
    if grant_failure is not None:
        return _failure_from_session(session, request, *grant_failure)
    lifecycle_failure = _current_session_lifecycle_failure(session)
    if lifecycle_failure is not None:
        return _failure_from_session(session, request, *lifecycle_failure)

    parent = _load_parent_snapshot(store, domain, request)
    if isinstance(parent, GovernanceCommitAttemptV2):
        return parent
    parent_snapshot, parent_head = parent
    continuity = _continuity_failure(request, parent_snapshot)
    if continuity is not None:
        return _failure_from_session(session, request, *continuity)
    try:
        verify_risk_state_request_source_v2(
            request,
            source=source,
            committed_parent_snapshot=parent_snapshot,
        )
    except Exception:
        return _failure_from_session(
            session,
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source",
        )

    observed = (
        parent_head,
        _session_grant_precondition(session),
        _session_lifecycle_precondition(session),
    )
    read_set = _read_set(observed)
    binding = _session_binding(session)
    records = _state_records(request, binding)
    events = _risk_events(
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
        state_records=records,
        events=events,
    )


def _risk_source_failure(
    request: RiskStateAdvanceRequestV2,
    source: object,
    domain: AuthorityDomainV2,
) -> GovernanceCommitAttemptV2 | None:
    """Validate the private source proof before any authoritative read/write."""

    if type(source) is not VerifiedRiskSourceV2:
        return _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source",
            GovernanceFailureStageV2.VALIDATION,
        )
    try:
        manifest = _verified_source_manifest_v2(source)
    except Exception:
        return _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source",
            GovernanceFailureStageV2.VALIDATION,
        )
    if _scoped_manifest_authority_matches_domain_v2(manifest, domain):
        return None
    return _failure_attempt(
        request,
        AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED,
        "/manifest/authority_policy",
        GovernanceFailureStageV2.VALIDATION,
    )


def rehydrate_risk_state_v2(
    payload: object,
    *,
    domain: AuthorityDomainV2,
    state_reader: GovernanceStateReaderV2,
) -> VerifiedRiskStateV2:
    """Rehydrate portable bytes only after historical Store verification."""

    _require_domain(domain)
    _require_state_reader(state_reader)
    request = _request_from_portable(payload)
    if (
        request.domain_root != domain.domain_root
        or request.scope_ref != domain.scope_ref
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/domain_root",
        )
    request, view = _load_verified_request_view(
        state_reader,
        domain,
        request,
        expected_receipt_root=None,
    )
    assert view.committed_transition is not None
    return _make_verified_state(
        state_reader=state_reader,
        domain=domain,
        request=request,
        receipt_root=view.committed_transition.receipt.receipt_root,
    )


def risk_state_is_current_v2(state: object) -> bool:
    try:
        _, view = _verified_state_view(state)
        assert view.position_observation is not None
        return view.position_observation.position is GovernanceCommitPositionV2.CURRENT
    except Exception:
        return False


def require_current_risk_state_v2(state: object) -> RiskStateSnapshotV2:
    request, view = _verified_state_view(state)
    assert view.position_observation is not None
    if view.position_observation.position is not GovernanceCommitPositionV2.CURRENT:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/position",
        )
    return RiskStateSnapshotV2.from_dict(request.snapshot.to_dict())


def _validated_session_or_failure(
    candidate: object,
    request: RiskStateAdvanceRequestV2,
) -> tuple[Any | None, GovernanceCommitAttemptV2 | None]:
    try:
        session = _governance_authority_session_state_v2(candidate)
        _require_store(cast(GovernanceStateStoreV2, session.store))
        _session_domain(session)
    except GovernanceAuthorityBindingErrorV2 as exc:
        return None, _failure_attempt(
            request, exc.code, exc.path, GovernanceFailureStageV2.VALIDATION
        )
    except TypeError:
        return None, _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
            "/authority_session",
            GovernanceFailureStageV2.VALIDATION,
        )
    expected: tuple[object, ...] = (
        GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
        request.domain_root,
        request.scope_ref,
        request.run_ref,
        request.advance_ref,
        request.request_root,
        request.epoch,
        (request.target_ref,),
        (),
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
    if observed != expected:
        return None, _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
            GovernanceFailureStageV2.VALIDATION,
        )
    if not _risk_issuer_matches_session(request, session):
        return None, _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/snapshot/assessment/issuer_ref",
            GovernanceFailureStageV2.VALIDATION,
        )
    return session, None


def _risk_issuer_matches_session(
    request: RiskStateAdvanceRequestV2,
    session: Any,
) -> bool:
    capability = _governance_issuer_capability_state_v2(session.capability)
    return request.snapshot.assessment.issuer_ref == capability.grant.issuer_ref


def _load_parent_snapshot(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: RiskStateAdvanceRequestV2,
) -> tuple[RiskStateSnapshotV2 | None, GovernanceHeadV2] | GovernanceCommitAttemptV2:
    if request.snapshot.parent_revision == 0:
        return None, GovernanceHeadV2.genesis(domain, request.stream_ref)
    return _load_committed_parent(store, domain, request)


def _load_committed_parent(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: RiskStateAdvanceRequestV2,
) -> tuple[RiskStateSnapshotV2, GovernanceHeadV2] | GovernanceCommitAttemptV2:
    snapshot = request.snapshot
    try:
        view = _canonical_commit_view_v2(
            store.load_commit_view_v2(
                request.scope_ref,
                request.stream_ref,
                snapshot.parent_transition_id,
            ),
            invalid_path="/snapshot/parent_transition_id",
        )
    except (KeyError, GovernanceAuthorityBindingErrorV2):
        return _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/snapshot/parent_transition_id",
            GovernanceFailureStageV2.LOAD,
        )
    if view.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE:
        if view.failure is None:
            return _failure_attempt(
                request,
                AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
                "/snapshot/parent_transition_id",
                GovernanceFailureStageV2.FINALITY,
            )
        return _failure_attempt(
            request, view.failure.code, view.failure.path, view.failure.stage
        )
    if (
        view.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or view.committed_transition is None
        or view.position_observation is None
    ):
        return _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/snapshot/parent_transition_id",
            GovernanceFailureStageV2.LOAD,
        )
    try:
        parent_request, _ = _decode_committed_view(view, domain, reader=None)
        parent_head = _head_from_view(view, domain)
    except (
        AttributeError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        GovernanceAuthorityBindingErrorV2,
    ):
        return _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/snapshot/parent_transition_id",
            GovernanceFailureStageV2.LOAD,
        )
    parent = parent_request.snapshot
    receipt = view.committed_transition.receipt
    if (
        parent.revision != snapshot.parent_revision
        or parent.transition_id != snapshot.parent_transition_id
        or parent.snapshot_root != snapshot.parent_snapshot_root
        or receipt.revision != parent.revision
        or receipt.transition_id != parent.transition_id
    ):
        return _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/snapshot/parent_snapshot_root",
            GovernanceFailureStageV2.PRECONDITION,
        )
    return parent, parent_head


def _head_from_view(
    view: GovernanceCommitViewV2, domain: AuthorityDomainV2
) -> GovernanceHeadV2:
    if view.committed_transition is None:
        raise ValueError("risk parent has no committed transition")
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


def _verified_state_view(
    state: object,
) -> tuple[RiskStateAdvanceRequestV2, GovernanceCommitViewV2]:
    if type(state) is not VerifiedRiskStateV2:
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
    _require_state_reader(reader)
    if type(request) is not RiskStateAdvanceRequestV2 or type(receipt_root) is not str:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        )
    detached = RiskStateAdvanceRequestV2.from_dict(request.to_dict())
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
    request: RiskStateAdvanceRequestV2,
    receipt_root: str,
) -> VerifiedRiskStateV2:
    handle = object.__new__(VerifiedRiskStateV2)
    object.__setattr__(handle, "_reader", state_reader)
    object.__setattr__(handle, "_domain", AuthorityDomainV2.from_dict(domain.to_dict()))
    object.__setattr__(
        handle,
        "_request",
        RiskStateAdvanceRequestV2.from_dict(request.to_dict()),
    )
    object.__setattr__(handle, "_receipt_root", receipt_root)
    return handle


def _request_from_portable(payload: object) -> RiskStateAdvanceRequestV2:
    if type(payload) is RiskStateAdvanceRequestV2:
        payload = payload.to_dict()
    try:
        return RiskStateAdvanceRequestV2.from_dict(payload)
    except (TypeError, ValueError) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        ) from exc


def _failure_from_session(
    session: Any,
    request: RiskStateAdvanceRequestV2,
    code: AuthorityDiagnosticCodeV2,
    path: str,
) -> GovernanceCommitAttemptV2:
    return _bound_failure_attempt(
        session.domain_root,
        session.scope_ref,
        request.stream_ref,
        request.transition_id,
        code,
        path,
        GovernanceFailureStageV2.PRECONDITION,
    )


def _failure_attempt(
    request: RiskStateAdvanceRequestV2,
    code: AuthorityDiagnosticCodeV2,
    path: str,
    stage: GovernanceFailureStageV2,
) -> GovernanceCommitAttemptV2:
    return _bound_failure_attempt(
        request.domain_root,
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
        code,
        path,
        stage,
    )


def _require_request(value: object) -> None:
    if type(value) is not RiskStateAdvanceRequestV2:
        raise TypeError("risk operation requires exact advance request v2")


def _require_domain(value: object) -> None:
    if type(value) is not AuthorityDomainV2:
        raise TypeError("risk rehydration requires exact AuthorityDomainV2")


def _require_state_reader(value: object) -> None:
    try:
        conforms = isinstance(value, GovernanceStateReaderV2)
    except Exception as exc:
        raise TypeError("risk rehydration requires StateReader v2") from exc
    if not conforms:
        raise TypeError("risk rehydration requires StateReader v2")


__all__ = [
    "VerifiedRiskStateV2",
    "advance_risk_state_v2",
    "open_risk_authority_session_v2",
    "rehydrate_risk_state_v2",
    "require_current_risk_state_v2",
    "risk_state_is_current_v2",
]
