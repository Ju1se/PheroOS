import pytest

from pheroos.kernel import DriverExposure, OSPlan, PermissionGrant, RuntimeMaterializer, ToolExposure
from pheroos.kernel.errors import KernelError


def test_materializer_exposes_only_permissioned_resources_from_ready_plan() -> None:
    plan = OSPlan(
        tenant_id="tenant-a",
        request_id="req-1",
        permission_grants=[PermissionGrant(capability_id="toy", permission="tool:use")],
        driver_exposures=[
            DriverExposure(driver_id="driver:allowed", capability_id="toy", permissions=["driver:invoke"]),
            DriverExposure(driver_id="driver:hidden", capability_id="toy"),
        ],
        tool_exposures=[
            ToolExposure(tool_id="tool:allowed", capability_id="toy", permissions=["tool:use"]),
            ToolExposure(tool_id="tool:hidden", capability_id="toy", permissions=[]),
        ],
    )

    context = RuntimeMaterializer().materialize(plan)

    assert [driver.driver_id for driver in context.driver_exposures] == ["driver:allowed"]
    assert [tool.tool_id for tool in context.tool_exposures] == ["tool:allowed"]
    assert context.ready is True


def test_materializer_exposes_no_callable_resources_from_not_ready_plan() -> None:
    plan = OSPlan(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[DriverExposure(driver_id="driver:toy", capability_id="toy", permissions=["driver:invoke"])],
        tool_exposures=[ToolExposure(tool_id="tool:allowed", capability_id="toy", permissions=["tool:use"])],
        runtime_ready=False,
        degraded=True,
    )

    context = RuntimeMaterializer().materialize(plan)

    assert context.driver_exposures == ()
    assert context.tool_exposures == ()
    assert context.ready is False
    assert context.degraded is True


def test_plan_and_materialized_context_snapshot_authority_collections() -> None:
    caller_permissions = ["driver:invoke"]
    caller_grants = [
        PermissionGrant(capability_id="toy", permission="driver:invoke")
    ]
    caller_exposures = [
        DriverExposure(
            driver_id="driver:toy",
            capability_id="toy",
            permissions=caller_permissions,
        )
    ]
    plan = OSPlan(
        tenant_id="tenant-a",
        request_id="req-1",
        permission_grants=caller_grants,
        driver_exposures=caller_exposures,
    )

    caller_permissions.append("driver:admin")
    caller_grants.append(
        PermissionGrant(capability_id="toy", permission="driver:admin")
    )
    caller_exposures.append(
        DriverExposure(
            driver_id="driver:forged",
            capability_id="toy",
            permissions=["driver:invoke"],
        )
    )
    context = RuntimeMaterializer().materialize(plan)
    object.__setattr__(
        plan.driver_exposures[0],
        "permissions",
        ("driver:admin",),
    )

    assert plan.permission_grants == (
        PermissionGrant(capability_id="toy", permission="driver:invoke"),
    )
    assert [item.driver_id for item in plan.driver_exposures] == ["driver:toy"]
    assert context.permission_grants == plan.permission_grants
    assert context.driver_exposures[0].permissions == ("driver:invoke",)
    with pytest.raises(AttributeError):
        context.driver_exposures.append(plan.driver_exposures[0])


def test_materializer_rejects_mutable_collection_bypass() -> None:
    plan = OSPlan(
        tenant_id="tenant-a",
        request_id="req-1",
        driver_exposures=[
            DriverExposure(
                driver_id="driver:toy",
                capability_id="toy",
                permissions=["driver:invoke"],
            )
        ],
    )
    object.__setattr__(plan, "driver_exposures", list(plan.driver_exposures))

    with pytest.raises(KernelError, match="must be immutable"):
        RuntimeMaterializer().materialize(plan)


@pytest.mark.parametrize(
    "plan",
    [
        OSPlan(tenant_id="   ", request_id="req-1"),
        OSPlan(tenant_id="tenant-a", request_id="   "),
        OSPlan(
            tenant_id="tenant-a",
            request_id="req-1",
            driver_exposures=[
                DriverExposure(
                    driver_id="   ",
                    capability_id="toy",
                    permissions=["driver:invoke"],
                )
            ],
        ),
        OSPlan(
            tenant_id="tenant-a",
            request_id="req-1",
            tool_exposures=[
                ToolExposure(
                    tool_id="tool:toy",
                    capability_id="   ",
                    permissions=["tool:use"],
                )
            ],
        ),
        OSPlan(
            tenant_id="tenant-a",
            request_id="req-1",
            driver_exposures=[
                DriverExposure(
                    driver_id="driver:toy",
                    capability_id="toy",
                    permissions=["   "],
                )
            ],
        ),
    ],
)
def test_materializer_rejects_blank_authority_identities(plan: OSPlan) -> None:
    with pytest.raises(KernelError):
        RuntimeMaterializer().materialize(plan)
