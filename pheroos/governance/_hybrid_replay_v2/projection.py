"""Exact, authority-free projections for durable Hybrid replay v2.

This module is deliberately a pure translation layer.  It can project an
already issued Hybrid v1 step into the closed v2 wire and reconstruct
ephemeral v1 inputs from a validated snapshot, but it never treats portable
bytes as authority.  StateStore inclusion/currentness and the opaque verified
wrapper live in the operations layer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from typing import Any, cast

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _compute_root,
)
from pheroos.governance._hybrid_replay_v2.canonical import (
    _canonical_hybrid_value_v2,
)
from pheroos.governance._hybrid_replay_v2.contracts import (
    HYBRID_REPLAY_GENESIS_SNAPSHOT_ROOT_V2,
    HYBRID_REPLAY_DIFFUSION_REPLAY_VERSION_V2,
    HybridReplayAdvanceRequestV2,
    HybridReplaySnapshotV2,
    hybrid_replay_diffusion_source_trail_root_v2,
    hybrid_replay_stream_ref_v2,
    hybrid_replay_transition_id_v2,
)
from pheroos.governance._hybrid_replay_v2.numeric import (
    decode_binary64_v1,
    encode_binary64_v1,
)
from pheroos.governance._hybrid_replay_v2.source import (
    VerifiedHybridSourceStepV2,
    _VerifiedHybridSourceMaterialV2,
    _require_hybrid_source_authority_context_v2,
    _verified_hybrid_source_material_v2,
)
from pheroos.governance._pheromone.lifecycle import PheromoneBudgetState
from pheroos.governance._pheromone.records import (
    PheromoneEdge,
    PheromoneNeighborhood,
    PheromoneSubject,
    PheromoneTrail,
)
from pheroos.governance._swarm.records import HybridCollectiveStep, HybridReplayState
from pheroos.governance.candidate import Candidate, CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.models import CollectiveDecisionPolicy, PheromoneKindProfile
from pheroos.trace import TraceEvent
from pheroos.trace._lineage_types import PHEROMONE_CLIP_PAYLOAD_VERSION
from pheroos.trace._pheromone_receipts import canonical_pheromone_clip_payload


_LAYERS = ("evolutionary", "learned", "metacognitive", "reactive")
_BINARY64_POLICY_FIELDS = (
    "pheromone_evaporation_rate",
    "pheromone_min_strength",
    "pheromone_max_strength",
    "pheromone_positive_weight",
    "pheromone_negative_weight",
    "pheromone_cautionary_weight",
    "pheromone_cautionary_override_threshold",
    "pheromone_novelty_weight",
    "pheromone_per_source_cap",
    "pheromone_per_round_deposit_cap",
    "pheromone_activation_threshold",
    "pheromone_saturation_threshold",
    "pheromone_exploration_floor",
    "pheromone_diffusion_attenuation",
    "exploration_floor",
    "novelty_decay_rate",
    "stale_route_reopen_threshold",
    "layer_conflict_threshold",
    "layer_emergency_override_threshold",
)
_TEXT_ADJUSTMENT_FIELDS = frozenset({"pheromone_response_model"})


@dataclass(frozen=True, slots=True)
class RestoredHybridReplayInputsV2:
    """Ephemeral compatibility inputs reconstructed without granting authority."""

    replay_state: HybridReplayState
    effective_policy: CollectiveDecisionPolicy
    topology: PheromoneNeighborhood
    budget_state: PheromoneBudgetState


def _exact_float(value: object, label: str) -> float:
    if type(value) is not float:
        raise TypeError(f"{label} must be an exact binary64 float")
    # Round-trip through the frozen wire also rejects non-finite values.
    return decode_binary64_v1(encode_binary64_v1(value, label), label)


def _encode_model_number(value: object, label: str) -> str:
    """Normalize numeric protocol-model leaves onto the binary64 wire.

    Protocol manifests historically accept JSON integer spellings for fields
    whose ABI meaning is binary64.  The v2 wire freezes the interpreted value,
    not the incidental JSON token type.
    """

    if type(value) not in (int, float):
        raise TypeError(f"{label} must be a finite protocol number")
    return encode_binary64_v1(float(cast(int | float, value)), label)


def _policy_projection(policy: CollectiveDecisionPolicy) -> dict[str, object]:
    if type(policy) is not CollectiveDecisionPolicy:
        raise TypeError("Hybrid replay policy must be exact CollectiveDecisionPolicy")
    if policy.extensions:
        raise GovernanceError(
            "Hybrid replay v2 cannot omit active policy extension semantics"
        )
    projection: dict[str, object] = {
        "mode": policy.mode,
        "min_independent_scouts": policy.min_independent_scouts,
        "quorum_threshold": policy.quorum_threshold,
        "recruitment_enabled": policy.recruitment_enabled,
        "inhibition_enabled": policy.inhibition_enabled,
        "pheromone_enabled": policy.pheromone_enabled,
        "pheromone_decay_model": policy.pheromone_decay_model,
        "pheromone_min_source_diversity": policy.pheromone_min_source_diversity,
        "pheromone_require_provenance": policy.pheromone_require_provenance,
        "pheromone_require_trace": policy.pheromone_require_trace,
        "pheromone_scored_subject_types": sorted(policy.pheromone_scored_subject_types),
        "pheromone_response_model": policy.pheromone_response_model,
        "pheromone_competition_mode": policy.pheromone_competition_mode,
        "pheromone_diffusion_enabled": policy.pheromone_diffusion_enabled,
        "pheromone_diffusion_max_hops": policy.pheromone_diffusion_max_hops,
        "pheromone_feedback_enabled": policy.pheromone_feedback_enabled,
        "exploration_enabled": policy.exploration_enabled,
        "layer_coordination_enabled": policy.layer_coordination_enabled,
        "layer_min_provenance": policy.layer_min_provenance,
        "layer_fallback_on_unresolved_conflict": (
            policy.layer_fallback_on_unresolved_conflict
        ),
        "fallback_candidate_ref": policy.fallback_candidate,
    }
    for field in _BINARY64_POLICY_FIELDS:
        projection[field] = _encode_model_number(
            getattr(policy, field), f"Hybrid replay policy {field}"
        )
    projection["pheromone_kind_profiles"] = [
        _kind_profile_projection(kind, profile)
        for kind, profile in sorted(policy.pheromone_kind_profiles.items())
    ]
    projection["layer_weight_bounds"] = _layer_bound_projection(
        policy.layer_weight_bounds
    )
    projection["layer_default_weights"] = _layer_value_projection(
        policy.layer_default_weights, "default weight"
    )
    projection["layer_confidence_thresholds"] = _layer_value_projection(
        policy.layer_confidence_thresholds, "confidence threshold"
    )
    projection["policy_adjustment_bounds"] = _adjustment_bound_projection(
        policy.policy_adjustment_bounds
    )
    return projection


def project_collective_policy_v2(
    policy: CollectiveDecisionPolicy,
) -> dict[str, object]:
    """Return the closed canonical projection of one Hybrid policy."""

    return _policy_projection(policy)


def _kind_profile_projection(
    kind: str, profile: PheromoneKindProfile
) -> dict[str, object]:
    if type(kind) is not str or not kind:
        raise TypeError("Hybrid replay pheromone kind must be non-empty text")
    if type(profile) is not PheromoneKindProfile:
        raise TypeError("Hybrid replay kind profile must be exact PheromoneKindProfile")
    if profile.extensions:
        raise GovernanceError(
            "Hybrid replay v2 cannot omit kind-profile extension semantics"
        )
    return {
        "kind": kind,
        "weight": _encode_model_number(profile.weight, f"{kind} weight"),
        "evaporation_rate": (
            None
            if profile.evaporation_rate is None
            else _encode_model_number(
                profile.evaporation_rate, f"{kind} evaporation_rate"
            )
        ),
        "ttl_steps": profile.ttl_steps,
        "response_model": profile.response_model,
        "priority": profile.priority,
        "can_suppress_positive": profile.can_suppress_positive,
        "scored_subject_types": sorted(profile.scored_subject_types),
    }


def _require_all_layers(value: Mapping[str, object], label: str) -> None:
    if set(value) != set(_LAYERS):
        raise GovernanceError(f"Hybrid replay {label} must declare every layer")


def _layer_bound_projection(value: Mapping[str, object]) -> list[dict[str, object]]:
    _require_all_layers(value, "layer weight bounds")
    result: list[dict[str, object]] = []
    for layer in _LAYERS:
        bound = value[layer]
        if type(bound) not in (list, tuple) or len(cast(Sequence[object], bound)) != 2:
            raise TypeError("Hybrid replay layer bound must be an exact pair")
        minimum, maximum = cast(Sequence[object], bound)
        result.append(
            {
                "layer_ref": layer,
                "minimum": _encode_model_number(
                    minimum, f"Hybrid replay {layer} minimum"
                ),
                "maximum": _encode_model_number(
                    maximum, f"Hybrid replay {layer} maximum"
                ),
            }
        )
    return result


def _layer_value_projection(
    value: Mapping[str, object], label: str
) -> list[dict[str, object]]:
    _require_all_layers(value, f"layer {label}s")
    return [
        {
            "layer_ref": layer,
            "value": _encode_model_number(
                value[layer], f"Hybrid replay {layer} {label}"
            ),
        }
        for layer in _LAYERS
    ]


def _adjustment_bound_projection(
    bounds: Mapping[str, object],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for field_ref, bound in sorted(bounds.items()):
        if type(field_ref) is not str or not field_ref:
            raise TypeError("Hybrid replay adjustment bound field must be text")
        if type(bound) in (list, tuple) and len(cast(Sequence[object], bound)) == 2:
            minimum, maximum = cast(Sequence[object], bound)
            result.append(
                {
                    "field_ref": field_ref,
                    "bound_kind": "binary64_range",
                    "minimum": _encode_model_number(
                        minimum, f"Hybrid replay {field_ref} minimum"
                    ),
                    "maximum": _encode_model_number(
                        maximum, f"Hybrid replay {field_ref} maximum"
                    ),
                    "allowed_values": [],
                }
            )
            continue
        if not isinstance(bound, Mapping):
            raise TypeError("Hybrid replay adjustment bound has unsupported shape")
        if set(bound) == {"min", "max"}:
            result.append(
                {
                    "field_ref": field_ref,
                    "bound_kind": "binary64_range",
                    "minimum": _encode_model_number(
                        bound["min"], f"Hybrid replay {field_ref} minimum"
                    ),
                    "maximum": _encode_model_number(
                        bound["max"], f"Hybrid replay {field_ref} maximum"
                    ),
                    "allowed_values": [],
                }
            )
        elif set(bound) == {"allowed_values"}:
            allowed = bound["allowed_values"]
            if type(allowed) not in (list, tuple):
                raise TypeError("Hybrid replay allowed values must be an exact array")
            result.append(
                {
                    "field_ref": field_ref,
                    "bound_kind": "allowed_values",
                    "minimum": None,
                    "maximum": None,
                    "allowed_values": sorted(cast(Sequence[str], allowed)),
                }
            )
        else:
            raise ValueError("Hybrid replay adjustment bound has unknown fields")
    return result


def _candidate_projection(
    candidate_set: CandidateSet, target_ref: str, fallback_ref: str
) -> dict[str, object]:
    active = sorted(
        (
            candidate
            for candidate in candidate_set.candidates
            if candidate.target == target_ref
        ),
        key=lambda candidate: candidate.id,
    )
    candidate_set.require_declared_for_target(fallback_ref, target_ref)
    # ScopedProtocolManifestV2 construction already proves a non-empty target
    # set and a safe fallback for this exact quorum target.
    return {
        "candidates": [
            {
                "candidate_ref": candidate.id,
                "target_ref": candidate.target,
                "safe_fallback": candidate.safe_fallback,
            }
            for candidate in active
        ],
        "fallback_candidate_ref": fallback_ref,
    }


def _topology_projection(
    topology: PheromoneNeighborhood,
) -> dict[str, object]:
    if type(topology) is not PheromoneNeighborhood:
        raise TypeError("Hybrid replay topology must be exact PheromoneNeighborhood")
    return {
        "subjects": [
            {
                "subject_type": subject.subject_type,
                "subject_ref": subject.subject_id,
                "candidate_ref": subject.candidate_id,
                "target_ref": subject.target,
            }
            for subject in sorted(
                topology.subjects,
                key=lambda item: (item.subject_type, item.subject_id),
            )
        ],
        "edges": [
            {
                "source_subject_type": edge.source_subject_type,
                "source_subject_ref": edge.source_subject_id,
                "target_subject_type": edge.target_subject_type,
                "target_subject_ref": edge.target_subject_id,
                "attenuation": _encode_model_number(
                    edge.attenuation, "Hybrid replay topology attenuation"
                ),
            }
            for edge in sorted(
                topology.edges,
                key=lambda item: (
                    item.source_subject_type,
                    item.source_subject_id,
                    item.target_subject_type,
                    item.target_subject_id,
                ),
            )
        ],
    }


def project_topology_v2(topology: PheromoneNeighborhood) -> dict[str, object]:
    """Return the closed canonical projection of one declared topology."""

    return _topology_projection(topology)


def _trail_projection(trail: PheromoneTrail) -> dict[str, object]:
    if type(trail) is not PheromoneTrail:
        raise TypeError("Hybrid replay trail must be exact PheromoneTrail")
    return {
        "candidate_ref": trail.candidate_id,
        "strength": encode_binary64_v1(trail.strength, "Hybrid replay trail strength"),
        "subject_type": trail.subject_type,
        "subject_ref": trail.subject_id,
        "target_ref": trail.target,
        "route_ref": trail.route_id,
        "tool_ref": trail.tool_id,
        "kind": trail.kind,
        "source_ref": trail.source_id,
        "source_role": trail.source_role,
        "evidence_ref": trail.evidence_id,
        "provenance_ref": trail.provenance,
        "trace_event_ref": trail.trace_event_id,
        "deposited_at_step": trail.deposited_at_step,
        "updated_at_step": trail.updated_at_step,
        "ttl_steps": trail.ttl_steps,
        "lineage_event_refs": list(trail.lineage_event_ids),
        "diffusion_root_trace_event_ref": trail.diffusion_root_trace_event_id,
        "diffusion_parent_trace_event_ref": trail.diffusion_parent_trace_event_id,
        "diffusion_hop": trail.diffusion_hop,
    }


def _adjustment_values_projection(
    values: Mapping[str, object],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for field_ref, value in sorted(values.items()):
        if field_ref in _TEXT_ADJUSTMENT_FIELDS:
            if type(value) is not str:
                raise TypeError("Hybrid replay text adjustment must be exact text")
            result.append(
                {"field_ref": field_ref, "value_kind": "text", "value": value}
            )
        else:
            result.append(
                {
                    "field_ref": field_ref,
                    "value_kind": "binary64",
                    "value": _encode_model_number(
                        value, f"Hybrid replay adjustment {field_ref}"
                    ),
                }
            )
    return result


def _require_fingerprint(
    fingerprint: object, version: str, length: int, label: str
) -> tuple[object, ...]:
    if type(fingerprint) is not tuple:
        raise TypeError(f"Hybrid replay {label} fingerprint must be an exact tuple")
    value = cast(tuple[object, ...], fingerprint)
    if len(value) != length or value[0] != version:
        raise ValueError(
            f"Hybrid replay {label} fingerprint version or arity is invalid"
        )
    return value


def _deposit_receipt(event_id: str, fingerprint: object) -> dict[str, object]:
    value = _require_fingerprint(fingerprint, "deposit-v1", 21, "deposit")
    trail = PheromoneTrail(
        candidate_id=cast(str, value[1]),
        strength=_exact_float(value[2], "Hybrid replay deposit strength"),
        subject_type=cast(str, value[3]),
        subject_id=cast(str, value[4]),
        target=cast(str, value[5]),
        route_id=cast(str, value[6]),
        tool_id=cast(str, value[7]),
        kind=cast(str, value[8]),
        source_id=cast(str, value[9]),
        source_role=cast(str, value[10]),
        evidence_id=cast(str, value[11]),
        provenance=cast(str, value[12]),
        trace_event_id=cast(str, value[13]),
        deposited_at_step=cast(int, value[14]),
        updated_at_step=cast(int, value[15]),
        ttl_steps=cast(int | None, value[16]),
        lineage_event_ids=_exact_text_tuple(value[17], "deposit lineage"),
        diffusion_root_trace_event_id=cast(str, value[18]),
        diffusion_parent_trace_event_id=cast(str, value[19]),
        diffusion_hop=cast(int, value[20]),
    )
    payload = _trail_projection(trail)
    if payload["trace_event_ref"] != event_id:
        raise ValueError("Hybrid replay deposit event id is mismatched")
    if _restore_receipt_fingerprint("deposit", payload) != value:
        raise ValueError("Hybrid replay deposit fingerprint did not decode exactly")
    return {
        "kind": "deposit",
        "event_id": event_id,
        "payload": payload,
        "payload_root": "",
    }


def _exact_text_tuple(value: object, label: str) -> tuple[str, ...]:
    if type(value) is not tuple or any(type(item) is not str for item in value):
        raise TypeError(f"Hybrid replay {label} must be an exact text tuple")
    return cast(tuple[str, ...], value)


def _feedback_receipt(event_id: str, fingerprint: object) -> dict[str, object]:
    value = _require_fingerprint(fingerprint, "feedback-v1", 13, "feedback")
    for index in (1, 2, 3, 4, 5, 6, 9, 10, 11):
        if type(value[index]) is not str:
            raise TypeError("Hybrid replay feedback text field has invalid type")
    if type(value[12]) is not int or type(value[12]) is bool:
        raise TypeError("Hybrid replay feedback step must be an exact integer")
    payload = {
        "source_ref": value[1],
        "subject_type": value[2],
        "subject_ref": value[3],
        "candidate_ref": value[4],
        "target_ref": value[5],
        "outcome": value[6],
        "reward": encode_binary64_v1(value[7], "Hybrid replay feedback reward"),
        "strength_delta": encode_binary64_v1(
            value[8], "Hybrid replay feedback strength_delta"
        ),
        "evidence_ref": value[9],
        "provenance_ref": value[10],
        "trace_event_ref": value[11],
        "step": value[12],
    }
    if payload["trace_event_ref"] != event_id:
        raise ValueError("Hybrid replay feedback event id is mismatched")
    return {
        "kind": "feedback",
        "event_id": event_id,
        "payload": payload,
        "payload_root": "",
    }


def _adjustment_receipt(event_id: str, fingerprint: object) -> dict[str, object]:
    value = _require_fingerprint(fingerprint, "adjustment-v1", 6, "adjustment")
    for index in (1, 2, 4, 5):
        if type(value[index]) is not str:
            raise TypeError("Hybrid replay adjustment text field has invalid type")
    canonical_values = value[3]
    if type(canonical_values) is not tuple:
        raise TypeError("Hybrid replay adjustment values must be an exact tuple")
    restored: dict[str, object] = {}
    prior = ""
    for item in cast(tuple[object, ...], canonical_values):
        if (
            type(item) is not tuple
            or len(cast(tuple[object, ...], item)) != 2
            or type(cast(tuple[object, ...], item)[0]) is not str
        ):
            raise TypeError("Hybrid replay adjustment entry is malformed")
        field_ref, adjustment = cast(tuple[object, object], item)
        if cast(str, field_ref) <= prior:
            raise ValueError("Hybrid replay adjustment values are not canonical")
        prior = cast(str, field_ref)
        restored[cast(str, field_ref)] = adjustment
    payload = {
        "layer_ref": value[1],
        "source_ref": value[2],
        "adjustments": _adjustment_values_projection(restored),
        "provenance_ref": value[4],
        "trace_event_ref": value[5],
    }
    if payload["trace_event_ref"] != event_id:
        raise ValueError("Hybrid replay adjustment event id is mismatched")
    return {
        "kind": "adjustment",
        "event_id": event_id,
        "payload": payload,
        "payload_root": "",
    }


def _exact_object(
    value: object, fields: frozenset[str], label: str
) -> dict[str, object]:
    if type(value) is not dict:
        raise TypeError(f"Hybrid replay {label} must be an exact JSON object")
    result = cast(dict[str, object], value)
    if set(result) != fields or any(type(key) is not str for key in result):
        raise ValueError(f"Hybrid replay {label} fields are invalid")
    return result


def _strict_json_object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Hybrid replay diffusion JSON contains duplicate keys")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ValueError(
        f"Hybrid replay diffusion JSON contains non-finite constant: {value}"
    )


def _diffusion_receipt(event_id: str, fingerprint: object) -> dict[str, object]:
    value = _require_fingerprint(fingerprint, "diffusion-v1", 2, "diffusion")
    if type(value[1]) is not str:
        raise TypeError("Hybrid replay diffusion payload must be canonical JSON text")
    canonical = value[1]
    try:
        envelope_value = json.loads(
            canonical,
            object_pairs_hook=_strict_json_object_pairs,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Hybrid replay diffusion payload is not valid JSON") from exc
    envelope = _exact_object(
        envelope_value, frozenset({"payload", "version"}), "diffusion envelope"
    )
    if envelope["version"] != PHEROMONE_CLIP_PAYLOAD_VERSION:
        raise ValueError("Hybrid replay diffusion payload version is unsupported")
    payload = _exact_object(
        envelope["payload"],
        frozenset({"lifecycle", "input", "effective"}),
        "diffusion causal payload",
    )
    if payload["lifecycle"] != "diffusion":
        raise ValueError("Hybrid replay diffusion lifecycle is invalid")
    if canonical_pheromone_clip_payload(payload) != canonical:
        raise ValueError("Hybrid replay diffusion payload is not canonical")
    inputs = _exact_object(
        payload["input"],
        frozenset(
            {
                "source_trail",
                "target_subject",
                "edge",
                "policy_attenuation",
                "hop",
                "parent_trace_event_id",
                "derived_trace_event_id",
            }
        ),
        "diffusion input",
    )
    effective = _exact_object(
        payload["effective"],
        frozenset(
            {
                "target",
                "candidate_id",
                "subject_type",
                "subject_id",
                "source_id",
                "source_kind",
                "source_strength",
                "root_trace_event_id",
            }
        ),
        "diffusion effective output",
    )
    target_subject = _exact_object(
        inputs["target_subject"],
        frozenset({"subject_type", "subject_id", "candidate_id", "target"}),
        "diffusion target subject",
    )
    edge = _exact_object(
        inputs["edge"],
        frozenset(
            {
                "source_subject_type",
                "source_subject_id",
                "target_subject_type",
                "target_subject_id",
                "attenuation",
            }
        ),
        "diffusion edge",
    )
    source_trail_payload = _exact_object(
        inputs["source_trail"],
        frozenset(
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
        ),
        "diffusion source trail",
    )
    _source_trail_from_causal_payload(source_trail_payload)
    if inputs["derived_trace_event_id"] != event_id:
        raise ValueError("Hybrid replay diffusion event id is mismatched")
    receipt_payload = {
        "replay_version": HYBRID_REPLAY_DIFFUSION_REPLAY_VERSION_V2,
        "source_trail_root": hybrid_replay_diffusion_source_trail_root_v2(
            source_trail_payload
        ),
        "target_subject_type": target_subject["subject_type"],
        "target_subject_ref": target_subject["subject_id"],
        "candidate_ref": effective["candidate_id"],
        "target_ref": effective["target"],
        "edge_attenuation": encode_binary64_v1(
            edge["attenuation"], "Hybrid replay diffusion edge attenuation"
        ),
        "policy_attenuation": encode_binary64_v1(
            inputs["policy_attenuation"],
            "Hybrid replay diffusion policy attenuation",
        ),
        "hop": inputs["hop"],
        "parent_event_id": inputs["parent_trace_event_id"],
        "derived_event_id": inputs["derived_trace_event_id"],
        "source_ref": effective["source_id"],
        "source_kind": effective["source_kind"],
        "source_strength": encode_binary64_v1(
            effective["source_strength"], "Hybrid replay diffusion source strength"
        ),
        "root_event_id": effective["root_trace_event_id"],
        # The closed contract validates this versioned JSON string and keeps it
        # so the v1 fingerprint can be restored byte-for-byte after restart.
        "canonical_causal_payload": canonical,
    }
    return {
        "kind": "diffusion",
        "event_id": event_id,
        "payload": receipt_payload,
        "payload_root": "",
    }


def _source_trail_from_causal_payload(value: object) -> PheromoneTrail:
    fields = frozenset(
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
    trail = _exact_object(value, fields, "diffusion source trail")
    lineage = trail["lineage_event_ids"]
    if type(lineage) is not list or any(
        type(item) is not str for item in cast(list[object], lineage)
    ):
        raise TypeError("Hybrid replay diffusion source lineage is malformed")
    return PheromoneTrail(
        candidate_id=cast(str, trail["candidate_id"]),
        strength=_exact_float(
            trail["strength"], "Hybrid replay diffusion trail strength"
        ),
        subject_type=cast(str, trail["subject_type"]),
        subject_id=cast(str, trail["subject_id"]),
        target=cast(str, trail["target"]),
        route_id=cast(str, trail["route_id"]),
        tool_id=cast(str, trail["tool_id"]),
        kind=cast(str, trail["kind"]),
        source_id=cast(str, trail["source_id"]),
        source_role=cast(str, trail["source_role"]),
        evidence_id=cast(str, trail["evidence_id"]),
        provenance=cast(str, trail["provenance"]),
        trace_event_id=cast(str, trail["trace_event_id"]),
        deposited_at_step=cast(int, trail["deposited_at_step"]),
        updated_at_step=cast(int, trail["updated_at_step"]),
        ttl_steps=cast(int | None, trail["ttl_steps"]),
        lineage_event_ids=tuple(cast(list[str], lineage)),
        diffusion_root_trace_event_id=cast(str, trail["diffusion_root_trace_event_id"]),
        diffusion_parent_trace_event_id=cast(
            str, trail["diffusion_parent_trace_event_id"]
        ),
        diffusion_hop=cast(int, trail["diffusion_hop"]),
    )


def _project_receipts(step: HybridCollectiveStep) -> list[dict[str, object]]:
    projections: list[dict[str, object]] = []
    decoders = (
        (step.deposit_replay_receipts, _deposit_receipt),
        (step.diffusion_replay_receipts, _diffusion_receipt),
        (step.feedback_replay_receipts, _feedback_receipt),
        (step.adjustment_replay_receipts, _adjustment_receipt),
    )
    for receipts, decoder in decoders:
        for event_id, fingerprint in receipts.items():
            if type(event_id) is not str or not event_id:
                raise TypeError("Hybrid replay receipt event id must be non-empty text")
            projections.append(decoder(event_id, fingerprint))
    projections.sort(
        key=lambda item: (cast(str, item["kind"]), cast(str, item["event_id"]))
    )
    return projections


def _budget_projection(budget: PheromoneBudgetState | None) -> dict[str, object]:
    if type(budget) is not PheromoneBudgetState:
        raise GovernanceError(
            "Hybrid replay source step requires an exact budget state"
        )
    return {
        "round_cap": encode_binary64_v1(
            budget.round_cap, "Hybrid replay budget round cap"
        ),
        "per_source_cap": encode_binary64_v1(
            budget.per_source_cap, "Hybrid replay budget source cap"
        ),
        "round_used": encode_binary64_v1(
            budget.round_used, "Hybrid replay budget round used"
        ),
        "source_used": [
            {
                "source_ref": source_ref,
                "used": encode_binary64_v1(
                    used, f"Hybrid replay budget usage {source_ref}"
                ),
            }
            for source_ref, used in sorted(budget.source_used.items())
        ],
    }


def _trace_root(event: TraceEvent) -> str:
    if type(event) is not TraceEvent:
        raise TypeError("Hybrid replay source trace must be exact TraceEvent")
    event.validate()
    return _compute_root(
        "hybrid-replay-source-trace-event", _canonical_hybrid_value_v2(event)
    )


def _overlay_projection(
    step: HybridCollectiveStep,
    trace_roots_by_input_id: Mapping[str, str],
    parent: HybridReplaySnapshotV2 | None,
) -> dict[str, object]:
    values: dict[str, object] = {}
    sources: set[str] = set()
    traces: set[str] = set()
    if parent is not None:
        values.update(_restore_adjustment_values(parent.overlay["values"]))
        sources.update(cast(Sequence[str], parent.overlay["source_refs"]))
        traces.update(cast(Sequence[str], parent.overlay["trace_roots"]))
    adjustment_overlay = cast(Any, step.adjustment_overlay)
    values.update(dict(adjustment_overlay))
    sources.update(adjustment_overlay.source_ids)
    for trace_event_id in adjustment_overlay.trace_event_ids:
        trace_root = trace_roots_by_input_id.get(trace_event_id)
        if trace_root is None:
            raise GovernanceError(
                "Hybrid replay adjustment overlay has no exact source trace root"
            )
        traces.add(trace_root)
    return {
        "values": _adjustment_values_projection(values),
        "source_refs": sorted(sources),
        "trace_roots": sorted(traces),
    }


def _adjustment_trace_roots(step: HybridCollectiveStep) -> dict[str, str]:
    result: dict[str, str] = {}
    for event in step.trace_events:
        if event.event_type != "policy_adjustment":
            continue
        source_id = cast(str, event.lineage["source_trace_event_id"])
        # The verified source proof has already required this exact lineage id
        # to be a member of the non-empty adjustment receipt id set.
        root = _trace_root(event)
        if source_id in result:
            raise GovernanceError(
                "Hybrid replay policy adjustment trace id is ambiguous"
            )
        result[source_id] = root
    return result


def _require_parent_binding(
    parent: HybridReplaySnapshotV2,
    *,
    domain_root: str,
    scope_ref: str,
    manifest_root: str,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
    observed_epoch: int,
    current_step: int,
    candidate_projection: Mapping[str, object],
    policy_projection: Mapping[str, object],
    topology_projection: Mapping[str, object],
) -> None:
    for field, value in (
        ("domain_root", domain_root),
        ("scope_ref", scope_ref),
        ("manifest_root", manifest_root),
        ("protocol_ref", protocol_ref),
        ("run_ref", run_ref),
        ("target_ref", target_ref),
    ):
        if getattr(parent, field) != value:
            raise GovernanceError(f"Hybrid replay parent {field} is cross-bound")
    if observed_epoch < parent.observed_epoch:
        raise GovernanceError("Hybrid replay observed_epoch cannot roll back")
    if current_step <= parent.current_step:
        raise GovernanceError("Hybrid replay current_step must advance its parent")
    for actual, expected, label in (
        (parent.candidate_projection, candidate_projection, "candidate projection"),
        (parent.policy_projection, policy_projection, "base policy projection"),
        (parent.topology_projection, topology_projection, "topology projection"),
    ):
        if _plain(actual) != _plain(expected):
            raise GovernanceError(f"Hybrid replay parent {label} changed")


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if type(value) in (tuple, list):
        return [_plain(item) for item in cast(Sequence[object], value)]
    return value


def _require_receipt_extension(
    parent: HybridReplaySnapshotV2, receipts: Sequence[Mapping[str, object]]
) -> None:
    prior = {
        (cast(str, item["kind"]), cast(str, item["event_id"])): _plain(item["payload"])
        for item in parent.replay_receipts
    }
    current = {
        (cast(str, item["kind"]), cast(str, item["event_id"])): _plain(item["payload"])
        for item in receipts
    }
    for key, value in prior.items():
        if current.get(key) != value:
            raise GovernanceError(
                "Hybrid replay historical receipt was deleted or replaced"
            )


def _source_projection_context(
    material: _VerifiedHybridSourceMaterialV2,
) -> tuple[
    HybridCollectiveStep,
    str,
    str,
    str,
    int,
    CandidateSet,
    CollectiveDecisionPolicy,
    PheromoneNeighborhood,
    HybridReplaySnapshotV2 | None,
]:
    manifest = material.manifest
    policy = manifest.collective_decision_policy
    if type(policy) is not CollectiveDecisionPolicy or policy.mode != "hybrid":
        raise GovernanceError("Hybrid replay source manifest has no Hybrid policy")
    if policy.fallback_candidate != manifest.quorum_policy.fallback_candidate:
        raise GovernanceError("Hybrid replay source manifest fallbacks are mismatched")
    target_ref = manifest.quorum_policy.target
    candidate_set = CandidateSet(
        tuple(
            Candidate(item.id, item.target, item.safe_fallback)
            for item in manifest.candidates
        )
    )
    candidate = _candidate_projection(
        candidate_set,
        target_ref,
        manifest.quorum_policy.fallback_candidate,
    )
    base_policy = _policy_projection(policy)
    _topology_projection(material.topology)
    binding = material.binding
    expected_roots = (
        (
            binding.candidate_projection_root,
            _compute_root("hybrid-replay-candidate-projection", candidate),
            "candidate set",
        ),
        (
            binding.base_policy_projection_root,
            _compute_root("hybrid-replay-policy-projection", base_policy),
            "manifest base policy",
        ),
    )
    for actual, expected, label in expected_roots:
        if actual != expected:
            raise GovernanceError(f"Hybrid replay source proof {label} root changed")
    expected_input = (
        base_policy
        if material.parent_snapshot is None
        else _plain(material.parent_snapshot.effective_policy_projection)
    )
    if _plain(material.input_policy_projection) != _plain(expected_input):
        raise GovernanceError(
            "Hybrid replay source proof actual input policy is mismatched"
        )
    return (
        material.step,
        manifest.manifest_root,
        manifest.id,
        target_ref,
        binding.current_step,
        candidate_set,
        policy,
        material.topology,
        material.parent_snapshot,
    )


def _require_committed_source_parent(
    material: _VerifiedHybridSourceMaterialV2,
    committed: HybridReplaySnapshotV2 | None,
) -> None:
    declared = material.parent_snapshot
    if declared is None and committed is None:
        return
    if (
        type(declared) is not HybridReplaySnapshotV2
        or type(committed) is not HybridReplaySnapshotV2
        or declared.canonical_bytes() != committed.canonical_bytes()
    ):
        raise GovernanceError(
            "Hybrid replay source proof does not bind the committed parent"
        )


def build_hybrid_replay_advance_request_v2(
    *,
    domain_root: str,
    scope_ref: str,
    run_ref: str,
    observed_epoch: int,
    advance_ref: str,
    source: VerifiedHybridSourceStepV2,
) -> HybridReplayAdvanceRequestV2:
    """Build one exact next snapshot from a context-bound v2 source proof."""

    material = _verified_hybrid_source_material_v2(source)
    _require_hybrid_source_authority_context_v2(
        material,
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        observed_epoch=observed_epoch,
    )
    (
        source_step,
        manifest_root,
        protocol_ref,
        target_ref,
        current_step,
        candidate_set,
        base_policy,
        topology,
        parent_snapshot,
    ) = _source_projection_context(material)
    # Source-proof verification has already bound the exact step, protocol,
    # target, and current step before this projection is entered.
    candidate = _candidate_projection(
        candidate_set,
        target_ref,
        material.manifest.quorum_policy.fallback_candidate,
    )
    policy = _policy_projection(base_policy)
    topology_value = _topology_projection(topology)
    if parent_snapshot is not None:
        _require_parent_binding(
            parent_snapshot,
            domain_root=domain_root,
            scope_ref=scope_ref,
            manifest_root=manifest_root,
            protocol_ref=protocol_ref,
            run_ref=run_ref,
            target_ref=target_ref,
            observed_epoch=observed_epoch,
            current_step=current_step,
            candidate_projection=candidate,
            policy_projection=policy,
            topology_projection=topology_value,
        )
    receipts = _project_receipts(source_step)
    if parent_snapshot is not None:
        _require_receipt_extension(parent_snapshot, receipts)
    overlay = _overlay_projection(
        source_step, _adjustment_trace_roots(source_step), parent_snapshot
    )
    source_trace_roots = {_trace_root(event) for event in source_step.trace_events}
    # Earlier full trace history remains in the append-only Store.  Only roots
    # that still justify the cumulative policy overlay must cross snapshots;
    # carrying every observation here would make bounded replay memory grow
    # without limit.
    source_trace_roots.update(cast(Sequence[str], overlay["trace_roots"]))
    effective = _policy_projection(source_step.effective_policy)
    stream_ref = hybrid_replay_stream_ref_v2(
        scope_ref, protocol_ref, run_ref, target_ref
    )
    transition_id = hybrid_replay_transition_id_v2(stream_ref, advance_ref)
    parent_revision = parent_snapshot.revision if parent_snapshot is not None else 0
    snapshot = HybridReplaySnapshotV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        manifest_root=manifest_root,
        protocol_ref=protocol_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        observed_epoch=observed_epoch,
        stream_ref=stream_ref,
        advance_ref=advance_ref,
        transition_id=transition_id,
        revision=parent_revision + 1,
        current_step=current_step,
        parent_revision=parent_revision,
        parent_transition_id=(
            parent_snapshot.transition_id if parent_snapshot is not None else "genesis"
        ),
        parent_snapshot_root=(
            parent_snapshot.snapshot_root
            if parent_snapshot is not None
            else HYBRID_REPLAY_GENESIS_SNAPSHOT_ROOT_V2
        ),
        candidate_projection=candidate,
        policy_projection=policy,
        topology_projection=topology_value,
        active_trails=[_trail_projection(trail) for trail in source_step.active_trails],
        replay_receipts=receipts,
        last_budget=_budget_projection(source_step.budget_state),
        overlay=overlay,
        effective_policy_projection=effective,
        source_step_root=_compute_root(
            "hybrid-replay-source-step", _canonical_hybrid_value_v2(source_step)
        ),
        source_trace_roots=sorted(source_trace_roots),
    )
    return HybridReplayAdvanceRequestV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        observed_epoch=observed_epoch,
        advance_ref=advance_ref,
        transition_id=transition_id,
        stream_ref=stream_ref,
        snapshot=snapshot,
    )


def verify_hybrid_replay_request_source_v2(
    request: HybridReplayAdvanceRequestV2,
    *,
    source: VerifiedHybridSourceStepV2,
    committed_parent_snapshot: HybridReplaySnapshotV2 | None,
) -> None:
    """Rebuild and compare an advance request without granting authority."""

    if type(request) is not HybridReplayAdvanceRequestV2:
        raise TypeError("Hybrid replay verification requires exact advance request")
    material = _verified_hybrid_source_material_v2(source)
    _require_hybrid_source_authority_context_v2(
        material,
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        run_ref=request.run_ref,
        observed_epoch=request.observed_epoch,
    )
    _require_committed_source_parent(material, committed_parent_snapshot)
    rebuilt = build_hybrid_replay_advance_request_v2(
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        run_ref=request.run_ref,
        observed_epoch=request.observed_epoch,
        advance_ref=request.advance_ref,
        source=source,
    )
    if rebuilt.canonical_bytes() != request.canonical_bytes():
        raise GovernanceError("Hybrid replay request does not match its exact source")


def _restore_adjustment_values(value: object) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in cast(Sequence[Mapping[str, object]], value):
        field_ref = cast(str, item["field_ref"])
        if item["value_kind"] == "text":
            result[field_ref] = item["value"]
        else:
            result[field_ref] = decode_binary64_v1(
                item["value"], f"Hybrid replay adjustment {field_ref}"
            )
    return result


def restore_collective_policy_v2(
    projection: Mapping[str, object],
) -> CollectiveDecisionPolicy:
    """Restore the exact protocol model represented by a frozen projection."""

    values = dict(projection)
    for field in _BINARY64_POLICY_FIELDS:
        values[field] = decode_binary64_v1(
            values[field], f"Hybrid replay policy {field}"
        )
    values["pheromone_kind_profiles"] = {
        cast(str, item["kind"]): PheromoneKindProfile(
            weight=decode_binary64_v1(item["weight"], "Hybrid replay profile weight"),
            evaporation_rate=(
                None
                if item["evaporation_rate"] is None
                else decode_binary64_v1(
                    item["evaporation_rate"],
                    "Hybrid replay profile evaporation rate",
                )
            ),
            ttl_steps=cast(int | None, item["ttl_steps"]),
            response_model=cast(str, item["response_model"]),
            priority=cast(int, item["priority"]),
            can_suppress_positive=cast(bool, item["can_suppress_positive"]),
            scored_subject_types=list(
                cast(Sequence[str], item["scored_subject_types"])
            ),
        )
        for item in cast(
            Sequence[Mapping[str, object]], values["pheromone_kind_profiles"]
        )
    }
    values["layer_weight_bounds"] = {
        cast(str, item["layer_ref"]): (
            decode_binary64_v1(item["minimum"], "Hybrid replay layer minimum"),
            decode_binary64_v1(item["maximum"], "Hybrid replay layer maximum"),
        )
        for item in cast(Sequence[Mapping[str, object]], values["layer_weight_bounds"])
    }
    for field in ("layer_default_weights", "layer_confidence_thresholds"):
        values[field] = {
            cast(str, item["layer_ref"]): decode_binary64_v1(
                item["value"], f"Hybrid replay {field} value"
            )
            for item in cast(Sequence[Mapping[str, object]], values[field])
        }
    values["policy_adjustment_bounds"] = _restore_adjustment_bounds(
        cast(Sequence[Mapping[str, object]], values["policy_adjustment_bounds"])
    )
    values["fallback_candidate"] = values.pop("fallback_candidate_ref")
    return CollectiveDecisionPolicy(**values)  # type: ignore[arg-type]


def _restore_adjustment_bounds(
    values: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in values:
        field_ref = cast(str, item["field_ref"])
        if item["bound_kind"] == "binary64_range":
            result[field_ref] = [
                decode_binary64_v1(item["minimum"], "Hybrid replay bound minimum"),
                decode_binary64_v1(item["maximum"], "Hybrid replay bound maximum"),
            ]
        else:
            result[field_ref] = {
                "allowed_values": list(cast(Sequence[str], item["allowed_values"]))
            }
    return result


def restore_topology_v2(projection: Mapping[str, object]) -> PheromoneNeighborhood:
    return PheromoneNeighborhood(
        subjects=[
            PheromoneSubject(
                subject_type=cast(str, item["subject_type"]),
                subject_id=cast(str, item["subject_ref"]),
                candidate_id=cast(str, item["candidate_ref"]),
                target=cast(str, item["target_ref"]),
            )
            for item in cast(Sequence[Mapping[str, object]], projection["subjects"])
        ],
        edges=[
            PheromoneEdge(
                source_subject_type=cast(str, item["source_subject_type"]),
                source_subject_id=cast(str, item["source_subject_ref"]),
                target_subject_type=cast(str, item["target_subject_type"]),
                target_subject_id=cast(str, item["target_subject_ref"]),
                attenuation=decode_binary64_v1(
                    item["attenuation"], "Hybrid replay topology attenuation"
                ),
            )
            for item in cast(Sequence[Mapping[str, object]], projection["edges"])
        ],
    )


def _trail_from_projection(value: Mapping[str, object]) -> PheromoneTrail:
    return PheromoneTrail(
        candidate_id=cast(str, value["candidate_ref"]),
        strength=decode_binary64_v1(value["strength"], "Hybrid replay trail strength"),
        subject_type=cast(str, value["subject_type"]),
        subject_id=cast(str, value["subject_ref"]),
        target=cast(str, value["target_ref"]),
        route_id=cast(str, value["route_ref"]),
        tool_id=cast(str, value["tool_ref"]),
        kind=cast(str, value["kind"]),
        source_id=cast(str, value["source_ref"]),
        source_role=cast(str, value["source_role"]),
        evidence_id=cast(str, value["evidence_ref"]),
        provenance=cast(str, value["provenance_ref"]),
        trace_event_id=cast(str, value["trace_event_ref"]),
        deposited_at_step=cast(int, value["deposited_at_step"]),
        updated_at_step=cast(int, value["updated_at_step"]),
        ttl_steps=cast(int | None, value["ttl_steps"]),
        lineage_event_ids=tuple(cast(Sequence[str], value["lineage_event_refs"])),
        diffusion_root_trace_event_id=cast(
            str, value["diffusion_root_trace_event_ref"]
        ),
        diffusion_parent_trace_event_id=cast(
            str, value["diffusion_parent_trace_event_ref"]
        ),
        diffusion_hop=cast(int, value["diffusion_hop"]),
    )


def _restore_receipts(
    receipts: Sequence[Mapping[str, object]],
) -> tuple[
    dict[str, tuple[Any, ...]],
    dict[str, tuple[Any, ...]],
    dict[str, tuple[Any, ...]],
    dict[str, tuple[Any, ...]],
]:
    restored: dict[str, dict[str, tuple[Any, ...]]] = {
        "deposit": {},
        "diffusion": {},
        "feedback": {},
        "adjustment": {},
    }
    for receipt in receipts:
        kind = cast(str, receipt["kind"])
        event_id = cast(str, receipt["event_id"])
        payload = cast(Mapping[str, object], receipt["payload"])
        restored[kind][event_id] = _restore_receipt_fingerprint(kind, payload)
    return (
        restored["deposit"],
        restored["diffusion"],
        restored["feedback"],
        restored["adjustment"],
    )


def _restore_receipt_fingerprint(
    kind: str, payload: Mapping[str, object]
) -> tuple[Any, ...]:
    if kind == "deposit":
        trail = _trail_from_projection(payload)
        return (
            "deposit-v1",
            trail.candidate_id,
            trail.strength,
            trail.subject_type,
            trail.subject_id,
            trail.target,
            trail.route_id,
            trail.tool_id,
            trail.kind,
            trail.source_id,
            trail.source_role,
            trail.evidence_id,
            trail.provenance,
            trail.trace_event_id,
            trail.deposited_at_step,
            trail.updated_at_step,
            trail.ttl_steps,
            tuple(trail.lineage_event_ids),
            trail.diffusion_root_trace_event_id,
            trail.diffusion_parent_trace_event_id,
            trail.diffusion_hop,
        )
    if kind == "diffusion":
        canonical = payload["canonical_causal_payload"]
        return ("diffusion-v1", canonical)
    if kind == "feedback":
        return (
            "feedback-v1",
            payload["source_ref"],
            payload["subject_type"],
            payload["subject_ref"],
            payload["candidate_ref"],
            payload["target_ref"],
            payload["outcome"],
            decode_binary64_v1(payload["reward"], "Hybrid replay feedback reward"),
            decode_binary64_v1(
                payload["strength_delta"], "Hybrid replay feedback strength delta"
            ),
            payload["evidence_ref"],
            payload["provenance_ref"],
            payload["trace_event_ref"],
            payload["step"],
        )
    values = _restore_adjustment_values(payload["adjustments"])
    return (
        "adjustment-v1",
        payload["layer_ref"],
        payload["source_ref"],
        tuple(sorted(values.items())),
        payload["provenance_ref"],
        payload["trace_event_ref"],
    )


def restore_hybrid_replay_inputs_v2(
    snapshot: HybridReplaySnapshotV2,
) -> RestoredHybridReplayInputsV2:
    """Restore compatibility inputs; callers must separately prove authority."""

    if type(snapshot) is not HybridReplaySnapshotV2:
        raise TypeError("Hybrid replay restore requires exact snapshot")
    deposit, diffusion, feedback, adjustment = _restore_receipts(
        snapshot.replay_receipts
    )
    replay_state = HybridReplayState(
        protocol_id=snapshot.protocol_ref,
        target=snapshot.target_ref,
        active_trails=tuple(
            _trail_from_projection(item) for item in snapshot.active_trails
        ),
        processed_pheromone_event_ids=snapshot.processed_pheromone_event_ids,
        processed_feedback_ids=snapshot.processed_feedback_ids,
        processed_adjustment_ids=snapshot.processed_adjustment_ids,
        deposit_replay_receipts=deposit,
        diffusion_replay_receipts=diffusion,
        feedback_replay_receipts=feedback,
        adjustment_replay_receipts=adjustment,
    )
    budget = snapshot.last_budget
    return RestoredHybridReplayInputsV2(
        replay_state=replay_state,
        effective_policy=restore_collective_policy_v2(
            snapshot.effective_policy_projection
        ),
        topology=restore_topology_v2(snapshot.topology_projection),
        budget_state=PheromoneBudgetState(
            round_cap=decode_binary64_v1(
                budget["round_cap"], "Hybrid replay budget round cap"
            ),
            per_source_cap=decode_binary64_v1(
                budget["per_source_cap"], "Hybrid replay budget source cap"
            ),
            round_used=decode_binary64_v1(
                budget["round_used"], "Hybrid replay budget round used"
            ),
            source_used={
                cast(str, item["source_ref"]): decode_binary64_v1(
                    item["used"], "Hybrid replay budget source used"
                )
                for item in cast(Sequence[Mapping[str, object]], budget["source_used"])
            },
        ),
    )


__all__ = [
    "RestoredHybridReplayInputsV2",
    "build_hybrid_replay_advance_request_v2",
    "project_collective_policy_v2",
    "project_topology_v2",
    "restore_collective_policy_v2",
    "restore_hybrid_replay_inputs_v2",
    "restore_topology_v2",
    "verify_hybrid_replay_request_source_v2",
]
