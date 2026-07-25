"""Private Commit TCK reference liveness handlers."""

from __future__ import annotations

from collections.abc import Sequence

from typing import Any

from pheroos.conformance._commit_reference import (
    ReferenceScenario,
    ReferenceStableCommit,
    initialize_reference_window,
)
from pheroos.conformance._commit_reference_typing import collective_commit_policy

from pheroos.governance.authority import AuthorityLevel

from pheroos.governance.certificate import (
    verify_local_commit_finality,
)

from pheroos.governance.collective import (
    ScoutReport,
)

from pheroos.governance.commit import (
    commit_assessment_fingerprint,
)

from pheroos.governance.commit_state import (
    CommitFinalityStatus,
    DecisionOutcome,
    DecisionProgress,
    commit_finality_verification_fingerprint,
    commit_window_state_fingerprint,
    decision_progress_fingerprint,
    issue_commit_liveness_input,
    reduce_commit_liveness,
)

from pheroos.governance.signal import verify_signal_input

from pheroos.conformance._commit_tck_reference.state import (
    _LIVENESS_INPUT_FIXTURE_CACHE,
    _LIVENESS_INPUT_FIXTURE_CACHE_LOCK,
)


def _initialize_window(scenario: ReferenceScenario) -> Any:
    return initialize_reference_window(scenario)


def _liveness_input(
    scenario: ReferenceScenario,
    window: Any,
    *,
    assessment: Any | None,
    step: int,
    suffix: str,
    finality_status: CommitFinalityStatus,
    finality_verification: Any | None = None,
    previous_progress: DecisionProgress | None = None,
    invalid_reason_codes: Sequence[str] = (),
    safety_violation_reason_codes: Sequence[str] = (),
    blocked_reason_codes: Sequence[str] = (),
    finality_reason_codes: Sequence[str] = (),
    next_required_inputs: Sequence[str] = (),
) -> Any:
    fixture_key = (
        scenario.namespace,
        commit_window_state_fingerprint(window),
        (commit_assessment_fingerprint(assessment) if assessment is not None else ""),
        step,
        suffix,
        finality_status.value,
        (
            commit_finality_verification_fingerprint(finality_verification)
            if finality_verification is not None
            else ""
        ),
        (
            decision_progress_fingerprint(previous_progress)
            if previous_progress is not None
            else ""
        ),
        tuple(invalid_reason_codes),
        tuple(safety_violation_reason_codes),
        tuple(blocked_reason_codes),
        tuple(finality_reason_codes),
        tuple(next_required_inputs),
    )
    with _LIVENESS_INPUT_FIXTURE_CACHE_LOCK:
        cached = _LIVENESS_INPUT_FIXTURE_CACHE.get(fixture_key)
        if cached is not None:
            return cached
    issued = issue_commit_liveness_input(
        window,
        assessment=assessment,
        replay_state=scenario.replay_state,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        support_replay_state=scenario.support_replay_state,
        commit_policy=collective_commit_policy(scenario.policy),
        previous_progress=previous_progress,
        current_step=step,
        finality_status=finality_status,
        finality_verification=finality_verification,
        invalid_reason_codes=tuple(invalid_reason_codes),
        safety_violation_reason_codes=tuple(safety_violation_reason_codes),
        blocked_reason_codes=tuple(blocked_reason_codes),
        finality_reason_codes=tuple(finality_reason_codes),
        next_required_inputs=tuple(next_required_inputs),
        input_id=f"liveness:{scenario.namespace}:{suffix}:{step}",
        issuer_id="governance:tck:liveness",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:liveness:{suffix}:{step}",
        trace_event_id=f"trace:{scenario.namespace}:liveness:{suffix}:{step}",
    )
    with _LIVENESS_INPUT_FIXTURE_CACHE_LOCK:
        _LIVENESS_INPUT_FIXTURE_CACHE[fixture_key] = issued
    return issued


def _local_commit_outcome(
    stable: ReferenceStableCommit, *, suffix: str
) -> DecisionOutcome:
    scenario = stable.scenario
    assessment = stable.assessments[-1]
    step = stable.window.last_evaluated_step
    finality = verify_local_commit_finality(
        stable.receipt,
        scenario.context,
        assessment,
        stable.window,
        commit_policy=collective_commit_policy(scenario.policy),
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
        current_step=step,
        verifier_id="governance:tck:local-finality",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:local-finality:{suffix}",
        trace_event_id=f"trace:{scenario.namespace}:local-finality:{suffix}",
    )
    result = reduce_commit_liveness(
        stable.window,
        commit_policy=collective_commit_policy(scenario.policy),
        liveness_input=_liveness_input(
            scenario,
            stable.window,
            assessment=assessment,
            step=step,
            suffix=suffix,
            finality_status=CommitFinalityStatus.VERIFIED,
            finality_verification=finality,
        ),
    )
    if type(result) is not DecisionOutcome:
        raise ValueError("local finality did not produce a terminal outcome")
    return result


def _verified_scout(
    scenario: ReferenceScenario,
    *,
    source_id: str,
    candidate_id: str,
) -> ScoutReport:
    trace_id = f"trace:{scenario.namespace}:{source_id}"
    return ScoutReport(
        source_id,
        candidate_id,
        f"evidence:{scenario.namespace}:{source_id}",
        f"runtime:tck:{source_id}",
        target=scenario.target,
        trace_event_id=trace_id,
        verification=verify_signal_input(
            target=scenario.target,
            source_id=source_id,
            subject_id=candidate_id,
            verifier_id="governance:tck:hybrid-attention",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="governance:tck:hybrid-attention",
            trace_event_id=f"{trace_id}:verified",
        ),
    )
