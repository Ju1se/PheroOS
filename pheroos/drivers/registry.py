from __future__ import annotations

from dataclasses import dataclass, field

from pheroos.drivers.base import DriverDescriptor
from pheroos.drivers.errors import DriverError


@dataclass
class DriverRegistry:
    descriptors: dict[str, DriverDescriptor] = field(default_factory=dict)

    def register(self, descriptor: DriverDescriptor) -> None:
        if not descriptor.id:
            raise DriverError("driver id is required")
        self.descriptors[descriptor.id] = descriptor

    def get(self, driver_id: str) -> DriverDescriptor:
        try:
            return self.descriptors[driver_id]
        except KeyError as exc:
            raise DriverError(f"unknown driver: {driver_id}") from exc
