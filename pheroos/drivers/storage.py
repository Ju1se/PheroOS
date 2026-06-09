from __future__ import annotations

from dataclasses import dataclass

from pheroos.drivers.base import DriverDescriptor


@dataclass(frozen=True)
class StorageDriverDescriptor(DriverDescriptor):
    stores_trace: bool = True
