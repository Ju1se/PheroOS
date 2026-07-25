"""Context-bound source proof and deterministic Commit Replay v2 projection."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import NoReturn, SupportsIndex, cast, final

from pheroos.protocol.commit_models import CommitAssurance

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _compute_root,
    _require_root,
)
from pheroos.governance._commit_state_v2.contracts import (
    COMMIT_REPLAY_GENESIS_SNAPSHOT_ROOT_V2,
    COMMIT_REPLAY_GENESIS_TRANSITION_ID_V2,
    CommitReplayAdvanceRequestV2,
    CommitReplayReceiptV2,
    CommitReplaySnapshotV2,
    canonical_commit_replay_receipts_v2,
    commit_replay_stream_ref_v2,
    commit_replay_transition_id_v2,
    _require_bounded_text,
    _require_count,
)


_SOURCE_VERSION_V2 = "pheroos-commit-replay-source-proof-v2"


@dataclass(frozen=True, slots=True)
class _CommitReplaySourceBindingV2:
    domain_root: str
    scope_ref: str
    manifest_root: str
    commit_policy_root: str
    profile: str
    assurance: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    observed_epoch: int
    advance_ref: str
    current_step: int
    parent_snapshot_root: str
    parent_transition_id: str
    parent_revision: int
    addition_roots: tuple[str, ...]
    request_root: str
    context_root: str

    def body(self) -> dict[str, object]:
        return {
            "version": _SOURCE_VERSION_V2,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "manifest_root": self.manifest_root,
            "commit_policy_root": self.commit_policy_root,
            "profile": self.profile,
            "assurance": self.assurance,
            "protocol_ref": self.protocol_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "observed_epoch": self.observed_epoch,
            "advance_ref": self.advance_ref,
            "current_step": self.current_step,
            "parent_snapshot_root": self.parent_snapshot_root,
            "parent_transition_id": self.parent_transition_id,
            "parent_revision": self.parent_revision,
            "addition_roots": list(self.addition_roots),
            "request_root": self.request_root,
        }


@dataclass(frozen=True, slots=True)
class _ParentMaterialV2:
    receipts: tuple[CommitReplayReceiptV2, ...]
    snapshot_root: str
    transition_id: str
    revision: int
    initialized_at_step: int


@final
class VerifiedCommitReplaySourceV2:
    """Non-portable proof binding one prepared advance to its exact context."""

    __slots__ = ("_binding", "_request")

    def __new__(cls, *_args: object, **_kwargs: object) -> VerifiedCommitReplaySourceV2:
        raise TypeError("VerifiedCommitReplaySourceV2 cannot be constructed directly")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedCommitReplaySourceV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedCommitReplaySourceV2 is immutable")

    def __copy__(self) -> VerifiedCommitReplaySourceV2:
        _verified_source(self)
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> VerifiedCommitReplaySourceV2:
        _verified_source(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedCommitReplaySourceV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedCommitReplaySourceV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("VerifiedCommitReplaySourceV2 is not portable")

    def __repr__(self) -> str:
        return "<VerifiedCommitReplaySourceV2 redacted>"

    @property
    def context_root(self) -> str:
        return _verified_source(self)[1].context_root


def prepare_commit_replay_advance_v2(
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
    advance_ref: str,
    current_step: int,
    receipt_additions: tuple[CommitReplayReceiptV2, ...],
    parent_snapshot: CommitReplaySnapshotV2 | None = None,
) -> tuple[CommitReplayAdvanceRequestV2, VerifiedCommitReplaySourceV2]:
    """Prepare a complete snapshot and its exact non-portable source proof."""

    _validate_prepare_context(
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
        advance_ref=advance_ref,
        current_step=current_step,
    )
    additions = _validate_additions(receipt_additions, target_ref=target_ref)
    parent = _prepare_parent_material(
        parent_snapshot,
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
    combined = canonical_commit_replay_receipts_v2((*parent.receipts, *additions))
    _require_exact_additions(
        parent.receipts, additions, combined, parent_revision=parent.revision
    )

    stream_ref = commit_replay_stream_ref_v2(
        scope_ref, protocol_ref, run_ref, target_ref
    )
    transition_id = commit_replay_transition_id_v2(stream_ref, advance_ref)
    snapshot = CommitReplaySnapshotV2(
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
        stream_ref=stream_ref,
        advance_ref=advance_ref,
        transition_id=transition_id,
        revision=parent.revision + 1,
        initialized_at_step=parent.initialized_at_step,
        current_step=current_step,
        parent_revision=parent.revision,
        parent_transition_id=parent.transition_id,
        parent_snapshot_root=parent.snapshot_root,
        receipts=combined,
    )
    request = CommitReplayAdvanceRequestV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        target_ref=target_ref,
        observed_epoch=observed_epoch,
        advance_ref=advance_ref,
        transition_id=transition_id,
        stream_ref=stream_ref,
        snapshot=snapshot,
    )
    return request, _issue_source(request, parent.receipts)


def _validate_prepare_context(
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
    advance_ref: str,
    current_step: int,
) -> None:
    _require_root(domain_root, "commit replay source domain_root")
    _require_root(manifest_root, "commit replay source manifest_root")
    _require_root(commit_policy_root, "commit replay source commit_policy_root")
    for label, value in (
        ("scope_ref", scope_ref),
        ("profile", profile),
        ("protocol_ref", protocol_ref),
        ("run_ref", run_ref),
        ("target_ref", target_ref),
        ("advance_ref", advance_ref),
    ):
        _require_bounded_text(value, f"commit replay source {label}")
    _require_count(observed_epoch, "commit replay source observed_epoch")
    _require_count(current_step, "commit replay source current_step")
    if type(assurance) is not CommitAssurance:
        raise TypeError("commit replay source assurance is invalid")


def _validate_additions(
    receipt_additions: tuple[CommitReplayReceiptV2, ...],
    *,
    target_ref: str,
) -> tuple[CommitReplayReceiptV2, ...]:
    if type(receipt_additions) is not tuple:
        raise TypeError("commit replay source additions must be an exact tuple")
    additions = canonical_commit_replay_receipts_v2(receipt_additions)
    if any(item.target_ref != target_ref for item in additions):
        raise ValueError("commit replay addition target is mismatched")
    return additions


def _prepare_parent_material(
    parent_snapshot: CommitReplaySnapshotV2 | None,
    **context: object,
) -> _ParentMaterialV2:
    if parent_snapshot is None:
        return _ParentMaterialV2(
            receipts=(),
            snapshot_root=COMMIT_REPLAY_GENESIS_SNAPSHOT_ROOT_V2,
            transition_id=COMMIT_REPLAY_GENESIS_TRANSITION_ID_V2,
            revision=0,
            initialized_at_step=cast(int, context["current_step"]),
        )
    if type(parent_snapshot) is not CommitReplaySnapshotV2:
        raise TypeError("commit replay parent must be exact snapshot v2")
    bindings = tuple(
        (name, context[name])
        for name in (
            "domain_root",
            "scope_ref",
            "manifest_root",
            "commit_policy_root",
            "profile",
            "assurance",
            "protocol_ref",
            "run_ref",
            "target_ref",
        )
    )
    if any(getattr(parent_snapshot, name) != value for name, value in bindings):
        raise ValueError("commit replay parent context is mismatched")
    if cast(int, context["current_step"]) < parent_snapshot.current_step:
        raise ValueError("commit replay current_step cannot move backwards")
    if cast(int, context["observed_epoch"]) < parent_snapshot.observed_epoch:
        raise ValueError("commit replay observed_epoch cannot move backwards")
    return _ParentMaterialV2(
        receipts=cast(tuple[CommitReplayReceiptV2, ...], parent_snapshot.receipts),
        snapshot_root=parent_snapshot.snapshot_root,
        transition_id=parent_snapshot.transition_id,
        revision=parent_snapshot.revision,
        initialized_at_step=parent_snapshot.initialized_at_step,
    )


def _require_exact_additions(
    existing: tuple[CommitReplayReceiptV2, ...],
    additions: tuple[CommitReplayReceiptV2, ...],
    combined: tuple[CommitReplayReceiptV2, ...],
    *,
    parent_revision: int,
) -> None:
    existing_roots = {item.receipt_root for item in existing}
    effective_additions = tuple(
        item for item in combined if item.receipt_root not in existing_roots
    )
    if not effective_additions and parent_revision != 0:
        raise ValueError("commit replay advance contains no new receipt")
    if {item.receipt_root for item in effective_additions} != {
        item.receipt_root for item in additions
    }:
        raise ValueError("commit replay additions collide with existing receipts")


def _issue_source(
    request: CommitReplayAdvanceRequestV2,
    existing: tuple[CommitReplayReceiptV2, ...],
) -> VerifiedCommitReplaySourceV2:
    snapshot = request.snapshot
    existing_roots = {item.receipt_root for item in existing}
    effective_additions = tuple(
        item for item in snapshot.receipts if item.receipt_root not in existing_roots
    )
    binding = _CommitReplaySourceBindingV2(
        domain_root=snapshot.domain_root,
        scope_ref=snapshot.scope_ref,
        manifest_root=snapshot.manifest_root,
        commit_policy_root=snapshot.commit_policy_root,
        profile=snapshot.profile,
        assurance=snapshot.assurance.value,
        protocol_ref=snapshot.protocol_ref,
        run_ref=snapshot.run_ref,
        target_ref=snapshot.target_ref,
        observed_epoch=snapshot.observed_epoch,
        advance_ref=snapshot.advance_ref,
        current_step=snapshot.current_step,
        parent_snapshot_root=snapshot.parent_snapshot_root,
        parent_transition_id=snapshot.parent_transition_id,
        parent_revision=snapshot.parent_revision,
        addition_roots=tuple(item.receipt_root for item in effective_additions),
        request_root=request.request_root,
        context_root="",
    )
    binding = replace(
        binding,
        context_root=_compute_root("commit-replay-v2:source-context", binding.body()),
    )
    handle = object.__new__(VerifiedCommitReplaySourceV2)
    object.__setattr__(
        handle, "_request", CommitReplayAdvanceRequestV2.from_dict(request.to_dict())
    )
    object.__setattr__(handle, "_binding", binding)
    return handle


def verify_commit_replay_request_source_v2(
    request: CommitReplayAdvanceRequestV2,
    *,
    source: object,
    committed_parent_snapshot: CommitReplaySnapshotV2 | None,
) -> None:
    """Require exact source/request/Store-parent binding without mutation."""

    if type(request) is not CommitReplayAdvanceRequestV2:
        raise TypeError("commit replay verification requires exact request v2")
    source_request, binding = _verified_source(source)
    if source_request.to_dict() != request.to_dict():
        raise ValueError("commit replay source request is mismatched")
    expected_parent_root = (
        COMMIT_REPLAY_GENESIS_SNAPSHOT_ROOT_V2
        if committed_parent_snapshot is None
        else committed_parent_snapshot.snapshot_root
    )
    expected_parent_transition = (
        COMMIT_REPLAY_GENESIS_TRANSITION_ID_V2
        if committed_parent_snapshot is None
        else committed_parent_snapshot.transition_id
    )
    expected_parent_revision = (
        0 if committed_parent_snapshot is None else committed_parent_snapshot.revision
    )
    if (
        binding.parent_snapshot_root != expected_parent_root
        or binding.parent_transition_id != expected_parent_transition
        or binding.parent_revision != expected_parent_revision
        or request.snapshot.parent_snapshot_root != expected_parent_root
        or request.snapshot.parent_transition_id != expected_parent_transition
        or request.snapshot.parent_revision != expected_parent_revision
    ):
        raise ValueError("commit replay source parent is mismatched")
    expected_context, _ = _expected_source_roots(request, committed_parent_snapshot)
    if binding.context_root != expected_context:
        raise ValueError("commit replay source context is mismatched")


def _expected_source_roots(
    request: CommitReplayAdvanceRequestV2,
    parent: CommitReplaySnapshotV2 | None,
) -> tuple[str, str]:
    snapshot = request.snapshot
    parent_roots = (
        set() if parent is None else {item.receipt_root for item in parent.receipts}
    )
    additions = tuple(
        item.receipt_root
        for item in snapshot.receipts
        if item.receipt_root not in parent_roots
    )
    if not additions and not (
        parent is None and snapshot.revision == 1 and not snapshot.receipts
    ):
        raise ValueError("commit replay transition has no receipt addition")
    addition_root = _compute_root(
        "commit-replay-v2:receipt-additions",
        {"receipt_roots": list(additions)},
    )
    binding = _CommitReplaySourceBindingV2(
        domain_root=snapshot.domain_root,
        scope_ref=snapshot.scope_ref,
        manifest_root=snapshot.manifest_root,
        commit_policy_root=snapshot.commit_policy_root,
        profile=snapshot.profile,
        assurance=snapshot.assurance.value,
        protocol_ref=snapshot.protocol_ref,
        run_ref=snapshot.run_ref,
        target_ref=snapshot.target_ref,
        observed_epoch=snapshot.observed_epoch,
        advance_ref=snapshot.advance_ref,
        current_step=snapshot.current_step,
        parent_snapshot_root=snapshot.parent_snapshot_root,
        parent_transition_id=snapshot.parent_transition_id,
        parent_revision=snapshot.parent_revision,
        addition_roots=additions,
        request_root=request.request_root,
        context_root="",
    )
    return (
        _compute_root("commit-replay-v2:source-context", binding.body()),
        addition_root,
    )


def _verified_source(
    value: object,
) -> tuple[CommitReplayAdvanceRequestV2, _CommitReplaySourceBindingV2]:
    if type(value) is not VerifiedCommitReplaySourceV2:
        raise TypeError("commit replay source proof is invalid")
    try:
        request = object.__getattribute__(value, "_request")
        binding = object.__getattribute__(value, "_binding")
    except AttributeError as exc:
        raise TypeError("commit replay source proof is incomplete") from exc
    if (
        type(request) is not CommitReplayAdvanceRequestV2
        or type(binding) is not _CommitReplaySourceBindingV2
    ):
        raise TypeError("commit replay source proof material is invalid")
    expected = _compute_root("commit-replay-v2:source-context", binding.body())
    if binding.context_root != expected or binding.request_root != request.request_root:
        raise ValueError("commit replay source proof integrity is invalid")
    return CommitReplayAdvanceRequestV2.from_dict(request.to_dict()), binding


__all__ = [
    "VerifiedCommitReplaySourceV2",
    "prepare_commit_replay_advance_v2",
    "verify_commit_replay_request_source_v2",
]
