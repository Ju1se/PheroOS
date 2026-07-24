from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.models import CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    targets = {target.id for target in manifest.protocol.targets}
    candidates = {candidate.id: candidate for candidate in manifest.protocol.candidates}
    problems: list[str] = []
    for recovery in manifest.protocol.recovery_protocols:
        problems.extend(
            target for target in recovery.trigger_targets if target not in targets
        )
        failure_candidate = candidates.get(recovery.failure_candidate)
        if recovery.failure_candidate and failure_candidate is None:
            problems.append(recovery.failure_candidate)
        if failure_candidate is not None and failure_candidate.target not in set(
            recovery.trigger_targets
        ):
            problems.append(f"{recovery.failure_candidate}:target")
    return CheckResult("recovery_policy", not problems, ", ".join(problems))
