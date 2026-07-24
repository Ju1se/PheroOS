"""StateStore-backed authority operations for durable Commit Replay v2."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NoReturn, SupportsIndex, cast, final

from pheroos.protocol.authority_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceReadPreconditionV2,
)
from pheroos.trace import TraceEvent

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceAuthoritySessionV2,
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerOperationV2,
    _governance_authority_session_state_v2,
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    _bound_failure_attempt,
    _canonical_commit_view_v2,
    _commit_transition,
    _current_session_grant_failure,
    _current_session_lifecycle_failure,
    _open_governance_authority_session_binding_v2,
    _portable_projection,
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
    _require_root,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
    GovernanceStateStoreV2,
)
from pheroos.governance._commit_state_v2.contracts import (
    COMMIT_REPLAY_STATE_SCHEMA_V2,
    CommitReplayAdvanceRequestV2,
    CommitReplaySnapshotV2,
)
from pheroos.governance._commit_state_v2.source import (
    VerifiedCommitReplaySourceV2,
    _expected_source_roots,
    verify_commit_replay_request_source_v2,
)


_STATE_FIELDS = frozenset(
    {
        "schema",
        "domain_root",
        "scope_ref",
        "stream_ref",
        "transition_id",
        "request_root",
        "request",
        "snapshot_root",
        "snapshot",
        "source_context_root",
        "receipt_addition_root",
        "session_binding",
    }
)
_SESSION_BINDING_FIELDS = frozenset(
    {
        "domain_root",
        "scope_ref",
        "run_ref",
        "request_ref",
        "request_root",
        "operation",
        "observed_epoch",
        "grant_ref",
        "grant_root",
        "grant_binding_ref",
        "grant_expected_revision",
        "grant_expected_root",
        "lifecycle_expected_revision",
        "lifecycle_expected_root",
        "target_refs",
        "action_refs",
    }
)


@final
class VerifiedCommitReplayStateV2:
    """Opaque view whose every observation is reverified by StateStore."""

    __slots__ = ("_domain", "_reader", "_receipt_root", "_request")

    def __new__(cls, *_args: object, **_kwargs: object) -> VerifiedCommitReplayStateV2:
        raise TypeError("VerifiedCommitReplayStateV2 cannot be constructed directly")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedCommitReplayStateV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedCommitReplayStateV2 is immutable")

    def __copy__(self) -> VerifiedCommitReplayStateV2:
        _verified_state_view(self)
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> VerifiedCommitReplayStateV2:
        _verified_state_view(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedCommitReplayStateV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedCommitReplayStateV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("VerifiedCommitReplayStateV2 is not portable")

    def __repr__(self) -> str:
        return "<VerifiedCommitReplayStateV2 redacted>"

    @property
    def snapshot(self) -> CommitReplaySnapshotV2:
        request, _ = _verified_state_view(self)
        return CommitReplaySnapshotV2.from_dict(request.snapshot.to_dict())

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


def open_commit_replay_authority_session_v2(
    capability: GovernanceIssuerCapabilityV2,
    request: CommitReplayAdvanceRequestV2,
) -> GovernanceAuthoritySessionV2:
    """Open one exact ADVANCE_REPLAY run/target/request binding."""

    _require_request(request)
    return _open_governance_authority_session_binding_v2(
        capability,
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        request_ref=request.advance_ref,
        request_root=request.request_root,
        operation=GovernanceIssuerOperationV2.ADVANCE_REPLAY,
        run_ref=request.run_ref,
        observed_epoch=request.observed_epoch,
        target_refs=(request.target_ref,),
        action_refs=(),
    )


def advance_commit_replay_state_v2(
    request: CommitReplayAdvanceRequestV2,
    *,
    source: object = None,
    authority_session: object = None,
) -> GovernanceCommitAttemptV2:
    """Atomically advance replay bookkeeping after exact source/session checks."""

    _require_request(request)
    session, failure = _validated_session_or_failure(authority_session, request)
    if failure is not None:
        return failure
    assert session is not None
    store = cast(GovernanceStateStoreV2, session.store)
    domain = _session_domain(session)

    # Exact recovery precedes grant/lifecycle/source checks.  A response lost
    # after atomic publication remains recoverable after revoke or seal.
    existing = _reconcile(
        store,
        domain,
        request.stream_ref,
        request.transition_id,
        lambda view: _committed_view_matches_request(view, request, session),
    )
    if existing is not None:
        return existing
    if type(source) is not VerifiedCommitReplaySourceV2:
        return _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source",
            GovernanceFailureStageV2.VALIDATION,
        )
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
        verify_commit_replay_request_source_v2(
            request,
            source=source,
            committed_parent_snapshot=parent_snapshot,
        )
        source_context_root, receipt_addition_root = _expected_source_roots(
            request, parent_snapshot
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
    read_set_root = _read_set(observed).root()
    binding = _session_binding(session)
    records = _state_records(
        request,
        binding,
        source_context_root=source_context_root,
        receipt_addition_root=receipt_addition_root,
    )
    event = _commit_replay_event(
        request,
        binding,
        source_context_root=source_context_root,
        receipt_addition_root=receipt_addition_root,
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


def rehydrate_commit_replay_state_v2(
    payload: object,
    *,
    domain: AuthorityDomainV2,
    state_reader: GovernanceStateReaderV2,
) -> VerifiedCommitReplayStateV2:
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
        state_reader, domain, request, expected_receipt_root=None
    )
    assert view.committed_transition is not None
    return _make_verified_state(
        state_reader=state_reader,
        domain=domain,
        request=request,
        receipt_root=view.committed_transition.receipt.receipt_root,
    )


def commit_replay_state_is_current_v2(state: object) -> bool:
    try:
        _, view = _verified_state_view(state)
        assert view.position_observation is not None
        return view.position_observation.position is GovernanceCommitPositionV2.CURRENT
    except Exception:
        return False


def require_current_commit_replay_state_v2(
    state: object,
) -> CommitReplaySnapshotV2:
    request, view = _verified_state_view(state)
    assert view.position_observation is not None
    if view.position_observation.position is not GovernanceCommitPositionV2.CURRENT:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/position",
        )
    return CommitReplaySnapshotV2.from_dict(request.snapshot.to_dict())


def _validated_session_or_failure(
    candidate: object,
    request: CommitReplayAdvanceRequestV2,
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
        GovernanceIssuerOperationV2.ADVANCE_REPLAY,
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


def _load_parent_snapshot(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: CommitReplayAdvanceRequestV2,
) -> tuple[CommitReplaySnapshotV2 | None, GovernanceHeadV2] | GovernanceCommitAttemptV2:
    snapshot = request.snapshot
    if snapshot.parent_revision == 0:
        return None, GovernanceHeadV2.genesis(domain, request.stream_ref)
    loaded = _load_committed_parent(store, domain, request)
    if isinstance(loaded, GovernanceCommitAttemptV2):
        return loaded
    return loaded


def _load_committed_parent(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: CommitReplayAdvanceRequestV2,
) -> tuple[CommitReplaySnapshotV2, GovernanceHeadV2] | GovernanceCommitAttemptV2:
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
        parent_request, _, _, _ = _decode_committed_view(view, domain, reader=None)
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


def _continuity_failure(
    request: CommitReplayAdvanceRequestV2,
    parent: CommitReplaySnapshotV2 | None,
) -> tuple[AuthorityDiagnosticCodeV2, str] | None:
    snapshot = request.snapshot
    if parent is None:
        return None
    immutable = (
        "domain_root",
        "scope_ref",
        "manifest_root",
        "commit_policy_root",
        "profile",
        "assurance",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "stream_ref",
        "initialized_at_step",
    )
    if any(getattr(snapshot, field) != getattr(parent, field) for field in immutable):
        return AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH, "/snapshot"
    if (
        snapshot.revision != parent.revision + 1
        or snapshot.current_step < parent.current_step
        or snapshot.observed_epoch < parent.observed_epoch
    ):
        return (
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/snapshot/revision",
        )
    current = {item.receipt_root: item.to_dict() for item in snapshot.receipts}
    for receipt in parent.receipts:
        if current.get(receipt.receipt_root) != receipt.to_dict():
            return (
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/snapshot/receipts",
            )
    return None


def _head_from_view(
    view: GovernanceCommitViewV2, domain: AuthorityDomainV2
) -> GovernanceHeadV2:
    if view.committed_transition is None:
        raise ValueError("commit replay parent has no committed transition")
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


def _state_records(
    request: CommitReplayAdvanceRequestV2,
    session_binding: Mapping[str, Any],
    *,
    source_context_root: str,
    receipt_addition_root: str,
) -> dict[str, Any]:
    return {
        "schema": COMMIT_REPLAY_STATE_SCHEMA_V2,
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.stream_ref,
        "transition_id": request.transition_id,
        "request_root": request.request_root,
        "request": request.to_dict(),
        "snapshot_root": request.snapshot.snapshot_root,
        "snapshot": request.snapshot.to_dict(),
        "source_context_root": source_context_root,
        "receipt_addition_root": receipt_addition_root,
        "session_binding": _portable_projection(session_binding),
    }


def _decode_state_records(
    value: object, domain: AuthorityDomainV2
) -> tuple[CommitReplayAdvanceRequestV2, dict[str, Any], str, str]:
    projected = _portable_projection(value)
    if type(projected) is not dict:
        raise TypeError("commit replay state must be an exact object")
    state = cast(dict[str, Any], projected)
    if set(state) != _STATE_FIELDS:
        raise ValueError("commit replay committed state fields are invalid")
    if (
        state["schema"] != COMMIT_REPLAY_STATE_SCHEMA_V2
        or state["domain_root"] != domain.domain_root
        or state["scope_ref"] != domain.scope_ref
    ):
        raise ValueError("commit replay committed state domain is mismatched")
    request = CommitReplayAdvanceRequestV2.from_dict(state["request"])
    snapshot = CommitReplaySnapshotV2.from_dict(state["snapshot"])
    if (
        state["stream_ref"] != request.stream_ref
        or state["transition_id"] != request.transition_id
        or state["request_root"] != request.request_root
        or state["snapshot_root"] != request.snapshot.snapshot_root
        or snapshot.to_dict() != request.snapshot.to_dict()
        or request.domain_root != domain.domain_root
        or request.scope_ref != domain.scope_ref
    ):
        raise ValueError("commit replay committed state payload is mismatched")
    _require_root(state["source_context_root"], "commit replay source_context_root")
    _require_root(state["receipt_addition_root"], "commit replay receipt_addition_root")
    binding = _validate_stored_session_binding(state["session_binding"], request)
    return (
        request,
        binding,
        cast(str, state["source_context_root"]),
        cast(str, state["receipt_addition_root"]),
    )


def _validate_stored_session_binding(
    value: object, request: CommitReplayAdvanceRequestV2
) -> dict[str, Any]:
    projected = _portable_projection(value)
    if type(projected) is not dict or set(projected) != _SESSION_BINDING_FIELDS:
        raise ValueError("commit replay session binding fields are invalid")
    binding = cast(dict[str, Any], projected)
    observed: tuple[object, ...] = (
        binding["domain_root"],
        binding["scope_ref"],
        binding["run_ref"],
        binding["request_ref"],
        binding["request_root"],
        binding["operation"],
        binding["observed_epoch"],
        binding["target_refs"],
        binding["action_refs"],
    )
    expected: tuple[object, ...] = (
        request.domain_root,
        request.scope_ref,
        request.run_ref,
        request.advance_ref,
        request.request_root,
        GovernanceIssuerOperationV2.ADVANCE_REPLAY.value,
        request.observed_epoch,
        [request.target_ref],
        [],
    )
    if observed != expected:
        raise ValueError("commit replay stored session binding is mismatched")
    for field in ("grant_ref", "grant_root", "grant_binding_ref"):
        if type(binding[field]) is not str or not binding[field]:
            raise ValueError("commit replay stored grant binding is invalid")
    GovernanceReadPreconditionV2(
        stream_ref=governance_issuer_grant_stream_ref_v2(
            request.scope_ref, cast(str, binding["grant_ref"])
        ),
        expected_revision=binding["grant_expected_revision"],
        expected_root=binding["grant_expected_root"],
    )
    GovernanceReadPreconditionV2(
        stream_ref=GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        expected_revision=binding["lifecycle_expected_revision"],
        expected_root=binding["lifecycle_expected_root"],
    )
    return binding


def _committed_view_matches_request(
    view: GovernanceCommitViewV2,
    request: CommitReplayAdvanceRequestV2,
    session: Any,
) -> bool:
    try:
        committed, binding, _, _ = _decode_committed_view(
            view,
            _session_domain(session),
            reader=cast(GovernanceStateReaderV2, session.store),
        )
    except (
        AttributeError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        GovernanceAuthorityBindingErrorV2,
    ):
        return False
    return committed.to_dict() == request.to_dict() and binding == _session_binding(
        session
    )


def _decode_committed_view(
    view: GovernanceCommitViewV2,
    domain: AuthorityDomainV2,
    *,
    reader: GovernanceStateReaderV2 | None,
) -> tuple[CommitReplayAdvanceRequestV2, dict[str, Any], str, str]:
    view = _canonical_commit_view_v2(view)
    if (
        view.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or view.committed_transition is None
        or view.position_observation is None
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/transition_id",
        )
    transition = view.committed_transition.batch.transition
    if transition is None:
        raise ValueError("commit replay committed batch has no transition")
    request, binding, source_root, addition_root = _decode_state_records(
        transition.state_records, domain
    )
    receipt = view.committed_transition.receipt
    if (
        receipt.revision != request.snapshot.revision
        or receipt.stream_ref != request.stream_ref
        or receipt.transition_id != request.transition_id
    ):
        raise ValueError("commit replay committed receipt is mismatched")
    _validate_committed_read_set(view, request, binding)
    expected_event = _commit_replay_event(
        request,
        binding,
        source_context_root=source_root,
        receipt_addition_root=addition_root,
        parent_head_root=receipt.parent_root,
        read_set_root=view.committed_transition.batch.read_set.root(),
    )
    events = view.committed_transition.batch.trace_batch.events
    if len(events) != 1 or events[0] != expected_event:
        raise ValueError("commit replay committed trace lineage is mismatched")
    if reader is not None:
        parent = _load_parent_from_reader(reader, domain, request)
        continuity = _continuity_failure(request, parent)
        if continuity is not None:
            raise ValueError("commit replay committed replacement is not continuous")
        expected_source, expected_addition = _expected_source_roots(request, parent)
        if (source_root, addition_root) != (expected_source, expected_addition):
            raise ValueError("commit replay committed source lineage is mismatched")
    return request, binding, source_root, addition_root


def _validate_committed_read_set(
    view: GovernanceCommitViewV2,
    request: CommitReplayAdvanceRequestV2,
    binding: Mapping[str, Any],
) -> None:
    assert view.committed_transition is not None
    receipt = view.committed_transition.receipt
    read_entries = view.committed_transition.batch.read_set.entries
    entries = {
        item.stream_ref: (item.expected_revision, item.expected_root)
        for item in read_entries
    }
    if len(entries) != len(read_entries):
        raise ValueError("commit replay read set contains duplicate streams")
    grant_stream = governance_issuer_grant_stream_ref_v2(
        request.scope_ref, cast(str, binding["grant_ref"])
    )
    expected = {
        request.stream_ref: (request.snapshot.parent_revision, receipt.parent_root),
        grant_stream: (
            binding["grant_expected_revision"],
            binding["grant_expected_root"],
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2: (
            binding["lifecycle_expected_revision"],
            binding["lifecycle_expected_root"],
        ),
    }
    if entries != expected:
        raise ValueError("commit replay authority read set is mismatched")


def _load_verified_request_view(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    expected_request: CommitReplayAdvanceRequestV2,
    *,
    expected_receipt_root: str | None,
) -> tuple[CommitReplayAdvanceRequestV2, GovernanceCommitViewV2]:
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
        request, _, _, _ = _decode_committed_view(view, domain, reader=reader)
    except GovernanceAuthorityBindingErrorV2:
        raise
    except (AttributeError, KeyError, IndexError, TypeError, ValueError) as exc:
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


def _load_parent_from_reader(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: CommitReplayAdvanceRequestV2,
) -> CommitReplaySnapshotV2 | None:
    if request.snapshot.parent_revision == 0:
        return None
    try:
        parent_view = _canonical_commit_view_v2(
            reader.load_commit_view_v2(
                request.scope_ref,
                request.stream_ref,
                request.snapshot.parent_transition_id,
            ),
            invalid_path="/snapshot/parent_transition_id",
        )
    except (KeyError, GovernanceAuthorityBindingErrorV2) as exc:
        raise ValueError("commit replay historical parent is unavailable") from exc
    if parent_view.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE:
        code = (
            AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
            if parent_view.failure is None
            else parent_view.failure.code
        )
        path = (
            "/snapshot/parent_transition_id"
            if parent_view.failure is None
            else parent_view.failure.path
        )
        raise GovernanceAuthorityBindingErrorV2(code, path)
    parent_request, _, _, _ = _decode_committed_view(parent_view, domain, reader=None)
    parent = parent_request.snapshot
    if (
        parent.revision != request.snapshot.parent_revision
        or parent.transition_id != request.snapshot.parent_transition_id
        or parent.snapshot_root != request.snapshot.parent_snapshot_root
    ):
        raise ValueError("commit replay historical parent binding is mismatched")
    return parent


def _verified_state_view(
    state: object,
) -> tuple[CommitReplayAdvanceRequestV2, GovernanceCommitViewV2]:
    if type(state) is not VerifiedCommitReplayStateV2:
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
    _require_state_reader(reader)
    if (
        type(request) is not CommitReplayAdvanceRequestV2
        or type(receipt_root) is not str
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        )
    detached = CommitReplayAdvanceRequestV2.from_dict(request.to_dict())
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
    request: CommitReplayAdvanceRequestV2,
    receipt_root: str,
) -> VerifiedCommitReplayStateV2:
    handle = object.__new__(VerifiedCommitReplayStateV2)
    object.__setattr__(handle, "_reader", state_reader)
    object.__setattr__(handle, "_domain", AuthorityDomainV2.from_dict(domain.to_dict()))
    object.__setattr__(
        handle, "_request", CommitReplayAdvanceRequestV2.from_dict(request.to_dict())
    )
    object.__setattr__(handle, "_receipt_root", receipt_root)
    return handle


def _commit_replay_event(
    request: CommitReplayAdvanceRequestV2,
    session_binding: Mapping[str, Any],
    *,
    source_context_root: str,
    receipt_addition_root: str,
    parent_head_root: str,
    read_set_root: str,
) -> TraceEvent:
    snapshot = request.snapshot
    binding = cast(dict[str, Any], _portable_projection(session_binding))
    return TraceEvent(
        event_type="commit_replay_advanced",
        protocol_id="pheroos.protocol.v2",
        target=request.target_ref,
        reason="atomically advance one durable commit replay lineage",
        lineage={
            "domain_root": request.domain_root,
            "scope_ref": request.scope_ref,
            "stream_ref": request.stream_ref,
            "transition_id": request.transition_id,
            "run_ref": request.run_ref,
            "request_ref": request.advance_ref,
            "request_root": request.request_root,
            "grant_ref": binding["grant_ref"],
            "grant_root": binding["grant_root"],
            "grant_binding_ref": binding["grant_binding_ref"],
            "operation": GovernanceIssuerOperationV2.ADVANCE_REPLAY.value,
            "observed_epoch": request.observed_epoch,
            "session_binding": binding,
            "target_ref": request.target_ref,
            "advance_ref": request.advance_ref,
            "protocol_ref": snapshot.protocol_ref,
            "manifest_root": snapshot.manifest_root,
            "commit_policy_root": snapshot.commit_policy_root,
            "profile": snapshot.profile,
            "assurance": snapshot.assurance.value,
            "revision": snapshot.revision,
            "current_step": snapshot.current_step,
            "parent_transition_id": snapshot.parent_transition_id,
            "parent_snapshot_root": snapshot.parent_snapshot_root,
            "parent_head_root": parent_head_root,
            "snapshot_root": snapshot.snapshot_root,
            "replay_receipt_root": snapshot.receipt_root,
            "receipt_addition_root": receipt_addition_root,
            "source_context_root": source_context_root,
            "read_set_root": read_set_root,
        },
    )


def _request_from_portable(payload: object) -> CommitReplayAdvanceRequestV2:
    if type(payload) is CommitReplayAdvanceRequestV2:
        payload = (payload).to_dict()
    try:
        return CommitReplayAdvanceRequestV2.from_dict(payload)
    except (TypeError, ValueError) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        ) from exc


def _failure_from_session(
    session: Any,
    request: CommitReplayAdvanceRequestV2,
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
    request: CommitReplayAdvanceRequestV2,
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
    if type(value) is not CommitReplayAdvanceRequestV2:
        raise TypeError("commit replay operation requires exact advance request v2")


def _require_domain(value: object) -> None:
    if type(value) is not AuthorityDomainV2:
        raise TypeError("commit replay rehydration requires exact AuthorityDomainV2")


def _require_state_reader(value: object) -> None:
    try:
        conforms = isinstance(value, GovernanceStateReaderV2)
    except Exception as exc:
        raise TypeError("commit replay rehydration requires StateReader v2") from exc
    if not conforms:
        raise TypeError("commit replay rehydration requires StateReader v2")


__all__ = [
    "VerifiedCommitReplayStateV2",
    "advance_commit_replay_state_v2",
    "commit_replay_state_is_current_v2",
    "open_commit_replay_authority_session_v2",
    "rehydrate_commit_replay_state_v2",
    "require_current_commit_replay_state_v2",
]
