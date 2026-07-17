from __future__ import annotations

from pheroos.governance.errors import GovernanceError


def _validate_receipt_state_binding(
    receipt: object,
    state: object,
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
        "membership_root",
    ):
        if getattr(receipt, name) != getattr(state, name):
            raise GovernanceError(f"distributed receipt state {name} mismatch")
    if receipt.membership_snapshot_root != state.membership_snapshot_root:
        raise GovernanceError("distributed receipt membership snapshot mismatch")
    if receipt.membership_epoch_state_root != state.membership_epoch_state_root:
        raise GovernanceError("distributed receipt membership epoch mismatch")


def _validate_certificate_proposal_binding(
    certificate: object,
) -> None:
    proposal = certificate.proposal
    for name in (
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
        "candidate_id",
        "commit_value_root",
        "proposal_digest",
        "membership_snapshot_root",
        "membership_root",
        "portable_certificate_ref",
        "portable_certificate_version",
    ):
        if getattr(certificate, name) != getattr(proposal, name):
            raise GovernanceError(f"distributed certificate proposal {name} mismatch")
    if certificate.membership_snapshot.snapshot_fingerprint != (
        certificate.membership_snapshot_root
    ) or certificate.membership_snapshot.membership_root != (
        certificate.membership_root
    ):
        raise GovernanceError("distributed certificate membership root mismatch")


def _validate_certificate_state_binding(
    certificate: object,
    state: object,
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
        "membership_snapshot_root",
        "membership_root",
        "membership_size",
        "max_byzantine_faults",
        "witness_quorum",
        "minimum_failure_domain_diversity",
    ):
        if getattr(certificate, name) != getattr(state, name):
            raise GovernanceError(f"distributed certificate state {name} mismatch")
