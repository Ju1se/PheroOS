from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.models import CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.collective_decision_policy
    if policy is None:
        return CheckResult("safe_fallback_collective", True)
    candidates = {candidate.id: candidate for candidate in manifest.protocol.candidates}
    fallback = candidates.get(policy.fallback_candidate)
    ok = fallback is not None and fallback.safe_fallback
    return CheckResult("safe_fallback_collective", ok, "" if ok else "collective fallback must be declared and safe")
