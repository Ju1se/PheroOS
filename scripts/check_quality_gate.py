#!/usr/bin/env python3
"""Evaluate the fixed CI quality gate from GitHub Actions ``needs`` results."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import os
from typing import Any


CANONICAL_REPOSITORY = "Ju1se/PheroOS"
PROVENANCE_JOB = "provenance"
QUALITY_GATE_JOB = "quality-gate"
REQUIRED_VALIDATION_JOBS = (
    "python-tests",
    "lint-and-typing",
    "schema-version-drift",
    "public-abi-shape-drift",
    "manifest-negative",
    "tck-v1-legacy",
    "tck-v2-reference",
    "tck-v2-independent",
    "external-adapter-adversarial",
    "consumer-compat",
    "scope-concurrency-lifecycle",
    "authority-restart-atomicity",
    "wheel-sdist-external-cwd",
    "import-dag-and-cold-import",
    "reference-performance",
    "supply-chain",
    "engineering-baseline",
    "coverage-measure",
    "coverage-gate",
    "authority-mutation",
)


def _result_for(needs: Mapping[str, object], job: str) -> str | None:
    value = needs.get(job)
    if not isinstance(value, Mapping):
        return None
    result = value.get("result")
    return result if isinstance(result, str) else None


def evaluate_quality_gate(
    needs: Mapping[str, object],
    *,
    event_name: str,
    ref: str,
    repository: str,
) -> list[str]:
    """Return failures for a closed, event-aware quality-gate decision."""

    failures: list[str] = []
    expected_jobs = set(REQUIRED_VALIDATION_JOBS) | {PROVENANCE_JOB}
    observed_jobs = set(needs)
    missing = expected_jobs - observed_jobs
    unclassified = observed_jobs - expected_jobs
    if missing:
        failures.append(f"quality-gate needs are missing jobs: {sorted(missing)}")
    if unclassified:
        failures.append(
            f"quality-gate needs contain unclassified jobs: {sorted(unclassified)}"
        )

    for job in REQUIRED_VALIDATION_JOBS:
        result = _result_for(needs, job)
        if result != "success":
            failures.append(
                f"validation job {job!r} must be success, observed {result!r}"
            )

    trusted_main = (
        event_name == "push"
        and ref == "refs/heads/main"
        and repository == CANONICAL_REPOSITORY
    )
    untrusted_context = event_name == "pull_request" or (
        event_name == "push"
        and ref == "refs/heads/main"
        and repository != CANONICAL_REPOSITORY
    )
    if not trusted_main and not untrusted_context:
        failures.append(
            "unsupported quality-gate event context: "
            f"event={event_name!r}, ref={ref!r}, repository={repository!r}"
        )
    else:
        expected_provenance = "success" if trusted_main else "skipped"
        observed_provenance = _result_for(needs, PROVENANCE_JOB)
        if observed_provenance != expected_provenance:
            failures.append(
                f"{PROVENANCE_JOB} must be {expected_provenance} in this context, "
                f"observed {observed_provenance!r}"
            )
    return failures


def _load_needs(raw: str) -> Mapping[str, object]:
    parsed: Any = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("quality-gate needs JSON must be an object")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--needs-json",
        default=os.environ.get("QUALITY_GATE_NEEDS", ""),
    )
    parser.add_argument(
        "--event-name",
        default=os.environ.get("GITHUB_EVENT_NAME", ""),
    )
    parser.add_argument("--ref", default=os.environ.get("GITHUB_REF", ""))
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
    )
    args = parser.parse_args(argv)
    try:
        needs = _load_needs(args.needs_json)
    except (json.JSONDecodeError, ValueError) as error:
        print(f"FAIL: {error}")
        return 1

    failures = evaluate_quality_gate(
        needs,
        event_name=args.event_name,
        ref=args.ref,
        repository=args.repository,
    )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("quality-gate policy satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
