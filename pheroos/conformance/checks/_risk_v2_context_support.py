"""Public ABI fixtures for the durable Risk v2 Conformance matrix."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256

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
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceStateStoreV2,
    AuthorityDomainV2,
)
from pheroos.governance.risk_v2 import (
    RiskBand,
    RiskStateAdvanceRequestV2,
    RiskStateSnapshotV2,
    VerifiedRiskSourceV2,
    advance_risk_state_v2,
    open_risk_authority_session_v2,
    prepare_risk_state_advance_v2,
)
from pheroos.protocol import (
    BASELINE_OUTPUT_POLICY_VERSION_V2,
    COMMIT_CANONICAL_VERSION,
    COMMIT_INTEGRITY_PROFILE_VERSION,
    COMMIT_MODEL,
    COMMIT_POLICY_VERSION,
    COMMIT_WIRE_VERSION,
    PROTOCOL_VERSION_V2,
    REQUIRED_COMMIT_RESET_RULES,
    BaselineOutputActionPolicyV2,
    BaselineOutputPolicyV2,
    CandidateSpec,
    CertificatePolicy,
    CollectiveCommitPolicy,
    CommitAssurance,
    CommitWindowPolicy,
    EvidencePolicy,
    EvidenceQualificationPolicy,
    QuorumPolicy,
    RiskBandPolicy,
    ScopedAuthorityPolicyV2,
    ScopedProtocolManifestV2,
    SupportLeasePolicy,
    TargetSpec,
    TerminalOutcomePolicy,
    TracePolicy,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


RUN_REF = "run:risk-v2-conformance"
TARGET_REF = "decision:risk-v2"
FALLBACK_REF = "candidate:risk-v2:safe"
ACTION_REF = "action:risk-v2:publish"
ISSUER_REF = "issuer:risk-v2-conformance"
BASE_EPOCH = 7

_BASELINE_TRACE_EVENTS = (
    "baseline_action_permission_issued",
    "baseline_decision_evaluated",
    "baseline_evidence_qualified",
    "baseline_manifest_activated",
    "baseline_output_committed",
    "baseline_stop_resolved",
)


@dataclass(frozen=True, slots=True)
class RiskV2ConformanceContext:
    domain: AuthorityDomainV2
    store: GovernanceStateStoreV2
    grant: GovernanceIssuerGrantV2
    capability: GovernanceIssuerCapabilityV2
    manifest: ScopedProtocolManifestV2


def context_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    suffix: str,
    *,
    operations: tuple[GovernanceIssuerOperationV2, ...] = (
        GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
    ),
) -> RiskV2ConformanceContext:
    domain = adapter.create_domain_v2(f"scope:risk-v2:{suffix}")
    store = adapter.create_store_v2((domain,))
    grant = GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref=ISSUER_REF,
        grant_ref="grant:risk-v2-conformance",
        grant_binding_ref=root_v2(f"grant-binding:{domain.scope_ref}"),
        operations=operations,
        target_refs=(TARGET_REF,),
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=10_000,
        revocation_generation=0,
    )
    activated = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        f"transition:grant:risk-v2:{suffix}",
        1,
    )
    if activated.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise RuntimeError("Risk v2 Conformance grant activation failed")
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        RUN_REF,
        BASE_EPOCH,
    )
    return RiskV2ConformanceContext(
        domain,
        store,
        grant,
        capability,
        manifest_v2(domain.profile),
    )


def rebind_context_v2(
    context: RiskV2ConformanceContext,
    store: GovernanceStateStoreV2,
    *,
    epoch: int = BASE_EPOCH,
) -> RiskV2ConformanceContext:
    return replace(
        context,
        store=store,
        capability=bind_governance_issuer_capability_v2(
            store,
            context.domain,
            context.grant,
            RUN_REF,
            epoch,
        ),
    )


def request_v2(
    context: RiskV2ConformanceContext,
    *,
    advance_ref: str,
    risk_band: RiskBand = RiskBand.LOW,
    parent: RiskStateSnapshotV2 | None = None,
    current_step: int = 2,
    epoch: int = BASE_EPOCH,
    manifest: ScopedProtocolManifestV2 | None = None,
    run_ref: str = RUN_REF,
    target_ref: str = TARGET_REF,
    issuer_ref: str = ISSUER_REF,
    risk_input_roots: tuple[str, ...] | None = None,
    rationale_codes: tuple[str, ...] = ("declared_risk_classification",),
    source_trace_roots: tuple[str, ...] | None = None,
) -> tuple[RiskStateAdvanceRequestV2, VerifiedRiskSourceV2]:
    return prepare_risk_state_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest if manifest is None else manifest,
        profile=COMMIT_INTEGRITY_PROFILE_VERSION,
        run_ref=run_ref,
        target_ref=target_ref,
        epoch=epoch,
        advance_ref=advance_ref,
        current_step=current_step,
        assessment_ref=f"assessment:{advance_ref}",
        risk_band=risk_band,
        risk_input_roots=(
            (root_v2(f"input:{advance_ref}"),)
            if risk_input_roots is None
            else risk_input_roots
        ),
        rationale_codes=rationale_codes,
        assessment_method="declared-risk-matrix-v1",
        issuer_ref=issuer_ref,
        issued_at_step=current_step,
        expires_at_step=100,
        provenance_ref=f"urn:pheroos:conformance:risk:{advance_ref}",
        source_trace_roots=(
            (root_v2(f"trace:{advance_ref}"),)
            if source_trace_roots is None
            else source_trace_roots
        ),
        parent_snapshot=parent,
    )


def advance_v2(
    context: RiskV2ConformanceContext,
    request: RiskStateAdvanceRequestV2,
    source: object,
) -> GovernanceCommitAttemptV2:
    session = open_risk_authority_session_v2(context.capability, request)
    return advance_risk_state_v2(
        request,
        source=source,
        authority_session=session,
    )


def manifest_v2(authority_profile: str) -> ScopedProtocolManifestV2:
    return ScopedProtocolManifestV2(
        protocol_version=PROTOCOL_VERSION_V2,
        id="protocol:risk-v2-conformance",
        targets=(TargetSpec(TARGET_REF, "durable Risk v2 target"),),
        candidates=(
            CandidateSpec("candidate:risk-v2:accept", TARGET_REF),
            CandidateSpec(FALLBACK_REF, TARGET_REF, True),
        ),
        quorum_policy=QuorumPolicy(TARGET_REF, FALLBACK_REF, 2),
        authority_policy=ScopedAuthorityPolicyV2(
            policy_version="pheroos-scoped-authority-policy-v2",
            profile=authority_profile,
            wire_version="pheroos-authority-wire-v2",
            canonical_version="pheroos-authority-canonical-v2",
            ledger_version="pheroos-governance-authority-ledger-v2",
            state_store_version="pheroos-governance-state-store-v2",
            trace_batch_version="pheroos-governance-trace-batch-v2",
            read_set_version="pheroos-governance-authority-read-set-v2",
        ),
        output_policy=BaselineOutputPolicyV2(
            BASELINE_OUTPUT_POLICY_VERSION_V2,
            "quorum",
            (
                BaselineOutputActionPolicyV2(
                    ACTION_REF,
                    "publish",
                    TARGET_REF,
                    ("evidence_commit", "safe_fallback"),
                ),
            ),
        ),
        trace_policy=TracePolicy(list(_BASELINE_TRACE_EVENTS)),
        evidence_policy=EvidencePolicy(),
        collective_commit_policy=_commit_policy_v2(),
    )


def _commit_policy_v2() -> CollectiveCommitPolicy:
    challenges = ["independent_replication"]
    return CollectiveCommitPolicy(
        policy_version=COMMIT_POLICY_VERSION,
        model=COMMIT_MODEL,
        assurance=CommitAssurance.EVIDENCE_BOUND.value,
        target=TARGET_REF,
        evidence_qualification=EvidenceQualificationPolicy(
            numeric_scale=1_000_000,
            minimum_quality_ppm=500_000,
            minimum_relevance_ppm=500_000,
            positive_group_cap=1_000_000,
            counter_group_cap=1_000_000,
            counter_weight_ppm=1_000_000,
            minimum_positive_evidence=2_000_000,
            maximum_counterevidence=500_000,
            maximum_counterevidence_ratio_ppm=200_000,
            domain_contribution_floor=250_000,
            minimum_source_diversity=2,
            required_challenge_categories=challenges,
            observation_ttl_steps=8,
            require_provenance=True,
            require_trace=True,
        ),
        support_lease=SupportLeasePolicy(
            minimum_support_clusters=2,
            support_ratio_ppm=500_000,
            lease_ttl_steps=6,
            membership_mode="verified_snapshot_v1",
            switch_mode="revoke_then_issue_v1",
            equivocation_mode="exclude_conflicts_v1",
            evidence_reference_required=True,
            cluster_verification_required=True,
        ),
        risk_bands={
            "LOW": _band_v2(2_000_000, 500_000, 200_000, 2, 500_000, 2, 2),
            "MODERATE": _band_v2(2_500_000, 400_000, 150_000, 2, 600_000, 2, 3),
            "HIGH": _band_v2(
                3_000_000,
                300_000,
                100_000,
                3,
                700_000,
                3,
                4,
                assurance=CommitAssurance.CERTIFIED.value,
            ),
            "CRITICAL": _band_v2(
                4_000_000,
                200_000,
                50_000,
                4,
                800_000,
                4,
                5,
                assurance=CommitAssurance.DISTRIBUTED.value,
            ),
        },
        commit_window=CommitWindowPolicy(
            minimum_stability_steps=2,
            deliberation_deadline_steps=8,
            maximum_leader_resets=2,
            maximum_epoch_restarts=1,
            run_deadline_steps=12,
            reset_rules=list(REQUIRED_COMMIT_RESET_RULES),
        ),
        terminal_outcome=TerminalOutcomePolicy(
            safe_fallback_candidate=FALLBACK_REF,
            deadline_outcome="safe_fallback",
            policy_incomplete_outcome="invalid",
            finality_unavailable_outcome="finality_unavailable",
            deliverable_outcomes=[
                "advisory",
                "blocked",
                "evidence_commit",
                "finality_unavailable",
                "invalid",
                "safe_fallback",
                "safety_violation",
            ],
            publishable_outcomes=["evidence_commit", "safe_fallback"],
            executable_outcomes=[],
        ),
        certificate=CertificatePolicy(
            mode="local_receipt",
            wire_version=COMMIT_WIRE_VERSION,
            canonicalization=COMMIT_CANONICAL_VERSION,
            hash_algorithm="sha256",
            issuer_attestation_required=False,
            independent_verification_required=False,
        ),
        distributed=None,
    )


def _band_v2(
    positive: int,
    counter: int,
    counter_ratio: int,
    clusters: int,
    support_ratio: int,
    diversity: int,
    stability: int,
    *,
    assurance: str = CommitAssurance.EVIDENCE_BOUND.value,
) -> RiskBandPolicy:
    return RiskBandPolicy(
        minimum_positive_evidence=positive,
        maximum_counterevidence=counter,
        maximum_counterevidence_ratio_ppm=counter_ratio,
        minimum_support_clusters=clusters,
        minimum_support_ratio_ppm=support_ratio,
        minimum_source_diversity=diversity,
        minimum_margin=250_000,
        stability_steps=stability,
        required_challenge_categories=["independent_replication"],
        minimum_assurance=assurance,
        publishable_outcomes=["evidence_commit"],
        executable_outcomes=[],
    )


def head_revision_v2(
    context: RiskV2ConformanceContext,
    request: RiskStateAdvanceRequestV2,
) -> int:
    return context.store.load_head_v2(request.scope_ref, request.stream_ref).revision


def is_failure_v2(
    attempt: GovernanceCommitAttemptV2,
    disposition: GovernanceCommitDispositionV2,
    code: AuthorityDiagnosticCodeV2,
) -> bool:
    return (
        attempt.disposition is disposition
        and attempt.failure is not None
        and attempt.failure.code is code
        and attempt.committed_transition is None
    )


def root_v2(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


__all__: list[str] = []
