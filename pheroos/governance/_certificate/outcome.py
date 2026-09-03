"""Typed terminal outcome certificate issuance and verification."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from pheroos.governance._certificate.invariants import (
    _attestations_match,
    _certificate_body_root,
    _certificate_envelope_root,
    _coerce_assurance,
    _coerce_authority,
    _coerce_authority_scope,
    _coerce_outcome_kind,
    _dataclass_public_payload,
    _require_attestation_bindings,
    _require_same_scope,
    _require_sequence,
    _strict_payload_values,
    _validate_policy_binding,
)
from pheroos.governance._certificate.records import (
    OUTCOME_CERTIFICATE_DISCRIMINATOR,
    OUTCOME_CERTIFICATE_VERSION,
    OutcomeCertificate,
    _validate_outcome_certificate,
)
from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance._commit.certificate_contracts import (
    LEGACY_CERTIFICATE_IDENTITIES as _LEGACY_CERTIFICATE_IDENTITIES,
    certificate_identity_key as _certificate_id_key,
)
from pheroos.governance._process_state import PROCESS_STATE
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit import (
    CommitAssessment,
    CommitEvaluationContext,
    commit_assessment_fingerprint,
    commit_assessment_is_authoritative,
    commit_evaluation_context_fingerprint,
    commit_evaluation_context_is_authoritative,
)
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.commit_state import (
    CommitWindowState,
    DecisionOutcome,
    commit_window_state_fingerprint,
    commit_window_state_is_authoritative,
    decision_outcome_fingerprint,
    decision_outcome_is_authoritative,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import CollectiveCommitPolicy


_OUTCOME_CERTIFICATE_ISSUANCE = object()


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
        **cast(Any, body),
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
        registered = PROCESS_STATE.get(
            _LEGACY_CERTIFICATE_IDENTITIES,
            key,
        )
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
    values["authority_scope"] = _coerce_authority_scope(values["authority_scope"])
    values["authority"] = _coerce_authority(values["authority"])
    values["issuer_attestation_refs"] = tuple(
        _require_sequence(values["issuer_attestation_refs"], "issuer attestations")
    )
    try:
        # This is the wire-decoder boundary: the strict field registry and the
        # enum/tuple coercions above have already narrowed every input value.
        return OutcomeCertificate(**cast(Any, values))
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(f"outcome certificate payload is invalid: {exc}") from exc


def verify_outcome_certificate(
    certificate_or_payload: OutcomeCertificate | Mapping[str, object],
    *,
    trusted_issuer_attestations: Mapping[str, str] | None = None,
    expected_certificate_ref: str = "",
    expected_output_payload_fingerprint: str = "",
) -> bool:
    try:
        if type(certificate_or_payload) is OutcomeCertificate:
            certificate = certificate_or_payload
        else:
            certificate = outcome_certificate_from_payload(
                cast(Mapping[str, object], certificate_or_payload)
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
    with PROCESS_STATE.transaction() as registry:
        existing = registry.get(_LEGACY_CERTIFICATE_IDENTITIES, key)
        if existing is not None:
            existing_ref, existing_record = existing
            if existing_ref == certificate_ref and outcome_certificate_is_authoritative(
                existing_record
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
        registry.set(
            _LEGACY_CERTIFICATE_IDENTITIES,
            key,
            (certificate_ref, certificate),
        )
        return certificate


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
    window_ref = _validate_outcome_certificate_window(outcome, window_state)
    context_root, claim_fingerprint = _outcome_certificate_context(outcome, context)
    assessment_root, stop_root, permission_root = _outcome_certificate_assessment(
        outcome,
        assessment,
    )

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


def _validate_outcome_certificate_window(
    outcome: DecisionOutcome,
    window_state: CommitWindowState,
) -> str:
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
            raise GovernanceError(f"outcome certificate window {name} lineage mismatch")
    return window_ref


def _outcome_certificate_context(
    outcome: DecisionOutcome,
    context: CommitEvaluationContext | None,
) -> tuple[str, str]:
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
    return context_root, claim_fingerprint


def _outcome_certificate_assessment(
    outcome: DecisionOutcome,
    assessment: CommitAssessment | None,
) -> tuple[str, str, str]:
    assessment_root = ""
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
        stop_root = assessment.stop_resolution_fingerprint
        permission_root = assessment.permission_fingerprint
    elif assessment is not None:
        raise GovernanceError("outcome certificate received unbound assessment")
    return assessment_root, stop_root, permission_root


def _require_outcome_certificate_issue_step(
    value: object,
    *,
    outcome: DecisionOutcome,
) -> int:
    issued = require_commit_step(value, "outcome certificate issued_at_step")
    if issued < outcome.current_step:
        raise GovernanceError("outcome certificate cannot predate its outcome")
    return issued


__all__ = [
    "OutcomeCertificate",
    "issue_outcome_certificate",
    "outcome_certificate_body_root",
    "outcome_certificate_fingerprint",
    "outcome_certificate_from_payload",
    "outcome_certificate_is_authoritative",
    "outcome_certificate_payload",
    "verify_outcome_certificate",
]
