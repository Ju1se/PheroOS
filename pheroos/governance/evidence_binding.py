from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TypedDict

from pheroos.governance._commit_validation import (
    require_commit_assurance,
    require_commit_fingerprint,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.challenge import (
    ChallengeCoverage,
    VerifiedChallenge,
    evaluate_challenge_coverage,
    verified_challenge_fingerprint,
    verified_challenge_matches,
)
from pheroos.governance.commit_numeric import (
    MAX_AUTHORITY_INTEGER,
    WEIGHT_SCALE,
    checked_add,
    checked_subtract,
    commit_payload_fingerprint,
    multiply_scaled,
    require_authority_integer,
    require_scaled_integer,
    scaled_ratio,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.observation import (
    CounterevidenceDisposition,
    CounterevidenceDispositionKind,
    ObservationPolarity,
    VerifiedObservation,
    counterevidence_disposition_fingerprint,
    counterevidence_disposition_is_authoritative,
    counterevidence_disposition_matches,
    counterevidence_is_material_critical,
    observation_weight_ppm,
    verified_observation_fingerprint,
    verified_observation_matches,
)
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CommitAssurance,
    EvidenceQualificationPolicy,
)


EVIDENCE_BINDING_VERSION = "pheroos-evidence-binding-v1"
_EVIDENCE_BINDING_ISSUANCE = object()


class _BindingCoordinates(TypedDict):
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    candidate_id: str
    claim_fingerprint: str
    epoch: int
    current_step: int


class _BindingRootCoordinates(TypedDict):
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    candidate_id: str
    claim_fingerprint: str
    epoch: int


@dataclass(frozen=True)
class EvidenceBinding:
    evidence_id: str
    binding_version: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    candidate_id: str
    claim_fingerprint: str
    epoch: int
    positive_observation_fingerprints: tuple[str, ...]
    counter_observation_fingerprints: tuple[str, ...]
    disposition_fingerprints: tuple[str, ...]
    challenge_fingerprints: tuple[str, ...]
    positive_root: str
    counter_root: str
    disposition_root: str
    challenge_root: str
    evidence_root: str
    issuer_id: str
    authority: AuthorityLevel
    issued_at_step: int
    expires_at_step: int
    provenance: str
    trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        for field_name in (
            "positive_observation_fingerprints",
            "counter_observation_fingerprints",
            "disposition_fingerprints",
            "challenge_fingerprints",
        ):
            object.__setattr__(
                self,
                field_name,
                _canonical_fingerprints(
                    getattr(self, field_name),
                    f"evidence binding {field_name}",
                    allow_empty=True,
                ),
            )
        _validate_evidence_binding_shape(self)


@dataclass(frozen=True)
class EvidenceGroupContribution:
    independence_group: str
    observation_fingerprints: tuple[str, ...]
    raw_contribution: int
    group_cap: int
    counted_contribution: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observation_fingerprints",
            _canonical_fingerprints(
                self.observation_fingerprints,
                "evidence group observation fingerprints",
                allow_empty=False,
            ),
        )
        require_commit_text(
            self.independence_group,
            "evidence group independence_group",
        )
        raw = require_authority_integer(
            self.raw_contribution,
            "evidence group raw_contribution",
        )
        cap = require_authority_integer(self.group_cap, "evidence group cap")
        counted = require_authority_integer(
            self.counted_contribution,
            "evidence group counted_contribution",
        )
        if cap <= 0 or counted != min(raw, cap):
            raise GovernanceError("evidence group contribution is not correctly capped")


@dataclass(frozen=True)
class SourceDomainContribution:
    source_domain: str
    observation_fingerprints: tuple[str, ...]
    contribution: int
    contribution_floor: int
    qualifies: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observation_fingerprints",
            _canonical_fingerprints(
                self.observation_fingerprints,
                "source domain observation fingerprints",
                allow_empty=False,
            ),
        )
        require_commit_text(self.source_domain, "evidence source_domain")
        contribution = require_authority_integer(
            self.contribution,
            "source domain contribution",
        )
        floor = require_authority_integer(
            self.contribution_floor,
            "source domain contribution floor",
        )
        if floor <= 0:
            raise GovernanceError("source domain contribution floor must be positive")
        object.__setattr__(self, "qualifies", contribution >= floor)


@dataclass(frozen=True)
class EvidenceSummary:
    evidence_binding_fingerprint: str
    positive_groups: tuple[EvidenceGroupContribution, ...]
    counter_groups: tuple[EvidenceGroupContribution, ...]
    source_domains: tuple[SourceDomainContribution, ...]
    active_counter_observation_fingerprints: tuple[str, ...]
    resolved_counter_observation_fingerprints: tuple[str, ...]
    blocking_critical_counter_observation_fingerprints: tuple[str, ...]
    positive_evidence: int
    counterevidence: int
    weighted_counterevidence: int
    net_evidence: int
    counterevidence_ratio_ppm: int
    source_diversity: int
    challenge_coverage: ChallengeCoverage
    positive_threshold_satisfied: bool = field(init=False)
    counter_limit_satisfied: bool = field(init=False)
    counter_ratio_satisfied: bool = field(init=False)
    source_diversity_satisfied: bool = field(init=False)
    critical_counterevidence_clear: bool = field(init=False)
    challenge_coverage_satisfied: bool = field(init=False)
    evidence_gates_satisfied: bool = field(init=False)
    _minimum_positive_evidence: int = field(repr=False, compare=False)
    _maximum_counterevidence: int = field(repr=False, compare=False)
    _maximum_counterevidence_ratio_ppm: int = field(repr=False, compare=False)
    _minimum_source_diversity: int = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        require_commit_fingerprint(
            self.evidence_binding_fingerprint,
            "evidence summary binding fingerprint",
        )
        object.__setattr__(
            self,
            "positive_groups",
            _canonical_group_contributions(self.positive_groups, "positive groups"),
        )
        object.__setattr__(
            self,
            "counter_groups",
            _canonical_group_contributions(self.counter_groups, "counter groups"),
        )
        object.__setattr__(
            self,
            "source_domains",
            _canonical_domain_contributions(self.source_domains),
        )
        for field_name in (
            "active_counter_observation_fingerprints",
            "resolved_counter_observation_fingerprints",
            "blocking_critical_counter_observation_fingerprints",
        ):
            object.__setattr__(
                self,
                field_name,
                _canonical_fingerprints(
                    getattr(self, field_name),
                    f"evidence summary {field_name}",
                    allow_empty=True,
                ),
            )
        for field_name in (
            "positive_evidence",
            "counterevidence",
            "weighted_counterevidence",
            "counterevidence_ratio_ppm",
            "source_diversity",
            "_minimum_positive_evidence",
            "_maximum_counterevidence",
            "_maximum_counterevidence_ratio_ppm",
            "_minimum_source_diversity",
        ):
            require_authority_integer(
                getattr(self, field_name),
                f"evidence summary {field_name}",
            )
        require_authority_integer(
            self.net_evidence,
            "evidence summary net_evidence",
            allow_negative=True,
        )
        if self.counterevidence_ratio_ppm > WEIGHT_SCALE:
            raise GovernanceError("evidence summary counter ratio exceeds scale")
        if type(self.challenge_coverage) is not ChallengeCoverage:
            raise GovernanceError("evidence summary challenge coverage is invalid")
        if self.source_diversity != sum(
            1 for item in self.source_domains if item.qualifies
        ):
            raise GovernanceError("evidence summary source diversity is inconsistent")

        positive_ok = self.positive_evidence >= self._minimum_positive_evidence
        counter_ok = self.counterevidence <= self._maximum_counterevidence
        ratio_ok = (
            self.counterevidence_ratio_ppm <= self._maximum_counterevidence_ratio_ppm
        )
        diversity_ok = self.source_diversity >= self._minimum_source_diversity
        critical_clear = not self.blocking_critical_counter_observation_fingerprints
        challenge_ok = self.challenge_coverage.complete
        object.__setattr__(self, "positive_threshold_satisfied", positive_ok)
        object.__setattr__(self, "counter_limit_satisfied", counter_ok)
        object.__setattr__(self, "counter_ratio_satisfied", ratio_ok)
        object.__setattr__(self, "source_diversity_satisfied", diversity_ok)
        object.__setattr__(self, "critical_counterevidence_clear", critical_clear)
        object.__setattr__(self, "challenge_coverage_satisfied", challenge_ok)
        object.__setattr__(
            self,
            "evidence_gates_satisfied",
            bool(
                positive_ok
                and counter_ok
                and ratio_ok
                and diversity_ok
                and critical_clear
                and challenge_ok
            ),
        )


def bind_evidence(
    *,
    evidence_id: str,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    candidate_id: str,
    claim_fingerprint: str,
    epoch: int,
    positive_observations: Sequence[VerifiedObservation],
    counter_observations: Sequence[VerifiedObservation],
    dispositions: Sequence[CounterevidenceDisposition],
    challenges: Sequence[VerifiedChallenge],
    issuer_id: str,
    authority: AuthorityLevel,
    current_step: int,
    provenance: str,
    trace_event_id: str,
) -> EvidenceBinding:
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("evidence binding requires governance authority")
    normalized = _normalize_binding_coordinates(
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        candidate_id=candidate_id,
        claim_fingerprint=claim_fingerprint,
        epoch=epoch,
        current_step=current_step,
    )
    components = _validate_binding_components(
        positive_observations=positive_observations,
        counter_observations=counter_observations,
        dispositions=dispositions,
        challenges=challenges,
        **normalized,
    )
    normalized_evidence_id = require_commit_text(
        evidence_id,
        "evidence binding evidence_id",
    )
    roots = _binding_roots(
        evidence_id=normalized_evidence_id,
        binding_version=EVIDENCE_BINDING_VERSION,
        positive_fingerprints=components.positive_fingerprints,
        counter_fingerprints=components.counter_fingerprints,
        disposition_fingerprints=components.disposition_fingerprints,
        challenge_fingerprints=components.challenge_fingerprints,
        **_root_coordinates(normalized),
    )
    binding = EvidenceBinding(
        evidence_id=normalized_evidence_id,
        binding_version=EVIDENCE_BINDING_VERSION,
        profile=normalized["profile"],
        assurance=normalized["assurance"],
        manifest_root=normalized["manifest_root"],
        commit_policy_root=normalized["commit_policy_root"],
        protocol_id=normalized["protocol_id"],
        run_id=normalized["run_id"],
        target=normalized["target"],
        candidate_id=normalized["candidate_id"],
        claim_fingerprint=normalized["claim_fingerprint"],
        epoch=normalized["epoch"],
        positive_observation_fingerprints=components.positive_fingerprints,
        counter_observation_fingerprints=components.counter_fingerprints,
        disposition_fingerprints=components.disposition_fingerprints,
        challenge_fingerprints=components.challenge_fingerprints,
        positive_root=roots["positive_root"],
        counter_root=roots["counter_root"],
        disposition_root=roots["disposition_root"],
        challenge_root=roots["challenge_root"],
        evidence_root=roots["evidence_root"],
        issuer_id=require_commit_text(issuer_id, "evidence binding issuer_id"),
        authority=authority,
        issued_at_step=normalized["current_step"],
        expires_at_step=components.expires_at_step,
        provenance=require_commit_text(provenance, "evidence binding provenance"),
        trace_event_id=require_commit_text(
            trace_event_id,
            "evidence binding trace_event_id",
        ),
    )
    object.__setattr__(
        binding,
        "_issuance",
        (_EVIDENCE_BINDING_ISSUANCE, _evidence_binding_snapshot(binding)),
    )
    return binding


def evidence_binding_payload(binding: EvidenceBinding) -> dict[str, object]:
    if type(binding) is not EvidenceBinding:
        raise GovernanceError("evidence binding must use the canonical record")
    _validate_evidence_binding_shape(binding)
    return {
        "assurance": binding.assurance,
        "authority": binding.authority,
        "binding_version": binding.binding_version,
        "candidate_id": binding.candidate_id,
        "challenge_fingerprints": binding.challenge_fingerprints,
        "challenge_root": binding.challenge_root,
        "claim_fingerprint": binding.claim_fingerprint,
        "commit_policy_root": binding.commit_policy_root,
        "counter_observation_fingerprints": (binding.counter_observation_fingerprints),
        "counter_root": binding.counter_root,
        "disposition_fingerprints": binding.disposition_fingerprints,
        "disposition_root": binding.disposition_root,
        "epoch": binding.epoch,
        "evidence_id": binding.evidence_id,
        "evidence_root": binding.evidence_root,
        "expires_at_step": binding.expires_at_step,
        "issued_at_step": binding.issued_at_step,
        "issuer_id": binding.issuer_id,
        "manifest_root": binding.manifest_root,
        "positive_observation_fingerprints": (
            binding.positive_observation_fingerprints
        ),
        "positive_root": binding.positive_root,
        "profile": binding.profile,
        "protocol_id": binding.protocol_id,
        "provenance": binding.provenance,
        "run_id": binding.run_id,
        "target": binding.target,
        "trace_event_id": binding.trace_event_id,
    }


def evidence_binding_fingerprint(binding: EvidenceBinding) -> str:
    return _evidence_binding_snapshot(binding)


def evidence_binding_is_authoritative(binding: object) -> bool:
    if type(binding) is not EvidenceBinding:
        return False
    try:
        _validate_evidence_binding_shape(binding)
        issuance = binding._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _EVIDENCE_BINDING_ISSUANCE
            and issuance[1] == _evidence_binding_snapshot(binding)
        )
    except Exception:
        return False


def evidence_binding_matches(
    binding: EvidenceBinding | None,
    *,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    candidate_id: str,
    claim_fingerprint: str,
    epoch: int,
    current_step: int,
) -> bool:
    try:
        normalized = _normalize_binding_coordinates(
            profile=profile,
            assurance=assurance,
            manifest_root=manifest_root,
            commit_policy_root=commit_policy_root,
            protocol_id=protocol_id,
            run_id=run_id,
            target=target,
            candidate_id=candidate_id,
            claim_fingerprint=claim_fingerprint,
            epoch=epoch,
            current_step=current_step,
        )
        return bool(
            evidence_binding_is_authoritative(binding)
            and binding is not None
            and binding.profile == normalized["profile"]
            and binding.assurance is normalized["assurance"]
            and binding.manifest_root == normalized["manifest_root"]
            and binding.commit_policy_root == normalized["commit_policy_root"]
            and binding.protocol_id == normalized["protocol_id"]
            and binding.run_id == normalized["run_id"]
            and binding.target == normalized["target"]
            and binding.candidate_id == normalized["candidate_id"]
            and binding.claim_fingerprint == normalized["claim_fingerprint"]
            and binding.epoch == normalized["epoch"]
            and binding.issued_at_step
            <= normalized["current_step"]
            < binding.expires_at_step
        )
    except GovernanceError:
        return False


def rebuild_evidence_binding_roots(binding: EvidenceBinding) -> dict[str, str]:
    if type(binding) is not EvidenceBinding:
        raise GovernanceError("evidence binding must use the canonical record")
    _validate_evidence_binding_shape(binding)
    return _binding_roots(
        evidence_id=binding.evidence_id,
        binding_version=binding.binding_version,
        profile=binding.profile,
        assurance=binding.assurance,
        manifest_root=binding.manifest_root,
        commit_policy_root=binding.commit_policy_root,
        protocol_id=binding.protocol_id,
        run_id=binding.run_id,
        target=binding.target,
        candidate_id=binding.candidate_id,
        claim_fingerprint=binding.claim_fingerprint,
        epoch=binding.epoch,
        positive_fingerprints=binding.positive_observation_fingerprints,
        counter_fingerprints=binding.counter_observation_fingerprints,
        disposition_fingerprints=binding.disposition_fingerprints,
        challenge_fingerprints=binding.challenge_fingerprints,
    )


def evaluate_evidence_binding(
    binding: EvidenceBinding,
    *,
    positive_observations: Sequence[VerifiedObservation],
    counter_observations: Sequence[VerifiedObservation],
    dispositions: Sequence[CounterevidenceDisposition],
    challenges: Sequence[VerifiedChallenge],
    evidence_policy: EvidenceQualificationPolicy,
    current_step: int,
) -> EvidenceSummary:
    if not evidence_binding_is_authoritative(binding):
        raise GovernanceError("evidence evaluation requires an authoritative binding")
    current = require_commit_step(current_step, "evidence evaluation current_step")
    if not binding.issued_at_step <= current < binding.expires_at_step:
        raise GovernanceError("evidence binding is not fresh")
    _validate_evidence_policy(evidence_policy)
    normalized = _normalize_binding_coordinates(
        profile=binding.profile,
        assurance=binding.assurance,
        manifest_root=binding.manifest_root,
        commit_policy_root=binding.commit_policy_root,
        protocol_id=binding.protocol_id,
        run_id=binding.run_id,
        target=binding.target,
        candidate_id=binding.candidate_id,
        claim_fingerprint=binding.claim_fingerprint,
        epoch=binding.epoch,
        current_step=current,
    )
    components = _validate_binding_components(
        positive_observations=positive_observations,
        counter_observations=counter_observations,
        dispositions=dispositions,
        challenges=challenges,
        **normalized,
    )
    for observation in (*tuple(positive_observations), *tuple(counter_observations)):
        if observation.quality_ppm < evidence_policy.minimum_quality_ppm:
            raise GovernanceError(
                "evidence binding contains observation below the quality floor"
            )
        if observation.relevance_ppm < evidence_policy.minimum_relevance_ppm:
            raise GovernanceError(
                "evidence binding contains observation below the relevance floor"
            )
        if (
            observation.expires_at_step - observation.observed_at_step
            > evidence_policy.observation_ttl_steps
        ):
            raise GovernanceError(
                "evidence binding contains observation beyond the policy TTL"
            )
    for challenge in tuple(challenges):
        if (
            challenge.expires_at_step - challenge.executed_at_step
            > evidence_policy.observation_ttl_steps
        ):
            raise GovernanceError(
                "evidence binding contains challenge beyond the policy TTL"
            )
    if (
        components.positive_fingerprints != binding.positive_observation_fingerprints
        or components.counter_fingerprints != binding.counter_observation_fingerprints
        or components.disposition_fingerprints != binding.disposition_fingerprints
        or components.challenge_fingerprints != binding.challenge_fingerprints
        or rebuild_evidence_binding_roots(binding)
        != {
            "positive_root": binding.positive_root,
            "counter_root": binding.counter_root,
            "disposition_root": binding.disposition_root,
            "challenge_root": binding.challenge_root,
            "evidence_root": binding.evidence_root,
        }
    ):
        raise GovernanceError("evidence binding leaves or roots do not reconstruct")

    disposition_by_counter = {
        item.counter_observation_fingerprint: item for item in dispositions
    }
    active_counters: list[VerifiedObservation] = []
    resolved_counters: list[VerifiedObservation] = []
    blocking_critical: list[str] = []
    for observation in counter_observations:
        fingerprint = verified_observation_fingerprint(observation)
        disposition = disposition_by_counter[fingerprint]
        if disposition.kind in {
            CounterevidenceDispositionKind.UNRESOLVED,
            CounterevidenceDispositionKind.ACCEPTED,
        }:
            active_counters.append(observation)
            if counterevidence_is_material_critical(observation):
                blocking_critical.append(fingerprint)
        else:
            resolved_counters.append(observation)

    positive_groups = _group_contributions(
        positive_observations,
        cap=evidence_policy.positive_group_cap,
    )
    counter_groups = _group_contributions(
        active_counters,
        cap=evidence_policy.counter_group_cap,
    )
    source_domains = _source_domain_contributions(
        positive_observations,
        contribution_floor=evidence_policy.domain_contribution_floor,
    )
    positive_evidence = checked_add(
        *(item.counted_contribution for item in positive_groups)
    )
    counterevidence = checked_add(
        *(item.counted_contribution for item in counter_groups)
    )
    weighted_counter = multiply_scaled(
        counterevidence,
        evidence_policy.counter_weight_ppm,
    )
    net_evidence = checked_subtract(positive_evidence, weighted_counter)
    counter_ratio = scaled_ratio(
        counterevidence,
        positive_evidence + counterevidence,
    )
    coverage = evaluate_challenge_coverage(
        challenges,
        required_categories=evidence_policy.required_challenge_categories,
        profile=binding.profile,
        assurance=binding.assurance,
        manifest_root=binding.manifest_root,
        commit_policy_root=binding.commit_policy_root,
        protocol_id=binding.protocol_id,
        run_id=binding.run_id,
        target=binding.target,
        candidate_id=binding.candidate_id,
        claim_fingerprint=binding.claim_fingerprint,
        epoch=binding.epoch,
        current_step=current,
    )
    return EvidenceSummary(
        evidence_binding_fingerprint=evidence_binding_fingerprint(binding),
        positive_groups=positive_groups,
        counter_groups=counter_groups,
        source_domains=source_domains,
        active_counter_observation_fingerprints=tuple(
            verified_observation_fingerprint(item) for item in active_counters
        ),
        resolved_counter_observation_fingerprints=tuple(
            verified_observation_fingerprint(item) for item in resolved_counters
        ),
        blocking_critical_counter_observation_fingerprints=tuple(blocking_critical),
        positive_evidence=positive_evidence,
        counterevidence=counterevidence,
        weighted_counterevidence=weighted_counter,
        net_evidence=net_evidence,
        counterevidence_ratio_ppm=counter_ratio,
        source_diversity=sum(1 for item in source_domains if item.qualifies),
        challenge_coverage=coverage,
        _minimum_positive_evidence=evidence_policy.minimum_positive_evidence,
        _maximum_counterevidence=evidence_policy.maximum_counterevidence,
        _maximum_counterevidence_ratio_ppm=(
            evidence_policy.maximum_counterevidence_ratio_ppm
        ),
        _minimum_source_diversity=evidence_policy.minimum_source_diversity,
    )


def evidence_summary_payload(summary: EvidenceSummary) -> dict[str, object]:
    if type(summary) is not EvidenceSummary:
        raise GovernanceError("evidence summary must use the canonical record")
    return {
        "active_counter_observation_fingerprints": (
            summary.active_counter_observation_fingerprints
        ),
        "blocking_critical_counter_observation_fingerprints": (
            summary.blocking_critical_counter_observation_fingerprints
        ),
        "challenge_coverage": {
            "challenge_fingerprints": summary.challenge_coverage.challenge_fingerprints,
            "complete": summary.challenge_coverage.complete,
            "covered_categories": summary.challenge_coverage.covered_categories,
            "missing_categories": summary.challenge_coverage.missing_categories,
            "required_categories": summary.challenge_coverage.required_categories,
        },
        "counter_groups": tuple(
            _group_contribution_payload(item) for item in summary.counter_groups
        ),
        "counter_limit_satisfied": summary.counter_limit_satisfied,
        "counter_ratio_satisfied": summary.counter_ratio_satisfied,
        "counterevidence": summary.counterevidence,
        "counterevidence_ratio_ppm": summary.counterevidence_ratio_ppm,
        "critical_counterevidence_clear": summary.critical_counterevidence_clear,
        "evidence_binding_fingerprint": summary.evidence_binding_fingerprint,
        "evidence_gates_satisfied": summary.evidence_gates_satisfied,
        "maximum_counterevidence": summary._maximum_counterevidence,
        "maximum_counterevidence_ratio_ppm": (
            summary._maximum_counterevidence_ratio_ppm
        ),
        "minimum_positive_evidence": summary._minimum_positive_evidence,
        "minimum_source_diversity": summary._minimum_source_diversity,
        "net_evidence": summary.net_evidence,
        "positive_evidence": summary.positive_evidence,
        "positive_groups": tuple(
            _group_contribution_payload(item) for item in summary.positive_groups
        ),
        "positive_threshold_satisfied": summary.positive_threshold_satisfied,
        "resolved_counter_observation_fingerprints": (
            summary.resolved_counter_observation_fingerprints
        ),
        "source_diversity": summary.source_diversity,
        "source_diversity_satisfied": summary.source_diversity_satisfied,
        "source_domains": tuple(
            _source_domain_payload(item) for item in summary.source_domains
        ),
        "weighted_counterevidence": summary.weighted_counterevidence,
    }


def evidence_summary_fingerprint(summary: EvidenceSummary, *, profile: str) -> str:
    return commit_payload_fingerprint(
        evidence_summary_payload(summary),
        schema="pheroos-evidence-summary-v1",
        profile=require_commit_profile(profile, "evidence summary profile"),
    )


@dataclass(frozen=True)
class _BindingComponents:
    positive_fingerprints: tuple[str, ...]
    counter_fingerprints: tuple[str, ...]
    disposition_fingerprints: tuple[str, ...]
    challenge_fingerprints: tuple[str, ...]
    expires_at_step: int


def _validate_binding_components(
    *,
    positive_observations: Sequence[VerifiedObservation],
    counter_observations: Sequence[VerifiedObservation],
    dispositions: Sequence[CounterevidenceDisposition],
    challenges: Sequence[VerifiedChallenge],
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    candidate_id: str,
    claim_fingerprint: str,
    epoch: int,
    current_step: int,
) -> _BindingComponents:
    positive = tuple(positive_observations)
    counters = tuple(counter_observations)
    disposition_records = tuple(dispositions)
    challenge_records = tuple(challenges)
    if not positive and not counters:
        raise GovernanceError("evidence binding requires at least one observation")

    observation_ids: set[str] = set()
    nonces: set[str] = set()
    fingerprints: set[str] = set()
    expiry_values: list[int] = []
    positive_fingerprints: list[str] = []
    counter_fingerprints: list[str] = []
    for observations, polarity, output in (
        (positive, ObservationPolarity.SUPPORT, positive_fingerprints),
        (counters, ObservationPolarity.CONTRADICT, counter_fingerprints),
    ):
        for observation in observations:
            if not verified_observation_matches(
                observation,
                profile=profile,
                assurance=assurance,
                manifest_root=manifest_root,
                commit_policy_root=commit_policy_root,
                protocol_id=protocol_id,
                run_id=run_id,
                target=target,
                candidate_id=candidate_id,
                claim_fingerprint=claim_fingerprint,
                epoch=epoch,
                current_step=current_step,
                polarity=polarity,
            ):
                raise GovernanceError(
                    "evidence binding observation is non-authoritative, stale, or unbound"
                )
            fingerprint = verified_observation_fingerprint(observation)
            if (
                observation.observation_id in observation_ids
                or observation.nonce in nonces
                or fingerprint in fingerprints
            ):
                raise GovernanceError("evidence binding contains a replay or duplicate")
            observation_ids.add(observation.observation_id)
            nonces.add(observation.nonce)
            fingerprints.add(fingerprint)
            output.append(fingerprint)
            expiry_values.append(observation.expires_at_step)

    canonical_positive = _canonical_fingerprints(
        positive_fingerprints,
        "positive observation fingerprints",
        allow_empty=True,
    )
    canonical_counter = _canonical_fingerprints(
        counter_fingerprints,
        "counter observation fingerprints",
        allow_empty=True,
    )
    disposition_by_counter: dict[str, CounterevidenceDisposition] = {}
    disposition_fingerprints: list[str] = []
    for disposition in disposition_records:
        if not counterevidence_disposition_is_authoritative(disposition):
            raise GovernanceError("evidence binding disposition is not authoritative")
        counter = next(
            (
                item
                for item in counters
                if verified_observation_fingerprint(item)
                == disposition.counter_observation_fingerprint
            ),
            None,
        )
        if counter is None or not counterevidence_disposition_matches(
            disposition,
            counter,
            current_step=current_step,
        ):
            raise GovernanceError(
                "evidence binding disposition is stale or references another counter"
            )
        if disposition.counter_observation_fingerprint in disposition_by_counter:
            raise GovernanceError(
                "evidence binding contains multiple dispositions for a counter"
            )
        if not set(disposition.rebuttal_observation_fingerprints).issubset(
            canonical_positive
        ):
            raise GovernanceError(
                "evidence binding omits rebuttal evidence from its positive leaves"
            )
        disposition_by_counter[disposition.counter_observation_fingerprint] = (
            disposition
        )
        fingerprint = counterevidence_disposition_fingerprint(disposition)
        if fingerprint in disposition_fingerprints:
            raise GovernanceError("evidence binding contains a duplicate disposition")
        disposition_fingerprints.append(fingerprint)
        expiry_values.append(disposition.expires_at_step)
    if set(disposition_by_counter) != set(canonical_counter):
        raise GovernanceError(
            "every counter observation requires exactly one disposition"
        )

    challenge_ids: set[str] = set()
    challenge_fingerprints: list[str] = []
    for challenge in challenge_records:
        if not verified_challenge_matches(
            challenge,
            profile=profile,
            assurance=assurance,
            manifest_root=manifest_root,
            commit_policy_root=commit_policy_root,
            protocol_id=protocol_id,
            run_id=run_id,
            target=target,
            candidate_id=candidate_id,
            claim_fingerprint=claim_fingerprint,
            epoch=epoch,
            current_step=current_step,
        ):
            raise GovernanceError(
                "evidence binding challenge is non-authoritative, stale, or unbound"
            )
        if challenge.challenge_id in challenge_ids or challenge.nonce in nonces:
            raise GovernanceError("evidence binding contains a challenge replay")
        challenge_ids.add(challenge.challenge_id)
        nonces.add(challenge.nonce)
        if not set(challenge.result_observation_fingerprints).issubset(
            canonical_counter
        ):
            raise GovernanceError(
                "evidence binding challenge result is absent from counter leaves"
            )
        fingerprint = verified_challenge_fingerprint(challenge)
        if fingerprint in challenge_fingerprints:
            raise GovernanceError("evidence binding contains a duplicate challenge")
        challenge_fingerprints.append(fingerprint)
        expiry_values.append(challenge.expires_at_step)

    return _BindingComponents(
        positive_fingerprints=canonical_positive,
        counter_fingerprints=canonical_counter,
        disposition_fingerprints=_canonical_fingerprints(
            disposition_fingerprints,
            "disposition fingerprints",
            allow_empty=True,
        ),
        challenge_fingerprints=_canonical_fingerprints(
            challenge_fingerprints,
            "challenge fingerprints",
            allow_empty=True,
        ),
        expires_at_step=min(expiry_values),
    )


def _normalize_binding_coordinates(
    *,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    candidate_id: str,
    claim_fingerprint: str,
    epoch: int,
    current_step: int,
) -> _BindingCoordinates:
    normalized_profile = require_commit_profile(profile, "evidence binding profile")
    normalized_assurance = require_commit_assurance(
        assurance,
        "evidence binding assurance",
    )
    if (
        normalized_profile
        not in COMMIT_PROFILES_BY_ASSURANCE[normalized_assurance.value]
    ):
        raise GovernanceError("commit profile/assurance mismatch")
    return {
        "profile": normalized_profile,
        "assurance": normalized_assurance,
        "manifest_root": require_commit_fingerprint(
            manifest_root,
            "evidence binding manifest_root",
        ),
        "commit_policy_root": require_commit_fingerprint(
            commit_policy_root,
            "evidence binding commit_policy_root",
        ),
        "protocol_id": require_commit_text(
            protocol_id,
            "evidence binding protocol_id",
        ),
        "run_id": require_commit_text(run_id, "evidence binding run_id"),
        "target": require_commit_text(target, "evidence binding target"),
        "candidate_id": require_commit_text(
            candidate_id,
            "evidence binding candidate_id",
        ),
        "claim_fingerprint": require_commit_fingerprint(
            claim_fingerprint,
            "evidence binding claim_fingerprint",
        ),
        "epoch": require_commit_step(epoch, "evidence binding epoch"),
        "current_step": require_commit_step(
            current_step,
            "evidence binding current_step",
        ),
    }


def _root_coordinates(normalized: _BindingCoordinates) -> _BindingRootCoordinates:
    return {
        "profile": normalized["profile"],
        "assurance": normalized["assurance"],
        "manifest_root": normalized["manifest_root"],
        "commit_policy_root": normalized["commit_policy_root"],
        "protocol_id": normalized["protocol_id"],
        "run_id": normalized["run_id"],
        "target": normalized["target"],
        "candidate_id": normalized["candidate_id"],
        "claim_fingerprint": normalized["claim_fingerprint"],
        "epoch": normalized["epoch"],
    }


def _binding_roots(
    *,
    evidence_id: str,
    binding_version: str,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    candidate_id: str,
    claim_fingerprint: str,
    epoch: int,
    positive_fingerprints: Sequence[str],
    counter_fingerprints: Sequence[str],
    disposition_fingerprints: Sequence[str],
    challenge_fingerprints: Sequence[str],
) -> dict[str, str]:
    positive = _canonical_fingerprints(
        positive_fingerprints,
        "positive root fingerprints",
        allow_empty=True,
    )
    counter = _canonical_fingerprints(
        counter_fingerprints,
        "counter root fingerprints",
        allow_empty=True,
    )
    dispositions = _canonical_fingerprints(
        disposition_fingerprints,
        "disposition root fingerprints",
        allow_empty=True,
    )
    challenges = _canonical_fingerprints(
        challenge_fingerprints,
        "challenge root fingerprints",
        allow_empty=True,
    )
    positive_root = commit_payload_fingerprint(
        {"observation_fingerprints": positive},
        schema="pheroos-positive-evidence-leaves-v1",
        profile=profile,
    )
    counter_root = commit_payload_fingerprint(
        {"observation_fingerprints": counter},
        schema="pheroos-counterevidence-leaves-v1",
        profile=profile,
    )
    disposition_root = commit_payload_fingerprint(
        {"disposition_fingerprints": dispositions},
        schema="pheroos-counterevidence-disposition-leaves-v1",
        profile=profile,
    )
    challenge_root = commit_payload_fingerprint(
        {"challenge_fingerprints": challenges},
        schema="pheroos-challenge-leaves-v1",
        profile=profile,
    )
    evidence_root = commit_payload_fingerprint(
        {
            "assurance": assurance,
            "binding_version": binding_version,
            "candidate_id": candidate_id,
            "challenge_root": challenge_root,
            "claim_fingerprint": claim_fingerprint,
            "commit_policy_root": commit_policy_root,
            "counter_root": counter_root,
            "disposition_root": disposition_root,
            "epoch": epoch,
            "evidence_id": evidence_id,
            "manifest_root": manifest_root,
            "positive_root": positive_root,
            "profile": profile,
            "protocol_id": protocol_id,
            "run_id": run_id,
            "target": target,
        },
        schema="pheroos-evidence-root-v1",
        profile=profile,
    )
    return {
        "positive_root": positive_root,
        "counter_root": counter_root,
        "disposition_root": disposition_root,
        "challenge_root": challenge_root,
        "evidence_root": evidence_root,
    }


def _validate_evidence_binding_shape(binding: EvidenceBinding) -> None:
    for field_name in (
        "evidence_id",
        "binding_version",
        "protocol_id",
        "run_id",
        "target",
        "candidate_id",
        "issuer_id",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(binding, field_name),
            f"evidence binding {field_name}",
        )
    if binding.binding_version != EVIDENCE_BINDING_VERSION:
        raise GovernanceError("evidence binding version is unsupported")
    assurance = require_commit_assurance(
        binding.assurance,
        "evidence binding assurance",
    )
    require_commit_profile(binding.profile, "evidence binding profile")
    if binding.profile not in COMMIT_PROFILES_BY_ASSURANCE[assurance.value]:
        raise GovernanceError("commit profile/assurance mismatch")
    for field_name in (
        "manifest_root",
        "commit_policy_root",
        "claim_fingerprint",
        "positive_root",
        "counter_root",
        "disposition_root",
        "challenge_root",
        "evidence_root",
    ):
        require_commit_fingerprint(
            getattr(binding, field_name),
            f"evidence binding {field_name}",
        )
    for field_name in (
        "positive_observation_fingerprints",
        "counter_observation_fingerprints",
        "disposition_fingerprints",
        "challenge_fingerprints",
    ):
        observed = getattr(binding, field_name)
        canonical = _canonical_fingerprints(
            observed,
            f"evidence binding {field_name}",
            allow_empty=True,
        )
        if observed != canonical:
            raise GovernanceError(f"evidence binding {field_name} is not canonical")
    if (
        not binding.positive_observation_fingerprints
        and not binding.counter_observation_fingerprints
    ):
        raise GovernanceError("evidence binding requires at least one observation")
    if set(binding.positive_observation_fingerprints).intersection(
        binding.counter_observation_fingerprints
    ):
        raise GovernanceError("positive and counter evidence leaves overlap")
    require_commit_step(binding.epoch, "evidence binding epoch")
    issued = require_commit_step(
        binding.issued_at_step,
        "evidence binding issued_at_step",
    )
    expires = require_commit_step(
        binding.expires_at_step,
        "evidence binding expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("evidence binding expiry must be after issuance")
    if type(binding.authority) is not AuthorityLevel or not can_verify(
        binding.authority
    ):
        raise GovernanceError("evidence binding authority is invalid")
    expected_roots = rebuild_evidence_binding_roots_unchecked(binding)
    if any(getattr(binding, key) != value for key, value in expected_roots.items()):
        raise GovernanceError("evidence binding roots are not reconstructable")


def rebuild_evidence_binding_roots_unchecked(
    binding: EvidenceBinding,
) -> dict[str, str]:
    return _binding_roots(
        evidence_id=binding.evidence_id,
        binding_version=binding.binding_version,
        profile=binding.profile,
        assurance=binding.assurance,
        manifest_root=binding.manifest_root,
        commit_policy_root=binding.commit_policy_root,
        protocol_id=binding.protocol_id,
        run_id=binding.run_id,
        target=binding.target,
        candidate_id=binding.candidate_id,
        claim_fingerprint=binding.claim_fingerprint,
        epoch=binding.epoch,
        positive_fingerprints=binding.positive_observation_fingerprints,
        counter_fingerprints=binding.counter_observation_fingerprints,
        disposition_fingerprints=binding.disposition_fingerprints,
        challenge_fingerprints=binding.challenge_fingerprints,
    )


def _validate_evidence_policy(policy: EvidenceQualificationPolicy) -> None:
    if type(policy) is not EvidenceQualificationPolicy:
        raise GovernanceError(
            "evidence evaluation requires the canonical evidence policy"
        )
    if policy.numeric_scale != WEIGHT_SCALE:
        raise GovernanceError("evidence policy numeric scale is unsupported")
    for field_name in (
        "positive_group_cap",
        "counter_group_cap",
        "minimum_positive_evidence",
        "domain_contribution_floor",
        "minimum_source_diversity",
        "observation_ttl_steps",
    ):
        value = require_authority_integer(
            getattr(policy, field_name),
            f"evidence policy {field_name}",
        )
        if value <= 0:
            raise GovernanceError(f"evidence policy {field_name} must be positive")
    require_authority_integer(
        policy.maximum_counterevidence,
        "evidence policy maximum_counterevidence",
    )
    require_scaled_integer(
        policy.counter_weight_ppm,
        "evidence policy counter_weight_ppm",
    )
    require_scaled_integer(
        policy.maximum_counterevidence_ratio_ppm,
        "evidence policy maximum_counterevidence_ratio_ppm",
        maximum=WEIGHT_SCALE,
    )
    require_scaled_integer(
        policy.minimum_quality_ppm,
        "evidence policy minimum_quality_ppm",
        maximum=WEIGHT_SCALE,
    )
    require_scaled_integer(
        policy.minimum_relevance_ppm,
        "evidence policy minimum_relevance_ppm",
        maximum=WEIGHT_SCALE,
    )
    required = tuple(policy.required_challenge_categories)
    if not required:
        raise GovernanceError("evidence policy requires challenge categories")
    if tuple(sorted(required)) != tuple(sorted(set(required))):
        raise GovernanceError("evidence policy challenge categories are duplicated")
    for category in required:
        require_commit_text(category, "evidence policy challenge category")
    if policy.require_provenance is not True or policy.require_trace is not True:
        raise GovernanceError("evidence policy must require provenance and trace")


def _group_contributions(
    observations: Sequence[VerifiedObservation],
    *,
    cap: int,
) -> tuple[EvidenceGroupContribution, ...]:
    normalized_cap = require_authority_integer(cap, "evidence group cap")
    # The only caller first validates the canonical evidence policy, including
    # the strictly-positive cap invariant.
    grouped: dict[str, list[VerifiedObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.independence_group, []).append(observation)
    contributions: list[EvidenceGroupContribution] = []
    for group, records in grouped.items():
        mathematical_raw = sum(observation_weight_ppm(item) for item in records)
        # Only the capped contribution affects authority.  Saturate the
        # diagnostic raw leaf at the wire bound after evaluating the exact
        # arbitrary-precision sum, never before applying the group cap.
        bounded_raw = min(mathematical_raw, MAX_AUTHORITY_INTEGER)
        contributions.append(
            EvidenceGroupContribution(
                independence_group=group,
                observation_fingerprints=tuple(
                    verified_observation_fingerprint(item) for item in records
                ),
                raw_contribution=bounded_raw,
                group_cap=normalized_cap,
                counted_contribution=min(mathematical_raw, normalized_cap),
            )
        )
    return tuple(sorted(contributions, key=lambda item: item.independence_group))


def _source_domain_contributions(
    observations: Sequence[VerifiedObservation],
    *,
    contribution_floor: int,
) -> tuple[SourceDomainContribution, ...]:
    floor = require_authority_integer(
        contribution_floor,
        "source domain contribution floor",
    )
    # The only caller first validates the canonical evidence policy, including
    # the strictly-positive contribution-floor invariant.
    grouped: dict[str, list[VerifiedObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.source_domain, []).append(observation)
    contributions = tuple(
        SourceDomainContribution(
            source_domain=domain,
            observation_fingerprints=tuple(
                verified_observation_fingerprint(item) for item in records
            ),
            contribution=min(
                sum(observation_weight_ppm(item) for item in records),
                MAX_AUTHORITY_INTEGER,
            ),
            contribution_floor=floor,
        )
        for domain, records in grouped.items()
    )
    return tuple(sorted(contributions, key=lambda item: item.source_domain))


def _canonical_group_contributions(
    values: Sequence[EvidenceGroupContribution],
    field_name: str,
) -> tuple[EvidenceGroupContribution, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise GovernanceError(f"{field_name} must be a sequence")
    records = tuple(values)
    if any(type(item) is not EvidenceGroupContribution for item in records):
        raise GovernanceError(f"{field_name} contains an invalid contribution")
    if len({item.independence_group for item in records}) != len(records):
        raise GovernanceError(f"{field_name} contains a duplicate group")
    return tuple(sorted(records, key=lambda item: item.independence_group))


def _canonical_domain_contributions(
    values: Sequence[SourceDomainContribution],
) -> tuple[SourceDomainContribution, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise GovernanceError("source domains must be a sequence")
    records = tuple(values)
    if any(type(item) is not SourceDomainContribution for item in records):
        raise GovernanceError("source domains contain an invalid contribution")
    if len({item.source_domain for item in records}) != len(records):
        raise GovernanceError("source domains contain a duplicate")
    return tuple(sorted(records, key=lambda item: item.source_domain))


def _group_contribution_payload(
    contribution: EvidenceGroupContribution,
) -> dict[str, object]:
    return {
        "counted_contribution": contribution.counted_contribution,
        "group_cap": contribution.group_cap,
        "independence_group": contribution.independence_group,
        "observation_fingerprints": contribution.observation_fingerprints,
        "raw_contribution": contribution.raw_contribution,
    }


def _source_domain_payload(
    contribution: SourceDomainContribution,
) -> dict[str, object]:
    return {
        "contribution": contribution.contribution,
        "contribution_floor": contribution.contribution_floor,
        "observation_fingerprints": contribution.observation_fingerprints,
        "qualifies": contribution.qualifies,
        "source_domain": contribution.source_domain,
    }


def _canonical_fingerprints(
    values: Sequence[str],
    field_name: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise GovernanceError(f"{field_name} must be a sequence")
    fingerprints = tuple(
        require_commit_fingerprint(value, field_name) for value in values
    )
    if not fingerprints and not allow_empty:
        raise GovernanceError(f"{field_name} must not be empty")
    if len(set(fingerprints)) != len(fingerprints):
        raise GovernanceError(f"{field_name} contains a duplicate")
    return tuple(sorted(fingerprints))


def _evidence_binding_snapshot(binding: EvidenceBinding) -> str:
    return commit_payload_fingerprint(
        evidence_binding_payload(binding),
        schema="pheroos-evidence-binding-authority-v1",
        profile=binding.profile,
    )


__all__ = [
    "EVIDENCE_BINDING_VERSION",
    "EvidenceBinding",
    "EvidenceGroupContribution",
    "EvidenceSummary",
    "SourceDomainContribution",
    "bind_evidence",
    "evidence_binding_fingerprint",
    "evidence_binding_is_authoritative",
    "evidence_binding_matches",
    "evidence_binding_payload",
    "evidence_summary_fingerprint",
    "evidence_summary_payload",
    "evaluate_evidence_binding",
    "rebuild_evidence_binding_roots",
]
