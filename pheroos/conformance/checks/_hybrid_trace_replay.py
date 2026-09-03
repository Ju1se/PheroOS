from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pheroos.conformance.checks._manifest import (
    active_target,
    candidate_set,
    exercise_candidate_id,
    target_candidate_ids,
)
from pheroos.governance import (
    AuthorityLevel,
    EvidenceGraph,
    EvidenceNode,
    InhibitionSignal,
    LayerPerformanceSnapshot,
    LayerProposal,
    OutputContract,
    PolicyAdjustmentProposal,
    RecruitmentSignal,
    ScoutReport,
    StopResolution,
    StrategyBias,
    evaluate_output_authorization,
    verify_signal_input,
)
from pheroos.governance._swarm.pipeline import evaluate_hybrid_collective_step
from pheroos.governance._swarm.records import HybridReplayState
from pheroos.governance.pheromone import (
    PheromoneEdge,
    PheromoneNeighborhood,
    PheromoneSubject,
    PheromoneTrail,
)
from pheroos.governance.pheromone_feedback import PheromoneFeedback
from pheroos.protocol.models import (
    CapabilityManifest,
    collective_fallback_id,
)
from pheroos.trace import TraceEvent


def replay_evaporation_kind(policy: Any) -> str | None:
    """Choose a declared/effective kind that changes before TTL at step one."""

    kinds = {
        "positive",
        "negative",
        "cautionary",
        "alarm",
        "novelty",
        *policy.pheromone_kind_profiles,
    }
    for kind in sorted(kinds):
        profile = policy.pheromone_kind_profiles.get(kind)
        rate = (
            profile.evaporation_rate
            if profile is not None and profile.evaporation_rate is not None
            else policy.pheromone_evaporation_rate
        )
        ttl_steps = profile.ttl_steps if profile is not None else None
        if rate > 0 and (ttl_steps is None or ttl_steps > 1):
            return str(kind)
    return None


def manifest_replay(
    manifest: CapabilityManifest,
    *,
    force_fallback: bool = False,
    lifecycle_focus: str | None = None,
    include_layer_inputs: bool = True,
    memory_only_feedback: bool = False,
    replay_state: HybridReplayState | None = None,
) -> tuple[Any, TraceEvent]:
    """Execute a deterministic replay derived entirely from manifest policy."""

    policy = manifest.protocol.collective_decision_policy
    if policy is None:
        raise ValueError("hybrid replay requires collective policy")
    target = active_target(manifest)
    candidates = candidate_set(manifest)
    primary = exercise_candidate_id(manifest)
    if primary is None:
        raise ValueError("hybrid replay has no active target candidate")
    active_ids = target_candidate_ids(manifest)
    secondary = next(
        (candidate_id for candidate_id in active_ids if candidate_id != primary),
        primary,
    )

    scouts = (
        []
        if force_fallback
        else [
            verified_scout(
                source_id=f"scout:conformance:{index}",
                candidate_id=primary,
                target=target,
                support=max(1.0, float(policy.quorum_threshold)),
            )
            for index in range(policy.min_independent_scouts)
        ]
    )
    recruitment = (
        [verified_recruitment("recruit:conformance", primary, target)]
        if policy.recruitment_enabled and not force_fallback
        else []
    )
    inhibition = (
        [verified_inhibition("inhibit:conformance", secondary, target)]
        if policy.inhibition_enabled and not force_fallback
        else []
    )

    unit = max(
        float(policy.pheromone_min_strength),
        min(
            float(policy.pheromone_max_strength) / 4,
            float(policy.pheromone_per_source_cap) / 4,
            float(policy.pheromone_per_round_deposit_cap) / 12,
        ),
    )
    if unit <= 0:
        raise ValueError("hybrid replay requires positive declared pheromone budgets")
    route_ids = {
        candidate_id: f"route:conformance:{index}"
        for index, candidate_id in enumerate(active_ids)
    }
    deposit_items = [
        route_trail(
            primary,
            route_ids[primary],
            target,
            "positive",
            max(
                unit,
                float(policy.pheromone_max_strength),
                float(policy.pheromone_per_source_cap),
                float(policy.pheromone_per_round_deposit_cap),
            )
            + 1,
            "source:deposit:primary",
            "trace:deposit:primary",
            step=1,
        )
    ]
    if secondary != primary:
        deposit_items.append(
            route_trail(
                secondary,
                route_ids[secondary],
                target,
                "cautionary",
                unit,
                "source:deposit:secondary",
                "trace:deposit:secondary",
                step=1,
            )
        )
    evaporation_kind = replay_evaporation_kind(policy) or "positive"
    existing = [
        route_trail(
            primary,
            "route:conformance:evaporating",
            target,
            evaporation_kind,
            float(policy.pheromone_max_strength),
            "source:existing:evaporating",
            "trace:existing:evaporating",
            step=0,
        ),
        route_trail(
            primary,
            "route:conformance:expiring",
            target,
            "alarm",
            float(policy.pheromone_max_strength),
            "source:existing:expiring",
            "trace:existing:expiring",
            step=0,
            ttl_steps=1,
        ),
    ]
    topology = replay_topology(target, active_ids, route_ids, existing)
    feedback_subject_type = "route"
    feedback_subject_id = route_ids[primary]
    if memory_only_feedback:
        feedback_subject_type = "evidence"
        feedback_subject_id = "evidence:memory:primary"
        topology = PheromoneNeighborhood(
            subjects=[
                *topology.subjects,
                PheromoneSubject(
                    feedback_subject_type,
                    feedback_subject_id,
                    primary,
                    target,
                ),
            ],
            edges=list(topology.edges),
        )
    feedback = [
        PheromoneFeedback(
            source_id="source:feedback:primary",
            subject_type=feedback_subject_type,
            subject_id=feedback_subject_id,
            candidate_id=primary,
            target=target,
            outcome="success",
            reward=1.0,
            strength_delta=unit,
            evidence_id="evidence:feedback:primary",
            provenance="conformance:feedback",
            trace_event_id="trace:feedback:primary",
            step=1,
        )
    ]
    if lifecycle_focus == "diffusion":
        # Use a separate real step to prove diffusion and feedback when a
        # legal tight round budget cannot also fund the deposit transition.
        # The source trail is current at this step, so declared minimum
        # strength remains reachable before bounded attenuation.
        deposit_items = []
        existing = [
            route_trail(
                primary,
                route_ids[primary],
                target,
                "positive",
                float(policy.pheromone_max_strength),
                "source:lifecycle:existing",
                "trace:lifecycle:existing",
                step=1,
                ttl_steps=2,
            )
        ]
        topology = replay_topology(target, active_ids, route_ids, existing)
        feedback = []
    elif lifecycle_focus == "reinforcement":
        deposit_items = []
        existing = []
        topology = PheromoneNeighborhood(
            subjects=[
                PheromoneSubject("route", route_ids[primary], primary, target),
            ],
            edges=[],
        )
        feedback = [
            PheromoneFeedback(
                source_id="source:lifecycle:feedback",
                subject_type="route",
                subject_id=route_ids[primary],
                candidate_id=primary,
                target=target,
                outcome="success",
                reward=1.0,
                strength_delta=unit,
                evidence_id="evidence:lifecycle:feedback",
                provenance="conformance:lifecycle:feedback",
                trace_event_id="trace:lifecycle:feedback",
                step=1,
            )
        ]
    layer_proposals = [
        LayerProposal(
            layer_id=layer_id,
            source_id=f"layer:conformance:{layer_id}",
            target=target,
            candidate_id=primary,
            action="support",
            confidence=max(
                0.9, float(policy.layer_confidence_thresholds.get(layer_id, 0.0))
            ),
            support=1.0,
            evidence_id=f"evidence:layer:{layer_id}",
            provenance=f"conformance:layer:{layer_id}",
            trace_event_id=f"trace:layer:{layer_id}",
        )
        for layer_id in ("reactive", "learned", "evolutionary", "metacognitive")
    ]
    snapshots = [
        LayerPerformanceSnapshot(
            layer_id,
            recent_success_rate=0.8,
            recent_conflict_rate=0.1,
            recent_fallback_rate=0.1,
            mean_confidence=0.8,
            evidence_coverage=1.0,
            trace_coverage=1.0,
        )
        for layer_id in ("reactive", "learned", "evolutionary", "metacognitive")
    ]
    biases = [
        StrategyBias(
            layer_id="evolutionary",
            candidate_id=primary,
            support=0.25,
            provenance="conformance:strategy-bias",
            trace_event_id="trace:strategy-bias",
            target=target,
            source_id="layer:conformance:evolutionary",
            confidence=0.8,
            evidence_id="evidence:strategy-bias",
        )
    ]
    adjustment_key = sorted(policy.policy_adjustment_bounds)[0]
    adjustment = PolicyAdjustmentProposal(
        layer_id="evolutionary",
        source_id="layer:conformance:evolutionary",
        adjustments={
            adjustment_key: accepted_adjustment_value(
                policy.policy_adjustment_bounds[adjustment_key]
            )
        },
        provenance="conformance:adjustment",
        trace_event_id="trace:adjustment",
    )

    step = evaluate_hybrid_collective_step(
        protocol_id=manifest.protocol.id,
        candidate_set=candidates,
        policy=policy,
        target=target,
        current_step=1,
        scout_reports=scouts,
        recruitment_signals=recruitment,
        inhibition_signals=inhibition,
        existing_trails=(None if replay_state is not None else existing),
        deposits=deposit_items,
        topology=topology,
        feedback=feedback,
        layer_proposals=layer_proposals if include_layer_inputs else [],
        performance_snapshots=snapshots if include_layer_inputs else [],
        strategy_biases=biases if include_layer_inputs else [],
        adjustment_proposals=[adjustment],
        replay_state=replay_state,
        fallback_candidate_id=collective_fallback_id(manifest.protocol),
    )
    evidence = EvidenceGraph(
        [
            EvidenceNode(report.evidence_id, report.candidate_id, report.provenance)
            for report in scouts
        ]
    )
    output_policy = manifest.protocol.output_policy
    output = evaluate_output_authorization(
        OutputContract(
            committed_candidate_required=output_policy.requires_committed_candidate,
            evidence_required=output_policy.requires_evidence_contract,
            stop_resolution_required=output_policy.requires_stop_resolution,
            publication_permission_required=output_policy.requires_publication_permission,
        ),
        step.decision,
        evidence,
        [
            StopResolution(
                target=target, action="publish", blocked=False, reason="conformance"
            )
        ],
        publication_permission=True,
        protocol_id=manifest.protocol.id,
        candidate_set=candidates,
    )
    return step, output.trace_event


def verified_scout(
    *, source_id: str, candidate_id: str, target: str, support: float
) -> ScoutReport:
    trace_event_id = f"trace:{source_id}"
    return ScoutReport(
        source_id,
        candidate_id,
        f"evidence:{source_id}",
        f"conformance:{source_id}",
        support=support,
        target=target,
        trace_event_id=trace_event_id,
        verification=verification(source_id, candidate_id, target, trace_event_id),
    )


def verified_recruitment(
    source_id: str, candidate_id: str, target: str
) -> RecruitmentSignal:
    trace_event_id = f"trace:{source_id}"
    return RecruitmentSignal(
        source_id,
        candidate_id,
        strength=0.5,
        target=target,
        provenance=f"conformance:{source_id}",
        trace_event_id=trace_event_id,
        verification=verification(source_id, candidate_id, target, trace_event_id),
    )


def verified_inhibition(
    source_id: str, candidate_id: str, target: str
) -> InhibitionSignal:
    trace_event_id = f"trace:{source_id}"
    return InhibitionSignal(
        source_id,
        candidate_id,
        strength=0.25,
        target=target,
        provenance=f"conformance:{source_id}",
        trace_event_id=trace_event_id,
        verification=verification(source_id, candidate_id, target, trace_event_id),
    )


def verification(
    source_id: str, candidate_id: str, target: str, trace_event_id: str
) -> Any:
    return verify_signal_input(
        target=target,
        source_id=source_id,
        subject_id=candidate_id,
        verifier_id="governance:conformance",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="conformance:governance",
        trace_event_id=f"{trace_event_id}:verified",
    )


def route_trail(
    candidate_id: str,
    route_id: str,
    target: str,
    kind: str,
    strength: float,
    source_id: str,
    trace_event_id: str,
    *,
    step: int,
    ttl_steps: int | None = None,
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
        provenance=f"conformance:{route_id}",
        trace_event_id=trace_event_id,
        deposited_at_step=step,
        updated_at_step=step,
        ttl_steps=ttl_steps,
    )


def replay_topology(
    target: str,
    candidate_ids: list[str],
    route_ids: dict[str, str],
    existing: list[PheromoneTrail],
) -> PheromoneNeighborhood:
    subjects: list[PheromoneSubject] = []
    edges: list[PheromoneEdge] = []
    seen_routes: set[str] = set()
    for candidate_id in candidate_ids:
        subjects.append(
            PheromoneSubject("candidate", candidate_id, candidate_id, target)
        )
        route_id = route_ids[candidate_id]
        seen_routes.add(route_id)
        subjects.append(PheromoneSubject("route", route_id, candidate_id, target))
        edges.append(PheromoneEdge("route", route_id, "candidate", candidate_id, 1.0))
    for trail in existing:
        if trail.subject_id in seen_routes:
            continue
        seen_routes.add(trail.subject_id)
        subjects.append(
            PheromoneSubject("route", trail.subject_id, trail.candidate_id, target)
        )
        edges.append(
            PheromoneEdge(
                "route", trail.subject_id, "candidate", trail.candidate_id, 1.0
            )
        )
    return PheromoneNeighborhood(subjects=subjects, edges=edges)


def accepted_adjustment_value(bounds: Any) -> Any:
    if isinstance(bounds, (list, tuple)) and len(bounds) == 2:
        return bounds[0]
    if isinstance(bounds, Mapping) and bounds.get("allowed_values"):
        return bounds["allowed_values"][0]
    if isinstance(bounds, Mapping) and "min" in bounds:
        return bounds["min"]
    raise ValueError("hybrid replay adjustment bound is malformed")
