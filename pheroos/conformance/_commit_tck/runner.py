"""Deterministic Commit TCK execution harness."""

from __future__ import annotations

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
    results = [_run_vector(implementation, vector) for vector in selected]
    return CommitTckReport(COMMIT_TCK_VERSION, tuple(results))


def _run_vector(
    implementation: CommitTckAdapter,
    vector: CommitTckVector,
) -> CommitTckResult:
    actual = _evaluate_adapter(implementation, vector)
    failures: list[str] = []
    if actual != vector.expected:
        failures.append("base")
    if _evaluate_adapter(implementation, vector) != actual:
        failures.append("repeat")
    _record_variant_failures(
        implementation,
        vector,
        vector.mutations,
        permutation=False,
        failures=failures,
    )
    _record_variant_failures(
        implementation,
        vector,
        vector.permutations,
        permutation=True,
        failures=failures,
    )
    ok = not failures
    return CommitTckResult(
        vector_id=vector.id,
        matrix_case=vector.matrix_case,
        ok=ok,
        expected=deepcopy(vector.expected),
        actual=deepcopy(actual),
        detail="" if ok else "exact TCK result mismatch: " + ", ".join(failures),
        variant_failures=tuple(failures),
    )


def _record_variant_failures(
    implementation: CommitTckAdapter,
    vector: CommitTckVector,
    variants: Sequence[Mapping[str, Any]],
    *,
    permutation: bool,
    failures: list[str],
) -> None:
    kind = "permutation" if permutation else "mutation"
    for variant in variants:
        varied = variant_vector(vector, variant, permutation=permutation)
        observed = _evaluate_adapter(implementation, varied)
        if observed != variant["expected"]:
            failures.append(f"{kind}:{variant['id']}")
        if _evaluate_adapter(implementation, varied) != observed:
            failures.append(f"{kind}-repeat:{variant['id']}")


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
