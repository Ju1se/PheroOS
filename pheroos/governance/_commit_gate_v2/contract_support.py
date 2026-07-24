"""Internal validation shared by the two Commit Gate v2 portable ledgers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2
from pheroos.protocol.commit_models import CommitAssurance
from pheroos.governance._authority_store_v2_contracts.foundation import _require_root
from pheroos.governance._commit_gate_v2.common import (
    COMMIT_GATE_GENESIS_TRANSITION_ID_V2,
    _require_count,
    _require_profile,
    _require_text,
)
from pheroos.governance._commit_gate_v2.dependency_contracts import (
    CommitGateDependenciesV2,
    commit_gate_evaluation_context_root_v2,
)


if TYPE_CHECKING:

    class _GateSnapshotShapeV2(Protocol):
        @property
        def canonical_version(self) -> str: ...
        @property
        def domain_root(self) -> str: ...
        @property
        def scope_ref(self) -> str: ...
        @property
        def manifest_root(self) -> str: ...
        @property
        def commit_policy_root(self) -> str: ...
        @property
        def policy_root(self) -> str: ...
        @property
        def profile(self) -> str: ...
        @property
        def assurance(self) -> CommitAssurance: ...
        @property
        def protocol_ref(self) -> str: ...
        @property
        def run_ref(self) -> str: ...
        @property
        def target_ref(self) -> str: ...
        @property
        def observed_epoch(self) -> int: ...
        @property
        def current_step(self) -> int: ...
        @property
        def stream_ref(self) -> str: ...
        @property
        def transition_id(self) -> str: ...
        @property
        def revision(self) -> int: ...
        @property
        def parent_revision(self) -> int: ...
        @property
        def parent_transition_id(self) -> str: ...
        @property
        def parent_snapshot_root(self) -> str: ...
        @property
        def mutation_issuer_ref(self) -> str: ...
        @property
        def issued_at_step(self) -> int: ...
        @property
        def expires_at_step(self) -> int: ...
        @property
        def dependencies(self) -> CommitGateDependenciesV2: ...
        @property
        def evaluation_context_root(self) -> str: ...
        @property
        def snapshot_root(self) -> str: ...
else:

    class _GateSnapshotShapeV2(Protocol):
        pass


def _validate_common_snapshot(
    snapshot: _GateSnapshotShapeV2,
    *,
    expected_policy_root: str,
    expected_stream_ref: str,
    expected_transition_id: str,
    genesis_snapshot_root: str,
) -> None:
    if snapshot.canonical_version != AUTHORITY_CANONICAL_VERSION_V2:
        raise ValueError("commit gate canonical version is unsupported")
    _validate_root_and_text_fields(snapshot)
    _validate_counts_and_parent(snapshot, genesis_snapshot_root)
    _validate_derived_bindings(
        snapshot,
        expected_policy_root=expected_policy_root,
        expected_stream_ref=expected_stream_ref,
        expected_transition_id=expected_transition_id,
    )


def _validate_root_and_text_fields(snapshot: _GateSnapshotShapeV2) -> None:
    for label, value in (
        ("domain_root", snapshot.domain_root),
        ("manifest_root", snapshot.manifest_root),
        ("commit_policy_root", snapshot.commit_policy_root),
        ("policy_root", snapshot.policy_root),
        ("parent_snapshot_root", snapshot.parent_snapshot_root),
        ("evaluation_context_root", snapshot.evaluation_context_root),
    ):
        _require_root(value, f"commit gate snapshot {label}")
    for label, value in (
        ("scope_ref", snapshot.scope_ref),
        ("protocol_ref", snapshot.protocol_ref),
        ("run_ref", snapshot.run_ref),
        ("target_ref", snapshot.target_ref),
        ("stream_ref", snapshot.stream_ref),
        ("transition_id", snapshot.transition_id),
        ("parent_transition_id", snapshot.parent_transition_id),
        ("mutation_issuer_ref", snapshot.mutation_issuer_ref),
    ):
        _require_text(value, f"commit gate snapshot {label}")
    _require_profile(snapshot.profile, snapshot.assurance, "commit gate snapshot")


def _validate_counts_and_parent(
    snapshot: _GateSnapshotShapeV2,
    genesis_snapshot_root: str,
) -> None:
    for label, value, minimum in (
        ("observed_epoch", snapshot.observed_epoch, 0),
        ("current_step", snapshot.current_step, 0),
        ("revision", snapshot.revision, 1),
        ("parent_revision", snapshot.parent_revision, 0),
        ("issued_at_step", snapshot.issued_at_step, 0),
        ("expires_at_step", snapshot.expires_at_step, 0),
    ):
        _require_count(value, f"commit gate snapshot {label}", minimum=minimum)
    if type(snapshot.dependencies) is not CommitGateDependenciesV2:
        raise TypeError("commit gate snapshot requires exact dependencies v2")
    if not snapshot.issued_at_step <= snapshot.current_step < snapshot.expires_at_step:
        raise ValueError("commit gate snapshot is not fresh at current_step")
    if snapshot.parent_revision != snapshot.revision - 1:
        raise ValueError("commit gate parent revision is not contiguous")
    if snapshot.revision == 1:
        if (
            snapshot.parent_transition_id != COMMIT_GATE_GENESIS_TRANSITION_ID_V2
            or snapshot.parent_snapshot_root != genesis_snapshot_root
        ):
            raise ValueError("commit gate genesis parent is invalid")
    elif snapshot.parent_transition_id == COMMIT_GATE_GENESIS_TRANSITION_ID_V2:
        raise ValueError("commit gate successor cannot use genesis transition")


def _validate_derived_bindings(
    snapshot: _GateSnapshotShapeV2,
    *,
    expected_policy_root: str,
    expected_stream_ref: str,
    expected_transition_id: str,
) -> None:
    if snapshot.policy_root != expected_policy_root:
        raise ValueError("commit gate policy_root is mismatched")
    if (
        snapshot.stream_ref != expected_stream_ref
        or snapshot.transition_id != expected_transition_id
    ):
        raise ValueError("commit gate stream or transition identity is mismatched")
    expected_context = commit_gate_evaluation_context_root_v2(
        domain_root=snapshot.domain_root,
        scope_ref=snapshot.scope_ref,
        manifest_root=snapshot.manifest_root,
        commit_policy_root=snapshot.commit_policy_root,
        profile=snapshot.profile,
        assurance=snapshot.assurance,
        protocol_ref=snapshot.protocol_ref,
        run_ref=snapshot.run_ref,
        target_ref=snapshot.target_ref,
        observed_epoch=snapshot.observed_epoch,
        current_step=snapshot.current_step,
        dependencies=snapshot.dependencies,
    )
    if snapshot.evaluation_context_root != expected_context:
        raise ValueError("commit gate evaluation_context_root is mismatched")


def _common_snapshot_body(snapshot: _GateSnapshotShapeV2) -> dict[str, object]:
    return {
        "canonical_version": snapshot.canonical_version,
        "domain_root": snapshot.domain_root,
        "scope_ref": snapshot.scope_ref,
        "manifest_root": snapshot.manifest_root,
        "commit_policy_root": snapshot.commit_policy_root,
        "policy_root": snapshot.policy_root,
        "profile": snapshot.profile,
        "assurance": snapshot.assurance.value,
        "protocol_ref": snapshot.protocol_ref,
        "run_ref": snapshot.run_ref,
        "target_ref": snapshot.target_ref,
        "observed_epoch": snapshot.observed_epoch,
        "current_step": snapshot.current_step,
        "stream_ref": snapshot.stream_ref,
        "transition_id": snapshot.transition_id,
        "revision": snapshot.revision,
        "parent_revision": snapshot.parent_revision,
        "parent_transition_id": snapshot.parent_transition_id,
        "parent_snapshot_root": snapshot.parent_snapshot_root,
        "mutation_issuer_ref": snapshot.mutation_issuer_ref,
        "issued_at_step": snapshot.issued_at_step,
        "expires_at_step": snapshot.expires_at_step,
        "dependencies": snapshot.dependencies.to_dict(),
        "evaluation_context_root": snapshot.evaluation_context_root,
    }


def _validate_successor_common(
    current: _GateSnapshotShapeV2,
    parent: _GateSnapshotShapeV2,
) -> None:
    immutable = (
        "domain_root",
        "scope_ref",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "stream_ref",
    )
    if any(getattr(current, field) != getattr(parent, field) for field in immutable):
        raise ValueError("commit gate successor changes its fixed stream binding")
    if (
        current.revision != parent.revision + 1
        or current.parent_revision != parent.revision
        or current.parent_transition_id != parent.transition_id
        or current.parent_snapshot_root != parent.snapshot_root
        or current.current_step < parent.current_step
        or current.observed_epoch < parent.observed_epoch
    ):
        raise ValueError("commit gate successor continuity is invalid")


__all__: tuple[str, ...] = ()
