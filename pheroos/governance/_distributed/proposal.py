from __future__ import annotations

from collections.abc import Mapping

from dataclasses import dataclass, field


from pheroos.governance._distributed.invariants import (
    _coerce_assurance,
    _public_dataclass_payload,
    _strict_dataclass_payload,
    _validate_distributed_policy,
)

from pheroos.governance._distributed._membership_contract import (
    _validate_membership_policy,
    _validate_portable_membership_snapshot,
)

from pheroos.governance._distributed._proposal_contract import (
    _validate_proposal_certificate_lineage,
    _validate_proposal_membership,
    _validate_receipt_certificate_lineage,
    distributed_commit_value_payload_from_mapping as _distributed_commit_value_payload_from_mapping_engine,
    distributed_commit_value_root_from_mapping as _distributed_commit_value_root_from_mapping_engine,
    distributed_proposal_body_from_receipt as _distributed_proposal_body_from_receipt_engine,
    validate_distributed_commit_proposal as _validate_distributed_commit_proposal_engine,
    validate_distributed_commit_value_payload as _validate_distributed_commit_value_payload_engine,
)

from pheroos.governance._distributed.records import (
    _LEGACY_PROPOSALS_BY_ID,
    _PROPOSAL_ISSUANCE,
)


from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_step,
)

from pheroos.governance._legacy.authority_registry import (
    LEGACY_AUTHORITY_REGISTRY,
)


from pheroos.governance.certificate import (
    EvidenceCommitCertificate,
    LocalCommitReceipt,
    local_commit_receipt_is_authoritative,
    verify_evidence_commit_certificate,
)

from pheroos.governance.commit_numeric import commit_payload_fingerprint

from pheroos.governance.errors import GovernanceError


from pheroos.protocol.commit_models import (
    CollectiveCommitPolicy,
    CommitAssurance,
)


from pheroos.governance._distributed.constants import (
    DISTRIBUTED_PROPOSAL_VERSION,
    DISTRIBUTED_COMMIT_VALUE_VERSION,
)
from pheroos.governance._support.records import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    eligible_membership_epoch_state_fingerprint,
)
from pheroos.governance._support.membership import (
    eligible_principal_snapshot_matches,
)
from pheroos.governance._distributed.membership import (
    PortableMembershipSnapshot,
    portable_membership_snapshot_from_eligible,
)


def _validate_distributed_commit_proposal(
    proposal: DistributedCommitProposal,
) -> None:
    _validate_distributed_commit_proposal_engine(
        proposal,
        proposal_version=DISTRIBUTED_PROPOSAL_VERSION,
        commit_value_version=DISTRIBUTED_COMMIT_VALUE_VERSION,
    )


def _distributed_commit_value_payload_from_mapping(
    values: Mapping[str, object],
) -> dict[str, object]:
    return _distributed_commit_value_payload_from_mapping_engine(
        values,
        value_version=DISTRIBUTED_COMMIT_VALUE_VERSION,
    )


def _validate_distributed_commit_value_payload(
    value: Mapping[str, object],
) -> dict[str, object]:
    return _validate_distributed_commit_value_payload_engine(
        value,
        value_version=DISTRIBUTED_COMMIT_VALUE_VERSION,
    )


def _distributed_commit_value_root_from_mapping(
    values: Mapping[str, object],
) -> str:
    return _distributed_commit_value_root_from_mapping_engine(
        values,
        value_version=DISTRIBUTED_COMMIT_VALUE_VERSION,
    )


def _distributed_proposal_body_from_receipt(
    receipt: LocalCommitReceipt,
    *,
    portable_certificate: EvidenceCommitCertificate,
    proposal_id: str,
    proposed_at_step: int,
) -> dict[str, object]:
    return _distributed_proposal_body_from_receipt_engine(
        receipt,
        portable_certificate=portable_certificate,
        proposal_id=proposal_id,
        proposed_at_step=proposed_at_step,
        proposal_version=DISTRIBUTED_PROPOSAL_VERSION,
    )


@dataclass(frozen=True)
class DistributedCommitProposal:
    proposal_version: str
    wire_version: str
    canonicalization: str
    hash_algorithm: str
    proposal_id: str
    profile: str
    assurance: CommitAssurance
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
    threshold_root: str
    stop_resolution_root: str
    permission_root: str
    context_root: str
    assessment_root: str
    local_receipt_version: str
    local_receipt_ref: str
    portable_certificate_version: str
    portable_certificate_ref: str
    proposed_at_step: int
    commit_value_root: str
    proposal_digest: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _validate_distributed_commit_proposal(self)


def issue_distributed_commit_proposal(
    receipt: LocalCommitReceipt,
    portable_certificate: EvidenceCommitCertificate,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    *,
    commit_policy: CollectiveCommitPolicy,
    trusted_issuer_attestations: Mapping[str, str],
    proposal_id: str,
    proposed_at_step: int,
) -> DistributedCommitProposal:
    """Build the exact digest witnesses sign from authoritative central leaves.

    The final bounded-liveness outcome is intentionally not an input: finality
    must be established first, after which its certificate fingerprint is
    passed to liveness. The proposal instead binds the stable window,
    assessment, local receipt, and independently verified portable central
    certificate.
    """

    if not local_commit_receipt_is_authoritative(receipt):
        raise GovernanceError(
            "distributed proposal requires an authoritative local receipt"
        )
    if receipt.assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("distributed proposal requires distributed assurance")
    distributed = _validate_distributed_policy(
        commit_policy,
        profile=receipt.profile,
        assurance=receipt.assurance,
        target=receipt.target,
        commit_policy_root=receipt.commit_policy_root,
    )
    current = require_commit_step(
        proposed_at_step,
        "distributed proposal proposed_at_step",
    )
    if not verify_evidence_commit_certificate(
        portable_certificate,
        trusted_issuer_attestations=trusted_issuer_attestations,
    ):
        raise GovernanceError(
            "distributed proposal portable certificate verification failed"
        )
    _validate_receipt_certificate_lineage(receipt, portable_certificate)
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
        raise GovernanceError(
            "distributed proposal membership snapshot is not authoritative and fresh"
        )
    portable_membership = portable_membership_snapshot_from_eligible(
        membership_snapshot
    )
    _validate_membership_policy(portable_membership, distributed)
    membership_epoch_ref = eligible_membership_epoch_state_fingerprint(
        membership_epoch_state
    )
    if (
        receipt.membership_snapshot_root != portable_membership.snapshot_fingerprint
        or receipt.membership_epoch_state_root != membership_epoch_ref
        or receipt.membership_root != portable_membership.membership_root
    ):
        raise GovernanceError(
            "distributed proposal central receipt membership lineage mismatch"
        )
    body = _distributed_proposal_body_from_receipt(
        receipt,
        portable_certificate=portable_certificate,
        proposal_id=proposal_id,
        proposed_at_step=current,
    )
    body["commit_value_root"] = _distributed_commit_value_root_from_mapping(body)
    digest = commit_payload_fingerprint(
        body,
        schema=DISTRIBUTED_PROPOSAL_VERSION,
        profile=receipt.profile,
    )
    proposal = DistributedCommitProposal(**body, proposal_digest=digest)
    object.__setattr__(
        proposal,
        "_issuance",
        (_PROPOSAL_ISSUANCE, distributed_commit_proposal_fingerprint(proposal)),
    )
    key = (
        proposal.profile,
        proposal.run_id,
        proposal.target,
        proposal.epoch,
        proposal.proposal_id,
    )
    with LEGACY_AUTHORITY_REGISTRY.transaction() as registry:
        existing = registry.get(_LEGACY_PROPOSALS_BY_ID, key)
        if existing is not None:
            if distributed_commit_proposal_fingerprint(existing) != (
                distributed_commit_proposal_fingerprint(proposal)
            ):
                raise GovernanceError(
                    "distributed proposal id replay has a different body"
                )
            return existing
        registry.set(_LEGACY_PROPOSALS_BY_ID, key, proposal)
        return proposal


def distributed_commit_proposal_payload(
    proposal: DistributedCommitProposal,
) -> dict[str, object]:
    if type(proposal) is not DistributedCommitProposal:
        raise GovernanceError("distributed proposal must use the canonical record")
    _validate_distributed_commit_proposal(proposal)
    return _public_dataclass_payload(proposal)


def distributed_commit_value_payload(
    proposal: DistributedCommitProposal,
) -> dict[str, object]:
    """Return the canonical semantic value carried by a proposal.

    Proposal, receipt, certificate, witness, and transport identities are proof
    envelope metadata.  They remain covered by the full proposal digest, but
    are deliberately absent here so an exact semantic retry cannot manufacture
    a Byzantine safety conflict.
    """

    if type(proposal) is not DistributedCommitProposal:
        raise GovernanceError("distributed commit value requires canonical proposal")
    _validate_distributed_commit_proposal(proposal)
    return _distributed_commit_value_payload_from_mapping(
        _public_dataclass_payload(proposal)
    )


def distributed_commit_value_root(
    value: DistributedCommitProposal | Mapping[str, object],
) -> str:
    if type(value) is DistributedCommitProposal:
        payload = distributed_commit_value_payload(value)
        profile = value.profile
    else:
        payload = _validate_distributed_commit_value_payload(value)
        profile = payload["profile"]
        assert type(profile) is str
    return commit_payload_fingerprint(
        payload,
        schema=DISTRIBUTED_COMMIT_VALUE_VERSION,
        profile=profile,
    )


def distributed_commit_proposal_fingerprint(
    proposal: DistributedCommitProposal,
) -> str:
    return commit_payload_fingerprint(
        distributed_commit_proposal_payload(proposal),
        schema="pheroos-distributed-commit-proposal-envelope-v1",
        profile=proposal.profile,
    )


def distributed_commit_proposal_is_authoritative(proposal: object) -> bool:
    if type(proposal) is not DistributedCommitProposal:
        return False
    try:
        issuance = proposal._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _PROPOSAL_ISSUANCE
            and issuance[1] == distributed_commit_proposal_fingerprint(proposal)
        )
    except Exception:
        return False


def distributed_commit_proposal_from_payload(
    payload: Mapping[str, object],
) -> DistributedCommitProposal:
    values = _strict_dataclass_payload(
        payload,
        DistributedCommitProposal,
        "distributed proposal payload",
    )
    values["assurance"] = _coerce_assurance(values["assurance"])
    try:
        return DistributedCommitProposal(**values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(
            f"distributed proposal payload is invalid: {exc}"
        ) from exc


def verify_distributed_commit_proposal(
    proposal_or_payload: DistributedCommitProposal | Mapping[str, object],
    *,
    commit_policy: CollectiveCommitPolicy,
    portable_certificate: EvidenceCommitCertificate,
    membership_snapshot: PortableMembershipSnapshot | EligiblePrincipalSnapshot,
    trusted_issuer_attestations: Mapping[str, str],
    expected_proposal_digest: str = "",
    expected_commit_value_root: str = "",
) -> bool:
    try:
        proposal = (
            proposal_or_payload
            if type(proposal_or_payload) is DistributedCommitProposal
            else distributed_commit_proposal_from_payload(proposal_or_payload)
        )
        assert type(proposal) is DistributedCommitProposal
        distributed = _validate_distributed_policy(
            commit_policy,
            profile=proposal.profile,
            assurance=proposal.assurance,
            target=proposal.target,
            commit_policy_root=proposal.commit_policy_root,
        )
        portable = _coerce_portable_membership(membership_snapshot)
        _validate_membership_policy(portable, distributed)
        _validate_proposal_membership(proposal, portable)
        if not verify_evidence_commit_certificate(
            portable_certificate,
            trusted_issuer_attestations=trusted_issuer_attestations,
            expected_certificate_ref=proposal.portable_certificate_ref,
            expected_claim_fingerprint=proposal.claim_fingerprint,
            expected_output_payload_fingerprint=(proposal.output_payload_fingerprint),
        ):
            return False
        _validate_proposal_certificate_lineage(proposal, portable_certificate)
        if expected_proposal_digest and proposal.proposal_digest != (
            require_commit_fingerprint(
                expected_proposal_digest,
                "expected distributed proposal digest",
            )
        ):
            return False
        if expected_commit_value_root and proposal.commit_value_root != (
            require_commit_fingerprint(
                expected_commit_value_root,
                "expected distributed commit value root",
            )
        ):
            return False
        return True
    except (AssertionError, TypeError, ValueError, GovernanceError):
        return False


def _coerce_portable_membership(
    membership: PortableMembershipSnapshot | EligiblePrincipalSnapshot,
) -> PortableMembershipSnapshot:
    if type(membership) is PortableMembershipSnapshot:
        _validate_portable_membership_snapshot(membership)
        return membership
    if type(membership) is EligiblePrincipalSnapshot:
        return portable_membership_snapshot_from_eligible(membership)
    raise GovernanceError("distributed membership snapshot type is invalid")


for _name in (
    "_validate_distributed_commit_proposal",
    "_distributed_commit_value_payload_from_mapping",
    "_validate_distributed_commit_value_payload",
    "_distributed_commit_value_root_from_mapping",
    "_distributed_proposal_body_from_receipt",
    "DistributedCommitProposal",
    "issue_distributed_commit_proposal",
    "distributed_commit_proposal_payload",
    "distributed_commit_value_payload",
    "distributed_commit_value_root",
    "distributed_commit_proposal_fingerprint",
    "distributed_commit_proposal_is_authoritative",
    "distributed_commit_proposal_from_payload",
    "verify_distributed_commit_proposal",
    "_coerce_portable_membership",
):
    globals()[_name].__module__ = "pheroos.governance.distributed_commit"
del _name
