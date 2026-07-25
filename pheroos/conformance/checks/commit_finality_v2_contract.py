"""Public-only dual-Store composite Conformance for Commit Finality v2."""

from __future__ import annotations

from dataclasses import replace

from pheroos.conformance.checks._commit_finality_v2_certificate_support import (
    verified_certificate_v2,
)
from pheroos.conformance.checks._commit_finality_v2_decision_support import (
    advance_decision_v2,
    certified_decision_vertical_v2,
    commit_decision_successor_v2,
    prepare_decision_successor_v2,
)
from pheroos.conformance.checks._commit_finality_v2_distributed_support import (
    advance_distributed_decision_v2,
    advance_distributed_owner_successor_v2,
    distributed_conflict_finality_v2,
    distributed_decision_state_v2,
    portable_finality_projection_v2,
    prepare_distributed_finalization_v2,
)
from pheroos.conformance.checks._distributed_v2_vertical_support import (
    build_verified_distributed_vertical_v2,
    freeze_external_witness_conflict_v2,
    verified_finality_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.report import CheckResult
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
)
from pheroos.governance.commit_certificate_v2 import (
    CommitCertificateStatusV2,
    verified_commit_certificate_finality_input_v2,
)
from pheroos.governance.commit_decision_v2 import (
    CommitDecisionOutcomeKindV2,
    VerifiedCommitDecisionStateV2,
)
from pheroos.governance.commit_finality_v2 import (
    VerifiedCommitFinalityInputV2,
)
from pheroos.governance.distributed_commit_v2 import (
    DistributedLaneStatusV2,
    DistributedMutationKindV2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


GOVERNANCE_COMMIT_FINALITY_CONFORMANCE_VERSION_V2 = (
    "pheroos-governance-commit-finality-conformance-v2"
)
_CHECK_NAME = "commit_finality_v2_contract"


def run_governance_commit_finality_conformance_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> CheckResult:
    """Run Certificate, Distributed, opaque-input, deadline, and CAS journeys."""

    try:
        if not isinstance(adapter, GovernanceStateStoreConformanceAdapterV2):
            return CheckResult(_CHECK_NAME, False, "adapter_protocol")
        if adapter.conformance_version != GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2:
            return CheckResult(_CHECK_NAME, False, "adapter_version")
        if type(adapter.implementation_id) is not str or not adapter.implementation_id:
            return CheckResult(_CHECK_NAME, False, "adapter_implementation_id")
    except Exception as exc:
        return CheckResult(
            _CHECK_NAME,
            False,
            f"adapter_exception:{type(exc).__name__}",
        )
    problems: list[str] = []
    try:
        _certificate_verified_and_portability_v2(adapter, problems)
        _certificate_race_and_conflict_v2(adapter, problems)
        _distributed_verified_v2(adapter, problems)
        _distributed_conflict_v2(adapter, problems)
        _distributed_owner_race_v2(adapter, problems)
        _missing_handle_deadline_v2(adapter, problems)
    except Exception as exc:
        problems.append(f"adapter_exception:{type(exc).__name__}:{exc}")
    return CheckResult(_CHECK_NAME, not problems, ", ".join(problems))


def _certificate_verified_and_portability_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    vertical = certified_decision_vertical_v2(adapter, "certificate-verified")
    certificate = verified_certificate_v2(vertical, "certificate-verified")
    handle = verified_commit_certificate_finality_input_v2(
        certificate.state,
        sealed_decision_state=vertical.state,
        current_step=10,
    )
    if type(handle) is not VerifiedCommitFinalityInputV2:
        problems.append("certificate_handle_exact_type")
    portable = portable_finality_projection_v2()
    for label, substitute in (
        ("portable_projection", portable),
        ("portable_projection_root", portable.projection_root),
    ):
        try:
            prepare_decision_successor_v2(
                vertical,
                mutation_ref=f"mutation:finality:substitute:{label}",
                current_step=10,
                verified_finality_input=substitute,
            )
        except (TypeError, ValueError):
            pass
        else:
            problems.append(f"portable_substituted_handle:{label}")
    attempt, state = commit_decision_successor_v2(
        vertical,
        mutation_ref="mutation:finality:certificate:verified",
        current_step=10,
        verified_finality_input=handle,
    )
    _expect_outcome_v2(
        attempt,
        state,
        CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT,
        problems,
        "certificate_verified",
    )


def _certificate_race_and_conflict_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    vertical = certified_decision_vertical_v2(adapter, "certificate-conflict")
    first = verified_certificate_v2(vertical, "certificate-conflict:first")
    handle = verified_commit_certificate_finality_input_v2(
        first.state,
        sealed_decision_state=vertical.state,
        current_step=10,
    )
    prepared, prepared_source = prepare_decision_successor_v2(
        vertical,
        mutation_ref="mutation:finality:certificate:prepared-before-owner-successor",
        current_step=10,
        verified_finality_input=handle,
    )
    successor = verified_certificate_v2(
        vertical,
        "certificate-conflict:semantic-successor",
        parent_state=first.state,
    )
    stale = advance_decision_v2(vertical, prepared, prepared_source)
    _expect_retry_v2(stale, problems, "certificate_owner_successor_cas")

    _, heartbeat = commit_decision_successor_v2(
        vertical,
        mutation_ref="mutation:finality:certificate:heartbeat:10",
        current_step=10,
    )
    current = replace(vertical, state=heartbeat)
    conflict = verified_certificate_v2(
        current,
        "certificate-conflict:conflicting-body",
        decision_state=heartbeat,
        parent_state=successor.state,
    )
    if conflict.state.snapshot.status is not CommitCertificateStatusV2.CONFLICT:
        problems.append("certificate_conflict_not_durable")
        return
    conflict_handle = verified_commit_certificate_finality_input_v2(
        conflict.state,
        sealed_decision_state=heartbeat,
        current_step=11,
    )
    attempt, state = commit_decision_successor_v2(
        current,
        mutation_ref="mutation:finality:certificate:safety-violation",
        current_step=11,
        verified_finality_input=conflict_handle,
    )
    _expect_outcome_v2(
        attempt,
        state,
        CommitDecisionOutcomeKindV2.SAFETY_VIOLATION,
        problems,
        "certificate_conflict",
    )


def _distributed_verified_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    vertical = build_verified_distributed_vertical_v2(adapter, "finality-verified")
    handle = verified_finality_v2(vertical)
    request, source = prepare_distributed_finalization_v2(
        vertical,
        verified_finality_input=handle,
        label="verified",
        current_step=10,
    )
    attempt = advance_distributed_decision_v2(vertical, request, source)
    state = distributed_decision_state_v2(vertical, request)
    _expect_outcome_v2(
        attempt,
        state,
        CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT,
        problems,
        "distributed_verified",
    )


def _distributed_conflict_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    baseline = build_verified_distributed_vertical_v2(adapter, "finality-conflict")
    conflict = freeze_external_witness_conflict_v2(
        baseline,
        "finality-conflict",
    )
    if (
        conflict.witness.snapshot.status is not DistributedLaneStatusV2.FROZEN
        or conflict.witness.snapshot.mutation_kind
        is not DistributedMutationKindV2.EQUIVOCATION_FROZEN
    ):
        problems.append("distributed_conflict_not_frozen")
        return
    handle = distributed_conflict_finality_v2(conflict, current_step=10)
    if type(handle) is not VerifiedCommitFinalityInputV2:
        problems.append("distributed_conflict_handle_exact_type")
        return
    request, source = prepare_distributed_finalization_v2(
        baseline,
        verified_finality_input=handle,
        label="conflict-safety-violation",
        current_step=10,
    )
    attempt = advance_distributed_decision_v2(baseline, request, source)
    state = distributed_decision_state_v2(baseline, request)
    _expect_outcome_v2(
        attempt,
        state,
        CommitDecisionOutcomeKindV2.SAFETY_VIOLATION,
        problems,
        "distributed_conflict",
    )
    outcome = state.snapshot.outcome
    if outcome is None or outcome.reason_codes != ("finality:conflict",):
        problems.append("distributed_conflict_reason")


def _distributed_owner_race_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    baseline = build_verified_distributed_vertical_v2(adapter, "finality-race")
    handle = verified_finality_v2(baseline)
    prepared, prepared_source = prepare_distributed_finalization_v2(
        baseline,
        verified_finality_input=handle,
        label="prepared-before-owner-successor",
        current_step=10,
    )
    successor = advance_distributed_owner_successor_v2(
        baseline,
        "finality-race",
    )
    stale = advance_distributed_decision_v2(
        successor,
        prepared,
        prepared_source,
    )
    _expect_retry_v2(stale, problems, "distributed_owner_successor_cas")


def _missing_handle_deadline_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    vertical = certified_decision_vertical_v2(adapter, "missing-handle-deadline")
    parent = vertical.state
    deadline = parent.snapshot.finality_deadline_step
    terminal: VerifiedCommitDecisionStateV2 | None = None
    terminal_attempt: GovernanceCommitAttemptV2 | None = None
    for step in range(parent.snapshot.current_step + 1, deadline + 1):
        terminal_attempt, parent = commit_decision_successor_v2(
            replace(vertical, state=parent),
            parent_state=parent,
            mutation_ref=f"mutation:finality:missing-handle:{step}",
            current_step=step,
        )
        if parent.snapshot.outcome is not None:
            terminal = parent
            break
    if terminal_attempt is None or terminal is None:
        problems.append("missing_handle_no_terminal")
        return
    outcome = terminal.snapshot.outcome
    if (
        terminal_attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or terminal_attempt.committed_transition is None
        or outcome is None
        or outcome.kind is not CommitDecisionOutcomeKindV2.FINALITY_UNAVAILABLE
        or not outcome.delivery_eligible
        or outcome.publication_eligible
        or outcome.execution_eligible
        or outcome.epistemically_committed
        or outcome.finality_root
        or not outcome.terminal
        or outcome.reason_codes
        != ("finality:verified_owner_handle_missing_at_deadline",)
    ):
        problems.append("missing_handle_deadline")
    if terminal.snapshot.current_step != deadline:
        problems.append("missing_handle_terminal_before_deadline")


def _expect_retry_v2(
    attempt: GovernanceCommitAttemptV2,
    problems: list[str],
    label: str,
) -> None:
    if (
        attempt.disposition is not GovernanceCommitDispositionV2.RETRY_REQUIRED
        or attempt.failure is None
        or attempt.failure.code
        is not AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    ):
        problems.append(label)


def _expect_outcome_v2(
    attempt: GovernanceCommitAttemptV2,
    state: VerifiedCommitDecisionStateV2,
    expected: CommitDecisionOutcomeKindV2,
    problems: list[str],
    label: str,
) -> None:
    outcome = state.snapshot.outcome
    if (
        attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or attempt.committed_transition is None
        or outcome is None
        or outcome.kind is not expected
        or not outcome.delivery_eligible
        or not outcome.finality_root
    ):
        problems.append(label)


run_governance_commit_finality_conformance_v2.__module__ = "pheroos.conformance"


__all__ = [
    "GOVERNANCE_COMMIT_FINALITY_CONFORMANCE_VERSION_V2",
    "run_governance_commit_finality_conformance_v2",
]
