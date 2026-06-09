from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.models import CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    required = {"block", "commit", "recovery", "output"}
    missing = sorted(required - set(manifest.protocol.trace_policy.required_events))
    return CheckResult("trace_contract", not missing, ", ".join(missing))
