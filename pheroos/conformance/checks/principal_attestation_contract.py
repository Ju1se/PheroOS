from __future__ import annotations

from dataclasses import replace

from pheroos.conformance.checks._commit_context import (
    ActiveCommitContext,
    active_commit_context,
)
from pheroos.conformance.report import CheckResult
from pheroos.governance import (
    AuthorityLevel,
    PrincipalAttestation,
    PrincipalVerification,
    principal_attestation_fingerprint,
    principal_verification_is_authoritative,
    principal_verification_matches,
    verify_principal_attestation,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol import CapabilityManifest


_ISSUED_AT_STEP = 4
_CURRENT_STEP = 5
_EXPIRES_AT_STEP = 9


def check(manifest: CapabilityManifest) -> CheckResult:
    context = active_commit_context(manifest)
    if context is None:
        return CheckResult("principal_attestation_contract", True)

    problems: list[str] = []
    attestation = _attestation()
    fingerprint = principal_attestation_fingerprint(attestation)
    if fingerprint != principal_attestation_fingerprint(_attestation()):
        problems.append("attestation_fingerprint_nondeterministic")

    verification = _issue_verification(
        context,
        attestation,
        authority=AuthorityLevel.GOVERNANCE,
        current_step=_CURRENT_STEP,
        trace_event_id="trace:conformance:principal:issued",
    )
    problems.extend(_issued_verification_problems(verification, context))
    problems.extend(_scope_replay_problems(verification, context))
    problems.extend(_tamper_problems(context, attestation))
    problems.extend(_issuance_authority_problems(context, attestation))

    unique = sorted(set(problems))
    return CheckResult(
        "principal_attestation_contract",
        not unique,
        ", ".join(unique),
    )


def _issued_verification_problems(
    verification: PrincipalVerification,
    context: ActiveCommitContext,
) -> list[str]:
    problems: list[str] = []
    if not principal_verification_is_authoritative(verification):
        problems.append("issued_verification_not_authoritative")
    if not _matches(verification, context, current_step=_CURRENT_STEP):
        problems.append("issued_verification_does_not_match")

    forged = replace(verification)
    if principal_verification_is_authoritative(forged):
        problems.append("direct_verification_forgery_accepted")
    return problems


def _scope_replay_problems(
    verification: PrincipalVerification,
    context: ActiveCommitContext,
) -> list[str]:
    problems: list[str] = []
    if _matches(
        verification,
        context,
        current_step=_CURRENT_STEP,
        target=f"{context.target}:cross-scope",
    ):
        problems.append("cross_target_replay_accepted")
    if _matches(
        verification,
        context,
        current_step=_CURRENT_STEP,
        run_id=f"{context.run_id}:cross-scope",
    ):
        problems.append("cross_run_replay_accepted")
    if _matches(
        verification,
        context,
        current_step=_CURRENT_STEP,
        epoch=context.epoch + 1,
    ):
        problems.append("cross_epoch_replay_accepted")
    if _matches(
        verification,
        context,
        current_step=_CURRENT_STEP,
        cluster_id="cluster:cross-scope",
    ):
        problems.append("cross_cluster_replay_accepted")
    if _matches(verification, context, current_step=_EXPIRES_AT_STEP):
        problems.append("expired_verification_accepted")
    return problems


def _tamper_problems(
    context: ActiveCommitContext,
    attestation: PrincipalAttestation,
) -> list[str]:
    tampered = _issue_verification(
        context,
        attestation,
        authority=AuthorityLevel.GOVERNANCE,
        current_step=_CURRENT_STEP,
        trace_event_id="trace:conformance:principal:tamper",
    )
    object.__setattr__(tampered, "cluster_id", "cluster:tampered")
    if principal_verification_is_authoritative(tampered):
        return ["tampered_verification_accepted"]
    return []


def _issuance_authority_problems(
    context: ActiveCommitContext,
    attestation: PrincipalAttestation,
) -> list[str]:
    problems: list[str] = []
    if not _issuance_rejected(
        context,
        attestation,
        authority=AuthorityLevel.AGENT,
        current_step=_CURRENT_STEP,
        trace_event_id="trace:conformance:principal:forged-authority",
    ):
        problems.append("agent_verification_authority_accepted")
    if not _issuance_rejected(
        context,
        attestation,
        authority=AuthorityLevel.GOVERNANCE,
        current_step=_EXPIRES_AT_STEP,
        trace_event_id="trace:conformance:principal:expired",
    ):
        problems.append("expired_attestation_issuance_accepted")
    return problems


def _attestation() -> PrincipalAttestation:
    return PrincipalAttestation(
        principal_id="principal:conformance:alpha",
        attestation_ref="attestation:conformance:alpha:v1",
        method="external-verifier-v1",
        issuer_id="issuer:conformance:identity",
        issued_at_step=_ISSUED_AT_STEP,
        expires_at_step=_EXPIRES_AT_STEP,
        provenance="urn:pheroos:conformance:principal-attestation",
        nonce="nonce:conformance:principal:alpha",
        trace_event_id="trace:conformance:principal:attestation",
    )


def _issue_verification(
    context: ActiveCommitContext,
    attestation: PrincipalAttestation,
    *,
    authority: AuthorityLevel,
    current_step: int,
    trace_event_id: str,
) -> PrincipalVerification:
    return verify_principal_attestation(
        attestation,
        profile=context.profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        protocol_id=context.protocol_id,
        run_id=context.run_id,
        target=context.target,
        epoch=context.epoch,
        cluster_id="cluster:conformance:alpha",
        failure_domain="failure-domain:conformance:east",
        verifier_id="governance:conformance:identity",
        authority=authority,
        current_step=current_step,
        provenance="urn:pheroos:conformance:principal-verification",
        trace_event_id=trace_event_id,
    )


def _matches(
    verification: PrincipalVerification,
    context: ActiveCommitContext,
    *,
    current_step: int,
    target: str | None = None,
    run_id: str | None = None,
    epoch: int | None = None,
    cluster_id: str = "cluster:conformance:alpha",
) -> bool:
    return bool(
        principal_verification_matches(
            verification,
            profile=context.profile,
            assurance=context.assurance,
            manifest_root=context.manifest_root,
            commit_policy_root=context.commit_policy_root,
            protocol_id=context.protocol_id,
            run_id=context.run_id if run_id is None else run_id,
            target=context.target if target is None else target,
            epoch=context.epoch if epoch is None else epoch,
            principal_id="principal:conformance:alpha",
            cluster_id=cluster_id,
            current_step=current_step,
        )
    )


def _issuance_rejected(
    context: ActiveCommitContext,
    attestation: PrincipalAttestation,
    *,
    authority: AuthorityLevel,
    current_step: int,
    trace_event_id: str,
) -> bool:
    try:
        _issue_verification(
            context,
            attestation,
            authority=authority,
            current_step=current_step,
            trace_event_id=trace_event_id,
        )
    except GovernanceError:
        return True
    return False


__all__ = ["check"]
