"""Canonical atomic Trace projections for Distributed Commit v2."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from pheroos.trace import TraceEvent

from pheroos.governance._authority_session_v2.operations import _portable_projection
from pheroos.governance._distributed_v2.enums import (
    DistributedLaneV2,
    DistributedMutationKindV2,
)
from pheroos.governance._distributed_v2.lane_states import (
    DistributedCertificateStateV2,
    DistributedEpochStateV2,
    DistributedProposalStateV2,
    DistributedWitnessStateV2,
)
from pheroos.governance._distributed_v2.request import DistributedAdvanceRequestV2


def _distributed_event_v2(
    request: DistributedAdvanceRequestV2,
    session_binding: Mapping[str, object],
    *,
    parent_head_root: str,
    read_set_root: str,
) -> TraceEvent:
    snapshot = request.snapshot
    projected = _portable_projection(session_binding)
    if type(projected) is not dict:
        raise TypeError("distributed session binding is invalid")
    binding = cast(dict[str, object], projected)
    lineage: dict[str, object] = {
        "domain_root": snapshot.domain_root,
        "scope_ref": snapshot.scope_ref,
        "stream_ref": snapshot.stream_ref,
        "transition_id": snapshot.transition_id,
        "request_ref": snapshot.mutation_ref,
        "request_root": request.request_root,
        "observed_epoch": request.observed_epoch,
        "protocol_ref": snapshot.protocol_ref,
        "run_ref": snapshot.run_ref,
        "target_ref": snapshot.target_ref,
        "lane": snapshot.lane.value,
        "mutation_kind": snapshot.mutation_kind.value,
        "status": snapshot.status.value,
        "revision": snapshot.revision,
        "parent_revision": snapshot.parent_revision,
        "parent_transition_id": snapshot.parent_transition_id,
        "parent_snapshot_root": snapshot.parent_snapshot_root,
        "parent_head_root": parent_head_root,
        "current_epoch": snapshot.current_epoch,
        "current_step": snapshot.current_step,
        "lane_state_root": snapshot.state.state_root,
        "lane_state_material": _lane_state_material(snapshot.state),
        "dependencies": [item.to_dict() for item in snapshot.dependencies],
        "dependency_set_root": snapshot.dependency_set_root,
        "reason_codes": list(snapshot.reason_codes),
        "source_context_root": snapshot.source_context_root,
        "snapshot_state_root": snapshot.snapshot_state_root,
        "snapshot_root": snapshot.snapshot_root,
        "parent_history_root": snapshot.parent_history_root,
        "parent_history_count": snapshot.parent_history_count,
        "history_root": snapshot.history_root,
        "history_count": snapshot.history_count,
        "read_set_root": read_set_root,
        "mutation_issuer_ref": snapshot.mutation_issuer_ref,
        "grant_ref": binding["grant_ref"],
        "grant_root": binding["grant_root"],
        "grant_binding_ref": binding["grant_binding_ref"],
        "operation": binding["operation"],
        "session_binding": binding,
    }
    return TraceEvent(
        event_type=_event_type(snapshot.lane, snapshot.mutation_kind),
        protocol_id="pheroos.protocol.v2",
        target=snapshot.target_ref,
        reason="atomically advance durable Distributed Commit v2 authority",
        lineage=lineage,
    )


def _event_type(
    lane: DistributedLaneV2,
    mutation: DistributedMutationKindV2,
) -> str:
    if mutation is DistributedMutationKindV2.EQUIVOCATION_FROZEN:
        return "distributed_witness_conflict_v2"
    if mutation is DistributedMutationKindV2.CERTIFICATE_CONFLICT_FROZEN:
        return "distributed_certificate_conflict_v2"
    return f"distributed_{lane.value}_advanced_v2"


def _lane_state_material(state: object) -> dict[str, object]:
    if type(state) is DistributedEpochStateV2:
        return {
            "transition_certificate_root": state.transition_certificate.certificate_root,
            "conflict_history_roots": list(state.conflict_history_roots),
        }
    if type(state) is DistributedProposalStateV2:
        return {
            "epoch": state.epoch,
            "proposal_digests": [item.proposal_digest for item in state.proposals],
        }
    if type(state) is DistributedWitnessStateV2:
        return {
            "epoch": state.epoch,
            "witness_roots": [item.witness_root for item in state.witnesses],
            "finding_roots": [item.finding_root for item in state.equivocations],
        }
    if type(state) is DistributedCertificateStateV2:
        return {
            "epoch": state.epoch,
            "certificate_roots": [item.certificate_root for item in state.certificates],
            "conflict_roots": list(state.conflict_roots),
        }
    raise TypeError("distributed Trace lane state is invalid")


__all__: tuple[str, ...] = ()
