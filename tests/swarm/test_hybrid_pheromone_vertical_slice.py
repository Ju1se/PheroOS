import importlib.util
from dataclasses import replace
from itertools import combinations
from pathlib import Path
from types import MappingProxyType

import pytest

from pheroos.governance import (
    AuthorityLevel,
    Candidate,
    CandidateSet,
    EvidenceGraph,
    EvidenceNode,
    InhibitionSignal,
    HybridReplayState,
    LayerPerformanceSnapshot,
    LayerProposal,
    OutputContract,
    PheromoneExplorationObservation,
    PheromoneEdge,
    PheromoneFeedback,
    PheromoneNeighborhood,
    PheromoneSubject,
    PheromoneTrail,
    PolicyAdjustmentProposal,
    RecruitmentSignal,
    ScoutReport,
    StopResolution,
    StrategyBias,
    evaluate_hybrid_collective_step,
    evaluate_output_authorization,
    hybrid_collective_step_is_authoritative,
    hybrid_replay_state_is_authoritative,
    replay_state_from_hybrid_step,
    RunScopedPolicyOverlay,
    verify_signal_input,
)
from pheroos.protocol import collective_fallback_id, load_capability_manifest, validate_capability_manifest
from pheroos.governance.errors import GovernanceError
from pheroos.trace import InMemoryTraceStore


HYBRID_TRACE_ID_SURFACES = (
    "deposit",
    "feedback",
    "adjustment",
    "scout_source",
    "scout_verification",
    "layer_proposal",
    "strategy_bias",
)
HYBRID_TRACE_ID_COLLISIONS = tuple(combinations(HYBRID_TRACE_ID_SURFACES, 2))
HYBRID_RECEIPT_FIELDS = (
    "deposit_replay_receipts",
    "diffusion_replay_receipts",
    "feedback_replay_receipts",
    "adjustment_replay_receipts",
)
HYBRID_RECEIPT_COLLISIONS = tuple(combinations(HYBRID_RECEIPT_FIELDS, 2))


def test_provider_free_hybrid_pheromone_vertical_slice() -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    protocol = manifest.protocol
    policy = protocol.collective_decision_policy
    target = protocol.quorum_policy.target

    assert policy is not None
    assert validate_capability_manifest(manifest) == []

    candidates = CandidateSet(
        [
            Candidate(candidate.id, candidate.target, candidate.safe_fallback)
            for candidate in protocol.candidates
        ]
    )
    step = evaluate_hybrid_collective_step(
        protocol_id=protocol.id,
        candidate_set=candidates,
        policy=policy,
        target=target,
        current_step=1,
        scout_reports=[
            verified_scout("scout:a", "candidate:alpha", target),
            verified_scout("scout:b", "candidate:alpha", target),
        ],
        recruitment_signals=[verified_recruitment("recruit:a", "candidate:alpha", target, 1.0)],
        inhibition_signals=[verified_inhibition("inhibit:a", "candidate:beta", target, 0.5)],
        deposits=deposits(target),
        topology=topology(target),
        feedback=feedback(target),
        layer_proposals=layer_proposals(target),
        performance_snapshots=[
            LayerPerformanceSnapshot(
                "learned",
                recent_success_rate=0.8,
                recent_conflict_rate=0.1,
                recent_fallback_rate=0.1,
                mean_confidence=0.8,
                evidence_coverage=1.0,
                trace_coverage=1.0,
            )
        ],
        strategy_biases=[
            StrategyBias(
                layer_id="evolutionary",
                candidate_id="candidate:alpha",
                support=0.4,
                provenance="runtime:evolutionary",
                trace_event_id="trace:bias:evolutionary",
                target=target,
                source_id="layer:evolutionary",
                confidence=0.8,
                evidence_id="evidence:evolutionary",
            )
        ],
        adjustment_proposals=[
            PolicyAdjustmentProposal(
                layer_id="evolutionary",
                source_id="layer:evolutionary",
                adjustments={"pheromone_positive_weight": 1.2},
                provenance="runtime:evolutionary",
                trace_event_id="trace:adjustment:evolutionary",
            )
        ],
        fallback_candidate_id=collective_fallback_id(protocol),
    )

    evidence = EvidenceGraph(
        [
            EvidenceNode("evidence:scout:a", "candidate:alpha", "driver:scout:a"),
            EvidenceNode("evidence:scout:b", "candidate:alpha", "driver:scout:b"),
        ]
    )
    output = evaluate_output_authorization(
        OutputContract(
            committed_candidate_required=protocol.output_policy.requires_committed_candidate,
            evidence_required=protocol.output_policy.requires_evidence_contract,
            stop_resolution_required=protocol.output_policy.requires_stop_resolution,
            publication_permission_required=protocol.output_policy.requires_publication_permission,
        ),
        step.decision,
        evidence,
        [StopResolution(target=target, action="publish", blocked=False)],
        publication_permission=True,
        protocol_id=protocol.id,
        candidate_set=candidates,
    )
    trace = InMemoryTraceStore()
    for trace_event in (*step.trace_events, output.trace_event):
        trace.append(trace_event)

    observed = {event.event_type for event in trace.events}
    assert step.decision.candidate_id == "candidate:alpha"
    assert step.decision.reason == "collective_consensus"
    assert output.authorized is True
    assert sum(step.state.score_breakdown["candidate:alpha"].values()) == step.state.scores["candidate:alpha"]
    assert step.adjustment_overlay == {"pheromone_positive_weight": 1.2}
    assert step.budget_state is not None
    assert step.budget_state.round_used <= policy.pheromone_per_round_deposit_cap
    assert all(
        used <= policy.pheromone_per_source_cap
        for used in step.budget_state.source_used.values()
    )
    assert step.layer_coordination.trace_coverage_confirmations == {"candidate:alpha": 0.8}
    assess_event = next(event for event in step.trace_events if event.event_type == "coordination_assess")
    assert assess_event.lineage["trace_coverage_confirmations"] == {"candidate:alpha": 0.8}
    assert {
        "pheromone_deposit",
        "pheromone_diffuse",
        "pheromone_reinforce",
        "pheromone_normalize",
        "layer_proposal",
        "coordination_assess",
        "coordination_resolve",
        "policy_adjustment",
        "candidate_score",
        "commit",
        "output",
    }.issubset(observed)
    assert {"pheromone_expire", "fallback", "recovery"}.isdisjoint(observed)


def test_hybrid_example_script_uses_complete_reference_path() -> None:
    path = Path.cwd() / "examples/hybrid-pheromone-protocol/run.py"
    spec = importlib.util.spec_from_file_location("hybrid_pheromone_example", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.run_example(Path.cwd())

    assert result["authorized"] is True
    assert result["decision"]["reason"] == "collective_consensus"
    assert "candidate_score" in result["trace_events"]
    assert "output" in result["trace_events"]
    assert "fallback" not in result["trace_events"]


def test_full_hybrid_step_applies_declared_novelty_decay() -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    protocol = manifest.protocol
    base = protocol.collective_decision_policy
    target = protocol.quorum_policy.target
    assert base is not None
    candidates = CandidateSet(
        [Candidate(item.id, item.target, item.safe_fallback) for item in protocol.candidates]
    )
    novelty = PheromoneTrail(
        candidate_id="candidate:alpha",
        strength=8.0,
        subject_type="route",
        subject_id="route:alpha",
        target=target,
        kind="novelty",
        source_id="source:novelty",
        evidence_id="evidence:novelty",
        provenance="driver:novelty",
        trace_event_id="trace:novelty",
        deposited_at_step=0,
        updated_at_step=0,
        ttl_steps=10,
    )

    def evaluate(decay: float):
        return evaluate_hybrid_collective_step(
            protocol_id=protocol.id,
            candidate_set=candidates,
            policy=replace(base, novelty_decay_rate=decay),
            target=target,
            current_step=2,
            scout_reports=[],
            existing_trails=[novelty],
            topology=topology(target),
            fallback_candidate_id=collective_fallback_id(protocol),
        )

    no_decay = evaluate(0.0)
    strong_decay = evaluate(0.9)
    no_decay_strength = sum(
        trail.strength for trail in no_decay.active_trails if trail.kind == "novelty"
    )
    strong_decay_strength = sum(
        trail.strength for trail in strong_decay.active_trails if trail.kind == "novelty"
    )

    assert strong_decay_strength < no_decay_strength
    assert strong_decay.state.scores["candidate:alpha"] < no_decay.state.scores["candidate:alpha"]


def test_full_hybrid_step_uses_safe_fallback_for_unresolved_emergency_conflict() -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    protocol = manifest.protocol
    policy = protocol.collective_decision_policy
    target = protocol.quorum_policy.target
    assert policy is not None
    candidates = CandidateSet(
        [Candidate(item.id, item.target, item.safe_fallback) for item in protocol.candidates]
    )
    step = evaluate_hybrid_collective_step(
        protocol_id=protocol.id,
        candidate_set=candidates,
        policy=policy,
        target=target,
        current_step=1,
        scout_reports=[
            verified_scout("scout:conflict:a", "candidate:alpha", target),
            verified_scout("scout:conflict:b", "candidate:alpha", target),
        ],
        deposits=[route_trail("candidate:alpha", "route:alpha", target, "positive", 1.0, "source:alpha")],
        topology=topology(target),
        layer_proposals=[
            LayerProposal(
                "reactive",
                "layer:reactive",
                target,
                "candidate:alpha",
                "alarm",
                0.9,
                risk=1.0,
                proposed_pheromone_kind="alarm",
                proposed_strength=1.0,
                evidence_id="evidence:reactive",
                provenance="runtime:reactive",
                trace_event_id="trace:conflict:reactive",
            ),
            LayerProposal(
                "learned",
                "layer:learned",
                target,
                "candidate:alpha",
                "support",
                0.9,
                support=2.0,
                evidence_id="evidence:learned",
                provenance="runtime:learned",
                trace_event_id="trace:conflict:learned",
            ),
        ],
        fallback_candidate_id=collective_fallback_id(protocol),
    )

    observed = [event.event_type for event in step.trace_events]
    assert step.layer_coordination.fallback_used is True
    assert step.decision.candidate_id == "candidate:safe_fallback"
    assert step.decision.reason == "safe_layer_coordination_fallback"
    assert observed.count("fallback") == 1
    assert "commit" not in observed


def test_positive_layer_pheromone_proposal_enters_full_step_only_through_governed_deposit() -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    protocol = manifest.protocol
    policy = protocol.collective_decision_policy
    target = protocol.quorum_policy.target
    assert policy is not None
    candidates = CandidateSet(
        [Candidate(item.id, item.target, item.safe_fallback) for item in protocol.candidates]
    )
    pheromone_proposal = LayerProposal(
        "evolutionary",
        "layer:evolutionary:pheromone",
        target,
        "candidate:alpha",
        "propose_pheromone",
        0.8,
        proposed_pheromone_kind="positive",
        proposed_strength=1.0,
        evidence_id="evidence:evolutionary:pheromone",
        provenance="runtime:evolutionary:pheromone",
        trace_event_id="trace:layer:evolutionary:pheromone",
    )
    step = evaluate_hybrid_collective_step(
        protocol_id=protocol.id,
        candidate_set=candidates,
        policy=policy,
        target=target,
        current_step=1,
        scout_reports=[
            verified_scout("scout:proposal:a", "candidate:alpha", target),
            verified_scout("scout:proposal:b", "candidate:alpha", target),
        ],
        recruitment_signals=[
            verified_recruitment("recruit:proposal", "candidate:alpha", target, 1.0)
        ],
        topology=topology(target),
        layer_proposals=[*layer_proposals(target), pheromone_proposal],
        fallback_candidate_id=collective_fallback_id(protocol),
    )

    proposed_trails = [
        trail
        for trail in step.active_trails
        if trail.trace_event_id == pheromone_proposal.trace_event_id
    ]
    assert len(proposed_trails) == 1
    assert proposed_trails[0].kind == "positive"
    assert proposed_trails[0].strength == 0.8
    assert step.layer_coordination.action_effects[pheromone_proposal.trace_event_id] == (
        "bounded_pheromone_deposit_proposed"
    )
    assert any(
        record.trace_event_id == pheromone_proposal.trace_event_id
        and record.action == "deposit"
        for record in step.deposit_records
    )
    assert pheromone_proposal.trace_event_id in step.processed_pheromone_event_ids
    assert step.decision.candidate_id == "candidate:alpha"

    proposal_event_index = next(
        index
        for index, event in enumerate(step.trace_events)
        if event.event_type == "layer_proposal"
        and event.lineage.get("source_trace_event_id") == pheromone_proposal.trace_event_id
    )
    proposal_event = step.trace_events[proposal_event_index]
    assert proposal_event.lineage["effect"] == "bounded_pheromone_deposit_proposed"
    assert proposal_event.lineage["proposed_pheromone_kind"] == "positive"
    assert proposal_event.lineage["proposed_strength"] == 1.0
    deposit_event_index = next(
        index
        for index, event in enumerate(step.trace_events)
        if event.event_type == "pheromone_deposit"
        and event.lineage.get("source_trace_event_id") == pheromone_proposal.trace_event_id
    )
    assert proposal_event_index < deposit_event_index
    assert hybrid_collective_step_is_authoritative(step) is True


def test_full_hybrid_step_accepts_unique_trace_ids_across_input_surfaces() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    target = manifest.protocol.quorum_policy.target

    step = evaluate_hybrid_trace_identity_step(
        manifest,
        hybrid_trace_identity_inputs(target, collided_surfaces=set()),
    )

    assert hybrid_collective_step_is_authoritative(step) is True


@pytest.mark.parametrize(
    ("left_surface", "right_surface"),
    HYBRID_TRACE_ID_COLLISIONS,
    ids=lambda value: value,
)
def test_full_hybrid_step_rejects_trace_id_reuse_across_input_surfaces(
    left_surface: str,
    right_surface: str,
) -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    target = manifest.protocol.quorum_policy.target
    inputs = hybrid_trace_identity_inputs(
        target,
        collided_surfaces={left_surface, right_surface},
    )

    with pytest.raises(GovernanceError, match="trace_event_id"):
        evaluate_hybrid_trace_identity_step(manifest, inputs)


@pytest.mark.parametrize(
    ("left_field", "right_field"),
    HYBRID_RECEIPT_COLLISIONS,
    ids=lambda value: value.removesuffix("_replay_receipts"),
)
@pytest.mark.parametrize("authority_record", ["step", "replay_state"])
def test_hybrid_authority_rejects_cross_lifecycle_receipt_id_collisions(
    left_field: str,
    right_field: str,
    authority_record: str,
) -> None:
    protocol, candidates, policy, target, step = issued_authority_step()
    record = (
        step
        if authority_record == "step"
        else replay_state_from_hybrid_step(step)
    )
    insert_cross_lifecycle_receipt_collision(record, left_field, right_field)

    if authority_record == "step":
        assert hybrid_collective_step_is_authoritative(record) is False
        with pytest.raises(GovernanceError, match="governance-issued step"):
            replay_state_from_hybrid_step(record)
    else:
        assert hybrid_replay_state_is_authoritative(record) is False
        with pytest.raises(GovernanceError, match="not governance-issued"):
            evaluate_hybrid_collective_step(
                protocol_id=protocol.id,
                candidate_set=candidates,
                policy=policy,
                target=target,
                current_step=2,
                scout_reports=[
                    verified_scout(
                        "scout:receipt-collision:a",
                        "candidate:alpha",
                        target,
                    ),
                    verified_scout(
                        "scout:receipt-collision:b",
                        "candidate:alpha",
                        target,
                    ),
                ],
                topology=topology(target),
                replay_state=record,
                fallback_candidate_id=collective_fallback_id(protocol),
            )


def test_full_hybrid_step_is_permutation_invariant_for_set_inputs() -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    protocol = manifest.protocol
    policy = protocol.collective_decision_policy
    target = protocol.quorum_policy.target
    assert policy is not None
    candidates = CandidateSet(
        [Candidate(item.id, item.target, item.safe_fallback) for item in protocol.candidates]
    )
    scouts = [
        verified_scout("scout:permutation:a", "candidate:alpha", target),
        verified_scout("scout:permutation:b", "candidate:alpha", target),
    ]
    trail_items = deposits(target)
    feedback_items = feedback(target)
    proposal_items = layer_proposals(target)

    def run(*, reverse: bool):
        order = lambda values: list(reversed(values)) if reverse else values
        return evaluate_hybrid_collective_step(
            protocol_id=protocol.id,
            candidate_set=candidates,
            policy=policy,
            target=target,
            current_step=1,
            scout_reports=order(scouts),
            deposits=order(trail_items),
            topology=topology(target),
            feedback=order(feedback_items),
            layer_proposals=order(proposal_items),
            fallback_candidate_id=collective_fallback_id(protocol),
        )

    forward = run(reverse=False)
    reverse = run(reverse=True)

    assert reverse.decision == forward.decision
    assert reverse.state.scores == forward.state.scores
    assert reverse.active_trails == forward.active_trails
    assert reverse.budget_state == forward.budget_state
    assert [event.event_type for event in reverse.trace_events] == [
        event.event_type for event in forward.trace_events
    ]


def test_full_hybrid_step_records_processed_feedback_as_replay_observation() -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    protocol = manifest.protocol
    policy = protocol.collective_decision_policy
    target = protocol.quorum_policy.target
    assert policy is not None
    candidates = CandidateSet(
        [Candidate(item.id, item.target, item.safe_fallback) for item in protocol.candidates]
    )
    feedback_items = feedback(target)
    replayed_adjustment = PolicyAdjustmentProposal(
        layer_id="evolutionary",
        source_id="layer:evolutionary:replay",
        adjustments={"pheromone_positive_weight": 1.1},
        provenance="runtime:evolutionary:replay",
        trace_event_id="trace:adjustment:replay",
    )

    first = evaluate_hybrid_collective_step(
        protocol_id=protocol.id,
        candidate_set=candidates,
        policy=policy,
        target=target,
        current_step=1,
        scout_reports=[
            verified_scout("scout:replay:a", "candidate:alpha", target),
            verified_scout("scout:replay:b", "candidate:alpha", target),
        ],
        existing_trails=deposits(target),
        topology=topology(target),
        feedback=feedback_items,
        adjustment_proposals=[replayed_adjustment],
        fallback_candidate_id=collective_fallback_id(protocol),
    )
    step = evaluate_hybrid_collective_step(
        protocol_id=protocol.id,
        candidate_set=candidates,
        policy=policy,
        target=target,
        current_step=2,
        scout_reports=[
            verified_scout("scout:replay:a", "candidate:alpha", target),
            verified_scout("scout:replay:b", "candidate:alpha", target),
        ],
        topology=topology(target),
        feedback=feedback_items,
        adjustment_proposals=[replayed_adjustment],
        replay_state=replay_state_from_hybrid_step(first),
        fallback_candidate_id=collective_fallback_id(protocol),
    )

    replay_events = [
        event
        for event in step.trace_events
        if event.event_type == "pheromone_observe"
        and event.lineage.get("lifecycle") == "feedback"
    ]
    assert len(replay_events) == len(feedback_items)
    assert all(event.lineage["result"] == "replay_ignored" for event in replay_events)
    assert step.reinforcement_records == ()
    adjustment_event = next(
        event for event in step.trace_events if event.event_type == "policy_adjustment"
    )
    assert adjustment_event.lineage["result"] == "replay_ignored"
    assert step.adjustment_overlay == {}


def test_full_hybrid_step_rejects_forged_replay_suppression() -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    protocol = manifest.protocol
    policy = protocol.collective_decision_policy
    target = protocol.quorum_policy.target
    assert policy is not None
    candidates = CandidateSet(
        [Candidate(item.id, item.target, item.safe_fallback) for item in protocol.candidates]
    )
    adverse = feedback(target)[1]
    common = dict(
        protocol_id=protocol.id,
        candidate_set=candidates,
        policy=policy,
        target=target,
        current_step=1,
        scout_reports=[
            verified_scout("scout:forged:a", "candidate:alpha", target),
            verified_scout("scout:forged:b", "candidate:alpha", target),
        ],
        topology=topology(target),
        feedback=[adverse],
        fallback_candidate_id=collective_fallback_id(protocol),
    )

    with pytest.raises(GovernanceError, match="raw processed replay ids"):
        evaluate_hybrid_collective_step(
            **common,
            processed_feedback_ids=frozenset({adverse.trace_event_id}),
        )
    forged = HybridReplayState(
        protocol_id=protocol.id,
        target=target,
        processed_feedback_ids=frozenset({adverse.trace_event_id}),
    )
    with pytest.raises(GovernanceError, match="not governance-issued"):
        evaluate_hybrid_collective_step(**common, replay_state=forged)


def test_hybrid_replay_ids_are_bound_to_their_original_payloads() -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    protocol = manifest.protocol
    policy = protocol.collective_decision_policy
    target = protocol.quorum_policy.target
    assert policy is not None
    candidates = CandidateSet(
        [Candidate(item.id, item.target, item.safe_fallback) for item in protocol.candidates]
    )
    scouts = [
        verified_scout("scout:receipt:a", "candidate:alpha", target),
        verified_scout("scout:receipt:b", "candidate:alpha", target),
    ]
    deposit_items = deposits(target)
    feedback_item = feedback(target)[0]
    adjustment = PolicyAdjustmentProposal(
        layer_id="evolutionary",
        source_id="layer:evolutionary:receipt",
        adjustments={"pheromone_positive_weight": 1.1},
        provenance="runtime:evolutionary:receipt",
        trace_event_id="trace:adjustment:receipt",
    )
    first = evaluate_hybrid_collective_step(
        protocol_id=protocol.id,
        candidate_set=candidates,
        policy=policy,
        target=target,
        current_step=1,
        scout_reports=scouts,
        deposits=deposit_items,
        topology=topology(target),
        feedback=[feedback_item],
        adjustment_proposals=[adjustment],
        fallback_candidate_id=collective_fallback_id(protocol),
    )
    replay_state = replay_state_from_hybrid_step(first)
    common = dict(
        protocol_id=protocol.id,
        candidate_set=candidates,
        policy=policy,
        target=target,
        current_step=1,
        scout_reports=scouts,
        topology=topology(target),
        replay_state=replay_state,
        fallback_candidate_id=collective_fallback_id(protocol),
    )

    substitutions = (
        {"deposits": [replace(deposit_items[0], strength=2.0)]},
        {
            "feedback": [
                replace(
                    feedback_item,
                    outcome="stale",
                    reward=0.0,
                    strength_delta=0.0,
                )
            ]
        },
        {
            "adjustment_proposals": [
                replace(
                    adjustment,
                    adjustments={"pheromone_positive_weight": 1.2},
                )
            ]
        },
    )
    for changed_input in substitutions:
        with pytest.raises(GovernanceError, match="replay payload"):
            evaluate_hybrid_collective_step(**common, **changed_input)


@pytest.mark.parametrize(
    "field_name",
    [
        "decision",
        "state",
        "active_trails",
        "layer_coordination",
        "adjustment_overlay",
        "effective_policy",
        "deposit_records",
        "evaporation_records",
        "diffusion_records",
        "reinforcement_records",
        "exploration_observations",
        "processed_pheromone_event_ids",
        "processed_feedback_ids",
        "processed_adjustment_ids",
        "deposit_replay_receipts",
        "diffusion_replay_receipts",
        "feedback_replay_receipts",
        "adjustment_replay_receipts",
        "budget_state",
        "trace_events",
    ],
)
def test_hybrid_step_issuance_snapshot_rejects_every_authority_field_mutation(
    field_name: str,
) -> None:
    _, _, _, _, step = issued_authority_step()
    object.__setattr__(step, field_name, tampered_step_field(step, field_name))

    assert hybrid_collective_step_is_authoritative(step) is False
    with pytest.raises(GovernanceError, match="governance-issued step"):
        replay_state_from_hybrid_step(step)


@pytest.mark.parametrize(
    "field_name",
    [
        "protocol_id",
        "target",
        "active_trails",
        "processed_pheromone_event_ids",
        "processed_feedback_ids",
        "processed_adjustment_ids",
        "deposit_replay_receipts",
        "diffusion_replay_receipts",
        "feedback_replay_receipts",
        "adjustment_replay_receipts",
    ],
)
def test_hybrid_replay_issuance_snapshot_rejects_every_authority_field_mutation(
    field_name: str,
) -> None:
    protocol, candidates, policy, target, step = issued_authority_step()
    replay_state = replay_state_from_hybrid_step(step)
    object.__setattr__(
        replay_state,
        field_name,
        tampered_replay_field(replay_state, field_name),
    )

    assert hybrid_replay_state_is_authoritative(replay_state) is False
    with pytest.raises(GovernanceError, match="not governance-issued"):
        evaluate_hybrid_collective_step(
            protocol_id=protocol.id,
            candidate_set=candidates,
            policy=policy,
            target=target,
            current_step=2,
            scout_reports=[
                verified_scout("scout:authority:next:a", "candidate:alpha", target),
                verified_scout("scout:authority:next:b", "candidate:alpha", target),
            ],
            topology=topology(target),
            replay_state=replay_state,
            fallback_candidate_id=collective_fallback_id(protocol),
        )


def test_full_hybrid_step_traces_stale_feedback_without_consuming_budget() -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    protocol = manifest.protocol
    policy = protocol.collective_decision_policy
    target = protocol.quorum_policy.target
    assert policy is not None
    candidates = CandidateSet(
        [Candidate(item.id, item.target, item.safe_fallback) for item in protocol.candidates]
    )
    stale_feedback = PheromoneFeedback(
        "source:alpha",
        "route",
        "route:alpha",
        "candidate:alpha",
        target,
        "stale",
        evidence_id="evidence:route:alpha:stale",
        provenance="driver:route:alpha:stale",
        trace_event_id="trace:feedback:alpha:stale",
        step=1,
    )

    step = evaluate_hybrid_collective_step(
        protocol_id=protocol.id,
        candidate_set=candidates,
        policy=policy,
        target=target,
        current_step=1,
        scout_reports=[
            verified_scout("scout:stale:a", "candidate:alpha", target),
            verified_scout("scout:stale:b", "candidate:alpha", target),
        ],
        existing_trails=deposits(target),
        topology=topology(target),
        feedback=[stale_feedback],
        fallback_candidate_id=collective_fallback_id(protocol),
    )

    assert len(step.reinforcement_records) == 1
    assert step.reinforcement_records[0].action == "reinforce_stale"
    assert step.reinforcement_records[0].round_budget_remaining is not None
    assert step.reinforcement_records[0].source_budget_remaining is not None
    reinforce_event = next(
        event for event in step.trace_events if event.event_type == "pheromone_reinforce"
    )
    assert reinforce_event.lineage["budget_result"]["status"] == "applied"
    assert any(
        trail.subject_id == "route:alpha" and trail.kind == "stale"
        for trail in step.active_trails
    )


def test_full_hybrid_step_rejects_overstrength_existing_memory() -> None:
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    protocol = manifest.protocol
    policy = protocol.collective_decision_policy
    target = protocol.quorum_policy.target
    assert policy is not None
    candidates = CandidateSet(
        [Candidate(item.id, item.target, item.safe_fallback) for item in protocol.candidates]
    )
    overstrength = route_trail(
        "candidate:alpha",
        "route:alpha",
        target,
        "positive",
        policy.pheromone_max_strength + 1,
        "source:alpha",
    )

    with pytest.raises(GovernanceError, match="exceeds the declared maximum"):
        evaluate_hybrid_collective_step(
            protocol_id=protocol.id,
            candidate_set=candidates,
            policy=policy,
            target=target,
            current_step=1,
            scout_reports=[
                verified_scout("scout:overstrength:a", "candidate:alpha", target),
                verified_scout("scout:overstrength:b", "candidate:alpha", target),
            ],
            existing_trails=[overstrength],
            topology=topology(target),
            fallback_candidate_id=collective_fallback_id(protocol),
        )


def verified_scout(source_id: str, candidate_id: str, target: str) -> ScoutReport:
    trace_id = f"trace:{source_id}"
    return ScoutReport(
        scout_id=source_id,
        candidate_id=candidate_id,
        evidence_id=f"evidence:{source_id}",
        provenance=f"driver:{source_id}",
        target=target,
        trace_event_id=trace_id,
        verification=verification(source_id, candidate_id, target, trace_id),
    )


def verified_recruitment(
    source_id: str,
    candidate_id: str,
    target: str,
    strength: float,
) -> RecruitmentSignal:
    trace_id = f"trace:{source_id}"
    return RecruitmentSignal(
        source_id=source_id,
        candidate_id=candidate_id,
        strength=strength,
        target=target,
        provenance=f"governance:{source_id}",
        trace_event_id=trace_id,
        verification=verification(source_id, candidate_id, target, trace_id),
    )


def verified_inhibition(
    source_id: str,
    candidate_id: str,
    target: str,
    strength: float,
) -> InhibitionSignal:
    trace_id = f"trace:{source_id}"
    return InhibitionSignal(
        source_id=source_id,
        candidate_id=candidate_id,
        strength=strength,
        target=target,
        provenance=f"governance:{source_id}",
        trace_event_id=trace_id,
        verification=verification(source_id, candidate_id, target, trace_id),
    )


def verification(source_id: str, candidate_id: str, target: str, trace_id: str):
    return verify_signal_input(
        target=target,
        source_id=source_id,
        subject_id=candidate_id,
        verifier_id="governance:hybrid",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="governance:hybrid-verification",
        trace_event_id=f"{trace_id}:verified",
    )


def deposits(target: str) -> list[PheromoneTrail]:
    return [
        route_trail("candidate:alpha", "route:alpha", target, "positive", 1.0, "source:alpha"),
        route_trail("candidate:beta", "route:beta", target, "cautionary", 0.5, "source:beta"),
    ]


def route_trail(
    candidate_id: str,
    route_id: str,
    target: str,
    kind: str,
    strength: float,
    source_id: str,
) -> PheromoneTrail:
    return PheromoneTrail(
        candidate_id=candidate_id,
        strength=strength,
        subject_type="route",
        subject_id=route_id,
        target=target,
        kind=kind,
        source_id=source_id,
        evidence_id=f"evidence:{route_id}",
        provenance=f"driver:{route_id}",
        trace_event_id=f"trace:deposit:{route_id}",
        deposited_at_step=1,
        updated_at_step=1,
    )


def topology(target: str) -> PheromoneNeighborhood:
    return PheromoneNeighborhood(
        subjects=[
            PheromoneSubject("route", "route:alpha", "candidate:alpha", target),
            PheromoneSubject("route", "route:beta", "candidate:beta", target),
            PheromoneSubject("candidate", "candidate:alpha", "candidate:alpha", target),
            PheromoneSubject("candidate", "candidate:beta", "candidate:beta", target),
        ],
        edges=[
            PheromoneEdge("route", "route:alpha", "candidate", "candidate:alpha", 1.0),
            PheromoneEdge("route", "route:beta", "candidate", "candidate:beta", 1.0),
        ],
    )


def feedback(target: str) -> list[PheromoneFeedback]:
    return [
        PheromoneFeedback(
            "source:alpha",
            "route",
            "route:alpha",
            "candidate:alpha",
            target,
            "success",
            reward=1.0,
            strength_delta=1.0,
            evidence_id="evidence:route:alpha",
            provenance="driver:route:alpha",
            trace_event_id="trace:feedback:alpha",
            step=1,
        ),
        PheromoneFeedback(
            "source:beta",
            "route",
            "route:beta",
            "candidate:beta",
            target,
            "congested",
            reward=-0.5,
            strength_delta=0.5,
            evidence_id="evidence:route:beta",
            provenance="driver:route:beta",
            trace_event_id="trace:feedback:beta",
            step=1,
        ),
    ]


def layer_proposals(target: str) -> list[LayerProposal]:
    return [
        LayerProposal(
            "learned",
            "layer:learned",
            target,
            "candidate:alpha",
            "support",
            0.9,
            support=1.5,
            evidence_id="evidence:learned",
            provenance="runtime:learned",
            trace_event_id="trace:layer:learned",
        ),
        LayerProposal(
            "metacognitive",
            "layer:metacognitive",
            target,
            "candidate:alpha",
            "confirm_trace_coverage",
            0.8,
            support=0.2,
            evidence_id="evidence:metacognitive",
            provenance="runtime:metacognitive",
            trace_event_id="trace:layer:metacognitive",
        ),
    ]


def hybrid_trace_identity_inputs(
    target: str,
    *,
    collided_surfaces: set[str],
):
    shared_trace_id = "trace:hybrid-input:collision"
    trace_ids = {
        surface: (
            shared_trace_id
            if surface in collided_surfaces
            else f"trace:hybrid-input:{surface}"
        )
        for surface in HYBRID_TRACE_ID_SURFACES
    }
    scout_id = "scout:hybrid-input"
    scout = ScoutReport(
        scout_id=scout_id,
        candidate_id="candidate:alpha",
        evidence_id="evidence:hybrid-input:scout",
        provenance="driver:hybrid-input:scout",
        target=target,
        trace_event_id=trace_ids["scout_source"],
        verification=verify_signal_input(
            target=target,
            source_id=scout_id,
            subject_id="candidate:alpha",
            verifier_id="governance:hybrid-input",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="governance:hybrid-input-verification",
            trace_event_id=trace_ids["scout_verification"],
        ),
    )
    deposit = replace(
        route_trail(
            "candidate:alpha",
            "route:alpha",
            target,
            "positive",
            1.0,
            "source:hybrid-input:deposit",
        ),
        trace_event_id=trace_ids["deposit"],
    )
    feedback_item = replace(
        feedback(target)[0],
        source_id="source:hybrid-input:feedback",
        trace_event_id=trace_ids["feedback"],
    )
    adjustment = PolicyAdjustmentProposal(
        layer_id="evolutionary",
        source_id="layer:hybrid-input:adjustment",
        adjustments={"pheromone_positive_weight": 1.1},
        provenance="runtime:hybrid-input:adjustment",
        trace_event_id=trace_ids["adjustment"],
    )
    layer_proposal = LayerProposal(
        "learned",
        "layer:hybrid-input:proposal",
        target,
        "candidate:alpha",
        "support",
        0.9,
        support=1.0,
        evidence_id="evidence:hybrid-input:proposal",
        provenance="runtime:hybrid-input:proposal",
        trace_event_id=trace_ids["layer_proposal"],
    )
    strategy_bias = StrategyBias(
        layer_id="evolutionary",
        candidate_id="candidate:alpha",
        support=0.25,
        provenance="runtime:hybrid-input:bias",
        trace_event_id=trace_ids["strategy_bias"],
        target=target,
        source_id="layer:hybrid-input:bias",
        confidence=0.8,
        evidence_id="evidence:hybrid-input:bias",
    )
    return {
        "scout": scout,
        "deposit": deposit,
        "feedback": feedback_item,
        "adjustment": adjustment,
        "layer_proposal": layer_proposal,
        "strategy_bias": strategy_bias,
    }


def evaluate_hybrid_trace_identity_step(manifest, inputs):
    protocol = manifest.protocol
    policy = protocol.collective_decision_policy
    target = protocol.quorum_policy.target
    assert policy is not None
    candidates = CandidateSet(
        [
            Candidate(item.id, item.target, item.safe_fallback)
            for item in protocol.candidates
        ]
    )
    return evaluate_hybrid_collective_step(
        protocol_id=protocol.id,
        candidate_set=candidates,
        policy=policy,
        target=target,
        current_step=1,
        scout_reports=[inputs["scout"]],
        deposits=[inputs["deposit"]],
        topology=topology(target),
        feedback=[inputs["feedback"]],
        layer_proposals=[inputs["layer_proposal"]],
        strategy_biases=[inputs["strategy_bias"]],
        adjustment_proposals=[inputs["adjustment"]],
        fallback_candidate_id=collective_fallback_id(protocol),
    )


def issued_authority_step():
    manifest = load_capability_manifest("examples/hybrid-pheromone-protocol/capability.json")
    protocol = manifest.protocol
    policy = protocol.collective_decision_policy
    target = protocol.quorum_policy.target
    assert policy is not None
    candidates = CandidateSet(
        [Candidate(item.id, item.target, item.safe_fallback) for item in protocol.candidates]
    )
    step = evaluate_hybrid_collective_step(
        protocol_id=protocol.id,
        candidate_set=candidates,
        policy=policy,
        target=target,
        current_step=1,
        scout_reports=[
            verified_scout("scout:authority:a", "candidate:alpha", target),
            verified_scout("scout:authority:b", "candidate:alpha", target),
        ],
        deposits=deposits(target),
        topology=topology(target),
        feedback=feedback(target),
        layer_proposals=layer_proposals(target),
        adjustment_proposals=[
            PolicyAdjustmentProposal(
                layer_id="evolutionary",
                source_id="layer:evolutionary:authority",
                adjustments={"pheromone_positive_weight": 1.1},
                provenance="runtime:evolutionary:authority",
                trace_event_id="trace:adjustment:authority",
            )
        ],
        fallback_candidate_id=collective_fallback_id(protocol),
    )
    return protocol, candidates, policy, target, step


def substituted_receipts(receipts):
    changed = dict(receipts)
    trace_event_id = next(iter(changed))
    changed[trace_event_id] = (*changed[trace_event_id], "forged-payload")
    return MappingProxyType(changed)


def insert_cross_lifecycle_receipt_collision(
    authority_record,
    left_field: str,
    right_field: str,
) -> None:
    left_receipts = getattr(authority_record, left_field)
    right_receipts = dict(getattr(authority_record, right_field))
    trace_event_id = next(iter(left_receipts))
    assert trace_event_id not in right_receipts
    right_receipts[trace_event_id] = tuple(left_receipts[trace_event_id])
    object.__setattr__(
        authority_record,
        right_field,
        MappingProxyType(right_receipts),
    )


def tampered_step_field(step, field_name: str):
    if field_name == "decision":
        return replace(step.decision, target="decision:forged")
    if field_name == "state":
        scores = dict(step.state.scores)
        candidate_id = next(iter(scores))
        scores[candidate_id] += 0.125
        return replace(step.state, scores=scores)
    if field_name == "active_trails":
        return (
            replace(step.active_trails[0], strength=step.active_trails[0].strength + 0.125),
            *step.active_trails[1:],
        )
    if field_name == "layer_coordination":
        return replace(step.layer_coordination, resolution="caller_rewrote_resolution")
    if field_name == "adjustment_overlay":
        return RunScopedPolicyOverlay(
            {"pheromone_positive_weight": 1.2},
            source_ids=step.adjustment_overlay.source_ids,
            trace_event_ids=step.adjustment_overlay.trace_event_ids,
        )
    if field_name == "effective_policy":
        return replace(
            step.effective_policy,
            quorum_threshold=step.effective_policy.quorum_threshold + 1,
        )
    if field_name in {
        "deposit_records",
        "diffusion_records",
        "reinforcement_records",
    }:
        return getattr(step, field_name)[:-1]
    if field_name == "evaporation_records":
        return (step.deposit_records[0],)
    if field_name == "exploration_observations":
        return (
            PheromoneExplorationObservation(
                target=step.decision.target,
                candidate_id="candidate:alpha",
                subject_type="route",
                subject_id="route:alpha",
                novelty_pressure=0.25,
                reopen_eligible=True,
                reason="caller inserted observation",
                trace_event_id="trace:observation:forged",
            ),
        )
    if field_name in {
        "processed_pheromone_event_ids",
        "processed_feedback_ids",
        "processed_adjustment_ids",
    }:
        return frozenset({*getattr(step, field_name), f"trace:forged:{field_name}"})
    if field_name in {
        "deposit_replay_receipts",
        "diffusion_replay_receipts",
        "feedback_replay_receipts",
        "adjustment_replay_receipts",
    }:
        return substituted_receipts(getattr(step, field_name))
    if field_name == "budget_state":
        assert step.budget_state is not None
        return replace(step.budget_state, round_used=step.budget_state.round_used + 0.125)
    if field_name == "trace_events":
        return (
            replace(step.trace_events[0], protocol_id="protocol:forged"),
            *step.trace_events[1:],
        )
    raise AssertionError(f"unhandled HybridCollectiveStep field: {field_name}")


def tampered_replay_field(replay_state: HybridReplayState, field_name: str):
    if field_name == "protocol_id":
        return "protocol:forged"
    if field_name == "target":
        return "decision:forged"
    if field_name == "active_trails":
        return (
            replace(
                replay_state.active_trails[0],
                strength=replay_state.active_trails[0].strength + 0.125,
            ),
            *replay_state.active_trails[1:],
        )
    if field_name in {
        "processed_pheromone_event_ids",
        "processed_feedback_ids",
        "processed_adjustment_ids",
    }:
        return frozenset(
            {*getattr(replay_state, field_name), f"trace:forged:{field_name}"}
        )
    if field_name in {
        "deposit_replay_receipts",
        "diffusion_replay_receipts",
        "feedback_replay_receipts",
        "adjustment_replay_receipts",
    }:
        return substituted_receipts(getattr(replay_state, field_name))
    raise AssertionError(f"unhandled HybridReplayState field: {field_name}")
