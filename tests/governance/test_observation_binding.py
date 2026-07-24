from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.challenge import (
    ChallengeAttestation,
    ChallengeResult,
    evaluate_challenge_coverage,
    verified_challenge_is_authoritative,
    verify_challenge_attestation,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.evidence_binding import (
    bind_evidence,
    evidence_binding_fingerprint,
    evidence_binding_is_authoritative,
    evaluate_evidence_binding,
    rebuild_evidence_binding_roots,
)
from pheroos.governance.observation import (
    CounterevidenceDispositionKind,
    ObservationAttestation,
    ObservationPolarity,
    counterevidence_disposition_is_authoritative,
    issue_counterevidence_disposition,
    observation_attestation_fingerprint,
    verified_observation_fingerprint,
    verified_observation_is_authoritative,
    verified_observation_matches,
    verify_observation_attestation,
)
from pheroos.governance.principal import (
    PrincipalAttestation,
    verify_principal_attestation,
)
from pheroos.protocol import CommitAssurance, EvidenceQualificationPolicy


MANIFEST_ROOT = "sha256:" + ("1" * 64)
COMMIT_POLICY_ROOT = "sha256:" + ("2" * 64)
CLAIM_ROOT = "sha256:" + ("3" * 64)
PAYLOAD_ROOT = "sha256:" + ("4" * 64)
EXECUTION_ROOT = "sha256:" + ("5" * 64)
RESULT_ROOT = "sha256:" + ("6" * 64)
RESOLUTION_ROOT = "sha256:" + ("7" * 64)
PROFILE = "pheroos-commit-integrity-v1"
ASSURANCE = CommitAssurance.EVIDENCE_BOUND
PROTOCOL_ID = "protocol:optimal"
RUN_ID = "run:1"
TARGET = "decision:collective"
CANDIDATE = "candidate:alpha"
EPOCH = 3


def evidence_policy(**overrides: object) -> EvidenceQualificationPolicy:
    values: dict[str, object] = {
        "numeric_scale": 1_000_000,
        "minimum_quality_ppm": 100_000,
        "minimum_relevance_ppm": 100_000,
        "positive_group_cap": 1_000_000,
        "counter_group_cap": 1_000_000,
        "counter_weight_ppm": 1_000_000,
        "minimum_positive_evidence": 2_000_000,
        "maximum_counterevidence": 1_000_000,
        "maximum_counterevidence_ratio_ppm": 400_000,
        "domain_contribution_floor": 250_000,
        "minimum_source_diversity": 2,
        "required_challenge_categories": ["edge_case", "falsification"],
        "observation_ttl_steps": 20,
        "require_provenance": True,
        "require_trace": True,
    }
    values.update(overrides)
    return EvidenceQualificationPolicy(**values)  # type: ignore[arg-type]


def principal_verification(
    principal_id: str,
    *,
    cluster_id: str | None = None,
):
    suffix = principal_id.split(":")[-1]
    attestation = PrincipalAttestation(
        principal_id=principal_id,
        attestation_ref=f"opaque:principal:{suffix}",
        method="identity-verifier-v1",
        issuer_id="issuer:identity",
        issued_at_step=0,
        expires_at_step=100,
        provenance=f"urn:test:principal:{suffix}",
        nonce=f"nonce:principal:{suffix}",
        trace_event_id=f"trace:principal:{suffix}",
    )
    return verify_principal_attestation(
        attestation,
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=TARGET,
        epoch=EPOCH,
        cluster_id=cluster_id or f"cluster:{suffix}",
        failure_domain=f"failure:{suffix}",
        verifier_id="governance:identity",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=1,
        provenance="urn:test:principal-verification",
        trace_event_id=f"trace:principal-verified:{suffix}",
    )


def observation_attestation(
    observation_id: str,
    *,
    principal_id: str,
    polarity: ObservationPolarity = ObservationPolarity.SUPPORT,
    group: str = "group:one",
    domain: str = "domain:one",
    nonce: str | None = None,
    quality_ppm: int = 1_000_000,
    relevance_ppm: int = 1_000_000,
    materiality_ppm: int = 0,
    criticality_ppm: int = 0,
    target: str = TARGET,
    candidate_id: str = CANDIDATE,
    expires_at_step: int = 20,
) -> ObservationAttestation:
    suffix = observation_id.split(":")[-1]
    return ObservationAttestation(
        observation_id=observation_id,
        target=target,
        candidate_id=candidate_id,
        claim_fingerprint=CLAIM_ROOT,
        principal_id=principal_id,
        polarity=polarity,
        independence_group=group,
        source_domain=domain,
        payload_fingerprint=PAYLOAD_ROOT,
        reported_quality_ppm=quality_ppm,
        reported_relevance_ppm=relevance_ppm,
        reported_materiality_ppm=materiality_ppm,
        reported_criticality_ppm=criticality_ppm,
        provenance=f"urn:test:observation:{suffix}",
        nonce=nonce or f"nonce:observation:{suffix}",
        observed_at_step=1,
        expires_at_step=expires_at_step,
        trace_event_id=f"trace:observation:{suffix}",
    )


def verify_observation(
    attestation: ObservationAttestation,
    *,
    principal=None,
    prior=(),
    policy: EvidenceQualificationPolicy | None = None,
    quality_ppm: int | None = None,
    relevance_ppm: int | None = None,
    materiality_ppm: int | None = None,
    criticality_ppm: int | None = None,
    current_step: int = 2,
):
    principal = principal or principal_verification(attestation.principal_id)
    return verify_observation_attestation(
        attestation,
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=TARGET,
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        epoch=EPOCH,
        principal_verification=principal,
        evidence_policy=policy or evidence_policy(),
        quality_ppm=(
            attestation.reported_quality_ppm if quality_ppm is None else quality_ppm
        ),
        relevance_ppm=(
            attestation.reported_relevance_ppm
            if relevance_ppm is None
            else relevance_ppm
        ),
        materiality_ppm=(
            attestation.reported_materiality_ppm
            if materiality_ppm is None
            else materiality_ppm
        ),
        criticality_ppm=(
            attestation.reported_criticality_ppm
            if criticality_ppm is None
            else criticality_ppm
        ),
        verifier_id="governance:evidence",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=current_step,
        verification_provenance="urn:test:observation-verification",
        verification_trace_event_id=f"trace:verified:{attestation.observation_id}",
        prior_observations=prior,
    )


def challenge_attestation(
    challenge_id: str,
    *,
    principal_id: str,
    category: str,
    result: ChallengeResult = ChallengeResult.NO_COUNTEREVIDENCE,
    result_observation_fingerprints=(),
    nonce: str | None = None,
    execution_attestation_ref: str | None = None,
    execution_fingerprint: str | None = None,
    expires_at_step: int = 20,
) -> ChallengeAttestation:
    suffix = challenge_id.split(":")[-1]
    return ChallengeAttestation(
        challenge_id=challenge_id,
        target=TARGET,
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        principal_id=principal_id,
        category=category,
        execution_method="declared-counter-search-v1",
        execution_attestation_ref=(
            execution_attestation_ref or f"opaque:execution:{suffix}"
        ),
        execution_fingerprint=(
            execution_fingerprint
            or "sha256:"
            + hashlib.sha256(
                f"execution:{challenge_id}:{category}".encode("utf-8")
            ).hexdigest()
        ),
        result=result,
        result_fingerprint=RESULT_ROOT,
        result_observation_fingerprints=tuple(result_observation_fingerprints),
        provenance=f"urn:test:challenge:{suffix}",
        nonce=nonce or f"nonce:challenge:{suffix}",
        executed_at_step=2,
        expires_at_step=expires_at_step,
        trace_event_id=f"trace:challenge:{suffix}",
    )


def verify_challenge(
    attestation: ChallengeAttestation,
    *,
    result_observations=(),
    prior=(),
    maximum_ttl_steps: int = 20,
):
    return verify_challenge_attestation(
        attestation,
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=TARGET,
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        epoch=EPOCH,
        principal_verification=principal_verification(attestation.principal_id),
        declared_categories=("falsification", "edge_case"),
        maximum_ttl_steps=maximum_ttl_steps,
        result_observations=result_observations,
        verifier_id="governance:challenge",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=3,
        verification_provenance="urn:test:challenge-verification",
        verification_trace_event_id=f"trace:verified:{attestation.challenge_id}",
        prior_challenges=prior,
    )


def unresolved(counter):
    return issue_counterevidence_disposition(
        counter,
        disposition_id=f"disposition:{counter.observation_id}",
        kind=CounterevidenceDispositionKind.UNRESOLVED,
        rebuttal_observations=(),
        resolution_ref="",
        reason_codes=("awaiting_resolution",),
        verifier_id="governance:counterevidence",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=3,
        provenance="urn:test:counterevidence",
        trace_event_id=f"trace:disposition:{counter.observation_id}",
    )


def bind(
    positive,
    counters=(),
    dispositions=(),
    challenges=(),
    *,
    evidence_id: str = "evidence:alpha",
):
    return bind_evidence(
        evidence_id=evidence_id,
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=TARGET,
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        epoch=EPOCH,
        positive_observations=positive,
        counter_observations=counters,
        dispositions=dispositions,
        challenges=challenges,
        issuer_id="governance:evidence-binding",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=4,
        provenance="urn:test:evidence-binding",
        trace_event_id="trace:evidence-bound",
    )


def complete_challenges():
    return (
        verify_challenge(
            challenge_attestation(
                "challenge:falsification",
                principal_id="principal:challenge-a",
                category="falsification",
            )
        ),
        verify_challenge(
            challenge_attestation(
                "challenge:edge",
                principal_id="principal:challenge-b",
                category="edge_case",
            )
        ),
    )


def test_observation_proposal_is_governance_verified_and_tamper_evident() -> None:
    attestation = observation_attestation(
        "observation:one",
        principal_id="principal:one",
        quality_ppm=900_000,
    )
    observation = verify_observation(attestation, quality_ppm=800_000)

    assert observation.quality_ppm == 800_000
    assert observation.attestation_fingerprint == observation_attestation_fingerprint(
        attestation
    )
    assert verified_observation_is_authoritative(observation)
    assert verified_observation_is_authoritative(replace(observation)) is False

    object.__setattr__(observation, "source_domain", "domain:tampered")
    assert verified_observation_is_authoritative(observation) is False


def test_observation_verification_rejects_wrong_binding_ttl_authority_and_replay() -> (
    None
):
    first = verify_observation(
        observation_attestation("observation:first", principal_id="principal:first")
    )
    replay = observation_attestation(
        "observation:second",
        principal_id="principal:second",
        nonce=first.nonce,
    )
    with pytest.raises(GovernanceError, match="nonce replay"):
        verify_observation(replay, prior=(first,))

    with pytest.raises(GovernanceError, match="binding mismatch"):
        verify_observation(
            observation_attestation(
                "observation:wrong-target",
                principal_id="principal:wrong-target",
                target="decision:other",
            )
        )
    with pytest.raises(GovernanceError, match="declared TTL"):
        verify_observation(
            observation_attestation(
                "observation:long",
                principal_id="principal:long",
                expires_at_step=30,
            )
        )
    with pytest.raises(GovernanceError, match="below policy minimum"):
        verify_observation(
            observation_attestation(
                "observation:weak",
                principal_id="principal:weak",
            ),
            quality_ppm=99_999,
        )

    attestation = observation_attestation(
        "observation:no-authority",
        principal_id="principal:no-authority",
    )
    with pytest.raises(GovernanceError, match="governance authority"):
        verify_observation_attestation(
            attestation,
            profile=PROFILE,
            assurance=ASSURANCE,
            manifest_root=MANIFEST_ROOT,
            commit_policy_root=COMMIT_POLICY_ROOT,
            protocol_id=PROTOCOL_ID,
            run_id=RUN_ID,
            target=TARGET,
            candidate_id=CANDIDATE,
            claim_fingerprint=CLAIM_ROOT,
            epoch=EPOCH,
            principal_verification=principal_verification(attestation.principal_id),
            evidence_policy=evidence_policy(),
            quality_ppm=1_000_000,
            relevance_ppm=1_000_000,
            materiality_ppm=0,
            criticality_ppm=0,
            verifier_id="agent:not-authority",
            authority=AuthorityLevel.AGENT,
            current_step=2,
            verification_provenance="urn:test:invalid",
            verification_trace_event_id="trace:invalid",
            prior_observations=(),
        )


def test_identical_observation_replay_is_idempotent_but_verified_value_conflict_fails() -> (
    None
):
    attestation = observation_attestation(
        "observation:idempotent",
        principal_id="principal:idempotent",
        quality_ppm=900_000,
    )
    principal = principal_verification("principal:idempotent")
    first = verify_observation(
        attestation,
        principal=principal,
        quality_ppm=800_000,
    )
    replayed = verify_observation(
        attestation,
        principal=principal,
        prior=(first,),
        quality_ppm=800_000,
    )

    assert replayed is first
    with pytest.raises(GovernanceError, match="safety violation"):
        verify_observation(
            attestation,
            principal=principal,
            prior=(first,),
            quality_ppm=700_000,
        )


def test_observation_freshness_is_capped_by_principal_verification_expiry() -> None:
    principal_attestation_record = PrincipalAttestation(
        principal_id="principal:short-lived",
        attestation_ref="opaque:principal:short-lived",
        method="identity-verifier-v1",
        issuer_id="issuer:identity",
        issued_at_step=0,
        expires_at_step=3,
        provenance="urn:test:principal:short-lived",
        nonce="nonce:principal:short-lived",
        trace_event_id="trace:principal:short-lived",
    )
    principal = verify_principal_attestation(
        principal_attestation_record,
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=TARGET,
        epoch=EPOCH,
        cluster_id="cluster:short-lived",
        failure_domain="failure:short-lived",
        verifier_id="governance:identity",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=1,
        provenance="urn:test:principal-verification",
        trace_event_id="trace:principal-verified:short-lived",
    )
    observation = verify_observation(
        observation_attestation(
            "observation:short-lived",
            principal_id="principal:short-lived",
            expires_at_step=20,
        ),
        principal=principal,
        current_step=2,
    )

    assert observation.expires_at_step == 3
    assert not verified_observation_matches(
        observation,
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=TARGET,
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        epoch=EPOCH,
        current_step=3,
    )


def test_rebutted_counterevidence_requires_independent_evidence_and_resolution() -> (
    None
):
    counter = verify_observation(
        observation_attestation(
            "observation:counter",
            principal_id="principal:counter",
            polarity=ObservationPolarity.CONTRADICT,
            group="group:shared",
            domain="domain:shared",
            materiality_ppm=1_000_000,
            criticality_ppm=1_000_000,
        )
    )
    same_source = verify_observation(
        observation_attestation(
            "observation:same-source",
            principal_id="principal:same-source",
            group="group:shared",
            domain="domain:shared",
        )
    )
    independent = verify_observation(
        observation_attestation(
            "observation:independent",
            principal_id="principal:independent",
            group="group:independent",
            domain="domain:independent",
        )
    )

    common = {
        "disposition_id": "disposition:counter",
        "kind": CounterevidenceDispositionKind.REBUTTED,
        "reason_codes": ("independent_rebuttal_verified",),
        "verifier_id": "governance:counterevidence",
        "authority": AuthorityLevel.GOVERNANCE,
        "current_step": 3,
        "provenance": "urn:test:counterevidence",
        "trace_event_id": "trace:counterevidence",
    }
    with pytest.raises(GovernanceError, match="independent group and source"):
        issue_counterevidence_disposition(
            counter,
            rebuttal_observations=(same_source,),
            resolution_ref=RESOLUTION_ROOT,
            **common,
        )
    with pytest.raises(GovernanceError, match="resolution_ref"):
        issue_counterevidence_disposition(
            counter,
            rebuttal_observations=(independent,),
            resolution_ref="",
            **common,
        )

    disposition = issue_counterevidence_disposition(
        counter,
        rebuttal_observations=(independent,),
        resolution_ref=RESOLUTION_ROOT,
        **common,
    )
    assert counterevidence_disposition_is_authoritative(disposition)
    assert counterevidence_disposition_is_authoritative(replace(disposition)) is False


def test_fake_rebuttal_cannot_relabel_the_same_principal_cluster_as_independent() -> (
    None
):
    principal = principal_verification(
        "principal:self-rebuttal",
        cluster_id="cluster:self-rebuttal",
    )
    counter = verify_observation(
        observation_attestation(
            "observation:self-counter",
            principal_id="principal:self-rebuttal",
            polarity=ObservationPolarity.CONTRADICT,
            group="group:counter",
            domain="domain:counter",
            materiality_ppm=1_000_000,
            criticality_ppm=1_000_000,
        ),
        principal=principal,
    )
    relabelled_rebuttal = verify_observation(
        observation_attestation(
            "observation:self-rebuttal",
            principal_id="principal:self-rebuttal",
            group="group:claimed-independent",
            domain="domain:claimed-independent",
        ),
        principal=principal,
    )

    with pytest.raises(GovernanceError, match="independent principal cluster"):
        issue_counterevidence_disposition(
            counter,
            disposition_id="disposition:self-rebuttal",
            kind=CounterevidenceDispositionKind.REBUTTED,
            rebuttal_observations=(relabelled_rebuttal,),
            resolution_ref=RESOLUTION_ROOT,
            reason_codes=("claimed_independent_rebuttal",),
            verifier_id="governance:counterevidence",
            authority=AuthorityLevel.GOVERNANCE,
            current_step=3,
            provenance="urn:test:self-rebuttal",
            trace_event_id="trace:self-rebuttal",
        )


def test_multiple_rebuttals_must_be_pairwise_cluster_independent() -> None:
    counter = verify_observation(
        observation_attestation(
            "observation:multi-counter",
            principal_id="principal:multi-counter",
            polarity=ObservationPolarity.CONTRADICT,
            group="group:counter",
            domain="domain:counter",
        )
    )
    shared_cluster = "cluster:shared-rebuttal"
    first = verify_observation(
        observation_attestation(
            "observation:rebuttal-one",
            principal_id="principal:rebuttal-one",
            group="group:rebuttal-one",
            domain="domain:rebuttal-one",
        ),
        principal=principal_verification(
            "principal:rebuttal-one",
            cluster_id=shared_cluster,
        ),
    )
    second = verify_observation(
        observation_attestation(
            "observation:rebuttal-two",
            principal_id="principal:rebuttal-two",
            group="group:rebuttal-two",
            domain="domain:rebuttal-two",
        ),
        principal=principal_verification(
            "principal:rebuttal-two",
            cluster_id=shared_cluster,
        ),
    )

    with pytest.raises(GovernanceError, match="pairwise independent"):
        issue_counterevidence_disposition(
            counter,
            disposition_id="disposition:multi-rebuttal",
            kind=CounterevidenceDispositionKind.REBUTTED,
            rebuttal_observations=(first, second),
            resolution_ref=RESOLUTION_ROOT,
            reason_codes=("multiple_rebuttals",),
            verifier_id="governance:counterevidence",
            authority=AuthorityLevel.GOVERNANCE,
            current_step=3,
            provenance="urn:test:multi-rebuttal",
            trace_event_id="trace:multi-rebuttal",
        )


def test_challenge_requires_declared_executed_category_and_actual_result_evidence() -> (
    None
):
    with pytest.raises(GovernanceError, match="not declared"):
        verify_challenge(
            challenge_attestation(
                "challenge:undeclared",
                principal_id="principal:challenge",
                category="undeclared",
            )
        )
    with pytest.raises(GovernanceError, match="NFC string"):
        challenge_attestation(
            "challenge:no-execution",
            principal_id="principal:no-execution",
            category="falsification",
        ).__class__(
            **{
                **challenge_attestation(
                    "challenge:no-execution",
                    principal_id="principal:no-execution",
                    category="falsification",
                ).__dict__,
                "execution_attestation_ref": "",
            }
        )

    counter = verify_observation(
        observation_attestation(
            "observation:challenge-counter",
            principal_id="principal:challenge-counter",
            polarity=ObservationPolarity.CONTRADICT,
        )
    )
    found = challenge_attestation(
        "challenge:found",
        principal_id="principal:challenge-found",
        category="falsification",
        result=ChallengeResult.COUNTEREVIDENCE_FOUND,
        result_observation_fingerprints=(verified_observation_fingerprint(counter),),
    )
    with pytest.raises(GovernanceError, match="do not match"):
        verify_challenge(found, result_observations=())
    verified = verify_challenge(found, result_observations=(counter,))
    assert verified_challenge_is_authoritative(verified)

    with pytest.raises(GovernanceError, match="nonce replay"):
        verify_challenge(
            challenge_attestation(
                "challenge:replayed",
                principal_id="principal:replayed",
                category="edge_case",
                nonce=verified.nonce,
            ),
            prior=(verified,),
        )


def test_identical_challenge_replay_is_idempotent() -> None:
    attestation = challenge_attestation(
        "challenge:idempotent",
        principal_id="principal:challenge-idempotent",
        category="falsification",
    )
    first = verify_challenge(attestation)
    replayed = verify_challenge(attestation, prior=(first,))

    assert replayed is first


def test_one_challenge_execution_cannot_be_relabelled_to_cover_two_categories() -> None:
    shared_execution_ref = "opaque:execution:shared"
    shared_execution_fingerprint = EXECUTION_ROOT
    falsification = verify_challenge(
        challenge_attestation(
            "challenge:shared-falsification",
            principal_id="principal:shared-falsification",
            category="falsification",
            execution_attestation_ref=shared_execution_ref,
            execution_fingerprint=shared_execution_fingerprint,
        )
    )
    relabelled = challenge_attestation(
        "challenge:shared-edge-case",
        principal_id="principal:shared-edge-case",
        category="edge_case",
        execution_attestation_ref=shared_execution_ref,
        execution_fingerprint=shared_execution_fingerprint,
    )

    with pytest.raises(GovernanceError, match="execution evidence replay"):
        verify_challenge(relabelled, prior=(falsification,))

    edge_case = verify_challenge(relabelled)
    with pytest.raises(GovernanceError, match="reuse one execution"):
        evaluate_challenge_coverage(
            (falsification, edge_case),
            required_categories=("edge_case", "falsification"),
            profile=PROFILE,
            assurance=ASSURANCE,
            manifest_root=MANIFEST_ROOT,
            commit_policy_root=COMMIT_POLICY_ROOT,
            protocol_id=PROTOCOL_ID,
            run_id=RUN_ID,
            target=TARGET,
            candidate_id=CANDIDATE,
            claim_fingerprint=CLAIM_ROOT,
            epoch=EPOCH,
            current_step=4,
        )


def test_inconclusive_or_missing_challenge_cannot_claim_coverage() -> None:
    completed = verify_challenge(
        challenge_attestation(
            "challenge:completed",
            principal_id="principal:completed",
            category="falsification",
        )
    )
    inconclusive = verify_challenge(
        challenge_attestation(
            "challenge:inconclusive",
            principal_id="principal:inconclusive",
            category="edge_case",
            result=ChallengeResult.INCONCLUSIVE,
        )
    )
    coverage = evaluate_challenge_coverage(
        (inconclusive, completed),
        required_categories=("edge_case", "falsification"),
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id=PROTOCOL_ID,
        run_id=RUN_ID,
        target=TARGET,
        candidate_id=CANDIDATE,
        claim_fingerprint=CLAIM_ROOT,
        epoch=EPOCH,
        current_step=4,
    )
    assert coverage.complete is False
    assert coverage.covered_categories == ("falsification",)
    assert coverage.missing_categories == ("edge_case",)


def test_evidence_evaluation_reapplies_policy_bound_challenge_ttl() -> None:
    positive = verify_observation(
        observation_attestation(
            "observation:challenge-ttl-anchor",
            principal_id="principal:challenge-ttl-anchor",
        )
    )
    challenge = verify_challenge(
        challenge_attestation(
            "challenge:long-lived",
            principal_id="principal:long-lived-challenge",
            category="falsification",
            expires_at_step=30,
        ),
        maximum_ttl_steps=30,
    )
    binding = bind((positive,), challenges=(challenge,))

    with pytest.raises(GovernanceError, match="challenge beyond the policy TTL"):
        evaluate_evidence_binding(
            binding,
            positive_observations=(positive,),
            counter_observations=(),
            dispositions=(),
            challenges=(challenge,),
            evidence_policy=evidence_policy(observation_ttl_steps=20),
            current_step=4,
        )


def test_evidence_binding_roots_are_order_stable_and_reject_duplicates() -> None:
    first = verify_observation(
        observation_attestation(
            "observation:first",
            principal_id="principal:first",
            group="group:first",
            domain="domain:first",
        )
    )
    second = verify_observation(
        observation_attestation(
            "observation:second",
            principal_id="principal:second",
            group="group:second",
            domain="domain:second",
        )
    )
    challenges = complete_challenges()
    forward = bind((first, second), challenges=challenges)
    reverse = bind(
        (second, first),
        challenges=tuple(reversed(challenges)),
    )

    assert evidence_binding_fingerprint(forward) == evidence_binding_fingerprint(
        reverse
    )
    assert forward.evidence_root == reverse.evidence_root
    assert rebuild_evidence_binding_roots(forward)["evidence_root"] == (
        forward.evidence_root
    )
    assert evidence_binding_is_authoritative(forward)
    assert evidence_binding_is_authoritative(replace(forward)) is False

    with pytest.raises(GovernanceError, match="replay or duplicate"):
        bind((first, first), challenges=challenges)
    object.__setattr__(forward, "evidence_root", MANIFEST_ROOT)
    assert evidence_binding_is_authoritative(forward) is False


def test_group_cap_and_source_floor_prevent_correlated_amplification() -> None:
    same_group = tuple(
        verify_observation(
            observation_attestation(
                f"observation:echo-{index}",
                principal_id=f"principal:echo-{index}",
                group="group:echo",
                domain="domain:echo",
            )
        )
        for index in range(3)
    )
    challenges = complete_challenges()
    binding = bind(same_group, challenges=challenges)
    summary = evaluate_evidence_binding(
        binding,
        positive_observations=same_group,
        counter_observations=(),
        dispositions=(),
        challenges=challenges,
        evidence_policy=evidence_policy(),
        current_step=5,
    )
    assert summary.positive_groups[0].raw_contribution == 3_000_000
    assert summary.positive_evidence == 1_000_000
    assert summary.source_diversity == 1
    assert summary.evidence_gates_satisfied is False

    low_domains = tuple(
        verify_observation(
            observation_attestation(
                f"observation:low-{index}",
                principal_id=f"principal:low-{index}",
                group=f"group:low-{index}",
                domain=f"domain:low-{index}",
                quality_ppm=100_000,
            )
        )
        for index in range(5)
    )
    low_binding = bind(
        low_domains,
        challenges=challenges,
        evidence_id="evidence:low-domains",
    )
    low_summary = evaluate_evidence_binding(
        low_binding,
        positive_observations=low_domains,
        counter_observations=(),
        dispositions=(),
        challenges=challenges,
        evidence_policy=evidence_policy(),
        current_step=5,
    )
    assert low_summary.source_diversity == 0
    assert all(not item.qualifies for item in low_summary.source_domains)


def test_correlated_counterevidence_is_capped_without_becoming_invisible() -> None:
    positive = tuple(
        verify_observation(
            observation_attestation(
                f"observation:base-{index}",
                principal_id=f"principal:base-{index}",
                group=f"group:base-{index}",
                domain=f"domain:base-{index}",
            )
        )
        for index in range(3)
    )
    counters = tuple(
        verify_observation(
            observation_attestation(
                f"observation:counter-echo-{index}",
                principal_id=f"principal:counter-echo-{index}",
                polarity=ObservationPolarity.CONTRADICT,
                group="group:counter-echo",
                domain="domain:counter-echo",
            )
        )
        for index in range(3)
    )
    dispositions = tuple(unresolved(item) for item in counters)
    challenges = complete_challenges()
    binding = bind(
        positive,
        counters=counters,
        dispositions=dispositions,
        challenges=challenges,
    )
    summary = evaluate_evidence_binding(
        binding,
        positive_observations=positive,
        counter_observations=tuple(reversed(counters)),
        dispositions=tuple(reversed(dispositions)),
        challenges=challenges,
        evidence_policy=evidence_policy(),
        current_step=5,
    )

    assert summary.counter_groups[0].raw_contribution == 3_000_000
    assert summary.counterevidence == 1_000_000
    assert summary.net_evidence == 2_000_000
    assert summary.evidence_gates_satisfied is True


def test_counterevidence_weight_uses_normative_fixed_point_floor() -> None:
    policy = evidence_policy(counter_weight_ppm=1_500_000)
    positive = tuple(
        verify_observation(
            observation_attestation(
                f"observation:weighted-positive-{index}",
                principal_id=f"principal:weighted-positive-{index}",
                group=f"group:weighted-positive-{index}",
                domain=f"domain:weighted-positive-{index}",
            ),
            policy=policy,
        )
        for index in range(2)
    )
    counter = verify_observation(
        observation_attestation(
            "observation:weighted-counter",
            principal_id="principal:weighted-counter",
            polarity=ObservationPolarity.CONTRADICT,
            group="group:weighted-counter",
            domain="domain:weighted-counter",
        ),
        policy=policy,
    )
    disposition = unresolved(counter)
    challenges = complete_challenges()
    binding = bind(
        positive,
        counters=(counter,),
        dispositions=(disposition,),
        challenges=challenges,
    )

    summary = evaluate_evidence_binding(
        binding,
        positive_observations=positive,
        counter_observations=(counter,),
        dispositions=(disposition,),
        challenges=challenges,
        evidence_policy=policy,
        current_step=5,
    )

    assert summary.positive_evidence == 2_000_000
    assert summary.counterevidence == 1_000_000
    assert summary.weighted_counterevidence == 1_500_000
    assert summary.net_evidence == 500_000


def test_unresolved_critical_counterevidence_cannot_be_drowned_by_majority() -> None:
    positive = tuple(
        verify_observation(
            observation_attestation(
                f"observation:positive-{index}",
                principal_id=f"principal:positive-{index}",
                group=f"group:positive-{index}",
                domain=f"domain:positive-{index}",
            )
        )
        for index in range(4)
    )
    counter = verify_observation(
        observation_attestation(
            "observation:critical-counter",
            principal_id="principal:critical-counter",
            polarity=ObservationPolarity.CONTRADICT,
            group="group:critical",
            domain="domain:critical",
            materiality_ppm=1_000_000,
            criticality_ppm=1_000_000,
        )
    )
    disposition = unresolved(counter)
    challenges = complete_challenges()
    binding = bind(
        positive,
        counters=(counter,),
        dispositions=(disposition,),
        challenges=challenges,
    )
    summary = evaluate_evidence_binding(
        binding,
        positive_observations=tuple(reversed(positive)),
        counter_observations=(counter,),
        dispositions=(disposition,),
        challenges=tuple(reversed(challenges)),
        evidence_policy=evidence_policy(),
        current_step=5,
    )

    assert summary.positive_evidence == 4_000_000
    assert summary.positive_threshold_satisfied is True
    assert summary.challenge_coverage_satisfied is True
    assert summary.critical_counterevidence_clear is False
    assert summary.evidence_gates_satisfied is False
