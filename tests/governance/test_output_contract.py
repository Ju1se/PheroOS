from pheroos.governance import (
    EvidenceGraph,
    EvidenceNode,
    OutputContract,
    QuorumDecision,
    StopResolution,
    output_authorized,
)


def test_output_requires_candidate_evidence_stop_resolution_and_permission() -> None:
    contract = OutputContract()
    decision = QuorumDecision(
        target="decision:review",
        candidate_id="candidate:accept",
        committed=True,
        reason="declared",
    )
    evidence = EvidenceGraph(nodes=[EvidenceNode(id="e1", content="Claim", provenance="source")])

    assert output_authorized(contract, decision, evidence, [], publication_permission=True) is True
    assert output_authorized(
        contract,
        decision,
        evidence,
        [StopResolution(target="decision:review", action="publish", blocked=True)],
        publication_permission=True,
    ) is False


def test_output_denied_when_evidence_provenance_is_missing() -> None:
    contract = OutputContract()
    decision = QuorumDecision(
        target="decision:review",
        candidate_id="candidate:accept",
        committed=True,
        reason="declared",
    )
    evidence = EvidenceGraph(nodes=[EvidenceNode(id="e1", content="Claim", provenance="")])

    assert output_authorized(contract, decision, evidence, [], publication_permission=True) is False
