"""Independent stdlib model for the StateStore v2 conformance contract.

This model intentionally imports only public authority v2 Protocol,
Governance, and Trace contracts.  It is not the Governance reference store
and shares no private ledger, snapshot, or root implementation with it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from hashlib import sha256
import json
from threading import RLock
from typing import Any, cast

import pheroos.governance.authority_store_v2 as governance_v2
import pheroos.protocol.authority_v2 as protocol_v2
from pheroos.trace import TraceEvent


_CONFORMANCE_VERSION = "pheroos-governance-state-store-conformance-v2"
_ATOMIC_FAILURE_STAGES = frozenset(
    {
        "before_validation",
        "after_identity_reconciliation",
        "after_read_set_validation",
        "after_state_head_staging",
        "after_trace_staging",
        "after_receipt_inclusion_staging",
        "after_atomic_publication",
    }
)
_VIEW_FAILURE_STAGE = "load_commit_view"
_TAMPER_CASES = (
    "batch_payload",
    "batch_root",
    "receipt_payload",
    "receipt_root",
    "inclusion_payload",
    "inclusion_root",
    "head_payload",
    "head_root",
    "state_payload",
    "state_root",
    "trace_payload",
    "trace_root",
    "scope_binding",
    "stream_binding",
    "revision_binding",
    "seal_payload",
    "seal_root",
    "lifecycle_state",
    "transition_index",
    "seal_marker",
    "projection_removal",
    "sequence_binding",
    "cross_stream_order",
    "history_payload",
)
_INJECTED_FAILURE_STAGES = {
    "before_validation": governance_v2.GovernanceFailureStageV2.VALIDATION,
    "after_identity_reconciliation": (
        governance_v2.GovernanceFailureStageV2.RECONCILIATION
    ),
    "after_read_set_validation": governance_v2.GovernanceFailureStageV2.PRECONDITION,
    "after_state_head_staging": governance_v2.GovernanceFailureStageV2.COMMIT,
    "after_trace_staging": governance_v2.GovernanceFailureStageV2.TRACE,
    "after_receipt_inclusion_staging": governance_v2.GovernanceFailureStageV2.COMMIT,
    "after_atomic_publication": governance_v2.GovernanceFailureStageV2.FINALITY,
}


class _IndependentTraceLineageInvalid(ValueError):
    """Typed private marker for a corrupted persisted Trace category."""


class IndependentStdlibGovernanceStateStoreV2:
    """Small copy-on-write model independent from the reference owner."""

    def __init__(
        self,
        domains: Sequence[governance_v2.AuthorityDomainV2] = (),
        *,
        failure_stage: str | None = None,
    ) -> None:
        if failure_stage is not None and failure_stage not in (
            _ATOMIC_FAILURE_STAGES | {_VIEW_FAILURE_STAGE}
        ):
            raise ValueError("unsupported StateStore v2 failure stage")
        self._failure_stage = failure_stage
        self._lock = RLock()
        self._domains: dict[str, governance_v2.AuthorityDomainV2] = {}
        self._heads: dict[tuple[str, str], governance_v2.GovernanceHeadV2] = {}
        self._states: dict[tuple[str, str], dict[str, Any]] = {}
        self._committed: dict[
            tuple[str, str], governance_v2.GovernanceCommittedTransitionV2
        ] = {}
        self._history: dict[
            tuple[str, str, int], governance_v2.GovernanceCommittedTransitionV2
        ] = {}
        self._trace_batches: dict[
            tuple[str, str], governance_v2.GovernanceTraceBatchV2
        ] = {}
        self._seals: dict[str, governance_v2.GovernanceDomainSealV2] = {}
        self._commit_order: dict[str, list[str]] = {}
        self._transition_index: dict[tuple[str, str], int] = {}
        self._validated_image_fingerprints: dict[str, str] = {}
        for domain in domains:
            detached = _clone_domain(domain)
            if detached.scope_ref in self._domains:
                raise ValueError("authority scope is duplicated")
            self._domains[detached.scope_ref] = detached

    @property
    def state_store_version(self) -> str:
        return governance_v2.GOVERNANCE_STATE_STORE_VERSION_V2

    def load_head_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> governance_v2.GovernanceHeadV2:
        with self._lock:
            return _clone_head(self._head(scope_ref, stream_ref))

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        with self._lock:
            self._domain(scope_ref)
            return deepcopy(self._states.get((scope_ref, stream_ref), {}))

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> governance_v2.GovernanceCommitViewV2:
        with self._lock:
            domain = self._domain(scope_ref)
            if self._failure_stage == _VIEW_FAILURE_STAGE:
                return self._view_failure(
                    domain,
                    stream_ref,
                    transition_id,
                    expected_receipt_root,
                    protocol_v2.AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
                    governance_v2.GovernanceFailureStageV2.LOAD,
                    reliable_snapshot=False,
                )
            key = (scope_ref, transition_id)
            try:
                selected = self._committed.get(key)
                if selected is None or selected.batch.stream_ref != stream_ref:
                    raise ValueError("selected transition is absent or cross-stream")
                _validate_or_reuse_store_image(self, scope_ref, transition_id)
                committed = governance_v2.GovernanceCommittedTransitionV2.from_dict(
                    selected.to_dict()
                )
                receipt = committed.receipt
                if expected_receipt_root is not None and (
                    expected_receipt_root != receipt.receipt_root
                ):
                    raise ValueError("receipt selection mismatch")
                history_key = (scope_ref, stream_ref, receipt.revision)
                included = self._history.get(history_key)
                trace = self._trace_batches.get(key)
                if (
                    included is None
                    or included.inclusion_proof.inclusion_root
                    != committed.inclusion_proof.inclusion_root
                    or trace is None
                    or trace.trace_root != committed.batch.trace_root
                ):
                    raise ValueError("selected store inclusion mismatch")
                position = self._position(committed)
            except _IndependentTraceLineageInvalid:
                return self._view_failure(
                    domain,
                    stream_ref,
                    transition_id,
                    expected_receipt_root,
                    protocol_v2.AuthorityDiagnosticCodeV2.GOVERNANCE_TRACE_LINEAGE_INVALID,
                    governance_v2.GovernanceFailureStageV2.LOAD,
                    path="/committed_transition/batch/trace_batch",
                )
            except (AttributeError, TypeError, ValueError, KeyError, IndexError):
                return self._view_failure(
                    domain,
                    stream_ref,
                    transition_id,
                    expected_receipt_root,
                    protocol_v2.AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
                    governance_v2.GovernanceFailureStageV2.LOAD,
                )
            return governance_v2.GovernanceCommitViewV2(
                domain_root=domain.domain_root,
                scope_ref=scope_ref,
                stream_ref=stream_ref,
                transition_id=transition_id,
                expected_receipt_root=expected_receipt_root,
                disposition=governance_v2.GovernanceCommitDispositionV2.COMMITTED,
                failure=None,
                committed_transition=committed,
                position_observation=position,
                observed_revision=position.observed_revision,
                observed_head_root=position.observed_head_root,
            )

    def atomic_commit_v2(
        self,
        batch: governance_v2.GovernanceCommitBatchV2,
    ) -> governance_v2.GovernanceCommitAttemptV2:
        if type(batch) is not governance_v2.GovernanceCommitBatchV2:
            raise TypeError("atomic_commit_v2 requires GovernanceCommitBatchV2")
        with self._lock:
            prepared = self._validate_and_reconcile(batch)
            if type(prepared) is governance_v2.GovernanceCommitAttemptV2:
                return prepared
            selected = cast(governance_v2.GovernanceCommitBatchV2, prepared)
            structural_failure = self._validate_store_preconditions(selected)
            if structural_failure is not None:
                return structural_failure
            if any(
                type(event) is not TraceEvent for event in selected.trace_batch.events
            ):
                return self._failure_attempt(
                    selected,
                    protocol_v2.AuthorityDiagnosticCodeV2.GOVERNANCE_TRACE_LINEAGE_INVALID,
                    "/trace_batch/events",
                    governance_v2.GovernanceFailureStageV2.TRACE,
                )
            if self._failure_stage == "after_read_set_validation":
                return self._unavailable_attempt(
                    selected,
                    governance_v2.GovernanceFailureStageV2.PRECONDITION,
                )
            return self._stage_and_publish(selected)

    def _validate_and_reconcile(
        self,
        batch: governance_v2.GovernanceCommitBatchV2,
    ) -> (
        governance_v2.GovernanceCommitBatchV2 | governance_v2.GovernanceCommitAttemptV2
    ):
        if self._failure_stage == "before_validation":
            return self._unavailable_attempt(
                batch,
                governance_v2.GovernanceFailureStageV2.VALIDATION,
            )
        try:
            selected = governance_v2.GovernanceCommitBatchV2.from_dict(batch.to_dict())
        except (TypeError, ValueError):
            return self._failure_attempt(
                batch,
                protocol_v2.AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
                "",
                governance_v2.GovernanceFailureStageV2.VALIDATION,
            )
        registered = self._domains.get(selected.scope_ref)
        if registered is None:
            return self._failure_attempt(
                selected,
                protocol_v2.AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
                "/scope_ref",
                governance_v2.GovernanceFailureStageV2.VALIDATION,
            )
        if selected.domain.to_dict() != registered.to_dict():
            return self._failure_attempt(
                selected,
                protocol_v2.AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/domain_root",
                governance_v2.GovernanceFailureStageV2.VALIDATION,
            )
        try:
            _validate_or_reuse_store_image(self, selected.scope_ref)
        except (
            _IndependentTraceLineageInvalid,
            AttributeError,
            TypeError,
            ValueError,
            KeyError,
            IndexError,
        ):
            return self._unavailable_attempt(
                selected,
                governance_v2.GovernanceFailureStageV2.RECONCILIATION,
            )
        existing = self._committed.get((selected.scope_ref, selected.transition_id))
        if existing is not None:
            return self._reconcile_existing(selected, existing)
        if self._failure_stage == "after_identity_reconciliation":
            return self._unavailable_attempt(
                selected,
                governance_v2.GovernanceFailureStageV2.RECONCILIATION,
            )
        if selected.scope_ref in self._seals:
            return self._failure_attempt(
                selected,
                protocol_v2.AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
                "/domain_root",
                governance_v2.GovernanceFailureStageV2.SEAL,
            )
        return selected

    def _reconcile_existing(
        self,
        selected: governance_v2.GovernanceCommitBatchV2,
        existing: governance_v2.GovernanceCommittedTransitionV2,
    ) -> governance_v2.GovernanceCommitAttemptV2:
        try:
            _validate_or_reuse_store_image(
                self,
                selected.scope_ref,
                selected.transition_id,
            )
            detached = _clone_committed(existing)
            if (
                detached.batch.batch_root == selected.batch_root
                and detached.batch.canonical_bytes() == selected.canonical_bytes()
            ):
                return self._committed_attempt(detached)
        except (
            _IndependentTraceLineageInvalid,
            AttributeError,
            TypeError,
            ValueError,
            KeyError,
            IndexError,
        ):
            return self._unavailable_attempt(
                selected,
                governance_v2.GovernanceFailureStageV2.RECONCILIATION,
            )
        return self._failure_attempt(
            selected,
            protocol_v2.AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT,
            "/transition_id",
            governance_v2.GovernanceFailureStageV2.RECONCILIATION,
        )

    def _stage_and_publish(
        self,
        selected: governance_v2.GovernanceCommitBatchV2,
    ) -> governance_v2.GovernanceCommitAttemptV2:
        previous = self._head(selected.scope_ref, selected.stream_ref)
        state_root, next_state = _next_state(selected)
        head = governance_v2.GovernanceHeadV2(
            domain_root=selected.domain_root,
            scope_ref=selected.scope_ref,
            stream_ref=selected.stream_ref,
            revision=previous.revision + 1,
            parent_root=previous.head_root,
            state_root=state_root,
            transition_id=selected.transition_id,
            batch_root=selected.batch_root,
        )
        if self._failure_stage == "after_state_head_staging":
            return self._unavailable_attempt(
                selected,
                governance_v2.GovernanceFailureStageV2.COMMIT,
            )

        trace_batch = governance_v2.GovernanceTraceBatchV2.from_dict(
            selected.trace_batch.to_dict()
        )
        if self._failure_stage == "after_trace_staging":
            return self._unavailable_attempt(
                selected,
                governance_v2.GovernanceFailureStageV2.TRACE,
            )

        committed = _committed_artifacts(selected, head)
        if self._failure_stage == "after_receipt_inclusion_staging":
            return self._unavailable_attempt(
                selected,
                governance_v2.GovernanceFailureStageV2.COMMIT,
            )
        self._publish(selected, head, next_state, trace_batch, committed)
        if self._failure_stage == "after_atomic_publication":
            return self._unavailable_attempt(
                selected,
                governance_v2.GovernanceFailureStageV2.FINALITY,
            )
        return self._committed_attempt(committed)

    def _publish(
        self,
        selected: governance_v2.GovernanceCommitBatchV2,
        head: governance_v2.GovernanceHeadV2,
        next_state: dict[str, Any],
        trace_batch: governance_v2.GovernanceTraceBatchV2,
        committed: governance_v2.GovernanceCommittedTransitionV2,
    ) -> None:
        self._validated_image_fingerprints.pop(selected.scope_ref, None)
        identity_key = (selected.scope_ref, selected.transition_id)
        self._domains[selected.scope_ref] = _clone_domain(selected.domain)
        self._heads[(selected.scope_ref, selected.stream_ref)] = _clone_head(head)
        self._states[(selected.scope_ref, selected.stream_ref)] = next_state
        self._committed[identity_key] = _clone_committed(committed)
        self._history[
            (selected.scope_ref, selected.stream_ref, committed.receipt.revision)
        ] = _clone_committed(committed)
        self._trace_batches[identity_key] = trace_batch
        self._commit_order.setdefault(selected.scope_ref, []).append(
            selected.transition_id
        )
        self._transition_index[identity_key] = len(
            self._commit_order[selected.scope_ref]
        )
        if selected.kind == "seal":
            assert selected.seal is not None
            self._seals[selected.scope_ref] = (
                governance_v2.GovernanceDomainSealV2.from_dict(selected.seal.to_dict())
            )

    def _validate_store_preconditions(
        self,
        batch: governance_v2.GovernanceCommitBatchV2,
    ) -> governance_v2.GovernanceCommitAttemptV2 | None:
        current_streams = {
            stream
            for (scope, stream), head in self._heads.items()
            if scope == batch.scope_ref
            and stream != governance_v2.GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
            and head.revision > 0
        }
        if batch.kind == "transition":
            if (
                batch.stream_ref not in current_streams
                and len(current_streams)
                >= governance_v2.MAX_GOVERNANCE_NON_LIFECYCLE_STREAMS_V2
            ):
                return self._failure_attempt(
                    batch,
                    protocol_v2.AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_INVALID,
                    "/read_set",
                    governance_v2.GovernanceFailureStageV2.PRECONDITION,
                )
        else:
            declared_streams = {
                item.stream_ref
                for item in batch.read_set.entries
                if item.stream_ref
                != governance_v2.GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
            }
            if declared_streams != current_streams:
                return self._failure_attempt(
                    batch,
                    protocol_v2.AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
                    "/read_set",
                    governance_v2.GovernanceFailureStageV2.PRECONDITION,
                )
        for item in batch.read_set.entries:
            current = self._head(batch.scope_ref, item.stream_ref)
            if (
                current.revision != item.expected_revision
                or current.head_root != item.expected_root
            ):
                return self._failure_attempt(
                    batch,
                    protocol_v2.AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
                    "/read_set",
                    governance_v2.GovernanceFailureStageV2.PRECONDITION,
                )
        return None

    def _committed_attempt(
        self,
        committed: governance_v2.GovernanceCommittedTransitionV2,
    ) -> governance_v2.GovernanceCommitAttemptV2:
        detached = _clone_committed(committed)
        position = self._position(detached)
        batch = detached.batch
        return governance_v2.GovernanceCommitAttemptV2(
            domain_root=batch.domain_root,
            scope_ref=batch.scope_ref,
            stream_ref=batch.stream_ref,
            transition_id=batch.transition_id,
            disposition=governance_v2.GovernanceCommitDispositionV2.COMMITTED,
            failure=None,
            committed_transition=detached,
            position_observation=position,
        )

    def _position(
        self,
        committed: governance_v2.GovernanceCommittedTransitionV2,
    ) -> governance_v2.GovernanceCommitPositionObservationV2:
        receipt = committed.receipt
        head = self._head(receipt.scope_ref, receipt.stream_ref)
        seal = self._seals.get(receipt.scope_ref)
        if seal is not None:
            position = governance_v2.GovernanceCommitPositionV2.SEALED
            seal_root: str | None = seal.seal_root
        elif head.head_root == receipt.head_root:
            position = governance_v2.GovernanceCommitPositionV2.CURRENT
            seal_root = None
        else:
            position = governance_v2.GovernanceCommitPositionV2.SUPERSEDED
            seal_root = None
        return governance_v2.GovernanceCommitPositionObservationV2(
            domain_root=receipt.domain_root,
            scope_ref=receipt.scope_ref,
            stream_ref=receipt.stream_ref,
            transition_id=receipt.transition_id,
            receipt_root=receipt.receipt_root,
            observed_revision=head.revision,
            observed_head_root=head.head_root,
            position=position,
            seal_root=seal_root,
        )

    def _failure_attempt(
        self,
        batch: governance_v2.GovernanceCommitBatchV2,
        code: protocol_v2.AuthorityDiagnosticCodeV2,
        path: str,
        stage: governance_v2.GovernanceFailureStageV2,
    ) -> governance_v2.GovernanceCommitAttemptV2:
        failure = governance_v2.GovernanceFailureV2(
            code=code,
            path=path,
            stage=stage,
        )
        return governance_v2.GovernanceCommitAttemptV2(
            domain_root=batch.domain_root,
            scope_ref=batch.scope_ref,
            stream_ref=batch.stream_ref,
            transition_id=batch.transition_id,
            disposition=_disposition(code),
            failure=failure,
            committed_transition=None,
            position_observation=None,
        )

    def _unavailable_attempt(
        self,
        batch: governance_v2.GovernanceCommitBatchV2,
        stage: governance_v2.GovernanceFailureStageV2,
    ) -> governance_v2.GovernanceCommitAttemptV2:
        return self._failure_attempt(
            batch,
            protocol_v2.AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
            "",
            stage,
        )

    def _view_failure(
        self,
        domain: governance_v2.AuthorityDomainV2,
        stream_ref: str,
        transition_id: str,
        expected_receipt_root: str | None,
        code: protocol_v2.AuthorityDiagnosticCodeV2,
        stage: governance_v2.GovernanceFailureStageV2,
        *,
        reliable_snapshot: bool = True,
        path: str | None = None,
    ) -> governance_v2.GovernanceCommitViewV2:
        head = self._head(domain.scope_ref, stream_ref) if reliable_snapshot else None
        failure = governance_v2.GovernanceFailureV2(
            code=code,
            path=("/transition_id" if reliable_snapshot else "")
            if path is None
            else path,
            stage=stage,
        )
        return governance_v2.GovernanceCommitViewV2(
            domain_root=domain.domain_root,
            scope_ref=domain.scope_ref,
            stream_ref=stream_ref,
            transition_id=transition_id,
            expected_receipt_root=expected_receipt_root,
            disposition=_disposition(code),
            failure=failure,
            committed_transition=None,
            position_observation=None,
            observed_revision=None if head is None else head.revision,
            observed_head_root=None if head is None else head.head_root,
        )

    def _head(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> governance_v2.GovernanceHeadV2:
        selected = self._heads.get((scope_ref, stream_ref))
        if selected is not None:
            return selected
        return governance_v2.GovernanceHeadV2.genesis(
            self._domain(scope_ref),
            stream_ref,
        )

    def _domain(self, scope_ref: str) -> governance_v2.AuthorityDomainV2:
        try:
            return self._domains[scope_ref]
        except KeyError as exc:
            raise KeyError("authority scope is not registered") from exc

    def _export_image(self) -> dict[str, object]:
        with self._lock:
            return {
                "version": "independent-stdlib-authority-store-image-v2",
                "domains": {
                    scope: domain.to_dict()
                    for scope, domain in sorted(self._domains.items())
                },
                "heads": [head.to_dict() for _key, head in sorted(self._heads.items())],
                "states": [
                    {
                        "scope_ref": scope,
                        "stream_ref": stream,
                        "state": deepcopy(state),
                    }
                    for (scope, stream), state in sorted(self._states.items())
                ],
                "committed": [
                    self._committed[(scope, transition_id)].to_dict()
                    for scope in sorted(self._commit_order)
                    for transition_id in self._commit_order[scope]
                ],
                "history": [
                    {
                        "scope_ref": scope,
                        "stream_ref": stream,
                        "revision": revision,
                        "committed_transition": committed.to_dict(),
                    }
                    for (scope, stream, revision), committed in sorted(
                        self._history.items()
                    )
                ],
                "trace_batches": [
                    {
                        "scope_ref": scope,
                        "transition_id": transition_id,
                        "trace_batch": trace.to_dict(),
                    }
                    for (scope, transition_id), trace in sorted(
                        self._trace_batches.items()
                    )
                ],
                "seals": [
                    seal.to_dict() for _scope, seal in sorted(self._seals.items())
                ],
                "transition_index": [
                    {
                        "scope_ref": scope,
                        "transition_id": transition_id,
                        "sequence": sequence,
                    }
                    for (scope, transition_id), sequence in sorted(
                        self._transition_index.items()
                    )
                ],
                "commit_order": {
                    scope: list(order)
                    for scope, order in sorted(self._commit_order.items())
                },
            }

    @classmethod
    def _from_image(
        cls,
        image: Mapping[str, object],
    ) -> IndependentStdlibGovernanceStateStoreV2:
        (
            domains,
            heads,
            states,
            committed,
            history,
            trace_batches,
            seals,
            transition_index,
            commit_order,
        ) = _image_sections(image)
        restored = cls()
        _restore_domains(restored, domains)
        _restore_heads(restored, heads)
        _restore_states(restored, states)
        observed_order = _restore_committed(restored, committed)
        _restore_history(restored, history)
        _restore_trace_batches(restored, trace_batches)
        _restore_seals(restored, seals)
        _restore_transition_index(restored, transition_index)
        requested_order = _restore_commit_order(commit_order)
        _validate_image_scope_closure(restored, requested_order)
        if requested_order != observed_order:
            raise ValueError("independent StateStore commit order was reordered")
        restored._commit_order = requested_order
        for scope_ref in restored._domains:
            _validate_store_image(restored, scope_ref)
            _bless_validated_store_image(restored, scope_ref)
        return restored

    def _observation(self, scope_ref: str) -> dict[str, object]:
        with self._lock:
            heads = sum(scope == scope_ref for scope, _stream in self._heads)
            states = sum(scope == scope_ref for scope, _stream in self._states)
            identities = sum(scope == scope_ref for scope, _id in self._committed)
            indexes = sum(scope == scope_ref for scope, _id in self._transition_index)
            traces = sum(scope == scope_ref for scope, _id in self._trace_batches)
            history = sum(scope == scope_ref for scope, _stream, _rev in self._history)
            image_bytes = _canonical_bytes(_independent_image_payload(self, scope_ref))
            return {
                "heads": heads,
                "states": states,
                "trace_batches": traces,
                "receipts": identities,
                "inclusions": history,
                "transition_ids": indexes,
                "seals": int(scope_ref in self._seals),
                "commit_order": tuple(self._commit_order.get(scope_ref, ())),
                "image_fingerprint": _image_fingerprint(image_bytes),
                "image_bytes": image_bytes,
            }

    def _tamper(
        self,
        scope_ref: str,
        transition_id: str,
        case: str,
    ) -> None:
        if case not in _TAMPER_CASES:
            raise ValueError("unsupported StateStore v2 tamper case")
        with self._lock:
            self._validated_image_fingerprints.pop(scope_ref, None)
            committed = self._committed[(scope_ref, transition_id)]
            _tamper_independent_entry(self, committed, case)


def _next_state(
    batch: governance_v2.GovernanceCommitBatchV2,
) -> tuple[str, dict[str, Any]]:
    if batch.kind == "transition":
        assert batch.transition is not None
        return (
            batch.transition.state_root,
            _portable_state_records(batch.transition.state_records),
        )
    assert batch.seal is not None
    return batch.seal.seal_root, {"seal": batch.seal.to_dict()}


def _portable_state_records(value: Mapping[str, Any]) -> dict[str, Any]:
    """Detach a canonical frozen state projection without implementation hooks."""

    return {
        key: _portable_state_value(item, path=f"state_records.{key}")
        for key, item in value.items()
    }


def _portable_state_value(value: object, *, path: str) -> Any:
    if value is None or type(value) in {bool, int, float, str}:
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError(f"{path} key must be text")
            result[key] = _portable_state_value(item, path=f"{path}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [
            _portable_state_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise TypeError(f"{path} contains a non-portable value")


def _committed_artifacts(
    batch: governance_v2.GovernanceCommitBatchV2,
    head: governance_v2.GovernanceHeadV2,
) -> governance_v2.GovernanceCommittedTransitionV2:
    receipt = governance_v2.GovernanceCommitReceiptV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        revision=head.revision,
        parent_root=head.parent_root,
        head_root=head.head_root,
        state_root=head.state_root,
        read_set_root=batch.read_set_root,
        trace_root=batch.trace_root,
        batch_root=batch.batch_root,
    )
    inclusion = governance_v2.GovernanceCommitInclusionProofV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        revision=head.revision,
        batch_root=batch.batch_root,
        receipt_root=receipt.receipt_root,
        head_root=head.head_root,
    )
    return governance_v2.GovernanceCommittedTransitionV2(
        batch=batch,
        receipt=receipt,
        inclusion_proof=inclusion,
    )


def _image_sections(
    image: Mapping[str, object],
) -> tuple[
    dict[str, object],
    list[object],
    list[object],
    list[object],
    list[object],
    list[object],
    list[object],
    list[object],
    dict[str, object],
]:
    if (
        set(image)
        != {
            "version",
            "domains",
            "heads",
            "states",
            "committed",
            "history",
            "trace_batches",
            "seals",
            "transition_index",
            "commit_order",
        }
        or image.get("version") != "independent-stdlib-authority-store-image-v2"
    ):
        raise ValueError("independent StateStore image version is invalid")
    domains = image.get("domains")
    heads = image.get("heads")
    states = image.get("states")
    committed = image.get("committed")
    history = image.get("history")
    trace_batches = image.get("trace_batches")
    seals = image.get("seals")
    transition_index = image.get("transition_index")
    commit_order = image.get("commit_order")
    if type(domains) is not dict or type(commit_order) is not dict:
        raise TypeError("independent StateStore image mappings are invalid")
    if any(
        type(item) is not list
        for item in (
            heads,
            states,
            committed,
            history,
            trace_batches,
            seals,
            transition_index,
        )
    ):
        raise TypeError("independent StateStore image arrays are invalid")
    return cast(
        tuple[
            dict[str, object],
            list[object],
            list[object],
            list[object],
            list[object],
            list[object],
            list[object],
            list[object],
            dict[str, object],
        ],
        (
            domains,
            heads,
            states,
            committed,
            history,
            trace_batches,
            seals,
            transition_index,
            commit_order,
        ),
    )


def _restore_domains(
    restored: IndependentStdlibGovernanceStateStoreV2,
    domains: Mapping[str, object],
) -> None:
    for scope, wire in domains.items():
        if type(scope) is not str:
            raise TypeError("independent StateStore scope is invalid")
        domain = governance_v2.AuthorityDomainV2.from_dict(wire)
        if domain.scope_ref != scope:
            raise ValueError("independent StateStore domain is invalid")
        restored._domains[scope] = domain


def _restore_heads(
    restored: IndependentStdlibGovernanceStateStoreV2,
    heads: list[object],
) -> None:
    for wire in heads:
        head = governance_v2.GovernanceHeadV2.from_dict(wire)
        key = (head.scope_ref, head.stream_ref)
        if key in restored._heads:
            raise ValueError("independent StateStore head is duplicated")
        restored._heads[key] = head


def _restore_states(
    restored: IndependentStdlibGovernanceStateStoreV2,
    states: list[object],
) -> None:
    expected = {"scope_ref", "stream_ref", "state"}
    for wire in states:
        if type(wire) is not dict or set(wire) != expected:
            raise ValueError("independent StateStore state image is invalid")
        scope_ref = wire["scope_ref"]
        stream_ref = wire["stream_ref"]
        if type(scope_ref) is not str or type(stream_ref) is not str:
            raise TypeError("independent StateStore state binding is invalid")
        key = (scope_ref, stream_ref)
        if key in restored._states or type(wire["state"]) is not dict:
            raise ValueError("independent StateStore state is duplicated")
        restored._states[key] = deepcopy(wire["state"])


def _restore_committed(
    restored: IndependentStdlibGovernanceStateStoreV2,
    committed: list[object],
) -> dict[str, list[str]]:
    observed_order: dict[str, list[str]] = {}
    for wire in committed:
        item = governance_v2.GovernanceCommittedTransitionV2.from_dict(wire)
        batch = item.batch
        identity = (batch.scope_ref, batch.transition_id)
        history_key = (batch.scope_ref, batch.stream_ref, item.receipt.revision)
        if identity in restored._committed or history_key in restored._history:
            raise ValueError("independent StateStore committed entry is duplicated")
        restored._committed[identity] = item
        observed_order.setdefault(batch.scope_ref, []).append(batch.transition_id)
    return observed_order


def _restore_history(
    restored: IndependentStdlibGovernanceStateStoreV2,
    history: list[object],
) -> None:
    expected = {"scope_ref", "stream_ref", "revision", "committed_transition"}
    for wire in history:
        if type(wire) is not dict or set(wire) != expected:
            raise ValueError("independent StateStore history image is invalid")
        scope_ref = wire["scope_ref"]
        stream_ref = wire["stream_ref"]
        revision = wire["revision"]
        if (
            type(scope_ref) is not str
            or type(stream_ref) is not str
            or type(revision) is not int
            or revision < 1
        ):
            raise TypeError("independent StateStore history binding is invalid")
        key = (scope_ref, stream_ref, revision)
        if key in restored._history:
            raise ValueError("independent StateStore history entry is duplicated")
        restored._history[key] = (
            governance_v2.GovernanceCommittedTransitionV2.from_dict(
                wire["committed_transition"]
            )
        )


def _restore_trace_batches(
    restored: IndependentStdlibGovernanceStateStoreV2,
    trace_batches: list[object],
) -> None:
    expected = {"scope_ref", "transition_id", "trace_batch"}
    for wire in trace_batches:
        if type(wire) is not dict or set(wire) != expected:
            raise ValueError("independent StateStore Trace image is invalid")
        scope_ref = wire["scope_ref"]
        transition_id = wire["transition_id"]
        if type(scope_ref) is not str or type(transition_id) is not str:
            raise TypeError("independent StateStore Trace binding is invalid")
        key = (scope_ref, transition_id)
        if key in restored._trace_batches:
            raise ValueError("independent StateStore Trace entry is duplicated")
        restored._trace_batches[key] = governance_v2.GovernanceTraceBatchV2.from_dict(
            wire["trace_batch"]
        )


def _restore_seals(
    restored: IndependentStdlibGovernanceStateStoreV2,
    seals: list[object],
) -> None:
    for wire in seals:
        seal = governance_v2.GovernanceDomainSealV2.from_dict(wire)
        if seal.scope_ref in restored._seals:
            raise ValueError("independent StateStore seal image is duplicated")
        restored._seals[seal.scope_ref] = seal


def _restore_transition_index(
    restored: IndependentStdlibGovernanceStateStoreV2,
    transition_index: list[object],
) -> None:
    expected = {"scope_ref", "transition_id", "sequence"}
    for wire in transition_index:
        if type(wire) is not dict or set(wire) != expected:
            raise ValueError("independent StateStore identity index is invalid")
        scope_ref = wire["scope_ref"]
        transition_id = wire["transition_id"]
        sequence = wire["sequence"]
        if (
            type(scope_ref) is not str
            or type(transition_id) is not str
            or type(sequence) is not int
            or sequence < 1
        ):
            raise TypeError("independent StateStore identity index binding is invalid")
        key = (scope_ref, transition_id)
        if key in restored._transition_index:
            raise ValueError("independent StateStore identity index is duplicated")
        restored._transition_index[key] = sequence


def _restore_commit_order(
    commit_order: Mapping[str, object],
) -> dict[str, list[str]]:
    requested: dict[str, list[str]] = {}
    for scope, order in commit_order.items():
        if (
            type(scope) is not str
            or type(order) is not list
            or any(type(item) is not str for item in order)
        ):
            raise TypeError("independent StateStore commit order is invalid")
        if len(order) != len(set(order)):
            raise ValueError("independent StateStore commit order is duplicated")
        requested[scope] = list(order)
    return requested


def _validate_image_scope_closure(
    restored: IndependentStdlibGovernanceStateStoreV2,
    commit_order: Mapping[str, object],
) -> None:
    registered = set(restored._domains)
    observed = set(commit_order)
    observed.update(scope for scope, _stream in restored._heads)
    observed.update(scope for scope, _stream in restored._states)
    observed.update(scope for scope, _transition in restored._committed)
    observed.update(scope for scope, _stream, _revision in restored._history)
    observed.update(scope for scope, _transition in restored._trace_batches)
    observed.update(restored._seals)
    observed.update(scope for scope, _transition in restored._transition_index)
    if not observed <= registered:
        raise ValueError("independent StateStore image contains an orphan scope")


def _validate_or_reuse_store_image(
    store: IndependentStdlibGovernanceStateStoreV2,
    scope_ref: str,
    selected_transition_id: str | None = None,
) -> None:
    """Reuse validation only for an unchanged, previously validated scope image."""

    try:
        fingerprint = _validation_image_fingerprint(store, scope_ref)
    except (AttributeError, TypeError, ValueError, KeyError, IndexError):
        store._validated_image_fingerprints.pop(scope_ref, None)
        _validate_store_image(store, scope_ref, selected_transition_id)
        _bless_validated_store_image(store, scope_ref)
        return
    if store._validated_image_fingerprints.get(scope_ref) == fingerprint:
        if selected_transition_id is not None and selected_transition_id not in (
            store._commit_order.get(scope_ref, ())
        ):
            raise ValueError("independent StateStore selected identity is absent")
        return
    store._validated_image_fingerprints.pop(scope_ref, None)
    _validate_store_image(store, scope_ref, selected_transition_id)
    _bless_validated_store_image(store, scope_ref)


def _bless_validated_store_image(
    store: IndependentStdlibGovernanceStateStoreV2,
    scope_ref: str,
) -> None:
    store._validated_image_fingerprints[scope_ref] = _validation_image_fingerprint(
        store,
        scope_ref,
    )


def _validation_image_fingerprint(
    store: IndependentStdlibGovernanceStateStoreV2,
    scope_ref: str,
) -> str:
    """Hash every raw persisted section for one registered authority scope."""

    domain = store._domains[scope_ref]
    payload = {
        "version": "independent-stdlib-authority-validation-image-v2",
        "scope_ref": scope_ref,
        "domain": {
            "scope_ref": scope_ref,
            "value": domain.to_dict(),
        },
        "heads": [
            {
                "scope_ref": scope,
                "stream_ref": stream,
                "value": head.to_dict(),
            }
            for (scope, stream), head in sorted(store._heads.items())
            if scope == scope_ref
        ],
        "states": [
            {
                "scope_ref": scope,
                "stream_ref": stream,
                "value": state,
            }
            for (scope, stream), state in sorted(store._states.items())
            if scope == scope_ref
        ],
        "committed": [
            {
                "scope_ref": scope,
                "transition_id": transition_id,
                "value": committed.to_dict(),
            }
            for (scope, transition_id), committed in sorted(store._committed.items())
            if scope == scope_ref
        ],
        "history": [
            {
                "scope_ref": scope,
                "stream_ref": stream,
                "revision": revision,
                "value": committed.to_dict(),
            }
            for (scope, stream, revision), committed in sorted(store._history.items())
            if scope == scope_ref
        ],
        "trace_batches": [
            {
                "scope_ref": scope,
                "transition_id": transition_id,
                "value": trace.to_dict(),
            }
            for (scope, transition_id), trace in sorted(store._trace_batches.items())
            if scope == scope_ref
        ],
        "seals": [
            {
                "scope_ref": scope,
                "value": seal.to_dict(),
            }
            for scope, seal in sorted(store._seals.items())
            if scope == scope_ref
        ],
        "transition_index": [
            {
                "scope_ref": scope,
                "transition_id": transition_id,
                "sequence": sequence,
            }
            for (scope, transition_id), sequence in sorted(
                store._transition_index.items()
            )
            if scope == scope_ref
        ],
        "commit_order": [
            {
                "scope_ref": scope,
                "value": order,
            }
            for scope, order in sorted(store._commit_order.items())
            if scope == scope_ref
        ],
    }
    prefix = b"pheroos-conformance-authority-validation-image-v2\x00"
    return "sha256:" + sha256(prefix + _canonical_bytes(payload)).hexdigest()


def _validate_store_image(
    store: IndependentStdlibGovernanceStateStoreV2,
    scope_ref: str,
    selected_transition_id: str | None = None,
) -> None:
    domain = _clone_domain(store._domains[scope_ref])
    order = _validated_image_order(store, scope_ref)
    replay_heads, expected_history, expected_trace, sealed = _replay_store_image(
        store,
        scope_ref,
        domain,
        order,
    )
    if selected_transition_id is not None and selected_transition_id not in order:
        raise ValueError("independent StateStore selected identity is absent")
    _validate_projection_sets(store, scope_ref, replay_heads)
    if {key for key in store._history if key[0] == scope_ref} != expected_history:
        raise ValueError("independent StateStore history index is inconsistent")
    if {key for key in store._trace_batches if key[0] == scope_ref} != expected_trace:
        raise _IndependentTraceLineageInvalid(
            "independent StateStore Trace index is inconsistent"
        )
    _validate_seal_projection(store, scope_ref, replay_heads, sealed)


def _validated_image_order(
    store: IndependentStdlibGovernanceStateStoreV2,
    scope_ref: str,
) -> list[str]:
    order = store._commit_order.get(scope_ref, [])
    if type(order) is not list or any(type(item) is not str for item in order):
        raise TypeError("independent StateStore commit order is invalid")
    if len(order) != len(set(order)):
        raise ValueError("independent StateStore commit order is duplicated")
    committed_keys = {
        transition_id for scope, transition_id in store._committed if scope == scope_ref
    }
    if committed_keys != set(order):
        raise ValueError("independent StateStore identity index is inconsistent")
    expected_index = {
        (scope_ref, transition_id): sequence
        for sequence, transition_id in enumerate(order, start=1)
    }
    actual_index = {
        key: sequence
        for key, sequence in store._transition_index.items()
        if key[0] == scope_ref
    }
    if set(actual_index) != set(expected_index) or any(
        type(actual_index[key]) is not int or actual_index[key] != expected_sequence
        for key, expected_sequence in expected_index.items()
    ):
        raise ValueError("independent StateStore global sequence is inconsistent")
    return order


def _replay_store_image(
    store: IndependentStdlibGovernanceStateStoreV2,
    scope_ref: str,
    domain: governance_v2.AuthorityDomainV2,
    order: Sequence[str],
) -> tuple[
    dict[str, governance_v2.GovernanceHeadV2],
    set[tuple[str, str, int]],
    set[tuple[str, str]],
    bool,
]:
    replay_heads: dict[str, governance_v2.GovernanceHeadV2] = {}
    expected_history: set[tuple[str, str, int]] = set()
    expected_trace: set[tuple[str, str]] = set()
    sealed = False
    for transition_id in order:
        if sealed:
            raise ValueError("independent StateStore contains a post-seal commit")
        item = store._committed[(scope_ref, transition_id)]
        _validate_trace_material(store, scope_ref, transition_id, item)
        committed = _clone_committed(item)
        batch = committed.batch
        if batch.transition_id != transition_id:
            raise ValueError("independent StateStore identity binding is invalid")
        _validate_batch_domain(batch, domain)
        _validate_replayed_preconditions(batch, domain, replay_heads)
        previous = replay_heads.get(batch.stream_ref) or (
            governance_v2.GovernanceHeadV2.genesis(domain, batch.stream_ref)
        )
        _validate_commit_proof(committed, previous)
        current = governance_v2.GovernanceHeadV2(
            domain_root=committed.receipt.domain_root,
            scope_ref=committed.receipt.scope_ref,
            stream_ref=committed.receipt.stream_ref,
            revision=committed.receipt.revision,
            parent_root=committed.receipt.parent_root,
            state_root=committed.receipt.state_root,
            transition_id=committed.receipt.transition_id,
            batch_root=committed.receipt.batch_root,
            head_root=committed.receipt.head_root,
        )
        replay_heads[batch.stream_ref] = current
        history_key = (scope_ref, batch.stream_ref, committed.receipt.revision)
        expected_history.add(history_key)
        persisted_history = store._history.get(history_key)
        if persisted_history is None:
            raise ValueError("independent StateStore history is absent")
        _validate_trace_object(persisted_history.batch.trace_batch)
        if persisted_history.canonical_bytes() != committed.canonical_bytes():
            raise ValueError("independent StateStore history is inconsistent")
        expected_trace.add((scope_ref, transition_id))
        sealed = batch.kind == "seal"
    return replay_heads, expected_history, expected_trace, sealed


def _validate_trace_material(
    store: IndependentStdlibGovernanceStateStoreV2,
    scope_ref: str,
    transition_id: str,
    committed: governance_v2.GovernanceCommittedTransitionV2,
) -> None:
    _validate_trace_object(committed.batch.trace_batch)
    trace = store._trace_batches.get((scope_ref, transition_id))
    if trace is None:
        raise _IndependentTraceLineageInvalid("persisted Trace batch is absent")
    _validate_trace_object(trace)
    if trace.canonical_bytes() != committed.batch.trace_batch.canonical_bytes():
        raise _IndependentTraceLineageInvalid("persisted Trace batch is inconsistent")


def _validate_trace_object(trace: governance_v2.GovernanceTraceBatchV2) -> None:
    try:
        governance_v2.GovernanceTraceBatchV2.from_dict(trace.to_dict())
    except (AttributeError, TypeError, ValueError, KeyError, IndexError) as exc:
        raise _IndependentTraceLineageInvalid from exc


def _validate_batch_domain(
    batch: governance_v2.GovernanceCommitBatchV2,
    domain: governance_v2.AuthorityDomainV2,
) -> None:
    if (
        batch.scope_ref != domain.scope_ref
        or batch.domain_root != domain.domain_root
        or batch.domain.canonical_bytes() != domain.canonical_bytes()
    ):
        raise ValueError("independent StateStore batch crosses authority domain")


def _validate_replayed_preconditions(
    batch: governance_v2.GovernanceCommitBatchV2,
    domain: governance_v2.AuthorityDomainV2,
    replay_heads: Mapping[str, governance_v2.GovernanceHeadV2],
) -> None:
    for expected in batch.read_set.entries:
        current = replay_heads.get(expected.stream_ref) or (
            governance_v2.GovernanceHeadV2.genesis(domain, expected.stream_ref)
        )
        if (
            current.revision != expected.expected_revision
            or current.head_root != expected.expected_root
        ):
            raise ValueError("independent StateStore historical read set is invalid")
    if batch.kind != "seal":
        return
    streams = {
        item
        for item in replay_heads
        if item != governance_v2.GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
    }
    declared = {
        item.stream_ref
        for item in batch.read_set.entries
        if item.stream_ref != governance_v2.GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
    }
    if streams != declared or batch.seal is None:
        raise ValueError("independent StateStore seal coverage is invalid")
    expected_final = tuple(
        {
            "stream_ref": stream_ref,
            "revision": replay_heads[stream_ref].revision,
            "head_root": replay_heads[stream_ref].head_root,
        }
        for stream_ref in sorted(streams, key=lambda item: item.encode())
    )
    if tuple(dict(item) for item in batch.seal.final_heads) != expected_final:
        raise ValueError("independent StateStore seal final heads are invalid")


def _validate_commit_proof(
    committed: governance_v2.GovernanceCommittedTransitionV2,
    previous: governance_v2.GovernanceHeadV2,
) -> None:
    batch = committed.batch
    receipt = committed.receipt
    inclusion = committed.inclusion_proof
    state_root, _state = _next_state(batch)
    if (
        receipt.domain_root != batch.domain_root
        or receipt.scope_ref != batch.scope_ref
        or receipt.stream_ref != batch.stream_ref
        or receipt.transition_id != batch.transition_id
        or receipt.revision != previous.revision + 1
        or receipt.parent_root != previous.head_root
        or receipt.state_root != state_root
        or receipt.read_set_root != batch.read_set_root
        or receipt.trace_root != batch.trace_root
        or receipt.batch_root != batch.batch_root
        or inclusion.domain_root != receipt.domain_root
        or inclusion.scope_ref != receipt.scope_ref
        or inclusion.stream_ref != receipt.stream_ref
        or inclusion.transition_id != receipt.transition_id
        or inclusion.revision != receipt.revision
        or inclusion.batch_root != receipt.batch_root
        or inclusion.receipt_root != receipt.receipt_root
        or inclusion.head_root != receipt.head_root
    ):
        raise ValueError("independent StateStore commit proof is inconsistent")


def _validate_projection_sets(
    store: IndependentStdlibGovernanceStateStoreV2,
    scope_ref: str,
    replay_heads: Mapping[str, governance_v2.GovernanceHeadV2],
) -> None:
    heads = {stream for scope, stream in store._heads if scope == scope_ref}
    states = {stream for scope, stream in store._states if scope == scope_ref}
    if heads != set(replay_heads) or states != set(replay_heads):
        raise ValueError("independent StateStore projection set is incomplete")
    for stream_ref, expected in replay_heads.items():
        actual = _clone_head(store._heads[(scope_ref, stream_ref)])
        if actual.canonical_bytes() != expected.canonical_bytes():
            raise ValueError("independent StateStore current head is inconsistent")
        current = store._committed[(scope_ref, expected.transition_id)]
        _validate_projection_state(store, scope_ref, stream_ref, current)


def _validate_projection_state(
    store: IndependentStdlibGovernanceStateStoreV2,
    scope_ref: str,
    stream_ref: str,
    committed: governance_v2.GovernanceCommittedTransitionV2,
) -> None:
    _root, expected = _next_state(committed.batch)
    actual = store._states[(scope_ref, stream_ref)]
    if _canonical_bytes(actual) != _canonical_bytes(expected):
        raise ValueError("independent StateStore state projection is inconsistent")
    if committed.batch.kind == "transition" and (
        committed.batch.transition is None
        or committed.batch.transition.state_root != committed.receipt.state_root
    ):
        raise ValueError("independent StateStore state root is inconsistent")


def _validate_seal_projection(
    store: IndependentStdlibGovernanceStateStoreV2,
    scope_ref: str,
    replay_heads: Mapping[str, governance_v2.GovernanceHeadV2],
    sealed: bool,
) -> None:
    seal = store._seals.get(scope_ref)
    lifecycle = governance_v2.GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
    if not sealed:
        if seal is not None or lifecycle in replay_heads:
            raise ValueError("independent open StateStore contains seal material")
        return
    if seal is None or lifecycle not in replay_heads:
        raise ValueError("independent sealed StateStore is incomplete")
    parsed = governance_v2.GovernanceDomainSealV2.from_dict(seal.to_dict())
    lifecycle_head = replay_heads[lifecycle]
    if lifecycle_head.state_root != parsed.seal_root:
        raise ValueError("independent lifecycle head is not seal-bound")


def _independent_image_payload(
    store: IndependentStdlibGovernanceStateStoreV2,
    scope_ref: str,
) -> Mapping[str, object]:
    order = tuple(store._commit_order.get(scope_ref, ()))
    committed = [store._committed[(scope_ref, item)] for item in order]
    payload = {
        "heads": [
            head.to_dict()
            for (scope, _stream), head in sorted(store._heads.items())
            if scope == scope_ref
        ],
        "states": [
            {
                "stream_ref": stream,
                "state_records": deepcopy(state),
            }
            for (scope, stream), state in sorted(store._states.items())
            if scope == scope_ref
        ],
        "trace_batches": [
            trace.to_dict()
            for (scope, _transition), trace in sorted(store._trace_batches.items())
            if scope == scope_ref
        ],
        "receipts": [
            {"batch": item.batch.to_dict(), "receipt": item.receipt.to_dict()}
            for item in committed
        ],
        "inclusions": {
            "proofs": [item.inclusion_proof.to_dict() for item in committed],
            "history": [
                {
                    "scope_ref": scope,
                    "stream_ref": stream,
                    "revision": revision,
                    "committed_transition": item.to_dict(),
                }
                for (scope, stream, revision), item in sorted(store._history.items())
                if scope == scope_ref
            ],
        },
        "transition_ids": {
            "index": [
                {"transition_id": transition_id, "sequence": sequence}
                for (scope, transition_id), sequence in sorted(
                    store._transition_index.items()
                )
                if scope == scope_ref
            ],
            "sequences": [
                {
                    "sequence": store._transition_index.get((scope_ref, transition_id)),
                    "transition_id": transition_id,
                }
                for transition_id in order
            ],
        },
        "seals": {
            "seal_root": None
            if scope_ref not in store._seals
            else store._seals[scope_ref].seal_root,
            "records": []
            if scope_ref not in store._seals
            else [store._seals[scope_ref].to_dict()],
        },
    }
    return payload


def _image_fingerprint(encoded: bytes) -> str:
    prefix = b"pheroos-conformance-authority-image-v2\x00"
    return "sha256:" + sha256(prefix + encoded).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _tamper_independent_entry(
    store: IndependentStdlibGovernanceStateStoreV2,
    committed: governance_v2.GovernanceCommittedTransitionV2,
    case: str,
) -> None:
    zero_root = "sha256:" + "0" * 64
    handlers = (
        _tamper_independent_commit,
        _tamper_independent_projection,
        _tamper_independent_trace_binding,
        _tamper_independent_seal,
        _tamper_independent_closure,
    )
    for handler in handlers:
        if handler(store, committed, case, zero_root):
            return
    raise AssertionError("unhandled StateStore v2 tamper case")


def _tamper_independent_commit(
    store: IndependentStdlibGovernanceStateStoreV2,
    committed: governance_v2.GovernanceCommittedTransitionV2,
    case: str,
    zero_root: str,
) -> bool:
    batch = committed.batch
    receipt = committed.receipt
    inclusion = committed.inclusion_proof
    if case == "batch_payload":
        object.__setattr__(batch, "transition_id", batch.transition_id + ":tampered")
    elif case == "batch_root":
        object.__setattr__(batch, "batch_root", zero_root)
    elif case == "receipt_payload":
        object.__setattr__(receipt, "state_root", zero_root)
    elif case == "receipt_root":
        object.__setattr__(receipt, "receipt_root", zero_root)
    elif case == "inclusion_payload":
        object.__setattr__(inclusion, "batch_root", zero_root)
    elif case == "inclusion_root":
        object.__setattr__(inclusion, "inclusion_root", zero_root)
    elif case == "history_payload":
        history = store._history[(batch.scope_ref, batch.stream_ref, receipt.revision)]
        object.__setattr__(history.receipt, "parent_root", zero_root)
    else:
        return False
    return True


def _tamper_independent_projection(
    store: IndependentStdlibGovernanceStateStoreV2,
    committed: governance_v2.GovernanceCommittedTransitionV2,
    case: str,
    zero_root: str,
) -> bool:
    key = (committed.batch.scope_ref, committed.batch.stream_ref)
    if case == "head_payload":
        object.__setattr__(store._heads[key], "batch_root", zero_root)
    elif case == "head_root":
        object.__setattr__(store._heads[key], "head_root", zero_root)
    elif case == "state_payload":
        store._states[key]["tampered"] = True
    elif case == "state_root":
        object.__setattr__(store._heads[key], "state_root", zero_root)
    else:
        return False
    return True


def _tamper_independent_trace_binding(
    store: IndependentStdlibGovernanceStateStoreV2,
    committed: governance_v2.GovernanceCommittedTransitionV2,
    case: str,
    zero_root: str,
) -> bool:
    batch, receipt = committed.batch, committed.receipt
    identity = (batch.scope_ref, batch.transition_id)
    if case == "trace_payload":
        _tamper_trace_payload(store._trace_batches[identity])
    elif case == "trace_root":
        object.__setattr__(store._trace_batches[identity], "trace_root", zero_root)
    elif case == "scope_binding":
        object.__setattr__(receipt, "scope_ref", receipt.scope_ref + ":crossed")
    elif case == "stream_binding":
        object.__setattr__(receipt, "stream_ref", receipt.stream_ref + ":crossed")
    elif case == "revision_binding":
        object.__setattr__(receipt, "revision", True)
    else:
        return False
    return True


def _tamper_independent_seal(
    store: IndependentStdlibGovernanceStateStoreV2,
    committed: governance_v2.GovernanceCommittedTransitionV2,
    case: str,
    zero_root: str,
) -> bool:
    batch = committed.batch
    if case == "seal_payload":
        seal = store._seals[batch.scope_ref]
        object.__setattr__(seal, "transition_id", seal.transition_id + ":tampered")
    elif case == "seal_root":
        object.__setattr__(store._seals[batch.scope_ref], "seal_root", zero_root)
    elif case == "lifecycle_state":
        lifecycle_key = (
            batch.scope_ref,
            governance_v2.GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        )
        store._states[lifecycle_key]["tampered"] = True
    elif case == "seal_marker":
        store._seals.pop(batch.scope_ref)
    else:
        return False
    return True


def _tamper_independent_closure(
    store: IndependentStdlibGovernanceStateStoreV2,
    committed: governance_v2.GovernanceCommittedTransitionV2,
    case: str,
    _zero_root: str,
) -> bool:
    batch = committed.batch
    key = (batch.scope_ref, batch.stream_ref)
    identity = (batch.scope_ref, batch.transition_id)
    if case == "transition_index":
        store._transition_index.pop(identity)
    elif case == "projection_removal":
        store._heads.pop(key)
        store._states.pop(key)
    elif case == "sequence_binding":
        store._transition_index[identity] = True
    elif case == "cross_stream_order":
        order = store._commit_order[batch.scope_ref]
        original_index = order.index(batch.transition_id)
        if original_index < 1:
            raise ValueError("cross-stream order tamper requires a predecessor")
        predecessor_id = order[original_index - 1]
        order[original_index - 1], order[original_index] = (
            batch.transition_id,
            predecessor_id,
        )
        store._transition_index[identity] = original_index
        store._transition_index[(batch.scope_ref, predecessor_id)] = original_index + 1
    else:
        return False
    return True


def _tamper_trace_payload(trace_batch: governance_v2.GovernanceTraceBatchV2) -> None:
    snapshots = tuple(cast(list[dict[str, Any]], trace_batch.to_dict()["events"]))
    first = snapshots[0]
    first["reason"] = cast(str, first["reason"]) + ":tampered"
    object.__setattr__(trace_batch, "_event_snapshots", snapshots)


class IndependentStdlibGovernanceStateStoreV2Adapter:
    """Conformance adapter for the independent public-contract-only model."""

    __slots__ = ()

    implementation_id = "pheroos-independent-stdlib-governance-state-store-v2"
    conformance_version = _CONFORMANCE_VERSION

    def create_domain_v2(
        self,
        scope_ref: str,
    ) -> governance_v2.AuthorityDomainV2:
        return _local_domain(scope_ref)

    def create_store_v2(
        self,
        domains: Sequence[governance_v2.AuthorityDomainV2],
    ) -> governance_v2.GovernanceStateStoreV2:
        return IndependentStdlibGovernanceStateStoreV2(domains)

    def restart_store_v2(
        self,
        store: governance_v2.GovernanceStateStoreV2,
    ) -> governance_v2.GovernanceStateStoreV2:
        selected = _require_independent_store(store)
        return IndependentStdlibGovernanceStateStoreV2._from_image(
            selected._export_image()
        )

    def create_failure_injected_store_v2(
        self,
        stage: str,
        domains: Sequence[governance_v2.AuthorityDomainV2],
    ) -> governance_v2.GovernanceStateStoreV2:
        return IndependentStdlibGovernanceStateStoreV2(
            domains,
            failure_stage=stage,
        )

    def observe_store_v2(
        self,
        store: governance_v2.GovernanceStateStoreV2,
        scope_ref: str,
    ) -> Mapping[str, object]:
        return _require_independent_store(store)._observation(scope_ref)

    def tamper_store_v2(
        self,
        store: governance_v2.GovernanceStateStoreV2,
        scope_ref: str,
        transition_id: str,
        case: str,
    ) -> None:
        _require_independent_store(store)._tamper(
            scope_ref,
            transition_id,
            case,
        )


def _require_independent_store(
    store: governance_v2.GovernanceStateStoreV2,
) -> IndependentStdlibGovernanceStateStoreV2:
    if type(store) is not IndependentStdlibGovernanceStateStoreV2:
        raise TypeError("adapter received a foreign StateStore implementation")
    return store


def _local_domain(scope_ref: str) -> governance_v2.AuthorityDomainV2:
    return governance_v2.AuthorityDomainV2(
        policy_version=governance_v2.AUTHORITY_POLICY_VERSION_V2,
        profile=governance_v2.AUTHORITY_LOCAL_PROFILE_V2,
        wire_version=governance_v2.AUTHORITY_WIRE_VERSION_V2,
        canonical_version=protocol_v2.AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=governance_v2.AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=governance_v2.GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=governance_v2.GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=protocol_v2.GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref=scope_ref,
    )


def _disposition(
    code: protocol_v2.AuthorityDiagnosticCodeV2,
) -> governance_v2.GovernanceCommitDispositionV2:
    if code is protocol_v2.AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE:
        return governance_v2.GovernanceCommitDispositionV2.RETRY_REQUIRED
    if code is protocol_v2.AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED:
        return governance_v2.GovernanceCommitDispositionV2.DENIED
    if code is protocol_v2.AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE:
        return governance_v2.GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    return governance_v2.GovernanceCommitDispositionV2.INVALID


def _clone_domain(
    value: governance_v2.AuthorityDomainV2,
) -> governance_v2.AuthorityDomainV2:
    return governance_v2.AuthorityDomainV2.from_dict(value.to_dict())


def _clone_head(
    value: governance_v2.GovernanceHeadV2,
) -> governance_v2.GovernanceHeadV2:
    return governance_v2.GovernanceHeadV2.from_dict(value.to_dict())


def _clone_committed(
    value: governance_v2.GovernanceCommittedTransitionV2,
) -> governance_v2.GovernanceCommittedTransitionV2:
    return governance_v2.GovernanceCommittedTransitionV2.from_dict(value.to_dict())


__all__ = [
    "IndependentStdlibGovernanceStateStoreV2",
    "IndependentStdlibGovernanceStateStoreV2Adapter",
]
