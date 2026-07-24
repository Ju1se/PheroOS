from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from inspect import signature
import json

import pytest

from pheroos.governance import (
    AuthorityDomain,
    GovernanceCommitBatch,
    GovernanceCommitReceipt,
    GovernanceHead,
    GovernanceStateStore,
    InMemoryGovernanceStateStore,
    PreparedGovernanceTransition,
)
from pheroos.governance.errors import GovernanceError


def canonical_scope(label: str) -> str:
    return "sha256:" + sha256(f"pheroos-test-scope:{label}".encode()).hexdigest()


SCOPE_ALPHA = canonical_scope("alpha")
SCOPE_BETA = canonical_scope("beta")


def prepared_batch(
    store: InMemoryGovernanceStateStore,
    *,
    scope_ref: str = SCOPE_ALPHA,
    stream: str = "commit",
    transition_id: str = "transition:1",
    value: int = 1,
    identity_claims: dict[str, dict[str, object]] | None = None,
) -> GovernanceCommitBatch:
    head = store.load_head(scope_ref, stream)
    transition = PreparedGovernanceTransition.from_head(
        head,
        transition_id=transition_id,
        state_records={"state": {"value": value}},
        identity_claims=identity_claims,
    )
    return GovernanceCommitBatch(
        transition=transition,
        trace_records=[
            {
                "trace_id": f"trace:{transition_id}",
                "scope_ref": scope_ref,
                "stream": stream,
                "transition_id": transition_id,
                "event": "state_advanced",
                "value": value,
            }
        ],
    )


def test_authority_records_are_portable_deterministic_and_defensively_snapshotted() -> (
    None
):
    state = {"state": {"values": [1]}}
    claims = {"claim:1": {"subject": {"roles": ["reviewer"]}}}
    trace = {
        "trace_id": "trace:1",
        "scope_ref": SCOPE_ALPHA,
        "stream": "commit",
        "transition_id": "transition:1",
        "details": {"values": [1]},
    }
    head = GovernanceHead.genesis(SCOPE_ALPHA, "commit")
    transition = PreparedGovernanceTransition.from_head(
        head,
        transition_id="transition:1",
        state_records=state,
        identity_claims=claims,
    )
    batch = GovernanceCommitBatch(transition, [trace])
    state_root = transition.state_root
    batch_root = batch.batch_root
    state["state"]["values"].append(2)
    claims["claim:1"]["subject"]["roles"].append("admin")
    trace["details"]["values"].append(2)

    assert transition.state_records["state"]["values"] == (1,)
    assert transition.identity_claims["claim:1"]["subject"]["roles"] == ("reviewer",)
    assert batch.trace_records[0]["details"]["values"] == (1,)
    assert transition.state_root == state_root
    assert batch.batch_root == batch_root
    assert PreparedGovernanceTransition.from_dict(transition.to_dict()) == transition
    assert GovernanceCommitBatch.from_dict(batch.to_dict()) == batch
    assert json.loads(json.dumps(batch.to_dict())) == batch.to_dict()

    portable = batch.to_dict()
    portable["transition"]["state_records"]["state"]["values"].append(99)
    portable["trace_records"][0]["details"]["values"].append(99)
    assert transition.state_records["state"]["values"] == (1,)
    assert batch.trace_records[0]["details"]["values"] == (1,)


@pytest.mark.parametrize(
    "invalid",
    (
        "scope:alpha",
        "",
        "sha256:" + "a" * 63,
        "sha256:" + "A" * 64,
        "sha512:" + "a" * 64,
    ),
)
def test_authority_domain_requires_opaque_canonical_scope_ref(invalid: str) -> None:
    with pytest.raises(GovernanceError, match="canonical SHA-256 digest"):
        AuthorityDomain(invalid)

    assert AuthorityDomain(SCOPE_ALPHA).scope_ref == SCOPE_ALPHA


def test_state_store_protocol_is_runtime_checkable_with_stable_method_shapes() -> None:
    store = InMemoryGovernanceStateStore()
    assert isinstance(store, GovernanceStateStore)
    expected = {
        "load_head": ("self", "scope_ref", "stream"),
        "load_state": ("self", "scope_ref", "stream"),
        "trace_records": ("self", "scope_ref", "stream"),
        "load_receipt": ("self", "scope_ref", "transition_id"),
        "claim_identity": ("self", "scope_ref", "identity_id", "body"),
        "compare_and_advance": ("self", "batch"),
        "atomic_commit": ("self", "batch"),
        "checkpoint": ("self", "scope_ref"),
        "rehydrate": ("self", "payload"),
        "rehydrate_snapshot": ("self", "payload"),
        "retire": ("self", "scope_ref"),
        "snapshot": ("self",),
        "fingerprint": ("self",),
    }
    for name, parameters in expected.items():
        assert (
            tuple(signature(getattr(GovernanceStateStore, name)).parameters)
            == parameters
        )


def test_commit_advances_exact_head_and_atomically_records_state_and_trace() -> None:
    store = InMemoryGovernanceStateStore()
    genesis = store.load_head(SCOPE_ALPHA, "commit")
    first = prepared_batch(store)

    receipt = store.atomic_commit(first)
    current = store.load_head(SCOPE_ALPHA, "commit")

    assert isinstance(store, GovernanceStateStore)
    assert receipt.matches(first) is True
    assert current == GovernanceHead(
        scope_ref=SCOPE_ALPHA,
        stream="commit",
        revision=1,
        parent_root=genesis.state_root,
        state_root=first.transition.state_root,
        transition_id="transition:1",
    )
    assert store.load_state(SCOPE_ALPHA, "commit")["state"]["value"] == 1
    assert store.trace_records(SCOPE_ALPHA, "commit") == first.trace_records
    assert store.load_receipt(SCOPE_ALPHA, "transition:1") == receipt
    assert GovernanceCommitReceipt.from_dict(receipt.to_dict()) == receipt

    second = prepared_batch(
        store,
        transition_id="transition:2",
        value=2,
    )
    second_receipt = store.compare_and_advance(second)

    assert second_receipt.revision == 2
    assert second_receipt.parent_root == receipt.state_root
    assert store.load_head(SCOPE_ALPHA, "commit").revision == 2
    assert len(store.trace_records(SCOPE_ALPHA, "commit")) == 2


def test_loaded_authority_views_are_detached_and_cannot_mutate_history() -> None:
    store = InMemoryGovernanceStateStore()
    batch = prepared_batch(store)
    committed = store.atomic_commit(batch)
    expected_receipt = GovernanceCommitReceipt.from_dict(committed.to_dict())

    first_head = store.load_head(SCOPE_ALPHA, "commit")
    first_state = store.load_state(SCOPE_ALPHA, "commit")
    first_traces = store.trace_records(SCOPE_ALPHA, "commit")
    first_receipt = store.load_receipt(SCOPE_ALPHA, "transition:1")
    assert first_receipt is not None

    assert first_head is not store.load_head(SCOPE_ALPHA, "commit")
    assert first_state is not store.load_state(SCOPE_ALPHA, "commit")
    assert first_traces[0] is not store.trace_records(SCOPE_ALPHA, "commit")[0]
    assert first_receipt is not store.load_receipt(SCOPE_ALPHA, "transition:1")
    with pytest.raises(TypeError):
        first_state["state"]["value"] = 99  # type: ignore[index]
    with pytest.raises(TypeError):
        first_traces[0]["value"] = 99  # type: ignore[index]

    object.__setattr__(first_head, "revision", 99)
    object.__setattr__(first_receipt, "revision", 99)
    object.__setattr__(committed, "revision", 99)
    object.__setattr__(batch.transition, "state_root", "sha256:" + "0" * 64)

    assert store.load_head(SCOPE_ALPHA, "commit").revision == 1
    assert store.load_state(SCOPE_ALPHA, "commit")["state"]["value"] == 1
    assert store.trace_records(SCOPE_ALPHA, "commit")[0]["value"] == 1
    assert store.load_receipt(SCOPE_ALPHA, "transition:1") == expected_receipt


def test_identity_claims_are_idempotent_but_conflicting_bodies_fail_closed() -> None:
    store = InMemoryGovernanceStateStore()
    body = {"subject": "principal:1", "role": "reviewer"}

    first = store.claim_identity(SCOPE_ALPHA, "claim:principal:1", body)
    retry = store.claim_identity(
        SCOPE_ALPHA,
        "claim:principal:1",
        {"role": "reviewer", "subject": "principal:1"},
    )

    assert retry == first
    with pytest.raises(GovernanceError, match="governance_identity_conflict"):
        store.claim_identity(
            SCOPE_ALPHA,
            "claim:principal:1",
            {"subject": "principal:1", "role": "admin"},
        )

    other = store.claim_identity(
        SCOPE_BETA,
        "claim:principal:1",
        {"subject": "principal:1", "role": "admin"},
    )
    assert other != first


def test_commit_retry_is_idempotent_and_changed_transition_body_conflicts() -> None:
    store = InMemoryGovernanceStateStore()
    batch = prepared_batch(store)

    first = store.commit(batch)
    retry = store.commit(GovernanceCommitBatch.from_dict(batch.to_dict()))

    assert retry == first
    assert store.load_head(SCOPE_ALPHA, "commit").revision == 1
    assert len(store.trace_records(SCOPE_ALPHA, "commit")) == 1

    changed = GovernanceCommitBatch(
        transition=replace(
            batch.transition,
            state_records={"state": {"value": 99}},
            state_root="",
        ),
        trace_records=[
            {
                **batch.trace_records[0],
                "value": 99,
            }
        ],
    )
    with pytest.raises(GovernanceError, match="governance_transition_conflict"):
        store.commit(changed)


def test_stale_fork_loses_cas_without_a_second_state_or_trace_commit() -> None:
    store = InMemoryGovernanceStateStore()
    winner = prepared_batch(store, transition_id="transition:winner", value=1)
    loser = prepared_batch(store, transition_id="transition:loser", value=2)

    winner_receipt = store.atomic_commit(winner)
    with pytest.raises(GovernanceError, match="governance_cas_conflict:retry_required"):
        store.atomic_commit(loser)

    assert (
        store.load_head(SCOPE_ALPHA, "commit").state_root == winner_receipt.state_root
    )
    assert store.load_state(SCOPE_ALPHA, "commit")["state"]["value"] == 1
    assert store.trace_records(SCOPE_ALPHA, "commit") == winner.trace_records
    assert store.load_receipt(SCOPE_ALPHA, "transition:loser") is None


@pytest.mark.parametrize(
    "failure_stage",
    ["before_commit", "after_state_prepare", "after_trace_prepare", "before_publish"],
)
def test_failure_injection_never_publishes_state_without_trace(
    failure_stage: str,
) -> None:
    def inject(stage: str, _batch: GovernanceCommitBatch) -> None:
        if stage == failure_stage:
            raise RuntimeError(f"injected:{stage}")

    store = InMemoryGovernanceStateStore(failure_injector=inject)
    batch = prepared_batch(store)

    with pytest.raises(RuntimeError, match=f"injected:{failure_stage}"):
        store.atomic_commit(batch)

    assert store.load_head(SCOPE_ALPHA, "commit").revision == 0
    assert store.load_state(SCOPE_ALPHA, "commit") == {}
    assert store.trace_records(SCOPE_ALPHA, "commit") == ()
    assert store.active_domain_count == 0
    assert store.retained_authority_record_count == 0


def test_checkpoint_round_trip_rehydrates_current_authority_and_continues_cas() -> None:
    store = InMemoryGovernanceStateStore()
    store.claim_identity(
        SCOPE_ALPHA,
        "claim:standalone",
        {"subject": "principal:standalone"},
    )
    store.atomic_commit(
        prepared_batch(
            store,
            transition_id="transition:1",
            value=1,
            identity_claims={"claim:batched": {"subject": "principal:batched"}},
        )
    )
    store.atomic_commit(prepared_batch(store, transition_id="transition:2", value=2))
    detached_checkpoint = store.checkpoint(SCOPE_ALPHA)
    original_fingerprint = store.fingerprint()
    detached_checkpoint["heads"][0]["revision"] = 99
    detached_checkpoint["identity_claims"]["claim:standalone"]["subject"] = "changed"
    assert store.fingerprint() == original_fingerprint

    checkpoint = json.loads(json.dumps(store.checkpoint(SCOPE_ALPHA)))

    restarted = InMemoryGovernanceStateStore.from_checkpoint(checkpoint)

    assert restarted.fingerprint() == store.fingerprint()
    assert restarted.load_head(SCOPE_ALPHA, "commit") == store.load_head(
        SCOPE_ALPHA,
        "commit",
    )
    assert restarted.load_state(SCOPE_ALPHA, "commit") == store.load_state(
        SCOPE_ALPHA,
        "commit",
    )
    assert restarted.trace_records(SCOPE_ALPHA, "commit") == store.trace_records(
        SCOPE_ALPHA,
        "commit",
    )
    receipt = restarted.atomic_commit(
        prepared_batch(restarted, transition_id="transition:3", value=3)
    )
    assert receipt.revision == 3

    checkpoint["heads"][0]["revision"] = 99
    checkpoint["batches"][0]["transition"]["state_records"]["state"]["value"] = 99
    assert restarted.load_head(SCOPE_ALPHA, "commit").revision == 3
    assert restarted.load_state(SCOPE_ALPHA, "commit")["state"]["value"] == 3
    with pytest.raises(GovernanceError, match="checkpoint root"):
        InMemoryGovernanceStateStore.from_checkpoint(checkpoint)


def test_retire_releases_active_graph_and_tombstone_rejects_all_replay() -> None:
    store = InMemoryGovernanceStateStore()
    batch = prepared_batch(store)
    store.claim_identity(
        SCOPE_ALPHA,
        "claim:retired",
        {"subject": "principal:retired", "role": "reviewer"},
    )
    store.atomic_commit(batch)
    tombstone = store.retire(SCOPE_ALPHA)

    assert store.retire(SCOPE_ALPHA) == tombstone
    assert store.active_domain_count == 0
    assert store.retained_authority_record_count == 0
    assert store.tombstone_count == 1
    assert store.is_retired(SCOPE_ALPHA) is True
    operations = (
        lambda: store.load_head(SCOPE_ALPHA, "commit"),
        lambda: store.load_state(SCOPE_ALPHA, "commit"),
        lambda: store.claim_identity(
            SCOPE_ALPHA,
            "claim:retired",
            {"subject": "principal:retired", "role": "admin"},
        ),
        lambda: store.atomic_commit(batch),
        lambda: store.checkpoint(SCOPE_ALPHA),
    )
    for operation in operations:
        with pytest.raises(GovernanceError, match="governance_domain_retired"):
            operation()

    portable = json.loads(json.dumps(store.snapshot()))
    restarted = InMemoryGovernanceStateStore.from_snapshot(portable)
    assert restarted.fingerprint() == store.fingerprint()
    assert restarted.is_retired(SCOPE_ALPHA) is True
    restarted_fingerprint = restarted.fingerprint()
    portable["tombstones"][0]["final_root"] = "sha256:" + "0" * 64
    assert restarted.fingerprint() == restarted_fingerprint
    with pytest.raises(GovernanceError, match="governance_domain_retired"):
        restarted.atomic_commit(batch)
    with pytest.raises(GovernanceError, match="governance_domain_retired"):
        restarted.claim_identity(
            SCOPE_ALPHA,
            "claim:retired",
            {"subject": "principal:retired", "role": "owner"},
        )


def test_domain_isolation_and_snapshot_fingerprint_are_order_deterministic() -> None:
    first = InMemoryGovernanceStateStore()
    second = InMemoryGovernanceStateStore()

    for store, scopes in (
        (first, (SCOPE_ALPHA, SCOPE_BETA)),
        (second, (SCOPE_BETA, SCOPE_ALPHA)),
    ):
        for index, scope_ref in enumerate(scopes):
            store.atomic_commit(
                prepared_batch(
                    store,
                    scope_ref=scope_ref,
                    transition_id="transition:shared",
                    value=1 if scope_ref == SCOPE_ALPHA else 2,
                )
            )

    assert first.load_state(SCOPE_ALPHA, "commit")["state"]["value"] == 1
    assert first.load_state(SCOPE_BETA, "commit")["state"]["value"] == 2
    assert first.snapshot() == second.snapshot()
    assert first.fingerprint() == second.fingerprint()

    with pytest.raises(GovernanceError, match="crosses authority scope"):
        GovernanceCommitBatch(
            transition=prepared_batch(first).transition,
            trace_records=[
                {
                    "trace_id": "trace:cross-scope",
                    "scope_ref": SCOPE_BETA,
                    "stream": "commit",
                    "transition_id": "transition:1",
                }
            ],
        )


def test_32_workers_retrying_same_batch_receive_one_identical_receipt() -> None:
    store = InMemoryGovernanceStateStore()
    batch = prepared_batch(store)

    with ThreadPoolExecutor(max_workers=32) as executor:
        receipts = tuple(
            executor.map(lambda _index: store.atomic_commit(batch), range(32))
        )

    assert len(set(receipts)) == 1
    assert store.load_head(SCOPE_ALPHA, "commit").revision == 1
    assert len(store.trace_records(SCOPE_ALPHA, "commit")) == 1


def test_32_conflicting_workers_produce_exactly_one_commit_and_31_retry_conflicts() -> (
    None
):
    store = InMemoryGovernanceStateStore()
    batches = tuple(
        prepared_batch(
            store,
            transition_id=f"transition:{index}",
            value=index,
        )
        for index in range(32)
    )

    def attempt(batch: GovernanceCommitBatch) -> str:
        try:
            store.atomic_commit(batch)
        except GovernanceError as exc:
            return str(exc)
        return "committed"

    with ThreadPoolExecutor(max_workers=32) as executor:
        outcomes = tuple(executor.map(attempt, batches))

    assert outcomes.count("committed") == 1
    assert (
        sum("governance_cas_conflict:retry_required" in item for item in outcomes) == 31
    )
    assert store.load_head(SCOPE_ALPHA, "commit").revision == 1
    assert len(store.trace_records(SCOPE_ALPHA, "commit")) == 1


def test_10000_retired_scopes_leave_no_active_authority_graph() -> None:
    store = InMemoryGovernanceStateStore()

    for index in range(10_000):
        scope_ref = canonical_scope(f"retired:{index:05d}")
        store.claim_identity(scope_ref, "claim:run", {"run": index})
        store.retire(scope_ref)

    assert store.active_domain_count == 0
    assert store.retained_authority_record_count == 0
    assert store.tombstone_count == 10_000
