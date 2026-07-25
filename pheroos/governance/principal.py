from __future__ import annotations

from dataclasses import dataclass, field

from pheroos.governance._commit_validation import (
    require_commit_assurance,
    require_commit_fingerprint,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
    require_fresh_interval,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CommitAssurance,
)


_PRINCIPAL_VERIFICATION_ISSUANCE = object()


@dataclass(frozen=True)
class PrincipalAttestation:
    principal_id: str
    attestation_ref: str
    method: str
    issuer_id: str
    issued_at_step: int
    expires_at_step: int
    provenance: str
    nonce: str
    trace_event_id: str

    def __post_init__(self) -> None:
        _validate_principal_attestation(self)


@dataclass(frozen=True)
class PrincipalVerification:
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    principal_id: str
    cluster_id: str
    failure_domain: str
    attestation_fingerprint: str
    verified_issuer_id: str
    verified_method: str
    verifier_id: str
    authority: AuthorityLevel
    issued_at_step: int
    expires_at_step: int
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _validate_principal_verification_shape(self)


def principal_attestation_fingerprint(attestation: PrincipalAttestation) -> str:
    if type(attestation) is not PrincipalAttestation:
        raise GovernanceError("principal attestation must use the canonical record")
    _validate_principal_attestation(attestation)
    return commit_payload_fingerprint(
        principal_attestation_payload(attestation),
        schema="pheroos-principal-attestation-v1",
        profile="pheroos-commit-authority-v1",
    )


def principal_attestation_payload(
    attestation: PrincipalAttestation,
) -> dict[str, object]:
    if type(attestation) is not PrincipalAttestation:
        raise GovernanceError("principal attestation must use the canonical record")
    _validate_principal_attestation(attestation)
    return {
        "attestation_ref": attestation.attestation_ref,
        "expires_at_step": attestation.expires_at_step,
        "issued_at_step": attestation.issued_at_step,
        "issuer_id": attestation.issuer_id,
        "method": attestation.method,
        "nonce": attestation.nonce,
        "principal_id": attestation.principal_id,
        "provenance": attestation.provenance,
        "trace_event_id": attestation.trace_event_id,
    }


def verify_principal_attestation(
    attestation: PrincipalAttestation,
    *,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    cluster_id: str,
    failure_domain: str,
    verifier_id: str,
    authority: AuthorityLevel,
    current_step: int,
    provenance: str,
    trace_event_id: str,
) -> PrincipalVerification:
    if type(attestation) is not PrincipalAttestation:
        raise GovernanceError("principal attestation must use the canonical record")
    _validate_principal_attestation(attestation)
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("principal verification requires governance authority")
    require_fresh_interval(
        issued_at_step=attestation.issued_at_step,
        expires_at_step=attestation.expires_at_step,
        current_step=current_step,
        field_name="principal attestation",
    )
    verification = PrincipalVerification(
        profile=require_commit_profile(profile, "principal verification profile"),
        assurance=require_commit_assurance(
            assurance,
            "principal verification assurance",
        ),
        manifest_root=require_commit_fingerprint(
            manifest_root,
            "principal verification manifest_root",
        ),
        commit_policy_root=require_commit_fingerprint(
            commit_policy_root,
            "principal verification commit_policy_root",
        ),
        protocol_id=require_commit_text(
            protocol_id,
            "principal verification protocol_id",
        ),
        run_id=require_commit_text(run_id, "principal verification run_id"),
        target=require_commit_text(target, "principal verification target"),
        epoch=require_commit_step(epoch, "principal verification epoch"),
        principal_id=attestation.principal_id,
        cluster_id=require_commit_text(cluster_id, "principal cluster_id"),
        failure_domain=(
            require_commit_text(failure_domain, "principal failure_domain")
            if failure_domain
            else ""
        ),
        attestation_fingerprint=principal_attestation_fingerprint(attestation),
        verified_issuer_id=attestation.issuer_id,
        verified_method=attestation.method,
        verifier_id=require_commit_text(verifier_id, "principal verifier_id"),
        authority=authority,
        issued_at_step=require_commit_step(
            current_step,
            "principal verification issued_at_step",
        ),
        expires_at_step=attestation.expires_at_step,
        provenance=require_commit_text(provenance, "principal verification provenance"),
        trace_event_id=require_commit_text(
            trace_event_id,
            "principal verification trace_event_id",
        ),
    )
    object.__setattr__(
        verification,
        "_issuance",
        (
            _PRINCIPAL_VERIFICATION_ISSUANCE,
            _principal_verification_snapshot(verification),
        ),
    )
    return verification


def principal_verification_is_authoritative(verification: object) -> bool:
    if type(verification) is not PrincipalVerification:
        return False
    try:
        _validate_principal_verification_shape(verification)
        issuance = verification._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _PRINCIPAL_VERIFICATION_ISSUANCE
            and issuance[1] == _principal_verification_snapshot(verification)
        )
    except Exception:
        return False


def principal_verification_matches(
    verification: PrincipalVerification | None,
    *,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    principal_id: str,
    current_step: int,
    cluster_id: str | None = None,
) -> bool:
    try:
        expected_profile = require_commit_profile(profile, "expected profile")
        expected_assurance = require_commit_assurance(
            assurance,
            "expected assurance",
        )
        expected_manifest_root = require_commit_fingerprint(
            manifest_root,
            "expected manifest_root",
        )
        expected_policy_root = require_commit_fingerprint(
            commit_policy_root,
            "expected commit_policy_root",
        )
        expected_protocol = require_commit_text(protocol_id, "expected protocol_id")
        expected_run = require_commit_text(run_id, "expected run_id")
        expected_target = require_commit_text(target, "expected target")
        expected_epoch = require_commit_step(epoch, "expected epoch")
        expected_principal = require_commit_text(
            principal_id,
            "expected principal_id",
        )
        current = require_commit_step(
            current_step, "principal verification current_step"
        )
        expected_cluster = (
            require_commit_text(cluster_id, "expected cluster_id")
            if cluster_id is not None
            else None
        )
        return bool(
            principal_verification_is_authoritative(verification)
            and verification is not None
            and verification.profile == expected_profile
            and verification.assurance is expected_assurance
            and verification.manifest_root == expected_manifest_root
            and verification.commit_policy_root == expected_policy_root
            and verification.protocol_id == expected_protocol
            and verification.run_id == expected_run
            and verification.target == expected_target
            and verification.epoch == expected_epoch
            and verification.principal_id == expected_principal
            and (
                expected_cluster is None or verification.cluster_id == expected_cluster
            )
            and verification.issued_at_step <= current < verification.expires_at_step
        )
    except GovernanceError:
        return False


def _validate_principal_attestation(attestation: PrincipalAttestation) -> None:
    for field_name in (
        "principal_id",
        "attestation_ref",
        "method",
        "issuer_id",
        "provenance",
        "nonce",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(attestation, field_name),
            f"principal attestation {field_name}",
        )
    issued = require_commit_step(
        attestation.issued_at_step,
        "principal attestation issued_at_step",
    )
    expires = require_commit_step(
        attestation.expires_at_step,
        "principal attestation expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("principal attestation expiry must be after issuance")


def _validate_principal_verification_shape(
    verification: PrincipalVerification,
) -> None:
    for field_name in (
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "principal_id",
        "cluster_id",
        "attestation_fingerprint",
        "verified_issuer_id",
        "verified_method",
        "verifier_id",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(verification, field_name),
            f"principal verification {field_name}",
        )
    assurance = require_commit_assurance(
        verification.assurance,
        "principal verification assurance",
    )
    require_commit_profile(verification.profile, "principal verification profile")
    if verification.profile not in COMMIT_PROFILES_BY_ASSURANCE[assurance.value]:
        raise GovernanceError("principal verification profile/assurance mismatch")
    require_commit_fingerprint(
        verification.manifest_root,
        "principal verification manifest_root",
    )
    require_commit_fingerprint(
        verification.commit_policy_root,
        "principal verification commit_policy_root",
    )
    require_commit_fingerprint(
        verification.attestation_fingerprint,
        "principal verification attestation_fingerprint",
    )
    if verification.failure_domain:
        require_commit_text(
            verification.failure_domain,
            "principal verification failure_domain",
        )
    elif assurance is CommitAssurance.DISTRIBUTED:
        raise GovernanceError(
            "distributed principal verification requires a failure_domain"
        )
    require_commit_step(verification.epoch, "principal verification epoch")
    if type(verification.authority) is not AuthorityLevel or not can_verify(
        verification.authority
    ):
        raise GovernanceError("principal verification authority is invalid")
    issued = require_commit_step(
        verification.issued_at_step,
        "principal verification issued_at_step",
    )
    expires = require_commit_step(
        verification.expires_at_step,
        "principal verification expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("principal verification expiry must be after issuance")


def _principal_verification_snapshot(verification: PrincipalVerification) -> str:
    return commit_payload_fingerprint(
        principal_verification_payload(verification),
        schema="pheroos-principal-verification-v1",
        profile=verification.profile,
    )


def principal_verification_payload(
    verification: PrincipalVerification,
) -> dict[str, object]:
    if type(verification) is not PrincipalVerification:
        raise GovernanceError("principal verification must use the canonical record")
    _validate_principal_verification_shape(verification)
    return {
        "attestation_fingerprint": verification.attestation_fingerprint,
        "assurance": verification.assurance,
        "authority": verification.authority,
        "cluster_id": verification.cluster_id,
        "commit_policy_root": verification.commit_policy_root,
        "epoch": verification.epoch,
        "expires_at_step": verification.expires_at_step,
        "failure_domain": verification.failure_domain,
        "issued_at_step": verification.issued_at_step,
        "manifest_root": verification.manifest_root,
        "principal_id": verification.principal_id,
        "profile": verification.profile,
        "protocol_id": verification.protocol_id,
        "provenance": verification.provenance,
        "run_id": verification.run_id,
        "target": verification.target,
        "trace_event_id": verification.trace_event_id,
        "verified_issuer_id": verification.verified_issuer_id,
        "verified_method": verification.verified_method,
        "verifier_id": verification.verifier_id,
    }


def principal_verification_fingerprint(
    verification: PrincipalVerification,
) -> str:
    return _principal_verification_snapshot(verification)


__all__ = [
    "PrincipalAttestation",
    "PrincipalVerification",
    "principal_attestation_fingerprint",
    "principal_attestation_payload",
    "principal_verification_fingerprint",
    "principal_verification_is_authoritative",
    "principal_verification_matches",
    "principal_verification_payload",
    "verify_principal_attestation",
]
