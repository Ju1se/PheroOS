"""Public-only sealed Decision and central Certificate setup for Distributed v2."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac

from pheroos.conformance.checks._distributed_v2_context_support import (
    CANDIDATE_REF,
    PROFILE,
    RUN_REF,
    TARGET_REF,
    DistributedV2Context,
    capability_v2,
)
from pheroos.conformance.checks._distributed_v2_input_support import (
    DistributedV2DecisionInputs,
)
from pheroos.conformance.checks._support_v2_manifest_support import root_v2
from pheroos.governance.authority_store_v2 import GovernanceCommitDispositionV2
from pheroos.governance.commit_certificate_v2 import (
    CommitCertificateRequestV2,
    VerifiedCommitCertificateStateV2,
    advance_commit_certificate_v2,
    open_commit_certificate_authority_session_v2,
    prepare_commit_certificate_v2,
    rehydrate_commit_certificate_state_v2,
)
from pheroos.governance.commit_decision_v2 import (
    CommitDecisionCandidateProposalV2,
    CommitDecisionCommandV2,
    CommitDecisionOutputProposalV2,
    CommitDecisionRequestV2,
    VerifiedCommitDecisionStateV2,
    VerifiedCommitDecisionSourceV2,
    advance_commit_decision_v2,
    open_commit_decision_authority_session_v2,
    prepare_commit_decision_initialize_v2,
    prepare_commit_decision_successor_v2,
    rehydrate_commit_decision_state_v2,
)


@dataclass(frozen=True, slots=True)
class DistributedV2Decision:
    state: VerifiedCommitDecisionStateV2
    central_request: CommitCertificateRequestV2
    central: VerifiedCommitCertificateStateV2


class _DiscoveryVerifier:
    def verify_commit_certificate_attestation_v2(
        self,
        *,
        issuer_ref: str,
        attestation_ref: str,
        body_root: str,
    ) -> bool:
        return bool(issuer_ref and attestation_ref and body_root)


class _DigestVerifier:
    @staticmethod
    def attestation_ref(issuer_ref: str, body_root: str) -> str:
        digest = sha256(
            issuer_ref.encode("utf-8") + b"\x00" + body_root.encode("ascii")
        ).hexdigest()
        return "attestation:sha256:" + digest

    def verify_commit_certificate_attestation_v2(
        self,
        *,
        issuer_ref: str,
        attestation_ref: str,
        body_root: str,
    ) -> bool:
        return hmac.compare_digest(
            attestation_ref,
            self.attestation_ref(issuer_ref, body_root),
        )


def decision_and_central_v2(
    context: DistributedV2Context,
    inputs: DistributedV2DecisionInputs,
    *,
    label: str,
    claim_root: str,
) -> DistributedV2Decision:
    decision = sealed_decision_v2(
        context,
        inputs,
        label=label,
        claim_root=claim_root,
    )
    central_request, central = central_certificate_v2(
        context,
        decision,
        label=label,
    )
    return DistributedV2Decision(decision, central_request, central)


def sealed_decision_v2(
    context: DistributedV2Context,
    inputs: DistributedV2DecisionInputs,
    *,
    label: str,
    claim_root: str,
) -> VerifiedCommitDecisionStateV2:
    initialize, source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        observed_epoch=1,
        mutation_ref=f"mutation:distributed:decision:initialize:{label}",
        current_step=6,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    state = _advance_decision_v2(context, initialize, source)
    proposal = CommitDecisionCandidateProposalV2(
        candidate_ref=CANDIDATE_REF,
        claim_root=claim_root,
        evidence=(),
    )
    for step in (7, 8):
        request, successor = _decision_successor_v2(
            context,
            inputs,
            state,
            label=f"{label}:evaluate:{step}",
            current_step=step,
            candidate_proposals=(proposal,),
        )
        state = _advance_decision_v2(context, request, successor)
    output = CommitDecisionOutputProposalV2(
        candidate_ref=CANDIDATE_REF,
        claim_root=claim_root,
        output_contract_root=root_v2(f"distributed:output-contract:{label}"),
        payload={"answer": "provider-free distributed commit"},
    )
    seal, seal_source = _decision_successor_v2(
        context,
        inputs,
        state,
        label=f"{label}:seal",
        current_step=8,
        command=CommitDecisionCommandV2.SEAL,
        output_proposal=output,
    )
    state = _advance_decision_v2(context, seal, seal_source)
    return advance_sealed_heartbeat_v2(
        context,
        inputs,
        state,
        label=f"{label}:heartbeat:9",
        current_step=9,
        claim_root=claim_root,
    )


def advance_sealed_heartbeat_v2(
    context: DistributedV2Context,
    inputs: DistributedV2DecisionInputs,
    parent: VerifiedCommitDecisionStateV2,
    *,
    label: str,
    current_step: int,
    claim_root: str,
) -> VerifiedCommitDecisionStateV2:
    proposal = CommitDecisionCandidateProposalV2(
        candidate_ref=CANDIDATE_REF,
        claim_root=claim_root,
        evidence=(),
    )
    request, source = _decision_successor_v2(
        context,
        inputs,
        parent,
        label=label,
        current_step=current_step,
        candidate_proposals=(proposal,),
    )
    return _advance_decision_v2(context, request, source)


def central_certificate_v2(
    context: DistributedV2Context,
    decision: VerifiedCommitDecisionStateV2,
    *,
    label: str,
    parent_state: VerifiedCommitCertificateStateV2 | None = None,
) -> tuple[CommitCertificateRequestV2, VerifiedCommitCertificateStateV2]:
    discovery, _ = prepare_commit_certificate_v2(
        decision_state=decision,
        manifest=context.manifest,
        trusted_verifier=_DiscoveryVerifier(),
        certificate_id=f"certificate:distributed:central:{label}",
        issuer_ref=context.grant.issuer_ref,
        issuer_attestation_refs=("attestation:discovery",),
        issued_at_step=decision.snapshot.current_step,
        provenance_ref=f"urn:pheroos:conformance:distributed:central:{label}",
        envelope_nonce=f"nonce:distributed:central:{label}",
        mutation_ref=f"mutation:distributed:central:{label}",
        parent_state=parent_state,
    )
    verifier = _DigestVerifier()
    attestation = verifier.attestation_ref(
        context.grant.issuer_ref,
        discovery.certificate.body.body_root,
    )
    request, source = prepare_commit_certificate_v2(
        decision_state=decision,
        manifest=context.manifest,
        trusted_verifier=verifier,
        certificate_id=f"certificate:distributed:central:{label}",
        issuer_ref=context.grant.issuer_ref,
        issuer_attestation_refs=(attestation,),
        issued_at_step=decision.snapshot.current_step,
        provenance_ref=f"urn:pheroos:conformance:distributed:central:{label}",
        envelope_nonce=f"nonce:distributed:central:{label}",
        mutation_ref=f"mutation:distributed:central:{label}",
        parent_state=parent_state,
    )
    attempt = advance_commit_certificate_v2(
        request,
        source=source,
        authority_session=open_commit_certificate_authority_session_v2(
            capability_v2(context, request.observed_epoch), request
        ),
    )
    _require_committed(attempt.disposition, "central certificate")
    return request, rehydrate_commit_certificate_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )


def _decision_successor_v2(
    context: DistributedV2Context,
    inputs: DistributedV2DecisionInputs,
    parent: VerifiedCommitDecisionStateV2,
    *,
    label: str,
    current_step: int,
    command: CommitDecisionCommandV2 = CommitDecisionCommandV2.EVALUATE,
    candidate_proposals: tuple[CommitDecisionCandidateProposalV2, ...] = (),
    output_proposal: CommitDecisionOutputProposalV2 | None = None,
) -> tuple[CommitDecisionRequestV2, VerifiedCommitDecisionSourceV2]:
    return prepare_commit_decision_successor_v2(
        parent_state=parent,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref=f"mutation:distributed:decision:{label}",
        current_step=current_step,
        mutation_issuer_ref=context.grant.issuer_ref,
        command=command,
        candidate_proposals=candidate_proposals,
        output_proposal=output_proposal,
        commit_replay_state=inputs.replay,
        risk_state=inputs.risk,
        membership_state=inputs.membership,
        support_state=inputs.support,
        evidence_state=inputs.evidence,
        stop_state=inputs.stop,
        permission_state=inputs.permission,
    )


def _advance_decision_v2(
    context: DistributedV2Context,
    request: CommitDecisionRequestV2,
    source: object,
) -> VerifiedCommitDecisionStateV2:
    attempt = advance_commit_decision_v2(
        request,
        source=source,
        authority_session=open_commit_decision_authority_session_v2(
            capability_v2(context, request.observed_epoch), request
        ),
    )
    _require_committed(attempt.disposition, "decision")
    return rehydrate_commit_decision_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )


def _require_committed(
    disposition: GovernanceCommitDispositionV2,
    label: str,
) -> None:
    if disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise RuntimeError(f"Distributed Commit v2 {label} setup failed")


__all__: tuple[str, ...] = ()
