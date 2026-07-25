"""Canonical TraceEvent projections for Support v2 transitions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from pheroos.trace import TraceEvent

from pheroos.governance._authority_session_v2.operations import _portable_projection
from pheroos.governance._support_v2.support_state_contracts import (
    SupportAdvanceRequestV2,
    SupportMutationKindV2,
    support_event_lineage_v2,
    support_issued_event_lineage_v2,
    support_revoked_event_lineage_v2,
)


def _support_events(
    request: SupportAdvanceRequestV2,
    session_binding: Mapping[str, Any],
    *,
    source_context_root: str,
    source_verification_root: str,
    parent_head_root: str,
    read_set_root: str,
) -> tuple[TraceEvent, ...]:
    binding = cast(dict[str, object], _portable_projection(session_binding))
    events = [
        TraceEvent(
            event_type="support_state_advanced",
            protocol_id="pheroos.protocol.v2",
            target=request.target_ref,
            reason="atomically advance the unified durable Support v2 ledger",
            lineage=support_event_lineage_v2(
                request,
                session_binding=binding,
                source_context_root=source_context_root,
                source_verification_root=source_verification_root,
                parent_head_root=parent_head_root,
                read_set_root=read_set_root,
            ),
        )
    ]
    if request.mutation_kind in (
        SupportMutationKindV2.REVOKE,
        SupportMutationKindV2.SWITCH,
    ):
        events.append(
            TraceEvent(
                event_type="support_lease_revoked_v2",
                protocol_id="pheroos.protocol.v2",
                target=request.target_ref,
                reason="atomically revoke one verified active Support v2 lease",
                lineage=support_revoked_event_lineage_v2(
                    request,
                    session_binding=binding,
                    read_set_root=read_set_root,
                ),
            )
        )
    if request.mutation_kind in (
        SupportMutationKindV2.ISSUE,
        SupportMutationKindV2.SWITCH,
    ):
        events.append(
            TraceEvent(
                event_type="support_lease_issued_v2",
                protocol_id="pheroos.protocol.v2",
                target=request.target_ref,
                reason="atomically issue one verified durable Support v2 lease",
                lineage=support_issued_event_lineage_v2(
                    request,
                    session_binding=binding,
                    read_set_root=read_set_root,
                ),
            )
        )
    return tuple(events)


def _request_target_refs(request: SupportAdvanceRequestV2) -> tuple[str, ...]:
    return (request.target_ref,)


__all__: tuple[str, ...] = ()
