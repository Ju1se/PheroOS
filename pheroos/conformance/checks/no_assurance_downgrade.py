from __future__ import annotations

from pheroos.conformance.checks._commit_tck_contract import check_commit_tck_cases
from pheroos.conformance.report import CheckResult
from pheroos.protocol import CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    return check_commit_tck_cases(
        manifest,
        check_name="no_assurance_downgrade",
        matrix_cases=(19, 24, 31, 34, 35, 36),
    )


__all__ = ["check"]
