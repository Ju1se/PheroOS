"""Scoped, atomic publication for Hybrid Commit evaluation results.

The existing Hybrid Commit evaluator produces a deterministic governance
projection and its canonical Trace events.  This module supplies the durable
authority boundary around that projection:

``prepare -> StateStore.atomic_commit -> verify receipt -> finalize``.

An evaluation held by a prepared transition is a proposal until a receipt is
verified against the current store.  In particular, output references present
in that proposal do not become externally authorizing merely because the
in-process evaluator constructed them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any

from pheroos._digest import is_canonical_sha256_fingerprint
from pheroos.governance.authority_domain import (
    AuthorityDomain,
    GovernanceCommitBatch,
    GovernanceCommitReceipt,
    GovernanceHead,
    GovernanceStateStore,
    PreparedGovernanceTransition,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.hybrid_commit_evaluation import (
    HybridCommitEvaluation,
    hybrid_commit_evaluation_fingerprint,
    hybrid_commit_evaluation_is_authoritative,
    hybrid_commit_evaluation_payload,
)
from pheroos.governance.hybrid_commit import evaluate_hybrid_commit_step
from pheroos.trace import COMMIT_EVENT_TYPES, ScopedTraceEvent, TraceEvent


ATOMIC_HYBRID_COMMIT_VERSION = "pheroos-atomic-hybrid-commit-v1"
_ATOMIC_STATE_SCHEMA = "pheroos-atomic-hybrid-commit-state-v1"
_ATOMIC_RESULT_SCHEMA = "pheroos-atomic-hybrid-commit-result-v1"


class AtomicHybridCommitStatus(StrEnum):
    """Outcome of the outer durable-authority operation."""

    COMMITTED = "committed"
    RETRY_REQUIRED = "retry_required"
    FINALITY_UNAVAILABLE = "finality_unavailable"
    INVALID = "invalid"


@dataclass(frozen=True)
class PreparedHybridCommitTransition:
    """Immutable proposal bound to one exact scoped Governance head.

    The embedded evaluation is deliberately a private runtime convenience.  It
    carries no durable authority until :func:`finalize_hybrid_commit_transition`
    verifies a store-issued receipt.
    """

    version: str
    scope_ref: str
    stream: str
    transition_id: str
    request_ref: str
    evaluation_root: str
    terminal: bool
    batch: GovernanceCommitBatch
    prepared_root: str
    _evaluation: HybridCommitEvaluation = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.version != ATOMIC_HYBRID_COMMIT_VERSION:
            raise GovernanceError("atomic Hybrid Commit version is unsupported")
        if not isinstance(self.batch, GovernanceCommitBatch):
            raise GovernanceError("atomic Hybrid Commit batch is invalid")
        if not isinstance(self._evaluation, HybridCommitEvaluation):
            raise GovernanceError("atomic Hybrid Commit evaluation is invalid")
        transition = self.batch.transition
        exact = {
            "scope_ref": transition.domain.scope_ref,
            "stream": transition.stream,
            "transition_id": transition.transition_id,
            "request_ref": self._evaluation.request_ref,
            "evaluation_root": self._evaluation.evaluation_root,
            "terminal": self._evaluation.terminal,
        }
        for name, expected in exact.items():
            if getattr(self, name) != expected:
                raise GovernanceError(
                    f"atomic Hybrid Commit prepared {name} is mismatched"
                )
        expected_root = _root(
            "pheroos-prepared-atomic-hybrid-commit-v1",
            {
                "version": self.version,
                "scope_ref": self.scope_ref,
                "stream": self.stream,
                "transition_id": self.transition_id,
                "request_ref": self.request_ref,
                "evaluation_root": self.evaluation_root,
                "terminal": self.terminal,
                "batch_root": self.batch.batch_root,
            },
        )
        if self.prepared_root != expected_root:
            raise GovernanceError(
                "atomic Hybrid Commit prepared root does not match its payload"
            )

    @property
    def evaluation(self) -> HybridCommitEvaluation:
        """Return the unfinalized proposal for inspection only."""

        return self._evaluation

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "scope_ref": self.scope_ref,
            "stream": self.stream,
            "transition_id": self.transition_id,
            "request_ref": self.request_ref,
            "evaluation_root": self.evaluation_root,
            "terminal": self.terminal,
            "batch": self.batch.to_dict(),
            "prepared_root": self.prepared_root,
        }


@dataclass(frozen=True)
class AtomicHybridCommitResult:
    """Total outer result; only ``COMMITTED`` can expose decision authority."""

    version: str
    status: AtomicHybridCommitStatus
    scope_ref: str
    stream: str
    transition_id: str
    authoritative: bool
    terminal: bool
    decision_output_authorized: bool
    diagnostic_deliverable: bool
    retry_required: bool
    evaluation_root: str
    receipt_root: str
    reason_code: str
    details: Mapping[str, Any]
    result_root: str
    evaluation: HybridCommitEvaluation | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    receipt: GovernanceCommitReceipt | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if self.version != ATOMIC_HYBRID_COMMIT_VERSION:
            raise GovernanceError("atomic Hybrid Commit result version is unsupported")
        if type(self.status) is not AtomicHybridCommitStatus:
            raise GovernanceError("atomic Hybrid Commit result status is invalid")
        for name in (
            "authoritative",
            "terminal",
            "decision_output_authorized",
            "diagnostic_deliverable",
            "retry_required",
        ):
            if type(getattr(self, name)) is not bool:
                raise GovernanceError(
                    f"atomic Hybrid Commit result {name} must be boolean"
                )
        _require_text(self.stream, "atomic Hybrid Commit stream")
        _require_text(self.transition_id, "atomic Hybrid Commit transition id")
        _require_text(self.reason_code, "atomic Hybrid Commit reason code")
        _require_digest(self.scope_ref, "atomic Hybrid Commit scope_ref")
        _require_digest(self.evaluation_root, "atomic Hybrid Commit evaluation root")
        if self.receipt_root:
            _require_digest(self.receipt_root, "atomic Hybrid Commit receipt root")
        if not isinstance(self.details, Mapping):
            raise GovernanceError("atomic Hybrid Commit result details must be a mapping")
        frozen_details = _freeze_json(self.details, path="atomic_result.details")
        if not isinstance(frozen_details, Mapping):  # pragma: no cover
            raise GovernanceError("atomic Hybrid Commit result details must be a mapping")
        object.__setattr__(self, "details", frozen_details)

        if self.status is AtomicHybridCommitStatus.COMMITTED:
            if not self.authoritative or self.retry_required:
                raise GovernanceError("committed Hybrid result authority flags are invalid")
            if self.evaluation is None or self.receipt is None:
                raise GovernanceError("committed Hybrid result requires evaluation and receipt")
            if self.receipt.receipt_root != self.receipt_root:
                raise GovernanceError("committed Hybrid result receipt root is mismatched")
            if self.evaluation.evaluation_root != self.evaluation_root:
                raise GovernanceError("committed Hybrid result evaluation root is mismatched")
            if self.terminal != self.evaluation.terminal:
                raise GovernanceError("committed Hybrid result terminal flag is mismatched")
            expected_output = bool(
                self.evaluation.terminal
                and self.evaluation.deliver_authorization is not None
                and self.evaluation.deliver_authorization.authorized
            )
            if self.decision_output_authorized != expected_output:
                raise GovernanceError("committed Hybrid output authority is mismatched")
        else:
            if self.authoritative or self.decision_output_authorized:
                raise GovernanceError(
                    "uncommitted Hybrid result cannot carry decision authority"
                )
            if self.evaluation is not None or self.receipt is not None or self.receipt_root:
                raise GovernanceError(
                    "uncommitted Hybrid result cannot expose evaluation or receipt objects"
                )
        if self.status is AtomicHybridCommitStatus.RETRY_REQUIRED:
            if not self.retry_required or self.terminal or self.diagnostic_deliverable:
                raise GovernanceError("retry-required Hybrid result flags are invalid")
        elif self.retry_required:
            raise GovernanceError("non-retry Hybrid result cannot request retry")
        if self.status in {
            AtomicHybridCommitStatus.FINALITY_UNAVAILABLE,
            AtomicHybridCommitStatus.INVALID,
        } and (not self.terminal or not self.diagnostic_deliverable):
            raise GovernanceError("terminal Hybrid diagnostic must be deliverable")

        expected_root = _root(_ATOMIC_RESULT_SCHEMA, self._root_payload())
        if self.result_root != expected_root:
            raise GovernanceError("atomic Hybrid result root does not match its payload")

    def _root_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "status": self.status,
            "scope_ref": self.scope_ref,
            "stream": self.stream,
            "transition_id": self.transition_id,
            "authoritative": self.authoritative,
            "terminal": self.terminal,
            "decision_output_authorized": self.decision_output_authorized,
            "diagnostic_deliverable": self.diagnostic_deliverable,
            "retry_required": self.retry_required,
            "evaluation_root": self.evaluation_root,
            "receipt_root": self.receipt_root,
            "reason_code": self.reason_code,
            "details": _portable_json(self.details),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._root_payload(), "result_root": self.result_root}


def hybrid_commit_stream(evaluation: HybridCommitEvaluation) -> str:
    """Return the canonical ledger stream for one Hybrid Commit lineage."""

    if not isinstance(evaluation, HybridCommitEvaluation):
        raise GovernanceError("Hybrid Commit stream requires a canonical evaluation")
    return ":".join(
        (
            "hybrid-commit-v1",
            evaluation.protocol_id,
            evaluation.run_id,
            evaluation.target,
            str(evaluation.epoch),
        )
    )


def prepare_hybrid_commit_transition(
    evaluation: HybridCommitEvaluation,
    *,
    domain: AuthorityDomain,
    head: GovernanceHead,
    transition_id: str | None = None,
) -> PreparedHybridCommitTransition:
    """Purely prepare state and scoped Trace records against ``head``.

    No store is read or changed by this function.  The supplied evaluation must
    already pass its full self-verification, but remains only a proposal until
    a matching receipt is finalized.
    """

    if not hybrid_commit_evaluation_is_authoritative(evaluation):
        raise GovernanceError(
            "atomic Hybrid Commit preparation requires an authoritative proposal"
        )
    if not isinstance(domain, AuthorityDomain):
        raise GovernanceError("atomic Hybrid Commit authority domain is invalid")
    stream = hybrid_commit_stream(evaluation)
    if not isinstance(head, GovernanceHead):
        raise GovernanceError("atomic Hybrid Commit preparation requires a head")
    if head.scope_ref != domain.scope_ref or head.stream != stream:
        raise GovernanceError("atomic Hybrid Commit head crosses scope or stream")
    resolved_transition_id = transition_id or (
        "hybrid-evaluation-" + evaluation.request_ref.removeprefix("sha256:")
    )
    _require_text(resolved_transition_id, "atomic Hybrid Commit transition id")

    evaluation_payload = hybrid_commit_evaluation_payload(evaluation)
    evaluation_fingerprint = hybrid_commit_evaluation_fingerprint(evaluation)
    state_records = {
        "version": ATOMIC_HYBRID_COMMIT_VERSION,
        "schema": _ATOMIC_STATE_SCHEMA,
        "scope_ref": domain.scope_ref,
        "stream": stream,
        "transition_id": resolved_transition_id,
        "request_ref": evaluation.request_ref,
        "evaluation_root": evaluation.evaluation_root,
        "evaluation_fingerprint": evaluation_fingerprint,
        "terminal": evaluation.terminal,
        "evaluation": evaluation_payload,
    }
    identity_claims = {
        f"hybrid-request:{evaluation.request_ref}": {
            "request_ref": evaluation.request_ref,
            "evaluation_root": evaluation.evaluation_root,
            "evaluation_fingerprint": evaluation_fingerprint,
            "protocol_id": evaluation.protocol_id,
            "run_id": evaluation.run_id,
            "target": evaluation.target,
            "epoch": evaluation.epoch,
        }
    }
    transition = PreparedGovernanceTransition.from_head(
        head,
        transition_id=resolved_transition_id,
        state_records=state_records,
        identity_claims=identity_claims,
    )
    trace_records = tuple(
        _scoped_trace_record(
            event,
            scope_ref=domain.scope_ref,
            stream=stream,
            transition_id=resolved_transition_id,
        )
        for event in evaluation.trace_events
    )
    if not trace_records:
        raise GovernanceError("atomic Hybrid Commit requires authoritative trace records")
    batch = GovernanceCommitBatch(
        transition=transition,
        trace_records=trace_records,
    )
    prepared_root = _root(
        "pheroos-prepared-atomic-hybrid-commit-v1",
        {
            "version": ATOMIC_HYBRID_COMMIT_VERSION,
            "scope_ref": domain.scope_ref,
            "stream": stream,
            "transition_id": resolved_transition_id,
            "request_ref": evaluation.request_ref,
            "evaluation_root": evaluation.evaluation_root,
            "terminal": evaluation.terminal,
            "batch_root": batch.batch_root,
        },
    )
    return PreparedHybridCommitTransition(
        version=ATOMIC_HYBRID_COMMIT_VERSION,
        scope_ref=domain.scope_ref,
        stream=stream,
        transition_id=resolved_transition_id,
        request_ref=evaluation.request_ref,
        evaluation_root=evaluation.evaluation_root,
        terminal=evaluation.terminal,
        batch=batch,
        prepared_root=prepared_root,
        _evaluation=evaluation,
    )


def commit_prepared_hybrid_transition(
    prepared: PreparedHybridCommitTransition,
    *,
    state_store: GovernanceStateStore,
) -> AtomicHybridCommitResult:
    """Atomically commit and finalize a prepared Hybrid transition.

    Store availability and CAS conflicts are represented as total outer
    results.  They never return the proposal object or its output authorization.
    """

    if not isinstance(prepared, PreparedHybridCommitTransition):
        raise GovernanceError("atomic Hybrid Commit prepared transition is invalid")
    if not isinstance(state_store, GovernanceStateStore):
        raise GovernanceError("atomic Hybrid Commit StateStore is incompatible")
    try:
        receipt = state_store.atomic_commit(prepared.batch)
    except GovernanceError as exc:
        message = str(exc)
        if "governance_cas_conflict:retry_required" in message:
            return _failure_result(
                prepared,
                status=AtomicHybridCommitStatus.RETRY_REQUIRED,
                reason_code="governance_cas_conflict",
                details={"retry_required": True},
            )
        if any(
            code in message
            for code in (
                "governance_transition_conflict",
                "governance_identity_conflict",
                "governance_trace_conflict",
                "governance_domain_retired",
            )
        ):
            return _failure_result(
                prepared,
                status=AtomicHybridCommitStatus.INVALID,
                reason_code="governance_authority_conflict",
                details={"error_type": type(exc).__name__},
            )
        return _failure_result(
            prepared,
            status=AtomicHybridCommitStatus.FINALITY_UNAVAILABLE,
            reason_code="governance_state_store_unavailable",
            details={"error_type": type(exc).__name__},
        )
    except Exception as exc:
        return _failure_result(
            prepared,
            status=AtomicHybridCommitStatus.FINALITY_UNAVAILABLE,
            reason_code="governance_state_store_unavailable",
            details={"error_type": type(exc).__name__},
        )
    return finalize_hybrid_commit_transition(
        prepared,
        receipt=receipt,
        state_store=state_store,
    )


def finalize_hybrid_commit_transition(
    prepared: PreparedHybridCommitTransition,
    *,
    receipt: GovernanceCommitReceipt,
    state_store: GovernanceStateStore,
) -> AtomicHybridCommitResult:
    """Verify a receipt against the store before exposing output authority."""

    if not isinstance(prepared, PreparedHybridCommitTransition):
        raise GovernanceError("atomic Hybrid Commit prepared transition is invalid")
    if not isinstance(receipt, GovernanceCommitReceipt):
        return _failure_result(
            prepared,
            status=AtomicHybridCommitStatus.INVALID,
            reason_code="governance_receipt_invalid",
            details={"receipt_type": type(receipt).__name__},
        )
    if not isinstance(state_store, GovernanceStateStore):
        raise GovernanceError("atomic Hybrid Commit StateStore is incompatible")
    try:
        stored = state_store.load_receipt(prepared.scope_ref, prepared.transition_id)
        head = state_store.load_head(prepared.scope_ref, prepared.stream)
    except Exception as exc:
        return _failure_result(
            prepared,
            status=AtomicHybridCommitStatus.FINALITY_UNAVAILABLE,
            reason_code="governance_receipt_verification_unavailable",
            details={"error_type": type(exc).__name__},
        )
    receipt_matches = receipt.matches(prepared.batch)
    stored_matches = bool(
        stored is not None
        and stored.receipt_root == receipt.receipt_root
        and stored.to_dict() == receipt.to_dict()
    )
    head_matches = (
        head.scope_ref == receipt.scope_ref
        and head.stream == receipt.stream
        and head.transition_id == receipt.transition_id
        and head.revision == receipt.revision
        and head.parent_root == receipt.parent_root
        and head.state_root == receipt.state_root
    )
    if not receipt_matches or not stored_matches or not head_matches:
        return _failure_result(
            prepared,
            status=AtomicHybridCommitStatus.INVALID,
            reason_code="governance_receipt_mismatch",
            details={
                "receipt_matches_batch": receipt_matches,
                "receipt_matches_store": stored_matches,
                "receipt_matches_head": head_matches,
            },
        )
    evaluation = prepared.evaluation
    output_authorized = bool(
        evaluation.terminal
        and evaluation.deliver_authorization is not None
        and evaluation.deliver_authorization.authorized
    )
    return _result(
        prepared,
        status=AtomicHybridCommitStatus.COMMITTED,
        authoritative=True,
        terminal=evaluation.terminal,
        decision_output_authorized=output_authorized,
        diagnostic_deliverable=False,
        retry_required=False,
        receipt_root=receipt.receipt_root,
        reason_code="governance_transition_committed",
        details={
            "batch_root": prepared.batch.batch_root,
            "revision": receipt.revision,
            "state_root": receipt.state_root,
            "trace_root": receipt.trace_root,
        },
        evaluation=evaluation,
        receipt=receipt,
    )


def evaluate_and_commit_hybrid_step(
    request: object,
    *,
    domain: AuthorityDomain,
    state_store: GovernanceStateStore,
    transition_id: str | None = None,
) -> AtomicHybridCommitResult:
    """High-aggregation total entry for the explicit durable authority path."""

    if not isinstance(domain, AuthorityDomain):
        raise GovernanceError("atomic Hybrid Commit authority domain is invalid")
    if not isinstance(state_store, GovernanceStateStore):
        raise GovernanceError("atomic Hybrid Commit StateStore is incompatible")
    evaluation = evaluate_hybrid_commit_step(request=request)
    if not hybrid_commit_evaluation_is_authoritative(evaluation):
        request_ref = evaluation.request_ref
        evaluation_root = evaluation.evaluation_root
        stream = _diagnostic_stream(evaluation)
        resolved_transition_id = transition_id or (
            "invalid-hybrid-evaluation-" + request_ref.removeprefix("sha256:")
        )
        return _standalone_failure_result(
            scope_ref=domain.scope_ref,
            stream=stream,
            transition_id=resolved_transition_id,
            evaluation_root=evaluation_root,
            status=AtomicHybridCommitStatus.INVALID,
            reason_code="hybrid_evaluation_invalid",
            details={
                "diagnostic_codes": tuple(item.code for item in evaluation.diagnostics)
            },
        )
    stream = hybrid_commit_stream(evaluation)
    try:
        head = state_store.load_head(domain.scope_ref, stream)
    except Exception as exc:
        resolved_transition_id = transition_id or (
            "hybrid-evaluation-" + evaluation.request_ref.removeprefix("sha256:")
        )
        return _standalone_failure_result(
            scope_ref=domain.scope_ref,
            stream=stream,
            transition_id=resolved_transition_id,
            evaluation_root=evaluation.evaluation_root,
            status=AtomicHybridCommitStatus.FINALITY_UNAVAILABLE,
            reason_code="governance_state_store_unavailable",
            details={"error_type": type(exc).__name__},
        )
    prepared = prepare_hybrid_commit_transition(
        evaluation,
        domain=domain,
        head=head,
        transition_id=transition_id,
    )
    return commit_prepared_hybrid_transition(prepared, state_store=state_store)


def _scoped_trace_record(
    event: TraceEvent,
    *,
    scope_ref: str,
    stream: str,
    transition_id: str,
) -> Mapping[str, Any]:
    if not isinstance(event, TraceEvent):
        raise GovernanceError("atomic Hybrid Commit trace event is invalid")
    trace_id = (
        event.lineage.get("event_id")
        if event.event_type in COMMIT_EVENT_TYPES
        else event.lineage.get("trace_event_id")
    )
    _require_text(trace_id, "atomic Hybrid Commit trace id")
    return ScopedTraceEvent(
        scope_ref=scope_ref,
        stream=stream,
        transition_id=transition_id,
        trace_id=trace_id,
        event=event,
    ).to_dict()


def _failure_result(
    prepared: PreparedHybridCommitTransition,
    *,
    status: AtomicHybridCommitStatus,
    reason_code: str,
    details: Mapping[str, Any],
) -> AtomicHybridCommitResult:
    return _standalone_failure_result(
        scope_ref=prepared.scope_ref,
        stream=prepared.stream,
        transition_id=prepared.transition_id,
        evaluation_root=prepared.evaluation_root,
        status=status,
        reason_code=reason_code,
        details=details,
    )


def _standalone_failure_result(
    *,
    scope_ref: str,
    stream: str,
    transition_id: str,
    evaluation_root: str,
    status: AtomicHybridCommitStatus,
    reason_code: str,
    details: Mapping[str, Any],
) -> AtomicHybridCommitResult:
    return _result_from_fields(
        status=status,
        scope_ref=scope_ref,
        stream=stream,
        transition_id=transition_id,
        authoritative=False,
        terminal=status is not AtomicHybridCommitStatus.RETRY_REQUIRED,
        decision_output_authorized=False,
        diagnostic_deliverable=status is not AtomicHybridCommitStatus.RETRY_REQUIRED,
        retry_required=status is AtomicHybridCommitStatus.RETRY_REQUIRED,
        evaluation_root=evaluation_root,
        receipt_root="",
        reason_code=reason_code,
        details=details,
        evaluation=None,
        receipt=None,
    )


def _result(
    prepared: PreparedHybridCommitTransition,
    *,
    status: AtomicHybridCommitStatus,
    authoritative: bool,
    terminal: bool,
    decision_output_authorized: bool,
    diagnostic_deliverable: bool,
    retry_required: bool,
    receipt_root: str,
    reason_code: str,
    details: Mapping[str, Any],
    evaluation: HybridCommitEvaluation | None,
    receipt: GovernanceCommitReceipt | None,
) -> AtomicHybridCommitResult:
    return _result_from_fields(
        status=status,
        scope_ref=prepared.scope_ref,
        stream=prepared.stream,
        transition_id=prepared.transition_id,
        authoritative=authoritative,
        terminal=terminal,
        decision_output_authorized=decision_output_authorized,
        diagnostic_deliverable=diagnostic_deliverable,
        retry_required=retry_required,
        evaluation_root=prepared.evaluation_root,
        receipt_root=receipt_root,
        reason_code=reason_code,
        details=details,
        evaluation=evaluation,
        receipt=receipt,
    )


def _result_from_fields(
    *,
    status: AtomicHybridCommitStatus,
    scope_ref: str,
    stream: str,
    transition_id: str,
    authoritative: bool,
    terminal: bool,
    decision_output_authorized: bool,
    diagnostic_deliverable: bool,
    retry_required: bool,
    evaluation_root: str,
    receipt_root: str,
    reason_code: str,
    details: Mapping[str, Any],
    evaluation: HybridCommitEvaluation | None,
    receipt: GovernanceCommitReceipt | None,
) -> AtomicHybridCommitResult:
    root_payload = {
        "version": ATOMIC_HYBRID_COMMIT_VERSION,
        "status": status,
        "scope_ref": scope_ref,
        "stream": stream,
        "transition_id": transition_id,
        "authoritative": authoritative,
        "terminal": terminal,
        "decision_output_authorized": decision_output_authorized,
        "diagnostic_deliverable": diagnostic_deliverable,
        "retry_required": retry_required,
        "evaluation_root": evaluation_root,
        "receipt_root": receipt_root,
        "reason_code": reason_code,
        "details": _portable_json(details),
    }
    return AtomicHybridCommitResult(
        **root_payload,
        result_root=_root(_ATOMIC_RESULT_SCHEMA, root_payload),
        evaluation=evaluation,
        receipt=receipt,
    )


def _diagnostic_stream(evaluation: HybridCommitEvaluation) -> str:
    parts = (
        evaluation.protocol_id or "unknown-protocol",
        evaluation.run_id or "unknown-run",
        evaluation.target or "unknown-target",
        str(evaluation.epoch),
    )
    return "hybrid-commit-v1:" + ":".join(parts)


def _root(schema: str, payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        {"schema": schema, "payload": _portable_json(payload)},
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


def _portable_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _portable_json(value[key]) for key in sorted(value)}
    if isinstance(value, (tuple, list)):
        return [_portable_json(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise GovernanceError(
        "atomic Hybrid Commit payload contains an unsupported value type"
    )


def _freeze_json(value: Any, *, path: str) -> Any:
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) and key for key in value):
            raise GovernanceError(f"{path} keys must be non-empty strings")
        return MappingProxyType(
            {key: _freeze_json(value[key], path=f"{path}.{key}") for key in sorted(value)}
        )
    if isinstance(value, (tuple, list)):
        return tuple(
            _freeze_json(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise GovernanceError(f"{path} contains an unsupported value type")


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise GovernanceError(f"{field_name} must be canonical non-blank text")
    return value


def _require_digest(value: object, field_name: str) -> str:
    if not is_canonical_sha256_fingerprint(value):
        raise GovernanceError(f"{field_name} must be a canonical SHA-256 digest")
    return value


__all__ = [
    "ATOMIC_HYBRID_COMMIT_VERSION",
    "AtomicHybridCommitResult",
    "AtomicHybridCommitStatus",
    "PreparedHybridCommitTransition",
    "commit_prepared_hybrid_transition",
    "evaluate_and_commit_hybrid_step",
    "finalize_hybrid_commit_transition",
    "hybrid_commit_stream",
    "prepare_hybrid_commit_transition",
]
