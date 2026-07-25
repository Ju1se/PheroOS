"""Detached-view integrity and typed fail-closed checks for Risk v2."""

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
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
)
from pheroos.governance.risk_v2 import (
    RiskBand,
    rehydrate_risk_state_v2,
    require_current_risk_state_v2,
    risk_state_is_current_v2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


_TYPED_INTEGRITY_CODES = frozenset(
    {
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_TRACE_LINEAGE_INVALID,
    }
)


def run_risk_v2_integrity_matrix(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    *,
    context_factory: Callable[..., Any],
    request_factory: Callable[..., Any],
    advance_factory: Callable[..., Any],
) -> list[str]:
    """Reject detached inclusion, position, state, Trace, and read-set damage."""

    problems: list[str] = []
    for mutation in ("inclusion", "position", "state", "trace", "read_set"):
        _detached_view_mutation(
            adapter,
            context_factory,
            request_factory,
            advance_factory,
            mutation,
            problems,
        )
    _forged_current_position(
        adapter,
        context_factory,
        request_factory,
        advance_factory,
        problems,
    )
    _cross_domain_rehydration(
        adapter,
        context_factory,
        request_factory,
        advance_factory,
        problems,
    )
    _noncanonical_portable_wire(
        adapter,
        context_factory,
        request_factory,
        advance_factory,
        problems,
    )
    return problems


def _portable_root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _noncanonical_portable_wire(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: Callable[..., Any],
    request_factory: Callable[..., Any],
    advance_factory: Callable[..., Any],
    problems: list[str],
) -> None:
    context, store = fault_risk_context_v2(
        adapter,
        context_factory,
        "noncanonical-portable-wire",
    )
    request, source = request_factory(
        context,
        advance_ref="advance:noncanonical-portable-wire",
        risk_input_roots=(
            _portable_root("risk-wire-input:alpha"),
            _portable_root("risk-wire-input:omega"),
        ),
        rationale_codes=("risk_wire_alpha", "risk_wire_omega"),
        source_trace_roots=(
            _portable_root("risk-wire-trace:alpha"),
            _portable_root("risk-wire-trace:omega"),
        ),
    )
    committed = advance_factory(context, request, source)
    if committed.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        problems.append("noncanonical_wire_setup")
        return

    store.reset_observations()
    _check_bool_epoch_rejection(context, store, request, problems)
    if not _check_empty_root_rejection(context, store, request, problems):
        return
    _check_reordered_array_rejection(context, store, request, problems)


def _check_bool_epoch_rejection(
    context: Any,
    store: Any,
    request: Any,
    problems: list[str],
) -> None:
    try:
        replace(request, epoch=True, request_root="")
    except (TypeError, ValueError):
        pass
    else:
        problems.append("bool_epoch_exact_type")
    if store.atomic_commits != 0 or risk_head_revision_v2(context, request) != 1:
        problems.append("bool_epoch_exact_type_zero_write")


def _check_empty_root_rejection(
    context: Any,
    store: Any,
    request: Any,
    problems: list[str],
) -> bool:
    empty_roots = request.to_dict()
    snapshot = empty_roots["snapshot"]
    if type(snapshot) is not dict:
        problems.append("noncanonical_wire_snapshot_shape")
        return False
    assessment = snapshot["assessment"]
    threshold = snapshot["threshold"]
    if type(assessment) is not dict or type(threshold) is not dict:
        problems.append("noncanonical_wire_record_shape")
        return False
    for owner, field in (
        (empty_roots, "request_root"),
        (snapshot, "snapshot_root"),
        (assessment, "assessment_root"),
        (threshold, "threshold_root"),
    ):
        owner[field] = ""
    _expect_portable_wire_rejection(
        context,
        store,
        request,
        empty_roots,
        "noncanonical_wire_empty_roots",
        problems,
    )
    return True


def _check_reordered_array_rejection(
    context: Any,
    store: Any,
    request: Any,
    problems: list[str],
) -> None:
    reordered = request.to_dict()
    reordered_snapshot = reordered["snapshot"]
    if type(reordered_snapshot) is not dict:
        problems.append("noncanonical_wire_reordered_snapshot_shape")
        return
    reordered_assessment = reordered_snapshot["assessment"]
    if type(reordered_assessment) is not dict:
        problems.append("noncanonical_wire_reordered_record_shape")
        return
    for field in ("risk_input_roots", "rationale_codes", "source_trace_roots"):
        values = reordered_assessment[field]
        if type(values) is not list:
            problems.append("noncanonical_wire_reordered_array_shape")
            return
        reordered_assessment[field] = list(reversed(values))
    _expect_portable_wire_rejection(
        context,
        store,
        request,
        reordered,
        "noncanonical_wire_reordered_arrays",
        problems,
    )


def _expect_portable_wire_rejection(
    context: Any,
    store: Any,
    request: Any,
    payload: dict[str, object],
    label: str,
    problems: list[str],
) -> None:
    store.reset_observations()
    try:
        rehydrate_risk_state_v2(
            payload,
            domain=context.domain,
            state_reader=context.store,
        )
    except GovernanceAuthorityBindingErrorV2 as exc:
        if exc.code is not AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH:
            problems.append(f"{label}_diagnostic")
    else:
        problems.append(f"{label}_accepted")
    if store.atomic_commits != 0 or risk_head_revision_v2(context, request) != 1:
        problems.append(f"{label}_zero_write")


def _detached_view_mutation(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: Callable[..., Any],
    request_factory: Callable[..., Any],
    advance_factory: Callable[..., Any],
    mutation: str,
    problems: list[str],
) -> None:
    context, store = fault_risk_context_v2(
        adapter, context_factory, f"detached-{mutation}"
    )
    request, source = request_factory(
        context, advance_ref=f"advance:detached:{mutation}"
    )
    committed = advance_factory(context, request, source)
    if committed.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        problems.append(f"{mutation}_setup")
        return

    store.view_mutator = lambda view: _mutate_view(view, mutation)
    store.reset_observations()
    retry = advance_factory(context, request, None)
    if (
        retry.disposition is not GovernanceCommitDispositionV2.INVALID
        or retry.failure is None
        or retry.failure.code not in _TYPED_INTEGRITY_CODES
        or retry.committed_transition is not None
    ):
        problems.append(f"{mutation}_retry_not_typed_fail_closed")
    _expect_typed_rehydrate_failure(context, request, problems, mutation)
    if store.atomic_commits != 0 or risk_head_revision_v2(context, request) != 1:
        problems.append(f"{mutation}_zero_write")

    # The proxy altered only a detached public view.  Once disabled, the
    # authoritative Store image must still rehydrate exactly.
    store.view_mutator = None
    recovered = rehydrate_risk_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    if recovered.snapshot.snapshot_root != request.snapshot.snapshot_root:
        problems.append(f"{mutation}_detached_store_preservation")


def _mutate_view(view: GovernanceCommitViewV2, mutation: str) -> None:
    committed = view.committed_transition
    if committed is None:
        raise ValueError("Risk v2 mutation requires a committed public view")
    if mutation == "inclusion":
        object.__setattr__(committed, "inclusion_proof", None)
        return
    if mutation == "position":
        object.__setattr__(view, "position_observation", None)
        return
    if mutation == "state":
        transition = committed.batch.transition
        if transition is None:
            raise ValueError("Risk v2 mutation requires transition state")
        object.__setattr__(transition, "state_records", {"forged": True})
        return
    if mutation == "trace":
        object.__setattr__(committed.batch, "trace_batch", None)
        return
    if mutation == "read_set":
        object.__setattr__(committed.batch.read_set, "entries", ())
        return
    raise ValueError("unsupported Risk v2 detached-view mutation")


def _expect_typed_rehydrate_failure(
    context: Any,
    request: Any,
    problems: list[str],
    mutation: str,
) -> None:
    try:
        rehydrate_risk_state_v2(
            request.to_dict(),
            domain=context.domain,
            state_reader=context.store,
        )
    except GovernanceAuthorityBindingErrorV2 as exc:
        if exc.code not in _TYPED_INTEGRITY_CODES:
            problems.append(f"{mutation}_rehydrate_diagnostic")
    else:
        problems.append(f"{mutation}_rehydrate_not_fail_closed")


def _forged_current_position(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: Callable[..., Any],
    request_factory: Callable[..., Any],
    advance_factory: Callable[..., Any],
    problems: list[str],
) -> None:
    context, store = fault_risk_context_v2(
        adapter, context_factory, "forged-current-position"
    )
    parent, parent_source = request_factory(
        context, advance_ref="advance:forged-position:parent"
    )
    if (
        advance_factory(context, parent, parent_source).disposition
        is not GovernanceCommitDispositionV2.COMMITTED
    ):
        problems.append("forged_position_parent_setup")
        return
    verified_parent = rehydrate_risk_state_v2(
        parent.to_dict(), domain=context.domain, state_reader=context.store
    )
    child, child_source = request_factory(
        context,
        advance_ref="advance:forged-position:child",
        risk_band=RiskBand.HIGH,
        parent=parent.snapshot,
        current_step=3,
    )
    if (
        advance_factory(context, child, child_source).disposition
        is not GovernanceCommitDispositionV2.COMMITTED
    ):
        problems.append("forged_position_child_setup")
        return

    store.view_mutator = lambda view: _forge_parent_current(view, parent.transition_id)
    if risk_state_is_current_v2(verified_parent):
        problems.append("forged_current_position_accepted")
    try:
        require_current_risk_state_v2(verified_parent)
    except GovernanceAuthorityBindingErrorV2 as exc:
        if exc.code not in _TYPED_INTEGRITY_CODES:
            problems.append("forged_current_position_diagnostic")
    else:
        problems.append("forged_current_position_not_typed")
    if risk_head_revision_v2(context, child) != 2:
        problems.append("forged_current_position_mutation")


def _forge_parent_current(
    view: GovernanceCommitViewV2,
    parent_transition_id: str,
) -> None:
    if view.transition_id != parent_transition_id:
        return
    position = view.position_observation
    if position is None:
        raise ValueError("Risk v2 position observation is absent")
    object.__setattr__(position, "position", GovernanceCommitPositionV2.CURRENT)


def _cross_domain_rehydration(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: Callable[..., Any],
    request_factory: Callable[..., Any],
    advance_factory: Callable[..., Any],
    problems: list[str],
) -> None:
    context = context_factory(adapter, "rehydrate-domain")
    request, source = request_factory(context, advance_ref="advance:rehydrate-domain")
    if (
        advance_factory(context, request, source).disposition
        is not GovernanceCommitDispositionV2.COMMITTED
    ):
        problems.append("cross_domain_setup")
        return
    foreign = context_factory(adapter, "rehydrate-foreign-domain")
    try:
        rehydrate_risk_state_v2(
            request.to_dict(),
            domain=foreign.domain,
            state_reader=context.store,
        )
    except GovernanceAuthorityBindingErrorV2 as exc:
        if exc.code is not AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH:
            problems.append("cross_domain_diagnostic")
    else:
        problems.append("cross_domain_rehydration")


__all__: list[str] = []
