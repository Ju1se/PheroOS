from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from enum import Enum
import gc
import hashlib
import json
import weakref

import pytest

import pheroos.governance as governance
from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.certificate import (
    EvidenceCommitCertificate,
    LocalCommitReceipt,
    evidence_commit_certificate_body_root,
    evidence_commit_certificate_fingerprint,
    evidence_commit_certificate_from_payload,
    evidence_commit_certificate_payload,
    issue_evidence_commit_certificate,
)
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.commit_state import (
    CommitFinalityStatus,
    DecisionOutcome,
    DecisionOutcomeKind,
    commit_finality_verification_is_authoritative,
    issue_commit_liveness_input,
    reduce_commit_liveness,
)
from pheroos.governance.distributed_commit import (
    DISTRIBUTED_PROPOSAL_VERSION,
    QUORUM_WITNESS_VERSION,
    WITNESS_VERIFICATION_VERSION,
    DistributedCertificateStatus,
    DistributedCommitCertificate,
    DistributedCommitProposal,
    DistributedCommitState,
    DistributedFinalityKind,
    PortableMembershipSnapshot,
    QuorumWitness,
    WitnessVerification,
    assemble_portable_distributed_commit_certificate,
    distributed_commit_certificate_fingerprint,
    distributed_commit_certificate_from_payload,
    distributed_commit_certificate_is_current_final,
    distributed_commit_certificate_payload,
    distributed_commit_proposal_from_payload,
    distributed_commit_proposal_payload,
    distributed_commit_value_payload,
    distributed_commit_value_root,
    distributed_commit_state_is_current,
    distributed_commit_state_fingerprint,
    distributed_commit_state_from_payload,
    distributed_commit_state_payload,
    distributed_finality_decision_from_payload,
    distributed_finality_decision_payload,
    epoch_transition_certificate_body_root,
    epoch_transition_decision_ref,
    evaluate_distributed_finality,
    initialize_distributed_commit_state,
    issue_distributed_commit_certificate,
    issue_distributed_commit_proposal,
    issue_epoch_transition_certificate,
    portable_membership_snapshot_from_eligible,
    quorum_witness_signing_root,
    quorum_witness_fingerprint,
    record_witness_verifications,
    register_distributed_commit_certificate,
    transition_distributed_commit_epoch,
    verify_distributed_commit_certificate,
    verify_distributed_commit_finality,
    verify_epoch_transition_certificate,
    verify_quorum_witness,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.permission import issue_action_permission
from pheroos.governance.principal import (
    PrincipalAttestation,
    PrincipalVerification,
    verify_principal_attestation,
    principal_verification_fingerprint,
)
from pheroos.governance.stop_signal import (
    StopResolution,
    verify_stop_resolution,
)
from pheroos.governance.support_lease import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    issue_eligible_principal_snapshot,
)
from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_MODEL,
    COMMIT_POLICY_VERSION,
    COMMIT_WIRE_VERSION,
    DISTRIBUTED_COMMIT_PROFILE_VERSION,
    REQUIRED_COMMIT_RESET_RULES,
    CertificatePolicy,
    CollectiveCommitPolicy,
    CommitAction,
    CommitAssurance,
    CommitWindowPolicy,
    DistributedCommitPolicy,
    EvidenceQualificationPolicy,
    RiskBandPolicy,
    SupportLeasePolicy,
    TerminalOutcomePolicy,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from tests.governance import test_commit_certificate as certificate_fixture
from tests.governance import test_commit_engine as engine_fixture


def _fingerprint(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


@dataclass
class _DistributedScenario:
    scenario: object
    assessment: object
    window: object
    receipt: LocalCommitReceipt
    portable_certificate: EvidenceCommitCertificate
    issuer_trust: dict[str, str]
    principals: tuple[PrincipalVerification, ...]
    proposal: DistributedCommitProposal
    state: DistributedCommitState
    witness_trust: dict[str, str]
    verifications: tuple[WitnessVerification, ...]


@dataclass(frozen=True)
class _PublicPortableScenario:
    policy: CollectiveCommitPolicy
    principals: tuple[PrincipalVerification, ...]
    membership_snapshot: EligiblePrincipalSnapshot
    membership_state: EligibleMembershipEpochState
    portable_membership: PortableMembershipSnapshot
    portable_certificate: EvidenceCommitCertificate
    issuer_trust: dict[str, str]
    proposal: DistributedCommitProposal
    witness_trust: dict[str, str]
    verifications: tuple[WitnessVerification, ...]
    certificate: DistributedCommitCertificate
    state: DistributedCommitState


_DISTRIBUTED_VALUE_FIELDS = (
    "wire_version",
    "canonicalization",
    "hash_algorithm",
    "profile",
    "assurance",
    "manifest_root",
    "commit_policy_root",
    "protocol_id",
    "run_id",
    "target",
    "epoch",
    "candidate_id",
    "claim_fingerprint",
    "output_payload_fingerprint",
    "risk_chain_state_root",
    "risk_assessment_root",
    "risk_policy_root",
    "membership_snapshot_root",
    "membership_epoch_state_root",
    "membership_root",
    "replay_state_root",
    "replay_root",
    "support_replay_state_root",
    "support_replay_root",
    "candidate_evidence_root",
    "candidate_challenge_root",
    "candidate_lease_root",
    "evidence_root",
    "challenge_root",
    "lease_root",
    "window_state_root",
    "window_root",
    "threshold_root",
    "stop_resolution_root",
    "permission_root",
    "context_root",
    "assessment_root",
    "local_receipt_version",
    "portable_certificate_version",
)


def _distributed_scenario(
    monkeypatch: pytest.MonkeyPatch,
) -> _DistributedScenario:
    original_policy = engine_fixture._policy
    original_membership_issuer = engine_fixture.issue_eligible_principal_snapshot
    captured_principals: list[PrincipalVerification] = []

    def distributed_policy(**kwargs):
        policy = original_policy(**kwargs)
        bands = {
            name: replace(
                band,
                minimum_assurance="distributed",
                minimum_support_ratio_ppm=250_000,
            )
            for name, band in policy.risk_bands.items()
        }
        return replace(
            policy,
            assurance="distributed",
            support_lease=replace(policy.support_lease, support_ratio_ppm=250_000),
            risk_bands=bands,
            certificate=CertificatePolicy(
                mode="distributed",
                wire_version=COMMIT_WIRE_VERSION,
                canonicalization=COMMIT_CANONICAL_VERSION,
                hash_algorithm="sha256",
                issuer_attestation_required=True,
                independent_verification_required=True,
            ),
            distributed=DistributedCommitPolicy(
                fault_model="byzantine_static_v1",
                membership_mode="static_epoch_verified_clusters_v1",
                membership_size=4,
                max_byzantine_faults=1,
                witness_quorum=3,
                witness_ttl_steps=4,
                minimum_failure_domain_diversity=3,
                epoch_transition_rule="governed_new_epoch_v1",
                conflict_rule="freeze_v1",
            ),
        )

    def four_member_snapshot(verifications, **kwargs):
        run_id = kwargs["run_id"]
        extras = tuple(
            engine_fixture._principal(
                f"principal:{run_id}:witness:{index}",
                f"cluster:{run_id}:witness:{index}",
                index=index,
                manifest_root=kwargs["manifest_root"],
                policy_root=kwargs["commit_policy_root"],
                run_id=run_id,
            )
            for index in (3, 4)
        )
        all_principals = tuple(verifications) + extras
        captured_principals[:] = all_principals
        return original_membership_issuer(all_principals, **kwargs)

    monkeypatch.setattr(
        engine_fixture,
        "PROFILE",
        DISTRIBUTED_COMMIT_PROFILE_VERSION,
    )
    monkeypatch.setattr(
        engine_fixture,
        "ASSURANCE",
        CommitAssurance.DISTRIBUTED,
    )
    monkeypatch.setattr(engine_fixture, "_policy", distributed_policy)
    monkeypatch.setattr(
        engine_fixture,
        "issue_eligible_principal_snapshot",
        four_member_snapshot,
    )
    scenario, assessment, window, output_ref = certificate_fixture._stable_scenario()
    receipt = certificate_fixture._receipt(
        scenario,
        assessment,
        window,
        output_ref,
    )
    metadata = {
        "certificate_id": f"portable:{scenario.run_id}",
        "issuer_id": "governance:portable",
        "authority": AuthorityLevel.GOVERNANCE,
        "issued_at_step": 6,
        "provenance": f"urn:test:portable:{scenario.run_id}",
        "trace_event_id": f"trace:portable:{scenario.run_id}",
    }
    portable_body = evidence_commit_certificate_body_root(receipt, **metadata)
    issuer_refs = (f"attestation:portable:{scenario.run_id}:1",)
    issuer_trust = {issuer_refs[0]: portable_body}
    portable = issue_evidence_commit_certificate(
        receipt,
        commit_policy=scenario.policy,
        issuer_attestation_refs=issuer_refs,
        trusted_issuer_attestations=issuer_trust,
        **metadata,
    )
    proposal = issue_distributed_commit_proposal(
        receipt,
        portable,
        scenario.membership_snapshot,
        scenario.membership_state,
        commit_policy=scenario.policy,
        trusted_issuer_attestations=issuer_trust,
        proposal_id=f"proposal:{scenario.run_id}:primary",
        proposed_at_step=6,
    )
    state = initialize_distributed_commit_state(
        scenario.membership_snapshot,
        scenario.membership_state,
        commit_policy=scenario.policy,
        current_step=6,
        issuer_id="governance:distributed-state",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:test:distributed-state:{scenario.run_id}",
        trace_event_id=f"trace:distributed-state:{scenario.run_id}",
    )
    witness_trust: dict[str, str] = {}
    verifications = tuple(
        _witness_verification(
            scenario,
            proposal,
            principal,
            index=index,
            witness_trust=witness_trust,
        )
        for index, principal in enumerate(captured_principals, start=1)
    )
    state = record_witness_verifications(
        state,
        verifications,
        current_step=6,
    )
    return _DistributedScenario(
        scenario=scenario,
        assessment=assessment,
        window=window,
        receipt=receipt,
        portable_certificate=portable,
        issuer_trust=issuer_trust,
        principals=tuple(captured_principals),
        proposal=proposal,
        state=state,
        witness_trust=witness_trust,
        verifications=verifications,
    )


def _witness_verification(
    scenario,
    proposal: DistributedCommitProposal,
    principal: PrincipalVerification,
    *,
    index: int,
    witness_trust: dict[str, str],
    nonce: str | None = None,
    witness_id: str | None = None,
) -> WitnessVerification:
    witness = QuorumWitness(
        witness_version=QUORUM_WITNESS_VERSION,
        witness_id=witness_id
        or f"witness:{scenario.run_id}:{proposal.proposal_id}:{index}",
        profile=proposal.profile,
        assurance=proposal.assurance,
        protocol_id=proposal.protocol_id,
        run_id=proposal.run_id,
        target=proposal.target,
        epoch=proposal.epoch,
        candidate_id=proposal.candidate_id,
        membership_root=proposal.membership_root,
        commit_value_root=proposal.commit_value_root,
        proposal_digest=proposal.proposal_digest,
        principal_id=principal.principal_id,
        principal_cluster_id=principal.cluster_id,
        failure_domain=principal.failure_domain,
        nonce=nonce
        or f"nonce:witness:{scenario.run_id}:{proposal.proposal_id}:{index}",
        witnessed_at_step=6,
        expires_at_step=10,
        provenance=f"urn:test:witness:{scenario.run_id}:{index}",
        trace_event_id=f"trace:witness:{scenario.run_id}:{index}",
        attestation_ref=f"attestation:witness:{scenario.run_id}:{proposal.proposal_id}:{index}",
    )
    witness_trust[witness.attestation_ref] = quorum_witness_signing_root(witness)
    return verify_quorum_witness(
        witness,
        proposal,
        principal,
        scenario.membership_snapshot,
        scenario.membership_state,
        commit_policy=scenario.policy,
        trusted_witness_attestations=witness_trust,
        verification_id=f"verification:{scenario.run_id}:{proposal.proposal_id}:{index}",
        verifier_id="governance:witness-verifier",
        authority=AuthorityLevel.GOVERNANCE,
        verified_at_step=6,
        provenance=f"urn:test:witness-verification:{scenario.run_id}:{index}",
        trace_event_id=f"trace:witness-verification:{scenario.run_id}:{index}",
    )


def _certificate(
    bundle: _DistributedScenario,
    verifications: tuple[WitnessVerification, ...],
    *,
    suffix: str,
) -> DistributedCommitCertificate:
    return issue_distributed_commit_certificate(
        bundle.state,
        bundle.proposal,
        verifications=verifications,
        commit_policy=bundle.scenario.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        certificate_id=f"distributed:{bundle.scenario.run_id}:{suffix}",
        issuer_id="governance:distributed-certificate",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=6,
        provenance=f"urn:test:distributed-certificate:{suffix}",
        trace_event_id=f"trace:distributed-certificate:{suffix}",
    )


def _public_distributed_policy() -> CollectiveCommitPolicy:
    risk_band = RiskBandPolicy(
        minimum_positive_evidence=1_000_000,
        maximum_counterevidence=0,
        maximum_counterevidence_ratio_ppm=0,
        minimum_support_clusters=1,
        minimum_support_ratio_ppm=250_000,
        minimum_source_diversity=1,
        minimum_margin=500_000,
        stability_steps=2,
        required_challenge_categories=["independent_replication"],
        minimum_assurance="distributed",
        publishable_outcomes=["evidence_commit"],
        executable_outcomes=[],
    )
    return CollectiveCommitPolicy(
        policy_version=COMMIT_POLICY_VERSION,
        model=COMMIT_MODEL,
        assurance="distributed",
        target="decision:optimal",
        evidence_qualification=EvidenceQualificationPolicy(
            numeric_scale=1_000_000,
            minimum_quality_ppm=500_000,
            minimum_relevance_ppm=500_000,
            positive_group_cap=1_000_000,
            counter_group_cap=1_000_000,
            counter_weight_ppm=1_000_000,
            minimum_positive_evidence=1_000_000,
            maximum_counterevidence=0,
            maximum_counterevidence_ratio_ppm=0,
            domain_contribution_floor=500_000,
            minimum_source_diversity=1,
            required_challenge_categories=["independent_replication"],
            observation_ttl_steps=20,
            require_provenance=True,
            require_trace=True,
        ),
        support_lease=SupportLeasePolicy(
            minimum_support_clusters=1,
            support_ratio_ppm=250_000,
            lease_ttl_steps=5,
            membership_mode="verified_snapshot_v1",
            switch_mode="revoke_then_issue_v1",
            equivocation_mode="exclude_conflicts_v1",
            evidence_reference_required=True,
            cluster_verification_required=True,
        ),
        risk_bands={
            name: risk_band for name in ("LOW", "MODERATE", "HIGH", "CRITICAL")
        },
        commit_window=CommitWindowPolicy(
            minimum_stability_steps=2,
            deliberation_deadline_steps=8,
            maximum_leader_resets=2,
            maximum_epoch_restarts=1,
            run_deadline_steps=12,
            reset_rules=list(REQUIRED_COMMIT_RESET_RULES),
        ),
        terminal_outcome=TerminalOutcomePolicy(
            safe_fallback_candidate="candidate:fallback",
            deadline_outcome="safe_fallback",
            policy_incomplete_outcome="invalid",
            finality_unavailable_outcome="finality_unavailable",
            deliverable_outcomes=[
                "evidence_commit",
                "safe_fallback",
                "advisory",
                "blocked",
                "invalid",
                "finality_unavailable",
                "safety_violation",
            ],
            publishable_outcomes=["evidence_commit", "safe_fallback"],
            executable_outcomes=[],
        ),
        certificate=CertificatePolicy(
            mode="distributed",
            wire_version=COMMIT_WIRE_VERSION,
            canonicalization=COMMIT_CANONICAL_VERSION,
            hash_algorithm="sha256",
            issuer_attestation_required=True,
            independent_verification_required=True,
        ),
        distributed=DistributedCommitPolicy(
            fault_model="byzantine_static_v1",
            membership_mode="static_epoch_verified_clusters_v1",
            membership_size=4,
            max_byzantine_faults=1,
            witness_quorum=3,
            witness_ttl_steps=4,
            minimum_failure_domain_diversity=3,
            epoch_transition_rule="governed_new_epoch_v1",
            conflict_rule="freeze_v1",
        ),
    )


def _public_membership(
    *,
    label: str,
    policy: CollectiveCommitPolicy,
    manifest_root: str,
    protocol_id: str,
    run_id: str,
    epoch: int,
) -> tuple[
    tuple[PrincipalVerification, ...],
    EligiblePrincipalSnapshot,
    EligibleMembershipEpochState,
]:
    policy_root = commit_policy_fingerprint(
        policy,
        profile=DISTRIBUTED_COMMIT_PROFILE_VERSION,
    )
    principals = tuple(
        governance.verify_principal_attestation(
            governance.PrincipalAttestation(
                principal_id=f"principal:{label}:{index}",
                attestation_ref=f"opaque:principal:{label}:{index}",
                method="identity-verifier-v1",
                issuer_id="issuer:identity",
                issued_at_step=0,
                expires_at_step=30,
                provenance=f"urn:test:principal:{label}:{index}",
                nonce=f"nonce:principal:{label}:{index}",
                trace_event_id=f"trace:principal:{label}:{index}",
            ),
            profile=DISTRIBUTED_COMMIT_PROFILE_VERSION,
            assurance=CommitAssurance.DISTRIBUTED,
            manifest_root=manifest_root,
            commit_policy_root=policy_root,
            protocol_id=protocol_id,
            run_id=run_id,
            target=policy.target,
            epoch=epoch,
            cluster_id=f"cluster:{label}:{index}",
            failure_domain=f"failure:{label}:{index}",
            verifier_id="governance:identity",
            authority=AuthorityLevel.GOVERNANCE,
            current_step=1,
            provenance=f"urn:test:principal-verification:{label}:{index}",
            trace_event_id=f"trace:principal-verified:{label}:{index}",
        )
        for index in range(1, 5)
    )
    snapshot, epoch_state = governance.issue_eligible_principal_snapshot(
        principals,
        snapshot_id=f"membership:{label}",
        profile=DISTRIBUTED_COMMIT_PROFILE_VERSION,
        assurance=CommitAssurance.DISTRIBUTED,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=policy.target,
        epoch=epoch,
        issuer_id="governance:membership",
        membership_method="verified-static-epoch-v1",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=2,
        expires_at_step=20,
        provenance=f"urn:test:membership:{label}",
        trace_event_id=f"trace:membership:{label}",
    )
    return principals, snapshot, epoch_state


def _portable_witness_verification(
    *,
    label: str,
    proposal: DistributedCommitProposal,
    principal: PrincipalVerification,
    portable_membership: PortableMembershipSnapshot,
    index: int,
    witness_trust: dict[str, str],
) -> WitnessVerification:
    witness = governance.QuorumWitness(
        witness_version=governance.QUORUM_WITNESS_VERSION,
        witness_id=f"witness:{label}:{index}",
        profile=proposal.profile,
        assurance=proposal.assurance,
        protocol_id=proposal.protocol_id,
        run_id=proposal.run_id,
        target=proposal.target,
        epoch=proposal.epoch,
        candidate_id=proposal.candidate_id,
        membership_root=portable_membership.membership_root,
        commit_value_root=proposal.commit_value_root,
        proposal_digest=proposal.proposal_digest,
        principal_id=principal.principal_id,
        principal_cluster_id=principal.cluster_id,
        failure_domain=principal.failure_domain,
        nonce=f"nonce:witness:{label}:{index}",
        witnessed_at_step=6,
        expires_at_step=10,
        provenance=f"urn:test:witness:{label}:{index}",
        trace_event_id=f"trace:witness:{label}:{index}",
        attestation_ref=f"attestation:witness:{label}:{index}",
    )
    signing_root = governance.quorum_witness_signing_root(witness)
    witness_trust[witness.attestation_ref] = signing_root
    return governance.witness_verification_from_payload(
        {
            "verification_version": governance.WITNESS_VERIFICATION_VERSION,
            "verification_id": f"verification:{label}:{index}",
            "witness": governance.quorum_witness_payload(witness),
            "witness_fingerprint": governance.quorum_witness_fingerprint(witness),
            "witness_signing_root": signing_root,
            "principal_verification_ref": (
                governance.principal_verification_fingerprint(principal)
            ),
            "verified_at_step": 6,
            "expires_at_step": 10,
            "verifier_id": "governance:portable-witness",
            "authority": AuthorityLevel.GOVERNANCE,
            "provenance": f"urn:test:portable-witness:{label}:{index}",
            "trace_event_id": f"trace:portable-witness:{label}:{index}",
        }
    )


def _public_action_gate(
    bundle: _PublicPortableScenario,
    *,
    action: CommitAction,
    decision_ref: str,
    suffix: str = "",
):
    identity_suffix = f":{suffix}" if suffix else ""
    stop = governance.verify_stop_resolution(
        governance.StopResolution(
            target=bundle.state.target,
            action=action.value,
            blocked=False,
            reason="governance_clear",
        ),
        resolution_id=(f"stop:{bundle.state.run_id}:{action.value}{identity_suffix}"),
        profile=bundle.state.profile,
        assurance=bundle.state.assurance,
        manifest_root=bundle.state.manifest_root,
        commit_policy_root=bundle.state.commit_policy_root,
        protocol_id=bundle.state.protocol_id,
        run_id=bundle.state.run_id,
        epoch=bundle.state.epoch,
        decision_ref=decision_ref,
        certificate_ref="",
        resolved_stop_root=_fingerprint(
            f"resolved-stop:{bundle.state.run_id}:{action.value}"
        ),
        verifier_id="governance:stop",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=7,
        expires_at_step=12,
        provenance=f"urn:test:stop:{bundle.state.run_id}:{action.value}",
        trace_event_id=f"trace:stop:{bundle.state.run_id}:{action.value}",
    )
    permission = governance.issue_action_permission(
        permission_id=(
            f"permission:{bundle.state.run_id}:{action.value}{identity_suffix}"
        ),
        profile=bundle.state.profile,
        assurance=bundle.state.assurance,
        manifest_root=bundle.state.manifest_root,
        commit_policy_root=bundle.state.commit_policy_root,
        protocol_id=bundle.state.protocol_id,
        run_id=bundle.state.run_id,
        target=bundle.state.target,
        action=action,
        epoch=bundle.state.epoch,
        decision_ref=decision_ref,
        certificate_ref="",
        allowed=True,
        reason_codes=("declared_governance_authority",),
        issuer_id="governance:permission",
        policy_ref="policy:epoch-transition",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=7,
        expires_at_step=12,
        provenance=f"urn:test:permission:{bundle.state.run_id}:{action.value}",
        trace_event_id=f"trace:permission:{bundle.state.run_id}:{action.value}",
    )
    return stop, permission


def _public_portable_scenario(label: str) -> _PublicPortableScenario:
    policy = _public_distributed_policy()
    manifest_root = _fingerprint(f"manifest:{label}")
    protocol_id = f"protocol:distributed:{label}"
    run_id = f"run:distributed:{label}"
    principals, membership_snapshot, membership_state = _public_membership(
        label=label,
        policy=policy,
        manifest_root=manifest_root,
        protocol_id=protocol_id,
        run_id=run_id,
        epoch=3,
    )
    portable_membership = governance.portable_membership_snapshot_from_eligible(
        membership_snapshot
    )
    policy_root = commit_policy_fingerprint(
        policy,
        profile=DISTRIBUTED_COMMIT_PROFILE_VERSION,
    )
    central_roots = {
        name: _fingerprint(f"{label}:{name}")
        for name in (
            "claim_fingerprint",
            "output_payload_fingerprint",
            "risk_chain_state_root",
            "risk_assessment_root",
            "risk_policy_root",
            "threshold_root",
            "replay_state_root",
            "replay_root",
            "support_replay_state_root",
            "support_replay_root",
            "candidate_evidence_root",
            "candidate_challenge_root",
            "candidate_lease_root",
            "evidence_root",
            "challenge_root",
            "lease_root",
            "window_state_root",
            "window_root",
            "stop_resolution_root",
            "permission_root",
            "context_root",
            "assessment_root",
        )
    }
    certificate_body = {
        "schema_discriminator": "evidence_commit_certificate",
        "certificate_version": governance.EVIDENCE_COMMIT_CERTIFICATE_VERSION,
        "wire_version": COMMIT_WIRE_VERSION,
        "canonicalization": COMMIT_CANONICAL_VERSION,
        "hash_algorithm": "sha256",
        "certificate_id": f"portable:{label}",
        "profile": DISTRIBUTED_COMMIT_PROFILE_VERSION,
        "assurance": CommitAssurance.DISTRIBUTED,
        "authority_scope": governance.AuthorityScope.CERTIFIED,
        "manifest_root": manifest_root,
        "commit_policy_root": policy_root,
        "protocol_id": protocol_id,
        "run_id": run_id,
        "target": policy.target,
        "epoch": 3,
        "candidate_id": "candidate:alpha",
        **central_roots,
        "membership_snapshot_root": portable_membership.snapshot_fingerprint,
        "membership_epoch_state_root": (
            governance.eligible_membership_epoch_state_fingerprint(membership_state)
        ),
        "membership_root": portable_membership.membership_root,
        "local_receipt_ref": _fingerprint(f"local-receipt:{label}"),
        "issuer_id": "governance:portable",
        "authority": AuthorityLevel.GOVERNANCE,
        "issued_at_step": 6,
        "provenance": f"urn:test:portable:{label}",
        "trace_event_id": f"trace:portable:{label}",
    }
    certificate_body_root = commit_payload_fingerprint(
        certificate_body,
        schema="pheroos-evidence-commit-certificate-body-v1",
        profile=DISTRIBUTED_COMMIT_PROFILE_VERSION,
    )
    issuer_refs = (f"attestation:portable:{label}",)
    portable_payload = {
        **certificate_body,
        "issuer_attestation_refs": issuer_refs,
        "certificate_body_root": certificate_body_root,
        "certificate_root": commit_payload_fingerprint(
            {
                "certificate_body_root": certificate_body_root,
                "issuer_attestation_refs": issuer_refs,
            },
            schema="pheroos-evidence-commit-certificate-envelope-v1",
            profile=DISTRIBUTED_COMMIT_PROFILE_VERSION,
        ),
    }
    portable_certificate = governance.evidence_commit_certificate_from_payload(
        portable_payload
    )
    issuer_trust = {issuer_refs[0]: certificate_body_root}
    proposal_body = {
        "proposal_version": governance.DISTRIBUTED_PROPOSAL_VERSION,
        "wire_version": COMMIT_WIRE_VERSION,
        "canonicalization": COMMIT_CANONICAL_VERSION,
        "hash_algorithm": "sha256",
        "proposal_id": f"proposal:{label}",
        "profile": DISTRIBUTED_COMMIT_PROFILE_VERSION,
        "assurance": CommitAssurance.DISTRIBUTED,
        "manifest_root": manifest_root,
        "commit_policy_root": policy_root,
        "protocol_id": protocol_id,
        "run_id": run_id,
        "target": policy.target,
        "epoch": 3,
        "candidate_id": "candidate:alpha",
        **central_roots,
        "membership_snapshot_root": portable_membership.snapshot_fingerprint,
        "membership_epoch_state_root": (
            governance.eligible_membership_epoch_state_fingerprint(membership_state)
        ),
        "membership_root": portable_membership.membership_root,
        "local_receipt_version": governance.LOCAL_COMMIT_RECEIPT_VERSION,
        "local_receipt_ref": portable_certificate.local_receipt_ref,
        "portable_certificate_version": portable_certificate.certificate_version,
        "portable_certificate_ref": (
            governance.evidence_commit_certificate_fingerprint(portable_certificate)
        ),
        "proposed_at_step": 6,
    }
    value_payload = {
        "value_version": governance.DISTRIBUTED_COMMIT_VALUE_VERSION,
        **{name: proposal_body[name] for name in _DISTRIBUTED_VALUE_FIELDS},
    }
    proposal_body["commit_value_root"] = governance.distributed_commit_value_root(
        value_payload
    )
    proposal_body["proposal_digest"] = commit_payload_fingerprint(
        proposal_body,
        schema=governance.DISTRIBUTED_PROPOSAL_VERSION,
        profile=DISTRIBUTED_COMMIT_PROFILE_VERSION,
    )
    proposal = governance.distributed_commit_proposal_from_payload(proposal_body)
    witness_trust: dict[str, str] = {}
    verifications = tuple(
        _portable_witness_verification(
            label=label,
            proposal=proposal,
            principal=principal,
            portable_membership=portable_membership,
            index=index,
            witness_trust=witness_trust,
        )
        for index, principal in enumerate(principals[:3], start=1)
    )
    certificate = governance.assemble_portable_distributed_commit_certificate(
        governance.distributed_commit_proposal_payload(proposal),
        portable_membership,
        tuple(governance.witness_verification_payload(item) for item in verifications),
        commit_policy=policy,
        portable_certificate=portable_certificate,
        trusted_issuer_attestations=issuer_trust,
        trusted_witness_attestations=witness_trust,
        certificate_id=f"distributed:{label}",
        issuer_id="governance:portable-distributed",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=6,
        provenance=f"urn:test:portable-distributed:{label}",
        trace_event_id=f"trace:portable-distributed:{label}",
    )
    state = governance.initialize_distributed_commit_state(
        membership_snapshot,
        membership_state,
        commit_policy=policy,
        current_step=6,
        issuer_id=f"governance:distributed-state:{label}",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:test:distributed-state:{label}",
        trace_event_id=f"trace:distributed-state:{label}",
    )
    return _PublicPortableScenario(
        policy=policy,
        principals=principals,
        membership_snapshot=membership_snapshot,
        membership_state=membership_state,
        portable_membership=portable_membership,
        portable_certificate=portable_certificate,
        issuer_trust=issuer_trust,
        proposal=proposal,
        witness_trust=witness_trust,
        verifications=verifications,
        certificate=certificate,
        state=state,
    )


def _portable_semantic_conflict(
    bundle: _DistributedScenario,
    *,
    field_name: str,
    field_value: str,
    suffix: str,
) -> tuple[
    DistributedCommitProposal,
    EvidenceCommitCertificate,
    dict[str, str],
    dict[str, str],
    DistributedCommitCertificate,
]:
    """Assemble a valid peer proof for a different semantic commit value.

    This follows the public portable verifier path: the remote evidence and
    witness records carry no process-local issuance sentinel.
    """

    portable_payload = evidence_commit_certificate_payload(bundle.portable_certificate)
    portable_payload[field_name] = field_value
    portable_payload["certificate_id"] = f"portable:{bundle.scenario.run_id}:{suffix}"
    portable_payload["local_receipt_ref"] = _fingerprint(
        f"remote-receipt:{bundle.scenario.run_id}:{suffix}"
    )
    issuer_attestation_ref = f"attestation:portable:{bundle.scenario.run_id}:{suffix}"
    portable_payload["issuer_attestation_refs"] = (issuer_attestation_ref,)
    portable_body = dict(portable_payload)
    portable_body.pop("issuer_attestation_refs")
    portable_body.pop("certificate_body_root")
    portable_body.pop("certificate_root")
    portable_body_root = commit_payload_fingerprint(
        portable_body,
        schema="pheroos-evidence-commit-certificate-body-v1",
        profile=bundle.proposal.profile,
    )
    portable_payload["certificate_body_root"] = portable_body_root
    portable_payload["certificate_root"] = commit_payload_fingerprint(
        {
            "certificate_body_root": portable_body_root,
            "issuer_attestation_refs": (issuer_attestation_ref,),
        },
        schema="pheroos-evidence-commit-certificate-envelope-v1",
        profile=bundle.proposal.profile,
    )
    portable = evidence_commit_certificate_from_payload(portable_payload)
    issuer_trust = {
        **bundle.issuer_trust,
        issuer_attestation_ref: portable_body_root,
    }

    proposal_payload = distributed_commit_proposal_payload(bundle.proposal)
    proposal_payload[field_name] = field_value
    proposal_payload["proposal_id"] = f"proposal:{bundle.scenario.run_id}:{suffix}"
    proposal_payload["local_receipt_ref"] = portable.local_receipt_ref
    proposal_payload["portable_certificate_ref"] = (
        evidence_commit_certificate_fingerprint(portable)
    )
    value_payload = distributed_commit_value_payload(bundle.proposal)
    value_payload[field_name] = field_value
    proposal_payload["commit_value_root"] = distributed_commit_value_root(value_payload)
    proposal_body = dict(proposal_payload)
    proposal_body.pop("proposal_digest")
    proposal_payload["proposal_digest"] = commit_payload_fingerprint(
        proposal_body,
        schema=DISTRIBUTED_PROPOSAL_VERSION,
        profile=bundle.proposal.profile,
    )
    proposal = distributed_commit_proposal_from_payload(proposal_payload)

    witness_trust = dict(bundle.witness_trust)
    verifications: list[WitnessVerification] = []
    for index, principal in enumerate(bundle.principals[:3], start=1):
        witness = QuorumWitness(
            witness_version=QUORUM_WITNESS_VERSION,
            witness_id=f"witness:{bundle.scenario.run_id}:{suffix}:{index}",
            profile=proposal.profile,
            assurance=proposal.assurance,
            protocol_id=proposal.protocol_id,
            run_id=proposal.run_id,
            target=proposal.target,
            epoch=proposal.epoch,
            candidate_id=proposal.candidate_id,
            membership_root=proposal.membership_root,
            commit_value_root=proposal.commit_value_root,
            proposal_digest=proposal.proposal_digest,
            principal_id=principal.principal_id,
            principal_cluster_id=principal.cluster_id,
            failure_domain=principal.failure_domain,
            nonce=f"nonce:{bundle.scenario.run_id}:{suffix}:{index}",
            witnessed_at_step=6,
            expires_at_step=10,
            provenance=f"urn:test:portable-witness:{suffix}:{index}",
            trace_event_id=f"trace:portable-witness:{suffix}:{index}",
            attestation_ref=(
                f"attestation:witness:{bundle.scenario.run_id}:{suffix}:{index}"
            ),
        )
        signing_root = quorum_witness_signing_root(witness)
        witness_trust[witness.attestation_ref] = signing_root
        verifications.append(
            WitnessVerification(
                verification_version=WITNESS_VERIFICATION_VERSION,
                verification_id=(
                    f"verification:{bundle.scenario.run_id}:{suffix}:{index}"
                ),
                witness=witness,
                witness_fingerprint=quorum_witness_fingerprint(witness),
                witness_signing_root=signing_root,
                principal_verification_ref=(
                    principal_verification_fingerprint(principal)
                ),
                verified_at_step=6,
                expires_at_step=10,
                verifier_id="governance:remote-witness-verifier",
                authority=AuthorityLevel.GOVERNANCE,
                provenance=f"urn:test:portable-verification:{suffix}:{index}",
                trace_event_id=f"trace:portable-verification:{suffix}:{index}",
            )
        )
    certificate = assemble_portable_distributed_commit_certificate(
        proposal,
        portable_membership_snapshot_from_eligible(bundle.scenario.membership_snapshot),
        tuple(reversed(verifications)),
        commit_policy=bundle.scenario.policy,
        portable_certificate=portable,
        trusted_issuer_attestations=issuer_trust,
        trusted_witness_attestations=witness_trust,
        certificate_id=f"distributed:{bundle.scenario.run_id}:{suffix}",
        issuer_id="governance:remote-distributed-certificate",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=6,
        provenance=f"urn:test:remote-certificate:{suffix}",
        trace_event_id=f"trace:remote-certificate:{suffix}",
    )
    return proposal, portable, issuer_trust, witness_trust, certificate


def test_public_portable_witness_and_certificate_paths_fail_closed() -> None:
    bundle = _public_portable_scenario("public-portable")
    other = _public_portable_scenario("public-portable-other")
    certificate_ref = governance.distributed_commit_certificate_fingerprint(
        bundle.certificate
    )
    assert bundle.certificate.status is DistributedCertificateStatus.FINAL
    assert not governance.distributed_commit_proposal_is_authoritative(bundle.proposal)

    for verification in bundle.verifications:
        witness_payload = governance.quorum_witness_payload(verification.witness)
        assert governance.quorum_witness_from_payload(witness_payload) == (
            verification.witness
        )
        verification_payload = governance.witness_verification_payload(verification)
        rebuilt = governance.witness_verification_from_payload(verification_payload)
        assert rebuilt == verification
        assert not governance.witness_verification_is_authoritative(rebuilt)
        assert governance.verify_portable_witness_verification(
            verification_payload,
            membership_snapshot=bundle.portable_membership,
            trusted_witness_attestations=bundle.witness_trust,
            issued_at_step=6,
        )
        assert not governance.verify_portable_witness_verification(
            verification,
            membership_snapshot=bundle.portable_membership,
            trusted_witness_attestations={},
            issued_at_step=6,
        )
        assert not governance.verify_portable_witness_verification(
            verification,
            membership_snapshot=bundle.portable_membership,
            trusted_witness_attestations=bundle.witness_trust,
            issued_at_step=10,
        )
        with pytest.raises(GovernanceError, match="authoritative verification"):
            governance.witness_replay_receipt(rebuilt)

    assert governance.verify_distributed_commit_certificate(
        governance.distributed_commit_certificate_payload(bundle.certificate),
        commit_policy=bundle.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        expected_certificate_ref=certificate_ref,
        expected_proposal_digest=bundle.proposal.proposal_digest,
        expected_commit_value_root=bundle.proposal.commit_value_root,
    )
    assert not governance.verify_distributed_commit_certificate(
        bundle.certificate,
        commit_policy=bundle.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        expected_certificate_ref=_fingerprint("wrong-certificate"),
    )
    assert not governance.verify_distributed_commit_certificate(
        bundle.certificate,
        commit_policy=bundle.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        expected_proposal_digest=_fingerprint("wrong-proposal"),
    )
    assert not governance.verify_distributed_commit_certificate(
        bundle.certificate,
        commit_policy=bundle.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        expected_commit_value_root=_fingerprint("wrong-value"),
    )
    assert not governance.verify_distributed_commit_certificate(
        bundle.certificate,
        commit_policy=bundle.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations={},
    )
    assert not governance.verify_distributed_commit_certificate(
        bundle.certificate,
        commit_policy=bundle.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        require_final="yes",
    )

    provisional = governance.assemble_portable_distributed_commit_certificate(
        bundle.proposal,
        bundle.portable_membership,
        bundle.verifications[:2],
        commit_policy=bundle.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        certificate_id="distributed:public-portable:provisional",
        issuer_id="governance:portable-distributed",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=6,
        provenance="urn:test:portable-distributed:provisional",
        trace_event_id="trace:portable-distributed:provisional",
    )
    assert provisional.status is DistributedCertificateStatus.PROVISIONAL
    assert governance.verify_distributed_commit_certificate(
        provisional,
        commit_policy=bundle.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        require_final=False,
    )
    assert not governance.verify_distributed_commit_certificate(
        provisional,
        commit_policy=bundle.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
    )

    with pytest.raises(GovernanceError, match="needs witnesses"):
        governance.assemble_portable_distributed_commit_certificate(
            bundle.proposal,
            bundle.portable_membership,
            (),
            commit_policy=bundle.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            certificate_id="distributed:public-portable:empty",
            issuer_id="governance:portable-distributed",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=6,
            provenance="urn:test:portable-distributed:empty",
            trace_event_id="trace:portable-distributed:empty",
        )
    with pytest.raises(GovernanceError, match="governance issuer metadata"):
        governance.assemble_portable_distributed_commit_certificate(
            bundle.proposal,
            bundle.portable_membership,
            bundle.verifications,
            commit_policy=bundle.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            certificate_id="distributed:public-portable:agent",
            issuer_id="agent:portable-distributed",
            authority=AuthorityLevel.AGENT,
            issued_at_step=6,
            provenance="urn:test:portable-distributed:agent",
            trace_event_id="trace:portable-distributed:agent",
        )
    with pytest.raises(GovernanceError, match="proposal verification failed"):
        governance.assemble_portable_distributed_commit_certificate(
            other.proposal,
            other.portable_membership,
            other.verifications,
            commit_policy=bundle.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=other.witness_trust,
            certificate_id="distributed:public-portable:wrong-proposal",
            issuer_id="governance:portable-distributed",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=6,
            provenance="urn:test:portable-distributed:wrong-proposal",
            trace_event_id="trace:portable-distributed:wrong-proposal",
        )
    with pytest.raises(GovernanceError, match="signed another proposal"):
        governance.assemble_portable_distributed_commit_certificate(
            bundle.proposal,
            bundle.portable_membership,
            other.verifications,
            commit_policy=bundle.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=other.witness_trust,
            certificate_id="distributed:public-portable:wrong-witness-value",
            issuer_id="governance:portable-distributed",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=6,
            provenance="urn:test:portable-distributed:wrong-witness-value",
            trace_event_id="trace:portable-distributed:wrong-witness-value",
        )
    with pytest.raises(GovernanceError, match="witness verification failed"):
        governance.assemble_portable_distributed_commit_certificate(
            bundle.proposal,
            bundle.portable_membership,
            bundle.verifications,
            commit_policy=bundle.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations={},
            certificate_id="distributed:public-portable:untrusted-witness",
            issuer_id="governance:portable-distributed",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=6,
            provenance="urn:test:portable-distributed:untrusted-witness",
            trace_event_id="trace:portable-distributed:untrusted-witness",
        )
    with pytest.raises(GovernanceError, match="duplicate"):
        governance.assemble_portable_distributed_commit_certificate(
            bundle.proposal,
            bundle.portable_membership,
            (*bundle.verifications, bundle.verifications[0]),
            commit_policy=bundle.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            certificate_id="distributed:public-portable:duplicate",
            issuer_id="governance:portable-distributed",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=6,
            provenance="urn:test:portable-distributed:duplicate",
            trace_event_id="trace:portable-distributed:duplicate",
        )
    repeated_cluster = _portable_witness_verification(
        label="public-portable:repeated-cluster",
        proposal=bundle.proposal,
        principal=bundle.principals[0],
        portable_membership=bundle.portable_membership,
        index=91,
        witness_trust=bundle.witness_trust,
    )
    with pytest.raises(GovernanceError, match="repeats a witness cluster"):
        governance.assemble_portable_distributed_commit_certificate(
            bundle.proposal,
            bundle.portable_membership,
            (bundle.verifications[0], repeated_cluster),
            commit_policy=bundle.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            certificate_id="distributed:public-portable:repeated-cluster",
            issuer_id="governance:portable-distributed",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=6,
            provenance="urn:test:portable-distributed:repeated-cluster",
            trace_event_id="trace:portable-distributed:repeated-cluster",
        )

    certificate_payload = governance.distributed_commit_certificate_payload(
        bundle.certificate
    )
    textual_status = dict(certificate_payload)
    textual_status["status"] = "final"
    assert governance.distributed_commit_certificate_from_payload(textual_status) == (
        bundle.certificate
    )
    repeated_cluster_payload = dict(certificate_payload)
    repeated_cluster_payload["witnesses"] = (
        governance.witness_verification_payload(bundle.verifications[0]),
        governance.witness_verification_payload(repeated_cluster),
    )
    with pytest.raises(GovernanceError, match="counts a cluster twice"):
        governance.distributed_commit_certificate_from_payload(repeated_cluster_payload)
    wrong_witness_payload = dict(certificate_payload)
    wrong_witness_payload["witnesses"] = (
        governance.witness_verification_payload(other.verifications[0]),
    )
    with pytest.raises(GovernanceError, match="witness proposal mismatch"):
        governance.distributed_commit_certificate_from_payload(wrong_witness_payload)
    wrong_status_payload = dict(certificate_payload)
    wrong_status_payload["status"] = "provisional"
    with pytest.raises(GovernanceError, match="misrepresents quorum"):
        governance.distributed_commit_certificate_from_payload(wrong_status_payload)
    deserialized_state = governance.distributed_commit_state_from_payload(
        governance.distributed_commit_state_payload(bundle.state)
    )
    with pytest.raises(GovernanceError, match="current authoritative state"):
        governance.issue_distributed_commit_certificate(
            deserialized_state,
            bundle.proposal,
            verifications=bundle.verifications,
            commit_policy=bundle.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            certificate_id="distributed:public-portable:forged-state",
            issuer_id="governance:distributed-certificate",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=6,
            provenance="urn:test:distributed-certificate:forged-state",
            trace_event_id="trace:distributed-certificate:forged-state",
        )
    second_certificate = governance.assemble_portable_distributed_commit_certificate(
        bundle.proposal,
        bundle.portable_membership,
        bundle.verifications,
        commit_policy=bundle.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        certificate_id="distributed:public-portable:second",
        issuer_id="governance:portable-distributed",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=6,
        provenance="urn:test:portable-distributed:second",
        trace_event_id="trace:portable-distributed:second",
    )

    registered = governance.register_distributed_commit_certificate(
        bundle.state,
        bundle.certificate,
        commit_policy=bundle.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        current_step=6,
    )
    assert governance.distributed_commit_certificate_is_current_final(
        bundle.certificate,
        registered,
    )
    assert (
        governance.register_distributed_commit_certificate(
            bundle.state,
            bundle.certificate,
            commit_policy=bundle.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            current_step=6,
        )
        is registered
    )
    with pytest.raises(GovernanceError, match="stale or would fork"):
        governance.register_distributed_commit_certificate(
            bundle.state,
            second_certificate,
            commit_policy=bundle.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            current_step=6,
        )
    with pytest.raises(GovernanceError, match="moves backwards"):
        governance.register_distributed_commit_certificate(
            registered,
            second_certificate,
            commit_policy=bundle.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            current_step=5,
        )
    with pytest.raises(GovernanceError, match="state is forged"):
        governance.register_distributed_commit_certificate(
            deserialized_state,
            bundle.certificate,
            commit_policy=bundle.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            current_step=6,
        )
    with pytest.raises(GovernanceError, match="final certificate verification"):
        governance.register_distributed_commit_certificate(
            registered,
            provisional,
            commit_policy=bundle.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            current_step=6,
        )


def test_public_state_roundtrip_boundaries_and_forged_witness_fail_closed() -> None:
    bundle = _public_portable_scenario("public-state")
    assert governance.distributed_commit_state_is_authoritative(bundle.state)
    assert governance.distributed_commit_state_is_current(bundle.state)
    payload = governance.distributed_commit_state_payload(bundle.state)
    rebuilt = governance.distributed_commit_state_from_payload(payload)
    assert rebuilt == bundle.state
    assert not governance.distributed_commit_state_is_authoritative(rebuilt)
    assert not governance.distributed_commit_state_is_current(rebuilt)
    assert not governance.distributed_commit_state_is_authoritative(object())
    assert not governance.distributed_commit_state_is_current(object())

    assert (
        governance.initialize_distributed_commit_state(
            bundle.membership_snapshot,
            bundle.membership_state,
            commit_policy=bundle.policy,
            current_step=6,
            issuer_id="governance:distributed-state:public-state",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:distributed-state:public-state",
            trace_event_id="trace:distributed-state:public-state",
        )
        is bundle.state
    )
    with pytest.raises(GovernanceError, match="different base"):
        governance.initialize_distributed_commit_state(
            bundle.membership_snapshot,
            bundle.membership_state,
            commit_policy=bundle.policy,
            current_step=6,
            issuer_id="governance:distributed-state:public-state",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:distributed-state:changed",
            trace_event_id="trace:distributed-state:public-state",
        )
    with pytest.raises(GovernanceError, match="governance authority"):
        governance.initialize_distributed_commit_state(
            bundle.membership_snapshot,
            bundle.membership_state,
            commit_policy=bundle.policy,
            current_step=6,
            issuer_id="agent:distributed-state",
            authority=AuthorityLevel.AGENT,
            provenance="urn:test:distributed-state:agent",
            trace_event_id="trace:distributed-state:agent",
        )
    with pytest.raises(GovernanceError, match="membership is not authoritative"):
        governance.initialize_distributed_commit_state(
            bundle.membership_snapshot,
            bundle.membership_state,
            commit_policy=bundle.policy,
            current_step=20,
            issuer_id="governance:distributed-state:stale",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:distributed-state:stale",
            trace_event_id="trace:distributed-state:stale",
        )
    with pytest.raises(GovernanceError, match="membership epoch is not current"):
        governance.initialize_distributed_commit_state(
            bundle.membership_snapshot,
            replace(
                bundle.membership_state,
                provenance="urn:test:membership-epoch:forged",
            ),
            commit_policy=bundle.policy,
            current_step=6,
            issuer_id="governance:distributed-state:forged-epoch",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:distributed-state:forged-epoch",
            trace_event_id="trace:distributed-state:forged-epoch",
        )
    with pytest.raises(GovernanceError, match="not governance-issued"):
        governance.record_witness_verifications(
            rebuilt,
            (),
            current_step=6,
        )
    with pytest.raises(GovernanceError, match="forged witness"):
        governance.record_witness_verifications(
            bundle.state,
            (bundle.verifications[0],),
            current_step=6,
        )
    with pytest.raises(GovernanceError, match="move backwards"):
        governance.record_witness_verifications(
            bundle.state,
            (),
            current_step=5,
        )
    with pytest.raises(GovernanceError, match="canonical record"):
        governance.distributed_commit_state_payload(object())

    invalid_fields = {
        "profile": "pheroos-commit-integrity-v1",
        "assurance": CommitAssurance.EVIDENCE_BOUND,
        "authority": AuthorityLevel.AGENT,
        "membership_snapshot_root": _fingerprint("wrong-membership-snapshot"),
        "membership_size": 3,
        "minimum_failure_domain_diversity": 4,
        "witness_receipt_root": _fingerprint("wrong-witness-receipt"),
        "frozen": True,
        "transitioned": True,
    }
    for field_name, field_value in invalid_fields.items():
        mutated = dict(payload)
        mutated[field_name] = field_value
        with pytest.raises(GovernanceError):
            governance.distributed_commit_state_from_payload(mutated)
    wrong_size = dict(payload)
    wrong_size.update(
        {
            "membership_size": 5,
            "max_byzantine_faults": 1,
            "witness_quorum": 4,
            "minimum_failure_domain_diversity": 3,
        }
    )
    with pytest.raises(GovernanceError, match="membership size mismatch"):
        governance.distributed_commit_state_from_payload(wrong_size)
    wrong_exclusion = dict(payload)
    wrong_exclusion["excluded_cluster_ids"] = ("cluster:not-equivocated",)
    with pytest.raises(GovernanceError, match="exclusions are invalid"):
        governance.distributed_commit_state_from_payload(wrong_exclusion)
    incomplete_equivocation = dict(payload)
    incomplete_equivocation["equivocation_findings"] = (
        {
            "finding_id": _fingerprint("incomplete-equivocation"),
            "target": bundle.state.target,
            "epoch": bundle.state.epoch,
            "principal_cluster_id": "cluster:incomplete-equivocation",
            "commit_value_roots": (
                _fingerprint("equivocation-value-a"),
                _fingerprint("equivocation-value-b"),
            ),
            "proposal_digests": (
                _fingerprint("equivocation-proposal-a"),
                _fingerprint("equivocation-proposal-b"),
            ),
            "witness_fingerprints": (
                _fingerprint("equivocation-witness-a"),
                _fingerprint("equivocation-witness-b"),
            ),
        },
    )
    incomplete_equivocation["excluded_cluster_ids"] = (
        "cluster:incomplete-equivocation",
    )
    with pytest.raises(GovernanceError, match="findings are incomplete"):
        governance.distributed_commit_state_from_payload(incomplete_equivocation)
    unregistered_conflict = dict(payload)
    unregistered_conflict.update(
        {
            "final_registrations": (
                {
                    "certificate_ref": _fingerprint("registered-certificate-a"),
                    "commit_value_root": _fingerprint("registered-value-a"),
                    "proposal_digest": _fingerprint("registered-proposal-a"),
                    "candidate_id": "candidate:alpha",
                    "registered_at_step": 6,
                },
                {
                    "certificate_ref": _fingerprint("registered-certificate-b"),
                    "commit_value_root": _fingerprint("registered-value-b"),
                    "proposal_digest": _fingerprint("registered-proposal-b"),
                    "candidate_id": "candidate:beta",
                    "registered_at_step": 6,
                },
            ),
            "conflict_findings": (
                {
                    "finding_id": _fingerprint("unregistered-conflict"),
                    "target": bundle.state.target,
                    "epoch": bundle.state.epoch,
                    "certificate_refs": (
                        _fingerprint("registered-certificate-a"),
                        _fingerprint("unregistered-certificate"),
                    ),
                    "commit_value_roots": (
                        _fingerprint("registered-value-a"),
                        _fingerprint("unregistered-value"),
                    ),
                    "proposal_digests": (
                        _fingerprint("registered-proposal-a"),
                        _fingerprint("unregistered-proposal"),
                    ),
                    "candidate_ids": ("candidate:alpha", "candidate:unregistered"),
                    "detected_at_step": 6,
                },
            ),
            "frozen": True,
        }
    )
    with pytest.raises(GovernanceError, match="lineage is not registered"):
        governance.distributed_commit_state_from_payload(unregistered_conflict)
    with pytest.raises(GovernanceError, match="requires two final proofs"):
        governance.CertificateConflictFinding(
            finding_id=_fingerprint("single-proof-conflict"),
            target=bundle.state.target,
            epoch=bundle.state.epoch,
            certificate_refs=(_fingerprint("single-certificate"),),
            commit_value_roots=(_fingerprint("single-value"),),
            proposal_digests=(_fingerprint("single-proposal"),),
            candidate_ids=("candidate:alpha",),
            detected_at_step=6,
        )


def test_public_epoch_certificate_roundtrip_transition_and_boundaries() -> None:
    bundle = _public_portable_scenario("public-epoch")
    new_principals, new_snapshot, new_epoch_state = _public_membership(
        label="public-epoch:new",
        policy=bundle.policy,
        manifest_root=bundle.state.manifest_root,
        protocol_id=bundle.state.protocol_id,
        run_id=bundle.state.run_id,
        epoch=4,
    )
    assert len(new_principals) == 4
    decision_ref = governance.epoch_transition_decision_ref(
        bundle.state,
        new_snapshot,
        new_epoch_state,
        commit_policy=bundle.policy,
    )
    transition_stop, transition_permission = _public_action_gate(
        bundle,
        action=CommitAction.EPOCH_TRANSITION,
        decision_ref=decision_ref,
    )
    metadata = {
        "certificate_id": "epoch-certificate:public-epoch:4",
        "issuer_id": "governance:epoch-transition",
        "authority": AuthorityLevel.GOVERNANCE,
        "issued_at_step": 8,
        "provenance": "urn:test:epoch-transition:public",
        "trace_event_id": "trace:epoch-transition:public",
    }
    body_root = governance.epoch_transition_certificate_body_root(
        bundle.state,
        new_snapshot,
        new_epoch_state,
        transition_stop,
        transition_permission,
        commit_policy=bundle.policy,
        **metadata,
    )
    issuer_refs = ("attestation:epoch:public-epoch:4",)
    trust = {issuer_refs[0]: body_root}
    certificate = governance.issue_epoch_transition_certificate(
        bundle.state,
        new_snapshot,
        new_epoch_state,
        transition_stop,
        transition_permission,
        commit_policy=bundle.policy,
        issuer_attestation_refs=issuer_refs,
        trusted_issuer_attestations=trust,
        **metadata,
    )
    certificate_ref = governance.epoch_transition_certificate_fingerprint(certificate)
    payload = governance.epoch_transition_certificate_payload(certificate)
    rebuilt = governance.epoch_transition_certificate_from_payload(payload)
    assert rebuilt == certificate
    assert governance.verify_epoch_transition_certificate(
        payload,
        commit_policy=bundle.policy,
        trusted_issuer_attestations=trust,
        expected_certificate_ref=certificate_ref,
    )
    assert not governance.verify_epoch_transition_certificate(
        certificate,
        commit_policy=bundle.policy,
        trusted_issuer_attestations={},
    )
    assert not governance.verify_epoch_transition_certificate(
        certificate,
        commit_policy=bundle.policy,
        trusted_issuer_attestations=trust,
        expected_certificate_ref=_fingerprint("wrong-epoch-certificate"),
    )
    assert not governance.verify_epoch_transition_certificate(
        {},
        commit_policy=bundle.policy,
        trusted_issuer_attestations=trust,
    )
    changed_rule_payload = dict(payload)
    changed_rule_payload["declared_transition_rule"] = "governed-other-rule-v1"
    changed_rule_body = dict(changed_rule_payload)
    changed_rule_body.pop("issuer_attestation_refs")
    changed_rule_body.pop("certificate_body_root")
    changed_rule_body.pop("certificate_root")
    changed_rule_root = commit_payload_fingerprint(
        changed_rule_body,
        schema="pheroos-epoch-transition-certificate-body-v1",
        profile=bundle.state.profile,
    )
    changed_rule_payload["certificate_body_root"] = changed_rule_root
    changed_rule_payload["certificate_root"] = commit_payload_fingerprint(
        {
            "certificate_body_root": changed_rule_root,
            "issuer_attestation_refs": issuer_refs,
        },
        schema="pheroos-epoch-transition-certificate-envelope-v1",
        profile=bundle.state.profile,
    )
    changed_rule_certificate = governance.epoch_transition_certificate_from_payload(
        changed_rule_payload
    )
    assert not governance.verify_epoch_transition_certificate(
        changed_rule_certificate,
        commit_policy=bundle.policy,
        trusted_issuer_attestations={issuer_refs[0]: changed_rule_root},
    )
    assert (
        governance.issue_epoch_transition_certificate(
            bundle.state,
            new_snapshot,
            new_epoch_state,
            transition_stop,
            transition_permission,
            commit_policy=bundle.policy,
            issuer_attestation_refs=issuer_refs,
            trusted_issuer_attestations=trust,
            **metadata,
        )
        is certificate
    )
    with pytest.raises(GovernanceError, match="id replay"):
        changed_metadata = {
            **metadata,
            "provenance": "urn:test:epoch-transition:changed",
        }
        changed_body_root = governance.epoch_transition_certificate_body_root(
            bundle.state,
            new_snapshot,
            new_epoch_state,
            transition_stop,
            transition_permission,
            commit_policy=bundle.policy,
            **changed_metadata,
        )
        governance.issue_epoch_transition_certificate(
            bundle.state,
            new_snapshot,
            new_epoch_state,
            transition_stop,
            transition_permission,
            commit_policy=bundle.policy,
            issuer_attestation_refs=issuer_refs,
            trusted_issuer_attestations={issuer_refs[0]: changed_body_root},
            **changed_metadata,
        )

    undeclared_recovery_ref = _fingerprint("undeclared-conflict")
    recovery_decision_ref = governance.epoch_transition_decision_ref(
        bundle.state,
        new_snapshot,
        new_epoch_state,
        commit_policy=bundle.policy,
        declared_recovery_ref=undeclared_recovery_ref,
    )
    recovery_claim_stop, recovery_claim_permission = _public_action_gate(
        bundle,
        action=CommitAction.EPOCH_TRANSITION,
        decision_ref=recovery_decision_ref,
        suffix="recovery-claim",
    )
    with pytest.raises(GovernanceError, match="claim recovery authority"):
        governance.epoch_transition_certificate_body_root(
            bundle.state,
            new_snapshot,
            new_epoch_state,
            recovery_claim_stop,
            recovery_claim_permission,
            commit_policy=bundle.policy,
            declared_recovery_ref=undeclared_recovery_ref,
            **metadata,
        )
    with pytest.raises(GovernanceError, match="governance authority"):
        governance.epoch_transition_certificate_body_root(
            bundle.state,
            new_snapshot,
            new_epoch_state,
            transition_stop,
            transition_permission,
            commit_policy=bundle.policy,
            **{**metadata, "authority": AuthorityLevel.AGENT},
        )
    with pytest.raises(GovernanceError, match="attestation"):
        governance.issue_epoch_transition_certificate(
            bundle.state,
            new_snapshot,
            new_epoch_state,
            transition_stop,
            transition_permission,
            commit_policy=bundle.policy,
            issuer_attestation_refs=issuer_refs,
            trusted_issuer_attestations={},
            **{**metadata, "certificate_id": "epoch-certificate:missing-trust"},
        )
    with pytest.raises(GovernanceError, match="canonical record"):
        governance.epoch_transition_certificate_payload(object())

    invalid_fields = {
        "schema_discriminator": "wrong-epoch-certificate",
        "certificate_version": "pheroos-epoch-transition-certificate-v0",
        "wire_version": "pheroos-commit-wire-v0",
        "canonicalization": "pheroos-canonical-json-v0",
        "hash_algorithm": "sha512",
        "profile": "pheroos-commit-integrity-v1",
        "assurance": CommitAssurance.EVIDENCE_BOUND,
        "authority": AuthorityLevel.AGENT,
        "new_epoch": certificate.previous_epoch,
        "declared_recovery_ref": _fingerprint("unexpected-recovery"),
        "new_membership_root": _fingerprint("wrong-new-membership"),
        "certificate_body_root": _fingerprint("wrong-epoch-body"),
        "certificate_root": _fingerprint("wrong-epoch-envelope"),
    }
    for field_name, field_value in invalid_fields.items():
        mutated = dict(payload)
        mutated[field_name] = field_value
        with pytest.raises(GovernanceError):
            governance.epoch_transition_certificate_from_payload(mutated)

    with pytest.raises(GovernanceError, match="must advance epoch"):
        governance.epoch_transition_decision_ref(
            bundle.state,
            bundle.membership_snapshot,
            bundle.membership_state,
            commit_policy=bundle.policy,
        )
    with pytest.raises(GovernanceError, match="not authoritative"):
        governance.epoch_transition_decision_ref(
            bundle.state,
            replace(new_snapshot, snapshot_id="membership:forged"),
            new_epoch_state,
            commit_policy=bundle.policy,
        )
    with pytest.raises(GovernanceError, match="certificate verification failed"):
        governance.transition_distributed_commit_epoch(
            bundle.state,
            certificate,
            new_snapshot,
            new_epoch_state,
            commit_policy=bundle.policy,
            trusted_issuer_attestations={},
            issuer_id="governance:distributed-state:untrusted",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:distributed-state:untrusted",
            trace_event_id="trace:distributed-state:untrusted",
        )
    with pytest.raises(GovernanceError, match="lineage mismatch"):
        governance.transition_distributed_commit_epoch(
            bundle.state,
            certificate,
            bundle.membership_snapshot,
            bundle.membership_state,
            commit_policy=bundle.policy,
            trusted_issuer_attestations=trust,
            issuer_id="governance:distributed-state:wrong-lineage",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:distributed-state:wrong-lineage",
            trace_event_id="trace:distributed-state:wrong-lineage",
        )

    transitioned, new_state = governance.transition_distributed_commit_epoch(
        bundle.state,
        certificate,
        new_snapshot,
        new_epoch_state,
        commit_policy=bundle.policy,
        trusted_issuer_attestations=trust,
        issuer_id="governance:distributed-state:public-epoch:4",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:distributed-state:public-epoch:4",
        trace_event_id="trace:distributed-state:public-epoch:4",
    )
    assert transitioned.transitioned is True
    assert transitioned.epoch_transition_certificate_ref == certificate_ref
    assert new_state.epoch == 4
    assert governance.distributed_commit_state_is_current(new_state)
    with pytest.raises(GovernanceError, match="current state"):
        governance.epoch_transition_decision_ref(
            bundle.state,
            new_snapshot,
            new_epoch_state,
            commit_policy=bundle.policy,
        )
    with pytest.raises(GovernanceError, match="already transitioned"):
        governance.epoch_transition_certificate_body_root(
            transitioned,
            new_snapshot,
            new_epoch_state,
            transition_stop,
            transition_permission,
            commit_policy=bundle.policy,
            **{**metadata, "certificate_id": "epoch-certificate:already-transitioned"},
        )
    with pytest.raises(GovernanceError, match="state is not current"):
        governance.transition_distributed_commit_epoch(
            bundle.state,
            certificate,
            new_snapshot,
            new_epoch_state,
            commit_policy=bundle.policy,
            trusted_issuer_attestations=trust,
            issuer_id="governance:distributed-state:public-epoch:4",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:distributed-state:public-epoch:4",
            trace_event_id="trace:distributed-state:public-epoch:4",
        )


def test_static_byzantine_policy_and_full_proposal_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _distributed_scenario(monkeypatch)
    policy = bundle.scenario.policy.distributed
    assert policy.membership_size == 4
    assert policy.max_byzantine_faults == 1
    assert policy.witness_quorum == 3
    assert 2 * policy.witness_quorum - policy.membership_size > (
        policy.max_byzantine_faults
    )

    semantic_payload = distributed_commit_value_payload(bundle.proposal)
    wire_semantic_payload = json.loads(json.dumps(semantic_payload))
    assert wire_semantic_payload["assurance"] == "distributed"
    assert distributed_commit_value_root(wire_semantic_payload) == (
        bundle.proposal.commit_value_root
    )
    with pytest.raises(GovernanceError, match="assurance"):
        distributed_commit_value_root(
            {**wire_semantic_payload, "assurance": "unknown-assurance"}
        )

    payload = distributed_commit_proposal_payload(bundle.proposal)
    rebuilt = distributed_commit_proposal_from_payload(payload)
    assert rebuilt == bundle.proposal
    rebuilt_state = distributed_commit_state_from_payload(
        distributed_commit_state_payload(bundle.state)
    )
    assert distributed_commit_state_fingerprint(rebuilt_state) == (
        distributed_commit_state_fingerprint(bundle.state)
    )
    assert not distributed_commit_state_is_current(rebuilt_state)
    assert (
        issue_distributed_commit_proposal(
            bundle.receipt,
            bundle.portable_certificate,
            bundle.scenario.membership_snapshot,
            bundle.scenario.membership_state,
            commit_policy=bundle.scenario.policy,
            trusted_issuer_attestations=bundle.issuer_trust,
            proposal_id=bundle.proposal.proposal_id,
            proposed_at_step=6,
        )
        is bundle.proposal
    )
    with pytest.raises(GovernanceError, match="proposal id replay"):
        issue_distributed_commit_proposal(
            bundle.receipt,
            bundle.portable_certificate,
            bundle.scenario.membership_snapshot,
            bundle.scenario.membership_state,
            commit_policy=bundle.scenario.policy,
            trusted_issuer_attestations=bundle.issuer_trust,
            proposal_id=bundle.proposal.proposal_id,
            proposed_at_step=7,
        )
    for field_name in (
        "manifest_root",
        "commit_policy_root",
        "risk_chain_state_root",
        "risk_assessment_root",
        "risk_policy_root",
        "membership_snapshot_root",
        "membership_epoch_state_root",
        "membership_root",
        "evidence_root",
        "lease_root",
        "challenge_root",
        "window_state_root",
        "window_root",
        "threshold_root",
        "stop_resolution_root",
        "permission_root",
        "portable_certificate_ref",
    ):
        mutated = dict(payload)
        mutated[field_name] = _fingerprint(f"mutated:{field_name}")
        with pytest.raises(GovernanceError):
            distributed_commit_proposal_from_payload(mutated)

    unsafe_policy = replace(
        bundle.scenario.policy,
        distributed=replace(policy, witness_quorum=2),
    )
    with pytest.raises(GovernanceError, match="Byzantine|intersection|policy"):
        initialize_distributed_commit_state(
            bundle.scenario.membership_snapshot,
            bundle.scenario.membership_state,
            commit_policy=unsafe_policy,
            current_step=7,
            issuer_id="governance:unsafe",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:unsafe",
            trace_event_id="trace:unsafe",
        )


def test_witness_verification_replay_scope_idempotence_and_permutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _distributed_scenario(monkeypatch)
    first = bundle.verifications[0]
    witness = first.witness
    repeated = verify_quorum_witness(
        witness,
        bundle.proposal,
        bundle.principals[0],
        bundle.scenario.membership_snapshot,
        bundle.scenario.membership_state,
        commit_policy=bundle.scenario.policy,
        trusted_witness_attestations=bundle.witness_trust,
        verification_id=first.verification_id,
        verifier_id=first.verifier_id,
        authority=first.authority,
        verified_at_step=first.verified_at_step,
        provenance=first.provenance,
        trace_event_id=first.trace_event_id,
    )
    assert repeated is first
    assert (
        record_witness_verifications(
            bundle.state,
            tuple(reversed(bundle.verifications)),
            current_step=6,
        )
        is bundle.state
    )
    with pytest.raises(GovernanceError, match="stale witness verification"):
        record_witness_verifications(
            bundle.state,
            (first,),
            current_step=10,
        )

    for changes in (
        {"epoch": witness.epoch + 1},
        {"target": "decision:other-target"},
        {"candidate_id": "candidate:other"},
        {"proposal_digest": _fingerprint("other-proposal")},
    ):
        forged = replace(witness, **changes)
        with pytest.raises(GovernanceError):
            verify_quorum_witness(
                forged,
                bundle.proposal,
                bundle.principals[0],
                bundle.scenario.membership_snapshot,
                bundle.scenario.membership_state,
                commit_policy=bundle.scenario.policy,
                trusted_witness_attestations=bundle.witness_trust,
                verification_id=f"verification:forged:{next(iter(changes))}",
                verifier_id="governance:witness-verifier",
                authority=AuthorityLevel.GOVERNANCE,
                verified_at_step=6,
                provenance="urn:test:forged",
                trace_event_id="trace:forged",
            )

    collision = replace(
        witness,
        witness_id=f"{witness.witness_id}:collision",
        attestation_ref=f"{witness.attestation_ref}:collision",
    )
    bundle.witness_trust[collision.attestation_ref] = quorum_witness_signing_root(
        collision
    )
    with pytest.raises(GovernanceError, match="replay collision"):
        verify_quorum_witness(
            collision,
            bundle.proposal,
            bundle.principals[0],
            bundle.scenario.membership_snapshot,
            bundle.scenario.membership_state,
            commit_policy=bundle.scenario.policy,
            trusted_witness_attestations=bundle.witness_trust,
            verification_id=f"{first.verification_id}:collision",
            verifier_id=first.verifier_id,
            authority=first.authority,
            verified_at_step=first.verified_at_step,
            provenance=first.provenance,
            trace_event_id=first.trace_event_id,
        )

    witness_payload = governance.quorum_witness_payload(witness)
    assert governance.quorum_witness_from_payload(witness_payload) == witness
    verification_payload = governance.witness_verification_payload(first)
    rebuilt = governance.witness_verification_from_payload(verification_payload)
    assert rebuilt == first
    assert governance.witness_verification_is_authoritative(first)
    assert not governance.witness_verification_is_authoritative(rebuilt)
    assert not governance.witness_verification_is_authoritative(object())
    assert governance.verify_portable_witness_verification(
        verification_payload,
        membership_snapshot=governance.portable_membership_snapshot_from_eligible(
            bundle.scenario.membership_snapshot
        ),
        trusted_witness_attestations=bundle.witness_trust,
        issued_at_step=6,
    )
    replay = governance.witness_replay_receipt(first)
    replay_payload = governance.witness_replay_receipt_payload(replay)
    replay_rebuilt = governance.witness_replay_receipt_from_payload(replay_payload)
    assert replay_rebuilt == replay
    assert governance.witness_replay_receipt_fingerprint(
        replay,
        profile=witness.profile,
    ) == governance.witness_replay_receipt_fingerprint(
        replay_rebuilt,
        profile=witness.profile,
    )
    with pytest.raises(GovernanceError, match="canonical record"):
        governance.quorum_witness_payload(object())
    with pytest.raises(GovernanceError, match="canonical record"):
        governance.quorum_witness_signing_payload(object())
    with pytest.raises(GovernanceError, match="canonical record"):
        governance.witness_verification_payload(object())
    with pytest.raises(GovernanceError, match="canonical record"):
        governance.witness_replay_receipt_payload(object())
    invalid_replay_payload = dict(replay_payload)
    invalid_replay_payload["verification_id"] = ""
    with pytest.raises(GovernanceError, match="payload is invalid"):
        governance.witness_replay_receipt_from_payload(invalid_replay_payload)
    assert not governance.verify_portable_witness_verification(
        {},
        membership_snapshot=governance.portable_membership_snapshot_from_eligible(
            bundle.scenario.membership_snapshot
        ),
        trusted_witness_attestations=bundle.witness_trust,
        issued_at_step=6,
    )

    for field_name, field_value in {
        "verification_version": "pheroos-witness-verification-v0",
        "witness_fingerprint": _fingerprint("wrong-witness"),
        "witness_signing_root": _fingerprint("wrong-signing-root"),
        "expires_at_step": first.verified_at_step,
        "authority": AuthorityLevel.AGENT,
    }.items():
        mutated = dict(verification_payload)
        mutated[field_name] = field_value
        with pytest.raises(GovernanceError):
            governance.witness_verification_from_payload(mutated)

    with pytest.raises(GovernanceError, match="governance-issued proposal"):
        verify_quorum_witness(
            witness,
            governance.distributed_commit_proposal_from_payload(
                governance.distributed_commit_proposal_payload(bundle.proposal)
            ),
            bundle.principals[0],
            bundle.scenario.membership_snapshot,
            bundle.scenario.membership_state,
            commit_policy=bundle.scenario.policy,
            trusted_witness_attestations=bundle.witness_trust,
            verification_id="verification:portable-proposal",
            verifier_id="governance:witness-verifier",
            authority=AuthorityLevel.GOVERNANCE,
            verified_at_step=6,
            provenance="urn:test:portable-proposal",
            trace_event_id="trace:portable-proposal",
        )
    with pytest.raises(GovernanceError, match="QuorumWitness"):
        verify_quorum_witness(
            object(),
            bundle.proposal,
            bundle.principals[0],
            bundle.scenario.membership_snapshot,
            bundle.scenario.membership_state,
            commit_policy=bundle.scenario.policy,
            trusted_witness_attestations=bundle.witness_trust,
            verification_id="verification:wrong-witness-type",
            verifier_id="governance:witness-verifier",
            authority=AuthorityLevel.GOVERNANCE,
            verified_at_step=6,
            provenance="urn:test:wrong-witness-type",
            trace_event_id="trace:wrong-witness-type",
        )
    with pytest.raises(GovernanceError, match="governance authority"):
        verify_quorum_witness(
            witness,
            bundle.proposal,
            bundle.principals[0],
            bundle.scenario.membership_snapshot,
            bundle.scenario.membership_state,
            commit_policy=bundle.scenario.policy,
            trusted_witness_attestations=bundle.witness_trust,
            verification_id="verification:agent",
            verifier_id="agent:witness-verifier",
            authority=AuthorityLevel.AGENT,
            verified_at_step=6,
            provenance="urn:test:agent",
            trace_event_id="trace:agent",
        )
    with pytest.raises(GovernanceError, match="declared witness TTL"):
        verify_quorum_witness(
            replace(witness, expires_at_step=11),
            bundle.proposal,
            bundle.principals[0],
            bundle.scenario.membership_snapshot,
            bundle.scenario.membership_state,
            commit_policy=bundle.scenario.policy,
            trusted_witness_attestations=bundle.witness_trust,
            verification_id="verification:excessive-ttl",
            verifier_id="governance:witness-verifier",
            authority=AuthorityLevel.GOVERNANCE,
            verified_at_step=6,
            provenance="urn:test:excessive-ttl",
            trace_event_id="trace:excessive-ttl",
        )
    with pytest.raises(GovernanceError, match="stale at verification"):
        verify_quorum_witness(
            witness,
            bundle.proposal,
            bundle.principals[0],
            bundle.scenario.membership_snapshot,
            bundle.scenario.membership_state,
            commit_policy=bundle.scenario.policy,
            trusted_witness_attestations=bundle.witness_trust,
            verification_id="verification:stale",
            verifier_id="governance:witness-verifier",
            authority=AuthorityLevel.GOVERNANCE,
            verified_at_step=10,
            provenance="urn:test:stale",
            trace_event_id="trace:stale",
        )
    with pytest.raises(GovernanceError, match="membership is not authoritative"):
        stale_membership_witness = replace(
            witness,
            witness_id=f"{witness.witness_id}:stale-membership",
            nonce=f"{witness.nonce}:stale-membership",
            witnessed_at_step=20,
            expires_at_step=24,
            attestation_ref=f"{witness.attestation_ref}:stale-membership",
        )
        verify_quorum_witness(
            stale_membership_witness,
            bundle.proposal,
            bundle.principals[0],
            bundle.scenario.membership_snapshot,
            bundle.scenario.membership_state,
            commit_policy=bundle.scenario.policy,
            trusted_witness_attestations={},
            verification_id="verification:stale-membership",
            verifier_id="governance:witness-verifier",
            authority=AuthorityLevel.GOVERNANCE,
            verified_at_step=20,
            provenance="urn:test:stale-membership",
            trace_event_id="trace:stale-membership",
        )
    with pytest.raises(GovernanceError, match="outside membership"):
        outsider = replace(
            witness,
            witness_id=f"{witness.witness_id}:outsider",
            principal_id="principal:outside-membership",
            nonce=f"{witness.nonce}:outsider",
            attestation_ref=f"{witness.attestation_ref}:outsider",
        )
        outsider_trust = {
            outsider.attestation_ref: governance.quorum_witness_signing_root(outsider)
        }
        verify_quorum_witness(
            outsider,
            bundle.proposal,
            bundle.principals[0],
            bundle.scenario.membership_snapshot,
            bundle.scenario.membership_state,
            commit_policy=bundle.scenario.policy,
            trusted_witness_attestations=outsider_trust,
            verification_id="verification:outsider",
            verifier_id="governance:witness-verifier",
            authority=AuthorityLevel.GOVERNANCE,
            verified_at_step=6,
            provenance="urn:test:outsider",
            trace_event_id="trace:outsider",
        )
    outsider_signing_root = governance.quorum_witness_signing_root(outsider)
    outsider_verification_payload = {
        **verification_payload,
        "verification_id": "verification:portable-outsider",
        "witness": governance.quorum_witness_payload(outsider),
        "witness_fingerprint": governance.quorum_witness_fingerprint(outsider),
        "witness_signing_root": outsider_signing_root,
    }
    outsider_verification = governance.witness_verification_from_payload(
        outsider_verification_payload
    )
    assert not governance.verify_portable_witness_verification(
        outsider_verification,
        membership_snapshot=governance.portable_membership_snapshot_from_eligible(
            bundle.scenario.membership_snapshot
        ),
        trusted_witness_attestations={outsider.attestation_ref: outsider_signing_root},
        issued_at_step=6,
    )
    with pytest.raises(GovernanceError, match="cluster/failure-domain mismatch"):
        wrong_cluster = replace(
            witness,
            witness_id=f"{witness.witness_id}:wrong-cluster",
            principal_cluster_id="cluster:wrong",
            nonce=f"{witness.nonce}:wrong-cluster",
            attestation_ref=f"{witness.attestation_ref}:wrong-cluster",
        )
        wrong_cluster_trust = {
            wrong_cluster.attestation_ref: (
                governance.quorum_witness_signing_root(wrong_cluster)
            )
        }
        verify_quorum_witness(
            wrong_cluster,
            bundle.proposal,
            bundle.principals[0],
            bundle.scenario.membership_snapshot,
            bundle.scenario.membership_state,
            commit_policy=bundle.scenario.policy,
            trusted_witness_attestations=wrong_cluster_trust,
            verification_id="verification:wrong-cluster",
            verifier_id="governance:witness-verifier",
            authority=AuthorityLevel.GOVERNANCE,
            verified_at_step=6,
            provenance="urn:test:wrong-cluster",
            trace_event_id="trace:wrong-cluster",
        )
    wrong_cluster_signing_root = governance.quorum_witness_signing_root(wrong_cluster)
    wrong_cluster_verification_payload = {
        **verification_payload,
        "verification_id": "verification:portable-wrong-cluster",
        "witness": governance.quorum_witness_payload(wrong_cluster),
        "witness_fingerprint": governance.quorum_witness_fingerprint(wrong_cluster),
        "witness_signing_root": wrong_cluster_signing_root,
    }
    wrong_cluster_verification = governance.witness_verification_from_payload(
        wrong_cluster_verification_payload
    )
    assert not governance.verify_portable_witness_verification(
        wrong_cluster_verification,
        membership_snapshot=governance.portable_membership_snapshot_from_eligible(
            bundle.scenario.membership_snapshot
        ),
        trusted_witness_attestations={
            wrong_cluster.attestation_ref: wrong_cluster_signing_root
        },
        issued_at_step=6,
    )
    with pytest.raises(GovernanceError, match="principal verification is forged"):
        verify_quorum_witness(
            witness,
            bundle.proposal,
            replace(
                bundle.principals[0],
                provenance="urn:test:principal-verification:forged",
            ),
            bundle.scenario.membership_snapshot,
            bundle.scenario.membership_state,
            commit_policy=bundle.scenario.policy,
            trusted_witness_attestations=bundle.witness_trust,
            verification_id="verification:forged-principal",
            verifier_id="governance:witness-verifier",
            authority=AuthorityLevel.GOVERNANCE,
            verified_at_step=6,
            provenance="urn:test:forged-principal",
            trace_event_id="trace:forged-principal",
        )
    with pytest.raises(GovernanceError, match="principal verification mismatch"):
        verify_quorum_witness(
            witness,
            bundle.proposal,
            bundle.principals[1],
            bundle.scenario.membership_snapshot,
            bundle.scenario.membership_state,
            commit_policy=bundle.scenario.policy,
            trusted_witness_attestations=bundle.witness_trust,
            verification_id="verification:wrong-principal",
            verifier_id="governance:witness-verifier",
            authority=AuthorityLevel.GOVERNANCE,
            verified_at_step=6,
            provenance="urn:test:wrong-principal",
            trace_event_id="trace:wrong-principal",
        )
    with pytest.raises(GovernanceError, match="attestation verification failed"):
        verify_quorum_witness(
            witness,
            bundle.proposal,
            bundle.principals[0],
            bundle.scenario.membership_snapshot,
            bundle.scenario.membership_state,
            commit_policy=bundle.scenario.policy,
            trusted_witness_attestations={},
            verification_id="verification:untrusted",
            verifier_id="governance:witness-verifier",
            authority=AuthorityLevel.GOVERNANCE,
            verified_at_step=6,
            provenance="urn:test:untrusted",
            trace_event_id="trace:untrusted",
        )

    finding = governance.WitnessEquivocationFinding(
        finding_id=_fingerprint("finding"),
        target=witness.target,
        epoch=witness.epoch,
        principal_cluster_id=witness.principal_cluster_id,
        commit_value_roots=(
            _fingerprint("value-b"),
            _fingerprint("value-a"),
        ),
        proposal_digests=(
            _fingerprint("proposal-b"),
            _fingerprint("proposal-a"),
        ),
        witness_fingerprints=(
            _fingerprint("witness-b"),
            _fingerprint("witness-a"),
        ),
    )
    assert finding.commit_value_roots == tuple(sorted(finding.commit_value_roots))
    with pytest.raises(GovernanceError, match="conflicting commit values"):
        governance.WitnessEquivocationFinding(
            finding_id=_fingerprint("not-a-finding"),
            target=witness.target,
            epoch=witness.epoch,
            principal_cluster_id=witness.principal_cluster_id,
            commit_value_roots=(_fingerprint("only-value"),),
            proposal_digests=(_fingerprint("only-proposal"),),
            witness_fingerprints=(_fingerprint("only-witness"),),
        )


def test_same_value_retries_do_not_equivocate_and_provisional_is_nonterminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _distributed_scenario(monkeypatch)
    proposal_two = issue_distributed_commit_proposal(
        bundle.receipt,
        bundle.portable_certificate,
        bundle.scenario.membership_snapshot,
        bundle.scenario.membership_state,
        commit_policy=bundle.scenario.policy,
        trusted_issuer_attestations=bundle.issuer_trust,
        proposal_id=f"proposal:{bundle.scenario.run_id}:revised",
        proposed_at_step=6,
    )
    conflicting = _witness_verification(
        bundle.scenario,
        proposal_two,
        bundle.principals[0],
        index=51,
        witness_trust=bundle.witness_trust,
    )
    state = record_witness_verifications(
        bundle.state,
        (conflicting,),
        current_step=6,
    )
    assert (
        record_witness_verifications(
            bundle.state,
            (conflicting,),
            current_step=6,
        )
        is state
    )
    assert (
        record_witness_verifications(
            bundle.state,
            (),
            current_step=6,
        )
        is state
    )
    third_proposal = issue_distributed_commit_proposal(
        bundle.receipt,
        bundle.portable_certificate,
        bundle.scenario.membership_snapshot,
        bundle.scenario.membership_state,
        commit_policy=bundle.scenario.policy,
        trusted_issuer_attestations=bundle.issuer_trust,
        proposal_id=f"proposal:{bundle.scenario.run_id}:third-fork",
        proposed_at_step=6,
    )
    third_verification = _witness_verification(
        bundle.scenario,
        third_proposal,
        bundle.principals[1],
        index=52,
        witness_trust=bundle.witness_trust,
    )
    with pytest.raises(GovernanceError, match="stale or would fork"):
        record_witness_verifications(
            bundle.state,
            (third_verification,),
            current_step=6,
        )
    assert proposal_two.proposal_digest != bundle.proposal.proposal_digest
    assert proposal_two.commit_value_root == bundle.proposal.commit_value_root
    assert bundle.principals[0].cluster_id not in state.excluded_cluster_ids
    assert not state.equivocation_findings

    local_view = replace(bundle, state=state)
    provisional = _certificate(
        local_view,
        bundle.verifications[:2],
        suffix="same-value-provisional",
    )
    assert provisional.status is DistributedCertificateStatus.PROVISIONAL
    decision = evaluate_distributed_finality(
        state,
        bundle.receipt,
        certificate=provisional,
        current_step=6,
    )
    assert decision.kind is DistributedFinalityKind.PROVISIONAL
    assert decision.terminal is False
    assert decision.authoritative_commit is False
    provisional_payload = governance.distributed_finality_decision_payload(decision)
    assert governance.distributed_finality_decision_is_authoritative(decision)
    assert (
        governance.distributed_finality_decision_from_payload(provisional_payload)
        == decision
    )
    missing_proof = dict(provisional_payload)
    missing_proof["distributed_certificate_ref"] = ""
    with pytest.raises(GovernanceError, match="requires its proof"):
        governance.distributed_finality_decision_from_payload(missing_proof)
    assert not verify_distributed_commit_certificate(
        provisional,
        commit_policy=bundle.scenario.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        require_final=True,
    )


def test_final_certificate_roundtrip_permutation_and_leaf_mutations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _distributed_scenario(monkeypatch)
    provisional = _certificate(
        bundle,
        tuple(reversed(bundle.verifications[:2])),
        suffix="provisional",
    )
    assert provisional.status is DistributedCertificateStatus.PROVISIONAL
    assert verify_distributed_commit_certificate(
        provisional,
        commit_policy=bundle.scenario.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        require_final=False,
    )

    final = _certificate(
        bundle,
        tuple(reversed(bundle.verifications[:3])),
        suffix="final",
    )
    reordered = _certificate(
        bundle,
        bundle.verifications[:3],
        suffix="final",
    )
    assert final.status is DistributedCertificateStatus.FINAL
    assert reordered is final
    assert final.witness_root == reordered.witness_root
    assert final.certificate_root == reordered.certificate_root
    payload = distributed_commit_certificate_payload(final)
    rebuilt = distributed_commit_certificate_from_payload(payload)
    assert rebuilt == final
    assert verify_distributed_commit_certificate(
        payload,
        commit_policy=bundle.scenario.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
    )
    with pytest.raises(GovernanceError, match="certificate id replay"):
        issue_distributed_commit_certificate(
            bundle.state,
            bundle.proposal,
            verifications=bundle.verifications[:2],
            commit_policy=bundle.scenario.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            certificate_id=final.certificate_id,
            issuer_id=final.issuer_id,
            authority=final.authority,
            issued_at_step=final.issued_at_step,
            provenance=final.provenance,
            trace_event_id=final.trace_event_id,
        )
    assert not distributed_commit_certificate_is_current_final(final, bundle.state)
    assert not distributed_commit_certificate_is_current_final(
        provisional, bundle.state
    )
    assert not distributed_commit_certificate_is_current_final(object(), bundle.state)
    assert not distributed_commit_certificate_is_current_final(final, object())
    assert verify_distributed_commit_certificate(
        final,
        commit_policy=bundle.scenario.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        expected_certificate_ref=distributed_commit_certificate_fingerprint(final),
        expected_proposal_digest=final.proposal_digest,
        expected_commit_value_root=final.commit_value_root,
    )
    for expected_argument in (
        {"expected_certificate_ref": _fingerprint("wrong-certificate")},
        {"expected_proposal_digest": _fingerprint("wrong-proposal")},
        {"expected_commit_value_root": _fingerprint("wrong-value")},
    ):
        assert not verify_distributed_commit_certificate(
            final,
            commit_policy=bundle.scenario.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            **expected_argument,
        )
    with pytest.raises(GovernanceError, match="canonical record"):
        distributed_commit_certificate_payload(object())
    with pytest.raises(GovernanceError, match="at least one verified witness"):
        issue_distributed_commit_certificate(
            bundle.state,
            bundle.proposal,
            verifications=(),
            commit_policy=bundle.scenario.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            certificate_id="distributed:empty",
            issuer_id="governance:distributed-certificate",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=6,
            provenance="urn:test:distributed-certificate:empty",
            trace_event_id="trace:distributed-certificate:empty",
        )
    with pytest.raises(GovernanceError, match="canonical verification records"):
        issue_distributed_commit_certificate(
            bundle.state,
            bundle.proposal,
            verifications=(object(),),
            commit_policy=bundle.scenario.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            certificate_id="distributed:wrong-witness-type",
            issuer_id="governance:distributed-certificate",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=6,
            provenance="urn:test:distributed-certificate:wrong-witness-type",
            trace_event_id="trace:distributed-certificate:wrong-witness-type",
        )
    with pytest.raises(GovernanceError, match="governance authority"):
        issue_distributed_commit_certificate(
            bundle.state,
            bundle.proposal,
            verifications=bundle.verifications[:3],
            commit_policy=bundle.scenario.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            certificate_id="distributed:agent",
            issuer_id="agent:distributed-certificate",
            authority=AuthorityLevel.AGENT,
            issued_at_step=6,
            provenance="urn:test:distributed-certificate:agent",
            trace_event_id="trace:distributed-certificate:agent",
        )
    with pytest.raises(GovernanceError, match="portable/fresh"):
        issue_distributed_commit_certificate(
            bundle.state,
            bundle.proposal,
            verifications=bundle.verifications[:3],
            commit_policy=bundle.scenario.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            certificate_id="distributed:stale-witnesses",
            issuer_id="governance:distributed-certificate",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=10,
            provenance="urn:test:distributed-certificate:stale",
            trace_event_id="trace:distributed-certificate:stale",
        )
    with pytest.raises(GovernanceError, match="unrecorded witness"):
        issue_distributed_commit_certificate(
            bundle.state,
            bundle.proposal,
            verifications=(
                governance.witness_verification_from_payload(
                    governance.witness_verification_payload(bundle.verifications[0])
                ),
            ),
            commit_policy=bundle.scenario.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            certificate_id="distributed:portable-only",
            issuer_id="governance:distributed-certificate",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=6,
            provenance="urn:test:distributed-certificate:portable-only",
            trace_event_id="trace:distributed-certificate:portable-only",
        )

    invalid_fields = {
        "schema_discriminator": "wrong-distributed-certificate",
        "certificate_version": "pheroos-distributed-commit-certificate-v0",
        "wire_version": "pheroos-commit-wire-v0",
        "canonicalization": "pheroos-canonical-json-v0",
        "hash_algorithm": "sha512",
        "profile": "pheroos-commit-integrity-v1",
        "assurance": CommitAssurance.EVIDENCE_BOUND,
        "status": "unknown",
        "authority": AuthorityLevel.AGENT,
        "membership_size": 3,
        "issued_at_step": 20,
        "minimum_failure_domain_diversity": 4,
        "witnesses": (),
        "excluded_cluster_ids": (final.witnesses[0].witness.principal_cluster_id,),
        "witness_root": _fingerprint("wrong-witness-root"),
        "certificate_body_root": _fingerprint("wrong-certificate-body"),
        "certificate_root": _fingerprint("wrong-certificate-root"),
    }
    for field_name, field_value in invalid_fields.items():
        mutated = dict(payload)
        mutated[field_name] = field_value
        with pytest.raises(GovernanceError):
            distributed_commit_certificate_from_payload(mutated)

    paths = tuple(_scalar_leaf_paths(payload))
    assert len(paths) > 150
    for path in paths:
        mutated = _mutable(deepcopy(payload))
        _mutate_leaf(mutated, path)
        assert not verify_distributed_commit_certificate(
            mutated,
            commit_policy=bundle.scenario.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
        ), path


def test_finality_order_is_certificate_then_typed_liveness_then_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _distributed_scenario(monkeypatch)
    certificate = _certificate(
        bundle,
        bundle.verifications[:3],
        suffix="ordering",
    )
    with pytest.raises(GovernanceError, match="registered/current"):
        evaluate_distributed_finality(
            bundle.state,
            bundle.receipt,
            certificate=certificate,
            current_step=6,
        )
    registered = register_distributed_commit_certificate(
        bundle.state,
        certificate,
        commit_policy=bundle.scenario.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        current_step=6,
    )
    assert distributed_commit_certificate_is_current_final(certificate, registered)
    preterminal = evaluate_distributed_finality(
        registered,
        bundle.receipt,
        certificate=certificate,
        current_step=6,
    )
    assert preterminal.kind is DistributedFinalityKind.FINAL
    assert preterminal.terminal is False
    assert preterminal.authoritative_commit is True
    preterminal_payload = governance.distributed_finality_decision_payload(preterminal)
    preterminal_rebuilt = governance.distributed_finality_decision_from_payload(
        preterminal_payload
    )
    assert preterminal_rebuilt == preterminal
    assert governance.distributed_finality_decision_is_authoritative(preterminal)
    assert not governance.distributed_finality_decision_is_authoritative(
        preterminal_rebuilt
    )
    assert not governance.distributed_finality_decision_is_authoritative(object())
    assert governance.distributed_finality_decision_fingerprint(preterminal) == (
        governance.distributed_finality_decision_fingerprint(preterminal_rebuilt)
    )
    textual_kind = dict(preterminal_payload)
    textual_kind["kind"] = "final"
    assert governance.distributed_finality_decision_from_payload(textual_kind) == (
        preterminal
    )
    with pytest.raises(GovernanceError, match="kind is invalid"):
        governance.DistributedFinalityDecision(
            **{**preterminal_payload, "kind": "final"}
        )
    with pytest.raises(GovernanceError, match="must be canonical"):
        governance.distributed_finality_decision_payload(object())
    for field_name, field_value in {
        "decision_version": "pheroos-distributed-finality-decision-v0",
        "kind": "unknown",
        "terminal": 1,
        "profile": "pheroos-commit-integrity-v1",
        "assurance": CommitAssurance.EVIDENCE_BOUND,
        "authoritative_commit": False,
        "distributed_certificate_ref": "",
    }.items():
        mutated = dict(preterminal_payload)
        mutated[field_name] = field_value
        with pytest.raises(GovernanceError):
            governance.distributed_finality_decision_from_payload(mutated)
    non_final_authority = dict(preterminal_payload)
    non_final_authority["kind"] = DistributedFinalityKind.SAFETY_VIOLATION
    with pytest.raises(GovernanceError, match="non-final"):
        governance.distributed_finality_decision_from_payload(non_final_authority)
    with pytest.raises(GovernanceError, match="move backwards"):
        evaluate_distributed_finality(
            registered,
            bundle.receipt,
            certificate=certificate,
            current_step=5,
        )
    with pytest.raises(GovernanceError, match="requires current state"):
        evaluate_distributed_finality(
            governance.distributed_commit_state_from_payload(
                governance.distributed_commit_state_payload(registered)
            ),
            bundle.receipt,
            certificate=certificate,
            current_step=6,
        )
    with pytest.raises(GovernanceError, match="requires local receipt"):
        evaluate_distributed_finality(
            registered,
            replace(bundle.receipt, candidate_id=bundle.scenario.other_id),
            certificate=certificate,
            current_step=6,
        )

    finality_verification = verify_distributed_commit_finality(
        certificate,
        registered,
        bundle.receipt,
        current_step=6,
        verifier_id="governance:distributed-finality",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:distributed-finality",
        trace_event_id="trace:distributed-finality",
    )
    with pytest.raises(GovernanceError, match="from the future"):
        verify_distributed_commit_finality(
            certificate,
            registered,
            bundle.receipt,
            current_step=5,
            verifier_id="governance:distributed-finality",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:distributed-finality",
            trace_event_id="trace:distributed-finality:future",
        )
    with pytest.raises(GovernanceError, match="lacks authority"):
        verify_distributed_commit_finality(
            certificate,
            registered,
            bundle.receipt,
            current_step=6,
            verifier_id="agent:distributed-finality",
            authority=AuthorityLevel.AGENT,
            provenance="urn:test:distributed-finality:agent",
            trace_event_id="trace:distributed-finality:agent",
        )
    with pytest.raises(GovernanceError, match="receipt is not authoritative"):
        verify_distributed_commit_finality(
            certificate,
            registered,
            replace(bundle.receipt, candidate_id=bundle.scenario.other_id),
            current_step=6,
            verifier_id="governance:distributed-finality",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:distributed-finality:forged-receipt",
            trace_event_id="trace:distributed-finality:forged-receipt",
        )
    liveness_input = issue_commit_liveness_input(
        bundle.window,
        assessment=bundle.assessment,
        replay_state=bundle.scenario.replay_state,
        risk_chain_state=bundle.scenario.risk_chain_state,
        risk_assessment=bundle.scenario.risk_assessment,
        threshold_snapshot=bundle.scenario.threshold,
        membership_snapshot=bundle.scenario.membership_snapshot,
        membership_epoch_state=bundle.scenario.membership_state,
        support_replay_state=bundle.scenario.support_replay_state,
        commit_policy=bundle.scenario.policy,
        current_step=6,
        finality_status=CommitFinalityStatus.VERIFIED,
        finality_verification=finality_verification,
        input_id=f"liveness:{bundle.scenario.run_id}:distributed-final",
        issuer_id="governance:liveness",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:liveness:distributed-final",
        trace_event_id="trace:liveness:distributed-final",
    )
    outcome = reduce_commit_liveness(
        bundle.window,
        commit_policy=bundle.scenario.policy,
        liveness_input=liveness_input,
    )
    assert type(outcome) is DecisionOutcome
    assert outcome.kind is DecisionOutcomeKind.EVIDENCE_COMMIT
    assert outcome.certificate_ref == distributed_commit_certificate_fingerprint(
        certificate
    )
    with pytest.raises(GovernanceError, match="not governance-issued"):
        evaluate_distributed_finality(
            registered,
            bundle.receipt,
            certificate=certificate,
            current_step=6,
            outcome=replace(outcome, reason_codes=("forged-outcome",)),
        )
    terminal = evaluate_distributed_finality(
        registered,
        bundle.receipt,
        certificate=certificate,
        current_step=6,
        outcome=outcome,
    )
    assert terminal.kind is DistributedFinalityKind.FINAL
    assert terminal.terminal is True
    assert terminal.authoritative_commit is True
    assert (
        distributed_finality_decision_from_payload(
            distributed_finality_decision_payload(terminal)
        )
        == terminal
    )


def test_finality_unavailable_only_at_deadline_and_never_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _distributed_scenario(monkeypatch)
    deadline = min(
        bundle.window.absolute_deadline_step,
        bundle.window.absolute_run_deadline_step,
    )
    pending = evaluate_distributed_finality(
        bundle.state,
        bundle.receipt,
        certificate=None,
        current_step=6,
    )
    assert pending.kind is DistributedFinalityKind.PENDING
    assert pending.terminal is False
    assert pending.distributed_certificate_ref == ""
    pending_payload = governance.distributed_finality_decision_payload(pending)
    pending_with_certificate = dict(pending_payload)
    pending_with_certificate["distributed_certificate_ref"] = _fingerprint(
        "pending-certificate"
    )
    with pytest.raises(GovernanceError, match="pending finality"):
        governance.distributed_finality_decision_from_payload(pending_with_certificate)
    terminal_pending = dict(pending_payload)
    terminal_pending["terminal"] = True
    terminal_pending["outcome_ref"] = _fingerprint("pending-outcome")
    with pytest.raises(GovernanceError, match="cannot be terminal"):
        governance.distributed_finality_decision_from_payload(terminal_pending)
    progress = reduce_commit_liveness(
        bundle.window,
        commit_policy=bundle.scenario.policy,
        liveness_input=issue_commit_liveness_input(
            bundle.window,
            assessment=bundle.assessment,
            replay_state=bundle.scenario.replay_state,
            risk_chain_state=bundle.scenario.risk_chain_state,
            risk_assessment=bundle.scenario.risk_assessment,
            threshold_snapshot=bundle.scenario.threshold,
            membership_snapshot=bundle.scenario.membership_snapshot,
            membership_epoch_state=bundle.scenario.membership_state,
            support_replay_state=bundle.scenario.support_replay_state,
            commit_policy=bundle.scenario.policy,
            current_step=bundle.window.last_evaluated_step,
            finality_status=CommitFinalityStatus.PENDING,
            input_id=(
                f"liveness:{bundle.scenario.run_id}:pending:"
                f"{bundle.window.last_evaluated_step}"
            ),
            issuer_id="governance:liveness",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:liveness:pending",
            trace_event_id=(
                f"trace:liveness:pending:{bundle.window.last_evaluated_step}"
            ),
        ),
    )
    for step in range(bundle.window.last_evaluated_step + 1, deadline):
        progress = reduce_commit_liveness(
            bundle.window,
            commit_policy=bundle.scenario.policy,
            liveness_input=issue_commit_liveness_input(
                bundle.window,
                assessment=bundle.assessment,
                replay_state=bundle.scenario.replay_state,
                risk_chain_state=bundle.scenario.risk_chain_state,
                risk_assessment=bundle.scenario.risk_assessment,
                threshold_snapshot=bundle.scenario.threshold,
                membership_snapshot=bundle.scenario.membership_snapshot,
                membership_epoch_state=bundle.scenario.membership_state,
                support_replay_state=bundle.scenario.support_replay_state,
                commit_policy=bundle.scenario.policy,
                previous_progress=progress,
                current_step=step,
                finality_status=CommitFinalityStatus.PENDING,
                input_id=f"liveness:{bundle.scenario.run_id}:pending:{step}",
                issuer_id="governance:liveness",
                authority=AuthorityLevel.GOVERNANCE,
                provenance="urn:test:liveness:pending",
                trace_event_id=f"trace:liveness:pending:{step}",
            ),
        )
    liveness_input = issue_commit_liveness_input(
        bundle.window,
        assessment=bundle.assessment,
        replay_state=bundle.scenario.replay_state,
        risk_chain_state=bundle.scenario.risk_chain_state,
        risk_assessment=bundle.scenario.risk_assessment,
        threshold_snapshot=bundle.scenario.threshold,
        membership_snapshot=bundle.scenario.membership_snapshot,
        membership_epoch_state=bundle.scenario.membership_state,
        support_replay_state=bundle.scenario.support_replay_state,
        commit_policy=bundle.scenario.policy,
        previous_progress=progress,
        current_step=deadline,
        finality_status=CommitFinalityStatus.UNAVAILABLE,
        finality_reason_codes=("witness_quorum_unavailable",),
        input_id=f"liveness:{bundle.scenario.run_id}:unavailable",
        issuer_id="governance:liveness",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:liveness:unavailable",
        trace_event_id="trace:liveness:unavailable",
    )
    outcome = reduce_commit_liveness(
        bundle.window,
        commit_policy=bundle.scenario.policy,
        liveness_input=liveness_input,
    )
    assert type(outcome) is DecisionOutcome
    assert outcome.kind is DecisionOutcomeKind.FINALITY_UNAVAILABLE
    assert outcome.authoritative_commit is False
    assert outcome.epistemically_committed is False
    decision = evaluate_distributed_finality(
        bundle.state,
        bundle.receipt,
        certificate=None,
        current_step=deadline,
        outcome=outcome,
    )
    assert decision.kind is DistributedFinalityKind.FINALITY_UNAVAILABLE
    assert decision.terminal is True
    assert decision.authoritative_commit is False
    unavailable_payload = governance.distributed_finality_decision_payload(decision)
    assert (
        governance.distributed_finality_decision_from_payload(unavailable_payload)
        == decision
    )
    missing_terminal = dict(unavailable_payload)
    missing_terminal["terminal"] = False
    with pytest.raises(GovernanceError, match="must bind an outcome"):
        governance.distributed_finality_decision_from_payload(missing_terminal)
    missing_outcome = dict(unavailable_payload)
    missing_outcome["terminal"] = False
    missing_outcome["outcome_ref"] = ""
    with pytest.raises(GovernanceError, match="requires an outcome"):
        governance.distributed_finality_decision_from_payload(missing_outcome)
    with pytest.raises(GovernanceError):
        replace(outcome, current_step=deadline - 1)


def test_distributed_adapter_preserves_later_finality_for_sealed_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _distributed_scenario(monkeypatch)
    certificate = _certificate(
        bundle,
        bundle.verifications[:3],
        suffix="later-finality",
    )
    registered = register_distributed_commit_certificate(
        bundle.state,
        certificate,
        commit_policy=bundle.scenario.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        current_step=6,
    )
    # Distributed authority remains valid at a later logical step; the
    # sealed-window heartbeat reducer consumes this without changing the signed
    # proposal.
    decision = evaluate_distributed_finality(
        registered,
        bundle.receipt,
        certificate=certificate,
        current_step=8,
    )
    assert decision.kind is DistributedFinalityKind.FINAL
    assert decision.terminal is False
    verification = verify_distributed_commit_finality(
        certificate,
        registered,
        bundle.receipt,
        current_step=8,
        verifier_id="governance:distributed-finality:later",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:distributed-finality:later",
        trace_event_id="trace:distributed-finality:later",
    )
    assert commit_finality_verification_is_authoritative(verification)
    assert verification.verified_at_step == 8


def test_same_value_final_retries_coexist_and_semantic_conflict_freezes_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _distributed_scenario(monkeypatch)
    first_certificate = _certificate(
        bundle,
        bundle.verifications[:3],
        suffix="conflict-a",
    )
    first_state = register_distributed_commit_certificate(
        bundle.state,
        first_certificate,
        commit_policy=bundle.scenario.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        current_step=6,
    )
    second_proposal = issue_distributed_commit_proposal(
        bundle.receipt,
        bundle.portable_certificate,
        bundle.scenario.membership_snapshot,
        bundle.scenario.membership_state,
        commit_policy=bundle.scenario.policy,
        trusted_issuer_attestations=bundle.issuer_trust,
        proposal_id=f"proposal:{bundle.scenario.run_id}:conflict-b",
        proposed_at_step=6,
    )
    second_verifications = tuple(
        _witness_verification(
            bundle.scenario,
            second_proposal,
            principal,
            index=100 + index,
            witness_trust=bundle.witness_trust,
        )
        for index, principal in enumerate(bundle.principals[:3], start=1)
    )
    second_certificate = assemble_portable_distributed_commit_certificate(
        second_proposal,
        portable_membership_snapshot_from_eligible(bundle.scenario.membership_snapshot),
        tuple(reversed(second_verifications)),
        commit_policy=bundle.scenario.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        certificate_id=f"distributed:{bundle.scenario.run_id}:conflict-b",
        issuer_id="governance:peer-certificate",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=6,
        provenance="urn:test:peer-certificate",
        trace_event_id="trace:peer-certificate",
    )
    assert second_certificate.status is DistributedCertificateStatus.FINAL
    assert second_certificate.proposal_digest != first_certificate.proposal_digest
    same_value_state = register_distributed_commit_certificate(
        first_state,
        second_certificate,
        commit_policy=bundle.scenario.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        current_step=6,
    )
    assert second_certificate.commit_value_root == first_certificate.commit_value_root
    assert same_value_state.frozen is False
    assert len(same_value_state.final_registrations) == 2
    assert not same_value_state.conflict_findings

    (
        conflict_proposal,
        conflict_portable,
        conflict_issuer_trust,
        conflict_witness_trust,
        conflict_certificate,
    ) = _portable_semantic_conflict(
        bundle,
        field_name="output_payload_fingerprint",
        field_value=_fingerprint(f"conflicting-output:{bundle.scenario.run_id}"),
        suffix="semantic-conflict",
    )
    assert conflict_proposal.commit_value_root != first_certificate.commit_value_root
    frozen = register_distributed_commit_certificate(
        same_value_state,
        conflict_certificate,
        commit_policy=bundle.scenario.policy,
        portable_certificate=conflict_portable,
        trusted_issuer_attestations=conflict_issuer_trust,
        trusted_witness_attestations=conflict_witness_trust,
        current_step=6,
    )
    assert frozen.frozen is True
    assert len(frozen.conflict_findings) == 1
    assert not distributed_commit_certificate_is_current_final(
        first_certificate,
        frozen,
    )
    safety = evaluate_distributed_finality(
        frozen,
        bundle.receipt,
        certificate=None,
        current_step=6,
    )
    assert safety.kind is DistributedFinalityKind.SAFETY_VIOLATION
    assert safety.authoritative_commit is False
    assert (
        register_distributed_commit_certificate(
            frozen,
            conflict_certificate,
            commit_policy=bundle.scenario.policy,
            portable_certificate=conflict_portable,
            trusted_issuer_attestations=conflict_issuer_trust,
            trusted_witness_attestations=conflict_witness_trust,
            current_step=6,
        )
        is frozen
    )
    assert (
        register_distributed_commit_certificate(
            first_state,
            first_certificate,
            commit_policy=bundle.scenario.policy,
            portable_certificate=bundle.portable_certificate,
            trusted_issuer_attestations=bundle.issuer_trust,
            trusted_witness_attestations=bundle.witness_trust,
            current_step=6,
        )
        is frozen
    )


def test_conflict_recovery_requires_declared_recovery_and_new_epoch_certificate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _distributed_scenario(monkeypatch)
    first = _certificate(bundle, bundle.verifications[:3], suffix="recovery-a")
    state = register_distributed_commit_certificate(
        bundle.state,
        first,
        commit_policy=bundle.scenario.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        current_step=6,
    )
    (
        _,
        other_portable,
        other_issuer_trust,
        other_witness_trust,
        other,
    ) = _portable_semantic_conflict(
        bundle,
        field_name="claim_fingerprint",
        field_value=_fingerprint(f"conflicting-claim:{bundle.scenario.run_id}"),
        suffix="recovery-semantic-conflict",
    )
    frozen = register_distributed_commit_certificate(
        state,
        other,
        commit_policy=bundle.scenario.policy,
        portable_certificate=other_portable,
        trusted_issuer_attestations=other_issuer_trust,
        trusted_witness_attestations=other_witness_trust,
        current_step=6,
    )
    new_snapshot, new_epoch_state = _new_epoch_membership(bundle, epoch=4)
    with pytest.raises(GovernanceError, match="declared recovery"):
        epoch_transition_decision_ref(
            frozen,
            new_snapshot,
            new_epoch_state,
            commit_policy=bundle.scenario.policy,
        )
    recovery_ref = _fingerprint(f"declared-recovery:{bundle.scenario.run_id}")
    decision_ref = epoch_transition_decision_ref(
        frozen,
        new_snapshot,
        new_epoch_state,
        commit_policy=bundle.scenario.policy,
        declared_recovery_ref=recovery_ref,
    )
    transition_stop, transition_permission = _action_gate(
        bundle,
        action=CommitAction.EPOCH_TRANSITION,
        decision_ref=decision_ref,
    )
    recovery_stop, recovery_permission = _action_gate(
        bundle,
        action=CommitAction.RECOVERY,
        decision_ref=decision_ref,
    )
    metadata = {
        "certificate_id": f"epoch-certificate:{bundle.scenario.run_id}:4",
        "declared_recovery_ref": recovery_ref,
        "recovery_stop": recovery_stop,
        "recovery_permission": recovery_permission,
        "issuer_id": "governance:epoch-transition",
        "authority": AuthorityLevel.GOVERNANCE,
        "issued_at_step": 9,
        "provenance": "urn:test:epoch-transition",
        "trace_event_id": "trace:epoch-transition",
    }
    body_root = epoch_transition_certificate_body_root(
        frozen,
        new_snapshot,
        new_epoch_state,
        transition_stop,
        transition_permission,
        commit_policy=bundle.scenario.policy,
        **metadata,
    )
    attestation_refs = (f"attestation:epoch:{bundle.scenario.run_id}:4",)
    trust = {attestation_refs[0]: body_root}
    certificate = issue_epoch_transition_certificate(
        frozen,
        new_snapshot,
        new_epoch_state,
        transition_stop,
        transition_permission,
        commit_policy=bundle.scenario.policy,
        issuer_attestation_refs=attestation_refs,
        trusted_issuer_attestations=trust,
        **metadata,
    )
    assert verify_epoch_transition_certificate(
        certificate,
        commit_policy=bundle.scenario.policy,
        trusted_issuer_attestations=trust,
    )
    old_state, new_state = transition_distributed_commit_epoch(
        frozen,
        certificate,
        new_snapshot,
        new_epoch_state,
        commit_policy=bundle.scenario.policy,
        trusted_issuer_attestations=trust,
        issuer_id="governance:distributed-state:epoch-4",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:distributed-state:epoch-4",
        trace_event_id="trace:distributed-state:epoch-4",
    )
    assert old_state.transitioned is True
    assert old_state.frozen is True
    assert new_state.epoch == 4
    assert new_state.frozen is False
    assert distributed_commit_state_is_current(new_state)


def test_distributed_state_concurrent_initialization_and_gc_are_strong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _distributed_scenario(monkeypatch)
    snapshot, epoch_state = _new_epoch_membership(bundle, epoch=9)

    def initialize():
        return initialize_distributed_commit_state(
            snapshot,
            epoch_state,
            commit_policy=bundle.scenario.policy,
            current_step=9,
            issuer_id="governance:distributed-state:concurrent",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:distributed-state:concurrent",
            trace_event_id="trace:distributed-state:concurrent",
        )

    with ThreadPoolExecutor(max_workers=32) as executor:
        states = tuple(executor.map(lambda _: initialize(), range(32)))
    assert len({id(item) for item in states}) == 1
    state = states[0]
    reference = weakref.ref(state)
    del states
    del state
    gc.collect()
    retained = reference()
    assert retained is not None
    assert initialize() is retained


def _new_epoch_membership(
    bundle: _DistributedScenario,
    *,
    epoch: int,
):
    principals = tuple(
        verify_principal_attestation(
            PrincipalAttestation(
                principal_id=principal.principal_id,
                attestation_ref=(
                    f"opaque:principal:{bundle.scenario.run_id}:epoch:{epoch}:{index}"
                ),
                method="identity-verifier-v1",
                issuer_id="issuer:identity",
                issued_at_step=7,
                expires_at_step=30,
                provenance=(
                    f"urn:test:principal:{bundle.scenario.run_id}:epoch:{epoch}:{index}"
                ),
                nonce=(
                    f"nonce:principal:{bundle.scenario.run_id}:epoch:{epoch}:{index}"
                ),
                trace_event_id=(
                    f"trace:principal:{bundle.scenario.run_id}:epoch:{epoch}:{index}"
                ),
            ),
            profile=DISTRIBUTED_COMMIT_PROFILE_VERSION,
            assurance=CommitAssurance.DISTRIBUTED,
            manifest_root=bundle.receipt.manifest_root,
            commit_policy_root=bundle.receipt.commit_policy_root,
            protocol_id=bundle.receipt.protocol_id,
            run_id=bundle.receipt.run_id,
            target=bundle.receipt.target,
            epoch=epoch,
            cluster_id=principal.cluster_id,
            failure_domain=principal.failure_domain,
            verifier_id="governance:identity",
            authority=AuthorityLevel.GOVERNANCE,
            current_step=8,
            provenance="urn:test:principal-verification:new-epoch",
            trace_event_id=(
                f"trace:principal-verified:{bundle.scenario.run_id}:epoch:{epoch}:{index}"
            ),
        )
        for index, principal in enumerate(bundle.principals, start=1)
    )
    return issue_eligible_principal_snapshot(
        principals,
        snapshot_id=f"membership:{bundle.scenario.run_id}:epoch:{epoch}",
        profile=DISTRIBUTED_COMMIT_PROFILE_VERSION,
        assurance=CommitAssurance.DISTRIBUTED,
        manifest_root=bundle.receipt.manifest_root,
        commit_policy_root=bundle.receipt.commit_policy_root,
        protocol_id=bundle.receipt.protocol_id,
        run_id=bundle.receipt.run_id,
        target=bundle.receipt.target,
        epoch=epoch,
        issuer_id="governance:membership",
        membership_method="verified-static-epoch-v1",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=8,
        expires_at_step=20,
        provenance=f"urn:test:membership:{bundle.scenario.run_id}:epoch:{epoch}",
        trace_event_id=f"trace:membership:{bundle.scenario.run_id}:epoch:{epoch}",
    )


def _action_gate(
    bundle: _DistributedScenario,
    *,
    action: CommitAction,
    decision_ref: str,
):
    stop = verify_stop_resolution(
        StopResolution(
            target=bundle.receipt.target,
            action=action.value,
            blocked=False,
            reason="governance_clear",
        ),
        resolution_id=f"stop:{bundle.scenario.run_id}:{action.value}:epoch-transition",
        profile=DISTRIBUTED_COMMIT_PROFILE_VERSION,
        assurance=CommitAssurance.DISTRIBUTED,
        manifest_root=bundle.receipt.manifest_root,
        commit_policy_root=bundle.receipt.commit_policy_root,
        protocol_id=bundle.receipt.protocol_id,
        run_id=bundle.receipt.run_id,
        epoch=bundle.receipt.epoch,
        decision_ref=decision_ref,
        certificate_ref="",
        resolved_stop_root=_fingerprint(
            f"resolved-stop:{bundle.scenario.run_id}:{action.value}"
        ),
        verifier_id="governance:stop",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=8,
        expires_at_step=12,
        provenance=f"urn:test:stop:{action.value}",
        trace_event_id=f"trace:stop:{action.value}",
    )
    permission = issue_action_permission(
        permission_id=f"permission:{bundle.scenario.run_id}:{action.value}",
        profile=DISTRIBUTED_COMMIT_PROFILE_VERSION,
        assurance=CommitAssurance.DISTRIBUTED,
        manifest_root=bundle.receipt.manifest_root,
        commit_policy_root=bundle.receipt.commit_policy_root,
        protocol_id=bundle.receipt.protocol_id,
        run_id=bundle.receipt.run_id,
        target=bundle.receipt.target,
        action=action,
        epoch=bundle.receipt.epoch,
        decision_ref=decision_ref,
        certificate_ref="",
        allowed=True,
        reason_codes=("declared_governance_authority",),
        issuer_id="governance:permission",
        policy_ref="policy:epoch-transition",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=8,
        expires_at_step=12,
        provenance=f"urn:test:permission:{action.value}",
        trace_event_id=f"trace:permission:{action.value}",
    )
    return stop, permission


def _scalar_leaf_paths(value, prefix=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _scalar_leaf_paths(item, (*prefix, key))
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            yield from _scalar_leaf_paths(item, (*prefix, index))
    else:
        yield prefix


def _mutate_leaf(payload, path) -> None:
    parent = payload
    for segment in path[:-1]:
        parent = parent[segment]
    key = path[-1]
    value = parent[key]
    if isinstance(value, bool):
        mutated = not value
    elif isinstance(value, Enum):
        mutated = f"mutated:{value.value}"
    elif isinstance(value, int):
        mutated = value + 1
    elif isinstance(value, str) and value.startswith("sha256:"):
        mutated = _fingerprint(f"mutated:{'.'.join(map(str, path))}")
    elif isinstance(value, str):
        mutated = f"{value}:mutated"
    else:
        raise AssertionError(f"unsupported leaf type at {path}: {type(value)!r}")
    parent[key] = mutated


def _mutable(value):
    if isinstance(value, dict):
        return {key: _mutable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_mutable(item) for item in value]
    return value
