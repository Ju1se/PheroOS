"""Private Commit reference fixture certificate handlers."""

from __future__ import annotations

from copy import deepcopy

from pheroos.conformance._commit_reference_typing import collective_commit_policy

from pheroos.governance.authority import AuthorityLevel

from pheroos.governance.certificate import (
    EvidenceCommitCertificate,
    evidence_commit_certificate_fingerprint,
    evidence_commit_certificate_from_payload,
    evidence_commit_certificate_payload,
)

from pheroos.governance.distributed_commit import (
    DISTRIBUTED_PROPOSAL_VERSION,
    QUORUM_WITNESS_VERSION,
    WITNESS_VERIFICATION_VERSION,
    DistributedCommitCertificate,
    DistributedCommitProposal,
    QuorumWitness,
    WitnessVerification,
    assemble_portable_distributed_commit_certificate,
    distributed_commit_proposal_from_payload,
    distributed_commit_proposal_payload,
    distributed_commit_value_payload,
    distributed_commit_value_root,
    portable_membership_snapshot_from_eligible,
    quorum_witness_signing_root,
    quorum_witness_fingerprint,
)

from pheroos.governance.principal import (
    principal_verification_fingerprint,
)

from pheroos.protocol.commit_wire import (
    commit_payload_fingerprint,
)

from pheroos.conformance._commit_reference_fixture.models import (
    ReferenceDistributedCommit,
    reference_fingerprint,
)


def issue_reference_distributed_certificate(
    bundle: ReferenceDistributedCommit,
    *,
    witness_count: int,
    variant: str,
) -> DistributedCommitCertificate:
    scenario = bundle.portable.stable.scenario
    step = bundle.portable.stable.window.last_evaluated_step
    return assemble_portable_distributed_commit_certificate(
        bundle.proposal,
        portable_membership_snapshot_from_eligible(scenario.membership_snapshot),
        bundle.verifications[:witness_count],
        commit_policy=collective_commit_policy(scenario.policy),
        portable_certificate=bundle.portable.certificate,
        trusted_issuer_attestations=bundle.portable.trusted_issuer_attestations,
        trusted_witness_attestations=bundle.trusted_witness_attestations,
        certificate_id=f"distributed-certificate:{scenario.namespace}:{variant}",
        issuer_id="governance:tck:distributed-certificate",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=step,
        provenance=(
            f"urn:pheroos:tck:{scenario.namespace}:distributed-certificate:{variant}"
        ),
        trace_event_id=(
            f"trace:{scenario.namespace}:distributed-certificate:{variant}"
        ),
    )


def issue_reference_semantic_conflict_certificate(
    bundle: ReferenceDistributedCommit,
    *,
    field_name: str,
    field_value: str,
    variant: str,
) -> tuple[
    DistributedCommitProposal,
    EvidenceCommitCertificate,
    dict[str, str],
    dict[str, str],
    DistributedCommitCertificate,
]:
    """Build a valid portable peer proof for a different commit value."""

    stable = bundle.portable.stable
    scenario = stable.scenario
    step = stable.window.last_evaluated_step
    portable_payload = deepcopy(
        evidence_commit_certificate_payload(bundle.portable.certificate)
    )
    portable_payload[field_name] = field_value
    portable_payload["certificate_id"] = f"certificate:{scenario.namespace}:{variant}"
    portable_payload["local_receipt_ref"] = reference_fingerprint(
        f"remote-receipt:{scenario.namespace}:{variant}"
    )
    issuer_attestation_ref = f"attestation:portable:{scenario.namespace}:{variant}"
    portable_payload["issuer_attestation_refs"] = (issuer_attestation_ref,)
    portable_body = dict(portable_payload)
    portable_body.pop("issuer_attestation_refs")
    portable_body.pop("certificate_body_root")
    portable_body.pop("certificate_root")
    portable_body_root = commit_payload_fingerprint(
        portable_body,
        schema="pheroos-evidence-commit-certificate-body-v1",
        profile=scenario.profile,
    )
    portable_payload["certificate_body_root"] = portable_body_root
    portable_payload["certificate_root"] = commit_payload_fingerprint(
        {
            "certificate_body_root": portable_body_root,
            "issuer_attestation_refs": (issuer_attestation_ref,),
        },
        schema="pheroos-evidence-commit-certificate-envelope-v1",
        profile=scenario.profile,
    )
    portable = evidence_commit_certificate_from_payload(portable_payload)
    issuer_trust = {
        **bundle.portable.trusted_issuer_attestations,
        issuer_attestation_ref: portable_body_root,
    }

    proposal_payload = distributed_commit_proposal_payload(bundle.proposal)
    proposal_payload[field_name] = field_value
    proposal_payload["proposal_id"] = f"proposal:{scenario.namespace}:{variant}"
    proposal_payload["local_receipt_ref"] = portable.local_receipt_ref
    proposal_payload["portable_certificate_ref"] = (
        evidence_commit_certificate_fingerprint(portable)
    )
    value_payload = distributed_commit_value_payload(bundle.proposal)
    value_payload[field_name] = field_value
    proposal_payload["commit_value_root"] = distributed_commit_value_root(value_payload)
    proposal_body = dict(proposal_payload)
    proposal_body.pop("proposal_digest")
    proposal_payload["proposal_digest"] = commit_payload_fingerprint(
        proposal_body,
        schema=DISTRIBUTED_PROPOSAL_VERSION,
        profile=scenario.profile,
    )
    proposal = distributed_commit_proposal_from_payload(proposal_payload)

    distributed = collective_commit_policy(scenario.policy).distributed
    if distributed is None:
        raise ValueError("semantic conflict requires distributed assurance")
    witness_trust = dict(bundle.trusted_witness_attestations)
    verifications: list[WitnessVerification] = []
    for index, principal in enumerate(
        scenario.principals[: distributed.witness_quorum],
        start=1,
    ):
        witness = QuorumWitness(
            witness_version=QUORUM_WITNESS_VERSION,
            witness_id=(f"witness:{scenario.namespace}:{variant}:{index}"),
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
            nonce=f"nonce:{scenario.namespace}:{variant}:{index}",
            witnessed_at_step=step,
            expires_at_step=step + distributed.witness_ttl_steps,
            provenance=(
                f"urn:pheroos:tck:{scenario.namespace}:remote-witness:{variant}:{index}"
            ),
            trace_event_id=(
                f"trace:{scenario.namespace}:remote-witness:{variant}:{index}"
            ),
            attestation_ref=(
                f"attestation:witness:{scenario.namespace}:{variant}:{index}"
            ),
        )
        signing_root = quorum_witness_signing_root(witness)
        witness_trust[witness.attestation_ref] = signing_root
        verifications.append(
            WitnessVerification(
                verification_version=WITNESS_VERIFICATION_VERSION,
                verification_id=(
                    f"verification:{scenario.namespace}:{variant}:{index}"
                ),
                witness=witness,
                witness_fingerprint=quorum_witness_fingerprint(witness),
                witness_signing_root=signing_root,
                principal_verification_ref=(
                    principal_verification_fingerprint(principal)
                ),
                verified_at_step=step,
                expires_at_step=step + distributed.witness_ttl_steps,
                verifier_id="governance:tck:remote-witness-verifier",
                authority=AuthorityLevel.GOVERNANCE,
                provenance=(
                    f"urn:pheroos:tck:{scenario.namespace}:"
                    f"remote-verification:{variant}:{index}"
                ),
                trace_event_id=(
                    f"trace:{scenario.namespace}:remote-verification:{variant}:{index}"
                ),
            )
        )
    certificate = assemble_portable_distributed_commit_certificate(
        proposal,
        portable_membership_snapshot_from_eligible(scenario.membership_snapshot),
        tuple(reversed(verifications)),
        commit_policy=collective_commit_policy(scenario.policy),
        portable_certificate=portable,
        trusted_issuer_attestations=issuer_trust,
        trusted_witness_attestations=witness_trust,
        certificate_id=(f"distributed-certificate:{scenario.namespace}:{variant}"),
        issuer_id="governance:tck:remote-distributed-certificate",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=step,
        provenance=(
            f"urn:pheroos:tck:{scenario.namespace}:remote-certificate:{variant}"
        ),
        trace_event_id=(f"trace:{scenario.namespace}:remote-certificate:{variant}"),
    )
    return proposal, portable, issuer_trust, witness_trust, certificate
