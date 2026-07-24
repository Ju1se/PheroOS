"""Public-only Conformance matrix for durable Commit Replay v2."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from pheroos.conformance.checks._commit_replay_v2_public_support import (
    run_public_commit_replay_adversarial_matrix_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.report import CheckResult
from pheroos.governance.commit_state_v2 import (
    COMMIT_REPLAY_GENESIS_TRANSITION_ID_V2,
    CommitReplayAdvanceRequestV2,
    CommitReplayReceiptV2,
    CommitReplaySnapshotV2,
    ReplayNamespace,
    VerifiedCommitReplaySourceV2,
    VerifiedCommitReplayStateV2,
    advance_commit_replay_state_v2,
    commit_replay_state_is_current_v2,
    open_commit_replay_authority_session_v2,
    prepare_commit_replay_advance_v2,
    rehydrate_commit_replay_state_v2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceStateStoreV2,
)
from pheroos.protocol import COMMIT_INTEGRITY_PROFILE_VERSION, CommitAssurance
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


GOVERNANCE_COMMIT_REPLAY_CONFORMANCE_VERSION_V2 = (
    "pheroos-governance-commit-replay-conformance-v2"
)
_CHECK_NAME = "commit_replay_v2_contract"
_RUN_REF = "run:commit-replay-v2"
_TARGET_REF = "target:commit-replay-v2"


@dataclass(frozen=True, slots=True)
class _Context:
    domain: AuthorityDomainV2
    store: GovernanceStateStoreV2
    grant: GovernanceIssuerGrantV2
    capability: GovernanceIssuerCapabilityV2


@dataclass(frozen=True, slots=True)
class _SameShapeSource:
    """Public-shape imitation that must never satisfy source authority."""

    context_root: str


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def run_governance_commit_replay_conformance_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> CheckResult:
    """Run the active exact-version replay matrix without private oracles."""

    try:
        if not isinstance(adapter, GovernanceStateStoreConformanceAdapterV2):
            return CheckResult(_CHECK_NAME, False, "adapter_protocol")
        if adapter.conformance_version != GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2:
            return CheckResult(_CHECK_NAME, False, "adapter_version")
        if type(adapter.implementation_id) is not str or not adapter.implementation_id:
            return CheckResult(_CHECK_NAME, False, "adapter_implementation_id")
    except Exception as exc:
        return CheckResult(
            _CHECK_NAME, False, f"adapter_exception:{type(exc).__name__}"
        )
    problems: list[str] = []
    try:
        _vertical_restart_and_fork(adapter, problems)
        _source_and_determinism(adapter, problems)
        problems.extend(
            run_public_commit_replay_adversarial_matrix_v2(
                adapter,
                context_factory=_context,
                receipt_factory=_receipt,
                request_factory=_request,
                advance_factory=_advance,
            )
        )
    except Exception as exc:
        problems.append(f"adapter_exception:{type(exc).__name__}:{exc}")
    return CheckResult(_CHECK_NAME, not problems, ", ".join(problems))


def _context(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    suffix: str,
) -> _Context:
    domain = adapter.create_domain_v2(f"scope:commit-replay-v2:{suffix}")
    store = adapter.create_store_v2((domain,))
    grant = GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:commit-replay-v2",
        grant_ref="grant:commit-replay-v2",
        grant_binding_ref=_root("commit-replay-v2:grant-binding"),
        operations=(GovernanceIssuerOperationV2.ADVANCE_REPLAY,),
        target_refs=(_TARGET_REF,),
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100,
        revocation_generation=0,
    )
    activated = activate_governance_issuer_grant_v2(
        store, domain, grant, "transition:commit-replay-v2:grant", 1
    )
    if activated.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise RuntimeError("commit replay conformance grant activation failed")
    capability = bind_governance_issuer_capability_v2(store, domain, grant, _RUN_REF, 3)
    return _Context(domain, store, grant, capability)


def _receipt(index: int, *, suffix: str = "") -> CommitReplayReceiptV2:
    return CommitReplayReceiptV2(
        namespace=ReplayNamespace.OBSERVATION,
        record_id=f"record:{index}{suffix}",
        nonce=f"nonce:{index}{suffix}",
        payload_fingerprint=_root(f"payload:{index}{suffix}"),
        target_ref=_TARGET_REF,
        candidate_ref="candidate:alpha",
        epoch=1,
        principal_ref="principal:scout",
    )


def _request(
    context: _Context,
    *,
    advance_ref: str,
    receipt: CommitReplayReceiptV2 | None,
    current_step: int,
    parent: CommitReplaySnapshotV2 | None = None,
) -> tuple[CommitReplayAdvanceRequestV2, VerifiedCommitReplaySourceV2]:
    return prepare_commit_replay_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest_root=_root("manifest"),
        commit_policy_root=_root("commit-policy"),
        profile=COMMIT_INTEGRITY_PROFILE_VERSION,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        protocol_ref="protocol:commit-replay-v2",
        run_ref=_RUN_REF,
        target_ref=_TARGET_REF,
        observed_epoch=3,
        advance_ref=advance_ref,
        current_step=current_step,
        receipt_additions=() if receipt is None else (receipt,),
        parent_snapshot=parent,
    )


def _advance(
    context: _Context,
    request: CommitReplayAdvanceRequestV2,
    source: object,
) -> GovernanceCommitAttemptV2:
    session = open_commit_replay_authority_session_v2(context.capability, request)
    return advance_commit_replay_state_v2(
        request,
        source=source,
        authority_session=session,
    )


def _vertical_restart_and_fork(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = _context(adapter, "vertical")
    request, source = _request(
        context, advance_ref="advance:genesis", receipt=None, current_step=1
    )
    attempt = _advance(context, request, source)
    if (
        attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or attempt.committed_transition is None
    ):
        problems.append("genesis_commit")
        return
    batch = attempt.committed_transition.batch
    expected_streams = {
        request.stream_ref,
        governance_issuer_grant_stream_ref_v2(
            context.domain.scope_ref, context.grant.grant_ref
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    if {item.stream_ref for item in batch.read_set.entries} != expected_streams:
        problems.append("complete_read_set")
    event = batch.trace_batch.events[0]
    if (
        event.event_type != "commit_replay_advanced"
        or event.lineage.get("parent_transition_id")
        != COMMIT_REPLAY_GENESIS_TRANSITION_ID_V2
        or event.lineage.get("read_set_root") != batch.read_set.root()
        or event.lineage.get("snapshot_root") != request.snapshot.snapshot_root
    ):
        problems.append("atomic_trace")
    verified = rehydrate_commit_replay_state_v2(
        json.loads(request.canonical_bytes()),
        domain=context.domain,
        state_reader=context.store,
    )
    if (
        type(verified) is not VerifiedCommitReplayStateV2
        or verified.position is not GovernanceCommitPositionV2.CURRENT
        or not commit_replay_state_is_current_v2(verified)
    ):
        problems.append("rehydration")

    restarted = adapter.restart_store_v2(context.store)
    rebound = _Context(
        context.domain,
        restarted,
        context.grant,
        bind_governance_issuer_capability_v2(
            restarted, context.domain, context.grant, _RUN_REF, 3
        ),
    )
    parent = rehydrate_commit_replay_state_v2(
        request.to_dict(), domain=context.domain, state_reader=restarted
    )
    child_a, source_a = _request(
        rebound,
        advance_ref="advance:child:a",
        receipt=_receipt(2, suffix=":a"),
        current_step=2,
        parent=parent.snapshot,
    )
    child_b, source_b = _request(
        rebound,
        advance_ref="advance:child:b",
        receipt=_receipt(2, suffix=":b"),
        current_step=2,
        parent=parent.snapshot,
    )
    committed = _advance(rebound, child_a, source_a)
    stale = _advance(rebound, child_b, source_b)
    if committed.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        problems.append("restart_child")
    if (
        stale.disposition is not GovernanceCommitDispositionV2.RETRY_REQUIRED
        or stale.failure is None
        or stale.failure.code is not AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    ):
        problems.append("stale_fork")
    if commit_replay_state_is_current_v2(parent):
        problems.append("superseded_parent")
    exact = _advance(rebound, child_a, None)
    if (
        exact.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or exact.committed_transition is None
        or committed.committed_transition is None
        or exact.committed_transition.receipt.receipt_root
        != committed.committed_transition.receipt.receipt_root
    ):
        problems.append("exact_retry")


def _source_and_determinism(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    first = _context(adapter, "deterministic")
    request, source = _request(
        first, advance_ref="advance:deterministic", receipt=_receipt(9), current_step=1
    )
    session = open_commit_replay_authority_session_v2(first.capability, request)
    assert type(source) is VerifiedCommitReplaySourceV2
    for label, raw_source in (
        ("snapshot", request.snapshot),
        ("dict", request.to_dict()),
        ("digest", request.request_root),
        ("same_shape", _SameShapeSource(source.context_root)),
    ):
        raw = advance_commit_replay_state_v2(
            request, source=raw_source, authority_session=session
        )
        if raw.disposition is not GovernanceCommitDispositionV2.INVALID:
            problems.append(f"raw_source:{label}")
        if (
            first.store.load_head_v2(
                first.domain.scope_ref, request.stream_ref
            ).revision
            != 0
        ):
            problems.append(f"raw_source_mutation:{label}")
    accepted = advance_commit_replay_state_v2(
        request, source=source, authority_session=session
    )
    if accepted.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        problems.append("source_commit")

    conflicting, conflicting_source = _request(
        first,
        advance_ref="advance:deterministic",
        receipt=_receipt(10),
        current_step=1,
    )
    conflict = _advance(first, conflicting, conflicting_source)
    if (
        conflict.disposition is not GovernanceCommitDispositionV2.INVALID
        or conflict.failure is None
        or conflict.failure.code
        is not AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT
    ):
        problems.append("transition_conflict")
    if (
        first.store.load_head_v2(first.domain.scope_ref, request.stream_ref).revision
        != 1
    ):
        problems.append("transition_conflict_mutation")

    second = _context(adapter, "deterministic")
    repeated, repeated_source = _request(
        second, advance_ref="advance:deterministic", receipt=_receipt(9), current_step=1
    )
    repeated_attempt = _advance(second, repeated, repeated_source)
    if (
        repeated.to_dict() != request.to_dict()
        or repeated_attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or repeated_attempt.committed_transition is None
        or accepted.committed_transition is None
        or repeated_attempt.committed_transition.batch.trace_batch.events
        != accepted.committed_transition.batch.trace_batch.events
    ):
        problems.append("deterministic_transcript")


run_governance_commit_replay_conformance_v2.__module__ = "pheroos.conformance"


__all__ = [
    "GOVERNANCE_COMMIT_REPLAY_CONFORMANCE_VERSION_V2",
    "run_governance_commit_replay_conformance_v2",
]
