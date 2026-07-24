"""Store-current upstream authority material for Commit Gate v2 sources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from pheroos.protocol.authority_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceReadPreconditionV2,
)
from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance._commit_state_v2.contracts import (
    CommitReplayAdvanceRequestV2,
    CommitReplaySnapshotV2,
)
from pheroos.governance._commit_state_v2.operations import (
    VerifiedCommitReplayStateV2,
    require_current_commit_replay_state_v2,
)
from pheroos.governance._commit_gate_v2.dependency_contracts import (
    CommitGateDependenciesV2,
)
from pheroos.governance._risk_v2.contracts import (
    RiskStateAdvanceRequestV2,
    RiskStateSnapshotV2,
)
from pheroos.governance._risk_v2.operations import (
    VerifiedRiskStateV2,
    require_current_risk_state_v2,
)
from pheroos.governance._support_v2.membership_operations import (
    VerifiedMembershipStateV2,
)
from pheroos.governance._support_v2.membership_contracts import MembershipSnapshotV2
from pheroos.governance._support_v2.support_state_access import (
    _membership_parent_authority_material_v2,
    _support_parent,
)
from pheroos.governance._support_v2.support_state_handle import VerifiedSupportStateV2
from pheroos.governance._support_v2.support_state_contracts import SupportSnapshotV2
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
)


@dataclass(frozen=True, slots=True)
class _DependencyMaterialV2:
    dependencies: CommitGateDependenciesV2
    preconditions: tuple[GovernanceReadPreconditionV2, ...]
    replay: CommitReplaySnapshotV2
    risk: RiskStateSnapshotV2
    membership: MembershipSnapshotV2
    support: SupportSnapshotV2


type _DependencySnapshotV2 = (
    CommitReplaySnapshotV2
    | RiskStateSnapshotV2
    | MembershipSnapshotV2
    | SupportSnapshotV2
)
type _DependencyRequestV2 = CommitReplayAdvanceRequestV2 | RiskStateAdvanceRequestV2
type _DependencyRequestTypeV2 = (
    type[CommitReplayAdvanceRequestV2] | type[RiskStateAdvanceRequestV2]
)


def _collect_dependency_material_v2(
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
) -> _DependencyMaterialV2:
    replay, replay_precondition = _current_replay(commit_replay_state)
    risk, risk_precondition = _current_risk(risk_state)
    (
        membership,
        membership_precondition,
        verification_precondition,
    ) = _current_membership(membership_state)
    support, support_precondition = _current_support(support_state)
    snapshots: tuple[tuple[str, _DependencySnapshotV2], ...] = (
        ("replay", replay),
        ("risk", risk),
        ("membership", membership),
        ("support", support),
    )
    for name, snapshot in snapshots:
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
            current_step=current_step,
        )
    dependencies = CommitGateDependenciesV2(
        replay_stream_ref=replay.stream_ref,
        replay_revision=replay.revision,
        replay_transition_id=replay.transition_id,
        replay_snapshot_root=replay.snapshot_root,
        replay_head_root=replay_precondition.expected_root,
        risk_stream_ref=risk.stream_ref,
        risk_revision=risk.revision,
        risk_transition_id=risk.transition_id,
        risk_snapshot_root=risk.snapshot_root,
        risk_head_root=risk_precondition.expected_root,
        verification_stream_ref=membership.verification_stream_ref,
        verification_revision=membership.verification_revision,
        verification_transition_id=membership.verification_transition_id,
        verification_snapshot_root=membership.verification_snapshot_root,
        verification_head_root=verification_precondition.expected_root,
        membership_stream_ref=membership.stream_ref,
        membership_revision=membership.revision,
        membership_transition_id=membership.transition_id,
        membership_snapshot_root=membership.snapshot_root,
        membership_head_root=membership_precondition.expected_root,
        support_stream_ref=support.stream_ref,
        support_revision=support.revision,
        support_transition_id=support.transition_id,
        support_snapshot_root=support.snapshot_root,
        support_head_root=support_precondition.expected_root,
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
    return _DependencyMaterialV2(
        dependencies=dependencies,
        preconditions=preconditions,
        replay=replay,
        risk=risk,
        membership=membership,
        support=support,
    )


def _current_replay(
    state: object,
) -> tuple[CommitReplaySnapshotV2, GovernanceReadPreconditionV2]:
    if type(state) is not VerifiedCommitReplayStateV2:
        raise TypeError("commit gate requires verified Commit Replay v2 state")
    snapshot = require_current_commit_replay_state_v2(state)
    head = _current_head_from_handle(
        state,
        expected_request_type=CommitReplayAdvanceRequestV2,
        expected_revision=snapshot.revision,
        expected_transition_id=snapshot.transition_id,
    )
    return snapshot, _precondition(head)


def _current_risk(
    state: object,
) -> tuple[RiskStateSnapshotV2, GovernanceReadPreconditionV2]:
    if type(state) is not VerifiedRiskStateV2:
        raise TypeError("commit gate requires verified Risk v2 state")
    snapshot = require_current_risk_state_v2(state)
    head = _current_head_from_handle(
        state,
        expected_request_type=RiskStateAdvanceRequestV2,
        expected_revision=snapshot.revision,
        expected_transition_id=snapshot.transition_id,
    )
    return snapshot, _precondition(head)


def _current_membership(
    state: object,
) -> tuple[
    MembershipSnapshotV2,
    GovernanceReadPreconditionV2,
    GovernanceReadPreconditionV2,
]:
    if type(state) is not VerifiedMembershipStateV2:
        raise TypeError("commit gate requires verified Membership v2 state")
    return _membership_parent_authority_material_v2(state)


def _current_support(
    state: object,
) -> tuple[SupportSnapshotV2, GovernanceReadPreconditionV2]:
    if type(state) is not VerifiedSupportStateV2:
        raise TypeError("commit gate requires verified Support v2 state")
    return _support_parent(state)


def _current_head_from_handle(
    state: object,
    *,
    expected_request_type: _DependencyRequestTypeV2,
    expected_revision: int,
    expected_transition_id: str,
) -> GovernanceHeadV2:
    try:
        reader = object.__getattribute__(state, "_reader")
        domain = object.__getattribute__(state, "_domain")
        raw_request = object.__getattribute__(state, "_request")
    except AttributeError as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/dependency_state",
        ) from exc
    if (
        type(domain) is not AuthorityDomainV2
        or type(raw_request) is not expected_request_type
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/dependency_state",
        )
    request = cast(_DependencyRequestV2, raw_request)
    try:
        conforms = isinstance(reader, GovernanceStateReaderV2)
    except Exception as exc:
        raise TypeError("commit gate dependency StateReader v2 is invalid") from exc
    if not conforms:
        raise TypeError("commit gate dependency StateReader v2 is invalid")
    try:
        head = cast(GovernanceStateReaderV2, reader).load_head_v2(
            request.scope_ref, request.stream_ref
        )
    except KeyError as exc:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
            "/scope_ref",
        ) from exc
    if type(head) is not GovernanceHeadV2:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/dependency_state/head",
        )
    detached = GovernanceHeadV2.from_dict(head.to_dict())
    if (
        detached.domain_root != domain.domain_root
        or detached.scope_ref != domain.scope_ref
        or detached.stream_ref != request.stream_ref
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/dependency_state/head",
        )
    if (
        detached.revision != expected_revision
        or detached.transition_id != expected_transition_id
    ):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            "/dependency_state/position",
        )
    return detached


def _precondition(head: GovernanceHeadV2) -> GovernanceReadPreconditionV2:
    return GovernanceReadPreconditionV2(
        stream_ref=head.stream_ref,
        expected_revision=head.revision,
        expected_root=head.head_root,
    )


def _validate_snapshot_context(
    name: str,
    snapshot: _DependencySnapshotV2,
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
) -> None:
    dependency_epoch = (
        (snapshot).epoch
        if type(snapshot) is RiskStateSnapshotV2
        else cast(
            CommitReplaySnapshotV2 | MembershipSnapshotV2 | SupportSnapshotV2,
            snapshot,
        ).observed_epoch
    )
    pairs = (
        ("domain_root", domain_root),
        ("scope_ref", scope_ref),
        ("manifest_root", manifest_root),
        ("commit_policy_root", commit_policy_root),
        ("profile", profile),
        ("assurance", assurance),
        ("protocol_ref", protocol_ref),
        ("run_ref", run_ref),
        ("target_ref", target_ref),
    )
    if any(getattr(snapshot, field, None) != value for field, value in pairs):
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            f"/{name}_state/context",
        )
    if dependency_epoch > observed_epoch:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            f"/{name}_state/observed_epoch",
        )
    dependency_step = (
        (snapshot).issued_at_step
        if type(snapshot) is MembershipSnapshotV2
        else cast(
            CommitReplaySnapshotV2 | RiskStateSnapshotV2 | SupportSnapshotV2,
            snapshot,
        ).current_step
    )
    if dependency_step > current_step:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            f"/{name}_state/current_step",
        )
    if name == "risk":
        if type(snapshot) is not RiskStateSnapshotV2:
            raise GovernanceAuthorityBindingErrorV2(
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/risk_state/context",
            )
        assessment = snapshot.assessment
        if not assessment.issued_at_step <= current_step < assessment.expires_at_step:
            raise GovernanceAuthorityBindingErrorV2(
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/risk_state/expires_at_step",
            )
    if name == "membership":
        if type(snapshot) is not MembershipSnapshotV2 or not (
            snapshot.issued_at_step <= current_step < snapshot.expires_at_step
        ):
            raise GovernanceAuthorityBindingErrorV2(
                AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
                "/membership_state/expires_at_step",
            )


__all__: tuple[str, ...] = ()
