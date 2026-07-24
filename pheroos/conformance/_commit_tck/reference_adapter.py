"""Reference adapter and ABI probes for the Commit Integrity TCK.

Vectors contain only JSON values.  The reference adapter delegates every
operation to a public Protocol, Governance, or Trace ABI function; it never
reimplements commit scoring, liveness, certificate, or finality algorithms.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pheroos.conformance._commit_tck.artifacts import (
    COMMIT_TCK_ARTIFACT as _ARTIFACT_DEPENDENCY,  # noqa: F401
)
from pheroos.conformance._commit_tck.models import (
    CommitTckVector,
    json_result as _json_result,
    request_from_vector as _request_from_vector,
    validate_expected_shape as _validate_expected_shape,
)
from pheroos.conformance._commit_tck_reference import MATRIX_PROBES as _HANDLER_PROBES
from pheroos.conformance._commit_tck_reference import operations as _operations
from pheroos.conformance.commit_tck_v2_protocol import (
    CommitTckRequest as _CommitTckRequest,
)


class ReferenceCommitTckAdapter:
    """Reference adapter composed exclusively from public PheroOS ABI calls."""

    def __init__(self) -> None:
        self._operations: dict[str, Callable[[_CommitTckRequest], dict[str, Any]]] = {
            "canonical_fingerprint": self._canonical_fingerprint,
            "canonical_set_fingerprint": self._canonical_set_fingerprint,
            "fixed_point_multiply": self._fixed_point_multiply,
            "fixed_point_ratio": self._fixed_point_ratio,
            "manifest_validation": self._manifest_validation,
            "matrix_case": self._matrix_case,
            "terminal_priority": self._terminal_priority,
            "trace_replay": self._trace_replay,
        }

    def evaluate(
        self,
        request: _CommitTckRequest | CommitTckVector,
    ) -> Mapping[str, Any]:
        # Preserve direct v1 calls to the reference adapter without allowing
        # its implementation to consume harness-owned expected values.
        selected = (
            _request_from_vector(request)
            if isinstance(request, CommitTckVector)
            else request
        )
        operation = selected.inputs.get("operation")
        if not isinstance(operation, str) or operation not in self._operations:
            raise ValueError(
                f"TCK vector {selected.id} uses unsupported operation: {operation!r}"
            )
        actual = _json_result(self._operations[operation](selected))
        _validate_expected_shape(actual, label=f"actual result for {selected.id}")
        return actual

    def _canonical_fingerprint(self, vector: _CommitTckRequest) -> dict[str, Any]:
        return _operations._canonical_fingerprint(vector)

    def _canonical_set_fingerprint(self, vector: _CommitTckRequest) -> dict[str, Any]:
        return _operations._canonical_set_fingerprint(vector)

    def _fixed_point_multiply(self, vector: _CommitTckRequest) -> dict[str, Any]:
        return _operations._fixed_point_multiply(vector)

    def _fixed_point_ratio(self, vector: _CommitTckRequest) -> dict[str, Any]:
        return _operations._fixed_point_ratio(vector)

    def _manifest_validation(self, vector: _CommitTckRequest) -> dict[str, Any]:
        return _operations._manifest_validation(vector)

    def _terminal_priority(self, vector: _CommitTckRequest) -> dict[str, Any]:
        return _operations._terminal_priority(vector)

    def _trace_replay(self, vector: _CommitTckRequest) -> dict[str, Any]:
        return _operations._trace_replay(vector)

    def _matrix_case(self, vector: _CommitTckRequest) -> dict[str, Any]:
        probe = _MATRIX_PROBES.get(vector.matrix_case)
        if probe is None:
            raise ValueError(
                f"TCK matrix case {vector.matrix_case} has no reference ABI probe"
            )
        return probe(vector)


def _probe_case_01(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[1](vector)


def _probe_case_02(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[2](vector)


def _probe_case_03(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[3](vector)


def _probe_case_04(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[4](vector)


def _probe_case_05(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[5](vector)


def _probe_case_06(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[6](vector)


def _probe_case_07(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[7](vector)


def _probe_case_08(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[8](vector)


def _probe_case_09(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[9](vector)


def _probe_case_10(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[10](vector)


def _probe_case_11(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[11](vector)


def _probe_case_12(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[12](vector)


def _probe_case_13(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[13](vector)


def _probe_case_14(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[14](vector)


def _probe_case_15(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[15](vector)


def _probe_case_16(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[16](vector)


def _probe_case_17(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[17](vector)


def _probe_case_18(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[18](vector)


def _probe_case_19(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[19](vector)


def _probe_case_20(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[20](vector)


def _probe_case_21(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[21](vector)


def _probe_case_22(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[22](vector)


def _probe_case_23(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[23](vector)


def _probe_case_24(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[24](vector)


def _probe_case_25(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[25](vector)


def _probe_case_26(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[26](vector)


def _probe_case_27(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[27](vector)


def _probe_case_28(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[28](vector)


def _probe_case_29(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[29](vector)


def _probe_case_30(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[30](vector)


def _probe_case_31(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[31](vector)


def _probe_case_32(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[32](vector)


def _probe_case_33(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[33](vector)


def _probe_case_34(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[34](vector)


def _probe_case_35(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[35](vector)


def _probe_case_36(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[36](vector)


def _probe_case_37(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[37](vector)


def _probe_case_38(vector: _CommitTckRequest) -> dict[str, Any]:
    return _HANDLER_PROBES[38](vector)


_MATRIX_PROBES: dict[int, Callable[[_CommitTckRequest], dict[str, Any]]] = {
    1: _probe_case_01,
    2: _probe_case_02,
    3: _probe_case_03,
    4: _probe_case_04,
    5: _probe_case_05,
    6: _probe_case_06,
    7: _probe_case_07,
    8: _probe_case_08,
    9: _probe_case_09,
    10: _probe_case_10,
    11: _probe_case_11,
    12: _probe_case_12,
    13: _probe_case_13,
    14: _probe_case_14,
    15: _probe_case_15,
    16: _probe_case_16,
    17: _probe_case_17,
    18: _probe_case_18,
    19: _probe_case_19,
    20: _probe_case_20,
    21: _probe_case_21,
    22: _probe_case_22,
    23: _probe_case_23,
    24: _probe_case_24,
    25: _probe_case_25,
    26: _probe_case_26,
    27: _probe_case_27,
    28: _probe_case_28,
    29: _probe_case_29,
    30: _probe_case_30,
    31: _probe_case_31,
    32: _probe_case_32,
    33: _probe_case_33,
    34: _probe_case_34,
    35: _probe_case_35,
    36: _probe_case_36,
    37: _probe_case_37,
    38: _probe_case_38,
}


__all__ = ["ReferenceCommitTckAdapter"]
