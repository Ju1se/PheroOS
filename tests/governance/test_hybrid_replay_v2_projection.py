from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Sequence, cast

import pytest

from pheroos.governance import (
    AuthorityLevel,
    Candidate,
    CandidateSet,
    LayerProposal,
    PolicyAdjustmentProposal,
    ScoutReport,
    verify_signal_input,
)
from pheroos.governance._pheromone.records import (
    PheromoneEdge,
    PheromoneNeighborhood,
    PheromoneSubject,
    PheromoneTrail,
)
from pheroos.governance.pheromone_feedback import PheromoneFeedback
from pheroos.governance._swarm.pipeline import evaluate_hybrid_collective_step
from pheroos.governance._swarm.records import HybridReplayState
from pheroos.governance._swarm.replay import replay_state_from_hybrid_step
from pheroos.governance._hybrid_replay_v2.contracts import (
    HybridReplayAdvanceRequestV2,
    HybridReplaySnapshotV2,
)
from pheroos.governance._authority_store_v2_contracts.foundation import _compute_root
from pheroos.governance._hybrid_replay_v2.projection import (
    build_hybrid_replay_advance_request_v2,
    project_collective_policy_v2,
    project_topology_v2,
    restore_collective_policy_v2,
    restore_hybrid_replay_inputs_v2,
    restore_topology_v2,
    verify_hybrid_replay_request_source_v2,
)
from pheroos.governance._hybrid_replay_v2.source import (
    VerifiedHybridSourceStepV2,
    _issue_verified_hybrid_source_step_v2,
)
from pheroos.governance._swarm.records import HybridCollectiveStep
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.authority_manifest_v2 import (
    BASELINE_OUTPUT_POLICY_VERSION_V2,
    PROTOCOL_VERSION_V2,
    REQUIRED_BASELINE_OUTPUT_TRACE_EVENTS_V2,
    ScopedProtocolManifestV2,
    scoped_protocol_manifest_v2_from_dict,
)
from pheroos.protocol.models import (
    CollectiveDecisionPolicy,
    PheromoneKindProfile,
)


DOMAIN_ROOT = "sha256:" + "1" * 64


def _verified_scout(source_id: str, candidate_id: str, target: str) -> ScoutReport:
    trace_id = f"trace:{source_id}"
    return ScoutReport(
        scout_id=source_id,
        candidate_id=candidate_id,
        evidence_id=f"evidence:{source_id}",
        provenance=f"driver:{source_id}",
        target=target,
        trace_event_id=trace_id,
        verification=verify_signal_input(
            target=target,
            source_id=source_id,
            subject_id=candidate_id,
            verifier_id="governance:hybrid-replay-test",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="governance:hybrid-replay-test",
            trace_event_id=f"{trace_id}:verified",
        ),
    )


def _route_trail(
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


def _deposits(target: str) -> list[PheromoneTrail]:
    return [
        _route_trail(
            "candidate:alpha",
            "route:alpha",
            target,
            "positive",
            1.0,
            "source:alpha",
        ),
        _route_trail(
            "candidate:beta",
            "route:beta",
            target,
            "cautionary",
            0.5,
            "source:beta",
        ),
    ]


def _topology(target: str) -> PheromoneNeighborhood:
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


def _feedback(target: str) -> list[PheromoneFeedback]:
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


def _layer_proposals(target: str) -> list[LayerProposal]:
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


def _scoped_manifest() -> ScopedProtocolManifestV2:
    payload = json.loads(
        Path("examples/hybrid-pheromone-protocol/capability.json").read_text()
    )["protocol"]
    payload["protocol_version"] = PROTOCOL_VERSION_V2
    payload["authority_policy"] = {
        "policy_version": "pheroos-scoped-authority-policy-v2",
        "profile": "pheroos-scoped-authority-local-v2",
        "wire_version": "pheroos-authority-wire-v2",
        "canonical_version": "pheroos-authority-canonical-v2",
        "ledger_version": "pheroos-governance-authority-ledger-v2",
        "state_store_version": "pheroos-governance-state-store-v2",
        "trace_batch_version": "pheroos-governance-trace-batch-v2",
        "read_set_version": "pheroos-governance-authority-read-set-v2",
    }
    payload["output_policy"] = {
        "policy_version": BASELINE_OUTPUT_POLICY_VERSION_V2,
        "decision_mode": "quorum",
        "actions": [
            {
                "action_ref": "action:publish",
                "effect": "publish",
                "target": payload["quorum_policy"]["target"],
                "allowed_outcomes": ["evidence_commit", "safe_fallback"],
            }
        ],
    }
    payload["trace_policy"]["required_events"] = sorted(
        set(payload["trace_policy"]["required_events"])
        | REQUIRED_BASELINE_OUTPUT_TRACE_EVENTS_V2
    )
    return scoped_protocol_manifest_v2_from_dict(payload)


def _fixture() -> tuple[
    ScopedProtocolManifestV2,
    CollectiveDecisionPolicy,
    CandidateSet,
    PheromoneNeighborhood,
]:
    protocol = _scoped_manifest()
    policy = protocol.collective_decision_policy
    assert policy is not None
    candidates = CandidateSet(
        tuple(
            Candidate(item.id, item.target, item.safe_fallback)
            for item in protocol.candidates
        )
    )
    return protocol, policy, candidates, _topology(protocol.quorum_policy.target)


def _candidate_projection_for_manifest(
    protocol: ScopedProtocolManifestV2,
) -> dict[str, object]:
    target = protocol.quorum_policy.target
    candidates = sorted(
        (item for item in protocol.candidates if item.target == target),
        key=lambda item: item.id,
    )
    return {
        "candidates": [
            {
                "candidate_ref": item.id,
                "target_ref": item.target,
                "safe_fallback": item.safe_fallback,
            }
            for item in candidates
        ],
        "fallback_candidate_ref": protocol.quorum_policy.fallback_candidate,
    }


def _source(
    step: HybridCollectiveStep,
    *,
    current_step: int,
    parent: HybridReplaySnapshotV2 | None = None,
    domain_root: str = DOMAIN_ROOT,
    scope_ref: str = "scope:test",
    run_ref: str = "run:test",
    observed_epoch: int = 3,
) -> VerifiedHybridSourceStepV2:
    protocol, policy, _, neighborhood = _fixture()
    candidate_projection = _candidate_projection_for_manifest(protocol)
    base_projection = project_collective_policy_v2(policy)
    input_projection = (
        base_projection
        if parent is None
        else cast(
            dict[str, object],
            parent.to_dict()["effective_policy_projection"],
        )
    )
    topology_projection = project_topology_v2(neighborhood)
    return _issue_verified_hybrid_source_step_v2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        observed_epoch=observed_epoch,
        step=step,
        manifest=protocol,
        topology=neighborhood,
        input_policy_projection=input_projection,
        candidate_projection_root=_compute_root(
            "hybrid-replay-candidate-projection", candidate_projection
        ),
        base_policy_projection_root=_compute_root(
            "hybrid-replay-policy-projection", base_projection
        ),
        topology_projection_root=_compute_root(
            "hybrid-replay-topology-projection", topology_projection
        ),
        parent_snapshot=parent,
        current_step=current_step,
    )


def _step(
    *,
    current_step: int = 1,
    replay_state: HybridReplayState | None = None,
    policy: CollectiveDecisionPolicy | None = None,
    adjustment_field: str = "pheromone_positive_weight",
    adjustment_value: object = 1.2,
    adjustment_id: str = "trace:adjustment:one",
) -> HybridCollectiveStep:
    protocol, base, candidates, neighborhood = _fixture()
    active_policy = policy or base
    target = protocol.quorum_policy.target
    return evaluate_hybrid_collective_step(
        protocol_id=protocol.id,
        candidate_set=candidates,
        policy=active_policy,
        target=target,
        current_step=current_step,
        scout_reports=[
            _verified_scout(f"scout:{current_step}:a", "candidate:alpha", target),
            _verified_scout(f"scout:{current_step}:b", "candidate:alpha", target),
        ],
        deposits=(_deposits(target) if replay_state is None else []),
        topology=neighborhood,
        feedback=(_feedback(target) if replay_state is None else []),
        layer_proposals=(_layer_proposals(target) if replay_state is None else []),
        adjustment_proposals=[
            PolicyAdjustmentProposal(
                layer_id="evolutionary",
                source_id=f"layer:evolutionary:{current_step}",
                adjustments={adjustment_field: adjustment_value},
                provenance="runtime:evolutionary",
                trace_event_id=adjustment_id,
            )
        ],
        replay_state=replay_state,
        fallback_candidate_id=protocol.quorum_policy.fallback_candidate,
    )


def _request(
    step: HybridCollectiveStep,
    *,
    advance_ref: str,
    current_step: int,
    parent: HybridReplaySnapshotV2 | None = None,
    observed_epoch: int = 3,
) -> HybridReplayAdvanceRequestV2:
    return build_hybrid_replay_advance_request_v2(
        domain_root=DOMAIN_ROOT,
        scope_ref="scope:test",
        run_ref="run:test",
        observed_epoch=observed_epoch,
        advance_ref=advance_ref,
        source=_source(
            step,
            current_step=current_step,
            parent=parent,
            observed_epoch=observed_epoch,
        ),
    )


def _verify(
    request: HybridReplayAdvanceRequestV2,
    step: HybridCollectiveStep,
    parent: HybridReplaySnapshotV2 | None = None,
) -> None:
    verify_hybrid_replay_request_source_v2(
        request,
        source=_source(
            step,
            current_step=request.snapshot.current_step,
            parent=parent,
            domain_root=request.domain_root,
            scope_ref=request.scope_ref,
            run_ref=request.run_ref,
            observed_epoch=request.observed_epoch,
        ),
        committed_parent_snapshot=parent,
    )


def _with_snapshot_mutation(
    request: HybridReplayAdvanceRequestV2,
    mutate: Callable[[dict[str, Any]], None],
) -> HybridReplayAdvanceRequestV2:
    payload = cast(dict[str, Any], deepcopy(request.to_dict()))
    snapshot = cast(dict[str, Any], payload["snapshot"])
    mutate(snapshot)
    for field in (
        "candidate_projection_root",
        "policy_projection_root",
        "topology_projection_root",
        "active_trails_root",
        "replay_receipts_root",
        "last_budget_root",
        "overlay_root",
        "effective_policy_root",
        "source_trace_set_root",
        "source_lineage_root",
        "state_root",
        "snapshot_root",
    ):
        snapshot[field] = ""
    payload["request_root"] = ""
    return HybridReplayAdvanceRequestV2.from_dict(payload)


def test_policy_projection_is_deterministic_closed_and_round_trippable() -> None:
    _, base, _, _ = _fixture()
    policy = replace(
        base,
        pheromone_scored_subject_types=["tool", "candidate", "route"],
        pheromone_kind_profiles={
            "positive": PheromoneKindProfile(
                weight=1,
                scored_subject_types=["tool", "candidate"],
            ),
            "alarm": PheromoneKindProfile(
                weight=2,
                evaporation_rate=0.5,
                scored_subject_types=["route", "candidate"],
            ),
        },
        policy_adjustment_bounds={
            "pheromone_response_model": {
                "allowed_values": ["threshold", "linear", "saturating"]
            },
            "pheromone_positive_weight": [0, 2],
        },
    )

    projected = project_collective_policy_v2(policy)
    profiles = cast(
        Sequence[Mapping[str, object]], projected["pheromone_kind_profiles"]
    )
    bounds = cast(Sequence[Mapping[str, object]], projected["policy_adjustment_bounds"])

    assert tuple(projected) == (
        "mode",
        "min_independent_scouts",
        "quorum_threshold",
        "recruitment_enabled",
        "inhibition_enabled",
        "pheromone_enabled",
        "pheromone_decay_model",
        "pheromone_min_source_diversity",
        "pheromone_require_provenance",
        "pheromone_require_trace",
        "pheromone_scored_subject_types",
        "pheromone_response_model",
        "pheromone_competition_mode",
        "pheromone_diffusion_enabled",
        "pheromone_diffusion_max_hops",
        "pheromone_feedback_enabled",
        "exploration_enabled",
        "layer_coordination_enabled",
        "layer_min_provenance",
        "layer_fallback_on_unresolved_conflict",
        "fallback_candidate_ref",
        "pheromone_evaporation_rate",
        "pheromone_min_strength",
        "pheromone_max_strength",
        "pheromone_positive_weight",
        "pheromone_negative_weight",
        "pheromone_cautionary_weight",
        "pheromone_cautionary_override_threshold",
        "pheromone_novelty_weight",
        "pheromone_per_source_cap",
        "pheromone_per_round_deposit_cap",
        "pheromone_activation_threshold",
        "pheromone_saturation_threshold",
        "pheromone_exploration_floor",
        "pheromone_diffusion_attenuation",
        "exploration_floor",
        "novelty_decay_rate",
        "stale_route_reopen_threshold",
        "layer_conflict_threshold",
        "layer_emergency_override_threshold",
        "pheromone_kind_profiles",
        "layer_weight_bounds",
        "layer_default_weights",
        "layer_confidence_thresholds",
        "policy_adjustment_bounds",
    )
    assert projected["pheromone_scored_subject_types"] == [
        "candidate",
        "route",
        "tool",
    ]
    assert [item["kind"] for item in profiles] == ["alarm", "positive"]
    assert profiles[0]["scored_subject_types"] == ["candidate", "route"]
    assert [item["field_ref"] for item in bounds] == [
        "pheromone_positive_weight",
        "pheromone_response_model",
    ]
    assert bounds[1]["allowed_values"] == ["linear", "saturating", "threshold"]
    assert project_collective_policy_v2(restore_collective_policy_v2(projected)) == (
        projected
    )


def test_policy_projection_preserves_finite_binary64_boundaries() -> None:
    _, base, _, _ = _fixture()
    policy = replace(
        base,
        pheromone_activation_threshold=-0.0,
        pheromone_saturation_threshold=sys.float_info.max,
        layer_weight_bounds={
            layer: (-0.0, sys.float_info.max)
            for layer in (
                "reactive",
                "learned",
                "evolutionary",
                "metacognitive",
            )
        },
    )

    projected = project_collective_policy_v2(policy)
    restored = restore_collective_policy_v2(projected)

    assert projected["pheromone_activation_threshold"] == (-0.0).hex()
    assert projected["pheromone_saturation_threshold"] == sys.float_info.max.hex()
    assert math.copysign(1.0, restored.pheromone_activation_threshold) == -1.0
    assert restored.pheromone_saturation_threshold == sys.float_info.max
    assert project_collective_policy_v2(restored) == projected


def test_policy_projection_and_restore_reject_invalid_inputs() -> None:
    _, base, _, _ = _fixture()

    with pytest.raises(TypeError, match="exact CollectiveDecisionPolicy"):
        project_collective_policy_v2(cast(CollectiveDecisionPolicy, object()))
    with pytest.raises(GovernanceError, match="extension semantics"):
        project_collective_policy_v2(replace(base, extensions={"x-active": True}))
    with pytest.raises(ValueError, match="finite binary64"):
        project_collective_policy_v2(replace(base, pheromone_positive_weight=math.inf))
    with pytest.raises(GovernanceError, match="declare every layer"):
        project_collective_policy_v2(
            replace(
                base,
                layer_default_weights={"reactive": 1.0},
            )
        )

    malformed = deepcopy(project_collective_policy_v2(base))
    malformed["pheromone_positive_weight"] = "0x1.0p+0 "
    with pytest.raises(ValueError, match="canonical binary64"):
        restore_collective_policy_v2(malformed)


def test_topology_projection_is_sorted_and_round_trippable() -> None:
    target = "target:test"
    first = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject("route", "route:z", "candidate:z", target),
            PheromoneSubject("candidate", "candidate:a", "candidate:a", target),
        ],
        edges=[
            PheromoneEdge("route", "route:z", "candidate", "candidate:a", -0.0),
            PheromoneEdge(
                "candidate",
                "candidate:a",
                "route",
                "route:z",
                sys.float_info.max,
            ),
        ],
    )
    reversed_input = PheromoneNeighborhood(
        subjects=list(reversed(first.subjects)),
        edges=list(reversed(first.edges)),
    )

    projected = project_topology_v2(first)
    edges = cast(Sequence[Mapping[str, object]], projected["edges"])

    assert projected == project_topology_v2(reversed_input)
    assert [
        (item["subject_type"], item["subject_ref"])
        for item in cast(Sequence[Mapping[str, object]], projected["subjects"])
    ] == [
        ("candidate", "candidate:a"),
        ("route", "route:z"),
    ]
    assert edges[0]["attenuation"] == sys.float_info.max.hex()
    assert edges[1]["attenuation"] == (-0.0).hex()
    assert project_topology_v2(restore_topology_v2(projected)) == projected
    assert project_topology_v2(PheromoneNeighborhood()) == {
        "subjects": [],
        "edges": [],
    }


def test_topology_projection_and_restore_reject_invalid_inputs() -> None:
    with pytest.raises(TypeError, match="exact PheromoneNeighborhood"):
        project_topology_v2(cast(PheromoneNeighborhood, object()))

    nonfinite = PheromoneNeighborhood(
        subjects=[
            PheromoneSubject("candidate", "candidate:a", "candidate:a", "target:test")
        ],
        edges=[
            PheromoneEdge(
                "candidate",
                "candidate:a",
                "candidate",
                "candidate:a",
                math.nan,
            )
        ],
    )
    with pytest.raises(ValueError, match="finite binary64"):
        project_topology_v2(nonfinite)

    malformed = {
        "subjects": [],
        "edges": [
            {
                "source_subject_type": "candidate",
                "source_subject_ref": "candidate:a",
                "target_subject_type": "candidate",
                "target_subject_ref": "candidate:a",
                "attenuation": "1.0",
            }
        ],
    }
    with pytest.raises(ValueError, match="canonical binary64"):
        restore_topology_v2(malformed)


def test_projection_round_trip_restores_every_v1_replay_fingerprint() -> None:
    step = _step()
    request = _request(step, advance_ref="advance:one", current_step=1)

    _verify(request, step)
    restored = restore_hybrid_replay_inputs_v2(request.snapshot)

    assert restored.replay_state._issuance is None
    assert tuple(restored.replay_state.active_trails) == step.active_trails
    assert dict(restored.replay_state.deposit_replay_receipts) == dict(
        step.deposit_replay_receipts
    )
    assert dict(restored.replay_state.diffusion_replay_receipts) == dict(
        step.diffusion_replay_receipts
    )
    assert dict(restored.replay_state.feedback_replay_receipts) == dict(
        step.feedback_replay_receipts
    )
    assert dict(restored.replay_state.adjustment_replay_receipts) == dict(
        step.adjustment_replay_receipts
    )
    snapshot_payload = request.snapshot.to_dict()
    assert (
        project_collective_policy_v2(restored.effective_policy)
        == snapshot_payload["effective_policy_projection"]
    )
    assert (
        project_topology_v2(restored.topology)
        == snapshot_payload["topology_projection"]
    )
    assert restored.budget_state == step.budget_state


def test_second_step_accumulates_overlay_and_exact_source_lineage() -> None:
    first_step = _step()
    first = _request(first_step, advance_ref="advance:one", current_step=1)
    first_replay = replay_state_from_hybrid_step(first_step)
    second_step = _step(
        current_step=2,
        replay_state=first_replay,
        policy=first_step.effective_policy,
        adjustment_field="pheromone_exploration_floor",
        adjustment_value=0.25,
        adjustment_id="trace:adjustment:two",
    )
    second = _request(
        second_step,
        advance_ref="advance:two",
        current_step=2,
        parent=first.snapshot,
    )

    overlay_values = cast(
        Sequence[Mapping[str, object]], second.snapshot.overlay["values"]
    )
    values = {item["field_ref"]: item["value"] for item in overlay_values}
    assert set(values) == {
        "pheromone_positive_weight",
        "pheromone_exploration_floor",
    }
    assert set(cast(Sequence[str], first.snapshot.overlay["source_refs"])).issubset(
        cast(Sequence[str], second.snapshot.overlay["source_refs"])
    )
    assert set(cast(Sequence[str], first.snapshot.overlay["trace_roots"])).issubset(
        cast(Sequence[str], second.snapshot.overlay["trace_roots"])
    )
    assert set(cast(Sequence[str], first.snapshot.overlay["trace_roots"])).issubset(
        second.snapshot.source_trace_roots
    )
    assert second.snapshot.parent_revision == first.snapshot.revision
    assert second.snapshot.parent_snapshot_root == first.snapshot.snapshot_root
    _verify(second, second_step, first.snapshot)


def test_same_field_overlay_replaces_value_but_preserves_all_lineage() -> None:
    first_step = _step()
    first = _request(first_step, advance_ref="advance:one", current_step=1)
    second_step = _step(
        current_step=2,
        replay_state=replay_state_from_hybrid_step(first_step),
        policy=first_step.effective_policy,
        adjustment_value=1.4,
        adjustment_id="trace:adjustment:replacement",
    )
    second = _request(
        second_step,
        advance_ref="advance:two",
        current_step=2,
        parent=first.snapshot,
    )

    values = cast(Sequence[Mapping[str, object]], second.snapshot.overlay["values"])
    assert len(values) == 1
    assert values[0]["value"] == float(1.4).hex()
    assert len(cast(Sequence[str], second.snapshot.overlay["source_refs"])) == 2
    assert len(cast(Sequence[str], second.snapshot.overlay["trace_roots"])) == 2


def test_parent_allows_epoch_advance_but_rejects_epoch_rollback() -> None:
    first_step = _step()
    first = _request(first_step, advance_ref="advance:one", current_step=1)
    second_step = _step(
        current_step=2,
        replay_state=replay_state_from_hybrid_step(first_step),
        policy=first_step.effective_policy,
        adjustment_field="pheromone_exploration_floor",
        adjustment_value=0.25,
        adjustment_id="trace:adjustment:epoch",
    )

    advanced = _request(
        second_step,
        advance_ref="advance:epoch",
        current_step=2,
        parent=first.snapshot,
        observed_epoch=4,
    )
    assert advanced.snapshot.observed_epoch == 4
    _verify(advanced, second_step, first.snapshot)

    with pytest.raises(GovernanceError, match="epoch cannot roll back"):
        _request(
            second_step,
            advance_ref="advance:rollback",
            current_step=2,
            parent=first.snapshot,
            observed_epoch=2,
        )


def test_evaporation_retires_active_trails_but_never_historical_receipts() -> None:
    first_step = _step()
    first = _request(first_step, advance_ref="advance:one", current_step=1)
    later_step = _step(
        current_step=100,
        replay_state=replay_state_from_hybrid_step(first_step),
        policy=first_step.effective_policy,
        adjustment_field="pheromone_exploration_floor",
        adjustment_value=0.2,
        adjustment_id="trace:adjustment:later",
    )
    later = _request(
        later_step,
        advance_ref="advance:later",
        current_step=100,
        parent=first.snapshot,
    )

    original_active = {
        (item["trace_event_ref"], item["kind"]) for item in first.snapshot.active_trails
    }
    later_active = {
        (item["trace_event_ref"], item["kind"]) for item in later.snapshot.active_trails
    }
    assert original_active.isdisjoint(later_active)
    assert {item["kind"] for item in later.snapshot.active_trails} == {"stale"}
    prior_receipts = {
        (item["kind"], item["event_id"]): item
        for item in first.snapshot.replay_receipts
    }
    later_receipts = {
        (item["kind"], item["event_id"]): item
        for item in later.snapshot.replay_receipts
    }
    assert all(later_receipts[key] == value for key, value in prior_receipts.items())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda snapshot: snapshot.__setitem__("source_step_root", "sha256:" + "9" * 64),
        lambda snapshot: snapshot["active_trails"][0].__setitem__(
            "strength", float(0.125).hex()
        ),
        lambda snapshot: snapshot["last_budget"].__setitem__(
            "round_used", float(0.0).hex()
        ),
        lambda snapshot: snapshot["replay_receipts"][0]["payload"].__setitem__(
            "strength", float(0.25).hex()
        ),
    ],
)
def test_valid_but_source_substituted_request_is_rejected(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    step = _step()
    request = _request(step, advance_ref="advance:one", current_step=1)

    try:
        mutated = _with_snapshot_mutation(request, mutate)
    except (TypeError, ValueError):
        # Some coupled numeric substitutions are rejected even earlier by the
        # closed contract; they still fail closed and never reach authority.
        return
    with pytest.raises(GovernanceError, match="exact source"):
        _verify(mutated, step)


def test_raw_fake_step_and_parent_rollback_are_rejected() -> None:
    step = _step()
    first = _request(step, advance_ref="advance:one", current_step=1)
    fake = HybridCollectiveStep(
        decision=step.decision,
        state=step.state,
        active_trails=step.active_trails,
        layer_coordination=step.layer_coordination,
        adjustment_overlay=step.adjustment_overlay,
        effective_policy=step.effective_policy,
        budget_state=step.budget_state,
        trace_events=step.trace_events,
    )
    with pytest.raises(GovernanceError, match="not evaluation-complete"):
        _request(fake, advance_ref="advance:fake", current_step=1)

    second_step = _step(
        current_step=2,
        replay_state=replay_state_from_hybrid_step(step),
        policy=step.effective_policy,
        adjustment_field="pheromone_exploration_floor",
        adjustment_value=0.2,
        adjustment_id="trace:adjustment:two",
    )
    with pytest.raises(GovernanceError, match="current_step"):
        _request(
            second_step,
            advance_ref="advance:rollback",
            current_step=1,
            parent=first.snapshot,
        )


@pytest.mark.parametrize(
    ("receipt_field", "replacement"),
    [
        ("deposit_replay_receipts", ("deposit-v9",)),
        ("feedback_replay_receipts", ("feedback-v1", "truncated")),
        (
            "adjustment_replay_receipts",
            ("adjustment-v1", "learned", "source", (("bad",),), "p", "e"),
        ),
        ("diffusion_replay_receipts", ("diffusion-v1", "{}")),
    ],
)
def test_unknown_truncated_or_malformed_v1_fingerprints_fail_closed(
    receipt_field: str,
    replacement: tuple[object, ...],
) -> None:
    step = _step()
    receipts = dict(
        cast(Mapping[str, tuple[object, ...]], getattr(step, receipt_field))
    )
    event_id = next(iter(receipts))
    receipts[event_id] = replacement
    object.__setattr__(
        step,
        receipt_field,
        receipts,
    )
    with pytest.raises((TypeError, ValueError)):
        _request(step, advance_ref="advance:bad", current_step=1)


def test_public_entry_points_reject_wrong_exact_types_and_cross_context() -> None:
    step = _step()
    source = _source(step, current_step=1)

    with pytest.raises(TypeError, match="exact snapshot"):
        restore_hybrid_replay_inputs_v2(cast(HybridReplaySnapshotV2, object()))
    with pytest.raises(TypeError, match="exact advance request"):
        verify_hybrid_replay_request_source_v2(
            cast(HybridReplayAdvanceRequestV2, object()),
            source=source,
            committed_parent_snapshot=None,
        )
    with pytest.raises(TypeError, match="VerifiedHybridSourceStepV2"):
        build_hybrid_replay_advance_request_v2(
            domain_root=DOMAIN_ROOT,
            scope_ref="scope:test",
            run_ref="run:test",
            observed_epoch=3,
            advance_ref="advance:wrong-source",
            source=cast(VerifiedHybridSourceStepV2, object()),
        )
    with pytest.raises(GovernanceError, match="domain_root is mismatched"):
        build_hybrid_replay_advance_request_v2(
            domain_root="sha256:" + "2" * 64,
            scope_ref="scope:test",
            run_ref="run:test",
            observed_epoch=3,
            advance_ref="advance:cross-domain",
            source=source,
        )


def test_diffusion_wire_corruption_fails_at_the_public_request_boundary() -> None:
    step = _step()
    request = _request(step, advance_ref="advance:one", current_step=1)
    event_id, fingerprint = next(iter(step.diffusion_replay_receipts.items()))
    canonical = fingerprint[1]
    assert isinstance(canonical, str)
    duplicate = '{"version":"pheroos-pheromone-clip-payload-v1",' + canonical[1:]
    nonfinite = canonical.replace('"source_strength":0.5', '"source_strength":NaN', 1)
    assert nonfinite != canonical

    def substitute(snapshot: dict[str, Any], value: str) -> None:
        receipts = cast(list[dict[str, Any]], snapshot["replay_receipts"])
        receipt = next(
            item
            for item in receipts
            if item["kind"] == "diffusion" and item["event_id"] == event_id
        )
        payload = cast(dict[str, object], receipt["payload"])
        payload["canonical_causal_payload"] = value

    for value, message in (
        (duplicate, "duplicate keys"),
        (nonfinite, "non-finite"),
    ):

        def mutate_snapshot(snapshot: dict[str, Any]) -> None:
            substitute(snapshot, value)

        with pytest.raises(ValueError, match=message):
            _with_snapshot_mutation(request, mutate_snapshot)
