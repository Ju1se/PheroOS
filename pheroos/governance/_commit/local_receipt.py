from __future__ import annotations

from dataclasses import dataclass, field

from pheroos.governance._commit.certificate_contracts import (
    LEGACY_CERTIFICATE_IDENTITIES,
    LOCAL_COMMIT_RECEIPT_DISCRIMINATOR,
    LOCAL_COMMIT_RECEIPT_VERSION,
    certificate_identity_key,
    validate_certificate_header,
    validate_commit_lineage,
    validate_issuer_metadata,
)
from pheroos.governance._commit.common import AuthorityScope
from pheroos.governance._commit_validation import require_commit_text
from pheroos.governance._process_state import PROCESS_STATE
from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import CommitAssurance


_LOCAL_COMMIT_RECEIPT_ISSUANCE = object()


@dataclass(frozen=True)
class LocalCommitReceipt:
    """Governance-local evidence-bound proof of a stable central commit."""

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
        validate_local_commit_receipt(self)


def local_commit_receipt_payload(
    receipt: LocalCommitReceipt,
) -> dict[str, object]:
    if type(receipt) is not LocalCommitReceipt:
        raise GovernanceError("local commit receipt must use the canonical record")
    validate_local_commit_receipt(receipt)
    return {
        name: getattr(receipt, name)
        for name in receipt.__dataclass_fields__
        if not name.startswith("_")
    }


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
        key = certificate_identity_key(
            receipt,
            discriminator=LOCAL_COMMIT_RECEIPT_DISCRIMINATOR,
            record_id=receipt.receipt_id,
        )
        registered = PROCESS_STATE.get(
            LEGACY_CERTIFICATE_IDENTITIES,
            key,
        )
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


def bind_local_commit_receipt_authority(
    receipt: LocalCommitReceipt,
    *,
    receipt_ref: str,
) -> LocalCommitReceipt:
    key = certificate_identity_key(
        receipt,
        discriminator=LOCAL_COMMIT_RECEIPT_DISCRIMINATOR,
        record_id=receipt.receipt_id,
    )
    with PROCESS_STATE.transaction() as registry:
        existing = registry.get(LEGACY_CERTIFICATE_IDENTITIES, key)
        if existing is not None:
            existing_ref, existing_record = existing
            if existing_ref == receipt_ref and local_commit_receipt_is_authoritative(
                existing_record
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
        registry.set(
            LEGACY_CERTIFICATE_IDENTITIES,
            key,
            (receipt_ref, receipt),
        )
        return receipt


def validate_local_commit_receipt(receipt: LocalCommitReceipt) -> None:
    validate_certificate_header(
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
    validate_commit_lineage(receipt, field_name="local receipt", complete=True)
    validate_issuer_metadata(receipt, field_name="local receipt")


_PUBLIC_MODULE = "pheroos.governance.certificate"
LocalCommitReceipt.__module__ = _PUBLIC_MODULE
for _public_function in (
    local_commit_receipt_fingerprint,
    local_commit_receipt_is_authoritative,
    local_commit_receipt_payload,
):
    _public_function.__module__ = _PUBLIC_MODULE


__all__ = [
    "LocalCommitReceipt",
    "local_commit_receipt_fingerprint",
    "local_commit_receipt_is_authoritative",
    "local_commit_receipt_payload",
    "bind_local_commit_receipt_authority",
    "validate_local_commit_receipt",
]
