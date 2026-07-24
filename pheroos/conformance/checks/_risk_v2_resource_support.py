"""Exact public resource-boundary checks for durable Risk v2 contracts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256
from typing import Any

from pheroos.conformance.checks._risk_v2_store_support import (
    fault_risk_context_v2,
    risk_head_revision_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.risk_v2 import (
    MAX_RISK_INPUT_ROOTS_V2,
    MAX_RISK_RATIONALE_CODES_V2,
    MAX_RISK_RESOURCE_DEPTH_V2,
    MAX_RISK_RESOURCE_NODES_V2,
    MAX_RISK_RESOURCE_TEXT_BYTES_V2,
    MAX_RISK_SNAPSHOT_BYTES_V2,
    MAX_RISK_SOURCE_TRACE_ROOTS_V2,
    MAX_RISK_TEXT_BYTES_V2,
    RiskStateSnapshotV2,
    RiskThresholdSnapshotV2,
)


def run_risk_v2_resource_matrix(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    *,
    context_factory: Callable[..., Any],
    request_factory: Callable[..., Any],
    advance_factory: Callable[..., Any],
) -> list[str]:
    """Exercise every declared Risk v2 cap at the boundary and one beyond."""

    del advance_factory
    problems: list[str] = []
    context, store = fault_risk_context_v2(adapter, context_factory, "resources")
    base, _ = request_factory(context, advance_ref="advance:resource-base")
    _collection_bounds(context, request_factory, problems)
    _individual_text_bound(base, problems)
    _portable_tree_bounds(base.snapshot.threshold, problems)
    _snapshot_byte_bound(base.snapshot, problems)
    if store.atomic_commits != 0 or risk_head_revision_v2(context, base) != 0:
        problems.append("resource_rejection_zero_write")
    return problems


def _collection_bounds(
    context: Any,
    request_factory: Callable[..., Any],
    problems: list[str],
) -> None:
    input_roots = tuple(
        _root(f"resource-input:{index}") for index in range(MAX_RISK_INPUT_ROOTS_V2)
    )
    exact_inputs, _ = request_factory(
        context,
        advance_ref="advance:resource-input-exact",
        risk_input_roots=input_roots,
    )
    if len(exact_inputs.snapshot.assessment.risk_input_roots) != len(input_roots):
        problems.append("resource_input_exact")
    if not _rejects(
        lambda: request_factory(
            context,
            advance_ref="advance:resource-input-over",
            risk_input_roots=(*input_roots, _root("resource-input:over")),
        )
    ):
        problems.append("resource_input_over")

    rationales = tuple(
        f"risk-rationale:{index}" for index in range(MAX_RISK_RATIONALE_CODES_V2)
    )
    exact_rationales, _ = request_factory(
        context,
        advance_ref="advance:resource-rationale-exact",
        rationale_codes=rationales,
    )
    if len(exact_rationales.snapshot.assessment.rationale_codes) != len(rationales):
        problems.append("resource_rationale_exact")
    if not _rejects(
        lambda: request_factory(
            context,
            advance_ref="advance:resource-rationale-over",
            rationale_codes=(*rationales, "risk-rationale:over"),
        )
    ):
        problems.append("resource_rationale_over")

    traces = tuple(
        _root(f"resource-trace:{index}")
        for index in range(MAX_RISK_SOURCE_TRACE_ROOTS_V2)
    )
    exact_traces, _ = request_factory(
        context,
        advance_ref="advance:resource-trace-exact",
        source_trace_roots=traces,
    )
    if len(exact_traces.snapshot.assessment.source_trace_roots) != len(traces):
        problems.append("resource_trace_exact")
    if not _rejects(
        lambda: request_factory(
            context,
            advance_ref="advance:resource-trace-over",
            source_trace_roots=(*traces, _root("resource-trace:over")),
        )
    ):
        problems.append("resource_trace_over")


def _individual_text_bound(base: Any, problems: list[str]) -> None:
    assessment = base.snapshot.assessment
    exact = replace(
        assessment,
        assessment_ref="a" * MAX_RISK_TEXT_BYTES_V2,
        assessment_root="",
    )
    if len(exact.assessment_ref.encode("utf-8")) != MAX_RISK_TEXT_BYTES_V2:
        problems.append("resource_text_exact")
    if not _rejects(
        lambda: replace(
            assessment,
            assessment_ref="a" * (MAX_RISK_TEXT_BYTES_V2 + 1),
            assessment_root="",
        )
    ):
        problems.append("resource_text_over")


def _portable_tree_bounds(
    threshold: RiskThresholdSnapshotV2,
    problems: list[str],
) -> None:
    exact_depth: object = "leaf"
    for _ in range(MAX_RISK_RESOURCE_DEPTH_V2 - 1):
        exact_depth = [exact_depth]
    depth_threshold = _threshold_with_extensions(threshold, {"x-risk-v2": exact_depth})
    if not depth_threshold.extensions:
        problems.append("resource_depth_exact")
    if not _rejects(
        lambda: _threshold_with_extensions(threshold, {"x-risk-v2": [exact_depth]})
    ):
        problems.append("resource_depth_over")

    # Mapping + key + sequence consume three nodes before the sequence items.
    exact_node_items = MAX_RISK_RESOURCE_NODES_V2 - 3
    node_threshold = _threshold_with_extensions(
        threshold, {"x-risk-v2": [None] * exact_node_items}
    )
    if not node_threshold.extensions:
        problems.append("resource_nodes_exact")
    if not _rejects(
        lambda: _threshold_with_extensions(
            threshold, {"x-risk-v2": [None] * (exact_node_items + 1)}
        )
    ):
        problems.append("resource_nodes_over")

    extension_key = "x-risk-v2"
    exact_text_bytes = MAX_RISK_RESOURCE_TEXT_BYTES_V2 - len(
        extension_key.encode("utf-8")
    )
    text_threshold = _threshold_with_extensions(
        threshold, {extension_key: "x" * exact_text_bytes}
    )
    if not text_threshold.extensions:
        problems.append("resource_aggregate_text_exact")
    if not _rejects(
        lambda: _threshold_with_extensions(
            threshold, {extension_key: "x" * (exact_text_bytes + 1)}
        )
    ):
        problems.append("resource_aggregate_text_over")

    cycle: list[object] = []
    cycle.append(cycle)
    if not _rejects(
        lambda: _threshold_with_extensions(threshold, {"x-risk-v2": cycle})
    ):
        problems.append("resource_cycle")


def _snapshot_byte_bound(
    base: RiskStateSnapshotV2,
    problems: list[str],
) -> None:
    empty_threshold = _threshold_with_extensions(base.threshold, {"x-risk-v2": ""})
    empty_snapshot = replace(
        base,
        threshold=empty_threshold,
        snapshot_root="",
    )
    padding = MAX_RISK_SNAPSHOT_BYTES_V2 - len(empty_snapshot.canonical_bytes())
    if padding < 0:
        problems.append("resource_snapshot_fixture")
        return
    exact_threshold = _threshold_with_extensions(
        base.threshold, {"x-risk-v2": "x" * padding}
    )
    exact_snapshot = replace(
        base,
        threshold=exact_threshold,
        snapshot_root="",
    )
    if len(exact_snapshot.canonical_bytes()) != MAX_RISK_SNAPSHOT_BYTES_V2:
        problems.append("resource_snapshot_exact")
    over_threshold = _threshold_with_extensions(
        base.threshold, {"x-risk-v2": "x" * (padding + 1)}
    )
    if not _rejects(
        lambda: replace(
            base,
            threshold=over_threshold,
            snapshot_root="",
        )
    ):
        problems.append("resource_snapshot_over")


def _threshold_with_extensions(
    threshold: RiskThresholdSnapshotV2,
    extensions: dict[str, object],
) -> RiskThresholdSnapshotV2:
    return replace(
        threshold,
        extensions=extensions,
        threshold_root="",
    )


def _rejects(action: Callable[[], object]) -> bool:
    try:
        action()
    except (TypeError, ValueError):
        return True
    return False


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


__all__: list[str] = []
