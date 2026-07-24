"""Public implementation TCK for the Scoped TraceStore v2 ABI."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Protocol, runtime_checkable

from pheroos.conformance.report import CheckResult
from pheroos.trace import (
    SCOPED_TRACE_STORE_VERSION_V2,
    InMemoryScopedTraceStoreV2,
    ScopedTraceAppendReceiptV2,
    ScopedTraceCheckpointV2,
    ScopedTraceEvent,
    ScopedTraceStoreV2,
    TraceEvent,
)


SCOPED_TRACE_STORE_CONFORMANCE_VERSION_V2 = "pheroos-scoped-trace-store-conformance-v2"
SCOPED_TRACE_STORE_FAILURE_STAGES_V2 = (
    "append_before_publish",
    "retire_before_publish",
    "checkpoint_before_return",
)
_CHECK = "scoped_trace_store_v2_contract"
_SCOPE_A = "sha256:" + "a" * 64
_SCOPE_B = "sha256:" + "b" * 64


@runtime_checkable
class ScopedTraceStoreConformanceAdapterV2(Protocol):
    """Creation-only TCK adapter; no request contains an expected answer."""

    implementation_id: str
    conformance_version: str

    def create_store_v2(self) -> ScopedTraceStoreV2: ...

    def restart_store_v2(
        self,
        store: ScopedTraceStoreV2,
        checkpoint: ScopedTraceCheckpointV2,
    ) -> ScopedTraceStoreV2: ...

    def create_failure_injected_store_v2(
        self,
        stage: str,
    ) -> ScopedTraceStoreV2: ...


class ReferenceScopedTraceStoreConformanceAdapterV2:
    __slots__ = ()

    implementation_id = "pheroos-in-memory-scoped-trace-store-v2"
    conformance_version = SCOPED_TRACE_STORE_CONFORMANCE_VERSION_V2

    def create_store_v2(self) -> ScopedTraceStoreV2:
        return InMemoryScopedTraceStoreV2()

    def restart_store_v2(
        self,
        store: ScopedTraceStoreV2,
        checkpoint: ScopedTraceCheckpointV2,
    ) -> ScopedTraceStoreV2:
        return store.restart_v2(checkpoint)

    def create_failure_injected_store_v2(
        self,
        stage: str,
    ) -> ScopedTraceStoreV2:
        return InMemoryScopedTraceStoreV2(failure_stage=stage)


def _event(
    ordinal: int,
    *,
    scope_ref: str = _SCOPE_A,
    stream: str = "commit",
    trace_id: str | None = None,
    transition_id: str | None = None,
) -> ScopedTraceEvent:
    return ScopedTraceEvent(
        scope_ref=scope_ref,
        stream=stream,
        trace_id=trace_id or f"trace:{ordinal}",
        transition_id=transition_id or f"transition:{ordinal}",
        event=TraceEvent(
            event_type="ext.pheroos.scoped_trace_store_tck_v2",
            protocol_id="protocol:scoped-trace-store-tck-v2",
            target="decision:scoped-trace-store-tck-v2",
            reason="verify portable scoped trace storage",
            lineage={"ordinal": ordinal, "nested": {"items": [ordinal]}},
        ),
    )


def run_scoped_trace_store_conformance_v2(
    adapter: ScopedTraceStoreConformanceAdapterV2,
) -> CheckResult:
    if not isinstance(adapter, ScopedTraceStoreConformanceAdapterV2):
        return CheckResult(_CHECK, False, "adapter_protocol")
    if (
        type(adapter.implementation_id) is not str
        or not adapter.implementation_id
        or adapter.implementation_id != adapter.implementation_id.strip()
    ):
        return CheckResult(_CHECK, False, "adapter_implementation_id")
    if adapter.conformance_version != SCOPED_TRACE_STORE_CONFORMANCE_VERSION_V2:
        return CheckResult(_CHECK, False, "adapter_version")
    problems: list[str] = []
    try:
        store = adapter.create_store_v2()
        if not isinstance(store, ScopedTraceStoreV2):
            return CheckResult(_CHECK, False, "store_protocol")
        if store.store_version != SCOPED_TRACE_STORE_VERSION_V2:
            return CheckResult(_CHECK, False, "store_version")
        _exercise_core(store, adapter, problems)
        _exercise_checkpoint_order(adapter, problems)
        _exercise_races(adapter, problems)
        _exercise_failures(adapter, problems)
        fresh = adapter.create_store_v2()
        if not isinstance(fresh, ScopedTraceStoreV2):
            problems.append("fresh_store_protocol")
        elif fresh.snapshot_scoped_v2(_SCOPE_A, "commit"):
            problems.append("fresh_store_isolation")
    except Exception as exc:
        problems.append(f"adapter_exception:{type(exc).__name__}:{exc}")
    return CheckResult(_CHECK, not problems, ", ".join(problems))


def check() -> CheckResult:
    return run_scoped_trace_store_conformance_v2(
        ReferenceScopedTraceStoreConformanceAdapterV2()
    )


def _exercise_core(
    store: ScopedTraceStoreV2,
    adapter: ScopedTraceStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    _exercise_append_and_snapshots(store, problems)
    _exercise_rejections(store, problems)
    _exercise_scope_and_cursor(store, problems)
    restarted = _exercise_restart(store, adapter, problems)
    if restarted is not None:
        _exercise_retirement(restarted, adapter, problems)


def _exercise_append_and_snapshots(
    store: ScopedTraceStoreV2,
    problems: list[str],
) -> None:
    if store.snapshot_scoped_v2(_SCOPE_A, "commit"):
        problems.append("fresh_store_not_empty")
    original = _event(1)
    first = store.append_scoped_v2(original)
    if not _valid_receipt(first, "appended", 0, original):
        problems.append("first_append_binding")
    original.event.lineage["nested"]["items"].append(99)
    first.record.event.event.lineage["nested"]["items"].append(88)
    observed = store.snapshot_scoped_v2(_SCOPE_A, "commit")
    if len(observed) != 1 or observed[0].event.event.lineage["nested"]["items"] != [1]:
        problems.append("input_output_snapshot_isolation")
    if observed:
        observed[0].event.event.lineage["nested"]["items"].append(77)
        if store.snapshot_scoped_v2(_SCOPE_A, "commit")[0].event.event.lineage[
            "nested"
        ]["items"] != [1]:
            problems.append("snapshot_history_mutated")

    replay = store.append_scoped_v2(_event(1))
    if not _valid_receipt(replay, "replayed", 0, _event(1)):
        problems.append("exact_replay")


def _exercise_rejections(
    store: ScopedTraceStoreV2,
    problems: list[str],
) -> None:
    before = store.checkpoint_v2()
    _exercise_identity_conflict_rejections(store, problems)
    _exercise_malformed_envelope_rejections(store, problems)
    _exercise_unicode_event_rejections(store, problems)
    if store.checkpoint_v2() != before:
        problems.append("rejection_not_atomic")


def _exercise_identity_conflict_rejections(
    store: ScopedTraceStoreV2,
    problems: list[str],
) -> None:
    for conflict in (
        _event(2, trace_id="trace:1"),
        _event(2, transition_id="transition:1"),
    ):
        try:
            store.append_scoped_v2(conflict)
        except ValueError:
            pass
        else:
            problems.append("identity_conflict_accepted")


def _exercise_malformed_envelope_rejections(
    store: ScopedTraceStoreV2,
    problems: list[str],
) -> None:
    malformed_scope = _event(9)
    object.__setattr__(malformed_scope, "scope_ref", _SCOPE_B)
    malformed = (
        malformed_scope,
        _event(9, stream="commit\x00hidden"),
        _event(9, stream="cafe\u0301"),
        _event(9, trace_id="trace\x00hidden"),
        _event(9, trace_id="trace:cafe\u0301"),
        _event(9, transition_id="transition\x00hidden"),
        _event(9, transition_id="transition:cafe\u0301"),
        _event(9, stream="invalid-\ud800"),
        _event(9, trace_id="invalid-\ud800"),
        _event(9, transition_id="invalid-\ud800"),
    )
    for item in malformed:
        try:
            store.append_scoped_v2(item)
        except (TypeError, ValueError):
            pass
        else:
            problems.append("malformed_envelope_accepted")


def _exercise_unicode_event_rejections(
    store: ScopedTraceStoreV2,
    problems: list[str],
) -> None:
    malformed_body = _event(10)
    object.__setattr__(malformed_body.event, "reason", "invalid-\ud800")
    malformed_lineage = _event(11)
    malformed_lineage.event.lineage["invalid-\ud800"] = "value"
    for item in (malformed_body, malformed_lineage):
        try:
            store.append_scoped_v2(item)
        except (TypeError, ValueError):
            pass
        else:
            problems.append("unicode_surrogate_event_accepted")


def _exercise_scope_and_cursor(
    store: ScopedTraceStoreV2,
    problems: list[str],
) -> None:
    cursor = store.cursor_scoped_v2(_SCOPE_A, "commit")
    second = store.append_scoped_v2(_event(2))
    cross_scope = store.append_scoped_v2(_event(3, scope_ref=_SCOPE_B))
    cross_stream = store.append_scoped_v2(_event(4, stream="audit"))
    if not _valid_receipt(second, "appended", 1, _event(2)):
        problems.append("second_append_binding")
    if cross_scope.record.sequence != 0 or cross_stream.record.sequence != 0:
        problems.append("scope_stream_sequence_isolation")
    tail = store.snapshot_scoped_v2(_SCOPE_A, "commit", cursor)
    if len(tail) != 1 or tail[0].event.trace_id != "trace:2":
        problems.append("cursor_tail")
    if len(store.snapshot_scoped_v2(_SCOPE_B, "commit")) != 1:
        problems.append("cross_scope_isolation")
    if len(store.snapshot_scoped_v2(_SCOPE_A, "audit")) != 1:
        problems.append("cross_stream_isolation")


def _exercise_restart(
    store: ScopedTraceStoreV2,
    adapter: ScopedTraceStoreConformanceAdapterV2,
    problems: list[str],
) -> ScopedTraceStoreV2 | None:
    checkpoint = store.checkpoint_v2()
    try:
        portable = ScopedTraceCheckpointV2.from_dict(checkpoint.to_dict())
        restarted = adapter.restart_store_v2(store, portable)
    except Exception as exc:
        problems.append(f"restart_exception:{type(exc).__name__}")
        return None
    if not isinstance(restarted, ScopedTraceStoreV2):
        problems.append("restart_store_protocol")
        return None
    if restarted.checkpoint_v2() != checkpoint:
        problems.append("restart_checkpoint")
    if restarted.cursor_scoped_v2(_SCOPE_A, "commit") != store.cursor_scoped_v2(
        _SCOPE_A, "commit"
    ):
        problems.append("restart_cursor")
    return restarted


def _exercise_retirement(
    restarted: ScopedTraceStoreV2,
    adapter: ScopedTraceStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    retirement = restarted.retire_scope_v2(_SCOPE_A)
    if retirement != restarted.retire_scope_v2(_SCOPE_A):
        problems.append("retirement_idempotence")
    if len(restarted.snapshot_scoped_v2(_SCOPE_A, "commit")) != 2:
        problems.append("retired_history_unreadable")
    for blocked in (_event(1), _event(5)):
        try:
            restarted.append_scoped_v2(blocked)
        except ValueError:
            pass
        else:
            problems.append("retired_scope_append_accepted")
    restarted_again = adapter.restart_store_v2(restarted, restarted.checkpoint_v2())
    try:
        restarted_again.append_scoped_v2(_event(1))
    except ValueError:
        pass
    else:
        problems.append("retirement_lost_on_restart")


def _exercise_races(
    adapter: ScopedTraceStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    replay_store = adapter.create_store_v2()
    if not isinstance(replay_store, ScopedTraceStoreV2):
        problems.append("race_store_protocol")
        return
    with ThreadPoolExecutor(max_workers=32) as pool:
        receipts = tuple(
            pool.map(lambda _: replay_store.append_scoped_v2(_event(1)), range(32))
        )
    if sum(item.disposition == "appended" for item in receipts) != 1:
        problems.append("race_replay_publication_count")
    if len({item.record.record_root for item in receipts}) != 1:
        problems.append("race_replay_record_identity")
    if len(replay_store.snapshot_scoped_v2(_SCOPE_A, "commit")) != 1:
        problems.append("race_replay_history")

    distinct_store = adapter.create_store_v2()
    if not isinstance(distinct_store, ScopedTraceStoreV2):
        problems.append("distinct_race_store_protocol")
        return
    with ThreadPoolExecutor(max_workers=32) as pool:
        tuple(
            pool.map(
                lambda ordinal: distinct_store.append_scoped_v2(_event(ordinal)),
                range(1, 65),
            )
        )
    records = distinct_store.snapshot_scoped_v2(_SCOPE_A, "commit")
    if tuple(item.sequence for item in records) != tuple(range(64)):
        problems.append("race_distinct_sequence")
    if {item.event.trace_id for item in records} != {
        f"trace:{item}" for item in range(1, 65)
    }:
        problems.append("race_distinct_loss_or_duplicate")


def _exercise_checkpoint_order(
    adapter: ScopedTraceStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    store = adapter.create_store_v2()
    if not isinstance(store, ScopedTraceStoreV2):
        problems.append("checkpoint_order_store_protocol")
        return
    store.append_scoped_v2(_event(1, scope_ref=_SCOPE_B, stream="z"))
    store.append_scoped_v2(_event(2, scope_ref=_SCOPE_A, stream="z"))
    store.append_scoped_v2(_event(3, scope_ref=_SCOPE_A, stream="a"))
    store.retire_scope_v2(_SCOPE_B)
    store.retire_scope_v2(_SCOPE_A)
    checkpoint = store.checkpoint_v2()
    keys = tuple(
        (item.scope_ref, item.stream, item.sequence) for item in checkpoint.records
    )
    if keys != tuple(sorted(keys)):
        problems.append("checkpoint_record_order")
    retirement_keys = tuple(item.scope_ref for item in checkpoint.retirements)
    if retirement_keys != tuple(sorted(retirement_keys)):
        problems.append("checkpoint_retirement_order")
    try:
        ScopedTraceCheckpointV2.from_dict(checkpoint.to_dict())
    except (TypeError, ValueError):
        problems.append("checkpoint_portable_canonical_order")
    forged_records = deepcopy(checkpoint)
    object.__setattr__(
        forged_records,
        "records",
        tuple(reversed(forged_records.records)),
    )
    forged_retirements = deepcopy(checkpoint)
    object.__setattr__(
        forged_retirements,
        "retirements",
        tuple(reversed(forged_retirements.retirements)),
    )
    forged_root = deepcopy(checkpoint)
    object.__setattr__(forged_root, "checkpoint_root", "sha256:" + "0" * 64)
    for label, forged in (
        ("records", forged_records),
        ("retirements", forged_retirements),
        ("root", forged_root),
    ):
        try:
            adapter.restart_store_v2(store, forged)
        except (TypeError, ValueError):
            pass
        else:
            problems.append(f"checkpoint_{label}_tamper_accepted")


def _exercise_failures(
    adapter: ScopedTraceStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    for stage in SCOPED_TRACE_STORE_FAILURE_STAGES_V2:
        store = adapter.create_failure_injected_store_v2(stage)
        if not isinstance(store, ScopedTraceStoreV2):
            problems.append(f"failure_store_protocol:{stage}")
            continue
        try:
            if stage == "append_before_publish":
                store.append_scoped_v2(_event(1))
            elif stage == "retire_before_publish":
                store.retire_scope_v2(_SCOPE_A)
            else:
                store.checkpoint_v2()
        except Exception:
            pass
        else:
            problems.append(f"failure_not_injected:{stage}")
        if store.snapshot_scoped_v2(_SCOPE_A, "commit"):
            problems.append(f"failure_published_record:{stage}")
        if stage == "retire_before_publish":
            try:
                store.append_scoped_v2(_event(1))
            except Exception:
                problems.append("retirement_failure_published_tombstone")


def _valid_receipt(
    receipt: object,
    disposition: str,
    sequence: int,
    expected: ScopedTraceEvent,
) -> bool:
    if not isinstance(receipt, ScopedTraceAppendReceiptV2):
        return False
    detached = ScopedTraceAppendReceiptV2.from_dict(deepcopy(receipt.to_dict()))
    return (
        detached.disposition == disposition
        and detached.record.sequence == sequence
        and detached.record.event == expected
    )


ScopedTraceStoreConformanceAdapterV2.__module__ = "pheroos.conformance"
ReferenceScopedTraceStoreConformanceAdapterV2.__module__ = "pheroos.conformance"
run_scoped_trace_store_conformance_v2.__module__ = "pheroos.conformance"


__all__ = [
    "SCOPED_TRACE_STORE_CONFORMANCE_VERSION_V2",
    "SCOPED_TRACE_STORE_FAILURE_STAGES_V2",
    "ReferenceScopedTraceStoreConformanceAdapterV2",
    "ScopedTraceStoreConformanceAdapterV2",
    "run_scoped_trace_store_conformance_v2",
]
