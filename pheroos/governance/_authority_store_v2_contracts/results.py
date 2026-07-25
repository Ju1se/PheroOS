"""Typed commit results and structural StateStore v2 protocols."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, ClassVar, Protocol, runtime_checkable

from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    AuthorityDiagnosticCodeV2,
)

from pheroos.governance._authority_store_v2_contracts.batch import (
    GovernanceCommitBatchV2,
)
from pheroos.governance._authority_store_v2_contracts.domain import GovernanceHeadV2
from pheroos.governance._authority_store_v2_contracts.foundation import (
    GOVERNANCE_COMMIT_ATTEMPT_SCHEMA_V2,
    GOVERNANCE_COMMIT_VIEW_SCHEMA_V2,
    GOVERNANCE_FAILURE_SCHEMA_V2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceFailureStageV2,
    _CanonicalRootRecordV2,
    _diagnostic_from_wire,
    _disposition_from_wire,
    _exact_object,
    _failure_stage_from_wire,
    _install_root,
    _require_exact_version,
    _require_json_pointer,
    _require_revision,
    _require_root,
    _require_text,
)
from pheroos.governance._authority_store_v2_contracts.receipt import (
    GovernanceCommitPositionObservationV2,
    GovernanceCommittedTransitionV2,
)


@dataclass(frozen=True, slots=True)
class GovernanceFailureV2(_CanonicalRootRecordV2):
    """Typed failure dispatch; human-readable exception text is not an ABI."""

    code: AuthorityDiagnosticCodeV2
    path: str
    stage: GovernanceFailureStageV2
    schema: str = GOVERNANCE_FAILURE_SCHEMA_V2
    failure_root: str = ""

    _root_field: ClassVar[str] = "failure_root"

    def __post_init__(self) -> None:
        if type(self.code) is not AuthorityDiagnosticCodeV2:
            raise TypeError("governance failure code must use Protocol owner enum")
        _require_json_pointer(self.path)
        if type(self.stage) is not GovernanceFailureStageV2:
            raise TypeError("governance failure stage is invalid")
        _require_exact_version(
            self.schema,
            GOVERNANCE_FAILURE_SCHEMA_V2,
            "governance failure schema",
        )
        _install_root(
            self,
            "failure_root",
            self.failure_root,
            "failure",
            self._root_body(),
        )

    def _root_body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "code": self.code.value,
            "path": self.path,
            "stage": self.stage.value,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._root_body(), "failure_root": self.failure_root}

    @classmethod
    def from_dict(cls, payload: object) -> GovernanceFailureV2:
        value = _exact_object(
            payload,
            frozenset({"schema", "code", "path", "stage", "failure_root"}),
            "governance failure v2",
        )
        return cls(
            code=_diagnostic_from_wire(value["code"]),
            path=value["path"],
            stage=_failure_stage_from_wire(value["stage"]),
            schema=value["schema"],
            failure_root=value["failure_root"],
        )


_DIAGNOSTIC_DISPOSITIONS = MappingProxyType(
    {
        AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED: GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED: GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH: GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH: GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED: GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH: GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED: GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED: GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED: GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_INVALID: GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE: GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT: GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED: GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE: GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID: GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_ACTION_NOT_AUTHORIZED: GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_TRACE_LINEAGE_INVALID: GovernanceCommitDispositionV2.INVALID,
    }
)


def _governance_disposition_for_diagnostic_v2(
    code: AuthorityDiagnosticCodeV2,
) -> GovernanceCommitDispositionV2:
    """Return the one Governance-owned mapping consumed by Store internals."""

    if type(code) is not AuthorityDiagnosticCodeV2:
        raise TypeError("diagnostic must use the Protocol-owned v2 enum")
    return _DIAGNOSTIC_DISPOSITIONS[code]


@dataclass(frozen=True, slots=True)
class GovernanceCommitAttemptV2(_CanonicalRootRecordV2):
    """Total atomic-commit result with mutually exclusive authority artifacts."""

    domain_root: str
    scope_ref: str
    stream_ref: str
    transition_id: str
    disposition: GovernanceCommitDispositionV2
    failure: GovernanceFailureV2 | None
    committed_transition: GovernanceCommittedTransitionV2 | None
    position_observation: GovernanceCommitPositionObservationV2 | None
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    schema: str = GOVERNANCE_COMMIT_ATTEMPT_SCHEMA_V2
    attempt_root: str = ""

    _root_field: ClassVar[str] = "attempt_root"

    def __post_init__(self) -> None:
        _snapshot_result_nested(self, "governance commit attempt")
        _validate_result_binding(
            canonical_version=self.canonical_version,
            domain_root=self.domain_root,
            scope_ref=self.scope_ref,
            stream_ref=self.stream_ref,
            transition_id=self.transition_id,
            disposition=self.disposition,
            failure=self.failure,
            committed_transition=self.committed_transition,
            position_observation=self.position_observation,
            label="governance commit attempt",
        )
        _require_exact_version(
            self.schema,
            GOVERNANCE_COMMIT_ATTEMPT_SCHEMA_V2,
            "governance commit attempt schema",
        )
        _install_root(
            self,
            "attempt_root",
            self.attempt_root,
            "attempt",
            self._root_body(),
        )

    def _root_body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "stream_ref": self.stream_ref,
            "transition_id": self.transition_id,
            "disposition": self.disposition.value,
            "failure": None if self.failure is None else self.failure.to_dict(),
            "committed_transition": (
                None
                if self.committed_transition is None
                else self.committed_transition.to_dict()
            ),
            "position_observation": (
                None
                if self.position_observation is None
                else self.position_observation.to_dict()
            ),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._root_body(), "attempt_root": self.attempt_root}

    @classmethod
    def from_dict(cls, payload: object) -> GovernanceCommitAttemptV2:
        value = _exact_object(
            payload,
            frozenset(
                {
                    "schema",
                    "canonical_version",
                    "domain_root",
                    "scope_ref",
                    "stream_ref",
                    "transition_id",
                    "disposition",
                    "failure",
                    "committed_transition",
                    "position_observation",
                    "attempt_root",
                }
            ),
            "governance commit attempt v2",
        )
        return cls(
            domain_root=value["domain_root"],
            scope_ref=value["scope_ref"],
            stream_ref=value["stream_ref"],
            transition_id=value["transition_id"],
            disposition=_disposition_from_wire(value["disposition"]),
            failure=_optional_failure(value["failure"]),
            committed_transition=_optional_committed_transition(
                value["committed_transition"]
            ),
            position_observation=_optional_position(value["position_observation"]),
            canonical_version=value["canonical_version"],
            schema=value["schema"],
            attempt_root=value["attempt_root"],
        )


@dataclass(frozen=True, slots=True)
class GovernanceCommitViewV2(_CanonicalRootRecordV2):
    """One total, consistent historical commit lookup and position snapshot."""

    domain_root: str
    scope_ref: str
    stream_ref: str
    transition_id: str
    expected_receipt_root: str | None
    disposition: GovernanceCommitDispositionV2
    failure: GovernanceFailureV2 | None
    committed_transition: GovernanceCommittedTransitionV2 | None
    position_observation: GovernanceCommitPositionObservationV2 | None
    observed_revision: int | None
    observed_head_root: str | None
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    schema: str = GOVERNANCE_COMMIT_VIEW_SCHEMA_V2
    view_root: str = ""

    _root_field: ClassVar[str] = "view_root"

    def __post_init__(self) -> None:
        _snapshot_result_nested(self, "governance commit view")
        if self.disposition not in {
            GovernanceCommitDispositionV2.COMMITTED,
            GovernanceCommitDispositionV2.INVALID,
            GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        }:
            raise ValueError("governance commit view disposition is unreachable")
        _validate_result_binding(
            canonical_version=self.canonical_version,
            domain_root=self.domain_root,
            scope_ref=self.scope_ref,
            stream_ref=self.stream_ref,
            transition_id=self.transition_id,
            disposition=self.disposition,
            failure=self.failure,
            committed_transition=self.committed_transition,
            position_observation=self.position_observation,
            label="governance commit view",
        )
        _require_exact_version(
            self.schema,
            GOVERNANCE_COMMIT_VIEW_SCHEMA_V2,
            "governance commit view schema",
        )
        if self.expected_receipt_root is not None:
            _require_root(
                self.expected_receipt_root,
                "governance commit view expected_receipt_root",
            )
        if (self.observed_revision is None) != (self.observed_head_root is None):
            raise ValueError(
                "governance commit view observed revision/root must be both present or null"
            )
        if self.observed_revision is not None:
            _require_revision(
                self.observed_revision,
                "governance commit view observed_revision",
            )
            _require_root(
                self.observed_head_root,
                "governance commit view observed_head_root",
            )
        if self.disposition is GovernanceCommitDispositionV2.COMMITTED:
            assert self.committed_transition is not None
            assert self.position_observation is not None
            if (
                self.observed_revision != self.position_observation.observed_revision
                or (
                    self.observed_head_root
                    != self.position_observation.observed_head_root
                )
            ):
                raise ValueError("committed view observed head is mismatched")
            if self.expected_receipt_root is not None and (
                self.expected_receipt_root
                != self.committed_transition.receipt.receipt_root
            ):
                raise ValueError("committed view expected receipt is mismatched")
        elif (
            self.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
            and (
                self.observed_revision is not None
                or self.observed_head_root is not None
            )
        ):
            raise ValueError(
                "unavailable commit view cannot fabricate an observed head"
            )
        _install_root(
            self,
            "view_root",
            self.view_root,
            "view",
            self._root_body(),
        )

    def _root_body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "stream_ref": self.stream_ref,
            "transition_id": self.transition_id,
            "expected_receipt_root": self.expected_receipt_root,
            "disposition": self.disposition.value,
            "failure": None if self.failure is None else self.failure.to_dict(),
            "committed_transition": (
                None
                if self.committed_transition is None
                else self.committed_transition.to_dict()
            ),
            "position_observation": (
                None
                if self.position_observation is None
                else self.position_observation.to_dict()
            ),
            "observed_revision": self.observed_revision,
            "observed_head_root": self.observed_head_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._root_body(), "view_root": self.view_root}

    @classmethod
    def from_dict(cls, payload: object) -> GovernanceCommitViewV2:
        value = _exact_object(
            payload,
            frozenset(
                {
                    "schema",
                    "canonical_version",
                    "domain_root",
                    "scope_ref",
                    "stream_ref",
                    "transition_id",
                    "expected_receipt_root",
                    "disposition",
                    "failure",
                    "committed_transition",
                    "position_observation",
                    "observed_revision",
                    "observed_head_root",
                    "view_root",
                }
            ),
            "governance commit view v2",
        )
        return cls(
            domain_root=value["domain_root"],
            scope_ref=value["scope_ref"],
            stream_ref=value["stream_ref"],
            transition_id=value["transition_id"],
            expected_receipt_root=value["expected_receipt_root"],
            disposition=_disposition_from_wire(value["disposition"]),
            failure=_optional_failure(value["failure"]),
            committed_transition=_optional_committed_transition(
                value["committed_transition"]
            ),
            position_observation=_optional_position(value["position_observation"]),
            observed_revision=value["observed_revision"],
            observed_head_root=value["observed_head_root"],
            canonical_version=value["canonical_version"],
            schema=value["schema"],
            view_root=value["view_root"],
        )


@runtime_checkable
class GovernanceStateReaderV2(Protocol):
    """Consistent, detached reads from a v2 authority StateStore."""

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2: ...

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]: ...

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2: ...


@runtime_checkable
class GovernanceStateWriterV2(Protocol):
    """Single total-operation write boundary for v2 authority state."""

    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2: ...


@runtime_checkable
class GovernanceStateStoreV2(
    GovernanceStateReaderV2,
    GovernanceStateWriterV2,
    Protocol,
):
    """Combined exact-version reader/writer contract; no storage policy."""

    @property
    def state_store_version(self) -> str: ...


def _snapshot_result_nested(
    result: GovernanceCommitAttemptV2 | GovernanceCommitViewV2,
    label: str,
) -> None:
    if result.failure is not None:
        if type(result.failure) is not GovernanceFailureV2:
            raise TypeError(f"{label} failure is invalid")
        object.__setattr__(
            result,
            "failure",
            GovernanceFailureV2.from_dict(result.failure.to_dict()),
        )
    if result.committed_transition is not None:
        if type(result.committed_transition) is not GovernanceCommittedTransitionV2:
            raise TypeError(f"{label} transition is invalid")
        object.__setattr__(
            result,
            "committed_transition",
            GovernanceCommittedTransitionV2.from_dict(
                result.committed_transition.to_dict()
            ),
        )
    if result.position_observation is not None:
        if (
            type(result.position_observation)
            is not GovernanceCommitPositionObservationV2
        ):
            raise TypeError(f"{label} position is invalid")
        object.__setattr__(
            result,
            "position_observation",
            GovernanceCommitPositionObservationV2.from_dict(
                result.position_observation.to_dict()
            ),
        )


def _validate_result_binding(
    *,
    canonical_version: str,
    domain_root: str,
    scope_ref: str,
    stream_ref: str,
    transition_id: str,
    disposition: GovernanceCommitDispositionV2,
    failure: GovernanceFailureV2 | None,
    committed_transition: GovernanceCommittedTransitionV2 | None,
    position_observation: GovernanceCommitPositionObservationV2 | None,
    label: str,
) -> None:
    _require_exact_version(
        canonical_version,
        AUTHORITY_CANONICAL_VERSION_V2,
        f"{label} canonical_version",
    )
    _require_root(domain_root, f"{label} domain_root")
    _require_text(scope_ref, f"{label} scope_ref")
    _require_text(stream_ref, f"{label} stream_ref")
    _require_text(transition_id, f"{label} transition_id")
    if type(disposition) is not GovernanceCommitDispositionV2:
        raise TypeError(f"{label} disposition is invalid")
    if disposition is GovernanceCommitDispositionV2.COMMITTED:
        if failure is not None:
            raise ValueError(f"{label} committed result cannot carry failure")
        if type(committed_transition) is not GovernanceCommittedTransitionV2 or (
            type(position_observation) is not GovernanceCommitPositionObservationV2
        ):
            raise ValueError(f"{label} committed result requires verified artifacts")
        _validate_committed_result_position(
            domain_root=domain_root,
            scope_ref=scope_ref,
            stream_ref=stream_ref,
            transition_id=transition_id,
            committed=committed_transition,
            position=position_observation,
            label=label,
        )
        return
    if type(failure) is not GovernanceFailureV2:
        raise ValueError(f"{label} non-committed result requires typed failure")
    if committed_transition is not None or position_observation is not None:
        raise ValueError(f"{label} non-committed result cannot carry authority")
    expected = _governance_disposition_for_diagnostic_v2(failure.code)
    if disposition is not expected:
        raise ValueError(f"{label} diagnostic/disposition mapping is mismatched")


def _validate_committed_result_position(
    *,
    domain_root: str,
    scope_ref: str,
    stream_ref: str,
    transition_id: str,
    committed: GovernanceCommittedTransitionV2,
    position: GovernanceCommitPositionObservationV2,
    label: str,
) -> None:
    receipt = committed.receipt
    binding = (domain_root, scope_ref, stream_ref, transition_id)
    if binding != (
        committed.batch.domain_root,
        committed.batch.scope_ref,
        committed.batch.stream_ref,
        committed.batch.transition_id,
    ) or binding != (
        position.domain_root,
        position.scope_ref,
        position.stream_ref,
        position.transition_id,
    ):
        raise ValueError(f"{label} committed artifacts cross authority binding")
    if position.receipt_root != receipt.receipt_root:
        raise ValueError(f"{label} position does not bind committed receipt")
    if position.position is GovernanceCommitPositionV2.CURRENT:
        if (
            position.observed_revision != receipt.revision
            or position.observed_head_root != receipt.head_root
        ):
            raise ValueError(f"{label} current position is not the committed head")
    elif position.position is GovernanceCommitPositionV2.SUPERSEDED:
        if position.observed_revision <= receipt.revision:
            raise ValueError(f"{label} superseded position requires a successor")
    elif position.observed_revision < receipt.revision:
        raise ValueError(f"{label} sealed observation predates its receipt")


def _optional_failure(value: object) -> GovernanceFailureV2 | None:
    return None if value is None else GovernanceFailureV2.from_dict(value)


def _optional_committed_transition(
    value: object,
) -> GovernanceCommittedTransitionV2 | None:
    return None if value is None else GovernanceCommittedTransitionV2.from_dict(value)


def _optional_position(
    value: object,
) -> GovernanceCommitPositionObservationV2 | None:
    return (
        None
        if value is None
        else GovernanceCommitPositionObservationV2.from_dict(value)
    )
