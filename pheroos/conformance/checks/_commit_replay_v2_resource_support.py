"""Public-constructor resource vectors for Commit Replay v2 Conformance."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256
from typing import Any, cast

from pheroos.governance.commit_state_v2 import (
    CommitReplayAdvanceRequestV2,
    CommitReplayReceiptV2,
    CommitReplaySnapshotV2,
    ReplayNamespace,
    VerifiedCommitReplaySourceV2,
    prepare_commit_replay_advance_v2,
)


_MAX_RECEIPTS = 4_096
_MAX_TEXT_BYTES = 4_096
_MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
_LARGE_RECEIPTS = 512
_LARGE_BASE_TEXT_BYTES = 3_500
_LARGE_FIELDS = ("record_id", "nonce", "candidate_ref", "principal_ref")

_RequestFactory = Callable[
    ...,
    tuple[CommitReplayAdvanceRequestV2, VerifiedCommitReplaySourceV2],
]


def run_public_commit_replay_resource_matrix_v2(
    *,
    context: Any,
    store: Any,
    request_factory: _RequestFactory,
) -> tuple[str, ...]:
    """Exercise exact/+1 bounds without publishing any StateStore write."""

    problems: list[str] = []
    baseline, _ = request_factory(
        context,
        advance_ref="advance:public-resource-baseline",
        receipt=None,
        current_step=1,
    )
    before = store.load_head_v2(baseline.scope_ref, baseline.stream_ref)
    store.reset_observations()
    _check_count_bound(baseline, problems)
    _check_text_bound(baseline, problems)
    _check_snapshot_and_preflight_bounds(baseline, problems)
    after = store.load_head_v2(baseline.scope_ref, baseline.stream_ref)
    if (
        store.atomic_commits != 0
        or after.revision != before.revision
        or after.head_root != before.head_root
    ):
        problems.append("resource_rejection_zero_write")
    return tuple(problems)


def _check_count_bound(
    baseline: CommitReplayAdvanceRequestV2,
    problems: list[str],
) -> None:
    receipts = tuple(
        _small_receipt(index, baseline.target_ref) for index in range(_MAX_RECEIPTS)
    )
    try:
        exact, _ = _prepare(baseline, "advance:resource-count-exact", receipts)
    except (TypeError, ValueError):
        problems.append("resource_count_exact")
        return
    if len(exact.snapshot.receipts) != _MAX_RECEIPTS:
        problems.append("resource_count_exact")
    payload = exact.snapshot.to_dict()
    raw_receipts = list(cast(list[object], payload["receipts"]))
    raw_receipts.append(receipts[-1].to_dict())
    payload["receipts"] = raw_receipts
    error = _snapshot_error(payload)
    if error is None or "receipt count exceeds" not in error:
        problems.append("resource_count_over")


def _check_text_bound(
    baseline: CommitReplayAdvanceRequestV2,
    problems: list[str],
) -> None:
    exact_text = "é" * (_MAX_TEXT_BYTES // 2)
    exact = CommitReplayReceiptV2(
        namespace=ReplayNamespace.OBSERVATION,
        record_id=exact_text,
        nonce="nonce:resource-text",
        payload_fingerprint=_root("resource-text"),
        target_ref=baseline.target_ref,
        candidate_ref="candidate:resource",
        epoch=1,
        principal_ref="principal:resource",
    )
    try:
        request, _ = _prepare(
            baseline,
            "advance:resource-text-exact",
            (exact,),
        )
    except (TypeError, ValueError):
        problems.append("resource_text_exact")
    else:
        if len(request.snapshot.receipts[0].record_id.encode("utf-8")) != (
            _MAX_TEXT_BYTES
        ):
            problems.append("resource_text_exact")
    try:
        CommitReplayReceiptV2(
            namespace=ReplayNamespace.OBSERVATION,
            record_id=exact_text + "x",
            nonce="nonce:resource-text-over",
            payload_fingerprint=_root("resource-text-over"),
            target_ref=baseline.target_ref,
            candidate_ref="candidate:resource",
            epoch=1,
            principal_ref="principal:resource",
        )
    except ValueError as exc:
        if "text bound" not in str(exc):
            problems.append("resource_text_over")
    else:
        problems.append("resource_text_over")


def _check_snapshot_and_preflight_bounds(
    baseline: CommitReplayAdvanceRequestV2,
    problems: list[str],
) -> None:
    lengths = [
        [_LARGE_BASE_TEXT_BYTES] * len(_LARGE_FIELDS) for _ in range(_LARGE_RECEIPTS)
    ]
    base_receipts = _large_receipts(lengths, baseline.target_ref)
    try:
        base, _ = _prepare(
            baseline,
            "advance:resource-snapshot-exact",
            base_receipts,
        )
    except (TypeError, ValueError):
        problems.append("resource_snapshot_vector")
        return
    growth = _MAX_SNAPSHOT_BYTES - len(base.snapshot.canonical_bytes())
    del base, base_receipts
    if growth < 0 or not _allocate_text(lengths, growth):
        problems.append("resource_snapshot_vector")
        return

    exact_receipts = _large_receipts(lengths, baseline.target_ref)
    try:
        exact, _ = _prepare(
            baseline,
            "advance:resource-snapshot-exact",
            exact_receipts,
        )
    except (TypeError, ValueError):
        problems.append("resource_snapshot_exact")
        return
    if len(exact.snapshot.canonical_bytes()) != _MAX_SNAPSHOT_BYTES:
        problems.append("resource_snapshot_exact")
        return

    over_lengths = [list(item) for item in lengths]
    if not _allocate_text(over_lengths, 1):
        problems.append("resource_snapshot_over_vector")
    else:
        over_receipts = _large_receipts(over_lengths, baseline.target_ref)
        error = _prepare_error(
            baseline,
            "advance:resource-snapshot-exact",
            over_receipts,
        )
        if error is None or "canonical snapshot exceeds" not in error:
            problems.append("resource_snapshot_over")

    receipt_bytes = sum(len(item.canonical_bytes()) for item in exact_receipts)
    preflight_growth = _MAX_SNAPSHOT_BYTES - receipt_bytes + 1
    preflight_lengths = [list(item) for item in lengths]
    if preflight_growth <= 0 or not _allocate_text(preflight_lengths, preflight_growth):
        problems.append("resource_preflight_vector")
        return
    raw_preflight = _large_receipts(preflight_lengths, baseline.target_ref)
    colliding = replace(
        raw_preflight[1],
        nonce=raw_preflight[0].nonce,
        receipt_root="",
    )
    preflight_receipts = (raw_preflight[0], colliding, *raw_preflight[2:])
    error = _snapshot_replace_error(exact.snapshot, preflight_receipts)
    if error is None or "receipt bytes exceed the snapshot bound" not in error:
        problems.append("resource_preflight_over")


def _prepare(
    baseline: CommitReplayAdvanceRequestV2,
    advance_ref: str,
    receipts: tuple[CommitReplayReceiptV2, ...],
) -> tuple[CommitReplayAdvanceRequestV2, VerifiedCommitReplaySourceV2]:
    snapshot = baseline.snapshot
    return prepare_commit_replay_advance_v2(
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
        advance_ref=advance_ref,
        current_step=1,
        receipt_additions=receipts,
        parent_snapshot=None,
    )


def _small_receipt(index: int, target_ref: str) -> CommitReplayReceiptV2:
    return CommitReplayReceiptV2(
        namespace=ReplayNamespace.OBSERVATION,
        record_id=f"resource-record:{index:04d}",
        nonce=f"resource-nonce:{index:04d}",
        payload_fingerprint=_root(f"resource-payload:{index:04d}"),
        target_ref=target_ref,
        candidate_ref="candidate:resource",
        epoch=1,
        principal_ref="principal:resource",
    )


def _large_receipts(
    lengths: list[list[int]],
    target_ref: str,
) -> tuple[CommitReplayReceiptV2, ...]:
    receipts: list[CommitReplayReceiptV2] = []
    for index, field_lengths in enumerate(lengths):
        prefixes = (
            f"r{index:04d}:",
            f"n{index:04d}:",
            f"c{index:04d}:",
            f"p{index:04d}:",
        )
        values = tuple(
            prefix + ("x" * (length - len(prefix)))
            for prefix, length in zip(prefixes, field_lengths, strict=True)
        )
        receipts.append(
            CommitReplayReceiptV2(
                namespace=ReplayNamespace.OBSERVATION,
                record_id=values[0],
                nonce=values[1],
                payload_fingerprint=_root(f"large-resource:{index:04d}"),
                target_ref=target_ref,
                candidate_ref=values[2],
                epoch=1,
                principal_ref=values[3],
            )
        )
    return tuple(receipts)


def _allocate_text(lengths: list[list[int]], amount: int) -> bool:
    remaining = amount
    for fields in lengths:
        for index, length in enumerate(fields):
            growth = min(remaining, _MAX_TEXT_BYTES - length)
            fields[index] += growth
            remaining -= growth
            if remaining == 0:
                return True
    return remaining == 0


def _prepare_error(
    baseline: CommitReplayAdvanceRequestV2,
    advance_ref: str,
    receipts: tuple[CommitReplayReceiptV2, ...],
) -> str | None:
    try:
        _prepare(baseline, advance_ref, receipts)
    except (TypeError, ValueError) as exc:
        return str(exc)
    return None


def _snapshot_error(payload: object) -> str | None:
    try:
        CommitReplaySnapshotV2.from_dict(payload)
    except (TypeError, ValueError) as exc:
        return str(exc)
    return None


def _snapshot_replace_error(
    snapshot: CommitReplaySnapshotV2,
    receipts: tuple[CommitReplayReceiptV2, ...],
) -> str | None:
    """Require byte preflight to win before the deliberate collision/sort."""

    try:
        replace(
            snapshot,
            receipts=receipts,
            receipt_root="",
            snapshot_root="",
        )
    except (TypeError, ValueError) as exc:
        return str(exc)
    return None


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


__all__: list[str] = []
