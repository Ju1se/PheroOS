from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from pheroos.governance._authority_session_v2.operations import (
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance._authority_v2 import InMemoryGovernanceStateStoreV2
from pheroos.governance.authority_store_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
)
from pheroos.governance.baseline_output_v2 import (
    BaselineOutputActionDispositionV2,
    BaselineOutputDeliveryDispositionV2,
    BaselineOutputRequestV2,
    BaselineOutputTerminalStatusV2,
    recover_baseline_output_result_v2,
)
from tests.governance.test_baseline_output_v2_operations import (
    _commit_output,
    _context,
    _issue,
    _request,
)


class _ReaderAdapter:
    def __init__(
        self,
        store: InMemoryGovernanceStateStoreV2,
        *,
        replacement_view: object | None = None,
        unavailable: bool = False,
    ) -> None:
        self.store = store
        self.replacement_view = replacement_view
        self.unavailable = unavailable
        self.commit_view_calls = 0

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        return self.store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        return self.store.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        self.commit_view_calls += 1
        if self.unavailable:
            raise OSError("reader unavailable")
        if self.replacement_view is not None:
            return self.replacement_view  # type: ignore[return-value]
        return self.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )


def _assert_historical_denial(result: object) -> None:
    assert getattr(result, "disposition") is GovernanceCommitDispositionV2.COMMITTED
    assert getattr(result, "delivery_disposition") is (
        BaselineOutputDeliveryDispositionV2.DELIVERABLE
    )
    assert getattr(result, "action_disposition") is (
        BaselineOutputActionDispositionV2.DENIED
    )
    assert getattr(result, "authorization") is None


def test_recovery_from_fresh_store_uses_one_commit_view_and_restores_current_action() -> (
    None
):
    context = _context(scope_ref="scope:baseline-recovery-restart")
    request = _request(context, decision_mode="direct_governance")
    assert (
        _issue(context, request).disposition is GovernanceCommitDispositionV2.COMMITTED
    )
    original = _commit_output(context, request)
    assert original.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED

    fresh = InMemoryGovernanceStateStoreV2.from_snapshot_v2(context.store.snapshot_v2())
    reader = _ReaderAdapter(fresh)
    recovered = recover_baseline_output_result_v2(request, state_reader=reader)

    assert reader.commit_view_calls == 1
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


def test_recovery_preserves_superseded_output_as_deliverable_history_only() -> None:
    context = _context(scope_ref="scope:baseline-recovery-historical")
    first = _request(
        context,
        request_label="first",
        decision_mode="direct_governance",
    )
    assert _issue(context, first).disposition is GovernanceCommitDispositionV2.COMMITTED
    _commit_output(context, first)
    successor = _request(
        context,
        request_label="successor",
        decision_mode="direct_governance",
        payload="successor",
    )
    assert (
        _issue(context, successor).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    _commit_output(context, successor)

    fresh = InMemoryGovernanceStateStoreV2.from_snapshot_v2(context.store.snapshot_v2())
    recovered = recover_baseline_output_result_v2(first, state_reader=fresh)

    assert recovered.position is GovernanceCommitPositionV2.SUPERSEDED
    _assert_historical_denial(recovered)


@pytest.mark.parametrize("stale_kind", ["permission-and-stop", "issuer-grant"])
def test_recovery_denies_current_output_when_original_authority_dependency_is_stale(
    stale_kind: str,
) -> None:
    context = _context(scope_ref=f"scope:baseline-recovery-stale:{stale_kind}")
    request = _request(
        context,
        request_label="original",
        decision_mode="direct_governance",
    )
    assert (
        _issue(context, request).disposition is GovernanceCommitDispositionV2.COMMITTED
    )
    committed = _commit_output(context, request)
    assert committed.position is GovernanceCommitPositionV2.CURRENT
    assert committed.action_disposition is BaselineOutputActionDispositionV2.AUTHORIZED

    if stale_kind == "permission-and-stop":
        successor = _request(
            context,
            request_label="dependency-successor",
            decision_mode="direct_governance",
            payload="successor",
        )
        assert _issue(context, successor).disposition is (
            GovernanceCommitDispositionV2.COMMITTED
        )
    else:
        revoked = revoke_governance_issuer_grant_v2(
            context.store,
            context.domain,
            context.grant.grant_ref,
            "transition:grant:recovery:revoke",
            3,
        )
        assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED

    recovered = recover_baseline_output_result_v2(
        request,
        state_reader=InMemoryGovernanceStateStoreV2.from_snapshot_v2(
            context.store.snapshot_v2()
        ),
    )

    assert recovered.position is GovernanceCommitPositionV2.CURRENT
    _assert_historical_denial(recovered)


def test_absent_wrong_and_unavailable_readers_return_typed_total_results() -> None:
    context = _context(scope_ref="scope:baseline-recovery-reader-failures")
    request = _request(context, decision_mode="direct_governance")

    absent = recover_baseline_output_result_v2(
        request,
        state_reader=context.store,
    )
    assert absent.disposition is GovernanceCommitDispositionV2.INVALID
    assert absent.terminal_status is BaselineOutputTerminalStatusV2.INVALID
    assert absent.commit_attempt.failure is not None
    assert absent.commit_attempt.failure.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )

    wrong = recover_baseline_output_result_v2(
        request,
        state_reader=object(),  # type: ignore[arg-type]
    )
    assert wrong.disposition is GovernanceCommitDispositionV2.INVALID
    assert wrong.commit_attempt.failure is not None
    assert wrong.commit_attempt.failure.code is (
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )

    unavailable_reader = _ReaderAdapter(context.store, unavailable=True)
    unavailable = recover_baseline_output_result_v2(
        request,
        state_reader=unavailable_reader,
    )
    assert unavailable_reader.commit_view_calls == 1
    assert unavailable.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert unavailable.terminal_status is (
        BaselineOutputTerminalStatusV2.FINALITY_UNAVAILABLE
    )
    assert unavailable.authorization is None


@pytest.mark.parametrize("attack", ["tamper", "transition-substitution", "cross-scope"])
def test_recovery_rejects_tampered_or_substituted_commit_views(attack: str) -> None:
    context = _context(scope_ref=f"scope:baseline-recovery-attack:{attack}")
    request = _request(
        context,
        request_label="original",
        decision_mode="direct_governance",
    )
    assert (
        _issue(context, request).disposition is GovernanceCommitDispositionV2.COMMITTED
    )
    _commit_output(context, request)

    if attack == "tamper":
        replacement = context.store.load_commit_view_v2(
            request.scope_ref,
            request.output_stream_ref,
            request.output_transition_id,
        )
        object.__setattr__(replacement, "view_root", "sha256:" + "7" * 64)
    elif attack == "transition-substitution":
        successor = _request(
            context,
            request_label="substituted",
            decision_mode="direct_governance",
            payload="substituted",
        )
        assert _issue(context, successor).disposition is (
            GovernanceCommitDispositionV2.COMMITTED
        )
        _commit_output(context, successor)
        replacement = context.store.load_commit_view_v2(
            successor.scope_ref,
            successor.output_stream_ref,
            successor.output_transition_id,
        )
    else:
        other = _context(scope_ref="scope:baseline-recovery-attack:other")
        other_request = _request(other, decision_mode="direct_governance")
        assert _issue(other, other_request).disposition is (
            GovernanceCommitDispositionV2.COMMITTED
        )
        _commit_output(other, other_request)
        replacement = other.store.load_commit_view_v2(
            other_request.scope_ref,
            other_request.output_stream_ref,
            other_request.output_transition_id,
        )
    reader = _ReaderAdapter(context.store, replacement_view=replacement)

    result = recover_baseline_output_result_v2(request, state_reader=reader)

    assert reader.commit_view_calls == 1
    assert result.disposition is GovernanceCommitDispositionV2.INVALID
    assert result.terminal_status is BaselineOutputTerminalStatusV2.INVALID
    assert result.action_disposition is BaselineOutputActionDispositionV2.DENIED
    assert result.authorization is None


def test_recovery_requires_the_exact_request_type() -> None:
    context = _context(scope_ref="scope:baseline-recovery-exact-request")
    request = _request(context, decision_mode="direct_governance")

    with pytest.raises(TypeError, match="exact request type"):
        recover_baseline_output_result_v2(
            request.to_dict(),  # type: ignore[arg-type]
            state_reader=context.store,
        )

    assert type(request) is BaselineOutputRequestV2
