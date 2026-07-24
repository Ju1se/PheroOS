"""Private Commit reference fixture evidence handlers."""

from __future__ import annotations

from collections.abc import Sequence

from pheroos.conformance._commit_reference_typing import (
    evidence_qualification_policy,
)

from pheroos.governance.authority import AuthorityLevel

from pheroos.governance.challenge import (
    ChallengeAttestation,
    ChallengeResult,
    VerifiedChallenge,
    verify_challenge_attestation,
)

from pheroos.governance.evidence_binding import (
    EvidenceBinding,
    bind_evidence,
)

from pheroos.governance.observation import (
    CounterevidenceDisposition,
    CounterevidenceDispositionKind,
    ObservationAttestation,
    ObservationPolarity,
    VerifiedObservation,
    issue_counterevidence_disposition,
    verified_observation_fingerprint,
    verify_observation_attestation,
)

from pheroos.governance.principal import (
    PrincipalAttestation,
    PrincipalVerification,
    verify_principal_attestation,
)

from pheroos.protocol.commit_models import CommitAssurance

from pheroos.conformance._commit_reference_fixture.models import (
    REFERENCE_CHALLENGE_CATEGORY,
    reference_fingerprint,
)


def issue_reference_principal(
    namespace: str,
    *,
    index: int,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    cluster_id: str | None = None,
    failure_domain: str | None = None,
) -> PrincipalVerification:
    principal_id = f"principal:{namespace}:{index}"
    return verify_principal_attestation(
        PrincipalAttestation(
            principal_id=principal_id,
            attestation_ref=f"opaque:principal:{namespace}:{index}",
            method="identity-verifier-v1",
            issuer_id="issuer:tck:identity",
            issued_at_step=0,
            expires_at_step=30,
            provenance=f"urn:pheroos:tck:{namespace}:principal:{index}",
            nonce=f"nonce:principal:{namespace}:{index}",
            trace_event_id=f"trace:{namespace}:principal:{index}",
        ),
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=commit_policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        cluster_id=cluster_id or f"cluster:{namespace}:{index}",
        failure_domain=failure_domain or f"failure-domain:{namespace}:{index}",
        verifier_id="governance:tck:identity",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=1,
        provenance=f"urn:pheroos:tck:{namespace}:principal-verification:{index}",
        trace_event_id=f"trace:{namespace}:principal-verified:{index}",
    )


def issue_reference_observation(
    namespace: str,
    *,
    index: int,
    principal: PrincipalVerification,
    candidate_id: str,
    claim_fingerprint: str,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    evidence_policy: object,
    polarity: ObservationPolarity = ObservationPolarity.SUPPORT,
    independence_group: str | None = None,
    source_domain: str | None = None,
    nonce: str | None = None,
    quality_ppm: int = 1_000_000,
    relevance_ppm: int = 1_000_000,
    materiality_ppm: int = 1_000_000,
    criticality_ppm: int = 0,
    expires_at_step: int | None = None,
) -> VerifiedObservation:
    expiry = (
        2 + evidence_qualification_policy(evidence_policy).observation_ttl_steps
        if expires_at_step is None
        else expires_at_step
    )
    attestation = ObservationAttestation(
        observation_id=f"observation:{namespace}:{index}",
        target=target,
        candidate_id=candidate_id,
        claim_fingerprint=claim_fingerprint,
        principal_id=principal.principal_id,
        polarity=polarity,
        independence_group=(independence_group or f"group:{namespace}:{index}"),
        source_domain=source_domain or f"source-domain:{namespace}:{index}",
        payload_fingerprint=reference_fingerprint(f"payload:{namespace}:{index}"),
        reported_quality_ppm=quality_ppm,
        reported_relevance_ppm=relevance_ppm,
        reported_materiality_ppm=materiality_ppm,
        reported_criticality_ppm=criticality_ppm,
        provenance=f"urn:pheroos:tck:{namespace}:observation:{index}",
        nonce=nonce or f"nonce:observation:{namespace}:{index}",
        observed_at_step=2,
        expires_at_step=expiry,
        trace_event_id=f"trace:{namespace}:observation:{index}",
    )
    return verify_observation_attestation(
        attestation,
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
        principal_verification=principal,
        evidence_policy=evidence_qualification_policy(evidence_policy),
        quality_ppm=quality_ppm,
        relevance_ppm=relevance_ppm,
        materiality_ppm=materiality_ppm,
        criticality_ppm=criticality_ppm,
        verifier_id="governance:tck:evidence",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=3,
        verification_provenance=(
            f"urn:pheroos:tck:{namespace}:observation-verification:{index}"
        ),
        verification_trace_event_id=(f"trace:{namespace}:observation-verified:{index}"),
        prior_observations=(),
    )


def issue_reference_challenge(
    namespace: str,
    *,
    index: int,
    principal: PrincipalVerification,
    candidate_id: str,
    claim_fingerprint: str,
    profile: str,
    assurance: CommitAssurance,
    manifest_root: str,
    commit_policy_root: str,
    protocol_id: str,
    run_id: str,
    target: str,
    epoch: int,
    result: ChallengeResult = ChallengeResult.NO_COUNTEREVIDENCE,
    result_observations: Sequence[VerifiedObservation] = (),
) -> VerifiedChallenge:
    attestation = ChallengeAttestation(
        challenge_id=f"challenge:{namespace}:{index}",
        target=target,
        candidate_id=candidate_id,
        claim_fingerprint=claim_fingerprint,
        principal_id=principal.principal_id,
        category=REFERENCE_CHALLENGE_CATEGORY,
        execution_method="declared-counter-search-v1",
        execution_attestation_ref=f"opaque:execution:{namespace}:{index}",
        execution_fingerprint=reference_fingerprint(
            f"challenge-execution:{namespace}:{index}"
        ),
        result=result,
        result_fingerprint=reference_fingerprint(
            f"challenge-result:{namespace}:{index}:{result.value}"
        ),
        result_observation_fingerprints=tuple(
            verified_observation_fingerprint(item) for item in result_observations
        ),
        provenance=f"urn:pheroos:tck:{namespace}:challenge:{index}",
        nonce=f"nonce:challenge:{namespace}:{index}",
        executed_at_step=2,
        expires_at_step=20,
        trace_event_id=f"trace:{namespace}:challenge:{index}",
    )
    return verify_challenge_attestation(
        attestation,
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
        principal_verification=principal,
        declared_categories=(REFERENCE_CHALLENGE_CATEGORY,),
        maximum_ttl_steps=20,
        result_observations=tuple(result_observations),
        verifier_id="governance:tck:challenge",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=3,
        verification_provenance=(
            f"urn:pheroos:tck:{namespace}:challenge-verification:{index}"
        ),
        verification_trace_event_id=(f"trace:{namespace}:challenge-verified:{index}"),
        prior_challenges=(),
    )


def issue_reference_disposition(
    namespace: str,
    counter_observation: VerifiedObservation,
    *,
    index: int,
    kind: CounterevidenceDispositionKind,
    rebuttal_observations: Sequence[VerifiedObservation] = (),
    resolution_ref: str = "",
) -> CounterevidenceDisposition:
    selected_resolution_ref = resolution_ref
    if (
        not selected_resolution_ref
        and kind is not CounterevidenceDispositionKind.UNRESOLVED
    ):
        selected_resolution_ref = reference_fingerprint(
            f"counterevidence-resolution:{namespace}:{index}:{kind.value}"
        )
    return issue_counterevidence_disposition(
        counter_observation,
        disposition_id=f"disposition:{namespace}:{index}",
        kind=kind,
        rebuttal_observations=tuple(rebuttal_observations),
        resolution_ref=selected_resolution_ref,
        reason_codes=(f"tck_{kind.value}",),
        verifier_id="governance:tck:counterevidence",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=4,
        provenance=f"urn:pheroos:tck:{namespace}:disposition:{index}",
        trace_event_id=f"trace:{namespace}:disposition:{index}",
    )


def issue_reference_binding(
    namespace: str,
    *,
    candidate_id: str,
    claim_fingerprint: str,
    observations: Sequence[VerifiedObservation],
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
    epoch: int,
    current_step: int,
    binding_variant: str = "",
) -> EvidenceBinding:
    suffix = f":{binding_variant}" if binding_variant else ""
    return bind_evidence(
        evidence_id=f"evidence:{namespace}:{candidate_id}{suffix}",
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
        positive_observations=tuple(observations),
        counter_observations=tuple(counter_observations),
        dispositions=tuple(dispositions),
        challenges=tuple(challenges),
        issuer_id="governance:tck:evidence-binding",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=current_step,
        provenance=(f"urn:pheroos:tck:{namespace}:evidence:{candidate_id}{suffix}"),
        trace_event_id=f"trace:{namespace}:evidence:{candidate_id}{suffix}",
    )
