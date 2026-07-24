"""Private Commit TCK reference mutation handlers."""

from __future__ import annotations

from collections.abc import Sequence

from copy import deepcopy

from dataclasses import replace

from typing import Any

from pheroos.conformance._commit_reference import (
    ReferenceScenario,
    assess_reference_scenario,
)
from pheroos.conformance._commit_reference_typing import collective_commit_policy

from pheroos.conformance._commit_tck.models import (
    object_value as _object,
    text_value as _text,
)

from pheroos.conformance.commit_tck_v2_protocol import (
    CommitTckRequest as _CommitTckRequest,
)

from pheroos.governance.commit_state import (
    CommitFinalityStatus,
    DecisionOutcome,
    reduce_commit_liveness,
)

from pheroos.conformance._commit_tck_reference.liveness import (
    _initialize_window,
    _liveness_input,
)

from pheroos.conformance._commit_tck_reference.state import (
    advance_commit_window_state,
)


def _scalar_leaf_paths(value: object, prefix: tuple[object, ...] = ()) -> Any:
    if isinstance(value, dict):
        for key in sorted(value):
            yield from _scalar_leaf_paths(value[key], (*prefix, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _scalar_leaf_paths(item, (*prefix, index))
    elif value is None or type(value) in {bool, int, str}:
        yield prefix


def _mutate_scalar(value: Any) -> Any:
    if value is None:
        return "tck-mutated"
    if type(value) is bool:
        return not value
    if type(value) is int:
        return value + 1
    if isinstance(value, str):
        if value.startswith("sha256:") and len(value) == 71:
            replacement = "0" if value[-1] != "0" else "1"
            return value[:-1] + replacement
        return value + ":tck-mutated"
    raise ValueError("TCK mutation selected a non-scalar leaf")


def _mutate_path(payload: dict[str, Any], path: Sequence[object]) -> None:
    parent: Any = payload
    for component in path[:-1]:
        parent = parent[component]
    key = path[-1]
    parent[key] = _mutate_scalar(parent[key])


def _terminal_variant_vector(
    vector: _CommitTckRequest,
    key: str,
) -> _CommitTckRequest:
    variants = _object(
        vector.inputs.get("terminal_variants"),
        "case 33 terminal_variants",
    )
    spec = _object(variants.get(key), f"case 33 terminal variant {key}")
    manifest = _object(spec.get("manifest"), f"case 33 {key} manifest")
    profile = _text(spec.get("profile"), f"case 33 {key} profile")
    return replace(
        vector,
        id=f"{vector.id}:{key}",
        manifest=deepcopy(manifest),
        profile=profile,
    )


def _coded_terminal_outcome(
    scenario: ReferenceScenario,
    *,
    suffix: str,
    invalid: Sequence[str] = (),
    safety: Sequence[str] = (),
    blocked: Sequence[str] = (),
) -> DecisionOutcome:
    window = _initialize_window(scenario)
    assessment = assess_reference_scenario(
        scenario,
        step=5,
        suffix=f"{suffix}:assessment",
    )
    window = advance_commit_window_state(
        window,
        assessment=assessment,
        commit_policy=collective_commit_policy(scenario.policy),
        threshold_snapshot=scenario.threshold,
        current_step=5,
    )
    decision = reduce_commit_liveness(
        window,
        commit_policy=collective_commit_policy(scenario.policy),
        liveness_input=_liveness_input(
            scenario,
            window,
            assessment=assessment,
            step=5,
            suffix=suffix,
            finality_status=CommitFinalityStatus.PENDING,
            invalid_reason_codes=invalid,
            safety_violation_reason_codes=safety,
            blocked_reason_codes=blocked,
        ),
    )
    if type(decision) is not DecisionOutcome:
        raise ValueError(f"{suffix} did not reduce to a terminal outcome")
    return decision
