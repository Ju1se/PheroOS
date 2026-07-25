"""Characterize known Draft v1 limitations without making them guarantees.

These reproductions exist only to keep the WP-00 engineering baseline honest
while versioned replacements are implemented.  They are not Stable semantics,
must not be promoted into a schema, TCK, or Conformance profile, and should be
retired with the corresponding v1 compatibility paths.
"""

from __future__ import annotations

from hashlib import sha256

from pheroos.governance import (
    AtomicHybridCommitStatus,
    AuthorityDomain,
    AuthorityLevel,
    Candidate,
    CandidateSet,
    EvidenceGraph,
    EvidenceNode,
    GovernanceCommitBatch,
    InMemoryGovernanceStateStore,
    OutputContract,
    PreparedGovernanceTransition,
    StopResolution,
    action_permission_is_authoritative,
    action_permission_matches,
    commit_candidate,
    evaluate_hybrid_commit_step,
    finalize_hybrid_commit_transition,
    hybrid_commit_stream,
    issue_action_permission,
    output_gate_lineage,
    prepare_hybrid_commit_transition,
)
from pheroos.protocol import CommitAction, CommitAssurance
from tests.governance.test_hybrid_commit_total_evaluation import _total_request


_MANIFEST_ROOT = "sha256:" + ("1" * 64)
_COMMIT_POLICY_ROOT = "sha256:" + ("2" * 64)
_DECISION_REF = "sha256:" + ("3" * 64)


def _scope(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def test_v1_public_issuer_is_trusted_host_compatibility_only() -> None:
    """Record WP-03's legacy host-trust input; do not treat it as a credential."""

    permission = issue_action_permission(
        permission_id="permission:wp00-characterization",
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=_MANIFEST_ROOT,
        commit_policy_root=_COMMIT_POLICY_ROOT,
        protocol_id="protocol:wp00-characterization",
        run_id="run:wp00-characterization",
        target="decision:wp00-characterization",
        action=CommitAction.COMMIT,
        epoch=1,
        decision_ref=_DECISION_REF,
        certificate_ref="",
        allowed=True,
        reason_codes=("trusted_host_selected",),
        issuer_id="host:wp00-characterization",
        policy_ref="policy:wp00-characterization",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=1,
        expires_at_step=3,
        provenance="urn:wp00:trusted-host-characterization",
        trace_event_id="trace:wp00:trusted-host-characterization",
    )

    assert action_permission_is_authoritative(permission) is True
    assert action_permission_matches(
        permission,
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=_MANIFEST_ROOT,
        commit_policy_root=_COMMIT_POLICY_ROOT,
        protocol_id="protocol:wp00-characterization",
        run_id="run:wp00-characterization",
        target="decision:wp00-characterization",
        action=CommitAction.COMMIT,
        epoch=1,
        decision_ref=_DECISION_REF,
        certificate_ref="",
        current_step=2,
    )


def test_v1_baseline_output_accepts_caller_publication_boolean() -> None:
    """Record WP-04's caller boolean gate without endorsing it for vNext."""

    candidates = CandidateSet(
        [Candidate("candidate:accept", "decision:wp00-characterization")]
    )
    decision = commit_candidate(
        candidate_set=candidates,
        candidate_id="candidate:accept",
        target="decision:wp00-characterization",
    )
    evidence = EvidenceGraph(
        [EvidenceNode("evidence:wp00", "characterized claim", "urn:wp00:source")]
    )
    resolutions = [
        StopResolution(
            "decision:wp00-characterization",
            "publish",
            blocked=False,
        )
    ]

    allowed = output_gate_lineage(
        OutputContract(),
        decision,
        evidence,
        resolutions,
        publication_permission=True,
        candidate_set=candidates,
    )
    denied = output_gate_lineage(
        OutputContract(),
        decision,
        evidence,
        resolutions,
        publication_permission=False,
        candidate_set=candidates,
    )

    assert allowed == {
        "committed_candidate": True,
        "evidence_provenance": True,
        "stop_resolution": True,
        "publication_permission": True,
    }
    assert denied == {**allowed, "publication_permission": False}


def test_v1_finalize_mismatches_after_legal_successor() -> None:
    """Record WP-02's historical-finality defect on the frozen v1 path."""

    evaluation = evaluate_hybrid_commit_step(request=_total_request(stable=True))
    domain = AuthorityDomain(_scope("wp00-finalize-characterization"))
    store = InMemoryGovernanceStateStore()
    stream = hybrid_commit_stream(evaluation)
    prepared = prepare_hybrid_commit_transition(
        evaluation,
        domain=domain,
        head=store.load_head(domain.scope_ref, stream),
        transition_id="wp00-characterization:first",
    )
    first_receipt = store.atomic_commit(prepared.batch)

    successor_transition = PreparedGovernanceTransition.from_head(
        store.load_head(domain.scope_ref, stream),
        transition_id="wp00-characterization:successor",
        state_records={"characterization": "legal-successor"},
    )
    successor = GovernanceCommitBatch(
        transition=successor_transition,
        trace_records=[
            {
                "trace_id": "trace:wp00-characterization:successor",
                "scope_ref": domain.scope_ref,
                "stream": stream,
                "transition_id": successor_transition.transition_id,
                "event": "legal_successor_committed",
            }
        ],
    )
    successor_receipt = store.atomic_commit(successor)

    assert first_receipt.matches(prepared.batch) is True
    assert store.load_receipt(domain.scope_ref, prepared.transition_id) == first_receipt
    assert successor_receipt.revision == 2
    assert store.load_head(domain.scope_ref, stream).transition_id == (
        successor_transition.transition_id
    )

    result = finalize_hybrid_commit_transition(
        prepared,
        receipt=first_receipt,
        state_store=store,
    )

    assert result.status is AtomicHybridCommitStatus.INVALID
    assert result.reason_code == "governance_receipt_mismatch"
    assert dict(result.details) == {
        "receipt_matches_batch": True,
        "receipt_matches_head": False,
        "receipt_matches_store": True,
    }
    assert result.authoritative is False
    assert result.evaluation is None
    assert result.receipt is None
