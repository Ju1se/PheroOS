"""Trace, seal, and atomic commit-batch v2 records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from hmac import compare_digest
from types import MappingProxyType
from typing import Any, ClassVar

from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GovernanceAuthorityReadSetV2,
)
from pheroos.trace import TraceEvent

from pheroos.governance._authority_store_v2_contracts.domain import (
    AuthorityDomainV2,
    PreparedGovernanceTransitionV2,
)
from pheroos.governance._authority_store_v2_contracts.foundation import (
    AUTHORITY_LEDGER_VERSION_V2,
    GOVERNANCE_COMMIT_BATCH_SCHEMA_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_DOMAIN_SEAL_SCHEMA_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    MAX_GOVERNANCE_NON_LIFECYCLE_STREAMS_V2,
    MAX_GOVERNANCE_TRACE_EVENTS_V2,
    _BATCH_KINDS,
    _CanonicalRootRecordV2,
    _compute_root,
    _exact_object,
    _freeze_json_mapping,
    _install_exact_computed,
    _install_optional_exact,
    _install_root,
    _portable_json,
    _read_precondition,
    _require_exact_version,
    _require_revision,
    _require_root,
    _require_text,
    _validate_common_binding,
    _validate_nested_binding,
)


@dataclass(frozen=True, slots=True, init=False)
class GovernanceTraceBatchV2(_CanonicalRootRecordV2):
    """Ordered defensive snapshots of canonical Trace ABI events."""

    canonical_version: str
    domain_root: str
    scope_ref: str
    stream_ref: str
    transition_id: str
    _event_snapshots: tuple[Mapping[str, Any], ...] = field(
        repr=False,
        compare=True,
    )
    schema: str
    trace_root: str

    _root_field: ClassVar[str] = "trace_root"

    def __init__(
        self,
        *,
        domain_root: str,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        events: Sequence[TraceEvent],
        canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2,
        schema: str = GOVERNANCE_TRACE_BATCH_VERSION_V2,
        trace_root: str = "",
    ) -> None:
        _require_exact_version(
            canonical_version,
            AUTHORITY_CANONICAL_VERSION_V2,
            "governance trace batch canonical_version",
        )
        _require_root(domain_root, "governance trace batch domain_root")
        _require_text(scope_ref, "governance trace batch scope_ref")
        _require_text(stream_ref, "governance trace batch stream_ref")
        _require_text(transition_id, "governance trace batch transition_id")
        _require_exact_version(
            schema,
            GOVERNANCE_TRACE_BATCH_VERSION_V2,
            "governance trace batch schema",
        )
        if isinstance(events, (str, bytes, bytearray)) or not isinstance(
            events,
            Sequence,
        ):
            raise TypeError("governance trace batch events must be a sequence")
        if not 1 <= len(events) <= MAX_GOVERNANCE_TRACE_EVENTS_V2:
            raise ValueError(
                "governance trace batch requires from 1 through 128 events"
            )
        snapshots = tuple(
            _trace_event_snapshot(
                event,
                domain_root=domain_root,
                scope_ref=scope_ref,
                stream_ref=stream_ref,
                transition_id=transition_id,
            )
            for event in events
        )
        object.__setattr__(self, "canonical_version", canonical_version)
        object.__setattr__(self, "domain_root", domain_root)
        object.__setattr__(self, "scope_ref", scope_ref)
        object.__setattr__(self, "stream_ref", stream_ref)
        object.__setattr__(self, "transition_id", transition_id)
        object.__setattr__(self, "_event_snapshots", snapshots)
        object.__setattr__(self, "schema", schema)
        computed = _compute_root("trace-batch", self._root_body())
        if not (type(trace_root) is str and trace_root == ""):
            _require_root(trace_root, "governance trace batch trace_root")
            if not compare_digest(trace_root, computed):
                raise ValueError("governance trace batch trace_root is mismatched")
        object.__setattr__(self, "trace_root", computed)

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        """Return detached canonical TraceEvent values, never internal mappings."""

        return tuple(
            _trace_event_from_snapshot(snapshot) for snapshot in self._event_snapshots
        )

    def _root_body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "stream_ref": self.stream_ref,
            "transition_id": self.transition_id,
            "events": [_portable_json(item) for item in self._event_snapshots],
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._root_body(), "trace_root": self.trace_root}

    @classmethod
    def from_dict(cls, payload: object) -> GovernanceTraceBatchV2:
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
                    "events",
                    "trace_root",
                }
            ),
            "governance trace batch v2",
        )
        events = value["events"]
        if type(events) is not list:
            raise TypeError("governance trace batch events wire field must be an array")
        return cls(
            domain_root=value["domain_root"],
            scope_ref=value["scope_ref"],
            stream_ref=value["stream_ref"],
            transition_id=value["transition_id"],
            events=tuple(_trace_event_from_wire(item) for item in events),
            canonical_version=value["canonical_version"],
            schema=value["schema"],
            trace_root=value["trace_root"],
        )


@dataclass(frozen=True, slots=True)
class GovernanceDomainSealV2(_CanonicalRootRecordV2):
    """Terminal domain lifecycle transition preserving all prior proof."""

    domain_root: str
    scope_ref: str
    transition_id: str
    expected_revision: int
    expected_root: str
    final_heads: tuple[Mapping[str, Any], ...]
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    ledger_version: str = AUTHORITY_LEDGER_VERSION_V2
    schema: str = GOVERNANCE_DOMAIN_SEAL_SCHEMA_V2
    final_heads_root: str = ""
    seal_root: str = ""

    _root_field: ClassVar[str] = "seal_root"

    def __post_init__(self) -> None:
        _validate_common_binding(
            canonical_version=self.canonical_version,
            ledger_version=self.ledger_version,
            domain_root=self.domain_root,
            scope_ref=self.scope_ref,
        )
        _require_exact_version(
            self.schema,
            GOVERNANCE_DOMAIN_SEAL_SCHEMA_V2,
            "governance domain seal schema",
        )
        _require_text(self.transition_id, "governance domain seal transition_id")
        if self.transition_id == "genesis":
            raise ValueError("governance domain seal cannot use genesis identity")
        _require_revision(
            self.expected_revision,
            "governance domain seal expected_revision",
        )
        _require_root(self.expected_root, "governance domain seal expected_root")
        if type(self.final_heads) is not tuple:
            raise TypeError("governance domain seal final_heads must be a tuple")
        if len(self.final_heads) > MAX_GOVERNANCE_NON_LIFECYCLE_STREAMS_V2:
            raise ValueError("governance domain seal supports at most 127 final heads")
        heads = tuple(_freeze_final_head(item) for item in self.final_heads)
        keys = tuple(item["stream_ref"].encode("utf-8") for item in heads)
        if len(keys) != len(set(keys)) or keys != tuple(sorted(keys)):
            raise ValueError(
                "governance domain seal final_heads must be unique and UTF-8 sorted"
            )
        if any(
            item["stream_ref"] == GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
            for item in heads
        ):
            raise ValueError("governance final_heads must exclude lifecycle stream")
        object.__setattr__(self, "final_heads", heads)
        computed_final_heads = _compute_root(
            "seal-heads",
            {
                "canonical_version": self.canonical_version,
                "domain_root": self.domain_root,
                "scope_ref": self.scope_ref,
                "entries": [_portable_json(item) for item in heads],
            },
        )
        _install_exact_computed(
            self,
            "final_heads_root",
            self.final_heads_root,
            computed_final_heads,
            "governance domain seal final_heads_root",
        )
        _install_root(self, "seal_root", self.seal_root, "seal", self._root_body())

    def _root_body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "ledger_version": self.ledger_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "transition_id": self.transition_id,
            "expected_revision": self.expected_revision,
            "expected_root": self.expected_root,
            "final_heads": [_portable_json(item) for item in self.final_heads],
            "final_heads_root": self.final_heads_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._root_body(), "seal_root": self.seal_root}

    @classmethod
    def from_dict(cls, payload: object) -> GovernanceDomainSealV2:
        value = _exact_object(
            payload,
            frozenset(
                {
                    "schema",
                    "canonical_version",
                    "ledger_version",
                    "domain_root",
                    "scope_ref",
                    "transition_id",
                    "expected_revision",
                    "expected_root",
                    "final_heads",
                    "final_heads_root",
                    "seal_root",
                }
            ),
            "governance domain seal v2",
        )
        final_heads = value["final_heads"]
        if type(final_heads) is not list:
            raise TypeError("governance domain seal final_heads must be an array")
        return cls(
            domain_root=value["domain_root"],
            scope_ref=value["scope_ref"],
            transition_id=value["transition_id"],
            expected_revision=value["expected_revision"],
            expected_root=value["expected_root"],
            final_heads=tuple(final_heads),
            canonical_version=value["canonical_version"],
            ledger_version=value["ledger_version"],
            schema=value["schema"],
            final_heads_root=value["final_heads_root"],
            seal_root=value["seal_root"],
        )


@dataclass(frozen=True, slots=True)
class GovernanceCommitBatchV2(_CanonicalRootRecordV2):
    """One bounded state-or-seal transition and canonical Trace batch."""

    domain: AuthorityDomainV2
    scope_ref: str
    stream_ref: str
    transition_id: str
    kind: str
    read_set: GovernanceAuthorityReadSetV2
    trace_batch: GovernanceTraceBatchV2
    transition: PreparedGovernanceTransitionV2 | None = None
    seal: GovernanceDomainSealV2 | None = None
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    ledger_version: str = AUTHORITY_LEDGER_VERSION_V2
    schema: str = GOVERNANCE_COMMIT_BATCH_SCHEMA_V2
    domain_root: str = ""
    read_set_root: str = ""
    transition_root: str | None = None
    seal_root: str | None = None
    trace_root: str = ""
    batch_root: str = ""

    _root_field: ClassVar[str] = "batch_root"

    def __post_init__(self) -> None:
        _snapshot_commit_batch_nested(self)
        _validate_common_binding(
            canonical_version=self.canonical_version,
            ledger_version=self.ledger_version,
            domain_root=self.domain.domain_root,
            scope_ref=self.scope_ref,
        )
        _require_exact_version(
            self.schema,
            GOVERNANCE_COMMIT_BATCH_SCHEMA_V2,
            "governance commit batch schema",
        )
        _require_text(self.stream_ref, "governance commit batch stream_ref")
        _require_text(self.transition_id, "governance commit batch transition_id")
        if self.transition_id == "genesis":
            raise ValueError("governance commit batch cannot use genesis identity")
        if type(self.kind) is not str or self.kind not in _BATCH_KINDS:
            raise ValueError("governance commit batch kind is unsupported")
        _install_exact_computed(
            self,
            "domain_root",
            self.domain_root,
            self.domain.domain_root,
            "governance commit batch domain_root",
        )
        if self.scope_ref != self.domain.scope_ref:
            raise ValueError("governance commit batch crosses authority scope")
        _install_exact_computed(
            self,
            "read_set_root",
            self.read_set_root,
            self.read_set.root(),
            "governance commit batch read_set_root",
        )
        _validate_nested_binding(
            self.trace_batch,
            domain_root=self.domain_root,
            scope_ref=self.scope_ref,
            stream_ref=self.stream_ref,
            transition_id=self.transition_id,
            label="governance commit trace batch",
        )
        _install_exact_computed(
            self,
            "trace_root",
            self.trace_root,
            self.trace_batch.trace_root,
            "governance commit batch trace_root",
        )
        if self.kind == "transition":
            self._validate_transition_kind()
        else:
            self._validate_seal_kind()
        _install_root(
            self,
            "batch_root",
            self.batch_root,
            "commit-batch",
            self._root_body(),
        )

    def _validate_transition_kind(self) -> None:
        if type(self.transition) is not PreparedGovernanceTransitionV2:
            raise TypeError("transition commit batch requires a prepared transition")
        if self.seal is not None or self.seal_root is not None:
            raise ValueError("transition commit batch cannot carry a domain seal")
        if self.stream_ref == GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2:
            raise ValueError("ordinary transition cannot write lifecycle stream")
        _validate_nested_binding(
            self.transition,
            domain_root=self.domain_root,
            scope_ref=self.scope_ref,
            stream_ref=self.stream_ref,
            transition_id=self.transition_id,
            label="prepared governance transition",
        )
        if self.transition.read_set_root != self.read_set_root:
            raise ValueError("prepared transition read_set_root is mismatched")
        target = _read_precondition(self.read_set, self.stream_ref)
        if target is None or (
            target.expected_revision != self.transition.expected_revision
            or target.expected_root != self.transition.expected_root
        ):
            raise ValueError(
                "prepared transition target precondition is absent or mismatched"
            )
        _install_optional_exact(
            self,
            "transition_root",
            self.transition_root,
            self.transition.transition_root,
            "governance commit batch transition_root",
        )

    def _validate_seal_kind(self) -> None:
        if type(self.seal) is not GovernanceDomainSealV2:
            raise TypeError("seal commit batch requires a governance domain seal")
        if self.transition is not None or self.transition_root is not None:
            raise ValueError("seal commit batch cannot carry a prepared transition")
        if self.stream_ref != GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2:
            raise ValueError("seal commit batch must write lifecycle stream")
        _validate_nested_binding(
            self.seal,
            domain_root=self.domain_root,
            scope_ref=self.scope_ref,
            stream_ref=None,
            transition_id=self.transition_id,
            label="governance domain seal",
        )
        lifecycle = _read_precondition(
            self.read_set,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        )
        if lifecycle is None or (
            lifecycle.expected_revision != self.seal.expected_revision
            or lifecycle.expected_root != self.seal.expected_root
        ):
            raise ValueError("domain seal lifecycle precondition is mismatched")
        expected_final_heads = tuple(
            {
                "stream_ref": item.stream_ref,
                "revision": item.expected_revision,
                "head_root": item.expected_root,
            }
            for item in self.read_set.entries
            if item.stream_ref != GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
        )
        if [_portable_json(item) for item in self.seal.final_heads] != list(
            expected_final_heads
        ):
            raise ValueError(
                "domain seal final_heads must exactly cover non-lifecycle read-set"
            )
        if not any(
            event.lineage.get("seal_root") == self.seal.seal_root
            for event in self.trace_batch.events
        ):
            raise ValueError("domain seal trace batch must bind the seal_root")
        _install_optional_exact(
            self,
            "seal_root",
            self.seal_root,
            self.seal.seal_root,
            "governance commit batch seal_root",
        )

    def _root_body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "ledger_version": self.ledger_version,
            "domain": self.domain.to_dict(),
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "stream_ref": self.stream_ref,
            "transition_id": self.transition_id,
            "kind": self.kind,
            "read_set": self.read_set.to_dict(),
            "read_set_root": self.read_set_root,
            "transition": None
            if self.transition is None
            else self.transition.to_dict(),
            "transition_root": self.transition_root,
            "seal": None if self.seal is None else self.seal.to_dict(),
            "seal_root": self.seal_root,
            "trace_batch": self.trace_batch.to_dict(),
            "trace_root": self.trace_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._root_body(), "batch_root": self.batch_root}

    @classmethod
    def from_dict(cls, payload: object) -> GovernanceCommitBatchV2:
        value = _exact_object(
            payload,
            frozenset(
                {
                    "schema",
                    "canonical_version",
                    "ledger_version",
                    "domain",
                    "domain_root",
                    "scope_ref",
                    "stream_ref",
                    "transition_id",
                    "kind",
                    "read_set",
                    "read_set_root",
                    "transition",
                    "transition_root",
                    "seal",
                    "seal_root",
                    "trace_batch",
                    "trace_root",
                    "batch_root",
                }
            ),
            "governance commit batch v2",
        )
        transition = value["transition"]
        seal = value["seal"]
        if transition is not None and type(transition) is not dict:
            raise TypeError("governance commit transition must be an object or null")
        if seal is not None and type(seal) is not dict:
            raise TypeError("governance commit seal must be an object or null")
        if value["kind"] == "transition" and (
            value["transition_root"] is None or value["seal_root"] is not None
        ):
            raise ValueError("transition batch wire roots violate its closed union")
        if value["kind"] == "seal" and (
            value["seal_root"] is None or value["transition_root"] is not None
        ):
            raise ValueError("seal batch wire roots violate its closed union")
        return cls(
            domain=AuthorityDomainV2.from_dict(value["domain"]),
            scope_ref=value["scope_ref"],
            stream_ref=value["stream_ref"],
            transition_id=value["transition_id"],
            kind=value["kind"],
            read_set=GovernanceAuthorityReadSetV2.from_dict(value["read_set"]),
            trace_batch=GovernanceTraceBatchV2.from_dict(value["trace_batch"]),
            transition=(
                None
                if transition is None
                else PreparedGovernanceTransitionV2.from_dict(transition)
            ),
            seal=None if seal is None else GovernanceDomainSealV2.from_dict(seal),
            canonical_version=value["canonical_version"],
            ledger_version=value["ledger_version"],
            schema=value["schema"],
            domain_root=value["domain_root"],
            read_set_root=value["read_set_root"],
            transition_root=value["transition_root"],
            seal_root=value["seal_root"],
            trace_root=value["trace_root"],
            batch_root=value["batch_root"],
        )


def _snapshot_commit_batch_nested(batch: GovernanceCommitBatchV2) -> None:
    if type(batch.domain) is not AuthorityDomainV2:
        raise TypeError("governance commit batch domain is invalid")
    if type(batch.read_set) is not GovernanceAuthorityReadSetV2:
        raise TypeError("governance commit batch read_set is invalid")
    if type(batch.trace_batch) is not GovernanceTraceBatchV2:
        raise TypeError("governance commit batch trace_batch is invalid")
    if batch.transition is not None and (
        type(batch.transition) is not PreparedGovernanceTransitionV2
    ):
        raise TypeError("governance commit batch transition is invalid")
    if batch.seal is not None and type(batch.seal) is not GovernanceDomainSealV2:
        raise TypeError("governance commit batch seal is invalid")
    object.__setattr__(
        batch,
        "domain",
        AuthorityDomainV2.from_dict(batch.domain.to_dict()),
    )
    object.__setattr__(
        batch,
        "read_set",
        GovernanceAuthorityReadSetV2.from_dict(batch.read_set.to_dict()),
    )
    object.__setattr__(
        batch,
        "trace_batch",
        GovernanceTraceBatchV2.from_dict(batch.trace_batch.to_dict()),
    )
    if batch.transition is not None:
        object.__setattr__(
            batch,
            "transition",
            PreparedGovernanceTransitionV2.from_dict(batch.transition.to_dict()),
        )
    if batch.seal is not None:
        object.__setattr__(
            batch,
            "seal",
            GovernanceDomainSealV2.from_dict(batch.seal.to_dict()),
        )


def _trace_event_snapshot(
    event: object,
    *,
    domain_root: str,
    scope_ref: str,
    stream_ref: str,
    transition_id: str,
) -> Mapping[str, Any]:
    if type(event) is not TraceEvent:
        raise TypeError("governance trace batch accepts only canonical TraceEvent")
    event.validate()
    lineage = _freeze_json_mapping(event.lineage, "trace_event.lineage")
    for field_name, expected in (
        ("domain_root", domain_root),
        ("scope_ref", scope_ref),
        ("stream_ref", stream_ref),
        ("transition_id", transition_id),
    ):
        if field_name == "domain_root" and field_name not in lineage:
            continue
        if lineage.get(field_name) != expected:
            raise ValueError(f"governance TraceEvent {field_name} is mismatched")
    return MappingProxyType(
        {
            "event_type": _require_text(event.event_type, "TraceEvent event_type"),
            "protocol_id": _require_text(event.protocol_id, "TraceEvent protocol_id"),
            "target": _require_text(event.target, "TraceEvent target"),
            "reason": _require_text(event.reason, "TraceEvent reason"),
            "lineage": lineage,
        }
    )


def _trace_event_from_snapshot(snapshot: Mapping[str, Any]) -> TraceEvent:
    return TraceEvent(
        event_type=snapshot["event_type"],
        protocol_id=snapshot["protocol_id"],
        target=snapshot["target"],
        reason=snapshot["reason"],
        lineage=_portable_json(snapshot["lineage"]),
    )


def _trace_event_from_wire(payload: object) -> TraceEvent:
    value = _exact_object(
        payload,
        frozenset({"event_type", "protocol_id", "target", "reason", "lineage"}),
        "governance TraceEvent projection",
    )
    if type(value["lineage"]) is not dict:
        raise TypeError("governance TraceEvent lineage must be an object")
    return TraceEvent(
        event_type=value["event_type"],
        protocol_id=value["protocol_id"],
        target=value["target"],
        reason=value["reason"],
        lineage=value["lineage"],
    )


def _freeze_final_head(value: object) -> Mapping[str, Any]:
    item = _exact_object(
        value,
        frozenset({"stream_ref", "revision", "head_root"}),
        "governance final head",
    )
    stream_ref = _require_text(item["stream_ref"], "governance final head stream_ref")
    revision = _require_revision(item["revision"], "governance final head revision")
    head_root = _require_root(item["head_root"], "governance final head head_root")
    return MappingProxyType(
        {"stream_ref": stream_ref, "revision": revision, "head_root": head_root}
    )
