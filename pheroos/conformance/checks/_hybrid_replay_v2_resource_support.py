"""Public-constructor resource vectors for Hybrid Replay v2 Conformance.

Cycle and over-limit vectors must be rejected at resource preflight.  Exact
depth/node/text/lineage vectors deliberately contain one unknown closed-shape
field: they prove that the exact resource boundary is passed and then fail at
ordinary shape validation.  The exact causal vector similarly reaches JSON
validation.  By contrast, the exact 16 MiB vector is a fully valid snapshot.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from pheroos.governance import (
    HybridReplayAdvanceRequestV2,
    HybridReplaySnapshotV2,
    VerifiedHybridSourceStepV2,
)


_MAX_CAUSAL_PAYLOAD_BYTES_V2 = 256 * 1024
_MAX_TOTAL_CAUSAL_PAYLOAD_BYTES_V2 = 8 * 1024 * 1024
_MAX_TOTAL_LINEAGE_BYTES_V2 = 4 * 1024 * 1024
_MAX_RESOURCE_TEXT_BYTES_V2 = 12 * 1024 * 1024
_MAX_SNAPSHOT_BYTES_V2 = 16 * 1024 * 1024
_MAX_RESOURCE_NODES_V2 = 262_144
_MAX_RESOURCE_DEPTH_V2 = 64
_FINAL_SNAPSHOT_TRAILS_V2 = 3_000
_RESOURCE_COMPONENT_FIELDS = (
    "candidate_projection",
    "policy_projection",
    "topology_projection",
    "active_trails",
    "replay_receipts",
    "last_budget",
    "overlay",
    "effective_policy_projection",
    "source_trace_roots",
)
_LINEAGE_RESOURCE_FIELDS = frozenset(
    {
        "lineage_event_ids",
        "lineage_event_refs",
        "source_refs",
        "source_trace_roots",
        "trace_roots",
    }
)

_SourceFactory = Callable[..., VerifiedHybridSourceStepV2]
_RequestFactory = Callable[..., HybridReplayAdvanceRequestV2]


@dataclass(slots=True)
class _ResourceUsageV2:
    nodes: int = 0
    text_bytes: int = 0
    lineage_bytes: int = 0
    maximum_depth: int = 0


def run_public_hybrid_replay_resource_matrix_v2(
    *,
    context: Any,
    store: Any,
    source_factory: _SourceFactory,
    request_factory: _RequestFactory,
) -> tuple[str, ...]:
    """Exercise real ABI limits with public constructors and zero Store writes."""

    problems: list[str] = []
    source = source_factory(context, current_step=1, event_suffix="resources")
    request = request_factory(
        context,
        source,
        "advance:public-resources",
        observed_epoch=3,
    )
    baseline = request.snapshot.to_dict()
    before = store.load_head_v2(request.scope_ref, request.stream_ref)
    store.reset_observations()

    _check_cycle_and_depth_bounds(baseline, problems)
    _check_node_text_and_lineage_bounds(baseline, problems)
    _check_aggregate_causal_bound(baseline, problems)
    _check_final_snapshot_bound(baseline, problems)

    after = store.load_head_v2(request.scope_ref, request.stream_ref)
    if (
        store.atomic_commits != 0
        or after.revision != before.revision
        or after.head_root != before.head_root
    ):
        problems.append("resource_rejection_zero_write")
    return tuple(problems)


def _check_cycle_and_depth_bounds(
    baseline: Mapping[str, object],
    problems: list[str],
) -> None:
    cycle: dict[str, object] = {}
    cycle["self"] = cycle
    cyclic = _replace_component(baseline, "overlay", cycle)
    _expect_resource_error(cyclic, "container cycle", "resource_cycle", problems)

    exact_value = _nested_lists(_MAX_RESOURCE_DEPTH_V2 - 2)
    exact_overlay = dict(cast(Mapping[str, object], baseline["overlay"]))
    exact_overlay["x-resource-depth"] = exact_value
    exact = _replace_component(baseline, "overlay", exact_overlay)
    if _measure_resource_envelope(exact).maximum_depth != _MAX_RESOURCE_DEPTH_V2:
        problems.append("resource_depth_vector")
    _expect_later_error(
        exact,
        "policy overlay fields invalid",
        "resource_depth_exact",
        problems,
    )

    over_overlay = dict(cast(Mapping[str, object], baseline["overlay"]))
    over_overlay["x-resource-depth"] = _nested_lists(_MAX_RESOURCE_DEPTH_V2 - 1)
    over = _replace_component(baseline, "overlay", over_overlay)
    _expect_resource_error(over, "depth bound", "resource_depth_over", problems)


def _check_node_text_and_lineage_bounds(
    baseline: Mapping[str, object],
    problems: list[str],
) -> None:
    node_overlay = dict(cast(Mapping[str, object], baseline["overlay"]))
    node_overlay["x-resource-nodes"] = []
    node_exact = _replace_component(baseline, "overlay", node_overlay)
    node_padding = _MAX_RESOURCE_NODES_V2 - _measure_resource_envelope(node_exact).nodes
    if node_padding < 0:
        problems.append("resource_node_vector")
    else:
        node_overlay["x-resource-nodes"] = [None] * node_padding
        node_exact = _replace_component(baseline, "overlay", node_overlay)
        _expect_later_error(
            node_exact,
            "policy overlay fields invalid",
            "resource_nodes_exact",
            problems,
        )
        node_overlay["x-resource-nodes"] = [None] * (node_padding + 1)
        _expect_resource_error(
            _replace_component(baseline, "overlay", node_overlay),
            "node bound",
            "resource_nodes_over",
            problems,
        )

    text_overlay = dict(cast(Mapping[str, object], baseline["overlay"]))
    text_overlay["x-resource-text"] = ""
    text_exact = _replace_component(baseline, "overlay", text_overlay)
    text_padding = (
        _MAX_RESOURCE_TEXT_BYTES_V2 - _measure_resource_envelope(text_exact).text_bytes
    )
    if text_padding < 0:
        problems.append("resource_text_vector")
    else:
        text_overlay["x-resource-text"] = "x" * text_padding
        text_exact = _replace_component(baseline, "overlay", text_overlay)
        _expect_later_error(
            text_exact,
            "policy overlay fields invalid",
            "resource_text_exact",
            problems,
        )
        text_overlay["x-resource-text"] = "x" * (text_padding + 1)
        _expect_resource_error(
            _replace_component(baseline, "overlay", text_overlay),
            "aggregate text",
            "resource_text_over",
            problems,
        )

    lineage_overlay = dict(cast(Mapping[str, object], baseline["overlay"]))
    lineage_overlay["lineage_event_refs"] = [""]
    lineage_exact = _replace_component(baseline, "overlay", lineage_overlay)
    lineage_padding = (
        _MAX_TOTAL_LINEAGE_BYTES_V2
        - _measure_resource_envelope(lineage_exact).lineage_bytes
    )
    if lineage_padding < 0:
        problems.append("resource_lineage_vector")
    else:
        lineage_overlay["lineage_event_refs"] = ["x" * lineage_padding]
        lineage_exact = _replace_component(baseline, "overlay", lineage_overlay)
        _expect_later_error(
            lineage_exact,
            "policy overlay fields invalid",
            "resource_lineage_exact",
            problems,
        )
        lineage_overlay["lineage_event_refs"] = ["x" * (lineage_padding + 1)]
        _expect_resource_error(
            _replace_component(baseline, "overlay", lineage_overlay),
            "aggregate lineage",
            "resource_lineage_over",
            problems,
        )


def _check_aggregate_causal_bound(
    baseline: Mapping[str, object],
    problems: list[str],
) -> None:
    receipts = cast(Sequence[Mapping[str, object]], baseline["replay_receipts"])
    template = next(
        (receipt for receipt in receipts if receipt.get("kind") == "diffusion"),
        None,
    )
    if template is None:
        problems.append("resource_causal_vector")
        return
    exact_count = _MAX_TOTAL_CAUSAL_PAYLOAD_BYTES_V2 // _MAX_CAUSAL_PAYLOAD_BYTES_V2
    exact_receipts = [
        _raw_causal_receipt(template, "x" * _MAX_CAUSAL_PAYLOAD_BYTES_V2)
        for _ in range(exact_count)
    ]
    exact = _replace_component(baseline, "replay_receipts", exact_receipts)
    _expect_later_error(
        exact,
        "invalid JSON",
        "resource_causal_exact",
        problems,
    )
    over_receipts = [*exact_receipts, _raw_causal_receipt(template, "x")]
    over = _replace_component(baseline, "replay_receipts", over_receipts)
    _expect_resource_error(
        over,
        "aggregate causal payload",
        "resource_causal_over",
        problems,
    )


def _check_final_snapshot_bound(
    baseline: Mapping[str, object],
    problems: list[str],
) -> None:
    active = cast(Sequence[Mapping[str, object]], baseline["active_trails"])
    if not active:
        problems.append("resource_snapshot_vector")
        return
    template = active[0]
    trails = [
        _resource_trail(template, index, quote_count=0)
        for index in range(_FINAL_SNAPSHOT_TRAILS_V2)
    ]
    base_payload = _snapshot_with_active_trails(baseline, trails)
    try:
        base_snapshot = HybridReplaySnapshotV2.from_dict(base_payload)
    except (TypeError, ValueError):
        problems.append("resource_snapshot_vector")
        return
    growth = _MAX_SNAPSHOT_BYTES_V2 - len(base_snapshot.canonical_bytes())
    if growth < 0:
        problems.append("resource_snapshot_vector")
        return
    del base_snapshot

    quote_total, plain_extra = divmod(growth, 2)
    quotes_per_trail, extra_quote_trails = divmod(
        quote_total, _FINAL_SNAPSHOT_TRAILS_V2
    )
    if quotes_per_trail + 32 > 4_096:
        problems.append("resource_snapshot_vector")
        return
    trails = [
        _resource_trail(
            template,
            index,
            quote_count=quotes_per_trail + (index < extra_quote_trails),
            plain_extra=bool(plain_extra and index == 0),
        )
        for index in range(_FINAL_SNAPSHOT_TRAILS_V2)
    ]
    exact_payload = _snapshot_with_active_trails(baseline, trails)
    try:
        exact = HybridReplaySnapshotV2.from_dict(exact_payload)
    except (TypeError, ValueError):
        problems.append("resource_snapshot_exact")
        return
    if len(exact.canonical_bytes()) != _MAX_SNAPSHOT_BYTES_V2:
        problems.append("resource_snapshot_exact")
        return
    over_payload = exact.to_dict()
    del exact
    over_trails = cast(list[dict[str, object]], over_payload["active_trails"])
    over_trails[0]["source_ref"] = cast(str, over_trails[0]["source_ref"]) + "x"
    over = _snapshot_with_active_trails(over_payload, over_trails)
    _expect_resource_error(
        over,
        "canonical snapshot exceeds",
        "resource_snapshot_over",
        problems,
    )


def _resource_trail(
    template: Mapping[str, object],
    index: int,
    *,
    quote_count: int,
    plain_extra: bool = False,
) -> dict[str, object]:
    trail = dict(template)
    source_ref = f"resource:{index:04d}:" + ('"' * quote_count)
    if plain_extra:
        source_ref += "x"
    event_ref = f"trace:resource-final:{index:04d}"
    lineage = list(cast(Sequence[str], trail["lineage_event_refs"]))
    lineage[-1] = event_ref
    trail["source_ref"] = source_ref
    trail["trace_event_ref"] = event_ref
    trail["lineage_event_refs"] = lineage
    return trail


def _snapshot_with_active_trails(
    baseline: Mapping[str, object],
    trails: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    payload = dict(baseline)
    payload["active_trails"] = list(trails)
    payload["active_trails_root"] = ""
    payload["state_root"] = ""
    payload["snapshot_root"] = ""
    return payload


def _raw_causal_receipt(
    template: Mapping[str, object],
    canonical: str,
) -> dict[str, object]:
    receipt = dict(template)
    payload = dict(cast(Mapping[str, object], receipt["payload"]))
    payload["canonical_causal_payload"] = canonical
    receipt["payload"] = payload
    receipt["payload_root"] = ""
    return receipt


def _replace_component(
    baseline: Mapping[str, object],
    field: str,
    value: object,
) -> dict[str, object]:
    payload = dict(baseline)
    payload[field] = value
    return payload


def _nested_lists(levels: int) -> object:
    value: object = None
    for _ in range(levels):
        value = [value]
    return value


def _measure_resource_envelope(payload: Mapping[str, object]) -> _ResourceUsageV2:
    envelope = {field: payload[field] for field in _RESOURCE_COMPONENT_FIELDS}
    usage = _ResourceUsageV2()
    _walk_resource(envelope, depth=0, lineage=False, usage=usage)
    return usage


def _walk_resource(
    value: object,
    *,
    depth: int,
    lineage: bool,
    usage: _ResourceUsageV2,
) -> None:
    usage.nodes += 1
    usage.maximum_depth = max(usage.maximum_depth, depth)
    if type(value) is str:
        size = len((value).encode("utf-8"))
        usage.text_bytes += size
        if lineage:
            usage.lineage_bytes += size
        return
    if type(value) in (list, tuple):
        for item in cast(Sequence[object], value):
            _walk_resource(
                item,
                depth=depth + 1,
                lineage=lineage,
                usage=usage,
            )
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            usage.nodes += 1
            child_lineage = lineage
            if type(key) is str:
                key_text = key
                usage.text_bytes += len(key_text.encode("utf-8"))
                child_lineage = lineage or key_text in _LINEAGE_RESOURCE_FIELDS
            _walk_resource(
                item,
                depth=depth + 1,
                lineage=child_lineage,
                usage=usage,
            )


def _expect_later_error(
    payload: Mapping[str, object],
    expected: str,
    label: str,
    problems: list[str],
) -> None:
    """Require an exact-bound vector to reach a later validation phase."""

    error = _snapshot_error(payload)
    if error is None or expected not in error:
        problems.append(label)


def _expect_resource_error(
    payload: Mapping[str, object],
    expected: str,
    label: str,
    problems: list[str],
) -> None:
    error = _snapshot_error(payload)
    if error is None or expected not in error:
        problems.append(label)


def _snapshot_error(payload: Mapping[str, object]) -> str | None:
    try:
        HybridReplaySnapshotV2.from_dict(payload)
    except (TypeError, ValueError) as exc:
        return str(exc)
    return None


__all__: list[str] = []
