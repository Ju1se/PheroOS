from __future__ import annotations

from pheroos.kernel._validation import validate_os_plan
from pheroos.kernel.os_plan import OSPlan
from pheroos.kernel.runtime_context import RuntimeContext


class RuntimeMaterializer:
    """Materialize run-scoped resources allowed by an OSPlan."""

    def materialize(self, plan: OSPlan) -> RuntimeContext:
        validate_os_plan(plan)
        allowed_drivers = [
            exposure for exposure in plan.driver_exposures if exposure.permissions and plan.runtime_ready
        ]
        allowed_tools = [
            exposure for exposure in plan.tool_exposures if exposure.permissions and plan.runtime_ready
        ]
        return RuntimeContext(
            tenant_id=plan.tenant_id,
            request_id=plan.request_id,
            permission_grants=[grant for grant in plan.permission_grants if grant.granted],
            driver_exposures=allowed_drivers,
            tool_exposures=allowed_tools,
            ready=plan.runtime_ready,
            degraded=plan.degraded,
        )
