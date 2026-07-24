from __future__ import annotations

from pheroos.conformance.checks.authority_ledger_contract import (
    GovernanceStateStoreConformanceAdapter,
)
from pheroos.conformance.checks.trace_store_contract import (
    TraceStoreConformanceAdapter,
)
from pheroos.drivers.invocation_store_v2 import DriverInvocationStoreV2
from pheroos.governance.authority_domain import GovernanceStateStore


class _UnimplementedGovernanceStore(GovernanceStateStore):
    pass


class _UnimplementedDriverInvocationStore(DriverInvocationStoreV2):
    pass


class _UnimplementedGovernanceAdapter(GovernanceStateStoreConformanceAdapter):
    pass


class _UnimplementedTraceAdapter(TraceStoreConformanceAdapter):
    pass


def test_governance_store_protocol_declarations_are_inert() -> None:
    store = _UnimplementedGovernanceStore()

    results = (
        store.load_head("scope", "stream"),
        store.load_state("scope", "stream"),
        store.trace_records("scope", "stream"),
        store.load_receipt("scope", "transition"),
        store.claim_identity("scope", "identity", {}),
        store.compare_and_advance(None),  # type: ignore[arg-type]
        store.atomic_commit(None),  # type: ignore[arg-type]
        store.checkpoint("scope"),
        store.rehydrate({}),
        store.rehydrate_snapshot({}),
        store.retire("scope"),
        store.snapshot(),
        store.fingerprint(),
    )

    assert results == (None,) * len(results)


def test_driver_store_protocol_declarations_are_inert() -> None:
    store = _UnimplementedDriverInvocationStore()

    results = (
        store.record(None, None),  # type: ignore[arg-type]
        store.get("scope", "driver", "idempotency-key"),
        store.retire("scope"),
        store.checkpoint(),
    )

    assert results == (None,) * len(results)


def test_conformance_adapter_protocol_declarations_are_inert() -> None:
    governance = _UnimplementedGovernanceAdapter()
    trace = _UnimplementedTraceAdapter()

    results = (
        governance.create_store(),
        governance.restore_checkpoint({}),
        governance.restore_snapshot({}),
        governance.create_failure_injected_store("after_state_prepare"),
        trace.create_store(),
    )

    assert results == (None,) * len(results)
