"""Atomic StateStore mutation path for Commit Decision v2."""

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
    _commit_transition_events,
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
from pheroos.governance._commit_decision_v2.dependencies import (
    CommitDecisionDependencyV2,
)
from pheroos.governance._commit_decision_v2.events import _commit_decision_events_v2
from pheroos.governance._commit_decision_v2.request import CommitDecisionRequestV2
from pheroos.governance._commit_decision_v2.snapshot import CommitDecisionSnapshotV2
from pheroos.governance._commit_decision_v2.source_proof import (
    VerifiedCommitDecisionSourceV2,
    _source_parent_dependency_v2,
    verify_commit_decision_request_source_v2,
)
from pheroos.governance._commit_decision_v2.state_records import (
    _decision_state_records_v2,
    _decode_committed_decision_view_v2,
    _head_from_view_v2,
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


def open_commit_decision_authority_session_v2(
    capability: GovernanceIssuerCapabilityV2,
    request: CommitDecisionRequestV2,
) -> GovernanceAuthoritySessionV2:
    """Open one exact EVALUATE_QUORUM decision mutation binding."""

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


def advance_commit_decision_v2(
    request: CommitDecisionRequestV2,
    *,
    source: object = None,
    authority_session: object = None,
) -> GovernanceCommitAttemptV2:
    """Atomically commit one source-derived complete decision replacement."""

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
    grant_failure = _current_session_grant_failure(session)
    if grant_failure is not None:
        return _failure_from_session(session, request, *grant_failure)
    lifecycle_failure = _current_session_lifecycle_failure(session)
    if lifecycle_failure is not None:
        return _failure_from_session(session, request, *lifecycle_failure)
    if type(source) is not VerifiedCommitDecisionSourceV2:
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source",
            GovernanceFailureStageV2.VALIDATION,
        )
    try:
        parent = _load_current_parent(store, domain, request, source=source)
    except (TypeError, ValueError):
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source",
            GovernanceFailureStageV2.VALIDATION,
        )
    if isinstance(parent, GovernanceCommitAttemptV2):
        return parent
    parent_snapshot, parent_head = parent
    try:
        snapshot, dependencies, _ = verify_commit_decision_request_source_v2(
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
    heads = _load_dependency_heads(
        store, domain, request, dependencies, parent_head=parent_head
    )
    if isinstance(heads, GovernanceCommitAttemptV2):
        return heads
    observed: tuple[GovernanceHeadV2 | GovernanceReadPreconditionV2, ...] = (
        *heads,
        _session_grant_precondition(session),
        _session_lifecycle_precondition(session),
    )
    read_set_root = _read_set(observed).root()
    binding = _session_binding(session)
    records = _decision_state_records_v2(request, snapshot, binding)
    events = _commit_decision_events_v2(
        request,
        snapshot,
        binding,
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


def _validated_session(
    candidate: object, request: CommitDecisionRequestV2
) -> tuple[
    _GovernanceAuthoritySessionStateV2 | None,
    GovernanceCommitAttemptV2 | None,
]:
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


def _load_current_parent(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: CommitDecisionRequestV2,
    *,
    source: VerifiedCommitDecisionSourceV2,
) -> (
    tuple[CommitDecisionSnapshotV2 | None, GovernanceHeadV2] | GovernanceCommitAttemptV2
):
    dependency = _source_parent_dependency_v2(source)
    try:
        head = store.load_head_v2(request.scope_ref, request.stream_ref)
    except KeyError:
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/scope_ref",
            GovernanceFailureStageV2.LOAD,
        )
    if type(head) is not GovernanceHeadV2:
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/parent",
            GovernanceFailureStageV2.LOAD,
        )
    detached = GovernanceHeadV2.from_dict(head.to_dict())
    if not _head_matches_dependency(detached, dependency, domain):
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/parent",
            GovernanceFailureStageV2.PRECONDITION,
        )
    if dependency.revision == 0:
        return None, detached
    try:
        view = _canonical_commit_view_v2(
            store.load_commit_view_v2(
                request.scope_ref,
                request.stream_ref,
                dependency.transition_id,
                expected_receipt_root=dependency.receipt_root,
            )
        )
    except KeyError:
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/parent",
            GovernanceFailureStageV2.PRECONDITION,
        )
    view_failure = _parent_view_failure(request, view)
    if view_failure is not None:
        return view_failure
    try:
        _, snapshot, _ = _decode_committed_decision_view_v2(
            view, domain, reader=cast(GovernanceStateReaderV2, store)
        )
    except Exception:
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/parent",
            GovernanceFailureStageV2.LOAD,
        )
    if (
        view.position_observation is None
        or view.position_observation.position is not GovernanceCommitPositionV2.CURRENT
        or snapshot.revision != dependency.revision
        or snapshot.transition_id != dependency.transition_id
        or snapshot.snapshot_root != dependency.snapshot_root
    ):
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/parent",
            GovernanceFailureStageV2.PRECONDITION,
        )
    verified_head = _head_from_view_v2(view, domain)
    if verified_head.to_dict() != detached.to_dict():
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/parent",
            GovernanceFailureStageV2.PRECONDITION,
        )
    return snapshot, verified_head


def _parent_view_failure(
    request: CommitDecisionRequestV2,
    view: GovernanceCommitViewV2,
) -> GovernanceCommitAttemptV2 | None:
    if view.disposition is GovernanceCommitDispositionV2.COMMITTED:
        return None
    if view.failure is not None:
        return _failure(
            request,
            view.failure.code,
            view.failure.path,
            view.failure.stage,
        )
    code = (
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
        if view.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
        else AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    return _failure(
        request,
        code,
        "/parent",
        GovernanceFailureStageV2.FINALITY,
    )


def _head_matches_dependency(
    head: GovernanceHeadV2,
    dependency: CommitDecisionDependencyV2,
    domain: AuthorityDomainV2,
) -> bool:
    return (
        head.domain_root == domain.domain_root
        and head.scope_ref == domain.scope_ref
        and head.stream_ref == dependency.stream_ref
        and head.revision == dependency.revision
        and head.transition_id == dependency.transition_id
        and head.head_root == dependency.head_root
    )


def _load_dependency_heads(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: CommitDecisionRequestV2,
    dependencies: tuple[CommitDecisionDependencyV2, ...],
    *,
    parent_head: GovernanceHeadV2,
) -> tuple[GovernanceHeadV2, ...] | GovernanceCommitAttemptV2:
    heads = []
    for dependency in dependencies:
        if dependency.stream_ref == request.stream_ref:
            head = parent_head
        else:
            try:
                head = store.load_head_v2(request.scope_ref, dependency.stream_ref)
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
            or detached.stream_ref != dependency.stream_ref
            or detached.revision != dependency.revision
            or detached.transition_id != dependency.transition_id
            or detached.head_root != dependency.head_root
        ):
            return _failure(
                request,
                AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
                "/dependencies",
                GovernanceFailureStageV2.PRECONDITION,
            )
        heads.append(detached)
    return tuple(heads)


def _committed_view_matches(
    view: GovernanceCommitViewV2,
    request: CommitDecisionRequestV2,
    session: _GovernanceAuthoritySessionStateV2,
) -> bool:
    try:
        committed, _, binding = _decode_committed_decision_view_v2(
            view,
            _session_domain(session),
            reader=cast(GovernanceStateReaderV2, session.store),
        )
    except Exception:
        return False
    return committed.to_dict() == request.to_dict() and binding == _session_binding(
        session
    )


def _failure_from_session(
    session: _GovernanceAuthoritySessionStateV2,
    request: CommitDecisionRequestV2,
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
    request: CommitDecisionRequestV2,
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


def _require_request(value: object) -> CommitDecisionRequestV2:
    if type(value) is not CommitDecisionRequestV2:
        raise TypeError("Commit Decision v2 requires an exact request")
    return value


__all__: tuple[str, ...] = ()
