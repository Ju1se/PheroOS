from __future__ import annotations

from copy import copy, deepcopy
from typing import Any

import pytest

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceAuthoritySessionV2,
    GovernanceDomainRetirementRequestV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    GovernanceVerifiedSignalRequestV2,
    IssuerGrantVerificationV2,
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance._authority_session_v2.operations import (
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    commit_verified_signal_v2,
    open_governance_authority_session_v2,
    retire_governance_domain_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance._authority_v2 import InMemoryGovernanceStateStoreV2
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    AuthorityDiagnosticCodeV2,
)


def _root(digit: str) -> str:
    return f"sha256:{digit * 64}"


def _domain(
    *,
    profile: str = AUTHORITY_LOCAL_PROFILE_V2,
    scope_ref: str = "scope:authority-session",
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
    domain: AuthorityDomainV2,
    *,
    grant_ref: str = "grant:primary",
    operations: tuple[GovernanceIssuerOperationV2, ...] = (
        GovernanceIssuerOperationV2.VERIFY_SIGNAL,
        GovernanceIssuerOperationV2.RETIRE_DOMAIN,
    ),
    target_refs: tuple[str, ...] = ("target:alpha",),
    expires_at_epoch: int = 100,
) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:trusted-host",
        grant_ref=grant_ref,
        grant_binding_ref=_root("1"),
        operations=operations,
        target_refs=target_refs,
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=expires_at_epoch,
        revocation_generation=0,
    )


def _signal_request(
    domain: AuthorityDomainV2,
    *,
    run_ref: str = "run:one",
    request_ref: str = "request:signal-one",
    transition_id: str = "transition:signal-one",
    signal_ref: str = "signal:one",
    target_ref: str = "target:alpha",
    status: str = "verified",
    observed_epoch: int = 2,
) -> GovernanceVerifiedSignalRequestV2:
    return GovernanceVerifiedSignalRequestV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        run_ref=run_ref,
        request_ref=request_ref,
        transition_id=transition_id,
        signal_ref=signal_ref,
        target_ref=target_ref,
        signal_root=_root("2"),
        evidence_root=_root("3"),
        status=status,
        observed_epoch=observed_epoch,
    )


def _retirement_request(
    domain: AuthorityDomainV2,
    stream_refs: tuple[str, ...],
    *,
    run_ref: str = "run:one",
    request_ref: str = "request:retire-one",
    transition_id: str = "transition:retire-one",
    observed_epoch: int = 3,
) -> GovernanceDomainRetirementRequestV2:
    return GovernanceDomainRetirementRequestV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        run_ref=run_ref,
        request_ref=request_ref,
        transition_id=transition_id,
        stream_refs=tuple(sorted(stream_refs, key=lambda item: item.encode("utf-8"))),
        reason_ref="reason:completed",
        observed_epoch=observed_epoch,
    )


def _assert_failure(
    attempt: Any,
    disposition: GovernanceCommitDispositionV2,
    code: AuthorityDiagnosticCodeV2,
) -> None:
    assert attempt.disposition is disposition
    assert attempt.failure is not None
    assert attempt.failure.code is code
    assert attempt.committed_transition is None
    assert attempt.position_observation is None


class _Verifier:
    def __init__(
        self,
        *,
        accepted: bool = True,
        grant_root: str | None = None,
        binding_root: str | None = None,
        verifier_ref: str = "verifier:host-selected",
    ) -> None:
        self.accepted = accepted
        self.grant_root = grant_root
        self.binding_root = binding_root
        self.verifier_ref = verifier_ref
        self.calls: list[tuple[str, int]] = []

    def verify_issuer_grant_v2(
        self,
        grant: GovernanceIssuerGrantV2,
        *,
        observed_epoch: int,
    ) -> IssuerGrantVerificationV2:
        self.calls.append((grant.grant_root, observed_epoch))
        return IssuerGrantVerificationV2(
            grant_root=self.grant_root or grant.grant_root,
            grant_binding_ref=self.binding_root or grant.grant_binding_ref,
            verifier_ref=self.verifier_ref,
            accepted=self.accepted,
            verified_epoch=observed_epoch,
        )


class _CountingStore(InMemoryGovernanceStateStoreV2):
    def __init__(self, domain: AuthorityDomainV2) -> None:
        self.calls: list[str] = []
        super().__init__((domain,))

    def load_head_v2(self, scope_ref: str, stream_ref: str):  # type: ignore[no-untyped-def]
        self.calls.append("load_head")
        return super().load_head_v2(scope_ref, stream_ref)

    def load_state_v2(self, scope_ref: str, stream_ref: str):  # type: ignore[no-untyped-def]
        self.calls.append("load_state")
        return super().load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(  # type: ignore[no-untyped-def]
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ):
        self.calls.append("load_view")
        return super().load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    def atomic_commit_v2(self, batch):  # type: ignore[no-untyped-def]
        self.calls.append("atomic_commit")
        return super().atomic_commit_v2(batch)


def test_local_vertical_slice_commits_exact_read_sets_trace_and_seal() -> None:
    domain = _domain()
    grant = _grant(domain)
    store = InMemoryGovernanceStateStoreV2((domain,))
    grant_stream = governance_issuer_grant_stream_ref_v2(
        domain.scope_ref,
        grant.grant_ref,
    )

    activation = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:activate",
        1,
    )
    assert activation.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert activation.committed_transition is not None
    activation_batch = activation.committed_transition.batch
    assert {item.stream_ref for item in activation_batch.read_set.entries} == {
        grant_stream,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    activation_event = activation_batch.trace_batch.events[0]
    assert activation_event.event_type == "issuer_grant_activated"
    assert activation_event.lineage["grant_root"] == grant.grant_root
    activation_retry = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:activate",
        1,
    )
    assert activation_retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert activation_retry.committed_transition is not None
    assert (
        activation_retry.committed_transition.receipt.receipt_root
        == activation.committed_transition.receipt.receipt_root
    )

    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        "run:one",
        2,
    )
    assert copy(capability) is capability
    assert deepcopy(capability) is capability
    request = _signal_request(domain)
    session = open_governance_authority_session_v2(capability, request)
    assert copy(session) is session
    assert deepcopy(session) is session

    signal = commit_verified_signal_v2(request, authority_session=session)
    assert signal.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert signal.committed_transition is not None
    signal_batch = signal.committed_transition.batch
    signal_entries = {item.stream_ref: item for item in signal_batch.read_set.entries}
    assert set(signal_entries) == {
        request.stream_ref,
        grant_stream,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    assert signal_entries[grant_stream].expected_revision == (
        session.grant_expected_revision
    )
    assert signal_entries[grant_stream].expected_root == session.grant_expected_root
    assert (
        signal_entries[GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2].expected_root
        == session.lifecycle_expected_root
    )
    signal_event = signal_batch.trace_batch.events[0]
    assert signal_event.event_type == "signal_verified"
    assert signal_event.lineage["request_ref"] == request.request_ref
    assert signal_event.lineage["target_ref"] == request.target_ref
    assert signal_event.lineage["session_binding"]["request_ref"] == (
        request.request_ref
    )
    signal_retry = commit_verified_signal_v2(request, authority_session=session)
    assert signal_retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert signal_retry.committed_transition is not None
    assert (
        signal_retry.committed_transition.receipt.receipt_root
        == signal.committed_transition.receipt.receipt_root
    )

    retirement_request = _retirement_request(
        domain,
        (grant_stream, request.stream_ref),
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
    assert retirement.position_observation is not None
    assert retirement.position_observation.position is GovernanceCommitPositionV2.SEALED
    assert retirement.committed_transition is not None
    retirement_batch = retirement.committed_transition.batch
    assert retirement_batch.seal is not None
    assert tuple(item["stream_ref"] for item in retirement_batch.seal.final_heads) == (
        retirement_request.stream_refs
    )
    assert {item.stream_ref for item in retirement_batch.read_set.entries} == {
        *retirement_request.stream_refs,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    retirement_event = retirement_batch.trace_batch.events[0]
    assert retirement_event.event_type == "domain_retired"
    assert retirement_event.lineage["request_ref"] == retirement_request.request_ref
    assert retirement_event.lineage["session_binding"]["request_ref"] == (
        retirement_request.request_ref
    )
    retirement_retry = retire_governance_domain_v2(
        retirement_request,
        authority_session=retirement_session,
    )
    assert retirement_retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert retirement_retry.committed_transition is not None
    assert (
        retirement_retry.committed_transition.receipt.receipt_root
        == retirement.committed_transition.receipt.receipt_root
    )

    historical = store.load_commit_view_v2(
        domain.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    assert historical.disposition is GovernanceCommitDispositionV2.COMMITTED
    later_grant = _grant(domain, grant_ref="grant:after-seal")
    denied = activate_governance_issuer_grant_v2(
        store,
        domain,
        later_grant,
        "transition:after-seal",
        4,
    )
    _assert_failure(
        denied,
        GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
    )


def test_fake_or_mismatched_sessions_fail_before_any_store_write() -> None:
    domain = _domain(scope_ref="scope:fake-session")
    grant = _grant(domain)
    store = InMemoryGovernanceStateStoreV2((domain,))
    activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:activate",
        1,
    )
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        "run:one",
        2,
    )
    request = _signal_request(domain)
    before = store.snapshot_v2()
    uninitialized = object.__new__(GovernanceAuthoritySessionV2)

    for candidate in (None, object(), uninitialized):
        attempt = commit_verified_signal_v2(
            request,
            authority_session=candidate,
        )
        _assert_failure(
            attempt,
            GovernanceCommitDispositionV2.DENIED,
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED,
        )
        assert attempt.transition_id == request.transition_id
        assert store.snapshot_v2() == before

    genuine = open_governance_authority_session_v2(capability, request)
    mismatched_request = _signal_request(
        domain,
        request_ref="request:signal-two",
        transition_id="transition:signal-two",
    )
    mismatch = commit_verified_signal_v2(
        mismatched_request,
        authority_session=genuine,
    )
    _assert_failure(
        mismatch,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
    )
    assert store.snapshot_v2() == before

    rejected_request = _signal_request(
        domain,
        request_ref="request:rejected",
        transition_id="transition:rejected",
        status="rejected",
    )
    rejected_session = open_governance_authority_session_v2(
        capability,
        rejected_request,
    )
    rejected = commit_verified_signal_v2(
        rejected_request,
        authority_session=rejected_session,
    )
    _assert_failure(
        rejected,
        GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_ACTION_NOT_AUTHORIZED,
    )
    assert store.snapshot_v2() == before


def test_revocation_expiry_and_request_bounds_fail_closed() -> None:
    domain = _domain(scope_ref="scope:revocation")
    grant = _grant(domain)
    store = InMemoryGovernanceStateStoreV2((domain,))
    activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:activate",
        1,
    )
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        "run:one",
        2,
    )
    request = _signal_request(domain)
    stale_session = open_governance_authority_session_v2(capability, request)

    revoked = revoke_governance_issuer_grant_v2(
        store,
        domain,
        grant.grant_ref,
        "transition:revoke",
        3,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert revoked.committed_transition is not None
    revoked_retry = revoke_governance_issuer_grant_v2(
        store,
        domain,
        grant.grant_ref,
        "transition:revoke",
        3,
    )
    assert revoked_retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert revoked_retry.committed_transition is not None
    assert (
        revoked_retry.committed_transition.receipt.receipt_root
        == revoked.committed_transition.receipt.receipt_root
    )
    denied = commit_verified_signal_v2(request, authority_session=stale_session)
    _assert_failure(
        denied,
        GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED,
    )
    assert store.load_head_v2(domain.scope_ref, request.stream_ref).revision == 0
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as revoked_error:
        bind_governance_issuer_capability_v2(
            store,
            domain,
            grant,
            "run:one",
            4,
        )
    assert revoked_error.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED

    short_domain = _domain(scope_ref="scope:expired")
    short_grant = _grant(short_domain, expires_at_epoch=2)
    short_store = InMemoryGovernanceStateStoreV2((short_domain,))
    activate_governance_issuer_grant_v2(
        short_store,
        short_domain,
        short_grant,
        "transition:activate-short",
        1,
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as expired_error:
        bind_governance_issuer_capability_v2(
            short_store,
            short_domain,
            short_grant,
            "run:one",
            3,
        )
    assert expired_error.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED

    bounded_store = InMemoryGovernanceStateStoreV2((short_domain,))
    activate_governance_issuer_grant_v2(
        bounded_store,
        short_domain,
        short_grant,
        "transition:activate-bounded",
        1,
    )
    bounded_capability = bind_governance_issuer_capability_v2(
        bounded_store,
        short_domain,
        short_grant,
        "run:one",
        1,
    )
    wrong_run = _signal_request(short_domain, run_ref="run:other", observed_epoch=2)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as run_error:
        open_governance_authority_session_v2(bounded_capability, wrong_run)
    assert run_error.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
    wrong_target = _signal_request(
        short_domain,
        request_ref="request:wrong-target",
        transition_id="transition:wrong-target",
        target_ref="target:outside-grant",
        observed_epoch=2,
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as target_error:
        open_governance_authority_session_v2(bounded_capability, wrong_target)
    assert (
        target_error.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED
    )


def test_authenticated_profile_reverifies_at_bind_epoch_without_fallback() -> None:
    domain = _domain(
        profile=AUTHORITY_AUTHENTICATED_PROFILE_V2,
        scope_ref="scope:authenticated",
    )
    grant = _grant(domain)
    store = _CountingStore(domain)
    before = store.snapshot_v2()
    store.calls.clear()

    missing = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:missing-verifier",
        2,
    )
    _assert_failure(
        missing,
        GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
    )
    assert store.calls == ["load_view"]
    assert store.snapshot_v2() == before

    rejected_verifier = _Verifier(accepted=False)
    rejected = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:rejected-verifier",
        2,
        rejected_verifier,
    )
    _assert_failure(
        rejected,
        GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
    )
    assert store.calls == ["load_view", "load_view"]
    assert store.snapshot_v2() == before

    activation_verifier = _Verifier()
    activated = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:activate-authenticated",
        2,
        activation_verifier,
    )
    assert activated.disposition is GovernanceCommitDispositionV2.COMMITTED
    durable = store.load_state_v2(
        domain.scope_ref,
        governance_issuer_grant_stream_ref_v2(domain.scope_ref, grant.grant_ref),
    )
    activation_verification = durable["verification"]
    assert activation_verification["verified_epoch"] == 2
    activation_retry = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:activate-authenticated",
        2,
    )
    assert activation_retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert activation_retry.committed_transition is not None
    assert activated.committed_transition is not None
    assert (
        activation_retry.committed_transition.receipt.receipt_root
        == activated.committed_transition.receipt.receipt_root
    )

    store.calls.clear()
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as missing_bind:
        bind_governance_issuer_capability_v2(
            store,
            domain,
            grant,
            "run:one",
            5,
        )
    assert (
        missing_bind.value.code is AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED
    )
    assert store.calls == []

    store.calls.clear()
    mismatched_verifier = _Verifier(grant_root=_root("4"))
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as mismatched_bind:
        bind_governance_issuer_capability_v2(
            store,
            domain,
            grant,
            "run:one",
            5,
            mismatched_verifier,
        )
    assert mismatched_bind.value.code is (
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED
    )
    assert store.calls == []

    bind_verifier = _Verifier()
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        "run:one",
        5,
        bind_verifier,
    )
    assert capability.observed_epoch == 5
    assert capability.verification_root != activation_verification["verification_root"]
    assert bind_verifier.calls == [(grant.grant_root, 5)]
    request = _signal_request(domain, observed_epoch=5)
    session = open_governance_authority_session_v2(capability, request)
    committed = commit_verified_signal_v2(request, authority_session=session)
    assert committed.disposition is GovernanceCommitDispositionV2.COMMITTED

    local_domain = _domain(scope_ref="scope:local-no-verifier")
    local_grant = _grant(local_domain)
    local_store = _CountingStore(local_domain)
    local_before = local_store.snapshot_v2()
    local_store.calls.clear()
    local_denial = activate_governance_issuer_grant_v2(
        local_store,
        local_domain,
        local_grant,
        "transition:local-with-verifier",
        1,
        _Verifier(),
    )
    _assert_failure(
        local_denial,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED,
    )
    assert local_store.calls == ["load_view"]
    assert local_store.snapshot_v2() == local_before
    local_store.calls.clear()
    assert (
        activate_governance_issuer_grant_v2(
            local_store,
            local_domain,
            local_grant,
            "transition:activate-local",
            1,
        ).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    local_store.calls.clear()
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as local_bind:
        bind_governance_issuer_capability_v2(
            local_store,
            local_domain,
            local_grant,
            "run:one",
            2,
            _Verifier(),
        )
    assert local_bind.value.code is (
        AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED
    )
    assert local_store.calls == []


def test_retirement_uses_store_closure_and_old_sessions_lose_seal_race() -> None:
    domain = _domain(scope_ref="scope:closure")
    grant = _grant(domain)
    store = InMemoryGovernanceStateStoreV2((domain,))
    activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:activate",
        1,
    )
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        "run:one",
        2,
    )
    grant_stream = governance_issuer_grant_stream_ref_v2(
        domain.scope_ref,
        grant.grant_ref,
    )
    signal_request = _signal_request(domain)
    signal_session = open_governance_authority_session_v2(
        capability,
        signal_request,
    )
    assert (
        commit_verified_signal_v2(
            signal_request,
            authority_session=signal_session,
        ).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )

    incomplete_request = _retirement_request(domain, (grant_stream,))
    incomplete_session = open_governance_authority_session_v2(
        capability,
        incomplete_request,
    )
    incomplete = retire_governance_domain_v2(
        incomplete_request,
        authority_session=incomplete_session,
    )
    _assert_failure(
        incomplete,
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
    )
    assert (
        store.load_head_v2(
            domain.scope_ref,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        ).revision
        == 0
    )

    missing_grant_request = _retirement_request(
        domain,
        (signal_request.stream_ref,),
        request_ref="request:missing-grant",
        transition_id="transition:missing-grant",
    )
    missing_grant_session = open_governance_authority_session_v2(
        capability,
        missing_grant_request,
    )
    missing_grant = retire_governance_domain_v2(
        missing_grant_request,
        authority_session=missing_grant_session,
    )
    _assert_failure(
        missing_grant,
        GovernanceCommitDispositionV2.INVALID,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_INVALID,
    )

    complete_request = _retirement_request(
        domain,
        (grant_stream, signal_request.stream_ref),
        request_ref="request:complete-retirement",
        transition_id="transition:complete-retirement",
    )
    complete_session = open_governance_authority_session_v2(
        capability,
        complete_request,
    )
    complete = retire_governance_domain_v2(
        complete_request,
        authority_session=complete_session,
    )
    assert complete.disposition is GovernanceCommitDispositionV2.COMMITTED

    race_domain = _domain(scope_ref="scope:seal-race")
    race_grant = _grant(race_domain)
    race_store = InMemoryGovernanceStateStoreV2((race_domain,))
    activate_governance_issuer_grant_v2(
        race_store,
        race_domain,
        race_grant,
        "transition:activate-race",
        1,
    )
    race_capability = bind_governance_issuer_capability_v2(
        race_store,
        race_domain,
        race_grant,
        "run:one",
        2,
    )
    late_signal_request = _signal_request(race_domain)
    late_signal_session = open_governance_authority_session_v2(
        race_capability,
        late_signal_request,
    )
    race_grant_stream = governance_issuer_grant_stream_ref_v2(
        race_domain.scope_ref,
        race_grant.grant_ref,
    )
    seal_request = _retirement_request(race_domain, (race_grant_stream,))
    seal_session = open_governance_authority_session_v2(
        race_capability,
        seal_request,
    )
    assert (
        retire_governance_domain_v2(
            seal_request,
            authority_session=seal_session,
        ).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    lost_race = commit_verified_signal_v2(
        late_signal_request,
        authority_session=late_signal_session,
    )
    _assert_failure(
        lost_race,
        GovernanceCommitDispositionV2.DENIED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
    )
