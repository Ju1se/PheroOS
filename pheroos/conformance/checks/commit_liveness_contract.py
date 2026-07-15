from __future__ import annotations

from pheroos.conformance.checks._commit_tck_contract import check_commit_tck_cases
from pheroos.conformance.report import CheckResult
from pheroos.protocol import CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    return check_commit_tck_cases(
        manifest,
        check_name="commit_liveness_contract",
        matrix_cases=(18, 19, 20, 21, 31, 33),
    )


__all__ = ["check"]
