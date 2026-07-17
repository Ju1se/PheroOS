from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
from math import isclose, isfinite
from numbers import Real
from typing import Any, Callable, Iterable, Protocol

from pheroos._digest import is_canonical_sha256_fingerprint
from pheroos.trace.commit_contracts import (
    COMMIT_EVENT_TYPES,
    validate_commit_trace_event,
)

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


class TraceEventView(Protocol):
    """Structural input owned below the public ``TraceEvent`` model."""

    event_type: str
    protocol_id: str
    target: str
    reason: str
    lineage: dict[str, Any]


TraceEventValidator = Callable[[TraceEventView], None]


def canonical_pheromone_clip_payload(payload: Mapping[str, Any]) -> str:
    """Return the versioned canonical JSON used to bind rejected clip inputs.

    The receipt is an integrity and replay-lineage binding, not evidence or
    authority.  Only provider-neutral JSON values are accepted, and all
    numeric leaves must be finite so the digest has one deterministic ABI
    interpretation.
    """

    normalized = _canonical_clip_payload_value(payload, path="causal_payload")
    if not isinstance(normalized, dict):  # pragma: no cover - Mapping above
        raise TypeError("pheromone clip causal payload must be an object")
    envelope = {
        "payload": normalized,
        "version": PHEROMONE_CLIP_PAYLOAD_VERSION,
    }
    return json.dumps(
        envelope,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def pheromone_clip_payload_fingerprint(payload: Mapping[str, Any]) -> str:
    """Return the canonical SHA-256 receipt for one clip causal payload."""

    canonical = canonical_pheromone_clip_payload(payload)
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_clip_payload_value(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, Real):
        if not isfinite(float(value)):
            raise ValueError(f"{path} must contain only finite numbers")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise TypeError(f"{path} keys must be non-empty strings")
            normalized[key] = _canonical_clip_payload_value(
                item,
                path=f"{path}.{key}",
            )
        return normalized
    if isinstance(value, (list, tuple)):
        return [
            _canonical_clip_payload_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise TypeError(f"{path} contains unsupported value type: {type(value).__name__}")


def build_declared_event_validator(
    required_fields: frozenset[str],
    *,
    schema_condition: bool,
) -> TraceEventValidator:
    """Bind one immutable declaration to the complete low-level validator."""

    declared_fields = frozenset(required_fields)

    def validate_declared_event(event: TraceEventView) -> None:
        _validate_declared_event_lineage(
            event,
            required_fields=declared_fields,
            schema_condition=schema_condition,
        )

    return validate_declared_event


def _validate_declared_event_lineage(
    event: TraceEventView,
    *,
    required_fields: frozenset[str],
    schema_condition: bool,
) -> None:
    """Validate event-specific lineage for authority-relevant built-ins.

    The checks intentionally cover only the small Trace ABI contract rather
    than becoming a general schema engine.  Missing, malformed, non-finite, or
    internally inconsistent lineage is rejected before a store append.
    """

    if not isinstance(event.lineage, dict):
        raise ValueError("trace event lineage must be an object")
    if event.event_type in COMMIT_EVENT_TYPES:
        validate_commit_trace_event(
            event_type=event.event_type,
            protocol_id=event.protocol_id,
            target=event.target,
            reason=event.reason,
            lineage=event.lineage,
        )
        return
    if not schema_condition:
        return
    missing = sorted(
        field for field in required_fields if field not in event.lineage
    )
    if missing:
        raise ValueError(f"{event.event_type} trace lineage missing required fields: {', '.join(missing)}")
    lineage = event.lineage
    if event.event_type == "explore":
        _require_positive_integer(event.event_type, lineage, "scout_count")
    elif event.event_type == "scout_report":
        _require_text_fields(
            event.event_type,
            lineage,
            {
                "scout_id",
                "candidate_id",
                "evidence_id",
                "provenance",
                "source_trace_event_id",
                "verification_trace_event_id",
            },
        )
        _require_nonnegative_number(event.event_type, lineage, "support")
    elif event.event_type in {"recruit", "inhibit"}:
        _require_text_fields(
            event.event_type,
            lineage,
            {
                "source_id",
                "candidate_id",
                "provenance",
                "source_trace_event_id",
                "verification_trace_event_id",
            },
        )
        _require_nonnegative_number(event.event_type, lineage, "strength")
    elif event.event_type == "pheromone_deposit":
        _require_text_fields(
            event.event_type,
            lineage,
            {
                "source_id",
                "provenance",
                "subject_type",
                "subject_id",
                "candidate_id",
                "kind",
                "source_kind",
                "source_trace_event_id",
                "trace_event_id",
            },
        )
        source_strength = _require_nonnegative_number(event.event_type, lineage, "source_strength")
        old_strength = _require_nonnegative_number(event.event_type, lineage, "old_strength")
        requested_strength = _require_nonnegative_number(
            event.event_type, lineage, "requested_strength"
        )
        applied_strength = _require_nonnegative_number(
            event.event_type, lineage, "applied_strength"
        )
        new_strength = _require_nonnegative_number(event.event_type, lineage, "new_strength")
        for field_name in ("round_budget_remaining", "source_budget_remaining"):
            _require_nonnegative_number(event.event_type, lineage, field_name)
        if not isclose(source_strength, old_strength, abs_tol=1e-9) or not isclose(
            old_strength, 0.0, abs_tol=1e-9
        ):
            raise ValueError("pheromone_deposit trace must start from zero source strength")
        if applied_strength > requested_strength + 1e-9:
            raise ValueError("pheromone_deposit trace applied strength exceeds its request")
        if not isclose(new_strength, source_strength + applied_strength, abs_tol=1e-9):
            raise ValueError("pheromone_deposit trace applied strength must reconstruct new strength")
        if lineage["source_kind"] != lineage["kind"]:
            raise ValueError("pheromone_deposit trace must preserve pheromone kind")
        if lineage["source_trace_event_id"] != lineage["trace_event_id"]:
            raise ValueError("pheromone_deposit trace result id must match its deposit source id")
        _require_nonnegative_integer(event.event_type, lineage, "step")
        _require_nonnegative_integer(event.event_type, lineage, "deposited_at_step")
        _require_nonnegative_integer(event.event_type, lineage, "updated_at_step")
        if lineage["updated_at_step"] != lineage["step"]:
            raise ValueError("pheromone_deposit trace updated step must equal lifecycle step")
        if lineage["deposited_at_step"] > lineage["updated_at_step"]:
            raise ValueError("pheromone_deposit trace deposit step must not follow update step")
    elif event.event_type == "pheromone_evaporate":
        _require_text_fields(
            event.event_type,
            lineage,
            {
                "subject_type",
                "subject_id",
                "kind",
                "source_kind",
                "source_id",
                "provenance",
                "profile",
                "candidate_id",
                "source_trace_event_id",
                "trace_event_id",
            },
        )
        source_strength = _require_nonnegative_number(event.event_type, lineage, "source_strength")
        old_strength = _require_nonnegative_number(event.event_type, lineage, "old_strength")
        requested_strength = _require_nonnegative_number(
            event.event_type, lineage, "requested_strength"
        )
        applied_strength = _require_nonnegative_number(
            event.event_type, lineage, "applied_strength"
        )
        new_strength = _require_nonnegative_number(event.event_type, lineage, "new_strength")
        if new_strength > old_strength:
            raise ValueError("pheromone_evaporate trace new strength must not exceed old strength")
        delta = _finite_number(event.event_type, "strength_delta", lineage["strength_delta"])
        if not (
            isclose(source_strength, old_strength, abs_tol=1e-9)
            and isclose(requested_strength, source_strength, abs_tol=1e-9)
            and isclose(applied_strength, new_strength, abs_tol=1e-9)
            and isclose(delta, new_strength - source_strength, abs_tol=1e-9)
        ):
            raise ValueError("pheromone_evaporate trace strengths do not reconstruct transition")
        if lineage["source_kind"] != lineage["kind"]:
            raise ValueError("pheromone_evaporate trace must preserve pheromone kind")
        if lineage["source_trace_event_id"] != lineage["trace_event_id"]:
            raise ValueError("pheromone_evaporate trace must update its source trail in place")
        _require_positive_integer(event.event_type, lineage, "elapsed_steps")
        _require_nonnegative_integer(event.event_type, lineage, "step")
        _require_nonnegative_integer(event.event_type, lineage, "source_updated_at_step")
        _require_nonnegative_integer(event.event_type, lineage, "deposited_at_step")
        if lineage["step"] - lineage["source_updated_at_step"] != lineage["elapsed_steps"]:
            raise ValueError("pheromone_evaporate trace elapsed steps do not reconstruct transition")
        if lineage["deposited_at_step"] > lineage["source_updated_at_step"]:
            raise ValueError("pheromone_evaporate trace source update precedes deposit")
    elif event.event_type == "pheromone_diffuse":
        _require_subject(event.event_type, lineage, "source_subject")
        _require_subject(event.event_type, lineage, "target_subject")
        _require_text_fields(
            event.event_type,
            lineage,
            {
                "root_trace_event_id",
                "source_id",
                "candidate_id",
                "source_kind",
                "kind",
                "provenance",
                "source_trace_event_id",
                "trace_event_id",
            },
        )
        _require_positive_integer(event.event_type, lineage, "hop")
        attenuation = _finite_number(event.event_type, "attenuation", lineage["attenuation"])
        if not 0 <= attenuation <= 1:
            raise ValueError("pheromone_diffuse trace lineage attenuation must be between 0 and 1")
        policy_attenuation = _finite_number(
            event.event_type, "policy_attenuation", lineage["policy_attenuation"]
        )
        edge_attenuation = _finite_number(
            event.event_type, "edge_attenuation", lineage["edge_attenuation"]
        )
        if not 0 <= policy_attenuation <= 1 or not 0 <= edge_attenuation <= 1:
            raise ValueError(
                "pheromone_diffuse trace policy and edge attenuation must be between 0 and 1"
            )
        if not isclose(
            attenuation,
            policy_attenuation * edge_attenuation,
            abs_tol=1e-9,
        ):
            raise ValueError("pheromone_diffuse trace attenuation factors do not reconstruct")
        source_strength = _require_nonnegative_number(event.event_type, lineage, "source_strength")
        requested_strength = _require_nonnegative_number(
            event.event_type, lineage, "requested_strength"
        )
        applied_strength = _require_nonnegative_number(
            event.event_type, lineage, "applied_strength"
        )
        new_strength = _require_nonnegative_number(event.event_type, lineage, "new_strength")
        for field_name in ("round_budget_remaining", "source_budget_remaining"):
            _require_nonnegative_number(event.event_type, lineage, field_name)
        if not isclose(requested_strength, source_strength * attenuation, abs_tol=1e-9):
            raise ValueError("pheromone_diffuse trace request must equal attenuated source strength")
        if applied_strength > requested_strength + 1e-9:
            raise ValueError("pheromone_diffuse trace applied strength exceeds its request")
        if not isclose(new_strength, applied_strength, abs_tol=1e-9):
            raise ValueError("pheromone_diffuse trace applied strength must equal new strength")
        if lineage["source_kind"] != lineage["kind"]:
            raise ValueError("pheromone_diffuse trace must preserve pheromone kind")
        if lineage["source_trace_event_id"] == lineage["trace_event_id"]:
            raise ValueError("pheromone_diffuse trace must issue a derived trail id")
    elif event.event_type == "pheromone_reinforce":
        _require_text_fields(
            event.event_type,
            lineage,
            {
                "feedback_source",
                "source_id",
                "provenance",
                "outcome",
                "candidate_id",
                "subject_type",
                "subject_id",
                "source_kind",
                "kind",
                "source_trace_event_id",
                "feedback_trace_event_id",
                "trace_event_id",
            },
        )
        _finite_number(event.event_type, "reward", lineage["reward"])
        delta = _finite_number(event.event_type, "delta", lineage["delta"])
        source_strength = _require_nonnegative_number(event.event_type, lineage, "source_strength")
        requested_strength = _require_nonnegative_number(
            event.event_type, lineage, "requested_strength"
        )
        applied_strength = _require_nonnegative_number(
            event.event_type, lineage, "applied_strength"
        )
        old_strength = _require_nonnegative_number(event.event_type, lineage, "old_strength")
        new_strength = _require_nonnegative_number(event.event_type, lineage, "new_strength")
        _validate_budget_result(event.event_type, lineage["budget_result"])
        if not isclose(source_strength, old_strength, abs_tol=1e-9) or not isclose(
            new_strength - source_strength, delta, abs_tol=1e-9
        ):
            raise ValueError("pheromone_reinforce trace delta must reconstruct new strength")
        if not isclose(applied_strength, abs(delta), abs_tol=1e-9):
            raise ValueError("pheromone_reinforce trace applied strength must equal delta magnitude")
        if applied_strength > requested_strength + 1e-9:
            raise ValueError("pheromone_reinforce trace applied strength exceeds its request")
        if lineage["feedback_source"] != lineage["source_id"]:
            raise ValueError("pheromone_reinforce trace feedback source identity is inconsistent")
        if delta < 0 and (lineage["outcome"] != "stale" or lineage["kind"] != "stale"):
            raise ValueError("negative pheromone reinforcement must be an explicit stale transition")
        _require_nonnegative_integer(event.event_type, lineage, "step")
    elif event.event_type == "pheromone_score":
        _validate_pheromone_score_lineage(lineage)
    elif event.event_type == "pheromone_clip":
        _validate_pheromone_clip_lineage(event)
    elif event.event_type == "pheromone_expire":
        _require_text_fields(
            event.event_type,
            lineage,
            {
                "action",
                "target",
                "candidate_id",
                "subject_type",
                "subject_id",
                "kind",
                "source_kind",
                "source_id",
                "provenance",
                "source_trace_event_id",
                "trace_event_id",
            },
        )
        if lineage["action"] != "expire" or lineage["kind"] != "stale":
            raise ValueError("pheromone_expire trace lineage must record an expire transition to stale")
        if lineage["target"] != event.target:
            raise ValueError("pheromone_expire trace lineage target must match the event target")
        source_strength = _require_nonnegative_number(event.event_type, lineage, "source_strength")
        old_strength = _require_nonnegative_number(event.event_type, lineage, "old_strength")
        requested_strength = _require_nonnegative_number(
            event.event_type, lineage, "requested_strength"
        )
        applied_strength = _require_nonnegative_number(
            event.event_type, lineage, "applied_strength"
        )
        new_strength = _require_nonnegative_number(event.event_type, lineage, "new_strength")
        delta = _finite_number(event.event_type, "strength_delta", lineage["strength_delta"])
        if new_strength > old_strength:
            raise ValueError("pheromone_expire trace new strength must not exceed old strength")
        if not (
            isclose(source_strength, old_strength, abs_tol=1e-9)
            and isclose(requested_strength, source_strength, abs_tol=1e-9)
            and isclose(applied_strength, new_strength, abs_tol=1e-9)
            and isclose(delta, new_strength - source_strength, abs_tol=1e-9)
        ):
            raise ValueError("pheromone_expire trace strengths do not reconstruct transition")
        if lineage["source_trace_event_id"] != lineage["trace_event_id"]:
            raise ValueError("pheromone_expire trace must update its source trail in place")
        _require_nonnegative_integer(event.event_type, lineage, "step")
        _require_nonnegative_integer(event.event_type, lineage, "source_updated_at_step")
        _require_nonnegative_integer(event.event_type, lineage, "deposited_at_step")
        _require_nonnegative_integer(event.event_type, lineage, "ttl_steps")
        _require_nonnegative_integer(event.event_type, lineage, "elapsed_steps")
        if lineage["step"] - lineage["source_updated_at_step"] != lineage["elapsed_steps"]:
            raise ValueError("pheromone_expire trace elapsed steps do not reconstruct transition")
        if lineage["step"] - lineage["deposited_at_step"] < lineage["ttl_steps"]:
            raise ValueError("pheromone_expire trace transition precedes its declared TTL")
    elif event.event_type == "pheromone_observe":
        _validate_pheromone_observation(event)
    elif event.event_type == "pheromone_normalize":
        _require_nonempty_text_sequence(event.event_type, lineage, "candidates")
        _require_score_mapping(event.event_type, lineage, "pre_scores")
        _require_score_mapping(event.event_type, lineage, "post_scores")
        _require_text_fields(event.event_type, lineage, {"response_model", "competition_mode"})
        candidates = set(lineage["candidates"])
        if set(lineage["pre_scores"]) != candidates or set(lineage["post_scores"]) != candidates:
            raise ValueError("pheromone_normalize trace scores must cover exactly the declared candidates")
        response_model = lineage["response_model"]
        per_kind_competitive = bool(
            response_model.startswith("competitive:")
            and all(
                kind and kind.strip() == kind
                for kind in response_model.removeprefix("competitive:").split(",")
            )
        )
        if response_model not in {"linear", "saturating", "threshold", "competitive"} and not per_kind_competitive:
            raise ValueError("pheromone_normalize trace response_model is unsupported")
        if lineage["competition_mode"] not in {"none", "normalize"}:
            raise ValueError("pheromone_normalize trace competition_mode is unsupported")
    elif event.event_type == "layer_proposal":
        _require_text_fields(
            event.event_type,
            lineage,
            {
                "layer_id",
                "source_id",
                "action",
                "effect",
                "candidate_id",
                "evidence_id",
                "provenance",
                "source_trace_event_id",
                "subject_type",
                "subject_id",
            },
        )
        if lineage["layer_id"] not in {
            "reactive",
            "learned",
            "evolutionary",
            "metacognitive",
        }:
            raise ValueError("layer_proposal trace lineage layer_id is unsupported")
        confidence = _finite_number(event.event_type, "confidence", lineage["confidence"])
        if not 0 <= confidence <= 1:
            raise ValueError("layer_proposal trace lineage confidence must be between 0 and 1")
        for field_name in ("support", "risk"):
            value = _finite_number(event.event_type, field_name, lineage[field_name])
            if not 0 <= value <= 10:
                raise ValueError(f"layer_proposal trace lineage {field_name} must be between 0 and 10")
        proposed_strength = _finite_number(
            event.event_type,
            "proposed_strength",
            lineage["proposed_strength"],
        )
        if not 0 <= proposed_strength <= 10:
            raise ValueError("layer_proposal trace lineage proposed_strength must be between 0 and 10")
        if not isinstance(lineage["proposed_pheromone_kind"], str):
            raise ValueError("layer_proposal trace lineage proposed_pheromone_kind must be a string")
        if lineage["action"] == "propose_pheromone":
            if lineage["effect"] != "bounded_pheromone_deposit_proposed":
                raise ValueError("layer pheromone proposal trace must declare its bounded deposit effect")
            if not lineage["proposed_pheromone_kind"] or proposed_strength <= 0:
                raise ValueError("layer pheromone proposal trace requires kind and positive strength")
    elif event.event_type == "coordination_assess":
        _require_declared_layer_score_mapping(
            event.event_type,
            lineage,
            "confidences",
            minimum=0.0,
            maximum=1.0,
        )
        _require_declared_layer_score_mapping(
            event.event_type,
            lineage,
            "weights",
            minimum=0.0,
        )
        _require_layer_snapshots(event.event_type, lineage, "snapshots")
        _require_recursive_coverage(event.event_type, lineage, "coverage")
        _require_text_mapping(event.event_type, lineage, "action_effects")
        _require_bounded_mapping(
            event.event_type,
            lineage,
            "trace_coverage_confirmations",
            minimum=0.0,
            maximum=1.0,
        )
        _require_text_sequence(event.event_type, lineage, "proposal_lineage", allow_empty=True)
    elif event.event_type == "coordination_resolve":
        _require_text_sequence(event.event_type, lineage, "conflicts", allow_empty=True)
        _require_text_fields(event.event_type, lineage, {"resolution", "selected_candidate", "reason"})
        _require_boolean(event.event_type, lineage, "fallback_used")
        _require_text_sequence(event.event_type, lineage, "proposal_lineage", allow_empty=True)
        if lineage["reason"] != lineage["resolution"]:
            raise ValueError(
                "coordination_resolve trace lineage reason must equal resolution"
            )
    elif event.event_type == "policy_adjustment":
        _require_nonempty_mapping(event.event_type, lineage, "proposed_values")
        _require_nonempty_mapping(event.event_type, lineage, "declared_bounds")
        _require_text_fields(
            event.event_type,
            lineage,
            {"result", "source_id", "layer_id", "provenance", "source_trace_event_id"},
        )
        if lineage["result"] not in {"accepted", "rejected", "replay_ignored"}:
            raise ValueError(
                "policy_adjustment trace lineage result must be accepted, rejected, or replay_ignored"
            )
        _validate_policy_adjustment_lineage(lineage)
        if lineage["result"] == "replay_ignored":
            if lineage.get("replayed") is not True:
                raise ValueError(
                    "replayed policy_adjustment trace must set replayed=true"
                )
            _require_matching_replay_fingerprints(event.event_type, lineage)
    elif event.event_type == "candidate_score":
        _validate_candidate_score_lineage(lineage)
    elif event.event_type == "consensus_check":
        threshold = _finite_number(event.event_type, "quorum_threshold", lineage["quorum_threshold"])
        if threshold <= 0:
            raise ValueError("consensus_check trace lineage quorum_threshold must be positive")
        _require_positive_integer(event.event_type, lineage, "min_independent_scouts")
    elif event.event_type in {"commit", "fallback"}:
        _require_text_fields(event.event_type, lineage, {"target", "candidate_id", "decision_reason"})
        if lineage["target"] != event.target:
            raise ValueError(f"{event.event_type} trace lineage target must match the event target")
        _require_nonempty_text_sequence(event.event_type, lineage, "upstream_score_lineage")
    elif event.event_type == "output":
        for field_name in required_fields:
            _require_boolean(event.event_type, lineage, field_name)
        expected = all(
            lineage[field_name]
            for field_name in (
                "committed_candidate",
                "evidence_provenance",
                "stop_resolution",
                "publication_permission",
            )
        )
        if lineage["authorized"] is not expected:
            raise ValueError("output trace authorization must equal the four declared output gates")


def _validate_candidate_score_lineage(lineage: dict[str, Any]) -> None:
    event_type = "candidate_score"
    _require_score_mapping(event_type, lineage, "scores")
    breakdown = lineage["score_breakdown"]
    if not isinstance(breakdown, dict) or not breakdown:
        raise ValueError("candidate_score trace lineage score_breakdown must be a non-empty object")
    if set(breakdown) != set(lineage["scores"]):
        raise ValueError("candidate_score trace scores and breakdown must cover the same candidates")
    for candidate_id, categories in breakdown.items():
        if not isinstance(candidate_id, str) or not candidate_id or not isinstance(categories, dict) or not categories:
            raise ValueError("candidate_score trace breakdown must map candidate ids to category objects")
        values = [_finite_number(event_type, f"score_breakdown.{candidate_id}.{name}", value) for name, value in categories.items()]
        if sum(values) != lineage["scores"][candidate_id]:
            raise ValueError(f"candidate_score trace breakdown does not reconstruct score for {candidate_id}")
    _require_count_mapping(event_type, lineage, "scout_diversity")
    _require_count_mapping(event_type, lineage, "pheromone_source_diversity")


def _validate_pheromone_score_lineage(lineage: dict[str, Any]) -> None:
    event_type = "pheromone_score"
    _require_nonnegative_integer(event_type, lineage, "current_step")
    current_step = lineage["current_step"]
    _require_score_mapping(event_type, lineage, "scores")
    candidates = set(lineage["scores"])
    for dimension in ("score_breakdown", "kind_breakdown", "subject_breakdown"):
        breakdown = lineage[dimension]
        if not isinstance(breakdown, dict) or set(breakdown) != candidates:
            raise ValueError(f"{event_type} trace lineage {dimension} must cover exactly the scored candidates")
        for candidate_id, categories in breakdown.items():
            if not isinstance(categories, dict):
                raise ValueError(f"{event_type} trace lineage {dimension}.{candidate_id} must be an object")
            values = [
                _finite_number(event_type, f"{dimension}.{candidate_id}.{name}", value)
                for name, value in categories.items()
            ]
            if not isclose(sum(values), lineage["scores"][candidate_id], abs_tol=1e-9):
                raise ValueError(
                    f"{event_type} trace lineage {dimension} does not reconstruct score for {candidate_id}"
                )
    trails = lineage["active_trails"]
    if not isinstance(trails, (list, tuple)):
        raise ValueError("pheromone_score trace lineage active_trails must be an array")
    trace_ids: set[str] = set()
    required = {
        "trace_event_id",
        "source_id",
        "candidate_id",
        "subject_type",
        "subject_id",
        "kind",
        "source_kind",
        "strength",
        "provenance",
        "deposited_at_step",
        "updated_at_step",
        "ttl_steps",
    }
    for index, trail in enumerate(trails):
        if not isinstance(trail, dict) or not required.issubset(trail):
            raise ValueError(
                f"pheromone_score trace lineage active_trails[{index}] is incomplete"
            )
        _require_text_fields(
            event_type,
            trail,
            required - {"strength", "deposited_at_step", "updated_at_step", "ttl_steps"},
        )
        _require_nonnegative_number(event_type, trail, "strength")
        _require_nonnegative_integer(event_type, trail, "deposited_at_step")
        _require_nonnegative_integer(event_type, trail, "updated_at_step")
        deposited_at_step = trail["deposited_at_step"]
        updated_at_step = trail["updated_at_step"]
        if deposited_at_step > updated_at_step:
            raise ValueError("pheromone_score trace active trail update precedes deposit")
        if updated_at_step > current_step:
            raise ValueError("pheromone_score trace active trail update exceeds current step")
        ttl_steps = trail["ttl_steps"]
        if ttl_steps is not None:
            if isinstance(ttl_steps, bool) or not isinstance(ttl_steps, int) or ttl_steps < 0:
                raise ValueError(
                    "pheromone_score trace active trail ttl_steps must be null or a non-negative integer"
                )
            if current_step - deposited_at_step >= ttl_steps and trail["kind"] != "stale":
                raise ValueError(
                    "pheromone_score trace cannot retain an expired non-stale active trail"
                )
        trace_id = trail["trace_event_id"]
        if trace_id in trace_ids:
            raise ValueError("pheromone_score trace active trail ids must be unique")
        trace_ids.add(trace_id)
    if "processed_replay_receipts" in lineage:
        _validate_processed_replay_receipts(
            event_type,
            lineage["processed_replay_receipts"],
        )


def _validate_processed_replay_receipts(event_type: str, value: Any) -> None:
    lifecycles = {"deposit", "diffusion", "feedback", "adjustment"}
    if not isinstance(value, dict) or set(value) != lifecycles:
        raise ValueError(
            f"{event_type} trace processed_replay_receipts must contain exactly "
            "deposit, diffusion, feedback, and adjustment"
        )
    seen_ids: set[str] = set()
    for lifecycle, receipts in value.items():
        if not isinstance(receipts, dict):
            raise ValueError(
                f"{event_type} trace processed_replay_receipts.{lifecycle} must be an object"
            )
        for trace_event_id, fingerprint in receipts.items():
            if not isinstance(trace_event_id, str) or not trace_event_id:
                raise ValueError(
                    f"{event_type} trace replay receipt ids must be non-empty strings"
                )
            if trace_event_id in seen_ids:
                raise ValueError(
                    f"{event_type} trace replay receipt ids must be unique across lifecycles"
                )
            seen_ids.add(trace_event_id)
            _require_receipt_fingerprint(
                event_type,
                f"processed_replay_receipts.{lifecycle}.{trace_event_id}",
                fingerprint,
            )


def _require_matching_replay_fingerprints(
    event_type: str,
    lineage: dict[str, Any],
) -> None:
    replay_payload = lineage.get("replay_payload")
    if not isinstance(replay_payload, (list, tuple)) or not replay_payload:
        raise ValueError(
            f"{event_type} replay lineage replay_payload must be a non-empty array"
        )
    for field_name in (
        "replay_payload_fingerprint",
        "processed_payload_fingerprint",
    ):
        if field_name not in lineage:
            raise ValueError(
                f"{event_type} replay lineage missing required field: {field_name}"
            )
        _require_receipt_fingerprint(event_type, field_name, lineage[field_name])
    expected_fingerprint = pheromone_clip_payload_fingerprint(
        {
            "lifecycle": "replay_receipt",
            "receipt": replay_payload,
        }
    )
    if lineage["replay_payload_fingerprint"] != expected_fingerprint:
        raise ValueError(
            f"{event_type} replay payload fingerprint does not match replay_payload"
        )
    if (
        lineage["replay_payload_fingerprint"]
        != lineage["processed_payload_fingerprint"]
    ):
        raise ValueError(f"{event_type} replay payload does not match processed receipt")


def _require_receipt_fingerprint(
    event_type: str,
    field_name: str,
    value: Any,
) -> None:
    if not is_canonical_sha256_fingerprint(value):
        raise ValueError(
            f"{event_type} trace lineage {field_name} must be a sha256 fingerprint"
        )


def _validate_pheromone_clip_lineage(event: TraceEventView) -> None:
    event_type = "pheromone_clip"
    lineage = event.lineage
    _require_text_fields(
        event_type,
        lineage,
        {
            "lifecycle",
            "result",
            "source_id",
            "provenance",
            "candidate_id",
            "subject_type",
            "subject_id",
            "kind",
            "source_trace_event_id",
            "trace_event_id",
        },
    )
    if lineage["lifecycle"] not in {"deposit", "diffusion", "feedback"}:
        raise ValueError("pheromone_clip trace lifecycle is unsupported")
    if lineage["result"] not in {"applied", "rejected"}:
        raise ValueError("pheromone_clip trace result is unsupported")
    requested = _require_nonnegative_number(event_type, lineage, "requested_strength")
    applied = _require_nonnegative_number(event_type, lineage, "applied_strength")
    for field_name in ("round_budget_remaining", "source_budget_remaining"):
        _require_nonnegative_number(event_type, lineage, field_name)
    if applied > requested:
        raise ValueError("pheromone_clip trace applied strength must not exceed requested strength")
    if lineage["result"] == "rejected" and applied != 0:
        raise ValueError("rejected pheromone_clip trace must apply zero strength")
    if lineage["result"] == "applied" and applied <= 0:
        raise ValueError("applied pheromone_clip trace must apply positive strength")

    causal_payload = lineage.get("causal_payload")
    causal_fingerprint = lineage.get("causal_fingerprint")
    if lineage["result"] == "rejected" and (
        causal_payload is None or causal_fingerprint is None
    ):
        raise ValueError(
            "rejected pheromone_clip trace requires causal_payload and causal_fingerprint"
        )
    if (causal_payload is None) != (causal_fingerprint is None):
        raise ValueError(
            "pheromone_clip causal payload and fingerprint must be declared together"
        )
    if causal_payload is not None:
        if not isinstance(causal_payload, dict):
            raise ValueError("pheromone_clip causal_payload must be an object")
        if not isinstance(causal_fingerprint, str) or not causal_fingerprint:
            raise ValueError("pheromone_clip causal_fingerprint must be a non-empty string")
        expected_fingerprint = pheromone_clip_payload_fingerprint(causal_payload)
        if causal_fingerprint != expected_fingerprint:
            raise ValueError("pheromone_clip causal payload fingerprint does not match")
        if causal_payload.get("lifecycle") != lineage["lifecycle"]:
            raise ValueError("pheromone_clip causal payload lifecycle does not match")

    lifecycle = lineage["lifecycle"]
    common_transition = {"source_kind", "source_strength", "new_strength", "step"}
    missing = sorted(common_transition - set(lineage))
    if missing:
        raise ValueError(
            f"pheromone_clip {lifecycle} lineage missing required fields: {', '.join(missing)}"
        )
    _require_text_fields(event_type, lineage, {"source_kind"})
    source_strength = _require_nonnegative_number(event_type, lineage, "source_strength")
    new_strength = _require_nonnegative_number(event_type, lineage, "new_strength")
    _require_nonnegative_integer(event_type, lineage, "step")
    if lifecycle == "deposit":
        if lineage["source_trace_event_id"] != lineage["trace_event_id"]:
            raise ValueError("deposit pheromone_clip trace identity is inconsistent")
        if source_strength != 0 or not isclose(new_strength, applied, abs_tol=1e-9):
            raise ValueError("deposit pheromone_clip trace does not reconstruct transition")
        if lineage["source_kind"] != lineage["kind"]:
            raise ValueError("deposit pheromone_clip trace must preserve kind")
        if causal_payload is not None:
            _validate_deposit_clip_payload(event, causal_payload)
        return
    if lifecycle == "diffusion":
        required = {
            "source_subject",
            "target_subject",
            "hop",
            "attenuation",
            "policy_attenuation",
            "edge_attenuation",
            "root_trace_event_id",
        }
        missing = sorted(required - set(lineage))
        if missing:
            raise ValueError(
                f"pheromone_clip diffusion lineage missing required fields: {', '.join(missing)}"
            )
        _require_subject(event_type, lineage, "source_subject")
        _require_subject(event_type, lineage, "target_subject")
        _require_text_fields(event_type, lineage, {"root_trace_event_id"})
        _require_positive_integer(event_type, lineage, "hop")
        attenuation = _finite_number(event_type, "attenuation", lineage["attenuation"])
        policy_attenuation = _finite_number(
            event_type,
            "policy_attenuation",
            lineage["policy_attenuation"],
        )
        edge_attenuation = _finite_number(
            event_type,
            "edge_attenuation",
            lineage["edge_attenuation"],
        )
        if not all(0 <= value <= 1 for value in (attenuation, policy_attenuation, edge_attenuation)):
            raise ValueError("pheromone_clip diffusion attenuation must be between zero and one")
        if not isclose(attenuation, policy_attenuation * edge_attenuation, abs_tol=1e-9):
            raise ValueError("pheromone_clip diffusion attenuation factors do not reconstruct")
        if not isclose(requested, source_strength * attenuation, abs_tol=1e-9):
            raise ValueError("pheromone_clip diffusion request is not causally derived")
        if applied != 0 or new_strength != 0 or lineage["result"] != "rejected":
            raise ValueError("pheromone_clip diffusion must record a rejected transition")
        _validate_diffusion_clip_payload(event, causal_payload)
        return
    required = {"outcome", "reward", "feedback_trace_event_id"}
    missing = sorted(required - set(lineage))
    if missing:
        raise ValueError(
            f"pheromone_clip feedback lineage missing required fields: {', '.join(missing)}"
        )
    _require_text_fields(event_type, lineage, {"outcome", "feedback_trace_event_id"})
    _finite_number(event_type, "reward", lineage["reward"])
    if "strength_delta" not in lineage:
        raise ValueError("pheromone_clip feedback lineage missing required field: strength_delta")
    strength_delta = _require_nonnegative_number(
        event_type,
        lineage,
        "strength_delta",
    )
    expected_requested = abs(
        strength_delta if strength_delta != 0.0 else float(lineage["reward"])
    )
    if not isclose(requested, expected_requested, abs_tol=1e-9):
        raise ValueError("pheromone_clip feedback request is not causally derived")
    if applied != 0 or not isclose(new_strength, source_strength, abs_tol=1e-9):
        raise ValueError("pheromone_clip feedback must record an unchanged rejected transition")
    _validate_feedback_clip_payload(event, causal_payload)


_TRAIL_PAYLOAD_FIELDS = frozenset(
    {
        "candidate_id",
        "strength",
        "subject_type",
        "subject_id",
        "target",
        "route_id",
        "tool_id",
        "kind",
        "source_id",
        "source_role",
        "evidence_id",
        "provenance",
        "trace_event_id",
        "deposited_at_step",
        "updated_at_step",
        "ttl_steps",
        "lineage_event_ids",
        "diffusion_root_trace_event_id",
        "diffusion_parent_trace_event_id",
        "diffusion_hop",
    }
)


def _validate_deposit_clip_payload(
    event: TraceEventView,
    payload: dict[str, Any],
) -> None:
    _require_exact_payload_fields(
        payload,
        {"lifecycle", "input", "effective"},
        "deposit causal payload",
    )
    item = _require_payload_object(payload, "input", "deposit causal payload")
    effective = _require_payload_object(payload, "effective", "deposit causal payload")
    _validate_trail_payload(item, "deposit causal payload.input")
    _require_exact_payload_fields(
        effective,
        {"target", "candidate_id", "subject_type", "subject_id", "source_id"},
        "deposit causal payload.effective",
    )
    _require_payload_text_fields(
        effective,
        {"target", "candidate_id", "subject_type", "subject_id", "source_id"},
        "deposit causal payload.effective",
        allow_empty=False,
    )
    raw_effective = _trail_payload_effective(item)
    if effective != raw_effective:
        raise ValueError("deposit causal payload effective binding does not match input trail")
    lineage = event.lineage
    expected = {
        "candidate_id": effective["candidate_id"],
        "subject_type": effective["subject_type"],
        "subject_id": effective["subject_id"],
        "source_id": effective["source_id"],
        "kind": item["kind"],
        "provenance": item["provenance"],
        "trace_event_id": item["trace_event_id"],
        "source_trace_event_id": item["trace_event_id"],
    }
    if event.target != effective["target"] or any(
        lineage.get(field_name) != value for field_name, value in expected.items()
    ):
        raise ValueError("deposit pheromone_clip causal payload does not bind trace lineage")
    if not isclose(
        float(lineage["requested_strength"]),
        float(item["strength"]),
        abs_tol=1e-9,
    ):
        raise ValueError("deposit pheromone_clip request does not match causal input")
    if lineage["step"] != item["updated_at_step"]:
        raise ValueError("deposit pheromone_clip step does not match causal input")


def _validate_feedback_clip_payload(
    event: TraceEventView,
    payload: dict[str, Any],
) -> None:
    _require_exact_payload_fields(
        payload,
        {"lifecycle", "input", "source_state"},
        "feedback causal payload",
    )
    item = _require_payload_object(payload, "input", "feedback causal payload")
    source = _require_payload_object(payload, "source_state", "feedback causal payload")
    _require_exact_payload_fields(
        item,
        {
            "source_id",
            "subject_type",
            "subject_id",
            "candidate_id",
            "target",
            "outcome",
            "reward",
            "strength_delta",
            "evidence_id",
            "provenance",
            "trace_event_id",
            "step",
        },
        "feedback causal payload.input",
    )
    _require_payload_text_fields(
        item,
        {
            "source_id",
            "subject_type",
            "subject_id",
            "candidate_id",
            "target",
            "outcome",
            "provenance",
            "trace_event_id",
        },
        "feedback causal payload.input",
        allow_empty=False,
    )
    _require_payload_text_fields(
        item,
        {"evidence_id"},
        "feedback causal payload.input",
        allow_empty=True,
    )
    _finite_number("pheromone_clip", "causal_payload.input.reward", item["reward"])
    strength_delta = _finite_number(
        "pheromone_clip",
        "causal_payload.input.strength_delta",
        item["strength_delta"],
    )
    if strength_delta < 0:
        raise ValueError("feedback causal payload strength_delta must be non-negative")
    _require_nonnegative_integer("pheromone_clip", item, "step")
    _require_exact_payload_fields(
        source,
        {"trace_event_id", "strength", "kind", "provenance"},
        "feedback causal payload.source_state",
    )
    _require_payload_text_fields(
        source,
        {"trace_event_id", "kind", "provenance"},
        "feedback causal payload.source_state",
        allow_empty=False,
    )
    _require_nonnegative_number("pheromone_clip", source, "strength")
    if float(source["strength"]) == 0.0:
        expected_kind = {
            "success": "positive",
            "failure": "negative",
            "blocked": "cautionary",
            "congested": "cautionary",
            "hazard": "alarm",
            "novel": "novelty",
            "stale": "stale",
        }.get(item["outcome"])
        if (
            source["trace_event_id"] != item["trace_event_id"]
            or source["kind"] != expected_kind
            or source["provenance"] != item["provenance"]
        ):
            raise ValueError(
                "feedback causal payload new-memory source state does not match input"
            )
    lineage = event.lineage
    expected = {
        "source_id": item["source_id"],
        "candidate_id": item["candidate_id"],
        "subject_type": item["subject_type"],
        "subject_id": item["subject_id"],
        "outcome": item["outcome"],
        "reward": item["reward"],
        "strength_delta": item["strength_delta"],
        "feedback_trace_event_id": item["trace_event_id"],
        "trace_event_id": item["trace_event_id"],
        "source_trace_event_id": source["trace_event_id"],
        "source_strength": source["strength"],
        "source_kind": source["kind"],
        "provenance": source["provenance"],
        "step": item["step"],
    }
    if event.target != item["target"]:
        raise ValueError("feedback pheromone_clip target does not match causal input")
    for field_name, value in expected.items():
        observed = lineage.get(field_name)
        if isinstance(value, Real) and not isinstance(value, bool):
            if not isclose(float(observed), float(value), abs_tol=1e-9):
                raise ValueError(
                    f"feedback pheromone_clip causal payload mismatch: {field_name}"
                )
        elif observed != value:
            raise ValueError(
                f"feedback pheromone_clip causal payload mismatch: {field_name}"
            )
    expected_requested = abs(
        float(item["strength_delta"])
        if float(item["strength_delta"]) != 0.0
        else float(item["reward"])
    )
    if not isclose(float(lineage["requested_strength"]), expected_requested, abs_tol=1e-9):
        raise ValueError("feedback pheromone_clip request does not match causal payload")


def _validate_diffusion_clip_payload(
    event: TraceEventView,
    payload: dict[str, Any],
) -> None:
    _require_exact_payload_fields(
        payload,
        {"lifecycle", "input", "effective"},
        "diffusion causal payload",
    )
    item = _require_payload_object(payload, "input", "diffusion causal payload")
    effective = _require_payload_object(payload, "effective", "diffusion causal payload")
    _require_exact_payload_fields(
        item,
        {
            "source_trail",
            "target_subject",
            "edge",
            "policy_attenuation",
            "hop",
            "parent_trace_event_id",
            "derived_trace_event_id",
        },
        "diffusion causal payload.input",
    )
    source_trail = _require_payload_object(
        item,
        "source_trail",
        "diffusion causal payload.input",
    )
    target_subject = _require_payload_object(
        item,
        "target_subject",
        "diffusion causal payload.input",
    )
    edge = _require_payload_object(item, "edge", "diffusion causal payload.input")
    _validate_trail_payload(source_trail, "diffusion causal payload.input.source_trail")
    _require_exact_payload_fields(
        target_subject,
        {"subject_type", "subject_id", "candidate_id", "target"},
        "diffusion causal payload.input.target_subject",
    )
    _require_payload_text_fields(
        target_subject,
        {"subject_type", "subject_id", "candidate_id", "target"},
        "diffusion causal payload.input.target_subject",
        allow_empty=False,
    )
    _require_exact_payload_fields(
        edge,
        {
            "source_subject_type",
            "source_subject_id",
            "target_subject_type",
            "target_subject_id",
            "attenuation",
        },
        "diffusion causal payload.input.edge",
    )
    _require_payload_text_fields(
        edge,
        {
            "source_subject_type",
            "source_subject_id",
            "target_subject_type",
            "target_subject_id",
        },
        "diffusion causal payload.input.edge",
        allow_empty=False,
    )
    for mapping, field_name in (
        (item, "policy_attenuation"),
        (edge, "attenuation"),
    ):
        value = _finite_number("pheromone_clip", field_name, mapping[field_name])
        if not 0 <= value <= 1:
            raise ValueError("diffusion causal payload attenuation must be between zero and one")
    _require_positive_integer("pheromone_clip", item, "hop")
    _require_payload_text_fields(
        item,
        {"parent_trace_event_id", "derived_trace_event_id"},
        "diffusion causal payload.input",
        allow_empty=False,
    )
    _require_exact_payload_fields(
        effective,
        {
            "target",
            "candidate_id",
            "subject_type",
            "subject_id",
            "source_id",
            "source_kind",
            "source_strength",
            "root_trace_event_id",
        },
        "diffusion causal payload.effective",
    )
    _require_payload_text_fields(
        effective,
        {
            "target",
            "candidate_id",
            "subject_type",
            "subject_id",
            "source_id",
            "source_kind",
            "root_trace_event_id",
        },
        "diffusion causal payload.effective",
        allow_empty=False,
    )
    _require_nonnegative_number("pheromone_clip", effective, "source_strength")
    source_effective = _trail_payload_effective(source_trail)
    expected_effective = {
        "target": target_subject["target"] or source_effective["target"],
        "candidate_id": (
            target_subject["candidate_id"] or source_effective["candidate_id"]
        ),
        "subject_type": target_subject["subject_type"],
        "subject_id": target_subject["subject_id"],
        "source_id": source_effective["source_id"],
        "source_kind": source_trail["kind"],
        "source_strength": source_trail["strength"],
        "root_trace_event_id": (
            source_trail["diffusion_root_trace_event_id"]
            or source_trail["trace_event_id"]
        ),
    }
    if effective != expected_effective:
        raise ValueError("diffusion causal payload effective binding does not match input")
    if (
        edge["source_subject_type"] != source_effective["subject_type"]
        or edge["source_subject_id"] != source_effective["subject_id"]
        or edge["target_subject_type"] != target_subject["subject_type"]
        or edge["target_subject_id"] != target_subject["subject_id"]
        or item["parent_trace_event_id"] != source_trail["trace_event_id"]
    ):
        raise ValueError("diffusion causal payload topology does not match input trail")
    lineage = event.lineage
    expected_subjects = {
        "source_subject": {
            "type": edge["source_subject_type"],
            "id": edge["source_subject_id"],
        },
        "target_subject": {
            "type": target_subject["subject_type"],
            "id": target_subject["subject_id"],
        },
    }
    expected = {
        "candidate_id": effective["candidate_id"],
        "subject_type": effective["subject_type"],
        "subject_id": effective["subject_id"],
        "source_id": effective["source_id"],
        "source_kind": effective["source_kind"],
        "kind": effective["source_kind"],
        "provenance": source_trail["provenance"],
        "source_trace_event_id": item["parent_trace_event_id"],
        "trace_event_id": item["derived_trace_event_id"],
        "root_trace_event_id": effective["root_trace_event_id"],
        "hop": item["hop"],
        "policy_attenuation": item["policy_attenuation"],
        "edge_attenuation": edge["attenuation"],
        "source_strength": effective["source_strength"],
        "step": source_trail["updated_at_step"],
    }
    if event.target != effective["target"]:
        raise ValueError("diffusion pheromone_clip target does not match causal payload")
    for field_name, value in {**expected_subjects, **expected}.items():
        observed = lineage.get(field_name)
        if isinstance(value, Real) and not isinstance(value, bool):
            if not isclose(float(observed), float(value), abs_tol=1e-9):
                raise ValueError(
                    f"diffusion pheromone_clip causal payload mismatch: {field_name}"
                )
        elif observed != value:
            raise ValueError(
                f"diffusion pheromone_clip causal payload mismatch: {field_name}"
            )


def _validate_trail_payload(item: dict[str, Any], path: str) -> None:
    _require_exact_payload_fields(item, set(_TRAIL_PAYLOAD_FIELDS), path)
    _require_payload_text_fields(
        item,
        {
            "candidate_id",
            "subject_type",
            "subject_id",
            "target",
            "route_id",
            "tool_id",
            "kind",
            "source_id",
            "source_role",
            "evidence_id",
            "provenance",
            "trace_event_id",
            "diffusion_root_trace_event_id",
            "diffusion_parent_trace_event_id",
        },
        path,
        allow_empty=True,
    )
    for field_name in ("subject_type", "kind", "provenance", "trace_event_id"):
        if not item[field_name]:
            raise ValueError(f"{path}.{field_name} must be non-empty")
    _require_nonnegative_number("pheromone_clip", item, "strength")
    for field_name in ("deposited_at_step", "updated_at_step", "diffusion_hop"):
        _require_nonnegative_integer("pheromone_clip", item, field_name)
    ttl_steps = item["ttl_steps"]
    if ttl_steps is not None and (
        isinstance(ttl_steps, bool) or not isinstance(ttl_steps, int) or ttl_steps < 0
    ):
        raise ValueError(f"{path}.ttl_steps must be null or a non-negative integer")
    lineage_ids = item["lineage_event_ids"]
    if not isinstance(lineage_ids, list) or any(
        not isinstance(trace_id, str) or not trace_id
        for trace_id in lineage_ids
    ):
        raise ValueError(f"{path}.lineage_event_ids must be an array of non-empty strings")
    if item["trace_event_id"] not in lineage_ids:
        raise ValueError(f"{path}.lineage_event_ids must contain trace_event_id")


def _trail_payload_effective(item: dict[str, Any]) -> dict[str, str]:
    if item["subject_id"]:
        subject_type = item["subject_type"]
        subject_id = item["subject_id"]
    elif item["candidate_id"]:
        subject_type = "candidate"
        subject_id = item["candidate_id"]
    elif item["route_id"]:
        subject_type = "route"
        subject_id = item["route_id"]
    elif item["tool_id"]:
        subject_type = "tool"
        subject_id = item["tool_id"]
    else:
        subject_type = item["subject_type"]
        subject_id = ""
    candidate_id = item["candidate_id"]
    if not candidate_id and subject_type == "candidate":
        candidate_id = subject_id
    return {
        "target": item["target"],
        "candidate_id": candidate_id,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "source_id": item["source_id"] or item["provenance"],
    }


def _require_payload_object(
    payload: dict[str, Any],
    field_name: str,
    path: str,
) -> dict[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, dict):
        raise ValueError(f"{path}.{field_name} must be an object")
    return value


def _require_exact_payload_fields(
    payload: dict[str, Any],
    expected: set[str],
    path: str,
) -> None:
    if set(payload) != expected:
        raise ValueError(f"{path} fields do not match the canonical contract")


def _require_payload_text_fields(
    payload: dict[str, Any],
    fields: set[str],
    path: str,
    *,
    allow_empty: bool,
) -> None:
    for field_name in fields:
        value = payload.get(field_name)
        if not isinstance(value, str) or (not allow_empty and not value):
            qualifier = "a string" if allow_empty else "a non-empty string"
            raise ValueError(f"{path}.{field_name} must be {qualifier}")


def _validate_pheromone_observation(event: TraceEventView) -> None:
    lineage = event.lineage
    event_type = event.event_type
    if {"lifecycle", "result"} & set(lineage):
        required = {
            "lifecycle",
            "source_trace_event_id",
            "result",
            "replay_payload",
            "replay_payload_fingerprint",
            "processed_payload_fingerprint",
        }
        missing = sorted(required - set(lineage))
        if missing:
            raise ValueError(
                f"pheromone_observe replay lineage missing required fields: {', '.join(missing)}"
            )
        _require_text_fields(event_type, lineage, {"lifecycle", "source_trace_event_id", "result"})
        if lineage["result"] != "replay_ignored":
            raise ValueError("pheromone_observe replay lineage result must be replay_ignored")
        if lineage["lifecycle"] not in {"deposit", "diffusion", "feedback"}:
            raise ValueError("pheromone_observe replay lineage has an unsupported lifecycle")
        if set(lineage) != required:
            raise ValueError(
                "pheromone_observe replay lineage must contain exactly the replay receipt fields"
            )
        _require_matching_replay_fingerprints(event_type, lineage)
        return
    if {
        "candidate_id",
        "subject_type",
        "subject_id",
        "novelty_pressure",
        "reopen_eligible",
    } & set(lineage):
        required = {
            "candidate_id",
            "subject_type",
            "subject_id",
            "novelty_pressure",
            "reopen_eligible",
            "source_trace_event_id",
        }
        missing = sorted(required - set(lineage))
        if missing:
            raise ValueError(f"pheromone_observe trace lineage missing required fields: {', '.join(missing)}")
        _require_text_fields(
            event_type,
            lineage,
            {"candidate_id", "subject_type", "subject_id", "source_trace_event_id"},
        )
        _require_nonnegative_number(event_type, lineage, "novelty_pressure")
        _require_boolean(event_type, lineage, "reopen_eligible")
        if set(lineage) != required:
            raise ValueError(
                "pheromone_observe exploration lineage must contain exactly the state fields"
            )
        return
    if {"exploration_floor", "candidate_ids"} & set(lineage):
        required = {"exploration_floor", "candidate_ids"}
        missing = sorted(required - set(lineage))
        if missing:
            raise ValueError(
                f"pheromone_observe exploration lineage missing required fields: {', '.join(missing)}"
            )
        _require_nonnegative_number(event_type, lineage, "exploration_floor")
        _require_nonempty_text_sequence(event_type, lineage, "candidate_ids")
        if set(lineage) != required:
            raise ValueError(
                "pheromone_observe exploration floor lineage must contain exactly the floor fields"
            )
        return
    raise ValueError("pheromone_observe trace lineage does not match a supported observation variant")


def _require_text_fields(event_type: str, lineage: dict[str, Any], fields: Iterable[str]) -> None:
    for field_name in fields:
        value = lineage[field_name]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{event_type} trace lineage {field_name} must be a non-empty string")


def _finite_number(event_type: str, field_name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)):
        raise ValueError(f"{event_type} trace lineage {field_name} must be a finite number")
    return float(value)


def _require_finite_fields(event_type: str, lineage: dict[str, Any], fields: Iterable[str]) -> None:
    for field_name in fields:
        _finite_number(event_type, field_name, lineage[field_name])


def _require_nonnegative_number(event_type: str, lineage: dict[str, Any], field_name: str) -> float:
    value = _finite_number(event_type, field_name, lineage[field_name])
    if value < 0:
        raise ValueError(f"{event_type} trace lineage {field_name} must be non-negative")
    return value


def _require_nonnegative_integer(event_type: str, lineage: dict[str, Any], field_name: str) -> None:
    value = lineage[field_name]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{event_type} trace lineage {field_name} must be a non-negative integer")


def _require_positive_integer(event_type: str, lineage: dict[str, Any], field_name: str) -> None:
    value = lineage[field_name]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{event_type} trace lineage {field_name} must be a positive integer")


def _require_boolean(event_type: str, lineage: dict[str, Any], field_name: str) -> None:
    if not isinstance(lineage[field_name], bool):
        raise ValueError(f"{event_type} trace lineage {field_name} must be a boolean")


def _require_nonempty_mapping(event_type: str, lineage: dict[str, Any], field_name: str) -> None:
    value = lineage[field_name]
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{event_type} trace lineage {field_name} must be a non-empty object")


def _validate_budget_result(event_type: str, value: Any) -> None:
    required = {"round_remaining", "source_remaining", "status"}
    if not isinstance(value, dict) or not required.issubset(value):
        raise ValueError(
            f"{event_type} trace lineage budget_result must contain round_remaining, "
            "source_remaining, and status"
        )
    _require_nonnegative_number(event_type, value, "round_remaining")
    _require_nonnegative_number(event_type, value, "source_remaining")
    if value["status"] not in {"applied", "rejected"}:
        raise ValueError(f"{event_type} trace lineage budget_result status is unsupported")


def _require_score_mapping(event_type: str, lineage: dict[str, Any], field_name: str) -> None:
    value = lineage[field_name]
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{event_type} trace lineage {field_name} must be a non-empty score object")
    for key, score in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{event_type} trace lineage {field_name} keys must be non-empty strings")
        _finite_number(event_type, f"{field_name}.{key}", score)


def _require_bounded_score_mapping(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
    *,
    minimum: float,
    maximum: float | None = None,
) -> None:
    """Validate a numeric map whose values carry field-specific ABI bounds."""

    _require_score_mapping(event_type, lineage, field_name)
    for key, raw_value in lineage[field_name].items():
        value = float(raw_value)
        if value < minimum or (maximum is not None and value > maximum):
            bounds = (
                f"between {minimum:g} and {maximum:g}"
                if maximum is not None
                else f"at least {minimum:g}"
            )
            raise ValueError(
                f"{event_type} trace lineage {field_name}.{key} must be {bounds}"
            )


def _require_declared_layer_score_mapping(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
    *,
    minimum: float,
    maximum: float | None = None,
) -> None:
    _require_bounded_score_mapping(
        event_type,
        lineage,
        field_name,
        minimum=minimum,
        maximum=maximum,
    )
    observed = set(lineage[field_name])
    if observed != set(DECLARED_COORDINATION_LAYER_IDS):
        raise ValueError(
            f"{event_type} trace lineage {field_name} must contain exactly the declared layer ids"
        )


def _require_layer_snapshots(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
) -> None:
    snapshots = lineage[field_name]
    if not isinstance(snapshots, dict) or set(snapshots) != set(
        DECLARED_COORDINATION_LAYER_IDS
    ):
        raise ValueError(
            f"{event_type} trace lineage {field_name} must contain exactly the declared layer ids"
        )
    rate_fields = LAYER_SNAPSHOT_FIELDS - {"present"}
    for layer_id, snapshot in snapshots.items():
        if not isinstance(snapshot, dict) or set(snapshot) != set(LAYER_SNAPSHOT_FIELDS):
            raise ValueError(
                f"{event_type} trace lineage {field_name}.{layer_id} must contain the complete snapshot"
            )
        if not isinstance(snapshot["present"], bool):
            raise ValueError(
                f"{event_type} trace lineage {field_name}.{layer_id}.present must be a boolean"
            )
        for metric in rate_fields:
            value = _finite_number(
                event_type,
                f"{field_name}.{layer_id}.{metric}",
                snapshot[metric],
            )
            if not 0 <= value <= 1:
                raise ValueError(
                    f"{event_type} trace lineage {field_name}.{layer_id}.{metric} "
                    "must be between 0 and 1"
                )
            if not snapshot["present"] and value != 0:
                raise ValueError(
                    f"{event_type} trace lineage {field_name}.{layer_id}.{metric} "
                    "must be zero when the snapshot is absent"
                )


def _require_text_mapping(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
) -> None:
    value = lineage[field_name]
    if not isinstance(value, dict):
        raise ValueError(f"{event_type} trace lineage {field_name} must be an object")
    if any(
        not isinstance(key, str)
        or not key.strip()
        or not isinstance(item, str)
        or not item.strip()
        for key, item in value.items()
    ):
        raise ValueError(
            f"{event_type} trace lineage {field_name} must contain non-empty string entries"
        )


def _require_bounded_mapping(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
    *,
    minimum: float,
    maximum: float,
) -> None:
    value = lineage[field_name]
    if not isinstance(value, dict):
        raise ValueError(f"{event_type} trace lineage {field_name} must be an object")
    for key, raw_value in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(
                f"{event_type} trace lineage {field_name} keys must be non-empty strings"
            )
        number = _finite_number(event_type, f"{field_name}.{key}", raw_value)
        if not minimum <= number <= maximum:
            raise ValueError(
                f"{event_type} trace lineage {field_name}.{key} must be between "
                f"{minimum:g} and {maximum:g}"
            )


def _require_recursive_coverage(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
) -> None:
    """Validate arbitrarily grouped coverage leaves as finite ratios.

    Coordination may group coverage by layer or expose aggregate coverage
    fields.  The grouping is extensible, but every leaf has the same ratio
    semantics and therefore must remain within ``[0, 1]``.
    """

    value = lineage[field_name]
    if not isinstance(value, dict) or not value:
        raise ValueError(
            f"{event_type} trace lineage {field_name} must be a non-empty coverage object"
        )

    def validate_node(node: dict[str, Any], path: str) -> None:
        for key, child in node.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(
                    f"{event_type} trace lineage {path} keys must be non-empty strings"
                )
            child_path = f"{path}.{key}"
            if isinstance(child, dict):
                # Empty groups are valid when no confirmations exist; they do
                # not smuggle an unvalidated leaf into the trace.
                validate_node(child, child_path)
                continue
            ratio = _finite_number(event_type, child_path, child)
            if not 0 <= ratio <= 1:
                raise ValueError(
                    f"{event_type} trace lineage {child_path} must be between 0 and 1"
                )

    validate_node(value, field_name)


def _validate_policy_adjustment_lineage(lineage: dict[str, Any]) -> None:
    """Validate adjustment values and their declared authority envelope."""

    event_type = "policy_adjustment"
    proposed = lineage["proposed_values"]
    declared = lineage["declared_bounds"]
    if set(proposed) != set(declared):
        raise ValueError(
            "policy_adjustment trace proposed values and declared bounds must cover the same fields"
        )

    for field_name, value in proposed.items():
        if not isinstance(field_name, str) or not field_name.strip():
            raise ValueError(
                "policy_adjustment trace lineage proposed_values keys must be non-empty strings"
            )
        _validate_adjustment_scalar(event_type, f"proposed_values.{field_name}", value)
        bound = _validate_adjustment_bound(field_name, declared[field_name])
        if (
            lineage["result"] in {"accepted", "replay_ignored"}
            and not _adjustment_value_within_bound(value, bound)
        ):
            raise ValueError(
                "policy_adjustment trace accepted or replayed value is outside "
                f"declared bounds: {field_name}"
            )


def _validate_adjustment_bound(field_name: str, raw_bound: Any) -> tuple[str, tuple[Any, ...]]:
    event_type = "policy_adjustment"
    path = f"declared_bounds.{field_name}"
    if isinstance(raw_bound, (list, tuple)) and len(raw_bound) == 2:
        lower = _finite_number(event_type, f"{path}[0]", raw_bound[0])
        upper = _finite_number(event_type, f"{path}[1]", raw_bound[1])
        if lower > upper:
            raise ValueError(
                f"policy_adjustment trace lineage {path} numeric bounds must be ordered"
            )
        return "numeric", (lower, upper)
    if isinstance(raw_bound, dict) and set(raw_bound) == {"min", "max"}:
        lower = _finite_number(event_type, f"{path}.min", raw_bound["min"])
        upper = _finite_number(event_type, f"{path}.max", raw_bound["max"])
        if lower > upper:
            raise ValueError(
                f"policy_adjustment trace lineage {path} numeric bounds must be ordered"
            )
        return "numeric", (lower, upper)
    if isinstance(raw_bound, dict) and set(raw_bound) == {"allowed_values"}:
        allowed = raw_bound["allowed_values"]
        if not isinstance(allowed, (list, tuple)) or not allowed:
            raise ValueError(
                f"policy_adjustment trace lineage {path}.allowed_values must be a non-empty array"
            )
        for index, item in enumerate(allowed):
            _validate_adjustment_scalar(event_type, f"{path}.allowed_values[{index}]", item)
        return "allowed_values", tuple(allowed)
    raise ValueError(
        f"policy_adjustment trace lineage {path} must declare numeric bounds or allowed_values"
    )


def _validate_adjustment_scalar(event_type: str, path: str, value: Any) -> None:
    if isinstance(value, bool):
        raise ValueError(f"{event_type} trace lineage {path} must be a finite number or string")
    if isinstance(value, Real):
        _finite_number(event_type, path, value)
        return
    if isinstance(value, str) and value.strip():
        return
    raise ValueError(f"{event_type} trace lineage {path} must be a finite number or string")


def _adjustment_value_within_bound(
    value: Any,
    bound: tuple[str, tuple[Any, ...]],
) -> bool:
    kind, values = bound
    if kind == "numeric":
        if isinstance(value, bool) or not isinstance(value, Real):
            return False
        lower, upper = values
        return float(lower) <= float(value) <= float(upper)
    return any(type(value) is type(allowed) and value == allowed for allowed in values)


def _require_count_mapping(event_type: str, lineage: dict[str, Any], field_name: str) -> None:
    value = lineage[field_name]
    if not isinstance(value, dict):
        raise ValueError(f"{event_type} trace lineage {field_name} must be an object")
    for key, count in value.items():
        if not isinstance(key, str) or not key or isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"{event_type} trace lineage {field_name} must contain non-negative integer counts")


def _require_nonempty_text_sequence(event_type: str, lineage: dict[str, Any], field_name: str) -> None:
    _require_text_sequence(event_type, lineage, field_name, allow_empty=False)


def _require_text_sequence(
    event_type: str,
    lineage: dict[str, Any],
    field_name: str,
    *,
    allow_empty: bool,
) -> None:
    value = lineage[field_name]
    if not isinstance(value, (list, tuple)) or (not value and not allow_empty):
        qualifier = "an array" if allow_empty else "a non-empty array"
        raise ValueError(f"{event_type} trace lineage {field_name} must be {qualifier}")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{event_type} trace lineage {field_name} must contain non-empty strings")


def _require_subject(event_type: str, lineage: dict[str, Any], field_name: str) -> None:
    value = lineage[field_name]
    if not isinstance(value, dict) or not {"type", "id"}.issubset(value):
        raise ValueError(f"{event_type} trace lineage {field_name} must contain type and id")
    _require_text_fields(event_type, value, {"type", "id"})


# Preserve the historical package-root identity of public callables.  The
# facade binds these same objects; no wrapper layer changes signatures.
canonical_pheromone_clip_payload.__module__ = "pheroos.trace"
pheromone_clip_payload_fingerprint.__module__ = "pheroos.trace"


__all__: tuple[str, ...] = ()
