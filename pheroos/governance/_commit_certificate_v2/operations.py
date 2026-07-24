"""Atomic StateStore-backed mutation path for Commit Certificate v2."""

from __future__ import annotations

from typing import cast

from pheroos.protocol.authority_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceReadPreconditionV2,
)

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
    _commit_transition,
    _current_session_grant_failure,
    _current_session_lifecycle_failure,
    _open_governance_authority_session_binding_v2,
    _read_set,
    _reconcile,
    _require_store,
    _session_binding,
    _session_domain,
    _session_grant_precondition,
    _session_lifecycle_precondition,
)
from pheroos.governance._authority_store_v2_contracts.foundation import (
    GovernanceFailureStageV2,
)
from pheroos.governance._commit_certificate_v2.events import (
    _commit_certificate_event_v2,
)
from pheroos.governance._commit_certificate_v2.authority_leaves import (
    CommitCertificateAuthorityLeafV2,
)
from pheroos.governance._commit_certificate_v2.request import (
    CommitCertificateRequestV2,
)
from pheroos.governance._commit_certificate_v2.source import (
    VerifiedCommitCertificateSourceV2,
    verify_commit_certificate_request_source_v2,
)
from pheroos.governance._commit_certificate_v2.state_contracts import (
    COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2,
    COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2,
    CommitCertificateSnapshotV2,
)
from pheroos.governance._commit_certificate_v2.state_records import (
    _certificate_state_records_v2,
    _decode_committed_certificate_view_v2,
    _head_from_view_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitReceiptV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
    GovernanceStateStoreV2,
)


def open_commit_certificate_authority_session_v2(
    capability: GovernanceIssuerCapabilityV2,
    request: CommitCertificateRequestV2,
) -> GovernanceAuthoritySessionV2:
    """Open one exact EVALUATE_QUORUM issuance binding without action scope."""

    _require_request(request)
    session = _open_governance_authority_session_binding_v2(
        capability,
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        request_ref=request.mutation_ref,
        request_root=request.request_root,
        operation=GovernanceIssuerOperationV2.EVALUATE_QUORUM,
        run_ref=request.run_ref,
        observed_epoch=request.observed_epoch,
        target_refs=(request.target_ref,),
        action_refs=(),
    )
    state = _governance_authority_session_state_v2(session)
    if state.capability.issuer_ref != request.mutation_issuer_ref:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/mutation_issuer_ref",
        )
    return session


def advance_commit_certificate_v2(
    request: CommitCertificateRequestV2,
    *,
    source: object = None,
    authority_session: object = None,
) -> GovernanceCommitAttemptV2:
    """Atomically verify and publish one complete certificate replacement."""

    _require_request(request)
    session, failure = _validated_session(authority_session, request)
    if failure is not None:
        return failure
    assert session is not None
    store = cast(GovernanceStateStoreV2, session.store)
    domain = _session_domain(session)

    # Exact recovery intentionally precedes revocation and domain lifecycle
    # checks so a lost response can always be recovered from committed truth.
    existing = _reconcile(
        store,
        domain,
        request.stream_ref,
        request.transition_id,
        lambda view: _committed_view_matches(view, request, session),
    )
    if existing is not None:
        return existing
    grant_failure = _current_session_grant_failure(session)
    if grant_failure is not None:
        return _failure_from_session(session, request, *grant_failure)
    lifecycle_failure = _current_session_lifecycle_failure(session)
    if lifecycle_failure is not None:
        return _failure_from_session(session, request, *lifecycle_failure)
    if type(source) is not VerifiedCommitCertificateSourceV2:
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source",
            GovernanceFailureStageV2.VALIDATION,
        )
    parent = _load_parent(store, domain, request)
    if isinstance(parent, GovernanceCommitAttemptV2):
        return parent
    parent_snapshot, parent_head = parent
    try:
        snapshot, decision = verify_commit_certificate_request_source_v2(
            request,
            source=source,
            committed_parent_snapshot=parent_snapshot,
        )
    except Exception:
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source",
            GovernanceFailureStageV2.VALIDATION,
        )
    dependency_heads = _load_dependency_heads(
        store,
        domain,
        request,
        snapshot,
        decision_head=decision.decision_head,
    )
    if isinstance(dependency_heads, GovernanceCommitAttemptV2):
        return dependency_heads
    observed: tuple[GovernanceHeadV2 | GovernanceReadPreconditionV2, ...] = (
        parent_head,
        *dependency_heads,
        _session_grant_precondition(session),
        _session_lifecycle_precondition(session),
    )
    read_set_root = _read_set(observed).root()
    binding = _session_binding(session)
    records = _certificate_state_records_v2(request, snapshot, binding)
    event = _commit_certificate_event_v2(
        request,
        snapshot,
        binding,
        parent_head_root=parent_head.head_root,
        read_set_root=read_set_root,
    )
    return _commit_transition(
        store=store,
        domain=domain,
        stream_ref=request.stream_ref,
        transition_id=request.transition_id,
        write_head=parent_head,
        observed_heads=observed,
        state_records=records,
        event=event,
    )


def _validated_session(
    candidate: object,
    request: CommitCertificateRequestV2,
) -> tuple[_GovernanceAuthoritySessionStateV2 | None, GovernanceCommitAttemptV2 | None]:
    try:
        session = _governance_authority_session_state_v2(candidate)
        _require_store(cast(GovernanceStateStoreV2, session.store))
        _session_domain(session)
    except GovernanceAuthorityBindingErrorV2 as exc:
        return None, _failure(
            request, exc.code, exc.path, GovernanceFailureStageV2.VALIDATION
        )
    except TypeError:
        return None, _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
            "/authority_session",
            GovernanceFailureStageV2.VALIDATION,
        )
    expected = (
        GovernanceIssuerOperationV2.EVALUATE_QUORUM,
        request.domain_root,
        request.scope_ref,
        request.run_ref,
        request.mutation_ref,
        request.request_root,
        request.observed_epoch,
        (request.target_ref,),
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
        return None, _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
            GovernanceFailureStageV2.VALIDATION,
        )
    return session, None


def _load_parent(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: CommitCertificateRequestV2,
) -> (
    tuple[CommitCertificateSnapshotV2 | None, GovernanceHeadV2]
    | GovernanceCommitAttemptV2
):
    if request.parent_revision == 0:
        head = _load_exact_head(store, domain, request, request.stream_ref)
        if isinstance(head, GovernanceCommitAttemptV2):
            return head
        if head.revision != 0:
            return _failure(
                request,
                AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
                "/parent_revision",
                GovernanceFailureStageV2.PRECONDITION,
            )
        if (
            request.parent_transition_id != COMMIT_CERTIFICATE_GENESIS_TRANSITION_ID_V2
            or request.parent_snapshot_root
            != COMMIT_CERTIFICATE_GENESIS_SNAPSHOT_ROOT_V2
        ):
            return _failure(
                request,
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/parent_snapshot_root",
                GovernanceFailureStageV2.PRECONDITION,
            )
        return None, head
    try:
        view = _canonical_commit_view_v2(
            store.load_commit_view_v2(
                request.scope_ref,
                request.stream_ref,
                request.parent_transition_id,
            )
        )
    except (KeyError, GovernanceAuthorityBindingErrorV2):
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/parent_transition_id",
            GovernanceFailureStageV2.LOAD,
        )
    if view.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE:
        return _finality_failure(request, view)
    try:
        _, parent, _ = _decode_committed_certificate_view_v2(
            view,
            domain,
            reader=cast(GovernanceStateReaderV2, store),
        )
        parent_head = _head_from_view_v2(view, domain)
    except Exception:
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/parent_transition_id",
            GovernanceFailureStageV2.LOAD,
        )
    if (
        parent.revision != request.parent_revision
        or parent.transition_id != request.parent_transition_id
        or parent.snapshot_root != request.parent_snapshot_root
    ):
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/parent_snapshot_root",
            GovernanceFailureStageV2.PRECONDITION,
        )
    if (
        view.position_observation is None
        or view.position_observation.position is not GovernanceCommitPositionV2.CURRENT
    ):
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/parent_revision",
            GovernanceFailureStageV2.PRECONDITION,
        )
    return parent, parent_head


def _load_dependency_heads(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: CommitCertificateRequestV2,
    snapshot: CommitCertificateSnapshotV2,
    *,
    decision_head: GovernanceHeadV2,
) -> tuple[GovernanceHeadV2, ...] | GovernanceCommitAttemptV2:
    try:
        expected = (
            decision_head,
            *tuple(
                _expected_dependency_head(store, domain, request, item)
                for item in snapshot.certificate.body.authority_leaves
            ),
        )
    except (KeyError, TypeError, ValueError, GovernanceAuthorityBindingErrorV2):
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/dependencies",
            GovernanceFailureStageV2.LOAD,
        )
    heads: list[GovernanceHeadV2] = []
    for expected_head in expected:
        loaded = _load_exact_head(store, domain, request, expected_head.stream_ref)
        if isinstance(loaded, GovernanceCommitAttemptV2):
            return loaded
        if loaded.to_dict() != expected_head.to_dict():
            return _failure(
                request,
                AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
                "/dependencies",
                GovernanceFailureStageV2.PRECONDITION,
            )
        heads.append(loaded)
    if len({item.stream_ref for item in heads}) != 9:
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/dependencies",
            GovernanceFailureStageV2.VALIDATION,
        )
    return tuple(heads)


def _dependency_receipt(
    store: GovernanceStateStoreV2,
    request: CommitCertificateRequestV2,
    stream_ref: str,
    transition_id: str,
    receipt_root: str,
) -> GovernanceCommitReceiptV2:
    view = _canonical_commit_view_v2(
        store.load_commit_view_v2(
            request.scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=receipt_root,
        )
    )
    if (
        view.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or view.committed_transition is None
    ):
        raise ValueError("commit certificate dependency receipt is unavailable")
    return view.committed_transition.receipt


def _expected_dependency_head(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: CommitCertificateRequestV2,
    item: CommitCertificateAuthorityLeafV2,
) -> GovernanceHeadV2:
    receipt = _dependency_receipt(
        store,
        request,
        item.stream_ref,
        item.transition_id,
        item.receipt_root,
    )
    if (
        receipt.revision != item.revision
        or receipt.head_root != item.head_root
        or receipt.stream_ref != item.stream_ref
        or receipt.transition_id != item.transition_id
    ):
        raise ValueError("commit certificate dependency receipt is mismatched")
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


def _load_exact_head(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: CommitCertificateRequestV2,
    stream_ref: str,
) -> GovernanceHeadV2 | GovernanceCommitAttemptV2:
    try:
        head = store.load_head_v2(request.scope_ref, stream_ref)
    except KeyError:
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/dependencies",
            GovernanceFailureStageV2.PRECONDITION,
        )
    if type(head) is not GovernanceHeadV2:
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/dependencies",
            GovernanceFailureStageV2.LOAD,
        )
    detached = GovernanceHeadV2.from_dict(head.to_dict())
    if (
        detached.domain_root != domain.domain_root
        or detached.scope_ref != domain.scope_ref
    ):
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/dependencies",
            GovernanceFailureStageV2.LOAD,
        )
    return detached


def _committed_view_matches(
    view: GovernanceCommitViewV2,
    request: CommitCertificateRequestV2,
    session: _GovernanceAuthoritySessionStateV2,
) -> bool:
    try:
        committed, _, binding = _decode_committed_certificate_view_v2(
            view,
            _session_domain(session),
            reader=cast(GovernanceStateReaderV2, session.store),
        )
    except Exception:
        return False
    return committed.to_dict() == request.to_dict() and binding == _session_binding(
        session
    )


def _finality_failure(
    request: CommitCertificateRequestV2,
    view: GovernanceCommitViewV2,
) -> GovernanceCommitAttemptV2:
    if view.failure is not None:
        return _failure(
            request, view.failure.code, view.failure.path, view.failure.stage
        )
    return _failure(
        request,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
        "/parent_transition_id",
        GovernanceFailureStageV2.FINALITY,
    )


def _failure_from_session(
    session: _GovernanceAuthoritySessionStateV2,
    request: CommitCertificateRequestV2,
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


def _failure(
    request: CommitCertificateRequestV2,
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


def _require_request(value: object) -> CommitCertificateRequestV2:
    if type(value) is not CommitCertificateRequestV2:
        raise TypeError("Commit Certificate v2 requires an exact request")
    return value


__all__: tuple[str, ...] = ()
