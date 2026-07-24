"""Portable complete-replacement StateStore contracts for Commit Evidence v2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import ClassVar

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2
from pheroos.protocol.commit_models import COMMIT_PROFILES_BY_ASSURANCE, CommitAssurance

from pheroos.governance._commit_evidence_projection_v2.common import (
    MAX_COMMIT_EVIDENCE_RECORDS_V2,
    canonical_roots_v2,
    evidence_root_v2,
    exact_array_v2,
    exact_object_v2,
    require_canonical_wire_v2,
    require_count_v2,
    require_root_v2,
    require_text_v2,
)
from pheroos.governance._commit_evidence_projection_v2.records import (
    CommitEvidencePolicySnapshotV2,
    CommitEvidenceStatusV2,
    QualifiedCommitEvidenceV2,
    canonical_qualified_evidence_v2,
)
from pheroos.governance._commit_evidence_owner_v2.contract_fields import (
    _REQUEST_FIELDS,
    _SNAPSHOT_ARRAY_FIELDS,
    _SNAPSHOT_BODY_FIELDS,
    _SNAPSHOT_COUNT_FIELDS,
    _SNAPSHOT_FIELDS,
    _SNAPSHOT_ROOT_FIELDS,
    _SNAPSHOT_TEXT_FIELDS,
)


COMMIT_EVIDENCE_SNAPSHOT_SCHEMA_V2 = "pheroos-commit-evidence-snapshot-v2"
COMMIT_EVIDENCE_STATE_SCHEMA_V2 = "pheroos-commit-evidence-state-v2"
COMMIT_EVIDENCE_ADVANCE_REQUEST_SCHEMA_V2 = "pheroos-commit-evidence-advance-request-v2"
MAX_COMMIT_EVIDENCE_SNAPSHOT_BYTES_V2 = 32 * 1024 * 1024


COMMIT_EVIDENCE_GENESIS_TRANSITION_ID_V2 = "genesis"
COMMIT_EVIDENCE_GENESIS_SNAPSHOT_ROOT_V2 = evidence_root_v2(
    "genesis-parent",
    {
        "schema": COMMIT_EVIDENCE_SNAPSHOT_SCHEMA_V2,
        "canonical_version": AUTHORITY_CANONICAL_VERSION_V2,
    },
)
COMMIT_EVIDENCE_GENESIS_HISTORY_ROOT_V2 = evidence_root_v2(
    "history-genesis", {"canonical_version": AUTHORITY_CANONICAL_VERSION_V2}
)


def commit_evidence_stream_ref_v2(
    scope_ref: str,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
) -> str:
    """Return the sole Evidence stream for one scoped run target."""

    material = tuple(
        require_text_v2(value, f"commit evidence stream {label}")
        for label, value in (
            ("scope_ref", scope_ref),
            ("protocol_ref", protocol_ref),
            ("run_ref", run_ref),
            ("target_ref", target_ref),
        )
    )
    digest = sha256("\x00".join(material).encode("utf-8")).hexdigest()
    return f"authority:commit-evidence-v2:{digest}"


def commit_evidence_transition_id_v2(stream_ref: str, advance_ref: str) -> str:
    stream = require_text_v2(stream_ref, "commit evidence transition stream_ref")
    advance = require_text_v2(advance_ref, "commit evidence transition advance_ref")
    digest = sha256(f"{stream}\x00{advance}".encode("utf-8")).hexdigest()
    return f"transition:commit-evidence-v2:{digest}"


def commit_evidence_history_advance_v2(
    *,
    parent_history_root: str,
    parent_history_count: int,
    transition_id: str,
    mutation_delta_root: str,
) -> str:
    require_root_v2(parent_history_root, "commit evidence parent_history_root")
    require_count_v2(parent_history_count, "commit evidence parent_history_count")
    require_text_v2(transition_id, "commit evidence history transition_id")
    require_root_v2(mutation_delta_root, "commit evidence mutation_delta_root")
    return evidence_root_v2(
        "history-successor",
        {
            "parent_history_root": parent_history_root,
            "parent_history_count": parent_history_count,
            "transition_id": transition_id,
            "mutation_delta_root": mutation_delta_root,
        },
    )


@dataclass(frozen=True, slots=True)
class CommitEvidenceSnapshotV2:
    domain_root: str
    scope_ref: str
    profile: str
    assurance: CommitAssurance
    authority_policy_root: str
    manifest_root: str
    commit_policy_root: str
    evidence_policy: CommitEvidencePolicySnapshotV2
    protocol_ref: str
    run_ref: str
    target_ref: str
    epoch: int
    observed_epoch: int
    advance_ref: str
    stream_ref: str
    transition_id: str
    revision: int
    initialized_at_step: int
    current_step: int
    expires_at_step: int
    parent_revision: int
    parent_epoch: int | None
    parent_transition_id: str
    parent_snapshot_root: str
    parent_history_root: str
    parent_history_count: int
    mutation_issuer_ref: str
    mutation_provenance_root: str
    mutation_trace_roots: Sequence[str]
    membership_stream_ref: str
    membership_transition_id: str
    membership_revision: int
    membership_head_root: str
    membership_snapshot_root: str
    membership_root: str
    membership_current_step: int
    membership_expires_at_step: int
    verification_stream_ref: str
    verification_transition_id: str
    verification_revision: int
    verification_head_root: str
    verification_snapshot_root: str
    verification_set_root: str
    verification_current_step: int
    verification_expires_at_step: int
    replay_stream_ref: str
    replay_transition_id: str
    replay_revision: int
    replay_head_root: str
    replay_snapshot_root: str
    replay_receipt_root: str
    replay_current_step: int
    records: Sequence[QualifiedCommitEvidenceV2]
    mutation_record_roots: Sequence[str]
    removed_record_roots: Sequence[str]
    revocation_roots: Sequence[str]
    record_count: int
    active_record_count: int
    record_set_root: str = ""
    active_record_set_root: str = ""
    mutation_delta_root: str = ""
    history_root: str = ""
    history_count: int = 0
    schema: str = COMMIT_EVIDENCE_SNAPSHOT_SCHEMA_V2
    state_schema: str = COMMIT_EVIDENCE_STATE_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    snapshot_root: str = ""

    _root_field: ClassVar[str] = "snapshot_root"

    def __post_init__(self) -> None:
        _validate_snapshot_context(self)
        records = canonical_qualified_evidence_v2(self.records)
        object.__setattr__(self, "records", records)
        for field in (
            "mutation_trace_roots",
            "mutation_record_roots",
            "removed_record_roots",
            "revocation_roots",
        ):
            roots = canonical_roots_v2(
                getattr(self, field),
                f"commit evidence snapshot {field}",
                allow_empty=field != "mutation_trace_roots",
                limit=MAX_COMMIT_EVIDENCE_RECORDS_V2,
            )
            object.__setattr__(self, field, roots)
        _validate_snapshot_counts(self, records)
        _install_snapshot_roots(self, records)
        if len(self.canonical_bytes()) > MAX_COMMIT_EVIDENCE_SNAPSHOT_BYTES_V2:
            raise ValueError("commit evidence snapshot exceeds its byte bound")

    def _body(self) -> dict[str, object]:
        body = {field: getattr(self, field) for field in _SNAPSHOT_BODY_FIELDS}
        body["assurance"] = self.assurance.value
        body["evidence_policy"] = self.evidence_policy.to_dict()
        body["records"] = [item.to_dict() for item in self.records]
        for field in _SNAPSHOT_ARRAY_FIELDS:
            body[field] = list(getattr(self, field))
        return body

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "snapshot_root": self.snapshot_root}

    def canonical_bytes(self) -> bytes:
        import json

        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    def root(self) -> str:
        return self.snapshot_root

    @classmethod
    def from_dict(cls, payload: object) -> CommitEvidenceSnapshotV2:
        value = exact_object_v2(
            payload, _SNAPSHOT_FIELDS, "commit evidence snapshot v2"
        )
        try:
            value["assurance"] = CommitAssurance(value["assurance"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "commit evidence snapshot assurance is unsupported"
            ) from exc
        value["evidence_policy"] = CommitEvidencePolicySnapshotV2.from_dict(
            value["evidence_policy"]
        )
        value["records"] = tuple(
            QualifiedCommitEvidenceV2.from_dict(item)
            for item in exact_array_v2(
                value["records"],
                "commit evidence snapshot records",
                limit=MAX_COMMIT_EVIDENCE_RECORDS_V2,
            )
        )
        for field in _SNAPSHOT_ARRAY_FIELDS:
            value[field] = tuple(
                exact_array_v2(
                    value[field],
                    f"commit evidence snapshot {field}",
                    limit=MAX_COMMIT_EVIDENCE_RECORDS_V2,
                )
            )
        decoded = cls(**value)
        require_canonical_wire_v2(
            payload, decoded.to_dict(), "commit evidence snapshot v2"
        )
        return decoded


@dataclass(frozen=True, slots=True)
class CommitEvidenceAdvanceRequestV2:
    domain_root: str
    scope_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    advance_ref: str
    stream_ref: str
    transition_id: str
    snapshot: CommitEvidenceSnapshotV2
    schema: str = COMMIT_EVIDENCE_ADVANCE_REQUEST_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    request_root: str = ""

    def __post_init__(self) -> None:
        if (
            self.schema != COMMIT_EVIDENCE_ADVANCE_REQUEST_SCHEMA_V2
            or self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2
        ):
            raise ValueError("commit evidence request version is unsupported")
        if type(self.snapshot) is not CommitEvidenceSnapshotV2:
            raise TypeError("commit evidence request requires exact snapshot v2")
        for field in (
            "domain_root",
            "scope_ref",
            "run_ref",
            "target_ref",
            "observed_epoch",
            "advance_ref",
            "stream_ref",
            "transition_id",
        ):
            if getattr(self, field) != getattr(self.snapshot, field):
                raise ValueError(f"commit evidence request {field} is cross-bound")
        expected = evidence_root_v2("advance-request", self._body())
        if self.request_root not in ("", expected):
            raise ValueError("commit evidence request_root is mismatched")
        object.__setattr__(self, "request_root", expected)

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
            "stream_ref": self.stream_ref,
            "transition_id": self.transition_id,
            "snapshot": self.snapshot.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "request_root": self.request_root}

    def canonical_bytes(self) -> bytes:
        import json

        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    def root(self) -> str:
        return self.request_root

    @classmethod
    def from_dict(cls, payload: object) -> CommitEvidenceAdvanceRequestV2:
        value = exact_object_v2(payload, _REQUEST_FIELDS, "commit evidence request v2")
        value["snapshot"] = CommitEvidenceSnapshotV2.from_dict(value["snapshot"])
        decoded = cls(**value)
        require_canonical_wire_v2(
            payload, decoded.to_dict(), "commit evidence request v2"
        )
        return decoded


def active_qualified_evidence_v2(
    snapshot: CommitEvidenceSnapshotV2,
) -> tuple[QualifiedCommitEvidenceV2, ...]:
    if type(snapshot) is not CommitEvidenceSnapshotV2:
        raise TypeError("active evidence projection requires exact snapshot v2")
    return tuple(
        item
        for item in snapshot.records
        if item.status is CommitEvidenceStatusV2.ACTIVE
        and item.epoch == snapshot.epoch
        and item.qualification_policy_root == snapshot.evidence_policy.policy_root
        and item.membership_root == snapshot.membership_root
        and item.verification_set_root == snapshot.verification_set_root
        and item.observed_at_step <= snapshot.current_step < item.expires_at_step
    )


def _validate_snapshot_context(snapshot: CommitEvidenceSnapshotV2) -> None:
    if (
        snapshot.schema != COMMIT_EVIDENCE_SNAPSHOT_SCHEMA_V2
        or snapshot.state_schema != COMMIT_EVIDENCE_STATE_SCHEMA_V2
        or snapshot.canonical_version != AUTHORITY_CANONICAL_VERSION_V2
    ):
        raise ValueError("commit evidence snapshot version is unsupported")
    if type(snapshot.evidence_policy) is not CommitEvidencePolicySnapshotV2:
        raise TypeError("commit evidence snapshot policy is invalid")
    if (
        type(snapshot.assurance) is not CommitAssurance
        or snapshot.profile
        not in COMMIT_PROFILES_BY_ASSURANCE.get(snapshot.assurance.value, frozenset())
    ):
        raise ValueError("commit evidence snapshot profile is mismatched")
    for field in _SNAPSHOT_ROOT_FIELDS:
        require_root_v2(getattr(snapshot, field), f"commit evidence snapshot {field}")
    for field in _SNAPSHOT_TEXT_FIELDS:
        require_text_v2(getattr(snapshot, field), f"commit evidence snapshot {field}")
    for field in _SNAPSHOT_COUNT_FIELDS:
        require_count_v2(getattr(snapshot, field), f"commit evidence snapshot {field}")
    if snapshot.parent_epoch is not None:
        require_count_v2(snapshot.parent_epoch, "commit evidence snapshot parent_epoch")
    if snapshot.expires_at_step <= snapshot.current_step:
        raise ValueError("commit evidence snapshot dependencies are expired")
    expected_stream = commit_evidence_stream_ref_v2(
        snapshot.scope_ref,
        snapshot.protocol_ref,
        snapshot.run_ref,
        snapshot.target_ref,
    )
    expected_transition = commit_evidence_transition_id_v2(
        expected_stream, snapshot.advance_ref
    )
    if (
        snapshot.stream_ref != expected_stream
        or snapshot.transition_id != expected_transition
    ):
        raise ValueError("commit evidence snapshot lineage identity is mismatched")


def _validate_snapshot_counts(
    snapshot: CommitEvidenceSnapshotV2,
    records: tuple[QualifiedCommitEvidenceV2, ...],
) -> None:
    active = active_qualified_evidence_v2(snapshot)
    if snapshot.record_count != len(records) or snapshot.active_record_count != len(
        active
    ):
        raise ValueError("commit evidence snapshot record counts are mismatched")
    if snapshot.revision != snapshot.parent_revision + 1:
        raise ValueError("commit evidence snapshot revision is not contiguous")
    if snapshot.revision == 1:
        valid_genesis = (
            snapshot.parent_revision == 0
            and snapshot.parent_epoch is None
            and snapshot.parent_transition_id
            == COMMIT_EVIDENCE_GENESIS_TRANSITION_ID_V2
            and snapshot.parent_snapshot_root
            == COMMIT_EVIDENCE_GENESIS_SNAPSHOT_ROOT_V2
            and snapshot.parent_history_root == COMMIT_EVIDENCE_GENESIS_HISTORY_ROOT_V2
            and snapshot.parent_history_count == 0
            and snapshot.initialized_at_step == snapshot.current_step
        )
        if not valid_genesis:
            raise ValueError("commit evidence genesis continuity is invalid")
    elif (
        snapshot.parent_epoch is None
        or snapshot.epoch < snapshot.parent_epoch
        or snapshot.parent_transition_id == COMMIT_EVIDENCE_GENESIS_TRANSITION_ID_V2
        or snapshot.parent_history_count != snapshot.revision - 1
    ):
        raise ValueError("commit evidence successor continuity is invalid")


def _install_snapshot_roots(
    snapshot: CommitEvidenceSnapshotV2,
    records: tuple[QualifiedCommitEvidenceV2, ...],
) -> None:
    active = active_qualified_evidence_v2(snapshot)
    roots = {
        "record_set_root": evidence_root_v2(
            "record-set", {"records": [item.record_root for item in records]}
        ),
        "active_record_set_root": evidence_root_v2(
            "active-record-set", {"records": [item.record_root for item in active]}
        ),
    }
    roots["mutation_delta_root"] = evidence_root_v2(
        "mutation-delta",
        {
            "transition_id": snapshot.transition_id,
            "mutation_issuer_ref": snapshot.mutation_issuer_ref,
            "mutation_provenance_root": snapshot.mutation_provenance_root,
            "mutation_trace_roots": list(snapshot.mutation_trace_roots),
            "mutation_record_roots": list(snapshot.mutation_record_roots),
            "removed_record_roots": list(snapshot.removed_record_roots),
            "revocation_roots": list(snapshot.revocation_roots),
            **roots,
        },
    )
    roots["history_root"] = commit_evidence_history_advance_v2(
        parent_history_root=snapshot.parent_history_root,
        parent_history_count=snapshot.parent_history_count,
        transition_id=snapshot.transition_id,
        mutation_delta_root=roots["mutation_delta_root"],
    )
    if snapshot.history_count != snapshot.parent_history_count + 1:
        raise ValueError("commit evidence history_count is not contiguous")
    for field, expected in roots.items():
        if getattr(snapshot, field) not in ("", expected):
            raise ValueError(f"commit evidence {field} is mismatched")
        object.__setattr__(snapshot, field, expected)
    expected_snapshot = evidence_root_v2("snapshot", snapshot._body())
    if snapshot.snapshot_root not in ("", expected_snapshot):
        raise ValueError("commit evidence snapshot_root is mismatched")
    object.__setattr__(snapshot, "snapshot_root", expected_snapshot)


__all__ = [
    "COMMIT_EVIDENCE_ADVANCE_REQUEST_SCHEMA_V2",
    "COMMIT_EVIDENCE_GENESIS_HISTORY_ROOT_V2",
    "COMMIT_EVIDENCE_GENESIS_SNAPSHOT_ROOT_V2",
    "COMMIT_EVIDENCE_GENESIS_TRANSITION_ID_V2",
    "COMMIT_EVIDENCE_SNAPSHOT_SCHEMA_V2",
    "COMMIT_EVIDENCE_STATE_SCHEMA_V2",
    "CommitEvidenceAdvanceRequestV2",
    "CommitEvidenceSnapshotV2",
    "active_qualified_evidence_v2",
    "commit_evidence_history_advance_v2",
    "commit_evidence_stream_ref_v2",
    "commit_evidence_transition_id_v2",
]
