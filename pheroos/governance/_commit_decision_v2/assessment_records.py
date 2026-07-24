"""Derived deterministic Commit Decision v2 assessment records."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from pheroos.governance._commit_decision_v2.common import (
    COMMIT_DECISION_ASSESSMENT_SCHEMA_V2,
    _canonical_roots,
    _canonical_texts,
    _exact_array,
    _exact_mapping,
    _install_root,
    _require_bool,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
)
from pheroos.protocol.authority_v2 import MAX_AUTHORITY_REVISION_V2


COMMIT_CANDIDATE_METRICS_SCHEMA_V2 = "pheroos-commit-candidate-metrics-v2"


@dataclass(frozen=True, slots=True)
class CommitCandidateMetricsV2:
    candidate_ref: str
    claim_root: str
    positive_evidence_count: int
    counterevidence_count: int
    counterevidence_ratio_ppm: int
    active_support_clusters: int
    support_ratio_ppm: int
    source_diversity: int
    challenge_categories: Sequence[str]
    evidence_root: str
    challenge_root: str
    lease_root: str
    net_evidence: int
    score: int
    ready_for_stability: bool
    reason_codes: Sequence[str]
    schema: str = COMMIT_CANDIDATE_METRICS_SCHEMA_V2
    metrics_root: str = ""

    def __post_init__(self) -> None:
        if self.schema != COMMIT_CANDIDATE_METRICS_SCHEMA_V2:
            raise ValueError("commit candidate metrics schema is unsupported")
        _require_text(self.candidate_ref, "commit metrics candidate_ref")
        _require_root(self.claim_root, "commit metrics claim_root")
        for field in (
            "positive_evidence_count",
            "counterevidence_count",
            "active_support_clusters",
            "source_diversity",
            "score",
        ):
            _require_count(getattr(self, field), f"commit metrics {field}")
        if (
            type(self.net_evidence) is not int
            or not -MAX_AUTHORITY_REVISION_V2
            <= self.net_evidence
            <= MAX_AUTHORITY_REVISION_V2
            or self.score != max(0, self.net_evidence)
        ):
            raise ValueError("commit metrics net evidence projection is invalid")
        for field in ("counterevidence_ratio_ppm", "support_ratio_ppm"):
            _require_count(
                getattr(self, field), f"commit metrics {field}", maximum=1_000_000
            )
        for field in ("evidence_root", "challenge_root", "lease_root"):
            _require_root(getattr(self, field), f"commit metrics {field}")
        _require_bool(self.ready_for_stability, "commit metrics ready_for_stability")
        object.__setattr__(
            self,
            "challenge_categories",
            _canonical_texts(self.challenge_categories, "commit challenge categories"),
        )
        object.__setattr__(
            self,
            "reason_codes",
            _canonical_texts(self.reason_codes, "commit candidate reason codes"),
        )
        if self.ready_for_stability == bool(self.reason_codes):
            raise ValueError("commit candidate readiness and reasons are inconsistent")
        _install_root(
            self, "metrics_root", self.metrics_root, "candidate-metrics", self._body()
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "candidate_ref": self.candidate_ref,
            "claim_root": self.claim_root,
            "positive_evidence_count": self.positive_evidence_count,
            "counterevidence_count": self.counterevidence_count,
            "counterevidence_ratio_ppm": self.counterevidence_ratio_ppm,
            "active_support_clusters": self.active_support_clusters,
            "support_ratio_ppm": self.support_ratio_ppm,
            "source_diversity": self.source_diversity,
            "challenge_categories": list(self.challenge_categories),
            "evidence_root": self.evidence_root,
            "challenge_root": self.challenge_root,
            "lease_root": self.lease_root,
            "net_evidence": self.net_evidence,
            "score": self.score,
            "ready_for_stability": self.ready_for_stability,
            "reason_codes": list(self.reason_codes),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "metrics_root": self.metrics_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitCandidateMetricsV2:
        fields = frozenset(
            {
                "schema",
                "candidate_ref",
                "claim_root",
                "positive_evidence_count",
                "counterevidence_count",
                "counterevidence_ratio_ppm",
                "active_support_clusters",
                "support_ratio_ppm",
                "source_diversity",
                "challenge_categories",
                "evidence_root",
                "challenge_root",
                "lease_root",
                "net_evidence",
                "score",
                "ready_for_stability",
                "reason_codes",
                "metrics_root",
            }
        )
        value = _exact_mapping(payload, fields, "commit candidate metrics v2")
        challenge_categories = tuple(
            cast(str, item)
            for item in _exact_array(
                value["challenge_categories"],
                "commit metrics challenge_categories",
            )
        )
        reason_codes = tuple(
            cast(str, item)
            for item in _exact_array(
                value["reason_codes"],
                "commit metrics reason_codes",
            )
        )
        decoded = cls(
            candidate_ref=cast(str, value["candidate_ref"]),
            claim_root=cast(str, value["claim_root"]),
            positive_evidence_count=cast(int, value["positive_evidence_count"]),
            counterevidence_count=cast(int, value["counterevidence_count"]),
            counterevidence_ratio_ppm=cast(
                int,
                value["counterevidence_ratio_ppm"],
            ),
            active_support_clusters=cast(int, value["active_support_clusters"]),
            support_ratio_ppm=cast(int, value["support_ratio_ppm"]),
            source_diversity=cast(int, value["source_diversity"]),
            challenge_categories=challenge_categories,
            evidence_root=cast(str, value["evidence_root"]),
            challenge_root=cast(str, value["challenge_root"]),
            lease_root=cast(str, value["lease_root"]),
            net_evidence=cast(int, value["net_evidence"]),
            score=cast(int, value["score"]),
            ready_for_stability=cast(bool, value["ready_for_stability"]),
            reason_codes=reason_codes,
            schema=cast(str, value["schema"]),
            metrics_root=cast(str, value["metrics_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "commit candidate metrics v2"
        )
        return decoded


@dataclass(frozen=True, slots=True)
class CommitAssessmentV2:
    current_step: int
    candidate_metrics: Sequence[CommitCandidateMetricsV2]
    leader_candidate_ref: str
    tied_candidate_refs: Sequence[str]
    unique_leader: bool
    leader_margin: int
    leader_ready_for_stability: bool
    stop_clear: bool
    permission_allowed: bool
    blocker_refs: Sequence[str]
    equivocation_refs: Sequence[str]
    replay_conflict_refs: Sequence[str]
    reason_codes: Sequence[str]
    dependency_set_root: str
    evaluation_context_root: str
    collective_evidence_root: str
    collective_challenge_root: str
    collective_claim_root: str
    collective_lease_root: str
    schema: str = COMMIT_DECISION_ASSESSMENT_SCHEMA_V2
    assessment_root: str = ""

    def __post_init__(self) -> None:
        if self.schema != COMMIT_DECISION_ASSESSMENT_SCHEMA_V2:
            raise ValueError("commit assessment schema is unsupported")
        _require_count(self.current_step, "commit assessment current_step")
        if type(self.candidate_metrics) not in (list, tuple):
            raise TypeError("commit assessment metrics must be an exact array or tuple")
        metrics = tuple(self.candidate_metrics)
        if any(type(item) is not CommitCandidateMetricsV2 for item in metrics):
            raise TypeError("commit assessment metrics contain a noncanonical record")
        ordered = tuple(
            sorted(metrics, key=lambda item: item.candidate_ref.encode("utf-8"))
        )
        refs = tuple(item.candidate_ref for item in ordered)
        if len(refs) != len(set(refs)):
            raise ValueError("commit assessment candidate set is invalid")
        object.__setattr__(self, "candidate_metrics", ordered)
        _require_text(
            self.leader_candidate_ref, "commit assessment leader", allow_empty=True
        )
        ties = _canonical_texts(self.tied_candidate_refs, "commit assessment ties")
        object.__setattr__(self, "tied_candidate_refs", ties)
        for field in (
            "unique_leader",
            "leader_ready_for_stability",
            "stop_clear",
            "permission_allowed",
        ):
            _require_bool(getattr(self, field), f"commit assessment {field}")
        _require_count(self.leader_margin, "commit assessment leader_margin")
        if self.unique_leader != bool(self.leader_candidate_ref and len(ties) == 1):
            raise ValueError("commit assessment leader projection is inconsistent")
        if ties and not set(ties).issubset(refs):
            raise ValueError("commit assessment tie set is undeclared")
        for field in ("blocker_refs", "equivocation_refs", "replay_conflict_refs"):
            object.__setattr__(
                self,
                field,
                _canonical_roots(getattr(self, field), f"commit assessment {field}"),
            )
        object.__setattr__(
            self,
            "reason_codes",
            _canonical_texts(self.reason_codes, "commit assessment reason codes"),
        )
        for field in (
            "dependency_set_root",
            "evaluation_context_root",
            "collective_evidence_root",
            "collective_challenge_root",
            "collective_claim_root",
            "collective_lease_root",
        ):
            _require_root(getattr(self, field), f"commit assessment {field}")
        _install_root(
            self, "assessment_root", self.assessment_root, "assessment", self._body()
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "current_step": self.current_step,
            "candidate_metrics": [item.to_dict() for item in self.candidate_metrics],
            "leader_candidate_ref": self.leader_candidate_ref,
            "tied_candidate_refs": list(self.tied_candidate_refs),
            "unique_leader": self.unique_leader,
            "leader_margin": self.leader_margin,
            "leader_ready_for_stability": self.leader_ready_for_stability,
            "stop_clear": self.stop_clear,
            "permission_allowed": self.permission_allowed,
            "blocker_refs": list(self.blocker_refs),
            "equivocation_refs": list(self.equivocation_refs),
            "replay_conflict_refs": list(self.replay_conflict_refs),
            "reason_codes": list(self.reason_codes),
            "dependency_set_root": self.dependency_set_root,
            "evaluation_context_root": self.evaluation_context_root,
            "collective_evidence_root": self.collective_evidence_root,
            "collective_challenge_root": self.collective_challenge_root,
            "collective_claim_root": self.collective_claim_root,
            "collective_lease_root": self.collective_lease_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "assessment_root": self.assessment_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitAssessmentV2:
        fields = frozenset(
            {
                "schema",
                "current_step",
                "candidate_metrics",
                "leader_candidate_ref",
                "tied_candidate_refs",
                "unique_leader",
                "leader_margin",
                "leader_ready_for_stability",
                "stop_clear",
                "permission_allowed",
                "blocker_refs",
                "equivocation_refs",
                "replay_conflict_refs",
                "reason_codes",
                "dependency_set_root",
                "evaluation_context_root",
                "collective_evidence_root",
                "collective_challenge_root",
                "collective_claim_root",
                "collective_lease_root",
                "assessment_root",
            }
        )
        value = _exact_mapping(payload, fields, "commit assessment v2")
        raw_metrics = _exact_array(
            value["candidate_metrics"],
            "commit assessment metrics",
        )
        metrics = tuple(
            CommitCandidateMetricsV2.from_dict(item) for item in raw_metrics
        )

        def texts(field: str) -> tuple[str, ...]:
            return tuple(
                cast(str, item)
                for item in _exact_array(
                    value[field],
                    f"commit assessment {field}",
                )
            )

        decoded = cls(
            current_step=cast(int, value["current_step"]),
            candidate_metrics=metrics,
            leader_candidate_ref=cast(str, value["leader_candidate_ref"]),
            tied_candidate_refs=texts("tied_candidate_refs"),
            unique_leader=cast(bool, value["unique_leader"]),
            leader_margin=cast(int, value["leader_margin"]),
            leader_ready_for_stability=cast(
                bool,
                value["leader_ready_for_stability"],
            ),
            stop_clear=cast(bool, value["stop_clear"]),
            permission_allowed=cast(bool, value["permission_allowed"]),
            blocker_refs=texts("blocker_refs"),
            equivocation_refs=texts("equivocation_refs"),
            replay_conflict_refs=texts("replay_conflict_refs"),
            reason_codes=texts("reason_codes"),
            dependency_set_root=cast(str, value["dependency_set_root"]),
            evaluation_context_root=cast(str, value["evaluation_context_root"]),
            collective_evidence_root=cast(str, value["collective_evidence_root"]),
            collective_challenge_root=cast(
                str,
                value["collective_challenge_root"],
            ),
            collective_claim_root=cast(str, value["collective_claim_root"]),
            collective_lease_root=cast(str, value["collective_lease_root"]),
            schema=cast(str, value["schema"]),
            assessment_root=cast(str, value["assessment_root"]),
        )
        _require_canonical_wire(payload, decoded.to_dict(), "commit assessment v2")
        return decoded


__all__ = ("CommitAssessmentV2", "CommitCandidateMetricsV2")
