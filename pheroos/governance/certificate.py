from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from threading import RLock
from typing import Any

from pheroos.governance._commit_validation import (
    require_commit_assurance,
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit import (
    CommitAssessment,
    CommitAssessmentStatus,
    CommitEvaluationContext,
    commit_assessment_fingerprint,
    commit_assessment_is_authoritative,
    commit_evaluation_context_fingerprint,
    commit_evaluation_context_is_authoritative,
)
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.commit_state import (
    _seal_commit_window_from_local_receipt,
    AuthorityScope,
    CommitFinalityVerification,
    CommitReplayState,
    CommitWindowState,
    DecisionOutcome,
    DecisionOutcomeKind,
    commit_window_ready,
    commit_window_seal_matches_receipt,
    commit_window_state_fingerprint,
    commit_window_state_is_authoritative,
    commit_window_state_is_current,
    commit_replay_state_fingerprint,
    commit_replay_state_matches,
    decision_outcome_fingerprint,
    decision_outcome_is_authoritative,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.risk import (
    CommitThresholdSnapshot,
    RiskAssessment,
    RiskAssessmentChainState,
    commit_threshold_snapshot_fingerprint,
    commit_threshold_snapshot_matches,
    risk_assessment_chain_state_fingerprint,
    risk_assessment_fingerprint,
)
from pheroos.governance.support_lease import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    SupportLeaseReplayState,
    eligible_membership_epoch_state_fingerprint,
    eligible_principal_snapshot_fingerprint,
    eligible_principal_snapshot_matches,
    support_lease_replay_state_fingerprint,
    support_lease_replay_state_is_current,
)
from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_AUTHORITY_SCOPE_BY_ASSURANCE,
    COMMIT_PROFILES_BY_ASSURANCE,
    COMMIT_WIRE_VERSION,
    CollectiveCommitPolicy,
    CommitAssurance,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint


LOCAL_COMMIT_RECEIPT_VERSION = "pheroos-local-commit-receipt-v1"
EVIDENCE_COMMIT_CERTIFICATE_VERSION = (
    "pheroos-evidence-commit-certificate-v1"
)
OUTCOME_CERTIFICATE_VERSION = "pheroos-outcome-certificate-v1"
LOCAL_COMMIT_RECEIPT_DISCRIMINATOR = "local_commit_receipt"
EVIDENCE_COMMIT_CERTIFICATE_DISCRIMINATOR = (
    "evidence_commit_certificate"
)
OUTCOME_CERTIFICATE_DISCRIMINATOR = "outcome_certificate"
CERTIFICATE_HASH_ALGORITHM = "sha256"

_LOCAL_COMMIT_RECEIPT_ISSUANCE = object()
_OUTCOME_CERTIFICATE_ISSUANCE = object()
_CERTIFICATE_ID_LOCK = RLock()
_CERTIFICATE_ID_AUTHORITIES: dict[
    tuple[str, str, str, str, str, int, str],
    tuple[str, object],
] = {}


@dataclass(frozen=True)
class LocalCommitReceipt:
    """Governance-local evidence-bound proof of a stable central commit.

    A receipt is deliberately process-local authority.  It is never accepted by
    the portable evidence-certificate verifier and cannot satisfy certified or
    distributed finality by itself.
    """

    schema_discriminator: str
    receipt_version: str
    wire_version: str
    canonicalization: str
    hash_algorithm: str
    receipt_id: str
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
    issuer_id: str
    authority: AuthorityLevel
    issued_at_step: int
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _validate_local_commit_receipt(self)


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


def output_payload_fingerprint(
    payload: Mapping[str, Any],
    *,
    profile: str,
) -> str:
    if not isinstance(payload, Mapping):
        raise GovernanceError("commit output payload must be a mapping")
    normalized_profile = require_commit_profile(
        profile,
        "commit output payload profile",
    )
    return commit_payload_fingerprint(
        payload,
        schema="pheroos-commit-output-payload-v1",
        profile=normalized_profile,
    )


def issue_local_commit_receipt(
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
    output_payload_fingerprint: str,
    receipt_id: str,
    issuer_id: str,
    authority: AuthorityLevel,
    current_step: int,
    provenance: str,
    trace_event_id: str,
) -> LocalCommitReceipt:
    """Issue the evidence-bound local layer after all central gates are stable."""

    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("local commit receipt requires governance authority")
    current = require_commit_step(current_step, "local receipt current_step")
    leaves = _stable_commit_leaves(
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
        output_fingerprint=output_payload_fingerprint,
        current_step=current,
    )
    receipt = LocalCommitReceipt(
        schema_discriminator=LOCAL_COMMIT_RECEIPT_DISCRIMINATOR,
        receipt_version=LOCAL_COMMIT_RECEIPT_VERSION,
        wire_version=commit_policy.certificate.wire_version,
        canonicalization=commit_policy.certificate.canonicalization,
        hash_algorithm=commit_policy.certificate.hash_algorithm,
        receipt_id=require_commit_text(receipt_id, "local receipt receipt_id"),
        authority_scope=AuthorityScope.GOVERNANCE_LOCAL,
        issuer_id=require_commit_text(issuer_id, "local receipt issuer_id"),
        authority=authority,
        issued_at_step=current,
        provenance=require_commit_text(provenance, "local receipt provenance"),
        trace_event_id=require_commit_text(
            trace_event_id,
            "local receipt trace_event_id",
        ),
        **leaves,
    )
    receipt_ref = local_commit_receipt_fingerprint(receipt)
    registered = _register_local_receipt(receipt, receipt_ref=receipt_ref)
    _seal_commit_window_from_local_receipt(window_state, registered)
    return registered


def local_commit_receipt_payload(
    receipt: LocalCommitReceipt,
) -> dict[str, object]:
    if type(receipt) is not LocalCommitReceipt:
        raise GovernanceError("local commit receipt must use the canonical record")
    _validate_local_commit_receipt(receipt)
    return _dataclass_public_payload(receipt)


def local_commit_receipt_fingerprint(receipt: LocalCommitReceipt) -> str:
    return commit_payload_fingerprint(
        local_commit_receipt_payload(receipt),
        schema=LOCAL_COMMIT_RECEIPT_VERSION,
        profile=receipt.profile,
    )


def local_commit_receipt_is_authoritative(receipt: object) -> bool:
    if type(receipt) is not LocalCommitReceipt:
        return False
    try:
        issuance = receipt._issuance
        key = _certificate_id_key(
            receipt,
            discriminator=LOCAL_COMMIT_RECEIPT_DISCRIMINATOR,
            record_id=receipt.receipt_id,
        )
        with _CERTIFICATE_ID_LOCK:
            registered = _CERTIFICATE_ID_AUTHORITIES.get(key)
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _LOCAL_COMMIT_RECEIPT_ISSUANCE
            and issuance[1] == local_commit_receipt_fingerprint(receipt)
            and registered is not None
            and registered[0] == issuance[1]
            and registered[1] is receipt
        )
    except Exception:
        return False


def local_commit_receipt_matches(
    receipt: LocalCommitReceipt | None,
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
    current_step: int,
    expected_output_payload_fingerprint: str = "",
) -> bool:
    """Rebuild every central-commit leaf against the current authority heads."""

    try:
        if not local_commit_receipt_is_authoritative(receipt) or receipt is None:
            return False
        if expected_output_payload_fingerprint and (
            receipt.output_payload_fingerprint
            != require_commit_fingerprint(
                expected_output_payload_fingerprint,
                "expected local receipt output payload fingerprint",
            )
        ):
            return False
        expected = _stable_commit_leaves(
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
            output_fingerprint=receipt.output_payload_fingerprint,
            current_step=current_step,
        )
        return all(getattr(receipt, name) == value for name, value in expected.items())
    except (GovernanceError, TypeError, ValueError):
        return False


def verify_local_commit_finality(
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
    current_step: int,
    verifier_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
) -> CommitFinalityVerification:
    """Convert a verified local receipt into the liveness typed-finality ABI."""

    if receipt.assurance is not CommitAssurance.EVIDENCE_BOUND:
        raise GovernanceError(
            "local receipt finality is reserved for evidence-bound assurance"
        )
    if current_step != receipt.issued_at_step:
        raise GovernanceError(
            "evidence-bound local finality must be verified at the receipt step"
        )
    if not commit_window_seal_matches_receipt(window_state, receipt):
        raise GovernanceError(
            "evidence-bound local finality requires the current receipt seal"
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
        current_step=current_step,
    ):
        raise GovernanceError("local receipt does not verify against current heads")
    return _issue_typed_finality_verification(
        receipt,
        certificate_kind=LOCAL_COMMIT_RECEIPT_DISCRIMINATOR,
        certificate_ref=local_commit_receipt_fingerprint(receipt),
        current_step=current_step,
        verifier_id=verifier_id,
        authority=authority,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )


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
        "portable"
        if receipt.assurance is CommitAssurance.CERTIFIED
        else "distributed"
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


def evidence_commit_certificate_payload(
    certificate: EvidenceCommitCertificate,
) -> dict[str, object]:
    if type(certificate) is not EvidenceCommitCertificate:
        raise GovernanceError(
            "evidence commit certificate must use the canonical record"
        )
    _validate_evidence_commit_certificate(certificate)
    return _dataclass_public_payload(certificate)


def evidence_commit_certificate_fingerprint(
    certificate: EvidenceCommitCertificate,
) -> str:
    return commit_payload_fingerprint(
        evidence_commit_certificate_payload(certificate),
        schema=EVIDENCE_COMMIT_CERTIFICATE_VERSION,
        profile=certificate.profile,
    )


def evidence_commit_certificate_from_payload(
    payload: Mapping[str, object],
) -> EvidenceCommitCertificate:
    values = _strict_payload_values(
        payload,
        EvidenceCommitCertificate,
        field_name="evidence commit certificate payload",
    )
    values["assurance"] = _coerce_assurance(values["assurance"])
    values["authority_scope"] = _coerce_authority_scope(
        values["authority_scope"]
    )
    values["authority"] = _coerce_authority(values["authority"])
    values["issuer_attestation_refs"] = tuple(
        _require_sequence(values["issuer_attestation_refs"], "issuer attestations")
    )
    try:
        return EvidenceCommitCertificate(**values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(
            f"evidence commit certificate payload is invalid: {exc}"
        ) from exc


def verify_evidence_commit_certificate(
    certificate_or_payload: EvidenceCommitCertificate | Mapping[str, object],
    *,
    trusted_issuer_attestations: Mapping[str, str],
    expected_certificate_ref: str = "",
    expected_claim_fingerprint: str = "",
    expected_output_payload_fingerprint: str = "",
) -> bool:
    """Independently rebuild and verify every portable certificate leaf."""

    try:
        certificate = (
            certificate_or_payload
            if type(certificate_or_payload) is EvidenceCommitCertificate
            else evidence_commit_certificate_from_payload(certificate_or_payload)
        )
        assert type(certificate) is EvidenceCommitCertificate
        _validate_evidence_commit_certificate(certificate)
        if not _attestations_match(
            certificate.issuer_attestation_refs,
            trusted_issuer_attestations,
            body_root=certificate.certificate_body_root,
        ):
            return False
        if expected_certificate_ref and (
            evidence_commit_certificate_fingerprint(certificate)
            != require_commit_fingerprint(
                expected_certificate_ref,
                "expected evidence certificate ref",
            )
        ):
            return False
        if expected_claim_fingerprint and (
            certificate.claim_fingerprint
            != require_commit_fingerprint(
                expected_claim_fingerprint,
                "expected evidence certificate claim",
            )
        ):
            return False
        if expected_output_payload_fingerprint and (
            certificate.output_payload_fingerprint
            != require_commit_fingerprint(
                expected_output_payload_fingerprint,
                "expected evidence certificate output",
            )
        ):
            return False
        return True
    except (AssertionError, TypeError, ValueError, GovernanceError):
        return False


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
        raise GovernanceError("portable evidence certificate is not independently valid")
    if (
        not local_commit_receipt_is_authoritative(receipt)
        or certificate.local_receipt_ref
        != local_commit_receipt_fingerprint(receipt)
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
        expected_output_payload_fingerprint=(
            certificate.output_payload_fingerprint
        ),
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


def outcome_certificate_body_root(
    outcome: DecisionOutcome,
    window_state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy,
    output_payload_fingerprint: str,
    certificate_id: str,
    context: CommitEvaluationContext | None,
    assessment: CommitAssessment | None,
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> str:
    body = _outcome_certificate_body(
        outcome,
        window_state,
        commit_policy=commit_policy,
        output_fingerprint=output_payload_fingerprint,
        certificate_id=certificate_id,
        context=context,
        assessment=assessment,
        issuer_id=issuer_id,
        authority=authority,
        issued_at_step=issued_at_step,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )
    return _certificate_body_root(
        body,
        schema="pheroos-outcome-certificate-body-v1",
        profile=outcome.profile,
    )


def issue_outcome_certificate(
    outcome: DecisionOutcome,
    window_state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy,
    output_payload_fingerprint: str,
    certificate_id: str,
    context: CommitEvaluationContext | None,
    assessment: CommitAssessment | None,
    issuer_attestation_refs: Sequence[str] = (),
    trusted_issuer_attestations: Mapping[str, str] | None = None,
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> OutcomeCertificate:
    body = _outcome_certificate_body(
        outcome,
        window_state,
        commit_policy=commit_policy,
        output_fingerprint=output_payload_fingerprint,
        certificate_id=certificate_id,
        context=context,
        assessment=assessment,
        issuer_id=issuer_id,
        authority=authority,
        issued_at_step=issued_at_step,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )
    body_root = _certificate_body_root(
        body,
        schema="pheroos-outcome-certificate-body-v1",
        profile=outcome.profile,
    )
    requires_portable = commit_policy.certificate.issuer_attestation_required
    if requires_portable:
        attestations = _require_attestation_bindings(
            issuer_attestation_refs,
            trusted_issuer_attestations,
            body_root=body_root,
            field_name="outcome certificate",
        )
    else:
        if tuple(issuer_attestation_refs):
            raise GovernanceError(
                "local outcome certificates cannot claim portable attestations"
            )
        attestations = ()
    certificate_root = _certificate_envelope_root(
        body_root,
        attestations,
        schema="pheroos-outcome-certificate-envelope-v1",
        profile=outcome.profile,
    )
    certificate = OutcomeCertificate(
        **body,
        issuer_attestation_refs=attestations,
        certificate_body_root=body_root,
        certificate_root=certificate_root,
    )
    certificate_ref = outcome_certificate_fingerprint(certificate)
    return _register_outcome_certificate(
        certificate,
        certificate_ref=certificate_ref,
    )


def outcome_certificate_payload(
    certificate: OutcomeCertificate,
) -> dict[str, object]:
    if type(certificate) is not OutcomeCertificate:
        raise GovernanceError("outcome certificate must use the canonical record")
    _validate_outcome_certificate(certificate)
    return _dataclass_public_payload(certificate)


def outcome_certificate_fingerprint(certificate: OutcomeCertificate) -> str:
    return commit_payload_fingerprint(
        outcome_certificate_payload(certificate),
        schema=OUTCOME_CERTIFICATE_VERSION,
        profile=certificate.profile,
    )


def outcome_certificate_is_authoritative(certificate: object) -> bool:
    if type(certificate) is not OutcomeCertificate:
        return False
    try:
        issuance = certificate._issuance
        key = _certificate_id_key(
            certificate,
            discriminator=OUTCOME_CERTIFICATE_DISCRIMINATOR,
            record_id=certificate.certificate_id,
        )
        with _CERTIFICATE_ID_LOCK:
            registered = _CERTIFICATE_ID_AUTHORITIES.get(key)
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _OUTCOME_CERTIFICATE_ISSUANCE
            and issuance[1] == outcome_certificate_fingerprint(certificate)
            and registered is not None
            and registered[0] == issuance[1]
            and registered[1] is certificate
        )
    except Exception:
        return False


def outcome_certificate_from_payload(
    payload: Mapping[str, object],
) -> OutcomeCertificate:
    values = _strict_payload_values(
        payload,
        OutcomeCertificate,
        field_name="outcome certificate payload",
    )
    values["outcome_kind"] = _coerce_outcome_kind(values["outcome_kind"])
    values["assurance"] = _coerce_assurance(values["assurance"])
    values["authority_scope"] = _coerce_authority_scope(
        values["authority_scope"]
    )
    values["authority"] = _coerce_authority(values["authority"])
    values["issuer_attestation_refs"] = tuple(
        _require_sequence(values["issuer_attestation_refs"], "issuer attestations")
    )
    try:
        return OutcomeCertificate(**values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(
            f"outcome certificate payload is invalid: {exc}"
        ) from exc


def verify_outcome_certificate(
    certificate_or_payload: OutcomeCertificate | Mapping[str, object],
    *,
    trusted_issuer_attestations: Mapping[str, str] | None = None,
    expected_certificate_ref: str = "",
    expected_output_payload_fingerprint: str = "",
) -> bool:
    try:
        certificate = (
            certificate_or_payload
            if type(certificate_or_payload) is OutcomeCertificate
            else outcome_certificate_from_payload(certificate_or_payload)
        )
        assert type(certificate) is OutcomeCertificate
        _validate_outcome_certificate(certificate)
        if certificate.issuer_attestation_refs:
            if not _attestations_match(
                certificate.issuer_attestation_refs,
                trusted_issuer_attestations,
                body_root=certificate.certificate_body_root,
            ):
                return False
        elif not outcome_certificate_is_authoritative(certificate):
            # A local serialized certificate has no portable authority.
            return False
        if expected_certificate_ref and (
            outcome_certificate_fingerprint(certificate)
            != require_commit_fingerprint(
                expected_certificate_ref,
                "expected outcome certificate ref",
            )
        ):
            return False
        if expected_output_payload_fingerprint and (
            certificate.output_payload_fingerprint
            != require_commit_fingerprint(
                expected_output_payload_fingerprint,
                "expected outcome certificate output",
            )
        ):
            return False
        return True
    except (AssertionError, TypeError, ValueError, GovernanceError):
        return False


def _certificate_id_key(
    value: LocalCommitReceipt | EvidenceCommitCertificate | OutcomeCertificate,
    *,
    discriminator: str,
    record_id: str,
) -> tuple[str, str, str, str, str, int, str]:
    return (
        discriminator,
        value.profile,
        value.protocol_id,
        value.run_id,
        value.target,
        value.epoch,
        record_id,
    )


def _issue_typed_finality_verification(
    certificate: LocalCommitReceipt | EvidenceCommitCertificate,
    *,
    certificate_kind: str,
    certificate_ref: str,
    current_step: int,
    verifier_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
) -> CommitFinalityVerification:
    from pheroos.governance.commit_state import (
        CommitFinalityStatus,
        _issue_commit_finality_verification,
    )

    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("commit finality verification requires governance authority")
    current = require_commit_step(current_step, "commit finality verified_at_step")
    if current < certificate.issued_at_step:
        raise GovernanceError(
            "central commit finality certificate is from the future"
        )
    return _issue_commit_finality_verification(
        status=CommitFinalityStatus.VERIFIED,
        certificate_kind=certificate_kind,
        certificate_ref=require_commit_fingerprint(
            certificate_ref,
            "commit finality certificate_ref",
        ),
        profile=certificate.profile,
        assurance=certificate.assurance,
        manifest_root=certificate.manifest_root,
        commit_policy_root=certificate.commit_policy_root,
        protocol_id=certificate.protocol_id,
        run_id=certificate.run_id,
        target=certificate.target,
        epoch=certificate.epoch,
        candidate_id=certificate.candidate_id,
        context_ref=certificate.context_root,
        assessment_ref=certificate.assessment_root,
        window_state_ref=certificate.window_state_root,
        window_root=certificate.window_root,
        risk_assessment_root=certificate.risk_assessment_root,
        risk_chain_state_root=certificate.risk_chain_state_root,
        risk_policy_root=certificate.risk_policy_root,
        membership_root=certificate.membership_root,
        membership_snapshot_root=certificate.membership_snapshot_root,
        membership_epoch_state_root=certificate.membership_epoch_state_root,
        threshold_root=certificate.threshold_root,
        replay_state_ref=certificate.replay_state_root,
        replay_root=certificate.replay_root,
        support_replay_state_root=certificate.support_replay_state_root,
        support_replay_root=certificate.support_replay_root,
        collective_evidence_root=certificate.evidence_root,
        collective_challenge_root=certificate.challenge_root,
        collective_lease_root=certificate.lease_root,
        candidate_evidence_root=certificate.candidate_evidence_root,
        candidate_challenge_root=certificate.candidate_challenge_root,
        candidate_lease_root=certificate.candidate_lease_root,
        stop_resolution_root=certificate.stop_resolution_root,
        permission_root=certificate.permission_root,
        verified_at_step=current,
        verifier_id=require_commit_text(
            verifier_id,
            "commit finality verifier_id",
        ),
        authority=authority,
        provenance=require_commit_text(
            provenance,
            "commit finality provenance",
        ),
        trace_event_id=require_commit_text(
            trace_event_id,
            "commit finality trace_event_id",
        ),
    )


def _register_local_receipt(
    receipt: LocalCommitReceipt,
    *,
    receipt_ref: str,
) -> LocalCommitReceipt:
    key = _certificate_id_key(
        receipt,
        discriminator=LOCAL_COMMIT_RECEIPT_DISCRIMINATOR,
        record_id=receipt.receipt_id,
    )
    with _CERTIFICATE_ID_LOCK:
        existing = _CERTIFICATE_ID_AUTHORITIES.get(key)
        if existing is not None:
            existing_ref, existing_record = existing
            if (
                existing_ref == receipt_ref
                and local_commit_receipt_is_authoritative(existing_record)
            ):
                assert type(existing_record) is LocalCommitReceipt
                return existing_record
            raise GovernanceError(
                "local receipt id is already bound to a different body"
            )
        object.__setattr__(
            receipt,
            "_issuance",
            (_LOCAL_COMMIT_RECEIPT_ISSUANCE, receipt_ref),
        )
        _CERTIFICATE_ID_AUTHORITIES[key] = (receipt_ref, receipt)
        return receipt


def _register_portable_evidence_certificate(
    certificate: EvidenceCommitCertificate,
) -> EvidenceCommitCertificate:
    certificate_ref = evidence_commit_certificate_fingerprint(certificate)
    key = _certificate_id_key(
        certificate,
        discriminator=EVIDENCE_COMMIT_CERTIFICATE_DISCRIMINATOR,
        record_id=certificate.certificate_id,
    )
    with _CERTIFICATE_ID_LOCK:
        existing = _CERTIFICATE_ID_AUTHORITIES.get(key)
        if existing is not None:
            existing_ref, existing_record = existing
            if existing_ref == certificate_ref:
                assert type(existing_record) is EvidenceCommitCertificate
                return existing_record
            raise GovernanceError(
                "evidence certificate id is already bound to a different body"
            )
        _CERTIFICATE_ID_AUTHORITIES[key] = (certificate_ref, certificate)
        return certificate


def _register_outcome_certificate(
    certificate: OutcomeCertificate,
    *,
    certificate_ref: str,
) -> OutcomeCertificate:
    key = _certificate_id_key(
        certificate,
        discriminator=OUTCOME_CERTIFICATE_DISCRIMINATOR,
        record_id=certificate.certificate_id,
    )
    with _CERTIFICATE_ID_LOCK:
        existing = _CERTIFICATE_ID_AUTHORITIES.get(key)
        if existing is not None:
            existing_ref, existing_record = existing
            if (
                existing_ref == certificate_ref
                and outcome_certificate_is_authoritative(existing_record)
            ):
                assert type(existing_record) is OutcomeCertificate
                return existing_record
            raise GovernanceError(
                "outcome certificate id is already bound to a different body"
            )
        object.__setattr__(
            certificate,
            "_issuance",
            (_OUTCOME_CERTIFICATE_ISSUANCE, certificate_ref),
        )
        _CERTIFICATE_ID_AUTHORITIES[key] = (certificate_ref, certificate)
        return certificate


def _stable_commit_leaves(
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
    output_fingerprint: str,
    current_step: int,
) -> dict[str, object]:
    if not commit_evaluation_context_is_authoritative(context):
        raise GovernanceError("local receipt requires authoritative context")
    if not commit_assessment_is_authoritative(assessment):
        raise GovernanceError("local receipt requires authoritative assessment")
    if not commit_window_state_is_authoritative(window_state):
        raise GovernanceError("local receipt requires authoritative window state")
    if not commit_window_state_is_current(window_state):
        raise GovernanceError("local receipt requires the current window head")
    if not commit_window_ready(window_state):
        raise GovernanceError("local receipt requires a stable ready window")
    _validate_policy_binding(
        commit_policy,
        profile=context.profile,
        assurance=context.assurance,
        target=context.target,
        commit_policy_root=context.commit_policy_root,
    )
    if context.assurance is CommitAssurance.ADVISORY:
        raise GovernanceError("advisory assurance cannot issue a local commit receipt")
    if not commit_threshold_snapshot_matches(
        threshold_snapshot,
        assessment=risk_assessment,
        chain_state=risk_chain_state,
        commit_policy=commit_policy,
        current_step=current_step,
    ):
        raise GovernanceError(
            "local receipt risk assessment or threshold head is stale"
        )
    if not eligible_principal_snapshot_matches(
        membership_snapshot,
        epoch_state=membership_epoch_state,
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id,
        target=context.target,
        epoch=context.epoch,
        current_step=current_step,
    ):
        raise GovernanceError("local receipt membership head is stale")
    if not commit_replay_state_matches(
        replay_state,
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id,
        current_step=current_step,
    ):
        raise GovernanceError("local receipt commit replay head is stale")
    if not (
        type(support_replay_state) is SupportLeaseReplayState
        and support_lease_replay_state_is_current(support_replay_state)
        and support_replay_state.profile == context.profile
        and support_replay_state.protocol_id == context.protocol_id
        and support_replay_state.last_issued_at_step <= current_step
    ):
        raise GovernanceError("local receipt support replay head is stale")
    current_head_fingerprints = {
        "risk_chain_state_fingerprint": risk_assessment_chain_state_fingerprint(
            risk_chain_state
        ),
        "risk_assessment_fingerprint": risk_assessment_fingerprint(
            risk_assessment
        ),
        "threshold_fingerprint": commit_threshold_snapshot_fingerprint(
            threshold_snapshot
        ),
        "membership_snapshot_fingerprint": eligible_principal_snapshot_fingerprint(
            membership_snapshot
        ),
        "membership_epoch_state_fingerprint": (
            eligible_membership_epoch_state_fingerprint(membership_epoch_state)
        ),
        "replay_state_fingerprint": commit_replay_state_fingerprint(
            replay_state
        ),
        "support_replay_state_fingerprint": (
            support_lease_replay_state_fingerprint(support_replay_state)
        ),
    }
    for name, observed in current_head_fingerprints.items():
        if getattr(context, name) != observed or getattr(assessment, name) != observed:
            raise GovernanceError(f"local receipt current {name} lineage mismatch")
    if (
        context.replay_receipt_root != replay_state.receipt_root
        or assessment.replay_receipt_root != replay_state.receipt_root
        or context.support_replay_root != support_replay_state.replay_root
        or assessment.support_replay_root != support_replay_state.replay_root
    ):
        raise GovernanceError("local receipt current replay roots mismatch")
    common = (
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
    )
    for name in common:
        expected = getattr(context, name)
        if getattr(assessment, name) != expected or getattr(window_state, name) != expected:
            raise GovernanceError(f"local receipt {name} lineage mismatch")
    for window_name, assessment_name in (
        ("risk_chain_state_root", "risk_chain_state_fingerprint"),
        ("risk_assessment_root", "risk_assessment_fingerprint"),
        ("risk_policy_root", "risk_policy_root"),
        ("membership_snapshot_root", "membership_snapshot_fingerprint"),
        ("membership_epoch_state_root", "membership_epoch_state_fingerprint"),
        ("membership_root", "membership_root"),
        ("threshold_root", "threshold_fingerprint"),
        ("support_replay_state_root", "support_replay_state_fingerprint"),
        ("support_replay_root", "support_replay_root"),
        ("collective_evidence_root", "collective_evidence_root"),
        ("collective_challenge_root", "collective_challenge_root"),
        ("collective_lease_root", "collective_lease_root"),
        ("stop_resolution_root", "stop_resolution_fingerprint"),
        ("permission_root", "permission_fingerprint"),
    ):
        if getattr(window_state, window_name) != getattr(
            assessment,
            assessment_name,
        ):
            raise GovernanceError(
                f"local receipt window {window_name} lineage mismatch"
            )
    context_ref = commit_evaluation_context_fingerprint(context)
    assessment_ref = commit_assessment_fingerprint(assessment)
    if assessment.context_fingerprint != context_ref:
        raise GovernanceError("local receipt assessment/context lineage mismatch")
    if assessment.status is not CommitAssessmentStatus.READY:
        raise GovernanceError("local receipt assessment is not READY")
    if not (
        assessment.unique_leader
        and assessment.leader_ready_for_stability
        and assessment.leader_candidate_id
    ):
        raise GovernanceError("local receipt has no declared ready leader")
    if (
        assessment.blocker_references
        or assessment.equivocation_finding_ids
        or assessment.replay_conflict_references
    ):
        raise GovernanceError("local receipt cannot contain a safety finding")
    if (
        window_state.last_assessment_ref != assessment_ref
        or window_state.last_context_ref != context_ref
        or window_state.leader_candidate_id != assessment.leader_candidate_id
        or window_state.last_assessment_status != CommitAssessmentStatus.READY.value
        or window_state.last_evaluated_step != current_step
    ):
        raise GovernanceError("local receipt does not bind the stable window head")
    claim = next(
        (
            item
            for item in context.candidate_claims
            if item.candidate_id == assessment.leader_candidate_id
        ),
        None,
    )
    if claim is None or claim.safe_fallback:
        raise GovernanceError("local receipt leader is not a substantive declaration")
    metrics = next(
        (
            item
            for item in assessment.candidate_metrics
            if item.candidate_id == assessment.leader_candidate_id
        ),
        None,
    )
    if (
        metrics is None
        or not metrics.ready_for_stability
        or metrics.claim_fingerprint != claim.claim_fingerprint
    ):
        raise GovernanceError("local receipt leader metrics are not commit-ready")
    if (
        window_state.candidate_evidence_root != metrics.evidence_root
        or window_state.candidate_challenge_root != metrics.challenge_root
        or window_state.candidate_lease_root != metrics.lease_root
    ):
        raise GovernanceError("local receipt leader metric roots mismatch")
    output_ref = require_commit_fingerprint(
        output_fingerprint,
        "local receipt output_payload_fingerprint",
    )
    return {
        "profile": context.profile,
        "assurance": context.assurance,
        "manifest_root": context.manifest_root,
        "commit_policy_root": context.commit_policy_root,
        "protocol_id": context.protocol_id,
        "run_id": context.run_id,
        "target": context.target,
        "epoch": context.epoch,
        "candidate_id": assessment.leader_candidate_id,
        "claim_fingerprint": claim.claim_fingerprint,
        "output_payload_fingerprint": output_ref,
        "risk_chain_state_root": assessment.risk_chain_state_fingerprint,
        "risk_assessment_root": assessment.risk_assessment_fingerprint,
        "risk_policy_root": assessment.risk_policy_root,
        "membership_snapshot_root": assessment.membership_snapshot_fingerprint,
        "membership_epoch_state_root": assessment.membership_epoch_state_fingerprint,
        "membership_root": assessment.membership_root,
        "threshold_root": assessment.threshold_fingerprint,
        "replay_state_root": assessment.replay_state_fingerprint,
        "replay_root": assessment.replay_receipt_root,
        "support_replay_state_root": assessment.support_replay_state_fingerprint,
        "support_replay_root": assessment.support_replay_root,
        "candidate_evidence_root": metrics.evidence_root,
        "candidate_challenge_root": metrics.challenge_root,
        "candidate_lease_root": metrics.lease_root,
        "evidence_root": assessment.collective_evidence_root,
        "challenge_root": assessment.collective_challenge_root,
        "lease_root": assessment.collective_lease_root,
        "window_state_root": commit_window_state_fingerprint(window_state),
        "window_root": window_state.window_root,
        "stop_resolution_root": assessment.stop_resolution_fingerprint,
        "permission_root": assessment.permission_fingerprint,
        "context_root": context_ref,
        "assessment_root": assessment_ref,
    }


def _current_authority_heads_match_receipt(
    receipt: LocalCommitReceipt,
    *,
    context: CommitEvaluationContext,
    assessment: CommitAssessment,
    window_state: CommitWindowState,
    commit_policy: CollectiveCommitPolicy,
    risk_chain_state: RiskAssessmentChainState,
    risk_assessment: RiskAssessment,
    threshold_snapshot: CommitThresholdSnapshot,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    replay_state: CommitReplayState,
    support_replay_state: SupportLeaseReplayState,
    current_step: int,
) -> bool:
    """Recheck mutable heads while preserving the sealed commit proof."""

    try:
        current = require_commit_step(current_step, "portable finality current_step")
        if current < receipt.issued_at_step:
            return False
        if not (
            commit_evaluation_context_is_authoritative(context)
            and commit_assessment_is_authoritative(assessment)
            and commit_window_state_is_authoritative(window_state)
        ):
            return False
        if not commit_threshold_snapshot_matches(
            threshold_snapshot,
            assessment=risk_assessment,
            chain_state=risk_chain_state,
            commit_policy=commit_policy,
            current_step=current,
        ):
            return False
        if not eligible_principal_snapshot_matches(
            membership_snapshot,
            epoch_state=membership_epoch_state,
            profile=receipt.profile,
            assurance=receipt.assurance,
            manifest_root=receipt.manifest_root,
            commit_policy_root=receipt.commit_policy_root,
            protocol_id=receipt.protocol_id,
            run_id=receipt.run_id,
            target=receipt.target,
            epoch=receipt.epoch,
            current_step=current,
        ):
            return False
        if not commit_replay_state_matches(
            replay_state,
            profile=receipt.profile,
            assurance=receipt.assurance,
            manifest_root=receipt.manifest_root,
            commit_policy_root=receipt.commit_policy_root,
            protocol_id=receipt.protocol_id,
            run_id=receipt.run_id,
            current_step=current,
        ):
            return False
        if not (
            support_lease_replay_state_is_current(support_replay_state)
            and support_replay_state.profile == receipt.profile
            and support_replay_state.protocol_id == receipt.protocol_id
            and support_replay_state.last_issued_at_step <= current
            and commit_window_state_is_current(window_state)
            and commit_window_state_fingerprint(window_state)
            == receipt.window_state_root
            and window_state.window_root == receipt.window_root
            and window_state.leader_candidate_id == receipt.candidate_id
            and window_state.last_assessment_ref == receipt.assessment_root
            and commit_evaluation_context_fingerprint(context)
            == receipt.context_root
            and commit_assessment_fingerprint(assessment)
            == receipt.assessment_root
        ):
            return False
        current_roots = {
            "risk_chain_state_root": risk_assessment_chain_state_fingerprint(
                risk_chain_state
            ),
            "risk_assessment_root": risk_assessment_fingerprint(risk_assessment),
            "threshold_root": commit_threshold_snapshot_fingerprint(
                threshold_snapshot
            ),
            "membership_snapshot_root": eligible_principal_snapshot_fingerprint(
                membership_snapshot
            ),
            "membership_epoch_state_root": (
                eligible_membership_epoch_state_fingerprint(
                    membership_epoch_state
                )
            ),
            "membership_root": membership_snapshot.membership_root,
            "replay_state_root": commit_replay_state_fingerprint(replay_state),
            "replay_root": replay_state.receipt_root,
            "support_replay_state_root": (
                support_lease_replay_state_fingerprint(support_replay_state)
            ),
            "support_replay_root": support_replay_state.replay_root,
        }
        return all(
            getattr(receipt, name) == value for name, value in current_roots.items()
        )
    except (AttributeError, GovernanceError, TypeError, ValueError):
        return False


def _evidence_certificate_body_from_receipt(
    receipt: LocalCommitReceipt,
    *,
    certificate_id: str,
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> dict[str, object]:
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
    payload = local_commit_receipt_payload(receipt)
    for name in (
        "schema_discriminator",
        "receipt_version",
        "receipt_id",
        "authority_scope",
        "issuer_id",
        "authority",
        "issued_at_step",
        "provenance",
        "trace_event_id",
    ):
        payload.pop(name)
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


def _outcome_certificate_body(
    outcome: DecisionOutcome,
    window_state: CommitWindowState,
    *,
    commit_policy: CollectiveCommitPolicy,
    output_fingerprint: str,
    certificate_id: str,
    context: CommitEvaluationContext | None,
    assessment: CommitAssessment | None,
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> dict[str, object]:
    if not decision_outcome_is_authoritative(outcome):
        raise GovernanceError("outcome certificate requires authoritative outcome")
    if not commit_window_state_is_authoritative(window_state):
        raise GovernanceError("outcome certificate requires authoritative window state")
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("outcome certificate issuer lacks governance authority")
    _validate_policy_binding(
        commit_policy,
        profile=outcome.profile,
        assurance=outcome.assurance,
        target=outcome.target,
        commit_policy_root=outcome.commit_policy_root,
    )
    window_ref = commit_window_state_fingerprint(window_state)
    for name in (
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
    ):
        if getattr(window_state, name) != getattr(outcome, name):
            raise GovernanceError(f"outcome certificate window {name} mismatch")
    if (
        outcome.window_state_ref != window_ref
        or outcome.window_root != window_state.window_root
        or outcome.risk_assessment_root != window_state.risk_assessment_root
        or outcome.membership_root != window_state.membership_root
        or outcome.threshold_root != window_state.threshold_root
    ):
        raise GovernanceError("outcome certificate window lineage mismatch")
    for name in (
        "risk_chain_state_root",
        "risk_policy_root",
        "membership_snapshot_root",
        "membership_epoch_state_root",
        "support_replay_state_root",
        "support_replay_root",
        "collective_evidence_root",
        "collective_challenge_root",
        "collective_lease_root",
        "candidate_evidence_root",
        "candidate_challenge_root",
        "candidate_lease_root",
        "stop_resolution_root",
        "permission_root",
    ):
        if getattr(outcome, name) != getattr(window_state, name):
            raise GovernanceError(
                f"outcome certificate window {name} lineage mismatch"
            )

    context_root = ""
    claim_fingerprint = ""
    if context is not None:
        if not commit_evaluation_context_is_authoritative(context):
            raise GovernanceError("outcome certificate context is not authoritative")
        context_root = commit_evaluation_context_fingerprint(context)
        if outcome.context_ref and context_root != outcome.context_ref:
            raise GovernanceError("outcome certificate context ref mismatch")
        _require_same_scope(outcome, context, "outcome certificate context")
        if outcome.candidate_id:
            claim = next(
                (
                    item
                    for item in context.candidate_claims
                    if item.candidate_id == outcome.candidate_id
                ),
                None,
            )
            if claim is None:
                raise GovernanceError("outcome certificate candidate is undeclared")
            claim_fingerprint = claim.claim_fingerprint
    elif outcome.candidate_id:
        raise GovernanceError("candidate outcome requires claim-bound context")

    assessment_root = ""
    evidence_root = ""
    challenge_root = ""
    lease_root = ""
    stop_root = ""
    permission_root = ""
    if outcome.assessment_ref:
        if not commit_assessment_is_authoritative(assessment):
            raise GovernanceError("outcome certificate assessment is not authoritative")
        assert assessment is not None
        assessment_root = commit_assessment_fingerprint(assessment)
        if assessment_root != outcome.assessment_ref:
            raise GovernanceError("outcome certificate assessment ref mismatch")
        _require_same_scope(outcome, assessment, "outcome certificate assessment")
        if assessment.context_fingerprint != outcome.context_ref:
            raise GovernanceError("outcome certificate assessment context mismatch")
        for outcome_name, assessment_name in (
            ("risk_chain_state_root", "risk_chain_state_fingerprint"),
            ("risk_assessment_root", "risk_assessment_fingerprint"),
            ("risk_policy_root", "risk_policy_root"),
            ("membership_snapshot_root", "membership_snapshot_fingerprint"),
            ("membership_epoch_state_root", "membership_epoch_state_fingerprint"),
            ("membership_root", "membership_root"),
            ("threshold_root", "threshold_fingerprint"),
            ("replay_state_ref", "replay_state_fingerprint"),
            ("replay_root", "replay_receipt_root"),
            ("support_replay_state_root", "support_replay_state_fingerprint"),
            ("support_replay_root", "support_replay_root"),
            ("collective_evidence_root", "collective_evidence_root"),
            ("collective_challenge_root", "collective_challenge_root"),
            ("collective_lease_root", "collective_lease_root"),
            ("stop_resolution_root", "stop_resolution_fingerprint"),
            ("permission_root", "permission_fingerprint"),
        ):
            if getattr(outcome, outcome_name) != getattr(
                assessment,
                assessment_name,
            ):
                raise GovernanceError(
                    f"outcome certificate {outcome_name} assessment mismatch"
                )
        evidence_root = assessment.collective_evidence_root
        challenge_root = assessment.collective_challenge_root
        lease_root = assessment.collective_lease_root
        stop_root = assessment.stop_resolution_fingerprint
        permission_root = assessment.permission_fingerprint
    elif assessment is not None:
        raise GovernanceError("outcome certificate received unbound assessment")

    return {
        "schema_discriminator": OUTCOME_CERTIFICATE_DISCRIMINATOR,
        "certificate_version": OUTCOME_CERTIFICATE_VERSION,
        "wire_version": commit_policy.certificate.wire_version,
        "canonicalization": commit_policy.certificate.canonicalization,
        "hash_algorithm": commit_policy.certificate.hash_algorithm,
        "certificate_id": require_commit_text(
            certificate_id,
            "outcome certificate certificate_id",
        ),
        "outcome_kind": outcome.kind,
        "outcome_ref": decision_outcome_fingerprint(outcome),
        "profile": outcome.profile,
        "assurance": outcome.assurance,
        "authority_scope": outcome.authority_scope,
        "authoritative_commit": outcome.authoritative_commit,
        "epistemically_committed": outcome.epistemically_committed,
        "manifest_root": outcome.manifest_root,
        "commit_policy_root": outcome.commit_policy_root,
        "protocol_id": outcome.protocol_id,
        "run_id": outcome.run_id,
        "target": outcome.target,
        "epoch": outcome.epoch,
        "candidate_id": outcome.candidate_id,
        "claim_fingerprint": claim_fingerprint,
        "output_payload_fingerprint": require_commit_fingerprint(
            output_fingerprint,
            "outcome certificate output_payload_fingerprint",
        ),
        "risk_assessment_root": outcome.risk_assessment_root,
        "risk_chain_state_root": outcome.risk_chain_state_root,
        "risk_policy_root": outcome.risk_policy_root,
        "membership_snapshot_root": outcome.membership_snapshot_root,
        "membership_epoch_state_root": outcome.membership_epoch_state_root,
        "membership_root": outcome.membership_root,
        "threshold_root": outcome.threshold_root,
        "replay_state_root": outcome.replay_state_ref,
        "replay_root": outcome.replay_root,
        "support_replay_state_root": outcome.support_replay_state_root,
        "support_replay_root": outcome.support_replay_root,
        "evidence_root": outcome.collective_evidence_root,
        "challenge_root": outcome.collective_challenge_root,
        "lease_root": outcome.collective_lease_root,
        "candidate_evidence_root": outcome.candidate_evidence_root,
        "candidate_challenge_root": outcome.candidate_challenge_root,
        "candidate_lease_root": outcome.candidate_lease_root,
        "window_state_root": window_ref,
        "window_root": outcome.window_root,
        "stop_resolution_root": stop_root,
        "permission_root": permission_root,
        "context_root": context_root,
        "assessment_root": assessment_root,
        "commit_certificate_ref": outcome.certificate_ref,
        "issuer_id": require_commit_text(
            issuer_id,
            "outcome certificate issuer_id",
        ),
        "authority": authority,
        "issued_at_step": _require_outcome_certificate_issue_step(
            issued_at_step,
            outcome=outcome,
        ),
        "provenance": require_commit_text(
            provenance,
            "outcome certificate provenance",
        ),
        "trace_event_id": require_commit_text(
            trace_event_id,
            "outcome certificate trace_event_id",
        ),
    }


def _validate_local_commit_receipt(receipt: LocalCommitReceipt) -> None:
    _validate_certificate_header(
        discriminator=receipt.schema_discriminator,
        expected_discriminator=LOCAL_COMMIT_RECEIPT_DISCRIMINATOR,
        version=receipt.receipt_version,
        expected_version=LOCAL_COMMIT_RECEIPT_VERSION,
        wire_version=receipt.wire_version,
        canonicalization=receipt.canonicalization,
        hash_algorithm=receipt.hash_algorithm,
        profile=receipt.profile,
        assurance=receipt.assurance,
    )
    if receipt.authority_scope is not AuthorityScope.GOVERNANCE_LOCAL:
        raise GovernanceError("local receipt must use governance-local authority")
    require_commit_text(receipt.receipt_id, "local receipt receipt_id")
    _validate_commit_lineage(receipt, field_name="local receipt", complete=True)
    _validate_issuer_metadata(receipt, field_name="local receipt")


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


def _validate_certificate_header(
    *,
    discriminator: object,
    expected_discriminator: str,
    version: object,
    expected_version: str,
    wire_version: object,
    canonicalization: object,
    hash_algorithm: object,
    profile: object,
    assurance: object,
) -> None:
    if discriminator != expected_discriminator:
        raise GovernanceError("certificate schema discriminator is invalid")
    if version != expected_version:
        raise GovernanceError("certificate version is unsupported")
    if wire_version != COMMIT_WIRE_VERSION:
        raise GovernanceError("certificate wire version is unsupported")
    if canonicalization != COMMIT_CANONICAL_VERSION:
        raise GovernanceError("certificate canonicalization is unsupported")
    if hash_algorithm != CERTIFICATE_HASH_ALGORITHM:
        raise GovernanceError("certificate hash algorithm is unsupported")
    normalized_profile = require_commit_profile(profile, "certificate profile")
    normalized_assurance = require_commit_assurance(
        assurance,
        "certificate assurance",
    )
    if normalized_profile not in COMMIT_PROFILES_BY_ASSURANCE[
        normalized_assurance.value
    ]:
        raise GovernanceError("certificate profile/assurance mismatch")


def _validate_commit_lineage(
    value: object,
    *,
    field_name: str,
    complete: bool,
) -> None:
    for name in ("protocol_id", "run_id", "target", "candidate_id"):
        require_commit_text(getattr(value, name), f"{field_name} {name}")
    require_commit_step(getattr(value, "epoch"), f"{field_name} epoch")
    for name in (
        "manifest_root",
        "commit_policy_root",
        "claim_fingerprint",
        "output_payload_fingerprint",
        "risk_chain_state_root",
        "risk_assessment_root",
        "risk_policy_root",
        "membership_snapshot_root",
        "membership_epoch_state_root",
        "membership_root",
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
    ):
        raw = getattr(value, name)
        if complete or raw:
            require_commit_fingerprint(raw, f"{field_name} {name}")


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


def _validate_issuer_metadata(value: object, *, field_name: str) -> None:
    require_commit_text(getattr(value, "issuer_id"), f"{field_name} issuer_id")
    authority = getattr(value, "authority")
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError(f"{field_name} authority is invalid")
    require_commit_step(getattr(value, "issued_at_step"), f"{field_name} issued_at_step")
    require_commit_text(getattr(value, "provenance"), f"{field_name} provenance")
    require_commit_text(getattr(value, "trace_event_id"), f"{field_name} trace_event_id")


def _require_outcome_certificate_issue_step(
    value: object,
    *,
    outcome: DecisionOutcome,
) -> int:
    issued = require_commit_step(value, "outcome certificate issued_at_step")
    if issued < outcome.current_step:
        raise GovernanceError("outcome certificate cannot predate its outcome")
    return issued


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


def _validate_policy_binding(
    policy: CollectiveCommitPolicy,
    *,
    profile: str,
    assurance: CommitAssurance,
    target: str,
    commit_policy_root: str,
) -> None:
    if type(policy) is not CollectiveCommitPolicy:
        raise GovernanceError("certificate requires canonical commit policy")
    if policy.assurance != assurance.value or policy.target != target:
        raise GovernanceError("certificate policy scope mismatch")
    if commit_policy_fingerprint(policy, profile=profile) != commit_policy_root:
        raise GovernanceError("certificate policy root mismatch")
    certificate = policy.certificate
    if (
        certificate.wire_version != COMMIT_WIRE_VERSION
        or certificate.canonicalization != COMMIT_CANONICAL_VERSION
        or certificate.hash_algorithm != CERTIFICATE_HASH_ALGORITHM
    ):
        raise GovernanceError("certificate policy uses unsupported wire semantics")


def _require_same_scope(left: object, right: object, field_name: str) -> None:
    for name in (
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
    ):
        if getattr(left, name) != getattr(right, name):
            raise GovernanceError(f"{field_name} {name} mismatch")


def _certificate_body_root(
    body: Mapping[str, object],
    *,
    schema: str,
    profile: str,
) -> str:
    return commit_payload_fingerprint(body, schema=schema, profile=profile)


def _certificate_envelope_root(
    body_root: str,
    issuer_attestation_refs: Sequence[str],
    *,
    schema: str,
    profile: str,
) -> str:
    return commit_payload_fingerprint(
        {
            "certificate_body_root": require_commit_fingerprint(
                body_root,
                "certificate body root",
            ),
            "issuer_attestation_refs": require_commit_labels(
                issuer_attestation_refs,
                "certificate issuer_attestation_refs",
                allow_empty=True,
            ),
        },
        schema=schema,
        profile=profile,
    )


def _require_attestation_bindings(
    issuer_attestation_refs: Sequence[str],
    trusted_issuer_attestations: Mapping[str, str] | None,
    *,
    body_root: str,
    field_name: str,
) -> tuple[str, ...]:
    refs = require_commit_labels(
        issuer_attestation_refs,
        f"{field_name} issuer_attestation_refs",
    )
    if not _attestations_match(
        refs,
        trusted_issuer_attestations,
        body_root=body_root,
    ):
        raise GovernanceError(
            f"{field_name} issuer attestations do not bind the certificate body"
        )
    return refs


def _attestations_match(
    issuer_attestation_refs: Sequence[str],
    trusted_issuer_attestations: Mapping[str, str] | None,
    *,
    body_root: str,
) -> bool:
    try:
        refs = require_commit_labels(
            issuer_attestation_refs,
            "certificate issuer_attestation_refs",
        )
        expected_root = require_commit_fingerprint(body_root, "certificate body root")
        if not isinstance(trusted_issuer_attestations, Mapping):
            return False
        return all(
            require_commit_fingerprint(
                trusted_issuer_attestations[ref],
                "trusted issuer attestation body root",
            )
            == expected_root
            for ref in refs
        )
    except (KeyError, GovernanceError, TypeError):
        return False


def _dataclass_public_payload(value: object) -> dict[str, object]:
    return {
        name: getattr(value, name)
        for name, record in value.__dataclass_fields__.items()  # type: ignore[attr-defined]
        if record.init
    }


def _strict_payload_values(
    payload: Mapping[str, object],
    record_type: type,
    *,
    field_name: str,
) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise GovernanceError(f"{field_name} must be a mapping")
    expected = {
        name
        for name, record in record_type.__dataclass_fields__.items()
        if record.init
    }
    observed = set(payload)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise GovernanceError(
            f"{field_name} keys mismatch; missing={missing}, extra={extra}"
        )
    if any(type(name) is not str for name in payload):
        raise GovernanceError(f"{field_name} keys must be strings")
    return dict(payload)


def _require_sequence(value: object, field_name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        raise GovernanceError(f"{field_name} must be a sequence")
    return value


def _coerce_assurance(value: object) -> CommitAssurance:
    try:
        return value if type(value) is CommitAssurance else CommitAssurance(value)
    except (TypeError, ValueError) as exc:
        raise GovernanceError("certificate assurance is invalid") from exc


def _coerce_authority_scope(value: object) -> AuthorityScope:
    try:
        return value if type(value) is AuthorityScope else AuthorityScope(value)
    except (TypeError, ValueError) as exc:
        raise GovernanceError("certificate authority scope is invalid") from exc


def _coerce_outcome_kind(value: object) -> DecisionOutcomeKind:
    try:
        return (
            value
            if type(value) is DecisionOutcomeKind
            else DecisionOutcomeKind(value)
        )
    except (TypeError, ValueError) as exc:
        raise GovernanceError("outcome certificate kind is invalid") from exc


def _coerce_authority(value: object) -> AuthorityLevel:
    try:
        return value if type(value) is AuthorityLevel else AuthorityLevel(value)
    except (TypeError, ValueError) as exc:
        raise GovernanceError("certificate authority is invalid") from exc


__all__ = [
    "CERTIFICATE_HASH_ALGORITHM",
    "EVIDENCE_COMMIT_CERTIFICATE_DISCRIMINATOR",
    "EVIDENCE_COMMIT_CERTIFICATE_VERSION",
    "LOCAL_COMMIT_RECEIPT_DISCRIMINATOR",
    "LOCAL_COMMIT_RECEIPT_VERSION",
    "OUTCOME_CERTIFICATE_DISCRIMINATOR",
    "OUTCOME_CERTIFICATE_VERSION",
    "EvidenceCommitCertificate",
    "LocalCommitReceipt",
    "OutcomeCertificate",
    "evidence_commit_certificate_body_root",
    "evidence_commit_certificate_fingerprint",
    "evidence_commit_certificate_from_payload",
    "evidence_commit_certificate_payload",
    "issue_evidence_commit_certificate",
    "issue_local_commit_receipt",
    "issue_outcome_certificate",
    "local_commit_receipt_fingerprint",
    "local_commit_receipt_is_authoritative",
    "local_commit_receipt_matches",
    "local_commit_receipt_payload",
    "outcome_certificate_body_root",
    "outcome_certificate_fingerprint",
    "outcome_certificate_from_payload",
    "outcome_certificate_is_authoritative",
    "outcome_certificate_payload",
    "output_payload_fingerprint",
    "verify_evidence_commit_certificate",
    "verify_evidence_commit_finality",
    "verify_local_commit_finality",
    "verify_outcome_certificate",
]
