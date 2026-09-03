from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import replace
from typing import Any, cast

import pytest

from pheroos.conformance.checks import hybrid_trace_contract
from pheroos.governance._swarm.replay import replay_state_from_hybrid_step
from pheroos.protocol import load_capability_manifest
from pheroos.trace import TraceEvent
from pheroos.trace._pheromone_receipts import (
    canonical_pheromone_clip_payload,
    pheromone_clip_payload_fingerprint,
)


@pytest.fixture(scope="module")
def hybrid_events() -> tuple[TraceEvent, ...]:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, _output = hybrid_trace_contract.manifest_replay(manifest)
    events = tuple(step.trace_events)
    for lifecycle in ("deposit", "diffusion", "feedback"):
        _clip(events, lifecycle).validate()
    return events


@pytest.fixture(scope="module")
def replay_event() -> TraceEvent:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    first, _output = hybrid_trace_contract.manifest_replay(manifest)
    second, _output = hybrid_trace_contract.manifest_replay(
        manifest,
        replay_state=replay_state_from_hybrid_step(first),
    )
    event = next(
        item
        for item in second.trace_events
        if item.event_type == "pheromone_observe"
        and item.lineage.get("result") == "replay_ignored"
    )
    event.validate()
    return event


@pytest.fixture(scope="module")
def replay_adjustment_event() -> TraceEvent:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    first, _output = hybrid_trace_contract.manifest_replay(manifest)
    second, _output = hybrid_trace_contract.manifest_replay(
        manifest,
        replay_state=replay_state_from_hybrid_step(first),
    )
    event = next(
        item
        for item in second.trace_events
        if item.event_type == "policy_adjustment"
        and item.lineage.get("result") == "replay_ignored"
    )
    event.validate()
    return event


def _clip(events: tuple[TraceEvent, ...], lifecycle: str) -> TraceEvent:
    return next(
        event
        for event in events
        if event.event_type == "pheromone_clip"
        and event.lineage.get("lifecycle") == lifecycle
    )


def _with_lineage(event: TraceEvent, **updates: object) -> TraceEvent:
    lineage = deepcopy(dict(event.lineage))
    lineage.update(updates)
    return replace(event, lineage=lineage)


def _without_lineage(event: TraceEvent, field_name: str) -> TraceEvent:
    lineage = deepcopy(dict(event.lineage))
    lineage.pop(field_name)
    return replace(event, lineage=lineage)


def _with_causal_mutation(
    event: TraceEvent,
    mutate: Callable[[dict[str, Any]], None],
    *,
    target: str | None = None,
) -> TraceEvent:
    lineage = deepcopy(dict(event.lineage))
    payload = cast(dict[str, Any], lineage["causal_payload"])
    mutate(payload)
    lineage["causal_fingerprint"] = pheromone_clip_payload_fingerprint(payload)
    return replace(
        event,
        target=event.target if target is None else target,
        lineage=lineage,
    )


def _assert_invalid(event: TraceEvent, error: str) -> None:
    with pytest.raises((TypeError, ValueError), match=error):
        event.validate()


def test_clip_common_transition_and_outcome_mutations_fail_closed(
    hybrid_events: tuple[TraceEvent, ...],
) -> None:
    deposit = _clip(hybrid_events, "deposit")
    diffusion = _clip(hybrid_events, "diffusion")
    feedback = _clip(hybrid_events, "feedback")
    cases = (
        (_with_lineage(deposit, lifecycle="unknown"), "lifecycle is unsupported"),
        (_with_lineage(deposit, result="unknown"), "result is unsupported"),
        (
            _with_lineage(deposit, applied_strength=12.0),
            "must not exceed requested",
        ),
        (
            _with_lineage(diffusion, applied_strength=0.1),
            "rejected pheromone_clip trace must apply zero",
        ),
        (
            _with_lineage(deposit, applied_strength=0.0, new_strength=0.0),
            "applied pheromone_clip trace must apply positive",
        ),
        (
            _with_lineage(deposit, causal_payload=None),
            "must be declared together",
        ),
        (
            _with_lineage(deposit, causal_payload=["not", "an", "object"]),
            "causal_payload must be an object",
        ),
        (
            _with_lineage(deposit, causal_fingerprint=""),
            "causal_fingerprint must be a non-empty string",
        ),
        (_without_lineage(deposit, "source_kind"), "missing required fields"),
        (
            _with_lineage(deposit, source_strength=0.1),
            "does not reconstruct transition",
        ),
        (_without_lineage(diffusion, "hop"), "missing required fields"),
        (
            _with_lineage(diffusion, attenuation=1.1),
            "attenuation must be between zero and one",
        ),
        (
            _with_lineage(diffusion, attenuation=0.4),
            "attenuation factors do not reconstruct",
        ),
        (
            _with_lineage(diffusion, requested_strength=0.1),
            "request is not causally derived",
        ),
        (
            _with_lineage(diffusion, new_strength=0.1),
            "must record a rejected transition",
        ),
        (_without_lineage(feedback, "outcome"), "missing required fields"),
        (
            _without_lineage(feedback, "strength_delta"),
            "missing required field: strength_delta",
        ),
        (
            _with_lineage(feedback, new_strength=0.1),
            "must record an unchanged rejected transition",
        ),
    )
    for event, error in cases:
        _assert_invalid(event, error)


def test_clip_causal_lifecycle_must_match_reported_lifecycle(
    hybrid_events: tuple[TraceEvent, ...],
) -> None:
    event = _with_causal_mutation(
        _clip(hybrid_events, "deposit"),
        lambda payload: payload.__setitem__("lifecycle", "feedback"),
    )
    _assert_invalid(event, "causal payload lifecycle does not match")


def test_deposit_trail_payload_variants_are_canonical_and_total(
    hybrid_events: tuple[TraceEvent, ...],
) -> None:
    deposit = _clip(hybrid_events, "deposit")

    def set_effective_subject(
        payload: dict[str, Any],
        *,
        subject_type: str,
        subject_id: str,
        candidate_id: str,
    ) -> None:
        item = payload["input"]
        item.update(
            subject_type=subject_type,
            subject_id=subject_id,
            candidate_id=candidate_id,
            route_id="",
            tool_id="",
        )
        effective = payload["effective"]
        effective.update(
            subject_type=subject_type,
            subject_id=subject_id,
            candidate_id=candidate_id,
        )

    candidate = _with_causal_mutation(
        deposit,
        lambda payload: set_effective_subject(
            payload,
            subject_type="candidate",
            subject_id="candidate:alpha",
            candidate_id="candidate:alpha",
        ),
    )
    candidate = _with_lineage(
        candidate,
        candidate_id="candidate:alpha",
        subject_type="candidate",
        subject_id="candidate:alpha",
    )
    candidate.validate()

    candidate_from_subject = _with_causal_mutation(
        deposit,
        lambda payload: (
            payload["input"].update(
                subject_type="candidate",
                subject_id="candidate:alpha",
                candidate_id="",
                route_id="",
                tool_id="",
            ),
            payload["effective"].update(
                subject_type="candidate",
                subject_id="candidate:alpha",
                candidate_id="candidate:alpha",
            ),
        ),
    )
    candidate_from_subject = _with_lineage(
        candidate_from_subject,
        candidate_id="candidate:alpha",
        subject_type="candidate",
        subject_id="candidate:alpha",
    )
    candidate_from_subject.validate()

    candidate_from_empty_subject = _with_causal_mutation(
        deposit,
        lambda payload: (
            payload["input"].update(
                subject_type="route",
                subject_id="",
                candidate_id="candidate:alpha",
                route_id="",
                tool_id="",
            ),
            payload["effective"].update(
                subject_type="candidate",
                subject_id="candidate:alpha",
                candidate_id="candidate:alpha",
            ),
        ),
    )
    candidate_from_empty_subject = _with_lineage(
        candidate_from_empty_subject,
        candidate_id="candidate:alpha",
        subject_type="candidate",
        subject_id="candidate:alpha",
    )
    candidate_from_empty_subject.validate()

    route = _with_causal_mutation(
        deposit,
        lambda payload: (
            payload["input"].update(
                subject_id="",
                candidate_id="",
                route_id="route:alternate",
                tool_id="",
            ),
            payload["effective"].update(
                subject_type="route",
                subject_id="route:alternate",
                candidate_id="candidate:alpha",
            ),
        ),
    )
    route = _with_lineage(
        route,
        subject_type="route",
        subject_id="route:alternate",
    )
    _assert_invalid(route, "effective binding does not match input trail")

    tool = _with_causal_mutation(
        deposit,
        lambda payload: (
            payload["input"].update(
                subject_id="",
                candidate_id="",
                route_id="",
                tool_id="tool:alternate",
            ),
            payload["effective"].update(
                subject_type="tool",
                subject_id="tool:alternate",
                candidate_id="candidate:alpha",
            ),
        ),
    )
    tool = _with_lineage(
        tool,
        subject_type="tool",
        subject_id="tool:alternate",
    )
    _assert_invalid(tool, "effective binding does not match input trail")

    provenance_source = _with_causal_mutation(
        deposit,
        lambda payload: (
            payload["input"].__setitem__("source_id", ""),
            payload["effective"].__setitem__(
                "source_id", payload["input"]["provenance"]
            ),
        ),
    )
    provenance_source = _with_lineage(
        provenance_source,
        source_id=provenance_source.lineage["provenance"],
    )
    provenance_source.validate()

    no_subject = _with_causal_mutation(
        deposit,
        lambda payload: (
            payload["input"].update(
                subject_id="",
                candidate_id="",
                route_id="",
                tool_id="",
            ),
            payload["effective"].update(
                subject_type=payload["input"]["subject_type"],
                subject_id="still-not-derived",
                candidate_id="candidate:alpha",
            ),
        ),
    )
    _assert_invalid(no_subject, "effective binding does not match input trail")


def test_deposit_causal_payload_shape_and_trail_mutations_fail_closed(
    hybrid_events: tuple[TraceEvent, ...],
) -> None:
    deposit = _clip(hybrid_events, "deposit")
    mutations: tuple[tuple[Callable[[dict[str, Any]], None], str], ...] = (
        (lambda payload: payload.__setitem__("extra", True), "fields do not match"),
        (lambda payload: payload.__setitem__("input", []), "must be an object"),
        (
            lambda payload: payload["input"].__setitem__("extra", True),
            "fields do not match",
        ),
        (
            lambda payload: payload["input"].__setitem__("subject_type", ""),
            "subject_type must be non-empty",
        ),
        (
            lambda payload: payload["input"].__setitem__("ttl_steps", True),
            "ttl_steps must be null or a non-negative integer",
        ),
        (
            lambda payload: payload["input"].__setitem__(
                "lineage_event_ids", "trace:not-an-array"
            ),
            "lineage_event_ids must be an array",
        ),
        (
            lambda payload: payload["input"].__setitem__("lineage_event_ids", []),
            "must contain trace_event_id",
        ),
        (
            lambda payload: payload["effective"].__setitem__("extra", True),
            "fields do not match",
        ),
        (
            lambda payload: payload["effective"].__setitem__("source_id", ""),
            "must be a non-empty string",
        ),
        (
            lambda payload: payload["effective"].__setitem__(
                "candidate_id", "candidate:forged"
            ),
            "effective binding does not match input trail",
        ),
    )
    for mutate, error in mutations:
        _assert_invalid(_with_causal_mutation(deposit, mutate), error)


def test_feedback_causal_semantics_fail_closed_after_digest_recomputation(
    hybrid_events: tuple[TraceEvent, ...],
) -> None:
    feedback = _clip(hybrid_events, "feedback")
    mutations: tuple[tuple[Callable[[dict[str, Any]], None], str], ...] = (
        (
            lambda payload: payload["input"].__setitem__("strength_delta", -0.1),
            "strength_delta must be non-negative",
        ),
        (
            lambda payload: payload["source_state"].__setitem__(
                "trace_event_id", "trace:forged"
            ),
            "new-memory source state does not match input",
        ),
    )
    for mutate, error in mutations:
        _assert_invalid(_with_causal_mutation(feedback, mutate), error)

    established = _with_causal_mutation(
        feedback,
        lambda payload: payload["source_state"].__setitem__("strength", 1.0),
    )
    established = _with_lineage(established, source_strength=1.0, new_strength=1.0)
    established.validate()

    wrong_target = _with_causal_mutation(
        feedback,
        lambda _payload: None,
        target="decision:forged",
    )
    _assert_invalid(wrong_target, "target does not match causal input")


def test_diffusion_causal_semantics_fail_closed_after_digest_recomputation(
    hybrid_events: tuple[TraceEvent, ...],
) -> None:
    diffusion = _clip(hybrid_events, "diffusion")
    mutations: tuple[tuple[Callable[[dict[str, Any]], None], str], ...] = (
        (
            lambda payload: payload["effective"].__setitem__(
                "source_id", "source:forged"
            ),
            "effective binding does not match input",
        ),
        (
            lambda payload: payload["input"].__setitem__("policy_attenuation", 1.1),
            "attenuation must be between zero and one",
        ),
        (
            lambda payload: payload["input"]["edge"].__setitem__(
                "source_subject_id", "route:forged"
            ),
            "topology does not match input trail",
        ),
    )
    for mutate, error in mutations:
        _assert_invalid(_with_causal_mutation(diffusion, mutate), error)

    wrong_target = _with_causal_mutation(
        diffusion,
        lambda _payload: None,
        target="decision:forged",
    )
    _assert_invalid(wrong_target, "target does not match causal payload")


def test_clip_payload_canonicalizer_rejects_invalid_nested_keys_and_values() -> None:
    for payload, error in (
        (cast(Mapping[str, object], {"": 1}), "keys must be non-empty strings"),
        (
            cast(Mapping[str, object], {1: "not-a-string-key"}),
            "keys must be non-empty strings",
        ),
        ({"nested": object()}, "unsupported value type"),
    ):
        with pytest.raises((TypeError, ValueError), match=error):
            canonical_pheromone_clip_payload(payload)


def test_processed_replay_receipt_shapes_fail_closed(
    hybrid_events: tuple[TraceEvent, ...],
) -> None:
    score = next(
        event for event in hybrid_events if event.event_type == "pheromone_score"
    )
    fingerprint = "sha256:" + "1" * 64

    def mutated_receipts(mutate: Callable[[dict[str, Any]], None]) -> TraceEvent:
        lineage = deepcopy(dict(score.lineage))
        receipts = cast(dict[str, Any], lineage["processed_replay_receipts"])
        mutate(receipts)
        return replace(score, lineage=lineage)

    cases = (
        (_with_lineage(score, processed_replay_receipts=[]), "must contain exactly"),
        (
            mutated_receipts(lambda receipts: receipts.__setitem__("deposit", [])),
            "deposit must be an object",
        ),
        (
            mutated_receipts(
                lambda receipts: receipts["deposit"].__setitem__("", fingerprint)
            ),
            "ids must be non-empty strings",
        ),
        (
            mutated_receipts(
                lambda receipts: (
                    receipts["deposit"].__setitem__("trace:duplicate", fingerprint),
                    receipts["feedback"].__setitem__("trace:duplicate", fingerprint),
                )
            ),
            "must be unique across lifecycles",
        ),
        (
            mutated_receipts(
                lambda receipts: receipts["deposit"].__setitem__(
                    "trace:bad-fingerprint", "not-a-fingerprint"
                )
            ),
            "must be a sha256 fingerprint",
        ),
    )
    for event, error in cases:
        _assert_invalid(event, error)


def test_replay_receipt_fingerprint_failures_are_total(
    replay_event: TraceEvent,
    replay_adjustment_event: TraceEvent,
) -> None:
    expected = cast(str, replay_event.lineage["replay_payload_fingerprint"])
    other = "sha256:" + ("f" * 64)
    cases = (
        (_with_lineage(replay_event, replay_payload={}), "must be a non-empty array"),
        (
            _without_lineage(replay_event, "replay_payload_fingerprint"),
            "missing required field",
        ),
        (
            _with_lineage(replay_event, replay_payload_fingerprint=other),
            "fingerprint does not match replay_payload",
        ),
        (
            _with_lineage(
                replay_event,
                replay_payload_fingerprint=expected,
                processed_payload_fingerprint=other,
            ),
            "does not match processed receipt",
        ),
        (
            _with_lineage(
                replay_event,
                replay_payload_fingerprint="not-a-fingerprint",
            ),
            "must be a sha256 fingerprint",
        ),
    )
    for event, error in cases:
        _assert_invalid(event, error)

    _assert_invalid(
        _without_lineage(replay_adjustment_event, "processed_payload_fingerprint"),
        "missing required field",
    )
