from __future__ import annotations

from dataclasses import dataclass, field

from pheroos.governance._commit_validation import (
    require_commit_assurance,
    require_commit_bool,
    require_commit_fingerprint,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CommitAction,
    CommitAssurance,
)


_STOP_RESOLUTION_VERIFICATION_ISSUANCE = object()


@dataclass(frozen=True)
class StopSignal:
    target: str
    action: str
    reason: str
    blocking: bool = True


@dataclass(frozen=True)
class StopResolution:
    target: str
    action: str
    blocked: bool
    reason: str = ""


@dataclass(frozen=True)
class StopResolutionVerification:
    resolution_id: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    action: CommitAction
    epoch: int
    decision_ref: str
    certificate_ref: str
    resolved_stop_root: str
    blocked: bool
    reason: str
    resolution_fingerprint: str
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
        _validate_stop_resolution_verification_shape(self)


def resolve_stop_signal(signal: StopSignal) -> StopResolution:
    return StopResolution(
        target=signal.target,
        action=signal.action,
        blocked=signal.blocking,
        reason=signal.reason,
    )


def verify_stop_resolution(
    resolution: StopResolution,
    *,
    resolution_id: str,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    epoch: int,
    decision_ref: str,
    certificate_ref: str,
    resolved_stop_root: str,
    verifier_id: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    expires_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> StopResolutionVerification:
    if type(resolution) is not StopResolution:
        raise GovernanceError("stop resolution must use the canonical record")
    target = require_commit_text(resolution.target, "stop resolution target")
    try:
        action = CommitAction(resolution.action)
    except (TypeError, ValueError) as exc:
        raise GovernanceError("stop resolution action is unsupported") from exc
    blocked = require_commit_bool(resolution.blocked, "stop resolution blocked")
    reason = require_commit_text(resolution.reason, "stop resolution reason")
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError(
            "stop resolution verification requires governance authority"
        )
    issued = require_commit_step(issued_at_step, "stop verification issued_at_step")
    expires = require_commit_step(expires_at_step, "stop verification expires_at_step")
    if expires <= issued:
        raise GovernanceError(
            "stop resolution verification expiry must be after issuance"
        )
    fingerprint = commit_payload_fingerprint(
        {
            "action": action,
            "blocked": blocked,
            "reason": reason,
            "target": target,
        },
        schema="pheroos-stop-resolution-v1",
        profile="pheroos-commit-authority-v1",
    )
    verification = StopResolutionVerification(
        resolution_id=require_commit_text(
            resolution_id,
            "stop verification resolution_id",
        ),
        profile=require_commit_profile(profile, "stop verification profile"),
        assurance=require_commit_assurance(
            assurance,
            "stop verification assurance",
        ),
        manifest_root=require_commit_fingerprint(
            manifest_root,
            "stop verification manifest_root",
        ),
        commit_policy_root=require_commit_fingerprint(
            commit_policy_root,
            "stop verification commit_policy_root",
        ),
        protocol_id=require_commit_text(protocol_id, "stop verification protocol_id"),
        run_id=require_commit_text(run_id, "stop verification run_id"),
        target=target,
        action=action,
        epoch=require_commit_step(epoch, "stop verification epoch"),
        decision_ref=require_commit_fingerprint(
            decision_ref,
            "stop verification decision_ref",
        ),
        certificate_ref=(
            require_commit_fingerprint(
                certificate_ref,
                "stop verification certificate_ref",
            )
            if certificate_ref
            else ""
        ),
        resolved_stop_root=require_commit_fingerprint(
            resolved_stop_root,
            "stop verification resolved_stop_root",
        ),
        blocked=blocked,
        reason=reason,
        resolution_fingerprint=fingerprint,
        verifier_id=require_commit_text(verifier_id, "stop verification verifier_id"),
        authority=authority,
        issued_at_step=issued,
        expires_at_step=expires,
        provenance=require_commit_text(provenance, "stop verification provenance"),
        trace_event_id=require_commit_text(
            trace_event_id,
            "stop verification trace_event_id",
        ),
    )
    object.__setattr__(
        verification,
        "_issuance",
        (
            _STOP_RESOLUTION_VERIFICATION_ISSUANCE,
            _stop_resolution_verification_snapshot(verification),
        ),
    )
    return verification


def stop_resolution_verification_is_authoritative(verification: object) -> bool:
    if type(verification) is not StopResolutionVerification:
        return False
    try:
        _validate_stop_resolution_verification_shape(verification)
        issuance = verification._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _STOP_RESOLUTION_VERIFICATION_ISSUANCE
            and issuance[1] == _stop_resolution_verification_snapshot(verification)
        )
    except Exception:
        return False


def stop_resolution_verification_matches(
    verification: StopResolutionVerification | None,
    *,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    action: CommitAction,
    epoch: int,
    decision_ref: str,
    certificate_ref: str,
    current_step: int,
    require_unblocked: bool = True,
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
        if type(action) is not CommitAction:
            return False
        expected_epoch = require_commit_step(epoch, "expected epoch")
        expected_decision = require_commit_fingerprint(
            decision_ref,
            "expected decision_ref",
        )
        expected_certificate = (
            require_commit_fingerprint(certificate_ref, "expected certificate_ref")
            if certificate_ref
            else ""
        )
        if type(require_unblocked) is not bool:
            return False
        current = require_commit_step(current_step, "stop verification current_step")
        return bool(
            stop_resolution_verification_is_authoritative(verification)
            and verification is not None
            and verification.profile == expected_profile
            and verification.assurance is expected_assurance
            and verification.manifest_root == expected_manifest_root
            and verification.commit_policy_root == expected_policy_root
            and verification.protocol_id == expected_protocol
            and verification.run_id == expected_run
            and verification.target == expected_target
            and verification.action is action
            and verification.epoch == expected_epoch
            and verification.decision_ref == expected_decision
            and verification.certificate_ref == expected_certificate
            and verification.issued_at_step <= current < verification.expires_at_step
            and (not require_unblocked or not verification.blocked)
        )
    except GovernanceError:
        return False


def _validate_stop_resolution_verification_shape(
    verification: StopResolutionVerification,
) -> None:
    for field_name in (
        "resolution_id",
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "resolved_stop_root",
        "reason",
        "verifier_id",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(verification, field_name),
            f"stop verification {field_name}",
        )
    assurance = require_commit_assurance(
        verification.assurance,
        "stop verification assurance",
    )
    require_commit_profile(verification.profile, "stop verification profile")
    if verification.profile not in COMMIT_PROFILES_BY_ASSURANCE[assurance.value]:
        raise GovernanceError("stop verification profile/assurance mismatch")
    for field_name in (
        "manifest_root",
        "commit_policy_root",
        "decision_ref",
        "resolved_stop_root",
        "resolution_fingerprint",
    ):
        require_commit_fingerprint(
            getattr(verification, field_name),
            f"stop verification {field_name}",
        )
    if verification.certificate_ref:
        require_commit_fingerprint(
            verification.certificate_ref,
            "stop verification certificate_ref",
        )
    if type(verification.action) is not CommitAction:
        raise GovernanceError("stop verification action is invalid")
    if (
        verification.action in {CommitAction.PUBLISH, CommitAction.EXECUTE}
        and not verification.certificate_ref
    ):
        raise GovernanceError(
            "publish/execute stop verification requires a certificate_ref"
        )
    require_commit_step(verification.epoch, "stop verification epoch")
    require_commit_bool(verification.blocked, "stop verification blocked")
    if type(verification.authority) is not AuthorityLevel or not can_verify(
        verification.authority
    ):
        raise GovernanceError("stop verification authority is invalid")
    issued = require_commit_step(
        verification.issued_at_step,
        "stop verification issued_at_step",
    )
    expires = require_commit_step(
        verification.expires_at_step,
        "stop verification expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("stop verification expiry must be after issuance")


def _stop_resolution_verification_snapshot(
    verification: StopResolutionVerification,
) -> str:
    return commit_payload_fingerprint(
        stop_resolution_verification_payload(verification),
        schema="pheroos-stop-resolution-verification-v1",
        profile=verification.profile,
    )


def stop_resolution_verification_payload(
    verification: StopResolutionVerification,
) -> dict[str, object]:
    if type(verification) is not StopResolutionVerification:
        raise GovernanceError("stop verification must use the canonical record")
    _validate_stop_resolution_verification_shape(verification)
    return {
        "action": verification.action,
        "assurance": verification.assurance,
        "authority": verification.authority,
        "blocked": verification.blocked,
        "certificate_ref": verification.certificate_ref,
        "commit_policy_root": verification.commit_policy_root,
        "decision_ref": verification.decision_ref,
        "epoch": verification.epoch,
        "expires_at_step": verification.expires_at_step,
        "issued_at_step": verification.issued_at_step,
        "manifest_root": verification.manifest_root,
        "profile": verification.profile,
        "protocol_id": verification.protocol_id,
        "provenance": verification.provenance,
        "reason": verification.reason,
        "resolution_fingerprint": verification.resolution_fingerprint,
        "resolution_id": verification.resolution_id,
        "resolved_stop_root": verification.resolved_stop_root,
        "run_id": verification.run_id,
        "target": verification.target,
        "trace_event_id": verification.trace_event_id,
        "verifier_id": verification.verifier_id,
    }


def stop_resolution_verification_fingerprint(
    verification: StopResolutionVerification,
) -> str:
    return _stop_resolution_verification_snapshot(verification)


__all__ = [
    "CommitAction",
    "StopResolution",
    "StopResolutionVerification",
    "StopSignal",
    "resolve_stop_signal",
    "stop_resolution_verification_is_authoritative",
    "stop_resolution_verification_fingerprint",
    "stop_resolution_verification_matches",
    "stop_resolution_verification_payload",
    "verify_stop_resolution",
]
