from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pheroos.governance import (
    AuthorityLevel,
    Candidate,
    CandidateSet,
    LayerProposal,
    PolicyAdjustmentProposal,
    verify_signal_input,
)
from pheroos.governance._swarm.pipeline import evaluate_hybrid_collective_step
from pheroos.governance._swarm.replay import replay_state_from_hybrid_step
from pheroos.governance._swarm.signals import ScoutReport
from pheroos.governance._pheromone.records import (
    PheromoneEdge,
    PheromoneNeighborhood,
    PheromoneSubject,
    PheromoneTrail,
)
from pheroos.governance.pheromone_feedback import PheromoneFeedback
from pheroos.protocol import (
    collective_fallback_id,
    load_capability_manifest,
    validate_capability_manifest,
)


REPLAY_FIXTURE = (
    {
        "source_id": "runtime:replay:alpha",
        "subject_id": "route:alpha",
        "candidate_id": "candidate:alpha",
        "outcome": "success",
        "reward": 1.0,
        "strength_delta": 2.0,
    },
    {
        "source_id": "runtime:replay:beta",
        "subject_id": "route:beta",
        "candidate_id": "candidate:beta",
        "outcome": "congested",
        "reward": -0.4,
        "strength_delta": 1.0,
    },
)


def run_replay(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parents[2]
    manifest = load_capability_manifest(
        root / "examples/hybrid-pheromone-protocol/capability.json"
    )
    diagnostics = validate_capability_manifest(manifest)
    if diagnostics:
        raise ValueError(
            f"manifest diagnostics: {[item.to_dict() for item in diagnostics]}"
        )

    protocol = manifest.protocol
    policy = protocol.collective_decision_policy
    if policy is None:
        raise ValueError("adaptive replay requires a collective decision policy")
    target = protocol.quorum_policy.target
    candidate_set = CandidateSet(
        [
            Candidate(candidate.id, candidate.target, candidate.safe_fallback)
            for candidate in protocol.candidates
        ]
    )
    feedback = replay_feedback(target)
    scouts = [
        verified_scout("scout:replay:a", "candidate:alpha", target),
        verified_scout("scout:replay:b", "candidate:alpha", target),
    ]
    layer_proposals = replay_layer_proposals(target)
    adjustment_proposals = [
        PolicyAdjustmentProposal(
            layer_id="evolutionary",
            source_id="runtime:replay",
            adjustments={"pheromone_evaporation_rate": 0.2},
            provenance="trace-replay:episode:1",
            trace_event_id="trace:episode:1:policy-adjustment",
        )
    ]
    step = evaluate_hybrid_collective_step(
        protocol_id=protocol.id,
        candidate_set=candidate_set,
        policy=policy,
        target=target,
        current_step=2,
        scout_reports=scouts,
        existing_trails=[prior_trail(target)],
        topology=replay_topology(target),
        feedback=feedback,
        layer_proposals=layer_proposals,
        adjustment_proposals=adjustment_proposals,
        fallback_candidate_id=collective_fallback_id(protocol),
    )

    # Continue only through governance-issued replay memory. Re-submitting the
    # same feedback and adjustment identities is a traced, validated no-op;
    # raw processed-id sets and parallel trail snapshots carry no authority.
    replay_step = evaluate_hybrid_collective_step(
        protocol_id=protocol.id,
        candidate_set=candidate_set,
        policy=policy,
        target=target,
        current_step=2,
        scout_reports=scouts,
        topology=replay_topology(target),
        feedback=feedback,
        layer_proposals=layer_proposals,
        adjustment_proposals=adjustment_proposals,
        replay_state=replay_state_from_hybrid_step(step),
        fallback_candidate_id=collective_fallback_id(protocol),
    )
    replayed_feedback_ids = [
        event.lineage["source_trace_event_id"]
        for event in replay_step.trace_events
        if event.event_type == "pheromone_observe"
        and event.lineage.get("lifecycle") == "feedback"
        and event.lineage.get("result") == "replay_ignored"
    ]
    decision_events = [
        event
        for event in replay_step.trace_events
        if event.event_type in {"commit", "fallback"}
    ]
    authority_retained = (
        len(decision_events) == 1
        and replay_step.decision.committed
        and candidate_set.require_declared_for_target(
            replay_step.decision.candidate_id, target
        ).id
        == replay_step.decision.candidate_id
    )
    return {
        "protocol_id": protocol.id,
        "feedback_count": len(feedback),
        "reinforced": [
            {
                "candidate_id": trail.candidate_id,
                "subject_type": trail.subject_type,
                "subject_id": trail.subject_id,
                "kind": trail.kind,
                "strength": trail.strength,
            }
            for trail in step.active_trails
        ],
        "layer_resolution": step.layer_coordination.resolution,
        "layer_fallback_used": step.layer_coordination.fallback_used,
        "accepted_adjustments": dict(step.adjustment_overlay),
        "decision": {
            "candidate_id": step.decision.candidate_id,
            "reason": step.decision.reason,
        },
        "trace_events": [event.event_type for event in step.trace_events],
        "replayed_feedback_ids": replayed_feedback_ids,
        "replay_reinforcement_count": len(replay_step.reinforcement_records),
        "replay_trace_events": [event.event_type for event in replay_step.trace_events],
        "authority": "governance_retained"
        if authority_retained
        else "authority_violation",
    }


def prior_trail(target: str) -> PheromoneTrail:
    return PheromoneTrail(
        candidate_id="candidate:alpha",
        subject_type="route",
        subject_id="route:alpha",
        target=target,
        kind="positive",
        strength=1.5,
        source_id="runtime:replay:alpha",
        evidence_id="evidence:alpha",
        provenance="trace-replay:episode:1",
        trace_event_id="trace:episode:1:route:alpha",
        deposited_at_step=1,
        updated_at_step=1,
    )


def replay_feedback(target: str) -> list[PheromoneFeedback]:
    return [
        PheromoneFeedback(
            source_id=item["source_id"],
            subject_type="route",
            subject_id=item["subject_id"],
            candidate_id=item["candidate_id"],
            target=target,
            outcome=item["outcome"],
            reward=item["reward"],
            strength_delta=item["strength_delta"],
            evidence_id=f"evidence:{item['subject_id']}",
            provenance="trace-replay:episode:1",
            trace_event_id=f"trace:episode:1:feedback:{item['candidate_id']}",
            step=2,
        )
        for item in REPLAY_FIXTURE
    ]


def replay_topology(target: str) -> PheromoneNeighborhood:
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


def replay_layer_proposals(target: str) -> list[LayerProposal]:
    return [
        LayerProposal(
            layer_id="learned",
            source_id="runtime:replay:learned",
            target=target,
            candidate_id="candidate:alpha",
            action="prefer_candidate",
            confidence=0.8,
            support=1.0,
            risk=0.1,
            evidence_id="evidence:alpha",
            provenance="trace-replay:episode:1:learned",
            trace_event_id="trace:episode:1:layer:learned",
        ),
        LayerProposal(
            layer_id="metacognitive",
            source_id="runtime:replay:metacognitive",
            target=target,
            candidate_id="candidate:alpha",
            action="confirm_trace_coverage",
            confidence=0.7,
            support=0.5,
            evidence_id="evidence:alpha",
            provenance="trace-replay:episode:1:metacognitive",
            trace_event_id="trace:episode:1:layer:metacognitive",
        ),
    ]


def verified_scout(source_id: str, candidate_id: str, target: str) -> ScoutReport:
    trace_id = f"trace:{source_id}"
    return ScoutReport(
        scout_id=source_id,
        candidate_id=candidate_id,
        evidence_id=f"evidence:{source_id}",
        provenance=f"trace-replay:{source_id}",
        target=target,
        trace_event_id=trace_id,
        verification=verify_signal_input(
            target=target,
            source_id=source_id,
            subject_id=candidate_id,
            verifier_id="governance:replay",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="governance:replay-verification",
            trace_event_id=f"{trace_id}:verified",
        ),
    )


def main() -> None:
    print(json.dumps(run_replay(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
