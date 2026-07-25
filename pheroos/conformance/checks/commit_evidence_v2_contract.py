"""Public-only Conformance matrix for durable Commit Evidence v2."""

from __future__ import annotations

from dataclasses import dataclass

from pheroos.conformance.checks._commit_evidence_v2_context_support import (
    CANDIDATE_REF,
    advance_v2,
    attestations_v2,
    commit_replay_v2,
    context_v2_for_evidence,
    rebind_context_v2,
    request_v2,
    root_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.report import CheckResult
from pheroos.governance.authority_session_v2 import (
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)
from pheroos.governance.commit_evidence_v2 import (
    VerifiedCommitEvidenceStateV2,
    commit_evidence_state_is_current_v2,
    evaluate_commit_evidence_projection_v2,
    project_current_commit_evidence_v2,
    rehydrate_commit_evidence_state_v2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


GOVERNANCE_COMMIT_EVIDENCE_CONFORMANCE_VERSION_V2 = (
    "pheroos-governance-commit-evidence-conformance-v2"
)
_CHECK_NAME = "commit_evidence_v2_contract"


@dataclass(frozen=True, slots=True)
class _SameShapeSource:
    context_root: str


def run_governance_commit_evidence_conformance_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> CheckResult:
    """Run one deterministic Store-backed Evidence matrix via public ABIs."""

    try:
        if not isinstance(adapter, GovernanceStateStoreConformanceAdapterV2):
            return CheckResult(_CHECK_NAME, False, "adapter_protocol")
        if adapter.conformance_version != GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2:
            return CheckResult(_CHECK_NAME, False, "adapter_version")
        implementation_id = adapter.implementation_id
        if (
            type(implementation_id) is not str
            or not implementation_id
            or implementation_id != implementation_id.strip()
        ):
            return CheckResult(_CHECK_NAME, False, "adapter_implementation_id")
    except Exception as exc:
        return CheckResult(
            _CHECK_NAME,
            False,
            f"adapter_exception:{type(exc).__name__}:{exc}",
        )
    problems: list[str] = []
    try:
        _vertical_restart(adapter, problems)
        _source_and_order(adapter, problems)
        _conflicting_fork(adapter, problems)
    except Exception as exc:
        problems.append(f"adapter_exception:{type(exc).__name__}:{exc}")
    return CheckResult(_CHECK_NAME, not problems, ", ".join(problems))


def _vertical_restart(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = context_v2_for_evidence(adapter, "vertical")
    attestations = attestations_v2("vertical")
    replay_request, replay_state = commit_replay_v2(
        context,
        attestations,
        advance_ref="advance:replay:vertical",
    )
    request, source = request_v2(
        context,
        replay_state,
        attestations,
        advance_ref="advance:evidence:vertical",
    )
    attempt = advance_v2(context, request, source)
    if (
        attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or attempt.committed_transition is None
    ):
        problems.append("vertical_commit")
        return
    batch = attempt.committed_transition.batch
    expected_streams = {
        request.stream_ref,
        replay_request.stream_ref,
        context.upstreams.membership_request.stream_ref,
        context.upstreams.verification_request.stream_ref,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        governance_issuer_grant_stream_ref_v2(
            context.support.domain.scope_ref,
            context.support.grant.grant_ref,
        ),
    }
    if {item.stream_ref for item in batch.read_set.entries} != expected_streams:
        problems.append("complete_authority_read_set")
    event = batch.trace_batch.events[0]
    if (
        event.event_type != "commit_evidence_qualified_v2"
        or event.lineage.get("read_set_root") != batch.read_set.root()
        or event.lineage.get("snapshot_root") != request.snapshot.snapshot_root
        or event.lineage.get("verification_head_root")
        != request.snapshot.verification_head_root
    ):
        problems.append("atomic_trace_lineage")
    state = rehydrate_commit_evidence_state_v2(
        request.to_dict(),
        domain=context.support.domain,
        state_reader=context.support.store,
    )
    if (
        type(state) is not VerifiedCommitEvidenceStateV2
        or state.position is not GovernanceCommitPositionV2.CURRENT
        or not commit_evidence_state_is_current_v2(state)
    ):
        problems.append("current_rehydration")
    projection = project_current_commit_evidence_v2(state)
    claim_root = attestations[0].claim_root
    evaluation = evaluate_commit_evidence_projection_v2(
        projection,
        candidate_ref=CANDIDATE_REF,
        claim_root=claim_root,
        replay_receipt_roots=tuple(
            item.receipt_root for item in replay_state.snapshot.receipts
        ),
    )
    if (
        len(projection.records) != 3
        or evaluation.candidate_ref != CANDIDATE_REF
        or evaluation.claim_root != claim_root
        or evaluation.positive_evidence != 2_000_000
        or evaluation.counterevidence != 0
        or evaluation.missing_challenge_categories
        or evaluation.source_diversity != 2
        or not evaluation.evidence_gates_satisfied
    ):
        problems.append("qualified_success_projection_evaluation")

    exact = advance_v2(context, request, None)
    if (
        exact.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or exact.committed_transition is None
        or exact.committed_transition.receipt.receipt_root
        != attempt.committed_transition.receipt.receipt_root
    ):
        problems.append("lost_response_exact_retry")

    restarted = adapter.restart_store_v2(context.support.store)
    rebound = rebind_context_v2(context, restarted)
    recovered = rehydrate_commit_evidence_state_v2(
        request.to_dict(),
        domain=context.support.domain,
        state_reader=restarted,
    )
    if not commit_evidence_state_is_current_v2(recovered):
        problems.append("restart_rehydration")
    restart_retry = advance_v2(rebound, request, None)
    if (
        restart_retry.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or restart_retry.committed_transition is None
        or restart_retry.committed_transition.receipt.receipt_root
        != attempt.committed_transition.receipt.receipt_root
    ):
        problems.append("restart_exact_retry")


def _source_and_order(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = context_v2_for_evidence(adapter, "source-order")
    attestations = attestations_v2(
        "source-order",
        include_second_positive=False,
    )
    _, replay_state = commit_replay_v2(
        context,
        attestations,
        advance_ref="advance:replay:source-order",
    )
    request, source = request_v2(
        context,
        replay_state,
        attestations,
        advance_ref="advance:evidence:source-order",
    )
    reversed_request, reversed_source = request_v2(
        context,
        replay_state,
        tuple(reversed(attestations)),
        advance_ref="advance:evidence:source-order",
    )
    if (
        request.request_root != reversed_request.request_root
        or source.context_root != reversed_source.context_root
    ):
        problems.append("input_order_determinism")
    for label, forged in (
        ("portable_request", request.to_dict()),
        ("portable_snapshot", request.snapshot),
        ("digest", request.request_root),
        ("same_shape", _SameShapeSource(source.context_root)),
    ):
        rejected = advance_v2(context, request, forged)
        if (
            rejected.disposition is not GovernanceCommitDispositionV2.INVALID
            or rejected.failure is None
            or rejected.failure.code
            is not AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
        ):
            problems.append(f"non_authoritative_source:{label}")
    committed = advance_v2(context, request, source)
    if committed.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        problems.append("single_source_commit")
        return
    single_projection = project_current_commit_evidence_v2(
        rehydrate_commit_evidence_state_v2(
            request.to_dict(),
            domain=context.support.domain,
            state_reader=context.support.store,
        )
    )
    single_evaluation = evaluate_commit_evidence_projection_v2(
        single_projection,
        candidate_ref=CANDIDATE_REF,
        claim_root=attestations[0].claim_root,
        replay_receipt_roots=tuple(
            item.receipt_root for item in replay_state.snapshot.receipts
        ),
    )
    if (
        single_evaluation.positive_evidence != 1_000_000
        or single_evaluation.source_diversity != 1
        or single_evaluation.evidence_gates_satisfied
    ):
        problems.append("single_source_insufficient")


def _conflicting_fork(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = context_v2_for_evidence(adapter, "fork")
    attestations = attestations_v2("fork")
    _, replay_state = commit_replay_v2(
        context,
        attestations,
        advance_ref="advance:replay:fork",
    )
    first, first_source = request_v2(
        context,
        replay_state,
        attestations,
        advance_ref="advance:evidence:fork:first",
    )
    second, second_source = request_v2(
        context,
        replay_state,
        attestations,
        advance_ref="advance:evidence:fork:second",
    )
    committed = advance_v2(context, first, first_source)
    stale = advance_v2(context, second, second_source)
    if committed.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        problems.append("fork_winner")
    if (
        stale.disposition is not GovernanceCommitDispositionV2.RETRY_REQUIRED
        or stale.failure is None
        or stale.failure.code is not AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    ):
        problems.append("fork_stale_loser")
    head = context.support.store.load_head_v2(
        context.support.domain.scope_ref,
        first.stream_ref,
    )
    if head.revision != 1:
        problems.append("fork_single_head")
    wrong_subject = evaluate_commit_evidence_projection_v2(
        project_current_commit_evidence_v2(
            rehydrate_commit_evidence_state_v2(
                first.to_dict(),
                domain=context.support.domain,
                state_reader=context.support.store,
            )
        ),
        candidate_ref=CANDIDATE_REF,
        claim_root=root_v2("claim:undeclared-for-state"),
        replay_receipt_roots=tuple(
            item.receipt_root for item in replay_state.snapshot.receipts
        ),
    )
    if wrong_subject.replayed_record_roots or wrong_subject.positive_evidence != 0:
        problems.append("candidate_claim_subject_isolation")


run_governance_commit_evidence_conformance_v2.__module__ = "pheroos.conformance"


__all__ = [
    "GOVERNANCE_COMMIT_EVIDENCE_CONFORMANCE_VERSION_V2",
    "run_governance_commit_evidence_conformance_v2",
]
