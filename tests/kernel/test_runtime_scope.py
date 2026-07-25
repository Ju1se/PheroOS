from __future__ import annotations

from dataclasses import FrozenInstanceError
import pickle
from types import MappingProxyType
from typing import Callable

import pytest

from pheroos.kernel import (
    RUNTIME_SCOPE_VERSION,
    OSPlan,
    OSPlanDocument,
    RuntimeMaterializer,
    RuntimeScope,
    runtime_scope_ref,
)
from pheroos.kernel.errors import KernelError
from pheroos.kernel.plan_document import KernelPlanVersionError


def test_runtime_scope_is_deterministic_and_tenant_isolated() -> None:
    first = RuntimeScope(
        tenant_id="tenant-a",
        run_id="run-1",
        request_id="request-1",
    )
    retry = RuntimeScope(
        tenant_id="tenant-a",
        run_id="run-1",
        request_id="request-2",
    )
    other_tenant = RuntimeScope(
        tenant_id="tenant-b",
        run_id="run-1",
        request_id="request-1",
    )

    assert first.scope_ref == retry.scope_ref
    assert first.scope_ref.startswith("sha256:")
    assert other_tenant.scope_ref != first.scope_ref


def test_runtime_scope_rejects_forged_scope_ref() -> None:
    try:
        RuntimeScope(
            tenant_id="tenant-a",
            run_id="run-1",
            request_id="request-1",
            scope_ref="sha256:" + "0" * 64,
        )
    except ValueError as exc:
        assert "scope_ref" in str(exc)
    else:  # pragma: no cover - explicit fail keeps the test dependency-free
        raise AssertionError("forged runtime scope ref was accepted")


def test_runtime_scope_v1_portable_wire_roundtrip_and_request_semantics() -> None:
    scope = RuntimeScope(
        tenant_id="tenant-a",
        run_id="run-1",
        request_id="request-1",
    )
    payload = scope.to_dict()

    assert payload == {
        "scope_version": RUNTIME_SCOPE_VERSION,
        "tenant_id": "tenant-a",
        "run_id": "run-1",
        "request_id": "request-1",
        "scope_ref": "sha256:8ba4527fcb104198ac480be091353bb84fa12930512eafeea67f7d3b3c8eb370",
    }
    assert RuntimeScope.from_dict(MappingProxyType(payload)) == scope
    assert RuntimeScope.from_dict(payload | {"request_id": "request-2"}).scope_ref == (
        scope.scope_ref
    )


@pytest.mark.parametrize(
    "change",
    [
        {"tenant_id": "tenant-b"},
        {"run_id": "run-2"},
    ],
)
def test_runtime_scope_v1_rejects_cross_identity_root_reuse(
    change: dict[str, str],
) -> None:
    payload = RuntimeScope("tenant-a", "run-1", "request-1").to_dict()

    with pytest.raises(ValueError, match="scope_ref"):
        RuntimeScope.from_dict(payload | change)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (
            lambda value: {key: item for key, item in value.items() if key != "run_id"},
            "missing fields",
        ),
        (lambda value: value | {"extra": "forbidden"}, "unknown fields"),
        (
            lambda value: value | {"scope_version": "pheroos-runtime-scope-v2"},
            "version",
        ),
        (lambda value: value | {"scope_ref": "sha256:" + "0" * 64}, "scope_ref"),
        (lambda value: value | {"tenant_id": 7}, "tenant_id"),
        (lambda value: value | {"request_id": " request-1"}, "request_id"),
        (lambda value: value | {"request_id": "request-1\x00suffix"}, "request_id"),
        (lambda value: value | {"request_id": "r" * 1025}, "request_id"),
    ],
)
def test_runtime_scope_v1_reader_is_exact(
    mutate: Callable[[dict[str, str]], dict[str, object]],
    message: str,
) -> None:
    payload = RuntimeScope("tenant-a", "run-1", "request-1").to_dict()

    with pytest.raises(ValueError, match=message):
        RuntimeScope.from_dict(mutate(payload))


def test_runtime_scope_v1_reader_takes_defensive_snapshot_and_is_immutable() -> None:
    payload = RuntimeScope("tenant-a", "run-1", "request-1").to_dict()
    restored = RuntimeScope.from_dict(payload)
    payload["request_id"] = "mutated"

    assert restored.request_id == "request-1"
    with pytest.raises(FrozenInstanceError):
        restored.request_id = "mutated"
    assert pickle.loads(pickle.dumps(restored)) == restored


def test_runtime_scope_existing_constructor_and_ref_are_unchanged() -> None:
    legacy_permitted = RuntimeScope(" tenant ", " run ", " request ")

    assert legacy_permitted.scope_ref == (
        "sha256:7040378488abc4b3478868abe045df396fbe5e5bbbb12a73b67c9a9715e4b6e5"
    )
    assert runtime_scope_ref("tenant:scoped", "run:scoped") == (
        "sha256:c92123671cc68cdba003ec4ede4bde7f66b8cc27550a87e219fa3820ba747c51"
    )
    with pytest.raises(ValueError, match="outer whitespace"):
        legacy_permitted.to_dict()


def test_runtime_scope_legacy_constructor_preserves_non_nfc_but_wire_rejects_it() -> (
    None
):
    decomposed = RuntimeScope("tenant-e\u0301", "run", "request")

    assert decomposed.tenant_id == "tenant-e\u0301"
    with pytest.raises(ValueError, match="Unicode NFC"):
        decomposed.to_dict()

    payload = RuntimeScope("tenant-é", "run", "request").to_dict()
    with pytest.raises(ValueError, match="Unicode NFC"):
        RuntimeScope.from_dict(payload | {"tenant_id": "tenant-e\u0301"})


@pytest.mark.parametrize("field", ["tenant_id", "run_id", "request_id"])
def test_runtime_scope_portable_boundary_rejects_unicode_surrogates(
    field: str,
) -> None:
    values = {
        "tenant_id": "tenant-a",
        "run_id": "run-1",
        "request_id": "request-1",
    }
    values[field] = "invalid-\ud800"
    legacy = RuntimeScope(**values)

    with pytest.raises(ValueError, match="Unicode scalar"):
        legacy.to_dict()

    payload = RuntimeScope("tenant-a", "run-1", "request-1").to_dict()
    payload[field] = "invalid-\ud800"
    with pytest.raises(ValueError, match="Unicode scalar"):
        RuntimeScope.from_dict(payload)


def test_plan_document_and_materializer_reject_legacy_nonportable_scope() -> None:
    plan = OSPlan(
        tenant_id="tenant-a",
        run_id="run-1",
        request_id="request-1\x00forged",
        runtime_ready=True,
    )

    with pytest.raises(KernelPlanVersionError, match="scope is invalid"):
        OSPlanDocument(plan)
    with pytest.raises(KernelError, match="scope is invalid"):
        RuntimeMaterializer().materialize(plan)
