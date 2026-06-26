from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.models import CapabilityManifest, DriverSpec


def check(manifest: CapabilityManifest) -> CheckResult:
    problems: list[str] = []
    for index, driver in enumerate(manifest.drivers):
        if not driver_id(driver) or not driver_kind(driver) or not driver_version(driver):
            problems.append(f"{index}:identity")
        if not driver_capabilities(driver):
            problems.append(f"{index}:capabilities")
        if not driver_permissions(driver):
            problems.append(f"{index}:permissions")
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


def driver_capabilities(driver: DriverSpec | dict[str, object]) -> list[str]:
    if isinstance(driver, DriverSpec):
        return [capability for capability in driver.capabilities if capability]
    return text_list(driver.get("capabilities"))


def driver_permissions(driver: DriverSpec | dict[str, object]) -> list[str]:
    if isinstance(driver, DriverSpec):
        return [permission for permission in driver.permissions if permission]
    return text_list(driver.get("permissions"))


def text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
