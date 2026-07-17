from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pheroos.trace.commit_contracts import (
    COMMIT_EVENT_TYPES,
    commit_trace_required_fields,
)
from pheroos.trace._validation_core import (
    TraceEventValidator,
    build_declared_event_validator,
)


@dataclass(frozen=True, slots=True)
class TraceEventContract:
    """One immutable built-in event contract.

    ``schema_condition`` preserves the v1 distinction between authority/state
    lineage contracts and informational events.  Every built-in still has one
    runtime validator, while only the pre-existing lineage contracts are
    emitted into the v1 schema.
    """

    event_type: str
    required_fields: frozenset[str]
    validator: TraceEventValidator
    authority_relevant: bool
    schema_condition: bool

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, str) or not self.event_type:
            raise ValueError("trace event contract type must be non-empty text")
        if not isinstance(self.required_fields, frozenset) or any(
            not isinstance(field, str) or not field
            for field in self.required_fields
        ):
            raise TypeError("trace event contract fields must be a frozenset of text")
        if not callable(self.validator):
            raise TypeError("trace event contract requires exactly one validator")
        if self.required_fields and not self.schema_condition:
            raise ValueError("required lineage fields require a schema condition")


def _contract(
    event_type: str,
    *,
    required: frozenset[str] = frozenset(),
    authority_relevant: bool = False,
    schema_condition: bool = False,
) -> TraceEventContract:
    return TraceEventContract(
        event_type=event_type,
        required_fields=required,
        validator=build_declared_event_validator(
            required,
            schema_condition=schema_condition,
        ),
        authority_relevant=authority_relevant,
        schema_condition=schema_condition,
    )


# These informational v1 events deliberately keep their existing open lineage
# shape.  Their explicit declarations are what make the built-in set closed.
BASE_TRACE_EVENT_CONTRACTS: tuple[TraceEventContract, ...] = (
    *(
        _contract(event_type)
        for event_type in (
            "plan",
            "grant",
            "expose",
            "invoke",
            "evidence",
            "signal",
            "block",
            "recovery",
        )
    ),
    *(
        _contract(
            event_type,
            required=commit_trace_required_fields(event_type),
            authority_relevant=True,
            schema_condition=True,
        )
        for event_type in sorted(COMMIT_EVENT_TYPES)
    ),
)


def contract_map(
    contracts: tuple[TraceEventContract, ...],
) -> Mapping[str, TraceEventContract]:
    """Build a checked map during module initialization, never at runtime."""

    result: dict[str, TraceEventContract] = {}
    for contract in contracts:
        if contract.event_type in result:
            raise RuntimeError(
                f"duplicate static trace event contract: {contract.event_type}"
            )
        result[contract.event_type] = contract
    return result


__all__: tuple[str, ...] = ()
