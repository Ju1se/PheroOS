from __future__ import annotations

from pheroos.conformance.checks._commit_tck_contract import check_commit_tck_cases
from pheroos.conformance.report import CheckResult
from pheroos.protocol import CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    return check_commit_tck_cases(
        manifest,
        check_name="no_assurance_downgrade",
        # Case 35 is the former registry-shape probe.  The checked public
        # ABI/source boundary now owns that assertion after the retired swarm
        # checks were removed; the frozen TCK artifact remains unchanged.
        matrix_cases=(19, 24, 31, 34, 36),
    )


__all__ = ["check"]
