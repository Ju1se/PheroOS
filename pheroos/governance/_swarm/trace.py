from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.layer_coordination import LayerCoordinationState
from pheroos.governance.layer_coordination import LayerPerformanceSnapshot
from pheroos.governance.layer_coordination import LayerProposal
from pheroos.governance.layer_coordination import SUPPORTED_LAYER_IDS
from pheroos.governance.layer_coordination import StrategyBias
from pheroos.governance._pheromone.invariants import (
    pheromone_bound_candidate_id,
    pheromone_source_id,
    pheromone_subject_id,
    pheromone_subject_type,
)
from pheroos.governance._pheromone.lifecycle import PheromoneBatchResult
from pheroos.governance._pheromone.records import (
    PheromoneExplorationObservation,
    PheromoneLifecycleRecord,
    PheromonePolicy,
    PheromoneTrail,
)
from pheroos.governance._pheromone.scoring import score_pheromone_trails_result
from pheroos.governance.pheromone_feedback import PheromoneFeedback
from pheroos.governance.pheromone_feedback import PheromoneReinforcementResult
from pheroos.governance.policy_adjustment import PolicyAdjustmentBatchResult
from pheroos.governance.policy_adjustment import PolicyAdjustmentProposal
from pheroos.governance.quorum import QuorumDecision
from pheroos.protocol.models import CollectiveDecisionPolicy
from pheroos.protocol.models import thaw_protocol_value
from pheroos.trace import PHEROMONE_CLIP_PAYLOAD_VERSION
from pheroos.trace import TraceEvent
from pheroos.trace import pheromone_clip_payload_fingerprint
from typing import Any
import json
from pheroos.governance._swarm.records import CollectiveDecisionState
from pheroos.governance._swarm.replay import (
    _adjustment_replay_fingerprint,
    _canonical_replay_value,
    _feedback_replay_fingerprint,
    _trail_replay_fingerprint,
)
from pheroos.governance._swarm.signals import (
    InhibitionSignal,
    RecruitmentSignal,
    ScoutReport,
)


def _trace_event(
    event_type: str,
    *,
    protocol_id: str,
    target: str,
    reason: str,
    lineage: dict[str, Any] | None = None,
) -> TraceEvent:
    event = TraceEvent(
        event_type=event_type,
        protocol_id=protocol_id,
        target=target,
        reason=reason,
        lineage=lineage or {},
    )
    try:
        event.validate()
    except ValueError as exc:
        raise GovernanceError(f"invalid governance trace action: {exc}") from exc
    return event


def _input_trace_events(
    *,
    protocol_id: str,
    target: str,
    scout_reports: list[ScoutReport],
    recruitment_signals: list[RecruitmentSignal],
    inhibition_signals: list[InhibitionSignal],
) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    if scout_reports:
        events.append(
            _trace_event(
                "explore",
                protocol_id=protocol_id,
                target=target,
                reason="independent exploration produced scout reports",
                lineage={"scout_count": len(scout_reports)},
            )
        )
    for report in sorted(
        scout_reports,
        key=lambda item: (
            item.candidate_id,
            item.scout_id,
            item.evidence_id,
            item.trace_event_id,
        ),
    ):
        events.append(
            _trace_event(
                "scout_report",
                protocol_id=protocol_id,
                target=target,
                reason="governance-verified scout report accepted",
                lineage={
                    "scout_id": report.scout_id,
                    "candidate_id": report.candidate_id,
                    "evidence_id": report.evidence_id,
                    "provenance": report.provenance,
                    "support": report.support,
                    "source_trace_event_id": report.trace_event_id,
                    "verification_trace_event_id": (
                        report.verification.trace_event_id
                        if report.verification is not None
                        else ""
                    ),
                },
            )
        )
    signal_groups: tuple[
        tuple[str, Sequence[RecruitmentSignal | InhibitionSignal]],
        ...,
    ] = (
        ("recruit", recruitment_signals),
        ("inhibit", inhibition_signals),
    )
    for event_type, signals in signal_groups:
        for signal in sorted(
            signals,
            key=lambda item: (item.candidate_id, item.source_id, item.trace_event_id),
        ):
            events.append(
                _trace_event(
                    event_type,
                    protocol_id=protocol_id,
                    target=target,
                    reason=f"governance-verified {event_type} signal accepted",
                    lineage={
                        "source_id": signal.source_id,
                        "candidate_id": signal.candidate_id,
                        "strength": signal.strength,
                        "provenance": signal.provenance,
                        "source_trace_event_id": signal.trace_event_id,
                        "verification_trace_event_id": (
                            signal.verification.trace_event_id
                            if signal.verification is not None
                            else ""
                        ),
                    },
                )
            )
    return events


def _clip_causal_lineage(record: PheromoneLifecycleRecord) -> dict[str, Any]:
    if not record._causal_payload_json:
        raise GovernanceError(
            f"rejected pheromone lifecycle has no causal payload: {record.trace_event_id}"
        )
    try:
        envelope = json.loads(record._causal_payload_json)
    except (TypeError, ValueError) as exc:
        raise GovernanceError(
            "pheromone clip causal payload is not canonical JSON"
        ) from exc
    if (
        not isinstance(envelope, dict)
        or envelope.get("version") != PHEROMONE_CLIP_PAYLOAD_VERSION
        or not isinstance(envelope.get("payload"), dict)
    ):
        raise GovernanceError("pheromone clip causal payload envelope is invalid")
    payload = envelope["payload"]
    return {
        "causal_payload": payload,
        "causal_fingerprint": pheromone_clip_payload_fingerprint(payload),
    }


def _pheromone_lifecycle_trace_events(
    *,
    protocol_id: str,
    target: str,
    pheromone_policy: PheromonePolicy,
    deposit_records: tuple[PheromoneLifecycleRecord, ...],
    evaporation_records: tuple[PheromoneLifecycleRecord, ...],
    diffusion_records: tuple[PheromoneLifecycleRecord, ...],
    reinforcement_records: tuple[PheromoneLifecycleRecord, ...],
    pre_diffusion_trails: tuple[PheromoneTrail, ...],
    phase: str = "primary",
) -> list[TraceEvent]:
    events: list[TraceEvent] = []
    for record in deposit_records:
        if record.requested_strength != record.applied_strength:
            events.append(
                _trace_event(
                    "pheromone_clip",
                    protocol_id=protocol_id,
                    target=target,
                    reason="pheromone deposit was bounded by declared budgets",
                    lineage={
                        "lifecycle": "deposit",
                        "result": (
                            "applied" if record.applied_strength > 0 else "rejected"
                        ),
                        "source_id": record.source_id,
                        "provenance": record.provenance,
                        "candidate_id": record.candidate_id,
                        "subject_type": record.subject_type,
                        "subject_id": record.subject_id,
                        "kind": record.kind,
                        "source_kind": record.source_kind,
                        "source_strength": record.old_strength,
                        "new_strength": record.new_strength,
                        "step": record.step,
                        "source_trace_event_id": record.source_trace_event_id,
                        "trace_event_id": record.trace_event_id,
                        "requested_strength": record.requested_strength,
                        "applied_strength": record.applied_strength,
                        "round_budget_remaining": record.round_budget_remaining,
                        "source_budget_remaining": record.source_budget_remaining,
                        **_clip_causal_lineage(record),
                    },
                )
            )
        if record.new_strength == record.old_strength:
            continue
        events.append(
            _trace_event(
                "pheromone_deposit",
                protocol_id=protocol_id,
                target=target,
                reason="bounded pheromone deposit applied",
                lineage={
                    "source_id": record.source_id,
                    "provenance": record.provenance,
                    "subject_type": record.subject_type,
                    "subject_id": record.subject_id,
                    "candidate_id": record.candidate_id,
                    "kind": record.kind,
                    "source_kind": record.source_kind,
                    "source_strength": record.old_strength,
                    "old_strength": record.old_strength,
                    "requested_strength": record.requested_strength,
                    "applied_strength": record.applied_strength,
                    "new_strength": record.new_strength,
                    "round_budget_remaining": record.round_budget_remaining,
                    "source_budget_remaining": record.source_budget_remaining,
                    "step": record.step,
                    "deposited_at_step": record.deposited_at_step,
                    "updated_at_step": record.step,
                    "source_trace_event_id": record.source_trace_event_id,
                    "trace_event_id": record.trace_event_id,
                },
            )
        )

    for record in sorted(
        evaporation_records,
        key=lambda item: (
            item.trace_event_id,
            item.subject_type,
            item.subject_id,
            item.kind,
        ),
    ):
        if record.action == "expire":
            events.append(
                _trace_event(
                    "pheromone_expire",
                    protocol_id=protocol_id,
                    target=target,
                    reason="pheromone trail reached its declared TTL",
                    lineage={
                        "action": "expire",
                        "target": record.target,
                        "candidate_id": record.candidate_id,
                        "subject_type": record.subject_type,
                        "subject_id": record.subject_id,
                        "kind": record.kind,
                        "source_kind": record.source_kind,
                        "source_id": record.source_id,
                        "provenance": record.provenance,
                        "source_trace_event_id": record.source_trace_event_id,
                        "trace_event_id": record.trace_event_id,
                        "source_strength": record.old_strength,
                        "old_strength": record.old_strength,
                        "requested_strength": record.old_strength,
                        "applied_strength": record.new_strength,
                        "new_strength": record.new_strength,
                        "strength_delta": record.new_strength - record.old_strength,
                        "step": record.step,
                        "source_updated_at_step": record.step - record.elapsed_steps,
                        "deposited_at_step": record.deposited_at_step,
                        "ttl_steps": record.ttl_steps,
                        "elapsed_steps": record.elapsed_steps,
                        "phase": phase,
                    },
                )
            )
            continue
        profile = (
            f"kind:{record.kind}"
            if record.kind in pheromone_policy.kind_profiles
            else f"global:{pheromone_policy.decay_model}"
        )
        events.append(
            _trace_event(
                "pheromone_evaporate",
                protocol_id=protocol_id,
                target=target,
                reason="pheromone lifecycle advanced deterministically",
                lineage={
                    "source_id": record.source_id,
                    "provenance": record.provenance,
                    "subject_type": record.subject_type,
                    "subject_id": record.subject_id,
                    "kind": record.kind,
                    "source_kind": record.source_kind,
                    "source_strength": record.old_strength,
                    "old_strength": record.old_strength,
                    "requested_strength": record.old_strength,
                    "applied_strength": record.new_strength,
                    "new_strength": record.new_strength,
                    "strength_delta": record.new_strength - record.old_strength,
                    "elapsed_steps": record.elapsed_steps,
                    "step": record.step,
                    "source_updated_at_step": record.step - record.elapsed_steps,
                    "deposited_at_step": record.deposited_at_step,
                    "profile": profile,
                    "candidate_id": record.candidate_id,
                    "source_trace_event_id": record.source_trace_event_id,
                    "trace_event_id": record.trace_event_id,
                    "phase": phase,
                },
            )
        )

    source_trails = {trail.trace_event_id: trail for trail in pre_diffusion_trails}
    for record in diffusion_records:
        source = source_trails.get(record.source_trace_event_id)
        if source is None:
            raise GovernanceError(
                f"diffusion record has no source trail lineage: {record.source_trace_event_id}"
            )
        if record.action == "diffuse_rejected":
            events.append(
                _trace_event(
                    "pheromone_clip",
                    protocol_id=protocol_id,
                    target=target,
                    reason="pheromone diffusion was rejected by the shared budget",
                    lineage={
                        "lifecycle": "diffusion",
                        "result": "rejected",
                        "source_id": record.source_id,
                        "provenance": source.provenance,
                        "candidate_id": record.candidate_id,
                        "subject_type": record.subject_type,
                        "subject_id": record.subject_id,
                        "kind": record.kind,
                        "source_kind": source.kind,
                        "source_strength": source.strength,
                        "new_strength": 0.0,
                        "step": record.step,
                        "source_trace_event_id": record.source_trace_event_id,
                        "trace_event_id": record.trace_event_id,
                        "requested_strength": record.requested_strength,
                        "applied_strength": 0.0,
                        "round_budget_remaining": record.round_budget_remaining,
                        "source_budget_remaining": record.source_budget_remaining,
                        "source_subject": {
                            "type": pheromone_subject_type(source),
                            "id": pheromone_subject_id(source),
                        },
                        "target_subject": {
                            "type": record.subject_type,
                            "id": record.subject_id,
                        },
                        "root_trace_event_id": (
                            source.diffusion_root_trace_event_id
                            or source.trace_event_id
                        ),
                        "hop": record.hop,
                        "attenuation": record.attenuation,
                        "policy_attenuation": record.policy_attenuation,
                        "edge_attenuation": record.edge_attenuation,
                        **_clip_causal_lineage(record),
                    },
                )
            )
            continue
        events.append(
            _trace_event(
                "pheromone_diffuse",
                protocol_id=protocol_id,
                target=target,
                reason="pheromone diffused over a declared target-scoped edge",
                lineage={
                    "source_subject": {
                        "type": pheromone_subject_type(source),
                        "id": pheromone_subject_id(source),
                    },
                    "target_subject": {
                        "type": record.subject_type,
                        "id": record.subject_id,
                    },
                    "hop": record.hop,
                    "attenuation": record.attenuation,
                    "policy_attenuation": record.policy_attenuation,
                    "edge_attenuation": record.edge_attenuation,
                    "root_trace_event_id": (
                        source.diffusion_root_trace_event_id or source.trace_event_id
                    ),
                    "source_strength": source.strength,
                    "requested_strength": record.requested_strength,
                    "applied_strength": record.applied_strength,
                    "new_strength": record.new_strength,
                    "round_budget_remaining": record.round_budget_remaining,
                    "source_budget_remaining": record.source_budget_remaining,
                    "source_id": record.source_id,
                    "candidate_id": record.candidate_id,
                    "source_kind": source.kind,
                    "kind": record.kind,
                    "provenance": source.provenance,
                    "source_trace_event_id": record.source_trace_event_id,
                    "trace_event_id": record.trace_event_id,
                },
            )
        )
        source_trails[record.trace_event_id] = replace(
            source,
            candidate_id=record.candidate_id,
            strength=record.new_strength,
            subject_type=record.subject_type,
            subject_id=record.subject_id,
            trace_event_id=record.trace_event_id,
        )

    for record in reinforcement_records:
        if record.action == "reinforce_rejected":
            causal_lineage = _clip_causal_lineage(record)
            feedback_input = causal_lineage["causal_payload"]["input"]
            events.append(
                _trace_event(
                    "pheromone_clip",
                    protocol_id=protocol_id,
                    target=target,
                    reason="pheromone feedback was rejected by declared strength or budget bounds",
                    lineage={
                        "lifecycle": "feedback",
                        "result": "rejected",
                        "source_id": record.source_id,
                        "provenance": record.provenance,
                        "candidate_id": record.candidate_id,
                        "subject_type": record.subject_type,
                        "subject_id": record.subject_id,
                        "kind": record.kind,
                        "source_kind": record.source_kind,
                        "source_strength": record.old_strength,
                        "new_strength": record.new_strength,
                        "outcome": record.outcome,
                        "reward": record.reward,
                        "strength_delta": feedback_input["strength_delta"],
                        "step": record.step,
                        "source_trace_event_id": record.source_trace_event_id,
                        "feedback_trace_event_id": (
                            record.cause_trace_event_id or record.trace_event_id
                        ),
                        "trace_event_id": record.trace_event_id,
                        "requested_strength": record.requested_strength,
                        "applied_strength": 0.0,
                        "round_budget_remaining": record.round_budget_remaining,
                        "source_budget_remaining": record.source_budget_remaining,
                        **causal_lineage,
                    },
                )
            )
            continue
        status = "applied"
        events.append(
            _trace_event(
                "pheromone_reinforce",
                protocol_id=protocol_id,
                target=target,
                reason="outcome feedback updated bounded collective memory",
                lineage={
                    "feedback_source": record.source_id,
                    "source_id": record.source_id,
                    "outcome": record.outcome,
                    "reward": record.reward,
                    "delta": record.applied_strength,
                    "source_strength": record.old_strength,
                    "old_strength": record.old_strength,
                    "requested_strength": (
                        record.requested_strength
                        if record.applied_strength >= 0
                        else abs(record.applied_strength)
                    ),
                    "applied_strength": abs(record.applied_strength),
                    "new_strength": record.new_strength,
                    "candidate_id": record.candidate_id,
                    "subject_type": record.subject_type,
                    "subject_id": record.subject_id,
                    "source_kind": record.source_kind,
                    "kind": record.kind,
                    "provenance": record.provenance,
                    "budget_result": {
                        "round_remaining": record.round_budget_remaining,
                        "source_remaining": record.source_budget_remaining,
                        "status": status,
                    },
                    "step": record.step,
                    "source_trace_event_id": record.source_trace_event_id,
                    "feedback_trace_event_id": (
                        record.cause_trace_event_id or record.trace_event_id
                    ),
                    "trace_event_id": record.trace_event_id,
                },
            )
        )
    return events


def _replay_receipt_digest(receipt: tuple[Any, ...]) -> str:
    return pheromone_clip_payload_fingerprint(
        {
            "lifecycle": "replay_receipt",
            "receipt": _canonical_replay_value(receipt),
        }
    )


def _replay_receipt_trace_payload(receipt: tuple[Any, ...]) -> list[Any]:
    """Expose the complete provider-neutral replay receipt for trace replay.

    Trace validation and conformance must be able to recompute the current
    payload digest instead of trusting two caller-controlled digest strings.
    The canonical replay value owns no governance objects, and TraceEvent takes
    a defensive lineage snapshot before the event leaves governance.
    """

    return list(_canonical_replay_value(receipt))


def _hybrid_step_trace_events(
    *,
    protocol_id: str,
    target: str,
    candidate_set: CandidateSet,
    policy: CollectiveDecisionPolicy,
    pheromone_policy: PheromonePolicy,
    scout_reports: list[ScoutReport],
    recruitment_signals: list[RecruitmentSignal],
    inhibition_signals: list[InhibitionSignal],
    deposit_inputs: list[PheromoneTrail],
    deposit_result: PheromoneBatchResult,
    deposit_replay_receipts: Mapping[str, tuple[Any, ...]],
    diffusion_replay_receipts: Mapping[str, tuple[Any, ...]],
    feedback_replay_receipts: Mapping[str, tuple[Any, ...]],
    adjustment_replay_receipts: Mapping[str, tuple[Any, ...]],
    evaporation_records: tuple[PheromoneLifecycleRecord, ...],
    pre_diffusion_trails: tuple[PheromoneTrail, ...],
    diffusion_result: PheromoneBatchResult,
    feedback: list[PheromoneFeedback],
    reinforcement_result: PheromoneReinforcementResult,
    post_reinforcement_expiration_records: tuple[PheromoneLifecycleRecord, ...],
    active_trails: tuple[PheromoneTrail, ...],
    observations: tuple[PheromoneExplorationObservation, ...],
    layer_proposals: list[LayerProposal],
    performance_snapshots: list[LayerPerformanceSnapshot],
    strategy_biases: list[StrategyBias],
    layer_state: LayerCoordinationState,
    adjustment_proposals: list[PolicyAdjustmentProposal],
    adjustment_batch: PolicyAdjustmentBatchResult,
    state: CollectiveDecisionState,
    decision: QuorumDecision,
    current_step: int,
    include_legacy_decision: bool = True,
) -> list[TraceEvent]:
    events = _input_trace_events(
        protocol_id=protocol_id,
        target=target,
        scout_reports=scout_reports,
        recruitment_signals=(recruitment_signals if policy.recruitment_enabled else []),
        inhibition_signals=(inhibition_signals if policy.inhibition_enabled else []),
    )
    replay_receipt_snapshot: dict[str, dict[str, str]] = {
        lifecycle: {}
        for lifecycle in ("deposit", "diffusion", "feedback", "adjustment")
    }

    def replay_binding(
        lifecycle: str,
        trace_event_id: str,
        current_receipt: tuple[Any, ...],
        processed_receipts: Mapping[str, tuple[Any, ...]],
    ) -> dict[str, object]:
        processed_receipt = processed_receipts.get(trace_event_id)
        if processed_receipt is None or processed_receipt != current_receipt:
            raise GovernanceError(
                f"{lifecycle} replay observation has no matching processed receipt: "
                f"{trace_event_id}"
            )
        current_digest = _replay_receipt_digest(current_receipt)
        processed_digest = _replay_receipt_digest(processed_receipt)
        replay_receipt_snapshot[lifecycle][trace_event_id] = processed_digest
        return {
            "replay_payload": _replay_receipt_trace_payload(current_receipt),
            "replay_payload_fingerprint": current_digest,
            "processed_payload_fingerprint": processed_digest,
        }

    accepted_adjustments = set(adjustment_batch.accepted_trace_event_ids)
    for adjustment in sorted(
        adjustment_proposals,
        key=lambda item: (item.layer_id, item.source_id, item.trace_event_id),
    ):
        if adjustment.trace_event_id not in adjustment_batch.processed_trace_event_ids:
            continue
        replayed = adjustment.trace_event_id not in accepted_adjustments
        replay_lineage = (
            replay_binding(
                "adjustment",
                adjustment.trace_event_id,
                _adjustment_replay_fingerprint(adjustment),
                adjustment_replay_receipts,
            )
            if replayed
            else {}
        )
        events.append(
            _trace_event(
                "policy_adjustment",
                protocol_id=protocol_id,
                target=target,
                reason=(
                    "previously accepted run-scoped adjustment replay was ignored"
                    if replayed
                    else "run-scoped policy adjustment accepted within declared bounds"
                ),
                lineage={
                    "proposed_values": dict(adjustment.adjustments),
                    "declared_bounds": {
                        key: thaw_protocol_value(policy.policy_adjustment_bounds[key])
                        for key in adjustment.adjustments
                    },
                    "result": "replay_ignored" if replayed else "accepted",
                    "source_id": adjustment.source_id,
                    "layer_id": adjustment.layer_id,
                    "provenance": adjustment.provenance,
                    "source_trace_event_id": adjustment.trace_event_id,
                    "replayed": replayed,
                    **replay_lineage,
                },
            )
        )

    # Layer proposals are inputs to governed coordination.  Record them before
    # any proposal-derived pheromone deposit so trace order mirrors causality.
    for proposal in sorted(
        layer_proposals,
        key=lambda item: (
            item.layer_id,
            item.source_id,
            item.candidate_id,
            item.action,
            item.trace_event_id,
        ),
    ):
        events.append(
            _trace_event(
                "layer_proposal",
                protocol_id=protocol_id,
                target=target,
                reason="bounded layer proposal accepted for governance coordination",
                lineage={
                    "layer_id": proposal.layer_id,
                    "source_id": proposal.source_id,
                    "action": proposal.action,
                    "effect": layer_state.action_effects.get(
                        proposal.trace_event_id, "metadata_only"
                    ),
                    "candidate_id": proposal.candidate_id,
                    "confidence": proposal.confidence,
                    "support": proposal.support,
                    "risk": proposal.risk,
                    "evidence_id": proposal.evidence_id,
                    "provenance": proposal.provenance,
                    "proposed_pheromone_kind": proposal.proposed_pheromone_kind,
                    "proposed_strength": proposal.proposed_strength,
                    "subject_type": proposal.metadata.get("subject_type", "candidate"),
                    "subject_id": proposal.metadata.get(
                        "subject_id", proposal.candidate_id
                    ),
                    "source_trace_event_id": proposal.trace_event_id,
                },
            )
        )
    for bias in sorted(
        strategy_biases,
        key=lambda item: (item.candidate_id, item.source_id, item.trace_event_id),
    ):
        events.append(
            _trace_event(
                "layer_proposal",
                protocol_id=protocol_id,
                target=target,
                reason="bounded evolutionary StrategyBias accepted",
                lineage={
                    "layer_id": bias.layer_id,
                    "source_id": bias.source_id,
                    "action": "strategy_bias",
                    "effect": "bounded_candidate_preference",
                    "candidate_id": bias.candidate_id,
                    "confidence": bias.confidence,
                    "support": bias.support,
                    "risk": 0.0,
                    "proposed_strength": 0.0,
                    "proposed_pheromone_kind": "",
                    "subject_type": "candidate",
                    "subject_id": bias.candidate_id,
                    "evidence_id": bias.evidence_id,
                    "provenance": bias.provenance,
                    "source_trace_event_id": bias.trace_event_id,
                },
            )
        )

    events.extend(
        _pheromone_lifecycle_trace_events(
            protocol_id=protocol_id,
            target=target,
            pheromone_policy=pheromone_policy,
            deposit_records=deposit_result.records,
            evaporation_records=evaporation_records,
            diffusion_records=diffusion_result.records,
            reinforcement_records=reinforcement_result.records,
            pre_diffusion_trails=pre_diffusion_trails,
        )
    )
    events.extend(
        _pheromone_lifecycle_trace_events(
            protocol_id=protocol_id,
            target=target,
            pheromone_policy=pheromone_policy,
            deposit_records=(),
            evaporation_records=post_reinforcement_expiration_records,
            diffusion_records=(),
            reinforcement_records=(),
            pre_diffusion_trails=(),
            phase="post_reinforcement",
        )
    )
    deposit_by_id = {item.trace_event_id: item for item in deposit_inputs}
    for trace_event_id in deposit_result.replayed_event_ids:
        item = deposit_by_id[trace_event_id]
        events.append(
            _trace_event(
                "pheromone_observe",
                protocol_id=protocol_id,
                target=target,
                reason="previously processed pheromone deposit replay was ignored",
                lineage={
                    "lifecycle": "deposit",
                    "source_trace_event_id": trace_event_id,
                    "result": "replay_ignored",
                    **replay_binding(
                        "deposit",
                        trace_event_id,
                        _trail_replay_fingerprint(item),
                        deposit_replay_receipts,
                    ),
                },
            )
        )
    for trace_event_id in diffusion_result.replayed_event_ids:
        processed_receipt = diffusion_replay_receipts.get(trace_event_id)
        if processed_receipt is None:
            raise GovernanceError(
                "diffusion replay observation has no processed receipt: "
                f"{trace_event_id}"
            )
        events.append(
            _trace_event(
                "pheromone_observe",
                protocol_id=protocol_id,
                target=target,
                reason="previously processed pheromone diffusion replay was ignored",
                lineage={
                    "lifecycle": "diffusion",
                    "source_trace_event_id": trace_event_id,
                    "result": "replay_ignored",
                    **replay_binding(
                        "diffusion",
                        trace_event_id,
                        processed_receipt,
                        diffusion_replay_receipts,
                    ),
                },
            )
        )
    feedback_by_id = {item.trace_event_id: item for item in feedback}
    for trace_event_id in reinforcement_result.replayed_feedback_ids:
        feedback_item = feedback_by_id[trace_event_id]
        events.append(
            _trace_event(
                "pheromone_observe",
                protocol_id=protocol_id,
                target=target,
                reason="previously processed feedback replay was ignored",
                lineage={
                    "lifecycle": "feedback",
                    "source_trace_event_id": feedback_item.trace_event_id,
                    "result": "replay_ignored",
                    **replay_binding(
                        "feedback",
                        trace_event_id,
                        _feedback_replay_fingerprint(feedback_item),
                        feedback_replay_receipts,
                    ),
                },
            )
        )

    active_source_kinds = {
        record.trace_event_id: record.source_kind
        for record in (
            *deposit_result.records,
            *evaporation_records,
            *diffusion_result.records,
            *reinforcement_result.records,
            *post_reinforcement_expiration_records,
        )
        if record.new_strength != record.old_strength or record.action == "expire"
    }
    active_candidate_set = CandidateSet(
        tuple(
            candidate
            for candidate in candidate_set.candidates
            if candidate.target == target
        )
    )
    pheromone_score = score_pheromone_trails_result(
        candidate_set=active_candidate_set,
        trails=list(active_trails),
        policy=pheromone_policy,
    )
    events.append(
        _trace_event(
            "pheromone_score",
            protocol_id=protocol_id,
            target=target,
            reason="target-scoped pheromone contributions were scored",
            lineage={
                "scores": dict(pheromone_score.scores),
                "score_breakdown": {
                    candidate_id: dict(categories)
                    for candidate_id, categories in pheromone_score.score_breakdown.items()
                },
                "kind_breakdown": {
                    candidate_id: dict(categories)
                    for candidate_id, categories in pheromone_score.kind_breakdown.items()
                },
                "subject_breakdown": {
                    candidate_id: dict(categories)
                    for candidate_id, categories in pheromone_score.subject_breakdown.items()
                },
                "active_trails": [
                    {
                        "trace_event_id": trail.trace_event_id,
                        "source_id": pheromone_source_id(trail),
                        "candidate_id": pheromone_bound_candidate_id(trail),
                        "subject_type": pheromone_subject_type(trail),
                        "subject_id": pheromone_subject_id(trail),
                        "kind": trail.kind,
                        "source_kind": active_source_kinds.get(
                            trail.trace_event_id,
                            trail.kind,
                        ),
                        "strength": trail.strength,
                        "provenance": trail.provenance,
                        "deposited_at_step": trail.deposited_at_step,
                        "updated_at_step": trail.updated_at_step,
                        "ttl_steps": trail.ttl_steps,
                    }
                    for trail in active_trails
                ],
                "current_step": current_step,
                "processed_replay_receipts": {
                    lifecycle: dict(receipts)
                    for lifecycle, receipts in replay_receipt_snapshot.items()
                },
            },
        )
    )
    if pheromone_score.normalization is not None:
        normalization = pheromone_score.normalization
        events.append(
            _trace_event(
                "pheromone_normalize",
                protocol_id=protocol_id,
                target=target,
                reason="competitive pheromone response normalized candidate pressure",
                lineage={
                    "candidates": list(normalization.candidate_ids),
                    "pre_scores": dict(normalization.pre_scores),
                    "post_scores": dict(normalization.post_scores),
                    "response_model": normalization.response_model,
                    "competition_mode": normalization.competition_mode,
                },
            )
        )
    for observation in observations:
        events.append(
            _trace_event(
                "pheromone_observe",
                protocol_id=protocol_id,
                target=target,
                reason=observation.reason,
                lineage={
                    "candidate_id": observation.candidate_id,
                    "subject_type": observation.subject_type,
                    "subject_id": observation.subject_id,
                    "novelty_pressure": observation.novelty_pressure,
                    "reopen_eligible": observation.reopen_eligible,
                    "source_trace_event_id": observation.trace_event_id,
                },
            )
        )
    exploration_candidate_ids = [
        candidate.id
        for candidate in active_candidate_set.candidates
        if not candidate.safe_fallback
    ]
    if (
        pheromone_policy.exploration_enabled
        and pheromone_policy.exploration_floor > 0
        and exploration_candidate_ids
    ):
        events.append(
            _trace_event(
                "pheromone_observe",
                protocol_id=protocol_id,
                target=target,
                reason="declared deterministic exploration floor applied",
                lineage={
                    "exploration_floor": pheromone_policy.exploration_floor,
                    "candidate_ids": exploration_candidate_ids,
                },
            )
        )

    proposal_lineage = [*layer_state.trace_lineage]
    snapshot_by_layer = {
        snapshot.layer_id: snapshot for snapshot in performance_snapshots
    }
    snapshot_lineage: dict[str, dict[str, float | bool]] = {}
    for layer_id in sorted(SUPPORTED_LAYER_IDS):
        snapshot = snapshot_by_layer.get(layer_id)
        snapshot_lineage[layer_id] = {
            "present": snapshot is not None,
            "recent_success_rate": (
                snapshot.recent_success_rate if snapshot is not None else 0.0
            ),
            "recent_conflict_rate": (
                snapshot.recent_conflict_rate if snapshot is not None else 0.0
            ),
            "recent_fallback_rate": (
                snapshot.recent_fallback_rate if snapshot is not None else 0.0
            ),
            "mean_confidence": snapshot.mean_confidence
            if snapshot is not None
            else 0.0,
            "evidence_coverage": snapshot.evidence_coverage
            if snapshot is not None
            else 0.0,
            "trace_coverage": snapshot.trace_coverage if snapshot is not None else 0.0,
        }
    # Keep the draft coverage view for readers while recording the complete
    # performance inputs used by governance in ``snapshots``.  Explicit
    # presence prevents an omitted snapshot from being confused with an
    # all-zero snapshot during conformance replay.
    snapshot_coverage = {
        layer_id: {
            "mean_confidence": values["mean_confidence"],
            "evidence_coverage": values["evidence_coverage"],
            "trace_coverage": values["trace_coverage"],
        }
        for layer_id, values in snapshot_lineage.items()
    }
    snapshot_coverage["governance_trace_confirmations"] = dict(
        layer_state.trace_coverage_confirmations
    )
    events.append(
        _trace_event(
            "coordination_assess",
            protocol_id=protocol_id,
            target=target,
            reason="layer confidence, performance coverage, and weights assessed",
            lineage={
                "confidences": dict(layer_state.confidences),
                "weights": dict(layer_state.allocated_weights),
                "snapshots": snapshot_lineage,
                "coverage": snapshot_coverage,
                "action_effects": dict(layer_state.action_effects),
                "trace_coverage_confirmations": dict(
                    layer_state.trace_coverage_confirmations
                ),
                "proposal_lineage": list(proposal_lineage),
            },
        )
    )
    events.append(
        _trace_event(
            "coordination_resolve",
            protocol_id=protocol_id,
            target=target,
            reason="layer conflicts resolved under declared fallback policy",
            lineage={
                "conflicts": list(layer_state.conflicts),
                "resolution": layer_state.resolution,
                "selected_candidate": layer_state.selected_candidate,
                "fallback_used": layer_state.fallback_used,
                "reason": layer_state.resolution,
                "proposal_lineage": list(proposal_lineage),
            },
        )
    )

    score_lineage = {
        "scores": dict(state.scores),
        "score_breakdown": {
            candidate_id: dict(categories)
            for candidate_id, categories in state.score_breakdown.items()
        },
        "scout_diversity": {
            candidate_id: len(scout_ids)
            for candidate_id, scout_ids in state.independent_scouts.items()
        },
        "pheromone_source_diversity": dict(state.pheromone_source_diversity),
    }
    events.append(
        _trace_event(
            "candidate_score",
            protocol_id=protocol_id,
            target=target,
            reason="complete Hybrid candidate score reconstructed from declared categories",
            lineage=score_lineage,
        )
    )
    if not include_legacy_decision:
        # The same Hybrid memory pipeline is also the attention plane for the
        # Optimal Commit ABI.  In that mode candidate scores are exploration
        # priorities only: emitting the legacy consensus/commit pair would
        # falsely suggest that blended attention carried commit authority.
        return events
    events.append(
        _trace_event(
            "consensus_check",
            protocol_id=protocol_id,
            target=target,
            reason="independent-scout and collective score gates evaluated",
            lineage={
                "quorum_threshold": policy.quorum_threshold,
                "min_independent_scouts": policy.min_independent_scouts,
            },
        )
    )
    decision_event_type = "fallback" if "fallback" in decision.reason else "commit"
    upstream_score_lineage = {
        "candidate_score",
        "pheromone_score",
        *(report.trace_event_id for report in scout_reports),
        *(
            signal.trace_event_id
            for signal in recruitment_signals
            if policy.recruitment_enabled
        ),
        *(
            signal.trace_event_id
            for signal in inhibition_signals
            if policy.inhibition_enabled
        ),
        *adjustment_batch.accepted_trace_event_ids,
        *(trail.trace_event_id for trail in active_trails),
        *proposal_lineage,
    }
    events.append(
        _trace_event(
            decision_event_type,
            protocol_id=protocol_id,
            target=target,
            reason=decision.reason,
            lineage={
                "target": target,
                "candidate_id": decision.candidate_id,
                "decision_reason": decision.reason,
                "upstream_score_lineage": sorted(upstream_score_lineage),
            },
        )
    )
    return events


for _compat_function in (
    _trace_event,
    _input_trace_events,
    _clip_causal_lineage,
    _pheromone_lifecycle_trace_events,
    _replay_receipt_digest,
    _replay_receipt_trace_payload,
    _hybrid_step_trace_events,
):
    _compat_function.__module__ = "pheroos.governance.collective"
del _compat_function

__all__ = (
    "_clip_causal_lineage",
    "_hybrid_step_trace_events",
    "_input_trace_events",
    "_pheromone_lifecycle_trace_events",
    "_replay_receipt_digest",
    "_replay_receipt_trace_payload",
    "_trace_event",
)
