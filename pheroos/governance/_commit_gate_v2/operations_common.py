"""Shared atomic StateStore mutation path for Commit Gate v2."""

from __future__ import annotations

from typing import cast

from pheroos.protocol.authority_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceReadPreconditionV2,
)

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
    _GovernanceAuthoritySessionStateV2,
    _governance_authority_session_state_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    _bound_failure_attempt,
    _canonical_commit_view_v2,
    _commit_transition,
    _current_session_grant_failure,
    _current_session_lifecycle_failure,
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
from pheroos.governance._commit_gate_v2.contract_support import (
    _validate_successor_common,
)
from pheroos.governance._commit_gate_v2.events import _commit_gate_event_v2
from pheroos.governance._commit_gate_v2.permission_contracts import (
    CommitPermissionRequestV2,
    CommitPermissionSnapshotV2,
)
from pheroos.governance._commit_gate_v2.permission_source import (
    VerifiedCommitPermissionSourceV2,
    verify_commit_permission_request_source_v2,
)
from pheroos.governance._commit_gate_v2.state_records import (
    GateKindV2,
    GateRequestV2,
    GateSnapshotV2,
    _decode_committed_gate_view_v2,
    _gate_state_records_v2,
    _head_from_view_v2,
    _operation,
    _request_ref,
)
from pheroos.governance._commit_gate_v2.stop_contracts import (
    CommitStopRequestV2,
    CommitStopSnapshotV2,
)
from pheroos.governance._commit_gate_v2.stop_source import (
    VerifiedCommitStopSourceV2,
    verify_commit_stop_request_source_v2,
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


def _advance_commit_gate_v2(
    request: GateRequestV2,
    *,
    source: object,
    authority_session: object,
    kind: GateKindV2,
) -> GovernanceCommitAttemptV2:
    session, failure = _validated_session_or_failure(
        authority_session, request, kind=kind
    )
    if failure is not None:
        return failure
    assert session is not None
    store = cast(GovernanceStateStoreV2, session.store)
    domain = _session_domain(session)

    # Lost-response recovery is intentionally first.  The exact committed
    # mutation remains recoverable after grant revocation or domain sealing.
    existing = _reconcile(
        store,
        domain,
        request.stream_ref,
        request.transition_id,
        lambda view: _committed_view_matches_request_v2(
            view, request, session, kind=kind
        ),
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

    parent = _load_parent_v2(store, domain, request, kind=kind)
    if isinstance(parent, GovernanceCommitAttemptV2):
        return parent
    parent_snapshot, parent_head = parent
    try:
        if parent_snapshot is not None:
            _validate_successor_common(request.snapshot, parent_snapshot)
        source_context_root, dependency_preconditions = _verify_source_v2(
            request, source, parent_snapshot, kind=kind
        )
    except Exception:
        return _failure_from_session(
            session,
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source",
        )
    dependency_heads = _load_dependency_heads_v2(
        store,
        domain,
        request,
        dependency_preconditions,
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
    records = _gate_state_records_v2(
        request,
        binding,
        kind=kind,
        source_context_root=source_context_root,
    )
    event = _commit_gate_event_v2(
        request,
        binding,
        operation=_operation(kind).value,
        source_context_root=source_context_root,
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


def _validated_session_or_failure(
    candidate: object,
    request: GateRequestV2,
    *,
    kind: GateKindV2,
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
            request, exc.code, exc.path, GovernanceFailureStageV2.VALIDATION
        )
    except TypeError:
        return None, _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
            "/authority_session",
            GovernanceFailureStageV2.VALIDATION,
        )
    expected = (
        _operation(kind),
        request.domain_root,
        request.scope_ref,
        request.run_ref,
        _request_ref(request),
        request.request_root,
        request.observed_epoch,
        (request.target_ref,),
        () if kind == "stop" else ("commit",),
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


def _load_parent_v2(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: GateRequestV2,
    *,
    kind: GateKindV2,
) -> tuple[GateSnapshotV2 | None, GovernanceHeadV2] | GovernanceCommitAttemptV2:
    if request.snapshot.parent_revision == 0:
        return None, GovernanceHeadV2.genesis(domain, request.stream_ref)
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
    try:
        parent_request, _, _ = _decode_committed_gate_view_v2(
            view,
            domain,
            kind=kind,
            reader=cast(GovernanceStateReaderV2, store),
        )
        parent_head = _head_from_view_v2(view, domain)
    except Exception:
        return _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/snapshot/parent_transition_id",
            GovernanceFailureStageV2.LOAD,
        )
    snapshot = request.snapshot
    parent = parent_request.snapshot
    if (
        parent.revision != snapshot.parent_revision
        or parent.transition_id != snapshot.parent_transition_id
        or parent.snapshot_root != snapshot.parent_snapshot_root
    ):
        return _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/snapshot/parent_snapshot_root",
            GovernanceFailureStageV2.PRECONDITION,
        )
    return parent, parent_head


def _verify_source_v2(
    request: GateRequestV2,
    source: object,
    parent: GateSnapshotV2 | None,
    *,
    kind: GateKindV2,
) -> tuple[str, tuple[GovernanceReadPreconditionV2, ...]]:
    if kind == "stop":
        if type(source) is not VerifiedCommitStopSourceV2:
            raise TypeError("commit stop source type is invalid")
        if type(request) is not CommitStopRequestV2 or (
            parent is not None and type(parent) is not CommitStopSnapshotV2
        ):
            raise TypeError("commit stop request or parent type is invalid")
        return verify_commit_stop_request_source_v2(
            request,
            source=source,
            committed_parent_snapshot=parent,
        )
    if type(source) is not VerifiedCommitPermissionSourceV2:
        raise TypeError("commit permission source type is invalid")
    if type(request) is not CommitPermissionRequestV2 or (
        parent is not None and type(parent) is not CommitPermissionSnapshotV2
    ):
        raise TypeError("commit permission request or parent type is invalid")
    return verify_commit_permission_request_source_v2(
        request,
        source=source,
        committed_parent_snapshot=parent,
    )


def _load_dependency_heads_v2(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: GateRequestV2,
    preconditions: tuple[GovernanceReadPreconditionV2, ...],
) -> tuple[GovernanceHeadV2, ...] | GovernanceCommitAttemptV2:
    expected_by_stream = {
        getattr(request.snapshot.dependencies, f"{name}_stream_ref"): getattr(
            request.snapshot.dependencies, f"{name}_transition_id"
        )
        for name in ("replay", "risk", "verification", "membership", "support")
    }
    heads = []
    for precondition in preconditions:
        try:
            head = store.load_head_v2(request.scope_ref, precondition.stream_ref)
        except KeyError:
            return _failure_attempt(
                request,
                AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
                "/dependencies",
                GovernanceFailureStageV2.PRECONDITION,
            )
        if type(head) is not GovernanceHeadV2:
            return _failure_attempt(
                request,
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/dependencies",
                GovernanceFailureStageV2.LOAD,
            )
        detached = GovernanceHeadV2.from_dict(head.to_dict())
        if (
            detached.domain_root != domain.domain_root
            or detached.scope_ref != domain.scope_ref
            or detached.stream_ref != precondition.stream_ref
        ):
            return _failure_attempt(
                request,
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/dependencies",
                GovernanceFailureStageV2.LOAD,
            )
        if (
            detached.revision != precondition.expected_revision
            or detached.head_root != precondition.expected_root
            or detached.transition_id != expected_by_stream.get(detached.stream_ref)
        ):
            return _failure_attempt(
                request,
                AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
                "/dependencies",
                GovernanceFailureStageV2.PRECONDITION,
            )
        heads.append(detached)
    if len(heads) != 5:
        return _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/dependencies",
            GovernanceFailureStageV2.VALIDATION,
        )
    return tuple(heads)


def _committed_view_matches_request_v2(
    view: GovernanceCommitViewV2,
    request: GateRequestV2,
    session: _GovernanceAuthoritySessionStateV2,
    *,
    kind: GateKindV2,
) -> bool:
    try:
        committed, binding, _ = _decode_committed_gate_view_v2(
            view,
            _session_domain(session),
            kind=kind,
            reader=cast(GovernanceStateReaderV2, session.store),
        )
    except Exception:
        return False
    return committed.to_dict() == request.to_dict() and binding == _session_binding(
        session
    )


def _failure_from_session(
    session: _GovernanceAuthoritySessionStateV2,
    request: GateRequestV2,
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
    request: GateRequestV2,
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


__all__: tuple[str, ...] = ()
