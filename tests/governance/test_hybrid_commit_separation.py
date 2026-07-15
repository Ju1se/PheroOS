from __future__ import annotations

from dataclasses import replace
from itertools import count

import pytest

import pheroos.governance.collective as collective_module
from pheroos.governance.attention import (
    AttentionBreakdown,
    attention_breakdown_fingerprint,
    attention_breakdown_is_authoritative,
    derive_attention_breakdown,
    evaluate_hybrid_attention_step,
    exploration_directive_is_authoritative,
)
from pheroos.governance.candidate import Candidate, CandidateSet
from pheroos.governance.collective import (
    evaluate_hybrid_collective_step,
    hybrid_collective_step_is_authoritative,
    hybrid_replay_state_is_authoritative,
    replay_state_from_hybrid_step,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.hybrid_commit import (
    bind_hybrid_commit_channels,
    hybrid_attention_projection,
    hybrid_commit_step_is_authoritative,
    hybrid_commit_truth_projection,
)
from pheroos.governance.layer_coordination import LayerPerformanceSnapshot
from pheroos.protocol import load_capability_manifest
import tests.governance.test_commit_engine as commit_engine_fixture
from tests.swarm.test_hybrid_pheromone_vertical_slice import (
    deposits,
    feedback,
    layer_proposals,
    topology,
    verified_inhibition,
    verified_recruitment,
    verified_scout,
)


# Pytest can import the source fixture module under a second collection name.
# Give this module a disjoint deterministic run-id range so the governance
# authority registries never confuse two independently built test runs.
commit_engine_fixture._SEQUENCE = count(100_000)
_assess = commit_engine_fixture._assess
_scenario = commit_engine_fixture._scenario


def _hybrid_inputs(scenario) -> dict:
    template = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = replace(
        template.protocol.collective_decision_policy,
        fallback_candidate="candidate:fallback",
    )
    candidates = CandidateSet(
        [
            Candidate(item.id, item.target, item.safe_fallback)
            for item in scenario.manifest.protocol.candidates
        ]
    )
    target = scenario.context.target
    return {
        "protocol_id": scenario.manifest.protocol.id,
        "candidate_set": candidates,
        "policy": policy,
        "target": target,
        "current_step": scenario.context.issued_at_step,
        "scout_reports": [
            verified_scout("attention-scout:a", "candidate:alpha", target),
        ],
        "recruitment_signals": [
            verified_recruitment(
                "attention-recruit:a",
                "candidate:alpha",
                target,
                1.0,
            )
        ],
        "inhibition_signals": [
            verified_inhibition(
                "attention-inhibit:b",
                "candidate:beta",
                target,
                0.5,
            )
        ],
        "deposits": deposits(target),
        "topology": topology(target),
        "feedback": [
            replace(item, step=scenario.context.issued_at_step)
            for item in feedback(target)
        ],
        "layer_proposals": layer_proposals(target),
        "fallback_candidate_id": "candidate:fallback",
    }


def _bound_step(scenario, inputs: dict):
    attention, directive = evaluate_hybrid_attention_step(**inputs)
    assessment = _assess(scenario)
    return bind_hybrid_commit_channels(
        attention=attention,
        exploration_directive=directive,
        commit_assessment=assessment,
    )


def _mutate_kind(inputs: dict) -> dict:
    values = dict(inputs)
    values["deposits"] = [
        replace(inputs["deposits"][0], kind="novelty"),
        *inputs["deposits"][1:],
    ]
    return values


def _mutate_strength(inputs: dict) -> dict:
    values = dict(inputs)
    values["deposits"] = [
        replace(inputs["deposits"][0], strength=0.2),
        *inputs["deposits"][1:],
    ]
    return values


def _mutate_diffusion(inputs: dict) -> dict:
    values = dict(inputs)
    values["policy"] = replace(
        inputs["policy"],
        pheromone_diffusion_attenuation=0.25,
    )
    return values


def _mutate_feedback(inputs: dict) -> dict:
    values = dict(inputs)
    values["feedback"] = [
        replace(inputs["feedback"][0], reward=0.25, strength_delta=0.25),
        *inputs["feedback"][1:],
    ]
    return values


def _mutate_recruitment(inputs: dict) -> dict:
    values = dict(inputs)
    values["recruitment_signals"] = [
        replace(inputs["recruitment_signals"][0], strength=0.1)
    ]
    return values


def _mutate_inhibition(inputs: dict) -> dict:
    values = dict(inputs)
    values["inhibition_signals"] = [
        replace(inputs["inhibition_signals"][0], strength=0.1)
    ]
    return values


def _mutate_layer_proposal(inputs: dict) -> dict:
    values = dict(inputs)
    values["layer_proposals"] = [
        replace(inputs["layer_proposals"][0], support=0.25),
        *inputs["layer_proposals"][1:],
    ]
    return values


def _mutate_coordination(inputs: dict) -> dict:
    values = dict(inputs)
    values["performance_snapshots"] = [
        LayerPerformanceSnapshot(
            "learned",
            recent_success_rate=0.2,
            recent_conflict_rate=0.7,
            recent_fallback_rate=0.4,
            mean_confidence=0.3,
            evidence_coverage=0.5,
            trace_coverage=0.6,
        )
    ]
    return values


def _mutate_exploration(inputs: dict) -> dict:
    values = dict(inputs)
    values["policy"] = replace(
        inputs["policy"],
        novelty_decay_rate=0.2,
        exploration_floor=0.3,
        pheromone_exploration_floor=0.3,
    )
    return values


ATTENTION_MUTATIONS = (
    ("pheromone_kind", _mutate_kind),
    ("pheromone_strength", _mutate_strength),
    ("diffusion", _mutate_diffusion),
    ("feedback", _mutate_feedback),
    ("recruitment", _mutate_recruitment),
    ("inhibition", _mutate_inhibition),
    ("layer_proposal", _mutate_layer_proposal),
    ("coordination", _mutate_coordination),
    ("exploration", _mutate_exploration),
)


@pytest.mark.parametrize(("mutation_name", "mutate"), ATTENTION_MUTATIONS)
def test_full_attention_mutation_matrix_has_zero_commit_sensitivity(
    mutation_name: str,
    mutate,
) -> None:
    del mutation_name
    scenario = _scenario()
    inputs = _hybrid_inputs(scenario)
    assessment = _assess(scenario)
    base_attention, base_directive = evaluate_hybrid_attention_step(**inputs)
    changed_attention, changed_directive = evaluate_hybrid_attention_step(
        **mutate(inputs)
    )
    base = bind_hybrid_commit_channels(
        attention=base_attention,
        exploration_directive=base_directive,
        commit_assessment=assessment,
    )
    changed = bind_hybrid_commit_channels(
        attention=changed_attention,
        exploration_directive=changed_directive,
        commit_assessment=assessment,
    )

    # Status, leader, metrics, evidence/challenge/lease roots, context and the
    # assessment truth root are a pure projection of CommitAssessment.
    assert hybrid_commit_truth_projection(changed) == hybrid_commit_truth_projection(
        base
    )
    assert changed.commit_assessment is assessment
    assert base.commit_assessment is assessment
    assert changed.attention_fingerprint != base.attention_fingerprint
    assert hybrid_attention_projection(changed) != hybrid_attention_projection(base)
    assert changed.composition_root != base.composition_root
    assert hybrid_commit_step_is_authoritative(base)
    assert hybrid_commit_step_is_authoritative(changed)


def test_attention_ranking_can_change_without_changing_commit_leader_or_roots() -> None:
    scenario = _scenario()
    inputs = _hybrid_inputs(scenario)
    assessment = _assess(scenario)
    base_attention, base_directive = evaluate_hybrid_attention_step(**inputs)
    changed_inputs = dict(inputs)
    changed_inputs["scout_reports"] = [
        verified_scout(
            "attention-scout:beta:a",
            "candidate:beta",
            scenario.context.target,
        ),
        verified_scout(
            "attention-scout:beta:b",
            "candidate:beta",
            scenario.context.target,
        ),
    ]
    changed_inputs["recruitment_signals"] = [
        verified_recruitment(
            "attention-recruit:beta",
            "candidate:beta",
            scenario.context.target,
            2.0,
        )
    ]
    changed_inputs["inhibition_signals"] = [
        verified_inhibition(
            "attention-inhibit:alpha",
            "candidate:alpha",
            scenario.context.target,
            2.0,
        )
    ]
    changed_inputs["layer_proposals"] = [
        replace(item, candidate_id="candidate:beta")
        for item in inputs["layer_proposals"]
    ]
    changed_attention, changed_directive = evaluate_hybrid_attention_step(
        **changed_inputs
    )
    base = bind_hybrid_commit_channels(
        attention=base_attention,
        exploration_directive=base_directive,
        commit_assessment=assessment,
    )
    changed = bind_hybrid_commit_channels(
        attention=changed_attention,
        exploration_directive=changed_directive,
        commit_assessment=assessment,
    )

    assert base_directive.candidate_order[0] == "candidate:alpha"
    assert changed_directive.candidate_order[0] == "candidate:beta"
    assert hybrid_commit_truth_projection(changed) == hybrid_commit_truth_projection(
        base
    )
    assert changed.leader_candidate_id == "candidate:alpha"


def test_active_attention_path_never_invokes_legacy_collective_decider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = _scenario()

    def forbidden(*args, **kwargs):
        del args, kwargs
        raise AssertionError("legacy _decide_collective_state was invoked")

    monkeypatch.setattr(collective_module, "_decide_collective_state", forbidden)
    attention, directive = evaluate_hybrid_attention_step(
        **_hybrid_inputs(scenario)
    )

    assert attention_breakdown_is_authoritative(attention)
    assert exploration_directive_is_authoritative(directive, attention=attention)
    assert attention.source_step.decision.committed is False
    assert attention.source_step.decision.reason == "attention_only_no_commit_authority"
    assert {
        event.event_type for event in attention.source_step.trace_events
    }.isdisjoint({"consensus_check", "commit", "fallback"})


def test_attention_reuses_one_authoritative_hybrid_memory_and_replay_lineage() -> None:
    scenario = _scenario()
    attention, directive = evaluate_hybrid_attention_step(
        **_hybrid_inputs(scenario)
    )
    expected_replay = replay_state_from_hybrid_step(attention.source_step)

    assert hybrid_collective_step_is_authoritative(attention.source_step)
    assert hybrid_replay_state_is_authoritative(attention.replay_state)
    assert attention.replay_state.active_trails == attention.source_step.active_trails
    assert expected_replay.active_trails == attention.replay_state.active_trails
    assert expected_replay.processed_pheromone_event_ids == (
        attention.replay_state.processed_pheromone_event_ids
    )
    assert attention.memory_root != attention.replay_root
    assert attention.memory_root != attention.trace_root
    assert attention.replay_root != attention.trace_root
    assert directive.authority_scope == "none"
    assert directive.commit_authority is False


def test_legacy_hybrid_default_result_is_unchanged_and_not_accepted_as_attention() -> None:
    scenario = _scenario()
    inputs = _hybrid_inputs(scenario)
    default_step = evaluate_hybrid_collective_step(**inputs)
    explicit_legacy_step = evaluate_hybrid_collective_step(
        **inputs,
        attention_only=False,
    )

    assert default_step == explicit_legacy_step
    assert default_step.decision.committed is True
    assert default_step.decision.reason in {
        "collective_consensus",
        "safe_collective_fallback",
        "safe_layer_coordination_fallback",
    }
    with pytest.raises(GovernanceError, match="legacy Hybrid decision path"):
        derive_attention_breakdown(default_step)


def test_attention_adapter_cannot_be_downgraded_to_legacy_mode() -> None:
    scenario = _scenario()
    with pytest.raises(GovernanceError, match="cannot be overridden"):
        evaluate_hybrid_attention_step(
            **_hybrid_inputs(scenario),
            attention_only=False,
        )


def test_forged_or_tampered_attention_and_assessment_are_rejected() -> None:
    scenario = _scenario()
    assessment = _assess(scenario)
    attention, directive = evaluate_hybrid_attention_step(
        **_hybrid_inputs(scenario)
    )
    forged_attention = replace(
        attention,
        attention_root="sha256:" + "f" * 64,
    )
    assert isinstance(forged_attention, AttentionBreakdown)
    assert not attention_breakdown_is_authoritative(forged_attention)
    with pytest.raises(GovernanceError, match="attention breakdown"):
        bind_hybrid_commit_channels(
            attention=forged_attention,
            exploration_directive=directive,
            commit_assessment=assessment,
        )

    attention, directive = evaluate_hybrid_attention_step(
        **_hybrid_inputs(scenario)
    )
    object.__setattr__(assessment, "leader_margin", assessment.leader_margin + 1)
    with pytest.raises(GovernanceError, match="CommitAssessment"):
        bind_hybrid_commit_channels(
            attention=attention,
            exploration_directive=directive,
            commit_assessment=assessment,
        )


def test_hybrid_commit_wrapper_tamper_invalidates_issuance() -> None:
    scenario = _scenario()
    step = _bound_step(scenario, _hybrid_inputs(scenario))
    object.__setattr__(step, "attention_trace_root", "sha256:" + "f" * 64)

    assert not hybrid_commit_step_is_authoritative(step)


def test_commit_truth_root_never_contains_or_aliases_attention_roots() -> None:
    scenario = _scenario()
    step = _bound_step(scenario, _hybrid_inputs(scenario))
    attention_roots = {
        step.attention_fingerprint,
        step.exploration_directive_fingerprint,
        step.attention_memory_root,
        step.attention_replay_root,
        step.attention_trace_root,
        step.attention_source_step_root,
        step.composition_root,
    }

    assert step.commit_truth_root == step.commit_assessment_fingerprint
    assert step.commit_truth_root not in attention_roots
    assert step.commit_metrics_root not in attention_roots
    assert all("attention" not in key for key in hybrid_commit_truth_projection(step))
    attention_projection = hybrid_attention_projection(step)
    assert attention_projection["attention_commit_authority"] is False
    assert "commit_truth_root" not in attention_projection
    assert "commit_metrics_root" not in attention_projection
    assert attention_breakdown_fingerprint(step.attention) == step.attention_fingerprint
