"""Exact upstream source proof and preparation for Commit Stop v2."""

from __future__ import annotations

from collections.abc import Sequence
from typing import NoReturn, cast, final

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.authority_v2 import GovernanceReadPreconditionV2

from pheroos.governance._commit_gate_v2.common import (
    COMMIT_GATE_GENESIS_TRANSITION_ID_V2,
    COMMIT_STOP_GENESIS_SNAPSHOT_ROOT_V2,
    commit_stop_stream_ref_v2,
    commit_stop_transition_id_v2,
)
from pheroos.governance._commit_gate_v2.contract_support import (
    _validate_successor_common,
)
from pheroos.governance._commit_gate_v2.dependency_contracts import (
    commit_gate_evaluation_context_root_v2,
    commit_stop_policy_root_v2,
)
from pheroos.governance._commit_gate_v2.dependency_source import (
    _collect_dependency_material_v2,
)
from pheroos.governance._commit_gate_v2.source_common import (
    _VerifiedGateSourceBaseV2,
    _dependency_preconditions_v2,
    _issue_gate_source_v2,
    _source_context_root_v2,
    _validated_gate_context_v2,
    _verified_gate_source_fields_v2,
)
from pheroos.governance._commit_gate_v2.stop_contracts import (
    CommitStopRequestV2,
    CommitStopSnapshotV2,
)


@final
class VerifiedCommitStopSourceV2(_VerifiedGateSourceBaseV2):
    """Non-portable proof for one exact Stop resolution request."""

    def __new__(cls, *_args: object, **_kwargs: object) -> VerifiedCommitStopSourceV2:
        raise TypeError("VerifiedCommitStopSourceV2 cannot be constructed directly")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedCommitStopSourceV2 is final")

    def __repr__(self) -> str:
        return "<VerifiedCommitStopSourceV2 redacted>"


def prepare_commit_stop_resolution_v2(
    *,
    domain_root: str,
    scope_ref: str,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    run_ref: str,
    target_ref: str,
    observed_epoch: int,
    resolution_ref: str,
    current_step: int,
    mutation_issuer_ref: str,
    blocked: bool,
    reason_codes: Sequence[str],
    issued_at_step: int,
    expires_at_step: int,
    commit_replay_state: object,
    risk_state: object,
    membership_state: object,
    support_state: object,
    parent_snapshot: CommitStopSnapshotV2 | None = None,
) -> tuple[CommitStopRequestV2, VerifiedCommitStopSourceV2]:
    """Prepare a complete Stop replacement from five current durable heads."""

    context = _validated_gate_context_v2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        manifest=manifest,
        profile=profile,
        run_ref=run_ref,
        target_ref=target_ref,
        observed_epoch=observed_epoch,
        request_ref=resolution_ref,
        current_step=current_step,
        mutation_issuer_ref=mutation_issuer_ref,
    )
    material = _collect_dependency_material_v2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        profile=context.profile,
        assurance=context.assurance,
        protocol_ref=context.protocol_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        observed_epoch=observed_epoch,
        current_step=current_step,
        commit_replay_state=commit_replay_state,
        risk_state=risk_state,
        membership_state=membership_state,
        support_state=support_state,
    )
    parent_revision, parent_transition, parent_root = _stop_parent(parent_snapshot)
    stream_ref = commit_stop_stream_ref_v2(
        scope_ref, context.protocol_ref, run_ref, target_ref
    )
    transition_id = commit_stop_transition_id_v2(stream_ref, resolution_ref)
    evaluation_context_root = commit_gate_evaluation_context_root_v2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        profile=context.profile,
        assurance=context.assurance,
        protocol_ref=context.protocol_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        observed_epoch=observed_epoch,
        current_step=current_step,
        dependencies=material.dependencies,
    )
    snapshot = CommitStopSnapshotV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        manifest_root=context.manifest_root,
        commit_policy_root=context.commit_policy_root,
        policy_root=commit_stop_policy_root_v2(
            manifest_root=context.manifest_root,
            commit_policy_root=context.commit_policy_root,
            protocol_ref=context.protocol_ref,
            target_ref=target_ref,
        ),
        profile=context.profile,
        assurance=context.assurance,
        protocol_ref=context.protocol_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        observed_epoch=observed_epoch,
        current_step=current_step,
        stream_ref=stream_ref,
        resolution_ref=resolution_ref,
        transition_id=transition_id,
        revision=parent_revision + 1,
        parent_revision=parent_revision,
        parent_transition_id=parent_transition,
        parent_snapshot_root=parent_root,
        mutation_issuer_ref=mutation_issuer_ref,
        blocked=blocked,
        reason_codes=tuple(reason_codes),
        reason_root="",
        issued_at_step=issued_at_step,
        expires_at_step=expires_at_step,
        dependencies=material.dependencies,
        evaluation_context_root=evaluation_context_root,
    )
    if parent_snapshot is not None:
        _validate_successor_common(snapshot, parent_snapshot)
    request = CommitStopRequestV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        observed_epoch=observed_epoch,
        resolution_ref=resolution_ref,
        stream_ref=stream_ref,
        transition_id=transition_id,
        snapshot=snapshot,
    )
    source = _issue_gate_source_v2(
        VerifiedCommitStopSourceV2,
        kind="stop",
        request=CommitStopRequestV2.from_dict(request.to_dict()),
        request_root=request.request_root,
        evaluation_context_root=evaluation_context_root,
        dependencies=material.dependencies,
        manifest=context.manifest,
        preconditions=material.preconditions,
    )
    return request, cast(VerifiedCommitStopSourceV2, source)


def verify_commit_stop_request_source_v2(
    request: CommitStopRequestV2,
    *,
    source: object,
    committed_parent_snapshot: CommitStopSnapshotV2 | None,
) -> tuple[str, tuple[GovernanceReadPreconditionV2, ...]]:
    """Recompute every source commitment without trusting caller expected roots."""

    if type(request) is not CommitStopRequestV2:
        raise TypeError("commit stop source verification requires exact request v2")
    stored, manifest, material, preconditions = _verified_gate_source_fields_v2(
        source,
        expected_type=VerifiedCommitStopSourceV2,
        expected_kind="stop",
        expected_request_type=CommitStopRequestV2,
    )
    detached = CommitStopRequestV2.from_dict(
        cast(CommitStopRequestV2, stored).to_dict()
    )
    if detached.to_dict() != request.to_dict():
        raise ValueError("commit stop source request is mismatched")
    snapshot = request.snapshot
    context = _validated_gate_context_v2(
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        manifest=manifest,
        profile=snapshot.profile,
        run_ref=request.run_ref,
        target_ref=request.target_ref,
        observed_epoch=request.observed_epoch,
        request_ref=request.resolution_ref,
        current_step=snapshot.current_step,
        mutation_issuer_ref=snapshot.mutation_issuer_ref,
    )
    if (
        context.manifest_root != snapshot.manifest_root
        or context.commit_policy_root != snapshot.commit_policy_root
        or context.assurance is not snapshot.assurance
    ):
        raise ValueError("commit stop source manifest context is mismatched")
    if committed_parent_snapshot is None:
        if snapshot.revision != 1:
            raise ValueError("commit stop source parent is missing")
    else:
        _validate_successor_common(snapshot, committed_parent_snapshot)
    expected_preconditions = _dependency_preconditions_v2(snapshot.dependencies)
    expected_source_root = _source_context_root_v2(
        kind="stop",
        request_root=request.request_root,
        evaluation_context_root=snapshot.evaluation_context_root,
        dependency_root=snapshot.dependencies.dependency_root,
    )
    if (
        preconditions != expected_preconditions
        or material.request_root != request.request_root
        or material.evaluation_context_root != snapshot.evaluation_context_root
        or material.dependency_root != snapshot.dependencies.dependency_root
        or material.source_context_root != expected_source_root
    ):
        raise ValueError("commit stop source proof is mismatched")
    return expected_source_root, expected_preconditions


def _stop_parent(
    parent: CommitStopSnapshotV2 | None,
) -> tuple[int, str, str]:
    if parent is None:
        return (
            0,
            COMMIT_GATE_GENESIS_TRANSITION_ID_V2,
            COMMIT_STOP_GENESIS_SNAPSHOT_ROOT_V2,
        )
    if type(parent) is not CommitStopSnapshotV2:
        raise TypeError("commit stop parent must be exact snapshot v2")
    detached = CommitStopSnapshotV2.from_dict(parent.to_dict())
    return detached.revision, detached.transition_id, detached.snapshot_root


__all__: tuple[str, ...] = ()
