from dataclasses import replace

import pytest

from pheroos.governance import (
    AuthorityLevel,
    Candidate,
    CandidateSet,
    EvidenceGraph,
    EvidenceNode,
    InhibitionSignal,
    LayerCoordinationState,
    RecruitmentSignal,
    ScoutReport,
    SignalVerification,
    score_candidates,
    verify_signal_input,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol import CollectiveDecisionPolicy
from pheroos.protocol.models import PheromoneKindProfile


TARGET = "decision:hybrid"


@pytest.mark.parametrize("mode", ["bee_swarm", "ant_colony", "hybrid"])
def test_all_swarm_collective_inputs_require_governance_verification(mode: str) -> None:
    active_policy = (
        policy()
        if mode == "hybrid"
        else CollectiveDecisionPolicy(
            mode=mode,
            min_independent_scouts=1,
            quorum_threshold=1,
            fallback_candidate="candidate:fallback",
        )
    )
    with pytest.raises(GovernanceError, match="not governance-verified"):
        score_candidates(
            candidate_set=candidates(),
            policy=active_policy,
            target=TARGET,
            scout_reports=[
                ScoutReport(
                    "scout:a",
                    "candidate:alpha",
                    "evidence:a",
                    "driver:a",
                    target=TARGET,
                    trace_event_id="trace:scout:a",
                )
            ],
        )


def test_verified_hybrid_scout_recruitment_and_inhibition_are_scored() -> None:
    state = score_candidates(
        candidate_set=candidates(),
        policy=policy(
            recruitment_enabled=True,
            inhibition_enabled=True,
            quorum_threshold=2,
        ),
        target=TARGET,
        scout_reports=[verified_scout("scout:a", "candidate:alpha")],
        recruitment_signals=[verified_recruitment("recruit:a", "candidate:alpha", 2.0)],
        inhibition_signals=[verified_inhibition("inhibit:a", "candidate:alpha", 0.5)],
    )

    assert state.scores["candidate:alpha"] == 2.5
    assert state.independent_scouts["candidate:alpha"] == {"scout:a"}
    with pytest.raises(TypeError):
        state.scores["candidate:alpha"] = 100.0
    with pytest.raises(AttributeError):
        state.independent_scouts["candidate:alpha"].add("scout:forged")


def test_direct_verification_record_cannot_forge_hybrid_authority() -> None:
    forged = SignalVerification(
        target=TARGET,
        source_id="scout:self-asserted",
        subject_id="candidate:alpha",
        verifier_id="scout:self-asserted",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="agent:self-assertion",
        trace_event_id="trace:self-assertion",
    )

    with pytest.raises(GovernanceError, match="not governance-verified"):
        score_candidates(
            candidate_set=candidates(),
            policy=policy(),
            target=TARGET,
            scout_reports=[
                ScoutReport(
                    "scout:self-asserted",
                    "candidate:alpha",
                    "evidence:self-asserted",
                    "agent:self-assertion",
                    target=TARGET,
                    trace_event_id="trace:self-assertion",
                    verification=forged,
                )
            ],
        )


@pytest.mark.parametrize(
    "report",
    [
        ScoutReport("", "candidate:alpha", "evidence:a", "driver:a", target=TARGET),
        ScoutReport("scout:a", "candidate:alpha", "", "driver:a", target=TARGET),
        ScoutReport("scout:a", "candidate:alpha", "evidence:a", "", target=TARGET),
    ],
)
def test_invalid_scout_identity_or_evidence_fails_closed(report: ScoutReport) -> None:
    with pytest.raises(GovernanceError):
        score_candidates(
            candidate_set=candidates(),
            policy=policy(),
            target=TARGET,
            scout_reports=[report],
        )


def test_duplicate_verified_scout_identity_is_rejected() -> None:
    report = verified_scout("scout:a", "candidate:alpha")

    with pytest.raises(GovernanceError, match="duplicate scout"):
        score_candidates(
            candidate_set=candidates(),
            policy=policy(),
            target=TARGET,
            scout_reports=[report, report],
        )


def test_collective_inputs_reject_ambiguous_trace_lineage_ids() -> None:
    first = verified_scout("scout:trace:a", "candidate:alpha")
    second = verified_scout("scout:trace:b", "candidate:alpha")

    with pytest.raises(GovernanceError, match="duplicate collective trace_event_id"):
        score_candidates(
            candidate_set=candidates(),
            policy=policy(),
            target=TARGET,
            scout_reports=[first, replace(second, trace_event_id=first.trace_event_id)],
        )

    duplicate_verification = verify_signal_input(
        target=TARGET,
        source_id=second.scout_id,
        subject_id=second.candidate_id,
        verifier_id="governance:test",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="governance:test",
        trace_event_id=first.verification.trace_event_id,
    )
    with pytest.raises(GovernanceError, match="duplicate collective trace_event_id"):
        score_candidates(
            candidate_set=candidates(),
            policy=policy(),
            target=TARGET,
            scout_reports=[first, replace(second, verification=duplicate_verification)],
        )

    recruitment = verified_recruitment("recruit:trace", "candidate:alpha", 1.0)
    with pytest.raises(GovernanceError, match="duplicate collective trace_event_id"):
        score_candidates(
            candidate_set=candidates(),
            policy=policy(recruitment_enabled=True),
            target=TARGET,
            scout_reports=[first],
            recruitment_signals=[
                replace(recruitment, trace_event_id=first.trace_event_id)
            ],
        )


def test_hybrid_signal_strength_cannot_exceed_declared_collective_bound() -> None:
    report = replace(
        verified_scout("scout:a", "candidate:alpha"),
        support=1.01,
    )

    with pytest.raises(
        GovernanceError, match="exceeds the declared collective threshold bound"
    ):
        score_candidates(
            candidate_set=candidates(),
            policy=policy(quorum_threshold=1),
            target=TARGET,
            scout_reports=[report],
        )


def test_direct_hybrid_policy_rejects_unreachable_activation_threshold() -> None:
    base = policy()
    positive = replace(
        base.pheromone_kind_profiles["positive"],
        response_model="threshold",
    )
    unreachable = replace(
        base,
        pheromone_kind_profiles={"positive": positive},
        pheromone_activation_threshold=base.pheromone_max_strength + 1,
    )

    with pytest.raises(GovernanceError, match="activation_threshold cannot be reached"):
        score_candidates(
            candidate_set=candidates(),
            policy=unreachable,
            target=TARGET,
            scout_reports=[verified_scout("scout:a", "candidate:alpha")],
        )


@pytest.mark.parametrize(
    "field_name", ["target", "source_id", "subject_id", "verifier_id"]
)
def test_signal_verification_rejects_whitespace_identity(field_name: str) -> None:
    values = {
        "target": TARGET,
        "source_id": "scout:a",
        "subject_id": "candidate:alpha",
        "verifier_id": "governance:hybrid",
        "authority": AuthorityLevel.GOVERNANCE,
        "provenance": "governance:verification",
        "trace_event_id": "trace:verification",
    }
    values[field_name] = "   "

    with pytest.raises(GovernanceError, match="signal verification is missing"):
        verify_signal_input(**values)


def test_caller_constructed_layer_state_cannot_inject_hybrid_score() -> None:
    forged = LayerCoordinationState(
        score_breakdown={"candidate:alpha": {"layer_learned": 1_000_000.0}},
        selected_candidate="candidate:alpha",
        resolution="caller_claimed",
    )

    with pytest.raises(GovernanceError, match="not authoritative"):
        score_candidates(
            candidate_set=candidates(),
            policy=policy(layer_coordination_enabled=True),
            target=TARGET,
            scout_reports=[verified_scout("scout:a", "candidate:alpha")],
            layer_coordination_state=forged,
        )


def test_governance_records_snapshot_caller_owned_collections() -> None:
    candidate_items = [Candidate("candidate:alpha", TARGET)]
    evidence_items = [EvidenceNode("evidence:a", "content", "driver:a")]
    candidate_set = CandidateSet(candidate_items)
    evidence = EvidenceGraph(evidence_items)

    candidate_items.append(Candidate("candidate:forged", TARGET))
    evidence_items.clear()

    assert [candidate.id for candidate in candidate_set.candidates] == [
        "candidate:alpha"
    ]
    assert [node.id for node in evidence.nodes] == ["evidence:a"]
    with pytest.raises(AttributeError):
        candidate_set.candidates.append(Candidate("candidate:forged", TARGET))
    with pytest.raises(AttributeError):
        evidence.nodes.append(
            EvidenceNode("evidence:forged", "content", "driver:forged")
        )


@pytest.mark.parametrize(
    "items",
    [
        [Candidate("   ", TARGET)],
        [Candidate("candidate:alpha", "   ")],
        [
            Candidate("candidate:alpha", TARGET),
            Candidate("candidate:alpha", TARGET),
        ],
    ],
)
def test_candidate_set_rejects_ambiguous_or_blank_declarations(items) -> None:
    with pytest.raises(GovernanceError):
        CandidateSet(items)


def candidates() -> CandidateSet:
    return CandidateSet(
        [
            Candidate("candidate:alpha", TARGET),
            Candidate("candidate:beta", TARGET),
            Candidate("candidate:fallback", TARGET, safe_fallback=True),
        ]
    )


def policy(**changes: object) -> CollectiveDecisionPolicy:
    base = CollectiveDecisionPolicy(
        mode="hybrid",
        min_independent_scouts=1,
        quorum_threshold=1,
        pheromone_enabled=True,
        pheromone_kind_profiles={
            "positive": PheromoneKindProfile(
                weight=1.0,
                scored_subject_types=["candidate"],
            )
        },
        pheromone_diffusion_enabled=True,
        pheromone_diffusion_max_hops=1,
        pheromone_diffusion_attenuation=0.5,
        pheromone_feedback_enabled=True,
        layer_coordination_enabled=True,
        layer_weight_bounds={
            layer_id: (0.0, 1.0)
            for layer_id in ("reactive", "learned", "evolutionary", "metacognitive")
        },
        layer_default_weights={
            layer_id: 1.0
            for layer_id in ("reactive", "learned", "evolutionary", "metacognitive")
        },
        layer_confidence_thresholds={
            layer_id: 0.5
            for layer_id in ("reactive", "learned", "evolutionary", "metacognitive")
        },
        policy_adjustment_bounds={"pheromone_positive_weight": (0.0, 2.0)},
        fallback_candidate="candidate:fallback",
    )
    return replace(base, **changes)


def verified_scout(source_id: str, candidate_id: str) -> ScoutReport:
    trace_id = f"trace:{source_id}"
    return ScoutReport(
        scout_id=source_id,
        candidate_id=candidate_id,
        evidence_id=f"evidence:{source_id}",
        provenance=f"driver:{source_id}",
        target=TARGET,
        trace_event_id=trace_id,
        verification=verification(source_id, candidate_id, trace_id),
    )


def verified_recruitment(
    source_id: str, candidate_id: str, strength: float
) -> RecruitmentSignal:
    trace_id = f"trace:{source_id}"
    return RecruitmentSignal(
        source_id=source_id,
        candidate_id=candidate_id,
        strength=strength,
        target=TARGET,
        provenance=f"governance:{source_id}",
        trace_event_id=trace_id,
        verification=verification(source_id, candidate_id, trace_id),
    )


def verified_inhibition(
    source_id: str, candidate_id: str, strength: float
) -> InhibitionSignal:
    trace_id = f"trace:{source_id}"
    return InhibitionSignal(
        source_id=source_id,
        candidate_id=candidate_id,
        strength=strength,
        target=TARGET,
        provenance=f"governance:{source_id}",
        trace_event_id=trace_id,
        verification=verification(source_id, candidate_id, trace_id),
    )


def verification(source_id: str, candidate_id: str, trace_id: str):
    return verify_signal_input(
        target=TARGET,
        source_id=source_id,
        subject_id=candidate_id,
        verifier_id="governance:hybrid",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="governance:hybrid-verification",
        trace_event_id=f"{trace_id}:verified",
    )
