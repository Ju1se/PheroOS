from __future__ import annotations

from collections.abc import Mapping, Sequence

from dataclasses import dataclass, field


from pheroos.governance._distributed.invariants import (
    _canonical_fingerprints,
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
)


from pheroos.governance._distributed.records import (
    _DISTRIBUTED_STATE_ISSUANCE,
    _LEGACY_DISTRIBUTED_STATE_CURSORS,
    _DistributedStateCursor,
)

from pheroos.governance._distributed._state_contract import (
    _replace_distributed_state,
    _validate_verification_state_binding,
)


from pheroos.governance._commit_validation import (
    require_commit_bool,
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_step,
    require_commit_text,
)

from pheroos.governance._legacy.authority_registry import (
    LEGACY_AUTHORITY_REGISTRY,
)

from pheroos.governance.authority import AuthorityLevel, can_verify


from pheroos.governance.commit_numeric import commit_payload_fingerprint

from pheroos.governance.errors import GovernanceError


from pheroos.protocol.commit_models import (
    DISTRIBUTED_COMMIT_PROFILE_VERSION,
    CollectiveCommitPolicy,
    CommitAssurance,
)


from pheroos.governance._distributed.constants import (
    DISTRIBUTED_STATE_VERSION,
)
from pheroos.governance._support.records import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    eligible_membership_epoch_state_fingerprint,
)
from pheroos.governance._support.membership import (
    eligible_membership_epoch_state_is_current,
    eligible_principal_snapshot_matches,
)

from pheroos.governance._distributed.membership import (
    PortableMembershipSnapshot,
    portable_membership_snapshot_from_eligible,
    portable_membership_snapshot_payload,
    portable_membership_snapshot_from_payload,
)


from pheroos.governance._distributed.witness import (
    WitnessVerification,
    WitnessEquivocationFinding,
    witness_verification_payload,
    witness_verification_fingerprint,
    witness_verification_is_authoritative,
    witness_verification_from_payload,
    witness_replay_receipt,
    witness_replay_receipt_portable,
    _canonical_witness_verifications,
    _witness_receipt_root,
    _witness_equivocation_findings,
    _equivocation_finding_from_payload,
)


@dataclass(frozen=True)
class FinalCertificateRegistration:
    certificate_ref: str
    commit_value_root: str
    proposal_digest: str
    candidate_id: str
    registered_at_step: int

    def __post_init__(self) -> None:
        require_commit_fingerprint(
            self.certificate_ref,
            "distributed registration certificate_ref",
        )
        require_commit_fingerprint(
            self.commit_value_root,
            "distributed registration commit_value_root",
        )
        require_commit_fingerprint(
            self.proposal_digest,
            "distributed registration proposal_digest",
        )
        require_commit_text(
            self.candidate_id,
            "distributed registration candidate_id",
        )
        require_commit_step(
            self.registered_at_step,
            "distributed registration registered_at_step",
        )


@dataclass(frozen=True)
class CertificateConflictFinding:
    finding_id: str
    target: str
    epoch: int
    certificate_refs: tuple[str, ...]
    commit_value_roots: tuple[str, ...]
    proposal_digests: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    detected_at_step: int

    def __post_init__(self) -> None:
        require_commit_fingerprint(self.finding_id, "certificate conflict finding_id")
        require_commit_text(self.target, "certificate conflict target")
        require_commit_step(self.epoch, "certificate conflict epoch")
        object.__setattr__(
            self,
            "certificate_refs",
            _canonical_fingerprints(
                self.certificate_refs,
                "certificate conflict refs",
            ),
        )
        object.__setattr__(
            self,
            "commit_value_roots",
            _canonical_fingerprints(
                self.commit_value_roots,
                "certificate conflict commit value roots",
            ),
        )
        object.__setattr__(
            self,
            "proposal_digests",
            _canonical_fingerprints(
                self.proposal_digests,
                "certificate conflict proposal digests",
            ),
        )
        object.__setattr__(
            self,
            "candidate_ids",
            require_commit_labels(
                self.candidate_ids,
                "certificate conflict candidate ids",
            ),
        )
        require_commit_step(
            self.detected_at_step,
            "certificate conflict detected_at_step",
        )
        if len(self.certificate_refs) < 2 or len(self.commit_value_roots) < 2:
            raise GovernanceError("certificate conflict requires two final proofs")


@dataclass(frozen=True)
class DistributedCommitState:
    chain_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    membership_snapshot: PortableMembershipSnapshot
    membership_snapshot_root: str
    membership_epoch_state_root: str
    membership_root: str
    membership_size: int
    max_byzantine_faults: int
    witness_quorum: int
    witness_ttl_steps: int
    minimum_failure_domain_diversity: int
    revision: int
    initialized_at_step: int
    current_step: int
    previous_state_fingerprint: str
    witness_verifications: tuple[WitnessVerification, ...]
    witness_receipt_root: str
    equivocation_findings: tuple[WitnessEquivocationFinding, ...]
    excluded_cluster_ids: tuple[str, ...]
    final_registrations: tuple[FinalCertificateRegistration, ...]
    conflict_findings: tuple[CertificateConflictFinding, ...]
    frozen: bool
    transitioned: bool
    epoch_transition_certificate_ref: str
    issuer_id: str
    authority: AuthorityLevel
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _cursor: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "witness_verifications",
            _canonical_witness_verifications(self.witness_verifications),
        )
        object.__setattr__(
            self,
            "equivocation_findings",
            tuple(sorted(self.equivocation_findings, key=lambda item: item.finding_id)),
        )
        object.__setattr__(
            self,
            "excluded_cluster_ids",
            require_commit_labels(
                self.excluded_cluster_ids,
                "distributed state excluded clusters",
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "final_registrations",
            tuple(
                sorted(
                    self.final_registrations,
                    key=lambda item: item.certificate_ref,
                )
            ),
        )
        object.__setattr__(
            self,
            "conflict_findings",
            tuple(sorted(self.conflict_findings, key=lambda item: item.finding_id)),
        )
        _validate_distributed_commit_state(self)


def initialize_distributed_commit_state(
    membership_snapshot: EligiblePrincipalSnapshot,
    membership_epoch_state: EligibleMembershipEpochState,
    *,
    commit_policy: CollectiveCommitPolicy,
    current_step: int,
    issuer_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
) -> DistributedCommitState:
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError(
            "distributed state initialization requires governance authority"
        )
    current = require_commit_step(
        current_step,
        "distributed state current_step",
    )
    if not eligible_membership_epoch_state_is_current(membership_epoch_state):
        raise GovernanceError("distributed state membership epoch is not current")
    if not eligible_principal_snapshot_matches(
        membership_snapshot,
        epoch_state=membership_epoch_state,
        profile=membership_snapshot.profile,
        assurance=membership_snapshot.assurance,
        manifest_root=membership_snapshot.manifest_root,
        commit_policy_root=membership_snapshot.commit_policy_root,
        protocol_id=membership_snapshot.protocol_id,
        run_id=membership_snapshot.run_id,
        target=membership_snapshot.target,
        epoch=membership_snapshot.epoch,
        current_step=current,
    ):
        raise GovernanceError("distributed state membership is not authoritative")
    distributed = _validate_distributed_policy(
        commit_policy,
        profile=membership_snapshot.profile,
        assurance=membership_snapshot.assurance,
        target=membership_snapshot.target,
        commit_policy_root=membership_snapshot.commit_policy_root,
    )
    portable = portable_membership_snapshot_from_eligible(membership_snapshot)
    _validate_membership_policy(portable, distributed)
    membership_epoch_ref = eligible_membership_epoch_state_fingerprint(
        membership_epoch_state
    )
    authority_key = commit_payload_fingerprint(
        {
            "commit_policy_root": portable.commit_policy_root,
            "epoch": portable.epoch,
            "manifest_root": portable.manifest_root,
            "membership_root": portable.membership_root,
            "profile": portable.profile,
            "protocol_id": portable.protocol_id,
            "run_id": portable.run_id,
            "target": portable.target,
        },
        schema="pheroos-distributed-state-authority-key-v1",
        profile=portable.profile,
    )
    base_fingerprint = commit_payload_fingerprint(
        {
            "authority": authority,
            "authority_key": authority_key,
            "initialized_at_step": current,
            "issuer_id": require_commit_text(
                issuer_id,
                "distributed state issuer_id",
            ),
            "membership_epoch_state_root": membership_epoch_ref,
            "membership_snapshot_root": portable.snapshot_fingerprint,
            "provenance": require_commit_text(
                provenance,
                "distributed state provenance",
            ),
            "trace_event_id": require_commit_text(
                trace_event_id,
                "distributed state trace_event_id",
            ),
        },
        schema="pheroos-distributed-state-base-v1",
        profile=portable.profile,
    )
    with LEGACY_AUTHORITY_REGISTRY.transaction() as registry:
        cursor = registry.get(_LEGACY_DISTRIBUTED_STATE_CURSORS, authority_key)
        if cursor is not None:
            if cursor.base_fingerprint != base_fingerprint:
                raise GovernanceError(
                    "distributed state authority already has a different base"
                )
            if not distributed_commit_state_is_current(cursor.current_state):
                raise GovernanceError("distributed state current head is unavailable")
            assert cursor.current_state is not None
            return cursor.current_state
        cursor = _DistributedStateCursor(
            authority_key=authority_key,
            base_fingerprint=base_fingerprint,
        )
        state = DistributedCommitState(
            chain_id=authority_key,
            profile=portable.profile,
            assurance=portable.assurance,
            manifest_root=portable.manifest_root,
            commit_policy_root=portable.commit_policy_root,
            protocol_id=portable.protocol_id,
            run_id=portable.run_id,
            target=portable.target,
            epoch=portable.epoch,
            membership_snapshot=portable,
            membership_snapshot_root=portable.snapshot_fingerprint,
            membership_epoch_state_root=membership_epoch_ref,
            membership_root=portable.membership_root,
            membership_size=distributed.membership_size,
            max_byzantine_faults=distributed.max_byzantine_faults,
            witness_quorum=distributed.witness_quorum,
            witness_ttl_steps=distributed.witness_ttl_steps,
            minimum_failure_domain_diversity=(
                distributed.minimum_failure_domain_diversity
            ),
            revision=0,
            initialized_at_step=current,
            current_step=current,
            previous_state_fingerprint="",
            witness_verifications=(),
            witness_receipt_root=_witness_receipt_root(
                (),
                profile=portable.profile,
            ),
            equivocation_findings=(),
            excluded_cluster_ids=(),
            final_registrations=(),
            conflict_findings=(),
            frozen=False,
            transitioned=False,
            epoch_transition_certificate_ref="",
            issuer_id=issuer_id,
            authority=authority,
            provenance=provenance,
            trace_event_id=trace_event_id,
        )
        state = _issue_distributed_state(state, cursor)
        cursor.current_state = state
        cursor.current_state_fingerprint = distributed_commit_state_fingerprint(state)
        registry.set(_LEGACY_DISTRIBUTED_STATE_CURSORS, authority_key, cursor)
        return state


def record_witness_verifications(
    state: DistributedCommitState,
    verifications: Sequence[WitnessVerification],
    *,
    current_step: int,
) -> DistributedCommitState:
    if not distributed_commit_state_is_authoritative(state):
        raise GovernanceError("distributed witness state is not governance-issued")
    if state.frozen:
        raise GovernanceError("distributed epoch is frozen after certificate conflict")
    if state.transitioned:
        raise GovernanceError("distributed epoch has already transitioned")
    current = require_commit_step(
        current_step,
        "distributed witness state current_step",
    )
    if current < state.current_step:
        raise GovernanceError("distributed witness state cannot move backwards")
    incoming = _canonical_witness_verifications(verifications)
    if not incoming:
        return _current_distributed_state_head(state)
    for verification in incoming:
        if not witness_verification_is_authoritative(verification):
            raise GovernanceError(
                "distributed state cannot record a forged witness verification"
            )
        _validate_verification_state_binding(verification, state)
        if not (
            verification.verified_at_step <= current < verification.expires_at_step
        ):
            raise GovernanceError(
                "distributed state cannot record a stale witness verification"
            )

    existing_by_fingerprint = {
        witness_verification_fingerprint(item): item
        for item in state.witness_verifications
    }
    existing_by_id = {
        item.verification_id: item for item in state.witness_verifications
    }
    existing_by_nonce = {
        item.witness.nonce: item for item in state.witness_verifications
    }
    additions: list[WitnessVerification] = []
    for verification in incoming:
        fingerprint = witness_verification_fingerprint(verification)
        collisions = tuple(
            item
            for item in (
                existing_by_id.get(verification.verification_id),
                existing_by_nonce.get(verification.witness.nonce),
            )
            if item is not None
        )
        if collisions:
            if any(
                witness_verification_fingerprint(item) != fingerprint
                for item in collisions
            ):
                raise GovernanceError(
                    "witness verification id/nonce collision is a safety violation"
                )
            continue
        if fingerprint in existing_by_fingerprint:
            continue
        additions.append(verification)
        existing_by_fingerprint[fingerprint] = verification
        existing_by_id[verification.verification_id] = verification
        existing_by_nonce[verification.witness.nonce] = verification
    if not additions:
        return _current_distributed_state_head(state)

    combined = _canonical_witness_verifications(
        (*state.witness_verifications, *additions)
    )
    findings = _witness_equivocation_findings(
        combined,
        profile=state.profile,
        target=state.target,
        epoch=state.epoch,
    )
    excluded = tuple(item.principal_cluster_id for item in findings)
    parent_ref = distributed_commit_state_fingerprint(state)
    request_ref = commit_payload_fingerprint(
        {
            "current_step": current,
            "parent_state_ref": parent_ref,
            "verification_refs": tuple(
                witness_verification_fingerprint(item) for item in additions
            ),
        },
        schema="pheroos-distributed-witness-record-request-v1",
        profile=state.profile,
    )
    cursor = state._cursor
    if type(cursor) is not _DistributedStateCursor:
        raise GovernanceError("distributed state cursor is invalid")
    with cursor.lock:
        if cursor.current_state_fingerprint != parent_ref:
            prior = cursor.transitions.get(parent_ref)
            if prior is not None and prior[0] == request_ref:
                return prior[1]
            raise GovernanceError("distributed witness state is stale or would fork")
        next_state = _replace_distributed_state(
            state,
            revision=state.revision + 1,
            current_step=current,
            previous_state_fingerprint=parent_ref,
            witness_verifications=combined,
            witness_receipt_root=_witness_receipt_root(
                tuple(witness_replay_receipt(item) for item in combined),
                profile=state.profile,
            ),
            equivocation_findings=findings,
            excluded_cluster_ids=excluded,
        )
        next_state = _issue_distributed_state(next_state, cursor)
        cursor.current_state = next_state
        cursor.current_state_fingerprint = distributed_commit_state_fingerprint(
            next_state
        )
        cursor.transitions[parent_ref] = (request_ref, next_state)
        return next_state


def distributed_commit_state_payload(
    state: DistributedCommitState,
) -> dict[str, object]:
    if type(state) is not DistributedCommitState:
        raise GovernanceError("distributed state must use the canonical record")
    _validate_distributed_commit_state(state)
    payload = _public_dataclass_payload(state)
    payload["membership_snapshot"] = portable_membership_snapshot_payload(
        state.membership_snapshot
    )
    payload["witness_verifications"] = tuple(
        witness_verification_payload(item) for item in state.witness_verifications
    )
    payload["equivocation_findings"] = tuple(
        _public_dataclass_payload(item) for item in state.equivocation_findings
    )
    payload["final_registrations"] = tuple(
        _public_dataclass_payload(item) for item in state.final_registrations
    )
    payload["conflict_findings"] = tuple(
        _public_dataclass_payload(item) for item in state.conflict_findings
    )
    return payload


def distributed_commit_state_fingerprint(state: DistributedCommitState) -> str:
    return commit_payload_fingerprint(
        distributed_commit_state_payload(state),
        schema=DISTRIBUTED_STATE_VERSION,
        profile=state.profile,
    )


def distributed_commit_state_from_payload(
    payload: Mapping[str, object],
) -> DistributedCommitState:
    values = _strict_dataclass_payload(
        payload,
        DistributedCommitState,
        "distributed state payload",
    )
    values["assurance"] = _coerce_assurance(values["assurance"])
    values["authority"] = _coerce_authority(values["authority"])
    values["membership_snapshot"] = portable_membership_snapshot_from_payload(
        values["membership_snapshot"]
    )
    values["witness_verifications"] = tuple(
        witness_verification_from_payload(item)
        for item in _require_sequence(
            values["witness_verifications"],
            "distributed state witness verifications",
        )
    )
    values["equivocation_findings"] = tuple(
        _equivocation_finding_from_payload(item)
        for item in _require_sequence(
            values["equivocation_findings"],
            "distributed state equivocation findings",
        )
    )
    values["excluded_cluster_ids"] = tuple(
        _require_sequence(
            values["excluded_cluster_ids"],
            "distributed state excluded clusters",
        )
    )
    values["final_registrations"] = tuple(
        FinalCertificateRegistration(
            **_strict_dataclass_payload(
                item,
                FinalCertificateRegistration,
                "distributed final registration payload",
            )
        )
        for item in _require_sequence(
            values["final_registrations"],
            "distributed state final registrations",
        )
    )
    values["conflict_findings"] = tuple(
        _conflict_finding_from_payload(item)
        for item in _require_sequence(
            values["conflict_findings"],
            "distributed state conflict findings",
        )
    )
    try:
        return DistributedCommitState(**values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(f"distributed state payload is invalid: {exc}") from exc


def distributed_commit_state_is_authoritative(state: object) -> bool:
    if type(state) is not DistributedCommitState:
        return False
    try:
        issuance = state._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _DISTRIBUTED_STATE_ISSUANCE
            and issuance[1] == distributed_commit_state_fingerprint(state)
            and type(state._cursor) is _DistributedStateCursor
        )
    except Exception:
        return False


def distributed_commit_state_is_current(state: object) -> bool:
    if not distributed_commit_state_is_authoritative(state):
        return False
    assert type(state) is DistributedCommitState
    cursor = state._cursor
    assert type(cursor) is _DistributedStateCursor
    try:
        with cursor.lock:
            return (
                cursor.current_state is state
                and cursor.current_state_fingerprint
                == distributed_commit_state_fingerprint(state)
            )
    except Exception:
        return False


def _validate_distributed_commit_state(state: DistributedCommitState) -> None:
    if state.profile != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("distributed state profile is invalid")
    if state.assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("distributed state assurance is invalid")
    for name in (
        "chain_id",
        "protocol_id",
        "run_id",
        "target",
        "issuer_id",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(getattr(state, name), f"distributed state {name}")
    for name in (
        "manifest_root",
        "commit_policy_root",
        "membership_snapshot_root",
        "membership_epoch_state_root",
        "membership_root",
        "witness_receipt_root",
    ):
        require_commit_fingerprint(
            getattr(state, name),
            f"distributed state {name}",
        )
    if state.previous_state_fingerprint:
        require_commit_fingerprint(
            state.previous_state_fingerprint,
            "distributed state previous_state_fingerprint",
        )
    if state.epoch_transition_certificate_ref:
        require_commit_fingerprint(
            state.epoch_transition_certificate_ref,
            "distributed state epoch transition certificate ref",
        )
    for name in (
        "epoch",
        "membership_size",
        "max_byzantine_faults",
        "witness_quorum",
        "witness_ttl_steps",
        "minimum_failure_domain_diversity",
        "revision",
        "initialized_at_step",
        "current_step",
    ):
        require_commit_step(getattr(state, name), f"distributed state {name}")
    if type(state.authority) is not AuthorityLevel or not can_verify(state.authority):
        raise GovernanceError("distributed state lacks governance authority")
    for name in ("frozen", "transitioned"):
        require_commit_bool(getattr(state, name), f"distributed state {name}")
    if not _quorum_intersection_is_safe(
        state.membership_size,
        state.max_byzantine_faults,
        state.witness_quorum,
    ):
        raise GovernanceError("distributed state quorum intersection is unsafe")
    if state.minimum_failure_domain_diversity > state.witness_quorum:
        raise GovernanceError("distributed state failure diversity is unreachable")
    if (
        state.membership_snapshot.snapshot_fingerprint
        != (state.membership_snapshot_root)
        or state.membership_snapshot.membership_root != state.membership_root
    ):
        raise GovernanceError("distributed state membership lineage mismatch")
    if state.membership_size != len(state.membership_snapshot.eligible_clusters):
        raise GovernanceError("distributed state membership size mismatch")
    expected_receipt_root = _witness_receipt_root(
        tuple(
            witness_replay_receipt_portable(item)
            for item in state.witness_verifications
        ),
        profile=state.profile,
    )
    if state.witness_receipt_root != expected_receipt_root:
        raise GovernanceError("distributed state witness receipt root is invalid")
    expected_findings = _witness_equivocation_findings(
        state.witness_verifications,
        profile=state.profile,
        target=state.target,
        epoch=state.epoch,
    )
    if state.equivocation_findings != expected_findings:
        raise GovernanceError("distributed state equivocation findings are incomplete")
    if set(state.excluded_cluster_ids) != {
        item.principal_cluster_id for item in state.equivocation_findings
    }:
        raise GovernanceError("distributed state equivocation exclusions are invalid")
    semantic_conflict = (
        len({item.commit_value_root for item in state.final_registrations}) > 1
    )
    if (
        state.frozen is not bool(state.conflict_findings)
        or state.frozen is not semantic_conflict
    ):
        raise GovernanceError("distributed state freeze/conflict invariant is invalid")
    registered_refs = {item.certificate_ref for item in state.final_registrations}
    registered_values = {item.commit_value_root for item in state.final_registrations}
    for finding in state.conflict_findings:
        if not set(finding.certificate_refs).issubset(registered_refs) or not set(
            finding.commit_value_roots
        ).issubset(registered_values):
            raise GovernanceError(
                "distributed state conflict lineage is not registered"
            )
    if state.transitioned is not bool(state.epoch_transition_certificate_ref):
        raise GovernanceError("distributed state transition invariant is invalid")
    for item in state.witness_verifications:
        _validate_verification_state_binding(item, state)


def _certificate_conflict_finding(
    registrations: Sequence[FinalCertificateRegistration],
    *,
    profile: str,
    target: str,
    epoch: int,
    current_step: int,
) -> CertificateConflictFinding:
    certificate_refs = tuple(sorted({item.certificate_ref for item in registrations}))
    commit_value_roots = tuple(
        sorted({item.commit_value_root for item in registrations})
    )
    proposal_digests = tuple(sorted({item.proposal_digest for item in registrations}))
    candidate_ids = tuple(sorted({item.candidate_id for item in registrations}))
    finding_id = commit_payload_fingerprint(
        {
            "certificate_refs": certificate_refs,
            "commit_value_roots": commit_value_roots,
            "epoch": epoch,
            "proposal_digests": proposal_digests,
            "target": target,
        },
        schema="pheroos-distributed-certificate-conflict-v1",
        profile=profile,
    )
    return CertificateConflictFinding(
        finding_id=finding_id,
        target=target,
        epoch=epoch,
        certificate_refs=certificate_refs,
        commit_value_roots=commit_value_roots,
        proposal_digests=proposal_digests,
        candidate_ids=candidate_ids,
        detected_at_step=current_step,
    )


def _issue_distributed_state(
    state: DistributedCommitState,
    cursor: _DistributedStateCursor,
) -> DistributedCommitState:
    object.__setattr__(state, "_cursor", cursor)
    object.__setattr__(
        state,
        "_issuance",
        (_DISTRIBUTED_STATE_ISSUANCE, distributed_commit_state_fingerprint(state)),
    )
    return state


def _current_distributed_state_head(
    state: DistributedCommitState,
) -> DistributedCommitState:
    if not distributed_commit_state_is_authoritative(state):
        raise GovernanceError("distributed state is not authoritative")
    cursor = state._cursor
    if type(cursor) is not _DistributedStateCursor:
        raise GovernanceError("distributed state cursor is invalid")
    with cursor.lock:
        current = cursor.current_state
        if (
            type(current) is not DistributedCommitState
            or cursor.current_state_fingerprint
            != distributed_commit_state_fingerprint(current)
        ):
            raise GovernanceError("distributed state current head is unavailable")
        return current


def _conflict_finding_from_payload(
    payload: object,
) -> CertificateConflictFinding:
    values = _strict_dataclass_payload(
        payload,
        CertificateConflictFinding,
        "certificate conflict finding payload",
    )
    for name in (
        "certificate_refs",
        "commit_value_roots",
        "proposal_digests",
        "candidate_ids",
    ):
        values[name] = tuple(
            _require_sequence(values[name], f"certificate conflict {name}")
        )
    return CertificateConflictFinding(**values)


for _name in (
    "FinalCertificateRegistration",
    "CertificateConflictFinding",
    "DistributedCommitState",
    "initialize_distributed_commit_state",
    "record_witness_verifications",
    "distributed_commit_state_payload",
    "distributed_commit_state_fingerprint",
    "distributed_commit_state_from_payload",
    "distributed_commit_state_is_authoritative",
    "distributed_commit_state_is_current",
    "_validate_distributed_commit_state",
    "_certificate_conflict_finding",
    "_issue_distributed_state",
    "_current_distributed_state_head",
    "_conflict_finding_from_payload",
):
    globals()[_name].__module__ = "pheroos.governance.distributed_commit"
del _name
