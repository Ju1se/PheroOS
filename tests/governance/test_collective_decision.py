import pytest

from pheroos.governance import (
    Candidate,
    CandidateSet,
    InhibitionSignal,
    PheromonePolicy,
    PheromoneTrail,
    RecruitmentSignal,
    ScoutReport,
    clip_pheromone_deposit_strength,
    clip_pheromone_strength,
    collect_pheromone_source_diversity,
    deposit_pheromone,
    evaporate_trails,
    evaluate_collective_decision,
    pheromone_subject_id,
    pheromone_subject_type,
    score_candidates,
    score_pheromone_trails,
    validate_pheromone_trail,
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


def test_collective_decision_accepts_runtime_fallback_override() -> None:
    decision = evaluate_collective_decision(
        candidate_set=declared_candidates(),
        policy=policy(fallback_candidate="", min_independent_scouts=2, quorum_threshold=1),
        target="decision:collective",
        scout_reports=[ScoutReport("scout:a", "candidate:alpha", "evidence:a", "driver:a")],
        fallback_candidate_id="candidate:safe_fallback",
    )

    assert decision.candidate_id == "candidate:safe_fallback"
    assert decision.reason == "safe_collective_fallback"


def test_collective_decision_rejects_invalid_runtime_fallback_override() -> None:
    for fallback_candidate_id in ["candidate:missing", "candidate:alpha"]:
        with pytest.raises(GovernanceError):
            evaluate_collective_decision(
                candidate_set=declared_candidates(),
                policy=policy(fallback_candidate="", min_independent_scouts=2, quorum_threshold=1),
                target="decision:collective",
                scout_reports=[ScoutReport("scout:a", "candidate:alpha", "evidence:a", "driver:a")],
                fallback_candidate_id=fallback_candidate_id,
            )


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


def test_pheromone_evaporation_reduces_all_kinds_deterministically() -> None:
    trails = evaporate_trails(
        [
            pheromone("candidate:alpha", strength=8, kind="positive"),
            pheromone("candidate:alpha", strength=8, kind="negative"),
            pheromone("candidate:alpha", strength=8, kind="cautionary"),
            pheromone("candidate:alpha", strength=8, kind="novelty"),
            pheromone("candidate:alpha", strength=8, kind="stale"),
        ],
        pheromone_policy(evaporation_rate=0.25),
        current_step=1,
    )

    assert [trail.kind for trail in trails] == ["positive", "negative", "cautionary", "novelty", "stale"]
    assert [trail.strength for trail in trails] == [6, 6, 6, 6, 6]
    assert [trail.updated_at_step for trail in trails] == [1, 1, 1, 1, 1]


def test_exponential_linear_and_step_pheromone_decay_are_deterministic() -> None:
    default_exponential = evaporate_trails(
        [pheromone("candidate:alpha", strength=8, updated_at_step=0)],
        PheromonePolicy(enabled=True, evaporation_rate=0.25),
        current_step=2,
    )
    exponential = evaporate_trails(
        [pheromone("candidate:alpha", strength=8, updated_at_step=0)],
        pheromone_policy(evaporation_rate=0.25, decay_model="exponential"),
        current_step=2,
    )
    linear = evaporate_trails(
        [pheromone("candidate:alpha", strength=8, updated_at_step=0)],
        pheromone_policy(evaporation_rate=0.25, decay_model="linear"),
        current_step=2,
    )
    step = evaporate_trails(
        [pheromone("candidate:alpha", strength=8, updated_at_step=0)],
        pheromone_policy(evaporation_rate=0.25, decay_model="step"),
        current_step=2,
    )

    assert default_exponential[0].strength == 4.5
    assert exponential[0].strength == 4.5
    assert linear[0].strength == 4
    assert step[0].strength == 6


def test_pheromone_strength_is_clipped_to_declared_bounds() -> None:
    policy = pheromone_policy(min_strength=1, max_strength=5)
    deposited = deposit_pheromone(
        pheromone(
            "candidate:alpha",
            strength=8,
            route_id="route:alpha",
            tool_id="tool:review",
            source_id="agent:alpha",
            source_role="scout",
        ),
        policy,
        candidate_set=declared_candidates(),
    )

    assert clip_pheromone_strength(-1, policy) == 1
    assert deposited.strength == 5
    assert deposited.route_id == "route:alpha"
    assert deposited.tool_id == "tool:review"
    assert deposited.source_id == "agent:alpha"
    assert deposited.source_role == "scout"


def test_pheromone_deposit_is_clipped_to_per_round_cap() -> None:
    policy = pheromone_policy(max_strength=10, per_round_deposit_cap=4)
    deposited = deposit_pheromone(
        pheromone("candidate:alpha", strength=8),
        policy,
        candidate_set=declared_candidates(),
    )

    assert clip_pheromone_deposit_strength(8, policy) == 4
    assert deposited.strength == 4


def test_candidate_subject_scores_declared_candidate() -> None:
    trail = pheromone("", subject_type="candidate", subject_id="candidate:alpha", strength=2)

    scores = score_pheromone_trails(
        candidate_set=declared_candidates(),
        policy=pheromone_policy(per_source_cap=100),
        trails=[trail],
    )

    assert pheromone_subject_type(trail) == "candidate"
    assert pheromone_subject_id(trail) == "candidate:alpha"
    assert scores["candidate:alpha"] == 2


def test_non_candidate_pheromone_subjects_validate_without_candidate_scoring() -> None:
    marks = [
        pheromone("", subject_type="route", subject_id="route:research"),
        pheromone("", subject_type="tool", subject_id="tool:parser"),
        pheromone("", subject_type="evidence", subject_id="evidence:a"),
        pheromone("", subject_type="agent", subject_id="agent:a"),
    ]

    for mark in marks:
        validate_pheromone_trail(mark, pheromone_policy(), candidate_set=declared_candidates())
    scores = score_pheromone_trails(
        candidate_set=declared_candidates(),
        policy=pheromone_policy(),
        trails=marks,
    )

    assert scores == {
        "candidate:alpha": 0.0,
        "candidate:beta": 0.0,
        "candidate:safe_fallback": 0.0,
    }


def test_legacy_candidate_pheromone_form_remains_compatible() -> None:
    trail = PheromoneTrail(
        "candidate:alpha",
        1,
        provenance="driver:a",
        trace_event_id="trace:pheromone",
    )

    validate_pheromone_trail(trail, pheromone_policy(), candidate_set=declared_candidates())

    assert pheromone_subject_type(trail) == "candidate"
    assert pheromone_subject_id(trail) == "candidate:alpha"


def test_undeclared_candidate_subject_is_rejected() -> None:
    with pytest.raises(GovernanceError):
        validate_pheromone_trail(
            pheromone("", subject_type="candidate", subject_id="candidate:missing"),
            pheromone_policy(),
            candidate_set=declared_candidates(),
        )


def test_positive_negative_and_cautionary_pheromone_have_distinct_scores() -> None:
    scores = score_pheromone_trails(
        candidate_set=declared_candidates(),
        policy=pheromone_policy(cautionary_override_threshold=100, per_source_cap=100),
        trails=[
            pheromone("candidate:alpha", strength=3, kind="positive"),
            pheromone("candidate:alpha", strength=1, kind="negative"),
            pheromone("candidate:beta", strength=2, kind="cautionary"),
        ],
    )

    assert scores["candidate:alpha"] == 2
    assert scores["candidate:beta"] == -2


def test_cautionary_pheromone_suppresses_positive_support_at_threshold() -> None:
    scores = score_pheromone_trails(
        candidate_set=declared_candidates(),
        policy=pheromone_policy(cautionary_override_threshold=2, per_source_cap=100),
        trails=[
            pheromone("candidate:alpha", strength=5, kind="positive"),
            pheromone("candidate:alpha", strength=2, kind="cautionary"),
        ],
    )

    assert scores["candidate:alpha"] == -2


def test_novelty_pheromone_uses_declared_weight() -> None:
    scores = score_pheromone_trails(
        candidate_set=declared_candidates(),
        policy=pheromone_policy(novelty_weight=0.5, per_source_cap=100),
        trails=[pheromone("candidate:alpha", strength=6, kind="novelty")],
    )

    assert scores["candidate:alpha"] == 3


def test_per_source_cap_limits_total_scoring_contribution() -> None:
    scores = score_pheromone_trails(
        candidate_set=declared_candidates(),
        policy=pheromone_policy(per_source_cap=4),
        trails=[
            pheromone("candidate:alpha", strength=3, source_id="agent:a", provenance="driver:a"),
            pheromone("candidate:alpha", strength=3, source_id="agent:a", provenance="driver:a"),
            pheromone("candidate:alpha", strength=3, source_id="agent:b", provenance="driver:b"),
        ],
    )

    assert scores["candidate:alpha"] == 7


def test_source_diversity_is_counted_and_can_gate_pheromone_scoring() -> None:
    one_source = [pheromone("candidate:alpha", strength=2, source_id="agent:a", provenance="driver:a")]
    two_sources = one_source + [pheromone("candidate:alpha", strength=2, source_id="agent:b", provenance="driver:b")]
    policy = pheromone_policy(min_source_diversity=2, per_source_cap=100)

    assert collect_pheromone_source_diversity(
        candidate_set=declared_candidates(),
        trails=two_sources,
        policy=policy,
    )["candidate:alpha"] == 2
    assert score_pheromone_trails(
        candidate_set=declared_candidates(),
        policy=policy,
        trails=one_source,
    )["candidate:alpha"] == 0
    assert score_pheromone_trails(
        candidate_set=declared_candidates(),
        policy=policy,
        trails=two_sources,
    )["candidate:alpha"] == 4


def test_expired_ttl_pheromone_becomes_stale_and_does_not_score() -> None:
    trails = evaporate_trails(
        [pheromone("candidate:alpha", strength=5, ttl_steps=2)],
        pheromone_policy(),
        current_step=2,
    )
    scores = score_pheromone_trails(
        candidate_set=declared_candidates(),
        policy=pheromone_policy(),
        trails=[pheromone("candidate:alpha", strength=5, ttl_steps=2)],
        current_step=2,
    )

    assert trails[0].kind == "stale"
    assert trails[0].strength == 0
    assert scores["candidate:alpha"] == 0


def test_stale_or_expired_pheromone_cannot_cause_commit() -> None:
    expired = evaporate_trails(
        [pheromone("candidate:alpha", strength=10, ttl_steps=1)],
        pheromone_policy(per_source_cap=100),
        current_step=1,
    )[0]
    for trail in [
        pheromone("candidate:alpha", strength=10, kind="stale"),
        expired,
    ]:
        decision = evaluate_collective_decision(
            candidate_set=declared_candidates(),
            policy=policy(
                min_independent_scouts=2,
                quorum_threshold=5,
                pheromone_enabled=True,
                pheromone_require_provenance=True,
                pheromone_require_trace=True,
                pheromone_per_source_cap=100,
            ),
            target="decision:collective",
            scout_reports=[
                ScoutReport("scout:a", "candidate:alpha", "evidence:a", "driver:a"),
                ScoutReport("scout:b", "candidate:alpha", "evidence:b", "driver:b"),
            ],
            pheromone_trails=[trail],
        )

        assert decision.candidate_id == "candidate:safe_fallback"
        assert decision.reason == "safe_collective_fallback"


def test_pheromone_requires_provenance_and_trace_when_policy_requires_them() -> None:
    policy = pheromone_policy()

    with pytest.raises(GovernanceError):
        validate_pheromone_trail(
            PheromoneTrail("candidate:alpha", 1, trace_event_id="trace:1"),
            policy,
            candidate_set=declared_candidates(),
        )
    with pytest.raises(GovernanceError):
        validate_pheromone_trail(
            PheromoneTrail("candidate:alpha", 1, provenance="source"),
            policy,
            candidate_set=declared_candidates(),
        )


def test_pheromone_provenance_and_trace_enforcement_is_policy_controlled() -> None:
    validate_pheromone_trail(
        PheromoneTrail("candidate:alpha", 1),
        pheromone_policy(require_provenance=False, require_trace=False),
        candidate_set=declared_candidates(),
    )


def test_invalid_pheromone_kind_steps_strength_and_candidate_are_rejected() -> None:
    policy = pheromone_policy(require_provenance=False, require_trace=False)

    for trail in [
        PheromoneTrail("candidate:alpha", 1, kind="unsupported"),
        PheromoneTrail("candidate:alpha", -1),
        PheromoneTrail("candidate:alpha", 1, deposited_at_step=2, updated_at_step=1),
        PheromoneTrail("candidate:alpha", 1, ttl_steps=-1),
        PheromoneTrail("candidate:missing", 1),
    ]:
        with pytest.raises(GovernanceError):
            validate_pheromone_trail(trail, policy, candidate_set=declared_candidates())


def test_high_pheromone_without_independent_scouts_falls_back_safely() -> None:
    decision = evaluate_collective_decision(
        candidate_set=declared_candidates(),
        policy=policy(
            min_independent_scouts=2,
            quorum_threshold=5,
            pheromone_enabled=True,
            pheromone_require_provenance=True,
            pheromone_require_trace=True,
        ),
        target="decision:collective",
        scout_reports=[],
        pheromone_trails=[pheromone("candidate:alpha", strength=10, kind="positive")],
    )

    assert decision.candidate_id == "candidate:safe_fallback"
    assert decision.reason == "safe_collective_fallback"


def test_novelty_only_pheromone_without_independent_scouts_falls_back_safely() -> None:
    decision = evaluate_collective_decision(
        candidate_set=declared_candidates(),
        policy=policy(
            min_independent_scouts=1,
            quorum_threshold=1,
            pheromone_enabled=True,
            pheromone_require_provenance=True,
            pheromone_require_trace=True,
            pheromone_novelty_weight=10,
        ),
        target="decision:collective",
        scout_reports=[],
        pheromone_trails=[pheromone("candidate:alpha", strength=10, kind="novelty")],
    )

    assert decision.candidate_id == "candidate:safe_fallback"
    assert decision.reason == "safe_collective_fallback"


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


def pheromone_policy(**overrides: object) -> PheromonePolicy:
    values = {
        "enabled": True,
        "evaporation_rate": 0.25,
        "decay_model": "exponential",
        "min_strength": 0.0,
        "max_strength": 10.0,
        "positive_weight": 1.0,
        "negative_weight": 1.0,
        "cautionary_weight": 1.0,
        "cautionary_override_threshold": 1.0,
        "novelty_weight": 0.5,
        "per_source_cap": 3.0,
        "per_round_deposit_cap": 5.0,
        "min_source_diversity": 1,
        "require_provenance": True,
        "require_trace": True,
    }
    values.update(overrides)
    return PheromonePolicy(**values)


def pheromone(candidate_id: str, **overrides: object) -> PheromoneTrail:
    values = {
        "candidate_id": candidate_id,
        "strength": 1.0,
        "target": "decision:collective",
        "kind": "positive",
        "source_id": "agent:a",
        "source_role": "scout",
        "evidence_id": "evidence:a",
        "provenance": "driver:a",
        "trace_event_id": "trace:pheromone",
        "deposited_at_step": 0,
        "updated_at_step": 0,
        "ttl_steps": None,
    }
    values.update(overrides)
    return PheromoneTrail(**values)
