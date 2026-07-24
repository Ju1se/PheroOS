"""StateStore-backed authority operations for durable Hybrid replay v2.

Portable snapshots are integrity records, not authority.  This module grants
authority only after the selected StateStore proves committed inclusion and,
when a snapshot is consumed as the next replay parent, currentness.
"""

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
    _scoped_manifest_authority_matches_domain_v2,
    _session_binding,
    _session_domain,
    _session_grant_precondition,
    _session_lifecycle_precondition,
)
from pheroos.governance._authority_store_v2_contracts.foundation import (
    GovernanceFailureStageV2,
)
from pheroos.governance._hybrid_replay_v2.source import (
    VerifiedHybridSourceStepV2,
    _verified_hybrid_source_manifest_v2,
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
from pheroos.governance._hybrid_replay_v2.contracts import (
    HYBRID_REPLAY_STATE_SCHEMA_V2,
    HybridReplayAdvanceRequestV2,
    HybridReplaySnapshotV2,
)


_HYBRID_REPLAY_STATE_FIELDS = frozenset(
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
class VerifiedHybridReplayStateV2:
    """Opaque local view whose every observation is reverified by StateStore.

    The object deliberately owns no issuance token.  Its identity never grants
    authority: the historical receipt and exact state records are checked on
    every property access, and current replay use performs an additional
    position check.
    """

    __slots__ = ("_domain", "_reader", "_receipt_root", "_request")

    def __new__(cls, *_args: object, **_kwargs: object) -> VerifiedHybridReplayStateV2:
        raise TypeError("VerifiedHybridReplayStateV2 cannot be constructed directly")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedHybridReplayStateV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedHybridReplayStateV2 is immutable")

    def __copy__(self) -> VerifiedHybridReplayStateV2:
        _verified_state_view(self)
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> VerifiedHybridReplayStateV2:
        _verified_state_view(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedHybridReplayStateV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedHybridReplayStateV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("VerifiedHybridReplayStateV2 is not portable")

    def __repr__(self) -> str:
        return "<VerifiedHybridReplayStateV2 redacted>"

    @property
    def snapshot(self) -> HybridReplaySnapshotV2:
        request, _ = _verified_state_view(self)
        return HybridReplaySnapshotV2.from_dict(request.snapshot.to_dict())

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

    @property
    def observed_revision(self) -> int:
        _, view = _verified_state_view(self)
        assert view.position_observation is not None
        return view.position_observation.observed_revision

    @property
    def observed_head_root(self) -> str:
        _, view = _verified_state_view(self)
        assert view.position_observation is not None
        return view.position_observation.observed_head_root


def open_hybrid_replay_authority_session_v2(
    capability: GovernanceIssuerCapabilityV2,
    request: HybridReplayAdvanceRequestV2,
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


def advance_hybrid_replay_state_v2(
    request: HybridReplayAdvanceRequestV2,
    *,
    source: object = None,
    authority_session: object = None,
) -> GovernanceCommitAttemptV2:
    """Validate and atomically advance one durable replay lineage.

    The prepared request is reconstructed from the context-bound v2 source
    proof.  For non-genesis advances the parent passed to that verifier is
    always loaded from the parent's historical committed transition, never
    from caller input or current complete-replacement state.  ``source`` may
    be omitted only when the exact request/session binding already reconciles
    to a committed Store transition.
    """

    _require_request(request)
    session, failure = _validated_session_or_failure(authority_session, request)
    if failure is not None:
        return failure
    assert session is not None
    store = cast(GovernanceStateStoreV2, session.store)
    domain = _session_domain(session)

    # Reconciliation precedes revocation, lifecycle, and source-step checks so
    # an exact retry remains observable after atomic publication or sealing.
    existing = _reconcile(
        store,
        domain,
        request.stream_ref,
        request.transition_id,
        lambda view: _committed_view_matches_request(view, request, session),
    )
    if existing is not None:
        return existing

    # A recovery retry is established by the exact committed request/session
    # binding above and does not need the now-consumed ephemeral source proof.
    # A new transition still requires that proof before any write or source
    # projection is attempted.
    source_failure = _hybrid_source_failure(request, source, domain)
    if source_failure is not None:
        return source_failure
    assert type(source) is VerifiedHybridSourceStepV2

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

    continuity_failure = _continuity_failure(request, parent_snapshot)
    if continuity_failure is not None:
        return _failure_from_session(session, request, *continuity_failure)

    try:
        # Local import keeps this Store authority layer independent from the
        # deterministic projection implementation and avoids an import cycle.
        from pheroos.governance._hybrid_replay_v2.projection import (
            verify_hybrid_replay_request_source_v2,
        )

        verify_hybrid_replay_request_source_v2(
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
    read_set_root = _read_set(observed).root()
    state = _state_records(request, _session_binding(session))
    event = _hybrid_replay_event(
        request,
        _session_binding(session),
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
        state_records=state,
        event=event,
    )


def _hybrid_source_failure(
    request: HybridReplayAdvanceRequestV2,
    source: object,
    domain: AuthorityDomainV2,
) -> GovernanceCommitAttemptV2 | None:
    """Validate the private source proof before any authoritative read/write."""

    if type(source) is not VerifiedHybridSourceStepV2:
        return _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/source",
            GovernanceFailureStageV2.VALIDATION,
        )
    try:
        manifest = _verified_hybrid_source_manifest_v2(source)
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


def rehydrate_hybrid_replay_state_v2(
    payload: object,
    *,
    domain: AuthorityDomainV2,
    state_reader: GovernanceStateReaderV2,
) -> VerifiedHybridReplayStateV2:
    """Rehydrate a portable request only after historical Store verification."""

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
    receipt_root = view.committed_transition.receipt.receipt_root
    return _make_verified_state(
        state_reader=state_reader,
        domain=domain,
        request=request,
        receipt_root=receipt_root,
    )


def hybrid_replay_state_is_current_v2(state: object) -> bool:
    """Return whether a genuine wrapper still names the Store's current head."""

    try:
        _, view = _verified_state_view(state)
        assert view.position_observation is not None
        return view.position_observation.position is GovernanceCommitPositionV2.CURRENT
    except Exception:
        return False


def require_current_hybrid_replay_state_v2(
    state: object,
) -> HybridReplaySnapshotV2:
    """Return a detached snapshot only while its verified commit is current."""

    request, view = _verified_state_view(state)
    assert view.position_observation is not None
    if view.position_observation.position is not GovernanceCommitPositionV2.CURRENT:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/position",
        )
    return HybridReplaySnapshotV2.from_dict(request.snapshot.to_dict())


def _validated_session_or_failure(
    candidate: object,
    request: HybridReplayAdvanceRequestV2,
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
    request: HybridReplayAdvanceRequestV2,
) -> tuple[HybridReplaySnapshotV2 | None, GovernanceHeadV2] | GovernanceCommitAttemptV2:
    snapshot = request.snapshot
    if snapshot.parent_revision == 0:
        parent_snapshot = None
        parent_head = GovernanceHeadV2.genesis(domain, request.stream_ref)
    else:
        loaded = _load_committed_parent(store, domain, request)
        if isinstance(loaded, GovernanceCommitAttemptV2):
            return loaded
        parent_snapshot, parent_head = loaded
        # A COMMITTED view carries the Store's dynamic position observation.
        # Under StateStore v2, SUPERSEDED means that this exact included entry
        # has a legal successor in the stream's single CAS order.  Rewalking
        # every intervening entry here would duplicate Store verification and
        # make one stale attempt O(history).  The atomic read-set comparison
        # below remains the authority for whether the parent is still current.
    return parent_snapshot, parent_head


def _load_committed_parent(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    request: HybridReplayAdvanceRequestV2,
) -> tuple[HybridReplaySnapshotV2, GovernanceHeadV2] | GovernanceCommitAttemptV2:
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
    view_failure = _parent_view_failure(view, request)
    if view_failure is not None:
        return view_failure
    assert view.committed_transition is not None
    try:
        parent_request, _ = _decode_committed_view(view, domain)
        parent_head = _head_from_committed_view(view, domain)
    except (TypeError, ValueError, GovernanceAuthorityBindingErrorV2):
        return _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/snapshot/parent_transition_id",
            GovernanceFailureStageV2.LOAD,
        )
    parent_snapshot = parent_request.snapshot
    receipt = view.committed_transition.receipt
    if (
        parent_snapshot.revision != snapshot.parent_revision
        or parent_snapshot.transition_id != snapshot.parent_transition_id
        or parent_snapshot.snapshot_root != snapshot.parent_snapshot_root
        or receipt.revision != parent_snapshot.revision
        or receipt.transition_id != parent_snapshot.transition_id
    ):
        return _failure_attempt(
            request,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/snapshot/parent_snapshot_root",
            GovernanceFailureStageV2.PRECONDITION,
        )
    return parent_snapshot, parent_head


def _parent_view_failure(
    view: GovernanceCommitViewV2,
    request: HybridReplayAdvanceRequestV2,
) -> GovernanceCommitAttemptV2 | None:
    if view.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE:
        assert view.failure is not None
        return _failure_attempt(
            request,
            view.failure.code,
            view.failure.path,
            view.failure.stage,
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
    return None


def _continuity_failure(
    request: HybridReplayAdvanceRequestV2,
    parent: HybridReplaySnapshotV2 | None,
) -> tuple[AuthorityDiagnosticCodeV2, str] | None:
    snapshot = request.snapshot
    if parent is None:
        return None
    immutable_bindings = (
        "domain_root",
        "scope_ref",
        "manifest_root",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "stream_ref",
        "candidate_projection_root",
        "policy_projection_root",
        "topology_projection_root",
    )
    if any(
        getattr(snapshot, field) != getattr(parent, field)
        for field in immutable_bindings
    ):
        return (
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/snapshot",
        )
    if (
        snapshot.revision != parent.revision + 1
        or snapshot.current_step <= parent.current_step
        or snapshot.observed_epoch < parent.observed_epoch
    ):
        return (
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/snapshot/revision",
        )
    current_receipts = {
        (item["kind"], item["event_id"]): _portable_projection(item)
        for item in snapshot.replay_receipts
    }
    for receipt in parent.replay_receipts:
        key = (receipt["kind"], receipt["event_id"])
        if current_receipts.get(key) != _portable_projection(receipt):
            return (
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/snapshot/replay_receipts",
            )
    return None


def _head_from_committed_view(
    view: GovernanceCommitViewV2,
    domain: AuthorityDomainV2,
) -> GovernanceHeadV2:
    assert view.committed_transition is not None
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
    request: HybridReplayAdvanceRequestV2,
    session_binding: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": HYBRID_REPLAY_STATE_SCHEMA_V2,
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.stream_ref,
        "transition_id": request.transition_id,
        "request_root": request.request_root,
        "request": request.to_dict(),
        "snapshot_root": request.snapshot.snapshot_root,
        "snapshot": request.snapshot.to_dict(),
        "session_binding": _portable_projection(session_binding),
    }


def _decode_state_records(
    value: object,
    domain: AuthorityDomainV2,
) -> tuple[HybridReplayAdvanceRequestV2, dict[str, Any]]:
    projected = _portable_projection(value)
    # PreparedGovernanceTransitionV2 owns a frozen JSON mapping, so its
    # detached portable projection is necessarily an exact dictionary.
    assert type(projected) is dict
    state = cast(dict[str, Any], projected)
    if set(state) != _HYBRID_REPLAY_STATE_FIELDS:
        raise ValueError("Hybrid replay committed state fields are invalid")
    if (
        state["schema"] != HYBRID_REPLAY_STATE_SCHEMA_V2
        or state["domain_root"] != domain.domain_root
        or state["scope_ref"] != domain.scope_ref
    ):
        raise ValueError("Hybrid replay committed state domain binding is invalid")
    request = HybridReplayAdvanceRequestV2.from_dict(state["request"])
    snapshot = HybridReplaySnapshotV2.from_dict(state["snapshot"])
    if (
        state["stream_ref"] != request.stream_ref
        or state["transition_id"] != request.transition_id
        or state["request_root"] != request.request_root
        or state["snapshot_root"] != request.snapshot.snapshot_root
        or snapshot.to_dict() != request.snapshot.to_dict()
        or request.domain_root != domain.domain_root
        or request.scope_ref != domain.scope_ref
    ):
        raise ValueError("Hybrid replay committed state payload is mismatched")
    binding = _validate_stored_session_binding(state["session_binding"], request)
    return request, binding


def _validate_stored_session_binding(
    value: object,
    request: HybridReplayAdvanceRequestV2,
) -> dict[str, Any]:
    projected = _portable_projection(value)
    if type(projected) is not dict or set(projected) != _SESSION_BINDING_FIELDS:
        raise ValueError("Hybrid replay committed session binding fields are invalid")
    binding = cast(dict[str, Any], projected)
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
    observed = (
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
    if observed != expected:
        raise ValueError("Hybrid replay committed session binding is mismatched")
    for field in ("grant_ref", "grant_root", "grant_binding_ref"):
        if type(binding[field]) is not str or not binding[field]:
            raise ValueError("Hybrid replay committed grant binding is invalid")
    # Reconstruct the exact Protocol-owned preconditions so bool-as-int,
    # malformed roots, and out-of-range revisions cannot compare equal to a
    # typed read-set entry during historical verification.
    GovernanceReadPreconditionV2(
        stream_ref=governance_issuer_grant_stream_ref_v2(
            request.scope_ref,
            cast(str, binding["grant_ref"]),
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
    request: HybridReplayAdvanceRequestV2,
    session: Any,
) -> bool:
    try:
        committed_request, binding = _decode_committed_view(
            view, _session_domain(session)
        )
    except (TypeError, ValueError, GovernanceAuthorityBindingErrorV2):
        return False
    return bool(
        committed_request.to_dict() == request.to_dict()
        and binding == _session_binding(session)
    )


def _decode_committed_view(
    view: GovernanceCommitViewV2,
    domain: AuthorityDomainV2,
) -> tuple[HybridReplayAdvanceRequestV2, dict[str, Any]]:
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
    # A committed view for the non-lifecycle Hybrid replay stream can only
    # carry the transition arm of the closed commit-batch union.
    assert transition is not None
    request, binding = _decode_state_records(transition.state_records, domain)
    receipt = view.committed_transition.receipt
    if (
        receipt.revision != request.snapshot.revision
        or receipt.stream_ref != request.stream_ref
        or receipt.transition_id != request.transition_id
    ):
        raise ValueError("Hybrid replay committed receipt is mismatched")
    _validate_committed_read_set(view, request, binding)
    expected_event = _hybrid_replay_event(
        request,
        binding,
        parent_head_root=receipt.parent_root,
        read_set_root=view.committed_transition.batch.read_set.root(),
    )
    events = view.committed_transition.batch.trace_batch.events
    if len(events) != 1 or events[0] != expected_event:
        raise ValueError("Hybrid replay committed trace lineage is mismatched")
    return request, binding


def _validate_committed_read_set(
    view: GovernanceCommitViewV2,
    request: HybridReplayAdvanceRequestV2,
    binding: Mapping[str, Any],
) -> None:
    assert view.committed_transition is not None
    receipt = view.committed_transition.receipt
    read_entries = view.committed_transition.batch.read_set.entries
    entries = {
        item.stream_ref: (item.expected_revision, item.expected_root)
        for item in read_entries
    }
    # GovernanceAuthorityReadSetV2 already enforces unique stream refs.
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
        raise ValueError("Hybrid replay committed authority read set is mismatched")


def _load_verified_request_view(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    expected_request: HybridReplayAdvanceRequestV2,
    *,
    expected_receipt_root: str | None,
) -> tuple[HybridReplayAdvanceRequestV2, GovernanceCommitViewV2]:
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
        request, _ = _decode_committed_view(view, domain)
    except GovernanceAuthorityBindingErrorV2:
        raise
    except (TypeError, ValueError) as exc:
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


def _verified_state_view(
    state: object,
) -> tuple[HybridReplayAdvanceRequestV2, GovernanceCommitViewV2]:
    if type(state) is not VerifiedHybridReplayStateV2:
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
    if type(request) is not HybridReplayAdvanceRequestV2:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        )
    if type(receipt_root) is not str:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/receipt_root",
        )
    detached = HybridReplayAdvanceRequestV2.from_dict(request.to_dict())
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
    request: HybridReplayAdvanceRequestV2,
    receipt_root: str,
) -> VerifiedHybridReplayStateV2:
    handle = object.__new__(VerifiedHybridReplayStateV2)
    object.__setattr__(handle, "_reader", state_reader)
    object.__setattr__(handle, "_domain", AuthorityDomainV2.from_dict(domain.to_dict()))
    object.__setattr__(
        handle,
        "_request",
        HybridReplayAdvanceRequestV2.from_dict(request.to_dict()),
    )
    object.__setattr__(handle, "_receipt_root", receipt_root)
    return handle


def _hybrid_replay_event(
    request: HybridReplayAdvanceRequestV2,
    session_binding: Mapping[str, Any],
    *,
    parent_head_root: str,
    read_set_root: str,
) -> TraceEvent:
    snapshot = request.snapshot
    binding = cast(dict[str, Any], _portable_projection(session_binding))
    return TraceEvent(
        event_type="hybrid_replay_advanced",
        protocol_id="pheroos.protocol.v2",
        target=request.target_ref,
        reason="atomically advance one durable hybrid replay lineage",
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
            "candidate_set_root": snapshot.candidate_projection_root,
            "hybrid_policy_root": snapshot.policy_projection_root,
            "effective_policy_root": snapshot.effective_policy_root,
            "topology_root": snapshot.topology_projection_root,
            "revision": snapshot.revision,
            "current_step": snapshot.current_step,
            "parent_transition_id": (
                None if snapshot.revision == 1 else snapshot.parent_transition_id
            ),
            "parent_snapshot_root": (
                None if snapshot.revision == 1 else snapshot.parent_snapshot_root
            ),
            "parent_head_root": parent_head_root,
            "snapshot_root": snapshot.snapshot_root,
            "memory_root": snapshot.active_trails_root,
            "replay_receipt_root": snapshot.replay_receipts_root,
            "source_step_root": snapshot.source_step_root,
            "source_trace_root": snapshot.source_trace_set_root,
            "read_set_root": read_set_root,
        },
    )


def _request_from_portable(payload: object) -> HybridReplayAdvanceRequestV2:
    if type(payload) is HybridReplayAdvanceRequestV2:
        payload = (payload).to_dict()
    try:
        return HybridReplayAdvanceRequestV2.from_dict(payload)
    except (TypeError, ValueError) as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        ) from exc


def _failure_from_session(
    session: Any,
    request: HybridReplayAdvanceRequestV2,
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
    request: HybridReplayAdvanceRequestV2,
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


def _require_request(request: object) -> None:
    if type(request) is not HybridReplayAdvanceRequestV2:
        raise TypeError(
            "Hybrid replay authority operation requires exact "
            "HybridReplayAdvanceRequestV2"
        )


def _require_domain(domain: object) -> None:
    if type(domain) is not AuthorityDomainV2:
        raise TypeError("Hybrid replay rehydration requires exact AuthorityDomainV2")


def _require_state_reader(reader: object) -> None:
    if not isinstance(reader, GovernanceStateReaderV2):
        raise TypeError("Hybrid replay rehydration requires StateReader v2")


__all__ = [
    "VerifiedHybridReplayStateV2",
    "advance_hybrid_replay_state_v2",
    "hybrid_replay_state_is_current_v2",
    "open_hybrid_replay_authority_session_v2",
    "rehydrate_hybrid_replay_state_v2",
    "require_current_hybrid_replay_state_v2",
]
