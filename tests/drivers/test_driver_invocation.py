from __future__ import annotations

from dataclasses import replace

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
    assert ledger.record(
        scope_ref=scope_a,
        driver_id="driver:one",
        idempotency_key="retry:1",
        request_digest=request_digest,
        result_digest=result_digest,
    ) == first

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
