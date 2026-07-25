from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable, cast

import pheroos.trace.validation as _validation
from pheroos.trace.commit_contracts import build_commit_trace_lineage
from pheroos.trace.validation import (
    VALID_EVENT_TYPES,
    is_extension_event_type,
    validate_event_lineage,
)


@dataclass(frozen=True)
class TraceEvent:
    event_type: str
    protocol_id: str
    target: str
    reason: str
    lineage: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # A frozen dataclass does not freeze nested containers.  Snapshot the
        # caller-owned input so validation cannot be invalidated by later
        # mutation of the original dictionary.
        object.__setattr__(self, "lineage", deepcopy(self.lineage))

    def validate(self) -> None:
        if self.event_type not in VALID_EVENT_TYPES and not is_extension_event_type(
            self.event_type
        ):
            raise ValueError(f"unsupported trace event type: {self.event_type}")
        if not isinstance(self.protocol_id, str) or not self.protocol_id.strip():
            raise ValueError("trace event protocol_id is required")
        if not isinstance(self.target, str) or not self.target.strip():
            raise ValueError("trace event target is required")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("trace event reason is required")
        validate_event_lineage(self)


def make_commit_trace_event(
    *,
    event_type: str,
    protocol_id: str,
    target: str,
    reason: str,
    profile: str,
    assurance: str,
    manifest_root: str,
    commit_policy_root: str,
    run_id: str,
    epoch: int,
    step: int,
    record_schema: str,
    record_payload: Mapping[str, Any],
    previous_event_ids: Iterable[str] = (),
    details: Mapping[str, Any],
    extensions: Mapping[str, Any] | None = None,
) -> TraceEvent:
    """Build and validate one canonical commit-specific Trace ABI event."""

    event = TraceEvent(
        event_type=event_type,
        protocol_id=protocol_id,
        target=target,
        reason=reason,
        lineage=build_commit_trace_lineage(
            event_type=event_type,
            protocol_id=protocol_id,
            target=target,
            reason=reason,
            profile=profile,
            assurance=assurance,
            manifest_root=manifest_root,
            commit_policy_root=commit_policy_root,
            run_id=run_id,
            epoch=epoch,
            step=step,
            record_schema=record_schema,
            record_payload=record_payload,
            previous_event_ids=previous_event_ids,
            details=details,
            extensions=extensions,
        ),
    )
    event.validate()
    return event


# TraceEvent was historically defined by the package root.  Preserve its
# canonical import/pickle identity while keeping the implementation modular.
TraceEvent.__module__ = "pheroos.trace"
make_commit_trace_event.__module__ = "pheroos.trace"
# ``validate_event_lineage`` historically resolved this forward reference from
# the package-root globals.  Bind the canonical class for equivalent
# ``typing.get_type_hints`` behavior without making validation own the model.
_validation.TraceEvent = cast(Any, TraceEvent)


__all__: tuple[str, ...] = ()
