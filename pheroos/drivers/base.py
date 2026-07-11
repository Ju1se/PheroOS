from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pheroos.drivers._immutable import freeze_abi_sequence, freeze_abi_value


@dataclass(frozen=True)
class DriverDescriptor:
    id: str
    kind: str
    version: str
    capabilities: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # A frozen dataclass does not freeze caller-owned containers. Snapshot
        # the public collection at construction so validation and registration
        # cannot be invalidated by a later mutation of the input list.
        object.__setattr__(self, "capabilities", freeze_abi_sequence(self.capabilities))


@dataclass(frozen=True)
class DriverRegistration:
    descriptor: DriverDescriptor
    registered: bool = True


@dataclass(frozen=True)
class DriverProbeResult:
    driver_id: str
    available: bool
    detail: str = ""


@dataclass(frozen=True)
class DriverBinding:
    driver_id: str
    tenant_id: str
    permissions: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "permissions", freeze_abi_sequence(self.permissions))


@dataclass(frozen=True)
class DriverHandle:
    binding: DriverBinding
    exposed: bool = False


@dataclass(frozen=True)
class DriverHealth:
    driver_id: str
    healthy: bool
    detail: str = ""


@dataclass(frozen=True)
class DriverResult:
    driver_id: str
    ok: bool
    payload: Mapping[str, Any] = field(default_factory=dict)
    provenance: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", freeze_abi_value(self.payload))
