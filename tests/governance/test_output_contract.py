import pytest

from pheroos.governance import (
    Candidate,
    CandidateSet,
    EvidenceGraph,
    EvidenceNode,
    OutputContract,
    QuorumDecision,
    StopResolution,
    commit_candidate,
    evaluate_quorum_decision,
    evaluate_output_authorization,
    output_authorized,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.quorum import quorum_decision_is_authoritative
from pheroos.protocol import QuorumPolicy


def candidates() -> CandidateSet:
    return CandidateSet(
        [
            Candidate("candidate:accept", "decision:review"),
            Candidate("candidate:fallback", "decision:review", safe_fallback=True),
        ]
    )


def committed(candidate_id: str = "candidate:accept") -> QuorumDecision:
    return commit_candidate(
        candidate_set=candidates(),
        candidate_id=candidate_id,
        target="decision:review",
    )


def test_output_requires_candidate_evidence_stop_resolution_and_permission() -> None:
    contract = OutputContract()
    decision = committed()
    evidence = EvidenceGraph(nodes=[EvidenceNode(id="e1", content="Claim", provenance="source")])

    assert output_authorized(
        contract,
        decision,
        evidence,
        [],
        publication_permission=True,
        candidate_set=candidates(),
    ) is False
    assert output_authorized(
        contract,
        decision,
        evidence,
        [StopResolution(target="decision:review", action="publish", blocked=False)],
        publication_permission=True,
        candidate_set=candidates(),
    ) is True
    assert output_authorized(
        contract,
        decision,
        evidence,
        [StopResolution(target="decision:review", action="publish", blocked=True)],
        publication_permission=True,
        candidate_set=candidates(),
    ) is False


def test_output_uses_only_target_scoped_stop_resolutions() -> None:
    contract = OutputContract()
    decision = committed()
    evidence = EvidenceGraph(nodes=[EvidenceNode(id="e1", content="Claim", provenance="source")])

    assert output_authorized(
        contract,
        decision,
        evidence,
        [StopResolution(target="decision:other", action="publish", blocked=False)],
        publication_permission=True,
        candidate_set=candidates(),
    ) is False
    assert output_authorized(
        contract,
        decision,
        evidence,
        [
            StopResolution(target="decision:other", action="publish", blocked=True),
            StopResolution(target="decision:review", action="publish", blocked=False),
        ],
        publication_permission=True,
        candidate_set=candidates(),
    ) is True
    assert output_authorized(
        contract,
        decision,
        evidence,
        [StopResolution(target="decision:review", action="", blocked=False)],
        publication_permission=True,
        candidate_set=candidates(),
    ) is False


def test_output_denied_when_evidence_provenance_is_missing() -> None:
    contract = OutputContract()
    decision = committed()
    evidence = EvidenceGraph(nodes=[EvidenceNode(id="e1", content="Claim", provenance="")])

    assert output_authorized(
        contract,
        decision,
        evidence,
        [StopResolution(target="decision:review", action="publish", blocked=False)],
        publication_permission=True,
        candidate_set=candidates(),
    ) is False


def test_output_denied_when_required_evidence_is_empty() -> None:
    contract = OutputContract()
    decision = committed()

    assert output_authorized(
        contract,
        decision,
        EvidenceGraph(),
        [StopResolution(target="decision:review", action="publish", blocked=False)],
        publication_permission=True,
        candidate_set=candidates(),
    ) is False


def test_pheromone_score_cannot_authorize_uncommitted_output() -> None:
    contract = OutputContract()
    pheromone_only_decision = QuorumDecision(
        target="decision:review",
        candidate_id="candidate:accept",
        committed=False,
        reason="pheromone_score_only",
    )
    evidence = EvidenceGraph(nodes=[EvidenceNode(id="e1", content="Claim", provenance="source")])

    assert output_authorized(
        contract,
        pheromone_only_decision,
        evidence,
        [StopResolution(target="decision:review", action="publish", blocked=False)],
        publication_permission=True,
        candidate_set=candidates(),
    ) is False


@pytest.mark.parametrize(
    "disabled_gate",
    [
        "committed_candidate_required",
        "evidence_required",
        "stop_resolution_required",
        "publication_permission_required",
    ],
)
def test_output_contract_rejects_disabling_any_gate(disabled_gate: str) -> None:
    with pytest.raises(GovernanceError, match="cannot be disabled"):
        OutputContract(**{disabled_gate: False})


@pytest.mark.parametrize("candidate_id", ["candidate:accept", "candidate:undeclared"])
def test_caller_constructed_committed_decision_cannot_forge_output_authority(
    candidate_id: str,
) -> None:
    forged = QuorumDecision(
        target="decision:review",
        candidate_id=candidate_id,
        committed=True,
        reason="caller_claimed_commit",
    )

    assert output_authorized(
        OutputContract(),
        forged,
        EvidenceGraph([EvidenceNode("e1", "Claim", "source")]),
        [StopResolution("decision:review", "publish", blocked=False)],
        publication_permission=True,
        candidate_set=candidates(),
    ) is False


@pytest.mark.parametrize(
    ("field_name", "tampered_value"),
    [
        ("target", "decision:forged"),
        ("candidate_id", "candidate:fallback"),
        ("committed", True),
        ("reason", "caller_rewrote_governance_reason"),
    ],
)
def test_issued_quorum_decision_snapshot_rejects_every_field_mutation(
    field_name: str,
    tampered_value: object,
) -> None:
    if field_name == "committed":
        decision = commit_candidate(
            candidate_set=candidates(),
            candidate_id="candidate:accept",
            target="decision:review",
            stop_resolutions=[
                StopResolution(target="decision:review", action="publish", blocked=True)
            ],
        )
        assert decision.committed is False
    else:
        decision = committed()
    object.__setattr__(decision, field_name, tampered_value)

    assert quorum_decision_is_authoritative(decision) is False
    assert output_authorized(
        OutputContract(),
        decision,
        EvidenceGraph([EvidenceNode("e1", "Claim", "source")]),
        [StopResolution(decision.target, "publish", blocked=False)],
        publication_permission=True,
        candidate_set=candidates(),
    ) is False


def test_output_requires_protocol_candidate_set_binding() -> None:
    assert output_authorized(
        OutputContract(),
        committed(),
        EvidenceGraph([EvidenceNode("e1", "Claim", "source")]),
        [StopResolution("decision:review", "publish", blocked=False)],
        publication_permission=True,
    ) is False


def test_safe_fallback_passes_the_same_four_output_gates() -> None:
    fallback = evaluate_quorum_decision(
        candidate_set=candidates(),
        policy=QuorumPolicy(
            target="decision:review",
            fallback_candidate="candidate:fallback",
            commit_threshold=1,
        ),
        signals=[],
    )
    evidence = EvidenceGraph([EvidenceNode("e1", "Claim", "source")])
    resolution = [StopResolution("decision:review", "publish", blocked=False)]

    assert output_authorized(
        OutputContract(),
        fallback,
        evidence,
        resolution,
        publication_permission=True,
        candidate_set=candidates(),
    ) is True
    assert output_authorized(
        OutputContract(),
        fallback,
        evidence,
        resolution,
        publication_permission=False,
        candidate_set=candidates(),
    ) is False


def test_output_denied_without_publication_permission() -> None:
    contract = OutputContract()
    decision = committed()
    evidence = EvidenceGraph(nodes=[EvidenceNode(id="e1", content="Claim", provenance="source")])

    assert output_authorized(
        contract,
        decision,
        evidence,
        [StopResolution(target="decision:review", action="publish", blocked=False)],
        publication_permission=False,
        candidate_set=candidates(),
    ) is False


@pytest.mark.parametrize("publication_permission", [1, "yes", object()])
def test_output_permission_must_be_literal_boolean_true(
    publication_permission: object,
) -> None:
    assert output_authorized(
        OutputContract(),
        committed(),
        EvidenceGraph([EvidenceNode("e1", "Claim", "source")]),
        [StopResolution("decision:review", "publish", blocked=False)],
        publication_permission=publication_permission,
        candidate_set=candidates(),
    ) is False


def test_output_rejects_malformed_evidence_and_stop_resolution_records() -> None:
    assert output_authorized(
        OutputContract(),
        committed(),
        EvidenceGraph([EvidenceNode("", "", True)]),
        [StopResolution("decision:review", "publish", blocked=False)],
        publication_permission=True,
        candidate_set=candidates(),
    ) is False
    assert output_authorized(
        OutputContract(),
        committed(),
        EvidenceGraph([EvidenceNode("e1", "Claim", "source")]),
        [StopResolution("decision:review", 1, blocked=0)],
        publication_permission=True,
        candidate_set=candidates(),
    ) is False


def test_output_authorization_result_carries_canonical_four_gate_trace() -> None:
    decision = committed()
    result = evaluate_output_authorization(
        OutputContract(),
        decision,
        EvidenceGraph(nodes=[EvidenceNode(id="e1", content="Claim", provenance="source")]),
        [StopResolution(target="decision:review", action="publish", blocked=False)],
        publication_permission=True,
        protocol_id="protocol:test",
        candidate_set=candidates(),
    )

    assert result.authorized is True
    assert result.trace_event.event_type == "output"
    assert result.trace_event.lineage == {
        "committed_candidate": True,
        "evidence_provenance": True,
        "stop_resolution": True,
        "publication_permission": True,
        "authorized": True,
    }
