"""Portable, target-scoped Commit Replay v2 contracts.

These records prove canonical integrity only.  Authority is established by the
StateStore-backed operations in :mod:`operations`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import ClassVar, cast

from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    MAX_AUTHORITY_REVISION_V2,
)
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CommitAssurance,
)

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _canonical_bytes,
    _compute_root,
    _require_root,
    _require_text,
)
from pheroos.governance._commit_replay_namespace import ReplayNamespace


COMMIT_REPLAY_RECEIPT_SCHEMA_V2 = "pheroos-commit-replay-receipt-v2"
COMMIT_REPLAY_SNAPSHOT_SCHEMA_V2 = "pheroos-commit-replay-snapshot-v2"
COMMIT_REPLAY_STATE_SCHEMA_V2 = "pheroos-commit-replay-state-v2"
COMMIT_REPLAY_ADVANCE_REQUEST_SCHEMA_V2 = "pheroos-commit-replay-advance-request-v2"
MAX_COMMIT_REPLAY_RECEIPTS_V2 = 4096
MAX_COMMIT_REPLAY_TEXT_BYTES_V2 = 4096
MAX_COMMIT_REPLAY_SNAPSHOT_BYTES_V2 = 8 * 1024 * 1024


def _root(kind: str, body: object) -> str:
    return _compute_root(f"commit-replay-v2:{kind}", body)


COMMIT_REPLAY_EMPTY_RECEIPT_ROOT_V2 = _root("receipt-set", {"receipts": []})
COMMIT_REPLAY_GENESIS_SNAPSHOT_ROOT_V2 = _root(
    "genesis-parent", {"version": COMMIT_REPLAY_SNAPSHOT_SCHEMA_V2}
)
COMMIT_REPLAY_GENESIS_TRANSITION_ID_V2 = "genesis"


def _require_bounded_text(
    value: object, label: str, *, allow_empty: bool = False
) -> str:
    if allow_empty and type(value) is str and value == "":
        return ""
    text = _require_text(value, label)
    if (
        len(text) > MAX_COMMIT_REPLAY_TEXT_BYTES_V2
        or len(text.encode("utf-8")) > MAX_COMMIT_REPLAY_TEXT_BYTES_V2
    ):
        raise ValueError(f"{label} exceeds the Commit Replay v2 text bound")
    return text


def _require_count(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= (value) <= MAX_AUTHORITY_REVISION_V2:
        raise ValueError(f"{label} is outside the authority integer bound")
    return value


def _require_exact_mapping(
    value: object, fields: frozenset[str], label: str
) -> dict[str, object]:
    if type(value) is not dict:
        raise TypeError(f"{label} must be an exact object")
    result = cast(dict[str, object], value).copy()
    if any(type(key) is not str for key in result) or set(result) != fields:
        raise ValueError(f"{label} fields are invalid")
    return result


def _require_canonical_wire(
    supplied: object,
    canonical: dict[str, object],
    label: str,
) -> None:
    if type(supplied) is not dict or supplied != canonical:
        raise ValueError(f"{label} is not canonical wire")


def _require_exact_version(value: object, expected: str, label: str) -> None:
    if type(value) is not str or value != expected:
        raise ValueError(f"{label} is unsupported")


def _install_exact_root(
    instance: object,
    attribute: str,
    supplied: object,
    kind: str,
    body: object,
) -> None:
    expected = _root(kind, body)
    if supplied not in ("", expected):
        raise ValueError(f"{attribute} is mismatched")
    object.__setattr__(instance, attribute, expected)


def commit_replay_stream_ref_v2(
    scope_ref: str,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
) -> str:
    """Return the sole replay stream for one scoped run target."""

    values = []
    for label, value in (
        ("scope_ref", scope_ref),
        ("protocol_ref", protocol_ref),
        ("run_ref", run_ref),
        ("target_ref", target_ref),
    ):
        values.append(_require_bounded_text(value, f"commit replay {label}"))
    digest = sha256("\x00".join(values).encode("utf-8")).hexdigest()
    return f"authority:commit-replay-v2:{digest}"


def commit_replay_transition_id_v2(stream_ref: str, advance_ref: str) -> str:
    stream = _require_bounded_text(stream_ref, "commit replay transition stream_ref")
    advance = _require_bounded_text(advance_ref, "commit replay advance_ref")
    digest = sha256(
        stream.encode("utf-8") + b"\x00" + advance.encode("utf-8")
    ).hexdigest()
    return f"transition:commit-replay-v2:{digest}"


@dataclass(frozen=True, slots=True)
class CommitReplayReceiptV2:
    """Portable replay identity with three mutually exclusive collision axes."""

    namespace: ReplayNamespace
    record_id: str
    nonce: str
    payload_fingerprint: str
    target_ref: str
    candidate_ref: str
    epoch: int
    principal_ref: str
    schema: str = COMMIT_REPLAY_RECEIPT_SCHEMA_V2
    receipt_root: str = ""

    _root_field: ClassVar[str] = "receipt_root"

    def __post_init__(self) -> None:
        _require_exact_version(
            self.schema, COMMIT_REPLAY_RECEIPT_SCHEMA_V2, "commit replay receipt schema"
        )
        if type(self.namespace) is not ReplayNamespace:
            raise TypeError("commit replay receipt namespace is invalid")
        for field in ("record_id", "nonce", "target_ref"):
            _require_bounded_text(
                getattr(self, field), f"commit replay receipt {field}"
            )
        for field in ("candidate_ref", "principal_ref"):
            _require_bounded_text(
                getattr(self, field),
                f"commit replay receipt {field}",
                allow_empty=True,
            )
        _require_root(
            self.payload_fingerprint, "commit replay receipt payload_fingerprint"
        )
        _require_count(self.epoch, "commit replay receipt epoch")
        _install_exact_root(
            self, "receipt_root", self.receipt_root, "receipt", self._body()
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "namespace": self.namespace.value,
            "record_id": self.record_id,
            "nonce": self.nonce,
            "payload_fingerprint": self.payload_fingerprint,
            "target_ref": self.target_ref,
            "candidate_ref": self.candidate_ref,
            "epoch": self.epoch,
            "principal_ref": self.principal_ref,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "receipt_root": self.receipt_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.receipt_root

    @classmethod
    def from_dict(cls, payload: object) -> CommitReplayReceiptV2:
        value = _require_exact_mapping(
            payload,
            frozenset(
                {
                    "schema",
                    "namespace",
                    "record_id",
                    "nonce",
                    "payload_fingerprint",
                    "target_ref",
                    "candidate_ref",
                    "epoch",
                    "principal_ref",
                    "receipt_root",
                }
            ),
            "commit replay receipt v2",
        )
        try:
            if type(value["namespace"]) is not str:
                raise ValueError
            value["namespace"] = ReplayNamespace((value["namespace"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("commit replay receipt namespace is unsupported") from exc
        decoded = cls(**value)  # type: ignore[arg-type]
        _require_canonical_wire(payload, decoded.to_dict(), "commit replay receipt v2")
        return decoded


def canonical_commit_replay_receipts_v2(
    receipts: Sequence[CommitReplayReceiptV2],
) -> tuple[CommitReplayReceiptV2, ...]:
    if type(receipts) not in (list, tuple):
        raise TypeError("commit replay receipts must be an exact array or tuple")
    if len(receipts) > MAX_COMMIT_REPLAY_RECEIPTS_V2:
        raise ValueError("commit replay receipt count exceeds its bound")
    values = tuple(receipts)
    if any(type(item) is not CommitReplayReceiptV2 for item in values):
        raise TypeError("commit replay receipts contain a non-canonical record")
    ordered = tuple(sorted(values, key=lambda item: item.receipt_root))
    by_nonce: dict[str, CommitReplayReceiptV2] = {}
    by_id: dict[tuple[ReplayNamespace, str], CommitReplayReceiptV2] = {}
    by_payload: dict[str, CommitReplayReceiptV2] = {}
    unique: list[CommitReplayReceiptV2] = []
    for receipt in ordered:
        collisions = tuple(
            existing
            for existing in (
                by_nonce.get(receipt.nonce),
                by_id.get((receipt.namespace, receipt.record_id)),
                by_payload.get(receipt.payload_fingerprint),
            )
            if existing is not None
        )
        if collisions:
            if any(existing != receipt for existing in collisions):
                raise ValueError(
                    "commit replay receipt collision is a safety violation"
                )
            continue
        by_nonce[receipt.nonce] = receipt
        by_id[(receipt.namespace, receipt.record_id)] = receipt
        by_payload[receipt.payload_fingerprint] = receipt
        unique.append(receipt)
    return tuple(unique)


def _preflight_receipt_bytes_v2(
    receipts: Sequence[CommitReplayReceiptV2],
) -> None:
    if type(receipts) not in (list, tuple):
        raise TypeError("commit replay receipts must be an exact array or tuple")
    if len(receipts) > MAX_COMMIT_REPLAY_RECEIPTS_V2:
        raise ValueError("commit replay receipt count exceeds its bound")
    total = 0
    for item in receipts:
        if type(item) is not CommitReplayReceiptV2:
            raise TypeError("commit replay receipts contain a non-canonical record")
        total += len(item.canonical_bytes())
        if total > MAX_COMMIT_REPLAY_SNAPSHOT_BYTES_V2:
            raise ValueError("commit replay receipt bytes exceed the snapshot bound")


def commit_replay_receipt_set_root_v2(
    receipts: Sequence[CommitReplayReceiptV2],
) -> str:
    canonical = canonical_commit_replay_receipts_v2(receipts)
    return _root("receipt-set", {"receipts": [item.receipt_root for item in canonical]})


def _validate_snapshot_versions_and_bindings(
    snapshot: CommitReplaySnapshotV2,
) -> None:
    _require_exact_version(
        snapshot.schema,
        COMMIT_REPLAY_SNAPSHOT_SCHEMA_V2,
        "commit replay snapshot schema",
    )
    _require_exact_version(
        snapshot.state_schema,
        COMMIT_REPLAY_STATE_SCHEMA_V2,
        "commit replay state schema",
    )
    _require_exact_version(
        snapshot.canonical_version,
        AUTHORITY_CANONICAL_VERSION_V2,
        "commit replay canonical version",
    )
    _require_root(snapshot.domain_root, "commit replay domain_root")
    _require_root(snapshot.manifest_root, "commit replay manifest_root")
    _require_root(snapshot.commit_policy_root, "commit replay commit_policy_root")
    for field in (
        "scope_ref",
        "profile",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "stream_ref",
        "advance_ref",
        "transition_id",
    ):
        _require_bounded_text(getattr(snapshot, field), f"commit replay {field}")
    if type(snapshot.assurance) is not CommitAssurance:
        raise TypeError("commit replay assurance is invalid")
    allowed = COMMIT_PROFILES_BY_ASSURANCE.get(snapshot.assurance.value, frozenset())
    if snapshot.profile not in allowed:
        raise ValueError("commit replay profile and assurance are mismatched")
    for field in (
        "observed_epoch",
        "revision",
        "initialized_at_step",
        "current_step",
        "parent_revision",
    ):
        _require_count(getattr(snapshot, field), f"commit replay {field}")


def _validate_snapshot_continuity(snapshot: CommitReplaySnapshotV2) -> None:
    if snapshot.revision < 1 or snapshot.current_step < snapshot.initialized_at_step:
        raise ValueError("commit replay revision or step continuity is invalid")
    if snapshot.parent_revision != snapshot.revision - 1:
        raise ValueError("commit replay parent revision is not contiguous")
    if snapshot.revision == 1:
        if snapshot.parent_transition_id != COMMIT_REPLAY_GENESIS_TRANSITION_ID_V2:
            raise ValueError("commit replay genesis parent transition is mismatched")
        if snapshot.parent_snapshot_root != COMMIT_REPLAY_GENESIS_SNAPSHOT_ROOT_V2:
            raise ValueError("commit replay genesis parent root is mismatched")
    else:
        _require_bounded_text(
            snapshot.parent_transition_id, "commit replay parent_transition_id"
        )
        _require_root(
            snapshot.parent_snapshot_root, "commit replay parent_snapshot_root"
        )
    expected_stream = commit_replay_stream_ref_v2(
        snapshot.scope_ref, snapshot.protocol_ref, snapshot.run_ref, snapshot.target_ref
    )
    expected_transition = commit_replay_transition_id_v2(
        expected_stream, snapshot.advance_ref
    )
    if (
        snapshot.stream_ref != expected_stream
        or snapshot.transition_id != expected_transition
    ):
        raise ValueError("commit replay stream or transition identity is mismatched")


@dataclass(frozen=True, slots=True)
class CommitReplaySnapshotV2:
    """Complete replacement snapshot for one durable replay lineage."""

    domain_root: str
    scope_ref: str
    manifest_root: str
    commit_policy_root: str
    profile: str
    assurance: CommitAssurance
    protocol_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    stream_ref: str
    advance_ref: str
    transition_id: str
    revision: int
    initialized_at_step: int
    current_step: int
    parent_revision: int
    parent_transition_id: str
    parent_snapshot_root: str
    receipts: Sequence[CommitReplayReceiptV2]
    receipt_root: str = ""
    schema: str = COMMIT_REPLAY_SNAPSHOT_SCHEMA_V2
    state_schema: str = COMMIT_REPLAY_STATE_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    snapshot_root: str = ""

    _root_field: ClassVar[str] = "snapshot_root"

    def __post_init__(self) -> None:
        _validate_snapshot_versions_and_bindings(self)
        _validate_snapshot_continuity(self)
        _preflight_receipt_bytes_v2(self.receipts)
        canonical = canonical_commit_replay_receipts_v2(self.receipts)
        if any(item.target_ref != self.target_ref for item in canonical):
            raise ValueError("commit replay receipt target is mismatched")
        object.__setattr__(self, "receipts", canonical)
        expected_receipt_root = commit_replay_receipt_set_root_v2(canonical)
        if self.receipt_root not in ("", expected_receipt_root):
            raise ValueError("commit replay receipt_root is mismatched")
        object.__setattr__(self, "receipt_root", expected_receipt_root)
        _install_exact_root(
            self, "snapshot_root", self.snapshot_root, "snapshot", self._body()
        )
        if len(_canonical_bytes(self.to_dict())) > MAX_COMMIT_REPLAY_SNAPSHOT_BYTES_V2:
            raise ValueError("commit replay canonical snapshot exceeds its byte bound")

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "state_schema": self.state_schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "manifest_root": self.manifest_root,
            "commit_policy_root": self.commit_policy_root,
            "profile": self.profile,
            "assurance": self.assurance.value,
            "protocol_ref": self.protocol_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "observed_epoch": self.observed_epoch,
            "stream_ref": self.stream_ref,
            "advance_ref": self.advance_ref,
            "transition_id": self.transition_id,
            "revision": self.revision,
            "initialized_at_step": self.initialized_at_step,
            "current_step": self.current_step,
            "parent_revision": self.parent_revision,
            "parent_transition_id": self.parent_transition_id,
            "parent_snapshot_root": self.parent_snapshot_root,
            "receipts": [item.to_dict() for item in self.receipts],
            "receipt_root": self.receipt_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "snapshot_root": self.snapshot_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.snapshot_root

    @classmethod
    def from_dict(cls, payload: object) -> CommitReplaySnapshotV2:
        fields = frozenset(
            {
                "schema",
                "state_schema",
                "canonical_version",
                "domain_root",
                "scope_ref",
                "manifest_root",
                "commit_policy_root",
                "profile",
                "assurance",
                "protocol_ref",
                "run_ref",
                "target_ref",
                "observed_epoch",
                "stream_ref",
                "advance_ref",
                "transition_id",
                "revision",
                "initialized_at_step",
                "current_step",
                "parent_revision",
                "parent_transition_id",
                "parent_snapshot_root",
                "receipts",
                "receipt_root",
                "snapshot_root",
            }
        )
        value = _require_exact_mapping(payload, fields, "commit replay snapshot v2")
        try:
            value["assurance"] = CommitAssurance(cast(str, value["assurance"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("commit replay assurance is unsupported") from exc
        raw_receipts = value["receipts"]
        if type(raw_receipts) is not list:
            raise TypeError("commit replay receipts must be an exact array")
        if len(raw_receipts) > MAX_COMMIT_REPLAY_RECEIPTS_V2:
            raise ValueError("commit replay receipt count exceeds its bound")
        value["receipts"] = tuple(
            CommitReplayReceiptV2.from_dict(item) for item in raw_receipts
        )
        decoded = cls(**value)  # type: ignore[arg-type]
        _require_canonical_wire(payload, decoded.to_dict(), "commit replay snapshot v2")
        return decoded


@dataclass(frozen=True, slots=True)
class CommitReplayAdvanceRequestV2:
    """Idempotent request binding one complete next replay snapshot."""

    domain_root: str
    scope_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    advance_ref: str
    transition_id: str
    stream_ref: str
    snapshot: CommitReplaySnapshotV2
    schema: str = COMMIT_REPLAY_ADVANCE_REQUEST_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    request_root: str = ""

    _root_field: ClassVar[str] = "request_root"

    def __post_init__(self) -> None:
        _require_exact_version(
            self.schema,
            COMMIT_REPLAY_ADVANCE_REQUEST_SCHEMA_V2,
            "commit replay advance request schema",
        )
        _require_exact_version(
            self.canonical_version,
            AUTHORITY_CANONICAL_VERSION_V2,
            "commit replay advance request canonical version",
        )
        if type(self.snapshot) is not CommitReplaySnapshotV2:
            raise TypeError("commit replay request requires exact snapshot v2")
        for field in (
            "domain_root",
            "scope_ref",
            "run_ref",
            "target_ref",
            "observed_epoch",
            "advance_ref",
            "transition_id",
            "stream_ref",
        ):
            if getattr(self, field) != getattr(self.snapshot, field):
                raise ValueError(
                    f"commit replay request {field} is cross-bound incorrectly"
                )
        _install_exact_root(
            self, "request_root", self.request_root, "advance-request", self._body()
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "observed_epoch": self.observed_epoch,
            "advance_ref": self.advance_ref,
            "transition_id": self.transition_id,
            "stream_ref": self.stream_ref,
            "snapshot": self.snapshot.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "request_root": self.request_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def root(self) -> str:
        return self.request_root

    @classmethod
    def from_dict(cls, payload: object) -> CommitReplayAdvanceRequestV2:
        value = _require_exact_mapping(
            payload,
            frozenset(
                {
                    "schema",
                    "canonical_version",
                    "domain_root",
                    "scope_ref",
                    "run_ref",
                    "target_ref",
                    "observed_epoch",
                    "advance_ref",
                    "transition_id",
                    "stream_ref",
                    "snapshot",
                    "request_root",
                }
            ),
            "commit replay advance request v2",
        )
        value["snapshot"] = CommitReplaySnapshotV2.from_dict(value["snapshot"])
        decoded = cls(**value)  # type: ignore[arg-type]
        _require_canonical_wire(
            payload,
            decoded.to_dict(),
            "commit replay advance request v2",
        )
        return decoded


__all__ = [
    "COMMIT_REPLAY_ADVANCE_REQUEST_SCHEMA_V2",
    "COMMIT_REPLAY_EMPTY_RECEIPT_ROOT_V2",
    "COMMIT_REPLAY_GENESIS_SNAPSHOT_ROOT_V2",
    "COMMIT_REPLAY_GENESIS_TRANSITION_ID_V2",
    "COMMIT_REPLAY_RECEIPT_SCHEMA_V2",
    "COMMIT_REPLAY_SNAPSHOT_SCHEMA_V2",
    "COMMIT_REPLAY_STATE_SCHEMA_V2",
    "CommitReplayAdvanceRequestV2",
    "CommitReplayReceiptV2",
    "CommitReplaySnapshotV2",
    "canonical_commit_replay_receipts_v2",
    "commit_replay_receipt_set_root_v2",
    "commit_replay_stream_ref_v2",
    "commit_replay_transition_id_v2",
]
