"""Canonical atomic Trace projections for Commit Gate v2 mutations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from pheroos.trace import TraceEvent

from pheroos.governance._authority_session_v2.operations import _portable_projection
from pheroos.governance._commit_gate_v2.permission_contracts import (
    CommitPermissionRequestV2,
)
from pheroos.governance._commit_gate_v2.stop_contracts import CommitStopRequestV2


def _commit_gate_event_v2(
    request: CommitStopRequestV2 | CommitPermissionRequestV2,
    session_binding: Mapping[str, object],
    *,
    operation: str,
    source_context_root: str,
    parent_head_root: str,
    read_set_root: str,
) -> TraceEvent:
    snapshot = request.snapshot
    binding = cast(dict[str, object], _portable_projection(session_binding))
    if type(request) is CommitStopRequestV2:
        request_ref = request.resolution_ref
    else:
        permission_request = cast(CommitPermissionRequestV2, request)
        request_ref = permission_request.permission_ref
    lineage: dict[str, object] = {
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.stream_ref,
        "transition_id": request.transition_id,
        "run_ref": request.run_ref,
        "request_ref": request_ref,
        "request_root": request.request_root,
        "grant_ref": binding["grant_ref"],
        "grant_root": binding["grant_root"],
        "grant_binding_ref": binding["grant_binding_ref"],
        "operation": operation,
        "observed_epoch": request.observed_epoch,
        "session_binding": binding,
        "target_ref": request.target_ref,
        "protocol_ref": snapshot.protocol_ref,
        "manifest_root": snapshot.manifest_root,
        "commit_policy_root": snapshot.commit_policy_root,
        "policy_root": snapshot.policy_root,
        "profile": snapshot.profile,
        "assurance": snapshot.assurance.value,
        "revision": snapshot.revision,
        "current_step": snapshot.current_step,
        "parent_revision": snapshot.parent_revision,
        "parent_transition_id": snapshot.parent_transition_id,
        "parent_snapshot_root": snapshot.parent_snapshot_root,
        "parent_head_root": parent_head_root,
        "snapshot_root": snapshot.snapshot_root,
        "mutation_issuer_ref": snapshot.mutation_issuer_ref,
        "grant_issuer_ref": snapshot.mutation_issuer_ref,
        "issued_at_step": snapshot.issued_at_step,
        "expires_at_step": snapshot.expires_at_step,
        "dependency_root": snapshot.dependencies.dependency_root,
        "evaluation_context_root": snapshot.evaluation_context_root,
        "source_context_root": source_context_root,
        "read_set_root": read_set_root,
    }
    for name in ("replay", "risk", "verification", "membership", "support"):
        for suffix in (
            "stream_ref",
            "revision",
            "transition_id",
            "snapshot_root",
            "head_root",
        ):
            lineage[f"{name}_{suffix}"] = getattr(
                snapshot.dependencies, f"{name}_{suffix}"
            )
    if type(request) is CommitStopRequestV2:
        stop_snapshot = request.snapshot
        lineage.update(
            {
                "resolution_ref": request.resolution_ref,
                "blocked": stop_snapshot.blocked,
                "reason_codes": list(stop_snapshot.reason_codes),
                "reason_root": stop_snapshot.reason_root,
            }
        )
        return TraceEvent(
            event_type="commit_stop_resolved_v2",
            protocol_id="pheroos.protocol.v2",
            target=request.target_ref,
            reason="atomically resolve the durable commit stop gate",
            lineage=lineage,
        )
    permission_request = cast(CommitPermissionRequestV2, request)
    permission_snapshot = permission_request.snapshot
    lineage.update(
        {
            "permission_ref": permission_request.permission_ref,
            "allowed": permission_snapshot.allowed,
            "candidate_refs": list(permission_snapshot.candidate_refs),
            "candidate_set_root": permission_snapshot.candidate_set_root,
            "claim_roots": list(permission_snapshot.claim_roots),
            "claims_root": permission_snapshot.claims_root,
        }
    )
    return TraceEvent(
        event_type="commit_permission_issued_v2",
        protocol_id="pheroos.protocol.v2",
        target=permission_request.target_ref,
        reason="atomically issue the durable commit action permission",
        lineage=lineage,
    )


__all__: tuple[str, ...] = ()
