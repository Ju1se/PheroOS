"""Commit receipt, inclusion, transition, and position v2 records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, cast

from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    MAX_AUTHORITY_REVISION_V2,
)

from pheroos.governance._authority_store_v2_contracts.batch import (
    GovernanceCommitBatchV2,
)
from pheroos.governance._authority_store_v2_contracts.domain import GovernanceHeadV2
from pheroos.governance._authority_store_v2_contracts.foundation import (
    AUTHORITY_LEDGER_VERSION_V2,
    GOVERNANCE_COMMITTED_TRANSITION_SCHEMA_V2,
    GOVERNANCE_COMMIT_INCLUSION_PROOF_SCHEMA_V2,
    GOVERNANCE_COMMIT_POSITION_OBSERVATION_SCHEMA_V2,
    GOVERNANCE_COMMIT_RECEIPT_SCHEMA_V2,
    GovernanceCommitPositionV2,
    _CanonicalRootRecordV2,
    _exact_object,
    _install_root,
    _position_from_wire,
    _require_exact_version,
    _require_revision,
    _require_root,
    _require_text,
    _validate_common_binding,
)


@dataclass(frozen=True, slots=True)
class GovernanceCommitReceiptV2(_CanonicalRootRecordV2):
    """Portable root binding one exact atomically committed v2 batch."""

    domain_root: str
    scope_ref: str
    stream_ref: str
    transition_id: str
    revision: int
    parent_root: str
    head_root: str
    state_root: str
    read_set_root: str
    trace_root: str
    batch_root: str
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    ledger_version: str = AUTHORITY_LEDGER_VERSION_V2
    schema: str = GOVERNANCE_COMMIT_RECEIPT_SCHEMA_V2
    receipt_root: str = ""

    _root_field: ClassVar[str] = "receipt_root"

    def __post_init__(self) -> None:
        _validate_common_binding(
            canonical_version=self.canonical_version,
            ledger_version=self.ledger_version,
            domain_root=self.domain_root,
            scope_ref=self.scope_ref,
        )
        _require_exact_version(
            self.schema,
            GOVERNANCE_COMMIT_RECEIPT_SCHEMA_V2,
            "governance commit receipt schema",
        )
        _require_text(self.stream_ref, "governance commit receipt stream_ref")
        _require_text(self.transition_id, "governance commit receipt transition_id")
        if self.transition_id == "genesis":
            raise ValueError("governance commit receipt cannot use genesis identity")
        _require_revision(self.revision, "governance commit receipt revision")
        if self.revision == 0:
            raise ValueError("governance commit receipt revision must be positive")
        for name in (
            "parent_root",
            "head_root",
            "state_root",
            "read_set_root",
            "trace_root",
            "batch_root",
        ):
            _require_root(
                cast(str, getattr(self, name)),
                f"governance commit receipt {name}",
            )
        _install_root(
            self,
            "receipt_root",
            self.receipt_root,
            "receipt",
            self._root_body(),
        )

    def _root_body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "ledger_version": self.ledger_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "stream_ref": self.stream_ref,
            "transition_id": self.transition_id,
            "revision": self.revision,
            "parent_root": self.parent_root,
            "head_root": self.head_root,
            "state_root": self.state_root,
            "read_set_root": self.read_set_root,
            "trace_root": self.trace_root,
            "batch_root": self.batch_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._root_body(), "receipt_root": self.receipt_root}

    @classmethod
    def from_dict(cls, payload: object) -> GovernanceCommitReceiptV2:
        value = _exact_object(
            payload,
            frozenset(
                {
                    "schema",
                    "canonical_version",
                    "ledger_version",
                    "domain_root",
                    "scope_ref",
                    "stream_ref",
                    "transition_id",
                    "revision",
                    "parent_root",
                    "head_root",
                    "state_root",
                    "read_set_root",
                    "trace_root",
                    "batch_root",
                    "receipt_root",
                }
            ),
            "governance commit receipt v2",
        )
        return cls(
            domain_root=value["domain_root"],
            scope_ref=value["scope_ref"],
            stream_ref=value["stream_ref"],
            transition_id=value["transition_id"],
            revision=value["revision"],
            parent_root=value["parent_root"],
            head_root=value["head_root"],
            state_root=value["state_root"],
            read_set_root=value["read_set_root"],
            trace_root=value["trace_root"],
            batch_root=value["batch_root"],
            canonical_version=value["canonical_version"],
            ledger_version=value["ledger_version"],
            schema=value["schema"],
            receipt_root=value["receipt_root"],
        )


@dataclass(frozen=True, slots=True)
class GovernanceCommitInclusionProofV2(_CanonicalRootRecordV2):
    """Durable historical inclusion binding independent of current head."""

    domain_root: str
    scope_ref: str
    stream_ref: str
    transition_id: str
    revision: int
    batch_root: str
    receipt_root: str
    head_root: str
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    ledger_version: str = AUTHORITY_LEDGER_VERSION_V2
    schema: str = GOVERNANCE_COMMIT_INCLUSION_PROOF_SCHEMA_V2
    inclusion_root: str = ""

    _root_field: ClassVar[str] = "inclusion_root"

    def __post_init__(self) -> None:
        _validate_common_binding(
            canonical_version=self.canonical_version,
            ledger_version=self.ledger_version,
            domain_root=self.domain_root,
            scope_ref=self.scope_ref,
        )
        _require_exact_version(
            self.schema,
            GOVERNANCE_COMMIT_INCLUSION_PROOF_SCHEMA_V2,
            "governance commit inclusion schema",
        )
        _require_text(self.stream_ref, "governance inclusion stream_ref")
        _require_text(self.transition_id, "governance inclusion transition_id")
        _require_revision(self.revision, "governance inclusion revision")
        if self.revision == 0:
            raise ValueError("governance inclusion revision must be positive")
        _require_root(self.batch_root, "governance inclusion batch_root")
        _require_root(self.receipt_root, "governance inclusion receipt_root")
        _require_root(self.head_root, "governance inclusion head_root")
        _install_root(
            self,
            "inclusion_root",
            self.inclusion_root,
            "inclusion",
            self._root_body(),
        )

    def _root_body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "ledger_version": self.ledger_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "stream_ref": self.stream_ref,
            "transition_id": self.transition_id,
            "revision": self.revision,
            "batch_root": self.batch_root,
            "receipt_root": self.receipt_root,
            "head_root": self.head_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._root_body(), "inclusion_root": self.inclusion_root}

    @classmethod
    def from_dict(cls, payload: object) -> GovernanceCommitInclusionProofV2:
        value = _exact_object(
            payload,
            frozenset(
                {
                    "schema",
                    "canonical_version",
                    "ledger_version",
                    "domain_root",
                    "scope_ref",
                    "stream_ref",
                    "transition_id",
                    "revision",
                    "batch_root",
                    "receipt_root",
                    "head_root",
                    "inclusion_root",
                }
            ),
            "governance commit inclusion proof v2",
        )
        return cls(
            domain_root=value["domain_root"],
            scope_ref=value["scope_ref"],
            stream_ref=value["stream_ref"],
            transition_id=value["transition_id"],
            revision=value["revision"],
            batch_root=value["batch_root"],
            receipt_root=value["receipt_root"],
            head_root=value["head_root"],
            canonical_version=value["canonical_version"],
            ledger_version=value["ledger_version"],
            schema=value["schema"],
            inclusion_root=value["inclusion_root"],
        )


@dataclass(frozen=True, slots=True)
class GovernanceCommittedTransitionV2(_CanonicalRootRecordV2):
    """Detached batch, receipt, and verified historical inclusion proof."""

    batch: GovernanceCommitBatchV2
    receipt: GovernanceCommitReceiptV2
    inclusion_proof: GovernanceCommitInclusionProofV2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    ledger_version: str = AUTHORITY_LEDGER_VERSION_V2
    schema: str = GOVERNANCE_COMMITTED_TRANSITION_SCHEMA_V2
    committed_transition_root: str = ""

    _root_field: ClassVar[str] = "committed_transition_root"

    def __post_init__(self) -> None:
        _require_exact_version(
            self.canonical_version,
            AUTHORITY_CANONICAL_VERSION_V2,
            "committed transition canonical_version",
        )
        _require_exact_version(
            self.ledger_version,
            AUTHORITY_LEDGER_VERSION_V2,
            "committed transition ledger_version",
        )
        _require_exact_version(
            self.schema,
            GOVERNANCE_COMMITTED_TRANSITION_SCHEMA_V2,
            "committed transition schema",
        )
        if type(self.batch) is not GovernanceCommitBatchV2:
            raise TypeError("committed transition batch is invalid")
        if type(self.receipt) is not GovernanceCommitReceiptV2:
            raise TypeError("committed transition receipt is invalid")
        if type(self.inclusion_proof) is not GovernanceCommitInclusionProofV2:
            raise TypeError("committed transition inclusion proof is invalid")
        object.__setattr__(
            self,
            "batch",
            GovernanceCommitBatchV2.from_dict(self.batch.to_dict()),
        )
        object.__setattr__(
            self,
            "receipt",
            GovernanceCommitReceiptV2.from_dict(self.receipt.to_dict()),
        )
        object.__setattr__(
            self,
            "inclusion_proof",
            GovernanceCommitInclusionProofV2.from_dict(self.inclusion_proof.to_dict()),
        )
        _validate_committed_artifacts(self.batch, self.receipt, self.inclusion_proof)
        _install_root(
            self,
            "committed_transition_root",
            self.committed_transition_root,
            "committed-transition",
            self._root_body(),
        )

    def _root_body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "ledger_version": self.ledger_version,
            "batch": self.batch.to_dict(),
            "receipt": self.receipt.to_dict(),
            "inclusion_proof": self.inclusion_proof.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            **self._root_body(),
            "committed_transition_root": self.committed_transition_root,
        }

    @classmethod
    def from_dict(cls, payload: object) -> GovernanceCommittedTransitionV2:
        value = _exact_object(
            payload,
            frozenset(
                {
                    "schema",
                    "canonical_version",
                    "ledger_version",
                    "batch",
                    "receipt",
                    "inclusion_proof",
                    "committed_transition_root",
                }
            ),
            "governance committed transition v2",
        )
        return cls(
            batch=GovernanceCommitBatchV2.from_dict(value["batch"]),
            receipt=GovernanceCommitReceiptV2.from_dict(value["receipt"]),
            inclusion_proof=GovernanceCommitInclusionProofV2.from_dict(
                value["inclusion_proof"]
            ),
            canonical_version=value["canonical_version"],
            ledger_version=value["ledger_version"],
            schema=value["schema"],
            committed_transition_root=value["committed_transition_root"],
        )


@dataclass(frozen=True, slots=True)
class GovernanceCommitPositionObservationV2(_CanonicalRootRecordV2):
    """Immutable read-time position for one verified included transition."""

    domain_root: str
    scope_ref: str
    stream_ref: str
    transition_id: str
    receipt_root: str
    observed_revision: int
    observed_head_root: str
    position: GovernanceCommitPositionV2
    seal_root: str | None = None
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    ledger_version: str = AUTHORITY_LEDGER_VERSION_V2
    schema: str = GOVERNANCE_COMMIT_POSITION_OBSERVATION_SCHEMA_V2
    observation_root: str = ""

    _root_field: ClassVar[str] = "observation_root"

    def __post_init__(self) -> None:
        _validate_common_binding(
            canonical_version=self.canonical_version,
            ledger_version=self.ledger_version,
            domain_root=self.domain_root,
            scope_ref=self.scope_ref,
        )
        _require_exact_version(
            self.schema,
            GOVERNANCE_COMMIT_POSITION_OBSERVATION_SCHEMA_V2,
            "governance position observation schema",
        )
        _require_text(self.stream_ref, "governance position stream_ref")
        _require_text(self.transition_id, "governance position transition_id")
        _require_root(self.receipt_root, "governance position receipt_root")
        _require_revision(
            self.observed_revision,
            "governance position observed_revision",
        )
        if self.observed_revision == 0:
            raise ValueError("governance position must observe a committed revision")
        _require_root(
            self.observed_head_root,
            "governance position observed_head_root",
        )
        if type(self.position) is not GovernanceCommitPositionV2:
            raise TypeError("governance commit position is invalid")
        if self.position is GovernanceCommitPositionV2.SEALED:
            _require_root(self.seal_root, "sealed position seal_root")
        elif self.seal_root is not None:
            raise ValueError("only a sealed position may carry seal_root")
        _install_root(
            self,
            "observation_root",
            self.observation_root,
            "position-observation",
            self._root_body(),
        )

    def _root_body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "ledger_version": self.ledger_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "stream_ref": self.stream_ref,
            "transition_id": self.transition_id,
            "receipt_root": self.receipt_root,
            "observed_revision": self.observed_revision,
            "observed_head_root": self.observed_head_root,
            "position": self.position.value,
            "seal_root": self.seal_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._root_body(), "observation_root": self.observation_root}

    @classmethod
    def from_dict(cls, payload: object) -> GovernanceCommitPositionObservationV2:
        value = _exact_object(
            payload,
            frozenset(
                {
                    "schema",
                    "canonical_version",
                    "ledger_version",
                    "domain_root",
                    "scope_ref",
                    "stream_ref",
                    "transition_id",
                    "receipt_root",
                    "observed_revision",
                    "observed_head_root",
                    "position",
                    "seal_root",
                    "observation_root",
                }
            ),
            "governance commit position observation v2",
        )
        return cls(
            domain_root=value["domain_root"],
            scope_ref=value["scope_ref"],
            stream_ref=value["stream_ref"],
            transition_id=value["transition_id"],
            receipt_root=value["receipt_root"],
            observed_revision=value["observed_revision"],
            observed_head_root=value["observed_head_root"],
            position=_position_from_wire(value["position"]),
            seal_root=value["seal_root"],
            canonical_version=value["canonical_version"],
            ledger_version=value["ledger_version"],
            schema=value["schema"],
            observation_root=value["observation_root"],
        )


def _validate_committed_artifacts(
    batch: GovernanceCommitBatchV2,
    receipt: GovernanceCommitReceiptV2,
    inclusion: GovernanceCommitInclusionProofV2,
) -> None:
    bindings = (
        batch.domain_root,
        batch.scope_ref,
        batch.stream_ref,
        batch.transition_id,
    )
    if bindings != (
        receipt.domain_root,
        receipt.scope_ref,
        receipt.stream_ref,
        receipt.transition_id,
    ) or bindings != (
        inclusion.domain_root,
        inclusion.scope_ref,
        inclusion.stream_ref,
        inclusion.transition_id,
    ):
        raise ValueError("committed transition artifacts have mismatched bindings")
    if batch.kind == "transition":
        assert batch.transition is not None
        expected_revision = batch.transition.expected_revision + 1
        expected_parent = batch.transition.expected_root
        expected_state = batch.transition.state_root
    else:
        assert batch.seal is not None
        expected_revision = batch.seal.expected_revision + 1
        expected_parent = batch.seal.expected_root
        expected_state = batch.seal.seal_root
    if expected_revision > MAX_AUTHORITY_REVISION_V2:
        raise ValueError("committed transition revision exceeds ABI maximum")
    expected_head = GovernanceHeadV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        revision=expected_revision,
        parent_root=expected_parent,
        state_root=expected_state,
        transition_id=batch.transition_id,
        batch_root=batch.batch_root,
    )
    if (
        receipt.revision != expected_revision
        or receipt.parent_root != expected_parent
        or receipt.state_root != expected_state
        or receipt.head_root != expected_head.head_root
        or receipt.read_set_root != batch.read_set_root
        or receipt.trace_root != batch.trace_root
        or receipt.batch_root != batch.batch_root
    ):
        raise ValueError("commit receipt does not match its exact batch")
    if (
        inclusion.revision != receipt.revision
        or inclusion.batch_root != receipt.batch_root
        or inclusion.receipt_root != receipt.receipt_root
        or inclusion.head_root != receipt.head_root
    ):
        raise ValueError("inclusion proof does not match its commit receipt")
