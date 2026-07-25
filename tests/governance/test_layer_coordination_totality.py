from __future__ import annotations

import pytest

from pheroos.governance.candidate import Candidate, CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.layer_coordination import (
    LayerCoordinationPolicy,
    LayerPerformanceSnapshot,
    LayerProposal,
    detect_layer_conflicts,
    proposal_score_delta,
    validate_layer_proposal,
)


TARGET = "decision:layer-totality"


def _candidates() -> CandidateSet:
    return CandidateSet(
        (
            Candidate("candidate:alpha", TARGET),
            Candidate("candidate:beta", TARGET),
            Candidate("candidate:fallback", TARGET, safe_fallback=True),
        )
    )


def _policy(*, min_layer_provenance: int = 1) -> LayerCoordinationPolicy:
    return LayerCoordinationPolicy(
        enabled=True,
        confidence_thresholds={
            "reactive": 0.5,
            "learned": 0.5,
            "evolutionary": 0.5,
            "metacognitive": 0.5,
        },
        conflict_threshold=0.1,
        emergency_override_threshold=0.8,
        min_layer_provenance=min_layer_provenance,
    )


def _proposal(
    layer_id: str,
    candidate_id: str,
    *,
    action: str = "support",
    source_id: str = "",
    evidence_id: str = "",
    support: float = 1.0,
    risk: float = 0.0,
) -> LayerProposal:
    source = source_id or f"source:{layer_id}:{candidate_id}:{action}"
    evidence = evidence_id or f"evidence:{layer_id}:{candidate_id}:{action}"
    return LayerProposal(
        layer_id=layer_id,
        source_id=source,
        target=TARGET,
        candidate_id=candidate_id,
        action=action,
        confidence=0.9,
        support=support,
        risk=risk,
        evidence_id=evidence,
        provenance="urn:test:layer-totality",
        trace_event_id=f"trace:{source}",
    )


def test_layer_proposal_requires_evidence_for_scoring_action() -> None:
    proposal = _proposal("learned", "candidate:alpha")
    object.__setattr__(proposal, "evidence_id", "")

    with pytest.raises(GovernanceError, match="missing evidence"):
        validate_layer_proposal(
            proposal,
            candidate_set=_candidates(),
            target=TARGET,
        )


def test_conflict_detection_reports_same_layer_and_operational_pressure() -> None:
    policy = _policy(min_layer_provenance=5)
    proposals = [
        _proposal("learned", "candidate:alpha"),
        _proposal("learned", "candidate:beta"),
        _proposal("reactive", "candidate:alpha", action="request_scouting"),
        _proposal(
            "metacognitive",
            "candidate:beta",
            action="fallback_pressure",
        ),
    ]

    conflicts = detect_layer_conflicts(
        proposals,
        policy,
        snapshots=[
            LayerPerformanceSnapshot(
                layer_id="learned",
                evidence_coverage=0.1,
                trace_coverage=1.0,
            )
        ],
    )

    assert {
        "fallback_pressure",
        "insufficient_evidence_coverage",
        "insufficient_layer_provenance",
        "scouting_requested",
    }.issubset(conflicts)


def test_risk_action_has_bounded_negative_score_semantics() -> None:
    proposal = _proposal(
        "learned",
        "candidate:alpha",
        action="risk",
        support=1.0,
        risk=2.0,
    )

    assert proposal_score_delta(proposal, _policy(), 1.0) == pytest.approx(-1.8)
