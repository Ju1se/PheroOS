from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from hashlib import sha256
import json
import pickle
from typing import Any, cast

import pytest

from pheroos.governance import (
    CommitAssurance,
    CommitReplayAdvanceRequestV2,
    CommitReplayReceiptV2,
    ReplayNamespace,
    VerifiedCommitReplayStateV2,
    advance_commit_replay_state_v2,
    commit_replay_state_is_current_v2,
    open_commit_replay_authority_session_v2,
    prepare_commit_replay_advance_v2,
    rehydrate_commit_replay_state_v2,
    require_current_commit_replay_state_v2,
)
from pheroos.governance._authority_v2 import (
    FAILURE_STAGE_AFTER_TRACE_STAGING_V2,
    InMemoryGovernanceStateStoreV2,
)
from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    governance_issuer_grant_stream_ref_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
)
from pheroos.protocol import COMMIT_INTEGRITY_PROFILE_VERSION
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    AuthorityDiagnosticCodeV2,
)


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class _Context:
    domain: AuthorityDomainV2
    store: InMemoryGovernanceStateStoreV2
    grant: GovernanceIssuerGrantV2
    capability: GovernanceIssuerCapabilityV2


def _context(*, failure_injector=None) -> _Context:
    domain = AuthorityDomainV2(
        policy_version=AUTHORITY_POLICY_VERSION_V2,
        profile=AUTHORITY_LOCAL_PROFILE_V2,
        wire_version=AUTHORITY_WIRE_VERSION_V2,
        canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref="scope:commit-replay-operations",
    )
    store = InMemoryGovernanceStateStoreV2((domain,), failure_injector=failure_injector)
    grant = GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:replay",
        grant_ref="grant:replay",
        grant_binding_ref=_root("grant-binding"),
        operations=(GovernanceIssuerOperationV2.ADVANCE_REPLAY,),
        target_refs=("target:replay",),
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100,
        revocation_generation=0,
    )
    activated = activate_governance_issuer_grant_v2(
        store, domain, grant, "transition:replay:grant", 1
    )
    assert activated.disposition is GovernanceCommitDispositionV2.COMMITTED
    capability = bind_governance_issuer_capability_v2(
        store, domain, grant, "run:replay", 3
    )
    return _Context(domain, store, grant, capability)


def _receipt(index: int, *, suffix: str = "") -> CommitReplayReceiptV2:
    return CommitReplayReceiptV2(
        namespace=ReplayNamespace.OBSERVATION,
        record_id=f"record:{index}{suffix}",
        nonce=f"nonce:{index}{suffix}",
        payload_fingerprint=_root(f"payload:{index}{suffix}"),
        target_ref="target:replay",
        candidate_ref="candidate:alpha",
        epoch=1,
        principal_ref="principal:scout",
    )


def _request(
    context: _Context,
    *,
    advance: str,
    additions: tuple[CommitReplayReceiptV2, ...],
    parent=None,
    step: int = 1,
):
    return prepare_commit_replay_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest_root=_root("manifest"),
        commit_policy_root=_root("policy"),
        profile=COMMIT_INTEGRITY_PROFILE_VERSION,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        protocol_ref="protocol:replay",
        run_ref="run:replay",
        target_ref="target:replay",
        observed_epoch=3,
        advance_ref=advance,
        current_step=step,
        receipt_additions=additions,
        parent_snapshot=parent,
    )


def _advance(context: _Context, request, source):
    session = open_commit_replay_authority_session_v2(context.capability, request)
    return advance_commit_replay_state_v2(
        request, source=source, authority_session=session
    ), session


def test_empty_genesis_commits_exact_state_trace_and_restart_wrapper() -> None:
    context = _context()
    request, source = _request(context, advance="advance:genesis", additions=())
    session = open_commit_replay_authority_session_v2(context.capability, request)

    raw = advance_commit_replay_state_v2(
        request, source=request.to_dict(), authority_session=session
    )
    assert raw.disposition is GovernanceCommitDispositionV2.INVALID
    assert (
        context.store.load_head_v2(
            context.domain.scope_ref, request.stream_ref
        ).revision
        == 0
    )

    attempt = advance_commit_replay_state_v2(
        request, source=source, authority_session=session
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert attempt.committed_transition is not None
    batch = attempt.committed_transition.batch
    assert {entry.stream_ref for entry in batch.read_set.entries} == {
        request.stream_ref,
        governance_issuer_grant_stream_ref_v2(
            context.domain.scope_ref, context.grant.grant_ref
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    event = batch.trace_batch.events[0]
    assert event.event_type == "commit_replay_advanced"
    assert event.lineage["read_set_root"] == batch.read_set.root()
    assert event.lineage["snapshot_root"] == request.snapshot.snapshot_root
    assert batch.transition is not None
    assert batch.transition.state_records["request_root"] == request.request_root

    restarted = InMemoryGovernanceStateStoreV2.from_snapshot_v2(
        context.store.snapshot_v2()
    )
    verified = rehydrate_commit_replay_state_v2(
        json.loads(request.canonical_bytes()),
        domain=context.domain,
        state_reader=restarted,
    )
    assert type(verified) is VerifiedCommitReplayStateV2
    assert verified.position is GovernanceCommitPositionV2.CURRENT
    assert commit_replay_state_is_current_v2(verified)
    assert require_current_commit_replay_state_v2(verified) == request.snapshot
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(verified)


def test_child_restart_stale_fork_and_exact_retry_after_revocation() -> None:
    context = _context()
    genesis, genesis_source = _request(context, advance="advance:genesis", additions=())
    committed_genesis, _ = _advance(context, genesis, genesis_source)
    assert committed_genesis.disposition is GovernanceCommitDispositionV2.COMMITTED

    child, child_source = _request(
        context,
        advance="advance:child",
        additions=(_receipt(1),),
        parent=genesis.snapshot,
        step=2,
    )
    fork, fork_source = _request(
        context,
        advance="advance:fork",
        additions=(_receipt(2),),
        parent=genesis.snapshot,
        step=2,
    )
    committed, child_session = _advance(context, child, child_source)
    stale, _ = _advance(context, fork, fork_source)
    assert committed.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert stale.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert stale.failure is not None
    assert stale.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE

    old = rehydrate_commit_replay_state_v2(
        genesis.to_dict(), domain=context.domain, state_reader=context.store
    )
    assert old.position is GovernanceCommitPositionV2.SUPERSEDED
    assert not commit_replay_state_is_current_v2(old)
    with pytest.raises(Exception, match="governance_read_set_stale"):
        require_current_commit_replay_state_v2(old)

    revoked = revoke_governance_issuer_grant_v2(
        context.store,
        context.domain,
        context.grant.grant_ref,
        "transition:replay:revoke",
        4,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED
    retry = advance_commit_replay_state_v2(
        child, source=None, authority_session=child_session
    )
    assert retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert retry.committed_transition is not None
    assert committed.committed_transition is not None
    assert (
        retry.committed_transition.receipt.receipt_root
        == committed.committed_transition.receipt.receipt_root
    )


def test_same_transition_different_body_conflicts_before_mutation() -> None:
    context = _context()
    first, first_source = _request(
        context, advance="advance:same", additions=(_receipt(1),)
    )
    accepted, _ = _advance(context, first, first_source)
    assert accepted.disposition is GovernanceCommitDispositionV2.COMMITTED
    conflicting, conflicting_source = _request(
        context, advance="advance:same", additions=(_receipt(2),)
    )
    conflict, _ = _advance(context, conflicting, conflicting_source)
    assert conflict.disposition is GovernanceCommitDispositionV2.INVALID
    assert conflict.failure is not None
    assert (
        conflict.failure.code
        is AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT
    )
    assert (
        context.store.load_head_v2(context.domain.scope_ref, first.stream_ref).revision
        == 1
    )


def test_atomic_failure_publishes_neither_state_nor_trace() -> None:
    armed = False

    def inject(stage, _batch):
        if armed and stage == FAILURE_STAGE_AFTER_TRACE_STAGING_V2:
            raise RuntimeError("injected")

    context = _context(failure_injector=inject)
    request, source = _request(context, advance="advance:atomic-failure", additions=())
    session = open_commit_replay_authority_session_v2(context.capability, request)
    armed = True
    attempt = advance_commit_replay_state_v2(
        request, source=source, authority_session=session
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert (
        context.store.load_head_v2(
            context.domain.scope_ref, request.stream_ref
        ).revision
        == 0
    )
    view = context.store.load_commit_view_v2(
        context.domain.scope_ref, request.stream_ref, request.transition_id
    )
    assert view.disposition is not GovernanceCommitDispositionV2.COMMITTED
    assert view.committed_transition is None


def test_portable_same_shape_and_direct_snapshot_never_grant_authority() -> None:
    context = _context()
    request, source = _request(
        context, advance="advance:source", additions=(_receipt(1),)
    )
    session = open_commit_replay_authority_session_v2(context.capability, request)
    for candidate in (None, request.snapshot, request.to_dict(), _root("source")):
        attempt = advance_commit_replay_state_v2(
            request, source=candidate, authority_session=session
        )
        assert attempt.disposition is GovernanceCommitDispositionV2.INVALID
    accepted = advance_commit_replay_state_v2(
        request, source=source, authority_session=session
    )
    assert accepted.disposition is GovernanceCommitDispositionV2.COMMITTED
    with pytest.raises(Exception):
        rehydrate_commit_replay_state_v2(
            CommitReplayAdvanceRequestV2.from_dict(
                {**request.to_dict(), "request_root": _root("wrong")}
            ),
            domain=context.domain,
            state_reader=context.store,
        )


class _UntrustedViewStore:
    def __init__(self, store: GovernanceStateStoreV2, domain_root: str) -> None:
        self.store = store
        self.domain_root = domain_root
        self.finality_transition_ids: set[str] = set()
        self.view_mutator: Callable[[GovernanceCommitViewV2], None] | None = None
        self.atomic_commits = 0

    @property
    def state_store_version(self) -> str:
        return self.store.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        return self.store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(self, scope_ref: str, stream_ref: str):  # type: ignore[no-untyped-def]
        return self.store.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        if transition_id in self.finality_transition_ids:
            return GovernanceCommitViewV2(
                domain_root=self.domain_root,
                scope_ref=scope_ref,
                stream_ref=stream_ref,
                transition_id=transition_id,
                expected_receipt_root=expected_receipt_root,
                disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
                failure=GovernanceFailureV2(
                    code=(AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE),
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
        if self.view_mutator is not None:
            self.view_mutator(view)
        return view

    def atomic_commit_v2(self, batch: Any) -> GovernanceCommitAttemptV2:
        self.atomic_commits += 1
        return self.store.atomic_commit_v2(batch)


def _untrusted_view_context() -> tuple[_Context, _UntrustedViewStore]:
    base = _context()
    store = _UntrustedViewStore(base.store, base.domain.domain_root)
    capability = bind_governance_issuer_capability_v2(
        cast(GovernanceStateStoreV2, store),
        base.domain,
        base.grant,
        "run:replay",
        3,
    )
    return (
        _Context(base.domain, cast(Any, store), base.grant, capability),
        store,
    )


@pytest.mark.parametrize(
    "mutation",
    (
        "inclusion_delete",
        "inclusion_replace",
        "batch_delete",
        "position_forge",
    ),
)
def test_untrusted_commit_views_fail_closed_without_new_writes(
    mutation: str,
) -> None:
    context, store = _untrusted_view_context()
    request, source = _request(
        context,
        advance=f"advance:untrusted-view:{mutation}",
        additions=(_receipt(1, suffix=mutation),),
    )
    committed, _ = _advance(context, request, source)
    assert committed.disposition is GovernanceCommitDispositionV2.COMMITTED
    verified = rehydrate_commit_replay_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )

    def mutate(view: GovernanceCommitViewV2) -> None:
        assert view.committed_transition is not None
        committed_transition = view.committed_transition
        if mutation == "inclusion_delete":
            object.__setattr__(committed_transition, "inclusion_proof", None)
        elif mutation == "inclusion_replace":
            replacement = replace(
                committed_transition.inclusion_proof,
                transition_id="transition:foreign-inclusion",
                inclusion_root="",
            )
            object.__setattr__(
                committed_transition,
                "inclusion_proof",
                replacement,
            )
        elif mutation == "batch_delete":
            object.__setattr__(committed_transition, "batch", None)
        else:
            assert view.position_observation is not None
            forged = replace(
                view.position_observation,
                observed_revision=view.position_observation.observed_revision + 1,
                observed_head_root=_root("foreign-head"),
                position=GovernanceCommitPositionV2.SUPERSEDED,
                observation_root="",
            )
            object.__setattr__(view, "position_observation", forged)

    store.view_mutator = mutate
    store.atomic_commits = 0
    session = open_commit_replay_authority_session_v2(
        context.capability,
        request,
    )
    retried = advance_commit_replay_state_v2(
        request,
        source=None,
        authority_session=session,
    )
    assert retried.disposition is GovernanceCommitDispositionV2.INVALID
    assert retried.failure is not None
    assert retried.failure.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    assert store.atomic_commits == 0
    assert not commit_replay_state_is_current_v2(verified)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as current_caught:
        require_current_commit_replay_state_v2(verified)
    assert current_caught.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as rehydrate_caught:
        rehydrate_commit_replay_state_v2(
            request.to_dict(),
            domain=context.domain,
            state_reader=context.store,
        )
    assert rehydrate_caught.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    assert (
        context.store.load_head_v2(
            request.scope_ref,
            request.stream_ref,
        ).revision
        == 1
    )


def test_untrusted_commit_view_finality_is_typed_and_never_rewritten() -> None:
    context, store = _untrusted_view_context()
    request, source = _request(
        context,
        advance="advance:untrusted-finality",
        additions=(_receipt(1, suffix="finality"),),
    )
    committed, session = _advance(context, request, source)
    assert committed.disposition is GovernanceCommitDispositionV2.COMMITTED
    store.finality_transition_ids.add(request.transition_id)
    store.atomic_commits = 0

    retried = advance_commit_replay_state_v2(
        request,
        source=None,
        authority_session=session,
    )
    assert retried.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert retried.failure is not None
    assert retried.failure.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
        rehydrate_commit_replay_state_v2(
            request.to_dict(),
            domain=context.domain,
            state_reader=context.store,
        )
    assert caught.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
    )
    assert store.atomic_commits == 0
    assert (
        context.store.load_head_v2(
            request.scope_ref,
            request.stream_ref,
        ).revision
        == 1
    )
