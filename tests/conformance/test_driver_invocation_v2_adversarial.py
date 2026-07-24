from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from threading import Lock
from typing import cast

import pytest

from pheroos.conformance import (
    DRIVER_INVOCATION_STORE_CONFORMANCE_VERSION_V2,
    DriverInvocationStoreConformanceAdapterV2,
    ReferenceDriverInvocationStoreConformanceAdapterV2,
    run_driver_invocation_store_conformance_v2,
)
from pheroos.drivers import (
    DriverInvocationReceiptV2,
    DriverInvocationRequestV2,
    DriverInvocationResultV2,
    DriverInvocationStoreV2,
    InMemoryDriverInvocationStoreV2,
)


class _InvalidImplementationIdAdapter(
    ReferenceDriverInvocationStoreConformanceAdapterV2
):
    implementation_id = " invalid "


class _InvalidVersionAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    conformance_version = "unsupported-driver-invocation-conformance"


class _NonStoreAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def create_store_v2(self) -> DriverInvocationStoreV2:
        return cast(DriverInvocationStoreV2, object())


class _WrongStoreVersion(InMemoryDriverInvocationStoreV2):
    store_version = "unsupported-driver-invocation-store"


class _WrongStoreVersionAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def create_store_v2(self) -> DriverInvocationStoreV2:
        return _WrongStoreVersion()


class _RaisingAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def create_store_v2(self) -> DriverInvocationStoreV2:
        raise OSError("third-party store construction failed")


class _BadProvenanceAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def invoke_v2(
        self,
        request: DriverInvocationRequestV2,
    ) -> DriverInvocationResultV2:
        result = super().invoke_v2(request)
        return replace(
            result,
            provenance=request.driver_id,
            payload=dict(result.payload),
            result_digest="",
        )


class _InvalidWireAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def invoke_v2(
        self,
        request: DriverInvocationRequestV2,
    ) -> DriverInvocationResultV2:
        result = super().invoke_v2(request)
        object.__setattr__(result, "result_digest", "sha256:" + "0" * 64)
        return result


class _ChangingRetryStore(InMemoryDriverInvocationStoreV2):
    def __init__(self) -> None:
        super().__init__()
        self._seen: dict[str, int] = {}

    def record(
        self,
        request: DriverInvocationRequestV2,
        result: DriverInvocationResultV2,
    ) -> DriverInvocationReceiptV2:
        receipt = super().record(request, result)
        count = self._seen.get(request.request_digest, 0) + 1
        self._seen[request.request_digest] = count
        if count == 2:
            return replace(
                receipt,
                provenance="tests:changed-retry",
                receipt_digest="",
            )
        return receipt


class _MissingGetStore(InMemoryDriverInvocationStoreV2):
    def get(
        self,
        scope_ref: str,
        driver_id: str,
        idempotency_key: str,
    ) -> DriverInvocationReceiptV2 | None:
        return None


class _SameReceiptStore(InMemoryDriverInvocationStoreV2):
    def __init__(self) -> None:
        super().__init__()
        self._first: DriverInvocationReceiptV2 | None = None

    def record(
        self,
        request: DriverInvocationRequestV2,
        result: DriverInvocationResultV2,
    ) -> DriverInvocationReceiptV2:
        receipt = super().record(request, result)
        if self._first is None:
            self._first = receipt
        return self._first


class _StoreFactoryAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def __init__(self, factory: Callable[[], DriverInvocationStoreV2]) -> None:
        self._factory = factory

    def create_store_v2(self) -> DriverInvocationStoreV2:
        return self._factory()


class _LateInvalidStoreAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def __init__(self) -> None:
        self._create_count = 0

    def create_store_v2(self) -> DriverInvocationStoreV2:
        self._create_count += 1
        if 2 <= self._create_count <= 8:
            return cast(DriverInvocationStoreV2, object())
        return InMemoryDriverInvocationStoreV2()


class _PreloadedConcurrencyStore(InMemoryDriverInvocationStoreV2):
    def __init__(self) -> None:
        super().__init__()
        self._first_get = True

    def get(
        self,
        scope_ref: str,
        driver_id: str,
        idempotency_key: str,
    ) -> DriverInvocationReceiptV2 | None:
        if self._first_get:
            self._first_get = False
            return cast(DriverInvocationReceiptV2, object())
        return super().get(scope_ref, driver_id, idempotency_key)


class _DivergentConcurrencyStore(InMemoryDriverInvocationStoreV2):
    def __init__(self) -> None:
        super().__init__()
        self._counter = 0
        self._counter_lock = Lock()

    def record(
        self,
        request: DriverInvocationRequestV2,
        result: DriverInvocationResultV2,
    ) -> DriverInvocationReceiptV2:
        receipt = super().record(request, result)
        with self._counter_lock:
            self._counter += 1
            counter = self._counter
        if counter % 2:
            return receipt
        return replace(
            receipt,
            provenance="tests:divergent-concurrent-retry",
            receipt_digest="",
        )


class _MissingConcurrencyGetStore(InMemoryDriverInvocationStoreV2):
    def get(
        self,
        scope_ref: str,
        driver_id: str,
        idempotency_key: str,
    ) -> DriverInvocationReceiptV2 | None:
        return None


class _EighthStoreAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def __init__(self, factory: Callable[[], DriverInvocationStoreV2]) -> None:
        self._factory = factory
        self._create_count = 0

    def create_store_v2(self) -> DriverInvocationStoreV2:
        self._create_count += 1
        if self._create_count == 8:
            return self._factory()
        return InMemoryDriverInvocationStoreV2()


class _FixedCheckpointStore(InMemoryDriverInvocationStoreV2):
    checkpoint_wire = b'{"receipts":[1],"version":"test"}'

    def checkpoint(self) -> bytes:
        return self.checkpoint_wire


class _FixedCheckpointAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def __init__(self, wire: bytes) -> None:
        self._wire = wire

    def _store(self) -> _FixedCheckpointStore:
        store = _FixedCheckpointStore()
        store.checkpoint_wire = self._wire
        return store

    def create_store_v2(self) -> DriverInvocationStoreV2:
        return self._store()

    def restart_store_v2(self, checkpoint: bytes) -> DriverInvocationStoreV2:
        return self._store()


class _NoRetireStore(InMemoryDriverInvocationStoreV2):
    def retire(self, scope_ref: str) -> int:
        return 0


class _NoRetireAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def create_store_v2(self) -> DriverInvocationStoreV2:
        return _NoRetireStore()

    def restart_store_v2(self, checkpoint: bytes) -> DriverInvocationStoreV2:
        return _NoRetireStore.from_checkpoint(checkpoint)


class _InvalidSecondRestartAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def __init__(self) -> None:
        self._restart_count = 0

    def restart_store_v2(self, checkpoint: bytes) -> DriverInvocationStoreV2:
        self._restart_count += 1
        if self._restart_count == 2:
            return cast(DriverInvocationStoreV2, object())
        return super().restart_store_v2(checkpoint)


class _IgnoringRestartAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def restart_store_v2(self, checkpoint: bytes) -> DriverInvocationStoreV2:
        return InMemoryDriverInvocationStoreV2()


class _WrongRestartReceiptStore(InMemoryDriverInvocationStoreV2):
    def record(
        self,
        request: DriverInvocationRequestV2,
        result: DriverInvocationResultV2,
    ) -> DriverInvocationReceiptV2:
        receipt = super().record(request, result)
        return replace(
            receipt,
            request_digest="sha256:" + "0" * 64,
            receipt_digest="",
        )


class _WrongRestartReceiptAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def restart_store_v2(self, checkpoint: bytes) -> DriverInvocationStoreV2:
        return _WrongRestartReceiptStore.from_checkpoint(checkpoint)


class _WrongScopeStore(InMemoryDriverInvocationStoreV2):
    def record(
        self,
        request: DriverInvocationRequestV2,
        result: DriverInvocationResultV2,
    ) -> DriverInvocationReceiptV2:
        receipt = super().record(request, result)
        if request.idempotency_key == "retry:shared-across-scopes":
            return replace(
                receipt,
                scope_ref="sha256:" + "0" * 64,
                receipt_digest="",
            )
        return receipt


class _WrongScopeAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def create_store_v2(self) -> DriverInvocationStoreV2:
        return _WrongScopeStore()


class _InvalidFailureStoreAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def create_failure_injected_store_v2(
        self,
        stage: str,
    ) -> DriverInvocationStoreV2:
        return cast(DriverInvocationStoreV2, object())


@pytest.mark.parametrize(
    ("adapter", "detail"),
    [
        (
            cast(DriverInvocationStoreConformanceAdapterV2, object()),
            "adapter_protocol",
        ),
        (_InvalidImplementationIdAdapter(), "adapter_implementation_id"),
        (_InvalidVersionAdapter(), "adapter_version"),
        (_NonStoreAdapter(), "store_protocol"),
        (_WrongStoreVersionAdapter(), "store_version"),
        (_RaisingAdapter(), "adapter_exception:OSError"),
        (_BadProvenanceAdapter(), "first_provenance"),
        (_InvalidWireAdapter(), "first_result_wire"),
        (_StoreFactoryAdapter(_ChangingRetryStore), "idempotent_retry"),
        (_StoreFactoryAdapter(_MissingGetStore), "get_binding"),
        (_StoreFactoryAdapter(_SameReceiptStore), "distinct_receipt"),
        (_LateInvalidStoreAdapter(), "cross_binding_store_protocol"),
        (
            _EighthStoreAdapter(_PreloadedConcurrencyStore),
            "concurrent_store_not_fresh",
        ),
        (
            _EighthStoreAdapter(_DivergentConcurrencyStore),
            "concurrent_retry_diverged",
        ),
        (
            _EighthStoreAdapter(_MissingConcurrencyGetStore),
            "concurrent_get_binding",
        ),
        (_FixedCheckpointAdapter(b"{"), "concurrent_active_receipt_count"),
        (
            _FixedCheckpointAdapter(b'{"receipts":[{}]}'),
            "checkpoint_version",
        ),
        (
            _FixedCheckpointAdapter(b'{"receipts":1,"version":"test"}'),
            "concurrent_active_receipt_count",
        ),
        (
            _FixedCheckpointAdapter(b'{"receipts":[1],"version":"test"}'),
            "unicode_checkpoint_receipt_invalid",
        ),
        (_NoRetireAdapter(), "retire_count"),
        (_InvalidSecondRestartAdapter(), "restart_store_protocol"),
        (_IgnoringRestartAdapter(), "concurrent_restart_stability"),
        (_WrongRestartReceiptAdapter(), "concurrent_restart_idempotency"),
        (_WrongScopeAdapter(), "scope_isolation"),
        (_InvalidFailureStoreAdapter(), "before_commit_failure_store_protocol"),
    ],
)
def test_public_tck_reports_deep_adversarial_contract_failures(
    adapter: DriverInvocationStoreConformanceAdapterV2,
    detail: str,
) -> None:
    result = run_driver_invocation_store_conformance_v2(adapter)
    assert not result.ok
    assert detail in result.detail


def test_reference_adapter_rejects_non_integer_operands() -> None:
    adapter = ReferenceDriverInvocationStoreConformanceAdapterV2()
    request = DriverInvocationRequestV2(
        scope_ref="sha256:" + "0" * 64,
        driver_id="driver:test",
        invocation_id="invocation:test",
        operation="conformance.add",
        capability="arithmetic:add",
        idempotency_key="retry:test",
        payload={"left": True, "right": 2},
    )

    result = adapter.invoke_v2(request)

    assert not result.ok
    assert result.payload == {"error": "invalid-operands"}
    assert adapter.conformance_version == DRIVER_INVOCATION_STORE_CONFORMANCE_VERSION_V2
