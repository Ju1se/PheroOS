from collections.abc import Mapping
from typing import Any

from pheroos.conformance import (
    GOVERNANCE_STATE_STORE_FAILURE_STAGES,
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION,
    GovernanceStateStoreConformanceAdapter,
    run_governance_state_store_conformance,
)
from pheroos.conformance.checks import authority_ledger_contract
from pheroos.governance import GovernanceStateStore
from pheroos.governance._authority.ledger import InMemoryGovernanceStateStore
from pheroos.governance.authority_domain import GovernanceCommitBatch


class _ExternalConformanceAdapter:
    implementation_id = "example-external-state-store-v1"
    conformance_version = GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION

    def __init__(self) -> None:
        self.calls: list[str] = []

    def create_store(self) -> GovernanceStateStore:
        self.calls.append("create")
        return InMemoryGovernanceStateStore()

    def restore_checkpoint(
        self,
        payload: Mapping[str, Any],
    ) -> GovernanceStateStore:
        self.calls.append("restore_checkpoint")
        return InMemoryGovernanceStateStore.from_checkpoint(payload)

    def restore_snapshot(
        self,
        payload: Mapping[str, Any],
    ) -> GovernanceStateStore:
        self.calls.append("restore_snapshot")
        return InMemoryGovernanceStateStore.from_snapshot(payload)

    def create_failure_injected_store(
        self,
        stage: str,
    ) -> GovernanceStateStore:
        self.calls.append(f"inject:{stage}")

        def inject(observed: str, _batch: GovernanceCommitBatch) -> None:
            if observed == stage:
                raise OSError(f"external persistence failure:{stage}")

        return InMemoryGovernanceStateStore(failure_injector=inject)


def test_authority_ledger_contract_proves_provider_neutral_atomic_authority() -> None:
    result = authority_ledger_contract.check()

    assert result.ok is True, result.detail
    assert result.name == "authority_ledger_contract"
    assert result.detail == ""


def test_external_state_store_adapter_runs_the_same_complete_matrix() -> None:
    adapter = _ExternalConformanceAdapter()

    assert isinstance(adapter, GovernanceStateStoreConformanceAdapter)
    result = run_governance_state_store_conformance(adapter)

    assert result.ok is True, result.detail
    assert GOVERNANCE_STATE_STORE_FAILURE_STAGES == (
        "after_state_prepare",
        "after_trace_prepare",
    )
    assert adapter.calls == [
        "create",
        "restore_checkpoint",
        *(f"inject:{stage}" for stage in GOVERNANCE_STATE_STORE_FAILURE_STAGES),
        "create",
        "create",
        "restore_snapshot",
    ]


def test_state_store_conformance_rejects_an_incomplete_adapter() -> None:
    class Incomplete:
        implementation_id = "incomplete-v1"

        def create_store(self) -> GovernanceStateStore:
            return InMemoryGovernanceStateStore()

    result = run_governance_state_store_conformance(Incomplete())  # type: ignore[arg-type]

    assert result.ok is False
    assert result.detail == "adapter_protocol"


def test_state_store_conformance_rejects_an_unknown_matrix_version() -> None:
    class UnknownVersion(_ExternalConformanceAdapter):
        conformance_version = "pheroos-governance-state-store-conformance-v999"

    result = run_governance_state_store_conformance(UnknownVersion())

    assert result.ok is False
    assert result.detail == "adapter_version"


def test_state_store_conformance_detects_non_atomic_failure_fixture() -> None:
    class NonAtomicFixture(_ExternalConformanceAdapter):
        implementation_id = "non-atomic-fixture-v1"

        def create_failure_injected_store(
            self,
            stage: str,
        ) -> GovernanceStateStore:
            self.calls.append(f"inject:{stage}")
            return InMemoryGovernanceStateStore()

    result = run_governance_state_store_conformance(NonAtomicFixture())

    assert result.ok is False
    assert "failure_not_injected:after_state_prepare" in result.detail
    assert "partial_publish:after_state_prepare" in result.detail
