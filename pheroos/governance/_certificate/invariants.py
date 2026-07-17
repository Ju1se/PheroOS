from __future__ import annotations

"""Shared, authority-neutral certificate invariants."""

from collections.abc import Mapping, Sequence
from typing import Any

from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance._commit.certificate_contracts import (
    CERTIFICATE_HASH_ALGORITHM,
)
from pheroos.governance._commit.local_receipt import LocalCommitReceipt
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.commit_state import (
    AuthorityScope,
    CommitFinalityStatus,
    CommitFinalityVerification,
    DecisionOutcomeKind,
    _issue_commit_finality_verification,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_WIRE_VERSION,
    CollectiveCommitPolicy,
    CommitAssurance,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint


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

def _issue_typed_finality_verification(
    certificate: LocalCommitReceipt | object,
    *,
    certificate_kind: str,
    certificate_ref: str,
    current_step: int,
    verifier_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
) -> CommitFinalityVerification:
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


__all__: list[str] = []
