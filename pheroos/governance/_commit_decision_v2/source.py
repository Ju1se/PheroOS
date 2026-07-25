"""Non-portable source proof for complete Commit Decision v2 replacements."""

from __future__ import annotations

from collections.abc import Sequence

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2

from pheroos.governance._commit_decision_v2.common import _root
from pheroos.governance._commit_decision_v2.dependencies import (
    CommitDecisionDependencyV2,
    canonical_commit_decision_dependencies_v2,
)
from pheroos.governance._commit_decision_v2.enums import (
    CommitDecisionCommandV2,
    CommitDecisionDependencyRoleV2,
)
from pheroos.governance._commit_decision_v2.finality_inputs import (
    _optional_verified_finality_input_v2,
)
from pheroos.governance._commit_decision_v2.genesis_inputs import (
    _canonical_genesis_inputs_v2,
)
from pheroos.governance._commit_decision_v2.reducer import reduce_commit_decision_v2
from pheroos.governance._commit_decision_v2.request import CommitDecisionRequestV2
from pheroos.governance._commit_decision_v2.seal_context import (
    _verified_commit_decision_seal_context_material_v2,
    _verified_commit_decision_seal_context_v2,
)
from pheroos.governance._commit_decision_v2.snapshot import (
    COMMIT_DECISION_GENESIS_SNAPSHOT_ROOT_V2,
    COMMIT_DECISION_GENESIS_TRANSITION_ID_V2,
    commit_decision_stream_ref_v2,
)
from pheroos.governance._commit_decision_v2.source_inputs import (
    _collect_commit_decision_inputs_v2,
)
from pheroos.governance._commit_decision_v2.source_proof import (
    VerifiedCommitDecisionSourceV2,
    _issue_source_v2,
    _source_context_root_v2,
)
from pheroos.governance._commit_decision_v2.proposals import (
    CommitDecisionCandidateProposalV2,
    CommitDecisionOutputProposalV2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitPositionV2,
    GovernanceHeadV2,
)


def prepare_commit_decision_initialize_v2(
    *,
    domain: AuthorityDomainV2,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    run_ref: str,
    target_ref: str,
    observed_epoch: int,
    mutation_ref: str,
    current_step: int,
    mutation_issuer_ref: str,
) -> tuple[CommitDecisionRequestV2, VerifiedCommitDecisionSourceV2]:
    """Prepare the sole initialization without manufacturing dependencies."""

    if type(domain) is not AuthorityDomainV2:
        raise TypeError("Commit Decision v2 requires an exact authority domain")
    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("Commit Decision v2 requires an exact scoped manifest")
    detached_manifest = ScopedProtocolManifestV2.from_dict(manifest.to_dict())
    stream_ref = commit_decision_stream_ref_v2(
        domain.scope_ref, detached_manifest.id, run_ref, target_ref
    )
    request = CommitDecisionRequestV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        protocol_ref=detached_manifest.id,
        run_ref=run_ref,
        target_ref=target_ref,
        observed_epoch=observed_epoch,
        mutation_ref=mutation_ref,
        mutation_issuer_ref=mutation_issuer_ref,
        command=CommitDecisionCommandV2.INITIALIZE,
        current_step=current_step,
        candidate_proposals=(),
        output_proposal=None,
        finality_projection=None,
        restart_epoch=None,
    )
    genesis = GovernanceHeadV2.genesis(domain, stream_ref)
    dependencies = (
        CommitDecisionDependencyV2(
            role=CommitDecisionDependencyRoleV2.PARENT,
            stream_ref=stream_ref,
            revision=0,
            transition_id=COMMIT_DECISION_GENESIS_TRANSITION_ID_V2,
            snapshot_root=COMMIT_DECISION_GENESIS_SNAPSHOT_ROOT_V2,
            head_root=genesis.head_root,
            receipt_root=_root("genesis-receipt", {"stream_ref": stream_ref}),
            observed_position=GovernanceCommitPositionV2.CURRENT,
        ),
    )
    policy = detached_manifest.collective_commit_policy
    if policy is None:
        raise ValueError("Commit Decision v2 manifest has no commit policy")
    required = policy.commit_window.minimum_stability_steps
    source_root = _source_context_root_v2(
        request=request,
        manifest=detached_manifest,
        dependencies=dependencies,
        parent=None,
        assessment=None,
        finality=None,
        finality_input_root="",
        seal_inclusion=None,
        gate_status=None,
    )
    snapshot = reduce_commit_decision_v2(
        request,
        manifest=detached_manifest,
        profile=profile,
        dependencies=dependencies,
        source_context_root=source_root,
        parent=None,
        assessment=None,
        required_stability_steps=required,
    )
    return request, _issue_source_v2(
        request=request,
        manifest=detached_manifest,
        profile=profile,
        dependencies=dependencies,
        parent=None,
        assessment=None,
        required_stability_steps=required,
        finality=None,
        finality_input_root="",
        seal_inclusion=None,
        gate_status=None,
        source_context_root=source_root,
        snapshot=snapshot,
    )


def prepare_commit_decision_successor_v2(
    *,
    parent_state: object,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    mutation_ref: str,
    current_step: int,
    mutation_issuer_ref: str,
    command: CommitDecisionCommandV2,
    candidate_proposals: Sequence[CommitDecisionCandidateProposalV2] = (),
    output_proposal: CommitDecisionOutputProposalV2 | None = None,
    restart_epoch: int | None = None,
    commit_replay_state: object,
    risk_state: object,
    membership_state: object,
    support_state: object,
    evidence_state: object,
    stop_state: object,
    permission_state: object,
    verified_finality_input: object | None = None,
) -> tuple[CommitDecisionRequestV2, VerifiedCommitDecisionSourceV2]:
    """Prepare one successor from exact current Store-verified owners."""

    if command is CommitDecisionCommandV2.INITIALIZE:
        raise ValueError("commit decision successor cannot initialize")
    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("commit decision successor requires an exact manifest")
    detached_manifest = ScopedProtocolManifestV2.from_dict(manifest.to_dict())
    inputs = _collect_commit_decision_inputs_v2(
        parent_state=parent_state,
        manifest=detached_manifest,
        profile=profile,
        current_step=current_step,
        proposals=candidate_proposals,
        commit_replay_state=commit_replay_state,
        risk_state=risk_state,
        membership_state=membership_state,
        support_state=support_state,
        evidence_state=evidence_state,
        stop_state=stop_state,
        permission_state=permission_state,
    )
    parent = inputs.parent
    finality_input = _optional_verified_finality_input_v2(
        verified_finality_input,
        parent_state=parent_state,
        parent=parent,
        current_step=current_step,
    )
    dependencies = canonical_commit_decision_dependencies_v2(
        (
            *inputs.dependencies,
            *(() if finality_input is None else (finality_input.dependency,)),
        )
    )
    finality = None if finality_input is None else finality_input.projection
    finality_input_root = "" if finality_input is None else finality_input.input_root
    request = CommitDecisionRequestV2(
        domain_root=inputs.domain.domain_root,
        scope_ref=inputs.domain.scope_ref,
        protocol_ref=parent.protocol_ref,
        run_ref=parent.run_ref,
        target_ref=parent.target_ref,
        observed_epoch=parent.epoch,
        mutation_ref=mutation_ref,
        mutation_issuer_ref=mutation_issuer_ref,
        command=command,
        current_step=current_step,
        candidate_proposals=candidate_proposals,
        output_proposal=output_proposal,
        finality_projection=finality,
        restart_epoch=restart_epoch,
    )
    assessment = (
        inputs.assessment
        if command
        in {
            CommitDecisionCommandV2.EVALUATE,
            CommitDecisionCommandV2.SEAL,
        }
        else None
    )
    gate_status = inputs.gate_status if parent.seal is not None else None
    seal_inclusion = None
    if parent.seal is not None:
        seal_context = _verified_commit_decision_seal_context_v2(parent_state)
        seal_inclusion = _verified_commit_decision_seal_context_material_v2(
            seal_context
        ).seal_inclusion
    source_root = _source_context_root_v2(
        request=request,
        manifest=detached_manifest,
        dependencies=dependencies,
        parent=parent,
        assessment=assessment,
        finality=finality,
        finality_input_root=finality_input_root,
        seal_inclusion=seal_inclusion,
        gate_status=gate_status,
    )
    snapshot = reduce_commit_decision_v2(
        request,
        manifest=detached_manifest,
        profile=profile,
        dependencies=dependencies,
        source_context_root=source_root,
        parent=parent,
        assessment=assessment,
        required_stability_steps=inputs.required_stability_steps,
        verified_finality=finality,
        verified_seal_inclusion=seal_inclusion,
        current_gate_status=gate_status,
    )
    return request, _issue_source_v2(
        request=request,
        manifest=detached_manifest,
        profile=profile,
        dependencies=dependencies,
        parent=parent,
        assessment=assessment,
        required_stability_steps=inputs.required_stability_steps,
        finality=finality,
        finality_input_root=finality_input_root,
        seal_inclusion=seal_inclusion,
        gate_status=gate_status,
        source_context_root=source_root,
        snapshot=snapshot,
    )


def prepare_commit_decision_missing_inputs_v2(
    *,
    parent_state: object,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    mutation_ref: str,
    current_step: int,
    mutation_issuer_ref: str,
) -> tuple[CommitDecisionRequestV2, VerifiedCommitDecisionSourceV2]:
    """Prepare bounded progress/fallback for any partial upstream set."""

    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("commit decision missing-input path requires exact manifest")
    detached = ScopedProtocolManifestV2.from_dict(manifest.to_dict())
    domain, parent, dependencies = _canonical_genesis_inputs_v2(
        parent_state=parent_state,
        manifest=detached,
        profile=profile,
    )
    if parent.seal is not None:
        raise ValueError("sealed decision cannot use the missing-input path")
    request = CommitDecisionRequestV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        protocol_ref=parent.protocol_ref,
        run_ref=parent.run_ref,
        target_ref=parent.target_ref,
        observed_epoch=parent.epoch,
        mutation_ref=mutation_ref,
        mutation_issuer_ref=mutation_issuer_ref,
        command=CommitDecisionCommandV2.EVALUATE,
        current_step=current_step,
        candidate_proposals=(),
        output_proposal=None,
        finality_projection=None,
        restart_epoch=None,
    )
    policy = detached.collective_commit_policy
    assert policy is not None
    required = policy.commit_window.minimum_stability_steps
    source_root = _source_context_root_v2(
        request=request,
        manifest=detached,
        dependencies=dependencies,
        parent=parent,
        assessment=None,
        finality=None,
        finality_input_root="",
        seal_inclusion=None,
        gate_status=None,
    )
    snapshot = reduce_commit_decision_v2(
        request,
        manifest=detached,
        profile=profile,
        dependencies=dependencies,
        source_context_root=source_root,
        parent=parent,
        assessment=None,
        required_stability_steps=required,
    )
    return request, _issue_source_v2(
        request=request,
        manifest=detached,
        profile=profile,
        dependencies=dependencies,
        parent=parent,
        assessment=None,
        required_stability_steps=required,
        finality=None,
        finality_input_root="",
        seal_inclusion=None,
        gate_status=None,
        source_context_root=source_root,
        snapshot=snapshot,
    )


__all__: tuple[str, ...] = ()
