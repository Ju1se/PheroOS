from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import copy, deepcopy
from dataclasses import dataclass, replace
from hashlib import sha256
import json
import pickle
from typing import Any, cast

import pytest

from pheroos.governance._authority_v2 import InMemoryGovernanceStateStoreV2
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceDomainRetirementRequestV2,
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    governance_issuer_grant_stream_ref_v2,
    open_governance_authority_session_v2,
    retire_governance_domain_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitInclusionProofV2,
    GovernanceCommitPositionObservationV2,
    GovernanceCommitPositionV2,
    GovernanceCommitReceiptV2,
    GovernanceCommitViewV2,
    GovernanceCommittedTransitionV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
    GovernanceTraceBatchV2,
    PreparedGovernanceTransitionV2,
)
from pheroos.governance.commit_state_v2 import (
    COMMIT_REPLAY_ADVANCE_REQUEST_SCHEMA_V2,
    COMMIT_REPLAY_RECEIPT_SCHEMA_V2,
    COMMIT_REPLAY_SNAPSHOT_SCHEMA_V2,
    CommitReplayAdvanceRequestV2,
    CommitReplayReceiptV2,
    CommitReplaySnapshotV2,
    ReplayNamespace,
    VerifiedCommitReplaySourceV2,
    VerifiedCommitReplayStateV2,
    advance_commit_replay_state_v2,
    canonical_commit_replay_receipts_v2,
    commit_replay_receipt_set_root_v2,
    commit_replay_state_is_current_v2,
    commit_replay_stream_ref_v2,
    commit_replay_transition_id_v2,
    open_commit_replay_authority_session_v2,
    prepare_commit_replay_advance_v2,
    rehydrate_commit_replay_state_v2,
    require_current_commit_replay_state_v2,
)
from pheroos.protocol import COMMIT_INTEGRITY_PROFILE_VERSION, CommitAssurance
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    MAX_AUTHORITY_REVISION_V2,
    AuthorityDiagnosticCodeV2,
    GovernanceAuthorityReadSetV2,
    GovernanceReadPreconditionV2,
)
from pheroos.trace import TraceEvent


_RUN_REF = "run:commit-state-v2-public"
_TARGET_REF = "target:commit-state-v2-public"
_DONOR_TARGET_REF = "target:commit-state-v2-donor"


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _authority_root(kind: str, body: object) -> str:
    payload = json.dumps(
        body,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    prefix = f"pheroos-governance-authority-v2:{kind}".encode("utf-8")
    return "sha256:" + sha256(prefix + b"\x00" + payload).hexdigest()


@dataclass(frozen=True, slots=True)
class _Context:
    domain: AuthorityDomainV2
    store: GovernanceStateStoreV2
    base_store: InMemoryGovernanceStateStoreV2
    grant: GovernanceIssuerGrantV2
    capability: GovernanceIssuerCapabilityV2


def _domain(label: str) -> AuthorityDomainV2:
    return AuthorityDomainV2(
        policy_version=AUTHORITY_POLICY_VERSION_V2,
        profile=AUTHORITY_LOCAL_PROFILE_V2,
        wire_version=AUTHORITY_WIRE_VERSION_V2,
        canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref=f"scope:commit-state-v2:{label}",
    )


def _grant(
    domain: AuthorityDomainV2,
    *,
    expires_at_epoch: int = 100,
) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:commit-state-v2",
        grant_ref="grant:commit-state-v2",
        grant_binding_ref=_root("grant-binding"),
        operations=(
            GovernanceIssuerOperationV2.ADVANCE_REPLAY,
            GovernanceIssuerOperationV2.RETIRE_DOMAIN,
        ),
        target_refs=tuple(
            sorted(
                (_TARGET_REF, _DONOR_TARGET_REF), key=lambda item: item.encode("utf-8")
            )
        ),
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=expires_at_epoch,
        revocation_generation=0,
    )


def _context(
    label: str,
    *,
    wrapper: Callable[
        [InMemoryGovernanceStateStoreV2, AuthorityDomainV2], GovernanceStateStoreV2
    ]
    | None = None,
    expires_at_epoch: int = 100,
    bind_epoch: int = 3,
) -> _Context:
    domain = _domain(label)
    base_store = InMemoryGovernanceStateStoreV2((domain,))
    grant = _grant(domain, expires_at_epoch=expires_at_epoch)
    activated = activate_governance_issuer_grant_v2(
        base_store,
        domain,
        grant,
        f"transition:grant:{label}",
        1,
    )
    assert activated.disposition is GovernanceCommitDispositionV2.COMMITTED
    store = (
        cast(GovernanceStateStoreV2, base_store)
        if wrapper is None
        else wrapper(base_store, domain)
    )
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        _RUN_REF,
        bind_epoch,
    )
    return _Context(domain, store, base_store, grant, capability)


def _receipt(
    index: int,
    *,
    target_ref: str = _TARGET_REF,
    suffix: str = "",
    candidate_ref: str = "candidate:alpha",
    principal_ref: str = "principal:scout",
) -> CommitReplayReceiptV2:
    return CommitReplayReceiptV2(
        namespace=ReplayNamespace.OBSERVATION,
        record_id=f"record:{index}{suffix}",
        nonce=f"nonce:{index}{suffix}",
        payload_fingerprint=_root(f"payload:{index}{suffix}"),
        target_ref=target_ref,
        candidate_ref=candidate_ref,
        epoch=1,
        principal_ref=principal_ref,
    )


def _request(
    context: _Context,
    *,
    advance_ref: str,
    additions: tuple[CommitReplayReceiptV2, ...] = (),
    parent: CommitReplaySnapshotV2 | None = None,
    current_step: int = 1,
    observed_epoch: int = 3,
    target_ref: str = _TARGET_REF,
) -> tuple[CommitReplayAdvanceRequestV2, VerifiedCommitReplaySourceV2]:
    return prepare_commit_replay_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest_root=_root("manifest"),
        commit_policy_root=_root("commit-policy"),
        profile=COMMIT_INTEGRITY_PROFILE_VERSION,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        protocol_ref="protocol:commit-state-v2",
        run_ref=_RUN_REF,
        target_ref=target_ref,
        observed_epoch=observed_epoch,
        advance_ref=advance_ref,
        current_step=current_step,
        receipt_additions=additions,
        parent_snapshot=parent,
    )


def _advance(
    context: _Context,
    request: CommitReplayAdvanceRequestV2,
    source: object,
) -> tuple[GovernanceCommitAttemptV2, object]:
    session = open_commit_replay_authority_session_v2(context.capability, request)
    return (
        advance_commit_replay_state_v2(
            request,
            source=source,
            authority_session=session,
        ),
        session,
    )


class _DelegatingStore:
    def __init__(
        self,
        store: InMemoryGovernanceStateStoreV2,
        domain: AuthorityDomainV2,
    ) -> None:
        self.store = store
        self.domain = domain
        self.view_mutator: Callable[
            [GovernanceCommitViewV2], GovernanceCommitViewV2
        ] = lambda view: view
        self.finality_without_failure: set[str] = set()
        self.missing_transitions: set[str] = set()
        self.lost_response = False
        self.atomic_commits = 0

    @property
    def state_store_version(self) -> str:
        return self.store.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        return self.store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        return self.store.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        if transition_id in self.missing_transitions:
            raise KeyError(transition_id)
        if transition_id in self.finality_without_failure:
            return GovernanceCommitViewV2(
                domain_root=self.domain.domain_root,
                scope_ref=scope_ref,
                stream_ref=stream_ref,
                transition_id=transition_id,
                expected_receipt_root=expected_receipt_root,
                disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
                failure=GovernanceFailureV2(
                    code=AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
                    path="/transition_id",
                    stage=GovernanceFailureStageV2.FINALITY,
                ),
                committed_transition=None,
                position_observation=None,
                observed_revision=None,
                observed_head_root=None,
            )
        view = self.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )
        return self.view_mutator(view)

    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        self.atomic_commits += 1
        result = self.store.atomic_commit_v2(batch)
        if (
            self.lost_response
            and result.disposition is GovernanceCommitDispositionV2.COMMITTED
        ):
            self.lost_response = False
            return GovernanceCommitAttemptV2(
                domain_root=batch.domain_root,
                scope_ref=batch.scope_ref,
                stream_ref=batch.stream_ref,
                transition_id=batch.transition_id,
                disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
                failure=GovernanceFailureV2(
                    code=AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
                    path="/transition_id",
                    stage=GovernanceFailureStageV2.FINALITY,
                ),
                committed_transition=None,
                position_observation=None,
            )
        return result


def _proxy_context(label: str) -> tuple[_Context, _DelegatingStore]:
    holder: list[_DelegatingStore] = []

    def wrapper(
        store: InMemoryGovernanceStateStoreV2,
        domain: AuthorityDomainV2,
    ) -> GovernanceStateStoreV2:
        proxy = _DelegatingStore(store, domain)
        holder.append(proxy)
        return cast(GovernanceStateStoreV2, proxy)

    context = _context(label, wrapper=wrapper)
    return context, holder[0]


def _rebuild_committed_view(
    view: GovernanceCommitViewV2,
    *,
    state_records: Mapping[str, Any] | None = None,
    read_set: GovernanceAuthorityReadSetV2 | None = None,
    trace_events: tuple[TraceEvent, ...] | None = None,
) -> GovernanceCommitViewV2:
    """Rebuild a fully canonical public view around consumer-selected material."""

    committed = view.committed_transition
    assert committed is not None
    base_batch = committed.batch
    base_transition = base_batch.transition
    assert base_transition is not None
    selected_read_set = base_batch.read_set if read_set is None else read_set
    write_precondition = next(
        item
        for item in selected_read_set.entries
        if item.stream_ref == base_batch.stream_ref
    )
    transition = PreparedGovernanceTransitionV2(
        domain_root=base_batch.domain_root,
        scope_ref=base_batch.scope_ref,
        stream_ref=base_batch.stream_ref,
        transition_id=base_batch.transition_id,
        expected_revision=write_precondition.expected_revision,
        expected_root=write_precondition.expected_root,
        read_set_root=selected_read_set.root(),
        state_records=(
            base_transition.state_records if state_records is None else state_records
        ),
    )
    trace_batch = GovernanceTraceBatchV2(
        domain_root=base_batch.domain_root,
        scope_ref=base_batch.scope_ref,
        stream_ref=base_batch.stream_ref,
        transition_id=base_batch.transition_id,
        events=(
            base_batch.trace_batch.events if trace_events is None else trace_events
        ),
    )
    batch = GovernanceCommitBatchV2(
        domain=base_batch.domain,
        scope_ref=base_batch.scope_ref,
        stream_ref=base_batch.stream_ref,
        transition_id=base_batch.transition_id,
        kind="transition",
        read_set=selected_read_set,
        trace_batch=trace_batch,
        transition=transition,
    )
    revision = transition.expected_revision + 1
    head = GovernanceHeadV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        revision=revision,
        parent_root=transition.expected_root,
        state_root=transition.state_root,
        transition_id=batch.transition_id,
        batch_root=batch.batch_root,
    )
    receipt = GovernanceCommitReceiptV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        revision=revision,
        parent_root=transition.expected_root,
        head_root=head.head_root,
        state_root=transition.state_root,
        read_set_root=selected_read_set.root(),
        trace_root=trace_batch.trace_root,
        batch_root=batch.batch_root,
    )
    inclusion = GovernanceCommitInclusionProofV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        revision=revision,
        batch_root=batch.batch_root,
        receipt_root=receipt.receipt_root,
        head_root=receipt.head_root,
    )
    rebuilt = GovernanceCommittedTransitionV2(
        batch=batch,
        receipt=receipt,
        inclusion_proof=inclusion,
    )
    position = GovernanceCommitPositionObservationV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        receipt_root=receipt.receipt_root,
        observed_revision=revision,
        observed_head_root=receipt.head_root,
        position=GovernanceCommitPositionV2.CURRENT,
    )
    return GovernanceCommitViewV2(
        domain_root=batch.domain_root,
        scope_ref=batch.scope_ref,
        stream_ref=batch.stream_ref,
        transition_id=batch.transition_id,
        expected_receipt_root=None,
        disposition=GovernanceCommitDispositionV2.COMMITTED,
        failure=None,
        committed_transition=rebuilt,
        position_observation=position,
        observed_revision=position.observed_revision,
        observed_head_root=position.observed_head_root,
    )


def _replace_event_lineage(
    event: TraceEvent,
    **changes: object,
) -> TraceEvent:
    return TraceEvent(
        event_type=event.event_type,
        protocol_id=event.protocol_id,
        target=event.target,
        reason=event.reason,
        lineage={**event.lineage, **changes},
    )


def _substitute_transition_view(
    forged: GovernanceCommitViewV2,
    transition_id: str,
) -> Callable[[GovernanceCommitViewV2], GovernanceCommitViewV2]:
    def substitute(view: GovernanceCommitViewV2) -> GovernanceCommitViewV2:
        return forged if view.transition_id == transition_id else view

    return substitute


def _commit_one(
    context: _Context,
    *,
    advance_ref: str,
    additions: tuple[CommitReplayReceiptV2, ...] = (),
    parent: CommitReplaySnapshotV2 | None = None,
    current_step: int = 1,
    target_ref: str = _TARGET_REF,
) -> tuple[CommitReplayAdvanceRequestV2, GovernanceCommitAttemptV2]:
    request, source = _request(
        context,
        advance_ref=advance_ref,
        additions=additions,
        parent=parent,
        current_step=current_step,
        target_ref=target_ref,
    )
    attempt, _ = _advance(context, request, source)
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    return request, attempt


def _assert_binding_failure(
    attempt: GovernanceCommitAttemptV2,
    *,
    code: AuthorityDiagnosticCodeV2 = AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
) -> None:
    assert attempt.disposition in {
        GovernanceCommitDispositionV2.INVALID,
        GovernanceCommitDispositionV2.DENIED,
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
    }
    assert attempt.failure is not None
    assert attempt.failure.code is code
    assert attempt.committed_transition is None


def test_public_contracts_round_trip_exact_roots_and_empty_text_axes() -> None:
    receipt = _receipt(1, candidate_ref="", principal_ref="")
    assert receipt.schema == COMMIT_REPLAY_RECEIPT_SCHEMA_V2
    assert receipt.root() == receipt.receipt_root
    assert CommitReplayReceiptV2.from_dict(receipt.to_dict()) == receipt
    assert receipt.canonical_bytes()
    assert canonical_commit_replay_receipts_v2([receipt, receipt]) == (receipt,)
    assert commit_replay_receipt_set_root_v2((receipt,)) == (
        commit_replay_receipt_set_root_v2([receipt])
    )

    context = _context("contract-roundtrip")
    request, _ = _request(
        context,
        advance_ref="advance:contract-roundtrip",
        additions=(receipt,),
    )
    assert request.schema == COMMIT_REPLAY_ADVANCE_REQUEST_SCHEMA_V2
    assert request.snapshot.schema == COMMIT_REPLAY_SNAPSHOT_SCHEMA_V2
    assert request.root() == request.request_root
    assert request.snapshot.root() == request.snapshot.snapshot_root
    assert request.canonical_bytes()
    assert request.snapshot.canonical_bytes()
    assert CommitReplaySnapshotV2.from_dict(request.snapshot.to_dict()) == (
        request.snapshot
    )
    assert CommitReplayAdvanceRequestV2.from_dict(request.to_dict()) == request
    assert request.stream_ref == commit_replay_stream_ref_v2(
        context.domain.scope_ref,
        "protocol:commit-state-v2",
        _RUN_REF,
        _TARGET_REF,
    )
    assert request.transition_id == commit_replay_transition_id_v2(
        request.stream_ref,
        request.advance_ref,
    )


@pytest.mark.parametrize(
    ("constructor", "match"),
    (
        (
            lambda: CommitReplayReceiptV2.from_dict([]),
            "exact object",
        ),
        (
            lambda: CommitReplayReceiptV2.from_dict(
                {
                    **_receipt(1).to_dict(),
                    "schema": "unsupported",
                    "receipt_root": "",
                }
            ),
            "unsupported",
        ),
        (
            lambda: CommitReplayReceiptV2.from_dict(
                {
                    **_receipt(1).to_dict(),
                    "namespace": True,
                    "receipt_root": "",
                }
            ),
            "namespace is unsupported",
        ),
        (
            lambda: CommitReplayReceiptV2.from_dict(
                {
                    **_receipt(1).to_dict(),
                    "namespace": "unsupported",
                    "receipt_root": "",
                }
            ),
            "namespace is unsupported",
        ),
        (
            lambda: canonical_commit_replay_receipts_v2(
                (_receipt(1), object())  # type: ignore[arg-type]
            ),
            "non-canonical",
        ),
    ),
)
def test_portable_receipt_wire_is_exact_and_fail_closed(
    constructor: Callable[[], object],
    match: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=match):
        constructor()
    with pytest.raises(TypeError, match="namespace is invalid"):
        replace(_receipt(3), namespace="observation", receipt_root="")  # type: ignore[arg-type]


def test_snapshot_and_request_semantic_forgery_is_rejected() -> None:
    context = _context("contract-forgery")
    request, _ = _request(
        context,
        advance_ref="advance:contract-forgery",
        additions=(_receipt(2),),
    )
    snapshot = request.snapshot

    for changes, match in (
        ({"assurance": "evidence_bound"}, "assurance is invalid"),
        (
            {"profile": "pheroos.commit.certified.v1"},
            "profile and assurance are mismatched",
        ),
        ({"revision": 0}, "revision or step continuity"),
        ({"current_step": -1}, "integer bound"),
        ({"parent_revision": 1}, "parent revision is not contiguous"),
        (
            {"parent_transition_id": "transition:not-genesis"},
            "genesis parent transition",
        ),
        (
            {"parent_snapshot_root": _root("not-genesis")},
            "genesis parent root",
        ),
        ({"stream_ref": "authority:forged"}, "stream or transition identity"),
        ({"receipt_root": _root("forged")}, "receipt_root is mismatched"),
        (
            {
                "receipts": (
                    replace(_receipt(2), target_ref=_DONOR_TARGET_REF, receipt_root=""),
                )
            },
            "receipt target is mismatched",
        ),
    ):
        with pytest.raises((TypeError, ValueError), match=match):
            replace(snapshot, snapshot_root="", **changes)  # type: ignore[arg-type]

    raw_receipts = snapshot.to_dict()["receipts"]
    assert type(raw_receipts) is list
    with pytest.raises(TypeError, match="exact array"):
        CommitReplaySnapshotV2.from_dict(
            {**snapshot.to_dict(), "receipts": tuple(raw_receipts)}
        )
    with pytest.raises(ValueError, match="assurance is unsupported"):
        CommitReplaySnapshotV2.from_dict(
            {
                **snapshot.to_dict(),
                "assurance": "unsupported",
                "snapshot_root": "",
            }
        )
    with pytest.raises(TypeError, match="exact snapshot"):
        replace(request, snapshot=object(), request_root="")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="cross-bound"):
        replace(request, target_ref=_DONOR_TARGET_REF, request_root="")
    with pytest.raises(ValueError, match="request_root is mismatched"):
        replace(request, request_root=_root("forged-request"))


def test_prepare_bounds_parent_continuity_and_collision_axes() -> None:
    context = _context("prepare-bounds")
    parent, _ = _request(
        context,
        advance_ref="advance:bounds-parent",
        additions=(_receipt(10),),
        current_step=2,
        observed_epoch=3,
    )
    base: dict[str, object] = {
        "domain_root": context.domain.domain_root,
        "scope_ref": context.domain.scope_ref,
        "manifest_root": _root("manifest"),
        "commit_policy_root": _root("commit-policy"),
        "profile": COMMIT_INTEGRITY_PROFILE_VERSION,
        "assurance": CommitAssurance.EVIDENCE_BOUND,
        "protocol_ref": "protocol:commit-state-v2",
        "run_ref": _RUN_REF,
        "target_ref": _TARGET_REF,
        "observed_epoch": 3,
        "advance_ref": "advance:bounds-child",
        "current_step": 3,
        "receipt_additions": (_receipt(11),),
        "parent_snapshot": parent.snapshot,
    }
    invalid: tuple[tuple[dict[str, object], str], ...] = (
        ({"assurance": "evidence_bound"}, "assurance is invalid"),
        ({"receipt_additions": [_receipt(11)]}, "exact tuple"),
        (
            {
                "receipt_additions": (
                    replace(
                        _receipt(11),
                        target_ref=_DONOR_TARGET_REF,
                        receipt_root="",
                    ),
                )
            },
            "addition target is mismatched",
        ),
        ({"parent_snapshot": object()}, "parent must be exact snapshot"),
        ({"manifest_root": _root("other-manifest")}, "parent context is mismatched"),
        ({"current_step": 1}, "current_step cannot move backwards"),
        ({"observed_epoch": 2}, "observed_epoch cannot move backwards"),
        (
            {"receipt_additions": (parent.snapshot.receipts[0],)},
            "no new receipt",
        ),
    )
    for changes, match in invalid:
        with pytest.raises((TypeError, ValueError), match=match):
            prepare_commit_replay_advance_v2(
                **{**base, **changes}  # type: ignore[arg-type]
            )

    with pytest.raises(ValueError, match="integer bound"):
        prepare_commit_replay_advance_v2(
            **{
                **base,
                "parent_snapshot": None,
                "observed_epoch": MAX_AUTHORITY_REVISION_V2 + 1,
            }  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="text bound"):
        prepare_commit_replay_advance_v2(
            **{
                **base,
                "parent_snapshot": None,
                "scope_ref": "界" * 2048,
            }  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="count exceeds"):
        prepare_commit_replay_advance_v2(
            **{
                **base,
                "parent_snapshot": None,
                "receipt_additions": (_receipt(99),) * 4097,
            }  # type: ignore[arg-type]
        )


def test_receipt_and_snapshot_preflight_reject_invalid_sequence_material() -> None:
    with pytest.raises(ValueError, match="record_id"):
        replace(_receipt(12), record_id="", receipt_root="")

    context = _context("snapshot-preflight")
    request, _ = _request(
        context,
        advance_ref="advance:snapshot-preflight",
        additions=(_receipt(13),),
    )
    with pytest.raises(TypeError, match="exact array or tuple"):
        replace(
            request.snapshot,
            receipts=iter(request.snapshot.receipts),  # type: ignore[arg-type]
            snapshot_root="",
        )
    with pytest.raises(ValueError, match="count exceeds"):
        replace(
            request.snapshot,
            receipts=[_receipt(13)] * 4097,
            snapshot_root="",
        )
    with pytest.raises(TypeError, match="non-canonical"):
        replace(
            request.snapshot,
            receipts=[object()],  # type: ignore[list-item]
            snapshot_root="",
        )

    parent, _ = _request(
        context,
        advance_ref="advance:source-collision-parent",
        additions=(_receipt(14),),
    )
    with pytest.raises(ValueError, match="collide with existing"):
        _request(
            context,
            advance_ref="advance:source-collision-child",
            additions=(parent.snapshot.receipts[0], _receipt(15)),
            parent=parent.snapshot,
            current_step=2,
        )


def test_verified_source_is_opaque_final_immutable_and_context_bound() -> None:
    context = _context("source-handle")
    request, source = _request(
        context,
        advance_ref="advance:source-handle",
        additions=(_receipt(20),),
    )
    assert repr(source) == "<VerifiedCommitReplaySourceV2 redacted>"
    assert copy(source) is source
    assert deepcopy(source) is source
    assert source.context_root.startswith("sha256:")
    with pytest.raises(AttributeError, match="immutable"):
        source.context_root = _root("forged")  # type: ignore[misc]
    with pytest.raises(TypeError, match="constructed directly"):
        VerifiedCommitReplaySourceV2()
    with pytest.raises(TypeError, match="final"):
        type("ForgedSource", (VerifiedCommitReplaySourceV2,), {})
    for operation in (
        source.__reduce__,
        lambda: source.__reduce_ex__(5),
        source.__getstate__,
        lambda: pickle.dumps(source),
    ):
        with pytest.raises(TypeError, match="not portable"):
            operation()

    session = open_commit_replay_authority_session_v2(context.capability, request)
    forged = object.__new__(VerifiedCommitReplaySourceV2)
    incomplete = advance_commit_replay_state_v2(
        request,
        source=forged,
        authority_session=session,
    )
    _assert_binding_failure(incomplete)
    object.__setattr__(forged, "_request", "not-a-request")
    object.__setattr__(forged, "_binding", "not-a-binding")
    malformed = advance_commit_replay_state_v2(
        request,
        source=forged,
        authority_session=session,
    )
    _assert_binding_failure(malformed)
    assert (
        context.store.load_head_v2(
            request.scope_ref,
            request.stream_ref,
        ).revision
        == 0
    )


def test_forged_source_material_cannot_bypass_context_or_addition_binding() -> None:
    context = _context("source-forgery")
    request, source = _request(
        context,
        advance_ref="advance:source-forgery",
        additions=(_receipt(21),),
    )
    session = open_commit_replay_authority_session_v2(context.capability, request)
    binding = object.__getattribute__(source, "_binding")

    mismatched_binding = replace(
        binding,
        manifest_root=_root("source-forged-manifest"),
        context_root="",
    )
    mismatched_binding = replace(
        mismatched_binding,
        context_root=_authority_root(
            "commit-replay-v2:source-context",
            mismatched_binding.body(),
        ),
    )
    mismatched_source = object.__new__(VerifiedCommitReplaySourceV2)
    object.__setattr__(
        mismatched_source,
        "_request",
        CommitReplayAdvanceRequestV2.from_dict(request.to_dict()),
    )
    object.__setattr__(mismatched_source, "_binding", mismatched_binding)
    mismatch = advance_commit_replay_state_v2(
        request,
        source=mismatched_source,
        authority_session=session,
    )
    _assert_binding_failure(mismatch)

    corrupt_source = object.__new__(VerifiedCommitReplaySourceV2)
    object.__setattr__(
        corrupt_source,
        "_request",
        CommitReplayAdvanceRequestV2.from_dict(request.to_dict()),
    )
    object.__setattr__(
        corrupt_source,
        "_binding",
        replace(binding, context_root=_root("corrupt-source-context")),
    )
    corrupt = advance_commit_replay_state_v2(
        request,
        source=corrupt_source,
        authority_session=session,
    )
    _assert_binding_failure(corrupt)

    parent, parent_source = _request(
        context,
        advance_ref="advance:source-forgery-parent",
        additions=(_receipt(22),),
    )
    parent_attempt, _ = _advance(context, parent, parent_source)
    assert parent_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    valid_child, valid_child_source = _request(
        context,
        advance_ref="advance:source-forgery-child",
        additions=(_receipt(23),),
        parent=parent.snapshot,
        current_step=2,
    )
    no_addition_snapshot = replace(
        valid_child.snapshot,
        receipts=parent.snapshot.receipts,
        receipt_root="",
        snapshot_root="",
    )
    no_addition_request = replace(
        valid_child,
        snapshot=no_addition_snapshot,
        request_root="",
    )
    child_binding = object.__getattribute__(valid_child_source, "_binding")
    no_addition_binding = replace(
        child_binding,
        addition_roots=(),
        request_root=no_addition_request.request_root,
        context_root="",
    )
    no_addition_binding = replace(
        no_addition_binding,
        context_root=_authority_root(
            "commit-replay-v2:source-context",
            no_addition_binding.body(),
        ),
    )
    no_addition_source = object.__new__(VerifiedCommitReplaySourceV2)
    object.__setattr__(
        no_addition_source,
        "_request",
        CommitReplayAdvanceRequestV2.from_dict(no_addition_request.to_dict()),
    )
    object.__setattr__(no_addition_source, "_binding", no_addition_binding)
    no_addition_session = open_commit_replay_authority_session_v2(
        context.capability,
        no_addition_request,
    )
    no_addition = advance_commit_replay_state_v2(
        no_addition_request,
        source=no_addition_source,
        authority_session=no_addition_session,
    )
    _assert_binding_failure(no_addition)
    assert no_addition.failure is not None
    assert no_addition.failure.path == "/source"


def test_commit_rehydrate_and_state_handle_reverify_every_observation() -> None:
    context = _context("state-handle")
    request, source = _request(
        context,
        advance_ref="advance:state-handle",
        additions=(_receipt(30),),
    )
    attempt, _ = _advance(context, request, source)
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    state = rehydrate_commit_replay_state_v2(
        request,
        domain=context.domain,
        state_reader=context.store,
    )
    assert repr(state) == "<VerifiedCommitReplayStateV2 redacted>"
    assert copy(state) is state
    assert deepcopy(state) is state
    assert state.snapshot == request.snapshot
    assert state.request_root == request.request_root
    assert state.stream_ref == request.stream_ref
    assert state.transition_id == request.transition_id
    assert state.receipt_root == (
        cast(Any, attempt.committed_transition).receipt.receipt_root
    )
    assert state.position is GovernanceCommitPositionV2.CURRENT
    assert commit_replay_state_is_current_v2(state)
    assert require_current_commit_replay_state_v2(state) == request.snapshot

    with pytest.raises(AttributeError, match="immutable"):
        state.request_root = _root("forged")  # type: ignore[misc]
    with pytest.raises(TypeError, match="constructed directly"):
        VerifiedCommitReplayStateV2()
    with pytest.raises(TypeError, match="final"):
        type("ForgedState", (VerifiedCommitReplayStateV2,), {})
    for operation in (
        state.__reduce__,
        lambda: state.__reduce_ex__(5),
        state.__getstate__,
        lambda: pickle.dumps(state),
    ):
        with pytest.raises(TypeError, match="not portable"):
            operation()


def test_exact_retry_survives_lost_response_revocation_and_no_source() -> None:
    context, store = _proxy_context("lost-response")
    request, source = _request(
        context,
        advance_ref="advance:lost-response",
        additions=(_receipt(40),),
    )
    session = open_commit_replay_authority_session_v2(context.capability, request)
    store.lost_response = True
    lost = advance_commit_replay_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert lost.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert (
        context.store.load_head_v2(
            request.scope_ref,
            request.stream_ref,
        ).revision
        == 1
    )

    revoked = revoke_governance_issuer_grant_v2(
        context.store,
        context.domain,
        context.grant.grant_ref,
        "transition:revoke-after-lost-response",
        4,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED
    commits_before_retry = store.atomic_commits
    recovered = advance_commit_replay_state_v2(
        request,
        source=None,
        authority_session=session,
    )
    assert recovered.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert recovered.committed_transition is not None
    assert store.atomic_commits == commits_before_retry


def test_new_transition_fails_after_grant_revocation_or_domain_retirement() -> None:
    revoked_context = _context("revoked-new-transition")
    revoked_request, revoked_source = _request(
        revoked_context,
        advance_ref="advance:revoked-new",
        additions=(_receipt(50),),
    )
    revoked_session = open_commit_replay_authority_session_v2(
        revoked_context.capability,
        revoked_request,
    )
    revoke = revoke_governance_issuer_grant_v2(
        revoked_context.store,
        revoked_context.domain,
        revoked_context.grant.grant_ref,
        "transition:revoke-before-advance",
        4,
    )
    assert revoke.disposition is GovernanceCommitDispositionV2.COMMITTED
    denied = advance_commit_replay_state_v2(
        revoked_request,
        source=revoked_source,
        authority_session=revoked_session,
    )
    _assert_binding_failure(
        denied,
        code=AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED,
    )

    retired_context = _context("retired-new-transition")
    retired_request, retired_source = _request(
        retired_context,
        advance_ref="advance:retired-new",
        additions=(_receipt(51),),
    )
    replay_session = open_commit_replay_authority_session_v2(
        retired_context.capability,
        retired_request,
    )
    grant_stream = governance_issuer_grant_stream_ref_v2(
        retired_context.domain.scope_ref,
        retired_context.grant.grant_ref,
    )
    retirement = GovernanceDomainRetirementRequestV2(
        domain_root=retired_context.domain.domain_root,
        scope_ref=retired_context.domain.scope_ref,
        run_ref=_RUN_REF,
        request_ref="request:retire-before-advance",
        transition_id="transition:retire-before-advance",
        stream_refs=(grant_stream,),
        reason_ref="reason:test-complete",
        observed_epoch=3,
    )
    retirement_session = open_governance_authority_session_v2(
        retired_context.capability,
        retirement,
    )
    sealed = retire_governance_domain_v2(
        retirement,
        authority_session=retirement_session,
    )
    assert sealed.disposition is GovernanceCommitDispositionV2.COMMITTED
    denied = advance_commit_replay_state_v2(
        retired_request,
        source=retired_source,
        authority_session=replay_session,
    )
    _assert_binding_failure(
        denied,
        code=AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
    )


def test_missing_finality_and_mismatched_parent_fail_before_new_write() -> None:
    context, store = _proxy_context("parent-failures")
    parent, _ = _commit_one(
        context,
        advance_ref="advance:parent-valid",
        additions=(_receipt(60),),
    )

    missing_parent, missing_source = _request(
        context,
        advance_ref="advance:missing-parent-child",
        additions=(_receipt(61),),
        parent=replace(
            parent.snapshot,
            advance_ref="advance:uncommitted-parent",
            transition_id=commit_replay_transition_id_v2(
                parent.stream_ref,
                "advance:uncommitted-parent",
            ),
            snapshot_root="",
        ),
        current_step=2,
    )
    store.missing_transitions.add(missing_parent.snapshot.parent_transition_id)
    missing, _ = _advance(context, missing_parent, missing_source)
    assert missing.disposition is GovernanceCommitDispositionV2.INVALID
    assert missing.failure is not None
    assert missing.failure.stage is GovernanceFailureStageV2.LOAD
    store.missing_transitions.clear()

    child, child_source = _request(
        context,
        advance_ref="advance:finality-child",
        additions=(_receipt(62),),
        parent=parent.snapshot,
        current_step=2,
    )
    store.finality_without_failure.add(parent.transition_id)
    finality, _ = _advance(context, child, child_source)
    assert finality.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert finality.failure is not None
    assert finality.failure.stage is GovernanceFailureStageV2.FINALITY
    store.finality_without_failure.clear()

    parent_view = context.base_store.load_commit_view_v2(
        parent.scope_ref,
        parent.stream_ref,
        parent.transition_id,
    )
    invalid_parent_view = GovernanceCommitViewV2(
        domain_root=context.domain.domain_root,
        scope_ref=parent.scope_ref,
        stream_ref=parent.stream_ref,
        transition_id=parent.transition_id,
        expected_receipt_root=None,
        disposition=GovernanceCommitDispositionV2.INVALID,
        failure=GovernanceFailureV2(
            code=AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            path="/snapshot/parent_transition_id",
            stage=GovernanceFailureStageV2.LOAD,
        ),
        committed_transition=None,
        position_observation=None,
        observed_revision=None,
        observed_head_root=None,
    )
    store.view_mutator = lambda view: (
        invalid_parent_view if view.transition_id == parent.transition_id else view
    )
    invalid_parent, _ = _advance(context, child, child_source)
    assert invalid_parent.disposition is GovernanceCommitDispositionV2.INVALID
    assert invalid_parent.failure is not None
    assert invalid_parent.failure.stage is GovernanceFailureStageV2.LOAD

    assert parent_view.committed_transition is not None
    parent_transition = parent_view.committed_transition.batch.transition
    assert parent_transition is not None
    malformed_parent_records = dict(parent_transition.state_records)
    malformed_parent_records.pop("snapshot")
    malformed_parent_view = _rebuild_committed_view(
        parent_view,
        state_records=malformed_parent_records,
    )
    store.view_mutator = lambda view: (
        malformed_parent_view if view.transition_id == parent.transition_id else view
    )
    malformed_parent, _ = _advance(context, child, child_source)
    assert malformed_parent.disposition is GovernanceCommitDispositionV2.INVALID
    assert malformed_parent.failure is not None
    assert malformed_parent.failure.stage is GovernanceFailureStageV2.LOAD
    store.view_mutator = lambda view: view

    alternate_parent, _ = _request(
        context,
        advance_ref=parent.advance_ref,
        additions=(_receipt(63),),
    )
    bound_elsewhere, bound_source = _request(
        context,
        advance_ref="advance:mismatched-parent-child",
        additions=(_receipt(64),),
        parent=alternate_parent.snapshot,
        current_step=2,
    )
    mismatch, _ = _advance(context, bound_elsewhere, bound_source)
    _assert_binding_failure(mismatch)
    assert (
        context.store.load_head_v2(
            parent.scope_ref,
            parent.stream_ref,
        ).revision
        == 1
    )


def _manual_child(
    child: CommitReplayAdvanceRequestV2,
    **snapshot_changes: object,
) -> CommitReplayAdvanceRequestV2:
    snapshot = replace(
        child.snapshot,
        snapshot_root="",
        **snapshot_changes,  # type: ignore[arg-type]
    )
    request_changes = {
        field: snapshot_changes[field]
        for field in (
            "domain_root",
            "scope_ref",
            "run_ref",
            "target_ref",
            "observed_epoch",
            "advance_ref",
            "transition_id",
            "stream_ref",
        )
        if field in snapshot_changes
    }
    return replace(
        child,
        snapshot=snapshot,
        request_root="",
        **request_changes,  # type: ignore[arg-type]
    )


def test_store_loaded_parent_enforces_immutable_monotonic_and_append_only_state() -> (
    None
):
    context = _context("parent-continuity")
    genesis, _ = _commit_one(
        context,
        advance_ref="advance:continuity-genesis",
        current_step=1,
    )
    parent, _ = _commit_one(
        context,
        advance_ref="advance:continuity-parent",
        additions=(_receipt(70),),
        parent=genesis.snapshot,
        current_step=2,
    )
    child, child_source = _request(
        context,
        advance_ref="advance:continuity-child",
        additions=(_receipt(71),),
        parent=parent.snapshot,
        current_step=3,
    )
    variants = (
        _manual_child(child, manifest_root=_root("forged-manifest")),
        _manual_child(child, current_step=1),
        _manual_child(child, receipts=(_receipt(71),), receipt_root=""),
    )
    expected_paths = (
        "/snapshot",
        "/snapshot/revision",
        "/snapshot/receipts",
    )
    for request, expected_path in zip(variants, expected_paths, strict=True):
        attempt, _ = _advance(context, request, source=child_source)
        _assert_binding_failure(attempt)
        assert attempt.failure is not None
        assert attempt.failure.path == expected_path
    assert (
        context.store.load_head_v2(
            parent.scope_ref,
            parent.stream_ref,
        ).revision
        == 2
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "not_mapping",
        "fields",
        "schema",
        "stream",
        "session_fields",
        "session_binding",
        "grant_ref",
    ),
)
def test_committed_state_and_session_material_fail_closed(
    mutation: str,
) -> None:
    context, store = _proxy_context(f"state-material-{mutation}")
    request, _ = _commit_one(
        context,
        advance_ref=f"advance:state-material:{mutation}",
        additions=(_receipt(80, suffix=f":{mutation}"),),
    )

    def mutate(view: GovernanceCommitViewV2) -> GovernanceCommitViewV2:
        assert view.committed_transition is not None
        transition = view.committed_transition.batch.transition
        assert transition is not None
        if mutation == "not_mapping":
            object.__setattr__(transition, "state_records", [])
            return view
        records = dict(transition.state_records)
        if mutation == "fields":
            records.pop("snapshot")
        elif mutation == "schema":
            records["schema"] = "unsupported"
        elif mutation == "stream":
            records["stream_ref"] = "authority:forged"
        else:
            binding = dict(cast(dict[str, Any], records["session_binding"]))
            if mutation == "session_fields":
                binding.pop("grant_root")
            elif mutation == "session_binding":
                binding["operation"] = GovernanceIssuerOperationV2.RETIRE_DOMAIN.value
            else:
                binding["grant_ref"] = ""
            records["session_binding"] = binding
        return _rebuild_committed_view(view, state_records=records)

    store.view_mutator = mutate
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
        rehydrate_commit_replay_state_v2(
            request.to_dict(),
            domain=context.domain,
            state_reader=context.store,
        )
    assert caught.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )


def test_canonical_consumer_views_reject_semantic_receipt_trace_and_read_set_forgery() -> (
    None
):
    context, store = _proxy_context("canonical-view-forgery")
    parent, _ = _commit_one(
        context,
        advance_ref="advance:canonical-parent",
        additions=(_receipt(85),),
    )
    child, _ = _commit_one(
        context,
        advance_ref="advance:canonical-child",
        additions=(_receipt(86),),
        parent=parent.snapshot,
        current_step=2,
    )
    parent_view = context.base_store.load_commit_view_v2(
        parent.scope_ref,
        parent.stream_ref,
        parent.transition_id,
    )
    child_view = context.base_store.load_commit_view_v2(
        child.scope_ref,
        child.stream_ref,
        child.transition_id,
    )
    assert parent_view.committed_transition is not None
    assert child_view.committed_transition is not None

    invalid_view = GovernanceCommitViewV2(
        domain_root=context.domain.domain_root,
        scope_ref=parent.scope_ref,
        stream_ref=parent.stream_ref,
        transition_id=parent.transition_id,
        expected_receipt_root=None,
        disposition=GovernanceCommitDispositionV2.INVALID,
        failure=GovernanceFailureV2(
            code=AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
            path="/transition_id",
            stage=GovernanceFailureStageV2.LOAD,
        ),
        committed_transition=None,
        position_observation=None,
        observed_revision=None,
        observed_head_root=None,
    )
    read_set = parent_view.committed_transition.batch.read_set
    mismatched_read_set = GovernanceAuthorityReadSetV2(
        entries=tuple(
            sorted(
                (
                    *read_set.entries,
                    GovernanceReadPreconditionV2(
                        stream_ref="authority:unexpected-dependency",
                        expected_revision=0,
                        expected_root=_root("unexpected-dependency"),
                    ),
                ),
                key=lambda item: item.stream_ref.encode("utf-8"),
            )
        )
    )
    event = parent_view.committed_transition.batch.trace_batch.events[0]
    mismatched_event = _replace_event_lineage(
        event,
        source_context_root=_root("wrong-trace-source"),
    )
    child_transition = child_view.committed_transition.batch.transition
    assert child_transition is not None

    variants = (
        invalid_view,
        _rebuild_committed_view(parent_view, read_set=mismatched_read_set),
        _rebuild_committed_view(
            parent_view,
            trace_events=(mismatched_event,),
        ),
        _rebuild_committed_view(
            parent_view,
            state_records=child_transition.state_records,
        ),
    )
    for forged in variants:
        store.view_mutator = _substitute_transition_view(
            forged,
            parent.transition_id,
        )
        with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
            rehydrate_commit_replay_state_v2(
                parent.to_dict(),
                domain=context.domain,
                state_reader=context.store,
            )
        assert caught.value.code is (
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
        )


def test_canonical_child_view_rechecks_continuity_and_source_lineage() -> None:
    context, store = _proxy_context("canonical-child-lineage")
    parent, _ = _commit_one(
        context,
        advance_ref="advance:lineage-parent",
        additions=(_receipt(87),),
    )
    child, _ = _commit_one(
        context,
        advance_ref="advance:lineage-child",
        additions=(_receipt(88),),
        parent=parent.snapshot,
        current_step=2,
    )
    child_view = context.base_store.load_commit_view_v2(
        child.scope_ref,
        child.stream_ref,
        child.transition_id,
    )
    assert child_view.committed_transition is not None
    transition = child_view.committed_transition.batch.transition
    assert transition is not None
    event = child_view.committed_transition.batch.trace_batch.events[0]

    forged_request = _manual_child(
        child,
        manifest_root=_root("lineage-forged-manifest"),
    )
    continuity_records = dict(transition.state_records)
    continuity_records.update(
        {
            "request_root": forged_request.request_root,
            "request": forged_request.to_dict(),
            "snapshot_root": forged_request.snapshot.snapshot_root,
            "snapshot": forged_request.snapshot.to_dict(),
        }
    )
    continuity_binding = dict(
        cast(dict[str, Any], continuity_records["session_binding"])
    )
    continuity_binding["request_root"] = forged_request.request_root
    continuity_records["session_binding"] = continuity_binding
    continuity_event_binding = dict(
        cast(dict[str, Any], event.lineage["session_binding"])
    )
    continuity_event_binding["request_root"] = forged_request.request_root
    continuity_event = _replace_event_lineage(
        event,
        request_root=forged_request.request_root,
        manifest_root=forged_request.snapshot.manifest_root,
        snapshot_root=forged_request.snapshot.snapshot_root,
        session_binding=continuity_event_binding,
    )
    continuity_view = _rebuild_committed_view(
        child_view,
        state_records=continuity_records,
        trace_events=(continuity_event,),
    )

    source_records = dict(transition.state_records)
    forged_source_root = _root("lineage-forged-source")
    source_records["source_context_root"] = forged_source_root
    source_event = _replace_event_lineage(
        event,
        source_context_root=forged_source_root,
    )
    source_view = _rebuild_committed_view(
        child_view,
        state_records=source_records,
        trace_events=(source_event,),
    )

    for forged in (continuity_view, source_view):
        store.view_mutator = _substitute_transition_view(
            forged,
            child.transition_id,
        )
        with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
            rehydrate_commit_replay_state_v2(
                child.to_dict(),
                domain=context.domain,
                state_reader=context.store,
            )
        assert caught.value.code is (
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
        )


def test_reconciliation_rejects_a_canonical_but_semantically_invalid_view() -> None:
    context, store = _proxy_context("canonical-reconciliation")
    request, attempt = _commit_one(
        context,
        advance_ref="advance:canonical-reconciliation",
        additions=(_receipt(89),),
    )
    assert attempt.committed_transition is not None
    base_view = context.base_store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    assert base_view.committed_transition is not None
    transition = base_view.committed_transition.batch.transition
    assert transition is not None
    malformed_records = dict(transition.state_records)
    malformed_records.pop("snapshot")
    forged = _rebuild_committed_view(
        base_view,
        state_records=malformed_records,
    )
    store.view_mutator = lambda _view: forged
    session = open_commit_replay_authority_session_v2(
        context.capability,
        request,
    )
    retry = advance_commit_replay_state_v2(
        request,
        source=None,
        authority_session=session,
    )
    assert retry.disposition is GovernanceCommitDispositionV2.INVALID
    assert retry.failure is not None
    assert retry.failure.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT
    )


def test_rehydration_uses_returned_committed_request_not_lookup_arguments() -> None:
    context, store = _proxy_context("returned-request")
    requested, _ = _commit_one(
        context,
        advance_ref="advance:requested",
        additions=(_receipt(90),),
    )
    donor, _ = _commit_one(
        context,
        advance_ref="advance:donor",
        additions=(_receipt(91, target_ref=_DONOR_TARGET_REF),),
        target_ref=_DONOR_TARGET_REF,
    )
    donor_view = context.base_store.load_commit_view_v2(
        donor.scope_ref,
        donor.stream_ref,
        donor.transition_id,
    )

    def substitute(view: GovernanceCommitViewV2) -> GovernanceCommitViewV2:
        if view.transition_id == requested.transition_id:
            return donor_view
        return view

    store.view_mutator = substitute
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
        rehydrate_commit_replay_state_v2(
            requested.to_dict(),
            domain=context.domain,
            state_reader=context.store,
        )
    assert caught.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    assert caught.value.path == "/request_root"


def test_rehydrate_and_operation_inputs_are_exact_and_typed() -> None:
    context = _context("typed-inputs")
    request, source = _request(
        context,
        advance_ref="advance:typed-inputs",
        additions=(_receipt(100),),
    )
    with pytest.raises(TypeError, match="exact advance request"):
        open_commit_replay_authority_session_v2(
            context.capability,
            request.to_dict(),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="exact advance request"):
        advance_commit_replay_state_v2(request.to_dict())  # type: ignore[arg-type]

    session = open_commit_replay_authority_session_v2(context.capability, request)
    missing_session = advance_commit_replay_state_v2(
        request,
        source=source,
        authority_session=None,
    )
    _assert_binding_failure(
        missing_session,
        code=AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED,
    )
    accepted = advance_commit_replay_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert accepted.disposition is GovernanceCommitDispositionV2.COMMITTED

    with pytest.raises(TypeError, match="exact AuthorityDomainV2"):
        rehydrate_commit_replay_state_v2(
            request.to_dict(),
            domain=request,  # type: ignore[arg-type]
            state_reader=context.store,
        )
    with pytest.raises(TypeError, match="StateReader v2"):
        rehydrate_commit_replay_state_v2(
            request.to_dict(),
            domain=context.domain,
            state_reader=object(),  # type: ignore[arg-type]
        )
    other_domain = _domain("typed-inputs-other")
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as scope:
        rehydrate_commit_replay_state_v2(
            request.to_dict(),
            domain=other_domain,
            state_reader=context.store,
        )
    assert scope.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as malformed:
        rehydrate_commit_replay_state_v2(
            {**request.to_dict(), "request_root": _root("forged")},
            domain=context.domain,
            state_reader=context.store,
        )
    assert malformed.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH

    forged_state = object.__new__(VerifiedCommitReplayStateV2)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        require_current_commit_replay_state_v2(object())
    assert not commit_replay_state_is_current_v2(forged_state)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        require_current_commit_replay_state_v2(forged_state)
    object.__setattr__(forged_state, "_reader", context.store)
    object.__setattr__(forged_state, "_domain", context.domain)
    object.__setattr__(forged_state, "_request", "not-a-request")
    object.__setattr__(forged_state, "_receipt_root", 1)
    assert not commit_replay_state_is_current_v2(forged_state)


def test_currentness_rechecks_historical_parent_and_finality() -> None:
    context, store = _proxy_context("currentness-parent")
    parent, _ = _commit_one(
        context,
        advance_ref="advance:currentness-parent",
        additions=(_receipt(110),),
    )
    child, _ = _commit_one(
        context,
        advance_ref="advance:currentness-child",
        additions=(_receipt(111),),
        parent=parent.snapshot,
        current_step=2,
    )
    state = rehydrate_commit_replay_state_v2(
        child.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    store.missing_transitions.add(parent.transition_id)
    assert not commit_replay_state_is_current_v2(state)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as missing:
        require_current_commit_replay_state_v2(state)
    assert missing.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    store.missing_transitions.clear()
    store.finality_without_failure.add(parent.transition_id)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as finality:
        rehydrate_commit_replay_state_v2(
            child.to_dict(),
            domain=context.domain,
            state_reader=context.store,
        )
    assert finality.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
    )


def test_rehydration_rejects_cross_stream_historical_parent_substitution() -> None:
    context, store = _proxy_context("historical-parent-substitution")
    parent, _ = _commit_one(
        context,
        advance_ref="advance:historical-parent",
        additions=(_receipt(115),),
    )
    child, _ = _commit_one(
        context,
        advance_ref="advance:historical-child",
        additions=(_receipt(116),),
        parent=parent.snapshot,
        current_step=2,
    )
    donor, _ = _commit_one(
        context,
        advance_ref="advance:historical-donor",
        additions=(_receipt(117, target_ref=_DONOR_TARGET_REF),),
        target_ref=_DONOR_TARGET_REF,
    )
    donor_view = context.base_store.load_commit_view_v2(
        donor.scope_ref,
        donor.stream_ref,
        donor.transition_id,
    )
    store.view_mutator = lambda view: (
        donor_view if view.transition_id == parent.transition_id else view
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
        rehydrate_commit_replay_state_v2(
            child.to_dict(),
            domain=context.domain,
            state_reader=context.store,
        )
    assert caught.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )


def test_epoch_deadline_boundary_and_overflow_are_fail_closed() -> None:
    boundary = _context(
        "deadline-boundary",
        expires_at_epoch=3,
        bind_epoch=3,
    )
    request, source = _request(
        boundary,
        advance_ref="advance:deadline-boundary",
        additions=(_receipt(120),),
        observed_epoch=3,
    )
    accepted, _ = _advance(boundary, request, source)
    assert accepted.disposition is GovernanceCommitDispositionV2.COMMITTED

    expired_domain = _domain("deadline-expired")
    expired_store = InMemoryGovernanceStateStoreV2((expired_domain,))
    expired_grant = _grant(expired_domain, expires_at_epoch=3)
    activated = activate_governance_issuer_grant_v2(
        expired_store,
        expired_domain,
        expired_grant,
        "transition:deadline-expired-grant",
        1,
    )
    assert activated.disposition is GovernanceCommitDispositionV2.COMMITTED
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as expired:
        bind_governance_issuer_capability_v2(
            expired_store,
            expired_domain,
            expired_grant,
            _RUN_REF,
            4,
        )
    assert expired.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED

    for value in (-1, True, MAX_AUTHORITY_REVISION_V2 + 1):
        with pytest.raises(ValueError, match="integer bound"):
            replace(_receipt(121), epoch=value, receipt_root="")  # type: ignore[arg-type]


def test_invalid_replay_receipts_collisions_and_noncanonical_wire_fail_closed() -> None:
    first = _receipt(130)
    for conflicting in (
        _receipt(131, suffix=":nonce"),
        _receipt(132, suffix=":record"),
        _receipt(133, suffix=":payload"),
    ):
        if "nonce" in conflicting.record_id:
            conflicting = replace(conflicting, nonce=first.nonce, receipt_root="")
        elif "record" in conflicting.record_id:
            conflicting = replace(
                conflicting,
                record_id=first.record_id,
                receipt_root="",
            )
        else:
            conflicting = replace(
                conflicting,
                payload_fingerprint=first.payload_fingerprint,
                receipt_root="",
            )
        with pytest.raises(ValueError, match="collision"):
            canonical_commit_replay_receipts_v2((first, conflicting))

    receipt_wire = first.to_dict()
    receipt_wire["receipt_root"] = ""
    with pytest.raises(ValueError, match="not canonical wire"):
        CommitReplayReceiptV2.from_dict(receipt_wire)
    with pytest.raises(ValueError, match="fields are invalid"):
        CommitReplayReceiptV2.from_dict({**first.to_dict(), "unexpected": True})
    with pytest.raises(ValueError, match="payload_fingerprint"):
        replace(first, payload_fingerprint="not-a-root", receipt_root="")
