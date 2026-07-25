from __future__ import annotations

import pytest

from pheroos.conformance.authority_store_v2_spec_adapter import (
    IndependentStdlibGovernanceStateStoreV2,
    IndependentStdlibGovernanceStateStoreV2Adapter,
)
from pheroos.conformance.checks.baseline_output_v2_contract import (
    _commit_output,
    _commit_verified_signal,
    _context,
    _issue_permission,
    _request,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)
from pheroos.governance.baseline_output_v2 import (
    BaselineOutputActionDispositionV2,
    BaselineOutputDeliveryDispositionV2,
    BaselineOutputTerminalStatusV2,
    recover_baseline_output_result_v2,
)


def test_independent_store_restart_recovers_current_authorization() -> None:
    adapter = IndependentStdlibGovernanceStateStoreV2Adapter()
    context = _context(adapter, "recovery-current", "direct_governance", 1)
    assert type(context.store) is IndependentStdlibGovernanceStateStoreV2
    proposal = _commit_verified_signal(
        context,
        label="recovery-current",
        source_ref="source:recovery-current",
    )
    request = _request(
        context,
        label="recovery-current",
        proposals=(proposal,),
        blocked=False,
    )
    _permission_session, permission = _issue_permission(context, request)
    _output_session, original = _commit_output(context, request)
    assert permission.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert original.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED

    restarted = adapter.restart_store_v2(context.store)
    assert type(restarted) is IndependentStdlibGovernanceStateStoreV2
    recovered = recover_baseline_output_result_v2(
        request,
        state_reader=restarted,
    )

    assert recovered.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert recovered.position is GovernanceCommitPositionV2.CURRENT
    assert recovered.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED
    assert recovered.authorization is not None
    assert recovered.result_root == original.result_root
    assert recovered.commit_attempt.committed_transition is not None
    assert original.commit_attempt.committed_transition is not None
    assert (
        recovered.commit_attempt.committed_transition.receipt.receipt_root
        == original.commit_attempt.committed_transition.receipt.receipt_root
    )


@pytest.mark.parametrize(
    ("decision_mode", "threshold", "blocked", "expected_status"),
    [
        (
            "quorum",
            2,
            False,
            BaselineOutputTerminalStatusV2.SAFE_FALLBACK,
        ),
        (
            "direct_governance",
            1,
            True,
            BaselineOutputTerminalStatusV2.BLOCKED,
        ),
    ],
)
def test_independent_restart_preserves_fallback_and_blocked_history_without_authority(
    decision_mode: str,
    threshold: int,
    blocked: bool,
    expected_status: BaselineOutputTerminalStatusV2,
) -> None:
    label = f"recovery-history:{expected_status.value}"
    adapter = IndependentStdlibGovernanceStateStoreV2Adapter()
    context = _context(adapter, label, decision_mode, threshold)
    proposal = _commit_verified_signal(
        context,
        label=f"{label}:signal",
        source_ref=f"source:{expected_status.value}",
    )
    first = _request(
        context,
        label=f"{label}:first",
        proposals=(proposal,),
        blocked=blocked,
    )
    _permission_session, permission = _issue_permission(context, first)
    _output_session, initial = _commit_output(context, first)
    assert permission.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert initial.terminal_status is expected_status
    assert initial.delivery_disposition is (
        BaselineOutputDeliveryDispositionV2.DELIVERABLE
    )

    successor = _request(
        context,
        label=f"{label}:successor",
        proposals=(proposal,),
        blocked=False,
        payload="successor",
    )
    _successor_permission_session, successor_permission = _issue_permission(
        context,
        successor,
    )
    _successor_output_session, successor_result = _commit_output(context, successor)
    assert successor_permission.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert successor_result.disposition is GovernanceCommitDispositionV2.COMMITTED

    recovered = recover_baseline_output_result_v2(
        first,
        state_reader=adapter.restart_store_v2(context.store),
    )

    assert recovered.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert recovered.position is GovernanceCommitPositionV2.SUPERSEDED
    assert recovered.terminal_status is expected_status
    assert recovered.delivery_disposition is (
        BaselineOutputDeliveryDispositionV2.DELIVERABLE
    )
    assert recovered.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert recovered.authorization is None
    assert recovered.result_root == initial.result_root
    assert recovered.commit_attempt.committed_transition is not None
    assert initial.commit_attempt.committed_transition is not None
    assert (
        recovered.commit_attempt.committed_transition.receipt.receipt_root
        == initial.commit_attempt.committed_transition.receipt.receipt_root
    )
