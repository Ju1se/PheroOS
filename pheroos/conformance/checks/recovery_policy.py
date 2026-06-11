from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.models import CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    targets = {target.id for target in manifest.protocol.targets}
    candidates = {candidate.id for candidate in manifest.protocol.candidates}
    problems: list[str] = []
    for recovery in manifest.protocol.recovery_protocols:
        problems.extend(target for target in recovery.trigger_targets if target not in targets)
        if recovery.failure_candidate and recovery.failure_candidate not in candidates:
            problems.append(recovery.failure_candidate)
    return CheckResult("recovery_policy", not problems, ", ".join(problems))
