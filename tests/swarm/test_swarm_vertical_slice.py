from pheroos.governance import (
    Candidate,
    CandidateSet,
    EvidenceGraph,
    EvidenceNode,
    InhibitionSignal,
    OutputContract,
    PheromoneTrail,
    RecruitmentSignal,
    RecoveryTrace,
    ScoutReport,
    StopResolution,
    deposit_pheromone,
    evaporate_trails,
    evaluate_collective_decision,
    output_authorized,
    pheromone_policy_from_collective,
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

    pheromone_policy = pheromone_policy_from_collective(policy)
    raw_pheromones = [
        pheromone("candidate:alpha", target, "positive", "evidence:a", "scout:a", "trace:pheromone:positive", strength=9),
        pheromone("candidate:beta", target, "negative", "evidence:b", "scout:b", "trace:pheromone:negative"),
        pheromone("candidate:beta", target, "cautionary", "evidence:b", "scout:b", "trace:pheromone:cautionary"),
        pheromone(
            "",
            target,
            "positive",
            "evidence:a",
            "scout:a",
            "trace:pheromone:expired-route",
            subject_type="route",
            subject_id="route:expired",
            ttl_steps=1,
        ),
    ]
    pheromones = [
        deposit_pheromone(trail, pheromone_policy, candidate_set=candidates)
        for trail in raw_pheromones
    ]
    trace.append(
        TraceEvent(
            event_type="pheromone_deposit",
            protocol_id=protocol.id,
            target=target,
            reason="evidence-bound pheromone marks deposited",
            lineage={"marks": [trail.trace_event_id for trail in pheromones]},
        )
    )
    trace.append(
        TraceEvent(
            event_type="pheromone_clip",
            protocol_id=protocol.id,
            target=target,
            reason="pheromone marks clipped to declared bounds",
            lineage={
                "marks": [
                    {
                        "trace_event_id": before.trace_event_id,
                        "subject_type": after.subject_type,
                        "subject_id": after.subject_id or after.candidate_id or after.route_id or after.tool_id,
                        "kind": after.kind,
                        "old_strength": before.strength,
                        "new_strength": after.strength,
                        "source_id": after.source_id,
                        "evidence_id": after.evidence_id,
                        "step": after.updated_at_step,
                    }
                    for before, after in zip(raw_pheromones, pheromones)
                    if before.strength != after.strength
                ]
            },
        )
    )
    evaporated = evaporate_trails(
        pheromones,
        pheromone_policy,
        current_step=1,
    )
    trace.append(
        TraceEvent(
            event_type="pheromone_evaporate",
            protocol_id=protocol.id,
            target=target,
            reason="pheromone support decayed",
            lineage={"marks": [trail.trace_event_id for trail in evaporated], "strengths": [trail.strength for trail in evaporated]},
        )
    )
    trace.append(
        TraceEvent(
            event_type="pheromone_expire",
            protocol_id=protocol.id,
            target=target,
            reason="expired pheromone represented as stale memory",
            lineage={
                "marks": [
                    {
                        "trace_event_id": trail.trace_event_id,
                        "subject_type": trail.subject_type,
                        "subject_id": trail.subject_id,
                        "kind": trail.kind,
                        "old_strength": 1,
                        "new_strength": trail.strength,
                        "source_id": trail.source_id,
                        "evidence_id": trail.evidence_id,
                        "step": trail.updated_at_step,
                    }
                    for trail in evaporated
                    if trail.kind == "stale"
                ]
            },
        )
    )

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
    trace.append(
        TraceEvent(
            event_type="pheromone_score",
            protocol_id=protocol.id,
            target=target,
            reason="pheromone score contributions computed",
            lineage={
                "subjects": [
                    {
                        "subject_type": trail.subject_type,
                        "subject_id": trail.subject_id or trail.candidate_id or trail.route_id or trail.tool_id,
                        "kind": trail.kind,
                        "old_strength": 5 if trail.trace_event_id == "trace:pheromone:positive" else 1,
                        "new_strength": trail.strength,
                        "source_id": trail.source_id,
                        "evidence_id": trail.evidence_id,
                        "step": trail.updated_at_step,
                    }
                    for trail in evaporated
                ],
                "source_diversity": state.pheromone_source_diversity,
            },
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


def pheromone(
    candidate_id: str,
    target: str,
    kind: str,
    evidence_id: str,
    provenance: str,
    trace_event_id: str,
    *,
    strength: float = 1,
    subject_type: str = "candidate",
    subject_id: str = "",
    ttl_steps: int | None = None,
) -> PheromoneTrail:
    return PheromoneTrail(
        candidate_id=candidate_id,
        strength=strength,
        subject_type=subject_type,
        subject_id=subject_id or candidate_id,
        target=target,
        kind=kind,
        source_id=provenance,
        source_role="scout",
        evidence_id=evidence_id,
        provenance=provenance,
        trace_event_id=trace_event_id,
        ttl_steps=ttl_steps,
    )
