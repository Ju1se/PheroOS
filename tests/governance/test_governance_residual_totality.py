from __future__ import annotations

from copy import copy
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import pytest

import pheroos.governance.distributed_commit as distributed_commit
from pheroos.governance import _risk_policy as risk_policy
from pheroos.governance._authority_session_v2 import contracts as session_contracts
from pheroos.governance._commit_evidence_owner_v2 import (
    context as evidence_context,
)
from pheroos.governance._commit_evidence_owner_v2 import (
    contracts as evidence_contracts,
)
from pheroos.governance._commit_evidence_owner_v2 import (
    operations as evidence_operations,
)
from pheroos.governance._commit_evidence_owner_v2 import (
    state_handle as evidence_state_handle,
)
from pheroos.governance._commit_evidence_owner_v2 import (
    state_records as evidence_state_records,
)
from pheroos.governance._commit_evidence_owner_v2 import (
    state_verification as evidence_state_verification,
)
from pheroos.governance._commit_evidence_projection_v2 import (
    common as evidence_common,
)
from pheroos.governance._commit_gate_v2 import common as gate_common
from pheroos.governance._commit_gate_v2 import (
    dependency_source as gate_dependency_source,
)
from pheroos.governance._commit_gate_v2 import (
    operations_common as gate_operations,
)
from pheroos.governance._commit_gate_v2 import (
    source_common as gate_source_common,
)
from pheroos.governance._commit_gate_v2 import (
    state_handle as gate_state_handle,
)
from pheroos.governance._commit_gate_v2 import (
    state_records as gate_state_records,
)
from pheroos.governance._distributed import (
    _state_contract as distributed_state_contract,
)
from pheroos.governance._distributed import epoch as distributed_epoch
from pheroos.governance._distributed import proposal as distributed_proposal
from pheroos.governance._hybrid_replay_v2 import source as hybrid_source
from pheroos.governance.authority_store_v2 import (
    AuthorityDiagnosticCodeV2,
    GovernanceCommitDispositionV2,
    GovernanceFailureStageV2,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import CommitAssurance
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from tests.governance import test_commit_gate_v2_operations as gate_fixture
from tests.governance.test_commit_authority_changed_totality import (
    _evidence_journey,
    _gate_journey,
    _unchecked,
)
from tests.governance.test_commit_risk import policy as legacy_risk_policy
from tests.governance import test_distributed_commit as distributed_fixture
from tests.governance.test_distributed_commit import _public_portable_scenario
from tests.governance.test_distributed_commit_totality import (
    _transition_public_bundle,
)
from tests.governance.test_hybrid_replay_v2_totality import _valid_source


def _root(character: str = "a") -> str:
    return "sha256:" + character * 64


class _ExplodingInstanceCheck(type):
    def __instancecheck__(cls, instance: object) -> bool:
        del cls, instance
        raise RuntimeError("controlled StateReader protocol instance-check failure")


class _ExplodingReaderProtocol(metaclass=_ExplodingInstanceCheck):
    pass


def _forge(value: Any, **changes: object) -> Any:
    forged = copy(value)
    for name, replacement in changes.items():
        object.__setattr__(forged, name, replacement)
    return forged


def test_legacy_risk_policy_exact_type_and_binding_guards_are_total() -> None:
    policy = legacy_risk_policy()
    profile = "pheroos-commit-integrity-v1"
    policy_root = commit_policy_fingerprint(policy, profile=profile)
    valid_bindings: dict[str, object] = {
        "profile": profile,
        "assurance": CommitAssurance.EVIDENCE_BOUND,
        "target": policy.target,
        "commit_policy_root": policy_root,
    }

    with pytest.raises(
        GovernanceError, match="risk policy root requires CollectiveCommitPolicy"
    ):
        risk_policy.risk_policy_root(cast(Any, object()), profile=profile)
    with pytest.raises(GovernanceError, match="profile/assurance mismatch"):
        risk_policy._validate_bound_record(
            SimpleNamespace(
                profile="pheroos-certified-commit-v1",
                assurance=CommitAssurance.EVIDENCE_BOUND,
            ),
            "risk record",
        )
    with pytest.raises(
        GovernanceError, match="risk issuance requires CollectiveCommitPolicy"
    ):
        risk_policy._validate_policy_binding(object(), valid_bindings)
    with pytest.raises(GovernanceError, match="target binding mismatch"):
        risk_policy._validate_policy_binding(
            policy,
            {**valid_bindings, "target": "decision:other"},
        )
    with pytest.raises(GovernanceError, match="assurance binding mismatch"):
        risk_policy._validate_policy_binding(
            policy,
            {**valid_bindings, "assurance": CommitAssurance.CERTIFIED},
        )
    with pytest.raises(GovernanceError, match="policy root binding mismatch"):
        risk_policy._validate_policy_binding(
            policy,
            {**valid_bindings, "commit_policy_root": _root("f")},
        )
    with pytest.raises(
        GovernanceError, match="risk band must use the Protocol ABI record"
    ):
        risk_policy._risk_band_payload(cast(Any, object()))


def test_legacy_distributed_dominated_exact_type_guards_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _public_portable_scenario("residual:replace-state").state
    monkeypatch.setattr(
        distributed_state_contract,
        "replace",
        lambda *_args, **_kwargs: object(),
    )
    with pytest.raises(GovernanceError, match="state replacement changed record type"):
        distributed_state_contract._replace_distributed_state(state, revision=2)

    monkeypatch.setattr(
        distributed_proposal,
        "_validate_distributed_commit_value_payload",
        lambda _value: {"profile": object()},
    )
    with pytest.raises(
        GovernanceError, match="distributed commit value profile is invalid"
    ):
        distributed_proposal.distributed_commit_value_root({})


def test_legacy_distributed_epoch_replay_rejects_corrupt_cached_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _public_portable_scenario("residual:epoch-replay")
    captured: dict[str, object] = {}
    transition = distributed_commit.transition_distributed_commit_epoch

    def recording_transition(*args: object, **kwargs: object) -> object:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return transition(*args, **kwargs)

    monkeypatch.setattr(
        distributed_commit,
        "transition_distributed_commit_epoch",
        recording_transition,
    )
    _transition_public_bundle(bundle)
    monkeypatch.setattr(
        distributed_commit,
        "transition_distributed_commit_epoch",
        transition,
    )

    parent_ref = distributed_commit.distributed_commit_state_fingerprint(bundle.state)
    cursor = object.__getattribute__(bundle.state, "_cursor")
    request_ref, _ = cursor.transitions[parent_ref]
    monkeypatch.setattr(
        distributed_epoch,
        "distributed_commit_state_is_current",
        lambda _state: True,
    )
    replayed, _ = transition(
        *cast(tuple[object, ...], captured["args"]),
        **cast(dict[str, object], captured["kwargs"]),
    )
    assert replayed is cursor.transitions[parent_ref][1]

    cursor.transitions[parent_ref] = (request_ref, object())

    with pytest.raises(
        GovernanceError, match="distributed epoch replay state is invalid"
    ):
        transition(
            *cast(tuple[object, ...], captured["args"]),
            **cast(dict[str, object], captured["kwargs"]),
        )


def test_legacy_distributed_witness_replay_rejects_corrupt_cached_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    record = distributed_fixture.record_witness_verifications

    def recording_witnesses(
        state: object,
        verifications: object,
        *,
        current_step: int,
    ) -> object:
        captured["state"] = state
        captured["verifications"] = verifications
        captured["current_step"] = current_step
        return record(
            cast(Any, state),
            cast(Any, verifications),
            current_step=current_step,
        )

    monkeypatch.setattr(
        distributed_fixture,
        "record_witness_verifications",
        recording_witnesses,
    )
    distributed_fixture._distributed_scenario(monkeypatch)
    monkeypatch.setattr(
        distributed_fixture,
        "record_witness_verifications",
        record,
    )

    parent = cast(Any, captured["state"])
    parent_ref = distributed_commit.distributed_commit_state_fingerprint(parent)
    cursor = object.__getattribute__(parent, "_cursor")
    request_ref, _ = cursor.transitions[parent_ref]
    cursor.transitions[parent_ref] = (request_ref, object())

    with pytest.raises(
        GovernanceError, match="distributed witness replay state is invalid"
    ):
        record(
            parent,
            cast(Any, captured["verifications"]),
            current_step=cast(int, captured["current_step"]),
        )


def test_evidence_context_rejects_deserializer_candidate_elision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journey = _evidence_journey("residual-context")
    detached = _forge(journey.context.manifest, candidates=())
    monkeypatch.setattr(
        evidence_context.ScopedProtocolManifestV2,
        "from_dict",
        classmethod(lambda _cls, _payload: detached),
    )

    with pytest.raises(ValueError, match="target has no declared candidate"):
        evidence_context.commit_evidence_context_v2(
            journey.context.manifest,
            profile=gate_fixture.PROFILE,
            target_ref=gate_fixture.TARGET,
        )


def test_evidence_snapshot_byte_bound_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _evidence_journey("residual-snapshot-bound").request.snapshot
    monkeypatch.setattr(
        evidence_contracts.CommitEvidenceSnapshotV2,
        "canonical_bytes",
        lambda _self: b"x"
        * (evidence_contracts.MAX_COMMIT_EVIDENCE_SNAPSHOT_BYTES_V2 + 1),
    )

    with pytest.raises(ValueError, match="snapshot exceeds its byte bound"):
        replace(snapshot)


def test_evidence_operation_dependency_fault_maps_to_source_binding_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journey = _evidence_journey("residual-source-fault")
    verifier = evidence_operations.verify_commit_evidence_request_source_v2
    call_count = 0

    def invalid_source(*_args: object, **_kwargs: object) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            verifier(*_args, **_kwargs)
            return
        raise ValueError("controlled source verification fault")

    monkeypatch.setattr(
        evidence_operations,
        "verify_commit_evidence_request_source_v2",
        invalid_source,
    )
    attempt = evidence_operations.advance_commit_evidence_state_v2(
        journey.request,
        source=journey.source,
        authority_session=journey.session,
    )

    assert attempt.failure is not None
    assert attempt.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    assert attempt.failure.path == "/source"
    assert attempt.failure.stage is GovernanceFailureStageV2.PRECONDITION
    assert call_count == 2


def test_evidence_invalid_session_store_type_maps_to_exact_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journey = _evidence_journey("residual-session-store")

    def invalid_store(_value: object) -> None:
        raise TypeError("controlled store protocol fault")

    monkeypatch.setattr(evidence_operations, "_require_store", invalid_store)
    session, attempt = evidence_operations._validated_session_or_failure(
        journey.session,
        journey.request,
    )

    assert session is None
    assert attempt is not None and attempt.failure is not None
    assert (
        attempt.failure.code
        is AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH
    )
    assert attempt.failure.path == "/authority_session"
    assert attempt.failure.stage is GovernanceFailureStageV2.VALIDATION


def test_evidence_reader_protocol_exception_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        evidence_state_handle,
        "GovernanceStateReaderV2",
        _ExplodingReaderProtocol,
    )
    with pytest.raises(TypeError, match="commit evidence requires StateReader v2"):
        evidence_state_handle._require_reader(object())


def test_evidence_state_record_non_text_source_root_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journey = _evidence_journey("residual-state-record")
    session = session_contracts._governance_authority_session_state_v2(journey.session)
    binding = evidence_operations._session_binding(session)
    records = evidence_state_records._state_records(
        journey.request,
        binding,
        source_context_root=cast(str, 7),
    )
    monkeypatch.setattr(
        evidence_state_records,
        "_source_context_root_from_request_v2",
        lambda _request: 7,
    )

    with pytest.raises(ValueError, match="source context root is invalid"):
        evidence_state_records._decode_state_records(
            records,
            journey.context.domain,
        )


def test_evidence_committed_receipt_cross_binding_is_rechecked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journey = _evidence_journey("residual-receipt", commit=True)
    view = journey.context.store.load_commit_view_v2(
        journey.request.scope_ref,
        journey.request.stream_ref,
        journey.request.transition_id,
    )
    assert view.committed_transition is not None
    bad_receipt = _unchecked(
        view.committed_transition.receipt,
        revision=journey.request.snapshot.revision + 1,
    )
    bad_committed = _unchecked(
        view.committed_transition,
        receipt=bad_receipt,
    )
    bad_view = _unchecked(view, committed_transition=bad_committed)
    monkeypatch.setattr(
        evidence_state_verification,
        "_canonical_commit_view_v2",
        lambda _value: bad_view,
    )

    with pytest.raises(ValueError, match="committed receipt is mismatched"):
        evidence_state_verification._decode_committed_view(
            view,
            journey.context.domain,
        )


def test_evidence_epoch_transition_takes_policy_rotation_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _evidence_journey("residual-epoch-delta").request.snapshot
    child = _unchecked(
        parent,
        revision=parent.revision + 1,
        parent_revision=parent.revision,
        parent_epoch=parent.epoch,
        parent_transition_id=parent.transition_id,
        parent_snapshot_root=parent.snapshot_root,
        parent_history_root=parent.history_root,
        parent_history_count=parent.history_count,
        current_step=parent.current_step + 1,
        epoch=parent.epoch + 1,
    )
    monkeypatch.setattr(
        evidence_state_verification,
        "_validate_record_delta",
        lambda *_args: None,
    )

    evidence_state_verification._validate_transition_delta(child, parent)


def test_evidence_root_allows_explicit_empty_sentinel() -> None:
    assert (
        evidence_common.require_root_v2(
            "",
            "optional evidence root",
            allow_empty=True,
        )
        == ""
    )


def test_gate_root_helper_rejects_non_string_dependency_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gate_common, "_compute_root", lambda *_args: object())
    with pytest.raises(TypeError, match="root helper returned a non-string"):
        gate_common._root("controlled", {})


def test_gate_dependency_reader_protocol_exception_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = gate_fixture._environment(
        "scope:gate-residual:dependency-reader",
    )
    state = environment.replay_state
    request = object.__getattribute__(state, "_request")
    snapshot = state.snapshot
    monkeypatch.setattr(
        gate_dependency_source,
        "GovernanceStateReaderV2",
        _ExplodingReaderProtocol,
    )

    with pytest.raises(
        TypeError, match="commit gate dependency StateReader v2 is invalid"
    ):
        gate_dependency_source._current_head_from_handle(
            state,
            expected_request_type=type(request),
            expected_revision=snapshot.revision,
            expected_transition_id=snapshot.transition_id,
        )


def test_gate_invalid_session_store_type_maps_to_exact_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journey = _gate_journey("residual-session-store", kind="permission")

    def invalid_store(_value: object) -> None:
        raise TypeError("controlled store protocol fault")

    monkeypatch.setattr(gate_operations, "_require_store", invalid_store)
    session, attempt = gate_operations._validated_session_or_failure(
        journey.session,
        journey.request,
        kind="permission",
    )

    assert session is None
    assert attempt is not None and attempt.failure is not None
    assert (
        attempt.failure.code
        is AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH
    )
    assert attempt.failure.path == "/authority_session"
    assert attempt.failure.stage is GovernanceFailureStageV2.VALIDATION


def test_gate_missing_finality_failure_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journey = _gate_journey("residual-parent-finality", kind="permission")
    successor, _ = gate_fixture._prepare_permission(
        journey.environment,
        label="residual-successor",
        parent=journey.request.snapshot,
    )
    unavailable = SimpleNamespace(
        disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        failure=None,
    )
    monkeypatch.setattr(
        gate_operations,
        "_canonical_commit_view_v2",
        lambda *_args, **_kwargs: unavailable,
    )

    result = gate_operations._load_parent_v2(
        journey.environment.store,
        journey.environment.domain,
        successor,
        kind="permission",
    )

    assert result.failure is not None
    assert (
        result.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
    )
    assert result.failure.path == "/snapshot/parent_transition_id"
    assert result.failure.stage is GovernanceFailureStageV2.FINALITY


def test_gate_context_rejects_deserializer_candidate_elision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = gate_fixture._environment("scope:gate-residual:context")
    request, _ = gate_fixture._prepare_permission(
        environment,
        label="residual-context",
    )
    detached = _forge(environment.manifest, candidates=())
    monkeypatch.setattr(
        gate_source_common.ScopedProtocolManifestV2,
        "from_dict",
        classmethod(lambda _cls, _payload: detached),
    )

    with pytest.raises(ValueError, match="target has no declared candidates"):
        gate_source_common._validated_gate_context_v2(
            domain_root=environment.domain.domain_root,
            scope_ref=environment.domain.scope_ref,
            manifest=environment.manifest,
            profile=gate_fixture.PROFILE,
            run_ref=gate_fixture.RUN_REF,
            target_ref=gate_fixture.TARGET,
            observed_epoch=gate_fixture.GATE_EPOCH,
            request_ref=request.permission_ref,
            current_step=gate_fixture.GATE_STEP,
            mutation_issuer_ref=environment.grant.issuer_ref,
        )


def test_gate_state_handle_preserves_owner_binding_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journey = _gate_journey("residual-owner-error", kind="permission")
    expected = session_contracts.GovernanceAuthorityBindingErrorV2(
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/controlled-owner",
    )

    def owner_failure(*_args: object, **_kwargs: object) -> None:
        raise expected

    monkeypatch.setattr(
        gate_state_handle,
        "_decode_committed_gate_view_v2",
        owner_failure,
    )
    with pytest.raises(session_contracts.GovernanceAuthorityBindingErrorV2) as caught:
        gate_state_handle._load_verified_request_view_v2(
            journey.environment.store,
            journey.environment.domain,
            journey.request,
            expected_receipt_root=None,
            kind="permission",
        )

    assert caught.value is expected
    assert caught.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    assert caught.value.path == "/controlled-owner"


def test_gate_reader_protocol_exception_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gate_state_handle,
        "GovernanceStateReaderV2",
        _ExplodingReaderProtocol,
    )
    with pytest.raises(
        TypeError, match="commit gate rehydration requires StateReader v2"
    ):
        gate_state_handle._require_reader(object())


def test_gate_committed_view_transition_receipt_and_trace_guards_are_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    journey = _gate_journey("residual-records", kind="permission")
    view = journey.environment.store.load_commit_view_v2(
        journey.request.scope_ref,
        journey.request.stream_ref,
        journey.request.transition_id,
    )
    assert view.committed_transition is not None
    committed = view.committed_transition

    monkeypatch.setattr(
        gate_state_records,
        "_canonical_commit_view_v2",
        lambda candidate: candidate,
    )
    no_transition_batch = _unchecked(committed.batch, transition=None)
    no_transition = _unchecked(
        view,
        committed_transition=_unchecked(committed, batch=no_transition_batch),
    )
    with pytest.raises(ValueError, match="committed batch has no transition"):
        gate_state_records._decode_committed_gate_view_v2(
            no_transition,
            journey.environment.domain,
            kind="permission",
            reader=None,
        )

    bad_receipt = _unchecked(
        committed.receipt,
        revision=journey.request.snapshot.revision + 1,
    )
    receipt_mismatch = _unchecked(
        view,
        committed_transition=_unchecked(committed, receipt=bad_receipt),
    )
    with pytest.raises(ValueError, match="committed receipt is mismatched"):
        gate_state_records._decode_committed_gate_view_v2(
            receipt_mismatch,
            journey.environment.domain,
            kind="permission",
            reader=None,
        )

    empty_trace = _unchecked(
        committed.batch.trace_batch,
        _event_snapshots=(),
    )
    trace_mismatch = _unchecked(
        view,
        committed_transition=_unchecked(
            committed,
            batch=_unchecked(committed.batch, trace_batch=empty_trace),
        ),
    )
    with pytest.raises(ValueError, match="committed Trace lineage is mismatched"):
        gate_state_records._decode_committed_gate_view_v2(
            trace_mismatch,
            journey.environment.domain,
            kind="permission",
            reader=None,
        )


def test_hybrid_source_redundant_trace_bindings_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, source = _valid_source("scope:hybrid-replay-residual:trace")
    material = hybrid_source._verified_hybrid_source_material_v2(source)
    binding = material.binding
    first, *remaining = material.step.trace_events
    bad_step = replace(
        material.step,
        trace_events=(
            replace(first, protocol_id="protocol:controlled-mismatch"),
            *remaining,
        ),
    )
    monkeypatch.setattr(
        hybrid_source,
        "_validate_source_step_v2",
        lambda *_args: None,
    )

    with pytest.raises(GovernanceError, match="protocol or target is mismatched"):
        hybrid_source._issue_verified_hybrid_source_step_v2(
            domain_root=binding.domain_root,
            scope_ref=binding.scope_ref,
            run_ref=binding.run_ref,
            observed_epoch=binding.observed_epoch,
            step=bad_step,
            manifest=material.manifest,
            topology=material.topology,
            input_policy_projection=material.input_policy_projection,
            candidate_projection_root=binding.candidate_projection_root,
            base_policy_projection_root=binding.base_policy_projection_root,
            topology_projection_root=binding.topology_projection_root,
            parent_snapshot=material.parent_snapshot,
            current_step=binding.current_step,
        )

    with pytest.raises(GovernanceError, match="trace binding changed"):
        hybrid_source._source_binding(
            step=bad_step,
            manifest=material.manifest,
            topology=material.topology,
            input_policy_projection=material.input_policy_projection,
            parent_snapshot=material.parent_snapshot,
            binding=binding,
        )
