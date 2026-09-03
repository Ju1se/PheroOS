from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

import pytest

from pheroos.trace import (
    InMemoryScopedTraceStoreV2,
    ScopedTraceAppendReceiptV2,
    ScopedTraceCheckpointV2,
    ScopedTraceCursorV2,
    ScopedTraceEvent,
    ScopedTraceRecordV2,
    ScopedTraceRetirementV2,
    ScopedTraceStoreV2,
    TraceEvent,
)
from pheroos.trace import _coordination_lineage_rules as coordination_rules
from pheroos.trace import _lineage_primitives as lineage_primitives
from pheroos.trace import _scoped_store_v2_codec as store_codec
from pheroos.trace import commit_contracts
from pheroos.trace._lineage_types import (
    DECLARED_COORDINATION_LAYER_IDS,
    LAYER_SNAPSHOT_FIELDS,
)
from tests.trace.test_trace_store import valid_lineage


SCOPE_A = "sha256:" + "a" * 64
SCOPE_B = "sha256:" + "b" * 64
ROOT_C = "sha256:" + "c" * 64


def _assert_error(
    expected: str,
    action: Callable[[], object],
    *,
    error_type: type[Exception] = ValueError,
) -> None:
    with pytest.raises(error_type) as caught:
        action()
    assert str(caught.value) == expected


def _view(
    event_type: str,
    lineage: dict[str, object],
    *,
    target: str = "decision:e2e",
) -> SimpleNamespace:
    return SimpleNamespace(event_type=event_type, lineage=lineage, target=target)


def _scoped_event(
    ordinal: int = 1,
    *,
    scope_ref: str = SCOPE_A,
    stream: str = "governance:commit",
    trace_id: str | None = None,
    transition_id: str | None = None,
) -> ScopedTraceEvent:
    return ScopedTraceEvent(
        scope_ref=scope_ref,
        stream=stream,
        trace_id=trace_id or f"trace:{ordinal}",
        transition_id=transition_id or f"transition:{ordinal}",
        event=TraceEvent(
            event_type="ext.pheroos.trace_totality",
            protocol_id="protocol:trace-totality",
            target="decision:trace-totality",
            reason="exercise the scoped append-only trace ABI",
            lineage={"ordinal": ordinal},
        ),
    )


def _record(
    sequence: int,
    *,
    ordinal: int = 1,
    trace_id: str | None = None,
    transition_id: str | None = None,
) -> ScopedTraceRecordV2:
    return ScopedTraceRecordV2(
        SCOPE_A,
        "governance:commit",
        sequence,
        _scoped_event(
            ordinal,
            trace_id=trace_id,
            transition_id=transition_id,
        ),
    )


def _layer_snapshots() -> dict[str, dict[str, object]]:
    return {
        layer_id: {
            field: False if field == "present" else 0.0
            for field in LAYER_SNAPSHOT_FIELDS
        }
        for layer_id in DECLARED_COORDINATION_LAYER_IDS
    }


def test_lineage_scalar_and_container_guards_report_exact_paths() -> None:
    lp = lineage_primitives
    cases: tuple[tuple[str, Callable[[], object]], ...] = (
        (
            "evt trace lineage name must be a non-empty string",
            lambda: lp.require_text_fields("evt", {"name": ""}, ("name",)),
        ),
        (
            "evt trace lineage amount must be non-negative",
            lambda: lp.require_nonnegative_number("evt", {"amount": -1}, "amount"),
        ),
        (
            "evt trace lineage count must be a non-negative integer",
            lambda: lp.require_nonnegative_integer("evt", {"count": True}, "count"),
        ),
        (
            "evt trace lineage count must be a positive integer",
            lambda: lp.require_positive_integer("evt", {"count": 0}, "count"),
        ),
        (
            "evt trace lineage enabled must be a boolean",
            lambda: lp.require_boolean("evt", {"enabled": 1}, "enabled"),
        ),
        (
            "evt trace lineage values must be a non-empty object",
            lambda: lp.require_nonempty_mapping("evt", {"values": {}}, "values"),
        ),
        (
            "evt trace lineage budget_result must contain round_remaining, "
            "source_remaining, and status",
            lambda: lp.validate_budget_result("evt", {}),
        ),
        (
            "evt trace lineage budget_result status is unsupported",
            lambda: lp.validate_budget_result(
                "evt",
                {
                    "round_remaining": 0,
                    "source_remaining": 0,
                    "status": "unknown",
                },
            ),
        ),
        (
            "evt trace lineage scores must be a non-empty score object",
            lambda: lp.require_score_mapping("evt", {"scores": {}}, "scores"),
        ),
        (
            "evt trace lineage scores keys must be non-empty strings",
            lambda: lp.require_score_mapping("evt", {"scores": {"": 0}}, "scores"),
        ),
        (
            "evt trace lineage names must be an object",
            lambda: lp.require_text_mapping("evt", {"names": []}, "names"),
        ),
        (
            "evt trace lineage names must contain non-empty string entries",
            lambda: lp.require_text_mapping("evt", {"names": {"": "value"}}, "names"),
        ),
        (
            "evt trace lineage weights must be an object",
            lambda: lp.require_bounded_mapping(
                "evt",
                {"weights": []},
                "weights",
                minimum=0,
                maximum=1,
            ),
        ),
        (
            "evt trace lineage weights keys must be non-empty strings",
            lambda: lp.require_bounded_mapping(
                "evt",
                {"weights": {"": 0}},
                "weights",
                minimum=0,
                maximum=1,
            ),
        ),
        (
            "evt trace lineage weights.a must be between 0 and 1",
            lambda: lp.require_bounded_mapping(
                "evt",
                {"weights": {"a": 2}},
                "weights",
                minimum=0,
                maximum=1,
            ),
        ),
        (
            "evt trace lineage coverage must be a non-empty coverage object",
            lambda: lp.require_recursive_coverage("evt", {"coverage": {}}, "coverage"),
        ),
        (
            "evt trace lineage coverage keys must be non-empty strings",
            lambda: lp.require_recursive_coverage(
                "evt",
                {"coverage": {"": 0}},
                "coverage",
            ),
        ),
        (
            "evt trace lineage counts must be an object",
            lambda: lp.require_count_mapping("evt", {"counts": []}, "counts"),
        ),
        (
            "evt trace lineage counts must contain non-negative integer counts",
            lambda: lp.require_count_mapping(
                "evt",
                {"counts": {"candidate:a": True}},
                "counts",
            ),
        ),
        (
            "evt trace lineage items must be a non-empty array",
            lambda: lp.require_text_sequence(
                "evt",
                {"items": 1},
                "items",
                allow_empty=False,
            ),
        ),
        (
            "evt trace lineage items must contain non-empty strings",
            lambda: lp.require_text_sequence(
                "evt",
                {"items": [""]},
                "items",
                allow_empty=False,
            ),
        ),
        (
            "evt trace lineage subject must contain type and id",
            lambda: lp.require_subject("evt", {"subject": {}}, "subject"),
        ),
    )
    for expected, action in cases:
        _assert_error(expected, action)

    lp.require_finite_fields("evt", {"amount": 1}, ("amount",))


def test_lineage_layer_snapshot_guards_reject_invalid_presence_and_metrics() -> None:
    snapshots = _layer_snapshots()
    snapshots["learned"]["present"] = 1
    _assert_error(
        "evt trace lineage snapshots.learned.present must be a boolean",
        lambda: lineage_primitives.require_layer_snapshots(
            "evt",
            {"snapshots": snapshots},
            "snapshots",
        ),
    )

    snapshots = _layer_snapshots()
    snapshots["learned"]["present"] = True
    snapshots["learned"]["trace_coverage"] = 1.1
    _assert_error(
        "evt trace lineage snapshots.learned.trace_coverage must be between 0 and 1",
        lambda: lineage_primitives.require_layer_snapshots(
            "evt",
            {"snapshots": snapshots},
            "snapshots",
        ),
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda lineage: lineage.update(confidence=1.1),
            "layer_proposal trace lineage confidence must be between 0 and 1",
        ),
        (
            lambda lineage: lineage.update(proposed_strength=11),
            "layer_proposal trace lineage proposed_strength must be between 0 and 10",
        ),
        (
            lambda lineage: lineage.update(proposed_pheromone_kind=1),
            "layer_proposal trace lineage proposed_pheromone_kind must be a string",
        ),
        (
            lambda lineage: lineage.update(support=11),
            "layer_proposal trace lineage support must be between 0 and 10",
        ),
        (
            lambda lineage: lineage.update(
                action="propose_pheromone",
                effect="wrong",
                proposed_pheromone_kind="positive",
                proposed_strength=1,
            ),
            "layer pheromone proposal trace must declare its bounded deposit effect",
        ),
        (
            lambda lineage: lineage.update(
                action="propose_pheromone",
                effect="bounded_pheromone_deposit_proposed",
                proposed_pheromone_kind="",
                proposed_strength=1,
            ),
            "layer pheromone proposal trace requires kind and positive strength",
        ),
    ],
)
def test_layer_proposal_changed_guards_fail_closed(
    mutation: Callable[[dict[str, object]], None],
    expected: str,
) -> None:
    lineage = valid_lineage("layer_proposal")
    mutation(lineage)
    _assert_error(
        expected,
        lambda: coordination_rules.apply_coordination_lineage_rule(
            _view("layer_proposal", lineage),
            frozenset(),
        ),
    )


def test_coordination_rule_dispatch_and_policy_adjustment_edges() -> None:
    assert (
        coordination_rules.apply_coordination_lineage_rule(
            _view("ext.unknown", {}),
            frozenset(),
        )
        is False
    )
    cases: tuple[
        tuple[dict[str, object], str],
        ...,
    ] = (
        (
            {**valid_lineage("policy_adjustment"), "result": "unknown"},
            "policy_adjustment trace lineage result must be accepted, rejected, "
            "or replay_ignored",
        ),
        (
            {
                **valid_lineage("policy_adjustment"),
                "result": "replay_ignored",
                "replayed": False,
            },
            "replayed policy_adjustment trace must set replayed=true",
        ),
        (
            {
                **valid_lineage("policy_adjustment"),
                "proposed_values": {"": 0.2},
                "declared_bounds": {"": [0, 1]},
            },
            "policy_adjustment trace lineage proposed_values keys must be "
            "non-empty strings",
        ),
        (
            {
                **valid_lineage("policy_adjustment"),
                "proposed_values": {"mode": "safe"},
                "declared_bounds": {"mode": {"allowed_values": []}},
            },
            "policy_adjustment trace lineage "
            "declared_bounds.mode.allowed_values must be a non-empty array",
        ),
        (
            {
                **valid_lineage("policy_adjustment"),
                "proposed_values": {"rate": True},
                "declared_bounds": {"rate": [0, 1]},
            },
            "policy_adjustment trace lineage proposed_values.rate must be a "
            "finite number or string",
        ),
        (
            {
                **valid_lineage("policy_adjustment"),
                "proposed_values": {"rate": None},
                "declared_bounds": {"rate": [0, 1]},
            },
            "policy_adjustment trace lineage proposed_values.rate must be a "
            "finite number or string",
        ),
        (
            {
                **valid_lineage("policy_adjustment"),
                "proposed_values": {"rate": "not-numeric"},
                "declared_bounds": {"rate": [0, 1]},
            },
            "policy_adjustment trace accepted or replayed value is outside "
            "declared bounds: rate",
        ),
    )
    for lineage, expected in cases:
        _assert_error(
            expected,
            lambda lineage=lineage: (
                coordination_rules.apply_coordination_lineage_rule(
                    _view("policy_adjustment", lineage),
                    frozenset(),
                )
            ),
        )


def test_scoped_codec_guards_cover_portability_and_type_boundaries() -> None:
    _assert_error(
        "root must be canonical text",
        lambda: store_codec._computed_root(1, ROOT_C, "root"),
    )
    store_codec._portable(1.0)
    _assert_error(
        "payload contains a non-portable value",
        lambda: store_codec._portable(object()),
    )
    _assert_error(
        "payload contains a non-text key",
        lambda: store_codec._portable({1: "value"}),
    )
    _assert_error(
        "scoped trace append requires ScopedTraceEvent v1",
        lambda: store_codec._canonical_event(object()),
        error_type=TypeError,
    )


def test_scoped_store_protocol_declaration_bodies_are_inert() -> None:
    receiver = object()
    assert ScopedTraceStoreV2.append_scoped_v2(receiver, object()) is None
    assert ScopedTraceStoreV2.snapshot_scoped_v2(receiver, SCOPE_A, "stream") is None
    assert ScopedTraceStoreV2.cursor_scoped_v2(receiver, SCOPE_A, "stream") is None
    assert ScopedTraceStoreV2.retire_scope_v2(receiver, SCOPE_A) is None
    assert ScopedTraceStoreV2.checkpoint_v2(receiver) is None
    assert ScopedTraceStoreV2.restart_v2(receiver, object()) is None


def test_scoped_event_and_value_constructors_reject_every_changed_shape_guard() -> None:
    _assert_error(
        "scoped trace event stream must be canonical nonblank text",
        lambda: _scoped_event(stream=" "),
    )
    envelope = _scoped_event()
    record = _record(0)
    cases: tuple[tuple[str, Callable[[], object], type[Exception]], ...] = (
        (
            "scoped trace record version is unsupported",
            lambda: ScopedTraceRecordV2(
                SCOPE_A,
                "governance:commit",
                0,
                envelope,
                version="wrong",
            ),
            ValueError,
        ),
        (
            "scoped trace record binding does not match its envelope",
            lambda: ScopedTraceRecordV2(
                SCOPE_B,
                "governance:commit",
                0,
                envelope,
            ),
            ValueError,
        ),
        (
            "scoped trace receipt version is unsupported",
            lambda: ScopedTraceAppendReceiptV2(
                "appended",
                record,
                version="wrong",
            ),
            ValueError,
        ),
        (
            "scoped trace receipt disposition is unsupported",
            lambda: ScopedTraceAppendReceiptV2("unknown", record),
            ValueError,
        ),
        (
            "scoped trace receipt requires a v2 record",
            lambda: ScopedTraceAppendReceiptV2("appended", object()),
            TypeError,
        ),
        (
            "scoped trace cursor version is unsupported",
            lambda: ScopedTraceCursorV2(
                SCOPE_A,
                "governance:commit",
                0,
                ROOT_C,
                version="wrong",
            ),
            ValueError,
        ),
        (
            "scoped trace retirement version is unsupported",
            lambda: ScopedTraceRetirementV2(
                SCOPE_A,
                ROOT_C,
                version="wrong",
            ),
            ValueError,
        ),
        (
            "scoped trace checkpoint version is unsupported",
            lambda: ScopedTraceCheckpointV2((), (), version="wrong"),
            ValueError,
        ),
        (
            "scoped trace checkpoint collections must be tuples",
            lambda: ScopedTraceCheckpointV2([], ()),
            ValueError,
        ),
        (
            "scoped trace failure stage is unsupported",
            lambda: InMemoryScopedTraceStoreV2(failure_stage="wrong"),
            ValueError,
        ),
    )
    for expected, action, error_type in cases:
        _assert_error(expected, action, error_type=error_type)


def test_scoped_value_decoders_reject_nested_non_object_shapes() -> None:
    record_raw = _record(0).to_dict()
    record_raw["event"] = []
    _assert_error(
        "scoped trace record event must be an object",
        lambda: ScopedTraceRecordV2.from_dict(record_raw),
    )

    receipt_raw = ScopedTraceAppendReceiptV2("appended", _record(0)).to_dict()
    receipt_raw["record"] = []
    _assert_error(
        "scoped trace receipt record must be an object",
        lambda: ScopedTraceAppendReceiptV2.from_dict(receipt_raw),
    )

    checkpoint_raw = ScopedTraceCheckpointV2((), ()).to_dict()
    checkpoint_raw["records"] = {}
    _assert_error(
        "scoped trace checkpoint collections must be arrays",
        lambda: ScopedTraceCheckpointV2.from_dict(checkpoint_raw),
    )

    checkpoint_raw = ScopedTraceCheckpointV2((), ()).to_dict()
    checkpoint_raw["records"] = ["not-an-object"]
    _assert_error(
        "scoped trace checkpoint entries must be objects",
        lambda: ScopedTraceCheckpointV2.from_dict(checkpoint_raw),
    )


def test_scoped_store_cursor_binding_rejects_cross_scope_replay() -> None:
    store = InMemoryScopedTraceStoreV2()
    store.append_scoped_v2(_scoped_event())
    cursor = store.cursor_scoped_v2(SCOPE_A, "governance:commit")
    _assert_error(
        "scoped trace cursor binding mismatch",
        lambda: store.snapshot_scoped_v2(
            SCOPE_B,
            "governance:commit",
            cursor,
        ),
    )


def test_scoped_store_restore_rejects_noncontiguous_and_duplicate_identity() -> None:
    noncontiguous = ScopedTraceCheckpointV2((_record(1),), ())
    _assert_error(
        "scoped trace checkpoint sequence is not contiguous",
        lambda: InMemoryScopedTraceStoreV2(noncontiguous),
    )

    first = _record(
        0,
        ordinal=1,
        trace_id="trace:shared",
        transition_id="transition:shared",
    )
    second = _record(
        1,
        ordinal=2,
        trace_id="trace:shared",
        transition_id="transition:shared",
    )
    duplicate = ScopedTraceCheckpointV2((first, second), ())
    _assert_error(
        "scoped trace checkpoint contains duplicate identity",
        lambda: InMemoryScopedTraceStoreV2(duplicate),
    )


def test_scoped_store_restore_rejects_duplicate_or_mismatched_retirement() -> None:
    history_root = InMemoryScopedTraceStoreV2()._scope_history_root(SCOPE_A)
    retirement = ScopedTraceRetirementV2(SCOPE_A, history_root)
    duplicate = ScopedTraceCheckpointV2((), (retirement, retirement))
    _assert_error(
        "scoped trace checkpoint contains duplicate retirement",
        lambda: InMemoryScopedTraceStoreV2(duplicate),
    )

    mismatched = ScopedTraceCheckpointV2(
        (),
        (ScopedTraceRetirementV2(SCOPE_A, ROOT_C),),
    )
    _assert_error(
        "scoped trace retirement history root mismatch",
        lambda: InMemoryScopedTraceStoreV2(mismatched),
    )


def test_commit_trace_provisional_and_finality_paths_fail_closed_and_complete() -> None:
    _assert_error(
        "witness-bearing provisional trace requires the exact proposal digest "
        "and commit value root",
        lambda: commit_contracts._validate_provisional_value_shape({}, 1),
    )
    commit_contracts._validate_terminal_path(
        "finality_unavailable",
        {"commit_provisional": [object()]},
        [object()],
    )
