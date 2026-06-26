import json
from pathlib import Path

from pheroos.conformance import run_conformance, validate_manifest
from pheroos.conformance.checks import driver_contract, kernel_contract
from pheroos.kernel import DriverExposure, OSPlan
from pheroos.protocol import (
    CandidateSpec,
    CapabilityManifest,
    DriverSpec,
    OutputPolicy,
    ProtocolManifest,
    QuorumPolicy,
    TargetSpec,
    TracePolicy,
)


def test_e2e_protocol_validate_and_conformance_pass() -> None:
    validation = validate_manifest("examples/e2e-protocol/capability.json")
    conformance = run_conformance("examples/e2e-protocol")

    assert validation.ok is True
    assert conformance.ok is True
    assert "extension_contract" in {check.name for check in conformance.checks}
    assert "kernel_contract" in {check.name for check in conformance.checks}
    assert "profile_contract" in {check.name for check in conformance.checks}


def test_secret_like_manifest_fields_fail_validation(tmp_path: Path) -> None:
    payload = json.loads(Path("examples/e2e-protocol/capability.json").read_text())
    payload["protocol"]["extensions"] = {"x-runtime": {"password": "not-allowed"}}
    path = tmp_path / "capability.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    validation = validate_manifest(path)

    assert validation.ok is False
    assert "secret-like manifest fields" in validation.checks[0].detail


def test_driver_contract_requires_declared_capabilities_and_permissions() -> None:
    manifest = CapabilityManifest(
        id="driver-contract",
        name="Driver Contract",
        version="0.1.0",
        drivers=[DriverSpec(id="driver:tool", kind="tool", version="0.1.0")],
        protocol=ProtocolManifest(
            protocol_version="pheroos.protocol.v1",
            id="driver.contract",
            targets=[TargetSpec(id="decision:review")],
            candidates=[CandidateSpec(id="candidate:fallback", target="decision:review", safe_fallback=True)],
            quorum_policy=QuorumPolicy(target="decision:review", fallback_candidate="candidate:fallback"),
            output_policy=OutputPolicy(),
            trace_policy=TracePolicy(),
        ),
    )

    result = driver_contract.check(manifest)

    assert result.ok is False
    assert "0:capabilities" in result.detail
    assert "0:permissions" in result.detail


def test_kernel_contract_proves_core_kernel_authority_boundaries() -> None:
    manifest = CapabilityManifest(
        id="kernel-contract",
        name="Kernel Contract",
        version="0.1.0",
        drivers=[
            DriverSpec(
                id="driver:tool",
                kind="tool",
                version="0.1.0",
                capabilities=["tool:invoke"],
                permissions=["driver:invoke"],
            )
        ],
        protocol=ProtocolManifest(
            protocol_version="pheroos.protocol.v1",
            id="kernel.contract",
            targets=[TargetSpec(id="decision:review")],
            candidates=[CandidateSpec(id="candidate:fallback", target="decision:review", safe_fallback=True)],
            quorum_policy=QuorumPolicy(target="decision:review", fallback_candidate="candidate:fallback"),
            output_policy=OutputPolicy(),
            trace_policy=TracePolicy(),
        ),
    )

    result = kernel_contract.check(manifest)

    assert result.ok is True
    assert result.detail == ""


def test_kernel_contract_reports_bad_plan_shape() -> None:
    bad_plan = OSPlan(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[DriverExposure(driver_id="driver:bad", capability_id="capability:bad")],
    )

    problems = kernel_contract.plan_authority_problems(bad_plan)

    assert "plan:unpermissioned_driver_exposure" in problems
