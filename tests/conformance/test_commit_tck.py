from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from pheroos.conformance.commit_tck import (
    COMMIT_TCK_VERSION,
    CommitTckVector,
    ReferenceCommitTckAdapter,
    commit_tck_artifact_root,
    commit_tck_schema,
    load_commit_tck_vectors,
    run_commit_tck,
)


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "pheroos" / "conformance" / "tck" / "commit-integrity-v1.json"
SPLIT_DIRECTORY = ROOT / "tests" / "fixtures" / "commit-integrity" / "v1"


def expected(
    *,
    metrics: dict[str, object] | None = None,
    roots: dict[str, object] | None = None,
    progress: object = None,
    outcome: object = None,
    trace_sequence: list[str] | None = None,
    certificate: object = None,
    failure_code: str | None = None,
) -> dict[str, object]:
    return {
        "metrics": metrics or {},
        "roots": roots or {},
        "progress": progress,
        "outcome": outcome,
        "trace_sequence": trace_sequence or [],
        "certificate": certificate,
        "failure_code": failure_code,
    }


def vector(
    *,
    vector_id: str,
    matrix_case: int,
    inputs: dict[str, object],
    result: dict[str, object],
) -> CommitTckVector:
    return CommitTckVector(
        id=vector_id,
        tck_version=COMMIT_TCK_VERSION,
        matrix_case=matrix_case,
        title=vector_id,
        manifest=None,
        profile="pheroos-commit-integrity-v1",
        prior_authoritative_state={},
        inputs=inputs,
        expected=result,
    )


def test_reference_tck_adapter_executes_public_numeric_and_terminal_functions() -> None:
    vectors = (
        vector(
            vector_id="fixed-point-floor",
            matrix_case=1,
            inputs={
                "operation": "fixed_point_multiply",
                "left": 750_001,
                "right": 500_001,
                "scale": 1_000_000,
            },
            result=expected(metrics={"value": 375_001}),
        ),
        vector(
            vector_id="terminal-priority",
            matrix_case=2,
            inputs={
                "operation": "terminal_priority",
                "invalid": False,
                "safety_violation": True,
                "blocked": True,
                "evidence_commit": True,
                "finality_unavailable": True,
                "deadline_reached": True,
                "deadline_outcome": "safe_fallback",
            },
            result=expected(outcome={"kind": "safety_violation"}),
        ),
    )

    report = run_commit_tck(vectors)

    assert report.ok is True
    assert [item.actual for item in report.results] == [
        item.expected for item in vectors
    ]


def test_tck_exact_comparison_catches_reference_drift() -> None:
    item = vector(
        vector_id="wrong-rounding",
        matrix_case=1,
        inputs={
            "operation": "fixed_point_multiply",
            "left": 750_001,
            "right": 500_001,
            "scale": 1_000_000,
        },
        result=expected(metrics={"value": 375_002}),
    )

    report = run_commit_tck((item,), adapter=ReferenceCommitTckAdapter())

    assert report.ok is False
    assert report.results[0].actual["metrics"] == {"value": 375_001}


@pytest.mark.parametrize("protocol_version", ["pheroos.protocol.v999", ""])
def test_tck_manifest_validation_fails_closed_for_unsupported_protocol_versions(
    protocol_version: str,
) -> None:
    base = load_commit_tck_vectors()[0]
    manifest = deepcopy(base.manifest)
    assert manifest is not None
    manifest["protocol"]["protocol_version"] = protocol_version
    item = replace(
        base,
        id="unsupported-protocol-version",
        manifest=manifest,
        inputs={"operation": "manifest_validation"},
        expected=expected(failure_code="load:ValueError"),
        mutations=(),
        permutations=(),
    )

    report = run_commit_tck((item,))

    assert report.ok is True
    assert report.results[0].actual["failure_code"] == "load:ValueError"


def test_tck_adapter_receives_only_a_fresh_input_request() -> None:
    item = vector(
        vector_id="adapter-input-only",
        matrix_case=17,
        inputs={
            "operation": "canonical_set_fingerprint",
            "schema": "tck-canonical-set-v1",
            "values": [{"id": "b"}, {"id": "a"}],
        },
        result=expected(
            roots={
                "fingerprint": "sha256:e85ef9c1e93ddb2ddf10294a23d16a127ee294d30010b5c64c9cc57cfd3661d4"
            },
            outcome={"canonical_values": [{"id": "a"}, {"id": "b"}]},
        ),
    )

    class InspectingAdapter:
        def __init__(self) -> None:
            self.reference = ReferenceCommitTckAdapter()
            self.requests: list[object] = []

        def evaluate(self, request: object) -> dict[str, object]:
            assert getattr(request, "request_version") == (
                "pheroos-commit-tck-request-v2"
            )
            assert not hasattr(request, "expected")
            assert not hasattr(request, "mutations")
            assert not hasattr(request, "permutations")
            self.requests.append(request)
            result = dict(self.reference.evaluate(request))  # type: ignore[arg-type]
            getattr(request, "inputs")["values"].append({"id": "forged"})
            return result

    adapter = InspectingAdapter()
    report = run_commit_tck((item,), adapter=adapter)

    assert report.ok is True
    assert len(adapter.requests) == 2
    assert adapter.requests[0] is not adapter.requests[1]
    assert item.inputs["values"] == [{"id": "b"}, {"id": "a"}]
    assert item.expected["outcome"] == {"canonical_values": [{"id": "a"}, {"id": "b"}]}


def test_tck_rejects_an_adapter_that_echoes_harness_expected() -> None:
    item = vector(
        vector_id="expected-echo-isolation",
        matrix_case=1,
        inputs={
            "operation": "fixed_point_multiply",
            "left": 2,
            "right": 3,
            "scale": 1,
        },
        result=expected(metrics={"value": 6}),
    )

    class EchoExpectedAdapter:
        def evaluate(self, request: object) -> dict[str, object]:
            return getattr(request, "expected")

    report = run_commit_tck((item,), adapter=EchoExpectedAdapter())

    assert report.ok is False
    assert report.results[0].variant_failures == ("base",)
    assert (
        report.results[0].actual["failure_code"].startswith("exception:AttributeError:")
    )


def test_tck_rejects_a_constant_base_pass_for_a_mutated_request() -> None:
    base = vector(
        vector_id="constant-pass-isolation",
        matrix_case=1,
        inputs={
            "operation": "fixed_point_multiply",
            "left": 2,
            "right": 3,
            "scale": 1,
        },
        result=expected(metrics={"value": 6}),
    )
    item = replace(
        base,
        mutations=(
            {
                "id": "change-right-operand",
                "authority_namespace": "isolated",
                "path": ["inputs", "right"],
                "replacement": 4,
                "expected": expected(metrics={"value": 8}),
            },
        ),
    )

    class ConstantBaseAdapter:
        def evaluate(self, _request: object) -> dict[str, object]:
            return deepcopy(base.expected)

    report = run_commit_tck((item,), adapter=ConstantBaseAdapter())

    assert report.ok is False
    assert report.results[0].actual == base.expected
    assert report.results[0].variant_failures == ("mutation:change-right-operand",)


def test_tck_executes_declared_mutations_and_permutations_exactly() -> None:
    base = vector(
        vector_id="canonical-set-variants",
        matrix_case=17,
        inputs={
            "operation": "canonical_set_fingerprint",
            "schema": "tck-canonical-set-v1",
            "values": [{"id": "b"}, {"id": "a"}],
        },
        result=expected(
            roots={
                "fingerprint": "sha256:e85ef9c1e93ddb2ddf10294a23d16a127ee294d30010b5c64c9cc57cfd3661d4"
            },
            outcome={"canonical_values": [{"id": "a"}, {"id": "b"}]},
        ),
    )
    item = replace(
        base,
        mutations=(
            {
                "id": "replace-first-id",
                "authority_namespace": "isolated",
                "path": ["inputs", "values", 0, "id"],
                "replacement": "c",
                "expected": expected(
                    roots={
                        "fingerprint": "sha256:f24f6734acfcf494ee979671b37b62389e1b27a4f78e860b7ac4295260890f0d"
                    },
                    outcome={"canonical_values": [{"id": "a"}, {"id": "c"}]},
                ),
            },
        ),
        permutations=(
            {
                "id": "reverse-values",
                "authority_namespace": "shared",
                "path": ["inputs", "values"],
                "order": "reverse",
                "expected": deepcopy(base.expected),
            },
        ),
    )

    report = run_commit_tck((item,))

    assert report.ok is True
    assert report.results[0].variant_failures == ()


def test_tck_repeats_base_mutation_and_permutation_without_result_cache() -> None:
    base = vector(
        vector_id="repeat-count",
        matrix_case=17,
        inputs={
            "operation": "canonical_set_fingerprint",
            "schema": "tck-canonical-set-v1",
            "values": [{"id": "b"}, {"id": "a"}],
        },
        result=expected(
            roots={
                "fingerprint": "sha256:e85ef9c1e93ddb2ddf10294a23d16a127ee294d30010b5c64c9cc57cfd3661d4"
            },
            outcome={"canonical_values": [{"id": "a"}, {"id": "b"}]},
        ),
    )
    item = replace(
        base,
        mutations=(
            {
                "id": "replace-first-id",
                "authority_namespace": "isolated",
                "path": ["inputs", "values", 0, "id"],
                "replacement": "c",
                "expected": expected(
                    roots={
                        "fingerprint": "sha256:f24f6734acfcf494ee979671b37b62389e1b27a4f78e860b7ac4295260890f0d"
                    },
                    outcome={"canonical_values": [{"id": "a"}, {"id": "c"}]},
                ),
            },
        ),
        permutations=(
            {
                "id": "reverse-values",
                "authority_namespace": "shared",
                "path": ["inputs", "values"],
                "order": "reverse",
                "expected": deepcopy(base.expected),
            },
        ),
    )

    class CountingAdapter:
        def __init__(self) -> None:
            self.reference = ReferenceCommitTckAdapter()
            self.calls: Counter[tuple[str, str]] = Counter()

        def evaluate(self, selected: CommitTckVector) -> dict[str, object]:
            key = (
                selected.id,
                json.dumps(selected.inputs, sort_keys=True),
            )
            self.calls[key] += 1
            return dict(self.reference.evaluate(selected))

    adapter = CountingAdapter()
    report = run_commit_tck((item,), adapter=adapter)

    assert report.ok is True
    assert sorted(adapter.calls.values()) == [2, 2, 2]


def test_tck_loader_rejects_duplicate_json_keys_and_incomplete_result_shape(
    tmp_path: Path,
) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"tck_version":"pheroos-commit-integrity-tck-v1",'
        '"tck_version":"pheroos-commit-integrity-tck-v1","vectors":[]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate key"):
        load_commit_tck_vectors(duplicate)

    incomplete = tmp_path / "incomplete.json"
    payload = {
        "tck_version": COMMIT_TCK_VERSION,
        "vectors": [
            {
                "id": "incomplete",
                "tck_version": COMMIT_TCK_VERSION,
                "matrix_case": 1,
                "title": "incomplete",
                "manifest": None,
                "profile": "pheroos-commit-integrity-v1",
                "prior_authoritative_state": {},
                "inputs": {"operation": "fixed_point_ratio"},
                "expected": {"metrics": {}},
                "mutations": [],
                "permutations": [],
            }
        ],
    }
    incomplete.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="exact normative result fields"):
        load_commit_tck_vectors(incomplete)


def test_commit_tck_schema_matches_checked_in_artifact() -> None:
    checked_in = json.loads(
        (ROOT / "schemas" / "commit-tck.schema.json").read_text(encoding="utf-8")
    )

    assert checked_in == commit_tck_schema()
    vector = checked_in["properties"]["vectors"]["items"]
    assert vector["additionalProperties"] is False
    assert vector["properties"]["matrix_case"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 38,
    }


def test_checked_commit_tck_is_complete_split_and_uses_real_variants() -> None:
    raw = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    vectors = load_commit_tck_vectors()
    split = [
        json.loads(
            (SPLIT_DIRECTORY / f"case-{case:02d}.json").read_text(encoding="utf-8")
        )
        for case in range(1, 39)
    ]

    assert raw == {
        "tck_version": COMMIT_TCK_VERSION,
        "vectors": split,
    }
    assert tuple(item.matrix_case for item in vectors) == tuple(range(1, 39))
    assert all(item.inputs.get("operation") == "matrix_case" for item in vectors)
    assert vectors[-1].expected["roots"]["artifact_root"] == (
        commit_tck_artifact_root()
    )
    assert sum(len(item.mutations) for item in vectors) >= 7
    assert sum(len(item.permutations) for item in vectors) >= 1
    namespaces = {
        variant["authority_namespace"]
        for item in vectors
        for variant in (*item.mutations, *item.permutations)
    }
    assert namespaces == {"isolated", "shared"}


def test_checked_commit_tck_locks_no_downgrade_adversarial_semantics() -> None:
    vectors = {item.matrix_case: item for item in load_commit_tck_vectors()}

    assert vectors[9].expected["failure_code"] == "commit_risk_evidence_weakened"
    assert vectors[14].expected["outcome"]["all_reset"] is True
    assert vectors[15].expected["outcome"] == {
        "evidence_root_changed": True,
        "leader_continuous": True,
        "window_continued": True,
    }
    commit_roots = (
        "commit_truth_root",
        "commit_evidence_root",
        "commit_challenge_root",
        "commit_lease_root",
    )
    attention_mutation = vectors[11].mutations[0]["expected"]
    assert {key: vectors[11].expected["roots"][key] for key in commit_roots} == {
        key: attention_mutation["roots"][key] for key in commit_roots
    }
    assert vectors[17].permutations[0]["expected"] == vectors[17].expected
    assert all(
        mutation["expected"]["outcome"]["certificate_valid"] is False
        or mutation["expected"]["outcome"]["trace_valid"] is False
        for mutation in vectors[25].mutations
    )
    assert (
        vectors[34].mutations[0]["expected"]["certificate"]["verified_authoritative"]
        is False
    )
    assert (
        vectors[34].mutations[0]["expected"]["certificate"]["assurance_downgraded"]
        is False
    )
    assert vectors[36].expected["failure_code"] == ("commit_unknown_critical_extension")
    assert vectors[36].mutations[0]["expected"]["failure_code"] is not None


def test_checked_commit_tck_runs_twice_in_one_process_exactly() -> None:
    vectors = load_commit_tck_vectors()

    first = run_commit_tck(vectors)
    second = run_commit_tck(vectors)

    assert first.ok is True
    assert second == first
    assert all(item.variant_failures == () for item in first.results)


def test_commit_tck_generator_check_is_reproducible() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_commit_tck.py"),
            "--check",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
    assert "verified 38 Commit TCK vectors" in completed.stdout
