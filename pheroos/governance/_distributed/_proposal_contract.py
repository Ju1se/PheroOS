from __future__ import annotations

from collections.abc import Mapping

from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance._distributed.invariants import (
    _coerce_assurance,
    _public_dataclass_payload,
)
from pheroos.governance.certificate import (
    EVIDENCE_COMMIT_CERTIFICATE_VERSION,
    LOCAL_COMMIT_RECEIPT_VERSION,
    EvidenceCommitCertificate,
    LocalCommitReceipt,
    evidence_commit_certificate_fingerprint,
    local_commit_receipt_fingerprint,
)
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_WIRE_VERSION,
    DISTRIBUTED_COMMIT_PROFILE_VERSION,
    CommitAssurance,
)

_PROPOSAL_ROOT_FIELDS = (
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
    "threshold_root",
    "stop_resolution_root",
    "permission_root",
    "context_root",
    "assessment_root",
    "local_receipt_ref",
    "portable_certificate_ref",
    "commit_value_root",
    "proposal_digest",
)

_DISTRIBUTED_COMMIT_VALUE_FIELDS = (
    "wire_version",
    "canonicalization",
    "hash_algorithm",
    "profile",
    "assurance",
    "manifest_root",
    "commit_policy_root",
    "protocol_id",
    "run_id",
    "target",
    "epoch",
    "candidate_id",
    "claim_fingerprint",
    "output_payload_fingerprint",
    "risk_chain_state_root",
    "risk_assessment_root",
    "risk_policy_root",
    "membership_snapshot_root",
    "membership_epoch_state_root",
    "membership_root",
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
    "threshold_root",
    "stop_resolution_root",
    "permission_root",
    "context_root",
    "assessment_root",
    "local_receipt_version",
    "portable_certificate_version",
)

_CENTRAL_LINEAGE_FIELDS = (
    "profile",
    "assurance",
    "manifest_root",
    "commit_policy_root",
    "protocol_id",
    "run_id",
    "target",
    "epoch",
    "candidate_id",
    "claim_fingerprint",
    "output_payload_fingerprint",
    "risk_chain_state_root",
    "risk_assessment_root",
    "risk_policy_root",
    "membership_snapshot_root",
    "membership_epoch_state_root",
    "membership_root",
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
    "threshold_root",
    "stop_resolution_root",
    "permission_root",
    "context_root",
    "assessment_root",
)


def validate_distributed_commit_proposal(
    proposal: object,
    *,
    proposal_version: str,
    commit_value_version: str,
) -> None:
    if proposal.proposal_version != proposal_version:
        raise GovernanceError("distributed proposal version is unsupported")
    if proposal.wire_version != COMMIT_WIRE_VERSION:
        raise GovernanceError("distributed proposal wire version is unsupported")
    if proposal.canonicalization != COMMIT_CANONICAL_VERSION:
        raise GovernanceError("distributed proposal canonicalization is unsupported")
    if proposal.hash_algorithm != "sha256":
        raise GovernanceError("distributed proposal hash algorithm is unsupported")
    if proposal.profile != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("distributed proposal profile is invalid")
    if proposal.assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("distributed proposal assurance is invalid")
    for name in (
        "proposal_id",
        "protocol_id",
        "run_id",
        "target",
        "candidate_id",
    ):
        require_commit_text(
            getattr(proposal, name),
            f"distributed proposal {name}",
        )
    for name in _PROPOSAL_ROOT_FIELDS:
        require_commit_fingerprint(
            getattr(proposal, name),
            f"distributed proposal {name}",
        )
    require_commit_step(proposal.epoch, "distributed proposal epoch")
    require_commit_step(
        proposal.proposed_at_step,
        "distributed proposal proposed_at_step",
    )
    if proposal.portable_certificate_version != EVIDENCE_COMMIT_CERTIFICATE_VERSION:
        raise GovernanceError(
            "distributed proposal portable certificate version is unsupported"
        )
    if proposal.local_receipt_version != LOCAL_COMMIT_RECEIPT_VERSION:
        raise GovernanceError(
            "distributed proposal local receipt version is unsupported"
        )
    expected_value_root = distributed_commit_value_root_from_mapping(
        _public_dataclass_payload(proposal),
        value_version=commit_value_version,
    )
    if proposal.commit_value_root != expected_value_root:
        raise GovernanceError("distributed proposal commit value root is invalid")
    expected = commit_payload_fingerprint(
        _distributed_proposal_body_payload(proposal),
        schema=proposal_version,
        profile=proposal.profile,
    )
    if proposal.proposal_digest != expected:
        raise GovernanceError("distributed proposal digest is invalid")


def distributed_commit_value_payload_from_mapping(
    values: Mapping[str, object],
    *,
    value_version: str,
) -> dict[str, object]:
    try:
        return {
            "value_version": value_version,
            **{name: values[name] for name in _DISTRIBUTED_COMMIT_VALUE_FIELDS},
        }
    except KeyError as exc:
        raise GovernanceError(
            f"distributed commit value is missing {exc.args[0]}"
        ) from exc


def validate_distributed_commit_value_payload(
    value: Mapping[str, object],
    *,
    value_version: str,
) -> dict[str, object]:
    if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
        raise GovernanceError("distributed commit value payload must be a mapping")
    expected = {"value_version", *_DISTRIBUTED_COMMIT_VALUE_FIELDS}
    observed = set(value)
    if observed != expected:
        raise GovernanceError(
            "distributed commit value payload keys mismatch; "
            f"missing={sorted(expected - observed)}, "
            f"extra={sorted(observed - expected)}"
        )
    payload = dict(value)
    if payload["value_version"] != value_version:
        raise GovernanceError("distributed commit value version is unsupported")
    if payload["wire_version"] != COMMIT_WIRE_VERSION:
        raise GovernanceError("distributed commit value wire version is unsupported")
    if payload["canonicalization"] != COMMIT_CANONICAL_VERSION:
        raise GovernanceError(
            "distributed commit value canonicalization is unsupported"
        )
    if payload["hash_algorithm"] != "sha256":
        raise GovernanceError("distributed commit value hash algorithm is unsupported")
    require_commit_profile(payload["profile"], "distributed commit value profile")
    if payload["profile"] != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("distributed commit value profile is invalid")
    assurance = _coerce_assurance(payload["assurance"])
    if assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("distributed commit value assurance is invalid")
    payload["assurance"] = assurance
    for name in ("protocol_id", "run_id", "target", "candidate_id"):
        require_commit_text(payload[name], f"distributed commit value {name}")
    require_commit_step(payload["epoch"], "distributed commit value epoch")
    fingerprint_fields = {
        name
        for name in _DISTRIBUTED_COMMIT_VALUE_FIELDS
        if name.endswith("_root")
        or name in {"claim_fingerprint", "output_payload_fingerprint"}
    }
    for name in sorted(fingerprint_fields):
        require_commit_fingerprint(
            payload[name],
            f"distributed commit value {name}",
        )
    if payload["local_receipt_version"] != LOCAL_COMMIT_RECEIPT_VERSION:
        raise GovernanceError(
            "distributed commit value local receipt version is unsupported"
        )
    if payload["portable_certificate_version"] != (EVIDENCE_COMMIT_CERTIFICATE_VERSION):
        raise GovernanceError(
            "distributed commit value portable certificate version is unsupported"
        )
    return payload


def distributed_commit_value_root_from_mapping(
    values: Mapping[str, object],
    *,
    value_version: str,
) -> str:
    payload = validate_distributed_commit_value_payload(
        distributed_commit_value_payload_from_mapping(
            values,
            value_version=value_version,
        ),
        value_version=value_version,
    )
    profile = payload["profile"]
    if type(profile) is not str:
        raise GovernanceError("distributed commit value profile is invalid")
    return commit_payload_fingerprint(
        payload,
        schema=value_version,
        profile=profile,
    )


def _distributed_proposal_body_payload(
    proposal: object,
) -> dict[str, object]:
    payload = _public_dataclass_payload(proposal)
    payload.pop("proposal_digest")
    return payload


def distributed_proposal_body_from_receipt(
    receipt: LocalCommitReceipt,
    *,
    portable_certificate: EvidenceCommitCertificate,
    proposal_id: str,
    proposed_at_step: int,
    proposal_version: str,
) -> dict[str, object]:
    return {
        "proposal_version": proposal_version,
        "wire_version": receipt.wire_version,
        "canonicalization": receipt.canonicalization,
        "hash_algorithm": receipt.hash_algorithm,
        "proposal_id": require_commit_text(
            proposal_id,
            "distributed proposal proposal_id",
        ),
        "profile": receipt.profile,
        "assurance": receipt.assurance,
        "manifest_root": receipt.manifest_root,
        "commit_policy_root": receipt.commit_policy_root,
        "protocol_id": receipt.protocol_id,
        "run_id": receipt.run_id,
        "target": receipt.target,
        "epoch": receipt.epoch,
        "candidate_id": receipt.candidate_id,
        "claim_fingerprint": receipt.claim_fingerprint,
        "output_payload_fingerprint": receipt.output_payload_fingerprint,
        "risk_chain_state_root": receipt.risk_chain_state_root,
        "risk_assessment_root": receipt.risk_assessment_root,
        "risk_policy_root": receipt.risk_policy_root,
        "membership_snapshot_root": receipt.membership_snapshot_root,
        "membership_epoch_state_root": receipt.membership_epoch_state_root,
        "membership_root": receipt.membership_root,
        "replay_state_root": receipt.replay_state_root,
        "replay_root": receipt.replay_root,
        "support_replay_state_root": receipt.support_replay_state_root,
        "support_replay_root": receipt.support_replay_root,
        "candidate_evidence_root": receipt.candidate_evidence_root,
        "candidate_challenge_root": receipt.candidate_challenge_root,
        "candidate_lease_root": receipt.candidate_lease_root,
        "evidence_root": receipt.evidence_root,
        "challenge_root": receipt.challenge_root,
        "lease_root": receipt.lease_root,
        "window_state_root": receipt.window_state_root,
        "window_root": receipt.window_root,
        "threshold_root": receipt.threshold_root,
        "stop_resolution_root": receipt.stop_resolution_root,
        "permission_root": receipt.permission_root,
        "context_root": receipt.context_root,
        "assessment_root": receipt.assessment_root,
        "local_receipt_version": receipt.receipt_version,
        "local_receipt_ref": local_commit_receipt_fingerprint(receipt),
        "portable_certificate_version": portable_certificate.certificate_version,
        "portable_certificate_ref": evidence_commit_certificate_fingerprint(
            portable_certificate
        ),
        "proposed_at_step": proposed_at_step,
    }


def _validate_receipt_certificate_lineage(
    receipt: LocalCommitReceipt,
    certificate: EvidenceCommitCertificate,
) -> None:
    for name in _CENTRAL_LINEAGE_FIELDS:
        if getattr(certificate, name) != getattr(receipt, name):
            raise GovernanceError(
                f"portable central certificate {name} does not match receipt"
            )
    if certificate.local_receipt_ref != local_commit_receipt_fingerprint(receipt):
        raise GovernanceError("portable certificate local receipt ref mismatch")


def _validate_proposal_certificate_lineage(
    proposal: object,
    certificate: EvidenceCommitCertificate,
) -> None:
    for name in _CENTRAL_LINEAGE_FIELDS:
        if getattr(proposal, name) != getattr(certificate, name):
            raise GovernanceError(
                f"distributed proposal {name} does not match portable certificate"
            )
    if (
        proposal.local_receipt_ref != certificate.local_receipt_ref
        or proposal.portable_certificate_version != certificate.certificate_version
        or proposal.portable_certificate_ref
        != evidence_commit_certificate_fingerprint(certificate)
    ):
        raise GovernanceError("distributed proposal portable certificate mismatch")


def _validate_proposal_membership(
    proposal: object,
    membership: object,
) -> None:
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
        if getattr(proposal, name) != getattr(membership, name):
            raise GovernanceError(f"distributed proposal membership {name} mismatch")
    if (
        proposal.membership_snapshot_root != membership.snapshot_fingerprint
        or proposal.membership_root != membership.membership_root
    ):
        raise GovernanceError("distributed proposal membership root mismatch")
