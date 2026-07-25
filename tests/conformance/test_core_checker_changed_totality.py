from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import pytest

from pheroos.conformance._runtime_integration_certificate import (
    _CertificateStateObservationV1,
)
from pheroos.conformance._runtime_integration_contracts import (
    RuntimeControlInputV1,
)
from pheroos.conformance._runtime_integration_fixture import (
    build_runtime_integration_request_v1,
)
from pheroos.conformance._runtime_integration_reference import (
    ReferenceRuntimeIntegrationAdapterV1,
)
from pheroos.conformance.checks import authority_session_v2_contract as session_check
from pheroos.conformance.checks import authority_store_v2_contract as store_check
from pheroos.conformance.checks import baseline_output_v2_contract as output_check
from pheroos.conformance.checks import (
    commit_certificate_v2_contract as certificate_check,
)
from pheroos.conformance.checks import (
    commit_decision_v2_contract as decision_check,
)
from pheroos.conformance.checks import (
    commit_evidence_v2_contract as evidence_check,
)
from pheroos.conformance.checks import (
    commit_finality_v2_contract as finality_check,
)
from pheroos.conformance.checks import commit_gate_v2_contract as gate_check
from pheroos.conformance.checks import (
    distributed_commit_v2_contract as distributed_check,
)
from pheroos.conformance.checks import (
    driver_invocation_v2_contract as invocation_check,
)
from pheroos.conformance.checks import (
    _commit_decision_v2_context_support as decision_context,
)
from pheroos.conformance.checks import (
    _commit_gate_v2_adversarial_support as gate_adversarial,
)
from pheroos.conformance.checks import (
    _commit_gate_v2_context_support as gate_context,
)
from pheroos.conformance.checks import (
    _distributed_v2_context_support as distributed_context,
)
from pheroos.conformance.checks import (
    _distributed_v2_input_support as distributed_input,
)
from pheroos.conformance.checks import (
    runtime_integration_v1_contract as runtime_check,
)
from pheroos.conformance.checks._distributed_v2_vertical_support import (
    build_verified_distributed_vertical_v2,
    freeze_external_witness_conflict_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.drivers import DriverInvocationStoreV2
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerOperationV2,
    open_governance_authority_session_v2,
)
from pheroos.governance.authority_store_v2 import (
    GovernanceCommitDispositionV2,
    GovernanceHeadV2,
)
from pheroos.governance.commit_certificate_v2 import (
    CommitCertificateStatusV2,
)
from pheroos.governance.commit_decision_v2 import (
    CommitDecisionMutationKindV2,
)
from pheroos.governance.commit_evidence_v2 import (
    VerifiedCommitEvidenceSourceV2,
    evaluate_commit_evidence_projection_v2,
)
from pheroos.governance.distributed_commit_v2 import (
    DistributedLaneStatusV2,
)
from pheroos.protocol import GovernanceReadPreconditionV2
from pheroos.protocol.schema_document import ProtocolSchemaVersionError


def _store_adapter() -> ReferenceGovernanceStateStoreConformanceAdapterV2:
    return ReferenceGovernanceStateStoreConformanceAdapterV2()


def test_authority_session_matrix_alarms_on_capability_and_session_shape_faults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _store_adapter()
    monkeypatch.setattr(
        session_check,
        "bind_governance_issuer_capability_v2",
        lambda *_args, **_kwargs: SimpleNamespace(
            run_ref="run:wrong",
            grant_root="sha256:" + "0" * 64,
            verification_root=None,
            profile=session_check.AUTHORITY_LOCAL_PROFILE_V2,
        ),
    )
    result = session_check.run_governance_authority_session_conformance_v2(adapter)
    assert "run_bound_capability" in result.detail

    monkeypatch.undo()
    monkeypatch.setattr(
        session_check,
        "open_governance_authority_session_v2",
        lambda _capability, request: SimpleNamespace(
            run_ref=session_check._RUN_REF,
            request_ref=request.request_ref,
            request_root=request.request_root,
            operation=GovernanceIssuerOperationV2.VERIFY_SIGNAL,
        ),
    )
    result = session_check.run_governance_authority_session_conformance_v2(adapter)
    assert "request_bound_session" in result.detail


def _authority_handle_fixture() -> tuple[Any, Any, Any, Any, Any]:
    adapter = _store_adapter()
    domain, store, grant, capability = session_check._active_local_setup(
        adapter,
        "totality-handles",
    )
    request = session_check._signal_request(
        domain,
        request_ref="request:totality:handles",
        transition_id="transition:totality:handles",
        observed_epoch=3,
    )
    session = open_governance_authority_session_v2(capability, request)
    return domain, store, grant, session, request


def test_authority_session_opaque_handle_alarms_are_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain, store, _grant, session, request = _authority_handle_fixture()
    capability = session_check.bind_governance_issuer_capability_v2(
        store,
        domain,
        session_check._grant(domain),
        session_check._RUN_REF,
        3,
    )
    monkeypatch.setattr(session_check, "copy", lambda _value: object())
    monkeypatch.setattr(session_check, "deepcopy", lambda _value: object())
    monkeypatch.setattr(session_check, "_pickle_rejected", lambda _value: False)
    monkeypatch.setattr(
        session_check,
        "hasattr",
        lambda _value, name: name in {"__dict__", "to_dict"},
        raising=False,
    )
    problems: list[str] = []
    session_check._evaluate_opaque_handle_boundaries(
        domain,
        store,
        capability,
        session,
        request,
        problems,
    )
    assert problems[:6] == [
        "capability_copy_identity",
        "session_copy_identity",
        "capability_pickle",
        "session_pickle",
        "capability_portable_surface",
        "session_portable_surface",
    ]


def test_authority_session_forgery_and_request_binding_alarms_are_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain, store, grant, session, request = _authority_handle_fixture()
    capability = session_check.bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        session_check._RUN_REF,
        3,
    )
    monkeypatch.setattr(session_check, "_has_failure", lambda *_args: False)
    monkeypatch.setattr(session_check, "_binding_rejected", lambda *_args: False)
    problems: list[str] = []
    session_check._evaluate_forged_handle_rejection(
        domain,
        store,
        session,
        request,
        cast(GovernanceHeadV2, object()),
        problems,
    )
    assert problems == [
        "missing_session",
        "fake_shaped_session",
        "forged_session",
        "forged_capability",
        "invalid_handle_mutation",
    ]

    problems = []
    session_check._evaluate_request_binding_boundaries(
        domain,
        grant,
        capability,
        session,
        problems,
    )
    assert problems == [
        "wrong_run",
        "wrong_target",
        "wrong_request",
        "wrong_status",
        "wrong_operation",
    ]


def test_authority_session_expiry_store_and_immutable_protocol_alarms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _store_adapter()
    monkeypatch.setattr(session_check, "_binding_rejected", lambda *_args: False)
    problems: list[str] = []
    session_check._evaluate_expiry_boundaries(adapter, problems)
    assert problems == ["expired_capability", "expired_session"]

    monkeypatch.undo()
    monkeypatch.setattr(
        session_check,
        "isinstance",
        lambda *_args: False,
        raising=False,
    )
    problems = []
    session_check._evaluate_immutable_mapping_reads(adapter, problems)
    assert problems == ["immutable_read_store_protocol"]

    monkeypatch.undo()
    monkeypatch.setattr(session_check, "_has_failure", lambda *_args: False)
    monkeypatch.setattr(session_check, "_binding_rejected", lambda *_args: False)
    problems = []
    session_check._evaluate_store_version_boundary(adapter, problems)
    assert {
        "store_version_activation",
        "store_version_bind",
        "store_version_commit",
        "store_version_open",
    }.issubset(problems)


def test_authority_session_authenticated_profile_alarms_are_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _store_adapter()
    domain = session_check._authenticated_domain(adapter, "totality-authenticated")
    store = adapter.create_store_v2((domain,))
    grant = session_check._grant(domain)

    monkeypatch.setattr(session_check, "_has_failure", lambda *_args: False)
    problems: list[str] = []
    assert session_check._evaluate_authenticated_activation(
        store,
        domain,
        grant,
        problems,
    )
    assert problems == [
        "authenticated_activation_missing_verifier",
        "authenticated_activation_reject",
        "authenticated_activation_mismatch",
        "authenticated_activation_wrong-epoch",
        "authenticated_activation_raise",
    ]

    monkeypatch.undo()
    monkeypatch.setattr(session_check, "_binding_rejected", lambda *_args: False)
    monkeypatch.setattr(
        session_check,
        "bind_governance_issuer_capability_v2",
        lambda *_args, **_kwargs: SimpleNamespace(
            profile=session_check.AUTHORITY_LOCAL_PROFILE_V2,
            verification_root=None,
            verifier_ref=None,
        ),
    )
    problems = []
    session_check._evaluate_authenticated_binding(store, domain, grant, problems)
    assert problems == [
        "authenticated_bind_missing_verifier",
        "authenticated_bind_reject",
        "authenticated_bind_mismatch",
        "authenticated_bind_wrong-epoch",
        "authenticated_bind_raise",
        "authenticated_later_bind",
    ]

    monkeypatch.undo()
    monkeypatch.setattr(session_check, "_has_failure", lambda *_args: False)
    problems = []
    session_check._evaluate_local_profile_verifier_rejection(adapter, problems)
    assert problems == ["local_profile_verifier_rejected_without_call"]
    assert session_check._binding_rejected(lambda: None, object()) is False
    assert session_check._pickle_rejected(object()) is False


def test_authority_store_internal_image_and_batch_guards_are_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(TypeError, match="non-JSON"):
        store_check._validate_image_json(object())
    with pytest.raises(TypeError, match="key must be text"):
        store_check._validate_image_mapping({1: "value"})

    for name in (
        "_tamper_reference_commit",
        "_tamper_reference_projection",
        "_tamper_reference_trace_binding",
        "_tamper_reference_seal",
        "_tamper_reference_closure",
    ):
        monkeypatch.setattr(store_check, name, lambda *_args: False)
    with pytest.raises(AssertionError, match="unhandled"):
        store_check._tamper_reference_entry(object(), object(), "unknown")

    monkeypatch.undo()
    assert (
        store_check._tamper_reference_closure(
            SimpleNamespace(),
            SimpleNamespace(batch=SimpleNamespace(stream_ref="stream")),
            "unknown",
            "sha256:" + "0" * 64,
        )
        is False
    )

    adapter = _store_adapter()
    scope_ref = "scope:store-check:target-read-set"
    store = adapter.create_store_v2((adapter.create_domain_v2(scope_ref),))
    batch = store_check._transition_batch(
        adapter,
        store,
        scope_ref,
        "stream:target",
        "transition:target",
        1,
        read_streams=("stream:other",),
    )
    assert {entry.stream_ref for entry in batch.read_set.entries} == {
        "stream:other",
        "stream:target",
    }


def test_protocol_declaration_bodies_are_inert_but_callable() -> None:
    assert (
        store_check.GovernanceStateStoreConformanceAdapterV2.create_domain_v2(
            cast(Any, object()),
            "scope:protocol-body",
        )
        is None
    )
    assert (
        store_check.GovernanceStateStoreConformanceAdapterV2.create_store_v2(
            cast(Any, object()),
            (),
        )
        is None
    )
    assert (
        store_check.GovernanceStateStoreConformanceAdapterV2.restart_store_v2(
            cast(Any, object()),
            cast(Any, object()),
        )
        is None
    )
    assert (
        store_check.GovernanceStateStoreConformanceAdapterV2.create_failure_injected_store_v2(
            cast(Any, object()),
            "before_validation",
            (),
        )
        is None
    )
    assert (
        store_check.GovernanceStateStoreConformanceAdapterV2.observe_store_v2(
            cast(Any, object()),
            cast(Any, object()),
            "scope:protocol-body",
        )
        is None
    )
    assert (
        store_check.GovernanceStateStoreConformanceAdapterV2.tamper_store_v2(
            cast(Any, object()),
            cast(Any, object()),
            "scope:protocol-body",
            "transition:protocol-body",
            "case",
        )
        is None
    )
    assert (
        certificate_check.CommitCertificateConformanceAdapterV2.attestation_ref_v2(
            cast(Any, object()),
            "issuer",
            "sha256:" + "0" * 64,
        )
        is None
    )
    assert (
        certificate_check.CommitCertificateConformanceAdapterV2.verifier_v2(
            cast(Any, object())
        )
        is None
    )
    assert (
        invocation_check.DriverInvocationStoreConformanceAdapterV2.create_store_v2(
            cast(Any, object())
        )
        is None
    )
    assert (
        invocation_check.DriverInvocationStoreConformanceAdapterV2.restart_store_v2(
            cast(Any, object()),
            b"checkpoint",
        )
        is None
    )
    assert (
        invocation_check.DriverInvocationStoreConformanceAdapterV2.create_failure_injected_store_v2(
            cast(Any, object()),
            "before_commit",
        )
        is None
    )
    assert (
        invocation_check.DriverInvocationStoreConformanceAdapterV2.invoke_v2(
            cast(Any, object()),
            cast(Any, object()),
        )
        is None
    )


def test_baseline_output_schema_dispatch_alarms_and_reader_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = output_check.read_capability_manifest

    def wrong_v3(payload: Any, *, schema_version: str) -> Any:
        if schema_version == output_check.CAPABILITY_SCHEMA_V3:
            return object()
        return original(payload, schema_version=schema_version)

    monkeypatch.setattr(output_check, "read_capability_manifest", wrong_v3)
    problems: list[str] = []
    output_check._evaluate_protocol_v3_opt_in(problems)
    assert problems == ["protocol_v3_explicit_opt_in"]

    monkeypatch.undo()

    def wrong_diagnostic(payload: Any, *, schema_version: str) -> Any:
        if schema_version == output_check.CAPABILITY_SCHEMA_V2:
            raise ProtocolSchemaVersionError("wrong-code", "injected")
        return original(payload, schema_version=schema_version)

    monkeypatch.setattr(output_check, "read_capability_manifest", wrong_diagnostic)
    problems = []
    output_check._evaluate_protocol_v3_opt_in(problems)
    assert problems == ["protocol_v3_cross_selector_diagnostic"]

    monkeypatch.undo()

    def inferred(payload: Any, *, schema_version: str) -> Any:
        if schema_version == output_check.CAPABILITY_SCHEMA_V2:
            return object()
        return original(payload, schema_version=schema_version)

    monkeypatch.setattr(output_check, "read_capability_manifest", inferred)
    problems = []
    output_check._evaluate_protocol_v3_opt_in(problems)
    assert problems == ["protocol_v3_shape_inference"]

    monkeypatch.setattr(
        output_check,
        "read_capability_manifest",
        lambda *_args, **_kwargs: object(),
    )
    with pytest.raises(TypeError, match="non-scoped capability"):
        output_check._read_manifest(decision_mode="quorum", threshold=2)


def test_certificate_checker_detects_every_accepting_verifier_regression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        certificate_check,
        "verify_portable_commit_certificate_v2",
        lambda *_args, **_kwargs: True,
    )
    result = certificate_check.run_governance_commit_certificate_conformance_v2(
        certificate_check.ReferenceCommitCertificateConformanceAdapterV2()
    )
    assert result.ok is False
    for detail in (
        "body_mutation:target_ref",
        "authority_leaf_mutation",
        "envelope_mutation:certificate_id",
        "unknown_envelope_field",
        "boolean_integer_substitution",
        "expected_context_binding",
        "raw_mapping_as_authority",
    ):
        assert detail in result.detail


def test_commit_decision_checker_alarms_on_non_durable_seal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = decision_check._ready_state_v2
    original_context = decision_check.ready_context_v2
    calls = 0
    captured: dict[str, Any] = {}

    def capture_context(*args: Any, **kwargs: Any) -> Any:
        value = original_context(*args, **kwargs)
        captured["context"] = value
        return value

    def state_fault(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        state = original(*args, **kwargs)
        if calls == 4:
            return SimpleNamespace(
                snapshot=SimpleNamespace(
                    seal=None,
                    mutation_kind=CommitDecisionMutationKindV2.SEALED,
                )
            )
        return state

    monkeypatch.setattr(decision_check, "ready_context_v2", capture_context)
    monkeypatch.setattr(decision_check, "_ready_state_v2", state_fault)
    problems: list[str] = []
    decision_check._ready_seal_terminal_restart(_store_adapter(), problems)
    assert "durable_seal" in problems
    context = captured["context"]
    assert context.assurance is context.support_context.assurance
    capability = decision_context.decision_capability_v2(context, 1)
    assert capability.run_ref == decision_context.RUN_REF
    with pytest.raises(RuntimeError, match="setup failed"):
        decision_context._require_committed(
            SimpleNamespace(
                disposition=GovernanceCommitDispositionV2.INVALID,
                failure=None,
            ),
            "injected",
        )


def test_commit_evidence_vertical_diagnostic_alarms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _store_adapter()
    monkeypatch.setattr(
        evidence_check,
        "commit_evidence_state_is_current_v2",
        lambda _state: False,
    )
    problems: list[str] = []
    evidence_check._vertical_restart(adapter, problems)
    assert {"current_rehydration", "restart_rehydration"}.issubset(problems)

    monkeypatch.undo()
    original_evaluate = evaluate_commit_evidence_projection_v2

    def evaluation_fault(*args: Any, **kwargs: Any) -> Any:
        value = original_evaluate(*args, **kwargs)
        return replace(value, positive_evidence=0, evaluation_root="")

    monkeypatch.setattr(
        evidence_check,
        "evaluate_commit_evidence_projection_v2",
        evaluation_fault,
    )
    problems = []
    evidence_check._vertical_restart(adapter, problems)
    assert problems == ["qualified_success_projection_evaluation"]

    monkeypatch.undo()
    original_advance = evidence_check.advance_v2
    calls = 0

    def retry_fault(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        value = original_advance(*args, **kwargs)
        if calls > 1:
            return SimpleNamespace(
                disposition=GovernanceCommitDispositionV2.INVALID,
                committed_transition=None,
            )
        return value

    monkeypatch.setattr(evidence_check, "advance_v2", retry_fault)
    problems = []
    evidence_check._vertical_restart(adapter, problems)
    assert problems == ["lost_response_exact_retry", "restart_exact_retry"]


def test_commit_evidence_source_and_subject_diagnostic_alarms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _store_adapter()
    original_request = evidence_check.request_v2
    calls = 0

    def order_fault(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        request, source = original_request(*args, **kwargs)
        if calls == 2:
            return (
                SimpleNamespace(request_root="sha256:" + "0" * 64),
                SimpleNamespace(context_root="sha256:" + "1" * 64),
            )
        return request, source

    monkeypatch.setattr(evidence_check, "request_v2", order_fault)
    problems: list[str] = []
    evidence_check._source_and_order(adapter, problems)
    assert "input_order_determinism" in problems

    monkeypatch.undo()
    original_advance = evidence_check.advance_v2

    def accepting_forgery(context: Any, request: Any, source: Any) -> Any:
        if not isinstance(source, VerifiedCommitEvidenceSourceV2):
            return SimpleNamespace(
                disposition=GovernanceCommitDispositionV2.COMMITTED,
                failure=None,
            )
        return original_advance(context, request, source)

    monkeypatch.setattr(evidence_check, "advance_v2", accepting_forgery)
    problems = []
    evidence_check._source_and_order(adapter, problems)
    assert {
        "non_authoritative_source:portable_request",
        "non_authoritative_source:portable_snapshot",
        "non_authoritative_source:digest",
        "non_authoritative_source:same_shape",
    }.issubset(problems)

    monkeypatch.undo()
    original_evaluate = evidence_check.evaluate_commit_evidence_projection_v2

    def insufficient_fault(*args: Any, **kwargs: Any) -> Any:
        value = original_evaluate(*args, **kwargs)
        return replace(value, source_diversity=99, evaluation_root="")

    monkeypatch.setattr(
        evidence_check,
        "evaluate_commit_evidence_projection_v2",
        insufficient_fault,
    )
    problems = []
    evidence_check._source_and_order(adapter, problems)
    assert problems == ["single_source_insufficient"]

    def subject_fault(*args: Any, **kwargs: Any) -> Any:
        value = original_evaluate(*args, **kwargs)
        return replace(value, positive_evidence=1, evaluation_root="")

    monkeypatch.setattr(
        evidence_check,
        "evaluate_commit_evidence_projection_v2",
        subject_fault,
    )
    problems = []
    evidence_check._conflicting_fork(adapter, problems)
    assert problems == ["candidate_claim_subject_isolation"]


def test_commit_finality_handle_and_portability_alarms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _store_adapter()
    monkeypatch.setattr(
        finality_check,
        "verified_commit_certificate_finality_input_v2",
        lambda *_args, **_kwargs: object(),
    )
    problems: list[str] = []
    with pytest.raises((TypeError, ValueError)):
        finality_check._certificate_verified_and_portability_v2(adapter, problems)
    assert problems == ["certificate_handle_exact_type"]

    monkeypatch.undo()
    monkeypatch.setattr(
        finality_check,
        "prepare_decision_successor_v2",
        lambda *_args, **_kwargs: (object(), object()),
    )
    problems = []
    finality_check._certificate_verified_and_portability_v2(adapter, problems)
    assert {
        "portable_substituted_handle:portable_projection",
        "portable_substituted_handle:portable_projection_root",
    }.issubset(problems)


def test_commit_finality_conflict_and_deadline_alarms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _store_adapter()
    original_certificate = finality_check.verified_certificate_v2
    calls = 0

    def certificate_fault(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        value = original_certificate(*args, **kwargs)
        if calls == 3:
            return SimpleNamespace(
                state=SimpleNamespace(
                    snapshot=SimpleNamespace(status=CommitCertificateStatusV2.VERIFIED)
                )
            )
        return value

    monkeypatch.setattr(finality_check, "verified_certificate_v2", certificate_fault)
    problems: list[str] = []
    finality_check._certificate_race_and_conflict_v2(adapter, problems)
    assert problems == ["certificate_conflict_not_durable"]

    monkeypatch.undo()
    original_freeze = finality_check.freeze_external_witness_conflict_v2

    def freeze_fault(*args: Any, **kwargs: Any) -> Any:
        value = original_freeze(*args, **kwargs)
        return SimpleNamespace(
            witness=SimpleNamespace(
                snapshot=SimpleNamespace(
                    status=DistributedLaneStatusV2.ACTIVE,
                    mutation_kind=value.witness.snapshot.mutation_kind,
                )
            )
        )

    monkeypatch.setattr(
        finality_check,
        "freeze_external_witness_conflict_v2",
        freeze_fault,
    )
    problems = []
    finality_check._distributed_conflict_v2(adapter, problems)
    assert problems == ["distributed_conflict_not_frozen"]

    monkeypatch.undo()
    monkeypatch.setattr(
        finality_check,
        "distributed_conflict_finality_v2",
        lambda *_args, **_kwargs: object(),
    )
    problems = []
    finality_check._distributed_conflict_v2(adapter, problems)
    assert problems == ["distributed_conflict_handle_exact_type"]

    monkeypatch.undo()
    monkeypatch.setattr(
        finality_check,
        "distributed_decision_state_v2",
        lambda *_args, **_kwargs: SimpleNamespace(
            snapshot=SimpleNamespace(outcome=None)
        ),
    )
    problems = []
    finality_check._distributed_conflict_v2(adapter, problems)
    assert {"distributed_conflict", "distributed_conflict_reason"}.issubset(problems)

    monkeypatch.undo()
    original_successor = finality_check.commit_decision_successor_v2

    def terminal_fault(*args: Any, **kwargs: Any) -> Any:
        attempt, state = original_successor(*args, **kwargs)
        if state.snapshot.outcome is None:
            return attempt, state
        return (
            SimpleNamespace(
                disposition=GovernanceCommitDispositionV2.INVALID,
                committed_transition=None,
            ),
            SimpleNamespace(
                snapshot=SimpleNamespace(
                    outcome=state.snapshot.outcome,
                    current_step=state.snapshot.current_step - 1,
                )
            ),
        )

    monkeypatch.setattr(
        finality_check,
        "commit_decision_successor_v2",
        terminal_fault,
    )
    problems = []
    finality_check._missing_handle_deadline_v2(adapter, problems)
    assert {
        "missing_handle_deadline",
        "missing_handle_terminal_before_deadline",
    }.issubset(problems)

    monkeypatch.undo()
    captured: dict[str, Any] = {}
    original_vertical = finality_check.certified_decision_vertical_v2

    def capture_vertical(*args: Any, **kwargs: Any) -> Any:
        value = original_vertical(*args, **kwargs)
        captured["state"] = value.state
        return value

    monkeypatch.setattr(
        finality_check,
        "certified_decision_vertical_v2",
        capture_vertical,
    )
    monkeypatch.setattr(
        finality_check,
        "commit_decision_successor_v2",
        lambda *_args, **_kwargs: (object(), captured["state"]),
    )
    problems = []
    finality_check._missing_handle_deadline_v2(adapter, problems)
    assert problems == ["missing_handle_no_terminal"]


def test_commit_gate_restart_and_stream_diagnostic_alarms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _store_adapter()
    monkeypatch.setattr(gate_check, "commit_stop_state_is_current_v2", lambda _: False)
    monkeypatch.setattr(
        gate_check,
        "commit_permission_state_is_current_v2",
        lambda _: False,
    )
    problems: list[str] = []
    gate_check._vertical_restart_exact_retry(adapter, problems)
    assert {
        "stop_restartable_currentness",
        "permission_restartable_currentness",
        "restart_rehydrate",
    }.issubset(problems)

    monkeypatch.undo()
    monkeypatch.setattr(
        gate_check,
        "commit_stop_stream_ref_v2",
        lambda *_args: "authority:wrong-stop",
    )
    problems = []
    gate_check._vertical_restart_exact_retry(adapter, problems)
    assert problems == ["fixed_stream_identity"]

    monkeypatch.undo()
    original_issue = gate_check.issue_permission_v2
    calls = 0

    def retry_fault(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        value = original_issue(*args, **kwargs)
        if calls == 2:
            return SimpleNamespace(
                disposition=GovernanceCommitDispositionV2.INVALID,
                committed_transition=None,
            )
        return value

    monkeypatch.setattr(gate_check, "issue_permission_v2", retry_fault)
    problems = []
    gate_check._vertical_restart_exact_retry(adapter, problems)
    assert problems == ["lost_response_exact_retry_after_restart"]

    monkeypatch.undo()
    original_rehydrate = gate_check.rehydrate_commit_permission_state_v2
    calls = 0

    def restart_rehydrate_fault(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("injected restart rehydrate failure")
        return original_rehydrate(*args, **kwargs)

    monkeypatch.setattr(
        gate_check,
        "rehydrate_commit_permission_state_v2",
        restart_rehydrate_fault,
    )
    problems = []
    gate_check._vertical_restart_exact_retry(adapter, problems)
    assert problems == ["restart_rehydrate"]


def test_commit_gate_race_and_source_diagnostic_alarms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _store_adapter()
    monkeypatch.setattr(
        gate_check,
        "issue_permission_v2",
        lambda *_args, **_kwargs: SimpleNamespace(
            disposition=GovernanceCommitDispositionV2.COMMITTED,
            failure=None,
        ),
    )
    problems: list[str] = []
    gate_check._principal_verification_toctou(adapter, problems)
    assert problems == ["verification_toctou_not_closed"]

    monkeypatch.undo()
    original_resolve = gate_check.resolve_stop_v2
    calls = 0

    def resolve_fault(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        value = original_resolve(*args, **kwargs)
        if calls in {2, 3}:
            return SimpleNamespace(
                disposition=GovernanceCommitDispositionV2.COMMITTED,
                failure=None,
            )
        return value

    monkeypatch.setattr(gate_check, "resolve_stop_v2", resolve_fault)
    problems = []
    gate_check._conflict_and_source_authority(adapter, problems)
    assert {"conflicting_genesis_retry", "portable_source_forgery"}.issubset(problems)


def test_commit_gate_adversarial_helpers_surface_injected_fail_open_regressions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _store_adapter()
    monkeypatch.setattr(
        gate_adversarial,
        "commit_permission_state_is_current_v2",
        lambda _state: True,
    )
    monkeypatch.setattr(
        gate_adversarial,
        "_rehydrate_succeeds",
        lambda *_args, **_kwargs: True,
    )
    problems = gate_adversarial.run_commit_gate_v2_finality_integrity_matrix(adapter)
    assert {
        "finality_not_fail_closed",
        "finality_rehydrate_accepted",
        "inclusion_tamper_not_fail_closed",
        "inclusion_tamper_rehydrate_accepted",
        "position_tamper_not_fail_closed",
        "position_tamper_rehydrate_accepted",
    }.issubset(problems)

    monkeypatch.undo()
    monkeypatch.setattr(
        gate_adversarial,
        "issue_commit_permission_v2",
        lambda *_args, **_kwargs: SimpleNamespace(
            disposition=GovernanceCommitDispositionV2.COMMITTED,
            failure=None,
        ),
    )
    assert gate_adversarial.run_commit_gate_v2_seal_matrix(adapter) == (
        "sealed_new_write_not_denied",
    )


def test_context_helper_dominated_policy_guards_are_observable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        distributed_context,
        "manifest_v2",
        lambda _profile: SimpleNamespace(collective_commit_policy=None),
    )
    with pytest.raises(RuntimeError, match="requires collective commit policy"):
        distributed_context._distributed_manifest_v2("profile")

    monkeypatch.undo()
    context = SimpleNamespace(
        domain=SimpleNamespace(domain_root="domain", scope_ref="scope"),
        manifest=SimpleNamespace(collective_commit_policy=None),
        grant=SimpleNamespace(issuer_ref="issuer"),
        store=object(),
    )
    identity = SimpleNamespace(membership=SimpleNamespace(snapshot=object()))
    initialize = SimpleNamespace(
        observed_epoch=1,
        to_dict=lambda: {},
    )
    monkeypatch.setattr(
        distributed_input,
        "prepare_support_initialize_v2",
        lambda **_kwargs: (initialize, object()),
    )
    monkeypatch.setattr(
        distributed_input,
        "advance_support_state_v2",
        lambda *_args, **_kwargs: SimpleNamespace(
            disposition=GovernanceCommitDispositionV2.COMMITTED
        ),
    )
    monkeypatch.setattr(
        distributed_input,
        "capability_v2",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        distributed_input,
        "open_support_authority_session_v2",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        distributed_input,
        "rehydrate_support_state_v2",
        lambda *_args, **_kwargs: object(),
    )
    with pytest.raises(RuntimeError, match="policy is unavailable"):
        distributed_input._support_v2(
            context,
            identity,
            label="injected",
            claim_root="sha256:" + "0" * 64,
        )

    monkeypatch.undo()
    monkeypatch.setattr(
        gate_context,
        "manifest_v2",
        lambda _profile: SimpleNamespace(collective_commit_policy=None),
    )
    monkeypatch.setattr(
        gate_context,
        "commit_upstreams_v2",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        gate_context,
        "initialize_v2",
        lambda *_args, **_kwargs: (object(), object()),
    )
    monkeypatch.setattr(
        gate_context,
        "advance_support_v2",
        lambda *_args, **_kwargs: SimpleNamespace(
            disposition=GovernanceCommitDispositionV2.COMMITTED
        ),
    )
    monkeypatch.setattr(
        gate_context,
        "support_state_v2",
        lambda *_args, **_kwargs: object(),
    )
    with pytest.raises(RuntimeError, match="policy is missing"):
        gate_context.commit_gate_context_v2(_store_adapter(), "injected-policy")


def test_distributed_checker_verified_restart_and_tamper_alarms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _store_adapter()
    vertical = build_verified_distributed_vertical_v2(adapter, "totality-distributed")
    monkeypatch.setattr(
        distributed_check,
        "verified_finality_v2",
        lambda _vertical: object(),
    )
    problems: list[str] = []
    distributed_check._evaluate_verified_vertical_v2(vertical, problems)
    assert problems == ["verified_finality_handle"]

    monkeypatch.undo()
    monkeypatch.setattr(
        distributed_check,
        "distributed_state_is_current_v2",
        lambda _state: False,
    )
    problems = []
    distributed_check._evaluate_restart_v2(adapter, vertical, problems)
    assert len(problems) == 4
    assert all(item.startswith("restart_rehydrate:") for item in problems)

    monkeypatch.undo()
    monkeypatch.setattr(
        distributed_check,
        "rehydrate_distributed_state_v2",
        lambda *_args, **_kwargs: object(),
    )
    problems = []
    distributed_check._evaluate_portable_tamper_v2(vertical, problems)
    assert problems == ["portable_request_tamper_accepted"]


def test_distributed_checker_conflict_diagnostic_alarms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _store_adapter()
    vertical = build_verified_distributed_vertical_v2(
        adapter,
        "totality-distributed-conflict",
    )
    conflict = freeze_external_witness_conflict_v2(
        vertical,
        "totality-distributed-conflict",
    )
    original_rehydrate = distributed_check.rehydrate_distributed_state_v2

    def restart_fault(*args: Any, **kwargs: Any) -> Any:
        original_rehydrate(*args, **kwargs)
        return SimpleNamespace(snapshot=SimpleNamespace(state=object()))

    monkeypatch.setattr(
        distributed_check,
        "rehydrate_distributed_state_v2",
        restart_fault,
    )

    class _WrongPortable:
        @staticmethod
        def from_dict(_payload: object) -> Any:
            return SimpleNamespace(to_dict=lambda: {"wrong": True})

    monkeypatch.setattr(
        distributed_check,
        "DistributedWitnessConflictObservationV2",
        _WrongPortable,
    )
    monkeypatch.setattr(
        distributed_check,
        "advance_conflict_decision_v2",
        lambda *_args, **_kwargs: SimpleNamespace(
            snapshot=SimpleNamespace(outcome=None)
        ),
    )
    problems: list[str] = []
    distributed_check._evaluate_conflict_vertical_v2(adapter, conflict, problems)
    assert {
        "external_conflict_restart",
        "external_conflict_portable_roundtrip",
        "external_conflict_decision_safety",
    }.issubset(problems)


def test_driver_invocation_checker_internal_alarm_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = invocation_check.ReferenceDriverInvocationStoreConformanceAdapterV2()
    request = invocation_check._request(
        scope_ref=invocation_check.runtime_scope_ref("tenant-totality", "run-1"),
        invocation_id="invocation:totality",
        idempotency_key="retry:totality",
        left=1,
        right=2,
    )
    result = adapter.invoke_v2(request)
    with pytest.raises(AssertionError, match="unregistered"):
        invocation_check._replace_result_binding(result, "unknown", "replacement")

    monkeypatch.setattr(
        invocation_check,
        "_request",
        lambda **_kwargs: request,
    )
    problems: list[str] = []
    invocation_check._exercise_forged_scope(problems)
    assert problems == ["forged_scope_accepted"]

    store = adapter.create_store_v2()
    assert isinstance(store, DriverInvocationStoreV2)
    store.record(request, result)
    problems = []
    invocation_check._exercise_unicode_scalar_boundary(adapter, store, problems)
    assert "unicode_surrogate_request_accepted" in problems


class _Reader:
    def __init__(self, head: GovernanceHeadV2 | None = None, *, raises: bool = False):
        self.head = head
        self.raises = raises

    def load_head_v2(self, _scope_ref: str, _stream_ref: str) -> GovernanceHeadV2:
        if self.raises:
            raise OSError("injected reader failure")
        assert self.head is not None
        return self.head


def test_runtime_integration_recovery_and_dependency_alarms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = ReferenceRuntimeIntegrationAdapterV1()
    request = build_runtime_integration_request_v1(
        "totality-recovery",
        control=RuntimeControlInputV1(recover_after_commit=True),
    )
    result = adapter.execute_transcript_v1(request)
    monkeypatch.setattr(
        runtime_check,
        "recover_baseline_output_result_v2",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("injected recovery failure")
        ),
    )
    problems: list[str] = []
    runtime_check._exercise_governance_recovery(
        adapter,
        request,
        result,
        "totality",
        problems,
    )
    assert problems == ["totality:governance_recovery:OSError"]

    problems = []
    runtime_check._verify_targeted_dependency_delta(
        SimpleNamespace(baseline_request=None),
        SimpleNamespace(governance_result=None),
        _CertificateStateObservationV1(
            snapshot=cast(Any, object()),
            projection_matches=True,
            is_current=True,
        ),
        "totality",
        problems,
    )
    assert problems == []

    stale_request = build_runtime_integration_request_v1(
        "totality-stale-permission",
        control=RuntimeControlInputV1(
            recover_after_commit=True,
            advance_permission_before_recovery=True,
        ),
    )
    stale_result = adapter.execute_transcript_v1(stale_request)
    missing_transition = SimpleNamespace(
        governance_result=SimpleNamespace(
            commit_attempt=SimpleNamespace(committed_transition=None)
        ),
        publication_authorized=False,
        execution_authorized=False,
    )
    problems = []
    runtime_check._verify_targeted_dependency_delta(
        stale_request,
        missing_transition,
        cast(Any, object()),
        "totality",
        problems,
    )
    assert problems == ["totality:stale_permission_head_delta"]

    monkeypatch.setattr(
        runtime_check,
        "_changed_read_set_streams",
        lambda *_args, **_kwargs: set(),
    )
    problems = []
    runtime_check._verify_targeted_dependency_delta(
        stale_request,
        stale_result,
        cast(Any, object()),
        "totality",
        problems,
    )
    assert problems == ["totality:stale_permission_head_delta"]


@pytest.mark.parametrize(
    ("head_mode", "expected"),
    (
        ("raise", None),
        ("same-revision-wrong-root", None),
        ("next-revision-same-root", None),
        ("far-revision", None),
    ),
)
def test_runtime_changed_read_set_rejects_malformed_head_deltas(
    head_mode: str,
    expected: set[str] | None,
) -> None:
    entry = GovernanceReadPreconditionV2(
        stream_ref="authority:runtime:delta",
        expected_revision=2,
        expected_root="sha256:" + "1" * 64,
    )
    if head_mode == "raise":
        reader = _Reader(raises=True)
    else:
        revision, root = {
            "same-revision-wrong-root": (2, "sha256:" + "2" * 64),
            "next-revision-same-root": (3, entry.expected_root),
            "far-revision": (5, "sha256:" + "3" * 64),
        }[head_mode]
        reader = _Reader(
            cast(
                GovernanceHeadV2,
                SimpleNamespace(revision=revision, head_root=root),
            )
        )
    observed = runtime_check._changed_read_set_streams(
        SimpleNamespace(scope=SimpleNamespace(scope_ref="scope:runtime")),
        cast(Any, reader),
        (entry,),
    )
    assert observed == expected


def _certificate_runtime_case(
    label: str,
    terminal: str,
) -> tuple[Any, Any, Any, Any]:
    adapter = ReferenceRuntimeIntegrationAdapterV1()
    request = build_runtime_integration_request_v1(label, terminal=terminal)
    result = adapter.execute_transcript_v1(request)
    states = adapter.open_recovered_certificate_states_v1(
        request.request_root,
        request.scope.scope_ref,
    )
    assert states is not None
    return request, result, states[0], states[1]


def test_runtime_certificate_pair_binding_return_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_request, _current_result, current, _ = _certificate_runtime_case(
        "totality-certificate-current",
        "certificate_current",
    )
    stale_request, _stale_result, stale, successor = _certificate_runtime_case(
        "totality-certificate-stale",
        "certificate_stale",
    )
    assert successor is not None

    assert (
        runtime_check._certificate_pair_observations(
            SimpleNamespace(commit_observation=None),
            current,
            None,
        )
        is None
    )

    monkeypatch.setattr(
        runtime_check,
        "_observe_certificate_state_v1",
        lambda *_args: None,
    )
    assert (
        runtime_check._certificate_pair_observations(
            current_request,
            current,
            None,
        )
        is None
    )

    monkeypatch.undo()
    assert (
        runtime_check._certificate_pair_observations(stale_request, stale, None) is None
    )
    assert (
        runtime_check._certificate_pair_observations(
            current_request,
            current,
            current,
        )
        is None
    )

    original_observe = runtime_check._observe_certificate_state_v1
    calls = 0

    def missing_successor(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            return None
        return original_observe(*args, **kwargs)

    monkeypatch.setattr(
        runtime_check,
        "_observe_certificate_state_v1",
        missing_successor,
    )
    assert (
        runtime_check._certificate_pair_observations(
            stale_request,
            stale,
            successor,
        )
        is None
    )

    calls = 0

    def mismatched_successor(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        value = original_observe(*args, **kwargs)
        if calls == 2:
            assert value is not None
            return replace(value, projection_matches=False)
        return value

    monkeypatch.setattr(
        runtime_check,
        "_observe_certificate_state_v1",
        mismatched_successor,
    )
    assert (
        runtime_check._certificate_pair_observations(
            stale_request,
            stale,
            successor,
        )
        is None
    )


def test_runtime_certificate_currentness_diagnostic_alarms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    problems: list[str] = []
    runtime_check._verify_certificate_currentness(
        cast(Any, object()),
        True,
        _CertificateStateObservationV1(
            snapshot=cast(Any, object()),
            projection_matches=True,
            is_current=True,
        ),
        None,
        SimpleNamespace(publication_authorized=True, execution_authorized=False),
        "stale",
        problems,
    )
    assert problems == [
        "stale:certificate_currentness",
        "stale:certificate_currentness_action_gate",
    ]

    monkeypatch.setattr(
        runtime_check,
        "_current_certificate_action_matches",
        lambda *_args: False,
    )
    problems = []
    runtime_check._verify_certificate_currentness(
        cast(Any, object()),
        False,
        _CertificateStateObservationV1(
            snapshot=cast(Any, object()),
            projection_matches=True,
            is_current=False,
        ),
        _CertificateStateObservationV1(
            snapshot=cast(Any, object()),
            projection_matches=True,
            is_current=True,
        ),
        cast(Any, object()),
        "current",
        problems,
    )
    assert problems == [
        "current:certificate_currentness",
        "current:certificate_currentness_action_gate",
    ]
    monkeypatch.undo()
    assert (
        runtime_check._current_certificate_action_matches(
            SimpleNamespace(baseline_request=None),
            SimpleNamespace(governance_result=None),
        )
        is False
    )
    assert runtime_check.check().ok is True
