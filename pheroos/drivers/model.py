from __future__ import annotations

from dataclasses import dataclass

from pheroos.drivers.base import DriverDescriptor


@dataclass(frozen=True)
class ModelDriverDescriptor(DriverDescriptor):
    model_family: str = "generic"
