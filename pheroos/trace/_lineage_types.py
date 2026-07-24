from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Protocol

EXTENSION_EVENT_PREFIXES = ("x-", "ext.")
PHEROMONE_CLIP_PAYLOAD_VERSION = "pheroos-pheromone-clip-payload-v1"
DECLARED_COORDINATION_LAYER_IDS = frozenset(
    {"reactive", "learned", "evolutionary", "metacognitive"}
)
LAYER_SNAPSHOT_FIELDS = frozenset(
    {
        "present",
        "recent_success_rate",
        "recent_conflict_rate",
        "recent_fallback_rate",
        "mean_confidence",
        "evidence_coverage",
        "trace_coverage",
    }
)


if TYPE_CHECKING:

    class TraceEventView(Protocol):
        """Structural input owned below the public ``TraceEvent`` model."""

        @property
        def event_type(self) -> str: ...

        @property
        def protocol_id(self) -> str: ...

        @property
        def target(self) -> str: ...

        @property
        def reason(self) -> str: ...

        @property
        def lineage(self) -> dict[str, Any]: ...
else:

    class TraceEventView(Protocol):
        """Runtime placeholder for the static Trace event projection."""


TraceEventValidator = Callable[[TraceEventView], None]


__all__: tuple[str, ...] = ()
