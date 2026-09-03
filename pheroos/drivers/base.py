from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pheroos._scope import runtime_scope_ref
from pheroos._immutable import freeze_abi_sequence, freeze_abi_value
from pheroos.drivers._versions import DRIVER_INVOCATION_VERSION


@dataclass(frozen=True)
class DriverDescriptor:
    id: str
    kind: str
    version: str
    capabilities: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    config_ref: str = ""
    extensions: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # A frozen dataclass does not freeze caller-owned containers. Snapshot
        # the public collection at construction so validation and registration
        # cannot be invalidated by a later mutation of the input list.
        object.__setattr__(self, "capabilities", freeze_abi_sequence(self.capabilities))
        object.__setattr__(self, "permissions", freeze_abi_sequence(self.permissions))
        object.__setattr__(self, "extensions", freeze_abi_value(self.extensions))


@dataclass(frozen=True)
class DriverRegistration:
    descriptor: DriverDescriptor
    registered: bool = True


@dataclass(frozen=True)
class DriverProbeResult:
    driver_id: str
    available: bool
    detail: str = ""
    version: str = ""
    capabilities: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "capabilities", freeze_abi_sequence(self.capabilities))


# The readiness input is a durable snapshot supplied by an outer runtime.  Keep
# the established result name as the canonical class during the Draft ABI
# migration while exposing the more precise snapshot terminology by identity.
DriverProbeSnapshot = DriverProbeResult


@dataclass(frozen=True)
class DriverBinding:
    driver_id: str
    tenant_id: str
    run_id: str = "legacy"
    scope_ref: str = ""
    permissions: tuple[str, ...] = field(default_factory=tuple)
    capabilities: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if (
            isinstance(self.tenant_id, str)
            and self.tenant_id.strip()
            and isinstance(self.run_id, str)
            and self.run_id.strip()
            and not self.scope_ref
        ):
            object.__setattr__(
                self,
                "scope_ref",
                runtime_scope_ref(self.tenant_id, self.run_id),
            )
        object.__setattr__(self, "permissions", freeze_abi_sequence(self.permissions))
        object.__setattr__(self, "capabilities", freeze_abi_sequence(self.capabilities))


@dataclass(frozen=True)
class DriverHandle:
    binding: DriverBinding
    exposed: bool = False


@dataclass(frozen=True)
class DriverResult:
    driver_id: str
    ok: bool
    payload: Mapping[str, Any] = field(default_factory=dict)
    provenance: str = ""
    scope_ref: str = ""
    invocation_id: str = ""
    operation: str = ""
    request_digest: str = ""
    invocation_version: str = DRIVER_INVOCATION_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_abi_value(self.payload))
