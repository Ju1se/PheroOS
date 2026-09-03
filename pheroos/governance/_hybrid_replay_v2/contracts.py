"""Portable, authority-free contracts for durable Hybrid replay v2.

The records in this module are exact wire snapshots.  They deliberately carry
no process-local issuance sentinel: StateStore inclusion and currentness are
required before another module may wrap a snapshot as verified authority.
Every binary64 leaf uses the frozen hexadecimal wire from :mod:`.numeric`.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
import json
from typing import ClassVar, cast

from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    MAX_AUTHORITY_REVISION_V2,
)

from pheroos.governance._authority_session_v2.contracts import _stream_ref
from pheroos.governance._authority_store_v2_contracts.foundation import (
    _canonical_bytes,
    _compute_root,
    _require_exact_version,
    _require_root,
    _require_text,
)
from pheroos.governance._hybrid_replay_v2.numeric import (
    HYBRID_REPLAY_NUMERIC_WIRE_VERSION_V2,
    decode_binary64_v1,
    encode_binary64_v1,
)
from pheroos.trace._pheromone_receipts import canonical_pheromone_clip_payload


HYBRID_REPLAY_SNAPSHOT_SCHEMA_V2 = "pheroos-governance-hybrid-replay-snapshot-v2"
HYBRID_REPLAY_ADVANCE_REQUEST_SCHEMA_V2 = (
    "pheroos-governance-hybrid-replay-advance-request-v2"
)
HYBRID_REPLAY_STATE_SCHEMA_V2 = "pheroos-governance-hybrid-replay-state-v2"

HYBRID_REPLAY_GENESIS_SNAPSHOT_ROOT_V2 = _compute_root(
    "hybrid-replay-genesis-snapshot",
    {
        "schema": HYBRID_REPLAY_STATE_SCHEMA_V2,
        "canonical_version": AUTHORITY_CANONICAL_VERSION_V2,
    },
)

MAX_HYBRID_REPLAY_TEXT_BYTES_V2 = 4096
MAX_HYBRID_REPLAY_CANDIDATES_V2 = 256
MAX_HYBRID_REPLAY_SUBJECTS_V2 = 2048
MAX_HYBRID_REPLAY_EDGES_V2 = 8192
MAX_HYBRID_REPLAY_TRAILS_V2 = 4096
MAX_HYBRID_REPLAY_RECEIPTS_V2 = 16384
MAX_HYBRID_REPLAY_TRACE_ROOTS_V2 = 1024
MAX_HYBRID_REPLAY_LINEAGE_EVENTS_V2 = 512
MAX_HYBRID_REPLAY_SOURCES_V2 = 4096
# A diffusion receipt retains a complete v1 causal envelope.  256 KiB is
# deliberately well above the closed envelope's ordinary size while keeping a
# single JSON parse small enough for an ABI boundary.  Aggregate limits below
# prevent item-count limits from multiplying this allowance into unbounded
# memory or hashing work.
MAX_HYBRID_REPLAY_CAUSAL_PAYLOAD_BYTES_V2 = 256 * 1024
MAX_HYBRID_REPLAY_TOTAL_CAUSAL_PAYLOAD_BYTES_V2 = 8 * 1024 * 1024
MAX_HYBRID_REPLAY_TOTAL_LINEAGE_BYTES_V2 = 4 * 1024 * 1024
MAX_HYBRID_REPLAY_RESOURCE_TEXT_BYTES_V2 = 12 * 1024 * 1024
MAX_HYBRID_REPLAY_SNAPSHOT_BYTES_V2 = 16 * 1024 * 1024
MAX_HYBRID_REPLAY_RESOURCE_NODES_V2 = 262_144
MAX_HYBRID_REPLAY_RESOURCE_DEPTH_V2 = 64

HYBRID_REPLAY_DIFFUSION_REPLAY_VERSION_V2 = "diffusion-v1"
_PHEROMONE_CLIP_PAYLOAD_VERSION_V1 = "pheroos-pheromone-clip-payload-v1"

_REPLAY_RECEIPT_KINDS = frozenset({"deposit", "diffusion", "feedback", "adjustment"})
_PHEROMONE_KINDS = frozenset(
    {"positive", "negative", "cautionary", "alarm", "novelty", "stale"}
)
_SUBJECT_TYPES = frozenset({"candidate", "route", "tool", "evidence", "agent"})
_RESPONSE_MODELS = frozenset({"linear", "saturating", "threshold", "competitive"})
_DECAY_MODELS = frozenset({"linear", "exponential", "step"})
_COMPETITION_MODES = frozenset({"none", "normalize"})
_LAYER_REFS = frozenset({"reactive", "learned", "evolutionary", "metacognitive"})
_FEEDBACK_OUTCOMES = frozenset(
    {"success", "failure", "blocked", "congested", "hazard", "novel", "stale"}
)
_ADJUSTMENT_FIELDS = frozenset(
    {
        "pheromone_evaporation_rate",
        "pheromone_response_model",
        "pheromone_exploration_floor",
        "pheromone_cautionary_override_threshold",
        "layer_emergency_override_threshold",
        "pheromone_positive_weight",
        "pheromone_negative_weight",
        "pheromone_cautionary_weight",
        "pheromone_alarm_weight",
        "pheromone_novelty_weight",
        "layer_learned_weight",
        "layer_evolutionary_weight",
        "layer_metacognitive_weight",
    }
)
_POLICY_FIELDS = frozenset(
    {
        "mode",
        "min_independent_scouts",
        "quorum_threshold",
        "recruitment_enabled",
        "inhibition_enabled",
        "pheromone_enabled",
        "pheromone_evaporation_rate",
        "pheromone_decay_model",
        "pheromone_min_strength",
        "pheromone_max_strength",
        "pheromone_positive_weight",
        "pheromone_negative_weight",
        "pheromone_cautionary_weight",
        "pheromone_cautionary_override_threshold",
        "pheromone_novelty_weight",
        "pheromone_per_source_cap",
        "pheromone_per_round_deposit_cap",
        "pheromone_min_source_diversity",
        "pheromone_require_provenance",
        "pheromone_require_trace",
        "pheromone_scored_subject_types",
        "pheromone_kind_profiles",
        "pheromone_response_model",
        "pheromone_activation_threshold",
        "pheromone_saturation_threshold",
        "pheromone_competition_mode",
        "pheromone_exploration_floor",
        "pheromone_diffusion_enabled",
        "pheromone_diffusion_max_hops",
        "pheromone_diffusion_attenuation",
        "pheromone_feedback_enabled",
        "exploration_enabled",
        "exploration_floor",
        "novelty_decay_rate",
        "stale_route_reopen_threshold",
        "layer_coordination_enabled",
        "layer_weight_bounds",
        "layer_default_weights",
        "layer_confidence_thresholds",
        "layer_conflict_threshold",
        "layer_emergency_override_threshold",
        "layer_min_provenance",
        "layer_fallback_on_unresolved_conflict",
        "policy_adjustment_bounds",
        "fallback_candidate_ref",
    }
)
_TRAIL_FIELDS = frozenset(
    {
        "candidate_ref",
        "strength",
        "subject_type",
        "subject_ref",
        "target_ref",
        "route_ref",
        "tool_ref",
        "kind",
        "source_ref",
        "source_role",
        "evidence_ref",
        "provenance_ref",
        "trace_event_ref",
        "deposited_at_step",
        "updated_at_step",
        "ttl_steps",
        "lineage_event_refs",
        "diffusion_root_trace_event_ref",
        "diffusion_parent_trace_event_ref",
        "diffusion_hop",
    }
)
_DIFFUSION_SOURCE_TRAIL_FIELDS = frozenset(
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

_LINEAGE_RESOURCE_FIELDS = frozenset(
    {
        "lineage_event_ids",
        "lineage_event_refs",
        "source_refs",
        "source_trace_roots",
        "trace_roots",
    }
)


class _FrozenJsonObject(Mapping[str, object]):
    """Small immutable, pickle-safe JSON object used by portable records."""

    __slots__ = ("_items",)
    _items: tuple[tuple[str, object], ...]

    def __init__(self, items: Sequence[tuple[str, object]]) -> None:
        object.__setattr__(self, "_items", tuple(items))

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("Hybrid replay portable objects are immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("Hybrid replay portable objects are immutable")

    def __getitem__(self, key: str) -> object:
        for item_key, value in self._items:
            if item_key == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __deepcopy__(self, memo: dict[int, object]) -> _FrozenJsonObject:
        del memo
        return self

    def __reduce__(self) -> tuple[object, tuple[tuple[tuple[str, object], ...]]]:
        return (type(self), (self._items,))


@dataclass(slots=True)
class _ResourceUsageV2:
    nodes: int = 0
    text_bytes: int = 0
    lineage_bytes: int = 0


def _record_resource_node_v2(usage: _ResourceUsageV2) -> None:
    usage.nodes += 1
    if usage.nodes > MAX_HYBRID_REPLAY_RESOURCE_NODES_V2:
        raise ValueError("Hybrid replay portable input exceeds its node bound")


def _record_resource_text_v2(
    value: str,
    *,
    path: str,
    lineage: bool,
    usage: _ResourceUsageV2,
) -> None:
    if len(value) > MAX_HYBRID_REPLAY_RESOURCE_TEXT_BYTES_V2 - usage.text_bytes:
        raise ValueError("Hybrid replay aggregate text exceeds its resource bound")
    if lineage and len(value) > (
        MAX_HYBRID_REPLAY_TOTAL_LINEAGE_BYTES_V2 - usage.lineage_bytes
    ):
        raise ValueError("Hybrid replay aggregate lineage exceeds its byte bound")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError(f"{path} must be valid UTF-8 text") from exc
    usage.text_bytes += size
    if usage.text_bytes > MAX_HYBRID_REPLAY_RESOURCE_TEXT_BYTES_V2:
        raise ValueError("Hybrid replay aggregate text exceeds its resource bound")
    if lineage:
        usage.lineage_bytes += size
        if usage.lineage_bytes > MAX_HYBRID_REPLAY_TOTAL_LINEAGE_BYTES_V2:
            raise ValueError("Hybrid replay aggregate lineage exceeds its byte bound")


def _walk_resource_sequence_v2(
    value: Sequence[object],
    *,
    path: str,
    depth: int,
    lineage: bool,
    active_containers: set[int],
    usage: _ResourceUsageV2,
) -> None:
    for index, item in enumerate(value):
        _walk_resource_value_v2(
            item,
            path=f"{path}/{index}",
            depth=depth + 1,
            lineage=lineage,
            active_containers=active_containers,
            usage=usage,
        )


def _walk_resource_mapping_v2(
    value: Mapping[object, object],
    *,
    path: str,
    depth: int,
    lineage: bool,
    active_containers: set[int],
    usage: _ResourceUsageV2,
) -> None:
    for index, (key, item) in enumerate(value.items()):
        _record_resource_node_v2(usage)
        key_path = f"{path}/key-{index}"
        child_lineage = lineage
        if type(key) is str:
            key_text = key
            key_path = f"{path}/{key_text}"
            _record_resource_text_v2(
                key_text, path=f"{path} key", lineage=False, usage=usage
            )
            child_lineage = lineage or key_text in _LINEAGE_RESOURCE_FIELDS
        _walk_resource_value_v2(
            item,
            path=key_path,
            depth=depth + 1,
            lineage=child_lineage,
            active_containers=active_containers,
            usage=usage,
        )


def _walk_resource_value_v2(
    value: object,
    *,
    path: str,
    depth: int,
    lineage: bool,
    active_containers: set[int],
    usage: _ResourceUsageV2,
) -> None:
    if depth > MAX_HYBRID_REPLAY_RESOURCE_DEPTH_V2:
        raise ValueError("Hybrid replay portable input exceeds its depth bound")
    _record_resource_node_v2(usage)
    if type(value) is str:
        _record_resource_text_v2((value), path=path, lineage=lineage, usage=usage)
        return
    if type(value) not in (list, tuple) and not isinstance(value, Mapping):
        return
    container_id = id(value)
    if container_id in active_containers:
        raise ValueError("Hybrid replay portable input contains a container cycle")
    active_containers.add(container_id)
    try:
        if type(value) in (list, tuple):
            _walk_resource_sequence_v2(
                cast(Sequence[object], value),
                path=path,
                depth=depth,
                lineage=lineage,
                active_containers=active_containers,
                usage=usage,
            )
            return
        _walk_resource_mapping_v2(
            cast(Mapping[object, object], value),
            path=path,
            depth=depth,
            lineage=lineage,
            active_containers=active_containers,
            usage=usage,
        )
    finally:
        active_containers.remove(container_id)


def _preflight_portable_resources_v2(value: object) -> _ResourceUsageV2:
    """Bound attacker-controlled structure before copying, sorting, or hashing."""

    usage = _ResourceUsageV2()
    _walk_resource_value_v2(
        value,
        path="hybrid replay portable input",
        depth=0,
        lineage=False,
        active_containers=set(),
        usage=usage,
    )
    return usage


def hybrid_replay_stream_ref_v2(
    scope_ref: str,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
) -> str:
    """Return the sole durable replay stream for one run target."""

    for label, value in (
        ("scope_ref", scope_ref),
        ("protocol_ref", protocol_ref),
        ("run_ref", run_ref),
        ("target_ref", target_ref),
    ):
        _require_bounded_text(value, f"hybrid replay {label}")
    return _stream_ref(
        "hybrid-replay-v2", (scope_ref, protocol_ref, run_ref, target_ref)
    )


def hybrid_replay_transition_id_v2(stream_ref: str, advance_ref: str) -> str:
    """Derive the sole transition identity for one stream advance request."""

    _require_bounded_text(stream_ref, "hybrid replay transition stream_ref")
    _require_bounded_text(advance_ref, "hybrid replay transition advance_ref")
    digest = sha256(
        stream_ref.encode("utf-8") + b"\x00" + advance_ref.encode("utf-8")
    ).hexdigest()
    return f"transition:hybrid-replay-v2:{digest}"


def _require_bounded_text(
    value: object, label: str, *, allow_empty: bool = False
) -> str:
    if allow_empty and type(value) is str and value == "":
        return ""
    text = _require_text(value, label)
    if len(text) > MAX_HYBRID_REPLAY_TEXT_BYTES_V2 or (
        len(text.encode("utf-8")) > MAX_HYBRID_REPLAY_TEXT_BYTES_V2
    ):
        raise ValueError(f"{label} exceeds the Hybrid replay text bound")
    return text


def _require_count(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= (value) <= MAX_AUTHORITY_REVISION_V2:
        raise ValueError(f"{label} must be a bounded non-negative integer")
    return value


def _require_exact_mapping(
    value: object,
    fields: frozenset[str],
    label: str,
) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an exact object")
    copied = dict(value)
    if set(copied) != fields:
        missing = sorted(fields - set(copied))
        unknown = sorted(set(copied) - fields)
        raise ValueError(
            f"{label} fields invalid: missing={missing}, unknown={unknown}"
        )
    return copied


def _require_sequence(
    value: object,
    label: str,
    *,
    maximum: int,
    minimum: int = 0,
) -> tuple[object, ...]:
    if type(value) not in (list, tuple):
        raise TypeError(f"{label} must be an exact array")
    items = tuple(cast(Sequence[object], value))
    if not minimum <= len(items) <= maximum:
        raise ValueError(f"{label} length is outside the Hybrid replay bound")
    return items


def _require_bool(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{label} must be an exact boolean")
    return value


def _require_binary64(
    value: object,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> str:
    number = decode_binary64_v1(value, label)
    if minimum is not None and number < minimum:
        raise ValueError(f"{label} is below its declared bound")
    if maximum is not None and number > maximum:
        raise ValueError(f"{label} exceeds its declared bound")
    return cast(str, value)


def _freeze_json(value: object, path: str) -> object:
    """Freeze only the closed, float-free portable JSON subset."""

    if isinstance(value, _FrozenJsonObject):
        # Owner helpers construct these only after exact validation.  Reusing
        # the immutable value avoids applying the generic 4 KiB text limit to
        # the separately bounded diffusion causal envelope.
        return value
    if value is None or type(value) in (bool, int, str):
        if type(value) is int:
            _require_count(value, path)
        if type(value) is str and (
            len((value)) > MAX_HYBRID_REPLAY_TEXT_BYTES_V2
            or len((value).encode("utf-8")) > MAX_HYBRID_REPLAY_TEXT_BYTES_V2
        ):
            raise ValueError(f"{path} exceeds the Hybrid replay text bound")
        return value
    if type(value) in (list, tuple):
        return tuple(
            _freeze_json(item, f"{path}/{index}")
            for index, item in enumerate(cast(Sequence[object], value))
        )
    if isinstance(value, Mapping):
        copied = dict(value)
        entries: list[tuple[str, object]] = []
        for key in sorted(copied):
            _require_bounded_text(key, f"{path} key")
            entries.append((key, _freeze_json(copied[key], f"{path}/{key}")))
        return _FrozenJsonObject(entries)
    if isinstance(value, float):
        raise TypeError(
            f"{path} must encode binary64 values as canonical hexadecimal text"
        )
    raise TypeError(f"{path} contains an unsupported portable value")


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_thaw_json(item) for item in cast(tuple[object, ...], value)]
    return value


def _frozen_object(value: Mapping[str, object], path: str) -> _FrozenJsonObject:
    # The Mapping input makes _FrozenJsonObject the sole possible successful
    # result.  _freeze_json raises for unsupported keys/values, so a second
    # type branch here would be unreachable duplicate validation.
    return cast(_FrozenJsonObject, _freeze_json(value, path))


def _install_exact_root(
    instance: object,
    attribute: str,
    supplied: object,
    kind: str,
    body: object,
) -> str:
    computed = _compute_root(kind, body)
    if type(supplied) is str and supplied == "":
        object.__setattr__(instance, attribute, computed)
        return computed
    _require_root(supplied, f"hybrid replay {attribute}")
    if not compare_digest(cast(str, supplied), computed):
        raise ValueError(f"hybrid replay {attribute} is mismatched")
    object.__setattr__(instance, attribute, computed)
    return computed


def _canonical_text_array(
    value: object,
    label: str,
    *,
    maximum: int,
    minimum: int = 0,
    roots: bool = False,
) -> tuple[str, ...]:
    items = _require_sequence(value, label, maximum=maximum, minimum=minimum)
    normalized: list[str] = []
    for item in items:
        if roots:
            normalized.append(_require_root(item, label))
        else:
            normalized.append(_require_bounded_text(item, label))
    if normalized != sorted(normalized) or len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} must be unique canonical order")
    return tuple(normalized)


def _freeze_candidate_projection(
    value: object,
    target_ref: str,
) -> tuple[_FrozenJsonObject, frozenset[str], str]:
    projection = _require_exact_mapping(
        value,
        frozenset({"candidates", "fallback_candidate_ref"}),
        "hybrid replay candidate projection",
    )
    candidate_items = _require_sequence(
        projection["candidates"],
        "hybrid replay candidates",
        maximum=MAX_HYBRID_REPLAY_CANDIDATES_V2,
        minimum=1,
    )
    candidates: list[_FrozenJsonObject] = []
    refs: list[str] = []
    safe_refs: set[str] = set()
    for index, item in enumerate(candidate_items):
        candidate = _require_exact_mapping(
            item,
            frozenset({"candidate_ref", "target_ref", "safe_fallback"}),
            f"hybrid replay candidate/{index}",
        )
        candidate_ref = _require_bounded_text(
            candidate["candidate_ref"], f"hybrid replay candidate/{index}/candidate_ref"
        )
        if candidate["target_ref"] != target_ref:
            raise ValueError("hybrid replay candidate target_ref is mismatched")
        _require_bool(
            candidate["safe_fallback"], "hybrid replay candidate safe_fallback"
        )
        if cast(bool, candidate["safe_fallback"]):
            safe_refs.add(candidate_ref)
        refs.append(candidate_ref)
        candidates.append(_frozen_object(candidate, f"candidate/{index}"))
    if refs != sorted(refs) or len(refs) != len(set(refs)):
        raise ValueError("hybrid replay candidates must be unique canonical order")
    fallback = _require_bounded_text(
        projection["fallback_candidate_ref"],
        "hybrid replay fallback_candidate_ref",
    )
    if fallback not in safe_refs:
        raise ValueError("hybrid replay fallback candidate must be declared safe")
    frozen = _frozen_object(
        {"candidates": tuple(candidates), "fallback_candidate_ref": fallback},
        "candidate_projection",
    )
    return frozen, frozenset(refs), fallback


def _require_extension_or_member(
    value: object,
    members: frozenset[str],
    label: str,
) -> str:
    text = _require_bounded_text(value, label)
    if text not in members and not text.startswith(("x-", "ext.")):
        raise ValueError(f"{label} is unsupported")
    return text


def _freeze_kind_profiles(value: object) -> tuple[_FrozenJsonObject, ...]:
    items = _require_sequence(
        value,
        "hybrid replay pheromone kind profiles",
        maximum=32,
        minimum=1,
    )
    fields = frozenset(
        {
            "kind",
            "weight",
            "evaporation_rate",
            "ttl_steps",
            "response_model",
            "priority",
            "can_suppress_positive",
            "scored_subject_types",
        }
    )
    result: list[_FrozenJsonObject] = []
    kinds: list[str] = []
    for index, item in enumerate(items):
        profile = _require_exact_mapping(
            item, fields, f"hybrid replay kind profile/{index}"
        )
        kind = _require_extension_or_member(
            profile["kind"], _PHEROMONE_KINDS, "hybrid replay profile kind"
        )
        _require_binary64(
            profile["weight"],
            "hybrid replay profile weight",
            minimum=0.0,
            maximum=1.0e12,
        )
        if profile["evaporation_rate"] is not None:
            _require_binary64(
                profile["evaporation_rate"],
                "hybrid replay profile evaporation_rate",
                minimum=0.0,
                maximum=1.0,
            )
        if profile["ttl_steps"] is not None:
            _require_count(profile["ttl_steps"], "hybrid replay profile ttl_steps")
        if profile["response_model"] not in _RESPONSE_MODELS:
            raise ValueError("hybrid replay profile response_model is unsupported")
        _require_count(profile["priority"], "hybrid replay profile priority")
        _require_bool(
            profile["can_suppress_positive"],
            "hybrid replay profile can_suppress_positive",
        )
        subjects = _canonical_text_array(
            profile["scored_subject_types"],
            "hybrid replay profile scored_subject_types",
            maximum=len(_SUBJECT_TYPES),
        )
        if any(subject not in _SUBJECT_TYPES for subject in subjects):
            raise ValueError("hybrid replay profile subject type is unsupported")
        profile["scored_subject_types"] = subjects
        kinds.append(kind)
        result.append(_frozen_object(profile, f"kind_profile/{index}"))
    if kinds != sorted(kinds) or len(kinds) != len(set(kinds)):
        raise ValueError("hybrid replay kind profiles must be unique canonical order")
    return tuple(result)


def _freeze_layer_scalars(
    value: object,
    *,
    bounds: bool,
    label: str,
) -> tuple[_FrozenJsonObject, ...]:
    items = _require_sequence(
        value, label, maximum=len(_LAYER_REFS), minimum=len(_LAYER_REFS)
    )
    expected_fields = (
        frozenset({"layer_ref", "minimum", "maximum"})
        if bounds
        else frozenset({"layer_ref", "value"})
    )
    result: list[_FrozenJsonObject] = []
    refs: list[str] = []
    for index, item in enumerate(items):
        entry = _require_exact_mapping(item, expected_fields, f"{label}/{index}")
        layer_ref = _require_bounded_text(entry["layer_ref"], f"{label} layer_ref")
        if layer_ref not in _LAYER_REFS:
            raise ValueError(f"{label} layer_ref is unsupported")
        if bounds:
            minimum = decode_binary64_v1(entry["minimum"], f"{label} minimum")
            maximum = decode_binary64_v1(entry["maximum"], f"{label} maximum")
            if not 0.0 <= minimum <= maximum <= 1.0e12:
                raise ValueError(f"{label} bounds are invalid")
        else:
            _require_binary64(
                entry["value"], f"{label} value", minimum=0.0, maximum=1.0e12
            )
        refs.append(layer_ref)
        result.append(_frozen_object(entry, f"{label}/{index}"))
    if refs != sorted(refs) or set(refs) != _LAYER_REFS:
        raise ValueError(f"{label} must cover every layer in canonical order")
    return tuple(result)


def _freeze_adjustment_bounds(value: object) -> tuple[_FrozenJsonObject, ...]:
    items = _require_sequence(
        value,
        "hybrid replay policy adjustment bounds",
        maximum=len(_ADJUSTMENT_FIELDS),
        minimum=1,
    )
    fields = frozenset(
        {"field_ref", "bound_kind", "minimum", "maximum", "allowed_values"}
    )
    result: list[_FrozenJsonObject] = []
    refs: list[str] = []
    for index, item in enumerate(items):
        entry = _require_exact_mapping(
            item, fields, f"hybrid replay adjustment bound/{index}"
        )
        field_ref = _require_bounded_text(
            entry["field_ref"], "hybrid replay adjustment bound field_ref"
        )
        if field_ref not in _ADJUSTMENT_FIELDS:
            raise ValueError("hybrid replay adjustment bound field_ref is unsupported")
        if entry["bound_kind"] == "binary64_range":
            minimum = decode_binary64_v1(
                entry["minimum"], "hybrid replay adjustment bound minimum"
            )
            maximum = decode_binary64_v1(
                entry["maximum"], "hybrid replay adjustment bound maximum"
            )
            if (
                minimum > maximum
                or entry["allowed_values"] != []
                and entry["allowed_values"] != ()
            ):
                raise ValueError("hybrid replay numeric adjustment bound is invalid")
            entry["allowed_values"] = ()
        elif entry["bound_kind"] == "allowed_values":
            if entry["minimum"] is not None or entry["maximum"] is not None:
                raise ValueError(
                    "hybrid replay allowed-values bound cannot contain numeric bounds"
                )
            allowed = _canonical_text_array(
                entry["allowed_values"],
                "hybrid replay adjustment allowed_values",
                maximum=32,
                minimum=1,
            )
            entry["allowed_values"] = allowed
        else:
            raise ValueError("hybrid replay adjustment bound kind is unsupported")
        refs.append(field_ref)
        result.append(_frozen_object(entry, f"adjustment_bound/{index}"))
    if refs != sorted(refs) or len(refs) != len(set(refs)):
        raise ValueError(
            "hybrid replay adjustment bounds must be unique canonical order"
        )
    return tuple(result)


def _validate_policy_identity_and_flags(policy: dict[str, object]) -> None:
    if policy["mode"] != "hybrid":
        raise ValueError("hybrid replay policy projection requires mode='hybrid'")
    for field in ("min_independent_scouts", "quorum_threshold"):
        _require_count(policy[field], f"hybrid replay policy {field}", minimum=1)
    for field in (
        "recruitment_enabled",
        "inhibition_enabled",
        "pheromone_enabled",
        "pheromone_require_provenance",
        "pheromone_require_trace",
        "pheromone_diffusion_enabled",
        "pheromone_feedback_enabled",
        "exploration_enabled",
        "layer_coordination_enabled",
        "layer_fallback_on_unresolved_conflict",
    ):
        _require_bool(policy[field], f"hybrid replay policy {field}")
    if not all(
        cast(bool, policy[field])
        for field in (
            "pheromone_enabled",
            "pheromone_require_provenance",
            "pheromone_require_trace",
            "pheromone_diffusion_enabled",
            "pheromone_feedback_enabled",
            "layer_coordination_enabled",
        )
    ):
        raise ValueError(
            "hybrid replay policy projection is not the complete Hybrid path"
        )
    if policy["pheromone_decay_model"] not in _DECAY_MODELS:
        raise ValueError("hybrid replay policy decay model is unsupported")
    if policy["pheromone_response_model"] not in _RESPONSE_MODELS:
        raise ValueError("hybrid replay policy response model is unsupported")
    if policy["pheromone_competition_mode"] not in _COMPETITION_MODES:
        raise ValueError("hybrid replay policy competition mode is unsupported")


def _validate_policy_numbers(policy: dict[str, object]) -> None:
    rate_fields = (
        "pheromone_evaporation_rate",
        "pheromone_diffusion_attenuation",
        "pheromone_exploration_floor",
        "exploration_floor",
        "novelty_decay_rate",
        "layer_conflict_threshold",
        "layer_emergency_override_threshold",
    )
    for field in rate_fields:
        _require_binary64(
            policy[field], f"hybrid replay policy {field}", minimum=0.0, maximum=1.0
        )
    nonnegative_fields = (
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
        "stale_route_reopen_threshold",
    )
    for field in nonnegative_fields:
        _require_binary64(
            policy[field], f"hybrid replay policy {field}", minimum=0.0, maximum=1.0e12
        )
    minimum_strength = decode_binary64_v1(
        policy["pheromone_min_strength"], "minimum strength"
    )
    maximum_strength = decode_binary64_v1(
        policy["pheromone_max_strength"], "maximum strength"
    )
    source_cap = decode_binary64_v1(policy["pheromone_per_source_cap"], "source cap")
    round_cap = decode_binary64_v1(
        policy["pheromone_per_round_deposit_cap"], "round cap"
    )
    if maximum_strength <= 0.0 or source_cap <= 0.0 or round_cap <= 0.0:
        raise ValueError(
            "hybrid replay policy strength and budget caps must be positive"
        )
    if minimum_strength > min(maximum_strength, source_cap, round_cap):
        raise ValueError("hybrid replay minimum strength exceeds a declared cap")
    for field in (
        "pheromone_min_source_diversity",
        "layer_min_provenance",
    ):
        _require_count(policy[field], f"hybrid replay policy {field}", minimum=1)
    _require_count(
        policy["pheromone_diffusion_max_hops"],
        "hybrid replay policy pheromone_diffusion_max_hops",
        minimum=1,
    )


def _freeze_policy_collections(policy: dict[str, object]) -> None:
    subjects = _canonical_text_array(
        policy["pheromone_scored_subject_types"],
        "hybrid replay policy scored subject types",
        maximum=len(_SUBJECT_TYPES),
        minimum=1,
    )
    if any(item not in _SUBJECT_TYPES for item in subjects):
        raise ValueError("hybrid replay scored subject type is unsupported")
    policy["pheromone_scored_subject_types"] = subjects
    policy["pheromone_kind_profiles"] = _freeze_kind_profiles(
        policy["pheromone_kind_profiles"]
    )
    policy["layer_weight_bounds"] = _freeze_layer_scalars(
        policy["layer_weight_bounds"],
        bounds=True,
        label="hybrid replay layer weight bounds",
    )
    policy["layer_default_weights"] = _freeze_layer_scalars(
        policy["layer_default_weights"],
        bounds=False,
        label="hybrid replay layer default weights",
    )
    policy["layer_confidence_thresholds"] = _freeze_layer_scalars(
        policy["layer_confidence_thresholds"],
        bounds=False,
        label="hybrid replay layer confidence thresholds",
    )
    policy["policy_adjustment_bounds"] = _freeze_adjustment_bounds(
        policy["policy_adjustment_bounds"]
    )


def _freeze_policy_projection(
    value: object,
    *,
    candidates: frozenset[str],
    fallback_candidate_ref: str,
) -> _FrozenJsonObject:
    policy = _require_exact_mapping(
        value, _POLICY_FIELDS, "hybrid replay policy projection"
    )
    _validate_policy_identity_and_flags(policy)
    _validate_policy_numbers(policy)
    _freeze_policy_collections(policy)
    fallback = _require_bounded_text(
        policy["fallback_candidate_ref"],
        "hybrid replay policy fallback_candidate_ref",
    )
    if fallback != fallback_candidate_ref or fallback not in candidates:
        raise ValueError("hybrid replay policy fallback candidate is mismatched")
    return _frozen_object(policy, "policy_projection")


def _freeze_topology_projection(
    value: object,
    *,
    target_ref: str,
    candidates: frozenset[str],
) -> _FrozenJsonObject:
    topology = _require_exact_mapping(
        value,
        frozenset({"subjects", "edges"}),
        "hybrid replay topology projection",
    )
    subject_items = _require_sequence(
        topology["subjects"],
        "hybrid replay topology subjects",
        maximum=MAX_HYBRID_REPLAY_SUBJECTS_V2,
        minimum=1,
    )
    subjects: list[_FrozenJsonObject] = []
    subject_keys: list[tuple[str, str]] = []
    for index, item in enumerate(subject_items):
        subject = _require_exact_mapping(
            item,
            frozenset({"subject_type", "subject_ref", "candidate_ref", "target_ref"}),
            f"hybrid replay topology subject/{index}",
        )
        subject_type = _require_extension_or_member(
            subject["subject_type"],
            _SUBJECT_TYPES,
            "hybrid replay topology subject type",
        )
        subject_ref = _require_bounded_text(
            subject["subject_ref"], "hybrid replay topology subject_ref"
        )
        candidate_ref = _require_bounded_text(
            subject["candidate_ref"],
            "hybrid replay topology candidate_ref",
            allow_empty=True,
        )
        if candidate_ref and candidate_ref not in candidates:
            raise ValueError(
                "hybrid replay topology references an undeclared candidate"
            )
        if subject_type == "candidate" and candidate_ref != subject_ref:
            raise ValueError(
                "hybrid replay candidate subject must bind its candidate_ref"
            )
        if subject["target_ref"] != target_ref:
            raise ValueError("hybrid replay topology target_ref is mismatched")
        subject_keys.append((subject_type, subject_ref))
        subjects.append(_frozen_object(subject, f"topology_subject/{index}"))
    if subject_keys != sorted(subject_keys) or len(subject_keys) != len(
        set(subject_keys)
    ):
        raise ValueError(
            "hybrid replay topology subjects must be unique canonical order"
        )
    edge_items = _require_sequence(
        topology["edges"],
        "hybrid replay topology edges",
        maximum=MAX_HYBRID_REPLAY_EDGES_V2,
    )
    edges: list[_FrozenJsonObject] = []
    edge_keys: list[tuple[str, str, str, str]] = []
    subject_set = set(subject_keys)
    for index, item in enumerate(edge_items):
        edge = _require_exact_mapping(
            item,
            frozenset(
                {
                    "source_subject_type",
                    "source_subject_ref",
                    "target_subject_type",
                    "target_subject_ref",
                    "attenuation",
                }
            ),
            f"hybrid replay topology edge/{index}",
        )
        source_key = (
            _require_extension_or_member(
                edge["source_subject_type"],
                _SUBJECT_TYPES,
                "hybrid replay edge source type",
            ),
            _require_bounded_text(
                edge["source_subject_ref"], "hybrid replay edge source ref"
            ),
        )
        target_key = (
            _require_extension_or_member(
                edge["target_subject_type"],
                _SUBJECT_TYPES,
                "hybrid replay edge target type",
            ),
            _require_bounded_text(
                edge["target_subject_ref"], "hybrid replay edge target ref"
            ),
        )
        if (
            source_key not in subject_set
            or target_key not in subject_set
            or source_key == target_key
        ):
            raise ValueError("hybrid replay topology edge endpoints are invalid")
        _require_binary64(
            edge["attenuation"],
            "hybrid replay edge attenuation",
            minimum=0.0,
            maximum=1.0,
        )
        edge_keys.append((*source_key, *target_key))
        edges.append(_frozen_object(edge, f"topology_edge/{index}"))
    if edge_keys != sorted(edge_keys) or len(edge_keys) != len(set(edge_keys)):
        raise ValueError("hybrid replay topology edges must be unique canonical order")
    return _frozen_object(
        {"subjects": tuple(subjects), "edges": tuple(edges)}, "topology"
    )


def _validate_trail_bindings(
    trail: dict[str, object],
    *,
    label: str,
    target_ref: str,
    candidates: frozenset[str],
    subject_keys: frozenset[tuple[str, str]],
) -> None:
    candidate_ref = _require_bounded_text(
        trail["candidate_ref"], f"{label} candidate_ref"
    )
    if candidate_ref not in candidates:
        raise ValueError(f"{label} references an undeclared candidate")
    if trail["target_ref"] != target_ref:
        raise ValueError(f"{label} target_ref is mismatched")
    subject_type = _require_extension_or_member(
        trail["subject_type"], _SUBJECT_TYPES, f"{label} subject_type"
    )
    subject_ref = _require_bounded_text(trail["subject_ref"], f"{label} subject_ref")
    if (subject_type, subject_ref) not in subject_keys:
        raise ValueError(f"{label} subject is absent from topology")
    if subject_type == "candidate" and subject_ref != candidate_ref:
        raise ValueError(f"{label} candidate subject is mismatched")
    _require_binary64(
        trail["strength"], f"{label} strength", minimum=0.0, maximum=1.0e12
    )
    _require_extension_or_member(trail["kind"], _PHEROMONE_KINDS, f"{label} kind")
    for field in (
        "source_ref",
        "evidence_ref",
        "provenance_ref",
        "trace_event_ref",
    ):
        _require_bounded_text(trail[field], f"{label} {field}")
    for field in ("route_ref", "tool_ref", "source_role"):
        _require_bounded_text(trail[field], f"{label} {field}", allow_empty=True)


def _freeze_trail_lineage(trail: dict[str, object], *, label: str) -> None:
    deposited = _require_count(trail["deposited_at_step"], f"{label} deposited_at_step")
    updated = _require_count(trail["updated_at_step"], f"{label} updated_at_step")
    if updated < deposited:
        raise ValueError(f"{label} updated step precedes deposited step")
    if trail["ttl_steps"] is not None:
        _require_count(trail["ttl_steps"], f"{label} ttl_steps", minimum=1)
    lineage = _require_sequence(
        trail["lineage_event_refs"],
        f"{label} lineage_event_refs",
        maximum=MAX_HYBRID_REPLAY_LINEAGE_EVENTS_V2,
        minimum=1,
    )
    lineage_refs = tuple(
        _require_bounded_text(item, f"{label} lineage_event_ref") for item in lineage
    )
    if (
        len(lineage_refs) != len(set(lineage_refs))
        or lineage_refs[-1] != trail["trace_event_ref"]
    ):
        raise ValueError(f"{label} lineage must be unique and end at trace_event_ref")
    trail["lineage_event_refs"] = lineage_refs
    hop = _require_count(trail["diffusion_hop"], f"{label} diffusion_hop")
    root_event = _require_bounded_text(
        trail["diffusion_root_trace_event_ref"],
        f"{label} diffusion_root_trace_event_ref",
        allow_empty=True,
    )
    parent_event = _require_bounded_text(
        trail["diffusion_parent_trace_event_ref"],
        f"{label} diffusion_parent_trace_event_ref",
        allow_empty=True,
    )
    if (hop == 0 and (root_event or parent_event)) or (
        hop > 0 and not (root_event and parent_event)
    ):
        raise ValueError(f"{label} diffusion lineage is inconsistent")


def _freeze_trail(
    value: object,
    *,
    label: str,
    target_ref: str,
    candidates: frozenset[str],
    subject_keys: frozenset[tuple[str, str]],
) -> _FrozenJsonObject:
    trail = _require_exact_mapping(value, _TRAIL_FIELDS, label)
    _validate_trail_bindings(
        trail,
        label=label,
        target_ref=target_ref,
        candidates=candidates,
        subject_keys=subject_keys,
    )
    _freeze_trail_lineage(trail, label=label)
    return _frozen_object(trail, label)


@dataclass(frozen=True, slots=True)
class _TopologyIndexV2:
    subject_keys: frozenset[tuple[str, str]]
    subjects_by_key: Mapping[tuple[str, str], Mapping[str, object]]
    edges_by_key: Mapping[tuple[str, str, str, str], Mapping[str, object]]


def _build_topology_index_v2(topology: Mapping[str, object]) -> _TopologyIndexV2:
    """Index a validated topology once for all trails and replay receipts."""

    subjects_by_key = {
        (cast(str, item["subject_type"]), cast(str, item["subject_ref"])): item
        for item in cast(tuple[Mapping[str, object], ...], topology["subjects"])
    }
    edges_by_key = {
        (
            cast(str, item["source_subject_type"]),
            cast(str, item["source_subject_ref"]),
            cast(str, item["target_subject_type"]),
            cast(str, item["target_subject_ref"]),
        ): item
        for item in cast(tuple[Mapping[str, object], ...], topology["edges"])
    }
    return _TopologyIndexV2(
        subject_keys=frozenset(subjects_by_key),
        subjects_by_key=subjects_by_key,
        edges_by_key=edges_by_key,
    )


def _trail_order_key(trail: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(
        cast(str, trail[field])
        for field in (
            "target_ref",
            "candidate_ref",
            "subject_type",
            "subject_ref",
            "kind",
            "source_ref",
            "trace_event_ref",
        )
    )


def _freeze_active_trails(
    value: object,
    *,
    target_ref: str,
    candidates: frozenset[str],
    topology_index: _TopologyIndexV2,
) -> tuple[_FrozenJsonObject, ...]:
    items = _require_sequence(
        value,
        "hybrid replay active trails",
        maximum=MAX_HYBRID_REPLAY_TRAILS_V2,
    )
    trails = tuple(
        _freeze_trail(
            item,
            label=f"hybrid replay active trail/{index}",
            target_ref=target_ref,
            candidates=candidates,
            subject_keys=topology_index.subject_keys,
        )
        for index, item in enumerate(items)
    )
    order = [_trail_order_key(item) for item in trails]
    event_refs = [cast(str, item["trace_event_ref"]) for item in trails]
    if order != sorted(order) or len(event_refs) != len(set(event_refs)):
        raise ValueError("hybrid replay active trails must be unique canonical order")
    return trails


def _freeze_adjustment_values(
    value: object, label: str
) -> tuple[_FrozenJsonObject, ...]:
    items = _require_sequence(value, label, maximum=len(_ADJUSTMENT_FIELDS))
    fields = frozenset({"field_ref", "value_kind", "value"})
    result: list[_FrozenJsonObject] = []
    refs: list[str] = []
    for index, item in enumerate(items):
        entry = _require_exact_mapping(item, fields, f"{label}/{index}")
        field_ref = _require_bounded_text(entry["field_ref"], f"{label} field_ref")
        if field_ref not in _ADJUSTMENT_FIELDS:
            raise ValueError(f"{label} field_ref is unsupported")
        if entry["value_kind"] == "binary64":
            _require_binary64(
                entry["value"], f"{label} value", minimum=0.0, maximum=1.0e12
            )
            if field_ref == "pheromone_response_model":
                raise ValueError(f"{label} response model must use text")
        elif entry["value_kind"] == "text":
            if (
                field_ref != "pheromone_response_model"
                or entry["value"] not in _RESPONSE_MODELS
            ):
                raise ValueError(f"{label} text adjustment is unsupported")
        else:
            raise ValueError(f"{label} value_kind is unsupported")
        refs.append(field_ref)
        result.append(_frozen_object(entry, f"{label}/{index}"))
    if refs != sorted(refs) or len(refs) != len(set(refs)):
        raise ValueError(f"{label} must be unique canonical order")
    return tuple(result)


def _freeze_deposit_receipt_payload(
    value: object,
    *,
    event_id: str,
    target_ref: str,
    candidates: frozenset[str],
    topology_index: _TopologyIndexV2,
) -> _FrozenJsonObject:
    trail = _freeze_trail(
        value,
        label="hybrid replay deposit receipt payload",
        target_ref=target_ref,
        candidates=candidates,
        subject_keys=topology_index.subject_keys,
    )
    if trail["trace_event_ref"] != event_id:
        raise ValueError("hybrid replay deposit receipt event id is mismatched")
    return trail


def _freeze_feedback_receipt_payload(
    value: object,
    *,
    event_id: str,
    target_ref: str,
    candidates: frozenset[str],
    topology_index: _TopologyIndexV2,
) -> _FrozenJsonObject:
    fields = frozenset(
        {
            "source_ref",
            "subject_type",
            "subject_ref",
            "candidate_ref",
            "target_ref",
            "outcome",
            "reward",
            "strength_delta",
            "evidence_ref",
            "provenance_ref",
            "trace_event_ref",
            "step",
        }
    )
    payload = _require_exact_mapping(
        value, fields, "hybrid replay feedback receipt payload"
    )
    for field in ("source_ref", "evidence_ref", "provenance_ref", "trace_event_ref"):
        _require_bounded_text(payload[field], f"hybrid replay feedback {field}")
    subject_key = (
        _require_extension_or_member(
            payload["subject_type"],
            _SUBJECT_TYPES,
            "hybrid replay feedback subject_type",
        ),
        _require_bounded_text(
            payload["subject_ref"], "hybrid replay feedback subject_ref"
        ),
    )
    if subject_key not in topology_index.subject_keys:
        raise ValueError("hybrid replay feedback subject is absent from topology")
    candidate_ref = _require_bounded_text(
        payload["candidate_ref"], "hybrid replay feedback candidate_ref"
    )
    if candidate_ref not in candidates or payload["target_ref"] != target_ref:
        raise ValueError("hybrid replay feedback candidate or target is mismatched")
    if subject_key[0] == "candidate" and subject_key[1] != candidate_ref:
        raise ValueError("hybrid replay feedback candidate subject is mismatched")
    if payload["outcome"] not in _FEEDBACK_OUTCOMES:
        raise ValueError("hybrid replay feedback outcome is unsupported")
    _require_binary64(
        payload["reward"],
        "hybrid replay feedback reward",
        minimum=-1.0e12,
        maximum=1.0e12,
    )
    _require_binary64(
        payload["strength_delta"],
        "hybrid replay feedback strength_delta",
        minimum=0.0,
        maximum=1.0e12,
    )
    _require_count(payload["step"], "hybrid replay feedback step")
    if payload["trace_event_ref"] != event_id:
        raise ValueError("hybrid replay feedback receipt event id is mismatched")
    return _frozen_object(payload, "feedback_receipt_payload")


def _freeze_adjustment_receipt_payload(
    value: object,
    *,
    event_id: str,
) -> _FrozenJsonObject:
    fields = frozenset(
        {"layer_ref", "source_ref", "adjustments", "provenance_ref", "trace_event_ref"}
    )
    payload = _require_exact_mapping(
        value, fields, "hybrid replay adjustment receipt payload"
    )
    if payload["layer_ref"] not in _LAYER_REFS - {"reactive"}:
        raise ValueError("hybrid replay adjustment layer is unsupported")
    for field in ("source_ref", "provenance_ref", "trace_event_ref"):
        _require_bounded_text(payload[field], f"hybrid replay adjustment {field}")
    payload["adjustments"] = _freeze_adjustment_values(
        payload["adjustments"], "hybrid replay receipt adjustments"
    )
    if not payload["adjustments"]:
        raise ValueError("hybrid replay adjustment receipt must contain an adjustment")
    if payload["trace_event_ref"] != event_id:
        raise ValueError("hybrid replay adjustment receipt event id is mismatched")
    return _frozen_object(payload, "adjustment_receipt_payload")


def _strict_json_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, item in pairs:
        if key in result:
            raise ValueError(
                "hybrid replay diffusion canonical payload contains duplicate keys"
            )
        result[key] = item
    return result


def _reject_nonfinite_json_constant(value: str) -> object:
    raise ValueError(
        "hybrid replay diffusion canonical payload contains a non-finite number: "
        f"{value}"
    )


def _require_causal_binary64(
    value: object,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> str:
    encoded = encode_binary64_v1(value, label)
    number = cast(float, value)
    if minimum is not None and number < minimum:
        raise ValueError(f"{label} is below its declared bound")
    if maximum is not None and number > maximum:
        raise ValueError(f"{label} exceeds its declared bound")
    return encoded


def _validate_diffusion_source_trail(
    value: object,
) -> dict[str, object]:
    trail = _require_exact_mapping(
        value,
        _DIFFUSION_SOURCE_TRAIL_FIELDS,
        "hybrid replay diffusion canonical source trail",
    )
    for field in (
        "candidate_id",
        "subject_id",
        "target",
        "route_id",
        "tool_id",
        "source_id",
        "source_role",
        "evidence_id",
        "provenance",
        "trace_event_id",
        "diffusion_root_trace_event_id",
        "diffusion_parent_trace_event_id",
    ):
        _require_bounded_text(
            trail[field],
            f"hybrid replay diffusion canonical source trail {field}",
            allow_empty=True,
        )
    _require_extension_or_member(
        trail["subject_type"],
        _SUBJECT_TYPES,
        "hybrid replay diffusion canonical source trail subject_type",
    )
    _require_extension_or_member(
        trail["kind"],
        _PHEROMONE_KINDS,
        "hybrid replay diffusion canonical source trail kind",
    )
    _require_causal_binary64(
        trail["strength"],
        "hybrid replay diffusion canonical source trail strength",
        minimum=0.0,
        maximum=1.0e12,
    )
    for field in ("deposited_at_step", "updated_at_step", "diffusion_hop"):
        _require_count(
            trail[field],
            f"hybrid replay diffusion canonical source trail {field}",
        )
    ttl_steps = trail["ttl_steps"]
    if ttl_steps is not None:
        _require_count(
            ttl_steps,
            "hybrid replay diffusion canonical source trail ttl_steps",
        )
    lineage = _require_sequence(
        trail["lineage_event_ids"],
        "hybrid replay diffusion canonical source trail lineage_event_ids",
        maximum=MAX_HYBRID_REPLAY_LINEAGE_EVENTS_V2,
    )
    normalized_lineage = [
        _require_bounded_text(
            item,
            "hybrid replay diffusion canonical source trail lineage_event_id",
        )
        for item in lineage
    ]
    if len(normalized_lineage) != len(set(normalized_lineage)):
        raise ValueError(
            "hybrid replay diffusion canonical source trail lineage is duplicated"
        )
    return trail


def hybrid_replay_diffusion_source_trail_root_v2(
    source_trail: Mapping[str, object],
) -> str:
    """Bind the exact v1 trail projection retained by a diffusion receipt."""

    trail = _validate_diffusion_source_trail(source_trail)
    return _compute_root("hybrid-replay-diffusion-source-trail", trail)


def _source_trail_subject_key(trail: Mapping[str, object]) -> tuple[str, str]:
    subject_type = cast(str, trail["subject_type"])
    subject_ref = cast(str, trail["subject_id"])
    if subject_ref:
        return subject_type, subject_ref
    for fallback_type, field in (
        ("candidate", "candidate_id"),
        ("route", "route_id"),
        ("tool", "tool_id"),
    ):
        fallback_ref = cast(str, trail[field])
        if fallback_ref:
            return fallback_type, fallback_ref
    return subject_type, ""


def _load_diffusion_causal_payload(value: object) -> dict[str, object]:
    if type(value) is not str:
        raise TypeError(
            "hybrid replay diffusion canonical_causal_payload must be exact text"
        )
    canonical = value
    if not canonical or len(canonical) > MAX_HYBRID_REPLAY_CAUSAL_PAYLOAD_BYTES_V2:
        raise ValueError(
            "hybrid replay diffusion canonical_causal_payload is outside its byte bound"
        )
    try:
        canonical_size = len(canonical.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError(
            "hybrid replay diffusion canonical_causal_payload must be valid UTF-8"
        ) from exc
    if canonical_size > MAX_HYBRID_REPLAY_CAUSAL_PAYLOAD_BYTES_V2:
        raise ValueError(
            "hybrid replay diffusion canonical_causal_payload is outside its byte bound"
        )
    try:
        decoded = json.loads(
            canonical,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_nonfinite_json_constant,
        )
    except (TypeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(
            "hybrid replay diffusion canonical_causal_payload is invalid JSON"
        ) from exc
    _preflight_portable_resources_v2(decoded)
    envelope = _require_exact_mapping(
        decoded,
        frozenset({"payload", "version"}),
        "hybrid replay diffusion canonical payload envelope",
    )
    if envelope["version"] != _PHEROMONE_CLIP_PAYLOAD_VERSION_V1:
        raise ValueError(
            "hybrid replay diffusion canonical payload version is unsupported"
        )
    causal = _require_exact_mapping(
        envelope["payload"],
        frozenset({"lifecycle", "input", "effective"}),
        "hybrid replay diffusion canonical causal payload",
    )
    if canonical_pheromone_clip_payload(causal) != canonical:
        raise ValueError(
            "hybrid replay diffusion canonical_causal_payload is not canonical"
        )
    return causal


def _freeze_diffusion_causal_input(
    value: object,
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    input_payload = _require_exact_mapping(
        value,
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
        "hybrid replay diffusion canonical input",
    )
    source_trail = _validate_diffusion_source_trail(input_payload["source_trail"])
    target_subject = _require_exact_mapping(
        input_payload["target_subject"],
        frozenset({"subject_type", "subject_id", "candidate_id", "target"}),
        "hybrid replay diffusion canonical target subject",
    )
    edge = _require_exact_mapping(
        input_payload["edge"],
        frozenset(
            {
                "source_subject_type",
                "source_subject_id",
                "target_subject_type",
                "target_subject_id",
                "attenuation",
            }
        ),
        "hybrid replay diffusion canonical edge",
    )
    _require_extension_or_member(
        target_subject["subject_type"],
        _SUBJECT_TYPES,
        "hybrid replay diffusion canonical target subject type",
    )
    _require_bounded_text(
        target_subject["subject_id"],
        "hybrid replay diffusion canonical target subject id",
    )
    for field in ("candidate_id", "target"):
        _require_bounded_text(
            target_subject[field],
            f"hybrid replay diffusion canonical target subject {field}",
            allow_empty=True,
        )
    for field in ("source_subject_type", "target_subject_type"):
        _require_extension_or_member(
            edge[field],
            _SUBJECT_TYPES,
            f"hybrid replay diffusion canonical edge {field}",
        )
    for field in ("source_subject_id", "target_subject_id"):
        _require_bounded_text(
            edge[field], f"hybrid replay diffusion canonical edge {field}"
        )
    _require_causal_binary64(
        edge["attenuation"],
        "hybrid replay diffusion canonical edge attenuation",
        minimum=0.0,
        maximum=1.0,
    )
    _require_causal_binary64(
        input_payload["policy_attenuation"],
        "hybrid replay diffusion canonical policy attenuation",
        minimum=0.0,
        maximum=1.0,
    )
    _require_count(
        input_payload["hop"], "hybrid replay diffusion canonical hop", minimum=1
    )
    for field in ("parent_trace_event_id", "derived_trace_event_id"):
        _require_bounded_text(
            input_payload[field],
            f"hybrid replay diffusion canonical {field}",
        )
    return input_payload, source_trail, target_subject, edge


def _freeze_diffusion_causal_effective(value: object) -> dict[str, object]:
    effective = _require_exact_mapping(
        value,
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
        "hybrid replay diffusion canonical effective payload",
    )
    for field in (
        "target",
        "candidate_id",
        "subject_id",
        "source_id",
        "root_trace_event_id",
    ):
        _require_bounded_text(
            effective[field], f"hybrid replay diffusion canonical effective {field}"
        )
    _require_extension_or_member(
        effective["subject_type"],
        _SUBJECT_TYPES,
        "hybrid replay diffusion canonical effective subject_type",
    )
    _require_extension_or_member(
        effective["source_kind"],
        _PHEROMONE_KINDS,
        "hybrid replay diffusion canonical effective source_kind",
    )
    _require_causal_binary64(
        effective["source_strength"],
        "hybrid replay diffusion canonical effective source_strength",
        minimum=0.0,
        maximum=1.0e12,
    )
    return effective


def _validate_diffusion_causal_lineage(
    *,
    input_payload: Mapping[str, object],
    effective: Mapping[str, object],
    source_trail: Mapping[str, object],
    target_subject: Mapping[str, object],
    edge: Mapping[str, object],
) -> None:
    if (
        edge["target_subject_type"],
        edge["target_subject_id"],
    ) != (target_subject["subject_type"], target_subject["subject_id"]):
        raise ValueError(
            "hybrid replay diffusion canonical target and edge are mismatched"
        )
    if _source_trail_subject_key(source_trail) != (
        edge["source_subject_type"],
        edge["source_subject_id"],
    ):
        raise ValueError(
            "hybrid replay diffusion canonical source trail and edge are mismatched"
        )
    expected_source_ref = source_trail["source_id"] or source_trail["provenance"]
    expected_root_event = (
        source_trail["diffusion_root_trace_event_id"] or source_trail["trace_event_id"]
    )
    if (
        effective["subject_type"],
        effective["subject_id"],
        effective["source_id"],
        effective["source_kind"],
        effective["root_trace_event_id"],
    ) != (
        target_subject["subject_type"],
        target_subject["subject_id"],
        expected_source_ref,
        source_trail["kind"],
        expected_root_event,
    ):
        raise ValueError(
            "hybrid replay diffusion canonical effective lineage is mismatched"
        )
    if input_payload["parent_trace_event_id"] != source_trail["trace_event_id"]:
        raise ValueError("hybrid replay diffusion canonical parent event is mismatched")
    if encode_binary64_v1(
        effective["source_strength"],
        "hybrid replay diffusion canonical effective source_strength",
    ) != encode_binary64_v1(
        source_trail["strength"],
        "hybrid replay diffusion canonical source trail strength",
    ):
        raise ValueError(
            "hybrid replay diffusion canonical source strength is mismatched"
        )
    if target_subject["candidate_id"] not in ("", effective["candidate_id"]):
        raise ValueError(
            "hybrid replay diffusion canonical target candidate is mismatched"
        )
    if target_subject["target"] not in ("", effective["target"]):
        raise ValueError("hybrid replay diffusion canonical target is mismatched")


def _validate_diffusion_causal_payload(
    causal: Mapping[str, object],
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    if causal["lifecycle"] != "diffusion":
        raise ValueError(
            "hybrid replay diffusion canonical payload lifecycle is mismatched"
        )
    input_payload, source_trail, target_subject, edge = _freeze_diffusion_causal_input(
        causal["input"]
    )
    effective = _freeze_diffusion_causal_effective(causal["effective"])
    _validate_diffusion_causal_lineage(
        input_payload=input_payload,
        effective=effective,
        source_trail=source_trail,
        target_subject=target_subject,
        edge=edge,
    )
    return input_payload, effective, source_trail, edge


def _declared_topology_edge(
    topology_index: _TopologyIndexV2,
    *,
    source_key: tuple[str, str],
    target_key: tuple[str, str],
) -> Mapping[str, object] | None:
    return topology_index.edges_by_key.get((*source_key, *target_key))


def _declared_topology_subject(
    topology_index: _TopologyIndexV2,
    subject_key: tuple[str, str],
) -> Mapping[str, object] | None:
    return topology_index.subjects_by_key.get(subject_key)


def _validate_diffusion_receipt_summary(
    payload: Mapping[str, object],
    *,
    event_id: str,
    target_ref: str,
    candidates: frozenset[str],
    topology_index: _TopologyIndexV2,
    source_trail: Mapping[str, object],
) -> tuple[tuple[str, str], str]:
    _require_root(
        payload["source_trail_root"], "hybrid replay diffusion source_trail_root"
    )
    expected_source_trail_root = hybrid_replay_diffusion_source_trail_root_v2(
        source_trail
    )
    if payload["source_trail_root"] != expected_source_trail_root:
        raise ValueError("hybrid replay diffusion source_trail_root is mismatched")
    subject_key = (
        _require_extension_or_member(
            payload["target_subject_type"],
            _SUBJECT_TYPES,
            "hybrid replay diffusion target subject type",
        ),
        _require_bounded_text(
            payload["target_subject_ref"],
            "hybrid replay diffusion target subject ref",
        ),
    )
    if subject_key not in topology_index.subject_keys:
        raise ValueError(
            "hybrid replay diffusion target subject is absent from topology"
        )
    candidate_ref = _require_bounded_text(
        payload["candidate_ref"], "hybrid replay diffusion candidate_ref"
    )
    if candidate_ref not in candidates or payload["target_ref"] != target_ref:
        raise ValueError("hybrid replay diffusion candidate or target is mismatched")
    source_candidate = cast(str, source_trail["candidate_id"])
    if source_candidate not in candidates or source_trail["target"] != target_ref:
        raise ValueError(
            "hybrid replay diffusion canonical source candidate or target is mismatched"
        )
    for field in ("edge_attenuation", "policy_attenuation"):
        _require_binary64(
            payload[field],
            f"hybrid replay diffusion {field}",
            minimum=0.0,
            maximum=1.0,
        )
    _require_binary64(
        payload["source_strength"],
        "hybrid replay diffusion source_strength",
        minimum=0.0,
        maximum=1.0e12,
    )
    _require_count(payload["hop"], "hybrid replay diffusion hop", minimum=1)
    for field in (
        "parent_event_id",
        "derived_event_id",
        "source_ref",
        "root_event_id",
    ):
        _require_bounded_text(payload[field], f"hybrid replay diffusion {field}")
    _require_extension_or_member(
        payload["source_kind"],
        _PHEROMONE_KINDS,
        "hybrid replay diffusion source_kind",
    )
    if payload["derived_event_id"] != event_id:
        raise ValueError("hybrid replay diffusion receipt event id is mismatched")
    return subject_key, candidate_ref


def _validate_diffusion_receipt_binding(
    payload: Mapping[str, object],
    *,
    input_payload: Mapping[str, object],
    effective: Mapping[str, object],
    causal_edge: Mapping[str, object],
    topology_index: _TopologyIndexV2,
    policy: Mapping[str, object],
    subject_key: tuple[str, str],
    candidate_ref: str,
    target_ref: str,
) -> None:
    target_subject = cast(Mapping[str, object], input_payload["target_subject"])
    causal_source_key = (
        cast(str, causal_edge["source_subject_type"]),
        cast(str, causal_edge["source_subject_id"]),
    )
    causal_target_key = (
        cast(str, causal_edge["target_subject_type"]),
        cast(str, causal_edge["target_subject_id"]),
    )
    if causal_target_key != subject_key:
        raise ValueError(
            "hybrid replay diffusion canonical target subject is mismatched"
        )
    declared_subject = _declared_topology_subject(topology_index, subject_key)
    if declared_subject is None or (
        declared_subject["candidate_ref"],
        declared_subject["target_ref"],
    ) != (candidate_ref, target_ref):
        raise ValueError("hybrid replay diffusion target subject binding is mismatched")
    declared_edge = _declared_topology_edge(
        topology_index,
        source_key=causal_source_key,
        target_key=causal_target_key,
    )
    if declared_edge is None:
        raise ValueError("hybrid replay diffusion edge is absent from topology")
    causal_edge_attenuation = encode_binary64_v1(
        causal_edge["attenuation"],
        "hybrid replay diffusion canonical edge attenuation",
    )
    causal_policy_attenuation = encode_binary64_v1(
        input_payload["policy_attenuation"],
        "hybrid replay diffusion canonical policy attenuation",
    )
    causal_source_strength = encode_binary64_v1(
        effective["source_strength"],
        "hybrid replay diffusion canonical source strength",
    )
    if (
        payload["target_subject_type"],
        payload["target_subject_ref"],
        payload["candidate_ref"],
        payload["target_ref"],
        payload["edge_attenuation"],
        payload["policy_attenuation"],
        payload["hop"],
        payload["parent_event_id"],
        payload["derived_event_id"],
        payload["source_ref"],
        payload["source_kind"],
        payload["source_strength"],
        payload["root_event_id"],
    ) != (
        target_subject["subject_type"],
        target_subject["subject_id"],
        effective["candidate_id"],
        effective["target"],
        causal_edge_attenuation,
        causal_policy_attenuation,
        input_payload["hop"],
        input_payload["parent_trace_event_id"],
        input_payload["derived_trace_event_id"],
        effective["source_id"],
        effective["source_kind"],
        causal_source_strength,
        effective["root_trace_event_id"],
    ):
        raise ValueError(
            "hybrid replay diffusion receipt summary and canonical payload are mismatched"
        )
    if declared_edge["attenuation"] != causal_edge_attenuation:
        raise ValueError(
            "hybrid replay diffusion canonical edge attenuation is undeclared"
        )
    if policy["pheromone_diffusion_attenuation"] != causal_policy_attenuation:
        raise ValueError(
            "hybrid replay diffusion canonical policy attenuation is undeclared"
        )


def _freeze_diffusion_receipt_payload(
    value: object,
    *,
    event_id: str,
    target_ref: str,
    candidates: frozenset[str],
    topology_index: _TopologyIndexV2,
    policy: Mapping[str, object],
) -> _FrozenJsonObject:
    fields = frozenset(
        {
            "replay_version",
            "canonical_causal_payload",
            "source_trail_root",
            "target_subject_type",
            "target_subject_ref",
            "candidate_ref",
            "target_ref",
            "edge_attenuation",
            "policy_attenuation",
            "hop",
            "parent_event_id",
            "derived_event_id",
            "source_ref",
            "source_kind",
            "source_strength",
            "root_event_id",
        }
    )
    payload = _require_exact_mapping(
        value, fields, "hybrid replay diffusion receipt payload"
    )
    if payload["replay_version"] != HYBRID_REPLAY_DIFFUSION_REPLAY_VERSION_V2:
        raise ValueError("hybrid replay diffusion replay_version is unsupported")
    causal = _load_diffusion_causal_payload(payload["canonical_causal_payload"])
    input_payload, effective, source_trail, causal_edge = (
        _validate_diffusion_causal_payload(causal)
    )
    subject_key, candidate_ref = _validate_diffusion_receipt_summary(
        payload,
        event_id=event_id,
        target_ref=target_ref,
        candidates=candidates,
        topology_index=topology_index,
        source_trail=source_trail,
    )
    _validate_diffusion_receipt_binding(
        payload,
        input_payload=input_payload,
        effective=effective,
        causal_edge=causal_edge,
        topology_index=topology_index,
        policy=policy,
        subject_key=subject_key,
        candidate_ref=candidate_ref,
        target_ref=target_ref,
    )
    return _FrozenJsonObject(tuple(sorted(payload.items())))


def _preflight_causal_payload_bytes_v2(items: Sequence[object]) -> int:
    """Reject multiplicative causal payload cost before JSON parsing starts."""

    total = 0
    for item in items:
        if not isinstance(item, Mapping) or item.get("kind") != "diffusion":
            continue
        payload = item.get("payload")
        if not isinstance(payload, Mapping):
            continue
        canonical = payload.get("canonical_causal_payload")
        if type(canonical) is not str:
            continue
        canonical_text = canonical
        if not canonical_text or len(canonical_text) > (
            MAX_HYBRID_REPLAY_CAUSAL_PAYLOAD_BYTES_V2
        ):
            raise ValueError(
                "hybrid replay diffusion canonical_causal_payload is outside its byte bound"
            )
        if total + len(canonical_text) > (
            MAX_HYBRID_REPLAY_TOTAL_CAUSAL_PAYLOAD_BYTES_V2
        ):
            raise ValueError(
                "Hybrid replay aggregate causal payload exceeds its byte bound"
            )
        try:
            size = len(canonical_text.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise ValueError(
                "hybrid replay diffusion canonical_causal_payload must be valid UTF-8"
            ) from exc
        if not size or size > MAX_HYBRID_REPLAY_CAUSAL_PAYLOAD_BYTES_V2:
            raise ValueError(
                "hybrid replay diffusion canonical_causal_payload is outside its byte bound"
            )
        total += size
        if total > MAX_HYBRID_REPLAY_TOTAL_CAUSAL_PAYLOAD_BYTES_V2:
            raise ValueError(
                "Hybrid replay aggregate causal payload exceeds its byte bound"
            )
    return total


def _freeze_receipts(
    value: object,
    *,
    target_ref: str,
    candidates: frozenset[str],
    topology_index: _TopologyIndexV2,
    policy: Mapping[str, object],
) -> tuple[_FrozenJsonObject, ...]:
    items = _require_sequence(
        value,
        "hybrid replay receipts",
        maximum=MAX_HYBRID_REPLAY_RECEIPTS_V2,
    )
    _preflight_causal_payload_bytes_v2(items)
    result: list[_FrozenJsonObject] = []
    order: list[tuple[str, str]] = []
    event_ids: list[str] = []
    fields = frozenset({"kind", "event_id", "payload", "payload_root"})
    for index, item in enumerate(items):
        receipt = _require_exact_mapping(item, fields, f"hybrid replay receipt/{index}")
        kind = _require_bounded_text(receipt["kind"], "hybrid replay receipt kind")
        if kind not in _REPLAY_RECEIPT_KINDS:
            raise ValueError("hybrid replay receipt kind is unsupported")
        event_id = _require_bounded_text(
            receipt["event_id"], "hybrid replay receipt event_id"
        )
        if kind == "deposit":
            payload = _freeze_deposit_receipt_payload(
                receipt["payload"],
                event_id=event_id,
                target_ref=target_ref,
                candidates=candidates,
                topology_index=topology_index,
            )
        elif kind == "diffusion":
            payload = _freeze_diffusion_receipt_payload(
                receipt["payload"],
                event_id=event_id,
                target_ref=target_ref,
                candidates=candidates,
                topology_index=topology_index,
                policy=policy,
            )
        elif kind == "feedback":
            payload = _freeze_feedback_receipt_payload(
                receipt["payload"],
                event_id=event_id,
                target_ref=target_ref,
                candidates=candidates,
                topology_index=topology_index,
            )
        else:
            payload = _freeze_adjustment_receipt_payload(
                receipt["payload"], event_id=event_id
            )
        expected_payload_root = _compute_root(
            f"hybrid-replay-{kind}-receipt-payload", _thaw_json(payload)
        )
        supplied_payload_root = receipt["payload_root"]
        if type(supplied_payload_root) is not str:
            raise TypeError("hybrid replay receipt payload_root must be text")
        if supplied_payload_root:
            _require_root(supplied_payload_root, "hybrid replay receipt payload_root")
        if supplied_payload_root not in ("", expected_payload_root):
            raise ValueError("hybrid replay receipt payload_root is mismatched")
        receipt["payload"] = payload
        receipt["payload_root"] = expected_payload_root
        result.append(_frozen_object(receipt, f"receipt/{index}"))
        order.append((kind, event_id))
        event_ids.append(event_id)
    if order != sorted(order) or len(event_ids) != len(set(event_ids)):
        raise ValueError(
            "hybrid replay receipt ids must be mutually exclusive canonical order"
        )
    return tuple(result)


def _freeze_budget(
    value: object, effective_policy: Mapping[str, object]
) -> _FrozenJsonObject:
    budget = _require_exact_mapping(
        value,
        frozenset({"round_cap", "per_source_cap", "round_used", "source_used"}),
        "hybrid replay last budget",
    )
    round_cap = decode_binary64_v1(
        budget["round_cap"], "hybrid replay budget round_cap"
    )
    source_cap = decode_binary64_v1(
        budget["per_source_cap"], "hybrid replay budget per_source_cap"
    )
    round_used = decode_binary64_v1(
        budget["round_used"], "hybrid replay budget round_used"
    )
    if (
        budget["round_cap"] != effective_policy["pheromone_per_round_deposit_cap"]
        or budget["per_source_cap"] != effective_policy["pheromone_per_source_cap"]
    ):
        raise ValueError("hybrid replay budget caps do not match effective policy")
    if not (round_cap > 0.0 and source_cap > 0.0 and 0.0 <= round_used <= round_cap):
        raise ValueError("hybrid replay budget values are outside declared bounds")
    items = _require_sequence(
        budget["source_used"],
        "hybrid replay budget source usage",
        maximum=MAX_HYBRID_REPLAY_SOURCES_V2,
    )
    sources: list[_FrozenJsonObject] = []
    source_refs: list[str] = []
    total = 0.0
    for index, item in enumerate(items):
        entry = _require_exact_mapping(
            item,
            frozenset({"source_ref", "used"}),
            f"hybrid replay source budget/{index}",
        )
        source_ref = _require_bounded_text(
            entry["source_ref"], "hybrid replay source budget source_ref"
        )
        used = decode_binary64_v1(entry["used"], "hybrid replay source budget used")
        if not 0.0 <= used <= source_cap:
            raise ValueError("hybrid replay source budget usage exceeds its cap")
        total += used
        source_refs.append(source_ref)
        sources.append(_frozen_object(entry, f"source_budget/{index}"))
    if source_refs != sorted(source_refs) or len(source_refs) != len(set(source_refs)):
        raise ValueError("hybrid replay source budgets must be unique canonical order")
    if abs(total - round_used) > 1.0e-9:
        raise ValueError("hybrid replay budget usage does not reconstruct")
    budget["source_used"] = tuple(sources)
    return _frozen_object(budget, "last_budget")


def _freeze_overlay(value: object) -> _FrozenJsonObject:
    overlay = _require_exact_mapping(
        value,
        frozenset({"values", "source_refs", "trace_roots"}),
        "hybrid replay policy overlay",
    )
    values = _freeze_adjustment_values(
        overlay["values"], "hybrid replay overlay values"
    )
    sources = _canonical_text_array(
        overlay["source_refs"],
        "hybrid replay overlay source_refs",
        maximum=MAX_HYBRID_REPLAY_SOURCES_V2,
        minimum=1 if values else 0,
    )
    traces = _canonical_text_array(
        overlay["trace_roots"],
        "hybrid replay overlay trace_roots",
        maximum=MAX_HYBRID_REPLAY_TRACE_ROOTS_V2,
        minimum=1 if values else 0,
        roots=True,
    )
    if not values and (sources or traces):
        raise ValueError("empty Hybrid replay overlay cannot carry source lineage")
    overlay["values"] = values
    overlay["source_refs"] = sources
    overlay["trace_roots"] = traces
    return _frozen_object(overlay, "overlay")


def _validate_overlay_against_policy(
    overlay: Mapping[str, object],
    policy: Mapping[str, object],
) -> None:
    declared = {
        cast(str, item["field_ref"]): item
        for item in cast(
            tuple[Mapping[str, object], ...], policy["policy_adjustment_bounds"]
        )
    }
    for item in cast(tuple[Mapping[str, object], ...], overlay["values"]):
        field_ref = cast(str, item["field_ref"])
        bound = declared.get(field_ref)
        if bound is None:
            raise ValueError("Hybrid replay overlay field is outside declared bounds")
        if item["value_kind"] == "text":
            allowed = cast(tuple[str, ...], bound["allowed_values"])
            if bound["bound_kind"] != "allowed_values" or item["value"] not in allowed:
                raise ValueError(
                    "Hybrid replay overlay text is outside declared bounds"
                )
            continue
        value = decode_binary64_v1(item["value"], "Hybrid replay overlay value")
        if bound["bound_kind"] != "binary64_range":
            raise ValueError("Hybrid replay overlay numeric bound kind is mismatched")
        minimum = decode_binary64_v1(
            bound["minimum"], "Hybrid replay overlay declared minimum"
        )
        maximum = decode_binary64_v1(
            bound["maximum"], "Hybrid replay overlay declared maximum"
        )
        if not minimum <= value <= maximum:
            raise ValueError("Hybrid replay overlay value is outside declared bounds")


def _apply_scalar_overlay(
    expected: dict[str, object], values: Mapping[str, object]
) -> None:
    scalar_mapping = {
        "pheromone_evaporation_rate": "pheromone_evaporation_rate",
        "pheromone_response_model": "pheromone_response_model",
        "pheromone_exploration_floor": "pheromone_exploration_floor",
        "pheromone_cautionary_override_threshold": "pheromone_cautionary_override_threshold",
        "layer_emergency_override_threshold": "layer_emergency_override_threshold",
        "pheromone_positive_weight": "pheromone_positive_weight",
        "pheromone_negative_weight": "pheromone_negative_weight",
        "pheromone_cautionary_weight": "pheromone_cautionary_weight",
        "pheromone_novelty_weight": "pheromone_novelty_weight",
    }
    for overlay_field, policy_field in scalar_mapping.items():
        if overlay_field in values:
            expected[policy_field] = values[overlay_field]


def _apply_profile_overlay(
    expected: dict[str, object], values: Mapping[str, object]
) -> None:
    kind_mapping = {
        "pheromone_positive_weight": "positive",
        "pheromone_negative_weight": "negative",
        "pheromone_cautionary_weight": "cautionary",
        "pheromone_alarm_weight": "alarm",
        "pheromone_novelty_weight": "novelty",
    }
    profiles = {
        cast(str, item["kind"]): item
        for item in cast(list[dict[str, object]], expected["pheromone_kind_profiles"])
    }
    if "pheromone_evaporation_rate" in values:
        for item in profiles.values():
            item["evaporation_rate"] = values["pheromone_evaporation_rate"]
    if "pheromone_response_model" in values:
        for item in profiles.values():
            item["response_model"] = values["pheromone_response_model"]
    for overlay_field, kind in kind_mapping.items():
        if overlay_field not in values:
            continue
        item = profiles.setdefault(
            kind,
            {
                "kind": kind,
                "weight": float(1.0).hex(),
                "evaporation_rate": None,
                "ttl_steps": None,
                "response_model": "linear",
                "priority": 0,
                "can_suppress_positive": False,
                "scored_subject_types": [],
            },
        )
        item["weight"] = values[overlay_field]
    expected["pheromone_kind_profiles"] = [profiles[key] for key in sorted(profiles)]


def _apply_layer_overlay(
    expected: dict[str, object], values: Mapping[str, object]
) -> None:
    layer_mapping = {
        "layer_learned_weight": "learned",
        "layer_evolutionary_weight": "evolutionary",
        "layer_metacognitive_weight": "metacognitive",
    }
    layer_weights = {
        cast(str, item["layer_ref"]): item
        for item in cast(list[dict[str, object]], expected["layer_default_weights"])
    }
    for overlay_field, layer_ref in layer_mapping.items():
        if overlay_field in values:
            layer_weights[layer_ref]["value"] = values[overlay_field]
    expected["layer_default_weights"] = [
        layer_weights[key] for key in sorted(layer_weights)
    ]


def _expected_effective_policy(
    policy: Mapping[str, object],
    overlay: Mapping[str, object],
) -> dict[str, object]:
    expected = cast(dict[str, object], _thaw_json(policy))
    entries = cast(list[dict[str, object]], _thaw_json(overlay["values"]))
    values = {cast(str, item["field_ref"]): item["value"] for item in entries}
    _apply_scalar_overlay(expected, values)
    _apply_profile_overlay(expected, values)
    _apply_layer_overlay(expected, values)
    return expected


def _validate_snapshot_identity(snapshot: HybridReplaySnapshotV2) -> None:
    _require_exact_version(
        snapshot.schema,
        HYBRID_REPLAY_SNAPSHOT_SCHEMA_V2,
        "Hybrid replay snapshot schema",
    )
    _require_exact_version(
        snapshot.state_schema,
        HYBRID_REPLAY_STATE_SCHEMA_V2,
        "Hybrid replay state schema",
    )
    _require_exact_version(
        snapshot.canonical_version,
        AUTHORITY_CANONICAL_VERSION_V2,
        "Hybrid replay canonical_version",
    )
    _require_exact_version(
        snapshot.numeric_wire_version,
        HYBRID_REPLAY_NUMERIC_WIRE_VERSION_V2,
        "Hybrid replay numeric wire version",
    )
    _require_root(snapshot.domain_root, "Hybrid replay domain_root")
    _require_root(snapshot.manifest_root, "Hybrid replay manifest_root")
    for field in (
        "scope_ref",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "advance_ref",
        "transition_id",
    ):
        _require_bounded_text(getattr(snapshot, field), f"Hybrid replay {field}")
    _require_count(snapshot.observed_epoch, "Hybrid replay observed_epoch")
    _require_count(snapshot.revision, "Hybrid replay revision", minimum=1)
    _require_count(snapshot.current_step, "Hybrid replay current_step")
    _require_count(snapshot.parent_revision, "Hybrid replay parent_revision")
    if snapshot.revision != snapshot.parent_revision + 1:
        raise ValueError(
            "Hybrid replay revision must advance exactly one parent revision"
        )
    _require_bounded_text(
        snapshot.parent_transition_id, "Hybrid replay parent_transition_id"
    )
    _require_root(snapshot.parent_snapshot_root, "Hybrid replay parent_snapshot_root")
    if snapshot.parent_revision == 0:
        if (
            snapshot.parent_transition_id != "genesis"
            or snapshot.parent_snapshot_root != HYBRID_REPLAY_GENESIS_SNAPSHOT_ROOT_V2
        ):
            raise ValueError("Hybrid replay genesis parent lineage is inconsistent")
    elif (
        snapshot.parent_transition_id == "genesis"
        or snapshot.parent_snapshot_root == HYBRID_REPLAY_GENESIS_SNAPSHOT_ROOT_V2
    ):
        raise ValueError("Hybrid replay non-genesis parent lineage is inconsistent")
    expected_stream = hybrid_replay_stream_ref_v2(
        snapshot.scope_ref,
        snapshot.protocol_ref,
        snapshot.run_ref,
        snapshot.target_ref,
    )
    if snapshot.stream_ref != expected_stream:
        raise ValueError("Hybrid replay stream_ref is mismatched")
    if snapshot.transition_id != hybrid_replay_transition_id_v2(
        snapshot.stream_ref, snapshot.advance_ref
    ):
        raise ValueError("Hybrid replay transition_id is mismatched")


@dataclass(frozen=True, slots=True)
class HybridReplaySnapshotV2:
    """One defensive portable Hybrid replay state projection.

    A valid instance proves only canonical integrity.  It is not replay
    authority until a verified StateStore reader proves committed inclusion,
    scope binding, position, and currentness.
    """

    domain_root: str
    scope_ref: str
    manifest_root: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    stream_ref: str
    advance_ref: str
    transition_id: str
    revision: int
    current_step: int
    parent_revision: int
    parent_transition_id: str
    parent_snapshot_root: str
    candidate_projection: Mapping[str, object]
    policy_projection: Mapping[str, object]
    topology_projection: Mapping[str, object]
    active_trails: Sequence[Mapping[str, object]]
    replay_receipts: Sequence[Mapping[str, object]]
    last_budget: Mapping[str, object]
    overlay: Mapping[str, object]
    effective_policy_projection: Mapping[str, object]
    source_step_root: str
    source_trace_roots: Sequence[str]
    candidate_projection_root: str = ""
    policy_projection_root: str = ""
    topology_projection_root: str = ""
    active_trails_root: str = ""
    replay_receipts_root: str = ""
    last_budget_root: str = ""
    overlay_root: str = ""
    effective_policy_root: str = ""
    source_trace_set_root: str = ""
    source_lineage_root: str = ""
    state_root: str = ""
    schema: str = HYBRID_REPLAY_SNAPSHOT_SCHEMA_V2
    state_schema: str = HYBRID_REPLAY_STATE_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    numeric_wire_version: str = HYBRID_REPLAY_NUMERIC_WIRE_VERSION_V2
    snapshot_root: str = ""

    _root_field: ClassVar[str] = "snapshot_root"

    def __post_init__(self) -> None:
        _preflight_portable_resources_v2(
            {
                "candidate_projection": self.candidate_projection,
                "policy_projection": self.policy_projection,
                "topology_projection": self.topology_projection,
                "active_trails": self.active_trails,
                "replay_receipts": self.replay_receipts,
                "last_budget": self.last_budget,
                "overlay": self.overlay,
                "effective_policy_projection": self.effective_policy_projection,
                "source_trace_roots": self.source_trace_roots,
            }
        )
        _validate_snapshot_identity(self)
        candidate, candidates, fallback = _freeze_candidate_projection(
            self.candidate_projection, self.target_ref
        )
        policy = _freeze_policy_projection(
            self.policy_projection,
            candidates=candidates,
            fallback_candidate_ref=fallback,
        )
        topology = _freeze_topology_projection(
            self.topology_projection,
            target_ref=self.target_ref,
            candidates=candidates,
        )
        topology_index = _build_topology_index_v2(topology)
        trails = _freeze_active_trails(
            self.active_trails,
            target_ref=self.target_ref,
            candidates=candidates,
            topology_index=topology_index,
        )
        receipts = _freeze_receipts(
            self.replay_receipts,
            target_ref=self.target_ref,
            candidates=candidates,
            topology_index=topology_index,
            policy=policy,
        )
        overlay = _freeze_overlay(self.overlay)
        _validate_overlay_against_policy(overlay, policy)
        effective = _freeze_policy_projection(
            self.effective_policy_projection,
            candidates=candidates,
            fallback_candidate_ref=fallback,
        )
        if cast(dict[str, object], _thaw_json(effective)) != _expected_effective_policy(
            policy, overlay
        ):
            raise ValueError(
                "Hybrid replay effective policy does not reconstruct from overlay"
            )
        budget = _freeze_budget(self.last_budget, effective)
        trace_roots = _canonical_text_array(
            self.source_trace_roots,
            "Hybrid replay source_trace_roots",
            maximum=MAX_HYBRID_REPLAY_TRACE_ROOTS_V2,
            minimum=1,
            roots=True,
        )
        _require_root(self.source_step_root, "Hybrid replay source_step_root")
        overlay_trace_roots = set(cast(tuple[str, ...], overlay["trace_roots"]))
        if not overlay_trace_roots.issubset(trace_roots):
            raise ValueError(
                "Hybrid replay overlay trace roots are absent from source lineage"
            )
        object.__setattr__(self, "candidate_projection", candidate)
        object.__setattr__(self, "policy_projection", policy)
        object.__setattr__(self, "topology_projection", topology)
        object.__setattr__(self, "active_trails", trails)
        object.__setattr__(self, "replay_receipts", receipts)
        object.__setattr__(self, "last_budget", budget)
        object.__setattr__(self, "overlay", overlay)
        object.__setattr__(self, "effective_policy_projection", effective)
        object.__setattr__(self, "source_trace_roots", trace_roots)
        derived = (
            (
                "candidate_projection_root",
                "hybrid-replay-candidate-projection",
                candidate,
            ),
            ("policy_projection_root", "hybrid-replay-policy-projection", policy),
            ("topology_projection_root", "hybrid-replay-topology-projection", topology),
            ("active_trails_root", "hybrid-replay-active-trails", trails),
            ("replay_receipts_root", "hybrid-replay-receipts", receipts),
            ("last_budget_root", "hybrid-replay-last-budget", budget),
            ("overlay_root", "hybrid-replay-overlay", overlay),
            ("effective_policy_root", "hybrid-replay-effective-policy", effective),
            ("source_trace_set_root", "hybrid-replay-source-trace-set", trace_roots),
        )
        for attribute, kind, body in derived:
            _install_exact_root(
                self, attribute, getattr(self, attribute), kind, _thaw_json(body)
            )
        _install_exact_root(
            self,
            "source_lineage_root",
            self.source_lineage_root,
            "hybrid-replay-source-lineage",
            {
                "source_step_root": self.source_step_root,
                "source_trace_set_root": self.source_trace_set_root,
            },
        )
        _install_exact_root(
            self,
            "state_root",
            self.state_root,
            "hybrid-replay-state",
            self._state_body(),
        )
        _install_exact_root(
            self,
            "snapshot_root",
            self.snapshot_root,
            "hybrid-replay-snapshot",
            self._snapshot_body(),
        )
        if len(_canonical_bytes(self.to_dict())) > MAX_HYBRID_REPLAY_SNAPSHOT_BYTES_V2:
            raise ValueError("Hybrid replay canonical snapshot exceeds its byte bound")

    @property
    def processed_pheromone_event_ids(self) -> frozenset[str]:
        return frozenset(
            cast(str, receipt["event_id"])
            for receipt in self.replay_receipts
            if receipt["kind"] in {"deposit", "diffusion"}
        )

    @property
    def processed_feedback_ids(self) -> frozenset[str]:
        return frozenset(
            cast(str, receipt["event_id"])
            for receipt in self.replay_receipts
            if receipt["kind"] == "feedback"
        )

    @property
    def processed_adjustment_ids(self) -> frozenset[str]:
        return frozenset(
            cast(str, receipt["event_id"])
            for receipt in self.replay_receipts
            if receipt["kind"] == "adjustment"
        )

    def _state_body(self) -> dict[str, object]:
        return {
            "state_schema": self.state_schema,
            "canonical_version": self.canonical_version,
            "numeric_wire_version": self.numeric_wire_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "manifest_root": self.manifest_root,
            "protocol_ref": self.protocol_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "observed_epoch": self.observed_epoch,
            "stream_ref": self.stream_ref,
            "advance_ref": self.advance_ref,
            "transition_id": self.transition_id,
            "revision": self.revision,
            "current_step": self.current_step,
            "parent_revision": self.parent_revision,
            "parent_transition_id": self.parent_transition_id,
            "parent_snapshot_root": self.parent_snapshot_root,
            "candidate_projection": _thaw_json(self.candidate_projection),
            "candidate_projection_root": self.candidate_projection_root,
            "policy_projection": _thaw_json(self.policy_projection),
            "policy_projection_root": self.policy_projection_root,
            "topology_projection": _thaw_json(self.topology_projection),
            "topology_projection_root": self.topology_projection_root,
            "active_trails": _thaw_json(self.active_trails),
            "active_trails_root": self.active_trails_root,
            "replay_receipts": _thaw_json(self.replay_receipts),
            "replay_receipts_root": self.replay_receipts_root,
            "last_budget": _thaw_json(self.last_budget),
            "last_budget_root": self.last_budget_root,
            "overlay": _thaw_json(self.overlay),
            "overlay_root": self.overlay_root,
            "effective_policy_projection": _thaw_json(self.effective_policy_projection),
            "effective_policy_root": self.effective_policy_root,
            "source_step_root": self.source_step_root,
            "source_trace_roots": list(self.source_trace_roots),
            "source_trace_set_root": self.source_trace_set_root,
            "source_lineage_root": self.source_lineage_root,
        }

    def _snapshot_body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            **self._state_body(),
            "state_root": self.state_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._snapshot_body(), "snapshot_root": self.snapshot_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.snapshot_root

    @classmethod
    def from_dict(cls, payload: object) -> HybridReplaySnapshotV2:
        fields = frozenset(
            {
                "schema",
                "state_schema",
                "canonical_version",
                "numeric_wire_version",
                "domain_root",
                "scope_ref",
                "manifest_root",
                "protocol_ref",
                "run_ref",
                "target_ref",
                "observed_epoch",
                "stream_ref",
                "advance_ref",
                "transition_id",
                "revision",
                "current_step",
                "parent_revision",
                "parent_transition_id",
                "parent_snapshot_root",
                "candidate_projection",
                "candidate_projection_root",
                "policy_projection",
                "policy_projection_root",
                "topology_projection",
                "topology_projection_root",
                "active_trails",
                "active_trails_root",
                "replay_receipts",
                "replay_receipts_root",
                "last_budget",
                "last_budget_root",
                "overlay",
                "overlay_root",
                "effective_policy_projection",
                "effective_policy_root",
                "source_step_root",
                "source_trace_roots",
                "source_trace_set_root",
                "source_lineage_root",
                "state_root",
                "snapshot_root",
            }
        )
        value = _require_exact_mapping(payload, fields, "Hybrid replay snapshot v2")
        return cls(**value)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class HybridReplayAdvanceRequestV2:
    """Idempotent request binding one fully prepared next snapshot."""

    domain_root: str
    scope_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    advance_ref: str
    transition_id: str
    stream_ref: str
    snapshot: HybridReplaySnapshotV2
    schema: str = HYBRID_REPLAY_ADVANCE_REQUEST_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    request_root: str = ""

    _root_field: ClassVar[str] = "request_root"

    def __post_init__(self) -> None:
        _require_exact_version(
            self.schema,
            HYBRID_REPLAY_ADVANCE_REQUEST_SCHEMA_V2,
            "Hybrid replay advance request schema",
        )
        _require_exact_version(
            self.canonical_version,
            AUTHORITY_CANONICAL_VERSION_V2,
            "Hybrid replay advance request canonical_version",
        )
        _require_root(self.domain_root, "Hybrid replay advance request domain_root")
        for field in (
            "scope_ref",
            "run_ref",
            "target_ref",
            "advance_ref",
            "transition_id",
        ):
            _require_bounded_text(
                getattr(self, field), f"Hybrid replay advance request {field}"
            )
        _require_count(
            self.observed_epoch, "Hybrid replay advance request observed_epoch"
        )
        if type(self.snapshot) is not HybridReplaySnapshotV2:
            raise TypeError(
                "Hybrid replay advance request requires exact HybridReplaySnapshotV2"
            )
        for field in (
            "domain_root",
            "scope_ref",
            "run_ref",
            "target_ref",
            "observed_epoch",
            "advance_ref",
            "transition_id",
            "stream_ref",
        ):
            if getattr(self, field) != getattr(self.snapshot, field):
                raise ValueError(
                    f"Hybrid replay advance request {field} is cross-bound incorrectly"
                )
        _install_exact_root(
            self,
            "request_root",
            self.request_root,
            "hybrid-replay-advance-request",
            self._body(),
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "observed_epoch": self.observed_epoch,
            "advance_ref": self.advance_ref,
            "transition_id": self.transition_id,
            "stream_ref": self.stream_ref,
            "snapshot": self.snapshot.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "request_root": self.request_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.request_root

    @classmethod
    def from_dict(cls, payload: object) -> HybridReplayAdvanceRequestV2:
        fields = frozenset(
            {
                "schema",
                "canonical_version",
                "domain_root",
                "scope_ref",
                "run_ref",
                "target_ref",
                "observed_epoch",
                "advance_ref",
                "transition_id",
                "stream_ref",
                "snapshot",
                "request_root",
            }
        )
        value = _require_exact_mapping(
            payload, fields, "Hybrid replay advance request v2"
        )
        value["snapshot"] = HybridReplaySnapshotV2.from_dict(value["snapshot"])
        return cls(**value)  # type: ignore[arg-type]


__all__ = [
    "HYBRID_REPLAY_ADVANCE_REQUEST_SCHEMA_V2",
    "HYBRID_REPLAY_DIFFUSION_REPLAY_VERSION_V2",
    "HYBRID_REPLAY_GENESIS_SNAPSHOT_ROOT_V2",
    "HYBRID_REPLAY_SNAPSHOT_SCHEMA_V2",
    "HYBRID_REPLAY_STATE_SCHEMA_V2",
    "HybridReplayAdvanceRequestV2",
    "HybridReplaySnapshotV2",
    "hybrid_replay_diffusion_source_trail_root_v2",
    "hybrid_replay_stream_ref_v2",
    "hybrid_replay_transition_id_v2",
]
