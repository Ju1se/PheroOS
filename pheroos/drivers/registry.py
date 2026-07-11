from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from pheroos.drivers.base import DriverDescriptor
from pheroos.drivers.errors import DriverError
from pheroos.drivers.lifecycle import register as register_driver


class DriverRegistry:
    """Validated descriptor registry with detached read-only inspection."""

    def __init__(
        self,
        descriptors: Mapping[str, DriverDescriptor] | None = None,
    ) -> None:
        self.__descriptors: dict[str, DriverDescriptor] = {}
        for driver_id, descriptor in (descriptors or {}).items():
            registration = register_driver(descriptor)
            if driver_id != registration.descriptor.id:
                raise DriverError("driver registry key does not match descriptor id")
            self.__descriptors[driver_id] = registration.descriptor

    @property
    def descriptors(self) -> Mapping[str, DriverDescriptor]:
        return MappingProxyType(
            {
                driver_id: register_driver(descriptor).descriptor
                for driver_id, descriptor in self.__descriptors.items()
            }
        )

    def register(self, descriptor: DriverDescriptor) -> None:
        registration = register_driver(descriptor)
        self.__descriptors[registration.descriptor.id] = registration.descriptor

    def get(self, driver_id: str) -> DriverDescriptor:
        try:
            descriptor = self.__descriptors[driver_id]
        except KeyError as exc:
            raise DriverError(f"unknown driver: {driver_id}") from exc
        return register_driver(descriptor).descriptor
