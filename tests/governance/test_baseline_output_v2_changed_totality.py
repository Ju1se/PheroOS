from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import pytest

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
)
from pheroos.governance._baseline_output_v2 import contracts
from pheroos.governance._baseline_output_v2 import operations
from pheroos.governance._baseline_output_v2.contracts import (
    ActionPermissionV2,
    BaselineOutputTerminalStatusV2,
)
from pheroos.governance._baseline_output_v2.operations import (
    open_baseline_output_authority_session_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
)
from tests.governance.test_baseline_output_v2_operations import (
    _commit_output,
    _context,
    _issue,
    _permission,
    _request,
    _root,
)
from tests.governance.test_baseline_output_v2_semantics import (
    _authorize as _race_authorize,
)
from tests.governance.test_baseline_output_v2_semantics import (
    _context as _race_context,
)
from tests.governance.test_baseline_output_v2_semantics import (
    _issue as _race_issue,
)
from tests.governance.test_baseline_output_v2_semantics import (
    _request as _race_request,
)


def _committed_bundle(
    label: str,
) -> tuple[Any, Any, ActionPermissionV2, Any, dict[str, Any]]:
    context = _context(scope_ref=f"scope:baseline-output-totality:{label}")
    request = _request(
        context,
        request_label=label,
        decision_mode="direct_governance",
    )
    issued = _issue(context, request)
    assert issued.disposition is GovernanceCommitDispositionV2.COMMITTED
    permission = _permission(context, request)
    result = _commit_output(context, request)
    assert result.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert result.authorization == permission
    state = operations._project_state(
        operations._view_or_attempt_state(result.commit_attempt)
    )
    return context, request, permission, result, state


def _output_session(context: Any, request: Any) -> Any:
    return open_baseline_output_authority_session_v2(
        context.capability,
        request,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
    )


def _assert_failure(
    attempt: GovernanceCommitAttemptV2,
    code: AuthorityDiagnosticCodeV2,
    path: str,
) -> None:
    assert attempt.failure is not None
    assert attempt.failure.code is code
    assert attempt.failure.path == path


def test_contract_redundant_guards_remain_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, permission, result, _ = _committed_bundle("contract-guards")

    monkeypatch.setattr(contracts, "_TERMINAL_STATUSES", frozenset())
    with pytest.raises(ValueError, match="terminal_status is unsupported"):
        replace(permission)
    monkeypatch.undo()

    object.__setattr__(result.commit_attempt, "stream_ref", "authority:wrong")
    with pytest.raises(ValueError, match="commit attempt binding is mismatched"):
        contracts._validate_result_permission_binding(result, permission)


def test_contract_committed_state_guards_reject_absence_shape_and_payload() -> None:
    _, _, _, missing_result, _ = _committed_bundle("contract-missing-transition")
    object.__setattr__(missing_result.commit_attempt, "committed_transition", None)
    with pytest.raises(ValueError, match="missing output state"):
        contracts._validate_result_attempt_binding(missing_result)

    _, _, _, shape_result, _ = _committed_bundle("contract-state-shape")
    committed = shape_result.commit_attempt.committed_transition
    assert committed is not None
    assert committed.batch.transition is not None
    object.__setattr__(committed.batch.transition, "state_records", ())
    with pytest.raises(TypeError, match="state must be a mapping"):
        contracts._validate_result_attempt_binding(shape_result)

    _, _, _, payload_result, _ = _committed_bundle("contract-state-payload")
    committed = payload_result.commit_attempt.committed_transition
    assert committed is not None
    assert committed.batch.transition is not None
    object.__setattr__(committed.batch.transition, "state_records", {})
    with pytest.raises(ValueError, match="output state is invalid"):
        contracts._validate_result_attempt_binding(payload_result)


def test_stage_reconciliation_and_view_shape_guards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(scope_ref="scope:baseline-output-totality:stage-reconcile")
    request = _request(
        context,
        request_label="stage-reconcile",
        decision_mode="direct_governance",
    )
    session = open_baseline_output_authority_session_v2(
        context.capability,
        request,
        GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
    )
    sentinel = _issue(context, request)
    assert sentinel.disposition is GovernanceCommitDispositionV2.COMMITTED
    monkeypatch.setattr(operations, "_reconcile", lambda *args, **kwargs: sentinel)

    reconciled = operations._commit_stage(
        context.store,
        request,
        operations._governance_authority_session_state_v2(session),
        role="manifest",
        write_head=context.store.load_head_v2(
            request.scope_ref,
            request.manifest_stream_ref,
        ),
        dependencies=(),
        state={},
        event=cast(Any, object()),
    )
    assert reconciled is sentinel

    monkeypatch.setattr(operations, "_view_state_records", lambda view: None)
    assert not operations._verified_signal_matches(sentinel, request, {})
    assert not operations._permission_view_matches(object(), request, session)
    assert not operations._output_view_matches(object(), request, session)
    assert not operations._stage_view_matches(object(), {})


def test_mutated_quorum_and_fallback_contracts_fail_closed() -> None:
    quorum_context = _context(scope_ref="scope:baseline-output-totality:quorum-target")
    quorum_request = _request(
        quorum_context,
        request_label="quorum-target",
        decision_mode="quorum",
    )
    object.__setattr__(
        quorum_request.manifest.quorum_policy,
        "target",
        "target:substituted",
    )
    with pytest.raises(ValueError, match="quorum policy target is mismatched"):
        operations._evaluate_quorum(quorum_request, {"signals": []})

    fallback_context = _context(
        scope_ref="scope:baseline-output-totality:fallback-shape"
    )
    fallback_request = _request(
        fallback_context,
        request_label="fallback-shape",
        decision_mode="quorum",
    )
    fallback = next(
        candidate
        for candidate in fallback_request.manifest.candidates
        if candidate.safe_fallback
    )
    object.__setattr__(fallback, "safe_fallback", False)
    with pytest.raises(ValueError, match="one declared safe candidate"):
        operations._safe_fallback(fallback_request)


def test_durable_input_recomputation_mismatch_is_bound_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(scope_ref="scope:baseline-output-totality:durable-inputs")
    request = _request(
        context,
        request_label="durable-inputs",
        decision_mode="direct_governance",
    )
    assert _issue(context, request).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    monkeypatch.setattr(
        operations,
        "_evaluate_decision",
        lambda request, evidence, stop: {"candidate_ref": "candidate:tampered"},
    )

    loaded = operations._load_output_inputs(context.store, request)

    assert isinstance(loaded, GovernanceCommitAttemptV2)
    _assert_failure(
        loaded,
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/authority_inputs",
    )


def test_reader_protocol_instancecheck_exception_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _ExplodingReaderMeta(type):
        def __instancecheck__(cls, instance: object) -> bool:
            raise RuntimeError("controlled protocol instancecheck failure")

    class _ExplodingReader(metaclass=_ExplodingReaderMeta):
        pass

    context = _context(scope_ref="scope:baseline-output-totality:reader-protocol")
    request = _request(
        context,
        request_label="reader-protocol",
        decision_mode="direct_governance",
    )
    monkeypatch.setattr(operations, "GovernanceStateReaderV2", _ExplodingReader)

    attempt = operations._load_recovery_attempt(request, object())

    assert attempt.disposition is GovernanceCommitDispositionV2.INVALID
    _assert_failure(
        attempt,
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/state_reader",
    )


def test_invalid_committed_output_is_converted_to_reconciliation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, request, _, result, _ = _committed_bundle("invalid-output-state")

    def _reject_state(state: object, candidate: object) -> None:
        raise ValueError("controlled invalid committed state")

    monkeypatch.setattr(operations, "_require_output_state", _reject_state)
    rejected = operations._result_from_attempt(
        context.store,
        request,
        result.commit_attempt,
    )

    assert rejected.disposition is GovernanceCommitDispositionV2.INVALID
    _assert_failure(
        rejected.commit_attempt,
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
        "/committed_transition",
    )


@pytest.mark.parametrize(
    ("attack", "message"),
    [
        ("undeclared-candidate", "candidate is not declared"),
        ("wrong-fallback", "fallback candidate is invalid"),
        ("wrong-direct-candidate", "direct output candidate is invalid"),
        ("invalid-terminal", "terminal status is invalid"),
        ("permission-binding", "permission binding is invalid"),
        ("result-binding", "result binding is invalid"),
    ],
)
def test_recovered_output_semantic_bindings_reject_tampering(
    attack: str,
    message: str,
) -> None:
    _, request, permission, result, state = _committed_bundle(
        f"recovery-semantic:{attack}"
    )
    status = cast(BaselineOutputTerminalStatusV2, result.terminal_status)
    candidate_ref = cast(str, result.candidate_ref)
    result_root = result.result_root
    candidate_permission = permission

    if attack == "undeclared-candidate":
        candidate_ref = "candidate:undeclared"
    elif attack == "wrong-fallback":
        status = BaselineOutputTerminalStatusV2.SAFE_FALLBACK
    elif attack == "wrong-direct-candidate":
        candidate_ref = "candidate:fallback"
    elif attack == "invalid-terminal":
        status = BaselineOutputTerminalStatusV2.INVALID
    elif attack == "permission-binding":
        candidate_permission = replace(
            permission,
            evidence_root=_root("7"),
            permission_root="",
        )
    else:
        state["permission_root"] = _root("6")

    with pytest.raises(ValueError, match=message):
        operations._require_recovered_output_bindings(
            state,
            request,
            candidate_permission,
            status,
            candidate_ref,
            result_root,
            result.commit_attempt,
        )


@pytest.mark.parametrize(
    ("attack", "message"),
    [
        ("missing-transition", "transition is absent"),
        ("binding-fields", "binding fields are invalid"),
        ("binding-value", "session binding is invalid"),
        ("shared-grant", "shared grant binding is invalid"),
        ("read-set", "read set is invalid"),
        ("precondition", "authority precondition is invalid"),
        ("trace-type", "Trace event is invalid"),
        ("trace-lineage", "Trace binding is invalid"),
    ],
)
def test_recovery_commit_material_rejects_structural_tampering(
    attack: str,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, request, permission, result, state = _committed_bundle(
        f"recovery-material:{attack}"
    )
    attempt = result.commit_attempt
    binding = cast(dict[str, Any], state["session_binding"])

    if attack == "missing-transition":
        object.__setattr__(attempt, "committed_transition", None)
    elif attack == "binding-fields":
        binding.pop("operation")
    elif attack == "binding-value":
        binding["run_ref"] = "run:substituted"
    elif attack == "shared-grant":
        binding["grant_root"] = _root("5")
    elif attack == "read-set":
        monkeypatch.setattr(
            operations,
            "GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2",
            "authority:missing-lifecycle",
        )
    elif attack == "precondition":
        binding["grant_expected_revision"] += 1
    else:
        committed = attempt.committed_transition
        assert committed is not None
        batch = committed.batch
        event = batch.trace_batch.events[0]
        if attack == "trace-type":
            replacement_event = SimpleNamespace(
                event_type="baseline_output_substituted",
                lineage=event.lineage,
            )
        else:
            lineage = deepcopy(dict(event.lineage))
            lineage["result_root"] = _root("4")
            replacement_event = SimpleNamespace(
                event_type=event.event_type,
                lineage=lineage,
            )
        replacement_batch = SimpleNamespace(
            transition=batch.transition,
            read_set=batch.read_set,
            trace_batch=SimpleNamespace(events=(replacement_event,)),
        )
        attempt = cast(
            GovernanceCommitAttemptV2,
            SimpleNamespace(
                committed_transition=SimpleNamespace(
                    batch=replacement_batch,
                    receipt=committed.receipt,
                )
            ),
        )

    with pytest.raises(ValueError, match=message):
        operations._require_recovery_commit_material(
            state,
            request,
            permission,
            attempt,
        )


def test_missing_transition_after_state_projection_denies_currentness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, request, permission, result, state = _committed_bundle(
        "currentness-missing-transition"
    )
    attempt = result.commit_attempt
    object.__setattr__(attempt, "committed_transition", None)
    monkeypatch.setattr(operations, "_view_or_attempt_state", lambda attempt: state)

    assert not operations._permission_current_for_result(
        context.store,
        request,
        permission,
        attempt,
    )


def test_failure_result_delegates_retry_attempt() -> None:
    context = _race_context(scope_ref="scope:baseline-output-totality:failure-retry")
    request = _race_request(context, label="loser")
    rival = _race_request(context, label="winner")
    assert _race_issue(context, request).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    context.store.race_once(
        request.output_stream_ref,
        lambda: _race_issue(context, rival),
    )
    raced = _race_authorize(context, request)
    assert raced.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    retry = raced.commit_attempt

    result = operations._failure_result(request, retry)

    assert result.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED


def test_session_validation_store_and_domain_exceptions_are_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(scope_ref="scope:baseline-output-totality:session-errors")
    request = _request(
        context,
        request_label="session-errors",
        decision_mode="direct_governance",
    )
    session = _output_session(context, request)

    def _raise_store(candidate: object) -> None:
        raise TypeError("controlled store projection failure")

    monkeypatch.setattr(operations, "_require_store", _raise_store)
    _, store_failure = operations._validated_session_or_failure(
        session,
        request,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
        request.output_stream_ref,
        request.output_transition_id,
    )
    assert store_failure is not None
    _assert_failure(
        store_failure,
        AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
        "/authority_session",
    )
    monkeypatch.undo()

    def _raise_domain(candidate: object) -> Any:
        raise GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/domain",
        )

    monkeypatch.setattr(operations, "_session_domain", _raise_domain)
    _, domain_failure = operations._validated_session_or_failure(
        session,
        request,
        GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
        request.output_stream_ref,
        request.output_transition_id,
    )
    assert domain_failure is not None
    _assert_failure(
        domain_failure,
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/domain",
    )


def test_permission_grant_loading_distinguishes_missing_and_malformed() -> None:
    context, request, permission, _, _ = _committed_bundle("grant-loading")
    session = operations._governance_authority_session_state_v2(
        _output_session(context, request)
    )

    class _MissingStore:
        def load_state_v2(self, scope_ref: str, stream_ref: str) -> object:
            raise KeyError(stream_ref)

    missing = operations._permission_issuer_grant_head(
        cast(Any, _MissingStore()),
        request,
        session,
        permission,
    )
    assert isinstance(missing, GovernanceCommitAttemptV2)
    _assert_failure(
        missing,
        AuthorityDiagnosticCodeV2.GOVERNANCE_ACTION_NOT_AUTHORIZED,
        "/permission/grant_ref",
    )

    class _MalformedStore:
        def load_state_v2(self, scope_ref: str, stream_ref: str) -> object:
            return {"grant": {}}

    malformed = operations._permission_issuer_grant_head(
        cast(Any, _MalformedStore()),
        request,
        session,
        permission,
    )
    assert isinstance(malformed, GovernanceCommitAttemptV2)
    _assert_failure(
        malformed,
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
        "/permission/grant_ref",
    )


@pytest.mark.parametrize(
    ("attack", "expected_code", "expected_path"),
    [
        (
            "unverified-status",
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
            "/permission/grant_ref",
        ),
        (
            "binding",
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/permission/grant_ref",
        ),
        (
            "operation",
            AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
            "/permission/grant_ref",
        ),
        (
            "expiry",
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED,
            "/permission/issued_epoch",
        ),
    ],
)
def test_permission_grant_semantic_failures_are_distinct(
    attack: str,
    expected_code: AuthorityDiagnosticCodeV2,
    expected_path: str,
) -> None:
    context, request, permission, _, _ = _committed_bundle(f"grant-semantics:{attack}")
    state = {"status": "pending" if attack == "unverified-status" else "active"}
    grant = context.grant
    candidate_permission = permission

    if attack == "binding":
        other = _context(scope_ref="scope:baseline-output-totality:grant-other")
        grant = other.grant
    elif attack in {"operation", "expiry"}:
        grant_values = context.grant.to_dict()
        grant_values.pop("grant_root")
        if attack == "operation":
            grant_values["operations"] = [
                GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT.value
            ]
        else:
            grant_values["expires_at_epoch"] = 1
        grant = GovernanceIssuerGrantV2.from_dict(
            {
                **grant_values,
                "grant_root": "",
            }
        )
        candidate_permission = replace(
            permission,
            grant_root=grant.grant_root,
            grant_binding_ref=grant.grant_binding_ref,
            permission_root="",
        )

    failure = operations._permission_issuer_grant_failure(
        request,
        candidate_permission,
        state,
        grant,
    )

    assert failure == (expected_code, expected_path)


@pytest.mark.parametrize(
    ("role", "schema"),
    [
        ("evidence", "baseline evidence state binding is invalid"),
        ("stop", "baseline stop state binding is invalid"),
        ("decision", "baseline decision state binding is invalid"),
        ("output", "baseline output state binding is invalid"),
    ],
)
def test_durable_state_decoders_reject_binding_substitution(
    role: str,
    schema: str,
) -> None:
    context, request, _, _, output_state = _committed_bundle(f"decoder-binding:{role}")
    stream_by_role = {
        "evidence": request.evidence_stream_ref,
        "stop": request.stop_stream_ref,
        "decision": request.decision_stream_ref,
    }
    state = (
        output_state
        if role == "output"
        else operations._project_state(
            context.store.load_state_v2(
                request.scope_ref,
                stream_by_role[role],
            )
        )
    )
    state["schema"] = "pheroos-governance-substituted-v2"
    decoder = {
        "evidence": operations._decode_evidence_state,
        "stop": operations._decode_stop_state,
        "decision": operations._decode_decision_state,
        "output": operations._require_output_state,
    }[role]

    with pytest.raises(ValueError, match=schema):
        decoder(state, request)


def test_projection_field_and_transition_shape_guards() -> None:
    with pytest.raises(TypeError, match="must project to an exact object"):
        operations._project_state([])
    with pytest.raises(ValueError, match="state fields are invalid"):
        operations._require_state_fields({"extra": True}, set(), "controlled")

    _, _, _, absent_result, _ = _committed_bundle("attempt-transition-absent")
    object.__setattr__(absent_result.commit_attempt, "committed_transition", None)
    with pytest.raises(ValueError, match="missing transition"):
        operations._view_or_attempt_state(absent_result.commit_attempt)

    _, _, _, seal_result, _ = _committed_bundle("attempt-transition-seal")
    committed = seal_result.commit_attempt.committed_transition
    assert committed is not None
    object.__setattr__(committed.batch, "transition", None)
    with pytest.raises(ValueError, match="cannot be a seal"):
        operations._view_or_attempt_state(seal_result.commit_attempt)
