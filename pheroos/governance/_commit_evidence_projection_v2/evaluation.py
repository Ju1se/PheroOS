"""Pure deterministic evaluation of one Commit Evidence v2 projection."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from pheroos.governance.commit_numeric import MAX_AUTHORITY_INTEGER, WEIGHT_SCALE

from pheroos.governance._commit_evidence_projection_v2.common import (
    MAX_COMMIT_EVIDENCE_RECORDS_V2,
    canonical_roots_v2,
    canonical_texts_v2,
    evidence_root_v2,
    exact_array_v2,
    exact_object_v2,
    require_canonical_wire_v2,
    require_count_v2,
    require_root_v2,
    require_text_v2,
)
from pheroos.governance._commit_evidence_projection_v2.projection import (
    CommitEvidenceProjectionV2,
)
from pheroos.governance._commit_evidence_projection_v2.records import (
    ChallengeResultV2,
    CommitEvidenceDispositionV2,
    CommitEvidenceKindV2,
    QualifiedCommitEvidenceV2,
)


_MAX_AUTHORITY_INTEGER_V2: int = int(MAX_AUTHORITY_INTEGER)
_WEIGHT_SCALE_V2: int = int(WEIGHT_SCALE)


@dataclass(frozen=True, slots=True)
class CommitEvidenceEvaluationV2:
    projection_root: str
    candidate_ref: str
    claim_root: str
    evaluated_at_step: int
    replayed_record_roots: tuple[str, ...]
    missing_replay_receipt_roots: tuple[str, ...]
    active_counter_record_roots: tuple[str, ...]
    resolved_counter_record_roots: tuple[str, ...]
    blocking_critical_counter_roots: tuple[str, ...]
    covered_challenge_categories: tuple[str, ...]
    missing_challenge_categories: tuple[str, ...]
    positive_evidence: int
    counterevidence: int
    weighted_counterevidence: int
    net_evidence: int
    counterevidence_ratio_ppm: int
    source_diversity: int
    replay_complete: bool
    positive_threshold_satisfied: bool
    counter_limit_satisfied: bool
    counter_ratio_satisfied: bool
    source_diversity_satisfied: bool
    critical_counterevidence_clear: bool
    challenge_coverage_satisfied: bool
    evidence_gates_satisfied: bool
    evaluation_root: str = ""

    def __post_init__(self) -> None:
        _validate_evaluation(self)
        expected = evidence_root_v2("evaluation", self._body())
        if self.evaluation_root not in ("", expected):
            raise ValueError("commit evidence evaluation_root is mismatched")
        object.__setattr__(self, "evaluation_root", expected)

    def _body(self) -> dict[str, object]:
        return {
            "projection_root": self.projection_root,
            "candidate_ref": self.candidate_ref,
            "claim_root": self.claim_root,
            "evaluated_at_step": self.evaluated_at_step,
            "replayed_record_roots": list(self.replayed_record_roots),
            "missing_replay_receipt_roots": list(self.missing_replay_receipt_roots),
            "active_counter_record_roots": list(self.active_counter_record_roots),
            "resolved_counter_record_roots": list(self.resolved_counter_record_roots),
            "blocking_critical_counter_roots": list(
                self.blocking_critical_counter_roots
            ),
            "covered_challenge_categories": list(self.covered_challenge_categories),
            "missing_challenge_categories": list(self.missing_challenge_categories),
            "positive_evidence": self.positive_evidence,
            "counterevidence": self.counterevidence,
            "weighted_counterevidence": self.weighted_counterevidence,
            "net_evidence": self.net_evidence,
            "counterevidence_ratio_ppm": self.counterevidence_ratio_ppm,
            "source_diversity": self.source_diversity,
            "replay_complete": self.replay_complete,
            "positive_threshold_satisfied": self.positive_threshold_satisfied,
            "counter_limit_satisfied": self.counter_limit_satisfied,
            "counter_ratio_satisfied": self.counter_ratio_satisfied,
            "source_diversity_satisfied": self.source_diversity_satisfied,
            "critical_counterevidence_clear": self.critical_counterevidence_clear,
            "challenge_coverage_satisfied": self.challenge_coverage_satisfied,
            "evidence_gates_satisfied": self.evidence_gates_satisfied,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "evaluation_root": self.evaluation_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitEvidenceEvaluationV2:
        value = exact_object_v2(
            payload,
            _EVALUATION_FIELDS,
            "commit evidence evaluation v2",
        )
        for field in _EVALUATION_ROOT_ARRAY_FIELDS:
            value[field] = tuple(
                exact_array_v2(
                    value[field],
                    f"commit evidence evaluation {field}",
                    limit=MAX_COMMIT_EVIDENCE_RECORDS_V2 * 2,
                )
            )
        for field in _EVALUATION_TEXT_ARRAY_FIELDS:
            value[field] = tuple(
                exact_array_v2(
                    value[field],
                    f"commit evidence evaluation {field}",
                    limit=MAX_COMMIT_EVIDENCE_RECORDS_V2,
                )
            )
        decoded = cls(**value)
        require_canonical_wire_v2(
            payload,
            decoded.to_dict(),
            "commit evidence evaluation v2",
        )
        return decoded


def evaluate_commit_evidence_projection_v2(
    projection: CommitEvidenceProjectionV2,
    *,
    candidate_ref: str,
    claim_root: str,
    replay_receipt_roots: Sequence[str],
) -> CommitEvidenceEvaluationV2:
    """Rebuild all metrics; portable inputs remain non-authoritative data."""

    if type(projection) is not CommitEvidenceProjectionV2:
        raise TypeError("commit evidence evaluation requires exact projection v2")
    candidate = require_text_v2(
        candidate_ref, "commit evidence evaluation candidate_ref"
    )
    claim = require_root_v2(claim_root, "commit evidence evaluation claim_root")
    replayed = frozenset(
        canonical_roots_v2(
            replay_receipt_roots,
            "commit evidence evaluation replay receipts",
            limit=MAX_COMMIT_EVIDENCE_RECORDS_V2 * 2,
        )
    )
    scoped = tuple(
        item
        for item in projection.records
        if item.candidate_ref == candidate and item.claim_root == claim
    )
    expected_replay = {root for item in scoped for root in item.replay_receipt_roots}
    missing = tuple(sorted(expected_replay - replayed))
    counted = tuple(
        item for item in scoped if set(item.replay_receipt_roots).issubset(replayed)
    )
    policy = projection.evidence_policy
    positive = tuple(
        item for item in counted if item.kind is CommitEvidenceKindV2.POSITIVE
    )
    counters = tuple(
        item for item in counted if item.kind is CommitEvidenceKindV2.COUNTER
    )
    active_counters = tuple(
        item
        for item in counters
        if item.disposition
        in {
            CommitEvidenceDispositionV2.UNRESOLVED,
            CommitEvidenceDispositionV2.ACCEPTED,
        }
    )
    resolved_counters = tuple(item for item in counters if item not in active_counters)
    positive_total = _saturating_sum(
        _independence_group_contributions(positive, policy.positive_group_cap).values()
    )
    counter_total = _saturating_sum(
        _independence_group_contributions(
            active_counters, policy.counter_group_cap
        ).values()
    )
    weighted_counter = _saturating_scaled_product(
        counter_total,
        policy.counter_weight_ppm,
    )
    net = _saturating_signed(positive_total - weighted_counter)
    denominator = positive_total + counter_total
    ratio = 0 if denominator == 0 else (counter_total * _WEIGHT_SCALE_V2) // denominator
    diversity = _verified_source_diversity(
        positive,
        floor=policy.domain_contribution_floor,
        cap=policy.positive_group_cap,
    )
    covered = _covered_challenge_categories(counted, counters)
    missing_categories = tuple(
        sorted(
            set(policy.required_challenge_categories) - covered,
            key=lambda item: item.encode("utf-8"),
        )
    )
    critical = tuple(
        sorted(
            item.record_root
            for item in active_counters
            if item.materiality_ppm > 0 and item.criticality_ppm > 0
        )
    )
    replay_complete = not missing
    positive_ok = positive_total >= policy.minimum_positive_evidence
    counter_ok = counter_total <= policy.maximum_counterevidence
    ratio_ok = ratio <= policy.maximum_counterevidence_ratio_ppm
    diversity_ok = diversity >= policy.minimum_source_diversity
    critical_clear = not critical
    challenge_ok = not missing_categories
    gates = all(
        (
            replay_complete,
            positive_ok,
            counter_ok,
            ratio_ok,
            diversity_ok,
            critical_clear,
            challenge_ok,
        )
    )
    return CommitEvidenceEvaluationV2(
        projection_root=projection.projection_root,
        candidate_ref=candidate,
        claim_root=claim,
        evaluated_at_step=projection.current_step,
        replayed_record_roots=tuple(sorted(item.record_root for item in counted)),
        missing_replay_receipt_roots=missing,
        active_counter_record_roots=tuple(
            sorted(item.record_root for item in active_counters)
        ),
        resolved_counter_record_roots=tuple(
            sorted(item.record_root for item in resolved_counters)
        ),
        blocking_critical_counter_roots=critical,
        covered_challenge_categories=tuple(
            sorted(covered, key=lambda item: item.encode("utf-8"))
        ),
        missing_challenge_categories=missing_categories,
        positive_evidence=positive_total,
        counterevidence=counter_total,
        weighted_counterevidence=weighted_counter,
        net_evidence=net,
        counterevidence_ratio_ppm=ratio,
        source_diversity=diversity,
        replay_complete=replay_complete,
        positive_threshold_satisfied=positive_ok,
        counter_limit_satisfied=counter_ok,
        counter_ratio_satisfied=ratio_ok,
        source_diversity_satisfied=diversity_ok,
        critical_counterevidence_clear=critical_clear,
        challenge_coverage_satisfied=challenge_ok,
        evidence_gates_satisfied=gates,
    )


def _independence_group_contributions(
    records: Sequence[QualifiedCommitEvidenceV2], cap: int
) -> dict[str, int]:
    raw: dict[str, int] = {}
    for item in records:
        raw[item.independence_ref] = min(
            _saturating_sum((raw.get(item.independence_ref, 0), item.weight_ppm)),
            cap,
        )
    return {group: min(value, cap) for group, value in raw.items()}


def _saturating_sum(values: Iterable[int]) -> int:
    mathematical = sum(values)
    return min(mathematical, _MAX_AUTHORITY_INTEGER_V2)


def _saturating_scaled_product(left: int, right: int) -> int:
    mathematical = (left * right) // _WEIGHT_SCALE_V2
    return min(mathematical, _MAX_AUTHORITY_INTEGER_V2)


def _saturating_signed(value: int) -> int:
    return max(
        -_MAX_AUTHORITY_INTEGER_V2,
        min(value, _MAX_AUTHORITY_INTEGER_V2),
    )


def _verified_source_diversity(
    records: Sequence[QualifiedCommitEvidenceV2], *, floor: int, cap: int
) -> int:
    pair_weights: dict[tuple[str, str], int] = {}
    for item in records:
        key = (item.failure_domain_ref, item.cluster_ref)
        pair_weights[key] = min(
            _saturating_sum((pair_weights.get(key, 0), item.weight_ppm)),
            cap,
        )
    domain_clusters: dict[str, set[str]] = {}
    for (domain, cluster), weight in pair_weights.items():
        if weight >= floor:
            domain_clusters.setdefault(domain, set()).add(cluster)
    qualifying = tuple(sorted(domain_clusters))
    matched_cluster: dict[str, str] = {}
    for domain in qualifying:
        _augment_domain(domain, domain_clusters, matched_cluster, set())
    return len(matched_cluster)


def _augment_domain(
    domain: str,
    edges: dict[str, set[str]],
    matched_cluster: dict[str, str],
    visited: set[str],
) -> bool:
    for cluster in sorted(edges.get(domain, set())):
        if cluster in visited:
            continue
        visited.add(cluster)
        prior = matched_cluster.get(cluster)
        if prior is None or _augment_domain(prior, edges, matched_cluster, visited):
            matched_cluster[cluster] = domain
            return True
    return False


def _covered_challenge_categories(
    records: Sequence[QualifiedCommitEvidenceV2],
    counters: Sequence[QualifiedCommitEvidenceV2],
) -> set[str]:
    counter_roots = {item.attestation_root for item in counters}
    covered: set[str] = set()
    for item in records:
        if item.kind is not CommitEvidenceKindV2.CHALLENGE:
            continue
        if not set(item.result_observation_roots).issubset(counter_roots):
            raise ValueError("challenge result refers to unavailable counterevidence")
        if item.challenge_result is not ChallengeResultV2.INCONCLUSIVE:
            covered.add(item.category_ref)
    return covered


def _validate_evaluation(evaluation: CommitEvidenceEvaluationV2) -> None:
    require_root_v2(
        evaluation.projection_root,
        "commit evidence evaluation projection_root",
    )
    require_text_v2(
        evaluation.candidate_ref,
        "commit evidence evaluation candidate_ref",
    )
    require_root_v2(
        evaluation.claim_root,
        "commit evidence evaluation claim_root",
    )
    require_count_v2(
        evaluation.evaluated_at_step,
        "commit evidence evaluation evaluated_at_step",
    )
    for field in _EVALUATION_ROOT_ARRAY_FIELDS:
        canonical = canonical_roots_v2(
            getattr(evaluation, field),
            f"commit evidence evaluation {field}",
            limit=MAX_COMMIT_EVIDENCE_RECORDS_V2 * 2,
        )
        object.__setattr__(evaluation, field, canonical)
    for field in _EVALUATION_TEXT_ARRAY_FIELDS:
        canonical_text = canonical_texts_v2(
            getattr(evaluation, field),
            f"commit evidence evaluation {field}",
            limit=MAX_COMMIT_EVIDENCE_RECORDS_V2,
            allow_empty=True,
        )
        object.__setattr__(evaluation, field, canonical_text)
    for field in _EVALUATION_UNSIGNED_FIELDS:
        value = getattr(evaluation, field)
        if type(value) is not int or not 0 <= value <= _MAX_AUTHORITY_INTEGER_V2:
            raise ValueError(f"commit evidence evaluation {field} is out of bounds")
    if (
        type(evaluation.net_evidence) is not int
        or abs(evaluation.net_evidence) > _MAX_AUTHORITY_INTEGER_V2
    ):
        raise ValueError("commit evidence evaluation net_evidence is out of bounds")
    if evaluation.counterevidence_ratio_ppm > _WEIGHT_SCALE_V2:
        raise ValueError("commit evidence evaluation ratio exceeds its scale")
    for field in _EVALUATION_BOOL_FIELDS:
        if type(getattr(evaluation, field)) is not bool:
            raise TypeError(f"commit evidence evaluation {field} must be exact bool")
    expected_gate = all(
        getattr(evaluation, field) for field in _EVALUATION_GATE_COMPONENT_FIELDS
    )
    if (
        evaluation.replay_complete is not (not evaluation.missing_replay_receipt_roots)
        or evaluation.challenge_coverage_satisfied
        is not (not evaluation.missing_challenge_categories)
        or evaluation.critical_counterevidence_clear
        is not (not evaluation.blocking_critical_counter_roots)
        or evaluation.evidence_gates_satisfied is not expected_gate
    ):
        raise ValueError("commit evidence evaluation booleans are inconsistent")


_EVALUATION_ROOT_ARRAY_FIELDS = (
    "replayed_record_roots",
    "missing_replay_receipt_roots",
    "active_counter_record_roots",
    "resolved_counter_record_roots",
    "blocking_critical_counter_roots",
)
_EVALUATION_TEXT_ARRAY_FIELDS = (
    "covered_challenge_categories",
    "missing_challenge_categories",
)
_EVALUATION_UNSIGNED_FIELDS = (
    "positive_evidence",
    "counterevidence",
    "weighted_counterevidence",
    "counterevidence_ratio_ppm",
    "source_diversity",
)
_EVALUATION_GATE_COMPONENT_FIELDS = (
    "replay_complete",
    "positive_threshold_satisfied",
    "counter_limit_satisfied",
    "counter_ratio_satisfied",
    "source_diversity_satisfied",
    "critical_counterevidence_clear",
    "challenge_coverage_satisfied",
)
_EVALUATION_BOOL_FIELDS = (
    *_EVALUATION_GATE_COMPONENT_FIELDS,
    "evidence_gates_satisfied",
)
_EVALUATION_FIELDS = frozenset(
    {
        "projection_root",
        "candidate_ref",
        "claim_root",
        "evaluated_at_step",
        *_EVALUATION_ROOT_ARRAY_FIELDS,
        *_EVALUATION_TEXT_ARRAY_FIELDS,
        *_EVALUATION_UNSIGNED_FIELDS,
        "net_evidence",
        *_EVALUATION_BOOL_FIELDS,
        "evaluation_root",
    }
)


__all__ = ["CommitEvidenceEvaluationV2", "evaluate_commit_evidence_projection_v2"]
