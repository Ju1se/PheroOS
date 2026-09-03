from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from dataclasses import dataclass


from pheroos.governance._distributed._epoch_contract import _require_action_gate


from pheroos.governance._distributed.invariants import (
    _coerce_assurance,
    _coerce_authority,
    _construct_dataclass,
    _public_dataclass_payload,
    _require_mapping,
    _require_sequence,
    _strict_dataclass_payload,
    _validate_distributed_policy,
)

from pheroos.governance._distributed._membership_contract import (
    _validate_membership_policy,
)


from pheroos.governance._distributed.records import (
    _LEGACY_EPOCH_CERTIFICATES_BY_ID,
    _DistributedStateCursor,
)

from pheroos.governance._distributed._state_contract import (
    _replace_distributed_state,
)

from pheroos.governance._distributed._witness_contract import (
    _require_attestation_bindings,
)

from pheroos.governance._commit_validation import (
    require_commit_bool,
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_step,
    require_commit_text,
)

from pheroos.governance._process_state import PROCESS_STATE

from pheroos.governance.authority import AuthorityLevel, can_verify


from pheroos.governance.commit_numeric import commit_payload_fingerprint

from pheroos.governance.errors import GovernanceError

from pheroos.governance.permission import (
    ActionPermission,
    action_permission_fingerprint,
)


from pheroos.governance.stop_signal import (
    StopResolutionVerification,
    stop_resolution_verification_fingerprint,
)

from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_WIRE_VERSION,
    DISTRIBUTED_COMMIT_PROFILE_VERSION,
    CollectiveCommitPolicy,
    CommitAction,
    CommitAssurance,
    DistributedCommitPolicy,
)


from pheroos.governance._distributed.constants import (
    EPOCH_TRANSITION_CERTIFICATE_VERSION,
    EPOCH_TRANSITION_CERTIFICATE_DISCRIMINATOR,
)
from pheroos.governance._support.records import (
    EligibleMembershipEpochState,
    EligiblePrincipalSnapshot,
    eligible_membership_epoch_state_fingerprint,
    eligible_principal_snapshot_fingerprint,
)
from pheroos.governance._support.membership import (
    eligible_principal_snapshot_matches,
)
from pheroos.governance._distributed.membership import (
    PortableMembershipSnapshot,
    portable_membership_snapshot_from_eligible,
    portable_membership_snapshot_payload,
    portable_membership_snapshot_from_payload,
)
from pheroos.governance._distributed.state import (
    DistributedCommitState,
    initialize_distributed_commit_state,
    distributed_commit_state_fingerprint,
    distributed_commit_state_is_current,
    _issue_distributed_state,
)


@dataclass(frozen=True)
class EpochTransitionCertificate:
    schema_discriminator: str
    certificate_version: str
    wire_version: str
    canonicalization: str
    hash_algorithm: str
    certificate_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    previous_epoch: int
    new_epoch: int
    previous_membership_root: str
    new_membership_snapshot: PortableMembershipSnapshot
    new_membership_snapshot_root: str
    new_membership_epoch_state_root: str
    new_membership_root: str
    prior_state_ref: str
    declared_transition_rule: str
    declared_recovery_ref: str
    recovery_required: bool
    transition_stop_root: str
    transition_permission_root: str
    recovery_stop_root: str
    recovery_permission_root: str
    issuer_id: str
    authority: AuthorityLevel
    issued_at_step: int
    provenance: str
    trace_event_id: str
    issuer_attestation_refs: tuple[str, ...]
    certificate_body_root: str
    certificate_root: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "issuer_attestation_refs",
            require_commit_labels(
                self.issuer_attestation_refs,
                "epoch transition issuer attestations",
            ),
        )
        _validate_epoch_transition_certificate(self)


def epoch_transition_decision_ref(
    state: DistributedCommitState,
    new_membership_snapshot: EligiblePrincipalSnapshot,
    new_membership_epoch_state: EligibleMembershipEpochState,
    *,
    commit_policy: CollectiveCommitPolicy,
    declared_recovery_ref: str = "",
) -> str:
    if not distributed_commit_state_is_current(state):
        raise GovernanceError("epoch transition requires the current state")
    _validate_new_epoch_membership(
        state,
        new_membership_snapshot,
        new_membership_epoch_state,
        commit_policy=commit_policy,
        current_step=new_membership_snapshot.issued_at_step,
    )
    recovery_ref = (
        require_commit_fingerprint(
            declared_recovery_ref,
            "epoch transition declared_recovery_ref",
        )
        if declared_recovery_ref
        else ""
    )
    if state.frozen and not recovery_ref:
        raise GovernanceError(
            "frozen epoch transition requires a declared recovery reference"
        )
    return commit_payload_fingerprint(
        {
            "declared_recovery_ref": recovery_ref,
            "new_epoch": new_membership_snapshot.epoch,
            "new_membership_epoch_state_root": (
                eligible_membership_epoch_state_fingerprint(new_membership_epoch_state)
            ),
            "new_membership_snapshot_root": (
                eligible_principal_snapshot_fingerprint(new_membership_snapshot)
            ),
            "previous_state_ref": distributed_commit_state_fingerprint(state),
            "recovery_required": state.frozen,
            "target": state.target,
        },
        schema="pheroos-epoch-transition-decision-v1",
        profile=state.profile,
    )


def epoch_transition_certificate_body_root(
    state: DistributedCommitState,
    new_membership_snapshot: EligiblePrincipalSnapshot,
    new_membership_epoch_state: EligibleMembershipEpochState,
    transition_stop: StopResolutionVerification,
    transition_permission: ActionPermission,
    *,
    commit_policy: CollectiveCommitPolicy,
    certificate_id: str,
    declared_recovery_ref: str = "",
    recovery_stop: StopResolutionVerification | None = None,
    recovery_permission: ActionPermission | None = None,
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> str:
    body = _epoch_transition_body_from_inputs(
        state,
        new_membership_snapshot,
        new_membership_epoch_state,
        transition_stop,
        transition_permission,
        commit_policy=commit_policy,
        certificate_id=certificate_id,
        declared_recovery_ref=declared_recovery_ref,
        recovery_stop=recovery_stop,
        recovery_permission=recovery_permission,
        issuer_id=issuer_id,
        authority=authority,
        issued_at_step=issued_at_step,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )
    return _epoch_transition_body_root(body, profile=state.profile)


def issue_epoch_transition_certificate(
    state: DistributedCommitState,
    new_membership_snapshot: EligiblePrincipalSnapshot,
    new_membership_epoch_state: EligibleMembershipEpochState,
    transition_stop: StopResolutionVerification,
    transition_permission: ActionPermission,
    *,
    commit_policy: CollectiveCommitPolicy,
    certificate_id: str,
    declared_recovery_ref: str = "",
    recovery_stop: StopResolutionVerification | None = None,
    recovery_permission: ActionPermission | None = None,
    issuer_attestation_refs: Sequence[str],
    trusted_issuer_attestations: Mapping[str, str],
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> EpochTransitionCertificate:
    body = _epoch_transition_body_from_inputs(
        state,
        new_membership_snapshot,
        new_membership_epoch_state,
        transition_stop,
        transition_permission,
        commit_policy=commit_policy,
        certificate_id=certificate_id,
        declared_recovery_ref=declared_recovery_ref,
        recovery_stop=recovery_stop,
        recovery_permission=recovery_permission,
        issuer_id=issuer_id,
        authority=authority,
        issued_at_step=issued_at_step,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )
    body_root = _epoch_transition_body_root(body, profile=state.profile)
    attestations = _require_attestation_bindings(
        issuer_attestation_refs,
        trusted_issuer_attestations,
        body_root,
        field_name="epoch transition certificate",
    )
    certificate_root = commit_payload_fingerprint(
        {
            "certificate_body_root": body_root,
            "issuer_attestation_refs": attestations,
        },
        schema="pheroos-epoch-transition-certificate-envelope-v1",
        profile=state.profile,
    )
    body["issuer_attestation_refs"] = attestations
    body["certificate_body_root"] = body_root
    body["certificate_root"] = certificate_root
    certificate = _construct_dataclass(EpochTransitionCertificate, body)
    return _register_epoch_transition_certificate_identity(certificate)


def epoch_transition_certificate_payload(
    certificate: EpochTransitionCertificate,
) -> dict[str, object]:
    if type(certificate) is not EpochTransitionCertificate:
        raise GovernanceError(
            "epoch transition certificate must use the canonical record"
        )
    _validate_epoch_transition_certificate(certificate)
    payload = _public_dataclass_payload(certificate)
    payload["new_membership_snapshot"] = portable_membership_snapshot_payload(
        certificate.new_membership_snapshot
    )
    return payload


def epoch_transition_certificate_fingerprint(
    certificate: EpochTransitionCertificate,
) -> str:
    return commit_payload_fingerprint(
        epoch_transition_certificate_payload(certificate),
        schema=EPOCH_TRANSITION_CERTIFICATE_VERSION,
        profile=certificate.profile,
    )


def epoch_transition_certificate_from_payload(
    payload: Mapping[str, object],
) -> EpochTransitionCertificate:
    values = _strict_dataclass_payload(
        payload,
        EpochTransitionCertificate,
        "epoch transition certificate payload",
    )
    values["assurance"] = _coerce_assurance(values["assurance"])
    values["authority"] = _coerce_authority(values["authority"])
    values["new_membership_snapshot"] = portable_membership_snapshot_from_payload(
        _require_mapping(
            values["new_membership_snapshot"],
            "epoch transition membership snapshot",
        )
    )
    values["issuer_attestation_refs"] = tuple(
        _require_sequence(
            values["issuer_attestation_refs"],
            "epoch transition issuer attestations",
        )
    )
    try:
        return _construct_dataclass(EpochTransitionCertificate, values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(
            f"epoch transition certificate payload is invalid: {exc}"
        ) from exc


def verify_epoch_transition_certificate(
    certificate_or_payload: EpochTransitionCertificate | Mapping[str, object],
    *,
    commit_policy: CollectiveCommitPolicy,
    trusted_issuer_attestations: Mapping[str, str],
    expected_certificate_ref: str = "",
) -> bool:
    try:
        if type(certificate_or_payload) is EpochTransitionCertificate:
            assert isinstance(certificate_or_payload, EpochTransitionCertificate)
            certificate = certificate_or_payload
        else:
            certificate = epoch_transition_certificate_from_payload(
                _require_mapping(
                    certificate_or_payload,
                    "epoch transition certificate payload",
                )
            )
        distributed = _validate_distributed_policy(
            commit_policy,
            profile=certificate.profile,
            assurance=certificate.assurance,
            target=certificate.target,
            commit_policy_root=certificate.commit_policy_root,
        )
        _validate_membership_policy(
            certificate.new_membership_snapshot,
            distributed,
        )
        if certificate.declared_transition_rule != distributed.epoch_transition_rule:
            return False
        if not all(
            trusted_issuer_attestations.get(reference)
            == certificate.certificate_body_root
            for reference in certificate.issuer_attestation_refs
        ):
            return False
        if expected_certificate_ref and (
            epoch_transition_certificate_fingerprint(certificate)
            != require_commit_fingerprint(
                expected_certificate_ref,
                "expected epoch transition certificate ref",
            )
        ):
            return False
        return True
    except (AssertionError, TypeError, ValueError, GovernanceError):
        return False


def transition_distributed_commit_epoch(
    state: DistributedCommitState,
    certificate: EpochTransitionCertificate,
    new_membership_snapshot: EligiblePrincipalSnapshot,
    new_membership_epoch_state: EligibleMembershipEpochState,
    *,
    commit_policy: CollectiveCommitPolicy,
    trusted_issuer_attestations: Mapping[str, str],
    issuer_id: str,
    authority: AuthorityLevel,
    provenance: str,
    trace_event_id: str,
) -> tuple[DistributedCommitState, DistributedCommitState]:
    if not distributed_commit_state_is_current(state):
        raise GovernanceError("epoch transition state is not current")
    if not verify_epoch_transition_certificate(
        certificate,
        commit_policy=commit_policy,
        trusted_issuer_attestations=trusted_issuer_attestations,
    ):
        raise GovernanceError("epoch transition certificate verification failed")
    certificate_ref = epoch_transition_certificate_fingerprint(certificate)
    if (
        certificate.prior_state_ref != distributed_commit_state_fingerprint(state)
        or certificate.previous_epoch != state.epoch
        or certificate.previous_membership_root != state.membership_root
        or certificate.recovery_required is not state.frozen
        or certificate.new_membership_snapshot_root
        != eligible_principal_snapshot_fingerprint(new_membership_snapshot)
        or certificate.new_membership_epoch_state_root
        != eligible_membership_epoch_state_fingerprint(new_membership_epoch_state)
    ):
        raise GovernanceError("epoch transition lineage mismatch")
    parent_ref = distributed_commit_state_fingerprint(state)
    request_ref = commit_payload_fingerprint(
        {
            "certificate_ref": certificate_ref,
            "parent_state_ref": parent_ref,
        },
        schema="pheroos-distributed-epoch-transition-request-v1",
        profile=state.profile,
    )
    cursor = state._cursor
    if type(cursor) is not _DistributedStateCursor:
        raise GovernanceError("distributed epoch state cursor is invalid")
    with cursor.lock:
        if cursor.current_state_fingerprint != parent_ref:
            prior = cursor.transitions.get(parent_ref)
            if prior is not None and prior[0] == request_ref:
                prior_state = prior[1]
                if type(prior_state) is not DistributedCommitState:
                    raise GovernanceError("distributed epoch replay state is invalid")
                transitioned = prior_state
            else:
                raise GovernanceError("distributed epoch state is stale or would fork")
        else:
            transitioned = _replace_distributed_state(
                state,
                revision=state.revision + 1,
                current_step=certificate.issued_at_step,
                previous_state_fingerprint=parent_ref,
                transitioned=True,
                epoch_transition_certificate_ref=certificate_ref,
            )
            transitioned = _issue_distributed_state(transitioned, cursor)
            cursor.current_state = transitioned
            cursor.current_state_fingerprint = distributed_commit_state_fingerprint(
                transitioned
            )
            cursor.transitions[parent_ref] = (request_ref, transitioned)
    new_state = initialize_distributed_commit_state(
        new_membership_snapshot,
        new_membership_epoch_state,
        commit_policy=commit_policy,
        current_step=certificate.issued_at_step,
        issuer_id=issuer_id,
        authority=authority,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )
    return transitioned, new_state


def _validate_epoch_transition_certificate(
    certificate: EpochTransitionCertificate,
) -> None:
    if certificate.schema_discriminator != EPOCH_TRANSITION_CERTIFICATE_DISCRIMINATOR:
        raise GovernanceError("epoch transition discriminator is invalid")
    if certificate.certificate_version != EPOCH_TRANSITION_CERTIFICATE_VERSION:
        raise GovernanceError("epoch transition version is unsupported")
    if certificate.wire_version != COMMIT_WIRE_VERSION:
        raise GovernanceError("epoch transition wire version is unsupported")
    if certificate.canonicalization != COMMIT_CANONICAL_VERSION:
        raise GovernanceError("epoch transition canonicalization is unsupported")
    if certificate.hash_algorithm != "sha256":
        raise GovernanceError("epoch transition hash algorithm is unsupported")
    if certificate.profile != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("epoch transition profile is invalid")
    if certificate.assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("epoch transition assurance is invalid")
    for name in (
        "certificate_id",
        "protocol_id",
        "run_id",
        "target",
        "declared_transition_rule",
        "issuer_id",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(certificate, name),
            f"epoch transition {name}",
        )
    for name in (
        "manifest_root",
        "commit_policy_root",
        "previous_membership_root",
        "new_membership_snapshot_root",
        "new_membership_epoch_state_root",
        "new_membership_root",
        "prior_state_ref",
        "transition_stop_root",
        "transition_permission_root",
        "certificate_body_root",
        "certificate_root",
    ):
        require_commit_fingerprint(
            getattr(certificate, name),
            f"epoch transition {name}",
        )
    for name in ("previous_epoch", "new_epoch", "issued_at_step"):
        require_commit_step(
            getattr(certificate, name),
            f"epoch transition {name}",
        )
    if certificate.new_epoch <= certificate.previous_epoch:
        raise GovernanceError("epoch transition must advance the epoch")
    require_commit_bool(
        certificate.recovery_required,
        "epoch transition recovery_required",
    )
    if type(certificate.authority) is not AuthorityLevel or not can_verify(
        certificate.authority
    ):
        raise GovernanceError("epoch transition issuer lacks governance authority")
    if certificate.recovery_required:
        for name in (
            "declared_recovery_ref",
            "recovery_stop_root",
            "recovery_permission_root",
        ):
            require_commit_fingerprint(
                getattr(certificate, name),
                f"epoch transition {name}",
            )
    elif any(
        (
            certificate.declared_recovery_ref,
            certificate.recovery_stop_root,
            certificate.recovery_permission_root,
        )
    ):
        raise GovernanceError(
            "non-recovery epoch certificate contains recovery authority"
        )
    membership = certificate.new_membership_snapshot
    if (
        membership.profile != certificate.profile
        or membership.assurance is not certificate.assurance
        or membership.manifest_root != certificate.manifest_root
        or membership.commit_policy_root != certificate.commit_policy_root
        or membership.protocol_id != certificate.protocol_id
        or membership.run_id != certificate.run_id
        or membership.target != certificate.target
        or membership.epoch != certificate.new_epoch
        or membership.snapshot_fingerprint != certificate.new_membership_snapshot_root
        or membership.membership_root != certificate.new_membership_root
    ):
        raise GovernanceError("epoch transition new membership lineage mismatch")
    expected_body = _epoch_transition_body_root(
        _epoch_transition_body_payload(certificate),
        profile=certificate.profile,
    )
    if certificate.certificate_body_root != expected_body:
        raise GovernanceError("epoch transition body root is invalid")
    expected_root = commit_payload_fingerprint(
        {
            "certificate_body_root": expected_body,
            "issuer_attestation_refs": certificate.issuer_attestation_refs,
        },
        schema="pheroos-epoch-transition-certificate-envelope-v1",
        profile=certificate.profile,
    )
    if certificate.certificate_root != expected_root:
        raise GovernanceError("epoch transition envelope root is invalid")


def _epoch_transition_body_payload(
    certificate: EpochTransitionCertificate,
) -> dict[str, object]:
    payload = _public_dataclass_payload(certificate)
    for name in (
        "issuer_attestation_refs",
        "certificate_body_root",
        "certificate_root",
    ):
        payload.pop(name)
    payload["new_membership_snapshot"] = portable_membership_snapshot_payload(
        certificate.new_membership_snapshot
    )
    return payload


def _epoch_transition_body_root(
    body: Mapping[str, object],
    *,
    profile: str,
) -> str:
    normalized = dict(body)
    membership = normalized.get("new_membership_snapshot")
    if type(membership) is PortableMembershipSnapshot:
        normalized["new_membership_snapshot"] = portable_membership_snapshot_payload(
            membership
        )
    return commit_payload_fingerprint(
        normalized,
        schema="pheroos-epoch-transition-certificate-body-v1",
        profile=profile,
    )


def _register_epoch_transition_certificate_identity(
    certificate: EpochTransitionCertificate,
) -> EpochTransitionCertificate:
    key = (
        certificate.profile,
        certificate.run_id,
        certificate.target,
        certificate.previous_epoch,
        certificate.certificate_id,
    )
    fingerprint = epoch_transition_certificate_fingerprint(certificate)
    with PROCESS_STATE.transaction() as registry:
        existing = registry.get(_LEGACY_EPOCH_CERTIFICATES_BY_ID, key)
        if existing is not None:
            if epoch_transition_certificate_fingerprint(existing) != fingerprint:
                raise GovernanceError(
                    "epoch transition certificate id replay has a different body"
                )
            return cast(EpochTransitionCertificate, existing)
        registry.set(_LEGACY_EPOCH_CERTIFICATES_BY_ID, key, certificate)
        return certificate


def _validate_new_epoch_membership(
    state: DistributedCommitState,
    new_snapshot: EligiblePrincipalSnapshot,
    new_epoch_state: EligibleMembershipEpochState,
    *,
    commit_policy: CollectiveCommitPolicy,
    current_step: int,
) -> DistributedCommitPolicy:
    distributed = _validate_distributed_policy(
        commit_policy,
        profile=state.profile,
        assurance=state.assurance,
        target=state.target,
        commit_policy_root=state.commit_policy_root,
    )
    if new_snapshot.epoch <= state.epoch:
        raise GovernanceError("new distributed membership must advance epoch")
    if not eligible_principal_snapshot_matches(
        new_snapshot,
        epoch_state=new_epoch_state,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=new_snapshot.epoch,
        current_step=current_step,
    ):
        raise GovernanceError("new distributed membership is not authoritative")
    _validate_membership_policy(
        portable_membership_snapshot_from_eligible(new_snapshot),
        distributed,
    )
    return distributed


def _epoch_transition_body_from_inputs(
    state: DistributedCommitState,
    new_membership_snapshot: EligiblePrincipalSnapshot,
    new_membership_epoch_state: EligibleMembershipEpochState,
    transition_stop: StopResolutionVerification,
    transition_permission: ActionPermission,
    *,
    commit_policy: CollectiveCommitPolicy,
    certificate_id: str,
    declared_recovery_ref: str,
    recovery_stop: StopResolutionVerification | None,
    recovery_permission: ActionPermission | None,
    issuer_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> dict[str, object]:
    if not distributed_commit_state_is_current(state):
        raise GovernanceError("epoch transition requires the current state")
    if state.transitioned:
        raise GovernanceError("distributed epoch already transitioned")
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("epoch transition requires governance authority")
    current = require_commit_step(
        issued_at_step,
        "epoch transition issued_at_step",
    )
    distributed = _validate_new_epoch_membership(
        state,
        new_membership_snapshot,
        new_membership_epoch_state,
        commit_policy=commit_policy,
        current_step=current,
    )
    decision_ref = epoch_transition_decision_ref(
        state,
        new_membership_snapshot,
        new_membership_epoch_state,
        commit_policy=commit_policy,
        declared_recovery_ref=declared_recovery_ref,
    )
    _require_action_gate(
        stop=transition_stop,
        permission=transition_permission,
        state=state,
        action=CommitAction.EPOCH_TRANSITION,
        decision_ref=decision_ref,
        current_step=current,
    )
    recovery_ref = (
        require_commit_fingerprint(
            declared_recovery_ref,
            "epoch transition declared_recovery_ref",
        )
        if declared_recovery_ref
        else ""
    )
    if state.frozen:
        if recovery_stop is None or recovery_permission is None:
            raise GovernanceError(
                "conflict recovery requires explicit recovery stop and permission"
            )
        _require_action_gate(
            stop=recovery_stop,
            permission=recovery_permission,
            state=state,
            action=CommitAction.RECOVERY,
            decision_ref=decision_ref,
            current_step=current,
        )
    elif recovery_stop is not None or recovery_permission is not None or recovery_ref:
        raise GovernanceError(
            "non-conflict epoch transition cannot claim recovery authority"
        )
    new_portable = portable_membership_snapshot_from_eligible(new_membership_snapshot)
    _validate_membership_policy(new_portable, distributed)
    return {
        "schema_discriminator": EPOCH_TRANSITION_CERTIFICATE_DISCRIMINATOR,
        "certificate_version": EPOCH_TRANSITION_CERTIFICATE_VERSION,
        "wire_version": COMMIT_WIRE_VERSION,
        "canonicalization": COMMIT_CANONICAL_VERSION,
        "hash_algorithm": "sha256",
        "certificate_id": require_commit_text(
            certificate_id,
            "epoch transition certificate_id",
        ),
        "profile": state.profile,
        "assurance": state.assurance,
        "manifest_root": state.manifest_root,
        "commit_policy_root": state.commit_policy_root,
        "protocol_id": state.protocol_id,
        "run_id": state.run_id,
        "target": state.target,
        "previous_epoch": state.epoch,
        "new_epoch": new_portable.epoch,
        "previous_membership_root": state.membership_root,
        "new_membership_snapshot": new_portable,
        "new_membership_snapshot_root": new_portable.snapshot_fingerprint,
        "new_membership_epoch_state_root": (
            eligible_membership_epoch_state_fingerprint(new_membership_epoch_state)
        ),
        "new_membership_root": new_portable.membership_root,
        "prior_state_ref": distributed_commit_state_fingerprint(state),
        "declared_transition_rule": distributed.epoch_transition_rule,
        "declared_recovery_ref": recovery_ref,
        "recovery_required": state.frozen,
        "transition_stop_root": stop_resolution_verification_fingerprint(
            transition_stop
        ),
        "transition_permission_root": action_permission_fingerprint(
            transition_permission
        ),
        "recovery_stop_root": (
            stop_resolution_verification_fingerprint(recovery_stop)
            if recovery_stop is not None
            else ""
        ),
        "recovery_permission_root": (
            action_permission_fingerprint(recovery_permission)
            if recovery_permission is not None
            else ""
        ),
        "issuer_id": require_commit_text(
            issuer_id,
            "epoch transition issuer_id",
        ),
        "authority": authority,
        "issued_at_step": current,
        "provenance": require_commit_text(
            provenance,
            "epoch transition provenance",
        ),
        "trace_event_id": require_commit_text(
            trace_event_id,
            "epoch transition trace_event_id",
        ),
    }


for _name in (
    "EpochTransitionCertificate",
    "epoch_transition_decision_ref",
    "epoch_transition_certificate_body_root",
    "issue_epoch_transition_certificate",
    "epoch_transition_certificate_payload",
    "epoch_transition_certificate_fingerprint",
    "epoch_transition_certificate_from_payload",
    "verify_epoch_transition_certificate",
    "transition_distributed_commit_epoch",
    "_validate_epoch_transition_certificate",
    "_epoch_transition_body_payload",
    "_epoch_transition_body_root",
    "_register_epoch_transition_certificate_identity",
    "_validate_new_epoch_membership",
    "_epoch_transition_body_from_inputs",
):
    globals()[_name].__module__ = "pheroos.governance.distributed_commit"
del _name
