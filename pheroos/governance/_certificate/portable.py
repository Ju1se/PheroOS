"""Portable evidence certificate issuance and verification."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pheroos.governance._certificate.invariants import (
    _certificate_body_root,
    _certificate_envelope_root,
    _issue_typed_finality_verification,
    _require_attestation_bindings,
    _validate_policy_binding,
)
from pheroos.governance._certificate.historical import (
    evidence_commit_certificate_fingerprint,
    evidence_commit_certificate_from_payload,
    evidence_commit_certificate_payload,
    verify_evidence_commit_certificate,
)
from pheroos.governance._certificate.local import (
    _StableCommitLeaves,
    _current_authority_heads_match_receipt,
    _stable_commit_leaves_from_receipt,
    local_commit_receipt_matches,
)
from pheroos.governance._certificate.records import (
    EVIDENCE_COMMIT_CERTIFICATE_DISCRIMINATOR,
    EVIDENCE_COMMIT_CERTIFICATE_VERSION,
    EvidenceCommitCertificate,
)
from pheroos.governance._commit_validation import (
    require_commit_step,
    require_commit_text,
)
from pheroos.governance._commit.certificate_contracts import (
    LEGACY_CERTIFICATE_IDENTITIES as _LEGACY_CERTIFICATE_IDENTITIES,
    certificate_identity_key as _certificate_id_key,
)
from pheroos.governance._commit.local_receipt import (
    LocalCommitReceipt,
    local_commit_receipt_fingerprint,
    local_commit_receipt_is_authoritative,
    local_commit_receipt_payload,
)
from pheroos.governance._legacy.authority_registry import LEGACY_AUTHORITY_REGISTRY
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit import CommitAssessment, CommitEvaluationContext
from pheroos.governance.commit_state import (
    AuthorityScope,
    CommitFinalityVerification,
    CommitReplayState,
    CommitWindowState,
    commit_window_seal_matches_receipt,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.risk import (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
)
from pheroos.governance.support_lease import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportLeaseReplayState,
)
from pheroos.protocol.commit_models import CollectiveCommitPolicy, CommitAssurance


class _EvidenceCertificateBody(_StableCommitLeaves):
    schema_discriminator: str
    certificate_version: str
    wire_version: str
    canonicalization: str
    hash_algorithm: str
    certificate_id: str
    authority_scope: AuthorityScope
    local_receipt_ref: str
    issuer_id: str
    authority: AuthorityLevel
    issued_at_step: int
    provenance: str
    trace_event_id: str


def evidence_commit_certificate_body_root(
    receipt: LocalCommitReceipt,
    *,
    certificate_id: str,
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> str:
    body = _evidence_certificate_body_from_receipt(
        receipt,
        certificate_id=certificate_id,
        issuer_id=issuer_id,
        authority=authority,
        issued_at_step=issued_at_step,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )
    return _certificate_body_root(
        body,
        schema="pheroos-evidence-commit-certificate-body-v1",
        profile=receipt.profile,
    )


def issue_evidence_commit_certificate(
    receipt: LocalCommitReceipt,
    *,
    commit_policy: CollectiveCommitPolicy,
    certificate_id: str,
    issuer_attestation_refs: Sequence[str],
    trusted_issuer_attestations: Mapping[str, str],
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> EvidenceCommitCertificate:
    if not local_commit_receipt_is_authoritative(receipt):
        raise GovernanceError(
            "portable commit certificate requires an authoritative local receipt"
        )
    if receipt.assurance not in {
        CommitAssurance.CERTIFIED,
        CommitAssurance.DISTRIBUTED,
    }:
        raise GovernanceError(
            "EvidenceCommitCertificate requires certified or distributed assurance"
        )
    _validate_policy_binding(
        commit_policy,
        profile=receipt.profile,
        assurance=receipt.assurance,
        target=receipt.target,
        commit_policy_root=receipt.commit_policy_root,
    )
    certificate_policy = commit_policy.certificate
    expected_mode = (
        "portable" if receipt.assurance is CommitAssurance.CERTIFIED else "distributed"
    )
    if (
        certificate_policy.mode != expected_mode
        or not certificate_policy.issuer_attestation_required
        or not certificate_policy.independent_verification_required
    ):
        raise GovernanceError(
            "certified assurance requires portable independently verified certificates"
        )
    body = _evidence_certificate_body_from_receipt(
        receipt,
        certificate_id=certificate_id,
        issuer_id=issuer_id,
        authority=authority,
        issued_at_step=issued_at_step,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )
    body_root = _certificate_body_root(
        body,
        schema="pheroos-evidence-commit-certificate-body-v1",
        profile=receipt.profile,
    )
    attestations = _require_attestation_bindings(
        issuer_attestation_refs,
        trusted_issuer_attestations,
        body_root=body_root,
        field_name="evidence certificate",
    )
    certificate_root = _certificate_envelope_root(
        body_root,
        attestations,
        schema="pheroos-evidence-commit-certificate-envelope-v1",
        profile=receipt.profile,
    )
    certificate = EvidenceCommitCertificate(
        **body,
        issuer_attestation_refs=attestations,
        certificate_body_root=body_root,
        certificate_root=certificate_root,
    )
    return _register_portable_evidence_certificate(certificate)


def verify_evidence_commit_finality(
    certificate: EvidenceCommitCertificate,
    receipt: LocalCommitReceipt,
    context: CommitEvaluationContext,
    assessment: CommitAssessment,
    window_state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy,
    risk_chain_state: RiskAssessmentChainState,
    risk_assessment: RiskAssessment,
    threshold_snapshot: CommitThresholdSnapshot,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: CommitReplayState,
    support_replay_state: SupportLeaseReplayState,
    trusted_issuer_attestations: Mapping[str, str],
    current_step: int,
    verifier_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
) -> CommitFinalityVerification:
    """Verify a portable central certificate and issue typed certified finality."""

    if certificate.assurance is not CommitAssurance.CERTIFIED:
        raise GovernanceError(
            "portable central finality is reserved for certified assurance"
        )
    certificate_ref = evidence_commit_certificate_fingerprint(certificate)
    if not verify_evidence_commit_certificate(
        certificate,
        trusted_issuer_attestations=trusted_issuer_attestations,
        expected_certificate_ref=certificate_ref,
    ):
        raise GovernanceError(
            "portable evidence certificate is not independently valid"
        )
    if (
        not local_commit_receipt_is_authoritative(receipt)
        or certificate.local_receipt_ref != local_commit_receipt_fingerprint(receipt)
        or certificate.issued_at_step < receipt.issued_at_step
    ):
        raise GovernanceError("portable certificate local receipt lineage is invalid")
    if not commit_window_seal_matches_receipt(window_state, receipt):
        raise GovernanceError(
            "portable certificate requires the current sealed receipt"
        )
    if not local_commit_receipt_matches(
        receipt,
        context,
        assessment,
        window_state,
        commit_policy=commit_policy,
        risk_chain_state=risk_chain_state,
        risk_assessment=risk_assessment,
        threshold_snapshot=threshold_snapshot,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_epoch_state,
        replay_state=replay_state,
        support_replay_state=support_replay_state,
        current_step=receipt.issued_at_step,
        expected_output_payload_fingerprint=(certificate.output_payload_fingerprint),
    ):
        raise GovernanceError("portable certificate sealed receipt does not rebuild")
    receipt_leaves = local_commit_receipt_payload(receipt)
    ignored = {
        "schema_discriminator",
        "receipt_version",
        "receipt_id",
        "authority_scope",
        "issuer_id",
        "authority",
        "issued_at_step",
        "provenance",
        "trace_event_id",
    }
    if any(
        getattr(certificate, name) != value
        for name, value in receipt_leaves.items()
        if name not in ignored
    ):
        raise GovernanceError(
            "portable evidence certificate does not reproduce the sealed receipt"
        )
    if not _current_authority_heads_match_receipt(
        receipt,
        context=context,
        assessment=assessment,
        window_state=window_state,
        commit_policy=commit_policy,
        risk_chain_state=risk_chain_state,
        risk_assessment=risk_assessment,
        threshold_snapshot=threshold_snapshot,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_epoch_state,
        replay_state=replay_state,
        support_replay_state=support_replay_state,
        current_step=current_step,
    ):
        raise GovernanceError(
            "portable evidence finality current authority heads changed or expired"
        )
    return _issue_typed_finality_verification(
        certificate,
        certificate_kind=EVIDENCE_COMMIT_CERTIFICATE_DISCRIMINATOR,
        certificate_ref=certificate_ref,
        current_step=current_step,
        verifier_id=verifier_id,
        authority=authority,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )


def _register_portable_evidence_certificate(
    certificate: EvidenceCommitCertificate,
) -> EvidenceCommitCertificate:
    certificate_ref = evidence_commit_certificate_fingerprint(certificate)
    key = _certificate_id_key(
        certificate,
        discriminator=EVIDENCE_COMMIT_CERTIFICATE_DISCRIMINATOR,
        record_id=certificate.certificate_id,
    )
    with LEGACY_AUTHORITY_REGISTRY.transaction() as registry:
        existing = registry.get(_LEGACY_CERTIFICATE_IDENTITIES, key)
        if existing is not None:
            existing_ref, existing_record = existing
            if existing_ref == certificate_ref:
                assert type(existing_record) is EvidenceCommitCertificate
                return existing_record
            raise GovernanceError(
                "evidence certificate id is already bound to a different body"
            )
        registry.set(
            _LEGACY_CERTIFICATE_IDENTITIES,
            key,
            (certificate_ref, certificate),
        )
        return certificate


def _evidence_certificate_body_from_receipt(
    receipt: LocalCommitReceipt,
    *,
    certificate_id: str,
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> _EvidenceCertificateBody:
    if not local_commit_receipt_is_authoritative(receipt):
        raise GovernanceError(
            "evidence certificate body requires authoritative local receipt"
        )
    if receipt.assurance not in {
        CommitAssurance.CERTIFIED,
        CommitAssurance.DISTRIBUTED,
    }:
        raise GovernanceError(
            "evidence certificate body requires certified or distributed assurance"
        )
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("evidence certificate issuer lacks governance authority")
    payload = _stable_commit_leaves_from_receipt(receipt)
    issued = require_commit_step(
        issued_at_step,
        "evidence certificate issued_at_step",
    )
    if issued < receipt.issued_at_step:
        raise GovernanceError(
            "evidence certificate cannot predate its sealed local receipt"
        )
    return {
        "schema_discriminator": EVIDENCE_COMMIT_CERTIFICATE_DISCRIMINATOR,
        "certificate_version": EVIDENCE_COMMIT_CERTIFICATE_VERSION,
        "wire_version": receipt.wire_version,
        "canonicalization": receipt.canonicalization,
        "hash_algorithm": receipt.hash_algorithm,
        "certificate_id": require_commit_text(
            certificate_id,
            "evidence certificate certificate_id",
        ),
        "authority_scope": AuthorityScope.CERTIFIED,
        **payload,
        "local_receipt_ref": local_commit_receipt_fingerprint(receipt),
        "issuer_id": require_commit_text(
            issuer_id,
            "evidence certificate issuer_id",
        ),
        "authority": authority,
        "issued_at_step": issued,
        "provenance": require_commit_text(
            provenance,
            "evidence certificate provenance",
        ),
        "trace_event_id": require_commit_text(
            trace_event_id,
            "evidence certificate trace_event_id",
        ),
    }


__all__ = [
    "EvidenceCommitCertificate",
    "evidence_commit_certificate_body_root",
    "evidence_commit_certificate_fingerprint",
    "evidence_commit_certificate_from_payload",
    "evidence_commit_certificate_payload",
    "issue_evidence_commit_certificate",
    "verify_evidence_commit_certificate",
    "verify_evidence_commit_finality",
]
