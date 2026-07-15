from __future__ import annotations

from dataclasses import dataclass, field

from pheroos.governance._commit_validation import (
    require_commit_assurance,
    require_commit_bool,
    require_commit_fingerprint,
    require_commit_labels,
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


_ACTION_PERMISSION_ISSUANCE = object()


@dataclass(frozen=True)
class ActionPermission:
    permission_id: str
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
    allowed: bool
    reason_codes: tuple[str, ...]
    issuer_id: str
    policy_ref: str
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
        object.__setattr__(
            self,
            "reason_codes",
            require_commit_labels(
                self.reason_codes,
                "action permission reason_codes",
            ),
        )
        _validate_action_permission_shape(self)


def issue_action_permission(
    *,
    permission_id: str,
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
    allowed: bool,
    reason_codes: tuple[str, ...] | list[str],
    issuer_id: str,
    policy_ref: str,
    authority: AuthorityLevel,
    issued_at_step: int,
    expires_at_step: int,
    provenance: str,
    trace_event_id: str,
) -> ActionPermission:
    if type(action) is not CommitAction:
        raise GovernanceError("action permission action is invalid")
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("action permission issuance requires governance authority")
    permission = ActionPermission(
        permission_id=require_commit_text(
            permission_id,
            "action permission permission_id",
        ),
        profile=require_commit_profile(profile, "action permission profile"),
        assurance=require_commit_assurance(
            assurance,
            "action permission assurance",
        ),
        manifest_root=require_commit_fingerprint(
            manifest_root,
            "action permission manifest_root",
        ),
        commit_policy_root=require_commit_fingerprint(
            commit_policy_root,
            "action permission commit_policy_root",
        ),
        protocol_id=require_commit_text(
            protocol_id,
            "action permission protocol_id",
        ),
        run_id=require_commit_text(run_id, "action permission run_id"),
        target=require_commit_text(target, "action permission target"),
        action=action,
        epoch=require_commit_step(epoch, "action permission epoch"),
        decision_ref=require_commit_fingerprint(
            decision_ref,
            "action permission decision_ref",
        ),
        certificate_ref=(
            require_commit_fingerprint(
                certificate_ref,
                "action permission certificate_ref",
            )
            if certificate_ref
            else ""
        ),
        allowed=require_commit_bool(allowed, "action permission allowed"),
        reason_codes=require_commit_labels(
            reason_codes,
            "action permission reason_codes",
        ),
        issuer_id=require_commit_text(issuer_id, "action permission issuer_id"),
        policy_ref=require_commit_text(policy_ref, "action permission policy_ref"),
        authority=authority,
        issued_at_step=require_commit_step(
            issued_at_step,
            "action permission issued_at_step",
        ),
        expires_at_step=require_commit_step(
            expires_at_step,
            "action permission expires_at_step",
        ),
        provenance=require_commit_text(provenance, "action permission provenance"),
        trace_event_id=require_commit_text(
            trace_event_id,
            "action permission trace_event_id",
        ),
    )
    object.__setattr__(
        permission,
        "_issuance",
        (
            _ACTION_PERMISSION_ISSUANCE,
            _action_permission_snapshot(permission),
        ),
    )
    return permission


def action_permission_is_authoritative(permission: object) -> bool:
    if type(permission) is not ActionPermission:
        return False
    try:
        _validate_action_permission_shape(permission)
        issuance = permission._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _ACTION_PERMISSION_ISSUANCE
            and issuance[1] == _action_permission_snapshot(permission)
        )
    except Exception:
        return False


def action_permission_matches(
    permission: ActionPermission | None,
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
    require_allowed: bool = True,
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
        if type(action) is not CommitAction or type(require_allowed) is not bool:
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
        current = require_commit_step(current_step, "action permission current_step")
        return bool(
            action_permission_is_authoritative(permission)
            and permission is not None
            and permission.profile == expected_profile
            and permission.assurance is expected_assurance
            and permission.manifest_root == expected_manifest_root
            and permission.commit_policy_root == expected_policy_root
            and permission.protocol_id == expected_protocol
            and permission.run_id == expected_run
            and permission.target == expected_target
            and permission.action is action
            and permission.epoch == expected_epoch
            and permission.decision_ref == expected_decision
            and permission.certificate_ref == expected_certificate
            and permission.issued_at_step <= current < permission.expires_at_step
            and (not require_allowed or permission.allowed)
        )
    except GovernanceError:
        return False


def _validate_action_permission_shape(permission: ActionPermission) -> None:
    for field_name in (
        "permission_id",
        "manifest_root",
        "commit_policy_root",
        "protocol_id",
        "run_id",
        "target",
        "issuer_id",
        "policy_ref",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(permission, field_name),
            f"action permission {field_name}",
        )
    assurance = require_commit_assurance(
        permission.assurance,
        "action permission assurance",
    )
    require_commit_profile(permission.profile, "action permission profile")
    if permission.profile not in COMMIT_PROFILES_BY_ASSURANCE[assurance.value]:
        raise GovernanceError("action permission profile/assurance mismatch")
    for field_name in ("manifest_root", "commit_policy_root", "decision_ref"):
        require_commit_fingerprint(
            getattr(permission, field_name),
            f"action permission {field_name}",
        )
    if permission.certificate_ref:
        require_commit_fingerprint(
            permission.certificate_ref,
            "action permission certificate_ref",
        )
    if type(permission.action) is not CommitAction:
        raise GovernanceError("action permission action is invalid")
    if (
        permission.action in {CommitAction.PUBLISH, CommitAction.EXECUTE}
        and not permission.certificate_ref
    ):
        raise GovernanceError(
            "publish/execute action permission requires a certificate_ref"
        )
    require_commit_step(permission.epoch, "action permission epoch")
    require_commit_bool(permission.allowed, "action permission allowed")
    require_commit_labels(
        permission.reason_codes,
        "action permission reason_codes",
    )
    if type(permission.authority) is not AuthorityLevel or not can_verify(
        permission.authority
    ):
        raise GovernanceError("action permission authority is invalid")
    issued = require_commit_step(
        permission.issued_at_step,
        "action permission issued_at_step",
    )
    expires = require_commit_step(
        permission.expires_at_step,
        "action permission expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("action permission expiry must be after issuance")


def _action_permission_snapshot(permission: ActionPermission) -> str:
    return commit_payload_fingerprint(
        action_permission_payload(permission),
        schema="pheroos-action-permission-v1",
        profile=permission.profile,
    )


def action_permission_payload(permission: ActionPermission) -> dict[str, object]:
    if type(permission) is not ActionPermission:
        raise GovernanceError("action permission must use the canonical record")
    _validate_action_permission_shape(permission)
    return {
        "action": permission.action,
        "allowed": permission.allowed,
        "assurance": permission.assurance,
        "authority": permission.authority,
        "certificate_ref": permission.certificate_ref,
        "commit_policy_root": permission.commit_policy_root,
        "decision_ref": permission.decision_ref,
        "epoch": permission.epoch,
        "expires_at_step": permission.expires_at_step,
        "issued_at_step": permission.issued_at_step,
        "issuer_id": permission.issuer_id,
        "manifest_root": permission.manifest_root,
        "permission_id": permission.permission_id,
        "policy_ref": permission.policy_ref,
        "profile": permission.profile,
        "protocol_id": permission.protocol_id,
        "provenance": permission.provenance,
        "reason_codes": permission.reason_codes,
        "run_id": permission.run_id,
        "target": permission.target,
        "trace_event_id": permission.trace_event_id,
    }


def action_permission_fingerprint(permission: ActionPermission) -> str:
    return _action_permission_snapshot(permission)


__all__ = [
    "ActionPermission",
    "action_permission_fingerprint",
    "action_permission_is_authoritative",
    "action_permission_matches",
    "action_permission_payload",
    "issue_action_permission",
]
