from __future__ import annotations

from typing import Any, cast
import json
from pathlib import Path

import pytest

from pheroos.drivers import DriverProbeSnapshot
from pheroos.kernel import (
    KERNEL_PLAN_VERSION_V2,
    ConnectionReadiness,
    InputEnvelope,
    OSKernel,
    OSPlanDocument,
    runtime_scope_ref,
)
from pheroos.kernel.errors import KernelError
from pheroos.protocol import (
    CAPABILITY_SCHEMA_V3,
    ScopedCapabilityManifestV2,
    read_capability_manifest,
)


ROOT = Path(__file__).resolve().parents[2]


def _payload() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            (ROOT / "examples/scoped-output-protocol/capability.json").read_text(
                encoding="utf-8"
            )
        ),
    )


def _read(payload: dict[str, Any] | None = None) -> ScopedCapabilityManifestV2:
    value = read_capability_manifest(
        payload or _payload(),
        schema_version=CAPABILITY_SCHEMA_V3,
    )
    assert type(value) is ScopedCapabilityManifestV2
    return value


def _envelope() -> InputEnvelope:
    return InputEnvelope(
        request="review",
        tenant_id="tenant:scoped",
        metadata={"request_id": "request:scoped", "run_id": "run:scoped"},
    )


def test_real_scoped_example_plans_to_the_existing_kernel_v2_document() -> None:
    plan = OSKernel().plan(_envelope(), [_read()])
    document = OSPlanDocument(plan)

    assert plan.runtime_ready is True
    assert plan.capability_resolutions[0].capability_id == "scoped-output-protocol"
    assert plan.scope_ref == runtime_scope_ref("tenant:scoped", "run:scoped")
    assert document.plan_version == KERNEL_PLAN_VERSION_V2
    assert document.to_dict()["plan_version"] == KERNEL_PLAN_VERSION_V2


def test_scoped_resources_require_exact_connection_and_driver_readiness() -> None:
    payload = _payload()
    payload["permissions"] = ["permission:review"]
    payload["required_connections"] = ["connection:evidence"]
    payload["drivers"] = [
        {
            "id": "driver:evidence",
            "kind": "tool",
            "version": "2.0.0",
            "capabilities": ["evidence:read"],
            "permissions": ["driver:invoke"],
        }
    ]
    manifest = _read(payload)

    missing = OSKernel().plan(_envelope(), [manifest])
    mismatch = OSKernel().plan(
        _envelope(),
        [manifest],
        connection_readiness=(
            ConnectionReadiness(connection="connection:evidence", available=True),
        ),
        driver_probe_snapshots=(
            DriverProbeSnapshot(
                driver_id="driver:evidence",
                available=True,
                version="1.0.0",
                capabilities=("evidence:read",),
            ),
        ),
    )
    ready = OSKernel().plan(
        _envelope(),
        [manifest],
        connection_readiness=(
            ConnectionReadiness(connection="connection:evidence", available=True),
        ),
        driver_probe_snapshots=(
            DriverProbeSnapshot(
                driver_id="driver:evidence",
                available=True,
                version="2.0.0",
                capabilities=("evidence:read",),
            ),
        ),
    )

    assert missing.capability_resolutions[0].reason == (
        "connection_readiness_missing,driver_probe_missing"
    )
    assert mismatch.capability_resolutions[0].reason == "driver_version_mismatch"
    assert ready.runtime_ready is True
    assert ready.permission_grants[0].permission == "permission:review"
    assert ready.connection_requirements[0].connection == "connection:evidence"
    assert ready.driver_exposures[0].driver_id == "driver:evidence"
    assert ready.driver_exposures[0].capabilities == ("evidence:read",)


def test_tampered_scoped_manifest_is_not_resolved_or_exposed() -> None:
    manifest = _read()
    object.__setattr__(manifest, "permissions", ["permission:forged"])

    plan = OSKernel().plan(_envelope(), [manifest])

    assert plan.runtime_ready is False
    assert plan.permission_grants == ()
    assert plan.capability_resolutions[0].reason == (
        "manifest_scoped_capability_manifest_invalid"
    )


def test_semantically_tampered_scoped_protocol_cannot_enter_kernel() -> None:
    manifest = _read()
    object.__setattr__(manifest.protocol.signals[0], "target", "decision:missing")

    plan = OSKernel().plan(_envelope(), [manifest])

    assert plan.runtime_ready is False
    assert plan.permission_grants == ()
    assert plan.driver_exposures == ()
    assert plan.capability_resolutions[0].reason == (
        "manifest_scoped_capability_manifest_invalid"
    )


def test_unsupported_duck_manifest_fails_closed_without_attribute_error() -> None:
    class CapabilityLike:
        id = "duck:capability"

    plan = OSKernel().plan(
        _envelope(),
        cast(Any, [CapabilityLike()]),
    )

    assert plan.runtime_ready is False
    assert plan.permission_grants == ()
    assert plan.capability_resolutions[0].capability_id == "<unsupported>"
    assert plan.capability_resolutions[0].reason == (
        "manifest_capability_manifest_type_unsupported"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tenant_id", 7),
        ("tenant_id", " tenant:scoped"),
        ("tenant_id", "tenant:\x00scoped"),
        ("tenant_id", "tenant:e\u0301"),
        ("tenant_id", "tenant:\ud800"),
        ("tenant_id", "t" * 1025),
        ("request_id", False),
        ("request_id", " request:scoped"),
        ("request_id", "request:\x00scoped"),
        ("request_id", "request:e\u0301"),
        ("request_id", "request:\ud800"),
        ("request_id", "r" * 1025),
        ("run_id", []),
        ("run_id", " run:scoped"),
        ("run_id", "run:\x00scoped"),
        ("run_id", "run:e\u0301"),
        ("run_id", "run:\ud800"),
        ("run_id", "r" * 1025),
    ],
)
def test_kernel_rejects_nonportable_scope_before_planning(
    field: str,
    value: object,
) -> None:
    tenant_id: object = "tenant:scoped"
    metadata: dict[str, object] = {
        "request_id": "request:scoped",
        "run_id": "run:scoped",
    }
    if field == "tenant_id":
        tenant_id = value
    else:
        metadata[field] = value
    envelope = InputEnvelope(
        request="review",
        tenant_id=cast(Any, tenant_id),
        metadata=metadata,
    )

    with pytest.raises(KernelError, match="runtime scope input is invalid"):
        OSKernel().plan(envelope, [_read()])


def test_kernel_defaults_scope_ids_only_when_metadata_keys_are_absent() -> None:
    plan = OSKernel().plan(
        InputEnvelope(request="review", tenant_id="tenant:scoped"),
        [],
    )

    assert plan.request_id == "request"
    assert plan.run_id == "request"
    assert plan.scope_ref == runtime_scope_ref("tenant:scoped", "request")

    for metadata in ({"request_id": ""}, {"run_id": ""}):
        with pytest.raises(KernelError, match="runtime scope input is invalid"):
            OSKernel().plan(
                InputEnvelope(
                    request="review",
                    tenant_id="tenant:scoped",
                    metadata=metadata,
                ),
                [],
            )
