"""Private Commit TCK reference timeline handlers."""

from __future__ import annotations

from collections.abc import Sequence

from typing import Any

from pheroos.conformance._commit_reference import (
    ReferenceScenario,
    ReferenceStableCommit,
    assess_reference_scenario,
    reference_fingerprint,
)
from pheroos.conformance._commit_reference_typing import collective_commit_policy

from pheroos.governance.authority import AuthorityLevel

from pheroos.governance.commit_state import (
    CommitFinalityStatus,
    DecisionOutcome,
    DecisionProgress,
    reduce_commit_liveness,
)

from pheroos.governance.risk import (
    RiskBand,
    initialize_risk_assessment_chain,
    issue_commit_threshold_snapshot,
    issue_risk_assessment,
)

from pheroos.conformance._commit_tck_reference.liveness import (
    _initialize_window,
    _liveness_input,
)

from pheroos.conformance._commit_tck_reference.state import (
    _EPOCH_THRESHOLD_FIXTURE_CACHE,
    _EPOCH_THRESHOLD_FIXTURE_CACHE_LOCK,
    advance_commit_window_state,
)


def _epoch_threshold(scenario: ReferenceScenario, *, epoch: int, step: int) -> Any:
    fixture_key = (
        scenario.namespace,
        scenario.profile,
        scenario.manifest_root,
        scenario.commit_policy_root,
        epoch,
        step,
    )
    with _EPOCH_THRESHOLD_FIXTURE_CACHE_LOCK:
        cached = _EPOCH_THRESHOLD_FIXTURE_CACHE.get(fixture_key)
        if cached is not None:
            return cached
    chain = initialize_risk_assessment_chain(
        commit_policy=collective_commit_policy(scenario.policy),
        profile=scenario.profile,
        assurance=scenario.assurance,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        protocol_id=scenario.protocol_id,
        run_id=scenario.run_id,
        target=scenario.target,
        epoch=epoch,
        issuer_id="governance:tck:risk-chain",
        authority=AuthorityLevel.GOVERNANCE,
        initialized_at_step=step,
        expires_at_step=30,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:risk-chain:{epoch}",
        trace_event_id=f"trace:{scenario.namespace}:risk-chain:{epoch}",
    )
    risk, chain = issue_risk_assessment(
        chain,
        assessment_id=f"risk:{scenario.namespace}:{epoch}",
        risk_band=RiskBand.LOW,
        risk_input_fingerprints=(
            reference_fingerprint(f"risk:{scenario.namespace}:{epoch}"),
        ),
        rationale_codes=("epoch_restart",),
        assessment_method="declared-risk-matrix-v1",
        commit_policy=collective_commit_policy(scenario.policy),
        profile=scenario.profile,
        assurance=scenario.assurance,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        protocol_id=scenario.protocol_id,
        run_id=scenario.run_id,
        target=scenario.target,
        epoch=epoch,
        issuer_id="governance:tck:risk",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=step,
        expires_at_step=30,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:risk:{epoch}",
        trace_event_id=f"trace:{scenario.namespace}:risk:{epoch}",
    )
    threshold = issue_commit_threshold_snapshot(
        risk,
        chain_state=chain,
        threshold_id=f"threshold:{scenario.namespace}:{epoch}",
        commit_policy=collective_commit_policy(scenario.policy),
        issuer_id="governance:tck:threshold",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=step,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:threshold:{epoch}",
        trace_event_id=f"trace:{scenario.namespace}:threshold:{epoch}",
    )
    with _EPOCH_THRESHOLD_FIXTURE_CACHE_LOCK:
        _EPOCH_THRESHOLD_FIXTURE_CACHE[fixture_key] = threshold
    return threshold


def _deadline_outcome(
    scenario: ReferenceScenario,
    *,
    suffix: str,
    finality_status: CommitFinalityStatus = CommitFinalityStatus.PENDING,
    finality_reason_codes: Sequence[str] = (),
) -> tuple[Any, DecisionOutcome]:
    window = _initialize_window(scenario)
    assessment = assess_reference_scenario(
        scenario,
        step=5,
        suffix=f"{suffix}:assessment",
    )
    window = advance_commit_window_state(
        window,
        assessment=assessment,
        commit_policy=collective_commit_policy(scenario.policy),
        threshold_snapshot=scenario.threshold,
        current_step=5,
    )
    deadline = min(window.absolute_deadline_step, window.absolute_run_deadline_step)
    decision = reduce_commit_liveness(
        window,
        commit_policy=collective_commit_policy(scenario.policy),
        liveness_input=_liveness_input(
            scenario,
            window,
            assessment=assessment,
            step=deadline,
            suffix=f"{suffix}:deadline",
            finality_status=finality_status,
            finality_reason_codes=finality_reason_codes,
        ),
    )
    if type(decision) is not DecisionOutcome:
        raise ValueError("deadline did not produce a terminal outcome")
    return window, decision


def _heartbeat_to_deadline(
    stable: ReferenceStableCommit,
    *,
    suffix: str,
    final_status: CommitFinalityStatus,
    final_reason_codes: Sequence[str] = (),
) -> tuple[DecisionProgress, DecisionOutcome]:
    scenario = stable.scenario
    assessment = stable.assessments[-1]
    sealed_step = stable.window.last_evaluated_step
    deadline = min(
        stable.window.absolute_deadline_step,
        stable.window.absolute_run_deadline_step,
    )
    first = reduce_commit_liveness(
        stable.window,
        commit_policy=collective_commit_policy(scenario.policy),
        liveness_input=_liveness_input(
            scenario,
            stable.window,
            assessment=assessment,
            step=sealed_step,
            suffix=f"{suffix}:pending",
            finality_status=CommitFinalityStatus.PENDING,
            next_required_inputs=("finality_certificate",),
        ),
    )
    if type(first) is not DecisionProgress:
        raise ValueError("sealed pre-deadline state did not remain pending")
    progress = first
    for step in range(sealed_step + 1, deadline):
        next_value = reduce_commit_liveness(
            stable.window,
            commit_policy=collective_commit_policy(scenario.policy),
            liveness_input=_liveness_input(
                scenario,
                stable.window,
                assessment=assessment,
                step=step,
                suffix=f"{suffix}:heartbeat",
                finality_status=CommitFinalityStatus.PENDING,
                previous_progress=progress,
                next_required_inputs=("finality_certificate",),
            ),
        )
        if type(next_value) is not DecisionProgress:
            raise ValueError("pre-deadline heartbeat became terminal")
        progress = next_value
    terminal = reduce_commit_liveness(
        stable.window,
        commit_policy=collective_commit_policy(scenario.policy),
        liveness_input=_liveness_input(
            scenario,
            stable.window,
            assessment=assessment,
            step=deadline,
            suffix=f"{suffix}:deadline",
            finality_status=final_status,
            previous_progress=progress,
            finality_reason_codes=tuple(final_reason_codes),
        ),
    )
    if type(terminal) is not DecisionOutcome:
        raise ValueError("deadline heartbeat did not become terminal")
    return first, terminal
