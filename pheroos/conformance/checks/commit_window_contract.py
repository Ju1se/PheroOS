from __future__ import annotations

from pheroos.conformance.checks._commit_tck_contract import check_commit_tck_cases
from pheroos.conformance.report import CheckResult
from pheroos.protocol import CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    return check_commit_tck_cases(
        manifest,
        check_name="commit_window_contract",
        matrix_cases=(10, 12, 13, 14, 15, 16, 17),
    )


__all__ = ["check"]
