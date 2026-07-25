"""Provider-free conformance TCK for Driver Invocation ABI v2 stores."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
import json
from typing import Protocol, runtime_checkable

from pheroos._scope import runtime_scope_ref
from pheroos.conformance.report import CheckResult
from pheroos.drivers import (
    DriverInvocationRequestV2,
    DriverInvocationResultV2,
    DriverInvocationStoreErrorV2,
    DriverInvocationStoreV2,
    InMemoryDriverInvocationStoreV2,
    validate_driver_invocation_binding_v2,
)


DRIVER_INVOCATION_STORE_CONFORMANCE_VERSION_V2 = (
    "pheroos-driver-invocation-store-conformance-v2"
)
DRIVER_INVOCATION_STORE_FAILURE_STAGES_V2 = (
    "before_commit",
    "before_retire",
)
_CHECK_NAME = "driver_invocation_v2_contract"
_WORKERS = 32


@runtime_checkable
class DriverInvocationStoreConformanceAdapterV2(Protocol):
    """Public black-box adapter for an Invocation Store v2 implementation."""

    implementation_id: str
    conformance_version: str

    def create_store_v2(self) -> DriverInvocationStoreV2: ...

    def restart_store_v2(
        self,
        checkpoint: bytes,
    ) -> DriverInvocationStoreV2: ...

    def create_failure_injected_store_v2(
        self,
        stage: str,
    ) -> DriverInvocationStoreV2: ...

    def invoke_v2(
        self,
        request: DriverInvocationRequestV2,
    ) -> DriverInvocationResultV2: ...


class ReferenceDriverInvocationStoreConformanceAdapterV2:
    """Reference adapter using only the public provider-neutral Driver ABI."""

    __slots__ = ()

    implementation_id = "pheroos-in-memory-driver-invocation-store-v2"
    conformance_version = DRIVER_INVOCATION_STORE_CONFORMANCE_VERSION_V2

    def create_store_v2(self) -> DriverInvocationStoreV2:
        return InMemoryDriverInvocationStoreV2()

    def restart_store_v2(
        self,
        checkpoint: bytes,
    ) -> DriverInvocationStoreV2:
        return InMemoryDriverInvocationStoreV2.from_checkpoint(checkpoint)

    def create_failure_injected_store_v2(
        self,
        stage: str,
    ) -> DriverInvocationStoreV2:
        if stage not in DRIVER_INVOCATION_STORE_FAILURE_STAGES_V2:
            raise ValueError("unsupported failure stage")

        def fail(observed: str) -> None:
            if observed == stage:
                raise OSError(f"injected-{stage}")

        return InMemoryDriverInvocationStoreV2(failure_hook=fail)

    def invoke_v2(
        self,
        request: DriverInvocationRequestV2,
    ) -> DriverInvocationResultV2:
        payload = request.payload
        left = payload.get("left")
        right = payload.get("right")
        if type(left) is not int or type(right) is not int:
            return DriverInvocationResultV2.for_request(
                request,
                ok=False,
                payload={"error": "invalid-operands"},
                provenance="driver:conformance/reference",
            )
        return DriverInvocationResultV2.for_request(
            request,
            ok=True,
            payload={"sum": left + right},
            provenance="driver:conformance/reference",
        )


def _request(
    *,
    scope_ref: str,
    invocation_id: str,
    idempotency_key: str,
    left: int,
    right: int,
) -> DriverInvocationRequestV2:
    return DriverInvocationRequestV2(
        scope_ref=scope_ref,
        driver_id="driver:conformance-calculator",
        invocation_id=invocation_id,
        operation="conformance.add",
        capability="arithmetic:add",
        idempotency_key=idempotency_key,
        payload={"left": left, "right": right},
    )


def _valid_adapter(
    adapter: DriverInvocationStoreConformanceAdapterV2,
) -> str | None:
    if not isinstance(adapter, DriverInvocationStoreConformanceAdapterV2):
        return "adapter_protocol"
    if (
        not isinstance(adapter.implementation_id, str)
        or not adapter.implementation_id
        or adapter.implementation_id != adapter.implementation_id.strip()
    ):
        return "adapter_implementation_id"
    if adapter.conformance_version != DRIVER_INVOCATION_STORE_CONFORMANCE_VERSION_V2:
        return "adapter_version"
    return None


def _expect_sum(
    adapter: DriverInvocationStoreConformanceAdapterV2,
    request: DriverInvocationRequestV2,
    expected: int,
    problems: list[str],
    label: str,
) -> DriverInvocationResultV2 | None:
    result = adapter.invoke_v2(request)
    if type(result) is not DriverInvocationResultV2:
        problems.append(f"{label}_result_type")
        return None
    if not result.ok or result.payload != {"sum": expected}:
        problems.append(f"{label}_result_semantics")
    if not result.provenance or result.provenance == request.driver_id:
        problems.append(f"{label}_provenance")
    try:
        DriverInvocationResultV2.from_wire(result.to_wire())
    except (TypeError, ValueError):
        problems.append(f"{label}_result_wire")
    try:
        validate_driver_invocation_binding_v2(request, result)
    except ValueError:
        problems.append(f"{label}_request_binding")
    return result


def _exercise_normal_path(
    adapter: DriverInvocationStoreConformanceAdapterV2,
    store: DriverInvocationStoreV2,
    problems: list[str],
) -> tuple[DriverInvocationRequestV2, DriverInvocationResultV2] | None:
    first = _request(
        scope_ref=runtime_scope_ref("tenant-a", "run-1"),
        invocation_id="invocation:first",
        idempotency_key="retry:first",
        left=2,
        right=3,
    )
    second = _request(
        scope_ref=runtime_scope_ref("tenant-a", "run-1"),
        invocation_id="invocation:second",
        idempotency_key="retry:second",
        left=7,
        right=11,
    )
    first_result = _expect_sum(adapter, first, 5, problems, "first")
    second_result = _expect_sum(adapter, second, 18, problems, "second")
    if first_result is None or second_result is None:
        return None
    first_receipt = store.record(first, first_result)
    if store.record(first, first_result) != first_receipt:
        problems.append("idempotent_retry")
    if (
        store.get(first.scope_ref, first.driver_id, first.idempotency_key)
        != first_receipt
    ):
        problems.append("get_binding")
    if (
        store.record(second, second_result).receipt_digest
        == first_receipt.receipt_digest
    ):
        problems.append("distinct_receipt")
    return first, first_result


def _exercise_conflict(
    adapter: DriverInvocationStoreConformanceAdapterV2,
    store: DriverInvocationStoreV2,
    first: DriverInvocationRequestV2,
    problems: list[str],
) -> None:
    conflict = _request(
        scope_ref=first.scope_ref,
        invocation_id="invocation:conflict",
        idempotency_key=first.idempotency_key,
        left=101,
        right=202,
    )
    conflict_result = adapter.invoke_v2(conflict)
    try:
        store.record(conflict, conflict_result)
    except DriverInvocationStoreErrorV2:
        pass
    else:
        problems.append("conflicting_request_accepted")


def _exercise_store_cross_binding(
    adapter: DriverInvocationStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    request = _request(
        scope_ref=runtime_scope_ref("tenant-binding", "run-1"),
        invocation_id="invocation:binding",
        idempotency_key="retry:binding",
        left=3,
        right=4,
    )
    result = adapter.invoke_v2(request)
    mutations: tuple[tuple[str, str], ...] = (
        ("scope_ref", runtime_scope_ref("tenant-binding", "run-2")),
        ("driver_id", "driver:forged"),
        ("invocation_id", "invocation:forged"),
        ("operation", "conformance.forged"),
        ("capability", "arithmetic:forged"),
        ("idempotency_key", "retry:forged"),
    )
    for field, replacement in mutations:
        store = adapter.create_store_v2()
        if not isinstance(store, DriverInvocationStoreV2):
            problems.append(f"cross_binding_store_protocol:{field}")
            continue
        before = store.checkpoint()
        # ``DriverInvocationResultV2`` freezes mappings after construction.  Give
        # ``replace`` a thawed payload so the adversarial result is a valid,
        # independently re-digested wire value rather than a mappingproxy that
        # fails before the store's request/result binding check is exercised.
        forged = _replace_result_binding(result, field, replacement)
        try:
            store.record(request, forged)
        except Exception:
            pass
        else:
            problems.append(f"cross_binding_accepted:{field}")
        if store.checkpoint() != before:
            problems.append(f"cross_binding_mutated_store:{field}")
        if (
            store.get(
                request.scope_ref,
                request.driver_id,
                request.idempotency_key,
            )
            is not None
        ):
            problems.append(f"cross_binding_visible:{field}")


def _replace_result_binding(
    result: DriverInvocationResultV2,
    field: str,
    replacement: str,
) -> DriverInvocationResultV2:
    """Build one typed adversarial binding mutation for the Store TCK."""

    if field == "scope_ref":
        return replace(
            result,
            scope_ref=replacement,
            payload=dict(result.payload),
            result_digest="",
        )
    if field == "driver_id":
        return replace(
            result,
            driver_id=replacement,
            payload=dict(result.payload),
            result_digest="",
        )
    if field == "invocation_id":
        return replace(
            result,
            invocation_id=replacement,
            payload=dict(result.payload),
            result_digest="",
        )
    if field == "operation":
        return replace(
            result,
            operation=replacement,
            payload=dict(result.payload),
            result_digest="",
        )
    if field == "capability":
        return replace(
            result,
            capability=replacement,
            payload=dict(result.payload),
            result_digest="",
        )
    if field == "idempotency_key":
        return replace(
            result,
            idempotency_key=replacement,
            payload=dict(result.payload),
            result_digest="",
        )
    raise AssertionError(f"unregistered result binding field: {field}")


def _exercise_concurrency(
    adapter: DriverInvocationStoreConformanceAdapterV2,
    request: DriverInvocationRequestV2,
    result: DriverInvocationResultV2,
    problems: list[str],
) -> None:
    store = adapter.create_store_v2()
    if not isinstance(store, DriverInvocationStoreV2):
        problems.append("concurrent_store_protocol")
        return
    if (
        store.get(request.scope_ref, request.driver_id, request.idempotency_key)
        is not None
    ):
        problems.append("concurrent_store_not_fresh")
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        receipts = tuple(
            pool.map(lambda _: store.record(request, result), range(_WORKERS))
        )
    if len({item.receipt_digest for item in receipts}) != 1:
        problems.append("concurrent_retry_diverged")
        return
    receipt = receipts[0]
    if (
        store.get(request.scope_ref, request.driver_id, request.idempotency_key)
        != receipt
    ):
        problems.append("concurrent_get_binding")
    checkpoint = store.checkpoint()
    if _checkpoint_receipt_count(checkpoint) != 1:
        problems.append("concurrent_active_receipt_count")
    restarted = adapter.restart_store_v2(checkpoint)
    if restarted.checkpoint() != checkpoint:
        problems.append("concurrent_restart_stability")
    elif restarted.record(request, result) != receipt:
        problems.append("concurrent_restart_idempotency")


def _checkpoint_receipt_count(checkpoint: bytes) -> int | None:
    try:
        parsed = json.loads(checkpoint)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict) or type(parsed.get("receipts")) is not list:
        return None
    return len(parsed["receipts"])


def _exercise_restart_and_retire(
    adapter: DriverInvocationStoreConformanceAdapterV2,
    store: DriverInvocationStoreV2,
    first: DriverInvocationRequestV2,
    first_result: DriverInvocationResultV2,
    problems: list[str],
) -> None:
    before = store.checkpoint()
    if not _checkpoint_has_version(before):
        problems.append("checkpoint_version")
        return
    restarted = adapter.restart_store_v2(before)
    if not isinstance(restarted, DriverInvocationStoreV2):
        problems.append("restart_store_protocol")
        return
    if restarted.record(first, first_result).request_digest != first.request_digest:
        problems.append("restart_idempotency")
    if restarted.retire(first.scope_ref) < 1:
        problems.append("retire_count")
    retired_checkpoint = restarted.checkpoint()
    retired = adapter.restart_store_v2(retired_checkpoint)
    if retired.checkpoint() != retired_checkpoint:
        problems.append("restart_checkpoint_stability")
    if retired.get(first.scope_ref, first.driver_id, first.idempotency_key) is not None:
        problems.append("retired_receipt_visible")
    try:
        retired.record(first, first_result)
    except DriverInvocationStoreErrorV2:
        pass
    else:
        problems.append("retired_scope_replayed")
    _exercise_checkpoint_tamper(adapter, retired_checkpoint, problems)


def _checkpoint_has_version(checkpoint: bytes) -> bool:
    try:
        parsed = json.loads(checkpoint)
    except (TypeError, ValueError):
        return False
    return isinstance(parsed, dict) and isinstance(parsed.get("version"), str)


def _exercise_checkpoint_tamper(
    adapter: DriverInvocationStoreConformanceAdapterV2,
    checkpoint: bytes,
    problems: list[str],
) -> None:
    mutated = bytearray(checkpoint)
    mutated[-2] = ord("0") if mutated[-2] != ord("0") else ord("1")
    try:
        adapter.restart_store_v2(bytes(mutated))
    except Exception:
        pass
    else:
        problems.append("mutated_checkpoint_accepted")


def _exercise_scope_isolation(
    adapter: DriverInvocationStoreConformanceAdapterV2,
    store: DriverInvocationStoreV2,
    problems: list[str],
) -> None:
    scopes = (
        runtime_scope_ref("tenant-a", "run-2"),
        runtime_scope_ref("tenant-b", "run-1"),
    )
    for index, scope in enumerate(scopes):
        item = _request(
            scope_ref=scope,
            invocation_id=f"invocation:scope-{index}",
            idempotency_key="retry:shared-across-scopes",
            left=index + 1,
            right=10,
        )
        outcome = adapter.invoke_v2(item)
        if store.record(item, outcome).scope_ref != scope:
            problems.append("scope_isolation")


def _exercise_forged_scope(problems: list[str]) -> None:
    try:
        _request(
            scope_ref="tenant-a/run-1",
            invocation_id="invocation:forged-scope",
            idempotency_key="retry:forged-scope",
            left=1,
            right=2,
        )
    except ValueError:
        pass
    else:
        problems.append("forged_scope_accepted")


def _canonical_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return "sha256:" + sha256(encoded).hexdigest()


def _exercise_unicode_scalar_boundary(
    adapter: DriverInvocationStoreConformanceAdapterV2,
    store: DriverInvocationStoreV2,
    problems: list[str],
) -> None:
    try:
        _request(
            scope_ref=runtime_scope_ref("tenant-a", "run-1"),
            invocation_id="invocation:invalid-\ud800",
            idempotency_key="retry:invalid",
            left=1,
            right=2,
        )
    except ValueError:
        pass
    else:
        problems.append("unicode_surrogate_request_accepted")
    try:
        store.get(
            runtime_scope_ref("tenant-a", "run-1"),
            "driver:invalid-\ud800",
            "retry:invalid",
        )
    except Exception:
        pass
    else:
        problems.append("unicode_surrogate_lookup_accepted")

    checkpoint = json.loads(store.checkpoint())
    receipts = checkpoint.get("receipts")
    if type(receipts) is not list or not receipts:
        problems.append("unicode_checkpoint_fixture_missing")
        return
    receipt = receipts[0]
    if type(receipt) is not dict:
        problems.append("unicode_checkpoint_receipt_invalid")
        return
    receipt["provenance"] = "invalid-\ud800"
    receipt_unsigned = dict(receipt)
    receipt_unsigned.pop("receipt_digest", None)
    receipt["receipt_digest"] = _canonical_digest(receipt_unsigned)
    checkpoint_unsigned = dict(checkpoint)
    checkpoint_unsigned.pop("checkpoint_digest", None)
    checkpoint["checkpoint_digest"] = _canonical_digest(checkpoint_unsigned)
    wire = json.dumps(
        checkpoint,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    try:
        adapter.restart_store_v2(wire)
    except Exception:
        pass
    else:
        problems.append("unicode_surrogate_checkpoint_accepted")


def _failure_fixture(
    adapter: DriverInvocationStoreConformanceAdapterV2,
    stage: str,
    problems: list[str],
) -> (
    tuple[DriverInvocationStoreV2, DriverInvocationRequestV2, DriverInvocationResultV2]
    | None
):
    store = adapter.create_failure_injected_store_v2(stage)
    if not isinstance(store, DriverInvocationStoreV2):
        problems.append(f"{stage}_failure_store_protocol")
        return None
    item = _request(
        scope_ref=runtime_scope_ref("tenant-failure", stage),
        invocation_id=f"invocation:{stage}",
        idempotency_key=f"retry:{stage}",
        left=1,
        right=1,
    )
    outcome = adapter.invoke_v2(item)
    return store, item, outcome


def _exercise_failure_before_commit(
    adapter: DriverInvocationStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    fixture = _failure_fixture(adapter, "before_commit", problems)
    if fixture is None:
        return
    store, item, outcome = fixture
    before = store.checkpoint()
    try:
        store.record(item, outcome)
    except Exception:
        pass
    else:
        problems.append("before_commit_failure_not_observed")
    if store.checkpoint() != before:
        problems.append("before_commit_created_partial_receipt")
    if store.get(item.scope_ref, item.driver_id, item.idempotency_key) is not None:
        problems.append("before_commit_receipt_visible")


def _exercise_failure_before_retire(
    adapter: DriverInvocationStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    fixture = _failure_fixture(adapter, "before_retire", problems)
    if fixture is None:
        return
    store, item, outcome = fixture
    receipt = store.record(item, outcome)
    before = store.checkpoint()
    try:
        store.retire(item.scope_ref)
    except Exception:
        pass
    else:
        problems.append("before_retire_failure_not_observed")
    if store.checkpoint() != before:
        problems.append("before_retire_mutated_store")
    if store.get(item.scope_ref, item.driver_id, item.idempotency_key) != receipt:
        problems.append("before_retire_receipt_lost")
    restarted = adapter.restart_store_v2(store.checkpoint())
    if restarted.get(item.scope_ref, item.driver_id, item.idempotency_key) != receipt:
        problems.append("before_retire_restart_currentness")


def _exercise_closed_failure_stage(
    adapter: DriverInvocationStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    try:
        adapter.create_failure_injected_store_v2("unknown-stage")
    except Exception:
        pass
    else:
        problems.append("unknown_failure_stage_accepted")


def run_driver_invocation_store_conformance_v2(
    adapter: DriverInvocationStoreConformanceAdapterV2,
) -> CheckResult:
    """Run semantics, restart, concurrency, isolation, and failure checks."""

    invalid = _valid_adapter(adapter)
    if invalid is not None:
        return CheckResult(_CHECK_NAME, False, invalid)
    problems: list[str] = []
    try:
        store = adapter.create_store_v2()
        if not isinstance(store, DriverInvocationStoreV2):
            return CheckResult(_CHECK_NAME, False, "store_protocol")
        if store.store_version != "pheroos-driver-invocation-store-v2":
            problems.append("store_version")
        path = _exercise_normal_path(adapter, store, problems)
        if path is not None:
            first, first_result = path
            _exercise_conflict(adapter, store, first, problems)
            _exercise_store_cross_binding(adapter, problems)
            _exercise_concurrency(adapter, first, first_result, problems)
            _exercise_scope_isolation(adapter, store, problems)
            _exercise_restart_and_retire(adapter, store, first, first_result, problems)
        _exercise_forged_scope(problems)
        _exercise_unicode_scalar_boundary(adapter, store, problems)
        _exercise_failure_before_commit(adapter, problems)
        _exercise_failure_before_retire(adapter, problems)
        _exercise_closed_failure_stage(adapter, problems)
    except Exception as exc:  # total-function boundary for third-party adapters
        problems.append(f"adapter_exception:{type(exc).__name__}:{exc}")
    return CheckResult(_CHECK_NAME, not problems, ", ".join(problems))


def check() -> CheckResult:
    return run_driver_invocation_store_conformance_v2(
        ReferenceDriverInvocationStoreConformanceAdapterV2()
    )


DriverInvocationStoreConformanceAdapterV2.__module__ = "pheroos.conformance"
ReferenceDriverInvocationStoreConformanceAdapterV2.__module__ = "pheroos.conformance"
run_driver_invocation_store_conformance_v2.__module__ = "pheroos.conformance"


__all__ = [
    "DRIVER_INVOCATION_STORE_FAILURE_STAGES_V2",
    "DRIVER_INVOCATION_STORE_CONFORMANCE_VERSION_V2",
    "DriverInvocationStoreConformanceAdapterV2",
    "ReferenceDriverInvocationStoreConformanceAdapterV2",
    "check",
    "run_driver_invocation_store_conformance_v2",
]
