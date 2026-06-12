from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.models import CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.collective_decision_policy
    if policy is None:
        return CheckResult("pheromone_policy", True)
    ok = 0 <= policy.pheromone_evaporation_rate <= 1
    return CheckResult("pheromone_policy", ok, "" if ok else "evaporation rate must be between 0 and 1")
