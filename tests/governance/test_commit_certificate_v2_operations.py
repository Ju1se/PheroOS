from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
from dataclasses import replace
from hashlib import sha256
import hmac
import json
import pickle
from threading import Barrier

import pytest

from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from tests.governance._commit_certificate_v2_decision_support import (
    finalize_certified_decision,
    heartbeat_certified_decision,
    sealed_certified_decision,
)
from tests.governance._commit_certificate_v2_store_support import (
    _capability,
    _root,
    certified_context,
)
from tests.governance._commit_certificate_v2_race_support import (
    DependencyRaceStoreV2,
    advance_principal_verification_only_v2,
)

from pheroos.governance._commit_certificate_v2.state_handle import (
    _verified_commit_certificate_finality_context_material_v2,
    _verified_commit_certificate_finality_context_v2,
)
from pheroos.governance.authority_session_v2 import (
    governance_issuer_grant_stream_ref_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2
from pheroos.governance.commit_certificate_v2 import (
    CommitCertificateAuthorityRoleV2,
    CommitCertificateMutationKindV2,
    CommitCertificateStatusV2,
    VerifiedCommitCertificateStateV2,
    advance_commit_certificate_v2,
    commit_certificate_state_is_current_v2,
    open_commit_certificate_authority_session_v2,
    prepare_commit_certificate_v2,
    rehydrate_commit_certificate_state_v2,
    require_current_commit_certificate_state_v2,
    verified_commit_certificate_finality_input_v2,
)
from pheroos.governance._commit_finality_v2 import (
    CommitFinalityOwnerV2,
    CommitFinalityStatusV2,
)


class _DiscoveryVerifier:
    def verify_commit_certificate_attestation_v2(
        self,
        *,
        issuer_ref: str,
        attestation_ref: str,
        body_root: str,
    ) -> bool:
        return bool(issuer_ref and attestation_ref and body_root)


class _DigestVerifier:
    @staticmethod
    def attestation_ref(issuer_ref: str, body_root: str) -> str:
        digest = sha256(
            issuer_ref.encode("utf-8") + b"\x00" + body_root.encode("ascii")
        ).hexdigest()
        return "attestation:sha256:" + digest

    def verify_commit_certificate_attestation_v2(
        self,
        *,
        issuer_ref: str,
        attestation_ref: str,
        body_root: str,
    ) -> bool:
        return hmac.compare_digest(
            attestation_ref,
            self.attestation_ref(issuer_ref, body_root),
        )


def _prepared_certificate(
    context,
    decision_state,
    *,
    mutation_ref: str,
    certificate_id: str = "certificate:portable:one",
    envelope_nonce: str = "nonce:portable:one",
    parent_state: object | None = None,
):
    common = {
        "decision_state": decision_state,
        "manifest": context.manifest,
        "certificate_id": certificate_id,
        "issuer_ref": context.grant.issuer_ref,
        "issued_at_step": decision_state.snapshot.current_step,
        "provenance_ref": "urn:test:certificate:portable",
        "envelope_nonce": envelope_nonce,
        "mutation_ref": mutation_ref,
        "parent_state": parent_state,
    }
    discovery, _ = prepare_commit_certificate_v2(
        trusted_verifier=_DiscoveryVerifier(),
        issuer_attestation_refs=("attestation:discovery",),
        **common,
    )
    verifier = _DigestVerifier()
    attestation = verifier.attestation_ref(
        context.grant.issuer_ref,
        discovery.certificate.body.body_root,
    )
    return prepare_commit_certificate_v2(
        trusted_verifier=verifier,
        issuer_attestation_refs=(attestation,),
        **common,
    )


def _commit_certificate(context, request, source):
    session = open_commit_certificate_authority_session_v2(
        _capability(context, request.observed_epoch),
        request,
    )
    attempt = advance_commit_certificate_v2(
        request,
        source=source,
        authority_session=session,
    )
    return attempt, session


def test_store_issuance_restart_exact_retry_finality_and_closed_read_set() -> None:
    context = certified_context("scope:certificate-v2:vertical")
    decision_state, inputs = sealed_certified_decision(
        context, _root("claim:certificate:vertical")
    )
    request, source = _prepared_certificate(
        context,
        decision_state,
        mutation_ref="mutation:certificate:verify",
    )
    attempt, session = _commit_certificate(context, request, source)
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert attempt.committed_transition is not None
    batch = attempt.committed_transition.batch
    body = request.certificate.body
    expected_streams = {
        request.stream_ref,
        body.decision_stream_ref,
        *(leaf.stream_ref for leaf in body.authority_leaves),
        governance_issuer_grant_stream_ref_v2(
            context.domain.scope_ref, context.grant.grant_ref
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    assert len(body.authority_leaves) == 8
    assert {leaf.role for leaf in body.authority_leaves} == set(
        CommitCertificateAuthorityRoleV2
    )
    assert body.seal_revision < body.decision_revision
    assert body.seal_transition_id != body.decision_transition_id
    assert {entry.stream_ref for entry in batch.read_set.entries} == expected_streams
    assert len(batch.read_set.entries) == 12
    assert batch.trace_batch.events[0].event_type == "commit_certificate_verified_v2"
    assert batch.trace_batch.events[0].lineage["read_set_root"] == batch.read_set.root()

    retry = advance_commit_certificate_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert retry.to_dict() == attempt.to_dict()
    restarted_store = (
        ReferenceGovernanceStateStoreConformanceAdapterV2().restart_store_v2(
            context.store
        )
    )
    restarted_context = replace(context, store=restarted_store)
    restarted_state = rehydrate_commit_certificate_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=restarted_store,
    )
    assert commit_certificate_state_is_current_v2(restarted_state)
    restarted_retry, _ = _commit_certificate(
        restarted_context,
        request,
        source,
    )
    assert restarted_retry.to_dict() == attempt.to_dict()

    state = rehydrate_commit_certificate_state_v2(
        json.loads(json.dumps(request.to_dict())),
        domain=context.domain,
        state_reader=context.store,
    )
    assert type(state) is VerifiedCommitCertificateStateV2
    assert state.position is GovernanceCommitPositionV2.CURRENT
    assert commit_certificate_state_is_current_v2(state)
    assert require_current_commit_certificate_state_v2(state).status is (
        CommitCertificateStatusV2.VERIFIED
    )
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(state)
    finality = _verified_commit_certificate_finality_context_v2(
        state,
        sealed_decision_state=decision_state,
        current_step=decision_state.snapshot.current_step + 1,
    )
    material = _verified_commit_certificate_finality_context_material_v2(finality)
    assert material.projection.owner is CommitFinalityOwnerV2.CERTIFICATE
    assert material.projection.status is CommitFinalityStatusV2.VERIFIED
    assert material.certificate_precondition.stream_ref == request.stream_ref
    assert material.certificate_receipt_root
    assert material.certificate_inclusion_root
    finality_input = verified_commit_certificate_finality_input_v2(
        state,
        sealed_decision_state=decision_state,
        current_step=decision_state.snapshot.current_step + 1,
    )
    assert copy.copy(finality_input) is finality_input
    assert copy.deepcopy(finality_input) is finality_input
    assert repr(finality_input) == "<VerifiedCommitFinalityInputV2 redacted>"
    with pytest.raises(TypeError, match="cannot be constructed"):
        type(finality_input)()
    with pytest.raises(TypeError, match="is final"):
        type("ForgedCommitFinalityInputV2", (type(finality_input),), {})
    incomplete = object.__new__(type(finality_input))
    with pytest.raises(TypeError, match="incomplete"):
        copy.copy(incomplete)
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(finality_input)
    terminal = finalize_certified_decision(
        context,
        decision_state,
        inputs,
        finality_input,
    ).snapshot
    assert terminal.outcome is not None
    assert terminal.outcome.kind.value == "evidence_commit"
    assert terminal.outcome.finality_root == material.projection.projection_root
    assert terminal.outcome.delivery_eligible

    revoked = revoke_governance_issuer_grant_v2(
        context.store,
        context.domain,
        context.grant.grant_ref,
        "transition:certificate:revoke-after-commit",
        99,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert (
        advance_commit_certificate_v2(
            request,
            source=source,
            authority_session=session,
        ).to_dict()
        == attempt.to_dict()
    )


def test_semantic_retry_records_new_envelope_without_changing_body_truth() -> None:
    context = certified_context("scope:certificate-v2:semantic-retry")
    decision_state, _ = sealed_certified_decision(
        context, _root("claim:certificate:semantic-retry")
    )
    first, first_source = _prepared_certificate(
        context,
        decision_state,
        mutation_ref="mutation:certificate:first",
    )
    first_attempt, _ = _commit_certificate(context, first, first_source)
    assert first_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    first_state = rehydrate_commit_certificate_state_v2(
        first,
        domain=context.domain,
        state_reader=context.store,
    )
    second, second_source = _prepared_certificate(
        context,
        decision_state,
        mutation_ref="mutation:certificate:reattest",
        certificate_id="certificate:portable:two",
        envelope_nonce="nonce:portable:two",
        parent_state=first_state,
    )
    second_attempt, _ = _commit_certificate(context, second, second_source)
    assert second_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert second_attempt.committed_transition is not None
    assert (
        second_attempt.committed_transition.batch.trace_batch.events[0].event_type
        == "commit_certificate_verified_v2"
    )
    state = rehydrate_commit_certificate_state_v2(
        second,
        domain=context.domain,
        state_reader=context.store,
    )
    snapshot = state.snapshot
    assert snapshot.revision == 2
    assert snapshot.mutation_kind is CommitCertificateMutationKindV2.SEMANTIC_RETRY
    assert snapshot.status is CommitCertificateStatusV2.VERIFIED
    assert first.certificate.body.body_root == second.certificate.body.body_root
    assert first.certificate.envelope_root != second.certificate.envelope_root
    assert len(snapshot.identity_bindings) == 2
    assert len(snapshot.envelope_roots) == 2


def test_store_conflict_drives_decision_safety_violation() -> None:
    context = certified_context("scope:certificate-v2:conflict-finality")
    decision_state, inputs = sealed_certified_decision(
        context,
        _root("claim:certificate:conflict-finality"),
    )
    first, first_source = _prepared_certificate(
        context,
        decision_state,
        mutation_ref="mutation:certificate:conflict:first",
    )
    first_attempt, _ = _commit_certificate(context, first, first_source)
    assert first_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    first_state = rehydrate_commit_certificate_state_v2(
        first,
        domain=context.domain,
        state_reader=context.store,
    )

    heartbeat = heartbeat_certified_decision(
        context,
        decision_state,
        inputs,
        mutation_ref="mutation:certificate:decision:conflict-heartbeat",
    )
    second, second_source = _prepared_certificate(
        context,
        heartbeat,
        mutation_ref="mutation:certificate:conflict:second",
        envelope_nonce="nonce:portable:conflict",
        parent_state=first_state,
    )
    second_attempt, _ = _commit_certificate(context, second, second_source)
    assert second_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    conflict_state = rehydrate_commit_certificate_state_v2(
        second,
        domain=context.domain,
        state_reader=context.store,
    )
    assert conflict_state.snapshot.status is CommitCertificateStatusV2.CONFLICT
    finality_context = _verified_commit_certificate_finality_context_v2(
        conflict_state,
        sealed_decision_state=heartbeat,
        current_step=heartbeat.snapshot.current_step + 1,
    )
    finality_material = _verified_commit_certificate_finality_context_material_v2(
        finality_context
    )
    assert finality_material.projection.status is CommitFinalityStatusV2.CONFLICT
    finality_input = verified_commit_certificate_finality_input_v2(
        conflict_state,
        sealed_decision_state=heartbeat,
        current_step=heartbeat.snapshot.current_step + 1,
    )
    terminal = finalize_certified_decision(
        context,
        heartbeat,
        inputs,
        finality_input,
        mutation_ref="mutation:certificate:decision:conflict-finalize",
    ).snapshot
    assert terminal.outcome is not None
    assert terminal.outcome.kind.value == "safety_violation"
    assert terminal.outcome.finality_root == (
        finality_material.projection.projection_root
    )
    assert terminal.outcome.delivery_eligible


class _SameShapeSource:
    def __init__(self, request_root: str) -> None:
        self.request_root = request_root


def test_forged_source_and_atomic_principal_verification_race_fail_closed() -> None:
    context = certified_context("scope:certificate-v2:pv-race")
    decision_state, inputs = sealed_certified_decision(
        context, _root("claim:certificate:pv-race")
    )
    request, source = _prepared_certificate(
        context,
        decision_state,
        mutation_ref="mutation:certificate:pv-race",
    )
    forged_session = open_commit_certificate_authority_session_v2(
        _capability(context, request.observed_epoch), request
    )
    forged = advance_commit_certificate_v2(
        request,
        source=_SameShapeSource(request.request_root),
        authority_session=forged_session,
    )
    assert forged.disposition is GovernanceCommitDispositionV2.INVALID
    assert (
        context.store.load_head_v2(request.scope_ref, request.stream_ref).revision == 0
    )

    raced_store = DependencyRaceStoreV2(context.store)
    raced_context = replace(context, store=raced_store)
    raced_store.armed_stream_ref = request.stream_ref
    raced_store.before_atomic = lambda: advance_principal_verification_only_v2(
        context, inputs.verification
    )
    raced, _ = _commit_certificate(raced_context, request, source)
    assert raced.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert raced.failure is not None
    assert raced.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    assert (
        context.store.load_head_v2(request.scope_ref, request.stream_ref).revision == 0
    )


def test_concurrent_identical_retry_and_conflicting_parent_have_one_truth() -> None:
    identical_context = certified_context("scope:certificate-v2:race-identical")
    identical_decision, _ = sealed_certified_decision(
        identical_context, _root("claim:certificate:race-identical")
    )
    request, source = _prepared_certificate(
        identical_context,
        identical_decision,
        mutation_ref="mutation:certificate:race-identical",
    )
    session = open_commit_certificate_authority_session_v2(
        _capability(identical_context, request.observed_epoch), request
    )
    barrier = Barrier(16)

    def commit_identical() -> object:
        barrier.wait()
        return advance_commit_certificate_v2(
            request, source=source, authority_session=session
        )

    with ThreadPoolExecutor(max_workers=16) as executor:
        attempts = tuple(executor.map(lambda _index: commit_identical(), range(16)))
    assert all(
        attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        for attempt in attempts
    )
    receipts = {
        attempt.committed_transition.receipt.receipt_root
        for attempt in attempts
        if attempt.committed_transition is not None
    }
    assert len(receipts) == 1

    conflict_context = certified_context("scope:certificate-v2:race-conflict")
    conflict_decision, _ = sealed_certified_decision(
        conflict_context, _root("claim:certificate:race-conflict")
    )
    first, first_source = _prepared_certificate(
        conflict_context,
        conflict_decision,
        mutation_ref="mutation:certificate:race:first",
        certificate_id="certificate:race:first",
    )
    second, second_source = _prepared_certificate(
        conflict_context,
        conflict_decision,
        mutation_ref="mutation:certificate:race:second",
        certificate_id="certificate:race:second",
    )
    first_session = open_commit_certificate_authority_session_v2(
        _capability(conflict_context, first.observed_epoch), first
    )
    second_session = open_commit_certificate_authority_session_v2(
        _capability(conflict_context, second.observed_epoch), second
    )
    start = Barrier(2)

    def commit_one(request_and_source: tuple[object, object, object]):
        candidate, candidate_source, candidate_session = request_and_source
        start.wait()
        return advance_commit_certificate_v2(
            candidate,
            source=candidate_source,
            authority_session=candidate_session,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        conflicting = tuple(
            executor.map(
                commit_one,
                (
                    (first, first_source, first_session),
                    (second, second_source, second_session),
                ),
            )
        )
    assert sorted(item.disposition.value for item in conflicting) == [
        GovernanceCommitDispositionV2.COMMITTED.value,
        GovernanceCommitDispositionV2.RETRY_REQUIRED.value,
    ]
    assert (
        conflict_context.store.load_head_v2(first.scope_ref, first.stream_ref).revision
        == 1
    )
