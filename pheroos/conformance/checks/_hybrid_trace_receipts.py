from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pheroos.governance import HybridReplayState, hybrid_replay_state_is_authoritative
from pheroos.trace import TraceEvent, pheromone_clip_payload_fingerprint


def replay_trace_problems(
    events: tuple[TraceEvent, ...],
    score_event: TraceEvent,
    *,
    replay_state: HybridReplayState | None,
    protocol_id: str,
    target: str,
) -> list[str]:
    """Bind every replay claim to an externally supplied issued replay state."""

    authoritative, issue = _authoritative_replay_receipts(
        replay_state, protocol_id, target
    )
    if issue is not None:
        return [issue]
    expected = _empty_replay_snapshot()
    problems: list[str] = []
    for index, event in enumerate(events):
        lifecycle = _replay_lifecycle(event)
        if lifecycle is not None:
            problems.extend(
                _replay_event_problems(index, event, lifecycle, authoritative, expected)
            )
    problems.extend(_replay_snapshot_problems(score_event, expected))
    return problems


def _empty_replay_snapshot() -> dict[str, dict[str, str]]:
    return {
        lifecycle: {}
        for lifecycle in ("deposit", "diffusion", "feedback", "adjustment")
    }


def _authoritative_replay_receipts(
    replay_state: HybridReplayState | None,
    protocol_id: str,
    target: str,
) -> tuple[dict[str, Mapping[str, tuple[Any, ...]]], str | None]:
    empty: dict[str, Mapping[str, tuple[Any, ...]]] = {
        lifecycle: {}
        for lifecycle in ("deposit", "diffusion", "feedback", "adjustment")
    }
    if replay_state is None:
        return empty, None
    if not hybrid_replay_state_is_authoritative(replay_state):
        return empty, "authority_replay_state_not_issued"
    if replay_state.protocol_id != protocol_id or replay_state.target != target:
        return empty, "authority_replay_state_binding"
    return {
        "deposit": replay_state.deposit_replay_receipts,
        "diffusion": replay_state.diffusion_replay_receipts,
        "feedback": replay_state.feedback_replay_receipts,
        "adjustment": replay_state.adjustment_replay_receipts,
    }, None


def _replay_lifecycle(event: TraceEvent) -> str | None:
    lineage = event.lineage
    if (
        event.event_type == "pheromone_observe"
        and lineage.get("result") == "replay_ignored"
    ):
        return str(lineage.get("lifecycle", ""))
    if (
        event.event_type == "policy_adjustment"
        and lineage.get("result") == "replay_ignored"
    ):
        return "adjustment"
    return None


def _replay_event_problems(
    index: int,
    event: TraceEvent,
    lifecycle: str,
    authoritative: dict[str, Mapping[str, tuple[Any, ...]]],
    expected: dict[str, dict[str, str]],
) -> list[str]:
    lineage = event.lineage
    trace_id = str(lineage.get("source_trace_event_id", ""))
    if lifecycle not in expected:
        return [f"authority_replay_lifecycle:{index}"]
    problems: list[str] = []
    if trace_id in expected[lifecycle]:
        problems.append(f"authority_replay_duplicate:{lifecycle}:{trace_id}")
    payload = lineage.get("replay_payload")
    if not isinstance(payload, (list, tuple)):
        problems.append(f"authority_replay_payload:{index}")
        return problems
    current = _canonical_trace_replay_receipt(payload)
    processed = authoritative[lifecycle].get(trace_id)
    if processed is None:
        problems.append(f"authority_replay_receipt_not_in_state:{lifecycle}:{trace_id}")
        return problems
    problems.extend(
        _replay_receipt_binding_problems(
            lineage, lifecycle, trace_id, current, processed
        )
    )
    expected[lifecycle][trace_id] = _replay_receipt_fingerprint(processed)
    return problems


def _replay_receipt_binding_problems(
    lineage: Any,
    lifecycle: str,
    trace_id: str,
    current: tuple[Any, ...],
    processed: tuple[Any, ...],
) -> list[str]:
    digest = _replay_receipt_fingerprint(processed)
    checks = (
        (
            current != processed,
            f"authority_replay_payload_state_mismatch:{lifecycle}:{trace_id}",
        ),
        (
            lineage.get("replay_payload_fingerprint") != digest,
            f"authority_replay_payload_fingerprint:{lifecycle}:{trace_id}",
        ),
        (
            lineage.get("processed_payload_fingerprint") != digest,
            f"authority_replay_processed_fingerprint:{lifecycle}:{trace_id}",
        ),
    )
    return [message for failed, message in checks if failed]


def _replay_snapshot_problems(
    score_event: TraceEvent,
    expected: dict[str, dict[str, str]],
) -> list[str]:
    observed = score_event.lineage.get("processed_replay_receipts")
    if not isinstance(observed, dict):
        return ["authority_replay_receipt_snapshot_missing"]
    if set(observed) != set(expected):
        return ["authority_replay_receipt_snapshot_lifecycles"]
    return [
        f"authority_replay_receipt_snapshot:{lifecycle}"
        for lifecycle, receipts in expected.items()
        if observed.get(lifecycle) != receipts
    ]


def _canonical_trace_replay_receipt(value: Any) -> tuple[Any, ...]:
    def freeze(item: Any) -> Any:
        if isinstance(item, Mapping):
            return tuple(
                (str(key), freeze(nested))
                for key, nested in sorted(item.items(), key=lambda pair: str(pair[0]))
            )
        if isinstance(item, (list, tuple)):
            return tuple(freeze(nested) for nested in item)
        return item

    return tuple(freeze(item) for item in value)


def _replay_receipt_fingerprint(receipt: tuple[Any, ...]) -> str:
    return str(
        pheromone_clip_payload_fingerprint(
            {
                "lifecycle": "replay_receipt",
                "receipt": receipt,
            }
        )
    )
