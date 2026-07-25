from __future__ import annotations

from copy import copy
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from pheroos.governance._authority import ledger as legacy_ledger
from pheroos.governance._authority_session_v2 import contracts as session_contracts
from pheroos.governance._authority_session_v2 import operations as session_operations
from pheroos.governance._authority_store_v2_contracts import batch as store_batch
from pheroos.governance._authority_store_v2_contracts import (
    foundation as store_foundation,
)
from pheroos.governance._authority_store_v2_contracts import (
    receipt as store_receipt,
)
from pheroos.governance._authority_store_v2_contracts import (
    results as store_results,
)
from pheroos.governance._baseline_output_v2 import contracts as baseline_contracts
from pheroos.governance._baseline_output_v2 import operations as baseline_operations
from pheroos.governance._commit_evidence_owner_v2 import (
    context as evidence_context,
)
from pheroos.governance._commit_evidence_owner_v2 import (
    context_adapter as evidence_adapter,
)
from pheroos.governance._commit_evidence_owner_v2 import (
    contracts as evidence_contracts,
)
from pheroos.governance._commit_evidence_owner_v2 import (
    dependencies as evidence_dependencies,
)
from pheroos.governance._commit_evidence_owner_v2 import (
    operations as evidence_operations,
)
from pheroos.governance._commit_evidence_owner_v2 import (
    proposals as evidence_proposals,
)
from pheroos.governance._commit_evidence_owner_v2 import (
    qualification as evidence_qualification,
)
from pheroos.governance._commit_evidence_owner_v2 import (
    replay_projection as evidence_replay,
)
from pheroos.governance._commit_evidence_owner_v2 import (
    source as evidence_source,
)
from pheroos.governance._commit_evidence_owner_v2 import (
    source_proof as evidence_source_proof,
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
from pheroos.governance._commit_finality_v2 import (
    MAX_COMMIT_FINALITY_REASONS_V2,
    MAX_COMMIT_FINALITY_TEXT_BYTES_V2,
    CommitFinalityOwnerV2,
    CommitFinalityProjectionV2,
    CommitFinalityStatusV2,
    VerifiedCommitFinalityInputV2,
    _commit_finality_input_material_v2,
    _issue_verified_commit_finality_input_v2,
    _verified_commit_finality_input_material_v2,
    commit_finality_owner_genesis_snapshot_root_v2,
    commit_finality_owner_stream_ref_v2,
)
from pheroos.governance._commit_gate_v2 import common as gate_common
from pheroos.governance._commit_gate_v2 import (
    contract_support as gate_contract_support,
)
from pheroos.governance._commit_gate_v2 import (
    dependency_contracts as gate_dependency_contracts,
)
from pheroos.governance._commit_gate_v2 import (
    dependency_source as gate_dependency_source,
)
from pheroos.governance._commit_gate_v2 import (
    operations_common as gate_operations,
)
from pheroos.governance._commit_gate_v2 import (
    permission_contracts as gate_permission_contracts,
)
from pheroos.governance._commit_gate_v2 import (
    permission_operations as gate_permission_operations,
)
from pheroos.governance._commit_gate_v2 import (
    permission_source as gate_permission_source,
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
from pheroos.governance._commit_gate_v2 import (
    stop_contracts as gate_stop_contracts,
)
from pheroos.governance._commit_gate_v2 import (
    stop_operations as gate_stop_operations,
)
from pheroos.governance._commit_gate_v2 import (
    stop_source as gate_stop_source,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    AuthorityDiagnosticCodeV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceDomainSealV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceTraceBatchV2,
)
from pheroos.protocol.authority_v2 import (
    MAX_AUTHORITY_REVISION_V2,
    GovernanceAuthorityReadSetV2,
    GovernanceReadPreconditionV2,
)
from pheroos.protocol.commit_models import CommitAssurance
from tests.governance import (
    test_commit_evidence_v2_contract_adversarial as evidence_adversarial,
)
from tests.governance import (
    test_commit_evidence_v2_operations as evidence_fixture,
)
from tests.governance import test_commit_gate_v2_operations as gate_fixture
from tests.governance.test_authority_session_v2_contracts import (
    _capability,
    _domain as _session_domain_fixture,
    _grant,
    _retirement_request,
    _session,
    _signal_request,
    _verification,
)
from tests.governance.test_authority_ledger import (
    SCOPE_ALPHA,
    SCOPE_BETA,
    prepared_batch as _legacy_prepared_batch,
)
from tests.governance.test_authority_store_v2_contracts import (
    _committed_fixture,
    _domain,
    _event,
    _seal_fixture,
)
from tests.governance.test_baseline_output_v2_operations import (
    _commit_output as _baseline_commit_output,
    _context as _baseline_context,
    _issue as _baseline_issue,
    _permission as _baseline_permission,
    _request as _baseline_request,
)


def _root(character: str = "a") -> str:
    return "sha256:" + character * 64


def _unchecked(value: Any, **changes: object) -> Any:
    clone = copy(value)
    for field, replacement in changes.items():
        object.__setattr__(clone, field, replacement)
    return clone


def _opaque_clone(value: Any, **changes: object) -> Any:
    clone = object.__new__(type(value))
    for field in type(value).__slots__:
        object.__setattr__(clone, field, object.__getattribute__(value, field))
    for field, replacement in changes.items():
        object.__setattr__(clone, field, replacement)
    return clone


def _projection(
    **changes: object,
) -> CommitFinalityProjectionV2:
    values: dict[str, object] = {
        "owner": CommitFinalityOwnerV2.CERTIFICATE,
        "status": CommitFinalityStatusV2.VERIFIED,
        "stream_ref": "authority:certificate:totality",
        "revision": 1,
        "transition_id": "transition:certificate:totality",
        "snapshot_root": _root("1"),
        "head_root": _root("2"),
        "receipt_root": _root("3"),
        "seal_transition_id": "transition:decision:seal",
        "seal_root": _root("4"),
        "frozen_dependency_root": _root("5"),
        "verified_at_step": 7,
        "reason_codes": ("certificate_verified", "decision_sealed"),
    }
    values.update(changes)
    return CommitFinalityProjectionV2(**values)  # type: ignore[arg-type]


def _finality_input() -> VerifiedCommitFinalityInputV2:
    projection = _projection()
    return _issue_verified_commit_finality_input_v2(
        projection=projection,
        owner_precondition=GovernanceReadPreconditionV2(
            projection.stream_ref,
            projection.revision,
            projection.head_root,
        ),
        owner_receipt_root=projection.receipt_root,
        owner_inclusion_root=_root("6"),
    )


def _baseline_journey(label: str) -> SimpleNamespace:
    context = _baseline_context(scope_ref=f"scope:baseline-totality:{label}")
    request = _baseline_request(
        context,
        request_label=label,
        decision_mode="direct_governance",
    )
    permission_attempt = _baseline_issue(context, request)
    permission = _baseline_permission(context, request)
    result = _baseline_commit_output(context, request)
    state = baseline_operations._project_state(
        baseline_operations._view_or_attempt_state(result.commit_attempt)
    )
    return SimpleNamespace(
        context=context,
        request=request,
        permission_attempt=permission_attempt,
        permission=permission,
        result=result,
        state=state,
    )


def _evidence_journey(label: str, *, commit: bool = False) -> SimpleNamespace:
    context = evidence_fixture._context(
        scope_ref=f"scope:evidence-totality:{label}",
    )
    upstreams = evidence_fixture._commit_upstreams(context)
    claim_root = evidence_fixture._root(f"claim:{label}")
    attestations = evidence_fixture._attestations(claim_root=claim_root)
    replay_request, replay_state = evidence_fixture._commit_replay(
        context,
        attestations,
    )
    request, source = evidence_fixture._prepare_evidence(
        context,
        upstreams,
        replay_state,
        attestations,
        advance=f"advance:evidence:totality:{label}",
    )
    session = evidence_operations.open_commit_evidence_authority_session_v2(
        evidence_fixture._capability(
            context,
            context.grant,
            request.observed_epoch,
        ),
        request,
    )
    attempt = None
    state = None
    if commit:
        attempt = evidence_operations.advance_commit_evidence_state_v2(
            request,
            source=source,
            authority_session=session,
        )
        assert attempt.committed_transition is not None
        state = evidence_operations.rehydrate_commit_evidence_state_v2(
            request.to_dict(),
            domain=context.domain,
            state_reader=context.store,
        )
    return SimpleNamespace(
        context=context,
        upstreams=upstreams,
        claim_root=claim_root,
        attestations=attestations,
        replay_request=replay_request,
        replay_state=replay_state,
        request=request,
        source=source,
        session=session,
        attempt=attempt,
        state=state,
    )


def _gate_journey(label: str, *, kind: str) -> SimpleNamespace:
    environment = gate_fixture._environment(
        f"scope:gate-totality:{kind}:{label}",
    )
    if kind == "stop":
        request, source = gate_fixture._prepare_stop(
            environment,
            label=label,
        )
        session = gate_stop_operations.open_commit_stop_authority_session_v2(
            environment.capability(),
            request,
        )
        attempt = gate_stop_operations.resolve_commit_stop_v2(
            request,
            source=source,
            authority_session=session,
        )
        state = gate_stop_operations.rehydrate_commit_stop_state_v2(
            request.to_dict(),
            domain=environment.domain,
            state_reader=environment.store,
        )
    else:
        request, source = gate_fixture._prepare_permission(
            environment,
            label=label,
        )
        session = (
            gate_permission_operations.open_commit_permission_authority_session_v2(
                environment.capability(),
                request,
            )
        )
        attempt = gate_permission_operations.issue_commit_permission_v2(
            request,
            source=source,
            authority_session=session,
        )
        state = gate_permission_operations.rehydrate_commit_permission_state_v2(
            request.to_dict(),
            domain=environment.domain,
            state_reader=environment.store,
        )
    assert attempt.committed_transition is not None
    return SimpleNamespace(
        environment=environment,
        request=request,
        source=source,
        session=session,
        attempt=attempt,
        state=state,
    )


def _failure(
    code: AuthorityDiagnosticCodeV2 = (
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    ),
) -> GovernanceFailureV2:
    return GovernanceFailureV2(
        code=code,
        path="/read_set",
        stage=GovernanceFailureStageV2.PRECONDITION,
    )


class _StaticStoreV2:
    state_store_version = GOVERNANCE_STATE_STORE_VERSION_V2

    def __init__(
        self,
        *,
        state: object | None = None,
        head: object | None = None,
    ) -> None:
        self.state = state
        self.head = head

    def load_head_v2(self, _scope_ref: str, _stream_ref: str) -> Any:
        if self.head is None:
            raise KeyError(_stream_ref)
        return self.head

    def load_state_v2(self, _scope_ref: str, _stream_ref: str) -> Any:
        if self.state is None:
            raise KeyError(_stream_ref)
        return self.state

    def load_commit_view_v2(
        self,
        _scope_ref: str,
        _stream_ref: str,
        _transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> Any:
        del expected_receipt_root
        raise KeyError(_transition_id)

    def atomic_commit_v2(self, _batch: object) -> Any:
        raise AssertionError("read-only totality fixture")


class _DelegatingStoreV2:
    def __init__(
        self,
        delegate: Any,
        *,
        state_overrides: dict[str, object] | None = None,
    ) -> None:
        self.delegate = delegate
        self.state_overrides = state_overrides or {}

    @property
    def state_store_version(self) -> str:
        return self.delegate.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> Any:
        return self.delegate.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(self, scope_ref: str, stream_ref: str) -> Any:
        if stream_ref in self.state_overrides:
            return self.state_overrides[stream_ref]
        return self.delegate.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> Any:
        return self.delegate.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    def atomic_commit_v2(self, batch: object) -> Any:
        return self.delegate.atomic_commit_v2(batch)


def test_commit_finality_owner_and_projection_fail_closed_totality() -> None:
    with pytest.raises(TypeError, match="stream owner"):
        commit_finality_owner_stream_ref_v2(  # type: ignore[arg-type]
            "certificate",
            "scope:a",
            "protocol:a",
            "run:a",
            "target:a",
        )
    with pytest.raises(TypeError, match="genesis owner"):
        commit_finality_owner_genesis_snapshot_root_v2("certificate")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="schema"):
        _projection(schema="unsupported")
    with pytest.raises(TypeError, match="owner"):
        _projection(owner="certificate")
    with pytest.raises(TypeError, match="status"):
        _projection(status="verified")
    with pytest.raises(ValueError, match="projection_root"):
        _projection(projection_root=_root("9"))


def test_commit_finality_projection_wire_is_exact_and_canonical() -> None:
    projection = _projection()
    wire = projection.to_dict()
    with pytest.raises(TypeError, match="exact object"):
        CommitFinalityProjectionV2.from_dict(tuple(wire.items()))
    with pytest.raises(ValueError, match="fields"):
        CommitFinalityProjectionV2.from_dict({**wire, "extension": True})
    with pytest.raises(ValueError, match="enum"):
        CommitFinalityProjectionV2.from_dict({**wire, "owner": "unknown"})
    with pytest.raises(TypeError, match="reasons"):
        CommitFinalityProjectionV2.from_dict(
            {**wire, "reason_codes": tuple(wire["reason_codes"])}
        )
    reversed_reasons = list(reversed(wire["reason_codes"]))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="canonical wire"):
        CommitFinalityProjectionV2.from_dict({**wire, "reason_codes": reversed_reasons})


def test_commit_finality_opaque_input_rejects_forgery_and_mutation() -> None:
    handle = _finality_input()
    material = _verified_commit_finality_input_material_v2(handle)
    assert copy(handle) is handle
    assert material.projection == _projection()
    with pytest.raises(AttributeError, match="immutable"):
        handle.extra = True  # type: ignore[attr-defined]
    with pytest.raises(TypeError, match="not portable"):
        handle.__reduce__()
    with pytest.raises(TypeError, match="not portable"):
        handle.__getstate__()

    bad_token = _finality_input()
    object.__setattr__(bad_token, "_token", object())
    with pytest.raises(TypeError, match="token"):
        _verified_commit_finality_input_material_v2(bad_token)

    bad_anchor = _finality_input()
    object.__setattr__(bad_anchor, "_anchor_root", _root("f"))
    with pytest.raises(ValueError, match="anchor"):
        _verified_commit_finality_input_material_v2(bad_anchor)


def test_commit_finality_material_and_primitives_are_total() -> None:
    projection = _projection()
    precondition = GovernanceReadPreconditionV2(
        projection.stream_ref,
        projection.revision,
        projection.head_root,
    )
    with pytest.raises(TypeError, match="projection"):
        _commit_finality_input_material_v2(
            projection=object(),
            owner_precondition=precondition,
            owner_receipt_root=projection.receipt_root,
            owner_inclusion_root=_root("6"),
        )
    with pytest.raises(TypeError, match="precondition"):
        _commit_finality_input_material_v2(
            projection=projection,
            owner_precondition=object(),
            owner_receipt_root=projection.receipt_root,
            owner_inclusion_root=_root("6"),
        )
    with pytest.raises(TypeError, match="non-empty string"):
        _projection(stream_ref=1)
    with pytest.raises(ValueError, match="U\\+0000"):
        _projection(stream_ref="stream:\x00bad")
    with pytest.raises(ValueError, match="UTF-8"):
        _projection(stream_ref="stream:\ud800")
    with pytest.raises(ValueError, match="text bound"):
        _projection(stream_ref="x" * (MAX_COMMIT_FINALITY_TEXT_BYTES_V2 + 1))
    with pytest.raises(ValueError, match="sha256"):
        _projection(snapshot_root="not-a-root")
    with pytest.raises(ValueError, match="integer bound"):
        _projection(revision=True)
    with pytest.raises(TypeError, match="bounded array"):
        _projection(reason_codes={"not": "a sequence"})
    with pytest.raises(TypeError, match="bounded array"):
        _projection(reason_codes=("x",) * (MAX_COMMIT_FINALITY_REASONS_V2 + 1))
    with pytest.raises(ValueError, match="unique"):
        _projection(reason_codes=("duplicate", "duplicate"))


def test_authority_session_portable_records_cover_remaining_methods() -> None:
    verification = _verification(_grant())
    request = _signal_request()
    retirement = _retirement_request()
    assert verification.root() == verification.verification_root
    assert request.root() == request.request_root
    assert retirement.root() == retirement.request_root
    assert retirement.canonical_bytes()


def test_authority_session_opaque_properties_and_protocol_methods_are_total() -> None:
    capability, _, _ = _capability()
    authority_session = _session(capability=capability)
    assert capability.grant_binding_ref == _grant().grant_binding_ref
    assert capability.target_refs == ("target:a", "target:b")
    assert capability.action_refs == ("action:publish",)
    assert capability.issued_epoch == 1
    assert capability.not_before_epoch == 2
    assert capability.expires_at_epoch == 9
    assert capability.revocation_generation == 0
    with pytest.raises(AttributeError, match="immutable"):
        capability.extra = True  # type: ignore[attr-defined]
    with pytest.raises(TypeError, match="not portable"):
        capability.__getstate__()
    with pytest.raises(AttributeError, match="immutable"):
        authority_session.extra = True  # type: ignore[attr-defined]
    with pytest.raises(TypeError, match="not portable"):
        authority_session.__getstate__()


def test_authority_session_factories_reject_wrong_exact_types() -> None:
    domain = _session_domain_fixture()
    grant = _grant(domain)
    with pytest.raises(TypeError, match="store"):
        session_contracts._make_governance_issuer_capability_v2(
            store=None,
            domain=domain,
            grant=grant,
            run_ref="run:a",
            observed_epoch=5,
        )
    with pytest.raises(TypeError, match="AuthorityDomainV2"):
        session_contracts._make_governance_issuer_capability_v2(
            store=object(),
            domain=object(),  # type: ignore[arg-type]
            grant=grant,
            run_ref="run:a",
            observed_epoch=5,
        )
    with pytest.raises(TypeError, match="GovernanceIssuerGrantV2"):
        session_contracts._make_governance_issuer_capability_v2(
            store=object(),
            domain=domain,
            grant=object(),  # type: ignore[arg-type]
            run_ref="run:a",
            observed_epoch=5,
        )
    authenticated = _session_domain_fixture(
        profile="pheroos-scoped-authority-authenticated-v2"
    )
    authenticated_grant = _grant(authenticated)
    with pytest.raises(TypeError, match="verification type"):
        session_contracts._make_governance_issuer_capability_v2(
            store=object(),
            domain=authenticated,
            grant=authenticated_grant,
            run_ref="run:a",
            observed_epoch=5,
            verification=object(),  # type: ignore[arg-type]
        )
    capability, _, _ = _capability()
    with pytest.raises(TypeError, match="operation type"):
        session_contracts._make_governance_authority_session_v2(
            capability=capability,
            request_ref="request:a",
            request_root=_root("a"),
            operation="verify_signal",  # type: ignore[arg-type]
            run_ref="run:alpha",
            observed_epoch=5,
            grant_expected_revision=1,
            grant_expected_root=_root("b"),
            lifecycle_expected_revision=0,
            lifecycle_expected_root=_root("c"),
            target_refs=("target:a",),
            action_refs=(),
        )


def test_authority_session_tokens_fail_closed_before_snapshot_use() -> None:
    capability, _, _ = _capability()
    forged_capability = object.__new__(session_contracts.GovernanceIssuerCapabilityV2)
    object.__setattr__(
        forged_capability,
        "_state",
        object.__getattribute__(capability, "_state"),
    )
    object.__setattr__(forged_capability, "_token", object())
    with pytest.raises(
        session_contracts.GovernanceAuthorityBindingErrorV2,
        match="authority_session_required",
    ):
        session_contracts._governance_issuer_capability_state_v2(forged_capability)

    authority_session = _session(capability=capability)
    forged_session = object.__new__(session_contracts.GovernanceAuthoritySessionV2)
    object.__setattr__(
        forged_session,
        "_state",
        object.__getattribute__(authority_session, "_state"),
    )
    object.__setattr__(forged_session, "_token", object())
    with pytest.raises(
        session_contracts.GovernanceAuthorityBindingErrorV2,
        match="authority_session_required",
    ):
        session_contracts._governance_authority_session_state_v2(forged_session)


def test_authority_session_contract_primitives_are_strict() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        session_contracts._require_exact_version("old", "current", "schema")
    with pytest.raises(ValueError, match="UTF-8"):
        session_contracts._require_text("\ud800", "text")
    with pytest.raises(TypeError, match="invalid operation"):
        session_contracts._require_operation_tuple(("verify_signal",))
    with pytest.raises(TypeError, match="only text"):
        session_contracts._require_ref_tuple((1,), "refs")
    with pytest.raises(TypeError, match="array"):
        session_contracts._operations_from_wire(())
    with pytest.raises(TypeError, match="array"):
        session_contracts._refs_from_wire((), "refs")
    with pytest.raises(ValueError, match="JSON pointer"):
        session_contracts._require_json_pointer("relative")
    with pytest.raises(ValueError, match="NFC"):
        session_contracts._require_json_pointer("/e\u0301")
    with pytest.raises(ValueError, match="UTF-8"):
        session_contracts._require_json_pointer("/\ud800")
    assert session_contracts._require_json_pointer("/a~0b~1c") == "/a~0b~1c"


def test_authority_session_operation_pure_failures_are_explicit() -> None:
    capability = session_contracts._governance_issuer_capability_state_v2(
        _capability()[0]
    )
    with pytest.raises(ValueError, match="profile"):
        session_operations._validate_grant_state_verification(
            {"profile": "unsupported", "verification": None},
            "unsupported",
            capability.grant,
        )
    assert (
        session_operations._scoped_manifest_authority_matches_domain_v2(
            object(),
            object(),
        )
        is False
    )
    malformed_manifest = object.__new__(session_operations.ScopedProtocolManifestV2)
    assert (
        session_operations._scoped_manifest_authority_matches_domain_v2(
            malformed_manifest,
            _session_domain_fixture(),
        )
        is False
    )


def test_authority_session_current_grant_and_lifecycle_defenses_are_total() -> None:
    domain = _session_domain_fixture()
    grant = _grant(domain)
    store = _StaticStoreV2()
    capability = session_contracts._make_governance_issuer_capability_v2(
        store=store,
        domain=domain,
        grant=grant,
        run_ref="run:alpha",
        observed_epoch=5,
    )
    capability_state = session_contracts._governance_issuer_capability_state_v2(
        capability
    )
    durable = session_operations._active_grant_state(
        domain,
        capability_state.grant,
        None,
        5,
    )
    store.state = durable
    session = SimpleNamespace(
        store=store,
        capability=capability,
        scope_ref=domain.scope_ref,
        domain_root=domain.domain_root,
        grant_ref=grant.grant_ref,
        grant_root=grant.grant_root,
        grant_binding_ref=grant.grant_binding_ref,
        observed_epoch=5,
    )
    object.__setattr__(capability_state.grant, "issuer_ref", "issuer:tampered")
    snapshot = list(capability_state._snapshot)
    snapshot[4] = capability_state.grant.canonical_bytes()
    object.__setattr__(capability_state, "_snapshot", tuple(snapshot))
    assert session_operations._current_session_grant_failure(session) == (
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/grant_ref",
    )

    short_grant = _grant(domain)
    object.__setattr__(short_grant, "expires_at_epoch", 4)
    object.__setattr__(short_grant, "grant_root", "")
    short_grant = session_contracts.GovernanceIssuerGrantV2.from_dict(
        {
            **short_grant.to_dict(),
            "grant_root": "",
        }
    )
    short_store = _StaticStoreV2()
    short_capability = session_contracts._make_governance_issuer_capability_v2(
        store=short_store,
        domain=domain,
        grant=short_grant,
        run_ref="run:alpha",
        observed_epoch=2,
    )
    short_state = session_contracts._governance_issuer_capability_state_v2(
        short_capability
    )
    short_store.state = session_operations._active_grant_state(
        domain,
        short_state.grant,
        None,
        2,
    )
    expired_session = SimpleNamespace(
        store=short_store,
        capability=short_capability,
        scope_ref=domain.scope_ref,
        grant_ref=short_grant.grant_ref,
        grant_root=short_grant.grant_root,
        grant_binding_ref=short_grant.grant_binding_ref,
        observed_epoch=5,
    )
    assert session_operations._current_session_grant_failure(expired_session) == (
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED,
        "/observed_epoch",
    )

    lifecycle = GovernanceHeadV2.genesis(
        domain,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    )
    stale_session = SimpleNamespace(
        store=_StaticStoreV2(head=lifecycle),
        scope_ref=domain.scope_ref,
        domain_root=domain.domain_root,
        lifecycle_expected_revision=0,
        lifecycle_expected_root=_root("9"),
    )
    assert session_operations._current_session_lifecycle_failure(stale_session) == (
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        "/lifecycle_expected_root",
    )
    with pytest.raises(
        session_contracts.GovernanceAuthorityBindingErrorV2,
        match="authority_binding_mismatch",
    ):
        session_operations._session_domain(
            SimpleNamespace(
                capability=short_capability,
                store=object(),
                domain_root=domain.domain_root,
                scope_ref=domain.scope_ref,
            )
        )


def test_store_foundation_pure_contract_helpers_are_total() -> None:
    with pytest.raises(NotImplementedError):
        store_foundation._CanonicalRootRecordV2().to_dict()
    box = SimpleNamespace(value=_root("1"))
    with pytest.raises(ValueError, match="mismatched"):
        store_foundation._install_optional_exact(
            box,
            "value",
            box.value,
            _root("2"),
            "nested root",
        )
    value = SimpleNamespace(
        domain_root=_root("1"),
        scope_ref="scope:a",
        stream_ref="stream:a",
        transition_id="transition:a",
    )
    mismatches = (
        {"domain_root": _root("2")},
        {"scope_ref": "scope:b"},
        {"stream_ref": "stream:b"},
    )
    for changes in mismatches:
        nested = SimpleNamespace(**{**vars(value), **changes})
        with pytest.raises(ValueError, match="mismatched"):
            store_foundation._validate_nested_binding(
                nested,
                domain_root=value.domain_root,
                scope_ref=value.scope_ref,
                stream_ref=value.stream_ref,
                transition_id=value.transition_id,
                label="nested",
            )


def test_store_foundation_text_pointer_and_json_helpers_are_total() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        store_foundation._require_exact_version("old", "current", "version")
    with pytest.raises(ValueError, match="NFC"):
        store_foundation._require_text("e\u0301", "text")
    with pytest.raises(ValueError, match="JSON pointer"):
        store_foundation._require_json_pointer("relative")
    with pytest.raises(ValueError, match="NFC"):
        store_foundation._require_json_pointer("/e\u0301")
    assert store_foundation._require_json_pointer("/a~0b~1c") == "/a~0b~1c"
    with pytest.raises(TypeError, match="exact JSON object"):
        store_foundation._exact_object((), frozenset(), "record")
    with pytest.raises(TypeError, match="unsupported value"):
        store_foundation._freeze_json(object(), "state")
    with pytest.raises(ValueError, match="NFC"):
        store_foundation._freeze_json_text("e\u0301", "state")
    with pytest.raises(ValueError, match="UTF-8"):
        store_foundation._freeze_json_text("\ud800", "state")
    with pytest.raises(ValueError, match="JSON-safe range"):
        store_foundation._freeze_json_integer(2**53, "state")
    with pytest.raises(TypeError, match="keys must be strings"):
        store_foundation._freeze_json_object({1: "value"}, "state")


@pytest.mark.parametrize(
    ("function", "expected"),
    (
        (store_foundation._diagnostic_from_wire, "diagnostic code"),
        (store_foundation._failure_stage_from_wire, "failure stage"),
        (store_foundation._disposition_from_wire, "commit disposition"),
        (store_foundation._position_from_wire, "commit position"),
    ),
)
def test_store_enum_wire_helpers_reject_non_text_and_unknown(
    function: Any,
    expected: str,
) -> None:
    with pytest.raises(TypeError, match=expected):
        function(1)
    with pytest.raises(ValueError, match="unsupported"):
        function("unknown")


def test_store_trace_and_seal_contract_edges_are_typed() -> None:
    domain = _domain()
    with pytest.raises(TypeError, match="events must be a sequence"):
        GovernanceTraceBatchV2(
            domain_root=domain.domain_root,
            scope_ref=domain.scope_ref,
            stream_ref="authority:decision",
            transition_id="transition:a",
            events="not-events",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="requires from 1"):
        GovernanceTraceBatchV2(
            domain_root=domain.domain_root,
            scope_ref=domain.scope_ref,
            stream_ref="authority:decision",
            transition_id="transition:a",
            events=(),
        )
    trace_wire = _committed_fixture()[3].to_dict()
    with pytest.raises(TypeError, match="wire field"):
        GovernanceTraceBatchV2.from_dict(
            {**trace_wire, "events": tuple(trace_wire["events"])}
        )

    lifecycle = GovernanceHeadV2.genesis(
        domain,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    )
    with pytest.raises(ValueError, match="genesis"):
        GovernanceDomainSealV2(
            domain_root=domain.domain_root,
            scope_ref=domain.scope_ref,
            transition_id="genesis",
            expected_revision=lifecycle.revision,
            expected_root=lifecycle.head_root,
            final_heads=(),
        )
    with pytest.raises(TypeError, match="tuple"):
        GovernanceDomainSealV2(
            domain_root=domain.domain_root,
            scope_ref=domain.scope_ref,
            transition_id="transition:seal",
            expected_revision=lifecycle.revision,
            expected_root=lifecycle.head_root,
            final_heads=[],  # type: ignore[arg-type]
        )
    seal = _seal_fixture()[0]
    seal_wire = seal.to_dict()
    with pytest.raises(TypeError, match="array"):
        GovernanceDomainSealV2.from_dict(
            {**seal_wire, "final_heads": tuple(seal_wire["final_heads"])}
        )


def test_store_seal_final_heads_are_bounded_unique_and_exclude_lifecycle() -> None:
    domain = _domain()
    lifecycle = GovernanceHeadV2.genesis(
        domain,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    )
    base = {
        "domain_root": domain.domain_root,
        "scope_ref": domain.scope_ref,
        "transition_id": "transition:seal",
        "expected_revision": lifecycle.revision,
        "expected_root": lifecycle.head_root,
    }
    with pytest.raises(ValueError, match="at most 127"):
        GovernanceDomainSealV2(
            **base,
            final_heads=tuple(
                {
                    "stream_ref": f"stream:{index:03d}",
                    "revision": 0,
                    "head_root": _root("0"),
                }
                for index in range(128)
            ),
        )
    repeated = {
        "stream_ref": "stream:a",
        "revision": 0,
        "head_root": _root("0"),
    }
    with pytest.raises(ValueError, match="unique"):
        GovernanceDomainSealV2(**base, final_heads=(repeated, repeated))
    lifecycle_item = {
        "stream_ref": GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        "revision": 0,
        "head_root": lifecycle.head_root,
    }
    with pytest.raises(ValueError, match="exclude lifecycle"):
        GovernanceDomainSealV2(**base, final_heads=(lifecycle_item,))


def test_store_domain_and_transition_reserved_identity_edges() -> None:
    domain, head, transition, *_ = _committed_fixture()
    with pytest.raises(ValueError, match="non-genesis"):
        GovernanceHeadV2(
            domain_root=head.domain_root,
            scope_ref=head.scope_ref,
            stream_ref=head.stream_ref,
            revision=1,
            parent_root=head.parent_root,
            state_root=head.state_root,
            transition_id="genesis",
            batch_root=head.batch_root,
        )
    with pytest.raises(TypeError, match="AuthorityDomainV2"):
        GovernanceHeadV2.genesis(object(), "stream:a")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="genesis"):
        replace(transition, transition_id="genesis", transition_root="")
    assert domain.scope_ref == head.scope_ref


def test_store_batch_validation_methods_cover_defensive_closed_union() -> None:
    *_, batch, _, _, _, _ = _committed_fixture()
    object.__setattr__(batch, "transition", None)
    with pytest.raises(TypeError, match="prepared transition"):
        batch._validate_transition_kind()

    *_, transition_batch, _, _, _, _ = _committed_fixture()
    object.__setattr__(transition_batch, "seal", _seal_fixture()[0])
    with pytest.raises(ValueError, match="cannot carry"):
        transition_batch._validate_transition_kind()

    *_, lifecycle_batch, _, _, _, _ = _committed_fixture()
    object.__setattr__(
        lifecycle_batch,
        "stream_ref",
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    )
    with pytest.raises(ValueError, match="lifecycle"):
        lifecycle_batch._validate_transition_kind()

    seal, seal_batch = _seal_fixture()
    object.__setattr__(seal_batch, "seal", None)
    with pytest.raises(TypeError, match="domain seal"):
        seal_batch._validate_seal_kind()

    _, mixed_batch = _seal_fixture()
    object.__setattr__(mixed_batch, "transition", _committed_fixture()[2])
    with pytest.raises(ValueError, match="cannot carry"):
        mixed_batch._validate_seal_kind()

    _, wrong_stream = _seal_fixture()
    object.__setattr__(wrong_stream, "stream_ref", "authority:decision")
    with pytest.raises(ValueError, match="lifecycle"):
        wrong_stream._validate_seal_kind()
    assert seal.seal_root


def test_store_batch_binding_and_seal_semantic_mismatches_are_explicit() -> None:
    batch = _committed_fixture()[4]
    with pytest.raises(ValueError, match="genesis"):
        replace(batch, transition_id="genesis", batch_root="")
    with pytest.raises(ValueError, match="crosses authority scope"):
        replace(batch, scope_ref="scope:other", batch_root="")

    read_set_mismatch = _committed_fixture()[4]
    assert read_set_mismatch.transition is not None
    object.__setattr__(
        read_set_mismatch.transition,
        "read_set_root",
        _root("9"),
    )
    with pytest.raises(ValueError, match="read_set_root"):
        read_set_mismatch._validate_transition_kind()

    absent_target = _committed_fixture()[4]
    unrelated_read_set = GovernanceAuthorityReadSetV2(
        entries=(
            GovernanceReadPreconditionV2(
                "authority:unrelated",
                0,
                _root("0"),
            ),
        )
    )
    object.__setattr__(absent_target, "read_set", unrelated_read_set)
    object.__setattr__(absent_target, "read_set_root", unrelated_read_set.root())
    assert absent_target.transition is not None
    object.__setattr__(
        absent_target.transition,
        "read_set_root",
        unrelated_read_set.root(),
    )
    with pytest.raises(ValueError, match="target precondition"):
        absent_target._validate_transition_kind()

    _, lifecycle_mismatch = _seal_fixture()
    assert lifecycle_mismatch.seal is not None
    object.__setattr__(lifecycle_mismatch.seal, "expected_revision", 1)
    with pytest.raises(ValueError, match="lifecycle precondition"):
        lifecycle_mismatch._validate_seal_kind()

    _, final_heads_mismatch = _seal_fixture()
    assert final_heads_mismatch.seal is not None
    object.__setattr__(final_heads_mismatch.seal, "final_heads", ())
    with pytest.raises(ValueError, match="exactly cover"):
        final_heads_mismatch._validate_seal_kind()

    _, trace_mismatch = _seal_fixture()
    assert trace_mismatch.seal is not None
    trace = GovernanceTraceBatchV2(
        domain_root=trace_mismatch.domain_root,
        scope_ref=trace_mismatch.scope_ref,
        stream_ref=trace_mismatch.stream_ref,
        transition_id=trace_mismatch.transition_id,
        events=(
            _event(
                stream_ref=trace_mismatch.stream_ref,
                transition_id=trace_mismatch.transition_id,
            ),
        ),
    )
    object.__setattr__(trace_mismatch, "trace_batch", trace)
    with pytest.raises(ValueError, match="seal_root"):
        trace_mismatch._validate_seal_kind()


def test_store_batch_nested_and_wire_types_fail_closed() -> None:
    batch = _committed_fixture()[4]
    batch_wire = batch.to_dict()
    with pytest.raises(TypeError, match="transition must be"):
        GovernanceCommitBatchV2.from_dict({**batch_wire, "transition": ()})
    seal_wire = _seal_fixture()[1].to_dict()
    with pytest.raises(TypeError, match="seal must be"):
        GovernanceCommitBatchV2.from_dict({**seal_wire, "seal": ()})

    attributes = (
        ("domain", object(), "domain"),
        ("read_set", object(), "read_set"),
        ("trace_batch", object(), "trace_batch"),
        ("transition", object(), "transition"),
    )
    for attribute, invalid, match in attributes:
        candidate = _committed_fixture()[4]
        object.__setattr__(candidate, attribute, invalid)
        with pytest.raises(TypeError, match=match):
            store_batch._snapshot_commit_batch_nested(candidate)

    seal_candidate = _seal_fixture()[1]
    object.__setattr__(seal_candidate, "seal", object())
    with pytest.raises(TypeError, match="seal"):
        store_batch._snapshot_commit_batch_nested(seal_candidate)
    with pytest.raises(TypeError, match="canonical TraceEvent"):
        store_batch._trace_event_snapshot(
            object(),
            domain_root=_root("1"),
            scope_ref="scope:a",
            stream_ref="stream:a",
            transition_id="transition:a",
        )
    with pytest.raises(TypeError, match="lineage"):
        store_batch._trace_event_from_wire(
            {
                "event_type": "event",
                "protocol_id": "protocol",
                "target": "target",
                "reason": "reason",
                "lineage": (),
            }
        )


def test_store_receipt_and_position_basic_invalid_states_are_explicit() -> None:
    _, _, _, _, _, receipt, inclusion, _, position = _committed_fixture()
    with pytest.raises(ValueError, match="genesis"):
        replace(receipt, transition_id="genesis", receipt_root="")
    with pytest.raises(ValueError, match="positive"):
        replace(receipt, revision=0, receipt_root="")
    with pytest.raises(ValueError, match="positive"):
        replace(inclusion, revision=0, inclusion_root="")
    with pytest.raises(ValueError, match="committed revision"):
        replace(
            position,
            observed_revision=0,
            observation_root="",
        )
    with pytest.raises(TypeError, match="position is invalid"):
        replace(position, position="current", observation_root="")
    with pytest.raises(ValueError, match="only a sealed"):
        replace(position, seal_root=_root("9"), observation_root="")


def test_store_committed_nested_types_and_cross_artifact_checks_are_total() -> None:
    *_, batch, receipt, inclusion, committed, _ = _committed_fixture()
    for attribute, match in (
        ("batch", "batch"),
        ("receipt", "receipt"),
        ("inclusion_proof", "inclusion"),
    ):
        with pytest.raises(TypeError, match=match):
            replace(committed, **{attribute: object()})

    bad_receipt = replace(receipt, trace_root=_root("9"), receipt_root="")
    with pytest.raises(ValueError, match="exact batch"):
        store_receipt._validate_committed_artifacts(batch, bad_receipt, inclusion)
    bad_inclusion = replace(inclusion, receipt_root=_root("9"), inclusion_root="")
    with pytest.raises(ValueError, match="commit receipt"):
        store_receipt._validate_committed_artifacts(batch, receipt, bad_inclusion)
    assert committed.committed_transition_root

    overflow = _committed_fixture()
    overflow_batch, overflow_receipt, overflow_inclusion = overflow[4:7]
    assert overflow_batch.transition is not None
    object.__setattr__(
        overflow_batch.transition,
        "expected_revision",
        MAX_AUTHORITY_REVISION_V2,
    )
    with pytest.raises(ValueError, match="ABI maximum"):
        store_receipt._validate_committed_artifacts(
            overflow_batch,
            overflow_receipt,
            overflow_inclusion,
        )


def test_store_failure_and_result_nested_types_are_explicit() -> None:
    with pytest.raises(TypeError, match="Protocol owner enum"):
        GovernanceFailureV2(  # type: ignore[arg-type]
            code="governance_read_set_stale",
            path="",
            stage=GovernanceFailureStageV2.PRECONDITION,
        )
    with pytest.raises(TypeError, match="stage"):
        GovernanceFailureV2(  # type: ignore[arg-type]
            code=AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
            path="",
            stage="precondition",
        )
    with pytest.raises(TypeError, match="Protocol-owned"):
        store_results._governance_disposition_for_diagnostic_v2(  # type: ignore[arg-type]
            "governance_read_set_stale"
        )

    domain, _, _, _, batch, _, _, committed, position = _committed_fixture()
    base = {
        "domain_root": domain.domain_root,
        "scope_ref": domain.scope_ref,
        "stream_ref": batch.stream_ref,
        "transition_id": batch.transition_id,
        "disposition": GovernanceCommitDispositionV2.COMMITTED,
        "failure": None,
        "committed_transition": committed,
        "position_observation": position,
    }
    for attribute, match in (
        ("failure", "failure"),
        ("committed_transition", "transition"),
        ("position_observation", "position"),
    ):
        candidate = SimpleNamespace(**{**base, attribute: object()})
        with pytest.raises(TypeError, match=match):
            store_results._snapshot_result_nested(candidate, "result")


def test_store_result_binding_closed_union_is_total() -> None:
    domain, _, _, _, batch, _, _, committed, position = _committed_fixture()
    common = {
        "canonical_version": store_foundation.AUTHORITY_CANONICAL_VERSION_V2,
        "domain_root": domain.domain_root,
        "scope_ref": domain.scope_ref,
        "stream_ref": batch.stream_ref,
        "transition_id": batch.transition_id,
        "label": "result",
    }
    with pytest.raises(TypeError, match="disposition"):
        store_results._validate_result_binding(
            **common,
            disposition="committed",
            failure=None,
            committed_transition=committed,
            position_observation=position,
        )
    with pytest.raises(ValueError, match="cannot carry failure"):
        store_results._validate_result_binding(
            **common,
            disposition=GovernanceCommitDispositionV2.COMMITTED,
            failure=_failure(),
            committed_transition=committed,
            position_observation=position,
        )
    with pytest.raises(ValueError, match="typed failure"):
        store_results._validate_result_binding(
            **common,
            disposition=GovernanceCommitDispositionV2.INVALID,
            failure=None,
            committed_transition=None,
            position_observation=None,
        )
    with pytest.raises(ValueError, match="cannot carry authority"):
        store_results._validate_result_binding(
            **common,
            disposition=GovernanceCommitDispositionV2.RETRY_REQUIRED,
            failure=_failure(),
            committed_transition=committed,
            position_observation=None,
        )


def test_store_commit_view_observation_and_receipt_binding_are_strict() -> None:
    domain, _, _, _, batch, receipt, _, committed, position = _committed_fixture()
    base = {
        "domain_root": domain.domain_root,
        "scope_ref": domain.scope_ref,
        "stream_ref": batch.stream_ref,
        "transition_id": batch.transition_id,
        "expected_receipt_root": receipt.receipt_root,
        "disposition": GovernanceCommitDispositionV2.COMMITTED,
        "failure": None,
        "committed_transition": committed,
        "position_observation": position,
        "observed_revision": position.observed_revision,
        "observed_head_root": position.observed_head_root,
    }
    with pytest.raises(ValueError, match="both present"):
        GovernanceCommitViewV2(**{**base, "observed_head_root": None})
    with pytest.raises(ValueError, match="expected receipt"):
        GovernanceCommitViewV2(**{**base, "expected_receipt_root": _root("9")})
    unavailable = _failure(AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE)
    with pytest.raises(ValueError, match="cannot fabricate"):
        GovernanceCommitViewV2(
            **{
                **base,
                "expected_receipt_root": None,
                "disposition": GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
                "failure": unavailable,
                "committed_transition": None,
                "position_observation": None,
            }
        )


def test_store_committed_position_cross_bindings_are_total() -> None:
    _, _, _, _, _, receipt, _, committed, position = _committed_fixture()
    common = {
        "domain_root": committed.batch.domain_root,
        "scope_ref": committed.batch.scope_ref,
        "stream_ref": committed.batch.stream_ref,
        "transition_id": committed.batch.transition_id,
        "committed": committed,
        "label": "result",
    }
    wrong_binding = replace(position)
    object.__setattr__(wrong_binding, "scope_ref", "scope:other")
    with pytest.raises(ValueError, match="cross authority binding"):
        store_results._validate_committed_result_position(
            **common,
            position=wrong_binding,
        )
    wrong_receipt = replace(position)
    object.__setattr__(wrong_receipt, "receipt_root", _root("9"))
    with pytest.raises(ValueError, match="committed receipt"):
        store_results._validate_committed_result_position(
            **common,
            position=wrong_receipt,
        )
    wrong_current = replace(position)
    object.__setattr__(wrong_current, "observed_head_root", _root("9"))
    with pytest.raises(ValueError, match="committed head"):
        store_results._validate_committed_result_position(
            **common,
            position=wrong_current,
        )
    sealed = replace(
        position,
        position=GovernanceCommitPositionV2.SEALED,
        seal_root=_root("8"),
        observation_root="",
    )
    object.__setattr__(sealed, "observed_revision", receipt.revision - 1)
    with pytest.raises(ValueError, match="predates"):
        store_results._validate_committed_result_position(
            **common,
            position=sealed,
        )


def test_baseline_contract_permission_and_result_defenses_are_total() -> None:
    journey = _baseline_journey("contract-defenses")
    forged_status = str.__new__(
        baseline_contracts.BaselineOutputTerminalStatusV2,
        "unsupported",
    )
    object.__setattr__(forged_status, "_name_", "FORGED")
    object.__setattr__(forged_status, "_value_", "unsupported")
    forged_permission = baseline_contracts.ActionPermissionV2.from_dict(
        journey.permission.to_dict()
    )
    object.__setattr__(forged_permission, "terminal_status", forged_status)
    with pytest.raises(ValueError, match="terminal_status is unsupported"):
        baseline_contracts._validate_permission(forged_permission)

    wrong_stream = baseline_contracts.BaselineOutputResultV2.from_dict(
        journey.result.to_dict()
    )
    object.__setattr__(
        wrong_stream.commit_attempt,
        "stream_ref",
        "authority:wrong-output",
    )
    assert wrong_stream.authorization is not None
    with pytest.raises(ValueError, match="commit attempt binding"):
        baseline_contracts._validate_result_permission_binding(
            wrong_stream,
            wrong_stream.authorization,
        )

    missing_transition = baseline_contracts.BaselineOutputResultV2.from_dict(
        journey.result.to_dict()
    )
    assert missing_transition.commit_attempt.committed_transition is not None
    object.__setattr__(
        missing_transition.commit_attempt.committed_transition.batch,
        "transition",
        None,
    )
    with pytest.raises(ValueError, match="missing output state"):
        baseline_contracts._validate_result_attempt_binding(missing_transition)

    non_mapping = baseline_contracts.BaselineOutputResultV2.from_dict(
        journey.result.to_dict()
    )
    assert non_mapping.commit_attempt.committed_transition is not None
    assert non_mapping.commit_attempt.committed_transition.batch.transition is not None
    object.__setattr__(
        non_mapping.commit_attempt.committed_transition.batch.transition,
        "state_records",
        (),
    )
    with pytest.raises(TypeError, match="must be a mapping"):
        baseline_contracts._validate_result_attempt_binding(non_mapping)

    invalid_state = baseline_contracts.BaselineOutputResultV2.from_dict(
        journey.result.to_dict()
    )
    assert invalid_state.commit_attempt.committed_transition is not None
    assert (
        invalid_state.commit_attempt.committed_transition.batch.transition is not None
    )
    object.__setattr__(
        invalid_state.commit_attempt.committed_transition.batch.transition,
        "state_records",
        {},
    )
    with pytest.raises(ValueError, match="output state is invalid"):
        baseline_contracts._validate_result_attempt_binding(invalid_state)


def test_baseline_stage_retry_and_decision_policy_defenses_are_total() -> None:
    context = _baseline_context(scope_ref="scope:baseline-totality:stage-retry")
    request = _baseline_request(
        context,
        request_label="stage-retry",
        decision_mode="direct_governance",
    )
    first = _baseline_issue(context, request)
    second = _baseline_issue(context, request)
    assert first.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert second.disposition is GovernanceCommitDispositionV2.COMMITTED

    session = session_contracts._governance_authority_session_state_v2(
        baseline_operations.open_baseline_output_authority_session_v2(
            context.capability,
            request,
            session_contracts.GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
        )
    )
    manifest_state = baseline_operations._project_state(
        context.store.load_state_v2(
            request.scope_ref,
            request.manifest_stream_ref,
        )
    )
    reconciled = baseline_operations._commit_stage(
        context.store,
        request,
        session,
        role="manifest",
        write_head=context.store.load_head_v2(
            request.scope_ref,
            request.manifest_stream_ref,
        ),
        dependencies=(),
        state=manifest_state,
        event=baseline_operations._manifest_event(request, session),
    )
    assert reconciled.disposition is GovernanceCommitDispositionV2.COMMITTED

    no_state_view = SimpleNamespace(
        disposition=GovernanceCommitDispositionV2.COMMITTED,
        position_observation=SimpleNamespace(
            position=GovernanceCommitPositionV2.CURRENT
        ),
        committed_transition=SimpleNamespace(batch=SimpleNamespace(transition=None)),
    )
    assert (
        baseline_operations._verified_signal_matches(
            no_state_view,
            request,
            {"signal_ref": "signal:a"},
        )
        is False
    )

    quorum_context = _baseline_context(
        scope_ref="scope:baseline-totality:quorum-policy"
    )
    quorum_request = _baseline_request(
        quorum_context,
        request_label="quorum-policy",
        decision_mode="quorum",
    )
    object.__setattr__(
        quorum_request.manifest.quorum_policy,
        "target",
        "target:other",
    )
    with pytest.raises(ValueError, match="policy target"):
        baseline_operations._evaluate_quorum(quorum_request, {"signals": []})

    fallback_context = _baseline_context(
        scope_ref="scope:baseline-totality:fallback-policy"
    )
    fallback_request = _baseline_request(
        fallback_context,
        request_label="fallback-policy",
        decision_mode="quorum",
    )
    object.__setattr__(
        fallback_request.manifest.quorum_policy,
        "fallback_candidate",
        "candidate:missing",
    )
    with pytest.raises(ValueError, match="safe candidate"):
        baseline_operations._safe_fallback(fallback_request)


def test_baseline_recovered_output_semantic_bindings_are_total() -> None:
    journey = _baseline_journey("recovered-bindings")
    request = journey.request
    permission = journey.permission
    attempt = journey.result.commit_attempt
    state = journey.state
    status = journey.result.terminal_status
    assert status is baseline_contracts.BaselineOutputTerminalStatusV2.EVIDENCE_COMMIT

    with pytest.raises(ValueError, match="candidate is not declared"):
        baseline_operations._require_recovered_output_bindings(
            state,
            request,
            permission,
            status,
            "candidate:missing",
            journey.result.result_root,
            attempt,
        )
    with pytest.raises(ValueError, match="fallback candidate"):
        baseline_operations._require_recovered_output_bindings(
            state,
            request,
            permission,
            baseline_contracts.BaselineOutputTerminalStatusV2.SAFE_FALLBACK,
            "candidate:accept",
            journey.result.result_root,
            attempt,
        )
    with pytest.raises(ValueError, match="direct output candidate"):
        baseline_operations._require_recovered_output_bindings(
            state,
            request,
            permission,
            status,
            "candidate:fallback",
            journey.result.result_root,
            attempt,
        )
    forged_status = str.__new__(
        baseline_contracts.BaselineOutputTerminalStatusV2,
        "forged",
    )
    object.__setattr__(forged_status, "_name_", "FORGED")
    object.__setattr__(forged_status, "_value_", "forged")
    with pytest.raises(ValueError, match="terminal status"):
        baseline_operations._require_recovered_output_bindings(
            state,
            request,
            permission,
            forged_status,
            "candidate:accept",
            journey.result.result_root,
            attempt,
        )

    mismatched_permission = baseline_contracts.ActionPermissionV2.from_dict(
        permission.to_dict()
    )
    object.__setattr__(
        mismatched_permission,
        "request_root",
        _root("9"),
    )
    with pytest.raises(ValueError, match="permission binding"):
        baseline_operations._require_recovered_output_bindings(
            state,
            request,
            mismatched_permission,
            status,
            "candidate:accept",
            journey.result.result_root,
            attempt,
        )
    with pytest.raises(ValueError, match="result binding"):
        baseline_operations._require_recovered_output_bindings(
            state,
            request,
            permission,
            status,
            "candidate:accept",
            _root("9"),
            attempt,
        )


def test_baseline_recovery_commit_material_rejects_each_authority_gap() -> None:
    journey = _baseline_journey("recovery-material")
    request = journey.request
    permission = journey.permission
    state = journey.state

    missing = GovernanceCommitAttemptV2.from_dict(
        journey.result.commit_attempt.to_dict()
    )
    object.__setattr__(missing, "committed_transition", None)
    with pytest.raises(ValueError, match="transition is absent"):
        baseline_operations._require_recovery_commit_material(
            state,
            request,
            permission,
            missing,
        )

    bad_fields = baseline_operations._project_state(state)
    bad_fields["session_binding"].pop("grant_ref")
    with pytest.raises(ValueError, match="binding fields"):
        baseline_operations._require_recovery_commit_material(
            bad_fields,
            request,
            permission,
            journey.result.commit_attempt,
        )

    bad_session = baseline_operations._project_state(state)
    bad_session["session_binding"]["run_ref"] = "run:other"
    with pytest.raises(ValueError, match="session binding"):
        baseline_operations._require_recovery_commit_material(
            bad_session,
            request,
            permission,
            journey.result.commit_attempt,
        )

    bad_shared_grant = baseline_operations._project_state(state)
    bad_shared_grant["session_binding"]["grant_root"] = _root("9")
    with pytest.raises(ValueError, match="shared grant"):
        baseline_operations._require_recovery_commit_material(
            bad_shared_grant,
            request,
            permission,
            journey.result.commit_attempt,
        )

    bad_read_set = GovernanceCommitAttemptV2.from_dict(
        journey.result.commit_attempt.to_dict()
    )
    assert bad_read_set.committed_transition is not None
    unrelated = GovernanceAuthorityReadSetV2(
        entries=(
            GovernanceReadPreconditionV2(
                "authority:unrelated",
                0,
                _root("0"),
            ),
        )
    )
    object.__setattr__(
        bad_read_set.committed_transition.batch,
        "read_set",
        unrelated,
    )
    with pytest.raises(ValueError, match="read set is invalid"):
        baseline_operations._require_recovery_commit_material(
            state,
            request,
            permission,
            bad_read_set,
        )


def test_baseline_recovery_precondition_and_trace_material_are_exact() -> None:
    journey = _baseline_journey("recovery-trace")
    request = journey.request
    permission = journey.permission
    state = journey.state

    bad_precondition = GovernanceCommitAttemptV2.from_dict(
        journey.result.commit_attempt.to_dict()
    )
    assert bad_precondition.committed_transition is not None
    batch = bad_precondition.committed_transition.batch
    entries = tuple(
        replace(entry, expected_root=_root("9"))
        if entry.stream_ref == request.output_stream_ref
        else entry
        for entry in batch.read_set.entries
    )
    object.__setattr__(
        batch,
        "read_set",
        GovernanceAuthorityReadSetV2(entries=entries),
    )
    with pytest.raises(ValueError, match="authority precondition"):
        baseline_operations._require_recovery_commit_material(
            state,
            request,
            permission,
            bad_precondition,
        )

    bad_event = GovernanceCommitAttemptV2.from_dict(
        journey.result.commit_attempt.to_dict()
    )
    assert bad_event.committed_transition is not None
    event_batch = bad_event.committed_transition.batch
    event = event_batch.trace_batch.events[0]
    wrong_event = store_batch.TraceEvent(
        event_type="x-not-baseline-output-committed",
        protocol_id=event.protocol_id,
        target=event.target,
        reason=event.reason,
        lineage=event.lineage,
    )
    object.__setattr__(
        event_batch,
        "trace_batch",
        GovernanceTraceBatchV2(
            domain_root=event_batch.domain_root,
            scope_ref=event_batch.scope_ref,
            stream_ref=event_batch.stream_ref,
            transition_id=event_batch.transition_id,
            events=(wrong_event,),
        ),
    )
    with pytest.raises(ValueError, match="Trace event"):
        baseline_operations._require_recovery_commit_material(
            state,
            request,
            permission,
            bad_event,
        )

    bad_lineage = GovernanceCommitAttemptV2.from_dict(
        journey.result.commit_attempt.to_dict()
    )
    assert bad_lineage.committed_transition is not None
    lineage_batch = bad_lineage.committed_transition.batch
    valid_event = lineage_batch.trace_batch.events[0]
    wrong_lineage = store_batch.TraceEvent(
        event_type=valid_event.event_type,
        protocol_id=valid_event.protocol_id,
        target=valid_event.target,
        reason=valid_event.reason,
        lineage={**valid_event.lineage, "candidate_ref": "candidate:wrong"},
    )
    object.__setattr__(
        lineage_batch,
        "trace_batch",
        GovernanceTraceBatchV2(
            domain_root=lineage_batch.domain_root,
            scope_ref=lineage_batch.scope_ref,
            stream_ref=lineage_batch.stream_ref,
            transition_id=lineage_batch.transition_id,
            events=(wrong_lineage,),
        ),
    )
    with pytest.raises(ValueError, match="Trace binding"):
        baseline_operations._require_recovery_commit_material(
            state,
            request,
            permission,
            bad_lineage,
        )


def test_baseline_low_level_state_and_result_failures_are_typed() -> None:
    journey = _baseline_journey("low-level")
    with pytest.raises(TypeError, match="exact object"):
        baseline_operations._project_state(())
    with pytest.raises(ValueError, match="fields"):
        baseline_operations._require_state_fields({}, {"required"}, "output")

    missing = GovernanceCommitAttemptV2.from_dict(
        journey.result.commit_attempt.to_dict()
    )
    object.__setattr__(missing, "committed_transition", None)
    with pytest.raises(ValueError, match="missing transition"):
        baseline_operations._view_or_attempt_state(missing)

    seal = GovernanceCommitAttemptV2.from_dict(journey.result.commit_attempt.to_dict())
    assert seal.committed_transition is not None
    object.__setattr__(seal.committed_transition.batch, "transition", None)
    with pytest.raises(ValueError, match="cannot be a seal"):
        baseline_operations._view_or_attempt_state(seal)

    invalid = GovernanceCommitAttemptV2.from_dict(
        journey.result.commit_attempt.to_dict()
    )
    assert invalid.committed_transition is not None
    assert invalid.committed_transition.batch.transition is not None
    object.__setattr__(
        invalid.committed_transition.batch.transition,
        "state_records",
        {},
    )
    invalid_result = baseline_operations._result_from_attempt(
        journey.context.store,
        journey.request,
        invalid,
    )
    assert (
        invalid_result.commit_attempt.failure.code
        is AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )

    retry = baseline_operations._bound_failure_attempt(
        journey.request.domain_root,
        journey.request.scope_ref,
        journey.request.output_stream_ref,
        journey.request.output_transition_id,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        "/read_set",
        GovernanceFailureStageV2.PRECONDITION,
    )
    retry_result = baseline_operations._failure_result(journey.request, retry)
    assert (
        retry_result.delivery_disposition
        is baseline_contracts.BaselineOutputDeliveryDispositionV2.RETRY_REQUIRED
    )

    class ExplodingReader:
        def __getattribute__(self, _name: str) -> object:
            raise RuntimeError("reader reflection failed")

    loaded = baseline_operations._load_recovery_attempt(
        journey.request,
        ExplodingReader(),
    )
    assert loaded.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH

    _, store_failure = baseline_operations._validated_session_or_failure(
        _session(),
        journey.request,
        session_contracts.GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
        journey.request.output_stream_ref,
        journey.request.output_transition_id,
    )
    assert store_failure is not None
    assert (
        store_failure.failure.code
        is AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH
    )


def test_baseline_output_inputs_reject_nonrecomputable_durable_decision() -> None:
    journey = _baseline_journey("nonrecomputable")
    request = journey.request
    decision = baseline_operations._project_state(
        journey.context.store.load_state_v2(
            request.scope_ref,
            request.decision_stream_ref,
        )
    )
    decision["candidate_ref"] = "candidate:fallback"
    decision["terminal_status"] = (
        baseline_contracts.BaselineOutputTerminalStatusV2.SAFE_FALLBACK.value
    )
    store = _DelegatingStoreV2(
        journey.context.store,
        state_overrides={request.decision_stream_ref: decision},
    )
    result = baseline_operations._load_output_inputs(store, request)
    assert isinstance(result, GovernanceCommitAttemptV2)
    assert result.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH


def test_baseline_permission_current_handles_disappearing_transition() -> None:
    journey = _baseline_journey("disappearing-transition")
    committed = journey.result.commit_attempt.committed_transition
    assert committed is not None

    class DisappearingAttempt:
        position_observation = journey.result.commit_attempt.position_observation

        def __init__(self) -> None:
            self.reads = 0

        @property
        def committed_transition(self) -> object | None:
            self.reads += 1
            return committed if self.reads <= 2 else None

    assert (
        baseline_operations._permission_current_for_result(
            journey.context.store,
            journey.request,
            journey.permission,
            DisappearingAttempt(),  # type: ignore[arg-type]
        )
        is False
    )


def test_baseline_validated_session_reports_domain_binding_failure() -> None:
    journey = _baseline_journey("session-domain")
    handle = baseline_operations.open_baseline_output_authority_session_v2(
        journey.context.capability,
        journey.request,
        session_contracts.GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
    )
    state = session_contracts._governance_authority_session_state_v2(handle)
    object.__setattr__(state, "domain_root", _root("9"))
    snapshot = list(state._snapshot)
    snapshot[3] = _root("9")
    object.__setattr__(state, "_snapshot", tuple(snapshot))
    _, failure = baseline_operations._validated_session_or_failure(
        handle,
        journey.request,
        session_contracts.GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
        journey.request.output_stream_ref,
        journey.request.output_transition_id,
    )
    assert failure is not None
    assert failure.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH


def test_baseline_permission_grant_head_maps_missing_and_invalid_state() -> None:
    journey = _baseline_journey("permission-grant-head")
    session = session_contracts._governance_authority_session_state_v2(
        baseline_operations.open_baseline_output_authority_session_v2(
            journey.context.capability,
            journey.request,
            session_contracts.GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
        )
    )
    missing = baseline_operations._permission_issuer_grant_head(
        _StaticStoreV2(),
        journey.request,
        session,
        journey.permission,
    )
    assert isinstance(missing, GovernanceCommitAttemptV2)
    assert (
        missing.failure.code
        is AuthorityDiagnosticCodeV2.GOVERNANCE_ACTION_NOT_AUTHORIZED
    )
    invalid = baseline_operations._permission_issuer_grant_head(
        _StaticStoreV2(state={}),
        journey.request,
        session,
        journey.permission,
    )
    assert isinstance(invalid, GovernanceCommitAttemptV2)
    assert invalid.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED


def test_baseline_durable_state_decoders_reject_bound_field_tamper() -> None:
    journey = _baseline_journey("decoder-tamper")
    request = journey.request
    cases = (
        (
            request.evidence_stream_ref,
            baseline_operations._decode_evidence_state,
            "evidence",
        ),
        (
            request.stop_stream_ref,
            baseline_operations._decode_stop_state,
            "stop",
        ),
        (
            request.decision_stream_ref,
            baseline_operations._decode_decision_state,
            "decision",
        ),
        (
            request.output_stream_ref,
            baseline_operations._require_output_state,
            "output",
        ),
    )
    for stream_ref, decoder, label in cases:
        state = baseline_operations._project_state(
            journey.context.store.load_state_v2(request.scope_ref, stream_ref)
        )
        state["scope_ref"] = "scope:other"
        with pytest.raises(ValueError, match=label):
            decoder(state, request)


def test_baseline_permission_grant_checks_are_total() -> None:
    journey = _baseline_journey("permission-grant")
    request = journey.request
    permission = journey.permission
    grant = journey.context.grant

    assert baseline_operations._permission_issuer_grant_failure(
        request,
        permission,
        {"status": "pending"},
        grant,
    ) == (
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
        "/permission/grant_ref",
    )

    wrong_grant = session_contracts.GovernanceIssuerGrantV2.from_dict(grant.to_dict())
    object.__setattr__(wrong_grant, "grant_root", _root("9"))
    assert baseline_operations._permission_issuer_grant_failure(
        request,
        permission,
        {"status": "active"},
        wrong_grant,
    ) == (
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/permission/grant_ref",
    )

    denied_grant = session_contracts.GovernanceIssuerGrantV2.from_dict(grant.to_dict())
    object.__setattr__(
        denied_grant,
        "operations",
        (session_contracts.GovernanceIssuerOperationV2.VERIFY_SIGNAL,),
    )
    assert baseline_operations._permission_issuer_grant_failure(
        request,
        permission,
        {"status": "active"},
        denied_grant,
    ) == (
        AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
        "/permission/grant_ref",
    )

    expired_permission = baseline_contracts.ActionPermissionV2.from_dict(
        permission.to_dict()
    )
    object.__setattr__(
        expired_permission,
        "issued_epoch",
        grant.expires_at_epoch + 1,
    )
    assert baseline_operations._permission_issuer_grant_failure(
        request,
        expired_permission,
        {"status": "active"},
        grant,
    ) == (
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED,
        "/permission/issued_epoch",
    )


def test_baseline_reconcile_view_matchers_reject_seal_views() -> None:
    journey = _baseline_journey("view-matchers")
    view = SimpleNamespace(
        committed_transition=SimpleNamespace(batch=SimpleNamespace(transition=None))
    )
    session = session_contracts._governance_authority_session_state_v2(
        baseline_operations.open_baseline_output_authority_session_v2(
            journey.context.capability,
            journey.request,
            session_contracts.GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT,
        )
    )
    assert (
        baseline_operations._permission_view_matches(
            view,
            journey.request,
            session,
        )
        is False
    )
    assert (
        baseline_operations._output_view_matches(
            view,
            journey.request,
            session,
        )
        is False
    )
    assert baseline_operations._stage_view_matches(view, {}) is False


def test_evidence_context_and_contract_helpers_fail_closed() -> None:
    journey = _evidence_journey("contracts")
    request = journey.request
    snapshot = request.snapshot

    with pytest.raises(TypeError, match="exact Protocol declaration"):
        evidence_context._policy_snapshot(object(), {})
    with pytest.raises(ValueError, match="portable policy"):
        evidence_context._evidence_extensions({})
    with pytest.raises(ValueError, match="portable declaration"):
        evidence_context._evidence_extensions({"collective_commit_policy": {}})

    assert snapshot.root() == snapshot.snapshot_root
    assert request.root() == request.request_root
    assert snapshot.canonical_bytes()
    assert request.canonical_bytes()
    payload = snapshot.to_dict()
    payload["assurance"] = "unsupported"
    with pytest.raises(ValueError, match="assurance"):
        evidence_contracts.CommitEvidenceSnapshotV2.from_dict(payload)
    with pytest.raises(ValueError, match="request version"):
        replace(request, schema="unsupported")
    with pytest.raises(TypeError, match="exact snapshot"):
        replace(request, snapshot=object())
    with pytest.raises(ValueError, match="scope_ref is cross-bound"):
        replace(request, scope_ref="scope:other")
    with pytest.raises(ValueError, match="request_root"):
        replace(request, request_root=_root("8"))
    with pytest.raises(TypeError, match="exact snapshot"):
        evidence_contracts.active_qualified_evidence_v2(object())


def test_evidence_snapshot_validation_and_roots_are_total() -> None:
    snapshot = _evidence_journey("snapshot-validation").request.snapshot
    invalid_contexts = (
        (_unchecked(snapshot, schema="unsupported"), "version"),
        (_unchecked(snapshot, evidence_policy=object()), "policy"),
        (_unchecked(snapshot, assurance="evidence_bound"), "profile"),
        (_unchecked(snapshot, profile="unsupported"), "profile"),
        (
            _unchecked(snapshot, expires_at_step=snapshot.current_step),
            "expired",
        ),
        (_unchecked(snapshot, stream_ref="authority:wrong"), "lineage identity"),
    )
    for candidate, message in invalid_contexts:
        with pytest.raises((TypeError, ValueError), match=message):
            evidence_contracts._validate_snapshot_context(candidate)

    records = tuple(snapshot.records)
    with pytest.raises(ValueError, match="record counts"):
        evidence_contracts._validate_snapshot_counts(
            _unchecked(snapshot, record_count=snapshot.record_count + 1),
            records,
        )
    with pytest.raises(ValueError, match="revision"):
        evidence_contracts._validate_snapshot_counts(
            _unchecked(snapshot, revision=2),
            records,
        )
    with pytest.raises(ValueError, match="genesis continuity"):
        evidence_contracts._validate_snapshot_counts(
            _unchecked(snapshot, parent_epoch=0),
            records,
        )
    successor = _unchecked(
        snapshot,
        revision=2,
        parent_revision=1,
        parent_epoch=None,
        parent_history_count=1,
    )
    with pytest.raises(ValueError, match="successor continuity"):
        evidence_contracts._validate_snapshot_counts(successor, records)

    with pytest.raises(ValueError, match="history_count"):
        evidence_contracts._install_snapshot_roots(
            _unchecked(snapshot, history_count=3),
            records,
        )
    with pytest.raises(ValueError, match="record_set_root"):
        evidence_contracts._install_snapshot_roots(
            _unchecked(snapshot, record_set_root=_root("7")),
            records,
        )
    with pytest.raises(ValueError, match="snapshot_root"):
        evidence_contracts._install_snapshot_roots(
            _unchecked(snapshot, snapshot_root=_root("7")),
            records,
        )


def test_evidence_opaque_context_source_and_state_protocols_are_total() -> None:
    journey = _evidence_journey("opaque-protocols", commit=True)
    state = journey.state
    source = journey.source
    verified_context = evidence_adapter._verified_commit_evidence_context_v2(
        state,
        journey.replay_state,
        current_step=4,
    )

    with pytest.raises(TypeError, match="cannot be constructed"):
        evidence_adapter._VerifiedCommitEvidenceContextV2()
    with pytest.raises(TypeError, match="final"):
        type(
            "EvidenceContextSubclass",
            (evidence_adapter._VerifiedCommitEvidenceContextV2,),
            {},
        )
    with pytest.raises(AttributeError, match="immutable"):
        verified_context.anything = 1
    with pytest.raises(TypeError, match="not portable"):
        verified_context.__reduce__()
    with pytest.raises(TypeError, match="not portable"):
        verified_context.__reduce_ex__(4)
    with pytest.raises(TypeError, match="not portable"):
        verified_context.__getstate__()
    with pytest.raises(TypeError, match="exact opaque"):
        evidence_adapter._verified_commit_evidence_context_material_v2(object())
    with pytest.raises(TypeError, match="incomplete"):
        evidence_adapter._verified_commit_evidence_context_material_v2(
            object.__new__(evidence_adapter._VerifiedCommitEvidenceContextV2)
        )
    stale_context = _opaque_clone(verified_context, _anchor_root=_root("7"))
    with pytest.raises(Exception, match="evidence_context"):
        evidence_adapter._verified_commit_evidence_context_material_v2(stale_context)

    with pytest.raises(TypeError, match="cannot be constructed"):
        evidence_source_proof.VerifiedCommitEvidenceSourceV2()
    with pytest.raises(TypeError, match="final"):
        type(
            "EvidenceSourceSubclass",
            (evidence_source_proof.VerifiedCommitEvidenceSourceV2,),
            {},
        )
    with pytest.raises(AttributeError, match="immutable"):
        source.anything = 1
    with pytest.raises(TypeError, match="not portable"):
        source.__reduce__()
    with pytest.raises(TypeError, match="not portable"):
        source.__reduce_ex__(4)
    with pytest.raises(TypeError, match="not portable"):
        source.__getstate__()
    assert repr(source) == "<VerifiedCommitEvidenceSourceV2 redacted>"
    assert source.context_root
    with pytest.raises(TypeError, match="exact request"):
        evidence_source_proof._source_context_root_from_request_v2(object())

    with pytest.raises(TypeError, match="cannot be constructed"):
        evidence_state_handle.VerifiedCommitEvidenceStateV2()
    with pytest.raises(TypeError, match="final"):
        type(
            "EvidenceStateSubclass",
            (evidence_state_handle.VerifiedCommitEvidenceStateV2,),
            {},
        )
    with pytest.raises(AttributeError, match="immutable"):
        state.anything = 1
    assert state.__copy__() is state
    assert state.__deepcopy__({}) is state
    with pytest.raises(TypeError, match="not portable"):
        state.__reduce__()
    with pytest.raises(TypeError, match="not portable"):
        state.__reduce_ex__(4)
    with pytest.raises(TypeError, match="not portable"):
        state.__getstate__()
    assert repr(state) == "<VerifiedCommitEvidenceStateV2 redacted>"
    assert state.snapshot == journey.request.snapshot
    assert state.request_root == journey.request.request_root
    assert state.stream_ref == journey.request.stream_ref
    assert state.transition_id == journey.request.transition_id
    assert state.receipt_root


def test_evidence_context_adapter_dependency_defenses_are_typed() -> None:
    journey = _evidence_journey("adapter-dependencies", commit=True)
    snapshot = journey.request.snapshot
    replay = journey.replay_state.snapshot

    with pytest.raises(Exception, match="replay_state"):
        evidence_adapter._context_material(journey.state, object(), 4)
    with pytest.raises(Exception, match="current_step"):
        evidence_adapter._validate_assessment_time(snapshot, replay, 0)
    with pytest.raises(Exception, match="replay_state"):
        evidence_adapter._validate_replay_context(
            snapshot,
            _unchecked(replay, scope_ref="scope:other"),
        )
    with pytest.raises(Exception, match="observed_epoch"):
        evidence_adapter._validate_replay_context(
            snapshot,
            _unchecked(replay, observed_epoch=snapshot.epoch + 1),
        )

    precondition = GovernanceReadPreconditionV2(
        snapshot.membership_stream_ref,
        snapshot.membership_revision,
        snapshot.membership_head_root,
    )

    class RaisingReader:
        def load_commit_view_v2(self, *_args: object) -> object:
            raise RuntimeError("reader failed")

    with pytest.raises(Exception, match="dependencies"):
        evidence_adapter._dependency_receipt_root(
            RaisingReader(),  # type: ignore[arg-type]
            snapshot.scope_ref,
            snapshot.membership_stream_ref,
            snapshot.membership_transition_id,
            precondition,
        )

    valid_view = journey.context.store.load_commit_view_v2(
        snapshot.scope_ref,
        snapshot.membership_stream_ref,
        snapshot.membership_transition_id,
    )

    class FixedReader:
        def __init__(self, view: object) -> None:
            self.view = view

        def load_commit_view_v2(self, *_args: object) -> object:
            return self.view

    invalid_view = _unchecked(
        valid_view,
        disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        committed_transition=None,
    )
    with pytest.raises(Exception, match="dependencies"):
        evidence_adapter._dependency_receipt_root(
            FixedReader(invalid_view),  # type: ignore[arg-type]
            snapshot.scope_ref,
            snapshot.membership_stream_ref,
            snapshot.membership_transition_id,
            precondition,
        )
    wrong_precondition = GovernanceReadPreconditionV2(
        snapshot.membership_stream_ref,
        snapshot.membership_revision,
        _root("7"),
    )
    with pytest.raises(Exception, match="dependencies"):
        evidence_adapter._dependency_receipt_root(
            FixedReader(valid_view),  # type: ignore[arg-type]
            snapshot.scope_ref,
            snapshot.membership_stream_ref,
            snapshot.membership_transition_id,
            wrong_precondition,
        )


def test_evidence_operations_and_source_failures_are_explicit() -> None:
    journey = _evidence_journey("operation-failures")
    request = journey.request
    session = session_contracts._governance_authority_session_state_v2(journey.session)

    with pytest.raises(TypeError, match="exact request"):
        evidence_operations.advance_commit_evidence_state_v2(object())
    with pytest.raises(TypeError, match="exact capability"):
        evidence_operations.open_commit_evidence_authority_session_v2(
            object(),  # type: ignore[arg-type]
            request,
        )
    attempt = evidence_operations.advance_commit_evidence_state_v2(
        request,
        source=journey.source,
        authority_session=object(),
    )
    assert attempt.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED
    invalid_source, failure = evidence_operations._validated_source_or_failure(
        session,
        request,
        object(),
        journey.context.domain,
    )
    assert invalid_source is None
    assert failure is not None
    other_domain = _unchecked(
        journey.context.domain,
        domain_root=_root("7"),
    )
    invalid_source, failure = evidence_operations._validated_source_or_failure(
        session,
        request,
        journey.source,
        other_domain,
    )
    assert invalid_source is None
    assert failure is not None
    with pytest.raises(TypeError, match="exact request"):
        evidence_operations._require_request(object())
    with pytest.raises(ValueError, match="not committed"):
        evidence_operations._head_from_view(
            _unchecked(
                journey.context.store.load_commit_view_v2(
                    request.scope_ref,
                    journey.replay_request.stream_ref,
                    journey.replay_request.transition_id,
                ),
                committed_transition=None,
            ),
            journey.context.domain,
        )
    assert (
        evidence_operations._committed_view_matches_request(
            SimpleNamespace(),
            request,
            session,
        )
        is False
    )
    wrong_domain = _unchecked(
        journey.context.domain,
        scope_ref="scope:other",
        domain_root=_root("8"),
    )
    with pytest.raises(Exception, match="domain_root"):
        evidence_operations.rehydrate_commit_evidence_state_v2(
            request.to_dict(),
            domain=wrong_domain,
            state_reader=journey.context.store,
        )


def test_evidence_operation_owner_and_parent_failures_are_total() -> None:
    journey = _evidence_journey("owner-parent")
    request = journey.request
    wrong_grant = replace(
        journey.context.grant,
        issuer_ref="issuer:evidence:other",
        grant_ref="grant:evidence:other",
        grant_binding_ref=_root("6"),
        grant_root="",
    )
    activated = evidence_fixture.activate_governance_issuer_grant_v2(
        journey.context.store,
        journey.context.domain,
        wrong_grant,
        "transition:evidence:grant:other",
        1,
    )
    assert activated.committed_transition is not None
    wrong_capability = evidence_fixture._capability(
        journey.context,
        wrong_grant,
        request.observed_epoch,
    )
    forged_for_open = _unchecked(
        request,
        snapshot=_unchecked(
            request.snapshot,
            mutation_issuer_ref=wrong_grant.issuer_ref,
        ),
    )
    wrong_session = evidence_operations.open_commit_evidence_authority_session_v2(
        wrong_capability,
        forged_for_open,
    )
    denied = evidence_operations.advance_commit_evidence_state_v2(
        request,
        source=journey.source,
        authority_session=wrong_session,
    )
    assert denied.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    assert denied.failure.path == "/snapshot/mutation_issuer_ref"

    journey = _evidence_journey("wrong-parent-view", commit=True)
    request = journey.request
    child = _unchecked(
        request,
        snapshot=_unchecked(
            request.snapshot,
            parent_revision=1,
            parent_transition_id=request.transition_id,
            parent_snapshot_root=request.snapshot.snapshot_root,
        ),
    )
    replay_view = journey.context.store.load_commit_view_v2(
        request.scope_ref,
        journey.replay_request.stream_ref,
        journey.replay_request.transition_id,
    )

    class WrongParentStore:
        def load_commit_view_v2(self, *_args: object) -> object:
            return replay_view

    loaded, failure = evidence_operations._load_parent(
        WrongParentStore(),  # type: ignore[arg-type]
        journey.context.domain,
        child,
    )
    assert loaded is None
    assert failure is not None

    finality_view = GovernanceCommitViewV2(
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        stream_ref=request.snapshot.membership_stream_ref,
        transition_id=request.snapshot.membership_transition_id,
        expected_receipt_root=None,
        disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        failure=_failure(AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE),
        committed_transition=None,
        position_observation=None,
        observed_revision=None,
        observed_head_root=None,
    )

    class FinalityReader:
        def load_commit_view_v2(self, *_args: object) -> object:
            return finality_view

    precondition = GovernanceReadPreconditionV2(
        request.snapshot.membership_stream_ref,
        request.snapshot.membership_revision,
        request.snapshot.membership_head_root,
    )
    with pytest.raises(Exception, match="dependencies"):
        evidence_adapter._dependency_receipt_root(
            FinalityReader(),  # type: ignore[arg-type]
            request.scope_ref,
            request.snapshot.membership_stream_ref,
            request.snapshot.membership_transition_id,
            precondition,
        )


def test_evidence_sealed_domain_maps_lifecycle_failure() -> None:
    journey = _evidence_journey("sealed-domain")
    request = journey.request
    stream_refs = tuple(
        sorted(
            {
                session_contracts.governance_issuer_grant_stream_ref_v2(
                    request.scope_ref,
                    journey.context.grant.grant_ref,
                ),
                session_contracts.governance_issuer_grant_stream_ref_v2(
                    request.scope_ref,
                    "grant:replay:evidence",
                ),
                journey.upstreams.verification_request.stream_ref,
                journey.upstreams.membership_request.stream_ref,
                journey.replay_request.stream_ref,
            }
        )
    )
    retirement = session_contracts.GovernanceDomainRetirementRequestV2(
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        run_ref=request.run_ref,
        request_ref="request:evidence:retire",
        transition_id="transition:evidence:retire",
        stream_refs=stream_refs,
        reason_ref="reason:complete",
        observed_epoch=request.observed_epoch + 1,
    )
    retirement_session = session_operations.open_governance_authority_session_v2(
        evidence_fixture._capability(
            journey.context,
            journey.context.grant,
            retirement.observed_epoch,
        ),
        retirement,
    )
    retired = session_operations.retire_governance_domain_v2(
        retirement,
        authority_session=retirement_session,
    )
    assert retired.committed_transition is not None
    denied = evidence_operations.advance_commit_evidence_state_v2(
        request,
        source=journey.source,
        authority_session=journey.session,
    )
    assert denied.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED


def test_evidence_state_handle_and_record_decoders_are_total() -> None:
    journey = _evidence_journey("state-defenses", commit=True)
    request = journey.request
    snapshot = request.snapshot

    with pytest.raises(Exception, match="dependencies"):
        evidence_state_handle._require_current_dependency_head(
            _StaticStoreV2(),  # type: ignore[arg-type]
            request.scope_ref,
            snapshot.membership_stream_ref,
            snapshot.membership_revision,
            snapshot.membership_head_root,
        )
    with pytest.raises(Exception, match="dependencies"):
        evidence_state_handle._require_current_dependency_head(
            _StaticStoreV2(head={}),  # type: ignore[arg-type]
            request.scope_ref,
            snapshot.membership_stream_ref,
            snapshot.membership_revision,
            snapshot.membership_head_root,
        )
    with pytest.raises(Exception, match="AUTHORITY_BINDING_MISMATCH|binding"):
        evidence_state_handle._verified_state_view(object())
    incomplete = object.__new__(evidence_state_handle.VerifiedCommitEvidenceStateV2)
    with pytest.raises(Exception):
        evidence_state_handle._verified_state_view(incomplete)
    malformed = _opaque_clone(journey.state, _receipt_root=object())
    with pytest.raises(Exception, match="request_root"):
        evidence_state_handle._verified_state_view(malformed)
    with pytest.raises(TypeError, match="exact AuthorityDomain"):
        evidence_state_handle._require_domain(object())
    with pytest.raises(TypeError, match="StateReader"):
        evidence_state_handle._require_reader(object())
    assert evidence_state_handle.commit_evidence_state_is_current_v2(object()) is False

    with pytest.raises(ValueError, match="keys"):
        evidence_state_records._string_object({1: "value"}, "commit evidence")
    with pytest.raises(ValueError, match="invalid"):
        evidence_state_records._text_field({"field": object()}, "field")
    with pytest.raises(ValueError, match="invalid"):
        evidence_state_records._integer_field({"field": True}, "field")


def test_evidence_dependency_proposal_replay_and_parent_edges_are_total() -> None:
    journey = _evidence_journey("dependency-proposal")
    dependency = evidence_dependencies._dependency_material(
        journey.upstreams.verification_state,
        journey.upstreams.membership_state,
        journey.replay_state,
    )
    context = evidence_context.commit_evidence_context_v2(
        journey.context.manifest,
        profile=evidence_fixture.PROFILE,
        target_ref=evidence_fixture.TARGET,
    )
    with pytest.raises(ValueError, match="does not bind verification"):
        evidence_dependencies._validate_dependency_context(
            _unchecked(dependency, verification_head_root=_root("7")),
            context=context,
            domain_root=journey.request.domain_root,
            scope_ref=journey.request.scope_ref,
            run_ref=journey.request.run_ref,
            epoch=journey.request.snapshot.epoch,
            current_step=journey.request.snapshot.current_step,
        )

    record = journey.request.snapshot.records[0]
    revocation = evidence_proposals.CommitEvidenceRevocationV2(
        revocation_ref="revocation:totality",
        record_ref=record.record_ref,
        record_root=record.record_root,
        revoked_at_step=8,
        reason_codes=("reason:withdrawn",),
        provenance_root=_root("8"),
        trace_roots=(_root("9"),),
    )
    with pytest.raises(TypeError, match="bounded array"):
        evidence_proposals.canonical_revocations_v2(object())
    with pytest.raises(TypeError, match="non-exact"):
        evidence_proposals.canonical_revocations_v2((object(),))
    with pytest.raises(ValueError, match="repeat"):
        evidence_proposals.canonical_revocations_v2((revocation, revocation))

    with pytest.raises(ValueError, match="not reconstructable"):
        evidence_replay.commit_evidence_replay_receipts_for_target_v2(
            _unchecked(record, replay_receipt_roots=(_root("7"),)),
            target_ref=journey.request.target_ref,
        )

    parent = journey.request.snapshot
    with pytest.raises(ValueError, match="new epoch"):
        evidence_source._validated_parent(
            parent,
            domain_root=parent.domain_root,
            scope_ref=parent.scope_ref,
            protocol_ref=parent.protocol_ref,
            run_ref=parent.run_ref,
            target_ref=parent.target_ref,
            epoch=parent.epoch,
            current_step=parent.current_step + 1,
            manifest_root=_root("7"),
            commit_policy_root=parent.commit_policy_root,
        )


def test_evidence_qualification_relational_defenses_are_total() -> None:
    journey = _evidence_journey("qualification")
    dependency = evidence_dependencies._dependency_material(
        journey.upstreams.verification_state,
        journey.upstreams.membership_state,
        journey.replay_state,
    )
    context = evidence_context.commit_evidence_context_v2(
        journey.context.manifest,
        profile=evidence_fixture.PROFILE,
        target_ref=evidence_fixture.TARGET,
    )
    counter = evidence_adversarial._counter_attestation()
    with pytest.raises(ValueError, match="exactly one disposition"):
        evidence_qualification.qualify_commit_evidence_v2(
            context=context,
            membership=dependency.membership,
            verification=dependency.verification,
            epoch=1,
            current_step=4,
            qualification_issuer_ref=journey.context.grant.issuer_ref,
            qualification_provenance_root=_root("7"),
            qualification_trace_roots=(_root("8"),),
            attestations=(counter,),
            dispositions=(),
            existing_records=(),
        )

    with pytest.raises(ValueError, match="lacks its verified"):
        evidence_qualification._principal_material(
            dependency.membership,
            _unchecked(dependency.verification, records=()),
        )
    verification_record = dependency.verification.records[0]
    mismatched_record = _unchecked(
        verification_record,
        failure_domain_ref="failure-domain:other",
    )
    with pytest.raises(ValueError, match="identity is unverified"):
        evidence_qualification._principal_material(
            dependency.membership,
            _unchecked(dependency.verification, records=(mismatched_record,)),
        )

    with pytest.raises(ValueError, match="dependencies diverge"):
        evidence_qualification._validate_context_dependencies(
            context,
            dependency.membership,
            _unchecked(dependency.verification, scope_ref="scope:other"),
            epoch=1,
            current_step=4,
        )
    with pytest.raises(ValueError, match="cross-bound"):
        evidence_qualification._validate_context_dependencies(
            context,
            _unchecked(dependency.membership, profile="unsupported"),
            _unchecked(dependency.verification, profile="unsupported"),
            epoch=1,
            current_step=4,
        )
    with pytest.raises(ValueError, match="not fresh"):
        evidence_qualification._validate_context_dependencies(
            context,
            _unchecked(dependency.membership, expires_at_step=4),
            dependency.verification,
            epoch=1,
            current_step=4,
        )
    with pytest.raises(ValueError, match="does not bind"):
        evidence_qualification._validate_context_dependencies(
            context,
            _unchecked(
                dependency.membership,
                verification_snapshot_root=_root("7"),
            ),
            dependency.verification,
            epoch=1,
            current_step=4,
        )

    existing = journey.request.snapshot.records[0]
    replaying_disposition = _unchecked(
        existing,
        record_ref="evidence:other",
        nonce="nonce:other",
        attestation_root=_root("7"),
        disposition_nonce=existing.nonce,
        disposition_root=_root("8"),
    )
    with pytest.raises(ValueError, match="attestation nonce"):
        evidence_qualification._validate_identity_additions(
            (existing,),
            (replaying_disposition,),
        )

    counter_record = _unchecked(
        existing,
        principal_ref="principal:counter",
        cluster_ref="cluster:counter",
        failure_domain_ref="domain:counter",
    )
    rebuttals = (
        _unchecked(
            existing,
            principal_ref="principal:one",
            cluster_ref="cluster:one",
            failure_domain_ref="domain:one",
        ),
        _unchecked(
            existing,
            principal_ref="principal:two",
            cluster_ref="cluster:two",
            failure_domain_ref="domain:two",
        ),
    )
    evidence_qualification._validate_rebuttal_independence(
        counter_record,
        rebuttals,
    )


def test_evidence_history_and_parent_loading_defenses_are_total() -> None:
    journey = _evidence_journey("history-parent", commit=True)
    request = journey.request
    view = journey.context.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    committed, binding, _ = evidence_state_verification._decode_committed_view(
        view,
        journey.context.domain,
    )
    assert committed.to_dict() == request.to_dict()

    read_set = view.committed_transition.batch.read_set
    duplicate_read_set = _unchecked(
        read_set,
        entries=(*read_set.entries, read_set.entries[0]),
    )
    duplicate_batch = _unchecked(
        view.committed_transition.batch,
        read_set=duplicate_read_set,
    )
    duplicate_transition = _unchecked(
        view.committed_transition,
        batch=duplicate_batch,
    )
    with pytest.raises(ValueError, match="duplicate"):
        evidence_state_verification._validate_committed_read_set(
            _unchecked(view, committed_transition=duplicate_transition),
            request,
            binding,
        )
    incomplete_read_set = _unchecked(read_set, entries=read_set.entries[:-1])
    incomplete_batch = _unchecked(
        view.committed_transition.batch,
        read_set=incomplete_read_set,
    )
    incomplete_transition = _unchecked(
        view.committed_transition,
        batch=incomplete_batch,
    )
    with pytest.raises(ValueError, match="read set"):
        evidence_state_verification._validate_committed_read_set(
            _unchecked(view, committed_transition=incomplete_transition),
            request,
            binding,
        )

    parent = request.snapshot
    with pytest.raises(ValueError, match="cross-bound"):
        evidence_state_verification._validate_transition_delta(
            _unchecked(parent, scope_ref="scope:other"),
            parent,
        )
    with pytest.raises(ValueError, match="continuity"):
        evidence_state_verification._validate_transition_delta(parent, parent)
    successor = _unchecked(
        parent,
        revision=2,
        parent_revision=1,
        parent_epoch=parent.epoch,
        parent_transition_id=parent.transition_id,
        parent_snapshot_root=parent.snapshot_root,
        parent_history_root=parent.history_root,
        parent_history_count=parent.history_count,
        current_step=parent.current_step + 1,
    )
    with pytest.raises(ValueError, match="policy rotated"):
        evidence_state_verification._validate_transition_delta(
            _unchecked(successor, profile="unsupported"),
            parent,
        )
    changed_policy = _unchecked(
        parent.evidence_policy,
        minimum_quality_ppm=parent.evidence_policy.minimum_quality_ppm - 1,
    )
    with pytest.raises(ValueError, match="policy snapshot changed"):
        evidence_state_verification._validate_transition_delta(
            _unchecked(successor, evidence_policy=changed_policy),
            parent,
        )
    with pytest.raises(ValueError, match="dropped history"):
        evidence_state_verification._validate_transition_delta(
            _unchecked(successor, records=()),
            parent,
        )
    with pytest.raises(ValueError, match="mutation delta"):
        evidence_state_verification._validate_transition_delta(
            _unchecked(successor, mutation_record_roots=(_root("7"),)),
            parent,
        )
    with pytest.raises(ValueError, match="not a revocation"):
        evidence_state_verification._validate_revocation_replacement(
            parent.records[0],
            parent.records[0],
            parent.current_step + 1,
        )

    mismatched_expected = _unchecked(request, target_ref="target:other")
    with pytest.raises(Exception, match="request_root"):
        evidence_state_verification._load_verified_request_view(
            journey.context.store,
            journey.context.domain,
            mismatched_expected,
            expected_receipt_root=None,
        )
    cycle_request = _unchecked(
        request,
        snapshot=_unchecked(
            parent,
            parent_revision=1,
            parent_transition_id=request.transition_id,
        ),
    )
    with pytest.raises(ValueError, match="cycle"):
        evidence_state_verification._validate_history(
            journey.context.store,
            journey.context.domain,
            cycle_request,
            view,
        )
    unavailable_request = _unchecked(
        request,
        snapshot=_unchecked(
            parent,
            parent_revision=1,
            parent_transition_id="transition:missing",
        ),
    )
    with pytest.raises(ValueError, match="parent unavailable"):
        evidence_state_verification._validate_history(
            journey.context.store,
            journey.context.domain,
            unavailable_request,
            view,
        )
    invalid_genesis = _unchecked(
        request,
        snapshot=_unchecked(parent, parent_transition_id="not-genesis"),
    )
    with pytest.raises(ValueError, match="genesis Store lineage"):
        evidence_state_verification._validate_history(
            journey.context.store,
            journey.context.domain,
            invalid_genesis,
            view,
        )
    reordered = _unchecked(
        request,
        snapshot=_unchecked(
            parent,
            parent_revision=1,
            parent_transition_id="transition:other-parent",
        ),
    )

    class ReorderedHistoryReader:
        def load_commit_view_v2(self, *_args: object) -> object:
            return view

    with pytest.raises(ValueError, match="reordered"):
        evidence_state_verification._validate_history(
            ReorderedHistoryReader(),  # type: ignore[arg-type]
            journey.context.domain,
            reordered,
            view,
        )

    child_snapshot = _unchecked(
        parent,
        parent_revision=parent.revision,
        parent_transition_id=parent.transition_id,
        parent_snapshot_root=parent.snapshot_root,
    )
    child_request = _unchecked(request, snapshot=child_snapshot)
    loaded, failure = evidence_operations._load_parent(
        journey.context.store,
        journey.context.domain,
        child_request,
    )
    assert loaded is not None
    assert failure is None
    mismatched_child = _unchecked(
        child_request,
        snapshot=_unchecked(child_snapshot, parent_snapshot_root=_root("7")),
    )
    loaded, failure = evidence_operations._load_parent(
        journey.context.store,
        journey.context.domain,
        mismatched_child,
    )
    assert loaded is None
    assert failure is not None


def test_commit_gate_common_and_contract_failures_are_total() -> None:
    with pytest.raises(TypeError, match="exact non-empty string"):
        gate_common._require_text(None, "value")
    with pytest.raises(ValueError, match="UTF-8"):
        gate_common._require_text("\ud800", "value")
    with pytest.raises(TypeError, match="exact object"):
        gate_common._require_exact_mapping([], frozenset(), "value")
    with pytest.raises(ValueError, match="fields are invalid"):
        gate_common._require_exact_mapping({"bad": 1}, frozenset(), "value")
    with pytest.raises(ValueError, match="item bound"):
        gate_common._require_exact_array([1], "value", maximum=0)
    with pytest.raises(TypeError, match="exact array or tuple"):
        gate_common._canonical_texts(None, "value", allow_empty=False)
    with pytest.raises(ValueError, match="item bound"):
        gate_common._canonical_texts(
            ("a",),
            "value",
            allow_empty=True,
            maximum=0,
        )
    with pytest.raises(ValueError, match="unique values"):
        gate_common._canonical_texts((), "value", allow_empty=False)
    with pytest.raises(TypeError, match="exact array or tuple"):
        gate_common._canonical_roots(None, "value", allow_empty=False)
    with pytest.raises(ValueError, match="item bound"):
        gate_common._canonical_roots(
            (_root("1"),),
            "value",
            allow_empty=True,
            maximum=0,
        )
    with pytest.raises(ValueError, match="unique roots"):
        gate_common._canonical_roots((), "value", allow_empty=False)
    with pytest.raises(ValueError, match="mismatched"):
        gate_common._install_root(object(), "root", _root("2"), "kind", {})
    with pytest.raises(ValueError, match="not canonical wire"):
        gate_common._require_canonical_wire({}, {"value": 1}, "value")
    with pytest.raises(TypeError, match="assurance is invalid"):
        gate_common._require_profile(gate_fixture.PROFILE, "invalid", "value")
    with pytest.raises(ValueError, match="profile and assurance"):
        gate_common._require_profile(
            "pheroos-certified-commit-v1",
            CommitAssurance.ADVISORY,
            "value",
        )
    with pytest.raises(ValueError, match="canonical byte bound"):
        gate_common._canonical_size(
            "x" * (gate_common.MAX_COMMIT_GATE_SNAPSHOT_BYTES_V2 + 1),
            "value",
        )

    environment = gate_fixture._environment("scope:gate-totality:contracts")
    permission, _ = gate_fixture._prepare_permission(
        environment,
        label="permission",
    )
    stop, _ = gate_fixture._prepare_stop(environment, label="stop")
    dependencies = permission.snapshot.dependencies

    with pytest.raises(ValueError, match="dependency schema"):
        replace(dependencies, schema="unsupported", dependency_root="")
    with pytest.raises(ValueError, match="canonical version"):
        replace(
            dependencies,
            canonical_version="unsupported",
            dependency_root="",
        )
    with pytest.raises(ValueError, match="streams must be distinct"):
        replace(
            dependencies,
            risk_stream_ref=dependencies.replay_stream_ref,
            dependency_root="",
        )
    assert dependencies.canonical_bytes()
    assert dependencies.root() == dependencies.dependency_root
    noncanonical_dependencies = dependencies.to_dict()
    noncanonical_dependencies["dependency_root"] = ""
    with pytest.raises(ValueError, match="not canonical wire"):
        gate_dependency_contracts.CommitGateDependenciesV2.from_dict(
            noncanonical_dependencies
        )

    snapshot = permission.snapshot
    with pytest.raises(TypeError, match="exact dependencies"):
        gate_dependency_contracts.commit_gate_evaluation_context_root_v2(
            domain_root=snapshot.domain_root,
            scope_ref=snapshot.scope_ref,
            manifest_root=snapshot.manifest_root,
            commit_policy_root=snapshot.commit_policy_root,
            profile=snapshot.profile,
            assurance=snapshot.assurance,
            protocol_ref=snapshot.protocol_ref,
            run_ref=snapshot.run_ref,
            target_ref=snapshot.target_ref,
            observed_epoch=snapshot.observed_epoch,
            current_step=snapshot.current_step,
            dependencies=object(),
        )

    for current, genesis_root in (
        (
            permission.snapshot,
            gate_common.COMMIT_PERMISSION_GENESIS_SNAPSHOT_ROOT_V2,
        ),
        (
            stop.snapshot,
            gate_common.COMMIT_STOP_GENESIS_SNAPSHOT_ROOT_V2,
        ),
    ):

        def validate(candidate: object) -> None:
            gate_contract_support._validate_common_snapshot(
                candidate,
                expected_policy_root=current.policy_root,
                expected_stream_ref=current.stream_ref,
                expected_transition_id=current.transition_id,
                genesis_snapshot_root=genesis_root,
            )

        for changes, error in (
            ({"canonical_version": "unsupported"}, ValueError),
            ({"dependencies": object()}, TypeError),
            ({"issued_at_step": current.current_step + 1}, ValueError),
            ({"parent_revision": 2}, ValueError),
            ({"parent_transition_id": "invalid-parent"}, ValueError),
            ({"policy_root": _root("3")}, ValueError),
            ({"stream_ref": "invalid-stream"}, ValueError),
            ({"evaluation_context_root": _root("4")}, ValueError),
        ):
            with pytest.raises(error):
                validate(_unchecked(current, **changes))

    successor, _ = gate_fixture._prepare_permission(
        environment,
        label="successor",
        parent=permission.snapshot,
    )
    with pytest.raises(ValueError, match="cannot use genesis transition"):
        gate_contract_support._validate_common_snapshot(
            _unchecked(successor.snapshot, parent_transition_id="genesis"),
            expected_policy_root=successor.snapshot.policy_root,
            expected_stream_ref=successor.snapshot.stream_ref,
            expected_transition_id=successor.snapshot.transition_id,
            genesis_snapshot_root=(
                gate_common.COMMIT_PERMISSION_GENESIS_SNAPSHOT_ROOT_V2
            ),
        )
    with pytest.raises(ValueError, match="fixed stream binding"):
        gate_contract_support._validate_successor_common(
            _unchecked(successor.snapshot, domain_root=_root("5")),
            permission.snapshot,
        )
    with pytest.raises(ValueError, match="continuity"):
        gate_contract_support._validate_successor_common(
            _unchecked(successor.snapshot, revision=9),
            permission.snapshot,
        )


def test_commit_gate_permission_and_stop_wire_failures_are_total() -> None:
    environment = gate_fixture._environment("scope:gate-totality:wire")
    permission, _ = gate_fixture._prepare_permission(
        environment,
        label="permission",
    )
    stop, _ = gate_fixture._prepare_stop(environment, label="stop")

    for changes, error in (
        ({"schema": "unsupported"}, ValueError),
        ({"state_schema": "unsupported"}, ValueError),
        ({"assurance": "invalid"}, TypeError),
        ({"claims_root": _root("6")}, ValueError),
    ):
        with pytest.raises(error):
            replace(permission.snapshot, snapshot_root="", **changes)
    assert permission.snapshot.canonical_bytes()
    assert permission.snapshot.root() == permission.snapshot.snapshot_root

    payload = permission.snapshot.to_dict()
    payload["assurance"] = "unsupported"
    with pytest.raises(ValueError, match="assurance is unsupported"):
        gate_permission_contracts.CommitPermissionSnapshotV2.from_dict(payload)

    for changes, error in (
        ({"schema": "unsupported"}, ValueError),
        ({"canonical_version": "unsupported"}, ValueError),
        ({"snapshot": object()}, TypeError),
        ({"scope_ref": "scope:other"}, ValueError),
    ):
        with pytest.raises(error):
            replace(permission, request_root="", **changes)
    assert permission.canonical_bytes()
    assert permission.root() == permission.request_root

    for changes, error in (
        ({"schema": "unsupported"}, ValueError),
        ({"state_schema": "unsupported"}, ValueError),
        ({"assurance": "invalid"}, TypeError),
        ({"blocked": True, "reason_codes": ()}, ValueError),
        ({"reason_root": _root("7")}, ValueError),
    ):
        with pytest.raises(error):
            replace(stop.snapshot, snapshot_root="", **changes)
    assert stop.snapshot.canonical_bytes()
    assert stop.snapshot.root() == stop.snapshot.snapshot_root

    payload = stop.snapshot.to_dict()
    payload["assurance"] = "unsupported"
    with pytest.raises(ValueError, match="assurance is unsupported"):
        gate_stop_contracts.CommitStopSnapshotV2.from_dict(payload)

    for changes, error in (
        ({"schema": "unsupported"}, ValueError),
        ({"canonical_version": "unsupported"}, ValueError),
        ({"snapshot": object()}, TypeError),
        ({"scope_ref": "scope:other"}, ValueError),
    ):
        with pytest.raises(error):
            replace(stop, request_root="", **changes)
    assert stop.canonical_bytes()
    assert stop.root() == stop.request_root


def test_commit_gate_source_proofs_fail_closed_under_tampering() -> None:
    environment = gate_fixture._environment("scope:gate-totality:sources")
    permission, permission_source = gate_fixture._prepare_permission(
        environment,
        label="permission",
    )
    stop, stop_source = gate_fixture._prepare_stop(
        environment,
        label="stop",
    )

    for source in (permission_source, stop_source):
        assert source.context_root.startswith("sha256:")
        assert "redacted" in repr(source)
        with pytest.raises(AttributeError, match="immutable"):
            source.extra = object()
        with pytest.raises(TypeError, match="not portable"):
            source.__reduce__()
        with pytest.raises(TypeError, match="not portable"):
            source.__getstate__()
        with pytest.raises(TypeError, match="material is invalid"):
            _ = _opaque_clone(source, _material=object()).context_root

    for source_type in (
        gate_permission_source.VerifiedCommitPermissionSourceV2,
        gate_stop_source.VerifiedCommitStopSourceV2,
    ):
        with pytest.raises(TypeError, match="is final"):
            type("ForbiddenGateSourceSubclass", (source_type,), {})

    context_args = {
        "domain_root": environment.domain.domain_root,
        "scope_ref": environment.domain.scope_ref,
        "profile": gate_fixture.PROFILE,
        "run_ref": gate_fixture.RUN_REF,
        "target_ref": gate_fixture.TARGET,
        "observed_epoch": gate_fixture.GATE_EPOCH,
        "request_ref": "request:gate:totality",
        "current_step": gate_fixture.GATE_STEP,
        "mutation_issuer_ref": environment.grant.issuer_ref,
    }
    with pytest.raises(TypeError, match="exact ScopedProtocolManifestV2"):
        gate_source_common._validated_gate_context_v2(
            manifest=object(),
            **context_args,
        )
    with pytest.raises(ValueError, match="no collective commit policy"):
        gate_source_common._validated_gate_context_v2(
            manifest=replace(
                environment.manifest,
                collective_commit_policy=None,
            ),
            **context_args,
        )
    with pytest.raises(TypeError, match="dependencies are invalid"):
        gate_source_common._dependency_preconditions_v2(object())
    with pytest.raises(ValueError, match="preconditions are mismatched"):
        gate_source_common._issue_gate_source_v2(
            gate_permission_source.VerifiedCommitPermissionSourceV2,
            kind="permission",
            request=permission,
            request_root=permission.request_root,
            evaluation_context_root=permission.snapshot.evaluation_context_root,
            dependencies=permission.snapshot.dependencies,
            manifest=environment.manifest,
            preconditions=(),
        )
    with pytest.raises(TypeError, match="wrong exact type"):
        gate_source_common._verified_gate_source_fields_v2(
            object(),
            expected_type=(gate_permission_source.VerifiedCommitPermissionSourceV2),
            expected_kind="permission",
            expected_request_type=(gate_permission_contracts.CommitPermissionRequestV2),
        )
    incomplete = object.__new__(gate_permission_source.VerifiedCommitPermissionSourceV2)
    with pytest.raises(TypeError, match="source is incomplete"):
        gate_source_common._verified_gate_source_fields_v2(
            incomplete,
            expected_type=(gate_permission_source.VerifiedCommitPermissionSourceV2),
            expected_kind="permission",
            expected_request_type=(gate_permission_contracts.CommitPermissionRequestV2),
        )
    with pytest.raises(TypeError, match="material is invalid"):
        gate_source_common._verified_gate_source_fields_v2(
            _opaque_clone(permission_source, _material=object()),
            expected_type=(gate_permission_source.VerifiedCommitPermissionSourceV2),
            expected_kind="permission",
            expected_request_type=(gate_permission_contracts.CommitPermissionRequestV2),
        )

    with pytest.raises(TypeError, match="exact request"):
        gate_permission_source.verify_commit_permission_request_source_v2(
            object(),
            source=permission_source,
            committed_parent_snapshot=None,
        )
    with pytest.raises(TypeError, match="exact request"):
        gate_stop_source.verify_commit_stop_request_source_v2(
            object(),
            source=stop_source,
            committed_parent_snapshot=None,
        )

    other_permission, _ = gate_fixture._prepare_permission(
        environment,
        label="other-permission",
    )
    other_stop, _ = gate_fixture._prepare_stop(
        environment,
        label="other-stop",
    )
    with pytest.raises(ValueError, match="source request is mismatched"):
        gate_permission_source.verify_commit_permission_request_source_v2(
            other_permission,
            source=permission_source,
            committed_parent_snapshot=None,
        )
    with pytest.raises(ValueError, match="source request is mismatched"):
        gate_stop_source.verify_commit_stop_request_source_v2(
            other_stop,
            source=stop_source,
            committed_parent_snapshot=None,
        )

    other_manifest = replace(
        environment.manifest,
        extensions={"gate-totality": "other"},
    )
    with pytest.raises(ValueError, match="manifest context is mismatched"):
        gate_permission_source.verify_commit_permission_request_source_v2(
            permission,
            source=_opaque_clone(
                permission_source,
                _manifest=other_manifest,
            ),
            committed_parent_snapshot=None,
        )
    with pytest.raises(ValueError, match="manifest context is mismatched"):
        gate_stop_source.verify_commit_stop_request_source_v2(
            stop,
            source=_opaque_clone(stop_source, _manifest=other_manifest),
            committed_parent_snapshot=None,
        )

    permission_successor, permission_successor_source = (
        gate_fixture._prepare_permission(
            environment,
            label="permission-successor",
            parent=permission.snapshot,
        )
    )
    stop_successor, stop_successor_source = gate_fixture._prepare_stop(
        environment,
        label="stop-successor",
        parent=stop.snapshot,
    )
    with pytest.raises(ValueError, match="source parent is missing"):
        gate_permission_source.verify_commit_permission_request_source_v2(
            permission_successor,
            source=permission_successor_source,
            committed_parent_snapshot=None,
        )
    with pytest.raises(ValueError, match="source parent is missing"):
        gate_stop_source.verify_commit_stop_request_source_v2(
            stop_successor,
            source=stop_successor_source,
            committed_parent_snapshot=None,
        )
    gate_permission_source.verify_commit_permission_request_source_v2(
        permission_successor,
        source=permission_successor_source,
        committed_parent_snapshot=permission.snapshot,
    )
    gate_stop_source.verify_commit_stop_request_source_v2(
        stop_successor,
        source=stop_successor_source,
        committed_parent_snapshot=stop.snapshot,
    )

    for request, source, verifier in (
        (
            permission,
            permission_source,
            gate_permission_source.verify_commit_permission_request_source_v2,
        ),
        (
            stop,
            stop_source,
            gate_stop_source.verify_commit_stop_request_source_v2,
        ),
    ):
        material = object.__getattribute__(source, "_material")
        bad_source = _opaque_clone(
            source,
            _material=replace(
                material,
                source_context_root=_root("8"),
            ),
        )
        with pytest.raises(ValueError, match="source proof is mismatched"):
            verifier(
                request,
                source=bad_source,
                committed_parent_snapshot=None,
            )

    with pytest.raises(TypeError, match="parent must be exact"):
        gate_permission_source._permission_parent(object())
    with pytest.raises(TypeError, match="parent must be exact"):
        gate_stop_source._stop_parent(object())
    assert gate_permission_source._permission_parent(permission.snapshot)[0] == 1
    assert gate_stop_source._stop_parent(stop.snapshot)[0] == 1


def test_commit_gate_dependency_source_handles_and_context_are_total() -> None:
    class Reader:
        def __init__(self, result: object) -> None:
            self.result = result

        def load_head_v2(self, *_args: object) -> object:
            if isinstance(self.result, BaseException):
                raise self.result
            return self.result

        def load_state_v2(self, *_args: object) -> dict[str, object]:
            return {}

        def load_commit_view_v2(
            self,
            *_args: object,
            **_kwargs: object,
        ) -> object:
            raise KeyError("unused")

    environment = gate_fixture._environment(
        "scope:gate-totality:dependencies",
    )
    for function in (
        gate_dependency_source._current_replay,
        gate_dependency_source._current_risk,
        gate_dependency_source._current_membership,
        gate_dependency_source._current_support,
    ):
        with pytest.raises(TypeError):
            function(object())

    state = environment.replay_state
    request = object.__getattribute__(state, "_request")
    snapshot = state.snapshot
    arguments = {
        "expected_request_type": type(request),
        "expected_revision": snapshot.revision,
        "expected_transition_id": snapshot.transition_id,
    }

    with pytest.raises(session_contracts.GovernanceAuthorityBindingErrorV2):
        gate_dependency_source._current_head_from_handle(
            object.__new__(type(state)),
            **arguments,
        )
    with pytest.raises(session_contracts.GovernanceAuthorityBindingErrorV2):
        gate_dependency_source._current_head_from_handle(
            _opaque_clone(state, _domain=object()),
            **arguments,
        )
    with pytest.raises(TypeError, match="StateReader"):
        gate_dependency_source._current_head_from_handle(
            _opaque_clone(state, _reader=object()),
            **arguments,
        )
    with pytest.raises(session_contracts.GovernanceAuthorityBindingErrorV2):
        gate_dependency_source._current_head_from_handle(
            _opaque_clone(state, _reader=Reader(KeyError("missing"))),
            **arguments,
        )
    with pytest.raises(session_contracts.GovernanceAuthorityBindingErrorV2):
        gate_dependency_source._current_head_from_handle(
            _opaque_clone(state, _reader=Reader(object())),
            **arguments,
        )
    with pytest.raises(session_contracts.GovernanceAuthorityBindingErrorV2):
        gate_dependency_source._current_head_from_handle(
            _opaque_clone(
                state,
                _reader=Reader(
                    GovernanceHeadV2.genesis(
                        environment.domain,
                        "other-stream",
                    )
                ),
            ),
            **arguments,
        )
    current_head = environment.store.load_head_v2(
        request.scope_ref,
        request.stream_ref,
    )
    with pytest.raises(session_contracts.GovernanceAuthorityBindingErrorV2):
        gate_dependency_source._current_head_from_handle(
            _opaque_clone(state, _reader=Reader(current_head)),
            **{**arguments, "expected_revision": snapshot.revision + 1},
        )


def test_commit_gate_public_operations_and_opaque_states_are_total() -> None:
    permission = _gate_journey("opaque-permission", kind="permission")
    stop = _gate_journey("opaque-stop", kind="stop")

    with pytest.raises(TypeError, match="exact issuer capability"):
        gate_permission_operations.open_commit_permission_authority_session_v2(
            object(),  # type: ignore[arg-type]
            permission.request,
        )
    with pytest.raises(TypeError, match="exact issuer capability"):
        gate_stop_operations.open_commit_stop_authority_session_v2(
            object(),  # type: ignore[arg-type]
            stop.request,
        )
    permission_failure = gate_permission_operations.issue_commit_permission_v2(
        permission.request,
        source=permission.source,
        authority_session=object(),
    )
    stop_failure = gate_stop_operations.resolve_commit_stop_v2(
        stop.request,
        source=stop.source,
        authority_session=object(),
    )
    assert permission_failure.failure is not None
    assert stop_failure.failure is not None
    assert (
        gate_permission_operations.commit_permission_allows_v2(
            object(),
            current_step=6,
            candidate_ref=gate_fixture.TARGET,
        )
        is False
    )
    assert (
        gate_stop_operations.commit_stop_blocks_v2(
            object(),
            current_step=6,
        )
        is False
    )
    with pytest.raises(TypeError, match="exact request"):
        gate_permission_operations._require_request(object())
    with pytest.raises(TypeError, match="exact request"):
        gate_stop_operations._require_request(object())

    for journey, state_type, state_kind, representation in (
        (
            permission,
            gate_state_handle.VerifiedCommitPermissionStateV2,
            "permission",
            "<VerifiedCommitPermissionStateV2 redacted>",
        ),
        (
            stop,
            gate_state_handle.VerifiedCommitStopStateV2,
            "stop",
            "<VerifiedCommitStopStateV2 redacted>",
        ),
    ):
        state = journey.state
        with pytest.raises(TypeError, match="cannot be constructed"):
            state_type()
        with pytest.raises(TypeError, match="final"):
            type("ForbiddenGateStateSubclass", (state_type,), {})
        with pytest.raises(AttributeError, match="immutable"):
            state.anything = 1
        assert state.__copy__() is state
        assert state.__deepcopy__({}) is state
        with pytest.raises(TypeError, match="not portable"):
            state.__reduce__()
        with pytest.raises(TypeError, match="not portable"):
            state.__reduce_ex__(4)
        with pytest.raises(TypeError, match="not portable"):
            state.__getstate__()
        assert repr(state) == representation
        assert state.request_root == journey.request.request_root
        assert state.stream_ref == journey.request.stream_ref
        assert state.transition_id == journey.request.transition_id
        assert state.receipt_root
        assert state.position is GovernanceCommitPositionV2.CURRENT
        assert state.snapshot == journey.request.snapshot
        wrong_kind = "stop" if state_kind == "permission" else "permission"
        assert (
            gate_state_handle._state_is_current_v2(
                state,
                kind=wrong_kind,  # type: ignore[arg-type]
            )
            is False
        )
        with pytest.raises(Exception):
            gate_state_handle._require_current_state_v2(
                state,
                kind=wrong_kind,  # type: ignore[arg-type]
            )

    with pytest.raises(Exception, match="request_root"):
        gate_state_handle._verified_state_view_v2(
            _opaque_clone(permission.state, _request=object())
        )
    with pytest.raises(Exception):
        gate_state_handle._verified_state_view_v2(
            object.__new__(gate_state_handle.VerifiedCommitPermissionStateV2)
        )
    with pytest.raises(Exception):
        gate_state_handle._kind_for_state(object())
    with pytest.raises(TypeError, match="exact AuthorityDomain"):
        gate_state_handle._require_domain(object())
    with pytest.raises(TypeError, match="StateReader"):
        gate_state_handle._require_reader(object())
    with pytest.raises(Exception, match="request_root"):
        gate_state_handle._request_from_portable(object(), kind="permission")
    mismatched = _unchecked(
        permission.request,
        target_ref="target:other",
    )
    with pytest.raises(Exception, match="request_root"):
        gate_state_handle._load_verified_request_view_v2(
            permission.environment.store,
            permission.environment.domain,
            mismatched,
            expected_receipt_root=None,
            kind="permission",
        )


def test_commit_gate_state_records_and_read_sets_are_total() -> None:
    journey = _gate_journey("records", kind="permission")
    request = journey.request
    domain = journey.environment.domain
    view = journey.environment.store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    decoded, binding, source_root = gate_state_records._decode_committed_gate_view_v2(
        view,
        domain,
        kind="permission",
        reader=journey.environment.store,
    )
    assert decoded.to_dict() == request.to_dict()
    records = gate_state_records._gate_state_records_v2(
        request,
        binding,
        kind="permission",
        source_context_root=source_root,
    )

    with pytest.raises(TypeError, match="exact object"):
        gate_state_records._decode_state_records_v2(
            (),
            domain,
            kind="permission",
        )
    with pytest.raises(ValueError, match="fields"):
        gate_state_records._decode_state_records_v2(
            {},
            domain,
            kind="permission",
        )
    with pytest.raises(ValueError, match="domain"):
        gate_state_records._decode_state_records_v2(
            {**records, "scope_ref": "scope:other"},
            domain,
            kind="permission",
        )
    with pytest.raises(ValueError, match="payload"):
        gate_state_records._decode_state_records_v2(
            {**records, "request_root": _root("7")},
            domain,
            kind="permission",
        )
    with pytest.raises(ValueError, match="source_context_root"):
        gate_state_records._decode_state_records_v2(
            {**records, "source_context_root": _root("7")},
            domain,
            kind="permission",
        )
    with pytest.raises(ValueError, match="session binding fields"):
        gate_state_records._validate_session_binding(
            {},
            request,
            kind="permission",
        )
    with pytest.raises(ValueError, match="session binding is mismatched"):
        gate_state_records._validate_session_binding(
            {**binding, "request_ref": "permission:other"},
            request,
            kind="permission",
        )
    with pytest.raises(ValueError, match="grant binding"):
        gate_state_records._validate_session_binding(
            {**binding, "grant_ref": ""},
            request,
            kind="permission",
        )

    read_set = view.committed_transition.batch.read_set
    duplicate = _unchecked(
        read_set,
        entries=(*read_set.entries, read_set.entries[0]),
    )
    duplicate_batch = _unchecked(
        view.committed_transition.batch,
        read_set=duplicate,
    )
    duplicate_committed = _unchecked(
        view.committed_transition,
        batch=duplicate_batch,
    )
    with pytest.raises(ValueError, match="duplicate"):
        gate_state_records._validate_committed_read_set_v2(
            _unchecked(view, committed_transition=duplicate_committed),
            request,
            binding,
            kind="permission",
        )
    incomplete = _unchecked(read_set, entries=read_set.entries[:-1])
    incomplete_batch = _unchecked(
        view.committed_transition.batch,
        read_set=incomplete,
    )
    incomplete_committed = _unchecked(
        view.committed_transition,
        batch=incomplete_batch,
    )
    with pytest.raises(ValueError, match="read set"):
        gate_state_records._validate_committed_read_set_v2(
            _unchecked(view, committed_transition=incomplete_committed),
            request,
            binding,
            kind="permission",
        )
    with pytest.raises(ValueError, match="no committed transition"):
        gate_state_records._head_from_view_v2(
            _unchecked(view, committed_transition=None),
            domain,
        )
    unavailable = _unchecked(
        request,
        snapshot=_unchecked(
            request.snapshot,
            parent_revision=1,
            parent_transition_id="transition:missing",
        ),
    )

    class MissingHistoryReader:
        def load_commit_view_v2(self, *_args: object) -> object:
            raise KeyError("missing")

    with pytest.raises(ValueError, match="parent is unavailable"):
        gate_state_records._validate_gate_history_v2(
            MissingHistoryReader(),  # type: ignore[arg-type]
            domain,
            unavailable,
            kind="permission",
        )


def test_commit_gate_operation_helpers_map_parent_and_dependency_failures() -> None:
    environment = gate_fixture._environment(
        "scope:gate-totality:operation-helpers",
    )
    parent, parent_source = gate_fixture._prepare_permission(
        environment,
        label="parent",
    )
    parent_session = (
        gate_permission_operations.open_commit_permission_authority_session_v2(
            environment.capability(),
            parent,
        )
    )
    state_session = session_contracts._governance_authority_session_state_v2(
        parent_session
    )
    _, failure = gate_operations._validated_session_or_failure(
        parent_session,
        parent,
        kind="stop",
    )
    assert failure is not None

    successor, successor_source = gate_fixture._prepare_permission(
        environment,
        label="successor",
        parent=parent.snapshot,
    )
    successor_session = (
        gate_permission_operations.open_commit_permission_authority_session_v2(
            environment.capability(),
            successor,
        )
    )
    missing_parent = gate_operations._load_parent_v2(
        environment.store,
        environment.domain,
        successor,
        kind="permission",
    )
    assert isinstance(missing_parent, GovernanceCommitAttemptV2)
    attempt = gate_permission_operations.issue_commit_permission_v2(
        successor,
        source=successor_source,
        authority_session=successor_session,
    )
    assert attempt.failure is not None

    assert gate_operations._verify_source_v2(
        parent,
        parent_source,
        None,
        kind="permission",
    )[0]
    with pytest.raises(TypeError, match="stop request or parent"):
        gate_operations._verify_source_v2(
            parent,  # type: ignore[arg-type]
            gate_fixture._prepare_stop(environment, label="wrong")[1],
            None,
            kind="stop",
        )
    with pytest.raises(TypeError, match="permission request or parent"):
        gate_operations._verify_source_v2(
            parent,
            parent_source,
            gate_fixture._prepare_stop(environment, label="wrong-parent")[0].snapshot,
            kind="permission",
        )
    assert (
        gate_operations._committed_view_matches_request_v2(
            SimpleNamespace(),
            parent,
            state_session,
            kind="permission",
        )
        is False
    )

    preconditions = gate_source_common._dependency_preconditions_v2(
        parent.snapshot.dependencies
    )

    class HeadReader:
        state_store_version = GOVERNANCE_STATE_STORE_VERSION_V2

        def __init__(self, head: object) -> None:
            self.head = head

        def load_head_v2(self, *_args: object) -> object:
            if isinstance(self.head, BaseException):
                raise self.head
            return self.head

    for reader, expected_code in (
        (
            HeadReader(KeyError("missing")),
            AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        ),
        (
            HeadReader(object()),
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        ),
    ):
        loaded = gate_operations._load_dependency_heads_v2(
            reader,  # type: ignore[arg-type]
            environment.domain,
            parent,
            preconditions,
        )
        assert isinstance(loaded, GovernanceCommitAttemptV2)
        assert loaded.failure.code is expected_code

    actual_head = environment.store.load_head_v2(
        parent.scope_ref,
        preconditions[0].stream_ref,
    )
    cross_bound = replace(
        actual_head,
        scope_ref="scope:other",
        head_root="",
    )
    loaded = gate_operations._load_dependency_heads_v2(
        HeadReader(cross_bound),  # type: ignore[arg-type]
        environment.domain,
        parent,
        preconditions,
    )
    assert isinstance(loaded, GovernanceCommitAttemptV2)
    stale = replace(
        actual_head,
        transition_id="transition:other",
        head_root="",
    )
    loaded = gate_operations._load_dependency_heads_v2(
        HeadReader(stale),  # type: ignore[arg-type]
        environment.domain,
        parent,
        preconditions,
    )
    assert isinstance(loaded, GovernanceCommitAttemptV2)
    loaded = gate_operations._load_dependency_heads_v2(
        environment.store,
        environment.domain,
        parent,
        (),
    )
    assert isinstance(loaded, GovernanceCommitAttemptV2)


def test_commit_gate_operation_grant_owner_and_stale_state_are_total() -> None:
    environment = gate_fixture._environment(
        "scope:gate-totality:grant-owner",
    )
    request, source = gate_fixture._prepare_permission(
        environment,
        label="grant-owner",
    )
    session = gate_permission_operations.open_commit_permission_authority_session_v2(
        environment.capability(),
        request,
    )
    wrong_grant = gate_fixture._grant(
        environment.domain,
        issuer_ref="issuer:gate:other",
        grant_ref="grant:gate:other",
    )
    activated = gate_fixture.activate_governance_issuer_grant_v2(
        environment.store,
        environment.domain,
        wrong_grant,
        "transition:gate:grant:other",
        1,
    )
    assert activated.committed_transition is not None
    forged_for_open = _unchecked(
        request,
        snapshot=_unchecked(
            request.snapshot,
            mutation_issuer_ref=wrong_grant.issuer_ref,
        ),
    )
    wrong_session = (
        gate_permission_operations.open_commit_permission_authority_session_v2(
            environment.capability(grant=wrong_grant),
            forged_for_open,
        )
    )
    with pytest.raises(ValueError, match="not owned"):
        gate_permission_operations.open_commit_permission_authority_session_v2(
            environment.capability(grant=wrong_grant),
            request,
        )
    stop_request, _ = gate_fixture._prepare_stop(
        environment,
        label="wrong-owner-stop",
    )
    with pytest.raises(ValueError, match="not owned"):
        gate_stop_operations.open_commit_stop_authority_session_v2(
            environment.capability(grant=wrong_grant),
            stop_request,
        )
    denied = gate_permission_operations.issue_commit_permission_v2(
        request,
        source=source,
        authority_session=wrong_session,
    )
    assert denied.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    assert denied.failure.path == "/snapshot/mutation_issuer_ref"

    revoked = gate_fixture.revoke_governance_issuer_grant_v2(
        environment.store,
        environment.domain,
        environment.grant.grant_ref,
        "transition:gate:grant:revoke",
        gate_fixture.GATE_EPOCH,
    )
    assert revoked.committed_transition is not None
    grant_denied = gate_permission_operations.issue_commit_permission_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert (
        grant_denied.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED
    )

    journey = _gate_journey("stale-successor", kind="permission")
    successor, successor_source = gate_fixture._prepare_permission(
        journey.environment,
        label="stale-successor-2",
        parent=journey.request.snapshot,
    )
    successor_session = (
        gate_permission_operations.open_commit_permission_authority_session_v2(
            journey.environment.capability(),
            successor,
        )
    )
    successor_attempt = gate_permission_operations.issue_commit_permission_v2(
        successor,
        source=successor_source,
        authority_session=successor_session,
    )
    assert successor_attempt.committed_transition is not None
    with pytest.raises(Exception, match="position"):
        gate_state_handle._require_current_state_v2(
            journey.state,
            kind="permission",
        )
    wrong_domain = _unchecked(
        journey.environment.domain,
        domain_root=_root("7"),
    )
    with pytest.raises(Exception, match="domain_root"):
        gate_state_handle._rehydrate_gate_state_v2(
            journey.request.to_dict(),
            domain=wrong_domain,
            state_reader=journey.environment.store,
            kind="permission",
        )


def test_commit_gate_remaining_source_parent_and_history_defenses_are_total() -> None:
    environment = gate_fixture._environment(
        "scope:gate-totality:remaining-defenses",
    )
    request, source = gate_fixture._prepare_permission(
        environment,
        label="remaining",
    )
    policy = environment.manifest.collective_commit_policy
    assert policy is not None
    invalid_assurance = replace(policy, assurance="unsupported")
    with pytest.raises(ValueError, match="assurance is unsupported"):
        gate_source_common._validated_gate_context_v2(
            domain_root=environment.domain.domain_root,
            scope_ref=environment.domain.scope_ref,
            manifest=replace(
                environment.manifest,
                collective_commit_policy=invalid_assurance,
            ),
            profile=gate_fixture.PROFILE,
            run_ref=gate_fixture.RUN_REF,
            target_ref=gate_fixture.TARGET,
            observed_epoch=gate_fixture.GATE_EPOCH,
            request_ref=request.permission_ref,
            current_step=gate_fixture.GATE_STEP,
            mutation_issuer_ref=environment.grant.issuer_ref,
        )
    with pytest.raises(TypeError, match="permission source type"):
        gate_operations._verify_source_v2(
            request,
            object(),
            None,
            kind="permission",
        )

    session = gate_permission_operations.open_commit_permission_authority_session_v2(
        environment.capability(),
        request,
    )
    committed = gate_permission_operations.issue_commit_permission_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert committed.committed_transition is not None
    successor, _ = gate_fixture._prepare_permission(
        environment,
        label="remaining-successor",
        parent=request.snapshot,
    )

    class MissingParentStore:
        def load_commit_view_v2(self, *_args: object) -> object:
            raise KeyError("missing")

    missing = gate_operations._load_parent_v2(
        MissingParentStore(),  # type: ignore[arg-type]
        environment.domain,
        successor,
        kind="permission",
    )
    assert isinstance(missing, GovernanceCommitAttemptV2)

    finality_view = GovernanceCommitViewV2(
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        stream_ref=request.stream_ref,
        transition_id=request.transition_id,
        expected_receipt_root=None,
        disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        failure=_failure(AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE),
        committed_transition=None,
        position_observation=None,
        observed_revision=None,
        observed_head_root=None,
    )

    class FinalityParentStore:
        def load_commit_view_v2(self, *_args: object) -> object:
            return finality_view

    finality = gate_operations._load_parent_v2(
        FinalityParentStore(),  # type: ignore[arg-type]
        environment.domain,
        successor,
        kind="permission",
    )
    assert isinstance(finality, GovernanceCommitAttemptV2)

    mismatched = _unchecked(
        successor,
        snapshot=_unchecked(
            successor.snapshot,
            parent_snapshot_root=_root("7"),
        ),
    )
    failure = gate_operations._load_parent_v2(
        environment.store,
        environment.domain,
        mismatched,
        kind="permission",
    )
    assert isinstance(failure, GovernanceCommitAttemptV2)
    assert failure.failure.path == "/snapshot/parent_snapshot_root"

    cyclic_snapshot = _unchecked(
        request.snapshot,
        revision=2,
        parent_revision=1,
        parent_transition_id=request.transition_id,
        parent_snapshot_root=request.snapshot.snapshot_root,
        current_step=request.snapshot.current_step + 1,
    )
    cyclic_request = _unchecked(
        request,
        transition_id=request.transition_id,
        snapshot=cyclic_snapshot,
    )
    with pytest.raises(ValueError, match="cyclic or gapped"):
        gate_state_records._validate_gate_history_v2(
            environment.store,
            environment.domain,
            cyclic_request,
            kind="permission",
        )

    replay_view = environment.store.load_commit_view_v2(
        request.scope_ref,
        environment.replay_state.snapshot.stream_ref,
        environment.replay_state.snapshot.transition_id,
    )

    class WrongViewReader:
        def load_commit_view_v2(
            self,
            *_args: object,
            **_kwargs: object,
        ) -> object:
            return replay_view

    with pytest.raises(Exception, match="transition_id"):
        gate_state_handle._load_verified_request_view_v2(
            WrongViewReader(),  # type: ignore[arg-type]
            environment.domain,
            request,
            expected_receipt_root=None,
            kind="permission",
        )


def test_commit_gate_dependency_snapshot_context_failures_are_total() -> None:
    environment = gate_fixture._environment(
        "scope:gate-totality:dependency-context",
    )
    request, _ = gate_fixture._prepare_permission(
        environment,
        label="dependency-context",
    )
    snapshot = request.snapshot
    common = {
        "domain_root": snapshot.domain_root,
        "scope_ref": snapshot.scope_ref,
        "manifest_root": snapshot.manifest_root,
        "commit_policy_root": snapshot.commit_policy_root,
        "profile": snapshot.profile,
        "assurance": snapshot.assurance,
        "protocol_ref": snapshot.protocol_ref,
        "run_ref": snapshot.run_ref,
        "target_ref": snapshot.target_ref,
        "observed_epoch": snapshot.observed_epoch,
        "current_step": snapshot.current_step,
    }
    replay = environment.replay_state.snapshot
    risk = environment.risk_state.snapshot
    membership = environment.membership_state.snapshot

    with pytest.raises(Exception, match="context"):
        gate_dependency_source._validate_snapshot_context(
            "replay",
            _unchecked(replay, scope_ref="scope:other"),
            **common,
        )
    with pytest.raises(Exception, match="observed_epoch"):
        gate_dependency_source._validate_snapshot_context(
            "replay",
            _unchecked(replay, observed_epoch=snapshot.observed_epoch + 1),
            **common,
        )
    with pytest.raises(Exception, match="current_step"):
        gate_dependency_source._validate_snapshot_context(
            "replay",
            _unchecked(replay, current_step=snapshot.current_step + 1),
            **common,
        )
    with pytest.raises(Exception, match="risk_state/context"):
        gate_dependency_source._validate_snapshot_context(
            "risk",
            replay,
            **common,
        )
    expired_assessment = _unchecked(
        risk.assessment,
        expires_at_step=snapshot.current_step,
    )
    with pytest.raises(Exception, match="risk_state/expires_at_step"):
        gate_dependency_source._validate_snapshot_context(
            "risk",
            _unchecked(risk, assessment=expired_assessment),
            **common,
        )
    with pytest.raises(Exception, match="membership_state/expires_at_step"):
        gate_dependency_source._validate_snapshot_context(
            "membership",
            _unchecked(membership, expires_at_step=snapshot.current_step),
            **common,
        )


def test_legacy_authority_ledger_input_shapes_fail_closed() -> None:
    store = legacy_ledger.InMemoryGovernanceStateStore()
    with pytest.raises(legacy_ledger.GovernanceError, match="body must be a mapping"):
        store.claim_identity(_root("a"), _root("b"), ())  # type: ignore[arg-type]
    with pytest.raises(legacy_ledger.GovernanceError, match="batch is invalid"):
        store.atomic_commit(object())  # type: ignore[arg-type]
    with pytest.raises(legacy_ledger.GovernanceError, match="checkpoint must be"):
        legacy_ledger._checkpoint_domain(())  # type: ignore[arg-type]
    with pytest.raises(legacy_ledger.GovernanceError, match="fields"):
        legacy_ledger._checkpoint_domain({})
    with pytest.raises(legacy_ledger.GovernanceError, match="version"):
        legacy_ledger._checkpoint_domain(
            {
                "version": "unsupported",
                "scope_ref": "scope:a",
                "batches": [],
                "identity_claims": {},
                "heads": [],
                "checkpoint_root": _root("1"),
            }
        )


def test_legacy_authority_changed_checkpoint_replay_defenses_are_total() -> None:
    store = legacy_ledger.InMemoryGovernanceStateStore()
    store.atomic_commit(_legacy_prepared_batch(store, scope_ref=SCOPE_ALPHA))
    checkpoint = dict(store.checkpoint(SCOPE_ALPHA))
    checkpoint["heads"] = [
        *checkpoint["heads"],
        legacy_ledger.GovernanceHead.genesis(SCOPE_ALPHA, "other").to_dict(),
    ]
    body = {
        key: legacy_ledger._portable_json(checkpoint[key])
        for key in {
            "version",
            "scope_ref",
            "batches",
            "identity_claims",
            "heads",
        }
    }
    checkpoint["checkpoint_root"] = legacy_ledger._fingerprint(
        legacy_ledger._CHECKPOINT_SCHEMA,
        body,
    )
    with pytest.raises(legacy_ledger.GovernanceError, match="heads do not match"):
        legacy_ledger.InMemoryGovernanceStateStore.from_checkpoint(checkpoint)

    other_store = legacy_ledger.InMemoryGovernanceStateStore()
    other_batch = _legacy_prepared_batch(other_store, scope_ref=SCOPE_BETA)
    with pytest.raises(legacy_ledger.GovernanceError, match="crosses authority scope"):
        legacy_ledger._checkpoint_batches(
            [other_batch.to_dict()],
            domain=legacy_ledger.AuthorityDomain(SCOPE_ALPHA),
        )


def test_legacy_authority_conflicts_and_nonempty_rehydrate_are_total() -> None:
    identity_store = legacy_ledger.InMemoryGovernanceStateStore()
    identity_store.atomic_commit(
        _legacy_prepared_batch(
            identity_store,
            identity_claims={"identity:one": {"value": 1}},
        )
    )
    conflicting_claim = _legacy_prepared_batch(
        identity_store,
        transition_id="transition:identity-conflict",
        identity_claims={"identity:one": {"value": 2}},
    )
    with pytest.raises(legacy_ledger.GovernanceError, match="identity replay"):
        identity_store.atomic_commit(conflicting_claim)

    trace_store = legacy_ledger.InMemoryGovernanceStateStore()
    first = _legacy_prepared_batch(trace_store)
    trace_store.atomic_commit(first)
    second = _legacy_prepared_batch(
        trace_store,
        transition_id="transition:trace-conflict",
    )
    repeated_trace = {
        **second.trace_records[0],
        "trace_id": first.trace_records[0]["trace_id"],
    }
    with pytest.raises(legacy_ledger.GovernanceError, match="trace id"):
        trace_store.atomic_commit(
            legacy_ledger.GovernanceCommitBatch(
                second.transition,
                (repeated_trace,),
            )
        )

    checkpoint = trace_store.checkpoint(SCOPE_ALPHA)
    with pytest.raises(legacy_ledger.GovernanceError, match="already active"):
        trace_store.rehydrate(checkpoint)
    snapshot = trace_store.snapshot()
    with pytest.raises(legacy_ledger.GovernanceError, match="not empty"):
        trace_store.rehydrate_snapshot(snapshot)


def test_legacy_authority_checkpoint_collection_shapes_are_total() -> None:
    domain = legacy_ledger.AuthorityDomain(_root("a"))
    with pytest.raises(legacy_ledger.GovernanceError, match="batches must be"):
        legacy_ledger._checkpoint_batches((), domain=domain)
    with pytest.raises(legacy_ledger.GovernanceError, match="batch must be"):
        legacy_ledger._checkpoint_batches([()], domain=domain)
    with pytest.raises(legacy_ledger.GovernanceError, match="claims must be"):
        legacy_ledger._rehydrate_checkpoint_claims(
            legacy_ledger.InMemoryGovernanceStateStore(),
            (),
            scope_ref="scope:a",
        )
    with pytest.raises(legacy_ledger.GovernanceError, match="claim body"):
        legacy_ledger._rehydrate_checkpoint_claims(
            legacy_ledger.InMemoryGovernanceStateStore(),
            {"identity:a": ()},
            scope_ref="scope:a",
        )
    with pytest.raises(legacy_ledger.GovernanceError, match="heads must be"):
        legacy_ledger._checkpoint_heads(())
    with pytest.raises(legacy_ledger.GovernanceError, match="head must be"):
        legacy_ledger._checkpoint_heads([()])


def test_legacy_authority_snapshot_collection_shapes_are_total() -> None:
    with pytest.raises(legacy_ledger.GovernanceError, match="snapshot must be"):
        legacy_ledger._snapshot_collections(())  # type: ignore[arg-type]
    with pytest.raises(legacy_ledger.GovernanceError, match="fields"):
        legacy_ledger._snapshot_collections({})
    store = legacy_ledger.InMemoryGovernanceStateStore()
    snapshot = store.snapshot()
    with pytest.raises(legacy_ledger.GovernanceError, match="version"):
        legacy_ledger._snapshot_collections({**snapshot, "version": "unsupported"})
    with pytest.raises(legacy_ledger.GovernanceError, match="root"):
        legacy_ledger._snapshot_collections({**snapshot, "snapshot_root": _root("1")})
    wire = dict(snapshot)
    wire["domains"] = ()
    body = {
        key: legacy_ledger._portable_json(wire[key])
        for key in {"version", "domains", "tombstones"}
    }
    wire["snapshot_root"] = legacy_ledger._fingerprint(
        legacy_ledger._SNAPSHOT_SCHEMA,
        body,
    )
    with pytest.raises(legacy_ledger.GovernanceError, match="collections"):
        legacy_ledger._snapshot_collections(wire)
    with pytest.raises(legacy_ledger.GovernanceError, match="domain checkpoint"):
        legacy_ledger._rehydrate_snapshot_domains(store, [()])


def test_legacy_authority_tombstones_reject_tamper_and_duplicates() -> None:
    malformed = {"scope_ref": "scope:a"}
    with pytest.raises(legacy_ledger.GovernanceError, match="fields"):
        legacy_ledger._snapshot_tombstones([malformed], active_scopes=frozenset())
    final_root = _root("1")
    item = {
        "scope_ref": _root("a"),
        "final_root": final_root,
        "tombstone_root": _root("2"),
    }
    with pytest.raises(legacy_ledger.GovernanceError, match="root"):
        legacy_ledger._snapshot_tombstones([item], active_scopes=frozenset())
    valid = {
        **item,
        "tombstone_root": legacy_ledger._fingerprint(
            legacy_ledger._TOMBSTONE_SCHEMA,
            {"scope_ref": _root("a"), "final_root": final_root},
        ),
    }
    with pytest.raises(legacy_ledger.GovernanceError, match="duplicated"):
        legacy_ledger._snapshot_tombstones(
            [valid],
            active_scopes=frozenset({_root("a")}),
        )
