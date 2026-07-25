from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import pickle
from typing import Any, cast

import pytest

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceDomainRetirementRequestV2,
)
from pheroos.governance._authority_session_v2.operations import (
    open_governance_authority_session_v2,
    retire_governance_domain_v2,
)
from pheroos.governance._authority_v2 import InMemoryGovernanceStateStoreV2
from pheroos.governance._support_v2.common import (
    MAX_SUPPORT_RESOURCE_DEPTH_V2,
    MAX_SUPPORT_RESOURCE_NODES_V2,
    MAX_SUPPORT_RESOURCE_TEXT_BYTES_V2,
    MAX_SUPPORT_TEXT_BYTES_V2,
    _preflight_support_resources_v2,
)
from pheroos.governance._support_v2.membership_contracts import (
    MembershipCommitRequestV2,
    MembershipSnapshotV2,
)
from pheroos.governance._support_v2.membership_operations import (
    VerifiedMembershipStateV2,
    commit_membership_epoch_v2,
    open_membership_authority_session_v2,
    rehydrate_membership_state_v2,
)
from pheroos.governance._support_v2.membership_source import (
    VerifiedMembershipSourceV2,
    prepare_membership_commit_v2,
)
from pheroos.governance._support_v2.principal_verification_contracts import (
    PrincipalVerificationSetAdvanceRequestV2,
    PrincipalVerificationSetSnapshotV2,
)
from pheroos.governance._support_v2.principal_verification_operations import (
    VerifiedPrincipalVerificationSetStateV2,
    advance_principal_verification_set_v2,
    open_principal_verification_authority_session_v2,
    rehydrate_principal_verification_set_state_v2,
)
from pheroos.governance._support_v2.principal_verification_records import (
    PrincipalVerificationRecordV2,
)
from pheroos.governance._support_v2.principal_verification_source import (
    VerifiedPrincipalVerificationSourceV2,
    prepare_principal_verification_set_v2,
)
from pheroos.governance._support_v2.support_lease_contracts import (
    MAX_SUPPORT_LEASES_V2,
    SupportLeaseProposalV2,
    SupportObservationV2,
)
from pheroos.governance._support_v2.support_operations import (
    VerifiedSupportStateV2,
    _adopt_committed_support_successor_v2,
    advance_support_state_v2,
    open_support_authority_session_v2,
    rehydrate_support_state_v2,
    require_current_support_state_v2,
    support_state_is_current_v2,
)
from pheroos.governance._support_v2.support_source import (
    VerifiedSupportSourceV2,
    prepare_support_initialize_v2,
    prepare_support_issue_v2,
    prepare_support_revoke_v2,
    prepare_support_switch_v2,
)
from pheroos.governance._support_v2.support_state_contracts import (
    SupportAdvanceRequestV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    governance_issuer_grant_stream_ref_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitViewV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
    GovernanceTraceBatchV2,
)
from pheroos.protocol import COMMIT_INTEGRITY_PROFILE_VERSION
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    AuthorityDiagnosticCodeV2,
    GovernanceAuthorityReadSetV2,
)
from pheroos.protocol.authority_manifest_v2 import (
    ScopedProtocolManifestV2,
    scoped_capability_manifest_v2_from_dict,
)
from pheroos.protocol.commit_models import CollectiveCommitPolicy, CommitAssurance
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from pheroos.protocol.loader import load_capability_manifest
from pheroos.trace import InMemoryTraceStore, TraceEvent


ROOT = Path(__file__).resolve().parents[2]
PROFILE = COMMIT_INTEGRITY_PROFILE_VERSION
TARGET = "decision:review"
RUN_REF = "run:support-v2-operations"


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _manifest() -> ScopedProtocolManifestV2:
    payload = json.loads(
        (ROOT / "examples/scoped-output-protocol/capability.json").read_text()
    )
    scoped = scoped_capability_manifest_v2_from_dict(payload).protocol
    legacy = load_capability_manifest(
        ROOT / "examples/hybrid-commit-protocol/capability.json"
    )
    policy = legacy.protocol.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    return replace(scoped, collective_commit_policy=replace(policy, target=TARGET))


def _policy(manifest: ScopedProtocolManifestV2) -> CollectiveCommitPolicy:
    policy = manifest.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    return policy


@dataclass(frozen=True, slots=True)
class _Context:
    domain: AuthorityDomainV2
    store: GovernanceStateStoreV2
    base_store: InMemoryGovernanceStateStoreV2
    grant: GovernanceIssuerGrantV2
    manifest: ScopedProtocolManifestV2


@dataclass(frozen=True, slots=True)
class _Upstreams:
    verification_request: PrincipalVerificationSetAdvanceRequestV2
    verification_state: VerifiedPrincipalVerificationSetStateV2
    membership_request: MembershipCommitRequestV2
    membership_state: VerifiedMembershipStateV2


def _grant(
    domain: AuthorityDomainV2,
    *,
    issuer_ref: str,
    grant_ref: str,
) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref=issuer_ref,
        grant_ref=grant_ref,
        grant_binding_ref=_root(f"binding:{domain.scope_ref}:{grant_ref}"),
        operations=(
            GovernanceIssuerOperationV2.EVALUATE_QUORUM,
            GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
            GovernanceIssuerOperationV2.RETIRE_DOMAIN,
        ),
        target_refs=(TARGET,),
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100_000,
        revocation_generation=0,
    )


def _context(
    *,
    scope_ref: str,
    store_wrapper: Callable[[GovernanceStateStoreV2, str], GovernanceStateStoreV2]
    | None = None,
) -> _Context:
    domain = AuthorityDomainV2(
        policy_version=AUTHORITY_POLICY_VERSION_V2,
        profile=AUTHORITY_LOCAL_PROFILE_V2,
        wire_version=AUTHORITY_WIRE_VERSION_V2,
        canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref=scope_ref,
    )
    base = InMemoryGovernanceStateStoreV2((domain,))
    grant = _grant(
        domain,
        issuer_ref="issuer:support:a",
        grant_ref="grant:support:a",
    )
    activated = activate_governance_issuer_grant_v2(
        base,
        domain,
        grant,
        f"transition:{scope_ref}:grant:a",
        1,
    )
    assert activated.disposition is GovernanceCommitDispositionV2.COMMITTED
    store: GovernanceStateStoreV2 = (
        base if store_wrapper is None else store_wrapper(base, domain.domain_root)
    )
    return _Context(domain, store, base, grant, _manifest())


def _capability(
    context: _Context,
    grant: GovernanceIssuerGrantV2,
    observed_epoch: int,
) -> GovernanceIssuerCapabilityV2:
    return bind_governance_issuer_capability_v2(
        context.store,
        context.domain,
        grant,
        RUN_REF,
        observed_epoch,
    )


def _activate_rotated_grant(context: _Context) -> GovernanceIssuerGrantV2:
    grant = _grant(
        context.domain,
        issuer_ref="issuer:support:b",
        grant_ref="grant:support:b",
    )
    attempt = activate_governance_issuer_grant_v2(
        context.store,
        context.domain,
        grant,
        f"transition:{context.domain.scope_ref}:grant:b",
        2,
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    return grant


def _verification_record(label: str) -> PrincipalVerificationRecordV2:
    return PrincipalVerificationRecordV2(
        principal_ref="principal:alpha",
        cluster_ref="cluster:alpha",
        failure_domain_ref="failure-domain:alpha",
        verification_method="external-attestation-v2",
        verification_issuer_ref="identity:verifier",
        attestation_root=_root(f"attestation:{label}"),
        evidence_roots=(_root(f"evidence:verification:{label}"),),
        issued_at_step=1,
        expires_at_step=90_000,
        provenance_ref=f"urn:test:verification:{label}",
        source_trace_roots=(_root(f"trace:verification:{label}"),),
    )


def _prepare_verification(
    context: _Context,
    *,
    epoch: int,
    label: str,
    issuer_ref: str,
    parent: PrincipalVerificationSetSnapshotV2 | None,
) -> tuple[
    PrincipalVerificationSetAdvanceRequestV2,
    VerifiedPrincipalVerificationSourceV2,
]:
    return cast(
        tuple[
            PrincipalVerificationSetAdvanceRequestV2,
            VerifiedPrincipalVerificationSourceV2,
        ],
        prepare_principal_verification_set_v2(
            domain_root=context.domain.domain_root,
            scope_ref=context.domain.scope_ref,
            manifest=context.manifest,
            profile=PROFILE,
            assurance=CommitAssurance.EVIDENCE_BOUND,
            run_ref=RUN_REF,
            target_ref=TARGET,
            epoch=epoch,
            observed_epoch=10 + epoch,
            advance_ref=f"advance:verification:{label}",
            snapshot_ref=f"snapshot:verification:{label}",
            current_step=epoch,
            expires_at_step=90_000,
            mutation_issuer_ref=issuer_ref,
            records=(_verification_record(label),),
            parent_snapshot=parent,
        ),
    )


def _commit_upstreams(
    context: _Context,
    *,
    epoch: int = 1,
    label: str = "genesis",
    grant: GovernanceIssuerGrantV2 | None = None,
    verification_parent: PrincipalVerificationSetSnapshotV2 | None = None,
    membership_parent: MembershipSnapshotV2 | None = None,
) -> _Upstreams:
    selected = context.grant if grant is None else grant
    verification, verification_source = _prepare_verification(
        context,
        epoch=epoch,
        label=label,
        issuer_ref=selected.issuer_ref,
        parent=verification_parent,
    )
    verification_session = open_principal_verification_authority_session_v2(
        _capability(context, selected, verification.observed_epoch), verification
    )
    verification_attempt = advance_principal_verification_set_v2(
        verification,
        source=verification_source,
        authority_session=verification_session,
    )
    assert verification_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    verification_state = rehydrate_principal_verification_set_state_v2(
        verification.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    membership, membership_source = cast(
        tuple[MembershipCommitRequestV2, VerifiedMembershipSourceV2],
        prepare_membership_commit_v2(
            domain_root=context.domain.domain_root,
            scope_ref=context.domain.scope_ref,
            manifest=context.manifest,
            profile=PROFILE,
            assurance=CommitAssurance.EVIDENCE_BOUND,
            run_ref=RUN_REF,
            target_ref=TARGET,
            epoch=epoch,
            observed_epoch=20 + epoch,
            request_ref=f"request:membership:{label}",
            snapshot_ref=f"snapshot:membership:{label}",
            current_step=epoch + 1,
            expires_at_step=80_000,
            mutation_issuer_ref=selected.issuer_ref,
            membership_method="store-current-verification-set-v2",
            provenance_ref=f"urn:test:membership:{label}",
            source_trace_roots=(_root(f"trace:membership:{label}"),),
            verification_state=verification_state,
            parent_snapshot=membership_parent,
        ),
    )
    membership_session = open_membership_authority_session_v2(
        _capability(context, selected, membership.observed_epoch), membership
    )
    membership_attempt = commit_membership_epoch_v2(
        membership,
        source=membership_source,
        authority_session=membership_session,
    )
    assert membership_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    membership_state = rehydrate_membership_state_v2(
        membership.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    return _Upstreams(
        verification,
        verification_state,
        membership,
        membership_state,
    )


def _observation(
    context: _Context,
    membership: MembershipSnapshotV2,
    *,
    candidate_ref: str,
    claim_root: str,
    label: str,
    current_step: int,
) -> SupportObservationV2:
    policy = _policy(context.manifest)
    return SupportObservationV2(
        observation_ref=f"observation:{label}",
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=context.manifest.manifest_root,
        commit_policy_root=commit_policy_fingerprint(policy, profile=PROFILE),
        protocol_ref=context.manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET,
        candidate_ref=candidate_ref,
        claim_root=claim_root,
        epoch=membership.epoch,
        source_ref=f"source:{label}",
        evidence_root=_root(f"evidence:observation:{label}"),
        observed_at_step=current_step,
        expires_at_step=min(membership.expires_at_step, current_step + 1_000),
        provenance_root=_root(f"provenance:observation:{label}"),
        source_trace_roots=(_root(f"trace:observation:{label}"),),
    )


def _proposal(
    context: _Context,
    membership: MembershipSnapshotV2,
    observation: SupportObservationV2,
    *,
    candidate_ref: str,
    claim_root: str,
    label: str,
    current_step: int,
) -> SupportLeaseProposalV2:
    policy = _policy(context.manifest)
    return SupportLeaseProposalV2(
        proposal_ref=f"proposal:{label}",
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=context.manifest.manifest_root,
        commit_policy_root=commit_policy_fingerprint(policy, profile=PROFILE),
        protocol_ref=context.manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET,
        candidate_ref=candidate_ref,
        claim_root=claim_root,
        epoch=membership.epoch,
        principal_ref="principal:alpha",
        positive_observation_roots=(observation.observation_root,),
        nonce=f"nonce:{label}",
        proposed_at_step=current_step,
        provenance_root=_root(f"provenance:proposal:{label}"),
        source_trace_roots=(_root(f"trace:proposal:{label}"),),
    )


def _initialize_request(
    context: _Context,
    *,
    label: str,
    grant: GovernanceIssuerGrantV2 | None = None,
    current_step: int = 3,
) -> tuple[SupportAdvanceRequestV2, VerifiedSupportSourceV2]:
    selected = context.grant if grant is None else grant
    return prepare_support_initialize_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        issuer_ref=selected.issuer_ref,
        observed_epoch=30 + current_step,
        mutation_ref=f"mutation:support:initialize:{label}",
        current_step=current_step,
        provenance_root=_root(f"provenance:support:initialize:{label}"),
        source_trace_roots=(_root(f"trace:support:initialize:{label}"),),
    )


def _prepare_issue(
    context: _Context,
    parent_state: VerifiedSupportStateV2,
    membership_state: VerifiedMembershipStateV2,
    *,
    label: str,
    current_step: int,
    candidate_ref: str = "candidate:a",
    claim_root: str | None = None,
    grant: GovernanceIssuerGrantV2 | None = None,
    membership_snapshot: MembershipSnapshotV2 | None = None,
) -> tuple[SupportAdvanceRequestV2, VerifiedSupportSourceV2]:
    selected = context.grant if grant is None else grant
    membership = (
        membership_state.snapshot
        if membership_snapshot is None
        else membership_snapshot
    )
    claim = _root(f"claim:{label}") if claim_root is None else claim_root
    observation = _observation(
        context,
        membership,
        candidate_ref=candidate_ref,
        claim_root=claim,
        label=label,
        current_step=current_step,
    )
    proposal = _proposal(
        context,
        membership,
        observation,
        candidate_ref=candidate_ref,
        claim_root=claim,
        label=label,
        current_step=current_step,
    )
    return prepare_support_issue_v2(
        manifest=context.manifest,
        parent_state=parent_state,
        membership_state=membership_state,
        proposal=proposal,
        positive_observations=(observation,),
        issuer_ref=selected.issuer_ref,
        observed_epoch=30 + current_step,
        mutation_ref=f"mutation:support:issue:{label}",
        current_step=current_step,
        issuance_provenance_root=_root(f"provenance:support:issue:{label}"),
        issuance_trace_roots=(_root(f"trace:support:issue:{label}"),),
    )


def _prepare_switch(
    context: _Context,
    parent_state: VerifiedSupportStateV2,
    membership_state: VerifiedMembershipStateV2,
    *,
    prior_lease_root: str,
    label: str,
    current_step: int,
    candidate_ref: str,
    claim_root: str,
    grant: GovernanceIssuerGrantV2 | None = None,
) -> tuple[SupportAdvanceRequestV2, VerifiedSupportSourceV2]:
    selected = context.grant if grant is None else grant
    membership = membership_state.snapshot
    observation = _observation(
        context,
        membership,
        candidate_ref=candidate_ref,
        claim_root=claim_root,
        label=label,
        current_step=current_step,
    )
    proposal = _proposal(
        context,
        membership,
        observation,
        candidate_ref=candidate_ref,
        claim_root=claim_root,
        label=label,
        current_step=current_step,
    )
    return prepare_support_switch_v2(
        manifest=context.manifest,
        parent_state=parent_state,
        membership_state=membership_state,
        prior_lease_root=prior_lease_root,
        proposal=proposal,
        positive_observations=(observation,),
        issuer_ref=selected.issuer_ref,
        revocation_reason_codes=("candidate-switch",),
        observed_epoch=30 + current_step,
        mutation_ref=f"mutation:support:switch:{label}",
        current_step=current_step,
        revocation_provenance_root=_root(f"provenance:support:switch:revoke:{label}"),
        revocation_trace_roots=(_root(f"trace:support:switch:revoke:{label}"),),
        issuance_provenance_root=_root(f"provenance:support:switch:issue:{label}"),
        issuance_trace_roots=(_root(f"trace:support:switch:issue:{label}"),),
    )


def _prepare_revoke(
    context: _Context,
    parent_state: VerifiedSupportStateV2,
    *,
    lease_root: str,
    label: str,
    current_step: int,
    grant: GovernanceIssuerGrantV2 | None = None,
) -> tuple[SupportAdvanceRequestV2, VerifiedSupportSourceV2]:
    selected = context.grant if grant is None else grant
    return prepare_support_revoke_v2(
        manifest=context.manifest,
        parent_state=parent_state,
        lease_root=lease_root,
        reason_codes=("test-complete",),
        issuer_ref=selected.issuer_ref,
        observed_epoch=30 + current_step,
        mutation_ref=f"mutation:support:revoke:{label}",
        current_step=current_step,
        provenance_root=_root(f"provenance:support:revoke:{label}"),
        source_trace_roots=(_root(f"trace:support:revoke:{label}"),),
    )


def _advance_support(
    context: _Context,
    request: SupportAdvanceRequestV2,
    source: VerifiedSupportSourceV2,
    *,
    grant: GovernanceIssuerGrantV2 | None = None,
) -> tuple[GovernanceCommitAttemptV2, object]:
    selected = context.grant if grant is None else grant
    session = open_support_authority_session_v2(
        _capability(context, selected, request.observed_epoch), request
    )
    return (
        advance_support_state_v2(
            request,
            source=source,
            authority_session=session,
        ),
        session,
    )


def _support_state(
    context: _Context,
    request: SupportAdvanceRequestV2,
) -> VerifiedSupportStateV2:
    return rehydrate_support_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )


def _commit_initialize(
    context: _Context,
    *,
    label: str,
    grant: GovernanceIssuerGrantV2 | None = None,
) -> tuple[SupportAdvanceRequestV2, VerifiedSupportStateV2, object]:
    request, source = _initialize_request(context, label=label, grant=grant)
    attempt, session = _advance_support(context, request, source, grant=grant)
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    return request, _support_state(context, request), session


def _assert_code(
    attempt: GovernanceCommitAttemptV2,
    disposition: GovernanceCommitDispositionV2,
    code: AuthorityDiagnosticCodeV2,
) -> None:
    assert attempt.disposition is disposition
    assert attempt.failure is not None
    assert attempt.failure.code is code


def test_real_store_initialize_issue_switch_revoke_restart_and_trace() -> None:
    context = _context(scope_ref="scope:support-v2:vertical")
    upstreams = _commit_upstreams(context)
    initialized, initialized_state, _ = _commit_initialize(context, label="vertical")

    initialized_view = context.store.load_commit_view_v2(
        context.domain.scope_ref,
        initialized.stream_ref,
        initialized.transition_id,
    )
    assert initialized_view.committed_transition is not None
    initialized_batch = initialized_view.committed_transition.batch
    assert {entry.stream_ref for entry in initialized_batch.read_set.entries} == {
        initialized.stream_ref,
        governance_issuer_grant_stream_ref_v2(
            context.domain.scope_ref, context.grant.grant_ref
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    assert tuple(
        event.event_type for event in initialized_batch.trace_batch.events
    ) == ("support_state_advanced",)

    claim_root = _root("claim:vertical")
    issued, issued_source = _prepare_issue(
        context,
        initialized_state,
        upstreams.membership_state,
        label="vertical:a",
        current_step=5,
        candidate_ref="candidate:a",
        claim_root=claim_root,
    )
    issued_attempt, _ = _advance_support(context, issued, issued_source)
    assert issued_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert issued.issued_lease is not None
    issued_state = _support_state(context, issued)
    issued_view = context.store.load_commit_view_v2(
        context.domain.scope_ref,
        issued.stream_ref,
        issued.transition_id,
    )
    assert issued_view.committed_transition is not None
    issued_batch = issued_view.committed_transition.batch
    assert {entry.stream_ref for entry in issued_batch.read_set.entries} == {
        issued.stream_ref,
        upstreams.membership_request.stream_ref,
        governance_issuer_grant_stream_ref_v2(
            context.domain.scope_ref, context.grant.grant_ref
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    assert tuple(event.event_type for event in issued_batch.trace_batch.events) == (
        "support_state_advanced",
        "support_lease_issued_v2",
    )

    switched, switched_source = _prepare_switch(
        context,
        issued_state,
        upstreams.membership_state,
        prior_lease_root=issued.issued_lease.lease_root,
        label="vertical:b",
        current_step=6,
        candidate_ref="candidate:b",
        claim_root=claim_root,
    )
    switched_attempt, _ = _advance_support(context, switched, switched_source)
    assert switched_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert switched.issued_lease is not None
    switched_state = _support_state(context, switched)
    switched_view = context.store.load_commit_view_v2(
        context.domain.scope_ref,
        switched.stream_ref,
        switched.transition_id,
    )
    assert switched_view.committed_transition is not None
    assert tuple(
        event.event_type
        for event in switched_view.committed_transition.batch.trace_batch.events
    ) == (
        "support_state_advanced",
        "support_lease_revoked_v2",
        "support_lease_issued_v2",
    )

    revoked, revoked_source = _prepare_revoke(
        context,
        switched_state,
        lease_root=switched.issued_lease.lease_root,
        label="vertical",
        current_step=7,
    )
    revoked_attempt, _ = _advance_support(context, revoked, revoked_source)
    assert revoked_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    revoked_view = context.store.load_commit_view_v2(
        context.domain.scope_ref,
        revoked.stream_ref,
        revoked.transition_id,
    )
    assert revoked_view.committed_transition is not None
    assert tuple(
        event.event_type
        for event in revoked_view.committed_transition.batch.trace_batch.events
    ) == ("support_state_advanced", "support_lease_revoked_v2")

    trace_store = InMemoryTraceStore()
    committed_events = (
        *initialized_batch.trace_batch.events,
        *issued_batch.trace_batch.events,
        *switched_view.committed_transition.batch.trace_batch.events,
        *revoked_view.committed_transition.batch.trace_batch.events,
    )
    records = tuple(trace_store.append(event) for event in committed_events)
    assert tuple(record.sequence for record in records) == tuple(
        range(len(committed_events))
    )
    assert trace_store.events == committed_events

    restarted = InMemoryGovernanceStateStoreV2.from_snapshot_v2(
        context.base_store.snapshot_v2()
    )
    recovered = rehydrate_support_state_v2(
        json.loads(revoked.canonical_bytes()),
        domain=context.domain,
        state_reader=restarted,
    )
    assert require_current_support_state_v2(recovered) == revoked.snapshot
    assert recovered.snapshot.leases == ()
    assert recovered.snapshot.history_count == 4
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(recovered)


def test_lost_response_exact_retry_survives_grant_revocation() -> None:
    context = _context(scope_ref="scope:support-v2:lost-response")
    upstreams = _commit_upstreams(context)
    _, initialized_state, _ = _commit_initialize(context, label="lost-response")
    request, source = _prepare_issue(
        context,
        initialized_state,
        upstreams.membership_state,
        label="lost-response",
        current_step=5,
    )
    accepted, session = _advance_support(context, request, source)
    assert accepted.committed_transition is not None

    restarted_store = InMemoryGovernanceStateStoreV2.from_snapshot_v2(
        context.base_store.snapshot_v2()
    )
    restarted_context = replace(
        context,
        store=cast(GovernanceStateStoreV2, restarted_store),
        base_store=restarted_store,
    )
    restarted_session = open_support_authority_session_v2(
        _capability(restarted_context, restarted_context.grant, request.observed_epoch),
        request,
    )
    restarted_retry = advance_support_state_v2(
        request,
        source=None,
        authority_session=restarted_session,
    )
    assert restarted_retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert restarted_retry.committed_transition is not None
    assert restarted_retry.committed_transition.receipt.receipt_root == (
        accepted.committed_transition.receipt.receipt_root
    )

    revoked = revoke_governance_issuer_grant_v2(
        context.store,
        context.domain,
        context.grant.grant_ref,
        "transition:support-v2:revoke-after-lost-response",
        100,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED
    retry = advance_support_state_v2(
        request,
        source=None,
        authority_session=session,
    )
    assert retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert retry.committed_transition is not None
    assert retry.committed_transition.receipt.receipt_root == (
        accepted.committed_transition.receipt.receipt_root
    )


def test_stale_parent_and_membership_read_sets_fail_without_writes() -> None:
    parent_context = _context(scope_ref="scope:support-v2:stale-parent")
    parent_upstreams = _commit_upstreams(parent_context)
    _, parent_state, _ = _commit_initialize(parent_context, label="stale-parent")
    winner, winner_source = _prepare_issue(
        parent_context,
        parent_state,
        parent_upstreams.membership_state,
        label="stale-parent:winner",
        current_step=5,
    )
    loser, loser_source = _prepare_issue(
        parent_context,
        parent_state,
        parent_upstreams.membership_state,
        label="stale-parent:loser",
        current_step=5,
    )
    assert _advance_support(parent_context, winner, winner_source)[0].disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    rejected = _advance_support(parent_context, loser, loser_source)[0]
    _assert_code(
        rejected,
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
    )
    assert (
        parent_context.store.load_head_v2(
            parent_context.domain.scope_ref, loser.stream_ref
        ).revision
        == 2
    )

    membership_context = _context(scope_ref="scope:support-v2:stale-membership")
    first = _commit_upstreams(membership_context)
    _, initialized_state, _ = _commit_initialize(
        membership_context, label="stale-membership"
    )
    pending, pending_source = _prepare_issue(
        membership_context,
        initialized_state,
        first.membership_state,
        label="stale-membership:pending",
        current_step=5,
    )
    pending_session = open_support_authority_session_v2(
        _capability(
            membership_context,
            membership_context.grant,
            pending.observed_epoch,
        ),
        pending,
    )
    _commit_upstreams(
        membership_context,
        epoch=2,
        label="stale-membership:successor",
        verification_parent=first.verification_request.snapshot,
        membership_parent=first.membership_request.snapshot,
    )
    before = membership_context.store.load_head_v2(
        membership_context.domain.scope_ref, pending.stream_ref
    ).revision
    membership_rejected = advance_support_state_v2(
        pending,
        source=pending_source,
        authority_session=pending_session,
    )
    _assert_code(
        membership_rejected,
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
    )
    assert (
        membership_context.store.load_head_v2(
            membership_context.domain.scope_ref, pending.stream_ref
        ).revision
        == before
        == 1
    )


def test_issuer_rotation_preserves_fixed_stream_and_historical_verification() -> None:
    context = _context(scope_ref="scope:support-v2:issuer-rotation")
    upstreams = _commit_upstreams(context)
    initialized, initialized_state, _ = _commit_initialize(
        context, label="issuer-rotation"
    )
    claim_root = _root("claim:issuer-rotation")
    issued, issued_source = _prepare_issue(
        context,
        initialized_state,
        upstreams.membership_state,
        label="issuer-rotation:a",
        current_step=5,
        candidate_ref="candidate:a",
        claim_root=claim_root,
    )
    assert _advance_support(context, issued, issued_source)[0].disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    assert issued.issued_lease is not None
    issued_state = _support_state(context, issued)

    rotated = _activate_rotated_grant(context)
    switched, switched_source = _prepare_switch(
        context,
        issued_state,
        upstreams.membership_state,
        prior_lease_root=issued.issued_lease.lease_root,
        label="issuer-rotation:b",
        current_step=6,
        candidate_ref="candidate:b",
        claim_root=claim_root,
        grant=rotated,
    )
    switched_attempt, _ = _advance_support(
        context, switched, switched_source, grant=rotated
    )
    assert switched_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert switched.issued_lease is not None
    assert initialized.stream_ref == issued.stream_ref == switched.stream_ref
    assert switched.snapshot.mutation_issuer_ref == rotated.issuer_ref
    assert switched.issued_lease.issuance_issuer_ref == rotated.issuer_ref
    assert switched.revocation is not None
    assert switched.revocation.lease_issuance_issuer_ref == context.grant.issuer_ref
    assert switched.revocation.revocation_issuer_ref == rotated.issuer_ref

    revoked = revoke_governance_issuer_grant_v2(
        context.store,
        context.domain,
        context.grant.grant_ref,
        "transition:support-v2:issuer-rotation:revoke-a",
        100,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED
    restarted = InMemoryGovernanceStateStoreV2.from_snapshot_v2(
        context.base_store.snapshot_v2()
    )
    recovered = rehydrate_support_state_v2(
        switched.to_dict(),
        domain=context.domain,
        state_reader=restarted,
    )
    assert recovered.snapshot == switched.snapshot
    assert recovered.snapshot.mutation_issuer_ref == rotated.issuer_ref


def test_96_store_commits_evict_expiry_and_keep_projection_bounded() -> None:
    context = _context(scope_ref="scope:support-v2:bounded-churn")
    upstreams = _commit_upstreams(context)
    _, parent_state, _ = _commit_initialize(context, label="bounded-churn")
    membership_snapshot = upstreams.membership_state.snapshot
    current_step = 5
    prior_lease_root: str | None = None
    snapshot_sizes: list[int] = []
    final_request: SupportAdvanceRequestV2 | None = None

    for index in range(96):
        label = f"bounded-churn:{index:03d}"
        request, source = _prepare_issue(
            context,
            parent_state,
            upstreams.membership_state,
            label=label,
            current_step=current_step,
            candidate_ref="candidate:a",
            claim_root=_root("claim:bounded-churn"),
            membership_snapshot=membership_snapshot,
        )
        attempt, _ = _advance_support(context, request, source)
        assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        assert request.issued_lease is not None
        assert len(request.snapshot.leases) == 1
        assert tuple(request.evicted_lease_roots) == (
            () if prior_lease_root is None else (prior_lease_root,)
        )
        assert request.snapshot.history_count == request.snapshot.revision
        snapshot_sizes.append(len(request.snapshot.canonical_bytes()))
        parent_state = _adopt_committed_support_successor_v2(
            parent_state,
            request,
            attempt,
        )
        prior_lease_root = request.issued_lease.lease_root
        current_step = request.issued_lease.expires_at_step
        final_request = request

    assert final_request is not None
    assert final_request.snapshot.revision == 97
    assert final_request.snapshot.history_count == 97
    assert len(final_request.snapshot.leases) == 1
    assert max(snapshot_sizes) - min(snapshot_sizes) < 512
    assert (
        context.store.load_head_v2(
            context.domain.scope_ref, final_request.stream_ref
        ).revision
        == 97
    )

    restarted = InMemoryGovernanceStateStoreV2.from_snapshot_v2(
        context.base_store.snapshot_v2()
    )
    recovered = rehydrate_support_state_v2(
        final_request.to_dict(),
        domain=context.domain,
        state_reader=restarted,
    )
    assert require_current_support_state_v2(recovered) == final_request.snapshot


class _AdversarialStore:
    def __init__(self, store: GovernanceStateStoreV2, domain_root: str) -> None:
        self.store = store
        self.domain_root = domain_root
        self.finality_transition_ids: set[str] = set()
        self.hidden_transition_ids: set[str] = set()
        self.view_mutator: Callable[[GovernanceCommitViewV2], None] | None = None
        self.atomic_commits = 0
        self.load_head_calls = 0
        self.load_state_calls = 0
        self.load_view_calls = 0

    @property
    def state_store_version(self) -> str:
        return cast(str, self.store.state_store_version)

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        self.load_head_calls += 1
        return self.store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(self, scope_ref: str, stream_ref: str):  # type: ignore[no-untyped-def]
        self.load_state_calls += 1
        return self.store.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        self.load_view_calls += 1
        if transition_id in self.hidden_transition_ids:
            raise KeyError(transition_id)
        if transition_id in self.finality_transition_ids:
            return GovernanceCommitViewV2(
                domain_root=self.domain_root,
                scope_ref=scope_ref,
                stream_ref=stream_ref,
                transition_id=transition_id,
                expected_receipt_root=expected_receipt_root,
                disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
                failure=GovernanceFailureV2(
                    code=AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
                    path="/transition_id",
                    stage=GovernanceFailureStageV2.FINALITY,
                ),
                committed_transition=None,
                position_observation=None,
                observed_revision=None,
                observed_head_root=None,
            )
        view = self.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )
        if self.view_mutator is not None:
            self.view_mutator(view)
        return view

    def atomic_commit_v2(self, batch: Any) -> GovernanceCommitAttemptV2:
        self.atomic_commits += 1
        return self.store.atomic_commit_v2(batch)

    def reset_counters(self) -> None:
        self.atomic_commits = 0
        self.load_head_calls = 0
        self.load_state_calls = 0
        self.load_view_calls = 0


def _adversarial_context(scope_ref: str) -> tuple[_Context, _AdversarialStore]:
    wrapper: _AdversarialStore | None = None

    def wrap(store: GovernanceStateStoreV2, domain_root: str) -> GovernanceStateStoreV2:
        nonlocal wrapper
        wrapper = _AdversarialStore(store, domain_root)
        return cast(GovernanceStateStoreV2, wrapper)

    context = _context(scope_ref=scope_ref, store_wrapper=wrap)
    assert wrapper is not None
    return context, wrapper


def test_successful_prepare_advance_and_adopt_keep_commit_view_reads_bounded() -> None:
    context, reader = _adversarial_context("scope:support-v2:bounded-success-reads")
    upstreams = _commit_upstreams(context)
    _, parent_state, _ = _commit_initialize(context, label="bounded-success-reads")
    # Caller-owned portable data is read before the measured prepare boundary;
    # prepare receives it explicitly and must use the verified state anchors.
    membership_snapshot = upstreams.membership_state.snapshot

    reader.reset_counters()
    request, source = _prepare_issue(
        context,
        parent_state,
        upstreams.membership_state,
        label="bounded-success-reads",
        current_step=5,
        membership_snapshot=membership_snapshot,
    )
    assert reader.load_view_calls == 0
    assert reader.atomic_commits == 0

    reader.reset_counters()
    attempt, _ = _advance_support(context, request, source)
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert reader.load_view_calls <= 1
    assert reader.atomic_commits == 1

    reader.reset_counters()
    adopted = _adopt_committed_support_successor_v2(
        parent_state,
        request,
        attempt,
    )
    assert type(adopted) is VerifiedSupportStateV2
    assert reader.load_view_calls == 0
    assert reader.atomic_commits == 0
    assert adopted.snapshot == request.snapshot

    # Zero-view adoption is not a trust downgrade: the complete detached
    # attempt is canonicalized before its committed child can be anchored.
    assert attempt.committed_transition is not None
    object.__setattr__(
        attempt.committed_transition.receipt,
        "receipt_root",
        _root("forged:bounded-success-receipt"),
    )
    reader.reset_counters()
    with pytest.raises((GovernanceAuthorityBindingErrorV2, TypeError, ValueError)):
        _adopt_committed_support_successor_v2(
            parent_state,
            request,
            attempt,
        )
    assert reader.load_view_calls == 0
    assert reader.atomic_commits == 0


def _replace_trace_root(view: GovernanceCommitViewV2) -> None:
    assert view.committed_transition is not None
    batch = view.committed_transition.batch
    trace_batch = batch.trace_batch
    events = list(trace_batch.events)
    first = events[0]
    lineage = dict(first.lineage)
    lineage["source_verification_root"] = _root("forged:trace-source")
    events[0] = TraceEvent(
        event_type=first.event_type,
        protocol_id=first.protocol_id,
        target=first.target,
        reason=first.reason,
        lineage=lineage,
    )
    object.__setattr__(
        batch,
        "trace_batch",
        GovernanceTraceBatchV2(
            domain_root=trace_batch.domain_root,
            scope_ref=trace_batch.scope_ref,
            stream_ref=trace_batch.stream_ref,
            transition_id=trace_batch.transition_id,
            events=tuple(events),
        ),
    )


def _replace_read_set_root(view: GovernanceCommitViewV2) -> None:
    assert view.committed_transition is not None
    batch = view.committed_transition.batch
    entries = list(batch.read_set.entries)
    selected = entries[0]
    entries[0] = replace(selected, expected_root=_root("forged:read-set-root"))
    object.__setattr__(
        batch,
        "read_set",
        GovernanceAuthorityReadSetV2(entries=tuple(entries)),
    )


def _replace_delta_record(view: GovernanceCommitViewV2) -> None:
    assert view.committed_transition is not None
    transition = view.committed_transition.batch.transition
    assert transition is not None
    records = cast(dict[str, Any], transition.to_dict()["state_records"])
    request = cast(dict[str, Any], records["request"])
    snapshot = cast(dict[str, Any], request["snapshot"])
    snapshot["mutation_delta_root"] = _root("forged:mutation-delta")
    object.__setattr__(transition, "state_records", records)


@pytest.mark.parametrize(  # type: ignore[misc]
    "mutation",
    ("missing_inclusion", "forged_position", "read_set", "trace", "delta"),
)
def test_malicious_state_reader_or_trace_fails_closed_without_write(
    mutation: str,
) -> None:
    context, reader = _adversarial_context(f"scope:support-v2:malicious:{mutation}")
    request, state, _ = _commit_initialize(context, label=mutation)

    def mutate(view: GovernanceCommitViewV2) -> None:
        if view.transition_id != request.transition_id:
            return
        assert view.committed_transition is not None
        if mutation == "missing_inclusion":
            object.__setattr__(view.committed_transition, "inclusion_proof", None)
        elif mutation == "forged_position":
            assert view.position_observation is not None
            object.__setattr__(
                view.position_observation,
                "observed_head_root",
                _root("forged:observed-head"),
            )
        elif mutation == "read_set":
            _replace_read_set_root(view)
        elif mutation == "trace":
            _replace_trace_root(view)
        else:
            _replace_delta_record(view)

    reader.view_mutator = mutate
    reader.reset_counters()
    assert not support_state_is_current_v2(state)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
        require_current_support_state_v2(state)
    assert caught.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as rehydrate_failure:
        rehydrate_support_state_v2(
            request.to_dict(),
            domain=context.domain,
            state_reader=reader,
        )
    assert rehydrate_failure.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    assert reader.atomic_commits == 0


def test_missing_historical_parent_and_finality_fail_closed() -> None:
    context, reader = _adversarial_context("scope:support-v2:history-finality")
    upstreams = _commit_upstreams(context)
    initialized, initialized_state, _ = _commit_initialize(
        context, label="history-finality"
    )
    issued, issued_source = _prepare_issue(
        context,
        initialized_state,
        upstreams.membership_state,
        label="history-finality",
        current_step=5,
    )
    assert _advance_support(context, issued, issued_source)[0].disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )

    reader.hidden_transition_ids = {initialized.transition_id}
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as missing:
        rehydrate_support_state_v2(
            issued.to_dict(),
            domain=context.domain,
            state_reader=reader,
        )
    assert missing.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    reader.hidden_transition_ids.clear()
    reader.finality_transition_ids = {issued.transition_id}
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as finality:
        rehydrate_support_state_v2(
            issued.to_dict(),
            domain=context.domain,
            state_reader=reader,
        )
    assert finality.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
    )


def test_sealed_domain_denies_new_mutation_but_exact_retry_survives() -> None:
    context = _context(scope_ref="scope:support-v2:sealed")
    upstreams = _commit_upstreams(context)
    initialized, initialized_state, initialized_session = _commit_initialize(
        context, label="sealed"
    )
    pending, pending_source = _prepare_issue(
        context,
        initialized_state,
        upstreams.membership_state,
        label="sealed:pending",
        current_step=5,
    )
    pending_session = open_support_authority_session_v2(
        _capability(context, context.grant, pending.observed_epoch), pending
    )

    retirement = GovernanceDomainRetirementRequestV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref=RUN_REF,
        request_ref="request:support-v2:retire",
        transition_id="transition:support-v2:retire",
        stream_refs=tuple(
            sorted(
                (
                    governance_issuer_grant_stream_ref_v2(
                        context.domain.scope_ref, context.grant.grant_ref
                    ),
                    upstreams.verification_request.stream_ref,
                    upstreams.membership_request.stream_ref,
                    initialized.stream_ref,
                )
            )
        ),
        reason_ref="reason:test-complete",
        observed_epoch=100,
    )
    retirement_session = open_governance_authority_session_v2(
        _capability(context, context.grant, retirement.observed_epoch), retirement
    )
    retired = retire_governance_domain_v2(
        retirement,
        authority_session=retirement_session,
    )
    assert retired.disposition is GovernanceCommitDispositionV2.COMMITTED

    exact_retry = advance_support_state_v2(
        initialized,
        source=None,
        authority_session=initialized_session,
    )
    assert exact_retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    denied = advance_support_state_v2(
        pending,
        source=pending_source,
        authority_session=pending_session,
    )
    _assert_code(
        denied,
        GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
    )


def test_32_identical_and_conflicting_workers_linearize_one_head() -> None:
    identical = _context(scope_ref="scope:support-v2:race-identical")
    request, source = _initialize_request(identical, label="race-identical")
    session = open_support_authority_session_v2(
        _capability(identical, identical.grant, request.observed_epoch), request
    )
    with ThreadPoolExecutor(max_workers=32) as executor:
        outcomes = tuple(
            executor.map(
                lambda _: advance_support_state_v2(
                    request,
                    source=source,
                    authority_session=session,
                ),
                range(32),
            )
        )
    assert all(
        outcome.disposition is GovernanceCommitDispositionV2.COMMITTED
        for outcome in outcomes
    )
    receipts = {
        outcome.committed_transition.receipt.receipt_root
        for outcome in outcomes
        if outcome.committed_transition is not None
    }
    assert len(receipts) == 1
    assert (
        identical.store.load_head_v2(
            identical.domain.scope_ref, request.stream_ref
        ).revision
        == 1
    )

    conflicting = _context(scope_ref="scope:support-v2:race-conflicting")
    candidates = tuple(
        _initialize_request(conflicting, label=f"race-conflicting:{index:02d}")
        for index in range(32)
    )
    sessions = tuple(
        open_support_authority_session_v2(
            _capability(conflicting, conflicting.grant, candidate.observed_epoch),
            candidate,
        )
        for candidate, _ in candidates
    )
    with ThreadPoolExecutor(max_workers=32) as executor:
        conflicts = tuple(
            executor.map(
                lambda item: advance_support_state_v2(
                    item[0][0],
                    source=item[0][1],
                    authority_session=item[1],
                ),
                zip(candidates, sessions, strict=True),
            )
        )
    assert (
        sum(
            outcome.disposition is GovernanceCommitDispositionV2.COMMITTED
            for outcome in conflicts
        )
        == 1
    )
    assert all(
        outcome.disposition
        in (
            GovernanceCommitDispositionV2.COMMITTED,
            GovernanceCommitDispositionV2.RETRY_REQUIRED,
        )
        for outcome in conflicts
    )
    assert (
        conflicting.store.load_head_v2(
            conflicting.domain.scope_ref, candidates[0][0].stream_ref
        ).revision
        == 1
    )


def test_noncanonical_wire_and_resource_exhaustion_do_zero_store_io() -> None:
    context, reader = _adversarial_context("scope:support-v2:wire-resources")
    request, _, _ = _commit_initialize(context, label="wire-resources")
    reader.reset_counters()

    missing_request_root = request.to_dict()
    missing_request_root["request_root"] = ""
    repaired_snapshot_root = request.to_dict()
    repaired_snapshot = cast(dict[str, Any], repaired_snapshot_root["snapshot"])
    repaired_snapshot["snapshot_root"] = ""
    tuple_array = request.to_dict()
    tuple_array["evicted_lease_roots"] = ()
    long_text = request.to_dict()
    long_snapshot = cast(dict[str, Any], long_text["snapshot"])
    long_snapshot["mutation_ref"] = "x" * (MAX_SUPPORT_TEXT_BYTES_V2 + 1)
    long_text["mutation_ref"] = long_snapshot["mutation_ref"]
    too_many_evictions = request.to_dict()
    too_many_evictions["evicted_lease_roots"] = [_root("resource:evicted")] * (
        MAX_SUPPORT_LEASES_V2 + 1
    )
    cyclic = request.to_dict()
    cyclic["caller_extension"] = cyclic

    for payload in (
        missing_request_root,
        repaired_snapshot_root,
        tuple_array,
        long_text,
        too_many_evictions,
        cyclic,
    ):
        with pytest.raises(GovernanceAuthorityBindingErrorV2):
            rehydrate_support_state_v2(
                payload,
                domain=context.domain,
                state_reader=reader,
            )
    assert reader.load_head_calls == 0
    assert reader.load_state_calls == 0
    assert reader.load_view_calls == 0
    assert reader.atomic_commits == 0

    exact_depth: object = None
    for _ in range(MAX_SUPPORT_RESOURCE_DEPTH_V2):
        exact_depth = [exact_depth]
    _preflight_support_resources_v2(exact_depth)
    with pytest.raises(ValueError, match="depth bound"):
        _preflight_support_resources_v2([exact_depth])
    _preflight_support_resources_v2([None] * (MAX_SUPPORT_RESOURCE_NODES_V2 - 1))
    with pytest.raises(ValueError, match="node bound"):
        _preflight_support_resources_v2([None] * MAX_SUPPORT_RESOURCE_NODES_V2)
    _preflight_support_resources_v2("x" * MAX_SUPPORT_RESOURCE_TEXT_BYTES_V2)
    with pytest.raises(ValueError, match="aggregate text"):
        _preflight_support_resources_v2("x" * (MAX_SUPPORT_RESOURCE_TEXT_BYTES_V2 + 1))
