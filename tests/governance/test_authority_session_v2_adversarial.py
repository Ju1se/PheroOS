from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest

from pheroos.conformance.checks.authority_store_v2_contract import (
    ReferenceGovernanceStateStoreConformanceAdapterV2,
)
import pheroos.governance._authority_session_v2.operations as authority_operations
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceDomainRetirementRequestV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    GovernanceVerifiedSignalRequestV2,
    IssuerGrantVerificationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    commit_verified_signal_v2,
    governance_issuer_grant_stream_ref_v2,
    open_governance_authority_session_v2,
    retire_governance_domain_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitViewV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
)
from pheroos.protocol.authority_v2 import (
    MAX_AUTHORITY_REVISION_V2,
    AuthorityDiagnosticCodeV2,
)


_ADAPTER = ReferenceGovernanceStateStoreConformanceAdapterV2()


def _root(digit: str) -> str:
    return f"sha256:{digit * 64}"


def _domain(
    scope_ref: str, *, profile: str = AUTHORITY_LOCAL_PROFILE_V2
) -> AuthorityDomainV2:
    local = _ADAPTER.create_domain_v2(scope_ref)
    if profile == AUTHORITY_LOCAL_PROFILE_V2:
        return local
    return AuthorityDomainV2(
        policy_version=local.policy_version,
        profile=profile,
        wire_version=local.wire_version,
        canonical_version=local.canonical_version,
        ledger_version=local.ledger_version,
        state_store_version=local.state_store_version,
        trace_batch_version=local.trace_batch_version,
        read_set_version=local.read_set_version,
        scope_ref=local.scope_ref,
    )


def _grant(
    domain: AuthorityDomainV2,
    *,
    grant_ref: str = "grant:adversarial",
    operations: tuple[GovernanceIssuerOperationV2, ...] = (
        GovernanceIssuerOperationV2.VERIFY_SIGNAL,
        GovernanceIssuerOperationV2.RETIRE_DOMAIN,
    ),
    target_refs: tuple[str, ...] = ("target:alpha",),
    issued_epoch: int = 1,
    expires_at_epoch: int = 100,
    revocation_generation: int = 0,
) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:adversarial",
        grant_ref=grant_ref,
        grant_binding_ref=_root("1"),
        operations=operations,
        target_refs=target_refs,
        action_refs=(),
        issued_epoch=issued_epoch,
        not_before_epoch=issued_epoch,
        expires_at_epoch=expires_at_epoch,
        revocation_generation=revocation_generation,
    )


def _signal(
    domain: AuthorityDomainV2,
    *,
    request_ref: str = "request:adversarial",
    transition_id: str = "transition:adversarial",
    observed_epoch: int = 2,
    run_ref: str = "run:adversarial",
    target_ref: str = "target:alpha",
) -> GovernanceVerifiedSignalRequestV2:
    return GovernanceVerifiedSignalRequestV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        run_ref=run_ref,
        request_ref=request_ref,
        transition_id=transition_id,
        signal_ref=f"signal:{request_ref}",
        target_ref=target_ref,
        signal_root=_root("2"),
        evidence_root=_root("3"),
        status="verified",
        observed_epoch=observed_epoch,
    )


def _retirement(
    domain: AuthorityDomainV2,
    stream_refs: tuple[str, ...],
    *,
    request_ref: str = "request:retire",
    transition_id: str = "transition:retire",
    observed_epoch: int = 3,
) -> GovernanceDomainRetirementRequestV2:
    return GovernanceDomainRetirementRequestV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        run_ref="run:adversarial",
        request_ref=request_ref,
        transition_id=transition_id,
        stream_refs=tuple(sorted(stream_refs, key=lambda item: item.encode("utf-8"))),
        reason_ref="reason:adversarial",
        observed_epoch=observed_epoch,
    )


class _BoundaryStore:
    """Public StateStore boundary wrapper with test-selected hostile reads."""

    def __init__(self, delegate: GovernanceStateStoreV2) -> None:
        self.delegate = delegate
        self.version: object = GOVERNANCE_STATE_STORE_VERSION_V2
        self.raise_version: Exception | None = None
        self.raise_version_after: int | None = None
        self.version_reads = 0
        self.head_hook: Any = None
        self.state_hook: Any = None
        self.view_hook: Any = None
        self.atomic_commit_calls = 0

    @property
    def state_store_version(self) -> str:
        self.version_reads += 1
        if self.raise_version is not None:
            raise self.raise_version
        if (
            self.raise_version_after is not None
            and self.version_reads > self.raise_version_after
        ):
            raise RuntimeError("version changed during authority operation")
        return cast(str, self.version)

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        value = self.delegate.load_head_v2(scope_ref, stream_ref)
        if self.head_hook is not None:
            return cast(GovernanceHeadV2, self.head_hook(scope_ref, stream_ref, value))
        return value

    def load_state_v2(self, scope_ref: str, stream_ref: str) -> Mapping[str, Any]:
        value = self.delegate.load_state_v2(scope_ref, stream_ref)
        if self.state_hook is not None:
            return cast(
                Mapping[str, Any], self.state_hook(scope_ref, stream_ref, value)
            )
        return value

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        value = self.delegate.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )
        if self.view_hook is not None:
            return cast(
                GovernanceCommitViewV2,
                self.view_hook(scope_ref, stream_ref, transition_id, value),
            )
        return value

    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        self.atomic_commit_calls += 1
        return self.delegate.atomic_commit_v2(batch)


class _ExplodingProtocolShape:
    @property
    def state_store_version(self) -> str:
        return GOVERNANCE_STATE_STORE_VERSION_V2

    def __getattr__(self, name: str) -> object:
        raise RuntimeError(f"hostile protocol reflection:{name}")


class _WrongResultVerifier:
    def verify_issuer_grant_v2(
        self,
        grant: GovernanceIssuerGrantV2,
        *,
        observed_epoch: int,
    ) -> IssuerGrantVerificationV2:
        return cast(IssuerGrantVerificationV2, object())


class _AcceptingVerifier:
    def verify_issuer_grant_v2(
        self,
        grant: GovernanceIssuerGrantV2,
        *,
        observed_epoch: int,
    ) -> IssuerGrantVerificationV2:
        return IssuerGrantVerificationV2(
            grant_root=grant.grant_root,
            grant_binding_ref=grant.grant_binding_ref,
            verifier_ref="verifier:adversarial-tests",
            accepted=True,
            verified_epoch=observed_epoch,
        )


def _store(domain: AuthorityDomainV2) -> _BoundaryStore:
    raw = _ADAPTER.create_store_v2((domain,))
    store = _BoundaryStore(raw)
    assert isinstance(store, GovernanceStateStoreV2)
    return store


def _activate(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    *,
    transition_id: str = "transition:activate",
    observed_epoch: int = 1,
) -> GovernanceCommitAttemptV2:
    attempt = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        transition_id,
        observed_epoch,
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    return attempt


def _assert_code(
    attempt: GovernanceCommitAttemptV2,
    code: AuthorityDiagnosticCodeV2,
) -> None:
    assert attempt.failure is not None
    assert attempt.failure.code is code
    assert attempt.committed_transition is None


def test_public_entrypoints_reject_noncanonical_inputs_and_hostile_store_shapes() -> (
    None
):
    domain = _domain("scope:authority-session:input-boundaries")
    other = _domain("scope:authority-session:input-other")
    grant = _grant(domain)
    store = _store(domain)

    with pytest.raises(TypeError, match="AuthorityDomainV2"):
        activate_governance_issuer_grant_v2(
            store,
            cast(AuthorityDomainV2, object()),
            grant,
            "transition:x",
            1,
        )
    with pytest.raises(TypeError, match="GovernanceIssuerGrantV2"):
        activate_governance_issuer_grant_v2(
            store,
            domain,
            cast(GovernanceIssuerGrantV2, object()),
            "transition:x",
            1,
        )
    with pytest.raises(ValueError, match="crosses"):
        activate_governance_issuer_grant_v2(
            store,
            domain,
            _grant(other),
            "transition:x",
            1,
        )
    for transition_id in ("genesis", " transition:x"):
        with pytest.raises((TypeError, ValueError)):
            activate_governance_issuer_grant_v2(
                store,
                domain,
                grant,
                transition_id,
                1,
            )
    with pytest.raises(TypeError, match="observed_epoch"):
        activate_governance_issuer_grant_v2(
            store,
            domain,
            grant,
            "transition:x",
            cast(int, True),
        )

    with pytest.raises(TypeError, match="StateStore"):
        bind_governance_issuer_capability_v2(
            cast(GovernanceStateStoreV2, object()),
            domain,
            grant,
            "run:x",
            1,
        )
    with pytest.raises(TypeError, match="StateStore"):
        bind_governance_issuer_capability_v2(
            cast(GovernanceStateStoreV2, _ExplodingProtocolShape()),
            domain,
            grant,
            "run:x",
            1,
        )
    with pytest.raises(TypeError, match="GovernanceIssuerGrantV2"):
        bind_governance_issuer_capability_v2(
            store,
            domain,
            cast(GovernanceIssuerGrantV2, object()),
            "run:x",
            1,
        )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as root_mismatch:
        bind_governance_issuer_capability_v2(
            _store(other),
            other,
            grant,
            "run:x",
            1,
        )
    assert root_mismatch.value.path == "/domain_root"
    scope_payload = grant.to_dict()
    scope_payload["scope_ref"] = other.scope_ref
    scope_payload["grant_root"] = ""
    scope_mismatch = GovernanceIssuerGrantV2.from_dict(scope_payload)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as scope_error:
        bind_governance_issuer_capability_v2(
            store,
            domain,
            scope_mismatch,
            "run:x",
            1,
        )
    assert scope_error.value.path == "/scope_ref"

    with pytest.raises(TypeError, match="exact request type"):
        commit_verified_signal_v2(cast(GovernanceVerifiedSignalRequestV2, object()))
    with pytest.raises(TypeError, match="exact request type"):
        retire_governance_domain_v2(cast(GovernanceDomainRetirementRequestV2, object()))
    with pytest.raises(TypeError, match="unsupported"):
        open_governance_authority_session_v2(
            cast(Any, object()),
            cast(Any, object()),
        )


def test_public_grant_lifecycle_distinguishes_scope_state_epoch_and_generation() -> (
    None
):
    domain = _domain("scope:authority-session:grant-lifecycle")
    grant = _grant(domain)
    store = _store(domain)

    store.version = "pheroos-governance-state-store-v999"
    wrong_store = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:wrong-store",
        1,
    )
    _assert_code(
        wrong_store,
        AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
    )
    store.version = GOVERNANCE_STATE_STORE_VERSION_V2
    _activate(store, domain, grant)

    already_active = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:activate-again",
        2,
    )
    _assert_code(already_active, AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH)

    too_early = revoke_governance_issuer_grant_v2(
        store,
        domain,
        grant.grant_ref,
        "transition:revoke-too-early",
        0,
    )
    _assert_code(too_early, AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH)
    revoked = revoke_governance_issuer_grant_v2(
        store,
        domain,
        grant.grant_ref,
        "transition:revoke",
        2,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED
    revoked_again = revoke_governance_issuer_grant_v2(
        store,
        domain,
        grant.grant_ref,
        "transition:revoke-again",
        3,
    )
    _assert_code(revoked_again, AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED)
    reactivation = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:reactivate",
        3,
    )
    _assert_code(reactivation, AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED)

    missing_domain = _domain("scope:authority-session:missing-domain")
    missing_store = _store(domain)
    missing = revoke_governance_issuer_grant_v2(
        missing_store,
        missing_domain,
        grant.grant_ref,
        "transition:missing",
        1,
    )
    _assert_code(missing, AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH)

    malformed_domain = _domain("scope:authority-session:malformed-state")
    malformed_grant = _grant(malformed_domain)
    malformed_store = _store(malformed_domain)
    _activate(malformed_store, malformed_domain, malformed_grant)
    grant_stream = governance_issuer_grant_stream_ref_v2(
        malformed_domain.scope_ref,
        malformed_grant.grant_ref,
    )
    malformed_store.state_hook = (
        lambda _scope, stream, value: [] if stream == grant_stream else value
    )
    malformed = revoke_governance_issuer_grant_v2(
        malformed_store,
        malformed_domain,
        malformed_grant.grant_ref,
        "transition:malformed",
        2,
    )
    _assert_code(malformed, AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED)

    max_domain = _domain("scope:authority-session:max-generation")
    max_grant = _grant(
        max_domain,
        revocation_generation=MAX_AUTHORITY_REVISION_V2,
    )
    max_store = _store(max_domain)
    _activate(max_store, max_domain, max_grant)
    saturated = revoke_governance_issuer_grant_v2(
        max_store,
        max_domain,
        max_grant.grant_ref,
        "transition:saturated",
        2,
    )
    _assert_code(saturated, AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH)


def test_public_grant_operations_totalize_missing_scope_and_store_version_drift() -> (
    None
):
    domain = _domain("scope:authority-session:missing-activation")
    grant = _grant(domain)
    registered = _domain("scope:authority-session:registered-activation")
    missing_store = _store(registered)
    missing = activate_governance_issuer_grant_v2(
        missing_store,
        domain,
        grant,
        "transition:missing-activation",
        1,
    )
    _assert_code(missing, AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH)

    store = _store(domain)
    _activate(store, domain, grant)
    store.version = "pheroos-governance-state-store-v999"
    revoked = revoke_governance_issuer_grant_v2(
        store,
        domain,
        grant.grant_ref,
        "transition:wrong-version-revoke",
        2,
    )
    _assert_code(
        revoked,
        AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
    )
    store.version = GOVERNANCE_STATE_STORE_VERSION_V2
    store.raise_version = RuntimeError("version unavailable")
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as unavailable:
        bind_governance_issuer_capability_v2(
            store,
            domain,
            grant,
            "run:adversarial",
            2,
        )
    assert (
        unavailable.value.code
        is AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH
    )


def test_public_bind_and_open_fail_closed_on_hostile_reader_results() -> None:
    domain = _domain("scope:authority-session:reader-attacks")
    grant = _grant(domain)
    store = _store(domain)
    _activate(store, domain, grant)
    grant_stream = governance_issuer_grant_stream_ref_v2(
        domain.scope_ref,
        grant.grant_ref,
    )

    store.state_hook = (
        lambda _scope, stream, value: {"unexpected": True}
        if stream == grant_stream
        else value
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as malformed:
        bind_governance_issuer_capability_v2(
            store,
            domain,
            grant,
            "run:adversarial",
            2,
        )
    assert malformed.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED
    store.state_hook = None

    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        "run:adversarial",
        2,
    )
    other_domain = _domain("scope:authority-session:reader-other")
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as wrong_root:
        open_governance_authority_session_v2(capability, _signal(other_domain))
    assert wrong_root.value.path == "/domain_root"

    request_payload = _signal(domain).to_dict()
    request_payload["scope_ref"] = other_domain.scope_ref
    request_payload["stream_ref"] = ""
    request_payload["request_root"] = ""
    wrong_scope_request = GovernanceVerifiedSignalRequestV2.from_dict(request_payload)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as wrong_scope:
        open_governance_authority_session_v2(capability, wrong_scope_request)
    assert wrong_scope.value.path == "/scope_ref"

    retirement_only_domain = _domain("scope:authority-session:retirement-only")
    retirement_only_grant = _grant(
        retirement_only_domain,
        operations=(GovernanceIssuerOperationV2.RETIRE_DOMAIN,),
    )
    retirement_only_store = _store(retirement_only_domain)
    _activate(retirement_only_store, retirement_only_domain, retirement_only_grant)
    retirement_only_capability = bind_governance_issuer_capability_v2(
        retirement_only_store,
        retirement_only_domain,
        retirement_only_grant,
        "run:adversarial",
        2,
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as denied:
        open_governance_authority_session_v2(
            retirement_only_capability,
            _signal(retirement_only_domain),
        )
    assert denied.value.path == "/operation"

    store.state_hook = (
        lambda _scope, stream, value: (_ for _ in ()).throw(KeyError(stream))
        if stream == grant_stream
        else value
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as missing:
        open_governance_authority_session_v2(capability, _signal(domain))
    assert missing.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH
    store.state_hook = (
        lambda _scope, stream, value: {"unexpected": True}
        if stream == grant_stream
        else value
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as invalid:
        open_governance_authority_session_v2(capability, _signal(domain))
    assert invalid.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED


@pytest.mark.parametrize(
    "mutation",
    (
        "binding",
        "payload",
        "activation_epoch",
        "active_status",
        "revocation_epoch",
        "revocation_generation",
        "local_verification",
    ),
)
def test_public_bind_rejects_each_malformed_durable_grant_state(
    mutation: str,
) -> None:
    domain = _domain(f"scope:authority-session:state-{mutation}")
    grant = _grant(domain)
    store = _store(domain)
    _activate(store, domain, grant)
    grant_stream = governance_issuer_grant_stream_ref_v2(
        domain.scope_ref,
        grant.grant_ref,
    )

    def corrupt(
        _scope: str,
        stream: str,
        value: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if stream != grant_stream:
            return value
        changed = dict(value)
        if mutation == "binding":
            changed["schema"] = "pheroos-unknown-grant-state-v999"
        elif mutation == "payload":
            changed["grant_root"] = _root("9")
        elif mutation == "activation_epoch":
            changed["activated_epoch"] = 0
        elif mutation == "active_status":
            changed["revoked_epoch"] = 1
        elif mutation == "revocation_epoch":
            changed["status"] = "revoked"
            changed["revoked_epoch"] = 0
            changed["revocation_generation"] = 1
        elif mutation == "revocation_generation":
            changed["status"] = "revoked"
            changed["revoked_epoch"] = 1
        else:
            changed["verification"] = {
                "schema": "pheroos-issuer-grant-verification-v2",
                "grant_root": grant.grant_root,
                "grant_binding_ref": grant.grant_binding_ref,
                "verifier_ref": "verifier:invalid-local",
                "accepted": True,
                "verified_epoch": 1,
                "verification_root": _root("8"),
            }
        return changed

    store.state_hook = corrupt
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as rejected:
        bind_governance_issuer_capability_v2(
            store,
            domain,
            grant,
            "run:adversarial",
            2,
        )
    assert rejected.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED


def test_public_bind_and_open_distinguish_missing_genesis_and_sealed_state() -> None:
    domain = _domain("scope:authority-session:bind-open-state")
    grant = _grant(domain)
    missing_store = _store(_domain("scope:authority-session:registered-elsewhere"))
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as missing:
        bind_governance_issuer_capability_v2(
            missing_store,
            domain,
            grant,
            "run:adversarial",
            1,
        )
    assert missing.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH

    store = _store(domain)
    _activate(store, domain, grant)
    grant_stream = governance_issuer_grant_stream_ref_v2(
        domain.scope_ref,
        grant.grant_ref,
    )
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        "run:adversarial",
        2,
    )

    store.head_hook = (
        lambda _scope, stream, _value: GovernanceHeadV2.genesis(domain, stream)
        if stream == grant_stream
        else _value
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as genesis:
        bind_governance_issuer_capability_v2(
            store,
            domain,
            grant,
            "run:adversarial",
            2,
        )
    assert genesis.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED
    store.head_hook = None

    retirement = _retirement(domain, (grant_stream,))
    session = open_governance_authority_session_v2(capability, retirement)
    sealed = retire_governance_domain_v2(retirement, authority_session=session)
    assert sealed.disposition is GovernanceCommitDispositionV2.COMMITTED
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as sealed_bind:
        bind_governance_issuer_capability_v2(
            store,
            domain,
            grant,
            "run:adversarial",
            3,
        )
    assert sealed_bind.value.code is AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as sealed_open:
        open_governance_authority_session_v2(capability, _signal(domain))
    assert sealed_open.value.code is AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED


def test_public_bind_rejects_a_different_exact_grant_for_the_same_stream() -> None:
    domain = _domain("scope:authority-session:bind-substitution")
    grant = _grant(domain)
    store = _store(domain)
    _activate(store, domain, grant)
    payload = grant.to_dict()
    payload["issuer_ref"] = "issuer:substituted-at-bind"
    payload["grant_root"] = ""
    substituted = GovernanceIssuerGrantV2.from_dict(payload)

    with pytest.raises(GovernanceAuthorityBindingErrorV2) as rejected:
        bind_governance_issuer_capability_v2(
            store,
            domain,
            substituted,
            "run:adversarial",
            2,
        )
    assert rejected.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH


def test_direct_bind_rejects_observation_before_durable_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain = _domain("scope:authority-session:bind-before-activation")
    grant = _grant(domain, issued_epoch=1, expires_at_epoch=100)
    store = _store(domain)
    _activate(store, domain, grant, observed_epoch=3)
    grant_stream = governance_issuer_grant_stream_ref_v2(
        domain.scope_ref,
        grant.grant_ref,
    )
    durable_head = store.load_head_v2(domain.scope_ref, grant_stream)
    durable_state = dict(store.load_state_v2(domain.scope_ref, grant_stream))
    commit_calls_after_activation = store.atomic_commit_calls
    constructor_calls: list[str] = []

    def reject_constructor(
        *_args: object,
        **_kwargs: object,
    ) -> Any:
        constructor_calls.append("reached")
        raise AssertionError(
            "a pre-activation binding reached an authority constructor"
        )

    monkeypatch.setattr(
        authority_operations,
        "_make_governance_issuer_capability_v2",
        reject_constructor,
    )
    monkeypatch.setattr(
        authority_operations,
        "_make_governance_authority_session_v2",
        reject_constructor,
    )

    capability = None
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as rejected:
        capability = bind_governance_issuer_capability_v2(
            store,
            domain,
            grant,
            "run:adversarial",
            2,
        )

    assert capability is None
    assert rejected.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    assert rejected.value.path == "/observed_epoch"
    assert str(rejected.value) == "authority_binding_mismatch:/observed_epoch"
    assert constructor_calls == []

    request = _signal(domain, observed_epoch=2)
    denied = commit_verified_signal_v2(request, authority_session=None)
    _assert_code(denied, AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED)
    assert store.atomic_commit_calls == commit_calls_after_activation
    assert store.load_head_v2(domain.scope_ref, grant_stream) == durable_head
    assert dict(store.load_state_v2(domain.scope_ref, grant_stream)) == durable_state


def test_public_currentness_detects_valid_but_substituted_grant_payload() -> None:
    domain = _domain("scope:authority-session:substituted-grant")
    grant = _grant(domain)
    store = _store(domain)
    _activate(store, domain, grant)
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        "run:adversarial",
        2,
    )
    request = _signal(domain)
    session = open_governance_authority_session_v2(capability, request)
    grant_stream = governance_issuer_grant_stream_ref_v2(
        domain.scope_ref,
        grant.grant_ref,
    )
    payload = grant.to_dict()
    payload["issuer_ref"] = "issuer:substituted"
    payload["grant_root"] = ""
    substituted = GovernanceIssuerGrantV2.from_dict(payload)

    def replace_grant(
        _scope: str,
        stream: str,
        value: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if stream != grant_stream:
            return value
        changed = dict(value)
        changed["grant"] = substituted.to_dict()
        changed["grant_root"] = substituted.grant_root
        changed["grant_binding_ref"] = substituted.grant_binding_ref
        return changed

    store.state_hook = replace_grant
    denied = commit_verified_signal_v2(request, authority_session=session)
    _assert_code(denied, AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH)


def test_public_commit_detects_mid_operation_store_version_loss() -> None:
    domain = _domain("scope:authority-session:mid-operation-store-version")
    grant = _grant(domain)
    store = _store(domain)
    _activate(store, domain, grant)
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        "run:adversarial",
        2,
    )
    request = _signal(domain)
    session = open_governance_authority_session_v2(capability, request)
    store.version_reads = 0
    store.raise_version_after = 1

    denied = commit_verified_signal_v2(request, authority_session=session)

    _assert_code(
        denied,
        AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
    )


def test_public_retirement_rechecks_grant_after_session_open() -> None:
    domain = _domain("scope:authority-session:retirement-revocation")
    grant = _grant(domain)
    store = _store(domain)
    _activate(store, domain, grant)
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        "run:adversarial",
        2,
    )
    grant_stream = governance_issuer_grant_stream_ref_v2(
        domain.scope_ref,
        grant.grant_ref,
    )
    request = _retirement(domain, (grant_stream,))
    session = open_governance_authority_session_v2(capability, request)
    revoked = revoke_governance_issuer_grant_v2(
        store,
        domain,
        grant.grant_ref,
        "transition:revoke-before-retire",
        3,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED

    denied = retire_governance_domain_v2(request, authority_session=session)
    _assert_code(denied, AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED)


def test_public_commit_detects_replaced_grant_and_malformed_heads() -> None:
    domain = _domain("scope:authority-session:commit-attacks")
    grant = _grant(domain)
    store = _store(domain)
    _activate(store, domain, grant)
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        "run:adversarial",
        2,
    )
    request = _signal(domain)
    session = open_governance_authority_session_v2(capability, request)
    grant_stream = governance_issuer_grant_stream_ref_v2(
        domain.scope_ref,
        grant.grant_ref,
    )

    store.state_hook = (
        lambda _scope, stream, value: (_ for _ in ()).throw(KeyError(stream))
        if stream == grant_stream
        else value
    )
    missing = commit_verified_signal_v2(request, authority_session=session)
    _assert_code(missing, AuthorityDiagnosticCodeV2.AUTHORITY_SCOPE_MISMATCH)

    store.state_hook = (
        lambda _scope, stream, value: [] if stream == grant_stream else value
    )
    malformed = commit_verified_signal_v2(request, authority_session=session)
    _assert_code(malformed, AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED)

    store.state_hook = None
    store.head_hook = (
        lambda _scope, stream, _value: cast(Any, object())
        if stream == request.stream_ref
        else _value
    )
    with pytest.raises(TypeError, match="GovernanceHeadV2"):
        commit_verified_signal_v2(request, authority_session=session)

    store.head_hook = (
        lambda _scope, stream, _value: GovernanceHeadV2.genesis(domain, grant_stream)
        if stream == request.stream_ref
        else _value
    )
    with pytest.raises(ValueError, match="duplicate streams"):
        commit_verified_signal_v2(request, authority_session=session)


def test_public_reconciliation_rejects_noncanonical_conflicting_and_unavailable_views() -> (
    None
):
    domain = _domain("scope:authority-session:reconciliation")
    grant = _grant(domain)
    store = _store(domain)

    store.view_hook = lambda *_args: object()
    invalid_view = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:invalid-view",
        1,
    )
    _assert_code(
        invalid_view,
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID,
    )
    assert invalid_view.failure is not None
    assert invalid_view.failure.stage is GovernanceFailureStageV2.RECONCILIATION

    store.view_hook = None
    committed = _activate(
        store,
        domain,
        grant,
        transition_id="transition:conflict",
    )
    changed_payload = grant.to_dict()
    changed_payload["issuer_ref"] = "issuer:changed"
    changed_payload["grant_root"] = ""
    changed = GovernanceIssuerGrantV2.from_dict(changed_payload)
    conflict = activate_governance_issuer_grant_v2(
        store,
        domain,
        changed,
        "transition:conflict",
        1,
    )
    _assert_code(conflict, AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT)

    assert committed.committed_transition is not None
    failure = GovernanceFailureV2(
        code=AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE,
        path="/transition_id",
        stage=GovernanceFailureStageV2.LOAD,
    )

    def unavailable(
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        _value: GovernanceCommitViewV2,
    ) -> GovernanceCommitViewV2:
        return GovernanceCommitViewV2(
            domain_root=domain.domain_root,
            scope_ref=scope_ref,
            stream_ref=stream_ref,
            transition_id=transition_id,
            expected_receipt_root=None,
            disposition=GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE,
            failure=failure,
            committed_transition=None,
            position_observation=None,
            observed_revision=None,
            observed_head_root=None,
        )

    store.view_hook = unavailable
    unavailable_result = revoke_governance_issuer_grant_v2(
        store,
        domain,
        grant.grant_ref,
        "transition:unavailable",
        2,
    )
    assert (
        unavailable_result.disposition
        is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    )
    assert unavailable_result.failure == failure


def test_public_reconciliation_rejects_cross_kind_committed_views() -> None:
    source_domain = _domain("scope:authority-session:reconcile-source")
    source_grant = _grant(source_domain)
    source_store = _store(source_domain)
    _activate(source_store, source_domain, source_grant)
    source_capability = bind_governance_issuer_capability_v2(
        source_store,
        source_domain,
        source_grant,
        "run:adversarial",
        2,
    )
    source_signal = _signal(
        source_domain,
        transition_id="transition:source-signal",
    )
    source_session = open_governance_authority_session_v2(
        source_capability,
        source_signal,
    )
    assert (
        commit_verified_signal_v2(
            source_signal,
            authority_session=source_session,
        ).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    signal_view = source_store.load_commit_view_v2(
        source_domain.scope_ref,
        source_signal.stream_ref,
        source_signal.transition_id,
    )
    source_grant_stream = governance_issuer_grant_stream_ref_v2(
        source_domain.scope_ref,
        source_grant.grant_ref,
    )
    source_retirement = _retirement(
        source_domain,
        (source_grant_stream, source_signal.stream_ref),
        transition_id="transition:source-retirement",
    )
    retirement_session = open_governance_authority_session_v2(
        source_capability,
        source_retirement,
    )
    assert (
        retire_governance_domain_v2(
            source_retirement,
            authority_session=retirement_session,
        ).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    seal_view = source_store.load_commit_view_v2(
        source_domain.scope_ref,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        source_retirement.transition_id,
    )

    for label, hostile_view in (
        ("seal-state", seal_view),
        ("signal-state", signal_view),
    ):
        domain = _domain(f"scope:authority-session:{label}")
        grant = _grant(domain)
        store = _store(domain)
        store.view_hook = lambda *_args, selected=hostile_view: selected
        conflict = activate_governance_issuer_grant_v2(
            store,
            domain,
            grant,
            f"transition:{label}",
            1,
        )
        _assert_code(
            conflict,
            AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT,
        )

    retirement_domain = _domain("scope:authority-session:retirement-kind")
    retirement_grant = _grant(retirement_domain)
    retirement_store = _store(retirement_domain)
    _activate(retirement_store, retirement_domain, retirement_grant)
    retirement_capability = bind_governance_issuer_capability_v2(
        retirement_store,
        retirement_domain,
        retirement_grant,
        "run:adversarial",
        2,
    )
    grant_stream = governance_issuer_grant_stream_ref_v2(
        retirement_domain.scope_ref,
        retirement_grant.grant_ref,
    )
    request = _retirement(retirement_domain, (grant_stream,))
    session = open_governance_authority_session_v2(
        retirement_capability,
        request,
    )
    retirement_store.view_hook = lambda *_args: signal_view
    conflict = retire_governance_domain_v2(request, authority_session=session)
    _assert_code(
        conflict,
        AuthorityDiagnosticCodeV2.GOVERNANCE_TRANSITION_CONFLICT,
    )


def test_authenticated_verifier_wrong_result_is_rejected_before_store_reads() -> None:
    domain = _domain(
        "scope:authority-session:wrong-verifier-result",
        profile=AUTHORITY_AUTHENTICATED_PROFILE_V2,
    )
    grant = _grant(domain)
    store = _store(domain)
    attempt = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:wrong-verifier-result",
        2,
        _WrongResultVerifier(),
    )
    _assert_code(attempt, AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED)


def test_tampered_exact_domain_with_unknown_profile_fails_closed() -> None:
    domain = _domain("scope:authority-session:unknown-profile")
    grant = _grant(domain)
    store = _store(domain)
    object.__setattr__(domain, "profile", "authority-profile-v999")

    attempt = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:unknown-profile",
        1,
    )

    _assert_code(attempt, AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED)


def test_authenticated_bind_rejects_durable_verification_substitution() -> None:
    domain = _domain(
        "scope:authority-session:verification-substitution",
        profile=AUTHORITY_AUTHENTICATED_PROFILE_V2,
    )
    grant = _grant(domain)
    store = _store(domain)
    activated = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:verification-substitution",
        2,
        _AcceptingVerifier(),
    )
    assert activated.disposition is GovernanceCommitDispositionV2.COMMITTED
    grant_stream = governance_issuer_grant_stream_ref_v2(
        domain.scope_ref,
        grant.grant_ref,
    )

    def substitute_verification(
        _scope: str,
        stream: str,
        value: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if stream != grant_stream:
            return value
        changed = dict(value)
        changed["verification"] = IssuerGrantVerificationV2(
            grant_root=grant.grant_root,
            grant_binding_ref=grant.grant_binding_ref,
            verifier_ref="verifier:substituted",
            accepted=False,
            verified_epoch=2,
        ).to_dict()
        return changed

    store.state_hook = substitute_verification
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as rejected:
        bind_governance_issuer_capability_v2(
            store,
            domain,
            grant,
            "run:adversarial",
            3,
            _AcceptingVerifier(),
        )
    assert rejected.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED
