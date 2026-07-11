from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pheroos.kernel._immutable import abi_value_is_frozen, freeze_abi_value
from pheroos.kernel._validation import (
    is_nonblank_text,
    validate_runtime_context,
)
from pheroos.drivers import DriverResult
from pheroos.kernel.errors import KernelError
from pheroos.kernel.os_plan import DriverExposure, ToolExposure
from pheroos.kernel.runtime_context import RuntimeContext


@dataclass(frozen=True)
class DriverInvokeRequest:
    driver_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_abi_value(self.payload))


@dataclass(frozen=True)
class DriverInvokeReply:
    request: DriverInvokeRequest
    result: DriverResult


class KernelSyscalls:
    def expose_driver(self, context: RuntimeContext, driver_id: str) -> DriverExposure:
        validate_runtime_context(context)
        if not is_nonblank_text(driver_id):
            raise KernelError("driver id is required")
        if not context.ready:
            raise KernelError("runtime context is not ready")
        for exposure in context.driver_exposures:
            if exposure.driver_id == driver_id:
                if not exposure.permissions:
                    raise KernelError(f"driver exposure has no granted permissions: {driver_id}")
                return exposure
        raise KernelError(f"driver is not exposed by the active runtime context: {driver_id}")

    def expose_tool(self, context: RuntimeContext, tool_id: str) -> ToolExposure:
        validate_runtime_context(context)
        if not is_nonblank_text(tool_id):
            raise KernelError("tool id is required")
        if not context.ready:
            raise KernelError("runtime context is not ready")
        for exposure in context.tool_exposures:
            if exposure.tool_id == tool_id:
                if not exposure.permissions:
                    raise KernelError(f"tool exposure has no granted permissions: {tool_id}")
                return exposure
        raise KernelError(f"tool is not exposed by the active runtime context: {tool_id}")

    def invoke_driver(
        self,
        context: RuntimeContext,
        request: DriverInvokeRequest,
        result: DriverResult,
    ) -> DriverInvokeReply:
        if not isinstance(request, DriverInvokeRequest):
            raise KernelError("driver invoke request is invalid")
        if not is_nonblank_text(request.driver_id):
            raise KernelError("driver invoke request id is required")
        if not isinstance(request.payload, Mapping) or not abi_value_is_frozen(request.payload):
            raise KernelError("driver invoke request payload must be an immutable mapping")
        if not isinstance(result, DriverResult):
            raise KernelError("driver result is invalid")
        if not is_nonblank_text(result.driver_id):
            raise KernelError("driver result id is required")
        if not isinstance(result.ok, bool):
            raise KernelError("driver result status must be boolean")
        if not isinstance(result.payload, Mapping) or not abi_value_is_frozen(result.payload):
            raise KernelError("driver result payload must be an immutable mapping")
        self.expose_driver(context, request.driver_id)
        if result.driver_id != request.driver_id:
            raise KernelError("driver result does not match syscall request")
        if not is_nonblank_text(result.provenance):
            raise KernelError("driver result provenance is required")
        return DriverInvokeReply(request=request, result=result)
