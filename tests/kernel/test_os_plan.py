from dataclasses import replace

from pheroos.drivers import DriverProbeSnapshot
from pheroos.kernel import ConnectionReadiness, InputEnvelope, OSKernel
from pheroos.protocol import (
    CandidateSpec,
    CapabilityManifest,
    DriverSpec,
    OutputPolicy,
    ProtocolManifest,
    QuorumPolicy,
    TargetSpec,
    TracePolicy,
    load_capability_manifest,
)


def test_os_kernel_outputs_plan_without_domain_conclusion() -> None:
    capability = load_capability_manifest("examples/toy-protocol/capability.json")
    envelope = InputEnvelope(
        request="review this packet",
        tenant_id="tenant-a",
        metadata={"request_id": "req-1"},
    )

    plan = OSKernel().plan(envelope, [capability])

    assert plan.tenant_id == "tenant-a"
    assert plan.request_id == "req-1"
    assert plan.runtime_ready is True
    assert plan.capability_resolutions[0].capability_id == "toy-protocol"


def test_os_kernel_uses_provider_neutral_driver_specs_for_exposure() -> None:
    capability = load_capability_manifest("examples/e2e-protocol/capability.json")
    envelope = InputEnvelope(
        request="review this packet",
        tenant_id="tenant-a",
        metadata={"request_id": "req-1"},
    )

    plan = OSKernel().plan(
        envelope,
        [capability],
        driver_probe_snapshots=[
            DriverProbeSnapshot(
                driver_id="driver:toy-evidence",
                available=True,
                version="0.1.0",
                capabilities=["evidence:read"],
            )
        ],
    )

    assert plan.driver_exposures[0].driver_id == "driver:toy-evidence"
    assert plan.driver_exposures[0].permissions == ("driver:invoke",)


def test_os_kernel_requires_probe_snapshot_for_declared_driver() -> None:
    capability = load_capability_manifest("examples/e2e-protocol/capability.json")
    envelope = InputEnvelope(
        request="review this packet",
        tenant_id="tenant-a",
        metadata={"request_id": "req-1"},
    )

    plan = OSKernel().plan(envelope, [capability])

    assert plan.runtime_ready is False
    assert plan.driver_exposures == ()
    assert plan.capability_resolutions[0].available is False
    assert plan.capability_resolutions[0].reason == "driver_probe_missing"
    assert {diagnostic.code for diagnostic in plan.diagnostics} == {
        "driver_probe_missing"
    }


def test_os_kernel_rejects_incompatible_driver_probe() -> None:
    capability = load_capability_manifest("examples/e2e-protocol/capability.json")
    envelope = InputEnvelope(
        request="review this packet",
        tenant_id="tenant-a",
        metadata={"request_id": "req-1"},
    )

    version_mismatch = OSKernel().plan(
        envelope,
        [capability],
        driver_probe_snapshots=[
            DriverProbeSnapshot(
                driver_id="driver:toy-evidence",
                available=True,
                version="9.0.0",
                capabilities=["evidence:read"],
            )
        ],
    )
    capability_mismatch = OSKernel().plan(
        envelope,
        [capability],
        driver_probe_snapshots=[
            DriverProbeSnapshot(
                driver_id="driver:toy-evidence",
                available=True,
                version="0.1.0",
                capabilities=["other:read"],
            )
        ],
    )

    assert version_mismatch.runtime_ready is False
    assert capability_mismatch.runtime_ready is False
    assert {item.code for item in version_mismatch.diagnostics} == {
        "driver_version_mismatch"
    }
    assert {item.code for item in capability_mismatch.diagnostics} == {
        "driver_capability_mismatch"
    }


def test_os_kernel_requires_connection_readiness_snapshot() -> None:
    capability = replace(
        load_capability_manifest("examples/toy-protocol/capability.json"),
        required_connections=["connection:evidence"],
    )
    envelope = InputEnvelope(
        request="review this packet",
        tenant_id="tenant-a",
        metadata={"request_id": "req-1"},
    )

    missing = OSKernel().plan(envelope, [capability])
    ready = OSKernel().plan(
        envelope,
        [capability],
        connection_readiness=[
            ConnectionReadiness(connection="connection:evidence", available=True)
        ],
    )

    assert missing.runtime_ready is False
    assert missing.capability_resolutions[0].reason == "connection_readiness_missing"
    assert ready.runtime_ready is True
    assert ready.connection_readiness[0].connection == "connection:evidence"


def test_os_kernel_does_not_fallback_from_driver_permissions_to_capability_permissions() -> (
    None
):
    capability = CapabilityManifest(
        id="capability:runtime",
        name="Runtime Capability",
        version="0.1.0",
        permissions=["publish"],
        drivers=[
            DriverSpec(
                id="driver:tool",
                kind="tool",
                version="0.1.0",
                capabilities=["tool:invoke"],
                permissions=[],
            )
        ],
        protocol=ProtocolManifest(
            protocol_version="pheroos.protocol.v1",
            id="runtime.protocol",
            targets=[TargetSpec(id="decision:review")],
            candidates=[
                CandidateSpec(
                    id="candidate:fallback",
                    target="decision:review",
                    safe_fallback=True,
                )
            ],
            quorum_policy=QuorumPolicy(
                target="decision:review", fallback_candidate="candidate:fallback"
            ),
            output_policy=OutputPolicy(),
            trace_policy=TracePolicy(),
        ),
    )
    envelope = InputEnvelope(
        request="review", tenant_id="tenant-a", metadata={"request_id": "req-1"}
    )

    plan = OSKernel().plan(envelope, [capability])

    assert plan.driver_exposures == ()
    assert {diagnostic.code for diagnostic in plan.diagnostics} == {
        "driver_permissions_missing"
    }


def test_input_envelope_recursively_snapshots_metadata() -> None:
    caller_metadata = {
        "request_id": "req-original",
        "nested": {"values": ["original"]},
    }
    envelope = InputEnvelope(
        request="review",
        tenant_id="tenant-a",
        metadata=caller_metadata,
    )
    caller_metadata["request_id"] = "req-forged"
    caller_metadata["nested"]["values"].append("mutated")

    plan = OSKernel().plan(envelope, [])

    assert plan.request_id == "req-original"
    assert envelope.metadata["nested"]["values"] == ("original",)
