"""Private Commit TCK reference distributed handlers."""

from __future__ import annotations

from collections.abc import Mapping

from typing import Any

from pheroos.conformance._commit_reference import (
    ReferenceDistributedCommit,
    ReferenceScenario,
    build_reference_distributed_commit,
    build_reference_portable_commit,
    build_reference_stable_commit,
    issue_reference_distributed_certificate,
    issue_reference_semantic_conflict_certificate,
    issue_reference_witness,
    reference_fingerprint,
)
from pheroos.conformance._commit_reference_typing import collective_commit_policy

from pheroos.conformance.commit_tck_v2_protocol import (
    CommitTckRequest as _CommitTckRequest,
)

from pheroos.governance.authority import AuthorityLevel

from pheroos.governance.commit_state import (
    DecisionOutcome,
    decision_outcome_fingerprint,
)

from pheroos.governance.distributed_commit import (
    assemble_portable_distributed_commit_certificate,
    distributed_commit_certificate_fingerprint,
    issue_distributed_commit_proposal,
    portable_membership_snapshot_from_eligible,
    register_distributed_commit_certificate,
    verify_distributed_commit_certificate,
)

from pheroos.governance.permission import (
    issue_action_permission,
)

from pheroos.governance.stop_signal import (
    StopResolution,
    verify_stop_resolution,
)

from pheroos.protocol.commit_models import CommitAction

from pheroos.conformance._commit_tck_reference.scenario import (
    _reference_scenario,
)


def _output_gates(
    scenario: ReferenceScenario,
    outcome: DecisionOutcome,
    *,
    certificate_ref: str,
    suffix: str,
    issued_at_step: int,
    stop_expires_at_step: int,
    permission_expires_at_step: int,
    permission_allowed: bool = True,
) -> tuple[Any, Any]:
    outcome_ref = decision_outcome_fingerprint(outcome)
    stop = verify_stop_resolution(
        StopResolution(
            target=scenario.target,
            action=CommitAction.PUBLISH,
            blocked=False,
            reason="all_hard_stops_resolved",
        ),
        resolution_id=f"stop:{scenario.namespace}:output:{suffix}",
        profile=scenario.profile,
        assurance=scenario.assurance,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        protocol_id=scenario.protocol_id,
        run_id=scenario.run_id,
        epoch=scenario.epoch,
        decision_ref=outcome_ref,
        certificate_ref=certificate_ref,
        resolved_stop_root=reference_fingerprint(
            f"stop:{scenario.namespace}:output:{suffix}"
        ),
        verifier_id="governance:tck:output-stop",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=issued_at_step,
        expires_at_step=stop_expires_at_step,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:output-stop:{suffix}",
        trace_event_id=f"trace:{scenario.namespace}:output-stop:{suffix}",
    )
    permission = issue_action_permission(
        permission_id=f"permission:{scenario.namespace}:output:{suffix}",
        profile=scenario.profile,
        assurance=scenario.assurance,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        protocol_id=scenario.protocol_id,
        run_id=scenario.run_id,
        target=scenario.target,
        action=CommitAction.PUBLISH,
        epoch=scenario.epoch,
        decision_ref=outcome_ref,
        certificate_ref=certificate_ref,
        allowed=permission_allowed,
        reason_codes=("policy_authorized",) if permission_allowed else ("denied",),
        issuer_id="governance:tck:output-permission",
        policy_ref="policy:tck:output-v1",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=issued_at_step,
        expires_at_step=permission_expires_at_step,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:output-permission:{suffix}",
        trace_event_id=f"trace:{scenario.namespace}:output-permission:{suffix}",
    )
    return stop, permission


def _distributed_conflict(
    vector: _CommitTckRequest,
) -> tuple[
    ReferenceDistributedCommit,
    Any,
    Any,
    Any,
    Any,
    Any,
    Mapping[str, str],
    Mapping[str, str],
    bool,
]:
    scenario = _reference_scenario(vector)
    stable = build_reference_stable_commit(scenario, variant="case-30")
    portable = build_reference_portable_commit(stable, variant="case-30")
    policy = collective_commit_policy(scenario.policy).distributed
    assert policy is not None
    bundle = build_reference_distributed_commit(
        portable,
        witness_count=policy.witness_quorum,
        variant="case-30:first",
    )
    first = issue_reference_distributed_certificate(
        bundle,
        witness_count=policy.witness_quorum,
        variant="case-30:first",
    )
    first_state = register_distributed_commit_certificate(
        bundle.state,
        first,
        commit_policy=collective_commit_policy(scenario.policy),
        portable_certificate=portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        trusted_witness_attestations=bundle.trusted_witness_attestations,
        current_step=stable.window.last_evaluated_step,
    )
    second_proposal = issue_distributed_commit_proposal(
        stable.receipt,
        portable.certificate,
        scenario.membership_snapshot,
        scenario.membership_state,
        commit_policy=collective_commit_policy(scenario.policy),
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        proposal_id=f"proposal:{scenario.namespace}:case-30:second",
        proposed_at_step=stable.window.last_evaluated_step,
    )
    second_trust = dict(bundle.trusted_witness_attestations)
    second_verifications = tuple(
        issue_reference_witness(
            scenario,
            second_proposal,
            principal,
            index=100 + index,
            variant="case-30:second",
            trusted_witness_attestations=second_trust,
        )
        for index, principal in enumerate(
            scenario.principals[: policy.witness_quorum], start=1
        )
    )
    second = assemble_portable_distributed_commit_certificate(
        second_proposal,
        portable_membership_snapshot_from_eligible(scenario.membership_snapshot),
        tuple(reversed(second_verifications)),
        commit_policy=collective_commit_policy(scenario.policy),
        portable_certificate=portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        trusted_witness_attestations=second_trust,
        certificate_id=f"distributed-certificate:{scenario.namespace}:case-30:second",
        issuer_id="governance:tck:peer-certificate",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=stable.window.last_evaluated_step,
        provenance=f"urn:pheroos:tck:{scenario.namespace}:peer-certificate",
        trace_event_id=f"trace:{scenario.namespace}:peer-certificate",
    )
    same_value_state = register_distributed_commit_certificate(
        first_state,
        second,
        commit_policy=collective_commit_policy(scenario.policy),
        portable_certificate=portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        trusted_witness_attestations=second_trust,
        current_step=stable.window.last_evaluated_step,
    )
    second_ref = distributed_commit_certificate_fingerprint(second)
    same_value_accepted = bool(
        not same_value_state.frozen
        and first.commit_value_root == second.commit_value_root
        and verify_distributed_commit_certificate(
            second,
            commit_policy=collective_commit_policy(scenario.policy),
            portable_certificate=portable.certificate,
            trusted_issuer_attestations=portable.trusted_issuer_attestations,
            trusted_witness_attestations=second_trust,
            require_final=True,
        )
        and any(
            item.certificate_ref == second_ref
            and item.commit_value_root == second.commit_value_root
            and item.proposal_digest == second.proposal_digest
            for item in same_value_state.final_registrations
        )
    )
    (
        conflict_proposal,
        conflict_portable,
        conflict_issuer_trust,
        conflict_witness_trust,
        conflict_certificate,
    ) = issue_reference_semantic_conflict_certificate(
        bundle,
        field_name="output_payload_fingerprint",
        field_value=reference_fingerprint(
            f"conflicting-output:{scenario.namespace}:case-30"
        ),
        variant="case-30:semantic-conflict",
    )
    if conflict_proposal.commit_value_root == first.commit_value_root:
        raise ValueError("case 30 semantic conflict did not change the value root")
    frozen = register_distributed_commit_certificate(
        same_value_state,
        conflict_certificate,
        commit_policy=collective_commit_policy(scenario.policy),
        portable_certificate=conflict_portable,
        trusted_issuer_attestations=conflict_issuer_trust,
        trusted_witness_attestations=conflict_witness_trust,
        current_step=stable.window.last_evaluated_step,
    )
    return (
        bundle,
        first,
        second,
        conflict_certificate,
        frozen,
        conflict_portable,
        conflict_issuer_trust,
        conflict_witness_trust,
        same_value_accepted,
    )
