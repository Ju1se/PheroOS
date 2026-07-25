from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from typing import Any, Protocol, runtime_checkable

from pheroos.conformance.report import CheckResult
from pheroos.governance._authority.ledger import InMemoryGovernanceStateStore
from pheroos.governance.authority_domain import (
    GovernanceCommitBatch,
    GovernanceStateStore,
    PreparedGovernanceTransition,
)
from pheroos.governance.errors import GovernanceError


GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION = (
    "pheroos-governance-state-store-conformance-v1"
)
GOVERNANCE_STATE_STORE_FAILURE_STAGES = (
    "after_state_prepare",
    "after_trace_prepare",
)
_CONCURRENCY_WORKERS = 32


@runtime_checkable
class GovernanceStateStoreConformanceAdapter(Protocol):
    """Test fixture contract for an external GovernanceStateStore backend."""

    implementation_id: str
    conformance_version: str

    def create_store(self) -> GovernanceStateStore: ...

    def restore_checkpoint(
        self,
        payload: Mapping[str, Any],
    ) -> GovernanceStateStore: ...

    def restore_snapshot(
        self,
        payload: Mapping[str, Any],
    ) -> GovernanceStateStore: ...

    def create_failure_injected_store(
        self,
        stage: str,
    ) -> GovernanceStateStore: ...


class ReferenceGovernanceStateStoreConformanceAdapter:
    """Conformance fixture for the provider-free in-memory reference store."""

    __slots__ = ()

    implementation_id = "pheroos-in-memory-governance-state-store-v1"
    conformance_version = GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION

    def create_store(self) -> GovernanceStateStore:
        return InMemoryGovernanceStateStore()

    def restore_checkpoint(
        self,
        payload: Mapping[str, Any],
    ) -> GovernanceStateStore:
        return InMemoryGovernanceStateStore.from_checkpoint(payload)

    def restore_snapshot(
        self,
        payload: Mapping[str, Any],
    ) -> GovernanceStateStore:
        return InMemoryGovernanceStateStore.from_snapshot(payload)

    def create_failure_injected_store(
        self,
        stage: str,
    ) -> GovernanceStateStore:
        def inject(observed: str, _selected: GovernanceCommitBatch) -> None:
            if observed == stage:
                raise RuntimeError(f"injected:{stage}")

        return InMemoryGovernanceStateStore(failure_injector=inject)


def run_governance_state_store_conformance(
    adapter: GovernanceStateStoreConformanceAdapter,
) -> CheckResult:
    """Run the reusable provider-neutral authority-store conformance matrix."""

    problems: list[str] = []
    if not isinstance(adapter, GovernanceStateStoreConformanceAdapter):
        return CheckResult(
            "authority_ledger_contract",
            False,
            "adapter_protocol",
        )
    if (
        not isinstance(adapter.implementation_id, str)
        or not adapter.implementation_id
        or adapter.implementation_id != adapter.implementation_id.strip()
    ):
        return CheckResult(
            "authority_ledger_contract",
            False,
            "adapter_implementation_id",
        )
    if adapter.conformance_version != GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION:
        return CheckResult(
            "authority_ledger_contract",
            False,
            "adapter_version",
        )
    try:
        store = adapter.create_store()
        if not isinstance(store, GovernanceStateStore):
            return CheckResult(
                "authority_ledger_contract",
                False,
                "store_protocol",
            )
        _evaluate_store_contract(adapter, store, problems)
    except Exception as exc:  # total-function boundary for third-party adapters
        problems.append(f"adapter_exception:{type(exc).__name__}:{exc}")
    return CheckResult(
        "authority_ledger_contract",
        not problems,
        ", ".join(problems),
    )


def check() -> CheckResult:
    return run_governance_state_store_conformance(
        ReferenceGovernanceStateStoreConformanceAdapter()
    )


def _evaluate_store_contract(
    adapter: GovernanceStateStoreConformanceAdapter,
    store: GovernanceStateStore,
    problems: list[str],
) -> None:
    ledger_scope = _scope("ledger")
    other_scope = _scope("other")
    _evaluate_opaque_scope_shape(store, problems)
    winner = _exercise_commit_and_identity_contract(store, ledger_scope, problems)
    _exercise_scope_isolation(store, ledger_scope, other_scope, problems)
    if not _exercise_checkpoint_restore(adapter, store, ledger_scope, problems):
        return
    _exercise_failure_atomicity(adapter, problems)
    _evaluate_retry_concurrency(adapter, problems)
    _evaluate_conflict_concurrency(adapter, problems)
    _exercise_retirement_and_snapshot_restore(
        adapter,
        store,
        winner,
        ledger_scope,
        other_scope,
        problems,
    )


def _evaluate_opaque_scope_shape(
    store: GovernanceStateStore,
    problems: list[str],
) -> None:
    if not _rejects(
        lambda: store.load_head("tenant-or-run-identifier", "commit"),
        "canonical SHA-256 digest",
    ):
        problems.append("opaque_scope_shape")


def _exercise_commit_and_identity_contract(
    store: GovernanceStateStore,
    ledger_scope: str,
    problems: list[str],
) -> GovernanceCommitBatch:
    winner = _batch(store, ledger_scope, "transition:winner", 1)
    stale = _batch(store, ledger_scope, "transition:stale", 2)
    receipt = store.atomic_commit(winner)
    if not receipt.matches(winner):
        problems.append("receipt_binding")
    if store.atomic_commit(winner) != receipt:
        problems.append("idempotent_retry")
    if not _rejects(
        lambda: store.atomic_commit(stale),
        "governance_cas_conflict:retry_required",
    ):
        problems.append("cas_conflict")
    if store.load_head(ledger_scope, "commit").revision != 1:
        problems.append("double_advance")
    if len(store.trace_records(ledger_scope, "commit")) != 1:
        problems.append("double_trace")

    claim = {"subject": "principal:1", "role": "reviewer"}
    claim_root = store.claim_identity(ledger_scope, "claim:1", claim)
    if store.claim_identity(ledger_scope, "claim:1", dict(claim)) != claim_root:
        problems.append("claim_retry")
    if not _rejects(
        lambda: store.claim_identity(
            ledger_scope,
            "claim:1",
            {"subject": "principal:1", "role": "admin"},
        ),
        "governance_identity_conflict",
    ):
        problems.append("claim_conflict")
    return winner


def _exercise_scope_isolation(
    store: GovernanceStateStore,
    ledger_scope: str,
    other_scope: str,
    problems: list[str],
) -> None:
    isolated = _batch(store, other_scope, "transition:winner", 3)
    store.atomic_commit(isolated)
    if store.load_state(ledger_scope, "commit")["state"]["value"] != 1:
        problems.append("cross_scope_pollution")


def _exercise_checkpoint_restore(
    adapter: GovernanceStateStoreConformanceAdapter,
    store: GovernanceStateStore,
    ledger_scope: str,
    problems: list[str],
) -> bool:
    checkpoint = store.checkpoint(ledger_scope)
    restarted = adapter.restore_checkpoint(checkpoint)
    if not isinstance(restarted, GovernanceStateStore):
        problems.append("checkpoint_store_protocol")
        return False
    if restarted.checkpoint(ledger_scope) != checkpoint:
        problems.append("checkpoint_rehydrate")
    if restarted.load_head(ledger_scope, "commit") != store.load_head(
        ledger_scope,
        "commit",
    ):
        problems.append("checkpoint_head")
    if restarted.trace_records(ledger_scope, "commit") != store.trace_records(
        ledger_scope,
        "commit",
    ):
        problems.append("checkpoint_trace")
    return True


def _exercise_failure_atomicity(
    adapter: GovernanceStateStoreConformanceAdapter,
    problems: list[str],
) -> None:
    for stage in GOVERNANCE_STATE_STORE_FAILURE_STAGES:
        failing = adapter.create_failure_injected_store(stage)
        if not isinstance(failing, GovernanceStateStore):
            problems.append(f"failure_store_protocol:{stage}")
            continue
        failure_scope = _scope(stage)
        selected = _batch(failing, failure_scope, "transition:1", 1)
        try:
            failing.atomic_commit(selected)
        except Exception:
            pass
        else:
            problems.append(f"failure_not_injected:{stage}")
        if (
            failing.load_head(failure_scope, "commit").revision != 0
            or failing.trace_records(failure_scope, "commit")
            or failing.load_state(failure_scope, "commit")
            or failing.load_receipt(failure_scope, "transition:1") is not None
        ):
            problems.append(f"partial_publish:{stage}")


def _exercise_retirement_and_snapshot_restore(
    adapter: GovernanceStateStoreConformanceAdapter,
    store: GovernanceStateStore,
    winner: GovernanceCommitBatch,
    ledger_scope: str,
    other_scope: str,
    problems: list[str],
) -> None:
    tombstone = store.retire(ledger_scope)
    if store.retire(ledger_scope) != tombstone:
        problems.append("retire_retry")
    if store.load_state(other_scope, "commit")["state"]["value"] != 3:
        problems.append("retire_cross_scope_pollution")
    if not _rejects(
        lambda: store.atomic_commit(winner),
        "governance_domain_retired",
    ):
        problems.append("tombstone_replay")
    snapshot = store.snapshot()
    restored = adapter.restore_snapshot(snapshot)
    if not isinstance(restored, GovernanceStateStore):
        problems.append("snapshot_store_protocol")
        return
    if restored.snapshot() != snapshot or restored.fingerprint() != store.fingerprint():
        problems.append("snapshot_rehydrate")
    if restored.load_state(other_scope, "commit")["state"]["value"] != 3:
        problems.append("snapshot_active_scope")
    if not _rejects(
        lambda: restored.load_head(ledger_scope, "commit"),
        "governance_domain_retired",
    ):
        problems.append("snapshot_tombstone")


def _evaluate_retry_concurrency(
    adapter: GovernanceStateStoreConformanceAdapter,
    problems: list[str],
) -> None:
    store = adapter.create_store()
    if not isinstance(store, GovernanceStateStore):
        problems.append("concurrent_retry_store_protocol")
        return
    scope_ref = _scope("concurrent-retry")
    batch = _batch(store, scope_ref, "transition:shared", 1)
    try:
        with ThreadPoolExecutor(max_workers=_CONCURRENCY_WORKERS) as executor:
            receipts = tuple(
                executor.map(
                    lambda _index: store.atomic_commit(batch),
                    range(_CONCURRENCY_WORKERS),
                )
            )
    except Exception as exc:
        problems.append(f"concurrent_retry_exception:{type(exc).__name__}:{exc}")
        return
    if len(set(receipts)) != 1:
        problems.append("concurrent_retry_receipt_divergence")
    if (
        store.load_head(scope_ref, "commit").revision != 1
        or len(store.trace_records(scope_ref, "commit")) != 1
        or store.load_receipt(scope_ref, "transition:shared") != receipts[0]
    ):
        problems.append("concurrent_retry_double_publish")


def _evaluate_conflict_concurrency(
    adapter: GovernanceStateStoreConformanceAdapter,
    problems: list[str],
) -> None:
    store = adapter.create_store()
    if not isinstance(store, GovernanceStateStore):
        problems.append("concurrent_conflict_store_protocol")
        return
    scope_ref = _scope("concurrent-conflict")
    batches = tuple(
        _batch(store, scope_ref, f"transition:{index}", index)
        for index in range(_CONCURRENCY_WORKERS)
    )

    def attempt(batch: GovernanceCommitBatch) -> str:
        try:
            store.atomic_commit(batch)
        except GovernanceError as exc:
            if "governance_cas_conflict:retry_required" in str(exc):
                return "conflict"
            return f"governance_error:{exc}"
        except Exception as exc:
            return f"unexpected:{type(exc).__name__}:{exc}"
        return "committed"

    with ThreadPoolExecutor(max_workers=_CONCURRENCY_WORKERS) as executor:
        outcomes = tuple(executor.map(attempt, batches))
    if outcomes.count("committed") != 1 or outcomes.count("conflict") != (
        _CONCURRENCY_WORKERS - 1
    ):
        problems.append("concurrent_conflict_outcome")
    if (
        store.load_head(scope_ref, "commit").revision != 1
        or len(store.trace_records(scope_ref, "commit")) != 1
    ):
        problems.append("concurrent_conflict_double_publish")


def _batch(
    store: GovernanceStateStore,
    scope_ref: str,
    transition_id: str,
    value: int,
) -> GovernanceCommitBatch:
    transition = PreparedGovernanceTransition.from_head(
        store.load_head(scope_ref, "commit"),
        transition_id=transition_id,
        state_records={"state": {"value": value}},
    )
    return GovernanceCommitBatch(
        transition,
        [
            {
                "trace_id": f"trace:{transition_id}",
                "scope_ref": scope_ref,
                "stream": "commit",
                "transition_id": transition_id,
                "value": value,
            }
        ],
    )


def _scope(label: str) -> str:
    return "sha256:" + sha256(f"pheroos-conformance-scope:{label}".encode()).hexdigest()


def _rejects(operation: Callable[[], object], marker: str) -> bool:
    try:
        operation()
    except GovernanceError as exc:
        return marker in str(exc)
    return False


GovernanceStateStoreConformanceAdapter.__module__ = "pheroos.conformance"
ReferenceGovernanceStateStoreConformanceAdapter.__module__ = "pheroos.conformance"
run_governance_state_store_conformance.__module__ = "pheroos.conformance"


__all__ = [
    "GOVERNANCE_STATE_STORE_FAILURE_STAGES",
    "GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION",
    "GovernanceStateStoreConformanceAdapter",
    "ReferenceGovernanceStateStoreConformanceAdapter",
    "check",
    "run_governance_state_store_conformance",
]
