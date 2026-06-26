from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.models import CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    candidates = {candidate.id: candidate for candidate in manifest.protocol.candidates}
    fallback = candidates.get(manifest.protocol.quorum_policy.fallback_candidate)
    problems: list[str] = []
    if fallback is None:
        problems.append("fallback_missing")
    elif not fallback.safe_fallback:
        problems.append("fallback_not_safe")
    elif fallback.target != manifest.protocol.quorum_policy.target:
        problems.append("fallback_target_mismatch")
    return CheckResult("quorum_policy", not problems, ", ".join(problems))
