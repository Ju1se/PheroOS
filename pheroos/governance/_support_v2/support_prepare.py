"""Deterministic request preparation for the durable Support v2 ledger."""

from __future__ import annotations

from collections.abc import Sequence

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2

from pheroos.governance._authority_store_v2_contracts.foundation import _require_root
from pheroos.governance._support_v2.common import (
    _require_bounded_text_v2,
    _require_count_v2,
)
from pheroos.governance._support_v2.membership_contracts import MembershipSnapshotV2
from pheroos.governance._support_v2.support_lease_contracts import (
    SupportLeaseProposalV2,
    SupportLeaseV2,
    SupportObservationV2,
    SupportRevocationV2,
)
from pheroos.governance._support_v2.support_projection import _current_projection
from pheroos.governance._support_v2.support_source_binding import (
    _mutation_lineage_roots,
)
from pheroos.governance._support_v2.support_source_proof import (
    VerifiedSupportSourceV2,
    _issue_source,
)
from pheroos.governance._support_v2.support_state_access import (
    _membership_parent,
    _support_parent,
)
from pheroos.governance._support_v2.support_state_contracts import (
    SUPPORT_GENESIS_HISTORY_ROOT_V2,
    SUPPORT_GENESIS_SNAPSHOT_ROOT_V2,
    SUPPORT_GENESIS_TRANSITION_ID_V2,
    SupportAdvanceRequestV2,
    SupportMutationKindV2,
    SupportSnapshotV2,
    support_history_advance_v2,
    support_switch_lineage_v2,
    support_stream_ref_v2,
    support_transition_id_v2,
)
from pheroos.governance._support_v2.support_verification import (
    _validated_child_manifest_v2,
    _validated_support_prepare_context_v2,
    active_support_lease_from_parent_v2,
    project_support_lease_v2,
    project_support_revocation_v2,
)


def prepare_support_initialize_v2(
    *,
    domain_root: str,
    scope_ref: str,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    run_ref: str,
    target_ref: str,
    issuer_ref: str,
    observed_epoch: int,
    mutation_ref: str,
    current_step: int,
    provenance_root: str,
    source_trace_roots: tuple[str, ...],
) -> tuple[SupportAdvanceRequestV2, VerifiedSupportSourceV2]:
    context = _validated_support_prepare_context_v2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        manifest=manifest,
        profile=profile,
        run_ref=run_ref,
        target_ref=target_ref,
        issuer_ref=issuer_ref,
        observed_epoch=observed_epoch,
        mutation_ref=mutation_ref,
        current_step=current_step,
        provenance_root=provenance_root,
    )
    stream_ref = support_stream_ref_v2(
        scope_ref,
        profile,
        context.assurance,
        context.manifest_root,
        context.commit_policy_root,
        context.protocol_ref,
        run_ref,
        target_ref,
    )
    transition_id = support_transition_id_v2(stream_ref, mutation_ref)
    source_context_root, mutation_delta_root = _mutation_lineage_roots(
        domain_root=domain_root,
        scope_ref=scope_ref,
        profile=profile,
        assurance=context.assurance.value,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        authority_policy_root=context.authority_policy_root,
        protocol_ref=context.protocol_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        observed_epoch=observed_epoch,
        current_step=current_step,
        mutation_ref=mutation_ref,
        transition_id=transition_id,
        mutation_issuer_ref=issuer_ref,
        mutation_kind=SupportMutationKindV2.INITIALIZE,
        mutation_provenance_root=provenance_root,
        mutation_trace_roots=source_trace_roots,
        parent_snapshot_root=SUPPORT_GENESIS_SNAPSHOT_ROOT_V2,
        parent_transition_id=SUPPORT_GENESIS_TRANSITION_ID_V2,
        parent_revision=0,
        parent_history_root=SUPPORT_GENESIS_HISTORY_ROOT_V2,
        parent_history_count=0,
        issued_lease=None,
        revoked_lease=None,
        revocation=None,
        evicted_lease_roots=(),
        membership=None,
    )
    history_root, history_count = support_history_advance_v2(
        parent_history_root=SUPPORT_GENESIS_HISTORY_ROOT_V2,
        parent_history_count=0,
        transition_id=transition_id,
        mutation_delta_root=mutation_delta_root,
    )
    snapshot = SupportSnapshotV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        profile=profile,
        assurance=context.assurance,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        authority_policy_root=context.authority_policy_root,
        protocol_ref=context.protocol_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        observed_epoch=observed_epoch,
        stream_ref=stream_ref,
        mutation_ref=mutation_ref,
        transition_id=transition_id,
        mutation_kind=SupportMutationKindV2.INITIALIZE,
        revision=1,
        initialized_at_step=current_step,
        current_step=current_step,
        mutation_issuer_ref=issuer_ref,
        mutation_provenance_root=provenance_root,
        mutation_trace_roots=source_trace_roots,
        parent_revision=0,
        parent_transition_id=SUPPORT_GENESIS_TRANSITION_ID_V2,
        parent_snapshot_root=SUPPORT_GENESIS_SNAPSHOT_ROOT_V2,
        parent_history_root=SUPPORT_GENESIS_HISTORY_ROOT_V2,
        parent_history_count=0,
        source_context_root=source_context_root,
        mutation_delta_root=mutation_delta_root,
        history_root=history_root,
        history_count=history_count,
        leases=(),
    )
    request = _request(snapshot)
    return request, _issue_source(request=request, manifest=context.manifest)


def prepare_support_issue_v2(
    *,
    manifest: ScopedProtocolManifestV2,
    parent_state: object,
    membership_state: object,
    proposal: SupportLeaseProposalV2,
    positive_observations: tuple[SupportObservationV2, ...],
    issuer_ref: str,
    observed_epoch: int,
    mutation_ref: str,
    current_step: int,
    issuance_provenance_root: str,
    issuance_trace_roots: tuple[str, ...],
) -> tuple[SupportAdvanceRequestV2, VerifiedSupportSourceV2]:
    _require_manifest(manifest, "issue")
    parent, _ = _support_parent(parent_state)
    context = _validated_child_manifest_v2(manifest, parent)
    membership, _ = _membership_parent(membership_state)
    transition_id = support_transition_id_v2(parent.stream_ref, mutation_ref)
    lease = project_support_lease_v2(
        parent=parent,
        membership=membership,
        proposal=proposal,
        positive_observations=positive_observations,
        manifest=context.manifest,
        mutation_transition_id=transition_id,
        issuance_issuer_ref=issuer_ref,
        current_step=current_step,
        prior_lease=None,
        issuance_provenance_root=issuance_provenance_root,
        issuance_trace_roots=issuance_trace_roots,
    )
    request = _child_request(
        parent,
        kind=SupportMutationKindV2.ISSUE,
        issuer_ref=issuer_ref,
        observed_epoch=observed_epoch,
        mutation_ref=mutation_ref,
        current_step=current_step,
        provenance_root=issuance_provenance_root,
        trace_roots=issuance_trace_roots,
        issued_lease=lease,
        membership=membership,
    )
    return request, _issue_source(
        request=request,
        manifest=context.manifest,
        parent_state=parent_state,
        membership_state=membership_state,
        proposal=proposal,
        observations=positive_observations,
    )


def prepare_support_revoke_v2(
    *,
    manifest: ScopedProtocolManifestV2,
    parent_state: object,
    lease_root: str,
    reason_codes: tuple[str, ...],
    issuer_ref: str,
    observed_epoch: int,
    mutation_ref: str,
    current_step: int,
    provenance_root: str,
    source_trace_roots: tuple[str, ...],
) -> tuple[SupportAdvanceRequestV2, VerifiedSupportSourceV2]:
    _require_manifest(manifest, "revoke")
    parent, _ = _support_parent(parent_state)
    context = _validated_child_manifest_v2(manifest, parent)
    transition_id = support_transition_id_v2(parent.stream_ref, mutation_ref)
    lease = active_support_lease_from_parent_v2(
        parent,
        lease_root,
        current_step=current_step,
    )
    revocation = project_support_revocation_v2(
        lease,
        mutation_transition_id=transition_id,
        reason_codes=reason_codes,
        revocation_issuer_ref=issuer_ref,
        current_step=current_step,
        provenance_root=provenance_root,
        source_trace_roots=source_trace_roots,
    )
    request = _child_request(
        parent,
        kind=SupportMutationKindV2.REVOKE,
        issuer_ref=issuer_ref,
        observed_epoch=observed_epoch,
        mutation_ref=mutation_ref,
        current_step=current_step,
        provenance_root=provenance_root,
        trace_roots=source_trace_roots,
        revoked_lease=lease,
        revocation=revocation,
    )
    return request, _issue_source(
        request=request,
        manifest=context.manifest,
        parent_state=parent_state,
    )


def prepare_support_switch_v2(
    *,
    manifest: ScopedProtocolManifestV2,
    parent_state: object,
    membership_state: object,
    prior_lease_root: str,
    proposal: SupportLeaseProposalV2,
    positive_observations: tuple[SupportObservationV2, ...],
    issuer_ref: str,
    revocation_reason_codes: tuple[str, ...],
    observed_epoch: int,
    mutation_ref: str,
    current_step: int,
    revocation_provenance_root: str,
    revocation_trace_roots: tuple[str, ...],
    issuance_provenance_root: str,
    issuance_trace_roots: tuple[str, ...],
) -> tuple[SupportAdvanceRequestV2, VerifiedSupportSourceV2]:
    _require_manifest(manifest, "switch")
    parent, _ = _support_parent(parent_state)
    context = _validated_child_manifest_v2(manifest, parent)
    membership, _ = _membership_parent(membership_state)
    transition_id = support_transition_id_v2(parent.stream_ref, mutation_ref)
    prior = active_support_lease_from_parent_v2(
        parent,
        prior_lease_root,
        current_step=current_step,
    )
    revocation = project_support_revocation_v2(
        prior,
        mutation_transition_id=transition_id,
        reason_codes=revocation_reason_codes,
        revocation_issuer_ref=issuer_ref,
        current_step=current_step,
        provenance_root=revocation_provenance_root,
        source_trace_roots=revocation_trace_roots,
    )
    replacement = project_support_lease_v2(
        parent=parent,
        membership=membership,
        proposal=proposal,
        positive_observations=positive_observations,
        manifest=context.manifest,
        mutation_transition_id=transition_id,
        issuance_issuer_ref=issuer_ref,
        current_step=current_step,
        prior_lease=prior,
        issuance_provenance_root=issuance_provenance_root,
        issuance_trace_roots=issuance_trace_roots,
    )
    provenance_root, trace_roots = support_switch_lineage_v2(
        revocation_provenance_root=revocation_provenance_root,
        revocation_trace_roots=revocation_trace_roots,
        issuance_provenance_root=issuance_provenance_root,
        issuance_trace_roots=issuance_trace_roots,
    )
    request = _child_request(
        parent,
        kind=SupportMutationKindV2.SWITCH,
        issuer_ref=issuer_ref,
        observed_epoch=observed_epoch,
        mutation_ref=mutation_ref,
        current_step=current_step,
        provenance_root=provenance_root,
        trace_roots=trace_roots,
        issued_lease=replacement,
        revoked_lease=prior,
        revocation=revocation,
        membership=membership,
    )
    return request, _issue_source(
        request=request,
        manifest=context.manifest,
        parent_state=parent_state,
        membership_state=membership_state,
        proposal=proposal,
        observations=positive_observations,
    )


def _child_request(
    parent: SupportSnapshotV2,
    *,
    kind: SupportMutationKindV2,
    issuer_ref: str,
    observed_epoch: int,
    mutation_ref: str,
    current_step: int,
    provenance_root: str,
    trace_roots: tuple[str, ...],
    issued_lease: SupportLeaseV2 | None = None,
    revoked_lease: SupportLeaseV2 | None = None,
    revocation: SupportRevocationV2 | None = None,
    membership: MembershipSnapshotV2 | None = None,
) -> SupportAdvanceRequestV2:
    observed = _require_count_v2(observed_epoch, "support mutation observed_epoch")
    current = _require_count_v2(current_step, "support mutation current_step")
    if observed < parent.observed_epoch or current < parent.current_step:
        raise ValueError("support mutation authority epoch or time moves backwards")
    _require_bounded_text_v2(mutation_ref, "support mutation mutation_ref")
    _require_bounded_text_v2(issuer_ref, "support mutation issuer_ref")
    _require_root(provenance_root, "support mutation provenance_root")
    transition_id = support_transition_id_v2(parent.stream_ref, mutation_ref)
    retained, evicted = _current_projection(parent, current_step=current)
    by_root = {item.lease_root: item for item in retained}
    if revoked_lease is not None:
        if by_root.get(revoked_lease.lease_root) != revoked_lease:
            raise ValueError(
                "support revoked lease is absent from the current projection"
            )
        by_root.pop(revoked_lease.lease_root)
    if issued_lease is not None:
        if issued_lease.mutation_transition_id != transition_id:
            raise ValueError("support issued lease belongs to another transition")
        if not issued_lease.issued_at_step <= current < issued_lease.expires_at_step:
            raise ValueError("support issued lease is not active at the mutation step")
        if issued_lease.lease_root in by_root:
            raise ValueError("support issued lease reuses an active lease root")
        by_root[issued_lease.lease_root] = issued_lease
    leases = tuple(sorted(by_root.values(), key=lambda item: item.lease_root.encode()))
    source_context_root, mutation_delta_root = _mutation_lineage_roots(
        domain_root=parent.domain_root,
        scope_ref=parent.scope_ref,
        profile=parent.profile,
        assurance=parent.assurance.value,
        manifest_root=parent.manifest_root,
        commit_policy_root=parent.commit_policy_root,
        authority_policy_root=parent.authority_policy_root,
        protocol_ref=parent.protocol_ref,
        run_ref=parent.run_ref,
        target_ref=parent.target_ref,
        observed_epoch=observed,
        current_step=current,
        mutation_ref=mutation_ref,
        transition_id=transition_id,
        mutation_issuer_ref=issuer_ref,
        mutation_kind=kind,
        mutation_provenance_root=provenance_root,
        mutation_trace_roots=trace_roots,
        parent_snapshot_root=parent.snapshot_root,
        parent_transition_id=parent.transition_id,
        parent_revision=parent.revision,
        parent_history_root=parent.history_root,
        parent_history_count=parent.history_count,
        issued_lease=issued_lease,
        revoked_lease=revoked_lease,
        revocation=revocation,
        evicted_lease_roots=evicted,
        membership=membership,
    )
    history_root, history_count = support_history_advance_v2(
        parent_history_root=parent.history_root,
        parent_history_count=parent.history_count,
        transition_id=transition_id,
        mutation_delta_root=mutation_delta_root,
    )
    snapshot = SupportSnapshotV2(
        domain_root=parent.domain_root,
        scope_ref=parent.scope_ref,
        profile=parent.profile,
        assurance=parent.assurance,
        manifest_root=parent.manifest_root,
        commit_policy_root=parent.commit_policy_root,
        authority_policy_root=parent.authority_policy_root,
        protocol_ref=parent.protocol_ref,
        run_ref=parent.run_ref,
        target_ref=parent.target_ref,
        observed_epoch=observed,
        stream_ref=parent.stream_ref,
        mutation_ref=mutation_ref,
        transition_id=transition_id,
        mutation_kind=kind,
        revision=parent.revision + 1,
        initialized_at_step=parent.initialized_at_step,
        current_step=current,
        mutation_issuer_ref=issuer_ref,
        mutation_provenance_root=provenance_root,
        mutation_trace_roots=trace_roots,
        parent_revision=parent.revision,
        parent_transition_id=parent.transition_id,
        parent_snapshot_root=parent.snapshot_root,
        parent_history_root=parent.history_root,
        parent_history_count=parent.history_count,
        source_context_root=source_context_root,
        mutation_delta_root=mutation_delta_root,
        history_root=history_root,
        history_count=history_count,
        leases=leases,
    )
    return _request(
        snapshot,
        issued_lease=issued_lease,
        revoked_lease=revoked_lease,
        revocation=revocation,
        evicted_lease_roots=evicted,
        membership=membership,
    )


def _request(
    snapshot: SupportSnapshotV2,
    *,
    issued_lease: SupportLeaseV2 | None = None,
    revoked_lease: SupportLeaseV2 | None = None,
    revocation: SupportRevocationV2 | None = None,
    evicted_lease_roots: Sequence[str] = (),
    membership: MembershipSnapshotV2 | None = None,
) -> SupportAdvanceRequestV2:
    return SupportAdvanceRequestV2(
        domain_root=snapshot.domain_root,
        scope_ref=snapshot.scope_ref,
        run_ref=snapshot.run_ref,
        target_ref=snapshot.target_ref,
        mutation_issuer_ref=snapshot.mutation_issuer_ref,
        observed_epoch=snapshot.observed_epoch,
        mutation_ref=snapshot.mutation_ref,
        stream_ref=snapshot.stream_ref,
        transition_id=snapshot.transition_id,
        mutation_kind=snapshot.mutation_kind,
        issued_lease_root="" if issued_lease is None else issued_lease.lease_root,
        revoked_lease_root="" if revoked_lease is None else revoked_lease.lease_root,
        revocation_root="" if revocation is None else revocation.revocation_root,
        evicted_lease_roots=evicted_lease_roots,
        issued_lease=issued_lease,
        revoked_lease=revoked_lease,
        revocation=revocation,
        membership_stream_ref="" if membership is None else membership.stream_ref,
        membership_transition_id=(
            "" if membership is None else membership.transition_id
        ),
        membership_snapshot_root=(
            "" if membership is None else membership.snapshot_root
        ),
        snapshot=snapshot,
    )


def _require_manifest(manifest: object, operation: str) -> None:
    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError(f"support {operation} requires exact ScopedProtocolManifestV2")


__all__: tuple[str, ...] = ()
