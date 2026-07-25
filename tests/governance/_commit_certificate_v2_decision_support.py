"""Certified Commit Decision v2 seal used by Certificate integration tests."""

from __future__ import annotations

from tests.governance import test_commit_decision_v2_operations as decision_fixture
from tests.governance._commit_certificate_v2_store_support import (
    PROFILE,
    RUN_REF,
    TARGET,
    certified_inputs,
    _root,
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


def sealed_certified_decision(context, claim_root: str):
    inputs = certified_inputs(context, claim_root)
    initialize, source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:certificate:decision:initialize",
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
            mutation_ref=f"mutation:certificate:decision:evaluate:{step}",
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
        output_contract_root=_root("certificate:output-contract"),
        payload={"answer": "accepted"},
    )
    seal, seal_source = prepare_commit_decision_successor_v2(
        parent_state=state,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:certificate:decision:seal",
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
        mutation_ref="mutation:certificate:decision:heartbeat",
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


def finalize_certified_decision(
    context,
    parent_state,
    inputs,
    verified_finality_input: object,
    *,
    mutation_ref: str = "mutation:certificate:decision:finalize",
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
        mutation_ref=mutation_ref,
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


def heartbeat_certified_decision(
    context,
    parent_state,
    inputs,
    *,
    mutation_ref: str,
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
        mutation_ref=mutation_ref,
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
    )
    return decision_fixture._commit_decision(context, request, source)


__all__: tuple[str, ...] = ()
