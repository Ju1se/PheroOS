"""Compatibility aggregate for split deterministic Support v2 evaluation."""

from pheroos.governance._support_v2.support_evaluation_contracts import (
    SupportEvaluationV2,
)
from pheroos.governance._support_v2.support_evaluation_engine import (
    _equivocations as _equivocations,
    evaluate_support_v2,
    support_lease_status_v2,
)


__all__ = [
    "SupportEvaluationV2",
    "evaluate_support_v2",
    "support_lease_status_v2",
]
