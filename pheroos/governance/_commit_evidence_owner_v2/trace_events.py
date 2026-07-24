"""Canonical Trace ABI events for Commit Evidence v2 authority transitions."""

from __future__ import annotations

from collections.abc import Mapping

from pheroos.trace import TraceEvent

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceIssuerOperationV2,
)
from pheroos.governance._authority_session_v2.operations import _portable_projection
from pheroos.governance._commit_evidence_owner_v2.contracts import (
    CommitEvidenceAdvanceRequestV2,
)
from pheroos.governance._commit_evidence_owner_v2.state_records import (
    _string_object,
)
from pheroos.governance._commit_evidence_projection_v2.records import (
    CommitEvidenceStatusV2,
)


COMMIT_EVIDENCE_QUALIFIED_EVENT_V2 = "commit_evidence_qualified_v2"


def _commit_evidence_events(
    request: CommitEvidenceAdvanceRequestV2,
    session_binding: Mapping[str, object],
    *,
    source_context_root: str,
    parent_head_root: str,
    read_set_root: str,
) -> tuple[TraceEvent, ...]:
    snapshot = request.snapshot
    additions = tuple(
        item
        for item in snapshot.records
        if item.record_root in snapshot.mutation_record_roots
        and item.status is CommitEvidenceStatusV2.ACTIVE
    )
    binding = _string_object(
        _portable_projection(session_binding),
        "commit evidence trace session binding",
    )
    lineage: dict[str, object] = {
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.stream_ref,
        "transition_id": request.transition_id,
        "run_ref": request.run_ref,
        "request_ref": request.advance_ref,
        "request_root": request.request_root,
        "grant_ref": binding["grant_ref"],
        "grant_root": binding["grant_root"],
        "grant_binding_ref": binding["grant_binding_ref"],
        "operation": GovernanceIssuerOperationV2.QUALIFY_EVIDENCE.value,
        "observed_epoch": request.observed_epoch,
        "session_binding": binding,
        "target_ref": request.target_ref,
        "advance_ref": request.advance_ref,
        "protocol_ref": snapshot.protocol_ref,
        "manifest_root": snapshot.manifest_root,
        "authority_policy_root": snapshot.authority_policy_root,
        "commit_policy_root": snapshot.commit_policy_root,
        "evidence_policy_root": snapshot.evidence_policy.policy_root,
        "profile": snapshot.profile,
        "assurance": snapshot.assurance.value,
        "epoch": snapshot.epoch,
        "revision": snapshot.revision,
        "current_step": snapshot.current_step,
        "expires_at_step": snapshot.expires_at_step,
        "parent_revision": snapshot.parent_revision,
        "parent_epoch": snapshot.parent_epoch,
        "parent_transition_id": snapshot.parent_transition_id,
        "parent_snapshot_root": snapshot.parent_snapshot_root,
        "parent_history_root": snapshot.parent_history_root,
        "parent_history_count": snapshot.parent_history_count,
        "parent_head_root": parent_head_root,
        "snapshot_root": snapshot.snapshot_root,
        "history_root": snapshot.history_root,
        "history_count": snapshot.history_count,
        "mutation_issuer_ref": snapshot.mutation_issuer_ref,
        "mutation_provenance_root": snapshot.mutation_provenance_root,
        "mutation_trace_roots": list(snapshot.mutation_trace_roots),
        "mutation_record_roots": list(snapshot.mutation_record_roots),
        "removed_record_roots": list(snapshot.removed_record_roots),
        "revocation_roots": list(snapshot.revocation_roots),
        "attestation_roots": sorted(item.attestation_root for item in additions),
        "disposition_roots": sorted(
            item.disposition_root for item in additions if item.disposition_root
        ),
        "record_count": snapshot.record_count,
        "active_record_count": snapshot.active_record_count,
        "record_set_root": snapshot.record_set_root,
        "active_record_set_root": snapshot.active_record_set_root,
        "mutation_delta_root": snapshot.mutation_delta_root,
        "membership_stream_ref": snapshot.membership_stream_ref,
        "membership_revision": snapshot.membership_revision,
        "membership_transition_id": snapshot.membership_transition_id,
        "membership_head_root": snapshot.membership_head_root,
        "membership_snapshot_root": snapshot.membership_snapshot_root,
        "membership_root": snapshot.membership_root,
        "membership_current_step": snapshot.membership_current_step,
        "membership_expires_at_step": snapshot.membership_expires_at_step,
        "verification_stream_ref": snapshot.verification_stream_ref,
        "verification_revision": snapshot.verification_revision,
        "verification_transition_id": snapshot.verification_transition_id,
        "verification_head_root": snapshot.verification_head_root,
        "verification_snapshot_root": snapshot.verification_snapshot_root,
        "verification_set_root": snapshot.verification_set_root,
        "verification_current_step": snapshot.verification_current_step,
        "verification_expires_at_step": snapshot.verification_expires_at_step,
        "replay_stream_ref": snapshot.replay_stream_ref,
        "replay_revision": snapshot.replay_revision,
        "replay_transition_id": snapshot.replay_transition_id,
        "replay_head_root": snapshot.replay_head_root,
        "replay_snapshot_root": snapshot.replay_snapshot_root,
        "replay_receipt_root": snapshot.replay_receipt_root,
        "replay_current_step": snapshot.replay_current_step,
        "source_context_root": source_context_root,
        "read_set_root": read_set_root,
    }
    return (
        TraceEvent(
            event_type=COMMIT_EVIDENCE_QUALIFIED_EVENT_V2,
            protocol_id="pheroos.protocol.v2",
            target=request.target_ref,
            reason="qualify a complete replacement evidence state",
            lineage=lineage,
        ),
    )


__all__: tuple[str, ...] = ()
