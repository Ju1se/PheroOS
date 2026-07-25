"""Distributed-assurance Store graph shared by Distributed Commit v2 tests."""

from __future__ import annotations

from dataclasses import replace

from tests.governance import test_commit_decision_v2_operations as decision_fixture
from tests.governance._commit_certificate_v2_store_support import (
    RUN_REF,
    TARGET,
    CertifiedDecisionInputs,
    _root,
    certified_inputs,
)

from pheroos.governance._commit_decision_v2.enums import CommitDecisionCommandV2
from pheroos.governance._commit_decision_v2.proposals import (
    CommitDecisionCandidateProposalV2,
    CommitDecisionOutputProposalV2,
)
from pheroos.governance._commit_decision_v2.source import (
    prepare_commit_decision_initialize_v2,
    prepare_commit_decision_successor_v2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerGrantV2,
    activate_governance_issuer_grant_v2,
)
from pheroos.governance.authority_store_v2 import GovernanceCommitDispositionV2
from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_WIRE_VERSION,
    DISTRIBUTED_COMMIT_PROFILE_VERSION,
    CertificatePolicy,
    CommitAssurance,
    CollectiveCommitPolicy,
    DistributedCommitPolicy,
)


PROFILE = DISTRIBUTED_COMMIT_PROFILE_VERSION
ASSURANCE = CommitAssurance.DISTRIBUTED


def distributed_context(scope_ref: str):
    context = decision_fixture._decision_context(scope_ref)
    grant = GovernanceIssuerGrantV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        issuer_ref=context.grant.issuer_ref,
        grant_ref="grant:distributed:a",
        grant_binding_ref=_root(f"binding:{scope_ref}:distributed"),
        operations=context.grant.operations,
        target_refs=context.grant.target_refs,
        action_refs=("commit", "epoch_transition", "recovery"),
        issued_epoch=context.grant.issued_epoch,
        not_before_epoch=context.grant.not_before_epoch,
        expires_at_epoch=context.grant.expires_at_epoch,
        revocation_generation=0,
    )
    activated = activate_governance_issuer_grant_v2(
        context.store,
        context.domain,
        grant,
        f"transition:{scope_ref}:distributed-grant",
        1,
    )
    assert activated.disposition is GovernanceCommitDispositionV2.COMMITTED
    policy = context.manifest.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    bands = {
        name: replace(band, minimum_assurance=ASSURANCE.value)
        for name, band in policy.risk_bands.items()
    }
    policy = replace(
        policy,
        assurance=ASSURANCE.value,
        risk_bands=bands,
        certificate=CertificatePolicy(
            mode="distributed",
            wire_version=COMMIT_WIRE_VERSION,
            canonicalization=COMMIT_CANONICAL_VERSION,
            hash_algorithm="sha256",
            issuer_attestation_required=True,
            independent_verification_required=True,
        ),
        distributed=DistributedCommitPolicy(
            fault_model="byzantine_static_v1",
            membership_mode="static_epoch_verified_clusters_v1",
            membership_size=1,
            max_byzantine_faults=0,
            witness_quorum=1,
            witness_ttl_steps=20,
            minimum_failure_domain_diversity=1,
            epoch_transition_rule="prior_quorum_certificate_v1",
            conflict_rule="freeze_v1",
        ),
    )
    return replace(
        context,
        grant=grant,
        manifest=replace(context.manifest, collective_commit_policy=policy),
    )


def sealed_distributed_decision(
    context,
    claim_root: str,
):
    inputs = certified_inputs(
        context,
        claim_root,
        profile=PROFILE,
        assurance=ASSURANCE,
    )
    initialize, source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:distributed:decision:initialize",
        current_step=6,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    state = decision_fixture._commit_decision(context, initialize, source)
    proposal = CommitDecisionCandidateProposalV2(
        candidate_ref="candidate:accept",
        claim_root=claim_root,
        evidence=(),
    )
    for step in (7, 8):
        request, successor = prepare_commit_decision_successor_v2(
            parent_state=state,
            manifest=context.manifest,
            profile=PROFILE,
            mutation_ref=f"mutation:distributed:decision:evaluate:{step}",
            current_step=step,
            mutation_issuer_ref=context.grant.issuer_ref,
            command=CommitDecisionCommandV2.EVALUATE,
            candidate_proposals=(proposal,),
            commit_replay_state=inputs.replay,
            risk_state=inputs.risk,
            membership_state=inputs.membership,
            support_state=inputs.support,
            evidence_state=inputs.evidence,
            stop_state=inputs.stop,
            permission_state=inputs.permission,
        )
        state = decision_fixture._commit_decision(context, request, successor)
    output = CommitDecisionOutputProposalV2(
        candidate_ref="candidate:accept",
        claim_root=claim_root,
        output_contract_root=_root("distributed:output-contract"),
        payload={"answer": "distributed-accepted"},
    )
    seal, seal_source = prepare_commit_decision_successor_v2(
        parent_state=state,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:distributed:decision:seal",
        current_step=8,
        mutation_issuer_ref=context.grant.issuer_ref,
        command=CommitDecisionCommandV2.SEAL,
        output_proposal=output,
        commit_replay_state=inputs.replay,
        risk_state=inputs.risk,
        membership_state=inputs.membership,
        support_state=inputs.support,
        evidence_state=inputs.evidence,
        stop_state=inputs.stop,
        permission_state=inputs.permission,
    )
    state = decision_fixture._commit_decision(context, seal, seal_source)
    heartbeat, heartbeat_source = prepare_commit_decision_successor_v2(
        parent_state=state,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:distributed:decision:heartbeat",
        current_step=9,
        mutation_issuer_ref=context.grant.issuer_ref,
        command=CommitDecisionCommandV2.EVALUATE,
        candidate_proposals=(proposal,),
        commit_replay_state=inputs.replay,
        risk_state=inputs.risk,
        membership_state=inputs.membership,
        support_state=inputs.support,
        evidence_state=inputs.evidence,
        stop_state=inputs.stop,
        permission_state=inputs.permission,
    )
    return (
        decision_fixture._commit_decision(context, heartbeat, heartbeat_source),
        inputs,
    )


def finalize_distributed_decision(
    context,
    parent_state,
    inputs: CertifiedDecisionInputs,
    verified_finality_input: object,
):
    snapshot = parent_state.snapshot
    seal = snapshot.seal
    assert seal is not None
    proposal = CommitDecisionCandidateProposalV2(
        candidate_ref=seal.candidate_ref,
        claim_root=seal.claim_root,
        evidence=(),
    )
    request, source = prepare_commit_decision_successor_v2(
        parent_state=parent_state,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:distributed:decision:finalize",
        current_step=snapshot.current_step + 1,
        mutation_issuer_ref=context.grant.issuer_ref,
        command=CommitDecisionCommandV2.EVALUATE,
        candidate_proposals=(proposal,),
        commit_replay_state=inputs.replay,
        risk_state=inputs.risk,
        membership_state=inputs.membership,
        support_state=inputs.support,
        evidence_state=inputs.evidence,
        stop_state=inputs.stop,
        permission_state=inputs.permission,
        verified_finality_input=verified_finality_input,
    )
    return decision_fixture._commit_decision(context, request, source)


__all__: tuple[str, ...] = ()
