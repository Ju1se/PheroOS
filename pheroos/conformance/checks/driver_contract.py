from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.models import CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    problems = [
        str(index)
        for index, driver in enumerate(manifest.drivers)
        if not str(driver.get("id") or "").strip() or not str(driver.get("kind") or "").strip()
    ]
    return CheckResult("driver_contract", not problems, ", ".join(problems))
