"""Private Commit TCK reference probes 05 07 handlers."""

from __future__ import annotations

from typing import Any

from pheroos.conformance._commit_reference import (
    issue_reference_lease,
)
from pheroos.conformance._commit_reference_typing import collective_commit_policy

from pheroos.conformance._commit_tck.models import (
    result as _result,
)

from pheroos.conformance.commit_tck_v2_protocol import (
    CommitTckRequest as _CommitTckRequest,
)

from pheroos.governance.authority import AuthorityLevel

from pheroos.governance.errors import GovernanceError

from pheroos.governance.support_lease import (
    SupportLeaseProposal,
    evaluate_support_leases,
    initialize_support_lease_replay_state,
    issue_support_lease,
    revoke_support_lease,
)

from pheroos.conformance._commit_tck_reference.scenario import (
    _binding,
    _evaluate_binding,
    _observation,
    _reference_scenario,
    _risk_trace_sequence,
)


def _probe_case_05(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    observations = tuple(
        _observation(
            scenario,
            index=500 + index,
            source_domain=f"domain:{scenario.namespace}:low:{index}",
            quality_ppm=500_000,
            relevance_ppm=500_000,
        )
        for index in range(1, 9)
    )
    binding = _binding(
        scenario,
        candidate_id=scenario.leader_id,
        positives=observations,
        variant="case-05",
    )
    summary = _evaluate_binding(
        scenario,
        binding,
        positives=observations,
    )
    qualifying = sum(1 for item in summary.source_domains if item.qualifies)
    return _result(
        metrics={
            "domain_count": len(summary.source_domains),
            "qualifying_domain_count": qualifying,
            "source_diversity": summary.source_diversity,
            "domain_floor": collective_commit_policy(
                scenario.policy
            ).evidence_qualification.domain_contribution_floor,
        },
        roots={"positive_root": binding.positive_root},
        outcome={"low_weight_domains_raise_diversity": summary.source_diversity > 0},
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_06(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector, shared_cluster=True)
    replay = initialize_support_lease_replay_state(
        profile=scenario.profile,
        protocol_id=scenario.protocol_id,
        issuer_id=f"governance:tck:support-dedup:{scenario.namespace}",
        authority=AuthorityLevel.GOVERNANCE,
        initialized_at_step=0,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:support-dedup",
        trace_event_id=f"trace:{scenario.namespace}:support-dedup",
    )
    observations = tuple(
        _observation(
            scenario,
            index=600 + index,
            principal_index=index - 1,
            candidate_id=scenario.leader_id,
        )
        for index in range(1, 3)
    )
    leases: list[Any] = []
    for index, (principal, observation) in enumerate(
        zip(scenario.principals[:2], observations, strict=True), start=1
    ):
        lease, replay = issue_reference_lease(
            scenario.namespace,
            index=600 + index,
            principal=principal,
            observation=observation,
            candidate_id=scenario.leader_id,
            claim_fingerprint=scenario.claims[scenario.leader_id],
            profile=scenario.profile,
            assurance=scenario.assurance,
            manifest_root=scenario.manifest_root,
            commit_policy_root=scenario.commit_policy_root,
            protocol_id=scenario.protocol_id,
            run_id=scenario.run_id,
            target=scenario.target,
            epoch=scenario.epoch,
            policy=scenario.policy,
            membership_snapshot=scenario.membership_snapshot,
            membership_state=scenario.membership_state,
            replay_state=replay,
            prior_leases=tuple(leases),
            issuer_id=f"governance:tck:support-dedup:{scenario.namespace}",
        )
        leases.append(lease)
    evaluation = evaluate_support_leases(
        tuple(leases),
        revocations=(),
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=replay,
        commit_policy=collective_commit_policy(scenario.policy),
        candidate_id=scenario.leader_id,
        claim_fingerprint=scenario.claims[scenario.leader_id],
        current_step=5,
    )
    return _result(
        metrics={
            "principal_count": 2,
            "eligible_cluster_count": evaluation.eligible_cluster_count,
            "active_support_cluster_count": evaluation.active_support_cluster_count,
        },
        roots={"lease_root": evaluation.lease_root},
        outcome={"cluster_deduplicated": evaluation.active_support_cluster_count == 1},
        trace_sequence=_risk_trace_sequence(scenario),
    )


def _probe_case_07(vector: _CommitTckRequest) -> dict[str, Any]:
    scenario = _reference_scenario(vector)
    leader_leases = tuple(
        item for item in scenario.leases if item.candidate_id == scenario.leader_id
    )
    no_evidence_rejected = False
    try:
        empty_proposal = SupportLeaseProposal(
            proposal_id=f"support-proposal:{scenario.namespace}:empty",
            profile=scenario.profile,
            assurance=scenario.assurance,
            manifest_root=scenario.manifest_root,
            commit_policy_root=scenario.commit_policy_root,
            protocol_id=scenario.protocol_id,
            run_id=scenario.run_id,
            target=scenario.target,
            candidate_id=scenario.leader_id,
            claim_fingerprint=scenario.claims[scenario.leader_id],
            epoch=scenario.epoch,
            principal_id=scenario.principals[0].principal_id,
            positive_observation_fingerprints=(),
            nonce=f"nonce:lease:{scenario.namespace}:empty",
            proposed_at_step=3,
            provenance=f"urn:pheroos:tck:{scenario.namespace}:empty-lease",
            trace_event_id=f"trace:{scenario.namespace}:empty-lease",
        )
        issue_support_lease(
            empty_proposal,
            principal_verification=scenario.principals[0],
            membership_snapshot=scenario.membership_snapshot,
            membership_epoch_state=scenario.membership_state,
            replay_state=scenario.support_replay_state,
            positive_observations=(),
            commit_policy=collective_commit_policy(scenario.policy),
            lease_id=f"lease:{scenario.namespace}:empty",
            issuer_id=f"governance:tck:support:{scenario.namespace}",
            authority=AuthorityLevel.GOVERNANCE,
            current_step=4,
            issuance_provenance=f"urn:pheroos:tck:{scenario.namespace}:empty-lease",
            issuance_trace_event_id=f"trace:{scenario.namespace}:empty-lease",
            prior_leases=scenario.leases,
        )
    except (GovernanceError, ValueError):
        no_evidence_rejected = True
    revocations = tuple(
        revoke_support_lease(
            lease,
            revocation_id=f"revocation:{scenario.namespace}:leader:{index}",
            reason_codes=("tck_revoked",),
            issuer_id=lease.issuer_id,
            authority=AuthorityLevel.GOVERNANCE,
            current_step=5,
            provenance=(f"urn:pheroos:tck:{scenario.namespace}:revocation:{index}"),
            trace_event_id=(f"trace:{scenario.namespace}:revocation:{index}"),
        )
        for index, lease in enumerate(leader_leases, start=1)
    )
    revoked = evaluate_support_leases(
        scenario.leases,
        revocations=revocations,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.support_replay_state,
        commit_policy=collective_commit_policy(scenario.policy),
        candidate_id=scenario.leader_id,
        claim_fingerprint=scenario.claims[scenario.leader_id],
        current_step=5,
    )
    expired_step = max(item.expires_at_step for item in scenario.leases)
    expired = evaluate_support_leases(
        scenario.leases,
        revocations=(),
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.support_replay_state,
        commit_policy=collective_commit_policy(scenario.policy),
        candidate_id=scenario.leader_id,
        claim_fingerprint=scenario.claims[scenario.leader_id],
        current_step=expired_step,
    )
    cross_replay = initialize_support_lease_replay_state(
        profile=scenario.profile,
        protocol_id=scenario.protocol_id,
        issuer_id=f"governance:tck:support-cross:{scenario.namespace}",
        authority=AuthorityLevel.GOVERNANCE,
        initialized_at_step=0,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:support-cross",
        trace_event_id=f"trace:{scenario.namespace}:support-cross",
    )
    cross_lease, cross_replay = issue_reference_lease(
        scenario.namespace,
        index=704,
        principal=scenario.principals[1],
        observation=scenario.observations[scenario.other_id][0],
        candidate_id=scenario.other_id,
        claim_fingerprint=scenario.claims[scenario.other_id],
        profile=scenario.profile,
        assurance=scenario.assurance,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        protocol_id=scenario.protocol_id,
        run_id=scenario.run_id,
        target=scenario.target,
        epoch=scenario.epoch,
        policy=scenario.policy,
        membership_snapshot=scenario.membership_snapshot,
        membership_state=scenario.membership_state,
        replay_state=cross_replay,
        prior_leases=(),
        issuer_id=f"governance:tck:support-cross:{scenario.namespace}",
    )
    cross_candidate = evaluate_support_leases(
        (cross_lease,),
        revocations=(),
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=cross_replay,
        commit_policy=collective_commit_policy(scenario.policy),
        candidate_id=scenario.leader_id,
        claim_fingerprint=scenario.claims[scenario.leader_id],
        current_step=5,
    )
    return _result(
        metrics={
            "revoked_active": revoked.active_support_cluster_count,
            "expired_active": expired.active_support_cluster_count,
            "cross_candidate_active": cross_candidate.active_support_cluster_count,
        },
        roots={
            "revoked_lease_root": revoked.lease_root,
            "expired_lease_root": expired.lease_root,
            "cross_candidate_lease_root": cross_candidate.lease_root,
        },
        outcome={
            "no_evidence_rejected": no_evidence_rejected,
            "all_invalid_excluded": all(
                item == 0
                for item in (
                    revoked.active_support_cluster_count,
                    expired.active_support_cluster_count,
                    cross_candidate.active_support_cluster_count,
                )
            ),
        },
        trace_sequence=_risk_trace_sequence(scenario),
    )
