from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pheroos.drivers import DriverResult
from pheroos.kernel.errors import KernelError
from pheroos.kernel.os_plan import DriverExposure, ToolExposure
from pheroos.kernel.runtime_context import RuntimeContext


@dataclass(frozen=True)
class DriverInvokeRequest:
    driver_id: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DriverInvokeReply:
    request: DriverInvokeRequest
    result: DriverResult


class KernelSyscalls:
    def expose_driver(self, context: RuntimeContext, driver_id: str) -> DriverExposure:
        for exposure in context.driver_exposures:
            if exposure.driver_id == driver_id:
                return exposure
        raise KernelError(f"driver is not exposed by the active runtime context: {driver_id}")

    def expose_tool(self, context: RuntimeContext, tool_id: str) -> ToolExposure:
        for exposure in context.tool_exposures:
            if exposure.tool_id == tool_id:
                return exposure
        raise KernelError(f"tool is not exposed by the active runtime context: {tool_id}")

    def invoke_driver(
        self,
        context: RuntimeContext,
        request: DriverInvokeRequest,
        result: DriverResult,
    ) -> DriverInvokeReply:
        self.expose_driver(context, request.driver_id)
        if result.driver_id != request.driver_id:
            raise KernelError("driver result does not match syscall request")
        return DriverInvokeReply(request=request, result=result)
