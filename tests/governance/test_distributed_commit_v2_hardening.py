from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import copy
from dataclasses import replace
from threading import Barrier

from tests.governance._commit_certificate_v2_race_support import (
    DependencyRaceStoreV2,
    advance_principal_verification_only_v2,
)
from tests.governance._commit_certificate_v2_store_support import (
    _capability,
    _root,
    certified_inputs,
)
from tests.governance._distributed_v2_store_support import (
    ASSURANCE,
    PROFILE,
    distributed_context,
)
from tests.governance.test_distributed_commit_v2_operations import (
    _commit_distributed,
)

from pheroos.governance._distributed_v2.source import (
    VerifiedDistributedAdvanceSourceV2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
)
from pheroos.governance.distributed_commit_v2 import (
    advance_distributed_commit_v2,
    open_distributed_authority_session_v2,
    prepare_distributed_epoch_v2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


class _SameShapeSource:
    __slots__ = ("request_root",)

    def __init__(self, request_root: str) -> None:
        self.request_root = request_root


def test_source_token_same_shape_copy_and_mutation_have_no_authority() -> None:
    context = distributed_context("scope:distributed-v2:source-forgery")
    inputs = certified_inputs(
        context,
        _root("claim:distributed:source-forgery"),
        profile=PROFILE,
        assurance=ASSURANCE,
    )
    request, source = prepare_distributed_epoch_v2(
        membership_state=inputs.membership,
        manifest=context.manifest,
        transition_certificate_ref="certificate:distributed:source-forgery",
        mutation_ref="mutation:distributed:source-forgery",
        mutation_issuer_ref=context.grant.issuer_ref,
        current_step=10,
        provenance_ref="urn:test:distributed:source-forgery",
        source_trace_roots=(_root("trace:distributed:source-forgery"),),
    )
    session = open_distributed_authority_session_v2(
        _capability(context, request.observed_epoch), request
    )
    for forged in (_SameShapeSource(request.request_root), object()):
        attempt = advance_distributed_commit_v2(
            request, source=forged, authority_session=session
        )
        assert attempt.disposition is GovernanceCommitDispositionV2.INVALID
    assert copy(source) is source

    clone = object.__new__(VerifiedDistributedAdvanceSourceV2)
    for slot in ("_request", "_recipe", "_anchor_root", "_self_anchor", "_token"):
        object.__setattr__(clone, slot, object.__getattribute__(source, slot))
    copied = advance_distributed_commit_v2(
        request, source=clone, authority_session=session
    )
    assert copied.disposition is GovernanceCommitDispositionV2.INVALID

    other_request, mutated_source = prepare_distributed_epoch_v2(
        membership_state=inputs.membership,
        manifest=context.manifest,
        transition_certificate_ref="certificate:distributed:token-mutation",
        mutation_ref="mutation:distributed:token-mutation",
        mutation_issuer_ref=context.grant.issuer_ref,
        current_step=10,
        provenance_ref="urn:test:distributed:token-mutation",
        source_trace_roots=(_root("trace:distributed:token-mutation"),),
    )
    object.__setattr__(mutated_source, "_token", object())
    mutated = advance_distributed_commit_v2(
        other_request,
        source=mutated_source,
        authority_session=open_distributed_authority_session_v2(
            _capability(context, other_request.observed_epoch), other_request
        ),
    )
    assert mutated.disposition is GovernanceCommitDispositionV2.INVALID
    assert (
        context.store.load_head_v2(request.scope_ref, request.stream_ref).revision == 0
    )


def test_thirty_two_racers_commit_one_epoch_truth_and_reconcile_identical_retry() -> (
    None
):
    context = distributed_context("scope:distributed-v2:race-32")
    inputs = certified_inputs(
        context,
        _root("claim:distributed:race-32"),
        profile=PROFILE,
        assurance=ASSURANCE,
    )
    prepared = tuple(
        prepare_distributed_epoch_v2(
            membership_state=inputs.membership,
            manifest=context.manifest,
            transition_certificate_ref=f"certificate:distributed:race:{index}",
            mutation_ref=f"mutation:distributed:race:{index}",
            mutation_issuer_ref=context.grant.issuer_ref,
            current_step=10,
            provenance_ref=f"urn:test:distributed:race:{index}",
            source_trace_roots=(_root(f"trace:distributed:race:{index}"),),
        )
        for index in range(32)
    )
    sessions = tuple(
        open_distributed_authority_session_v2(
            _capability(context, request.observed_epoch), request
        )
        for request, _ in prepared
    )
    barrier = Barrier(32)

    def commit_one(index: int) -> GovernanceCommitAttemptV2:
        barrier.wait()
        request, source = prepared[index]
        return advance_distributed_commit_v2(
            request, source=source, authority_session=sessions[index]
        )

    with ThreadPoolExecutor(max_workers=32) as executor:
        attempts = tuple(executor.map(commit_one, range(32)))
    assert (
        sum(
            item.disposition is GovernanceCommitDispositionV2.COMMITTED
            for item in attempts
        )
        == 1
    )
    assert (
        sum(
            item.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
            for item in attempts
        )
        == 31
    )
    winner = next(
        item
        for item in attempts
        if item.disposition is GovernanceCommitDispositionV2.COMMITTED
    )
    assert winner.committed_transition is not None
    winner_index = attempts.index(winner)
    request, source = prepared[winner_index]
    identical = tuple(
        advance_distributed_commit_v2(
            request,
            source=source,
            authority_session=sessions[winner_index],
        )
        for _ in range(32)
    )
    assert all(item.to_dict() == winner.to_dict() for item in identical)


def test_principal_verification_only_atomic_dependency_race_requires_retry() -> None:
    context = distributed_context("scope:distributed-v2:pv-race")
    inputs = certified_inputs(
        context,
        _root("claim:distributed:pv-race"),
        profile=PROFILE,
        assurance=ASSURANCE,
    )
    request, source = prepare_distributed_epoch_v2(
        membership_state=inputs.membership,
        manifest=context.manifest,
        transition_certificate_ref="certificate:distributed:pv-race",
        mutation_ref="mutation:distributed:pv-race",
        mutation_issuer_ref=context.grant.issuer_ref,
        current_step=10,
        provenance_ref="urn:test:distributed:pv-race",
        source_trace_roots=(_root("trace:distributed:pv-race"),),
    )
    raced_store = DependencyRaceStoreV2(context.store)
    raced_context = replace(context, store=raced_store)
    raced_store.armed_stream_ref = request.stream_ref
    raced_store.before_atomic = lambda: advance_principal_verification_only_v2(
        context,
        inputs.verification,
        profile=PROFILE,
        assurance=ASSURANCE,
    )
    attempt, _ = _commit_distributed(raced_context, request, source)
    assert attempt.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert attempt.failure is not None
    assert attempt.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    assert (
        context.store.load_head_v2(request.scope_ref, request.stream_ref).revision == 0
    )


__all__: tuple[str, ...] = ()
