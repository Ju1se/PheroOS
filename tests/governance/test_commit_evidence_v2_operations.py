from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import pickle

import pytest

from pheroos.governance._commit_evidence_owner_v2.context import (
    commit_evidence_context_v2,
)
from pheroos.governance._commit_evidence_owner_v2.context_adapter import (
    _CommitEvidenceSubjectConflictErrorV2,
    _verified_commit_evidence_assessment_v2,
    _verified_commit_evidence_context_material_v2,
    _verified_commit_evidence_context_v2,
)
from pheroos.governance._commit_evidence_owner_v2.source_proof import (
    _verified_source,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.commit_evidence_v2 import (
    ChallengeResultV2,
    CommitEvidenceAttestationV2,
    CommitEvidenceKindV2,
    VerifiedCommitEvidenceStateV2,
    advance_commit_evidence_state_v2,
    commit_evidence_replay_receipts_for_proposals_v2,
    commit_evidence_state_is_current_v2,
    open_commit_evidence_authority_session_v2,
    prepare_commit_evidence_advance_v2,
    rehydrate_commit_evidence_state_v2,
    require_current_commit_evidence_state_v2,
)
from pheroos.governance.commit_state_v2 import (
    advance_commit_replay_state_v2,
    open_commit_replay_authority_session_v2,
    prepare_commit_replay_advance_v2,
    rehydrate_commit_replay_state_v2,
)
from pheroos.governance.support_v2 import (
    advance_principal_verification_set_v2,
    commit_membership_epoch_v2,
    open_membership_authority_session_v2,
    open_principal_verification_authority_session_v2,
    prepare_membership_commit_v2,
    rehydrate_principal_verification_set_state_v2,
)
from pheroos.protocol.commit_models import CommitAssurance
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2
from pheroos.trace import TraceEvent
from tests.governance.test_support_v2_operations import (
    PROFILE,
    RUN_REF,
    TARGET,
    _capability,
    _commit_upstreams,
    _context,
    _prepare_verification,
)


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode()).hexdigest()


def _attestations(*, claim_root: str, expires_at_step: int = 20):
    positive = CommitEvidenceAttestationV2(
        evidence_ref="evidence:positive",
        kind=CommitEvidenceKindV2.POSITIVE,
        candidate_ref="candidate:accept",
        claim_root=claim_root,
        epoch=1,
        principal_ref="principal:alpha",
        payload_root=_root("payload:positive"),
        source_ref="source:independent",
        independence_ref="independence:one",
        reported_quality_ppm=1_000_000,
        reported_relevance_ppm=1_000_000,
        reported_materiality_ppm=0,
        reported_criticality_ppm=0,
        category_ref="",
        execution_method="",
        execution_attestation_root="",
        execution_root="",
        challenge_result=ChallengeResultV2.NONE,
        result_root="",
        result_observation_roots=(),
        nonce="nonce:positive",
        observed_at_step=3,
        expires_at_step=expires_at_step,
        provenance_root=_root("provenance:positive"),
        trace_roots=(_root("trace:positive"),),
    )
    challenge = CommitEvidenceAttestationV2(
        evidence_ref="evidence:challenge",
        kind=CommitEvidenceKindV2.CHALLENGE,
        candidate_ref="candidate:accept",
        claim_root=claim_root,
        epoch=1,
        principal_ref="principal:alpha",
        payload_root=_root("payload:challenge"),
        source_ref="",
        independence_ref="",
        reported_quality_ppm=0,
        reported_relevance_ppm=0,
        reported_materiality_ppm=0,
        reported_criticality_ppm=0,
        category_ref="independent_replication",
        execution_method="deterministic-challenge-v2",
        execution_attestation_root=_root("execution-attestation"),
        execution_root=_root("execution"),
        challenge_result=ChallengeResultV2.NO_COUNTEREVIDENCE,
        result_root=_root("challenge-result"),
        result_observation_roots=(),
        nonce="nonce:challenge",
        observed_at_step=3,
        expires_at_step=expires_at_step,
        provenance_root=_root("provenance:challenge"),
        trace_roots=(_root("trace:challenge"),),
    )
    return positive, challenge


def _replay_grant(context) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        issuer_ref="issuer:replay:evidence",
        grant_ref="grant:replay:evidence",
        grant_binding_ref=_root("grant-binding:replay:evidence"),
        operations=(GovernanceIssuerOperationV2.ADVANCE_REPLAY,),
        target_refs=(TARGET,),
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100,
        revocation_generation=0,
    )


def _commit_replay(context, attestations):
    policy = commit_evidence_context_v2(
        context.manifest,
        profile=PROFILE,
        target_ref=TARGET,
    )
    grant = _replay_grant(context)
    activated = activate_governance_issuer_grant_v2(
        context.store,
        context.domain,
        grant,
        "transition:grant:replay:evidence",
        1,
    )
    assert activated.disposition is GovernanceCommitDispositionV2.COMMITTED
    receipts = commit_evidence_replay_receipts_for_proposals_v2(
        attestations,
        (),
        target_ref=TARGET,
    )
    request, source = prepare_commit_replay_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest_root=policy.manifest_root,
        commit_policy_root=policy.commit_policy_root,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        protocol_ref=policy.protocol_ref,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        advance_ref="advance:replay:evidence",
        current_step=3,
        receipt_additions=receipts,
    )
    capability = bind_governance_issuer_capability_v2(
        context.store,
        context.domain,
        grant,
        RUN_REF,
        1,
    )
    session = open_commit_replay_authority_session_v2(capability, request)
    attempt = advance_commit_replay_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    return request, rehydrate_commit_replay_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )


def _prepare_evidence(context, upstreams, replay_state, attestations, *, advance):
    return prepare_commit_evidence_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        epoch=1,
        observed_epoch=30,
        advance_ref=advance,
        current_step=4,
        mutation_issuer_ref=context.grant.issuer_ref,
        mutation_provenance_root=_root(f"mutation:{advance}"),
        mutation_trace_roots=(_root(f"trace:{advance}"),),
        principal_verification_state=upstreams.verification_state,
        membership_state=upstreams.membership_state,
        commit_replay_state=replay_state,
        attestations=attestations,
        dispositions=(),
    )


class _DependencyRaceStore:
    def __init__(self, store: GovernanceStateStoreV2) -> None:
        self.store = store
        self.armed_stream_ref = ""
        self.before_atomic = None

    @property
    def state_store_version(self):  # type: ignore[no-untyped-def]
        return self.store.state_store_version

    def load_head_v2(self, scope_ref, stream_ref):  # type: ignore[no-untyped-def]
        return self.store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(self, scope_ref, stream_ref):  # type: ignore[no-untyped-def]
        return self.store.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(  # type: ignore[no-untyped-def]
        self,
        scope_ref,
        stream_ref,
        transition_id,
        *,
        expected_receipt_root=None,
    ):
        return self.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    def atomic_commit_v2(self, batch):  # type: ignore[no-untyped-def]
        callback = self.before_atomic
        if batch.stream_ref == self.armed_stream_ref and callback is not None:
            self.before_atomic = None
            callback()
        return self.store.atomic_commit_v2(batch)


def _dependency_race_context(scope_ref: str):
    wrapper = None

    def wrap(store, _domain_root):  # type: ignore[no-untyped-def]
        nonlocal wrapper
        wrapper = _DependencyRaceStore(store)
        return wrapper

    context = _context(scope_ref=scope_ref, store_wrapper=wrap)
    assert wrapper is not None
    return context, wrapper


def test_store_commit_restart_exact_retry_and_opaque_context() -> None:
    context = _context(scope_ref="scope:commit-evidence-v2:vertical")
    upstreams = _commit_upstreams(context)
    claim_root = _root("claim:vertical")
    attestations = _attestations(claim_root=claim_root)
    replay_request, replay_state = _commit_replay(context, attestations)
    request, source = _prepare_evidence(
        context,
        upstreams,
        replay_state,
        attestations,
        advance="advance:evidence:genesis",
    )
    session = open_commit_evidence_authority_session_v2(
        _capability(context, context.grant, request.observed_epoch),
        request,
    )
    attempt = advance_commit_evidence_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert attempt.committed_transition is not None
    batch = attempt.committed_transition.batch
    assert {item.stream_ref for item in batch.read_set.entries} == {
        request.stream_ref,
        replay_request.stream_ref,
        upstreams.membership_request.stream_ref,
        upstreams.verification_request.stream_ref,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        governance_issuer_grant_stream_ref_v2(
            context.domain.scope_ref,
            context.grant.grant_ref,
        ),
    }
    assert batch.trace_batch.events[0].event_type == "commit_evidence_qualified_v2"
    assert batch.trace_batch.events[0].lineage["read_set_root"] == batch.read_set.root()

    retry = advance_commit_evidence_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert retry.to_dict() == attempt.to_dict()
    state = rehydrate_commit_evidence_state_v2(
        json.loads(request.canonical_bytes()),
        domain=context.domain,
        state_reader=context.store,
    )
    assert type(state) is VerifiedCommitEvidenceStateV2
    assert state.position is GovernanceCommitPositionV2.CURRENT
    assert commit_evidence_state_is_current_v2(state)
    assert require_current_commit_evidence_state_v2(state) == request.snapshot
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(state)

    verified_context = _verified_commit_evidence_context_v2(
        state,
        replay_state,
        current_step=4,
    )
    material = _verified_commit_evidence_context_material_v2(verified_context)
    assert material.active_subjects == (("candidate:accept", claim_root),)
    assert not material.subject_conflicts
    assert material.evidence_current
    assert material.membership_current
    assert material.verification_current
    assert material.verification_receipt_root
    rebound, evaluation = _verified_commit_evidence_assessment_v2(
        verified_context,
        candidate_ref="candidate:accept",
        claim_root=claim_root,
    )
    assert rebound.context_root == material.context_root
    assert evaluation.evaluated_at_step == 4
    with pytest.raises(Exception, match="evidence_subject"):
        _verified_commit_evidence_assessment_v2(
            verified_context,
            candidate_ref="candidate:accept",
            claim_root=_root("bogus-claim"),
        )


def test_unchanged_head_excludes_records_at_exact_ttl_boundary() -> None:
    context = _context(scope_ref="scope:commit-evidence-v2:ttl")
    upstreams = _commit_upstreams(context)
    claim_root = _root("claim:ttl")
    attestations = _attestations(claim_root=claim_root, expires_at_step=20)
    _, replay_state = _commit_replay(context, attestations)
    request, source = _prepare_evidence(
        context,
        upstreams,
        replay_state,
        attestations,
        advance="advance:evidence:ttl",
    )
    _verified_source(source)
    session = open_commit_evidence_authority_session_v2(
        _capability(context, context.grant, request.observed_epoch),
        request,
    )
    attempt = advance_commit_evidence_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED, (
        None if attempt.failure is None else attempt.failure.to_dict()
    )
    state = rehydrate_commit_evidence_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    before_boundary = _verified_commit_evidence_context_v2(
        state,
        replay_state,
        current_step=19,
    )
    _, before_evaluation = _verified_commit_evidence_assessment_v2(
        before_boundary,
        candidate_ref="candidate:accept",
        claim_root=claim_root,
    )
    assert before_evaluation.evaluated_at_step == 19
    verified_context = _verified_commit_evidence_context_v2(
        state,
        replay_state,
        current_step=20,
    )
    material = _verified_commit_evidence_context_material_v2(verified_context)
    assert material.projection.records == ()
    assert material.active_subjects == ()


def test_expired_dependencies_remain_cas_bound_but_cannot_be_assessed() -> None:
    context = _context(scope_ref="scope:commit-evidence-v2:expired-context")
    upstreams = _commit_upstreams(context)
    claim_root = _root("claim:expired-context")
    attestations = _attestations(claim_root=claim_root)
    _, replay_state = _commit_replay(context, attestations)
    request, source = _prepare_evidence(
        context,
        upstreams,
        replay_state,
        attestations,
        advance="advance:evidence:expired-context",
    )
    session = open_commit_evidence_authority_session_v2(
        _capability(context, context.grant, request.observed_epoch),
        request,
    )
    attempt = advance_commit_evidence_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    state = rehydrate_commit_evidence_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    before_boundary = _verified_commit_evidence_context_v2(
        state,
        replay_state,
        current_step=request.snapshot.membership_expires_at_step - 1,
    )
    before_material = _verified_commit_evidence_context_material_v2(before_boundary)
    assert before_material.evidence_current
    assert before_material.membership_current
    assert before_material.verification_current

    verified_context = _verified_commit_evidence_context_v2(
        state,
        replay_state,
        current_step=request.snapshot.membership_expires_at_step,
    )
    material = _verified_commit_evidence_context_material_v2(verified_context)
    assert not material.evidence_current
    assert not material.membership_current
    assert material.verification_current
    assert material.evidence_receipt_root
    assert material.replay_receipt_root
    assert material.membership_receipt_root
    assert material.verification_receipt_root
    assert material.projection.records == ()
    assert material.active_subjects == ()
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as captured:
        _verified_commit_evidence_assessment_v2(
            verified_context,
            candidate_ref="candidate:accept",
            claim_root=claim_root,
        )
    assert captured.value.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    assert captured.value.path == "/evidence_state/current_step"


def test_same_candidate_multiple_claims_is_typed_conflict() -> None:
    context = _context(scope_ref="scope:commit-evidence-v2:subject-conflict")
    upstreams = _commit_upstreams(context)
    first = _attestations(claim_root=_root("claim:first"))[0]
    second = _attestations(claim_root=_root("claim:second"))[0]
    second = replace(
        second,
        evidence_ref="evidence:positive:second",
        nonce="nonce:positive:second",
        attestation_root="",
    )
    attestations = (first, second)
    _, replay_state = _commit_replay(context, attestations)
    request, source = _prepare_evidence(
        context,
        upstreams,
        replay_state,
        attestations,
        advance="advance:evidence:subject-conflict",
    )
    session = open_commit_evidence_authority_session_v2(
        _capability(context, context.grant, request.observed_epoch),
        request,
    )
    attempt = advance_commit_evidence_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED, (
        None if attempt.failure is None else attempt.failure.to_dict()
    )
    state = rehydrate_commit_evidence_state_v2(
        request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    verified_context = _verified_commit_evidence_context_v2(
        state,
        replay_state,
        current_step=4,
    )
    material = _verified_commit_evidence_context_material_v2(verified_context)
    assert len(material.subject_conflicts) == 1
    with pytest.raises(_CommitEvidenceSubjectConflictErrorV2):
        _verified_commit_evidence_assessment_v2(
            verified_context,
            candidate_ref="candidate:accept",
            claim_root=_root("claim:first"),
        )


def test_replay_head_advance_between_validation_and_atomic_cas_is_retryable() -> None:
    context, race_store = _dependency_race_context(
        "scope:commit-evidence-v2:dependency-cas-race"
    )
    upstreams = _commit_upstreams(context)
    claim_root = _root("claim:dependency-cas-race")
    attestations = _attestations(claim_root=claim_root)
    replay_request, replay_state = _commit_replay(context, attestations)
    request, source = _prepare_evidence(
        context,
        upstreams,
        replay_state,
        attestations,
        advance="advance:evidence:dependency-cas-race",
    )
    session = open_commit_evidence_authority_session_v2(
        _capability(context, context.grant, request.observed_epoch),
        request,
    )

    extra = replace(
        attestations[0],
        evidence_ref="evidence:replay-race-extra",
        payload_root=_root("payload:replay-race-extra"),
        nonce="nonce:replay-race-extra",
        provenance_root=_root("provenance:replay-race-extra"),
        attestation_root="",
    )
    policy = commit_evidence_context_v2(
        context.manifest,
        profile=PROFILE,
        target_ref=TARGET,
    )
    successor_request, successor_source = prepare_commit_replay_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest_root=policy.manifest_root,
        commit_policy_root=policy.commit_policy_root,
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        protocol_ref=policy.protocol_ref,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=2,
        advance_ref="advance:replay:evidence:dependency-race",
        current_step=5,
        receipt_additions=commit_evidence_replay_receipts_for_proposals_v2(
            (extra,),
            (),
            target_ref=TARGET,
        ),
        parent_snapshot=replay_request.snapshot,
    )
    replay_grant = _replay_grant(context)
    successor_capability = bind_governance_issuer_capability_v2(
        context.base_store,
        context.domain,
        replay_grant,
        RUN_REF,
        successor_request.observed_epoch,
    )
    successor_session = open_commit_replay_authority_session_v2(
        successor_capability,
        successor_request,
    )

    def advance_replay() -> None:
        successor = advance_commit_replay_state_v2(
            successor_request,
            source=successor_source,
            authority_session=successor_session,
        )
        assert successor.disposition is GovernanceCommitDispositionV2.COMMITTED

    race_store.armed_stream_ref = request.stream_ref
    race_store.before_atomic = advance_replay
    raced = advance_commit_evidence_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert raced.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert raced.failure is not None
    assert raced.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    raced_view = context.store.load_commit_view_v2(
        context.domain.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    assert raced_view.committed_transition is None
    assert (
        context.store.load_head_v2(
            context.domain.scope_ref,
            request.stream_ref,
        ).revision
        == 0
    )


def test_verification_head_advance_between_validation_and_atomic_cas_is_retryable() -> (
    None
):
    context, race_store = _dependency_race_context(
        "scope:commit-evidence-v2:verification-cas-race"
    )
    upstreams = _commit_upstreams(context)
    attestations = _attestations(claim_root=_root("claim:verification-cas-race"))
    _, replay_state = _commit_replay(context, attestations)
    request, source = _prepare_evidence(
        context,
        upstreams,
        replay_state,
        attestations,
        advance="advance:evidence:verification-cas-race",
    )
    session = open_commit_evidence_authority_session_v2(
        _capability(context, context.grant, request.observed_epoch),
        request,
    )
    successor_request, successor_source = _prepare_verification(
        context,
        epoch=2,
        label="evidence-verification-cas-race",
        issuer_ref=context.grant.issuer_ref,
        parent=upstreams.verification_request.snapshot,
    )
    successor_capability = bind_governance_issuer_capability_v2(
        context.base_store,
        context.domain,
        context.grant,
        RUN_REF,
        successor_request.observed_epoch,
    )
    successor_session = open_principal_verification_authority_session_v2(
        successor_capability,
        successor_request,
    )

    def advance_verification() -> None:
        successor = advance_principal_verification_set_v2(
            successor_request,
            source=successor_source,
            authority_session=successor_session,
        )
        assert successor.disposition is GovernanceCommitDispositionV2.COMMITTED

    race_store.armed_stream_ref = request.stream_ref
    race_store.before_atomic = advance_verification
    raced = advance_commit_evidence_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert raced.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert raced.failure is not None
    assert raced.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    assert (
        context.store.load_head_v2(
            context.domain.scope_ref,
            request.stream_ref,
        ).revision
        == 0
    )


def test_membership_head_advance_between_validation_and_atomic_cas_is_retryable() -> (
    None
):
    context, race_store = _dependency_race_context(
        "scope:commit-evidence-v2:membership-cas-race"
    )
    upstreams = _commit_upstreams(context)
    attestations = _attestations(claim_root=_root("claim:membership-cas-race"))
    _, replay_state = _commit_replay(context, attestations)
    request, source = _prepare_evidence(
        context,
        upstreams,
        replay_state,
        attestations,
        advance="advance:evidence:membership-cas-race",
    )
    session = open_commit_evidence_authority_session_v2(
        _capability(context, context.grant, request.observed_epoch),
        request,
    )
    verification_request, verification_source = _prepare_verification(
        context,
        epoch=2,
        label="evidence-membership-cas-race",
        issuer_ref=context.grant.issuer_ref,
        parent=upstreams.verification_request.snapshot,
    )
    verification_capability = bind_governance_issuer_capability_v2(
        context.base_store,
        context.domain,
        context.grant,
        RUN_REF,
        verification_request.observed_epoch,
    )
    verification_session = open_principal_verification_authority_session_v2(
        verification_capability,
        verification_request,
    )

    def advance_membership_dependency() -> None:
        verification_attempt = advance_principal_verification_set_v2(
            verification_request,
            source=verification_source,
            authority_session=verification_session,
        )
        assert (
            verification_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        )
        verification_state = rehydrate_principal_verification_set_state_v2(
            verification_request.to_dict(),
            domain=context.domain,
            state_reader=context.base_store,
        )
        membership_request, membership_source = prepare_membership_commit_v2(
            domain_root=context.domain.domain_root,
            scope_ref=context.domain.scope_ref,
            manifest=context.manifest,
            profile=PROFILE,
            assurance=CommitAssurance.EVIDENCE_BOUND,
            run_ref=RUN_REF,
            target_ref=TARGET,
            epoch=2,
            observed_epoch=22,
            request_ref="request:membership:evidence-cas-race",
            snapshot_ref="snapshot:membership:evidence-cas-race",
            current_step=3,
            expires_at_step=80_000,
            mutation_issuer_ref=context.grant.issuer_ref,
            membership_method="store-current-verification-set-v2",
            provenance_ref="urn:test:membership:evidence-cas-race",
            source_trace_roots=(_root("trace:membership:evidence-cas-race"),),
            verification_state=verification_state,
            parent_snapshot=upstreams.membership_request.snapshot,
        )
        membership_capability = bind_governance_issuer_capability_v2(
            context.base_store,
            context.domain,
            context.grant,
            RUN_REF,
            membership_request.observed_epoch,
        )
        membership_session = open_membership_authority_session_v2(
            membership_capability,
            membership_request,
        )
        membership_attempt = commit_membership_epoch_v2(
            membership_request,
            source=membership_source,
            authority_session=membership_session,
        )
        assert membership_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED

    race_store.armed_stream_ref = request.stream_ref
    race_store.before_atomic = advance_membership_dependency
    raced = advance_commit_evidence_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert raced.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert raced.failure is not None
    assert raced.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    assert (
        context.store.load_head_v2(
            context.domain.scope_ref,
            request.stream_ref,
        ).revision
        == 0
    )


def test_commit_evidence_trace_contract_rejects_derived_root_and_shape_tamper() -> None:
    context = _context(scope_ref="scope:commit-evidence-v2:trace-tamper")
    upstreams = _commit_upstreams(context)
    attestations = _attestations(claim_root=_root("claim:trace-tamper"))
    _, replay_state = _commit_replay(context, attestations)
    request, source = _prepare_evidence(
        context,
        upstreams,
        replay_state,
        attestations,
        advance="advance:evidence:trace-tamper",
    )
    session = open_commit_evidence_authority_session_v2(
        _capability(context, context.grant, request.observed_epoch),
        request,
    )
    attempt = advance_commit_evidence_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert attempt.committed_transition is not None
    event = attempt.committed_transition.batch.trace_batch.events[0]
    event.validate()

    mutations = (
        ("source_context_root", _root("forged:source-context")),
        ("read_set_root", _root("forged:read-set")),
        ("mutation_delta_root", _root("forged:mutation-delta")),
        ("membership_head_root", _root("forged:membership-head")),
        ("parent_epoch", True),
    )
    for field, value in mutations:
        lineage = deepcopy(event.lineage)
        lineage[field] = value
        forged = TraceEvent(
            event_type=event.event_type,
            protocol_id=event.protocol_id,
            target=event.target,
            reason=event.reason,
            lineage=lineage,
        )
        with pytest.raises(ValueError):
            forged.validate()

    extended = deepcopy(event.lineage)
    extended["caller_extension"] = "not-authority"
    with pytest.raises(ValueError, match="not exact"):
        TraceEvent(
            event_type=event.event_type,
            protocol_id=event.protocol_id,
            target=event.target,
            reason=event.reason,
            lineage=extended,
        ).validate()


def test_32_conflicting_evidence_workers_linearize_one_genesis_head() -> None:
    context = _context(scope_ref="scope:commit-evidence-v2:race-conflicting")
    upstreams = _commit_upstreams(context)
    claim_root = _root("claim:race-conflicting")
    prototype = _attestations(claim_root=claim_root)[0]
    attestations = tuple(
        replace(
            prototype,
            evidence_ref=f"evidence:race:{index:02d}",
            payload_root=_root(f"payload:race:{index:02d}"),
            nonce=f"nonce:race:{index:02d}",
            provenance_root=_root(f"provenance:race:{index:02d}"),
            attestation_root="",
        )
        for index in range(32)
    )
    _, replay_state = _commit_replay(context, attestations)
    candidates = tuple(
        _prepare_evidence(
            context,
            upstreams,
            replay_state,
            (attestation,),
            advance=f"advance:evidence:race:{index:02d}",
        )
        for index, attestation in enumerate(attestations)
    )
    sessions = tuple(
        open_commit_evidence_authority_session_v2(
            _capability(context, context.grant, request.observed_epoch),
            request,
        )
        for request, _ in candidates
    )
    with ThreadPoolExecutor(max_workers=32) as executor:
        outcomes = tuple(
            executor.map(
                lambda item: advance_commit_evidence_state_v2(
                    item[0][0],
                    source=item[0][1],
                    authority_session=item[1],
                ),
                zip(candidates, sessions, strict=True),
            )
        )
    assert (
        sum(
            outcome.disposition is GovernanceCommitDispositionV2.COMMITTED
            for outcome in outcomes
        )
        == 1
    )
    assert all(
        outcome.disposition
        in (
            GovernanceCommitDispositionV2.COMMITTED,
            GovernanceCommitDispositionV2.RETRY_REQUIRED,
        )
        for outcome in outcomes
    )
    head = context.store.load_head_v2(
        context.domain.scope_ref, candidates[0][0].stream_ref
    )
    assert head.revision == 1
