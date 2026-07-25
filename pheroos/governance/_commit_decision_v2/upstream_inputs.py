"""Store-current Decision inputs without conflating freshness with existence."""

from __future__ import annotations

from dataclasses import dataclass

from pheroos.protocol.authority_v2 import GovernanceReadPreconditionV2
from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._commit_gate_v2.dependency_source import (
    _current_membership,
    _current_replay,
    _current_risk,
    _current_support,
    _validate_snapshot_context,
)
from pheroos.governance._commit_gate_v2.dependency_contracts import (
    CommitGateDependenciesV2,
)
from pheroos.governance._commit_state_v2.contracts import CommitReplaySnapshotV2
from pheroos.governance._risk_v2.contracts import RiskStateSnapshotV2
from pheroos.governance._support_v2.membership_contracts import (
    MembershipSnapshotV2,
)
from pheroos.governance._support_v2.support_state_contracts import SupportSnapshotV2


@dataclass(frozen=True, slots=True)
class _CommitDecisionUpstreamMaterialV2:
    preconditions: tuple[GovernanceReadPreconditionV2, ...]
    replay: CommitReplaySnapshotV2
    risk: RiskStateSnapshotV2
    membership: MembershipSnapshotV2
    support: SupportSnapshotV2


def _collect_decision_upstream_material_v2(
    *,
    domain_root: str,
    scope_ref: str,
    manifest_root: str,
    commit_policy_root: str,
    profile: str,
    assurance: CommitAssurance,
    protocol_ref: str,
    run_ref: str,
    target_ref: str,
    observed_epoch: int,
    current_step: int,
    commit_replay_state: object,
    risk_state: object,
    membership_state: object,
    support_state: object,
) -> _CommitDecisionUpstreamMaterialV2:
    replay, replay_precondition = _current_replay(commit_replay_state)
    risk, risk_precondition = _current_risk(risk_state)
    membership, membership_precondition, verification_precondition = (
        _current_membership(membership_state)
    )
    support, support_precondition = _current_support(support_state)
    snapshots = (
        ("replay", replay, current_step),
        (
            "risk",
            risk,
            min(current_step, risk.assessment.expires_at_step - 1),
        ),
        (
            "membership",
            membership,
            min(current_step, membership.expires_at_step - 1),
        ),
        ("support", support, current_step),
    )
    for name, snapshot, validation_step in snapshots:
        _validate_snapshot_context(
            name,
            snapshot,
            domain_root=domain_root,
            scope_ref=scope_ref,
            manifest_root=manifest_root,
            commit_policy_root=commit_policy_root,
            profile=profile,
            assurance=assurance,
            protocol_ref=protocol_ref,
            run_ref=run_ref,
            target_ref=target_ref,
            observed_epoch=observed_epoch,
            current_step=validation_step,
        )
    preconditions = tuple(
        sorted(
            (
                replay_precondition,
                risk_precondition,
                verification_precondition,
                membership_precondition,
                support_precondition,
            ),
            key=lambda item: item.stream_ref.encode("utf-8"),
        )
    )
    return _CommitDecisionUpstreamMaterialV2(
        preconditions=preconditions,
        replay=replay,
        risk=risk,
        membership=membership,
        support=support,
    )


def _gate_dependencies_match_v2(
    dependencies: CommitGateDependenciesV2,
    upstream: _CommitDecisionUpstreamMaterialV2,
) -> bool:
    preconditions = {item.stream_ref: item for item in upstream.preconditions}
    expected = CommitGateDependenciesV2(
        replay_stream_ref=upstream.replay.stream_ref,
        replay_revision=upstream.replay.revision,
        replay_transition_id=upstream.replay.transition_id,
        replay_snapshot_root=upstream.replay.snapshot_root,
        replay_head_root=preconditions[upstream.replay.stream_ref].expected_root,
        risk_stream_ref=upstream.risk.stream_ref,
        risk_revision=upstream.risk.revision,
        risk_transition_id=upstream.risk.transition_id,
        risk_snapshot_root=upstream.risk.snapshot_root,
        risk_head_root=preconditions[upstream.risk.stream_ref].expected_root,
        verification_stream_ref=upstream.membership.verification_stream_ref,
        verification_revision=upstream.membership.verification_revision,
        verification_transition_id=upstream.membership.verification_transition_id,
        verification_snapshot_root=upstream.membership.verification_snapshot_root,
        verification_head_root=preconditions[
            upstream.membership.verification_stream_ref
        ].expected_root,
        membership_stream_ref=upstream.membership.stream_ref,
        membership_revision=upstream.membership.revision,
        membership_transition_id=upstream.membership.transition_id,
        membership_snapshot_root=upstream.membership.snapshot_root,
        membership_head_root=preconditions[
            upstream.membership.stream_ref
        ].expected_root,
        support_stream_ref=upstream.support.stream_ref,
        support_revision=upstream.support.revision,
        support_transition_id=upstream.support.transition_id,
        support_snapshot_root=upstream.support.snapshot_root,
        support_head_root=preconditions[upstream.support.stream_ref].expected_root,
    )
    return dependencies.to_dict() == expected.to_dict()


__all__: tuple[str, ...] = ()
