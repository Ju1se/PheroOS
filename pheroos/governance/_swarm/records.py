from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field
from pheroos.governance.layer_coordination import LayerCoordinationState
from pheroos.governance._pheromone.lifecycle import PheromoneBudgetState
from pheroos.governance._pheromone.records import (
    PheromoneExplorationObservation,
    PheromoneLifecycleRecord,
    PheromoneTrail,
)
from pheroos.governance.policy_adjustment import RunScopedPolicyOverlay
from pheroos.governance.quorum import QuorumDecision
from pheroos.protocol.models import CollectiveDecisionPolicy
from pheroos.trace import TraceEvent
from types import MappingProxyType
from typing import Any

@dataclass(frozen=True)
class CollectiveDecisionState:
    scores: dict[str, float] = field(default_factory=dict)
    independent_scouts: dict[str, set[str]] = field(default_factory=dict)
    pheromone_source_diversity: dict[str, int] = field(default_factory=dict)
    score_breakdown: dict[str, dict[str, float]] = field(default_factory=dict)
    layer_coordination: LayerCoordinationState | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "scores", MappingProxyType(dict(self.scores)))
        object.__setattr__(
            self,
            "independent_scouts",
            MappingProxyType(
                {
                    candidate_id: frozenset(source_ids)
                    for candidate_id, source_ids in self.independent_scouts.items()
                }
            ),
        )
        object.__setattr__(
            self,
            "pheromone_source_diversity",
            MappingProxyType(dict(self.pheromone_source_diversity)),
        )
        object.__setattr__(
            self,
            "score_breakdown",
            MappingProxyType(
                {
                    candidate_id: MappingProxyType(dict(categories))
                    for candidate_id, categories in self.score_breakdown.items()
                }
            ),
        )
        object.__setattr__(self, "layer_coordination", deepcopy(self.layer_coordination))

    def __deepcopy__(self, memo: dict[int, object]) -> CollectiveDecisionState:
        del memo
        return self


@dataclass(frozen=True)
class CollectiveDecisionStep:
    decision: QuorumDecision
    state: CollectiveDecisionState
    pheromone_trails: list[PheromoneTrail] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pheromone_trails", tuple(deepcopy(self.pheromone_trails)))


@dataclass(frozen=True)
class HybridCollectiveStep:
    decision: QuorumDecision
    state: CollectiveDecisionState
    active_trails: tuple[PheromoneTrail, ...]
    layer_coordination: LayerCoordinationState
    adjustment_overlay: RunScopedPolicyOverlay
    effective_policy: CollectiveDecisionPolicy
    deposit_records: tuple[PheromoneLifecycleRecord, ...] = ()
    evaporation_records: tuple[PheromoneLifecycleRecord, ...] = ()
    diffusion_records: tuple[PheromoneLifecycleRecord, ...] = ()
    reinforcement_records: tuple[PheromoneLifecycleRecord, ...] = ()
    exploration_observations: tuple[PheromoneExplorationObservation, ...] = ()
    processed_pheromone_event_ids: frozenset[str] = frozenset()
    processed_feedback_ids: frozenset[str] = frozenset()
    processed_adjustment_ids: frozenset[str] = frozenset()
    deposit_replay_receipts: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    diffusion_replay_receipts: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    feedback_replay_receipts: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    adjustment_replay_receipts: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    budget_state: PheromoneBudgetState | None = None
    trace_events: tuple[TraceEvent, ...] = ()
    _issuance: object | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        for field_name in (
            "active_trails",
            "deposit_records",
            "evaporation_records",
            "diffusion_records",
            "reinforcement_records",
            "exploration_observations",
            "trace_events",
        ):
            object.__setattr__(self, field_name, tuple(deepcopy(getattr(self, field_name))))
        object.__setattr__(
            self,
            "processed_pheromone_event_ids",
            frozenset(self.processed_pheromone_event_ids),
        )
        object.__setattr__(self, "processed_feedback_ids", frozenset(self.processed_feedback_ids))
        object.__setattr__(self, "processed_adjustment_ids", frozenset(self.processed_adjustment_ids))
        for field_name in (
            "deposit_replay_receipts",
            "diffusion_replay_receipts",
            "feedback_replay_receipts",
            "adjustment_replay_receipts",
        ):
            object.__setattr__(
                self,
                field_name,
                _freeze_replay_receipts(getattr(self, field_name)),
            )


_HYBRID_STEP_ISSUANCE = object()


_HYBRID_REPLAY_STATE_ISSUANCE = object()


@dataclass(frozen=True)
class HybridReplayState:
    protocol_id: str
    target: str
    active_trails: tuple[PheromoneTrail, ...] = ()
    processed_pheromone_event_ids: frozenset[str] = frozenset()
    processed_feedback_ids: frozenset[str] = frozenset()
    processed_adjustment_ids: frozenset[str] = frozenset()
    deposit_replay_receipts: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    diffusion_replay_receipts: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    feedback_replay_receipts: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    adjustment_replay_receipts: dict[str, tuple[Any, ...]] = field(default_factory=dict)
    _issuance: object | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "active_trails", tuple(deepcopy(self.active_trails)))
        object.__setattr__(
            self,
            "processed_pheromone_event_ids",
            frozenset(self.processed_pheromone_event_ids),
        )
        object.__setattr__(self, "processed_feedback_ids", frozenset(self.processed_feedback_ids))
        object.__setattr__(self, "processed_adjustment_ids", frozenset(self.processed_adjustment_ids))
        for field_name in (
            "deposit_replay_receipts",
            "diffusion_replay_receipts",
            "feedback_replay_receipts",
            "adjustment_replay_receipts",
        ):
            object.__setattr__(
                self,
                field_name,
                _freeze_replay_receipts(getattr(self, field_name)),
            )


def _freeze_replay_receipts(
    receipts: Mapping[str, tuple[Any, ...]],
) -> MappingProxyType:
    return MappingProxyType(
        {
            trace_event_id: tuple(deepcopy(fingerprint))
            for trace_event_id, fingerprint in receipts.items()
        }
    )


for _compat_function in (_freeze_replay_receipts,):
    _compat_function.__module__ = 'pheroos.governance.collective'
del _compat_function
for _compat_type in (CollectiveDecisionState, CollectiveDecisionStep, HybridCollectiveStep, HybridReplayState,):
    _compat_type.__module__ = 'pheroos.governance.collective'
    for _compat_descriptor in _compat_type.__dict__.values():
        if isinstance(_compat_descriptor, (staticmethod, classmethod)):
            _compat_member = _compat_descriptor.__func__
        else:
            _compat_member = _compat_descriptor
        if callable(_compat_member) and hasattr(_compat_member, '__module__'):
            _compat_member.__module__ = 'pheroos.governance.collective'
del _compat_descriptor, _compat_member, _compat_type

__all__ = ('CollectiveDecisionState', 'CollectiveDecisionStep', 'HybridCollectiveStep', 'HybridReplayState', '_HYBRID_REPLAY_STATE_ISSUANCE', '_HYBRID_STEP_ISSUANCE', '_freeze_replay_receipts')
