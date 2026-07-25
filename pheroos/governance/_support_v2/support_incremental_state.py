"""Incremental verified-state adoption for a committed Support v2 successor."""

from __future__ import annotations

from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance._support_v2.support_projection import (
    _validate_transition_delta,
)
from pheroos.governance._support_v2.support_state_contracts import (
    SupportAdvanceRequestV2,
    SupportMutationKindV2,
)
from pheroos.governance._support_v2.support_state_handle import (
    VerifiedSupportStateV2,
    _make_verified_state,
    _state_handle_fields,
    _verified_current_state_material_v2,
)
from pheroos.governance._support_v2.support_state_load import (
    _decode_committed_view,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
)


def _adopt_committed_support_successor_v2(
    parent_state: object,
    request: SupportAdvanceRequestV2,
    attempt: GovernanceCommitAttemptV2,
) -> VerifiedSupportStateV2:
    """Adopt an exact committed child from one already verified parent anchor."""

    if type(request) is not SupportAdvanceRequestV2:
        raise TypeError("support successor adoption requires exact request v2")
    reader, domain, parent, parent_anchor = _state_handle_fields(parent_state)
    if request.mutation_kind is SupportMutationKindV2.INITIALIZE:
        raise ValueError("support initialization has no incremental parent")
    if type(attempt) is not GovernanceCommitAttemptV2:
        raise TypeError("support successor adoption requires exact commit attempt v2")
    detached = GovernanceCommitAttemptV2.from_dict(attempt.to_dict())
    if not _committed_current_attempt(detached):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            "/attempt",
        )
    view = _view_from_attempt(detached)
    committed, _, _, _, _ = _decode_committed_view(view, domain)
    if committed.to_dict() != request.to_dict():
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/request_root",
        )
    _validate_incremental_parent(request, parent, parent_anchor.head_root, view)
    state = _make_verified_state(
        state_reader=reader,
        domain=domain,
        request=request,
        view=view,
    )
    _verified_current_state_material_v2(state)
    return state


def _committed_current_attempt(attempt: GovernanceCommitAttemptV2) -> bool:
    position = attempt.position_observation
    return bool(
        attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        and attempt.committed_transition is not None
        and position is not None
        and position.position is GovernanceCommitPositionV2.CURRENT
    )


def _view_from_attempt(attempt: GovernanceCommitAttemptV2) -> GovernanceCommitViewV2:
    assert attempt.committed_transition is not None
    assert attempt.position_observation is not None
    position = attempt.position_observation
    return GovernanceCommitViewV2(
        domain_root=attempt.domain_root,
        scope_ref=attempt.scope_ref,
        stream_ref=attempt.stream_ref,
        transition_id=attempt.transition_id,
        expected_receipt_root=attempt.committed_transition.receipt.receipt_root,
        disposition=attempt.disposition,
        failure=None,
        committed_transition=attempt.committed_transition,
        position_observation=position,
        observed_revision=position.observed_revision,
        observed_head_root=position.observed_head_root,
    )


def _validate_incremental_parent(
    request: SupportAdvanceRequestV2,
    parent: SupportAdvanceRequestV2,
    parent_head_root: str,
    view: GovernanceCommitViewV2,
) -> None:
    assert view.committed_transition is not None
    receipt = view.committed_transition.receipt
    if (
        request.snapshot.parent_snapshot_root != parent.snapshot.snapshot_root
        or request.snapshot.parent_transition_id != parent.transition_id
        or request.snapshot.parent_revision != parent.snapshot.revision
        or receipt.parent_root != parent_head_root
        or receipt.revision != request.snapshot.revision
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/snapshot/parent_snapshot_root",
        )
    _validate_transition_delta(request, parent.snapshot)


__all__: tuple[str, ...] = ()
