"""Serialized, provider-free reference StateStore v2.

This module is deliberately private.  It proves the public Store protocols
without making its snapshot format, failure hooks, or in-memory layout part of
the Governance ABI.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from threading import RLock
from typing import Any, NoReturn
import unicodedata

from pheroos.governance.authority_store_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    AuthorityDiagnosticCodeV2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitInclusionProofV2,
    GovernanceCommitPositionObservationV2,
    GovernanceCommitPositionV2,
    GovernanceCommitReceiptV2,
    GovernanceCommitViewV2,
    GovernanceCommittedTransitionV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceTraceBatchV2,
    MAX_GOVERNANCE_NON_LIFECYCLE_STREAMS_V2,
    _governance_disposition_for_diagnostic_v2,
    governance_authority_state_root_v2,
)
from pheroos.protocol.authority_v2 import MAX_AUTHORITY_REVISION_V2


FAILURE_STAGE_BEFORE_VALIDATION_V2 = "before_validation"
FAILURE_STAGE_AFTER_IDENTITY_RECONCILIATION_V2 = "after_identity_reconciliation"
FAILURE_STAGE_AFTER_READ_SET_VALIDATION_V2 = "after_read_set_validation"
FAILURE_STAGE_AFTER_STATE_HEAD_STAGING_V2 = "after_state_head_staging"
FAILURE_STAGE_AFTER_TRACE_STAGING_V2 = "after_trace_staging"
FAILURE_STAGE_AFTER_RECEIPT_INCLUSION_STAGING_V2 = "after_receipt_inclusion_staging"
FAILURE_STAGE_AFTER_ATOMIC_PUBLICATION_V2 = "after_atomic_publication"

_REFERENCE_SNAPSHOT_SCHEMA_V2 = "pheroos-governance-reference-snapshot-v2"

FailureInjectorV2 = Callable[[str, GovernanceCommitBatchV2], None]


def _validated_failure_injector(
    value: FailureInjectorV2 | None,
) -> FailureInjectorV2 | None:
    if value is not None and not callable(value):
        raise TypeError("failure_injector must be callable or None")
    return value


class _TraceLineageInvalidV2(ValueError):
    """Private typed marker for corrupted committed Trace material."""


@dataclass(frozen=True, slots=True)
class _CommittedEntryV2:
    sequence: int
    batch: GovernanceCommitBatchV2
    receipt: GovernanceCommitReceiptV2
    inclusion_proof: GovernanceCommitInclusionProofV2
    verified_integrity_root: str


@dataclass(frozen=True, slots=True, eq=False)
class _VerifiedDomainCheckpointV2:
    """Non-portable witness for one fully verified immutable domain image.

    The object references deliberately never enter ``snapshot_v2``.  They make
    replacement of any top-level projection observable in constant time while
    the history and tail roots permit append-only successor verification using
    only the newly committed batch.  The reference Store owns these objects;
    callers only receive detached ABI records.
    """

    domain_ref: object
    heads_ref: object
    states_ref: object
    entries_ref: object
    transition_index_ref: object
    domain_root: str
    scope_ref: str
    entry_count: int
    head_count: int
    state_count: int
    transition_count: int
    tail_entry_ref: object | None
    tail_entry_root: str | None
    parent_history_root: str | None
    history_root: str
    seal_root: str | None


@dataclass(frozen=True, slots=True)
class _DomainImageV2:
    domain: AuthorityDomainV2
    heads: Mapping[str, GovernanceHeadV2]
    states: Mapping[str, Mapping[str, Any]]
    entries: tuple[_CommittedEntryV2, ...]
    transition_index: Mapping[str, int]
    seal_root: str | None
    verified_checkpoint: _VerifiedDomainCheckpointV2 | None


class InMemoryGovernanceStateStoreV2:
    """RLock-serialized reference implementation of the StateStore v2 ABI."""

    def __init__(
        self,
        domains: Iterable[AuthorityDomainV2] = (),
        *,
        failure_injector: FailureInjectorV2 | None = None,
    ) -> None:
        self._lock = RLock()
        self.__domain_images: dict[str, _DomainImageV2] = {}
        self._private_image_exposed = False
        self._failure_injector = _validated_failure_injector(failure_injector)
        for domain in domains:
            self.register_domain_v2(domain)

    @property
    def state_store_version(self) -> str:
        return GOVERNANCE_STATE_STORE_VERSION_V2

    @property
    def _domains(self) -> dict[str, _DomainImageV2]:
        """Expose private images only for adversarial reference instrumentation.

        Any retained reference can bypass frozen dataclasses with reflection.
        Once exposed, every later public operation therefore performs the full
        replay audit.  Normal Store consumers never use this private hook and
        remain on the incremental verified-checkpoint path.
        """

        with self._lock:
            self._private_image_exposed = True
            return self.__domain_images

    def register_domain_v2(self, domain: AuthorityDomainV2) -> None:
        """Register one selected domain for reference setup, never by inference."""

        detached = _clone_domain(domain)
        with self._lock:
            existing = self.__domain_images.get(detached.scope_ref)
            if existing is not None:
                self._verify_image_integrity(existing)
                if existing.domain.canonical_bytes() == detached.canonical_bytes():
                    return
                raise ValueError("authority scope already selects another domain")
            self.__domain_images[detached.scope_ref] = _empty_domain_image(detached)

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        _require_ref(scope_ref, "scope_ref")
        _require_ref(stream_ref, "stream_ref")
        with self._lock:
            image = self._resolve_domain(scope_ref)
            self._verify_image_integrity(image)
            head = _head_for(image, stream_ref)
            _verify_current_projection(image, stream_ref, head)
            return _clone_head(head)

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        _require_ref(scope_ref, "scope_ref")
        _require_ref(stream_ref, "stream_ref")
        with self._lock:
            image = self._resolve_domain(scope_ref)
            self._verify_image_integrity(image)
            _verify_current_projection(image, stream_ref, _head_for(image, stream_ref))
            return _detach_mapping(image.states.get(stream_ref, {}))

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        _require_ref(scope_ref, "scope_ref")
        _require_ref(stream_ref, "stream_ref")
        _require_ref(transition_id, "transition_id")
        with self._lock:
            image = self._resolve_domain(scope_ref)
            observed = _reliable_observed_head(image, stream_ref)
            try:
                self._verify_image_integrity(image)
                sequence = image.transition_index.get(transition_id)
            except _TraceLineageInvalidV2:
                return _invalid_view(
                    image,
                    stream_ref,
                    transition_id,
                    expected_receipt_root,
                    observed,
                    code=AuthorityDiagnosticCodeV2.GOVERNANCE_TRACE_LINEAGE_INVALID,
                    path="/committed_transition/batch/trace_batch",
                )
            except (AttributeError, TypeError, ValueError):
                return _invalid_view(
                    image,
                    stream_ref,
                    transition_id,
                    expected_receipt_root,
                    observed,
                )
            if sequence is None:
                return _invalid_view(
                    image,
                    stream_ref,
                    transition_id,
                    expected_receipt_root,
                    observed,
                )
            try:
                if type(sequence) is not int or not 1 <= sequence <= len(image.entries):
                    raise ValueError("committed transition index is invalid")
                entry = image.entries[sequence - 1]
                if entry.batch.stream_ref != stream_ref or (
                    expected_receipt_root is not None
                    and expected_receipt_root != entry.receipt.receipt_root
                ):
                    raise ValueError("commit view binding is mismatched")
                committed = _detached_committed(entry)
                _verify_selected_entry_in_image(image, entry)
                _verify_current_projection(
                    image,
                    stream_ref,
                    _head_for(image, stream_ref),
                )
                position = _position_for(image, entry.receipt)
            except _TraceLineageInvalidV2:
                return _invalid_view(
                    image,
                    stream_ref,
                    transition_id,
                    expected_receipt_root,
                    observed,
                    code=AuthorityDiagnosticCodeV2.GOVERNANCE_TRACE_LINEAGE_INVALID,
                    path="/committed_transition/batch/trace_batch",
                )
            except (AttributeError, TypeError, ValueError, KeyError, IndexError):
                return _invalid_view(
                    image,
                    stream_ref,
                    transition_id,
                    expected_receipt_root,
                    observed,
                )
            return GovernanceCommitViewV2(
                domain_root=image.domain.domain_root,
                scope_ref=scope_ref,
                stream_ref=stream_ref,
                transition_id=transition_id,
                expected_receipt_root=expected_receipt_root,
                disposition=GovernanceCommitDispositionV2.COMMITTED,
                failure=None,
                committed_transition=committed,
                position_observation=position,
                observed_revision=position.observed_revision,
                observed_head_root=position.observed_head_root,
            )

    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        if type(batch) is not GovernanceCommitBatchV2:
            raise TypeError("atomic_commit_v2 requires GovernanceCommitBatchV2")
        injected = self._injected_failure(
            FAILURE_STAGE_BEFORE_VALIDATION_V2,
            batch,
            GovernanceFailureStageV2.VALIDATION,
        )
        if injected is not None:
            return injected
        try:
            detached = GovernanceCommitBatchV2.from_dict(batch.to_dict())
        except (TypeError, ValueError):
            return _failure_attempt(
                batch,
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "",
                GovernanceFailureStageV2.VALIDATION,
            )

        with self._lock:
            try:
                return self._atomic_commit_locked(detached)
            except (AttributeError, TypeError, ValueError, KeyError, IndexError):
                return _unavailable_attempt(
                    detached,
                    GovernanceFailureStageV2.FINALITY,
                )

    def _atomic_commit_locked(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        image, selection_failure = _select_commit_domain(
            self.__domain_images,
            batch,
            verify_image=self._verify_image_integrity,
        )
        if selection_failure is not None:
            return selection_failure
        assert image is not None
        previous, lookup_failure = _lookup_existing_entry(image, batch)
        if lookup_failure is not None:
            return lookup_failure
        if previous is not None:
            return self._reconcile_existing(image, previous, batch)
        injected = self._injected_failure(
            FAILURE_STAGE_AFTER_IDENTITY_RECONCILIATION_V2,
            batch,
            GovernanceFailureStageV2.RECONCILIATION,
        )
        if injected is not None:
            return injected
        if image.seal_root is not None:
            return _failure_attempt(
                batch,
                AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
                "/domain_root",
                GovernanceFailureStageV2.SEAL,
            )
        if _would_exceed_stream_bound(image, batch):
            return _failure_attempt(
                batch,
                AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_INVALID,
                "/read_set",
                GovernanceFailureStageV2.PRECONDITION,
            )
        if not _read_set_matches(image, batch):
            return _failure_attempt(
                batch,
                AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
                "/read_set",
                GovernanceFailureStageV2.PRECONDITION,
            )
        injected = self._injected_failure(
            FAILURE_STAGE_AFTER_READ_SET_VALIDATION_V2,
            batch,
            GovernanceFailureStageV2.PRECONDITION,
        )
        if injected is not None:
            return injected
        current_head = _head_for(image, batch.stream_ref)
        if current_head.revision == MAX_AUTHORITY_REVISION_V2:
            return _failure_attempt(
                batch,
                AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_INVALID,
                "/read_set",
                GovernanceFailureStageV2.PRECONDITION,
            )
        return self._stage_and_publish(image, batch, current_head)

    def _reconcile_existing(
        self,
        image: _DomainImageV2,
        previous: _CommittedEntryV2,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        try:
            _verify_selected_entry_in_image(image, previous)
            is_exact_retry = previous.batch.canonical_bytes() == batch.canonical_bytes()
        except (
            AttributeError,
            TypeError,
            ValueError,
            KeyError,
            IndexError,
        ):
            return _unavailable_attempt(
                batch,
                GovernanceFailureStageV2.RECONCILIATION,
            )
        if not is_exact_retry:
            return _failure_attempt(
                batch,
                AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT,
                "/transition_id",
                GovernanceFailureStageV2.RECONCILIATION,
            )
        injected = self._injected_failure(
            FAILURE_STAGE_AFTER_IDENTITY_RECONCILIATION_V2,
            batch,
            GovernanceFailureStageV2.RECONCILIATION,
        )
        if injected is not None:
            return injected
        try:
            return _committed_attempt(image, previous)
        except (AttributeError, TypeError, ValueError, KeyError, IndexError):
            return _unavailable_attempt(
                batch,
                GovernanceFailureStageV2.RECONCILIATION,
            )

    def _stage_and_publish(
        self,
        image: _DomainImageV2,
        batch: GovernanceCommitBatchV2,
        previous: GovernanceHeadV2,
    ) -> GovernanceCommitAttemptV2:
        state_root, state_records = _next_state(batch)
        head = _successor_head(batch, previous, state_root)
        injected = self._injected_failure(
            FAILURE_STAGE_AFTER_STATE_HEAD_STAGING_V2,
            batch,
            GovernanceFailureStageV2.COMMIT,
        )
        if injected is not None:
            return injected
        staged_trace = GovernanceTraceBatchV2.from_dict(batch.trace_batch.to_dict())
        injected = self._injected_failure(
            FAILURE_STAGE_AFTER_TRACE_STAGING_V2,
            batch,
            GovernanceFailureStageV2.TRACE,
        )
        if injected is not None:
            return injected
        receipt, inclusion = _stage_proof(batch, previous, head, staged_trace)
        injected = self._injected_failure(
            FAILURE_STAGE_AFTER_RECEIPT_INCLUSION_STAGING_V2,
            batch,
            GovernanceFailureStageV2.COMMIT,
        )
        if injected is not None:
            return injected
        entry = _new_committed_entry(
            sequence=len(image.entries) + 1,
            batch=batch,
            receipt=receipt,
            inclusion_proof=inclusion,
        )
        published = _published_image(image, entry, head, state_records)
        self.__domain_images[batch.scope_ref] = published
        injected = self._injected_failure(
            FAILURE_STAGE_AFTER_ATOMIC_PUBLICATION_V2,
            batch,
            GovernanceFailureStageV2.FINALITY,
        )
        return injected or _committed_attempt(published, entry)

    def _injected_failure(
        self,
        hook_stage: str,
        batch: GovernanceCommitBatchV2,
        failure_stage: GovernanceFailureStageV2,
    ) -> GovernanceCommitAttemptV2 | None:
        try:
            self._inject(hook_stage, batch)
        except Exception:
            return _unavailable_attempt(batch, failure_stage)
        return None

    def snapshot_v2(self) -> bytes:
        """Return deterministic private reference bytes for restart testing."""

        with self._lock:
            domains = [
                _domain_snapshot(self.__domain_images[scope_ref])
                for scope_ref in sorted(
                    self.__domain_images,
                    key=lambda item: item.encode(),
                )
            ]
        return _canonical_bytes(
            {
                "schema": _REFERENCE_SNAPSHOT_SCHEMA_V2,
                "state_store_version": GOVERNANCE_STATE_STORE_VERSION_V2,
                "canonical_version": AUTHORITY_CANONICAL_VERSION_V2,
                "domains": domains,
            }
        )

    @classmethod
    def from_snapshot_v2(
        cls,
        value: str | bytes | bytearray,
        *,
        failure_injector: FailureInjectorV2 | None = None,
    ) -> InMemoryGovernanceStateStoreV2:
        """Validate and atomically materialize one private reference snapshot."""

        validated_injector = _validated_failure_injector(failure_injector)
        payload = _loads_snapshot(value)
        root = _exact_object(
            payload,
            {"schema", "state_store_version", "canonical_version", "domains"},
            "reference snapshot",
        )
        if root["schema"] != _REFERENCE_SNAPSHOT_SCHEMA_V2 or (
            root["state_store_version"] != GOVERNANCE_STATE_STORE_VERSION_V2
            or root["canonical_version"] != AUTHORITY_CANONICAL_VERSION_V2
        ):
            raise ValueError("reference snapshot version selection is unsupported")
        domains = root["domains"]
        if type(domains) is not list:
            raise TypeError("reference snapshot domains must be an array")
        parsed = [_restore_domain_snapshot(item) for item in domains]
        scope_keys = [item.domain.scope_ref.encode() for item in parsed]
        if scope_keys != sorted(scope_keys) or len(scope_keys) != len(set(scope_keys)):
            raise ValueError("reference snapshot domains must be unique and sorted")

        restored = cls(item.domain for item in parsed)
        for expected in parsed:
            for entry in expected.entries:
                attempt = restored.atomic_commit_v2(entry.batch)
                if attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED:
                    raise ValueError("reference snapshot commit replay failed")
                assert attempt.committed_transition is not None
                actual = attempt.committed_transition
                if (
                    actual.receipt.canonical_bytes() != entry.receipt.canonical_bytes()
                    or (
                        actual.inclusion_proof.canonical_bytes()
                        != entry.inclusion_proof.canonical_bytes()
                    )
                ):
                    raise ValueError("reference snapshot commit proof is inconsistent")
            actual_image = restored.__domain_images[expected.domain.scope_ref]
            _require_same_domain_image(actual_image, expected)
        restored._failure_injector = validated_injector
        return restored

    def _resolve_domain(self, scope_ref: str) -> _DomainImageV2:
        try:
            return self.__domain_images[scope_ref]
        except KeyError as exc:
            raise KeyError("authority scope is not registered") from exc

    def _verify_image_integrity(self, image: _DomainImageV2) -> None:
        if self._private_image_exposed:
            _verify_domain_image(image)
        else:
            _verify_verified_checkpoint(image)

    def _inject(self, stage: str, batch: GovernanceCommitBatchV2) -> None:
        if self._failure_injector is not None:
            self._failure_injector(stage, batch)


def _committed_attempt(
    image: _DomainImageV2,
    entry: _CommittedEntryV2,
) -> GovernanceCommitAttemptV2:
    committed = _detached_committed(entry)
    _verify_current_projection(
        image,
        entry.batch.stream_ref,
        _head_for(image, entry.batch.stream_ref),
    )
    position = _position_for(image, entry.receipt)
    return GovernanceCommitAttemptV2(
        domain_root=image.domain.domain_root,
        scope_ref=image.domain.scope_ref,
        stream_ref=entry.batch.stream_ref,
        transition_id=entry.batch.transition_id,
        disposition=GovernanceCommitDispositionV2.COMMITTED,
        failure=None,
        committed_transition=committed,
        position_observation=position,
    )


def _history_genesis_root(domain: AuthorityDomainV2) -> str:
    material = b"pheroos-governance-reference-history-v2\x00" + domain.canonical_bytes()
    return "sha256:" + sha256(material).hexdigest()


def _committed_material_root(
    sequence: int,
    batch: GovernanceCommitBatchV2,
    receipt: GovernanceCommitReceiptV2,
    inclusion_proof: GovernanceCommitInclusionProofV2,
) -> str:
    payload = {
        "sequence": sequence,
        "batch": batch.to_dict(),
        "receipt": receipt.to_dict(),
        "inclusion_proof": inclusion_proof.to_dict(),
    }
    return "sha256:" + sha256(_canonical_bytes(payload)).hexdigest()


def _entry_integrity_root(entry: _CommittedEntryV2) -> str:
    return _committed_material_root(
        entry.sequence,
        entry.batch,
        entry.receipt,
        entry.inclusion_proof,
    )


def _new_committed_entry(
    *,
    sequence: int,
    batch: GovernanceCommitBatchV2,
    receipt: GovernanceCommitReceiptV2,
    inclusion_proof: GovernanceCommitInclusionProofV2,
) -> _CommittedEntryV2:
    return _CommittedEntryV2(
        sequence=sequence,
        batch=batch,
        receipt=receipt,
        inclusion_proof=inclusion_proof,
        verified_integrity_root=_committed_material_root(
            sequence,
            batch,
            receipt,
            inclusion_proof,
        ),
    )


def _history_successor_root(parent_root: str, entry_root: str) -> str:
    material = _canonical_bytes(
        {
            "parent_history_root": parent_root,
            "entry_root": entry_root,
        }
    )
    return "sha256:" + sha256(material).hexdigest()


def _checkpoint_for_material(
    *,
    domain: AuthorityDomainV2,
    heads: Mapping[str, GovernanceHeadV2],
    states: Mapping[str, Mapping[str, Any]],
    entries: tuple[_CommittedEntryV2, ...],
    transition_index: Mapping[str, int],
    seal_root: str | None,
    parent_history_root: str | None,
    history_root: str,
) -> _VerifiedDomainCheckpointV2:
    tail = entries[-1] if entries else None
    return _VerifiedDomainCheckpointV2(
        domain_ref=domain,
        heads_ref=heads,
        states_ref=states,
        entries_ref=entries,
        transition_index_ref=transition_index,
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        entry_count=len(entries),
        head_count=len(heads),
        state_count=len(states),
        transition_count=len(transition_index),
        tail_entry_ref=tail,
        tail_entry_root=None if tail is None else _entry_integrity_root(tail),
        parent_history_root=parent_history_root,
        history_root=history_root,
        seal_root=seal_root,
    )


def _verify_verified_checkpoint(image: _DomainImageV2) -> None:
    checkpoint = image.verified_checkpoint
    if type(checkpoint) is not _VerifiedDomainCheckpointV2:
        raise ValueError("authority scope has no verified checkpoint")
    if (
        checkpoint.domain_ref is not image.domain
        or checkpoint.heads_ref is not image.heads
        or checkpoint.states_ref is not image.states
        or checkpoint.entries_ref is not image.entries
        or checkpoint.transition_index_ref is not image.transition_index
        or checkpoint.domain_root != image.domain.domain_root
        or checkpoint.scope_ref != image.domain.scope_ref
        or type(checkpoint.entry_count) is not int
        or checkpoint.entry_count != len(image.entries)
        or type(checkpoint.head_count) is not int
        or checkpoint.head_count != len(image.heads)
        or type(checkpoint.state_count) is not int
        or checkpoint.state_count != len(image.states)
        or type(checkpoint.transition_count) is not int
        or checkpoint.transition_count != len(image.transition_index)
        or checkpoint.seal_root != image.seal_root
    ):
        raise ValueError("authority scope verified checkpoint is inconsistent")
    if image.entries:
        tail = image.entries[-1]
        tail_root = _entry_integrity_root(tail)
        if (
            checkpoint.tail_entry_ref is not tail
            or checkpoint.tail_entry_root != tail_root
            or tail.verified_integrity_root != tail_root
            or checkpoint.parent_history_root is None
            or checkpoint.history_root
            != _history_successor_root(checkpoint.parent_history_root, tail_root)
        ):
            raise ValueError("authority scope history checkpoint is inconsistent")
    elif (
        checkpoint.tail_entry_ref is not None
        or checkpoint.tail_entry_root is not None
        or checkpoint.parent_history_root is not None
        or checkpoint.history_root != _history_genesis_root(image.domain)
    ):
        raise ValueError("empty authority scope checkpoint is inconsistent")


def _successor_checkpoint(
    previous: _DomainImageV2,
    entry: _CommittedEntryV2,
    *,
    heads: Mapping[str, GovernanceHeadV2],
    states: Mapping[str, Mapping[str, Any]],
    entries: tuple[_CommittedEntryV2, ...],
    transition_index: Mapping[str, int],
    seal_root: str | None,
) -> _VerifiedDomainCheckpointV2:
    _verify_verified_checkpoint(previous)
    previous_checkpoint = previous.verified_checkpoint
    assert previous_checkpoint is not None
    entry_root = _entry_integrity_root(entry)
    history_root = _history_successor_root(
        previous_checkpoint.history_root,
        entry_root,
    )
    checkpoint = _checkpoint_for_material(
        domain=previous.domain,
        heads=heads,
        states=states,
        entries=entries,
        transition_index=transition_index,
        seal_root=seal_root,
        parent_history_root=previous_checkpoint.history_root,
        history_root=history_root,
    )
    return checkpoint


def _empty_domain_image(domain: AuthorityDomainV2) -> _DomainImageV2:
    heads: dict[str, GovernanceHeadV2] = {}
    states: dict[str, Mapping[str, Any]] = {}
    entries: tuple[_CommittedEntryV2, ...] = ()
    transition_index: dict[str, int] = {}
    checkpoint = _checkpoint_for_material(
        domain=domain,
        heads=heads,
        states=states,
        entries=entries,
        transition_index=transition_index,
        seal_root=None,
        parent_history_root=None,
        history_root=_history_genesis_root(domain),
    )
    return _DomainImageV2(
        domain=domain,
        heads=heads,
        states=states,
        entries=entries,
        transition_index=transition_index,
        seal_root=None,
        verified_checkpoint=checkpoint,
    )


def _select_commit_domain(
    domains: Mapping[str, _DomainImageV2],
    batch: GovernanceCommitBatchV2,
    *,
    verify_image: Callable[[_DomainImageV2], None],
) -> tuple[_DomainImageV2 | None, GovernanceCommitAttemptV2 | None]:
    image = domains.get(batch.scope_ref)
    if image is None:
        return None, _failure_attempt(
            batch,
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/scope_ref",
            GovernanceFailureStageV2.VALIDATION,
        )
    if image.domain.domain_root != batch.domain_root or (
        image.domain.canonical_bytes() != batch.domain.canonical_bytes()
    ):
        return None, _failure_attempt(
            batch,
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/domain_root",
            GovernanceFailureStageV2.VALIDATION,
        )
    try:
        verify_image(image)
    except (
        AttributeError,
        TypeError,
        ValueError,
        KeyError,
        IndexError,
    ):
        return None, _unavailable_attempt(
            batch,
            GovernanceFailureStageV2.RECONCILIATION,
        )
    return image, None


def _lookup_existing_entry(
    image: _DomainImageV2,
    batch: GovernanceCommitBatchV2,
) -> tuple[_CommittedEntryV2 | None, GovernanceCommitAttemptV2 | None]:
    try:
        sequence = image.transition_index.get(batch.transition_id)
        if sequence is None:
            return None, None
        if type(sequence) is not int or not 1 <= sequence <= len(image.entries):
            raise ValueError("committed transition index is invalid")
        entry = image.entries[sequence - 1]
    except (AttributeError, TypeError, ValueError):
        return None, _unavailable_attempt(
            batch,
            GovernanceFailureStageV2.RECONCILIATION,
        )
    return entry, None


def _failure_attempt(
    batch: GovernanceCommitBatchV2,
    code: AuthorityDiagnosticCodeV2,
    path: str,
    stage: GovernanceFailureStageV2,
) -> GovernanceCommitAttemptV2:
    failure = GovernanceFailureV2(code=code, path=path, stage=stage)
    return GovernanceCommitAttemptV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        disposition=_governance_disposition_for_diagnostic_v2(code),
        failure=failure,
        committed_transition=None,
        position_observation=None,
    )


def _unavailable_attempt(
    batch: GovernanceCommitBatchV2,
    stage: GovernanceFailureStageV2,
) -> GovernanceCommitAttemptV2:
    return _failure_attempt(
        batch,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
        "",
        stage,
    )


def _invalid_view(
    image: _DomainImageV2,
    stream_ref: str,
    transition_id: str,
    expected_receipt_root: str | None,
    observed: GovernanceHeadV2 | None,
    *,
    code: AuthorityDiagnosticCodeV2 = (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    ),
    path: str = "/transition_id",
) -> GovernanceCommitViewV2:
    return GovernanceCommitViewV2(
        domain_root=image.domain.domain_root,
        scope_ref=image.domain.scope_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        expected_receipt_root=expected_receipt_root,
        disposition=GovernanceCommitDispositionV2.INVALID,
        failure=GovernanceFailureV2(
            code=code,
            path=path,
            stage=GovernanceFailureStageV2.LOAD,
        ),
        committed_transition=None,
        position_observation=None,
        observed_revision=None if observed is None else observed.revision,
        observed_head_root=None if observed is None else observed.head_root,
    )


def _head_for(image: _DomainImageV2, stream_ref: str) -> GovernanceHeadV2:
    return image.heads.get(stream_ref) or GovernanceHeadV2.genesis(
        image.domain,
        stream_ref,
    )


def _reliable_observed_head(
    image: _DomainImageV2,
    stream_ref: str,
) -> GovernanceHeadV2 | None:
    try:
        return _clone_head(_head_for(image, stream_ref))
    except (AttributeError, TypeError, ValueError, KeyError):
        return None


def _read_set_matches(
    image: _DomainImageV2,
    batch: GovernanceCommitBatchV2,
) -> bool:
    for expected in batch.read_set.entries:
        head = _head_for(image, expected.stream_ref)
        _verify_current_projection(image, expected.stream_ref, head)
        if head.revision != expected.expected_revision or (
            head.head_root != expected.expected_root
        ):
            return False
    if batch.kind == "seal":
        observed_streams = {
            item
            for item in image.heads
            if item != GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
        }
        declared_streams = {
            item.stream_ref
            for item in batch.read_set.entries
            if item.stream_ref != GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
        }
        if observed_streams != declared_streams:
            return False
    return True


def _would_exceed_stream_bound(
    image: _DomainImageV2,
    batch: GovernanceCommitBatchV2,
) -> bool:
    if batch.kind != "transition" or batch.stream_ref in image.heads:
        return False
    count = sum(
        stream_ref != GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
        for stream_ref in image.heads
    )
    return count >= MAX_GOVERNANCE_NON_LIFECYCLE_STREAMS_V2


def _next_state(
    batch: GovernanceCommitBatchV2,
) -> tuple[str, Mapping[str, Any]]:
    if batch.kind == "transition":
        assert batch.transition is not None
        return (
            batch.transition.state_root,
            _detach_mapping(batch.transition.state_records),
        )
    assert batch.seal is not None
    return batch.seal.seal_root, {"seal": batch.seal.to_dict()}


def _successor_head(
    batch: GovernanceCommitBatchV2,
    previous: GovernanceHeadV2,
    state_root: str,
) -> GovernanceHeadV2:
    return GovernanceHeadV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        revision=previous.revision + 1,
        parent_root=previous.head_root,
        state_root=state_root,
        transition_id=batch.transition_id,
        batch_root=batch.batch_root,
    )


def _stage_proof(
    batch: GovernanceCommitBatchV2,
    previous: GovernanceHeadV2,
    head: GovernanceHeadV2,
    trace: GovernanceTraceBatchV2,
) -> tuple[GovernanceCommitReceiptV2, GovernanceCommitInclusionProofV2]:
    receipt = GovernanceCommitReceiptV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        revision=head.revision,
        parent_root=previous.head_root,
        head_root=head.head_root,
        state_root=head.state_root,
        read_set_root=batch.read_set_root,
        trace_root=trace.trace_root,
        batch_root=batch.batch_root,
    )
    inclusion = GovernanceCommitInclusionProofV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        revision=head.revision,
        batch_root=batch.batch_root,
        receipt_root=receipt.receipt_root,
        head_root=head.head_root,
    )
    return receipt, inclusion


def _published_image(
    image: _DomainImageV2,
    entry: _CommittedEntryV2,
    head: GovernanceHeadV2,
    state_records: Mapping[str, Any],
) -> _DomainImageV2:
    heads = dict(image.heads)
    heads[entry.batch.stream_ref] = head
    states = dict(image.states)
    states[entry.batch.stream_ref] = _detach_mapping(state_records)
    transition_index = dict(image.transition_index)
    transition_index[entry.batch.transition_id] = entry.sequence
    seal_root = image.seal_root
    if entry.batch.kind == "seal":
        assert entry.batch.seal is not None
        seal_root = entry.batch.seal.seal_root
    entries = (*image.entries, entry)
    checkpoint = _successor_checkpoint(
        image,
        entry,
        heads=heads,
        states=states,
        entries=entries,
        transition_index=transition_index,
        seal_root=seal_root,
    )
    return _DomainImageV2(
        domain=image.domain,
        heads=heads,
        states=states,
        entries=entries,
        transition_index=transition_index,
        seal_root=seal_root,
        verified_checkpoint=checkpoint,
    )


def _detached_committed(entry: _CommittedEntryV2) -> GovernanceCommittedTransitionV2:
    try:
        GovernanceTraceBatchV2.from_dict(entry.batch.trace_batch.to_dict())
    except (TypeError, ValueError) as exc:
        raise _TraceLineageInvalidV2 from exc
    return GovernanceCommittedTransitionV2(
        batch=GovernanceCommitBatchV2.from_dict(entry.batch.to_dict()),
        receipt=GovernanceCommitReceiptV2.from_dict(entry.receipt.to_dict()),
        inclusion_proof=GovernanceCommitInclusionProofV2.from_dict(
            entry.inclusion_proof.to_dict()
        ),
    )


def _position_for(
    image: _DomainImageV2,
    receipt: GovernanceCommitReceiptV2,
) -> GovernanceCommitPositionObservationV2:
    observed = _head_for(image, receipt.stream_ref)
    if image.seal_root is not None:
        position = GovernanceCommitPositionV2.SEALED
        seal_root = image.seal_root
    elif observed.head_root == receipt.head_root:
        position = GovernanceCommitPositionV2.CURRENT
        seal_root = None
    else:
        position = GovernanceCommitPositionV2.SUPERSEDED
        seal_root = None
    return GovernanceCommitPositionObservationV2(
        domain_root=receipt.domain_root,
        scope_ref=receipt.scope_ref,
        stream_ref=receipt.stream_ref,
        transition_id=receipt.transition_id,
        receipt_root=receipt.receipt_root,
        observed_revision=observed.revision,
        observed_head_root=observed.head_root,
        position=position,
        seal_root=seal_root,
    )


def _verify_selected_entry_in_image(
    image: _DomainImageV2,
    selected: _CommittedEntryV2,
) -> None:
    if (
        type(selected.sequence) is not int
        or not 1 <= selected.sequence <= len(image.entries)
        or (image.entries[selected.sequence - 1] is not selected)
    ):
        raise ValueError("committed entry sequence is invalid")
    if image.transition_index.get(selected.batch.transition_id) != selected.sequence:
        raise ValueError("committed transition index is invalid")
    integrity_root = _entry_integrity_root(selected)
    if selected.verified_integrity_root != integrity_root:
        raise ValueError("committed entry integrity witness is invalid")


def _verify_domain_image(image: _DomainImageV2) -> None:
    """Reject any scope image that is not one closed committed projection."""

    domain = _clone_domain(image.domain)
    _verify_global_sequence_and_index(image)
    if not isinstance(image.heads, Mapping) or not isinstance(
        image.states,
        Mapping,
    ):
        raise TypeError("authority scope projections must be mappings")
    (
        expected_heads,
        expected_states,
        replayed_seal_root,
        parent_history_root,
        history_root,
    ) = _replay_domain_history(domain, image.entries)
    _verify_replayed_projections(
        image,
        domain,
        expected_heads,
        expected_states,
    )
    _verify_replayed_seal_root(image, replayed_seal_root)
    _verify_verified_checkpoint(image)
    checkpoint = image.verified_checkpoint
    assert checkpoint is not None
    if checkpoint.parent_history_root != parent_history_root or (
        checkpoint.history_root != history_root
    ):
        raise ValueError("authority scope historical checkpoint is inconsistent")


def _replay_domain_history(
    domain: AuthorityDomainV2,
    entries: tuple[_CommittedEntryV2, ...],
) -> tuple[
    dict[str, GovernanceHeadV2],
    dict[str, Mapping[str, Any]],
    str | None,
    str | None,
    str,
]:
    """Replay committed entries once in their declared global sequence."""

    expected_heads: dict[str, GovernanceHeadV2] = {}
    expected_states: dict[str, Mapping[str, Any]] = {}
    replayed_seal_root: str | None = None
    history_root = _history_genesis_root(domain)
    parent_history_root: str | None = None
    for entry in entries:
        committed = _detached_committed(entry)
        if entry.verified_integrity_root != _entry_integrity_root(entry):
            raise ValueError("committed entry integrity witness is invalid")
        batch = committed.batch
        if batch.domain.canonical_bytes() != domain.canonical_bytes():
            raise ValueError("committed transition domain is inconsistent")
        if replayed_seal_root is not None:
            raise ValueError("sealed domain contains a later commit")
        _verify_replayed_read_set(domain, expected_heads, batch)
        if (
            batch.kind == "transition"
            and batch.stream_ref not in expected_heads
            and len(expected_heads) >= MAX_GOVERNANCE_NON_LIFECYCLE_STREAMS_V2
        ):
            raise ValueError("committed scope exceeds its stream bound")
        previous = expected_heads.get(batch.stream_ref)
        if previous is None:
            previous = GovernanceHeadV2.genesis(domain, batch.stream_ref)
        receipt = committed.receipt
        expected_heads[batch.stream_ref] = GovernanceHeadV2(
            domain_root=receipt.domain_root,
            scope_ref=receipt.scope_ref,
            stream_ref=receipt.stream_ref,
            revision=receipt.revision,
            parent_root=receipt.parent_root,
            state_root=receipt.state_root,
            transition_id=receipt.transition_id,
            batch_root=receipt.batch_root,
            head_root=receipt.head_root,
        )
        if batch.kind == "transition":
            assert batch.transition is not None
            expected_states[batch.stream_ref] = batch.transition.state_records
        else:
            assert batch.seal is not None
            expected_states[batch.stream_ref] = {"seal": batch.seal.to_dict()}
            replayed_seal_root = batch.seal.seal_root
        parent_history_root = history_root
        history_root = _history_successor_root(
            history_root,
            _entry_integrity_root(entry),
        )
    return (
        expected_heads,
        expected_states,
        replayed_seal_root,
        parent_history_root,
        history_root,
    )


def _verify_replayed_projections(
    image: _DomainImageV2,
    domain: AuthorityDomainV2,
    expected_heads: Mapping[str, GovernanceHeadV2],
    expected_states: Mapping[str, Mapping[str, Any]],
) -> None:
    if set(image.heads) != set(expected_heads) or set(image.states) != set(
        expected_heads
    ):
        raise ValueError("authority scope projections are incomplete")
    for stream_ref, expected in expected_heads.items():
        actual = image.heads[stream_ref]
        if type(actual) is not GovernanceHeadV2 or (
            actual.canonical_bytes() != expected.canonical_bytes()
        ):
            raise ValueError("current authority head projection is inconsistent")
        actual_state = image.states[stream_ref]
        actual_state_root = governance_authority_state_root_v2(
            domain.scope_ref,
            stream_ref,
            actual_state,
        )
        expected_state_root = governance_authority_state_root_v2(
            domain.scope_ref,
            stream_ref,
            expected_states[stream_ref],
        )
        if actual_state_root != expected_state_root or (
            stream_ref != GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
            and actual_state_root != expected.state_root
        ):
            raise ValueError("current authority state projection is inconsistent")


def _verify_replayed_seal_root(
    image: _DomainImageV2,
    replayed_seal_root: str | None,
) -> None:
    if replayed_seal_root is None:
        if image.seal_root is not None:
            raise ValueError("open domain contains a seal root")
    elif type(image.seal_root) is not str or image.seal_root != replayed_seal_root:
        raise ValueError("sealed domain root is inconsistent")


def _verify_replayed_read_set(
    domain: AuthorityDomainV2,
    replayed_heads: Mapping[str, GovernanceHeadV2],
    batch: GovernanceCommitBatchV2,
) -> None:
    """Verify one historical read-set against heads before its publication."""

    for precondition in batch.read_set.entries:
        observed = replayed_heads.get(precondition.stream_ref)
        if observed is None:
            observed = GovernanceHeadV2.genesis(domain, precondition.stream_ref)
        if observed.revision != precondition.expected_revision or (
            observed.head_root != precondition.expected_root
        ):
            raise ValueError("committed historical read-set is inconsistent")
    if batch.kind == "seal":
        declared_streams = {
            item.stream_ref
            for item in batch.read_set.entries
            if item.stream_ref != GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
        }
        observed_streams = {
            stream_ref
            for stream_ref in replayed_heads
            if stream_ref != GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
        }
        if declared_streams != observed_streams:
            raise ValueError("committed seal read-set is incomplete")


def _verify_current_projection(
    image: _DomainImageV2,
    stream_ref: str,
    head: GovernanceHeadV2,
) -> None:
    if type(head) is not GovernanceHeadV2:
        raise TypeError("current authority head projection is invalid")
    if head.revision == 0:
        if stream_ref in image.heads or stream_ref in image.states:
            raise ValueError("genesis stream has persisted authority material")
        return
    sequence = image.transition_index.get(head.transition_id)
    if type(sequence) is not int or not 1 <= sequence <= len(image.entries):
        raise ValueError("current stream projection has no included head")
    current_entry = image.entries[sequence - 1]
    if (
        current_entry.batch.stream_ref != stream_ref
        or current_entry.receipt.head_root != head.head_root
    ):
        raise ValueError("current stream projection has no included head")
    _verify_selected_entry_in_image(image, current_entry)
    expected_state = _current_entry_state_projection(current_entry)
    _verify_current_state_projection(
        image, stream_ref, head, current_entry, expected_state
    )


def _current_entry_state_projection(
    entry: _CommittedEntryV2,
) -> Mapping[str, Any]:
    """Return the exact state material selected by one verified current entry."""

    if entry.batch.kind == "seal":
        seal = entry.batch.seal
        if seal is None:
            raise ValueError("lifecycle projection has no seal")
        return {"seal": seal.to_dict()}
    transition = entry.batch.transition
    if transition is None:
        raise ValueError("authority projection has no state transition")
    return transition.state_records


def _verify_current_state_projection(
    image: _DomainImageV2,
    stream_ref: str,
    head: GovernanceHeadV2,
    current_entry: _CommittedEntryV2,
    expected_state: Mapping[str, Any],
) -> None:
    """Match the stored current state to its entry and selected head."""

    actual_state = image.states.get(stream_ref)
    if actual_state is None:
        raise ValueError("current authority state projection is inconsistent")
    actual_projection_root = governance_authority_state_root_v2(
        image.domain.scope_ref,
        stream_ref,
        actual_state,
    )
    expected_projection_root = governance_authority_state_root_v2(
        image.domain.scope_ref,
        stream_ref,
        expected_state,
    )
    if actual_projection_root != expected_projection_root or (
        current_entry.batch.kind != "seal" and actual_projection_root != head.state_root
    ):
        raise ValueError("current authority state projection is inconsistent")


def _verify_global_sequence_and_index(image: _DomainImageV2) -> None:
    expected_index: dict[str, int] = {}
    for expected_sequence, entry in enumerate(image.entries, start=1):
        if (
            type(entry.sequence) is not int
            or entry.sequence != expected_sequence
            or (entry.batch.transition_id in expected_index)
        ):
            raise ValueError("committed global sequence is inconsistent")
        expected_index[entry.batch.transition_id] = expected_sequence
    if not isinstance(image.transition_index, Mapping) or len(
        image.transition_index
    ) != len(expected_index):
        raise ValueError("committed transition index is inconsistent")
    if any(
        type(transition_id) is not str
        or type(sequence) is not int
        or expected_index.get(transition_id) != sequence
        for transition_id, sequence in image.transition_index.items()
    ):
        raise ValueError("committed transition index is inconsistent")


def _domain_snapshot(image: _DomainImageV2) -> dict[str, object]:
    sorted_streams = sorted(image.heads, key=lambda item: item.encode())
    return {
        "domain": image.domain.to_dict(),
        "heads": [image.heads[item].to_dict() for item in sorted_streams],
        "states": [
            {
                "stream_ref": item,
                "state_records": _detach_mapping(image.states[item]),
            }
            for item in sorted_streams
        ],
        "commits": [
            {
                "sequence": entry.sequence,
                "batch": entry.batch.to_dict(),
                "receipt": entry.receipt.to_dict(),
                "inclusion_proof": entry.inclusion_proof.to_dict(),
            }
            for entry in image.entries
        ],
        "transition_index": [
            {"transition_id": transition_id, "sequence": sequence}
            for transition_id, sequence in sorted(
                image.transition_index.items(),
                key=lambda item: item[0].encode(),
            )
        ],
        "seal_root": image.seal_root,
    }


def _restore_domain_snapshot(payload: object) -> _DomainImageV2:
    value = _exact_object(
        payload,
        {
            "domain",
            "heads",
            "states",
            "commits",
            "transition_index",
            "seal_root",
        },
        "reference domain snapshot",
    )
    domain = AuthorityDomainV2.from_dict(value["domain"])
    heads = _restore_snapshot_heads(value["heads"], domain)
    states = _restore_snapshot_states(value["states"], heads)
    entries = _restore_snapshot_entries(value["commits"])
    transition_index = _restore_snapshot_index(
        value["transition_index"],
        entries,
    )
    seal_root = value["seal_root"]
    if seal_root is not None and type(seal_root) is not str:
        raise TypeError("snapshot seal_root must be a root or null")
    return _DomainImageV2(
        domain=domain,
        heads=heads,
        states=states,
        entries=entries,
        transition_index=transition_index,
        seal_root=seal_root,
        verified_checkpoint=None,
    )


def _restore_snapshot_heads(
    payload: object,
    domain: AuthorityDomainV2,
) -> dict[str, GovernanceHeadV2]:
    heads: dict[str, GovernanceHeadV2] = {}
    for item in _require_array(payload, "snapshot heads"):
        head = GovernanceHeadV2.from_dict(item)
        if head.scope_ref != domain.scope_ref or head.domain_root != domain.domain_root:
            raise ValueError("snapshot head crosses authority domain")
        if head.stream_ref in heads:
            raise ValueError("snapshot head stream is duplicated")
        heads[head.stream_ref] = head
    if list(heads) != sorted(heads, key=lambda item: item.encode()):
        raise ValueError("snapshot heads must be UTF-8 sorted")
    return heads


def _restore_snapshot_states(
    payload: object,
    heads: Mapping[str, GovernanceHeadV2],
) -> dict[str, Mapping[str, Any]]:
    states: dict[str, Mapping[str, Any]] = {}
    for item in _require_array(payload, "snapshot states"):
        state = _exact_object(
            item,
            {"stream_ref", "state_records"},
            "snapshot state",
        )
        stream_ref = _require_ref(state["stream_ref"], "snapshot stream_ref")
        if stream_ref in states:
            raise ValueError("snapshot state stream is duplicated")
        states[stream_ref] = _detach_mapping(state["state_records"])
    if list(states) != sorted(states, key=lambda item: item.encode()) or (
        set(states) != set(heads)
    ):
        raise ValueError("snapshot states must exactly match sorted heads")
    return states


def _restore_snapshot_entries(payload: object) -> tuple[_CommittedEntryV2, ...]:
    entries: list[_CommittedEntryV2] = []
    for expected_sequence, item in enumerate(
        _require_array(payload, "snapshot commits"),
        start=1,
    ):
        commit = _exact_object(
            item,
            {"sequence", "batch", "receipt", "inclusion_proof"},
            "snapshot commit",
        )
        if type(commit["sequence"]) is not int or (
            commit["sequence"] != expected_sequence
        ):
            raise ValueError("snapshot commit sequence must be gap-free")
        entries.append(
            _new_committed_entry(
                sequence=expected_sequence,
                batch=GovernanceCommitBatchV2.from_dict(commit["batch"]),
                receipt=GovernanceCommitReceiptV2.from_dict(commit["receipt"]),
                inclusion_proof=GovernanceCommitInclusionProofV2.from_dict(
                    commit["inclusion_proof"]
                ),
            )
        )
    return tuple(entries)


def _restore_snapshot_index(
    payload: object,
    entries: tuple[_CommittedEntryV2, ...],
) -> dict[str, int]:
    transition_index: dict[str, int] = {}
    for item in _require_array(payload, "snapshot transition index"):
        indexed = _exact_object(
            item,
            {"transition_id", "sequence"},
            "snapshot transition index entry",
        )
        transition_id = _require_ref(
            indexed["transition_id"],
            "snapshot transition_id",
        )
        sequence = indexed["sequence"]
        if type(sequence) is not int or not 1 <= sequence <= len(entries):
            raise ValueError("snapshot transition index sequence is invalid")
        if transition_id in transition_index:
            raise ValueError("snapshot transition index identity is duplicated")
        transition_index[transition_id] = sequence
    if list(transition_index) != sorted(
        transition_index,
        key=lambda item: item.encode(),
    ):
        raise ValueError("snapshot transition index must be UTF-8 sorted")
    expected_index: dict[str, int] = {
        entry.batch.transition_id: entry.sequence for entry in entries
    }
    if transition_index != dict(
        sorted(expected_index.items(), key=lambda item: item[0].encode())
    ):
        raise ValueError("snapshot transition index does not match commit sequence")
    return transition_index


def _require_same_domain_image(
    actual: _DomainImageV2,
    expected: _DomainImageV2,
) -> None:
    if _canonical_bytes(_domain_snapshot(actual)) != _canonical_bytes(
        _domain_snapshot(expected)
    ):
        raise ValueError("reference snapshot derived image is inconsistent")


def _clone_domain(value: AuthorityDomainV2) -> AuthorityDomainV2:
    if type(value) is not AuthorityDomainV2:
        raise TypeError("registered authority domain must be AuthorityDomainV2")
    return AuthorityDomainV2.from_dict(value.to_dict())


def _clone_head(value: GovernanceHeadV2) -> GovernanceHeadV2:
    return GovernanceHeadV2.from_dict(value.to_dict())


def _detach_mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("authority state must be a mapping")
    return {str(key): _detach_json(item) for key, item in value.items()}


def _detach_json(value: object) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _detach_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_detach_json(item) for item in value]
    return value


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _loads_snapshot(value: object) -> object:
    if type(value) is str:
        text = value
    elif isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        if raw.startswith(b"\xef\xbb\xbf"):
            raise ValueError("reference snapshot must not contain a BOM")
        text = raw.decode("utf-8")
    else:
        raise TypeError("reference snapshot must be text or UTF-8 bytes")
    if text.startswith("\ufeff"):
        raise ValueError("reference snapshot must not contain a BOM")
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_number,
        parse_float=_reject_number,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("reference snapshot contains duplicate object keys")
        value[key] = item
    return value


def _reject_number(_value: str) -> NoReturn:
    raise ValueError("reference snapshot does not permit floating-point numbers")


def _exact_object(
    value: object,
    fields: set[str],
    label: str,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise TypeError(f"{label} must be an exact object")
    if set(value) != fields:
        raise ValueError(f"{label} fields are invalid")
    return value


def _require_array(value: object, label: str) -> list[object]:
    if type(value) is not list:
        raise TypeError(f"{label} must be an array")
    return value


def _require_ref(value: object, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be a canonical non-blank string")
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError(f"{label} must already use Unicode NFC")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{label} must encode as UTF-8") from exc
    return value


__all__ = [
    "FAILURE_STAGE_AFTER_ATOMIC_PUBLICATION_V2",
    "FAILURE_STAGE_AFTER_IDENTITY_RECONCILIATION_V2",
    "FAILURE_STAGE_AFTER_READ_SET_VALIDATION_V2",
    "FAILURE_STAGE_AFTER_RECEIPT_INCLUSION_STAGING_V2",
    "FAILURE_STAGE_AFTER_STATE_HEAD_STAGING_V2",
    "FAILURE_STAGE_AFTER_TRACE_STAGING_V2",
    "FAILURE_STAGE_BEFORE_VALIDATION_V2",
    "InMemoryGovernanceStateStoreV2",
]
