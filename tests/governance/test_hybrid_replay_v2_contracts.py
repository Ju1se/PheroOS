from __future__ import annotations

from copy import deepcopy
import json
import pickle
from typing import Any, cast

import pytest

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2

import pheroos.governance._hybrid_replay_v2.contracts as contracts
from pheroos.governance._hybrid_replay_v2.contracts import (
    HYBRID_REPLAY_ADVANCE_REQUEST_SCHEMA_V2,
    HYBRID_REPLAY_DIFFUSION_REPLAY_VERSION_V2,
    HYBRID_REPLAY_GENESIS_SNAPSHOT_ROOT_V2,
    HYBRID_REPLAY_SNAPSHOT_SCHEMA_V2,
    HYBRID_REPLAY_STATE_SCHEMA_V2,
    HybridReplayAdvanceRequestV2,
    HybridReplaySnapshotV2,
    hybrid_replay_diffusion_source_trail_root_v2,
    hybrid_replay_stream_ref_v2,
    hybrid_replay_transition_id_v2,
)
from pheroos.governance._hybrid_replay_v2.numeric import (
    HYBRID_REPLAY_NUMERIC_WIRE_VERSION_V2,
)
from pheroos.trace import canonical_pheromone_clip_payload


def _root(index: int) -> str:
    return f"sha256:{index:064x}"


def _binary64(value: float) -> str:
    return value.hex()


def _candidate_projection() -> dict[str, Any]:
    return {
        "candidates": [
            {
                "candidate_ref": "candidate-a",
                "target_ref": "target-a",
                "safe_fallback": False,
            },
            {
                "candidate_ref": "fallback",
                "target_ref": "target-a",
                "safe_fallback": True,
            },
        ],
        "fallback_candidate_ref": "fallback",
    }


def _layer_values(field: str, value: float) -> list[dict[str, Any]]:
    return [
        {"layer_ref": layer, field: _binary64(value)}
        for layer in ("evolutionary", "learned", "metacognitive", "reactive")
    ]


def _policy_projection() -> dict[str, Any]:
    return {
        "mode": "hybrid",
        "min_independent_scouts": 1,
        "quorum_threshold": 1,
        "recruitment_enabled": True,
        "inhibition_enabled": True,
        "pheromone_enabled": True,
        "pheromone_evaporation_rate": _binary64(0.1),
        "pheromone_decay_model": "exponential",
        "pheromone_min_strength": _binary64(0.0),
        "pheromone_max_strength": _binary64(10.0),
        "pheromone_positive_weight": _binary64(1.0),
        "pheromone_negative_weight": _binary64(1.0),
        "pheromone_cautionary_weight": _binary64(1.0),
        "pheromone_cautionary_override_threshold": _binary64(1.0),
        "pheromone_novelty_weight": _binary64(0.5),
        "pheromone_per_source_cap": _binary64(3.0),
        "pheromone_per_round_deposit_cap": _binary64(5.0),
        "pheromone_min_source_diversity": 1,
        "pheromone_require_provenance": True,
        "pheromone_require_trace": True,
        "pheromone_scored_subject_types": ["candidate"],
        "pheromone_kind_profiles": [
            {
                "kind": "positive",
                "weight": _binary64(1.0),
                "evaporation_rate": None,
                "ttl_steps": None,
                "response_model": "linear",
                "priority": 0,
                "can_suppress_positive": False,
                "scored_subject_types": ["candidate"],
            }
        ],
        "pheromone_response_model": "linear",
        "pheromone_activation_threshold": _binary64(0.0),
        "pheromone_saturation_threshold": _binary64(10.0),
        "pheromone_competition_mode": "none",
        "pheromone_exploration_floor": _binary64(0.0),
        "pheromone_diffusion_enabled": True,
        "pheromone_diffusion_max_hops": 1,
        "pheromone_diffusion_attenuation": _binary64(0.5),
        "pheromone_feedback_enabled": True,
        "exploration_enabled": True,
        "exploration_floor": _binary64(0.0),
        "novelty_decay_rate": _binary64(0.0),
        "stale_route_reopen_threshold": _binary64(0.0),
        "layer_coordination_enabled": True,
        "layer_weight_bounds": [
            {
                "layer_ref": layer,
                "minimum": _binary64(0.0),
                "maximum": _binary64(1.0),
            }
            for layer in ("evolutionary", "learned", "metacognitive", "reactive")
        ],
        "layer_default_weights": _layer_values("value", 0.5),
        "layer_confidence_thresholds": _layer_values("value", 0.5),
        "layer_conflict_threshold": _binary64(0.5),
        "layer_emergency_override_threshold": _binary64(0.9),
        "layer_min_provenance": 1,
        "layer_fallback_on_unresolved_conflict": True,
        "policy_adjustment_bounds": [
            {
                "field_ref": "pheromone_response_model",
                "bound_kind": "allowed_values",
                "minimum": None,
                "maximum": None,
                "allowed_values": ["linear", "saturating"],
            }
        ],
        "fallback_candidate_ref": "fallback",
    }


def _topology_projection() -> dict[str, Any]:
    return {
        "subjects": [
            {
                "subject_type": "candidate",
                "subject_ref": "candidate-a",
                "candidate_ref": "candidate-a",
                "target_ref": "target-a",
            },
            {
                "subject_type": "candidate",
                "subject_ref": "fallback",
                "candidate_ref": "fallback",
                "target_ref": "target-a",
            },
        ],
        "edges": [
            {
                "source_subject_type": "candidate",
                "source_subject_ref": "candidate-a",
                "target_subject_type": "candidate",
                "target_subject_ref": "fallback",
                "attenuation": _binary64(0.5),
            }
        ],
    }


def _trail(*, event_id: str = "event-deposit") -> dict[str, Any]:
    return {
        "candidate_ref": "candidate-a",
        "strength": _binary64(1.0),
        "subject_type": "candidate",
        "subject_ref": "candidate-a",
        "target_ref": "target-a",
        "route_ref": "",
        "tool_ref": "",
        "kind": "positive",
        "source_ref": "scout-a",
        "source_role": "scout",
        "evidence_ref": "evidence-a",
        "provenance_ref": "provenance-a",
        "trace_event_ref": event_id,
        "deposited_at_step": 1,
        "updated_at_step": 1,
        "ttl_steps": None,
        "lineage_event_refs": [event_id],
        "diffusion_root_trace_event_ref": "",
        "diffusion_parent_trace_event_ref": "",
        "diffusion_hop": 0,
    }


def _feedback_payload(*, event_id: str = "event-feedback") -> dict[str, Any]:
    return {
        "source_ref": "scout-a",
        "subject_type": "candidate",
        "subject_ref": "candidate-a",
        "candidate_ref": "candidate-a",
        "target_ref": "target-a",
        "outcome": "success",
        "reward": _binary64(1.0),
        "strength_delta": _binary64(1.0),
        "evidence_ref": "evidence-a",
        "provenance_ref": "provenance-a",
        "trace_event_ref": event_id,
        "step": 1,
    }


def _adjustment_payload(*, event_id: str = "event-adjustment") -> dict[str, Any]:
    return {
        "layer_ref": "learned",
        "source_ref": "learner-a",
        "adjustments": [
            {
                "field_ref": "pheromone_response_model",
                "value_kind": "text",
                "value": "saturating",
            }
        ],
        "provenance_ref": "provenance-adjustment",
        "trace_event_ref": event_id,
    }


def _diffusion_source_trail() -> dict[str, Any]:
    return {
        "candidate_id": "candidate-a",
        "strength": 1.0,
        "subject_type": "candidate",
        "subject_id": "candidate-a",
        "target": "target-a",
        "route_id": "",
        "tool_id": "",
        "kind": "positive",
        "source_id": "scout-a",
        "source_role": "scout",
        "evidence_id": "evidence-a",
        "provenance": "provenance-a",
        "trace_event_id": "event-deposit",
        "deposited_at_step": 1,
        "updated_at_step": 1,
        "ttl_steps": None,
        "lineage_event_ids": ["event-deposit"],
        "diffusion_root_trace_event_id": "",
        "diffusion_parent_trace_event_id": "",
        "diffusion_hop": 0,
    }


def _diffusion_receipt_payload() -> dict[str, Any]:
    source_trail = _diffusion_source_trail()
    causal_payload = {
        "lifecycle": "diffusion",
        "input": {
            "source_trail": source_trail,
            "target_subject": {
                "subject_type": "candidate",
                "subject_id": "fallback",
                "candidate_id": "fallback",
                "target": "target-a",
            },
            "edge": {
                "source_subject_type": "candidate",
                "source_subject_id": "candidate-a",
                "target_subject_type": "candidate",
                "target_subject_id": "fallback",
                "attenuation": 0.5,
            },
            "policy_attenuation": 0.5,
            "hop": 1,
            "parent_trace_event_id": "event-deposit",
            "derived_trace_event_id": "event-diffusion",
        },
        "effective": {
            "target": "target-a",
            "candidate_id": "fallback",
            "subject_type": "candidate",
            "subject_id": "fallback",
            "source_id": "scout-a",
            "source_kind": "positive",
            "source_strength": 1.0,
            "root_trace_event_id": "event-deposit",
        },
    }
    return {
        "replay_version": HYBRID_REPLAY_DIFFUSION_REPLAY_VERSION_V2,
        "canonical_causal_payload": canonical_pheromone_clip_payload(causal_payload),
        "source_trail_root": hybrid_replay_diffusion_source_trail_root_v2(source_trail),
        "target_subject_type": "candidate",
        "target_subject_ref": "fallback",
        "candidate_ref": "fallback",
        "target_ref": "target-a",
        "edge_attenuation": _binary64(0.5),
        "policy_attenuation": _binary64(0.5),
        "hop": 1,
        "parent_event_id": "event-deposit",
        "derived_event_id": "event-diffusion",
        "source_ref": "scout-a",
        "source_kind": "positive",
        "source_strength": _binary64(1.0),
        "root_event_id": "event-deposit",
    }


def _snapshot_kwargs() -> dict[str, Any]:
    policy = _policy_projection()
    trail = _trail()
    stream_ref = hybrid_replay_stream_ref_v2(
        "scope-a", "protocol-a", "run-a", "target-a"
    )
    return {
        "domain_root": _root(1),
        "scope_ref": "scope-a",
        "manifest_root": _root(2),
        "protocol_ref": "protocol-a",
        "run_ref": "run-a",
        "target_ref": "target-a",
        "observed_epoch": 7,
        "stream_ref": stream_ref,
        "advance_ref": "advance-1",
        "transition_id": hybrid_replay_transition_id_v2(stream_ref, "advance-1"),
        "revision": 1,
        "current_step": 1,
        "parent_revision": 0,
        "parent_transition_id": "genesis",
        "parent_snapshot_root": HYBRID_REPLAY_GENESIS_SNAPSHOT_ROOT_V2,
        "candidate_projection": _candidate_projection(),
        "policy_projection": policy,
        "topology_projection": _topology_projection(),
        "active_trails": [trail],
        "replay_receipts": [
            {
                "kind": "deposit",
                "event_id": "event-deposit",
                "payload": trail,
                "payload_root": "",
            }
        ],
        "last_budget": {
            "round_cap": _binary64(5.0),
            "per_source_cap": _binary64(3.0),
            "round_used": _binary64(1.0),
            "source_used": [{"source_ref": "scout-a", "used": _binary64(1.0)}],
        },
        "overlay": {"values": [], "source_refs": [], "trace_roots": []},
        "effective_policy_projection": deepcopy(policy),
        "source_step_root": _root(3),
        "source_trace_roots": [_root(4), _root(5)],
    }


def _snapshot() -> HybridReplaySnapshotV2:
    return HybridReplaySnapshotV2(**_snapshot_kwargs())


def _snapshot_kwargs_with_diffusion() -> dict[str, Any]:
    kwargs = _snapshot_kwargs()
    kwargs["replay_receipts"] = [
        kwargs["replay_receipts"][0],
        {
            "kind": "diffusion",
            "event_id": "event-diffusion",
            "payload": _diffusion_receipt_payload(),
            "payload_root": "",
        },
    ]
    return kwargs


def _snapshot_kwargs_with_mutated_diffusion_causal_payload(
    path: tuple[object, ...], replacement: object
) -> dict[str, Any]:
    kwargs = _snapshot_kwargs_with_diffusion()
    receipt = kwargs["replay_receipts"][1]["payload"]
    envelope = json.loads(receipt["canonical_causal_payload"])
    _replace_nested(envelope["payload"], path, replacement)
    receipt["canonical_causal_payload"] = canonical_pheromone_clip_payload(
        envelope["payload"]
    )
    source_trail = envelope["payload"]["input"]["source_trail"]
    receipt["source_trail_root"] = hybrid_replay_diffusion_source_trail_root_v2(
        source_trail
    )
    return kwargs


def _request(
    snapshot: HybridReplaySnapshotV2 | None = None,
) -> HybridReplayAdvanceRequestV2:
    item = snapshot or _snapshot()
    return HybridReplayAdvanceRequestV2(
        domain_root=item.domain_root,
        scope_ref=item.scope_ref,
        run_ref=item.run_ref,
        target_ref=item.target_ref,
        observed_epoch=item.observed_epoch,
        advance_ref=item.advance_ref,
        transition_id=item.transition_id,
        stream_ref=item.stream_ref,
        snapshot=item,
    )


def _assert_no_float(value: object) -> None:
    assert type(value) is not float
    if isinstance(value, dict):
        for item in value.values():
            _assert_no_float(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_float(item)


def _replace_nested(
    document: dict[str, Any], path: tuple[object, ...], value: object
) -> None:
    target: Any = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def test_versions_and_exact_binary64_wire_are_frozen() -> None:
    assert HYBRID_REPLAY_SNAPSHOT_SCHEMA_V2 == (
        "pheroos-governance-hybrid-replay-snapshot-v2"
    )
    assert HYBRID_REPLAY_ADVANCE_REQUEST_SCHEMA_V2 == (
        "pheroos-governance-hybrid-replay-advance-request-v2"
    )
    assert HYBRID_REPLAY_STATE_SCHEMA_V2 == (
        "pheroos-governance-hybrid-replay-state-v2"
    )
    assert HYBRID_REPLAY_NUMERIC_WIRE_VERSION_V2 == "pheroos-binary64-hex-v1"
    assert _snapshot().canonical_version == AUTHORITY_CANONICAL_VERSION_V2


def test_stream_and_transition_derivation_have_independent_exact_vectors() -> None:
    stream_ref = hybrid_replay_stream_ref_v2(
        "scope-a", "protocol-a", "run-a", "target-a"
    )
    assert stream_ref == (
        "authority:hybrid-replay-v2:"
        "5192bb9bd56fe0db531a21ecb25b317670744981e2a601a56f79fa66da15d56d"
    )
    assert hybrid_replay_transition_id_v2(stream_ref, "advance-1") == (
        "transition:hybrid-replay-v2:"
        "bbda5cd65cfcc7647cf19166cc925ff1c5eecf93ab9a47680581d80979037621"
    )


def test_stream_and_transition_bindings_reject_nul_delimiter_aliases() -> None:
    left = ("scope-a", "protocol-a\x00run-a", "x", "target-a")
    right = ("scope-a", "protocol-a", "run-a\x00x", "target-a")
    assert b"\x00".join(item.encode("utf-8") for item in left) == b"\x00".join(
        item.encode("utf-8") for item in right
    )
    for bindings in (left, right):
        with pytest.raises(ValueError, match=r"U\+0000"):
            hybrid_replay_stream_ref_v2(*bindings)

    stream_ref = hybrid_replay_stream_ref_v2(
        "scope-a", "protocol-a", "run-a", "target-a"
    )
    with pytest.raises(ValueError, match=r"U\+0000"):
        hybrid_replay_transition_id_v2(stream_ref, "advance\x00substitute")


def test_snapshot_and_request_round_trip_exact_bytes_and_derived_ids() -> None:
    snapshot = _snapshot()
    request = _request(snapshot)

    restored_snapshot = HybridReplaySnapshotV2.from_dict(
        json.loads(snapshot.canonical_bytes())
    )
    restored_request = HybridReplayAdvanceRequestV2.from_dict(
        json.loads(request.canonical_bytes())
    )

    assert restored_snapshot == snapshot
    assert restored_snapshot.canonical_bytes() == snapshot.canonical_bytes()
    assert restored_snapshot.root() == snapshot.snapshot_root
    assert restored_request == request
    assert restored_request.canonical_bytes() == request.canonical_bytes()
    assert restored_request.root() == request.request_root
    assert restored_snapshot.processed_pheromone_event_ids == {"event-deposit"}
    assert restored_snapshot.processed_feedback_ids == frozenset()
    assert restored_snapshot.processed_adjustment_ids == frozenset()
    assert "processed_pheromone_event_ids" not in restored_snapshot.to_dict()
    _assert_no_float(restored_request.to_dict())


def test_snapshot_is_defensive_immutable_and_pickle_portable() -> None:
    kwargs = _snapshot_kwargs()
    snapshot = HybridReplaySnapshotV2(**kwargs)
    before = snapshot.canonical_bytes()

    kwargs["candidate_projection"]["candidates"][0]["candidate_ref"] = "mutated"
    kwargs["active_trails"][0]["strength"] = _binary64(9.0)
    kwargs["last_budget"]["source_used"][0]["used"] = _binary64(2.0)

    assert snapshot.canonical_bytes() == before
    with pytest.raises(TypeError):
        snapshot.candidate_projection["fallback_candidate_ref"] = "mutated"  # type: ignore[index]
    with pytest.raises(AttributeError):
        snapshot.candidate_projection._items = ()  # type: ignore[attr-defined]
    restored = pickle.loads(pickle.dumps(snapshot))
    assert type(restored) is HybridReplaySnapshotV2
    assert restored == snapshot
    assert restored.canonical_bytes() == before
    assert not hasattr(restored, "_issuance")


@pytest.mark.parametrize(
    "field", ["schema", "state_root", "snapshot_root", "active_trails"]
)
def test_snapshot_reader_rejects_missing_and_unknown_fields(field: str) -> None:
    payload = _snapshot().to_dict()
    del payload[field]
    with pytest.raises(ValueError, match="missing"):
        HybridReplaySnapshotV2.from_dict(payload)

    payload = _snapshot().to_dict()
    payload["unknown"] = True
    with pytest.raises(ValueError, match="unknown"):
        HybridReplaySnapshotV2.from_dict(payload)


def test_request_reader_rejects_missing_unknown_and_wrong_snapshot_type() -> None:
    payload = _request().to_dict()
    del payload["snapshot"]
    with pytest.raises(ValueError, match="missing"):
        HybridReplayAdvanceRequestV2.from_dict(payload)

    payload = _request().to_dict()
    payload["unknown"] = None
    with pytest.raises(ValueError, match="unknown"):
        HybridReplayAdvanceRequestV2.from_dict(payload)

    with pytest.raises(TypeError, match="HybridReplaySnapshotV2"):
        HybridReplayAdvanceRequestV2(
            domain_root=_root(1),
            scope_ref="scope-a",
            run_ref="run-a",
            target_ref="target-a",
            observed_epoch=7,
            advance_ref="advance-1",
            transition_id=hybrid_replay_transition_id_v2(
                hybrid_replay_stream_ref_v2(
                    "scope-a", "protocol-a", "run-a", "target-a"
                ),
                "advance-1",
            ),
            stream_ref=hybrid_replay_stream_ref_v2(
                "scope-a", "protocol-a", "run-a", "target-a"
            ),
            snapshot={},  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("path", "bad"),
    [
        (("policy_projection", "pheromone_evaporation_rate"), 0.1),
        (("active_trails", 0, "strength"), 1.0),
        (("last_budget", "round_used"), 1.0),
        (("observed_epoch",), True),
    ],
)
def test_snapshot_rejects_raw_float_and_primitive_type_confusion(
    path: tuple[object, ...], bad: object
) -> None:
    kwargs = _snapshot_kwargs()
    target: Any = kwargs
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = bad
    with pytest.raises((TypeError, ValueError)):
        HybridReplaySnapshotV2(**kwargs)


@pytest.mark.parametrize(
    "root_field",
    [
        "candidate_projection_root",
        "policy_projection_root",
        "topology_projection_root",
        "active_trails_root",
        "replay_receipts_root",
        "last_budget_root",
        "overlay_root",
        "effective_policy_root",
        "source_trace_set_root",
        "source_lineage_root",
        "state_root",
        "snapshot_root",
    ],
)
def test_every_snapshot_derived_root_is_recomputed(root_field: str) -> None:
    payload = _snapshot().to_dict()
    payload[root_field] = _root(999)
    with pytest.raises(ValueError, match=f"{root_field} is mismatched"):
        HybridReplaySnapshotV2.from_dict(payload)


def test_delete_and_substitute_attacks_fail_against_original_roots() -> None:
    deleted = _snapshot().to_dict()
    deleted["replay_receipts"] = []
    with pytest.raises(ValueError, match="replay_receipts_root is mismatched"):
        HybridReplaySnapshotV2.from_dict(deleted)

    substituted = _snapshot().to_dict()
    substituted["replay_receipts"][0]["payload"]["strength"] = _binary64(2.0)
    with pytest.raises(ValueError, match="payload_root is mismatched"):
        HybridReplaySnapshotV2.from_dict(substituted)


@pytest.mark.parametrize(
    "collection_path",
    [
        ("candidate_projection", "candidates"),
        ("topology_projection", "subjects"),
        ("source_trace_roots",),
    ],
)
def test_canonical_collections_reject_reordering(
    collection_path: tuple[str, ...],
) -> None:
    payload = _snapshot().to_dict()
    target: Any = payload
    for key in collection_path[:-1]:
        target = target[key]
    target[collection_path[-1]] = list(reversed(target[collection_path[-1]]))
    with pytest.raises(ValueError, match="canonical order"):
        HybridReplaySnapshotV2.from_dict(payload)


def test_receipt_ids_are_mutually_exclusive_across_closed_kinds() -> None:
    kwargs = _snapshot_kwargs()
    kwargs["replay_receipts"] = [
        kwargs["replay_receipts"][0],
        {
            "kind": "feedback",
            "event_id": "event-deposit",
            "payload": {
                "source_ref": "scout-a",
                "subject_type": "candidate",
                "subject_ref": "candidate-a",
                "candidate_ref": "candidate-a",
                "target_ref": "target-a",
                "outcome": "success",
                "reward": _binary64(1.0),
                "strength_delta": _binary64(1.0),
                "evidence_ref": "evidence-a",
                "provenance_ref": "provenance-a",
                "trace_event_ref": "event-deposit",
                "step": 1,
            },
            "payload_root": "",
        },
    ]
    with pytest.raises(ValueError, match="mutually exclusive"):
        HybridReplaySnapshotV2(**kwargs)


def test_all_closed_receipt_kinds_and_overlay_reconstruct_without_duplicate_truth() -> (
    None
):
    kwargs = _snapshot_kwargs()
    effective = deepcopy(kwargs["policy_projection"])
    effective["pheromone_response_model"] = "saturating"
    effective["pheromone_kind_profiles"][0]["response_model"] = "saturating"
    kwargs["effective_policy_projection"] = effective
    kwargs["overlay"] = {
        "values": [
            {
                "field_ref": "pheromone_response_model",
                "value_kind": "text",
                "value": "saturating",
            }
        ],
        "source_refs": ["learner-a"],
        "trace_roots": [_root(4)],
    }
    kwargs["replay_receipts"] = [
        {
            "kind": "adjustment",
            "event_id": "event-adjustment",
            "payload": {
                "layer_ref": "learned",
                "source_ref": "learner-a",
                "adjustments": [
                    {
                        "field_ref": "pheromone_response_model",
                        "value_kind": "text",
                        "value": "saturating",
                    }
                ],
                "provenance_ref": "provenance-adjustment",
                "trace_event_ref": "event-adjustment",
            },
            "payload_root": "",
        },
        kwargs["replay_receipts"][0],
        {
            "kind": "diffusion",
            "event_id": "event-diffusion",
            "payload": _diffusion_receipt_payload(),
            "payload_root": "",
        },
        {
            "kind": "feedback",
            "event_id": "event-feedback",
            "payload": {
                "source_ref": "scout-a",
                "subject_type": "candidate",
                "subject_ref": "candidate-a",
                "candidate_ref": "candidate-a",
                "target_ref": "target-a",
                "outcome": "success",
                "reward": _binary64(1.0),
                "strength_delta": _binary64(1.0),
                "evidence_ref": "evidence-a",
                "provenance_ref": "provenance-a",
                "trace_event_ref": "event-feedback",
                "step": 1,
            },
            "payload_root": "",
        },
    ]

    snapshot = HybridReplaySnapshotV2(**kwargs)
    restored = HybridReplaySnapshotV2.from_dict(snapshot.to_dict())

    assert restored.processed_pheromone_event_ids == {
        "event-deposit",
        "event-diffusion",
    }
    assert restored.processed_feedback_ids == {"event-feedback"}
    assert restored.processed_adjustment_ids == {"event-adjustment"}
    assert restored == snapshot


def test_diffusion_receipt_preserves_exact_v1_replay_fingerprint_across_roundtrip() -> (
    None
):
    expected = _diffusion_receipt_payload()["canonical_causal_payload"]
    snapshot = HybridReplaySnapshotV2(**_snapshot_kwargs_with_diffusion())
    restored = HybridReplaySnapshotV2.from_dict(snapshot.to_dict())
    receipt = restored.to_dict()["replay_receipts"][1]

    assert receipt["payload"]["replay_version"] == "diffusion-v1"
    assert receipt["payload"]["canonical_causal_payload"] == expected
    assert restored.processed_pheromone_event_ids == {
        "event-deposit",
        "event-diffusion",
    }


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("source_ref", "scout-substitute"),
        ("source_strength", _binary64(2.0)),
        ("root_event_id", "event-substitute"),
        ("edge_attenuation", _binary64(0.25)),
        ("policy_attenuation", _binary64(0.25)),
    ],
)
def test_diffusion_receipt_rejects_summary_substitution(
    field: str, replacement: object
) -> None:
    kwargs = _snapshot_kwargs_with_diffusion()
    kwargs["replay_receipts"][1]["payload"][field] = replacement
    with pytest.raises(ValueError, match="summary and canonical payload"):
        HybridReplaySnapshotV2(**kwargs)


def test_diffusion_receipt_rejects_canonical_payload_or_source_root_substitution() -> (
    None
):
    kwargs = _snapshot_kwargs_with_diffusion()
    receipt = kwargs["replay_receipts"][1]["payload"]
    envelope = json.loads(receipt["canonical_causal_payload"])
    envelope["payload"]["input"]["source_trail"]["strength"] = 2.0
    receipt["canonical_causal_payload"] = canonical_pheromone_clip_payload(
        envelope["payload"]
    )
    with pytest.raises(ValueError, match="canonical source strength is mismatched"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs_with_diffusion()
    kwargs["replay_receipts"][1]["payload"]["source_trail_root"] = _root(20)
    with pytest.raises(ValueError, match="source_trail_root is mismatched"):
        HybridReplaySnapshotV2(**kwargs)


def test_diffusion_receipt_rejects_noncanonical_duplicate_and_nonfinite_json() -> None:
    kwargs = _snapshot_kwargs_with_diffusion()
    receipt = kwargs["replay_receipts"][1]["payload"]
    receipt["canonical_causal_payload"] = (
        cast(str, receipt["canonical_causal_payload"]) + " "
    )
    with pytest.raises(ValueError, match="not canonical"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs_with_diffusion()
    kwargs["replay_receipts"][1]["payload"]["canonical_causal_payload"] = (
        '{"payload":{},"payload":{},"version":"pheroos-pheromone-clip-payload-v1"}'
    )
    with pytest.raises(ValueError, match="duplicate keys"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs_with_diffusion()
    receipt = kwargs["replay_receipts"][1]["payload"]
    envelope = json.loads(receipt["canonical_causal_payload"])
    envelope["payload"]["effective"]["source_strength"] = float("nan")
    receipt["canonical_causal_payload"] = json.dumps(
        envelope, separators=(",", ":"), sort_keys=True
    )
    with pytest.raises(ValueError, match="non-finite"):
        HybridReplaySnapshotV2(**kwargs)


def test_diffusion_receipt_rejects_missing_exact_replay_material() -> None:
    kwargs = _snapshot_kwargs_with_diffusion()
    del kwargs["replay_receipts"][1]["payload"]["canonical_causal_payload"]
    with pytest.raises(ValueError, match="missing=.*canonical_causal_payload"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs_with_diffusion()
    kwargs["replay_receipts"][1]["payload"]["replay_version"] = "diffusion-v0"
    with pytest.raises(ValueError, match="replay_version is unsupported"):
        HybridReplaySnapshotV2(**kwargs)


def test_same_advance_with_different_snapshot_body_has_different_request_root() -> None:
    first = _request()
    kwargs = _snapshot_kwargs()
    kwargs["source_step_root"] = _root(99)
    second = _request(HybridReplaySnapshotV2(**kwargs))

    assert first.transition_id == second.transition_id
    assert first.snapshot.snapshot_root != second.snapshot.snapshot_root
    assert first.request_root != second.request_root


def test_policy_topology_budget_and_effective_policy_are_cross_bound() -> None:
    kwargs = _snapshot_kwargs()
    kwargs["policy_projection"]["fallback_candidate_ref"] = "candidate-a"
    with pytest.raises(ValueError, match="fallback candidate"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["topology_projection"]["subjects"][0]["candidate_ref"] = "fallback"
    with pytest.raises(ValueError, match="candidate subject"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["last_budget"]["round_cap"] = _binary64(6.0)
    with pytest.raises(ValueError, match="budget caps"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["effective_policy_projection"]["pheromone_response_model"] = "saturating"
    with pytest.raises(ValueError, match="does not reconstruct"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["overlay"] = {
        "values": [
            {
                "field_ref": "pheromone_response_model",
                "value_kind": "text",
                "value": "competitive",
            }
        ],
        "source_refs": ["learner-a"],
        "trace_roots": [_root(4)],
    }
    with pytest.raises(ValueError, match="outside declared bounds"):
        HybridReplaySnapshotV2(**kwargs)


def test_parent_lineage_and_request_identity_are_cross_bound() -> None:
    kwargs = _snapshot_kwargs()
    kwargs["parent_snapshot_root"] = _root(77)
    with pytest.raises(ValueError, match="genesis parent"):
        HybridReplaySnapshotV2(**kwargs)

    snapshot = _snapshot()
    with pytest.raises(ValueError, match="run_ref is cross-bound"):
        HybridReplayAdvanceRequestV2(
            domain_root=snapshot.domain_root,
            scope_ref=snapshot.scope_ref,
            run_ref="run-b",
            target_ref=snapshot.target_ref,
            observed_epoch=snapshot.observed_epoch,
            advance_ref=snapshot.advance_ref,
            transition_id=snapshot.transition_id,
            stream_ref=snapshot.stream_ref,
            snapshot=snapshot,
        )


def test_request_root_detects_snapshot_substitution() -> None:
    payload = _request().to_dict()
    payload["snapshot"]["source_step_root"] = _root(88)
    payload["snapshot"]["source_lineage_root"] = ""
    payload["snapshot"]["state_root"] = ""
    payload["snapshot"]["snapshot_root"] = ""
    with pytest.raises(ValueError, match="request_root is mismatched"):
        HybridReplayAdvanceRequestV2.from_dict(payload)


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (("policy_projection", "mode"), "ant_colony", "mode='hybrid'"),
        (
            ("policy_projection", "min_independent_scouts"),
            0,
            "bounded non-negative integer",
        ),
        (
            ("policy_projection", "recruitment_enabled"),
            1,
            "exact boolean",
        ),
        (
            ("policy_projection", "pheromone_enabled"),
            False,
            "complete Hybrid path",
        ),
        (
            ("policy_projection", "pheromone_decay_model"),
            "unknown",
            "decay model is unsupported",
        ),
        (
            ("policy_projection", "pheromone_response_model"),
            "unknown",
            "response model is unsupported",
        ),
        (
            ("policy_projection", "pheromone_competition_mode"),
            "unknown",
            "competition mode is unsupported",
        ),
        (
            ("policy_projection", "pheromone_max_strength"),
            _binary64(0.0),
            "caps must be positive",
        ),
        (
            ("policy_projection", "pheromone_min_strength"),
            _binary64(4.0),
            "minimum strength exceeds",
        ),
        (
            ("policy_projection", "pheromone_scored_subject_types"),
            ["x-undeclared"],
            "scored subject type is unsupported",
        ),
        (
            (
                "policy_projection",
                "pheromone_kind_profiles",
                0,
                "response_model",
            ),
            "unknown",
            "profile response_model is unsupported",
        ),
        (
            (
                "policy_projection",
                "pheromone_kind_profiles",
                0,
                "scored_subject_types",
            ),
            ["x-undeclared"],
            "profile subject type is unsupported",
        ),
        (
            ("policy_projection", "layer_weight_bounds", 0, "layer_ref"),
            "unknown",
            "layer_ref is unsupported",
        ),
        (
            ("policy_projection", "layer_weight_bounds", 0, "minimum"),
            _binary64(2.0),
            "bounds are invalid",
        ),
        (
            (
                "policy_projection",
                "policy_adjustment_bounds",
                0,
                "field_ref",
            ),
            "unknown",
            "field_ref is unsupported",
        ),
        (
            (
                "policy_projection",
                "policy_adjustment_bounds",
                0,
                "minimum",
            ),
            _binary64(0.0),
            "allowed-values bound cannot contain numeric bounds",
        ),
        (
            (
                "policy_projection",
                "policy_adjustment_bounds",
                0,
                "bound_kind",
            ),
            "unknown",
            "bound kind is unsupported",
        ),
        (
            ("topology_projection", "subjects", 0, "candidate_ref"),
            "candidate-unknown",
            "undeclared candidate",
        ),
        (
            ("topology_projection", "subjects", 0, "target_ref"),
            "target-b",
            "target_ref is mismatched",
        ),
        (
            ("topology_projection", "edges", 0, "source_subject_ref"),
            "candidate-unknown",
            "edge endpoints are invalid",
        ),
        (
            ("active_trails", 0, "candidate_ref"),
            "candidate-unknown",
            "undeclared candidate",
        ),
        (
            ("active_trails", 0, "target_ref"),
            "target-b",
            "target_ref is mismatched",
        ),
        (
            ("active_trails", 0, "subject_ref"),
            "candidate-unknown",
            "subject is absent from topology",
        ),
        (
            ("active_trails", 0, "candidate_ref"),
            "fallback",
            "candidate subject is mismatched",
        ),
        (
            ("active_trails", 0, "updated_at_step"),
            0,
            "updated step precedes",
        ),
        (
            ("active_trails", 0, "ttl_steps"),
            0,
            "bounded non-negative integer",
        ),
        (
            ("active_trails", 0, "lineage_event_refs"),
            ["event-other"],
            "lineage must be unique and end",
        ),
        (
            ("active_trails", 0, "diffusion_root_trace_event_ref"),
            "event-root",
            "diffusion lineage is inconsistent",
        ),
    ],
)
def test_snapshot_rejects_invalid_policy_topology_and_trail_boundaries(
    path: tuple[object, ...], replacement: object, message: str
) -> None:
    kwargs = _snapshot_kwargs()
    _replace_nested(kwargs, path, replacement)

    with pytest.raises((TypeError, ValueError), match=message):
        HybridReplaySnapshotV2(**kwargs)


def test_snapshot_rejects_noncanonical_duplicate_policy_and_topology_entries() -> None:
    kwargs = _snapshot_kwargs()
    profiles = kwargs["policy_projection"]["pheromone_kind_profiles"]
    profiles.append(deepcopy(profiles[0]))
    with pytest.raises(
        ValueError, match="kind profiles must be unique canonical order"
    ):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["policy_projection"]["layer_default_weights"] = kwargs["policy_projection"][
        "layer_default_weights"
    ][:-1]
    with pytest.raises(ValueError, match="length is outside"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    bounds = kwargs["policy_projection"]["policy_adjustment_bounds"]
    bounds.append(deepcopy(bounds[0]))
    with pytest.raises(ValueError, match="adjustment bounds must be unique"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    subjects = kwargs["topology_projection"]["subjects"]
    subjects.append(deepcopy(subjects[0]))
    with pytest.raises(ValueError, match="subjects must be unique canonical order"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    edges = kwargs["topology_projection"]["edges"]
    edges.append(deepcopy(edges[0]))
    with pytest.raises(ValueError, match="edges must be unique canonical order"):
        HybridReplaySnapshotV2(**kwargs)


def test_snapshot_rejects_each_adjustment_bound_shape() -> None:
    kwargs = _snapshot_kwargs()
    bound = kwargs["policy_projection"]["policy_adjustment_bounds"][0]
    bound.update(
        {
            "bound_kind": "binary64_range",
            "minimum": _binary64(2.0),
            "maximum": _binary64(1.0),
            "allowed_values": [],
        }
    )
    with pytest.raises(ValueError, match="numeric adjustment bound is invalid"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    bound = kwargs["policy_projection"]["policy_adjustment_bounds"][0]
    bound.update(
        {
            "bound_kind": "binary64_range",
            "minimum": _binary64(0.0),
            "maximum": _binary64(1.0),
            "allowed_values": ["linear"],
        }
    )
    with pytest.raises(ValueError, match="numeric adjustment bound is invalid"):
        HybridReplaySnapshotV2(**kwargs)


def test_snapshot_rejects_duplicate_trails_and_receipt_envelope_substitution() -> None:
    kwargs = _snapshot_kwargs()
    kwargs["active_trails"].append(deepcopy(kwargs["active_trails"][0]))
    with pytest.raises(
        ValueError, match="active trails must be unique canonical order"
    ):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["replay_receipts"][0]["event_id"] = "event-other"
    with pytest.raises(ValueError, match="deposit receipt event id is mismatched"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["replay_receipts"][0]["payload_root"] = 7
    with pytest.raises(TypeError, match="payload_root must be text"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["replay_receipts"][0]["payload_root"] = _root(99)
    with pytest.raises(ValueError, match="payload_root is mismatched"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["replay_receipts"][0]["kind"] = "unknown"
    with pytest.raises(ValueError, match="receipt kind is unsupported"):
        HybridReplaySnapshotV2(**kwargs)


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (("subject_ref",), "candidate-unknown", "subject is absent from topology"),
        (("candidate_ref",), "candidate-unknown", "candidate or target is mismatched"),
        (("target_ref",), "target-b", "candidate or target is mismatched"),
        (("candidate_ref",), "fallback", "candidate subject is mismatched"),
        (("outcome",), "unknown", "outcome is unsupported"),
        (("trace_event_ref",), "event-other", "event id is mismatched"),
    ],
)
def test_feedback_receipt_rejects_cross_binding_and_closed_enum_substitution(
    path: tuple[object, ...], replacement: object, message: str
) -> None:
    kwargs = _snapshot_kwargs()
    payload = _feedback_payload()
    _replace_nested(payload, path, replacement)
    kwargs["replay_receipts"].append(
        {
            "kind": "feedback",
            "event_id": "event-feedback",
            "payload": payload,
            "payload_root": "",
        }
    )

    with pytest.raises(ValueError, match=message):
        HybridReplaySnapshotV2(**kwargs)


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (("layer_ref",), "reactive", "adjustment layer is unsupported"),
        (("adjustments",), [], "must contain an adjustment"),
        (("trace_event_ref",), "event-other", "event id is mismatched"),
        (
            ("adjustments", 0, "field_ref"),
            "unknown",
            "field_ref is unsupported",
        ),
        (
            ("adjustments", 0, "value_kind"),
            "unknown",
            "value_kind is unsupported",
        ),
        (
            ("adjustments", 0, "value_kind"),
            "binary64",
            "response model must use text",
        ),
        (
            ("adjustments", 0, "field_ref"),
            "pheromone_positive_weight",
            "text adjustment is unsupported",
        ),
    ],
)
def test_adjustment_receipt_rejects_unauthorized_or_malformed_adjustments(
    path: tuple[object, ...], replacement: object, message: str
) -> None:
    kwargs = _snapshot_kwargs()
    payload = _adjustment_payload()
    _replace_nested(payload, path, replacement)
    if path == ("adjustments", 0, "value_kind") and replacement == "binary64":
        payload["adjustments"][0]["value"] = _binary64(0.5)
    kwargs["replay_receipts"] = [
        {
            "kind": "adjustment",
            "event_id": "event-adjustment",
            "payload": payload,
            "payload_root": "",
        }
    ]

    with pytest.raises((TypeError, ValueError), match=message):
        HybridReplaySnapshotV2(**kwargs)


def test_adjustment_values_and_budget_reject_duplicate_or_out_of_bounds_state() -> None:
    kwargs = _snapshot_kwargs()
    payload = _adjustment_payload()
    payload["adjustments"].append(deepcopy(payload["adjustments"][0]))
    kwargs["replay_receipts"] = [
        {
            "kind": "adjustment",
            "event_id": "event-adjustment",
            "payload": payload,
            "payload_root": "",
        }
    ]
    with pytest.raises(ValueError, match="must be unique canonical order"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["last_budget"]["round_used"] = _binary64(6.0)
    with pytest.raises(ValueError, match="budget values are outside declared bounds"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["last_budget"]["source_used"][0]["used"] = _binary64(4.0)
    with pytest.raises(ValueError, match="source budget usage exceeds its cap"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    source = kwargs["last_budget"]["source_used"][0]
    kwargs["last_budget"]["source_used"].append(deepcopy(source))
    kwargs["last_budget"]["round_used"] = _binary64(2.0)
    with pytest.raises(
        ValueError, match="source budgets must be unique canonical order"
    ):
        HybridReplaySnapshotV2(**kwargs)


def test_overlay_rejects_lineage_without_values_and_unknown_or_wrong_bound_kinds() -> (
    None
):
    kwargs = _snapshot_kwargs()
    kwargs["overlay"] = {
        "values": [],
        "source_refs": ["learner-a"],
        "trace_roots": [],
    }
    with pytest.raises(ValueError, match="empty Hybrid replay overlay"):
        HybridReplaySnapshotV2(**kwargs)

    policy = {
        "policy_adjustment_bounds": (
            {
                "field_ref": "pheromone_positive_weight",
                "bound_kind": "binary64_range",
                "minimum": _binary64(0.0),
                "maximum": _binary64(1.0),
                "allowed_values": (),
            },
        )
    }
    with pytest.raises(ValueError, match="outside declared bounds"):
        contracts._validate_overlay_against_policy(
            {
                "values": (
                    {
                        "field_ref": "unknown",
                        "value_kind": "binary64",
                        "value": _binary64(0.5),
                    },
                )
            },
            policy,
        )
    with pytest.raises(ValueError, match="numeric bound kind is mismatched"):
        contracts._validate_overlay_against_policy(
            {
                "values": (
                    {
                        "field_ref": "pheromone_response_model",
                        "value_kind": "binary64",
                        "value": _binary64(0.5),
                    },
                )
            },
            {
                "policy_adjustment_bounds": (
                    {
                        "field_ref": "pheromone_response_model",
                        "bound_kind": "allowed_values",
                        "minimum": None,
                        "maximum": None,
                        "allowed_values": ("linear",),
                    },
                )
            },
        )
    with pytest.raises(ValueError, match="overlay value is outside declared bounds"):
        contracts._validate_overlay_against_policy(
            {
                "values": (
                    {
                        "field_ref": "pheromone_positive_weight",
                        "value_kind": "binary64",
                        "value": _binary64(2.0),
                    },
                )
            },
            policy,
        )


def test_snapshot_rejects_candidate_policy_and_parent_identity_substitution() -> None:
    kwargs = _snapshot_kwargs()
    kwargs["candidate_projection"]["candidates"][0]["target_ref"] = "target-b"
    with pytest.raises(ValueError, match="candidate target_ref is mismatched"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["candidate_projection"]["candidates"][1]["safe_fallback"] = False
    with pytest.raises(ValueError, match="fallback candidate must be declared safe"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["policy_projection"]["pheromone_kind_profiles"][0]["kind"] = "unknown"
    with pytest.raises(ValueError, match="profile kind is unsupported"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["policy_projection"]["layer_default_weights"][-1]["layer_ref"] = "learned"
    with pytest.raises(ValueError, match="must cover every layer in canonical order"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["revision"] = 2
    with pytest.raises(ValueError, match="revision must advance exactly one"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["revision"] = 2
    kwargs["parent_revision"] = 1
    with pytest.raises(ValueError, match="non-genesis parent lineage"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["stream_ref"] = "authority:hybrid-replay-v2:" + ("0" * 64)
    with pytest.raises(ValueError, match="stream_ref is mismatched"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs()
    kwargs["transition_id"] = "transition:hybrid-replay-v2:" + ("0" * 64)
    with pytest.raises(ValueError, match="transition_id is mismatched"):
        HybridReplaySnapshotV2(**kwargs)


def test_overlay_trace_lineage_must_be_present_in_snapshot_source_roots() -> None:
    kwargs = _snapshot_kwargs()
    effective = deepcopy(kwargs["policy_projection"])
    effective["pheromone_response_model"] = "saturating"
    effective["pheromone_kind_profiles"][0]["response_model"] = "saturating"
    kwargs["effective_policy_projection"] = effective
    kwargs["overlay"] = {
        "values": [
            {
                "field_ref": "pheromone_response_model",
                "value_kind": "text",
                "value": "saturating",
            }
        ],
        "source_refs": ["learner-a"],
        "trace_roots": [_root(99)],
    }

    with pytest.raises(ValueError, match="absent from source lineage"):
        HybridReplaySnapshotV2(**kwargs)


@pytest.mark.parametrize(
    ("path", "replacement", "message"),
    [
        (
            ("input", "edge", "attenuation"),
            -0.1,
            "below its declared bound",
        ),
        (
            ("input", "edge", "attenuation"),
            2.0,
            "exceeds its declared bound",
        ),
        (("lifecycle",), "deposit", "payload lifecycle is mismatched"),
        (
            ("input", "target_subject", "subject_id"),
            "candidate-a",
            "target and edge are mismatched",
        ),
        (
            ("input", "edge", "source_subject_id"),
            "fallback",
            "source trail and edge are mismatched",
        ),
        (
            ("effective", "source_id"),
            "scout-b",
            "effective lineage is mismatched",
        ),
        (
            ("input", "parent_trace_event_id"),
            "event-other",
            "parent event is mismatched",
        ),
        (
            ("input", "target_subject", "candidate_id"),
            "candidate-a",
            "target candidate is mismatched",
        ),
        (
            ("input", "target_subject", "target"),
            "target-b",
            "canonical target is mismatched",
        ),
    ],
)
def test_diffusion_causal_payload_rejects_numeric_and_lineage_substitution(
    path: tuple[object, ...], replacement: object, message: str
) -> None:
    kwargs = _snapshot_kwargs_with_mutated_diffusion_causal_payload(path, replacement)

    with pytest.raises(ValueError, match=message):
        HybridReplaySnapshotV2(**kwargs)


def test_diffusion_receipt_rejects_summary_and_declared_topology_substitution() -> None:
    kwargs = _snapshot_kwargs_with_mutated_diffusion_causal_payload(
        ("input", "source_trail", "candidate_id"), "candidate-unknown"
    )
    with pytest.raises(ValueError, match="source candidate or target is mismatched"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs_with_diffusion()
    payload = kwargs["replay_receipts"][1]["payload"]
    payload["target_subject_ref"] = "candidate-unknown"
    with pytest.raises(ValueError, match="target subject is absent from topology"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs_with_diffusion()
    kwargs["replay_receipts"][1]["payload"]["candidate_ref"] = "candidate-unknown"
    with pytest.raises(ValueError, match="candidate or target is mismatched"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs_with_diffusion()
    kwargs["replay_receipts"][1]["payload"]["derived_event_id"] = "event-other"
    with pytest.raises(ValueError, match="receipt event id is mismatched"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs_with_diffusion()
    payload = kwargs["replay_receipts"][1]["payload"]
    payload["target_subject_ref"] = "candidate-a"
    payload["candidate_ref"] = "candidate-a"
    with pytest.raises(ValueError, match="canonical target subject is mismatched"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs_with_diffusion()
    kwargs["replay_receipts"][1]["payload"]["candidate_ref"] = "candidate-a"
    with pytest.raises(ValueError, match="target subject binding is mismatched"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs_with_mutated_diffusion_causal_payload(
        ("input", "edge", "attenuation"), 0.25
    )
    kwargs["replay_receipts"][1]["payload"]["edge_attenuation"] = _binary64(0.25)
    with pytest.raises(ValueError, match="edge attenuation is undeclared"):
        HybridReplaySnapshotV2(**kwargs)

    kwargs = _snapshot_kwargs_with_mutated_diffusion_causal_payload(
        ("input", "policy_attenuation"), 0.25
    )
    kwargs["replay_receipts"][1]["payload"]["policy_attenuation"] = _binary64(0.25)
    with pytest.raises(ValueError, match="policy attenuation is undeclared"):
        HybridReplaySnapshotV2(**kwargs)


def test_diffusion_binding_rejects_an_exact_but_undeclared_topology_edge() -> None:
    subject_key = ("candidate", "fallback")
    topology = contracts._TopologyIndexV2(
        subject_keys=frozenset({subject_key}),
        subjects_by_key={
            subject_key: {
                "candidate_ref": "fallback",
                "target_ref": "target-a",
            }
        },
        edges_by_key={},
    )

    with pytest.raises(ValueError, match="edge is absent from topology"):
        contracts._validate_diffusion_receipt_binding(
            {},
            input_payload={
                "target_subject": {
                    "subject_type": "candidate",
                    "subject_id": "fallback",
                }
            },
            effective={},
            causal_edge={
                "source_subject_type": "candidate",
                "source_subject_id": "candidate-a",
                "target_subject_type": "candidate",
                "target_subject_id": "fallback",
            },
            topology_index=topology,
            policy={},
            subject_key=subject_key,
            candidate_ref="fallback",
            target_ref="target-a",
        )


def test_effective_policy_overlay_updates_profile_and_layer_projections() -> None:
    expected = _policy_projection()
    contracts._apply_profile_overlay(
        expected,
        {
            "pheromone_evaporation_rate": _binary64(0.2),
            "pheromone_alarm_weight": _binary64(2.0),
        },
    )
    profiles = {item["kind"]: item for item in expected["pheromone_kind_profiles"]}
    assert profiles["positive"]["evaporation_rate"] == _binary64(0.2)
    assert profiles["alarm"]["weight"] == _binary64(2.0)

    contracts._apply_layer_overlay(
        expected,
        {"layer_learned_weight": _binary64(0.75)},
    )
    layers = {item["layer_ref"]: item for item in expected["layer_default_weights"]}
    assert layers["learned"]["value"] == _binary64(0.75)
