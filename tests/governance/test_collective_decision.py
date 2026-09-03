import pytest

from pheroos.governance import (
    AuthorityLevel,
    Candidate,
    CandidateSet,
    CollectiveDecisionState,
    InhibitionSignal,
    LayerCoordinationPolicy,
    LayerProposal,
    PolicyAdjustmentProposal,
    RecruitmentSignal,
    ScoutReport,
    evaluate_collective_decision,
    evaluate_collective_decision_step,
    evaluate_layer_coordination,
    score_candidates,
    verify_signal_input,
)
from pheroos.governance.pheromone import (
    PheromoneDiffusionPolicy,
    PheromoneEdge,
    PheromoneNeighborhood,
    PheromonePolicy,
    PheromoneSubject,
    PheromoneTrail,
    clip_pheromone_deposit_strength,
    clip_pheromone_strength,
    collect_pheromone_source_diversity,
    deposit_pheromone,
    diffuse_pheromone_trails,
    evaporate_trails,
    pheromone_subject_id,
    pheromone_subject_type,
    score_pheromone_trails,
    score_pheromone_trails_with_breakdown,
    pheromone_lineage,
    validate_pheromone_trail,
    validate_pheromone_topology,
)
from pheroos.governance._swarm.scoring import candidate_score_lineage
from pheroos.governance._swarm.scoring import validate_score_breakdown
from pheroos.governance.pheromone_feedback import (
    PheromoneFeedback,
    reinforce_pheromone_trails,
    validate_pheromone_feedback,
)
from pheroos.governance.policy_adjustment import validate_policy_adjustment_proposal
from pheroos.protocol.models import PheromoneKindProfile
from pheroos.governance.errors import GovernanceError
from pheroos.governance._pheromone.records import PheromoneLifecycleRecord
from pheroos.governance._swarm.trace import _clip_causal_lineage
from pheroos.protocol import CollectiveDecisionPolicy


TARGET = "decision:collective"


def test_clip_causal_lineage_rejects_corrupted_internal_json() -> None:
    record = PheromoneLifecycleRecord(
        action="clip",
        target=TARGET,
        candidate_id="candidate:alpha",
        subject_type="candidate",
        subject_id="candidate:alpha",
        kind="positive",
        source_kind="positive",
        source_id="agent:one",
        provenance="evidence:one",
        source_trace_event_id="trace:source",
        trace_event_id="trace:clip",
        old_strength=1.0,
        new_strength=1.0,
        _causal_payload_json="{",
    )

    with pytest.raises(GovernanceError, match="not canonical JSON"):
        _clip_causal_lineage(record)


def verified_scout(
    source_id: str,
    candidate_id: str = "candidate:alpha",
    *,
    support: float = 1.0,
) -> ScoutReport:
    trace_id = f"trace:{source_id}"
    return ScoutReport(
        source_id,
        candidate_id,
        f"evidence:{source_id}",
        f"driver:{source_id}",
        support=support,
        target=TARGET,
        trace_event_id=trace_id,
        verification=verify_signal_input(
            target=TARGET,
            source_id=source_id,
            subject_id=candidate_id,
            verifier_id="governance:test",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="governance:test",
            trace_event_id=f"{trace_id}:verified",
        ),
    )


def verified_recruitment(source_id: str, *, strength: float) -> RecruitmentSignal:
    trace_id = f"trace:{source_id}"
    return RecruitmentSignal(
        source_id,
        "candidate:alpha",
        strength=strength,
        target=TARGET,
        provenance="governance:test",
        trace_event_id=trace_id,
        verification=verify_signal_input(
            target=TARGET,
            source_id=source_id,
            subject_id="candidate:alpha",
            verifier_id="governance:test",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="governance:test",
            trace_event_id=f"{trace_id}:verified",
        ),
    )


def verified_inhibition(source_id: str, *, strength: float) -> InhibitionSignal:
    item = verified_recruitment(source_id, strength=strength)
    return InhibitionSignal(
        source_id=item.source_id,
        candidate_id=item.candidate_id,
        strength=item.strength,
        target=item.target,
        provenance=item.provenance,
        trace_event_id=item.trace_event_id,
        verification=item.verification,
    )


def test_consensus_succeeds_with_enough_independent_scout_reports() -> None:
    decision = evaluate_collective_decision(
        candidate_set=declared_candidates(),
        policy=policy(min_independent_scouts=2, quorum_threshold=2),
        target="decision:collective",
        scout_reports=[
            verified_scout("scout:a"),
            verified_scout("scout:b"),
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
        scout_reports=[verified_scout("scout:a")],
    )

    assert decision.committed is True
    assert decision.candidate_id == "candidate:safe_fallback"
    assert decision.reason == "safe_collective_fallback"


def test_collective_decision_accepts_runtime_fallback_override() -> None:
    decision = evaluate_collective_decision(
        candidate_set=declared_candidates(),
        policy=policy(
            fallback_candidate="", min_independent_scouts=2, quorum_threshold=1
        ),
        target="decision:collective",
        scout_reports=[verified_scout("scout:a")],
        fallback_candidate_id="candidate:safe_fallback",
    )

    assert decision.candidate_id == "candidate:safe_fallback"
    assert decision.reason == "safe_collective_fallback"


def test_collective_decision_rejects_invalid_runtime_fallback_override() -> None:
    for fallback_candidate_id in ["candidate:missing", "candidate:alpha"]:
        with pytest.raises(GovernanceError):
            evaluate_collective_decision(
                candidate_set=declared_candidates(),
                policy=policy(
                    fallback_candidate="", min_independent_scouts=2, quorum_threshold=1
                ),
                target="decision:collective",
                scout_reports=[verified_scout("scout:a")],
                fallback_candidate_id=fallback_candidate_id,
            )


@pytest.mark.parametrize(
    "overrides",
    [
        {"min_independent_scouts": 0},
        {"quorum_threshold": 0},
        {"min_independent_scouts": True},
        {"quorum_threshold": float("nan")},
    ],
)
def test_collective_decision_rejects_invalid_direct_runtime_policy(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(GovernanceError, match="collective policy"):
        evaluate_collective_decision(
            candidate_set=declared_candidates(),
            policy=policy(**overrides),
            target="decision:collective",
            scout_reports=[],
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"mode": "unsupported"},
        {"pheromone_enabled": "yes"},
        {"pheromone_evaporation_rate": float("inf")},
        {"pheromone_min_strength": -1},
        {"pheromone_diffusion_enabled": True, "pheromone_diffusion_max_hops": 0},
        {"pheromone_scored_subject_types": []},
        {"policy_adjustment_bounds": {"unknown": [0, 1]}},
    ],
)
def test_candidate_scoring_validates_all_direct_policy_surfaces(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(GovernanceError):
        score_candidates(
            candidate_set=declared_candidates(),
            policy=policy(**overrides),
            target="decision:collective",
            scout_reports=[],
        )


def test_collective_decision_rejects_fallback_override_of_declared_policy() -> None:
    candidates = CandidateSet(
        [
            Candidate(id="candidate:alpha", target="decision:collective"),
            Candidate(
                id="candidate:safe-a", target="decision:collective", safe_fallback=True
            ),
            Candidate(
                id="candidate:safe-b", target="decision:collective", safe_fallback=True
            ),
        ]
    )

    with pytest.raises(GovernanceError, match="declared collective fallback"):
        evaluate_collective_decision(
            candidate_set=candidates,
            policy=policy(
                fallback_candidate="candidate:safe-a",
                min_independent_scouts=2,
            ),
            target="decision:collective",
            scout_reports=[],
            fallback_candidate_id="candidate:safe-b",
        )


def test_collective_decision_rejects_ambiguous_compatibility_fallback() -> None:
    candidates = CandidateSet(
        [
            Candidate(id="candidate:alpha", target="decision:collective"),
            Candidate(
                id="candidate:safe-a", target="decision:collective", safe_fallback=True
            ),
            Candidate(
                id="candidate:safe-b", target="decision:collective", safe_fallback=True
            ),
        ]
    )

    with pytest.raises(GovernanceError, match="exactly one safe fallback"):
        evaluate_collective_decision(
            candidate_set=candidates,
            policy=policy(fallback_candidate="", min_independent_scouts=2),
            target="decision:collective",
            scout_reports=[],
            fallback_candidate_id="candidate:safe-a",
        )


def test_recruitment_increases_candidate_support_when_enabled() -> None:
    state = score_candidates(
        candidate_set=declared_candidates(),
        policy=policy(recruitment_enabled=True, quorum_threshold=2),
        target=TARGET,
        scout_reports=[verified_scout("scout:a")],
        recruitment_signals=[verified_recruitment("signal:a", strength=2)],
    )

    assert state.scores["candidate:alpha"] == 3


def test_recruitment_is_ignored_when_disabled() -> None:
    state = score_candidates(
        candidate_set=declared_candidates(),
        policy=policy(recruitment_enabled=False),
        target=TARGET,
        scout_reports=[verified_scout("scout:a")],
        recruitment_signals=[
            RecruitmentSignal("signal:a", "candidate:alpha", strength=2)
        ],
    )

    assert state.scores["candidate:alpha"] == 1


def test_inhibition_decreases_candidate_support_when_enabled() -> None:
    state = score_candidates(
        candidate_set=declared_candidates(),
        policy=policy(inhibition_enabled=True, quorum_threshold=3),
        target=TARGET,
        scout_reports=[verified_scout("scout:a", support=3)],
        inhibition_signals=[verified_inhibition("signal:a", strength=2)],
    )

    assert state.scores["candidate:alpha"] == 1


def test_inhibition_is_ignored_when_disabled() -> None:
    state = score_candidates(
        candidate_set=declared_candidates(),
        policy=policy(inhibition_enabled=False, quorum_threshold=3),
        target=TARGET,
        scout_reports=[verified_scout("scout:a", support=3)],
        inhibition_signals=[
            InhibitionSignal("signal:a", "candidate:alpha", strength=2)
        ],
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

    assert [trail.kind for trail in trails] == [
        "positive",
        "negative",
        "cautionary",
        "novelty",
        "stale",
    ]
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
    # Deposit is bounded by max strength, the round budget, and the shared
    # source budget; the strictest declared bound wins.
    assert deposited.strength == 3
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

    assert clip_pheromone_deposit_strength(8, policy) == 3
    assert deposited.strength == 3


def test_candidate_subject_scores_declared_candidate() -> None:
    trail = pheromone(
        "", subject_type="candidate", subject_id="candidate:alpha", strength=2
    )

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
        validate_pheromone_trail(
            mark, pheromone_policy(), candidate_set=declared_candidates()
        )
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

    validate_pheromone_trail(
        trail, pheromone_policy(), candidate_set=declared_candidates()
    )

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
        policy=pheromone_policy(
            novelty_weight=0.5,
            per_source_cap=100,
            exploration_enabled=True,
        ),
        trails=[pheromone("candidate:alpha", strength=6, kind="novelty")],
    )

    assert scores["candidate:alpha"] == 3


def test_per_source_cap_limits_total_scoring_contribution() -> None:
    scores = score_pheromone_trails(
        candidate_set=declared_candidates(),
        policy=pheromone_policy(per_source_cap=4),
        trails=[
            pheromone(
                "candidate:alpha",
                strength=3,
                source_id="agent:a",
                provenance="driver:a",
            ),
            pheromone(
                "candidate:alpha",
                strength=3,
                source_id="agent:a",
                provenance="driver:a",
            ),
            pheromone(
                "candidate:alpha",
                strength=3,
                source_id="agent:b",
                provenance="driver:b",
            ),
        ],
    )

    assert scores["candidate:alpha"] == 7


def test_source_diversity_is_counted_and_can_gate_pheromone_scoring() -> None:
    one_source = [
        pheromone(
            "candidate:alpha", strength=2, source_id="agent:a", provenance="driver:a"
        )
    ]
    two_sources = one_source + [
        pheromone(
            "candidate:alpha", strength=2, source_id="agent:b", provenance="driver:b"
        )
    ]
    policy = pheromone_policy(min_source_diversity=2, per_source_cap=100)

    assert (
        collect_pheromone_source_diversity(
            candidate_set=declared_candidates(),
            trails=two_sources,
            policy=policy,
        )["candidate:alpha"]
        == 2
    )
    assert (
        score_pheromone_trails(
            candidate_set=declared_candidates(),
            policy=policy,
            trails=one_source,
        )["candidate:alpha"]
        == 0
    )
    assert (
        score_pheromone_trails(
            candidate_set=declared_candidates(),
            policy=policy,
            trails=two_sources,
        )["candidate:alpha"]
        == 4
    )


def test_zero_strength_trail_cannot_fabricate_source_diversity() -> None:
    trails = [
        pheromone(
            "candidate:alpha", strength=5, source_id="agent:a", provenance="driver:a"
        ),
        pheromone(
            "candidate:alpha", strength=0, source_id="agent:b", provenance="driver:b"
        ),
    ]
    policy = pheromone_policy(min_source_diversity=2, per_source_cap=100)

    assert (
        collect_pheromone_source_diversity(
            candidate_set=declared_candidates(),
            trails=trails,
            policy=policy,
        )["candidate:alpha"]
        == 1
    )
    assert (
        score_pheromone_trails(
            candidate_set=declared_candidates(),
            trails=trails,
            policy=policy,
        )["candidate:alpha"]
        == 0
    )


def test_global_source_cap_is_applied_before_candidate_diversity_gate() -> None:
    policy = pheromone_policy(
        per_source_cap=1.0,
        min_source_diversity=2,
        kind_profiles={
            "alarm": PheromoneKindProfile(
                weight=1.0,
                priority=2,
                can_suppress_positive=True,
                scored_subject_types=["candidate"],
            ),
            "positive": PheromoneKindProfile(
                weight=1.0,
                priority=1,
                scored_subject_types=["candidate"],
            ),
        },
    )
    trails = [
        pheromone(
            "candidate:alpha",
            kind="alarm",
            source_id="agent:shared",
            trace_event_id="trace:alpha:shared",
        ),
        pheromone(
            "candidate:alpha",
            kind="alarm",
            source_id="agent:alpha:helper",
            trace_event_id="trace:alpha:helper",
        ),
        pheromone(
            "candidate:beta",
            source_id="agent:shared",
            trace_event_id="trace:beta:shared",
        ),
        pheromone(
            "candidate:beta",
            source_id="agent:beta:other",
            trace_event_id="trace:beta:other",
        ),
    ]

    diversity = collect_pheromone_source_diversity(
        candidate_set=declared_candidates(),
        trails=trails,
        policy=policy,
    )
    scores = score_pheromone_trails(
        candidate_set=declared_candidates(),
        trails=trails,
        policy=policy,
    )
    reversed_scores = score_pheromone_trails(
        candidate_set=declared_candidates(),
        trails=list(reversed(trails)),
        policy=policy,
    )

    assert diversity["candidate:alpha"] == 2
    assert diversity["candidate:beta"] == 1
    assert scores["candidate:alpha"] == -2.0
    assert scores["candidate:beta"] == 0.0
    assert reversed_scores == scores


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
                verified_scout("scout:a"),
                verified_scout("scout:b"),
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


def test_namespaced_pheromone_values_validate_but_do_not_score_by_default() -> None:
    policy = pheromone_policy(per_source_cap=100)
    custom_kind = pheromone("candidate:alpha", strength=10, kind="x-acme.preference")
    custom_subject = pheromone(
        "",
        subject_type="ext.acme.path",
        subject_id="candidate:alpha",
        kind="positive",
        strength=10,
    )

    validate_pheromone_trail(custom_kind, policy, candidate_set=declared_candidates())
    validate_pheromone_trail(
        custom_subject, policy, candidate_set=declared_candidates()
    )
    scores = score_pheromone_trails(
        candidate_set=declared_candidates(),
        policy=policy,
        trails=[custom_kind, custom_subject],
    )

    assert scores == {
        "candidate:alpha": 0.0,
        "candidate:beta": 0.0,
        "candidate:safe_fallback": 0.0,
    }


def test_namespaced_kind_profile_requires_its_own_scoring_subject_declaration() -> None:
    custom = pheromone(
        "candidate:alpha",
        strength=2,
        kind="x-acme.preference",
    )
    metadata_policy = pheromone_policy(
        per_source_cap=100,
        kind_profiles={"x-acme.preference": PheromoneKindProfile(weight=3)},
    )
    explicit_policy = pheromone_policy(
        per_source_cap=100,
        kind_profiles={
            "x-acme.preference": PheromoneKindProfile(
                weight=3,
                scored_subject_types=["candidate"],
            )
        },
    )

    assert (
        score_pheromone_trails(
            candidate_set=declared_candidates(),
            policy=metadata_policy,
            trails=[custom],
        )["candidate:alpha"]
        == 0
    )
    assert (
        score_pheromone_trails(
            candidate_set=declared_candidates(),
            policy=explicit_policy,
            trails=[custom],
        )["candidate:alpha"]
        == 6
    )


@pytest.mark.parametrize(
    "policy_overrides",
    [
        {"scored_subject_types": ["evidence"]},
        {
            "kind_profiles": {
                "positive": PheromoneKindProfile(
                    scored_subject_types=["evidence"],
                )
            }
        },
    ],
)
def test_evidence_subject_cannot_be_declared_for_pheromone_scoring(
    policy_overrides: dict[str, object],
) -> None:
    active_policy = pheromone_policy(**policy_overrides)
    with pytest.raises(GovernanceError, match="non-scoring pheromone subject"):
        score_pheromone_trails(
            candidate_set=declared_candidates(),
            policy=active_policy,
            trails=[
                pheromone(
                    "candidate:alpha",
                    subject_type="evidence",
                    subject_id="evidence:a",
                )
            ],
        )


def test_route_tool_and_agent_pheromone_score_only_when_declared_by_policy() -> None:
    route_trail = pheromone(
        "candidate:alpha",
        subject_type="route",
        subject_id="route:alpha",
        strength=3,
    )

    default_scores = score_pheromone_trails(
        candidate_set=declared_candidates(),
        policy=pheromone_policy(per_source_cap=100),
        trails=[route_trail],
    )
    route_scores, breakdown = score_pheromone_trails_with_breakdown(
        candidate_set=declared_candidates(),
        policy=pheromone_policy(
            scored_subject_types=["candidate", "route"], per_source_cap=100
        ),
        trails=[route_trail],
    )

    assert default_scores["candidate:alpha"] == 0
    assert route_scores["candidate:alpha"] == 3
    assert breakdown["candidate:alpha"]["pheromone_route"] == 3


def test_kind_profiles_drive_alarm_ttl_and_stale_no_score() -> None:
    policy = pheromone_policy(
        per_source_cap=100,
        kind_profiles={
            "alarm": PheromoneKindProfile(weight=2, ttl_steps=1),
            "stale": PheromoneKindProfile(weight=0),
        },
    )

    alarm_scores = score_pheromone_trails(
        candidate_set=declared_candidates(),
        policy=policy,
        trails=[pheromone("candidate:alpha", kind="alarm", strength=3)],
    )
    expired = evaporate_trails(
        [pheromone("candidate:alpha", kind="alarm", strength=3)],
        policy,
        current_step=1,
    )[0]
    stale_scores = score_pheromone_trails(
        candidate_set=declared_candidates(),
        policy=policy,
        trails=[expired],
    )

    assert alarm_scores["candidate:alpha"] == -6
    assert expired.kind == "stale"
    assert stale_scores["candidate:alpha"] == 0


def test_pheromone_diffuses_only_across_declared_topology_and_hop_bound() -> None:
    topology = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject("route", "route:alpha", candidate_id="candidate:alpha"),
            PheromoneSubject(
                "candidate", "candidate:alpha", candidate_id="candidate:alpha"
            ),
            PheromoneSubject("tool", "tool:review", candidate_id="candidate:alpha"),
        ],
        edges=[
            PheromoneEdge(
                "route", "route:alpha", "candidate", "candidate:alpha", attenuation=0.5
            ),
            PheromoneEdge(
                "candidate", "candidate:alpha", "tool", "tool:review", attenuation=0.5
            ),
        ],
    )

    trails = diffuse_pheromone_trails(
        [
            pheromone(
                "candidate:alpha",
                subject_type="route",
                subject_id="route:alpha",
                strength=8,
            )
        ],
        topology,
        pheromone_policy(
            scored_subject_types=["candidate", "route"], per_source_cap=100
        ),
        PheromoneDiffusionPolicy(enabled=True, max_hops=1, attenuation=0.5),
        candidate_set=declared_candidates(),
    )

    by_subject = {(trail.subject_type, trail.subject_id): trail for trail in trails}
    assert by_subject[("candidate", "candidate:alpha")].strength == 2
    assert ("tool", "tool:review") not in by_subject


def test_pheromone_feedback_reinforces_outcomes_and_requires_lineage() -> None:
    policy = pheromone_policy(feedback_enabled=True, per_round_deposit_cap=3)

    reinforced = reinforce_pheromone_trails(
        [],
        [
            PheromoneFeedback(
                source_id="agent:a",
                subject_type="route",
                subject_id="route:alpha",
                candidate_id="candidate:alpha",
                target="decision:collective",
                outcome="success",
                strength_delta=7,
                evidence_id="evidence:a",
                provenance="driver:a",
                trace_event_id="trace:feedback:success",
                step=2,
            ),
            PheromoneFeedback(
                source_id="agent:b",
                subject_type="route",
                subject_id="route:beta",
                candidate_id="candidate:beta",
                target="decision:collective",
                outcome="congested",
                strength_delta=2,
                evidence_id="evidence:b",
                provenance="driver:b",
                trace_event_id="trace:feedback:congested",
                step=2,
            ),
        ],
        policy,
        candidate_set=declared_candidates(),
        target="decision:collective",
    )

    with pytest.raises(GovernanceError):
        validate_pheromone_feedback(
            PheromoneFeedback(
                source_id="agent:bad",
                subject_type="route",
                subject_id="route:bad",
                candidate_id="candidate:alpha",
                target="decision:collective",
                outcome="success",
                strength_delta=1,
            ),
            policy,
            candidate_set=declared_candidates(),
        )
    with pytest.raises(GovernanceError):
        validate_pheromone_feedback(
            PheromoneFeedback(
                source_id="agent:bad",
                subject_type="route",
                subject_id="route:bad",
                candidate_id="candidate:alpha",
                target="decision:other",
                outcome="success",
                strength_delta=1,
                evidence_id="evidence:bad",
                provenance="driver:bad",
                trace_event_id="trace:feedback:wrong-target",
            ),
            policy,
            candidate_set=declared_candidates(),
            target="decision:collective",
        )

    assert {trail.kind: trail.strength for trail in reinforced} == {
        "positive": 1,
        "cautionary": 2,
    }


def test_pheromone_feedback_requires_source_candidate_binding_and_bounded_delta() -> (
    None
):
    policy = pheromone_policy(feedback_enabled=True)

    for feedback in [
        PheromoneFeedback(
            source_id="",
            subject_type="route",
            subject_id="route:alpha",
            candidate_id="candidate:alpha",
            target="decision:collective",
            outcome="success",
            strength_delta=1,
            evidence_id="evidence:a",
            provenance="driver:a",
            trace_event_id="trace:feedback",
        ),
        PheromoneFeedback(
            source_id="agent:a",
            subject_type="candidate",
            subject_id="candidate:alpha",
            candidate_id="",
            target="decision:collective",
            outcome="success",
            strength_delta=1,
            evidence_id="evidence:a",
            provenance="driver:a",
            trace_event_id="trace:feedback",
        ),
        PheromoneFeedback(
            source_id="agent:a",
            subject_type="candidate",
            subject_id="candidate:alpha",
            candidate_id="candidate:beta",
            target="decision:collective",
            outcome="success",
            strength_delta=1,
            evidence_id="evidence:a",
            provenance="driver:a",
            trace_event_id="trace:feedback",
        ),
        PheromoneFeedback(
            source_id="agent:a",
            subject_type="route",
            subject_id="route:alpha",
            candidate_id="candidate:alpha",
            target="decision:collective",
            outcome="success",
            strength_delta=-1,
            evidence_id="evidence:a",
            provenance="driver:a",
            trace_event_id="trace:feedback",
        ),
    ]:
        with pytest.raises(GovernanceError):
            validate_pheromone_feedback(
                feedback,
                policy,
                candidate_set=declared_candidates(),
                target="decision:collective",
            )


def test_pheromone_response_models_are_deterministic() -> None:
    saturating = score_pheromone_trails(
        candidate_set=declared_candidates(),
        policy=pheromone_policy(
            response_model="saturating", saturation_threshold=2, per_source_cap=100
        ),
        trails=[pheromone("candidate:alpha", strength=6)],
    )
    threshold = score_pheromone_trails(
        candidate_set=declared_candidates(),
        policy=pheromone_policy(
            response_model="threshold", activation_threshold=3, per_source_cap=100
        ),
        trails=[pheromone("candidate:alpha", strength=2)],
    )
    competitive = score_pheromone_trails(
        candidate_set=declared_candidates(),
        policy=pheromone_policy(
            response_model="competitive",
            competition_mode="normalize",
            per_source_cap=100,
        ),
        trails=[
            pheromone("candidate:alpha", strength=2, source_id="agent:a"),
            pheromone(
                "candidate:beta", strength=2, source_id="agent:b", provenance="driver:b"
            ),
        ],
    )

    assert saturating["candidate:alpha"] == 1.5
    assert threshold["candidate:alpha"] == 0
    assert round(sum(competitive.values()), 7) == 0
    assert competitive["candidate:alpha"] == competitive["candidate:beta"]


def test_layer_coordination_unresolved_conflict_forces_safe_fallback() -> None:
    layer_state = evaluate_layer_coordination(
        candidate_set=declared_candidates(),
        target="decision:collective",
        policy=LayerCoordinationPolicy(
            enabled=True,
            default_layer_weights={"learned": 1, "reactive": 1},
            layer_weight_bounds={"learned": (0, 1), "reactive": (0, 1)},
            confidence_thresholds={"learned": 0.5, "reactive": 0.5},
            conflict_threshold=0.1,
            min_layer_provenance=2,
            fallback_on_unresolved_conflict=True,
        ),
        fallback_candidate_id="candidate:safe_fallback",
        proposals=[
            layer_proposal(
                "learned",
                "candidate:alpha",
                confidence=0.9,
                support=10,
                provenance="runtime:learned",
            ),
            layer_proposal(
                "reactive",
                "candidate:beta",
                confidence=0.85,
                support=10,
                provenance="runtime:reactive",
            ),
        ],
    )
    assert layer_state.fallback_used is True
    assert layer_state.selected_candidate == "candidate:safe_fallback"
    with pytest.raises(GovernanceError, match="not authoritative"):
        evaluate_collective_decision(
            candidate_set=declared_candidates(),
            policy=policy(
                layer_coordination_enabled=True,
                min_independent_scouts=1,
                quorum_threshold=1,
            ),
            target="decision:collective",
            scout_reports=[
                ScoutReport("scout:a", "candidate:alpha", "evidence:a", "driver:a")
            ],
            layer_coordination_state=layer_state,
        )


def test_policy_adjustments_are_bounded_and_cannot_be_reactive() -> None:
    coordination_policy = LayerCoordinationPolicy(
        enabled=True,
        policy_adjustment_bounds={
            "pheromone_evaporation_rate": [0.1, 0.5],
            "pheromone_response_model": {"allowed_values": ["linear", "saturating"]},
        },
    )

    accepted = validate_policy_adjustment_proposal(
        PolicyAdjustmentProposal(
            layer_id="evolutionary",
            source_id="layer:evolutionary",
            adjustments={
                "pheromone_evaporation_rate": 0.2,
                "pheromone_response_model": "saturating",
            },
            provenance="runtime:evolutionary",
            trace_event_id="trace:adjustment",
        ),
        coordination_policy,
    )

    with pytest.raises(GovernanceError):
        validate_policy_adjustment_proposal(
            PolicyAdjustmentProposal(
                layer_id="evolutionary",
                source_id="layer:evolutionary",
                adjustments={"pheromone_evaporation_rate": 0.9},
                provenance="runtime:evolutionary",
                trace_event_id="trace:adjustment",
            ),
            coordination_policy,
        )
    with pytest.raises(GovernanceError):
        validate_policy_adjustment_proposal(
            PolicyAdjustmentProposal(
                layer_id="reactive",
                source_id="layer:reactive",
                adjustments={"pheromone_evaporation_rate": 0.2},
                provenance="runtime:reactive",
                trace_event_id="trace:adjustment",
            ),
            coordination_policy,
        )

    assert accepted == {
        "pheromone_evaporation_rate": 0.2,
        "pheromone_response_model": "saturating",
    }


def test_collective_score_breakdown_reconstructs_scores() -> None:
    state = score_candidates(
        candidate_set=declared_candidates(),
        policy=policy(
            recruitment_enabled=True,
            inhibition_enabled=True,
            pheromone_enabled=True,
            pheromone_per_source_cap=100,
            quorum_threshold=2,
        ),
        target=TARGET,
        scout_reports=[verified_scout("scout:a", support=2)],
        recruitment_signals=[verified_recruitment("recruit:a", strength=1)],
        inhibition_signals=[verified_inhibition("inhibit:a", strength=0.5)],
        pheromone_trails=[pheromone("candidate:alpha", strength=2)],
    )

    assert state.scores["candidate:alpha"] == 4.5
    assert (
        sum(state.score_breakdown["candidate:alpha"].values())
        == state.scores["candidate:alpha"]
    )


def test_candidate_score_lineage_exposes_reconstructable_breakdown() -> None:
    state = score_candidates(
        candidate_set=declared_candidates(),
        policy=policy(pheromone_enabled=True, pheromone_per_source_cap=100),
        target=TARGET,
        scout_reports=[verified_scout("scout:a", support=1)],
        pheromone_trails=[pheromone("candidate:alpha", strength=2)],
    )

    lineage = candidate_score_lineage(state, candidate_id="candidate:alpha")

    assert lineage["scores"] == {"candidate:alpha": 3.0}
    assert (
        sum(lineage["score_breakdown"]["candidate:alpha"].values())
        == lineage["scores"]["candidate:alpha"]
    )
    assert lineage["independent_scouts"]["candidate:alpha"] == ["scout:a"]
    assert lineage["pheromone_source_diversity"]["candidate:alpha"] == 1


def test_score_breakdown_validation_rejects_non_reconstructable_state() -> None:
    with pytest.raises(GovernanceError):
        validate_score_breakdown(
            CollectiveDecisionState(
                scores={"candidate:alpha": 1.0},
                score_breakdown={"candidate:alpha": {"scout": 0.5}},
            )
        )


def test_pheromone_lineage_standardizes_lifecycle_fields() -> None:
    trail = pheromone("candidate:alpha", strength=2, updated_at_step=3)

    lineage = pheromone_lineage(
        trail,
        old_strength=4,
        score_delta=2,
        score_breakdown={"pheromone_positive": 2},
        fallback_used=False,
        resolution="scored",
    )

    assert lineage["candidate_id"] == "candidate:alpha"
    assert lineage["subject_type"] == "candidate"
    assert lineage["subject_id"] == "candidate:alpha"
    assert lineage["kind"] == "positive"
    assert lineage["old_strength"] == 4
    assert lineage["new_strength"] == 2
    assert lineage["step"] == 3
    assert lineage["score_delta"] == 2
    assert lineage["score_breakdown"] == {"pheromone_positive": 2}
    assert lineage["fallback_used"] is False
    assert lineage["resolution"] == "scored"


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


def test_collective_decision_step_evaporates_pheromones_before_scoring() -> None:
    step = evaluate_collective_decision_step(
        candidate_set=declared_candidates(),
        policy=policy(
            min_independent_scouts=1,
            quorum_threshold=5,
            pheromone_enabled=True,
            pheromone_evaporation_rate=0.5,
            pheromone_per_source_cap=100,
            pheromone_require_provenance=True,
            pheromone_require_trace=True,
        ),
        target="decision:collective",
        scout_reports=[verified_scout("scout:a")],
        pheromone_trails=[pheromone("candidate:alpha", strength=8)],
        current_step=1,
    )

    assert step.pheromone_trails[0].strength == 4
    assert step.state.scores["candidate:alpha"] == 5
    assert step.decision.candidate_id == "candidate:alpha"
    assert step.decision.reason == "collective_consensus"


def test_collective_decision_step_expires_stale_pheromones_before_evaluation() -> None:
    step = evaluate_collective_decision_step(
        candidate_set=declared_candidates(),
        policy=policy(
            min_independent_scouts=1,
            quorum_threshold=5,
            pheromone_enabled=True,
            pheromone_per_source_cap=100,
            pheromone_require_provenance=True,
            pheromone_require_trace=True,
        ),
        target="decision:collective",
        scout_reports=[verified_scout("scout:a")],
        pheromone_trails=[pheromone("candidate:alpha", strength=10, ttl_steps=1)],
        current_step=1,
    )

    assert step.pheromone_trails[0].kind == "stale"
    assert step.state.scores["candidate:alpha"] == 1
    assert step.decision.candidate_id == "candidate:safe_fallback"
    assert step.decision.reason == "safe_collective_fallback"


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
            scout_reports=[verified_scout("scout:a", "candidate:missing")],
        )


def test_collective_decision_rejects_candidate_for_different_target() -> None:
    with pytest.raises(GovernanceError, match="not active target"):
        evaluate_collective_decision(
            candidate_set=CandidateSet(
                [
                    Candidate(id="candidate:alpha", target="decision:other"),
                    Candidate(
                        id="candidate:safe_fallback",
                        target="decision:collective",
                        safe_fallback=True,
                    ),
                ]
            ),
            policy=policy(
                fallback_candidate="candidate:safe_fallback",
                min_independent_scouts=1,
                quorum_threshold=1,
            ),
            target="decision:collective",
            scout_reports=[verified_scout("scout:a")],
        )


def test_scout_report_requires_evidence_provenance() -> None:
    with pytest.raises(GovernanceError):
        score_candidates(
            candidate_set=declared_candidates(),
            policy=policy(),
            scout_reports=[ScoutReport("scout:a", "candidate:alpha", "evidence:a", "")],
        )


def test_pheromone_topology_rejects_candidate_target_mismatch() -> None:
    with pytest.raises(GovernanceError):
        validate_pheromone_topology(
            PheromoneNeighborhood(
                subjects=[
                    PheromoneSubject(
                        "route",
                        "route:alpha",
                        candidate_id="candidate:alpha",
                        target="decision:other",
                    )
                ]
            ),
            candidate_set=declared_candidates(),
        )


def declared_candidates() -> CandidateSet:
    return CandidateSet(
        [
            Candidate(id="candidate:alpha", target="decision:collective"),
            Candidate(id="candidate:beta", target="decision:collective"),
            Candidate(
                id="candidate:safe_fallback",
                target="decision:collective",
                safe_fallback=True,
            ),
        ]
    )


def policy(**overrides: object) -> CollectiveDecisionPolicy:
    values = {
        "mode": "ant_colony",
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


def layer_proposal(
    layer_id: str,
    candidate_id: str,
    *,
    confidence: float,
    support: float,
    provenance: str,
) -> LayerProposal:
    return LayerProposal(
        layer_id=layer_id,
        source_id=f"source:{layer_id}",
        target="decision:collective",
        candidate_id=candidate_id,
        action="support",
        confidence=confidence,
        support=support,
        evidence_id=f"evidence:{layer_id}",
        provenance=provenance,
        trace_event_id=f"trace:{layer_id}",
    )
