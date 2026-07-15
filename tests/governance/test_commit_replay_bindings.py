from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.challenge import (
    ChallengeAttestation,
    ChallengeResult,
    verified_challenge_is_authoritative,
    verify_challenge_attestation,
)
from pheroos.governance.commit_state import (
    CommitReplayState,
    commit_replay_state_is_current,
    initialize_commit_replay_state,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.observation import (
    CounterevidenceDispositionKind,
    ObservationAttestation,
    ObservationPolarity,
    counterevidence_disposition_is_authoritative,
    issue_counterevidence_disposition,
    verified_observation_fingerprint,
    verified_observation_is_authoritative,
    verify_observation_attestation,
)
from pheroos.governance.principal import (
    PrincipalAttestation,
    verify_principal_attestation,
)
from pheroos.governance.replay import (
    challenge_replay_receipt,
    counterevidence_disposition_replay_receipt,
    evidence_replay_inputs_are_recorded,
    missing_evidence_replay_input_refs,
    observation_replay_receipt,
    record_evidence_replay_inputs,
)
from pheroos.protocol.commit_models import (
    CommitAssurance,
    EvidenceQualificationPolicy,
)


PROFILE = "pheroos-commit-integrity-v1"
ASSURANCE = CommitAssurance.EVIDENCE_BOUND
MANIFEST_ROOT = "sha256:" + ("1" * 64)
POLICY_ROOT = "sha256:" + ("2" * 64)
CLAIM_ROOT = "sha256:" + ("3" * 64)
PAYLOAD_ROOT = "sha256:" + ("4" * 64)
RESULT_ROOT = "sha256:" + ("5" * 64)
RESOLUTION_ROOT = "sha256:" + ("6" * 64)
PROTOCOL_ID = "protocol:replay-bindings"
TARGET = "decision:collective"
CANDIDATE = "candidate:alpha"
EPOCH = 7


def _policy() -> EvidenceQualificationPolicy:
    return EvidenceQualificationPolicy(
        numeric_scale=1_000_000,
        minimum_quality_ppm=100_000,
        minimum_relevance_ppm=100_000,
        positive_group_cap=1_000_000,
        counter_group_cap=1_000_000,
        counter_weight_ppm=1_000_000,
        minimum_positive_evidence=1_000_000,
        maximum_counterevidence=1_000_000,
        maximum_counterevidence_ratio_ppm=500_000,
        domain_contribution_floor=100_000,
        minimum_source_diversity=1,
        required_challenge_categories=["falsification"],
        observation_ttl_steps=30,
        require_provenance=True,
        require_trace=True,
    )


def _principal(
    run_id: str,
    principal_id: str,
    *,
    target: str = TARGET,
    epoch: int = EPOCH,
):
    suffix = hashlib.sha256(
        f"{run_id}:{target}:{epoch}:{principal_id}".encode("utf-8")
    ).hexdigest()[:16]
    attestation = PrincipalAttestation(
        principal_id=principal_id,
        attestation_ref=f"opaque:principal:{suffix}",
        method="identity-verifier-v1",
        issuer_id="issuer:identity",
        issued_at_step=0,
        expires_at_step=30,
        provenance=f"urn:test:principal:{suffix}",
        nonce=f"nonce:principal:{suffix}",
        trace_event_id=f"trace:principal:{suffix}",
    )
    return verify_principal_attestation(
        attestation,
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=POLICY_ROOT,
        protocol_id=PROTOCOL_ID,
        run_id=run_id,
        target=target,
        epoch=epoch,
        cluster_id=f"cluster:{suffix}",
        failure_domain=f"failure:{suffix}",
        verifier_id="governance:identity",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=1,
        provenance="urn:test:principal-verification",
        trace_event_id=f"trace:principal-verified:{suffix}",
    )


def _observation(
    run_id: str,
    observation_id: str,
    *,
    nonce: str,
    principal_id: str,
    target: str = TARGET,
    candidate_id: str = CANDIDATE,
    epoch: int = EPOCH,
    polarity: ObservationPolarity = ObservationPolarity.SUPPORT,
    group: str = "group:one",
    domain: str = "domain:one",
):
    suffix = observation_id.split(":")[-1]
    attestation = ObservationAttestation(
        observation_id=observation_id,
        target=target,
        candidate_id=candidate_id,
        claim_fingerprint=CLAIM_ROOT,
        principal_id=principal_id,
        polarity=polarity,
        independence_group=group,
        source_domain=domain,
        payload_fingerprint=PAYLOAD_ROOT,
        reported_quality_ppm=900_000,
        reported_relevance_ppm=900_000,
        reported_materiality_ppm=(900_000 if polarity is ObservationPolarity.CONTRADICT else 0),
        reported_criticality_ppm=(900_000 if polarity is ObservationPolarity.CONTRADICT else 0),
        provenance=f"urn:test:observation:{suffix}",
        nonce=nonce,
        observed_at_step=1,
        expires_at_step=30,
        trace_event_id=f"trace:observation:{suffix}",
    )
    return verify_observation_attestation(
        attestation,
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=POLICY_ROOT,
        protocol_id=PROTOCOL_ID,
        run_id=run_id,
        target=target,
        candidate_id=candidate_id,
        claim_fingerprint=CLAIM_ROOT,
        epoch=epoch,
        principal_verification=_principal(
            run_id,
            principal_id,
            target=target,
            epoch=epoch,
        ),
        evidence_policy=_policy(),
        quality_ppm=900_000,
        relevance_ppm=900_000,
        materiality_ppm=attestation.reported_materiality_ppm,
        criticality_ppm=attestation.reported_criticality_ppm,
        verifier_id="governance:evidence",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=2,
        verification_provenance="urn:test:observation-verification",
        verification_trace_event_id=f"trace:verified:{suffix}",
        # Deliberately empty: local verification alone cannot prove global replay.
        prior_observations=(),
    )


def _challenge(
    run_id: str,
    challenge_id: str,
    *,
    nonce: str,
    principal_id: str,
):
    suffix = challenge_id.split(":")[-1]
    execution_fingerprint = "sha256:" + hashlib.sha256(
        f"execution:{run_id}:{challenge_id}".encode("utf-8")
    ).hexdigest()
    attestation = ChallengeAttestation(
        challenge_id=challenge_id,
        target=TARGET,
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        principal_id=principal_id,
        category="falsification",
        execution_method="declared-counter-search-v1",
        execution_attestation_ref=f"opaque:execution:{suffix}",
        execution_fingerprint=execution_fingerprint,
        result=ChallengeResult.NO_COUNTEREVIDENCE,
        result_fingerprint=RESULT_ROOT,
        result_observation_fingerprints=(),
        provenance=f"urn:test:challenge:{suffix}",
        nonce=nonce,
        executed_at_step=2,
        expires_at_step=30,
        trace_event_id=f"trace:challenge:{suffix}",
    )
    return verify_challenge_attestation(
        attestation,
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=POLICY_ROOT,
        protocol_id=PROTOCOL_ID,
        run_id=run_id,
        target=TARGET,
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        epoch=EPOCH,
        principal_verification=_principal(run_id, principal_id),
        declared_categories=("falsification",),
        maximum_ttl_steps=30,
        result_observations=(),
        verifier_id="governance:challenge",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=3,
        verification_provenance="urn:test:challenge-verification",
        verification_trace_event_id=f"trace:challenge-verified:{suffix}",
        # Deliberately empty for the same global-replay adversarial case.
        prior_challenges=(),
    )


def _replay_state(run_id: str) -> CommitReplayState:
    return initialize_commit_replay_state(
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=POLICY_ROOT,
        protocol_id=PROTOCOL_ID,
        run_id=run_id,
        current_step=0,
        issuer_id="governance:replay",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:replay",
        trace_event_id=f"trace:replay:{run_id}",
    )


def _record(
    state: CommitReplayState,
    *,
    observations=(),
    challenges=(),
    dispositions=(),
    current_step: int = 4,
) -> CommitReplayState:
    return record_evidence_replay_inputs(
        state,
        observations=observations,
        challenges=challenges,
        dispositions=dispositions,
        current_step=current_step,
    )


def test_local_empty_prior_observation_forks_are_stopped_by_central_head() -> None:
    run_id = "run:replay:observation-fork"
    nonce = "nonce:shared-observation"
    first_observation = _observation(
        run_id,
        "observation:first",
        nonce=nonce,
        principal_id="principal:first",
    )
    forked_observation = _observation(
        run_id,
        "observation:fork",
        nonce=nonce,
        principal_id="principal:fork",
    )
    assert verified_observation_is_authoritative(first_observation)
    assert verified_observation_is_authoritative(forked_observation)

    first_head = _record(
        _replay_state(run_id),
        observations=(first_observation,),
    )
    with pytest.raises(GovernanceError, match="safety violation"):
        _record(first_head, observations=(forked_observation,))

    assert commit_replay_state_is_current(first_head)
    assert first_head.receipts == (observation_replay_receipt(first_observation),)


def test_disposition_id_nonce_blocks_unresolved_rebutted_fork() -> None:
    run_id = "run:replay:disposition-fork"
    counter = _observation(
        run_id,
        "observation:counter",
        nonce="nonce:counter",
        principal_id="principal:counter",
        polarity=ObservationPolarity.CONTRADICT,
        group="group:counter",
        domain="domain:counter",
    )
    rebuttal = _observation(
        run_id,
        "observation:rebuttal",
        nonce="nonce:rebuttal",
        principal_id="principal:rebuttal",
        group="group:rebuttal",
        domain="domain:rebuttal",
    )
    unresolved = issue_counterevidence_disposition(
        counter,
        disposition_id="disposition:fork",
        kind=CounterevidenceDispositionKind.UNRESOLVED,
        rebuttal_observations=(),
        resolution_ref="",
        reason_codes=("awaiting_resolution",),
        verifier_id="governance:counterevidence",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=4,
        provenance="urn:test:disposition:unresolved",
        trace_event_id="trace:disposition:unresolved",
    )
    rebutted = issue_counterevidence_disposition(
        counter,
        disposition_id="disposition:fork",
        kind=CounterevidenceDispositionKind.REBUTTED,
        rebuttal_observations=(rebuttal,),
        resolution_ref=RESOLUTION_ROOT,
        reason_codes=("independent_rebuttal",),
        verifier_id="governance:counterevidence",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=4,
        provenance="urn:test:disposition:rebutted",
        trace_event_id="trace:disposition:rebutted",
    )
    assert counterevidence_disposition_is_authoritative(unresolved)
    assert counterevidence_disposition_is_authoritative(rebutted)
    assert (
        counterevidence_disposition_replay_receipt(unresolved).nonce
        == counterevidence_disposition_replay_receipt(rebutted).nonce
    )

    first_head = _record(_replay_state(run_id), dispositions=(unresolved,))
    with pytest.raises(GovernanceError, match="safety violation"):
        _record(first_head, dispositions=(rebutted,))
    assert commit_replay_state_is_current(first_head)


def test_challenge_exact_replay_is_idempotent_and_queryable() -> None:
    run_id = "run:replay:challenge-idempotent"
    challenge = _challenge(
        run_id,
        "challenge:one",
        nonce="nonce:challenge:one",
        principal_id="principal:challenge",
    )
    assert verified_challenge_is_authoritative(challenge)
    initial = _replay_state(run_id)
    missing = missing_evidence_replay_input_refs(
        initial,
        observations=(),
        challenges=(challenge,),
        dispositions=(),
        current_step=4,
    )
    assert missing == (challenge_replay_receipt(challenge).payload_fingerprint,)

    first_head = _record(initial, challenges=(challenge,))
    repeated_head = _record(first_head, challenges=(challenge,))
    assert repeated_head is first_head
    assert evidence_replay_inputs_are_recorded(
        repeated_head,
        observations=(),
        challenges=(challenge,),
        dispositions=(),
        current_step=4,
    )


def test_forged_tampered_or_stale_authority_is_rejected() -> None:
    run_id = "run:replay:forgery"
    observation = _observation(
        run_id,
        "observation:authentic",
        nonce="nonce:authentic",
        principal_id="principal:authentic",
    )
    forged = replace(observation, source_domain="domain:forged")
    assert not verified_observation_is_authoritative(forged)
    with pytest.raises(GovernanceError, match="authoritative, tamper-evident"):
        observation_replay_receipt(forged)

    first_head = _record(_replay_state(run_id), observations=(observation,))
    with pytest.raises(GovernanceError, match="current authoritative head"):
        _record(replace(first_head), observations=(observation,))


def test_permutation_and_exact_duplicates_produce_one_canonical_root() -> None:
    run_id = "run:replay:permutation"
    first = _observation(
        run_id,
        "observation:a",
        nonce="nonce:observation:a",
        principal_id="principal:a",
    )
    second = _observation(
        run_id,
        "observation:b",
        nonce="nonce:observation:b",
        principal_id="principal:b",
    )
    challenge = _challenge(
        run_id,
        "challenge:a",
        nonce="nonce:challenge:a",
        principal_id="principal:challenge:a",
    )
    first_head = _record(
        _replay_state(run_id),
        observations=(second, first, first),
        challenges=(challenge,),
    )
    canonical_root = first_head.receipt_root
    permuted_head = _record(
        first_head,
        observations=(first, second),
        challenges=(challenge,),
    )
    assert permuted_head is first_head
    assert permuted_head.receipt_root == canonical_root
    assert len(first_head.receipts) == 3
    assert not missing_evidence_replay_input_refs(
        first_head,
        observations=(second, first),
        challenges=(challenge,),
        dispositions=(),
        current_step=4,
    )


@pytest.mark.parametrize(
    ("second_target", "second_candidate", "second_epoch"),
    (
        ("decision:other", CANDIDATE, EPOCH),
        (TARGET, "candidate:other", EPOCH),
        (TARGET, CANDIDATE, EPOCH + 1),
    ),
)
def test_nonce_collision_cannot_cross_target_candidate_or_epoch(
    second_target: str,
    second_candidate: str,
    second_epoch: int,
) -> None:
    run_id = f"run:replay:scope:{second_target}:{second_candidate}:{second_epoch}"
    nonce = "nonce:scope-fork"
    first = _observation(
        run_id,
        "observation:scope:first",
        nonce=nonce,
        principal_id="principal:scope:first",
    )
    second = _observation(
        run_id,
        "observation:scope:second",
        nonce=nonce,
        principal_id="principal:scope:second",
        target=second_target,
        candidate_id=second_candidate,
        epoch=second_epoch,
    )
    first_head = _record(_replay_state(run_id), observations=(first,))
    with pytest.raises(GovernanceError, match="safety violation"):
        _record(first_head, observations=(second,))


def test_nonce_collision_cannot_cross_replay_namespace() -> None:
    run_id = "run:replay:namespace-fork"
    nonce = "nonce:cross-namespace"
    observation = _observation(
        run_id,
        "observation:namespace",
        nonce=nonce,
        principal_id="principal:observation",
    )
    challenge = _challenge(
        run_id,
        "challenge:namespace",
        nonce=nonce,
        principal_id="principal:challenge",
    )
    first_head = _record(_replay_state(run_id), observations=(observation,))
    with pytest.raises(GovernanceError, match="safety violation"):
        _record(first_head, challenges=(challenge,))
    with pytest.raises(GovernanceError, match="safety violation"):
        missing_evidence_replay_input_refs(
            first_head,
            observations=(observation,),
            challenges=(challenge,),
            dispositions=(),
            current_step=4,
        )
