from __future__ import annotations

from dataclasses import replace

from pheroos.conformance.checks._manifest import active_target, candidate_set, exercise_candidate_id
from pheroos.conformance.report import CheckResult
from pheroos.governance import (
    Candidate,
    CandidateSet,
    EvidenceGraph,
    EvidenceNode,
    LayerCoordinationPolicy,
    LayerProposal,
    OutputContract,
    QuorumDecision,
    evaluate_collective_decision,
    evaluate_layer_coordination,
    output_authorized,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.models import CapabilityManifest, collective_fallback_id, has_hybrid_pheromone_features


def check(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.collective_decision_policy
    if not has_hybrid_pheromone_features(policy):
        return CheckResult("hybrid_authority_boundary", True)
    if policy is None:
        return CheckResult("hybrid_authority_boundary", True)
    target = active_target(manifest)
    fallback_id = collective_fallback_id(manifest.protocol)
    candidates = candidate_set(manifest)
    candidate_id = exercise_candidate_id(manifest)
    if candidate_id is None:
        return CheckResult("hybrid_authority_boundary", False, "active_target_candidates")
    layer_state = evaluate_layer_coordination(
        candidate_set=candidates,
        target=target,
        policy=LayerCoordinationPolicy(
            enabled=True,
            default_layer_weights={"learned": 1.0},
            layer_weight_bounds={"learned": (0.0, 10.0)},
            min_layer_provenance=1,
            fallback_on_unresolved_conflict=True,
        ),
        fallback_candidate_id=fallback_id,
        proposals=[
            LayerProposal(
                layer_id="learned",
                source_id="layer:learned",
                target=target,
                candidate_id=candidate_id,
                action="support",
                confidence=1.0,
                support=10.0,
                evidence_id="evidence:learned",
                provenance="runtime:learned",
                trace_event_id="trace:learned",
            )
        ],
    )
    try:
        evaluate_collective_decision(
            candidate_set=candidates,
            policy=replace(policy, layer_coordination_enabled=True, min_independent_scouts=1, quorum_threshold=1),
            target=target,
            scout_reports=[],
            layer_coordination_state=layer_state,
            fallback_candidate_id=fallback_id,
        )
    except GovernanceError:
        rejects_forged_layer_state = True
    else:
        rejects_forged_layer_state = False
    uncommitted = QuorumDecision(target=target, candidate_id=candidate_id, committed=False, reason="proposal_only")
    authorized = output_authorized(
        OutputContract(),
        uncommitted,
        EvidenceGraph([EvidenceNode("evidence:proposal", "proposal is not evidence", provenance="")]),
        [],
        publication_permission=True,
        candidate_set=candidates,
    )
    problems = []
    if not rejects_forged_layer_state:
        problems.append("forged_layer_state")
    if authorized:
        problems.append("proposal_direct_output")
    return CheckResult("hybrid_authority_boundary", not problems, ", ".join(problems))
