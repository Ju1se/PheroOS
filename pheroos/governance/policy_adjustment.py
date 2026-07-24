from __future__ import annotations

from collections.abc import Iterator, Mapping
from copy import deepcopy
import math
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, TypeGuard

from pheroos.governance._validation import is_nonblank_string
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.models import (
    CollectiveDecisionPolicy,
    PheromoneKindProfile,
    deep_freeze,
    thaw_protocol_value,
)


SUPPORTED_POLICY_ADJUSTMENT_LAYER_IDS = frozenset(
    {"reactive", "learned", "evolutionary", "metacognitive"}
)
ADJUSTMENT_PROPOSER_LAYER_IDS = frozenset({"learned", "evolutionary", "metacognitive"})
SUPPORTED_RESPONSE_MODELS = frozenset(
    {"linear", "saturating", "threshold", "competitive"}
)
SUPPORTED_KIND_WEIGHT_FIELDS = frozenset(
    {
        "pheromone_positive_weight",
        "pheromone_negative_weight",
        "pheromone_cautionary_weight",
        "pheromone_alarm_weight",
        "pheromone_novelty_weight",
    }
)
SUPPORTED_LAYER_WEIGHT_FIELDS = frozenset(
    {
        "layer_learned_weight",
        "layer_evolutionary_weight",
        "layer_metacognitive_weight",
    }
)
SUPPORTED_POLICY_ADJUSTMENT_FIELDS = frozenset(
    {
        "pheromone_evaporation_rate",
        "pheromone_response_model",
        "pheromone_exploration_floor",
        "pheromone_cautionary_override_threshold",
        "layer_emergency_override_threshold",
        *SUPPORTED_KIND_WEIGHT_FIELDS,
        *SUPPORTED_LAYER_WEIGHT_FIELDS,
    }
)


@dataclass(frozen=True)
class PolicyAdjustmentProposal:
    layer_id: str
    source_id: str
    adjustments: dict[str, Any]
    provenance: str
    trace_event_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "adjustments",
            MappingProxyType(thaw_protocol_value(self.adjustments)),
        )

    def __deepcopy__(self, memo: dict[int, object]) -> PolicyAdjustmentProposal:
        del memo
        return self


_RUN_SCOPED_OVERLAY_ISSUANCE = object()


class RunScopedPolicyOverlay(Mapping[str, Any]):
    """Immutable run overlay; only governance validation can issue authority."""

    __slots__ = ("_values", "source_ids", "trace_event_ids", "_issuance")
    _values: Mapping[str, Any]
    source_ids: tuple[str, ...]
    trace_event_ids: tuple[str, ...]
    _issuance: object | None

    def __init__(
        self,
        values: dict[str, Any] | None = None,
        *,
        source_ids: tuple[str, ...] = (),
        trace_event_ids: tuple[str, ...] = (),
    ) -> None:
        object.__setattr__(self, "_values", deep_freeze(values or {}))
        object.__setattr__(self, "source_ids", tuple(source_ids))
        object.__setattr__(self, "trace_event_ids", tuple(trace_event_ids))
        object.__setattr__(self, "_issuance", None)

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("run-scoped policy overlay is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("run-scoped policy overlay is immutable")

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        return repr(dict(self._values))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return dict(self._values) == dict(other)
        return False

    def __copy__(self) -> RunScopedPolicyOverlay:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> RunScopedPolicyOverlay:
        del memo
        return self


def _issue_run_scoped_policy_overlay(
    values: dict[str, Any],
    *,
    source_ids: tuple[str, ...],
    trace_event_ids: tuple[str, ...],
) -> RunScopedPolicyOverlay:
    overlay = RunScopedPolicyOverlay(
        values,
        source_ids=source_ids,
        trace_event_ids=trace_event_ids,
    )
    object.__setattr__(
        overlay,
        "_issuance",
        (
            _RUN_SCOPED_OVERLAY_ISSUANCE,
            _run_scoped_policy_overlay_snapshot(overlay),
        ),
    )
    return overlay


def _canonical_overlay_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(
            (key, _canonical_overlay_value(item))
            for key, item in sorted(value.items(), key=lambda pair: repr(pair[0]))
        )
    if isinstance(value, (list, tuple)):
        return tuple(_canonical_overlay_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(
            sorted(
                (_canonical_overlay_value(item) for item in value),
                key=repr,
            )
        )
    return deepcopy(value)


def _run_scoped_policy_overlay_snapshot(
    overlay: RunScopedPolicyOverlay,
) -> tuple[tuple[tuple[str, Any], ...], tuple[str, ...], tuple[str, ...]]:
    return (
        tuple(
            (key, _canonical_overlay_value(value))
            for key, value in sorted(overlay.items())
        ),
        tuple(overlay.source_ids),
        tuple(overlay.trace_event_ids),
    )


def run_scoped_policy_overlay_is_authoritative(overlay: object) -> bool:
    if type(overlay) is not RunScopedPolicyOverlay:
        return False
    try:
        issuance = overlay._issuance
        current_snapshot = _run_scoped_policy_overlay_snapshot(overlay)
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _RUN_SCOPED_OVERLAY_ISSUANCE
            and issuance[1] == current_snapshot
            and (
                not overlay
                or (
                    bool(overlay.source_ids)
                    and bool(overlay.trace_event_ids)
                    and all(is_nonblank_string(item) for item in overlay.source_ids)
                    and all(
                        is_nonblank_string(item) for item in overlay.trace_event_ids
                    )
                )
            )
        )
    except Exception:
        # A caller can use object.__setattr__ to corrupt a slot despite the
        # public assignment guard.  Malformed state is never authoritative and
        # must fail closed rather than escaping into policy application.
        return False


@dataclass(frozen=True)
class PolicyAdjustmentBatchResult:
    overlay: RunScopedPolicyOverlay
    accepted_trace_event_ids: tuple[str, ...] = ()
    processed_trace_event_ids: frozenset[str] = frozenset()


def validate_policy_adjustment_proposal(
    proposal: PolicyAdjustmentProposal,
    policy: object,
) -> RunScopedPolicyOverlay:
    accepted = _validate_policy_adjustment_proposal(proposal, policy)
    return _issue_run_scoped_policy_overlay(
        accepted,
        source_ids=(proposal.source_id,),
        trace_event_ids=(proposal.trace_event_id,),
    )


def validate_policy_adjustment_proposals(
    proposals: list[PolicyAdjustmentProposal],
    policy: object,
    *,
    processed_trace_event_ids: frozenset[str] = frozenset(),
) -> PolicyAdjustmentBatchResult:
    """Validate an adjustment batch atomically and return one run overlay.

    Duplicate keys are rejected instead of applying order-sensitive last-write
    wins.  Processed trace ids are idempotent no-ops across replay.
    """

    items = list(proposals)
    validated: list[tuple[PolicyAdjustmentProposal, dict[str, Any]]] = []
    for proposal in items:
        validated.append(
            (proposal, _validate_policy_adjustment_proposal(proposal, policy))
        )
    trace_ids: set[str] = set()
    for proposal, _ in validated:
        if proposal.trace_event_id in trace_ids:
            raise GovernanceError(
                f"duplicate policy adjustment trace_event_id: {proposal.trace_event_id}"
            )
        trace_ids.add(proposal.trace_event_id)

    processed = set(processed_trace_event_ids)
    pending = [item for item in validated if item[0].trace_event_id not in processed]
    pending.sort(
        key=lambda item: (item[0].layer_id, item[0].source_id, item[0].trace_event_id)
    )
    accepted: dict[str, Any] = {}
    accepted_sources: list[str] = []
    accepted_events: list[str] = []
    for proposal, values in pending:
        for key, value in sorted(values.items()):
            if key in accepted:
                raise GovernanceError(
                    f"policy adjustment key is proposed more than once in a batch: {key}"
                )
            accepted[key] = value
        accepted_sources.append(proposal.source_id)
        accepted_events.append(proposal.trace_event_id)
        processed.add(proposal.trace_event_id)
    overlay = _issue_run_scoped_policy_overlay(
        accepted,
        source_ids=tuple(accepted_sources),
        trace_event_ids=tuple(accepted_events),
    )
    return PolicyAdjustmentBatchResult(
        overlay=overlay,
        accepted_trace_event_ids=tuple(accepted_events),
        processed_trace_event_ids=frozenset(processed),
    )


def validate_policy_adjustment_bounds(policy: object) -> None:
    """Validate every declared adjustment dimension at the runtime boundary."""

    declared_bounds = getattr(policy, "policy_adjustment_bounds", None)
    if not isinstance(declared_bounds, Mapping):
        raise GovernanceError("active policy does not expose adjustment bounds")
    for key, bounds in sorted(declared_bounds.items()):
        if not isinstance(key, str) or key not in SUPPORTED_POLICY_ADJUSTMENT_FIELDS:
            raise GovernanceError(f"policy adjustment field is not allowlisted: {key}")
        values: tuple[Any, ...]
        numeric_bounds: tuple[float, float] | None = None
        if isinstance(bounds, (list, tuple)) and len(bounds) == 2:
            if (
                not numeric(bounds[0])
                or not numeric(bounds[1])
                or float(bounds[0]) > float(bounds[1])
            ):
                raise GovernanceError(f"policy adjustment bounds are invalid: {key}")
            values = (bounds[0], bounds[1])
            numeric_bounds = (float(bounds[0]), float(bounds[1]))
        elif isinstance(bounds, Mapping) and set(bounds) == {"min", "max"}:
            if (
                not numeric(bounds["min"])
                or not numeric(bounds["max"])
                or float(bounds["min"]) > float(bounds["max"])
            ):
                raise GovernanceError(f"policy adjustment bounds are invalid: {key}")
            values = (bounds["min"], bounds["max"])
            numeric_bounds = (float(bounds["min"]), float(bounds["max"]))
        elif isinstance(bounds, Mapping) and set(bounds) == {"allowed_values"}:
            allowed = bounds["allowed_values"]
            if not isinstance(allowed, (list, tuple)) or not allowed:
                raise GovernanceError(
                    f"policy adjustment allowed values are invalid: {key}"
                )
            values = tuple(allowed)
        else:
            raise GovernanceError(f"policy adjustment bounds are invalid: {key}")
        for value in values:
            validate_absolute_adjustment_value(key, value)
        if key == "pheromone_cautionary_override_threshold":
            maximum_strength = getattr(policy, "pheromone_max_strength", None)
            if (
                numeric_bounds is None
                or not numeric(maximum_strength)
                or numeric_bounds[1] > float(maximum_strength)
            ):
                raise GovernanceError(
                    "pheromone cautionary adjustment bounds exceed the declared maximum strength"
                )
        if key in SUPPORTED_LAYER_WEIGHT_FIELDS:
            layer_id = key.removeprefix("layer_").removesuffix("_weight")
            layer_bounds = getattr(policy, "layer_weight_bounds", None)
            if not isinstance(layer_bounds, Mapping) or layer_id not in layer_bounds:
                raise GovernanceError(
                    f"policy adjustment requires declared layer weight bounds: {layer_id}"
                )
            owner_bounds = layer_bounds[layer_id]
            if (
                not isinstance(owner_bounds, (list, tuple))
                or len(owner_bounds) != 2
                or not numeric(owner_bounds[0])
                or not numeric(owner_bounds[1])
                or float(owner_bounds[0]) > float(owner_bounds[1])
                or numeric_bounds is None
                or numeric_bounds[0] < float(owner_bounds[0])
                or numeric_bounds[1] > float(owner_bounds[1])
            ):
                raise GovernanceError(
                    f"policy adjustment bounds exceed declared layer weight bounds: {layer_id}"
                )


def _validate_policy_adjustment_proposal(
    proposal: PolicyAdjustmentProposal,
    policy: object,
) -> dict[str, Any]:
    validate_policy_adjustment_bounds(policy)
    for field_name in ("layer_id", "source_id", "provenance", "trace_event_id"):
        if not isinstance(getattr(proposal, field_name), str):
            raise GovernanceError(
                f"policy adjustment proposal {field_name} must be a string"
            )
    if proposal.layer_id not in SUPPORTED_POLICY_ADJUSTMENT_LAYER_IDS:
        raise GovernanceError(f"unsupported layer id: {proposal.layer_id}")
    if proposal.layer_id not in ADJUSTMENT_PROPOSER_LAYER_IDS:
        raise GovernanceError("reactive layer cannot propose policy adjustment")
    if not is_nonblank_string(proposal.source_id):
        raise GovernanceError("policy adjustment proposal source_id is required")
    if not is_nonblank_string(proposal.provenance):
        raise GovernanceError("policy adjustment proposal is missing provenance")
    if not is_nonblank_string(proposal.trace_event_id):
        raise GovernanceError("policy adjustment proposal is missing trace event id")
    if not proposal.adjustments:
        raise GovernanceError(
            "policy adjustment proposal must contain at least one adjustment"
        )
    declared_bounds = getattr(policy, "policy_adjustment_bounds", None)
    if not isinstance(declared_bounds, Mapping):
        raise GovernanceError("active policy does not expose adjustment bounds")
    accepted: dict[str, Any] = {}
    for key, value in sorted(proposal.adjustments.items()):
        if not isinstance(key, str) or key not in SUPPORTED_POLICY_ADJUSTMENT_FIELDS:
            raise GovernanceError(f"policy adjustment field is not allowlisted: {key}")
        if key not in declared_bounds:
            raise GovernanceError(
                f"policy adjustment is outside declared bounds: {key}"
            )
        validate_absolute_adjustment_value(key, value)
        bounds = declared_bounds[key]
        if not adjustment_value_allowed(value, bounds):
            raise GovernanceError(
                f"policy adjustment value is outside declared bounds: {key}"
            )
        accepted[key] = value
    return accepted


def validate_absolute_adjustment_value(key: str, value: Any) -> None:
    if key == "pheromone_response_model":
        if value not in SUPPORTED_RESPONSE_MODELS:
            raise GovernanceError("policy response model adjustment is unsupported")
        return
    if not numeric(value):
        raise GovernanceError(f"policy adjustment value must be a finite number: {key}")
    number = float(value)
    if key == "pheromone_evaporation_rate" and not 0 <= number <= 1:
        raise GovernanceError(
            "pheromone evaporation adjustment is outside absolute bounds"
        )
    if key == "pheromone_exploration_floor" and not 0 <= number <= 1:
        raise GovernanceError(
            "pheromone exploration adjustment is outside absolute bounds"
        )
    if (
        key in SUPPORTED_KIND_WEIGHT_FIELDS | SUPPORTED_LAYER_WEIGHT_FIELDS
        and not 0 <= number <= 10
    ):
        raise GovernanceError("policy weight adjustment is outside absolute bounds")
    if key == "pheromone_cautionary_override_threshold" and not 0 <= number <= 10:
        raise GovernanceError(
            "pheromone threshold adjustment is outside absolute bounds"
        )
    if key == "layer_emergency_override_threshold" and not 0 <= number <= 1:
        raise GovernanceError(
            "layer emergency threshold adjustment is outside absolute bounds"
        )


def apply_policy_adjustment_overlay(
    policy: CollectiveDecisionPolicy,
    overlay: RunScopedPolicyOverlay,
) -> CollectiveDecisionPolicy:
    """Return a run-scoped adjusted policy without mutating the manifest ABI."""

    validate_policy_adjustment_bounds(policy)
    if not run_scoped_policy_overlay_is_authoritative(overlay):
        raise GovernanceError("policy adjustment overlay must be governance-validated")
    for key, value in overlay.items():
        if key not in SUPPORTED_POLICY_ADJUSTMENT_FIELDS:
            raise GovernanceError(f"policy adjustment field is not allowlisted: {key}")
        if key not in policy.policy_adjustment_bounds:
            raise GovernanceError(
                f"policy adjustment is outside declared bounds: {key}"
            )
        validate_absolute_adjustment_value(key, value)
        if not adjustment_value_allowed(value, policy.policy_adjustment_bounds[key]):
            raise GovernanceError(
                f"policy adjustment value is outside declared bounds: {key}"
            )

    scalar_updates: dict[str, Any] = {}
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
    for overlay_key, policy_field in scalar_mapping.items():
        if overlay_key in overlay:
            scalar_updates[policy_field] = overlay[overlay_key]

    kind_mapping = {
        "pheromone_positive_weight": "positive",
        "pheromone_negative_weight": "negative",
        "pheromone_cautionary_weight": "cautionary",
        "pheromone_alarm_weight": "alarm",
        "pheromone_novelty_weight": "novelty",
    }
    kind_profiles = dict(policy.pheromone_kind_profiles)
    # Run-scoped global dynamics are authoritative for the run.  Applying
    # them to declared kind profiles prevents an accepted adjustment from
    # becoming a shadowed no-op when every active kind has a local override.
    if "pheromone_evaporation_rate" in overlay:
        evaporation_rate = float(overlay["pheromone_evaporation_rate"])
        kind_profiles = {
            kind: replace(profile, evaporation_rate=evaporation_rate)
            for kind, profile in kind_profiles.items()
        }
    if "pheromone_response_model" in overlay:
        response_model = str(overlay["pheromone_response_model"])
        kind_profiles = {
            kind: replace(profile, response_model=response_model)
            for kind, profile in kind_profiles.items()
        }
    for overlay_key, kind in kind_mapping.items():
        if overlay_key not in overlay:
            continue
        profile = kind_profiles.get(kind, PheromoneKindProfile())
        kind_profiles[kind] = replace(profile, weight=float(overlay[overlay_key]))

    layer_mapping = {
        "layer_learned_weight": "learned",
        "layer_evolutionary_weight": "evolutionary",
        "layer_metacognitive_weight": "metacognitive",
    }
    layer_weights = dict(policy.layer_default_weights)
    for overlay_key, layer_id in layer_mapping.items():
        if overlay_key in overlay:
            layer_weights[layer_id] = float(overlay[overlay_key])

    return replace(
        policy,
        **scalar_updates,
        pheromone_kind_profiles=kind_profiles,
        layer_default_weights=layer_weights,
    )


def adjustment_value_allowed(value: Any, bounds: Any) -> bool:
    if isinstance(bounds, (list, tuple)) and len(bounds) == 2:
        return (
            numeric(value)
            and numeric(bounds[0])
            and numeric(bounds[1])
            and float(bounds[0]) <= float(value) <= float(bounds[1])
        )
    if isinstance(bounds, Mapping):
        if set(bounds) == {"allowed_values"}:
            allowed_values = bounds["allowed_values"]
            if not isinstance(allowed_values, (list, tuple)) or not allowed_values:
                return False
            return any(
                type(value) is type(allowed) and value == allowed
                for allowed in allowed_values
            )
        if set(bounds) == {"min", "max"}:
            return (
                numeric(value)
                and numeric(bounds["min"])
                and numeric(bounds["max"])
                and float(bounds["min"]) <= float(value) <= float(bounds["max"])
            )
    return False


def numeric(value: object) -> TypeGuard[int | float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))
