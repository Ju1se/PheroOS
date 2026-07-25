from pheroos.governance import (
    AuthorityLevel,
    Candidate,
    CandidateSet,
    EvidenceGraph,
    EvidenceNode,
    InhibitionSignal,
    OutputContract,
    PheromoneTrail,
    RecruitmentSignal,
    ScoutReport,
    StopResolution,
    deposit_pheromone,
    evaporate_trails,
    evaluate_collective_decision,
    output_authorized,
    pheromone_policy_from_collective,
    score_pheromone_trails_result,
    score_candidates,
    verify_signal_input,
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
            Candidate(
                id=candidate.id,
                target=candidate.target,
                safe_fallback=candidate.safe_fallback,
            )
            for candidate in protocol.candidates
        ]
    )
    trace.append(
        event(
            "explore",
            protocol.id,
            target,
            "independent scouts explored declared candidates",
            lineage={"scout_count": 2},
        )
    )

    scout_reports = [
        verified_scout("scout:a", "candidate:alpha", "evidence:a", target),
        verified_scout("scout:b", "candidate:alpha", "evidence:b", target),
    ]
    for report in scout_reports:
        trace.append(
            event(
                "scout_report",
                protocol.id,
                target,
                "scout report recorded with provenance",
                lineage={
                    "scout_id": report.scout_id,
                    "candidate_id": report.candidate_id,
                    "evidence_id": report.evidence_id,
                    "provenance": report.provenance,
                    "support": report.support,
                    "source_trace_event_id": report.trace_event_id,
                    "verification_trace_event_id": report.verification.trace_event_id,
                },
            )
        )

    recruitment = [verified_recruitment("recruit:a", "candidate:alpha", target)]
    trace.append(
        event(
            "recruit",
            protocol.id,
            target,
            "recruitment increased declared candidate support",
            lineage=signal_lineage(recruitment[0]),
        )
    )

    inhibition = [verified_inhibition("inhibit:a", "candidate:beta", target)]
    trace.append(
        event(
            "inhibit",
            protocol.id,
            target,
            "inhibition reduced declared candidate support",
            lineage=signal_lineage(inhibition[0]),
        )
    )

    pheromone_policy = pheromone_policy_from_collective(policy)
    raw_pheromones = [
        pheromone(
            "candidate:alpha",
            target,
            "positive",
            "evidence:a",
            "scout:a",
            "trace:pheromone:positive",
            strength=9,
        ),
        pheromone(
            "candidate:beta",
            target,
            "negative",
            "evidence:b",
            "scout:b",
            "trace:pheromone:negative",
        ),
        pheromone(
            "candidate:beta",
            target,
            "cautionary",
            "evidence:b",
            "scout:b",
            "trace:pheromone:cautionary",
        ),
        pheromone(
            "candidate:alpha",
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
    for trail in pheromones:
        requested = next(
            item.strength
            for item in raw_pheromones
            if item.trace_event_id == trail.trace_event_id
        )
        trace.append(
            TraceEvent(
                event_type="pheromone_deposit",
                protocol_id=protocol.id,
                target=target,
                reason="evidence-bound pheromone mark deposited",
                lineage={
                    "source_id": trail.source_id,
                    "provenance": trail.provenance,
                    "subject_type": trail.subject_type,
                    "subject_id": trail.subject_id,
                    "candidate_id": trail.candidate_id,
                    "kind": trail.kind,
                    "source_kind": trail.kind,
                    "source_strength": 0.0,
                    "old_strength": 0.0,
                    "requested_strength": requested,
                    "applied_strength": trail.strength,
                    "new_strength": trail.strength,
                    "round_budget_remaining": max(
                        0.0, pheromone_policy.per_round_deposit_cap - trail.strength
                    ),
                    "source_budget_remaining": max(
                        0.0, pheromone_policy.per_source_cap - trail.strength
                    ),
                    "step": trail.updated_at_step,
                    "deposited_at_step": trail.deposited_at_step,
                    "updated_at_step": trail.updated_at_step,
                    "source_trace_event_id": trail.trace_event_id,
                    "trace_event_id": trail.trace_event_id,
                },
            )
        )
    for before, after in zip(raw_pheromones, pheromones):
        if before.strength == after.strength:
            continue
        trace.append(
            TraceEvent(
                event_type="pheromone_clip",
                protocol_id=protocol.id,
                target=target,
                reason="pheromone mark clipped to declared bounds",
                lineage={
                    "lifecycle": "deposit",
                    "result": "applied",
                    "source_id": after.source_id,
                    "provenance": after.provenance,
                    "candidate_id": after.candidate_id,
                    "subject_type": after.subject_type,
                    "subject_id": after.subject_id,
                    "kind": after.kind,
                    "source_kind": before.kind,
                    "source_strength": 0.0,
                    "new_strength": after.strength,
                    "step": after.updated_at_step,
                    "source_trace_event_id": before.trace_event_id,
                    "trace_event_id": before.trace_event_id,
                    "requested_strength": before.strength,
                    "applied_strength": after.strength,
                    "round_budget_remaining": max(
                        0.0,
                        pheromone_policy.per_round_deposit_cap - after.strength,
                    ),
                    "source_budget_remaining": max(
                        0.0,
                        pheromone_policy.per_source_cap - after.strength,
                    ),
                },
            )
        )
    evaporated = evaporate_trails(
        pheromones,
        pheromone_policy,
        current_step=1,
    )
    for before, after in zip(pheromones, evaporated):
        if after.kind == "stale":
            continue
        trace.append(
            TraceEvent(
                event_type="pheromone_evaporate",
                protocol_id=protocol.id,
                target=target,
                reason="pheromone support decayed",
                lineage={
                    "source_id": after.source_id,
                    "provenance": after.provenance,
                    "subject_type": after.subject_type,
                    "subject_id": after.subject_id,
                    "kind": before.kind,
                    "source_kind": before.kind,
                    "source_strength": before.strength,
                    "old_strength": before.strength,
                    "requested_strength": before.strength,
                    "applied_strength": after.strength,
                    "new_strength": after.strength,
                    "strength_delta": after.strength - before.strength,
                    "elapsed_steps": 1,
                    "step": after.updated_at_step,
                    "source_updated_at_step": before.updated_at_step,
                    "deposited_at_step": before.deposited_at_step,
                    "profile": before.kind,
                    "candidate_id": before.candidate_id,
                    "source_trace_event_id": before.trace_event_id,
                    "trace_event_id": after.trace_event_id,
                },
            )
        )
    for before, after in zip(pheromones, evaporated):
        if after.kind != "stale":
            continue
        trace.append(
            TraceEvent(
                event_type="pheromone_expire",
                protocol_id=protocol.id,
                target=target,
                reason="expired pheromone represented as stale memory",
                lineage={
                    "action": "expire",
                    "target": target,
                    "candidate_id": after.candidate_id,
                    "subject_type": after.subject_type,
                    "subject_id": after.subject_id,
                    "kind": "stale",
                    "source_kind": before.kind,
                    "source_id": after.source_id,
                    "provenance": after.provenance,
                    "source_trace_event_id": after.trace_event_id,
                    "trace_event_id": after.trace_event_id,
                    "old_strength": before.strength,
                    "source_strength": before.strength,
                    "requested_strength": before.strength,
                    "applied_strength": after.strength,
                    "new_strength": after.strength,
                    "strength_delta": after.strength - before.strength,
                    "step": after.updated_at_step,
                    "source_updated_at_step": before.updated_at_step,
                    "deposited_at_step": before.deposited_at_step,
                    "ttl_steps": before.ttl_steps,
                    "elapsed_steps": 1,
                },
            )
        )

    pheromone_result = score_pheromone_trails_result(
        candidate_set=candidates,
        trails=evaporated,
        policy=pheromone_policy,
    )
    state = score_candidates(
        candidate_set=candidates,
        policy=policy,
        target=target,
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
            lineage={
                "scores": dict(state.scores),
                "score_breakdown": {
                    candidate_id: dict(categories)
                    for candidate_id, categories in state.score_breakdown.items()
                },
                "scout_diversity": {
                    candidate_id: len(scouts)
                    for candidate_id, scouts in state.independent_scouts.items()
                },
                "pheromone_source_diversity": dict(state.pheromone_source_diversity),
            },
        )
    )
    trace.append(
        TraceEvent(
            event_type="pheromone_score",
            protocol_id=protocol.id,
            target=target,
            reason="pheromone score contributions computed",
            lineage={
                "scores": dict(pheromone_result.scores),
                "score_breakdown": {
                    candidate_id: dict(categories)
                    for candidate_id, categories in pheromone_result.score_breakdown.items()
                },
                "kind_breakdown": {
                    candidate_id: dict(categories)
                    for candidate_id, categories in pheromone_result.kind_breakdown.items()
                },
                "subject_breakdown": {
                    candidate_id: dict(categories)
                    for candidate_id, categories in pheromone_result.subject_breakdown.items()
                },
                "active_trails": [
                    {
                        "trace_event_id": trail.trace_event_id,
                        "source_id": trail.source_id,
                        "candidate_id": trail.candidate_id,
                        "subject_type": trail.subject_type,
                        "subject_id": trail.subject_id,
                        "kind": trail.kind,
                        "source_kind": next(
                            (
                                item.kind
                                for item in pheromones
                                if item.trace_event_id == trail.trace_event_id
                            ),
                            trail.kind,
                        ),
                        "strength": trail.strength,
                        "provenance": trail.provenance,
                        "deposited_at_step": trail.deposited_at_step,
                        "updated_at_step": trail.updated_at_step,
                        "ttl_steps": trail.ttl_steps,
                    }
                    for trail in evaporated
                ],
                "current_step": 1,
                "source_diversity": dict(state.pheromone_source_diversity),
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
    trace.append(
        event(
            "consensus_check",
            protocol.id,
            target,
            "collective consensus evaluated",
            lineage={
                "quorum_threshold": policy.quorum_threshold,
                "min_independent_scouts": policy.min_independent_scouts,
            },
        )
    )
    decision_event = "fallback" if "fallback" in decision.reason else "commit"
    trace.append(
        event(
            decision_event,
            protocol.id,
            target,
            decision.reason,
            lineage={
                "target": target,
                "candidate_id": decision.candidate_id,
                "decision_reason": decision.reason,
                "upstream_score_lineage": ["candidate_score:collective"],
            },
        )
    )

    stop_resolution = StopResolution(target=target, action="publish", blocked=False)
    trace.append(event("block", protocol.id, target, "stop resolution permits output"))

    evidence = EvidenceGraph(
        [
            EvidenceNode(
                id=report.evidence_id,
                content=report.candidate_id,
                provenance=report.provenance,
            )
            for report in scout_reports
        ]
    )
    contract = OutputContract(
        committed_candidate_required=protocol.output_policy.requires_committed_candidate,
        evidence_required=protocol.output_policy.requires_evidence_contract,
        stop_resolution_required=protocol.output_policy.requires_stop_resolution,
        publication_permission_required=protocol.output_policy.requires_publication_permission,
    )
    authorized = output_authorized(
        contract,
        decision,
        evidence,
        [stop_resolution],
        publication_permission=True,
        candidate_set=candidates,
    )
    trace.append(
        event(
            "output",
            protocol.id,
            target,
            "output authorized by collective contract",
            lineage={
                "committed_candidate": decision.committed,
                "evidence_provenance": evidence.has_evidence()
                and evidence.has_provenance(),
                "stop_resolution": not stop_resolution.blocked,
                "publication_permission": True,
                "authorized": authorized,
            },
        )
    )

    assert decision.candidate_id == "candidate:alpha"
    assert authorized is True
    path_alternative = "commit" if decision_event == "fallback" else "fallback"
    actual_required = set(protocol.trace_policy.required_events) - {
        path_alternative,
        "recovery",
    }
    assert trace.require_events(actual_required) == []
    observed = {item.event_type for item in trace.events}
    assert path_alternative not in observed
    assert "recovery" not in observed


def event(
    event_type: str,
    protocol_id: str,
    target: str,
    reason: str,
    *,
    lineage: dict[str, object] | None = None,
) -> TraceEvent:
    return TraceEvent(
        event_type=event_type,
        protocol_id=protocol_id,
        target=target,
        reason=reason,
        lineage=lineage or {},
    )


def verified_scout(
    source_id: str,
    candidate_id: str,
    evidence_id: str,
    target: str,
) -> ScoutReport:
    trace_event_id = f"trace:{source_id}"
    return ScoutReport(
        source_id,
        candidate_id,
        evidence_id,
        f"runtime:{source_id}",
        target=target,
        trace_event_id=trace_event_id,
        verification=verification(
            target, source_id, candidate_id, f"{trace_event_id}:verified"
        ),
    )


def verified_recruitment(
    source_id: str, candidate_id: str, target: str
) -> RecruitmentSignal:
    trace_event_id = f"trace:{source_id}"
    return RecruitmentSignal(
        source_id,
        candidate_id,
        strength=1,
        target=target,
        provenance=f"runtime:{source_id}",
        trace_event_id=trace_event_id,
        verification=verification(
            target, source_id, candidate_id, f"{trace_event_id}:verified"
        ),
    )


def verified_inhibition(
    source_id: str, candidate_id: str, target: str
) -> InhibitionSignal:
    trace_event_id = f"trace:{source_id}"
    return InhibitionSignal(
        source_id,
        candidate_id,
        strength=1,
        target=target,
        provenance=f"runtime:{source_id}",
        trace_event_id=trace_event_id,
        verification=verification(
            target, source_id, candidate_id, f"{trace_event_id}:verified"
        ),
    )


def verification(
    target: str, source_id: str, candidate_id: str, trace_event_id: str
) -> object:
    return verify_signal_input(
        target=target,
        source_id=source_id,
        subject_id=candidate_id,
        verifier_id="governance:swarm-example",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="governance:swarm-example",
        trace_event_id=trace_event_id,
    )


def signal_lineage(signal: RecruitmentSignal | InhibitionSignal) -> dict[str, object]:
    assert signal.verification is not None
    return {
        "source_id": signal.source_id,
        "candidate_id": signal.candidate_id,
        "strength": signal.strength,
        "provenance": signal.provenance,
        "source_trace_event_id": signal.trace_event_id,
        "verification_trace_event_id": signal.verification.trace_event_id,
    }


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
