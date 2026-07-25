"""Canonical current-or-genesis dependency material for Decision liveness."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._commit_decision_v2.common import _root
from pheroos.governance._commit_decision_v2.dependencies import (
    CommitDecisionDependencyV2,
    canonical_commit_decision_dependencies_v2,
)
from pheroos.governance._commit_decision_v2.enums import (
    CommitDecisionDependencyRoleV2,
)
from pheroos.governance._commit_decision_v2.snapshot import CommitDecisionSnapshotV2
from pheroos.governance._commit_decision_v2.source_inputs import _current_parent_v2
from pheroos.governance._commit_evidence_owner_v2.contracts import (
    COMMIT_EVIDENCE_GENESIS_SNAPSHOT_ROOT_V2,
    commit_evidence_stream_ref_v2,
)
from pheroos.governance._commit_evidence_owner_v2.operations import (
    rehydrate_commit_evidence_state_v2,
)
from pheroos.governance._commit_evidence_owner_v2.state_handle import (
    require_current_commit_evidence_state_v2,
)
from pheroos.governance._commit_gate_v2.common import (
    COMMIT_PERMISSION_GENESIS_SNAPSHOT_ROOT_V2,
    COMMIT_STOP_GENESIS_SNAPSHOT_ROOT_V2,
    commit_permission_stream_ref_v2,
    commit_stop_stream_ref_v2,
)
from pheroos.governance._commit_gate_v2.permission_operations import (
    rehydrate_commit_permission_state_v2,
    require_current_commit_permission_state_v2,
)
from pheroos.governance._commit_gate_v2.stop_operations import (
    rehydrate_commit_stop_state_v2,
    require_current_commit_stop_state_v2,
)
from pheroos.governance._commit_state_v2.contracts import (
    COMMIT_REPLAY_GENESIS_SNAPSHOT_ROOT_V2,
    commit_replay_stream_ref_v2,
)
from pheroos.governance._commit_state_v2.operations import (
    rehydrate_commit_replay_state_v2,
    require_current_commit_replay_state_v2,
)
from pheroos.governance._risk_policy import risk_policy_root
from pheroos.governance._risk_v2.contracts import (
    RISK_GENESIS_SNAPSHOT_ROOT_V2,
    risk_state_stream_ref_v2,
)
from pheroos.governance._risk_v2.operations import (
    rehydrate_risk_state_v2,
    require_current_risk_state_v2,
)
from pheroos.governance._support_v2.durable_context import durable_support_context_v2
from pheroos.governance._support_v2.membership_operations import (
    rehydrate_membership_state_v2,
    require_current_membership_state_v2,
)
from pheroos.governance._support_v2.membership_stream_contracts import (
    MEMBERSHIP_GENESIS_SNAPSHOT_ROOT_V2,
    membership_stream_ref_v2,
)
from pheroos.governance._support_v2.principal_verification_contracts import (
    PRINCIPAL_VERIFICATION_GENESIS_SNAPSHOT_ROOT_V2,
    principal_verification_stream_ref_v2,
)
from pheroos.governance._support_v2.principal_verification_operations import (
    rehydrate_principal_verification_set_state_v2,
    require_current_principal_verification_set_v2,
)
from pheroos.governance._support_v2.support_operations import (
    rehydrate_support_state_v2,
)
from pheroos.governance._support_v2.support_state_handle import (
    require_current_support_state_v2,
)
from pheroos.governance._support_v2.support_snapshot_contracts import (
    SUPPORT_GENESIS_SNAPSHOT_ROOT_V2,
)
from pheroos.governance._support_v2.support_stream_contracts import (
    support_stream_ref_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitPositionV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
)


def _canonical_genesis_inputs_v2(
    *,
    parent_state: object,
    manifest: ScopedProtocolManifestV2,
    profile: str,
) -> tuple[
    AuthorityDomainV2,
    CommitDecisionSnapshotV2,
    tuple[CommitDecisionDependencyV2, ...],
]:
    """Bind every current head while allowing any valid missing-role subset."""
    domain, parent, parent_dependency = _current_parent_v2(parent_state)
    policy = manifest.collective_commit_policy
    if policy is None:
        raise ValueError("commit decision manifest has no commit policy")
    if (
        parent.manifest_root != manifest.manifest_root
        or parent.profile != profile
        or parent.protocol_ref != manifest.id
    ):
        raise ValueError("commit decision missing-input manifest is mismatched")
    assurance = CommitAssurance(policy.assurance)
    support_context = durable_support_context_v2(
        manifest,
        profile=profile,
        assurance=assurance,
        target_ref=parent.target_ref,
    )
    reader = object.__getattribute__(parent_state, "_reader")
    if not isinstance(reader, GovernanceStateReaderV2):
        raise TypeError("commit decision parent StateReader is invalid")
    bindings: Sequence[tuple[CommitDecisionDependencyRoleV2, str, str]] = (
        (
            CommitDecisionDependencyRoleV2.REPLAY,
            commit_replay_stream_ref_v2(
                domain.scope_ref,
                parent.protocol_ref,
                parent.run_ref,
                parent.target_ref,
            ),
            COMMIT_REPLAY_GENESIS_SNAPSHOT_ROOT_V2,
        ),
        (
            CommitDecisionDependencyRoleV2.RISK,
            risk_state_stream_ref_v2(
                scope_ref=domain.scope_ref,
                profile=profile,
                assurance=assurance,
                manifest_root=manifest.manifest_root,
                commit_policy_root=parent.commit_policy_root,
                risk_policy_root=risk_policy_root(policy, profile=profile),
                protocol_ref=parent.protocol_ref,
                run_ref=parent.run_ref,
                target_ref=parent.target_ref,
            ),
            RISK_GENESIS_SNAPSHOT_ROOT_V2,
        ),
        (
            CommitDecisionDependencyRoleV2.MEMBERSHIP,
            membership_stream_ref_v2(
                scope_ref=domain.scope_ref,
                profile=profile,
                assurance=assurance,
                manifest_root=manifest.manifest_root,
                commit_policy_root=parent.commit_policy_root,
                membership_policy_root=support_context.membership_policy_root,
                protocol_ref=parent.protocol_ref,
                run_ref=parent.run_ref,
                target_ref=parent.target_ref,
            ),
            MEMBERSHIP_GENESIS_SNAPSHOT_ROOT_V2,
        ),
        (
            CommitDecisionDependencyRoleV2.PRINCIPAL_VERIFICATION,
            principal_verification_stream_ref_v2(
                scope_ref=domain.scope_ref,
                profile=profile,
                assurance=assurance,
                manifest_root=manifest.manifest_root,
                commit_policy_root=parent.commit_policy_root,
                verification_policy_root=support_context.principal_verification_policy_root,
                protocol_ref=parent.protocol_ref,
                run_ref=parent.run_ref,
                target_ref=parent.target_ref,
            ),
            PRINCIPAL_VERIFICATION_GENESIS_SNAPSHOT_ROOT_V2,
        ),
        (
            CommitDecisionDependencyRoleV2.SUPPORT,
            support_stream_ref_v2(
                scope_ref=domain.scope_ref,
                profile=profile,
                assurance=assurance,
                manifest_root=manifest.manifest_root,
                commit_policy_root=parent.commit_policy_root,
                protocol_ref=parent.protocol_ref,
                run_ref=parent.run_ref,
                target_ref=parent.target_ref,
            ),
            SUPPORT_GENESIS_SNAPSHOT_ROOT_V2,
        ),
        (
            CommitDecisionDependencyRoleV2.EVIDENCE,
            commit_evidence_stream_ref_v2(
                domain.scope_ref,
                parent.protocol_ref,
                parent.run_ref,
                parent.target_ref,
            ),
            COMMIT_EVIDENCE_GENESIS_SNAPSHOT_ROOT_V2,
        ),
        (
            CommitDecisionDependencyRoleV2.STOP,
            commit_stop_stream_ref_v2(
                domain.scope_ref,
                parent.protocol_ref,
                parent.run_ref,
                parent.target_ref,
            ),
            COMMIT_STOP_GENESIS_SNAPSHOT_ROOT_V2,
        ),
        (
            CommitDecisionDependencyRoleV2.PERMISSION,
            commit_permission_stream_ref_v2(
                domain.scope_ref,
                parent.protocol_ref,
                parent.run_ref,
                parent.target_ref,
            ),
            COMMIT_PERMISSION_GENESIS_SNAPSHOT_ROOT_V2,
        ),
    )
    dependencies: list[CommitDecisionDependencyV2] = []
    missing: list[CommitDecisionDependencyRoleV2] = []
    for role, stream_ref, snapshot_root in bindings:
        head = reader.load_head_v2(domain.scope_ref, stream_ref)
        if type(head) is not GovernanceHeadV2:
            raise TypeError("commit decision dependency head is invalid")
        if head.revision == 0:
            dependencies.append(
                _genesis_dependency_v2(
                    role,
                    stream_ref,
                    snapshot_root,
                    domain=domain,
                    observed=head,
                )
            )
            missing.append(role)
        else:
            dependencies.append(
                _committed_dependency_v2(
                    role,
                    stream_ref,
                    domain=domain,
                    reader=(reader),
                    parent=parent,
                    manifest=manifest,
                    profile=profile,
                    assurance=assurance,
                )
            )
    if not missing:
        raise ValueError("commit decision missing-input path has no missing dependency")
    return (
        domain,
        parent,
        canonical_commit_decision_dependencies_v2((parent_dependency, *dependencies)),
    )


def _genesis_dependency_v2(
    role: CommitDecisionDependencyRoleV2,
    stream_ref: str,
    snapshot_root: str,
    *,
    domain: AuthorityDomainV2,
    observed: GovernanceHeadV2,
) -> CommitDecisionDependencyV2:
    expected = GovernanceHeadV2.genesis(domain, stream_ref)
    if (
        type(observed) is not GovernanceHeadV2
        or observed.to_dict() != expected.to_dict()
    ):
        raise ValueError("commit decision dependency is no longer at genesis")
    return CommitDecisionDependencyV2(
        role=role,
        stream_ref=stream_ref,
        revision=0,
        transition_id="genesis",
        snapshot_root=snapshot_root,
        head_root=expected.head_root,
        receipt_root=_root("genesis-receipt", {"stream_ref": stream_ref}),
        observed_position=GovernanceCommitPositionV2.CURRENT,
    )


def _committed_dependency_v2(
    role: CommitDecisionDependencyRoleV2,
    stream_ref: str,
    *,
    domain: AuthorityDomainV2,
    reader: GovernanceStateReaderV2,
    parent: CommitDecisionSnapshotV2,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    assurance: CommitAssurance,
) -> CommitDecisionDependencyV2:
    payload = _current_request_payload_v2(reader, domain.scope_ref, stream_ref)
    state, snapshot = _rehydrate_current_owner_v2(
        role,
        payload,
        domain=domain,
        reader=reader,
    )
    _validate_committed_context_v2(
        snapshot,
        stream_ref=stream_ref,
        parent=parent,
        manifest=manifest,
        profile=profile,
        assurance=assurance,
    )
    head = reader.load_head_v2(domain.scope_ref, stream_ref)
    if type(head) is not GovernanceHeadV2:
        raise TypeError("commit decision dependency head is invalid")
    revision = cast(int, getattr(snapshot, "revision"))
    transition_id = cast(str, getattr(snapshot, "transition_id"))
    snapshot_root = cast(str, getattr(snapshot, "snapshot_root"))
    receipt_root = cast(str, getattr(state, "receipt_root"))
    if (
        cast(str, getattr(state, "stream_ref")) != stream_ref
        or head.revision != revision
        or head.transition_id != transition_id
    ):
        raise ValueError("commit decision committed dependency is not current")
    return CommitDecisionDependencyV2(
        role=role,
        stream_ref=stream_ref,
        revision=revision,
        transition_id=transition_id,
        snapshot_root=snapshot_root,
        head_root=head.head_root,
        receipt_root=receipt_root,
        observed_position=GovernanceCommitPositionV2.CURRENT,
    )


def _current_request_payload_v2(
    reader: GovernanceStateReaderV2,
    scope_ref: str,
    stream_ref: str,
) -> object:
    records = reader.load_state_v2(scope_ref, stream_ref)
    if not isinstance(records, Mapping) or "request" not in records:
        raise ValueError("commit decision dependency state omits its request")
    return records["request"]


def _rehydrate_current_owner_v2(
    role: CommitDecisionDependencyRoleV2,
    payload: object,
    *,
    domain: AuthorityDomainV2,
    reader: GovernanceStateReaderV2,
) -> tuple[object, object]:
    if role is CommitDecisionDependencyRoleV2.REPLAY:
        replay_state = rehydrate_commit_replay_state_v2(
            payload, domain=domain, state_reader=reader
        )
        return replay_state, require_current_commit_replay_state_v2(replay_state)
    if role is CommitDecisionDependencyRoleV2.RISK:
        risk_state = rehydrate_risk_state_v2(
            payload, domain=domain, state_reader=reader
        )
        return risk_state, require_current_risk_state_v2(risk_state)
    if role is CommitDecisionDependencyRoleV2.MEMBERSHIP:
        membership_state = rehydrate_membership_state_v2(
            payload, domain=domain, state_reader=reader
        )
        return membership_state, require_current_membership_state_v2(membership_state)
    if role is CommitDecisionDependencyRoleV2.PRINCIPAL_VERIFICATION:
        verification_state = rehydrate_principal_verification_set_state_v2(
            payload, domain=domain, state_reader=reader
        )
        return (
            verification_state,
            require_current_principal_verification_set_v2(verification_state),
        )
    if role is CommitDecisionDependencyRoleV2.SUPPORT:
        support_state = rehydrate_support_state_v2(
            payload, domain=domain, state_reader=reader
        )
        return support_state, require_current_support_state_v2(support_state)
    if role is CommitDecisionDependencyRoleV2.EVIDENCE:
        evidence_state = rehydrate_commit_evidence_state_v2(
            payload, domain=domain, state_reader=reader
        )
        return evidence_state, require_current_commit_evidence_state_v2(evidence_state)
    if role is CommitDecisionDependencyRoleV2.STOP:
        stop_state = rehydrate_commit_stop_state_v2(
            payload, domain=domain, state_reader=reader
        )
        return stop_state, require_current_commit_stop_state_v2(stop_state)
    if role is CommitDecisionDependencyRoleV2.PERMISSION:
        permission_state = rehydrate_commit_permission_state_v2(
            payload, domain=domain, state_reader=reader
        )
        return permission_state, require_current_commit_permission_state_v2(
            permission_state
        )
    raise ValueError("commit decision missing-input dependency role is unsupported")


def _validate_committed_context_v2(
    snapshot: object,
    *,
    stream_ref: str,
    parent: CommitDecisionSnapshotV2,
    manifest: ScopedProtocolManifestV2,
    profile: str,
    assurance: CommitAssurance,
) -> None:
    observed = tuple(
        getattr(snapshot, field)
        for field in (
            "domain_root",
            "scope_ref",
            "manifest_root",
            "commit_policy_root",
            "profile",
            "assurance",
            "protocol_ref",
            "run_ref",
            "target_ref",
            "stream_ref",
        )
    )
    expected = (
        parent.domain_root,
        parent.scope_ref,
        manifest.manifest_root,
        parent.commit_policy_root,
        profile,
        assurance,
        parent.protocol_ref,
        parent.run_ref,
        parent.target_ref,
        stream_ref,
    )
    if observed != expected:
        raise ValueError("commit decision committed dependency context is mismatched")


__all__: tuple[str, ...] = ()
