"""Public Draft facade for the diagnostic-total Hybrid Commit evaluator."""

from __future__ import annotations


from pheroos.governance._hybrid.commit import (
    hybrid_commit_evaluation_is_authoritative,
)
from pheroos.governance._hybrid.evaluation_records import (
    HYBRID_COMMIT_EVALUATION_DIAGNOSTIC_VERSION as _ENGINE_DIAGNOSTIC_VERSION,
    HYBRID_COMMIT_EVALUATION_REQUEST_VERSION as _ENGINE_REQUEST_VERSION,
    HYBRID_COMMIT_EVALUATION_VERSION as _ENGINE_EVALUATION_VERSION,
    HybridCommitAttentionStatus,
    HybridCommitDiagnostic,
    HybridCommitDiagnosticSeverity,
    HybridCommitEvaluation,
    HybridCommitEvaluationStatus,
    hybrid_commit_diagnostic_payload,
    hybrid_commit_evaluation_fingerprint,
    hybrid_commit_evaluation_payload,
)
from pheroos.governance._hybrid.pipeline import (
    evaluate_hybrid_commit_step as _run_hybrid_commit_pipeline,
)
from pheroos.governance._hybrid.request import (
    HybridCommitEvaluationRequest,
    hybrid_commit_evaluation_request_fingerprint,
    hybrid_commit_evaluation_request_payload,
)
from pheroos.governance._hybrid.trace import _build_evaluation_trace
from pheroos.governance.commit_state import (
    commit_window_state_fingerprint as _commit_window_state_fingerprint,
)


# Retained private test/debug hook from the historical aggregate module.
commit_window_state_fingerprint = _commit_window_state_fingerprint


# Direct declarations retain the historical public binding owner.
HYBRID_COMMIT_EVALUATION_VERSION = "pheroos-hybrid-commit-evaluation-v1"
HYBRID_COMMIT_EVALUATION_REQUEST_VERSION = "pheroos-hybrid-commit-evaluation-request-v1"
HYBRID_COMMIT_EVALUATION_DIAGNOSTIC_VERSION = (
    "pheroos-hybrid-commit-evaluation-diagnostic-v1"
)

if (
    HYBRID_COMMIT_EVALUATION_VERSION != _ENGINE_EVALUATION_VERSION
    or HYBRID_COMMIT_EVALUATION_REQUEST_VERSION != _ENGINE_REQUEST_VERSION
    or HYBRID_COMMIT_EVALUATION_DIAGNOSTIC_VERSION != _ENGINE_DIAGNOSTIC_VERSION
):
    raise RuntimeError("Hybrid Commit evaluation facade constants drifted")


def _evaluate_hybrid_commit_step(request: object) -> HybridCommitEvaluation:
    """Compatibility bridge into the sole total private pipeline."""

    return _run_hybrid_commit_pipeline(
        request=request,
        _trace_builder=_build_evaluation_trace,
    )


_PUBLIC_MODULE = __name__
for _public_object in (
    HybridCommitAttentionStatus,
    HybridCommitDiagnostic,
    HybridCommitDiagnosticSeverity,
    HybridCommitEvaluation,
    HybridCommitEvaluationRequest,
    HybridCommitEvaluationStatus,
    hybrid_commit_diagnostic_payload,
    hybrid_commit_evaluation_fingerprint,
    hybrid_commit_evaluation_is_authoritative,
    hybrid_commit_evaluation_payload,
    hybrid_commit_evaluation_request_fingerprint,
    hybrid_commit_evaluation_request_payload,
):
    _public_object.__module__ = _PUBLIC_MODULE
del _public_object


__all__ = [
    "HYBRID_COMMIT_EVALUATION_DIAGNOSTIC_VERSION",
    "HYBRID_COMMIT_EVALUATION_REQUEST_VERSION",
    "HYBRID_COMMIT_EVALUATION_VERSION",
    "HybridCommitDiagnostic",
    "HybridCommitDiagnosticSeverity",
    "HybridCommitAttentionStatus",
    "HybridCommitEvaluation",
    "HybridCommitEvaluationRequest",
    "HybridCommitEvaluationStatus",
    "hybrid_commit_diagnostic_payload",
    "hybrid_commit_evaluation_fingerprint",
    "hybrid_commit_evaluation_is_authoritative",
    "hybrid_commit_evaluation_payload",
    "hybrid_commit_evaluation_request_fingerprint",
    "hybrid_commit_evaluation_request_payload",
]
