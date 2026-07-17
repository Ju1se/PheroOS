from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from pheroos.drivers import DriverProbeSnapshot
from pheroos.kernel import (
    KERNEL_PLAN_VERSION_V2,
    KERNEL_SCHEMA_V1_ID,
    KERNEL_SCHEMA_V2_ID,
    ConnectionReadiness,
    KernelPlanVersionError,
    LegacyOSPlan,
    OSPlanDocument,
    kernel_schema,
    kernel_schema_v2,
    os_plan_from_dict,
    os_plan_v1_from_dict,
    runtime_scope_ref,
    upgrade_os_plan_v1,
)


ROOT = Path(__file__).resolve().parents[2]
V1_ROOT = "da2e2001a61c19d2726bc96ef05392e1acb8618c6bb6a3dfb233bcc0398e0822"


def _fixture() -> dict[str, object]:
    return json.loads(
        (ROOT / "tests/fixtures/schema-v1/kernel-plan.json").read_text()
    )


def test_kernel_v1_artifact_is_frozen_and_alias_is_byte_equivalent() -> None:
    artifact = ROOT / "schemas/kernel.schema.json"
    expected = (json.dumps(kernel_schema(), indent=2, sort_keys=True) + "\n").encode()

    assert artifact.read_bytes() == expected
    assert sha256(expected).hexdigest() == V1_ROOT
    assert kernel_schema()["$id"] == KERNEL_SCHEMA_V1_ID


def test_kernel_v2_artifact_is_versioned_and_checked_in() -> None:
    generated = kernel_schema_v2()
    artifact = json.loads((ROOT / "schemas/kernel-v2.schema.json").read_text())

    Draft202012Validator.check_schema(generated)
    assert artifact == generated
    assert generated["$id"] == KERNEL_SCHEMA_V2_ID
    assert generated["properties"]["plan_version"] == {
        "const": KERNEL_PLAN_VERSION_V2
    }


def test_kernel_v1_reader_does_not_synthesize_scope_or_readiness_authority() -> None:
    payload = _fixture()
    Draft202012Validator(kernel_schema()).validate(payload)

    legacy = os_plan_v1_from_dict(payload)

    assert isinstance(legacy, LegacyOSPlan)
    assert not hasattr(legacy, "run_id")
    assert not hasattr(legacy, "scope_ref")
    assert not hasattr(legacy, "connection_readiness")
    with pytest.raises(ValidationError):
        Draft202012Validator(kernel_schema_v2()).validate(payload)


def test_kernel_v1_upgrade_requires_explicit_driver_and_readiness_authority() -> None:
    legacy = os_plan_v1_from_dict(_fixture())
    scope_ref = runtime_scope_ref("tenant:legacy", "run:upgrade")
    readiness = (
        ConnectionReadiness(connection="connection:evidence", available=True),
    )
    probes = (
        DriverProbeSnapshot(
            driver_id="driver:legacy",
            available=True,
            version="0.1.0",
            capabilities=("tool:invoke",),
        ),
    )
    with pytest.raises(KernelPlanVersionError) as raised:
        upgrade_os_plan_v1(
            legacy,
            run_id="run:upgrade",
            scope_ref=scope_ref,
            connection_readiness=readiness,
            driver_probe_snapshots=probes,
            driver_capabilities={},
            driver_versions={},
        )
    assert raised.value.code == "kernel_plan_v1_driver_authority_missing"

    document = upgrade_os_plan_v1(
        legacy,
        run_id="run:upgrade",
        scope_ref=scope_ref,
        connection_readiness=readiness,
        driver_probe_snapshots=probes,
        driver_capabilities={"driver:legacy": ("tool:invoke",)},
        driver_versions={"driver:legacy": "0.1.0"},
    )

    assert isinstance(document, OSPlanDocument)
    assert document.plan.scope_ref == scope_ref
    assert document.plan.driver_exposures[0].capabilities == ("tool:invoke",)
    assert os_plan_from_dict(document.to_dict()) == document
    Draft202012Validator(kernel_schema_v2()).validate(document.to_dict())


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({}, "kernel_plan_version_missing"),
        ({"plan_version": "pheroos-kernel-plan-v999"},
         "kernel_plan_version_unsupported"),
        ({"plan_version": "pheroos-driver-descriptor-v2"},
         "kernel_plan_version_unsupported"),
    ],
)
def test_kernel_authoritative_reader_fails_closed_on_missing_unknown_or_cross_version(
    payload: dict[str, object],
    code: str,
) -> None:
    with pytest.raises(KernelPlanVersionError) as raised:
        os_plan_from_dict(payload)

    assert raised.value.code == code
