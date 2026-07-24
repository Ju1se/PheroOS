from copy import deepcopy
from dataclasses import replace

import pytest

from pheroos.conformance import run_conformance, validate_manifest
from pheroos.conformance.checks import (
    hybrid_trace_contract,
    pheromone_behavior,
    pheromone_policy,
    swarm_trace_contract,
)
from pheroos.governance import (
    PheromoneNeighborhood,
    PheromoneSubject,
    PheromoneTrail,
    evaluate_hybrid_collective_step,
    replay_state_from_hybrid_step,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol import (
    CollectiveDecisionPolicy,
    TracePolicy,
    load_capability_manifest,
    validate_capability_manifest,
)
from pheroos.protocol.models import collective_fallback_id
from pheroos.trace import TraceEvent, pheromone_clip_payload_fingerprint


def test_swarm_protocol_validate_and_conformance_pass() -> None:
    validation = validate_manifest("examples/swarm-protocol/capability.json")
    conformance = run_conformance("examples/swarm-protocol")

    assert validation.ok is True
    assert conformance.ok is True
    assert conformance.profile == "pheroos-swarm-v1"
    assert {check.name for check in conformance.checks} >= {
        "collective_policy",
        "safe_fallback_collective",
        "pheromone_behavior",
        "pheromone_policy",
        "kernel_contract",
        "swarm_trace_contract",
    }


def test_hybrid_pheromone_protocol_validate_and_conformance_pass() -> None:
    validation = validate_manifest("examples/hybrid-pheromone-protocol/capability.json")
    conformance = run_conformance("examples/hybrid-pheromone-protocol")

    assert validation.ok is True
    assert conformance.ok is True
    assert conformance.profile == "pheroos-hybrid-swarm-v1"
    assert {check.name for check in conformance.checks} >= {
        "pheromone_subject_scoring",
        "pheromone_kind_profile",
        "pheromone_diffusion",
        "pheromone_reinforcement",
        "pheromone_response_model",
        "layer_coordination_policy",
        "policy_adjustment_bounds",
        "hybrid_trace_contract",
        "hybrid_authority_boundary",
    }


def test_hybrid_trace_replay_requires_matching_governance_issued_prior_state() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    first, _ = hybrid_trace_contract.manifest_replay(manifest)
    replay_state = replay_state_from_hybrid_step(first)
    second, output_event = hybrid_trace_contract.manifest_replay(
        manifest,
        replay_state=replay_state,
    )
    events = [*second.trace_events, output_event]

    valid = hybrid_trace_contract.check_actual_trace(
        manifest,
        events,
        decision=second.decision,
        replay_state=replay_state,
    )
    missing_state = hybrid_trace_contract.check_actual_trace(
        manifest,
        events,
        decision=second.decision,
    )
    wrong_step, _ = hybrid_trace_contract.manifest_replay(
        manifest,
        force_fallback=True,
        lifecycle_focus="reinforcement",
    )
    wrong_state = hybrid_trace_contract.check_actual_trace(
        manifest,
        events,
        decision=second.decision,
        replay_state=replay_state_from_hybrid_step(wrong_step),
    )
    lookalike_state = replace(replay_state)
    lookalike = hybrid_trace_contract.check_actual_trace(
        manifest,
        events,
        decision=second.decision,
        replay_state=lookalike_state,
    )
    tampered_state = replay_state_from_hybrid_step(first)
    tampered_receipts = dict(tampered_state.adjustment_replay_receipts)
    receipt_id = next(iter(tampered_receipts))
    tampered_receipts[receipt_id] = (
        *tampered_receipts[receipt_id],
        "caller-forged-receipt",
    )
    object.__setattr__(
        tampered_state,
        "adjustment_replay_receipts",
        tampered_receipts,
    )
    tampered = hybrid_trace_contract.check_actual_trace(
        manifest,
        events,
        decision=second.decision,
        replay_state=tampered_state,
    )

    assert valid.ok is True, valid.detail
    assert missing_state.ok is False
    assert "authority_replay_receipt_not_in_state" in missing_state.detail
    assert wrong_state.ok is False
    assert "authority_replay_receipt_not_in_state" in wrong_state.detail
    assert lookalike.ok is False
    assert "authority_replay_state_not_issued" in lookalike.detail
    assert tampered.ok is False
    assert "authority_replay_state_not_issued" in tampered.detail


def test_hybrid_trace_rejects_coordinated_phantom_replay_event_and_score_anchor() -> (
    None
):
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    events = [*step.trace_events, output_event]
    accepted = next(
        event
        for event in events
        if event.event_type == "policy_adjustment"
        and event.lineage.get("result") == "accepted"
    )
    phantom_id = "trace:adjustment:phantom-replay"
    proposed_values = dict(accepted.lineage["proposed_values"])
    receipt = (
        "adjustment-v1",
        accepted.lineage["layer_id"],
        accepted.lineage["source_id"],
        tuple(sorted(proposed_values.items())),
        accepted.lineage["provenance"],
        phantom_id,
    )
    fingerprint = pheromone_clip_payload_fingerprint(
        {"lifecycle": "replay_receipt", "receipt": receipt}
    )
    phantom = replace(
        accepted,
        reason="forged replay claim with a coordinated score anchor",
        lineage={
            **dict(accepted.lineage),
            "result": "replay_ignored",
            "source_trace_event_id": phantom_id,
            "replayed": True,
            "replay_payload": list(receipt),
            "replay_payload_fingerprint": fingerprint,
            "processed_payload_fingerprint": fingerprint,
        },
    )
    insert_at = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "layer_proposal"
    )
    events.insert(insert_at, phantom)
    score_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "pheromone_score"
    )
    score_lineage = deepcopy(dict(events[score_index].lineage))
    score_lineage["processed_replay_receipts"]["adjustment"][phantom_id] = fingerprint
    events[score_index] = replace(events[score_index], lineage=score_lineage)

    result = hybrid_trace_contract.check_actual_trace(manifest, events)

    assert result.ok is False
    assert "authority_replay_receipt_not_in_state:adjustment" in result.detail


def test_hybrid_trace_rejects_replay_payload_and_anchor_mutated_together() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    first, _ = hybrid_trace_contract.manifest_replay(manifest)
    replay_state = replay_state_from_hybrid_step(first)
    second, output_event = hybrid_trace_contract.manifest_replay(
        manifest,
        replay_state=replay_state,
    )
    events = [*second.trace_events, output_event]
    replay_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "pheromone_observe"
        and event.lineage.get("lifecycle") == "deposit"
    )
    lineage = deepcopy(dict(events[replay_index].lineage))
    payload = list(lineage["replay_payload"])
    payload[2] = float(payload[2]) + 0.125
    fingerprint = pheromone_clip_payload_fingerprint(
        {"lifecycle": "replay_receipt", "receipt": payload}
    )
    lineage.update(
        replay_payload=payload,
        replay_payload_fingerprint=fingerprint,
        processed_payload_fingerprint=fingerprint,
    )
    events[replay_index] = replace(events[replay_index], lineage=lineage)
    score_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "pheromone_score"
    )
    score_lineage = deepcopy(dict(events[score_index].lineage))
    trace_event_id = lineage["source_trace_event_id"]
    score_lineage["processed_replay_receipts"]["deposit"][trace_event_id] = fingerprint
    events[score_index] = replace(events[score_index], lineage=score_lineage)

    result = hybrid_trace_contract.check_actual_trace(
        manifest,
        events,
        replay_state=replay_state,
    )

    assert result.ok is False
    assert "authority_replay_payload_state_mismatch:deposit" in result.detail


def test_swarm_trace_contract_skips_quorum_collective_mode() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    protocol = replace(
        manifest.protocol,
        collective_decision_policy=CollectiveDecisionPolicy(
            mode="quorum",
            fallback_candidate="candidate:safe_fallback",
        ),
        trace_policy=TracePolicy(
            required_events=["block", "commit", "recovery", "output"]
        ),
    )

    result = swarm_trace_contract.check(replace(manifest, protocol=protocol))

    assert result.ok is True


def test_hybrid_trace_contract_reports_missing_hybrid_events() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    protocol = replace(
        manifest.protocol,
        trace_policy=TracePolicy(
            required_events=["block", "commit", "recovery", "output"]
        ),
    )

    result = hybrid_trace_contract.check(replace(manifest, protocol=protocol))

    assert result.ok is False
    assert "pheromone_diffuse" in result.detail
    assert "coordination_resolve" in result.detail


def test_hybrid_trace_coverage_requires_real_positive_reinforcement() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    observed = set(manifest.protocol.trace_policy.required_events)
    no_change = TraceEvent(
        "pheromone_reinforce",
        manifest.protocol.id,
        manifest.protocol.quorum_policy.target,
        "feedback observed without state change",
        {
            "delta": 0.0,
            "old_strength": 1.0,
            "new_strength": 1.0,
        },
    )

    problems = hybrid_trace_contract.actual_trace_coverage_problems(
        policy,
        observed,
        events=[no_change],
    )

    assert "actual_event_missing:pheromone_reinforce_state_change" in problems
    reinforced = replace(
        no_change,
        lineage={"delta": 0.25, "old_strength": 1.0, "new_strength": 1.25},
    )
    assert (
        hybrid_trace_contract.actual_trace_coverage_problems(
            policy,
            observed,
            events=[reinforced],
        )
        == []
    )


def test_hybrid_trace_contract_validates_actual_decision_lineage() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(
        manifest, force_fallback=True
    )
    events = [*step.trace_events, output_event]

    result = hybrid_trace_contract.check_actual_trace(
        manifest, events, decision=step.decision
    )

    assert result.ok is True, result.detail


def test_hybrid_trace_contract_rejects_zeroed_score_and_diversity_with_commit() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    events = [*step.trace_events, output_event]
    score_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "candidate_score"
    )
    lineage = dict(events[score_index].lineage)
    lineage["scores"] = {candidate_id: 0.0 for candidate_id in lineage["scores"]}
    lineage["score_breakdown"] = {
        candidate_id: {category: 0.0 for category in categories}
        for candidate_id, categories in lineage["score_breakdown"].items()
    }
    lineage["scout_diversity"] = {
        candidate_id: 0 for candidate_id in lineage["scout_diversity"]
    }
    lineage["pheromone_source_diversity"] = {
        candidate_id: 0 for candidate_id in lineage["pheromone_source_diversity"]
    }
    events[score_index] = replace(events[score_index], lineage=lineage)

    result = hybrid_trace_contract.check_actual_trace(
        manifest,
        events,
        decision=step.decision,
    )

    assert result.ok is False
    assert "authority_scout_diversity:candidate:alpha" in result.detail
    assert "authority_scout_score:candidate:alpha" in result.detail
    assert "authority_commit_without_consensus" in result.detail


def test_hybrid_trace_contract_rejects_forward_layer_deposit_lineage() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    events = [*step.trace_events, output_event]
    proposal_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "layer_proposal"
    )
    deposit_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "pheromone_deposit"
    )
    deposit = events[deposit_index]
    proposal_lineage = dict(events[proposal_index].lineage)
    proposal_lineage.update(
        {
            "source_id": deposit.lineage["source_id"],
            "action": "propose_pheromone",
            "effect": "bounded_pheromone_deposit_proposed",
            "candidate_id": deposit.lineage["candidate_id"],
            "confidence": 1.0,
            "proposed_strength": (
                deposit.lineage["new_strength"] - deposit.lineage["old_strength"]
            ),
            "proposed_pheromone_kind": deposit.lineage["kind"],
            "subject_type": deposit.lineage["subject_type"],
            "subject_id": deposit.lineage["subject_id"],
            "source_trace_event_id": deposit.lineage["source_trace_event_id"],
        }
    )
    proposal = replace(events[proposal_index], lineage=proposal_lineage)
    del events[proposal_index]
    deposit_index = next(
        index for index, event in enumerate(events) if event is deposit
    )
    events.insert(deposit_index + 1, proposal)

    result = hybrid_trace_contract.check_actual_trace(manifest, events)

    assert result.ok is False
    assert "authority_layer_pheromone_forward_reference" in result.detail


def test_hybrid_trace_contract_rejects_manifest_threshold_and_commit_lineage_tampering() -> (
    None
):
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    original = [*step.trace_events, output_event]

    threshold_events = list(original)
    consensus_index = next(
        index
        for index, event in enumerate(threshold_events)
        if event.event_type == "consensus_check"
    )
    consensus_lineage = dict(threshold_events[consensus_index].lineage)
    consensus_lineage["quorum_threshold"] += 1
    threshold_events[consensus_index] = replace(
        threshold_events[consensus_index],
        lineage=consensus_lineage,
    )
    threshold_result = hybrid_trace_contract.check_actual_trace(
        manifest, threshold_events
    )

    lineage_events = list(original)
    commit_index = next(
        index
        for index, event in enumerate(lineage_events)
        if event.event_type == "commit"
    )
    commit_lineage = dict(lineage_events[commit_index].lineage)
    commit_lineage["upstream_score_lineage"] = ["candidate_score"]
    lineage_events[commit_index] = replace(
        lineage_events[commit_index],
        lineage=commit_lineage,
    )
    lineage_result = hybrid_trace_contract.check_actual_trace(manifest, lineage_events)

    assert threshold_result.ok is False
    assert "authority_quorum_threshold_mismatch" in threshold_result.detail
    assert lineage_result.ok is False
    assert "authority_scout_upstream_lineage" in lineage_result.detail


def test_hybrid_trace_contract_rejects_impossible_signal_and_pheromone_bounds() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    original = [*step.trace_events, output_event]

    signal_events = list(original)
    scout_index = next(
        index
        for index, event in enumerate(signal_events)
        if event.event_type == "scout_report"
    )
    scout = dict(signal_events[scout_index].lineage)
    excess = 1e100
    delta = excess - float(scout["support"])
    scout["support"] = excess
    signal_events[scout_index] = replace(signal_events[scout_index], lineage=scout)
    score_index = next(
        index
        for index, event in enumerate(signal_events)
        if event.event_type == "candidate_score"
    )
    score = dict(signal_events[score_index].lineage)
    score["scores"] = dict(score["scores"])
    score["score_breakdown"] = {
        candidate_id: dict(categories)
        for candidate_id, categories in score["score_breakdown"].items()
    }
    candidate_id = scout["candidate_id"]
    score["score_breakdown"][candidate_id]["scout"] += delta
    score["scores"][candidate_id] += delta
    signal_events[score_index] = replace(signal_events[score_index], lineage=score)

    lifecycle_events = list(original)
    deposit_index = next(
        index
        for index, event in enumerate(lifecycle_events)
        if event.event_type == "pheromone_deposit"
    )
    deposit = dict(lifecycle_events[deposit_index].lineage)
    deposit["new_strength"] = excess
    lifecycle_events[deposit_index] = replace(
        lifecycle_events[deposit_index],
        lineage=deposit,
    )

    signal_result = hybrid_trace_contract.check_actual_trace(manifest, signal_events)
    lifecycle_result = hybrid_trace_contract.check_actual_trace(
        manifest, lifecycle_events
    )

    assert signal_result.ok is False
    assert "authority_scout_strength_bound" in signal_result.detail
    assert lifecycle_result.ok is False
    assert "authority_pheromone_deposit_new_strength_bound" in lifecycle_result.detail


def test_hybrid_trace_contract_causally_replays_every_pheromone_lifecycle() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )

    primary, primary_output = hybrid_trace_contract.manifest_replay(manifest)
    deposit_events = [*primary.trace_events, primary_output]
    deposit_index = next(
        index
        for index, event in enumerate(deposit_events)
        if event.event_type == "pheromone_deposit"
    )
    deposit = dict(deposit_events[deposit_index].lineage)
    deposit["applied_strength"] = float(deposit["applied_strength"]) / 2
    deposit["new_strength"] = float(deposit["source_strength"]) + float(
        deposit["applied_strength"]
    )
    deposit_events[deposit_index] = replace(
        deposit_events[deposit_index], lineage=deposit
    )
    deposit_result = hybrid_trace_contract.check_actual_trace(manifest, deposit_events)

    evaporation_events = [*primary.trace_events, primary_output]
    evaporation_index = next(
        index
        for index, event in enumerate(evaporation_events)
        if event.event_type == "pheromone_evaporate"
    )
    evaporation = dict(evaporation_events[evaporation_index].lineage)
    evaporation["new_strength"] = float(evaporation["new_strength"]) / 2
    evaporation["applied_strength"] = evaporation["new_strength"]
    evaporation["strength_delta"] = float(evaporation["new_strength"]) - float(
        evaporation["source_strength"]
    )
    evaporation_events[evaporation_index] = replace(
        evaporation_events[evaporation_index], lineage=evaporation
    )
    evaporation_result = hybrid_trace_contract.check_actual_trace(
        manifest, evaporation_events
    )

    expiry_events = [*primary.trace_events, primary_output]
    expiry_index = next(
        index
        for index, event in enumerate(expiry_events)
        if event.event_type == "pheromone_expire"
    )
    expiry = dict(expiry_events[expiry_index].lineage)
    expiry["new_strength"] = float(expiry["new_strength"]) + 0.1
    expiry["applied_strength"] = expiry["new_strength"]
    expiry["strength_delta"] = float(expiry["new_strength"]) - float(
        expiry["source_strength"]
    )
    expiry_events[expiry_index] = replace(expiry_events[expiry_index], lineage=expiry)
    expiry_result = hybrid_trace_contract.check_actual_trace(manifest, expiry_events)

    diffusion_step, diffusion_output = hybrid_trace_contract.manifest_replay(
        manifest,
        force_fallback=True,
        lifecycle_focus="diffusion",
    )
    diffusion_events = [*diffusion_step.trace_events, diffusion_output]
    diffusion_index = next(
        index
        for index, event in enumerate(diffusion_events)
        if event.event_type == "pheromone_diffuse"
    )
    diffusion = dict(diffusion_events[diffusion_index].lineage)
    diffusion["policy_attenuation"] = float(diffusion["policy_attenuation"]) * 0.8
    diffusion["attenuation"] = float(diffusion["policy_attenuation"]) * float(
        diffusion["edge_attenuation"]
    )
    diffusion["requested_strength"] = float(diffusion["source_strength"]) * float(
        diffusion["attenuation"]
    )
    diffusion_events[diffusion_index] = replace(
        diffusion_events[diffusion_index], lineage=diffusion
    )
    diffusion_result = hybrid_trace_contract.check_actual_trace(
        manifest, diffusion_events
    )

    reinforcement_step, reinforcement_output = hybrid_trace_contract.manifest_replay(
        manifest,
        force_fallback=True,
        lifecycle_focus="reinforcement",
    )
    reinforcement_events = [*reinforcement_step.trace_events, reinforcement_output]
    reinforcement_index = next(
        index
        for index, event in enumerate(reinforcement_events)
        if event.event_type == "pheromone_reinforce"
    )
    reinforcement = dict(reinforcement_events[reinforcement_index].lineage)
    reinforcement["requested_strength"] = float(reinforcement["requested_strength"]) / 2
    reinforcement["applied_strength"] = reinforcement["requested_strength"]
    reinforcement["delta"] = reinforcement["applied_strength"]
    reinforcement["new_strength"] = float(reinforcement["source_strength"]) + float(
        reinforcement["delta"]
    )
    reinforcement_events[reinforcement_index] = replace(
        reinforcement_events[reinforcement_index], lineage=reinforcement
    )
    reinforcement_result = hybrid_trace_contract.check_actual_trace(
        manifest, reinforcement_events
    )

    assert deposit_result.ok is False
    assert "authority_pheromone_budget_applied" in deposit_result.detail
    assert "authority_pheromone_active_transition" in deposit_result.detail
    assert evaporation_result.ok is False
    assert "authority_pheromone_evaporation_replay" in evaporation_result.detail
    assert "authority_pheromone_active_transition" in evaporation_result.detail
    assert expiry_result.ok is False
    assert "authority_pheromone_expiry_floor" in expiry_result.detail
    assert "authority_pheromone_active_transition" in expiry_result.detail
    assert diffusion_result.ok is False
    assert "authority_pheromone_diffuse_policy_attenuation" in diffusion_result.detail
    assert reinforcement_result.ok is False
    assert "authority_pheromone_active_transition" in reinforcement_result.detail


def test_hybrid_trace_contract_rejects_forged_lifecycle_budget_lineage() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    diffusion_step, diffusion_output = hybrid_trace_contract.manifest_replay(
        manifest,
        force_fallback=True,
        lifecycle_focus="diffusion",
    )
    diffusion_events = [*diffusion_step.trace_events, diffusion_output]
    diffusion_index = next(
        index
        for index, event in enumerate(diffusion_events)
        if event.event_type == "pheromone_diffuse"
    )
    diffusion = dict(diffusion_events[diffusion_index].lineage)
    diffusion["round_budget_remaining"] = float(diffusion["round_budget_remaining"]) / 2
    diffusion_events[diffusion_index] = replace(
        diffusion_events[diffusion_index], lineage=diffusion
    )

    reinforcement_step, reinforcement_output = hybrid_trace_contract.manifest_replay(
        manifest,
        force_fallback=True,
        lifecycle_focus="reinforcement",
    )
    reinforcement_events = [*reinforcement_step.trace_events, reinforcement_output]
    reinforcement_index = next(
        index
        for index, event in enumerate(reinforcement_events)
        if event.event_type == "pheromone_reinforce"
    )
    reinforcement = dict(reinforcement_events[reinforcement_index].lineage)
    reinforcement["budget_result"] = dict(reinforcement["budget_result"])
    reinforcement["budget_result"]["source_remaining"] = 0.0
    reinforcement_events[reinforcement_index] = replace(
        reinforcement_events[reinforcement_index], lineage=reinforcement
    )

    diffusion_result = hybrid_trace_contract.check_actual_trace(
        manifest, diffusion_events
    )
    reinforcement_result = hybrid_trace_contract.check_actual_trace(
        manifest, reinforcement_events
    )

    assert diffusion_result.ok is False
    assert "authority_pheromone_round_budget_lineage" in diffusion_result.detail
    assert reinforcement_result.ok is False
    assert "authority_pheromone_source_budget_lineage" in reinforcement_result.detail


def test_hybrid_trace_contract_reconstructs_normalization_from_scored_memory() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    original = [*step.trace_events, output_event]
    normalize_index = next(
        index
        for index, event in enumerate(original)
        if event.event_type == "pheromone_normalize"
    )

    mutations = (
        ("pre_scores", "authority_pheromone_normalize_pre_scores"),
        ("post_scores", "authority_pheromone_normalize_post_scores"),
        ("response_model", "authority_pheromone_normalize_response_model"),
        ("competition_mode", "authority_pheromone_normalize_competition_mode"),
    )
    for field_name, expected in mutations:
        events = list(original)
        lineage = dict(events[normalize_index].lineage)
        if field_name in {"pre_scores", "post_scores"}:
            values = dict(lineage[field_name])
            candidate_id = next(iter(values))
            values[candidate_id] = float(values[candidate_id]) + 0.25
            lineage[field_name] = values
        elif field_name == "response_model":
            lineage[field_name] = "linear"
        else:
            lineage[field_name] = "none"
        events[normalize_index] = replace(
            events[normalize_index],
            lineage=lineage,
        )

        result = hybrid_trace_contract.check_actual_trace(manifest, events)

        assert result.ok is False
        assert expected in result.detail


def test_hybrid_trace_contract_reconstructs_exploration_observations() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    original = [*step.trace_events, output_event]
    state_index = next(
        index
        for index, event in enumerate(original)
        if event.event_type == "pheromone_observe" and "candidate_id" in event.lineage
    )
    floor_index = next(
        index
        for index, event in enumerate(original)
        if event.event_type == "pheromone_observe"
        and "exploration_floor" in event.lineage
    )

    state_events = list(original)
    state_lineage = dict(state_events[state_index].lineage)
    state_lineage["reopen_eligible"] = False
    state_lineage["novelty_pressure"] = 0.25
    state_events[state_index] = replace(
        state_events[state_index],
        lineage=state_lineage,
    )
    state_result = hybrid_trace_contract.check_actual_trace(manifest, state_events)

    source_events = list(original)
    source_lineage = dict(source_events[state_index].lineage)
    source_lineage["source_trace_event_id"] = "trace:deposit:secondary"
    source_events[state_index] = replace(
        source_events[state_index],
        lineage=source_lineage,
    )
    source_result = hybrid_trace_contract.check_actual_trace(manifest, source_events)

    floor_events = list(original)
    floor_lineage = dict(floor_events[floor_index].lineage)
    floor_lineage["exploration_floor"] = 0.25
    floor_lineage["candidate_ids"] = ["candidate:beta"]
    floor_events[floor_index] = replace(
        floor_events[floor_index],
        lineage=floor_lineage,
    )
    floor_result = hybrid_trace_contract.check_actual_trace(manifest, floor_events)

    assert state_result.ok is False
    assert "authority_pheromone_observe_novelty" in state_result.detail
    assert "authority_pheromone_observe_lineage" in state_result.detail
    assert source_result.ok is False
    assert "authority_pheromone_observe_lineage" in source_result.detail
    assert floor_result.ok is False
    assert "authority_pheromone_exploration_floor_value" in floor_result.detail
    assert "authority_pheromone_exploration_floor_candidates" in floor_result.detail


def test_hybrid_trace_contract_binds_lifecycle_and_active_trail_timing() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    original = [*step.trace_events, output_event]

    deposit_events = list(original)
    deposit_index = next(
        index
        for index, event in enumerate(deposit_events)
        if event.event_type == "pheromone_deposit"
    )
    deposit = dict(deposit_events[deposit_index].lineage)
    deposit.update({"step": 0, "deposited_at_step": 0, "updated_at_step": 0})
    deposit_events[deposit_index] = replace(
        deposit_events[deposit_index],
        lineage=deposit,
    )
    deposit_result = hybrid_trace_contract.check_actual_trace(manifest, deposit_events)

    evaporation_events = list(original)
    evaporation_index = next(
        index
        for index, event in enumerate(evaporation_events)
        if event.event_type == "pheromone_evaporate"
    )
    evaporation = dict(evaporation_events[evaporation_index].lineage)
    evaporation.update({"step": 2, "source_updated_at_step": 1, "elapsed_steps": 1})
    evaporation_events[evaporation_index] = replace(
        evaporation_events[evaporation_index],
        lineage=evaporation,
    )
    evaporation_result = hybrid_trace_contract.check_actual_trace(
        manifest,
        evaporation_events,
    )

    assert deposit_result.ok is False
    assert "authority_pheromone_active_transition" in deposit_result.detail
    assert evaporation_result.ok is False
    assert "authority_pheromone_active_transition" in evaporation_result.detail


def test_hybrid_trace_contract_reconstructs_commit_and_fallback_reasons() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    cases = (
        (False, "safe_collective_fallback"),
        (True, "collective_consensus"),
    )
    for force_fallback, forged_reason in cases:
        step, output_event = hybrid_trace_contract.manifest_replay(
            manifest,
            force_fallback=force_fallback,
        )
        events = [*step.trace_events, output_event]
        decision_index = next(
            index
            for index, event in enumerate(events)
            if event.event_type in {"commit", "fallback"}
        )
        lineage = dict(events[decision_index].lineage)
        lineage["decision_reason"] = forged_reason
        events[decision_index] = replace(
            events[decision_index],
            reason=forged_reason,
            lineage=lineage,
        )

        result = hybrid_trace_contract.check_actual_trace(manifest, events)

        assert result.ok is False
        assert "authority_decision_semantic_reason" in result.detail


def test_hybrid_trace_contract_binds_rejected_diffusion_clip_lineage() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    original = [*step.trace_events, output_event]
    clip_index = next(
        index
        for index, event in enumerate(original)
        if event.event_type == "pheromone_clip"
        and event.lineage.get("lifecycle") == "diffusion"
    )
    mutations = (
        ("hop", "authority_pheromone_clip_diffusion_parent_lineage"),
        ("root_trace_event_id", "authority_pheromone_clip_diffusion_parent_lineage"),
        ("target_subject", "authority_pheromone_clip_diffusion_target_subject"),
        ("trace_event_id", "authority_pheromone_clip_diffusion_trace_lineage"),
        ("kind", "authority_pheromone_clip_diffusion_kind"),
        ("step", "authority_pheromone_clip_future_step"),
    )

    for field_name, expected in mutations:
        events = list(original)
        lineage = dict(events[clip_index].lineage)
        if field_name == "hop":
            lineage[field_name] = int(lineage[field_name]) + 1
        elif field_name == "step":
            lineage[field_name] = int(lineage[field_name]) + 1
        elif field_name == "kind":
            lineage[field_name] = "alarm"
        elif field_name == "target_subject":
            lineage[field_name] = {**lineage[field_name], "id": "candidate:forged"}
        else:
            lineage[field_name] = "trace:forged"
        events[clip_index] = replace(events[clip_index], lineage=lineage)

        result = hybrid_trace_contract.check_actual_trace(manifest, events)

        assert result.ok is False
        assert expected in result.detail


def test_rejected_diffusion_clip_receipt_binds_every_causal_input_leaf() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    original = [*step.trace_events, output_event]
    clip_index = next(
        index
        for index, event in enumerate(original)
        if event.event_type == "pheromone_clip"
        and event.lineage.get("lifecycle") == "diffusion"
    )
    payload = original[clip_index].lineage["causal_payload"]

    for path in _payload_leaf_paths(payload):
        events = list(original)
        lineage = deepcopy(dict(events[clip_index].lineage))
        _mutate_payload_path(lineage["causal_payload"], path)
        events[clip_index] = replace(events[clip_index], lineage=lineage)

        result = hybrid_trace_contract.check_actual_trace(
            manifest,
            events,
            decision=step.decision,
        )

        assert result.ok is False, path
        assert "fingerprint" in result.detail, path


@pytest.mark.parametrize("missing_field", ["causal_payload", "causal_fingerprint"])
def test_rejected_diffusion_clip_requires_both_receipt_fields(
    missing_field: str,
) -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    events = [*step.trace_events, output_event]
    clip_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "pheromone_clip"
        and event.lineage.get("lifecycle") == "diffusion"
    )
    lineage = dict(events[clip_index].lineage)
    lineage.pop(missing_field)
    events[clip_index] = replace(events[clip_index], lineage=lineage)

    result = hybrid_trace_contract.check_actual_trace(manifest, events)

    assert result.ok is False
    assert "causal_payload and causal_fingerprint" in result.detail


def test_hybrid_trace_contract_binds_raw_and_inherited_active_ttl() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    original = [*step.trace_events, output_event]
    score_index = next(
        index
        for index, event in enumerate(original)
        if event.event_type == "pheromone_score"
    )
    cases = (
        ("trace:deposit:primary", 1, "authority_pheromone_active_transition"),
        ("trace:existing:expiring", 2, "authority_pheromone_expire_ttl"),
        (
            next(
                item["trace_event_id"]
                for item in original[score_index].lineage["active_trails"]
                if str(item["trace_event_id"]).startswith("diffuse:")
            ),
            3,
            "authority_pheromone_diffuse_ttl",
        ),
    )

    for trace_id, forged_ttl, expected in cases:
        events = list(original)
        lineage = dict(events[score_index].lineage)
        lineage["active_trails"] = [
            {**item, "ttl_steps": forged_ttl}
            if item["trace_event_id"] == trace_id
            else dict(item)
            for item in lineage["active_trails"]
        ]
        events[score_index] = replace(events[score_index], lineage=lineage)

        result = hybrid_trace_contract.check_actual_trace(manifest, events)

        assert result.ok is False
        assert expected in result.detail


def test_hybrid_trace_contract_binds_adjustment_replay_and_layer_effect() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    original = [*step.trace_events, output_event]

    adjustment_events = list(original)
    adjustment_index = next(
        index
        for index, event in enumerate(adjustment_events)
        if event.event_type == "policy_adjustment"
    )
    adjustment = dict(adjustment_events[adjustment_index].lineage)
    adjustment["replayed"] = True
    adjustment_events[adjustment_index] = replace(
        adjustment_events[adjustment_index],
        lineage=adjustment,
    )

    proposal_events = list(original)
    proposal_index = next(
        index
        for index, event in enumerate(proposal_events)
        if event.event_type == "layer_proposal"
        and event.lineage.get("action") != "strategy_bias"
    )
    proposal = dict(proposal_events[proposal_index].lineage)
    proposal["effect"] = "forged_effect"
    proposal_events[proposal_index] = replace(
        proposal_events[proposal_index],
        lineage=proposal,
    )

    adjustment_result = hybrid_trace_contract.check_actual_trace(
        manifest, adjustment_events
    )
    proposal_result = hybrid_trace_contract.check_actual_trace(
        manifest, proposal_events
    )

    assert adjustment_result.ok is False
    assert "authority_policy_adjustment_replayed" in adjustment_result.detail
    assert proposal_result.ok is False
    assert "authority_layer_proposal_effect" in proposal_result.detail


def test_hybrid_trace_contract_binds_feedback_clip_outcome_and_trace_identity() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    original = [*step.trace_events, output_event]
    clip_index = next(
        index
        for index, event in enumerate(original)
        if event.event_type == "pheromone_clip"
        and event.lineage.get("lifecycle") == "feedback"
    )
    cases = (
        (
            "source_trace_event_id",
            "trace:forged",
            "authority_pheromone_clip_feedback_new_trail_lineage",
        ),
        (
            "feedback_trace_event_id",
            "trace:forged",
            "authority_pheromone_clip_feedback_lineage",
        ),
        ("trace_event_id", "trace:forged", "authority_pheromone_clip_feedback_lineage"),
        ("kind", "negative", "authority_pheromone_clip_feedback_outcome_kind"),
        ("source_kind", "negative", "authority_pheromone_clip_feedback_source_kind"),
        ("outcome", "failure", "authority_pheromone_clip_feedback_outcome_kind"),
        ("candidate_id", "candidate:forged", "authority_pheromone_clip_candidate"),
        ("subject_type", "unsupported", "authority_pheromone_clip_subject_type"),
        ("step", 2, "authority_pheromone_clip_future_step"),
    )

    for field_name, forged_value, expected in cases:
        events = list(original)
        lineage = dict(events[clip_index].lineage)
        lineage[field_name] = forged_value
        events[clip_index] = replace(events[clip_index], lineage=lineage)

        result = hybrid_trace_contract.check_actual_trace(manifest, events)

        assert result.ok is False
        assert expected in result.detail


def test_hybrid_trace_contract_allows_memory_only_feedback_clip_subject() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(
        manifest,
        memory_only_feedback=True,
    )
    events = [*step.trace_events, output_event]
    clip = next(
        event
        for event in events
        if event.event_type == "pheromone_clip"
        and event.lineage.get("lifecycle") == "feedback"
    )

    result = hybrid_trace_contract.check_actual_trace(manifest, events)

    assert result.ok is True, result.detail
    assert clip.lineage["subject_type"] == "evidence"
    assert clip.lineage["subject_id"] == "evidence:memory:primary"
    assert clip.lineage["causal_payload"]["input"]["subject_type"] == "evidence"


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    [
        ("source_id", "source:forged"),
        ("provenance", "forged:provenance"),
        ("subject_id", "route:forged"),
        ("reward", 0.125),
        ("strength_delta", 0.125),
        ("requested_strength", 0.125),
    ],
)
def test_rejected_feedback_clip_receipt_rejects_reported_single_field_mutations(
    field_name: str,
    forged_value: object,
) -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    events = [*step.trace_events, output_event]
    clip_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "pheromone_clip"
        and event.lineage.get("lifecycle") == "feedback"
    )
    lineage = dict(events[clip_index].lineage)
    lineage[field_name] = forged_value
    events[clip_index] = replace(events[clip_index], lineage=lineage)

    result = hybrid_trace_contract.check_actual_trace(
        manifest,
        events,
        decision=step.decision,
    )

    assert result.ok is False
    assert "pheromone_clip" in result.detail


def test_rejected_feedback_clip_receipt_binds_every_input_and_source_state_leaf() -> (
    None
):
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    original = [*step.trace_events, output_event]
    clip_index = next(
        index
        for index, event in enumerate(original)
        if event.event_type == "pheromone_clip"
        and event.lineage.get("lifecycle") == "feedback"
    )
    payload = original[clip_index].lineage["causal_payload"]

    for path in _payload_leaf_paths(payload):
        events = list(original)
        lineage = deepcopy(dict(events[clip_index].lineage))
        _mutate_payload_path(lineage["causal_payload"], path)
        events[clip_index] = replace(events[clip_index], lineage=lineage)

        result = hybrid_trace_contract.check_actual_trace(
            manifest,
            events,
            decision=step.decision,
        )

        assert result.ok is False, path
        assert "fingerprint" in result.detail, path


@pytest.mark.parametrize("missing_field", ["causal_payload", "causal_fingerprint"])
def test_rejected_feedback_clip_requires_both_receipt_fields(
    missing_field: str,
) -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    events = [*step.trace_events, output_event]
    clip_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "pheromone_clip"
        and event.lineage.get("lifecycle") == "feedback"
    )
    lineage = dict(events[clip_index].lineage)
    lineage.pop(missing_field)
    events[clip_index] = replace(events[clip_index], lineage=lineage)

    result = hybrid_trace_contract.check_actual_trace(manifest, events)

    assert result.ok is False
    assert "causal_payload and causal_fingerprint" in result.detail


def test_hybrid_trace_contract_binds_applied_reinforcement_semantics() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(
        manifest,
        force_fallback=True,
        lifecycle_focus="reinforcement",
    )
    original = [*step.trace_events, output_event]
    reinforcement_index = next(
        index
        for index, event in enumerate(original)
        if event.event_type == "pheromone_reinforce"
    )
    cases = (
        ("outcome", "failure", "authority_pheromone_reinforce_outcome_kind"),
        (
            "source_trace_event_id",
            "trace:forged",
            "authority_pheromone_reinforce_new_trail_lineage",
        ),
        (
            "feedback_trace_event_id",
            "trace:forged",
            "authority_pheromone_reinforce_feedback_lineage",
        ),
    )

    for field_name, forged_value, expected in cases:
        events = list(original)
        lineage = dict(events[reinforcement_index].lineage)
        lineage[field_name] = forged_value
        events[reinforcement_index] = replace(
            events[reinforcement_index],
            lineage=lineage,
        )

        result = hybrid_trace_contract.check_actual_trace(manifest, events)

        assert result.ok is False
        assert expected in result.detail

    step_events = list(original)
    score_index = next(
        index
        for index, event in enumerate(step_events)
        if event.event_type == "pheromone_score"
    )
    score = dict(step_events[score_index].lineage)
    score["current_step"] = int(score["current_step"]) + 1
    step_events[score_index] = replace(step_events[score_index], lineage=score)
    step_result = hybrid_trace_contract.check_actual_trace(manifest, step_events)

    assert step_result.ok is False
    assert "authority_pheromone_active_current_step" in step_result.detail


def test_hybrid_trace_contract_binds_shared_deposit_clip_authority() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    original = [*step.trace_events, output_event]
    clip_index = next(
        index
        for index, event in enumerate(original)
        if event.event_type == "pheromone_clip"
        and event.lineage.get("lifecycle") == "deposit"
    )
    cases = (
        ("candidate_id", "candidate:forged", "authority_pheromone_clip_candidate"),
        ("subject_type", "unsupported", "authority_pheromone_clip_subject_type"),
        ("step", 2, "authority_pheromone_clip_future_step"),
    )

    for field_name, forged_value, expected in cases:
        events = list(original)
        lineage = dict(events[clip_index].lineage)
        lineage[field_name] = forged_value
        events[clip_index] = replace(events[clip_index], lineage=lineage)

        result = hybrid_trace_contract.check_actual_trace(manifest, events)

        assert result.ok is False
        assert expected in result.detail


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    [
        ("source_id", "source:forged"),
        ("provenance", "forged:provenance"),
        ("candidate_id", "candidate:beta"),
        ("subject_id", "route:forged"),
        ("kind", "alarm"),
        ("requested_strength", 0.75),
        ("source_trace_event_id", "trace:forged"),
        ("trace_event_id", "trace:forged"),
    ],
)
def test_rejected_deposit_clip_receipt_rejects_reported_single_field_mutations(
    field_name: str,
    forged_value: object,
) -> None:
    manifest, step, events, clip_index = _rejected_deposit_trace()
    lineage = dict(events[clip_index].lineage)
    lineage[field_name] = forged_value
    events[clip_index] = replace(events[clip_index], lineage=lineage)

    result = hybrid_trace_contract.check_actual_trace(
        manifest,
        events,
        decision=step.decision,
    )

    assert result.ok is False
    assert "pheromone_clip" in result.detail


def test_rejected_deposit_clip_receipt_binds_every_original_trail_leaf() -> None:
    manifest, step, original, clip_index = _rejected_deposit_trace()
    payload = original[clip_index].lineage["causal_payload"]

    for path in _payload_leaf_paths(payload):
        events = list(original)
        lineage = deepcopy(dict(events[clip_index].lineage))
        _mutate_payload_path(lineage["causal_payload"], path)
        events[clip_index] = replace(events[clip_index], lineage=lineage)

        result = hybrid_trace_contract.check_actual_trace(
            manifest,
            events,
            decision=step.decision,
        )

        assert result.ok is False, path
        assert "fingerprint" in result.detail, path


def test_rejected_deposit_clip_receipt_rejects_digest_mismatch() -> None:
    manifest, step, events, clip_index = _rejected_deposit_trace()
    lineage = dict(events[clip_index].lineage)
    lineage["causal_fingerprint"] = "sha256:" + ("0" * 64)
    events[clip_index] = replace(events[clip_index], lineage=lineage)

    result = hybrid_trace_contract.check_actual_trace(
        manifest,
        events,
        decision=step.decision,
    )

    assert result.ok is False
    assert "fingerprint does not match" in result.detail


@pytest.mark.parametrize("missing_field", ["causal_payload", "causal_fingerprint"])
def test_rejected_deposit_clip_requires_both_receipt_fields(
    missing_field: str,
) -> None:
    manifest, step, events, clip_index = _rejected_deposit_trace()
    lineage = dict(events[clip_index].lineage)
    lineage.pop(missing_field)
    events[clip_index] = replace(events[clip_index], lineage=lineage)

    result = hybrid_trace_contract.check_actual_trace(
        manifest,
        events,
        decision=step.decision,
    )

    assert result.ok is False
    assert "causal_payload and causal_fingerprint" in result.detail


def test_rejected_deposit_requires_declared_scored_subject_but_allows_global_evidence_memory() -> (
    None
):
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = replace(
        manifest.protocol.collective_decision_policy,
        pheromone_min_strength=1.0,
        pheromone_max_strength=10.0,
        pheromone_per_source_cap=10.0,
        pheromone_per_round_deposit_cap=10.0,
    )
    manifest = replace(
        manifest,
        protocol=replace(manifest.protocol, collective_decision_policy=policy),
    )
    target = manifest.protocol.quorum_policy.target
    empty_topology = PheromoneNeighborhood(subjects=[], edges=[])

    def deposit(subject_type: str) -> PheromoneTrail:
        return PheromoneTrail(
            candidate_id="candidate:alpha",
            strength=0.5,
            subject_type=subject_type,
            subject_id=f"{subject_type}:memory",
            target=target,
            kind="positive",
            source_id=f"source:{subject_type}",
            evidence_id="evidence:memory",
            provenance=f"driver:{subject_type}",
            trace_event_id=f"trace:{subject_type}",
            deposited_at_step=1,
            updated_at_step=1,
        )

    evidence_step = evaluate_hybrid_collective_step(
        protocol_id=manifest.protocol.id,
        candidate_set=hybrid_trace_contract.candidate_set(manifest),
        policy=policy,
        target=target,
        current_step=1,
        scout_reports=[],
        deposits=[deposit("evidence")],
        topology=empty_topology,
        fallback_candidate_id=collective_fallback_id(manifest.protocol),
    )
    evidence_clip = next(
        event
        for event in evidence_step.trace_events
        if event.event_type == "pheromone_clip"
    )

    assert evidence_clip.lineage["result"] == "rejected"
    assert evidence_clip.lineage["subject_type"] == "evidence"
    assert evidence_step.active_trails == ()
    with pytest.raises(GovernanceError, match="not declared in topology"):
        evaluate_hybrid_collective_step(
            protocol_id=manifest.protocol.id,
            candidate_set=hybrid_trace_contract.candidate_set(manifest),
            policy=policy,
            target=target,
            current_step=1,
            scout_reports=[],
            deposits=[deposit("route")],
            topology=empty_topology,
            fallback_candidate_id=collective_fallback_id(manifest.protocol),
        )


def test_hybrid_trace_contract_binds_output_commit_gate_to_decision() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    events = [*step.trace_events, output_event]
    output_index = next(
        index for index, event in enumerate(events) if event.event_type == "output"
    )
    lineage = dict(events[output_index].lineage)
    lineage.update(
        {
            "committed_candidate": False,
            "evidence_provenance": False,
            "authorized": False,
        }
    )
    events[output_index] = replace(events[output_index], lineage=lineage)

    result = hybrid_trace_contract.check_actual_trace(manifest, events)

    assert result.ok is False
    assert "authority_output_committed_candidate" in result.detail


def test_hybrid_trace_contract_rejects_forbidden_adjustment_authority() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    events = [*step.trace_events, output_event]
    adjustment_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "policy_adjustment"
    )
    lineage = dict(events[adjustment_index].lineage)
    lineage["proposed_values"] = {"fallback_candidate": "candidate:alpha"}
    lineage["declared_bounds"] = {
        "fallback_candidate": {"allowed_values": ["candidate:alpha"]}
    }
    events[adjustment_index] = replace(events[adjustment_index], lineage=lineage)

    result = hybrid_trace_contract.check_actual_trace(manifest, events)

    assert result.ok is False
    assert "authority_policy_adjustment_undeclared:fallback_candidate" in result.detail
    assert "authority_policy_adjustment_invalid" in result.detail


def test_hybrid_trace_contract_requires_all_score_affecting_upstream_lineage() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    events = [*step.trace_events, output_event]
    commit_index = next(
        index for index, event in enumerate(events) if event.event_type == "commit"
    )
    lineage = dict(events[commit_index].lineage)
    lineage["upstream_score_lineage"] = ["candidate_score", "pheromone_score"]
    events[commit_index] = replace(events[commit_index], lineage=lineage)

    result = hybrid_trace_contract.check_actual_trace(manifest, events)

    assert result.ok is False
    assert "authority_recruitment_upstream_lineage" in result.detail
    assert "authority_inhibition_upstream_lineage" in result.detail
    assert "authority_adjustment_upstream_lineage" in result.detail
    assert "authority_pheromone_trail_upstream_lineage" in result.detail


def test_hybrid_trace_contract_rejects_ambiguous_collective_trace_ids() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    events = [*step.trace_events, output_event]
    scout_indexes = [
        index
        for index, event in enumerate(events)
        if event.event_type == "scout_report"
    ]
    first_trace = events[scout_indexes[0]].lineage["source_trace_event_id"]
    lineage = dict(events[scout_indexes[1]].lineage)
    lineage["source_trace_event_id"] = first_trace
    events[scout_indexes[1]] = replace(events[scout_indexes[1]], lineage=lineage)

    result = hybrid_trace_contract.check_actual_trace(manifest, events)

    assert result.ok is False
    assert "authority_duplicate_collective_trace" in result.detail


def test_hybrid_trace_contract_rejects_phantom_pheromone_score() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    events = [*step.trace_events, output_event]
    score_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "pheromone_score"
    )
    lineage = dict(events[score_index].lineage)
    lineage["active_trails"] = []
    events[score_index] = replace(events[score_index], lineage=lineage)

    result = hybrid_trace_contract.check_actual_trace(manifest, events)

    assert result.ok is False
    assert "authority_pheromone_reconstruction" in result.detail


def test_hybrid_trace_contract_rejects_altered_coordination_confidence_and_phantom_weight() -> (
    None
):
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    original = [*step.trace_events, output_event]
    assess_index = next(
        index
        for index, event in enumerate(original)
        if event.event_type == "coordination_assess"
    )

    confidence_events = list(original)
    confidence = dict(confidence_events[assess_index].lineage)
    confidence["confidences"] = dict(confidence["confidences"])
    confidence["confidences"]["learned"] = 0.01
    confidence_events[assess_index] = replace(
        confidence_events[assess_index],
        lineage=confidence,
    )
    confidence_result = hybrid_trace_contract.check_actual_trace(
        manifest,
        confidence_events,
    )

    weight_events = list(original)
    weight = dict(weight_events[assess_index].lineage)
    weight["weights"] = {**weight["weights"], "phantom": 1.0}
    weight_events[assess_index] = replace(
        weight_events[assess_index],
        lineage=weight,
    )
    weight_result = hybrid_trace_contract.check_actual_trace(manifest, weight_events)

    coverage_events = list(original)
    coverage = dict(coverage_events[assess_index].lineage)
    coverage["coverage"] = {
        key: dict(value) for key, value in coverage["coverage"].items()
    }
    coverage["coverage"]["learned"]["mean_confidence"] = 0.01
    coverage_events[assess_index] = replace(
        coverage_events[assess_index],
        lineage=coverage,
    )
    coverage_result = hybrid_trace_contract.check_actual_trace(
        manifest,
        coverage_events,
    )

    assert confidence_result.ok is False
    assert "authority_coordination_confidences" in confidence_result.detail
    assert weight_result.ok is False
    assert "weights must contain exactly the declared layer ids" in weight_result.detail
    assert coverage_result.ok is False
    assert "authority_coordination_coverage" in coverage_result.detail


def test_hybrid_trace_contract_rejects_forged_coordination_resolution_fields() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    original = [*step.trace_events, output_event]
    resolve_index = next(
        index
        for index, event in enumerate(original)
        if event.event_type == "coordination_resolve"
    )

    mutations = (
        (
            {"selected_candidate": "candidate:beta"},
            "authority_coordination_resolution_selected_candidate",
        ),
        (
            {"conflicts": ["fallback_pressure"]},
            "authority_coordination_resolution_conflicts",
        ),
        (
            {
                "resolution": "metacognitive_conflict_resolution",
                "reason": "metacognitive_conflict_resolution",
            },
            "authority_coordination_resolution_resolution",
        ),
        (
            {"reason": "forged_reason"},
            "reason must equal resolution",
        ),
        (
            {"fallback_used": not original[resolve_index].lineage["fallback_used"]},
            "authority_coordination_resolution_fallback_used",
        ),
    )
    for updates, expected in mutations:
        events = list(original)
        lineage = {**events[resolve_index].lineage, **updates}
        events[resolve_index] = replace(events[resolve_index], lineage=lineage)

        result = hybrid_trace_contract.check_actual_trace(manifest, events)

        assert result.ok is False
        assert expected in result.detail


def test_hybrid_trace_contract_replays_zero_proposal_coordination() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(
        manifest,
        force_fallback=True,
        include_layer_inputs=False,
    )
    events = [*step.trace_events, output_event]
    assessment = next(
        event for event in events if event.event_type == "coordination_assess"
    )

    result = hybrid_trace_contract.check_actual_trace(
        manifest,
        events,
        decision=step.decision,
    )

    assert result.ok is True, result.detail
    assert assessment.lineage["proposal_lineage"] == []
    assert assessment.lineage["action_effects"] == {}
    assert all(
        snapshot["present"] is False
        for snapshot in assessment.lineage["snapshots"].values()
    )


def test_hybrid_trace_contract_rejects_safe_fallback_when_consensus_exists() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    events = [*step.trace_events, output_event]
    commit_index = next(
        index for index, event in enumerate(events) if event.event_type == "commit"
    )
    lineage = dict(events[commit_index].lineage)
    lineage.update(
        {
            "candidate_id": "candidate:safe_fallback",
            "decision_reason": "safe_collective_fallback",
        }
    )
    events[commit_index] = replace(
        events[commit_index],
        event_type="fallback",
        reason="tampered fallback despite consensus",
        lineage=lineage,
    )

    result = hybrid_trace_contract.check_actual_trace(manifest, events)

    assert result.ok is False
    assert "authority_fallback_despite_consensus" in result.detail


def test_hybrid_trace_contract_replays_real_manifest_policy_and_transitions() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )

    step, output_event = hybrid_trace_contract.manifest_replay(manifest)
    events = [*step.trace_events, output_event]
    result = hybrid_trace_contract.check_actual_trace(
        manifest,
        events,
        decision=step.decision,
    )
    coverage = hybrid_trace_contract.check(manifest)
    observed = {event.event_type for event in events}

    assert result.ok is True, result.detail
    assert coverage.ok is True, coverage.detail
    assert {"pheromone_deposit", "pheromone_evaporate", "pheromone_expire"} <= observed
    assert {"pheromone_diffuse", "candidate_score", "commit", "output"} <= observed
    assert "fallback" not in observed
    assert "recovery" not in observed


def test_hybrid_trace_contract_covers_lifecycle_under_tight_legal_budget() -> None:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    tight = replace(
        policy,
        pheromone_min_strength=0.25,
        pheromone_max_strength=0.5,
        pheromone_per_source_cap=0.25,
        pheromone_per_round_deposit_cap=0.5,
        pheromone_min_source_diversity=2,
    )
    variant = replace(
        manifest,
        protocol=replace(manifest.protocol, collective_decision_policy=tight),
    )

    assert validate_capability_manifest(variant) == []
    result = hybrid_trace_contract.check(variant)
    diffusion_step, _ = hybrid_trace_contract.manifest_replay(
        variant,
        force_fallback=True,
        lifecycle_focus="diffusion",
    )
    reinforcement_step, _ = hybrid_trace_contract.manifest_replay(
        variant,
        force_fallback=True,
        lifecycle_focus="reinforcement",
    )

    assert result.ok is True, result.detail
    assert "pheromone_reinforce" not in {
        event.event_type for event in diffusion_step.trace_events
    }
    reinforcement = next(
        event
        for event in reinforcement_step.trace_events
        if event.event_type == "pheromone_reinforce"
    )
    assert reinforcement.lineage["delta"] > 0


def test_hybrid_trace_contract_rejects_malformed_actual_event_without_throwing() -> (
    None
):
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    target = manifest.protocol.quorum_policy.target
    malformed = TraceEvent(
        event_type="candidate_score",
        protocol_id=manifest.protocol.id,
        target=target,
        reason="missing lineage",
    )

    result = hybrid_trace_contract.check_actual_trace(manifest, [malformed])

    assert result.ok is False
    assert "missing required fields" in result.detail
    assert "decision_event_count" in result.detail


def test_pheromone_policy_conformance_reports_stigmergic_memory_invariants() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    protocol = replace(
        manifest.protocol,
        collective_decision_policy=replace(
            manifest.protocol.collective_decision_policy,
            pheromone_decay_model="adaptive",
            pheromone_min_strength=4,
            pheromone_max_strength=1,
            pheromone_positive_weight=-1,
            pheromone_novelty_weight=-1,
            pheromone_cautionary_override_threshold=-1,
            pheromone_per_source_cap=-1,
            pheromone_per_round_deposit_cap=-1,
            pheromone_min_source_diversity=0,
            pheromone_require_provenance=False,
            pheromone_require_trace=False,
        ),
    )

    result = pheromone_policy.check(replace(manifest, protocol=protocol))

    assert result.ok is False
    assert "decay_model" in result.detail
    assert "strength_bounds" in result.detail
    assert "weights" in result.detail
    assert "cautionary_threshold" in result.detail
    assert "caps" in result.detail
    assert "min_source_diversity" in result.detail


def test_pheromone_behavior_conformance_proves_runtime_boundaries() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")

    result = pheromone_behavior.check(manifest)

    assert result.ok is True
    assert result.detail == ""


def test_pheromone_policy_conformance_does_not_overconstrain_trace_policy_flags() -> (
    None
):
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    protocol = replace(
        manifest.protocol,
        collective_decision_policy=replace(
            manifest.protocol.collective_decision_policy,
            pheromone_require_provenance=False,
            pheromone_require_trace=False,
        ),
    )

    result = pheromone_policy.check(replace(manifest, protocol=protocol))

    assert result.ok is True


def _rejected_deposit_trace():
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    policy = replace(
        policy,
        pheromone_min_strength=1.0,
        pheromone_max_strength=10.0,
        pheromone_per_source_cap=10.0,
        pheromone_per_round_deposit_cap=10.0,
    )
    manifest = replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            collective_decision_policy=policy,
        ),
    )
    assert validate_capability_manifest(manifest) == []
    target = manifest.protocol.quorum_policy.target
    trail = PheromoneTrail(
        candidate_id="candidate:alpha",
        strength=0.5,
        subject_type="route",
        subject_id="route:tiny",
        target=target,
        kind="positive",
        source_id="source:tiny",
        source_role="scout",
        evidence_id="evidence:tiny",
        provenance="driver:tiny",
        trace_event_id="trace:tiny",
        deposited_at_step=1,
        updated_at_step=1,
        ttl_steps=2,
    )
    topology = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject(
                "route",
                "route:tiny",
                "candidate:alpha",
                target,
            )
        ],
        edges=[],
    )
    step = evaluate_hybrid_collective_step(
        protocol_id=manifest.protocol.id,
        candidate_set=hybrid_trace_contract.candidate_set(manifest),
        policy=policy,
        target=target,
        current_step=1,
        scout_reports=[],
        deposits=[trail],
        topology=topology,
        fallback_candidate_id=collective_fallback_id(manifest.protocol),
    )
    events = list(step.trace_events)
    clip_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "pheromone_clip"
        and event.lineage.get("lifecycle") == "deposit"
        and event.lineage.get("result") == "rejected"
    )
    baseline = hybrid_trace_contract.check_actual_trace(
        manifest,
        events,
        decision=step.decision,
    )
    assert baseline.ok is True, baseline.detail
    return manifest, step, events, clip_index


def _payload_leaf_paths(value, path=()):
    if isinstance(value, dict):
        return [
            leaf
            for key, item in value.items()
            for leaf in _payload_leaf_paths(item, (*path, key))
        ]
    if isinstance(value, list):
        return [
            leaf
            for index, item in enumerate(value)
            for leaf in _payload_leaf_paths(item, (*path, index))
        ]
    return [path]


def _mutate_payload_path(payload, path) -> None:
    parent = payload
    for part in path[:-1]:
        parent = parent[part]
    key = path[-1]
    value = parent[key]
    if isinstance(value, bool):
        parent[key] = not value
    elif isinstance(value, int):
        parent[key] = value + 1
    elif isinstance(value, float):
        parent[key] = value + 0.125
    elif isinstance(value, str):
        parent[key] = value + ":forged"
    elif value is None:
        parent[key] = 1
    else:  # pragma: no cover - fixture payloads are closed JSON leaves
        raise AssertionError(f"unsupported payload leaf: {path!r}")
