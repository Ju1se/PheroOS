from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
import json
from math import isfinite
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from pheroos._digest import is_canonical_sha256_fingerprint
from pheroos.governance.errors import GovernanceError


AUTHORITY_LEDGER_VERSION = "pheroos-governance-authority-ledger-v1"
_DOMAIN_SCHEMA = "pheroos-authority-domain-v1"
_HEAD_SCHEMA = "pheroos-governance-head-v1"
_TRANSITION_SCHEMA = "pheroos-prepared-governance-transition-v1"
_BATCH_SCHEMA = "pheroos-governance-commit-batch-v1"
_RECEIPT_SCHEMA = "pheroos-governance-commit-receipt-v1"
GOVERNANCE_GENESIS_ROOT = "sha256:" + sha256(
    b"pheroos-governance-authority-genesis-v1"
).hexdigest()


@dataclass(frozen=True)
class AuthorityDomain:
    """Opaque Governance authority domain supplied by an outer runtime."""

    scope_ref: str

    def __post_init__(self) -> None:
        _require_scope_ref(self.scope_ref, "authority domain scope_ref")

    def to_dict(self) -> dict[str, Any]:
        return {"schema": _DOMAIN_SCHEMA, "scope_ref": self.scope_ref}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AuthorityDomain:
        _require_exact_fields(payload, {"schema", "scope_ref"}, _DOMAIN_SCHEMA)
        if payload["schema"] != _DOMAIN_SCHEMA:
            raise GovernanceError("authority domain schema is unsupported")
        return cls(scope_ref=payload["scope_ref"])

    def fingerprint(self) -> str:
        return _fingerprint(_DOMAIN_SCHEMA, self.to_dict())


@dataclass(frozen=True)
class GovernanceHead:
    """Current authoritative head for one scope-local Governance stream."""

    scope_ref: str
    stream: str
    revision: int
    parent_root: str
    state_root: str
    transition_id: str

    def __post_init__(self) -> None:
        _require_scope_ref(self.scope_ref, "governance head scope_ref")
        _require_identity(self.stream, "governance head stream")
        if type(self.revision) is not int or self.revision < 0:
            raise GovernanceError("governance head revision must be a non-negative integer")
        _require_digest(self.parent_root, "governance head parent_root")
        _require_digest(self.state_root, "governance head state_root")
        _require_identity(self.transition_id, "governance head transition_id")

    @classmethod
    def genesis(cls, scope_ref: str, stream: str) -> GovernanceHead:
        return cls(
            scope_ref=scope_ref,
            stream=stream,
            revision=0,
            parent_root=GOVERNANCE_GENESIS_ROOT,
            state_root=GOVERNANCE_GENESIS_ROOT,
            transition_id="genesis",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": _HEAD_SCHEMA,
            "scope_ref": self.scope_ref,
            "stream": self.stream,
            "revision": self.revision,
            "parent_root": self.parent_root,
            "state_root": self.state_root,
            "transition_id": self.transition_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> GovernanceHead:
        _require_exact_fields(
            payload,
            {
                "schema",
                "scope_ref",
                "stream",
                "revision",
                "parent_root",
                "state_root",
                "transition_id",
            },
            _HEAD_SCHEMA,
        )
        if payload["schema"] != _HEAD_SCHEMA:
            raise GovernanceError("governance head schema is unsupported")
        return cls(
            scope_ref=payload["scope_ref"],
            stream=payload["stream"],
            revision=payload["revision"],
            parent_root=payload["parent_root"],
            state_root=payload["state_root"],
            transition_id=payload["transition_id"],
        )

    def fingerprint(self) -> str:
        return _fingerprint(_HEAD_SCHEMA, self.to_dict())


@dataclass(frozen=True)
class PreparedGovernanceTransition:
    """Pure immutable state transition prepared against one exact head."""

    domain: AuthorityDomain
    stream: str
    transition_id: str
    expected_revision: int
    expected_parent_root: str
    expected_state_root: str
    state_records: Mapping[str, Any]
    identity_claims: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    state_root: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.domain, AuthorityDomain):
            raise GovernanceError("prepared transition authority domain is invalid")
        _require_identity(self.stream, "prepared transition stream")
        _require_identity(self.transition_id, "prepared transition id")
        if type(self.expected_revision) is not int or self.expected_revision < 0:
            raise GovernanceError(
                "prepared transition expected revision must be a non-negative integer"
            )
        _require_digest(
            self.expected_parent_root,
            "prepared transition expected parent root",
        )
        _require_digest(
            self.expected_state_root,
            "prepared transition expected state root",
        )
        if not isinstance(self.state_records, Mapping):
            raise GovernanceError("prepared transition state records must be a mapping")
        frozen_state = _freeze_json(self.state_records, path="state_records")
        if not isinstance(frozen_state, Mapping):  # pragma: no cover - guarded above
            raise GovernanceError("prepared transition state records must be a mapping")
        if not isinstance(self.identity_claims, Mapping):
            raise GovernanceError("prepared transition identity claims must be a mapping")
        claims: dict[str, Mapping[str, Any]] = {}
        for claim_id in self.identity_claims:
            _require_identity(claim_id, "governance identity claim id")
        for claim_id in sorted(self.identity_claims):
            body = self.identity_claims[claim_id]
            if not isinstance(body, Mapping):
                raise GovernanceError("governance identity claim body must be a mapping")
            frozen_body = _freeze_json(body, path=f"identity_claims.{claim_id}")
            if not isinstance(frozen_body, Mapping):  # pragma: no cover - guarded above
                raise GovernanceError("governance identity claim body must be a mapping")
            claims[claim_id] = frozen_body
        object.__setattr__(self, "state_records", frozen_state)
        object.__setattr__(self, "identity_claims", MappingProxyType(claims))
        computed = _fingerprint(_TRANSITION_SCHEMA, self._root_payload())
        if self.state_root and self.state_root != computed:
            raise GovernanceError("prepared transition state root does not match its payload")
        object.__setattr__(self, "state_root", computed)

    @classmethod
    def from_head(
        cls,
        head: GovernanceHead,
        *,
        transition_id: str,
        state_records: Mapping[str, Any],
        identity_claims: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> PreparedGovernanceTransition:
        if not isinstance(head, GovernanceHead):
            raise GovernanceError("prepared transition requires a governance head")
        return cls(
            domain=AuthorityDomain(head.scope_ref),
            stream=head.stream,
            transition_id=transition_id,
            expected_revision=head.revision,
            expected_parent_root=head.parent_root,
            expected_state_root=head.state_root,
            state_records=state_records,
            identity_claims=identity_claims or {},
        )

    def _root_payload(self) -> dict[str, Any]:
        return {
            "scope_ref": self.domain.scope_ref,
            "stream": self.stream,
            "transition_id": self.transition_id,
            "expected_revision": self.expected_revision,
            "expected_parent_root": self.expected_parent_root,
            "expected_state_root": self.expected_state_root,
            "state_records": _portable_json(self.state_records),
            "identity_claims": _portable_json(self.identity_claims),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": _TRANSITION_SCHEMA,
            "domain": self.domain.to_dict(),
            **self._root_payload(),
            "state_root": self.state_root,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PreparedGovernanceTransition:
        _require_exact_fields(
            payload,
            {
                "schema",
                "domain",
                "scope_ref",
                "stream",
                "transition_id",
                "expected_revision",
                "expected_parent_root",
                "expected_state_root",
                "state_records",
                "identity_claims",
                "state_root",
            },
            _TRANSITION_SCHEMA,
        )
        if payload["schema"] != _TRANSITION_SCHEMA:
            raise GovernanceError("prepared transition schema is unsupported")
        domain_payload = payload["domain"]
        if not isinstance(domain_payload, Mapping):
            raise GovernanceError("prepared transition domain must be an object")
        domain = AuthorityDomain.from_dict(domain_payload)
        if payload["scope_ref"] != domain.scope_ref:
            raise GovernanceError("prepared transition scope does not match its domain")
        return cls(
            domain=domain,
            stream=payload["stream"],
            transition_id=payload["transition_id"],
            expected_revision=payload["expected_revision"],
            expected_parent_root=payload["expected_parent_root"],
            expected_state_root=payload["expected_state_root"],
            state_records=payload["state_records"],
            identity_claims=payload["identity_claims"],
            state_root=payload["state_root"],
        )

    def fingerprint(self) -> str:
        return _fingerprint(_TRANSITION_SCHEMA, self.to_dict())


@dataclass(frozen=True)
class GovernanceCommitBatch:
    """One state transition and its trace records committed atomically."""

    transition: PreparedGovernanceTransition
    trace_records: Sequence[Mapping[str, Any]]
    trace_root: str = ""
    batch_root: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.transition, PreparedGovernanceTransition):
            raise GovernanceError("governance commit batch transition is invalid")
        if not isinstance(self.trace_records, Sequence) or isinstance(
            self.trace_records,
            (str, bytes, bytearray),
        ):
            raise GovernanceError("governance commit trace records must be a sequence")
        if not self.trace_records:
            raise GovernanceError("governance commit batch requires at least one trace record")
        records: list[Mapping[str, Any]] = []
        trace_ids: set[str] = set()
        for index, record in enumerate(self.trace_records):
            if not isinstance(record, Mapping):
                raise GovernanceError("governance trace record must be a mapping")
            frozen = _freeze_json(record, path=f"trace_records[{index}]")
            if not isinstance(frozen, Mapping):  # pragma: no cover - guarded above
                raise GovernanceError("governance trace record must be a mapping")
            trace_id = frozen.get("trace_id")
            _require_identity(trace_id, "governance trace record id")
            if trace_id in trace_ids:
                raise GovernanceError("governance commit batch trace ids must be unique")
            trace_ids.add(trace_id)
            if frozen.get("scope_ref") != self.transition.domain.scope_ref:
                raise GovernanceError("governance trace record crosses authority scope")
            if frozen.get("stream") != self.transition.stream:
                raise GovernanceError("governance trace record crosses authority stream")
            if frozen.get("transition_id") != self.transition.transition_id:
                raise GovernanceError("governance trace record transition id is mismatched")
            records.append(frozen)
        object.__setattr__(self, "trace_records", tuple(records))
        computed_trace = _fingerprint(
            "pheroos-governance-trace-batch-v1",
            {"records": _portable_json(records)},
        )
        if self.trace_root and self.trace_root != computed_trace:
            raise GovernanceError("governance commit trace root does not match its records")
        object.__setattr__(self, "trace_root", computed_trace)
        computed_batch = _fingerprint(_BATCH_SCHEMA, self._root_payload())
        if self.batch_root and self.batch_root != computed_batch:
            raise GovernanceError("governance commit batch root does not match its payload")
        object.__setattr__(self, "batch_root", computed_batch)

    def _root_payload(self) -> dict[str, Any]:
        return {
            "transition": self.transition.to_dict(),
            "trace_records": _portable_json(self.trace_records),
            "trace_root": self.trace_root,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": _BATCH_SCHEMA,
            **self._root_payload(),
            "batch_root": self.batch_root,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> GovernanceCommitBatch:
        _require_exact_fields(
            payload,
            {"schema", "transition", "trace_records", "trace_root", "batch_root"},
            _BATCH_SCHEMA,
        )
        if payload["schema"] != _BATCH_SCHEMA:
            raise GovernanceError("governance commit batch schema is unsupported")
        transition_payload = payload["transition"]
        if not isinstance(transition_payload, Mapping):
            raise GovernanceError("governance commit batch transition must be an object")
        return cls(
            transition=PreparedGovernanceTransition.from_dict(transition_payload),
            trace_records=payload["trace_records"],
            trace_root=payload["trace_root"],
            batch_root=payload["batch_root"],
        )

    def fingerprint(self) -> str:
        return self.batch_root


@dataclass(frozen=True)
class GovernanceCommitReceipt:
    """Portable proof that one exact state+trace batch was atomically committed."""

    scope_ref: str
    stream: str
    transition_id: str
    revision: int
    parent_root: str
    state_root: str
    trace_root: str
    batch_root: str
    receipt_root: str = ""

    def __post_init__(self) -> None:
        _require_scope_ref(self.scope_ref, "governance receipt scope_ref")
        _require_identity(self.stream, "governance receipt stream")
        _require_identity(self.transition_id, "governance receipt transition id")
        if type(self.revision) is not int or self.revision < 1:
            raise GovernanceError("governance receipt revision must be a positive integer")
        for name, root in (
            ("parent_root", self.parent_root),
            ("state_root", self.state_root),
            ("trace_root", self.trace_root),
            ("batch_root", self.batch_root),
        ):
            _require_digest(root, f"governance receipt {name}")
        computed = _fingerprint(_RECEIPT_SCHEMA, self._root_payload())
        if self.receipt_root and self.receipt_root != computed:
            raise GovernanceError("governance receipt root does not match its payload")
        object.__setattr__(self, "receipt_root", computed)

    def _root_payload(self) -> dict[str, Any]:
        return {
            "scope_ref": self.scope_ref,
            "stream": self.stream,
            "transition_id": self.transition_id,
            "revision": self.revision,
            "parent_root": self.parent_root,
            "state_root": self.state_root,
            "trace_root": self.trace_root,
            "batch_root": self.batch_root,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": _RECEIPT_SCHEMA,
            **self._root_payload(),
            "receipt_root": self.receipt_root,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> GovernanceCommitReceipt:
        _require_exact_fields(
            payload,
            {
                "schema",
                "scope_ref",
                "stream",
                "transition_id",
                "revision",
                "parent_root",
                "state_root",
                "trace_root",
                "batch_root",
                "receipt_root",
            },
            _RECEIPT_SCHEMA,
        )
        if payload["schema"] != _RECEIPT_SCHEMA:
            raise GovernanceError("governance commit receipt schema is unsupported")
        return cls(
            scope_ref=payload["scope_ref"],
            stream=payload["stream"],
            transition_id=payload["transition_id"],
            revision=payload["revision"],
            parent_root=payload["parent_root"],
            state_root=payload["state_root"],
            trace_root=payload["trace_root"],
            batch_root=payload["batch_root"],
            receipt_root=payload["receipt_root"],
        )

    def matches(self, batch: GovernanceCommitBatch) -> bool:
        transition = batch.transition
        return (
            self.scope_ref == transition.domain.scope_ref
            and self.stream == transition.stream
            and self.transition_id == transition.transition_id
            and self.revision == transition.expected_revision + 1
            and self.parent_root == transition.expected_state_root
            and self.state_root == transition.state_root
            and self.trace_root == batch.trace_root
            and self.batch_root == batch.batch_root
        )

    def fingerprint(self) -> str:
        return self.receipt_root


@runtime_checkable
class GovernanceStateStore(Protocol):
    """Provider-neutral durable-state contract required by Governance."""

    def load_head(self, scope_ref: str, stream: str) -> GovernanceHead: ...

    def load_state(self, scope_ref: str, stream: str) -> Mapping[str, Any]: ...

    def trace_records(
        self,
        scope_ref: str,
        stream: str,
    ) -> tuple[Mapping[str, Any], ...]: ...

    def load_receipt(
        self,
        scope_ref: str,
        transition_id: str,
    ) -> GovernanceCommitReceipt | None: ...

    def claim_identity(
        self,
        scope_ref: str,
        identity_id: str,
        body: Mapping[str, Any],
    ) -> str: ...

    def compare_and_advance(
        self,
        batch: GovernanceCommitBatch,
    ) -> GovernanceCommitReceipt: ...

    def atomic_commit(
        self,
        batch: GovernanceCommitBatch,
    ) -> GovernanceCommitReceipt: ...

    def checkpoint(self, scope_ref: str) -> Mapping[str, Any]: ...

    def rehydrate(self, payload: Mapping[str, Any]) -> tuple[GovernanceHead, ...]: ...

    def rehydrate_snapshot(self, payload: Mapping[str, Any]) -> None: ...

    def retire(self, scope_ref: str) -> str: ...

    def snapshot(self) -> Mapping[str, Any]: ...

    def fingerprint(self) -> str: ...


def _require_identity(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise GovernanceError(f"{field_name} must be canonical non-blank text")
    return value


def _require_digest(value: object, field_name: str) -> str:
    if not is_canonical_sha256_fingerprint(value):
        raise GovernanceError(f"{field_name} must be a canonical SHA-256 digest")
    return value


def _require_scope_ref(value: object, field_name: str) -> str:
    """Validate an opaque canonical scope reference without deriving its identity."""

    return _require_digest(value, field_name)


def _freeze_json(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not isfinite(value):
            raise GovernanceError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        if not all(isinstance(key, str) and key for key in value):
            raise GovernanceError(f"{path} keys must be non-empty strings")
        for key in sorted(value):
            item = value[key]
            frozen[key] = _freeze_json(item, path=f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(
            _freeze_json(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    raise GovernanceError(f"{path} contains unsupported value type: {type(value).__name__}")


def _portable_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) and key for key in value):
            raise GovernanceError(
                "portable Governance payload keys must be non-empty strings"
            )
        return {key: _portable_json(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_portable_json(item) for item in value]
    if value is None or isinstance(value, (bool, str)):
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not isfinite(value):
            raise GovernanceError("portable Governance payload contains a non-finite number")
        return value
    raise GovernanceError(
        "portable Governance payload contains unsupported value type: "
        f"{type(value).__name__}"
    )


def _fingerprint(schema: str, payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        {"payload": _portable_json(payload), "schema": schema},
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


def _require_exact_fields(
    payload: Mapping[str, Any],
    fields: set[str],
    label: str,
) -> None:
    if not isinstance(payload, Mapping) or set(payload) != fields:
        raise GovernanceError(f"{label} must contain its exact declared fields")


__all__ = [
    "AUTHORITY_LEDGER_VERSION",
    "AuthorityDomain",
    "GovernanceCommitBatch",
    "GovernanceCommitReceipt",
    "GovernanceHead",
    "GovernanceStateStore",
    "PreparedGovernanceTransition",
]
