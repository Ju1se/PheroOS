from __future__ import annotations

from dataclasses import replace

from pheroos.conformance.checks._commit_context import (
    ActiveCommitContext,
    active_commit_context,
)
from pheroos.conformance.report import CheckResult
from pheroos.governance import (
    ActionPermission,
    AuthorityLevel,
    CommitAction,
    CommitAssurance,
    StopResolution,
    StopResolutionVerification,
    action_permission_is_authoritative,
    action_permission_matches,
    commit_payload_fingerprint,
    issue_action_permission,
    stop_resolution_verification_is_authoritative,
    stop_resolution_verification_matches,
    verify_stop_resolution,
)
from pheroos.governance.errors import GovernanceError
from pheroos.conformance.checks._commit_tck_contract import check_commit_tck_cases
from pheroos.protocol import CapabilityManifest


_ISSUED_AT_STEP = 4
_CURRENT_STEP = 5
_EXPIRES_AT_STEP = 9


def check(manifest: CapabilityManifest) -> CheckResult:
    context = active_commit_context(manifest)
    if context is None:
        return CheckResult("commit_authority_boundary", True)

    decision_ref = _decision_ref(context)
    permission_allowed = context.assurance is not CommitAssurance.ADVISORY
    problems = _permission_authority_problems(
        context,
        decision_ref=decision_ref,
        permission_allowed=permission_allowed,
    )
    problems.extend(_stop_authority_problems(context, decision_ref=decision_ref))
    problems.extend(_blocked_stop_problems(context, decision_ref=decision_ref))
    tck_result = check_commit_tck_cases(
        manifest,
        check_name="commit_authority_boundary",
        matrix_cases=(21, 22, 23),
    )
    if not tck_result.ok:
        problems.append(tck_result.detail or "authority TCK failed")

    unique = sorted(set(problems))
    return CheckResult(
        "commit_authority_boundary",
        not unique,
        "; ".join(unique) if unique else tck_result.detail,
    )


def _permission_authority_problems(
    context: ActiveCommitContext,
    *,
    decision_ref: str,
    permission_allowed: bool,
) -> list[str]:
    problems: list[str] = []
    permission = _issue_permission(
        context,
        decision_ref=decision_ref,
        authority=AuthorityLevel.GOVERNANCE,
        allowed=permission_allowed,
        trace_event_id="trace:conformance:permission:issued",
    )
    if not action_permission_is_authoritative(permission):
        problems.append("issued_permission_not_authoritative")
    if not _permission_matches(
        permission,
        context,
        decision_ref=decision_ref,
        current_step=_CURRENT_STEP,
        require_allowed=permission_allowed,
    ):
        problems.append("issued_permission_does_not_match")

    forged_permission = replace(permission)
    if action_permission_is_authoritative(forged_permission):
        problems.append("direct_permission_forgery_accepted")
    if _permission_matches(
        permission,
        context,
        decision_ref=decision_ref,
        current_step=_CURRENT_STEP,
        target=f"{context.target}:cross-scope",
        require_allowed=permission_allowed,
    ):
        problems.append("permission_cross_target_replay_accepted")
    if _permission_matches(
        permission,
        context,
        decision_ref=decision_ref,
        current_step=_CURRENT_STEP,
        run_id=f"{context.run_id}:cross-scope",
        require_allowed=permission_allowed,
    ):
        problems.append("permission_cross_run_replay_accepted")
    if _permission_matches(
        permission,
        context,
        decision_ref=decision_ref,
        current_step=_CURRENT_STEP,
        action=CommitAction.RECOVERY,
        require_allowed=permission_allowed,
    ):
        problems.append("permission_cross_action_replay_accepted")
    if _permission_matches(
        permission,
        context,
        decision_ref=decision_ref,
        current_step=_EXPIRES_AT_STEP,
        require_allowed=permission_allowed,
    ):
        problems.append("expired_permission_accepted")

    tampered_permission = _issue_permission(
        context,
        decision_ref=decision_ref,
        authority=AuthorityLevel.GOVERNANCE,
        allowed=permission_allowed,
        trace_event_id="trace:conformance:permission:tamper",
    )
    object.__setattr__(tampered_permission, "allowed", not permission_allowed)
    if action_permission_is_authoritative(tampered_permission):
        problems.append("tampered_permission_accepted")
    if not _permission_issuance_rejected(
        context,
        decision_ref=decision_ref,
        authority=AuthorityLevel.AGENT,
        allowed=True,
        trace_event_id="trace:conformance:permission:forged-authority",
    ):
        problems.append("agent_permission_authority_accepted")
    return problems


def _stop_authority_problems(
    context: ActiveCommitContext,
    *,
    decision_ref: str,
) -> list[str]:
    problems: list[str] = []
    stop_verification = _issue_stop_verification(
        context,
        decision_ref=decision_ref,
        authority=AuthorityLevel.GOVERNANCE,
        blocked=False,
        trace_event_id="trace:conformance:stop:issued",
    )
    if not stop_resolution_verification_is_authoritative(stop_verification):
        problems.append("issued_stop_verification_not_authoritative")
    if not _stop_matches(
        stop_verification,
        context,
        decision_ref=decision_ref,
        current_step=_CURRENT_STEP,
    ):
        problems.append("issued_stop_verification_does_not_match")

    forged_stop = replace(stop_verification)
    if stop_resolution_verification_is_authoritative(forged_stop):
        problems.append("direct_stop_verification_forgery_accepted")
    if _stop_matches(
        stop_verification,
        context,
        decision_ref=decision_ref,
        current_step=_CURRENT_STEP,
        target=f"{context.target}:cross-scope",
    ):
        problems.append("stop_cross_target_replay_accepted")
    if _stop_matches(
        stop_verification,
        context,
        decision_ref=decision_ref,
        current_step=_CURRENT_STEP,
        action=CommitAction.RECOVERY,
    ):
        problems.append("stop_cross_action_replay_accepted")
    if _stop_matches(
        stop_verification,
        context,
        decision_ref=decision_ref,
        current_step=_EXPIRES_AT_STEP,
    ):
        problems.append("expired_stop_verification_accepted")

    tampered_stop = _issue_stop_verification(
        context,
        decision_ref=decision_ref,
        authority=AuthorityLevel.GOVERNANCE,
        blocked=False,
        trace_event_id="trace:conformance:stop:tamper",
    )
    object.__setattr__(tampered_stop, "blocked", True)
    if stop_resolution_verification_is_authoritative(tampered_stop):
        problems.append("tampered_stop_verification_accepted")
    if not _stop_issuance_rejected(
        context,
        decision_ref=decision_ref,
        authority=AuthorityLevel.AGENT,
        blocked=False,
        trace_event_id="trace:conformance:stop:forged-authority",
    ):
        problems.append("agent_stop_verification_authority_accepted")
    return problems


def _blocked_stop_problems(
    context: ActiveCommitContext,
    *,
    decision_ref: str,
) -> list[str]:
    problems: list[str] = []
    blocked_stop = _issue_stop_verification(
        context,
        decision_ref=decision_ref,
        authority=AuthorityLevel.GOVERNANCE,
        blocked=True,
        trace_event_id="trace:conformance:stop:blocked",
    )
    if _stop_matches(
        blocked_stop,
        context,
        decision_ref=decision_ref,
        current_step=_CURRENT_STEP,
    ):
        problems.append("blocked_stop_authorized_action")
    if not _stop_matches(
        blocked_stop,
        context,
        decision_ref=decision_ref,
        current_step=_CURRENT_STEP,
        require_unblocked=False,
    ):
        problems.append("blocked_stop_denial_not_verifiable")
    return problems


def _decision_ref(context: ActiveCommitContext) -> str:
    return commit_payload_fingerprint(
        {
            "commit_policy_root": context.commit_policy_root,
            "epoch": context.epoch,
            "manifest_root": context.manifest_root,
            "run_id": context.run_id,
            "target": context.target,
        },
        schema="pheroos-conformance-decision-reference-v1",
        profile=context.profile,
    )


def _resolved_stop_root(context: ActiveCommitContext, *, blocked: bool) -> str:
    return commit_payload_fingerprint(
        {
            "action": CommitAction.COMMIT,
            "blocked": blocked,
            "run_id": context.run_id,
            "target": context.target,
        },
        schema="pheroos-conformance-resolved-stop-set-v1",
        profile=context.profile,
    )


def _issue_permission(
    context: ActiveCommitContext,
    *,
    decision_ref: str,
    authority: AuthorityLevel,
    allowed: bool,
    trace_event_id: str,
) -> ActionPermission:
    return issue_action_permission(
        permission_id="permission:conformance:commit:v1",
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id,
        target=context.target,
        action=CommitAction.COMMIT,
        epoch=context.epoch,
        decision_ref=decision_ref,
        certificate_ref="",
        allowed=allowed,
        reason_codes=(
            ("policy_allowed",) if allowed else ("advisory_has_no_commit_authority",)
        ),
        issuer_id="governance:conformance:policy",
        policy_ref="policy:conformance:commit:v1",
        authority=authority,
        issued_at_step=_ISSUED_AT_STEP,
        expires_at_step=_EXPIRES_AT_STEP,
        provenance="urn:pheroos:conformance:action-permission",
        trace_event_id=trace_event_id,
    )


def _permission_matches(
    permission: ActionPermission,
    context: ActiveCommitContext,
    *,
    decision_ref: str,
    current_step: int,
    target: str | None = None,
    run_id: str | None = None,
    action: CommitAction = CommitAction.COMMIT,
    require_allowed: bool = True,
) -> bool:
    return action_permission_matches(
        permission,
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id if run_id is None else run_id,
        target=context.target if target is None else target,
        action=action,
        epoch=context.epoch,
        decision_ref=decision_ref,
        certificate_ref="",
        current_step=current_step,
        require_allowed=require_allowed,
    )


def _permission_issuance_rejected(
    context: ActiveCommitContext,
    *,
    decision_ref: str,
    authority: AuthorityLevel,
    allowed: bool,
    trace_event_id: str,
) -> bool:
    try:
        _issue_permission(
            context,
            decision_ref=decision_ref,
            authority=authority,
            allowed=allowed,
            trace_event_id=trace_event_id,
        )
    except GovernanceError:
        return True
    return False


def _issue_stop_verification(
    context: ActiveCommitContext,
    *,
    decision_ref: str,
    authority: AuthorityLevel,
    blocked: bool,
    trace_event_id: str,
) -> StopResolutionVerification:
    return verify_stop_resolution(
        StopResolution(
            target=context.target,
            action=CommitAction.COMMIT.value,
            blocked=blocked,
            reason=("active hard stop" if blocked else "no active hard stop"),
        ),
        resolution_id="stop-resolution:conformance:commit:v1",
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id,
        epoch=context.epoch,
        decision_ref=decision_ref,
        certificate_ref="",
        resolved_stop_root=_resolved_stop_root(context, blocked=blocked),
        verifier_id="governance:conformance:stop",
        authority=authority,
        issued_at_step=_ISSUED_AT_STEP,
        expires_at_step=_EXPIRES_AT_STEP,
        provenance="urn:pheroos:conformance:stop-resolution",
        trace_event_id=trace_event_id,
    )


def _stop_matches(
    verification: StopResolutionVerification,
    context: ActiveCommitContext,
    *,
    decision_ref: str,
    current_step: int,
    target: str | None = None,
    action: CommitAction = CommitAction.COMMIT,
    require_unblocked: bool = True,
) -> bool:
    return stop_resolution_verification_matches(
        verification,
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id,
        target=context.target if target is None else target,
        action=action,
        epoch=context.epoch,
        decision_ref=decision_ref,
        certificate_ref="",
        current_step=current_step,
        require_unblocked=require_unblocked,
    )


def _stop_issuance_rejected(
    context: ActiveCommitContext,
    *,
    decision_ref: str,
    authority: AuthorityLevel,
    blocked: bool,
    trace_event_id: str,
) -> bool:
    try:
        _issue_stop_verification(
            context,
            decision_ref=decision_ref,
            authority=authority,
            blocked=blocked,
            trace_event_id=trace_event_id,
        )
    except GovernanceError:
        return True
    return False


__all__ = ["check"]
