"""Private Commit reference fixture scenario handlers."""

from __future__ import annotations

from collections.abc import Mapping

from pheroos.governance.authority import AuthorityLevel

from pheroos.governance.commit import (
    CandidateCommitInput,
    build_commit_replay_receipts,
    issue_commit_evaluation_context,
)

from pheroos.governance.commit_state import (
    initialize_commit_replay_state,
    record_commit_replay_receipts,
)

from pheroos.governance.risk import (
    RiskBand,
    initialize_risk_assessment_chain,
    issue_commit_threshold_snapshot,
    issue_risk_assessment,
)

from pheroos.governance.support_lease import (
    SupportLease,
    initialize_support_lease_replay_state,
    issue_eligible_principal_snapshot,
)

from pheroos.protocol.commit_models import CommitAction, CommitAssurance

from pheroos.protocol.commit_wire import (
    commit_manifest_fingerprint,
    commit_policy_fingerprint,
)

from pheroos.protocol.manifest import capability_manifest_from_dict

from pheroos.conformance._commit_reference_fixture.models import (
    REFERENCE_EPOCH,
    REFERENCE_LEADER,
    ReferenceScenario,
    reference_fingerprint,
    reference_namespace,
)

from pheroos.conformance._commit_reference_fixture.decision import (
    issue_reference_action_gates,
    issue_reference_lease,
)

from pheroos.conformance._commit_reference_fixture.evidence import (
    issue_reference_binding,
    issue_reference_challenge,
    issue_reference_observation,
    issue_reference_principal,
)


def build_reference_scenario(
    vector_id: str,
    manifest_payload: Mapping[str, object],
    *,
    profile: str,
    variant: str = "base",
    tie: bool = False,
    blocked: bool = False,
    shared_cluster: bool = False,
    leader_observation_count: int = 2,
    other_observation_count: int | None = None,
    minimum_membership_size: int = 3,
) -> ReferenceScenario:
    """Issue one complete deterministic Optimal Commit authority substrate."""

    manifest = capability_manifest_from_dict(dict(manifest_payload))
    policy = manifest.protocol.collective_commit_policy
    if policy is None:
        raise ValueError("reference scenario requires collective_commit_policy")
    assurance = CommitAssurance(policy.assurance)
    protocol_id = manifest.protocol.id
    target = policy.target
    epoch = REFERENCE_EPOCH
    candidates = tuple(item.id for item in manifest.protocol.candidates)
    leader_id = REFERENCE_LEADER if REFERENCE_LEADER in candidates else candidates[0]
    fallback_id = policy.terminal_outcome.safe_fallback_candidate
    substantive = tuple(
        item for item in candidates if item not in {leader_id, fallback_id}
    )
    if not substantive:
        raise ValueError("reference scenario requires two substantive candidates")
    other_id = substantive[0]
    manifest_root = commit_manifest_fingerprint(manifest, profile=profile)
    policy_root = commit_policy_fingerprint(policy, profile=profile)
    # A JSON mutation that changes authority-bearing manifest semantics must
    # never fork an existing strong process-local head.  Canonical manifest and
    # policy roots isolate those variants while semantic permutations that keep
    # both roots stable continue to exercise exact-replay authority.
    namespace = reference_namespace(
        vector_id,
        f"{variant}:manifest-{manifest_root[7:23]}:policy-{policy_root[7:23]}",
    )
    run_id = f"run:{namespace}"
    claims = {
        candidate_id: reference_fingerprint(f"claim:{namespace}:{candidate_id}")
        for candidate_id in candidates
    }

    if type(minimum_membership_size) is not int or minimum_membership_size < 3:
        raise ValueError("reference membership requires at least three principals")
    membership_size = max(
        minimum_membership_size,
        (policy.distributed.membership_size if policy.distributed is not None else 0),
    )
    principals = tuple(
        issue_reference_principal(
            namespace,
            index=index,
            profile=profile,
            assurance=assurance,
            manifest_root=manifest_root,
            commit_policy_root=policy_root,
            protocol_id=protocol_id,
            run_id=run_id,
            target=target,
            epoch=epoch,
            cluster_id=(f"cluster:{namespace}:shared" if shared_cluster else None),
        )
        for index in range(1, membership_size + 1)
    )
    membership_snapshot, membership_state = issue_eligible_principal_snapshot(
        principals,
        snapshot_id=f"membership:{namespace}",
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        issuer_id="governance:tck:membership",
        membership_method="verified-static-epoch-v1",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=2,
        expires_at_step=30,
        provenance=f"urn:pheroos:tck:{namespace}:membership",
        trace_event_id=f"trace:{namespace}:membership",
    )

    if type(leader_observation_count) is not int or leader_observation_count < 2:
        raise ValueError("reference leader requires at least two observations")
    selected_other_count = (
        2 if tie else 1 if other_observation_count is None else other_observation_count
    )
    if type(selected_other_count) is not int or selected_other_count < 1:
        raise ValueError("reference other candidate requires observations")
    leader_observations = tuple(
        issue_reference_observation(
            namespace,
            index=index,
            principal=(principals[0] if index != 2 else principals[2]),
            candidate_id=leader_id,
            claim_fingerprint=claims[leader_id],
            profile=profile,
            assurance=assurance,
            manifest_root=manifest_root,
            commit_policy_root=policy_root,
            protocol_id=protocol_id,
            run_id=run_id,
            target=target,
            epoch=epoch,
            evidence_policy=policy.evidence_qualification,
        )
        for index in range(1, leader_observation_count + 1)
    )
    other_values = [
        issue_reference_observation(
            namespace,
            index=100 + index,
            principal=principals[1],
            candidate_id=other_id,
            claim_fingerprint=claims[other_id],
            profile=profile,
            assurance=assurance,
            manifest_root=manifest_root,
            commit_policy_root=policy_root,
            protocol_id=protocol_id,
            run_id=run_id,
            target=target,
            epoch=epoch,
            evidence_policy=policy.evidence_qualification,
        )
        for index in range(1, selected_other_count + 1)
    ]
    observations = {
        leader_id: leader_observations,
        other_id: tuple(other_values),
    }
    challenges = {
        candidate_id: issue_reference_challenge(
            namespace,
            index=index,
            principal=principals[index - 1],
            candidate_id=candidate_id,
            claim_fingerprint=claims[candidate_id],
            profile=profile,
            assurance=assurance,
            manifest_root=manifest_root,
            commit_policy_root=policy_root,
            protocol_id=protocol_id,
            run_id=run_id,
            target=target,
            epoch=epoch,
        )
        for index, candidate_id in enumerate((leader_id, other_id), start=1)
    }
    bindings = {
        candidate_id: issue_reference_binding(
            namespace,
            candidate_id=candidate_id,
            claim_fingerprint=claims[candidate_id],
            observations=candidate_observations,
            counter_observations=(),
            dispositions=(),
            challenges=(challenges[candidate_id],),
            profile=profile,
            assurance=assurance,
            manifest_root=manifest_root,
            commit_policy_root=policy_root,
            protocol_id=protocol_id,
            run_id=run_id,
            target=target,
            epoch=epoch,
            current_step=4,
        )
        for candidate_id, candidate_observations in observations.items()
    }
    candidate_inputs = tuple(
        CandidateCommitInput(
            candidate_id=candidate_id,
            claim_fingerprint=claims[candidate_id],
            evidence_binding=bindings[candidate_id],
            positive_observations=observations[candidate_id],
            counter_observations=(),
            dispositions=(),
            challenges=(challenges[candidate_id],),
        )
        for candidate_id in (leader_id, other_id)
    )

    support_replay = initialize_support_lease_replay_state(
        profile=profile,
        protocol_id=protocol_id,
        issuer_id=f"governance:tck:support:{namespace}",
        authority=AuthorityLevel.GOVERNANCE,
        initialized_at_step=0,
        provenance=f"urn:pheroos:tck:{namespace}:support-replay",
        trace_event_id=f"trace:{namespace}:support-replay",
    )
    leases: list[SupportLease] = []
    lease_inputs = (
        (leader_id, principals[0], observations[leader_id][0]),
        (other_id, principals[1], observations[other_id][0]),
        (leader_id, principals[2], observations[leader_id][1]),
    )
    for index, (candidate_id, principal, observation) in enumerate(
        lease_inputs,
        start=1,
    ):
        lease, support_replay = issue_reference_lease(
            namespace,
            index=index,
            principal=principal,
            observation=observation,
            candidate_id=candidate_id,
            claim_fingerprint=claims[candidate_id],
            profile=profile,
            assurance=assurance,
            manifest_root=manifest_root,
            commit_policy_root=policy_root,
            protocol_id=protocol_id,
            run_id=run_id,
            target=target,
            epoch=epoch,
            policy=policy,
            membership_snapshot=membership_snapshot,
            membership_state=membership_state,
            replay_state=support_replay,
            prior_leases=tuple(leases),
        )
        leases.append(lease)

    risk_chain = initialize_risk_assessment_chain(
        commit_policy=policy,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        issuer_id="governance:tck:risk-chain",
        authority=AuthorityLevel.GOVERNANCE,
        initialized_at_step=1,
        expires_at_step=30,
        provenance=f"urn:pheroos:tck:{namespace}:risk-chain",
        trace_event_id=f"trace:{namespace}:risk-chain",
    )
    risk_assessment, risk_chain = issue_risk_assessment(
        risk_chain,
        assessment_id=f"risk:{namespace}:low",
        risk_band=RiskBand.LOW,
        risk_input_fingerprints=(reference_fingerprint(f"risk-input:{namespace}"),),
        rationale_codes=("declared_risk",),
        assessment_method="declared-risk-matrix-v1",
        commit_policy=policy,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        issuer_id="governance:tck:risk",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=2,
        expires_at_step=30,
        provenance=f"urn:pheroos:tck:{namespace}:risk",
        trace_event_id=f"trace:{namespace}:risk",
    )
    threshold = issue_commit_threshold_snapshot(
        risk_assessment,
        chain_state=risk_chain,
        threshold_id=f"threshold:{namespace}:low",
        commit_policy=policy,
        issuer_id="governance:tck:threshold",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=2,
        provenance=f"urn:pheroos:tck:{namespace}:threshold",
        trace_event_id=f"trace:{namespace}:threshold",
    )
    replay = initialize_commit_replay_state(
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        current_step=0,
        issuer_id="governance:tck:replay",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:pheroos:tck:{namespace}:replay",
        trace_event_id=f"trace:{namespace}:replay",
    )
    replay = record_commit_replay_receipts(
        replay,
        current_step=5,
        receipts=build_commit_replay_receipts(candidate_inputs, leases),
    )
    context = issue_commit_evaluation_context(
        manifest,
        context_id=f"context:{namespace}",
        profile=profile,
        assurance=assurance,
        run_id=run_id,
        target=target,
        epoch=epoch,
        candidate_claims=claims,
        risk_chain_state=risk_chain,
        risk_assessment=risk_assessment,
        threshold_snapshot=threshold,
        membership_snapshot=membership_snapshot,
        membership_epoch_state=membership_state,
        replay_state=replay,
        support_replay_state=support_replay,
        issuer_id="governance:tck:commit-context",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=5,
        provenance=f"urn:pheroos:tck:{namespace}:context",
        trace_event_id=f"trace:{namespace}:context",
    )
    stop, permission = issue_reference_action_gates(
        namespace,
        context=context,
        action=CommitAction.COMMIT,
        blocked=blocked,
        current_step=5,
        expires_at_step=20,
        suffix="commit",
    )
    return ReferenceScenario(
        namespace=namespace,
        manifest=manifest,
        policy=policy,
        profile=profile,
        assurance=assurance,
        manifest_root=manifest_root,
        commit_policy_root=policy_root,
        protocol_id=protocol_id,
        run_id=run_id,
        target=target,
        epoch=epoch,
        leader_id=leader_id,
        other_id=other_id,
        fallback_id=fallback_id,
        claims=claims,
        principals=principals,
        membership_snapshot=membership_snapshot,
        membership_state=membership_state,
        observations=observations,
        challenges=challenges,
        bindings=bindings,
        candidate_inputs=candidate_inputs,
        leases=tuple(leases),
        support_replay_state=support_replay,
        risk_chain_state=risk_chain,
        risk_assessment=risk_assessment,
        threshold=threshold,
        replay_state=replay,
        context=context,
        stop_resolution=stop,
        permission=permission,
    )
