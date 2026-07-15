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
    DISTRIBUTED_COMMIT_CERTIFICATE_VERSION,
    DISTRIBUTED_PROPOSAL_VERSION,
    QUORUM_WITNESS_VERSION,
    WITNESS_VERIFICATION_VERSION,
    DistributedCertificateStatus,
    DistributedCommitCertificate,
    DistributedCommitProposal,
    DistributedCommitState,
    DistributedFinalityKind,
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
from pheroos.governance.support_lease import issue_eligible_principal_snapshot
from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_WIRE_VERSION,
    DISTRIBUTED_COMMIT_PROFILE_VERSION,
    CertificatePolicy,
    CommitAction,
    CommitAssurance,
    DistributedCommitPolicy,
)
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
        witness_id=witness_id or f"witness:{scenario.run_id}:{proposal.proposal_id}:{index}",
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
        nonce=nonce or f"nonce:witness:{scenario.run_id}:{proposal.proposal_id}:{index}",
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

    portable_payload = evidence_commit_certificate_payload(
        bundle.portable_certificate
    )
    portable_payload[field_name] = field_value
    portable_payload["certificate_id"] = (
        f"portable:{bundle.scenario.run_id}:{suffix}"
    )
    portable_payload["local_receipt_ref"] = _fingerprint(
        f"remote-receipt:{bundle.scenario.run_id}:{suffix}"
    )
    issuer_attestation_ref = (
        f"attestation:portable:{bundle.scenario.run_id}:{suffix}"
    )
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
    proposal_payload["proposal_id"] = (
        f"proposal:{bundle.scenario.run_id}:{suffix}"
    )
    proposal_payload["local_receipt_ref"] = portable.local_receipt_ref
    proposal_payload["portable_certificate_ref"] = (
        evidence_commit_certificate_fingerprint(portable)
    )
    value_payload = distributed_commit_value_payload(bundle.proposal)
    value_payload[field_name] = field_value
    proposal_payload["commit_value_root"] = distributed_commit_value_root(
        value_payload
    )
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
        portable_membership_snapshot_from_eligible(
            bundle.scenario.membership_snapshot
        ),
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
    assert issue_distributed_commit_proposal(
        bundle.receipt,
        bundle.portable_certificate,
        bundle.scenario.membership_snapshot,
        bundle.scenario.membership_state,
        commit_policy=bundle.scenario.policy,
        trusted_issuer_attestations=bundle.issuer_trust,
        proposal_id=bundle.proposal.proposal_id,
        proposed_at_step=6,
    ) is bundle.proposal
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
    assert record_witness_verifications(
        bundle.state,
        tuple(reversed(bundle.verifications)),
        current_step=6,
    ) is bundle.state

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
    assert record_witness_verifications(
        bundle.state,
        (conflicting,),
        current_step=6,
    ) is state
    assert record_witness_verifications(
        bundle.state,
        (),
        current_step=6,
    ) is state
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
    assert distributed_finality_decision_from_payload(
        distributed_finality_decision_payload(terminal)
    ) == terminal


def test_finality_unavailable_only_at_deadline_and_never_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _distributed_scenario(monkeypatch)
    deadline = min(
        bundle.window.absolute_deadline_step,
        bundle.window.absolute_run_deadline_step,
    )
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
                "trace:liveness:pending:"
                f"{bundle.window.last_evaluated_step}"
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
        portable_membership_snapshot_from_eligible(
            bundle.scenario.membership_snapshot
        ),
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
    assert register_distributed_commit_certificate(
        frozen,
        conflict_certificate,
        commit_policy=bundle.scenario.policy,
        portable_certificate=conflict_portable,
        trusted_issuer_attestations=conflict_issuer_trust,
        trusted_witness_attestations=conflict_witness_trust,
        current_step=6,
    ) is frozen
    assert register_distributed_commit_certificate(
        first_state,
        first_certificate,
        commit_policy=bundle.scenario.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        current_step=6,
    ) is frozen


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
