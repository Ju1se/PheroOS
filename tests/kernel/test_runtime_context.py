from pheroos.kernel import DriverExposure, OSPlan, PermissionGrant, RuntimeMaterializer, ToolExposure


def test_materializer_exposes_only_permissioned_tools_from_ready_plan() -> None:
    plan = OSPlan(
        tenant_id="tenant-a",
        request_id="req-1",
        permission_grants=[PermissionGrant(capability_id="toy", permission="tool:use")],
        driver_exposures=[DriverExposure(driver_id="driver:toy", capability_id="toy")],
        tool_exposures=[
            ToolExposure(tool_id="tool:allowed", capability_id="toy", permissions=["tool:use"]),
            ToolExposure(tool_id="tool:hidden", capability_id="toy", permissions=[]),
        ],
    )

    context = RuntimeMaterializer().materialize(plan)

    assert [tool.tool_id for tool in context.tool_exposures] == ["tool:allowed"]
    assert context.ready is True
