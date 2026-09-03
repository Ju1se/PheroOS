from __future__ import annotations

from copy import deepcopy
import json

from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.challenge import (
    ChallengeAttestation,
    ChallengeCoverage,
    ChallengeResult,
    VerifiedChallenge,
    challenge_attestation_payload,
    challenge_coverage_payload,
    verified_challenge_payload,
)
from pheroos.governance.evidence_binding import (
    EVIDENCE_BINDING_VERSION,
    EvidenceBinding,
    EvidenceGroupContribution,
    EvidenceSummary,
    SourceDomainContribution,
    evidence_binding_payload,
    evidence_summary_payload,
)
from pheroos.governance.observation import (
    CounterevidenceDisposition,
    CounterevidenceDispositionKind,
    ObservationAttestation,
    ObservationPolarity,
    VerifiedObservation,
    counterevidence_disposition_payload,
    observation_attestation_payload,
    verified_observation_payload,
)
from pheroos.governance.risk import (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
    RiskBand,
    commit_threshold_snapshot_payload,
    risk_assessment_chain_state_payload,
    risk_assessment_payload,
)
from pheroos.governance.schema import validate_commit_wire_record
from pheroos.governance.support_lease import (
    EligibleMembershipEpochState,
    EligiblePrincipal,
    EligiblePrincipalCluster,
    EligiblePrincipalSnapshot,
    SupportEquivocationFinding,
    SupportLease,
    SupportLeaseEvaluation,
    SupportLeaseProposal,
    SupportLeaseReplayReceipt,
    SupportLeaseReplayState,
    SupportLeaseRevocation,
    eligible_membership_epoch_state_payload,
    eligible_principal_snapshot_payload,
    support_lease_payload,
    support_lease_proposal_payload,
    support_lease_replay_receipt_payload,
    support_lease_replay_state_payload,
    support_lease_revocation_payload,
)
from pheroos.protocol import (
    COMMIT_WIRE_VERSION,
    CommitAssurance,
)
from pheroos.protocol.commit_wire import (
    canonical_commit_payload,
    canonical_commit_set,
    commit_payload_fingerprint,
)


PROFILE = "pheroos-commit-integrity-v1"
AUTHORITY_PROFILE = "pheroos-commit-authority-v1"
ASSURANCE = CommitAssurance.EVIDENCE_BOUND
MANIFEST_ROOT = "sha256:" + ("1" * 64)
POLICY_ROOT = "sha256:" + ("2" * 64)
CLAIM_ROOT = "sha256:" + ("3" * 64)
PAYLOAD_ROOT = "sha256:" + ("4" * 64)
PRINCIPAL_ROOT = "sha256:" + ("5" * 64)
ATTESTATION_ROOT = "sha256:" + ("6" * 64)
EXECUTION_ROOT = "sha256:" + ("7" * 64)
RESULT_ROOT = "sha256:" + ("8" * 64)
OBSERVATION_A = "sha256:" + ("a" * 64)
OBSERVATION_B = "sha256:" + ("b" * 64)
CHALLENGE_ROOT = "sha256:" + ("c" * 64)
DISPOSITION_ROOT = "sha256:" + ("d" * 64)
LEASE_A = "sha256:" + ("e" * 64)
LEASE_B = "sha256:" + ("f" * 64)
PROTOCOL_ID = "protocol:optimal"
RUN_ID = "run:schema"
TARGET = "decision:collective"
CANDIDATE = "candidate:alpha"
EPOCH = 3


def envelope(
    payload: dict[str, object],
    *,
    schema: str,
    profile: str = PROFILE,
) -> dict[str, object]:
    return json.loads(
        canonical_commit_payload(
            payload,
            schema=schema,
            profile=profile,
        )
    )


def binding_fields() -> dict[str, object]:
    return {
        "profile": PROFILE,
        "assurance": ASSURANCE,
        "manifest_root": MANIFEST_ROOT,
        "commit_policy_root": POLICY_ROOT,
        "protocol_id": PROTOCOL_ID,
        "run_id": RUN_ID,
        "target": TARGET,
        "epoch": EPOCH,
    }


def observation_records() -> tuple[
    ObservationAttestation,
    VerifiedObservation,
    CounterevidenceDisposition,
]:
    attestation = ObservationAttestation(
        observation_id="observation:alpha",
        target=TARGET,
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        principal_id="principal:alpha",
        polarity=ObservationPolarity.SUPPORT,
        independence_group="group:alpha",
        source_domain="domain:alpha",
        payload_fingerprint=PAYLOAD_ROOT,
        reported_quality_ppm=900_000,
        reported_relevance_ppm=800_000,
        reported_materiality_ppm=700_000,
        reported_criticality_ppm=100_000,
        provenance="urn:test:observation",
        nonce="nonce:observation:alpha",
        observed_at_step=1,
        expires_at_step=20,
        trace_event_id="trace:observation:alpha",
    )
    verified = VerifiedObservation(
        observation_id=attestation.observation_id,
        **binding_fields(),
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        principal_id=attestation.principal_id,
        principal_cluster_id="cluster:alpha",
        principal_verification_fingerprint=PRINCIPAL_ROOT,
        attestation_fingerprint=ATTESTATION_ROOT,
        polarity=attestation.polarity,
        independence_group=attestation.independence_group,
        source_domain=attestation.source_domain,
        payload_fingerprint=attestation.payload_fingerprint,
        quality_ppm=attestation.reported_quality_ppm,
        relevance_ppm=attestation.reported_relevance_ppm,
        materiality_ppm=attestation.reported_materiality_ppm,
        criticality_ppm=attestation.reported_criticality_ppm,
        nonce=attestation.nonce,
        observed_at_step=attestation.observed_at_step,
        verified_at_step=2,
        expires_at_step=attestation.expires_at_step,
        attestation_provenance=attestation.provenance,
        attestation_trace_event_id=attestation.trace_event_id,
        verifier_id="governance:evidence",
        authority=AuthorityLevel.GOVERNANCE,
        verification_provenance="urn:test:observation-verification",
        verification_trace_event_id="trace:observation:verified",
    )
    disposition = CounterevidenceDisposition(
        disposition_id="disposition:alpha",
        kind=CounterevidenceDispositionKind.UNRESOLVED,
        **binding_fields(),
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        counter_observation_fingerprint=OBSERVATION_B,
        rebuttal_observation_fingerprints=(),
        resolution_ref="",
        reason_codes=("awaiting_resolution",),
        verifier_id="governance:counterevidence",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=3,
        expires_at_step=20,
        provenance="urn:test:disposition",
        trace_event_id="trace:disposition:alpha",
    )
    return attestation, verified, disposition


def challenge_records() -> tuple[
    ChallengeAttestation,
    VerifiedChallenge,
    ChallengeCoverage,
]:
    attestation = ChallengeAttestation(
        challenge_id="challenge:alpha",
        target=TARGET,
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        principal_id="principal:challenger",
        category="independent_replication",
        execution_method="declared-counter-search-v1",
        execution_attestation_ref="opaque:execution:alpha",
        execution_fingerprint=EXECUTION_ROOT,
        result=ChallengeResult.NO_COUNTEREVIDENCE,
        result_fingerprint=RESULT_ROOT,
        result_observation_fingerprints=(),
        provenance="urn:test:challenge",
        nonce="nonce:challenge:alpha",
        executed_at_step=2,
        expires_at_step=20,
        trace_event_id="trace:challenge:alpha",
    )
    verified = VerifiedChallenge(
        challenge_id=attestation.challenge_id,
        **binding_fields(),
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        principal_id=attestation.principal_id,
        principal_cluster_id="cluster:challenger",
        principal_verification_fingerprint=PRINCIPAL_ROOT,
        attestation_fingerprint=ATTESTATION_ROOT,
        category=attestation.category,
        execution_method=attestation.execution_method,
        execution_attestation_ref=attestation.execution_attestation_ref,
        execution_fingerprint=attestation.execution_fingerprint,
        result=attestation.result,
        result_fingerprint=attestation.result_fingerprint,
        result_observation_fingerprints=(),
        nonce=attestation.nonce,
        executed_at_step=attestation.executed_at_step,
        verified_at_step=3,
        expires_at_step=attestation.expires_at_step,
        attestation_provenance=attestation.provenance,
        attestation_trace_event_id=attestation.trace_event_id,
        verifier_id="governance:challenge",
        authority=AuthorityLevel.GOVERNANCE,
        verification_provenance="urn:test:challenge-verification",
        verification_trace_event_id="trace:challenge:verified",
    )
    coverage = ChallengeCoverage(
        required_categories=("independent_replication",),
        covered_categories=("independent_replication",),
        missing_categories=(),
        challenge_fingerprints=(CHALLENGE_ROOT,),
    )
    return attestation, verified, coverage


def evidence_binding_record() -> EvidenceBinding:
    leaves = {
        "positive_observation_fingerprints": tuple(
            sorted((OBSERVATION_A, OBSERVATION_B))
        ),
        "counter_observation_fingerprints": (),
        "disposition_fingerprints": (),
        "challenge_fingerprints": (CHALLENGE_ROOT,),
    }
    roots = evidence_roots(leaves)
    return EvidenceBinding(
        evidence_id="evidence:alpha",
        binding_version=EVIDENCE_BINDING_VERSION,
        **binding_fields(),
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        **leaves,
        **roots,
        issuer_id="governance:evidence-binding",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=4,
        expires_at_step=20,
        provenance="urn:test:evidence-binding",
        trace_event_id="trace:evidence-binding",
    )


def evidence_roots(leaves: dict[str, object]) -> dict[str, str]:
    positive_root = commit_payload_fingerprint(
        {"observation_fingerprints": leaves["positive_observation_fingerprints"]},
        schema="pheroos-positive-evidence-leaves-v1",
        profile=PROFILE,
    )
    counter_root = commit_payload_fingerprint(
        {"observation_fingerprints": leaves["counter_observation_fingerprints"]},
        schema="pheroos-counterevidence-leaves-v1",
        profile=PROFILE,
    )
    disposition_root = commit_payload_fingerprint(
        {"disposition_fingerprints": leaves["disposition_fingerprints"]},
        schema="pheroos-counterevidence-disposition-leaves-v1",
        profile=PROFILE,
    )
    challenge_root = commit_payload_fingerprint(
        {"challenge_fingerprints": leaves["challenge_fingerprints"]},
        schema="pheroos-challenge-leaves-v1",
        profile=PROFILE,
    )
    evidence_root = commit_payload_fingerprint(
        {
            "assurance": ASSURANCE,
            "binding_version": EVIDENCE_BINDING_VERSION,
            "candidate_id": CANDIDATE,
            "challenge_root": challenge_root,
            "claim_fingerprint": CLAIM_ROOT,
            "commit_policy_root": POLICY_ROOT,
            "counter_root": counter_root,
            "disposition_root": disposition_root,
            "epoch": EPOCH,
            "evidence_id": "evidence:alpha",
            "manifest_root": MANIFEST_ROOT,
            "positive_root": positive_root,
            "profile": PROFILE,
            "protocol_id": PROTOCOL_ID,
            "run_id": RUN_ID,
            "target": TARGET,
        },
        schema="pheroos-evidence-root-v1",
        profile=PROFILE,
    )
    return {
        "positive_root": positive_root,
        "counter_root": counter_root,
        "disposition_root": disposition_root,
        "challenge_root": challenge_root,
        "evidence_root": evidence_root,
    }


def evidence_summary_record(binding: EvidenceBinding) -> EvidenceSummary:
    coverage = challenge_records()[2]
    positive_group = EvidenceGroupContribution(
        independence_group="group:alpha",
        observation_fingerprints=(OBSERVATION_A, OBSERVATION_B),
        raw_contribution=800_000,
        group_cap=700_000,
        counted_contribution=700_000,
    )
    source = SourceDomainContribution(
        source_domain="domain:alpha",
        observation_fingerprints=(OBSERVATION_A, OBSERVATION_B),
        contribution=800_000,
        contribution_floor=500_000,
    )
    return EvidenceSummary(
        evidence_binding_fingerprint=commit_payload_fingerprint(
            evidence_binding_payload(binding),
            schema="pheroos-evidence-binding-authority-v1",
            profile=PROFILE,
        ),
        positive_groups=(positive_group,),
        counter_groups=(),
        source_domains=(source,),
        active_counter_observation_fingerprints=(),
        resolved_counter_observation_fingerprints=(),
        blocking_critical_counter_observation_fingerprints=(),
        positive_evidence=700_000,
        counterevidence=0,
        weighted_counterevidence=0,
        net_evidence=700_000,
        counterevidence_ratio_ppm=0,
        source_diversity=1,
        challenge_coverage=coverage,
        _minimum_positive_evidence=600_000,
        _maximum_counterevidence=0,
        _maximum_counterevidence_ratio_ppm=0,
        _minimum_source_diversity=1,
    )


def membership_record() -> EligiblePrincipalSnapshot:
    principal = EligiblePrincipal(
        principal_id="principal:alpha",
        principal_verification_fingerprint=PRINCIPAL_ROOT,
        verified_issuer_id="issuer:identity",
        verified_method="identity-verifier-v1",
        failure_domain="failure:alpha",
    )
    cluster = EligiblePrincipalCluster(
        cluster_id="cluster:alpha",
        principals=(principal,),
    )
    clusters = (cluster,)
    membership_root = commit_payload_fingerprint(
        {
            "assurance": ASSURANCE,
            "commit_policy_root": POLICY_ROOT,
            "eligible_clusters": tuple(cluster_payload(item) for item in clusters),
            "epoch": EPOCH,
            "manifest_root": MANIFEST_ROOT,
            "protocol_id": PROTOCOL_ID,
            "run_id": RUN_ID,
            "target": TARGET,
        },
        schema="pheroos-eligible-membership-root-v1",
        profile=PROFILE,
    )
    return EligiblePrincipalSnapshot(
        snapshot_id="membership:epoch:3",
        **binding_fields(),
        eligible_clusters=clusters,
        membership_root=membership_root,
        issuer_id="governance:membership",
        membership_method="verified-static-epoch-v1",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=2,
        expires_at_step=20,
        provenance="urn:test:membership",
        trace_event_id="trace:membership:3",
    )


def membership_epoch_record(
    snapshot: EligiblePrincipalSnapshot,
) -> EligibleMembershipEpochState:
    authority_key = commit_payload_fingerprint(
        {
            "assurance": snapshot.assurance,
            "commit_policy_root": snapshot.commit_policy_root,
            "epoch": snapshot.epoch,
            "manifest_root": snapshot.manifest_root,
            "protocol_id": snapshot.protocol_id,
            "run_id": snapshot.run_id,
            "target": snapshot.target,
        },
        schema="pheroos-eligible-membership-epoch-authority-key-v1",
        profile=PROFILE,
    )
    return EligibleMembershipEpochState(
        authority_key=authority_key,
        **binding_fields(),
        snapshot_id=snapshot.snapshot_id,
        snapshot_fingerprint=commit_payload_fingerprint(
            eligible_principal_snapshot_payload(snapshot),
            schema="pheroos-eligible-principal-snapshot-v1",
            profile=PROFILE,
        ),
        membership_root=snapshot.membership_root,
        issuer_id=snapshot.issuer_id,
        membership_method=snapshot.membership_method,
        authority=snapshot.authority,
        issued_at_step=snapshot.issued_at_step,
        expires_at_step=snapshot.expires_at_step,
        provenance=snapshot.provenance,
        trace_event_id=snapshot.trace_event_id,
    )


def membership_epoch_fingerprint(state: EligibleMembershipEpochState) -> str:
    return commit_payload_fingerprint(
        eligible_membership_epoch_state_payload(state),
        schema="pheroos-eligible-membership-epoch-state-v1",
        profile=PROFILE,
    )


def cluster_payload(cluster: EligiblePrincipalCluster) -> dict[str, object]:
    return {
        "cluster_id": cluster.cluster_id,
        "principals": tuple(
            {
                "failure_domain": principal.failure_domain,
                "principal_id": principal.principal_id,
                "principal_verification_fingerprint": (
                    principal.principal_verification_fingerprint
                ),
                "verified_issuer_id": principal.verified_issuer_id,
                "verified_method": principal.verified_method,
            }
            for principal in cluster.principals
        ),
    }


def lease_records() -> tuple[
    SupportLeaseProposal,
    SupportLease,
    SupportLeaseRevocation,
]:
    proposal = SupportLeaseProposal(
        proposal_id="proposal:alpha",
        **binding_fields(),
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        principal_id="principal:alpha",
        positive_observation_fingerprints=(OBSERVATION_A,),
        nonce="nonce:lease:alpha",
        proposed_at_step=3,
        provenance="urn:test:lease-proposal",
        trace_event_id="trace:lease-proposal",
    )
    membership = membership_record()
    membership_epoch = membership_epoch_record(membership)
    proposal_fingerprint = commit_payload_fingerprint(
        support_lease_proposal_payload(proposal),
        schema="pheroos-support-lease-proposal-v1",
        profile=PROFILE,
    )
    replay_authority_key = commit_payload_fingerprint(
        {
            "issuer_id": "governance:support",
            "profile": PROFILE,
            "protocol_id": PROTOCOL_ID,
        },
        schema="pheroos-support-lease-replay-authority-key-v1",
        profile=PROFILE,
    )
    request_payload: dict[str, object] = {
        "assurance": ASSURANCE,
        "authority": AuthorityLevel.GOVERNANCE,
        "candidate_id": CANDIDATE,
        "claim_fingerprint": CLAIM_ROOT,
        "commit_policy_root": POLICY_ROOT,
        "epoch": EPOCH,
        "expires_at_step": 10,
        "issuance_provenance": "urn:test:lease",
        "issuance_trace_event_id": "trace:lease",
        "issued_at_step": 4,
        "issuer_id": "governance:support",
        "lease_id": "lease:alpha",
        "manifest_root": MANIFEST_ROOT,
        "membership_epoch_state_fingerprint": membership_epoch_fingerprint(
            membership_epoch
        ),
        "membership_root": membership.membership_root,
        "nonce": "nonce:lease:alpha",
        "positive_observation_fingerprints": (OBSERVATION_A,),
        "principal_cluster_id": "cluster:alpha",
        "principal_id": "principal:alpha",
        "principal_verification_fingerprint": PRINCIPAL_ROOT,
        "prior_lease_fingerprint": "",
        "profile": PROFILE,
        "proposal_fingerprint": proposal_fingerprint,
        "proposal_provenance": proposal.provenance,
        "proposal_trace_event_id": proposal.trace_event_id,
        "protocol_id": PROTOCOL_ID,
        "replay_authority_key": replay_authority_key,
        "run_id": RUN_ID,
        "target": TARGET,
    }
    lease = SupportLease(
        lease_id="lease:alpha",
        proposal_fingerprint=proposal_fingerprint,
        **binding_fields(),
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        principal_id="principal:alpha",
        principal_cluster_id="cluster:alpha",
        principal_verification_fingerprint=PRINCIPAL_ROOT,
        membership_root=membership.membership_root,
        membership_epoch_state_fingerprint=membership_epoch_fingerprint(
            membership_epoch
        ),
        positive_observation_fingerprints=(OBSERVATION_A,),
        prior_lease_fingerprint="",
        nonce="nonce:lease:alpha",
        replay_authority_key=replay_authority_key,
        replay_receipt_fingerprint=commit_payload_fingerprint(
            request_payload,
            schema="pheroos-support-lease-replay-receipt-v1",
            profile=PROFILE,
        ),
        issuer_id="governance:support",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=4,
        expires_at_step=10,
        proposal_provenance=proposal.provenance,
        proposal_trace_event_id=proposal.trace_event_id,
        issuance_provenance="urn:test:lease",
        issuance_trace_event_id="trace:lease",
    )
    revocation = SupportLeaseRevocation(
        revocation_id="revocation:alpha",
        lease_fingerprint=commit_payload_fingerprint(
            support_lease_payload(lease),
            schema="pheroos-support-lease-v1",
            profile=PROFILE,
        ),
        **binding_fields(),
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        principal_id=lease.principal_id,
        principal_cluster_id=lease.principal_cluster_id,
        reason_codes=("support_withdrawn",),
        issuer_id="governance:support",
        authority=AuthorityLevel.GOVERNANCE,
        revoked_at_step=6,
        provenance="urn:test:revocation",
        trace_event_id="trace:revocation",
    )
    return proposal, lease, revocation


def support_replay_records(
    lease: SupportLease,
) -> tuple[SupportLeaseReplayReceipt, SupportLeaseReplayState]:
    receipt = SupportLeaseReplayReceipt(
        replay_receipt_fingerprint=lease.replay_receipt_fingerprint,
        lease_fingerprint=commit_payload_fingerprint(
            support_lease_payload(lease),
            schema="pheroos-support-lease-v1",
            profile=PROFILE,
        ),
        lease_id=lease.lease_id,
        proposal_fingerprint=lease.proposal_fingerprint,
        nonce=lease.nonce,
        **binding_fields(),
        candidate_id=lease.candidate_id,
        claim_fingerprint=lease.claim_fingerprint,
        principal_id=lease.principal_id,
        principal_cluster_id=lease.principal_cluster_id,
        membership_root=lease.membership_root,
        membership_epoch_state_fingerprint=(lease.membership_epoch_state_fingerprint),
        issued_at_step=lease.issued_at_step,
        expires_at_step=lease.expires_at_step,
    )
    authority_key = lease.replay_authority_key
    empty_root = commit_payload_fingerprint(
        {"receipts": ()},
        schema="pheroos-support-lease-replay-root-v1",
        profile=PROFILE,
    )
    initial_payload = {
        "authority": AuthorityLevel.GOVERNANCE,
        "authority_key": authority_key,
        "initialized_at_step": 3,
        "issuer_id": lease.issuer_id,
        "last_issued_at_step": 3,
        "previous_state_fingerprint": "",
        "profile": PROFILE,
        "protocol_id": PROTOCOL_ID,
        "provenance": "urn:test:support-replay",
        "receipts": (),
        "replay_root": empty_root,
        "revision": 0,
        "trace_event_id": "trace:support-replay",
    }
    receipt_payload = support_lease_replay_receipt_payload(receipt)
    state = SupportLeaseReplayState(
        authority_key=authority_key,
        profile=PROFILE,
        protocol_id=PROTOCOL_ID,
        issuer_id=lease.issuer_id,
        authority=AuthorityLevel.GOVERNANCE,
        revision=1,
        receipts=(receipt,),
        replay_root=commit_payload_fingerprint(
            {"receipts": (receipt_payload,)},
            schema="pheroos-support-lease-replay-root-v1",
            profile=PROFILE,
        ),
        previous_state_fingerprint=commit_payload_fingerprint(
            initial_payload,
            schema="pheroos-support-lease-replay-state-v1",
            profile=PROFILE,
        ),
        initialized_at_step=3,
        last_issued_at_step=lease.issued_at_step,
        provenance=lease.issuance_provenance,
        trace_event_id=lease.issuance_trace_event_id,
    )
    return receipt, state


def equivocation_record() -> SupportEquivocationFinding:
    candidates = tuple(canonical_commit_set((CANDIDATE, "candidate:beta")))
    leases = tuple(sorted((LEASE_A, LEASE_B)))
    finding_id = commit_payload_fingerprint(
        {
            "assurance": ASSURANCE,
            "commit_policy_root": POLICY_ROOT,
            "conflicting_candidates": candidates,
            "conflicting_lease_fingerprints": leases,
            "epoch": EPOCH,
            "first_overlap_step": 5,
            "manifest_root": MANIFEST_ROOT,
            "principal_cluster_id": "cluster:conflict",
            "protocol_id": PROTOCOL_ID,
            "run_id": RUN_ID,
            "target": TARGET,
        },
        schema="pheroos-support-equivocation-finding-v1",
        profile=PROFILE,
    )
    return SupportEquivocationFinding(
        finding_id=finding_id,
        **binding_fields(),
        principal_cluster_id="cluster:conflict",
        conflicting_candidates=candidates,
        conflicting_lease_fingerprints=leases,
        first_overlap_step=5,
    )


def equivocation_payload(finding: SupportEquivocationFinding) -> dict[str, object]:
    return {
        "assurance": finding.assurance,
        "commit_policy_root": finding.commit_policy_root,
        "conflicting_candidates": finding.conflicting_candidates,
        "conflicting_lease_fingerprints": finding.conflicting_lease_fingerprints,
        "epoch": finding.epoch,
        "finding_id": finding.finding_id,
        "first_overlap_step": finding.first_overlap_step,
        "manifest_root": finding.manifest_root,
        "principal_cluster_id": finding.principal_cluster_id,
        "profile": finding.profile,
        "protocol_id": finding.protocol_id,
        "run_id": finding.run_id,
        "target": finding.target,
    }


def support_evaluation_payload() -> dict[str, object]:
    finding = equivocation_record()
    membership = membership_record()
    membership_epoch = membership_epoch_record(membership)
    membership_epoch_state_fingerprint = membership_epoch_fingerprint(membership_epoch)
    support_replay_scope_root = commit_payload_fingerprint(
        {"receipts": ()},
        schema="pheroos-support-lease-scope-replay-root-v1",
        profile=PROFILE,
    )
    active_clusters = tuple(canonical_commit_set(("cluster:alpha",)))
    included = (OBSERVATION_A,)
    excluded = finding.conflicting_lease_fingerprints
    root = commit_payload_fingerprint(
        {
            "candidate_id": CANDIDATE,
            "claim_fingerprint": CLAIM_ROOT,
            "commit_policy_root": POLICY_ROOT,
            "current_step": 6,
            "epoch": EPOCH,
            "equivocation_finding_ids": (finding.finding_id,),
            "excluded_lease_fingerprints": excluded,
            "included_lease_fingerprints": included,
            "membership_root": membership.membership_root,
            "membership_epoch_state_fingerprint": (membership_epoch_state_fingerprint),
            "run_id": RUN_ID,
            "support_replay_scope_root": support_replay_scope_root,
            "target": TARGET,
        },
        schema="pheroos-support-lease-evaluation-root-v1",
        profile=PROFILE,
    )
    evaluation = SupportLeaseEvaluation(
        **binding_fields(),
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        current_step=6,
        membership_root=membership.membership_root,
        membership_epoch_state_fingerprint=membership_epoch_state_fingerprint,
        support_replay_scope_root=support_replay_scope_root,
        eligible_cluster_count=3,
        active_support_cluster_count=1,
        support_ratio_ppm=333_333,
        policy_support_threshold_clusters=2,
        policy_support_met=False,
        active_support_clusters=active_clusters,
        included_lease_fingerprints=included,
        excluded_lease_fingerprints=excluded,
        equivocation_findings=(finding,),
        lease_root=root,
    )
    return {
        "active_support_cluster_count": evaluation.active_support_cluster_count,
        "active_support_clusters": evaluation.active_support_clusters,
        "assurance": evaluation.assurance,
        "candidate_id": evaluation.candidate_id,
        "claim_fingerprint": evaluation.claim_fingerprint,
        "commit_policy_root": evaluation.commit_policy_root,
        "current_step": evaluation.current_step,
        "eligible_cluster_count": evaluation.eligible_cluster_count,
        "epoch": evaluation.epoch,
        "equivocation_findings": tuple(
            equivocation_payload(item) for item in evaluation.equivocation_findings
        ),
        "excluded_lease_fingerprints": evaluation.excluded_lease_fingerprints,
        "included_lease_fingerprints": evaluation.included_lease_fingerprints,
        "lease_root": evaluation.lease_root,
        "manifest_root": evaluation.manifest_root,
        "membership_root": evaluation.membership_root,
        "membership_epoch_state_fingerprint": (
            evaluation.membership_epoch_state_fingerprint
        ),
        "policy_support_met": evaluation.policy_support_met,
        "policy_support_threshold_clusters": (
            evaluation.policy_support_threshold_clusters
        ),
        "profile": evaluation.profile,
        "protocol_id": evaluation.protocol_id,
        "run_id": evaluation.run_id,
        "support_ratio_ppm": evaluation.support_ratio_ppm,
        "support_replay_scope_root": evaluation.support_replay_scope_root,
        "target": evaluation.target,
    }


def risk_records() -> tuple[
    RiskAssessmentChainState,
    RiskAssessment,
    CommitThresholdSnapshot,
]:
    chain_id = commit_payload_fingerprint(
        {
            **binding_fields(),
            "risk_policy_root": RESULT_ROOT,
        },
        schema="pheroos-risk-assessment-chain-authority-key-v1",
        profile=PROFILE,
    )
    chain_state = RiskAssessmentChainState(
        chain_id=chain_id,
        **binding_fields(),
        risk_policy_root=RESULT_ROOT,
        revision=0,
        latest_assessment_fingerprint="",
        latest_risk_band="",
        initialized_at_step=1,
        last_issued_at_step=1,
        expires_at_step=20,
        previous_state_fingerprint="",
        issuer_id="governance:risk",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:risk-chain",
        trace_event_id="trace:risk-chain",
    )
    chain_state_fingerprint = commit_payload_fingerprint(
        risk_assessment_chain_state_payload(chain_state),
        schema="pheroos-risk-assessment-chain-state-v1",
        profile=PROFILE,
    )
    assessment = RiskAssessment(
        assessment_id="risk:low",
        **binding_fields(),
        risk_policy_root=RESULT_ROOT,
        risk_chain_id=chain_id,
        risk_chain_revision=1,
        previous_chain_state_fingerprint=chain_state_fingerprint,
        risk_band=RiskBand.LOW,
        risk_input_fingerprints=(EXECUTION_ROOT, RESULT_ROOT),
        rationale_codes=("declared_matrix", "independent_review"),
        assessment_method="declared-risk-matrix-v1",
        issuer_id="governance:risk",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=2,
        expires_at_step=20,
        previous_assessment_fingerprint="",
        window_reset_required=False,
        provenance="urn:test:risk",
        trace_event_id="trace:risk",
    )
    snapshot = CommitThresholdSnapshot(
        threshold_id="threshold:low",
        **binding_fields(),
        risk_policy_root=assessment.risk_policy_root,
        risk_chain_id=chain_id,
        risk_chain_revision=1,
        risk_chain_state_fingerprint=chain_state_fingerprint,
        risk_assessment_fingerprint=commit_payload_fingerprint(
            risk_assessment_payload(assessment),
            schema="pheroos-risk-assessment-v1",
            profile=PROFILE,
        ),
        risk_band=RiskBand.LOW,
        minimum_positive_evidence=600_000,
        maximum_counterevidence=100_000,
        maximum_counterevidence_ratio_ppm=100_000,
        minimum_support_clusters=1,
        minimum_support_ratio_ppm=500_000,
        minimum_source_diversity=1,
        minimum_margin=100_000,
        stability_steps=2,
        required_challenge_categories=("independent_replication",),
        minimum_assurance=CommitAssurance.EVIDENCE_BOUND,
        publishable_outcomes=("evidence_commit",),
        executable_outcomes=(),
        issuer_id="governance:threshold",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=2,
        expires_at_step=20,
        provenance="urn:test:threshold",
        trace_event_id="trace:threshold",
    )
    return chain_state, assessment, snapshot


def wp_cd_records() -> dict[str, dict[str, object]]:
    observation, verified_observation, disposition = observation_records()
    challenge, verified_challenge, coverage = challenge_records()
    binding = evidence_binding_record()
    summary = evidence_summary_record(binding)
    membership = membership_record()
    membership_epoch = membership_epoch_record(membership)
    proposal, lease, revocation = lease_records()
    replay_receipt, replay_state = support_replay_records(lease)
    chain_state, assessment, threshold = risk_records()
    return {
        "pheroos-observation-attestation-v1": envelope(
            observation_attestation_payload(observation),
            schema="pheroos-observation-attestation-v1",
            profile=AUTHORITY_PROFILE,
        ),
        "pheroos-verified-observation-v1": envelope(
            verified_observation_payload(verified_observation),
            schema="pheroos-verified-observation-v1",
        ),
        "pheroos-counterevidence-disposition-v1": envelope(
            counterevidence_disposition_payload(disposition),
            schema="pheroos-counterevidence-disposition-v1",
        ),
        "pheroos-challenge-attestation-v1": envelope(
            challenge_attestation_payload(challenge),
            schema="pheroos-challenge-attestation-v1",
            profile=AUTHORITY_PROFILE,
        ),
        "pheroos-verified-challenge-v1": envelope(
            verified_challenge_payload(verified_challenge),
            schema="pheroos-verified-challenge-v1",
        ),
        "pheroos-challenge-coverage-v1": envelope(
            challenge_coverage_payload(coverage),
            schema="pheroos-challenge-coverage-v1",
        ),
        "pheroos-evidence-binding-authority-v1": envelope(
            evidence_binding_payload(binding),
            schema="pheroos-evidence-binding-authority-v1",
        ),
        "pheroos-evidence-summary-v1": envelope(
            evidence_summary_payload(summary),
            schema="pheroos-evidence-summary-v1",
        ),
        "pheroos-eligible-principal-snapshot-v1": envelope(
            eligible_principal_snapshot_payload(membership),
            schema="pheroos-eligible-principal-snapshot-v1",
        ),
        "pheroos-eligible-membership-epoch-state-v1": envelope(
            eligible_membership_epoch_state_payload(membership_epoch),
            schema="pheroos-eligible-membership-epoch-state-v1",
        ),
        "pheroos-support-lease-proposal-v1": envelope(
            support_lease_proposal_payload(proposal),
            schema="pheroos-support-lease-proposal-v1",
        ),
        "pheroos-support-lease-replay-receipt-v1": envelope(
            support_lease_replay_receipt_payload(replay_receipt),
            schema="pheroos-support-lease-replay-receipt-v1",
        ),
        "pheroos-support-lease-replay-state-v1": envelope(
            support_lease_replay_state_payload(replay_state),
            schema="pheroos-support-lease-replay-state-v1",
        ),
        "pheroos-support-lease-v1": envelope(
            support_lease_payload(lease),
            schema="pheroos-support-lease-v1",
        ),
        "pheroos-support-lease-revocation-v1": envelope(
            support_lease_revocation_payload(revocation),
            schema="pheroos-support-lease-revocation-v1",
        ),
        "pheroos-support-lease-evaluation-v1": envelope(
            support_evaluation_payload(),
            schema="pheroos-support-lease-evaluation-v1",
        ),
        "pheroos-support-equivocation-finding-v1": envelope(
            equivocation_payload(equivocation_record()),
            schema="pheroos-support-equivocation-finding-v1",
        ),
        "pheroos-risk-assessment-v1": envelope(
            risk_assessment_payload(assessment),
            schema="pheroos-risk-assessment-v1",
        ),
        "pheroos-risk-assessment-chain-state-v1": envelope(
            risk_assessment_chain_state_payload(chain_state),
            schema="pheroos-risk-assessment-chain-state-v1",
        ),
        "pheroos-commit-threshold-snapshot-v1": envelope(
            commit_threshold_snapshot_payload(threshold),
            schema="pheroos-commit-threshold-snapshot-v1",
        ),
    }


def test_wp_cd_actual_and_reconstructable_payloads_match_strict_wire_schema() -> None:
    records = wp_cd_records()

    assert len(records) == 20
    for schema_name, record in records.items():
        assert record["schema"] == schema_name
        assert record["version"] == COMMIT_WIRE_VERSION
        assert validate_commit_wire_record(record) == []


def test_every_wp_cd_payload_rejects_unknown_critical_fields() -> None:
    for record in wp_cd_records().values():
        mutated = deepcopy(record)
        mutated["payload"]["unknown_authority"] = True
        assert validate_commit_wire_record(mutated)


def test_wp_cd_wire_rejects_malformed_refs_floats_and_cross_profile_reuse() -> None:
    record = wp_cd_records()["pheroos-verified-observation-v1"]

    malformed = deepcopy(record)
    malformed["payload"]["claim_fingerprint"] = "sha256:not-a-root"
    assert validate_commit_wire_record(malformed)

    coerced = deepcopy(record)
    coerced["payload"]["quality_ppm"] = 800_000.0
    assert validate_commit_wire_record(coerced)

    cross_profile = deepcopy(record)
    cross_profile["profile"] = "pheroos-certified-commit-v1"
    assert any(
        "profile" in error or "assurance" in error
        for error in validate_commit_wire_record(cross_profile)
    )


def test_wp_cd_wire_rejects_noncanonical_sets_and_mutated_roots() -> None:
    records = wp_cd_records()
    noncanonical = deepcopy(records["pheroos-evidence-binding-authority-v1"])
    noncanonical["payload"]["positive_observation_fingerprints"].reverse()
    assert any(
        "canonical" in error or "root mismatch" in error
        for error in validate_commit_wire_record(noncanonical)
    )

    root_cases = (
        ("pheroos-evidence-binding-authority-v1", "evidence_root"),
        ("pheroos-eligible-principal-snapshot-v1", "membership_root"),
        ("pheroos-eligible-membership-epoch-state-v1", "authority_key"),
        ("pheroos-support-lease-replay-state-v1", "replay_root"),
        ("pheroos-support-lease-v1", "replay_receipt_fingerprint"),
        ("pheroos-support-lease-evaluation-v1", "lease_root"),
        ("pheroos-support-equivocation-finding-v1", "finding_id"),
        ("pheroos-risk-assessment-chain-state-v1", "chain_id"),
        ("pheroos-risk-assessment-v1", "risk_chain_id"),
        ("pheroos-commit-threshold-snapshot-v1", "risk_chain_id"),
    )
    for schema_name, field_name in root_cases:
        mutated = deepcopy(records[schema_name])
        mutated["payload"][field_name] = "sha256:" + ("0" * 64)
        assert any(
            "mismatch" in error for error in validate_commit_wire_record(mutated)
        )


def test_wp_cd_wire_rejects_false_challenge_and_derived_summary_claims() -> None:
    records = wp_cd_records()
    false_challenge = deepcopy(records["pheroos-challenge-attestation-v1"])
    false_challenge["payload"]["result"] = "counterevidence_found"
    assert any(
        "requires observations" in error
        for error in validate_commit_wire_record(false_challenge)
    )

    false_summary = deepcopy(records["pheroos-evidence-summary-v1"])
    false_summary["payload"]["positive_threshold_satisfied"] = False
    assert any(
        "derived gate mismatch" in error
        for error in validate_commit_wire_record(false_summary)
    )

    invalid_interval = deepcopy(records["pheroos-risk-assessment-v1"])
    invalid_interval["payload"]["expires_at_step"] = invalid_interval["payload"][
        "issued_at_step"
    ]
    assert any(
        "must be after" in error
        for error in validate_commit_wire_record(invalid_interval)
    )


def test_support_replay_wire_rejects_cross_profile_and_receipt_key_collision() -> None:
    state = deepcopy(wp_cd_records()["pheroos-support-lease-replay-state-v1"])

    cross_profile = deepcopy(state)
    cross_profile["profile"] = "pheroos-certified-commit-v1"
    assert any(
        "profile mismatch" in error
        for error in validate_commit_wire_record(cross_profile)
    )

    collision = deepcopy(state)
    conflicting = deepcopy(collision["payload"]["receipts"][0])
    conflicting["lease_id"] = "lease:conflict"
    conflicting["lease_fingerprint"] = "sha256:" + ("0" * 64)
    conflicting["replay_receipt_fingerprint"] = "sha256:" + ("9" * 64)
    collision["payload"]["receipts"].append(conflicting)
    collision["payload"]["revision"] = 2
    assert any(
        "duplicate nonce" in error for error in validate_commit_wire_record(collision)
    )
