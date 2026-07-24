"""Atomic StateStore-backed mutation path for Distributed Commit v2."""

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
from pheroos.governance._distributed_v2.events import _distributed_event_v2
from pheroos.governance._distributed_v2.request import DistributedAdvanceRequestV2
from pheroos.governance._distributed_v2.source import (
    VerifiedDistributedAdvanceSourceV2,
    verify_distributed_source_v2,
)
from pheroos.governance._distributed_v2.state_contracts import (
    DISTRIBUTED_GENESIS_TRANSITION_ID_V2,
    DistributedLaneSnapshotV2,
    distributed_genesis_snapshot_root_v2,
)
from pheroos.governance._distributed_v2.state_records import (
    _decode_committed_distributed_view_v2,
    _distributed_state_records_v2,
    _head_from_view_v2,
    _required_actions,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
)


def open_distributed_authority_session_v2(
    capability: GovernanceIssuerCapabilityV2,
    request: DistributedAdvanceRequestV2,
) -> GovernanceAuthoritySessionV2:
    """Open one exact EVALUATE_QUORUM binding for a distributed mutation."""

    _require_request(request)
    actions = _required_actions(request.snapshot)
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
        action_refs=actions,
    )
    state = _governance_authority_session_state_v2(session)
    if state.capability.issuer_ref != request.mutation_issuer_ref:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/mutation_issuer_ref",
        )
    return session


def advance_distributed_commit_v2(
    request: DistributedAdvanceRequestV2,
    *,
    source: object = None,
    authority_session: object = None,
) -> GovernanceCommitAttemptV2:
    """Atomically recheck the complete read-set and replace one fixed lane."""

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
    prepared = _validated_source_and_heads(store, domain, request, source)
    if isinstance(prepared, GovernanceCommitAttemptV2):
        return prepared
    snapshot, parent_head, dependency_heads = prepared
    observed: tuple[GovernanceHeadV2 | GovernanceReadPreconditionV2, ...] = (
        parent_head,
        *dependency_heads,
        _session_grant_precondition(session),
        _session_lifecycle_precondition(session),
    )
    read_set_root = _read_set(observed).root()
    binding = _session_binding(session)
    records = _distributed_state_records_v2(request, binding)
    event = _distributed_event_v2(
        request,
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


def _validated_source_and_heads(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: DistributedAdvanceRequestV2,
    source: object,
) -> (
    tuple[DistributedLaneSnapshotV2, GovernanceHeadV2, tuple[GovernanceHeadV2, ...]]
    | GovernanceCommitAttemptV2
):
    if type(source) is not VerifiedDistributedAdvanceSourceV2:
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
    dependency_heads = _load_dependency_heads(store, domain, request)
    if isinstance(dependency_heads, GovernanceCommitAttemptV2):
        return dependency_heads
    try:
        snapshot = verify_distributed_source_v2(
            request,
            source=source,
            committed_parent_snapshot=parent_snapshot,
        )
    except Exception:
        if _dependency_or_parent_changed(store, domain, request, parent_head):
            return _stale(request, "/dependencies")
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source",
            GovernanceFailureStageV2.VALIDATION,
        )
    if snapshot.to_dict() != request.snapshot.to_dict():
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/snapshot",
            GovernanceFailureStageV2.VALIDATION,
        )
    return snapshot, parent_head, dependency_heads


def _validated_session(
    candidate: object,
    request: DistributedAdvanceRequestV2,
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
        _required_actions(request.snapshot),
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
    request: DistributedAdvanceRequestV2,
) -> (
    tuple[DistributedLaneSnapshotV2 | None, GovernanceHeadV2]
    | GovernanceCommitAttemptV2
):
    if request.parent_revision == 0:
        head = _load_exact_head(store, domain, request, request.stream_ref)
        if isinstance(head, GovernanceCommitAttemptV2):
            return head
        if head.revision != 0:
            return _stale(request, "/parent_revision")
        if (
            request.parent_transition_id != DISTRIBUTED_GENESIS_TRANSITION_ID_V2
            or request.parent_snapshot_root
            != distributed_genesis_snapshot_root_v2(request.snapshot.lane)
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
    except Exception:
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/parent_transition_id",
            GovernanceFailureStageV2.LOAD,
        )
    if view.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE:
        return _finality_failure(request, view)
    try:
        _, parent, _ = _decode_committed_distributed_view_v2(view, domain, reader=store)
        head = _head_from_view_v2(view, domain)
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
        return _stale(request, "/parent_revision")
    return parent, head


def _load_dependency_heads(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: DistributedAdvanceRequestV2,
) -> tuple[GovernanceHeadV2, ...] | GovernanceCommitAttemptV2:
    heads: list[GovernanceHeadV2] = []
    for dependency in request.snapshot.dependencies:
        loaded = _load_exact_head(store, domain, request, dependency.stream_ref)
        if isinstance(loaded, GovernanceCommitAttemptV2):
            return loaded
        if (
            loaded.revision != dependency.revision
            or loaded.head_root != dependency.head_root
            or (
                loaded.revision > 0 and loaded.transition_id != dependency.transition_id
            )
        ):
            return _stale(request, "/dependencies")
        heads.append(loaded)
    if len({item.stream_ref for item in heads}) != len(heads):
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/dependencies",
            GovernanceFailureStageV2.VALIDATION,
        )
    return tuple(heads)


def _load_exact_head(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: DistributedAdvanceRequestV2,
    stream_ref: str,
) -> GovernanceHeadV2 | GovernanceCommitAttemptV2:
    try:
        head = store.load_head_v2(request.scope_ref, stream_ref)
    except Exception:
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/scope_ref",
            GovernanceFailureStageV2.LOAD,
        )
    if (
        type(head) is not GovernanceHeadV2
        or head.domain_root != domain.domain_root
        or head.scope_ref != domain.scope_ref
        or head.stream_ref != stream_ref
    ):
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/dependencies",
            GovernanceFailureStageV2.LOAD,
        )
    return head


def _dependency_or_parent_changed(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: DistributedAdvanceRequestV2,
    parent: GovernanceHeadV2,
) -> bool:
    loaded_parent = _load_exact_head(store, domain, request, request.stream_ref)
    if (
        not isinstance(loaded_parent, GovernanceHeadV2)
        or loaded_parent.to_dict() != parent.to_dict()
    ):
        return True
    loaded = _load_dependency_heads(store, domain, request)
    return isinstance(loaded, GovernanceCommitAttemptV2)


def _committed_view_matches(
    view: GovernanceCommitViewV2,
    request: DistributedAdvanceRequestV2,
    session: _GovernanceAuthoritySessionStateV2,
) -> bool:
    try:
        committed, _, binding = _decode_committed_distributed_view_v2(
            view,
            _session_domain(session),
            reader=cast(GovernanceStateStoreV2, session.store),
        )
    except Exception:
        return False
    return committed.to_dict() == request.to_dict() and binding == _session_binding(
        session
    )


def _failure_from_session(
    session: _GovernanceAuthoritySessionStateV2,
    request: DistributedAdvanceRequestV2,
    code: AuthorityDiagnosticCodeV2,
    path: str,
) -> GovernanceCommitAttemptV2:
    return _failure(request, code, path, GovernanceFailureStageV2.PRECONDITION)


def _finality_failure(
    request: DistributedAdvanceRequestV2,
    view: GovernanceCommitViewV2,
) -> GovernanceCommitAttemptV2:
    if view.failure is None:
        return _failure(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
            "/parent_transition_id",
            GovernanceFailureStageV2.LOAD,
        )
    return _failure(
        request,
        view.failure.code,
        view.failure.path,
        GovernanceFailureStageV2.LOAD,
    )


def _stale(
    request: DistributedAdvanceRequestV2, path: str
) -> GovernanceCommitAttemptV2:
    return _failure(
        request,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        path,
        GovernanceFailureStageV2.PRECONDITION,
    )


def _failure(
    request: DistributedAdvanceRequestV2,
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
    if type(value) is not DistributedAdvanceRequestV2:
        raise TypeError("distributed operation requires exact request")


__all__ = [
    "advance_distributed_commit_v2",
    "open_distributed_authority_session_v2",
]
