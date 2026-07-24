"""Complete historical mutation delta requests for Support v2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, TypedDict, cast

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _canonical_bytes,
    _compute_root,
    _require_root,
)
from pheroos.governance._support_v2.common import (
    _require_bounded_text_v2,
    _require_canonical_wire_v2,
    _require_count_v2,
    _require_exact_mapping_v2,
)
from pheroos.governance._support_v2.support_evidence_contracts import (
    _bounded_root_tuple,
)
from pheroos.governance._support_v2.support_lease_contracts import (
    MAX_SUPPORT_LEASES_V2,
    SupportLeaseV2,
    SupportRevocationV2,
)
from pheroos.governance._support_v2.support_snapshot_contracts import (
    SupportSnapshotV2,
    replacement_matches_prior_v2,
    revocation_matches_lease_v2,
)
from pheroos.governance._support_v2.support_stream_contracts import (
    SupportMutationKindV2,
    support_mutation_delta_root_v2,
    support_switch_lineage_v2,
)


SUPPORT_ADVANCE_REQUEST_SCHEMA_V2 = "pheroos-support-advance-request-v2"


class _SupportAdvanceRequestDecodedV2(TypedDict):
    domain_root: str
    scope_ref: str
    run_ref: str
    target_ref: str
    mutation_issuer_ref: str
    observed_epoch: int
    mutation_ref: str
    stream_ref: str
    transition_id: str
    mutation_kind: SupportMutationKindV2
    issued_lease_root: str
    revoked_lease_root: str
    revocation_root: str
    evicted_lease_roots: tuple[str, ...]
    issued_lease: SupportLeaseV2 | None
    revoked_lease: SupportLeaseV2 | None
    revocation: SupportRevocationV2 | None
    membership_stream_ref: str
    membership_transition_id: str
    membership_snapshot_root: str
    snapshot: SupportSnapshotV2
    schema: str
    canonical_version: str
    request_root: str


def _root(kind: str, body: object) -> str:
    return _compute_root(f"support-v2:{kind}", body)


@dataclass(frozen=True, slots=True)
class SupportAdvanceRequestV2:
    domain_root: str
    scope_ref: str
    run_ref: str
    target_ref: str
    mutation_issuer_ref: str
    observed_epoch: int
    mutation_ref: str
    stream_ref: str
    transition_id: str
    mutation_kind: SupportMutationKindV2
    issued_lease_root: str
    revoked_lease_root: str
    revocation_root: str
    evicted_lease_roots: Sequence[str]
    issued_lease: SupportLeaseV2 | None
    revoked_lease: SupportLeaseV2 | None
    revocation: SupportRevocationV2 | None
    membership_stream_ref: str
    membership_transition_id: str
    membership_snapshot_root: str
    snapshot: SupportSnapshotV2
    schema: str = SUPPORT_ADVANCE_REQUEST_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    request_root: str = ""

    _root_field: ClassVar[str] = "request_root"

    def __post_init__(self) -> None:
        if self.schema != SUPPORT_ADVANCE_REQUEST_SCHEMA_V2:
            raise ValueError("support request schema is unsupported")
        if self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2:
            raise ValueError("support request canonical version is unsupported")
        if type(self.snapshot) is not SupportSnapshotV2:
            raise TypeError("support request requires exact snapshot v2")
        _require_count_v2(self.observed_epoch, "support request observed_epoch")
        for field in (
            "domain_root",
            "scope_ref",
            "run_ref",
            "target_ref",
            "mutation_issuer_ref",
            "observed_epoch",
            "mutation_ref",
            "stream_ref",
            "transition_id",
            "mutation_kind",
        ):
            if getattr(self, field) != getattr(self.snapshot, field):
                raise ValueError(f"support request {field} is cross-bound incorrectly")
        object.__setattr__(
            self,
            "evicted_lease_roots",
            _bounded_root_tuple(
                self.evicted_lease_roots,
                "support evicted lease roots",
                limit=MAX_SUPPORT_LEASES_V2,
                allow_empty=True,
            ),
        )
        _validate_mutation_bindings(self)
        expected_delta_root = support_mutation_delta_root_v2(
            self.mutation_kind,
            transition_id=self.transition_id,
            mutation_issuer_ref=self.mutation_issuer_ref,
            observed_epoch=self.observed_epoch,
            current_step=self.snapshot.current_step,
            mutation_provenance_root=self.snapshot.mutation_provenance_root,
            mutation_trace_roots=self.snapshot.mutation_trace_roots,
            issued_lease_root=self.issued_lease_root,
            revoked_lease_root=self.revoked_lease_root,
            revocation_root=self.revocation_root,
            evicted_lease_roots=self.evicted_lease_roots,
            membership_stream_ref=self.membership_stream_ref,
            membership_transition_id=self.membership_transition_id,
            membership_snapshot_root=self.membership_snapshot_root,
        )
        if self.snapshot.mutation_delta_root != expected_delta_root:
            raise ValueError("support request mutation delta root is mismatched")
        expected = _root("advance-request", self._body())
        if self.request_root not in ("", expected):
            raise ValueError("request_root is mismatched")
        object.__setattr__(self, "request_root", expected)

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "mutation_issuer_ref": self.mutation_issuer_ref,
            "observed_epoch": self.observed_epoch,
            "mutation_ref": self.mutation_ref,
            "stream_ref": self.stream_ref,
            "transition_id": self.transition_id,
            "mutation_kind": self.mutation_kind.value,
            "issued_lease_root": self.issued_lease_root,
            "revoked_lease_root": self.revoked_lease_root,
            "revocation_root": self.revocation_root,
            "evicted_lease_roots": list(self.evicted_lease_roots),
            "issued_lease": (
                None if self.issued_lease is None else self.issued_lease.to_dict()
            ),
            "revoked_lease": (
                None if self.revoked_lease is None else self.revoked_lease.to_dict()
            ),
            "revocation": None
            if self.revocation is None
            else self.revocation.to_dict(),
            "membership_stream_ref": self.membership_stream_ref,
            "membership_transition_id": self.membership_transition_id,
            "membership_snapshot_root": self.membership_snapshot_root,
            "snapshot": self.snapshot.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "request_root": self.request_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, payload: object) -> SupportAdvanceRequestV2:
        fields = frozenset(
            {
                "schema",
                "canonical_version",
                "domain_root",
                "scope_ref",
                "run_ref",
                "target_ref",
                "mutation_issuer_ref",
                "observed_epoch",
                "mutation_ref",
                "stream_ref",
                "transition_id",
                "mutation_kind",
                "issued_lease_root",
                "revoked_lease_root",
                "revocation_root",
                "evicted_lease_roots",
                "issued_lease",
                "revoked_lease",
                "revocation",
                "membership_stream_ref",
                "membership_transition_id",
                "membership_snapshot_root",
                "snapshot",
                "request_root",
            }
        )
        value = _require_exact_mapping_v2(payload, fields, "support request v2")
        try:
            value["mutation_kind"] = SupportMutationKindV2(
                cast(str, value["mutation_kind"])
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("support request mutation kind is unsupported") from exc
        value["snapshot"] = SupportSnapshotV2.from_dict(value["snapshot"])
        raw_evicted = value["evicted_lease_roots"]
        if type(raw_evicted) is not list:
            raise TypeError("support evicted lease roots must be an exact array")
        value["evicted_lease_roots"] = tuple(raw_evicted)
        value["issued_lease"] = _lease_or_none(value["issued_lease"], "issued lease")
        value["revoked_lease"] = _lease_or_none(
            value["revoked_lease"],
            "revoked lease",
        )
        value["revocation"] = _revocation_or_none(value["revocation"])
        decoded = cls(**cast(_SupportAdvanceRequestDecodedV2, value))
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "support request v2",
        )
        return decoded


def _lease_or_none(value: object, label: str) -> SupportLeaseV2 | None:
    if value is None:
        return None
    try:
        return SupportLeaseV2.from_dict(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"support request {label} is invalid") from exc


def _revocation_or_none(value: object) -> SupportRevocationV2 | None:
    if value is None:
        return None
    try:
        return SupportRevocationV2.from_dict(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("support request revocation is invalid") from exc


def _validate_mutation_bindings(request: SupportAdvanceRequestV2) -> None:
    roots = (
        request.issued_lease_root,
        request.revoked_lease_root,
        request.revocation_root,
    )
    membership = (
        request.membership_stream_ref,
        request.membership_transition_id,
        request.membership_snapshot_root,
    )
    for value in (*roots, request.membership_snapshot_root):
        if value:
            _require_root(value, "support request mutation root")
    for value in membership[:2]:
        _require_bounded_text_v2(value, "support membership binding", allow_empty=True)
    _validate_mutation_presence(request, roots, membership)
    _validate_support_mutation_semantics_v2(request)


def _validate_mutation_presence(
    request: SupportAdvanceRequestV2,
    roots: tuple[str, str, str],
    membership: tuple[str, str, str],
) -> None:
    records = (request.issued_lease, request.revoked_lease, request.revocation)
    empty_roots = ("", "", "")
    empty_records = (None, None, None)
    if request.mutation_kind is SupportMutationKindV2.INITIALIZE:
        valid = (
            roots == empty_roots and records == empty_records and not any(membership)
        )
        valid = valid and not request.evicted_lease_roots
    elif request.mutation_kind is SupportMutationKindV2.ISSUE:
        valid = bool(roots[0] and records[0]) and roots[1:] == ("", "")
        valid = valid and records[1:] == (None, None) and all(membership)
    elif request.mutation_kind is SupportMutationKindV2.REVOKE:
        valid = not roots[0] and all(roots[1:]) and records[0] is None
        valid = valid and all(records[1:]) and not any(membership)
    else:
        valid = all(roots) and all(records) and all(membership)
    if not valid:
        raise ValueError("support mutation delta records are incomplete")


def _validate_support_mutation_semantics_v2(
    request: SupportAdvanceRequestV2,
) -> None:
    """Enforce one exact semantic delta for every mutation kind."""

    issued = request.issued_lease
    revoked = request.revoked_lease
    revocation = request.revocation
    active_roots = {item.lease_root for item in request.snapshot.leases}
    if active_roots.intersection(request.evicted_lease_roots):
        raise ValueError("support current projection retains an expired eviction")
    if request.revoked_lease_root in set(request.evicted_lease_roots):
        raise ValueError("support revoked lease cannot also be an expiry eviction")
    if request.mutation_kind is SupportMutationKindV2.INITIALIZE:
        _validate_initialize_semantics(request)
        return
    if issued is not None:
        _validate_issued_record(request, issued, active_roots)
    if revoked is not None and revocation is not None:
        _validate_revoked_records(request, revoked, revocation, active_roots)
    if issued is not None and revoked is not None:
        _validate_replacement(issued, revoked)
    _validate_exact_mutation_lineage(request)


def _validate_initialize_semantics(request: SupportAdvanceRequestV2) -> None:
    snapshot = request.snapshot
    if snapshot.leases:
        raise ValueError("support initialization must commit an empty projection")
    if snapshot.current_step != snapshot.initialized_at_step:
        raise ValueError("support initialization step is mismatched")


def _validate_issued_record(
    request: SupportAdvanceRequestV2,
    issued: SupportLeaseV2,
    active_roots: set[str],
) -> None:
    if issued.lease_root != request.issued_lease_root:
        raise ValueError("support issued lease root is mismatched")
    if issued.mutation_transition_id != request.transition_id:
        raise ValueError("support issued lease belongs to another transition")
    if issued.issuance_issuer_ref != request.mutation_issuer_ref:
        raise ValueError("support issued lease is owned by another mutation issuer")
    if issued.issued_at_step != request.snapshot.current_step:
        raise ValueError("support issued lease step is mismatched")
    if issued.lease_root not in active_roots:
        raise ValueError("support issued lease is absent from current projection")


def _validate_revoked_records(
    request: SupportAdvanceRequestV2,
    revoked: SupportLeaseV2,
    revocation: SupportRevocationV2,
    active_roots: set[str],
) -> None:
    if revoked.lease_root != request.revoked_lease_root:
        raise ValueError("support revoked lease root is mismatched")
    if revocation.revocation_root != request.revocation_root:
        raise ValueError("support revocation root is mismatched")
    if revocation.mutation_transition_id != request.transition_id:
        raise ValueError("support revocation belongs to another transition")
    if revocation.revocation_issuer_ref != request.mutation_issuer_ref:
        raise ValueError("support revocation is owned by another mutation issuer")
    if revocation.revoked_at_step != request.snapshot.current_step:
        raise ValueError("support revocation step is mismatched")
    if not revocation_matches_lease_v2(revocation, revoked):
        raise ValueError("support revocation and revoked lease are mismatched")
    if revoked.lease_root in active_roots:
        raise ValueError("support current projection retains a revoked lease")


def _validate_replacement(
    issued: SupportLeaseV2,
    revoked: SupportLeaseV2,
) -> None:
    if not replacement_matches_prior_v2(issued, revoked):
        raise ValueError("support replacement and prior lease are mismatched")
    if issued.prior_lease_root != revoked.lease_root:
        raise ValueError("support replacement prior root is mismatched")


def _validate_exact_mutation_lineage(request: SupportAdvanceRequestV2) -> None:
    issued = request.issued_lease
    revocation = request.revocation
    snapshot = request.snapshot
    if request.mutation_kind is SupportMutationKindV2.ISSUE:
        assert issued is not None
        expected = (
            issued.issuance_provenance_root,
            tuple(issued.issuance_trace_roots),
        )
    elif request.mutation_kind is SupportMutationKindV2.REVOKE:
        assert revocation is not None
        expected = (revocation.provenance_root, tuple(revocation.source_trace_roots))
    else:
        assert issued is not None and revocation is not None
        expected = support_switch_lineage_v2(
            revocation_provenance_root=revocation.provenance_root,
            revocation_trace_roots=revocation.source_trace_roots,
            issuance_provenance_root=issued.issuance_provenance_root,
            issuance_trace_roots=issued.issuance_trace_roots,
        )
    observed = (
        snapshot.mutation_provenance_root,
        tuple(snapshot.mutation_trace_roots),
    )
    if observed != expected:
        raise ValueError("support mutation lineage is mismatched")


__all__: tuple[str, ...] = ()
