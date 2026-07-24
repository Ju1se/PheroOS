from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import replace
import json
import pickle
from types import SimpleNamespace
from typing import Any, cast

import pytest

from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    governance_issuer_grant_stream_ref_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceStateReaderV2,
)
from pheroos.governance.commit_evidence_v2 import (
    ChallengeResultV2,
    CommitEvidenceAdvanceRequestV2,
    CommitEvidenceAttestationV2,
    CommitEvidenceDispositionV2,
    CommitEvidenceKindV2,
    CommitEvidenceRevocationV2,
    CommitEvidenceSnapshotV2,
    CounterevidenceDispositionProposalV2,
    VerifiedCommitEvidenceSourceV2,
    VerifiedCommitEvidenceStateV2,
    active_qualified_evidence_v2,
    advance_commit_evidence_state_v2,
    commit_evidence_replay_receipts_for_proposals_v2,
    commit_evidence_state_is_current_v2,
    open_commit_evidence_authority_session_v2,
    prepare_commit_evidence_advance_v2,
    project_current_commit_evidence_v2,
    rehydrate_commit_evidence_state_v2,
    require_current_commit_evidence_state_v2,
    verify_commit_evidence_request_source_v2,
)
from pheroos.governance.commit_decision_v2 import (
    CommitDecisionCandidateProposalV2,
    CommitDecisionCommandV2,
    prepare_commit_decision_initialize_v2,
    prepare_commit_decision_successor_v2,
)
from pheroos.governance.commit_state_v2 import (
    advance_commit_replay_state_v2,
    open_commit_replay_authority_session_v2,
    prepare_commit_replay_advance_v2,
    rehydrate_commit_replay_state_v2,
)
from pheroos.governance.support_v2 import (
    advance_principal_verification_set_v2,
    open_principal_verification_authority_session_v2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2
from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.commit_models import CommitAssurance
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from tests.governance.test_commit_evidence_v2_operations import (
    _attestations,
    _replay_grant,
    _root,
)
from tests.governance.test_commit_decision_v2_operations import (
    _commit_decision,
    _decision_context,
    _fresh_inputs,
)
from tests.governance.test_authority_store_v2_reference import _transition_batch
from tests.governance.test_support_v2_operations import (
    PROFILE,
    RUN_REF,
    TARGET,
    _activate_rotated_grant,
    _adversarial_context,
    _capability,
    _commit_upstreams,
    _context,
    _prepare_verification,
)


def _counter_attestation(
    *,
    claim_root: str,
    label: str,
) -> CommitEvidenceAttestationV2:
    positive, _challenge = _attestations(claim_root=claim_root)
    return replace(
        positive,
        evidence_ref=f"evidence:counter:{label}",
        kind=CommitEvidenceKindV2.COUNTER,
        payload_root=_root(f"payload:counter:{label}"),
        source_ref=f"source:counter:{label}",
        independence_ref=f"independence:counter:{label}",
        nonce=f"nonce:counter:{label}",
        provenance_root=_root(f"provenance:counter:{label}"),
        trace_roots=(_root(f"trace:counter:{label}"),),
        attestation_root="",
    )


def _disposition(
    counter: CommitEvidenceAttestationV2,
    *,
    label: str,
    disposition: CommitEvidenceDispositionV2 = (CommitEvidenceDispositionV2.UNRESOLVED),
    rebuttal_observation_roots: tuple[str, ...] = (),
    issued_at_step: int = 3,
    expires_at_step: int = 20,
    nonce: str | None = None,
) -> CounterevidenceDispositionProposalV2:
    return CounterevidenceDispositionProposalV2(
        disposition_ref=f"disposition:{label}",
        counter_attestation_root=counter.attestation_root,
        disposition=disposition,
        rebuttal_observation_roots=rebuttal_observation_roots,
        resolution_root=(
            ""
            if disposition is CommitEvidenceDispositionV2.UNRESOLVED
            else _root(f"resolution:{label}")
        ),
        reason_codes=(f"reason:{label}",),
        nonce=nonce or f"nonce:disposition:{label}",
        issued_at_step=issued_at_step,
        expires_at_step=expires_at_step,
        provenance_root=_root(f"provenance:disposition:{label}"),
        trace_roots=(_root(f"trace:disposition:{label}"),),
    )


def _commit_replay_public(
    context: Any,
    attestations: tuple[CommitEvidenceAttestationV2, ...],
    dispositions: tuple[CounterevidenceDispositionProposalV2, ...] = (),
    *,
    observed_epoch: int = 1,
    current_step: int = 3,
) -> tuple[Any, Any]:
    grant = _replay_grant(context)
    activated = activate_governance_issuer_grant_v2(
        context.store,
        context.domain,
        grant,
        f"transition:{context.domain.scope_ref}:replay-grant",
        1,
    )
    assert activated.disposition is GovernanceCommitDispositionV2.COMMITTED
    policy = context.manifest.collective_commit_policy
    assert policy is not None
    request, source = prepare_commit_replay_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest_root=context.manifest.manifest_root,
        commit_policy_root=commit_policy_fingerprint(policy, profile=PROFILE),
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        protocol_ref=context.manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=observed_epoch,
        advance_ref=(
            f"advance:replay:{context.domain.scope_ref}:{observed_epoch}:{current_step}"
        ),
        current_step=current_step,
        receipt_additions=commit_evidence_replay_receipts_for_proposals_v2(
            attestations,
            dispositions,
            target_ref=TARGET,
        ),
    )
    capability = bind_governance_issuer_capability_v2(
        context.store,
        context.domain,
        grant,
        RUN_REF,
        request.observed_epoch,
    )
    session = open_commit_replay_authority_session_v2(capability, request)
    attempt = advance_commit_replay_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    return request, rehydrate_commit_replay_state_v2(
        request,
        domain=context.domain,
        state_reader=context.store,
    )


def _prepare(
    context: Any,
    upstreams: Any,
    replay_state: Any,
    *,
    label: str,
    attestations: tuple[CommitEvidenceAttestationV2, ...] = (),
    dispositions: tuple[CounterevidenceDispositionProposalV2, ...] = (),
    revocations: tuple[CommitEvidenceRevocationV2, ...] = (),
    parent_snapshot: CommitEvidenceSnapshotV2 | None = None,
    current_step: int = 4,
    manifest: ScopedProtocolManifestV2 | None = None,
    profile: str = PROFILE,
    target_ref: str = TARGET,
    verification_state: object | None = None,
    membership_state: object | None = None,
) -> tuple[Any, VerifiedCommitEvidenceSourceV2]:
    return prepare_commit_evidence_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest if manifest is None else manifest,
        profile=profile,
        run_ref=RUN_REF,
        target_ref=target_ref,
        epoch=1,
        observed_epoch=30,
        advance_ref=f"advance:evidence:{label}",
        current_step=current_step,
        mutation_issuer_ref=context.grant.issuer_ref,
        mutation_provenance_root=_root(f"mutation:{label}"),
        mutation_trace_roots=(_root(f"trace:{label}"),),
        principal_verification_state=(
            upstreams.verification_state
            if verification_state is None
            else verification_state
        ),
        membership_state=(
            upstreams.membership_state if membership_state is None else membership_state
        ),
        commit_replay_state=replay_state,
        attestations=attestations,
        dispositions=dispositions,
        revocations=revocations,
        parent_snapshot=parent_snapshot,
    )


def _commit(
    context: Any,
    request: Any,
    source: VerifiedCommitEvidenceSourceV2,
) -> tuple[Any, VerifiedCommitEvidenceStateV2]:
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
    return attempt, rehydrate_commit_evidence_state_v2(
        request,
        domain=context.domain,
        state_reader=context.store,
    )


def _runtime(
    scope_ref: str,
    *,
    attestations: tuple[CommitEvidenceAttestationV2, ...] = (),
    dispositions: tuple[CounterevidenceDispositionProposalV2, ...] = (),
) -> tuple[Any, Any, Any, Any, VerifiedCommitEvidenceSourceV2]:
    context = _context(scope_ref=scope_ref)
    upstreams = _commit_upstreams(context)
    _replay_request, replay_state = _commit_replay_public(
        context,
        attestations,
        dispositions,
    )
    request, source = _prepare(
        context,
        upstreams,
        replay_state,
        label=scope_ref.rsplit(":", 1)[-1],
        attestations=attestations,
        dispositions=dispositions,
    )
    return context, upstreams, replay_state, request, source


def _clone_source(
    source: VerifiedCommitEvidenceSourceV2,
) -> VerifiedCommitEvidenceSourceV2:
    clone = object.__new__(VerifiedCommitEvidenceSourceV2)
    for name in VerifiedCommitEvidenceSourceV2.__slots__:
        object.__setattr__(clone, name, object.__getattribute__(source, name))
    return clone


def test_public_success_retry_rehydrate_projection_and_opaque_handles() -> None:
    claim_root = _root("claim:public-success")
    attestations = _attestations(claim_root=claim_root)
    context, _upstreams, _replay, request, source = _runtime(
        "scope:commit-evidence-v2:public-success",
        attestations=attestations,
    )
    verify_commit_evidence_request_source_v2(request, source=source)
    assert source.context_root.startswith("sha256:")
    assert repr(source) == "<VerifiedCommitEvidenceSourceV2 redacted>"
    with pytest.raises(TypeError, match="cannot be constructed"):
        VerifiedCommitEvidenceSourceV2()
    for serialize in (
        pickle.dumps,
        lambda item: item.__reduce__(),
        lambda item: item.__reduce_ex__(4),
        lambda item: item.__getstate__(),
    ):
        with pytest.raises(TypeError, match="not portable"):
            serialize(source)

    session = open_commit_evidence_authority_session_v2(
        _capability(context, context.grant, request.observed_epoch),
        request,
    )
    committed = advance_commit_evidence_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert committed.disposition is GovernanceCommitDispositionV2.COMMITTED
    retry = advance_commit_evidence_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert retry.to_dict() == committed.to_dict()

    state = rehydrate_commit_evidence_state_v2(
        json.loads(request.canonical_bytes()),
        domain=context.domain,
        state_reader=context.store,
    )
    assert repr(state) == "<VerifiedCommitEvidenceStateV2 redacted>"
    assert state.snapshot == request.snapshot
    assert state.request_root == request.request_root
    assert state.stream_ref == request.stream_ref
    assert state.transition_id == request.transition_id
    assert committed.committed_transition is not None
    assert state.receipt_root == committed.committed_transition.receipt.receipt_root
    assert state.position is GovernanceCommitPositionV2.CURRENT
    assert copy(state) is state
    assert deepcopy(state) is state
    assert commit_evidence_state_is_current_v2(state)
    assert require_current_commit_evidence_state_v2(state) == request.snapshot
    projection = project_current_commit_evidence_v2(state)
    assert projection.records == active_qualified_evidence_v2(request.snapshot)
    assert {item.record_ref for item in projection.records} == {
        "evidence:positive",
        "evidence:challenge",
    }
    for serialize in (
        pickle.dumps,
        lambda item: item.__reduce__(),
        lambda item: item.__reduce_ex__(4),
        lambda item: item.__getstate__(),
    ):
        with pytest.raises(TypeError, match="not portable"):
            serialize(state)


def test_empty_advance_is_authoritative_but_grants_no_evidence() -> None:
    context, _upstreams, _replay, request, source = _runtime(
        "scope:commit-evidence-v2:empty"
    )
    _attempt, state = _commit(context, request, source)
    assert request.snapshot.records == ()
    assert request.snapshot.mutation_record_roots == ()
    assert request.snapshot.active_record_count == 0
    assert active_qualified_evidence_v2(request.snapshot) == ()
    assert project_current_commit_evidence_v2(state).records == ()


def test_successor_revocation_rehydrates_full_history_and_removes_authority() -> None:
    claim_root = _root("claim:revocation")
    positive = _attestations(claim_root=claim_root)[0]
    context, upstreams, replay_state, parent_request, parent_source = _runtime(
        "scope:commit-evidence-v2:revocation",
        attestations=(positive,),
    )
    _parent_attempt, parent_state = _commit(context, parent_request, parent_source)
    record = parent_request.snapshot.records[0]
    revocation = CommitEvidenceRevocationV2(
        revocation_ref="revocation:public",
        record_ref=record.record_ref,
        record_root=record.record_root,
        revoked_at_step=5,
        reason_codes=("reason:withdrawn",),
        provenance_root=_root("provenance:revocation:public"),
        trace_roots=(_root("trace:revocation:public"),),
    )
    child_request, child_source = _prepare(
        context,
        upstreams,
        replay_state,
        label="revocation-child",
        revocations=(revocation,),
        parent_snapshot=parent_state.snapshot,
        current_step=5,
    )
    _child_attempt, child_state = _commit(context, child_request, child_source)
    assert parent_state.position is GovernanceCommitPositionV2.SUPERSEDED
    assert not commit_evidence_state_is_current_v2(parent_state)
    assert child_state.position is GovernanceCommitPositionV2.CURRENT
    assert child_request.snapshot.revision == 2
    assert child_request.snapshot.records[0].status.value == "revoked"
    assert child_request.snapshot.removed_record_roots == (record.record_root,)
    assert child_request.snapshot.revocation_roots == (revocation.revocation_root,)
    assert active_qualified_evidence_v2(child_request.snapshot) == ()
    assert project_current_commit_evidence_v2(child_state).records == ()
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as captured:
        require_current_commit_evidence_state_v2(parent_state)
    assert captured.value.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE

    restarted = rehydrate_commit_evidence_state_v2(
        child_request.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    assert restarted.snapshot == child_request.snapshot


def test_counter_disposition_is_bound_to_replay_and_projection() -> None:
    claim_root = _root("claim:counter-disposition")
    counter = _counter_attestation(
        claim_root=claim_root,
        label="public",
    )
    disposition = _disposition(counter, label="public")
    context, _upstreams, _replay, request, source = _runtime(
        "scope:commit-evidence-v2:counter-disposition",
        attestations=(counter,),
        dispositions=(disposition,),
    )
    _attempt, state = _commit(context, request, source)
    record = request.snapshot.records[0]
    assert record.kind is CommitEvidenceKindV2.COUNTER
    assert record.disposition is CommitEvidenceDispositionV2.UNRESOLVED
    assert record.disposition_root == disposition.disposition_root
    assert len(record.replay_receipt_roots) == 2
    assert project_current_commit_evidence_v2(state).records == (record,)


def test_stale_dependency_handles_fail_closed_before_or_after_commit() -> None:
    claim_root = _root("claim:stale-dependencies")
    positive = _attestations(claim_root=claim_root)[0]
    context, upstreams, replay_state, request, source = _runtime(
        "scope:commit-evidence-v2:stale-dependencies",
        attestations=(positive,),
    )
    _attempt, state = _commit(context, request, source)

    successor, successor_source = _prepare_verification(
        context,
        epoch=2,
        label="commit-evidence-public-stale",
        issuer_ref=context.grant.issuer_ref,
        parent=upstreams.verification_request.snapshot,
    )
    successor_session = open_principal_verification_authority_session_v2(
        _capability(context, context.grant, successor.observed_epoch),
        successor,
    )
    verification_attempt = advance_principal_verification_set_v2(
        successor,
        source=successor_source,
        authority_session=successor_session,
    )
    assert verification_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert not commit_evidence_state_is_current_v2(state)
    for observe in (
        require_current_commit_evidence_state_v2,
        project_current_commit_evidence_v2,
    ):
        with pytest.raises(GovernanceAuthorityBindingErrorV2) as captured:
            observe(state)
        assert (
            captured.value.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
        )
        assert captured.value.path == "/dependencies"

    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _prepare(
            context,
            upstreams,
            replay_state,
            label="stale-prepare",
            attestations=(),
            current_step=5,
        )


def test_expired_and_replay_uncovered_inputs_cannot_create_records() -> None:
    expired_context = _context(scope_ref="scope:commit-evidence-v2:expired-prepare")
    expired_upstreams = _commit_upstreams(expired_context)
    _request, expired_replay = _commit_replay_public(expired_context, ())
    with pytest.raises(ValueError, match="dependencies are stale"):
        _prepare(
            expired_context,
            expired_upstreams,
            expired_replay,
            label="expired-prepare",
            current_step=80_000,
        )

    uncovered_context = _context(scope_ref="scope:commit-evidence-v2:uncovered-replay")
    uncovered_upstreams = _commit_upstreams(uncovered_context)
    _request, empty_replay = _commit_replay_public(uncovered_context, ())
    positive = _attestations(claim_root=_root("claim:uncovered-replay"))[0]
    with pytest.raises(ValueError, match="absent from current replay"):
        _prepare(
            uncovered_context,
            uncovered_upstreams,
            empty_replay,
            label="uncovered-replay",
            attestations=(positive,),
        )


def test_prepare_rejects_unverified_dependency_shapes_and_cross_binding() -> None:
    context = _context(scope_ref="scope:commit-evidence-v2:dependency-shapes")
    upstreams = _commit_upstreams(context)
    _request, replay_state = _commit_replay_public(context, ())
    with pytest.raises(TypeError, match="verified principal state v2"):
        _prepare(
            context,
            upstreams,
            replay_state,
            label="bad-verification",
            verification_state=object(),
        )
    with pytest.raises(TypeError, match="verified membership state v2"):
        _prepare(
            context,
            upstreams,
            replay_state,
            label="bad-membership",
            membership_state=object(),
        )
    with pytest.raises(TypeError, match="verified commit replay state v2"):
        _prepare(
            context,
            upstreams,
            object(),
            label="bad-replay",
        )

    other = _context(scope_ref="scope:commit-evidence-v2:dependency-other")
    other_upstreams = _commit_upstreams(other)
    with pytest.raises(ValueError, match="cross-bound"):
        _prepare(
            context,
            upstreams,
            replay_state,
            label="cross-bound-membership",
            membership_state=other_upstreams.membership_state,
        )
    with pytest.raises(ValueError, match="verification dependency is cross-bound"):
        _prepare(
            context,
            upstreams,
            replay_state,
            label="cross-bound-verification",
            verification_state=other_upstreams.verification_state,
        )
    _other_request, other_replay_state = _commit_replay_public(other, ())
    with pytest.raises(ValueError, match="replay dependency is cross-bound"):
        _prepare(
            context,
            upstreams,
            other_replay_state,
            label="cross-bound-replay",
        )

    wrong_epoch = _context(
        scope_ref="scope:commit-evidence-v2:dependency-wrong-replay-epoch"
    )
    wrong_epoch_upstreams = _commit_upstreams(wrong_epoch)
    _wrong_epoch_request, wrong_epoch_replay = _commit_replay_public(
        wrong_epoch,
        (),
        observed_epoch=2,
    )
    with pytest.raises(ValueError, match="stale or cross-epoch"):
        _prepare(
            wrong_epoch,
            wrong_epoch_upstreams,
            wrong_epoch_replay,
            label="wrong-replay-epoch",
        )


def test_qualification_runtime_failures_are_deterministic_and_non_authoritative() -> (
    None
):
    claim_root = _root("claim:qualification-failures")
    positive, challenge = _attestations(claim_root=claim_root)
    counter = _counter_attestation(
        claim_root=claim_root,
        label="qualification-failures",
    )
    unrelated = _attestations(claim_root=_root("claim:unrelated"))[0]
    proposals = (
        (
            (replace(positive, principal_ref="principal:absent", attestation_root=""),),
            (),
            "principal is absent",
        ),
        (
            (replace(positive, reported_quality_ppm=0, attestation_root=""),),
            (),
            "quality is below",
        ),
        (
            (replace(positive, reported_relevance_ppm=0, attestation_root=""),),
            (),
            "relevance is below",
        ),
        (
            (
                replace(
                    positive,
                    candidate_ref="candidate:undeclared",
                    attestation_root="",
                ),
            ),
            (),
            "candidate or epoch is undeclared",
        ),
        (
            (replace(positive, epoch=2, attestation_root=""),),
            (),
            "candidate or epoch is undeclared",
        ),
        (
            (
                replace(
                    positive,
                    observed_at_step=5,
                    expires_at_step=20,
                    attestation_root="",
                ),
            ),
            (),
            "attestation is not fresh",
        ),
        (
            (
                replace(
                    positive,
                    expires_at_step=10_000,
                    attestation_root="",
                ),
            ),
            (),
            "exceeds the declared TTL",
        ),
        (
            (
                replace(
                    challenge,
                    challenge_result=ChallengeResultV2.COUNTEREVIDENCE_FOUND,
                    result_observation_roots=(_root("missing:counter"),),
                    attestation_root="",
                ),
            ),
            (),
            "omits committed counter evidence",
        ),
        (
            (counter,),
            (
                _disposition(
                    counter,
                    label="stale-disposition",
                    issued_at_step=1,
                    expires_at_step=4,
                ),
            ),
            "disposition is not fresh",
        ),
        (
            (counter,),
            (
                _disposition(
                    counter,
                    label="missing-rebuttal",
                    disposition=CommitEvidenceDispositionV2.REBUTTED,
                    rebuttal_observation_roots=(_root("missing:positive"),),
                ),
            ),
            "unavailable rebuttal",
        ),
        (
            (counter, unrelated),
            (
                _disposition(
                    counter,
                    label="cross-subject-rebuttal",
                    disposition=CommitEvidenceDispositionV2.REBUTTED,
                    rebuttal_observation_roots=(unrelated.attestation_root,),
                ),
            ),
            "crosses candidate, claim, or epoch",
        ),
    )
    for index, (attestations, dispositions, match) in enumerate(proposals):
        context = _context(
            scope_ref=f"scope:commit-evidence-v2:qualification-failure:{index}"
        )
        upstreams = _commit_upstreams(context)
        _request, replay_state = _commit_replay_public(
            context,
            attestations,
            dispositions,
        )
        with pytest.raises(ValueError, match=match):
            _prepare(
                context,
                upstreams,
                replay_state,
                label=f"qualification-failure-{index}",
                attestations=attestations,
                dispositions=dispositions,
            )


def test_successor_identity_and_rebuttal_independence_are_public_invariants() -> None:
    claim_root = _root("claim:successor-identity")
    positive = _attestations(claim_root=claim_root)[0]
    counter_rebuttal = _counter_attestation(
        claim_root=claim_root,
        label="successor-non-independent-rebuttal",
    )
    rebutted = _disposition(
        counter_rebuttal,
        label="successor-non-independent-rebuttal",
        disposition=CommitEvidenceDispositionV2.REBUTTED,
        rebuttal_observation_roots=(positive.attestation_root,),
    )
    context = _context(scope_ref="scope:commit-evidence-v2:successor-identity")
    upstreams = _commit_upstreams(context)
    _replay_request, replay_state = _commit_replay_public(
        context,
        (positive, counter_rebuttal),
        (rebutted,),
    )
    parent_request, parent_source = _prepare(
        context,
        upstreams,
        replay_state,
        label="successor-identity-parent",
        attestations=(positive,),
    )
    _parent_attempt, parent_state = _commit(context, parent_request, parent_source)

    with pytest.raises(ValueError, match="addition replays"):
        _prepare(
            context,
            upstreams,
            replay_state,
            label="successor-replays-attestation",
            attestations=(positive,),
            parent_snapshot=parent_state.snapshot,
            current_step=5,
        )
    with pytest.raises(ValueError, match="not principal/cluster/domain independent"):
        _prepare(
            context,
            upstreams,
            replay_state,
            label="successor-non-independent-rebuttal",
            attestations=(counter_rebuttal,),
            dispositions=(rebutted,),
            parent_snapshot=parent_state.snapshot,
            current_step=5,
        )


def test_source_forgery_and_cross_request_reuse_are_typed_failures() -> None:
    positive = _attestations(claim_root=_root("claim:source-forgery"))[0]
    context, upstreams, replay_state, request, source = _runtime(
        "scope:commit-evidence-v2:source-forgery",
        attestations=(positive,),
    )
    session = open_commit_evidence_authority_session_v2(
        _capability(context, context.grant, request.observed_epoch),
        request,
    )
    for forged in (object(), SimpleNamespace(context_root=source.context_root)):
        with pytest.raises(TypeError):
            verify_commit_evidence_request_source_v2(request, source=forged)
        rejected = advance_commit_evidence_state_v2(
            request,
            source=forged,
            authority_session=session,
        )
        assert rejected.disposition is GovernanceCommitDispositionV2.INVALID
        assert rejected.failure is not None
        assert (
            rejected.failure.code
            is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
        )
        assert rejected.failure.path == "/source"

    incomplete = object.__new__(VerifiedCommitEvidenceSourceV2)
    with pytest.raises(TypeError, match="incomplete"):
        verify_commit_evidence_request_source_v2(request, source=incomplete)

    with pytest.raises(TypeError, match="exact request"):
        verify_commit_evidence_request_source_v2(
            cast(CommitEvidenceAdvanceRequestV2, object()),
            source=source,
        )

    invalid_shape = _clone_source(source)
    object.__setattr__(invalid_shape, "_manifest", object())
    with pytest.raises(TypeError, match="shape is invalid"):
        verify_commit_evidence_request_source_v2(request, source=invalid_shape)

    forged_binding = _clone_source(source)
    binding = object.__getattribute__(forged_binding, "_binding")
    object.__setattr__(
        forged_binding,
        "_binding",
        replace(binding, request_root=_root("forged:binding-request")),
    )
    with pytest.raises(ValueError, match="cross-bound at request_root"):
        verify_commit_evidence_request_source_v2(request, source=forged_binding)

    forged_root = _clone_source(source)
    binding = object.__getattribute__(forged_root, "_binding")
    object.__setattr__(
        forged_root,
        "_binding",
        replace(binding, source_context_root=_root("forged:source-context")),
    )
    with pytest.raises(ValueError, match="context root is mismatched"):
        verify_commit_evidence_request_source_v2(request, source=forged_root)

    other_request, other_source = _prepare(
        context,
        upstreams,
        replay_state,
        label="source-forgery-other-request",
        attestations=(positive,),
    )
    with pytest.raises(ValueError, match="belongs to another request"):
        verify_commit_evidence_request_source_v2(request, source=other_source)
    other_session = open_commit_evidence_authority_session_v2(
        _capability(context, context.grant, other_request.observed_epoch),
        other_request,
    )
    rejected = advance_commit_evidence_state_v2(
        other_request,
        source=source,
        authority_session=other_session,
    )
    assert rejected.disposition is GovernanceCommitDispositionV2.INVALID
    assert rejected.failure is not None
    assert rejected.failure.path == "/source"


def test_session_binding_and_transition_conflicts_never_commit() -> None:
    positive = _attestations(claim_root=_root("claim:session-binding"))[0]
    conflicting = replace(
        positive,
        evidence_ref="evidence:transition-conflict",
        payload_root=_root("payload:transition-conflict"),
        nonce="nonce:transition-conflict",
        provenance_root=_root("provenance:transition-conflict"),
        attestation_root="",
    )
    context = _context(scope_ref="scope:commit-evidence-v2:session-binding")
    upstreams = _commit_upstreams(context)
    _replay_request, replay_state = _commit_replay_public(
        context,
        (positive, conflicting),
    )
    request, source = _prepare(
        context,
        upstreams,
        replay_state,
        label="session-binding-shared-transition",
        attestations=(positive,),
    )
    conflict_request, conflict_source = _prepare(
        context,
        upstreams,
        replay_state,
        label="session-binding-shared-transition",
        attestations=(conflicting,),
    )
    assert conflict_request.transition_id == request.transition_id
    assert conflict_request.request_root != request.request_root
    invalid_session = advance_commit_evidence_state_v2(
        request,
        source=source,
        authority_session=None,
    )
    assert invalid_session.disposition is GovernanceCommitDispositionV2.DENIED
    assert invalid_session.failure is not None
    assert (
        invalid_session.failure.code
        is AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED
    )

    other_request, other_source = _prepare(
        context,
        upstreams,
        replay_state,
        label="session-binding-other",
        attestations=(positive,),
    )
    wrong_session = open_commit_evidence_authority_session_v2(
        _capability(context, context.grant, other_request.observed_epoch),
        other_request,
    )
    wrong_binding = advance_commit_evidence_state_v2(
        request,
        source=source,
        authority_session=wrong_session,
    )
    assert wrong_binding.disposition is GovernanceCommitDispositionV2.INVALID
    assert wrong_binding.failure is not None
    assert (
        wrong_binding.failure.code
        is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )

    rotated = _activate_rotated_grant(context)
    with pytest.raises(ValueError, match="issuer is not owned"):
        open_commit_evidence_authority_session_v2(
            _capability(context, rotated, request.observed_epoch),
            request,
        )

    original_session = open_commit_evidence_authority_session_v2(
        _capability(context, context.grant, request.observed_epoch),
        request,
    )
    committed = advance_commit_evidence_state_v2(
        request,
        source=source,
        authority_session=original_session,
    )
    assert committed.disposition is GovernanceCommitDispositionV2.COMMITTED
    conflict_session = open_commit_evidence_authority_session_v2(
        _capability(context, context.grant, conflict_request.observed_epoch),
        conflict_request,
    )
    conflict = advance_commit_evidence_state_v2(
        conflict_request,
        source=conflict_source,
        authority_session=conflict_session,
    )
    assert conflict.disposition is GovernanceCommitDispositionV2.INVALID
    assert conflict.failure is not None
    assert (
        conflict.failure.code
        is AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT
    )

    revoked = revoke_governance_issuer_grant_v2(
        context.store,
        context.domain,
        context.grant.grant_ref,
        "transition:commit-evidence:revoke-after-commit",
        31,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED
    retry = advance_commit_evidence_state_v2(
        request,
        source=source,
        authority_session=original_session,
    )
    assert retry.to_dict() == committed.to_dict()

    denied_fresh = advance_commit_evidence_state_v2(
        other_request,
        source=other_source,
        authority_session=wrong_session,
    )
    assert denied_fresh.disposition is GovernanceCommitDispositionV2.DENIED
    assert denied_fresh.failure is not None
    assert (
        denied_fresh.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED
    )


def test_forged_state_and_portable_projection_have_zero_authority() -> None:
    positive = _attestations(claim_root=_root("claim:forged-state"))[0]
    context, _upstreams, _replay, request, source = _runtime(
        "scope:commit-evidence-v2:forged-state",
        attestations=(positive,),
    )
    _attempt, state = _commit(context, request, source)
    projection = project_current_commit_evidence_v2(state)

    with pytest.raises(TypeError, match="cannot be constructed"):
        VerifiedCommitEvidenceStateV2()
    incomplete = object.__new__(VerifiedCommitEvidenceStateV2)
    for forged in (incomplete, projection, request.snapshot, request.to_dict()):
        assert not commit_evidence_state_is_current_v2(forged)
        with pytest.raises(GovernanceAuthorityBindingErrorV2):
            require_current_commit_evidence_state_v2(forged)

    forged_receipt = object.__new__(VerifiedCommitEvidenceStateV2)
    for name in VerifiedCommitEvidenceStateV2.__slots__:
        object.__setattr__(
            forged_receipt,
            name,
            object.__getattribute__(state, name),
        )
    object.__setattr__(
        forged_receipt,
        "_receipt_root",
        _root("forged:receipt"),
    )
    assert not commit_evidence_state_is_current_v2(forged_receipt)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as captured:
        project_current_commit_evidence_v2(forged_receipt)
    assert (
        captured.value.code
        is AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )

    forged_request_shape = object.__new__(VerifiedCommitEvidenceStateV2)
    for name in VerifiedCommitEvidenceStateV2.__slots__:
        object.__setattr__(
            forged_request_shape,
            name,
            object.__getattribute__(state, name),
        )
    object.__setattr__(forged_request_shape, "_request", object())
    assert not commit_evidence_state_is_current_v2(forged_request_shape)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as malformed_request:
        require_current_commit_evidence_state_v2(forged_request_shape)
    assert (
        malformed_request.value.code
        is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )
    assert malformed_request.value.path == "/request_root"

    with pytest.raises(GovernanceAuthorityBindingErrorV2) as malformed:
        rehydrate_commit_evidence_state_v2(
            {"not": "a request"},
            domain=context.domain,
            state_reader=context.store,
        )
    assert malformed.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    with pytest.raises(TypeError, match="exact AuthorityDomainV2"):
        rehydrate_commit_evidence_state_v2(
            request,
            domain=cast(AuthorityDomainV2, object()),
            state_reader=context.store,
        )
    with pytest.raises(TypeError, match="StateReader v2"):
        rehydrate_commit_evidence_state_v2(
            request,
            domain=context.domain,
            state_reader=cast(GovernanceStateReaderV2, object()),
        )


def test_context_rejects_wrong_manifest_profile_target_and_candidate_set() -> None:
    context = _context(scope_ref="scope:commit-evidence-v2:context-failures")
    upstreams = _commit_upstreams(context)
    _request, replay_state = _commit_replay_public(context, ())
    cases = (
        (cast(ScopedProtocolManifestV2, object()), PROFILE, TARGET, TypeError),
        (
            replace(context.manifest, collective_commit_policy=None),
            PROFILE,
            TARGET,
            ValueError,
        ),
        (context.manifest, "profile:unsupported", TARGET, ValueError),
        (context.manifest, PROFILE, "target:cross-bound", ValueError),
    )
    for index, (manifest, profile, target_ref, error) in enumerate(cases):
        with pytest.raises(error):
            _prepare(
                context,
                upstreams,
                replay_state,
                label=f"context-failure-{index}",
                manifest=manifest,
                profile=profile,
                target_ref=target_ref,
            )

    policy = context.manifest.collective_commit_policy
    assert policy is not None
    unsupported_assurance = replace(
        context.manifest,
        collective_commit_policy=replace(
            policy,
            assurance=cast(Any, "unsupported-assurance"),
        ),
    )
    with pytest.raises(ValueError, match="assurance is unsupported"):
        _prepare(
            context,
            upstreams,
            replay_state,
            label="context-unsupported-assurance",
            manifest=unsupported_assurance,
        )

    invalid_policy = replace(
        context.manifest,
        collective_commit_policy=replace(
            policy,
            evidence_qualification=replace(
                policy.evidence_qualification,
                numeric_scale=0,
            ),
        ),
    )
    with pytest.raises(ValueError, match="policy is invalid"):
        _prepare(
            context,
            upstreams,
            replay_state,
            label="context-invalid-policy",
            manifest=invalid_policy,
        )


def test_parent_validation_and_revocation_fail_closed_before_source_issue() -> None:
    positive = _attestations(claim_root=_root("claim:parent-validation"))[0]
    context, upstreams, replay_state, parent_request, _parent_source = _runtime(
        "scope:commit-evidence-v2:parent-validation",
        attestations=(positive,),
    )
    with pytest.raises(TypeError, match="parent must be exact snapshot"):
        _prepare(
            context,
            upstreams,
            replay_state,
            label="parent-wrong-type",
            parent_snapshot=cast(CommitEvidenceSnapshotV2, object()),
            current_step=5,
        )

    other, _other_upstreams, _other_replay, other_request, _other_source = _runtime(
        "scope:commit-evidence-v2:parent-validation-other",
        attestations=(positive,),
    )
    assert other.domain.scope_ref != context.domain.scope_ref
    with pytest.raises(ValueError, match="fixed lineage is cross-bound"):
        _prepare(
            context,
            upstreams,
            replay_state,
            label="parent-cross-bound",
            parent_snapshot=other_request.snapshot,
            current_step=5,
        )

    with pytest.raises(ValueError, match="moves backwards"):
        _prepare(
            context,
            upstreams,
            replay_state,
            label="parent-same-step",
            parent_snapshot=parent_request.snapshot,
            current_step=parent_request.snapshot.current_step,
        )

    record = parent_request.snapshot.records[0]
    stale_revocation = CommitEvidenceRevocationV2(
        revocation_ref="revocation:stale-root",
        record_ref=record.record_ref,
        record_root=_root("wrong:record-root"),
        revoked_at_step=5,
        reason_codes=("reason:stale",),
        provenance_root=_root("provenance:stale-revocation"),
        trace_roots=(_root("trace:stale-revocation"),),
    )
    with pytest.raises(ValueError, match="revocation is stale or cross-bound"):
        _prepare(
            context,
            upstreams,
            replay_state,
            label="parent-stale-revocation",
            revocations=(stale_revocation,),
            parent_snapshot=parent_request.snapshot,
            current_step=5,
        )


def test_same_parent_competitors_leave_one_current_state() -> None:
    positive = _attestations(claim_root=_root("claim:parent-cas"))[0]
    context, upstreams, replay_state, parent_request, parent_source = _runtime(
        "scope:commit-evidence-v2:parent-cas",
        attestations=(positive,),
    )
    _attempt, parent_state = _commit(context, parent_request, parent_source)
    first_request, first_source = _prepare(
        context,
        upstreams,
        replay_state,
        label="parent-cas-first",
        parent_snapshot=parent_state.snapshot,
        current_step=5,
    )
    second_request, second_source = _prepare(
        context,
        upstreams,
        replay_state,
        label="parent-cas-second",
        parent_snapshot=parent_state.snapshot,
        current_step=5,
    )
    first, first_state = _commit(context, first_request, first_source)
    assert first.disposition is GovernanceCommitDispositionV2.COMMITTED
    stale_session = open_commit_evidence_authority_session_v2(
        _capability(context, context.grant, second_request.observed_epoch),
        second_request,
    )
    stale = advance_commit_evidence_state_v2(
        second_request,
        source=second_source,
        authority_session=stale_session,
    )
    assert stale.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert stale.failure is not None
    assert stale.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    assert first_state.position is GovernanceCommitPositionV2.CURRENT
    assert parent_state.position is GovernanceCommitPositionV2.SUPERSEDED


def test_public_decision_preparation_consumes_only_current_evidence_handle() -> None:
    context = _decision_context("scope:commit-evidence-v2:public-decision-adapter")
    claim_root = _root("claim:public-decision-adapter")
    inputs = _fresh_inputs(context, claim_root)
    initialize, initialize_source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:public-decision-adapter:initialize",
        current_step=6,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    parent = _commit_decision(context, initialize, initialize_source)
    proposal = CommitDecisionCandidateProposalV2(
        candidate_ref="candidate:accept",
        claim_root=claim_root,
        evidence=(),
    )
    request, source = prepare_commit_decision_successor_v2(
        parent_state=parent,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:public-decision-adapter:evaluate",
        current_step=7,
        mutation_issuer_ref=context.grant.issuer_ref,
        command=CommitDecisionCommandV2.EVALUATE,
        candidate_proposals=(proposal,),
        commit_replay_state=inputs[0],
        risk_state=inputs[1],
        membership_state=inputs[2],
        support_state=inputs[3],
        evidence_state=inputs[4],
        stop_state=inputs[5],
        permission_state=inputs[6],
    )
    committed = _commit_decision(context, request, source).snapshot
    assert committed.assessment is not None
    assert tuple(
        (item.candidate_ref, item.claim_root)
        for item in committed.assessment.candidate_metrics
    ) == (("candidate:accept", claim_root),)


def _forged_evidence_records(
    records: dict[str, Any],
    mutation: str,
) -> dict[str, Any]:
    forged = deepcopy(records)
    top_level_mutations: dict[str, tuple[str, Any]] = {
        "extra-state-field": ("caller_extension", True),
        "wrong-domain-root": ("domain_root", _root("forged:domain-root")),
        "wrong-request-root": ("request_root", _root("forged:request-root")),
        "bad-session-fields": ("session_binding", {"unexpected": True}),
        "non-object-session-binding": ("session_binding", []),
    }
    selected = top_level_mutations.get(mutation)
    if selected is not None:
        key, value = selected
        forged[key] = value
        return forged
    if mutation == "exact-records-wrong-trace":
        return forged
    binding = forged["session_binding"]
    assert type(binding) is dict
    binding_mutations: dict[str, tuple[str, Any]] = {
        "wrong-session-binding": ("operation", "forged-operation"),
        "empty-grant-ref": ("grant_ref", ""),
        "bool-grant-revision": ("grant_expected_revision", True),
        "empty-grant-root": ("grant_expected_root", ""),
    }
    key, value = binding_mutations[mutation]
    binding[key] = value
    return forged


def test_canonical_store_with_forged_evidence_records_fails_closed() -> None:
    positive = _attestations(claim_root=_root("claim:forged-store-records"))[0]
    context, _upstreams, _replay, request, source = _runtime(
        "scope:commit-evidence-v2:forged-store-records",
        attestations=(positive,),
    )
    precommit_snapshot = context.base_store.snapshot_v2()
    attempt, _state = _commit(context, request, source)
    assert attempt.committed_transition is not None
    assert attempt.committed_transition.batch.transition is not None
    records = attempt.committed_transition.batch.transition.to_dict()["state_records"]
    assert type(records) is dict

    for mutation in (
        "exact-records-wrong-trace",
        "extra-state-field",
        "wrong-domain-root",
        "wrong-request-root",
        "bad-session-fields",
        "non-object-session-binding",
        "wrong-session-binding",
        "empty-grant-ref",
        "bool-grant-revision",
        "empty-grant-root",
    ):
        forged_records = _forged_evidence_records(records, mutation)

        forged_store = type(context.base_store).from_snapshot_v2(precommit_snapshot)
        snapshot = request.snapshot
        observed_heads = tuple(
            forged_store.load_head_v2(context.domain.scope_ref, stream_ref)
            for stream_ref in (
                request.stream_ref,
                governance_issuer_grant_stream_ref_v2(
                    request.scope_ref,
                    context.grant.grant_ref,
                ),
                GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
                snapshot.membership_stream_ref,
                snapshot.verification_stream_ref,
                snapshot.replay_stream_ref,
            )
        )
        forged_batch = _transition_batch(
            forged_store,
            context.domain,
            request.stream_ref,
            request.transition_id,
            forged_records,
            observed_heads=observed_heads,
        )
        forged_attempt = forged_store.atomic_commit_v2(forged_batch)
        assert forged_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        with pytest.raises(GovernanceAuthorityBindingErrorV2) as captured:
            rehydrate_commit_evidence_state_v2(
                request,
                domain=context.domain,
                state_reader=forged_store,
            )
        assert (
            captured.value.code
            is AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
        )
        assert captured.value.path == "/transition_id"


def test_projection_with_expired_related_record_returns_no_partial_authority() -> None:
    claim_root = _root("claim:projection-related-expiry")
    counter = replace(
        _counter_attestation(
            claim_root=claim_root,
            label="projection-related-expiry",
        ),
        expires_at_step=5,
        attestation_root="",
    )
    challenge = replace(
        _attestations(claim_root=claim_root)[1],
        evidence_ref="evidence:challenge:projection-related-expiry",
        challenge_result=ChallengeResultV2.COUNTEREVIDENCE_FOUND,
        result_root=_root("result:projection-related-expiry"),
        result_observation_roots=(counter.attestation_root,),
        nonce="nonce:challenge:projection-related-expiry",
        provenance_root=_root("provenance:challenge:projection-related-expiry"),
        trace_roots=(_root("trace:challenge:projection-related-expiry"),),
        attestation_root="",
    )
    disposition = _disposition(counter, label="projection-related-expiry")
    context = _context(scope_ref="scope:commit-evidence-v2:projection-related-expiry")
    upstreams = _commit_upstreams(context)
    _replay_request, replay_state = _commit_replay_public(
        context,
        (counter, challenge),
        (disposition,),
    )
    parent_request, parent_source = _prepare(
        context,
        upstreams,
        replay_state,
        label="projection-related-expiry-parent",
        attestations=(counter, challenge),
        dispositions=(disposition,),
    )
    _parent_attempt, parent_state = _commit(context, parent_request, parent_source)
    child_request, child_source = _prepare(
        context,
        upstreams,
        replay_state,
        label="projection-related-expiry-child",
        parent_snapshot=parent_state.snapshot,
        current_step=5,
    )
    _child_attempt, child_state = _commit(context, child_request, child_source)
    assert active_qualified_evidence_v2(child_state.snapshot) == (
        child_state.snapshot.records[0],
    )
    assert project_current_commit_evidence_v2(child_state).records == ()


def test_parent_store_finality_and_missing_history_are_typed_failures() -> None:
    context, reader = _adversarial_context(
        "scope:commit-evidence-v2:parent-store-failures"
    )
    upstreams = _commit_upstreams(context)
    positive = _attestations(claim_root=_root("claim:parent-store-failures"))[0]
    _replay_request, replay_state = _commit_replay_public(context, (positive,))
    parent_request, parent_source = _prepare(
        context,
        upstreams,
        replay_state,
        label="parent-store-failures-genesis",
        attestations=(positive,),
    )
    _parent_attempt, parent_state = _commit(
        context,
        parent_request,
        parent_source,
    )
    finality_request, finality_source = _prepare(
        context,
        upstreams,
        replay_state,
        label="parent-store-failures-finality",
        parent_snapshot=parent_state.snapshot,
        current_step=5,
    )
    finality_session = open_commit_evidence_authority_session_v2(
        _capability(context, context.grant, finality_request.observed_epoch),
        finality_request,
    )
    reader.finality_transition_ids.add(parent_request.transition_id)
    finality = advance_commit_evidence_state_v2(
        finality_request,
        source=finality_source,
        authority_session=finality_session,
    )
    assert finality.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert finality.failure is not None
    assert (
        finality.failure.code
        is AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
    )
    assert finality.failure.path == "/transition_id"
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as rehydrate_finality:
        rehydrate_commit_evidence_state_v2(
            parent_request,
            domain=context.domain,
            state_reader=reader,
        )
    assert (
        rehydrate_finality.value.code
        is AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
    )

    reader.finality_transition_ids.clear()
    missing_request, missing_source = _prepare(
        context,
        upstreams,
        replay_state,
        label="parent-store-failures-missing",
        parent_snapshot=parent_state.snapshot,
        current_step=5,
    )
    missing_session = open_commit_evidence_authority_session_v2(
        _capability(context, context.grant, missing_request.observed_epoch),
        missing_request,
    )
    reader.hidden_transition_ids.add(parent_request.transition_id)
    missing = advance_commit_evidence_state_v2(
        missing_request,
        source=missing_source,
        authority_session=missing_session,
    )
    assert missing.disposition is GovernanceCommitDispositionV2.INVALID
    assert missing.failure is not None
    assert (
        missing.failure.code
        is AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    assert missing.failure.path == "/snapshot/parent_transition_id"
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as rehydrate_missing:
        rehydrate_commit_evidence_state_v2(
            parent_request,
            domain=context.domain,
            state_reader=reader,
        )
    assert (
        rehydrate_missing.value.code
        is AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
