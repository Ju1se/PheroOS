from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import pickle

import pytest

from pheroos.governance import (
    AuthorityLevel,
    COMMIT_REPLAY_GENESIS_TRANSITION_ID_V2,
    CommitAssurance,
    CommitReplayAdvanceRequestV2,
    CommitReplayReceiptV2,
    CommitReplaySnapshotV2,
    ReplayNamespace,
    ReplayReceipt,
    VerifiedCommitReplaySourceV2,
    canonical_commit_replay_receipts_v2,
    commit_replay_stream_ref_v2,
    initialize_commit_replay_state,
    prepare_commit_replay_advance_v2,
    record_commit_replay_receipts,
)
from pheroos.governance._commit_state_v2.source import (
    verify_commit_replay_request_source_v2,
)
from pheroos.protocol import (
    CERTIFIED_COMMIT_PROFILE_VERSION,
    COMMIT_INTEGRITY_PROFILE_VERSION,
)


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode()).hexdigest()


def _receipt(
    index: int,
    *,
    namespace: ReplayNamespace = ReplayNamespace.OBSERVATION,
    record_id: str | None = None,
    nonce: str | None = None,
    payload: str | None = None,
) -> CommitReplayReceiptV2:
    return CommitReplayReceiptV2(
        namespace=namespace,
        record_id=record_id or f"record:{index}",
        nonce=nonce or f"nonce:{index}",
        payload_fingerprint=_root(payload or f"payload:{index}"),
        target_ref="target:replay",
        candidate_ref="candidate:alpha",
        epoch=1,
        principal_ref="principal:scout",
    )


def _prepare(
    *,
    additions: tuple[CommitReplayReceiptV2, ...],
    parent: CommitReplaySnapshotV2 | None = None,
    advance: str = "advance:one",
):
    return prepare_commit_replay_advance_v2(
        domain_root=_root("domain"),
        scope_ref="scope:replay",
        manifest_root=_root("manifest"),
        commit_policy_root=_root("policy"),
        profile=COMMIT_INTEGRITY_PROFILE_VERSION,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        protocol_ref="protocol:replay",
        run_ref="run:replay",
        target_ref="target:replay",
        observed_epoch=2,
        advance_ref=advance,
        current_step=1 if parent is None else parent.current_step + 1,
        receipt_additions=additions,
        parent_snapshot=parent,
    )


def test_explicit_empty_genesis_round_trips_and_child_requires_addition() -> None:
    request, source = _prepare(additions=())

    assert request.snapshot.receipts == ()
    assert (
        request.snapshot.parent_transition_id == COMMIT_REPLAY_GENESIS_TRANSITION_ID_V2
    )
    assert CommitReplayAdvanceRequestV2.from_dict(request.to_dict()) == request
    assert (
        CommitReplaySnapshotV2.from_dict(request.snapshot.to_dict()) == request.snapshot
    )
    assert type(source) is VerifiedCommitReplaySourceV2
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(source)
    with pytest.raises(TypeError, match="constructed directly"):
        VerifiedCommitReplaySourceV2()

    with pytest.raises(ValueError, match="no new receipt"):
        _prepare(additions=(), parent=request.snapshot, advance="advance:empty-child")


def test_stream_and_versioned_roots_have_frozen_golden_values() -> None:
    request, _ = _prepare(additions=(_receipt(1),))

    assert commit_replay_stream_ref_v2(
        "scope:replay", "protocol:replay", "run:replay", "target:replay"
    ) == (
        "authority:commit-replay-v2:"
        "77e48d4a9150bbe188b138b5a2f8b199f40dcafdd777cce1b7075d1f5a411fe6"
    )
    assert request.snapshot.receipt_root == (
        "sha256:71ebebb7b5fd3bfe51a5799c008f40159598123acc2f840c4b2299a350af98a0"
    )
    assert request.snapshot.snapshot_root == (
        "sha256:e1708f06ff4e0f73e34a342340c30d6e2a210644a2d5e11ec99bfa75cdb70432"
    )


@pytest.mark.parametrize("axis", ["nonce", "record_id", "payload"])
def test_v1_v2_three_axis_collision_semantics_are_differential(axis: str) -> None:
    first = _receipt(1)
    values = {
        "nonce": {"nonce": first.nonce},
        "record_id": {"record_id": first.record_id},
        "payload": {"payload": "payload:1"},
    }[axis]
    conflicting = _receipt(2, **values)
    with pytest.raises(ValueError, match="collision"):
        canonical_commit_replay_receipts_v2((first, conflicting))

    v1_first = ReplayReceipt(
        namespace=first.namespace,
        record_id=first.record_id,
        nonce=first.nonce,
        payload_fingerprint=first.payload_fingerprint,
        target=first.target_ref,
        candidate_id=first.candidate_ref,
        epoch=first.epoch,
        principal_id=first.principal_ref,
    )
    v1_conflict = ReplayReceipt(
        namespace=conflicting.namespace,
        record_id=conflicting.record_id,
        nonce=conflicting.nonce,
        payload_fingerprint=conflicting.payload_fingerprint,
        target=conflicting.target_ref,
        candidate_id=conflicting.candidate_ref,
        epoch=conflicting.epoch,
        principal_id=conflicting.principal_ref,
    )
    state = initialize_commit_replay_state(
        profile=COMMIT_INTEGRITY_PROFILE_VERSION,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=_root(f"manifest:{axis}"),
        commit_policy_root=_root("policy"),
        protocol_id=f"protocol:replay:{axis}",
        run_id=f"run:replay:{axis}",
        current_step=1,
        issuer_id="issuer:test",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="test",
        trace_event_id=f"trace:{axis}",
    )
    state = record_commit_replay_receipts(state, current_step=1, receipts=(v1_first,))
    with pytest.raises(Exception, match="collision"):
        record_commit_replay_receipts(state, current_step=2, receipts=(v1_conflict,))


def test_exact_duplicate_and_explicit_v1_v2_vector_preserve_shared_meaning() -> None:
    first = _receipt(1)
    legacy = ReplayReceipt(
        namespace=first.namespace,
        record_id=first.record_id,
        nonce=first.nonce,
        payload_fingerprint=first.payload_fingerprint,
        target=first.target_ref,
        candidate_id=first.candidate_ref,
        epoch=first.epoch,
        principal_id=first.principal_ref,
    )
    projected = CommitReplayReceiptV2(
        namespace=legacy.namespace,
        record_id=legacy.record_id,
        nonce=legacy.nonce,
        payload_fingerprint=legacy.payload_fingerprint,
        target_ref=legacy.target,
        candidate_ref=legacy.candidate_id,
        epoch=legacy.epoch,
        principal_ref=legacy.principal_id,
    )
    assert projected == first
    assert canonical_commit_replay_receipts_v2((first, first)) == (first,)


def test_resource_bounds_and_defensive_root_validation_fail_before_hashing() -> None:
    with pytest.raises(ValueError, match="count exceeds"):
        canonical_commit_replay_receipts_v2([_receipt(1)] * 4097)
    with pytest.raises(TypeError, match="exact array or tuple"):
        canonical_commit_replay_receipts_v2(iter((_receipt(1),)))  # type: ignore[arg-type]
    request, _ = _prepare(additions=(_receipt(1),))
    with pytest.raises(ValueError, match="snapshot_root is mismatched"):
        CommitReplaySnapshotV2.from_dict(
            {**request.snapshot.to_dict(), "snapshot_root": _root("tampered")}
        )
    with pytest.raises(ValueError, match="request_root is mismatched"):
        replace(request, request_root=_root("tampered-request"))
    with pytest.raises(ValueError, match="fields are invalid"):
        CommitReplayAdvanceRequestV2.from_dict(
            {**request.to_dict(), "unexpected": True}
        )


def test_from_dict_requires_exact_non_self_healing_canonical_wire() -> None:
    first = _receipt(1)
    second = _receipt(2)
    request, _ = _prepare(additions=(first, second))

    missing_receipt_root = first.to_dict()
    missing_receipt_root["receipt_root"] = ""
    with pytest.raises(ValueError, match="not canonical wire"):
        CommitReplayReceiptV2.from_dict(missing_receipt_root)

    missing_snapshot_root = request.snapshot.to_dict()
    missing_snapshot_root["snapshot_root"] = ""
    with pytest.raises(ValueError, match="not canonical wire"):
        CommitReplaySnapshotV2.from_dict(missing_snapshot_root)

    missing_request_root = request.to_dict()
    missing_request_root["request_root"] = ""
    with pytest.raises(ValueError, match="not canonical wire"):
        CommitReplayAdvanceRequestV2.from_dict(missing_request_root)

    tuple_receipts = request.snapshot.to_dict()
    tuple_receipts["receipts"] = tuple(tuple_receipts["receipts"])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="exact array"):
        CommitReplaySnapshotV2.from_dict(tuple_receipts)

    reordered = request.snapshot.to_dict()
    receipts = reordered["receipts"]
    assert type(receipts) is list
    receipts.reverse()
    with pytest.raises(ValueError, match="not canonical wire"):
        CommitReplaySnapshotV2.from_dict(reordered)


def test_aggregate_receipt_bytes_are_bounded_before_snapshot_hashing() -> None:
    large = "x" * 3990
    receipts = tuple(
        CommitReplayReceiptV2(
            namespace=ReplayNamespace.OBSERVATION,
            record_id=f"record:{index}:{large}",
            nonce=f"nonce:{index}:{large}",
            payload_fingerprint=_root(f"large-payload:{index}"),
            target_ref="target:replay",
            candidate_ref=large,
            epoch=1,
            principal_ref=large,
        )
        for index in range(530)
    )
    with pytest.raises(ValueError, match="receipt bytes exceed"):
        _prepare(additions=receipts, advance="advance:aggregate-overflow")


def test_source_proof_binds_every_authority_context_axis() -> None:
    request, source = _prepare(additions=(_receipt(1),))
    variants = (
        {"domain_root": _root("other-domain")},
        {"scope_ref": "scope:other"},
        {"manifest_root": _root("other-manifest")},
        {"commit_policy_root": _root("other-policy")},
        {"protocol_ref": "protocol:other"},
        {"run_ref": "run:other"},
        {
            "target_ref": "target:other",
            "receipt_additions": (
                replace(_receipt(1), target_ref="target:other", receipt_root=""),
            ),
        },
        {
            "profile": CERTIFIED_COMMIT_PROFILE_VERSION,
            "assurance": CommitAssurance.CERTIFIED,
        },
        {"observed_epoch": 3},
        {"current_step": 2},
        {"receipt_additions": (_receipt(2),)},
    )
    base = {
        "domain_root": _root("domain"),
        "scope_ref": "scope:replay",
        "manifest_root": _root("manifest"),
        "commit_policy_root": _root("policy"),
        "profile": COMMIT_INTEGRITY_PROFILE_VERSION,
        "assurance": CommitAssurance.EVIDENCE_BOUND,
        "protocol_ref": "protocol:replay",
        "run_ref": "run:replay",
        "target_ref": "target:replay",
        "observed_epoch": 2,
        "advance_ref": "advance:one",
        "current_step": 1,
        "receipt_additions": (_receipt(1),),
    }
    for changes in variants:
        other_request, _ = prepare_commit_replay_advance_v2(
            **{**base, **changes}  # type: ignore[arg-type]
        )
        with pytest.raises(ValueError, match="source request is mismatched"):
            verify_commit_replay_request_source_v2(
                other_request,
                source=source,
                committed_parent_snapshot=None,
            )

    class SameShape:
        context_root = source.context_root

    for forged in (request, request.to_dict(), request.request_root, SameShape()):
        with pytest.raises(TypeError, match="source proof is invalid"):
            verify_commit_replay_request_source_v2(
                request,
                source=forged,
                committed_parent_snapshot=None,
            )

    parent, _ = _prepare(additions=(), advance="advance:parent")
    child, child_source = _prepare(
        additions=(_receipt(3),),
        parent=parent.snapshot,
        advance="advance:child",
    )
    other_parent, _ = _prepare(additions=(_receipt(4),), advance="advance:other-parent")
    with pytest.raises(ValueError, match="source parent is mismatched"):
        verify_commit_replay_request_source_v2(
            child,
            source=child_source,
            committed_parent_snapshot=other_parent.snapshot,
        )
