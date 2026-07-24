"""Provider-neutral lineage dictionaries for Support v2 events."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pheroos.governance._support_v2.support_request_contracts import (
    SupportAdvanceRequestV2,
)


def support_event_lineage_v2(
    request: SupportAdvanceRequestV2,
    session_binding: Mapping[str, Any],
    *,
    source_context_root: str,
    source_verification_root: str,
    parent_head_root: str,
    read_set_root: str,
) -> dict[str, object]:
    snapshot = request.snapshot
    return {
        **_authority_event_common(request, session_binding),
        "mutation_kind": request.mutation_kind.value,
        "revision": snapshot.revision,
        "initialized_at_step": snapshot.initialized_at_step,
        "current_step": snapshot.current_step,
        "mutation_provenance_root": snapshot.mutation_provenance_root,
        "mutation_trace_roots": list(snapshot.mutation_trace_roots),
        "mutation_delta_root": snapshot.mutation_delta_root,
        "evicted_lease_roots": list(request.evicted_lease_roots),
        "parent_revision": snapshot.parent_revision,
        "parent_transition_id": snapshot.parent_transition_id,
        "parent_snapshot_root": snapshot.parent_snapshot_root,
        "parent_history_root": snapshot.parent_history_root,
        "parent_history_count": snapshot.parent_history_count,
        "history_root": snapshot.history_root,
        "history_count": snapshot.history_count,
        "parent_head_root": parent_head_root,
        "snapshot_root": snapshot.snapshot_root,
        "lease_set_root": snapshot.lease_set_root,
        "active_lease_count": len(snapshot.leases),
        "issued_lease_root": request.issued_lease_root,
        "revoked_lease_root": request.revoked_lease_root,
        "revocation_root": request.revocation_root,
        "membership_stream_ref": request.membership_stream_ref,
        "membership_transition_id": request.membership_transition_id,
        "membership_snapshot_root": request.membership_snapshot_root,
        "source_context_root": source_context_root,
        "source_verification_root": source_verification_root,
        "read_set_root": read_set_root,
    }


def support_issued_event_lineage_v2(
    request: SupportAdvanceRequestV2,
    session_binding: Mapping[str, Any],
    *,
    read_set_root: str,
) -> dict[str, object]:
    lease = request.issued_lease
    if lease is None:
        raise ValueError("support issued event has no issued lease")
    return {
        **_authority_event_common(request, session_binding),
        "lease_root": lease.lease_root,
        "lease_ref": lease.lease_ref,
        "mutation_transition_id": lease.mutation_transition_id,
        "proposal_root": lease.proposal_root,
        "target_ref": lease.target_ref,
        "candidate_ref": lease.candidate_ref,
        "claim_root": lease.claim_root,
        "epoch": lease.epoch,
        "principal_ref": lease.principal_ref,
        "principal_cluster_ref": lease.principal_cluster_ref,
        "membership_principal_root": lease.membership_principal_root,
        "principal_verification_root": lease.principal_verification_root,
        "membership_stream_ref": lease.membership_stream_ref,
        "membership_transition_id": lease.membership_transition_id,
        "membership_snapshot_root": lease.membership_snapshot_root,
        "membership_root": lease.membership_root,
        "positive_observation_set_root": lease.positive_observation_set_root,
        "prior_lease_root": lease.prior_lease_root,
        "issuance_issuer_ref": lease.issuance_issuer_ref,
        "issued_at_step": lease.issued_at_step,
        "expires_at_step": lease.expires_at_step,
        "proposal_provenance_root": lease.proposal_provenance_root,
        "proposal_trace_roots": list(lease.proposal_trace_roots),
        "issuance_provenance_root": lease.issuance_provenance_root,
        "issuance_trace_roots": list(lease.issuance_trace_roots),
        "read_set_root": read_set_root,
    }


def support_revoked_event_lineage_v2(
    request: SupportAdvanceRequestV2,
    session_binding: Mapping[str, Any],
    *,
    read_set_root: str,
) -> dict[str, object]:
    item = request.revocation
    if item is None:
        raise ValueError("support revoked event has no revocation")
    return {
        **_authority_event_common(request, session_binding),
        "revocation_root": item.revocation_root,
        "revocation_ref": item.revocation_ref,
        "mutation_transition_id": item.mutation_transition_id,
        "lease_root": item.lease_root,
        "target_ref": item.target_ref,
        "candidate_ref": item.candidate_ref,
        "claim_root": item.claim_root,
        "epoch": item.epoch,
        "principal_ref": item.principal_ref,
        "principal_cluster_ref": item.principal_cluster_ref,
        "lease_issuance_issuer_ref": item.lease_issuance_issuer_ref,
        "revocation_issuer_ref": item.revocation_issuer_ref,
        "reason_codes": list(item.reason_codes),
        "revoked_at_step": item.revoked_at_step,
        "provenance_root": item.provenance_root,
        "source_trace_roots": list(item.source_trace_roots),
        "read_set_root": read_set_root,
    }


def _authority_event_common(
    request: SupportAdvanceRequestV2,
    binding: Mapping[str, Any],
) -> dict[str, object]:
    return {
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "profile": request.snapshot.profile,
        "assurance": request.snapshot.assurance.value,
        "manifest_root": request.snapshot.manifest_root,
        "commit_policy_root": request.snapshot.commit_policy_root,
        "authority_policy_root": request.snapshot.authority_policy_root,
        "protocol_ref": request.snapshot.protocol_ref,
        "target_ref": request.snapshot.target_ref,
        "mutation_issuer_ref": request.snapshot.mutation_issuer_ref,
        "stream_ref": request.stream_ref,
        "transition_id": request.transition_id,
        "run_ref": request.run_ref,
        "request_ref": request.mutation_ref,
        "request_root": request.request_root,
        "grant_ref": binding["grant_ref"],
        "grant_root": binding["grant_root"],
        "grant_binding_ref": binding["grant_binding_ref"],
        "operation": "qualify_evidence",
        "observed_epoch": request.observed_epoch,
        "session_binding": dict(binding),
    }


__all__: tuple[str, ...] = ()
