from __future__ import annotations

from pheroos.governance._commit_validation import (
    require_commit_assurance,
    require_commit_fingerprint,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_PROFILES_BY_ASSURANCE,
    COMMIT_WIRE_VERSION,
)


CERTIFICATE_HASH_ALGORITHM = "sha256"
LOCAL_COMMIT_RECEIPT_DISCRIMINATOR = "local_commit_receipt"
LOCAL_COMMIT_RECEIPT_VERSION = "pheroos-local-commit-receipt-v1"
LEGACY_CERTIFICATE_IDENTITIES = "legacy.certificate.identities"


def certificate_identity_key(
    value: object,
    *,
    discriminator: str,
    record_id: str,
) -> tuple[str, str, str, str, str, int, str]:
    return (
        discriminator,
        getattr(value, "profile"),
        getattr(value, "protocol_id"),
        getattr(value, "run_id"),
        getattr(value, "target"),
        getattr(value, "epoch"),
        record_id,
    )


def validate_certificate_header(
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
    if (
        normalized_profile
        not in COMMIT_PROFILES_BY_ASSURANCE[normalized_assurance.value]
    ):
        raise GovernanceError("certificate profile/assurance mismatch")


def validate_commit_lineage(
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


def validate_issuer_metadata(value: object, *, field_name: str) -> None:
    require_commit_text(getattr(value, "issuer_id"), f"{field_name} issuer_id")
    authority = getattr(value, "authority")
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError(f"{field_name} authority is invalid")
    require_commit_step(
        getattr(value, "issued_at_step"),
        f"{field_name} issued_at_step",
    )
    require_commit_text(getattr(value, "provenance"), f"{field_name} provenance")
    require_commit_text(
        getattr(value, "trace_event_id"),
        f"{field_name} trace_event_id",
    )


__all__ = [
    "CERTIFICATE_HASH_ALGORITHM",
    "LEGACY_CERTIFICATE_IDENTITIES",
    "LOCAL_COMMIT_RECEIPT_DISCRIMINATOR",
    "LOCAL_COMMIT_RECEIPT_VERSION",
    "certificate_identity_key",
    "validate_certificate_header",
    "validate_commit_lineage",
    "validate_issuer_metadata",
]
