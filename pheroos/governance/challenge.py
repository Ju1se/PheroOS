from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from pheroos.governance._commit_validation import (
    require_commit_assurance,
    require_commit_fingerprint,
    require_commit_profile,
    require_commit_step,
    require_commit_text,
    require_fresh_interval,
)
from pheroos.governance.authority import AuthorityLevel, can_verify
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.governance.observation import (
    ObservationPolarity,
    VerifiedObservation,
    verified_observation_fingerprint,
    verified_observation_matches,
)
from pheroos.governance.principal import (
    PrincipalVerification,
    principal_verification_fingerprint,
    principal_verification_matches,
)
from pheroos.protocol.commit_models import (
    COMMIT_PROFILES_BY_ASSURANCE,
    CommitAssurance,
)


class ChallengeResult(StrEnum):
    NO_COUNTEREVIDENCE = "no_counterevidence"
    COUNTEREVIDENCE_FOUND = "counterevidence_found"
    INCONCLUSIVE = "inconclusive"


_VERIFIED_CHALLENGE_ISSUANCE = object()


@dataclass(frozen=True)
class ChallengeAttestation:
    challenge_id: str
    target: str
    candidate_id: str
    claim_fingerprint: str
    principal_id: str
    category: str
    execution_method: str
    execution_attestation_ref: str
    execution_fingerprint: str
    result: ChallengeResult
    result_fingerprint: str
    result_observation_fingerprints: tuple[str, ...]
    provenance: str
    nonce: str
    executed_at_step: int
    expires_at_step: int
    trace_event_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "result_observation_fingerprints",
            _canonical_fingerprints(
                self.result_observation_fingerprints,
                "challenge result observation fingerprints",
            ),
        )
        _validate_challenge_attestation(self)


@dataclass(frozen=True)
class VerifiedChallenge:
    challenge_id: str
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
    category: str
    execution_method: str
    execution_attestation_ref: str
    execution_fingerprint: str
    result: ChallengeResult
    result_fingerprint: str
    result_observation_fingerprints: tuple[str, ...]
    nonce: str
    executed_at_step: int
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
        object.__setattr__(
            self,
            "result_observation_fingerprints",
            _canonical_fingerprints(
                self.result_observation_fingerprints,
                "verified challenge result observation fingerprints",
            ),
        )
        _validate_verified_challenge_shape(self)


@dataclass(frozen=True)
class ChallengeCoverage:
    required_categories: tuple[str, ...]
    covered_categories: tuple[str, ...]
    missing_categories: tuple[str, ...]
    challenge_fingerprints: tuple[str, ...]
    complete: bool = field(init=False)

    def __post_init__(self) -> None:
        required = _canonical_labels(
            self.required_categories,
            "challenge coverage required categories",
            allow_empty=True,
        )
        covered = _canonical_labels(
            self.covered_categories,
            "challenge coverage covered categories",
            allow_empty=True,
        )
        missing = _canonical_labels(
            self.missing_categories,
            "challenge coverage missing categories",
            allow_empty=True,
        )
        fingerprints = _canonical_fingerprints(
            self.challenge_fingerprints,
            "challenge coverage fingerprints",
        )
        if not set(covered).issubset(required):
            raise GovernanceError(
                "covered challenge categories must be required categories"
            )
        if set(missing) != set(required) - set(covered):
            raise GovernanceError("challenge coverage missing categories are invalid")
        object.__setattr__(self, "required_categories", required)
        object.__setattr__(self, "covered_categories", covered)
        object.__setattr__(self, "missing_categories", missing)
        object.__setattr__(self, "challenge_fingerprints", fingerprints)
        object.__setattr__(self, "complete", not missing)


def challenge_attestation_payload(
    attestation: ChallengeAttestation,
) -> dict[str, object]:
    if type(attestation) is not ChallengeAttestation:
        raise GovernanceError("challenge attestation must use the canonical record")
    _validate_challenge_attestation(attestation)
    return {
        "candidate_id": attestation.candidate_id,
        "category": attestation.category,
        "challenge_id": attestation.challenge_id,
        "claim_fingerprint": attestation.claim_fingerprint,
        "executed_at_step": attestation.executed_at_step,
        "execution_attestation_ref": attestation.execution_attestation_ref,
        "execution_fingerprint": attestation.execution_fingerprint,
        "execution_method": attestation.execution_method,
        "expires_at_step": attestation.expires_at_step,
        "nonce": attestation.nonce,
        "principal_id": attestation.principal_id,
        "provenance": attestation.provenance,
        "result": attestation.result,
        "result_fingerprint": attestation.result_fingerprint,
        "result_observation_fingerprints": (
            attestation.result_observation_fingerprints
        ),
        "target": attestation.target,
        "trace_event_id": attestation.trace_event_id,
    }


def challenge_attestation_fingerprint(attestation: ChallengeAttestation) -> str:
    return commit_payload_fingerprint(
        challenge_attestation_payload(attestation),
        schema="pheroos-challenge-attestation-v1",
        profile="pheroos-commit-authority-v1",
    )


def verify_challenge_attestation(
    attestation: ChallengeAttestation,
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
    declared_categories: Sequence[str],
    maximum_ttl_steps: int,
    result_observations: Sequence[VerifiedObservation],
    verifier_id: str,
    authority: AuthorityLevel,
    current_step: int,
    verification_provenance: str,
    verification_trace_event_id: str,
    prior_challenges: Sequence[VerifiedChallenge],
) -> VerifiedChallenge:
    if type(attestation) is not ChallengeAttestation:
        raise GovernanceError("challenge attestation must use the canonical record")
    _validate_challenge_attestation(attestation)
    if type(authority) is not AuthorityLevel or not can_verify(authority):
        raise GovernanceError("challenge verification requires governance authority")

    normalized_profile = require_commit_profile(profile, "verified challenge profile")
    normalized_assurance = require_commit_assurance(
        assurance,
        "verified challenge assurance",
    )
    _require_profile_assurance(normalized_profile, normalized_assurance)
    normalized_manifest = require_commit_fingerprint(
        manifest_root,
        "verified challenge manifest_root",
    )
    normalized_policy = require_commit_fingerprint(
        commit_policy_root,
        "verified challenge commit_policy_root",
    )
    normalized_protocol = require_commit_text(
        protocol_id,
        "verified challenge protocol_id",
    )
    normalized_run = require_commit_text(run_id, "verified challenge run_id")
    normalized_target = require_commit_text(target, "verified challenge target")
    normalized_candidate = require_commit_text(
        candidate_id,
        "verified challenge candidate_id",
    )
    normalized_claim = require_commit_fingerprint(
        claim_fingerprint,
        "verified challenge claim_fingerprint",
    )
    normalized_epoch = require_commit_step(epoch, "verified challenge epoch")
    current = require_commit_step(current_step, "verified challenge current_step")
    ttl = require_commit_step(maximum_ttl_steps, "challenge maximum_ttl_steps")
    if ttl <= 0:
        raise GovernanceError("challenge maximum_ttl_steps must be positive")

    declared = _canonical_labels(
        declared_categories,
        "declared challenge categories",
        allow_empty=False,
    )
    if attestation.category not in declared:
        raise GovernanceError("challenge category is not declared by policy")
    if (
        attestation.target != normalized_target
        or attestation.candidate_id != normalized_candidate
        or attestation.claim_fingerprint != normalized_claim
    ):
        raise GovernanceError("challenge target/candidate/claim binding mismatch")
    require_fresh_interval(
        issued_at_step=attestation.executed_at_step,
        expires_at_step=attestation.expires_at_step,
        current_step=current,
        field_name="challenge attestation",
    )
    if attestation.expires_at_step - attestation.executed_at_step > ttl:
        raise GovernanceError("challenge attestation exceeds the declared TTL")
    if not principal_verification_matches(
        principal_verification,
        profile=normalized_profile,
        assurance=normalized_assurance,
        manifest_root=normalized_manifest,
        commit_policy_root=normalized_policy,
        protocol_id=normalized_protocol,
        run_id=normalized_run,
        target=normalized_target,
        epoch=normalized_epoch,
        principal_id=attestation.principal_id,
        current_step=current,
    ):
        raise GovernanceError(
            "challenge principal verification is not authoritative, fresh, and bound"
        )

    actual_result_fingerprints: list[str] = []
    expiry = min(attestation.expires_at_step, principal_verification.expires_at_step)
    for observation in result_observations:
        if not verified_observation_matches(
            observation,
            profile=normalized_profile,
            assurance=normalized_assurance,
            manifest_root=normalized_manifest,
            commit_policy_root=normalized_policy,
            protocol_id=normalized_protocol,
            run_id=normalized_run,
            target=normalized_target,
            candidate_id=normalized_candidate,
            claim_fingerprint=normalized_claim,
            epoch=normalized_epoch,
            current_step=current,
            polarity=ObservationPolarity.CONTRADICT,
        ):
            raise GovernanceError(
                "challenge result observation is not authoritative, fresh, and bound"
            )
        actual_result_fingerprints.append(verified_observation_fingerprint(observation))
        expiry = min(expiry, observation.expires_at_step)
    actual_refs = _canonical_fingerprints(
        actual_result_fingerprints,
        "verified challenge result observation fingerprints",
    )
    if actual_refs != attestation.result_observation_fingerprints:
        raise GovernanceError(
            "challenge result observation records do not match the attestation"
        )
    if any(attestation.nonce == item.nonce for item in result_observations):
        raise GovernanceError("challenge nonce cannot replay an observation nonce")

    attestation_fingerprint = challenge_attestation_fingerprint(attestation)
    challenge = VerifiedChallenge(
        challenge_id=attestation.challenge_id,
        profile=normalized_profile,
        assurance=normalized_assurance,
        manifest_root=normalized_manifest,
        commit_policy_root=normalized_policy,
        protocol_id=normalized_protocol,
        run_id=normalized_run,
        target=normalized_target,
        candidate_id=normalized_candidate,
        claim_fingerprint=normalized_claim,
        epoch=normalized_epoch,
        principal_id=attestation.principal_id,
        principal_cluster_id=principal_verification.cluster_id,
        principal_verification_fingerprint=principal_verification_fingerprint(
            principal_verification
        ),
        attestation_fingerprint=attestation_fingerprint,
        category=attestation.category,
        execution_method=attestation.execution_method,
        execution_attestation_ref=attestation.execution_attestation_ref,
        execution_fingerprint=attestation.execution_fingerprint,
        result=attestation.result,
        result_fingerprint=attestation.result_fingerprint,
        result_observation_fingerprints=actual_refs,
        nonce=attestation.nonce,
        executed_at_step=attestation.executed_at_step,
        verified_at_step=current,
        expires_at_step=expiry,
        attestation_provenance=attestation.provenance,
        attestation_trace_event_id=attestation.trace_event_id,
        verifier_id=require_commit_text(
            verifier_id,
            "verified challenge verifier_id",
        ),
        authority=authority,
        verification_provenance=require_commit_text(
            verification_provenance,
            "verified challenge verification_provenance",
        ),
        verification_trace_event_id=require_commit_text(
            verification_trace_event_id,
            "verified challenge verification_trace_event_id",
        ),
    )
    replayed = _challenge_replay_result(
        challenge,
        prior_challenges=prior_challenges,
        current_step=current,
    )
    if replayed is not None:
        return replayed
    object.__setattr__(
        challenge,
        "_issuance",
        (
            _VERIFIED_CHALLENGE_ISSUANCE,
            _verified_challenge_snapshot(challenge),
        ),
    )
    return challenge


def verified_challenge_payload(challenge: VerifiedChallenge) -> dict[str, object]:
    if type(challenge) is not VerifiedChallenge:
        raise GovernanceError("verified challenge must use the canonical record")
    _validate_verified_challenge_shape(challenge)
    return {
        "assurance": challenge.assurance,
        "attestation_fingerprint": challenge.attestation_fingerprint,
        "attestation_provenance": challenge.attestation_provenance,
        "attestation_trace_event_id": challenge.attestation_trace_event_id,
        "authority": challenge.authority,
        "candidate_id": challenge.candidate_id,
        "category": challenge.category,
        "challenge_id": challenge.challenge_id,
        "claim_fingerprint": challenge.claim_fingerprint,
        "commit_policy_root": challenge.commit_policy_root,
        "epoch": challenge.epoch,
        "executed_at_step": challenge.executed_at_step,
        "execution_attestation_ref": challenge.execution_attestation_ref,
        "execution_fingerprint": challenge.execution_fingerprint,
        "execution_method": challenge.execution_method,
        "expires_at_step": challenge.expires_at_step,
        "manifest_root": challenge.manifest_root,
        "nonce": challenge.nonce,
        "principal_cluster_id": challenge.principal_cluster_id,
        "principal_id": challenge.principal_id,
        "principal_verification_fingerprint": (
            challenge.principal_verification_fingerprint
        ),
        "profile": challenge.profile,
        "protocol_id": challenge.protocol_id,
        "result": challenge.result,
        "result_fingerprint": challenge.result_fingerprint,
        "result_observation_fingerprints": (challenge.result_observation_fingerprints),
        "run_id": challenge.run_id,
        "target": challenge.target,
        "verification_provenance": challenge.verification_provenance,
        "verification_trace_event_id": challenge.verification_trace_event_id,
        "verified_at_step": challenge.verified_at_step,
        "verifier_id": challenge.verifier_id,
    }


def verified_challenge_fingerprint(challenge: VerifiedChallenge) -> str:
    return _verified_challenge_snapshot(challenge)


def verified_challenge_is_authoritative(challenge: object) -> bool:
    if type(challenge) is not VerifiedChallenge:
        return False
    try:
        _validate_verified_challenge_shape(challenge)
        issuance = challenge._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _VERIFIED_CHALLENGE_ISSUANCE
            and issuance[1] == _verified_challenge_snapshot(challenge)
        )
    except Exception:
        return False


def verified_challenge_matches(
    challenge: VerifiedChallenge | None,
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
        current = require_commit_step(current_step, "challenge current_step")
        return bool(
            verified_challenge_is_authoritative(challenge)
            and challenge is not None
            and challenge.profile == expected_profile
            and challenge.assurance is expected_assurance
            and challenge.manifest_root == expected_manifest
            and challenge.commit_policy_root == expected_policy
            and challenge.protocol_id == expected_protocol
            and challenge.run_id == expected_run
            and challenge.target == expected_target
            and challenge.candidate_id == expected_candidate
            and challenge.claim_fingerprint == expected_claim
            and challenge.epoch == expected_epoch
            and challenge.executed_at_step <= current < challenge.expires_at_step
        )
    except GovernanceError:
        return False


def evaluate_challenge_coverage(
    challenges: Sequence[VerifiedChallenge],
    *,
    required_categories: Sequence[str],
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
) -> ChallengeCoverage:
    required = _canonical_labels(
        required_categories,
        "required challenge categories",
        allow_empty=True,
    )
    covered: set[str] = set()
    fingerprints: list[str] = []
    seen_ids: set[str] = set()
    seen_nonces: set[str] = set()
    seen_execution_refs: set[str] = set()
    seen_execution_fingerprints: set[str] = set()
    for challenge in challenges:
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
                "challenge coverage contains non-authoritative, stale, or unbound input"
            )
        if challenge.challenge_id in seen_ids or challenge.nonce in seen_nonces:
            raise GovernanceError("challenge coverage contains a replay")
        if (
            challenge.execution_attestation_ref in seen_execution_refs
            or challenge.execution_fingerprint in seen_execution_fingerprints
        ):
            raise GovernanceError(
                "challenge coverage cannot reuse one execution for multiple claims"
            )
        seen_ids.add(challenge.challenge_id)
        seen_nonces.add(challenge.nonce)
        seen_execution_refs.add(challenge.execution_attestation_ref)
        seen_execution_fingerprints.add(challenge.execution_fingerprint)
        fingerprint = verified_challenge_fingerprint(challenge)
        if fingerprint in fingerprints:
            raise GovernanceError("challenge coverage contains duplicate evidence")
        fingerprints.append(fingerprint)
        if (
            challenge.category in required
            and challenge.result is not ChallengeResult.INCONCLUSIVE
        ):
            covered.add(challenge.category)
    return ChallengeCoverage(
        required_categories=required,
        covered_categories=tuple(covered),
        missing_categories=tuple(set(required) - covered),
        challenge_fingerprints=tuple(fingerprints),
    )


def challenge_coverage_payload(coverage: ChallengeCoverage) -> dict[str, object]:
    if type(coverage) is not ChallengeCoverage:
        raise GovernanceError("challenge coverage must use the canonical record")
    return {
        "challenge_fingerprints": coverage.challenge_fingerprints,
        "complete": coverage.complete,
        "covered_categories": coverage.covered_categories,
        "missing_categories": coverage.missing_categories,
        "required_categories": coverage.required_categories,
    }


def challenge_coverage_fingerprint(
    coverage: ChallengeCoverage,
    *,
    profile: str,
) -> str:
    return commit_payload_fingerprint(
        challenge_coverage_payload(coverage),
        schema="pheroos-challenge-coverage-v1",
        profile=require_commit_profile(profile, "challenge coverage profile"),
    )


def _validate_challenge_attestation(attestation: ChallengeAttestation) -> None:
    for field_name in (
        "challenge_id",
        "target",
        "candidate_id",
        "principal_id",
        "category",
        "execution_method",
        "execution_attestation_ref",
        "provenance",
        "nonce",
        "trace_event_id",
    ):
        require_commit_text(
            getattr(attestation, field_name),
            f"challenge attestation {field_name}",
        )
    for field_name in (
        "claim_fingerprint",
        "execution_fingerprint",
        "result_fingerprint",
    ):
        require_commit_fingerprint(
            getattr(attestation, field_name),
            f"challenge attestation {field_name}",
        )
    if type(attestation.result) is not ChallengeResult:
        raise GovernanceError("challenge attestation result is invalid")
    refs = _canonical_fingerprints(
        attestation.result_observation_fingerprints,
        "challenge result observation fingerprints",
    )
    if refs != attestation.result_observation_fingerprints:
        raise GovernanceError(
            "challenge result observation fingerprints are not canonical"
        )
    if attestation.result is ChallengeResult.COUNTEREVIDENCE_FOUND:
        if not refs:
            raise GovernanceError(
                "counterevidence-found challenge must reference observations"
            )
    elif refs:
        raise GovernanceError(
            "challenge without counterevidence cannot reference observations"
        )
    executed = require_commit_step(
        attestation.executed_at_step,
        "challenge attestation executed_at_step",
    )
    expires = require_commit_step(
        attestation.expires_at_step,
        "challenge attestation expires_at_step",
    )
    if expires <= executed:
        raise GovernanceError("challenge attestation expiry must be after execution")


def _validate_verified_challenge_shape(challenge: VerifiedChallenge) -> None:
    for field_name in (
        "challenge_id",
        "protocol_id",
        "run_id",
        "target",
        "candidate_id",
        "principal_id",
        "principal_cluster_id",
        "category",
        "execution_method",
        "execution_attestation_ref",
        "nonce",
        "attestation_provenance",
        "attestation_trace_event_id",
        "verifier_id",
        "verification_provenance",
        "verification_trace_event_id",
    ):
        require_commit_text(
            getattr(challenge, field_name),
            f"verified challenge {field_name}",
        )
    assurance = require_commit_assurance(
        challenge.assurance,
        "verified challenge assurance",
    )
    require_commit_profile(challenge.profile, "verified challenge profile")
    _require_profile_assurance(challenge.profile, assurance)
    for field_name in (
        "manifest_root",
        "commit_policy_root",
        "claim_fingerprint",
        "principal_verification_fingerprint",
        "attestation_fingerprint",
        "execution_fingerprint",
        "result_fingerprint",
    ):
        require_commit_fingerprint(
            getattr(challenge, field_name),
            f"verified challenge {field_name}",
        )
    if type(challenge.result) is not ChallengeResult:
        raise GovernanceError("verified challenge result is invalid")
    refs = _canonical_fingerprints(
        challenge.result_observation_fingerprints,
        "verified challenge result observation fingerprints",
    )
    if refs != challenge.result_observation_fingerprints:
        raise GovernanceError(
            "verified challenge result fingerprints are not canonical"
        )
    if challenge.result is ChallengeResult.COUNTEREVIDENCE_FOUND:
        if not refs:
            raise GovernanceError(
                "counterevidence-found challenge requires observation evidence"
            )
    elif refs:
        raise GovernanceError(
            "verified challenge without counterevidence cannot reference observations"
        )
    require_commit_step(challenge.epoch, "verified challenge epoch")
    executed = require_commit_step(
        challenge.executed_at_step,
        "verified challenge executed_at_step",
    )
    verified = require_commit_step(
        challenge.verified_at_step,
        "verified challenge verified_at_step",
    )
    expires = require_commit_step(
        challenge.expires_at_step,
        "verified challenge expires_at_step",
    )
    if verified < executed or expires <= verified:
        raise GovernanceError("verified challenge interval is invalid")
    if type(challenge.authority) is not AuthorityLevel or not can_verify(
        challenge.authority
    ):
        raise GovernanceError("verified challenge authority is invalid")


def _challenge_replay_result(
    challenge: VerifiedChallenge,
    *,
    prior_challenges: Sequence[VerifiedChallenge],
    current_step: int,
) -> VerifiedChallenge | None:
    if isinstance(prior_challenges, (str, bytes, bytearray)):
        raise GovernanceError("prior challenges must be a sequence")
    seen_ids: set[str] = set()
    seen_nonces: set[str] = set()
    seen_attestations: set[str] = set()
    seen_execution_refs: set[str] = set()
    seen_execution_fingerprints: set[str] = set()
    idempotent: VerifiedChallenge | None = None
    for prior in prior_challenges:
        if not verified_challenge_is_authoritative(prior):
            raise GovernanceError(
                "prior challenge replay state contains non-authoritative input"
            )
        if (
            prior.challenge_id in seen_ids
            or prior.nonce in seen_nonces
            or prior.attestation_fingerprint in seen_attestations
            or prior.execution_attestation_ref in seen_execution_refs
            or prior.execution_fingerprint in seen_execution_fingerprints
        ):
            raise GovernanceError("prior challenge replay state contains a duplicate")
        seen_ids.add(prior.challenge_id)
        seen_nonces.add(prior.nonce)
        seen_attestations.add(prior.attestation_fingerprint)
        seen_execution_refs.add(prior.execution_attestation_ref)
        seen_execution_fingerprints.add(prior.execution_fingerprint)

        identity_collision = bool(
            prior.challenge_id == challenge.challenge_id
            or prior.nonce == challenge.nonce
            or prior.attestation_fingerprint == challenge.attestation_fingerprint
            or prior.execution_attestation_ref == challenge.execution_attestation_ref
            or prior.execution_fingerprint == challenge.execution_fingerprint
        )
        if not identity_collision:
            continue
        exact_replay = bool(
            prior.challenge_id == challenge.challenge_id
            and prior.nonce == challenge.nonce
            and prior.attestation_fingerprint == challenge.attestation_fingerprint
            and prior.profile == challenge.profile
            and prior.assurance is challenge.assurance
            and prior.manifest_root == challenge.manifest_root
            and prior.commit_policy_root == challenge.commit_policy_root
            and prior.protocol_id == challenge.protocol_id
            and prior.run_id == challenge.run_id
            and prior.target == challenge.target
            and prior.candidate_id == challenge.candidate_id
            and prior.claim_fingerprint == challenge.claim_fingerprint
            and prior.epoch == challenge.epoch
            and prior.principal_id == challenge.principal_id
            and prior.principal_cluster_id == challenge.principal_cluster_id
            and prior.principal_verification_fingerprint
            == challenge.principal_verification_fingerprint
            and prior.category == challenge.category
            and prior.execution_method == challenge.execution_method
            and prior.execution_attestation_ref == challenge.execution_attestation_ref
            and prior.execution_fingerprint == challenge.execution_fingerprint
            and prior.result is challenge.result
            and prior.result_fingerprint == challenge.result_fingerprint
            and prior.result_observation_fingerprints
            == challenge.result_observation_fingerprints
            and prior.executed_at_step == challenge.executed_at_step
            and prior.expires_at_step == challenge.expires_at_step
            and prior.attestation_provenance == challenge.attestation_provenance
            and prior.attestation_trace_event_id == challenge.attestation_trace_event_id
            and prior.verifier_id == challenge.verifier_id
            and prior.authority is challenge.authority
            and prior.verification_provenance == challenge.verification_provenance
            and prior.verification_trace_event_id
            == challenge.verification_trace_event_id
            and prior.executed_at_step <= current_step < prior.expires_at_step
        )
        if not exact_replay:
            if prior.nonce == challenge.nonce:
                raise GovernanceError("challenge nonce replay is a safety violation")
            if (
                prior.execution_attestation_ref == challenge.execution_attestation_ref
                or prior.execution_fingerprint == challenge.execution_fingerprint
            ):
                raise GovernanceError(
                    "challenge execution evidence replay is a safety violation"
                )
            raise GovernanceError("challenge identity replay is a safety violation")
        idempotent = prior
    return idempotent


def _verified_challenge_snapshot(challenge: VerifiedChallenge) -> str:
    return commit_payload_fingerprint(
        verified_challenge_payload(challenge),
        schema="pheroos-verified-challenge-v1",
        profile=challenge.profile,
    )


def _require_profile_assurance(profile: str, assurance: CommitAssurance) -> None:
    if profile not in COMMIT_PROFILES_BY_ASSURANCE[assurance.value]:
        raise GovernanceError("commit profile/assurance mismatch")


def _canonical_labels(
    values: Sequence[str],
    field_name: str,
    *,
    allow_empty: bool,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise GovernanceError(f"{field_name} must be a sequence")
    labels = tuple(require_commit_text(value, field_name) for value in values)
    if not labels and not allow_empty:
        raise GovernanceError(f"{field_name} must not be empty")
    if len(set(labels)) != len(labels):
        raise GovernanceError(f"{field_name} contains a duplicate")
    return tuple(sorted(labels))


def _canonical_fingerprints(
    values: Sequence[str],
    field_name: str,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise GovernanceError(f"{field_name} must be a sequence")
    fingerprints = tuple(
        require_commit_fingerprint(value, field_name) for value in values
    )
    if len(set(fingerprints)) != len(fingerprints):
        raise GovernanceError(f"{field_name} contains a duplicate")
    return tuple(sorted(fingerprints))


__all__ = [
    "ChallengeAttestation",
    "ChallengeCoverage",
    "ChallengeResult",
    "VerifiedChallenge",
    "challenge_attestation_fingerprint",
    "challenge_attestation_payload",
    "challenge_coverage_fingerprint",
    "challenge_coverage_payload",
    "evaluate_challenge_coverage",
    "verified_challenge_fingerprint",
    "verified_challenge_is_authoritative",
    "verified_challenge_matches",
    "verified_challenge_payload",
    "verify_challenge_attestation",
]
