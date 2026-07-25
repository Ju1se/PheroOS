"""Public-only Certificate owner fixtures for finality Conformance."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
from typing import cast

from pheroos.conformance.checks._commit_finality_v2_decision_support import (
    FinalityDecisionV2Vertical,
)
from pheroos.conformance.checks._support_v2_manifest_support import RUN_REF
from pheroos.governance.authority_session_v2 import (
    bind_governance_issuer_capability_v2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
)
from pheroos.governance.commit_certificate_v2 import (
    CommitCertificateIssuerAttestationVerifierV2,
    CommitCertificateRequestV2,
    VerifiedCommitCertificateSourceV2,
    VerifiedCommitCertificateStateV2,
    advance_commit_certificate_v2,
    open_commit_certificate_authority_session_v2,
    prepare_commit_certificate_v2,
    rehydrate_commit_certificate_state_v2,
)
from pheroos.governance.commit_decision_v2 import VerifiedCommitDecisionStateV2


@dataclass(frozen=True, slots=True)
class CertificateOwnerV2Vertical:
    decision: FinalityDecisionV2Vertical
    request: CommitCertificateRequestV2
    state: VerifiedCommitCertificateStateV2


class DigestCertificateVerifierV2:
    @staticmethod
    def attestation_ref_v2(issuer_ref: str, body_root: str) -> str:
        material = issuer_ref.encode("utf-8") + b"\x00" + body_root.encode("ascii")
        return "attestation:sha256:" + sha256(material).hexdigest()

    def verify_commit_certificate_attestation_v2(
        self,
        *,
        issuer_ref: str,
        attestation_ref: str,
        body_root: str,
    ) -> bool:
        return hmac.compare_digest(
            attestation_ref,
            self.attestation_ref_v2(issuer_ref, body_root),
        )


class _DiscoveryCertificateVerifierV2:
    def verify_commit_certificate_attestation_v2(
        self,
        *,
        issuer_ref: str,
        attestation_ref: str,
        body_root: str,
    ) -> bool:
        return bool(issuer_ref and attestation_ref and body_root)


def prepare_certificate_v2(
    decision: FinalityDecisionV2Vertical,
    label: str,
    *,
    decision_state: VerifiedCommitDecisionStateV2 | None = None,
    parent_state: VerifiedCommitCertificateStateV2 | None = None,
    certificate_id: str = "certificate:finality:owner",
) -> tuple[CommitCertificateRequestV2, VerifiedCommitCertificateSourceV2]:
    selected_decision = decision.state if decision_state is None else decision_state
    support = decision.context.support_context
    discovery, _ = prepare_commit_certificate_v2(
        decision_state=selected_decision,
        manifest=decision.context.manifest,
        trusted_verifier=_DiscoveryCertificateVerifierV2(),
        certificate_id=certificate_id,
        issuer_ref=support.grant.issuer_ref,
        issuer_attestation_refs=("attestation:discovery",),
        issued_at_step=selected_decision.snapshot.current_step,
        provenance_ref=f"urn:pheroos:conformance:finality:{label}",
        envelope_nonce=f"nonce:finality:certificate:{label}",
        mutation_ref=f"mutation:finality:certificate:{label}",
        parent_state=parent_state,
    )
    verifier = DigestCertificateVerifierV2()
    attestation = verifier.attestation_ref_v2(
        support.grant.issuer_ref,
        discovery.certificate.body.body_root,
    )
    return prepare_commit_certificate_v2(
        decision_state=selected_decision,
        manifest=decision.context.manifest,
        trusted_verifier=cast(
            CommitCertificateIssuerAttestationVerifierV2,
            verifier,
        ),
        certificate_id=certificate_id,
        issuer_ref=support.grant.issuer_ref,
        issuer_attestation_refs=(attestation,),
        issued_at_step=selected_decision.snapshot.current_step,
        provenance_ref=f"urn:pheroos:conformance:finality:{label}",
        envelope_nonce=f"nonce:finality:certificate:{label}",
        mutation_ref=f"mutation:finality:certificate:{label}",
        parent_state=parent_state,
    )


def advance_certificate_v2(
    decision: FinalityDecisionV2Vertical,
    request: CommitCertificateRequestV2,
    source: object,
) -> GovernanceCommitAttemptV2:
    support = decision.context.support_context
    capability = bind_governance_issuer_capability_v2(
        support.store,
        support.domain,
        support.grant,
        RUN_REF,
        request.observed_epoch,
    )
    session = open_commit_certificate_authority_session_v2(capability, request)
    return advance_commit_certificate_v2(
        request,
        source=source,
        authority_session=session,
    )


def certificate_state_v2(
    decision: FinalityDecisionV2Vertical,
    request: CommitCertificateRequestV2,
) -> VerifiedCommitCertificateStateV2:
    support = decision.context.support_context
    return rehydrate_commit_certificate_state_v2(
        request.to_dict(),
        domain=support.domain,
        state_reader=support.store,
    )


def verified_certificate_v2(
    decision: FinalityDecisionV2Vertical,
    label: str,
    *,
    decision_state: VerifiedCommitDecisionStateV2 | None = None,
    parent_state: VerifiedCommitCertificateStateV2 | None = None,
    certificate_id: str = "certificate:finality:owner",
) -> CertificateOwnerV2Vertical:
    request, source = prepare_certificate_v2(
        decision,
        label,
        decision_state=decision_state,
        parent_state=parent_state,
        certificate_id=certificate_id,
    )
    attempt = advance_certificate_v2(decision, request, source)
    if attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        detail = "" if attempt.failure is None else str(attempt.failure.to_dict())
        raise RuntimeError(f"Finality Certificate commit failed: {detail}")
    return CertificateOwnerV2Vertical(
        decision=decision,
        request=request,
        state=certificate_state_v2(decision, request),
    )


__all__: tuple[str, ...] = ()
