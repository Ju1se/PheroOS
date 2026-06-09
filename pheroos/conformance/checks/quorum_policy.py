from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.models import CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    candidates = {candidate.id: candidate for candidate in manifest.protocol.candidates}
    fallback = candidates.get(manifest.protocol.quorum_policy.fallback_candidate)
    ok = fallback is not None and fallback.safe_fallback
    return CheckResult("quorum_policy", ok, "" if ok else "fallback candidate must be declared and safe")
