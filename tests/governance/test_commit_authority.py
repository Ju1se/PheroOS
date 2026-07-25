from __future__ import annotations

import pytest

from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.errors import GovernanceError
from pheroos.governance.permission import (
    ActionPermission,
    action_permission_is_authoritative,
    action_permission_matches,
    issue_action_permission,
)
from pheroos.governance.principal import (
    PrincipalAttestation,
    PrincipalVerification,
    principal_attestation_fingerprint,
    principal_verification_is_authoritative,
    principal_verification_matches,
    verify_principal_attestation,
)
from pheroos.governance.stop_signal import (
    CommitAction,
    StopResolution,
    StopResolutionVerification,
    stop_resolution_verification_is_authoritative,
    stop_resolution_verification_matches,
    verify_stop_resolution,
)
from pheroos.protocol import CommitAssurance


MANIFEST_ROOT = "sha256:" + ("1" * 64)
COMMIT_POLICY_ROOT = "sha256:" + ("2" * 64)
ASSESSMENT_REF = "sha256:" + ("3" * 64)
CERTIFICATE_REF = "sha256:" + ("4" * 64)
RESOLVED_STOP_ROOT = "sha256:" + ("5" * 64)


def attestation(**overrides: object) -> PrincipalAttestation:
    values: dict[str, object] = {
        "principal_id": "principal:alpha",
        "attestation_ref": "opaque:attestation:alpha",
        "method": "external-verifier-v1",
        "issuer_id": "issuer:identity",
        "issued_at_step": 1,
        "expires_at_step": 10,
        "provenance": "urn:test:principal",
        "nonce": "nonce:principal:1",
        "trace_event_id": "trace:principal:1",
    }
    values.update(overrides)
    return PrincipalAttestation(**values)  # type: ignore[arg-type]


def verified_principal() -> PrincipalVerification:
    return verify_principal_attestation(
        attestation(),
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        epoch=3,
        cluster_id="cluster:one",
        failure_domain="domain:east",
        verifier_id="governance:identity",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=2,
        provenance="urn:test:principal-verification",
        trace_event_id="trace:principal:verified",
    )


def verified_stop() -> StopResolutionVerification:
    return verify_stop_resolution(
        StopResolution(
            target="decision:collective",
            action="commit",
            blocked=False,
            reason="no active hard stop",
        ),
        resolution_id="stop-resolution:1",
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        epoch=3,
        decision_ref=ASSESSMENT_REF,
        certificate_ref="",
        resolved_stop_root=RESOLVED_STOP_ROOT,
        verifier_id="governance:stop",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=4,
        expires_at_step=8,
        provenance="urn:test:stop",
        trace_event_id="trace:stop:verified",
    )


def issued_permission(
    *, action: CommitAction = CommitAction.COMMIT
) -> ActionPermission:
    return issue_action_permission(
        permission_id="permission:1",
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        action=action,
        epoch=3,
        decision_ref=ASSESSMENT_REF,
        certificate_ref=(
            CERTIFICATE_REF
            if action in {CommitAction.PUBLISH, CommitAction.EXECUTE}
            else ""
        ),
        allowed=True,
        reason_codes=("policy_allowed",),
        issuer_id="governance:policy",
        policy_ref="policy:commit:v1",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=4,
        expires_at_step=8,
        provenance="urn:test:permission",
        trace_event_id="trace:permission:issued",
    )


def test_principal_attestation_is_strict_and_fingerprinted() -> None:
    first = principal_attestation_fingerprint(attestation())
    second = principal_attestation_fingerprint(attestation())
    assert first == second
    assert first.startswith("sha256:")

    with pytest.raises(GovernanceError, match="expiry"):
        attestation(expires_at_step=1)
    with pytest.raises(GovernanceError, match="NFC string"):
        attestation(principal_id=" principal:alpha ")


def test_principal_cluster_is_governance_verified_not_self_asserted() -> None:
    forged = PrincipalVerification(
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        epoch=3,
        principal_id="principal:alpha",
        cluster_id="cluster:forged",
        failure_domain="domain:forged",
        attestation_fingerprint=principal_attestation_fingerprint(attestation()),
        verified_issuer_id="issuer:identity",
        verified_method="external-verifier-v1",
        verifier_id="agent:forger",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=2,
        expires_at_step=10,
        provenance="urn:test:forged",
        trace_event_id="trace:forged",
    )
    issued = verified_principal()

    assert principal_verification_is_authoritative(forged) is False
    assert principal_verification_is_authoritative(issued) is True
    assert principal_verification_matches(
        issued,
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        epoch=3,
        principal_id="principal:alpha",
        cluster_id="cluster:one",
        current_step=9,
    )
    assert not principal_verification_matches(
        issued,
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        epoch=3,
        principal_id="principal:alpha",
        cluster_id="cluster:one",
        current_step=10,
    )
    assert not principal_verification_matches(
        issued,
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:other",
        epoch=3,
        principal_id="principal:alpha",
        cluster_id="cluster:one",
        current_step=9,
    )
    assert not principal_verification_matches(
        issued,
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        epoch=4,
        principal_id="principal:alpha",
        cluster_id="cluster:one",
        current_step=9,
    )

    object.__setattr__(issued, "cluster_id", "cluster:tampered")
    assert principal_verification_is_authoritative(issued) is False


def test_principal_verification_requires_governance_and_fresh_attestation() -> None:
    with pytest.raises(GovernanceError, match="governance authority"):
        verify_principal_attestation(
            attestation(),
            profile="pheroos-commit-integrity-v1",
            assurance=CommitAssurance.EVIDENCE_BOUND,
            manifest_root=MANIFEST_ROOT,
            commit_policy_root=COMMIT_POLICY_ROOT,
            protocol_id="protocol:optimal",
            run_id="run:1",
            target="decision:collective",
            epoch=3,
            cluster_id="cluster:one",
            failure_domain="domain:east",
            verifier_id="agent:alpha",
            authority=AuthorityLevel.AGENT,
            current_step=2,
            provenance="urn:test:principal-verification",
            trace_event_id="trace:principal:verified",
        )
    with pytest.raises(GovernanceError, match="not fresh"):
        verify_principal_attestation(
            attestation(),
            profile="pheroos-commit-integrity-v1",
            assurance=CommitAssurance.EVIDENCE_BOUND,
            manifest_root=MANIFEST_ROOT,
            commit_policy_root=COMMIT_POLICY_ROOT,
            protocol_id="protocol:optimal",
            run_id="run:1",
            target="decision:collective",
            epoch=3,
            cluster_id="cluster:one",
            failure_domain="domain:east",
            verifier_id="governance:identity",
            authority=AuthorityLevel.GOVERNANCE,
            current_step=10,
            provenance="urn:test:principal-verification",
            trace_event_id="trace:principal:verified",
        )


def test_stop_resolution_is_exactly_bound_and_tamper_evident() -> None:
    verification = verified_stop()
    assert stop_resolution_verification_is_authoritative(verification)
    assert stop_resolution_verification_matches(
        verification,
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        action=CommitAction.COMMIT,
        epoch=3,
        decision_ref=ASSESSMENT_REF,
        certificate_ref="",
        current_step=7,
    )
    assert not stop_resolution_verification_matches(
        verification,
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        action=CommitAction.PUBLISH,
        epoch=3,
        decision_ref=ASSESSMENT_REF,
        certificate_ref="",
        current_step=7,
    )
    assert not stop_resolution_verification_matches(
        verification,
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        action=CommitAction.COMMIT,
        epoch=4,
        decision_ref=ASSESSMENT_REF,
        certificate_ref="",
        current_step=7,
    )
    assert not stop_resolution_verification_matches(
        verification,
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        action=CommitAction.COMMIT,
        epoch=3,
        decision_ref=ASSESSMENT_REF,
        certificate_ref="",
        current_step=8,
    )

    object.__setattr__(verification, "blocked", True)
    assert stop_resolution_verification_is_authoritative(verification) is False


def test_direct_stop_verification_and_unknown_action_fail_closed() -> None:
    issued = verified_stop()
    forged = StopResolutionVerification(
        resolution_id=issued.resolution_id,
        profile=issued.profile,
        assurance=issued.assurance,
        manifest_root=issued.manifest_root,
        commit_policy_root=issued.commit_policy_root,
        protocol_id=issued.protocol_id,
        run_id=issued.run_id,
        target=issued.target,
        action=issued.action,
        epoch=issued.epoch,
        decision_ref=issued.decision_ref,
        certificate_ref=issued.certificate_ref,
        resolved_stop_root=issued.resolved_stop_root,
        blocked=issued.blocked,
        reason=issued.reason,
        resolution_fingerprint=issued.resolution_fingerprint,
        verifier_id=issued.verifier_id,
        authority=issued.authority,
        issued_at_step=issued.issued_at_step,
        expires_at_step=issued.expires_at_step,
        provenance=issued.provenance,
        trace_event_id=issued.trace_event_id,
    )
    assert stop_resolution_verification_is_authoritative(forged) is False
    with pytest.raises(GovernanceError, match="unsupported"):
        verify_stop_resolution(
            StopResolution(
                target="decision:collective",
                action="custom-dangerous-action",
                blocked=False,
                reason="caller assertion",
            ),
            resolution_id="stop-resolution:2",
            profile="pheroos-commit-integrity-v1",
            assurance=CommitAssurance.EVIDENCE_BOUND,
            manifest_root=MANIFEST_ROOT,
            commit_policy_root=COMMIT_POLICY_ROOT,
            protocol_id="protocol:optimal",
            run_id="run:1",
            epoch=3,
            decision_ref=ASSESSMENT_REF,
            certificate_ref="",
            resolved_stop_root=RESOLVED_STOP_ROOT,
            verifier_id="governance:stop",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=4,
            expires_at_step=8,
            provenance="urn:test:stop",
            trace_event_id="trace:stop:verified",
        )


def test_action_permission_rejects_caller_bool_and_cross_scope_replay() -> None:
    permission = issued_permission()
    assert action_permission_is_authoritative(permission)
    assert action_permission_matches(
        permission,
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        action=CommitAction.COMMIT,
        epoch=3,
        decision_ref=ASSESSMENT_REF,
        certificate_ref="",
        current_step=7,
    )
    assert not action_permission_matches(  # type: ignore[arg-type]
        True,
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        action=CommitAction.COMMIT,
        epoch=3,
        decision_ref=ASSESSMENT_REF,
        certificate_ref="",
        current_step=7,
    )
    assert not action_permission_matches(
        permission,
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:other",
        action=CommitAction.COMMIT,
        epoch=3,
        decision_ref=ASSESSMENT_REF,
        certificate_ref="",
        current_step=7,
    )
    assert not action_permission_matches(
        permission,
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        action=CommitAction.PUBLISH,
        epoch=3,
        decision_ref=ASSESSMENT_REF,
        certificate_ref="",
        current_step=7,
    )


def test_action_permission_requires_governance_and_detects_mutation() -> None:
    with pytest.raises(GovernanceError, match="governance authority"):
        issue_action_permission(
            permission_id="permission:forged",
            profile="pheroos-commit-integrity-v1",
            assurance=CommitAssurance.EVIDENCE_BOUND,
            manifest_root=MANIFEST_ROOT,
            commit_policy_root=COMMIT_POLICY_ROOT,
            protocol_id="protocol:optimal",
            run_id="run:1",
            target="decision:collective",
            action=CommitAction.COMMIT,
            epoch=3,
            decision_ref=ASSESSMENT_REF,
            certificate_ref="",
            allowed=True,
            reason_codes=("caller_allowed",),
            issuer_id="agent:alpha",
            policy_ref="policy:caller",
            authority=AuthorityLevel.AGENT,
            issued_at_step=4,
            expires_at_step=8,
            provenance="urn:test:forged",
            trace_event_id="trace:forged",
        )

    permission = issued_permission()
    object.__setattr__(permission, "allowed", False)
    assert action_permission_is_authoritative(permission) is False


def test_blocked_stop_is_authoritative_denial_but_does_not_allow_action() -> None:
    blocked = verify_stop_resolution(
        StopResolution(
            target="decision:collective",
            action="commit",
            blocked=True,
            reason="active hard stop",
        ),
        resolution_id="stop-resolution:blocked",
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        epoch=3,
        decision_ref=ASSESSMENT_REF,
        certificate_ref="",
        resolved_stop_root=RESOLVED_STOP_ROOT,
        verifier_id="governance:stop",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=4,
        expires_at_step=8,
        provenance="urn:test:stop",
        trace_event_id="trace:stop:blocked",
    )
    match_args = {
        "profile": "pheroos-commit-integrity-v1",
        "assurance": CommitAssurance.EVIDENCE_BOUND,
        "manifest_root": MANIFEST_ROOT,
        "commit_policy_root": COMMIT_POLICY_ROOT,
        "protocol_id": "protocol:optimal",
        "run_id": "run:1",
        "target": "decision:collective",
        "action": CommitAction.COMMIT,
        "epoch": 3,
        "decision_ref": ASSESSMENT_REF,
        "certificate_ref": "",
        "current_step": 7,
    }

    assert stop_resolution_verification_is_authoritative(blocked)
    assert not stop_resolution_verification_matches(blocked, **match_args)
    assert stop_resolution_verification_matches(
        blocked,
        **match_args,
        require_unblocked=False,
    )


def test_permission_and_stop_reject_cross_assurance_policy_or_missing_certificate() -> (
    None
):
    permission = issued_permission()
    assert not action_permission_matches(
        permission,
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.ADVISORY,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        action=CommitAction.COMMIT,
        epoch=3,
        decision_ref=ASSESSMENT_REF,
        certificate_ref="",
        current_step=7,
    )
    assert not action_permission_matches(
        permission,
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root="sha256:" + ("9" * 64),
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        action=CommitAction.COMMIT,
        epoch=3,
        decision_ref=ASSESSMENT_REF,
        certificate_ref="",
        current_step=7,
    )
    with pytest.raises(GovernanceError, match="requires a certificate_ref"):
        issue_action_permission(
            permission_id="permission:publish",
            profile="pheroos-distributed-commit-v1",
            assurance=CommitAssurance.DISTRIBUTED,
            manifest_root=MANIFEST_ROOT,
            commit_policy_root=COMMIT_POLICY_ROOT,
            protocol_id="protocol:optimal",
            run_id="run:1",
            target="decision:collective",
            action=CommitAction.PUBLISH,
            epoch=3,
            decision_ref=ASSESSMENT_REF,
            certificate_ref="",
            allowed=True,
            reason_codes=("policy_allowed",),
            issuer_id="governance:policy",
            policy_ref="policy:publish:v1",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=4,
            expires_at_step=8,
            provenance="urn:test:permission",
            trace_event_id="trace:permission:publish",
        )


def test_authority_fingerprint_fields_reject_malformed_sha256_refs() -> None:
    with pytest.raises(GovernanceError, match="sha256 authority fingerprint"):
        issue_action_permission(
            permission_id="permission:bad-ref",
            profile="pheroos-commit-integrity-v1",
            assurance=CommitAssurance.EVIDENCE_BOUND,
            manifest_root=MANIFEST_ROOT,
            commit_policy_root=COMMIT_POLICY_ROOT,
            protocol_id="protocol:optimal",
            run_id="run:1",
            target="decision:collective",
            action=CommitAction.COMMIT,
            epoch=3,
            decision_ref="sha256:assessment",
            certificate_ref="",
            allowed=True,
            reason_codes=("policy_allowed",),
            issuer_id="governance:policy",
            policy_ref="policy:commit:v1",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=4,
            expires_at_step=8,
            provenance="urn:test:permission",
            trace_event_id="trace:permission:bad-ref",
        )
