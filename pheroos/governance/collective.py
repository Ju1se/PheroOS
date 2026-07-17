from __future__ import annotations

"""Compatibility facade for lifecycle-scoped governance implementations."""

# ruff: noqa: F401 -- owner-module globals support annotations and pickle.
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field, fields as dataclass_fields, is_dataclass, replace
from enum import Enum
import json
import math
from types import MappingProxyType
from typing import Any
from pheroos.governance._validation import is_nonblank_string
from pheroos.governance._legacy.hybrid_v1 import select_legacy_blended_decision
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
    PheromoneBudgetState,
    PheromoneBatchResult,
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
    scoreable_pheromone_candidate_id,
    score_pheromone_trails_result,
    score_pheromone_trails_with_breakdown,
    validate_pheromone_trail,
    validate_pheromone_subject_binding,
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
from typing import cast

from pheroos.governance._swarm.signals import InhibitionSignal as _compat_InhibitionSignal
from pheroos.governance._swarm.signals import RecruitmentSignal as _compat_RecruitmentSignal
from pheroos.governance._swarm.signals import ScoutReport as _compat_ScoutReport
from pheroos.governance._swarm.signals import require_finite_bounded_strength as _compat_require_finite_bounded_strength
from pheroos.governance._swarm.signals import require_finite_non_negative as _compat_require_finite_non_negative
from pheroos.governance._swarm.signals import validate_collective_signal as _compat_validate_collective_signal
from pheroos.governance._swarm.signals import validate_scout_report as _compat_validate_scout_report
from pheroos.governance._swarm.records import CollectiveDecisionState as _compat_CollectiveDecisionState
from pheroos.governance._swarm.records import CollectiveDecisionStep as _compat_CollectiveDecisionStep
from pheroos.governance._swarm.records import HybridCollectiveStep as _compat_HybridCollectiveStep
from pheroos.governance._swarm.records import HybridReplayState as _compat_HybridReplayState
from pheroos.governance._swarm.records import _HYBRID_REPLAY_STATE_ISSUANCE as _compat__HYBRID_REPLAY_STATE_ISSUANCE
from pheroos.governance._swarm.records import _HYBRID_STEP_ISSUANCE as _compat__HYBRID_STEP_ISSUANCE
from pheroos.governance._swarm.records import _freeze_replay_receipts as _compat__freeze_replay_receipts
from pheroos.governance._swarm.replay import _adjustment_replay_fingerprint as _compat__adjustment_replay_fingerprint
from pheroos.governance._swarm.replay import _canonical_authority_value as _compat__canonical_authority_value
from pheroos.governance._swarm.replay import _canonical_replay_value as _compat__canonical_replay_value
from pheroos.governance._swarm.replay import _extend_replay_receipts as _compat__extend_replay_receipts
from pheroos.governance._swarm.replay import _feedback_replay_fingerprint as _compat__feedback_replay_fingerprint
from pheroos.governance._swarm.replay import _hybrid_authority_snapshot as _compat__hybrid_authority_snapshot
from pheroos.governance._swarm.replay import _hybrid_step_bindings_match as _compat__hybrid_step_bindings_match
from pheroos.governance._swarm.replay import _issue_hybrid_collective_step as _compat__issue_hybrid_collective_step
from pheroos.governance._swarm.replay import _replay_receipts_match_processed_ids as _compat__replay_receipts_match_processed_ids
from pheroos.governance._swarm.replay import _trail_replay_fingerprint as _compat__trail_replay_fingerprint
from pheroos.governance._swarm.replay import _validate_complete_hybrid_trace_identity as _compat__validate_complete_hybrid_trace_identity
from pheroos.governance._swarm.replay import _validate_replay_receipts as _compat__validate_replay_receipts
from pheroos.governance._swarm.replay import hybrid_collective_step_is_authoritative as _compat_hybrid_collective_step_is_authoritative
from pheroos.governance._swarm.replay import hybrid_replay_state_is_authoritative as _compat_hybrid_replay_state_is_authoritative
from pheroos.governance._swarm.replay import replay_state_from_hybrid_step as _compat_replay_state_from_hybrid_step
from pheroos.governance._swarm.scoring import candidate_score_lineage as _compat_candidate_score_lineage
from pheroos.governance._swarm.scoring import merge_candidate_breakdown as _compat_merge_candidate_breakdown
from pheroos.governance._swarm.scoring import score_candidates as _compat_score_candidates
from pheroos.governance._swarm.scoring import validate_score_breakdown as _compat_validate_score_breakdown
from pheroos.governance._swarm.trace import _clip_causal_lineage as _compat__clip_causal_lineage
from pheroos.governance._swarm.trace import _hybrid_step_trace_events as _compat__hybrid_step_trace_events
from pheroos.governance._swarm.trace import _input_trace_events as _compat__input_trace_events
from pheroos.governance._swarm.trace import _pheromone_lifecycle_trace_events as _compat__pheromone_lifecycle_trace_events
from pheroos.governance._swarm.trace import _replay_receipt_digest as _compat__replay_receipt_digest
from pheroos.governance._swarm.trace import _replay_receipt_trace_payload as _compat__replay_receipt_trace_payload
from pheroos.governance._swarm.trace import _trace_event as _compat__trace_event
from pheroos.governance._swarm.pipeline import _decide_collective_state as _compat__decide_collective_state
from pheroos.governance._swarm.pipeline import evaluate_collective_decision as _compat_evaluate_collective_decision
from pheroos.governance._swarm.pipeline import evaluate_collective_decision_step as _compat_evaluate_collective_decision_step
from pheroos.governance._swarm.pipeline import evaluate_hybrid_collective_step as _compat_evaluate_hybrid_collective_step
from pheroos.governance._swarm.pipeline import merge_governed_layer_coordination as _compat_merge_governed_layer_coordination

ScoutReport = cast(Any, _compat_ScoutReport)
RecruitmentSignal = cast(Any, _compat_RecruitmentSignal)
InhibitionSignal = cast(Any, _compat_InhibitionSignal)
CollectiveDecisionState = cast(Any, _compat_CollectiveDecisionState)
CollectiveDecisionStep = cast(Any, _compat_CollectiveDecisionStep)
HybridCollectiveStep = cast(Any, _compat_HybridCollectiveStep)
_HYBRID_STEP_ISSUANCE = cast(Any, _compat__HYBRID_STEP_ISSUANCE)
_HYBRID_REPLAY_STATE_ISSUANCE = cast(Any, _compat__HYBRID_REPLAY_STATE_ISSUANCE)
HybridReplayState = cast(Any, _compat_HybridReplayState)
_canonical_authority_value = cast(Any, _compat__canonical_authority_value)
_hybrid_authority_snapshot = cast(Any, _compat__hybrid_authority_snapshot)
_hybrid_step_bindings_match = cast(Any, _compat__hybrid_step_bindings_match)
_issue_hybrid_collective_step = cast(Any, _compat__issue_hybrid_collective_step)
hybrid_collective_step_is_authoritative = cast(Any, _compat_hybrid_collective_step_is_authoritative)
replay_state_from_hybrid_step = cast(Any, _compat_replay_state_from_hybrid_step)
hybrid_replay_state_is_authoritative = cast(Any, _compat_hybrid_replay_state_is_authoritative)
_freeze_replay_receipts = cast(Any, _compat__freeze_replay_receipts)
_replay_receipts_match_processed_ids = cast(Any, _compat__replay_receipts_match_processed_ids)
_canonical_replay_value = cast(Any, _compat__canonical_replay_value)
_trail_replay_fingerprint = cast(Any, _compat__trail_replay_fingerprint)
_feedback_replay_fingerprint = cast(Any, _compat__feedback_replay_fingerprint)
_adjustment_replay_fingerprint = cast(Any, _compat__adjustment_replay_fingerprint)
_validate_replay_receipts = cast(Any, _compat__validate_replay_receipts)
_extend_replay_receipts = cast(Any, _compat__extend_replay_receipts)
_validate_complete_hybrid_trace_identity = cast(Any, _compat__validate_complete_hybrid_trace_identity)
score_candidates = cast(Any, _compat_score_candidates)
validate_scout_report = cast(Any, _compat_validate_scout_report)
validate_collective_signal = cast(Any, _compat_validate_collective_signal)
require_finite_non_negative = cast(Any, _compat_require_finite_non_negative)
require_finite_bounded_strength = cast(Any, _compat_require_finite_bounded_strength)
_trace_event = cast(Any, _compat__trace_event)
_input_trace_events = cast(Any, _compat__input_trace_events)
_clip_causal_lineage = cast(Any, _compat__clip_causal_lineage)
_pheromone_lifecycle_trace_events = cast(Any, _compat__pheromone_lifecycle_trace_events)
_replay_receipt_digest = cast(Any, _compat__replay_receipt_digest)
_replay_receipt_trace_payload = cast(Any, _compat__replay_receipt_trace_payload)
_hybrid_step_trace_events = cast(Any, _compat__hybrid_step_trace_events)
merge_candidate_breakdown = cast(Any, _compat_merge_candidate_breakdown)
merge_governed_layer_coordination = cast(Any, _compat_merge_governed_layer_coordination)
validate_score_breakdown = cast(Any, _compat_validate_score_breakdown)
candidate_score_lineage = cast(Any, _compat_candidate_score_lineage)
evaluate_collective_decision = cast(Any, _compat_evaluate_collective_decision)
evaluate_collective_decision_step = cast(Any, _compat_evaluate_collective_decision_step)
evaluate_hybrid_collective_step = cast(Any, _compat_evaluate_hybrid_collective_step)
_decide_collective_state = cast(Any, _compat__decide_collective_state)

del _compat_CollectiveDecisionState, _compat_CollectiveDecisionStep, _compat_HybridCollectiveStep, _compat_HybridReplayState, _compat_InhibitionSignal, _compat_RecruitmentSignal, _compat_ScoutReport, _compat__HYBRID_REPLAY_STATE_ISSUANCE, _compat__HYBRID_STEP_ISSUANCE, _compat__adjustment_replay_fingerprint, _compat__canonical_authority_value, _compat__canonical_replay_value, _compat__clip_causal_lineage, _compat__decide_collective_state, _compat__extend_replay_receipts, _compat__feedback_replay_fingerprint, _compat__freeze_replay_receipts, _compat__hybrid_authority_snapshot, _compat__hybrid_step_bindings_match, _compat__hybrid_step_trace_events, _compat__input_trace_events, _compat__issue_hybrid_collective_step, _compat__pheromone_lifecycle_trace_events, _compat__replay_receipt_digest, _compat__replay_receipt_trace_payload, _compat__replay_receipts_match_processed_ids, _compat__trace_event, _compat__trail_replay_fingerprint, _compat__validate_complete_hybrid_trace_identity, _compat__validate_replay_receipts, _compat_candidate_score_lineage, _compat_evaluate_collective_decision, _compat_evaluate_collective_decision_step, _compat_evaluate_hybrid_collective_step, _compat_hybrid_collective_step_is_authoritative, _compat_hybrid_replay_state_is_authoritative, _compat_merge_candidate_breakdown, _compat_merge_governed_layer_coordination, _compat_replay_state_from_hybrid_step, _compat_require_finite_bounded_strength, _compat_require_finite_non_negative, _compat_score_candidates, _compat_validate_collective_signal, _compat_validate_score_breakdown, _compat_validate_scout_report
