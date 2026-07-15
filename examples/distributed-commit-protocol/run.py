from __future__ import annotations

import json

from pheroos.conformance import load_commit_tck_vectors, run_commit_tck


CASES = {
    27: "byzantine_intersection",
    28: "insufficient_partition_quorum",
    29: "single_final_quorum",
    30: "certificate_conflict_freeze",
    31: "deadline_finality_unavailable",
}


def main() -> None:
    vectors = {
        vector.matrix_case: vector for vector in load_commit_tck_vectors()
    }
    report = run_commit_tck(tuple(vectors[case] for case in CASES))
    if not report.ok:
        failures = {
            item.matrix_case: item.detail
            for item in report.results
            if not item.ok
        }
        raise SystemExit(f"distributed commit reference failed: {failures}")
    print(
        json.dumps(
            {
                CASES[item.matrix_case]: {
                    "case": item.matrix_case,
                    "metrics": item.actual["metrics"],
                    "outcome": item.actual["outcome"],
                    "certificate": item.actual["certificate"],
                    "trace_sequence": item.actual["trace_sequence"],
                    "failure_code": item.actual["failure_code"],
                }
                for item in report.results
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
