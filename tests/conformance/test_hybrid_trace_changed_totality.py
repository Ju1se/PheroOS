"""Changed-line totality tests for the decomposed Hybrid Trace checker.

The large, scenario-oriented Hybrid Trace contract suite remains the canonical
source of real replay/tamper cases.  This module deliberately re-executes that
corpus as one coverage-locked regression matrix so changes to the private
checker decomposition cannot silently fall outside the production gate.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import inspect
from types import SimpleNamespace
from typing import Any

import pytest

from pheroos.conformance.checks import hybrid_trace_contract
from pheroos.conformance.checks import _hybrid_trace_authority as _authority
from pheroos.conformance.checks import _hybrid_trace_coordination as _coordination
from pheroos.conformance.checks import _hybrid_trace_entry as _entry
from pheroos.conformance.checks import _hybrid_trace_lifecycle as _lifecycle
from pheroos.conformance.checks import (
    _hybrid_trace_lifecycle_clips as _lifecycle_clips,
)
from pheroos.conformance.checks import (
    _hybrid_trace_lifecycle_state as _lifecycle_state,
)
from pheroos.conformance.checks import (
    _hybrid_trace_lifecycle_transitions as _lifecycle_transitions,
)
from pheroos.conformance.checks import _hybrid_trace_receipts as _receipts
from pheroos.conformance.checks import _hybrid_trace_replay as _replay
from pheroos.conformance.checks import _hybrid_trace_score as _score
from pheroos.conformance.checks import _hybrid_trace_shared as _shared
from pheroos.conformance.report import CheckResult
from pheroos.governance._swarm.replay import replay_state_from_hybrid_step
from pheroos.protocol import load_capability_manifest
from pheroos.trace import TraceEvent
from tests.conformance import test_swarm_protocol_conformance as _scenario_corpus


_PARAMETERIZED_SCENARIOS = {
    "test_rejected_deposit_clip_receipt_rejects_reported_single_field_mutations",
    "test_rejected_deposit_clip_requires_both_receipt_fields",
    "test_rejected_diffusion_clip_requires_both_receipt_fields",
    "test_rejected_feedback_clip_receipt_rejects_reported_single_field_mutations",
    "test_rejected_feedback_clip_requires_both_receipt_fields",
}

_REAL_HYBRID_TRACE_SCENARIOS = tuple(
    (name, function)
    for name, function in inspect.getmembers(_scenario_corpus, inspect.isfunction)
    if name.startswith("test_hybrid_trace")
    and name not in _PARAMETERIZED_SCENARIOS
    and not inspect.signature(function).parameters
) + tuple(
    (name, function)
    for name, function in inspect.getmembers(_scenario_corpus, inspect.isfunction)
    if name.startswith("test_rejected_")
    and name not in _PARAMETERIZED_SCENARIOS
    and not inspect.signature(function).parameters
)


def _hybrid_replay(
    *,
    force_fallback: bool = False,
) -> tuple[Any, Any, list[TraceEvent], TraceEvent]:
    manifest = load_capability_manifest(
        "examples/hybrid-pheromone-protocol/capability.json"
    )
    step, output = hybrid_trace_contract.manifest_replay(
        manifest,
        force_fallback=force_fallback,
    )
    return manifest, step, [*step.trace_events, output], output


def _event_index(events: list[TraceEvent], event_type: str, occurrence: int = 0) -> int:
    return [
        index for index, event in enumerate(events) if event.event_type == event_type
    ][occurrence]


def _with_lineage(event: TraceEvent, **changes: Any) -> TraceEvent:
    lineage = deepcopy(dict(event.lineage))
    lineage.update(changes)
    return replace(event, lineage=lineage)


@pytest.mark.parametrize(
    ("scenario_name", "scenario"),
    _REAL_HYBRID_TRACE_SCENARIOS,
    ids=[name.removeprefix("test_") for name, _ in _REAL_HYBRID_TRACE_SCENARIOS],
)
def test_hybrid_trace_real_scenario_corpus(
    scenario_name: str,
    scenario: object,
) -> None:
    """Run each established real replay/tamper scenario under this gate."""

    assert scenario_name.startswith(("test_hybrid_trace", "test_rejected_"))
    assert callable(scenario)
    scenario()


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    [
        ("source_id", "source:forged"),
        ("provenance", "forged:provenance"),
        ("subject_id", "route:forged"),
        ("reward", 0.125),
        ("strength_delta", 0.125),
        ("requested_strength", 0.125),
    ],
)
def test_feedback_clip_reported_field_tamper_corpus(
    field_name: str,
    forged_value: object,
) -> None:
    _scenario_corpus.test_rejected_feedback_clip_receipt_rejects_reported_single_field_mutations(
        field_name,
        forged_value,
    )


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    [
        ("source_id", "source:forged"),
        ("provenance", "forged:provenance"),
        ("candidate_id", "candidate:beta"),
        ("subject_id", "route:forged"),
        ("kind", "alarm"),
        ("requested_strength", 0.75),
        ("source_trace_event_id", "trace:forged"),
        ("trace_event_id", "trace:forged"),
    ],
)
def test_deposit_clip_reported_field_tamper_corpus(
    field_name: str,
    forged_value: object,
) -> None:
    _scenario_corpus.test_rejected_deposit_clip_receipt_rejects_reported_single_field_mutations(
        field_name,
        forged_value,
    )


@pytest.mark.parametrize(
    ("scenario", "missing_field"),
    [
        (
            _scenario_corpus.test_rejected_diffusion_clip_requires_both_receipt_fields,
            "causal_payload",
        ),
        (
            _scenario_corpus.test_rejected_diffusion_clip_requires_both_receipt_fields,
            "causal_fingerprint",
        ),
        (
            _scenario_corpus.test_rejected_feedback_clip_requires_both_receipt_fields,
            "causal_payload",
        ),
        (
            _scenario_corpus.test_rejected_feedback_clip_requires_both_receipt_fields,
            "causal_fingerprint",
        ),
        (
            _scenario_corpus.test_rejected_deposit_clip_requires_both_receipt_fields,
            "causal_payload",
        ),
        (
            _scenario_corpus.test_rejected_deposit_clip_requires_both_receipt_fields,
            "causal_fingerprint",
        ),
    ],
)
def test_rejected_clip_missing_receipt_field_corpus(
    scenario: object,
    missing_field: str,
) -> None:
    assert callable(scenario)
    scenario(missing_field)


def test_entry_public_shape_and_fail_closed_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, step, events, output = _hybrid_replay()
    baseline = tuple(events)

    non_hybrid = load_capability_manifest("examples/toy-protocol/capability.json")
    assert hybrid_trace_contract.check(non_hybrid).ok is True
    assert hybrid_trace_contract.check_actual_trace(non_hybrid, []).ok is True
    empty = hybrid_trace_contract.check_actual_trace(manifest, [])
    assert empty.detail == "actual_trace_empty"

    protocol_events = list(baseline)
    protocol_events[0] = replace(protocol_events[0], protocol_id="protocol:forged")
    assert (
        "event:0:protocol_id"
        in hybrid_trace_contract.check_actual_trace(manifest, protocol_events).detail
    )

    target_events = list(baseline)
    target_events[0] = replace(target_events[0], target="decision:forged")
    assert (
        "event:0:target"
        in hybrid_trace_contract.check_actual_trace(manifest, target_events).detail
    )

    no_score = [event for event in baseline if event.event_type != "candidate_score"]
    assert (
        "candidate_score_missing"
        in hybrid_trace_contract.check_actual_trace(manifest, no_score).detail
    )

    reversed_events = list(baseline)
    decision_index = _event_index(reversed_events, "commit")
    decision = reversed_events.pop(decision_index)
    reversed_events.insert(_event_index(reversed_events, "candidate_score"), decision)
    reversed_result = hybrid_trace_contract.check_actual_trace(
        manifest, reversed_events
    )
    assert "decision_precedes_score" in reversed_result.detail
    assert "authority_score_consensus_decision_order" in reversed_result.detail

    output_first = [output, *step.trace_events]
    assert (
        "output_precedes_decision"
        in hybrid_trace_contract.check_actual_trace(manifest, output_first).detail
    )

    coverage = hybrid_trace_contract.check_actual_trace(
        manifest,
        baseline,
        decision=step.decision,
        enforce_declared_coverage=True,
    )
    assert coverage.ok is False
    assert "actual_event_missing:" in coverage.detail

    monkeypatch.setattr(
        _entry,
        "collective_authority_problems",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("alarm")),
    )
    reconstruction = _entry.check_actual_trace(manifest, baseline)
    assert reconstruction.detail.endswith("authority_reconstruction:ValueError:alarm")


def test_entry_decision_lineage_and_reinforcement_conversion_edges() -> None:
    manifest, step, events, _ = _hybrid_replay()

    decision_index = _event_index(events, "commit")
    forged = _with_lineage(
        events[decision_index],
        candidate_id="candidate:undeclared",
        decision_reason="forged",
    )
    events[decision_index] = replace(forged, event_type="fallback", reason="forged")
    result = hybrid_trace_contract.check_actual_trace(
        manifest,
        events,
        decision=step.decision,
    )
    for diagnostic in (
        "decision_undeclared_candidate",
        "fallback_not_safe",
        "decision_event_type",
        "decision_lineage_mismatch",
    ):
        assert diagnostic in result.detail

    malformed = TraceEvent(
        "pheromone_reinforce",
        manifest.protocol.id,
        manifest.protocol.quorum_policy.target,
        "malformed numeric reinforcement",
        {"delta": object(), "old_strength": 0.0, "new_strength": 1.0},
    )
    assert _entry.has_positive_reinforcement_state_change([malformed]) is False
    assert _entry._declared_coverage_problems(None, ()) == []

    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    no_evaporation = replace(
        policy,
        pheromone_evaporation_rate=0.0,
        pheromone_kind_profiles={},
    )
    missing = _entry.actual_trace_coverage_problems(no_evaporation, set())
    assert "actual_event_missing:pheromone_evaporate" not in missing


def test_entry_replay_orchestration_regression_alarms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _, _, _ = _hybrid_replay()
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    bundle = _entry._build_replay_bundle(manifest)
    failed = CheckResult("hybrid_trace_contract", False, "injected_failure")
    passed = CheckResult("hybrid_trace_contract", True)

    monkeypatch.setattr(_entry, "_check_replay_pair", lambda *_a, **_kw: failed)
    assert _entry._check_replay_bundle(manifest, policy, bundle) == failed

    calls = 0

    def fail_secondary(*_args: Any, **_kwargs: Any) -> CheckResult:
        nonlocal calls
        calls += 1
        return failed if calls == 2 else passed

    monkeypatch.setattr(_entry, "_check_replay_pair", fail_secondary)
    secondary = _entry._check_replay_bundle(manifest, policy, bundle)
    assert secondary.detail == "idempotent_replay:injected_failure"

    monkeypatch.setattr(_entry, "_check_replay_pair", lambda *_a, **_kw: passed)
    no_fallback = replace(bundle, fallback=bundle.primary)
    missing_fallback = _entry._check_replay_bundle(manifest, policy, no_fallback)
    assert missing_fallback.detail == "fallback_replay:fallback_event_missing"

    monkeypatch.setattr(
        _entry,
        "_build_replay_bundle",
        lambda _manifest: (_ for _ in ()).throw(ValueError("builder alarm")),
    )
    replay_error = _entry.check(manifest)
    assert replay_error.detail == "replay:ValueError:builder alarm"
    assert _entry._replay_exception_result(ValueError()).detail == "replay:ValueError"


def test_authority_selection_signal_and_threshold_edges() -> None:
    manifest, _, events, _ = _hybrid_replay()
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None

    protocol = replace(manifest.protocol, collective_decision_policy=None)
    assert _authority.collective_authority_problems(
        replace(manifest, protocol=protocol), tuple(events)
    ) == ["authority_collective_policy_missing"]

    selected, problems = _authority._select_authority_events(tuple(events))
    assert selected is not None and problems == []
    assert (
        _authority._authority_event_count_issue((), (object(),), (object(),))
        == "authority_candidate_score_count"
    )
    assert (
        _authority._authority_event_count_issue(
            (object(),), (object(),), (object(), object())
        )
        == "authority_decision_event_count"
    )

    threshold_events = list(events)
    consensus_index = _event_index(threshold_events, "consensus_check")
    threshold_events[consensus_index] = _with_lineage(
        threshold_events[consensus_index],
        min_independent_scouts=policy.min_independent_scouts + 1,
    )
    assert (
        "authority_scout_threshold_mismatch"
        in _authority.collective_authority_problems(manifest, tuple(threshold_events))
    )

    active_ids = _authority._active_candidate_ids(manifest)
    state = _authority._new_signal_replay(active_ids)
    recruit = events[_event_index(events, "recruit")]
    disabled = replace(policy, recruitment_enabled=False)
    disabled_problems = _authority._direct_signal_problems(disabled, 7, recruit, state)
    assert "authority_recruitment_disabled:7" in disabled_problems
    duplicate_problems = _authority._direct_signal_problems(disabled, 8, recruit, state)
    assert "authority_duplicate_recruitment:recruit:conformance" in duplicate_problems

    invalid = _with_lineage(
        recruit,
        candidate_id="candidate:undeclared",
        verification_trace_event_id="",
    )
    assert "authority_recruitment_lineage:9" in _authority._direct_signal_problems(
        policy, 9, invalid, state
    )
    strong = _with_lineage(recruit, source_id="recruit:strong", strength=1e6)
    assert "authority_recruitment_strength_bound:10" in (
        _authority._direct_signal_problems(policy, 10, strong, state)
    )
    assert _authority._record_collective_lineage(0, None, object(), state) == []


def test_authority_real_scout_score_and_coordination_tamper_edges() -> None:
    manifest, _, baseline, _ = _hybrid_replay()

    scout_target = list(baseline)
    scout_index = _event_index(scout_target, "scout_report")
    scout_target[scout_index] = _with_lineage(
        scout_target[scout_index], candidate_id="candidate:undeclared"
    )
    assert (
        "authority_scout_target:"
        in hybrid_trace_contract.check_actual_trace(manifest, scout_target).detail
    )

    scout_missing = list(baseline)
    scout_missing[scout_index] = _with_lineage(
        scout_missing[scout_index], verification_trace_event_id=""
    )
    assert "authority_scout_verification_lineage:" in (
        hybrid_trace_contract.check_actual_trace(manifest, scout_missing).detail
    )

    duplicate_scout = list(baseline)
    duplicate_scout.insert(scout_index + 1, duplicate_scout[scout_index])
    assert (
        "authority_duplicate_scout:"
        in hybrid_trace_contract.check_actual_trace(manifest, duplicate_scout).detail
    )

    category_events = list(baseline)
    score_index = _event_index(category_events, "candidate_score")
    score_lineage = deepcopy(dict(category_events[score_index].lineage))
    first_candidate = next(iter(score_lineage["score_breakdown"]))
    score_lineage["score_breakdown"][first_candidate].pop("scout")
    category_events[score_index] = replace(
        category_events[score_index], lineage=score_lineage
    )
    assert f"authority_score_categories:{first_candidate}" in (
        hybrid_trace_contract.check_actual_trace(manifest, category_events).detail
    )

    duplicate_proposal = list(baseline)
    proposals = [
        index
        for index, event in enumerate(duplicate_proposal)
        if event.event_type == "layer_proposal"
    ]
    duplicate_proposal[proposals[1]] = _with_lineage(
        duplicate_proposal[proposals[1]],
        source_trace_event_id=duplicate_proposal[proposals[0]].lineage[
            "source_trace_event_id"
        ],
    )
    assert "authority_duplicate_layer_proposal_lineage" in (
        hybrid_trace_contract.check_actual_trace(manifest, duplicate_proposal).detail
    )

    no_assessment = [
        event for event in baseline if event.event_type != "coordination_assess"
    ]
    assert "authority_coordination_event_count" in (
        hybrid_trace_contract.check_actual_trace(manifest, no_assessment).detail
    )


def test_authority_direct_pheromone_and_decision_edge_helpers() -> None:
    manifest, _, events, _ = _hybrid_replay()
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    selected, _ = _authority._select_authority_events(tuple(events))
    assert selected is not None
    pheromone_events = tuple(
        event for event in events if event.event_type == "pheromone_score"
    )

    assert _authority._replay_receipt_problems(manifest, tuple(events), (), None) == [
        "authority_pheromone_score_count"
    ]
    assert (
        _authority._pheromone_score_problems(
            manifest,
            replace(policy, pheromone_enabled=False),
            tuple(events),
            selected,
            _authority._active_candidate_ids(manifest),
            pheromone_events,
        )
        == []
    )
    assert _authority._pheromone_score_problems(
        manifest,
        policy,
        tuple(events),
        selected,
        _authority._active_candidate_ids(manifest),
        (),
    ) == ["authority_pheromone_score_count"]

    fallback_event = replace(
        selected.decision,
        event_type="fallback",
        lineage={
            **dict(selected.decision.lineage),
            "candidate_id": "candidate:alpha",
        },
    )
    coordination = _authority._CoordinationView(
        {"selected_candidate": "candidate:safe_fallback"},
        set(),
    )
    assert "authority_coordination_fallback_candidate" in (
        _authority._decision_consensus_problems(
            fallback_event,
            "candidate:alpha",
            coordination,
            True,
            [],
        )
    )
    assert "authority_commit_not_top_qualified_candidate" in (
        _authority._decision_consensus_problems(
            selected.decision,
            selected.decision.lineage["candidate_id"],
            _authority._CoordinationView({}, set()),
            False,
            ["candidate:beta", "candidate:alpha"],
        )
    )


def test_policy_adjustment_trace_real_tamper_matrix() -> None:
    manifest, _, events, _ = _hybrid_replay()
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    adjustment = events[_event_index(events, "policy_adjustment")]

    missing_trace = _with_lineage(adjustment, source_trace_event_id="")
    assert _coordination.policy_adjustment_trace_problems(policy, (missing_trace,)) == [
        "authority_policy_adjustment_trace:0"
    ]

    invalid_result = _with_lineage(adjustment, result="forged")
    assert "authority_policy_adjustment_result:0" in (
        _coordination.policy_adjustment_trace_problems(policy, (invalid_result,))
    )

    second = _with_lineage(adjustment, source_trace_event_id="trace:adjustment:second")
    duplicate = _coordination.policy_adjustment_trace_problems(
        policy, (adjustment, second)
    )
    assert "authority_policy_adjustment_duplicate_key:layer_learned_weight" in duplicate
    duplicate_trace = _coordination.policy_adjustment_trace_problems(
        policy, (adjustment, adjustment)
    )
    assert "authority_policy_adjustment_duplicate_trace:trace:adjustment" in (
        duplicate_trace
    )

    wrong_bounds = _with_lineage(
        adjustment, declared_bounds={"layer_learned_weight": [-1, -1]}
    )
    assert "authority_policy_adjustment_bound:layer_learned_weight" in (
        _coordination.policy_adjustment_trace_problems(policy, (wrong_bounds,))
    )

    protocol = replace(manifest.protocol, collective_decision_policy=None)
    missing_policy_manifest = replace(manifest, protocol=protocol)
    proposal = next(event for event in events if event.event_type == "layer_proposal")
    assessment = next(
        event for event in events if event.event_type == "coordination_assess"
    )
    resolution = next(
        event for event in events if event.event_type == "coordination_resolve"
    )
    assert _coordination.coordination_replay_problems(
        missing_policy_manifest,
        tuple(events),
        [proposal],
        assessment,
        resolution,
        {},
        set(),
    ) == ["authority_coordination_policy_missing"]


def test_layer_proposal_effect_regression_alarm_matrix() -> None:
    manifest, _, events, _ = _hybrid_replay()
    original = next(event for event in events if event.event_type == "layer_proposal")
    trace_id = "trace:layer:pheromone"
    proposal = _with_lineage(
        original,
        action="propose_pheromone",
        effect="bounded_pheromone_deposit_proposed",
        confidence=0.5,
        proposed_strength=2.0,
        proposed_pheromone_kind="positive",
        subject_type="route",
        subject_id="route:alpha",
        source_trace_event_id=trace_id,
    )
    proposals = {trace_id: (1, proposal)}

    assert _coordination._proposal_effect_problems(proposal, proposals, {}, {}) == [
        f"authority_layer_pheromone_effect_missing:{trace_id}"
    ]

    deposit = TraceEvent(
        "pheromone_deposit",
        manifest.protocol.id,
        manifest.protocol.quorum_policy.target,
        "proposal deposit",
        {
            "source_id": "forged",
            "candidate_id": "candidate:beta",
            "kind": "negative",
            "subject_type": "route",
            "subject_id": "route:forged",
            "old_strength": 0.0,
            "new_strength": 0.25,
            "source_trace_event_id": trace_id,
        },
    )
    clip = TraceEvent(
        "pheromone_clip",
        manifest.protocol.id,
        manifest.protocol.quorum_policy.target,
        "proposal clip",
        {
            "lifecycle": "deposit",
            "trace_event_id": trace_id,
            "requested_strength": 9.0,
            "applied_strength": 0.75,
        },
    )
    deposits: dict[str, list[tuple[int, TraceEvent]]] = {}
    clips: dict[str, list[tuple[int, TraceEvent]]] = {}
    _coordination._index_proposal_effect(3, clip, proposals, deposits, clips)
    assert clips == {trace_id: [(3, clip)]}

    shape = _coordination._proposal_effect_shape_problems(
        trace_id,
        2,
        [(1, deposit), (3, deposit)],
        [(1, clip), (4, clip)],
    )
    assert f"authority_layer_pheromone_effect_count:{trace_id}" in shape
    assert f"authority_layer_pheromone_forward_reference:{trace_id}" in shape
    assert (
        _coordination._proposal_effect_shape_problems(
            trace_id,
            1,
            [(2, deposit)],
            [(3, clip)],
        )
        == []
    )

    applied, clip_problems = _coordination._proposal_clip_problems(
        trace_id, [(3, clip)], 1.0
    )
    assert applied == 0.75
    assert clip_problems == [f"authority_layer_pheromone_requested_strength:{trace_id}"]
    assert _coordination._proposal_deposit_problems(
        trace_id, proposal.lineage, [], applied
    ) == [f"authority_layer_pheromone_deposit_missing:{trace_id}"]
    deposit_problems = _coordination._proposal_deposit_problems(
        trace_id,
        proposal.lineage,
        [(3, deposit)],
        1.0,
    )
    assert f"authority_layer_pheromone_subject_lineage:{trace_id}" in deposit_problems
    assert f"authority_layer_pheromone_applied_strength:{trace_id}" in deposit_problems


def test_lifecycle_policy_and_shared_helper_edges() -> None:
    manifest, _, events, _ = _hybrid_replay()
    protocol = replace(manifest.protocol, collective_decision_policy=None)
    assert _lifecycle.pheromone_lifecycle_policy_problems(
        replace(manifest, protocol=protocol), tuple(events)
    ) == ["authority_pheromone_policy_missing"]

    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    context = _lifecycle._build_context(manifest, (), policy)
    _lifecycle._finalize_active_memory(context, ())
    assert context.problems == []

    unknown = TraceEvent(
        "custom_event",
        manifest.protocol.id,
        manifest.protocol.quorum_policy.target,
        "unknown stage",
        {},
    )
    assert _shared.event_stage_order_problems((unknown,)) == []
    assert _shared.near(object(), 1.0) is False


def test_lifecycle_state_identity_and_optional_field_edges() -> None:
    expected = _lifecycle_state.trail_state(
        trace_event_id="trace:one",
        source_id="source:one",
        candidate_id="candidate:alpha",
        subject_type="route",
        subject_id="route:one",
        kind="positive",
        strength=1.0,
        source_kind="positive",
        provenance="evidence:one",
        deposited_at_step=1,
        updated_at_step=2,
        ttl_steps=3,
        ttl_bound=True,
    )
    assert (
        _lifecycle_state.lifecycle_state_near(
            {**expected, "candidate_id": "candidate:beta"}, expected
        )
        is False
    )
    assert (
        _lifecycle_state.lifecycle_state_near(
            {**expected, "provenance": "forged"}, expected
        )
        is False
    )
    assert (
        _lifecycle_state.lifecycle_state_near(
            {**expected, "source_kind": "negative"}, expected
        )
        is False
    )


def test_lifecycle_clip_deposit_and_parent_edges() -> None:
    manifest, _, events, _ = _hybrid_replay()
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    clip_event = next(
        event
        for event in events
        if event.event_type == "pheromone_clip"
        and event.lineage.get("lifecycle") == "deposit"
        and float(event.lineage.get("applied_strength", 0.0)) > 0.0
    )
    item = clip_event.lineage
    trace_id = str(item["trace_event_id"])
    source_id = str(item["source_id"])
    requested = float(item["requested_strength"])

    context = _lifecycle._build_context(manifest, tuple(events), policy)
    _lifecycle_clips.process_clip(context, 1, clip_event)
    _lifecycle_clips.process_clip(context, 2, clip_event)
    assert f"authority_pheromone_clip_duplicate:{trace_id}" in context.problems

    mismatch = _lifecycle._build_context(manifest, tuple(events), policy)
    _lifecycle_clips._deposit_clip(
        mismatch,
        3,
        item,
        trace_id,
        source_id,
        requested,
        -1.0,
    )
    assert "authority_pheromone_clip_deposit_applied:3" in mismatch.problems

    missing = _lifecycle._build_context(manifest, tuple(events), policy)
    missing.deposit_events_by_trace.clear()
    _lifecycle_clips._deposit_clip(
        missing,
        4,
        item,
        trace_id,
        source_id,
        requested,
        1.0,
    )
    assert "authority_pheromone_clip_deposit_missing:4" in missing.problems

    rejected = _lifecycle._build_context(manifest, tuple(events), policy)
    _lifecycle_clips._deposit_clip(
        rejected,
        5,
        item,
        trace_id,
        source_id,
        requested,
        0.0,
    )
    assert "authority_pheromone_clip_rejected_deposit_applied:5" in rejected.problems

    parent_context = SimpleNamespace(
        diffusion_lineage={"trace:parent": ("trace:root", 1)}
    )
    assert (
        _lifecycle_clips._diffusion_parent_invalid(
            parent_context, "trace:parent", "trace:wrong", 2
        )
        is True
    )

    feedback = next(
        event
        for event in events
        if event.event_type == "pheromone_clip"
        and event.lineage.get("lifecycle") == "feedback"
    )
    known = _lifecycle._build_context(manifest, tuple(events), policy)
    _lifecycle_state.source_state(known, 6, feedback)
    feedback_item = feedback.lineage
    _lifecycle_clips._feedback_clip(
        known,
        6,
        feedback,
        str(feedback_item["trace_event_id"]),
        str(feedback_item["source_id"]),
        float(feedback_item["requested_strength"]),
        float(feedback_item["applied_strength"]),
    )
    assert str(feedback_item["source_trace_event_id"]) in known.states


def test_lifecycle_transition_replay_model_and_budget_edges() -> None:
    manifest, _, events, _ = _hybrid_replay()
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None

    deposit = next(event for event in events if event.event_type == "pheromone_deposit")
    duplicate_context = _lifecycle._build_context(manifest, tuple(events), policy)
    duplicate_context.states[str(deposit.lineage["trace_event_id"])] = {}
    _lifecycle_transitions.process_transition(duplicate_context, 7, deposit)
    assert "authority_pheromone_duplicate_transition:" in ";".join(
        duplicate_context.problems
    )

    evaporation = next(
        event for event in events if event.event_type == "pheromone_evaporate"
    )
    wrong_profile = _with_lineage(evaporation, profile="forged")
    evaporation_context = _lifecycle._build_context(manifest, tuple(events), policy)
    _lifecycle_transitions.process_transition(evaporation_context, 8, wrong_profile)
    assert "authority_pheromone_evaporation_profile:8" in evaporation_context.problems

    novelty_source = {
        "kind": "novelty",
        "strength": 1.0,
    }
    novelty_item = {"elapsed_steps": 1}
    expected, label = _lifecycle_transitions._expected_evaporation(
        evaporation_context, novelty_source, novelty_item
    )
    assert expected >= evaporation_context.minimum
    assert label.startswith(("kind:", "global:"))
    assert _lifecycle_transitions._decayed_strength("step", 2.0, 0.75, 0.25, 3) == 1.5
    assert _lifecycle_transitions._decayed_strength("linear", 2.0, 0.75, 0.25, 3) == 0.5

    parent_context = SimpleNamespace(diffusion_lineage={"parent": ("root", 1)})
    assert _lifecycle_transitions._diffusion_parent_invalid(
        parent_context, "parent", "wrong", 2
    )

    negative_context = _lifecycle._build_context(manifest, tuple(events), policy)
    negative_item = {
        "delta": -1.0,
        "new_strength": 1.0,
        "budget_result": {
            "round_remaining": -1.0,
            "source_remaining": -1.0,
        },
        "source_id": "source:negative",
    }
    _lifecycle_transitions._reinforcement_budget(
        negative_context,
        9,
        negative_item,
        {"strength": 2.0},
    )
    for diagnostic in (
        "authority_pheromone_reinforce_stale_floor:9",
        "authority_pheromone_round_budget_lineage:9",
        "authority_pheromone_source_budget_lineage:9",
    ):
        assert diagnostic in negative_context.problems
    exact_budget = {
        "new_strength": negative_context.minimum,
        "budget_result": {
            "round_remaining": negative_context.round_cap,
            "source_remaining": negative_context.source_cap,
        },
        "source_id": "source:exact",
    }
    before = list(negative_context.problems)
    _lifecycle_transitions._negative_reinforcement_budget(
        negative_context, 10, exact_budget
    )
    assert negative_context.problems == before
    assert _lifecycle_transitions._kind_ttl(negative_context, "undeclared") is None


def test_replay_receipt_binding_and_snapshot_edges() -> None:
    manifest, step, events, _ = _hybrid_replay()
    replay_state = replay_state_from_hybrid_step(step)
    empty, issue = _receipts._authoritative_replay_receipts(
        replay_state,
        "protocol:wrong",
        manifest.protocol.quorum_policy.target,
    )
    assert issue == "authority_replay_state_binding"
    assert set(empty) == {"deposit", "diffusion", "feedback", "adjustment"}

    score_event = next(
        event for event in events if event.event_type == "pheromone_score"
    )
    malformed = TraceEvent(
        "pheromone_observe",
        manifest.protocol.id,
        manifest.protocol.quorum_policy.target,
        "malformed replay",
        {
            "result": "replay_ignored",
            "lifecycle": "unknown",
            "source_trace_event_id": "trace:unknown",
            "replay_payload": [],
        },
    )
    assert _receipts._replay_event_problems(
        1,
        malformed,
        "unknown",
        {"deposit": {}, "diffusion": {}, "feedback": {}, "adjustment": {}},
        _receipts._empty_replay_snapshot(),
    ) == ["authority_replay_lifecycle:1"]

    expected = _receipts._empty_replay_snapshot()
    expected["deposit"]["trace:duplicate"] = "sha256:known"
    authoritative = {
        "deposit": {"trace:duplicate": ("payload",)},
        "diffusion": {},
        "feedback": {},
        "adjustment": {},
    }
    duplicate = _with_lineage(
        malformed,
        lifecycle="deposit",
        source_trace_event_id="trace:duplicate",
        replay_payload=["payload"],
    )
    duplicate_problems = _receipts._replay_event_problems(
        2, duplicate, "deposit", authoritative, expected
    )
    assert "authority_replay_duplicate:deposit:trace:duplicate" in duplicate_problems

    invalid_payload = _with_lineage(
        duplicate,
        source_trace_event_id="trace:other",
        replay_payload={"not": "a sequence"},
    )
    assert _receipts._replay_event_problems(
        3, invalid_payload, "deposit", authoritative, _receipts._empty_replay_snapshot()
    ) == ["authority_replay_payload:3"]

    missing_snapshot = replace(score_event, lineage={"processed_replay_receipts": ()})
    assert _receipts._replay_snapshot_problems(
        missing_snapshot, _receipts._empty_replay_snapshot()
    ) == ["authority_replay_receipt_snapshot_missing"]
    wrong_lifecycles = replace(
        score_event, lineage={"processed_replay_receipts": {"deposit": {}}}
    )
    assert _receipts._replay_snapshot_problems(
        wrong_lifecycles, _receipts._empty_replay_snapshot()
    ) == ["authority_replay_receipt_snapshot_lifecycles"]
    assert _receipts._canonical_trace_replay_receipt(
        [{"nested": [1, {"value": 2}]}]
    ) == ((("nested", (1, (("value", 2),))),),)


def test_manifest_replay_builder_and_bound_shape_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _, _, _ = _hybrid_replay()
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None

    no_policy = replace(
        manifest,
        protocol=replace(manifest.protocol, collective_decision_policy=None),
    )
    with pytest.raises(ValueError, match="requires collective policy"):
        _replay.manifest_replay(no_policy)

    monkeypatch.setattr(_replay, "exercise_candidate_id", lambda _manifest: None)
    with pytest.raises(ValueError, match="no active target candidate"):
        _replay.manifest_replay(manifest)
    monkeypatch.undo()

    assert _replay.accepted_adjustment_value((2, 3)) == 2
    assert _replay.accepted_adjustment_value({"allowed_values": ["x"]}) == "x"
    assert _replay.accepted_adjustment_value({"min": 0.25}) == 0.25
    with pytest.raises(ValueError, match="adjustment bound is malformed"):
        _replay.accepted_adjustment_value({})

    no_evaporation = replace(
        policy,
        pheromone_evaporation_rate=0.0,
        pheromone_kind_profiles={},
    )
    assert _replay.replay_evaporation_kind(no_evaporation) is None

    zero_budget_policy = replace(
        policy,
        pheromone_min_strength=0.0,
        pheromone_max_strength=0.0,
        pheromone_per_source_cap=0.0,
        pheromone_per_round_deposit_cap=0.0,
    )
    zero_budget_manifest = replace(
        manifest,
        protocol=replace(
            manifest.protocol,
            collective_decision_policy=zero_budget_policy,
        ),
    )
    with pytest.raises(ValueError, match="positive declared pheromone budgets"):
        _replay.manifest_replay(zero_budget_manifest)


def test_score_reconstruction_policy_ttl_and_count_edges() -> None:
    manifest, _, events, _ = _hybrid_replay()
    score_event = next(
        event for event in events if event.event_type == "pheromone_score"
    )
    candidate_event = next(
        event for event in events if event.event_type == "candidate_score"
    )
    no_policy = replace(
        manifest,
        protocol=replace(manifest.protocol, collective_decision_policy=None),
    )
    assert _score.pheromone_score_reconstruction_problems(
        no_policy,
        tuple(events),
        score_event,
        candidate_event,
    ) == ["authority_pheromone_policy_missing"]

    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    replay = _score._reconstruct_score(
        manifest,
        policy,
        _score._accepted_adjustments(tuple(events)),
        score_event,
    )
    trail = replay.trails[0]
    expired = replace(
        trail,
        deposited_at_step=0,
        updated_at_step=replay.current_step,
        ttl_steps=1,
        kind="positive",
    )
    expired_replay = replace(replay, trails=[expired])
    assert _score._trail_state_problems(expired_replay) == [
        f"authority_pheromone_active_ttl:{expired.trace_event_id}"
    ]

    assert _score._normalization_problems((), replay.reconstructed, -1) == [
        "authority_pheromone_normalize_count"
    ]
    expected_observations = [object()]
    assert _score._observation_problems((), expected_observations, -1) == [
        "authority_pheromone_observe_count"
    ]

    runtime = replace(replay.runtime_policy, exploration_floor=0.5)
    assert _score._exploration_floor_problems((), replay.candidates, runtime, -1) == [
        "authority_pheromone_exploration_floor_count"
    ]
    assert _score.nested_numeric_mapping_near([], {}) is False


def test_facade_forwards_each_decomposed_hybrid_trace_surface() -> None:
    manifest, step, events, _ = _hybrid_replay()
    items = tuple(events)
    policy = manifest.protocol.collective_decision_policy
    assert policy is not None
    score_event = next(
        event for event in items if event.event_type == "pheromone_score"
    )
    candidate_event = next(
        event for event in items if event.event_type == "candidate_score"
    )
    proposals = [event for event in items if event.event_type == "layer_proposal"]
    assessment = next(
        event for event in items if event.event_type == "coordination_assess"
    )
    resolution = next(
        event for event in items if event.event_type == "coordination_resolve"
    )
    active_ids = _authority._active_candidate_ids(manifest)

    assert hybrid_trace_contract.collective_authority_problems(manifest, items) == []
    assert (
        hybrid_trace_contract.replay_trace_problems(
            items,
            score_event,
            replay_state=None,
            protocol_id=manifest.protocol.id,
            target=manifest.protocol.quorum_policy.target,
        )
        == []
    )
    assert (
        hybrid_trace_contract.pheromone_lifecycle_policy_problems(manifest, items) == []
    )
    assert (
        hybrid_trace_contract.pheromone_score_reconstruction_problems(
            manifest,
            items,
            score_event,
            candidate_event,
        )
        == []
    )

    replay = _score._reconstruct_score(
        manifest,
        policy,
        _score._accepted_adjustments(items),
        score_event,
    )
    assert (
        hybrid_trace_contract.pheromone_derived_trace_problems(
            events=items,
            pheromone_score_event=score_event,
            reconstructed=replay.reconstructed,
            runtime_policy=replay.runtime_policy,
            candidates=replay.candidates,
            trails=replay.trails,
            current_step=replay.current_step,
        )
        == []
    )
    assert hybrid_trace_contract.policy_adjustment_trace_problems(policy, items) == []
    assert (
        hybrid_trace_contract.coordination_replay_problems(
            manifest,
            items,
            proposals,
            assessment,
            resolution,
            candidate_event.lineage["score_breakdown"],
            active_ids,
        )
        == []
    )
    assert (
        hybrid_trace_contract.layer_pheromone_lineage_problems(items, proposals) == []
    )
    assert hybrid_trace_contract.event_stage(score_event) == 7
    replayed_step, _ = hybrid_trace_contract.manifest_replay(
        manifest,
        replay_state=replay_state_from_hybrid_step(step),
    )
    assert replayed_step.decision == step.decision
