from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from pheroos.drivers import (
    DriverInvocationLedger,
    DriverInvocationReceipt,
    DriverResult,
    driver_request_digest,
    driver_result_digest,
)
from pheroos.drivers.errors import DriverError
from pheroos.kernel import runtime_scope_ref


def invocation_values(scope_ref: str) -> tuple[str, DriverResult]:
    request_digest = driver_request_digest(
        scope_ref=scope_ref,
        invocation_id="invoke:1",
        driver_id="driver:one",
        operation="driver:invoke",
        capability="evidence:read",
        idempotency_key="retry:1",
        payload={"value": 1},
    )
    result = DriverResult(
        driver_id="driver:one",
        ok=True,
        payload={"value": 2},
        provenance="driver:one",
        scope_ref=scope_ref,
        invocation_id="invoke:1",
        operation="driver:invoke",
        request_digest=request_digest,
    )
    return request_digest, result


def request_values() -> dict[str, Any]:
    return {
        "scope_ref": runtime_scope_ref("tenant-a", "run-1"),
        "invocation_id": "invoke:1",
        "driver_id": "driver:one",
        "operation": "driver:invoke",
        "capability": "evidence:read",
        "idempotency_key": "retry:1",
        "payload": {"value": 1},
    }


def test_invocation_ledger_is_idempotent_conflict_safe_and_scope_isolated() -> None:
    ledger = DriverInvocationLedger()
    scope_a = runtime_scope_ref("tenant-a", "run-1")
    scope_b = runtime_scope_ref("tenant-b", "run-1")
    request_digest, result = invocation_values(scope_a)
    result_digest = driver_result_digest(result)

    first = ledger.record(
        scope_ref=scope_a,
        driver_id="driver:one",
        idempotency_key="retry:1",
        request_digest=request_digest,
        result_digest=result_digest,
    )
    assert (
        ledger.record(
            scope_ref=scope_a,
            driver_id="driver:one",
            idempotency_key="retry:1",
            request_digest=request_digest,
            result_digest=result_digest,
        )
        == first
    )

    with pytest.raises(DriverError, match="conflicting"):
        ledger.record(
            scope_ref=scope_a,
            driver_id="driver:one",
            idempotency_key="retry:1",
            request_digest=request_digest,
            result_digest=driver_result_digest(
                replace(result, payload={"value": "forged"})
            ),
        )

    foreign_request, foreign_result = invocation_values(scope_b)
    ledger.record(
        scope_ref=scope_b,
        driver_id="driver:one",
        idempotency_key="retry:1",
        request_digest=foreign_request,
        result_digest=driver_result_digest(foreign_result),
    )
    assert len(ledger.receipts) == 2
    assert ledger.retire_scope(scope_a) == 1
    assert len(ledger.receipts) == 1


def test_invocation_digest_accepts_the_complete_provider_neutral_value_shape() -> None:
    values = request_values()
    values["payload"] = {
        "none": None,
        "boolean": True,
        "text": "value",
        "number": 1.25,
        "mapping": {"nested": 2},
        "sequence": [1, "two", False],
    }

    first = driver_request_digest(**values)
    values["payload"] = {
        "sequence": (1, "two", False),
        "mapping": {"nested": 2},
        "number": 1.25,
        "text": "value",
        "boolean": True,
        "none": None,
    }

    assert driver_request_digest(**values) == first


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scope_ref", ""),
        ("invocation_id", "   "),
        ("driver_id", None),
        ("operation", "\t"),
        ("capability", ""),
        ("idempotency_key", "\n"),
    ],
)
def test_invocation_digest_rejects_noncanonical_request_identity(
    field: str,
    value: object,
) -> None:
    values = request_values()
    values[field] = value

    with pytest.raises(ValueError, match="identities must be nonblank strings"):
        driver_request_digest(**values)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_invocation_digest_rejects_nonfinite_payload_numbers(value: float) -> None:
    values = request_values()
    values["payload"] = {"invalid": value}

    with pytest.raises(ValueError, match="non-finite"):
        driver_request_digest(**values)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"": "value"}, "keys must be non-empty strings"),
        ({1: "value"}, "keys must be non-empty strings"),
        ({"invalid": b"bytes"}, "unsupported value type: bytes"),
        ({"invalid": object()}, "unsupported value type: object"),
    ],
)
def test_invocation_digest_rejects_noncanonical_payload_values(
    payload: object,
    message: str,
) -> None:
    values = request_values()
    values["payload"] = payload

    with pytest.raises(ValueError, match=message):
        driver_request_digest(**values)


def test_result_digest_requires_a_canonical_driver_result() -> None:
    with pytest.raises(ValueError, match="driver result must be canonical"):
        driver_result_digest(object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", "pheroos-driver-invocation-receipt-v999"),
        ("request_digest", "sha256:forged"),
        ("result_digest", "sha256:forged"),
    ],
)
def test_invocation_receipt_rejects_unknown_version_and_noncanonical_digest(
    field: str,
    value: str,
) -> None:
    kwargs = {
        "scope_ref": runtime_scope_ref("tenant-a", "run-1"),
        "driver_id": "driver:one",
        "idempotency_key": "retry:1",
        "request_digest": "sha256:" + "1" * 64,
        "result_digest": "sha256:" + "2" * 64,
        field: value,
    }

    with pytest.raises(ValueError):
        DriverInvocationReceipt(**kwargs)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scope_ref", ""),
        ("driver_id", None),
        ("idempotency_key", "   "),
    ],
)
def test_invocation_receipt_rejects_noncanonical_identity(
    field: str,
    value: object,
) -> None:
    kwargs: dict[str, Any] = {
        "scope_ref": runtime_scope_ref("tenant-a", "run-1"),
        "driver_id": "driver:one",
        "idempotency_key": "retry:1",
        "request_digest": "sha256:" + "1" * 64,
        "result_digest": "sha256:" + "2" * 64,
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match="identities must be nonblank"):
        DriverInvocationReceipt(**kwargs)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scope_ref", ""),
        ("driver_id", None),
        ("idempotency_key", "   "),
        ("request_digest", ""),
        ("result_digest", 7),
    ],
)
def test_invocation_ledger_rejects_noncanonical_record_identity(
    field: str,
    value: object,
) -> None:
    ledger = DriverInvocationLedger()
    values: dict[str, Any] = {
        "scope_ref": runtime_scope_ref("tenant-a", "run-1"),
        "driver_id": "driver:one",
        "idempotency_key": "retry:1",
        "request_digest": "sha256:" + "1" * 64,
        "result_digest": "sha256:" + "2" * 64,
    }
    values[field] = value

    with pytest.raises(DriverError, match="identities must be nonblank"):
        ledger.record(**values)


@pytest.mark.parametrize("field", ["request_digest", "result_digest"])
def test_invocation_ledger_rejects_noncanonical_record_digest(field: str) -> None:
    ledger = DriverInvocationLedger()
    values = {
        "scope_ref": runtime_scope_ref("tenant-a", "run-1"),
        "driver_id": "driver:one",
        "idempotency_key": "retry:1",
        "request_digest": "sha256:" + "1" * 64,
        "result_digest": "sha256:" + "2" * 64,
    }
    values[field] = "sha256:forged"

    with pytest.raises(DriverError, match="digests must be canonical sha256"):
        ledger.record(**values)


def test_invocation_ledger_get_and_empty_retirement_are_scope_safe() -> None:
    ledger = DriverInvocationLedger()
    scope_ref = runtime_scope_ref("tenant-a", "run-1")
    request_digest, result = invocation_values(scope_ref)
    receipt = ledger.record(
        scope_ref=scope_ref,
        driver_id="driver:one",
        idempotency_key="retry:1",
        request_digest=request_digest,
        result_digest=driver_result_digest(result),
    )

    assert (
        ledger.get(
            scope_ref=scope_ref,
            driver_id="driver:one",
            idempotency_key="retry:1",
        )
        == receipt
    )
    assert (
        ledger.get(
            scope_ref=scope_ref,
            driver_id="driver:one",
            idempotency_key="retry:missing",
        )
        is None
    )
    assert ledger.retire_scope(runtime_scope_ref("tenant-b", "run-1")) == 0


@pytest.mark.parametrize("scope_ref", ["", "   ", None])
def test_invocation_ledger_rejects_invalid_retirement_scope(
    scope_ref: object,
) -> None:
    with pytest.raises(DriverError, match="scope_ref is required"):
        DriverInvocationLedger().retire_scope(scope_ref)  # type: ignore[arg-type]
