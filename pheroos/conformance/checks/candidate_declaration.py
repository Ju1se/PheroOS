from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.models import CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    target_ids = {target.id for target in manifest.protocol.targets}
    undeclared_targets = [candidate.id for candidate in manifest.protocol.candidates if candidate.target not in target_ids]
    return CheckResult("candidate_declaration", not undeclared_targets, ", ".join(undeclared_targets))
