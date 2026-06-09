from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DriverDescriptor:
    id: str
    kind: str
    version: str
    capabilities: list[str] = field(default_factory=list)


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
    permissions: list[str] = field(default_factory=list)


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
    payload: dict[str, Any] = field(default_factory=dict)
    provenance: str = ""
