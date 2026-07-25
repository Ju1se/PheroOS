from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import pickle
from typing import Any, Callable, Mapping, cast

import pytest

from pheroos.conformance import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance._authority_session_v2.contracts import (
    _governance_authority_session_state_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance._support_v2.common import (
    _preflight_support_resources_v2,
    _require_bounded_text_v2,
    _require_exact_array_v2,
    _require_exact_mapping_v2,
)
from pheroos.governance._support_v2.principal_verification_source import (
    _expected_source_context_root_v2 as _verification_source_context_root,
)
from pheroos.governance._support_v2.principal_verification_contracts import (
    _validate_snapshot_counts as _validate_verification_snapshot_counts,
    _validate_snapshot_identity as _validate_verification_snapshot_identity,
    _validate_snapshot_versions as _validate_verification_snapshot_versions,
)
from pheroos.governance._support_v2.membership_contracts import (
    _validate_membership_snapshot_timeline,
    _validate_snapshot_identity as _validate_membership_snapshot_identity,
    _validate_snapshot_traces_and_counts,
    _validate_snapshot_versions as _validate_membership_snapshot_versions,
    _validated_membership_trace_roots,
)
from pheroos.governance._support_v2.membership_operations import (
    _committed_view_matches as _membership_committed_view_matches,
    _head_from_view as _membership_head_from_view,
    _load_parent as _load_membership_parent,
    _validated_session as _validated_membership_session,
)
from pheroos.governance._support_v2.membership_state import (
    _continuity_failure as _membership_continuity_failure,
    _decode_state_records as _decode_membership_state_records,
    _load_verified_request_view as _load_verified_membership_request_view,
    _validate_history as _validate_membership_history,
    _validate_read_set as _validate_membership_read_set,
    _validate_session_binding as _validate_membership_session_binding,
    _validate_verification_inclusion,
)
from pheroos.governance._support_v2.principal_verification_operations import (
    _committed_view_matches as _verification_committed_view_matches,
    _head_from_view as _verification_head_from_view,
    _load_parent as _load_verification_parent,
    _validated_session as _validated_verification_session,
)
from pheroos.governance._support_v2.principal_verification_state import (
    _continuity_failure as _verification_continuity_failure,
    _decode_state_records as _decode_verification_state_records,
    _load_verified_request_view as _load_verified_verification_request_view,
    _validate_history as _validate_verification_history,
    _validate_read_set as _validate_verification_read_set,
    _validate_session_binding as _validate_verification_session_binding,
)
from pheroos.governance._support_v2.support_source_proof import (
    _expected_source_roots,
    _validate_revocation_projection,
    _validate_source_upstreams,
    _verified_source as _verified_support_source,
    _verified_source_manifest_v2,
)
from pheroos.governance._support_v2.support_committed_state import (
    _decode_state_records as _decode_support_state_records,
    _validate_membership_precondition as _validate_support_membership_precondition,
    _validate_stored_session_binding,
)
from pheroos.governance._support_v2.support_evaluation_contracts import (
    _normalize_evaluation_collections,
    _validate_evaluation_derivations,
    _validate_evaluation_scalars,
)
from pheroos.governance._support_v2.support_evaluation_engine import (
    _active_interval,
    _conflict_segments,
    _lease_matches_evaluation,
    _lease_status,
    _validate_evaluation_context,
)
from pheroos.governance._support_v2.support_event_lineage import (
    support_issued_event_lineage_v2,
    support_revoked_event_lineage_v2,
)
from pheroos.governance._support_v2.support_evidence_contracts import (
    _bounded_root_tuple,
    _bounded_text_tuple,
    _validate_bound_context,
)
from pheroos.governance._support_v2.support_incremental_state import (
    _adopt_committed_support_successor_v2,
)
from pheroos.governance._support_v2.support_lease_contracts import (
    _index_collision,
)
from pheroos.governance._support_v2.support_prepare import (
    _child_request,
)
from pheroos.governance._support_v2.support_state_access import (
    _membership_handle_fields,
    _membership_parent_authority_material_v2,
    _validate_membership_heads,
    _validate_membership_projection,
)
from pheroos.governance._support_v2.support_state_handle import (
    _current_support_source_material_v2,
    _make_verified_state,
    _require_domain as _require_support_domain,
    _require_state_reader,
    _state_handle_fields,
    _validate_current_projection,
)
from pheroos.governance._support_v2.support_verification import (
    _membership_principal,
    _validate_membership,
    _validate_observations,
    _validate_parent_proposal,
    _validate_policy,
    _validate_request_manifest_context_v2,
    _validate_switch_prior,
    _validated_child_manifest_v2,
    _validated_support_manifest_context_v2,
)
from pheroos.governance._support_v2.support_request_contracts import (
    _lease_or_none,
    _revocation_or_none,
    _validate_exact_mutation_lineage,
    _validate_initialize_semantics,
    _validate_issued_record,
    _validate_mutation_presence,
    _validate_replacement,
    _validate_revoked_records,
    _validate_support_mutation_semantics_v2,
)
from pheroos.governance._support_v2.support_operations import (
    _committed_view_matches_request,
    _resolve_write_head,
    _source_failure_from_error,
    _validated_session_or_failure,
    _write_head_or_failure,
)
from pheroos.governance._support_v2.support_snapshot_contracts import (
    _validate_snapshot_continuity,
    _validate_snapshot_records,
    _validate_snapshot_shape,
    _validate_snapshot_values,
    _validate_snapshot_versions,
)
from pheroos.governance.support_v2 import (
    MembershipClusterV2,
    MembershipCommitRequestV2,
    MembershipPrincipalV2,
    MembershipSnapshotV2,
    PrincipalVerificationRecordV2,
    PrincipalVerificationSetAdvanceRequestV2,
    PrincipalVerificationSetSnapshotV2,
    SupportAdvanceRequestV2,
    SupportEquivocationV2,
    SupportEvaluationV2,
    SupportLeaseV2,
    SupportLeaseProposalV2,
    SupportLeaseStatusV2,
    SupportMutationKindV2,
    SupportObservationV2,
    SupportSnapshotV2,
    VerifiedMembershipSourceV2,
    VerifiedMembershipStateV2,
    VerifiedPrincipalVerificationSourceV2,
    VerifiedPrincipalVerificationSetStateV2,
    VerifiedSupportSourceV2,
    VerifiedSupportStateV2,
    active_support_lease_from_parent_v2,
    advance_principal_verification_set_v2,
    advance_support_state_v2,
    canonical_membership_clusters_v2,
    canonical_support_leases_v2,
    canonical_support_observations_v2,
    canonical_verification_records_v2,
    commit_membership_epoch_v2,
    durable_support_context_v2,
    evaluate_support_v2,
    membership_state_is_current_v2,
    membership_stream_ref_v2,
    open_membership_authority_session_v2,
    open_principal_verification_authority_session_v2,
    open_support_authority_session_v2,
    prepare_membership_commit_v2,
    prepare_principal_verification_set_v2,
    prepare_support_initialize_v2,
    prepare_support_issue_v2,
    prepare_support_revoke_v2,
    prepare_support_switch_v2,
    principal_verification_set_is_current_v2,
    principal_verification_stream_ref_v2,
    project_support_lease_v2,
    rehydrate_membership_state_v2,
    rehydrate_principal_verification_set_state_v2,
    rehydrate_support_state_v2,
    replacement_matches_prior_v2,
    require_current_membership_state_v2,
    require_current_principal_verification_set_v2,
    require_current_support_state_v2,
    revocation_matches_lease_v2,
    support_lease_status_v2,
    support_history_advance_v2,
    support_mutation_delta_root_v2,
    support_state_is_current_v2,
    support_stream_ref_v2,
    support_switch_lineage_v2,
    support_transition_id_v2,
    verify_membership_request_source_v2,
    verify_principal_verification_source_v2,
    verify_support_request_source_v2,
)
from pheroos.protocol import (
    COMMIT_INTEGRITY_PROFILE_VERSION,
    PROTOCOL_SCHEMA_V3,
    CollectiveCommitPolicy,
    CommitAssurance,
    ScopedProtocolManifestV2,
    read_protocol_manifest,
)
from pheroos.protocol.authority_v2 import (
    MAX_AUTHORITY_REVISION_V2,
    AuthorityDiagnosticCodeV2,
    GovernanceReadPreconditionV2,
)
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from pheroos.trace import TraceEvent


ROOT = Path(__file__).resolve().parents[2]
PROFILE = COMMIT_INTEGRITY_PROFILE_VERSION
TARGET = "decision:support-v2"
RUN_REF = "run:support-v2-public-semantics"
ISSUER_REF = "issuer:support-v2-public-semantics"


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _manifest() -> ScopedProtocolManifestV2:
    payload = json.loads(
        (ROOT / "examples/support-v2-protocol/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = read_protocol_manifest(payload, schema_version=PROTOCOL_SCHEMA_V3)
    assert type(manifest) is ScopedProtocolManifestV2
    return cast(ScopedProtocolManifestV2, manifest)


@dataclass(frozen=True, slots=True)
class _Ledger:
    adapter: ReferenceGovernanceStateStoreConformanceAdapterV2
    domain: AuthorityDomainV2
    store: GovernanceStateStoreV2
    grant: GovernanceIssuerGrantV2
    manifest: ScopedProtocolManifestV2


@dataclass(frozen=True, slots=True)
class _Upstream:
    verification_request: PrincipalVerificationSetAdvanceRequestV2
    verification_state: VerifiedPrincipalVerificationSetStateV2
    membership_request: MembershipCommitRequestV2
    membership_state: VerifiedMembershipStateV2


class _ReaderProxy:
    def __init__(self, store: GovernanceStateStoreV2) -> None:
        self.store = store
        self.head_error: Exception | None = None
        self.state_error: Exception | None = None
        self.view_error: Exception | None = None
        self.head_hook: Callable[[str, str, GovernanceHeadV2], object] | None = None
        self.state_hook: Callable[[str, str, Mapping[str, Any]], object] | None = None
        self.view_hook: (
            Callable[[str, str, str, GovernanceCommitViewV2], object] | None
        ) = None

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        if self.head_error is not None:
            raise self.head_error
        head = self.store.load_head_v2(scope_ref, stream_ref)
        if self.head_hook is None:
            return head
        return cast(GovernanceHeadV2, self.head_hook(scope_ref, stream_ref, head))

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        if self.state_error is not None:
            raise self.state_error
        state = self.store.load_state_v2(scope_ref, stream_ref)
        if self.state_hook is None:
            return state
        return cast(Mapping[str, Any], self.state_hook(scope_ref, stream_ref, state))

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        if self.view_error is not None:
            raise self.view_error
        view = self.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )
        if self.view_hook is None:
            return view
        return cast(
            GovernanceCommitViewV2,
            self.view_hook(scope_ref, stream_ref, transition_id, view),
        )


def _grant(domain: AuthorityDomainV2) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref=ISSUER_REF,
        grant_ref=f"grant:{domain.scope_ref}",
        grant_binding_ref=_root(f"grant-binding:{domain.scope_ref}"),
        operations=(
            GovernanceIssuerOperationV2.EVALUATE_QUORUM,
            GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
        ),
        target_refs=(TARGET,),
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=10_000,
        revocation_generation=0,
    )


def _ledger(label: str) -> _Ledger:
    adapter = ReferenceGovernanceStateStoreConformanceAdapterV2()
    domain = adapter.create_domain_v2(f"scope:support-v2-public:{label}")
    store = adapter.create_store_v2((domain,))
    grant = _grant(domain)
    activated = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        f"transition:grant:{label}",
        1,
    )
    assert activated.disposition is GovernanceCommitDispositionV2.COMMITTED
    return _Ledger(adapter, domain, store, grant, _manifest())


def _capability(ledger: _Ledger, observed_epoch: int) -> GovernanceIssuerCapabilityV2:
    return bind_governance_issuer_capability_v2(
        ledger.store,
        ledger.domain,
        ledger.grant,
        RUN_REF,
        observed_epoch,
    )


def _assert_committed(attempt: GovernanceCommitAttemptV2) -> None:
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert attempt.committed_transition is not None


def _verification_record(
    principal_ref: str,
    cluster_ref: str,
    *,
    label: str,
) -> PrincipalVerificationRecordV2:
    return PrincipalVerificationRecordV2(
        principal_ref=principal_ref,
        cluster_ref=cluster_ref,
        failure_domain_ref=f"failure-domain:{cluster_ref}",
        verification_method="external-attestation-v2",
        verification_issuer_ref="identity:public-verifier",
        attestation_root=_root(f"attestation:{label}"),
        evidence_roots=(_root(f"verification-evidence:{label}"),),
        issued_at_step=1,
        expires_at_step=100,
        provenance_ref=f"urn:test:verification:{label}",
        source_trace_roots=(_root(f"verification-trace:{label}"),),
    )


def _prepare_verification(
    ledger: _Ledger,
    *,
    label: str,
    epoch: int,
    parent: PrincipalVerificationSetSnapshotV2 | None = None,
    issuer_ref: str = ISSUER_REF,
    current_step: int | None = None,
) -> tuple[
    PrincipalVerificationSetAdvanceRequestV2,
    VerifiedPrincipalVerificationSourceV2,
]:
    records = (
        _verification_record(
            "principal:alpha",
            "cluster:alpha",
            label=f"{label}:alpha",
        ),
        _verification_record(
            "principal:beta",
            "cluster:beta",
            label=f"{label}:beta",
        ),
    )
    return prepare_principal_verification_set_v2(
        domain_root=ledger.domain.domain_root,
        scope_ref=ledger.domain.scope_ref,
        manifest=ledger.manifest,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        run_ref=RUN_REF,
        target_ref=TARGET,
        epoch=epoch,
        observed_epoch=10 + epoch,
        advance_ref=f"advance:verification:{label}",
        snapshot_ref=f"snapshot:verification:{label}",
        current_step=epoch if current_step is None else current_step,
        expires_at_step=100,
        mutation_issuer_ref=issuer_ref,
        records=records,
        parent_snapshot=parent,
    )


def _commit_verification(
    ledger: _Ledger,
    *,
    label: str,
    epoch: int,
    parent: PrincipalVerificationSetSnapshotV2 | None = None,
) -> tuple[
    PrincipalVerificationSetAdvanceRequestV2,
    VerifiedPrincipalVerificationSetStateV2,
]:
    request, source = _prepare_verification(
        ledger,
        label=label,
        epoch=epoch,
        parent=parent,
    )
    session = open_principal_verification_authority_session_v2(
        _capability(ledger, request.observed_epoch),
        request,
    )
    _assert_committed(
        advance_principal_verification_set_v2(
            request,
            source=source,
            authority_session=session,
        )
    )
    state = rehydrate_principal_verification_set_state_v2(
        json.loads(request.canonical_bytes()),
        domain=ledger.domain,
        state_reader=ledger.store,
    )
    return request, state


def _prepare_membership(
    ledger: _Ledger,
    verification_state: VerifiedPrincipalVerificationSetStateV2,
    *,
    label: str,
    epoch: int,
    parent: MembershipSnapshotV2 | None = None,
    issuer_ref: str = ISSUER_REF,
    current_step: int | None = None,
    expires_at_step: int = 90,
) -> tuple[MembershipCommitRequestV2, VerifiedMembershipSourceV2]:
    return prepare_membership_commit_v2(
        domain_root=ledger.domain.domain_root,
        scope_ref=ledger.domain.scope_ref,
        manifest=ledger.manifest,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        run_ref=RUN_REF,
        target_ref=TARGET,
        epoch=epoch,
        observed_epoch=20 + epoch,
        request_ref=f"request:membership:{label}",
        snapshot_ref=f"snapshot:membership:{label}",
        current_step=epoch + 1 if current_step is None else current_step,
        expires_at_step=expires_at_step,
        mutation_issuer_ref=issuer_ref,
        membership_method="store-current-verification-set-v2",
        provenance_ref=f"urn:test:membership:{label}",
        source_trace_roots=(_root(f"membership-trace:{label}"),),
        verification_state=verification_state,
        parent_snapshot=parent,
    )


def _commit_membership(
    ledger: _Ledger,
    verification_state: VerifiedPrincipalVerificationSetStateV2,
    *,
    label: str,
    epoch: int,
    parent: MembershipSnapshotV2 | None = None,
) -> tuple[MembershipCommitRequestV2, VerifiedMembershipStateV2]:
    request, source = _prepare_membership(
        ledger,
        verification_state,
        label=label,
        epoch=epoch,
        parent=parent,
    )
    session = open_membership_authority_session_v2(
        _capability(ledger, request.observed_epoch),
        request,
    )
    _assert_committed(
        commit_membership_epoch_v2(
            request,
            source=source,
            authority_session=session,
        )
    )
    state = rehydrate_membership_state_v2(
        json.loads(request.canonical_bytes()),
        domain=ledger.domain,
        state_reader=ledger.store,
    )
    return request, state


def _upstream(ledger: _Ledger, *, label: str = "genesis") -> _Upstream:
    verification_request, verification_state = _commit_verification(
        ledger,
        label=label,
        epoch=1,
    )
    membership_request, membership_state = _commit_membership(
        ledger,
        verification_state,
        label=label,
        epoch=1,
    )
    return _Upstream(
        verification_request,
        verification_state,
        membership_request,
        membership_state,
    )


def _advance_support(
    ledger: _Ledger,
    request: SupportAdvanceRequestV2,
    source: VerifiedSupportSourceV2 | None,
) -> GovernanceCommitAttemptV2:
    session = open_support_authority_session_v2(
        _capability(ledger, request.observed_epoch),
        request,
    )
    return advance_support_state_v2(
        request,
        source=source,
        authority_session=session,
    )


def _initialize(
    ledger: _Ledger,
    *,
    label: str,
    issuer_ref: str = ISSUER_REF,
) -> tuple[SupportAdvanceRequestV2, VerifiedSupportSourceV2]:
    return prepare_support_initialize_v2(
        domain_root=ledger.domain.domain_root,
        scope_ref=ledger.domain.scope_ref,
        manifest=ledger.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        issuer_ref=issuer_ref,
        observed_epoch=30,
        mutation_ref=f"mutation:support:initialize:{label}",
        current_step=3,
        provenance_root=_root(f"support-initialize-provenance:{label}"),
        source_trace_roots=(_root(f"support-initialize-trace:{label}"),),
    )


def _support_state(
    ledger: _Ledger,
    request: SupportAdvanceRequestV2,
) -> VerifiedSupportStateV2:
    return rehydrate_support_state_v2(
        json.loads(request.canonical_bytes()),
        domain=ledger.domain,
        state_reader=ledger.store,
    )


def _observation(
    ledger: _Ledger,
    membership: MembershipSnapshotV2,
    *,
    candidate_ref: str,
    claim_root: str,
    principal_ref: str,
    label: str,
    current_step: int,
) -> SupportObservationV2:
    policy = ledger.manifest.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    return SupportObservationV2(
        observation_ref=f"observation:{label}",
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=ledger.manifest.manifest_root,
        commit_policy_root=commit_policy_fingerprint(policy, profile=PROFILE),
        protocol_ref=ledger.manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET,
        candidate_ref=candidate_ref,
        claim_root=claim_root,
        epoch=membership.epoch,
        source_ref=f"source:{principal_ref}:{label}",
        evidence_root=_root(f"observation-evidence:{label}"),
        observed_at_step=current_step,
        expires_at_step=current_step + 8,
        provenance_root=_root(f"observation-provenance:{label}"),
        source_trace_roots=(_root(f"observation-trace:{label}"),),
    )


def _proposal(
    ledger: _Ledger,
    membership: MembershipSnapshotV2,
    observation: SupportObservationV2,
    *,
    candidate_ref: str,
    claim_root: str,
    principal_ref: str,
    label: str,
    current_step: int,
) -> SupportLeaseProposalV2:
    policy = ledger.manifest.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    return SupportLeaseProposalV2(
        proposal_ref=f"proposal:{label}",
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=ledger.manifest.manifest_root,
        commit_policy_root=commit_policy_fingerprint(policy, profile=PROFILE),
        protocol_ref=ledger.manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET,
        candidate_ref=candidate_ref,
        claim_root=claim_root,
        epoch=membership.epoch,
        principal_ref=principal_ref,
        positive_observation_roots=(observation.observation_root,),
        nonce=f"nonce:{label}",
        proposed_at_step=current_step,
        provenance_root=_root(f"proposal-provenance:{label}"),
        source_trace_roots=(_root(f"proposal-trace:{label}"),),
    )


def _prepare_issue(
    ledger: _Ledger,
    parent_state: VerifiedSupportStateV2,
    membership_state: VerifiedMembershipStateV2,
    *,
    candidate_ref: str,
    claim_root: str,
    principal_ref: str,
    label: str,
    current_step: int,
) -> tuple[SupportAdvanceRequestV2, VerifiedSupportSourceV2]:
    membership = membership_state.snapshot
    observation = _observation(
        ledger,
        membership,
        candidate_ref=candidate_ref,
        claim_root=claim_root,
        principal_ref=principal_ref,
        label=label,
        current_step=current_step,
    )
    proposal = _proposal(
        ledger,
        membership,
        observation,
        candidate_ref=candidate_ref,
        claim_root=claim_root,
        principal_ref=principal_ref,
        label=label,
        current_step=current_step,
    )
    return prepare_support_issue_v2(
        manifest=ledger.manifest,
        parent_state=parent_state,
        membership_state=membership_state,
        proposal=proposal,
        positive_observations=(observation,),
        issuer_ref=ISSUER_REF,
        observed_epoch=30 + current_step,
        mutation_ref=f"mutation:support:issue:{label}",
        current_step=current_step,
        issuance_provenance_root=_root(f"issue-provenance:{label}"),
        issuance_trace_roots=(_root(f"issue-trace:{label}"),),
    )


def _prepare_switch(
    ledger: _Ledger,
    parent_state: VerifiedSupportStateV2,
    membership_state: VerifiedMembershipStateV2,
    *,
    prior_lease_root: str,
    candidate_ref: str,
    claim_root: str,
    principal_ref: str,
    label: str,
    current_step: int,
) -> tuple[SupportAdvanceRequestV2, VerifiedSupportSourceV2]:
    membership = membership_state.snapshot
    observation = _observation(
        ledger,
        membership,
        candidate_ref=candidate_ref,
        claim_root=claim_root,
        principal_ref=principal_ref,
        label=label,
        current_step=current_step,
    )
    proposal = _proposal(
        ledger,
        membership,
        observation,
        candidate_ref=candidate_ref,
        claim_root=claim_root,
        principal_ref=principal_ref,
        label=label,
        current_step=current_step,
    )
    return prepare_support_switch_v2(
        manifest=ledger.manifest,
        parent_state=parent_state,
        membership_state=membership_state,
        prior_lease_root=prior_lease_root,
        proposal=proposal,
        positive_observations=(observation,),
        issuer_ref=ISSUER_REF,
        revocation_reason_codes=("candidate-switch",),
        observed_epoch=30 + current_step,
        mutation_ref=f"mutation:support:switch:{label}",
        current_step=current_step,
        revocation_provenance_root=_root(f"switch-revoke-provenance:{label}"),
        revocation_trace_roots=(_root(f"switch-revoke-trace:{label}"),),
        issuance_provenance_root=_root(f"switch-issue-provenance:{label}"),
        issuance_trace_roots=(_root(f"switch-issue-trace:{label}"),),
    )


def _prepare_revoke(
    ledger: _Ledger,
    parent_state: VerifiedSupportStateV2,
    *,
    lease_root: str,
    label: str,
    current_step: int,
) -> tuple[SupportAdvanceRequestV2, VerifiedSupportSourceV2]:
    return prepare_support_revoke_v2(
        manifest=ledger.manifest,
        parent_state=parent_state,
        lease_root=lease_root,
        reason_codes=("completed",),
        issuer_ref=ISSUER_REF,
        observed_epoch=30 + current_step,
        mutation_ref=f"mutation:support:revoke:{label}",
        current_step=current_step,
        provenance_root=_root(f"revoke-provenance:{label}"),
        source_trace_roots=(_root(f"revoke-trace:{label}"),),
    )


def test_public_support_v2_full_lifecycle_and_replay_are_deterministic() -> None:
    ledger = _ledger("lifecycle")
    upstream = _upstream(ledger)
    initialized, initialized_source = _initialize(ledger, label="lifecycle")
    initialized_session = open_support_authority_session_v2(
        _capability(ledger, initialized.observed_epoch),
        initialized,
    )
    initialized_attempt = advance_support_state_v2(
        initialized,
        source=initialized_source,
        authority_session=initialized_session,
    )
    _assert_committed(initialized_attempt)
    initialized_state = _support_state(ledger, initialized)
    assert require_current_support_state_v2(initialized_state).leases == ()

    claim_root = _root("claim:lifecycle")
    issued, issued_source = _prepare_issue(
        ledger,
        initialized_state,
        upstream.membership_state,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="lifecycle:issue",
        current_step=5,
    )
    issued_attempt = _advance_support(ledger, issued, issued_source)
    _assert_committed(issued_attempt)
    assert issued.issued_lease is not None
    issued_state = _support_state(ledger, issued)
    assert (
        support_lease_status_v2(
            issued_state,
            issued.issued_lease.lease_root,
            current_step=5,
        )
        is SupportLeaseStatusV2.ACTIVE
    )
    assert (
        support_lease_status_v2(
            issued_state,
            issued.issued_lease.lease_root,
            current_step=issued.issued_lease.expires_at_step,
        )
        is SupportLeaseStatusV2.EXPIRED
    )

    switched, switched_source = _prepare_switch(
        ledger,
        issued_state,
        upstream.membership_state,
        prior_lease_root=issued.issued_lease.lease_root,
        candidate_ref="candidate:support-v2:safe",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="lifecycle:switch",
        current_step=6,
    )
    switched_attempt = _advance_support(ledger, switched, switched_source)
    _assert_committed(switched_attempt)
    assert switched.revoked_lease == issued.issued_lease
    assert switched.revocation is not None
    assert switched.issued_lease is not None
    assert revocation_matches_lease_v2(switched.revocation, issued.issued_lease)
    assert replacement_matches_prior_v2(switched.issued_lease, issued.issued_lease)
    switched_state = _support_state(ledger, switched)
    assert tuple(lease.lease_root for lease in switched_state.snapshot.leases) == (
        switched.issued_lease.lease_root,
    )

    revoked, revoked_source = _prepare_revoke(
        ledger,
        switched_state,
        lease_root=switched.issued_lease.lease_root,
        label="lifecycle",
        current_step=7,
    )
    revoked_attempt = _advance_support(ledger, revoked, revoked_source)
    _assert_committed(revoked_attempt)
    assert revoked.revocation is not None
    assert revoked.revoked_lease == switched.issued_lease
    assert revocation_matches_lease_v2(
        revoked.revocation,
        switched.issued_lease,
    )
    revoked_state = _support_state(ledger, revoked)
    assert revoked_state.snapshot.leases == ()
    assert revoked_state.snapshot.history_count == 4

    replay = advance_support_state_v2(
        initialized,
        source=None,
        authority_session=initialized_session,
    )
    _assert_committed(replay)
    assert replay.committed_transition is not None
    assert initialized_attempt.committed_transition is not None
    assert replay.committed_transition.receipt.receipt_root == (
        initialized_attempt.committed_transition.receipt.receipt_root
    )

    restarted = ledger.adapter.restart_store_v2(ledger.store)
    recovered = rehydrate_support_state_v2(
        json.loads(revoked.canonical_bytes()),
        domain=ledger.domain,
        state_reader=restarted,
    )
    assert require_current_support_state_v2(recovered) == revoked.snapshot

    event_types = tuple(
        event.event_type
        for request in (initialized, issued, switched, revoked)
        for event in _committed_events(ledger.store, ledger.domain.scope_ref, request)
    )
    assert event_types == (
        "support_state_advanced",
        "support_state_advanced",
        "support_lease_issued_v2",
        "support_state_advanced",
        "support_lease_revoked_v2",
        "support_lease_issued_v2",
        "support_state_advanced",
        "support_lease_revoked_v2",
    )


def _committed_events(
    store: GovernanceStateStoreV2,
    scope_ref: str,
    request: SupportAdvanceRequestV2,
) -> tuple[TraceEvent, ...]:
    view = store.load_commit_view_v2(
        scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    assert view.committed_transition is not None
    return tuple(view.committed_transition.batch.trace_batch.events)


def test_public_support_v2_conflicting_parent_and_missing_proofs_fail_closed() -> None:
    ledger = _ledger("conflict")
    upstream = _upstream(ledger)
    initialized, initialized_source = _initialize(ledger, label="conflict")
    _assert_committed(_advance_support(ledger, initialized, initialized_source))
    initialized_state = _support_state(ledger, initialized)
    claim_root = _root("claim:conflict")

    winner, winner_source = _prepare_issue(
        ledger,
        initialized_state,
        upstream.membership_state,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="conflict:winner",
        current_step=5,
    )
    loser, loser_source = _prepare_issue(
        ledger,
        initialized_state,
        upstream.membership_state,
        candidate_ref="candidate:support-v2:safe",
        claim_root=claim_root,
        principal_ref="principal:beta",
        label="conflict:loser",
        current_step=5,
    )
    loser_session = open_support_authority_session_v2(
        _capability(ledger, loser.observed_epoch),
        loser,
    )
    _assert_committed(_advance_support(ledger, winner, winner_source))
    rejected = advance_support_state_v2(
        loser,
        source=loser_source,
        authority_session=loser_session,
    )
    assert rejected.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert rejected.failure is not None
    assert rejected.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE

    winner_state = _support_state(ledger, winner)
    missing_source, _ = _prepare_issue(
        ledger,
        winner_state,
        upstream.membership_state,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        principal_ref="principal:beta",
        label="conflict:missing-source",
        current_step=6,
    )
    missing_source_session = open_support_authority_session_v2(
        _capability(ledger, missing_source.observed_epoch),
        missing_source,
    )
    denied_source = advance_support_state_v2(
        missing_source,
        source=None,
        authority_session=missing_source_session,
    )
    assert denied_source.disposition is GovernanceCommitDispositionV2.INVALID
    assert denied_source.failure is not None
    assert (
        denied_source.failure.code
        is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )
    assert denied_source.failure.path == "/source"

    denied_session = advance_support_state_v2(
        missing_source,
        source=None,
        authority_session=None,
    )
    assert denied_session.disposition is GovernanceCommitDispositionV2.DENIED
    assert denied_session.failure is not None
    assert (
        denied_session.failure.code
        is AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED
    )
    assert not support_state_is_current_v2(initialized_state)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        require_current_support_state_v2(initialized_state)


def test_public_support_v2_membership_successor_invalidates_old_handles() -> None:
    ledger = _ledger("membership-successor")
    first = _upstream(ledger)
    second_verification_request, second_verification_state = _commit_verification(
        ledger,
        label="successor",
        epoch=2,
        parent=first.verification_request.snapshot,
    )
    second_membership_request, second_membership_state = _commit_membership(
        ledger,
        second_verification_state,
        label="successor",
        epoch=2,
        parent=first.membership_request.snapshot,
    )

    assert not principal_verification_set_is_current_v2(first.verification_state)
    assert not membership_state_is_current_v2(first.membership_state)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        require_current_principal_verification_set_v2(first.verification_state)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        require_current_membership_state_v2(first.membership_state)
    assert principal_verification_set_is_current_v2(second_verification_state)
    assert membership_state_is_current_v2(second_membership_state)
    assert second_verification_state.snapshot == second_verification_request.snapshot
    assert second_membership_state.snapshot == second_membership_request.snapshot


def test_public_support_v2_evaluation_excludes_cluster_equivocation() -> None:
    ledger = _ledger("equivocation")
    upstream = _upstream(ledger)
    initialized, initialized_source = _initialize(ledger, label="equivocation")
    _assert_committed(_advance_support(ledger, initialized, initialized_source))
    initialized_state = _support_state(ledger, initialized)
    claim_root = _root("claim:equivocation")

    first, first_source = _prepare_issue(
        ledger,
        initialized_state,
        upstream.membership_state,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="equivocation:accept",
        current_step=5,
    )
    _assert_committed(_advance_support(ledger, first, first_source))
    first_state = _support_state(ledger, first)
    second, second_source = _prepare_issue(
        ledger,
        first_state,
        upstream.membership_state,
        candidate_ref="candidate:support-v2:safe",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="equivocation:safe",
        current_step=6,
    )
    _assert_committed(_advance_support(ledger, second, second_source))
    assert first.issued_lease is not None
    assert second.issued_lease is not None
    second_state = _support_state(ledger, second)

    evaluation = evaluate_support_v2(
        support_state=second_state,
        membership_state=upstream.membership_state,
        manifest=ledger.manifest,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        epoch=upstream.membership_request.epoch,
        current_step=6,
    )
    assert evaluation.active_support_cluster_count == 0
    assert evaluation.policy_support_met is False
    assert evaluation.included_lease_roots == ()
    assert set(evaluation.excluded_lease_roots) == {
        first.issued_lease.lease_root,
        second.issued_lease.lease_root,
    }
    assert len(evaluation.equivocations) == 1
    finding = evaluation.equivocations[0]
    assert finding.principal_cluster_ref == "cluster:alpha"
    assert set(finding.conflicting_candidate_refs) == {
        "candidate:support-v2:accept",
        "candidate:support-v2:safe",
    }
    assert (
        support_lease_status_v2(
            second_state,
            first.issued_lease.lease_root,
            current_step=6,
        )
        is SupportLeaseStatusV2.EQUIVOCATED
    )
    assert (
        support_lease_status_v2(
            second_state,
            second.issued_lease.lease_root,
            current_step=6,
        )
        is SupportLeaseStatusV2.EQUIVOCATED
    )


def test_public_support_v2_record_construction_rejects_malformed_state() -> None:
    record = _verification_record(
        "principal:malformed",
        "cluster:malformed",
        label="malformed",
    )
    with pytest.raises((TypeError, ValueError, GovernanceError)):
        replace(record, evidence_roots=(record.evidence_roots[0],) * 2)
    with pytest.raises((TypeError, ValueError, GovernanceError)):
        replace(record, expires_at_step=record.issued_at_step)

    noncanonical = record.to_dict()
    noncanonical["evidence_roots"] = tuple(record.evidence_roots)
    with pytest.raises(TypeError):
        PrincipalVerificationRecordV2.from_dict(noncanonical)

    unknown = record.to_dict()
    unknown["caller_claimed_authority"] = True
    with pytest.raises(ValueError):
        PrincipalVerificationRecordV2.from_dict(unknown)


def test_public_support_v2_rejects_cross_request_source_without_writing() -> None:
    ledger = _ledger("cross-source")
    upstream = _upstream(ledger)
    initialized, initialized_source = _initialize(ledger, label="cross-source")
    _assert_committed(_advance_support(ledger, initialized, initialized_source))
    initialized_state = _support_state(ledger, initialized)
    claim_root = _root("claim:cross-source")
    request_a, _ = _prepare_issue(
        ledger,
        initialized_state,
        upstream.membership_state,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="cross-source:a",
        current_step=5,
    )
    _, source_b = _prepare_issue(
        ledger,
        initialized_state,
        upstream.membership_state,
        candidate_ref="candidate:support-v2:safe",
        claim_root=claim_root,
        principal_ref="principal:beta",
        label="cross-source:b",
        current_step=5,
    )
    before = ledger.store.load_head_v2(
        ledger.domain.scope_ref,
        request_a.stream_ref,
    )
    rejected = _advance_support(ledger, request_a, source_b)
    after = ledger.store.load_head_v2(
        ledger.domain.scope_ref,
        request_a.stream_ref,
    )
    assert rejected.disposition is GovernanceCommitDispositionV2.INVALID
    assert rejected.failure is not None
    assert rejected.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    assert before == after


def test_public_support_v2_opaque_handles_are_immutable_and_nonportable() -> None:
    ledger = _ledger("opaque-handles")
    verification_request, verification_source = _prepare_verification(
        ledger,
        label="opaque",
        epoch=1,
    )
    verification_session = open_principal_verification_authority_session_v2(
        _capability(ledger, verification_request.observed_epoch),
        verification_request,
    )
    _assert_committed(
        advance_principal_verification_set_v2(
            verification_request,
            source=verification_source,
            authority_session=verification_session,
        )
    )
    verification_state = rehydrate_principal_verification_set_state_v2(
        verification_request.to_dict(),
        domain=ledger.domain,
        state_reader=ledger.store,
    )
    membership_request, membership_source = _prepare_membership(
        ledger,
        verification_state,
        label="opaque",
        epoch=1,
    )
    membership_session = open_membership_authority_session_v2(
        _capability(ledger, membership_request.observed_epoch),
        membership_request,
    )
    _assert_committed(
        commit_membership_epoch_v2(
            membership_request,
            source=membership_source,
            authority_session=membership_session,
        )
    )
    membership_state = rehydrate_membership_state_v2(
        membership_request.to_dict(),
        domain=ledger.domain,
        state_reader=ledger.store,
    )
    support_request, support_source = _initialize(ledger, label="opaque")
    _assert_committed(_advance_support(ledger, support_request, support_source))
    support_state = _support_state(ledger, support_request)

    source_objects = (
        verification_source,
        membership_source,
        support_source,
    )
    state_objects = (
        verification_state,
        membership_state,
        support_state,
    )
    opaque_types = (
        VerifiedPrincipalVerificationSourceV2,
        VerifiedMembershipSourceV2,
        VerifiedSupportSourceV2,
        VerifiedPrincipalVerificationSetStateV2,
        VerifiedMembershipStateV2,
        VerifiedSupportStateV2,
    )
    for opaque_type in opaque_types:
        with pytest.raises(TypeError):
            opaque_type()
        with pytest.raises(TypeError):
            type(f"Forbidden{opaque_type.__name__}", (opaque_type,), {})

    for opaque in (*source_objects, *state_objects):
        with pytest.raises(AttributeError):
            setattr(opaque, "_request", None)
        with pytest.raises(TypeError):
            pickle.dumps(opaque)
        with pytest.raises(TypeError):
            opaque.__reduce__()
        with pytest.raises(TypeError):
            opaque.__reduce_ex__(pickle.HIGHEST_PROTOCOL)

    for source in source_objects:
        assert source.context_root.startswith("sha256:")

    expected_states = (
        (verification_state, verification_request),
        (membership_state, membership_request),
        (support_state, support_request),
    )
    for state, request in expected_states:
        assert state.snapshot == request.snapshot
        assert state.request_root == request.request_root
        assert state.stream_ref == request.stream_ref
        assert state.transition_id == request.transition_id
        assert state.receipt_root.startswith("sha256:")
        assert state.position.value == "current"

    assert copy.copy(support_source) is support_source
    assert copy.deepcopy(support_source) is support_source
    assert repr(support_source) == "<VerifiedSupportSourceV2 redacted>"
    with pytest.raises(TypeError):
        support_source.__getstate__()
    assert copy.copy(support_state) is support_state
    assert copy.deepcopy(support_state) is support_state
    assert repr(support_state) == "<VerifiedSupportStateV2 redacted>"
    with pytest.raises(TypeError):
        support_state.__getstate__()

    assert not principal_verification_set_is_current_v2(object())
    assert not membership_state_is_current_v2(object())
    assert not support_state_is_current_v2(object())
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        require_current_principal_verification_set_v2(object())
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        require_current_membership_state_v2(object())
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        require_current_support_state_v2(object())


def test_public_support_v2_identity_records_are_canonical_and_total() -> None:
    first = _verification_record(
        "principal:record:first",
        "cluster:record:first",
        label="record:first",
    )
    second = _verification_record(
        "principal:record:second",
        "cluster:record:second",
        label="record:second",
    )
    assert first.root() == first.verification_root
    assert json.loads(first.canonical_bytes()) == first.to_dict()

    with pytest.raises(TypeError):
        canonical_verification_records_v2(cast(Any, "not-an-array"))
    with pytest.raises(TypeError):
        canonical_verification_records_v2(cast(Any, (object(),)))
    with pytest.raises(ValueError):
        canonical_verification_records_v2((first, first))
    reused_attestation = replace(
        second,
        attestation_root=first.attestation_root,
        verification_root="",
    )
    with pytest.raises(ValueError):
        canonical_verification_records_v2((first, reused_attestation))
    duplicate_root = replace(second, verification_root="")
    object.__setattr__(duplicate_root, "verification_root", first.verification_root)
    with pytest.raises(ValueError):
        canonical_verification_records_v2((first, duplicate_root))
    with pytest.raises(TypeError):
        replace(first, evidence_roots=cast(Any, {"not": "an array"}))
    with pytest.raises(ValueError):
        replace(first, schema="unsupported")
    with pytest.raises(ValueError):
        replace(first, verification_root=_root("wrong:verification-root"))

    principal = MembershipPrincipalV2(
        principal_ref="principal:membership-record",
        verification_root=first.verification_root,
        verified_issuer_ref=first.verification_issuer_ref,
        verification_method=first.verification_method,
        failure_domain_ref=first.failure_domain_ref,
    )
    assert principal.root() == principal.principal_root
    assert json.loads(principal.canonical_bytes()) == principal.to_dict()
    with pytest.raises(ValueError):
        replace(principal, schema="unsupported")
    with pytest.raises(ValueError):
        replace(principal, principal_root=_root("wrong:principal-root"))

    cluster = MembershipClusterV2(
        cluster_ref="cluster:membership-record",
        principals=(principal,),
    )
    assert cluster.root() == cluster.cluster_root
    assert json.loads(cluster.canonical_bytes()) == cluster.to_dict()
    with pytest.raises(ValueError):
        replace(cluster, schema="unsupported")
    with pytest.raises(TypeError):
        replace(cluster, principals=cast(Any, {"not": "an array"}))
    with pytest.raises(ValueError):
        replace(cluster, principals=())
    with pytest.raises(TypeError):
        replace(cluster, principals=cast(Any, (object(),)))
    with pytest.raises(ValueError):
        replace(cluster, principals=(principal, principal))
    with pytest.raises(ValueError):
        replace(cluster, cluster_root=_root("wrong:cluster-root"))

    with pytest.raises(TypeError):
        canonical_membership_clusters_v2(cast(Any, "not-an-array"))
    with pytest.raises(TypeError):
        canonical_membership_clusters_v2(cast(Any, (object(),)))
    with pytest.raises(ValueError):
        canonical_membership_clusters_v2((cluster, cluster))
    oversized_cluster = replace(cluster, cluster_root="")
    object.__setattr__(oversized_cluster, "principals", (principal,) * 4097)
    with pytest.raises(ValueError):
        canonical_membership_clusters_v2((oversized_cluster,))


def test_public_support_v2_request_and_snapshot_contracts_fail_closed() -> None:
    ledger = _ledger("request-snapshot-contracts")
    upstream = _upstream(ledger)
    initialized, initialized_source = _initialize(
        ledger,
        label="request-snapshot-contracts",
    )
    _assert_committed(_advance_support(ledger, initialized, initialized_source))
    initialized_state = _support_state(ledger, initialized)
    claim_root = _root("claim:request-snapshot-contracts")
    issued, issued_source = _prepare_issue(
        ledger,
        initialized_state,
        upstream.membership_state,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="request-snapshot-contracts:issue",
        current_step=5,
    )
    _assert_committed(_advance_support(ledger, issued, issued_source))
    issued_state = _support_state(ledger, issued)
    assert issued.issued_lease is not None
    switched, _ = _prepare_switch(
        ledger,
        issued_state,
        upstream.membership_state,
        prior_lease_root=issued.issued_lease.lease_root,
        candidate_ref="candidate:support-v2:safe",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="request-snapshot-contracts:switch",
        current_step=6,
    )
    revoked, _ = _prepare_revoke(
        ledger,
        issued_state,
        lease_root=issued.issued_lease.lease_root,
        label="request-snapshot-contracts",
        current_step=6,
    )
    assert switched.issued_lease is not None
    assert switched.revoked_lease is not None
    assert switched.revocation is not None
    assert revoked.revoked_lease is not None
    assert revoked.revocation is not None

    with pytest.raises(ValueError):
        replace(initialized, schema="unsupported")
    with pytest.raises(ValueError):
        replace(initialized, canonical_version="unsupported")
    with pytest.raises(TypeError):
        replace(initialized, snapshot=cast(Any, object()))
    with pytest.raises(ValueError):
        replace(initialized, scope_ref="scope:cross-bound")
    with pytest.raises(ValueError):
        replace(initialized, request_root=_root("wrong:request-root"))

    malformed_request = initialized.to_dict()
    malformed_request["mutation_kind"] = "unsupported"
    with pytest.raises(ValueError):
        SupportAdvanceRequestV2.from_dict(malformed_request)
    malformed_request = initialized.to_dict()
    malformed_request["evicted_lease_roots"] = ()
    with pytest.raises(TypeError):
        SupportAdvanceRequestV2.from_dict(malformed_request)
    with pytest.raises(ValueError):
        _lease_or_none({"not": "a lease"}, "issued lease")
    with pytest.raises(ValueError):
        _revocation_or_none({"not": "a revocation"})

    with pytest.raises(ValueError):
        _validate_mutation_presence(
            initialized,
            ("", "", ""),
            ("membership:unexpected", "", ""),
        )
    with pytest.raises(ValueError):
        _validate_mutation_presence(
            issued,
            ("", "", ""),
            (
                issued.membership_stream_ref,
                issued.membership_transition_id,
                issued.membership_snapshot_root,
            ),
        )
    with pytest.raises(ValueError):
        _validate_mutation_presence(
            revoked,
            (
                _root("unexpected:issued-lease"),
                revoked.revoked_lease_root,
                revoked.revocation_root,
            ),
            ("", "", ""),
        )
    with pytest.raises(ValueError):
        _validate_mutation_presence(
            switched,
            (
                switched.issued_lease_root,
                "",
                switched.revocation_root,
            ),
            (
                switched.membership_stream_ref,
                switched.membership_transition_id,
                switched.membership_snapshot_root,
            ),
        )

    tampered_snapshot = SupportSnapshotV2.from_dict(initialized.snapshot.to_dict())
    object.__setattr__(tampered_snapshot, "leases", (issued.issued_lease,))
    initialized_with_lease = SupportAdvanceRequestV2.from_dict(initialized.to_dict())
    object.__setattr__(initialized_with_lease, "snapshot", tampered_snapshot)
    with pytest.raises(ValueError):
        _validate_initialize_semantics(initialized_with_lease)
    wrong_initial_step = SupportAdvanceRequestV2.from_dict(initialized.to_dict())
    wrong_step_snapshot = SupportSnapshotV2.from_dict(initialized.snapshot.to_dict())
    object.__setattr__(wrong_step_snapshot, "current_step", 4)
    object.__setattr__(wrong_initial_step, "snapshot", wrong_step_snapshot)
    with pytest.raises(ValueError):
        _validate_initialize_semantics(wrong_initial_step)

    active_roots = {issued.issued_lease.lease_root}
    for field, value in (
        ("lease_root", _root("wrong:issued-lease")),
        ("mutation_transition_id", "transition:wrong"),
        ("issuance_issuer_ref", "issuer:wrong"),
        ("issued_at_step", issued.snapshot.current_step + 1),
    ):
        altered = SupportAdvanceRequestV2.from_dict(issued.to_dict())
        assert altered.issued_lease is not None
        object.__setattr__(altered.issued_lease, field, value)
        with pytest.raises(ValueError):
            _validate_issued_record(altered, altered.issued_lease, active_roots)
    with pytest.raises(ValueError):
        _validate_issued_record(issued, issued.issued_lease, set())

    for target, field, value in (
        ("lease", "lease_root", _root("wrong:revoked-lease")),
        ("revocation", "revocation_root", _root("wrong:revocation")),
        ("revocation", "mutation_transition_id", "transition:wrong"),
        ("revocation", "revocation_issuer_ref", "issuer:wrong"),
        ("revocation", "revoked_at_step", revoked.snapshot.current_step + 1),
        ("revocation", "candidate_ref", "candidate:wrong"),
    ):
        altered = SupportAdvanceRequestV2.from_dict(revoked.to_dict())
        assert altered.revoked_lease is not None
        assert altered.revocation is not None
        record = altered.revoked_lease if target == "lease" else altered.revocation
        object.__setattr__(record, field, value)
        with pytest.raises(ValueError):
            _validate_revoked_records(
                altered,
                altered.revoked_lease,
                altered.revocation,
                set(),
            )
    with pytest.raises(ValueError):
        _validate_revoked_records(
            revoked,
            revoked.revoked_lease,
            revoked.revocation,
            {revoked.revoked_lease.lease_root},
        )

    incompatible_replacement = SupportAdvanceRequestV2.from_dict(switched.to_dict())
    assert incompatible_replacement.issued_lease is not None
    assert incompatible_replacement.revoked_lease is not None
    object.__setattr__(
        incompatible_replacement.issued_lease,
        "candidate_ref",
        incompatible_replacement.revoked_lease.candidate_ref,
    )
    with pytest.raises(ValueError):
        _validate_replacement(
            incompatible_replacement.issued_lease,
            incompatible_replacement.revoked_lease,
        )
    wrong_prior = SupportAdvanceRequestV2.from_dict(switched.to_dict())
    assert wrong_prior.issued_lease is not None
    assert wrong_prior.revoked_lease is not None
    object.__setattr__(
        wrong_prior.issued_lease,
        "prior_lease_root",
        _root("wrong:prior-lease"),
    )
    with pytest.raises(ValueError):
        _validate_replacement(wrong_prior.issued_lease, wrong_prior.revoked_lease)
    wrong_lineage = SupportAdvanceRequestV2.from_dict(issued.to_dict())
    lineage_snapshot = SupportSnapshotV2.from_dict(issued.snapshot.to_dict())
    object.__setattr__(
        lineage_snapshot,
        "mutation_provenance_root",
        _root("wrong:lineage"),
    )
    object.__setattr__(wrong_lineage, "snapshot", lineage_snapshot)
    with pytest.raises(ValueError):
        _validate_exact_mutation_lineage(wrong_lineage)

    with pytest.raises(ValueError):
        replace(initialized.snapshot, lease_set_root=_root("wrong:lease-set"))
    with pytest.raises(ValueError):
        replace(initialized.snapshot, snapshot_root=_root("wrong:snapshot"))
    malformed_snapshot = initialized.snapshot.to_dict()
    malformed_snapshot["assurance"] = "unsupported"
    with pytest.raises(ValueError):
        SupportSnapshotV2.from_dict(malformed_snapshot)

    for field, value in (
        ("stream_ref", "support:wrong-stream"),
        ("transition_id", "transition:wrong"),
    ):
        snapshot = SupportSnapshotV2.from_dict(initialized.snapshot.to_dict())
        object.__setattr__(snapshot, field, value)
        with pytest.raises(ValueError):
            _validate_snapshot_shape(snapshot)
    for field, value in (
        ("schema", "unsupported"),
        ("state_schema", "unsupported"),
        ("canonical_version", "unsupported"),
    ):
        snapshot = SupportSnapshotV2.from_dict(initialized.snapshot.to_dict())
        object.__setattr__(snapshot, field, value)
        with pytest.raises(ValueError):
            _validate_snapshot_versions(snapshot)
    for field, value in (
        ("mutation_kind", "initialize"),
        ("assurance", "evidence_bound"),
        ("profile", "unsupported"),
    ):
        snapshot = SupportSnapshotV2.from_dict(initialized.snapshot.to_dict())
        object.__setattr__(snapshot, field, value)
        with pytest.raises((TypeError, ValueError)):
            _validate_snapshot_values(snapshot)

    continuity_cases = (
        ("revision", 2),
        ("current_step", initialized.snapshot.initialized_at_step - 1),
        ("history_root", _root("wrong:history")),
        ("history_count", initialized.snapshot.history_count + 1),
        ("mutation_kind", SupportMutationKindV2.ISSUE),
        ("parent_transition_id", "transition:wrong-parent"),
    )
    for field, value in continuity_cases:
        snapshot = SupportSnapshotV2.from_dict(initialized.snapshot.to_dict())
        object.__setattr__(snapshot, field, value)
        with pytest.raises(ValueError):
            _validate_snapshot_continuity(snapshot)
    non_genesis_initialize = SupportSnapshotV2.from_dict(issued.snapshot.to_dict())
    object.__setattr__(
        non_genesis_initialize,
        "mutation_kind",
        SupportMutationKindV2.INITIALIZE,
    )
    with pytest.raises(ValueError):
        _validate_snapshot_continuity(non_genesis_initialize)

    cross_bound_lease = SupportAdvanceRequestV2.from_dict(issued.to_dict()).issued_lease
    assert cross_bound_lease is not None
    object.__setattr__(cross_bound_lease, "run_ref", "run:cross-bound")
    with pytest.raises(ValueError):
        _validate_snapshot_records(issued.snapshot, (cross_bound_lease,))
    stale_lease = SupportAdvanceRequestV2.from_dict(issued.to_dict()).issued_lease
    assert stale_lease is not None
    object.__setattr__(stale_lease, "expires_at_step", issued.snapshot.current_step)
    with pytest.raises(ValueError):
        _validate_snapshot_records(issued.snapshot, (stale_lease,))
    retained_prior = SupportAdvanceRequestV2.from_dict(switched.to_dict()).issued_lease
    assert retained_prior is not None
    with pytest.raises(ValueError):
        _validate_snapshot_records(
            switched.snapshot,
            (retained_prior, switched.revoked_lease),
        )


def test_public_support_v2_upstream_operations_bind_session_source_and_scope() -> None:
    verification_ledger = _ledger("verification-operation-bindings")
    verification_request, verification_source = _prepare_verification(
        verification_ledger,
        label="operation-bindings",
        epoch=1,
    )
    verification_session = open_principal_verification_authority_session_v2(
        _capability(
            verification_ledger,
            verification_request.observed_epoch,
        ),
        verification_request,
    )
    missing_session = advance_principal_verification_set_v2(
        verification_request,
        source=verification_source,
        authority_session=None,
    )
    assert missing_session.disposition is GovernanceCommitDispositionV2.DENIED
    missing_source = advance_principal_verification_set_v2(
        verification_request,
        source=None,
        authority_session=verification_session,
    )
    assert missing_source.disposition is GovernanceCommitDispositionV2.INVALID
    _, cross_verification_source = _prepare_verification(
        verification_ledger,
        label="operation-bindings:cross",
        epoch=1,
    )
    cross_source = advance_principal_verification_set_v2(
        verification_request,
        source=cross_verification_source,
        authority_session=verification_session,
    )
    assert cross_source.disposition is GovernanceCommitDispositionV2.INVALID
    _assert_committed(
        advance_principal_verification_set_v2(
            verification_request,
            source=verification_source,
            authority_session=verification_session,
        )
    )
    _assert_committed(
        advance_principal_verification_set_v2(
            verification_request,
            source=None,
            authority_session=verification_session,
        )
    )
    verification_state = rehydrate_principal_verification_set_state_v2(
        verification_request,
        domain=verification_ledger.domain,
        state_reader=verification_ledger.store,
    )
    assert verification_state.snapshot == verification_request.snapshot

    wrong_verification_ledger = _ledger("verification-wrong-session")
    wrong_verification_issuer, _ = _prepare_verification(
        wrong_verification_ledger,
        label="wrong-issuer",
        epoch=1,
        issuer_ref="issuer:not-authorized",
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        open_principal_verification_authority_session_v2(
            _capability(
                wrong_verification_ledger,
                wrong_verification_issuer.observed_epoch,
            ),
            wrong_verification_issuer,
        )

    foreign = _ledger("foreign-upstream-scope")
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        rehydrate_principal_verification_set_state_v2(
            verification_request.to_dict(),
            domain=foreign.domain,
            state_reader=foreign.store,
        )
    with pytest.raises(TypeError):
        rehydrate_principal_verification_set_state_v2(
            verification_request.to_dict(),
            domain=cast(AuthorityDomainV2, object()),
            state_reader=verification_ledger.store,
        )
    with pytest.raises(TypeError):
        rehydrate_principal_verification_set_state_v2(
            verification_request.to_dict(),
            domain=verification_ledger.domain,
            state_reader=cast(GovernanceStateStoreV2, object()),
        )
    incomplete_verification_state = object.__new__(
        VerifiedPrincipalVerificationSetStateV2
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        require_current_principal_verification_set_v2(incomplete_verification_state)
    with pytest.raises(TypeError):
        advance_principal_verification_set_v2(
            cast(PrincipalVerificationSetAdvanceRequestV2, object())
        )

    membership_ledger = _ledger("membership-operation-bindings")
    _, committed_verification_state = _commit_verification(
        membership_ledger,
        label="membership-operation-bindings",
        epoch=1,
    )
    membership_request, membership_source = _prepare_membership(
        membership_ledger,
        committed_verification_state,
        label="operation-bindings",
        epoch=1,
    )
    membership_session = open_membership_authority_session_v2(
        _capability(membership_ledger, membership_request.observed_epoch),
        membership_request,
    )
    missing_membership_session = commit_membership_epoch_v2(
        membership_request,
        source=membership_source,
        authority_session=None,
    )
    assert (
        missing_membership_session.disposition is GovernanceCommitDispositionV2.DENIED
    )
    missing_membership_source = commit_membership_epoch_v2(
        membership_request,
        source=None,
        authority_session=membership_session,
    )
    assert (
        missing_membership_source.disposition is GovernanceCommitDispositionV2.INVALID
    )
    _, cross_membership_source = _prepare_membership(
        membership_ledger,
        committed_verification_state,
        label="operation-bindings:cross",
        epoch=1,
    )
    cross_membership = commit_membership_epoch_v2(
        membership_request,
        source=cross_membership_source,
        authority_session=membership_session,
    )
    assert cross_membership.disposition is GovernanceCommitDispositionV2.INVALID
    _assert_committed(
        commit_membership_epoch_v2(
            membership_request,
            source=membership_source,
            authority_session=membership_session,
        )
    )
    _assert_committed(
        commit_membership_epoch_v2(
            membership_request,
            source=None,
            authority_session=membership_session,
        )
    )
    membership_state = rehydrate_membership_state_v2(
        membership_request,
        domain=membership_ledger.domain,
        state_reader=membership_ledger.store,
    )
    assert membership_state.snapshot == membership_request.snapshot

    wrong_membership_ledger = _ledger("membership-wrong-session")
    _, wrong_membership_verification = _commit_verification(
        wrong_membership_ledger,
        label="wrong-membership-issuer",
        epoch=1,
    )
    wrong_membership_issuer, _ = _prepare_membership(
        wrong_membership_ledger,
        wrong_membership_verification,
        label="wrong-issuer",
        epoch=1,
        issuer_ref="issuer:not-authorized",
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        open_membership_authority_session_v2(
            _capability(
                wrong_membership_ledger,
                wrong_membership_issuer.observed_epoch,
            ),
            wrong_membership_issuer,
        )

    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        rehydrate_membership_state_v2(
            membership_request.to_dict(),
            domain=foreign.domain,
            state_reader=foreign.store,
        )
    with pytest.raises(TypeError):
        rehydrate_membership_state_v2(
            membership_request.to_dict(),
            domain=cast(AuthorityDomainV2, object()),
            state_reader=membership_ledger.store,
        )
    with pytest.raises(TypeError):
        rehydrate_membership_state_v2(
            membership_request.to_dict(),
            domain=membership_ledger.domain,
            state_reader=cast(GovernanceStateStoreV2, object()),
        )
    incomplete_membership_state = object.__new__(VerifiedMembershipStateV2)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        require_current_membership_state_v2(incomplete_membership_state)
    with pytest.raises(TypeError):
        commit_membership_epoch_v2(cast(MembershipCommitRequestV2, object()))


def test_public_support_v2_source_proofs_and_contexts_fail_closed() -> None:
    ledger = _ledger("source-proof-totality")
    verification_request, verification_source = _prepare_verification(
        ledger,
        label="source-proof",
        epoch=1,
    )
    verify_principal_verification_source_v2(
        verification_request,
        source=verification_source,
    )
    assert _verification_source_context_root(verification_request).startswith("sha256:")
    with pytest.raises(TypeError):
        verify_principal_verification_source_v2(
            cast(PrincipalVerificationSetAdvanceRequestV2, object()),
            source=verification_source,
        )
    with pytest.raises(TypeError):
        verify_principal_verification_source_v2(
            verification_request,
            source=object(),
        )
    incomplete_verification_source = object.__new__(
        VerifiedPrincipalVerificationSourceV2
    )
    with pytest.raises(TypeError):
        verify_principal_verification_source_v2(
            verification_request,
            source=incomplete_verification_source,
        )
    malformed_verification_source = object.__new__(
        VerifiedPrincipalVerificationSourceV2
    )
    object.__setattr__(malformed_verification_source, "_binding", object())
    object.__setattr__(malformed_verification_source, "_manifest", ledger.manifest)
    object.__setattr__(
        malformed_verification_source,
        "_request",
        verification_request,
    )
    with pytest.raises(TypeError):
        verify_principal_verification_source_v2(
            verification_request,
            source=malformed_verification_source,
        )
    cross_bound_verification_source = _prepare_verification(
        ledger,
        label="source-proof:tampered",
        epoch=1,
    )[1]
    verification_binding = object.__getattribute__(
        cross_bound_verification_source,
        "_binding",
    )
    object.__setattr__(
        verification_binding,
        "request_root",
        _root("wrong:verification-source-binding"),
    )
    with pytest.raises(ValueError):
        verify_principal_verification_source_v2(
            verification_request,
            source=cross_bound_verification_source,
        )
    with pytest.raises(TypeError):
        _verification_source_context_root(
            cast(PrincipalVerificationSetAdvanceRequestV2, object())
        )
    with pytest.raises(TypeError):
        _prepare_verification(
            ledger,
            label="source-proof:wrong-parent",
            epoch=2,
            parent=cast(PrincipalVerificationSetSnapshotV2, object()),
        )
    foreign_request, _ = _prepare_verification(
        _ledger("source-proof-foreign-parent"),
        label="foreign-parent",
        epoch=1,
    )
    with pytest.raises(ValueError):
        _prepare_verification(
            ledger,
            label="source-proof:cross-parent",
            epoch=2,
            parent=foreign_request.snapshot,
        )
    with pytest.raises(ValueError):
        _prepare_verification(
            ledger,
            label="source-proof:epoch-does-not-advance",
            epoch=1,
            parent=verification_request.snapshot,
        )
    with pytest.raises(ValueError):
        _prepare_verification(
            ledger,
            label="source-proof:step-does-not-advance",
            epoch=2,
            current_step=verification_request.snapshot.current_step,
            parent=verification_request.snapshot,
        )

    _, verification_state = _commit_verification(
        ledger,
        label="source-proof",
        epoch=1,
    )
    membership_request, membership_source = _prepare_membership(
        ledger,
        verification_state,
        label="source-proof",
        epoch=1,
    )
    verify_membership_request_source_v2(
        membership_request,
        source=membership_source,
    )
    with pytest.raises(TypeError):
        verify_membership_request_source_v2(
            cast(MembershipCommitRequestV2, object()),
            source=membership_source,
        )
    with pytest.raises(TypeError):
        verify_membership_request_source_v2(
            membership_request,
            source=object(),
        )
    incomplete_membership_source = object.__new__(VerifiedMembershipSourceV2)
    with pytest.raises(TypeError):
        verify_membership_request_source_v2(
            membership_request,
            source=incomplete_membership_source,
        )
    malformed_membership_source = object.__new__(VerifiedMembershipSourceV2)
    object.__setattr__(malformed_membership_source, "_binding", object())
    object.__setattr__(malformed_membership_source, "_manifest", ledger.manifest)
    object.__setattr__(
        malformed_membership_source,
        "_request",
        membership_request,
    )
    with pytest.raises(TypeError):
        verify_membership_request_source_v2(
            membership_request,
            source=malformed_membership_source,
        )
    _, cross_bound_membership_source = _prepare_membership(
        ledger,
        verification_state,
        label="source-proof:tampered",
        epoch=1,
    )
    membership_binding = object.__getattribute__(
        cross_bound_membership_source,
        "_binding",
    )
    object.__setattr__(
        membership_binding,
        "request_root",
        _root("wrong:membership-source-binding"),
    )
    with pytest.raises(ValueError):
        verify_membership_request_source_v2(
            membership_request,
            source=cross_bound_membership_source,
        )
    with pytest.raises(TypeError):
        _prepare_membership(
            ledger,
            cast(VerifiedPrincipalVerificationSetStateV2, object()),
            label="source-proof:wrong-verification-state",
            epoch=1,
        )
    with pytest.raises(TypeError):
        _prepare_membership(
            ledger,
            verification_state,
            label="source-proof:wrong-parent",
            epoch=1,
            parent=cast(MembershipSnapshotV2, object()),
        )
    with pytest.raises(ValueError):
        _prepare_membership(
            ledger,
            verification_state,
            label="source-proof:epoch-mismatch",
            epoch=2,
        )

    context = durable_support_context_v2(
        ledger.manifest,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        target_ref=TARGET,
    )
    assert context.target_ref == TARGET
    with pytest.raises(TypeError):
        durable_support_context_v2(
            cast(ScopedProtocolManifestV2, object()),
            profile=PROFILE,
            assurance=CommitAssurance.EVIDENCE_BOUND,
            target_ref=TARGET,
        )
    with pytest.raises(TypeError):
        durable_support_context_v2(
            ledger.manifest,
            profile=PROFILE,
            assurance=cast(CommitAssurance, "evidence_bound"),
            target_ref=TARGET,
        )
    with pytest.raises(ValueError):
        durable_support_context_v2(
            ledger.manifest,
            profile="unsupported",
            assurance=CommitAssurance.EVIDENCE_BOUND,
            target_ref=TARGET,
        )
    with pytest.raises(ValueError):
        durable_support_context_v2(
            ledger.manifest,
            profile=PROFILE,
            assurance=CommitAssurance.EVIDENCE_BOUND,
            target_ref="target:not-declared",
        )
    no_policy = replace(ledger.manifest, collective_commit_policy=None)
    with pytest.raises(ValueError):
        durable_support_context_v2(
            no_policy,
            profile=PROFILE,
            assurance=CommitAssurance.EVIDENCE_BOUND,
            target_ref=TARGET,
        )
    policy = ledger.manifest.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    cross_bound_policy = replace(
        ledger.manifest,
        collective_commit_policy=replace(
            policy,
            assurance=CommitAssurance.CERTIFIED.value,
        ),
    )
    with pytest.raises(ValueError):
        durable_support_context_v2(
            cross_bound_policy,
            profile=PROFILE,
            assurance=CommitAssurance.EVIDENCE_BOUND,
            target_ref=TARGET,
        )


def test_support_v2_portable_resource_totality_guards() -> None:
    with pytest.raises(ValueError):
        _preflight_support_resources_v2("\ud800")
    with pytest.raises(TypeError):
        _preflight_support_resources_v2({1: "non-text-key"})
    cyclic: list[object] = []
    cyclic.append(cyclic)
    with pytest.raises(ValueError):
        _preflight_support_resources_v2(cyclic)
    with pytest.raises(ValueError):
        _require_bounded_text_v2("\ud800", "surrogate")
    with pytest.raises(TypeError):
        _require_exact_mapping_v2([], frozenset(), "mapping")
    with pytest.raises(TypeError):
        _require_exact_array_v2((), "array", limit=1)


def test_public_support_v2_source_proof_rebuilds_every_declared_upstream() -> None:
    ledger = _ledger("support-source-proof")
    upstream = _upstream(ledger)
    initialized, initialized_source = _initialize(
        ledger,
        label="support-source-proof",
    )
    assert (
        verify_support_request_source_v2(
            initialized,
            source=initialized_source,
        )
        is None
    )
    material = _verified_support_source(initialized_source)
    with pytest.raises(TypeError):
        material.__reduce__()
    with pytest.raises(TypeError):
        material.__reduce_ex__(pickle.HIGHEST_PROTOCOL)
    with pytest.raises(TypeError):
        material.__getstate__()
    with pytest.raises(TypeError):
        verify_support_request_source_v2(
            cast(SupportAdvanceRequestV2, object()),
            source=initialized_source,
        )
    with pytest.raises(TypeError):
        verify_support_request_source_v2(initialized, source=object())

    incomplete = object.__new__(VerifiedSupportSourceV2)
    with pytest.raises(TypeError):
        verify_support_request_source_v2(initialized, source=incomplete)
    malformed = object.__new__(VerifiedSupportSourceV2)
    for name, value in (
        ("_binding", object()),
        ("_manifest", ledger.manifest),
        ("_request", initialized),
        ("_parent_state", None),
        ("_membership_state", None),
        ("_proposal", None),
        ("_observations", None),
    ):
        object.__setattr__(malformed, name, value)
    with pytest.raises(TypeError):
        verify_support_request_source_v2(initialized, source=malformed)

    cross_bound_request, cross_bound_source = _initialize(
        ledger,
        label="support-source-proof:cross-bound",
    )
    cross_binding = object.__getattribute__(cross_bound_source, "_binding")
    object.__setattr__(
        cross_binding,
        "request_root",
        _root("wrong:support-source-binding"),
    )
    with pytest.raises(ValueError):
        verify_support_request_source_v2(
            cross_bound_request,
            source=cross_bound_source,
        )

    undeclared_request, undeclared_source = _initialize(
        ledger,
        label="support-source-proof:undeclared",
    )
    object.__setattr__(undeclared_source, "_parent_state", object())
    with pytest.raises(ValueError):
        verify_support_request_source_v2(
            undeclared_request,
            source=undeclared_source,
        )
    with pytest.raises(TypeError):
        _validate_source_upstreams(
            initialized,
            manifest=object(),
            parent_state=None,
            membership_state=None,
            proposal=None,
            observations=None,
        )

    other_request, other_source = _initialize(
        ledger,
        label="support-source-proof:other",
    )
    with pytest.raises(ValueError):
        verify_support_request_source_v2(initialized, source=other_source)
    with pytest.raises(ValueError):
        _expected_source_roots(initialized, other_source)
    assert other_request.request_root != initialized.request_root

    _assert_committed(_advance_support(ledger, initialized, initialized_source))
    initialized_state = _support_state(ledger, initialized)
    claim_root = _root("claim:support-source-proof")
    issue, issue_source = _prepare_issue(
        ledger,
        initialized_state,
        upstream.membership_state,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="support-source-proof:issue",
        current_step=5,
    )
    membership_precondition = verify_support_request_source_v2(
        issue,
        source=issue_source,
    )
    assert membership_precondition is not None

    foreign = _ledger("support-source-proof-foreign")
    foreign_initialized, foreign_source = _initialize(
        foreign,
        label="foreign",
    )
    _assert_committed(_advance_support(foreign, foreign_initialized, foreign_source))
    foreign_state = _support_state(foreign, foreign_initialized)
    mismatched_parent, mismatched_parent_source = _prepare_issue(
        ledger,
        initialized_state,
        upstream.membership_state,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="support-source-proof:mismatched-parent",
        current_step=5,
    )
    object.__setattr__(
        mismatched_parent_source,
        "_parent_state",
        foreign_state,
    )
    with pytest.raises(ValueError):
        verify_support_request_source_v2(
            mismatched_parent,
            source=mismatched_parent_source,
        )

    rebuilt_mismatch, rebuilt_mismatch_source = _prepare_issue(
        ledger,
        initialized_state,
        upstream.membership_state,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="support-source-proof:rebuilt-mismatch",
        current_step=5,
    )
    private_issue = object.__getattribute__(rebuilt_mismatch_source, "_request")
    assert private_issue.issued_lease is not None
    object.__setattr__(
        private_issue.issued_lease,
        "candidate_ref",
        "candidate:support-v2:safe",
    )
    object.__setattr__(
        private_issue.snapshot.leases[0],
        "candidate_ref",
        "candidate:support-v2:safe",
    )
    with pytest.raises(ValueError):
        verify_support_request_source_v2(
            rebuilt_mismatch,
            source=rebuilt_mismatch_source,
        )

    _assert_committed(_advance_support(ledger, issue, issue_source))
    issued_state = _support_state(ledger, issue)
    assert issue.issued_lease is not None
    revoked, revoked_source = _prepare_revoke(
        ledger,
        issued_state,
        lease_root=issue.issued_lease.lease_root,
        label="support-source-proof",
        current_step=6,
    )
    assert revoked.revocation is not None
    assert revoked.revoked_lease is not None
    verify_support_request_source_v2(revoked, source=revoked_source)

    caller_material, caller_material_source = _prepare_revoke(
        ledger,
        issued_state,
        lease_root=issue.issued_lease.lease_root,
        label="support-source-proof:caller-material",
        current_step=6,
    )
    object.__setattr__(caller_material_source, "_proposal", object())
    with pytest.raises(ValueError):
        verify_support_request_source_v2(
            caller_material,
            source=caller_material_source,
        )

    incomplete_revocation = SupportAdvanceRequestV2.from_dict(revoked.to_dict())
    object.__setattr__(incomplete_revocation, "revocation", None)
    with pytest.raises(ValueError):
        _validate_revocation_projection(
            incomplete_revocation,
            issued_state.snapshot,
        )
    wrong_prior = SupportAdvanceRequestV2.from_dict(revoked.to_dict())
    assert wrong_prior.revoked_lease is not None
    object.__setattr__(
        wrong_prior.revoked_lease,
        "candidate_ref",
        "candidate:support-v2:safe",
    )
    with pytest.raises(ValueError):
        _validate_revocation_projection(wrong_prior, issued_state.snapshot)
    wrong_revocation = SupportAdvanceRequestV2.from_dict(revoked.to_dict())
    assert wrong_revocation.revocation is not None
    object.__setattr__(
        wrong_revocation.revocation,
        "candidate_ref",
        "candidate:support-v2:safe",
    )
    with pytest.raises(ValueError):
        _validate_revocation_projection(wrong_revocation, issued_state.snapshot)


def test_public_support_v2_state_handles_reverify_store_heads_and_projection() -> None:
    ledger = _ledger("state-handle-reverification")
    upstream = _upstream(ledger)
    initialized, initialized_source = _initialize(
        ledger,
        label="state-handle-reverification",
    )
    _assert_committed(_advance_support(ledger, initialized, initialized_source))
    state = _support_state(ledger, initialized)
    snapshot, precondition = _current_support_source_material_v2(state)
    assert snapshot == initialized.snapshot
    assert precondition.expected_revision == initialized.snapshot.revision

    anchor = object.__getattribute__(state, "_anchor")
    with pytest.raises(TypeError):
        anchor.__reduce__()
    with pytest.raises(TypeError):
        anchor.__reduce_ex__(pickle.HIGHEST_PROTOCOL)
    with pytest.raises(TypeError):
        anchor.__getstate__()

    missing_head = _support_state(ledger, initialized)
    missing_head_reader = _ReaderProxy(ledger.store)
    missing_head_reader.head_error = KeyError("hidden")
    object.__setattr__(missing_head, "_reader", missing_head_reader)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _current_support_source_material_v2(missing_head)

    malformed_head = _support_state(ledger, initialized)
    malformed_head_reader = _ReaderProxy(ledger.store)
    malformed_head_reader.head_hook = lambda *_args: object()
    object.__setattr__(malformed_head, "_reader", malformed_head_reader)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _current_support_source_material_v2(malformed_head)

    foreign = _ledger("state-handle-foreign-head")
    cross_bound_head = _support_state(ledger, initialized)
    cross_bound_reader = _ReaderProxy(ledger.store)
    cross_bound_reader.head_hook = (
        lambda _scope, stream, _head: GovernanceHeadV2.genesis(
            foreign.domain,
            stream,
        )
    )
    object.__setattr__(cross_bound_head, "_reader", cross_bound_reader)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _current_support_source_material_v2(cross_bound_head)

    stale_head = _support_state(ledger, initialized)
    stale_reader = _ReaderProxy(ledger.store)
    stale_reader.head_hook = lambda _scope, stream, _head: GovernanceHeadV2.genesis(
        ledger.domain,
        stream,
    )
    object.__setattr__(stale_head, "_reader", stale_reader)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _current_support_source_material_v2(stale_head)

    missing_projection = _support_state(ledger, initialized)
    missing_projection_reader = _ReaderProxy(ledger.store)
    missing_projection_reader.state_error = KeyError("hidden")
    object.__setattr__(
        missing_projection,
        "_reader",
        missing_projection_reader,
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _current_support_source_material_v2(missing_projection)

    malformed_projection = _support_state(ledger, initialized)
    malformed_projection_reader = _ReaderProxy(ledger.store)
    malformed_projection_reader.state_hook = lambda *_args: {"invalid": True}
    object.__setattr__(
        malformed_projection,
        "_reader",
        malformed_projection_reader,
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _current_support_source_material_v2(malformed_projection)

    other_request, _ = _initialize(
        ledger,
        label="state-handle-other-request",
    )
    current_head = ledger.store.load_head_v2(
        initialized.scope_ref,
        initialized.stream_ref,
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _validate_current_projection(
            ledger.store,
            ledger.domain,
            other_request,
            current_head,
        )

    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _current_support_source_material_v2(object())
    incomplete = object.__new__(VerifiedSupportStateV2)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _state_handle_fields(incomplete)
    malformed = object.__new__(VerifiedSupportStateV2)
    object.__setattr__(malformed, "_reader", ledger.store)
    object.__setattr__(malformed, "_domain", ledger.domain)
    object.__setattr__(malformed, "_request", object())
    object.__setattr__(malformed, "_anchor", anchor)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _state_handle_fields(malformed)
    incomplete_view = object.__new__(VerifiedSupportStateV2)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        require_current_support_state_v2(incomplete_view)
    malformed_view = object.__new__(VerifiedSupportStateV2)
    object.__setattr__(malformed_view, "_reader", ledger.store)
    object.__setattr__(malformed_view, "_domain", ledger.domain)
    object.__setattr__(malformed_view, "_request", object())
    object.__setattr__(malformed_view, "_anchor", anchor)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        require_current_support_state_v2(malformed_view)

    with pytest.raises(TypeError):
        _make_verified_state(
            state_reader=ledger.store,
            domain=ledger.domain,
            request=initialized,
            view=cast(GovernanceCommitViewV2, object()),
        )
    with pytest.raises(TypeError):
        _require_support_domain(object())
    with pytest.raises(TypeError):
        _require_state_reader(object())
    _require_state_reader(_ReaderProxy(ledger.store))

    membership_snapshot, membership_precondition, verification_precondition = (
        _membership_parent_authority_material_v2(upstream.membership_state)
    )
    assert membership_snapshot == upstream.membership_request.snapshot
    assert membership_precondition.expected_revision == 1
    assert verification_precondition.expected_revision == 1
    with pytest.raises(TypeError):
        _membership_parent_authority_material_v2(object())

    missing_membership_heads = rehydrate_membership_state_v2(
        upstream.membership_request.to_dict(),
        domain=ledger.domain,
        state_reader=ledger.store,
    )
    missing_membership_reader = _ReaderProxy(ledger.store)
    missing_membership_reader.head_error = KeyError("hidden")
    object.__setattr__(
        missing_membership_heads,
        "_reader",
        missing_membership_reader,
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _membership_parent_authority_material_v2(missing_membership_heads)

    incomplete_membership = object.__new__(VerifiedMembershipStateV2)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _membership_handle_fields(incomplete_membership)
    malformed_membership = object.__new__(VerifiedMembershipStateV2)
    object.__setattr__(malformed_membership, "_reader", ledger.store)
    object.__setattr__(malformed_membership, "_domain", object())
    object.__setattr__(malformed_membership, "_request", object())
    object.__setattr__(malformed_membership, "_receipt_root", "")
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _membership_handle_fields(malformed_membership)
    invalid_membership_reader = object.__new__(VerifiedMembershipStateV2)
    object.__setattr__(invalid_membership_reader, "_reader", object())
    object.__setattr__(invalid_membership_reader, "_domain", ledger.domain)
    object.__setattr__(
        invalid_membership_reader,
        "_request",
        upstream.membership_request,
    )
    object.__setattr__(
        invalid_membership_reader,
        "_receipt_root",
        upstream.membership_state.receipt_root,
    )
    with pytest.raises(TypeError):
        _membership_handle_fields(invalid_membership_reader)

    membership_head = ledger.store.load_head_v2(
        upstream.membership_request.scope_ref,
        upstream.membership_request.stream_ref,
    )
    verification_head = ledger.store.load_head_v2(
        upstream.membership_request.scope_ref,
        upstream.membership_request.snapshot.verification_stream_ref,
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _validate_membership_heads(
            upstream.membership_request,
            ledger.domain,
            object(),
            object(),
        )
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _validate_membership_heads(
            upstream.membership_request,
            ledger.domain,
            membership_head,
            GovernanceHeadV2.genesis(
                foreign.domain,
                upstream.membership_request.snapshot.verification_stream_ref,
            ),
        )
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _validate_membership_heads(
            upstream.membership_request,
            ledger.domain,
            GovernanceHeadV2.genesis(
                ledger.domain,
                upstream.membership_request.stream_ref,
            ),
            GovernanceHeadV2.genesis(
                ledger.domain,
                upstream.membership_request.snapshot.verification_stream_ref,
            ),
        )
    _validate_membership_heads(
        upstream.membership_request,
        ledger.domain,
        membership_head,
        verification_head,
    )

    missing_membership_state = _ReaderProxy(ledger.store)
    missing_membership_state.state_error = KeyError("hidden")
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _validate_membership_projection(
            missing_membership_state,
            ledger.domain,
            upstream.membership_request,
            membership_head,
        )
    malformed_membership_state = _ReaderProxy(ledger.store)
    malformed_membership_state.state_hook = lambda *_args: {"invalid": True}
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _validate_membership_projection(
            malformed_membership_state,
            ledger.domain,
            upstream.membership_request,
            membership_head,
        )
    other_membership_request, _ = _prepare_membership(
        ledger,
        upstream.verification_state,
        label="state-handle-other-membership",
        epoch=1,
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _validate_membership_projection(
            ledger.store,
            ledger.domain,
            other_membership_request,
            membership_head,
        )


def test_public_support_v2_lease_projection_rejects_every_cross_binding() -> None:
    ledger = _ledger("lease-projection-totality")
    upstream = _upstream(ledger)
    initialized, initialized_source = _initialize(
        ledger,
        label="lease-projection-totality",
    )
    _assert_committed(_advance_support(ledger, initialized, initialized_source))
    initialized_state = _support_state(ledger, initialized)
    membership = upstream.membership_state.snapshot
    claim_root = _root("claim:lease-projection-totality")
    observation = _observation(
        ledger,
        membership,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="lease-projection-totality",
        current_step=5,
    )
    proposal = _proposal(
        ledger,
        membership,
        observation,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="lease-projection-totality",
        current_step=5,
    )
    lease = project_support_lease_v2(
        parent=initialized.snapshot,
        membership=membership,
        proposal=proposal,
        positive_observations=(observation,),
        manifest=ledger.manifest,
        mutation_transition_id="transition:lease-projection-totality",
        issuance_issuer_ref=ISSUER_REF,
        current_step=5,
        prior_lease=None,
        issuance_provenance_root=_root("lease-projection:provenance"),
        issuance_trace_roots=(_root("lease-projection:trace"),),
    )
    assert lease.candidate_ref == proposal.candidate_ref

    with pytest.raises(ValueError):
        _validated_support_manifest_context_v2(
            ledger.manifest,
            profile=PROFILE,
            target_ref="target:not-declared",
        )
    with pytest.raises(ValueError):
        _validated_support_manifest_context_v2(
            replace(ledger.manifest, collective_commit_policy=None),
            profile=PROFILE,
            target_ref=TARGET,
        )
    policy = ledger.manifest.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    with pytest.raises(ValueError):
        _validated_support_manifest_context_v2(
            replace(
                ledger.manifest,
                collective_commit_policy=replace(
                    policy,
                    target="target:not-policy-owned",
                ),
            ),
            profile=PROFILE,
            target_ref=TARGET,
        )
    with pytest.raises(ValueError):
        _validated_support_manifest_context_v2(
            replace(
                ledger.manifest,
                collective_commit_policy=replace(
                    policy,
                    assurance="unsupported",
                ),
            ),
            profile=PROFILE,
            target_ref=TARGET,
        )
    with pytest.raises(ValueError):
        _validated_support_manifest_context_v2(
            ledger.manifest,
            profile="pheroos-certified-commit-v1",
            target_ref=TARGET,
        )
    invalid_lease_policy = replace(
        policy.support_lease,
        minimum_support_clusters=0,
    )
    with pytest.raises(ValueError):
        _validated_support_manifest_context_v2(
            replace(
                ledger.manifest,
                collective_commit_policy=replace(
                    policy,
                    support_lease=invalid_lease_policy,
                ),
            ),
            profile=PROFILE,
            target_ref=TARGET,
        )

    cross_parent = SupportSnapshotV2.from_dict(initialized.snapshot.to_dict())
    object.__setattr__(
        cross_parent,
        "manifest_root",
        _root("wrong:parent-manifest"),
    )
    with pytest.raises(ValueError):
        _validated_child_manifest_v2(ledger.manifest, cross_parent)
    context = _validated_support_manifest_context_v2(
        ledger.manifest,
        profile=PROFILE,
        target_ref=TARGET,
    )
    with pytest.raises(TypeError):
        _validate_request_manifest_context_v2(object(), context)
    cross_request = SupportAdvanceRequestV2.from_dict(initialized.to_dict())
    object.__setattr__(
        cross_request.snapshot,
        "manifest_root",
        _root("wrong:request-manifest"),
    )
    with pytest.raises(ValueError):
        _validate_request_manifest_context_v2(cross_request, context)

    common_projection: dict[str, Any] = {
        "parent": initialized.snapshot,
        "membership": membership,
        "positive_observations": (observation,),
        "manifest": ledger.manifest,
        "mutation_transition_id": "transition:lease-projection-invalid",
        "issuance_issuer_ref": ISSUER_REF,
        "current_step": 5,
        "prior_lease": None,
        "issuance_provenance_root": _root("lease-projection:invalid:provenance"),
        "issuance_trace_roots": (_root("lease-projection:invalid:trace"),),
    }
    with pytest.raises(TypeError):
        project_support_lease_v2(
            proposal=cast(SupportLeaseProposalV2, object()),
            **common_projection,
        )
    future_proposal = replace(
        proposal,
        proposed_at_step=6,
        proposal_root="",
    )
    with pytest.raises(ValueError):
        project_support_lease_v2(
            proposal=future_proposal,
            **common_projection,
        )

    short_membership = MembershipSnapshotV2.from_dict(membership.to_dict())
    object.__setattr__(short_membership, "expires_at_step", 10)
    with pytest.raises(ValueError):
        project_support_lease_v2(
            proposal=proposal,
            **{**common_projection, "membership": short_membership},
        )
    short_observation = replace(
        observation,
        expires_at_step=10,
        observation_root="",
    )
    short_proposal = replace(
        proposal,
        positive_observation_roots=(short_observation.observation_root,),
        proposal_root="",
    )
    with pytest.raises(ValueError):
        project_support_lease_v2(
            proposal=short_proposal,
            **{
                **common_projection,
                "positive_observations": (short_observation,),
            },
        )

    absent_root = _root("lease:absent")
    with pytest.raises(ValueError):
        active_support_lease_from_parent_v2(
            initialized.snapshot,
            absent_root,
            current_step=5,
        )
    issued, issued_source = _prepare_issue(
        ledger,
        initialized_state,
        upstream.membership_state,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="lease-projection-totality:issued",
        current_step=5,
    )
    _assert_committed(_advance_support(ledger, issued, issued_source))
    assert issued.issued_lease is not None
    with pytest.raises(ValueError):
        active_support_lease_from_parent_v2(
            issued.snapshot,
            issued.issued_lease.lease_root,
            current_step=issued.issued_lease.expires_at_step,
        )

    policy_mismatch = SupportLeaseProposalV2.from_dict(proposal.to_dict())
    object.__setattr__(
        policy_mismatch,
        "assurance",
        CommitAssurance.CERTIFIED,
    )
    with pytest.raises(ValueError):
        _validate_policy(policy_mismatch, context)
    root_mismatch = SupportLeaseProposalV2.from_dict(proposal.to_dict())
    object.__setattr__(
        root_mismatch,
        "manifest_root",
        _root("wrong:proposal-manifest"),
    )
    with pytest.raises(ValueError):
        _validate_policy(root_mismatch, context)
    cross_proposal = SupportLeaseProposalV2.from_dict(proposal.to_dict())
    object.__setattr__(cross_proposal, "run_ref", "run:wrong")
    with pytest.raises(ValueError):
        _validate_parent_proposal(initialized.snapshot, cross_proposal)
    cross_membership = MembershipSnapshotV2.from_dict(membership.to_dict())
    object.__setattr__(cross_membership, "run_ref", "run:wrong")
    with pytest.raises(ValueError):
        _validate_membership(proposal, cross_membership, current_step=5)
    with pytest.raises(ValueError):
        _validate_membership(
            proposal,
            membership,
            current_step=membership.expires_at_step,
        )
    missing_principal = SupportLeaseProposalV2.from_dict(proposal.to_dict())
    object.__setattr__(
        missing_principal,
        "principal_ref",
        "principal:not-a-member",
    )
    with pytest.raises(ValueError):
        _membership_principal(missing_principal, membership)

    with pytest.raises(TypeError):
        _validate_observations(proposal, (), current_step=5)
    with pytest.raises(ValueError):
        _validate_observations(
            proposal,
            (observation,) * 1025,
            current_step=5,
        )
    with pytest.raises(TypeError):
        _validate_observations(
            proposal,
            cast(tuple[SupportObservationV2, ...], (object(),)),
            current_step=5,
        )
    other_observation = _observation(
        ledger,
        membership,
        candidate_ref="candidate:support-v2:safe",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="lease-projection-totality:other",
        current_step=5,
    )
    with pytest.raises(ValueError):
        _validate_observations(
            proposal,
            (other_observation,),
            current_step=5,
        )
    future_observation = _observation(
        ledger,
        membership,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="lease-projection-totality:future",
        current_step=6,
    )
    future_observation_proposal = _proposal(
        ledger,
        membership,
        future_observation,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="lease-projection-totality:future",
        current_step=6,
    )
    with pytest.raises(ValueError):
        _validate_observations(
            future_observation_proposal,
            (future_observation,),
            current_step=5,
        )

    membership_principal = membership.clusters[0].principals[0]
    with pytest.raises(ValueError):
        _validate_switch_prior(
            issued.issued_lease,
            proposal,
            issued.issued_lease.principal_cluster_ref,
            membership_principal,
            membership,
        )


def test_public_support_v2_operations_fail_before_any_unbound_write() -> None:
    ledger = _ledger("support-operation-totality")
    initialized, initialized_source = _initialize(
        ledger,
        label="support-operation-totality",
    )
    capability = _capability(ledger, initialized.observed_epoch)
    with pytest.raises(TypeError):
        open_support_authority_session_v2(
            cast(GovernanceIssuerCapabilityV2, object()),
            initialized,
        )
    wrong_issuer, _ = _initialize(
        ledger,
        label="support-operation-totality:wrong-issuer",
        issuer_ref="issuer:not-authorized",
    )
    with pytest.raises(ValueError):
        open_support_authority_session_v2(capability, wrong_issuer)
    with pytest.raises(TypeError):
        advance_support_state_v2(cast(SupportAdvanceRequestV2, object()))

    session = open_support_authority_session_v2(capability, initialized)
    malformed_source = object.__new__(VerifiedSupportSourceV2)
    malformed_attempt = advance_support_state_v2(
        initialized,
        source=malformed_source,
        authority_session=session,
    )
    assert malformed_attempt.disposition is GovernanceCommitDispositionV2.INVALID

    other_request, other_source = _initialize(
        ledger,
        label="support-operation-totality:other-session",
    )
    mismatched_session = advance_support_state_v2(
        other_request,
        source=other_source,
        authority_session=session,
    )
    assert mismatched_session.disposition is GovernanceCommitDispositionV2.INVALID
    assert _validated_session_or_failure(session, other_request)[0] is None
    session_state = _governance_authority_session_state_v2(session)
    assert not _committed_view_matches_request(
        cast(GovernanceCommitViewV2, object()),
        initialized,
        session_state,
    )

    parent = GovernanceReadPreconditionV2(
        stream_ref=initialized.stream_ref,
        expected_revision=0,
        expected_root=GovernanceHeadV2.genesis(
            ledger.domain,
            initialized.stream_ref,
        ).head_root,
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _resolve_write_head(
            ledger.store,
            ledger.domain,
            initialized,
            parent_precondition=parent,
        )
    write_head, invalid_membership = _write_head_or_failure(
        session_state,
        initialized,
        ledger.store,
        ledger.domain,
        parent_precondition=None,
        membership_precondition=cast(GovernanceReadPreconditionV2, object()),
    )
    assert write_head is None
    assert invalid_membership is not None
    _, resolved_error = _write_head_or_failure(
        session_state,
        initialized,
        ledger.store,
        ledger.domain,
        parent_precondition=parent,
        membership_precondition=None,
    )
    assert resolved_error is not None
    binding_error = GovernanceAuthorityBindingErrorV2(
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/source/parent",
    )
    assert (
        _source_failure_from_error(
            session_state,
            initialized,
            binding_error,
        ).failure
        is not None
    )

    _assert_committed(
        advance_support_state_v2(
            initialized,
            source=initialized_source,
            authority_session=session,
        )
    )
    state = rehydrate_support_state_v2(
        initialized,
        domain=ledger.domain,
        state_reader=ledger.store,
    )
    assert state.snapshot == initialized.snapshot
    foreign = _ledger("support-operation-foreign-scope")
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        rehydrate_support_state_v2(
            initialized.to_dict(),
            domain=foreign.domain,
            state_reader=foreign.store,
        )
    with pytest.raises(TypeError):
        rehydrate_support_state_v2(
            initialized.to_dict(),
            domain=cast(AuthorityDomainV2, object()),
            state_reader=ledger.store,
        )
    with pytest.raises(TypeError):
        rehydrate_support_state_v2(
            initialized.to_dict(),
            domain=ledger.domain,
            state_reader=cast(GovernanceStateStoreV2, object()),
        )

    upstream = _upstream(ledger)
    claim_root = _root("claim:support-operation-totality")
    issue, issue_source = _prepare_issue(
        ledger,
        state,
        upstream.membership_state,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="support-operation-totality:issue",
        current_step=5,
    )
    issue_material = _verified_support_source(issue_source)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _resolve_write_head(
            ledger.store,
            ledger.domain,
            issue,
            parent_precondition=None,
        )
    wrong_head_reader = _ReaderProxy(ledger.store)
    wrong_head_reader.head_hook = lambda *_args: object()
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _resolve_write_head(
            cast(GovernanceStateStoreV2, wrong_head_reader),
            ledger.domain,
            issue,
            parent_precondition=issue_material.parent_precondition,
        )
    stale_head_reader = _ReaderProxy(ledger.store)
    stale_head_reader.head_hook = (
        lambda _scope, stream, _head: GovernanceHeadV2.genesis(
            ledger.domain,
            stream,
        )
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _resolve_write_head(
            cast(GovernanceStateStoreV2, stale_head_reader),
            ledger.domain,
            issue,
            parent_precondition=issue_material.parent_precondition,
        )
    key_error_reader = _ReaderProxy(ledger.store)
    key_error_reader.head_error = KeyError("hidden")
    _, key_error_attempt = _write_head_or_failure(
        session_state,
        issue,
        cast(GovernanceStateStoreV2, key_error_reader),
        ledger.domain,
        parent_precondition=issue_material.parent_precondition,
        membership_precondition=issue_material.membership_precondition,
    )
    assert key_error_attempt is not None

    revoked_ledger = _ledger("support-operation-revoked-grant")
    revoked_request, revoked_source = _initialize(
        revoked_ledger,
        label="revoked-grant",
    )
    revoked_session = open_support_authority_session_v2(
        _capability(revoked_ledger, revoked_request.observed_epoch),
        revoked_request,
    )
    _assert_committed(
        revoke_governance_issuer_grant_v2(
            revoked_ledger.store,
            revoked_ledger.domain,
            revoked_ledger.grant.grant_ref,
            "transition:revoke:support-operation-grant",
            revoked_request.observed_epoch,
        )
    )
    revoked_attempt = advance_support_state_v2(
        revoked_request,
        source=revoked_source,
        authority_session=revoked_session,
    )
    assert revoked_attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED


def test_public_support_v2_upstream_contracts_reject_noncanonical_lineage() -> None:
    ledger = _ledger("upstream-contract-totality")
    verification_request, _ = _prepare_verification(
        ledger,
        label="upstream-contract-totality",
        epoch=1,
    )
    verification = verification_request.snapshot
    assert verification.root() == verification.snapshot_root
    assert verification_request.root() == verification_request.request_root
    assert json.loads(verification.canonical_bytes()) == verification.to_dict()
    assert json.loads(verification_request.canonical_bytes()) == (
        verification_request.to_dict()
    )
    with pytest.raises(TypeError):
        principal_verification_stream_ref_v2(
            verification.scope_ref,
            verification.profile,
            cast(CommitAssurance, "evidence_bound"),
            verification.manifest_root,
            verification.commit_policy_root,
            verification.verification_policy_root,
            verification.protocol_ref,
            verification.run_ref,
            verification.target_ref,
        )
    with pytest.raises(ValueError):
        replace(verification, record_count=verification.record_count + 1)
    future_record = replace(
        verification.records[0],
        issued_at_step=verification.current_step + 1,
        verification_root="",
    )
    with pytest.raises(ValueError):
        replace(
            verification,
            records=(future_record, *verification.records[1:]),
            verification_set_root="",
            snapshot_root="",
        )
    with pytest.raises(ValueError):
        replace(
            verification,
            verification_set_root=_root("wrong:verification-set"),
        )
    with pytest.raises(ValueError):
        replace(
            verification,
            snapshot_root=_root("wrong:verification-snapshot"),
        )
    malformed_verification = verification.to_dict()
    malformed_verification["assurance"] = "unsupported"
    with pytest.raises(ValueError):
        PrincipalVerificationSetSnapshotV2.from_dict(malformed_verification)

    with pytest.raises(ValueError):
        replace(verification_request, schema="unsupported")
    with pytest.raises(ValueError):
        replace(verification_request, canonical_version="unsupported")
    with pytest.raises(TypeError):
        replace(verification_request, snapshot=cast(Any, object()))
    with pytest.raises(ValueError):
        replace(verification_request, run_ref="run:cross-bound")
    with pytest.raises(ValueError):
        replace(
            verification_request,
            request_root=_root("wrong:verification-request"),
        )

    wrong_verification_version = PrincipalVerificationSetSnapshotV2.from_dict(
        verification.to_dict()
    )
    object.__setattr__(
        wrong_verification_version,
        "schema",
        "unsupported",
    )
    with pytest.raises(ValueError):
        _validate_verification_snapshot_versions(wrong_verification_version)
    wrong_verification_assurance = PrincipalVerificationSetSnapshotV2.from_dict(
        verification.to_dict()
    )
    object.__setattr__(
        wrong_verification_assurance,
        "assurance",
        "evidence_bound",
    )
    with pytest.raises(TypeError):
        _validate_verification_snapshot_counts(wrong_verification_assurance)
    wrong_verification_profile = PrincipalVerificationSetSnapshotV2.from_dict(
        verification.to_dict()
    )
    object.__setattr__(
        wrong_verification_profile,
        "profile",
        "pheroos-certified-commit-v1",
    )
    with pytest.raises(ValueError):
        _validate_verification_snapshot_counts(wrong_verification_profile)
    expired_verification = PrincipalVerificationSetSnapshotV2.from_dict(
        verification.to_dict()
    )
    object.__setattr__(
        expired_verification,
        "expires_at_step",
        verification.current_step,
    )
    with pytest.raises(ValueError):
        _validate_verification_snapshot_counts(expired_verification)
    wrong_verification_stream = PrincipalVerificationSetSnapshotV2.from_dict(
        verification.to_dict()
    )
    object.__setattr__(
        wrong_verification_stream,
        "stream_ref",
        "authority:principal-verification-v2:wrong",
    )
    with pytest.raises(ValueError):
        _validate_verification_snapshot_identity(wrong_verification_stream)
    wrong_verification_genesis = PrincipalVerificationSetSnapshotV2.from_dict(
        verification.to_dict()
    )
    object.__setattr__(wrong_verification_genesis, "revision", 2)
    with pytest.raises(ValueError):
        _validate_verification_snapshot_identity(wrong_verification_genesis)
    verification_successor, _ = _prepare_verification(
        ledger,
        label="upstream-contract-totality:successor",
        epoch=2,
        parent=verification,
    )
    wrong_verification_successor = PrincipalVerificationSetSnapshotV2.from_dict(
        verification_successor.snapshot.to_dict()
    )
    object.__setattr__(
        wrong_verification_successor,
        "parent_transition_id",
        "genesis",
    )
    with pytest.raises(ValueError):
        _validate_verification_snapshot_identity(wrong_verification_successor)

    _, verification_state = _commit_verification(
        ledger,
        label="upstream-contract-totality",
        epoch=1,
    )
    membership_request, _ = _prepare_membership(
        ledger,
        verification_state,
        label="upstream-contract-totality",
        epoch=1,
    )
    membership = membership_request.snapshot
    assert membership.root() == membership.snapshot_root
    assert membership_request.root() == membership_request.request_root
    assert json.loads(membership.canonical_bytes()) == membership.to_dict()
    assert json.loads(membership_request.canonical_bytes()) == (
        membership_request.to_dict()
    )
    with pytest.raises(ValueError):
        replace(membership, cluster_count=membership.cluster_count + 1)
    with pytest.raises(ValueError):
        replace(
            membership,
            membership_root=_root("wrong:membership-root"),
        )
    with pytest.raises(ValueError):
        replace(
            membership,
            snapshot_root=_root("wrong:membership-snapshot"),
        )
    malformed_membership = membership.to_dict()
    malformed_membership["assurance"] = "unsupported"
    with pytest.raises(ValueError):
        MembershipSnapshotV2.from_dict(malformed_membership)

    with pytest.raises(ValueError):
        replace(membership_request, schema="unsupported")
    with pytest.raises(ValueError):
        replace(membership_request, canonical_version="unsupported")
    with pytest.raises(TypeError):
        replace(membership_request, snapshot=cast(Any, object()))
    with pytest.raises(ValueError):
        replace(membership_request, run_ref="run:cross-bound")
    with pytest.raises(ValueError):
        replace(
            membership_request,
            request_root=_root("wrong:membership-request"),
        )

    wrong_membership_version = MembershipSnapshotV2.from_dict(membership.to_dict())
    object.__setattr__(wrong_membership_version, "schema", "unsupported")
    with pytest.raises(ValueError):
        _validate_membership_snapshot_versions(wrong_membership_version)
    wrong_membership_assurance = MembershipSnapshotV2.from_dict(membership.to_dict())
    object.__setattr__(
        wrong_membership_assurance,
        "assurance",
        "evidence_bound",
    )
    with pytest.raises(TypeError):
        _validate_snapshot_traces_and_counts(wrong_membership_assurance)
    wrong_membership_profile = MembershipSnapshotV2.from_dict(membership.to_dict())
    object.__setattr__(
        wrong_membership_profile,
        "profile",
        "pheroos-certified-commit-v1",
    )
    with pytest.raises(ValueError):
        _validate_snapshot_traces_and_counts(wrong_membership_profile)
    with pytest.raises(TypeError):
        _validated_membership_trace_roots("not-an-array")
    with pytest.raises(ValueError):
        _validated_membership_trace_roots(())
    with pytest.raises(ValueError):
        _validated_membership_trace_roots((membership.source_trace_roots[0],) * 2)
    expired_membership = MembershipSnapshotV2.from_dict(membership.to_dict())
    object.__setattr__(
        expired_membership,
        "expires_at_step",
        membership.issued_at_step,
    )
    with pytest.raises(ValueError):
        _validate_membership_snapshot_timeline(expired_membership)
    zero_verification_revision = MembershipSnapshotV2.from_dict(membership.to_dict())
    object.__setattr__(
        zero_verification_revision,
        "verification_revision",
        0,
    )
    with pytest.raises(ValueError):
        _validate_membership_snapshot_timeline(zero_verification_revision)
    cross_bound_verification_timeline = MembershipSnapshotV2.from_dict(
        membership.to_dict()
    )
    object.__setattr__(
        cross_bound_verification_timeline,
        "verification_record_count",
        membership.verification_record_count + 1,
    )
    with pytest.raises(ValueError):
        _validate_membership_snapshot_timeline(cross_bound_verification_timeline)
    wrong_membership_stream = MembershipSnapshotV2.from_dict(membership.to_dict())
    object.__setattr__(
        wrong_membership_stream,
        "stream_ref",
        "authority:membership-v2:wrong",
    )
    with pytest.raises(ValueError):
        _validate_membership_snapshot_identity(wrong_membership_stream)
    wrong_membership_verification_stream = MembershipSnapshotV2.from_dict(
        membership.to_dict()
    )
    object.__setattr__(
        wrong_membership_verification_stream,
        "verification_stream_ref",
        "authority:principal-verification-v2:wrong",
    )
    with pytest.raises(ValueError):
        _validate_membership_snapshot_identity(wrong_membership_verification_stream)
    wrong_membership_genesis = MembershipSnapshotV2.from_dict(membership.to_dict())
    object.__setattr__(wrong_membership_genesis, "revision", 2)
    with pytest.raises(ValueError):
        _validate_membership_snapshot_identity(wrong_membership_genesis)

    membership_successor_ledger = _ledger("membership-contract-successor")
    first_upstream = _upstream(membership_successor_ledger)
    second_verification_request, second_verification_state = _commit_verification(
        membership_successor_ledger,
        label="membership-contract-successor",
        epoch=2,
        parent=first_upstream.verification_request.snapshot,
    )
    membership_successor, _ = _prepare_membership(
        membership_successor_ledger,
        second_verification_state,
        label="membership-contract-successor",
        epoch=2,
        parent=first_upstream.membership_request.snapshot,
    )
    assert membership_successor.snapshot.verification_snapshot_root == (
        second_verification_request.snapshot.snapshot_root
    )
    wrong_membership_successor = MembershipSnapshotV2.from_dict(
        membership_successor.snapshot.to_dict()
    )
    object.__setattr__(
        wrong_membership_successor,
        "parent_transition_id",
        "genesis",
    )
    with pytest.raises(ValueError):
        _validate_membership_snapshot_identity(wrong_membership_successor)

    cluster = membership.clusters[0]
    with pytest.raises(ValueError):
        canonical_membership_clusters_v2((cluster,) * 1025)
    with pytest.raises(TypeError):
        membership_stream_ref_v2(
            membership.scope_ref,
            membership.profile,
            cast(CommitAssurance, "evidence_bound"),
            membership.manifest_root,
            membership.commit_policy_root,
            membership.membership_policy_root,
            membership.protocol_ref,
            membership.run_ref,
            membership.target_ref,
        )
    with pytest.raises(ValueError):
        _prepare_verification(
            _ledger("verification-source-expiry"),
            label="expiry",
            epoch=1,
            current_step=100,
        )
    with pytest.raises(ValueError):
        _prepare_membership(
            ledger,
            verification_state,
            label="membership-source-expiry",
            epoch=1,
            current_step=90,
            expires_at_step=90,
        )


def test_public_support_v2_upstream_operations_totalize_bad_parent_views() -> None:
    verification_ledger = _ledger("verification-parent-view-totality")
    verification_request, verification_source = _prepare_verification(
        verification_ledger,
        label="parent-view",
        epoch=1,
    )
    verification_session = open_principal_verification_authority_session_v2(
        _capability(
            verification_ledger,
            verification_request.observed_epoch,
        ),
        verification_request,
    )
    other_verification, _ = _prepare_verification(
        verification_ledger,
        label="parent-view:other",
        epoch=1,
    )
    assert (
        _validated_verification_session(
            verification_session,
            other_verification,
        )[0]
        is None
    )
    verification_session_state = _governance_authority_session_state_v2(
        verification_session
    )
    missing_verification_view = verification_ledger.store.load_commit_view_v2(
        verification_request.scope_ref,
        verification_request.stream_ref,
        "transition:missing-verification",
    )
    assert not _verification_committed_view_matches(
        missing_verification_view,
        verification_request,
        verification_session_state,
    )
    with pytest.raises(ValueError):
        _verification_head_from_view(
            missing_verification_view,
            verification_ledger.domain,
        )
    verification_successor, _ = _prepare_verification(
        verification_ledger,
        label="parent-view:successor",
        epoch=2,
        parent=verification_request.snapshot,
    )
    hidden_verification_parent = _ReaderProxy(verification_ledger.store)
    hidden_verification_parent.view_error = KeyError("hidden")
    assert isinstance(
        _load_verification_parent(
            hidden_verification_parent,
            verification_ledger.domain,
            verification_successor,
        ),
        GovernanceCommitAttemptV2,
    )
    invalid_verification_parent = _ReaderProxy(verification_ledger.store)
    invalid_verification_parent.view_error = GovernanceAuthorityBindingErrorV2(
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
        "/transition_id",
    )
    assert isinstance(
        _load_verification_parent(
            invalid_verification_parent,
            verification_ledger.domain,
            verification_successor,
        ),
        GovernanceCommitAttemptV2,
    )

    revoked_verification_ledger = _ledger("verification-revoked-grant")
    revoked_verification, revoked_verification_source = _prepare_verification(
        revoked_verification_ledger,
        label="revoked-grant",
        epoch=1,
    )
    revoked_verification_session = open_principal_verification_authority_session_v2(
        _capability(
            revoked_verification_ledger,
            revoked_verification.observed_epoch,
        ),
        revoked_verification,
    )
    _assert_committed(
        revoke_governance_issuer_grant_v2(
            revoked_verification_ledger.store,
            revoked_verification_ledger.domain,
            revoked_verification_ledger.grant.grant_ref,
            "transition:revoke:verification-operation-grant",
            revoked_verification.observed_epoch,
        )
    )
    assert (
        advance_principal_verification_set_v2(
            revoked_verification,
            source=revoked_verification_source,
            authority_session=revoked_verification_session,
        ).disposition
        is not GovernanceCommitDispositionV2.COMMITTED
    )

    membership_ledger = _ledger("membership-parent-view-totality")
    _, verification_state = _commit_verification(
        membership_ledger,
        label="membership-parent-view",
        epoch=1,
    )
    membership_request, membership_source = _prepare_membership(
        membership_ledger,
        verification_state,
        label="parent-view",
        epoch=1,
    )
    membership_session = open_membership_authority_session_v2(
        _capability(membership_ledger, membership_request.observed_epoch),
        membership_request,
    )
    other_membership, _ = _prepare_membership(
        membership_ledger,
        verification_state,
        label="parent-view:other",
        epoch=1,
    )
    assert (
        _validated_membership_session(
            membership_session,
            other_membership,
        )[0]
        is None
    )
    membership_session_state = _governance_authority_session_state_v2(
        membership_session
    )
    missing_membership_view = membership_ledger.store.load_commit_view_v2(
        membership_request.scope_ref,
        membership_request.stream_ref,
        "transition:missing-membership",
    )
    assert not _membership_committed_view_matches(
        missing_membership_view,
        membership_request,
        membership_session_state,
    )
    with pytest.raises(ValueError):
        _membership_head_from_view(
            missing_membership_view,
            membership_ledger.domain,
        )
    membership_successor = replace(
        membership_request,
        snapshot=membership_request.snapshot,
    )
    object.__setattr__(membership_successor.snapshot, "parent_revision", 1)
    hidden_membership_parent = _ReaderProxy(membership_ledger.store)
    hidden_membership_parent.view_error = KeyError("hidden")
    assert isinstance(
        _load_membership_parent(
            hidden_membership_parent,
            membership_ledger.domain,
            membership_successor,
        ),
        GovernanceCommitAttemptV2,
    )
    invalid_membership_parent = _ReaderProxy(membership_ledger.store)
    invalid_membership_parent.view_error = GovernanceAuthorityBindingErrorV2(
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
        "/transition_id",
    )
    assert isinstance(
        _load_membership_parent(
            invalid_membership_parent,
            membership_ledger.domain,
            membership_successor,
        ),
        GovernanceCommitAttemptV2,
    )

    revoked_membership_ledger = _ledger("membership-revoked-grant")
    _, revoked_membership_verification = _commit_verification(
        revoked_membership_ledger,
        label="revoked-membership-grant",
        epoch=1,
    )
    revoked_membership, revoked_membership_source = _prepare_membership(
        revoked_membership_ledger,
        revoked_membership_verification,
        label="revoked-grant",
        epoch=1,
    )
    revoked_membership_session = open_membership_authority_session_v2(
        _capability(
            revoked_membership_ledger,
            revoked_membership.observed_epoch,
        ),
        revoked_membership,
    )
    _assert_committed(
        revoke_governance_issuer_grant_v2(
            revoked_membership_ledger.store,
            revoked_membership_ledger.domain,
            revoked_membership_ledger.grant.grant_ref,
            "transition:revoke:membership-operation-grant",
            revoked_membership.observed_epoch,
        )
    )
    assert (
        commit_membership_epoch_v2(
            revoked_membership,
            source=revoked_membership_source,
            authority_session=revoked_membership_session,
        ).disposition
        is not GovernanceCommitDispositionV2.COMMITTED
    )


def test_public_support_v2_upstream_committed_state_is_fail_closed() -> None:
    ledger = _ledger("upstream-committed-state-totality")
    verification_request, verification_state = _commit_verification(
        ledger,
        label="committed-state",
        epoch=1,
    )
    verification_view = ledger.store.load_commit_view_v2(
        verification_request.scope_ref,
        verification_request.stream_ref,
        verification_request.transition_id,
    )
    assert verification_view.committed_transition is not None
    verification_transition = verification_view.committed_transition.batch.transition
    assert verification_transition is not None
    verification_records = dict(verification_transition.state_records)
    decoded_verification, verification_binding = _decode_verification_state_records(
        verification_records,
        ledger.domain,
    )
    assert decoded_verification == verification_request
    assert (
        _validate_verification_session_binding(
            verification_binding,
            verification_request,
        )
        == verification_binding
    )

    with pytest.raises(ValueError, match="fields"):
        _decode_verification_state_records({}, ledger.domain)
    wrong_verification_domain = dict(verification_records)
    wrong_verification_domain["domain_root"] = _root("wrong:domain")
    with pytest.raises(ValueError, match="domain"):
        _decode_verification_state_records(
            wrong_verification_domain,
            ledger.domain,
        )
    cross_bound_verification = dict(verification_records)
    cross_bound_verification["request_root"] = _root("wrong:request")
    with pytest.raises(ValueError, match="cross-bound"):
        _decode_verification_state_records(
            cross_bound_verification,
            ledger.domain,
        )
    with pytest.raises(ValueError, match="fields"):
        _validate_verification_session_binding({}, verification_request)
    wrong_verification_binding = dict(verification_binding)
    wrong_verification_binding["run_ref"] = "run:cross-bound"
    with pytest.raises(ValueError, match="mismatched"):
        _validate_verification_session_binding(
            wrong_verification_binding,
            verification_request,
        )
    empty_verification_grant = dict(verification_binding)
    empty_verification_grant["grant_root"] = ""
    with pytest.raises(ValueError, match="empty"):
        _validate_verification_session_binding(
            empty_verification_grant,
            verification_request,
        )

    _validate_verification_read_set(
        verification_view,
        verification_request,
        verification_binding,
    )
    duplicate_verification_view = ledger.store.load_commit_view_v2(
        verification_request.scope_ref,
        verification_request.stream_ref,
        verification_request.transition_id,
    )
    assert duplicate_verification_view.committed_transition is not None
    duplicate_verification_read_set = (
        duplicate_verification_view.committed_transition.batch.read_set
    )
    object.__setattr__(
        duplicate_verification_read_set,
        "entries",
        (
            *duplicate_verification_read_set.entries,
            duplicate_verification_read_set.entries[0],
        ),
    )
    with pytest.raises(ValueError, match="duplicate"):
        _validate_verification_read_set(
            duplicate_verification_view,
            verification_request,
            verification_binding,
        )
    incomplete_verification_view = ledger.store.load_commit_view_v2(
        verification_request.scope_ref,
        verification_request.stream_ref,
        verification_request.transition_id,
    )
    assert incomplete_verification_view.committed_transition is not None
    incomplete_verification_read_set = (
        incomplete_verification_view.committed_transition.batch.read_set
    )
    object.__setattr__(
        incomplete_verification_read_set,
        "entries",
        incomplete_verification_read_set.entries[:-1],
    )
    with pytest.raises(ValueError, match="mismatched"):
        _validate_verification_read_set(
            incomplete_verification_view,
            verification_request,
            verification_binding,
        )

    invalid_verification_genesis = PrincipalVerificationSetAdvanceRequestV2.from_dict(
        verification_request.to_dict()
    )
    object.__setattr__(
        invalid_verification_genesis.snapshot,
        "parent_epoch",
        1,
    )
    assert (
        _verification_continuity_failure(
            invalid_verification_genesis,
            None,
        )
        is not None
    )
    with pytest.raises(ValueError, match="genesis continuity"):
        _validate_verification_history(
            ledger.store,
            ledger.domain,
            invalid_verification_genesis,
        )

    verification_successor, _ = _prepare_verification(
        ledger,
        label="committed-state-successor",
        epoch=2,
        parent=verification_request.snapshot,
    )
    immutable_verification_successor = (
        PrincipalVerificationSetAdvanceRequestV2.from_dict(
            verification_successor.to_dict()
        )
    )
    object.__setattr__(
        immutable_verification_successor.snapshot,
        "run_ref",
        "run:cross-bound",
    )
    assert (
        _verification_continuity_failure(
            immutable_verification_successor,
            verification_request.snapshot,
        )
        is not None
    )
    discontinuous_verification_successor = (
        PrincipalVerificationSetAdvanceRequestV2.from_dict(
            verification_successor.to_dict()
        )
    )
    object.__setattr__(
        discontinuous_verification_successor.snapshot,
        "parent_snapshot_root",
        _root("wrong:parent-snapshot"),
    )
    assert (
        _verification_continuity_failure(
            discontinuous_verification_successor,
            verification_request.snapshot,
        )
        is not None
    )
    with pytest.raises(ValueError, match="historical continuity"):
        _validate_verification_history(
            ledger.store,
            ledger.domain,
            discontinuous_verification_successor,
        )

    missing_verification = _ReaderProxy(ledger.store)
    missing_verification.view_error = KeyError("missing")
    with pytest.raises(
        GovernanceAuthorityBindingErrorV2,
    ) as missing_verification_error:
        _load_verified_verification_request_view(
            missing_verification,
            ledger.domain,
            verification_request,
            expected_receipt_root=None,
        )
    assert missing_verification_error.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    cross_bound_verification_request = (
        PrincipalVerificationSetAdvanceRequestV2.from_dict(
            verification_request.to_dict()
        )
    )
    object.__setattr__(
        cross_bound_verification_request,
        "observed_epoch",
        verification_request.observed_epoch + 1,
    )
    with pytest.raises(
        GovernanceAuthorityBindingErrorV2,
    ) as cross_bound_verification_error:
        _load_verified_verification_request_view(
            ledger.store,
            ledger.domain,
            cross_bound_verification_request,
            expected_receipt_root=None,
        )
    assert cross_bound_verification_error.value.code is (
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )

    membership_request, _ = _commit_membership(
        ledger,
        verification_state,
        label="committed-state",
        epoch=1,
    )
    membership_view = ledger.store.load_commit_view_v2(
        membership_request.scope_ref,
        membership_request.stream_ref,
        membership_request.transition_id,
    )
    assert membership_view.committed_transition is not None
    membership_transition = membership_view.committed_transition.batch.transition
    assert membership_transition is not None
    membership_records = dict(membership_transition.state_records)
    decoded_membership, membership_binding = _decode_membership_state_records(
        membership_records,
        ledger.domain,
    )
    assert decoded_membership == membership_request
    assert (
        _validate_membership_session_binding(
            membership_binding,
            membership_request,
        )
        == membership_binding
    )

    with pytest.raises(ValueError, match="fields"):
        _decode_membership_state_records({}, ledger.domain)
    wrong_membership_domain = dict(membership_records)
    wrong_membership_domain["scope_ref"] = "scope:cross-bound"
    with pytest.raises(ValueError, match="domain"):
        _decode_membership_state_records(
            wrong_membership_domain,
            ledger.domain,
        )
    cross_bound_membership = dict(membership_records)
    cross_bound_membership["membership_root"] = _root("wrong:membership")
    with pytest.raises(ValueError, match="cross-bound"):
        _decode_membership_state_records(
            cross_bound_membership,
            ledger.domain,
        )
    with pytest.raises(ValueError, match="fields"):
        _validate_membership_session_binding({}, membership_request)
    wrong_membership_binding = dict(membership_binding)
    wrong_membership_binding["operation"] = (
        GovernanceIssuerOperationV2.QUALIFY_EVIDENCE.value
    )
    with pytest.raises(ValueError, match="mismatched"):
        _validate_membership_session_binding(
            wrong_membership_binding,
            membership_request,
        )

    _validate_membership_read_set(
        membership_view,
        membership_request,
        membership_binding,
    )
    duplicate_membership_view = ledger.store.load_commit_view_v2(
        membership_request.scope_ref,
        membership_request.stream_ref,
        membership_request.transition_id,
    )
    assert duplicate_membership_view.committed_transition is not None
    duplicate_membership_read_set = (
        duplicate_membership_view.committed_transition.batch.read_set
    )
    object.__setattr__(
        duplicate_membership_read_set,
        "entries",
        (
            *duplicate_membership_read_set.entries,
            duplicate_membership_read_set.entries[0],
        ),
    )
    with pytest.raises(ValueError, match="duplicate"):
        _validate_membership_read_set(
            duplicate_membership_view,
            membership_request,
            membership_binding,
        )
    incomplete_membership_view = ledger.store.load_commit_view_v2(
        membership_request.scope_ref,
        membership_request.stream_ref,
        membership_request.transition_id,
    )
    assert incomplete_membership_view.committed_transition is not None
    incomplete_membership_read_set = (
        incomplete_membership_view.committed_transition.batch.read_set
    )
    object.__setattr__(
        incomplete_membership_read_set,
        "entries",
        incomplete_membership_read_set.entries[:-1],
    )
    with pytest.raises(ValueError, match="mismatched"):
        _validate_membership_read_set(
            incomplete_membership_view,
            membership_request,
            membership_binding,
        )

    invalid_membership_genesis = MembershipCommitRequestV2.from_dict(
        membership_request.to_dict()
    )
    object.__setattr__(
        invalid_membership_genesis.snapshot,
        "parent_epoch",
        1,
    )
    assert (
        _membership_continuity_failure(
            invalid_membership_genesis,
            None,
        )
        is not None
    )
    with pytest.raises(ValueError, match="genesis continuity"):
        _validate_membership_history(
            ledger.store,
            ledger.domain,
            invalid_membership_genesis,
        )

    _, successor_verification_state = _commit_verification(
        ledger,
        label="committed-state-membership-successor",
        epoch=2,
        parent=verification_request.snapshot,
    )
    membership_successor, _ = _prepare_membership(
        ledger,
        successor_verification_state,
        label="committed-state-successor",
        epoch=2,
        parent=membership_request.snapshot,
    )
    immutable_membership_successor = MembershipCommitRequestV2.from_dict(
        membership_successor.to_dict()
    )
    object.__setattr__(
        immutable_membership_successor.snapshot,
        "run_ref",
        "run:cross-bound",
    )
    assert (
        _membership_continuity_failure(
            immutable_membership_successor,
            membership_request.snapshot,
        )
        is not None
    )
    discontinuous_membership_successor = MembershipCommitRequestV2.from_dict(
        membership_successor.to_dict()
    )
    object.__setattr__(
        discontinuous_membership_successor.snapshot,
        "parent_snapshot_root",
        _root("wrong:parent-snapshot"),
    )
    assert (
        _membership_continuity_failure(
            discontinuous_membership_successor,
            membership_request.snapshot,
        )
        is not None
    )
    with pytest.raises(ValueError, match="historical continuity"):
        _validate_membership_history(
            ledger.store,
            ledger.domain,
            discontinuous_membership_successor,
        )

    missing_verification_inclusion = _ReaderProxy(ledger.store)
    missing_verification_inclusion.view_error = KeyError("missing")
    with pytest.raises(ValueError, match="verification inclusion"):
        _validate_verification_inclusion(
            missing_verification_inclusion,
            ledger.domain,
            membership_request.snapshot,
            require_current=False,
        )
    cross_bound_membership_request = MembershipCommitRequestV2.from_dict(
        membership_request.to_dict()
    )
    object.__setattr__(
        cross_bound_membership_request,
        "observed_epoch",
        membership_request.observed_epoch + 1,
    )
    with pytest.raises(
        GovernanceAuthorityBindingErrorV2,
    ) as cross_bound_membership_error:
        _load_verified_membership_request_view(
            ledger.store,
            ledger.domain,
            cross_bound_membership_request,
            expected_receipt_root=None,
        )
    assert cross_bound_membership_error.value.code is (
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )


def test_public_support_v2_stream_and_evidence_bounds_are_total() -> None:
    ledger = _ledger("stream-evidence-totality")
    upstream = _upstream(ledger)
    membership = upstream.membership_state.snapshot
    observation = _observation(
        ledger,
        membership,
        candidate_ref="candidate:support-v2:accept",
        claim_root=_root("claim:stream-evidence-totality"),
        principal_ref="principal:alpha",
        label="stream-evidence-totality",
        current_step=5,
    )

    with pytest.raises(TypeError):
        support_stream_ref_v2(
            ledger.domain.scope_ref,
            PROFILE,
            cast(CommitAssurance, "evidence_bound"),
            ledger.manifest.manifest_root,
            membership.commit_policy_root,
            ledger.manifest.id,
            RUN_REF,
            TARGET,
        )

    delta_arguments: dict[str, Any] = {
        "transition_id": "transition:support-v2:totality",
        "mutation_issuer_ref": ISSUER_REF,
        "observed_epoch": 1,
        "current_step": 1,
        "mutation_provenance_root": _root("delta:provenance"),
        "mutation_trace_roots": (_root("delta:trace"),),
        "issued_lease_root": "",
        "revoked_lease_root": "",
        "revocation_root": "",
        "evicted_lease_roots": (),
        "membership_stream_ref": "",
        "membership_transition_id": "",
        "membership_snapshot_root": "",
    }
    assert support_mutation_delta_root_v2(
        SupportMutationKindV2.INITIALIZE,
        **delta_arguments,
    ).startswith("sha256:")
    with pytest.raises(TypeError):
        support_mutation_delta_root_v2(
            cast(SupportMutationKindV2, "initialize"),
            **delta_arguments,
        )
    for invalid_traces, expected_error in (
        ("not-an-array", TypeError),
        ((), ValueError),
        ((1,), TypeError),
        ((_root("delta:trace"),) * 2, ValueError),
    ):
        with pytest.raises(expected_error):
            support_mutation_delta_root_v2(
                SupportMutationKindV2.INITIALIZE,
                **{
                    **delta_arguments,
                    "mutation_trace_roots": invalid_traces,
                },
            )

    with pytest.raises(ValueError):
        support_mutation_delta_root_v2(
            SupportMutationKindV2.INITIALIZE,
            **{
                **delta_arguments,
                "evicted_lease_roots": tuple(
                    _root(f"evicted:{index}") for index in range(1025)
                ),
            },
        )
    with pytest.raises(TypeError):
        support_mutation_delta_root_v2(
            SupportMutationKindV2.INITIALIZE,
            **{
                **delta_arguments,
                "evicted_lease_roots": cast(tuple[str, ...], (1,)),
            },
        )
    with pytest.raises(ValueError):
        support_mutation_delta_root_v2(
            SupportMutationKindV2.INITIALIZE,
            **{
                **delta_arguments,
                "evicted_lease_roots": (_root("evicted:duplicate"),) * 2,
            },
        )

    revocation_traces = tuple(
        sorted(_root(f"switch:revoke:{index}") for index in range(1024))
    )
    issuance_traces = tuple(
        sorted(_root(f"switch:issue:{index}") for index in range(1024))
    )
    with pytest.raises(ValueError, match="aggregate bound"):
        support_switch_lineage_v2(
            revocation_provenance_root=_root("switch:revoke:provenance"),
            revocation_trace_roots=revocation_traces,
            issuance_provenance_root=_root("switch:issue:provenance"),
            issuance_trace_roots=issuance_traces,
        )
    with pytest.raises(ValueError, match="integer bound"):
        support_history_advance_v2(
            parent_history_root=_root("history:parent"),
            parent_history_count=MAX_AUTHORITY_REVISION_V2,
            transition_id="transition:support-v2:history-bound",
            mutation_delta_root=_root("history:delta"),
        )

    with pytest.raises(ValueError, match="unsupported"):
        replace(observation, schema="unsupported")
    with pytest.raises(TypeError):
        _bounded_root_tuple(
            "not-an-array",
            "test roots",
            limit=2,
        )
    with pytest.raises(ValueError):
        _bounded_root_tuple((), "test roots", limit=2)
    with pytest.raises(ValueError):
        _bounded_root_tuple(
            (_root("bounded:root"),) * 2,
            "test roots",
            limit=2,
        )
    with pytest.raises(TypeError):
        _bounded_text_tuple(
            "not-an-array",
            "test text",
            limit=2,
        )
    with pytest.raises(ValueError):
        _bounded_text_tuple((), "test text", limit=2)
    with pytest.raises(ValueError):
        _bounded_text_tuple(("duplicate", "duplicate"), "test text", limit=2)

    invalid_assurance = SupportObservationV2.from_dict(observation.to_dict())
    object.__setattr__(invalid_assurance, "assurance", "evidence_bound")
    with pytest.raises(TypeError):
        _validate_bound_context(invalid_assurance, "test observation")
    mismatched_profile = SupportObservationV2.from_dict(observation.to_dict())
    object.__setattr__(mismatched_profile, "profile", "profile:unsupported")
    with pytest.raises(ValueError, match="mismatched"):
        _validate_bound_context(mismatched_profile, "test observation")
    with pytest.raises(ValueError, match="expiry"):
        replace(
            observation,
            expires_at_step=observation.observed_at_step,
            observation_root="",
        )

    with pytest.raises(TypeError):
        canonical_support_observations_v2(
            cast(tuple[SupportObservationV2, ...], "not-an-array")
        )
    with pytest.raises(ValueError):
        canonical_support_observations_v2(())
    with pytest.raises(TypeError):
        canonical_support_observations_v2(
            cast(tuple[SupportObservationV2, ...], (object(),))
        )
    with pytest.raises(ValueError, match="observation root"):
        canonical_support_observations_v2((observation, observation))
    replayed_observation = replace(
        observation,
        evidence_root=_root("observation:replayed-ref"),
        observation_root="",
    )
    with pytest.raises(ValueError, match="observation_ref"):
        canonical_support_observations_v2((observation, replayed_observation))


def test_public_support_v2_committed_delta_and_incremental_adoption_are_total() -> None:
    ledger = _ledger("committed-delta-totality")
    upstream = _upstream(ledger)
    initialized, initialized_source = _initialize(
        ledger,
        label="committed-delta-totality",
    )
    initialized_attempt = _advance_support(
        ledger,
        initialized,
        initialized_source,
    )
    _assert_committed(initialized_attempt)
    initialized_state = _support_state(ledger, initialized)
    claim_root = _root("claim:committed-delta-totality")
    issued, issued_source = _prepare_issue(
        ledger,
        initialized_state,
        upstream.membership_state,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="committed-delta-totality",
        current_step=5,
    )
    other_issued, _ = _prepare_issue(
        ledger,
        initialized_state,
        upstream.membership_state,
        candidate_ref="candidate:support-v2:safe",
        claim_root=claim_root,
        principal_ref="principal:beta",
        label="committed-delta-totality:other",
        current_step=5,
    )
    issued_expected_roots = _expected_source_roots(issued, issued_source)
    denied_attempt = advance_support_state_v2(
        issued,
        source=issued_source,
        authority_session=None,
    )
    assert denied_attempt.disposition is GovernanceCommitDispositionV2.DENIED
    issued_attempt = _advance_support(ledger, issued, issued_source)
    _assert_committed(issued_attempt)
    issued_state = _support_state(ledger, issued)
    assert issued.issued_lease is not None
    lease = issued.issued_lease

    issued_view = ledger.store.load_commit_view_v2(
        issued.scope_ref,
        issued.stream_ref,
        issued.transition_id,
    )
    assert issued_view.committed_transition is not None
    issued_transition = issued_view.committed_transition.batch.transition
    assert issued_transition is not None
    issued_records = dict(issued_transition.state_records)
    (
        decoded_issued,
        support_binding,
        source_context_root,
        source_verification_root,
        membership_precondition,
    ) = _decode_support_state_records(issued_records, ledger.domain)
    assert decoded_issued == issued
    assert membership_precondition is not None
    assert source_context_root == issued.snapshot.source_context_root
    assert source_verification_root == issued_expected_roots[1]

    with pytest.raises(ValueError, match="missing"):
        _validate_support_membership_precondition(issued, None)
    wrong_membership_precondition = GovernanceReadPreconditionV2(
        stream_ref=initialized.stream_ref,
        expected_revision=0,
        expected_root=_root("wrong:membership-head"),
    )
    with pytest.raises(ValueError, match="cross-bound"):
        _validate_support_membership_precondition(
            issued,
            wrong_membership_precondition,
        )
    with pytest.raises(TypeError, match="exact object"):
        _decode_support_state_records(object(), ledger.domain)
    wrong_state_domain = dict(issued_records)
    wrong_state_domain["domain_root"] = _root("wrong:domain")
    with pytest.raises(ValueError, match="domain"):
        _decode_support_state_records(wrong_state_domain, ledger.domain)
    wrong_state_payload = dict(issued_records)
    wrong_state_payload["request_root"] = _root("wrong:request")
    with pytest.raises(ValueError, match="payload"):
        _decode_support_state_records(wrong_state_payload, ledger.domain)
    wrong_state_source = dict(issued_records)
    wrong_state_source["source_context_root"] = _root("wrong:source-context")
    with pytest.raises(ValueError, match="source lineage"):
        _decode_support_state_records(wrong_state_source, ledger.domain)
    with pytest.raises(ValueError, match="fields"):
        _validate_stored_session_binding({}, issued)
    wrong_support_binding = dict(support_binding)
    wrong_support_binding["run_ref"] = "run:cross-bound"
    with pytest.raises(ValueError, match="mismatched"):
        _validate_stored_session_binding(wrong_support_binding, issued)
    empty_support_grant = dict(support_binding)
    empty_support_grant["grant_ref"] = ""
    with pytest.raises(ValueError, match="grant binding"):
        _validate_stored_session_binding(empty_support_grant, issued)

    with pytest.raises(TypeError, match="exact request"):
        _adopt_committed_support_successor_v2(
            initialized_state,
            cast(Any, object()),
            issued_attempt,
        )
    with pytest.raises(ValueError, match="initialization"):
        _adopt_committed_support_successor_v2(
            initialized_state,
            initialized,
            initialized_attempt,
        )
    with pytest.raises(TypeError, match="exact commit attempt"):
        _adopt_committed_support_successor_v2(
            initialized_state,
            issued,
            cast(Any, object()),
        )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as denied_adoption:
        _adopt_committed_support_successor_v2(
            initialized_state,
            issued,
            denied_attempt,
        )
    assert denied_adoption.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as request_adoption:
        _adopt_committed_support_successor_v2(
            initialized_state,
            other_issued,
            issued_attempt,
        )
    assert request_adoption.value.code is (
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as parent_adoption:
        _adopt_committed_support_successor_v2(
            issued_state,
            issued,
            issued_attempt,
        )
    assert parent_adoption.value.code is (
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )

    with pytest.raises(ValueError, match="transition-derived"):
        replace(
            lease,
            lease_ref="lease:support-v2:wrong",
            lease_root="",
        )
    with pytest.raises(ValueError, match="expiry"):
        replace(
            lease,
            expires_at_step=lease.issued_at_step,
            lease_root="",
        )
    with pytest.raises(ValueError, match="records and roots"):
        replace(
            lease,
            positive_observation_roots=(_root("wrong:observation"),),
            positive_observation_set_root="",
            lease_root="",
        )
    with pytest.raises(TypeError):
        canonical_support_leases_v2(cast(tuple[SupportLeaseV2, ...], "not-an-array"))
    with pytest.raises(ValueError):
        canonical_support_leases_v2((lease,) * 1025)
    with pytest.raises(TypeError):
        canonical_support_leases_v2(cast(tuple[SupportLeaseV2, ...], (object(),)))
    with pytest.raises(ValueError, match="repeats a lease root"):
        canonical_support_leases_v2((lease, lease))
    with pytest.raises(ValueError, match="replay collision"):
        _index_collision(
            {"identity": lease.lease_root},
            "identity",
            _root("other:lease"),
            "test",
        )

    revoked, _ = _prepare_revoke(
        ledger,
        issued_state,
        lease_root=lease.lease_root,
        label="committed-delta-totality",
        current_step=6,
    )
    assert revoked.revocation is not None
    with pytest.raises(ValueError, match="transition-derived"):
        replace(
            revoked.revocation,
            revocation_ref="revocation:support-v2:wrong",
            revocation_root="",
        )

    with pytest.raises(ValueError, match="no issued lease"):
        support_issued_event_lineage_v2(
            initialized,
            {},
            read_set_root=_root("read-set"),
        )
    with pytest.raises(ValueError, match="no revocation"):
        support_revoked_event_lineage_v2(
            initialized,
            {},
            read_set_root=_root("read-set"),
        )
    assert _verified_source_manifest_v2(initialized_source) == ledger.manifest
    assert _expected_source_roots(initialized, initialized_source)[0] == (
        initialized.snapshot.source_context_root
    )

    wrong_evicted_wire = issued.to_dict()
    wrong_evicted_wire["evicted_lease_roots"] = tuple(issued.evicted_lease_roots)
    with pytest.raises(TypeError):
        SupportAdvanceRequestV2.from_dict(wrong_evicted_wire)
    wrong_delta_snapshot = SupportSnapshotV2.from_dict(issued.snapshot.to_dict())
    object.__setattr__(
        wrong_delta_snapshot,
        "mutation_delta_root",
        _root("wrong:mutation-delta"),
    )
    with pytest.raises(ValueError, match="delta root"):
        replace(
            issued,
            snapshot=wrong_delta_snapshot,
            request_root="",
        )
    retained_eviction = SupportAdvanceRequestV2.from_dict(issued.to_dict())
    object.__setattr__(
        retained_eviction,
        "evicted_lease_roots",
        (lease.lease_root,),
    )
    with pytest.raises(ValueError, match="retains"):
        _validate_support_mutation_semantics_v2(retained_eviction)
    duplicate_revocation_eviction = SupportAdvanceRequestV2.from_dict(revoked.to_dict())
    object.__setattr__(
        duplicate_revocation_eviction,
        "evicted_lease_roots",
        (revoked.revoked_lease_root,),
    )
    with pytest.raises(ValueError, match="also be an expiry"):
        _validate_support_mutation_semantics_v2(duplicate_revocation_eviction)

    wrong_transition_snapshot = SupportSnapshotV2.from_dict(
        initialized.snapshot.to_dict()
    )
    wrong_transition_id = "transition:support-v2:wrong"
    wrong_history_root, wrong_history_count = support_history_advance_v2(
        parent_history_root=wrong_transition_snapshot.parent_history_root,
        parent_history_count=wrong_transition_snapshot.parent_history_count,
        transition_id=wrong_transition_id,
        mutation_delta_root=wrong_transition_snapshot.mutation_delta_root,
    )
    object.__setattr__(
        wrong_transition_snapshot,
        "transition_id",
        wrong_transition_id,
    )
    object.__setattr__(
        wrong_transition_snapshot,
        "history_root",
        wrong_history_root,
    )
    object.__setattr__(
        wrong_transition_snapshot,
        "history_count",
        wrong_history_count,
    )
    with pytest.raises(ValueError, match="transition"):
        _validate_snapshot_shape(wrong_transition_snapshot)
    divergent_history_count = SupportSnapshotV2.from_dict(
        initialized.snapshot.to_dict()
    )
    object.__setattr__(divergent_history_count, "revision", 2)
    object.__setattr__(divergent_history_count, "parent_revision", 1)
    with pytest.raises(ValueError, match="count and revision"):
        _validate_snapshot_continuity(divergent_history_count)

    early_child_arguments: dict[str, Any] = {
        "kind": SupportMutationKindV2.REVOKE,
        "issuer_ref": ISSUER_REF,
        "observed_epoch": initialized.observed_epoch,
        "mutation_ref": "mutation:support:child-totality",
        "current_step": initialized.snapshot.current_step,
        "provenance_root": _root("child:provenance"),
        "trace_roots": (_root("child:trace"),),
    }
    with pytest.raises(ValueError, match="moves backwards"):
        _child_request(
            initialized.snapshot,
            **{
                **early_child_arguments,
                "current_step": initialized.snapshot.current_step - 1,
            },
        )
    with pytest.raises(ValueError, match="absent"):
        _child_request(
            initialized.snapshot,
            **{
                **early_child_arguments,
                "revoked_lease": lease,
            },
        )
    with pytest.raises(ValueError, match="another transition"):
        _child_request(
            initialized.snapshot,
            **{
                **early_child_arguments,
                "kind": SupportMutationKindV2.ISSUE,
                "issued_lease": lease,
            },
        )
    inactive_lease = SupportLeaseV2.from_dict(lease.to_dict())
    inactive_transition_id = support_transition_id_v2(
        initialized.stream_ref,
        "mutation:support:child-inactive",
    )
    object.__setattr__(
        inactive_lease,
        "mutation_transition_id",
        inactive_transition_id,
    )
    object.__setattr__(
        inactive_lease,
        "expires_at_step",
        initialized.snapshot.current_step,
    )
    with pytest.raises(ValueError, match="not active"):
        _child_request(
            initialized.snapshot,
            **{
                **early_child_arguments,
                "kind": SupportMutationKindV2.ISSUE,
                "mutation_ref": "mutation:support:child-inactive",
                "issued_lease": inactive_lease,
            },
        )
    replayed_lease = SupportLeaseV2.from_dict(lease.to_dict())
    replay_transition_id = support_transition_id_v2(
        issued.stream_ref,
        "mutation:support:child-replay",
    )
    object.__setattr__(
        replayed_lease,
        "mutation_transition_id",
        replay_transition_id,
    )
    with pytest.raises(ValueError, match="reuses"):
        _child_request(
            issued.snapshot,
            **{
                **early_child_arguments,
                "kind": SupportMutationKindV2.ISSUE,
                "observed_epoch": issued.observed_epoch,
                "mutation_ref": "mutation:support:child-replay",
                "current_step": issued.snapshot.current_step + 1,
                "issued_lease": replayed_lease,
            },
        )


def test_public_support_v2_evaluation_contract_and_engine_branches_are_total() -> None:
    ledger = _ledger("evaluation-totality")
    upstream = _upstream(ledger)
    initialized, initialized_source = _initialize(
        ledger,
        label="evaluation-totality",
    )
    _assert_committed(_advance_support(ledger, initialized, initialized_source))
    initialized_state = _support_state(ledger, initialized)
    claim_root = _root("claim:evaluation-totality")
    issued, issued_source = _prepare_issue(
        ledger,
        initialized_state,
        upstream.membership_state,
        candidate_ref="candidate:support-v2:accept",
        claim_root=claim_root,
        principal_ref="principal:alpha",
        label="evaluation-totality",
        current_step=5,
    )
    _assert_committed(_advance_support(ledger, issued, issued_source))
    issued_state = _support_state(ledger, issued)
    assert issued.issued_lease is not None
    lease = issued.issued_lease
    membership = upstream.membership_state.snapshot
    support = issued_state.snapshot
    evaluation = evaluate_support_v2(
        support_state=issued_state,
        membership_state=upstream.membership_state,
        manifest=ledger.manifest,
        candidate_ref=lease.candidate_ref,
        claim_root=claim_root,
        epoch=membership.epoch,
        current_step=5,
    )
    assert SupportEvaluationV2.from_dict(evaluation.to_dict()) == evaluation
    assert evaluation.active_support_cluster_count == 1

    with pytest.raises(ValueError, match="root"):
        replace(
            evaluation,
            evaluation_root=_root("wrong:evaluation"),
        )
    wrong_schema = SupportEvaluationV2.from_dict(evaluation.to_dict())
    object.__setattr__(wrong_schema, "schema", "unsupported")
    with pytest.raises(ValueError, match="schema"):
        _validate_evaluation_scalars(wrong_schema)
    wrong_policy_type = SupportEvaluationV2.from_dict(evaluation.to_dict())
    object.__setattr__(wrong_policy_type, "policy_support_met", 1)
    with pytest.raises(TypeError, match="exact bool"):
        _validate_evaluation_scalars(wrong_policy_type)
    wrong_finding_type = SupportEvaluationV2.from_dict(evaluation.to_dict())
    object.__setattr__(
        wrong_finding_type,
        "equivocations",
        (object(),),
    )
    with pytest.raises(TypeError, match="equivocations"):
        _normalize_evaluation_collections(wrong_finding_type)

    finding = SupportEquivocationV2(
        target_ref=evaluation.target_ref,
        claim_root=evaluation.claim_root,
        epoch=evaluation.epoch,
        principal_cluster_ref="cluster:alpha",
        support_snapshot_root=evaluation.support_snapshot_root,
        lease_set_root=support.lease_set_root,
        conflicting_candidate_refs=(
            "candidate:support-v2:accept",
            "candidate:support-v2:safe",
        ),
        conflicting_lease_roots=(
            lease.lease_root,
            _root("lease:evaluation-totality:other"),
        ),
        first_overlap_step=evaluation.current_step,
    )
    assert SupportEquivocationV2.from_dict(finding.to_dict()) == finding
    with pytest.raises(ValueError, match="at least two"):
        replace(
            finding,
            conflicting_candidate_refs=("candidate:support-v2:accept",),
            finding_root="",
        )

    clusters = tuple(evaluation.active_cluster_refs)
    included = tuple(evaluation.included_lease_roots)
    excluded = tuple(evaluation.excluded_lease_roots)
    with pytest.raises(ValueError, match="repeats"):
        _validate_evaluation_derivations(
            evaluation,
            clusters=clusters,
            included=included,
            excluded=excluded,
            findings=(finding, finding),
        )
    with pytest.raises(ValueError, match="includes and excludes"):
        _validate_evaluation_derivations(
            evaluation,
            clusters=clusters,
            included=included,
            excluded=included,
            findings=(),
        )
    with pytest.raises(ValueError, match="cluster count"):
        _validate_evaluation_derivations(
            evaluation,
            clusters=(),
            included=included,
            excluded=excluded,
            findings=(),
        )
    wrong_ratio = SupportEvaluationV2.from_dict(evaluation.to_dict())
    object.__setattr__(
        wrong_ratio,
        "support_ratio_ppm",
        evaluation.support_ratio_ppm - 1,
    )
    with pytest.raises(ValueError, match="ratio"):
        _validate_evaluation_derivations(
            wrong_ratio,
            clusters=clusters,
            included=included,
            excluded=excluded,
            findings=(),
        )
    wrong_policy_result = SupportEvaluationV2.from_dict(evaluation.to_dict())
    object.__setattr__(
        wrong_policy_result,
        "policy_support_met",
        not evaluation.policy_support_met,
    )
    with pytest.raises(ValueError, match="policy result"):
        _validate_evaluation_derivations(
            wrong_policy_result,
            clusters=clusters,
            included=included,
            excluded=excluded,
            findings=(),
        )

    assert (
        _validate_evaluation_context(
            support,
            membership,
            ledger.manifest,
            epoch=membership.epoch,
            current_step=5,
        )
        == ledger.manifest.collective_commit_policy
    )
    empty_membership = MembershipSnapshotV2.from_dict(membership.to_dict())
    object.__setattr__(empty_membership, "clusters", ())
    with pytest.raises(ValueError, match="empty membership"):
        _validate_evaluation_context(
            support,
            empty_membership,
            ledger.manifest,
            epoch=membership.epoch,
            current_step=5,
        )
    with pytest.raises(ValueError, match="predates"):
        _validate_evaluation_context(
            support,
            membership,
            ledger.manifest,
            epoch=membership.epoch,
            current_step=support.current_step - 1,
        )
    with pytest.raises(ValueError, match="expired"):
        _validate_evaluation_context(
            support,
            membership,
            ledger.manifest,
            epoch=membership.epoch,
            current_step=membership.expires_at_step,
        )
    with pytest.raises(ValueError, match="policy or membership"):
        _validate_evaluation_context(
            support,
            membership,
            ledger.manifest,
            epoch=membership.epoch + 1,
            current_step=5,
        )
    cross_bound_support = SupportSnapshotV2.from_dict(support.to_dict())
    object.__setattr__(cross_bound_support, "run_ref", "run:cross-bound")
    with pytest.raises(ValueError, match="states are cross-bound"):
        _validate_evaluation_context(
            cross_bound_support,
            membership,
            ledger.manifest,
            epoch=membership.epoch,
            current_step=5,
        )

    assert _lease_matches_evaluation(
        lease,
        membership,
        claim_root=claim_root,
        epoch=membership.epoch,
    )
    with pytest.raises(ValueError, match="absent"):
        support_lease_status_v2(
            issued_state,
            _root("lease:absent"),
            current_step=5,
        )
    future_lease = SupportLeaseV2.from_dict(lease.to_dict())
    object.__setattr__(future_lease, "issued_at_step", 6)
    object.__setattr__(future_lease, "expires_at_step", 7)
    assert _active_interval(future_lease, current_step=5) is None

    interval_leases = tuple(SupportLeaseV2.from_dict(lease.to_dict()) for _ in range(4))
    interval_values = (
        ("candidate:a", 1, 5),
        ("candidate:b", 2, 3),
        ("candidate:b", 2, 3),
        ("candidate:c", 3, 4),
    )
    for interval_lease, (candidate, start, end) in zip(
        interval_leases,
        interval_values,
        strict=True,
    ):
        object.__setattr__(interval_lease, "candidate_ref", candidate)
        object.__setattr__(interval_lease, "issued_at_step", start)
        object.__setattr__(interval_lease, "expires_at_step", end)
    assert _conflict_segments(
        tuple(
            (interval_lease, start, end)
            for interval_lease, (_, start, end) in zip(
                interval_leases,
                interval_values,
                strict=True,
            )
        )
    ) == ((2, 4),)
    assert (
        _lease_status(
            lease,
            equivocated_roots=frozenset({lease.lease_root}),
            current_step=5,
        )
        is SupportLeaseStatusV2.EQUIVOCATED
    )
