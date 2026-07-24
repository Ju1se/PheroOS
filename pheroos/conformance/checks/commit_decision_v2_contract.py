"""Public-only dual-Store Conformance for durable Commit Decision v2."""

from __future__ import annotations

from dataclasses import replace

from pheroos.conformance.checks._commit_decision_v2_context_support import (
    CANDIDATE_REF,
    CommitDecisionV2ReadyContext,
    ready_context_v2,
)
from pheroos.conformance.checks._support_v2_context_support import (
    SupportV2ConformanceContext,
    capability_v2,
    context_v2,
)
from pheroos.conformance.checks._support_v2_manifest_support import (
    PROFILE,
    RUN_REF,
    TARGET_REF,
    root_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.report import CheckResult
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    bind_governance_issuer_capability_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.commit_decision_v2 import (
    CommitDecisionCandidateProposalV2,
    CommitDecisionCommandV2,
    CommitDecisionMutationKindV2,
    CommitDecisionOutcomeKindV2,
    CommitDecisionOutputProposalV2,
    CommitDecisionRequestV2,
    VerifiedCommitDecisionSourceV2,
    VerifiedCommitDecisionStateV2,
    advance_commit_decision_v2,
    commit_decision_state_is_current_v2,
    open_commit_decision_authority_session_v2,
    prepare_commit_decision_initialize_v2,
    prepare_commit_decision_missing_inputs_v2,
    prepare_commit_decision_successor_v2,
    rehydrate_commit_decision_state_v2,
    require_current_commit_decision_state_v2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


GOVERNANCE_COMMIT_DECISION_CONFORMANCE_VERSION_V2 = (
    "pheroos-governance-commit-decision-conformance-v2"
)
_CHECK_NAME = "commit_decision_v2_contract"


def run_governance_commit_decision_conformance_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> CheckResult:
    """Run missing, ready, seal, terminal, restart, retry, and CAS journeys."""

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
        _missing_deadline_restart_retry_race(adapter, problems)
        _ready_seal_terminal_restart(adapter, problems)
    except Exception as exc:
        problems.append(f"adapter_exception:{type(exc).__name__}:{exc}")
    return CheckResult(_CHECK_NAME, not problems, ", ".join(problems))


def _missing_deadline_restart_retry_race(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = context_v2(adapter, "commit-decision:missing")
    initialize, source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        observed_epoch=1,
        mutation_ref="mutation:commit-decision:missing:initialize",
        current_step=6,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    first = _advance_support_context_v2(context, initialize, source)
    if not _committed(first):
        problems.append("missing_initialize_commit")
        return
    _expect_events(
        first,
        ("commit_decision_initialized_v2", "commit_decision_progressed_v2"),
        problems,
        "missing_initialize_trace",
    )
    retry = _advance_support_context_v2(context, initialize, source)
    if retry.to_dict() != first.to_dict():
        problems.append("same_process_exact_retry")

    restarted_parent = _restart_missing_parent(
        adapter, context, initialize, first, problems
    )
    if restarted_parent is None:
        return
    restarted, parent = restarted_parent
    progressed = _commit_competing_missing_children(restarted, parent, problems)
    if progressed is None:
        return
    _commit_missing_deadline(restarted, progressed, problems)


def _restart_missing_parent(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context: SupportV2ConformanceContext,
    initialize: CommitDecisionRequestV2,
    first: GovernanceCommitAttemptV2,
    problems: list[str],
) -> tuple[SupportV2ConformanceContext, VerifiedCommitDecisionStateV2] | None:
    """Recover the exact initialized parent from a restarted Store."""

    restarted_store = adapter.restart_store_v2(context.store)
    restarted = replace(context, store=restarted_store)
    restarted_retry = _advance_support_context_v2(restarted, initialize, None)
    if restarted_retry.to_dict() != first.to_dict():
        problems.append("restart_lost_response_exact_retry")
    try:
        parent = rehydrate_commit_decision_state_v2(
            initialize.to_dict(),
            domain=context.domain,
            state_reader=restarted_store,
        )
    except Exception:
        problems.append("restart_rehydrate")
        return None
    if type(
        parent
    ) is not VerifiedCommitDecisionStateV2 or not commit_decision_state_is_current_v2(
        parent
    ):
        problems.append("restart_current_state")
        return None
    return restarted, parent


def _commit_competing_missing_children(
    context: SupportV2ConformanceContext,
    parent: VerifiedCommitDecisionStateV2,
    problems: list[str],
) -> VerifiedCommitDecisionStateV2 | None:
    """Commit one child and prove the competing parent CAS loses."""

    child_a, child_a_source = prepare_commit_decision_missing_inputs_v2(
        parent_state=parent,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:commit-decision:missing:child-a",
        current_step=7,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    child_b, child_b_source = prepare_commit_decision_missing_inputs_v2(
        parent_state=parent,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:commit-decision:missing:child-b",
        current_step=7,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    committed_child = _advance_support_context_v2(
        context,
        child_a,
        child_a_source,
    )
    if not _committed(committed_child):
        problems.append("missing_progress_commit")
        return None
    stale = _advance_support_context_v2(context, child_b, child_b_source)
    if (
        stale.disposition is not GovernanceCommitDispositionV2.RETRY_REQUIRED
        or stale.failure is None
        or stale.failure.code is not AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
        or stale.failure.path != "/parent"
    ):
        problems.append("decision_parent_cas_race")
    progressed = rehydrate_commit_decision_state_v2(
        child_a.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    return progressed


def _commit_missing_deadline(
    context: SupportV2ConformanceContext,
    progressed: VerifiedCommitDecisionStateV2,
    problems: list[str],
) -> None:
    """Advance missing evidence to its typed safe terminal deadline."""

    snapshot = require_current_commit_decision_state_v2(progressed)
    if (
        snapshot.progress is None
        or snapshot.outcome is not None
        or not snapshot.progress.unmet_gates
        or not all(
            item.startswith("missing:") for item in snapshot.progress.unmet_gates
        )
    ):
        problems.append("bounded_missing_progress")
    deadline, deadline_source = prepare_commit_decision_missing_inputs_v2(
        parent_state=progressed,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:commit-decision:missing:deadline",
        current_step=snapshot.evidence_deadline_step,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    terminal_attempt = _advance_support_context_v2(
        context,
        deadline,
        deadline_source,
    )
    if not _committed(terminal_attempt):
        problems.append("missing_deadline_commit")
        return
    terminal = rehydrate_commit_decision_state_v2(
        deadline.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    ).snapshot
    if (
        terminal.outcome is None
        or terminal.outcome.kind is not CommitDecisionOutcomeKindV2.SAFE_FALLBACK
        or not terminal.outcome.delivery_eligible
        or terminal.progress is not None
    ):
        problems.append("missing_deadline_typed_terminal")
    _expect_events(
        terminal_attempt,
        ("commit_decision_outcome_committed_v2",),
        problems,
        "missing_deadline_trace",
    )


def _ready_seal_terminal_restart(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = ready_context_v2(adapter, "ready")
    initialize, initialize_source = prepare_commit_decision_initialize_v2(
        domain=context.support_context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        observed_epoch=1,
        mutation_ref="mutation:commit-decision:ready:initialize",
        current_step=6,
        mutation_issuer_ref=context.support_context.grant.issuer_ref,
    )
    initialized = _advance_ready_context_v2(context, initialize, initialize_source)
    if not _committed(initialized):
        problems.append("ready_initialize_commit")
        return
    state = _ready_state_v2(context, initialize)
    proposal = CommitDecisionCandidateProposalV2(
        candidate_ref=CANDIDATE_REF,
        claim_root=context.claim_root,
        evidence=(),
    )
    advanced_state = _advance_ready_window(context, state, proposal, problems)
    if advanced_state is None:
        return
    sealed_state = _seal_ready_window(context, advanced_state, proposal, problems)
    if sealed_state is None:
        return
    _finalize_ready_window(context, adapter, sealed_state, proposal, problems)


def _advance_ready_window(
    context: CommitDecisionV2ReadyContext,
    state: VerifiedCommitDecisionStateV2,
    proposal: CommitDecisionCandidateProposalV2,
    problems: list[str],
) -> VerifiedCommitDecisionStateV2 | None:
    for step in (7, 8):
        request, source = _ready_successor_v2(
            context,
            state,
            mutation_ref=f"mutation:commit-decision:ready:evaluate:{step}",
            current_step=step,
            command=CommitDecisionCommandV2.EVALUATE,
            proposals=(proposal,),
        )
        attempt = _advance_ready_context_v2(context, request, source)
        if not _committed(attempt):
            problems.append(f"ready_evaluate_commit:{step}")
            return None
        state = _ready_state_v2(context, request)
    ready = state.snapshot
    if (
        ready.assessment is None
        or not ready.assessment.leader_ready_for_stability
        or ready.window.streak_count < ready.window.required_stability_steps
        or ready.outcome is not None
    ):
        problems.append("ready_window")
        return None
    return state


def _seal_ready_window(
    context: CommitDecisionV2ReadyContext,
    state: VerifiedCommitDecisionStateV2,
    proposal: CommitDecisionCandidateProposalV2,
    problems: list[str],
) -> VerifiedCommitDecisionStateV2 | None:
    output = CommitDecisionOutputProposalV2(
        candidate_ref=CANDIDATE_REF,
        claim_root=context.claim_root,
        output_contract_root=root_v2("commit-decision:output-contract"),
        payload={"answer": "provider-free durable evidence commit"},
    )
    seal, seal_source = _ready_successor_v2(
        context,
        state,
        mutation_ref="mutation:commit-decision:ready:seal",
        current_step=8,
        command=CommitDecisionCommandV2.SEAL,
        output=output,
    )
    seal_attempt = _advance_ready_context_v2(context, seal, seal_source)
    if not _committed(seal_attempt):
        problems.append("same_step_seal_commit")
        return None
    _expect_events(
        seal_attempt,
        ("commit_window_sealed_v2", "commit_decision_progressed_v2"),
        problems,
        "seal_trace",
    )
    sealed_state = _ready_state_v2(context, seal)
    if (
        sealed_state.snapshot.seal is None
        or sealed_state.snapshot.mutation_kind
        is not CommitDecisionMutationKindV2.SEALED
    ):
        problems.append("durable_seal")
        return None
    return sealed_state


def _finalize_ready_window(
    context: CommitDecisionV2ReadyContext,
    adapter: GovernanceStateStoreConformanceAdapterV2,
    sealed_state: VerifiedCommitDecisionStateV2,
    proposal: CommitDecisionCandidateProposalV2,
    problems: list[str],
) -> None:
    finalize, finalize_source = _ready_successor_v2(
        context,
        sealed_state,
        mutation_ref="mutation:commit-decision:ready:finalize",
        current_step=8,
        command=CommitDecisionCommandV2.EVALUATE,
        proposals=(proposal,),
    )
    finalized = _advance_ready_context_v2(
        context,
        finalize,
        finalize_source,
    )
    if not _committed(finalized):
        problems.append("evidence_finality_commit")
        return
    terminal_state = _ready_state_v2(context, finalize)
    terminal = terminal_state.snapshot
    if (
        terminal.outcome is None
        or terminal.outcome.kind is not CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT
        or not terminal.outcome.epistemically_committed
        or not terminal.outcome.delivery_eligible
        or not terminal.outcome.finality_root
        or terminal.progress is not None
    ):
        problems.append("ready_typed_terminal")
    _expect_events(
        finalized,
        ("commit_decision_outcome_committed_v2",),
        problems,
        "terminal_trace",
    )
    support = context.support_context
    restarted = adapter.restart_store_v2(support.store)
    retry = _advance_on_store_v2(
        support.domain,
        restarted,
        support.grant,
        finalize,
        None,
    )
    if retry.to_dict() != finalized.to_dict():
        problems.append("terminal_restart_exact_retry")
    try:
        rehydrated = rehydrate_commit_decision_state_v2(
            finalize.to_dict(),
            domain=support.domain,
            state_reader=restarted,
        )
        if not commit_decision_state_is_current_v2(rehydrated):
            problems.append("terminal_restart_currentness")
    except Exception:
        problems.append("terminal_restart_rehydrate")


def _ready_successor_v2(
    context: CommitDecisionV2ReadyContext,
    parent: VerifiedCommitDecisionStateV2,
    *,
    mutation_ref: str,
    current_step: int,
    command: CommitDecisionCommandV2,
    proposals: tuple[CommitDecisionCandidateProposalV2, ...] = (),
    output: CommitDecisionOutputProposalV2 | None = None,
) -> tuple[CommitDecisionRequestV2, VerifiedCommitDecisionSourceV2]:
    return prepare_commit_decision_successor_v2(
        parent_state=parent,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref=mutation_ref,
        current_step=current_step,
        mutation_issuer_ref=context.support_context.grant.issuer_ref,
        command=command,
        candidate_proposals=proposals,
        output_proposal=output,
        commit_replay_state=context.replay_state,
        risk_state=context.risk_state,
        membership_state=context.membership_state,
        support_state=context.support_state,
        evidence_state=context.evidence_state,
        stop_state=context.stop_state,
        permission_state=context.permission_state,
    )


def _advance_support_context_v2(
    context: SupportV2ConformanceContext,
    request: CommitDecisionRequestV2,
    source: object,
) -> GovernanceCommitAttemptV2:
    session = open_commit_decision_authority_session_v2(
        capability_v2(context, request.observed_epoch),
        request,
    )
    return advance_commit_decision_v2(
        request,
        source=source,
        authority_session=session,
    )


def _advance_ready_context_v2(
    context: CommitDecisionV2ReadyContext,
    request: CommitDecisionRequestV2,
    source: object,
) -> GovernanceCommitAttemptV2:
    support = context.support_context
    return _advance_on_store_v2(
        support.domain,
        support.store,
        support.grant,
        request,
        source,
    )


def _advance_on_store_v2(
    domain: AuthorityDomainV2,
    store: GovernanceStateStoreV2,
    grant: GovernanceIssuerGrantV2,
    request: CommitDecisionRequestV2,
    source: object,
) -> GovernanceCommitAttemptV2:
    capability: GovernanceIssuerCapabilityV2 = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        RUN_REF,
        request.observed_epoch,
    )
    session = open_commit_decision_authority_session_v2(capability, request)
    return advance_commit_decision_v2(
        request,
        source=source,
        authority_session=session,
    )


def _ready_state_v2(
    context: CommitDecisionV2ReadyContext,
    request: CommitDecisionRequestV2,
) -> VerifiedCommitDecisionStateV2:
    support = context.support_context
    return rehydrate_commit_decision_state_v2(
        request.to_dict(),
        domain=support.domain,
        state_reader=support.store,
    )


def _committed(attempt: GovernanceCommitAttemptV2) -> bool:
    return (
        attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        and attempt.committed_transition is not None
    )


def _expect_events(
    attempt: GovernanceCommitAttemptV2,
    expected: tuple[str, ...],
    problems: list[str],
    label: str,
) -> None:
    if attempt.committed_transition is None:
        problems.append(label)
        return
    events = attempt.committed_transition.batch.trace_batch.events
    if tuple(item.event_type for item in events) != expected:
        problems.append(label)
        return
    read_set_root = attempt.committed_transition.batch.read_set.root()
    if any(item.lineage.get("read_set_root") != read_set_root for item in events):
        problems.append(f"{label}:read_set_root")


for _public in (run_governance_commit_decision_conformance_v2,):
    _public.__module__ = "pheroos.conformance"
del _public


__all__ = [
    "GOVERNANCE_COMMIT_DECISION_CONFORMANCE_VERSION_V2",
    "run_governance_commit_decision_conformance_v2",
]
