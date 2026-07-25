"""Private owner adapter from Certificate state to neutral Decision finality."""

from __future__ import annotations

from pheroos.governance._commit_certificate_v2.state_handle import (
    _verified_commit_certificate_finality_context_material_v2,
    _verified_commit_certificate_finality_context_v2,
)
from pheroos.governance._commit_finality_v2 import (
    VerifiedCommitFinalityInputV2,
    _issue_verified_commit_finality_input_v2,
)


def _verified_commit_certificate_finality_input_v2(
    certificate_state: object,
    *,
    sealed_decision_state: object,
    current_step: int,
) -> VerifiedCommitFinalityInputV2:
    """Issue one opaque neutral handle after full current-state revalidation."""

    context = _verified_commit_certificate_finality_context_v2(
        certificate_state,
        sealed_decision_state=sealed_decision_state,
        current_step=current_step,
    )
    material = _verified_commit_certificate_finality_context_material_v2(context)
    return _issue_verified_commit_finality_input_v2(
        projection=material.projection,
        owner_precondition=material.certificate_precondition,
        owner_receipt_root=material.certificate_receipt_root,
        owner_inclusion_root=material.certificate_inclusion_root,
    )


__all__: tuple[str, ...] = ()
