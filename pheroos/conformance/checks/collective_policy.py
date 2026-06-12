from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.models import SUPPORTED_COLLECTIVE_MODES, CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.collective_decision_policy
    if policy is None:
        return CheckResult("collective_policy", True)
    problems: list[str] = []
    if policy.mode not in SUPPORTED_COLLECTIVE_MODES:
        problems.append("unsupported_mode")
    if policy.min_independent_scouts <= 0:
        problems.append("min_independent_scouts")
    if policy.quorum_threshold <= 0:
        problems.append("quorum_threshold")
    return CheckResult("collective_policy", not problems, ", ".join(problems))
