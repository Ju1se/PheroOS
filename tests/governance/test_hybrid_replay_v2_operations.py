from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import pickle
from typing import Any

import pytest

from pheroos.governance._swarm.replay import replay_state_from_hybrid_step
from pheroos.governance._authority_session_v2.contracts import (
    GovernanceDomainRetirementRequestV2,
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    open_governance_authority_session_v2,
    retire_governance_domain_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance._authority_v2 import (
    FAILURE_STAGE_AFTER_TRACE_STAGING_V2,
    InMemoryGovernanceStateStoreV2,
)
from pheroos.governance._hybrid_replay_v2.contracts import (
    HybridReplayAdvanceRequestV2,
    HybridReplaySnapshotV2,
)
from pheroos.governance._hybrid_replay_v2.operations import (
    VerifiedHybridReplayStateV2,
    advance_hybrid_replay_state_v2,
    hybrid_replay_state_is_current_v2,
    open_hybrid_replay_authority_session_v2,
    rehydrate_hybrid_replay_state_v2,
    require_current_hybrid_replay_state_v2,
)
from pheroos.governance._hybrid_replay_v2.projection import (
    build_hybrid_replay_advance_request_v2,
)
from pheroos.governance._hybrid_replay_v2.source import VerifiedHybridSourceStepV2
from pheroos.governance._swarm.records import HybridCollectiveStep
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    AuthorityDiagnosticCodeV2,
)
from tests.governance.test_hybrid_replay_v2_projection import (
    _fixture,
    _source,
    _step,
)


def _root(label: str) -> str:
    from hashlib import sha256

    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _plain(value: object) -> object:
    from collections.abc import Mapping, Sequence

    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True)
class _Context:
    domain: AuthorityDomainV2
    store: InMemoryGovernanceStateStoreV2
    grant: GovernanceIssuerGrantV2
    capability: GovernanceIssuerCapabilityV2


_SOURCES: dict[str, VerifiedHybridSourceStepV2] = {}


def _context(
    *,
    scope_ref: str = "scope:hybrid-replay-operations",
    operations: tuple[GovernanceIssuerOperationV2, ...] = (
        GovernanceIssuerOperationV2.ADVANCE_REPLAY,
    ),
    failure_injector=None,
) -> _Context:
    domain = AuthorityDomainV2(
        policy_version=AUTHORITY_POLICY_VERSION_V2,
        profile=AUTHORITY_LOCAL_PROFILE_V2,
        wire_version=AUTHORITY_WIRE_VERSION_V2,
        canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref=scope_ref,
    )
    protocol, _, _, _ = _fixture()
    grant = GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:hybrid-replay",
        grant_ref="grant:hybrid-replay",
        grant_binding_ref=_root("hybrid-replay-grant-binding"),
        operations=operations,
        target_refs=(protocol.quorum_policy.target,),
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100,
        revocation_generation=0,
    )
    store = InMemoryGovernanceStateStoreV2((domain,), failure_injector=failure_injector)
    activation = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:hybrid-replay:grant-activation",
        1,
    )
    assert activation.disposition is GovernanceCommitDispositionV2.COMMITTED
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        "run:hybrid-replay",
        3,
    )
    return _Context(domain, store, grant, capability)


def _request(
    context: _Context,
    step: HybridCollectiveStep,
    *,
    advance_ref: str,
    current_step: int,
    parent: HybridReplaySnapshotV2 | None = None,
) -> HybridReplayAdvanceRequestV2:
    source = _source(
        step,
        current_step=current_step,
        parent=parent,
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref="run:hybrid-replay",
        observed_epoch=3,
    )
    request = build_hybrid_replay_advance_request_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref="run:hybrid-replay",
        observed_epoch=3,
        advance_ref=advance_ref,
        source=source,
    )
    _SOURCES[request.request_root] = source
    return request


def _source_for(request: HybridReplayAdvanceRequestV2) -> VerifiedHybridSourceStepV2:
    return _SOURCES[request.request_root]


def _advance(
    context: _Context,
    request: HybridReplayAdvanceRequestV2,
    step: HybridCollectiveStep,
):
    del step
    session = open_hybrid_replay_authority_session_v2(
        context.capability,
        request,
    )
    return advance_hybrid_replay_state_v2(
        request,
        source=_source_for(request),
        authority_session=session,
    )


def _assert_failure(
    attempt: Any,
    disposition: GovernanceCommitDispositionV2,
    code: AuthorityDiagnosticCodeV2,
) -> None:
    assert attempt.disposition is disposition
    assert attempt.failure is not None
    assert attempt.failure.code is code
    assert attempt.committed_transition is None


def test_store_vertical_slice_commits_exact_state_trace_and_restart_wrapper() -> None:
    context = _context(
        operations=(
            GovernanceIssuerOperationV2.ADVANCE_REPLAY,
            GovernanceIssuerOperationV2.RETIRE_DOMAIN,
        )
    )
    step = _step()
    request = _request(
        context,
        step,
        advance_ref="advance:hybrid:one",
        current_step=1,
    )

    attempt = _advance(context, request, step)

    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert attempt.committed_transition is not None
    batch = attempt.committed_transition.batch
    assert {item.stream_ref for item in batch.read_set.entries} == {
        request.stream_ref,
        governance_issuer_grant_stream_ref_v2(
            context.domain.scope_ref, context.grant.grant_ref
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    event = batch.trace_batch.events[0]
    assert event.event_type == "hybrid_replay_advanced"
    assert event.lineage["snapshot_root"] == request.snapshot.snapshot_root
    assert event.lineage["read_set_root"] == batch.read_set.root()
    state = batch.transition.state_records if batch.transition is not None else {}
    assert _plain(state["request"]) == request.to_dict()
    assert _plain(state["snapshot"]) == request.snapshot.to_dict()

    portable = json.loads(request.canonical_bytes())
    restored = rehydrate_hybrid_replay_state_v2(
        portable,
        domain=context.domain,
        state_reader=context.store,
    )
    assert type(restored) is VerifiedHybridReplayStateV2
    assert restored.snapshot == request.snapshot
    assert restored.position is GovernanceCommitPositionV2.CURRENT
    assert restored.receipt_root == attempt.committed_transition.receipt.receipt_root
    assert restored.observed_revision == 1
    assert hybrid_replay_state_is_current_v2(restored)
    assert require_current_hybrid_replay_state_v2(restored) == request.snapshot
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(restored)
    tampered = rehydrate_hybrid_replay_state_v2(
        portable,
        domain=context.domain,
        state_reader=context.store,
    )
    object.__setattr__(tampered, "_receipt_root", _root("substituted-receipt"))
    assert not hybrid_replay_state_is_current_v2(tampered)
    with pytest.raises(Exception, match="committed_transition_invalid"):
        _ = tampered.snapshot

    grant_stream = governance_issuer_grant_stream_ref_v2(
        context.domain.scope_ref, context.grant.grant_ref
    )
    retirement = GovernanceDomainRetirementRequestV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref="run:hybrid-replay",
        request_ref="request:hybrid-replay:seal-after-commit",
        transition_id="transition:hybrid-replay:seal-after-commit",
        stream_refs=tuple(sorted((grant_stream, request.stream_ref))),
        reason_ref="reason:complete",
        observed_epoch=3,
    )
    retire_session = open_governance_authority_session_v2(
        context.capability, retirement
    )
    assert (
        retire_governance_domain_v2(
            retirement, authority_session=retire_session
        ).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    assert restored.position is GovernanceCommitPositionV2.SEALED
    assert restored.snapshot == request.snapshot
    assert not hybrid_replay_state_is_current_v2(restored)


def test_portable_values_and_direct_wrapper_construction_never_grant_authority() -> (
    None
):
    context = _context()
    step = _step()
    request = _request(
        context,
        step,
        advance_ref="advance:hybrid:raw",
        current_step=1,
    )
    assert not hybrid_replay_state_is_current_v2(request)
    assert not hybrid_replay_state_is_current_v2(request.snapshot)
    assert not hybrid_replay_state_is_current_v2(request.to_dict())
    with pytest.raises(TypeError, match="cannot be constructed"):
        VerifiedHybridReplayStateV2()


def test_missing_or_cross_request_session_is_rejected_before_store_mutation() -> None:
    context = _context(scope_ref="scope:hybrid-replay-session-binding")
    step = _step()
    request = _request(
        context,
        step,
        advance_ref="advance:hybrid:session-one",
        current_step=1,
    )
    missing = advance_hybrid_replay_state_v2(
        request,
        source=_source_for(request),
    )
    _assert_failure(
        missing,
        GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED,
    )

    other = _request(
        context,
        step,
        advance_ref="advance:hybrid:session-two",
        current_step=1,
    )
    other_session = open_hybrid_replay_authority_session_v2(context.capability, other)
    mismatched = advance_hybrid_replay_state_v2(
        request,
        source=_source_for(request),
        authority_session=other_session,
    )
    _assert_failure(
        mismatched,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
    )
    assert (
        context.store.load_head_v2(request.scope_ref, request.stream_ref).revision == 0
    )


def test_exact_duplicate_reconciles_and_same_transition_different_body_conflicts() -> (
    None
):
    context = _context()
    first_step = _step()
    first = _request(
        context,
        first_step,
        advance_ref="advance:hybrid:idempotent",
        current_step=1,
    )
    committed = _advance(context, first, first_step)
    duplicate = _advance(context, first, first_step)
    assert committed.committed_transition is not None
    assert duplicate.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert duplicate.committed_transition is not None
    assert (
        duplicate.committed_transition.receipt.receipt_root
        == committed.committed_transition.receipt.receipt_root
    )
    assert context.store.load_head_v2(first.scope_ref, first.stream_ref).revision == 1

    other_step = _step(
        adjustment_value=1.3,
        adjustment_id="trace:adjustment:conflict",
    )
    conflict = _request(
        context,
        other_step,
        advance_ref=first.advance_ref,
        current_step=1,
    )
    rejected = _advance(context, conflict, other_step)
    _assert_failure(
        rejected,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT,
    )


def test_exact_duplicate_and_conflict_reconcile_before_revoked_grant() -> None:
    context = _context(scope_ref="scope:hybrid-replay-reconcile-revoked")
    step = _step()
    request = _request(
        context,
        step,
        advance_ref="advance:hybrid:reconcile-revoked",
        current_step=1,
    )
    session = open_hybrid_replay_authority_session_v2(context.capability, request)
    committed = advance_hybrid_replay_state_v2(
        request,
        source=_source_for(request),
        authority_session=session,
    )
    assert committed.committed_transition is not None

    other_step = _step(
        adjustment_value=1.3,
        adjustment_id="trace:adjustment:reconcile-revoked-conflict",
    )
    conflict = _request(
        context,
        other_step,
        advance_ref=request.advance_ref,
        current_step=1,
    )
    conflict_session = open_hybrid_replay_authority_session_v2(
        context.capability, conflict
    )
    assert (
        revoke_governance_issuer_grant_v2(
            context.store,
            context.domain,
            context.grant.grant_ref,
            "transition:hybrid-replay:reconcile-revoke",
            4,
        ).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )

    exact = advance_hybrid_replay_state_v2(
        request,
        source=_source_for(request),
        authority_session=session,
    )
    assert exact.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert exact.committed_transition is not None
    assert exact.position_observation is not None
    assert exact.position_observation.position is GovernanceCommitPositionV2.CURRENT
    assert (
        exact.committed_transition.receipt.receipt_root
        == committed.committed_transition.receipt.receipt_root
    )
    rejected = advance_hybrid_replay_state_v2(
        conflict,
        source=_source_for(conflict),
        authority_session=conflict_session,
    )
    _assert_failure(
        rejected,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT,
    )


def test_exact_duplicate_and_conflict_reconcile_before_sealed_lifecycle() -> None:
    context = _context(
        scope_ref="scope:hybrid-replay-reconcile-sealed",
        operations=(
            GovernanceIssuerOperationV2.ADVANCE_REPLAY,
            GovernanceIssuerOperationV2.RETIRE_DOMAIN,
        ),
    )
    step = _step()
    request = _request(
        context,
        step,
        advance_ref="advance:hybrid:reconcile-sealed",
        current_step=1,
    )
    session = open_hybrid_replay_authority_session_v2(context.capability, request)
    committed = advance_hybrid_replay_state_v2(
        request,
        source=_source_for(request),
        authority_session=session,
    )
    assert committed.committed_transition is not None

    other_step = _step(
        adjustment_value=1.3,
        adjustment_id="trace:adjustment:reconcile-sealed-conflict",
    )
    conflict = _request(
        context,
        other_step,
        advance_ref=request.advance_ref,
        current_step=1,
    )
    conflict_session = open_hybrid_replay_authority_session_v2(
        context.capability, conflict
    )
    grant_stream = governance_issuer_grant_stream_ref_v2(
        context.domain.scope_ref, context.grant.grant_ref
    )
    retirement = GovernanceDomainRetirementRequestV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref="run:hybrid-replay",
        request_ref="request:hybrid-replay:reconcile-seal",
        transition_id="transition:hybrid-replay:reconcile-seal",
        stream_refs=tuple(sorted((grant_stream, request.stream_ref))),
        reason_ref="reason:complete",
        observed_epoch=3,
    )
    retire_session = open_governance_authority_session_v2(
        context.capability, retirement
    )
    assert (
        retire_governance_domain_v2(
            retirement, authority_session=retire_session
        ).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )

    exact = advance_hybrid_replay_state_v2(
        request,
        source=_source_for(request),
        authority_session=session,
    )
    assert exact.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert exact.committed_transition is not None
    assert exact.position_observation is not None
    assert exact.position_observation.position is GovernanceCommitPositionV2.SEALED
    assert (
        exact.committed_transition.receipt.receipt_root
        == committed.committed_transition.receipt.receipt_root
    )
    rejected = advance_hybrid_replay_state_v2(
        conflict,
        source=_source_for(conflict),
        authority_session=conflict_session,
    )
    _assert_failure(
        rejected,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT,
    )


def test_concurrent_genesis_forks_have_one_commit_and_one_read_set_retry() -> None:
    context = _context(scope_ref="scope:hybrid-replay-concurrent")
    first_step = _step()
    second_step = _step(
        adjustment_value=1.3,
        adjustment_id="trace:adjustment:concurrent-second",
    )
    first = _request(
        context,
        first_step,
        advance_ref="advance:hybrid:concurrent-first",
        current_step=1,
    )
    second = _request(
        context,
        second_step,
        advance_ref="advance:hybrid:concurrent-second",
        current_step=1,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        attempts = tuple(
            executor.map(
                lambda item: _advance(context, item[0], item[1]),
                ((first, first_step), (second, second_step)),
            )
        )

    assert {item.disposition for item in attempts} == {
        GovernanceCommitDispositionV2.COMMITTED,
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
    }
    retry = next(
        item
        for item in attempts
        if item.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    )
    assert retry.failure is not None
    assert retry.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    assert context.store.load_head_v2(first.scope_ref, first.stream_ref).revision == 1


def test_successor_supersedes_historical_wrapper_and_stale_fork_retries() -> None:
    context = _context()
    first_step = _step()
    first = _request(
        context,
        first_step,
        advance_ref="advance:hybrid:first",
        current_step=1,
    )
    assert _advance(context, first, first_step).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    historical = rehydrate_hybrid_replay_state_v2(
        first.to_dict(), domain=context.domain, state_reader=context.store
    )

    first_replay = replay_state_from_hybrid_step(first_step)
    second_step = _step(
        current_step=2,
        replay_state=first_replay,
        policy=first_step.effective_policy,
        adjustment_field="pheromone_exploration_floor",
        adjustment_value=0.25,
        adjustment_id="trace:adjustment:second",
    )
    second = _request(
        context,
        second_step,
        advance_ref="advance:hybrid:second",
        current_step=2,
        parent=first.snapshot,
    )
    assert _advance(context, second, second_step).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    assert historical.position is GovernanceCommitPositionV2.SUPERSEDED
    assert historical.snapshot == first.snapshot
    assert not hybrid_replay_state_is_current_v2(historical)
    with pytest.raises(
        Exception,
        match=AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE.value,
    ):
        require_current_hybrid_replay_state_v2(historical)

    stale_step = _step(
        current_step=3,
        replay_state=first_replay,
        policy=first_step.effective_policy,
        adjustment_field="pheromone_exploration_floor",
        adjustment_value=0.3,
        adjustment_id="trace:adjustment:stale-fork",
    )
    stale = _request(
        context,
        stale_step,
        advance_ref="advance:hybrid:stale-fork",
        current_step=3,
        parent=first.snapshot,
    )
    retry = _advance(context, stale, stale_step)
    _assert_failure(
        retry,
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
    )
    assert context.store.load_head_v2(stale.scope_ref, stale.stream_ref).revision == 2


def test_valid_snapshot_memory_or_receipt_substitution_fails_source_rebuild() -> None:
    context = _context()
    step = _step()
    request = _request(
        context,
        step,
        advance_ref="advance:hybrid:substitution",
        current_step=1,
    )
    payload = deepcopy(request.to_dict())
    snapshot = payload["snapshot"]
    assert isinstance(snapshot, dict)
    snapshot["replay_receipts"] = []
    for field in (
        "replay_receipts_root",
        "source_lineage_root",
        "state_root",
        "snapshot_root",
    ):
        snapshot[field] = ""
    payload["request_root"] = ""
    substituted = HybridReplayAdvanceRequestV2.from_dict(payload)
    _SOURCES[substituted.request_root] = _source_for(request)

    rejected = _advance(context, substituted, step)
    _assert_failure(
        rejected,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
    )
    assert rejected.failure is not None
    assert rejected.failure.path == "/source"


class _HistoricalOnlyReader:
    def __init__(self, store: InMemoryGovernanceStateStoreV2) -> None:
        self.store = store
        self.state_reads = 0

    def load_head_v2(self, scope_ref: str, stream_ref: str):  # type: ignore[no-untyped-def]
        return self.store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(self, scope_ref: str, stream_ref: str):  # type: ignore[no-untyped-def]
        del scope_ref, stream_ref
        self.state_reads += 1
        raise AssertionError("rehydration must not read complete replacement state")

    def load_commit_view_v2(  # type: ignore[no-untyped-def]
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ):
        return self.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )


def test_rehydrate_uses_historical_transition_not_current_replacement_state() -> None:
    context = _context()
    first_step = _step()
    first = _request(
        context,
        first_step,
        advance_ref="advance:hybrid:historical-one",
        current_step=1,
    )
    assert _advance(context, first, first_step).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    second_step = _step(
        current_step=2,
        replay_state=replay_state_from_hybrid_step(first_step),
        policy=first_step.effective_policy,
        adjustment_field="pheromone_exploration_floor",
        adjustment_value=0.2,
        adjustment_id="trace:adjustment:historical-two",
    )
    second = _request(
        context,
        second_step,
        advance_ref="advance:hybrid:historical-two",
        current_step=2,
        parent=first.snapshot,
    )
    assert _advance(context, second, second_step).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )

    reader = _HistoricalOnlyReader(context.store)
    restored = rehydrate_hybrid_replay_state_v2(
        first.to_dict(), domain=context.domain, state_reader=reader
    )
    assert restored.snapshot.snapshot_root == first.snapshot.snapshot_root
    assert restored.position is GovernanceCommitPositionV2.SUPERSEDED
    assert reader.state_reads == 0


def test_rehydrate_rejects_deleted_payload_and_cross_scope_domain() -> None:
    context = _context()
    step = _step()
    request = _request(
        context,
        step,
        advance_ref="advance:hybrid:rehydrate",
        current_step=1,
    )
    assert _advance(context, request, step).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    deleted = request.to_dict()
    del deleted["request_root"]
    with pytest.raises(Exception, match="request_root"):
        rehydrate_hybrid_replay_state_v2(
            deleted, domain=context.domain, state_reader=context.store
        )

    other = _context(scope_ref="scope:hybrid-replay-other")
    with pytest.raises(Exception, match="authority_scope_mismatch"):
        rehydrate_hybrid_replay_state_v2(
            request.to_dict(), domain=other.domain, state_reader=context.store
        )


def test_revoked_grant_and_sealed_lifecycle_fail_closed() -> None:
    revoked_context = _context(scope_ref="scope:hybrid-replay-revoked")
    step = _step()
    revoked_request = _request(
        revoked_context,
        step,
        advance_ref="advance:hybrid:revoked",
        current_step=1,
    )
    revoked_session = open_hybrid_replay_authority_session_v2(
        revoked_context.capability, revoked_request
    )
    assert (
        revoke_governance_issuer_grant_v2(
            revoked_context.store,
            revoked_context.domain,
            revoked_context.grant.grant_ref,
            "transition:hybrid-replay:revoke",
            4,
        ).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    denied = advance_hybrid_replay_state_v2(
        revoked_request,
        source=_source_for(revoked_request),
        authority_session=revoked_session,
    )
    _assert_failure(
        denied,
        GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED,
    )

    sealed_context = _context(
        scope_ref="scope:hybrid-replay-sealed",
        operations=(
            GovernanceIssuerOperationV2.ADVANCE_REPLAY,
            GovernanceIssuerOperationV2.RETIRE_DOMAIN,
        ),
    )
    sealed_request = _request(
        sealed_context,
        step,
        advance_ref="advance:hybrid:sealed",
        current_step=1,
    )
    sealed_session = open_hybrid_replay_authority_session_v2(
        sealed_context.capability, sealed_request
    )
    grant_stream = governance_issuer_grant_stream_ref_v2(
        sealed_context.domain.scope_ref, sealed_context.grant.grant_ref
    )
    retirement = GovernanceDomainRetirementRequestV2(
        domain_root=sealed_context.domain.domain_root,
        scope_ref=sealed_context.domain.scope_ref,
        run_ref="run:hybrid-replay",
        request_ref="request:hybrid-replay:retire",
        transition_id="transition:hybrid-replay:retire",
        stream_refs=(grant_stream,),
        reason_ref="reason:complete",
        observed_epoch=3,
    )
    retire_session = open_governance_authority_session_v2(
        sealed_context.capability, retirement
    )
    assert (
        retire_governance_domain_v2(
            retirement, authority_session=retire_session
        ).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    sealed = advance_hybrid_replay_state_v2(
        sealed_request,
        source=_source_for(sealed_request),
        authority_session=sealed_session,
    )
    _assert_failure(
        sealed,
        GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
    )


def test_trace_stage_failure_publishes_neither_state_head_nor_commit_view() -> None:
    armed = False

    def fail_after_trace(stage: str, batch: Any) -> None:
        del batch
        if armed and stage == FAILURE_STAGE_AFTER_TRACE_STAGING_V2:
            raise OSError("injected trace publication failure")

    context = _context(
        scope_ref="scope:hybrid-replay-atomicity",
        failure_injector=fail_after_trace,
    )
    step = _step()
    request = _request(
        context,
        step,
        advance_ref="advance:hybrid:atomicity",
        current_step=1,
    )
    before = context.store.snapshot_v2()
    armed = True
    unavailable = _advance(context, request, step)
    assert unavailable.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert context.store.snapshot_v2() == before
    assert (
        context.store.load_head_v2(request.scope_ref, request.stream_ref).revision == 0
    )
    assert (
        context.store.load_commit_view_v2(
            request.scope_ref, request.stream_ref, request.transition_id
        ).disposition
        is GovernanceCommitDispositionV2.INVALID
    )
