from __future__ import annotations

from collections.abc import Callable, Mapping
import copy
from dataclasses import dataclass, replace
from hashlib import sha256
import hmac
import json
import pickle
from typing import Any

import pytest

from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceDomainRetirementRequestV2,
    open_governance_authority_session_v2,
    retire_governance_domain_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitViewV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
    GovernanceTraceBatchV2,
)
from pheroos.governance._commit_certificate_v2.common import (
    _canonical_texts,
    _exact_mapping,
    _require_canonical_wire,
    _require_root,
    _require_text,
)
from pheroos.governance._commit_certificate_v2.decision_leaves import (
    _authority_leaves,
)
from pheroos.governance._commit_certificate_v2.events import (
    _commit_certificate_event_v2,
)
from pheroos.governance._commit_certificate_v2.operations import (
    _finality_failure,
    _load_dependency_heads,
    _load_parent,
)
from pheroos.governance._commit_certificate_v2.reducer import (
    _conflict_reason,
    _reduce_snapshot,
)
from pheroos.governance._commit_certificate_v2.source import (
    _body_from_decision,
    _validated_manifest,
    verify_commit_certificate_request_source_v2,
)
from pheroos.governance._commit_certificate_v2.state_handle import (
    _VerifiedCommitCertificateFinalityContextV2,
    _require_certificate_matches_decision,
    _require_reader,
    _require_upstreams_current,
    _verified_commit_certificate_finality_context_material_v2,
    _verified_commit_certificate_finality_context_v2,
    _verified_commit_certificate_state_material_v2,
)
from pheroos.governance._commit_certificate_v2.state_records import (
    _decode_committed_certificate_view_v2,
    _decode_state_records_v2,
    _head_from_view_v2,
    _load_bound_view,
    _validate_read_set_v2,
    _validate_session_binding_v2,
    _verify_decision_body_binding,
    _verify_historical_dependencies,
    _verify_parent_history,
    _verify_seal_inclusion,
)
from pheroos.governance._commit_decision_v2.seal_context import (
    _verified_commit_decision_seal_context_material_v2,
    _verified_commit_decision_seal_context_v2,
)
from pheroos.governance.commit_certificate_v2 import (
    CommitCertificateAuthorityLeafV2,
    CommitCertificateBodyV2,
    CommitCertificateIdentityBindingV2,
    CommitCertificateIssuerAttestationVerifierV2,
    CommitCertificateMutationKindV2,
    CommitCertificateRequestV2,
    CommitCertificateSnapshotV2,
    CommitCertificateStatusV2,
    PortableCommitCertificateV2,
    VerifiedCommitCertificateSourceV2,
    VerifiedCommitCertificateStateV2,
    advance_commit_certificate_v2,
    canonical_commit_certificate_authority_leaves_v2,
    commit_certificate_authority_leaf_set_root_v2,
    commit_certificate_state_is_current_v2,
    commit_certificate_stream_ref_v2,
    commit_certificate_transition_id_v2,
    open_commit_certificate_authority_session_v2,
    prepare_commit_certificate_v2,
    rehydrate_commit_certificate_state_v2,
    require_current_commit_certificate_state_v2,
    verified_commit_certificate_finality_input_v2,
    verify_portable_commit_certificate_v2,
)
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2
from pheroos.protocol.commit_models import CommitAssurance
from tests.governance._commit_certificate_v2_decision_support import (
    heartbeat_certified_decision,
    sealed_certified_decision,
)
from tests.governance._commit_certificate_v2_store_support import (
    _capability,
    _root,
    certified_context,
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
    enabled = True

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
        return self.enabled and hmac.compare_digest(
            attestation_ref,
            self.attestation_ref(issuer_ref, body_root),
        )


@dataclass(frozen=True, slots=True)
class _Fixture:
    context: Any
    decision_state: Any
    inputs: Any
    request: CommitCertificateRequestV2
    source: VerifiedCommitCertificateSourceV2


@pytest.fixture(scope="module")
def certificate_fixture() -> _Fixture:
    context = certified_context("scope:certificate-v2:public-semantics")
    decision_state, inputs = sealed_certified_decision(
        context,
        _root("claim:certificate:public-semantics"),
    )
    request, source = _prepared_certificate(
        context,
        decision_state,
        mutation_ref="mutation:certificate:public-semantics:initial",
    )
    return _Fixture(
        context=context,
        decision_state=decision_state,
        inputs=inputs,
        request=request,
        source=source,
    )


def _prepared_certificate(
    context: Any,
    decision_state: Any,
    *,
    mutation_ref: str,
    certificate_id: str = "certificate:public-semantics",
    envelope_nonce: str = "nonce:public-semantics",
    parent_state: object | None = None,
    verifier: _DigestVerifier | None = None,
) -> tuple[CommitCertificateRequestV2, VerifiedCommitCertificateSourceV2]:
    common = {
        "decision_state": decision_state,
        "manifest": context.manifest,
        "certificate_id": certificate_id,
        "issuer_ref": context.grant.issuer_ref,
        "issued_at_step": decision_state.snapshot.current_step,
        "provenance_ref": "urn:test:certificate:public-semantics",
        "envelope_nonce": envelope_nonce,
        "mutation_ref": mutation_ref,
        "parent_state": parent_state,
    }
    discovery, _ = prepare_commit_certificate_v2(
        trusted_verifier=_DiscoveryVerifier(),
        issuer_attestation_refs=("attestation:discovery",),
        **common,
    )
    trusted = _DigestVerifier() if verifier is None else verifier
    attestation = trusted.attestation_ref(
        context.grant.issuer_ref,
        discovery.certificate.body.body_root,
    )
    return prepare_commit_certificate_v2(
        trusted_verifier=trusted,
        issuer_attestation_refs=(attestation,),
        **common,
    )


def _restart_context(fixture: _Fixture) -> Any:
    store = ReferenceGovernanceStateStoreConformanceAdapterV2().restart_store_v2(
        fixture.context.store
    )
    return replace(fixture.context, store=store)


def _commit(
    context: Any,
    request: CommitCertificateRequestV2,
    source: object,
) -> GovernanceCommitAttemptV2:
    session = open_commit_certificate_authority_session_v2(
        _capability(context, request.observed_epoch),
        request,
    )
    return advance_commit_certificate_v2(
        request,
        source=source,
        authority_session=session,
    )


def _commit_and_rehydrate(
    fixture: _Fixture,
) -> tuple[Any, GovernanceCommitAttemptV2, VerifiedCommitCertificateStateV2]:
    context = _restart_context(fixture)
    attempt = _commit(context, fixture.request, fixture.source)
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    state = rehydrate_commit_certificate_state_v2(
        fixture.request,
        domain=context.domain,
        state_reader=context.store,
    )
    return context, attempt, state


class _ReaderProxy:
    def __init__(
        self,
        store: GovernanceStateStoreV2,
        *,
        head_hook: Callable[[str, str], GovernanceHeadV2] | None = None,
        view_hook: Callable[[str, str, str, str | None], GovernanceCommitViewV2]
        | None = None,
    ) -> None:
        self.store = store
        self.head_hook = head_hook
        self.view_hook = view_hook

    @property
    def state_store_version(self) -> str:
        return self.store.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        if self.head_hook is not None:
            return self.head_hook(scope_ref, stream_ref)
        return self.store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, object]:
        return self.store.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        if self.view_hook is not None:
            return self.view_hook(
                scope_ref,
                stream_ref,
                transition_id,
                expected_receipt_root,
            )
        return self.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )


class _StoreProxy(_ReaderProxy):
    def atomic_commit_v2(self, batch: Any) -> GovernanceCommitAttemptV2:
        return self.store.atomic_commit_v2(batch)


class _ProtocolExplodingStoreProxy(_StoreProxy):
    def __init__(self, store: GovernanceStateStoreV2) -> None:
        super().__init__(store)
        self.explode = False

    def __getattribute__(self, name: str) -> object:
        if name not in {"arm", "explode"} and object.__getattribute__(self, "explode"):
            raise RuntimeError("hostile StateStore protocol lookup")
        return object.__getattribute__(self, name)

    def arm(self) -> None:
        object.__setattr__(self, "explode", True)


class _ProtocolExplodingReader:
    def __getattribute__(self, name: str) -> object:
        raise RuntimeError(f"hostile StateReader protocol lookup: {name}")


def _binding_error(
    expected_code: AuthorityDiagnosticCodeV2,
    expected_path: str,
    operation: Callable[[], object],
) -> None:
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
        operation()
    assert caught.value.code is expected_code
    assert caught.value.path == expected_path


def _assert_failure(
    attempt: GovernanceCommitAttemptV2,
    *,
    disposition: GovernanceCommitDispositionV2,
    code: AuthorityDiagnosticCodeV2,
    path: str,
    stage: GovernanceFailureStageV2,
) -> None:
    assert attempt.disposition is disposition
    assert attempt.failure is not None
    assert attempt.failure.code is code
    assert attempt.failure.path == path
    assert attempt.failure.stage is stage
    assert attempt.committed_transition is None


def _snapshot_with(
    snapshot: CommitCertificateSnapshotV2,
    **changes: object,
) -> CommitCertificateSnapshotV2:
    return replace(
        snapshot,
        state_root="",
        history_root="",
        snapshot_root="",
        **changes,
    )


def _forged_source(
    source: VerifiedCommitCertificateSourceV2,
    **changes: object,
) -> VerifiedCommitCertificateSourceV2:
    forged = object.__new__(VerifiedCommitCertificateSourceV2)
    for name in VerifiedCommitCertificateSourceV2.__slots__:
        value = changes.get(name, object.__getattribute__(source, name))
        object.__setattr__(forged, name, value)
    return forged


def _unavailable_view(
    request: CommitCertificateRequestV2,
    expected_receipt_root: str | None,
) -> GovernanceCommitViewV2:
    return GovernanceCommitViewV2(
        domain_root=request.domain_root,
        scope_ref=request.scope_ref,
        stream_ref=request.stream_ref,
        transition_id=request.transition_id,
        expected_receipt_root=expected_receipt_root,
        disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
        failure=GovernanceFailureV2(
            code=AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
            path="/transition_id",
            stage=GovernanceFailureStageV2.FINALITY,
        ),
        committed_transition=None,
        position_observation=None,
        observed_revision=None,
        observed_head_root=None,
    )


def test_public_wire_round_trips_and_canonical_leaf_set(
    certificate_fixture: _Fixture,
) -> None:
    request = certificate_fixture.request
    certificate = request.certificate
    body = certificate.body
    leaves = tuple(reversed(body.authority_leaves))

    assert CommitCertificateRequestV2.from_dict(request.to_dict()) == request
    assert PortableCommitCertificateV2.from_dict(certificate.to_dict()) == certificate
    assert CommitCertificateBodyV2.from_dict(body.to_dict()) == body
    assert all(
        CommitCertificateAuthorityLeafV2.from_dict(leaf.to_dict()) == leaf
        for leaf in leaves
    )
    canonical = canonical_commit_certificate_authority_leaves_v2(leaves)
    assert canonical == body.authority_leaves
    assert commit_certificate_authority_leaf_set_root_v2(leaves) == (
        body.authority_leaf_set_root
    )
    assert (
        commit_certificate_stream_ref_v2(
            request.scope_ref,
            request.protocol_ref,
            request.run_ref,
            request.target_ref,
        )
        == request.stream_ref
    )
    assert (
        commit_certificate_transition_id_v2(
            request.stream_ref,
            request.mutation_ref,
        )
        == request.transition_id
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("expected_body_root", _root("wrong-body")),
        ("expected_target_ref", "target:wrong"),
        ("expected_candidate_ref", "candidate:wrong"),
        ("expected_claim_root", _root("wrong-claim")),
        ("expected_epoch", 999),
    ),
)
def test_portable_verifier_rejects_each_expected_binding_mismatch(
    certificate_fixture: _Fixture,
    field: str,
    value: object,
) -> None:
    certificate = certificate_fixture.request.certificate
    verifier = object.__getattribute__(
        certificate_fixture.source,
        "_trusted_verifier",
    )
    assert isinstance(verifier, CommitCertificateIssuerAttestationVerifierV2)
    assert not verify_portable_commit_certificate_v2(
        certificate.to_dict(),
        trusted_verifier=verifier,
        **{field: value},
    )


@pytest.mark.parametrize("accepted", (False, 1, "yes", None))
def test_portable_verifier_requires_exact_boolean_attestation_result(
    certificate_fixture: _Fixture,
    accepted: object,
) -> None:
    class _ResultVerifier:
        def verify_commit_certificate_attestation_v2(self, **_kwargs: object) -> object:
            return accepted

    assert not verify_portable_commit_certificate_v2(
        certificate_fixture.request.certificate,
        trusted_verifier=_ResultVerifier(),  # type: ignore[arg-type]
    )


def test_portable_verifier_is_total_over_wire_and_adapter_exceptions(
    certificate_fixture: _Fixture,
) -> None:
    class _ExplodingVerifier:
        def verify_commit_certificate_attestation_v2(self, **_kwargs: object) -> bool:
            raise ValueError("untrusted adapter failure")

    certificate = certificate_fixture.request.certificate
    malformed = certificate.to_dict()
    malformed["envelope_root"] = _root("forged-envelope")
    assert not verify_portable_commit_certificate_v2(
        malformed,
        trusted_verifier=_ExplodingVerifier(),
    )
    assert not verify_portable_commit_certificate_v2(
        certificate,
        trusted_verifier=_ExplodingVerifier(),
    )
    assert not verify_portable_commit_certificate_v2(
        certificate,
        trusted_verifier=object(),  # type: ignore[arg-type]
    )
    assert not verify_portable_commit_certificate_v2(
        certificate,
        trusted_verifier=_ExplodingVerifier(),
        expected_epoch=True,
    )


def test_portable_envelope_and_request_wire_are_exact_and_root_bound(
    certificate_fixture: _Fixture,
) -> None:
    certificate = certificate_fixture.request.certificate
    with pytest.raises(ValueError, match="schema is unsupported"):
        replace(certificate, schema="unsupported", envelope_root="")
    with pytest.raises(TypeError, match="exact body"):
        replace(certificate, body=object(), envelope_root="")  # type: ignore[arg-type]

    wrong_refs = certificate.to_dict()
    wrong_refs["issuer_attestation_refs"] = ("attestation:tuple",)
    with pytest.raises(TypeError, match="exact wire array"):
        PortableCommitCertificateV2.from_dict(wrong_refs)

    wrong_root = certificate.to_dict()
    wrong_root["envelope_root"] = _root("wrong-envelope-root")
    with pytest.raises(ValueError, match="envelope_root is mismatched"):
        PortableCommitCertificateV2.from_dict(wrong_root)

    request = certificate_fixture.request
    with pytest.raises(ValueError, match="version is unsupported"):
        replace(request, schema="unsupported", request_root="")
    with pytest.raises(TypeError, match="exact envelope"):
        replace(request, certificate=object(), request_root="")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="stream_ref is mismatched"):
        replace(request, stream_ref="authority:wrong", request_root="")
    with pytest.raises(ValueError, match="transition_id is mismatched"):
        replace(request, transition_id="transition:wrong", request_root="")
    with pytest.raises(ValueError, match="genesis parent is mismatched"):
        replace(
            request,
            parent_snapshot_root=_root("wrong-parent"),
            request_root="",
        )
    cross_bound_body = replace(
        certificate.body,
        target_ref="target:cross-bound-request",
        body_root="",
    )
    cross_bound_certificate = replace(
        certificate,
        body=cross_bound_body,
        envelope_root="",
    )
    with pytest.raises(ValueError, match="request body is cross-bound"):
        replace(
            request,
            certificate=cross_bound_certificate,
            request_root="",
        )


def test_authority_leaf_contract_rejects_noncanonical_and_incomplete_sets(
    certificate_fixture: _Fixture,
) -> None:
    leaves = certificate_fixture.request.certificate.body.authority_leaves
    first = leaves[0]
    with pytest.raises(ValueError, match="schema is unsupported"):
        replace(first, schema="unsupported", leaf_root="")
    with pytest.raises(TypeError, match="role is invalid"):
        replace(first, role="risk", leaf_root="")  # type: ignore[arg-type]

    unsupported = first.to_dict()
    unsupported["role"] = "root"
    with pytest.raises(ValueError, match="role is unsupported"):
        CommitCertificateAuthorityLeafV2.from_dict(unsupported)

    with pytest.raises(TypeError, match="exact sequence"):
        canonical_commit_certificate_authority_leaves_v2(set(leaves))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="count is invalid"):
        canonical_commit_certificate_authority_leaves_v2(())
    with pytest.raises(TypeError, match="noncanonical"):
        canonical_commit_certificate_authority_leaves_v2(
            (*leaves[:-1], object())  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="unique"):
        canonical_commit_certificate_authority_leaves_v2(
            (
                *leaves[:-1],
                replace(
                    leaves[-1],
                    stream_ref=leaves[0].stream_ref,
                    leaf_root="",
                ),
            )
        )
    with pytest.raises(ValueError, match="incomplete"):
        canonical_commit_certificate_authority_leaves_v2(leaves[:-1])


def test_body_contract_rejects_version_algorithm_assurance_and_root_forgery(
    certificate_fixture: _Fixture,
) -> None:
    body = certificate_fixture.request.certificate.body
    with pytest.raises(ValueError, match="schema is unsupported"):
        replace(body, schema="unsupported", body_root="")
    with pytest.raises(ValueError, match="canonical version is unsupported"):
        replace(body, canonical_version="unsupported", body_root="")
    with pytest.raises(ValueError, match="hash algorithm is unsupported"):
        replace(body, hash_algorithm="sha512", body_root="")
    with pytest.raises(ValueError, match="assurance is unsupported"):
        replace(
            body,
            assurance=CommitAssurance.ADVISORY,
            body_root="",
        )
    with pytest.raises(ValueError, match="leaf set root is mismatched"):
        replace(
            body,
            authority_leaf_set_root=_root("wrong-leaf-set"),
            body_root="",
        )

    unsupported = body.to_dict()
    unsupported["assurance"] = "unknown"
    with pytest.raises(ValueError, match="assurance is unsupported"):
        CommitCertificateBodyV2.from_dict(unsupported)


def test_state_handle_is_opaque_immutable_redacted_and_live(
    certificate_fixture: _Fixture,
) -> None:
    context, attempt, state = _commit_and_rehydrate(certificate_fixture)
    assert attempt.committed_transition is not None
    assert type(state) is VerifiedCommitCertificateStateV2
    assert copy.copy(state) is state
    assert copy.deepcopy(state) is state
    assert repr(state) == "<VerifiedCommitCertificateStateV2 redacted>"
    assert state.request_root == certificate_fixture.request.request_root
    assert state.stream_ref == certificate_fixture.request.stream_ref
    assert state.transition_id == certificate_fixture.request.transition_id
    assert state.receipt_root == attempt.committed_transition.receipt.receipt_root
    assert state.position is GovernanceCommitPositionV2.CURRENT
    assert (
        state.snapshot.to_dict()
        == require_current_commit_certificate_state_v2(state).to_dict()
    )
    assert commit_certificate_state_is_current_v2(state)

    with pytest.raises(TypeError, match="cannot be constructed"):
        VerifiedCommitCertificateStateV2()
    with pytest.raises(TypeError, match="is final"):
        type("ForgedCertificateState", (VerifiedCommitCertificateStateV2,), {})
    with pytest.raises(AttributeError, match="is immutable"):
        state._reader = context.store  # type: ignore[misc]
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(state)


def test_state_currentness_tracks_successor_and_restart(
    certificate_fixture: _Fixture,
) -> None:
    context, first_attempt, first_state = _commit_and_rehydrate(certificate_fixture)
    second, second_source = _prepared_certificate(
        context,
        certificate_fixture.decision_state,
        mutation_ref="mutation:certificate:public-semantics:retry",
        certificate_id="certificate:public-semantics:retry",
        envelope_nonce="nonce:public-semantics:retry",
        parent_state=first_state,
    )
    second_attempt = _commit(context, second, second_source)
    assert second_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert not commit_certificate_state_is_current_v2(first_state)
    assert first_state.position is GovernanceCommitPositionV2.SUPERSEDED
    _binding_error(
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        "/position",
        lambda: require_current_commit_certificate_state_v2(first_state),
    )

    second_state = rehydrate_commit_certificate_state_v2(
        second.to_dict(),
        domain=context.domain,
        state_reader=context.store,
    )
    assert second_state.snapshot.revision == 2
    assert second_state.snapshot.mutation_kind is (
        CommitCertificateMutationKindV2.SEMANTIC_RETRY
    )
    assert second_state.snapshot.status is CommitCertificateStatusV2.VERIFIED

    restarted = ReferenceGovernanceStateStoreConformanceAdapterV2().restart_store_v2(
        context.store
    )
    restarted_state = rehydrate_commit_certificate_state_v2(
        second,
        domain=context.domain,
        state_reader=restarted,
    )
    assert commit_certificate_state_is_current_v2(restarted_state)
    assert restarted_state.snapshot.to_dict() == second_state.snapshot.to_dict()
    assert first_attempt.committed_transition is not None


def test_rehydrate_rejects_scope_malformed_payload_and_reader_forgery(
    certificate_fixture: _Fixture,
) -> None:
    context, _, _ = _commit_and_rehydrate(certificate_fixture)
    request = certificate_fixture.request
    other_domain = replace(
        context.domain,
        scope_ref="scope:wrong",
        domain_root="",
    )
    _binding_error(
        AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH,
        "/domain_root",
        lambda: rehydrate_commit_certificate_state_v2(
            request,
            domain=other_domain,
            state_reader=context.store,
        ),
    )
    _binding_error(
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/request_root",
        lambda: rehydrate_commit_certificate_state_v2(
            {"request_root": request.request_root},
            domain=context.domain,
            state_reader=context.store,
        ),
    )
    with pytest.raises(TypeError, match="exact authority domain"):
        rehydrate_commit_certificate_state_v2(
            request,
            domain=object(),  # type: ignore[arg-type]
            state_reader=context.store,
        )
    with pytest.raises(TypeError, match="StateReader v2"):
        rehydrate_commit_certificate_state_v2(
            request,
            domain=context.domain,
            state_reader=object(),  # type: ignore[arg-type]
        )


def test_rehydrate_normalizes_store_lookup_and_decode_failures(
    certificate_fixture: _Fixture,
) -> None:
    context, _, _ = _commit_and_rehydrate(certificate_fixture)
    request = certificate_fixture.request
    decision = certificate_fixture.decision_state.snapshot

    def missing_view(
        _scope: str,
        _stream: str,
        _transition: str,
        _receipt: str | None,
    ) -> GovernanceCommitViewV2:
        raise KeyError("missing")

    missing = _ReaderProxy(context.store, view_hook=missing_view)
    _binding_error(
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
        "/transition_id",
        lambda: rehydrate_commit_certificate_state_v2(
            request,
            domain=context.domain,
            state_reader=missing,
        ),
    )

    unavailable = _ReaderProxy(
        context.store,
        view_hook=lambda _s, _r, _t, receipt: _unavailable_view(request, receipt),
    )
    _binding_error(
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
        "/transition_id",
        lambda: rehydrate_commit_certificate_state_v2(
            request,
            domain=context.domain,
            state_reader=unavailable,
        ),
    )

    def decision_view(
        _scope: str,
        stream_ref: str,
        _transition: str,
        _receipt: str | None,
    ) -> GovernanceCommitViewV2:
        if stream_ref == request.stream_ref:
            return context.store.load_commit_view_v2(
                request.scope_ref,
                decision.stream_ref,
                decision.transition_id,
            )
        return context.store.load_commit_view_v2(
            request.scope_ref,
            stream_ref,
            _transition,
            expected_receipt_root=_receipt,
        )

    corrupt = _ReaderProxy(context.store, view_hook=decision_view)
    _binding_error(
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
        "/transition_id",
        lambda: rehydrate_commit_certificate_state_v2(
            request,
            domain=context.domain,
            state_reader=corrupt,
        ),
    )


def test_state_handle_forgery_is_total_and_never_current(
    certificate_fixture: _Fixture,
) -> None:
    context, _, _ = _commit_and_rehydrate(certificate_fixture)
    incomplete = object.__new__(VerifiedCommitCertificateStateV2)
    assert not commit_certificate_state_is_current_v2(incomplete)
    _binding_error(
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "",
        lambda: require_current_commit_certificate_state_v2(incomplete),
    )

    invalid_request = object.__new__(VerifiedCommitCertificateStateV2)
    object.__setattr__(invalid_request, "_reader", context.store)
    object.__setattr__(invalid_request, "_domain", context.domain)
    object.__setattr__(invalid_request, "_request", object())
    object.__setattr__(invalid_request, "_receipt_root", _root("receipt"))
    _binding_error(
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/request_root",
        lambda: require_current_commit_certificate_state_v2(invalid_request),
    )

    invalid_domain = object.__new__(VerifiedCommitCertificateStateV2)
    object.__setattr__(invalid_domain, "_reader", context.store)
    object.__setattr__(invalid_domain, "_domain", object())
    object.__setattr__(invalid_domain, "_request", certificate_fixture.request)
    object.__setattr__(invalid_domain, "_receipt_root", _root("receipt"))
    with pytest.raises(TypeError, match="exact authority domain"):
        require_current_commit_certificate_state_v2(invalid_domain)

    invalid_reader = object.__new__(VerifiedCommitCertificateStateV2)
    object.__setattr__(invalid_reader, "_reader", object())
    object.__setattr__(invalid_reader, "_domain", context.domain)
    object.__setattr__(invalid_reader, "_request", certificate_fixture.request)
    object.__setattr__(invalid_reader, "_receipt_root", _root("receipt"))
    with pytest.raises(TypeError, match="StateReader v2"):
        require_current_commit_certificate_state_v2(invalid_reader)


def test_rehydrate_detects_cross_transition_substitution(
    certificate_fixture: _Fixture,
) -> None:
    context, _, _ = _commit_and_rehydrate(certificate_fixture)
    alternate_context = _restart_context(certificate_fixture)
    alternate, alternate_source = _prepared_certificate(
        alternate_context,
        certificate_fixture.decision_state,
        mutation_ref="mutation:certificate:public-semantics:substitution",
        certificate_id="certificate:public-semantics:substitution",
        envelope_nonce="nonce:public-semantics:substitution",
    )
    assert _commit(
        alternate_context,
        alternate,
        alternate_source,
    ).disposition is (GovernanceCommitDispositionV2.COMMITTED)

    def substitute(
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        expected_receipt_root: str | None,
    ) -> GovernanceCommitViewV2:
        if (
            stream_ref == certificate_fixture.request.stream_ref
            and transition_id == certificate_fixture.request.transition_id
        ):
            return alternate_context.store.load_commit_view_v2(
                scope_ref,
                alternate.stream_ref,
                alternate.transition_id,
            )
        return context.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    reader = _ReaderProxy(context.store, view_hook=substitute)
    _binding_error(
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/request_root",
        lambda: rehydrate_commit_certificate_state_v2(
            certificate_fixture.request,
            domain=context.domain,
            state_reader=reader,
        ),
    )


def test_source_handle_is_opaque_and_revalidated_at_commit(
    certificate_fixture: _Fixture,
) -> None:
    source = certificate_fixture.source
    assert copy.copy(source) is source
    assert copy.deepcopy(source) is source
    assert repr(source) == "<VerifiedCommitCertificateSourceV2 redacted>"
    with pytest.raises(TypeError, match="cannot be constructed"):
        VerifiedCommitCertificateSourceV2()
    with pytest.raises(TypeError, match="is final"):
        type("ForgedCertificateSource", (VerifiedCommitCertificateSourceV2,), {})
    with pytest.raises(AttributeError, match="is immutable"):
        source._request = certificate_fixture.request  # type: ignore[misc]
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(source)

    context = _restart_context(certificate_fixture)
    incomplete = object.__new__(VerifiedCommitCertificateSourceV2)
    attempt = _commit(context, certificate_fixture.request, incomplete)
    _assert_failure(
        attempt,
        disposition=GovernanceCommitDispositionV2.INVALID,
        code=AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        path="/source",
        stage=GovernanceFailureStageV2.VALIDATION,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("_request", object()),
        ("_snapshot", object()),
        ("_manifest", object()),
        ("_decision_state", object()),
        ("_trusted_verifier", object()),
        ("_source_context_root", object()),
    ),
)
def test_each_forged_source_component_fails_closed(
    certificate_fixture: _Fixture,
    field: str,
    value: object,
) -> None:
    context = _restart_context(certificate_fixture)
    forged = _forged_source(certificate_fixture.source, **{field: value})
    _assert_failure(
        _commit(context, certificate_fixture.request, forged),
        disposition=GovernanceCommitDispositionV2.INVALID,
        code=AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        path="/source",
        stage=GovernanceFailureStageV2.VALIDATION,
    )


def test_source_trust_context_and_snapshot_are_rechecked(
    certificate_fixture: _Fixture,
) -> None:
    context = _restart_context(certificate_fixture)
    verifier = _DigestVerifier()
    request, source = _prepared_certificate(
        context,
        certificate_fixture.decision_state,
        mutation_ref="mutation:certificate:public-semantics:mutable-trust",
        verifier=verifier,
    )
    verifier.enabled = False
    _assert_failure(
        _commit(context, request, source),
        disposition=GovernanceCommitDispositionV2.INVALID,
        code=AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        path="/source",
        stage=GovernanceFailureStageV2.VALIDATION,
    )

    context = _restart_context(certificate_fixture)
    wrong_context = _forged_source(
        certificate_fixture.source,
        _source_context_root=_root("forged-source-context"),
    )
    _assert_failure(
        _commit(context, certificate_fixture.request, wrong_context),
        disposition=GovernanceCommitDispositionV2.INVALID,
        code=AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        path="/source",
        stage=GovernanceFailureStageV2.VALIDATION,
    )

    context = _restart_context(certificate_fixture)
    snapshot = object.__getattribute__(certificate_fixture.source, "_snapshot")
    forged_snapshot = _snapshot_with(
        snapshot,
        source_context_root=_root("forged-snapshot-context"),
    )
    wrong_snapshot = _forged_source(
        certificate_fixture.source,
        _snapshot=forged_snapshot,
    )
    _assert_failure(
        _commit(context, certificate_fixture.request, wrong_snapshot),
        disposition=GovernanceCommitDispositionV2.INVALID,
        code=AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        path="/source",
        stage=GovernanceFailureStageV2.VALIDATION,
    )


def test_prepare_rejects_wrong_types_policy_step_parent_and_attestation(
    certificate_fixture: _Fixture,
) -> None:
    fixture = certificate_fixture
    decision = fixture.decision_state
    common = {
        "decision_state": decision,
        "manifest": fixture.context.manifest,
        "trusted_verifier": _DiscoveryVerifier(),
        "certificate_id": "certificate:prepare:negative",
        "issuer_ref": fixture.context.grant.issuer_ref,
        "issuer_attestation_refs": ("attestation:negative",),
        "issued_at_step": decision.snapshot.current_step,
        "provenance_ref": "urn:test:certificate:prepare:negative",
        "envelope_nonce": "nonce:prepare:negative",
        "mutation_ref": "mutation:certificate:prepare:negative",
    }
    with pytest.raises((TypeError, GovernanceAuthorityBindingErrorV2)):
        prepare_commit_certificate_v2(**{**common, "decision_state": object()})
    with pytest.raises(TypeError, match="exact scoped manifest"):
        prepare_commit_certificate_v2(**{**common, "manifest": object()})
    with pytest.raises(ValueError, match="issuance step is not current"):
        prepare_commit_certificate_v2(
            **{
                **common,
                "issued_at_step": decision.snapshot.current_step + 1,
            }
        )
    with pytest.raises((TypeError, GovernanceAuthorityBindingErrorV2)):
        prepare_commit_certificate_v2(**{**common, "parent_state": object()})

    class _RejectingVerifier:
        def verify_commit_certificate_attestation_v2(
            self,
            **_kwargs: object,
        ) -> bool:
            return False

    with pytest.raises(ValueError, match="attestation is not trusted"):
        prepare_commit_certificate_v2(
            **{
                **common,
                "trusted_verifier": _RejectingVerifier(),
            }
        )


def test_open_and_advance_require_exact_request_session_and_source(
    certificate_fixture: _Fixture,
) -> None:
    context = _restart_context(certificate_fixture)
    request = certificate_fixture.request
    with pytest.raises(TypeError, match="exact request"):
        open_commit_certificate_authority_session_v2(
            _capability(context, request.observed_epoch),
            object(),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="exact request"):
        advance_commit_certificate_v2(object())  # type: ignore[arg-type]

    issuer_mismatch = replace(
        request,
        mutation_issuer_ref="issuer:wrong",
        request_root="",
    )
    _binding_error(
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/mutation_issuer_ref",
        lambda: open_commit_certificate_authority_session_v2(
            _capability(context, issuer_mismatch.observed_epoch),
            issuer_mismatch,
        ),
    )

    missing_session = advance_commit_certificate_v2(
        request,
        source=certificate_fixture.source,
    )
    assert missing_session.failure is not None
    assert (
        missing_session.failure.code
        is AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED
    )
    assert missing_session.failure.path == ""
    assert missing_session.failure.stage is GovernanceFailureStageV2.VALIDATION

    session = open_commit_certificate_authority_session_v2(
        _capability(context, request.observed_epoch),
        request,
    )
    wrong_source = advance_commit_certificate_v2(
        request,
        source=object(),
        authority_session=session,
    )
    _assert_failure(
        wrong_source,
        disposition=GovernanceCommitDispositionV2.INVALID,
        code=AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        path="/source",
        stage=GovernanceFailureStageV2.VALIDATION,
    )

    other = replace(
        request,
        mutation_ref="mutation:certificate:public-semantics:other-session",
        transition_id="",
        request_root="",
    )
    bound_elsewhere = advance_commit_certificate_v2(
        other,
        source=certificate_fixture.source,
        authority_session=session,
    )
    _assert_failure(
        bound_elsewhere,
        disposition=GovernanceCommitDispositionV2.INVALID,
        code=AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        path="/request_root",
        stage=GovernanceFailureStageV2.VALIDATION,
    )


def test_advance_normalizes_a_state_store_protocol_lookup_exception(
    certificate_fixture: _Fixture,
) -> None:
    baseline = _restart_context(certificate_fixture)
    proxy = _ProtocolExplodingStoreProxy(baseline.store)
    context = replace(baseline, store=proxy)
    request = certificate_fixture.request
    session = open_commit_certificate_authority_session_v2(
        _capability(context, request.observed_epoch),
        request,
    )
    proxy.arm()

    attempt = advance_commit_certificate_v2(
        request,
        source=certificate_fixture.source,
        authority_session=session,
    )
    _assert_failure(
        attempt,
        disposition=GovernanceCommitDispositionV2.INVALID,
        code=AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
        path="/authority_session",
        stage=GovernanceFailureStageV2.VALIDATION,
    )


def test_revoked_grant_blocks_new_commit_but_exact_retry_survives(
    certificate_fixture: _Fixture,
) -> None:
    context = _restart_context(certificate_fixture)
    request = certificate_fixture.request
    session = open_commit_certificate_authority_session_v2(
        _capability(context, request.observed_epoch),
        request,
    )
    revoked = revoke_governance_issuer_grant_v2(
        context.store,
        context.domain,
        context.grant.grant_ref,
        "transition:certificate:public-semantics:revoke",
        99,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED
    denied = advance_commit_certificate_v2(
        request,
        source=certificate_fixture.source,
        authority_session=session,
    )
    assert denied.disposition is GovernanceCommitDispositionV2.DENIED
    assert denied.failure is not None
    assert denied.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED

    context, committed, _ = _commit_and_rehydrate(certificate_fixture)
    session = open_commit_certificate_authority_session_v2(
        _capability(context, request.observed_epoch),
        request,
    )
    revoked = revoke_governance_issuer_grant_v2(
        context.store,
        context.domain,
        context.grant.grant_ref,
        "transition:certificate:public-semantics:revoke-after",
        100,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED
    recovered = advance_commit_certificate_v2(
        request,
        source=object(),
        authority_session=session,
    )
    assert recovered.to_dict() == committed.to_dict()


def test_genesis_parent_preconditions_fail_before_source_validation(
    certificate_fixture: _Fixture,
) -> None:
    context, _, _ = _commit_and_rehydrate(certificate_fixture)
    request = replace(
        certificate_fixture.request,
        mutation_ref="mutation:certificate:public-semantics:second-genesis",
        transition_id="",
        request_root="",
    )
    attempt = _commit(context, request, certificate_fixture.source)
    _assert_failure(
        attempt,
        disposition=GovernanceCommitDispositionV2.RETRY_REQUIRED,
        code=AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        path="/parent_revision",
        stage=GovernanceFailureStageV2.PRECONDITION,
    )

    context = _restart_context(certificate_fixture)
    non_genesis = replace(
        certificate_fixture.request,
        parent_revision=1,
        parent_transition_id="transition:missing-parent",
        parent_snapshot_root=_root("missing-parent"),
        request_root="",
    )
    attempt = _commit(context, non_genesis, certificate_fixture.source)
    _assert_failure(
        attempt,
        disposition=GovernanceCommitDispositionV2.INVALID,
        code=AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
        path="/parent_transition_id",
        stage=GovernanceFailureStageV2.LOAD,
    )


def test_dependency_load_failures_are_typed_and_atomic(
    certificate_fixture: _Fixture,
) -> None:
    baseline = _restart_context(certificate_fixture)
    request = certificate_fixture.request
    leaf_stream = request.certificate.body.authority_leaves[0].stream_ref

    def missing_head(scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        if stream_ref == leaf_stream:
            raise KeyError(stream_ref)
        return baseline.store.load_head_v2(scope_ref, stream_ref)

    store = _StoreProxy(baseline.store, head_hook=missing_head)
    context = replace(baseline, store=store)
    attempt = _commit(context, request, certificate_fixture.source)
    _assert_failure(
        attempt,
        disposition=GovernanceCommitDispositionV2.RETRY_REQUIRED,
        code=AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        path="/dependencies",
        stage=GovernanceFailureStageV2.PRECONDITION,
    )
    assert (
        baseline.store.load_head_v2(
            request.scope_ref,
            request.stream_ref,
        ).revision
        == 0
    )

    def wrong_head_type(scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        if stream_ref == leaf_stream:
            return object()  # type: ignore[return-value]
        return baseline.store.load_head_v2(scope_ref, stream_ref)

    store = _StoreProxy(baseline.store, head_hook=wrong_head_type)
    context = replace(baseline, store=store)
    attempt = _commit(context, request, certificate_fixture.source)
    _assert_failure(
        attempt,
        disposition=GovernanceCommitDispositionV2.INVALID,
        code=AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        path="/dependencies",
        stage=GovernanceFailureStageV2.LOAD,
    )


def test_dependency_receipt_and_head_substitution_fail_closed(
    certificate_fixture: _Fixture,
) -> None:
    baseline = _restart_context(certificate_fixture)
    request = certificate_fixture.request
    leaf = request.certificate.body.authority_leaves[0]

    def missing_receipt(
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        expected_receipt_root: str | None,
    ) -> GovernanceCommitViewV2:
        if stream_ref == leaf.stream_ref:
            raise KeyError(stream_ref)
        return baseline.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    store = _StoreProxy(baseline.store, view_hook=missing_receipt)
    attempt = _commit(
        replace(baseline, store=store),
        request,
        certificate_fixture.source,
    )
    _assert_failure(
        attempt,
        disposition=GovernanceCommitDispositionV2.INVALID,
        code=AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
        path="/dependencies",
        stage=GovernanceFailureStageV2.LOAD,
    )

    def changed_head(scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        head = baseline.store.load_head_v2(scope_ref, stream_ref)
        if stream_ref == leaf.stream_ref:
            return replace(
                head,
                transition_id="transition:substituted-head",
                head_root="",
            )
        return head

    store = _StoreProxy(baseline.store, head_hook=changed_head)
    attempt = _commit(
        replace(baseline, store=store),
        request,
        certificate_fixture.source,
    )
    _assert_failure(
        attempt,
        disposition=GovernanceCommitDispositionV2.RETRY_REQUIRED,
        code=AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        path="/dependencies",
        stage=GovernanceFailureStageV2.PRECONDITION,
    )


def test_snapshot_contract_round_trip_and_semantic_invariants(
    certificate_fixture: _Fixture,
) -> None:
    _, _, state = _commit_and_rehydrate(certificate_fixture)
    snapshot = state.snapshot
    assert CommitCertificateSnapshotV2.from_dict(snapshot.to_dict()) == snapshot
    binding = snapshot.identity_bindings[0]
    assert CommitCertificateIdentityBindingV2.from_dict(binding.to_dict()) == binding

    with pytest.raises(ValueError, match="identity schema is unsupported"):
        replace(binding, schema="unsupported", binding_root="")
    with pytest.raises(ValueError, match="version is unsupported"):
        _snapshot_with(snapshot, schema="unsupported")
    with pytest.raises(TypeError, match="mutation kind is invalid"):
        _snapshot_with(snapshot, mutation_kind="verified")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="status is invalid"):
        _snapshot_with(snapshot, status="verified")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="exact certificate"):
        _snapshot_with(snapshot, certificate=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="stream identity is mismatched"):
        _snapshot_with(snapshot, stream_ref="authority:wrong")
    with pytest.raises(ValueError, match="transition identity is mismatched"):
        _snapshot_with(snapshot, transition_id="transition:wrong")
    with pytest.raises(ValueError, match="revision is not contiguous"):
        _snapshot_with(snapshot, revision=2)
    with pytest.raises(ValueError, match="history count is not contiguous"):
        _snapshot_with(snapshot, history_count=2)
    with pytest.raises(ValueError, match="genesis lineage is mismatched"):
        _snapshot_with(
            snapshot,
            parent_history_root=_root("wrong-genesis-history"),
        )


def test_snapshot_contract_rejects_status_identity_and_wire_forgery(
    certificate_fixture: _Fixture,
) -> None:
    _, _, state = _commit_and_rehydrate(certificate_fixture)
    snapshot = state.snapshot
    binding = snapshot.identity_bindings[0]

    with pytest.raises(ValueError, match="absent from history"):
        _snapshot_with(snapshot, envelope_roots=(_root("other-envelope"),))
    with pytest.raises(ValueError, match="no durable binding"):
        _snapshot_with(
            snapshot,
            identity_bindings=(
                replace(
                    binding,
                    certificate_id="certificate:other",
                    binding_root="",
                ),
            ),
        )
    with pytest.raises(ValueError, match="cannot carry conflicts"):
        _snapshot_with(
            snapshot,
            conflicting_body_roots=(_root("conflicting-body"),),
        )
    with pytest.raises(ValueError, match="identity is mismatched"):
        _snapshot_with(
            snapshot,
            identity_bindings=(
                replace(binding, body_root=_root("other-body"), binding_root=""),
            ),
        )
    with pytest.raises(ValueError, match="requires conflict roots"):
        _snapshot_with(snapshot, status=CommitCertificateStatusV2.CONFLICT)
    with pytest.raises(ValueError, match="conflict mutation must be sticky"):
        _snapshot_with(
            snapshot,
            mutation_kind=CommitCertificateMutationKindV2.CONFLICT,
        )
    with pytest.raises(ValueError, match="must be verified"):
        _snapshot_with(
            snapshot,
            status=CommitCertificateStatusV2.CONFLICT,
            conflicting_body_roots=(_root("conflicting-body"),),
        )
    with pytest.raises(TypeError, match="exact sequence"):
        _snapshot_with(snapshot, identity_bindings=set(snapshot.identity_bindings))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must be unique"):
        _snapshot_with(
            snapshot,
            identity_bindings=(binding, binding),
        )

    unsupported = snapshot.to_dict()
    unsupported["status"] = "unsupported"
    with pytest.raises(ValueError, match="enum is unsupported"):
        CommitCertificateSnapshotV2.from_dict(unsupported)
    wrong_array = snapshot.to_dict()
    wrong_array["reason_codes"] = ()
    with pytest.raises(TypeError, match="exact wire array"):
        CommitCertificateSnapshotV2.from_dict(wrong_array)


def test_public_finality_input_revalidates_type_step_binding_and_currentness(
    certificate_fixture: _Fixture,
) -> None:
    context, _, state = _commit_and_rehydrate(certificate_fixture)
    decision = certificate_fixture.decision_state
    current_step = decision.snapshot.current_step + 1
    finality = verified_commit_certificate_finality_input_v2(
        state,
        sealed_decision_state=decision,
        current_step=current_step,
    )
    assert copy.copy(finality) is finality
    assert copy.deepcopy(finality) is finality
    assert repr(finality) == "<VerifiedCommitFinalityInputV2 redacted>"
    with pytest.raises(TypeError, match="verified Decision state"):
        verified_commit_certificate_finality_input_v2(
            state,
            sealed_decision_state=object(),
            current_step=current_step,
        )
    with pytest.raises(TypeError, match="exact integer"):
        verified_commit_certificate_finality_input_v2(
            state,
            sealed_decision_state=decision,
            current_step=True,
        )
    with pytest.raises(ValueError, match="exact next heartbeat"):
        verified_commit_certificate_finality_input_v2(
            state,
            sealed_decision_state=decision,
            current_step=current_step + 1,
        )

    second, second_source = _prepared_certificate(
        context,
        decision,
        mutation_ref="mutation:certificate:public-semantics:stale-finality",
        certificate_id="certificate:public-semantics:stale-finality",
        envelope_nonce="nonce:public-semantics:stale-finality",
        parent_state=state,
    )
    assert _commit(context, second, second_source).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    _binding_error(
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        "/certificate/position",
        lambda: verified_commit_certificate_finality_input_v2(
            state,
            sealed_decision_state=decision,
            current_step=current_step,
        ),
    )


def test_public_finality_input_rejects_the_exact_deadline_heartbeat() -> None:
    context = certified_context("scope:certificate-v2:deadline-boundary")
    policy = context.manifest.collective_commit_policy
    assert policy is not None
    context = replace(
        context,
        manifest=replace(
            context.manifest,
            collective_commit_policy=replace(
                policy,
                commit_window=replace(
                    policy.commit_window,
                    deliberation_deadline_steps=5,
                    run_deadline_steps=5,
                ),
            ),
        ),
    )
    decision, inputs = sealed_certified_decision(
        context,
        _root("claim:certificate:deadline-boundary"),
    )
    decision = heartbeat_certified_decision(
        context,
        decision,
        inputs,
        mutation_ref="mutation:certificate:deadline-boundary:heartbeat",
    )
    assert decision.snapshot.current_step + 1 == (
        decision.snapshot.finality_deadline_step
    )
    request, source = _prepared_certificate(
        context,
        decision,
        mutation_ref="mutation:certificate:deadline-boundary",
        certificate_id="certificate:deadline-boundary",
        envelope_nonce="nonce:deadline-boundary",
    )
    attempt = _commit(context, request, source)
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    state = rehydrate_commit_certificate_state_v2(
        request,
        domain=context.domain,
        state_reader=context.store,
    )

    with pytest.raises(ValueError, match="deadline has elapsed"):
        verified_commit_certificate_finality_input_v2(
            state,
            sealed_decision_state=decision,
            current_step=decision.snapshot.finality_deadline_step,
        )


def test_public_finality_input_rejects_cross_decision_and_dependency_drift(
    certificate_fixture: _Fixture,
) -> None:
    context, _, state = _commit_and_rehydrate(certificate_fixture)
    decision = certificate_fixture.decision_state
    leaf = state.snapshot.certificate.body.authority_leaves[0]

    def missing_dependency(scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        if stream_ref == leaf.stream_ref:
            raise KeyError(stream_ref)
        return context.store.load_head_v2(scope_ref, stream_ref)

    reader = _ReaderProxy(context.store, head_hook=missing_dependency)
    state_with_missing_dependency = rehydrate_commit_certificate_state_v2(
        certificate_fixture.request,
        domain=context.domain,
        state_reader=reader,
    )
    _binding_error(
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        "/certificate/dependencies",
        lambda: verified_commit_certificate_finality_input_v2(
            state_with_missing_dependency,
            sealed_decision_state=decision,
            current_step=decision.snapshot.current_step + 1,
        ),
    )

    def invalid_dependency(scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        if stream_ref == leaf.stream_ref:
            return object()  # type: ignore[return-value]
        return context.store.load_head_v2(scope_ref, stream_ref)

    reader = _ReaderProxy(context.store, head_hook=invalid_dependency)
    invalid_dependency_state = rehydrate_commit_certificate_state_v2(
        certificate_fixture.request,
        domain=context.domain,
        state_reader=reader,
    )
    with pytest.raises(ValueError, match="dependency head is invalid"):
        verified_commit_certificate_finality_input_v2(
            invalid_dependency_state,
            sealed_decision_state=decision,
            current_step=decision.snapshot.current_step + 1,
        )

    heartbeat = heartbeat_certified_decision(
        _restart_context(certificate_fixture),
        decision,
        certificate_fixture.inputs,
        mutation_ref="mutation:certificate:public-semantics:cross-decision",
    )
    with pytest.raises(ValueError, match="cross-bound"):
        verified_commit_certificate_finality_input_v2(
            state,
            sealed_decision_state=heartbeat,
            current_step=heartbeat.snapshot.current_step + 1,
        )


def test_commit_view_records_reject_non_certificate_substitution(
    certificate_fixture: _Fixture,
) -> None:
    context, _, state = _commit_and_rehydrate(certificate_fixture)
    request = certificate_fixture.request
    decision = certificate_fixture.decision_state.snapshot

    def substitute_decision(
        _scope: str,
        stream_ref: str,
        transition_id: str,
        expected_receipt_root: str | None,
    ) -> GovernanceCommitViewV2:
        if stream_ref == request.stream_ref:
            return context.store.load_commit_view_v2(
                request.scope_ref,
                decision.stream_ref,
                decision.transition_id,
            )
        return context.store.load_commit_view_v2(
            request.scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    poisoned = _ReaderProxy(context.store, view_hook=substitute_decision)
    _binding_error(
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
        "/transition_id",
        lambda: rehydrate_commit_certificate_state_v2(
            request,
            domain=context.domain,
            state_reader=poisoned,
        ),
    )
    assert state.snapshot.status is CommitCertificateStatusV2.VERIFIED


def test_canonical_totality_helpers_report_each_wire_failure() -> None:
    with pytest.raises(TypeError, match="exact string"):
        _require_text(1, "text")
    with pytest.raises(ValueError, match="non-empty"):
        _require_text("", "text")
    with pytest.raises(ValueError, match="U\\+0000"):
        _require_text("bad\x00text", "text")
    with pytest.raises(ValueError, match="encode as UTF-8"):
        _require_text("\ud800", "text")
    with pytest.raises(ValueError, match="text bound"):
        _require_text("x" * 4_097, "text")
    assert _require_root("", "root", allow_empty=True) == ""
    with pytest.raises(ValueError, match="lowercase sha256"):
        _require_root("sha256:" + ("A" * 64), "root")
    with pytest.raises(TypeError, match="exact array or tuple"):
        _canonical_texts({"one"}, "texts")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="invalid item count"):
        _canonical_texts((), "texts")
    with pytest.raises(ValueError, match="unique values"):
        _canonical_texts(("one", "one"), "texts")
    with pytest.raises(TypeError, match="exact object"):
        _exact_mapping((), frozenset({"field"}), "mapping")
    with pytest.raises(ValueError, match="not canonical wire"):
        _require_canonical_wire({"field": "wrong"}, {"field": "right"}, "wire")


def test_nested_byte_bounds_remain_total_after_object_forgery(
    certificate_fixture: _Fixture,
) -> None:
    body = CommitCertificateBodyV2.from_dict(
        certificate_fixture.request.certificate.body.to_dict()
    )
    forged_leaf = CommitCertificateAuthorityLeafV2.from_dict(
        body.authority_leaves[0].to_dict()
    )
    object.__setattr__(forged_leaf, "stream_ref", "x" * 524_289)
    with pytest.raises(ValueError, match="body exceeds its byte bound"):
        replace(
            body,
            authority_leaves=(forged_leaf, *body.authority_leaves[1:]),
            body_root="",
        )

    forged_body = CommitCertificateBodyV2.from_dict(body.to_dict())
    object.__setattr__(forged_body, "scope_ref", "x" * 524_289)
    with pytest.raises(ValueError, match="envelope exceeds its byte bound"):
        replace(
            certificate_fixture.request.certificate,
            body=forged_body,
            envelope_root="",
        )

    _, _, state = _commit_and_rehydrate(certificate_fixture)
    forged_certificate = PortableCommitCertificateV2.from_dict(
        state.snapshot.certificate.to_dict()
    )
    object.__setattr__(forged_certificate, "provenance_ref", "x" * 524_289)
    with pytest.raises(ValueError, match="snapshot exceeds its byte bound"):
        _snapshot_with(state.snapshot, certificate=forged_certificate)


def test_snapshot_totality_rejects_history_body_and_identity_forgery(
    certificate_fixture: _Fixture,
) -> None:
    _, _, state = _commit_and_rehydrate(certificate_fixture)
    snapshot = state.snapshot
    with pytest.raises(ValueError, match="history root is mismatched"):
        replace(
            snapshot,
            history_root=_root("forged-history"),
            snapshot_root="",
        )
    with pytest.raises(ValueError, match="identity count is invalid"):
        _snapshot_with(snapshot, identity_bindings=())
    with pytest.raises(TypeError, match="identity binding is noncanonical"):
        _snapshot_with(snapshot, identity_bindings=(object(),))  # type: ignore[arg-type]

    forged_certificate = PortableCommitCertificateV2.from_dict(
        snapshot.certificate.to_dict()
    )
    object.__setattr__(
        forged_certificate.body,
        "target_ref",
        "target:cross-bound",
    )
    with pytest.raises(ValueError, match="snapshot body is cross-bound"):
        _snapshot_with(snapshot, certificate=forged_certificate)


def test_decision_leaf_and_event_totality_helpers_fail_specifically(
    certificate_fixture: _Fixture,
) -> None:
    original_dependency = next(
        item
        for item in certificate_fixture.decision_state.snapshot.dependencies
        if item.revision > 0
    )
    dependency = type(original_dependency).from_dict(original_dependency.to_dict())
    object.__setattr__(
        dependency,
        "observed_position",
        GovernanceCommitPositionV2.SUPERSEDED,
    )
    with pytest.raises(ValueError, match="dependency was not current"):
        _authority_leaves((dependency,))

    _, _, state = _commit_and_rehydrate(certificate_fixture)
    with pytest.raises(TypeError, match="session binding is invalid"):
        _commit_certificate_event_v2(
            certificate_fixture.request,
            state.snapshot,
            (),  # type: ignore[arg-type]
            parent_head_root=_root("parent-head"),
            read_set_root=_root("read-set"),
        )


def test_reducer_distinguishes_new_epoch_and_both_semantic_conflicts(
    certificate_fixture: _Fixture,
) -> None:
    _, _, state = _commit_and_rehydrate(certificate_fixture)
    parent = state.snapshot
    old_body = parent.certificate.body

    semantic_body = replace(
        old_body,
        output_payload_root=_root("semantic-conflict-output"),
        body_root="",
    )
    semantic = replace(
        parent.certificate,
        certificate_id="certificate:semantic-conflict",
        envelope_nonce="nonce:semantic-conflict",
        body=semantic_body,
        envelope_root="",
    )
    assert _conflict_reason(parent, semantic, ()) == "certificate_semantic_conflict"
    semantic_request = replace(
        certificate_fixture.request,
        mutation_ref="mutation:certificate:semantic-conflict",
        parent_revision=parent.revision,
        parent_transition_id=parent.transition_id,
        parent_snapshot_root=parent.snapshot_root,
        certificate=semantic,
        transition_id="",
        request_root="",
    )
    semantic_snapshot = _reduce_snapshot(
        semantic_request,
        parent=parent,
        source_context_root=_root("semantic-conflict-source"),
    )
    assert semantic_snapshot.status is CommitCertificateStatusV2.CONFLICT
    assert semantic_snapshot.mutation_kind is CommitCertificateMutationKindV2.CONFLICT
    assert semantic_snapshot.reason_codes == ("certificate_semantic_conflict",)
    assert semantic_snapshot.conflicting_body_roots == tuple(
        sorted((old_body.body_root, semantic_body.body_root))
    )

    seal_body = replace(
        old_body,
        seal_root=_root("replacement-seal"),
        body_root="",
    )
    seal = replace(
        parent.certificate,
        certificate_id="certificate:seal-conflict",
        envelope_nonce="nonce:seal-conflict",
        body=seal_body,
        envelope_root="",
    )
    assert _conflict_reason(parent, seal, ()) == "certificate_seal_conflict"

    retry_certificate = replace(
        parent.certificate,
        envelope_nonce="nonce:semantic-retry",
        envelope_root="",
    )
    retry_request = replace(
        certificate_fixture.request,
        mutation_ref="mutation:certificate:semantic-retry",
        parent_revision=parent.revision,
        parent_transition_id=parent.transition_id,
        parent_snapshot_root=parent.snapshot_root,
        certificate=retry_certificate,
        transition_id="",
        request_root="",
    )
    retried = _reduce_snapshot(
        retry_request,
        parent=parent,
        source_context_root=_root("semantic-retry-source"),
    )
    assert retried.mutation_kind is CommitCertificateMutationKindV2.SEMANTIC_RETRY
    assert retried.reason_codes == ("certificate_semantic_retry",)
    assert retried.identity_bindings == parent.identity_bindings

    sticky_parent = CommitCertificateSnapshotV2.from_dict(parent.to_dict())
    object.__setattr__(sticky_parent, "status", CommitCertificateStatusV2.CONFLICT)
    assert (
        _conflict_reason(sticky_parent, retry_certificate, ())
        == "certificate_conflict_sticky"
    )
    identity_conflict = replace(
        parent.certificate,
        body=semantic_body,
        envelope_nonce="nonce:identity-body-conflict",
        envelope_root="",
    )
    assert (
        _conflict_reason(
            parent,
            identity_conflict,
            (parent.identity_bindings[0],),
        )
        == "certificate_identity_body_conflict"
    )

    epoch_body = replace(
        old_body,
        epoch=old_body.epoch + 1,
        seal_root=_root("new-epoch-seal"),
        body_root="",
    )
    epoch_certificate = replace(
        parent.certificate,
        certificate_id="certificate:new-epoch",
        envelope_nonce="nonce:new-epoch",
        body=epoch_body,
        envelope_root="",
    )
    epoch_request = replace(
        certificate_fixture.request,
        observed_epoch=epoch_body.epoch,
        mutation_ref="mutation:certificate:new-epoch",
        parent_revision=parent.revision,
        parent_transition_id=parent.transition_id,
        parent_snapshot_root=parent.snapshot_root,
        certificate=epoch_certificate,
        transition_id="",
        request_root="",
    )
    reduced = _reduce_snapshot(
        epoch_request,
        parent=parent,
        source_context_root=_root("new-epoch-source"),
    )
    assert reduced.status is CommitCertificateStatusV2.VERIFIED
    assert reduced.reason_codes == ("certificate_new_epoch_verified",)


def test_private_finality_context_totality_is_redacted_and_tamper_evident(
    certificate_fixture: _Fixture,
) -> None:
    _, _, state = _commit_and_rehydrate(certificate_fixture)
    decision = certificate_fixture.decision_state
    context = _verified_commit_certificate_finality_context_v2(
        state,
        sealed_decision_state=decision,
        current_step=decision.snapshot.current_step + 1,
    )
    assert repr(context) == "<_VerifiedCommitCertificateFinalityContextV2 redacted>"
    with pytest.raises(TypeError, match="cannot be constructed"):
        _VerifiedCommitCertificateFinalityContextV2()
    with pytest.raises(TypeError, match="is final"):
        type(
            "ForgedFinalityContext",
            (_VerifiedCommitCertificateFinalityContextV2,),
            {},
        )
    with pytest.raises(AttributeError, match="is immutable"):
        context._anchor_root = _root("forged-anchor")  # type: ignore[misc]
    with pytest.raises(TypeError, match="not portable"):
        context.__reduce__()
    with pytest.raises(TypeError, match="not portable"):
        context.__reduce_ex__(5)
    with pytest.raises(TypeError, match="not portable"):
        context.__getstate__()
    with pytest.raises(TypeError, match="wrong exact type"):
        _verified_commit_certificate_finality_context_material_v2(object())

    incomplete = object.__new__(_VerifiedCommitCertificateFinalityContextV2)
    with pytest.raises(TypeError, match="is incomplete"):
        _verified_commit_certificate_finality_context_material_v2(incomplete)

    invalid_anchor = object.__new__(_VerifiedCommitCertificateFinalityContextV2)
    for name in _VerifiedCommitCertificateFinalityContextV2.__slots__:
        object.__setattr__(
            invalid_anchor,
            name,
            object.__getattribute__(context, name),
        )
    object.__setattr__(invalid_anchor, "_current_step", True)
    with pytest.raises(TypeError, match="anchor is invalid"):
        _verified_commit_certificate_finality_context_material_v2(invalid_anchor)

    mismatched = object.__new__(_VerifiedCommitCertificateFinalityContextV2)
    for name in _VerifiedCommitCertificateFinalityContextV2.__slots__:
        object.__setattr__(mismatched, name, object.__getattribute__(context, name))
    object.__setattr__(mismatched, "_anchor_root", _root("mismatched-anchor"))
    with pytest.raises(ValueError, match="anchor is mismatched"):
        _verified_commit_certificate_finality_context_material_v2(mismatched)


def test_state_and_source_explicit_pickle_hooks_reject_portability(
    certificate_fixture: _Fixture,
) -> None:
    _, _, state = _commit_and_rehydrate(certificate_fixture)
    for handle in (state, certificate_fixture.source):
        with pytest.raises(TypeError, match="not portable"):
            handle.__reduce__()
        with pytest.raises(TypeError, match="not portable"):
            handle.__getstate__()


def test_source_verifier_reports_request_parent_and_exact_type_mismatches(
    certificate_fixture: _Fixture,
) -> None:
    request = certificate_fixture.request
    other_request = replace(
        request,
        mutation_ref="mutation:certificate:source-mismatch",
        transition_id="",
        request_root="",
    )
    mismatched_source = _forged_source(
        certificate_fixture.source,
        _request=other_request,
    )
    with pytest.raises(ValueError, match="source request is mismatched"):
        verify_commit_certificate_request_source_v2(
            request,
            source=mismatched_source,
            committed_parent_snapshot=None,
        )
    with pytest.raises(TypeError, match="wrong exact type"):
        verify_commit_certificate_request_source_v2(
            request,
            source=object(),
            committed_parent_snapshot=None,
        )

    _, _, unrelated_parent = _commit_and_rehydrate(certificate_fixture)
    unexpected_parent_source = _forged_source(
        certificate_fixture.source,
        _parent_state=unrelated_parent,
    )
    with pytest.raises(ValueError, match="parent presence is mismatched"):
        verify_commit_certificate_request_source_v2(
            request,
            source=unexpected_parent_source,
            committed_parent_snapshot=None,
        )


def test_source_verifier_reports_parent_snapshot_mismatch(
    certificate_fixture: _Fixture,
) -> None:
    context, _, parent_state = _commit_and_rehydrate(certificate_fixture)
    successor, successor_source = _prepared_certificate(
        context,
        certificate_fixture.decision_state,
        mutation_ref="mutation:certificate:source-parent-mismatch",
        certificate_id="certificate:source-parent-mismatch",
        envelope_nonce="nonce:source-parent-mismatch",
        parent_state=parent_state,
    )
    different_parent = _snapshot_with(
        parent_state.snapshot,
        source_context_root=_root("different-parent-source"),
    )
    with pytest.raises(ValueError, match="source parent is mismatched"):
        verify_commit_certificate_request_source_v2(
            successor,
            source=successor_source,
            committed_parent_snapshot=different_parent,
        )


def test_source_verifier_rejects_decision_body_substitution(
    certificate_fixture: _Fixture,
) -> None:
    request = certificate_fixture.request
    original = request.certificate
    verifier = _DigestVerifier()
    substituted_body = replace(
        original.body,
        evidence_root=_root("substituted-evidence"),
        body_root="",
    )
    attestation_ref = verifier.attestation_ref(
        original.issuer_ref,
        substituted_body.body_root,
    )
    substituted_certificate = replace(
        original,
        body=substituted_body,
        issuer_attestation_refs=(attestation_ref,),
        envelope_root="",
    )
    substituted_request = replace(
        request,
        certificate=substituted_certificate,
        request_root="",
    )
    substituted_source = _forged_source(
        certificate_fixture.source,
        _request=substituted_request,
        _trusted_verifier=verifier,
    )
    with pytest.raises(
        ValueError,
        match="body no longer matches Decision authority",
    ):
        verify_commit_certificate_request_source_v2(
            substituted_request,
            source=substituted_source,
            committed_parent_snapshot=None,
        )


def test_manifest_and_decision_totality_reject_missing_policy_assurance_and_metrics(
    certificate_fixture: _Fixture,
) -> None:
    fixture = certificate_fixture
    no_policy = replace(
        fixture.context.manifest,
        collective_commit_policy=None,
    )
    with pytest.raises(ValueError, match="manifest has no commit policy"):
        prepare_commit_certificate_v2(
            decision_state=fixture.decision_state,
            manifest=no_policy,
            trusted_verifier=_DiscoveryVerifier(),
            certificate_id="certificate:no-policy",
            issuer_ref=fixture.context.grant.issuer_ref,
            issuer_attestation_refs=("attestation:no-policy",),
            issued_at_step=fixture.decision_state.snapshot.current_step,
            provenance_ref="urn:test:certificate:no-policy",
            envelope_nonce="nonce:no-policy",
            mutation_ref="mutation:certificate:no-policy",
        )

    mismatched_manifest = replace(
        fixture.context.manifest,
        id="protocol:certificate:mismatched",
    )
    with pytest.raises(ValueError, match="manifest policy is mismatched"):
        prepare_commit_certificate_v2(
            decision_state=fixture.decision_state,
            manifest=mismatched_manifest,
            trusted_verifier=_DiscoveryVerifier(),
            certificate_id="certificate:mismatched-policy",
            issuer_ref=fixture.context.grant.issuer_ref,
            issuer_attestation_refs=("attestation:mismatched-policy",),
            issued_at_step=fixture.decision_state.snapshot.current_step,
            provenance_ref="urn:test:certificate:mismatched-policy",
            envelope_nonce="nonce:mismatched-policy",
            mutation_ref="mutation:certificate:mismatched-policy",
        )

    decision_material = _verified_commit_decision_seal_context_material_v2(
        _verified_commit_decision_seal_context_v2(fixture.decision_state)
    )
    object.__setattr__(
        decision_material.snapshot,
        "assurance",
        CommitAssurance.ADVISORY,
    )
    with pytest.raises(ValueError, match="requires certified assurance"):
        _validated_manifest(fixture.context.manifest, decision_material)

    decision_material = _verified_commit_decision_seal_context_material_v2(
        _verified_commit_decision_seal_context_v2(fixture.decision_state)
    )
    assert decision_material.snapshot.assessment is not None
    object.__setattr__(
        decision_material.snapshot.assessment,
        "candidate_metrics",
        (),
    )
    with pytest.raises(ValueError, match="candidate is not evidence-ready"):
        _body_from_decision(decision_material, fixture.context.manifest)


def test_finality_detects_evidence_domain_and_current_head_substitution(
    certificate_fixture: _Fixture,
) -> None:
    context, _, state = _commit_and_rehydrate(certificate_fixture)
    decision_context = _verified_commit_decision_seal_context_v2(
        certificate_fixture.decision_state
    )
    decision = _verified_commit_decision_seal_context_material_v2(decision_context)
    certificate = _verified_commit_certificate_state_material_v2(state)

    forged_snapshot = CommitCertificateSnapshotV2.from_dict(
        certificate.snapshot.to_dict()
    )
    object.__setattr__(
        forged_snapshot.certificate.body,
        "evidence_root",
        _root("forged-finality-evidence"),
    )
    with pytest.raises(ValueError, match="evidence or authority leaves"):
        _require_certificate_matches_decision(forged_snapshot, decision)

    cross_domain = replace(
        certificate,
        domain=replace(
            certificate.domain,
            scope_ref="scope:certificate:cross-domain",
            domain_root="",
        ),
    )
    with pytest.raises(ValueError, match="finality domain is cross-bound"):
        _require_upstreams_current(cross_domain, decision)

    leaf = certificate.snapshot.certificate.body.authority_leaves[0]

    def changed_dependency(scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        head = context.store.load_head_v2(scope_ref, stream_ref)
        if stream_ref == leaf.stream_ref:
            return replace(
                head,
                transition_id="transition:forged-current-head",
                head_root="",
            )
        return head

    reader = _ReaderProxy(context.store, head_hook=changed_dependency)
    drifted_state = rehydrate_commit_certificate_state_v2(
        certificate_fixture.request,
        domain=context.domain,
        state_reader=reader,
    )
    _binding_error(
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        "/certificate/dependencies",
        lambda: verified_commit_certificate_finality_input_v2(
            drifted_state,
            sealed_decision_state=certificate_fixture.decision_state,
            current_step=certificate_fixture.decision_state.snapshot.current_step + 1,
        ),
    )


def test_reader_totality_guard_rejects_non_reader() -> None:
    with pytest.raises(TypeError, match="requires StateReader v2"):
        _require_reader(object())
    with pytest.raises(TypeError, match="requires StateReader v2") as caught:
        _require_reader(_ProtocolExplodingReader())
    assert isinstance(caught.value.__cause__, RuntimeError)


def test_domain_retirement_blocks_new_certificate_and_seal_is_not_state(
    certificate_fixture: _Fixture,
) -> None:
    context = _restart_context(certificate_fixture)
    request = certificate_fixture.request
    capability = _capability(context, request.observed_epoch)
    certificate_session = open_commit_certificate_authority_session_v2(
        capability,
        request,
    )
    payload: Any = json.loads(getattr(context.store, "snapshot_v2")())
    domain_image = next(
        item
        for item in payload["domains"]
        if item["domain"]["scope_ref"] == context.domain.scope_ref
    )
    stream_refs = tuple(
        sorted(
            (
                head["stream_ref"]
                for head in domain_image["heads"]
                if head["stream_ref"] != GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2
            ),
            key=lambda item: item.encode("utf-8"),
        )
    )
    retirement_request = GovernanceDomainRetirementRequestV2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref=request.run_ref,
        request_ref="request:certificate:domain-retirement",
        transition_id="transition:certificate:domain-retirement",
        stream_refs=stream_refs,
        reason_ref="reason:certificate-test-complete",
        observed_epoch=request.observed_epoch,
    )
    retirement_session = open_governance_authority_session_v2(
        capability,
        retirement_request,
    )
    retirement = retire_governance_domain_v2(
        retirement_request,
        authority_session=retirement_session,
    )
    assert retirement.disposition is GovernanceCommitDispositionV2.COMMITTED
    lifecycle_view = context.store.load_commit_view_v2(
        request.scope_ref,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        retirement_request.transition_id,
    )
    with pytest.raises(ValueError, match="committed batch has no transition"):
        _decode_committed_certificate_view_v2(
            lifecycle_view,
            context.domain,
            reader=None,
        )

    denied = advance_commit_certificate_v2(
        request,
        source=certificate_fixture.source,
        authority_session=certificate_session,
    )
    assert denied.failure is not None
    assert denied.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED
    assert denied.failure.path == "/domain_root"
    assert denied.failure.stage is GovernanceFailureStageV2.PRECONDITION


def test_operations_report_missing_genesis_head_and_forged_genesis_lineage(
    certificate_fixture: _Fixture,
) -> None:
    baseline = _restart_context(certificate_fixture)
    request = CommitCertificateRequestV2.from_dict(
        certificate_fixture.request.to_dict()
    )

    def missing_certificate_head(
        scope_ref: str,
        stream_ref: str,
    ) -> GovernanceHeadV2:
        if stream_ref == request.stream_ref:
            raise KeyError(stream_ref)
        return baseline.store.load_head_v2(scope_ref, stream_ref)

    missing_store = _StoreProxy(
        baseline.store,
        head_hook=missing_certificate_head,
    )
    missing = _commit(
        replace(baseline, store=missing_store),
        request,
        certificate_fixture.source,
    )
    _assert_failure(
        missing,
        disposition=GovernanceCommitDispositionV2.RETRY_REQUIRED,
        code=AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        path="/dependencies",
        stage=GovernanceFailureStageV2.PRECONDITION,
    )

    session = open_commit_certificate_authority_session_v2(
        _capability(baseline, request.observed_epoch),
        request,
    )
    object.__setattr__(
        request,
        "parent_snapshot_root",
        _root("forged-genesis-parent"),
    )
    forged = advance_commit_certificate_v2(
        request,
        source=certificate_fixture.source,
        authority_session=session,
    )
    _assert_failure(
        forged,
        disposition=GovernanceCommitDispositionV2.INVALID,
        code=AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        path="/parent_snapshot_root",
        stage=GovernanceFailureStageV2.PRECONDITION,
    )


def test_parent_loader_totality_distinguishes_missing_unavailable_and_mismatch(
    certificate_fixture: _Fixture,
) -> None:
    baseline = _restart_context(certificate_fixture)
    request = replace(
        certificate_fixture.request,
        parent_revision=1,
        parent_transition_id="transition:missing-parent",
        parent_snapshot_root=_root("missing-parent"),
        request_root="",
    )

    def missing_view(
        _scope: str,
        _stream: str,
        _transition: str,
        _receipt: str | None,
    ) -> GovernanceCommitViewV2:
        raise KeyError("missing parent")

    loaded = _load_parent(
        _StoreProxy(baseline.store, view_hook=missing_view),
        baseline.domain,
        request,
    )
    assert isinstance(loaded, GovernanceCommitAttemptV2)
    _assert_failure(
        loaded,
        disposition=GovernanceCommitDispositionV2.INVALID,
        code=AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
        path="/parent_transition_id",
        stage=GovernanceFailureStageV2.LOAD,
    )

    unavailable = _load_parent(
        _StoreProxy(
            baseline.store,
            view_hook=lambda _s, _r, _t, receipt: _unavailable_view(
                request,
                receipt,
            ),
        ),
        baseline.domain,
        request,
    )
    assert isinstance(unavailable, GovernanceCommitAttemptV2)
    assert unavailable.disposition is (
        GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    )

    context, _, parent_state = _commit_and_rehydrate(certificate_fixture)
    successor, _ = _prepared_certificate(
        context,
        certificate_fixture.decision_state,
        mutation_ref="mutation:certificate:parent-mismatch-totality",
        certificate_id="certificate:parent-mismatch-totality",
        envelope_nonce="nonce:parent-mismatch-totality",
        parent_state=parent_state,
    )
    object.__setattr__(
        successor,
        "parent_snapshot_root",
        _root("forged-committed-parent"),
    )
    mismatched = _load_parent(
        context.store,
        context.domain,
        successor,
    )
    assert isinstance(mismatched, GovernanceCommitAttemptV2)
    assert mismatched.failure is not None
    assert mismatched.failure.path == "/parent_snapshot_root"


def test_parent_loader_rejects_superseded_parent(
    certificate_fixture: _Fixture,
) -> None:
    context, _, first_state = _commit_and_rehydrate(certificate_fixture)
    second, second_source = _prepared_certificate(
        context,
        certificate_fixture.decision_state,
        mutation_ref="mutation:certificate:parent-current:second",
        certificate_id="certificate:parent-current:second",
        envelope_nonce="nonce:parent-current:second",
        parent_state=first_state,
    )
    assert _commit(context, second, second_source).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    stale_parent_request = replace(
        second,
        mutation_ref="mutation:certificate:parent-current:third",
        parent_revision=first_state.snapshot.revision,
        parent_transition_id=first_state.snapshot.transition_id,
        parent_snapshot_root=first_state.snapshot.snapshot_root,
        transition_id="",
        request_root="",
    )
    loaded = _load_parent(
        context.store,
        context.domain,
        stale_parent_request,
    )
    assert isinstance(loaded, GovernanceCommitAttemptV2)
    _assert_failure(
        loaded,
        disposition=GovernanceCommitDispositionV2.RETRY_REQUIRED,
        code=AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
        path="/parent_revision",
        stage=GovernanceFailureStageV2.PRECONDITION,
    )


def test_dependency_totality_rejects_unavailable_receipt_substitution_and_scope(
    certificate_fixture: _Fixture,
) -> None:
    baseline = _restart_context(certificate_fixture)
    request = certificate_fixture.request
    first_leaf, second_leaf = request.certificate.body.authority_leaves[:2]

    def unavailable_receipt(
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        expected_receipt_root: str | None,
    ) -> GovernanceCommitViewV2:
        if stream_ref == first_leaf.stream_ref:
            return _unavailable_view(request, expected_receipt_root)
        return baseline.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    unavailable = _commit(
        replace(
            baseline,
            store=_StoreProxy(baseline.store, view_hook=unavailable_receipt),
        ),
        request,
        certificate_fixture.source,
    )
    assert unavailable.failure is not None
    assert unavailable.failure.path == "/dependencies"

    def substituted_receipt(
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        expected_receipt_root: str | None,
    ) -> GovernanceCommitViewV2:
        if stream_ref == first_leaf.stream_ref:
            return baseline.store.load_commit_view_v2(
                scope_ref,
                second_leaf.stream_ref,
                second_leaf.transition_id,
            )
        return baseline.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    substituted = _commit(
        replace(
            baseline,
            store=_StoreProxy(baseline.store, view_hook=substituted_receipt),
        ),
        request,
        certificate_fixture.source,
    )
    assert substituted.failure is not None
    assert substituted.failure.path == "/dependencies"

    def cross_scope_head(scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        head = baseline.store.load_head_v2(scope_ref, stream_ref)
        if stream_ref == first_leaf.stream_ref:
            other_domain = replace(
                baseline.domain,
                scope_ref="scope:cross-bound-head",
                domain_root="",
            )
            return replace(
                head,
                domain_root=other_domain.domain_root,
                scope_ref=other_domain.scope_ref,
                head_root="",
            )
        return head

    cross_scope = _commit(
        replace(
            baseline,
            store=_StoreProxy(baseline.store, head_hook=cross_scope_head),
        ),
        request,
        certificate_fixture.source,
    )
    assert cross_scope.failure is not None
    assert cross_scope.failure.code is (
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )


def test_dependency_loader_rejects_duplicate_declared_streams(
    certificate_fixture: _Fixture,
) -> None:
    baseline = _restart_context(certificate_fixture)
    request = certificate_fixture.request
    snapshot = object.__getattribute__(certificate_fixture.source, "_snapshot")
    body = snapshot.certificate.body
    decision_view = baseline.store.load_commit_view_v2(
        request.scope_ref,
        body.decision_stream_ref,
        body.decision_transition_id,
        expected_receipt_root=body.decision_receipt_root,
    )
    assert decision_view.committed_transition is not None
    decision_receipt = decision_view.committed_transition.receipt
    decision_head = GovernanceHeadV2(
        domain_root=baseline.domain.domain_root,
        scope_ref=baseline.domain.scope_ref,
        stream_ref=decision_receipt.stream_ref,
        revision=decision_receipt.revision,
        parent_root=decision_receipt.parent_root,
        state_root=decision_receipt.state_root,
        transition_id=decision_receipt.transition_id,
        batch_root=decision_receipt.batch_root,
        head_root=decision_receipt.head_root,
    )
    forged_leaf = CommitCertificateAuthorityLeafV2.from_dict(
        body.authority_leaves[0].to_dict()
    )
    object.__setattr__(forged_leaf, "stream_ref", decision_receipt.stream_ref)
    object.__setattr__(forged_leaf, "revision", decision_receipt.revision)
    object.__setattr__(forged_leaf, "transition_id", decision_receipt.transition_id)
    object.__setattr__(forged_leaf, "head_root", decision_receipt.head_root)
    object.__setattr__(forged_leaf, "receipt_root", decision_receipt.receipt_root)
    forged_snapshot = CommitCertificateSnapshotV2.from_dict(snapshot.to_dict())
    object.__setattr__(
        forged_snapshot.certificate.body,
        "authority_leaves",
        (forged_leaf, *body.authority_leaves[1:]),
    )
    result = _load_dependency_heads(
        baseline.store,
        baseline.domain,
        request,
        forged_snapshot,
        decision_head=decision_head,
    )
    assert isinstance(result, GovernanceCommitAttemptV2)
    assert result.failure is not None
    assert result.failure.path == "/dependencies"


def test_reconciliation_and_finality_totality_fail_closed(
    certificate_fixture: _Fixture,
) -> None:
    context, committed, _ = _commit_and_rehydrate(certificate_fixture)
    decision = certificate_fixture.decision_state.snapshot

    def non_certificate_view(
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        expected_receipt_root: str | None,
    ) -> GovernanceCommitViewV2:
        if (
            stream_ref == certificate_fixture.request.stream_ref
            and transition_id == certificate_fixture.request.transition_id
        ):
            return context.store.load_commit_view_v2(
                scope_ref,
                decision.stream_ref,
                decision.transition_id,
            )
        return context.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    proxy = _StoreProxy(context.store, view_hook=non_certificate_view)
    retried = _commit(
        replace(context, store=proxy),
        certificate_fixture.request,
        certificate_fixture.source,
    )
    assert retried.disposition is not GovernanceCommitDispositionV2.COMMITTED
    assert retried.failure is not None
    assert committed.disposition is GovernanceCommitDispositionV2.COMMITTED

    unavailable = _unavailable_view(certificate_fixture.request, None)
    propagated = _finality_failure(certificate_fixture.request, unavailable)
    assert propagated.failure == unavailable.failure
    without_failure = object.__new__(GovernanceCommitViewV2)
    object.__setattr__(without_failure, "failure", None)
    synthesized = _finality_failure(certificate_fixture.request, without_failure)
    assert synthesized.failure is not None
    assert synthesized.failure.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
    )


def test_state_record_and_session_binding_totality_rejects_exact_mutations(
    certificate_fixture: _Fixture,
) -> None:
    context, attempt, state = _commit_and_rehydrate(certificate_fixture)
    assert attempt.committed_transition is not None
    transition = attempt.committed_transition.batch.transition
    assert transition is not None
    records = dict(transition.state_records)
    binding = dict(records["session_binding"])  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="state must be an exact object"):
        _decode_state_records_v2((), context.domain)
    wrong_domain = dict(records)
    wrong_domain["domain_root"] = _root("wrong-state-domain")
    with pytest.raises(ValueError, match="state domain is mismatched"):
        _decode_state_records_v2(wrong_domain, context.domain)
    wrong_payload = dict(records)
    wrong_payload["stream_ref"] = "authority:wrong-state-stream"
    with pytest.raises(ValueError, match="state payload is mismatched"):
        _decode_state_records_v2(wrong_payload, context.domain)

    with pytest.raises(ValueError, match="binding fields are invalid"):
        _validate_session_binding_v2((), certificate_fixture.request)
    wrong_binding = dict(binding)
    wrong_binding["request_ref"] = "mutation:wrong-binding"
    with pytest.raises(ValueError, match="session binding is mismatched"):
        _validate_session_binding_v2(wrong_binding, certificate_fixture.request)
    wrong_grant = dict(binding)
    wrong_grant["grant_ref"] = ""
    with pytest.raises(ValueError, match="grant binding is invalid"):
        _validate_session_binding_v2(wrong_grant, certificate_fixture.request)
    assert state.snapshot.snapshot_root == records["snapshot_root"]


def test_read_set_totality_rejects_duplicate_and_nonclosed_sets(
    certificate_fixture: _Fixture,
) -> None:
    context, attempt, state = _commit_and_rehydrate(certificate_fixture)
    assert attempt.committed_transition is not None
    view = context.store.load_commit_view_v2(
        certificate_fixture.request.scope_ref,
        certificate_fixture.request.stream_ref,
        certificate_fixture.request.transition_id,
    )
    transition = attempt.committed_transition.batch.transition
    assert transition is not None
    binding = dict(transition.state_records["session_binding"])  # type: ignore[arg-type]

    assert view.committed_transition is not None
    read_set = view.committed_transition.batch.read_set
    object.__setattr__(
        read_set,
        "entries",
        (read_set.entries[0], *read_set.entries),
    )
    with pytest.raises(ValueError, match="duplicate streams"):
        _validate_read_set_v2(view, state.snapshot, binding)  # type: ignore[arg-type]

    view = context.store.load_commit_view_v2(
        certificate_fixture.request.scope_ref,
        certificate_fixture.request.stream_ref,
        certificate_fixture.request.transition_id,
    )
    nonclosed = dict(binding)
    nonclosed["lifecycle_expected_root"] = _root("wrong-lifecycle-root")
    with pytest.raises(ValueError, match="read set is not closed"):
        _validate_read_set_v2(view, state.snapshot, nonclosed)  # type: ignore[arg-type]


def test_historical_dependency_totality_rejects_decision_and_leaf_substitution(
    certificate_fixture: _Fixture,
) -> None:
    context, _, state = _commit_and_rehydrate(certificate_fixture)
    snapshot = state.snapshot
    body = snapshot.certificate.body

    def stale_decision(
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        expected_receipt_root: str | None,
    ) -> GovernanceCommitViewV2:
        if (
            stream_ref == body.decision_stream_ref
            and transition_id == body.decision_transition_id
        ):
            return context.store.load_commit_view_v2(
                scope_ref,
                stream_ref,
                body.seal_transition_id,
            )
        return context.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    with pytest.raises(ValueError, match="Decision dependency is mismatched"):
        _verify_historical_dependencies(
            snapshot,
            context.domain,
            _ReaderProxy(context.store, view_hook=stale_decision),
        )

    first_leaf, second_leaf = body.authority_leaves[:2]

    def substituted_leaf(
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        expected_receipt_root: str | None,
    ) -> GovernanceCommitViewV2:
        if stream_ref == first_leaf.stream_ref:
            return context.store.load_commit_view_v2(
                scope_ref,
                second_leaf.stream_ref,
                second_leaf.transition_id,
            )
        return context.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    with pytest.raises(ValueError, match="historical dependency is mismatched"):
        _verify_historical_dependencies(
            snapshot,
            context.domain,
            _ReaderProxy(context.store, view_hook=substituted_leaf),
        )


def test_seal_and_decision_binding_totality_rejects_each_semantic_gap(
    certificate_fixture: _Fixture,
) -> None:
    context, _, state = _commit_and_rehydrate(certificate_fixture)
    snapshot = state.snapshot
    body = snapshot.certificate.body
    current_view = context.store.load_commit_view_v2(
        snapshot.scope_ref,
        body.decision_stream_ref,
        body.decision_transition_id,
    )
    sealed_view = context.store.load_commit_view_v2(
        snapshot.scope_ref,
        body.decision_stream_ref,
        body.seal_transition_id,
    )

    substituted = False

    def nonseal_view(
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        expected_receipt_root: str | None,
    ) -> GovernanceCommitViewV2:
        nonlocal substituted
        if not substituted and transition_id == body.seal_transition_id:
            substituted = True
            return context.store.load_commit_view_v2(
                scope_ref,
                stream_ref,
                body.decision_transition_id,
            )
        return context.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    with pytest.raises(ValueError, match="seal inclusion is mismatched"):
        _verify_seal_inclusion(
            snapshot,
            context.domain,
            _ReaderProxy(context.store, view_hook=nonseal_view),
        )

    decision_snapshot = type(certificate_fixture.decision_state.snapshot).from_dict(
        certificate_fixture.decision_state.snapshot.to_dict()
    )
    sealed_snapshot = type(decision_snapshot).from_dict(decision_snapshot.to_dict())
    object.__setattr__(decision_snapshot, "seal", None)
    with pytest.raises(ValueError, match="Decision authority is incomplete"):
        _verify_decision_body_binding(
            snapshot,
            decision_snapshot=decision_snapshot,
            decision_view=current_view,
            sealed_snapshot=sealed_snapshot,
            sealed_view=sealed_view,
        )

    decision_snapshot = type(certificate_fixture.decision_state.snapshot).from_dict(
        certificate_fixture.decision_state.snapshot.to_dict()
    )
    sealed_snapshot = type(decision_snapshot).from_dict(decision_snapshot.to_dict())
    assert decision_snapshot.assessment is not None
    object.__setattr__(decision_snapshot.assessment, "candidate_metrics", ())
    with pytest.raises(ValueError, match="candidate is not evidence-ready"):
        _verify_decision_body_binding(
            snapshot,
            decision_snapshot=decision_snapshot,
            decision_view=current_view,
            sealed_snapshot=sealed_snapshot,
            sealed_view=sealed_view,
        )

    decision_snapshot = type(certificate_fixture.decision_state.snapshot).from_dict(
        certificate_fixture.decision_state.snapshot.to_dict()
    )
    sealed_snapshot = type(decision_snapshot).from_dict(decision_snapshot.to_dict())
    forged_certificate = CommitCertificateSnapshotV2.from_dict(snapshot.to_dict())
    object.__setattr__(
        forged_certificate.certificate.body,
        "candidate_ref",
        "candidate:forged-binding",
    )
    with pytest.raises(ValueError, match="not bound to Decision authority"):
        _verify_decision_body_binding(
            forged_certificate,
            decision_snapshot=decision_snapshot,
            decision_view=current_view,
            sealed_snapshot=sealed_snapshot,
            sealed_view=sealed_view,
        )


def test_bound_view_parent_history_and_head_totality(
    certificate_fixture: _Fixture,
) -> None:
    context, _, state = _commit_and_rehydrate(certificate_fixture)
    snapshot = state.snapshot
    unavailable = _ReaderProxy(
        context.store,
        view_hook=lambda _s, _r, _t, receipt: _unavailable_view(
            certificate_fixture.request,
            receipt,
        ),
    )
    with pytest.raises(ValueError, match="dependency is unavailable"):
        _load_bound_view(
            unavailable,
            snapshot,
            stream_ref=snapshot.certificate.body.authority_leaves[0].stream_ref,
            transition_id=snapshot.certificate.body.authority_leaves[0].transition_id,
            receipt_root=snapshot.certificate.body.authority_leaves[0].receipt_root,
        )

    forged_genesis = CommitCertificateSnapshotV2.from_dict(snapshot.to_dict())
    object.__setattr__(
        forged_genesis,
        "parent_transition_id",
        "transition:forged-genesis",
    )
    with pytest.raises(ValueError, match="genesis parent is invalid"):
        _verify_parent_history(forged_genesis, context.domain, context.store)

    with pytest.raises(ValueError, match="view has no transition"):
        _head_from_view_v2(
            _unavailable_view(certificate_fixture.request, None),
            context.domain,
        )


def test_parent_history_totality_rejects_committed_parent_substitution(
    certificate_fixture: _Fixture,
) -> None:
    context, _, first_state = _commit_and_rehydrate(certificate_fixture)
    second, second_source = _prepared_certificate(
        context,
        certificate_fixture.decision_state,
        mutation_ref="mutation:certificate:history:second",
        certificate_id="certificate:history:second",
        envelope_nonce="nonce:history:second",
        parent_state=first_state,
    )
    assert _commit(context, second, second_source).disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    second_state = rehydrate_commit_certificate_state_v2(
        second,
        domain=context.domain,
        state_reader=context.store,
    )
    forged = CommitCertificateSnapshotV2.from_dict(second_state.snapshot.to_dict())
    object.__setattr__(
        forged,
        "parent_history_root",
        _root("forged-parent-history"),
    )
    with pytest.raises(ValueError, match="historical parent is mismatched"):
        _verify_parent_history(forged, context.domain, context.store)


def test_committed_view_decoder_rejects_canonical_receipt_and_trace_substitution(
    certificate_fixture: _Fixture,
) -> None:
    build_context = _restart_context(certificate_fixture)
    first_attempt = _commit(
        build_context,
        certificate_fixture.request,
        certificate_fixture.source,
    )
    assert first_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert first_attempt.committed_transition is not None
    first_batch = first_attempt.committed_transition.batch
    first_transition = first_batch.transition
    assert first_transition is not None
    first_state = rehydrate_commit_certificate_state_v2(
        certificate_fixture.request,
        domain=build_context.domain,
        state_reader=build_context.store,
    )
    second_request, second_source = _prepared_certificate(
        build_context,
        certificate_fixture.decision_state,
        mutation_ref="mutation:certificate:decoder:second",
        certificate_id="certificate:decoder:second",
        envelope_nonce="nonce:decoder:second",
        parent_state=first_state,
    )
    second_attempt = _commit(build_context, second_request, second_source)
    assert second_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert second_attempt.committed_transition is not None
    second_transition = second_attempt.committed_transition.batch.transition
    assert second_transition is not None

    receipt_context = _restart_context(certificate_fixture)
    receipt_substituted_transition = replace(
        first_transition,
        state_records=second_transition.state_records,
        state_root="",
        transition_root="",
    )
    receipt_substituted_batch = replace(
        first_batch,
        transition=receipt_substituted_transition,
        transition_root=None,
        batch_root="",
    )
    receipt_commit = receipt_context.store.atomic_commit_v2(receipt_substituted_batch)
    assert receipt_commit.disposition is GovernanceCommitDispositionV2.COMMITTED
    receipt_view = receipt_context.store.load_commit_view_v2(
        certificate_fixture.request.scope_ref,
        certificate_fixture.request.stream_ref,
        certificate_fixture.request.transition_id,
    )
    with pytest.raises(ValueError, match="receipt is mismatched"):
        _decode_committed_certificate_view_v2(
            receipt_view,
            receipt_context.domain,
            reader=None,
        )

    trace_context = _restart_context(certificate_fixture)
    event = first_batch.trace_batch.events[0]
    substituted_trace = GovernanceTraceBatchV2(
        domain_root=first_batch.domain_root,
        scope_ref=first_batch.scope_ref,
        stream_ref=first_batch.stream_ref,
        transition_id=first_batch.transition_id,
        events=(
            replace(
                event,
                reason="canonical but semantically substituted certificate trace",
            ),
        ),
    )
    trace_substituted_batch = replace(
        first_batch,
        trace_batch=substituted_trace,
        trace_root="",
        batch_root="",
    )
    trace_commit = trace_context.store.atomic_commit_v2(trace_substituted_batch)
    assert trace_commit.disposition is GovernanceCommitDispositionV2.COMMITTED
    trace_view = trace_context.store.load_commit_view_v2(
        certificate_fixture.request.scope_ref,
        certificate_fixture.request.stream_ref,
        certificate_fixture.request.transition_id,
    )
    with pytest.raises(ValueError, match="Trace lineage is mismatched"):
        _decode_committed_certificate_view_v2(
            trace_view,
            trace_context.domain,
            reader=None,
        )
