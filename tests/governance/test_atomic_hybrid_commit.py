from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

from pheroos.governance._authority.ledger import InMemoryGovernanceStateStore
from pheroos.governance.atomic_evaluation import (
    AtomicHybridCommitStatus,
    commit_prepared_hybrid_transition,
    evaluate_and_commit_hybrid_step,
    finalize_hybrid_commit_transition,
    hybrid_commit_stream,
    prepare_hybrid_commit_transition,
)
from pheroos.governance.authority_domain import AuthorityDomain
from pheroos.governance.errors import GovernanceError
from pheroos.governance.hybrid_commit import evaluate_hybrid_commit_step
from tests.governance.test_hybrid_commit_total_evaluation import _total_request


def _scope(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _prepared(label: str = "atomic"):
    evaluation = evaluate_hybrid_commit_step(request=_total_request(stable=True))
    domain = AuthorityDomain(_scope(label))
    store = InMemoryGovernanceStateStore()
    head = store.load_head(domain.scope_ref, hybrid_commit_stream(evaluation))
    prepared = prepare_hybrid_commit_transition(
        evaluation,
        domain=domain,
        head=head,
    )
    return evaluation, domain, store, prepared


def test_prepare_is_pure_and_atomic_commit_finalizes_output_authority() -> None:
    evaluation, domain, store, prepared = _prepared("atomic-success")

    assert store.load_head(domain.scope_ref, prepared.stream).revision == 0
    assert store.trace_records(domain.scope_ref, prepared.stream) == ()
    assert prepared.evaluation is evaluation

    result = commit_prepared_hybrid_transition(prepared, state_store=store)

    assert result.status is AtomicHybridCommitStatus.COMMITTED
    assert result.authoritative is True
    assert result.terminal is True
    assert result.decision_output_authorized is True
    assert result.diagnostic_deliverable is False
    assert result.retry_required is False
    assert result.evaluation is evaluation
    assert result.receipt is not None
    assert result.receipt.matches(prepared.batch)
    assert store.load_head(domain.scope_ref, prepared.stream).revision == 1
    assert len(store.trace_records(domain.scope_ref, prepared.stream)) == len(
        evaluation.trace_events
    )


def test_exact_retry_is_idempotent() -> None:
    _, _, store, prepared = _prepared("atomic-idempotent")

    first = commit_prepared_hybrid_transition(prepared, state_store=store)
    second = commit_prepared_hybrid_transition(prepared, state_store=store)

    assert first.status is AtomicHybridCommitStatus.COMMITTED
    assert second.status is AtomicHybridCommitStatus.COMMITTED
    assert second.result_root == first.result_root
    assert second.receipt_root == first.receipt_root


def test_stale_head_returns_retry_without_double_commit() -> None:
    evaluation, domain, store, first = _prepared("atomic-cas")
    same_head = store.load_head(domain.scope_ref, first.stream)
    stale = prepare_hybrid_commit_transition(
        evaluation,
        domain=domain,
        head=same_head,
        transition_id="independent-stale-transition",
    )

    committed = commit_prepared_hybrid_transition(first, state_store=store)
    retry = commit_prepared_hybrid_transition(stale, state_store=store)

    assert committed.status is AtomicHybridCommitStatus.COMMITTED
    assert retry.status is AtomicHybridCommitStatus.RETRY_REQUIRED
    assert retry.authoritative is False
    assert retry.terminal is False
    assert retry.retry_required is True
    assert retry.decision_output_authorized is False
    assert retry.evaluation is None
    assert store.load_head(domain.scope_ref, first.stream).revision == 1


@pytest.mark.parametrize(
    "stage",
    ["before_commit", "after_state_prepare", "after_trace_prepare", "before_publish"],
)
def test_failure_injection_never_advances_state_without_trace(stage: str) -> None:
    evaluation = evaluate_hybrid_commit_step(request=_total_request(stable=True))
    domain = AuthorityDomain(_scope(f"atomic-failure:{stage}"))

    def fail(observed: str, _batch) -> None:
        if observed == stage:
            raise RuntimeError(f"injected:{stage}")

    store = InMemoryGovernanceStateStore(failure_injector=fail)
    stream = hybrid_commit_stream(evaluation)
    prepared = prepare_hybrid_commit_transition(
        evaluation,
        domain=domain,
        head=store.load_head(domain.scope_ref, stream),
    )

    result = commit_prepared_hybrid_transition(prepared, state_store=store)

    assert result.status is AtomicHybridCommitStatus.FINALITY_UNAVAILABLE
    assert result.authoritative is False
    assert result.terminal is True
    assert result.diagnostic_deliverable is True
    assert result.decision_output_authorized is False
    assert result.evaluation is None
    assert result.receipt is None
    assert store.load_head(domain.scope_ref, stream).revision == 0
    assert store.trace_records(domain.scope_ref, stream) == ()


def test_forged_or_unpersisted_receipt_cannot_finalize() -> None:
    _, _, store, prepared = _prepared("atomic-forged-receipt")
    committed = commit_prepared_hybrid_transition(prepared, state_store=store)
    assert committed.receipt is not None
    forged = replace(
        committed.receipt,
        revision=committed.receipt.revision + 1,
        receipt_root="",
    )

    result = finalize_hybrid_commit_transition(
        prepared,
        receipt=forged,
        state_store=store,
    )

    assert result.status is AtomicHybridCommitStatus.INVALID
    assert result.authoritative is False
    assert result.decision_output_authorized is False
    assert result.evaluation is None


def test_checkpoint_rehydrate_preserves_receipt_finalization() -> None:
    _, domain, store, prepared = _prepared("atomic-rehydrate")
    committed = commit_prepared_hybrid_transition(prepared, state_store=store)
    assert committed.receipt is not None
    restarted = InMemoryGovernanceStateStore.from_snapshot(store.snapshot())

    finalized = finalize_hybrid_commit_transition(
        prepared,
        receipt=committed.receipt,
        state_store=restarted,
    )

    assert finalized.status is AtomicHybridCommitStatus.COMMITTED
    assert finalized.authoritative is True
    assert finalized.receipt_root == committed.receipt_root
    assert restarted.load_head(domain.scope_ref, prepared.stream).revision == 1


def test_scope_rebinding_is_rejected_before_prepare() -> None:
    evaluation, domain, store, prepared = _prepared("atomic-scope-a")
    other = AuthorityDomain(_scope("atomic-scope-b"))

    with pytest.raises(GovernanceError, match="crosses scope or stream"):
        prepare_hybrid_commit_transition(
            evaluation,
            domain=other,
            head=store.load_head(domain.scope_ref, prepared.stream),
        )


def test_high_level_entry_commits_against_explicit_store_and_domain() -> None:
    domain = AuthorityDomain(_scope("atomic-entry"))
    store = InMemoryGovernanceStateStore()

    result = evaluate_and_commit_hybrid_step(
        _total_request(stable=True),
        domain=domain,
        state_store=store,
    )

    assert result.status is AtomicHybridCommitStatus.COMMITTED
    assert result.authoritative is True
    assert result.decision_output_authorized is True


def test_retired_scope_returns_deliverable_invalid_without_output_authority() -> None:
    evaluation = evaluate_hybrid_commit_step(request=_total_request(stable=True))
    domain = AuthorityDomain(_scope("atomic-retired"))
    store = InMemoryGovernanceStateStore()
    stream = hybrid_commit_stream(evaluation)
    prepared = prepare_hybrid_commit_transition(
        evaluation,
        domain=domain,
        head=store.load_head(domain.scope_ref, stream),
    )
    store.retire(domain.scope_ref)

    result = commit_prepared_hybrid_transition(prepared, state_store=store)

    assert result.status is AtomicHybridCommitStatus.INVALID
    assert result.terminal is True
    assert result.diagnostic_deliverable is True
    assert result.decision_output_authorized is False
