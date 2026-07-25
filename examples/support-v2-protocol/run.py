"""Provider-free vertical journey through the public durable Support v2 ABI."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, cast

from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
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
from pheroos.governance.support_v2 import (
    MembershipCommitRequestV2,
    PrincipalVerificationRecordV2,
    PrincipalVerificationSetAdvanceRequestV2,
    SupportAdvanceRequestV2,
    SupportLeaseProposalV2,
    SupportObservationV2,
    VerifiedMembershipSourceV2,
    VerifiedPrincipalVerificationSourceV2,
    VerifiedPrincipalVerificationSetStateV2,
    VerifiedSupportSourceV2,
    advance_principal_verification_set_v2,
    advance_support_state_v2,
    commit_membership_epoch_v2,
    evaluate_support_v2,
    open_membership_authority_session_v2,
    open_principal_verification_authority_session_v2,
    open_support_authority_session_v2,
    prepare_membership_commit_v2,
    prepare_principal_verification_set_v2,
    prepare_support_initialize_v2,
    prepare_support_issue_v2,
    rehydrate_membership_state_v2,
    rehydrate_principal_verification_set_state_v2,
    rehydrate_support_state_v2,
    require_current_support_state_v2,
)
from pheroos.protocol import (
    COMMIT_INTEGRITY_PROFILE_VERSION,
    PROTOCOL_SCHEMA_V3,
    CollectiveCommitPolicy,
    CommitAssurance,
    ScopedProtocolManifestV2,
    read_protocol_manifest,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from pheroos.trace import TraceEvent


RESULT_SCHEMA = "pheroos-support-v2-example-result-v1"
RUN_REF = "run:support-v2-example"
SCOPE_REF = "scope:support-v2-example"
TARGET_REF = "decision:support-v2"
ISSUER_REF = "issuer:support-v2-example"
PROFILE = COMMIT_INTEGRITY_PROFILE_VERSION


def run_example() -> dict[str, Any]:
    manifest = _manifest()
    adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()
    domain = adapter.create_domain_v2(SCOPE_REF)
    _require(
        domain.profile == manifest.authority_policy.profile,
        "manifest authority profile does not match the Store domain",
    )
    store = adapter.create_store_v2((domain,))
    grant = _grant(domain.domain_root)
    activated = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:support-v2-example:grant",
        1,
    )
    _require_committed(activated, "grant activation")

    verification_request, verification_source = _verification_request(
        manifest,
        domain.domain_root,
    )
    verification_session = open_principal_verification_authority_session_v2(
        _capability(store, domain, grant, verification_request.observed_epoch),
        verification_request,
    )
    verification_attempt = advance_principal_verification_set_v2(
        verification_request,
        source=verification_source,
        authority_session=verification_session,
    )
    _require_committed(verification_attempt, "principal verification")
    verification_state = rehydrate_principal_verification_set_state_v2(
        verification_request.to_dict(),
        domain=domain,
        state_reader=store,
    )

    membership_request, membership_source = _membership_request(
        manifest,
        domain.domain_root,
        verification_state,
    )
    membership_session = open_membership_authority_session_v2(
        _capability(store, domain, grant, membership_request.observed_epoch),
        membership_request,
    )
    membership_attempt = commit_membership_epoch_v2(
        membership_request,
        source=membership_source,
        authority_session=membership_session,
    )
    _require_committed(membership_attempt, "membership")
    membership_state = rehydrate_membership_state_v2(
        membership_request.to_dict(),
        domain=domain,
        state_reader=store,
    )

    initialize_request, initialize_source = prepare_support_initialize_v2(
        domain_root=domain.domain_root,
        scope_ref=SCOPE_REF,
        manifest=manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        issuer_ref=ISSUER_REF,
        observed_epoch=30,
        mutation_ref="mutation:support-v2-example:initialize",
        current_step=3,
        provenance_root=_root("support-initialize-provenance"),
        source_trace_roots=(_root("support-initialize-trace"),),
    )
    initialize_attempt = _advance_support(
        store,
        domain,
        grant,
        initialize_request,
        initialize_source,
    )
    _require_committed(initialize_attempt, "support initialize")
    initialized_state = rehydrate_support_state_v2(
        initialize_request.to_dict(),
        domain=domain,
        state_reader=store,
    )

    claim_root = _root("support-claim")
    observation = _observation(manifest, membership_request, claim_root)
    proposal = _proposal(manifest, membership_request, observation, claim_root)
    issue_request, issue_source = prepare_support_issue_v2(
        manifest=manifest,
        parent_state=initialized_state,
        membership_state=membership_state,
        proposal=proposal,
        positive_observations=(observation,),
        issuer_ref=ISSUER_REF,
        observed_epoch=35,
        mutation_ref="mutation:support-v2-example:issue",
        current_step=5,
        issuance_provenance_root=_root("support-issue-provenance"),
        issuance_trace_roots=(_root("support-issue-trace"),),
    )
    issue_attempt = _advance_support(
        store,
        domain,
        grant,
        issue_request,
        issue_source,
    )
    _require_committed(issue_attempt, "support issue")
    _require(issue_request.issued_lease is not None, "issued lease is absent")
    support_state = rehydrate_support_state_v2(
        issue_request.to_dict(),
        domain=domain,
        state_reader=store,
    )
    evaluation = evaluate_support_v2(
        support_state=support_state,
        membership_state=membership_state,
        manifest=manifest,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        epoch=membership_request.epoch,
        current_step=5,
    )

    restarted = adapter.restart_store_v2(store)
    recovered = rehydrate_support_state_v2(
        json.loads(issue_request.canonical_bytes()),
        domain=domain,
        state_reader=restarted,
    )
    _require(
        require_current_support_state_v2(recovered) == issue_request.snapshot,
        "fresh Store reader did not recover the current Support state",
    )

    event_types = tuple(
        event.event_type
        for request in (
            verification_request,
            membership_request,
            initialize_request,
            issue_request,
        )
        for event in _events(store, domain.scope_ref, request)
    )
    return {
        "schema": RESULT_SCHEMA,
        "provider_free": True,
        "network_used": False,
        "manifest_root": manifest.manifest_root,
        "authority_chain": {
            "verification_snapshot_root": verification_request.snapshot.snapshot_root,
            "membership_snapshot_root": membership_request.snapshot.snapshot_root,
            "support_snapshot_root": issue_request.snapshot.snapshot_root,
            "support_revision": issue_request.snapshot.revision,
        },
        "lease": {
            "lease_root": issue_request.issued_lease.lease_root,
            "candidate_ref": issue_request.issued_lease.candidate_ref,
            "active_cluster_count": evaluation.active_support_cluster_count,
            "policy_support_met": evaluation.policy_support_met,
        },
        "trace_event_types": list(event_types),
        "restart_rehydrated": True,
    }


def _manifest() -> ScopedProtocolManifestV2:
    payload = json.loads(
        Path(__file__).with_name("manifest.json").read_text(encoding="utf-8")
    )
    manifest = read_protocol_manifest(payload, schema_version=PROTOCOL_SCHEMA_V3)
    _require(
        type(manifest) is ScopedProtocolManifestV2,
        "protocol-v3 did not produce an exact scoped manifest",
    )
    return cast(ScopedProtocolManifestV2, manifest)


def _grant(domain_root: str) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=domain_root,
        scope_ref=SCOPE_REF,
        issuer_ref=ISSUER_REF,
        grant_ref="grant:support-v2-example",
        grant_binding_ref=_root("support-v2-example-grant-binding"),
        operations=(
            GovernanceIssuerOperationV2.EVALUATE_QUORUM,
            GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
        ),
        target_refs=(TARGET_REF,),
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=1_000,
        revocation_generation=0,
    )


def _capability(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    epoch: int,
) -> GovernanceIssuerCapabilityV2:
    return bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        RUN_REF,
        epoch,
    )


def _verification_request(
    manifest: ScopedProtocolManifestV2,
    domain_root: str,
) -> tuple[
    PrincipalVerificationSetAdvanceRequestV2,
    VerifiedPrincipalVerificationSourceV2,
]:
    record = PrincipalVerificationRecordV2(
        principal_ref="principal:example",
        cluster_ref="cluster:example",
        failure_domain_ref="failure-domain:example",
        verification_method="external-attestation-v2",
        verification_issuer_ref="identity:example-verifier",
        attestation_root=_root("verification-attestation"),
        evidence_roots=(_root("verification-evidence"),),
        issued_at_step=1,
        expires_at_step=100,
        provenance_ref="urn:pheroos:example:verification",
        source_trace_roots=(_root("verification-source-trace"),),
    )
    return cast(
        tuple[
            PrincipalVerificationSetAdvanceRequestV2,
            VerifiedPrincipalVerificationSourceV2,
        ],
        prepare_principal_verification_set_v2(
            domain_root=domain_root,
            scope_ref=SCOPE_REF,
            manifest=manifest,
            profile=PROFILE,
            assurance=CommitAssurance.EVIDENCE_BOUND,
            run_ref=RUN_REF,
            target_ref=TARGET_REF,
            epoch=1,
            observed_epoch=10,
            advance_ref="advance:support-v2-example:verification",
            snapshot_ref="snapshot:support-v2-example:verification",
            current_step=1,
            expires_at_step=90,
            mutation_issuer_ref=ISSUER_REF,
            records=(record,),
        ),
    )


def _membership_request(
    manifest: ScopedProtocolManifestV2,
    domain_root: str,
    verification_state: VerifiedPrincipalVerificationSetStateV2,
) -> tuple[MembershipCommitRequestV2, VerifiedMembershipSourceV2]:
    return cast(
        tuple[MembershipCommitRequestV2, VerifiedMembershipSourceV2],
        prepare_membership_commit_v2(
            domain_root=domain_root,
            scope_ref=SCOPE_REF,
            manifest=manifest,
            profile=PROFILE,
            assurance=CommitAssurance.EVIDENCE_BOUND,
            run_ref=RUN_REF,
            target_ref=TARGET_REF,
            epoch=1,
            observed_epoch=20,
            request_ref="request:support-v2-example:membership",
            snapshot_ref="snapshot:support-v2-example:membership",
            current_step=2,
            expires_at_step=80,
            mutation_issuer_ref=ISSUER_REF,
            membership_method="store-current-verification-set-v2",
            provenance_ref="urn:pheroos:example:membership",
            source_trace_roots=(_root("membership-source-trace"),),
            verification_state=verification_state,
        ),
    )


def _observation(
    manifest: ScopedProtocolManifestV2,
    membership: MembershipCommitRequestV2,
    claim_root: str,
) -> SupportObservationV2:
    policy = manifest.collective_commit_policy
    _require(type(policy) is CollectiveCommitPolicy, "commit policy is absent")
    return SupportObservationV2(
        observation_ref="observation:support-v2-example",
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=manifest.manifest_root,
        commit_policy_root=commit_policy_fingerprint(policy, profile=PROFILE),
        protocol_ref=manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        epoch=membership.epoch,
        source_ref="source:support-v2-example",
        evidence_root=_root("support-observation-evidence"),
        observed_at_step=5,
        expires_at_step=20,
        provenance_root=_root("support-observation-provenance"),
        source_trace_roots=(_root("support-observation-trace"),),
    )


def _proposal(
    manifest: ScopedProtocolManifestV2,
    membership: MembershipCommitRequestV2,
    observation: SupportObservationV2,
    claim_root: str,
) -> SupportLeaseProposalV2:
    policy = manifest.collective_commit_policy
    _require(type(policy) is CollectiveCommitPolicy, "commit policy is absent")
    return SupportLeaseProposalV2(
        proposal_ref="proposal:support-v2-example",
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=manifest.manifest_root,
        commit_policy_root=commit_policy_fingerprint(policy, profile=PROFILE),
        protocol_ref=manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET_REF,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        epoch=membership.epoch,
        principal_ref="principal:example",
        positive_observation_roots=(observation.observation_root,),
        nonce="nonce:support-v2-example",
        proposed_at_step=5,
        provenance_root=_root("support-proposal-provenance"),
        source_trace_roots=(_root("support-proposal-trace"),),
    )


def _advance_support(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    request: SupportAdvanceRequestV2,
    source: VerifiedSupportSourceV2,
) -> GovernanceCommitAttemptV2:
    session = open_support_authority_session_v2(
        _capability(store, domain, grant, request.observed_epoch),
        request,
    )
    return advance_support_state_v2(
        request,
        source=source,
        authority_session=session,
    )


def _events(
    store: GovernanceStateStoreV2,
    scope_ref: str,
    request: (
        PrincipalVerificationSetAdvanceRequestV2
        | MembershipCommitRequestV2
        | SupportAdvanceRequestV2
    ),
) -> tuple[TraceEvent, ...]:
    view = store.load_commit_view_v2(
        scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    _require(view.committed_transition is not None, "committed Trace is absent")
    return tuple(view.committed_transition.batch.trace_batch.events)


def _require_committed(attempt: GovernanceCommitAttemptV2, label: str) -> None:
    _require(
        attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        and attempt.committed_transition is not None,
        f"{label} did not commit",
    )


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    print(json.dumps(run_example(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
