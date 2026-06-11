from __future__ import annotations

from dataclasses import dataclass

from pheroos.drivers.base import DriverDescriptor


@dataclass(frozen=True)
class ToolDriverDescriptor(DriverDescriptor):
    invocation_schema: str = "json"
