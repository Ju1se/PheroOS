"""Owner-neutral verified finality consumption for Commit Decision v2."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._commit_decision_v2.common import _require_root, _root
from pheroos.governance._commit_decision_v2.dependencies import (
    CommitDecisionDependencyV2,
)
from pheroos.governance._commit_decision_v2.enums import (
    CommitDecisionDependencyRoleV2,
)
from pheroos.governance._commit_decision_v2.snapshot import CommitDecisionSnapshotV2
from pheroos.governance._commit_finality_v2 import (
    CommitFinalityOwnerV2,
    CommitFinalityProjectionV2,
    _verified_commit_finality_input_material_v2,
    commit_finality_owner_genesis_snapshot_root_v2,
    commit_finality_owner_stream_ref_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceHeadV2,
    GovernanceStateReaderV2,
)


@dataclass(frozen=True, slots=True)
class _CommitDecisionFinalityInputV2:
    projection: CommitFinalityProjectionV2 | None
    dependency: CommitDecisionDependencyV2
    inclusion_root: str
    input_root: str


def _optional_verified_finality_input_v2(
    verified_finality_input: object | None,
    *,
    parent_state: object,
    parent: CommitDecisionSnapshotV2,
    current_step: int,
) -> _CommitDecisionFinalityInputV2 | None:
    if parent.seal is None:
        if verified_finality_input is not None:
            raise ValueError("commit finality input requires a sealed decision")
        return None
    expected = {
        CommitAssurance.CERTIFIED: (
            CommitFinalityOwnerV2.CERTIFICATE,
            CommitDecisionDependencyRoleV2.CERTIFICATE,
        ),
        CommitAssurance.DISTRIBUTED: (
            CommitFinalityOwnerV2.DISTRIBUTED,
            CommitDecisionDependencyRoleV2.DISTRIBUTED,
        ),
    }.get(parent.assurance)
    if expected is None:
        if verified_finality_input is not None:
            raise ValueError("commit finality owner cannot satisfy this assurance")
        return None
    if verified_finality_input is None:
        return _observed_finality_input_v2(
            parent_state,
            parent=parent,
            owner=expected[0],
            role=expected[1],
        )
    material = _verified_commit_finality_input_material_v2(verified_finality_input)
    projection = material.projection
    if projection.owner is not expected[0]:
        raise ValueError("commit finality owner cannot satisfy this assurance")
    expected_stream = commit_finality_owner_stream_ref_v2(
        projection.owner,
        parent.scope_ref,
        parent.protocol_ref,
        parent.run_ref,
        parent.target_ref,
    )
    if projection.stream_ref != expected_stream:
        raise ValueError("commit finality owner stream is not canonical")
    if projection.verified_at_step != current_step:
        raise ValueError("commit finality input is not from the current step")
    dependency = CommitDecisionDependencyV2(
        role=expected[1],
        stream_ref=projection.stream_ref,
        revision=projection.revision,
        transition_id=projection.transition_id,
        snapshot_root=projection.snapshot_root,
        head_root=projection.head_root,
        receipt_root=projection.receipt_root,
        observed_position=GovernanceCommitPositionV2.CURRENT,
    )
    return _CommitDecisionFinalityInputV2(
        projection=CommitFinalityProjectionV2.from_dict(projection.to_dict()),
        dependency=dependency,
        inclusion_root=material.owner_inclusion_root,
        input_root=material.input_root,
    )


def _observed_finality_input_v2(
    parent_state: object,
    *,
    parent: CommitDecisionSnapshotV2,
    owner: CommitFinalityOwnerV2,
    role: CommitDecisionDependencyRoleV2,
) -> _CommitDecisionFinalityInputV2:
    """CAS-bind the current owner without treating its bytes as finality.

    This is deliberately weaker than consuming an opaque verified finality
    handle.  A non-genesis owner is observed only as generic committed Store
    state, so Decision may keep progressing but can never infer VERIFIED,
    CONFLICT, or any other owner status from it.
    """

    reader = object.__getattribute__(parent_state, "_reader")
    domain = object.__getattribute__(parent_state, "_domain")
    if not isinstance(reader, GovernanceStateReaderV2):
        raise TypeError("commit finality observation requires the parent StateReader")
    if type(domain) is not AuthorityDomainV2:
        raise TypeError("commit finality observation requires the parent domain")
    stream_ref = commit_finality_owner_stream_ref_v2(
        owner,
        parent.scope_ref,
        parent.protocol_ref,
        parent.run_ref,
        parent.target_ref,
    )
    expected = GovernanceHeadV2.genesis(domain, stream_ref)
    try:
        head = reader.load_head_v2(parent.scope_ref, stream_ref)
    except KeyError as exc:
        raise ValueError("commit finality owner head is unavailable") from exc
    if type(head) is not GovernanceHeadV2:
        raise TypeError("commit finality owner head is invalid")
    head = GovernanceHeadV2.from_dict(head.to_dict())
    if (
        head.domain_root != domain.domain_root
        or head.scope_ref != parent.scope_ref
        or head.stream_ref != stream_ref
    ):
        raise ValueError("commit finality owner head is cross-bound")
    if head.revision == 0:
        if head.to_dict() != expected.to_dict():
            raise ValueError("commit finality owner genesis head is invalid")
        snapshot_root = commit_finality_owner_genesis_snapshot_root_v2(owner)
        receipt_root = _root("genesis-receipt", {"stream_ref": stream_ref})
    else:
        snapshot_root, receipt_root = _committed_owner_observation_v2(
            reader,
            domain=domain,
            head=head,
        )
    dependency = CommitDecisionDependencyV2(
        role=role,
        stream_ref=stream_ref,
        revision=head.revision,
        transition_id=head.transition_id,
        snapshot_root=snapshot_root,
        head_root=head.head_root,
        receipt_root=receipt_root,
        observed_position=GovernanceCommitPositionV2.CURRENT,
    )
    return _CommitDecisionFinalityInputV2(
        projection=None,
        dependency=dependency,
        inclusion_root="",
        input_root="",
    )


def _committed_owner_observation_v2(
    reader: GovernanceStateReaderV2,
    *,
    domain: AuthorityDomainV2,
    head: GovernanceHeadV2,
) -> tuple[str, str]:
    """Read one exact current commit without decoding owner status semantics."""

    try:
        view = reader.load_commit_view_v2(
            head.scope_ref,
            head.stream_ref,
            head.transition_id,
        )
    except KeyError as exc:
        raise ValueError("commit finality owner commit view is unavailable") from exc
    if type(view) is not GovernanceCommitViewV2:
        raise TypeError("commit finality owner commit view is invalid")
    canonical = GovernanceCommitViewV2.from_dict(view.to_dict())
    committed = canonical.committed_transition
    position = canonical.position_observation
    if (
        canonical.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or committed is None
        or position is None
    ):
        raise ValueError("commit finality owner commit view is not committed")
    receipt = committed.receipt
    if (
        canonical.domain_root != domain.domain_root
        or canonical.scope_ref != head.scope_ref
        or canonical.stream_ref != head.stream_ref
        or canonical.transition_id != head.transition_id
        or canonical.observed_revision != head.revision
        or canonical.observed_head_root != head.head_root
        or position.position is not GovernanceCommitPositionV2.CURRENT
        or position.stream_ref != head.stream_ref
        or position.transition_id != head.transition_id
        or position.observed_revision != head.revision
        or position.observed_head_root != head.head_root
        or position.receipt_root != receipt.receipt_root
        or receipt.domain_root != domain.domain_root
        or receipt.scope_ref != head.scope_ref
        or receipt.stream_ref != head.stream_ref
        or receipt.transition_id != head.transition_id
        or receipt.revision != head.revision
        or receipt.head_root != head.head_root
        or receipt.state_root != head.state_root
        or receipt.batch_root != head.batch_root
        or receipt.parent_root != head.parent_root
    ):
        raise ValueError("commit finality owner commit view is not the current head")
    transition = committed.batch.transition
    if transition is None:
        raise ValueError("commit finality owner commit has no state transition")
    snapshot_root = _restricted_owner_snapshot_root_v2(
        transition.state_records,
        domain=domain,
        head=head,
    )
    return snapshot_root, receipt.receipt_root


def _restricted_owner_snapshot_root_v2(
    state_records: object,
    *,
    domain: AuthorityDomainV2,
    head: GovernanceHeadV2,
) -> str:
    """Extract only the generic snapshot identity, never owner status fields."""

    if not isinstance(state_records, Mapping):
        raise TypeError("commit finality owner state records are invalid")
    state = cast(Mapping[object, object], state_records)
    required = frozenset(
        {
            "schema",
            "domain_root",
            "scope_ref",
            "stream_ref",
            "transition_id",
            "snapshot_root",
            "snapshot",
        }
    )
    if any(type(key) is not str for key in state) or not required.issubset(state):
        raise ValueError("commit finality owner state records are incomplete")
    snapshot_root = _require_root(
        state["snapshot_root"],
        "commit finality owner snapshot_root",
    )
    snapshot_value = state["snapshot"]
    if not isinstance(snapshot_value, Mapping):
        raise TypeError("commit finality owner snapshot record is invalid")
    snapshot = cast(Mapping[object, object], snapshot_value)
    snapshot_fields = frozenset(
        {
            "domain_root",
            "scope_ref",
            "stream_ref",
            "transition_id",
            "revision",
            "snapshot_root",
        }
    )
    if any(type(key) is not str for key in snapshot) or not snapshot_fields.issubset(
        snapshot
    ):
        raise ValueError("commit finality owner snapshot binding is incomplete")
    if (
        state["domain_root"] != domain.domain_root
        or state["scope_ref"] != head.scope_ref
        or state["stream_ref"] != head.stream_ref
        or state["transition_id"] != head.transition_id
        or snapshot["domain_root"] != domain.domain_root
        or snapshot["scope_ref"] != head.scope_ref
        or snapshot["stream_ref"] != head.stream_ref
        or snapshot["transition_id"] != head.transition_id
        or type(snapshot["revision"]) is not int
        or snapshot["revision"] != head.revision
        or snapshot["snapshot_root"] != snapshot_root
    ):
        raise ValueError("commit finality owner snapshot is cross-bound")
    return snapshot_root


__all__: tuple[str, ...] = ()
