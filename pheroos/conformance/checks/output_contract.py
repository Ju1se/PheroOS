from __future__ import annotations

from pheroos.conformance.checks._manifest import active_target, candidate_set, exercise_candidate_id
from pheroos.conformance.report import CheckResult
from pheroos.governance.evidence import EvidenceGraph, EvidenceNode
from pheroos.governance.output import OutputContract, output_authorized
from pheroos.governance.quorum import QuorumDecision, commit_candidate
from pheroos.governance.stop_signal import StopResolution
from pheroos.protocol.models import CapabilityManifest


def check(manifest: CapabilityManifest) -> CheckResult:
    policy = manifest.protocol.output_policy
    problems: list[str] = []
    if policy.writer_may_create_facts:
        problems.append("writer_fact_creation")
    required = (
        policy.requires_committed_candidate,
        policy.requires_evidence_contract,
        policy.requires_stop_resolution,
        policy.requires_publication_permission,
    )
    if not all(required):
        problems.append("mandatory_gates")

    candidate_id = exercise_candidate_id(manifest)
    if candidate_id is None:
        problems.append("active_target_candidates")
        return CheckResult("output_contract", False, ", ".join(problems))
    target = active_target(manifest)
    contract = OutputContract()
    candidates = candidate_set(manifest)
    committed = commit_candidate(
        candidate_set=candidates,
        candidate_id=candidate_id,
        target=target,
    )
    uncommitted = QuorumDecision(target=target, candidate_id=candidate_id, committed=False, reason="conformance")
    forged = QuorumDecision(target=target, candidate_id=candidate_id, committed=True, reason="caller_claimed")
    evidence = EvidenceGraph([EvidenceNode("evidence:conformance", "provider-free", "driver:conformance")])
    resolution = StopResolution(target=target, action="publish", blocked=False, reason="resolved")

    if not output_authorized(
        contract,
        committed,
        evidence,
        [resolution],
        publication_permission=True,
        candidate_set=candidates,
    ):
        problems.append("valid_contract_rejected")
    if output_authorized(
        contract,
        uncommitted,
        evidence,
        [resolution],
        publication_permission=True,
        candidate_set=candidates,
    ):
        problems.append("missing_commit")
    if output_authorized(
        contract,
        forged,
        evidence,
        [resolution],
        publication_permission=True,
        candidate_set=candidates,
    ):
        problems.append("forged_commit")
    if output_authorized(
        contract,
        committed,
        EvidenceGraph(),
        [resolution],
        publication_permission=True,
        candidate_set=candidates,
    ):
        problems.append("missing_evidence")
    if output_authorized(
        contract,
        committed,
        evidence,
        [],
        publication_permission=True,
        candidate_set=candidates,
    ):
        problems.append("missing_stop_resolution")
    if output_authorized(
        contract,
        committed,
        evidence,
        [StopResolution(target=f"{target}:other", action="publish", blocked=False)],
        publication_permission=True,
        candidate_set=candidates,
    ):
        problems.append("wrong_target_stop_resolution")
    if output_authorized(
        contract,
        committed,
        evidence,
        [StopResolution(target=target, action="publish", blocked=True, reason="blocked")],
        publication_permission=True,
        candidate_set=candidates,
    ):
        problems.append("blocked_stop_resolution")
    if output_authorized(
        contract,
        committed,
        evidence,
        [resolution],
        publication_permission=False,
        candidate_set=candidates,
    ):
        problems.append("missing_publication_permission")

    return CheckResult("output_contract", not problems, ", ".join(problems))
