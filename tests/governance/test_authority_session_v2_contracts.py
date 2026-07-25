from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import FrozenInstanceError, is_dataclass, replace
from hashlib import sha256
import json
import pickle

import pytest

from pheroos.governance.authority_store_v2 import (
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDomainV2,
)
from pheroos.governance._authority_session_v2 import contracts
from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceAuthoritySessionV2,
    GovernanceDomainRetirementRequestV2,
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    GovernanceVerifiedSignalRequestV2,
    IssuerGrantVerificationV2,
    IssuerGrantVerifierV2,
    _governance_authority_session_state_v2,
    _governance_issuer_capability_state_v2,
    _make_governance_authority_session_v2,
    _make_governance_issuer_capability_v2,
    governance_issuer_grant_stream_ref_v2,
    governance_verified_signal_stream_ref_v2,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    MAX_AUTHORITY_REVISION_V2,
    AuthorityDiagnosticCodeV2,
)


_ROOT_PREFIX = "pheroos-governance-authority-v2:"


def _root(character: str) -> str:
    return "sha256:" + character * 64


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _expected_root(kind: str, body: object) -> str:
    material = (_ROOT_PREFIX + kind).encode("utf-8") + b"\x00" + _canonical(body)
    return "sha256:" + sha256(material).hexdigest()


def _domain(
    *,
    scope_ref: str = "scope:alpha",
    profile: str = AUTHORITY_LOCAL_PROFILE_V2,
) -> AuthorityDomainV2:
    return AuthorityDomainV2(
        policy_version=AUTHORITY_POLICY_VERSION_V2,
        profile=profile,
        wire_version=AUTHORITY_WIRE_VERSION_V2,
        canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref=scope_ref,
    )


def _grant(
    domain: AuthorityDomainV2 | None = None,
    *,
    operations: tuple[GovernanceIssuerOperationV2, ...] = (
        GovernanceIssuerOperationV2.VERIFY_SIGNAL,
        GovernanceIssuerOperationV2.RETIRE_DOMAIN,
    ),
    target_refs: tuple[str, ...] = ("target:a", "target:b"),
    action_refs: tuple[str, ...] = ("action:publish",),
) -> GovernanceIssuerGrantV2:
    selected = _domain() if domain is None else domain
    return GovernanceIssuerGrantV2(
        domain_root=selected.domain_root,
        scope_ref=selected.scope_ref,
        issuer_ref="issuer:host",
        grant_ref="grant:alpha",
        grant_binding_ref=_root("b"),
        operations=operations,
        target_refs=target_refs,
        action_refs=action_refs,
        issued_epoch=1,
        not_before_epoch=2,
        expires_at_epoch=9,
        revocation_generation=0,
    )


def _verification(
    grant: GovernanceIssuerGrantV2,
    *,
    accepted: bool = True,
    observed_epoch: int = 5,
) -> IssuerGrantVerificationV2:
    return IssuerGrantVerificationV2(
        grant_root=grant.grant_root,
        grant_binding_ref=grant.grant_binding_ref,
        verifier_ref="verifier:host",
        accepted=accepted,
        verified_epoch=observed_epoch,
    )


def _signal_request(
    domain: AuthorityDomainV2 | None = None,
    **overrides: object,
) -> GovernanceVerifiedSignalRequestV2:
    selected = _domain() if domain is None else domain
    values: dict[str, object] = {
        "domain_root": selected.domain_root,
        "scope_ref": selected.scope_ref,
        "run_ref": "run:alpha",
        "request_ref": "request:signal:1",
        "transition_id": "transition:signal:1",
        "signal_ref": "signal:1",
        "target_ref": "target:a",
        "signal_root": _root("c"),
        "evidence_root": _root("d"),
        "status": "verified",
        "observed_epoch": 5,
    }
    values.update(overrides)
    return GovernanceVerifiedSignalRequestV2(**values)  # type: ignore[arg-type]


def _retirement_request(
    domain: AuthorityDomainV2 | None = None,
    **overrides: object,
) -> GovernanceDomainRetirementRequestV2:
    selected = _domain() if domain is None else domain
    streams = tuple(
        sorted(
            (
                governance_issuer_grant_stream_ref_v2(
                    selected.scope_ref,
                    "grant:alpha",
                ),
                governance_verified_signal_stream_ref_v2(
                    selected.scope_ref,
                    "signal:1",
                    "target:a",
                ),
            ),
            key=lambda value: value.encode("utf-8"),
        )
    )
    values: dict[str, object] = {
        "domain_root": selected.domain_root,
        "scope_ref": selected.scope_ref,
        "run_ref": "run:alpha",
        "request_ref": "request:retire:1",
        "transition_id": "transition:retire:1",
        "stream_refs": streams,
        "reason_ref": "reason:complete",
        "observed_epoch": 5,
    }
    values.update(overrides)
    return GovernanceDomainRetirementRequestV2(**values)  # type: ignore[arg-type]


def _capability(
    *,
    store: object | None = None,
    domain: AuthorityDomainV2 | None = None,
    grant: GovernanceIssuerGrantV2 | None = None,
    run_ref: str = "run:alpha",
    verification: IssuerGrantVerificationV2 | None = None,
) -> tuple[GovernanceIssuerCapabilityV2, object, AuthorityDomainV2]:
    selected_store = object() if store is None else store
    selected_domain = _domain() if domain is None else domain
    selected_grant = _grant(selected_domain) if grant is None else grant
    handle = _make_governance_issuer_capability_v2(
        store=selected_store,
        domain=selected_domain,
        grant=selected_grant,
        run_ref=run_ref,
        observed_epoch=5,
        verification=verification,
    )
    return handle, selected_store, selected_domain


def _session(
    *,
    capability: GovernanceIssuerCapabilityV2 | None = None,
) -> GovernanceAuthoritySessionV2:
    selected = _capability()[0] if capability is None else capability
    return _make_governance_authority_session_v2(
        capability=selected,
        request_ref="request:signal:1",
        request_root=_root("e"),
        operation=GovernanceIssuerOperationV2.VERIFY_SIGNAL,
        run_ref="run:alpha",
        observed_epoch=5,
        grant_expected_revision=1,
        grant_expected_root=_root("f"),
        lifecycle_expected_revision=0,
        lifecycle_expected_root=_root("0"),
        target_refs=("target:a",),
        action_refs=(),
    )


def test_issuer_operation_registry_is_exact_closed_and_canonically_ordered() -> None:
    assert tuple((item.name, item.value) for item in GovernanceIssuerOperationV2) == (
        ("VERIFY_SIGNAL", "verify_signal"),
        ("EVALUATE_QUORUM", "evaluate_quorum"),
        ("QUALIFY_EVIDENCE", "qualify_evidence"),
        ("RESOLVE_STOP", "resolve_stop"),
        ("ADVANCE_REPLAY", "advance_replay"),
        ("ISSUE_ACTION_PERMISSION", "issue_action_permission"),
        ("AUTHORIZE_OUTPUT", "authorize_output"),
        ("RETIRE_DOMAIN", "retire_domain"),
    )
    grant = _grant(operations=tuple(GovernanceIssuerOperationV2))
    assert grant.operations == tuple(GovernanceIssuerOperationV2)
    with pytest.raises(ValueError, match="canonical enum order"):
        _grant(
            operations=(
                GovernanceIssuerOperationV2.RETIRE_DOMAIN,
                GovernanceIssuerOperationV2.VERIFY_SIGNAL,
            )
        )


def test_grant_is_frozen_slotted_portable_and_rooted_independently() -> None:
    grant = _grant()
    assert is_dataclass(grant)
    assert not hasattr(grant, "__dict__")
    with pytest.raises(FrozenInstanceError):
        grant.grant_ref = "grant:changed"  # type: ignore[misc]
    wire = grant.to_dict()
    body = {key: value for key, value in wire.items() if key != "grant_root"}
    assert grant.grant_root == _expected_root("issuer-grant", body)
    assert grant.root() == grant.grant_root
    assert grant.canonical_bytes() == _canonical(wire)
    assert GovernanceIssuerGrantV2.from_dict(wire) == grant
    assert GovernanceIssuerGrantV2.from_dict(wire).to_dict() is not wire
    assert pickle.loads(pickle.dumps(grant)) == grant


@pytest.mark.parametrize(
    ("changes", "exception"),
    [
        ({"issued_epoch": True}, ValueError),
        ({"not_before_epoch": 10}, ValueError),
        ({"expires_at_epoch": MAX_AUTHORITY_REVISION_V2 + 1}, ValueError),
        ({"grant_binding_ref": "SHA256:" + "a" * 64}, ValueError),
        ({"scope_ref": "scope:e\u0301"}, ValueError),
        ({"target_refs": ["target:a"]}, TypeError),
        ({"target_refs": ("target:a", "target:a")}, ValueError),
        ({"target_refs": ("target:b", "target:a")}, ValueError),
        ({"operations": ()}, TypeError),
        (
            {
                "operations": (
                    GovernanceIssuerOperationV2.VERIFY_SIGNAL,
                    GovernanceIssuerOperationV2.VERIFY_SIGNAL,
                )
            },
            ValueError,
        ),
    ],
)
def test_grant_rejects_noncanonical_values(
    changes: dict[str, object],
    exception: type[Exception],
) -> None:
    with pytest.raises(exception):
        replace(_grant(), **changes)


def test_grant_strict_wire_rejects_extensions_missing_fields_and_root_tamper() -> None:
    wire = _grant().to_dict()
    with pytest.raises(ValueError, match="fields"):
        GovernanceIssuerGrantV2.from_dict({**wire, "extension": True})
    missing = dict(wire)
    missing.pop("issuer_ref")
    with pytest.raises(ValueError, match="fields"):
        GovernanceIssuerGrantV2.from_dict(missing)
    with pytest.raises(ValueError, match="mismatched"):
        GovernanceIssuerGrantV2.from_dict({**wire, "grant_root": _root("9")})
    with pytest.raises(TypeError):
        GovernanceIssuerGrantV2.from_dict(tuple(wire.items()))
    with pytest.raises(TypeError, match="exact text"):
        GovernanceIssuerGrantV2.from_dict(
            {
                **wire,
                "operations": list(_grant().operations),
            }
        )


def test_issuer_verification_is_strict_portable_and_rooted() -> None:
    verification = _verification(_grant())
    wire = verification.to_dict()
    body = {key: value for key, value in wire.items() if key != "verification_root"}
    assert verification.verification_root == _expected_root(
        "issuer-grant-verification",
        body,
    )
    assert IssuerGrantVerificationV2.from_dict(wire) == verification
    assert not hasattr(verification, "__dict__")
    with pytest.raises(TypeError, match="exact bool"):
        replace(verification, accepted=1)
    with pytest.raises(ValueError, match="mismatched"):
        replace(verification, verification_root=_root("8"))


def test_issuer_verifier_protocol_is_runtime_checkable() -> None:
    class Verifier:
        def verify_issuer_grant_v2(
            self,
            grant: GovernanceIssuerGrantV2,
            *,
            observed_epoch: int,
        ) -> IssuerGrantVerificationV2:
            return _verification(grant, observed_epoch=observed_epoch)

    assert isinstance(Verifier(), IssuerGrantVerifierV2)
    assert not isinstance(object(), IssuerGrantVerifierV2)


def test_stream_refs_are_exact_sha256_nfc_utf8_derivations() -> None:
    grant_material = b"scope:alpha\x00grant:alpha"
    expected_grant = "authority:issuer-grant:" + sha256(grant_material).hexdigest()
    assert (
        governance_issuer_grant_stream_ref_v2("scope:alpha", "grant:alpha")
        == expected_grant
    )
    signal_material = b"scope:alpha\x00signal:1\x00target:a"
    expected_signal = "authority:verified-signal:" + sha256(signal_material).hexdigest()
    assert (
        governance_verified_signal_stream_ref_v2(
            "scope:alpha",
            "signal:1",
            "target:a",
        )
        == expected_signal
    )
    assert governance_issuer_grant_stream_ref_v2(
        "scope:alpha", "grant:alpha"
    ) != governance_issuer_grant_stream_ref_v2("scope:beta", "grant:alpha")
    with pytest.raises(ValueError, match="NFC"):
        governance_issuer_grant_stream_ref_v2("scope:e\u0301", "grant:alpha")


def test_verified_signal_request_binds_request_transition_stream_and_roots() -> None:
    request = _signal_request()
    assert request.stream_ref == governance_verified_signal_stream_ref_v2(
        request.scope_ref,
        request.signal_ref,
        request.target_ref,
    )
    wire = request.to_dict()
    assert wire["request_ref"] == "request:signal:1"
    assert wire["transition_id"] == "transition:signal:1"
    body = {key: value for key, value in wire.items() if key != "request_root"}
    assert request.request_root == _expected_root("verified-signal-request", body)
    assert GovernanceVerifiedSignalRequestV2.from_dict(wire) == request
    assert request.canonical_bytes() == _canonical(wire)


@pytest.mark.parametrize(
    "changes",
    [
        {"status": True},
        {"status": "pending"},
        {"observed_epoch": False},
        {"request_ref": "request:e\u0301"},
        {"transition_id": " transition:1"},
        {"transition_id": "genesis"},
        {"signal_root": "sha256:" + "A" * 64},
        {"stream_ref": "authority:verified-signal:wrong"},
        {"request_root": _root("7")},
    ],
)
def test_verified_signal_request_rejects_noncanonical_or_mismatched_values(
    changes: dict[str, object],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(_signal_request(), **changes)


def test_retirement_request_binds_complete_sorted_stream_set_and_root() -> None:
    request = _retirement_request()
    wire = request.to_dict()
    assert wire["request_ref"] == "request:retire:1"
    assert wire["transition_id"] == "transition:retire:1"
    body = {key: value for key, value in wire.items() if key != "request_root"}
    assert request.request_root == _expected_root("domain-retirement-request", body)
    assert GovernanceDomainRetirementRequestV2.from_dict(wire) == request
    assert (
        GovernanceDomainRetirementRequestV2(
            domain_root=request.domain_root,
            scope_ref=request.scope_ref,
            run_ref=request.run_ref,
            request_ref="request:retire:empty",
            transition_id="transition:retire:empty",
            stream_refs=(),
            reason_ref=request.reason_ref,
            observed_epoch=request.observed_epoch,
        ).stream_refs
        == ()
    )


def test_retirement_request_rejects_invalid_stream_sets_and_bindings() -> None:
    request = _retirement_request()
    with pytest.raises(TypeError):
        replace(request, stream_refs=list(request.stream_refs))
    with pytest.raises(ValueError, match="unique"):
        replace(request, stream_refs=(request.stream_refs[0],) * 2)
    with pytest.raises(ValueError, match="sorted"):
        replace(request, stream_refs=tuple(reversed(request.stream_refs)))
    with pytest.raises(ValueError, match="bound"):
        replace(
            request, stream_refs=tuple(f"authority:{index:03d}" for index in range(128))
        )
    with pytest.raises(ValueError, match="NFC"):
        replace(request, request_ref="request:e\u0301")
    with pytest.raises(ValueError, match="reserved"):
        replace(request, transition_id="genesis")
    with pytest.raises(ValueError, match="mismatched"):
        replace(request, request_root=_root("6"))


def test_binding_error_has_exact_protocol_code_and_json_pointer() -> None:
    error = GovernanceAuthorityBindingErrorV2(
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
        "/request_ref",
    )
    assert error.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    assert error.path == "/request_ref"
    assert str(error) == "authority_binding_mismatch:/request_ref"
    with pytest.raises(TypeError):
        GovernanceAuthorityBindingErrorV2("authority_binding_mismatch", "")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="escape"):
        GovernanceAuthorityBindingErrorV2(
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/bad~2path",
        )


def test_capability_retains_exact_store_domain_and_nonsecret_bindings() -> None:
    domain = _domain(profile=AUTHORITY_AUTHENTICATED_PROFILE_V2)
    grant = _grant(domain)
    verification = _verification(grant)
    store = object()
    capability, _, _ = _capability(
        store=store,
        domain=domain,
        grant=grant,
        verification=verification,
    )
    state = _governance_issuer_capability_state_v2(capability)
    assert state.store is store
    assert state.domain is domain
    assert state.grant is not grant
    assert state.grant == grant
    assert capability.profile == domain.profile
    assert capability.domain_root == domain.domain_root
    assert capability.scope_ref == domain.scope_ref
    assert capability.run_ref == "run:alpha"
    assert capability.grant_ref == grant.grant_ref
    assert capability.grant_root == grant.grant_root
    assert capability.operations == grant.operations
    assert capability.verifier_ref == "verifier:host"
    assert capability.verification_root == verification.verification_root


def test_capability_local_profile_allows_no_manufactured_verification() -> None:
    capability, _, _ = _capability()
    state = _governance_issuer_capability_state_v2(capability)
    assert state.verification is None
    assert capability.verifier_ref is None
    assert capability.verification_root is None
    local_domain = _domain()
    local_grant = _grant(local_domain)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as manufactured:
        _make_governance_issuer_capability_v2(
            store=object(),
            domain=local_domain,
            grant=local_grant,
            run_ref="run:alpha",
            observed_epoch=5,
            verification=_verification(local_grant),
        )
    assert (
        manufactured.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )


def test_capability_is_final_opaque_identity_preserving_and_nonportable() -> None:
    capability, _, _ = _capability()
    assert not is_dataclass(capability)
    assert not hasattr(capability, "__dict__")
    assert not hasattr(capability, "to_dict")
    assert not hasattr(capability, "from_dict")
    assert copy(capability) is capability
    assert deepcopy(capability) is capability
    assert repr(capability) == "<GovernanceIssuerCapabilityV2 redacted>"
    assert "scope:alpha" not in repr(capability)
    with pytest.raises(TypeError):
        GovernanceIssuerCapabilityV2()
    with pytest.raises(TypeError):
        pickle.dumps(capability)
    with pytest.raises(TypeError):
        capability.__reduce__()
    with pytest.raises(TypeError):
        capability.__reduce_ex__(5)
    with pytest.raises(TypeError):

        class ForgedCapability(GovernanceIssuerCapabilityV2):
            pass


def test_capability_reconstruction_reflection_and_slot_copy_fail_closed() -> None:
    capability, _, _ = _capability()
    forged = object.__new__(GovernanceIssuerCapabilityV2)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as uninitialized:
        _governance_issuer_capability_state_v2(forged)
    assert (
        uninitialized.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED
    )
    object.__setattr__(
        forged,
        "_state",
        object.__getattribute__(capability, "_state"),
    )
    object.__setattr__(
        forged,
        "_token",
        object.__getattribute__(capability, "_token"),
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as copied_slots:
        _governance_issuer_capability_state_v2(forged)
    assert (
        copied_slots.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        _governance_issuer_capability_state_v2(object())


def test_capability_factory_rejects_scope_epoch_and_verification_mismatch() -> None:
    domain = _domain(profile=AUTHORITY_AUTHENTICATED_PROFILE_V2)
    grant = _grant(domain)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as scope:
        _make_governance_issuer_capability_v2(
            store=object(),
            domain=_domain(scope_ref="scope:other"),
            grant=grant,
            run_ref="run:alpha",
            observed_epoch=5,
        )
    assert scope.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as expired:
        _make_governance_issuer_capability_v2(
            store=object(),
            domain=domain,
            grant=grant,
            run_ref="run:alpha",
            observed_epoch=10,
        )
    assert expired.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as missing:
        _make_governance_issuer_capability_v2(
            store=object(),
            domain=domain,
            grant=grant,
            run_ref="run:alpha",
            observed_epoch=5,
        )
    assert missing.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as denied:
        _make_governance_issuer_capability_v2(
            store=object(),
            domain=domain,
            grant=grant,
            run_ref="run:alpha",
            observed_epoch=5,
            verification=_verification(grant, accepted=False),
        )
    assert denied.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED


def test_capability_tamper_is_detected_by_private_snapshot() -> None:
    capability, _, _ = _capability()
    state = _governance_issuer_capability_state_v2(capability)
    object.__setattr__(state, "run_ref", "run:tampered")
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as tampered:
        _governance_issuer_capability_state_v2(capability)
    assert tampered.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH


def test_malformed_private_snapshot_shapes_fail_with_typed_binding_errors() -> None:
    capability, _, _ = _capability()
    capability_state = _governance_issuer_capability_state_v2(capability)
    object.__setattr__(
        capability,
        "_state",
        replace(capability_state, _snapshot=()),
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as malformed_capability:
        _governance_issuer_capability_state_v2(capability)
    assert (
        malformed_capability.value.code
        is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )

    session = _session()
    session_state = _governance_authority_session_state_v2(session)
    object.__setattr__(
        session,
        "_state",
        replace(session_state, _snapshot=()),
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as malformed_session:
        _governance_authority_session_state_v2(session)
    assert (
        malformed_session.value.code
        is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )


def test_session_retains_exact_store_capability_and_request_bindings() -> None:
    capability, store, domain = _capability()
    session = _session(capability=capability)
    state = _governance_authority_session_state_v2(session)
    assert state.store is store
    assert state.capability is capability
    assert session.profile == domain.profile
    assert session.domain_root == domain.domain_root
    assert session.scope_ref == domain.scope_ref
    assert session.run_ref == capability.run_ref
    assert session.request_ref == "request:signal:1"
    assert session.request_root == _root("e")
    assert session.operation is GovernanceIssuerOperationV2.VERIFY_SIGNAL
    assert session.observed_epoch == 5
    assert session.grant_expected_revision == 1
    assert session.lifecycle_expected_revision == 0
    assert session.target_refs == ("target:a",)
    assert session.action_refs == ()


def test_session_is_final_opaque_identity_preserving_and_nonportable() -> None:
    session = _session()
    assert not is_dataclass(session)
    assert not hasattr(session, "__dict__")
    assert not hasattr(session, "to_dict")
    assert not hasattr(session, "from_dict")
    assert copy(session) is session
    assert deepcopy(session) is session
    assert repr(session) == "<GovernanceAuthoritySessionV2 redacted>"
    assert "request:signal:1" not in repr(session)
    with pytest.raises(TypeError):
        GovernanceAuthoritySessionV2()
    with pytest.raises(TypeError):
        pickle.dumps(session)
    with pytest.raises(TypeError):
        session.__reduce__()
    with pytest.raises(TypeError):
        session.__reduce_ex__(5)
    with pytest.raises(TypeError):

        class ForgedSession(GovernanceAuthoritySessionV2):
            pass


def test_session_reconstruction_and_copied_slots_fail_closed() -> None:
    session = _session()
    forged = object.__new__(GovernanceAuthoritySessionV2)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as uninitialized:
        _governance_authority_session_state_v2(forged)
    assert (
        uninitialized.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED
    )
    object.__setattr__(forged, "_state", object.__getattribute__(session, "_state"))
    object.__setattr__(forged, "_token", object.__getattribute__(session, "_token"))
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as copied_slots:
        _governance_authority_session_state_v2(forged)
    assert (
        copied_slots.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    )


def test_session_factory_enforces_run_operation_epoch_and_declared_bounds() -> None:
    capability, _, _ = _capability()
    base = {
        "capability": capability,
        "request_ref": "request:1",
        "request_root": _root("e"),
        "operation": GovernanceIssuerOperationV2.VERIFY_SIGNAL,
        "run_ref": "run:alpha",
        "observed_epoch": 5,
        "grant_expected_revision": 1,
        "grant_expected_root": _root("f"),
        "lifecycle_expected_revision": 0,
        "lifecycle_expected_root": _root("0"),
        "target_refs": ("target:a",),
        "action_refs": (),
    }
    cases = (
        (
            {"run_ref": "run:other"},
            AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
            "/run_ref",
        ),
        (
            {"operation": GovernanceIssuerOperationV2.AUTHORIZE_OUTPUT},
            AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
            "/operation",
        ),
        (
            {"observed_epoch": 10},
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED,
            "/observed_epoch",
        ),
        (
            {"target_refs": ("target:other",)},
            AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
            "/target_refs",
        ),
        (
            {"action_refs": ("action:execute",)},
            AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
            "/action_refs",
        ),
    )
    for changes, code, path in cases:
        with pytest.raises(GovernanceAuthorityBindingErrorV2) as error:
            _make_governance_authority_session_v2(**{**base, **changes})  # type: ignore[arg-type]
        assert (error.value.code, error.value.path) == (code, path)


def test_empty_grant_target_bound_is_not_a_target_wildcard() -> None:
    domain = _domain()
    grant = _grant(domain, target_refs=(), action_refs=())
    capability = _make_governance_issuer_capability_v2(
        store=object(),
        domain=domain,
        grant=grant,
        run_ref="run:alpha",
        observed_epoch=5,
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as denied:
        _make_governance_authority_session_v2(
            capability=capability,
            request_ref="request:signal:1",
            request_root=_root("e"),
            operation=GovernanceIssuerOperationV2.VERIFY_SIGNAL,
            run_ref="run:alpha",
            observed_epoch=5,
            grant_expected_revision=1,
            grant_expected_root=_root("f"),
            lifecycle_expected_revision=0,
            lifecycle_expected_root=_root("0"),
            target_refs=("target:a",),
            action_refs=(),
        )
    assert (denied.value.code, denied.value.path) == (
        AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
        "/target_refs",
    )


def test_targetless_retirement_session_accepts_empty_grant_bounds() -> None:
    domain = _domain()
    grant = _grant(
        domain,
        operations=(GovernanceIssuerOperationV2.RETIRE_DOMAIN,),
        target_refs=(),
        action_refs=(),
    )
    capability = _make_governance_issuer_capability_v2(
        store=object(),
        domain=domain,
        grant=grant,
        run_ref="run:alpha",
        observed_epoch=5,
    )
    session = _make_governance_authority_session_v2(
        capability=capability,
        request_ref="request:retire:1",
        request_root=_root("e"),
        operation=GovernanceIssuerOperationV2.RETIRE_DOMAIN,
        run_ref="run:alpha",
        observed_epoch=5,
        grant_expected_revision=1,
        grant_expected_root=_root("f"),
        lifecycle_expected_revision=0,
        lifecycle_expected_root=_root("0"),
        target_refs=(),
        action_refs=(),
    )
    assert session.target_refs == ()
    assert session.action_refs == ()


def test_session_tamper_and_cross_store_identity_fail_closed() -> None:
    store_a = object()
    store_b = object()
    capability_a, _, _ = _capability(store=store_a)
    capability_b, _, _ = _capability(store=store_b)
    session_a = _session(capability=capability_a)
    session_b = _session(capability=capability_b)
    assert _governance_authority_session_state_v2(session_a).store is store_a
    assert _governance_authority_session_state_v2(session_b).store is store_b
    assert store_a is not store_b
    state = _governance_authority_session_state_v2(session_a)
    object.__setattr__(state, "store", store_b)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as tampered:
        _governance_authority_session_state_v2(session_a)
    assert tampered.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH


def test_contract_source_uses_exact_objects_without_store_registry_or_ids() -> None:
    source = contracts.__loader__.get_source(contracts.__name__)  # type: ignore[union-attr]
    assert source is not None
    assert "id(store)" not in source
    assert "WeakKeyDictionary" not in source
    assert "store_registry" not in source
    assert "state.store is not" in source


def test_authority_stream_bindings_reject_nul_delimiter_aliases() -> None:
    assert b"\x00".join(
        value.encode("utf-8") for value in ("scope:a\x00grant", "x")
    ) == b"\x00".join(value.encode("utf-8") for value in ("scope:a", "grant\x00x"))
    for scope_ref, grant_ref in (
        ("scope:a\x00grant", "x"),
        ("scope:a", "grant\x00x"),
    ):
        with pytest.raises(ValueError, match=r"U\+0000"):
            governance_issuer_grant_stream_ref_v2(scope_ref, grant_ref)

    with pytest.raises(ValueError, match=r"U\+0000"):
        governance_verified_signal_stream_ref_v2("scope:a", "signal\x00target", "x")
