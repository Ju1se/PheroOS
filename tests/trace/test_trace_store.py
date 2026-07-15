import pytest

from pheroos.trace import (
    COMMIT_EVENT_TYPES,
    EVENT_LINEAGE_CONTRACTS,
    InMemoryTraceStore,
    TraceEvent,
    VALID_EVENT_TYPES,
    canonical_pheromone_clip_payload,
    pheromone_clip_payload_fingerprint,
)


def test_trace_store_appends_records_and_validates_required_events() -> None:
    store = InMemoryTraceStore()
    for event_type in sorted(VALID_EVENT_TYPES - COMMIT_EVENT_TYPES):
        store.append(
            TraceEvent(
                event_type=event_type,
                protocol_id="e2e.review",
                target="decision:e2e",
                reason="test",
                lineage=valid_lineage(event_type),
            )
        )

    assert [record.sequence for record in store.records] == list(
        range(len(VALID_EVENT_TYPES - COMMIT_EVENT_TYPES))
    )
    assert store.require_events(["plan", "invoke", "output"]) == []


def test_pheromone_clip_payload_receipt_is_canonical_and_finite() -> None:
    left = {"lifecycle": "feedback", "input": {"b": [2, 3], "a": 1.0}}
    right = {"input": {"a": 1.0, "b": [2, 3]}, "lifecycle": "feedback"}

    assert canonical_pheromone_clip_payload(left) == canonical_pheromone_clip_payload(right)
    assert pheromone_clip_payload_fingerprint(left) == pheromone_clip_payload_fingerprint(right)
    assert pheromone_clip_payload_fingerprint(left).startswith("sha256:")
    assert len(pheromone_clip_payload_fingerprint(left)) == len("sha256:") + 64
    with pytest.raises(ValueError, match="finite"):
        pheromone_clip_payload_fingerprint(
            {"lifecycle": "feedback", "strength_delta": float("nan")}
        )


def test_replay_trace_recomputes_fingerprint_from_complete_payload() -> None:
    receipt = (
        "deposit-v1",
        "candidate:alpha",
        1.0,
        "route",
        "route:alpha",
        "decision:e2e",
        "route:alpha",
        "",
        "positive",
        "scout:a",
        "scout",
        "evidence:a",
        "driver:a",
        "trace:deposit:a",
        1,
        1,
        2,
        ("trace:deposit:a",),
        "",
        "",
        0,
    )
    fingerprint = pheromone_clip_payload_fingerprint(
        {"lifecycle": "replay_receipt", "receipt": receipt}
    )
    lineage = {
        "lifecycle": "deposit",
        "source_trace_event_id": "trace:deposit:a",
        "result": "replay_ignored",
        "replay_payload": list(receipt),
        "replay_payload_fingerprint": fingerprint,
        "processed_payload_fingerprint": fingerprint,
    }
    store = InMemoryTraceStore()
    store.append(
        TraceEvent(
            event_type="pheromone_observe",
            protocol_id="swarm.collective",
            target="decision:e2e",
            reason="issued replay receipt",
            lineage=lineage,
        )
    )
    mutated = dict(lineage)
    mutated_payload = list(receipt)
    mutated_payload[2] = 1.125
    mutated["replay_payload"] = mutated_payload

    with pytest.raises(ValueError, match="does not match replay_payload"):
        store.append(
            TraceEvent(
                event_type="pheromone_observe",
                protocol_id="swarm.collective",
                target="decision:e2e",
                reason="payload substitution",
                lineage=mutated,
            )
        )


def test_trace_store_rejects_unknown_event_type() -> None:
    store = InMemoryTraceStore()

    with pytest.raises(ValueError):
        store.append(
            TraceEvent(
                event_type="unknown",
                protocol_id="e2e.review",
                target="decision:e2e",
                reason="test",
            )
        )


def test_trace_store_accepts_namespaced_extension_events() -> None:
    store = InMemoryTraceStore()

    record = store.append(
        TraceEvent(
            event_type="x-acme.agent_observed",
            protocol_id="e2e.review",
            target="decision:e2e",
            reason="external runtime observation",
            lineage={"adapter": "outside-core"},
        )
    )

    assert record.event.event_type == "x-acme.agent_observed"
    assert store.require_events(["x-acme.agent_observed"]) == []


def test_trace_store_rejects_invalid_extension_prefix_and_empty_reason() -> None:
    store = InMemoryTraceStore()

    with pytest.raises(ValueError, match="unsupported trace event type"):
        store.append(
            TraceEvent(
                event_type="x-",
                protocol_id="e2e.review",
                target="decision:e2e",
                reason="test",
            )
        )
    with pytest.raises(ValueError, match="reason is required"):
        store.append(
            TraceEvent(
                event_type="ext.acme.observed",
                protocol_id="e2e.review",
                target="decision:e2e",
                reason="",
            )
        )


@pytest.mark.parametrize(
    ("field_name", "message"),
    [
        ("protocol_id", "protocol_id is required"),
        ("target", "target is required"),
        ("reason", "reason is required"),
    ],
)
def test_trace_event_rejects_whitespace_identity_fields(
    field_name: str,
    message: str,
) -> None:
    values = {
        "event_type": "block",
        "protocol_id": "protocol:test",
        "target": "decision:test",
        "reason": "blocked",
    }
    values[field_name] = "   "

    with pytest.raises(ValueError, match=message):
        TraceEvent(**values).validate()


def test_trace_event_lineage_carries_pheromone_metadata() -> None:
    store = InMemoryTraceStore()
    deposit = store.append(
        TraceEvent(
            event_type="pheromone_deposit",
            protocol_id="swarm.collective",
            target="decision:collective",
            reason="traceable pheromone mark",
            lineage={
                "source_id": "agent:a",
                "provenance": "driver:a",
                "subject_type": "candidate",
                "subject_id": "candidate:alpha",
                "candidate_id": "candidate:alpha",
                "kind": "cautionary",
                "source_kind": "cautionary",
                "source_strength": 0,
                "old_strength": 0,
                "requested_strength": 1,
                "applied_strength": 1,
                "new_strength": 1,
                "round_budget_remaining": 1,
                "source_budget_remaining": 1,
                "step": 1,
                "deposited_at_step": 1,
                "updated_at_step": 1,
                "source_trace_event_id": "trace:deposit:a",
                "trace_event_id": "trace:deposit:a",
            },
        )
    )
    score = store.append(
        TraceEvent(
            event_type="pheromone_score",
            protocol_id="swarm.collective",
            target="decision:collective",
            reason="candidate pheromone score contribution",
            lineage={
                "scores": {"candidate:alpha": 3.0},
                "score_breakdown": {"candidate:alpha": {"pheromone_positive": 3.0}},
                "kind_breakdown": {"candidate:alpha": {"positive": 3.0}},
                "subject_breakdown": {"candidate:alpha": {"candidate": 3.0}},
                "active_trails": [
                    {
                        "trace_event_id": "trace:deposit:a",
                        "source_id": "agent:a",
                        "candidate_id": "candidate:alpha",
                        "subject_type": "candidate",
                        "subject_id": "candidate:alpha",
                        "kind": "positive",
                        "source_kind": "positive",
                        "strength": 3.0,
                        "provenance": "driver:a",
                        "deposited_at_step": 1,
                        "updated_at_step": 1,
                        "ttl_steps": None,
                    }
                ],
                "current_step": 1,
            },
        )
    )
    expire = store.append(
        TraceEvent(
            event_type="pheromone_expire",
            protocol_id="swarm.collective",
            target="decision:collective",
            reason="expired pheromone represented as stale",
            lineage={
                "action": "expire",
                "target": "decision:collective",
                "candidate_id": "candidate:alpha",
                "subject_type": "route",
                "subject_id": "route:alpha",
                "kind": "stale",
                "source_kind": "positive",
                "source_strength": 1,
                "old_strength": 1,
                "requested_strength": 1,
                "applied_strength": 0,
                "new_strength": 0,
                "strength_delta": -1,
                "source_id": "agent:a",
                "provenance": "driver:a",
                "evidence_id": "evidence:a",
                "source_trace_event_id": "trace:deposit:a",
                "trace_event_id": "trace:deposit:a",
                "step": 2,
                "source_updated_at_step": 1,
                "deposited_at_step": 1,
                "ttl_steps": 1,
                "elapsed_steps": 1,
            },
        )
    )

    assert deposit.event.lineage["kind"] == "cautionary"
    assert score.event.lineage["kind_breakdown"]["candidate:alpha"] == {"positive": 3.0}
    assert expire.event.lineage["kind"] == "stale"
    assert store.require_events(["pheromone_deposit", "pheromone_score", "pheromone_expire"]) == []


def test_trace_lineage_can_carry_uniform_pheromone_subjects() -> None:
    store = InMemoryTraceStore()
    record = store.append(
        TraceEvent(
            event_type="pheromone_deposit",
            protocol_id="swarm.collective",
            target="decision:collective",
            reason="uniform pheromone subjects deposited",
            lineage={
                "source_id": "agent:a",
                "provenance": "driver:a",
                "subject_type": "route",
                "subject_id": "route:research",
                "candidate_id": "candidate:alpha",
                "kind": "positive",
                "source_kind": "positive",
                "source_strength": 0,
                "old_strength": 0,
                "requested_strength": 1,
                "applied_strength": 1,
                "new_strength": 1,
                "round_budget_remaining": 1,
                    "source_budget_remaining": 1,
                    "step": 1,
                    "deposited_at_step": 1,
                    "updated_at_step": 1,
                    "ttl_steps": None,
                    "source_trace_event_id": "trace:deposit:a",
                "trace_event_id": "trace:deposit:a",
                "subjects": [
                    {"subject_type": "route", "subject_id": "route:research"},
                    {"subject_type": "tool", "subject_id": "tool:parser"},
                    {"subject_type": "evidence", "subject_id": "evidence:a"},
                    {"subject_type": "agent", "subject_id": "agent:a"},
                ]
            },
        )
    )

    assert [item["subject_type"] for item in record.event.lineage["subjects"]] == [
        "route",
        "tool",
        "evidence",
        "agent",
    ]


@pytest.mark.parametrize(
    "event_type,required",
    sorted(
        (event_type, required)
        for event_type, required in EVENT_LINEAGE_CONTRACTS.items()
        if event_type not in COMMIT_EVENT_TYPES
    ),
)
def test_event_specific_lineage_contract_rejects_each_missing_field(
    event_type: str,
    required: frozenset[str],
) -> None:
    store = InMemoryTraceStore()

    for missing in required:
        lineage = valid_lineage(event_type)
        del lineage[missing]
        with pytest.raises(ValueError, match=missing):
            store.append(
                TraceEvent(
                    event_type=event_type,
                    protocol_id="swarm.collective",
                    target="decision:e2e",
                    reason="missing lineage must fail closed",
                    lineage=lineage,
                )
            )

    assert store.records == ()


@pytest.mark.parametrize(
    "lineage,required",
    [
        (
            {
                "lifecycle": "deposit",
                "source_trace_event_id": "trace:deposit:a",
                "result": "replay_ignored",
            },
            {"lifecycle", "source_trace_event_id", "result"},
        ),
        (
            {
                "candidate_id": "candidate:alpha",
                "subject_type": "route",
                "subject_id": "route:alpha",
                "novelty_pressure": 0.1,
                "reopen_eligible": True,
                "source_trace_event_id": "trace:deposit:a",
            },
            {
                "candidate_id",
                "subject_type",
                "subject_id",
                "novelty_pressure",
                "reopen_eligible",
                "source_trace_event_id",
            },
        ),
        (
            {"exploration_floor": 0.1, "candidate_ids": ["candidate:alpha"]},
            {"exploration_floor", "candidate_ids"},
        ),
    ],
)
def test_pheromone_observe_variants_reject_each_missing_field(
    lineage: dict[str, object],
    required: set[str],
) -> None:
    for missing in required:
        malformed = dict(lineage)
        del malformed[missing]
        with pytest.raises(ValueError):
            InMemoryTraceStore().append(
                TraceEvent(
                    event_type="pheromone_observe",
                    protocol_id="swarm.collective",
                    target="decision:e2e",
                    reason="incomplete observation",
                    lineage=malformed,
                )
            )


def test_trace_store_snapshots_nested_lineage_and_returned_records() -> None:
    original = {"nested": {"values": [1, 2]}}
    event = TraceEvent(
        event_type="plan",
        protocol_id="toy.review",
        target="decision:e2e",
        reason="snapshot",
        lineage=original,
    )
    original["nested"]["values"].append(3)
    store = InMemoryTraceStore()
    returned = store.append(event)

    event.lineage["nested"]["values"].append(4)
    returned.event.lineage["nested"]["values"].append(5)
    exposed = store.records
    exposed[0].event.lineage["nested"]["values"].append(6)

    assert store.records[0].event.lineage == {"nested": {"values": [1, 2]}}


def test_trace_store_former_private_records_view_cannot_rewrite_history() -> None:
    store = InMemoryTraceStore()
    store.append(
        TraceEvent(
            event_type="plan",
            protocol_id="toy.review",
            target="decision:e2e",
            reason="append-only private storage",
            lineage={"state": {"values": ["original"]}},
        )
    )

    compatibility_view = store._records
    compatibility_view[0].event.lineage["state"]["values"].append("forged")
    with pytest.raises(AttributeError):
        store._records = ()

    assert store.records[0].event.lineage == {
        "state": {"values": ["original"]}
    }


def test_trace_validation_failure_is_atomic() -> None:
    store = InMemoryTraceStore()
    store.append(
        TraceEvent(
            event_type="plan",
            protocol_id="toy.review",
            target="decision:e2e",
            reason="valid",
        )
    )

    with pytest.raises(ValueError, match="authorization"):
        store.append(
            TraceEvent(
                event_type="output",
                protocol_id="toy.review",
                target="decision:e2e",
                reason="inconsistent gates",
                lineage={
                    "committed_candidate": True,
                    "evidence_provenance": True,
                    "stop_resolution": True,
                    "publication_permission": False,
                    "authorized": True,
                },
            )
        )

    assert [record.sequence for record in store.records] == [0]


def test_trace_lineage_rejects_non_finite_and_unreconstructable_scores() -> None:
    store = InMemoryTraceStore()
    deposit = valid_lineage("pheromone_deposit")
    deposit["new_strength"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        store.append(
            TraceEvent(
                event_type="pheromone_deposit",
                protocol_id="swarm.collective",
                target="decision:e2e",
                reason="non-finite transition",
                lineage=deposit,
            )
        )

    score = valid_lineage("candidate_score")
    score["scores"] = {"candidate:alpha": 99.0}
    with pytest.raises(ValueError, match="does not reconstruct"):
        store.append(
            TraceEvent(
                event_type="candidate_score",
                protocol_id="swarm.collective",
                target="decision:e2e",
                reason="unreconstructable score",
                lineage=score,
            )
        )

    pheromone_score = valid_lineage("pheromone_score")
    pheromone_score["kind_breakdown"] = {"candidate:alpha": {"positive": 99.0}}
    with pytest.raises(ValueError, match="kind_breakdown does not reconstruct"):
        store.append(
            TraceEvent(
                event_type="pheromone_score",
                protocol_id="swarm.collective",
                target="decision:e2e",
                reason="unreconstructable dimension",
                lineage=pheromone_score,
            )
        )

    assert store.records == ()


@pytest.mark.parametrize(
    ("field_name", "malformed"),
    [
        ("confidences", {"learned": 2.0}),
        ("confidences", {"learned": float("nan")}),
        ("weights", {"learned": -1.0}),
        ("weights", {"learned": float("inf")}),
        ("coverage", {"learned": {"trace_coverage": float("nan")}}),
        ("coverage", {"learned": {"evidence_coverage": 1.01}}),
        ("coverage", {"learned": {"trace_coverage": "complete"}}),
    ],
)
def test_coordination_assess_trace_rejects_out_of_range_or_malformed_metrics(
    field_name: str,
    malformed: object,
) -> None:
    lineage = valid_lineage("coordination_assess")
    lineage[field_name] = malformed

    with pytest.raises(ValueError, match=field_name):
        InMemoryTraceStore().append(
            TraceEvent(
                event_type="coordination_assess",
                protocol_id="swarm.collective",
                target="decision:e2e",
                reason="coordination metrics must fail closed",
                lineage=lineage,
            )
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_layer",
        "phantom_layer",
        "incomplete_snapshot",
        "absent_nonzero",
    ],
)
def test_coordination_assess_trace_requires_complete_declared_snapshot_inputs(
    mutation: str,
) -> None:
    lineage = valid_lineage("coordination_assess")
    snapshots = {
        layer_id: dict(snapshot)
        for layer_id, snapshot in lineage["snapshots"].items()
    }
    if mutation == "missing_layer":
        del snapshots["reactive"]
    elif mutation == "phantom_layer":
        snapshots["phantom"] = dict(snapshots["learned"])
    elif mutation == "incomplete_snapshot":
        del snapshots["learned"]["trace_coverage"]
    else:
        snapshots["reactive"]["trace_coverage"] = 0.5
    lineage["snapshots"] = snapshots

    with pytest.raises(ValueError, match="snapshots"):
        InMemoryTraceStore().append(
            TraceEvent(
                event_type="coordination_assess",
                protocol_id="swarm.collective",
                target="decision:e2e",
                reason="snapshot inputs must be complete and unambiguous",
                lineage=lineage,
            )
        )


@pytest.mark.parametrize(
    ("proposed_values", "declared_bounds", "error"),
    [
        (
            {"pheromone_evaporation_rate": float("nan")},
            {"pheromone_evaporation_rate": [0.1, 0.5]},
            "finite",
        ),
        (
            {"pheromone_evaporation_rate": 0.2},
            {"pheromone_evaporation_rate": [0.1, float("inf")]},
            "finite",
        ),
        (
            {"pheromone_evaporation_rate": 0.2},
            {"pheromone_evaporation_rate": [0.5, 0.1]},
            "ordered",
        ),
        (
            {"pheromone_evaporation_rate": 0.2},
            {"pheromone_evaporation_rate": [0.1]},
            "numeric bounds or allowed_values",
        ),
        (
            {"pheromone_evaporation_rate": 0.8},
            {"pheromone_evaporation_rate": {"min": 0.1, "max": 0.5}},
            "outside declared bounds",
        ),
        (
            {"pheromone_response_model": "competitive"},
            {"pheromone_response_model": {"allowed_values": ["linear", "saturating"]}},
            "outside declared bounds",
        ),
        (
            {"pheromone_evaporation_rate": 0.2},
            {"different_field": [0.1, 0.5]},
            "same fields",
        ),
    ],
)
def test_accepted_policy_adjustment_trace_rejects_malformed_or_unbounded_values(
    proposed_values: dict[str, object],
    declared_bounds: dict[str, object],
    error: str,
) -> None:
    lineage = valid_lineage("policy_adjustment")
    lineage["proposed_values"] = proposed_values
    lineage["declared_bounds"] = declared_bounds

    with pytest.raises(ValueError, match=error):
        InMemoryTraceStore().append(
            TraceEvent(
                event_type="policy_adjustment",
                protocol_id="swarm.collective",
                target="decision:e2e",
                reason="adjustment authority envelope must fail closed",
                lineage=lineage,
            )
        )


def test_policy_adjustment_trace_accepts_enum_bounds_and_records_bounded_rejection() -> None:
    store = InMemoryTraceStore()
    enum_lineage = valid_lineage("policy_adjustment")
    enum_lineage["proposed_values"] = {"pheromone_response_model": "saturating"}
    enum_lineage["declared_bounds"] = {
        "pheromone_response_model": {"allowed_values": ["linear", "saturating"]}
    }
    store.append(
        TraceEvent(
            event_type="policy_adjustment",
            protocol_id="swarm.collective",
            target="decision:e2e",
            reason="accepted enum adjustment",
            lineage=enum_lineage,
        )
    )

    rejected_lineage = valid_lineage("policy_adjustment")
    rejected_lineage["proposed_values"] = {"pheromone_evaporation_rate": 0.8}
    rejected_lineage["declared_bounds"] = {"pheromone_evaporation_rate": [0.1, 0.5]}
    rejected_lineage["result"] = "rejected"
    store.append(
        TraceEvent(
            event_type="policy_adjustment",
            protocol_id="swarm.collective",
            target="decision:e2e",
            reason="bounded rejection remains reconstructable",
            lineage=rejected_lineage,
        )
    )

    assert len(store.records) == 2


def test_replayed_policy_adjustment_must_still_fit_declared_bounds() -> None:
    lineage = valid_lineage("policy_adjustment")
    lineage["proposed_values"] = {"pheromone_evaporation_rate": 0.8}
    lineage["declared_bounds"] = {"pheromone_evaporation_rate": [0.1, 0.5]}
    lineage["result"] = "replay_ignored"

    with pytest.raises(ValueError, match="accepted or replayed value"):
        InMemoryTraceStore().append(
            TraceEvent(
                event_type="policy_adjustment",
                protocol_id="swarm.collective",
                target="decision:e2e",
                reason="an impossible replay cannot enter trace history",
                lineage=lineage,
            )
        )


def test_decision_trace_target_must_match_event_target() -> None:
    lineage = valid_lineage("commit")
    lineage["target"] = "decision:other"

    with pytest.raises(ValueError, match="must match"):
        InMemoryTraceStore().append(
            TraceEvent(
                event_type="commit",
                protocol_id="swarm.collective",
                target="decision:e2e",
                reason="wrong target",
                lineage=lineage,
            )
        )


def valid_lineage(event_type: str) -> dict[str, object]:
    lineages: dict[str, dict[str, object]] = {
        "explore": {"scout_count": 1},
        "scout_report": {
            "scout_id": "scout:a",
            "candidate_id": "candidate:alpha",
            "evidence_id": "evidence:a",
            "provenance": "driver:a",
            "support": 2.0,
            "source_trace_event_id": "trace:scout:a",
            "verification_trace_event_id": "trace:verify:scout:a",
        },
        "recruit": {
            "source_id": "agent:recruit",
            "candidate_id": "candidate:alpha",
            "strength": 0.5,
            "provenance": "driver:a",
            "source_trace_event_id": "trace:recruit:a",
            "verification_trace_event_id": "trace:verify:recruit:a",
        },
        "inhibit": {
            "source_id": "agent:inhibit",
            "candidate_id": "candidate:alpha",
            "strength": 0.25,
            "provenance": "driver:a",
            "source_trace_event_id": "trace:inhibit:a",
            "verification_trace_event_id": "trace:verify:inhibit:a",
        },
        "pheromone_deposit": {
            "source_id": "scout:a",
            "provenance": "driver:a",
            "subject_type": "candidate",
            "subject_id": "candidate:alpha",
            "candidate_id": "candidate:alpha",
            "kind": "positive",
            "source_kind": "positive",
            "source_strength": 0.0,
            "old_strength": 0.0,
            "requested_strength": 1.0,
            "applied_strength": 1.0,
            "new_strength": 1.0,
            "round_budget_remaining": 1.0,
            "source_budget_remaining": 1.0,
            "step": 1,
            "deposited_at_step": 1,
            "updated_at_step": 1,
            "source_trace_event_id": "trace:deposit:a",
            "trace_event_id": "trace:deposit:a",
        },
        "pheromone_evaporate": {
            "source_id": "scout:a",
            "provenance": "driver:a",
            "subject_type": "candidate",
            "subject_id": "candidate:alpha",
            "kind": "positive",
            "source_kind": "positive",
            "source_strength": 1.0,
            "old_strength": 1.0,
            "requested_strength": 1.0,
            "applied_strength": 0.8,
            "new_strength": 0.8,
            "strength_delta": -0.2,
            "elapsed_steps": 1,
            "step": 2,
            "source_updated_at_step": 1,
            "deposited_at_step": 1,
            "profile": "positive",
            "candidate_id": "candidate:alpha",
            "source_trace_event_id": "trace:deposit:a",
            "trace_event_id": "trace:deposit:a",
        },
        "pheromone_diffuse": {
            "source_subject": {"type": "route", "id": "route:alpha"},
            "target_subject": {"type": "candidate", "id": "candidate:alpha"},
            "hop": 1,
            "attenuation": 0.5,
            "policy_attenuation": 0.5,
            "edge_attenuation": 1.0,
            "root_trace_event_id": "trace:deposit:a",
            "source_strength": 1.0,
            "requested_strength": 0.5,
            "applied_strength": 0.5,
            "new_strength": 0.5,
            "round_budget_remaining": 1.0,
            "source_budget_remaining": 1.0,
            "source_id": "scout:a",
            "candidate_id": "candidate:alpha",
            "source_kind": "positive",
            "kind": "positive",
            "provenance": "driver:a",
            "source_trace_event_id": "trace:deposit:a",
            "trace_event_id": "trace:diffuse:a",
        },
        "pheromone_reinforce": {
            "feedback_source": "runtime:a",
            "source_id": "runtime:a",
            "provenance": "runtime:a",
            "outcome": "success",
            "reward": 1.0,
            "delta": 0.5,
            "source_strength": 1.0,
            "requested_strength": 0.5,
            "applied_strength": 0.5,
            "old_strength": 1.0,
            "new_strength": 1.5,
            "candidate_id": "candidate:alpha",
            "subject_type": "candidate",
            "subject_id": "candidate:alpha",
            "source_kind": "positive",
            "kind": "positive",
            "budget_result": {
                "round_remaining": 1.0,
                "source_remaining": 1.0,
                "status": "applied",
            },
            "step": 1,
            "source_trace_event_id": "trace:feedback:a",
            "feedback_trace_event_id": "trace:feedback:a",
            "trace_event_id": "trace:feedback:a",
        },
        "pheromone_clip": {
            "lifecycle": "deposit",
            "result": "applied",
            "source_id": "scout:a",
            "provenance": "driver:a",
            "candidate_id": "candidate:alpha",
            "subject_type": "candidate",
            "subject_id": "candidate:alpha",
            "kind": "positive",
            "source_kind": "positive",
            "source_strength": 0.0,
            "new_strength": 1.0,
            "step": 1,
            "source_trace_event_id": "trace:deposit:a",
            "trace_event_id": "trace:deposit:a",
            "requested_strength": 2.0,
            "applied_strength": 1.0,
            "round_budget_remaining": 1.0,
            "source_budget_remaining": 1.0,
        },
        "pheromone_expire": {
            "action": "expire",
            "target": "decision:e2e",
            "candidate_id": "candidate:alpha",
            "subject_type": "candidate",
            "subject_id": "candidate:alpha",
            "kind": "stale",
            "source_kind": "positive",
            "source_id": "scout:a",
            "provenance": "driver:a",
            "source_trace_event_id": "trace:deposit:a",
            "trace_event_id": "trace:deposit:a",
            "old_strength": 1.0,
            "source_strength": 1.0,
            "requested_strength": 1.0,
            "applied_strength": 0.0,
            "new_strength": 0.0,
            "strength_delta": -1.0,
            "step": 2,
            "source_updated_at_step": 1,
            "deposited_at_step": 1,
            "ttl_steps": 1,
            "elapsed_steps": 1,
        },
        "pheromone_observe": {
            "candidate_id": "candidate:alpha",
            "subject_type": "route",
            "subject_id": "route:alpha",
            "novelty_pressure": 0.1,
            "reopen_eligible": True,
            "source_trace_event_id": "trace:deposit:a",
        },
        "pheromone_score": {
            "scores": {"candidate:alpha": 1.5},
            "score_breakdown": {"candidate:alpha": {"pheromone_positive": 1.5}},
            "kind_breakdown": {"candidate:alpha": {"positive": 1.5}},
            "subject_breakdown": {"candidate:alpha": {"candidate": 1.5}},
            "active_trails": [
                {
                    "trace_event_id": "trace:deposit:a",
                    "source_id": "agent:a",
                    "provenance": "driver:a",
                    "candidate_id": "candidate:alpha",
                    "subject_type": "candidate",
                    "subject_id": "candidate:alpha",
                    "kind": "positive",
                    "source_kind": "positive",
                    "strength": 1.5,
                    "provenance": "driver:a",
                    "deposited_at_step": 1,
                    "updated_at_step": 1,
                    "ttl_steps": None,
                }
            ],
            "current_step": 1,
        },
        "pheromone_normalize": {
            "candidates": ["candidate:alpha"],
            "pre_scores": {"candidate:alpha": 2.0},
            "post_scores": {"candidate:alpha": 1.0},
            "response_model": "competitive",
            "competition_mode": "normalize",
        },
        "layer_proposal": {
            "layer_id": "learned",
            "source_id": "layer:a",
            "action": "support",
            "effect": "candidate_preference",
            "candidate_id": "candidate:alpha",
            "confidence": 0.8,
            "support": 1.0,
            "risk": 0.0,
            "proposed_strength": 0.0,
            "proposed_pheromone_kind": "",
            "subject_type": "candidate",
            "subject_id": "candidate:alpha",
            "evidence_id": "evidence:a",
            "provenance": "runtime:a",
            "source_trace_event_id": "trace:proposal:a",
        },
        "coordination_assess": {
            "confidences": {
                "reactive": 0.0,
                "learned": 0.8,
                "evolutionary": 0.0,
                "metacognitive": 0.0,
            },
            "weights": {
                "reactive": 1.0,
                "learned": 1.0,
                "evolutionary": 0.5,
                "metacognitive": 0.5,
            },
            "snapshots": {
                layer_id: {
                    "present": layer_id == "learned",
                    "recent_success_rate": 0.8 if layer_id == "learned" else 0.0,
                    "recent_conflict_rate": 0.1 if layer_id == "learned" else 0.0,
                    "recent_fallback_rate": 0.1 if layer_id == "learned" else 0.0,
                    "mean_confidence": 0.8 if layer_id == "learned" else 0.0,
                    "evidence_coverage": 1.0 if layer_id == "learned" else 0.0,
                    "trace_coverage": 1.0 if layer_id == "learned" else 0.0,
                }
                for layer_id in (
                    "reactive",
                    "learned",
                    "evolutionary",
                    "metacognitive",
                )
            },
            "coverage": {"learned": {"evidence": 1.0, "trace": 1.0}},
            "action_effects": {"trace:proposal:a": "candidate_preference"},
            "trace_coverage_confirmations": {},
            "proposal_lineage": ["trace:proposal:a"],
        },
        "coordination_resolve": {
            "conflicts": ["candidate_contention"],
            "resolution": "safe_fallback_for_layer_conflict",
            "selected_candidate": "candidate:safe",
            "fallback_used": True,
            "reason": "safe_fallback_for_layer_conflict",
            "proposal_lineage": ["trace:proposal:a"],
        },
        "policy_adjustment": {
            "proposed_values": {"pheromone_evaporation_rate": 0.2},
            "declared_bounds": {"pheromone_evaporation_rate": [0.1, 0.5]},
            "result": "accepted",
            "source_id": "layer:evolutionary",
            "layer_id": "evolutionary",
            "provenance": "runtime:evolutionary",
            "source_trace_event_id": "trace:adjustment:evolutionary",
        },
        "candidate_score": {
            "scores": {"candidate:alpha": 3.0},
            "score_breakdown": {"candidate:alpha": {"scout": 2.0, "pheromone": 1.0}},
            "scout_diversity": {"candidate:alpha": 1},
            "pheromone_source_diversity": {"candidate:alpha": 1},
        },
        "consensus_check": {
            "quorum_threshold": 3.0,
            "min_independent_scouts": 1,
        },
        "commit": {
            "target": "decision:e2e",
            "candidate_id": "candidate:alpha",
            "decision_reason": "collective_consensus",
            "upstream_score_lineage": ["trace:score:1"],
        },
        "fallback": {
            "target": "decision:e2e",
            "candidate_id": "candidate:safe",
            "decision_reason": "safe_collective_fallback",
            "upstream_score_lineage": ["trace:score:1"],
        },
        "output": {
            "committed_candidate": True,
            "evidence_provenance": True,
            "stop_resolution": True,
            "publication_permission": True,
            "authorized": True,
        },
    }
    return lineages.get(event_type, {})
