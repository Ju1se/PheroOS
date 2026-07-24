"""Canonical atomic Trace events for Commit Certificate v2."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from pheroos.trace import TraceEvent

from pheroos.governance._authority_session_v2.operations import _portable_projection
from pheroos.governance._commit_certificate_v2.enums import (
    CommitCertificateMutationKindV2,
)
from pheroos.governance._commit_certificate_v2.request import (
    CommitCertificateRequestV2,
)
from pheroos.governance._commit_certificate_v2.state_contracts import (
    CommitCertificateSnapshotV2,
)


def _commit_certificate_event_v2(
    request: CommitCertificateRequestV2,
    snapshot: CommitCertificateSnapshotV2,
    session_binding: Mapping[str, object],
    *,
    parent_head_root: str,
    read_set_root: str,
) -> TraceEvent:
    projected = _portable_projection(session_binding)
    if type(projected) is not dict:
        raise TypeError("commit certificate session binding is invalid")
    binding = cast(dict[str, object], projected)
    event_type = (
        "commit_certificate_conflict_v2"
        if snapshot.mutation_kind is CommitCertificateMutationKindV2.CONFLICT
        else "commit_certificate_verified_v2"
    )
    body = snapshot.certificate.body
    lineage: dict[str, object] = {
        "domain_root": snapshot.domain_root,
        "scope_ref": snapshot.scope_ref,
        "stream_ref": snapshot.stream_ref,
        "transition_id": snapshot.transition_id,
        "request_ref": snapshot.mutation_ref,
        "request_root": request.request_root,
        "observed_epoch": request.observed_epoch,
        "revision": snapshot.revision,
        "parent_revision": snapshot.parent_revision,
        "parent_transition_id": snapshot.parent_transition_id,
        "parent_snapshot_root": snapshot.parent_snapshot_root,
        "parent_head_root": parent_head_root,
        "snapshot_root": snapshot.snapshot_root,
        "state_root": snapshot.state_root,
        "history_root": snapshot.history_root,
        "history_count": snapshot.history_count,
        "protocol_ref": snapshot.protocol_ref,
        "run_ref": snapshot.run_ref,
        "target_ref": snapshot.target_ref,
        "epoch": body.epoch,
        "current_step": snapshot.current_step,
        "profile": body.profile,
        "assurance": body.assurance.value,
        "manifest_root": body.manifest_root,
        "commit_policy_root": body.commit_policy_root,
        "decision_stream_ref": body.decision_stream_ref,
        "decision_revision": body.decision_revision,
        "decision_transition_id": body.decision_transition_id,
        "decision_snapshot_root": body.decision_snapshot_root,
        "decision_head_root": body.decision_head_root,
        "decision_receipt_root": body.decision_receipt_root,
        "decision_inclusion_root": body.decision_inclusion_root,
        "seal_transition_id": body.seal_transition_id,
        "seal_revision": body.seal_revision,
        "seal_snapshot_root": body.seal_snapshot_root,
        "seal_receipt_root": body.seal_receipt_root,
        "seal_head_root": body.seal_head_root,
        "seal_inclusion_root": body.seal_inclusion_root,
        "seal_root": body.seal_root,
        "window_root": body.window_root,
        "frozen_dependency_root": body.frozen_dependency_root,
        "assessment_root": body.assessment_root,
        "candidate_ref": body.candidate_ref,
        "claim_root": body.claim_root,
        "evidence_root": body.evidence_root,
        "challenge_root": body.challenge_root,
        "lease_root": body.lease_root,
        "output_contract_root": body.output_contract_root,
        "output_payload_root": body.output_payload_root,
        "authority_leaf_set_root": body.authority_leaf_set_root,
        "authority_leaves": [item.to_dict() for item in body.authority_leaves],
        "certificate_id": snapshot.certificate.certificate_id,
        "certificate_body_root": body.body_root,
        "certificate_envelope_root": snapshot.certificate.envelope_root,
        "issuer_ref": snapshot.certificate.issuer_ref,
        "issued_at_step": snapshot.certificate.issued_at_step,
        "provenance_ref": snapshot.certificate.provenance_ref,
        "attestation_refs": list(snapshot.certificate.issuer_attestation_refs),
        "mutation_issuer_ref": snapshot.mutation_issuer_ref,
        "mutation_kind": snapshot.mutation_kind.value,
        "status": snapshot.status.value,
        "reason_codes": list(snapshot.reason_codes),
        "source_context_root": snapshot.source_context_root,
        "read_set_root": read_set_root,
        "grant_ref": binding["grant_ref"],
        "grant_root": binding["grant_root"],
        "grant_binding_ref": binding["grant_binding_ref"],
        "operation": binding["operation"],
        "session_binding": binding,
    }
    return TraceEvent(
        event_type=event_type,
        protocol_id="pheroos.protocol.v2",
        target=request.target_ref,
        reason="atomically verify durable Commit Certificate v2 authority",
        lineage=lineage,
    )


__all__: tuple[str, ...] = ()
