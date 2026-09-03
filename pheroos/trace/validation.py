"""Static Trace ABI catalog and public lineage dispatch.

The catalog depends on immutable contract declarations.  Contract validators
depend only on ``_validation_core`` so no private module imports this aggregate
facade back into the dependency graph.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from pheroos.trace._contracts.base import (
    BASE_TRACE_EVENT_CONTRACTS,
    TraceEventContract,
    contract_map,
)
from pheroos.trace._contracts.authority import AUTHORITY_TRACE_EVENT_CONTRACTS
from pheroos.trace._contracts.commit_gate_authority import (
    COMMIT_GATE_AUTHORITY_TRACE_EVENT_CONTRACTS,
)
from pheroos.trace._contracts.commit_certificate_authority import (
    COMMIT_CERTIFICATE_AUTHORITY_TRACE_EVENT_CONTRACTS,
)
from pheroos.trace._contracts.commit_decision_authority import (
    COMMIT_DECISION_AUTHORITY_TRACE_EVENT_CONTRACTS,
)
from pheroos.trace._contracts.commit_evidence_authority import (
    COMMIT_EVIDENCE_AUTHORITY_TRACE_EVENT_CONTRACTS,
)
from pheroos.trace._contracts.durable_authority import (
    DURABLE_AUTHORITY_TRACE_EVENT_CONTRACTS,
)
from pheroos.trace._contracts.distributed_authority import (
    DISTRIBUTED_AUTHORITY_TRACE_EVENT_CONTRACTS,
)
from pheroos.trace._contracts.layer import LAYER_TRACE_EVENT_CONTRACTS
from pheroos.trace._contracts.membership_authority import (
    MEMBERSHIP_AUTHORITY_TRACE_EVENT_CONTRACTS,
)
from pheroos.trace._contracts.pheromone import PHEROMONE_TRACE_EVENT_CONTRACTS
from pheroos.trace._contracts.support_authority import (
    SUPPORT_AUTHORITY_TRACE_EVENT_CONTRACTS,
)
from pheroos.trace._validation_core import (
    DECLARED_COORDINATION_LAYER_IDS as DECLARED_COORDINATION_LAYER_IDS,
    EXTENSION_EVENT_PREFIXES as EXTENSION_EVENT_PREFIXES,
    LAYER_SNAPSHOT_FIELDS as LAYER_SNAPSHOT_FIELDS,
    PHEROMONE_CLIP_PAYLOAD_VERSION as PHEROMONE_CLIP_PAYLOAD_VERSION,
    TraceEventView,
    canonical_pheromone_clip_payload as canonical_pheromone_clip_payload,
    pheromone_clip_payload_fingerprint as pheromone_clip_payload_fingerprint,
)


# ``event`` installs the canonical class after importing this module.  The
# structural default keeps this module independent from the public model while
# retaining the historical ``TraceEvent`` annotation and type-hint behavior.
TraceEvent = TraceEventView


# The complete built-in event set is assembled once from immutable domain
# declarations.  There is intentionally no registration API.
TRACE_EVENT_CONTRACTS: tuple[TraceEventContract, ...] = (
    *BASE_TRACE_EVENT_CONTRACTS,
    *AUTHORITY_TRACE_EVENT_CONTRACTS,
    *DURABLE_AUTHORITY_TRACE_EVENT_CONTRACTS,
    *COMMIT_GATE_AUTHORITY_TRACE_EVENT_CONTRACTS,
    *COMMIT_DECISION_AUTHORITY_TRACE_EVENT_CONTRACTS,
    *COMMIT_EVIDENCE_AUTHORITY_TRACE_EVENT_CONTRACTS,
    *COMMIT_CERTIFICATE_AUTHORITY_TRACE_EVENT_CONTRACTS,
    *DISTRIBUTED_AUTHORITY_TRACE_EVENT_CONTRACTS,
    *MEMBERSHIP_AUTHORITY_TRACE_EVENT_CONTRACTS,
    *SUPPORT_AUTHORITY_TRACE_EVENT_CONTRACTS,
    *PHEROMONE_TRACE_EVENT_CONTRACTS,
    *LAYER_TRACE_EVENT_CONTRACTS,
)
_TRACE_EVENT_CONTRACTS_BY_TYPE: Mapping[str, TraceEventContract] = MappingProxyType(
    dict(contract_map(TRACE_EVENT_CONTRACTS))
)
VALID_EVENT_TYPES = frozenset(_TRACE_EVENT_CONTRACTS_BY_TYPE)
EVENT_LINEAGE_CONTRACTS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        contract.event_type: contract.required_fields
        for contract in TRACE_EVENT_CONTRACTS
        if contract.schema_condition
    }
)


def is_extension_event_type(event_type: str) -> bool:
    return any(
        event_type.startswith(prefix) and len(event_type) > len(prefix)
        for prefix in EXTENSION_EVENT_PREFIXES
    )


def required_lineage_fields(event_type: str) -> frozenset[str]:
    """Return the canonical required lineage keys for a built-in event."""

    return EVENT_LINEAGE_CONTRACTS.get(event_type, frozenset())


def validate_event_lineage(event: TraceEvent) -> None:
    """Validate lineage through the immutable built-in contract map.

    Namespaced extension events remain non-authoritative and open.  Every
    built-in must have an immutable declaration; a missing declaration fails
    closed instead of silently turning an authority event into metadata.
    """

    if not isinstance(event.lineage, dict):
        raise ValueError("trace event lineage must be an object")
    if is_extension_event_type(event.event_type):
        return
    contract = _TRACE_EVENT_CONTRACTS_BY_TYPE.get(event.event_type)
    if contract is None:
        raise ValueError(f"unsupported trace event type: {event.event_type}")
    contract.validator(event)


# Preserve the historical package-root identity of public callables.  The
# facade binds these same objects; no wrapper layer changes signatures.
is_extension_event_type.__module__ = "pheroos.trace"
required_lineage_fields.__module__ = "pheroos.trace"
validate_event_lineage.__module__ = "pheroos.trace"


__all__: tuple[str, ...] = ()
