from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields, replace
from itertools import count, product

import pytest

import tests.governance.test_commit_engine as commit_engine_tests
import tests.governance.test_commit_certificate as certificate_tests
from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.commit_state import (
    AuthorityScope,
    CommitFinalityStatus,
    DecisionOutcome,
    DecisionOutcomeKind,
    DecisionPhase,
    DecisionProgress,
    ReplayNamespace,
    ReplayReceipt,
    _finality_unavailable_at_deadline,
    advance_commit_window_state,
    commit_window_seal_for_state,
    commit_window_seal_is_authoritative,
    commit_window_seal_is_current,
    commit_window_seal_matches_receipt,
    commit_liveness_input_is_authoritative,
    decision_outcome_is_authoritative,
    decision_progress_is_authoritative,
    issue_commit_liveness_input,
    record_commit_replay_receipts,
    reduce_commit_liveness,
    reset_commit_window_state,
    restart_commit_window_epoch,
    select_terminal_outcome_kind,
)
from pheroos.governance.certificate import (
    evidence_commit_certificate_body_root,
    issue_evidence_commit_certificate,
    issue_local_commit_receipt,
    output_payload_fingerprint,
    verify_evidence_commit_finality,
    verify_local_commit_finality,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import CommitAssurance
from tests.governance.test_commit_window import (
    _advance,
    _assessment,
    _epoch_threshold,
    _scenario,
    _window,
)


_IDS = count(1)


def _liveness(
    state,
    scenario,
    *,
    assessment,
    current_step: int,
    finality_status: CommitFinalityStatus = CommitFinalityStatus.NOT_REQUIRED,
    finality_verification=None,
    certificate_ref: str = "",
    invalid_reason_codes=(),
    safety_violation_reason_codes=(),
    blocked_reason_codes=(),
    finality_reason_codes=(),
    next_required_inputs=(),
    replay_state=None,
    previous_progress=None,
):
    index = next(_IDS)
    return issue_commit_liveness_input(
        state,
        assessment=assessment,
        replay_state=(scenario.replay_state if replay_state is None else replay_state),
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        support_replay_state=scenario.support_replay_state,
        commit_policy=scenario.policy,
        previous_progress=previous_progress,
        current_step=current_step,
        finality_status=finality_status,
        finality_verification=finality_verification,
        certificate_ref=certificate_ref,
        invalid_reason_codes=invalid_reason_codes,
        safety_violation_reason_codes=safety_violation_reason_codes,
        blocked_reason_codes=blocked_reason_codes,
        finality_reason_codes=finality_reason_codes,
        next_required_inputs=next_required_inputs,
        input_id=f"liveness:{scenario.run_id}:{index}",
        issuer_id="governance:liveness",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:test:liveness:{scenario.run_id}:{index}",
        trace_event_id=f"trace:liveness:{scenario.run_id}:{index}",
    )


def _one_ready_step():
    scenario = _scenario()
    assessment = _assessment(scenario, step=5)
    state = _advance(
        _window(scenario),
        scenario,
        step=5,
        assessment=assessment,
    )
    return scenario, assessment, state


def _stable_step():
    scenario, first, state = _one_ready_step()
    second = _assessment(scenario, step=6)
    state = _advance(
        state,
        scenario,
        step=6,
        assessment=second,
    )
    return scenario, second, state


def _local_receipt(state, scenario, assessment, *, current_step: int):
    output_ref = output_payload_fingerprint(
        {"candidate_id": state.leader_candidate_id, "run_id": state.run_id},
        profile=state.profile,
    )
    return issue_local_commit_receipt(
        scenario.context,
        assessment,
        state,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
        output_payload_fingerprint=output_ref,
        receipt_id=f"receipt:liveness:{scenario.run_id}",
        issuer_id="governance:receipt",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=current_step,
        provenance=f"urn:test:receipt:{scenario.run_id}",
        trace_event_id=f"trace:receipt:{scenario.run_id}",
    )


def _verified_local_finality(state, scenario, assessment, *, current_step: int):
    receipt = _local_receipt(
        state,
        scenario,
        assessment,
        current_step=current_step,
    )
    return verify_local_commit_finality(
        receipt,
        scenario.context,
        assessment,
        state,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
        current_step=current_step,
        verifier_id="governance:certificate-verifier",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:local-finality",
        trace_event_id=f"trace:local-finality:{state.run_id}",
    )


def test_before_deadline_returns_issued_non_terminal_progress() -> None:
    scenario, assessment, state = _one_ready_step()
    facts = _liveness(
        state,
        scenario,
        assessment=assessment,
        current_step=5,
    )
    result = reduce_commit_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=facts,
    )
    assert type(result) is DecisionProgress
    assert result.phase is DecisionPhase.QUORUM_PENDING
    assert result.terminal is False
    assert result.window_count == 1
    assert result.minimum_stability_steps == 2
    assert result.next_required_inputs == ("consecutive_stability_assessment",)
    assert decision_progress_is_authoritative(result)
    assert result.context_ref == assessment.context_fingerprint
    assert result.risk_chain_state_root == assessment.risk_chain_state_fingerprint
    assert result.collective_evidence_root == assessment.collective_evidence_root
    assert result.window_state_ref == facts.window_state_ref


def test_stable_local_commit_is_terminal_but_never_pre_authorizes_actions() -> None:
    scenario, assessment, state = _stable_step()
    verification = _verified_local_finality(
        state,
        scenario,
        assessment,
        current_step=6,
    )
    facts = _liveness(
        state,
        scenario,
        assessment=assessment,
        current_step=6,
        finality_status=CommitFinalityStatus.VERIFIED,
        finality_verification=verification,
    )
    outcome = reduce_commit_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=facts,
    )
    assert type(outcome) is DecisionOutcome
    assert outcome.kind is DecisionOutcomeKind.EVIDENCE_COMMIT
    assert outcome.terminal is True
    assert outcome.authoritative_commit is True
    assert outcome.epistemically_committed is True
    assert outcome.authority_scope is AuthorityScope.GOVERNANCE_LOCAL
    assert outcome.candidate_id == scenario.leader_id
    assert outcome.delivery_eligible is True
    assert outcome.publication_eligible is False
    assert outcome.execution_eligible is False
    assert decision_outcome_is_authoritative(outcome)
    assert (
        reduce_commit_liveness(
            state,
            commit_policy=scenario.policy,
            liveness_input=facts,
        )
        is outcome
    )
    with pytest.raises(GovernanceError, match="already terminal"):
        advance_commit_window_state(
            state,
            assessment=_assessment(scenario, step=7),
            commit_policy=scenario.policy,
            threshold_snapshot=scenario.threshold,
            current_step=7,
        )


@pytest.mark.parametrize("late_by", [0, 1, 20])
def test_deadline_or_late_call_always_returns_deliverable_non_commit_fallback(
    late_by: int,
) -> None:
    scenario, assessment, state = _one_ready_step()
    facts = _liveness(
        state,
        scenario,
        assessment=assessment,
        current_step=state.absolute_deadline_step + late_by,
    )
    outcome = reduce_commit_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=facts,
    )
    assert type(outcome) is DecisionOutcome
    assert outcome.kind is DecisionOutcomeKind.SAFE_FALLBACK
    assert (
        outcome.candidate_id == scenario.policy.terminal_outcome.safe_fallback_candidate
    )
    assert outcome.terminal and outcome.delivery_eligible
    assert not outcome.authoritative_commit
    assert not outcome.epistemically_committed
    assert not outcome.publication_eligible
    assert not outcome.execution_eligible
    assert "deadline_reached" in outcome.reason_codes


def test_declared_advisory_deadline_is_terminal_non_authoritative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = commit_engine_tests._policy

    def advisory_policy(**kwargs):
        policy = original(**kwargs)
        return replace(
            policy,
            terminal_outcome=replace(
                policy.terminal_outcome,
                deadline_outcome="advisory",
            ),
        )

    monkeypatch.setattr(commit_engine_tests, "_policy", advisory_policy)
    scenario = commit_engine_tests._scenario()
    assessment = _assessment(scenario, step=5)
    state = _advance(_window(scenario), scenario, step=5, assessment=assessment)
    facts = _liveness(
        state,
        scenario,
        assessment=assessment,
        current_step=state.absolute_deadline_step,
    )
    outcome = reduce_commit_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=facts,
    )
    assert outcome.kind is DecisionOutcomeKind.ADVISORY
    assert outcome.delivery_eligible
    assert not outcome.authoritative_commit
    assert not outcome.epistemically_committed


def test_missing_local_receipt_waits_then_falls_back_without_commit() -> None:
    scenario, assessment, state = _stable_step()
    pending = _liveness(
        state,
        scenario,
        assessment=assessment,
        current_step=6,
        finality_status=CommitFinalityStatus.NOT_REQUIRED,
    )
    progress = reduce_commit_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=pending,
    )
    assert type(progress) is DecisionProgress
    assert progress.phase is DecisionPhase.QUORUM_PENDING
    assert progress.terminal is False
    assert progress.next_required_inputs == ("local_commit_receipt",)

    deadline = _liveness(
        state,
        scenario,
        assessment=assessment,
        current_step=state.absolute_deadline_step,
        finality_status=CommitFinalityStatus.NOT_REQUIRED,
    )
    outcome = reduce_commit_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=deadline,
    )
    assert outcome.kind is DecisionOutcomeKind.SAFE_FALLBACK
    assert outcome.delivery_eligible
    assert not outcome.epistemically_committed


def test_evidence_bound_receipt_cannot_commit_after_its_sealed_step() -> None:
    scenario, assessment, state = _stable_step()
    verification = _verified_local_finality(
        state,
        scenario,
        assessment,
        current_step=6,
    )
    pending = reduce_commit_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=_liveness(
            state,
            scenario,
            assessment=assessment,
            current_step=6,
            finality_status=CommitFinalityStatus.PENDING,
        ),
    )
    assert type(pending) is DecisionProgress
    assert pending.phase is DecisionPhase.PROVISIONAL
    with pytest.raises(GovernanceError, match="freshly verified"):
        _liveness(
            state,
            scenario,
            assessment=assessment,
            current_step=7,
            previous_progress=pending,
            finality_status=CommitFinalityStatus.VERIFIED,
            finality_verification=verification,
        )


def test_replay_head_change_after_assessment_requires_reassessment() -> None:
    scenario, assessment, state = _stable_step()
    _local_receipt(state, scenario, assessment, current_step=6)
    before = _liveness(
        state,
        scenario,
        assessment=assessment,
        current_step=6,
        finality_status=CommitFinalityStatus.PENDING,
    )
    progress = reduce_commit_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=before,
    )
    changed = record_commit_replay_receipts(
        scenario.replay_state,
        current_step=7,
        receipts=(
            ReplayReceipt(
                namespace=ReplayNamespace.WITNESS,
                record_id=f"witness:{scenario.run_id}:late",
                nonce=f"nonce:witness:{scenario.run_id}:late",
                payload_fingerprint="sha256:" + ("d" * 64),
                target=state.target,
                candidate_id=state.leader_candidate_id,
                epoch=state.epoch,
                principal_id="principal:late-witness",
            ),
        ),
    )
    with pytest.raises(GovernanceError, match="changed after the assessment"):
        _liveness(
            state,
            scenario,
            assessment=assessment,
            current_step=7,
            replay_state=changed,
            previous_progress=progress,
        )
    assert not commit_liveness_input_is_authoritative(before)
    # The historical exact request remains replay-idempotent even though it is
    # no longer eligible to authorize a new transition from current heads.
    assert (
        reduce_commit_liveness(
            state,
            commit_policy=scenario.policy,
            liveness_input=before,
        )
        is progress
    )


@pytest.mark.parametrize(
    "assurance",
    (CommitAssurance.CERTIFIED, CommitAssurance.DISTRIBUTED),
)
@pytest.mark.parametrize(
    "status",
    (
        CommitFinalityStatus.PENDING,
        CommitFinalityStatus.PROVISIONAL,
        CommitFinalityStatus.UNAVAILABLE,
    ),
)
def test_required_finality_states_become_unavailable_only_at_deadline(
    assurance: CommitAssurance,
    status: CommitFinalityStatus,
) -> None:
    assert not _finality_unavailable_at_deadline(
        assurance=assurance,
        finality_status=status,
        stability_satisfied=True,
        deadline_reached=False,
    )
    assert _finality_unavailable_at_deadline(
        assurance=assurance,
        finality_status=status,
        stability_satisfied=True,
        deadline_reached=True,
    )
    assert not _finality_unavailable_at_deadline(
        assurance=assurance,
        finality_status=status,
        stability_satisfied=False,
        deadline_reached=True,
    )


@pytest.mark.parametrize(
    "wrong_head",
    ("risk_assessment", "threshold_snapshot", "membership_snapshot"),
)
def test_deadline_terminal_still_requires_exact_sealed_authority_roots(
    wrong_head: str,
) -> None:
    scenario, assessment, state = _one_ready_step()
    other = _scenario()
    values = {
        "risk_assessment": scenario.risk_assessment,
        "threshold_snapshot": scenario.threshold,
        "membership_snapshot": scenario.membership_snapshot,
    }
    values[wrong_head] = {
        "risk_assessment": other.risk_assessment,
        "threshold_snapshot": other.threshold,
        "membership_snapshot": other.membership_snapshot,
    }[wrong_head]
    index = next(_IDS)

    with pytest.raises(GovernanceError, match="risk or threshold root|membership root"):
        issue_commit_liveness_input(
            state,
            assessment=assessment,
            replay_state=scenario.replay_state,
            risk_chain_state=scenario.risk_chain_state,
            risk_assessment=values["risk_assessment"],
            threshold_snapshot=values["threshold_snapshot"],
            membership_snapshot=values["membership_snapshot"],
            membership_epoch_state=scenario.membership_state,
            support_replay_state=scenario.support_replay_state,
            commit_policy=scenario.policy,
            current_step=state.absolute_deadline_step,
            finality_status=CommitFinalityStatus.PENDING,
            input_id=f"liveness:{scenario.run_id}:wrong-head:{index}",
            issuer_id="governance:liveness",
            authority=AuthorityLevel.GOVERNANCE,
            provenance=f"urn:test:liveness-wrong-head:{index}",
            trace_event_id=f"trace:liveness-wrong-head:{index}",
        )


def test_terminal_priority_truth_table_is_total_and_exact() -> None:
    priority = (
        DecisionOutcomeKind.INVALID,
        DecisionOutcomeKind.SAFETY_VIOLATION,
        DecisionOutcomeKind.BLOCKED,
        DecisionOutcomeKind.EVIDENCE_COMMIT,
        DecisionOutcomeKind.FINALITY_UNAVAILABLE,
        DecisionOutcomeKind.SAFE_FALLBACK,
    )
    for values in product((False, True), repeat=6):
        expected = next(
            (kind for enabled, kind in zip(values, priority, strict=True) if enabled),
            None,
        )
        assert (
            select_terminal_outcome_kind(
                invalid=values[0],
                safety_violation=values[1],
                blocked=values[2],
                evidence_commit_ready=values[3],
                finality_unavailable=values[4],
                deadline_reached=values[5],
                deadline_outcome="safe_fallback",
            )
            is expected
        )
    assert (
        select_terminal_outcome_kind(
            invalid=False,
            safety_violation=False,
            blocked=False,
            evidence_commit_ready=False,
            finality_unavailable=False,
            deadline_reached=True,
            deadline_outcome="advisory",
        )
        is DecisionOutcomeKind.ADVISORY
    )


def test_simultaneous_runtime_findings_follow_invalid_safety_blocked_priority() -> None:
    scenario, assessment, state = _one_ready_step()
    facts = _liveness(
        state,
        scenario,
        assessment=assessment,
        current_step=5,
        invalid_reason_codes=("protocol_instance_invalid",),
        safety_violation_reason_codes=("equivocation",),
        blocked_reason_codes=("hard_stop",),
        finality_status=CommitFinalityStatus.CONFLICT,
    )
    outcome = reduce_commit_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=facts,
    )
    assert outcome.kind is DecisionOutcomeKind.INVALID
    assert outcome.delivery_eligible


@pytest.mark.parametrize(
    ("expected", "kwargs"),
    (
        (
            DecisionOutcomeKind.INVALID,
            {"invalid_reason_codes": ("protocol_instance_invalid",)},
        ),
        (
            DecisionOutcomeKind.SAFETY_VIOLATION,
            {"safety_violation_reason_codes": ("equivocation",)},
        ),
        (
            DecisionOutcomeKind.BLOCKED,
            {"blocked_reason_codes": ("hard_stop",)},
        ),
        (
            DecisionOutcomeKind.SAFETY_VIOLATION,
            {"finality_status": CommitFinalityStatus.CONFLICT},
        ),
    ),
)
def test_every_authoritative_terminal_finding_is_deliverable(
    expected: DecisionOutcomeKind,
    kwargs: dict[str, object],
) -> None:
    scenario, assessment, state = _one_ready_step()
    outcome = reduce_commit_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=_liveness(
            state,
            scenario,
            assessment=assessment,
            current_step=5,
            **kwargs,
        ),
    )
    assert outcome.kind is expected
    assert outcome.terminal is True
    assert outcome.delivery_eligible is True
    assert outcome.execution_eligible is False


def test_progress_and_outcome_every_lineage_leaf_is_tamper_evident() -> None:
    scenario, first_assessment, first_state = _one_ready_step()
    progress = reduce_commit_liveness(
        first_state,
        commit_policy=scenario.policy,
        liveness_input=_liveness(
            first_state,
            scenario,
            assessment=first_assessment,
            current_step=5,
        ),
    )
    assert type(progress) is DecisionProgress
    progress_fields = (
        "context_ref",
        "assessment_ref",
        "risk_assessment_root",
        "risk_chain_state_root",
        "risk_policy_root",
        "membership_root",
        "membership_snapshot_root",
        "membership_epoch_state_root",
        "threshold_root",
        "replay_state_ref",
        "replay_root",
        "support_replay_state_root",
        "support_replay_root",
        "collective_evidence_root",
        "collective_challenge_root",
        "collective_lease_root",
        "candidate_evidence_root",
        "candidate_challenge_root",
        "candidate_lease_root",
        "stop_resolution_root",
        "permission_root",
        "window_state_ref",
        "window_root",
    )
    replacement = "sha256:" + ("f" * 64)
    for field_name in progress_fields:
        original = getattr(progress, field_name)
        object.__setattr__(progress, field_name, replacement)
        assert not decision_progress_is_authoritative(progress), field_name
        object.__setattr__(progress, field_name, original)
        assert decision_progress_is_authoritative(progress), field_name

    scenario, assessment, state = _stable_step()
    verification = _verified_local_finality(
        state,
        scenario,
        assessment,
        current_step=6,
    )
    outcome = reduce_commit_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=_liveness(
            state,
            scenario,
            assessment=assessment,
            current_step=6,
            finality_status=CommitFinalityStatus.VERIFIED,
            finality_verification=verification,
        ),
    )
    assert type(outcome) is DecisionOutcome
    for field_name in progress_fields:
        original = getattr(outcome, field_name)
        object.__setattr__(outcome, field_name, replacement)
        assert not decision_outcome_is_authoritative(outcome), field_name
        object.__setattr__(outcome, field_name, original)
        assert decision_outcome_is_authoritative(outcome), field_name


def test_liveness_reduction_is_exactly_idempotent_and_fork_free() -> None:
    scenario, assessment, state = _one_ready_step()
    first = _liveness(
        state,
        scenario,
        assessment=assessment,
        current_step=5,
    )
    second = _liveness(
        state,
        scenario,
        assessment=assessment,
        current_step=5,
        next_required_inputs=("different_request",),
    )
    progress = reduce_commit_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=first,
    )
    assert (
        reduce_commit_liveness(
            state,
            commit_policy=scenario.policy,
            liveness_input=first,
        )
        is progress
    )
    with pytest.raises(GovernanceError, match="would fork"):
        reduce_commit_liveness(
            state,
            commit_policy=scenario.policy,
            liveness_input=second,
        )


def test_certified_finality_commits_late_only_with_continuous_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario, assessment, state, output_ref = certificate_tests._certified_scenario(
        monkeypatch
    )
    receipt = certificate_tests._receipt(
        scenario,
        assessment,
        state,
        output_ref,
    )
    seal = commit_window_seal_for_state(state)
    assert seal is not None and commit_window_seal_is_current(seal)
    original_deadlines = (
        seal.absolute_deadline_step,
        seal.absolute_run_deadline_step,
    )
    initial = reduce_commit_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=_liveness(
            state,
            scenario,
            assessment=assessment,
            current_step=6,
            finality_status=CommitFinalityStatus.PENDING,
        ),
    )
    assert type(initial) is DecisionProgress
    assert initial.phase is DecisionPhase.PROVISIONAL
    assert initial.sealed_window and initial.heartbeat_sequence == 0

    metadata = {
        "certificate_id": f"certificate:liveness-late:{scenario.run_id}",
        "issuer_id": "governance:portable-liveness",
        "authority": AuthorityLevel.GOVERNANCE,
        "issued_at_step": 7,
        "provenance": f"urn:test:portable-liveness:{scenario.run_id}",
        "trace_event_id": f"trace:portable-liveness:{scenario.run_id}",
    }
    body_root = evidence_commit_certificate_body_root(receipt, **metadata)
    trust = {"attestation:portable:liveness": body_root}
    certificate = issue_evidence_commit_certificate(
        receipt,
        commit_policy=scenario.policy,
        issuer_attestation_refs=tuple(trust),
        trusted_issuer_attestations=trust,
        **metadata,
    )
    verification = verify_evidence_commit_finality(
        certificate,
        receipt,
        scenario.context,
        assessment,
        state,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
        trusted_issuer_attestations=trust,
        current_step=7,
        verifier_id="governance:portable-liveness-verifier",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:portable-liveness-verifier",
        trace_event_id="trace:portable-liveness-verifier",
    )
    outcome = reduce_commit_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=_liveness(
            state,
            scenario,
            assessment=assessment,
            current_step=7,
            previous_progress=initial,
            finality_status=CommitFinalityStatus.VERIFIED,
            finality_verification=verification,
        ),
    )
    assert outcome.kind is DecisionOutcomeKind.EVIDENCE_COMMIT
    assert outcome.authority_scope is AuthorityScope.CERTIFIED
    assert outcome.previous_progress_ref
    assert outcome.heartbeat_sequence == 1
    assert "late_finality_verified" in outcome.reason_codes
    assert (
        outcome.absolute_deadline_step,
        outcome.absolute_run_deadline_step,
    ) == original_deadlines


def test_late_finality_step_gap_is_rejected_before_certificate_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario, assessment, state, output_ref = certificate_tests._certified_scenario(
        monkeypatch
    )
    certificate_tests._receipt(scenario, assessment, state, output_ref)
    initial = reduce_commit_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=_liveness(
            state,
            scenario,
            assessment=assessment,
            current_step=6,
            finality_status=CommitFinalityStatus.PENDING,
        ),
    )
    with pytest.raises(GovernanceError, match="exactly one logical step"):
        _liveness(
            state,
            scenario,
            assessment=assessment,
            current_step=8,
            previous_progress=initial,
            finality_status=CommitFinalityStatus.PENDING,
        )


def test_missing_heartbeat_at_deadline_is_terminal_noncommit_not_provisional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario, assessment, state, output_ref = certificate_tests._certified_scenario(
        monkeypatch
    )
    certificate_tests._receipt(scenario, assessment, state, output_ref)
    deadline = min(
        state.absolute_deadline_step,
        state.absolute_run_deadline_step,
    )
    outcome = reduce_commit_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=_liveness(
            state,
            scenario,
            assessment=assessment,
            current_step=deadline,
            finality_status=CommitFinalityStatus.UNAVAILABLE,
            finality_reason_codes=("heartbeat_missing",),
        ),
    )
    assert type(outcome) is DecisionOutcome
    assert outcome.kind is DecisionOutcomeKind.SAFE_FALLBACK
    assert outcome.terminal and outcome.delivery_eligible
    assert not outcome.authoritative_commit
    assert not outcome.epistemically_committed
    assert not outcome.heartbeat_continuous


def test_explicit_reset_unseals_consumes_budget_and_invalidates_old_proof() -> None:
    scenario, assessment, state = _stable_step()
    receipt = _local_receipt(state, scenario, assessment, current_step=6)
    seal = commit_window_seal_for_state(state)
    assert seal is not None
    old_budget = state.remaining_reset_budget
    old_deadlines = (
        state.absolute_deadline_step,
        state.absolute_run_deadline_step,
    )
    with pytest.raises(GovernanceError, match="explicit reset/unseal"):
        advance_commit_window_state(
            state,
            assessment=_assessment(scenario, step=7),
            commit_policy=scenario.policy,
            threshold_snapshot=scenario.threshold,
            current_step=7,
        )
    next_assessment = _assessment(scenario, step=7)
    reset = reset_commit_window_state(
        state,
        assessment=next_assessment,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        current_step=7,
    )
    assert reset.remaining_reset_budget == old_budget - 1
    assert reset.reset_reason == "explicit_unseal"
    assert reset.window_count == 1
    assert (
        reset.absolute_deadline_step,
        reset.absolute_run_deadline_step,
    ) == old_deadlines
    assert commit_window_seal_for_state(reset) is None
    assert commit_window_seal_is_authoritative(seal)
    assert not commit_window_seal_is_current(seal)
    assert not commit_window_seal_matches_receipt(reset, receipt)
    assert (
        reset_commit_window_state(
            state,
            assessment=next_assessment,
            commit_policy=scenario.policy,
            threshold_snapshot=scenario.threshold,
            current_step=7,
        )
        is reset
    )


def test_epoch_restart_invalidates_seal_and_consumes_both_budgets() -> None:
    scenario, assessment, state = _stable_step()
    _local_receipt(state, scenario, assessment, current_step=6)
    seal = commit_window_seal_for_state(state)
    assert seal is not None
    threshold = _epoch_threshold(
        scenario,
        epoch=state.epoch + 1,
        step=7,
    )
    restarted = restart_commit_window_epoch(
        state,
        new_epoch=state.epoch + 1,
        current_step=7,
        commit_policy=scenario.policy,
        threshold_snapshot=threshold,
        membership_root="sha256:" + ("b" * 64),
    )
    assert restarted.remaining_reset_budget == state.remaining_reset_budget - 1
    assert (
        restarted.remaining_epoch_restart_budget
        == state.remaining_epoch_restart_budget - 1
    )
    assert restarted.absolute_deadline_step == state.absolute_deadline_step
    assert restarted.absolute_run_deadline_step == state.absolute_run_deadline_step
    assert not commit_window_seal_is_current(seal)
    assert commit_window_seal_for_state(restarted) is None


def test_commit_window_seal_every_canonical_leaf_is_tamper_evident() -> None:
    scenario, assessment, state = _stable_step()
    _local_receipt(state, scenario, assessment, current_step=6)
    seal = commit_window_seal_for_state(state)
    assert seal is not None
    for record in fields(seal):
        if not record.init:
            continue
        original = getattr(seal, record.name)
        if isinstance(original, CommitAssurance):
            mutation = CommitAssurance.CERTIFIED
        elif isinstance(original, AuthorityLevel):
            mutation = AuthorityLevel.OBSERVER
        elif isinstance(original, int):
            mutation = original + 1
        elif isinstance(original, str):
            mutation = (
                "sha256:" + ("e" * 64)
                if original.startswith("sha256:")
                else f"{original}:mutation"
            )
        else:  # pragma: no cover - the v1 seal has no other public leaf kind.
            raise AssertionError(record.name)
        object.__setattr__(seal, record.name, mutation)
        assert not commit_window_seal_is_authoritative(seal), record.name
        object.__setattr__(seal, record.name, original)
        assert commit_window_seal_is_authoritative(seal), record.name


def test_liveness_input_and_reduction_are_concurrently_exactly_idempotent() -> None:
    scenario, assessment, state = _stable_step()
    _local_receipt(state, scenario, assessment, current_step=6)

    def issue():
        return issue_commit_liveness_input(
            state,
            assessment=assessment,
            replay_state=scenario.replay_state,
            risk_chain_state=scenario.risk_chain_state,
            risk_assessment=scenario.risk_assessment,
            threshold_snapshot=scenario.threshold,
            membership_snapshot=scenario.membership_snapshot,
            membership_epoch_state=scenario.membership_state,
            support_replay_state=scenario.support_replay_state,
            commit_policy=scenario.policy,
            current_step=6,
            finality_status=CommitFinalityStatus.PENDING,
            input_id=f"liveness:{scenario.run_id}:concurrent",
            issuer_id="governance:liveness",
            authority=AuthorityLevel.GOVERNANCE,
            provenance=f"urn:test:liveness:{scenario.run_id}:concurrent",
            trace_event_id=f"trace:liveness:{scenario.run_id}:concurrent",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        inputs = tuple(executor.map(lambda _: issue(), range(24)))
    assert all(item is inputs[0] for item in inputs)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = tuple(
            executor.map(
                lambda _: reduce_commit_liveness(
                    state,
                    commit_policy=scenario.policy,
                    liveness_input=inputs[0],
                ),
                range(24),
            )
        )
    assert all(item is results[0] for item in results)
    assert type(results[0]) is DecisionProgress
