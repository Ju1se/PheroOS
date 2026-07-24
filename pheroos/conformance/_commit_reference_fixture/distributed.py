"""Private Commit reference fixture distributed handlers."""

from __future__ import annotations

from pheroos.conformance._commit_reference_typing import (
    collective_commit_policy,
    distributed_commit_policy,
)

from pheroos.governance.authority import AuthorityLevel

from pheroos.governance.certificate import (
    evidence_commit_certificate_body_root,
    issue_evidence_commit_certificate,
)

from pheroos.governance.distributed_commit import (
    QUORUM_WITNESS_VERSION,
    DistributedCommitProposal,
    QuorumWitness,
    WitnessVerification,
    initialize_distributed_commit_state,
    issue_distributed_commit_proposal,
    quorum_witness_signing_root,
    record_witness_verifications,
    verify_quorum_witness,
)

from pheroos.governance.principal import (
    PrincipalVerification,
)

from pheroos.conformance._commit_reference_fixture.models import (
    ReferenceDistributedCommit,
    ReferencePortableCommit,
    ReferenceScenario,
    ReferenceStableCommit,
)

from pheroos.conformance._commit_reference_fixture.state import (
    _REFERENCE_DISTRIBUTED_FIXTURES,
    _REFERENCE_DISTRIBUTED_FIXTURES_LOCK,
)


def build_reference_portable_commit(
    stable: ReferenceStableCommit,
    *,
    variant: str = "portable",
) -> ReferencePortableCommit:
    scenario = stable.scenario
    certificate_id = f"certificate:{scenario.namespace}:{variant}"
    issuer_id = "governance:tck:portable-certificate"
    authority = AuthorityLevel.GOVERNANCE
    issued_at_step = stable.window.last_evaluated_step
    provenance = f"urn:pheroos:tck:{scenario.namespace}:certificate:{variant}"
    trace_event_id = f"trace:{scenario.namespace}:certificate:{variant}"
    body_root = evidence_commit_certificate_body_root(
        stable.receipt,
        certificate_id=certificate_id,
        issuer_id=issuer_id,
        authority=authority,
        issued_at_step=issued_at_step,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )
    attestation_refs = (
        f"attestation:portable:{scenario.namespace}:{variant}:primary",
        f"attestation:portable:{scenario.namespace}:{variant}:backup",
    )
    trusted = {item: body_root for item in attestation_refs}
    certificate = issue_evidence_commit_certificate(
        stable.receipt,
        commit_policy=collective_commit_policy(scenario.policy),
        issuer_attestation_refs=attestation_refs,
        trusted_issuer_attestations=trusted,
        certificate_id=certificate_id,
        issuer_id=issuer_id,
        authority=authority,
        issued_at_step=issued_at_step,
        provenance=provenance,
        trace_event_id=trace_event_id,
    )
    return ReferencePortableCommit(
        stable=stable,
        certificate=certificate,
        trusted_issuer_attestations=trusted,
    )


def build_reference_distributed_commit(
    portable: ReferencePortableCommit,
    *,
    witness_count: int | None = None,
    variant: str = "distributed",
) -> ReferenceDistributedCommit:
    stable = portable.stable
    scenario = stable.scenario
    fixture_key = (scenario.namespace, variant, witness_count)
    with _REFERENCE_DISTRIBUTED_FIXTURES_LOCK:
        cached = _REFERENCE_DISTRIBUTED_FIXTURES.get(fixture_key)
        if cached is not None:
            return cached
    distributed = collective_commit_policy(scenario.policy).distributed
    if distributed is None:
        raise ValueError("distributed fixture requires distributed commit policy")
    proposal = issue_distributed_commit_proposal(
        stable.receipt,
        portable.certificate,
        scenario.membership_snapshot,
        scenario.membership_state,
        commit_policy=collective_commit_policy(scenario.policy),
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        proposal_id=f"proposal:{scenario.namespace}:{variant}",
        proposed_at_step=stable.window.last_evaluated_step,
    )
    state = initialize_distributed_commit_state(
        scenario.membership_snapshot,
        scenario.membership_state,
        commit_policy=collective_commit_policy(scenario.policy),
        current_step=stable.window.last_evaluated_step,
        issuer_id="governance:tck:distributed-state",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:distributed-state",
        trace_event_id=f"trace:{scenario.namespace}:distributed-state",
    )
    trusted_witnesses: dict[str, str] = {}
    verifications = tuple(
        issue_reference_witness(
            scenario,
            proposal,
            principal,
            index=index,
            variant=variant,
            trusted_witness_attestations=trusted_witnesses,
        )
        for index, principal in enumerate(scenario.principals, start=1)
    )
    selected_count = (
        distributed.witness_quorum if witness_count is None else witness_count
    )
    selected = verifications[:selected_count]
    state = record_witness_verifications(
        state,
        selected,
        current_step=stable.window.last_evaluated_step,
    )
    bundle = ReferenceDistributedCommit(
        portable=portable,
        proposal=proposal,
        state=state,
        verifications=verifications,
        trusted_witness_attestations=trusted_witnesses,
    )
    with _REFERENCE_DISTRIBUTED_FIXTURES_LOCK:
        _REFERENCE_DISTRIBUTED_FIXTURES[fixture_key] = bundle
    return bundle


def issue_reference_witness(
    scenario: ReferenceScenario,
    proposal: DistributedCommitProposal,
    principal: PrincipalVerification,
    *,
    index: int,
    variant: str,
    trusted_witness_attestations: dict[str, str],
) -> WitnessVerification:
    step = proposal.proposed_at_step
    witness = QuorumWitness(
        witness_version=QUORUM_WITNESS_VERSION,
        witness_id=(
            f"witness:{scenario.namespace}:{proposal.proposal_id}:{variant}:{index}"
        ),
        profile=proposal.profile,
        assurance=proposal.assurance,
        protocol_id=proposal.protocol_id,
        run_id=proposal.run_id,
        target=proposal.target,
        epoch=proposal.epoch,
        candidate_id=proposal.candidate_id,
        membership_root=proposal.membership_root,
        commit_value_root=proposal.commit_value_root,
        proposal_digest=proposal.proposal_digest,
        principal_id=principal.principal_id,
        principal_cluster_id=principal.cluster_id,
        failure_domain=principal.failure_domain,
        nonce=f"nonce:witness:{scenario.namespace}:{variant}:{index}",
        witnessed_at_step=step,
        expires_at_step=(
            step + distributed_commit_policy(scenario.policy).witness_ttl_steps
        ),
        provenance=f"urn:pheroos:tck:{scenario.namespace}:witness:{variant}:{index}",
        trace_event_id=f"trace:{scenario.namespace}:witness:{variant}:{index}",
        attestation_ref=(f"attestation:witness:{scenario.namespace}:{variant}:{index}"),
    )
    trusted_witness_attestations[witness.attestation_ref] = quorum_witness_signing_root(
        witness
    )
    return verify_quorum_witness(
        witness,
        proposal,
        principal,
        scenario.membership_snapshot,
        scenario.membership_state,
        commit_policy=collective_commit_policy(scenario.policy),
        trusted_witness_attestations=trusted_witness_attestations,
        verification_id=(f"verification:{scenario.namespace}:{variant}:{index}"),
        verifier_id="governance:tck:witness-verifier",
        authority=AuthorityLevel.GOVERNANCE,
        verified_at_step=step,
        provenance=(
            f"urn:pheroos:tck:{scenario.namespace}:witness-verification:"
            f"{variant}:{index}"
        ),
        trace_event_id=(
            f"trace:{scenario.namespace}:witness-verification:{variant}:{index}"
        ),
    )
