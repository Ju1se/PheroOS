from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.models import CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    target_ids = {target.id for target in manifest.protocol.targets}
    problems = duplicate_values(target.id for target in manifest.protocol.targets)
    problems.extend(duplicate_values(candidate.id for candidate in manifest.protocol.candidates))
    problems.extend(candidate.id for candidate in manifest.protocol.candidates if candidate.target not in target_ids)
    return CheckResult("candidate_declaration", not problems, ", ".join(problems))


def duplicate_values(values: object) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        text = str(value)
        if text in seen:
            duplicates.add(text)
        seen.add(text)
    return sorted(duplicates)
