from __future__ import annotations

from hashlib import sha256
import json
from threading import RLock
import unicodedata

import pytest

from pheroos._scope import runtime_scope_ref
from pheroos.conformance.checks.driver_invocation_v2_contract import (
    DRIVER_INVOCATION_STORE_FAILURE_STAGES_V2,
    DRIVER_INVOCATION_STORE_CONFORMANCE_VERSION_V2,
    DriverInvocationStoreConformanceAdapterV2,
    ReferenceDriverInvocationStoreConformanceAdapterV2,
    check,
    run_driver_invocation_store_conformance_v2,
)
from pheroos.drivers import (
    DRIVER_INVOCATION_STORE_VERSION_V2,
    DriverInvocationReceiptV2,
    DriverInvocationRequestV2,
    DriverInvocationResultV2,
    DriverInvocationStoreErrorV2,
    DriverInvocationStoreV2,
    InMemoryDriverInvocationStoreV2,
)


class IndependentStoreV2:
    store_version = DRIVER_INVOCATION_STORE_VERSION_V2

    def __init__(
        self,
        checkpoint: bytes | None = None,
        *,
        fail_stage: str | None = None,
    ) -> None:
        self._values: dict[tuple[str, str, str], DriverInvocationReceiptV2] = {}
        self._retired: set[str] = set()
        self._fail_stage = fail_stage
        self._lock = RLock()
        if checkpoint is not None:
            self._restore(checkpoint)

    @staticmethod
    def _key(
        value: DriverInvocationReceiptV2,
    ) -> tuple[str, str, str]:
        return value.scope_ref, value.driver_id, value.idempotency_key

    @staticmethod
    def _identity(value: object) -> str:
        if (
            type(value) is not str
            or not value
            or value != value.strip()
            or "\x00" in value
            or unicodedata.normalize("NFC", value) != value
            or any(0xD800 <= ord(character) <= 0xDFFF for character in value)
        ):
            raise DriverInvocationStoreErrorV2("noncanonical store identity")
        return value

    def record(
        self,
        request: DriverInvocationRequestV2,
        result: DriverInvocationResultV2,
    ) -> DriverInvocationReceiptV2:
        request_binding = (
            request.scope_ref,
            request.driver_id,
            request.invocation_id,
            request.operation,
            request.capability,
            request.idempotency_key,
            request.request_digest,
        )
        result_binding = (
            result.scope_ref,
            result.driver_id,
            result.invocation_id,
            result.operation,
            result.capability,
            result.idempotency_key,
            result.request_digest,
        )
        if request_binding != result_binding:
            raise DriverInvocationStoreErrorV2("binding mismatch")
        receipt = DriverInvocationReceiptV2.for_result(result)
        key = self._key(receipt)
        with self._lock:
            if request.scope_ref in self._retired:
                raise DriverInvocationStoreErrorV2("scope retired")
            existing = self._values.get(key)
            if existing is not None:
                if existing != receipt:
                    raise DriverInvocationStoreErrorV2("conflicting retry")
                return existing
            if self._fail_stage == "before_commit":
                raise OSError("independent injected failure")
            self._values[key] = receipt
            return receipt

    def get(
        self,
        scope_ref: str,
        driver_id: str,
        idempotency_key: str,
    ) -> DriverInvocationReceiptV2 | None:
        scope_ref = self._identity(scope_ref)
        driver_id = self._identity(driver_id)
        idempotency_key = self._identity(idempotency_key)
        with self._lock:
            if scope_ref in self._retired:
                return None
            return self._values.get((scope_ref, driver_id, idempotency_key))

    def retire(self, scope_ref: str) -> int:
        scope_ref = self._identity(scope_ref)
        with self._lock:
            if scope_ref in self._retired:
                return 0
            keys = tuple(key for key in self._values if key[0] == scope_ref)
            if self._fail_stage == "before_retire":
                raise OSError("independent injected retirement failure")
            for key in keys:
                del self._values[key]
            self._retired.add(scope_ref)
            return len(keys)

    def _unsigned(self) -> dict[str, object]:
        return {
            "version": "independent-driver-invocation-checkpoint-v2",
            "store_version": self.store_version,
            "receipts": [
                value.to_dict()
                for value in sorted(self._values.values(), key=self._key)
            ],
            "retired_scopes": sorted(self._retired),
        }

    @staticmethod
    def _encode(payload: dict[str, object]) -> bytes:
        return json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")

    def checkpoint(self) -> bytes:
        with self._lock:
            unsigned = self._unsigned()
        digest = "sha256:" + sha256(self._encode(unsigned)).hexdigest()
        return self._encode({**unsigned, "checkpoint_digest": digest})

    def _restore(self, checkpoint: bytes) -> None:
        payload = json.loads(checkpoint)
        fields = {
            "version",
            "store_version",
            "receipts",
            "retired_scopes",
            "checkpoint_digest",
        }
        if type(payload) is not dict or set(payload) != fields:
            raise DriverInvocationStoreErrorV2("independent checkpoint fields")
        if self._encode(payload) != checkpoint:
            raise DriverInvocationStoreErrorV2("independent checkpoint canonicality")
        digest = payload.pop("checkpoint_digest")
        expected = "sha256:" + sha256(self._encode(payload)).hexdigest()
        if digest != expected:
            raise DriverInvocationStoreErrorV2("independent checkpoint digest")
        if payload["version"] != "independent-driver-invocation-checkpoint-v2":
            raise DriverInvocationStoreErrorV2("independent checkpoint version")
        if payload["store_version"] != self.store_version:
            raise DriverInvocationStoreErrorV2("independent store version")
        receipts = tuple(
            DriverInvocationReceiptV2.from_dict(item) for item in payload["receipts"]
        )
        self._values = {self._key(value): value for value in receipts}
        self._retired = set(payload["retired_scopes"])


class IndependentAdapterV2:
    implementation_id = "tests.independent-stdlib-driver-store-v2"
    conformance_version = DRIVER_INVOCATION_STORE_CONFORMANCE_VERSION_V2

    def create_store_v2(self) -> DriverInvocationStoreV2:
        return IndependentStoreV2()

    def restart_store_v2(
        self,
        checkpoint: bytes,
    ) -> DriverInvocationStoreV2:
        return IndependentStoreV2(checkpoint)

    def create_failure_injected_store_v2(
        self,
        stage: str,
    ) -> DriverInvocationStoreV2:
        if stage not in DRIVER_INVOCATION_STORE_FAILURE_STAGES_V2:
            raise ValueError("unsupported failure stage")
        return IndependentStoreV2(fail_stage=stage)

    def invoke_v2(
        self,
        request: DriverInvocationRequestV2,
    ) -> DriverInvocationResultV2:
        left = request.payload["left"]
        right = request.payload["right"]
        assert type(left) is int and type(right) is int
        return DriverInvocationResultV2.for_request(
            request,
            ok=True,
            payload={"sum": left + right},
            provenance="tests:independent-calculator-v2",
        )


@pytest.mark.parametrize(
    "adapter",
    [ReferenceDriverInvocationStoreConformanceAdapterV2(), IndependentAdapterV2()],
)
def test_reference_and_independent_adapters_pass_full_matrix(
    adapter: DriverInvocationStoreConformanceAdapterV2,
) -> None:
    assert isinstance(adapter, DriverInvocationStoreConformanceAdapterV2)
    result = run_driver_invocation_store_conformance_v2(adapter)
    assert result.ok, result.detail


def test_reference_check_passes() -> None:
    assert check().ok


class EchoAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def invoke_v2(
        self,
        request: DriverInvocationRequestV2,
    ) -> DriverInvocationResultV2:
        return DriverInvocationResultV2.for_request(
            request, ok=True, payload=dict(request.payload), provenance="tests:echo"
        )


class ConstantAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def invoke_v2(
        self,
        request: DriverInvocationRequestV2,
    ) -> DriverInvocationResultV2:
        return DriverInvocationResultV2.for_request(
            request, ok=True, payload={"sum": 5}, provenance="tests:constant"
        )


class MalformedAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def invoke_v2(self, request: DriverInvocationRequestV2) -> DriverInvocationResultV2:
        return object()  # type: ignore[return-value]


class CrossBindingAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def invoke_v2(
        self,
        request: DriverInvocationRequestV2,
    ) -> DriverInvocationResultV2:
        left = request.payload["left"]
        right = request.payload["right"]
        assert type(left) is int and type(right) is int
        return DriverInvocationResultV2(
            scope_ref=request.scope_ref,
            driver_id=request.driver_id,
            invocation_id=request.invocation_id,
            operation=request.operation,
            capability="arithmetic:forged",
            idempotency_key=request.idempotency_key,
            request_digest=request.request_digest,
            ok=True,
            payload={"sum": left + right},
            provenance="tests:cross-binding",
        )


class ConflictAcceptingStore(InMemoryDriverInvocationStoreV2):
    def record(
        self,
        request: DriverInvocationRequestV2,
        result: DriverInvocationResultV2,
    ) -> DriverInvocationReceiptV2:
        try:
            return super().record(request, result)
        except DriverInvocationStoreErrorV2:
            return DriverInvocationReceiptV2.for_result(result)


class ConflictAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def create_store_v2(self) -> DriverInvocationStoreV2:
        return ConflictAcceptingStore()


class DigestOnlyBindingStore(IndependentStoreV2):
    def record(
        self,
        request: DriverInvocationRequestV2,
        result: DriverInvocationResultV2,
    ) -> DriverInvocationReceiptV2:
        if result.request_digest != request.request_digest:
            raise DriverInvocationStoreErrorV2("digest mismatch")
        receipt = DriverInvocationReceiptV2.for_result(result)
        key = self._key(receipt)
        with self._lock:
            existing = self._values.get(key)
            if existing is not None:
                return existing
            self._values[key] = receipt
            return receipt


class DigestOnlyBindingAdapter(IndependentAdapterV2):
    def create_store_v2(self) -> DriverInvocationStoreV2:
        return DigestOnlyBindingStore()


class FailureIgnoringAdapter(ReferenceDriverInvocationStoreConformanceAdapterV2):
    def create_failure_injected_store_v2(
        self,
        stage: str,
    ) -> DriverInvocationStoreV2:
        return InMemoryDriverInvocationStoreV2()


@pytest.mark.parametrize(
    ("adapter", "detail"),
    [
        (EchoAdapter(), "result_semantics"),
        (ConstantAdapter(), "second_result_semantics"),
        (MalformedAdapter(), "result_type"),
        (CrossBindingAdapter(), "request_binding"),
        (ConflictAdapter(), "conflicting_request_accepted"),
        (DigestOnlyBindingAdapter(), "cross_binding_accepted"),
        (FailureIgnoringAdapter(), "before_commit_failure_not_observed"),
    ],
)
def test_tck_detects_nonconforming_adapters(
    adapter: DriverInvocationStoreConformanceAdapterV2,
    detail: str,
) -> None:
    result = run_driver_invocation_store_conformance_v2(adapter)
    assert not result.ok
    assert detail in result.detail


def test_adapter_request_has_no_expected_or_oracle_field() -> None:
    request = DriverInvocationRequestV2(
        scope_ref=runtime_scope_ref("test", "run"),
        driver_id="driver:test",
        invocation_id="invocation:test",
        operation="conformance.add",
        capability="arithmetic:add",
        idempotency_key="retry:test",
        payload={"left": 1, "right": 2},
    )
    assert "expected" not in request.to_dict()
    assert "oracle" not in request.to_dict()
