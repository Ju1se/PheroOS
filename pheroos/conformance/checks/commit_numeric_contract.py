from __future__ import annotations

from collections.abc import Callable

from pheroos.conformance.report import CheckResult
from pheroos.governance import (
    MAX_AUTHORITY_INTEGER,
    WEIGHT_SCALE,
    checked_add,
    checked_multiply,
    checked_subtract,
    ceil_scaled_count,
    multiply_scaled,
    require_authority_integer,
    require_scaled_integer,
    scaled_ratio,
)
from pheroos.governance.commit_numeric import (
    canonical_commit_payload,
    canonical_commit_set,
    commit_payload_fingerprint,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol import CapabilityManifest


_REFERENCE_SCHEMA = "pheroos-commit-conformance-vector-v1"
_REFERENCE_PROFILE = "pheroos-commit-integrity-v1"
_REFERENCE_CANONICAL = (
    '{"payload":{"ready":true,"target":"decision:collective","values":[1,2]},'
    '"profile":"pheroos-commit-integrity-v1",'
    '"schema":"pheroos-commit-conformance-vector-v1",'
    '"version":"pheroos-commit-wire-v1"}'
)
_REFERENCE_FINGERPRINT = (
    "sha256:2a3b605424d3a7d8faac671d1fc6626799e362ea116a11dc068f63104902df44"
)


def check(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.collective_commit_policy
    if policy is None:
        return CheckResult("commit_numeric_contract", True)

    problems: list[str] = []
    if policy.evidence_qualification.numeric_scale != WEIGHT_SCALE:
        problems.append("manifest_numeric_scale")

    reference = {
        "target": "decision:collective",
        "values": [1, 2],
        "ready": True,
    }
    reordered = {
        "ready": True,
        "values": [1, 2],
        "target": "decision:collective",
    }
    canonical_args = {
        "schema": _REFERENCE_SCHEMA,
        "profile": _REFERENCE_PROFILE,
    }
    canonical = canonical_commit_payload(reference, **canonical_args)
    if canonical != _REFERENCE_CANONICAL:
        problems.append("canonical_reference_vector")
    if canonical_commit_payload(reordered, **canonical_args) != _REFERENCE_CANONICAL:
        problems.append("canonical_object_key_order")
    if (
        commit_payload_fingerprint(reference, **canonical_args)
        != _REFERENCE_FINGERPRINT
    ):
        problems.append("fingerprint_reference_vector")
    if canonical_commit_set(("zeta", "alpha", "mu")) != (
        "mu",
        "zeta",
        "alpha",
    ):
        problems.append("canonical_set_order")

    reference_operations = {
        "multiply_scaled": multiply_scaled(900_000, 800_000),
        "ceil_scaled_count": ceil_scaled_count(7, 500_000),
        "scaled_ratio": scaled_ratio(1, 4),
        "zero_denominator_ratio": scaled_ratio(0, 0),
        "checked_add": checked_add(1, 2, -1),
        "checked_subtract": checked_subtract(1, 2),
        "checked_multiply": checked_multiply(-3, 2),
    }
    expected_operations = {
        "multiply_scaled": 720_000,
        "ceil_scaled_count": 4,
        "scaled_ratio": 250_000,
        "zero_denominator_ratio": 1_000_000,
        "checked_add": 2,
        "checked_subtract": -1,
        "checked_multiply": -6,
    }
    problems.extend(
        f"numeric_vector:{name}"
        for name, observed in reference_operations.items()
        if observed != expected_operations[name]
    )

    rejection_vectors: tuple[tuple[str, Callable[[], object]], ...] = (
        ("bool_scaled_integer", lambda: require_scaled_integer(True, "vector")),
        ("bool_authority_integer", lambda: require_authority_integer(False, "vector")),
        ("float_scaled_integer", lambda: require_scaled_integer(1.0, "vector")),
        (
            "float_canonical_payload",
            lambda: canonical_commit_payload(
                {"value": 0.5},
                **canonical_args,
            ),
        ),
        (
            "addition_overflow",
            lambda: checked_add(MAX_AUTHORITY_INTEGER, 1),
        ),
        (
            "multiplication_overflow",
            lambda: checked_multiply(MAX_AUTHORITY_INTEGER, 2),
        ),
        (
            "canonical_integer_overflow",
            lambda: canonical_commit_payload(
                {"value": MAX_AUTHORITY_INTEGER + 1},
                **canonical_args,
            ),
        ),
        (
            "duplicate_canonical_set",
            lambda: canonical_commit_set(("duplicate", "duplicate")),
        ),
    )
    problems.extend(
        f"rejection:{name}"
        for name, operation in rejection_vectors
        if not _rejects_with_governance_error(operation)
    )

    unique = sorted(set(problems))
    return CheckResult(
        "commit_numeric_contract",
        not unique,
        ", ".join(unique),
    )


def _rejects_with_governance_error(operation: Callable[[], object]) -> bool:
    try:
        operation()
    except GovernanceError:
        return True
    except Exception:
        return False
    return False


__all__ = ["check"]
