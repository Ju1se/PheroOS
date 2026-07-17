from __future__ import annotations

from collections.abc import Mapping, Sequence

from dataclasses import dataclass

from enum import StrEnum

from pheroos.governance._distributed._certificate_contract import (
    _validate_certificate_proposal_binding,
    _validate_certificate_state_binding,
    _validate_receipt_state_binding,
)

from pheroos.governance._distributed.invariants import (
    _coerce_assurance,
    _coerce_authority,
    _public_dataclass_payload,
    _quorum_intersection_is_safe,
    _require_sequence,
    _strict_dataclass_payload,
    _validate_distributed_policy,
)

from pheroos.governance._distributed._membership_contract import (
    _validate_membership_policy,
    _validate_portable_membership_snapshot,
)


from pheroos.governance._distributed.records import (
    _LEGACY_DISTRIBUTED_CERTIFICATES_BY_ID,
    _DistributedStateCursor,
)

from pheroos.governance._distributed._state_contract import (
    _replace_distributed_state,
    _validate_proposal_state_binding,
)


from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_step,
    require_commit_text,
)

from pheroos.governance._legacy.authority_registry import (
    LEGACY_AUTHORITY_REGISTRY,
)

from pheroos.governance.authority import AuthorityLevel, can_verify

from pheroos.governance.certificate import (
    EvidenceCommitCertificate,
    LocalCommitReceipt,
    local_commit_receipt_fingerprint,
    local_commit_receipt_is_authoritative,
)

from pheroos.governance.commit_numeric import commit_payload_fingerprint

from pheroos.governance.errors import GovernanceError


from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_WIRE_VERSION,
    DISTRIBUTED_COMMIT_PROFILE_VERSION,
    CollectiveCommitPolicy,
    CommitAssurance,
)


from pheroos.governance._distributed.constants import (
    DISTRIBUTED_COMMIT_CERTIFICATE_VERSION,
    DISTRIBUTED_COMMIT_CERTIFICATE_DISCRIMINATOR,
)

from pheroos.governance._distributed.membership import (
    PortableMembershipSnapshot,
    portable_membership_snapshot_payload,
    portable_membership_snapshot_from_payload,
)

from pheroos.governance._distributed.proposal import (
    _validate_distributed_commit_proposal,
    DistributedCommitProposal,
    distributed_commit_proposal_payload,
    distributed_commit_proposal_from_payload,
    verify_distributed_commit_proposal,
)

from pheroos.governance._distributed.witness import (
    WitnessVerification,
    witness_verification_payload,
    witness_verification_fingerprint,
    witness_verification_is_authoritative,
    witness_verification_from_payload,
    verify_portable_witness_verification,
    _canonical_witness_verifications,
    _witness_verification_root,
)

from pheroos.governance._distributed.state import (
    FinalCertificateRegistration,
    DistributedCommitState,
    distributed_commit_state_fingerprint,
    distributed_commit_state_is_authoritative,
    distributed_commit_state_is_current,
    _certificate_conflict_finding,
    _issue_distributed_state,
    _current_distributed_state_head,
)


class DistributedCertificateStatus(StrEnum):
    PROVISIONAL = "provisional"
    FINAL = "final"


@dataclass(frozen=True)
class DistributedCommitCertificate:
    schema_discriminator: str
    certificate_version: str
    wire_version: str
    canonicalization: str
    hash_algorithm: str
    certificate_id: str
    status: DistributedCertificateStatus
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    candidate_id: str
    commit_value_root: str
    proposal_digest: str
    proposal: DistributedCommitProposal
    membership_snapshot: PortableMembershipSnapshot
    membership_snapshot_root: str
    membership_root: str
    membership_size: int
    max_byzantine_faults: int
    witness_quorum: int
    minimum_failure_domain_diversity: int
    witnesses: tuple[WitnessVerification, ...]
    witness_root: str
    excluded_cluster_ids: tuple[str, ...]
    portable_certificate_ref: str
    portable_certificate_version: str
    issuer_id: str
    authority: AuthorityLevel
    issued_at_step: int
    provenance: str
    trace_event_id: str
    certificate_body_root: str
    certificate_root: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "witnesses",
            _canonical_witness_verifications(self.witnesses),
        )
        object.__setattr__(
            self,
            "excluded_cluster_ids",
            require_commit_labels(
                self.excluded_cluster_ids,
                "distributed certificate excluded clusters",
                allow_empty=True,
            ),
        )
        _validate_distributed_commit_certificate(self)


def issue_distributed_commit_certificate(
    state: DistributedCommitState,
    proposal: DistributedCommitProposal,
    *,
    verifications: Sequence[WitnessVerification],
    commit_policy: CollectiveCommitPolicy,
    portable_certificate: EvidenceCommitCertificate,
    trusted_issuer_attestations: Mapping[str, str],
    trusted_witness_attestations: Mapping[str, str],
    certificate_id: str,
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> DistributedCommitCertificate:
    if not distributed_commit_state_is_current(state):
        raise GovernanceError(
            "distributed certificate requires the current authoritative state"
        )
    if state.frozen:
        raise GovernanceError("frozen distributed epoch cannot issue certificates")
    if state.transitioned:
        raise GovernanceError(
            "transitioned distributed epoch cannot issue certificates"
        )
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError(
            "distributed certificate issuance requires governance authority"
        )
    current = require_commit_step(
        issued_at_step,
        "distributed certificate issued_at_step",
    )
    distributed = _validate_distributed_policy(
        commit_policy,
        profile=state.profile,
        assurance=state.assurance,
        target=state.target,
        commit_policy_root=state.commit_policy_root,
    )
    if not verify_distributed_commit_proposal(
        proposal,
        commit_policy=commit_policy,
        portable_certificate=portable_certificate,
        membership_snapshot=state.membership_snapshot,
        trusted_issuer_attestations=trusted_issuer_attestations,
    ):
        raise GovernanceError("distributed proposal verification failed")
    _validate_proposal_state_binding(proposal, state)
    requested = _canonical_witness_verifications(verifications)
    if not requested:
        raise GovernanceError(
            "distributed certificate requires at least one verified witness"
        )
    recorded = {
        witness_verification_fingerprint(item): item
        for item in state.witness_verifications
    }
    excluded = set(state.excluded_cluster_ids)
    by_cluster: dict[str, WitnessVerification] = {}
    for verification in requested:
        fingerprint = witness_verification_fingerprint(verification)
        if (
            not witness_verification_is_authoritative(verification)
            or fingerprint not in recorded
        ):
            raise GovernanceError(
                "distributed certificate contains an unrecorded witness"
            )
        witness = verification.witness
        if (
            witness.proposal_digest != proposal.proposal_digest
            or witness.commit_value_root != proposal.commit_value_root
        ):
            raise GovernanceError(
                "distributed certificate witness signed another proposal"
            )
        if witness.principal_cluster_id in excluded:
            continue
        if not verify_portable_witness_verification(
            verification,
            membership_snapshot=state.membership_snapshot,
            trusted_witness_attestations=trusted_witness_attestations,
            issued_at_step=current,
        ):
            raise GovernanceError(
                "distributed certificate witness verification is not portable/fresh"
            )
        prior = by_cluster.get(witness.principal_cluster_id)
        if prior is None or witness_verification_fingerprint(verification) < (
            witness_verification_fingerprint(prior)
        ):
            by_cluster[witness.principal_cluster_id] = verification
    included = _canonical_witness_verifications(tuple(by_cluster.values()))
    if not included:
        raise GovernanceError(
            "all distributed certificate witnesses were excluded for equivocation"
        )
    failure_domains = {item.witness.failure_domain for item in included}
    status = (
        DistributedCertificateStatus.FINAL
        if (
            len(included) >= distributed.witness_quorum
            and len(failure_domains) >= distributed.minimum_failure_domain_diversity
        )
        else DistributedCertificateStatus.PROVISIONAL
    )
    body = {
        "schema_discriminator": (DISTRIBUTED_COMMIT_CERTIFICATE_DISCRIMINATOR),
        "certificate_version": DISTRIBUTED_COMMIT_CERTIFICATE_VERSION,
        "wire_version": COMMIT_WIRE_VERSION,
        "canonicalization": COMMIT_CANONICAL_VERSION,
        "hash_algorithm": "sha256",
        "certificate_id": require_commit_text(
            certificate_id,
            "distributed certificate certificate_id",
        ),
        "status": status,
        "profile": state.profile,
        "assurance": state.assurance,
        "manifest_root": state.manifest_root,
        "commit_policy_root": state.commit_policy_root,
        "protocol_id": state.protocol_id,
        "run_id": state.run_id,
        "target": state.target,
        "epoch": state.epoch,
        "candidate_id": proposal.candidate_id,
        "commit_value_root": proposal.commit_value_root,
        "proposal_digest": proposal.proposal_digest,
        "proposal": proposal,
        "membership_snapshot": state.membership_snapshot,
        "membership_snapshot_root": state.membership_snapshot_root,
        "membership_root": state.membership_root,
        "membership_size": state.membership_size,
        "max_byzantine_faults": state.max_byzantine_faults,
        "witness_quorum": state.witness_quorum,
        "minimum_failure_domain_diversity": (state.minimum_failure_domain_diversity),
        "witnesses": included,
        "witness_root": _witness_verification_root(
            included,
            profile=state.profile,
            commit_value_root=proposal.commit_value_root,
            proposal_digest=proposal.proposal_digest,
        ),
        "excluded_cluster_ids": state.excluded_cluster_ids,
        "portable_certificate_ref": proposal.portable_certificate_ref,
        "portable_certificate_version": proposal.portable_certificate_version,
        "issuer_id": require_commit_text(
            issuer_id,
            "distributed certificate issuer_id",
        ),
        "authority": authority,
        "issued_at_step": current,
        "provenance": require_commit_text(
            provenance,
            "distributed certificate provenance",
        ),
        "trace_event_id": require_commit_text(
            trace_event_id,
            "distributed certificate trace_event_id",
        ),
    }
    body_root = _distributed_certificate_body_root(body, profile=state.profile)
    certificate_root = commit_payload_fingerprint(
        {
            "certificate_body_root": body_root,
            "commit_value_root": proposal.commit_value_root,
            "proposal_digest": proposal.proposal_digest,
            "witness_root": body["witness_root"],
        },
        schema="pheroos-distributed-commit-certificate-envelope-v1",
        profile=state.profile,
    )
    certificate = DistributedCommitCertificate(
        **body,
        certificate_body_root=body_root,
        certificate_root=certificate_root,
    )
    return _register_distributed_certificate_identity(certificate)


def assemble_portable_distributed_commit_certificate(
    proposal: DistributedCommitProposal | Mapping[str, object],
    membership_snapshot: PortableMembershipSnapshot,
    verifications: Sequence[WitnessVerification | Mapping[str, object]],
    *,
    commit_policy: CollectiveCommitPolicy,
    portable_certificate: EvidenceCommitCertificate,
    trusted_issuer_attestations: Mapping[str, str],
    trusted_witness_attestations: Mapping[str, str],
    certificate_id: str,
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> DistributedCommitCertificate:
    """Aggregate a portable peer proof without process-local state authority.

    This is required for independent verification and conflict ingestion.  It
    never mutates or authorizes a local epoch; callers must register a FINAL
    result in the strong local state before using it as current authority.
    """

    canonical_proposal = (
        proposal
        if type(proposal) is DistributedCommitProposal
        else distributed_commit_proposal_from_payload(proposal)
    )
    assert type(canonical_proposal) is DistributedCommitProposal
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError(
            "portable distributed certificate requires governance issuer metadata"
        )
    current = require_commit_step(
        issued_at_step,
        "portable distributed certificate issued_at_step",
    )
    distributed = _validate_distributed_policy(
        commit_policy,
        profile=canonical_proposal.profile,
        assurance=canonical_proposal.assurance,
        target=canonical_proposal.target,
        commit_policy_root=canonical_proposal.commit_policy_root,
    )
    _validate_membership_policy(membership_snapshot, distributed)
    if not verify_distributed_commit_proposal(
        canonical_proposal,
        commit_policy=commit_policy,
        portable_certificate=portable_certificate,
        membership_snapshot=membership_snapshot,
        trusted_issuer_attestations=trusted_issuer_attestations,
    ):
        raise GovernanceError("portable distributed proposal verification failed")
    parsed = tuple(
        item
        if type(item) is WitnessVerification
        else witness_verification_from_payload(item)
        for item in verifications
    )
    canonical = _canonical_witness_verifications(parsed)
    if not canonical:
        raise GovernanceError("portable distributed certificate needs witnesses")
    by_cluster: dict[str, WitnessVerification] = {}
    for verification in canonical:
        witness = verification.witness
        if (
            witness.proposal_digest != canonical_proposal.proposal_digest
            or witness.commit_value_root != canonical_proposal.commit_value_root
        ):
            raise GovernanceError("portable witness signed another proposal")
        if not verify_portable_witness_verification(
            verification,
            membership_snapshot=membership_snapshot,
            trusted_witness_attestations=trusted_witness_attestations,
            issued_at_step=current,
        ):
            raise GovernanceError("portable witness verification failed")
        if witness.principal_cluster_id in by_cluster:
            raise GovernanceError("portable certificate repeats a witness cluster")
        by_cluster[witness.principal_cluster_id] = verification
    included = _canonical_witness_verifications(tuple(by_cluster.values()))
    status = (
        DistributedCertificateStatus.FINAL
        if (
            len(included) >= distributed.witness_quorum
            and len({item.witness.failure_domain for item in included})
            >= distributed.minimum_failure_domain_diversity
        )
        else DistributedCertificateStatus.PROVISIONAL
    )
    body = {
        "schema_discriminator": DISTRIBUTED_COMMIT_CERTIFICATE_DISCRIMINATOR,
        "certificate_version": DISTRIBUTED_COMMIT_CERTIFICATE_VERSION,
        "wire_version": COMMIT_WIRE_VERSION,
        "canonicalization": COMMIT_CANONICAL_VERSION,
        "hash_algorithm": "sha256",
        "certificate_id": require_commit_text(
            certificate_id,
            "portable distributed certificate_id",
        ),
        "status": status,
        "profile": canonical_proposal.profile,
        "assurance": canonical_proposal.assurance,
        "manifest_root": canonical_proposal.manifest_root,
        "commit_policy_root": canonical_proposal.commit_policy_root,
        "protocol_id": canonical_proposal.protocol_id,
        "run_id": canonical_proposal.run_id,
        "target": canonical_proposal.target,
        "epoch": canonical_proposal.epoch,
        "candidate_id": canonical_proposal.candidate_id,
        "commit_value_root": canonical_proposal.commit_value_root,
        "proposal_digest": canonical_proposal.proposal_digest,
        "proposal": canonical_proposal,
        "membership_snapshot": membership_snapshot,
        "membership_snapshot_root": membership_snapshot.snapshot_fingerprint,
        "membership_root": membership_snapshot.membership_root,
        "membership_size": distributed.membership_size,
        "max_byzantine_faults": distributed.max_byzantine_faults,
        "witness_quorum": distributed.witness_quorum,
        "minimum_failure_domain_diversity": (
            distributed.minimum_failure_domain_diversity
        ),
        "witnesses": included,
        "witness_root": _witness_verification_root(
            included,
            profile=canonical_proposal.profile,
            commit_value_root=canonical_proposal.commit_value_root,
            proposal_digest=canonical_proposal.proposal_digest,
        ),
        "excluded_cluster_ids": (),
        "portable_certificate_ref": canonical_proposal.portable_certificate_ref,
        "portable_certificate_version": (
            canonical_proposal.portable_certificate_version
        ),
        "issuer_id": require_commit_text(
            issuer_id,
            "portable distributed issuer_id",
        ),
        "authority": authority,
        "issued_at_step": current,
        "provenance": require_commit_text(
            provenance,
            "portable distributed provenance",
        ),
        "trace_event_id": require_commit_text(
            trace_event_id,
            "portable distributed trace_event_id",
        ),
    }
    body_root = _distributed_certificate_body_root(
        body,
        profile=canonical_proposal.profile,
    )
    root = commit_payload_fingerprint(
        {
            "certificate_body_root": body_root,
            "commit_value_root": canonical_proposal.commit_value_root,
            "proposal_digest": canonical_proposal.proposal_digest,
            "witness_root": body["witness_root"],
        },
        schema="pheroos-distributed-commit-certificate-envelope-v1",
        profile=canonical_proposal.profile,
    )
    certificate = DistributedCommitCertificate(
        **body,
        certificate_body_root=body_root,
        certificate_root=root,
    )
    return _register_distributed_certificate_identity(certificate)


def distributed_commit_certificate_payload(
    certificate: DistributedCommitCertificate,
) -> dict[str, object]:
    if type(certificate) is not DistributedCommitCertificate:
        raise GovernanceError("distributed certificate must use the canonical record")
    _validate_distributed_commit_certificate(certificate)
    payload = _public_dataclass_payload(certificate)
    payload["proposal"] = distributed_commit_proposal_payload(certificate.proposal)
    payload["membership_snapshot"] = portable_membership_snapshot_payload(
        certificate.membership_snapshot
    )
    payload["witnesses"] = tuple(
        witness_verification_payload(item) for item in certificate.witnesses
    )
    return payload


def distributed_commit_certificate_fingerprint(
    certificate: DistributedCommitCertificate,
) -> str:
    return commit_payload_fingerprint(
        distributed_commit_certificate_payload(certificate),
        schema=DISTRIBUTED_COMMIT_CERTIFICATE_VERSION,
        profile=certificate.profile,
    )


def distributed_commit_certificate_from_payload(
    payload: Mapping[str, object],
) -> DistributedCommitCertificate:
    values = _strict_dataclass_payload(
        payload,
        DistributedCommitCertificate,
        "distributed certificate payload",
    )
    values["status"] = _coerce_certificate_status(values["status"])
    values["assurance"] = _coerce_assurance(values["assurance"])
    values["authority"] = _coerce_authority(values["authority"])
    values["proposal"] = distributed_commit_proposal_from_payload(values["proposal"])
    values["membership_snapshot"] = portable_membership_snapshot_from_payload(
        values["membership_snapshot"]
    )
    values["witnesses"] = tuple(
        witness_verification_from_payload(item)
        for item in _require_sequence(
            values["witnesses"],
            "distributed certificate witnesses",
        )
    )
    values["excluded_cluster_ids"] = tuple(
        _require_sequence(
            values["excluded_cluster_ids"],
            "distributed certificate excluded clusters",
        )
    )
    try:
        return DistributedCommitCertificate(**values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(
            f"distributed certificate payload is invalid: {exc}"
        ) from exc


def verify_distributed_commit_certificate(
    certificate_or_payload: DistributedCommitCertificate | Mapping[str, object],
    *,
    commit_policy: CollectiveCommitPolicy,
    portable_certificate: EvidenceCommitCertificate,
    trusted_issuer_attestations: Mapping[str, str],
    trusted_witness_attestations: Mapping[str, str],
    expected_certificate_ref: str = "",
    expected_proposal_digest: str = "",
    expected_commit_value_root: str = "",
    require_final: bool = True,
) -> bool:
    """Independently verify proposal, membership, witnesses and q intersection."""

    try:
        if type(require_final) is not bool:
            return False
        certificate = (
            certificate_or_payload
            if type(certificate_or_payload) is DistributedCommitCertificate
            else distributed_commit_certificate_from_payload(certificate_or_payload)
        )
        assert type(certificate) is DistributedCommitCertificate
        distributed = _validate_distributed_policy(
            commit_policy,
            profile=certificate.profile,
            assurance=certificate.assurance,
            target=certificate.target,
            commit_policy_root=certificate.commit_policy_root,
        )
        if not verify_distributed_commit_proposal(
            certificate.proposal,
            commit_policy=commit_policy,
            portable_certificate=portable_certificate,
            membership_snapshot=certificate.membership_snapshot,
            trusted_issuer_attestations=trusted_issuer_attestations,
            expected_proposal_digest=certificate.proposal_digest,
            expected_commit_value_root=certificate.commit_value_root,
        ):
            return False
        if certificate.membership_size != distributed.membership_size:
            return False
        if certificate.max_byzantine_faults != distributed.max_byzantine_faults:
            return False
        if certificate.witness_quorum != distributed.witness_quorum:
            return False
        if certificate.minimum_failure_domain_diversity != (
            distributed.minimum_failure_domain_diversity
        ):
            return False
        if not _quorum_intersection_is_safe(
            certificate.membership_size,
            certificate.max_byzantine_faults,
            certificate.witness_quorum,
        ):
            return False
        excluded = set(certificate.excluded_cluster_ids)
        cluster_ids: set[str] = set()
        failure_domains: set[str] = set()
        for verification in certificate.witnesses:
            witness = verification.witness
            if (
                witness.proposal_digest != certificate.proposal_digest
                or witness.commit_value_root != certificate.commit_value_root
                or witness.target != certificate.target
                or witness.candidate_id != certificate.candidate_id
                or witness.epoch != certificate.epoch
                or witness.membership_root != certificate.membership_root
                or witness.principal_cluster_id in excluded
                or witness.principal_cluster_id in cluster_ids
            ):
                return False
            if not verify_portable_witness_verification(
                verification,
                membership_snapshot=certificate.membership_snapshot,
                trusted_witness_attestations=trusted_witness_attestations,
                issued_at_step=certificate.issued_at_step,
            ):
                return False
            cluster_ids.add(witness.principal_cluster_id)
            failure_domains.add(witness.failure_domain)
        meets_finality = bool(
            len(cluster_ids) >= certificate.witness_quorum
            and len(failure_domains) >= certificate.minimum_failure_domain_diversity
        )
        if certificate.status is DistributedCertificateStatus.FINAL:
            if not meets_finality:
                return False
        elif meets_finality:
            # A fully qualified proof cannot be mislabeled provisional.
            return False
        if (
            require_final
            and certificate.status is not DistributedCertificateStatus.FINAL
        ):
            return False
        if expected_certificate_ref and (
            distributed_commit_certificate_fingerprint(certificate)
            != require_commit_fingerprint(
                expected_certificate_ref,
                "expected distributed certificate ref",
            )
        ):
            return False
        if expected_proposal_digest and certificate.proposal_digest != (
            require_commit_fingerprint(
                expected_proposal_digest,
                "expected distributed proposal digest",
            )
        ):
            return False
        if expected_commit_value_root and certificate.commit_value_root != (
            require_commit_fingerprint(
                expected_commit_value_root,
                "expected distributed commit value root",
            )
        ):
            return False
        return True
    except (AssertionError, TypeError, ValueError, GovernanceError):
        return False


def record_distributed_commit_certificate(
    state: DistributedCommitState,
    certificate: DistributedCommitCertificate,
    *,
    commit_policy: CollectiveCommitPolicy,
    portable_certificate: EvidenceCommitCertificate,
    trusted_issuer_attestations: Mapping[str, str],
    trusted_witness_attestations: Mapping[str, str],
    current_step: int,
) -> DistributedCommitState:
    """Register final proofs and freeze on any same-epoch conflicting proof."""

    if not distributed_commit_state_is_authoritative(state):
        raise GovernanceError("distributed certificate registry state is forged")
    current = require_commit_step(
        current_step,
        "distributed certificate registration current_step",
    )
    if current < state.current_step:
        raise GovernanceError("distributed certificate registration moves backwards")
    if state.transitioned:
        raise GovernanceError("transitioned epoch cannot register final certificates")
    if not verify_distributed_commit_certificate(
        certificate,
        commit_policy=commit_policy,
        portable_certificate=portable_certificate,
        trusted_issuer_attestations=trusted_issuer_attestations,
        trusted_witness_attestations=trusted_witness_attestations,
        require_final=True,
    ):
        raise GovernanceError("distributed final certificate verification failed")
    _validate_certificate_state_binding(certificate, state)
    certificate_ref = distributed_commit_certificate_fingerprint(certificate)
    registration = FinalCertificateRegistration(
        certificate_ref=certificate_ref,
        commit_value_root=certificate.commit_value_root,
        proposal_digest=certificate.proposal_digest,
        candidate_id=certificate.candidate_id,
        registered_at_step=current,
    )
    existing = {item.certificate_ref: item for item in state.final_registrations}
    if certificate_ref in existing:
        current_head = _current_distributed_state_head(state)
        if not any(
            item.certificate_ref == certificate_ref
            and item.commit_value_root == certificate.commit_value_root
            and item.proposal_digest == certificate.proposal_digest
            for item in current_head.final_registrations
        ):
            raise GovernanceError(
                "distributed certificate replay is absent from the current head"
            )
        return current_head
    registrations = tuple((*state.final_registrations, registration))
    commit_value_roots = {item.commit_value_root for item in registrations}
    conflict_findings = state.conflict_findings
    frozen = state.frozen
    if len(commit_value_roots) > 1:
        frozen = True
        finding = _certificate_conflict_finding(
            registrations,
            profile=state.profile,
            target=state.target,
            epoch=state.epoch,
            current_step=current,
        )
        conflict_findings = tuple(
            sorted(
                {
                    item.finding_id: item for item in (*conflict_findings, finding)
                }.values(),
                key=lambda item: item.finding_id,
            )
        )
    parent_ref = distributed_commit_state_fingerprint(state)
    request_ref = commit_payload_fingerprint(
        {
            "certificate_ref": certificate_ref,
            "current_step": current,
            "parent_state_ref": parent_ref,
        },
        schema="pheroos-distributed-certificate-registration-request-v1",
        profile=state.profile,
    )
    cursor = state._cursor
    if type(cursor) is not _DistributedStateCursor:
        raise GovernanceError("distributed certificate state cursor is invalid")
    with cursor.lock:
        if cursor.current_state_fingerprint != parent_ref:
            prior = cursor.transitions.get(parent_ref)
            if prior is not None and prior[0] == request_ref:
                return prior[1]
            raise GovernanceError(
                "distributed certificate state is stale or would fork"
            )
        next_state = _replace_distributed_state(
            state,
            revision=state.revision + 1,
            current_step=current,
            previous_state_fingerprint=parent_ref,
            final_registrations=registrations,
            conflict_findings=conflict_findings,
            frozen=frozen,
        )
        next_state = _issue_distributed_state(next_state, cursor)
        cursor.current_state = next_state
        cursor.current_state_fingerprint = distributed_commit_state_fingerprint(
            next_state
        )
        cursor.transitions[parent_ref] = (request_ref, next_state)
        return next_state


def distributed_commit_certificate_is_current_final(
    certificate: object,
    state: object,
) -> bool:
    if (
        type(certificate) is not DistributedCommitCertificate
        or type(state) is not DistributedCommitState
    ):
        return False
    try:
        certificate_ref = distributed_commit_certificate_fingerprint(certificate)
        return bool(
            certificate.status is DistributedCertificateStatus.FINAL
            and distributed_commit_state_is_current(state)
            and not state.frozen
            and not state.transitioned
            and any(
                item.certificate_ref == certificate_ref
                and item.commit_value_root == certificate.commit_value_root
                and item.proposal_digest == certificate.proposal_digest
                for item in state.final_registrations
            )
        )
    except GovernanceError:
        return False


def verify_distributed_commit_finality(
    certificate: DistributedCommitCertificate,
    state: DistributedCommitState,
    receipt: LocalCommitReceipt,
    *,
    current_step: int,
    verifier_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
):
    """Issue typed finality from a current registered FINAL proof."""

    if not distributed_commit_certificate_is_current_final(certificate, state):
        raise GovernanceError(
            "distributed finality verification requires current registered FINAL proof"
        )
    if not local_commit_receipt_is_authoritative(receipt):
        raise GovernanceError("distributed finality receipt is not authoritative")
    _validate_receipt_state_binding(receipt, state)
    proposal = certificate.proposal
    receipt_ref = local_commit_receipt_fingerprint(receipt)
    if proposal.local_receipt_ref != receipt_ref:
        raise GovernanceError("distributed finality local receipt lineage mismatch")
    current = require_commit_step(
        current_step,
        "distributed finality verified_at_step",
    )
    if current < certificate.issued_at_step:
        raise GovernanceError("distributed finality certificate is from the future")
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("distributed finality verifier lacks authority")
    from pheroos.governance._commit_state.records import (
        CommitFinalityStatus,
        _issue_commit_finality_verification,
    )

    return _issue_commit_finality_verification(
        status=CommitFinalityStatus.VERIFIED,
        certificate_kind=DISTRIBUTED_COMMIT_CERTIFICATE_DISCRIMINATOR,
        certificate_ref=distributed_commit_certificate_fingerprint(certificate),
        profile=proposal.profile,
        assurance=proposal.assurance,
        manifest_root=proposal.manifest_root,
        commit_policy_root=proposal.commit_policy_root,
        protocol_id=proposal.protocol_id,
        run_id=proposal.run_id,
        target=proposal.target,
        epoch=proposal.epoch,
        candidate_id=proposal.candidate_id,
        context_ref=proposal.context_root,
        assessment_ref=proposal.assessment_root,
        window_state_ref=proposal.window_state_root,
        window_root=proposal.window_root,
        risk_assessment_root=proposal.risk_assessment_root,
        risk_chain_state_root=proposal.risk_chain_state_root,
        risk_policy_root=proposal.risk_policy_root,
        membership_root=proposal.membership_root,
        membership_snapshot_root=proposal.membership_snapshot_root,
        membership_epoch_state_root=proposal.membership_epoch_state_root,
        threshold_root=proposal.threshold_root,
        replay_state_ref=proposal.replay_state_root,
        replay_root=proposal.replay_root,
        support_replay_state_root=proposal.support_replay_state_root,
        support_replay_root=proposal.support_replay_root,
        collective_evidence_root=proposal.evidence_root,
        collective_challenge_root=proposal.challenge_root,
        collective_lease_root=proposal.lease_root,
        candidate_evidence_root=proposal.candidate_evidence_root,
        candidate_challenge_root=proposal.candidate_challenge_root,
        candidate_lease_root=proposal.candidate_lease_root,
        stop_resolution_root=proposal.stop_resolution_root,
        permission_root=proposal.permission_root,
        verified_at_step=current,
        verifier_id=require_commit_text(
            verifier_id,
            "distributed finality verifier_id",
        ),
        authority=authority,
        provenance=require_commit_text(
            provenance,
            "distributed finality provenance",
        ),
        trace_event_id=require_commit_text(
            trace_event_id,
            "distributed finality trace_event_id",
        ),
    )


def _validate_distributed_commit_certificate(
    certificate: DistributedCommitCertificate,
) -> None:
    if certificate.schema_discriminator != (
        DISTRIBUTED_COMMIT_CERTIFICATE_DISCRIMINATOR
    ):
        raise GovernanceError("distributed certificate discriminator is invalid")
    if certificate.certificate_version != DISTRIBUTED_COMMIT_CERTIFICATE_VERSION:
        raise GovernanceError("distributed certificate version is unsupported")
    if certificate.wire_version != COMMIT_WIRE_VERSION:
        raise GovernanceError("distributed certificate wire version is unsupported")
    if certificate.canonicalization != COMMIT_CANONICAL_VERSION:
        raise GovernanceError("distributed certificate canonicalization is unsupported")
    if certificate.hash_algorithm != "sha256":
        raise GovernanceError("distributed certificate hash algorithm is unsupported")
    if certificate.profile != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("distributed certificate profile is invalid")
    if certificate.assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("distributed certificate assurance is invalid")
    if type(certificate.status) is not DistributedCertificateStatus:
        raise GovernanceError("distributed certificate status is invalid")
    for name in (
        "certificate_id",
        "protocol_id",
        "run_id",
        "target",
        "candidate_id",
        "portable_certificate_version",
        "issuer_id",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(certificate, name),
            f"distributed certificate {name}",
        )
    for name in (
        "manifest_root",
        "commit_policy_root",
        "commit_value_root",
        "proposal_digest",
        "membership_snapshot_root",
        "membership_root",
        "witness_root",
        "portable_certificate_ref",
        "certificate_body_root",
        "certificate_root",
    ):
        require_commit_fingerprint(
            getattr(certificate, name),
            f"distributed certificate {name}",
        )
    for name in (
        "epoch",
        "membership_size",
        "max_byzantine_faults",
        "witness_quorum",
        "minimum_failure_domain_diversity",
        "issued_at_step",
    ):
        require_commit_step(
            getattr(certificate, name),
            f"distributed certificate {name}",
        )
    if type(certificate.authority) is not AuthorityLevel or not can_verify(
        certificate.authority
    ):
        raise GovernanceError("distributed certificate lacks issuer authority")
    if type(certificate.proposal) is not DistributedCommitProposal:
        raise GovernanceError("distributed certificate proposal is invalid")
    if type(certificate.membership_snapshot) is not PortableMembershipSnapshot:
        raise GovernanceError("distributed certificate membership is invalid")
    _validate_distributed_commit_proposal(certificate.proposal)
    _validate_portable_membership_snapshot(certificate.membership_snapshot)
    _validate_certificate_proposal_binding(certificate)
    if not _quorum_intersection_is_safe(
        certificate.membership_size,
        certificate.max_byzantine_faults,
        certificate.witness_quorum,
    ):
        raise GovernanceError("distributed certificate quorum intersection is unsafe")
    if certificate.membership_size != len(
        certificate.membership_snapshot.eligible_clusters
    ):
        raise GovernanceError("distributed certificate membership size mismatch")
    if not (
        certificate.membership_snapshot.issued_at_step
        <= certificate.issued_at_step
        < certificate.membership_snapshot.expires_at_step
    ):
        raise GovernanceError(
            "distributed certificate membership was not fresh at issuance"
        )
    if certificate.minimum_failure_domain_diversity > certificate.witness_quorum:
        raise GovernanceError("distributed certificate diversity is unreachable")
    if not certificate.witnesses:
        raise GovernanceError("distributed certificate requires witnesses")
    cluster_ids = tuple(
        item.witness.principal_cluster_id for item in certificate.witnesses
    )
    if len(cluster_ids) != len(set(cluster_ids)):
        raise GovernanceError("distributed certificate counts a cluster twice")
    if set(cluster_ids).intersection(certificate.excluded_cluster_ids):
        raise GovernanceError("distributed certificate counts equivocated clusters")
    for verification in certificate.witnesses:
        if (
            verification.witness.proposal_digest != certificate.proposal_digest
            or verification.witness.commit_value_root != certificate.commit_value_root
        ):
            raise GovernanceError("distributed certificate witness proposal mismatch")
    expected_witness_root = _witness_verification_root(
        certificate.witnesses,
        profile=certificate.profile,
        commit_value_root=certificate.commit_value_root,
        proposal_digest=certificate.proposal_digest,
    )
    if certificate.witness_root != expected_witness_root:
        raise GovernanceError("distributed certificate witness root is invalid")
    meets_finality = bool(
        len(cluster_ids) >= certificate.witness_quorum
        and len({item.witness.failure_domain for item in certificate.witnesses})
        >= certificate.minimum_failure_domain_diversity
    )
    if (certificate.status is DistributedCertificateStatus.FINAL) is not meets_finality:
        raise GovernanceError("distributed certificate status misrepresents quorum")
    expected_body = _distributed_certificate_body_root(
        _distributed_certificate_body_payload(certificate),
        profile=certificate.profile,
    )
    if certificate.certificate_body_root != expected_body:
        raise GovernanceError("distributed certificate body root is invalid")
    expected_root = commit_payload_fingerprint(
        {
            "certificate_body_root": expected_body,
            "commit_value_root": certificate.commit_value_root,
            "proposal_digest": certificate.proposal_digest,
            "witness_root": certificate.witness_root,
        },
        schema="pheroos-distributed-commit-certificate-envelope-v1",
        profile=certificate.profile,
    )
    if certificate.certificate_root != expected_root:
        raise GovernanceError("distributed certificate envelope root is invalid")


def _distributed_certificate_body_payload(
    certificate: DistributedCommitCertificate,
) -> dict[str, object]:
    payload = _public_dataclass_payload(certificate)
    payload.pop("certificate_body_root")
    payload.pop("certificate_root")
    payload["proposal"] = distributed_commit_proposal_payload(certificate.proposal)
    payload["membership_snapshot"] = portable_membership_snapshot_payload(
        certificate.membership_snapshot
    )
    payload["witnesses"] = tuple(
        witness_verification_payload(item) for item in certificate.witnesses
    )
    return payload


def _distributed_certificate_body_root(
    body: Mapping[str, object],
    *,
    profile: str,
) -> str:
    normalized = dict(body)
    proposal = normalized.get("proposal")
    if type(proposal) is DistributedCommitProposal:
        normalized["proposal"] = distributed_commit_proposal_payload(proposal)
    membership = normalized.get("membership_snapshot")
    if type(membership) is PortableMembershipSnapshot:
        normalized["membership_snapshot"] = portable_membership_snapshot_payload(
            membership
        )
    witness_values = normalized.get("witnesses")
    if witness_values is not None:
        normalized["witnesses"] = tuple(
            witness_verification_payload(item)
            if type(item) is WitnessVerification
            else item
            for item in _require_sequence(
                witness_values,
                "distributed certificate body witnesses",
            )
        )
    return commit_payload_fingerprint(
        normalized,
        schema="pheroos-distributed-commit-certificate-body-v1",
        profile=profile,
    )


def _register_distributed_certificate_identity(
    certificate: DistributedCommitCertificate,
) -> DistributedCommitCertificate:
    key = (
        certificate.profile,
        certificate.run_id,
        certificate.target,
        certificate.epoch,
        certificate.certificate_id,
    )
    fingerprint = distributed_commit_certificate_fingerprint(certificate)
    with LEGACY_AUTHORITY_REGISTRY.transaction() as registry:
        existing = registry.get(_LEGACY_DISTRIBUTED_CERTIFICATES_BY_ID, key)
        if existing is not None:
            if distributed_commit_certificate_fingerprint(existing) != fingerprint:
                raise GovernanceError(
                    "distributed certificate id replay has a different body"
                )
            return existing
        registry.set(_LEGACY_DISTRIBUTED_CERTIFICATES_BY_ID, key, certificate)
        return certificate


def _coerce_certificate_status(value: object) -> DistributedCertificateStatus:
    if type(value) is DistributedCertificateStatus:
        return value
    try:
        return DistributedCertificateStatus(value)
    except (TypeError, ValueError) as exc:
        raise GovernanceError("distributed certificate status is invalid") from exc


for _name in (
    "DistributedCertificateStatus",
    "DistributedCommitCertificate",
    "issue_distributed_commit_certificate",
    "assemble_portable_distributed_commit_certificate",
    "distributed_commit_certificate_payload",
    "distributed_commit_certificate_fingerprint",
    "distributed_commit_certificate_from_payload",
    "verify_distributed_commit_certificate",
    "distributed_commit_certificate_is_current_final",
    "verify_distributed_commit_finality",
    "_validate_distributed_commit_certificate",
    "_distributed_certificate_body_payload",
    "_distributed_certificate_body_root",
    "_register_distributed_certificate_identity",
    "_coerce_certificate_status",
):
    globals()[_name].__module__ = "pheroos.governance.distributed_commit"
del _name
