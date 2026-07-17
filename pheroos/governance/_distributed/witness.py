from __future__ import annotations

from collections.abc import Mapping, Sequence

from dataclasses import dataclass, field


from pheroos.governance._distributed.invariants import (
    _canonical_fingerprints,
    _coerce_assurance,
    _coerce_authority,
    _public_dataclass_payload,
    _require_sequence,
    _strict_dataclass_payload,
    _validate_distributed_policy,
)

from pheroos.governance._distributed._membership_contract import (
    _portable_member,
    _validate_membership_policy,
)


from pheroos.governance._distributed.records import (
    _LEGACY_WITNESS_VERIFICATIONS_BY_ID,
    _LEGACY_WITNESS_VERIFICATIONS_BY_NONCE,
    _WITNESS_VERIFICATION_ISSUANCE,
)

from pheroos.governance._distributed._witness_contract import (
    _attestation_matches,
    _validate_witness_proposal_binding,
    validate_quorum_witness as _validate_quorum_witness_engine,
)

from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)

from pheroos.governance._legacy.authority_registry import (
    LEGACY_AUTHORITY_REGISTRY,
)

from pheroos.governance.authority import AuthorityLevel, can_verify


from pheroos.governance.commit_numeric import commit_payload_fingerprint

from pheroos.governance.errors import GovernanceError


from pheroos.governance.principal import (
    PrincipalVerification,
    principal_verification_fingerprint,
    principal_verification_is_authoritative,
    principal_verification_matches,
)


from pheroos.protocol.commit_models import (
    CollectiveCommitPolicy,
    CommitAssurance,
)


from pheroos.governance._distributed.constants import (
    QUORUM_WITNESS_VERSION,
    WITNESS_VERIFICATION_VERSION,
)
from pheroos.governance._support.records import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
)
from pheroos.governance._support.membership import (
    eligible_principal_snapshot_matches,
)
from pheroos.governance._distributed.membership import (
    PortableMembershipSnapshot,
    portable_membership_snapshot_from_eligible,
)
from pheroos.governance._distributed.proposal import (
    DistributedCommitProposal,
    distributed_commit_proposal_is_authoritative,
)


def _validate_quorum_witness(witness: QuorumWitness) -> None:
    _validate_quorum_witness_engine(
        witness,
        witness_version=QUORUM_WITNESS_VERSION,
    )


@dataclass(frozen=True)
class QuorumWitness:
    witness_version: str
    witness_id: str
    profile: str
    assurance: CommitAssurance
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    candidate_id: str
    membership_root: str
    commit_value_root: str
    proposal_digest: str
    principal_id: str
    principal_cluster_id: str
    failure_domain: str
    nonce: str
    witnessed_at_step: int
    expires_at_step: int
    provenance: str
    trace_event_id: str
    attestation_ref: str

    def __post_init__(self) -> None:
        _validate_quorum_witness(self)


@dataclass(frozen=True)
class WitnessVerification:
    verification_version: str
    verification_id: str
    witness: QuorumWitness
    witness_fingerprint: str
    witness_signing_root: str
    principal_verification_ref: str
    verified_at_step: int
    expires_at_step: int
    verifier_id: str
    authority: AuthorityLevel
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _validate_witness_verification(self)


@dataclass(frozen=True)
class WitnessReplayReceipt:
    verification_id: str
    witness_id: str
    nonce: str
    witness_fingerprint: str
    commit_value_root: str
    proposal_digest: str
    target: str
    candidate_id: str
    epoch: int
    principal_id: str
    principal_cluster_id: str

    def __post_init__(self) -> None:
        for name in (
            "verification_id",
            "witness_id",
            "nonce",
            "target",
            "candidate_id",
            "principal_id",
            "principal_cluster_id",
        ):
            require_commit_text(
                getattr(self, name),
                f"witness replay receipt {name}",
            )
        for name in (
            "witness_fingerprint",
            "commit_value_root",
            "proposal_digest",
        ):
            require_commit_fingerprint(
                getattr(self, name),
                f"witness replay receipt {name}",
            )
        require_commit_step(self.epoch, "witness replay receipt epoch")


@dataclass(frozen=True)
class WitnessEquivocationFinding:
    finding_id: str
    target: str
    epoch: int
    principal_cluster_id: str
    commit_value_roots: tuple[str, ...]
    proposal_digests: tuple[str, ...]
    witness_fingerprints: tuple[str, ...]

    def __post_init__(self) -> None:
        require_commit_fingerprint(self.finding_id, "witness equivocation finding_id")
        require_commit_text(self.target, "witness equivocation target")
        require_commit_step(self.epoch, "witness equivocation epoch")
        require_commit_text(
            self.principal_cluster_id,
            "witness equivocation principal_cluster_id",
        )
        object.__setattr__(
            self,
            "commit_value_roots",
            _canonical_fingerprints(
                self.commit_value_roots,
                "witness equivocation commit value roots",
            ),
        )
        object.__setattr__(
            self,
            "proposal_digests",
            _canonical_fingerprints(
                self.proposal_digests,
                "witness equivocation proposal digests",
            ),
        )
        object.__setattr__(
            self,
            "witness_fingerprints",
            _canonical_fingerprints(
                self.witness_fingerprints,
                "witness equivocation fingerprints",
            ),
        )
        if len(self.commit_value_roots) < 2:
            raise GovernanceError(
                "witness equivocation requires conflicting commit values"
            )


def quorum_witness_signing_payload(witness: QuorumWitness) -> dict[str, object]:
    if type(witness) is not QuorumWitness:
        raise GovernanceError("quorum witness must use the canonical record")
    _validate_quorum_witness(witness)
    payload = _public_dataclass_payload(witness)
    payload.pop("attestation_ref")
    return payload


def quorum_witness_signing_root(witness: QuorumWitness) -> str:
    return commit_payload_fingerprint(
        quorum_witness_signing_payload(witness),
        schema="pheroos-quorum-witness-signing-v1",
        profile=witness.profile,
    )


def quorum_witness_payload(witness: QuorumWitness) -> dict[str, object]:
    if type(witness) is not QuorumWitness:
        raise GovernanceError("quorum witness must use the canonical record")
    _validate_quorum_witness(witness)
    return _public_dataclass_payload(witness)


def quorum_witness_fingerprint(witness: QuorumWitness) -> str:
    return commit_payload_fingerprint(
        quorum_witness_payload(witness),
        schema=QUORUM_WITNESS_VERSION,
        profile=witness.profile,
    )


def quorum_witness_from_payload(payload: Mapping[str, object]) -> QuorumWitness:
    values = _strict_dataclass_payload(
        payload,
        QuorumWitness,
        "quorum witness payload",
    )
    values["assurance"] = _coerce_assurance(values["assurance"])
    try:
        return QuorumWitness(**values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(f"quorum witness payload is invalid: {exc}") from exc


def verify_quorum_witness(
    witness: QuorumWitness,
    proposal: DistributedCommitProposal,
    principal_verification: PrincipalVerification,
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    *,
    commit_policy: CollectiveCommitPolicy,
    trusted_witness_attestations: Mapping[str, str],
    verification_id: str,
    verifier_id: str,
    authority: AuthorityLevel,
    verified_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> WitnessVerification:
    """Turn an untrusted witness proposal into governance-issued authority."""

    if type(witness) is not QuorumWitness:
        raise GovernanceError("witness proposal must use QuorumWitness")
    if not distributed_commit_proposal_is_authoritative(proposal):
        raise GovernanceError(
            "witness verification requires a governance-issued proposal"
        )
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("witness verification requires governance authority")
    distributed = _validate_distributed_policy(
        commit_policy,
        profile=proposal.profile,
        assurance=proposal.assurance,
        target=proposal.target,
        commit_policy_root=proposal.commit_policy_root,
    )
    current = require_commit_step(
        verified_at_step,
        "witness verification verified_at_step",
    )
    _validate_witness_proposal_binding(witness, proposal)
    if witness.expires_at_step - witness.witnessed_at_step > (
        distributed.witness_ttl_steps
    ):
        raise GovernanceError("quorum witness exceeds the declared witness TTL")
    if not (witness.witnessed_at_step <= current < witness.expires_at_step):
        raise GovernanceError("quorum witness is stale at verification")
    if not eligible_principal_snapshot_matches(
        membership_snapshot,
        epoch_state=membership_epoch_state,
        profile=proposal.profile,
        assurance=proposal.assurance,
        manifest_root=proposal.manifest_root,
        commit_policy_root=proposal.commit_policy_root,
        protocol_id=proposal.protocol_id,
        run_id=proposal.run_id,
        target=proposal.target,
        epoch=proposal.epoch,
        current_step=current,
    ):
        raise GovernanceError("witness membership is not authoritative and fresh")
    portable = portable_membership_snapshot_from_eligible(membership_snapshot)
    _validate_membership_policy(portable, distributed)
    member = _portable_member(portable, witness.principal_id)
    if member is None:
        raise GovernanceError("quorum witness principal is outside membership")
    cluster_id, portable_principal = member
    if (
        cluster_id != witness.principal_cluster_id
        or portable_principal.failure_domain != witness.failure_domain
    ):
        raise GovernanceError("quorum witness cluster/failure-domain mismatch")
    if not principal_verification_is_authoritative(principal_verification):
        raise GovernanceError("quorum witness principal verification is forged")
    principal_ref = principal_verification_fingerprint(principal_verification)
    if (
        principal_ref != portable_principal.principal_verification_fingerprint
        or not principal_verification_matches(
            principal_verification,
            profile=proposal.profile,
            assurance=proposal.assurance,
            manifest_root=proposal.manifest_root,
            commit_policy_root=proposal.commit_policy_root,
            protocol_id=proposal.protocol_id,
            run_id=proposal.run_id,
            target=proposal.target,
            epoch=proposal.epoch,
            principal_id=witness.principal_id,
            current_step=current,
        )
    ):
        raise GovernanceError("quorum witness principal verification mismatch")
    signing_root = quorum_witness_signing_root(witness)
    if not _attestation_matches(
        witness.attestation_ref,
        trusted_witness_attestations,
        signing_root,
    ):
        raise GovernanceError("quorum witness attestation verification failed")
    expires = min(
        witness.expires_at_step,
        principal_verification.expires_at_step,
        membership_snapshot.expires_at_step,
    )
    if expires <= current:
        raise GovernanceError("quorum witness verification has no fresh interval")
    verification = WitnessVerification(
        verification_version=WITNESS_VERIFICATION_VERSION,
        verification_id=require_commit_text(
            verification_id,
            "witness verification verification_id",
        ),
        witness=witness,
        witness_fingerprint=quorum_witness_fingerprint(witness),
        witness_signing_root=signing_root,
        principal_verification_ref=principal_ref,
        verified_at_step=current,
        expires_at_step=expires,
        verifier_id=require_commit_text(
            verifier_id,
            "witness verification verifier_id",
        ),
        authority=authority,
        provenance=require_commit_text(
            provenance,
            "witness verification provenance",
        ),
        trace_event_id=require_commit_text(
            trace_event_id,
            "witness verification trace_event_id",
        ),
    )
    fingerprint = witness_verification_fingerprint(verification)
    id_key = (witness.profile, witness.run_id, verification.verification_id)
    nonce_key = (witness.profile, witness.run_id, witness.nonce)
    with LEGACY_AUTHORITY_REGISTRY.transaction() as registry:
        by_id = registry.get(_LEGACY_WITNESS_VERIFICATIONS_BY_ID, id_key)
        by_nonce = registry.get(
            _LEGACY_WITNESS_VERIFICATIONS_BY_NONCE,
            nonce_key,
        )
        for existing in (by_id, by_nonce):
            if existing is None:
                continue
            if witness_verification_fingerprint(existing) != fingerprint:
                raise GovernanceError(
                    "witness id/nonce replay collision is a safety violation"
                )
            return existing
        object.__setattr__(
            verification,
            "_issuance",
            (_WITNESS_VERIFICATION_ISSUANCE, fingerprint),
        )
        registry.set(_LEGACY_WITNESS_VERIFICATIONS_BY_ID, id_key, verification)
        registry.set(
            _LEGACY_WITNESS_VERIFICATIONS_BY_NONCE,
            nonce_key,
            verification,
        )
        return verification


def witness_verification_payload(
    verification: WitnessVerification,
) -> dict[str, object]:
    if type(verification) is not WitnessVerification:
        raise GovernanceError("witness verification must use the canonical record")
    _validate_witness_verification(verification)
    payload = _public_dataclass_payload(verification)
    payload["witness"] = quorum_witness_payload(verification.witness)
    return payload


def witness_verification_fingerprint(
    verification: WitnessVerification,
) -> str:
    return commit_payload_fingerprint(
        witness_verification_payload(verification),
        schema=WITNESS_VERIFICATION_VERSION,
        profile=verification.witness.profile,
    )


def witness_verification_is_authoritative(verification: object) -> bool:
    if type(verification) is not WitnessVerification:
        return False
    try:
        issuance = verification._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _WITNESS_VERIFICATION_ISSUANCE
            and issuance[1] == witness_verification_fingerprint(verification)
        )
    except Exception:
        return False


def witness_verification_from_payload(
    payload: Mapping[str, object],
) -> WitnessVerification:
    values = _strict_dataclass_payload(
        payload,
        WitnessVerification,
        "witness verification payload",
    )
    values["witness"] = quorum_witness_from_payload(values["witness"])
    values["authority"] = _coerce_authority(values["authority"])
    try:
        return WitnessVerification(**values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(
            f"witness verification payload is invalid: {exc}"
        ) from exc


def verify_portable_witness_verification(
    verification_or_payload: WitnessVerification | Mapping[str, object],
    *,
    membership_snapshot: PortableMembershipSnapshot,
    trusted_witness_attestations: Mapping[str, str],
    issued_at_step: int,
) -> bool:
    try:
        verification = (
            verification_or_payload
            if type(verification_or_payload) is WitnessVerification
            else witness_verification_from_payload(verification_or_payload)
        )
        assert type(verification) is WitnessVerification
        current = require_commit_step(
            issued_at_step,
            "portable witness certificate issuance step",
        )
        witness = verification.witness
        if not (
            verification.verified_at_step <= current < verification.expires_at_step
            and witness.witnessed_at_step <= current < witness.expires_at_step
        ):
            return False
        member = _portable_member(membership_snapshot, witness.principal_id)
        if member is None:
            return False
        cluster_id, principal = member
        if (
            cluster_id != witness.principal_cluster_id
            or principal.failure_domain != witness.failure_domain
            or principal.principal_verification_fingerprint
            != verification.principal_verification_ref
        ):
            return False
        if quorum_witness_fingerprint(witness) != verification.witness_fingerprint:
            return False
        signing_root = quorum_witness_signing_root(witness)
        if signing_root != verification.witness_signing_root:
            return False
        return _attestation_matches(
            witness.attestation_ref,
            trusted_witness_attestations,
            signing_root,
        )
    except (AssertionError, TypeError, ValueError, GovernanceError):
        return False


def witness_replay_receipt(
    verification: WitnessVerification,
) -> WitnessReplayReceipt:
    if not witness_verification_is_authoritative(verification):
        raise GovernanceError(
            "witness replay receipt requires authoritative verification"
        )
    witness = verification.witness
    return WitnessReplayReceipt(
        verification_id=verification.verification_id,
        witness_id=witness.witness_id,
        nonce=witness.nonce,
        witness_fingerprint=verification.witness_fingerprint,
        commit_value_root=witness.commit_value_root,
        proposal_digest=witness.proposal_digest,
        target=witness.target,
        candidate_id=witness.candidate_id,
        epoch=witness.epoch,
        principal_id=witness.principal_id,
        principal_cluster_id=witness.principal_cluster_id,
    )


def witness_replay_receipt_payload(
    receipt: WitnessReplayReceipt,
) -> dict[str, object]:
    if type(receipt) is not WitnessReplayReceipt:
        raise GovernanceError("witness replay receipt must use canonical record")
    return _public_dataclass_payload(receipt)


def witness_replay_receipt_from_payload(
    payload: Mapping[str, object],
) -> WitnessReplayReceipt:
    values = _strict_dataclass_payload(
        payload,
        WitnessReplayReceipt,
        "witness replay receipt payload",
    )
    try:
        return WitnessReplayReceipt(**values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(
            f"witness replay receipt payload is invalid: {exc}"
        ) from exc


def witness_replay_receipt_fingerprint(
    receipt: WitnessReplayReceipt,
    *,
    profile: str,
) -> str:
    return commit_payload_fingerprint(
        witness_replay_receipt_payload(receipt),
        schema="pheroos-witness-replay-receipt-v1",
        profile=require_commit_profile(profile, "witness replay profile"),
    )


def _validate_witness_verification(verification: WitnessVerification) -> None:
    if verification.verification_version != WITNESS_VERIFICATION_VERSION:
        raise GovernanceError("witness verification version is unsupported")
    if type(verification.witness) is not QuorumWitness:
        raise GovernanceError("witness verification lacks canonical witness")
    _validate_quorum_witness(verification.witness)
    for name in (
        "verification_id",
        "verifier_id",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(verification, name),
            f"witness verification {name}",
        )
    for name in (
        "witness_fingerprint",
        "witness_signing_root",
        "principal_verification_ref",
    ):
        require_commit_fingerprint(
            getattr(verification, name),
            f"witness verification {name}",
        )
    if verification.witness_fingerprint != quorum_witness_fingerprint(
        verification.witness
    ):
        raise GovernanceError("witness verification witness root mismatch")
    if verification.witness_signing_root != quorum_witness_signing_root(
        verification.witness
    ):
        raise GovernanceError("witness verification signing root mismatch")
    verified = require_commit_step(
        verification.verified_at_step,
        "witness verification verified_at_step",
    )
    expires = require_commit_step(
        verification.expires_at_step,
        "witness verification expires_at_step",
    )
    if expires <= verified or expires > verification.witness.expires_at_step:
        raise GovernanceError("witness verification freshness interval is invalid")
    if type(verification.authority) is not AuthorityLevel or not can_verify(
        verification.authority
    ):
        raise GovernanceError("witness verification lacks governance authority")


def witness_replay_receipt_portable(
    verification: WitnessVerification,
) -> WitnessReplayReceipt:
    """Build a replay leaf without requiring process-local issuance."""

    _validate_witness_verification(verification)
    witness = verification.witness
    return WitnessReplayReceipt(
        verification_id=verification.verification_id,
        witness_id=witness.witness_id,
        nonce=witness.nonce,
        witness_fingerprint=verification.witness_fingerprint,
        commit_value_root=witness.commit_value_root,
        proposal_digest=witness.proposal_digest,
        target=witness.target,
        candidate_id=witness.candidate_id,
        epoch=witness.epoch,
        principal_id=witness.principal_id,
        principal_cluster_id=witness.principal_cluster_id,
    )


def _canonical_witness_verifications(
    values: Sequence[WitnessVerification],
) -> tuple[WitnessVerification, ...]:
    normalized = tuple(values)
    if any(type(item) is not WitnessVerification for item in normalized):
        raise GovernanceError(
            "distributed witnesses must use canonical verification records"
        )
    fingerprints = tuple(witness_verification_fingerprint(item) for item in normalized)
    if len(fingerprints) != len(set(fingerprints)):
        raise GovernanceError("distributed witnesses contain a duplicate")
    return tuple(
        item
        for _, item in sorted(
            zip(fingerprints, normalized, strict=True),
            key=lambda pair: pair[0],
        )
    )


def _witness_receipt_root(
    receipts: Sequence[WitnessReplayReceipt],
    *,
    profile: str,
) -> str:
    fingerprints = tuple(
        sorted(
            witness_replay_receipt_fingerprint(item, profile=profile)
            for item in receipts
        )
    )
    return commit_payload_fingerprint(
        {"receipt_fingerprints": fingerprints},
        schema="pheroos-witness-replay-root-v1",
        profile=profile,
    )


def _witness_verification_root(
    verifications: Sequence[WitnessVerification],
    *,
    profile: str,
    commit_value_root: str,
    proposal_digest: str,
) -> str:
    return commit_payload_fingerprint(
        {
            "commit_value_root": commit_value_root,
            "proposal_digest": proposal_digest,
            "witness_verification_fingerprints": tuple(
                sorted(witness_verification_fingerprint(item) for item in verifications)
            ),
        },
        schema="pheroos-distributed-witness-root-v1",
        profile=profile,
    )


def _witness_equivocation_findings(
    verifications: Sequence[WitnessVerification],
    *,
    profile: str,
    target: str,
    epoch: int,
) -> tuple[WitnessEquivocationFinding, ...]:
    by_cluster: dict[str, list[WitnessVerification]] = {}
    for verification in verifications:
        by_cluster.setdefault(
            verification.witness.principal_cluster_id,
            [],
        ).append(verification)
    findings: list[WitnessEquivocationFinding] = []
    for cluster_id, items in sorted(by_cluster.items()):
        commit_value_roots = tuple(
            sorted({item.witness.commit_value_root for item in items})
        )
        proposal_digests = tuple(
            sorted({item.witness.proposal_digest for item in items})
        )
        if len(commit_value_roots) < 2:
            continue
        witness_refs = tuple(
            sorted(witness_verification_fingerprint(item) for item in items)
        )
        finding_id = commit_payload_fingerprint(
            {
                "epoch": epoch,
                "commit_value_roots": commit_value_roots,
                "principal_cluster_id": cluster_id,
                "proposal_digests": proposal_digests,
                "target": target,
                "witness_fingerprints": witness_refs,
            },
            schema="pheroos-witness-equivocation-finding-v1",
            profile=profile,
        )
        findings.append(
            WitnessEquivocationFinding(
                finding_id=finding_id,
                target=target,
                epoch=epoch,
                principal_cluster_id=cluster_id,
                commit_value_roots=commit_value_roots,
                proposal_digests=proposal_digests,
                witness_fingerprints=witness_refs,
            )
        )
    return tuple(findings)


def _equivocation_finding_from_payload(
    payload: object,
) -> WitnessEquivocationFinding:
    values = _strict_dataclass_payload(
        payload,
        WitnessEquivocationFinding,
        "witness equivocation finding payload",
    )
    for name in ("commit_value_roots", "proposal_digests"):
        values[name] = tuple(
            _require_sequence(
                values[name],
                f"witness equivocation {name}",
            )
        )
    values["witness_fingerprints"] = tuple(
        _require_sequence(
            values["witness_fingerprints"],
            "witness equivocation witness fingerprints",
        )
    )
    return WitnessEquivocationFinding(**values)


for _name in (
    "_validate_quorum_witness",
    "QuorumWitness",
    "WitnessVerification",
    "WitnessReplayReceipt",
    "WitnessEquivocationFinding",
    "quorum_witness_signing_payload",
    "quorum_witness_signing_root",
    "quorum_witness_payload",
    "quorum_witness_fingerprint",
    "quorum_witness_from_payload",
    "verify_quorum_witness",
    "witness_verification_payload",
    "witness_verification_fingerprint",
    "witness_verification_is_authoritative",
    "witness_verification_from_payload",
    "verify_portable_witness_verification",
    "witness_replay_receipt",
    "witness_replay_receipt_payload",
    "witness_replay_receipt_from_payload",
    "witness_replay_receipt_fingerprint",
    "_validate_witness_verification",
    "witness_replay_receipt_portable",
    "_canonical_witness_verifications",
    "_witness_receipt_root",
    "_witness_verification_root",
    "_witness_equivocation_findings",
    "_equivocation_finding_from_payload",
):
    globals()[_name].__module__ = "pheroos.governance.distributed_commit"
del _name
