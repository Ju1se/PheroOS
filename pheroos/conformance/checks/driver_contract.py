from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.models import CapabilityManifest, DriverSpec


def check(manifest: CapabilityManifest) -> CheckResult:
    problems = [
        str(index)
        for index, driver in enumerate(manifest.drivers)
        if not driver_id(driver) or not driver_kind(driver) or not driver_version(driver)
    ]
    return CheckResult("driver_contract", not problems, ", ".join(problems))


def driver_id(driver: DriverSpec | dict[str, object]) -> str:
    if isinstance(driver, DriverSpec):
        return driver.id.strip()
    return str(driver.get("id") or "").strip()


def driver_kind(driver: DriverSpec | dict[str, object]) -> str:
    if isinstance(driver, DriverSpec):
        return driver.kind.strip()
    return str(driver.get("kind") or "").strip()


def driver_version(driver: DriverSpec | dict[str, object]) -> str:
    if isinstance(driver, DriverSpec):
        return driver.version.strip()
    return str(driver.get("version") or "").strip()
