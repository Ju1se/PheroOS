"""Compatibility facade for lifecycle-scoped governance implementations."""

from __future__ import annotations

# The private owner modules deliberately preserve the historical public
# ``__module__`` value for pickle and annotation compatibility.  These imports
# provide that public annotation namespace; wildcard imports are constrained by
# each owner module's explicit ``__all__`` contract.
# ruff: noqa: F401,F403
import json
import math
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import (
    dataclass,
    field,
    fields as dataclass_fields,
    is_dataclass,
    replace,
)
from enum import Enum
from types import MappingProxyType
from typing import Any

from pheroos.governance._legacy.hybrid_v1 import select_legacy_blended_decision
from pheroos.governance._validation import is_nonblank_string
from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.layer_coordination import (
    SUPPORTED_LAYER_IDS,
    LayerCoordinationState,
    LayerPerformanceSnapshot,
    LayerProposal,
    StrategyBias,
    evaluate_layer_coordination,
    layer_coordination_policy_from_collective,
    materialize_layer_pheromone_proposals,
)
from pheroos.governance.pheromone import (
    PheromoneBatchResult,
    PheromoneBudgetState,
    PheromoneExplorationObservation,
    PheromoneLifecycleRecord,
    PheromoneNeighborhood,
    PheromonePolicy,
    PheromoneTrail,
    add_breakdown,
    collect_pheromone_source_diversity,
    deposit_pheromone_trails,
    diffuse_pheromone_trails_with_records,
    diffusion_policy_from_collective,
    empty_score_breakdown,
    evaporate_trails,
    evaporate_trails_with_records,
    observe_pheromone_exploration,
    pheromone_bound_candidate_id,
    pheromone_policy_from_collective,
    pheromone_source_id,
    pheromone_subject_id,
    pheromone_subject_type,
    score_pheromone_trails_result,
    score_pheromone_trails_with_breakdown,
    scoreable_pheromone_candidate_id,
    validate_pheromone_subject_binding,
    validate_pheromone_trail,
)
from pheroos.governance.pheromone_feedback import (
    PheromoneFeedback,
    PheromoneReinforcementResult,
    reinforce_pheromone_trails_with_records,
)
from pheroos.governance.policy_adjustment import (
    PolicyAdjustmentBatchResult,
    PolicyAdjustmentProposal,
    RunScopedPolicyOverlay,
    apply_policy_adjustment_overlay,
    run_scoped_policy_overlay_is_authoritative,
    validate_policy_adjustment_proposals,
)
from pheroos.governance.quorum import (
    QuorumDecision,
    _issue_quorum_decision,
    quorum_decision_is_authoritative,
)
from pheroos.governance.runtime_policy import (
    resolve_collective_fallback_id,
    validate_collective_runtime_policy,
)
from pheroos.governance.signal import SignalVerification, signal_verification_matches
from pheroos.protocol.models import (
    SWARM_COLLECTIVE_MODES,
    CollectiveDecisionPolicy,
    thaw_protocol_value,
)
from pheroos.trace import (
    PHEROMONE_CLIP_PAYLOAD_VERSION,
    TraceEvent,
    pheromone_clip_payload_fingerprint,
)

from pheroos.governance._swarm.pipeline import *
from pheroos.governance._swarm.records import *
from pheroos.governance._swarm.replay import *
from pheroos.governance._swarm.scoring import *
from pheroos.governance._swarm.signals import *
from pheroos.governance._swarm.trace import *
