from __future__ import annotations

import json

from pheroos.conformance import load_commit_tck_vectors, run_commit_tck


CASES = {
    3: "critical_counterevidence",
    11: "attention_channel_separation",
    12: "first_ready_pending",
    13: "stable_evidence_commit",
    18: "deadline_terminal",
    20: "declared_safe_fallback",
    32: "current_publication_gate",
    34: "no_assurance_downgrade",
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
        raise SystemExit(f"Hybrid Commit reference failed: {failures}")
    payload = {
        CASES[item.matrix_case]: {
            "case": item.matrix_case,
            "metrics": item.actual["metrics"],
            "progress": item.actual["progress"],
            "outcome": item.actual["outcome"],
            "certificate": item.actual["certificate"],
            "trace_sequence": item.actual["trace_sequence"],
            "failure_code": item.actual["failure_code"],
        }
        for item in report.results
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
