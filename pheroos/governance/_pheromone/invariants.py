from __future__ import annotations

from dataclasses import replace
from pheroos.governance._validation import is_nonblank_string
from pheroos.governance.candidate import CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.models import CollectiveDecisionPolicy
from pheroos.protocol.models import PheromoneKindProfile
from pheroos.protocol.models import SUPPORTED_PHEROMONE_DECAY_MODELS
from pheroos.protocol.models import effective_pheromone_scored_subject_types
from pheroos.protocol.models import is_scored_pheromone_subject_type
from typing import Any
import math
from pheroos.governance._pheromone.records import PHEROMONE_EXTENSION_PREFIXES, PheromoneDiffusionPolicy, PheromoneNeighborhood, PheromonePolicy, PheromoneSubject, PheromoneTrail, SUPPORTED_PHEROMONE_COMPETITION_MODES, SUPPORTED_PHEROMONE_KINDS, SUPPORTED_PHEROMONE_RESPONSE_MODELS, SUPPORTED_PHEROMONE_SUBJECT_TYPES

def pheromone_policy_from_collective(policy: CollectiveDecisionPolicy) -> PheromonePolicy:
    kind_profiles = canonical_pheromone_kind_profiles(policy)
    return PheromonePolicy(
        enabled=policy.pheromone_enabled,
        evaporation_rate=policy.pheromone_evaporation_rate,
        decay_model=policy.pheromone_decay_model,
        min_strength=policy.pheromone_min_strength,
        max_strength=policy.pheromone_max_strength,
        positive_weight=policy.pheromone_positive_weight,
        negative_weight=policy.pheromone_negative_weight,
        cautionary_weight=policy.pheromone_cautionary_weight,
        cautionary_override_threshold=policy.pheromone_cautionary_override_threshold,
        novelty_weight=policy.pheromone_novelty_weight,
        per_source_cap=policy.pheromone_per_source_cap,
        per_round_deposit_cap=policy.pheromone_per_round_deposit_cap,
        min_source_diversity=policy.pheromone_min_source_diversity,
        require_provenance=policy.pheromone_require_provenance,
        require_trace=policy.pheromone_require_trace,
        scored_subject_types=list(policy.pheromone_scored_subject_types),
        kind_profiles={
            kind: PheromoneKindProfile(
                weight=profile.weight,
                evaporation_rate=profile.evaporation_rate,
                ttl_steps=profile.ttl_steps,
                response_model=profile.response_model,
                priority=profile.priority,
                can_suppress_positive=profile.can_suppress_positive,
                scored_subject_types=list(profile.scored_subject_types),
                extensions=dict(profile.extensions),
            )
            for kind, profile in kind_profiles.items()
        },
        response_model=policy.pheromone_response_model,
        activation_threshold=policy.pheromone_activation_threshold,
        saturation_threshold=policy.pheromone_saturation_threshold,
        competition_mode=policy.pheromone_competition_mode,
        exploration_floor=policy.exploration_floor,
        exploration_enabled=policy.exploration_enabled,
        novelty_decay_rate=policy.novelty_decay_rate,
        stale_route_reopen_threshold=policy.stale_route_reopen_threshold,
        feedback_enabled=policy.pheromone_feedback_enabled,
        response_exploration_floor=policy.pheromone_exploration_floor,
    )


def canonical_pheromone_kind_profiles(
    policy: CollectiveDecisionPolicy,
) -> dict[str, PheromoneKindProfile]:
    """Return the single runtime map used to interpret pheromone kinds.

    ``pheroos-pheromone-kind-profile-map-v1`` resolves the legacy scalar and
    per-kind double-write deterministically: an explicitly declared kind
    profile wins in full, while legacy scalar weights only synthesize missing
    built-in kinds.  Extension kinds are never inferred.  Empty built-in
    ``scored_subject_types`` intentionally retain the protocol's documented
    policy-wide inheritance semantics.
    """

    profiles = dict(policy.pheromone_kind_profiles)
    legacy_weights = {
        "positive": policy.pheromone_positive_weight,
        "negative": policy.pheromone_negative_weight,
        "cautionary": policy.pheromone_cautionary_weight,
        "alarm": policy.pheromone_cautionary_weight,
        "novelty": policy.pheromone_novelty_weight,
        "stale": 0.0,
    }
    for kind in sorted(SUPPORTED_PHEROMONE_KINDS):
        if kind in profiles:
            continue
        profiles[kind] = PheromoneKindProfile(
            weight=legacy_weights[kind],
            evaporation_rate=None,
            ttl_steps=None,
            response_model=policy.pheromone_response_model,
            priority=_DEFAULT_KIND_PRIORITY[kind],
            can_suppress_positive=kind in {"cautionary", "alarm"},
            scored_subject_types=[],
        )
    return profiles


def normalize_legacy_pheromone_trail(
    trail: PheromoneTrail,
    *,
    target: str,
    source_id: str,
    provenance: str,
    trace_event_id: str,
    source_role: str = "",
    evidence_id: str = "",
) -> PheromoneTrail:
    """Bind a legacy trail to an explicit subject and lineage envelope.

    The function is a migration boundary, not an authority shortcut.  It never
    invents target, source, provenance, evidence, or trace identifiers.  A
    value already present on the trail must match the supplied binding.
    """

    if not isinstance(trail, PheromoneTrail):
        raise GovernanceError("legacy pheromone trail must be a PheromoneTrail")
    supplied = {
        "target": target,
        "source_id": source_id,
        "provenance": provenance,
        "trace_event_id": trace_event_id,
    }
    for field_name, value in supplied.items():
        if not is_nonblank_string(value):
            raise GovernanceError(
                f"legacy pheromone normalization requires non-blank {field_name}"
            )
        current = getattr(trail, field_name)
        if current and current != value:
            raise GovernanceError(
                f"legacy pheromone {field_name} conflicts with declared binding"
            )
    for field_name, value in {"source_role": source_role, "evidence_id": evidence_id}.items():
        if value and not is_nonblank_string(value):
            raise GovernanceError(
                f"legacy pheromone {field_name} must be non-blank when supplied"
            )
        current = getattr(trail, field_name)
        if current and value and current != value:
            raise GovernanceError(
                f"legacy pheromone {field_name} conflicts with declared binding"
            )

    declared_subject_id = trail.subject_id
    declared_subject_type = trail.subject_type
    legacy_subjects = [
        ("candidate", trail.candidate_id),
        ("route", trail.route_id),
        ("tool", trail.tool_id),
    ]
    bound_subjects = [(kind, identifier) for kind, identifier in legacy_subjects if identifier]
    if declared_subject_id:
        if not is_nonblank_string(declared_subject_id):
            raise GovernanceError("legacy pheromone subject_id must be non-blank")
        if any(
            kind == declared_subject_type and identifier != declared_subject_id
            for kind, identifier in bound_subjects
        ):
            raise GovernanceError("legacy pheromone subject binding is inconsistent")
        subject_type = declared_subject_type
        subject_id = declared_subject_id
    else:
        direct_subjects = [
            (kind, identifier)
            for kind, identifier in bound_subjects
            if kind != "candidate" or not trail.route_id and not trail.tool_id
        ]
        route_tool_subjects = [item for item in bound_subjects if item[0] in {"route", "tool"}]
        if len(route_tool_subjects) > 1:
            raise GovernanceError("legacy pheromone trail has ambiguous route/tool subject bindings")
        if route_tool_subjects:
            subject_type, subject_id = route_tool_subjects[0]
        elif direct_subjects:
            subject_type, subject_id = direct_subjects[0]
        else:
            raise GovernanceError("legacy pheromone trail does not identify a subject")

    if subject_type == "candidate" and trail.candidate_id != subject_id:
        raise GovernanceError("legacy candidate pheromone subject must match candidate_id")
    return replace(
        trail,
        subject_type=subject_type,
        subject_id=subject_id,
        target=target,
        source_id=source_id,
        source_role=source_role or trail.source_role,
        evidence_id=evidence_id or trail.evidence_id,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )


def diffusion_policy_from_collective(policy: CollectiveDecisionPolicy) -> PheromoneDiffusionPolicy:
    return PheromoneDiffusionPolicy(
        enabled=policy.pheromone_diffusion_enabled,
        max_hops=policy.pheromone_diffusion_max_hops,
        attenuation=policy.pheromone_diffusion_attenuation,
    )


def _finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GovernanceError(f"{field_name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise GovernanceError(f"{field_name} must be a finite number")
    return number


def _non_negative_number(value: object, field_name: str) -> float:
    number = _finite_number(value, field_name)
    if number < 0:
        raise GovernanceError(f"{field_name} must be non-negative")
    return number


def _non_negative_step(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GovernanceError(f"{field_name} must be a non-negative integer")
    return value


def validate_pheromone_policy(policy: PheromonePolicy) -> None:
    if not isinstance(policy.enabled, bool):
        raise GovernanceError("pheromone enabled must be boolean")
    if not isinstance(policy.feedback_enabled, bool):
        raise GovernanceError("pheromone feedback_enabled must be boolean")
    if not isinstance(policy.exploration_enabled, bool):
        raise GovernanceError("pheromone exploration_enabled must be boolean")
    if not isinstance(policy.require_provenance, bool) or not isinstance(policy.require_trace, bool):
        raise GovernanceError("pheromone provenance and trace requirements must be boolean")
    evaporation_rate = _finite_number(policy.evaporation_rate, "pheromone evaporation_rate")
    if not 0 <= evaporation_rate <= 1:
        raise GovernanceError("pheromone evaporation_rate must be between 0 and 1")
    if not isinstance(policy.decay_model, str) or policy.decay_model not in SUPPORTED_PHEROMONE_DECAY_MODELS:
        raise GovernanceError(f"unsupported pheromone decay model: {policy.decay_model}")
    minimum = _non_negative_number(policy.min_strength, "pheromone min_strength")
    maximum = _non_negative_number(policy.max_strength, "pheromone max_strength")
    if minimum > maximum:
        raise GovernanceError("pheromone min_strength must not exceed max_strength")
    for name in (
        "positive_weight",
        "negative_weight",
        "cautionary_weight",
        "cautionary_override_threshold",
        "novelty_weight",
        "per_source_cap",
        "per_round_deposit_cap",
        "activation_threshold",
        "saturation_threshold",
        "exploration_floor",
        "stale_route_reopen_threshold",
        "response_exploration_floor",
    ):
        _non_negative_number(getattr(policy, name), f"pheromone {name}")
    for name in ("exploration_floor", "response_exploration_floor"):
        if getattr(policy, name) > 1:
            raise GovernanceError(f"pheromone {name} must be between 0 and 1")
    if policy.enabled and any(
        policy.min_strength > bound
        for bound in (policy.max_strength, policy.per_source_cap, policy.per_round_deposit_cap)
    ):
        raise GovernanceError(
            "pheromone minimum strength must fit max/source/round bounds"
        )
    novelty_decay_rate = _finite_number(policy.novelty_decay_rate, "pheromone novelty_decay_rate")
    if not 0 <= novelty_decay_rate <= 1:
        raise GovernanceError("pheromone novelty_decay_rate must be between 0 and 1")
    if isinstance(policy.min_source_diversity, bool) or not isinstance(policy.min_source_diversity, int):
        raise GovernanceError("pheromone min_source_diversity must be a positive integer")
    if policy.min_source_diversity <= 0:
        raise GovernanceError("pheromone min_source_diversity must be a positive integer")
    if not isinstance(policy.response_model, str) or policy.response_model not in SUPPORTED_PHEROMONE_RESPONSE_MODELS:
        raise GovernanceError(f"unsupported pheromone response model: {policy.response_model}")
    if not isinstance(policy.competition_mode, str) or policy.competition_mode not in SUPPORTED_PHEROMONE_COMPETITION_MODES:
        raise GovernanceError(f"unsupported pheromone competition mode: {policy.competition_mode}")
    if not policy.scored_subject_types:
        raise GovernanceError("pheromone scored_subject_types must not be empty")
    for subject_type in policy.scored_subject_types:
        if not isinstance(subject_type, str) or (
            not is_scored_pheromone_subject_type(subject_type)
        ):
            raise GovernanceError(
                f"unsupported or non-scoring pheromone subject type: {subject_type}"
            )
    if len(set(policy.scored_subject_types)) != len(policy.scored_subject_types):
        raise GovernanceError("pheromone scored_subject_types must not contain duplicates")
    for kind, profile in policy.kind_profiles.items():
        if not isinstance(kind, str) or (
            kind not in SUPPORTED_PHEROMONE_KINDS and not is_extension_pheromone_value(kind)
        ):
            raise GovernanceError(f"unsupported pheromone kind profile: {kind}")
        if not isinstance(profile, PheromoneKindProfile):
            raise GovernanceError(f"pheromone kind profile has invalid type: {kind}")
        _non_negative_number(profile.weight, f"pheromone kind profile {kind} weight")
        if profile.evaporation_rate is not None:
            rate = _finite_number(profile.evaporation_rate, f"pheromone kind profile {kind} evaporation_rate")
            if not 0 <= rate <= 1:
                raise GovernanceError(f"pheromone kind profile {kind} evaporation_rate must be between 0 and 1")
        if profile.ttl_steps is not None:
            _non_negative_step(profile.ttl_steps, f"pheromone kind profile {kind} ttl_steps")
        if not isinstance(profile.response_model, str) or profile.response_model not in SUPPORTED_PHEROMONE_RESPONSE_MODELS:
            raise GovernanceError(f"unsupported pheromone kind profile response model: {profile.response_model}")
        if isinstance(profile.priority, bool) or not isinstance(profile.priority, int) or profile.priority < 0:
            raise GovernanceError(f"pheromone kind profile {kind} priority must be a non-negative integer")
        if not isinstance(profile.can_suppress_positive, bool):
            raise GovernanceError(f"pheromone kind profile {kind} can_suppress_positive must be boolean")
        for subject_type in profile.scored_subject_types:
            if not isinstance(subject_type, str) or (
                not is_scored_pheromone_subject_type(subject_type)
            ):
                raise GovernanceError(
                    f"unsupported or non-scoring pheromone subject type: {subject_type}"
                )
        if len(set(profile.scored_subject_types)) != len(profile.scored_subject_types):
            raise GovernanceError(f"pheromone kind profile {kind} subject types must not contain duplicates")
        if kind == "stale" and (profile.weight != 0 or profile.scored_subject_types):
            raise GovernanceError("stale pheromone kind profile must remain no-score")
    if policy.activation_threshold > 0:
        threshold_weights = []
        for kind in set(SUPPORTED_PHEROMONE_KINDS) | set(policy.kind_profiles):
            if kind == "stale":
                continue
            profile = policy.kind_profiles.get(kind)
            if not effective_pheromone_scored_subject_types(
                kind,
                profile,
                policy.scored_subject_types,
            ):
                continue
            response_model = profile.response_model if profile is not None else policy.response_model
            if response_model != "threshold":
                continue
            weight = profile.weight if profile is not None else legacy_pheromone_weight(kind, policy)
            threshold_weights.append(float(weight))
        maximum_threshold_delta = policy.max_strength * max(threshold_weights, default=0.0)
        if threshold_weights and (
            maximum_threshold_delta <= 0
            or policy.activation_threshold > maximum_threshold_delta
        ):
            raise GovernanceError(
                "pheromone activation_threshold cannot be reached by any declared threshold response"
            )


def validate_pheromone_diffusion_policy(policy: PheromoneDiffusionPolicy) -> None:
    if not isinstance(policy.enabled, bool):
        raise GovernanceError("pheromone diffusion enabled must be boolean")
    if isinstance(policy.max_hops, bool) or not isinstance(policy.max_hops, int) or policy.max_hops < 0:
        raise GovernanceError("pheromone diffusion max_hops must be a non-negative integer")
    attenuation = _finite_number(policy.attenuation, "pheromone diffusion attenuation")
    if not 0 <= attenuation <= 1:
        raise GovernanceError("pheromone diffusion attenuation must be between 0 and 1")
    if policy.enabled and (policy.max_hops <= 0 or attenuation <= 0):
        raise GovernanceError("enabled pheromone diffusion requires positive hops and attenuation")


def clip_pheromone_strength(strength: float, policy: PheromonePolicy) -> float:
    validate_pheromone_policy(policy)
    value = _finite_number(strength, "pheromone strength")
    clipped = min(policy.max_strength, max(policy.min_strength, value))
    if not math.isfinite(clipped):
        raise GovernanceError("clipped pheromone strength must be finite")
    return clipped


def validate_pheromone_trail(
    trail: PheromoneTrail,
    policy: PheromonePolicy,
    *,
    candidate_set: CandidateSet | None = None,
    target: str | None = None,
    allow_strength_above_max: bool = False,
    allow_strength_below_min: bool = False,
) -> None:
    validate_pheromone_policy(policy)
    for field_name in (
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
    ):
        if not isinstance(getattr(trail, field_name), str):
            raise GovernanceError(f"pheromone trail {field_name} must be a string")
    if trail.subject_type not in SUPPORTED_PHEROMONE_SUBJECT_TYPES and not is_extension_pheromone_value(trail.subject_type):
        raise GovernanceError(f"unsupported pheromone subject type: {trail.subject_type}")
    if trail.kind not in SUPPORTED_PHEROMONE_KINDS and not is_extension_pheromone_value(trail.kind):
        raise GovernanceError(f"unsupported pheromone kind: {trail.kind}")
    strength = _non_negative_number(trail.strength, "pheromone strength")
    if not allow_strength_below_min and strength < policy.min_strength:
        raise GovernanceError("active pheromone strength is below the declared minimum")
    if not allow_strength_above_max and strength > policy.max_strength:
        raise GovernanceError("active pheromone strength exceeds the declared maximum")
    if not is_nonblank_string(pheromone_subject_id(trail)):
        raise GovernanceError("pheromone trail must declare a subject")
    for field_name in ("candidate_id", "target", "route_id", "tool_id", "source_role", "evidence_id"):
        value = getattr(trail, field_name)
        if value and not is_nonblank_string(value):
            raise GovernanceError(f"pheromone trail {field_name} must be non-blank when declared")
    candidate_id = pheromone_bound_candidate_id(trail)
    subject_type = pheromone_subject_type(trail)
    subject_id = pheromone_subject_id(trail)
    if subject_type == "candidate" and candidate_id != subject_id:
        raise GovernanceError("candidate pheromone subject_id must match candidate_id")
    if candidate_id and candidate_set is not None:
        candidate = candidate_set.require_declared(candidate_id)
        if trail.target and trail.target != candidate.target:
            raise GovernanceError(
                f"pheromone trail targets {trail.target}, not candidate target {candidate.target}"
            )
        if target is not None and candidate.target != target:
            raise GovernanceError(
                f"pheromone trail candidate targets {candidate.target}, not active target {target}"
            )
    if trail.source_id and not is_nonblank_string(trail.source_id):
        raise GovernanceError("pheromone trail source_id must be non-blank")
    if target is not None:
        if not is_nonblank_string(trail.target):
            raise GovernanceError("target-scoped pheromone trail must declare target")
        if trail.target != target:
            raise GovernanceError(f"pheromone trail targets {trail.target}, not active target {target}")
    if policy.require_provenance and not is_nonblank_string(trail.provenance):
        raise GovernanceError("pheromone trail is missing provenance")
    if policy.require_trace and not is_nonblank_string(trail.trace_event_id):
        raise GovernanceError("pheromone trail is missing trace event id")
    # Legacy non-Hybrid callers may score anonymous trails when neither
    # provenance nor trace lineage is part of their declared contract.  A
    # lineage-aware policy, including every valid Hybrid policy, must bind the
    # trail to a non-blank source identity.
    if (
        policy.enabled
        and (policy.require_provenance or policy.require_trace)
        and not is_nonblank_string(pheromone_source_id(trail))
    ):
        raise GovernanceError("active pheromone trail requires a non-blank source identity")
    _non_negative_step(trail.deposited_at_step, "pheromone deposited_at_step")
    _non_negative_step(trail.updated_at_step, "pheromone updated_at_step")
    if trail.updated_at_step < trail.deposited_at_step:
        raise GovernanceError("pheromone updated step must not precede deposit step")
    if trail.ttl_steps is not None:
        _non_negative_step(trail.ttl_steps, "pheromone ttl_steps")
    if any(not is_nonblank_string(item) for item in trail.lineage_event_ids):
        raise GovernanceError("pheromone lineage_event_ids must be non-empty strings")
    if len(set(trail.lineage_event_ids)) != len(trail.lineage_event_ids):
        raise GovernanceError("pheromone lineage_event_ids must not contain duplicates")
    _non_negative_step(trail.diffusion_hop, "pheromone diffusion_hop")
    if trail.diffusion_hop == 0:
        if trail.diffusion_root_trace_event_id or trail.diffusion_parent_trace_event_id:
            raise GovernanceError("root pheromone trail cannot declare diffusion lineage")
    elif not (
        is_nonblank_string(trail.diffusion_root_trace_event_id)
        and is_nonblank_string(trail.diffusion_parent_trace_event_id)
    ):
        raise GovernanceError("derived pheromone trail requires explicit diffusion lineage")
    elif (
        trail.diffusion_root_trace_event_id not in trail.lineage_event_ids
        or trail.diffusion_parent_trace_event_id not in trail.lineage_event_ids
        or trail.trace_event_id == trail.diffusion_root_trace_event_id
    ):
        raise GovernanceError("derived pheromone trail diffusion lineage is inconsistent")


def pheromone_subject_type(trail: PheromoneTrail) -> str:
    if trail.subject_id:
        return trail.subject_type
    if trail.candidate_id:
        return "candidate"
    if trail.route_id:
        return "route"
    if trail.tool_id:
        return "tool"
    return trail.subject_type


def pheromone_subject_id(trail: PheromoneTrail) -> str:
    if trail.subject_id:
        return trail.subject_id
    if trail.candidate_id:
        return trail.candidate_id
    if trail.route_id:
        return trail.route_id
    if trail.tool_id:
        return trail.tool_id
    return ""


def pheromone_candidate_id(trail: PheromoneTrail) -> str:
    subject_type = pheromone_subject_type(trail)
    if subject_type != "candidate":
        return ""
    return pheromone_subject_id(trail)


def pheromone_bound_candidate_id(trail: PheromoneTrail) -> str:
    return trail.candidate_id or pheromone_candidate_id(trail)


def pheromone_lineage(
    trail: PheromoneTrail,
    *,
    old_strength: float | None = None,
    new_strength: float | None = None,
    step: int | None = None,
    score_delta: float | None = None,
    score_breakdown: dict[str, float] | None = None,
    fallback_used: bool | None = None,
    resolution: str = "",
) -> dict[str, Any]:
    lineage: dict[str, Any] = {
        "candidate_id": pheromone_bound_candidate_id(trail),
        "subject_type": pheromone_subject_type(trail),
        "subject_id": pheromone_subject_id(trail),
        "kind": trail.kind,
        "source_id": trail.source_id,
        "evidence_id": trail.evidence_id,
        "provenance": trail.provenance,
        "trace_event_id": trail.trace_event_id,
        "lineage_event_ids": list(trail.lineage_event_ids),
        "new_strength": trail.strength if new_strength is None else new_strength,
        "step": trail.updated_at_step if step is None else step,
    }
    if trail.target:
        lineage["target"] = trail.target
    if old_strength is not None:
        lineage["old_strength"] = old_strength
    if score_delta is not None:
        lineage["score_delta"] = score_delta
    if score_breakdown is not None:
        lineage["score_breakdown"] = dict(score_breakdown)
    if fallback_used is not None:
        lineage["fallback_used"] = fallback_used
    if resolution:
        lineage["resolution"] = resolution
    return lineage


def scoreable_pheromone_candidate_id(trail: PheromoneTrail, policy: PheromonePolicy) -> str:
    if trail.kind == "stale":
        return ""
    if trail.kind == "novelty" and not policy.exploration_enabled:
        return ""
    subject_type = pheromone_subject_type(trail)
    if subject_type == "evidence":
        return ""
    profile = policy.kind_profiles.get(trail.kind)
    scored_subject_types = effective_pheromone_scored_subject_types(
        trail.kind,
        profile,
        policy.scored_subject_types,
    )
    if subject_type not in scored_subject_types:
        return ""
    if subject_type == "candidate":
        return pheromone_candidate_id(trail)
    return trail.candidate_id


def pheromone_source_id(trail: PheromoneTrail) -> str:
    return trail.source_id or trail.provenance or ""


_DEFAULT_KIND_PRIORITY = {
    "alarm": 5,
    "cautionary": 4,
    "negative": 3,
    "positive": 2,
    "novelty": 1,
    "stale": 0,
}


def pheromone_kind_priority(trail: PheromoneTrail, policy: PheromonePolicy) -> int:
    profile = policy.kind_profiles.get(trail.kind)
    if profile is not None:
        return profile.priority
    return _DEFAULT_KIND_PRIORITY.get(trail.kind, -1)


def pheromone_processing_key(
    trail: PheromoneTrail,
    original_index: int,
    policy: PheromonePolicy,
) -> tuple[object, ...]:
    return (
        -pheromone_kind_priority(trail, policy),
        trail.target,
        pheromone_bound_candidate_id(trail),
        pheromone_subject_type(trail),
        pheromone_subject_id(trail),
        pheromone_source_id(trail),
        trail.kind,
        trail.trace_event_id,
        original_index,
    )


def _trail_clip_payload(trail: PheromoneTrail) -> dict[str, Any]:
    """Snapshot every public trail input field for a deterministic receipt."""

    return {
        "candidate_id": trail.candidate_id,
        "strength": float(trail.strength),
        "subject_type": trail.subject_type,
        "subject_id": trail.subject_id,
        "target": trail.target,
        "route_id": trail.route_id,
        "tool_id": trail.tool_id,
        "kind": trail.kind,
        "source_id": trail.source_id,
        "source_role": trail.source_role,
        "evidence_id": trail.evidence_id,
        "provenance": trail.provenance,
        "trace_event_id": trail.trace_event_id,
        "deposited_at_step": trail.deposited_at_step,
        "updated_at_step": trail.updated_at_step,
        "ttl_steps": trail.ttl_steps,
        "lineage_event_ids": list(trail.lineage_event_ids),
        "diffusion_root_trace_event_id": trail.diffusion_root_trace_event_id,
        "diffusion_parent_trace_event_id": trail.diffusion_parent_trace_event_id,
        "diffusion_hop": trail.diffusion_hop,
    }


def legacy_pheromone_weight(kind: str, policy: PheromonePolicy) -> float:
    if kind == "positive":
        return policy.positive_weight
    if kind == "negative":
        return policy.negative_weight
    if kind == "cautionary":
        return policy.cautionary_weight
    if kind == "alarm":
        return policy.cautionary_weight
    if kind == "novelty":
        return policy.novelty_weight
    return 0.0


def validate_pheromone_topology(
    neighborhood: PheromoneNeighborhood,
    *,
    candidate_set: CandidateSet | None = None,
    target: str | None = None,
) -> None:
    subjects: dict[tuple[str, str], PheromoneSubject] = {}
    for subject in neighborhood.subjects:
        for field_name in ("subject_type", "subject_id", "candidate_id", "target"):
            if not isinstance(getattr(subject, field_name), str):
                raise GovernanceError(f"pheromone topology subject {field_name} must be a string")
        for field_name in ("candidate_id", "target"):
            value = getattr(subject, field_name)
            if value and not is_nonblank_string(value):
                raise GovernanceError(
                    f"pheromone topology subject {field_name} must be non-blank when declared"
                )
        if not isinstance(subject.subject_type, str) or (
            subject.subject_type not in SUPPORTED_PHEROMONE_SUBJECT_TYPES
            and not is_extension_pheromone_value(subject.subject_type)
        ):
            raise GovernanceError(f"unsupported pheromone subject type: {subject.subject_type}")
        if not is_nonblank_string(subject.subject_id):
            raise GovernanceError("pheromone topology subject_id is required")
        key = subject_key(subject.subject_type, subject.subject_id)
        if key in subjects:
            raise GovernanceError(f"duplicate pheromone topology subject: {subject.subject_type}:{subject.subject_id}")
        subjects[key] = subject
        candidate_id = topology_subject_candidate_id(subject)
        if subject.subject_type == "candidate" and candidate_id != subject.subject_id:
            raise GovernanceError("candidate topology subject_id must match candidate_id")
        if subject.subject_type != "candidate" and not is_nonblank_string(subject.candidate_id):
            raise GovernanceError(
                "non-candidate pheromone topology subject must declare candidate_id"
            )
        if candidate_id and candidate_set is not None:
            candidate = candidate_set.require_declared(candidate_id)
            if subject.target and candidate.target != subject.target:
                raise GovernanceError(
                    f"pheromone topology subject targets {subject.target}, not candidate target {candidate.target}"
                )
            if target is not None and candidate.target != target:
                raise GovernanceError(
                    f"pheromone topology subject candidate targets {candidate.target}, not active target {target}"
                )
        resolved_target = topology_subject_target(subject, candidate_set)
        if target is not None:
            if not resolved_target:
                raise GovernanceError("target-scoped pheromone topology subject must declare target or candidate binding")
            if resolved_target != target:
                raise GovernanceError(
                    f"pheromone topology subject targets {resolved_target}, not active target {target}"
                )
    seen_edges: set[tuple[tuple[str, str], tuple[str, str]]] = set()
    for edge in neighborhood.edges:
        for field_name in (
            "source_subject_type",
            "source_subject_id",
            "target_subject_type",
            "target_subject_id",
        ):
            if not is_nonblank_string(getattr(edge, field_name)):
                raise GovernanceError(f"pheromone edge {field_name} must be a non-empty string")
        if not isinstance(edge.source_subject_type, str) or (
            edge.source_subject_type not in SUPPORTED_PHEROMONE_SUBJECT_TYPES
            and not is_extension_pheromone_value(edge.source_subject_type)
        ):
            raise GovernanceError(f"unsupported pheromone edge source type: {edge.source_subject_type}")
        if not isinstance(edge.target_subject_type, str) or (
            edge.target_subject_type not in SUPPORTED_PHEROMONE_SUBJECT_TYPES
            and not is_extension_pheromone_value(edge.target_subject_type)
        ):
            raise GovernanceError(f"unsupported pheromone edge target type: {edge.target_subject_type}")
        attenuation = _finite_number(edge.attenuation, "pheromone edge attenuation")
        if not 0 <= attenuation <= 1:
            raise GovernanceError("pheromone edge attenuation must be between 0 and 1")
        source = subject_key(edge.source_subject_type, edge.source_subject_id)
        destination = subject_key(edge.target_subject_type, edge.target_subject_id)
        if source not in subjects or destination not in subjects:
            raise GovernanceError("pheromone edge must reference declared topology subjects")
        edge_identity = (source, destination)
        if edge_identity in seen_edges:
            raise GovernanceError("duplicate pheromone topology edge")
        seen_edges.add(edge_identity)
        source_target = topology_subject_target(subjects[source], candidate_set)
        destination_target = topology_subject_target(subjects[destination], candidate_set)
        if source_target and destination_target and source_target != destination_target:
            raise GovernanceError(
                f"pheromone edge crosses targets: {source_target} -> {destination_target}"
            )


def topology_subject_candidate_id(subject: PheromoneSubject) -> str:
    if subject.candidate_id:
        return subject.candidate_id
    if subject.subject_type == "candidate":
        return subject.subject_id
    return ""


def topology_subject_target(
    subject: PheromoneSubject,
    candidate_set: CandidateSet | None,
) -> str:
    if subject.target:
        return subject.target
    candidate_id = topology_subject_candidate_id(subject)
    if candidate_id and candidate_set is not None:
        return candidate_set.require_declared(candidate_id).target
    return ""


def validate_pheromone_subject_binding(
    neighborhood: PheromoneNeighborhood,
    *,
    subject_type: str,
    subject_id: str,
    candidate_id: str,
    require_declared: bool,
) -> None:
    """Require one topology key to have one explicit candidate meaning.

    Subject keys are the topology identity.  Letting a route/tool/agent key
    inherit whichever candidate happens to reach it makes diffusion order an
    authority input, so connected or scored subjects must use their declared
    binding instead.
    """

    key = subject_key(subject_type, subject_id)
    subjects = {
        subject_key(subject.subject_type, subject.subject_id): subject
        for subject in neighborhood.subjects
    }
    subject = subjects.get(key)
    if subject is None:
        if require_declared:
            raise GovernanceError(
                f"pheromone subject is not declared in topology: {subject_type}:{subject_id}"
            )
        return
    declared_candidate_id = topology_subject_candidate_id(subject)
    if not declared_candidate_id:
        raise GovernanceError(
            f"pheromone topology subject has no candidate binding: {subject_type}:{subject_id}"
        )
    if candidate_id != declared_candidate_id:
        raise GovernanceError(
            "pheromone subject candidate binding does not match topology: "
            f"{subject_type}:{subject_id} binds {declared_candidate_id}, not {candidate_id}"
        )


def subject_key(subject_type: str, subject_id: str) -> tuple[str, str]:
    return subject_type, subject_id


def is_extension_pheromone_value(value: str) -> bool:
    return isinstance(value, str) and any(
        value.startswith(prefix) and len(value) > len(prefix)
        for prefix in PHEROMONE_EXTENSION_PREFIXES
    )


for _compat_function in (pheromone_policy_from_collective, canonical_pheromone_kind_profiles, normalize_legacy_pheromone_trail, diffusion_policy_from_collective, _finite_number, _non_negative_number, _non_negative_step, validate_pheromone_policy, validate_pheromone_diffusion_policy, clip_pheromone_strength, validate_pheromone_trail, pheromone_subject_type, pheromone_subject_id, pheromone_candidate_id, pheromone_bound_candidate_id, pheromone_lineage, scoreable_pheromone_candidate_id, pheromone_source_id, pheromone_kind_priority, pheromone_processing_key, _trail_clip_payload, legacy_pheromone_weight, validate_pheromone_topology, topology_subject_candidate_id, topology_subject_target, validate_pheromone_subject_binding, subject_key, is_extension_pheromone_value,):
    _compat_function.__module__ = 'pheroos.governance.pheromone'
del _compat_function

__all__ = ('_DEFAULT_KIND_PRIORITY', '_finite_number', '_non_negative_number', '_non_negative_step', '_trail_clip_payload', 'canonical_pheromone_kind_profiles', 'clip_pheromone_strength', 'diffusion_policy_from_collective', 'is_extension_pheromone_value', 'legacy_pheromone_weight', 'normalize_legacy_pheromone_trail', 'pheromone_bound_candidate_id', 'pheromone_candidate_id', 'pheromone_kind_priority', 'pheromone_lineage', 'pheromone_policy_from_collective', 'pheromone_processing_key', 'pheromone_source_id', 'pheromone_subject_id', 'pheromone_subject_type', 'scoreable_pheromone_candidate_id', 'subject_key', 'topology_subject_candidate_id', 'topology_subject_target', 'validate_pheromone_diffusion_policy', 'validate_pheromone_policy', 'validate_pheromone_subject_binding', 'validate_pheromone_topology', 'validate_pheromone_trail')
