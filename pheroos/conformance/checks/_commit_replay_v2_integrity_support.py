"""Public historical-integrity and authority-substitution checks."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
import pickle
from typing import Any

from pheroos.conformance.checks._commit_replay_v2_store_support import (
    commit_replay_head_revision_v2,
    fault_commit_replay_context_v2,
    is_commit_replay_failure_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.commit_state_v2 import (
    CommitReplayAdvanceRequestV2,
    CommitReplayReceiptV2,
    VerifiedCommitReplaySourceV2,
    advance_commit_replay_state_v2,
    open_commit_replay_authority_session_v2,
    rehydrate_commit_replay_state_v2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceTraceBatchV2,
)
from pheroos.protocol.authority_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceAuthorityReadSetV2,
    GovernanceReadPreconditionV2,
)
from pheroos.trace import TraceEvent


_ContextFactory = Callable[..., Any]
_ReceiptFactory = Callable[..., CommitReplayReceiptV2]
_RequestFactory = Callable[
    ...,
    tuple[CommitReplayAdvanceRequestV2, VerifiedCommitReplaySourceV2],
]
_AdvanceFactory = Callable[
    [Any, CommitReplayAdvanceRequestV2, object], GovernanceCommitAttemptV2
]


@dataclass(frozen=True, slots=True)
class _SameShapeSource:
    context_root: str


@dataclass(frozen=True, slots=True)
class _LegacyReceiptShape:
    """Old receipt-shaped data without importing the process-local v1 owner."""

    namespace: object
    record_id: str
    nonce: str
    payload_fingerprint: str
    target: str
    candidate_id: str
    epoch: int | None
    principal_id: str


def run_public_commit_replay_integrity_matrix_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    *,
    context_factory: _ContextFactory,
    receipt_factory: _ReceiptFactory,
    request_factory: _RequestFactory,
    advance_factory: _AdvanceFactory,
) -> tuple[str, ...]:
    problems: list[str] = []
    _evaluate_historical_integrity(
        adapter,
        context_factory,
        receipt_factory,
        request_factory,
        advance_factory,
        problems,
    )
    _evaluate_context_and_portability(
        adapter,
        context_factory,
        receipt_factory,
        request_factory,
        problems,
    )
    return tuple(problems)


def _evaluate_historical_integrity(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: _ContextFactory,
    receipt_factory: _ReceiptFactory,
    request_factory: _RequestFactory,
    advance_factory: _AdvanceFactory,
    problems: list[str],
) -> None:
    context, store = fault_commit_replay_context_v2(
        adapter, context_factory, "public-historical-integrity"
    )
    request, source = request_factory(
        context,
        advance_ref="advance:public-historical-integrity",
        receipt=receipt_factory(201, suffix=":integrity"),
        current_step=1,
    )
    if (
        advance_factory(context, request, source).disposition
        is not GovernanceCommitDispositionV2.COMMITTED
    ):
        problems.append("historical_integrity_setup")
        return

    variants = (
        *(
            (stream_kind, mutation)
            for stream_kind in ("state", "grant", "lifecycle")
            for mutation in ("missing", "revision", "root")
        ),
        ("set", "extra"),
        ("set", "duplicate"),
        ("set", "reorder"),
    )
    for stream_kind, mutation in variants:
        label = f"read_set_{stream_kind}_{mutation}"
        store.view_mutator = _read_set_mutator(
            request.transition_id,
            request,
            stream_kind,
            mutation,
        )
        _expect_invalid_rehydration(context, request, label, problems)

    store.view_mutator = _trace_read_set_root_mutator(request.transition_id)
    _expect_invalid_rehydration(
        context,
        request,
        "trace_read_set_root_tamper",
        problems,
    )

    store.view_mutator = None
    donor, donor_source = request_factory(
        context,
        advance_ref="advance:public-historical-donor",
        receipt=receipt_factory(202, suffix=":donor"),
        current_step=2,
        parent=request.snapshot,
    )
    if (
        advance_factory(context, donor, donor_source).disposition
        is not GovernanceCommitDispositionV2.COMMITTED
    ):
        problems.append("historical_donor_setup")
        return
    donor_view = context.store.load_commit_view_v2(
        donor.scope_ref,
        donor.stream_ref,
        donor.transition_id,
    )
    if donor_view.committed_transition is None:
        problems.append("historical_donor_view")
        return
    for mutation in (
        "state_substitute",
        "state_delete",
        "request_substitute",
        "request_delete",
        "receipt_substitute",
        "receipt_delete",
        "trace_substitute",
        "trace_delete",
        "inclusion_delete",
        "batch_delete",
        "position_delete",
        "position_forge_current",
    ):
        store.view_mutator = _artifact_mutator(
            request.transition_id,
            donor_view.committed_transition,
            mutation,
        )
        _expect_invalid_rehydration(context, request, mutation, problems)
        _expect_invalid_reconciliation(context, request, mutation, problems)
    store.view_mutator = None
    if store.atomic_commits != 2 or commit_replay_head_revision_v2(context, donor) != 2:
        problems.append("historical_tamper_zero_write")


def _read_set_mutator(
    transition_id: str,
    request: CommitReplayAdvanceRequestV2,
    stream_kind: str,
    mutation: str,
) -> Callable[[GovernanceCommitViewV2], None]:
    def mutate(view: GovernanceCommitViewV2) -> None:
        if view.transition_id != transition_id or view.committed_transition is None:
            return
        read_set = view.committed_transition.batch.read_set
        entries = list(read_set.entries)
        if mutation == "extra":
            entries.append(
                GovernanceReadPreconditionV2(
                    stream_ref="authority:commit-replay-v2:unexpected",
                    expected_revision=0,
                    expected_root="sha256:" + "a" * 64,
                )
            )
            _replace_read_set(view, entries)
            return
        if mutation == "duplicate":
            object.__setattr__(read_set, "entries", (*read_set.entries, entries[0]))
            return
        if mutation == "reorder":
            object.__setattr__(read_set, "entries", tuple(reversed(read_set.entries)))
            return
        selected_index = next(
            index
            for index, item in enumerate(entries)
            if (stream_kind == "state" and item.stream_ref == request.stream_ref)
            or (
                stream_kind == "lifecycle"
                and item.stream_ref == GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
            )
            or (
                stream_kind == "grant"
                and item.stream_ref
                not in {
                    request.stream_ref,
                    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
                }
            )
        )
        selected = entries[selected_index]
        if mutation == "missing":
            del entries[selected_index]
        elif mutation == "revision":
            entries[selected_index] = replace(
                selected,
                expected_revision=selected.expected_revision + 1,
            )
        elif mutation == "root":
            entries[selected_index] = replace(
                selected,
                expected_root="sha256:" + "b" * 64,
            )
        else:
            raise ValueError("unknown Commit Replay read-set mutation")
        _replace_read_set(view, entries)

    return mutate


def _replace_read_set(
    view: GovernanceCommitViewV2,
    entries: Sequence[GovernanceReadPreconditionV2],
) -> None:
    assert view.committed_transition is not None
    ordered = tuple(sorted(entries, key=lambda item: item.stream_ref.encode("utf-8")))
    object.__setattr__(
        view.committed_transition.batch,
        "read_set",
        GovernanceAuthorityReadSetV2(entries=ordered),
    )


def _trace_read_set_root_mutator(
    transition_id: str,
) -> Callable[[GovernanceCommitViewV2], None]:
    def mutate(view: GovernanceCommitViewV2) -> None:
        if view.transition_id != transition_id or view.committed_transition is None:
            return
        batch = view.committed_transition.batch
        event = batch.trace_batch.events[0]
        lineage = dict(event.lineage)
        lineage["read_set_root"] = "sha256:" + "c" * 64
        substituted = TraceEvent(
            event_type=event.event_type,
            protocol_id=event.protocol_id,
            target=event.target,
            reason=event.reason,
            lineage=lineage,
        )
        object.__setattr__(
            batch,
            "trace_batch",
            GovernanceTraceBatchV2(
                domain_root=batch.trace_batch.domain_root,
                scope_ref=batch.trace_batch.scope_ref,
                stream_ref=batch.trace_batch.stream_ref,
                transition_id=batch.trace_batch.transition_id,
                events=(substituted,),
            ),
        )

    return mutate


def _artifact_mutator(
    transition_id: str,
    donor: Any,
    mutation: str,
) -> Callable[[GovernanceCommitViewV2], None]:
    def mutate(view: GovernanceCommitViewV2) -> None:
        if view.transition_id != transition_id or view.committed_transition is None:
            return
        committed = view.committed_transition
        transition = committed.batch.transition
        donor_transition = donor.batch.transition
        assert transition is not None and donor_transition is not None
        if mutation.startswith(("state_", "request_")):
            _mutate_state_artifact(transition, donor_transition, mutation)
        else:
            _mutate_commit_artifact(view, donor, mutation)

    return mutate


def _mutate_state_artifact(transition: Any, donor: Any, mutation: str) -> None:
    if mutation == "state_substitute":
        object.__setattr__(transition, "state_records", donor.state_records)
        return
    records = dict(transition.state_records)
    if mutation == "state_delete":
        records.pop("snapshot")
    elif mutation == "request_substitute":
        records["request"] = donor.state_records["request"]
    elif mutation == "request_delete":
        records.pop("request")
    else:
        raise ValueError("unknown Commit Replay State mutation")
    object.__setattr__(transition, "state_records", records)


def _mutate_commit_artifact(
    view: GovernanceCommitViewV2,
    donor: Any,
    mutation: str,
) -> None:
    assert view.committed_transition is not None
    committed = view.committed_transition
    if mutation == "receipt_substitute":
        object.__setattr__(committed, "receipt", donor.receipt)
    elif mutation == "receipt_delete":
        object.__setattr__(committed, "receipt", None)
    elif mutation == "trace_substitute":
        object.__setattr__(committed.batch, "trace_batch", donor.batch.trace_batch)
    elif mutation == "trace_delete":
        object.__setattr__(committed.batch, "trace_batch", None)
    elif mutation == "inclusion_delete":
        object.__setattr__(committed, "inclusion_proof", None)
    elif mutation == "batch_delete":
        object.__setattr__(committed, "batch", None)
    elif mutation == "position_delete":
        object.__setattr__(view, "position_observation", None)
    elif mutation == "position_forge_current":
        assert view.position_observation is not None
        object.__setattr__(
            view.position_observation,
            "position",
            GovernanceCommitPositionV2.CURRENT,
        )
    else:
        raise ValueError("unknown Commit Replay commit mutation")


def _expect_invalid_rehydration(
    context: Any,
    request: CommitReplayAdvanceRequestV2,
    label: str,
    problems: list[str],
) -> None:
    try:
        rehydrate_commit_replay_state_v2(
            request.to_dict(),
            domain=context.domain,
            state_reader=context.store,
        )
    except GovernanceAuthorityBindingErrorV2 as exc:
        if exc.code is not (
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
        ):
            problems.append(label)
    except Exception:
        problems.append(label)
    else:
        problems.append(label)


def _expect_invalid_reconciliation(
    context: Any,
    request: CommitReplayAdvanceRequestV2,
    label: str,
    problems: list[str],
) -> None:
    try:
        session = open_commit_replay_authority_session_v2(
            context.capability,
            request,
        )
        attempt = advance_commit_replay_state_v2(
            request,
            source=None,
            authority_session=session,
        )
    except Exception:
        problems.append(f"{label}_reconciliation_exception")
        return
    if not is_commit_replay_failure_v2(
        attempt,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
    ):
        problems.append(f"{label}_reconciliation")


def _evaluate_context_and_portability(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    context_factory: _ContextFactory,
    receipt_factory: _ReceiptFactory,
    request_factory: _RequestFactory,
    problems: list[str],
) -> None:
    context, store = fault_commit_replay_context_v2(
        adapter, context_factory, "public-authority-a"
    )
    other_context, other_store = fault_commit_replay_context_v2(
        adapter, context_factory, "public-authority-b"
    )
    receipt = receipt_factory(301, suffix=":authority")
    request, source = request_factory(
        context,
        advance_ref="advance:public-authority",
        receipt=receipt,
        current_step=1,
    )
    other_request, other_source = request_factory(
        other_context,
        advance_ref="advance:public-authority",
        receipt=receipt_factory(301, suffix=":authority"),
        current_step=1,
    )
    alternate, alternate_source = request_factory(
        context,
        advance_ref="advance:public-authority:alternate",
        receipt=receipt_factory(302, suffix=":alternate"),
        current_step=1,
    )
    session = open_commit_replay_authority_session_v2(context.capability, request)
    alternate_session = open_commit_replay_authority_session_v2(
        context.capability, alternate
    )
    other_session = open_commit_replay_authority_session_v2(
        other_context.capability, other_request
    )
    _check_portable_source_rejections(request, source, session, receipt, problems)
    _check_cross_authority_rejections(
        request,
        source,
        session,
        alternate_source,
        alternate_session,
        other_source,
        other_session,
        problems,
    )
    if (
        store.atomic_commits != 0
        or other_store.atomic_commits != 0
        or commit_replay_head_revision_v2(context, request) != 0
        or commit_replay_head_revision_v2(other_context, other_request) != 0
    ):
        problems.append("authority_rejection_zero_write")

    accepted = advance_commit_replay_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    if accepted.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        problems.append("authority_valid_setup")
        return
    verified = rehydrate_commit_replay_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    _expect_pickle_rejection(verified, "state_pickle_portable", problems)


def _check_portable_source_rejections(
    request: CommitReplayAdvanceRequestV2,
    source: VerifiedCommitReplaySourceV2,
    session: Any,
    receipt: CommitReplayReceiptV2,
    problems: list[str],
) -> None:
    v1_receipt = _LegacyReceiptShape(
        namespace=receipt.namespace,
        record_id=receipt.record_id,
        nonce=receipt.nonce,
        payload_fingerprint=receipt.payload_fingerprint,
        target=receipt.target_ref,
        candidate_id=receipt.candidate_ref,
        epoch=receipt.epoch,
        principal_id=receipt.principal_ref,
    )
    raw_sources = (
        request,
        request.snapshot,
        request.to_dict(),
        request.request_root,
        pickle.dumps(request.to_dict()),
        v1_receipt,
        _SameShapeSource(source.context_root),
    )
    for raw_index, candidate in enumerate(raw_sources):
        attempt = advance_commit_replay_state_v2(
            request,
            source=candidate,
            authority_session=session,
        )
        if not is_commit_replay_failure_v2(
            attempt,
            GovernanceCommitDispositionV2.INVALID,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        ):
            problems.append(f"portable_source_{raw_index}")
    _expect_pickle_rejection(source, "source_pickle_portable", problems)


def _check_cross_authority_rejections(
    request: CommitReplayAdvanceRequestV2,
    source: VerifiedCommitReplaySourceV2,
    session: Any,
    alternate_source: VerifiedCommitReplaySourceV2,
    alternate_session: Any,
    other_source: VerifiedCommitReplaySourceV2,
    other_session: Any,
    problems: list[str],
) -> None:
    for case_label, candidate_source, candidate_session in (
        ("same_context_source", alternate_source, session),
        ("cross_context_source", other_source, session),
        ("same_context_session", source, alternate_session),
        ("cross_context_session", source, other_session),
    ):
        attempt = advance_commit_replay_state_v2(
            request,
            source=candidate_source,
            authority_session=candidate_session,
        )
        if attempt.disposition is not GovernanceCommitDispositionV2.INVALID:
            problems.append(case_label)


def _expect_pickle_rejection(
    value: object,
    label: str,
    problems: list[str],
) -> None:
    try:
        pickle.dumps(value)
    except TypeError:
        pass
    else:
        problems.append(label)


__all__: list[str] = []
