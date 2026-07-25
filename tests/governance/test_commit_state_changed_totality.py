from __future__ import annotations

from copy import copy
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import pytest

import pheroos.governance._commit.evaluation_engine as evaluation_engine
import pheroos.governance._commit.replay as commit_replay
import pheroos.governance._commit_state.liveness as liveness_facade
import pheroos.governance._commit_state.liveness_input as liveness_input
import pheroos.governance._commit_state.liveness_reduction as liveness_reduction
import pheroos.governance._commit_state.records as commit_state_records
import pheroos.governance._commit_state.replay as state_replay
import pheroos.governance._commit_state.window as commit_window
import pheroos.governance._commit_state_v2.operations as replay_operations_v2
import pheroos.governance._commit_state_v2.source as replay_source_v2
from pheroos.governance._commit.evaluation_engine import CommitEvaluationRequest
from pheroos.governance._commit.records import (
    CandidateCommitInput,
    CommitEvaluationError,
    CommitReasonCode,
)
from pheroos.governance._commit_state.liveness_input import HeartbeatFacts
from pheroos.governance._commit_state.records import (
    CommitFinalityStatus,
    ReplayNamespace,
)
from pheroos.governance._commit_state_v2.contracts import CommitReplayAdvanceRequestV2
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitDispositionV2,
)
from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import CommitAssurance
from pheroos.protocol.models import CapabilityManifest
from tests.governance import test_commit_engine as commit_engine_tests
from tests.governance import test_commit_liveness as commit_liveness_tests
from tests.governance import test_commit_state_v2_public_semantics as state_v2_tests
from tests.governance import test_commit_window as commit_window_tests


def _mutated(value: Any, **changes: object) -> Any:
    clone = copy(value)
    for name, replacement in changes.items():
        object.__setattr__(clone, name, replacement)
    return clone


@pytest.fixture(scope="module")
def optimal_request() -> CommitEvaluationRequest:
    scenario = commit_engine_tests._scenario()
    return CommitEvaluationRequest(
        context=scenario.context,
        manifest=scenario.manifest,
        candidate_inputs=scenario.candidate_inputs,
        leases=scenario.leases,
        revocations=(),
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
        stop_resolution=scenario.stop_resolution,
        commit_permission=scenario.permission,
        assessment_id=f"assessment:{scenario.run_id}:changed-totality",
        issuer_id="governance:commit",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=5,
        provenance=f"urn:test:changed-totality:{scenario.run_id}",
        trace_event_id=f"trace:changed-totality:{scenario.run_id}",
    )


def _assert_commit_error(
    reason: CommitReasonCode,
    operation: Any,
) -> None:
    with pytest.raises(CommitEvaluationError) as captured:
        operation()
    assert captured.value.reason_code is reason


def test_initial_request_freshness_and_authority_fail_closed(
    optimal_request: CommitEvaluationRequest,
) -> None:
    _assert_commit_error(
        CommitReasonCode.CONTEXT_EXPIRED,
        lambda: evaluation_engine._validate_initial_request(
            replace(
                optimal_request,
                current_step=optimal_request.context.expires_at_step,
            )
        ),
    )
    _assert_commit_error(
        CommitReasonCode.INVALID_CONTEXT,
        lambda: evaluation_engine._validate_initial_request(
            replace(optimal_request, authority=AuthorityLevel.AGENT)
        ),
    )


def test_manifest_type_diagnostics_policy_and_root_bindings_fail_closed(
    optimal_request: CommitEvaluationRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_commit_error(
        CommitReasonCode.INVALID_MANIFEST,
        lambda: evaluation_engine._validate_manifest_binding(
            replace(
                optimal_request,
                manifest=cast(CapabilityManifest, object()),
            )
        ),
    )

    monkeypatch.setattr(
        evaluation_engine,
        "validate_capability_manifest",
        lambda _manifest: (SimpleNamespace(level="error", code="invalid.fixture"),),
    )
    _assert_commit_error(
        CommitReasonCode.INVALID_MANIFEST,
        lambda: evaluation_engine._validate_manifest_binding(optimal_request),
    )
    monkeypatch.setattr(
        evaluation_engine,
        "validate_capability_manifest",
        lambda _manifest: (),
    )

    no_policy = replace(
        optimal_request.manifest,
        protocol=replace(
            optimal_request.manifest.protocol,
            collective_commit_policy=None,
        ),
    )
    _assert_commit_error(
        CommitReasonCode.INVALID_MANIFEST,
        lambda: evaluation_engine._validate_manifest_binding(
            replace(optimal_request, manifest=no_policy)
        ),
    )

    monkeypatch.setattr(
        evaluation_engine,
        "commit_manifest_fingerprint",
        lambda *_args, **_kwargs: commit_engine_tests._fingerprint("wrong-manifest"),
    )
    _assert_commit_error(
        CommitReasonCode.MANIFEST_ROOT_MISMATCH,
        lambda: evaluation_engine._validate_manifest_roots(
            optimal_request.context,
            manifest=optimal_request.manifest,
            policy=optimal_request.manifest.protocol.collective_commit_policy,
        ),
    )
    monkeypatch.setattr(
        evaluation_engine,
        "commit_manifest_fingerprint",
        lambda *_args, **_kwargs: optimal_request.context.manifest_root,
    )
    monkeypatch.setattr(
        evaluation_engine,
        "commit_policy_fingerprint",
        lambda *_args, **_kwargs: commit_engine_tests._fingerprint("wrong-policy"),
    )
    _assert_commit_error(
        CommitReasonCode.POLICY_ROOT_MISMATCH,
        lambda: evaluation_engine._validate_manifest_roots(
            optimal_request.context,
            manifest=optimal_request.manifest,
            policy=optimal_request.manifest.protocol.collective_commit_policy,
        ),
    )


def test_context_head_reason_dispatch_is_total() -> None:
    assert (
        evaluation_engine._context_head_reason("replay_state_fingerprint")
        is CommitReasonCode.REPLAY_HEAD_MISMATCH
    )
    assert (
        evaluation_engine._context_head_reason("support_replay_root")
        is CommitReasonCode.SUPPORT_REPLAY_HEAD_MISMATCH
    )
    assert (
        evaluation_engine._context_head_reason("membership_root")
        is CommitReasonCode.MEMBERSHIP_HEAD_MISMATCH
    )
    assert (
        evaluation_engine._context_head_reason("threshold_fingerprint")
        is CommitReasonCode.THRESHOLD_MISMATCH
    )
    assert (
        evaluation_engine._context_head_reason("risk_assessment_fingerprint")
        is CommitReasonCode.RISK_HEAD_MISMATCH
    )


def test_candidate_and_support_input_guards_are_exact(
    optimal_request: CommitEvaluationRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_commit_error(
        CommitReasonCode.CANDIDATE_COVERAGE_MISMATCH,
        lambda: evaluation_engine._validate_candidate_inputs(
            optimal_request.context,
            (cast(CandidateCommitInput, object()),),
        ),
    )
    first = optimal_request.candidate_inputs[0]
    wrong_claim = _mutated(
        first,
        claim_fingerprint=commit_engine_tests._fingerprint("wrong-claim"),
    )
    _assert_commit_error(
        CommitReasonCode.CANDIDATE_CLAIM_MISMATCH,
        lambda: evaluation_engine._validate_candidate_context_claims(
            optimal_request.context,
            (wrong_claim,),
        ),
    )
    _assert_commit_error(
        CommitReasonCode.SUPPORT_EVALUATION_INVALID,
        lambda: evaluation_engine._validate_support_inputs(
            replace(
                optimal_request,
                revocations=(cast(Any, object()),),
            )
        ),
    )
    _assert_commit_error(
        CommitReasonCode.SUPPORT_EVALUATION_INVALID,
        lambda: evaluation_engine._validate_lease(
            optimal_request.context,
            cast(Any, object()),
            {first.candidate_id: first.claim_fingerprint},
        ),
    )

    lease = optimal_request.leases[0]
    monkeypatch.setattr(
        evaluation_engine,
        "support_lease_is_authoritative",
        lambda _lease: False,
    )
    _assert_commit_error(
        CommitReasonCode.SUPPORT_EVALUATION_INVALID,
        lambda: evaluation_engine._validate_lease(
            optimal_request.context,
            lease,
            {lease.candidate_id: lease.claim_fingerprint},
        ),
    )
    monkeypatch.setattr(
        evaluation_engine,
        "support_lease_is_authoritative",
        lambda _lease: True,
    )
    _assert_commit_error(
        CommitReasonCode.CANDIDATE_COVERAGE_MISMATCH,
        lambda: evaluation_engine._validate_lease(
            optimal_request.context,
            _mutated(lease, run_id="run:wrong"),
            {lease.candidate_id: lease.claim_fingerprint},
        ),
    )
    _assert_commit_error(
        CommitReasonCode.CANDIDATE_CLAIM_MISMATCH,
        lambda: evaluation_engine._validate_lease(
            optimal_request.context,
            _mutated(
                lease,
                claim_fingerprint=commit_engine_tests._fingerprint("lease-claim"),
            ),
            {lease.candidate_id: lease.claim_fingerprint},
        ),
    )


def test_replay_evidence_and_support_dependency_failures_are_typed(
    optimal_request: CommitEvaluationRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_governance(*_args: object, **_kwargs: object) -> Any:
        raise GovernanceError("controlled dependency failure")

    monkeypatch.setattr(
        evaluation_engine,
        "build_commit_replay_receipts",
        raise_governance,
    )
    _assert_commit_error(
        CommitReasonCode.REPLAY_COVERAGE_MISMATCH,
        lambda: evaluation_engine._validate_replay_inputs(
            optimal_request,
            inputs=optimal_request.candidate_inputs,
            leases=optimal_request.leases,
            revocations=(),
        ),
    )

    item = optimal_request.candidate_inputs[0]
    monkeypatch.setattr(
        evaluation_engine,
        "evidence_binding_is_authoritative",
        lambda _binding: True,
    )
    mismatched_binding = _mutated(item.evidence_binding, run_id="run:mismatched")
    _assert_commit_error(
        CommitReasonCode.EVIDENCE_BINDING_INVALID,
        lambda: evaluation_engine._evaluate_candidate(
            optimal_request,
            policy=optimal_request.manifest.protocol.collective_commit_policy,
            item=_mutated(item, evidence_binding=mismatched_binding),
            leases=optimal_request.leases,
            revocations=(),
            current=optimal_request.current_step,
        ),
    )

    monkeypatch.setattr(
        evaluation_engine,
        "evaluate_evidence_binding",
        raise_governance,
    )
    _assert_commit_error(
        CommitReasonCode.EVIDENCE_EVALUATION_INVALID,
        lambda: evaluation_engine._evaluate_evidence(
            optimal_request,
            policy=optimal_request.manifest.protocol.collective_commit_policy,
            item=item,
            current=optimal_request.current_step,
        ),
    )
    monkeypatch.setattr(
        evaluation_engine,
        "evaluate_support_leases",
        raise_governance,
    )
    _assert_commit_error(
        CommitReasonCode.SUPPORT_EVALUATION_INVALID,
        lambda: evaluation_engine._evaluate_support(
            optimal_request,
            policy=optimal_request.manifest.protocol.collective_commit_policy,
            item=item,
            leases=optimal_request.leases,
            revocations=(),
            current=optimal_request.current_step,
        ),
    )


def test_challenge_execution_reuse_is_detected(
    optimal_request: CommitEvaluationRequest,
) -> None:
    left, right = optimal_request.candidate_inputs[:2]
    left_challenge = left.challenges[0]
    forged_challenge = _mutated(
        right.challenges[0],
        execution_attestation_ref=left_challenge.execution_attestation_ref,
    )
    forged_right = _mutated(right, challenges=(forged_challenge,))
    conflicts = commit_replay._cross_record_replay_conflicts(
        (left, forged_right),
        (),
    )
    assert len(conflicts) == 1


def test_liveness_facade_executes_every_commit_state_delegate() -> None:
    scenario, assessment, state = commit_liveness_tests._one_ready_step()
    value = commit_liveness_tests._liveness(
        state,
        scenario,
        assessment=assessment,
        current_step=state.last_evaluated_step,
    )
    assert liveness_facade.commit_liveness_input_fingerprint(value).startswith(
        "sha256:"
    )
    liveness_facade._validate_liveness_input_matches_window(state, value)
    liveness_facade._validate_liveness_current_authority_heads(
        state,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        support_replay_state=scenario.support_replay_state,
        current_step=state.last_evaluated_step,
        require_fresh_snapshot=False,
    )
    assert liveness_facade._liveness_authority_heads_are_current(value)
    assert not liveness_facade._finality_satisfied(value)
    assert not liveness_facade._finality_unavailable_at_deadline(
        assurance=CommitAssurance.EVIDENCE_BOUND,
        finality_status=CommitFinalityStatus.PENDING,
        stability_satisfied=False,
        deadline_reached=False,
    )
    progress = liveness_facade._progress_from_liveness(state, value)
    outcome = liveness_facade._outcome_from_liveness(
        state,
        commit_policy=scenario.policy,
        liveness_input=_mutated(
            value,
            invalid_reason_codes=("controlled_invalidity",),
        ),
        kind=commit_state_records.DecisionOutcomeKind.INVALID,
        deadline_reached=False,
        run_deadline_reached=False,
        derived_blocked=False,
    )
    assert progress.window_state_ref == outcome.window_state_ref


def test_liveness_dominated_cursor_and_finality_guards_are_alarms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        liveness_input,
        "commit_window_state_is_current",
        lambda _state: True,
    )
    request = SimpleNamespace(
        state=SimpleNamespace(
            last_evaluated_step=1,
            absolute_deadline_step=5,
            absolute_run_deadline_step=6,
            _cursor=object(),
        ),
        authority=AuthorityLevel.GOVERNANCE,
        current_step=1,
    )
    with pytest.raises(GovernanceError, match="window cursor is invalid"):
        liveness_input._validate_issuance_request(cast(Any, request))

    previous = SimpleNamespace(current_step=1)
    cursor = SimpleNamespace(
        lock=__import__("threading").RLock(),
        current_progress=object(),
    )
    defaults = HeartbeatFacts(
        seal=object(),
        seal_ref="seal",
        sealed_at_step=1,
        previous_progress_ref="",
        heartbeat_sequence=0,
        heartbeat_continuous=True,
    )
    monkeypatch.setattr(
        liveness_input,
        "decision_progress_is_authoritative",
        lambda _value: True,
    )
    with pytest.raises(GovernanceError, match="not the current head"):
        liveness_input._validate_previous_heartbeat(
            cast(Any, previous),
            defaults=defaults,
            cursor=cast(Any, cursor),
            current=2,
        )
    sealed = SimpleNamespace(
        sealed_at_step=1,
        window_state_ref="window-state",
        window_root="window-root",
    )
    defaults = replace(defaults, seal=sealed)
    previous = SimpleNamespace(
        current_step=1,
        sealed_window=False,
        heartbeat_continuous=True,
        seal_ref=defaults.seal_ref,
        sealed_at_step=sealed.sealed_at_step,
        window_state_ref=sealed.window_state_ref,
        window_root=sealed.window_root,
    )
    cursor.current_progress = previous
    with pytest.raises(GovernanceError, match="does not preserve the seal"):
        liveness_input._validate_previous_heartbeat(
            cast(Any, previous),
            defaults=defaults,
            cursor=cast(Any, cursor),
            current=2,
        )

    monkeypatch.setattr(
        liveness_input,
        "commit_finality_verification_is_authoritative",
        lambda _value: True,
    )
    monkeypatch.setattr(
        liveness_input,
        "validate_finality_verification_matches_window_impl",
        lambda *_args, **_kwargs: None,
    )
    finality_request = SimpleNamespace(
        finality_verification=SimpleNamespace(certificate_ref="certificate"),
        state=SimpleNamespace(assurance=CommitAssurance.EVIDENCE_BOUND),
    )
    no_seal = replace(defaults, seal=None)
    with pytest.raises(GovernanceError, match="current receipt-backed seal"):
        liveness_input._verified_finality_facts(
            cast(Any, finality_request),
            heartbeat=no_seal,
            current=2,
        )
    mismatched = replace(
        defaults,
        seal=SimpleNamespace(sealed_at_step=1, receipt_ref="receipt"),
    )
    with pytest.raises(GovernanceError, match="same-step local receipt"):
        liveness_input._verified_finality_facts(
            cast(Any, finality_request),
            heartbeat=mismatched,
            current=2,
        )

    monkeypatch.setattr(
        liveness_reduction,
        "commit_window_state_is_current",
        lambda _state: True,
    )
    monkeypatch.setattr(
        liveness_reduction,
        "commit_liveness_input_was_issued_impl",
        lambda _value: True,
    )
    monkeypatch.setattr(
        liveness_reduction,
        "validate_liveness_input_matches_window_impl",
        lambda *_args: None,
    )
    monkeypatch.setattr(liveness_reduction, "_validate_policy", lambda *_args: None)
    monkeypatch.setattr(
        liveness_reduction,
        "_reduction_facts",
        lambda *_args: SimpleNamespace(outcome_kind=None),
    )
    monkeypatch.setattr(
        liveness_reduction,
        "_reduction_request_fingerprint",
        lambda *_args: "request",
    )
    with pytest.raises(GovernanceError, match="window cursor is invalid"):
        liveness_reduction.reduce_commit_liveness_impl(
            cast(Any, SimpleNamespace(_cursor=object())),
            commit_policy=cast(Any, object()),
            liveness_input=cast(Any, object()),
        )


def test_window_and_replay_second_check_races_return_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = commit_window_tests._scenario()
    state = commit_window_tests._window(scenario)
    assessment = commit_window_tests._assessment(scenario, step=5)
    winner = object()
    calls = iter((None, winner))
    monkeypatch.setattr(
        commit_window,
        "_cached_commit_window_transition",
        lambda *_args, **_kwargs: next(calls),
    )
    assert (
        commit_window._transition_commit_window_state(
            state,
            assessment=assessment,
            commit_policy=scenario.policy,
            threshold_snapshot=scenario.threshold,
            current_step=5,
            explicit_unseal=False,
        )
        is winner
    )

    replay = commit_window_tests._replay(run_id="run:changed-totality-race")
    receipt = commit_window_tests._receipt(
        ReplayNamespace.OBSERVATION,
        "record:changed-totality",
        "nonce:changed-totality",
        commit_engine_tests._fingerprint("changed-totality"),
    )
    replay_winner = object()
    replay_calls = iter((None, replay_winner))
    monkeypatch.setattr(
        state_replay,
        "_cached_commit_replay_transition",
        lambda *_args, **_kwargs: next(replay_calls),
    )
    assert (
        state_replay.record_commit_replay_receipts(
            replay,
            current_step=1,
            receipts=(receipt,),
        )
        is replay_winner
    )


def test_window_restart_cursor_race_and_receipt_lineage_guards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = commit_window_tests._scenario()
    state = commit_window_tests._advance(
        commit_window_tests._window(scenario),
        scenario,
        step=5,
    )
    threshold = commit_window_tests._epoch_threshold(
        scenario,
        epoch=commit_window_tests.EPOCH + 1,
        step=6,
    )
    invalid_cursor_state = _mutated(state, _cursor=object())
    restart_inputs = commit_window._commit_window_epoch_restart_inputs(
        state,
        new_epoch=commit_window_tests.EPOCH + 1,
        current_step=6,
        commit_policy=scenario.policy,
        threshold_snapshot=threshold,
        membership_root=commit_engine_tests._fingerprint("next-membership"),
    )
    original_input_builder = commit_window._commit_window_epoch_restart_inputs
    monkeypatch.setattr(
        commit_window,
        "_commit_window_epoch_restart_inputs",
        lambda *_args, **_kwargs: restart_inputs,
    )
    with pytest.raises(GovernanceError, match="window cursor is invalid"):
        commit_window.restart_commit_window_epoch(
            invalid_cursor_state,
            new_epoch=commit_window_tests.EPOCH + 1,
            current_step=6,
            commit_policy=scenario.policy,
            threshold_snapshot=threshold,
            membership_root=commit_engine_tests._fingerprint("next-membership"),
        )
    state._cursor.current_seal = object()
    no_reset_budget = _mutated(state, remaining_reset_budget=0)
    monkeypatch.setattr(
        commit_window,
        "commit_window_seal_is_current",
        lambda _seal: True,
    )
    with pytest.raises(GovernanceError, match="remaining reset budget"):
        commit_window.restart_commit_window_epoch(
            no_reset_budget,
            new_epoch=commit_window_tests.EPOCH + 1,
            current_step=6,
            commit_policy=scenario.policy,
            threshold_snapshot=threshold,
            membership_root=commit_engine_tests._fingerprint("next-membership"),
        )
    state._cursor.current_seal = None
    monkeypatch.setattr(
        commit_window,
        "_commit_window_epoch_restart_inputs",
        original_input_builder,
    )

    winner = object()
    calls = iter((None, winner))
    monkeypatch.setattr(
        commit_window,
        "_cached_commit_window_epoch_restart",
        lambda *_args, **_kwargs: next(calls),
    )
    assert (
        commit_window.restart_commit_window_epoch(
            state,
            new_epoch=commit_window_tests.EPOCH + 1,
            current_step=6,
            commit_policy=scenario.policy,
            threshold_snapshot=threshold,
            membership_root=commit_engine_tests._fingerprint("next-membership"),
        )
        is winner
    )


def test_evidence_outcome_missing_lineage_and_continuity_are_rejected() -> None:
    scenario, assessment, state = commit_liveness_tests._stable_step()
    receipt = commit_liveness_tests._local_receipt(
        state,
        scenario,
        assessment,
        current_step=6,
    )
    seal = commit_window.commit_window_seal_for_state(state)
    verification = commit_liveness_tests.verify_local_commit_finality(
        receipt,
        scenario.context,
        assessment,
        state,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
        current_step=6,
        verifier_id="governance:changed-totality-verifier",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:changed-totality-verifier",
        trace_event_id="trace:changed-totality-verifier",
    )
    liveness_facade._validate_finality_verification_matches_window(
        verification,
        state=state,
        seal=seal,
        current_step=6,
    )
    original_authority_check = commit_window.local_commit_receipt_is_authoritative
    commit_window.local_commit_receipt_is_authoritative = lambda _receipt: True
    try:
        with pytest.raises(GovernanceError, match="assessment_root lineage mismatch"):
            commit_window._validated_commit_window_seal_receipt(
                state,
                _mutated(
                    receipt,
                    assessment_root=commit_engine_tests._fingerprint(
                        "wrong-assessment-root"
                    ),
                ),
            )
    finally:
        commit_window.local_commit_receipt_is_authoritative = original_authority_check
    outcome = liveness_reduction.reduce_commit_liveness_impl(
        state,
        commit_policy=scenario.policy,
        liveness_input=commit_liveness_tests._liveness(
            state,
            scenario,
            assessment=assessment,
            current_step=6,
            finality_status=CommitFinalityStatus.VERIFIED,
            finality_verification=verification,
        ),
    )
    with pytest.raises(GovernanceError, match="assessment_ref is required"):
        commit_state_records._validate_evidence_commit_outcome(
            _mutated(outcome, assessment_ref="")
        )
    with pytest.raises(GovernanceError, match="continuous sealed-window"):
        commit_state_records._validate_evidence_commit_outcome(
            _mutated(outcome, heartbeat_continuous=False)
        )


def test_v2_dependency_type_and_semantic_guards_are_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = state_v2_tests._context("changed-totality-guards")
    request, _ = state_v2_tests._request(
        context,
        advance_ref="advance:changed-totality-guards",
    )

    monkeypatch.setattr(
        replay_operations_v2,
        "_governance_authority_session_state_v2",
        lambda _candidate: (_ for _ in ()).throw(TypeError("controlled")),
    )
    session, failure = replay_operations_v2._validated_session_or_failure(
        object(),
        request,
    )
    assert session is None
    assert failure is not None

    monkeypatch.setattr(
        replay_operations_v2,
        "_canonical_commit_view_v2",
        lambda *_args, **_kwargs: SimpleNamespace(
            disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
            failure=None,
        ),
    )
    parent = replay_operations_v2._load_committed_parent(
        SimpleNamespace(load_commit_view_v2=lambda *_args: object()),
        context.domain,
        request,
    )
    assert parent.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE

    with pytest.raises(ValueError, match="no committed transition"):
        replay_operations_v2._head_from_view(
            cast(Any, SimpleNamespace(committed_transition=None)),
            context.domain,
        )

    monkeypatch.setattr(
        replay_operations_v2,
        "_portable_projection",
        lambda _value: (),
    )
    with pytest.raises(TypeError, match="exact object"):
        replay_operations_v2._decode_state_records(object(), context.domain)

    monkeypatch.setattr(
        replay_operations_v2,
        "_canonical_commit_view_v2",
        lambda _view: SimpleNamespace(
            disposition=GovernanceCommitDispositionV2.COMMITTED,
            committed_transition=SimpleNamespace(
                batch=SimpleNamespace(transition=None),
            ),
            position_observation=object(),
        ),
    )
    with pytest.raises(ValueError, match="no transition"):
        replay_operations_v2._decode_committed_view(
            cast(Any, object()),
            context.domain,
            reader=None,
        )

    class ExplodingInstanceCheck(type):
        def __instancecheck__(cls, instance: object) -> bool:
            raise RuntimeError("controlled protocol failure")

    class ExplodingReader(metaclass=ExplodingInstanceCheck):
        pass

    monkeypatch.setattr(
        replay_operations_v2,
        "GovernanceStateReaderV2",
        ExplodingReader,
    )
    with pytest.raises(TypeError, match="requires StateReader v2"):
        replay_operations_v2._require_state_reader(object())

    with pytest.raises(TypeError, match="exact request v2"):
        replay_source_v2.verify_commit_replay_request_source_v2(
            cast(CommitReplayAdvanceRequestV2, object()),
            source=object(),
            committed_parent_snapshot=None,
        )


def test_v2_duplicate_read_stream_alarm_is_fail_closed() -> None:
    context = state_v2_tests._context("changed-totality-read-set")
    request, _ = state_v2_tests._request(
        context,
        advance_ref="advance:changed-totality-read-set",
    )
    entry = SimpleNamespace(
        stream_ref=request.stream_ref,
        expected_revision=0,
        expected_root="root",
    )
    view = SimpleNamespace(
        committed_transition=SimpleNamespace(
            receipt=SimpleNamespace(parent_root="root"),
            batch=SimpleNamespace(
                read_set=SimpleNamespace(entries=(entry, entry)),
            ),
        )
    )
    with pytest.raises(ValueError, match="duplicate streams"):
        replay_operations_v2._validate_committed_read_set(
            cast(Any, view),
            request,
            {
                "grant_ref": "grant",
                "grant_expected_revision": 0,
                "grant_expected_root": "root",
                "lifecycle_expected_revision": 0,
                "lifecycle_expected_root": "root",
            },
        )
