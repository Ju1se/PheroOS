from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType

import pytest

from pheroos.governance.candidate import Candidate, CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.layer_coordination import (
    LayerCoordinationPolicy,
    LayerPerformanceSnapshot,
    LayerProposal,
    StrategyBias,
    allocate_layer_weights,
    evaluate_layer_coordination,
    layer_action_effect,
    materialize_layer_pheromone_proposals,
    validate_layer_coordination_policy,
    validate_layer_proposal,
    validate_strategy_bias,
)
from pheroos.governance.pheromone import (
    PheromoneDiffusionPolicy,
    PheromoneEdge,
    PheromoneNeighborhood,
    PheromonePolicy,
    PheromoneSubject,
    PheromoneTrail,
    deposit_pheromone_trails,
    diffuse_pheromone_trails_with_records,
    evaporate_trails_with_records,
    observe_pheromone_exploration,
    score_pheromone_trails,
    score_pheromone_trails_result,
    validate_pheromone_topology,
    validate_pheromone_trail,
)
from pheroos.governance.pheromone_feedback import (
    PheromoneFeedback,
    reinforce_pheromone_trails_with_records,
)
from pheroos.governance.policy_adjustment import (
    PolicyAdjustmentProposal,
    RunScopedPolicyOverlay,
    apply_policy_adjustment_overlay,
    run_scoped_policy_overlay_is_authoritative,
    validate_policy_adjustment_proposal,
    validate_policy_adjustment_proposals,
)
from pheroos.protocol.models import CollectiveDecisionPolicy, PheromoneKindProfile


TARGET = "decision:active"


def candidates() -> CandidateSet:
    return CandidateSet(
        [
            Candidate("candidate:foreign", "decision:foreign"),
            Candidate("candidate:alpha", TARGET),
            Candidate("candidate:beta", TARGET),
            Candidate("candidate:fallback", TARGET, safe_fallback=True),
        ]
    )


def policy(**overrides: object) -> PheromonePolicy:
    values: dict[str, object] = {
        "enabled": True,
        "max_strength": 10.0,
        "per_source_cap": 100.0,
        "per_round_deposit_cap": 100.0,
        "require_provenance": True,
        "require_trace": True,
    }
    values.update(overrides)
    return PheromonePolicy(**values)


def trail(
    candidate_id: str = "candidate:alpha",
    *,
    trace_id: str = "trace:deposit:a",
    source_id: str = "source:a",
    strength: float = 1.0,
    kind: str = "positive",
    subject_type: str = "candidate",
    subject_id: str | None = None,
    target: str = TARGET,
    updated_at_step: int = 0,
) -> PheromoneTrail:
    return PheromoneTrail(
        candidate_id=candidate_id,
        strength=strength,
        subject_type=subject_type,
        subject_id=subject_id if subject_id is not None else (candidate_id if subject_type == "candidate" else "route:a"),
        target=target,
        kind=kind,
        source_id=source_id,
        evidence_id=f"evidence:{trace_id}",
        provenance=f"runtime:{source_id}",
        trace_event_id=trace_id,
        updated_at_step=updated_at_step,
    )


def feedback(
    *,
    trace_id: str,
    source_id: str = "source:a",
    outcome: str = "success",
    delta: float = 1.0,
) -> PheromoneFeedback:
    return PheromoneFeedback(
        source_id=source_id,
        subject_type="route",
        subject_id="route:a",
        candidate_id="candidate:alpha",
        target=TARGET,
        outcome=outcome,
        strength_delta=delta,
        evidence_id=f"evidence:{trace_id}",
        provenance=f"runtime:{source_id}",
        trace_event_id=trace_id,
        step=1,
    )


def proposal(
    layer_id: str,
    candidate_id: str = "candidate:alpha",
    *,
    action: str = "support",
    confidence: float = 0.9,
    support: float = 1.0,
    risk: float = 0.0,
    trace_id: str | None = None,
) -> LayerProposal:
    event_id = trace_id or f"trace:layer:{layer_id}:{candidate_id}:{action}"
    return LayerProposal(
        layer_id=layer_id,
        source_id=f"source:{layer_id}",
        target=TARGET,
        candidate_id=candidate_id,
        action=action,
        confidence=confidence,
        support=support,
        risk=risk,
        evidence_id=f"evidence:{layer_id}",
        provenance=f"runtime:{layer_id}",
        trace_event_id=event_id,
    )


def layer_policy(**overrides: object) -> LayerCoordinationPolicy:
    values: dict[str, object] = {
        "enabled": True,
        "default_layer_weights": {layer: 1.0 for layer in ("reactive", "learned", "evolutionary", "metacognitive")},
        "layer_weight_bounds": {layer: (0.0, 2.0) for layer in ("reactive", "learned", "evolutionary", "metacognitive")},
        "confidence_thresholds": {layer: 0.5 for layer in ("reactive", "learned", "evolutionary", "metacognitive")},
        "conflict_threshold": 0.1,
        "emergency_override_threshold": 0.8,
        "min_layer_provenance": 1,
    }
    values.update(overrides)
    return LayerCoordinationPolicy(**values)


def test_target_binding_duplicate_topology_and_cross_target_edges_fail_closed() -> None:
    with pytest.raises(GovernanceError, match="candidate target"):
        validate_pheromone_trail(
            trail(target="decision:foreign"),
            policy(),
            candidate_set=candidates(),
        )

    duplicate = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject("route", "route:a", "candidate:alpha", TARGET),
            PheromoneSubject("route", "route:a", "candidate:beta", TARGET),
        ]
    )
    with pytest.raises(GovernanceError, match="duplicate pheromone topology subject"):
        validate_pheromone_topology(duplicate, candidate_set=candidates())

    cross_target = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject("route", "route:a", "candidate:alpha", TARGET),
            PheromoneSubject("candidate", "candidate:foreign", "candidate:foreign", "decision:foreign"),
        ],
        edges=[PheromoneEdge("route", "route:a", "candidate", "candidate:foreign")],
    )
    with pytest.raises(GovernanceError, match="crosses targets"):
        validate_pheromone_topology(cross_target, candidate_set=candidates())


def test_topology_requires_one_explicit_candidate_binding_per_subject_key() -> None:
    unbound = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject("route", "route:a", target=TARGET),
            PheromoneSubject("candidate", "candidate:alpha", "candidate:alpha", TARGET),
        ],
        edges=[PheromoneEdge("route", "route:a", "candidate", "candidate:alpha")],
    )
    with pytest.raises(GovernanceError, match="must declare candidate_id"):
        validate_pheromone_topology(unbound, candidate_set=candidates(), target=TARGET)

    bound = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject("route", "route:a", "candidate:alpha", TARGET),
            PheromoneSubject("candidate", "candidate:alpha", "candidate:alpha", TARGET),
        ],
        edges=[PheromoneEdge("route", "route:a", "candidate", "candidate:alpha")],
    )
    with pytest.raises(GovernanceError, match="candidate binding does not match topology"):
        diffuse_pheromone_trails_with_records(
            [trail("candidate:beta", subject_type="route", subject_id="route:a")],
            bound,
            policy(scored_subject_types=["route"]),
            PheromoneDiffusionPolicy(enabled=True, max_hops=1, attenuation=0.5),
            candidate_set=candidates(),
            target=TARGET,
        )

    with pytest.raises(GovernanceError, match="not declared in topology"):
        diffuse_pheromone_trails_with_records(
            [trail(subject_type="route", subject_id="route:undeclared")],
            bound,
            policy(scored_subject_types=["route"]),
            PheromoneDiffusionPolicy(enabled=True, max_hops=1, attenuation=0.5),
            candidate_set=candidates(),
            target=TARGET,
        )


def test_feedback_must_match_declared_topology_subject_candidate_binding() -> None:
    bound = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject("route", "route:a", "candidate:alpha", TARGET),
            PheromoneSubject("candidate", "candidate:alpha", "candidate:alpha", TARGET),
        ],
        edges=[PheromoneEdge("route", "route:a", "candidate", "candidate:alpha")],
    )

    with pytest.raises(GovernanceError, match="candidate binding does not match topology"):
        reinforce_pheromone_trails_with_records(
            [],
            [replace(feedback(trace_id="trace:feedback:wrong"), candidate_id="candidate:beta")],
            policy(feedback_enabled=True),
            candidate_set=candidates(),
            target=TARGET,
            neighborhood=bound,
        )

    with pytest.raises(GovernanceError, match="not declared in topology"):
        reinforce_pheromone_trails_with_records(
            [],
            [replace(feedback(trace_id="trace:feedback:missing"), subject_id="route:missing")],
            policy(feedback_enabled=True),
            candidate_set=candidates(),
            target=TARGET,
            neighborhood=bound,
        )


def test_deposit_priority_is_permutation_invariant_and_batch_is_atomic() -> None:
    active_policy = policy(
        per_source_cap=3.0,
        per_round_deposit_cap=3.0,
        kind_profiles={
            "positive": PheromoneKindProfile(weight=1.0, priority=1),
            "alarm": PheromoneKindProfile(weight=1.0, priority=10, can_suppress_positive=True),
        },
    )
    positive = trail(trace_id="trace:positive", strength=3.0, kind="positive")
    alarm = trail(trace_id="trace:alarm", strength=2.0, kind="alarm")
    forward = deposit_pheromone_trails([positive, alarm], active_policy, candidate_set=candidates(), target=TARGET)
    reverse = deposit_pheromone_trails([alarm, positive], active_policy, candidate_set=candidates(), target=TARGET)

    assert {item.trace_event_id: item.strength for item in forward.trails} == {
        item.trace_event_id: item.strength for item in reverse.trails
    } == {"trace:positive": 1.0, "trace:alarm": 2.0}
    initial_budget = forward.budget_state.for_policy(active_policy)
    with pytest.raises(GovernanceError):
        deposit_pheromone_trails(
            [positive, replace(alarm, trace_event_id="trace:bad", strength=float("nan"))],
            active_policy,
            candidate_set=candidates(),
            target=TARGET,
            budget_state=initial_budget,
        )
    assert initial_budget.round_used == 0


def test_zero_elapsed_evaporation_is_a_true_noop_without_lifecycle_record() -> None:
    current = trail(strength=4.0, updated_at_step=2)
    result = evaporate_trails_with_records(
        [current],
        policy(evaporation_rate=0.5),
        current_step=2,
    )

    assert result.trails == (current,)
    assert result.records == ()


def test_one_budget_threads_deposit_diffusion_feedback_and_replay() -> None:
    active_policy = policy(per_source_cap=3.0, per_round_deposit_cap=5.0, feedback_enabled=True)
    raw = trail(
        trace_id="trace:route",
        strength=2.0,
        subject_type="route",
        subject_id="route:a",
    )
    deposited = deposit_pheromone_trails([raw], active_policy, candidate_set=candidates(), target=TARGET)
    topology = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject("route", "route:a", "candidate:alpha", TARGET),
            PheromoneSubject("candidate", "candidate:alpha", "candidate:alpha", TARGET),
        ],
        edges=[PheromoneEdge("route", "route:a", "candidate", "candidate:alpha", attenuation=1.0)],
    )
    diffused = diffuse_pheromone_trails_with_records(
        list(deposited.trails),
        topology,
        active_policy,
        PheromoneDiffusionPolicy(enabled=True, max_hops=1, attenuation=0.5),
        candidate_set=candidates(),
        target=TARGET,
        budget_state=deposited.budget_state,
        processed_event_ids=deposited.processed_event_ids,
    )
    reinforced = reinforce_pheromone_trails_with_records(
        list(diffused.trails),
        [feedback(trace_id="trace:feedback", delta=2.0)],
        active_policy,
        candidate_set=candidates(),
        target=TARGET,
        budget_state=diffused.budget_state,
    )

    assert reinforced.budget_state is not None
    assert reinforced.budget_state.round_used == 3.0
    assert reinforced.budget_state.source_used == {"source:a": 3.0}
    assert reinforced.records[-1].action == "reinforce_rejected"
    assert reinforced.records[-1].applied_strength == 0

    deposit_replay = deposit_pheromone_trails(
        [raw],
        active_policy,
        candidate_set=candidates(),
        target=TARGET,
        processed_event_ids=deposited.processed_event_ids,
    )
    assert deposit_replay.trails == ()
    assert deposit_replay.replayed_event_ids == ("trace:route",)
    diffusion_replay = diffuse_pheromone_trails_with_records(
        list(deposited.trails),
        topology,
        active_policy,
        PheromoneDiffusionPolicy(enabled=True, max_hops=1, attenuation=0.5),
        candidate_set=candidates(),
        target=TARGET,
        processed_event_ids=diffused.processed_event_ids,
        processed_event_receipts=dict(diffused._processed_event_receipts),
    )
    assert len(diffusion_replay.trails) == 1
    assert diffusion_replay.replayed_event_ids
    nested_replay = diffuse_pheromone_trails_with_records(
        list(diffused.trails),
        topology,
        active_policy,
        PheromoneDiffusionPolicy(enabled=True, max_hops=1, attenuation=0.5),
        candidate_set=candidates(),
        target=TARGET,
        processed_event_ids=diffused.processed_event_ids,
        processed_event_receipts=dict(diffused._processed_event_receipts),
    )
    assert nested_replay.trails == diffused.trails
    feedback_replay = reinforce_pheromone_trails_with_records(
        list(reinforced.trails),
        [feedback(trace_id="trace:feedback", delta=2.0)],
        active_policy,
        candidate_set=candidates(),
        target=TARGET,
        processed_feedback_ids=reinforced.processed_feedback_ids,
    )
    assert feedback_replay.replayed_feedback_ids == ("trace:feedback",)


@pytest.mark.parametrize("substitution", ["source_strength", "edge_attenuation"])
def test_diffusion_replay_receipt_rejects_causal_payload_substitution(
    substitution: str,
) -> None:
    active_policy = policy(per_source_cap=10.0, per_round_deposit_cap=10.0)
    raw = trail(
        trace_id="trace:diffusion-receipt",
        strength=2.0,
        subject_type="route",
        subject_id="route:a",
    )
    deposited = deposit_pheromone_trails(
        [raw],
        active_policy,
        candidate_set=candidates(),
        target=TARGET,
    )
    topology = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject("route", "route:a", "candidate:alpha", TARGET),
            PheromoneSubject("candidate", "candidate:alpha", "candidate:alpha", TARGET),
        ],
        edges=[
            PheromoneEdge(
                "route",
                "route:a",
                "candidate",
                "candidate:alpha",
                attenuation=1.0,
            )
        ],
    )
    diffusion_policy = PheromoneDiffusionPolicy(
        enabled=True,
        max_hops=1,
        attenuation=0.5,
    )
    first = diffuse_pheromone_trails_with_records(
        list(deposited.trails),
        topology,
        active_policy,
        diffusion_policy,
        candidate_set=candidates(),
        target=TARGET,
        processed_event_ids=deposited.processed_event_ids,
    )
    replay_trails = list(deposited.trails)
    replay_topology = topology
    if substitution == "source_strength":
        replay_trails[0] = replace(replay_trails[0], strength=2.125)
    else:
        replay_topology = replace(
            topology,
            edges=(
                replace(topology.edges[0], attenuation=0.75),
            ),
        )

    with pytest.raises(GovernanceError, match="diffusion replay payload"):
        diffuse_pheromone_trails_with_records(
            replay_trails,
            replay_topology,
            active_policy,
            diffusion_policy,
            candidate_set=candidates(),
            target=TARGET,
            processed_event_ids=first.processed_event_ids,
            processed_event_receipts=dict(first._processed_event_receipts),
        )


def test_diffusion_replay_receipts_reject_unknown_ids_and_non_tuple_payloads() -> None:
    active_policy = policy(per_source_cap=10.0, per_round_deposit_cap=10.0)
    raw = trail(
        trace_id="trace:diffusion-receipt-shape",
        strength=2.0,
        subject_type="route",
        subject_id="route:a",
    )
    topology = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject("route", "route:a", "candidate:alpha", TARGET),
        ],
        edges=[],
    )
    diffusion_policy = PheromoneDiffusionPolicy(enabled=True, max_hops=1, attenuation=0.5)

    with pytest.raises(GovernanceError, match="must be processed event ids"):
        diffuse_pheromone_trails_with_records(
            [raw],
            topology,
            active_policy,
            diffusion_policy,
            candidate_set=candidates(),
            target=TARGET,
            processed_event_receipts={"trace:unknown": ("diffusion-v1",)},
        )
    with pytest.raises(GovernanceError, match="tuple payloads"):
        diffuse_pheromone_trails_with_records(
            [raw],
            topology,
            active_policy,
            diffusion_policy,
            candidate_set=candidates(),
            target=TARGET,
            processed_event_ids=frozenset({"trace:known"}),
            processed_event_receipts={"trace:known": ["diffusion-v1"]},
        )


def test_opaque_root_trace_id_containing_diffuse_text_still_diffuses() -> None:
    root = replace(
        trail("candidate:alpha", strength=2.0),
        trace_event_id="trace:caller:diffuse:opaque",
        lineage_event_ids=("trace:caller:diffuse:opaque",),
    )

    topology = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject("candidate", "candidate:alpha", "candidate:alpha", TARGET),
            PheromoneSubject("route", "route:a", "candidate:alpha", TARGET),
        ],
        edges=[
            PheromoneEdge("candidate", "candidate:alpha", "route", "route:a")
        ],
    )
    result = diffuse_pheromone_trails_with_records(
        [root],
        topology,
        policy(),
        PheromoneDiffusionPolicy(enabled=True, max_hops=1, attenuation=0.5),
        candidate_set=candidates(),
        target=TARGET,
    )

    derived = [item for item in result.trails if item.diffusion_hop > 0]
    assert derived
    assert derived[0].diffusion_root_trace_event_id == root.trace_event_id


def test_diffusion_ids_are_collision_free_for_namespaced_subject_components() -> None:
    root = trail("candidate:alpha", strength=4.0)
    topology = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject("candidate", "candidate:alpha", "candidate:alpha", TARGET),
            PheromoneSubject("x-a", "b:c", "candidate:alpha", TARGET),
            PheromoneSubject("x-a:b", "c", "candidate:alpha", TARGET),
        ],
        edges=[
            PheromoneEdge("candidate", "candidate:alpha", "x-a", "b:c"),
            PheromoneEdge("candidate", "candidate:alpha", "x-a:b", "c"),
        ],
    )

    result = diffuse_pheromone_trails_with_records(
        [root],
        topology,
        policy(),
        PheromoneDiffusionPolicy(enabled=True, max_hops=1, attenuation=0.5),
        candidate_set=candidates(),
        target=TARGET,
    )

    derived = [item for item in result.trails if item.diffusion_hop == 1]
    assert len(derived) == 2
    assert len({item.trace_event_id for item in derived}) == 2
    assert result.replayed_event_ids == ()


def test_feedback_keeps_source_lineage_independent() -> None:
    result = reinforce_pheromone_trails_with_records(
        [],
        [
            feedback(trace_id="trace:feedback:a", source_id="source:a"),
            feedback(trace_id="trace:feedback:b", source_id="source:b"),
        ],
        policy(feedback_enabled=True),
        candidate_set=candidates(),
        target=TARGET,
    )

    assert {(item.source_id, item.strength) for item in result.trails} == {
        ("source:a", 1.0),
        ("source:b", 1.0),
    }


def test_one_stale_feedback_issues_unique_mutation_ids_for_multiple_kinds() -> None:
    existing = [
        trail(
            trace_id="trace:route:positive",
            source_id="source:a",
            strength=3.0,
            kind="positive",
            subject_type="route",
            subject_id="route:a",
        ),
        trail(
            trace_id="trace:route:cautionary",
            source_id="source:a",
            strength=2.0,
            kind="cautionary",
            subject_type="route",
            subject_id="route:a",
        ),
    ]
    stale = feedback(trace_id="trace:feedback:stale", outcome="stale", delta=0.0)

    result = reinforce_pheromone_trails_with_records(
        existing,
        [stale],
        policy(feedback_enabled=True),
        candidate_set=candidates(),
        target=TARGET,
    )

    assert {item.kind for item in result.trails} == {"stale"}
    assert len({item.trace_event_id for item in result.trails}) == 2
    assert all(
        stale.trace_event_id in item.lineage_event_ids for item in result.trails
    )
    assert {record.source_trace_event_id for record in result.records} == {
        "trace:route:positive",
        "trace:route:cautionary",
    }
    assert {record.cause_trace_event_id for record in result.records} == {
        stale.trace_event_id
    }
    replay = reinforce_pheromone_trails_with_records(
        list(result.trails),
        [stale],
        policy(feedback_enabled=True),
        candidate_set=candidates(),
        target=TARGET,
        processed_feedback_ids=result.processed_feedback_ids,
    )
    assert replay.trails == result.trails
    assert replay.replayed_feedback_ids == (stale.trace_event_id,)


def test_caller_trail_lineage_cannot_forge_feedback_replay_authority() -> None:
    future_feedback_id = "trace:feedback:future:stale"
    forged = replace(
        trail(
            trace_id="trace:route:existing",
            source_id="source:a",
            strength=3.0,
            subject_type="route",
            subject_id="route:a",
        ),
        lineage_event_ids=("trace:route:existing", future_feedback_id),
    )
    stale = feedback(trace_id=future_feedback_id, outcome="stale", delta=0.0)

    result = reinforce_pheromone_trails_with_records(
        [forged],
        [stale],
        policy(feedback_enabled=True),
        candidate_set=candidates(),
        target=TARGET,
    )

    assert result.replayed_feedback_ids == ()
    assert result.processed_feedback_ids == frozenset({future_feedback_id})
    assert result.trails[0].kind == "stale"
    assert result.trails[0].strength == 0.0


@pytest.mark.parametrize(
    "field_name",
    ["source_id", "subject_id", "candidate_id", "target", "provenance", "trace_event_id"],
)
def test_feedback_rejects_whitespace_required_identity(field_name: str) -> None:
    with pytest.raises(GovernanceError, match="pheromone feedback"):
        reinforce_pheromone_trails_with_records(
            [],
            [replace(feedback(trace_id="trace:feedback:blank"), **{field_name: "   "})],
            policy(feedback_enabled=True),
            candidate_set=candidates(),
            target=TARGET,
        )


def test_feedback_rejects_whitespace_processed_replay_id() -> None:
    with pytest.raises(GovernanceError, match="processed pheromone feedback ids"):
        reinforce_pheromone_trails_with_records(
            [],
            [],
            policy(feedback_enabled=True),
            processed_feedback_ids=frozenset({"   "}),
        )


def test_kind_suppression_and_per_kind_competition_are_executable() -> None:
    positive = trail(trace_id="trace:positive", source_id="source:positive", strength=5.0)
    caution = trail(
        trace_id="trace:caution",
        source_id="source:caution",
        strength=2.0,
        kind="cautionary",
    )
    no_suppression = score_pheromone_trails(
        candidate_set=candidates(),
        trails=[positive, caution],
        policy=policy(
            cautionary_override_threshold=2.0,
            kind_profiles={"cautionary": PheromoneKindProfile(weight=1.0, can_suppress_positive=False)},
        ),
    )
    suppression = score_pheromone_trails(
        candidate_set=candidates(),
        trails=[positive, caution],
        policy=policy(
            cautionary_override_threshold=2.0,
            kind_profiles={"cautionary": PheromoneKindProfile(weight=1.0, can_suppress_positive=True)},
        ),
    )
    competitive = score_pheromone_trails_result(
        candidate_set=candidates(),
        trails=[positive],
        policy=policy(
            kind_profiles={"positive": PheromoneKindProfile(weight=1.0, response_model="competitive")}
        ),
    )

    assert no_suppression["candidate:alpha"] == 3.0
    assert suppression["candidate:alpha"] == -2.0
    assert competitive.normalization is not None
    assert competitive.normalization.response_model == "competitive:positive"
    assert sum(competitive.scores.values()) == pytest.approx(0.0)
    for candidate_id, score in competitive.scores.items():
        assert sum(competitive.kind_breakdown[candidate_id].values()) == pytest.approx(score)
        assert sum(competitive.subject_breakdown[candidate_id].values()) == pytest.approx(score)


def test_source_capped_competitive_trail_cannot_trigger_normalization() -> None:
    result = score_pheromone_trails_result(
        candidate_set=candidates(),
        trails=[
            trail(strength=1.0, source_id="source:shared", trace_id="trace:positive"),
            trail(
                "candidate:beta",
                strength=1.0,
                source_id="source:shared",
                trace_id="trace:novelty",
                kind="novelty",
            ),
        ],
        policy=policy(
            per_source_cap=1.0,
            exploration_enabled=True,
            kind_profiles={
                "positive": PheromoneKindProfile(weight=1.0, priority=2),
                "novelty": PheromoneKindProfile(
                    weight=1.0,
                    priority=1,
                    response_model="competitive",
                ),
            },
        ),
    )

    assert result.normalization is None
    assert result.scores["candidate:alpha"] == 1.0
    assert result.scores["candidate:beta"] == 0.0


def test_exploration_is_explicit_bounded_and_stale_routes_only_reopen_as_observations() -> None:
    novelty = trail(kind="novelty", strength=4.0, updated_at_step=0)
    stale_route = trail(
        trace_id="trace:stale",
        strength=0.1,
        kind="stale",
        subject_type="route",
        subject_id="route:a",
    )
    disabled_scores = score_pheromone_trails(
        candidate_set=candidates(),
        trails=[novelty],
        policy=policy(exploration_enabled=False, exploration_floor=0.5),
    )
    enabled_policy = policy(
        exploration_enabled=True,
        exploration_floor=0.5,
        novelty_decay_rate=0.5,
        stale_route_reopen_threshold=0.2,
    )
    enabled_scores = score_pheromone_trails(
        candidate_set=candidates(),
        trails=[novelty, stale_route],
        policy=enabled_policy,
        current_step=2,
    )
    observations = observe_pheromone_exploration(
        candidate_set=candidates(),
        trails=[novelty, stale_route],
        policy=enabled_policy,
        current_step=2,
        target=TARGET,
    )

    assert disabled_scores["candidate:alpha"] == 0
    assert disabled_scores["candidate:beta"] == 0
    assert enabled_scores["candidate:alpha"] == 1.0  # novelty 4 * .25 * default .5 + floor .5
    assert enabled_scores["candidate:beta"] == 0.5
    assert enabled_scores["candidate:fallback"] == 0
    assert any(item.reopen_eligible and item.subject_id == "route:a" for item in observations)


def test_response_and_runtime_exploration_floors_have_distinct_semantics() -> None:
    active_candidates = CandidateSet(
        [candidate for candidate in candidates().candidates if candidate.target == TARGET]
    )
    response_only = score_pheromone_trails(
        candidate_set=active_candidates,
        trails=[],
        policy=policy(
            response_exploration_floor=0.4,
            exploration_enabled=False,
            exploration_floor=0.9,
        ),
    )
    runtime_only = score_pheromone_trails(
        candidate_set=active_candidates,
        trails=[],
        policy=policy(
            response_exploration_floor=0.0,
            exploration_enabled=True,
            exploration_floor=0.2,
        ),
    )
    combined = score_pheromone_trails_result(
        candidate_set=active_candidates,
        trails=[],
        policy=policy(
            response_exploration_floor=0.4,
            exploration_enabled=True,
            exploration_floor=0.2,
        ),
    )

    assert response_only == {
        "candidate:alpha": 0.4,
        "candidate:beta": 0.4,
        "candidate:fallback": 0.0,
    }
    assert runtime_only == {
        "candidate:alpha": 0.2,
        "candidate:beta": 0.2,
        "candidate:fallback": 0.0,
    }
    assert combined.scores["candidate:alpha"] == pytest.approx(0.6)
    assert combined.score_breakdown["candidate:alpha"]["pheromone_response_floor"] == 0.4
    assert combined.score_breakdown["candidate:alpha"]["pheromone_novelty"] == 0.2
    assert combined.kind_breakdown["candidate:alpha"]["response_exploration_floor"] == 0.4


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), True])
def test_runtime_numeric_inputs_must_be_finite_non_boolean(invalid: object) -> None:
    with pytest.raises(GovernanceError):
        validate_pheromone_trail(
            replace(trail(), strength=invalid),
            policy(),
            candidate_set=candidates(),
        )
    with pytest.raises(GovernanceError):
        validate_layer_proposal(
            replace(proposal("learned"), confidence=invalid),
            candidate_set=candidates(),
            target=TARGET,
        )


def test_layer_actions_snapshots_emergency_and_conflict_resolution_are_deterministic() -> None:
    snapshots = [
        LayerPerformanceSnapshot(
            "reactive",
            recent_success_rate=0.0,
            recent_conflict_rate=1.0,
            recent_fallback_rate=1.0,
            mean_confidence=0.0,
            evidence_coverage=0.0,
            trace_coverage=0.0,
        ),
        LayerPerformanceSnapshot(
            "learned",
            recent_success_rate=1.0,
            recent_conflict_rate=0.0,
            recent_fallback_rate=0.0,
            mean_confidence=1.0,
            evidence_coverage=1.0,
            trace_coverage=1.0,
        ),
    ]
    normal = allocate_layer_weights(layer_policy(), snapshots)
    emergency = allocate_layer_weights(layer_policy(), snapshots, active_emergency=True)
    assert normal["reactive"] < normal["learned"]
    assert emergency["reactive"] >= 1.0

    conflicted = evaluate_layer_coordination(
        candidate_set=candidates(),
        target=TARGET,
        policy=layer_policy(min_layer_provenance=2),
        fallback_candidate_id="candidate:fallback",
        proposals=[
            proposal("learned", "candidate:alpha", confidence=0.9, trace_id="trace:learned"),
            proposal("evolutionary", "candidate:beta", confidence=0.85, trace_id="trace:evolutionary"),
            proposal(
                "metacognitive",
                "candidate:alpha",
                action="resolve_conflict",
                confidence=0.95,
                trace_id="trace:metacognitive",
            ),
        ],
    )
    assert "candidate_support_conflict" in conflicted.conflicts
    assert conflicted.fallback_used is False
    assert conflicted.resolution == "metacognitive_conflict_resolution"

    alarm = replace(
        proposal("reactive", "candidate:alpha", action="alarm", confidence=0.9, support=0.0),
        proposed_pheromone_kind="alarm",
        proposed_strength=1.0,
    )
    emergency_state = evaluate_layer_coordination(
        candidate_set=candidates(),
        target=TARGET,
        policy=layer_policy(min_layer_provenance=2),
        fallback_candidate_id="candidate:fallback",
        proposals=[alarm, proposal("learned", "candidate:alpha", trace_id="trace:learned:emergency")],
        snapshots=snapshots,
    )
    assert "reactive_emergency_exploitation_conflict" in emergency_state.conflicts
    assert emergency_state.fallback_used is True


def test_trace_coverage_confirmation_is_metacognitive_observable_and_resolves_only_matching_gap() -> None:
    active_policy = layer_policy(min_layer_provenance=1)
    learned = proposal("learned", "candidate:alpha", trace_id="trace:learned:coverage")
    degraded = [
        LayerPerformanceSnapshot(
            "learned",
            recent_success_rate=1.0,
            mean_confidence=0.9,
            evidence_coverage=1.0,
            trace_coverage=0.1,
        )
    ]
    without_confirmation = evaluate_layer_coordination(
        candidate_set=candidates(),
        target=TARGET,
        policy=active_policy,
        fallback_candidate_id="candidate:fallback",
        proposals=[learned],
        snapshots=degraded,
    )
    confirmation = proposal(
        "metacognitive",
        "candidate:alpha",
        action="confirm_trace_coverage",
        confidence=0.8,
        support=0.0,
        trace_id="trace:meta:coverage",
    )
    confirmed = evaluate_layer_coordination(
        candidate_set=candidates(),
        target=TARGET,
        policy=active_policy,
        fallback_candidate_id="candidate:fallback",
        proposals=[learned, confirmation],
        snapshots=degraded,
    )

    assert "insufficient_trace_coverage" in without_confirmation.conflicts
    assert without_confirmation.fallback_used is True
    assert "insufficient_trace_coverage" not in confirmed.conflicts
    assert confirmed.trace_coverage_confirmations == {"candidate:alpha": 0.8}
    assert confirmed.action_effects[confirmation.trace_event_id] == "trace_coverage_confirmed"
    assert confirmed.score_breakdown["candidate:alpha"]["layer_metacognitive"] == 0
    assert confirmed.selected_candidate == "candidate:alpha"
    with pytest.raises(GovernanceError, match="metacognitive layer"):
        validate_layer_proposal(
            replace(confirmation, layer_id="learned"),
            candidate_set=candidates(),
            target=TARGET,
        )


@pytest.mark.parametrize(
    ("action", "layer_id", "effect"),
    [
        ("support", "learned", "candidate_preference"),
        ("prefer_candidate", "learned", "candidate_preference"),
        ("route_preference", "learned", "candidate_preference"),
        ("risk", "learned", "candidate_risk_pressure"),
        ("alarm", "reactive", "reactive_emergency_pressure"),
        ("cautionary", "reactive", "reactive_emergency_pressure"),
        ("request_scouting", "learned", "scouting_required"),
        ("fallback_pressure", "reactive", "fallback_required"),
        ("confirm_trace_coverage", "metacognitive", "trace_coverage_confirmed"),
        ("resolve_conflict", "metacognitive", "metacognitive_conflict_resolution_proposed"),
        ("propose_pheromone", "evolutionary", "bounded_pheromone_deposit_proposed"),
    ],
)
def test_every_builtin_layer_action_has_declared_deterministic_semantics(
    action: str,
    layer_id: str,
    effect: str,
) -> None:
    item = proposal(layer_id, action=action, support=1.0)
    if action == "propose_pheromone":
        item = replace(item, proposed_pheromone_kind="positive", proposed_strength=1.0)
    validate_layer_proposal(item, candidate_set=candidates(), target=TARGET)

    assert layer_action_effect(item, layer_policy()) == effect


def test_positive_pheromone_proposal_materializes_as_bounded_memory_not_layer_authority() -> None:
    active_policy = layer_policy()
    proposed = replace(
        proposal(
            "evolutionary",
            "candidate:alpha",
            action="propose_pheromone",
            confidence=0.8,
            support=0.0,
            trace_id="trace:layer:pheromone",
        ),
        proposed_pheromone_kind="positive",
        proposed_strength=2.0,
    )
    trails = materialize_layer_pheromone_proposals(
        proposals=[proposed],
        candidate_set=candidates(),
        target=TARGET,
        current_step=3,
        policy=active_policy,
    )
    state = evaluate_layer_coordination(
        candidate_set=candidates(),
        target=TARGET,
        policy=active_policy,
        fallback_candidate_id="candidate:fallback",
        proposals=[proposed],
    )

    assert len(trails) == 1
    assert trails[0].candidate_id == "candidate:alpha"
    assert trails[0].kind == "positive"
    assert trails[0].strength == pytest.approx(1.6)
    assert trails[0].source_id == proposed.source_id
    assert trails[0].trace_event_id == proposed.trace_event_id
    assert state.action_effects[proposed.trace_event_id] == "bounded_pheromone_deposit_proposed"
    assert state.pheromone_proposal_trace_ids == (proposed.trace_event_id,)
    assert state.score_breakdown["candidate:alpha"]["layer_evolutionary"] == 0
    assert state.fallback_used is True

    for invalid in (
        replace(proposed, proposed_pheromone_kind=""),
        replace(proposed, proposed_strength=0.0),
    ):
        with pytest.raises(GovernanceError):
            validate_layer_proposal(invalid, candidate_set=candidates(), target=TARGET)
    with pytest.raises(GovernanceError, match="not declared in topology"):
        materialize_layer_pheromone_proposals(
            proposals=[proposed],
            candidate_set=candidates(),
            target=TARGET,
            current_step=3,
            policy=active_policy,
            neighborhood=PheromoneNeighborhood(
                subjects=[
                    PheromoneSubject("candidate", "candidate:beta", "candidate:beta", TARGET)
                ]
                ),
            )
    bound_elsewhere = replace(
        proposed,
        metadata={"subject_type": "route", "subject_id": "route:shared"},
    )
    with pytest.raises(GovernanceError, match="candidate binding"):
        materialize_layer_pheromone_proposals(
            proposals=[bound_elsewhere],
            candidate_set=candidates(),
            target=TARGET,
            current_step=3,
            policy=active_policy,
            neighborhood=PheromoneNeighborhood(
                subjects=[
                    PheromoneSubject("route", "route:shared", "candidate:beta", TARGET)
                ]
            ),
        )


def test_strategy_bias_is_bounded_traceable_and_uses_its_own_score_category() -> None:
    active_policy = layer_policy(max_strategy_bias=1.0)
    bias = StrategyBias(
        layer_id="evolutionary",
        candidate_id="candidate:alpha",
        support=0.5,
        provenance="runtime:evolutionary",
        trace_event_id="trace:bias",
        target=TARGET,
        source_id="source:evolutionary",
        confidence=0.8,
        evidence_id="evidence:bias",
    )
    validate_strategy_bias(bias, active_policy, candidate_set=candidates(), target=TARGET)
    state = evaluate_layer_coordination(
        candidate_set=candidates(),
        target=TARGET,
        policy=active_policy,
        fallback_candidate_id="candidate:fallback",
        proposals=[],
        strategy_biases=[bias],
    )
    assert state.score_breakdown["candidate:alpha"]["layer_evolutionary"] == pytest.approx(0.4)
    assert state.selected_candidate == "candidate:alpha"
    with pytest.raises(GovernanceError):
        validate_strategy_bias(replace(bias, support=1.1), active_policy, candidate_set=candidates(), target=TARGET)


def test_layer_coordination_policy_recursively_freezes_validated_weight_bounds() -> None:
    caller_bounds = {
        layer: [0.0, 2.0]
        for layer in ("reactive", "learned", "evolutionary", "metacognitive")
    }
    active_policy = layer_policy(layer_weight_bounds=caller_bounds)
    validate_layer_coordination_policy(active_policy)
    before = allocate_layer_weights(active_policy)

    caller_bounds["learned"][1] = 10.0
    with pytest.raises(TypeError):
        active_policy.layer_weight_bounds["learned"][1] = 10.0
    with pytest.raises(TypeError):
        active_policy.default_layer_weights["learned"] = 10.0
    with pytest.raises(TypeError):
        active_policy.confidence_thresholds["learned"] = 0.0

    assert active_policy.layer_weight_bounds["learned"] == (0.0, 2.0)
    assert allocate_layer_weights(active_policy) == before


def test_policy_adjustment_overlay_is_allowlisted_immutable_run_scoped_and_replay_safe() -> None:
    collective = CollectiveDecisionPolicy(
        mode="hybrid",
        pheromone_evaporation_rate=0.2,
        pheromone_response_model="linear",
        pheromone_kind_profiles={
            "positive": PheromoneKindProfile(
                weight=1.0,
                evaporation_rate=0.9,
                response_model="linear",
            )
        },
        layer_weight_bounds={"learned": (0.0, 2.0)},
        layer_default_weights={"learned": 1.0},
        policy_adjustment_bounds={
            "pheromone_evaporation_rate": [0.1, 0.5],
            "pheromone_positive_weight": [0.5, 2.0],
            "pheromone_response_model": {"allowed_values": ["linear", "saturating"]},
            "layer_learned_weight": [0.0, 2.0],
            "layer_emergency_override_threshold": [0.5, 1.0],
        },
    )
    item = PolicyAdjustmentProposal(
        layer_id="evolutionary",
        source_id="source:evolutionary",
        adjustments={
            "pheromone_evaporation_rate": 0.3,
            "pheromone_positive_weight": 1.5,
            "pheromone_response_model": "saturating",
            "layer_learned_weight": 1.25,
            "layer_emergency_override_threshold": 0.8,
        },
        provenance="runtime:evolutionary",
        trace_event_id="trace:adjustment",
    )
    overlay = validate_policy_adjustment_proposal(item, collective)
    adjusted = apply_policy_adjustment_overlay(collective, overlay)

    assert adjusted.pheromone_evaporation_rate == 0.3
    assert adjusted.pheromone_response_model == "saturating"
    assert adjusted.pheromone_kind_profiles["positive"].evaporation_rate == 0.3
    assert adjusted.pheromone_kind_profiles["positive"].response_model == "saturating"
    assert adjusted.pheromone_kind_profiles["positive"].weight == 1.5
    assert adjusted.layer_default_weights["learned"] == 1.25
    assert adjusted.layer_emergency_override_threshold == 0.8
    assert collective.pheromone_evaporation_rate == 0.2
    assert collective.pheromone_kind_profiles["positive"].weight == 1.0
    with pytest.raises(TypeError):
        overlay["pheromone_evaporation_rate"] = 0.4
    with pytest.raises(TypeError):
        dict.__setitem__(overlay, "pheromone_evaporation_rate", 0.4)
    with pytest.raises(AttributeError, match="immutable"):
        overlay._values = MappingProxyType({"pheromone_positive_weight": 1.8})
    with pytest.raises(GovernanceError, match="governance-validated"):
        apply_policy_adjustment_overlay(
            collective,
            RunScopedPolicyOverlay({"pheromone_positive_weight": 1.8}),
        )

    for field_name, forged_value in (
        (
            "_values",
            MappingProxyType({"pheromone_positive_weight": 1.8}),
        ),
        ("source_ids", ("source:forged",)),
        ("trace_event_ids", ("trace:forged",)),
    ):
        tampered = validate_policy_adjustment_proposal(item, collective)
        object.__setattr__(tampered, field_name, forged_value)
        assert run_scoped_policy_overlay_is_authoritative(tampered) is False
        with pytest.raises(GovernanceError, match="governance-validated"):
            apply_policy_adjustment_overlay(collective, tampered)

    first = validate_policy_adjustment_proposals([item], collective)
    replay = validate_policy_adjustment_proposals(
        [item],
        collective,
        processed_trace_event_ids=first.processed_trace_event_ids,
    )
    assert replay.overlay == {}
    with pytest.raises(GovernanceError, match="not allowlisted"):
        validate_policy_adjustment_proposal(
            replace(item, adjustments={"fallback_candidate": "candidate:alpha"}),
            collective,
        )
    with pytest.raises(TypeError):
        collective.policy_adjustment_bounds["pheromone_positive_weight"][1] = 10.0
    with pytest.raises(TypeError):
        collective.policy_adjustment_bounds["pheromone_positive_weight"] = (0.5, 10.0)
    with pytest.raises(GovernanceError, match="outside declared bounds"):
        validate_policy_adjustment_proposal(
            replace(item, adjustments={"pheromone_positive_weight": 9.0}),
            collective,
        )


@pytest.mark.parametrize(
    ("unsafe_bounds", "match"),
    [
        (
            {"layer_learned_weight": (0.0, 10.0)},
            "exceed declared layer weight bounds",
        ),
        (
            {"pheromone_cautionary_override_threshold": (0.0, 10.0)},
            "exceed the declared maximum strength",
        ),
    ],
)
def test_direct_policy_adjustment_bounds_cannot_escape_owned_policy_bounds(
    unsafe_bounds: dict[str, tuple[float, float]],
    match: str,
) -> None:
    base = CollectiveDecisionPolicy(
        pheromone_max_strength=1.0,
        layer_weight_bounds={"learned": (0.0, 1.0)},
        layer_default_weights={"learned": 0.5},
        policy_adjustment_bounds={
            "layer_learned_weight": (0.0, 1.0),
            "pheromone_cautionary_override_threshold": (0.0, 1.0),
        },
    )
    key = next(iter(unsafe_bounds))
    value = 9.0
    proposal = PolicyAdjustmentProposal(
        layer_id="evolutionary",
        source_id="source:evolutionary:unsafe-bounds",
        adjustments={key: value},
        provenance="runtime:evolutionary:unsafe-bounds",
        trace_event_id=f"trace:adjustment:unsafe-bounds:{key}",
    )
    unsafe = replace(base, policy_adjustment_bounds=unsafe_bounds)

    with pytest.raises(GovernanceError, match=match):
        validate_policy_adjustment_proposal(proposal, unsafe)

    # An overlay issued against a valid policy cannot be applied to a policy
    # whose declared adjustment envelope has subsequently escaped its owner.
    safe_proposal = replace(proposal, adjustments={key: 0.75})
    issued = validate_policy_adjustment_proposal(safe_proposal, base)
    with pytest.raises(GovernanceError, match=match):
        apply_policy_adjustment_overlay(unsafe, issued)


def test_frozen_governance_outputs_are_safe_to_deepcopy_and_not_caller_mutable() -> None:
    score = score_pheromone_trails_result(
        candidate_set=candidates(),
        trails=[trail()],
        policy=policy(),
    )
    state = evaluate_layer_coordination(
        candidate_set=candidates(),
        target=TARGET,
        policy=layer_policy(),
        fallback_candidate_id="candidate:fallback",
        proposals=[proposal("learned")],
    )
    assert deepcopy(score) is score
    assert deepcopy(state) is state
    with pytest.raises(TypeError):
        score.scores["candidate:alpha"] = 100
    with pytest.raises(TypeError):
        state.allocated_weights["learned"] = 100


def test_layer_policy_deeply_snapshots_caller_owned_adjustment_bounds() -> None:
    caller_bounds = [0.0, 0.1]
    active_policy = LayerCoordinationPolicy(
        policy_adjustment_bounds={"pheromone_evaporation_rate": caller_bounds}
    )
    caller_bounds[1] = 1.0
    item = PolicyAdjustmentProposal(
        layer_id="evolutionary",
        source_id="source:evolutionary:snapshot",
        adjustments={"pheromone_evaporation_rate": 0.9},
        provenance="runtime:evolutionary:snapshot",
        trace_event_id="trace:adjustment:snapshot",
    )

    with pytest.raises(GovernanceError, match="outside declared bounds"):
        validate_policy_adjustment_proposal(item, active_policy)
