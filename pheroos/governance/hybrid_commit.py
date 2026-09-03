from __future__ import annotations

from pheroos.governance._hybrid.binding import (
    COMMIT_AUTHORITY_SOURCE as _ENGINE_COMMIT_AUTHORITY_SOURCE,
    HYBRID_COMMIT_BINDING_PROFILE as _ENGINE_HYBRID_COMMIT_BINDING_PROFILE,
    HybridCommitStep,
    bind_hybrid_commit_channels,
    hybrid_attention_projection,
    hybrid_commit_step_fingerprint,
    hybrid_commit_step_is_authoritative,
    hybrid_commit_step_payload,
    hybrid_commit_truth_projection,
)
from pheroos.governance.hybrid_commit_evaluation import (
    HYBRID_COMMIT_EVALUATION_DIAGNOSTIC_VERSION,
    HYBRID_COMMIT_EVALUATION_REQUEST_VERSION,
    HYBRID_COMMIT_EVALUATION_VERSION,
    HybridCommitAttentionStatus,
    HybridCommitDiagnostic,
    HybridCommitDiagnosticSeverity,
    HybridCommitEvaluation,
    HybridCommitEvaluationRequest,
    HybridCommitEvaluationStatus,
    _evaluate_hybrid_commit_step,
    hybrid_commit_diagnostic_payload,
    hybrid_commit_evaluation_fingerprint,
    hybrid_commit_evaluation_is_authoritative,
    hybrid_commit_evaluation_payload,
    hybrid_commit_evaluation_request_fingerprint,
    hybrid_commit_evaluation_request_payload,
)


# Constants remain direct bindings in their historical ABI owner.  The private
# engine asserts the same values at import so the facade and engine cannot
# drift while functions and records retain one implementation owner.
COMMIT_AUTHORITY_SOURCE = "optimal_commit_assessment_only"
HYBRID_COMMIT_BINDING_PROFILE = "pheroos-hybrid-commit-binding-v1"
if (
    COMMIT_AUTHORITY_SOURCE != _ENGINE_COMMIT_AUTHORITY_SOURCE
    or HYBRID_COMMIT_BINDING_PROFILE != _ENGINE_HYBRID_COMMIT_BINDING_PROFILE
):
    raise RuntimeError("Hybrid Commit facade constants do not match the engine")


# The missing runtime return annotation is frozen in the Draft public shape;
# the precise ignore preserves that ABI while the private owner stays typed.
def evaluate_hybrid_commit_step(  # type: ignore[no-untyped-def]
    *, request: object
):
    """Run the sole total Hybrid Commit evaluation engine."""

    return _evaluate_hybrid_commit_step(request)


__all__ = [
    "COMMIT_AUTHORITY_SOURCE",
    "HYBRID_COMMIT_EVALUATION_DIAGNOSTIC_VERSION",
    "HYBRID_COMMIT_EVALUATION_REQUEST_VERSION",
    "HYBRID_COMMIT_EVALUATION_VERSION",
    "HYBRID_COMMIT_BINDING_PROFILE",
    "HybridCommitAttentionStatus",
    "HybridCommitDiagnostic",
    "HybridCommitDiagnosticSeverity",
    "HybridCommitEvaluation",
    "HybridCommitEvaluationRequest",
    "HybridCommitEvaluationStatus",
    "HybridCommitStep",
    "bind_hybrid_commit_channels",
    "evaluate_hybrid_commit_step",
    "hybrid_attention_projection",
    "hybrid_commit_diagnostic_payload",
    "hybrid_commit_evaluation_fingerprint",
    "hybrid_commit_evaluation_is_authoritative",
    "hybrid_commit_evaluation_payload",
    "hybrid_commit_evaluation_request_fingerprint",
    "hybrid_commit_evaluation_request_payload",
    "hybrid_commit_step_fingerprint",
    "hybrid_commit_step_is_authoritative",
    "hybrid_commit_step_payload",
    "hybrid_commit_truth_projection",
]
