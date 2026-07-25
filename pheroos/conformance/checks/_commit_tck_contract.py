"""Shared exact-vector runner for active Optimal Commit conformance checks.

The individual checks select the adversarial matrix cases that prove their
invariant.  This helper delegates to the public TCK adapter and compares the
complete expected result; it does not duplicate governance algorithms or turn
exceptions into a passing result.
"""

from __future__ import annotations

from collections.abc import Iterable

from pheroos.conformance.report import CheckResult
from pheroos.protocol import CapabilityManifest


def check_commit_tck_cases(
    manifest: CapabilityManifest,
    *,
    check_name: str,
    matrix_cases: Iterable[int],
) -> CheckResult:
    """Run an exact, non-skippable subset of the checked-in Commit TCK."""

    if manifest.protocol.collective_commit_policy is None:
        # Commit checks are not selected for this profile.  Keeping the helper
        # total protects direct callers without treating an active feature as
        # not-applicable.
        return CheckResult(check_name, True, "commit profile not active")

    required = tuple(sorted(set(matrix_cases)))
    if not required:
        return CheckResult(check_name, False, "no TCK matrix cases declared")

    try:
        # Imported only when an active check executes.  The TCK includes a
        # conformance-registry adversarial vector, so keeping this edge lazy
        # prevents a runner -> checks -> TCK -> runner import cycle.
        from pheroos.conformance.commit_tck import (
            ReferenceCommitTckAdapter,
            load_commit_tck_vectors,
            run_commit_tck,
        )

        vectors = load_commit_tck_vectors()
    except Exception as exc:
        return CheckResult(
            check_name,
            False,
            f"TCK load failed: {type(exc).__name__}: {exc}",
        )

    by_case = {vector.matrix_case: vector for vector in vectors}
    missing = tuple(case for case in required if case not in by_case)
    if missing:
        return CheckResult(
            check_name,
            False,
            "missing TCK matrix cases: " + ", ".join(map(str, missing)),
        )
    wrong_operations = tuple(
        case
        for case in required
        if by_case[case].inputs.get("operation") != "matrix_case"
    )
    if wrong_operations:
        return CheckResult(
            check_name,
            False,
            "non-normative TCK operations for matrix cases: "
            + ", ".join(map(str, wrong_operations)),
        )

    report = run_commit_tck(
        tuple(by_case[case] for case in required),
        adapter=ReferenceCommitTckAdapter(),
    )
    failures = tuple(result for result in report.results if not result.ok)
    if failures:
        detail = "; ".join(
            f"case {result.matrix_case} ({result.vector_id}): "
            f"{result.detail or 'exact result mismatch'}"
            for result in failures
        )
        return CheckResult(check_name, False, detail)
    if tuple(result.matrix_case for result in report.results) != required:
        return CheckResult(check_name, False, "TCK result coverage mismatch")
    return CheckResult(
        check_name,
        True,
        "exact TCK cases: " + ", ".join(map(str, required)),
    )


__all__ = ["check_commit_tck_cases"]
