from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pheroos.governance import (
    AuthorityLevel,
    Candidate,
    CandidateSet,
    EvidenceGraph,
    EvidenceNode,
    LayerProposal,
    OutputContract,
    PheromoneEdge,
    PheromoneFeedback,
    PheromoneNeighborhood,
    PheromoneSubject,
    PheromoneTrail,
    PolicyAdjustmentProposal,
    ScoutReport,
    StopResolution,
    evaluate_hybrid_collective_step,
    evaluate_output_authorization,
    verify_signal_input,
)
from pheroos.protocol import collective_fallback_id, load_capability_manifest, validate_capability_manifest


def run_example(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parents[2]
    manifest = load_capability_manifest(root / "examples/hybrid-pheromone-protocol/capability.json")
    diagnostics = validate_capability_manifest(manifest)
    if diagnostics:
        raise ValueError([diagnostic.to_dict() for diagnostic in diagnostics])
    protocol = manifest.protocol
    policy = protocol.collective_decision_policy
    if policy is None:
        raise ValueError("Hybrid example requires a collective policy")
    target = protocol.quorum_policy.target
    candidates = CandidateSet(
        [Candidate(item.id, item.target, item.safe_fallback) for item in protocol.candidates]
    )
    scouts = [
        verified_scout("scout:alpha:a", "candidate:alpha", target),
        verified_scout("scout:alpha:b", "candidate:alpha", target),
    ]
    step = evaluate_hybrid_collective_step(
        protocol_id=protocol.id,
        candidate_set=candidates,
        policy=policy,
        target=target,
        current_step=1,
        scout_reports=scouts,
        deposits=[
            PheromoneTrail(
                candidate_id="candidate:alpha",
                strength=1.0,
                subject_type="route",
                subject_id="route:alpha",
                target=target,
                kind="positive",
                source_id="runtime:alpha",
                evidence_id="evidence:route:alpha",
                provenance="runtime:provider-free",
                trace_event_id="trace:deposit:route:alpha",
                deposited_at_step=1,
                updated_at_step=1,
            )
        ],
        topology=PheromoneNeighborhood(
            subjects=[
                PheromoneSubject("route", "route:alpha", "candidate:alpha", target),
                PheromoneSubject("candidate", "candidate:alpha", "candidate:alpha", target),
            ],
            edges=[PheromoneEdge("route", "route:alpha", "candidate", "candidate:alpha", 1.0)],
        ),
        feedback=[
            PheromoneFeedback(
                source_id="runtime:alpha",
                subject_type="route",
                subject_id="route:alpha",
                candidate_id="candidate:alpha",
                target=target,
                outcome="success",
                reward=1.0,
                strength_delta=1.0,
                evidence_id="evidence:route:alpha",
                provenance="runtime:provider-free",
                trace_event_id="trace:feedback:route:alpha",
                step=1,
            )
        ],
        layer_proposals=[
            LayerProposal(
                "learned",
                "layer:learned",
                target,
                "candidate:alpha",
                "support",
                0.9,
                support=1.0,
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
                evidence_id="evidence:metacognitive",
                provenance="runtime:metacognitive",
                trace_event_id="trace:layer:metacognitive",
            ),
        ],
        adjustment_proposals=[
            PolicyAdjustmentProposal(
                "evolutionary",
                "layer:evolutionary",
                {"pheromone_positive_weight": 1.2},
                "runtime:evolutionary",
                "trace:adjustment:evolutionary",
            )
        ],
        fallback_candidate_id=collective_fallback_id(protocol),
    )
    output = evaluate_output_authorization(
        OutputContract(
            committed_candidate_required=protocol.output_policy.requires_committed_candidate,
            evidence_required=protocol.output_policy.requires_evidence_contract,
            stop_resolution_required=protocol.output_policy.requires_stop_resolution,
            publication_permission_required=protocol.output_policy.requires_publication_permission,
        ),
        step.decision,
        EvidenceGraph(
            [EvidenceNode(item.evidence_id, item.candidate_id, item.provenance) for item in scouts]
        ),
        [StopResolution(target, "publish", blocked=False)],
        publication_permission=True,
        protocol_id=protocol.id,
        candidate_set=candidates,
    )
    return {
        "protocol_id": protocol.id,
        "decision": {
            "candidate_id": step.decision.candidate_id,
            "reason": step.decision.reason,
        },
        "authorized": output.authorized,
        "scores": dict(step.state.scores),
        "adjustment_overlay": dict(step.adjustment_overlay),
        "trace_events": [event.event_type for event in (*step.trace_events, output.trace_event)],
    }


def verified_scout(source_id: str, candidate_id: str, target: str) -> ScoutReport:
    trace_id = f"trace:{source_id}"
    return ScoutReport(
        source_id,
        candidate_id,
        f"evidence:{source_id}",
        f"runtime:{source_id}",
        target=target,
        trace_event_id=trace_id,
        verification=verify_signal_input(
            target=target,
            source_id=source_id,
            subject_id=candidate_id,
            verifier_id="governance:hybrid-example",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="governance:hybrid-example",
            trace_event_id=f"{trace_id}:verified",
        ),
    )


def main() -> None:
    print(json.dumps(run_example(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
