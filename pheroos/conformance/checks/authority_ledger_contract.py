from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256

from pheroos.conformance.report import CheckResult
from pheroos.governance._authority.ledger import InMemoryGovernanceStateStore
from pheroos.governance.authority_domain import (
    GovernanceCommitBatch,
    PreparedGovernanceTransition,
)
from pheroos.governance.errors import GovernanceError


def check() -> CheckResult:
    problems: list[str] = []
    store = InMemoryGovernanceStateStore()
    ledger_scope = _scope("ledger")
    other_scope = _scope("other")
    if not _rejects(
        lambda: store.load_head("tenant-or-run-identifier", "commit"),
        "canonical SHA-256 digest",
    ):
        problems.append("opaque_scope_shape")
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

    isolated = _batch(store, other_scope, "transition:winner", 3)
    store.atomic_commit(isolated)
    if store.load_state(ledger_scope, "commit")["state"]["value"] != 1:
        problems.append("cross_scope_pollution")

    checkpoint = store.checkpoint(ledger_scope)
    restarted = InMemoryGovernanceStateStore.from_checkpoint(checkpoint)
    if restarted.checkpoint(ledger_scope) != checkpoint:
        problems.append("checkpoint_rehydrate")

    for stage in ("after_state_prepare", "after_trace_prepare"):
        def inject(
            observed: str,
            _selected: GovernanceCommitBatch,
            *,
            expected: str = stage,
        ) -> None:
            if observed == expected:
                raise RuntimeError(f"injected:{expected}")

        failing = InMemoryGovernanceStateStore(failure_injector=inject)
        failure_scope = _scope(stage)
        selected = _batch(failing, failure_scope, "transition:1", 1)
        try:
            failing.atomic_commit(selected)
        except RuntimeError:
            pass
        else:
            problems.append(f"failure_not_injected:{stage}")
        if (
            failing.load_head(failure_scope, "commit").revision != 0
            or failing.trace_records(failure_scope, "commit")
        ):
            problems.append(f"partial_publish:{stage}")

    tombstone = store.retire(ledger_scope)
    if store.retire(ledger_scope) != tombstone:
        problems.append("retire_retry")
    if store.active_domain_count != 1 or store.retained_authority_record_count == 0:
        # The second opaque scope remains active; the retired scope graph must not.
        problems.append("retire_cardinality")
    if not _rejects(
        lambda: store.atomic_commit(winner),
        "governance_domain_retired",
    ):
        problems.append("tombstone_replay")
    return CheckResult(
        "authority_ledger_contract",
        not problems,
        ", ".join(problems),
    )


def _batch(
    store: InMemoryGovernanceStateStore,
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


__all__ = ["check"]
