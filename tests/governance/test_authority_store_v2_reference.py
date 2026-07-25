from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from threading import Barrier
from typing import Any, cast

import pytest

import pheroos.governance._authority_v2.store as authority_store_reference
from pheroos.governance._authority_v2 import (
    FAILURE_STAGE_AFTER_ATOMIC_PUBLICATION_V2,
    FAILURE_STAGE_AFTER_IDENTITY_RECONCILIATION_V2,
    FAILURE_STAGE_AFTER_READ_SET_VALIDATION_V2,
    FAILURE_STAGE_AFTER_RECEIPT_INCLUSION_STAGING_V2,
    FAILURE_STAGE_AFTER_STATE_HEAD_STAGING_V2,
    FAILURE_STAGE_AFTER_TRACE_STAGING_V2,
    FAILURE_STAGE_BEFORE_VALIDATION_V2,
    InMemoryGovernanceStateStoreV2,
)
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDiagnosticCodeV2,
    AuthorityDomainV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceDomainSealV2,
    GovernanceFailureStageV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
    GovernanceTraceBatchV2,
    PreparedGovernanceTransitionV2,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    MAX_AUTHORITY_REVISION_V2,
    GovernanceAuthorityReadSetV2,
    GovernanceReadPreconditionV2,
)
from pheroos.trace import TraceEvent


def _domain(
    scope_ref: str = "scope:reference",
    *,
    profile: str = AUTHORITY_LOCAL_PROFILE_V2,
) -> AuthorityDomainV2:
    return AuthorityDomainV2(
        policy_version=AUTHORITY_POLICY_VERSION_V2,
        profile=profile,
        wire_version=AUTHORITY_WIRE_VERSION_V2,
        canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref=scope_ref,
    )


def _read_set(*heads: GovernanceHeadV2) -> GovernanceAuthorityReadSetV2:
    ordered = sorted(heads, key=lambda item: item.stream_ref.encode("utf-8"))
    return GovernanceAuthorityReadSetV2(
        entries=tuple(
            GovernanceReadPreconditionV2(
                stream_ref=head.stream_ref,
                expected_revision=head.revision,
                expected_root=head.head_root,
            )
            for head in ordered
        )
    )


def _transition_batch(
    store: InMemoryGovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    stream_ref: str,
    transition_id: str,
    state_records: dict[str, Any],
    *,
    observed_streams: tuple[str, ...] = (),
    observed_heads: tuple[GovernanceHeadV2, ...] | None = None,
) -> GovernanceCommitBatchV2:
    if observed_heads is None:
        refs = tuple(dict.fromkeys((*observed_streams, stream_ref)))
        heads = tuple(store.load_head_v2(domain.scope_ref, item) for item in refs)
    else:
        heads = observed_heads
    read_set = _read_set(*heads)
    target = next(item for item in heads if item.stream_ref == stream_ref)
    transition = PreparedGovernanceTransitionV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        expected_revision=target.revision,
        expected_root=target.head_root,
        read_set_root=read_set.root(),
        state_records=state_records,
    )
    trace = GovernanceTraceBatchV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        events=(
            TraceEvent(
                event_type="x-authority-v2-commit",
                protocol_id="protocol:reference-test",
                target=stream_ref,
                reason="reference store commit",
                lineage={
                    "scope_ref": domain.scope_ref,
                    "stream_ref": stream_ref,
                    "transition_id": transition_id,
                },
            ),
        ),
    )
    return GovernanceCommitBatchV2(
        domain=domain,
        scope_ref=domain.scope_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        kind="transition",
        read_set=read_set,
        trace_batch=trace,
        transition=transition,
    )


def _seal_batch(
    store: InMemoryGovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    transition_id: str,
    stream_refs: tuple[str, ...],
) -> GovernanceCommitBatchV2:
    lifecycle = store.load_head_v2(
        domain.scope_ref,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    )
    heads = (
        lifecycle,
        *(store.load_head_v2(domain.scope_ref, item) for item in stream_refs),
    )
    read_set = _read_set(*heads)
    final_heads = tuple(
        {
            "stream_ref": item.stream_ref,
            "revision": item.revision,
            "head_root": item.head_root,
        }
        for item in sorted(heads, key=lambda value: value.stream_ref.encode())
        if item.stream_ref != GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
    )
    seal = GovernanceDomainSealV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        transition_id=transition_id,
        expected_revision=lifecycle.revision,
        expected_root=lifecycle.head_root,
        final_heads=final_heads,
    )
    trace = GovernanceTraceBatchV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        transition_id=transition_id,
        events=(
            TraceEvent(
                event_type="x-authority-v2-seal",
                protocol_id="protocol:reference-test",
                target=GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
                reason="reference store seal",
                lineage={
                    "scope_ref": domain.scope_ref,
                    "stream_ref": GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
                    "transition_id": transition_id,
                    "seal_root": seal.seal_root,
                },
            ),
        ),
    )
    return GovernanceCommitBatchV2(
        domain=domain,
        scope_ref=domain.scope_ref,
        stream_ref=GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        transition_id=transition_id,
        kind="seal",
        read_set=read_set,
        trace_batch=trace,
        seal=seal,
    )


def test_reference_store_satisfies_protocol_and_defensively_snapshots() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    assert isinstance(store, GovernanceStateStoreV2)
    assert store.state_store_version == GOVERNANCE_STATE_STORE_VERSION_V2

    caller_state: dict[str, Any] = {
        "nested": {"value": 1},
        "items": ["a"],
    }
    batch = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:alpha-1",
        caller_state,
    )
    caller_state["nested"]["value"] = 99
    caller_state["items"].append("mutated")

    result = store.atomic_commit_v2(batch)
    assert result.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert result.failure is None
    assert result.position_observation is not None
    assert result.position_observation.position is GovernanceCommitPositionV2.CURRENT
    assert store.load_state_v2(domain.scope_ref, "authority:alpha") == {
        "items": ["a"],
        "nested": {"value": 1},
    }

    detached = store.load_state_v2(domain.scope_ref, "authority:alpha")
    detached["nested"]["value"] = -1
    assert store.load_state_v2(domain.scope_ref, "authority:alpha")["nested"] == {
        "value": 1
    }


def test_scope_wide_idempotency_conflict_and_historical_supersession() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    first = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:shared",
        {"value": 1},
    )
    committed = store.atomic_commit_v2(first)
    assert committed.committed_transition is not None
    receipt_root = committed.committed_transition.receipt.receipt_root

    successor = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:alpha-2",
        {"value": 2},
    )
    assert (
        store.atomic_commit_v2(successor).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )

    retry = store.atomic_commit_v2(first)
    assert retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert retry.committed_transition is not None
    assert retry.committed_transition.receipt.receipt_root == receipt_root
    assert retry.position_observation is not None
    assert retry.position_observation.position is GovernanceCommitPositionV2.SUPERSEDED

    conflicting = _transition_batch(
        store,
        domain,
        "authority:beta",
        "transition:shared",
        {"substitution": True},
    )
    conflict = store.atomic_commit_v2(conflicting)
    assert conflict.disposition is GovernanceCommitDispositionV2.INVALID
    assert conflict.failure is not None
    assert (
        conflict.failure.code
        is AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT
    )
    assert store.load_head_v2(domain.scope_ref, "authority:beta").revision == 0

    view = store.load_commit_view_v2(
        domain.scope_ref,
        "authority:alpha",
        "transition:shared",
        expected_receipt_root=receipt_root,
    )
    assert view.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert view.position_observation is not None
    assert view.position_observation.position is GovernanceCommitPositionV2.SUPERSEDED


def test_full_read_set_drift_has_no_partial_publication() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    alpha = store.load_head_v2(domain.scope_ref, "authority:alpha")
    beta = store.load_head_v2(domain.scope_ref, "authority:beta")
    dependent = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:dependent",
        {"depends_on_beta": True},
        observed_heads=(alpha, beta),
    )
    winner = _transition_batch(
        store,
        domain,
        "authority:beta",
        "transition:beta-1",
        {"value": 1},
        observed_heads=(beta,),
    )
    assert (
        store.atomic_commit_v2(winner).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    before = store.snapshot_v2()
    stale = store.atomic_commit_v2(dependent)
    assert stale.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert stale.failure is not None
    assert stale.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    assert store.snapshot_v2() == before
    assert store.load_head_v2(domain.scope_ref, "authority:alpha").revision == 0


def test_32_identical_workers_publish_one_exact_receipt() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    batch = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:once",
        {"value": 1},
    )
    with ThreadPoolExecutor(max_workers=32) as executor:
        results = list(executor.map(lambda _: store.atomic_commit_v2(batch), range(32)))
    assert {item.disposition for item in results} == {
        GovernanceCommitDispositionV2.COMMITTED
    }
    assert (
        len(
            {
                item.committed_transition.receipt.receipt_root
                for item in results
                if item.committed_transition is not None
            }
        )
        == 1
    )
    assert store.load_head_v2(domain.scope_ref, "authority:alpha").revision == 1


def test_32_conflicting_genesis_workers_have_one_winner() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    genesis = store.load_head_v2(domain.scope_ref, "authority:alpha")
    batches = tuple(
        _transition_batch(
            store,
            domain,
            "authority:alpha",
            f"transition:competitor-{index:02d}",
            {"winner": index},
            observed_heads=(genesis,),
        )
        for index in range(32)
    )
    with ThreadPoolExecutor(max_workers=32) as executor:
        results = list(executor.map(store.atomic_commit_v2, batches))
    assert (
        sum(
            item.disposition is GovernanceCommitDispositionV2.COMMITTED
            for item in results
        )
        == 1
    )
    assert (
        sum(
            item.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
            for item in results
        )
        == 31
    )
    assert store.load_head_v2(domain.scope_ref, "authority:alpha").revision == 1


@pytest.mark.parametrize(
    ("stage", "failure_stage"),
    (
        (
            FAILURE_STAGE_BEFORE_VALIDATION_V2,
            GovernanceFailureStageV2.VALIDATION,
        ),
        (
            FAILURE_STAGE_AFTER_IDENTITY_RECONCILIATION_V2,
            GovernanceFailureStageV2.RECONCILIATION,
        ),
        (
            FAILURE_STAGE_AFTER_READ_SET_VALIDATION_V2,
            GovernanceFailureStageV2.PRECONDITION,
        ),
        (
            FAILURE_STAGE_AFTER_STATE_HEAD_STAGING_V2,
            GovernanceFailureStageV2.COMMIT,
        ),
        (
            FAILURE_STAGE_AFTER_TRACE_STAGING_V2,
            GovernanceFailureStageV2.TRACE,
        ),
        (
            FAILURE_STAGE_AFTER_RECEIPT_INCLUSION_STAGING_V2,
            GovernanceFailureStageV2.COMMIT,
        ),
    ),
)
def test_prepublication_failure_boundaries_expose_zero_partial_writes(
    stage: str,
    failure_stage: GovernanceFailureStageV2,
) -> None:
    domain = _domain()

    def fail_at(current: str, _batch: GovernanceCommitBatchV2) -> None:
        if current == stage:
            raise OSError("injected availability failure")

    store = InMemoryGovernanceStateStoreV2([domain], failure_injector=fail_at)
    batch = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:failure",
        {"value": 1},
    )
    before = store.snapshot_v2()
    result = store.atomic_commit_v2(batch)
    assert result.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert result.failure is not None
    assert (
        result.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
    )
    assert result.failure.stage is failure_stage
    assert store.snapshot_v2() == before
    assert store.load_head_v2(domain.scope_ref, "authority:alpha").revision == 0


def test_postpublication_response_loss_reconciles_without_recommit() -> None:
    domain = _domain()

    def fail_after_publication(
        stage: str,
        _batch: GovernanceCommitBatchV2,
    ) -> None:
        if stage == FAILURE_STAGE_AFTER_ATOMIC_PUBLICATION_V2:
            raise OSError("response lost")

    store = InMemoryGovernanceStateStoreV2(
        [domain],
        failure_injector=fail_after_publication,
    )
    batch = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:response-loss",
        {"value": 1},
    )
    response = store.atomic_commit_v2(batch)
    assert response.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert store.load_head_v2(domain.scope_ref, "authority:alpha").revision == 1

    reconciled = store.load_commit_view_v2(
        domain.scope_ref,
        "authority:alpha",
        "transition:response-loss",
    )
    assert reconciled.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert reconciled.position_observation is not None
    assert (
        reconciled.position_observation.position is GovernanceCommitPositionV2.CURRENT
    )
    retry = store.atomic_commit_v2(batch)
    assert retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert store.load_head_v2(domain.scope_ref, "authority:alpha").revision == 1


def test_snapshot_restart_preserves_global_order_history_idempotency_and_seal() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    alpha_1 = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:alpha-1",
        {"value": 1},
    )
    assert store.atomic_commit_v2(alpha_1).committed_transition is not None
    beta_1 = _transition_batch(
        store,
        domain,
        "authority:beta",
        "transition:beta-1",
        {"value": 1},
        observed_streams=("authority:alpha",),
    )
    store.atomic_commit_v2(beta_1)
    alpha_2 = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:alpha-2",
        {"value": 2},
        observed_streams=("authority:beta",),
    )
    store.atomic_commit_v2(alpha_2)
    seal = _seal_batch(
        store,
        domain,
        "transition:seal",
        ("authority:alpha", "authority:beta"),
    )
    store.atomic_commit_v2(seal)

    snapshot = store.snapshot_v2()
    parsed = json.loads(snapshot)
    assert [
        item["batch"]["transition_id"] for item in parsed["domains"][0]["commits"]
    ] == [
        "transition:alpha-1",
        "transition:beta-1",
        "transition:alpha-2",
        "transition:seal",
    ]
    restored = InMemoryGovernanceStateStoreV2.from_snapshot_v2(snapshot)
    assert restored.snapshot_v2() == snapshot
    retry = restored.atomic_commit_v2(alpha_1)
    assert retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert retry.position_observation is not None
    assert retry.position_observation.position is GovernanceCommitPositionV2.SEALED
    restored_view = restored.load_commit_view_v2(
        domain.scope_ref,
        "authority:alpha",
        "transition:alpha-2",
    )
    assert restored_view.position_observation is not None
    assert (
        restored_view.position_observation.position is GovernanceCommitPositionV2.SEALED
    )

    parsed["domains"][0]["commits"][0], parsed["domains"][0]["commits"][1] = (
        parsed["domains"][0]["commits"][1],
        parsed["domains"][0]["commits"][0],
    )
    with pytest.raises(ValueError, match="sequence"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(
            json.dumps(parsed, separators=(",", ":"), sort_keys=True)
        )


def test_seal_completeness_history_and_postseal_denial() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    first = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:alpha-1",
        {"value": 1},
    )
    committed = store.atomic_commit_v2(first)
    assert committed.committed_transition is not None

    incomplete = _seal_batch(
        store,
        domain,
        "transition:incomplete-seal",
        (),
    )
    stale = store.atomic_commit_v2(incomplete)
    assert stale.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert (
        store.load_head_v2(
            domain.scope_ref,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        ).revision
        == 0
    )
    extra = _seal_batch(
        store,
        domain,
        "transition:extra-seal",
        ("authority:alpha", "authority:ghost"),
    )
    assert (
        store.atomic_commit_v2(extra).disposition
        is GovernanceCommitDispositionV2.RETRY_REQUIRED
    )

    seal = _seal_batch(
        store,
        domain,
        "transition:seal",
        ("authority:alpha",),
    )
    sealed = store.atomic_commit_v2(seal)
    assert sealed.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert sealed.position_observation is not None
    assert sealed.position_observation.position is GovernanceCommitPositionV2.SEALED
    old = store.load_commit_view_v2(
        domain.scope_ref,
        "authority:alpha",
        "transition:alpha-1",
        expected_receipt_root=committed.committed_transition.receipt.receipt_root,
    )
    assert old.position_observation is not None
    assert old.position_observation.position is GovernanceCommitPositionV2.SEALED
    assert seal.seal is not None
    assert old.position_observation.seal_root == seal.seal.seal_root

    postseal = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:postseal",
        {"value": 2},
    )
    denied = store.atomic_commit_v2(postseal)
    assert denied.disposition is GovernanceCommitDispositionV2.DENIED
    assert denied.failure is not None
    assert denied.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED
    exact_retry = store.atomic_commit_v2(first)
    assert exact_retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert exact_retry.position_observation is not None
    assert (
        exact_retry.position_observation.position is GovernanceCommitPositionV2.SEALED
    )
    substitution = _transition_batch(
        store,
        domain,
        "authority:alpha",
        first.transition_id,
        {"value": "substituted"},
    )
    conflict = store.atomic_commit_v2(substitution)
    assert conflict.disposition is GovernanceCommitDispositionV2.INVALID
    assert conflict.failure is not None
    assert (
        conflict.failure.code
        is AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT
    )


def test_128th_non_lifecycle_stream_is_rejected_without_partial_write() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    for index in range(127):
        stream_ref = f"authority:stream-{index:03d}"
        result = store.atomic_commit_v2(
            _transition_batch(
                store,
                domain,
                stream_ref,
                f"transition:stream-{index:03d}",
                {"index": index},
            )
        )
        assert result.disposition is GovernanceCommitDispositionV2.COMMITTED
    before = store.snapshot_v2()
    rejected = store.atomic_commit_v2(
        _transition_batch(
            store,
            domain,
            "authority:stream-127",
            "transition:stream-127",
            {"index": 127},
        )
    )
    assert rejected.disposition is GovernanceCommitDispositionV2.INVALID
    assert rejected.failure is not None
    assert (
        rejected.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_INVALID
    )
    assert rejected.failure.path == "/read_set"
    assert store.snapshot_v2() == before


def test_steady_state_uses_incremental_checkpoint_without_history_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain = _domain("scope:incremental-checkpoint")
    store = InMemoryGovernanceStateStoreV2([domain])
    replay_calls = 0
    original_replay = authority_store_reference._replay_domain_history

    def counted_replay(*args: Any, **kwargs: Any) -> Any:
        nonlocal replay_calls
        replay_calls += 1
        return original_replay(*args, **kwargs)

    monkeypatch.setattr(
        authority_store_reference,
        "_replay_domain_history",
        counted_replay,
    )
    batches: list[GovernanceCommitBatchV2] = []
    for revision in range(1, 97):
        batch = _transition_batch(
            store,
            domain,
            "authority:long-history",
            f"transition:long-history-{revision:03d}",
            {"revision": revision},
        )
        batches.append(batch)
        assert (
            store.atomic_commit_v2(batch).disposition
            is GovernanceCommitDispositionV2.COMMITTED
        )

    assert store.load_head_v2(domain.scope_ref, batches[-1].stream_ref).revision == 96
    assert store.load_state_v2(domain.scope_ref, batches[-1].stream_ref) == {
        "revision": 96
    }
    assert (
        store.load_commit_view_v2(
            domain.scope_ref,
            batches[0].stream_ref,
            batches[0].transition_id,
        ).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    assert (
        store.atomic_commit_v2(batches[-1]).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    store.snapshot_v2()
    assert replay_calls == 0

    # Private-image reflection permanently opts this test instance into the
    # expensive adversarial audit path; the next public read replays exactly
    # once and proves that the fast path did not weaken tamper detection.
    exposed = store._domains[domain.scope_ref]
    assert store.load_head_v2(domain.scope_ref, batches[-1].stream_ref).revision == 96
    assert replay_calls == 1
    object.__setattr__(
        exposed.entries[0].batch.trace_batch,
        "trace_root",
        batches[0].batch_root,
    )
    with pytest.raises(ValueError):
        store.load_state_v2(domain.scope_ref, batches[-1].stream_ref)
    assert replay_calls == 2


def test_total_view_only_returns_declared_view_dispositions() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    absent = store.load_commit_view_v2(
        domain.scope_ref,
        "authority:alpha",
        "transition:absent",
    )
    assert absent.disposition is GovernanceCommitDispositionV2.INVALID
    assert absent.committed_transition is None
    assert absent.position_observation is None
    assert absent.observed_revision == 0
    assert absent.observed_head_root is not None

    batch = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:alpha-1",
        {"value": 1},
    )
    result = store.atomic_commit_v2(batch)
    assert result.committed_transition is not None
    mismatched = store.load_commit_view_v2(
        domain.scope_ref,
        "authority:alpha",
        "transition:alpha-1",
        expected_receipt_root=batch.batch_root,
    )
    assert mismatched.disposition is GovernanceCommitDispositionV2.INVALID
    assert mismatched.failure is not None
    assert (
        mismatched.failure.code
        is AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )


def test_total_view_maps_corrupt_index_and_seal_to_invalid() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    batch = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:alpha-1",
        {"value": 1},
    )
    store.atomic_commit_v2(batch)
    image = store._domains[domain.scope_ref]
    index = cast(dict[str, int], image.transition_index)
    index[batch.transition_id] = 999
    corrupt_index = store.load_commit_view_v2(
        domain.scope_ref,
        "authority:alpha",
        batch.transition_id,
    )
    assert corrupt_index.disposition is GovernanceCommitDispositionV2.INVALID
    assert corrupt_index.failure is not None
    assert (
        corrupt_index.failure.code
        is AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    index[batch.transition_id] = 1
    stored_head = image.heads["authority:alpha"]
    object.__setattr__(stored_head, "head_root", batch.batch_root)
    corrupt_head = store.load_commit_view_v2(
        domain.scope_ref,
        "authority:alpha",
        batch.transition_id,
    )
    assert corrupt_head.disposition is GovernanceCommitDispositionV2.INVALID
    assert corrupt_head.observed_revision is None
    assert corrupt_head.observed_head_root is None

    sealed_store = InMemoryGovernanceStateStoreV2([domain])
    sealed_store.atomic_commit_v2(batch)
    seal = _seal_batch(
        sealed_store,
        domain,
        "transition:seal",
        ("authority:alpha",),
    )
    sealed_store.atomic_commit_v2(seal)
    sealed_image = sealed_store._domains[domain.scope_ref]
    object.__setattr__(sealed_image, "seal_root", batch.batch_root)
    corrupt_seal = sealed_store.load_commit_view_v2(
        domain.scope_ref,
        "authority:alpha",
        batch.transition_id,
    )
    assert corrupt_seal.disposition is GovernanceCommitDispositionV2.INVALID
    assert corrupt_seal.position_observation is None


def test_commit_reconciliation_maps_corrupt_authority_material_to_unavailable() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    batch = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:alpha-1",
        {"value": 1},
    )
    store.atomic_commit_v2(batch)
    image = store._domains[domain.scope_ref]
    index = cast(dict[str, int], image.transition_index)
    index[batch.transition_id] = 999
    corrupt_index = store.atomic_commit_v2(batch)
    assert (
        corrupt_index.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    )
    assert corrupt_index.failure is not None
    assert (
        corrupt_index.failure.code
        is AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
    )
    assert corrupt_index.failure.stage is GovernanceFailureStageV2.RECONCILIATION

    index[batch.transition_id] = 1
    entry = image.entries[0]
    object.__setattr__(entry.receipt, "receipt_root", batch.batch_root)
    corrupt_receipt = store.atomic_commit_v2(batch)
    assert (
        corrupt_receipt.disposition
        is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    )
    assert corrupt_receipt.committed_transition is None

    state_store = InMemoryGovernanceStateStoreV2([domain])
    state_batch = _transition_batch(
        state_store,
        domain,
        "authority:alpha",
        "transition:state-corruption",
        {"value": 1},
    )
    state_store.atomic_commit_v2(state_batch)
    state_image = state_store._domains[domain.scope_ref]
    states = cast(dict[str, Mapping[str, Any]], state_image.states)
    states["authority:alpha"] = {"value": "corrupt"}
    state_retry = state_store.atomic_commit_v2(state_batch)
    assert state_retry.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    state_view = state_store.load_commit_view_v2(
        domain.scope_ref,
        "authority:alpha",
        state_batch.transition_id,
    )
    assert state_view.disposition is GovernanceCommitDispositionV2.INVALID

    sequence_store = InMemoryGovernanceStateStoreV2([domain])
    sequence_batch = _transition_batch(
        sequence_store,
        domain,
        "authority:alpha",
        "transition:sequence-corruption",
        {"value": 1},
    )
    sequence_store.atomic_commit_v2(sequence_batch)
    sequence_entry = sequence_store._domains[domain.scope_ref].entries[0]
    object.__setattr__(sequence_entry, "sequence", True)
    sequence_view = sequence_store.load_commit_view_v2(
        domain.scope_ref,
        "authority:alpha",
        sequence_batch.transition_id,
    )
    assert sequence_view.disposition is GovernanceCommitDispositionV2.INVALID
    sequence_retry = sequence_store.atomic_commit_v2(sequence_batch)
    assert (
        sequence_retry.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    )


def test_boolean_for_integer_state_tamper_fails_strict_canonical_verification() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    batch = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:strict-state",
        {"value": 1},
    )
    assert (
        store.atomic_commit_v2(batch).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )

    image = store._domains[domain.scope_ref]
    states = cast(dict[str, Mapping[str, Any]], image.states)
    states["authority:alpha"] = {"value": True}

    view = store.load_commit_view_v2(
        domain.scope_ref,
        "authority:alpha",
        batch.transition_id,
    )
    assert view.disposition is GovernanceCommitDispositionV2.INVALID
    retry = store.atomic_commit_v2(batch)
    assert retry.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert retry.failure is not None
    assert retry.failure.stage is GovernanceFailureStageV2.RECONCILIATION


def test_cross_stream_dependency_reordering_invalidates_the_domain_image() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    alpha = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:alpha-1",
        {"value": 1},
    )
    assert (
        store.atomic_commit_v2(alpha).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    beta = _transition_batch(
        store,
        domain,
        "authority:beta",
        "transition:beta-1",
        {"depends_on_alpha": 1},
        observed_streams=("authority:alpha",),
    )
    assert (
        store.atomic_commit_v2(beta).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    fresh = _transition_batch(
        store,
        domain,
        "authority:gamma",
        "transition:gamma-1",
        {"value": 3},
    )
    image = store._domains[domain.scope_ref]
    alpha_entry, beta_entry = image.entries
    object.__setattr__(beta_entry, "sequence", 1)
    object.__setattr__(alpha_entry, "sequence", 2)
    object.__setattr__(image, "entries", (beta_entry, alpha_entry))
    index = cast(dict[str, int], image.transition_index)
    index[beta.transition_id] = 1
    index[alpha.transition_id] = 2
    corrupt_snapshot = store.snapshot_v2()

    view = store.load_commit_view_v2(
        domain.scope_ref,
        alpha.stream_ref,
        alpha.transition_id,
    )
    assert view.disposition is GovernanceCommitDispositionV2.INVALID
    retry = store.atomic_commit_v2(alpha)
    assert retry.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert retry.failure is not None
    assert retry.failure.stage is GovernanceFailureStageV2.RECONCILIATION
    rejected_fresh = store.atomic_commit_v2(fresh)
    assert (
        rejected_fresh.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    )
    assert rejected_fresh.failure is not None
    assert rejected_fresh.failure.stage is GovernanceFailureStageV2.RECONCILIATION
    with pytest.raises(ValueError):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(corrupt_snapshot)


def test_independent_stream_interleaving_replays_and_restarts() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    batches: list[GovernanceCommitBatchV2] = []
    for stream_ref, transition_id, value in (
        ("authority:alpha", "transition:alpha-1", 1),
        ("authority:beta", "transition:beta-1", 1),
        ("authority:alpha", "transition:alpha-2", 2),
        ("authority:beta", "transition:beta-2", 2),
    ):
        batch = _transition_batch(
            store,
            domain,
            stream_ref,
            transition_id,
            {"value": value},
        )
        batches.append(batch)
        assert (
            store.atomic_commit_v2(batch).disposition
            is GovernanceCommitDispositionV2.COMMITTED
        )

    for batch in batches:
        view = store.load_commit_view_v2(
            domain.scope_ref,
            batch.stream_ref,
            batch.transition_id,
        )
        assert view.disposition is GovernanceCommitDispositionV2.COMMITTED

    snapshot = store.snapshot_v2()
    restored = InMemoryGovernanceStateStoreV2.from_snapshot_v2(snapshot)
    assert restored.snapshot_v2() == snapshot
    assert (
        restored.atomic_commit_v2(batches[0]).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )


def test_historical_read_set_revision_rejects_boolean_integer_substitution() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    alpha = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:alpha-1",
        {"value": 1},
    )
    assert (
        store.atomic_commit_v2(alpha).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    beta = _transition_batch(
        store,
        domain,
        "authority:beta",
        "transition:beta-1",
        {"depends_on_alpha": 1},
        observed_streams=("authority:alpha",),
    )
    assert (
        store.atomic_commit_v2(beta).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    fresh = _transition_batch(
        store,
        domain,
        "authority:gamma",
        "transition:gamma-1",
        {"value": 3},
    )
    stored_beta = store._domains[domain.scope_ref].entries[1]
    alpha_precondition = next(
        item
        for item in stored_beta.batch.read_set.entries
        if item.stream_ref == alpha.stream_ref
    )
    object.__setattr__(alpha_precondition, "expected_revision", True)
    corrupt_snapshot = store.snapshot_v2()

    view = store.load_commit_view_v2(
        domain.scope_ref,
        beta.stream_ref,
        beta.transition_id,
    )
    assert view.disposition is GovernanceCommitDispositionV2.INVALID
    retry = store.atomic_commit_v2(beta)
    assert retry.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert retry.failure is not None
    assert retry.failure.stage is GovernanceFailureStageV2.RECONCILIATION
    rejected_fresh = store.atomic_commit_v2(fresh)
    assert (
        rejected_fresh.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    )
    assert rejected_fresh.failure is not None
    assert rejected_fresh.failure.stage is GovernanceFailureStageV2.RECONCILIATION
    with pytest.raises((TypeError, ValueError)):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(corrupt_snapshot)


def test_new_commit_and_seal_map_corrupt_persistent_head_to_unavailable() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    alpha = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:alpha-1",
        {"value": 1},
    )
    store.atomic_commit_v2(alpha)
    dependent = _transition_batch(
        store,
        domain,
        "authority:beta",
        "transition:beta-1",
        {"value": 2},
        observed_streams=("authority:alpha",),
    )
    seal = _seal_batch(
        store,
        domain,
        "transition:seal",
        ("authority:alpha",),
    )
    image = store._domains[domain.scope_ref]
    heads = cast(dict[str, object], image.heads)
    heads["authority:alpha"] = object()

    dependent_result = store.atomic_commit_v2(dependent)
    seal_result = store.atomic_commit_v2(seal)
    assert (
        dependent_result.disposition
        is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    )
    assert seal_result.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    with pytest.raises((TypeError, ValueError)):
        store.load_head_v2(domain.scope_ref, "authority:beta")


def test_new_write_rejects_missing_transition_index_without_duplicate_identity() -> (
    None
):
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    first = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:duplicate",
        {"value": 1},
    )
    assert (
        store.atomic_commit_v2(first).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    replacement = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:duplicate",
        {"value": 2},
    )
    image = store._domains[domain.scope_ref]
    cast(dict[str, int], image.transition_index).clear()

    result = store.atomic_commit_v2(replacement)

    assert result.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert result.failure is not None
    assert result.failure.stage is GovernanceFailureStageV2.RECONCILIATION
    assert len(image.entries) == 1
    assert [entry.batch.transition_id for entry in image.entries] == [
        "transition:duplicate"
    ]


def test_new_write_rejects_cleared_seal_marker_without_reopening_domain() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    ordinary = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:alpha-1",
        {"value": 1},
    )
    assert (
        store.atomic_commit_v2(ordinary).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    seal = _seal_batch(
        store,
        domain,
        "transition:seal",
        (ordinary.stream_ref,),
    )
    assert (
        store.atomic_commit_v2(seal).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    candidate = _transition_batch(
        store,
        domain,
        ordinary.stream_ref,
        "transition:after-seal",
        {"value": 2},
    )
    image = store._domains[domain.scope_ref]
    object.__setattr__(image, "seal_root", None)

    result = store.atomic_commit_v2(candidate)

    assert result.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert result.failure is not None
    assert result.failure.stage is GovernanceFailureStageV2.RECONCILIATION
    assert [entry.batch.kind for entry in image.entries] == ["transition", "seal"]


def test_new_write_rejects_history_without_current_head_and_state() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    first = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:alpha-1",
        {"value": 1},
    )
    assert (
        store.atomic_commit_v2(first).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    false_genesis = GovernanceHeadV2.genesis(domain, first.stream_ref)
    from_false_genesis = _transition_batch(
        store,
        domain,
        first.stream_ref,
        "transition:alpha-2",
        {"value": 2},
        observed_heads=(false_genesis,),
    )
    image = store._domains[domain.scope_ref]
    cast(dict[str, GovernanceHeadV2], image.heads).clear()
    cast(dict[str, Mapping[str, Any]], image.states).clear()
    with pytest.raises(ValueError):
        store.load_head_v2(domain.scope_ref, first.stream_ref)

    result = store.atomic_commit_v2(from_false_genesis)

    assert result.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert result.failure is not None
    assert result.failure.stage is GovernanceFailureStageV2.RECONCILIATION
    assert [entry.receipt.revision for entry in image.entries] == [1]


def test_new_write_rejects_boolean_sequence_corruption_in_another_stream() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    first = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:alpha-1",
        {"value": 1},
    )
    assert (
        store.atomic_commit_v2(first).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    other_stream = _transition_batch(
        store,
        domain,
        "authority:beta",
        "transition:beta-1",
        {"value": 2},
    )
    image = store._domains[domain.scope_ref]
    object.__setattr__(image.entries[0], "sequence", True)
    with pytest.raises(ValueError):
        store.load_head_v2(domain.scope_ref, "authority:beta")

    result = store.atomic_commit_v2(other_stream)

    assert result.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert result.failure is not None
    assert result.failure.stage is GovernanceFailureStageV2.RECONCILIATION
    assert len(image.entries) == 1
    with pytest.raises(ValueError):
        store.load_head_v2(domain.scope_ref, "authority:beta")


@pytest.mark.parametrize("selector", ["e\u0301", "\ud800"])
def test_reader_selectors_require_nfc_utf8_text(selector: str) -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])

    with pytest.raises(ValueError):
        store.load_head_v2(domain.scope_ref, selector)
    with pytest.raises(ValueError):
        store.load_state_v2(domain.scope_ref, selector)
    with pytest.raises(ValueError):
        store.load_commit_view_v2(
            domain.scope_ref,
            "authority:alpha",
            selector,
        )


def test_trace_tamper_has_specific_diagnostic_and_snapshot_restore_rejects() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    batch = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:alpha-1",
        {"value": 1},
    )
    store.atomic_commit_v2(batch)
    stored = store._domains[domain.scope_ref].entries[0]
    object.__setattr__(stored.batch.trace_batch, "trace_root", batch.batch_root)

    view = store.load_commit_view_v2(
        domain.scope_ref,
        "authority:alpha",
        batch.transition_id,
    )
    assert view.disposition is GovernanceCommitDispositionV2.INVALID
    assert view.failure is not None
    assert (
        view.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_TRACE_LINEAGE_INVALID
    )
    assert view.failure.path == "/committed_transition/batch/trace_batch"
    corrupt_snapshot = store.snapshot_v2()
    with pytest.raises(ValueError):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(corrupt_snapshot)


def test_seal_and_ordinary_commit_race_has_one_legal_linearization() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    ordinary = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:alpha-1",
        {"value": 1},
    )
    seal = _seal_batch(store, domain, "transition:seal", ())
    barrier = Barrier(2)

    def commit_after_barrier(
        candidate: GovernanceCommitBatchV2,
    ) -> GovernanceCommitDispositionV2:
        barrier.wait()
        return store.atomic_commit_v2(candidate).disposition

    with ThreadPoolExecutor(max_workers=2) as executor:
        ordinary_future = executor.submit(commit_after_barrier, ordinary)
        seal_future = executor.submit(commit_after_barrier, seal)
        outcome = (ordinary_future.result(), seal_future.result())
    assert outcome in {
        (
            GovernanceCommitDispositionV2.COMMITTED,
            GovernanceCommitDispositionV2.RETRY_REQUIRED,
        ),
        (
            GovernanceCommitDispositionV2.DENIED,
            GovernanceCommitDispositionV2.COMMITTED,
        ),
    }


def test_seal_state_boolean_for_integer_tamper_invalidates_all_history() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    ordinary = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:alpha-1",
        {"value": 1},
    )
    assert (
        store.atomic_commit_v2(ordinary).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    seal = _seal_batch(
        store,
        domain,
        "transition:seal",
        ("authority:alpha",),
    )
    assert (
        store.atomic_commit_v2(seal).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )

    image = store._domains[domain.scope_ref]
    lifecycle_states = cast(dict[str, Mapping[str, Any]], image.states)
    lifecycle = cast(
        dict[str, Any],
        lifecycle_states[GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2],
    )
    seal_state = cast(dict[str, Any], lifecycle["seal"])
    seal_state["expected_revision"] = False

    view = store.load_commit_view_v2(
        domain.scope_ref,
        ordinary.stream_ref,
        ordinary.transition_id,
    )
    assert view.disposition is GovernanceCommitDispositionV2.INVALID
    retry = store.atomic_commit_v2(ordinary)
    assert retry.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert retry.failure is not None
    assert retry.failure.stage is GovernanceFailureStageV2.RECONCILIATION


def _snapshot_with_two_streams() -> dict[str, Any]:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    for stream_ref in ("authority:alpha", "authority:beta"):
        batch = _transition_batch(
            store,
            domain,
            stream_ref,
            f"transition:{stream_ref.rsplit(':', 1)[1]}-1",
            {"value": stream_ref},
        )
        assert (
            store.atomic_commit_v2(batch).disposition
            is GovernanceCommitDispositionV2.COMMITTED
        )
    return cast(dict[str, Any], json.loads(store.snapshot_v2()))


def _raw_image(
    store: InMemoryGovernanceStateStoreV2,
    scope_ref: str,
) -> Any:
    images = getattr(
        store,
        "_InMemoryGovernanceStateStoreV2__domain_images",
    )
    return images[scope_ref]


def _refresh_entry_integrity(entry: Any) -> str:
    entry_root = authority_store_reference._entry_integrity_root(entry)
    object.__setattr__(entry, "verified_integrity_root", entry_root)
    return entry_root


def _refresh_fast_tail_checkpoint(image: Any, entry: Any) -> None:
    entry_root = _refresh_entry_integrity(entry)
    checkpoint = image.verified_checkpoint
    assert checkpoint is not None
    assert checkpoint.parent_history_root is not None
    object.__setattr__(checkpoint, "tail_entry_root", entry_root)
    object.__setattr__(
        checkpoint,
        "history_root",
        authority_store_reference._history_successor_root(
            checkpoint.parent_history_root,
            entry_root,
        ),
    )


def _store_with_transition(
    *,
    scope_ref: str = "scope:reference",
    stream_ref: str = "authority:alpha",
    transition_id: str = "transition:alpha-1",
) -> tuple[
    AuthorityDomainV2,
    InMemoryGovernanceStateStoreV2,
    GovernanceCommitBatchV2,
]:
    domain = _domain(scope_ref)
    store = InMemoryGovernanceStateStoreV2([domain])
    batch = _transition_batch(
        store,
        domain,
        stream_ref,
        transition_id,
        {"value": 1},
    )
    assert (
        store.atomic_commit_v2(batch).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    return domain, store, batch


def _sealed_store(
    *,
    with_stream: bool,
) -> tuple[AuthorityDomainV2, InMemoryGovernanceStateStoreV2]:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    streams: tuple[str, ...] = ()
    if with_stream:
        batch = _transition_batch(
            store,
            domain,
            "authority:alpha",
            "transition:alpha-1",
            {"value": 1},
        )
        assert (
            store.atomic_commit_v2(batch).disposition
            is GovernanceCommitDispositionV2.COMMITTED
        )
        streams = ("authority:alpha",)
    seal = _seal_batch(store, domain, "transition:seal", streams)
    assert (
        store.atomic_commit_v2(seal).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    return domain, store


def test_reference_store_rejects_invalid_setup_and_runtime_call_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain = _domain()
    with pytest.raises(TypeError, match="failure_injector"):
        InMemoryGovernanceStateStoreV2([domain], failure_injector=object())  # type: ignore[arg-type]
    snapshot = InMemoryGovernanceStateStoreV2([domain]).snapshot_v2()
    with pytest.raises(TypeError, match="failure_injector"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(
            snapshot,
            failure_injector=object(),  # type: ignore[arg-type]
        )

    store = InMemoryGovernanceStateStoreV2([domain])
    store.register_domain_v2(domain)
    with pytest.raises(ValueError, match="another domain"):
        store.register_domain_v2(
            _domain(
                domain.scope_ref,
                profile=AUTHORITY_AUTHENTICATED_PROFILE_V2,
            )
        )
    with pytest.raises(TypeError, match="GovernanceCommitBatchV2"):
        store.atomic_commit_v2(object())  # type: ignore[arg-type]

    batch = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:invalid-runtime-shape",
        {"value": 1},
    )

    def fail_locked(
        _store: InMemoryGovernanceStateStoreV2,
        _batch: GovernanceCommitBatchV2,
    ) -> object:
        raise ValueError("corrupt private runtime")

    monkeypatch.setattr(
        InMemoryGovernanceStateStoreV2, "_atomic_commit_locked", fail_locked
    )
    unavailable = store.atomic_commit_v2(batch)
    assert unavailable.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert unavailable.failure is not None
    assert unavailable.failure.stage is GovernanceFailureStageV2.FINALITY


def test_reference_snapshot_root_selection_and_domain_order_fail_closed() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    baseline = cast(dict[str, Any], json.loads(store.snapshot_v2()))

    version = json.loads(json.dumps(baseline))
    version["schema"] = "unsupported"
    with pytest.raises(ValueError, match="version selection"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(json.dumps(version))

    wrong_domains = json.loads(json.dumps(baseline))
    wrong_domains["domains"] = {}
    with pytest.raises(TypeError, match="domains must be an array"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(json.dumps(wrong_domains))

    duplicate = json.loads(json.dumps(baseline))
    duplicate["domains"].append(duplicate["domains"][0])
    with pytest.raises(ValueError, match="unique and sorted"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(json.dumps(duplicate))

    bad_seal = json.loads(json.dumps(baseline))
    bad_seal["domains"][0]["seal_root"] = 1
    with pytest.raises(TypeError, match="seal_root"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(json.dumps(bad_seal))


def test_reference_snapshot_head_and_state_catalogs_fail_closed() -> None:
    baseline = _snapshot_with_two_streams()
    domain_snapshot = baseline["domains"][0]

    invalid_heads = json.loads(json.dumps(baseline))
    invalid_heads["domains"][0]["heads"] = {}
    with pytest.raises(TypeError, match="snapshot heads must be an array"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(json.dumps(invalid_heads))

    cross_domain = json.loads(json.dumps(baseline))
    other = _domain("scope:other")
    cross_domain["domains"][0]["heads"][0] = GovernanceHeadV2.genesis(
        other, "authority:alpha"
    ).to_dict()
    with pytest.raises(ValueError, match="crosses authority domain"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(json.dumps(cross_domain))

    duplicate_head = json.loads(json.dumps(baseline))
    duplicate_head["domains"][0]["heads"].append(
        duplicate_head["domains"][0]["heads"][0]
    )
    with pytest.raises(ValueError, match="head stream is duplicated"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(json.dumps(duplicate_head))

    unsorted_heads = json.loads(json.dumps(baseline))
    unsorted_heads["domains"][0]["heads"].reverse()
    with pytest.raises(ValueError, match="heads must be UTF-8 sorted"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(json.dumps(unsorted_heads))

    duplicate_state = json.loads(json.dumps(baseline))
    duplicate_state["domains"][0]["states"].append(
        duplicate_state["domains"][0]["states"][0]
    )
    with pytest.raises(ValueError, match="state stream is duplicated"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(json.dumps(duplicate_state))

    missing_state = json.loads(json.dumps(baseline))
    missing_state["domains"][0]["states"].pop()
    with pytest.raises(ValueError, match="exactly match sorted heads"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(json.dumps(missing_state))

    assert len(domain_snapshot["heads"]) == len(domain_snapshot["states"]) == 2


def test_reference_snapshot_transition_index_catalog_fails_closed() -> None:
    baseline = _snapshot_with_two_streams()

    invalid_sequence = json.loads(json.dumps(baseline))
    invalid_sequence["domains"][0]["transition_index"][0]["sequence"] = 99
    with pytest.raises(ValueError, match="sequence is invalid"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(json.dumps(invalid_sequence))

    duplicate_identity = json.loads(json.dumps(baseline))
    duplicate_identity["domains"][0]["transition_index"][1]["transition_id"] = (
        duplicate_identity["domains"][0]["transition_index"][0]["transition_id"]
    )
    with pytest.raises(ValueError, match="identity is duplicated"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(json.dumps(duplicate_identity))

    unsorted = json.loads(json.dumps(baseline))
    unsorted["domains"][0]["transition_index"].reverse()
    with pytest.raises(ValueError, match="UTF-8 sorted"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(json.dumps(unsorted))


def test_reference_snapshot_and_public_selector_boundaries_fail_closed() -> None:
    with pytest.raises(ValueError, match="BOM"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(b"\xef\xbb\xbf{}")
    with pytest.raises(ValueError, match="BOM"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2("\ufeff{}")
    with pytest.raises(TypeError, match="text or UTF-8 bytes"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="duplicate object keys"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2('{"a":1,"a":2}')
    with pytest.raises(ValueError, match="floating-point"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2('{"value":1.5}')

    with pytest.raises(TypeError, match="exact object"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2("[]")
    with pytest.raises(ValueError, match="fields are invalid"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2("{}")

    baseline = _snapshot_with_two_streams()
    invalid_domains = json.loads(json.dumps(baseline))
    invalid_domains["domains"] = {}
    with pytest.raises(TypeError, match="must be an array"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(json.dumps(invalid_domains))

    invalid_state = json.loads(json.dumps(baseline))
    invalid_state["domains"][0]["states"][0]["state_records"] = []
    with pytest.raises(TypeError, match="must be a mapping"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(json.dumps(invalid_state))

    store = InMemoryGovernanceStateStoreV2()
    with pytest.raises(TypeError, match="AuthorityDomainV2"):
        store.register_domain_v2(cast(AuthorityDomainV2, object()))

    for value in ("", " whitespace "):
        with pytest.raises(ValueError, match="canonical non-blank"):
            store.load_head_v2(value, "authority:alpha")
    with pytest.raises(ValueError, match="Unicode NFC"):
        store.load_state_v2("e\u0301", "authority:alpha")
    with pytest.raises(ValueError, match="UTF-8"):
        store.load_commit_view_v2(
            "\ud800",
            "authority:alpha",
            "transition:test",
        )


def test_fast_checkpoint_path_rejects_corrupt_index_and_trace_lineage() -> None:
    domain, store, batch = _store_with_transition()
    image = _raw_image(store, domain.scope_ref)
    cast(dict[str, int], image.transition_index)[batch.transition_id] = 99
    invalid_index = store.load_commit_view_v2(
        domain.scope_ref,
        batch.stream_ref,
        batch.transition_id,
    )
    assert invalid_index.disposition is GovernanceCommitDispositionV2.INVALID
    unavailable = store.atomic_commit_v2(batch)
    assert unavailable.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE

    domain, store, batch = _store_with_transition()
    image = _raw_image(store, domain.scope_ref)
    entry = image.entries[0]
    object.__setattr__(entry.batch.trace_batch, "trace_root", batch.batch_root)
    entry_root = authority_store_reference._entry_integrity_root(entry)
    object.__setattr__(entry, "verified_integrity_root", entry_root)
    checkpoint = image.verified_checkpoint
    assert checkpoint is not None
    object.__setattr__(checkpoint, "tail_entry_root", entry_root)
    assert checkpoint.parent_history_root is not None
    object.__setattr__(
        checkpoint,
        "history_root",
        authority_store_reference._history_successor_root(
            checkpoint.parent_history_root,
            entry_root,
        ),
    )
    invalid_trace = store.load_commit_view_v2(
        domain.scope_ref,
        batch.stream_ref,
        batch.transition_id,
    )
    assert invalid_trace.failure is not None
    assert (
        invalid_trace.failure.code
        is AuthorityDiagnosticCodeV2.GOVERNANCE_TRACE_LINEAGE_INVALID
    )


def test_commit_clone_lookup_and_reconcile_corruption_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    malformed = _transition_batch(
        store,
        domain,
        "authority:alpha",
        "transition:malformed",
        {"value": 1},
    )
    assert malformed.transition is not None
    object.__setattr__(malformed.transition, "state_records", object())
    rejected = store.atomic_commit_v2(malformed)
    assert rejected.disposition is GovernanceCommitDispositionV2.INVALID

    domain, store, first = _store_with_transition()
    second = _transition_batch(
        store,
        domain,
        first.stream_ref,
        "transition:alpha-2",
        {"value": 2},
    )
    assert (
        store.atomic_commit_v2(second).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    image = _raw_image(store, domain.scope_ref)
    object.__setattr__(image.entries[0], "verified_integrity_root", second.batch_root)
    unavailable = store.atomic_commit_v2(first)
    assert unavailable.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE

    domain, store, batch = _store_with_transition()

    def fail_committed_attempt(*_args: object) -> object:
        raise ValueError("corrupt committed projection")

    monkeypatch.setattr(
        authority_store_reference,
        "_committed_attempt",
        fail_committed_attempt,
    )
    unavailable = store.atomic_commit_v2(batch)
    assert unavailable.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE


def test_retry_failure_injection_and_revision_exhaustion_are_total() -> None:
    domain, store, batch = _store_with_transition()

    def fail_reconcile(stage: str, _batch: GovernanceCommitBatchV2) -> None:
        if stage == FAILURE_STAGE_AFTER_IDENTITY_RECONCILIATION_V2:
            raise OSError("reconcile response unavailable")

    store._failure_injector = fail_reconcile
    unavailable = store.atomic_commit_v2(batch)
    assert unavailable.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert unavailable.failure is not None
    assert unavailable.failure.stage is GovernanceFailureStageV2.RECONCILIATION

    domain, store, _batch = _store_with_transition()
    image = _raw_image(store, domain.scope_ref)
    head = image.heads["authority:alpha"]
    object.__setattr__(head, "revision", MAX_AUTHORITY_REVISION_V2)
    read_set = GovernanceAuthorityReadSetV2(
        entries=(
            GovernanceReadPreconditionV2(
                stream_ref=head.stream_ref,
                expected_revision=MAX_AUTHORITY_REVISION_V2,
                expected_root=head.head_root,
            ),
        )
    )
    transition = PreparedGovernanceTransitionV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=head.stream_ref,
        transition_id="transition:revision-exhausted",
        expected_revision=MAX_AUTHORITY_REVISION_V2,
        expected_root=head.head_root,
        read_set_root=read_set.root(),
        state_records={"value": 2},
    )
    trace = GovernanceTraceBatchV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=head.stream_ref,
        transition_id=transition.transition_id,
        events=(
            TraceEvent(
                event_type="x-authority-v2-commit",
                protocol_id="protocol:reference-test",
                target=head.stream_ref,
                reason="revision exhaustion",
                lineage={
                    "scope_ref": domain.scope_ref,
                    "stream_ref": head.stream_ref,
                    "transition_id": transition.transition_id,
                },
            ),
        ),
    )
    exhausted = store.atomic_commit_v2(
        GovernanceCommitBatchV2(
            domain=domain,
            scope_ref=domain.scope_ref,
            stream_ref=head.stream_ref,
            transition_id=transition.transition_id,
            kind="transition",
            read_set=read_set,
            trace_batch=trace,
            transition=transition,
        )
    )
    assert exhausted.disposition is GovernanceCommitDispositionV2.INVALID
    assert exhausted.failure is not None
    assert exhausted.failure.path == "/read_set"


def test_checkpoint_identity_history_and_empty_state_corruption_is_rejected() -> None:
    domain, store, _batch = _store_with_transition()
    image = _raw_image(store, domain.scope_ref)
    object.__setattr__(image, "verified_checkpoint", None)
    with pytest.raises(ValueError, match="no verified checkpoint"):
        store.load_head_v2(domain.scope_ref, "authority:alpha")

    domain, store, _batch = _store_with_transition()
    image = _raw_image(store, domain.scope_ref)
    checkpoint = image.verified_checkpoint
    assert checkpoint is not None
    object.__setattr__(checkpoint, "entry_count", 99)
    with pytest.raises(ValueError, match="checkpoint is inconsistent"):
        store.load_head_v2(domain.scope_ref, "authority:alpha")

    domain, store, _batch = _store_with_transition()
    image = _raw_image(store, domain.scope_ref)
    checkpoint = image.verified_checkpoint
    assert checkpoint is not None
    object.__setattr__(checkpoint, "tail_entry_root", image.domain.domain_root)
    with pytest.raises(ValueError, match="history checkpoint"):
        store.load_head_v2(domain.scope_ref, "authority:alpha")

    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    image = _raw_image(store, domain.scope_ref)
    checkpoint = image.verified_checkpoint
    assert checkpoint is not None
    object.__setattr__(checkpoint, "history_root", domain.domain_root)
    with pytest.raises(ValueError, match="empty authority scope"):
        store.load_head_v2(domain.scope_ref, "authority:alpha")


def test_snapshot_replay_detects_proof_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _domain_value, store, batch = _store_with_transition()
    snapshot = store.snapshot_v2()
    restore = authority_store_reference._restore_domain_snapshot

    def restore_with_substituted_receipt(payload: object) -> Any:
        image = restore(payload)
        object.__setattr__(
            image.entries[0].receipt,
            "receipt_root",
            batch.batch_root,
        )
        return image

    monkeypatch.setattr(
        authority_store_reference,
        "_restore_domain_snapshot",
        restore_with_substituted_receipt,
    )
    with pytest.raises(ValueError, match="commit proof is inconsistent"):
        InMemoryGovernanceStateStoreV2.from_snapshot_v2(snapshot)


def test_public_commit_and_view_reject_selection_and_entry_integrity_tamper() -> None:
    domain, store, batch = _store_with_transition()
    image = _raw_image(store, domain.scope_ref)
    object.__setattr__(image.domain, "domain_root", _domain("scope:other").domain_root)
    binding_failure = store.atomic_commit_v2(batch)
    assert binding_failure.disposition is GovernanceCommitDispositionV2.INVALID
    assert binding_failure.failure is not None
    assert (
        binding_failure.failure.code
        is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )
    assert binding_failure.failure.path == "/domain_root"

    domain, store, batch = _store_with_transition()
    object.__setattr__(batch, "domain_root", _domain("scope:other").domain_root)
    failure = store.atomic_commit_v2(batch)
    assert failure.disposition is GovernanceCommitDispositionV2.INVALID
    assert failure.failure is not None
    assert failure.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    assert failure.failure.stage is GovernanceFailureStageV2.VALIDATION

    domain, store, first = _store_with_transition()
    second = _transition_batch(
        store,
        domain,
        first.stream_ref,
        "transition:alpha-2",
        {"value": 2},
    )
    assert (
        store.atomic_commit_v2(second).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    image = _raw_image(store, domain.scope_ref)
    index = cast(dict[str, int], image.transition_index)
    index[first.transition_id], index[second.transition_id] = (
        index[second.transition_id],
        index[first.transition_id],
    )
    mismatched_index = store.load_commit_view_v2(
        domain.scope_ref,
        first.stream_ref,
        first.transition_id,
    )
    assert mismatched_index.disposition is GovernanceCommitDispositionV2.INVALID
    assert mismatched_index.failure is not None
    assert mismatched_index.failure.stage is GovernanceFailureStageV2.LOAD

    for invalid_sequence in (0, True):
        domain, store, batch = _store_with_transition()
        image = _raw_image(store, domain.scope_ref)
        entry = image.entries[0]
        object.__setattr__(entry, "sequence", invalid_sequence)
        _refresh_fast_tail_checkpoint(image, entry)
        invalid = store.load_commit_view_v2(
            domain.scope_ref,
            batch.stream_ref,
            batch.transition_id,
        )
        assert invalid.disposition is GovernanceCommitDispositionV2.INVALID
        assert invalid.failure is not None
        assert invalid.failure.code is (
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
        )
        assert invalid.failure.stage is GovernanceFailureStageV2.LOAD

    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    batches: list[GovernanceCommitBatchV2] = []
    for stream_ref in ("authority:alpha", "authority:beta"):
        batch = _transition_batch(
            store,
            domain,
            stream_ref,
            f"transition:{stream_ref.rsplit(':', 1)[1]}",
            {"value": stream_ref},
        )
        assert (
            store.atomic_commit_v2(batch).disposition
            is GovernanceCommitDispositionV2.COMMITTED
        )
        batches.append(batch)
    image = _raw_image(store, domain.scope_ref)
    first = image.entries[0]
    object.__setattr__(first, "verified_integrity_root", domain.domain_root)
    invalid_witness = store.load_commit_view_v2(
        domain.scope_ref,
        batches[0].stream_ref,
        batches[0].transition_id,
    )
    assert invalid_witness.disposition is GovernanceCommitDispositionV2.INVALID

    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    batches = []
    for stream_ref in ("authority:alpha", "authority:beta"):
        batch = _transition_batch(
            store,
            domain,
            stream_ref,
            f"transition:{stream_ref.rsplit(':', 1)[1]}",
            {"value": stream_ref},
        )
        assert (
            store.atomic_commit_v2(batch).disposition
            is GovernanceCommitDispositionV2.COMMITTED
        )
        batches.append(batch)
    image = _raw_image(store, domain.scope_ref)
    index = cast(dict[str, int], image.transition_index)
    index[batches[0].transition_id], index[batches[1].transition_id] = 2, 1
    invalid_index = store.load_commit_view_v2(
        domain.scope_ref,
        batches[0].stream_ref,
        batches[0].transition_id,
    )
    assert invalid_index.disposition is GovernanceCommitDispositionV2.INVALID


def test_historical_replay_rejects_domain_seal_bound_and_continuity_tamper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    other_domain, other_store, _batch = _store_with_transition(scope_ref="scope:other")
    other_entry = _raw_image(other_store, other_domain.scope_ref).entries[0]
    image = _raw_image(store, domain.scope_ref)
    store._domains[domain.scope_ref] = replace(
        image,
        entries=(other_entry,),
        transition_index={other_entry.batch.transition_id: 1},
    )
    with pytest.raises(ValueError, match="domain is inconsistent"):
        store.load_head_v2(domain.scope_ref, "authority:alpha")

    domain, sealed = _sealed_store(with_stream=False)
    sealed_image = _raw_image(sealed, domain.scope_ref)
    seal_entry = sealed_image.entries[0]
    _same, transition_store, _batch = _store_with_transition()
    transition_entry = _raw_image(transition_store, domain.scope_ref).entries[0]
    transition_entry = replace(transition_entry, sequence=2)
    _refresh_entry_integrity(transition_entry)
    sealed._domains[domain.scope_ref] = replace(
        sealed_image,
        entries=(seal_entry, transition_entry),
        transition_index={
            seal_entry.batch.transition_id: 1,
            transition_entry.batch.transition_id: 2,
        },
    )
    with pytest.raises(ValueError, match="later commit"):
        sealed.load_head_v2(
            domain.scope_ref,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        )

    domain, transition_store, _batch = _store_with_transition()
    transition_image = _raw_image(transition_store, domain.scope_ref)
    transition_store._domains[domain.scope_ref] = transition_image
    with monkeypatch.context() as bound_patch:
        bound_patch.setattr(
            authority_store_reference,
            "MAX_GOVERNANCE_NON_LIFECYCLE_STREAMS_V2",
            0,
        )
        with pytest.raises(ValueError, match="stream bound"):
            transition_store.load_head_v2(
                domain.scope_ref,
                "authority:alpha",
            )

    domain, store, first = _store_with_transition()
    second = _transition_batch(
        store,
        domain,
        first.stream_ref,
        "transition:alpha-2",
        {"value": 2},
    )
    assert (
        store.atomic_commit_v2(second).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    image = _raw_image(store, domain.scope_ref)
    second_entry = replace(image.entries[1], sequence=1)
    _refresh_entry_integrity(second_entry)
    store._domains[domain.scope_ref] = replace(
        image,
        entries=(second_entry,),
        transition_index={second_entry.batch.transition_id: 1},
    )
    with pytest.raises(ValueError, match="historical read-set"):
        store.load_head_v2(domain.scope_ref, first.stream_ref)


def test_public_full_replay_rejects_seal_root_and_read_set_tamper() -> None:
    domain = _domain()
    open_store = InMemoryGovernanceStateStoreV2([domain])
    open_image = _raw_image(open_store, domain.scope_ref)
    open_store._domains[domain.scope_ref] = replace(
        open_image,
        seal_root=domain.domain_root,
    )
    with pytest.raises(ValueError, match="open domain contains a seal root"):
        open_store.load_head_v2(
            domain.scope_ref,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        )

    domain, sealed_store = _sealed_store(with_stream=False)
    sealed_image = _raw_image(sealed_store, domain.scope_ref)
    sealed_store._domains[domain.scope_ref] = replace(sealed_image, seal_root=None)
    with pytest.raises(ValueError, match="sealed domain root"):
        sealed_store.load_head_v2(
            domain.scope_ref,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        )

    domain, sealed_store = _sealed_store(with_stream=False)
    sealed_store._domains[domain.scope_ref] = _raw_image(
        sealed_store,
        domain.scope_ref,
    )
    assert (
        sealed_store.load_head_v2(
            domain.scope_ref,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        ).revision
        == 1
    )

    domain, transition_store, _batch = _store_with_transition()
    transition_image = _raw_image(transition_store, domain.scope_ref)
    transition_entry = transition_image.entries[0]
    _same, seal_store = _sealed_store(with_stream=False)
    seal_entry = replace(
        _raw_image(seal_store, domain.scope_ref).entries[0],
        sequence=2,
    )
    _refresh_entry_integrity(seal_entry)
    assert seal_entry.batch.seal is not None
    transition_store._domains[domain.scope_ref] = replace(
        transition_image,
        entries=(transition_entry, seal_entry),
        transition_index={
            transition_entry.batch.transition_id: 1,
            seal_entry.batch.transition_id: 2,
        },
        seal_root=seal_entry.batch.seal.seal_root,
    )
    with pytest.raises(ValueError, match="seal read-set is incomplete"):
        transition_store.load_head_v2(
            domain.scope_ref,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        )


def test_public_full_replay_rejects_historical_read_set_mismatch() -> None:
    domain, store, first = _store_with_transition()
    second = _transition_batch(
        store,
        domain,
        first.stream_ref,
        "transition:alpha-2",
        {"value": 2},
    )
    assert (
        store.atomic_commit_v2(second).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    image = _raw_image(store, domain.scope_ref)
    second_entry = replace(image.entries[1], sequence=1)
    _refresh_entry_integrity(second_entry)
    store._domains[domain.scope_ref] = replace(
        image,
        entries=(second_entry,),
        transition_index={second.transition_id: 1},
    )
    with pytest.raises(ValueError, match="historical read-set"):
        store.load_head_v2(domain.scope_ref, first.stream_ref)


def test_public_loads_reject_current_projection_and_state_tamper() -> None:
    domain, store, _batch = _store_with_transition()
    image = _raw_image(store, domain.scope_ref)
    cast(dict[str, Any], image.heads)["authority:alpha"] = object()
    with pytest.raises(TypeError, match="head projection"):
        store.load_head_v2(domain.scope_ref, "authority:alpha")

    domain, store, _batch = _store_with_transition()
    image = _raw_image(store, domain.scope_ref)
    object.__setattr__(image.heads["authority:alpha"], "revision", 0)
    with pytest.raises(ValueError, match="persisted authority material"):
        store.load_head_v2(domain.scope_ref, "authority:alpha")

    domain, store, batch = _store_with_transition()
    image = _raw_image(store, domain.scope_ref)
    index = cast(dict[str, int], image.transition_index)
    index.pop(batch.transition_id)
    index["transition:substituted"] = 1
    with pytest.raises(ValueError, match="no included head"):
        store.load_head_v2(domain.scope_ref, "authority:alpha")

    domain, store, _batch = _store_with_transition()
    image = _raw_image(store, domain.scope_ref)
    heads = cast(dict[str, GovernanceHeadV2], image.heads)
    states = cast(dict[str, Mapping[str, Any]], image.states)
    heads["authority:other"] = heads.pop("authority:alpha")
    states["authority:other"] = states.pop("authority:alpha")
    with pytest.raises(ValueError, match="no included head"):
        store.load_head_v2(domain.scope_ref, "authority:other")

    domain, store, _batch = _store_with_transition()
    image = _raw_image(store, domain.scope_ref)
    states = cast(dict[str, Mapping[str, Any]], image.states)
    states.pop("authority:alpha")
    states["authority:substituted"] = {"value": 1}
    with pytest.raises(ValueError, match="state projection"):
        store.load_state_v2(domain.scope_ref, "authority:alpha")

    domain, store, _batch = _store_with_transition()
    image = _raw_image(store, domain.scope_ref)
    cast(dict[str, Mapping[str, Any]], image.states)["authority:alpha"] = {"value": 2}
    with pytest.raises(ValueError, match="state projection"):
        store.load_state_v2(domain.scope_ref, "authority:alpha")


def test_public_loads_reject_entry_kind_and_domain_mapping_tamper() -> None:
    domain = _domain()
    store = InMemoryGovernanceStateStoreV2([domain])
    empty = _raw_image(store, domain.scope_ref)
    store._domains[domain.scope_ref] = replace(empty, heads=())
    with pytest.raises(TypeError, match="projections must be mappings"):
        store.load_head_v2(domain.scope_ref, "authority:alpha")

    domain, store, _batch = _store_with_transition()
    image = _raw_image(store, domain.scope_ref)
    transition_entry = image.entries[0]
    object.__setattr__(transition_entry.batch, "kind", "seal")
    _refresh_fast_tail_checkpoint(image, transition_entry)
    with pytest.raises(ValueError, match="no seal"):
        store.load_head_v2(domain.scope_ref, "authority:alpha")

    domain, sealed = _sealed_store(with_stream=False)
    image = _raw_image(sealed, domain.scope_ref)
    seal_entry = image.entries[0]
    object.__setattr__(seal_entry.batch, "kind", "transition")
    _refresh_fast_tail_checkpoint(image, seal_entry)
    with pytest.raises(ValueError, match="no state transition"):
        sealed.load_head_v2(
            domain.scope_ref,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        )


def test_public_loads_reject_sealed_projection_substitution() -> None:
    lifecycle = GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2

    domain, store = _sealed_store(with_stream=True)
    image = _raw_image(store, domain.scope_ref)
    store._domains[domain.scope_ref] = replace(
        image,
        entries=tuple(reversed(image.entries)),
    )
    with pytest.raises(ValueError, match="global sequence"):
        store.load_head_v2(domain.scope_ref, lifecycle)

    domain, store = _sealed_store(with_stream=True)
    image = _raw_image(store, domain.scope_ref)
    store._domains[domain.scope_ref] = replace(
        image,
        seal_root=domain.domain_root,
    )
    with pytest.raises(ValueError, match="sealed domain root"):
        store.load_head_v2(domain.scope_ref, lifecycle)

    domain, store = _sealed_store(with_stream=True)
    image = _raw_image(store, domain.scope_ref)
    wrong_heads = dict(image.heads)
    wrong_heads[lifecycle] = GovernanceHeadV2.genesis(domain, lifecycle)
    store._domains[domain.scope_ref] = replace(image, heads=wrong_heads)
    with pytest.raises(ValueError, match="head projection"):
        store.load_head_v2(domain.scope_ref, lifecycle)

    domain, store = _sealed_store(with_stream=True)
    image = _raw_image(store, domain.scope_ref)
    wrong_final_heads = dict(image.heads)
    wrong_final_heads["authority:alpha"] = GovernanceHeadV2.genesis(
        domain,
        "authority:alpha",
    )
    store._domains[domain.scope_ref] = replace(image, heads=wrong_final_heads)
    with pytest.raises(ValueError, match="head projection"):
        store.load_head_v2(domain.scope_ref, "authority:alpha")

    domain, store = _sealed_store(with_stream=True)
    image = _raw_image(store, domain.scope_ref)
    missing_state = dict(image.states)
    missing_state.pop(lifecycle)
    store._domains[domain.scope_ref] = replace(image, states=missing_state)
    with pytest.raises(ValueError, match="projections are incomplete"):
        store.load_state_v2(domain.scope_ref, lifecycle)

    domain, store = _sealed_store(with_stream=True)
    image = _raw_image(store, domain.scope_ref)
    wrong_state = dict(image.states)
    wrong_state[lifecycle] = {"seal": {}}
    store._domains[domain.scope_ref] = replace(image, states=wrong_state)
    with pytest.raises(ValueError, match="state projection"):
        store.load_state_v2(domain.scope_ref, lifecycle)


def test_full_replay_detects_checkpoint_history_substitution() -> None:
    domain, store, _batch = _store_with_transition()
    image = store._domains[domain.scope_ref]
    checkpoint = image.verified_checkpoint
    assert checkpoint is not None
    tail = image.entries[-1]
    tail_root = authority_store_reference._entry_integrity_root(tail)
    object.__setattr__(checkpoint, "parent_history_root", domain.domain_root)
    object.__setattr__(
        checkpoint,
        "history_root",
        authority_store_reference._history_successor_root(
            domain.domain_root,
            tail_root,
        ),
    )
    with pytest.raises(ValueError, match="historical checkpoint"):
        store.load_head_v2(domain.scope_ref, "authority:alpha")
