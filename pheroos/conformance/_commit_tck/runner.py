from __future__ import annotations

"""Deterministic Commit TCK execution harness."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from pheroos.conformance._commit_tck.artifacts import (
    COMMIT_TCK_VERSION,
    load_commit_tck_vectors,
)
from pheroos.conformance._commit_tck.models import (
    CommitTckAdapter,
    CommitTckReport,
    CommitTckResult,
    CommitTckVector,
    json_result,
    request_from_vector,
    result,
    validate_expected_shape,
)
from pheroos.conformance._commit_tck.mutations import variant_vector


def run_commit_tck(
    vectors: Sequence[CommitTckVector] | None = None,
    *,
    adapter: CommitTckAdapter | None = None,
) -> CommitTckReport:
    # Imported lazily to keep the harness reusable with an external adapter
    # without loading Governance's reference implementation.
    if adapter is None:
        from pheroos.conformance._commit_tck.reference_adapter import (
            ReferenceCommitTckAdapter,
        )

        implementation: CommitTckAdapter = ReferenceCommitTckAdapter()
    else:
        implementation = adapter
    selected = tuple(vectors) if vectors is not None else load_commit_tck_vectors()
    results: list[CommitTckResult] = []
    for vector in selected:
        actual = _evaluate_adapter(implementation, vector)
        failures: list[str] = []
        if actual != vector.expected:
            failures.append("base")
        repeated = _evaluate_adapter(implementation, vector)
        if repeated != actual:
            failures.append("repeat")
        for mutation in vector.mutations:
            mutated = variant_vector(vector, mutation, permutation=False)
            observed = _evaluate_adapter(implementation, mutated)
            if observed != mutation["expected"]:
                failures.append(f"mutation:{mutation['id']}")
            repeated_mutation = _evaluate_adapter(implementation, mutated)
            if repeated_mutation != observed:
                failures.append(f"mutation-repeat:{mutation['id']}")
        for permutation in vector.permutations:
            permuted = variant_vector(vector, permutation, permutation=True)
            observed = _evaluate_adapter(implementation, permuted)
            if observed != permutation["expected"]:
                failures.append(f"permutation:{permutation['id']}")
            repeated_permutation = _evaluate_adapter(implementation, permuted)
            if repeated_permutation != observed:
                failures.append(f"permutation-repeat:{permutation['id']}")
        ok = not failures
        results.append(
            CommitTckResult(
                vector_id=vector.id,
                matrix_case=vector.matrix_case,
                ok=ok,
                expected=deepcopy(vector.expected),
                actual=deepcopy(actual),
                detail=(
                    ""
                    if ok
                    else "exact TCK result mismatch: " + ", ".join(failures)
                ),
                variant_failures=tuple(failures),
            )
        )
    return CommitTckReport(COMMIT_TCK_VERSION, tuple(results))


def _evaluate_adapter(
    adapter: CommitTckAdapter,
    vector: CommitTckVector,
) -> dict[str, Any]:
    try:
        request = request_from_vector(vector)
        actual = json_result(dict(adapter.evaluate(request)))
        validate_expected_shape(actual, label=f"actual result for {vector.id}")
        return actual
    except Exception as exc:
        return result(failure_code=f"exception:{type(exc).__name__}:{exc}")


__all__ = ["run_commit_tck"]
