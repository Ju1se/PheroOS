"""StateStore-backed Commit Evidence v2 authority operations."""

from __future__ import annotations

from typing import cast

from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceAuthoritySessionV2,
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerOperationV2,
    _GovernanceAuthoritySessionStateV2,
    _governance_authority_session_state_v2,
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
from pheroos.governance._commit_evidence_owner_v2.contracts import (
    CommitEvidenceAdvanceRequestV2,
    CommitEvidenceSnapshotV2,
)
from pheroos.governance._commit_evidence_owner_v2.source import (
    verify_commit_evidence_request_source_v2,
)
from pheroos.governance._commit_evidence_owner_v2.source_proof import (
    VerifiedCommitEvidenceSourceV2,
    _expected_source_context_root_v2,
    _source_read_preconditions_v2,
    _verified_source_manifest_v2,
)
from pheroos.governance._commit_evidence_owner_v2.state_handle import (
    VerifiedCommitEvidenceStateV2,
    _make_verified_state,
    _require_domain,
    _require_reader,
)
from pheroos.governance._commit_evidence_owner_v2.state_records import (
    _state_records,
)
from pheroos.governance._commit_evidence_owner_v2.state_verification import (
    _decode_committed_view,
    _load_verified_request_view,
    _validate_transition_delta,
)
from pheroos.governance._commit_evidence_owner_v2.trace_events import (
    _commit_evidence_events,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
    GovernanceStateStoreV2,
)


def open_commit_evidence_authority_session_v2(
    capability: GovernanceIssuerCapabilityV2,
    request: CommitEvidenceAdvanceRequestV2,
) -> GovernanceAuthoritySessionV2:
    """Open one exact QUALIFY_EVIDENCE request binding."""

    _require_request(request)
    if type(capability) is not GovernanceIssuerCapabilityV2:
        raise TypeError("commit evidence session requires exact capability v2")
    if capability.issuer_ref != request.snapshot.mutation_issuer_ref:
        raise ValueError("commit evidence issuer is not owned by capability")
    return _open_governance_authority_session_binding_v2(
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


def advance_commit_evidence_state_v2(
    request: CommitEvidenceAdvanceRequestV2,
    *,
    source: object = None,
    authority_session: object = None,
) -> GovernanceCommitAttemptV2:
    """Atomically commit one complete Evidence replacement snapshot."""

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
    if session.capability.issuer_ref != request.snapshot.mutation_issuer_ref:
        return _failure_from_session(
            session,
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/snapshot/mutation_issuer_ref",
        )
    verified_source, source_failure = _validated_source_or_failure(
        session,
        request,
        source,
        domain,
    )
    if source_failure is not None:
        return source_failure
    assert verified_source is not None
    parent, parent_failure = _load_parent(store, domain, request)
    if parent_failure is not None:
        return parent_failure
    assert parent is not None
    parent_snapshot, parent_head = parent
    try:
        if parent_snapshot is not None:
            _validate_transition_delta(request.snapshot, parent_snapshot)
        verify_commit_evidence_request_source_v2(request, source=verified_source)
        dependencies = _source_read_preconditions_v2(verified_source)
    except (AttributeError, KeyError, IndexError, TypeError, ValueError):
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
        *dependencies,
    )
    read_set_root = _read_set(observed).root()
    binding = _session_binding(session)
    source_root = _expected_source_context_root_v2(verified_source)
    records = _state_records(
        request,
        binding,
        source_context_root=source_root,
    )
    events = _commit_evidence_events(
        request,
        binding,
        source_context_root=source_root,
        parent_head_root=parent_head.head_root,
        read_set_root=read_set_root,
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


def rehydrate_commit_evidence_state_v2(
    payload: object,
    *,
    domain: AuthorityDomainV2,
    state_reader: GovernanceStateReaderV2,
) -> VerifiedCommitEvidenceStateV2:
    """Rehydrate portable bytes only after Store and history verification."""

    _require_domain(domain)
    _require_reader(state_reader)
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


def _validated_source_or_failure(
    session: _GovernanceAuthoritySessionStateV2,
    request: CommitEvidenceAdvanceRequestV2,
    source: object,
    domain: AuthorityDomainV2,
) -> tuple[VerifiedCommitEvidenceSourceV2 | None, GovernanceCommitAttemptV2 | None]:
    if type(source) is not VerifiedCommitEvidenceSourceV2:
        return None, _failure_from_session(
            session,
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source",
        )
    try:
        manifest = _verified_source_manifest_v2(source)
        verify_commit_evidence_request_source_v2(request, source=source)
    except (AttributeError, KeyError, IndexError, TypeError, ValueError):
        return None, _failure_from_session(
            session,
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source",
        )
    if not _scoped_manifest_authority_matches_domain_v2(manifest, domain):
        return None, _failure_from_session(
            session,
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED,
            "/manifest/authority_policy",
        )
    return source, None


def _validated_session_or_failure(
    candidate: object,
    request: CommitEvidenceAdvanceRequestV2,
) -> tuple[
    _GovernanceAuthoritySessionStateV2 | None,
    GovernanceCommitAttemptV2 | None,
]:
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
        request.advance_ref,
        request.request_root,
        request.observed_epoch,
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
    return session, None


def _load_parent(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: CommitEvidenceAdvanceRequestV2,
) -> tuple[
    tuple[CommitEvidenceSnapshotV2 | None, GovernanceHeadV2] | None,
    GovernanceCommitAttemptV2 | None,
]:
    if request.snapshot.parent_revision == 0:
        return (None, GovernanceHeadV2.genesis(domain, request.stream_ref)), None
    try:
        view = _canonical_commit_view_v2(
            store.load_commit_view_v2(
                request.scope_ref,
                request.stream_ref,
                request.snapshot.parent_transition_id,
            ),
            invalid_path="/snapshot/parent_transition_id",
        )
    except (KeyError, GovernanceAuthorityBindingErrorV2):
        return None, _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/snapshot/parent_transition_id",
            GovernanceFailureStageV2.LOAD,
        )
    if view.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE:
        code = (
            AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
            if view.failure is None
            else view.failure.code
        )
        path = (
            "/snapshot/parent_transition_id"
            if view.failure is None
            else view.failure.path
        )
        return None, _failure_attempt(
            request,
            code,
            path,
            GovernanceFailureStageV2.FINALITY,
        )
    try:
        parent_request, _, _ = _decode_committed_view(view, domain)
        parent_head = _head_from_view(view, domain)
    except (
        AttributeError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        GovernanceAuthorityBindingErrorV2,
    ):
        return None, _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/snapshot/parent_transition_id",
            GovernanceFailureStageV2.LOAD,
        )
    parent = parent_request.snapshot
    snapshot = request.snapshot
    if (
        parent.revision != snapshot.parent_revision
        or parent.transition_id != snapshot.parent_transition_id
        or parent.snapshot_root != snapshot.parent_snapshot_root
    ):
        return None, _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/snapshot/parent_snapshot_root",
            GovernanceFailureStageV2.PRECONDITION,
        )
    return (parent, parent_head), None


def _head_from_view(
    view: GovernanceCommitViewV2,
    domain: AuthorityDomainV2,
) -> GovernanceHeadV2:
    if view.committed_transition is None:
        raise ValueError("commit evidence parent is not committed")
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


def _committed_view_matches_request(
    view: GovernanceCommitViewV2,
    request: CommitEvidenceAdvanceRequestV2,
    session: _GovernanceAuthoritySessionStateV2,
) -> bool:
    try:
        committed, binding, _ = _decode_committed_view(
            view,
            _session_domain(session),
        )
    except (TypeError, ValueError, GovernanceAuthorityBindingErrorV2):
        return False
    return committed.to_dict() == request.to_dict() and binding == _session_binding(
        session
    )


def _request_from_portable(payload: object) -> CommitEvidenceAdvanceRequestV2:
    if type(payload) is CommitEvidenceAdvanceRequestV2:
        payload = payload.to_dict()
    try:
        return CommitEvidenceAdvanceRequestV2.from_dict(payload)
    except (TypeError, ValueError) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        ) from exc


def _failure_from_session(
    session: _GovernanceAuthoritySessionStateV2,
    request: CommitEvidenceAdvanceRequestV2,
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
    request: CommitEvidenceAdvanceRequestV2,
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
    if type(value) is not CommitEvidenceAdvanceRequestV2:
        raise TypeError("commit evidence operation requires exact request v2")


__all__: tuple[str, ...] = ()
