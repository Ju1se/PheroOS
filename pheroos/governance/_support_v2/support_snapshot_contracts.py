"""Current authority projection and history commitment for Support v2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, TypedDict, cast

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2
from pheroos.protocol.commit_models import COMMIT_PROFILES_BY_ASSURANCE, CommitAssurance

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _canonical_bytes,
    _compute_root,
    _require_root,
)
from pheroos.governance._support_v2.common import (
    _require_bounded_text_v2,
    _require_canonical_wire_v2,
    _require_count_v2,
    _require_exact_array_v2,
    _require_exact_mapping_v2,
)
from pheroos.governance._support_v2.support_evidence_contracts import (
    _bounded_root_tuple,
)
from pheroos.governance._support_v2.support_lease_contracts import (
    MAX_SUPPORT_LEASES_V2,
    MAX_SUPPORT_TRACE_ROOTS_V2,
    SupportLeaseV2,
    SupportRevocationV2,
    canonical_support_leases_v2,
)
from pheroos.governance._support_v2.support_stream_contracts import (
    SUPPORT_GENESIS_HISTORY_ROOT_V2,
    SUPPORT_GENESIS_TRANSITION_ID_V2,
    SupportMutationKindV2,
    support_history_advance_v2,
    support_stream_ref_v2,
    support_transition_id_v2,
)


SUPPORT_SNAPSHOT_SCHEMA_V2 = "pheroos-support-snapshot-v2"
SUPPORT_STATE_SCHEMA_V2 = "pheroos-support-state-v2"
MAX_SUPPORT_SNAPSHOT_BYTES_V2 = 16 * 1024 * 1024


class _SupportSnapshotDecodedV2(TypedDict):
    domain_root: str
    scope_ref: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    authority_policy_root: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    stream_ref: str
    mutation_ref: str
    transition_id: str
    mutation_kind: SupportMutationKindV2
    revision: int
    initialized_at_step: int
    current_step: int
    mutation_issuer_ref: str
    mutation_provenance_root: str
    mutation_trace_roots: tuple[str, ...]
    parent_revision: int
    parent_transition_id: str
    parent_snapshot_root: str
    parent_history_root: str
    parent_history_count: int
    source_context_root: str
    mutation_delta_root: str
    history_root: str
    history_count: int
    leases: tuple[SupportLeaseV2, ...]
    lease_set_root: str
    schema: str
    state_schema: str
    canonical_version: str
    snapshot_root: str


def _root(kind: str, body: object) -> str:
    return _compute_root(f"support-v2:{kind}", body)


SUPPORT_GENESIS_SNAPSHOT_ROOT_V2 = _root(
    "genesis-parent",
    {
        "schema": SUPPORT_SNAPSHOT_SCHEMA_V2,
        "canonical_version": AUTHORITY_CANONICAL_VERSION_V2,
    },
)


@dataclass(frozen=True, slots=True)
class SupportSnapshotV2:
    domain_root: str
    scope_ref: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    authority_policy_root: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    stream_ref: str
    mutation_ref: str
    transition_id: str
    mutation_kind: SupportMutationKindV2
    revision: int
    initialized_at_step: int
    current_step: int
    mutation_issuer_ref: str
    mutation_provenance_root: str
    mutation_trace_roots: Sequence[str]
    parent_revision: int
    parent_transition_id: str
    parent_snapshot_root: str
    parent_history_root: str
    parent_history_count: int
    source_context_root: str
    mutation_delta_root: str
    history_root: str
    history_count: int
    leases: Sequence[SupportLeaseV2]
    lease_set_root: str = ""
    schema: str = SUPPORT_SNAPSHOT_SCHEMA_V2
    state_schema: str = SUPPORT_STATE_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    snapshot_root: str = ""

    _root_field: ClassVar[str] = "snapshot_root"

    def __post_init__(self) -> None:
        _validate_snapshot_shape(self)
        object.__setattr__(
            self,
            "mutation_trace_roots",
            _bounded_root_tuple(
                self.mutation_trace_roots,
                "support snapshot mutation trace roots",
                limit=MAX_SUPPORT_TRACE_ROOTS_V2,
            ),
        )
        leases = canonical_support_leases_v2(self.leases)
        object.__setattr__(self, "leases", leases)
        _validate_snapshot_records(self, leases)
        lease_root = _root(
            "lease-set",
            {"leases": [item.lease_root for item in leases]},
        )
        if self.lease_set_root not in ("", lease_root):
            raise ValueError("support lease_set_root is mismatched")
        object.__setattr__(self, "lease_set_root", lease_root)
        expected = _root("snapshot", self._body())
        if self.snapshot_root not in ("", expected):
            raise ValueError("snapshot_root is mismatched")
        object.__setattr__(self, "snapshot_root", expected)
        if len(_canonical_bytes(self.to_dict())) > MAX_SUPPORT_SNAPSHOT_BYTES_V2:
            raise ValueError("support canonical snapshot exceeds its byte bound")

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "state_schema": self.state_schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "profile": self.profile,
            "assurance": self.assurance.value,
            "manifest_root": self.manifest_root,
            "commit_policy_root": self.commit_policy_root,
            "authority_policy_root": self.authority_policy_root,
            "protocol_ref": self.protocol_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "observed_epoch": self.observed_epoch,
            "stream_ref": self.stream_ref,
            "mutation_ref": self.mutation_ref,
            "transition_id": self.transition_id,
            "mutation_kind": self.mutation_kind.value,
            "revision": self.revision,
            "initialized_at_step": self.initialized_at_step,
            "current_step": self.current_step,
            "mutation_issuer_ref": self.mutation_issuer_ref,
            "mutation_provenance_root": self.mutation_provenance_root,
            "mutation_trace_roots": list(self.mutation_trace_roots),
            "parent_revision": self.parent_revision,
            "parent_transition_id": self.parent_transition_id,
            "parent_snapshot_root": self.parent_snapshot_root,
            "parent_history_root": self.parent_history_root,
            "parent_history_count": self.parent_history_count,
            "source_context_root": self.source_context_root,
            "mutation_delta_root": self.mutation_delta_root,
            "history_root": self.history_root,
            "history_count": self.history_count,
            "leases": [item.to_dict() for item in self.leases],
            "lease_set_root": self.lease_set_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "snapshot_root": self.snapshot_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, payload: object) -> SupportSnapshotV2:
        fields = frozenset(
            {
                "schema",
                "state_schema",
                "canonical_version",
                "domain_root",
                "scope_ref",
                "profile",
                "assurance",
                "manifest_root",
                "commit_policy_root",
                "authority_policy_root",
                "protocol_ref",
                "run_ref",
                "target_ref",
                "observed_epoch",
                "stream_ref",
                "mutation_ref",
                "transition_id",
                "mutation_kind",
                "revision",
                "initialized_at_step",
                "current_step",
                "mutation_issuer_ref",
                "mutation_provenance_root",
                "mutation_trace_roots",
                "parent_revision",
                "parent_transition_id",
                "parent_snapshot_root",
                "parent_history_root",
                "parent_history_count",
                "source_context_root",
                "mutation_delta_root",
                "history_root",
                "history_count",
                "leases",
                "lease_set_root",
                "snapshot_root",
            }
        )
        value = _require_exact_mapping_v2(payload, fields, "support snapshot v2")
        try:
            value["assurance"] = CommitAssurance(cast(str, value["assurance"]))
            value["mutation_kind"] = SupportMutationKindV2(
                cast(str, value["mutation_kind"])
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("support snapshot enum value is unsupported") from exc
        raw_leases = _require_exact_array_v2(
            value["leases"],
            "support leases",
            limit=MAX_SUPPORT_LEASES_V2,
        )
        value["leases"] = tuple(SupportLeaseV2.from_dict(item) for item in raw_leases)
        value["mutation_trace_roots"] = tuple(
            _require_exact_array_v2(
                value["mutation_trace_roots"],
                "support snapshot mutation trace roots",
                limit=MAX_SUPPORT_TRACE_ROOTS_V2,
            )
        )
        decoded = cls(**cast(_SupportSnapshotDecodedV2, value))
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "support snapshot v2",
        )
        return decoded


def _validate_snapshot_shape(snapshot: SupportSnapshotV2) -> None:
    _validate_snapshot_versions(snapshot)
    _validate_snapshot_values(snapshot)
    _validate_snapshot_continuity(snapshot)
    expected_stream = support_stream_ref_v2(
        snapshot.scope_ref,
        snapshot.profile,
        snapshot.assurance,
        snapshot.manifest_root,
        snapshot.commit_policy_root,
        snapshot.protocol_ref,
        snapshot.run_ref,
        snapshot.target_ref,
    )
    if snapshot.stream_ref != expected_stream:
        raise ValueError("support snapshot stream is mismatched")
    if snapshot.transition_id != support_transition_id_v2(
        expected_stream,
        snapshot.mutation_ref,
    ):
        raise ValueError("support snapshot transition is mismatched")


def _validate_snapshot_versions(snapshot: SupportSnapshotV2) -> None:
    expected = (
        (snapshot.schema, SUPPORT_SNAPSHOT_SCHEMA_V2, "snapshot schema"),
        (snapshot.state_schema, SUPPORT_STATE_SCHEMA_V2, "state schema"),
        (
            snapshot.canonical_version,
            AUTHORITY_CANONICAL_VERSION_V2,
            "canonical version",
        ),
    )
    if any(value != required for value, required, _ in expected):
        label = next(label for value, required, label in expected if value != required)
        raise ValueError(f"support {label} is unsupported")


def _validate_snapshot_values(snapshot: SupportSnapshotV2) -> None:
    for field in (
        "domain_root",
        "manifest_root",
        "commit_policy_root",
        "authority_policy_root",
        "mutation_provenance_root",
        "parent_snapshot_root",
        "parent_history_root",
        "source_context_root",
        "mutation_delta_root",
        "history_root",
    ):
        _require_root(getattr(snapshot, field), f"support snapshot {field}")
    for field in (
        "scope_ref",
        "profile",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "mutation_issuer_ref",
        "stream_ref",
        "mutation_ref",
        "transition_id",
        "parent_transition_id",
    ):
        _require_bounded_text_v2(getattr(snapshot, field), f"support snapshot {field}")
    for field in (
        "observed_epoch",
        "revision",
        "initialized_at_step",
        "current_step",
        "parent_revision",
        "parent_history_count",
        "history_count",
    ):
        _require_count_v2(getattr(snapshot, field), f"support snapshot {field}")
    if type(snapshot.mutation_kind) is not SupportMutationKindV2:
        raise TypeError("support snapshot mutation_kind is invalid")
    if type(snapshot.assurance) is not CommitAssurance:
        raise TypeError("support snapshot assurance is invalid")
    if snapshot.profile not in COMMIT_PROFILES_BY_ASSURANCE.get(
        snapshot.assurance.value,
        frozenset(),
    ):
        raise ValueError("support snapshot profile and assurance are mismatched")


def _validate_snapshot_continuity(snapshot: SupportSnapshotV2) -> None:
    if snapshot.revision < 1 or snapshot.parent_revision != snapshot.revision - 1:
        raise ValueError("support snapshot revision is not contiguous")
    if snapshot.current_step < snapshot.initialized_at_step:
        raise ValueError("support snapshot time moves before initialization")
    expected_history = support_history_advance_v2(
        parent_history_root=snapshot.parent_history_root,
        parent_history_count=snapshot.parent_history_count,
        transition_id=snapshot.transition_id,
        mutation_delta_root=snapshot.mutation_delta_root,
    )
    if (snapshot.history_root, snapshot.history_count) != expected_history:
        raise ValueError("support snapshot history commitment is mismatched")
    if snapshot.history_count != snapshot.revision:
        raise ValueError("support snapshot history count and revision diverge")
    if snapshot.revision == 1:
        if snapshot.mutation_kind is not SupportMutationKindV2.INITIALIZE:
            raise ValueError("support genesis transition must initialize")
        if (
            snapshot.parent_transition_id != SUPPORT_GENESIS_TRANSITION_ID_V2
            or snapshot.parent_snapshot_root != SUPPORT_GENESIS_SNAPSHOT_ROOT_V2
            or snapshot.parent_history_root != SUPPORT_GENESIS_HISTORY_ROOT_V2
            or snapshot.parent_history_count != 0
        ):
            raise ValueError("support genesis parent is mismatched")
    elif snapshot.mutation_kind is SupportMutationKindV2.INITIALIZE:
        raise ValueError("support initialization is only legal at revision 1")


def _validate_snapshot_records(
    snapshot: SupportSnapshotV2,
    leases: tuple[SupportLeaseV2, ...],
) -> None:
    for lease in leases:
        if (
            lease.profile != snapshot.profile
            or lease.assurance is not snapshot.assurance
            or lease.manifest_root != snapshot.manifest_root
            or lease.commit_policy_root != snapshot.commit_policy_root
            or lease.protocol_ref != snapshot.protocol_ref
            or lease.run_ref != snapshot.run_ref
            or lease.target_ref != snapshot.target_ref
        ):
            raise ValueError("support snapshot record has a cross-ledger binding")
        if not lease.issued_at_step <= snapshot.current_step < lease.expires_at_step:
            raise ValueError("support snapshot contains a non-active lease")
    by_lease = {item.lease_root: item for item in leases}
    for lease in leases:
        if lease.prior_lease_root and lease.prior_lease_root in by_lease:
            raise ValueError("support replacement retains its revoked prior lease")


def revocation_matches_lease_v2(
    revocation: SupportRevocationV2,
    lease: SupportLeaseV2,
) -> bool:
    return bool(
        all(
            getattr(revocation, name) == getattr(lease, name)
            for name in (
                "profile",
                "assurance",
                "manifest_root",
                "commit_policy_root",
                "protocol_ref",
                "run_ref",
                "target_ref",
                "candidate_ref",
                "claim_root",
                "epoch",
                "principal_ref",
                "principal_cluster_ref",
            )
        )
        and revocation.lease_issuance_issuer_ref == lease.issuance_issuer_ref
        and lease.issued_at_step <= revocation.revoked_at_step < lease.expires_at_step
    )


def replacement_matches_prior_v2(
    replacement: SupportLeaseV2,
    prior: SupportLeaseV2,
) -> bool:
    return bool(
        all(
            getattr(replacement, name) == getattr(prior, name)
            for name in (
                "profile",
                "assurance",
                "manifest_root",
                "commit_policy_root",
                "protocol_ref",
                "run_ref",
                "target_ref",
                "epoch",
                "principal_ref",
                "principal_cluster_ref",
                "membership_principal_root",
                "principal_verification_root",
                "membership_root",
            )
        )
        and replacement.candidate_ref != prior.candidate_ref
        and replacement.issued_at_step >= prior.issued_at_step
    )


__all__: tuple[str, ...] = ()
