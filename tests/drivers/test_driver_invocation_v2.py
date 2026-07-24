from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
import json
from math import nan
from pickle import dumps, loads
from types import MappingProxyType
from typing import Any, cast

import pytest

from pheroos._scope import runtime_scope_ref
from pheroos.drivers import (
    DRIVER_INVOCATION_CHECKPOINT_VERSION_V2,
    DriverInvocationReceiptV2,
    DriverInvocationReplyV2,
    DriverInvocationRequestV2,
    DriverInvocationResultV2,
    DriverInvocationStoreErrorV2,
    DriverInvocationStoreV2,
    DriverInvocationWireErrorV2,
    InMemoryDriverInvocationStoreV2,
    validate_driver_invocation_binding_v2,
)


def request(
    *,
    scope: str = runtime_scope_ref("tenant-a", "run-1"),
    invocation: str = "invocation:1",
    key: str = "retry:1",
    value: int = 2,
) -> DriverInvocationRequestV2:
    return DriverInvocationRequestV2(
        scope_ref=scope,
        driver_id="driver:calculator",
        invocation_id=invocation,
        operation="conformance.add",
        capability="arithmetic:add",
        idempotency_key=key,
        payload={"left": value, "right": 3},
    )


def result(
    item: DriverInvocationRequestV2,
    *,
    value: int = 5,
) -> DriverInvocationResultV2:
    return DriverInvocationResultV2.for_request(
        item,
        ok=True,
        payload={"sum": value},
        provenance="driver:calculator/reference",
    )


def test_v2_values_are_strict_portable_and_defensively_immutable() -> None:
    mutable: dict[str, Any] = {
        "left": 2,
        "right": 3,
        "nested": [1, {"value": "kept"}],
    }
    item = DriverInvocationRequestV2(
        scope_ref=runtime_scope_ref("tenant-a", "run-1"),
        driver_id="driver:calculator",
        invocation_id="invocation:1",
        operation="conformance.add",
        capability="arithmetic:add",
        idempotency_key="retry:1",
        payload=mutable,
    )
    mutable["left"] = 999
    mutable["nested"][1]["value"] = "mutated"
    assert item.payload["left"] == 2
    assert isinstance(item.payload, MappingProxyType)
    wire = item.to_wire()
    assert DriverInvocationRequestV2.from_wire(wire) == item
    detached = item.to_dict()
    cast(dict[str, object], detached["payload"])["left"] = 888
    assert item.payload["left"] == 2

    outcome = result(item)
    receipt = DriverInvocationReceiptV2.for_result(outcome)
    reply = DriverInvocationReplyV2(item, outcome, receipt)
    assert DriverInvocationResultV2.from_wire(outcome.to_wire()) == outcome
    assert DriverInvocationReceiptV2.from_wire(receipt.to_wire()) == receipt
    assert DriverInvocationReplyV2.from_wire(reply.to_wire()) == reply


def test_all_v2_wire_values_reject_unknown_missing_and_wrong_version() -> None:
    item = request()
    outcome = result(item)
    receipt = DriverInvocationReceiptV2.for_result(outcome)
    reply = DriverInvocationReplyV2(item, outcome, receipt)
    cases = (
        (item, DriverInvocationRequestV2),
        (outcome, DriverInvocationResultV2),
        (receipt, DriverInvocationReceiptV2),
        (reply, DriverInvocationReplyV2),
    )
    for value, value_type in cases:
        unknown = value.to_dict()
        unknown["unknown"] = True
        with pytest.raises(DriverInvocationWireErrorV2):
            value_type.from_dict(unknown)
        missing = value.to_dict()
        del missing["version"]
        with pytest.raises(DriverInvocationWireErrorV2):
            value_type.from_dict(missing)
        wrong_version = value.to_dict()
        wrong_version["version"] = "pheroos-driver-invocation-unknown-v999"
        with pytest.raises(DriverInvocationWireErrorV2):
            value_type.from_dict(wrong_version)


@pytest.mark.parametrize("kind", ["missing", "unknown", "digest", "coercion"])
def test_request_from_dict_fails_closed(kind: str) -> None:
    payload = request().to_dict()
    if kind == "missing":
        del payload["operation"]
    elif kind == "unknown":
        payload["extra"] = True
    elif kind == "digest":
        payload["request_digest"] = "sha256:" + "0" * 64
    else:
        payload["invocation_id"] = 1
    with pytest.raises(DriverInvocationWireErrorV2):
        DriverInvocationRequestV2.from_dict(payload)


def test_wire_rejects_duplicates_noncanonical_json_nonfinite_and_size() -> None:
    item = request()
    duplicate = item.to_wire().replace(
        b'{"capability"', b'{"capability":"forged","capability"', 1
    )
    with pytest.raises(DriverInvocationWireErrorV2, match="duplicate"):
        DriverInvocationRequestV2.from_wire(duplicate)

    noncanonical = json.dumps(item.to_dict()).encode("ascii")
    with pytest.raises(DriverInvocationWireErrorV2, match="canonical"):
        DriverInvocationRequestV2.from_wire(noncanonical)
    with pytest.raises(DriverInvocationWireErrorV2):
        replace(item, payload={"number": nan}, request_digest="")
    with pytest.raises(DriverInvocationWireErrorV2, match="size"):
        replace(item, payload={"value": "x" * 70_000}, request_digest="")


def test_result_and_reply_reject_cross_binding_and_missing_provenance() -> None:
    first = request()
    other = request(scope=runtime_scope_ref("tenant-b", "run-1"))
    outcome = result(first)
    with pytest.raises(DriverInvocationWireErrorV2, match="bind"):
        DriverInvocationReplyV2(
            other,
            outcome,
            DriverInvocationReceiptV2.for_result(outcome),
        )
    with pytest.raises(DriverInvocationWireErrorV2, match="provenance"):
        replace(outcome, provenance="", result_digest="")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scope_ref", "tenant-a/run-1"),
        ("scope_ref", "sha256:" + "A" * 64),
        ("driver_id", "driver:bad\x00id"),
        ("operation", "cafe\u0301"),
    ],
)
def test_request_rejects_forged_scope_nul_and_non_nfc_text(
    field: str,
    value: str,
) -> None:
    values: dict[str, Any] = {
        "scope_ref": runtime_scope_ref("tenant-a", "run-1"),
        "driver_id": "driver:calculator",
        "invocation_id": "invocation:1",
        "operation": "conformance.add",
        "capability": "arithmetic:add",
        "idempotency_key": "retry:1",
        "payload": {"left": 2, "right": 3},
        field: value,
    }
    with pytest.raises(DriverInvocationWireErrorV2):
        DriverInvocationRequestV2(**values)


def test_payload_rejects_nul_and_non_nfc_text() -> None:
    with pytest.raises(DriverInvocationWireErrorV2, match="noncanonical text"):
        replace(request(), payload={"value": "bad\x00text"}, request_digest="")
    with pytest.raises(DriverInvocationWireErrorV2, match="canonical"):
        replace(request(), payload={"cafe\u0301": "value"}, request_digest="")
    with pytest.raises(DriverInvocationWireErrorV2, match="unsupported"):
        replace(request(), payload={"items": (1, 2)}, request_digest="")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda: replace(request(), operation="invalid-\ud800", request_digest=""),
        lambda: replace(
            request(), payload={"value": "invalid-\ud800"}, request_digest=""
        ),
        lambda: replace(
            request(), payload={"invalid-\ud800": "value"}, request_digest=""
        ),
        lambda: replace(
            result(request()), provenance="invalid-\ud800", result_digest=""
        ),
    ],
)
def test_v2_wire_rejects_unicode_surrogate_code_points(mutation) -> None:
    with pytest.raises(DriverInvocationWireErrorV2, match="canonical"):
        mutation()


def test_receipt_reply_store_lookup_and_checkpoint_reject_surrogates() -> None:
    item = request()
    outcome = result(item)
    receipt = DriverInvocationReceiptV2.for_result(outcome)
    with pytest.raises(DriverInvocationWireErrorV2, match="canonical"):
        replace(receipt, provenance="invalid-\ud800", receipt_digest="")

    reply = DriverInvocationReplyV2(item, outcome, receipt).to_dict()
    cast(dict[str, object], reply["request"])["operation"] = "invalid-\ud800"
    with pytest.raises(DriverInvocationWireErrorV2, match="canonical"):
        DriverInvocationReplyV2.from_dict(reply)

    store = InMemoryDriverInvocationStoreV2()
    store.record(item, outcome)
    with pytest.raises(DriverInvocationStoreErrorV2, match="canonical"):
        store.get(item.scope_ref, "invalid-\ud800", item.idempotency_key)


def test_v2_public_wire_and_record_boundaries_cover_each_typed_failure() -> None:
    item = request()
    outcome = result(item)
    receipt = DriverInvocationReceiptV2.for_result(outcome)

    floating = replace(
        item,
        payload={"positive": 1.25},
        request_digest="",
    )
    assert floating.payload["positive"] == 1.25
    with pytest.raises(DriverInvocationWireErrorV2, match="number"):
        replace(item, payload={"negative_zero": -0.0}, request_digest="")

    for wire in (b"", b"[1]", b"{", b"\xff"):
        with pytest.raises(DriverInvocationWireErrorV2):
            DriverInvocationRequestV2.from_wire(wire)
    with pytest.raises(DriverInvocationWireErrorV2, match="wire bytes"):
        DriverInvocationRequestV2.from_wire(cast(bytes, "not-bytes"))

    with pytest.raises(DriverInvocationWireErrorV2, match="payload must be an object"):
        replace(item, payload=cast(Any, []), request_digest="")
    request_payload = item.to_dict()
    request_payload["payload"] = []
    with pytest.raises(DriverInvocationWireErrorV2, match="payload must be an object"):
        DriverInvocationRequestV2.from_dict(request_payload)

    with pytest.raises(DriverInvocationWireErrorV2, match="canonical sha256"):
        replace(outcome, request_digest=cast(str, 1), result_digest="")
    with pytest.raises(DriverInvocationWireErrorV2, match="ok must be boolean"):
        replace(outcome, ok=cast(bool, 1), result_digest="")
    with pytest.raises(DriverInvocationWireErrorV2, match="payload must be an object"):
        replace(outcome, payload=cast(Any, []), result_digest="")
    with pytest.raises(DriverInvocationWireErrorV2, match="digest does not match"):
        replace(
            outcome,
            payload=dict(outcome.payload),
            result_digest="sha256:" + "0" * 64,
        )
    with pytest.raises(DriverInvocationWireErrorV2, match="canonical request"):
        DriverInvocationResultV2.for_request(
            cast(DriverInvocationRequestV2, object()),
            ok=True,
            payload={},
            provenance="driver:test",
        )
    result_payload = outcome.to_dict()
    result_payload["payload"] = []
    with pytest.raises(DriverInvocationWireErrorV2, match="payload must be an object"):
        DriverInvocationResultV2.from_dict(result_payload)
    result_payload = outcome.to_dict()
    result_payload["ok"] = 1
    with pytest.raises(DriverInvocationWireErrorV2, match="ok must be boolean"):
        DriverInvocationResultV2.from_dict(result_payload)

    with pytest.raises(DriverInvocationWireErrorV2, match="canonical values"):
        validate_driver_invocation_binding_v2(cast(Any, object()), outcome)
    with pytest.raises(DriverInvocationWireErrorV2, match="digest does not match"):
        replace(receipt, receipt_digest="sha256:" + "0" * 64)
    with pytest.raises(DriverInvocationWireErrorV2, match="canonical result"):
        DriverInvocationReceiptV2.for_result(cast(Any, object()))

    other_receipt = replace(receipt, provenance="driver:other", receipt_digest="")
    with pytest.raises(DriverInvocationWireErrorV2, match="receipt does not bind"):
        DriverInvocationReplyV2(item, outcome, other_receipt)
    reply_payload = DriverInvocationReplyV2(item, outcome, receipt).to_dict()
    reply_payload["request"] = []
    with pytest.raises(DriverInvocationWireErrorV2, match="members must be objects"):
        DriverInvocationReplyV2.from_dict(reply_payload)

    store = InMemoryDriverInvocationStoreV2()
    store.record(item, outcome)
    checkpoint = json.loads(store.checkpoint())
    checkpoint["receipts"][0]["provenance"] = "invalid-\ud800"
    malformed = json.dumps(
        checkpoint,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    with pytest.raises(DriverInvocationStoreErrorV2, match="receipt is invalid"):
        InMemoryDriverInvocationStoreV2.from_checkpoint(malformed)


def test_store_is_idempotent_conflict_safe_and_runtime_checkable() -> None:
    store = InMemoryDriverInvocationStoreV2()
    assert isinstance(store, DriverInvocationStoreV2)
    item = request()
    outcome = result(item)
    first = store.record(item, outcome)
    assert store.record(item, outcome) is first
    assert store.get(item.scope_ref, item.driver_id, item.idempotency_key) == first

    conflicting_request = request(invocation="invocation:other")
    with pytest.raises(DriverInvocationStoreErrorV2, match="conflicts"):
        store.record(conflicting_request, result(conflicting_request))
    with pytest.raises(DriverInvocationStoreErrorV2, match="conflicts"):
        store.record(item, result(item, value=999))
    with pytest.raises(DriverInvocationStoreErrorV2, match="RuntimeScope"):
        store.get("tenant-a/run-1", item.driver_id, item.idempotency_key)


def test_store_concurrent_retry_commits_one_canonical_receipt() -> None:
    store = InMemoryDriverInvocationStoreV2()
    item = request()
    outcome = result(item)
    with ThreadPoolExecutor(max_workers=32) as pool:
        receipts = tuple(pool.map(lambda _: store.record(item, outcome), range(32)))
    assert len({receipt.receipt_digest for receipt in receipts}) == 1
    assert len(json.loads(store.checkpoint())["receipts"]) == 1


def test_store_scope_isolation_retirement_and_restart_tombstone() -> None:
    store = InMemoryDriverInvocationStoreV2()
    first = request(scope=runtime_scope_ref("tenant-a", "run-1"))
    second = request(scope=runtime_scope_ref("tenant-a", "run-2"))
    third = request(scope=runtime_scope_ref("tenant-b", "run-1"))
    for item in (first, second, third):
        store.record(item, result(item))
    assert store.retire(first.scope_ref) == 1
    assert store.get(first.scope_ref, first.driver_id, first.idempotency_key) is None

    checkpoint = store.checkpoint()
    restarted = InMemoryDriverInvocationStoreV2.from_checkpoint(checkpoint)
    assert restarted.checkpoint() == checkpoint
    assert restarted.record(second, result(second)).scope_ref == second.scope_ref
    assert restarted.record(third, result(third)).scope_ref == third.scope_ref
    with pytest.raises(DriverInvocationStoreErrorV2, match="retired"):
        restarted.record(first, result(first))
    assert restarted.retire(first.scope_ref) == 0


def test_checkpoint_is_closed_canonical_and_mutation_safe() -> None:
    store = InMemoryDriverInvocationStoreV2()
    item = request()
    store.record(item, result(item))
    checkpoint = store.checkpoint()
    parsed = json.loads(checkpoint)
    assert parsed["version"] == DRIVER_INVOCATION_CHECKPOINT_VERSION_V2
    parsed["unknown"] = True
    with pytest.raises(DriverInvocationStoreErrorV2):
        InMemoryDriverInvocationStoreV2.from_checkpoint(
            json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode("ascii")
        )
    noncanonical = json.dumps(json.loads(checkpoint)).encode("ascii")
    with pytest.raises(DriverInvocationStoreErrorV2, match="canonical"):
        InMemoryDriverInvocationStoreV2.from_checkpoint(noncanonical)
    duplicate = checkpoint.replace(
        b'{"checkpoint_digest"', b'{"version":"x","checkpoint_digest"', 1
    )
    with pytest.raises(DriverInvocationStoreErrorV2, match="duplicate"):
        InMemoryDriverInvocationStoreV2.from_checkpoint(duplicate)


def _canonical_checkpoint(document: dict[str, Any], *, refresh: bool = True) -> bytes:
    if refresh:
        unsigned = {
            name: document[name]
            for name in ("version", "store_version", "receipts", "retired_scopes")
        }
        material = json.dumps(
            unsigned,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        document["checkpoint_digest"] = "sha256:" + sha256(material).hexdigest()
    return json.dumps(
        document,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _two_receipt_checkpoint() -> dict[str, Any]:
    store = InMemoryDriverInvocationStoreV2()
    for index in (1, 2):
        item = request(invocation=f"invocation:{index}", key=f"retry:{index}")
        store.record(item, result(item))
    return cast(dict[str, Any], json.loads(store.checkpoint()))


def test_checkpoint_public_reader_rejects_each_structural_inconsistency() -> None:
    scope = request().scope_ref
    store = InMemoryDriverInvocationStoreV2()
    with pytest.raises(DriverInvocationStoreErrorV2, match="RuntimeScope"):
        store.get("sha256:" + "g" * 64, "driver:one", "retry:one")
    with pytest.raises(DriverInvocationStoreErrorV2, match="RuntimeScope"):
        store.get("sha256:" + "A" * 64, "driver:one", "retry:one")

    for wire in (b"", b"{", b"\xff", b"x" * 4_194_305):
        with pytest.raises(DriverInvocationStoreErrorV2):
            InMemoryDriverInvocationStoreV2.from_checkpoint(wire)

    baseline = _two_receipt_checkpoint()
    mutations: tuple[tuple[str, dict[str, Any]], ...] = (
        (
            "unsupported checkpoint version",
            {**baseline, "version": "unknown"},
        ),
        (
            "unsupported checkpoint store version",
            {**baseline, "store_version": "unknown"},
        ),
        (
            "collections are invalid",
            {**baseline, "receipts": {}},
        ),
        (
            "receipt must be an object",
            {**baseline, "receipts": [1]},
        ),
        (
            "retired scope is invalid",
            {**baseline, "retired_scopes": [1]},
        ),
        (
            "duplicate receipt keys",
            {**baseline, "receipts": [baseline["receipts"][0]] * 2},
        ),
        (
            "collections are not canonical",
            {**baseline, "receipts": list(reversed(baseline["receipts"]))},
        ),
        (
            "collections are not canonical",
            {
                **baseline,
                "receipts": [],
                "retired_scopes": [
                    runtime_scope_ref("tenant-z", "run-z"),
                    runtime_scope_ref("tenant-a", "run-a"),
                ],
            },
        ),
        (
            "retired scope contains active receipt",
            {**baseline, "retired_scopes": [scope]},
        ),
    )
    for message, document in mutations:
        with pytest.raises(DriverInvocationStoreErrorV2, match=message):
            InMemoryDriverInvocationStoreV2.from_checkpoint(
                _canonical_checkpoint(document)
            )

    wrong_digest = _two_receipt_checkpoint()
    wrong_digest["checkpoint_digest"] = "sha256:" + "0" * 64
    with pytest.raises(DriverInvocationStoreErrorV2, match="digest"):
        InMemoryDriverInvocationStoreV2.from_checkpoint(
            _canonical_checkpoint(wrong_digest, refresh=False)
        )


def test_store_rejects_cross_bound_result_and_oversized_checkpoint() -> None:
    store = InMemoryDriverInvocationStoreV2()
    first = request()
    other = request(scope=runtime_scope_ref("tenant-b", "run-2"))
    with pytest.raises(DriverInvocationStoreErrorV2, match="binding is invalid"):
        store.record(first, result(other))

    long_text = "x" * 1000
    for index in range(680):
        suffix = f"{index:04d}"
        item = DriverInvocationRequestV2(
            scope_ref=first.scope_ref,
            driver_id=f"driver:{suffix}:{long_text}",
            invocation_id=f"invocation:{suffix}:{long_text}",
            operation=f"operation:{long_text}",
            capability=f"capability:{long_text}",
            idempotency_key=f"retry:{suffix}:{long_text}",
            payload={},
        )
        outcome = DriverInvocationResultV2.for_request(
            item,
            ok=True,
            payload={},
            provenance=f"provenance:{long_text}",
        )
        store.record(item, outcome)
    with pytest.raises(DriverInvocationStoreErrorV2, match="size limit"):
        store.checkpoint()


def test_failure_before_commit_and_retire_have_no_partial_write() -> None:
    def fail(stage: str) -> None:
        raise OSError(stage)

    store = InMemoryDriverInvocationStoreV2(failure_hook=fail)
    item = request()
    before = store.checkpoint()
    with pytest.raises(OSError, match="before_commit"):
        store.record(item, result(item))
    assert store.checkpoint() == before

    healthy = InMemoryDriverInvocationStoreV2()
    healthy.record(item, result(item))
    failing = InMemoryDriverInvocationStoreV2.from_checkpoint(
        healthy.checkpoint(), failure_hook=fail
    )
    before_retire = failing.checkpoint()
    with pytest.raises(OSError, match="before_retire"):
        failing.retire(item.scope_ref)
    assert failing.checkpoint() == before_retire


def test_receipt_is_data_and_serialization_does_not_create_authority() -> None:
    item = request()
    receipt = InMemoryDriverInvocationStoreV2().record(item, result(item))
    restored = loads(dumps(receipt))
    assert restored == receipt
    assert not hasattr(receipt, "authorize")
    assert not hasattr(restored, "commit")
    assert DriverInvocationReceiptV2.from_dict(receipt.to_dict()) == receipt
