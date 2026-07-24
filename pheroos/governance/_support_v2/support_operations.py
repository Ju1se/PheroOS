"""StateStore-backed unified ledger operations for durable Support v2."""

from __future__ import annotations

from typing import Any, cast

from pheroos.protocol.authority_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceReadPreconditionV2,
)

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceAuthoritySessionV2,
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerOperationV2,
    _governance_authority_session_state_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    _bound_failure_attempt,
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
from pheroos.governance._support_v2.support_committed_state import (
    _decode_state_records as _decode_state_records,
    _state_records,
    _validate_membership_precondition,
)
from pheroos.governance._support_v2.support_incremental_state import (
    _adopt_committed_support_successor_v2 as _adopt_committed_support_successor_v2,
)
from pheroos.governance._support_v2.support_source_proof import (
    _VerifiedSupportMaterialV2,
    VerifiedSupportSourceV2,
    _verified_source,
)
from pheroos.governance._support_v2.support_state_contracts import (
    SupportAdvanceRequestV2,
    SupportMutationKindV2,
)
from pheroos.governance._support_v2.support_state_handle import (
    VerifiedSupportStateV2,
    _make_verified_state,
    require_current_support_state_v2,
    support_state_is_current_v2,
)
from pheroos.governance._support_v2.support_state_load import (
    _decode_committed_view,
    _load_verified_request_view,
)
from pheroos.governance._support_v2.support_trace_events import (
    _request_target_refs,
    _support_events,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
    GovernanceStateStoreV2,
)


def open_support_authority_session_v2(
    capability: GovernanceIssuerCapabilityV2,
    request: SupportAdvanceRequestV2,
) -> GovernanceAuthoritySessionV2:
    """Open one exact QUALIFY_EVIDENCE Support mutation binding."""

    _require_request(request)
    if type(capability) is not GovernanceIssuerCapabilityV2:
        raise TypeError("support authority session requires exact capability v2")
    if capability.issuer_ref != request.mutation_issuer_ref:
        raise ValueError("support issuer_ref is not owned by the capability")
    return _open_governance_authority_session_binding_v2(
        capability,
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        request_ref=request.mutation_ref,
        request_root=request.request_root,
        operation=GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
        run_ref=request.run_ref,
        observed_epoch=request.observed_epoch,
        target_refs=_request_target_refs(request),
        action_refs=(),
    )


def advance_support_state_v2(
    request: SupportAdvanceRequestV2,
    *,
    source: object = None,
    authority_session: object = None,
) -> GovernanceCommitAttemptV2:
    """Atomically initialize, issue, revoke, or switch the unified ledger."""

    _require_request(request)
    session, failure = _validated_session_or_failure(authority_session, request)
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
        lambda view: _committed_view_matches_request(view, request, session),
    )
    if existing is not None:
        return existing
    grant_failure = _current_session_grant_failure(session)
    if grant_failure is not None:
        return _failure_from_session(session, request, *grant_failure)
    lifecycle_failure = _current_session_lifecycle_failure(session)
    if lifecycle_failure is not None:
        return _failure_from_session(session, request, *lifecycle_failure)
    if session.capability.issuer_ref != request.mutation_issuer_ref:
        return _failure_from_session(
            session,
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/mutation_issuer_ref",
        )
    material, source_failure = _validated_source_or_failure(
        session,
        request,
        source,
        domain,
    )
    if source_failure is not None:
        return source_failure
    assert material is not None
    source_context_root = material.binding.context_root
    source_verification_root = material.binding.source_verification_root
    parent_precondition = material.parent_precondition
    membership_precondition = material.membership_precondition
    write_head, source_failure = _write_head_or_failure(
        session,
        request,
        store,
        domain,
        parent_precondition,
        membership_precondition,
    )
    if source_failure is not None:
        return source_failure
    assert write_head is not None

    observed: tuple[GovernanceHeadV2 | GovernanceReadPreconditionV2, ...] = (
        write_head,
        _session_grant_precondition(session),
        _session_lifecycle_precondition(session),
        *((membership_precondition,) if membership_precondition is not None else ()),
    )
    read_set_root = _read_set(observed).root()
    binding = _session_binding(session)
    records = _state_records(
        request,
        binding,
        source_context_root=source_context_root,
        source_verification_root=source_verification_root,
        membership_precondition=membership_precondition,
    )
    events = _support_events(
        request,
        binding,
        source_context_root=source_context_root,
        source_verification_root=source_verification_root,
        parent_head_root=write_head.head_root,
        read_set_root=read_set_root,
    )
    return _commit_transition_events(
        store=store,
        domain=domain,
        stream_ref=request.stream_ref,
        transition_id=request.transition_id,
        write_head=write_head,
        observed_heads=observed,
        state_records=records,
        events=events,
    )


def rehydrate_support_state_v2(
    payload: object,
    *,
    domain: AuthorityDomainV2,
    state_reader: GovernanceStateReaderV2,
) -> VerifiedSupportStateV2:
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
        view=view,
    )


def _validated_source_or_failure(
    session: Any,
    request: SupportAdvanceRequestV2,
    source: object,
    domain: AuthorityDomainV2,
) -> tuple[_VerifiedSupportMaterialV2 | None, GovernanceCommitAttemptV2 | None]:
    if type(source) is not VerifiedSupportSourceV2:
        return None, _failure_from_session(
            session,
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source",
        )
    try:
        material = _verified_source(source)
    except GovernanceAuthorityBindingErrorV2 as exc:
        return None, _source_failure_from_error(session, request, exc)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return None, _failure_from_session(
            session,
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source",
        )
    if material.request.to_dict() != request.to_dict():
        return None, _failure_from_session(
            session,
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source/request_root",
        )
    if not _scoped_manifest_authority_matches_domain_v2(material.manifest, domain):
        return None, _failure_from_session(
            session,
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source/manifest/authority_policy",
        )
    return material, None


def _write_head_or_failure(
    session: Any,
    request: SupportAdvanceRequestV2,
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    parent_precondition: GovernanceReadPreconditionV2 | None,
    membership_precondition: GovernanceReadPreconditionV2 | None,
) -> tuple[GovernanceHeadV2 | None, GovernanceCommitAttemptV2 | None]:
    try:
        _validate_membership_precondition(request, membership_precondition)
    except (AttributeError, TypeError, ValueError):
        return None, _failure_from_session(
            session,
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source/membership",
        )
    try:
        head = _resolve_write_head(
            store,
            domain,
            request,
            parent_precondition=parent_precondition,
        )
    except GovernanceAuthorityBindingErrorV2 as exc:
        return None, _source_failure_from_error(session, request, exc)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return None, _failure_from_session(
            session,
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source",
        )
    return head, None


def _resolve_write_head(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: SupportAdvanceRequestV2,
    *,
    parent_precondition: GovernanceReadPreconditionV2 | None,
) -> GovernanceHeadV2:
    if request.mutation_kind is SupportMutationKindV2.INITIALIZE:
        if parent_precondition is not None:
            raise GovernanceAuthorityBindingErrorV2(
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/source/parent",
            )
        return GovernanceHeadV2.genesis(domain, request.stream_ref)
    if type(parent_precondition) is not GovernanceReadPreconditionV2:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source/parent",
        )
    head = store.load_head_v2(request.scope_ref, request.stream_ref)
    if type(head) is not GovernanceHeadV2:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source/parent",
        )
    observed = (head.stream_ref, head.revision, head.head_root)
    expected = (
        parent_precondition.stream_ref,
        parent_precondition.expected_revision,
        parent_precondition.expected_root,
    )
    if observed != expected or head.revision != request.snapshot.parent_revision:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/source/parent",
        )
    return head


def _source_failure_from_error(
    session: Any,
    request: SupportAdvanceRequestV2,
    error: GovernanceAuthorityBindingErrorV2,
) -> GovernanceCommitAttemptV2:
    if error.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE:
        return _failure_from_session(
            session,
            request,
            error.code,
            error.path or "/source",
        )
    return _failure_from_session(
        session,
        request,
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        error.path or "/source",
    )


def _validated_session_or_failure(
    candidate: object,
    request: SupportAdvanceRequestV2,
) -> tuple[Any | None, GovernanceCommitAttemptV2 | None]:
    try:
        session = _governance_authority_session_state_v2(candidate)
        _require_store(cast(GovernanceStateStoreV2, session.store))
        _session_domain(session)
    except GovernanceAuthorityBindingErrorV2 as exc:
        return None, _failure_attempt(
            request,
            exc.code,
            exc.path,
            GovernanceFailureStageV2.VALIDATION,
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
        request.mutation_ref,
        request.request_root,
        request.observed_epoch,
        _request_target_refs(request),
        (),
        request.mutation_issuer_ref,
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
        session.capability.issuer_ref,
    )
    if observed != expected:
        return None, _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
            GovernanceFailureStageV2.VALIDATION,
        )
    return session, None


def _committed_view_matches_request(
    view: GovernanceCommitViewV2,
    request: SupportAdvanceRequestV2,
    session: Any,
) -> bool:
    try:
        committed, binding, _, _, _ = _decode_committed_view(
            view,
            _session_domain(session),
        )
    except (TypeError, ValueError, GovernanceAuthorityBindingErrorV2):
        return False
    return bool(
        committed.to_dict() == request.to_dict()
        and binding == _session_binding(session)
    )


def _request_from_portable(payload: object) -> SupportAdvanceRequestV2:
    if type(payload) is SupportAdvanceRequestV2:
        payload = payload.to_dict()
    try:
        return SupportAdvanceRequestV2.from_dict(payload)
    except (TypeError, ValueError) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        ) from exc


def _failure_from_session(
    session: Any,
    request: SupportAdvanceRequestV2,
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
    request: SupportAdvanceRequestV2,
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
    if type(value) is not SupportAdvanceRequestV2:
        raise TypeError("support operation requires exact advance request v2")


def _require_domain(value: object) -> None:
    if type(value) is not AuthorityDomainV2:
        raise TypeError("support rehydration requires exact AuthorityDomainV2")


def _require_state_reader(value: object) -> None:
    try:
        conforms = isinstance(value, GovernanceStateReaderV2)
    except Exception as exc:
        raise TypeError("support rehydration requires StateReader v2") from exc
    if not conforms:
        raise TypeError("support rehydration requires StateReader v2")


__all__ = [
    "VerifiedSupportStateV2",
    "advance_support_state_v2",
    "open_support_authority_session_v2",
    "rehydrate_support_state_v2",
    "require_current_support_state_v2",
    "support_state_is_current_v2",
]
