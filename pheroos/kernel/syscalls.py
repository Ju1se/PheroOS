from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pheroos._immutable import abi_value_is_frozen, freeze_abi_value
from pheroos.kernel._validation import (
    is_nonblank_text,
    validate_runtime_context,
)
from pheroos.drivers import DriverResult
from pheroos.drivers.errors import DriverError
from pheroos.drivers.invocation import (
    DRIVER_INVOCATION_VERSION,
    DriverInvocationLedger,
    driver_request_digest,
    driver_result_digest,
)
from pheroos.kernel.errors import KernelError
from pheroos.kernel.os_plan import DriverExposure, ToolExposure
from pheroos.kernel.runtime_context import RuntimeContext


@dataclass(frozen=True)
class DriverInvokeRequest:
    driver_id: str
    scope_ref: str = ""
    invocation_id: str = ""
    operation: str = ""
    capability: str = ""
    idempotency_key: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)
    request_digest: str = ""
    version: str = DRIVER_INVOCATION_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_abi_value(self.payload))
        identities = (
            self.driver_id,
            self.scope_ref,
            self.invocation_id,
            self.operation,
            self.capability,
            self.idempotency_key,
        )
        if not self.request_digest and all(
            is_nonblank_text(item) for item in identities
        ):
            object.__setattr__(
                self,
                "request_digest",
                driver_request_digest(
                    scope_ref=self.scope_ref,
                    invocation_id=self.invocation_id,
                    driver_id=self.driver_id,
                    operation=self.operation,
                    capability=self.capability,
                    idempotency_key=self.idempotency_key,
                    payload=self.payload,
                ),
            )


@dataclass(frozen=True)
class DriverInvokeReply:
    request: DriverInvokeRequest
    result: DriverResult
    version: str = DRIVER_INVOCATION_VERSION


class KernelSyscalls:
    def __init__(self, invocation_ledger: DriverInvocationLedger | None = None) -> None:
        self._invocation_ledger = invocation_ledger or DriverInvocationLedger()

    def expose_driver(
        self,
        context: RuntimeContext,
        driver_id: str,
        *,
        operation: str | None = None,
        capability: str | None = None,
    ) -> DriverExposure:
        validate_runtime_context(context)
        if not is_nonblank_text(driver_id):
            raise KernelError("driver id is required")
        if not context.ready:
            raise KernelError("runtime context is not ready")
        for exposure in context.driver_exposures:
            if exposure.driver_id == driver_id:
                if not exposure.permissions:
                    raise KernelError(
                        f"driver exposure has no granted permissions: {driver_id}"
                    )
                if operation is not None and operation not in exposure.permissions:
                    raise KernelError(
                        f"driver operation is not granted by the active context: {operation}"
                    )
                if capability is not None and capability not in exposure.capabilities:
                    raise KernelError(
                        f"driver capability is not exposed by the active context: {capability}"
                    )
                return exposure
        raise KernelError(
            f"driver is not exposed by the active runtime context: {driver_id}"
        )

    def expose_tool(self, context: RuntimeContext, tool_id: str) -> ToolExposure:
        validate_runtime_context(context)
        if not is_nonblank_text(tool_id):
            raise KernelError("tool id is required")
        if not context.ready:
            raise KernelError("runtime context is not ready")
        for exposure in context.tool_exposures:
            if exposure.tool_id == tool_id:
                if not exposure.permissions:
                    raise KernelError(
                        f"tool exposure has no granted permissions: {tool_id}"
                    )
                return exposure
        raise KernelError(
            f"tool is not exposed by the active runtime context: {tool_id}"
        )

    def invoke_driver(
        self,
        context: RuntimeContext,
        request: DriverInvokeRequest,
        result: DriverResult,
    ) -> DriverInvokeReply:
        validate_runtime_context(context)
        _validate_driver_invoke_request(context, request)
        _validate_driver_result(result)
        self.expose_driver(
            context,
            request.driver_id,
            operation=request.operation,
            capability=request.capability,
        )
        _validate_driver_result_binding(request, result)
        self._record_driver_invocation(request, result)
        return DriverInvokeReply(request=request, result=result)

    def _record_driver_invocation(
        self,
        request: DriverInvokeRequest,
        result: DriverResult,
    ) -> None:
        try:
            self._invocation_ledger.record(
                scope_ref=request.scope_ref,
                driver_id=request.driver_id,
                idempotency_key=request.idempotency_key,
                request_digest=request.request_digest,
                result_digest=driver_result_digest(result),
            )
        except (DriverError, ValueError) as exc:
            raise KernelError(f"driver invocation idempotency conflict: {exc}") from exc


def _validate_driver_invoke_request(
    context: RuntimeContext,
    request: object,
) -> None:
    if not isinstance(request, DriverInvokeRequest):
        raise KernelError("driver invoke request is invalid")
    if request.version != DRIVER_INVOCATION_VERSION:
        raise KernelError("driver invoke request version is unsupported")
    for name, value in (
        ("id", request.driver_id),
        ("scope_ref", request.scope_ref),
        ("invocation id", request.invocation_id),
        ("operation", request.operation),
        ("capability", request.capability),
        ("idempotency key", request.idempotency_key),
        ("request digest", request.request_digest),
    ):
        if not is_nonblank_text(value):
            raise KernelError(f"driver invoke request {name} is required")
    if request.scope_ref != context.scope_ref:
        raise KernelError("driver invoke request scope does not match runtime context")
    if not isinstance(request.payload, Mapping) or not abi_value_is_frozen(
        request.payload
    ):
        raise KernelError("driver invoke request payload must be an immutable mapping")
    try:
        expected_digest = driver_request_digest(
            scope_ref=request.scope_ref,
            invocation_id=request.invocation_id,
            driver_id=request.driver_id,
            operation=request.operation,
            capability=request.capability,
            idempotency_key=request.idempotency_key,
            payload=request.payload,
        )
    except ValueError as exc:
        raise KernelError(f"driver invoke request is not canonical: {exc}") from exc
    if request.request_digest != expected_digest:
        raise KernelError("driver invoke request digest does not match its payload")


def _validate_driver_result(result: object) -> None:
    if not isinstance(result, DriverResult):
        raise KernelError("driver result is invalid")
    if result.invocation_version != DRIVER_INVOCATION_VERSION:
        raise KernelError("driver result invocation version is unsupported")
    if not is_nonblank_text(result.driver_id):
        raise KernelError("driver result id is required")
    if not isinstance(result.ok, bool):
        raise KernelError("driver result status must be boolean")
    if not isinstance(result.payload, Mapping) or not abi_value_is_frozen(
        result.payload
    ):
        raise KernelError("driver result payload must be an immutable mapping")


def _validate_driver_result_binding(
    request: DriverInvokeRequest,
    result: DriverResult,
) -> None:
    bindings = (
        (
            result.driver_id,
            request.driver_id,
            "driver result does not match syscall request",
        ),
        (
            result.scope_ref,
            request.scope_ref,
            "driver result scope does not match syscall request",
        ),
        (
            result.invocation_id,
            request.invocation_id,
            "driver result invocation does not match syscall request",
        ),
        (
            result.operation,
            request.operation,
            "driver result operation does not match syscall request",
        ),
        (
            result.request_digest,
            request.request_digest,
            "driver result digest does not match syscall request",
        ),
    )
    for observed, expected, message in bindings:
        if observed != expected:
            raise KernelError(message)
    if not is_nonblank_text(result.provenance):
        raise KernelError("driver result provenance is required")
