from __future__ import annotations

from pheroos.conformance.report import CheckResult
from pheroos.protocol.extensions import secret_like_paths
from pheroos.protocol.models import CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    problems = secret_like_paths(manifest)
    return CheckResult("extension_contract", not problems, ", ".join(problems))
