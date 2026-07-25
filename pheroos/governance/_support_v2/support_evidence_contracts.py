"""Portable observation and lease-proposal records for Support v2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Protocol, TypedDict, cast

from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CommitAssurance,
)

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _canonical_bytes,
    _compute_root,
    _require_root,
)
from pheroos.governance._support_v2.common import (
    _canonical_utf8_order_v2,
    _require_bounded_text_v2,
    _require_count_v2,
    _require_canonical_wire_v2,
    _require_exact_array_v2,
    _require_exact_mapping_v2,
)


SUPPORT_PROPOSAL_SCHEMA_V2 = "pheroos-support-lease-proposal-v2"
SUPPORT_OBSERVATION_SCHEMA_V2 = "pheroos-support-observation-v2"
MAX_SUPPORT_OBSERVATIONS_V2 = 1024
MAX_SUPPORT_TRACE_ROOTS_V2 = 1024


class _SupportObservationDecodedV2(TypedDict):
    observation_ref: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    candidate_ref: str
    claim_root: str
    epoch: int
    source_ref: str
    evidence_root: str
    observed_at_step: int
    expires_at_step: int
    provenance_root: str
    source_trace_roots: tuple[str, ...]
    schema: str
    observation_root: str


class _SupportLeaseProposalDecodedV2(TypedDict):
    proposal_ref: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    candidate_ref: str
    claim_root: str
    epoch: int
    principal_ref: str
    positive_observation_roots: tuple[str, ...]
    nonce: str
    proposed_at_step: int
    provenance_root: str
    source_trace_roots: tuple[str, ...]
    schema: str
    proposal_root: str


def _root(kind: str, body: object) -> str:
    return _compute_root(f"support-v2:{kind}", body)


def _exact_version(value: object, expected: str, label: str) -> None:
    if type(value) is not str or value != expected:
        raise ValueError(f"{label} is unsupported")


def _install_root(
    instance: object,
    field: str,
    supplied: object,
    kind: str,
    body: object,
) -> None:
    expected = _root(kind, body)
    if supplied not in ("", expected):
        raise ValueError(f"{field} is mismatched")
    object.__setattr__(instance, field, expected)


def _bounded_root_tuple(
    values: object,
    label: str,
    *,
    limit: int,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if type(values) not in (list, tuple):
        raise TypeError(f"{label} must be an exact array or tuple")
    roots: tuple[object, ...] = tuple(cast(Sequence[object], values))
    if len(roots) > limit or (not roots and not allow_empty):
        raise ValueError(f"{label} count is outside its bound")
    for root in roots:
        _require_root(root, label)
    if len(roots) != len(set(roots)):
        raise ValueError(f"{label} contains a duplicate")
    return tuple(sorted(cast(tuple[str, ...], roots), key=lambda item: item.encode()))


def _bounded_text_tuple(
    values: object,
    label: str,
    *,
    limit: int,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if type(values) not in (list, tuple):
        raise TypeError(f"{label} must be an exact array or tuple")
    items: tuple[object, ...] = tuple(cast(Sequence[object], values))
    if len(items) > limit or (not items and not allow_empty):
        raise ValueError(f"{label} count is outside its bound")
    normalized = tuple(_require_bounded_text_v2(item, label) for item in items)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} contains a duplicate")
    return _canonical_utf8_order_v2(normalized)


if TYPE_CHECKING:

    class _BoundContextV2(Protocol):
        @property
        def profile(self) -> str: ...

        @property
        def assurance(self) -> CommitAssurance: ...

        @property
        def manifest_root(self) -> str: ...

        @property
        def commit_policy_root(self) -> str: ...

        @property
        def protocol_ref(self) -> str: ...

        @property
        def run_ref(self) -> str: ...

        @property
        def target_ref(self) -> str: ...

        @property
        def epoch(self) -> int: ...
else:

    class _BoundContextV2(Protocol):
        pass


def _validate_bound_context(value: _BoundContextV2, label: str) -> None:
    profile = _require_bounded_text_v2(getattr(value, "profile"), f"{label} profile")
    assurance = getattr(value, "assurance")
    if type(assurance) is not CommitAssurance:
        raise TypeError(f"{label} assurance is invalid")
    if profile not in COMMIT_PROFILES_BY_ASSURANCE.get(assurance.value, frozenset()):
        raise ValueError(f"{label} profile and assurance are mismatched")
    for field in ("manifest_root", "commit_policy_root"):
        _require_root(getattr(value, field), f"{label} {field}")
    for field in ("protocol_ref", "run_ref", "target_ref"):
        _require_bounded_text_v2(getattr(value, field), f"{label} {field}")
    _require_count_v2(getattr(value, "epoch"), f"{label} epoch")


def _bound_context_body(value: _BoundContextV2) -> dict[str, object]:
    return {
        "profile": value.profile,
        "assurance": value.assurance.value,
        "manifest_root": value.manifest_root,
        "commit_policy_root": value.commit_policy_root,
        "protocol_ref": value.protocol_ref,
        "run_ref": value.run_ref,
        "target_ref": value.target_ref,
        "epoch": value.epoch,
    }


def _assurance(value: object, label: str) -> CommitAssurance:
    try:
        return CommitAssurance(cast(str, value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} assurance is unsupported") from exc


@dataclass(frozen=True, slots=True)
class SupportObservationV2:
    """Portable positive evidence assertion that confers no authority itself."""

    observation_ref: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    candidate_ref: str
    claim_root: str
    epoch: int
    source_ref: str
    evidence_root: str
    observed_at_step: int
    expires_at_step: int
    provenance_root: str
    source_trace_roots: Sequence[str]
    schema: str = SUPPORT_OBSERVATION_SCHEMA_V2
    observation_root: str = ""

    _root_field: ClassVar[str] = "observation_root"

    def __post_init__(self) -> None:
        _exact_version(
            self.schema,
            SUPPORT_OBSERVATION_SCHEMA_V2,
            "support observation schema",
        )
        _validate_bound_context(self, "support observation")
        for field in ("observation_ref", "candidate_ref", "source_ref"):
            _require_bounded_text_v2(
                getattr(self, field),
                f"support observation {field}",
            )
        for field in ("claim_root", "evidence_root", "provenance_root"):
            _require_root(getattr(self, field), f"support observation {field}")
        observed = _require_count_v2(
            self.observed_at_step,
            "support observation observed_at_step",
        )
        expires = _require_count_v2(
            self.expires_at_step,
            "support observation expires_at_step",
        )
        if expires <= observed:
            raise ValueError("support observation expiry must be after observation")
        object.__setattr__(
            self,
            "source_trace_roots",
            _bounded_root_tuple(
                self.source_trace_roots,
                "support observation source trace roots",
                limit=MAX_SUPPORT_TRACE_ROOTS_V2,
            ),
        )
        _install_root(
            self,
            "observation_root",
            self.observation_root,
            "observation",
            self._body(),
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "observation_ref": self.observation_ref,
            **_bound_context_body(self),
            "candidate_ref": self.candidate_ref,
            "claim_root": self.claim_root,
            "source_ref": self.source_ref,
            "evidence_root": self.evidence_root,
            "observed_at_step": self.observed_at_step,
            "expires_at_step": self.expires_at_step,
            "provenance_root": self.provenance_root,
            "source_trace_roots": list(self.source_trace_roots),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "observation_root": self.observation_root}

    @classmethod
    def from_dict(cls, payload: object) -> SupportObservationV2:
        fields = frozenset(
            {
                "schema",
                "observation_ref",
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
                "source_ref",
                "evidence_root",
                "observed_at_step",
                "expires_at_step",
                "provenance_root",
                "source_trace_roots",
                "observation_root",
            }
        )
        value = _require_exact_mapping_v2(payload, fields, "support observation v2")
        value["assurance"] = _assurance(value["assurance"], "support observation")
        value["source_trace_roots"] = tuple(
            _require_exact_array_v2(
                value["source_trace_roots"],
                "support observation source trace roots",
                limit=MAX_SUPPORT_TRACE_ROOTS_V2,
            )
        )
        decoded = cls(**cast(_SupportObservationDecodedV2, value))
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "support observation v2",
        )
        return decoded


def canonical_support_observations_v2(
    observations: Sequence[SupportObservationV2],
) -> tuple[SupportObservationV2, ...]:
    if type(observations) not in (list, tuple):
        raise TypeError("support observations must be an exact array or tuple")
    values = tuple(observations)
    if not values or len(values) > MAX_SUPPORT_OBSERVATIONS_V2:
        raise ValueError("support observation count is outside its bound")
    if any(type(item) is not SupportObservationV2 for item in values):
        raise TypeError("support observations contain a non-canonical record")
    ordered = tuple(sorted(values, key=lambda item: item.observation_root.encode()))
    roots = tuple(item.observation_root for item in ordered)
    refs = tuple(item.observation_ref for item in ordered)
    if len(roots) != len(set(roots)):
        raise ValueError("support observations repeat an observation root")
    if len(refs) != len(set(refs)):
        raise ValueError("support observations contain a replayed observation_ref")
    return ordered


@dataclass(frozen=True, slots=True)
class SupportLeaseProposalV2:
    proposal_ref: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    candidate_ref: str
    claim_root: str
    epoch: int
    principal_ref: str
    positive_observation_roots: Sequence[str]
    nonce: str
    proposed_at_step: int
    provenance_root: str
    source_trace_roots: Sequence[str]
    schema: str = SUPPORT_PROPOSAL_SCHEMA_V2
    proposal_root: str = ""

    _root_field: ClassVar[str] = "proposal_root"

    def __post_init__(self) -> None:
        _exact_version(
            self.schema, SUPPORT_PROPOSAL_SCHEMA_V2, "support proposal schema"
        )
        _validate_bound_context(self, "support proposal")
        for field in ("proposal_ref", "candidate_ref", "principal_ref", "nonce"):
            _require_bounded_text_v2(getattr(self, field), f"support proposal {field}")
        for field in ("claim_root", "provenance_root"):
            _require_root(getattr(self, field), f"support proposal {field}")
        _require_count_v2(self.proposed_at_step, "support proposal proposed_at_step")
        roots = _bounded_root_tuple(
            self.positive_observation_roots,
            "support proposal positive observations",
            limit=MAX_SUPPORT_OBSERVATIONS_V2,
        )
        object.__setattr__(self, "positive_observation_roots", roots)
        object.__setattr__(
            self,
            "source_trace_roots",
            _bounded_root_tuple(
                self.source_trace_roots,
                "support proposal source trace roots",
                limit=MAX_SUPPORT_TRACE_ROOTS_V2,
            ),
        )
        _install_root(
            self, "proposal_root", self.proposal_root, "proposal", self._body()
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "proposal_ref": self.proposal_ref,
            **_bound_context_body(self),
            "candidate_ref": self.candidate_ref,
            "claim_root": self.claim_root,
            "principal_ref": self.principal_ref,
            "positive_observation_roots": list(self.positive_observation_roots),
            "nonce": self.nonce,
            "proposed_at_step": self.proposed_at_step,
            "provenance_root": self.provenance_root,
            "source_trace_roots": list(self.source_trace_roots),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "proposal_root": self.proposal_root}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, payload: object) -> SupportLeaseProposalV2:
        fields = frozenset(
            {
                "schema",
                "proposal_ref",
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
                "positive_observation_roots",
                "nonce",
                "proposed_at_step",
                "provenance_root",
                "source_trace_roots",
                "proposal_root",
            }
        )
        value = _require_exact_mapping_v2(payload, fields, "support proposal v2")
        value["assurance"] = _assurance(value["assurance"], "support proposal")
        raw = _require_exact_array_v2(
            value["positive_observation_roots"],
            "support proposal observations",
            limit=MAX_SUPPORT_OBSERVATIONS_V2,
        )
        value["positive_observation_roots"] = tuple(raw)
        value["source_trace_roots"] = tuple(
            _require_exact_array_v2(
                value["source_trace_roots"],
                "support proposal source trace roots",
                limit=MAX_SUPPORT_TRACE_ROOTS_V2,
            )
        )
        decoded = cls(**cast(_SupportLeaseProposalDecodedV2, value))
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "support proposal v2",
        )
        return decoded


__all__ = [
    "MAX_SUPPORT_OBSERVATIONS_V2",
    "MAX_SUPPORT_TRACE_ROOTS_V2",
    "SupportLeaseProposalV2",
    "SupportObservationV2",
    "canonical_support_observations_v2",
]
