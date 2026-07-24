"""Portable deterministic Support v2 evaluation result."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, TypedDict, cast

from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._authority_store_v2_contracts.foundation import (
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
from pheroos.governance._support_v2.support_equivocation_contracts import (
    SupportEquivocationV2,
)
from pheroos.governance._support_v2.support_evidence_contracts import (
    _assurance,
    _bound_context_body,
    _bounded_root_tuple,
    _bounded_text_tuple,
    _validate_bound_context,
)
from pheroos.governance._support_v2.support_lease_contracts import (
    MAX_SUPPORT_LEASES_V2,
)
from pheroos.governance.commit_numeric import scaled_ratio


SUPPORT_EVALUATION_SCHEMA_V2 = "pheroos-support-evaluation-v2"


class _SupportEvaluationDecodedV2(TypedDict):
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
    current_step: int
    membership_snapshot_root: str
    membership_root: str
    support_snapshot_root: str
    eligible_cluster_count: int
    active_support_cluster_count: int
    support_ratio_ppm: int
    policy_threshold_clusters: int
    policy_support_met: bool
    active_cluster_refs: tuple[str, ...]
    included_lease_roots: tuple[str, ...]
    excluded_lease_roots: tuple[str, ...]
    equivocations: tuple[SupportEquivocationV2, ...]
    schema: str
    evaluation_root: str


@dataclass(frozen=True, slots=True)
class SupportEvaluationV2:
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
    current_step: int
    membership_snapshot_root: str
    membership_root: str
    support_snapshot_root: str
    eligible_cluster_count: int
    active_support_cluster_count: int
    support_ratio_ppm: int
    policy_threshold_clusters: int
    policy_support_met: bool
    active_cluster_refs: Sequence[str]
    included_lease_roots: Sequence[str]
    excluded_lease_roots: Sequence[str]
    equivocations: Sequence[SupportEquivocationV2]
    schema: str = SUPPORT_EVALUATION_SCHEMA_V2
    evaluation_root: str = ""

    _root_field: ClassVar[str] = "evaluation_root"

    def __post_init__(self) -> None:
        _validate_evaluation_scalars(self)
        clusters, included, excluded, findings = _normalize_evaluation_collections(self)
        _validate_evaluation_derivations(
            self,
            clusters=clusters,
            included=included,
            excluded=excluded,
            findings=findings,
        )
        object.__setattr__(self, "active_cluster_refs", clusters)
        object.__setattr__(self, "included_lease_roots", included)
        object.__setattr__(self, "excluded_lease_roots", excluded)
        object.__setattr__(self, "equivocations", findings)
        expected_root = _compute_root("support-v2:evaluation", self._body())
        if self.evaluation_root not in ("", expected_root):
            raise ValueError("support evaluation root is mismatched")
        object.__setattr__(self, "evaluation_root", expected_root)

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            **_bound_context_body(self),
            "candidate_ref": self.candidate_ref,
            "claim_root": self.claim_root,
            "current_step": self.current_step,
            "membership_snapshot_root": self.membership_snapshot_root,
            "membership_root": self.membership_root,
            "support_snapshot_root": self.support_snapshot_root,
            "eligible_cluster_count": self.eligible_cluster_count,
            "active_support_cluster_count": self.active_support_cluster_count,
            "support_ratio_ppm": self.support_ratio_ppm,
            "policy_threshold_clusters": self.policy_threshold_clusters,
            "policy_support_met": self.policy_support_met,
            "active_cluster_refs": list(self.active_cluster_refs),
            "included_lease_roots": list(self.included_lease_roots),
            "excluded_lease_roots": list(self.excluded_lease_roots),
            "equivocations": [item.to_dict() for item in self.equivocations],
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "evaluation_root": self.evaluation_root}

    @classmethod
    def from_dict(cls, payload: object) -> SupportEvaluationV2:
        fields = frozenset(
            {
                "schema",
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
                "current_step",
                "membership_snapshot_root",
                "membership_root",
                "support_snapshot_root",
                "eligible_cluster_count",
                "active_support_cluster_count",
                "support_ratio_ppm",
                "policy_threshold_clusters",
                "policy_support_met",
                "active_cluster_refs",
                "included_lease_roots",
                "excluded_lease_roots",
                "equivocations",
                "evaluation_root",
            }
        )
        value = _require_exact_mapping_v2(payload, fields, "support evaluation v2")
        value["assurance"] = _assurance(value["assurance"], "support evaluation")
        for field in (
            "active_cluster_refs",
            "included_lease_roots",
            "excluded_lease_roots",
        ):
            value[field] = tuple(
                _require_exact_array_v2(
                    value[field],
                    f"support evaluation {field}",
                    limit=MAX_SUPPORT_LEASES_V2,
                )
            )
        raw_findings = _require_exact_array_v2(
            value["equivocations"],
            "support evaluation equivocations",
            limit=MAX_SUPPORT_LEASES_V2,
        )
        value["equivocations"] = tuple(
            SupportEquivocationV2.from_dict(item) for item in raw_findings
        )
        decoded = cls(**cast(_SupportEvaluationDecodedV2, value))
        _require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "support evaluation v2",
        )
        return decoded


def _validate_evaluation_scalars(value: SupportEvaluationV2) -> None:
    if value.schema != SUPPORT_EVALUATION_SCHEMA_V2:
        raise ValueError("support evaluation schema is unsupported")
    _validate_bound_context(value, "support evaluation")
    _require_bounded_text_v2(
        value.candidate_ref,
        "support evaluation candidate_ref",
    )
    for field in (
        "claim_root",
        "membership_snapshot_root",
        "membership_root",
        "support_snapshot_root",
    ):
        _require_root(getattr(value, field), f"support evaluation {field}")
    for field in (
        "current_step",
        "eligible_cluster_count",
        "active_support_cluster_count",
        "support_ratio_ppm",
        "policy_threshold_clusters",
    ):
        _require_count_v2(getattr(value, field), f"support evaluation {field}")
    if type(value.policy_support_met) is not bool:
        raise TypeError("support evaluation policy_support_met must be exact bool")


def _normalize_evaluation_collections(
    value: SupportEvaluationV2,
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[SupportEquivocationV2, ...],
]:
    clusters = _bounded_text_tuple(
        value.active_cluster_refs,
        "support evaluation active clusters",
        limit=MAX_SUPPORT_LEASES_V2,
        allow_empty=True,
    )
    included = _bounded_root_tuple(
        value.included_lease_roots,
        "support evaluation included leases",
        limit=MAX_SUPPORT_LEASES_V2,
        allow_empty=True,
    )
    excluded = _bounded_root_tuple(
        value.excluded_lease_roots,
        "support evaluation excluded leases",
        limit=MAX_SUPPORT_LEASES_V2,
        allow_empty=True,
    )
    findings = tuple(value.equivocations)
    if len(findings) > MAX_SUPPORT_LEASES_V2 or any(
        type(item) is not SupportEquivocationV2 for item in findings
    ):
        raise TypeError("support evaluation equivocations are invalid")
    return (
        clusters,
        included,
        excluded,
        tuple(sorted(findings, key=lambda item: item.finding_root.encode("utf-8"))),
    )


def _validate_evaluation_derivations(
    value: SupportEvaluationV2,
    *,
    clusters: tuple[str, ...],
    included: tuple[str, ...],
    excluded: tuple[str, ...],
    findings: tuple[SupportEquivocationV2, ...],
) -> None:
    if len({item.finding_root for item in findings}) != len(findings):
        raise ValueError("support evaluation repeats an equivocation finding")
    if set(included).intersection(excluded):
        raise ValueError("support evaluation includes and excludes the same lease")
    _validate_equivocation_bindings(
        value,
        clusters=clusters,
        excluded=excluded,
        findings=findings,
    )
    if value.active_support_cluster_count != len(clusters):
        raise ValueError("support evaluation active cluster count is mismatched")
    expected_ratio = scaled_ratio(
        value.active_support_cluster_count,
        value.eligible_cluster_count,
    )
    if value.support_ratio_ppm != expected_ratio:
        raise ValueError("support evaluation ratio is mismatched")
    if value.policy_support_met != (
        value.active_support_cluster_count >= value.policy_threshold_clusters
    ):
        raise ValueError("support evaluation policy result is mismatched")


def _validate_equivocation_bindings(
    value: SupportEvaluationV2,
    *,
    clusters: tuple[str, ...],
    excluded: tuple[str, ...],
    findings: tuple[SupportEquivocationV2, ...],
) -> None:
    excluded_roots = frozenset(excluded)
    active_clusters = frozenset(clusters)
    expected_context = (
        value.target_ref,
        value.claim_root,
        value.epoch,
        value.support_snapshot_root,
    )
    for finding in findings:
        observed_context = (
            finding.target_ref,
            finding.claim_root,
            finding.epoch,
            finding.support_snapshot_root,
        )
        if observed_context != expected_context:
            raise ValueError("support evaluation equivocation is cross-bound")
        if finding.first_overlap_step > value.current_step:
            raise ValueError("support evaluation equivocation is from a future step")
        if not set(finding.conflicting_lease_roots).issubset(excluded_roots):
            raise ValueError("support evaluation omits an equivocated lease exclusion")
        if finding.principal_cluster_ref in active_clusters:
            raise ValueError("support evaluation counts an equivocated cluster")


__all__ = ["SupportEvaluationV2"]
