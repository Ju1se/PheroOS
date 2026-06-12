import pytest

from pheroos.governance import (
    Candidate,
    CandidateSet,
    InhibitionSignal,
    PheromonePolicy,
    PheromoneTrail,
    RecruitmentSignal,
    ScoutReport,
    evaporate_trails,
    evaluate_collective_decision,
    score_candidates,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol import CollectiveDecisionPolicy


def test_consensus_succeeds_with_enough_independent_scout_reports() -> None:
    decision = evaluate_collective_decision(
        candidate_set=declared_candidates(),
        policy=policy(min_independent_scouts=2, quorum_threshold=2),
        target="decision:collective",
        scout_reports=[
            ScoutReport("scout:a", "candidate:alpha", "evidence:a", "driver:a"),
            ScoutReport("scout:b", "candidate:alpha", "evidence:b", "driver:b"),
        ],
    )

    assert decision.committed is True
    assert decision.candidate_id == "candidate:alpha"
    assert decision.reason == "collective_consensus"


def test_consensus_falls_back_when_scout_threshold_is_not_met() -> None:
    decision = evaluate_collective_decision(
        candidate_set=declared_candidates(),
        policy=policy(min_independent_scouts=2, quorum_threshold=1),
        target="decision:collective",
        scout_reports=[ScoutReport("scout:a", "candidate:alpha", "evidence:a", "driver:a")],
    )

    assert decision.committed is True
    assert decision.candidate_id == "candidate:safe_fallback"
    assert decision.reason == "safe_collective_fallback"


def test_recruitment_increases_candidate_support_when_enabled() -> None:
    state = score_candidates(
        candidate_set=declared_candidates(),
        policy=policy(recruitment_enabled=True),
        scout_reports=[ScoutReport("scout:a", "candidate:alpha", "evidence:a", "driver:a")],
        recruitment_signals=[RecruitmentSignal("signal:a", "candidate:alpha", strength=2)],
    )

    assert state.scores["candidate:alpha"] == 3


def test_recruitment_is_ignored_when_disabled() -> None:
    state = score_candidates(
        candidate_set=declared_candidates(),
        policy=policy(recruitment_enabled=False),
        scout_reports=[ScoutReport("scout:a", "candidate:alpha", "evidence:a", "driver:a")],
        recruitment_signals=[RecruitmentSignal("signal:a", "candidate:alpha", strength=2)],
    )

    assert state.scores["candidate:alpha"] == 1


def test_inhibition_decreases_candidate_support_when_enabled() -> None:
    state = score_candidates(
        candidate_set=declared_candidates(),
        policy=policy(inhibition_enabled=True),
        scout_reports=[ScoutReport("scout:a", "candidate:alpha", "evidence:a", "driver:a", support=3)],
        inhibition_signals=[InhibitionSignal("signal:a", "candidate:alpha", strength=2)],
    )

    assert state.scores["candidate:alpha"] == 1


def test_inhibition_is_ignored_when_disabled() -> None:
    state = score_candidates(
        candidate_set=declared_candidates(),
        policy=policy(inhibition_enabled=False),
        scout_reports=[ScoutReport("scout:a", "candidate:alpha", "evidence:a", "driver:a", support=3)],
        inhibition_signals=[InhibitionSignal("signal:a", "candidate:alpha", strength=2)],
    )

    assert state.scores["candidate:alpha"] == 3


def test_pheromone_evaporation_reduces_trail_strength() -> None:
    trails = evaporate_trails(
        [PheromoneTrail("candidate:alpha", strength=8)],
        PheromonePolicy(enabled=True, evaporation_rate=0.25),
    )

    assert trails[0].strength == 6


def test_undeclared_candidate_cannot_enter_collective_decision() -> None:
    with pytest.raises(GovernanceError):
        evaluate_collective_decision(
            candidate_set=declared_candidates(),
            policy=policy(),
            target="decision:collective",
            scout_reports=[ScoutReport("scout:a", "candidate:missing", "evidence:a", "driver:a")],
        )


def test_scout_report_requires_evidence_provenance() -> None:
    with pytest.raises(GovernanceError):
        score_candidates(
            candidate_set=declared_candidates(),
            policy=policy(),
            scout_reports=[ScoutReport("scout:a", "candidate:alpha", "evidence:a", "")],
        )


def declared_candidates() -> CandidateSet:
    return CandidateSet(
        [
            Candidate(id="candidate:alpha", target="decision:collective"),
            Candidate(id="candidate:beta", target="decision:collective"),
            Candidate(id="candidate:safe_fallback", target="decision:collective", safe_fallback=True),
        ]
    )


def policy(**overrides: object) -> CollectiveDecisionPolicy:
    values = {
        "mode": "hybrid",
        "min_independent_scouts": 1,
        "quorum_threshold": 1,
        "recruitment_enabled": False,
        "inhibition_enabled": False,
        "pheromone_enabled": False,
        "pheromone_evaporation_rate": 0.0,
        "fallback_candidate": "candidate:safe_fallback",
    }
    values.update(overrides)
    return CollectiveDecisionPolicy(**values)
