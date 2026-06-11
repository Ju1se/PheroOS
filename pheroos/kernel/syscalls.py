from __future__ import annotations

from pheroos.kernel.errors import KernelError
from pheroos.kernel.os_plan import ToolExposure
from pheroos.kernel.runtime_context import RuntimeContext


class KernelSyscalls:
    def expose_tool(self, context: RuntimeContext, tool_id: str) -> ToolExposure:
        for exposure in context.tool_exposures:
            if exposure.tool_id == tool_id:
                return exposure
        raise KernelError(f"tool is not exposed by the active runtime context: {tool_id}")
