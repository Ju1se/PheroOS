from __future__ import annotations

from dataclasses import dataclass

from pheroos.drivers.base import DriverDescriptor


@dataclass(frozen=True)
class DataProviderDriverDescriptor(DriverDescriptor):
    result_schema: str = "pheroos.driver.result.v1"
