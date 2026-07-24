"""Committed-state, read-set, and Trace verification for Commit Gate v2."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, TypedDict, cast

from pheroos.protocol.authority_v2 import GovernanceReadPreconditionV2

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceIssuerOperationV2,
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    _canonical_commit_view_v2,
    _portable_projection,
)
from pheroos.governance._authority_store_v2_contracts.foundation import _require_root
from pheroos.governance._commit_gate_v2.common import (
    COMMIT_PERMISSION_STATE_SCHEMA_V2,
    COMMIT_STOP_STATE_SCHEMA_V2,
)
from pheroos.governance._commit_gate_v2.contract_support import (
    _validate_successor_common,
)
from pheroos.governance._commit_gate_v2.events import _commit_gate_event_v2
from pheroos.governance._commit_gate_v2.permission_contracts import (
    CommitPermissionRequestV2,
    CommitPermissionSnapshotV2,
)
from pheroos.governance._commit_gate_v2.source_common import (
    _source_context_root_v2,
)
from pheroos.governance._commit_gate_v2.stop_contracts import (
    CommitStopRequestV2,
    CommitStopSnapshotV2,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
)


type GateKindV2 = Literal["stop", "permission"]
type GateRequestV2 = CommitStopRequestV2 | CommitPermissionRequestV2
type GateSnapshotV2 = CommitStopSnapshotV2 | CommitPermissionSnapshotV2

_STATE_FIELDS = frozenset(
    {
        "schema",
        "domain_root",
        "scope_ref",
        "stream_ref",
        "transition_id",
        "request_root",
        "request",
        "snapshot_root",
        "source_context_root",
        "session_binding",
    }
)
_SESSION_FIELDS = frozenset(
    {
        "domain_root",
        "scope_ref",
        "run_ref",
        "request_ref",
        "request_root",
        "operation",
        "observed_epoch",
        "grant_ref",
        "grant_root",
        "grant_binding_ref",
        "grant_expected_revision",
        "grant_expected_root",
        "lifecycle_expected_revision",
        "lifecycle_expected_root",
        "target_refs",
        "action_refs",
    }
)


class _SessionBindingV2(TypedDict):
    domain_root: str
    scope_ref: str
    run_ref: str
    request_ref: str
    request_root: str
    operation: str
    observed_epoch: int
    grant_ref: str
    grant_root: str
    grant_binding_ref: str
    grant_expected_revision: int
    grant_expected_root: str
    lifecycle_expected_revision: int
    lifecycle_expected_root: str
    target_refs: list[str]
    action_refs: list[str]


def _gate_state_records_v2(
    request: GateRequestV2,
    session_binding: Mapping[str, object],
    *,
    kind: GateKindV2,
    source_context_root: str,
) -> dict[str, object]:
    return {
        "schema": _state_schema(kind),
        "domain_root": request.domain_root,
        "scope_ref": request.scope_ref,
        "stream_ref": request.stream_ref,
        "transition_id": request.transition_id,
        "request_root": request.request_root,
        "request": request.to_dict(),
        "snapshot_root": request.snapshot.snapshot_root,
        "source_context_root": source_context_root,
        "session_binding": _portable_projection(session_binding),
    }


def _decode_state_records_v2(
    value: object,
    domain: AuthorityDomainV2,
    *,
    kind: GateKindV2,
) -> tuple[GateRequestV2, _SessionBindingV2, str]:
    projected = _portable_projection(value)
    if type(projected) is not dict:
        raise TypeError("commit gate state must be an exact object")
    state = cast(dict[str, object], projected)
    if set(state) != _STATE_FIELDS:
        raise ValueError("commit gate committed state fields are invalid")
    if (
        state["schema"] != _state_schema(kind)
        or state["domain_root"] != domain.domain_root
        or state["scope_ref"] != domain.scope_ref
    ):
        raise ValueError("commit gate committed state domain is mismatched")
    request = _request_from_dict(kind, state["request"])
    if (
        state["stream_ref"] != request.stream_ref
        or state["transition_id"] != request.transition_id
        or state["request_root"] != request.request_root
        or state["snapshot_root"] != request.snapshot.snapshot_root
        or request.domain_root != domain.domain_root
        or request.scope_ref != domain.scope_ref
    ):
        raise ValueError("commit gate committed state payload is mismatched")
    source_root = _require_root(
        state["source_context_root"], "commit gate source_context_root"
    )
    expected_source = _source_context_root_v2(
        kind=kind,
        request_root=request.request_root,
        evaluation_context_root=request.snapshot.evaluation_context_root,
        dependency_root=request.snapshot.dependencies.dependency_root,
    )
    if source_root != expected_source:
        raise ValueError("commit gate committed source_context_root is mismatched")
    binding = _validate_session_binding(state["session_binding"], request, kind=kind)
    return request, binding, source_root


def _validate_session_binding(
    value: object,
    request: GateRequestV2,
    *,
    kind: GateKindV2,
) -> _SessionBindingV2:
    projected = _portable_projection(value)
    if type(projected) is not dict or set(projected) != _SESSION_FIELDS:
        raise ValueError("commit gate session binding fields are invalid")
    binding = cast(_SessionBindingV2, projected)
    observed = (
        binding["domain_root"],
        binding["scope_ref"],
        binding["run_ref"],
        binding["request_ref"],
        binding["request_root"],
        binding["operation"],
        binding["observed_epoch"],
        binding["target_refs"],
        binding["action_refs"],
    )
    expected = (
        request.domain_root,
        request.scope_ref,
        request.run_ref,
        _request_ref(request),
        request.request_root,
        _operation(kind).value,
        request.observed_epoch,
        [request.target_ref],
        [] if kind == "stop" else ["commit"],
    )
    if observed != expected:
        raise ValueError("commit gate stored session binding is mismatched")
    for field in ("grant_ref", "grant_root", "grant_binding_ref"):
        if type(binding[field]) is not str or not binding[field]:
            raise ValueError("commit gate stored grant binding is invalid")
    GovernanceReadPreconditionV2(
        stream_ref=governance_issuer_grant_stream_ref_v2(
            request.scope_ref, binding["grant_ref"]
        ),
        expected_revision=binding["grant_expected_revision"],
        expected_root=binding["grant_expected_root"],
    )
    GovernanceReadPreconditionV2(
        stream_ref=GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        expected_revision=binding["lifecycle_expected_revision"],
        expected_root=binding["lifecycle_expected_root"],
    )
    return binding


def _decode_committed_gate_view_v2(
    view: GovernanceCommitViewV2,
    domain: AuthorityDomainV2,
    *,
    kind: GateKindV2,
    reader: GovernanceStateReaderV2 | None,
) -> tuple[GateRequestV2, _SessionBindingV2, str]:
    view = _canonical_commit_view_v2(view)
    if (
        view.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or view.committed_transition is None
        or view.position_observation is None
    ):
        raise ValueError("commit gate view is not committed")
    transition = view.committed_transition.batch.transition
    if transition is None:
        raise ValueError("commit gate committed batch has no transition")
    request, binding, source_root = _decode_state_records_v2(
        transition.state_records, domain, kind=kind
    )
    receipt = view.committed_transition.receipt
    if (
        receipt.revision != request.snapshot.revision
        or receipt.stream_ref != request.stream_ref
        or receipt.transition_id != request.transition_id
    ):
        raise ValueError("commit gate committed receipt is mismatched")
    _validate_committed_read_set_v2(view, request, binding, kind=kind)
    event = _commit_gate_event_v2(
        request,
        binding,
        operation=_operation(kind).value,
        source_context_root=source_root,
        parent_head_root=receipt.parent_root,
        read_set_root=view.committed_transition.batch.read_set.root(),
    )
    events = view.committed_transition.batch.trace_batch.events
    if len(events) != 1 or events[0] != event:
        raise ValueError("commit gate committed Trace lineage is mismatched")
    if reader is not None:
        _validate_gate_history_v2(reader, domain, request, kind=kind)
    return request, binding, source_root


def _validate_committed_read_set_v2(
    view: GovernanceCommitViewV2,
    request: GateRequestV2,
    binding: _SessionBindingV2,
    *,
    kind: GateKindV2,
) -> None:
    assert view.committed_transition is not None
    entries = view.committed_transition.batch.read_set.entries
    observed = {
        item.stream_ref: (item.expected_revision, item.expected_root)
        for item in entries
    }
    if len(observed) != len(entries):
        raise ValueError("commit gate read set contains duplicate streams")
    receipt = view.committed_transition.receipt
    expected = {
        request.stream_ref: (request.snapshot.parent_revision, receipt.parent_root),
        governance_issuer_grant_stream_ref_v2(
            request.scope_ref, binding["grant_ref"]
        ): (binding["grant_expected_revision"], binding["grant_expected_root"]),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2: (
            binding["lifecycle_expected_revision"],
            binding["lifecycle_expected_root"],
        ),
    }
    dependencies = request.snapshot.dependencies
    for name in ("replay", "risk", "verification", "membership", "support"):
        expected[getattr(dependencies, f"{name}_stream_ref")] = (
            getattr(dependencies, f"{name}_revision"),
            getattr(dependencies, f"{name}_head_root"),
        )
    if observed != expected:
        raise ValueError("commit gate authority read set is mismatched")


def _validate_gate_history_v2(
    reader: GovernanceStateReaderV2,
    domain: AuthorityDomainV2,
    request: GateRequestV2,
    *,
    kind: GateKindV2,
) -> None:
    child = request.snapshot
    seen = {request.transition_id}
    remaining = child.parent_revision
    while remaining:
        try:
            view = reader.load_commit_view_v2(
                request.scope_ref, request.stream_ref, child.parent_transition_id
            )
        except KeyError as exc:
            raise ValueError("commit gate historical parent is unavailable") from exc
        parent_request, _, _ = _decode_committed_gate_view_v2(
            view, domain, kind=kind, reader=None
        )
        parent = parent_request.snapshot
        _validate_successor_common(child, parent)
        if parent.transition_id in seen or parent.revision != remaining:
            raise ValueError("commit gate historical lineage is cyclic or gapped")
        seen.add(parent.transition_id)
        child = parent
        remaining -= 1


def _head_from_view_v2(
    view: GovernanceCommitViewV2, domain: AuthorityDomainV2
) -> GovernanceHeadV2:
    if view.committed_transition is None:
        raise ValueError("commit gate parent has no committed transition")
    receipt = view.committed_transition.receipt
    return GovernanceHeadV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        stream_ref=receipt.stream_ref,
        revision=receipt.revision,
        parent_root=receipt.parent_root,
        state_root=receipt.state_root,
        transition_id=receipt.transition_id,
        batch_root=receipt.batch_root,
        head_root=receipt.head_root,
    )


def _request_from_dict(kind: GateKindV2, value: object) -> GateRequestV2:
    if kind == "stop":
        return CommitStopRequestV2.from_dict(value)
    return CommitPermissionRequestV2.from_dict(value)


def _request_ref(request: GateRequestV2) -> str:
    if type(request) is CommitStopRequestV2:
        return request.resolution_ref
    return cast(CommitPermissionRequestV2, request).permission_ref


def _state_schema(kind: GateKindV2) -> str:
    return (
        COMMIT_STOP_STATE_SCHEMA_V2
        if kind == "stop"
        else COMMIT_PERMISSION_STATE_SCHEMA_V2
    )


def _operation(kind: GateKindV2) -> GovernanceIssuerOperationV2:
    return (
        GovernanceIssuerOperationV2.RESOLVE_STOP
        if kind == "stop"
        else GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION
    )


__all__: tuple[str, ...] = ()
