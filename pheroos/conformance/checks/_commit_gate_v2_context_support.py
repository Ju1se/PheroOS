"""Public-governance fixtures for the Commit Gate v2 Conformance matrix."""

from __future__ import annotations

from dataclasses import dataclass

from pheroos.conformance.checks._support_v2_context_support import (
    SupportV2ConformanceContext,
    advance_support_v2,
    commit_upstreams_v2,
    initialize_v2,
    support_state_v2,
)
from pheroos.conformance.checks._support_v2_manifest_support import (
    PROFILE,
    RUN_REF,
    TARGET_REF,
    manifest_v2,
    root_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.commit_gate_v2 import (
    CommitPermissionRequestV2,
    CommitPermissionSnapshotV2,
    CommitStopRequestV2,
    CommitStopSnapshotV2,
    VerifiedCommitPermissionSourceV2,
    VerifiedCommitStopSourceV2,
    issue_commit_permission_v2,
    open_commit_permission_authority_session_v2,
    open_commit_stop_authority_session_v2,
    prepare_commit_permission_issue_v2,
    prepare_commit_stop_resolution_v2,
    resolve_commit_stop_v2,
)
from pheroos.governance.commit_state_v2 import (
    VerifiedCommitReplayStateV2,
    advance_commit_replay_state_v2,
    open_commit_replay_authority_session_v2,
    prepare_commit_replay_advance_v2,
    rehydrate_commit_replay_state_v2,
)
from pheroos.governance.risk_v2 import (
    RiskBand,
    VerifiedRiskStateV2,
    advance_risk_state_v2,
    open_risk_authority_session_v2,
    prepare_risk_state_advance_v2,
    rehydrate_risk_state_v2,
)
from pheroos.governance.support_v2 import (
    PrincipalVerificationRecordV2,
    VerifiedMembershipStateV2,
    VerifiedPrincipalVerificationSetStateV2,
    VerifiedSupportStateV2,
    advance_principal_verification_set_v2,
    open_principal_verification_authority_session_v2,
    prepare_principal_verification_set_v2,
)
from pheroos.protocol import CommitAssurance, ScopedProtocolManifestV2
from pheroos.protocol.commit_wire import commit_policy_fingerprint


GATE_EPOCH_V2 = 50
GATE_STEP_V2 = 6


@dataclass(frozen=True, slots=True)
class CommitGateV2ConformanceContext:
    adapter: GovernanceStateStoreConformanceAdapterV2
    domain: AuthorityDomainV2
    store: GovernanceStateStoreV2
    grant: GovernanceIssuerGrantV2
    manifest: ScopedProtocolManifestV2
    verification_state: VerifiedPrincipalVerificationSetStateV2
    replay_state: VerifiedCommitReplayStateV2
    risk_state: VerifiedRiskStateV2
    membership_state: VerifiedMembershipStateV2
    support_state: VerifiedSupportStateV2


def commit_gate_context_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    label: str,
) -> CommitGateV2ConformanceContext:
    domain = adapter.create_domain_v2(f"scope:commit-gate-v2:{label}")
    store = adapter.create_store_v2((domain,))
    grant = GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:commit-gate-v2",
        grant_ref="grant:commit-gate-v2",
        grant_binding_ref=root_v2(f"commit-gate-v2:binding:{label}"),
        operations=(
            GovernanceIssuerOperationV2.EVALUATE_QUORUM,
            GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
            GovernanceIssuerOperationV2.RESOLVE_STOP,
            GovernanceIssuerOperationV2.ADVANCE_REPLAY,
            GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
            GovernanceIssuerOperationV2.RETIRE_DOMAIN,
        ),
        target_refs=(TARGET_REF,),
        action_refs=("commit",),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100_000,
        revocation_generation=0,
    )
    activated = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        f"transition:commit-gate-v2:grant:{label}",
        1,
    )
    if activated.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise RuntimeError("Commit Gate v2 Conformance grant activation failed")
    base = SupportV2ConformanceContext(
        adapter=adapter,
        domain=domain,
        store=store,
        grant=grant,
        manifest=manifest_v2(domain.profile),
    )
    upstreams = commit_upstreams_v2(base, label=label)
    support_request, support_source = initialize_v2(base, label)
    if (
        advance_support_v2(base, support_request, support_source).disposition
        is not GovernanceCommitDispositionV2.COMMITTED
    ):
        raise RuntimeError("Commit Gate v2 Conformance Support commit failed")
    support = support_state_v2(base, support_request)

    policy = base.manifest.collective_commit_policy
    if policy is None:
        raise RuntimeError("Commit Gate v2 Conformance policy is missing")
    replay_request, replay_source = prepare_commit_replay_advance_v2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        manifest_root=base.manifest.manifest_root,
        commit_policy_root=commit_policy_fingerprint(policy, profile=PROFILE),
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        protocol_ref=base.manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        observed_epoch=5,
        advance_ref=f"advance:commit-gate-v2:replay:{label}",
        current_step=4,
        receipt_additions=(),
    )
    replay_session = open_commit_replay_authority_session_v2(
        capability_v2(store, domain, grant, replay_request.observed_epoch),
        replay_request,
    )
    if (
        advance_commit_replay_state_v2(
            replay_request,
            source=replay_source,
            authority_session=replay_session,
        ).disposition
        is not GovernanceCommitDispositionV2.COMMITTED
    ):
        raise RuntimeError("Commit Gate v2 Conformance Replay commit failed")
    replay = rehydrate_commit_replay_state_v2(
        replay_request.to_dict(), domain=domain, state_reader=store
    )

    risk_request, risk_source = prepare_risk_state_advance_v2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        manifest=base.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        epoch=1,
        advance_ref=f"advance:commit-gate-v2:risk:{label}",
        current_step=4,
        assessment_ref=f"assessment:commit-gate-v2:{label}",
        risk_band=RiskBand.LOW,
        risk_input_roots=(root_v2(f"risk-input:{label}"),),
        rationale_codes=("risk:low",),
        assessment_method="deterministic-conformance-v2",
        issuer_ref=grant.issuer_ref,
        issued_at_step=4,
        expires_at_step=90_000,
        provenance_ref=f"urn:pheroos:conformance:commit-gate:risk:{label}",
        source_trace_roots=(root_v2(f"risk-trace:{label}"),),
    )
    risk_session = open_risk_authority_session_v2(
        capability_v2(store, domain, grant, risk_request.observed_epoch),
        risk_request,
    )
    if (
        advance_risk_state_v2(
            risk_request,
            source=risk_source,
            authority_session=risk_session,
        ).disposition
        is not GovernanceCommitDispositionV2.COMMITTED
    ):
        raise RuntimeError("Commit Gate v2 Conformance Risk commit failed")
    risk = rehydrate_risk_state_v2(
        risk_request.to_dict(), domain=domain, state_reader=store
    )
    return CommitGateV2ConformanceContext(
        adapter,
        domain,
        store,
        grant,
        base.manifest,
        upstreams.verification_state,
        replay,
        risk,
        upstreams.membership_state,
        support,
    )


def capability_v2(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    observed_epoch: int = GATE_EPOCH_V2,
) -> GovernanceIssuerCapabilityV2:
    return bind_governance_issuer_capability_v2(
        store, domain, grant, RUN_REF, observed_epoch
    )


def advance_verification_only_v2(
    context: CommitGateV2ConformanceContext,
    label: str,
) -> GovernanceCommitAttemptV2:
    """Advance only PV so Gate Conformance can prove transitive CAS closure."""

    parent = context.verification_state.snapshot
    record = PrincipalVerificationRecordV2(
        principal_ref="principal:alpha",
        cluster_ref="cluster:alpha",
        failure_domain_ref="failure-domain:alpha",
        verification_method="external-attestation-v2",
        verification_issuer_ref="identity:verifier",
        attestation_root=root_v2(f"gate-verification-attestation:{label}"),
        evidence_roots=(root_v2(f"gate-verification-evidence:{label}"),),
        issued_at_step=1,
        expires_at_step=90_000,
        provenance_ref=f"urn:pheroos:conformance:gate-verification:{label}",
        source_trace_roots=(root_v2(f"gate-verification-trace:{label}"),),
    )
    request, source = prepare_principal_verification_set_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        epoch=parent.epoch + 1,
        observed_epoch=GATE_EPOCH_V2,
        advance_ref=f"advance:commit-gate-v2:verification:{label}",
        snapshot_ref=f"snapshot:commit-gate-v2:verification:{label}",
        current_step=parent.current_step + 1,
        expires_at_step=80_000,
        mutation_issuer_ref=context.grant.issuer_ref,
        records=(record,),
        parent_snapshot=parent,
    )
    session = open_principal_verification_authority_session_v2(
        capability_v2(
            context.store,
            context.domain,
            context.grant,
            request.observed_epoch,
        ),
        request,
    )
    return advance_principal_verification_set_v2(
        request,
        source=source,
        authority_session=session,
    )


def prepare_stop_v2(
    context: CommitGateV2ConformanceContext,
    label: str,
    *,
    blocked: bool = False,
    parent: CommitStopSnapshotV2 | None = None,
) -> tuple[CommitStopRequestV2, VerifiedCommitStopSourceV2]:
    return prepare_commit_stop_resolution_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        observed_epoch=GATE_EPOCH_V2,
        resolution_ref=f"resolution:commit-gate-v2:{label}",
        current_step=GATE_STEP_V2,
        mutation_issuer_ref=context.grant.issuer_ref,
        blocked=blocked,
        reason_codes=("stop:blocked",) if blocked else ("stop:clear",),
        issued_at_step=GATE_STEP_V2,
        expires_at_step=GATE_STEP_V2 + 10,
        commit_replay_state=context.replay_state,
        risk_state=context.risk_state,
        membership_state=context.membership_state,
        support_state=context.support_state,
        parent_snapshot=parent,
    )


def prepare_permission_v2(
    context: CommitGateV2ConformanceContext,
    label: str,
    *,
    allowed: bool = True,
    parent: CommitPermissionSnapshotV2 | None = None,
) -> tuple[CommitPermissionRequestV2, VerifiedCommitPermissionSourceV2]:
    return prepare_commit_permission_issue_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        observed_epoch=GATE_EPOCH_V2,
        permission_ref=f"permission:commit-gate-v2:{label}",
        current_step=GATE_STEP_V2,
        mutation_issuer_ref=context.grant.issuer_ref,
        allowed=allowed,
        claim_roots=(root_v2(f"claim:{label}"),) if allowed else (),
        issued_at_step=GATE_STEP_V2,
        expires_at_step=GATE_STEP_V2 + 10,
        commit_replay_state=context.replay_state,
        risk_state=context.risk_state,
        membership_state=context.membership_state,
        support_state=context.support_state,
        parent_snapshot=parent,
    )


def resolve_stop_v2(
    context: CommitGateV2ConformanceContext,
    request: CommitStopRequestV2,
    source: object,
) -> GovernanceCommitAttemptV2:
    session = open_commit_stop_authority_session_v2(
        capability_v2(
            context.store, context.domain, context.grant, request.observed_epoch
        ),
        request,
    )
    return resolve_commit_stop_v2(request, source=source, authority_session=session)


def issue_permission_v2(
    context: CommitGateV2ConformanceContext,
    request: CommitPermissionRequestV2,
    source: object,
) -> GovernanceCommitAttemptV2:
    session = open_commit_permission_authority_session_v2(
        capability_v2(
            context.store, context.domain, context.grant, request.observed_epoch
        ),
        request,
    )
    return issue_commit_permission_v2(request, source=source, authority_session=session)


__all__: tuple[str, ...] = ()
