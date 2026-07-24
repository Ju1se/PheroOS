from __future__ import annotations

import json

from pheroos.conformance import load_commit_tck_vectors, run_commit_tck


CASES = (24, 25, 26)


def main() -> None:
    vectors = {vector.matrix_case: vector for vector in load_commit_tck_vectors()}
    report = run_commit_tck(tuple(vectors[case] for case in CASES))
    if not report.ok:
        failures = {
            item.matrix_case: item.detail for item in report.results if not item.ok
        }
        raise SystemExit(f"certificate replay reference failed: {failures}")
    print(
        json.dumps(
            {
                item.matrix_case: {
                    "certificate": item.actual["certificate"],
                    "roots": item.actual["roots"],
                    "outcome": item.actual["outcome"],
                    "failure_code": item.actual["failure_code"],
                    "variants_passed": not item.variant_failures,
                }
                for item in report.results
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
