"""Canonical Trace ABI facade.

The package root intentionally contains no event-specific policy.  Immutable
built-in contracts live under ``_contracts``; event, store, and validation
implementations remain independently importable while these bindings preserve
the v1 public and pickle identities.
"""

from collections.abc import Mapping  # noqa: F401 - historical type-hint globals
from types import MappingProxyType
from typing import Any, Iterable  # noqa: F401 - historical type-hint globals

from pheroos.trace.commit_contracts import (
    COMMIT_EVENT_TYPES,
    COMMIT_TRACE_EVENT_SCHEMA,
    COMMIT_TRACE_PAYLOAD_VERSION,
    CommitTraceReplay,
    commit_trace_event_id,
    replay_commit_trace,
)
from pheroos.trace.event import (
    TraceEvent as _TraceEvent,
    make_commit_trace_event as _make_commit_trace_event,
)
from pheroos.trace.scoped import (
    SCOPED_TRACE_EVENT_SCHEMA_ID,
    SCOPED_TRACE_EVENT_VERSION,
    ScopedTraceEvent,
    scoped_trace_event_schema,
)
from pheroos.trace.store import (
    InMemoryTraceStore as _InMemoryTraceStore,
    TraceRecord as _TraceRecord,
    missing_required_events as _missing_required_events,
)
from pheroos.trace.validation import (
    DECLARED_COORDINATION_LAYER_IDS as _DECLARED_COORDINATION_LAYER_IDS,
    EVENT_LINEAGE_CONTRACTS as _EVENT_LINEAGE_CONTRACTS,
    EXTENSION_EVENT_PREFIXES as _EXTENSION_EVENT_PREFIXES,
    LAYER_SNAPSHOT_FIELDS as _LAYER_SNAPSHOT_FIELDS,
    PHEROMONE_CLIP_PAYLOAD_VERSION as _PHEROMONE_CLIP_PAYLOAD_VERSION,
    VALID_EVENT_TYPES as _VALID_EVENT_TYPES,
    canonical_pheromone_clip_payload as _canonical_pheromone_clip_payload,
    is_extension_event_type as _is_extension_event_type,
    pheromone_clip_payload_fingerprint as _pheromone_clip_payload_fingerprint,
    required_lineage_fields as _required_lineage_fields,
    validate_event_lineage as _validate_event_lineage,
)


# Direct facade assignments keep historical binding ownership and object
# identity for inspect, pickle, ``from`` and star imports.
TraceEvent = _TraceEvent
TraceRecord = _TraceRecord
InMemoryTraceStore = _InMemoryTraceStore
make_commit_trace_event = _make_commit_trace_event
missing_required_events = _missing_required_events
canonical_pheromone_clip_payload = _canonical_pheromone_clip_payload
pheromone_clip_payload_fingerprint = _pheromone_clip_payload_fingerprint
is_extension_event_type = _is_extension_event_type
required_lineage_fields = _required_lineage_fields
validate_event_lineage = _validate_event_lineage

# Materialize the three historical package-owned constants here so static ABI
# inventory continues to attribute them to ``pheroos.trace``.
EVENT_LINEAGE_CONTRACTS = MappingProxyType(dict(_EVENT_LINEAGE_CONTRACTS))
EXTENSION_EVENT_PREFIXES = tuple(_EXTENSION_EVENT_PREFIXES)
PHEROMONE_CLIP_PAYLOAD_VERSION = str(_PHEROMONE_CLIP_PAYLOAD_VERSION)
VALID_EVENT_TYPES = frozenset(_VALID_EVENT_TYPES)
# Private schema-builder compatibility bindings.  They intentionally remain
# outside ``__all__`` as before.
DECLARED_COORDINATION_LAYER_IDS = frozenset(_DECLARED_COORDINATION_LAYER_IDS)
LAYER_SNAPSHOT_FIELDS = frozenset(_LAYER_SNAPSHOT_FIELDS)


__all__ = [
    "COMMIT_EVENT_TYPES",
    "COMMIT_TRACE_EVENT_SCHEMA",
    "COMMIT_TRACE_PAYLOAD_VERSION",
    "CommitTraceReplay",
    "EVENT_LINEAGE_CONTRACTS",
    "PHEROMONE_CLIP_PAYLOAD_VERSION",
    "SCOPED_TRACE_EVENT_SCHEMA_ID",
    "SCOPED_TRACE_EVENT_VERSION",
    "InMemoryTraceStore",
    "TraceEvent",
    "TraceRecord",
    "ScopedTraceEvent",
    "EXTENSION_EVENT_PREFIXES",
    "VALID_EVENT_TYPES",
    "canonical_pheromone_clip_payload",
    "commit_trace_event_id",
    "is_extension_event_type",
    "make_commit_trace_event",
    "missing_required_events",
    "pheromone_clip_payload_fingerprint",
    "required_lineage_fields",
    "scoped_trace_event_schema",
    "replay_commit_trace",
    "validate_event_lineage",
]
