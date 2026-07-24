from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import pickle

import pytest

from pheroos.trace import (
    SCOPED_TRACE_STORE_VERSION_V2,
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


SCOPE_A = "sha256:" + "a" * 64
SCOPE_B = "sha256:" + "b" * 64


def event(
    ordinal: int = 1,
    *,
    scope_ref: str = SCOPE_A,
    stream: str = "governance:commit",
    transition_id: str | None = None,
    trace_id: str | None = None,
) -> ScopedTraceEvent:
    transition_id = transition_id or f"transition:{ordinal}"
    trace_id = trace_id or f"trace:{ordinal}"
    return ScopedTraceEvent(
        scope_ref=scope_ref,
        stream=stream,
        transition_id=transition_id,
        trace_id=trace_id,
        event=TraceEvent(
            event_type="ext.pheroos.scoped_store_v2",
            protocol_id="protocol:scoped-store-v2",
            target="decision:scoped-store-v2",
            reason="portable scoped history",
            lineage={"ordinal": ordinal, "nested": {"items": [ordinal]}},
        ),
    )


def test_scoped_store_v2_is_additive_and_v1_schema_bytes_are_frozen() -> None:
    assert isinstance(InMemoryScopedTraceStoreV2(), ScopedTraceStoreV2)
    assert InMemoryScopedTraceStoreV2.store_version == SCOPED_TRACE_STORE_VERSION_V2
    schema = Path("schemas/scoped-trace-event-v1.schema.json").read_bytes()
    assert sha256(schema).hexdigest() == (
        "b05925809d83645734d205e814f2ced0ff8afe242a8526b2ed3aadb93dfccd01"
    )


def test_v2_values_have_closed_portable_round_trips_and_defensive_views() -> None:
    store = InMemoryScopedTraceStoreV2()
    receipt = store.append_scoped_v2(event())
    cursor = store.cursor_scoped_v2(SCOPE_A, "governance:commit")
    retirement = store.retire_scope_v2(SCOPE_A)
    checkpoint = store.checkpoint_v2()
    values = (
        (receipt.record, ScopedTraceRecordV2),
        (receipt, ScopedTraceAppendReceiptV2),
        (cursor, ScopedTraceCursorV2),
        (retirement, ScopedTraceRetirementV2),
        (checkpoint, ScopedTraceCheckpointV2),
    )
    for value, kind in values:
        portable = json.loads(json.dumps(value.to_dict(), allow_nan=False))
        restored = kind.from_dict(portable)
        assert restored == value
        portable["unknown"] = True
        with pytest.raises(ValueError, match="fields"):
            kind.from_dict(portable)

    checkpoint.records[0].event.event.lineage["nested"]["items"].append(999)
    assert store.checkpoint_v2().records[0].event.event.lineage["nested"]["items"] == [
        1
    ]


def test_checkpoint_has_one_canonical_record_and_retirement_order() -> None:
    store = InMemoryScopedTraceStoreV2()
    store.append_scoped_v2(event(1, scope_ref=SCOPE_B, stream="z"))
    store.append_scoped_v2(event(2, scope_ref=SCOPE_A, stream="z"))
    store.append_scoped_v2(event(3, scope_ref=SCOPE_A, stream="a"))
    store.retire_scope_v2(SCOPE_B)
    store.retire_scope_v2(SCOPE_A)
    checkpoint = store.checkpoint_v2()

    equivalent = InMemoryScopedTraceStoreV2()
    equivalent.append_scoped_v2(event(3, scope_ref=SCOPE_A, stream="a"))
    equivalent.append_scoped_v2(event(2, scope_ref=SCOPE_A, stream="z"))
    equivalent.append_scoped_v2(event(1, scope_ref=SCOPE_B, stream="z"))
    equivalent.retire_scope_v2(SCOPE_A)
    equivalent.retire_scope_v2(SCOPE_B)
    assert equivalent.checkpoint_v2() == checkpoint

    keys = tuple(
        (item.scope_ref, item.stream, item.sequence) for item in checkpoint.records
    )
    assert keys == tuple(sorted(keys))
    assert tuple(item.scope_ref for item in checkpoint.retirements) == (
        SCOPE_A,
        SCOPE_B,
    )

    reversed_records = checkpoint.to_dict()
    reversed_records["records"].reverse()
    reversed_records["checkpoint_root"] = ""
    with pytest.raises(ValueError, match="records are not canonical order"):
        ScopedTraceCheckpointV2.from_dict(reversed_records)

    reversed_retirements = checkpoint.to_dict()
    reversed_retirements["retirements"].reverse()
    reversed_retirements["checkpoint_root"] = ""
    with pytest.raises(ValueError, match="retirements are not canonical order"):
        ScopedTraceCheckpointV2.from_dict(reversed_retirements)

    forged = deepcopy(checkpoint)
    object.__setattr__(forged, "records", tuple(reversed(forged.records)))
    with pytest.raises(ValueError, match="records are not canonical order"):
        store.restart_v2(forged)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda raw: raw.pop("stream"),
        lambda raw: raw.update({"sequence": True}),
        lambda raw: raw.update({"scope_ref": "sha256:" + "A" * 64}),
        lambda raw: raw["event"]["event"]["lineage"].update({"bad": float("nan")}),
    ],
)
def test_record_rejects_missing_coerced_noncanonical_and_nonfinite_wire(
    mutation,
) -> None:
    raw = ScopedTraceRecordV2(SCOPE_A, "governance:commit", 0, event()).to_dict()
    mutation(raw)
    with pytest.raises((TypeError, ValueError)):
        ScopedTraceRecordV2.from_dict(raw)


def test_append_revalidates_scope_and_envelope_roots_before_writing() -> None:
    store = InMemoryScopedTraceStoreV2()
    mutated_scope = event()
    object.__setattr__(mutated_scope, "scope_ref", SCOPE_B)
    with pytest.raises(ValueError, match="envelope root"):
        store.append_scoped_v2(mutated_scope)

    mutated_body = event()
    mutated_body.event.lineage["ordinal"] = 999
    with pytest.raises(ValueError, match="root"):
        store.append_scoped_v2(mutated_body)
    assert store.snapshot_scoped_v2(SCOPE_A, "governance:commit") == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("stream", "commit\x00hidden"),
        ("stream", "cafe\u0301"),
        ("trace_id", "trace\x00hidden"),
        ("trace_id", "trace:cafe\u0301"),
        ("transition_id", "transition\x00hidden"),
        ("transition_id", "transition:cafe\u0301"),
    ],
)
def test_store_rejects_nul_and_non_nfc_stream_or_identity(
    field: str,
    value: str,
) -> None:
    kwargs = {field: value}
    malformed = event(**kwargs)
    store = InMemoryScopedTraceStoreV2()
    with pytest.raises(ValueError, match="canonical nonblank text"):
        store.append_scoped_v2(malformed)
    assert store.checkpoint_v2().records == ()


@pytest.mark.parametrize(
    "malformed",
    [
        lambda: event(stream="invalid-\ud800"),
        lambda: event(trace_id="invalid-\ud800"),
        lambda: event(transition_id="invalid-\ud800"),
        lambda: event(),
    ],
)
def test_store_rejects_unicode_surrogates_in_identity_and_nested_event(
    malformed,
) -> None:
    envelope = malformed()
    if envelope.stream == "governance:commit" and envelope.trace_id == "trace:1":
        envelope.event.lineage["nested"] = {"value": "invalid-\ud800"}
    store = InMemoryScopedTraceStoreV2()

    with pytest.raises(ValueError, match="canonical"):
        store.append_scoped_v2(envelope)
    assert store.checkpoint_v2().records == ()


@pytest.mark.parametrize(
    "field",
    ["event_type", "protocol_id", "target", "reason"],
)
def test_store_rejects_surrogates_in_trace_event_body(field: str) -> None:
    envelope = event()
    object.__setattr__(envelope.event, field, "invalid-\ud800")

    with pytest.raises(ValueError, match="canonical"):
        InMemoryScopedTraceStoreV2().append_scoped_v2(envelope)


def test_store_rejects_surrogate_lineage_keys_and_checkpoint_replay() -> None:
    keyed = event()
    keyed.event.lineage["invalid-\ud800"] = "value"
    with pytest.raises(ValueError, match="canonical"):
        InMemoryScopedTraceStoreV2().append_scoped_v2(keyed)

    store = InMemoryScopedTraceStoreV2()
    store.append_scoped_v2(event())
    checkpoint = store.checkpoint_v2().to_dict()
    checkpoint["records"][0]["event"]["event"]["reason"] = "invalid-\ud800"
    with pytest.raises(ValueError, match="canonical"):
        ScopedTraceCheckpointV2.from_dict(checkpoint)


def test_append_snapshots_input_and_output_and_exact_replay_is_idempotent() -> None:
    store = InMemoryScopedTraceStoreV2()
    envelope = event()
    first = store.append_scoped_v2(envelope)
    second = store.append_scoped_v2(event())
    assert first.disposition == "appended"
    assert second.disposition == "replayed"
    assert first.record == second.record

    envelope.event.lineage["nested"]["items"].append(2)
    first.record.event.event.lineage["nested"]["items"].append(3)
    observed = store.snapshot_scoped_v2(SCOPE_A, "governance:commit")
    assert observed[0].event.event.lineage["nested"]["items"] == [1]
    observed[0].event.event.lineage["nested"]["items"].append(4)
    assert store.snapshot_scoped_v2(SCOPE_A, "governance:commit")[
        0
    ].event.event.lineage["nested"]["items"] == [1]


@pytest.mark.parametrize(
    "conflict",
    [
        event(2, trace_id="trace:1"),
        event(2, transition_id="transition:1"),
    ],
)
def test_trace_or_transition_identity_conflict_is_rejected(
    conflict: ScopedTraceEvent,
) -> None:
    store = InMemoryScopedTraceStoreV2()
    store.append_scoped_v2(event())
    with pytest.raises(ValueError, match="identity replay"):
        store.append_scoped_v2(conflict)
    assert len(store.snapshot_scoped_v2(SCOPE_A, "governance:commit")) == 1


def test_scope_and_stream_histories_are_isolated_and_contiguous() -> None:
    store = InMemoryScopedTraceStoreV2()
    receipts = (
        store.append_scoped_v2(event(1, scope_ref=SCOPE_A, stream="a")),
        store.append_scoped_v2(event(2, scope_ref=SCOPE_B, stream="a")),
        store.append_scoped_v2(event(3, scope_ref=SCOPE_A, stream="b")),
        store.append_scoped_v2(event(4, scope_ref=SCOPE_A, stream="a")),
    )
    assert [item.record.sequence for item in receipts] == [0, 0, 0, 1]
    assert [item.event.trace_id for item in store.snapshot_scoped_v2(SCOPE_A, "a")] == [
        "trace:1",
        "trace:4",
    ]
    assert [item.event.trace_id for item in store.snapshot_scoped_v2(SCOPE_B, "a")] == [
        "trace:2"
    ]


def test_cursor_and_restart_preserve_exact_history_and_reject_forgery() -> None:
    store = InMemoryScopedTraceStoreV2()
    store.append_scoped_v2(event(1))
    cursor = store.cursor_scoped_v2(SCOPE_A, "governance:commit")
    store.append_scoped_v2(event(2))
    assert [
        item.sequence
        for item in store.snapshot_scoped_v2(SCOPE_A, "governance:commit", cursor)
    ] == [1]

    restarted = store.restart_v2(store.checkpoint_v2())
    assert restarted.snapshot_scoped_v2(
        SCOPE_A, "governance:commit"
    ) == store.snapshot_scoped_v2(SCOPE_A, "governance:commit")
    assert restarted.cursor_scoped_v2(
        SCOPE_A, "governance:commit"
    ) == store.cursor_scoped_v2(SCOPE_A, "governance:commit")
    replay = restarted.append_scoped_v2(event(1))
    assert replay.disposition == "replayed"
    assert len(restarted.snapshot_scoped_v2(SCOPE_A, "governance:commit")) == 2
    forged = replace(cursor, prefix_root="sha256:" + "0" * 64, cursor_root="")
    with pytest.raises(ValueError, match="stale or forged"):
        restarted.snapshot_scoped_v2(SCOPE_A, "governance:commit", forged)


def test_retirement_is_idempotent_readable_and_permanently_blocks_append_or_replay() -> (
    None
):
    store = InMemoryScopedTraceStoreV2()
    store.append_scoped_v2(event())
    retirement = store.retire_scope_v2(SCOPE_A)
    assert store.retire_scope_v2(SCOPE_A) == retirement
    assert len(store.snapshot_scoped_v2(SCOPE_A, "governance:commit")) == 1
    for blocked in (event(), event(2)):
        with pytest.raises(ValueError, match="retired"):
            store.append_scoped_v2(blocked)
    restarted = store.restart_v2(store.checkpoint_v2())
    with pytest.raises(ValueError, match="retired"):
        restarted.append_scoped_v2(event())


def test_32_workers_replaying_one_envelope_publish_one_canonical_record() -> None:
    store = InMemoryScopedTraceStoreV2()
    with ThreadPoolExecutor(max_workers=32) as pool:
        receipts = tuple(pool.map(lambda _: store.append_scoped_v2(event()), range(32)))
    assert sum(item.disposition == "appended" for item in receipts) == 1
    assert len({item.record.record_root for item in receipts}) == 1
    assert len(store.snapshot_scoped_v2(SCOPE_A, "governance:commit")) == 1


def test_concurrent_distinct_events_have_no_loss_duplicate_or_sequence_gap() -> None:
    store = InMemoryScopedTraceStoreV2()
    with ThreadPoolExecutor(max_workers=32) as pool:
        tuple(
            pool.map(
                lambda ordinal: store.append_scoped_v2(event(ordinal)), range(1, 65)
            )
        )
    records = store.snapshot_scoped_v2(SCOPE_A, "governance:commit")
    assert tuple(item.sequence for item in records) == tuple(range(64))
    assert {item.event.trace_id for item in records} == {
        f"trace:{item}" for item in range(1, 65)
    }


@pytest.mark.parametrize(
    "stage",
    ["append_before_publish", "retire_before_publish", "checkpoint_before_return"],
)
def test_failure_injection_never_publishes_half_record_or_tombstone(stage: str) -> None:
    base = InMemoryScopedTraceStoreV2()
    checkpoint = base.checkpoint_v2()
    store = InMemoryScopedTraceStoreV2(checkpoint, failure_stage=stage)
    before = (
        store.restart_v2(store.checkpoint_v2())
        if stage != "checkpoint_before_return"
        else base
    )
    with pytest.raises(RuntimeError, match="injected"):
        if stage == "append_before_publish":
            store.append_scoped_v2(event())
        elif stage == "retire_before_publish":
            store.retire_scope_v2(SCOPE_A)
        else:
            store.checkpoint_v2()
    if stage != "checkpoint_before_return":
        assert store.snapshot_scoped_v2(
            SCOPE_A, "governance:commit"
        ) == before.snapshot_scoped_v2(SCOPE_A, "governance:commit")


def test_pickle_and_raw_round_trip_restore_data_without_special_authority() -> None:
    store = InMemoryScopedTraceStoreV2()
    receipt = store.append_scoped_v2(event())
    restored = pickle.loads(pickle.dumps(receipt))
    raw = ScopedTraceAppendReceiptV2.from_dict(
        json.loads(json.dumps(receipt.to_dict()))
    )
    assert restored == raw == receipt
    assert not hasattr(restored, "append_scoped_v2")
    assert not hasattr(raw, "retire_scope_v2")
