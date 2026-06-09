from __future__ import annotations

from pheroos.kernel.os_plan import OSPlan
from pheroos.kernel.runtime_context import RuntimeContext


class RuntimeMaterializer:
    """Materialize run-scoped resources allowed by an OSPlan."""

    def materialize(self, plan: OSPlan) -> RuntimeContext:
        allowed_tools = [
            exposure for exposure in plan.tool_exposures if exposure.permissions and plan.runtime_ready
        ]
        return RuntimeContext(
            tenant_id=plan.tenant_id,
            request_id=plan.request_id,
            permission_grants=[grant for grant in plan.permission_grants if grant.granted],
            driver_exposures=list(plan.driver_exposures) if plan.runtime_ready else [],
            tool_exposures=allowed_tools,
            ready=plan.runtime_ready,
            degraded=plan.degraded,
        )
