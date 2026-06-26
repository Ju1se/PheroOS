from pheroos.kernel import DriverExposure, OSPlan, PermissionGrant, RuntimeMaterializer, ToolExposure


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

    assert context.driver_exposures == []
    assert context.tool_exposures == []
    assert context.ready is False
    assert context.degraded is True
