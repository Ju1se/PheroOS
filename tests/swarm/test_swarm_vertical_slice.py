from pheroos.governance import (
    Candidate,
    CandidateSet,
    EvidenceGraph,
    EvidenceNode,
    InhibitionSignal,
    OutputContract,
    PheromonePolicy,
    PheromoneTrail,
    RecruitmentSignal,
    RecoveryTrace,
    ScoutReport,
    StopResolution,
    evaporate_trails,
    evaluate_collective_decision,
    output_authorized,
    score_candidates,
)
from pheroos.protocol import load_capability_manifest, validate_capability_manifest
from pheroos.trace import InMemoryTraceStore, TraceEvent


def test_provider_free_swarm_collective_vertical_slice() -> None:
    manifest = load_capability_manifest("examples/swarm-protocol/capability.json")
    protocol = manifest.protocol
    policy = protocol.collective_decision_policy
    target = protocol.quorum_policy.target
    trace = InMemoryTraceStore()

    assert policy is not None
    assert validate_capability_manifest(manifest) == []

    candidates = CandidateSet(
        [
            Candidate(id=candidate.id, target=candidate.target, safe_fallback=candidate.safe_fallback)
            for candidate in protocol.candidates
        ]
    )
    trace.append(event("explore", protocol.id, target, "independent scouts explored declared candidates"))

    scout_reports = [
        ScoutReport("scout:a", "candidate:alpha", "evidence:a", "scout:a"),
        ScoutReport("scout:b", "candidate:alpha", "evidence:b", "scout:b"),
    ]
    trace.append(event("scout_report", protocol.id, target, "scout reports recorded with provenance"))

    recruitment = [RecruitmentSignal("recruit:a", "candidate:alpha", strength=1)]
    trace.append(event("recruit", protocol.id, target, "recruitment increased declared candidate support"))

    inhibition = [InhibitionSignal("inhibit:a", "candidate:beta", strength=1)]
    trace.append(event("inhibit", protocol.id, target, "inhibition reduced declared candidate support"))

    pheromones = [PheromoneTrail("candidate:alpha", strength=1)]
    trace.append(event("pheromone_deposit", protocol.id, target, "pheromone support deposited"))
    evaporated = evaporate_trails(
        pheromones,
        PheromonePolicy(enabled=policy.pheromone_enabled, evaporation_rate=policy.pheromone_evaporation_rate),
    )
    trace.append(event("pheromone_evaporate", protocol.id, target, "pheromone support decayed"))

    state = score_candidates(
        candidate_set=candidates,
        policy=policy,
        scout_reports=scout_reports,
        recruitment_signals=recruitment,
        inhibition_signals=inhibition,
        pheromone_trails=evaporated,
    )
    trace.append(
        TraceEvent(
            event_type="candidate_score",
            protocol_id=protocol.id,
            target=target,
            reason="candidate scores computed",
            lineage={"scores": state.scores},
        )
    )

    decision = evaluate_collective_decision(
        candidate_set=candidates,
        policy=policy,
        target=target,
        scout_reports=scout_reports,
        recruitment_signals=recruitment,
        inhibition_signals=inhibition,
        pheromone_trails=evaporated,
    )
    trace.append(event("consensus_check", protocol.id, target, "collective consensus evaluated"))
    trace.append(event("fallback", protocol.id, target, "safe fallback remained declared"))
    trace.append(event("commit", protocol.id, target, decision.reason))

    stop_resolution = StopResolution(target=target, action="publish", blocked=False)
    trace.append(event("block", protocol.id, target, "stop resolution permits output"))

    recovery = protocol.recovery_protocols[0]
    recovery_trace = RecoveryTrace(
        protocol_id=recovery.id,
        trigger_target=target,
        selected_roles=recovery.allowed_roles,
        selected_tags=recovery.allowed_tags,
        selected_tools=recovery.required_tools,
        success=True,
        failure_candidate=recovery.failure_candidate,
    )
    trace.append(
        TraceEvent(
            event_type="recovery",
            protocol_id=protocol.id,
            target=target,
            reason="declared recovery path available",
            lineage={"recovery": recovery_trace.protocol_id},
        )
    )

    evidence = EvidenceGraph(
        [
            EvidenceNode(id=report.evidence_id, content=report.candidate_id, provenance=report.provenance)
            for report in scout_reports
        ]
    )
    contract = OutputContract(
        committed_candidate_required=protocol.output_policy.requires_committed_candidate,
        evidence_required=protocol.output_policy.requires_evidence_contract,
        publication_permission_required=protocol.output_policy.requires_publication_permission,
    )
    authorized = output_authorized(contract, decision, evidence, [stop_resolution], publication_permission=True)
    trace.append(event("output", protocol.id, target, "output authorized by collective contract"))

    assert decision.candidate_id == "candidate:alpha"
    assert authorized is True
    assert trace.require_events(protocol.trace_policy.required_events) == []


def event(event_type: str, protocol_id: str, target: str, reason: str) -> TraceEvent:
    return TraceEvent(event_type=event_type, protocol_id=protocol_id, target=target, reason=reason)
