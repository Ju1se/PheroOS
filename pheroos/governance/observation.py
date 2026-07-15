from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from pheroos.governance._commit_validation import (
    require_commit_assurance,
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
    require_fresh_interval,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit_numeric import (
    WEIGHT_SCALE,
    commit_payload_fingerprint,
    multiply_scaled,
    require_scaled_integer,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.principal import (
    PrincipalVerification,
    principal_verification_fingerprint,
    principal_verification_matches,
)
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CommitAssurance,
    EvidenceQualificationPolicy,
)


class ObservationPolarity(StrEnum):
    SUPPORT = "support"
    CONTRADICT = "contradict"


class CounterevidenceDispositionKind(StrEnum):
    UNRESOLVED = "unresolved"
    REBUTTED = "rebutted"
    ACCEPTED = "accepted"
    IMMATERIAL = "immaterial"


_VERIFIED_OBSERVATION_ISSUANCE = object()
_COUNTEREVIDENCE_DISPOSITION_ISSUANCE = object()


@dataclass(frozen=True)
class ObservationAttestation:
    observation_id: str
    target: str
    candidate_id: str
    claim_fingerprint: str
    principal_id: str
    polarity: ObservationPolarity
    independence_group: str
    source_domain: str
    payload_fingerprint: str
    reported_quality_ppm: int
    reported_relevance_ppm: int
    reported_materiality_ppm: int
    reported_criticality_ppm: int
    provenance: str
    nonce: str
    observed_at_step: int
    expires_at_step: int
    trace_event_id: str

    def __post_init__(self) -> None:
        _validate_observation_attestation(self)


@dataclass(frozen=True)
class VerifiedObservation:
    observation_id: str
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
    principal_id: str
    principal_cluster_id: str
    principal_verification_fingerprint: str
    attestation_fingerprint: str
    polarity: ObservationPolarity
    independence_group: str
    source_domain: str
    payload_fingerprint: str
    quality_ppm: int
    relevance_ppm: int
    materiality_ppm: int
    criticality_ppm: int
    nonce: str
    observed_at_step: int
    verified_at_step: int
    expires_at_step: int
    attestation_provenance: str
    attestation_trace_event_id: str
    verifier_id: str
    authority: AuthorityLevel
    verification_provenance: str
    verification_trace_event_id: str
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _validate_verified_observation_shape(self)


@dataclass(frozen=True)
class CounterevidenceDisposition:
    disposition_id: str
    kind: CounterevidenceDispositionKind
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
    counter_observation_fingerprint: str
    rebuttal_observation_fingerprints: tuple[str, ...]
    resolution_ref: str
    reason_codes: tuple[str, ...]
    verifier_id: str
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
        object.__setattr__(
            self,
            "rebuttal_observation_fingerprints",
            _canonical_fingerprints(
                self.rebuttal_observation_fingerprints,
                "counterevidence disposition rebuttal observation fingerprints",
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "reason_codes",
            require_commit_labels(
                self.reason_codes,
                "counterevidence disposition reason_codes",
            ),
        )
        _validate_counterevidence_disposition_shape(self)


def observation_attestation_payload(
    attestation: ObservationAttestation,
) -> dict[str, object]:
    if type(attestation) is not ObservationAttestation:
        raise GovernanceError("observation attestation must use the canonical record")
    _validate_observation_attestation(attestation)
    return {
        "candidate_id": attestation.candidate_id,
        "claim_fingerprint": attestation.claim_fingerprint,
        "expires_at_step": attestation.expires_at_step,
        "independence_group": attestation.independence_group,
        "nonce": attestation.nonce,
        "observation_id": attestation.observation_id,
        "observed_at_step": attestation.observed_at_step,
        "payload_fingerprint": attestation.payload_fingerprint,
        "polarity": attestation.polarity,
        "principal_id": attestation.principal_id,
        "provenance": attestation.provenance,
        "reported_criticality_ppm": attestation.reported_criticality_ppm,
        "reported_materiality_ppm": attestation.reported_materiality_ppm,
        "reported_quality_ppm": attestation.reported_quality_ppm,
        "reported_relevance_ppm": attestation.reported_relevance_ppm,
        "source_domain": attestation.source_domain,
        "target": attestation.target,
        "trace_event_id": attestation.trace_event_id,
    }


def observation_attestation_fingerprint(
    attestation: ObservationAttestation,
) -> str:
    return commit_payload_fingerprint(
        observation_attestation_payload(attestation),
        schema="pheroos-observation-attestation-v1",
        profile="pheroos-commit-authority-v1",
    )


def verify_observation_attestation(
    attestation: ObservationAttestation,
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
    principal_verification: PrincipalVerification,
    evidence_policy: EvidenceQualificationPolicy,
    quality_ppm: int,
    relevance_ppm: int,
    materiality_ppm: int,
    criticality_ppm: int,
    verifier_id: str,
    authority: AuthorityLevel,
    current_step: int,
    verification_provenance: str,
    verification_trace_event_id: str,
    prior_observations: Sequence[VerifiedObservation],
) -> VerifiedObservation:
    if type(attestation) is not ObservationAttestation:
        raise GovernanceError("observation attestation must use the canonical record")
    _validate_observation_attestation(attestation)
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("observation verification requires governance authority")

    normalized_profile = require_commit_profile(
        profile,
        "verified observation profile",
    )
    normalized_assurance = require_commit_assurance(
        assurance,
        "verified observation assurance",
    )
    _require_profile_assurance(normalized_profile, normalized_assurance)
    normalized_manifest_root = require_commit_fingerprint(
        manifest_root,
        "verified observation manifest_root",
    )
    normalized_policy_root = require_commit_fingerprint(
        commit_policy_root,
        "verified observation commit_policy_root",
    )
    normalized_protocol_id = require_commit_text(
        protocol_id,
        "verified observation protocol_id",
    )
    normalized_run_id = require_commit_text(
        run_id,
        "verified observation run_id",
    )
    normalized_target = require_commit_text(target, "verified observation target")
    normalized_candidate = require_commit_text(
        candidate_id,
        "verified observation candidate_id",
    )
    normalized_claim = require_commit_fingerprint(
        claim_fingerprint,
        "verified observation claim_fingerprint",
    )
    normalized_epoch = require_commit_step(epoch, "verified observation epoch")
    normalized_current = require_commit_step(
        current_step,
        "verified observation current_step",
    )

    if (
        attestation.target != normalized_target
        or attestation.candidate_id != normalized_candidate
        or attestation.claim_fingerprint != normalized_claim
    ):
        raise GovernanceError(
            "observation attestation target/candidate/claim binding mismatch"
        )
    _validate_evidence_policy_for_observation(evidence_policy)
    require_fresh_interval(
        issued_at_step=attestation.observed_at_step,
        expires_at_step=min(
            attestation.expires_at_step,
            principal_verification.expires_at_step,
        ),
        current_step=normalized_current,
        field_name="observation attestation",
    )
    if (
        attestation.expires_at_step - attestation.observed_at_step
        > evidence_policy.observation_ttl_steps
    ):
        raise GovernanceError("observation attestation exceeds the declared TTL")

    normalized_quality = require_scaled_integer(
        quality_ppm,
        "verified observation quality_ppm",
        maximum=WEIGHT_SCALE,
    )
    normalized_relevance = require_scaled_integer(
        relevance_ppm,
        "verified observation relevance_ppm",
        maximum=WEIGHT_SCALE,
    )
    normalized_materiality = require_scaled_integer(
        materiality_ppm,
        "verified observation materiality_ppm",
        maximum=WEIGHT_SCALE,
    )
    normalized_criticality = require_scaled_integer(
        criticality_ppm,
        "verified observation criticality_ppm",
        maximum=WEIGHT_SCALE,
    )
    if normalized_quality < evidence_policy.minimum_quality_ppm:
        raise GovernanceError("verified observation quality is below policy minimum")
    if normalized_relevance < evidence_policy.minimum_relevance_ppm:
        raise GovernanceError("verified observation relevance is below policy minimum")

    if not principal_verification_matches(
        principal_verification,
        profile=normalized_profile,
        assurance=normalized_assurance,
        manifest_root=normalized_manifest_root,
        commit_policy_root=normalized_policy_root,
        protocol_id=normalized_protocol_id,
        run_id=normalized_run_id,
        target=normalized_target,
        epoch=normalized_epoch,
        principal_id=attestation.principal_id,
        current_step=normalized_current,
    ):
        raise GovernanceError(
            "observation principal verification is not authoritative, fresh, and bound"
        )

    attestation_fingerprint = observation_attestation_fingerprint(attestation)
    principal_fingerprint = principal_verification_fingerprint(
        principal_verification
    )
    effective_expiry = min(
        attestation.expires_at_step,
        principal_verification.expires_at_step,
    )
    replayed = _observation_replay_result(
        attestation,
        attestation_fingerprint=attestation_fingerprint,
        prior_observations=prior_observations,
        profile=normalized_profile,
        assurance=normalized_assurance,
        manifest_root=normalized_manifest_root,
        commit_policy_root=normalized_policy_root,
        protocol_id=normalized_protocol_id,
        run_id=normalized_run_id,
        target=normalized_target,
        candidate_id=normalized_candidate,
        claim_fingerprint=normalized_claim,
        epoch=normalized_epoch,
        principal_verification_fingerprint_value=principal_fingerprint,
        principal_cluster_id=principal_verification.cluster_id,
        quality_ppm=normalized_quality,
        relevance_ppm=normalized_relevance,
        materiality_ppm=normalized_materiality,
        criticality_ppm=normalized_criticality,
        effective_expiry=effective_expiry,
        current_step=normalized_current,
    )
    if replayed is not None:
        return replayed

    observation = VerifiedObservation(
        observation_id=attestation.observation_id,
        profile=normalized_profile,
        assurance=normalized_assurance,
        manifest_root=normalized_manifest_root,
        commit_policy_root=normalized_policy_root,
        protocol_id=normalized_protocol_id,
        run_id=normalized_run_id,
        target=normalized_target,
        candidate_id=normalized_candidate,
        claim_fingerprint=normalized_claim,
        epoch=normalized_epoch,
        principal_id=attestation.principal_id,
        principal_cluster_id=principal_verification.cluster_id,
        principal_verification_fingerprint=principal_fingerprint,
        attestation_fingerprint=attestation_fingerprint,
        polarity=attestation.polarity,
        independence_group=attestation.independence_group,
        source_domain=attestation.source_domain,
        payload_fingerprint=attestation.payload_fingerprint,
        quality_ppm=normalized_quality,
        relevance_ppm=normalized_relevance,
        materiality_ppm=normalized_materiality,
        criticality_ppm=normalized_criticality,
        nonce=attestation.nonce,
        observed_at_step=attestation.observed_at_step,
        verified_at_step=normalized_current,
        expires_at_step=effective_expiry,
        attestation_provenance=attestation.provenance,
        attestation_trace_event_id=attestation.trace_event_id,
        verifier_id=require_commit_text(
            verifier_id,
            "verified observation verifier_id",
        ),
        authority=authority,
        verification_provenance=require_commit_text(
            verification_provenance,
            "verified observation verification_provenance",
        ),
        verification_trace_event_id=require_commit_text(
            verification_trace_event_id,
            "verified observation verification_trace_event_id",
        ),
    )
    object.__setattr__(
        observation,
        "_issuance",
        (
            _VERIFIED_OBSERVATION_ISSUANCE,
            _verified_observation_snapshot(observation),
        ),
    )
    return observation


def verified_observation_payload(
    observation: VerifiedObservation,
) -> dict[str, object]:
    if type(observation) is not VerifiedObservation:
        raise GovernanceError("verified observation must use the canonical record")
    _validate_verified_observation_shape(observation)
    return {
        "assurance": observation.assurance,
        "attestation_fingerprint": observation.attestation_fingerprint,
        "attestation_provenance": observation.attestation_provenance,
        "attestation_trace_event_id": observation.attestation_trace_event_id,
        "authority": observation.authority,
        "candidate_id": observation.candidate_id,
        "claim_fingerprint": observation.claim_fingerprint,
        "commit_policy_root": observation.commit_policy_root,
        "criticality_ppm": observation.criticality_ppm,
        "epoch": observation.epoch,
        "expires_at_step": observation.expires_at_step,
        "independence_group": observation.independence_group,
        "manifest_root": observation.manifest_root,
        "materiality_ppm": observation.materiality_ppm,
        "nonce": observation.nonce,
        "observation_id": observation.observation_id,
        "observed_at_step": observation.observed_at_step,
        "payload_fingerprint": observation.payload_fingerprint,
        "polarity": observation.polarity,
        "principal_cluster_id": observation.principal_cluster_id,
        "principal_id": observation.principal_id,
        "principal_verification_fingerprint": (
            observation.principal_verification_fingerprint
        ),
        "profile": observation.profile,
        "protocol_id": observation.protocol_id,
        "quality_ppm": observation.quality_ppm,
        "relevance_ppm": observation.relevance_ppm,
        "run_id": observation.run_id,
        "source_domain": observation.source_domain,
        "target": observation.target,
        "verification_provenance": observation.verification_provenance,
        "verification_trace_event_id": observation.verification_trace_event_id,
        "verified_at_step": observation.verified_at_step,
        "verifier_id": observation.verifier_id,
    }


def verified_observation_fingerprint(observation: VerifiedObservation) -> str:
    return _verified_observation_snapshot(observation)


def verified_observation_is_authoritative(observation: object) -> bool:
    if type(observation) is not VerifiedObservation:
        return False
    try:
        _validate_verified_observation_shape(observation)
        issuance = observation._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _VERIFIED_OBSERVATION_ISSUANCE
            and issuance[1] == _verified_observation_snapshot(observation)
        )
    except Exception:
        return False


def verified_observation_matches(
    observation: VerifiedObservation | None,
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
    polarity: ObservationPolarity | None = None,
    principal_id: str | None = None,
) -> bool:
    try:
        expected_profile = require_commit_profile(profile, "expected profile")
        expected_assurance = require_commit_assurance(
            assurance,
            "expected assurance",
        )
        _require_profile_assurance(expected_profile, expected_assurance)
        expected_manifest = require_commit_fingerprint(
            manifest_root,
            "expected manifest_root",
        )
        expected_policy = require_commit_fingerprint(
            commit_policy_root,
            "expected commit_policy_root",
        )
        expected_protocol = require_commit_text(protocol_id, "expected protocol_id")
        expected_run = require_commit_text(run_id, "expected run_id")
        expected_target = require_commit_text(target, "expected target")
        expected_candidate = require_commit_text(candidate_id, "expected candidate_id")
        expected_claim = require_commit_fingerprint(
            claim_fingerprint,
            "expected claim_fingerprint",
        )
        expected_epoch = require_commit_step(epoch, "expected epoch")
        current = require_commit_step(current_step, "observation current_step")
        if polarity is not None and type(polarity) is not ObservationPolarity:
            return False
        expected_principal = (
            require_commit_text(principal_id, "expected principal_id")
            if principal_id is not None
            else None
        )
        return bool(
            verified_observation_is_authoritative(observation)
            and observation is not None
            and observation.profile == expected_profile
            and observation.assurance is expected_assurance
            and observation.manifest_root == expected_manifest
            and observation.commit_policy_root == expected_policy
            and observation.protocol_id == expected_protocol
            and observation.run_id == expected_run
            and observation.target == expected_target
            and observation.candidate_id == expected_candidate
            and observation.claim_fingerprint == expected_claim
            and observation.epoch == expected_epoch
            and (polarity is None or observation.polarity is polarity)
            and (
                expected_principal is None
                or observation.principal_id == expected_principal
            )
            and observation.observed_at_step <= current < observation.expires_at_step
        )
    except GovernanceError:
        return False


def observation_weight_ppm(observation: VerifiedObservation) -> int:
    if not verified_observation_is_authoritative(observation):
        raise GovernanceError("observation weight requires authoritative evidence")
    return multiply_scaled(observation.quality_ppm, observation.relevance_ppm)


def issue_counterevidence_disposition(
    counter_observation: VerifiedObservation,
    *,
    disposition_id: str,
    kind: CounterevidenceDispositionKind,
    rebuttal_observations: Sequence[VerifiedObservation],
    resolution_ref: str,
    reason_codes: Sequence[str],
    verifier_id: str,
    authority: AuthorityLevel,
    current_step: int,
    provenance: str,
    trace_event_id: str,
) -> CounterevidenceDisposition:
    if type(kind) is not CounterevidenceDispositionKind:
        raise GovernanceError("counterevidence disposition kind is invalid")
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError(
            "counterevidence disposition requires governance authority"
        )
    current = require_commit_step(current_step, "counterevidence current_step")
    if not verified_observation_is_authoritative(counter_observation):
        raise GovernanceError(
            "counterevidence disposition requires an authoritative observation"
        )
    if counter_observation.polarity is not ObservationPolarity.CONTRADICT:
        raise GovernanceError(
            "counterevidence disposition requires contradict polarity"
        )
    if not (
        counter_observation.observed_at_step
        <= current
        < counter_observation.expires_at_step
    ):
        raise GovernanceError("counterevidence observation is not fresh")

    normalized_rebuttals = tuple(rebuttal_observations)
    if kind is CounterevidenceDispositionKind.REBUTTED:
        if not normalized_rebuttals:
            raise GovernanceError(
                "rebutted counterevidence requires independent rebuttal evidence"
            )
        normalized_resolution = require_commit_fingerprint(
            resolution_ref,
            "counterevidence disposition resolution_ref",
        )
    else:
        if normalized_rebuttals:
            raise GovernanceError(
                "only rebutted counterevidence may reference rebuttal evidence"
            )
        if kind is CounterevidenceDispositionKind.UNRESOLVED:
            if resolution_ref:
                raise GovernanceError(
                    "unresolved counterevidence cannot claim a governance resolution"
                )
            normalized_resolution = ""
        else:
            normalized_resolution = require_commit_fingerprint(
                resolution_ref,
                "counterevidence disposition resolution_ref",
            )

    rebuttal_fingerprints: list[str] = []
    rebuttal_principals: set[str] = set()
    rebuttal_clusters: set[str] = set()
    rebuttal_groups: set[str] = set()
    rebuttal_domains: set[str] = set()
    expiry = counter_observation.expires_at_step
    for rebuttal in normalized_rebuttals:
        if not verified_observation_matches(
            rebuttal,
            profile=counter_observation.profile,
            assurance=counter_observation.assurance,
            manifest_root=counter_observation.manifest_root,
            commit_policy_root=counter_observation.commit_policy_root,
            protocol_id=counter_observation.protocol_id,
            run_id=counter_observation.run_id,
            target=counter_observation.target,
            candidate_id=counter_observation.candidate_id,
            claim_fingerprint=counter_observation.claim_fingerprint,
            epoch=counter_observation.epoch,
            current_step=current,
            polarity=ObservationPolarity.SUPPORT,
        ):
            raise GovernanceError(
                "rebuttal observation is not authoritative, fresh, and bound"
            )
        if (
            rebuttal.principal_id == counter_observation.principal_id
            or rebuttal.principal_cluster_id
            == counter_observation.principal_cluster_id
            or
            rebuttal.independence_group == counter_observation.independence_group
            or rebuttal.source_domain == counter_observation.source_domain
        ):
            raise GovernanceError(
                "rebutted counterevidence requires an independent group and source "
                "domain backed by an independent principal cluster"
            )
        if (
            rebuttal.principal_id in rebuttal_principals
            or rebuttal.principal_cluster_id in rebuttal_clusters
            or rebuttal.independence_group in rebuttal_groups
            or rebuttal.source_domain in rebuttal_domains
        ):
            raise GovernanceError(
                "rebuttal evidence must be pairwise independent by principal, cluster, "
                "group, and source domain"
            )
        rebuttal_principals.add(rebuttal.principal_id)
        rebuttal_clusters.add(rebuttal.principal_cluster_id)
        rebuttal_groups.add(rebuttal.independence_group)
        rebuttal_domains.add(rebuttal.source_domain)
        rebuttal_fingerprints.append(verified_observation_fingerprint(rebuttal))
        expiry = min(expiry, rebuttal.expires_at_step)

    disposition = CounterevidenceDisposition(
        disposition_id=require_commit_text(
            disposition_id,
            "counterevidence disposition disposition_id",
        ),
        kind=kind,
        profile=counter_observation.profile,
        assurance=counter_observation.assurance,
        manifest_root=counter_observation.manifest_root,
        commit_policy_root=counter_observation.commit_policy_root,
        protocol_id=counter_observation.protocol_id,
        run_id=counter_observation.run_id,
        target=counter_observation.target,
        candidate_id=counter_observation.candidate_id,
        claim_fingerprint=counter_observation.claim_fingerprint,
        epoch=counter_observation.epoch,
        counter_observation_fingerprint=verified_observation_fingerprint(
            counter_observation
        ),
        rebuttal_observation_fingerprints=tuple(rebuttal_fingerprints),
        resolution_ref=normalized_resolution,
        reason_codes=tuple(reason_codes),
        verifier_id=require_commit_text(
            verifier_id,
            "counterevidence disposition verifier_id",
        ),
        authority=authority,
        issued_at_step=current,
        expires_at_step=expiry,
        provenance=require_commit_text(
            provenance,
            "counterevidence disposition provenance",
        ),
        trace_event_id=require_commit_text(
            trace_event_id,
            "counterevidence disposition trace_event_id",
        ),
    )
    object.__setattr__(
        disposition,
        "_issuance",
        (
            _COUNTEREVIDENCE_DISPOSITION_ISSUANCE,
            _counterevidence_disposition_snapshot(disposition),
        ),
    )
    return disposition


def counterevidence_disposition_payload(
    disposition: CounterevidenceDisposition,
) -> dict[str, object]:
    if type(disposition) is not CounterevidenceDisposition:
        raise GovernanceError(
            "counterevidence disposition must use the canonical record"
        )
    _validate_counterevidence_disposition_shape(disposition)
    return {
        "assurance": disposition.assurance,
        "authority": disposition.authority,
        "candidate_id": disposition.candidate_id,
        "claim_fingerprint": disposition.claim_fingerprint,
        "commit_policy_root": disposition.commit_policy_root,
        "counter_observation_fingerprint": (
            disposition.counter_observation_fingerprint
        ),
        "disposition_id": disposition.disposition_id,
        "epoch": disposition.epoch,
        "expires_at_step": disposition.expires_at_step,
        "issued_at_step": disposition.issued_at_step,
        "kind": disposition.kind,
        "manifest_root": disposition.manifest_root,
        "profile": disposition.profile,
        "protocol_id": disposition.protocol_id,
        "provenance": disposition.provenance,
        "reason_codes": disposition.reason_codes,
        "rebuttal_observation_fingerprints": (
            disposition.rebuttal_observation_fingerprints
        ),
        "resolution_ref": disposition.resolution_ref,
        "run_id": disposition.run_id,
        "target": disposition.target,
        "trace_event_id": disposition.trace_event_id,
        "verifier_id": disposition.verifier_id,
    }


def counterevidence_disposition_fingerprint(
    disposition: CounterevidenceDisposition,
) -> str:
    return _counterevidence_disposition_snapshot(disposition)


def counterevidence_disposition_is_authoritative(disposition: object) -> bool:
    if type(disposition) is not CounterevidenceDisposition:
        return False
    try:
        _validate_counterevidence_disposition_shape(disposition)
        issuance = disposition._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _COUNTEREVIDENCE_DISPOSITION_ISSUANCE
            and issuance[1] == _counterevidence_disposition_snapshot(disposition)
        )
    except Exception:
        return False


def counterevidence_disposition_matches(
    disposition: CounterevidenceDisposition | None,
    counter_observation: VerifiedObservation,
    *,
    current_step: int,
) -> bool:
    try:
        current = require_commit_step(current_step, "counterevidence current_step")
        return bool(
            counterevidence_disposition_is_authoritative(disposition)
            and disposition is not None
            and verified_observation_is_authoritative(counter_observation)
            and disposition.profile == counter_observation.profile
            and disposition.assurance is counter_observation.assurance
            and disposition.manifest_root == counter_observation.manifest_root
            and disposition.commit_policy_root
            == counter_observation.commit_policy_root
            and disposition.protocol_id == counter_observation.protocol_id
            and disposition.run_id == counter_observation.run_id
            and disposition.target == counter_observation.target
            and disposition.candidate_id == counter_observation.candidate_id
            and disposition.claim_fingerprint
            == counter_observation.claim_fingerprint
            and disposition.epoch == counter_observation.epoch
            and disposition.counter_observation_fingerprint
            == verified_observation_fingerprint(counter_observation)
            and disposition.issued_at_step <= current < disposition.expires_at_step
        )
    except GovernanceError:
        return False


def counterevidence_is_material_critical(
    observation: VerifiedObservation,
) -> bool:
    if not verified_observation_is_authoritative(observation):
        raise GovernanceError(
            "material critical evaluation requires authoritative evidence"
        )
    if observation.polarity is not ObservationPolarity.CONTRADICT:
        return False
    return observation.materiality_ppm > 0 and observation.criticality_ppm > 0


def _validate_observation_attestation(attestation: ObservationAttestation) -> None:
    for field_name in (
        "observation_id",
        "target",
        "candidate_id",
        "principal_id",
        "independence_group",
        "source_domain",
        "provenance",
        "nonce",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(attestation, field_name),
            f"observation attestation {field_name}",
        )
    for field_name in ("claim_fingerprint", "payload_fingerprint"):
        require_commit_fingerprint(
            getattr(attestation, field_name),
            f"observation attestation {field_name}",
        )
    if type(attestation.polarity) is not ObservationPolarity:
        raise GovernanceError("observation attestation polarity is invalid")
    for field_name in (
        "reported_quality_ppm",
        "reported_relevance_ppm",
        "reported_materiality_ppm",
        "reported_criticality_ppm",
    ):
        require_scaled_integer(
            getattr(attestation, field_name),
            f"observation attestation {field_name}",
            maximum=WEIGHT_SCALE,
        )
    observed = require_commit_step(
        attestation.observed_at_step,
        "observation attestation observed_at_step",
    )
    expires = require_commit_step(
        attestation.expires_at_step,
        "observation attestation expires_at_step",
    )
    if expires <= observed:
        raise GovernanceError("observation attestation expiry must be after observation")


def _validate_verified_observation_shape(observation: VerifiedObservation) -> None:
    for field_name in (
        "observation_id",
        "protocol_id",
        "run_id",
        "target",
        "candidate_id",
        "principal_id",
        "principal_cluster_id",
        "independence_group",
        "source_domain",
        "nonce",
        "attestation_provenance",
        "attestation_trace_event_id",
        "verifier_id",
        "verification_provenance",
        "verification_trace_event_id",
    ):
        require_commit_text(
            getattr(observation, field_name),
            f"verified observation {field_name}",
        )
    assurance = require_commit_assurance(
        observation.assurance,
        "verified observation assurance",
    )
    require_commit_profile(observation.profile, "verified observation profile")
    _require_profile_assurance(observation.profile, assurance)
    for field_name in (
        "manifest_root",
        "commit_policy_root",
        "claim_fingerprint",
        "principal_verification_fingerprint",
        "attestation_fingerprint",
        "payload_fingerprint",
    ):
        require_commit_fingerprint(
            getattr(observation, field_name),
            f"verified observation {field_name}",
        )
    if type(observation.polarity) is not ObservationPolarity:
        raise GovernanceError("verified observation polarity is invalid")
    for field_name in (
        "quality_ppm",
        "relevance_ppm",
        "materiality_ppm",
        "criticality_ppm",
    ):
        require_scaled_integer(
            getattr(observation, field_name),
            f"verified observation {field_name}",
            maximum=WEIGHT_SCALE,
        )
    require_commit_step(observation.epoch, "verified observation epoch")
    observed = require_commit_step(
        observation.observed_at_step,
        "verified observation observed_at_step",
    )
    verified = require_commit_step(
        observation.verified_at_step,
        "verified observation verified_at_step",
    )
    expires = require_commit_step(
        observation.expires_at_step,
        "verified observation expires_at_step",
    )
    if verified < observed or expires <= verified:
        raise GovernanceError("verified observation interval is invalid")
    if type(observation.authority) is not AuthorityLevel or not can_verify(
        observation.authority
    ):
        raise GovernanceError("verified observation authority is invalid")


def _validate_counterevidence_disposition_shape(
    disposition: CounterevidenceDisposition,
) -> None:
    for field_name in (
        "disposition_id",
        "protocol_id",
        "run_id",
        "target",
        "candidate_id",
        "verifier_id",
        "provenance",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(disposition, field_name),
            f"counterevidence disposition {field_name}",
        )
    assurance = require_commit_assurance(
        disposition.assurance,
        "counterevidence disposition assurance",
    )
    require_commit_profile(
        disposition.profile,
        "counterevidence disposition profile",
    )
    _require_profile_assurance(disposition.profile, assurance)
    for field_name in (
        "manifest_root",
        "commit_policy_root",
        "claim_fingerprint",
        "counter_observation_fingerprint",
    ):
        require_commit_fingerprint(
            getattr(disposition, field_name),
            f"counterevidence disposition {field_name}",
        )
    if type(disposition.kind) is not CounterevidenceDispositionKind:
        raise GovernanceError("counterevidence disposition kind is invalid")
    rebuttals = _canonical_fingerprints(
        disposition.rebuttal_observation_fingerprints,
        "counterevidence disposition rebuttal observation fingerprints",
        allow_empty=True,
    )
    if rebuttals != disposition.rebuttal_observation_fingerprints:
        raise GovernanceError(
            "counterevidence disposition rebuttal fingerprints are not canonical"
        )
    if disposition.kind is CounterevidenceDispositionKind.REBUTTED:
        if not rebuttals or not disposition.resolution_ref:
            raise GovernanceError(
                "rebutted counterevidence requires evidence and governance resolution"
            )
    elif rebuttals:
        raise GovernanceError(
            "only rebutted counterevidence may reference rebuttal evidence"
        )
    if disposition.kind is CounterevidenceDispositionKind.UNRESOLVED:
        if disposition.resolution_ref:
            raise GovernanceError(
                "unresolved counterevidence cannot claim a governance resolution"
            )
    else:
        require_commit_fingerprint(
            disposition.resolution_ref,
            "counterevidence disposition resolution_ref",
        )
    require_commit_labels(
        disposition.reason_codes,
        "counterevidence disposition reason_codes",
    )
    require_commit_step(disposition.epoch, "counterevidence disposition epoch")
    issued = require_commit_step(
        disposition.issued_at_step,
        "counterevidence disposition issued_at_step",
    )
    expires = require_commit_step(
        disposition.expires_at_step,
        "counterevidence disposition expires_at_step",
    )
    if expires <= issued:
        raise GovernanceError("counterevidence disposition expiry must be after issuance")
    if type(disposition.authority) is not AuthorityLevel or not can_verify(
        disposition.authority
    ):
        raise GovernanceError("counterevidence disposition authority is invalid")


def _observation_replay_result(
    attestation: ObservationAttestation,
    *,
    attestation_fingerprint: str,
    prior_observations: Sequence[VerifiedObservation],
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
    principal_verification_fingerprint_value: str,
    principal_cluster_id: str,
    quality_ppm: int,
    relevance_ppm: int,
    materiality_ppm: int,
    criticality_ppm: int,
    effective_expiry: int,
    current_step: int,
) -> VerifiedObservation | None:
    if isinstance(prior_observations, (str, bytes, bytearray)):
        raise GovernanceError("prior observations must be a sequence")
    seen_ids: set[str] = set()
    seen_nonces: set[str] = set()
    seen_attestations: set[str] = set()
    idempotent: VerifiedObservation | None = None
    for prior in prior_observations:
        if not verified_observation_is_authoritative(prior):
            raise GovernanceError(
                "prior observation replay state contains non-authoritative evidence"
            )
        if (
            prior.observation_id in seen_ids
            or prior.nonce in seen_nonces
            or prior.attestation_fingerprint in seen_attestations
        ):
            raise GovernanceError("prior observation replay state contains a duplicate")
        seen_ids.add(prior.observation_id)
        seen_nonces.add(prior.nonce)
        seen_attestations.add(prior.attestation_fingerprint)
        identity_collision = bool(
            prior.observation_id == attestation.observation_id
            or prior.nonce == attestation.nonce
            or prior.attestation_fingerprint == attestation_fingerprint
        )
        if not identity_collision:
            continue
        exact_attestation = bool(
            prior.observation_id == attestation.observation_id
            and prior.nonce == attestation.nonce
            and prior.attestation_fingerprint == attestation_fingerprint
        )
        exact_verification = bool(
            exact_attestation
            and prior.profile == profile
            and prior.assurance is assurance
            and prior.manifest_root == manifest_root
            and prior.commit_policy_root == commit_policy_root
            and prior.protocol_id == protocol_id
            and prior.run_id == run_id
            and prior.target == target
            and prior.candidate_id == candidate_id
            and prior.claim_fingerprint == claim_fingerprint
            and prior.epoch == epoch
            and prior.principal_id == attestation.principal_id
            and prior.principal_cluster_id == principal_cluster_id
            and prior.principal_verification_fingerprint
            == principal_verification_fingerprint_value
            and prior.polarity is attestation.polarity
            and prior.independence_group == attestation.independence_group
            and prior.source_domain == attestation.source_domain
            and prior.payload_fingerprint == attestation.payload_fingerprint
            and prior.quality_ppm == quality_ppm
            and prior.relevance_ppm == relevance_ppm
            and prior.materiality_ppm == materiality_ppm
            and prior.criticality_ppm == criticality_ppm
            and prior.observed_at_step == attestation.observed_at_step
            and prior.expires_at_step == effective_expiry
            and prior.attestation_provenance == attestation.provenance
            and prior.attestation_trace_event_id == attestation.trace_event_id
            and prior.observed_at_step <= current_step < prior.expires_at_step
        )
        if not exact_verification:
            if prior.nonce == attestation.nonce:
                raise GovernanceError(
                    "observation nonce replay conflict is a safety violation"
                )
            if prior.observation_id == attestation.observation_id:
                raise GovernanceError(
                    "observation_id replay conflict is a safety violation"
                )
            raise GovernanceError(
                "observation attestation replay conflict is a safety violation"
            )
        idempotent = prior
    return idempotent


def _validated_policy_integer(value: object, field_name: str) -> int:
    normalized = require_commit_step(value, field_name)
    if normalized <= 0:
        raise GovernanceError(f"{field_name} must be positive")
    return normalized


def _validate_evidence_policy_for_observation(
    policy: EvidenceQualificationPolicy,
) -> None:
    if type(policy) is not EvidenceQualificationPolicy:
        raise GovernanceError(
            "observation verification requires the canonical evidence policy"
        )
    if policy.numeric_scale != WEIGHT_SCALE:
        raise GovernanceError("observation policy numeric scale is unsupported")
    require_scaled_integer(
        policy.minimum_quality_ppm,
        "observation policy minimum_quality_ppm",
        maximum=WEIGHT_SCALE,
    )
    require_scaled_integer(
        policy.minimum_relevance_ppm,
        "observation policy minimum_relevance_ppm",
        maximum=WEIGHT_SCALE,
    )
    _validated_policy_integer(
        policy.observation_ttl_steps,
        "observation policy observation_ttl_steps",
    )
    if policy.require_provenance is not True or policy.require_trace is not True:
        raise GovernanceError(
            "observation policy must require provenance and trace lineage"
        )


def _verified_observation_snapshot(observation: VerifiedObservation) -> str:
    return commit_payload_fingerprint(
        verified_observation_payload(observation),
        schema="pheroos-verified-observation-v1",
        profile=observation.profile,
    )


def _counterevidence_disposition_snapshot(
    disposition: CounterevidenceDisposition,
) -> str:
    return commit_payload_fingerprint(
        counterevidence_disposition_payload(disposition),
        schema="pheroos-counterevidence-disposition-v1",
        profile=disposition.profile,
    )


def _require_profile_assurance(profile: str, assurance: CommitAssurance) -> None:
    if profile not in COMMIT_PROFILES_BY_ASSURANCE[assurance.value]:
        raise GovernanceError("commit profile/assurance mismatch")


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


__all__ = [
    "CounterevidenceDisposition",
    "CounterevidenceDispositionKind",
    "ObservationAttestation",
    "ObservationPolarity",
    "VerifiedObservation",
    "counterevidence_disposition_fingerprint",
    "counterevidence_disposition_is_authoritative",
    "counterevidence_disposition_matches",
    "counterevidence_disposition_payload",
    "counterevidence_is_material_critical",
    "issue_counterevidence_disposition",
    "observation_attestation_fingerprint",
    "observation_attestation_payload",
    "observation_weight_ppm",
    "verified_observation_fingerprint",
    "verified_observation_is_authoritative",
    "verified_observation_matches",
    "verified_observation_payload",
    "verify_observation_attestation",
]
