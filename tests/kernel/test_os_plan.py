from pheroos.kernel import InputEnvelope, OSKernel
from pheroos.protocol import load_capability_manifest


def test_os_kernel_outputs_plan_without_domain_conclusion() -> None:
    capability = load_capability_manifest("examples/toy-protocol/capability.json")
    envelope = InputEnvelope(request="review this packet", tenant_id="tenant-a", metadata={"request_id": "req-1"})

    plan = OSKernel().plan(envelope, [capability])

    assert plan.tenant_id == "tenant-a"
    assert plan.request_id == "req-1"
    assert plan.runtime_ready is True
    assert plan.capability_resolutions[0].capability_id == "toy-protocol"


def test_os_kernel_uses_provider_neutral_driver_specs_for_exposure() -> None:
    capability = load_capability_manifest("examples/e2e-protocol/capability.json")
    envelope = InputEnvelope(request="review this packet", tenant_id="tenant-a", metadata={"request_id": "req-1"})

    plan = OSKernel().plan(envelope, [capability])

    assert plan.driver_exposures[0].driver_id == "driver:toy-evidence"
    assert plan.driver_exposures[0].permissions == ["driver:invoke"]
