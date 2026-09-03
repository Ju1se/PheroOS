from hashlib import sha256
import json
from typing import cast

import pytest

from pheroos.trace._contracts.commit_certificate_authority import (
    COMMIT_CERTIFICATE_EVENT_TYPES,
)
from pheroos.trace._contracts.commit_decision_authority import (
    COMMIT_DECISION_EVENT_TYPES,
)
from pheroos.trace._contracts.commit_evidence_authority import (
    COMMIT_EVIDENCE_AUTHORITY_TRACE_EVENT_CONTRACTS,
)
from pheroos.trace._contracts.distributed_authority import (
    DISTRIBUTED_AUTHORITY_EVENT_TYPES,
)
from pheroos.trace import (
    COMMIT_EVENT_TYPES,
    EVENT_LINEAGE_CONTRACTS,
    InMemoryTraceStore,
    TraceEvent,
    VALID_EVENT_TYPES,
)
from pheroos.trace._pheromone_receipts import (
    canonical_pheromone_clip_payload,
    pheromone_clip_payload_fingerprint,
)


_COMMIT_EVIDENCE_EVENT_TYPES = frozenset(
    contract.event_type for contract in COMMIT_EVIDENCE_AUTHORITY_TRACE_EVENT_CONTRACTS
)


def test_trace_store_appends_records_and_validates_required_events() -> None:
    store = InMemoryTraceStore()
    generic_event_types = (
        VALID_EVENT_TYPES
        - COMMIT_EVENT_TYPES
        - COMMIT_CERTIFICATE_EVENT_TYPES
        - COMMIT_DECISION_EVENT_TYPES
        - _COMMIT_EVIDENCE_EVENT_TYPES
        - DISTRIBUTED_AUTHORITY_EVENT_TYPES
    )
    for event_type in sorted(generic_event_types):
        protocol_id, target = valid_event_context(event_type)
        store.append(
            TraceEvent(
                event_type=event_type,
                protocol_id=protocol_id,
                target=target,
                reason="test",
                lineage=valid_lineage(event_type),
            )
        )

    assert [record.sequence for record in store.records] == list(
        range(len(generic_event_types))
    )
    assert store.require_events(["plan", "invoke", "output"]) == []


def test_pheromone_clip_payload_receipt_is_canonical_and_finite() -> None:
    left = {"lifecycle": "feedback", "input": {"b": [2, 3], "a": 1.0}}
    right = {"input": {"a": 1.0, "b": [2, 3]}, "lifecycle": "feedback"}

    assert canonical_pheromone_clip_payload(left) == canonical_pheromone_clip_payload(
        right
    )
    assert pheromone_clip_payload_fingerprint(
        left
    ) == pheromone_clip_payload_fingerprint(right)
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
    assert (
        store.require_events(
            ["pheromone_deposit", "pheromone_score", "pheromone_expire"]
        )
        == []
    )


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
                ],
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
        if event_type
        not in (
            COMMIT_EVENT_TYPES
            | COMMIT_CERTIFICATE_EVENT_TYPES
            | COMMIT_DECISION_EVENT_TYPES
            | _COMMIT_EVIDENCE_EVENT_TYPES
            | DISTRIBUTED_AUTHORITY_EVENT_TYPES
        )
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
        layer_id: dict(snapshot) for layer_id, snapshot in lineage["snapshots"].items()
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


def test_policy_adjustment_trace_accepts_enum_bounds_and_records_bounded_rejection() -> (
    None
):
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
        "issuer_grant_activated": {
            **_authority_common(
                _authority_stream("issuer-grant", "scope:test", "grant:test")
            ),
            "profile": "pheroos-scoped-authority-local-v2",
            "grant_ref": "grant:test",
            "grant_root": _trace_root("grant"),
            "grant_binding_ref": _trace_root("grant-binding"),
            "observed_epoch": 1,
            "revocation_generation": 0,
            "verification_root": None,
        },
        "issuer_grant_revoked": {
            **_authority_common(
                _authority_stream("issuer-grant", "scope:test", "grant:test")
            ),
            "profile": "pheroos-scoped-authority-local-v2",
            "grant_ref": "grant:test",
            "grant_root": _trace_root("grant"),
            "grant_binding_ref": _trace_root("grant-binding"),
            "observed_epoch": 2,
            "revocation_generation": 1,
        },
        "signal_verified": {
            **_authority_common(
                _authority_stream(
                    "verified-signal",
                    "scope:test",
                    "signal:test",
                    "target:test",
                )
            ),
            **_authority_session("verify_signal", ["target:test"]),
            "target_ref": "target:test",
            "signal_ref": "signal:test",
            "signal_root": _trace_root("signal"),
            "evidence_root": _trace_root("evidence"),
        },
        "domain_retired": {
            **_authority_common("authority:domain-lifecycle"),
            **_authority_session("retire_domain", []),
            "reason_ref": "reason:test",
            "final_heads_root": _trace_root("final-heads"),
            "seal_root": _trace_root("seal"),
        },
        "baseline_manifest_activated": {
            **_baseline_authority("baseline_manifest_activated"),
            "protocol_ref": "protocol:test",
        },
        "baseline_evidence_qualified": {
            **_baseline_authority("baseline_evidence_qualified"),
            "evidence_root": _trace_root("evidence"),
            "qualified_signal_count": 1,
        },
        "baseline_stop_resolved": {
            **_baseline_authority("baseline_stop_resolved"),
            "stop_root": _trace_root("stop"),
        },
        "baseline_decision_evaluated": {
            **_baseline_authority("baseline_decision_evaluated"),
            **_baseline_decision(),
        },
        "baseline_action_permission_issued": {
            **_baseline_authority("baseline_action_permission_issued"),
            **_baseline_decision(),
            "effect": "publish",
            "output_payload_root": _trace_root("output-payload"),
            "permission_root": _trace_root("permission"),
            "permission_disposition": "authorized",
            "expires_at_epoch": 2,
        },
        "baseline_output_committed": {
            **_baseline_authority(
                "baseline_output_committed",
                operation="authorize_output",
            ),
            **_baseline_decision(),
            "effect": "publish",
            "output_payload_root": _trace_root("output-payload"),
            "permission_root": _trace_root("permission"),
            "result_root": _trace_root("result"),
            "delivery_disposition": "deliverable",
            "action_disposition": "authorized",
            "read_set_root": _trace_root("read-set"),
        },
        "hybrid_replay_advanced": _hybrid_replay_authority(),
        "commit_replay_advanced": _commit_replay_authority(),
        "commit_stop_resolved_v2": _commit_gate_authority("stop"),
        "commit_permission_issued_v2": _commit_gate_authority("permission"),
        "risk_state_advanced": _risk_authority(),
        "principal_verification_set_advanced": _principal_verification_authority(),
        "membership_epoch_committed": _membership_authority(),
        "support_state_advanced": _support_state_authority(),
        "support_lease_issued_v2": _support_lease_issued_authority(),
        "support_lease_revoked_v2": _support_lease_revoked_authority(),
        "risk_assessed_v2": {
            **_risk_authority(),
            "assessment_ref": "assessment:test",
            "issuer_ref": "issuer:test",
            "risk_band": "LOW",
            "risk_input_roots": [_trace_root("risk-input")],
            "rationale_codes": ["risk:low"],
            "assessment_method": "method:test",
            "issued_at_step": 0,
            "expires_at_step": 2,
            "previous_assessment_root": "",
            "window_reset_required": False,
            "provenance_ref": "provenance:test",
            "source_trace_roots": [_trace_root("source-trace")],
        },
    }
    return lineages.get(event_type, {})


_AUTHORITY_EVENT_TYPES = frozenset(
    {
        "baseline_action_permission_issued",
        "baseline_decision_evaluated",
        "baseline_evidence_qualified",
        "baseline_manifest_activated",
        "baseline_output_committed",
        "baseline_stop_resolved",
        "issuer_grant_activated",
        "issuer_grant_revoked",
        "hybrid_replay_advanced",
        "commit_replay_advanced",
        "commit_stop_resolved_v2",
        "commit_permission_issued_v2",
        "risk_state_advanced",
        "risk_assessed_v2",
        "principal_verification_set_advanced",
        "membership_epoch_committed",
        "support_state_advanced",
        "support_lease_issued_v2",
        "support_lease_revoked_v2",
        "signal_verified",
        "domain_retired",
    }
)


def valid_event_context(event_type: str) -> tuple[str, str]:
    if event_type not in _AUTHORITY_EVENT_TYPES:
        return "e2e.review", "decision:e2e"
    target = {
        "issuer_grant_activated": "grant:test",
        "issuer_grant_revoked": "grant:test",
        "signal_verified": "target:test",
        "domain_retired": "scope:test",
        "baseline_action_permission_issued": "target:test",
        "baseline_decision_evaluated": "target:test",
        "baseline_evidence_qualified": "target:test",
        "baseline_manifest_activated": "target:test",
        "baseline_output_committed": "target:test",
        "baseline_stop_resolved": "target:test",
        "hybrid_replay_advanced": "target:test",
        "commit_replay_advanced": "target:test",
        "commit_stop_resolved_v2": "target:test",
        "commit_permission_issued_v2": "target:test",
        "risk_state_advanced": "target:test",
        "risk_assessed_v2": "target:test",
        "principal_verification_set_advanced": "target:test",
        "membership_epoch_committed": "target:test",
        "support_state_advanced": "target:test",
        "support_lease_issued_v2": "target:test",
        "support_lease_revoked_v2": "target:test",
    }[event_type]
    return "pheroos.protocol.v2", target


def _trace_root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _authority_stream(kind: str, *bindings: str) -> str:
    payload = b"\x00".join(item.encode("utf-8") for item in bindings)
    return f"authority:{kind}:{sha256(payload).hexdigest()}"


def _durable_membership_source_root(
    event_type: str,
    lineage: dict[str, object],
) -> str:
    if event_type == "principal_verification_set_advanced":
        kind = "principal-verification-v2:source-context"
        body = {
            "version": "pheroos-principal-verification-source-v2",
            "request_root": lineage["request_root"],
            "manifest_root": lineage["manifest_root"],
            "authority_policy_root": lineage["authority_policy_root"],
            "commit_policy_root": lineage["commit_policy_root"],
            "verification_policy_root": lineage["verification_policy_root"],
            "verification_set_root": lineage["verification_set_root"],
        }
    else:
        kind = "membership-v2:source-context"
        body = {
            "version": "pheroos-membership-source-v2",
            "request_root": lineage["request_root"],
            "manifest_root": lineage["manifest_root"],
            "authority_policy_root": lineage["authority_policy_root"],
            "commit_policy_root": lineage["commit_policy_root"],
            "membership_policy_root": lineage["membership_policy_root"],
            "verification_set_root": lineage["verification_set_root"],
            "membership_root": lineage["membership_root"],
        }
    return _durable_membership_root(kind, body)


def _durable_membership_read_set_root(
    event_type: str,
    lineage: dict[str, object],
) -> str:
    binding = lineage["session_binding"]
    assert isinstance(binding, dict)
    scope_ref = lineage["scope_ref"]
    grant_ref = lineage["grant_ref"]
    assert isinstance(scope_ref, str)
    assert isinstance(grant_ref, str)
    entries = [
        {
            "expected_revision": lineage["parent_revision"],
            "expected_root": lineage["parent_head_root"],
            "stream_ref": lineage["stream_ref"],
        },
        {
            "expected_revision": binding["grant_expected_revision"],
            "expected_root": binding["grant_expected_root"],
            "stream_ref": _authority_stream("issuer-grant", scope_ref, grant_ref),
        },
        {
            "expected_revision": binding["lifecycle_expected_revision"],
            "expected_root": binding["lifecycle_expected_root"],
            "stream_ref": "authority:domain-lifecycle",
        },
    ]
    if event_type == "membership_epoch_committed":
        entries.append(
            {
                "expected_revision": lineage["verification_revision"],
                "expected_root": lineage["verification_head_root"],
                "stream_ref": lineage["verification_stream_ref"],
            }
        )
    entries.sort(key=lambda item: str(item["stream_ref"]).encode("utf-8"))
    payload = {
        "canonical_version": "pheroos-authority-canonical-v2",
        "entries": entries,
        "schema": "pheroos-governance-authority-read-set-v2",
    }
    return "sha256:" + sha256(_canonical_json_bytes(payload)).hexdigest()


def _durable_membership_root(kind: str, body: object) -> str:
    prefix = f"pheroos-governance-authority-v2:{kind}".encode("utf-8")
    return (
        "sha256:" + sha256(prefix + b"\x00" + _canonical_json_bytes(body)).hexdigest()
    )


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _authority_common(stream_ref: str) -> dict[str, object]:
    return {
        "domain_root": _trace_root("domain"),
        "scope_ref": "scope:test",
        "stream_ref": stream_ref,
        "transition_id": "transition:test",
    }


def _authority_session(
    operation: str,
    target_refs: list[str],
    action_refs: list[str] | None = None,
) -> dict[str, object]:
    binding = {
        "domain_root": _trace_root("domain"),
        "scope_ref": "scope:test",
        "run_ref": "run:test",
        "request_ref": "request:test",
        "request_root": _trace_root("request"),
        "operation": operation,
        "observed_epoch": 1,
        "grant_ref": "grant:test",
        "grant_root": _trace_root("grant"),
        "grant_binding_ref": _trace_root("grant-binding"),
        "grant_expected_revision": 1,
        "grant_expected_root": _trace_root("grant-head"),
        "lifecycle_expected_revision": 0,
        "lifecycle_expected_root": _trace_root("lifecycle-head"),
        "target_refs": target_refs,
        "action_refs": [] if action_refs is None else action_refs,
    }
    return {
        "run_ref": binding["run_ref"],
        "request_ref": binding["request_ref"],
        "request_root": binding["request_root"],
        "grant_ref": binding["grant_ref"],
        "grant_root": binding["grant_root"],
        "grant_binding_ref": binding["grant_binding_ref"],
        "operation": operation,
        "observed_epoch": binding["observed_epoch"],
        "session_binding": binding,
    }


def _baseline_authority(
    event_type: str,
    *,
    operation: str = "issue_action_permission",
) -> dict[str, object]:
    return {
        **_authority_common(f"authority:baseline-output:{event_type}"),
        **_authority_session(
            operation,
            ["target:test"],
            ["action:publish"],
        ),
        "target_ref": "target:test",
        "action_ref": "action:publish",
        "manifest_root": _trace_root("manifest"),
        "output_policy_root": _trace_root("output-policy"),
    }


def _baseline_decision() -> dict[str, object]:
    return {
        "evidence_root": _trace_root("evidence"),
        "stop_root": _trace_root("stop"),
        "decision_root": _trace_root("decision"),
        "candidate_ref": "candidate:test",
        "terminal_status": "evidence_commit",
    }


def _hybrid_replay_authority() -> dict[str, object]:
    target_ref = "target:test"
    scope_ref = "scope:test"
    protocol_ref = "protocol:hybrid-replay"
    run_ref = "run:test"
    advance_ref = "advance:test"
    stream_ref = _authority_stream(
        "hybrid-replay-v2",
        scope_ref,
        protocol_ref,
        run_ref,
        target_ref,
    )
    transition_payload = b"\x00".join(
        (stream_ref.encode("utf-8"), advance_ref.encode("utf-8"))
    )
    transition_id = (
        "transition:hybrid-replay-v2:" + sha256(transition_payload).hexdigest()
    )
    session = _authority_session("advance_replay", [target_ref])
    session["request_ref"] = advance_ref
    session_binding = session["session_binding"]
    assert isinstance(session_binding, dict)
    session_binding["request_ref"] = advance_ref
    return {
        **_authority_common(stream_ref),
        **session,
        "transition_id": transition_id,
        "target_ref": target_ref,
        "advance_ref": advance_ref,
        "protocol_ref": protocol_ref,
        "manifest_root": _trace_root("manifest"),
        "candidate_set_root": _trace_root("candidate-set"),
        "hybrid_policy_root": _trace_root("hybrid-policy"),
        "effective_policy_root": _trace_root("effective-policy"),
        "topology_root": _trace_root("topology"),
        "revision": 1,
        "current_step": 0,
        "parent_transition_id": None,
        "parent_snapshot_root": None,
        "parent_head_root": _trace_root("genesis-head"),
        "snapshot_root": _trace_root("snapshot"),
        "memory_root": _trace_root("memory"),
        "replay_receipt_root": _trace_root("replay-receipts"),
        "source_step_root": _trace_root("source-step"),
        "source_trace_root": _trace_root("source-trace"),
        "read_set_root": _trace_root("read-set"),
    }


def _commit_replay_authority() -> dict[str, object]:
    target_ref = "target:test"
    scope_ref = "scope:test"
    protocol_ref = "protocol:commit-replay"
    run_ref = "run:test"
    advance_ref = "advance:test"
    stream_ref = _authority_stream(
        "commit-replay-v2", scope_ref, protocol_ref, run_ref, target_ref
    )
    transition_payload = b"\x00".join(
        (stream_ref.encode("utf-8"), advance_ref.encode("utf-8"))
    )
    transition_id = (
        "transition:commit-replay-v2:" + sha256(transition_payload).hexdigest()
    )
    session = _authority_session("advance_replay", [target_ref])
    session["request_ref"] = advance_ref
    session_binding = session["session_binding"]
    assert isinstance(session_binding, dict)
    session_binding["request_ref"] = advance_ref
    return {
        **_authority_common(stream_ref),
        **session,
        "transition_id": transition_id,
        "target_ref": target_ref,
        "advance_ref": advance_ref,
        "protocol_ref": protocol_ref,
        "manifest_root": _trace_root("manifest"),
        "commit_policy_root": _trace_root("commit-policy"),
        "profile": "pheroos-commit-integrity-v1",
        "assurance": "evidence_bound",
        "revision": 1,
        "current_step": 0,
        "parent_transition_id": "genesis",
        "parent_snapshot_root": _trace_root("genesis-snapshot"),
        "parent_head_root": _trace_root("genesis-head"),
        "snapshot_root": _trace_root("snapshot"),
        "replay_receipt_root": _trace_root("replay-receipts"),
        "receipt_addition_root": _trace_root("receipt-additions"),
        "source_context_root": _trace_root("source-context"),
        "read_set_root": _trace_root("read-set"),
    }


def _commit_gate_authority(kind: str) -> dict[str, object]:
    from pheroos.trace._contracts.commit_gate_authority import (
        _expected_read_set_root,
        _request_wire,
        _root,
        _snapshot_wire,
    )

    target_ref = "target:test"
    scope_ref = "scope:test"
    protocol_ref = "protocol:commit-gate"
    run_ref = "run:test"
    request_field = "resolution_ref" if kind == "stop" else "permission_ref"
    request_ref = f"{kind}:test"
    stream_material = (scope_ref, protocol_ref, run_ref, target_ref, "commit")
    stream_ref = (
        f"authority:commit-{kind}-v2:"
        + sha256("\x00".join(stream_material).encode("utf-8")).hexdigest()
    )
    transition_id = (
        f"transition:commit-{kind}-v2:"
        + sha256(
            stream_ref.encode("utf-8") + b"\x00" + request_ref.encode("utf-8")
        ).hexdigest()
    )
    operation = "resolve_stop" if kind == "stop" else "issue_action_permission"
    session = _authority_session(
        operation,
        [target_ref],
        [] if kind == "stop" else ["commit"],
    )
    session["request_ref"] = request_ref
    binding = session["session_binding"]
    assert isinstance(binding, dict)
    binding["request_ref"] = request_ref
    dependency_body: dict[str, object] = {
        "schema": "pheroos-commit-gate-dependencies-v2",
        "canonical_version": "pheroos-authority-canonical-v2",
    }
    dependency_lineage: dict[str, object] = {}
    for index, name in enumerate(
        ("replay", "risk", "verification", "membership", "support"), 1
    ):
        dependency_lineage.update(
            {
                f"{name}_stream_ref": f"authority:{name}:test",
                f"{name}_revision": index,
                f"{name}_transition_id": f"transition:{name}:test",
                f"{name}_snapshot_root": _trace_root(f"{name}-snapshot"),
                f"{name}_head_root": _trace_root(f"{name}-head"),
            }
        )
    dependency_body.update(dependency_lineage)
    dependency_root = _root("dependencies", dependency_body)
    manifest_root = _trace_root("manifest")
    commit_policy_root = _trace_root("commit-policy")
    policy_root = _root(
        f"{kind}-policy",
        {
            "policy_version": f"pheroos-commit-{kind}-policy-v2",
            "authority_operation": operation,
            "manifest_root": manifest_root,
            "commit_policy_root": commit_policy_root,
            "protocol_ref": protocol_ref,
            "target_ref": target_ref,
        },
    )
    lineage: dict[str, object] = {
        **_authority_common(stream_ref),
        **session,
        **dependency_lineage,
        "transition_id": transition_id,
        "target_ref": target_ref,
        "protocol_ref": protocol_ref,
        "manifest_root": manifest_root,
        "commit_policy_root": commit_policy_root,
        "policy_root": policy_root,
        "profile": "pheroos-commit-integrity-v1",
        "assurance": "evidence_bound",
        "revision": 1,
        "current_step": 5,
        "parent_revision": 0,
        "parent_transition_id": "genesis",
        "parent_snapshot_root": _root(
            f"{kind}-genesis-parent",
            {"schema": f"pheroos-commit-{kind}-snapshot-v2"},
        ),
        "parent_head_root": _trace_root("genesis-head"),
        "snapshot_root": _trace_root("placeholder-snapshot"),
        "mutation_issuer_ref": "issuer:test",
        "grant_issuer_ref": "issuer:test",
        "issued_at_step": 5,
        "expires_at_step": 10,
        "dependency_root": dependency_root,
        "evaluation_context_root": "",
        "source_context_root": _trace_root("placeholder-source"),
        "read_set_root": _trace_root("placeholder-read-set"),
        request_field: request_ref,
    }
    lineage["evaluation_context_root"] = _root(
        "evaluation-context",
        {
            "version": "pheroos-commit-gate-context-v2",
            "domain_root": lineage["domain_root"],
            "scope_ref": lineage["scope_ref"],
            "manifest_root": manifest_root,
            "commit_policy_root": commit_policy_root,
            "profile": lineage["profile"],
            "assurance": lineage["assurance"],
            "protocol_ref": protocol_ref,
            "run_ref": run_ref,
            "target_ref": target_ref,
            "observed_epoch": lineage["observed_epoch"],
            "current_step": lineage["current_step"],
            "dependency_root": dependency_root,
        },
    )
    if kind == "stop":
        reasons = ["stop:clear"]
        decision = {
            "resolution_ref": request_ref,
            "blocked": False,
            "reason_codes": reasons,
            "reason_root": _root("stop-reasons", {"reason_codes": reasons}),
        }
    else:
        candidates = ["candidate:test"]
        claims = [_trace_root("claim")]
        decision = {
            "permission_ref": request_ref,
            "allowed": True,
            "candidate_refs": candidates,
            "candidate_set_root": _root(
                "candidate-set", {"candidate_refs": candidates}
            ),
            "claim_roots": claims,
            "claims_root": _root("claims", {"claim_roots": claims}),
        }
    lineage.update(decision)
    snapshot = _snapshot_wire(lineage, dependency_body, decision, kind=kind)
    lineage["snapshot_root"] = snapshot["snapshot_root"]
    request = _request_wire(lineage, snapshot, kind=kind)
    lineage["request_root"] = request["request_root"]
    binding["request_root"] = request["request_root"]
    lineage["source_context_root"] = _root(
        "source-context",
        {
            "kind": kind,
            "request_root": request["request_root"],
            "evaluation_context_root": lineage["evaluation_context_root"],
            "dependency_root": dependency_root,
        },
    )
    lineage["read_set_root"] = _expected_read_set_root(lineage)
    return lineage


def _risk_authority() -> dict[str, object]:
    target_ref = "target:test"
    scope_ref = "scope:test"
    protocol_ref = "protocol:risk"
    run_ref = "run:test"
    advance_ref = "advance:test"
    profile = "pheroos-commit-integrity-v1"
    assurance = "evidence_bound"
    manifest_root = _trace_root("manifest")
    commit_policy_root = _trace_root("commit-policy")
    risk_policy_root = _trace_root("risk-policy")
    stream_ref = _authority_stream(
        "risk-v2",
        scope_ref,
        profile,
        assurance,
        manifest_root,
        commit_policy_root,
        risk_policy_root,
        protocol_ref,
        run_ref,
        target_ref,
    )
    transition_id = (
        "transition:risk-v2:"
        + sha256(
            stream_ref.encode("utf-8") + b"\x00" + advance_ref.encode("utf-8")
        ).hexdigest()
    )
    session = _authority_session("qualify_evidence", [target_ref])
    session["request_ref"] = advance_ref
    session_binding = session["session_binding"]
    assert isinstance(session_binding, dict)
    session_binding["request_ref"] = advance_ref
    return {
        **_authority_common(stream_ref),
        **session,
        "transition_id": transition_id,
        "target_ref": target_ref,
        "advance_ref": advance_ref,
        "protocol_ref": protocol_ref,
        "manifest_root": manifest_root,
        "commit_policy_root": commit_policy_root,
        "risk_policy_root": risk_policy_root,
        "profile": profile,
        "assurance": assurance,
        "revision": 1,
        "epoch": 1,
        "parent_epoch": None,
        "current_step": 0,
        "parent_transition_id": "genesis",
        "parent_snapshot_root": (
            "sha256:c5a27a1c3b2313e09395f6fec7602b17e30e58334bc9a33b335a2135c1a55ec2"
        ),
        "parent_head_root": _trace_root("genesis-head"),
        "snapshot_root": _trace_root("risk-snapshot"),
        "assessment_root": _trace_root("assessment"),
        "threshold_root": _trace_root("threshold"),
        "source_context_root": _trace_root("source-context"),
        "read_set_root": _trace_root("read-set"),
    }


def _principal_verification_authority() -> dict[str, object]:
    policy_root = _trace_root("verification-policy")
    lineage = _durable_membership_authority(
        stream_kind="principal-verification-v2",
        operation="qualify_evidence",
        policy_root=policy_root,
        request_ref="advance:verification:test",
        genesis_root=(
            "sha256:250b6db081d9b7bd133f06b6c3192bb409c2f97e2bb462d2c0302d81bbda7ec5"
        ),
    )
    result = {
        **lineage,
        "verification_policy_root": policy_root,
        "verification_set_root": _trace_root("verification-set"),
        "record_count": 2,
        "current_step": 2,
        "expires_at_step": 100,
        "verification_roots": sorted(
            [
                _trace_root("verification:alpha"),
                _trace_root("verification:beta"),
            ],
            key=lambda value: value.encode("utf-8"),
        ),
    }
    result["source_context_root"] = _durable_membership_source_root(
        "principal_verification_set_advanced",
        result,
    )
    result["read_set_root"] = _durable_membership_read_set_root(
        "principal_verification_set_advanced",
        result,
    )
    return result


def _membership_authority() -> dict[str, object]:
    policy_root = _trace_root("membership-policy")
    lineage = _durable_membership_authority(
        stream_kind="membership-v2",
        operation="evaluate_quorum",
        policy_root=policy_root,
        request_ref="request:membership:test",
        genesis_root=(
            "sha256:442d957d649f827ae3be2c4389d9ca281f25c86355f54fb1efc0895c61f3c797"
        ),
    )
    verification_policy_root = _trace_root("verification-policy")
    verification_stream = _authority_stream(
        "principal-verification-v2",
        cast(str, lineage["scope_ref"]),
        cast(str, lineage["profile"]),
        cast(str, lineage["assurance"]),
        cast(str, lineage["manifest_root"]),
        cast(str, lineage["commit_policy_root"]),
        verification_policy_root,
        cast(str, lineage["protocol_ref"]),
        cast(str, lineage["run_ref"]),
        cast(str, lineage["target_ref"]),
    )
    verification_request = "advance:verification:test"
    verification_transition = (
        "transition:principal-verification-v2:"
        + sha256(
            verification_stream.encode("utf-8")
            + b"\x00"
            + verification_request.encode("utf-8")
        ).hexdigest()
    )
    result = {
        **lineage,
        "membership_policy_root": policy_root,
        "membership_root": _trace_root("membership"),
        "cluster_count": 1,
        "principal_count": 2,
        "issued_at_step": 2,
        "expires_at_step": 100,
        "verification_stream_ref": verification_stream,
        "verification_transition_id": verification_transition,
        "verification_policy_root": verification_policy_root,
        "verification_request_ref": verification_request,
        "verification_revision": 1,
        "verification_head_root": _trace_root("verification-head"),
        "verification_snapshot_root": _trace_root("verification-snapshot"),
        "verification_set_root": _trace_root("verification-set"),
        "verification_current_step": 2,
        "verification_expires_at_step": 100,
        "verification_record_count": 2,
        "source_trace_roots": sorted(
            [_trace_root("membership-source:a"), _trace_root("membership-source:b")],
            key=lambda value: value.encode("utf-8"),
        ),
    }
    result["source_context_root"] = _durable_membership_source_root(
        "membership_epoch_committed",
        result,
    )
    result["read_set_root"] = _durable_membership_read_set_root(
        "membership_epoch_committed",
        result,
    )
    return result


def _durable_membership_authority(
    *,
    stream_kind: str,
    operation: str,
    policy_root: str,
    request_ref: str,
    genesis_root: str,
) -> dict[str, object]:
    target_ref = "target:test"
    scope_ref = "scope:test"
    protocol_ref = "protocol:membership"
    run_ref = "run:test"
    profile = "pheroos-commit-integrity-v1"
    assurance = "evidence_bound"
    manifest_root = _trace_root("manifest")
    commit_policy_root = _trace_root("commit-policy")
    stream_ref = _authority_stream(
        stream_kind,
        scope_ref,
        profile,
        assurance,
        manifest_root,
        commit_policy_root,
        policy_root,
        protocol_ref,
        run_ref,
        target_ref,
    )
    transition_id = (
        f"transition:{stream_kind}:"
        + sha256(
            stream_ref.encode("utf-8") + b"\x00" + request_ref.encode("utf-8")
        ).hexdigest()
    )
    session = _authority_session(operation, [target_ref])
    session["request_ref"] = request_ref
    session_binding = session["session_binding"]
    assert isinstance(session_binding, dict)
    session_binding["request_ref"] = request_ref
    return {
        **_authority_common(stream_ref),
        **session,
        "transition_id": transition_id,
        "target_ref": target_ref,
        "protocol_ref": protocol_ref,
        "profile": profile,
        "assurance": assurance,
        "authority_policy_root": _trace_root("authority-policy"),
        "manifest_root": manifest_root,
        "commit_policy_root": commit_policy_root,
        "epoch": 1,
        "revision": 1,
        "parent_revision": 0,
        "parent_epoch": None,
        "parent_transition_id": "genesis",
        "parent_snapshot_root": genesis_root,
        "parent_head_root": _trace_root(f"{stream_kind}:genesis-head"),
        "snapshot_root": _trace_root(f"{stream_kind}:snapshot"),
        "mutation_issuer_ref": "issuer:test",
        "grant_issuer_ref": "issuer:test",
        "source_context_root": _trace_root(f"{stream_kind}:source-context"),
        "read_set_root": _trace_root(f"{stream_kind}:read-set"),
    }


def _support_root(kind: str, body: object) -> str:
    payload = json.dumps(
        body,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    prefix = f"pheroos-governance-authority-v2:support-v2:{kind}".encode()
    return "sha256:" + sha256(prefix + b"\x00" + payload).hexdigest()


def _support_authority(request_ref: str) -> dict[str, object]:
    target_ref = "target:test"
    scope_ref = "scope:test"
    profile = "pheroos-commit-integrity-v1"
    assurance = "evidence_bound"
    manifest_root = _trace_root("manifest")
    commit_policy_root = _trace_root("commit-policy")
    protocol_ref = "protocol:support"
    run_ref = "run:test"
    stream_ref = _authority_stream(
        "support-v2",
        scope_ref,
        profile,
        assurance,
        manifest_root,
        commit_policy_root,
        protocol_ref,
        run_ref,
        target_ref,
    )
    transition_id = (
        "transition:support-v2:"
        + sha256(
            stream_ref.encode("utf-8") + b"\x00" + request_ref.encode("utf-8")
        ).hexdigest()
    )
    session = _authority_session("qualify_evidence", [target_ref])
    session["request_ref"] = request_ref
    binding = session["session_binding"]
    assert isinstance(binding, dict)
    binding["request_ref"] = request_ref
    return {
        **_authority_common(stream_ref),
        **session,
        "transition_id": transition_id,
        "profile": profile,
        "assurance": assurance,
        "manifest_root": manifest_root,
        "commit_policy_root": commit_policy_root,
        "authority_policy_root": _trace_root("authority-policy"),
        "protocol_ref": protocol_ref,
        "target_ref": target_ref,
        "mutation_issuer_ref": "issuer:support",
    }


def _support_state_authority() -> dict[str, object]:
    lineage = _support_authority("mutation:support:initialize")
    current_step = 2
    mutation_provenance_root = _trace_root("support:mutation-provenance")
    mutation_trace_roots = [_trace_root("support:mutation-trace")]
    delta = _support_root(
        "mutation-delta",
        {
            "mutation_kind": "initialize",
            "transition_id": lineage["transition_id"],
            "mutation_issuer_ref": lineage["mutation_issuer_ref"],
            "observed_epoch": lineage["observed_epoch"],
            "current_step": current_step,
            "mutation_provenance_root": mutation_provenance_root,
            "mutation_trace_roots": mutation_trace_roots,
            "issued_lease_root": "",
            "revoked_lease_root": "",
            "revocation_root": "",
            "evicted_lease_roots": [],
            "membership_stream_ref": "",
            "membership_transition_id": "",
            "membership_snapshot_root": "",
        },
    )
    parent_history_root = (
        "sha256:b59daa9f35cdad62195ecc31ee2ca1f9b3ab0991f73a95f171a6b41b4c8d856d"
    )
    history = _support_root(
        "history-link",
        {
            "parent_history_root": parent_history_root,
            "parent_history_count": 0,
            "transition_id": lineage["transition_id"],
            "mutation_delta_root": delta,
            "history_count": 1,
        },
    )
    return {
        **lineage,
        "mutation_kind": "initialize",
        "revision": 1,
        "initialized_at_step": current_step,
        "current_step": current_step,
        "mutation_provenance_root": mutation_provenance_root,
        "mutation_trace_roots": mutation_trace_roots,
        "mutation_delta_root": delta,
        "evicted_lease_roots": [],
        "parent_revision": 0,
        "parent_transition_id": "genesis",
        "parent_snapshot_root": (
            "sha256:14ba7b83f873a31cf2a77df89c1a6c060f0b3db69c1991b0d11a4630bd7fde3a"
        ),
        "parent_history_root": parent_history_root,
        "parent_history_count": 0,
        "history_root": history,
        "history_count": 1,
        "parent_head_root": _trace_root("support:genesis-head"),
        "snapshot_root": _trace_root("support:snapshot"),
        "lease_set_root": (
            "sha256:23c99380d8b87c91dc9c69d963d0089a2b17f2a1db0b0cb2bb108f3023c35fb7"
        ),
        "active_lease_count": 0,
        "issued_lease_root": "",
        "revoked_lease_root": "",
        "revocation_root": "",
        "membership_stream_ref": "",
        "membership_transition_id": "",
        "membership_snapshot_root": "",
        "source_context_root": _trace_root("support:source-context"),
        "source_verification_root": _trace_root("support:source-verification"),
        "read_set_root": _trace_root("support:read-set"),
    }


def _support_lease_issued_authority() -> dict[str, object]:
    lineage = _support_authority("mutation:support:issue")
    proposal_root = _trace_root("support:proposal")
    transition = str(lineage["transition_id"])
    lease_ref = (
        "lease:support-v2:"
        + sha256(
            transition.encode("utf-8") + b"\x00" + proposal_root.encode("ascii")
        ).hexdigest()
    )
    membership_stream = _authority_stream("membership-v2", "support:membership")
    membership_transition = "transition:membership-v2:" + "1" * 64
    return {
        **lineage,
        "lease_root": _trace_root("support:lease"),
        "lease_ref": lease_ref,
        "mutation_transition_id": transition,
        "proposal_root": proposal_root,
        "candidate_ref": "candidate:test",
        "claim_root": _trace_root("support:claim"),
        "epoch": 11,
        "principal_ref": "principal:test",
        "principal_cluster_ref": "cluster:test",
        "membership_principal_root": _trace_root("membership:principal"),
        "principal_verification_root": _trace_root("principal:verification"),
        "membership_stream_ref": membership_stream,
        "membership_transition_id": membership_transition,
        "membership_snapshot_root": _trace_root("membership:snapshot"),
        "membership_root": _trace_root("membership"),
        "positive_observation_set_root": _trace_root("support:observations"),
        "prior_lease_root": "",
        "issuance_issuer_ref": lineage["mutation_issuer_ref"],
        "issued_at_step": 4,
        "expires_at_step": 40,
        "proposal_provenance_root": _trace_root("support:proposal-provenance"),
        "proposal_trace_roots": [_trace_root("support:proposal-trace")],
        "issuance_provenance_root": _trace_root("support:issuance-provenance"),
        "issuance_trace_roots": [_trace_root("support:issuance-trace")],
        "read_set_root": _trace_root("support:read-set"),
    }


def _support_lease_revoked_authority() -> dict[str, object]:
    lineage = _support_authority("mutation:support:revoke")
    transition = str(lineage["transition_id"])
    lease_root = _trace_root("support:lease")
    revocation_ref = (
        "revocation:support-v2:"
        + sha256(
            transition.encode("utf-8") + b"\x00" + lease_root.encode("ascii")
        ).hexdigest()
    )
    return {
        **lineage,
        "revocation_root": _trace_root("support:revocation"),
        "revocation_ref": revocation_ref,
        "mutation_transition_id": transition,
        "lease_root": lease_root,
        "candidate_ref": "candidate:test",
        "claim_root": _trace_root("support:claim"),
        "epoch": 11,
        "principal_ref": "principal:test",
        "principal_cluster_ref": "cluster:test",
        "lease_issuance_issuer_ref": "issuer:original",
        "revocation_issuer_ref": lineage["mutation_issuer_ref"],
        "reason_codes": ["support:withdrawn"],
        "revoked_at_step": 8,
        "provenance_root": _trace_root("support:revocation-provenance"),
        "source_trace_roots": [_trace_root("support:revocation-trace")],
        "read_set_root": _trace_root("support:read-set"),
    }
