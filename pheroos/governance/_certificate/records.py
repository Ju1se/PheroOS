from __future__ import annotations

"""Canonical portable and terminal certificate records."""

from dataclasses import dataclass, field

from pheroos.governance._certificate.invariants import (
    _certificate_body_root,
    _certificate_envelope_root,
    _dataclass_public_payload,
)
from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance._commit.certificate_contracts import (
    validate_certificate_header as _validate_certificate_header,
    validate_commit_lineage as _validate_commit_lineage,
    validate_issuer_metadata as _validate_issuer_metadata,
)
from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.commit_state import AuthorityScope, DecisionOutcomeKind
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    COMMIT_AUTHORITY_SCOPE_BY_ASSURANCE,
    CommitAssurance,
)


EVIDENCE_COMMIT_CERTIFICATE_VERSION = (
    "pheroos-evidence-commit-certificate-v1"
)
OUTCOME_CERTIFICATE_VERSION = "pheroos-outcome-certificate-v1"
EVIDENCE_COMMIT_CERTIFICATE_DISCRIMINATOR = "evidence_commit_certificate"
OUTCOME_CERTIFICATE_DISCRIMINATOR = "outcome_certificate"


@dataclass(frozen=True)
class EvidenceCommitCertificate:
    """Portable certified commit proof.

    Trust is supplied to the verifier as opaque issuer-attestation references
    bound to ``certificate_body_root``.  Verification never depends on an
    in-process issuance sentinel.
    """

    schema_discriminator: str
    certificate_version: str
    wire_version: str
    canonicalization: str
    hash_algorithm: str
    certificate_id: str
    profile: str
    assurance: CommitAssurance
    authority_scope: AuthorityScope
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    candidate_id: str
    claim_fingerprint: str
    output_payload_fingerprint: str
    risk_chain_state_root: str
    risk_assessment_root: str
    risk_policy_root: str
    membership_snapshot_root: str
    membership_epoch_state_root: str
    membership_root: str
    threshold_root: str
    replay_state_root: str
    replay_root: str
    support_replay_state_root: str
    support_replay_root: str
    candidate_evidence_root: str
    candidate_challenge_root: str
    candidate_lease_root: str
    evidence_root: str
    challenge_root: str
    lease_root: str
    window_state_root: str
    window_root: str
    stop_resolution_root: str
    permission_root: str
    context_root: str
    assessment_root: str
    local_receipt_ref: str
    issuer_id: str
    authority: AuthorityLevel
    issued_at_step: int
    provenance: str
    trace_event_id: str
    issuer_attestation_refs: tuple[str, ...]
    certificate_body_root: str
    certificate_root: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "issuer_attestation_refs",
            require_commit_labels(
                self.issuer_attestation_refs,
                "evidence certificate issuer_attestation_refs",
            ),
        )
        _validate_evidence_commit_certificate(self)

@dataclass(frozen=True)
class OutcomeCertificate:
    """Typed proof for a terminal outcome, never an epistemic commit proof."""

    schema_discriminator: str
    certificate_version: str
    wire_version: str
    canonicalization: str
    hash_algorithm: str
    certificate_id: str
    outcome_kind: DecisionOutcomeKind
    outcome_ref: str
    profile: str
    assurance: CommitAssurance
    authority_scope: AuthorityScope
    authoritative_commit: bool
    epistemically_committed: bool
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    candidate_id: str
    claim_fingerprint: str
    output_payload_fingerprint: str
    risk_chain_state_root: str
    risk_assessment_root: str
    risk_policy_root: str
    membership_snapshot_root: str
    membership_epoch_state_root: str
    membership_root: str
    threshold_root: str
    replay_state_root: str
    replay_root: str
    support_replay_state_root: str
    support_replay_root: str
    evidence_root: str
    challenge_root: str
    lease_root: str
    candidate_evidence_root: str
    candidate_challenge_root: str
    candidate_lease_root: str
    window_state_root: str
    window_root: str
    stop_resolution_root: str
    permission_root: str
    context_root: str
    assessment_root: str
    commit_certificate_ref: str
    issuer_id: str
    authority: AuthorityLevel
    issued_at_step: int
    provenance: str
    trace_event_id: str
    issuer_attestation_refs: tuple[str, ...]
    certificate_body_root: str
    certificate_root: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "issuer_attestation_refs",
            require_commit_labels(
                self.issuer_attestation_refs,
                "outcome certificate issuer_attestation_refs",
                allow_empty=True,
            ),
        )
        _validate_outcome_certificate(self)

def _validate_evidence_commit_certificate(
    certificate: EvidenceCommitCertificate,
) -> None:
    _validate_certificate_header(
        discriminator=certificate.schema_discriminator,
        expected_discriminator=EVIDENCE_COMMIT_CERTIFICATE_DISCRIMINATOR,
        version=certificate.certificate_version,
        expected_version=EVIDENCE_COMMIT_CERTIFICATE_VERSION,
        wire_version=certificate.wire_version,
        canonicalization=certificate.canonicalization,
        hash_algorithm=certificate.hash_algorithm,
        profile=certificate.profile,
        assurance=certificate.assurance,
    )
    if certificate.assurance not in {
        CommitAssurance.CERTIFIED,
        CommitAssurance.DISTRIBUTED,
    }:
        raise GovernanceError(
            "evidence certificate requires certified or distributed assurance"
        )
    if certificate.authority_scope is not AuthorityScope.CERTIFIED:
        raise GovernanceError("evidence certificate authority scope is invalid")
    require_commit_text(
        certificate.certificate_id,
        "evidence certificate certificate_id",
    )
    _validate_commit_lineage(
        certificate,
        field_name="evidence certificate",
        complete=True,
    )
    require_commit_fingerprint(
        certificate.local_receipt_ref,
        "evidence certificate local_receipt_ref",
    )
    _validate_issuer_metadata(certificate, field_name="evidence certificate")
    if not certificate.issuer_attestation_refs:
        raise GovernanceError("evidence certificate requires issuer attestation")
    _validate_certificate_roots(
        certificate,
        body_schema="pheroos-evidence-commit-certificate-body-v1",
        envelope_schema="pheroos-evidence-commit-certificate-envelope-v1",
    )

def _validate_outcome_certificate(certificate: OutcomeCertificate) -> None:
    _validate_certificate_header(
        discriminator=certificate.schema_discriminator,
        expected_discriminator=OUTCOME_CERTIFICATE_DISCRIMINATOR,
        version=certificate.certificate_version,
        expected_version=OUTCOME_CERTIFICATE_VERSION,
        wire_version=certificate.wire_version,
        canonicalization=certificate.canonicalization,
        hash_algorithm=certificate.hash_algorithm,
        profile=certificate.profile,
        assurance=certificate.assurance,
    )
    if type(certificate.outcome_kind) is not DecisionOutcomeKind:
        raise GovernanceError("outcome certificate kind is invalid")
    require_commit_text(
        certificate.certificate_id,
        "outcome certificate certificate_id",
    )
    for name in ("authoritative_commit", "epistemically_committed"):
        if type(getattr(certificate, name)) is not bool:
            raise GovernanceError(
                f"outcome certificate {name} must be a boolean"
            )
    require_commit_fingerprint(certificate.outcome_ref, "outcome certificate outcome_ref")
    _validate_outcome_lineage(certificate)
    _validate_issuer_metadata(certificate, field_name="outcome certificate")
    if certificate.outcome_kind is DecisionOutcomeKind.EVIDENCE_COMMIT:
        if not certificate.authoritative_commit or not certificate.epistemically_committed:
            raise GovernanceError("evidence outcome certificate authority is invalid")
        if certificate.assurance is CommitAssurance.ADVISORY:
            raise GovernanceError(
                "advisory outcome certificate cannot claim an evidence commit"
            )
        expected_scope = COMMIT_AUTHORITY_SCOPE_BY_ASSURANCE[
            certificate.assurance.value
        ]
        if certificate.authority_scope.value != expected_scope:
            raise GovernanceError(
                "evidence outcome certificate authority scope is invalid"
            )
        if not certificate.commit_certificate_ref:
            raise GovernanceError("evidence outcome lacks its typed commit proof")
    else:
        if certificate.authoritative_commit or certificate.epistemically_committed:
            raise GovernanceError("non-commit outcome certificate cannot claim commit")
        if certificate.commit_certificate_ref:
            raise GovernanceError(
                "non-commit outcome certificate cannot carry a commit proof"
            )
        expected_scope = (
            AuthorityScope.DENIAL
            if certificate.outcome_kind is DecisionOutcomeKind.BLOCKED
            else AuthorityScope.NONE
        )
        if certificate.authority_scope is not expected_scope:
            raise GovernanceError(
                "non-commit outcome certificate authority scope is invalid"
            )
        if certificate.outcome_kind is DecisionOutcomeKind.SAFE_FALLBACK:
            if not certificate.candidate_id or not certificate.claim_fingerprint:
                raise GovernanceError("safe fallback certificate requires claim binding")
    if certificate.assurance in {
        CommitAssurance.CERTIFIED,
        CommitAssurance.DISTRIBUTED,
    }:
        if not certificate.issuer_attestation_refs:
            raise GovernanceError(
                "portable outcome certificate requires issuer attestation"
            )
    elif certificate.issuer_attestation_refs:
        raise GovernanceError(
            "local outcome certificate cannot claim portable attestations"
        )
    _validate_certificate_roots(
        certificate,
        body_schema="pheroos-outcome-certificate-body-v1",
        envelope_schema="pheroos-outcome-certificate-envelope-v1",
    )

def _validate_outcome_lineage(certificate: OutcomeCertificate) -> None:
    for name in ("protocol_id", "run_id", "target"):
        require_commit_text(
            getattr(certificate, name),
            f"outcome certificate {name}",
        )
    require_commit_step(certificate.epoch, "outcome certificate epoch")
    if certificate.candidate_id:
        require_commit_text(certificate.candidate_id, "outcome certificate candidate_id")
        require_commit_fingerprint(
            certificate.claim_fingerprint,
            "outcome certificate claim_fingerprint",
        )
    elif certificate.claim_fingerprint:
        raise GovernanceError("outcome certificate claim requires a candidate")
    for name in (
        "manifest_root",
        "commit_policy_root",
        "output_payload_fingerprint",
        "risk_assessment_root",
        "membership_root",
        "threshold_root",
        "replay_state_root",
        "replay_root",
        "window_state_root",
        "window_root",
    ):
        require_commit_fingerprint(
            getattr(certificate, name),
            f"outcome certificate {name}",
        )
    for name in (
        "risk_chain_state_root",
        "risk_policy_root",
        "membership_snapshot_root",
        "membership_epoch_state_root",
        "support_replay_state_root",
        "support_replay_root",
        "evidence_root",
        "challenge_root",
        "lease_root",
        "candidate_evidence_root",
        "candidate_challenge_root",
        "candidate_lease_root",
        "stop_resolution_root",
        "permission_root",
        "context_root",
        "assessment_root",
        "commit_certificate_ref",
    ):
        raw = getattr(certificate, name)
        if raw:
            require_commit_fingerprint(raw, f"outcome certificate {name}")

def _validate_certificate_roots(
    certificate: EvidenceCommitCertificate | OutcomeCertificate,
    *,
    body_schema: str,
    envelope_schema: str,
) -> None:
    require_commit_fingerprint(
        certificate.certificate_body_root,
        "certificate body root",
    )
    require_commit_fingerprint(certificate.certificate_root, "certificate root")
    body = _dataclass_public_payload(certificate)
    body.pop("issuer_attestation_refs")
    body.pop("certificate_body_root")
    body.pop("certificate_root")
    expected_body_root = _certificate_body_root(
        body,
        schema=body_schema,
        profile=certificate.profile,
    )
    if certificate.certificate_body_root != expected_body_root:
        raise GovernanceError("certificate body root does not rebuild")
    expected_certificate_root = _certificate_envelope_root(
        expected_body_root,
        certificate.issuer_attestation_refs,
        schema=envelope_schema,
        profile=certificate.profile,
    )
    if certificate.certificate_root != expected_certificate_root:
        raise GovernanceError("certificate envelope root does not rebuild")


__all__ = ["EvidenceCommitCertificate", "OutcomeCertificate"]
