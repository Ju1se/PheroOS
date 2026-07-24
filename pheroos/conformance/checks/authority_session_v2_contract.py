"""Reusable Draft conformance matrix for scoped-authority v2 sessions.

The matrix composes only public Protocol, Governance StateStore, scoped-
authority session, and Trace contracts.  The selected StateStore enters solely
through ``GovernanceStateStoreConformanceAdapterV2`` so one behavior matrix is
applied to the reference and independent stdlib implementations.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import copy, deepcopy
from hashlib import sha256
import pickle
from types import MappingProxyType
from typing import Any, cast

from pheroos.conformance.checks.authority_store_v2_contract import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.report import CheckResult
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_AUTHENTICATED_PROFILE_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitBatchV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceCommitPositionObservationV2,
    GovernanceCommitViewV2,
    GovernanceCommittedTransitionV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceAuthoritySessionV2,
    GovernanceDomainRetirementRequestV2,
    GovernanceIssuerCapabilityV2,
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
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2
from pheroos.trace import TraceEvent


GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2 = (
    "pheroos-governance-authority-session-conformance-v2"
)

_CHECK_NAME = "authority_session_v2_contract"
_RUN_REF = "run:authority-session-v2"
_TARGET_REF = "target:authority-session-v2"


class _VerifierV2:
    """Deterministic host-verifier fixture with explicit failure modes."""

    def __init__(self, mode: str = "accept") -> None:
        self.mode = mode
        self.calls: list[tuple[str, int]] = []

    def verify_issuer_grant_v2(
        self,
        grant: GovernanceIssuerGrantV2,
        *,
        observed_epoch: int,
    ) -> IssuerGrantVerificationV2:
        self.calls.append((grant.grant_root, observed_epoch))
        if self.mode == "raise":
            raise RuntimeError("deterministic verifier rejection")
        return IssuerGrantVerificationV2(
            grant_root=(
                _root("mismatched-grant")
                if self.mode == "mismatch"
                else grant.grant_root
            ),
            grant_binding_ref=grant.grant_binding_ref,
            verifier_ref="verifier:authority-session-v2",
            accepted=self.mode != "reject",
            verified_epoch=(
                observed_epoch + 1 if self.mode == "wrong-epoch" else observed_epoch
            ),
        )


class _ImmutableReadStoreV2:
    """Exercise the public detached-Mapping reader contract exactly."""

    def __init__(self, delegate: GovernanceStateStoreV2) -> None:
        self._delegate = delegate

    @property
    def state_store_version(self) -> str:
        return self._delegate.state_store_version

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        return self._delegate.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(
        self,
        scope_ref: str,
        stream_ref: str,
    ) -> Mapping[str, Any]:
        projected = _immutable_projection(
            self._delegate.load_state_v2(scope_ref, stream_ref)
        )
        return cast(Mapping[str, Any], projected)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        return self._delegate.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )

    def atomic_commit_v2(
        self,
        batch: GovernanceCommitBatchV2,
    ) -> GovernanceCommitAttemptV2:
        return self._delegate.atomic_commit_v2(batch)


class _VersionSwitchingStoreV2(_ImmutableReadStoreV2):
    """Expose a structural Store whose advertised exact version can drift."""

    def __init__(self, delegate: GovernanceStateStoreV2) -> None:
        super().__init__(delegate)
        self.selected_version = GOVERNANCE_STATE_STORE_VERSION_V2

    @property
    def state_store_version(self) -> str:
        return self.selected_version


def run_governance_authority_session_conformance_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> CheckResult:
    """Run the complete deterministic Draft authority-session v2 matrix."""

    try:
        if not isinstance(adapter, GovernanceStateStoreConformanceAdapterV2):
            return CheckResult(_CHECK_NAME, False, "adapter_protocol")
        implementation_id = adapter.implementation_id
        store_conformance_version = adapter.conformance_version
    except Exception as exc:
        return CheckResult(
            _CHECK_NAME,
            False,
            f"adapter_exception:{type(exc).__name__}:{exc}",
        )
    if (
        type(implementation_id) is not str
        or not implementation_id
        or implementation_id != implementation_id.strip()
    ):
        return CheckResult(_CHECK_NAME, False, "adapter_implementation_id")
    if store_conformance_version != GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2:
        return CheckResult(_CHECK_NAME, False, "adapter_version")

    problems: list[str] = []
    try:
        _evaluate_local_vertical_slice(adapter, problems)
        _evaluate_immutable_mapping_reads(adapter, problems)
        _evaluate_store_version_boundary(adapter, problems)
        _evaluate_handle_and_request_boundaries(adapter, problems)
        _evaluate_revocation_after_session(adapter, problems)
        _evaluate_lifecycle_seal_race(adapter, problems)
        _evaluate_retirement_closure_and_history(adapter, problems)
        _evaluate_authenticated_verifier_boundary(adapter, problems)
    except Exception as exc:  # total boundary for third-party adapters
        problems.append(f"adapter_exception:{type(exc).__name__}:{exc}")
    return CheckResult(_CHECK_NAME, not problems, ", ".join(problems))


def _evaluate_local_vertical_slice(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    domain, store, grant = _local_setup(adapter, "local-vertical")
    activation = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:activate",
        2,
    )
    if not _is_committed(activation):
        problems.append("local_activation")
        return
    activation_retry = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:activate",
        2,
    )
    if (
        not _same_commit(activation, activation_retry)
        or store.load_head_v2(
            domain.scope_ref,
            governance_issuer_grant_stream_ref_v2(
                domain.scope_ref,
                grant.grant_ref,
            ),
        ).revision
        != 1
    ):
        problems.append("activation_exact_retry")

    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        _RUN_REF,
        3,
    )
    if (
        type(capability) is not GovernanceIssuerCapabilityV2
        or capability.run_ref != _RUN_REF
        or capability.grant_root != grant.grant_root
        or capability.verification_root is not None
        or capability.profile != AUTHORITY_LOCAL_PROFILE_V2
    ):
        problems.append("run_bound_capability")

    request = _signal_request(
        domain,
        request_ref="request:signal:one",
        transition_id="transition:signal:one",
        observed_epoch=3,
    )
    second_request = _signal_request(
        domain,
        request_ref="request:signal:two",
        transition_id="transition:signal:two",
        observed_epoch=3,
        signal_ref="signal:two",
    )
    session = open_governance_authority_session_v2(capability, request)
    second_session = open_governance_authority_session_v2(
        capability,
        second_request,
    )
    if (
        type(session) is not GovernanceAuthoritySessionV2
        or session.run_ref != _RUN_REF
        or session.request_ref != request.request_ref
        or session.request_root != request.request_root
        or session.operation is not GovernanceIssuerOperationV2.VERIFY_SIGNAL
        or second_session.request_ref != second_request.request_ref
        or second_session.request_root == session.request_root
    ):
        problems.append("request_bound_session")

    committed = commit_verified_signal_v2(request, authority_session=session)
    if not _is_committed(committed):
        problems.append("verified_signal_commit")
        return
    committed_retry = commit_verified_signal_v2(
        request,
        authority_session=session,
    )
    if not _same_commit(committed, committed_retry):
        problems.append("verified_signal_exact_retry")
    if store.load_head_v2(domain.scope_ref, request.stream_ref).revision != 1:
        problems.append("verified_signal_double_advance")

    _evaluate_committed_signal_artifacts(
        adapter,
        domain,
        store,
        grant,
        session,
        request,
        committed,
        problems,
    )


def _evaluate_committed_signal_artifacts(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    domain: AuthorityDomainV2,
    store: GovernanceStateStoreV2,
    grant: GovernanceIssuerGrantV2,
    session: GovernanceAuthoritySessionV2,
    request: GovernanceVerifiedSignalRequestV2,
    committed: GovernanceCommitAttemptV2,
    problems: list[str],
) -> None:
    # The caller admits this path only after ``_is_committed`` proves both
    # artifacts are present.  Keep the detector at that single authority gate
    # instead of duplicating an unreachable optionality check here.
    transition = cast(
        GovernanceCommittedTransitionV2,
        committed.committed_transition,
    )
    position = cast(
        GovernanceCommitPositionObservationV2,
        committed.position_observation,
    )
    events = transition.batch.trace_batch.events
    expected_streams = {
        request.stream_ref,
        governance_issuer_grant_stream_ref_v2(
            domain.scope_ref,
            grant.grant_ref,
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    if not _session_read_set_matches(
        transition.batch,
        session,
        expected_streams,
    ):
        problems.append("verified_signal_session_read_set")
    if (
        position.position is not GovernanceCommitPositionV2.CURRENT
        or len(events) != 1
        or type(events[0]) is not TraceEvent
        or events[0].event_type != "signal_verified"
        or events[0].lineage.get("request_root") != request.request_root
        or events[0].lineage.get("grant_root") != grant.grant_root
    ):
        problems.append("verified_signal_trace_or_current_inclusion")
    else:
        try:
            events[0].validate()
        except (TypeError, ValueError):
            problems.append("verified_signal_trace_validation")

    state = store.load_state_v2(domain.scope_ref, request.stream_ref)
    if (
        state.get("request_root") != request.request_root
        or state.get("signal_root") != request.signal_root
        or state.get("evidence_root") != request.evidence_root
        or state.get("status") != "verified"
    ):
        problems.append("verified_signal_durable_state")
    restarted = adapter.restart_store_v2(store)
    if not isinstance(restarted, GovernanceStateStoreV2):
        problems.append("verified_signal_restart_store_protocol")
        return
    restarted_view = restarted.load_commit_view_v2(
        domain.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    if (
        restarted.load_state_v2(domain.scope_ref, request.stream_ref) != state
        or restarted_view.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or restarted_view.committed_transition is None
        or restarted_view.committed_transition.committed_transition_root
        != transition.committed_transition_root
    ):
        problems.append("verified_signal_restart_durability")


def _evaluate_handle_and_request_boundaries(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    domain, store, grant, capability = _active_local_setup(
        adapter,
        "handle-boundaries",
    )
    request = _signal_request(
        domain,
        request_ref="request:handle",
        transition_id="transition:handle",
        observed_epoch=3,
    )
    session = open_governance_authority_session_v2(capability, request)
    _evaluate_opaque_handle_boundaries(
        domain,
        store,
        capability,
        session,
        request,
        problems,
    )
    _evaluate_request_binding_boundaries(
        domain,
        grant,
        capability,
        session,
        problems,
    )
    _evaluate_expiry_boundaries(adapter, problems)


def _evaluate_opaque_handle_boundaries(
    domain: AuthorityDomainV2,
    store: GovernanceStateStoreV2,
    capability: GovernanceIssuerCapabilityV2,
    session: GovernanceAuthoritySessionV2,
    request: GovernanceVerifiedSignalRequestV2,
    problems: list[str],
) -> None:
    initial_head = store.load_head_v2(domain.scope_ref, request.stream_ref)
    if copy(capability) is not capability or deepcopy(capability) is not capability:
        problems.append("capability_copy_identity")
    if copy(session) is not session or deepcopy(session) is not session:
        problems.append("session_copy_identity")
    if not _pickle_rejected(capability):
        problems.append("capability_pickle")
    if not _pickle_rejected(session):
        problems.append("session_pickle")
    if hasattr(capability, "__dict__") or hasattr(capability, "to_dict"):
        problems.append("capability_portable_surface")
    if hasattr(session, "__dict__") or hasattr(session, "to_dict"):
        problems.append("session_portable_surface")

    _evaluate_forged_handle_rejection(
        domain,
        store,
        session,
        request,
        initial_head,
        problems,
    )


def _evaluate_forged_handle_rejection(
    domain: AuthorityDomainV2,
    store: GovernanceStateStoreV2,
    session: GovernanceAuthoritySessionV2,
    request: GovernanceVerifiedSignalRequestV2,
    initial_head: GovernanceHeadV2,
    problems: list[str],
) -> None:
    attempts = (
        ("missing_session", commit_verified_signal_v2(request)),
        (
            "fake_shaped_session",
            commit_verified_signal_v2(
                request,
                authority_session=_FakeSessionV2(session),
            ),
        ),
        (
            "forged_session",
            commit_verified_signal_v2(
                request,
                authority_session=object.__new__(GovernanceAuthoritySessionV2),
            ),
        ),
    )
    for label, attempt in attempts:
        if not _has_failure(
            attempt,
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED,
        ):
            problems.append(label)
    forged_capability = object.__new__(GovernanceIssuerCapabilityV2)
    if not _binding_rejected(
        lambda: open_governance_authority_session_v2(
            forged_capability,
            request,
        ),
        AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_REQUIRED,
    ):
        problems.append("forged_capability")
    if store.load_head_v2(domain.scope_ref, request.stream_ref) != initial_head:
        problems.append("invalid_handle_mutation")


def _evaluate_request_binding_boundaries(
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    capability: GovernanceIssuerCapabilityV2,
    session: GovernanceAuthoritySessionV2,
    problems: list[str],
) -> None:
    wrong_run = _signal_request(
        domain,
        request_ref="request:wrong-run",
        transition_id="transition:wrong-run",
        observed_epoch=3,
        run_ref="run:other",
    )
    if not _binding_rejected(
        lambda: open_governance_authority_session_v2(capability, wrong_run),
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
    ):
        problems.append("wrong_run")

    wrong_target = _signal_request(
        domain,
        request_ref="request:wrong-target",
        transition_id="transition:wrong-target",
        observed_epoch=3,
        target_ref="target:outside-grant",
    )
    if not _binding_rejected(
        lambda: open_governance_authority_session_v2(capability, wrong_target),
        AuthorityDiagnosticCodeV2.AUTHORITY_OPERATION_DENIED,
    ):
        problems.append("wrong_target")

    other_request = _signal_request(
        domain,
        request_ref="request:other",
        transition_id="transition:other",
        observed_epoch=3,
        signal_ref="signal:other",
    )
    wrong_request = commit_verified_signal_v2(
        other_request,
        authority_session=session,
    )
    if not _has_failure(
        wrong_request,
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
    ):
        problems.append("wrong_request")

    rejected_request = _signal_request(
        domain,
        request_ref="request:rejected",
        transition_id="transition:rejected",
        observed_epoch=3,
        signal_ref="signal:rejected",
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
    if not _has_failure(
        rejected,
        AuthorityDiagnosticCodeV2.GOVERNANCE_ACTION_NOT_AUTHORIZED,
    ):
        problems.append("wrong_status")

    retirement = _retirement_request(
        domain,
        stream_refs=(
            governance_issuer_grant_stream_ref_v2(
                domain.scope_ref,
                grant.grant_ref,
            ),
        ),
        request_ref="request:wrong-operation",
        transition_id="transition:wrong-operation",
        observed_epoch=3,
    )
    wrong_operation = retire_governance_domain_v2(
        retirement,
        authority_session=session,
    )
    if not _has_failure(
        wrong_operation,
        AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH,
    ):
        problems.append("wrong_operation")


def _evaluate_expiry_boundaries(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    expiring_domain, expiring_store, expiring_grant = _local_setup(
        adapter,
        "expiry",
        expires_at_epoch=3,
    )
    activated = activate_governance_issuer_grant_v2(
        expiring_store,
        expiring_domain,
        expiring_grant,
        "transition:expiry:activate",
        2,
    )
    if not _is_committed(activated):
        problems.append("expiry_setup")
        return
    valid_capability = bind_governance_issuer_capability_v2(
        expiring_store,
        expiring_domain,
        expiring_grant,
        _RUN_REF,
        2,
    )
    if not _binding_rejected(
        lambda: bind_governance_issuer_capability_v2(
            expiring_store,
            expiring_domain,
            expiring_grant,
            _RUN_REF,
            4,
        ),
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED,
    ):
        problems.append("expired_capability")
    expired_request = _signal_request(
        expiring_domain,
        request_ref="request:expired",
        transition_id="transition:expired",
        observed_epoch=4,
    )
    if not _binding_rejected(
        lambda: open_governance_authority_session_v2(
            valid_capability,
            expired_request,
        ),
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_EXPIRED,
    ):
        problems.append("expired_session")


def _evaluate_immutable_mapping_reads(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    domain = adapter.create_domain_v2("scope:authority-session-v2:immutable-read")
    raw_store = adapter.create_store_v2((domain,))
    store = _ImmutableReadStoreV2(raw_store)
    if not isinstance(store, GovernanceStateStoreV2):
        problems.append("immutable_read_store_protocol")
        return
    grant = _grant(domain)
    activated = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:immutable-read:activate",
        2,
    )
    if not _is_committed(activated):
        problems.append("immutable_read_activation")
        return
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        _RUN_REF,
        3,
    )
    request = _signal_request(
        domain,
        request_ref="request:immutable-read",
        transition_id="transition:immutable-read:signal",
        observed_epoch=3,
    )
    session = open_governance_authority_session_v2(capability, request)
    if not _is_committed(commit_verified_signal_v2(request, authority_session=session)):
        problems.append("immutable_read_signal")


def _evaluate_store_version_boundary(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    domain = adapter.create_domain_v2("scope:authority-session-v2:store-version")
    raw_store = adapter.create_store_v2((domain,))
    store = _VersionSwitchingStoreV2(raw_store)
    grant = _grant(domain)
    grant_stream = governance_issuer_grant_stream_ref_v2(
        domain.scope_ref,
        grant.grant_ref,
    )
    store.selected_version = "pheroos-governance-state-store-v999"
    wrong_activation = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:store-version:wrong",
        2,
    )
    if (
        not _has_failure(
            wrong_activation,
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
        )
        or raw_store.load_head_v2(domain.scope_ref, grant_stream).revision != 0
    ):
        problems.append("store_version_activation")

    store.selected_version = GOVERNANCE_STATE_STORE_VERSION_V2
    activated = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:store-version:activate",
        2,
    )
    if not _is_committed(activated):
        problems.append("store_version_setup")
        return
    store.selected_version = "pheroos-governance-state-store-v999"
    if not _binding_rejected(
        lambda: bind_governance_issuer_capability_v2(
            store,
            domain,
            grant,
            _RUN_REF,
            3,
        ),
        AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
    ):
        problems.append("store_version_bind")

    store.selected_version = GOVERNANCE_STATE_STORE_VERSION_V2
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        _RUN_REF,
        3,
    )
    request = _signal_request(
        domain,
        request_ref="request:store-version",
        transition_id="transition:store-version:signal",
        observed_epoch=3,
    )
    session = open_governance_authority_session_v2(capability, request)
    store.selected_version = "pheroos-governance-state-store-v999"
    denied = commit_verified_signal_v2(request, authority_session=session)
    if (
        not _has_failure(
            denied,
            AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
        )
        or raw_store.load_head_v2(domain.scope_ref, request.stream_ref).revision != 0
    ):
        problems.append("store_version_commit")
    other_request = _signal_request(
        domain,
        request_ref="request:store-version:other",
        transition_id="transition:store-version:other",
        observed_epoch=3,
        signal_ref="signal:store-version:other",
    )
    if not _binding_rejected(
        lambda: open_governance_authority_session_v2(capability, other_request),
        AuthorityDiagnosticCodeV2.AUTHORITY_SESSION_STORE_MISMATCH,
    ):
        problems.append("store_version_open")
    store.selected_version = GOVERNANCE_STATE_STORE_VERSION_V2
    if not _is_committed(commit_verified_signal_v2(request, authority_session=session)):
        problems.append("store_version_recovery")


def _evaluate_revocation_after_session(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    domain, store, grant, capability = _active_local_setup(
        adapter,
        "revoke-race",
    )
    request = _signal_request(
        domain,
        request_ref="request:revoke-race",
        transition_id="transition:revoke-race:signal",
        observed_epoch=3,
    )
    session = open_governance_authority_session_v2(capability, request)
    revoked = revoke_governance_issuer_grant_v2(
        store,
        domain,
        grant.grant_ref,
        "transition:revoke-race:revoke",
        4,
    )
    revoked_retry = revoke_governance_issuer_grant_v2(
        store,
        domain,
        grant.grant_ref,
        "transition:revoke-race:revoke",
        4,
    )
    denied = commit_verified_signal_v2(request, authority_session=session)
    if not _is_committed(revoked) or not _same_commit(revoked, revoked_retry):
        problems.append("revocation_exact_retry")
    if not _has_failure(
        denied,
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_REVOKED,
    ):
        problems.append("revoke_after_session")
    if store.load_head_v2(domain.scope_ref, request.stream_ref).revision != 0:
        problems.append("revoke_after_session_mutation")


def _evaluate_lifecycle_seal_race(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    domain, store, grant, capability = _active_local_setup(
        adapter,
        "seal-race",
    )
    signal = _signal_request(
        domain,
        request_ref="request:seal-race:signal",
        transition_id="transition:seal-race:signal",
        observed_epoch=3,
    )
    stale_signal_session = open_governance_authority_session_v2(
        capability,
        signal,
    )
    grant_stream = governance_issuer_grant_stream_ref_v2(
        domain.scope_ref,
        grant.grant_ref,
    )
    retirement = _retirement_request(
        domain,
        # A genesis-only stream is not a current persisted stream and therefore
        # is not part of seal closure.  The already-open signal session below
        # is the competing lifecycle writer whose commit must lose after seal.
        stream_refs=(grant_stream,),
        request_ref="request:seal-race:retire",
        transition_id="transition:seal-race:retire",
        observed_epoch=3,
    )
    retirement_session = open_governance_authority_session_v2(
        capability,
        retirement,
    )
    sealed = retire_governance_domain_v2(
        retirement,
        authority_session=retirement_session,
    )
    stale = commit_verified_signal_v2(
        signal,
        authority_session=stale_signal_session,
    )
    if not _is_committed(sealed) or not _has_failure(
        stale,
        AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED,
    ):
        problems.append("lifecycle_seal_race")
    if store.load_head_v2(domain.scope_ref, signal.stream_ref).revision != 0:
        problems.append("lifecycle_seal_race_mutation")


def _evaluate_retirement_closure_and_history(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    domain, store, grant, capability = _active_local_setup(
        adapter,
        "retirement",
    )
    signal = _signal_request(
        domain,
        request_ref="request:retirement:signal",
        transition_id="transition:retirement:signal",
        observed_epoch=3,
    )
    signal_session = open_governance_authority_session_v2(capability, signal)
    signal_result = commit_verified_signal_v2(
        signal,
        authority_session=signal_session,
    )
    if not _is_committed(signal_result):
        problems.append("retirement_signal_setup")
        return
    grant_stream = governance_issuer_grant_stream_ref_v2(
        domain.scope_ref,
        grant.grant_ref,
    )
    omitted = _retirement_request(
        domain,
        stream_refs=(grant_stream,),
        request_ref="request:retirement:omitted",
        transition_id="transition:retirement:omitted",
        observed_epoch=3,
    )
    omitted_session = open_governance_authority_session_v2(capability, omitted)
    omitted_result = retire_governance_domain_v2(
        omitted,
        authority_session=omitted_session,
    )
    if not _has_failure(
        omitted_result,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
    ):
        problems.append("retirement_omitted_stream")
    if (
        store.load_head_v2(
            domain.scope_ref,
            GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        ).revision
        != 0
    ):
        problems.append("retirement_omitted_stream_mutation")

    complete = _retirement_request(
        domain,
        stream_refs=_sorted_refs((grant_stream, signal.stream_ref)),
        request_ref="request:retirement:complete",
        transition_id="transition:retirement:complete",
        observed_epoch=3,
    )
    complete_session = open_governance_authority_session_v2(capability, complete)
    retired = retire_governance_domain_v2(
        complete,
        authority_session=complete_session,
    )
    if not _is_committed(retired):
        problems.append("retirement_complete_streams")
        return
    retry = retire_governance_domain_v2(
        complete,
        authority_session=complete_session,
    )
    if not _same_commit(retired, retry):
        problems.append("retirement_exact_retry")

    signal_view = store.load_commit_view_v2(
        domain.scope_ref,
        signal.stream_ref,
        signal.transition_id,
    )
    retirement_view = store.load_commit_view_v2(
        domain.scope_ref,
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
        complete.transition_id,
    )
    positions = (
        None
        if signal_view.position_observation is None
        else signal_view.position_observation.position,
        None
        if retirement_view.position_observation is None
        else retirement_view.position_observation.position,
    )
    if (
        signal_view.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or retirement_view.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or positions
        != (GovernanceCommitPositionV2.SEALED, GovernanceCommitPositionV2.SEALED)
    ):
        problems.append("retirement_sealed_history")
    if retirement_view.committed_transition is None:
        problems.append("retirement_seal_artifact")
    else:
        batch = retirement_view.committed_transition.batch
        event = batch.trace_batch.events[0]
        if not _session_read_set_matches(
            batch,
            complete_session,
            set(complete.stream_refs) | {GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2},
        ):
            problems.append("retirement_session_read_set")
        if (
            batch.seal is None
            or event.event_type != "domain_retired"
            or event.lineage.get("seal_root") != batch.seal.seal_root
            or event.lineage.get("final_heads_root") != batch.seal.final_heads_root
        ):
            problems.append("retirement_trace_seal_binding")


def _evaluate_authenticated_verifier_boundary(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    domain = _authenticated_domain(adapter, "authenticated")
    store = adapter.create_store_v2((domain,))
    if not isinstance(store, GovernanceStateStoreV2):
        problems.append("authenticated_store_protocol")
        return
    grant = _grant(domain)

    if not _evaluate_authenticated_activation(store, domain, grant, problems):
        return
    _evaluate_authenticated_binding(store, domain, grant, problems)
    _evaluate_local_profile_verifier_rejection(adapter, problems)


def _evaluate_authenticated_activation(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    problems: list[str],
) -> bool:
    missing = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:authenticated:missing",
        2,
    )
    if not _has_failure(
        missing,
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
    ):
        problems.append("authenticated_activation_missing_verifier")
    for mode in ("reject", "mismatch", "wrong-epoch", "raise"):
        failed = activate_governance_issuer_grant_v2(
            store,
            domain,
            grant,
            f"transition:authenticated:{mode}",
            2,
            _VerifierV2(mode),
        )
        if not _has_failure(
            failed,
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
        ):
            problems.append(f"authenticated_activation_{mode}")
    grant_stream = governance_issuer_grant_stream_ref_v2(
        domain.scope_ref,
        grant.grant_ref,
    )
    if store.load_head_v2(domain.scope_ref, grant_stream).revision != 0:
        problems.append("authenticated_failed_activation_mutation")

    activation_verifier = _VerifierV2()
    activated = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:authenticated:activate",
        2,
        activation_verifier,
    )
    if not _is_committed(activated) or activation_verifier.calls != [
        (grant.grant_root, 2)
    ]:
        problems.append("authenticated_activation")
        return False
    unavailable_retry = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:authenticated:activate",
        2,
    )
    if not _same_commit(activated, unavailable_retry) or activation_verifier.calls != [
        (grant.grant_root, 2)
    ]:
        problems.append("authenticated_activation_retry_without_verifier")
    return True


def _evaluate_authenticated_binding(
    store: GovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
    problems: list[str],
) -> None:
    if not _binding_rejected(
        lambda: bind_governance_issuer_capability_v2(
            store,
            domain,
            grant,
            _RUN_REF,
            4,
        ),
        AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
    ):
        problems.append("authenticated_bind_missing_verifier")
    for mode in ("reject", "mismatch", "wrong-epoch", "raise"):
        if not _binding_rejected(
            lambda mode=mode: bind_governance_issuer_capability_v2(
                store,
                domain,
                grant,
                _RUN_REF,
                4,
                _VerifierV2(mode),
            ),
            AuthorityDiagnosticCodeV2.AUTHORITY_GRANT_UNVERIFIED,
        ):
            problems.append(f"authenticated_bind_{mode}")
    later_verifier = _VerifierV2()
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        _RUN_REF,
        4,
        later_verifier,
    )
    if (
        capability.profile != AUTHORITY_AUTHENTICATED_PROFILE_V2
        or capability.verification_root is None
        or capability.verifier_ref != "verifier:authority-session-v2"
        or later_verifier.calls != [(grant.grant_root, 4)]
    ):
        problems.append("authenticated_later_bind")


def _evaluate_local_profile_verifier_rejection(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    local_domain, local_store, local_grant = _local_setup(
        adapter,
        "local-no-verifier-fallback",
    )
    local_verifier = _VerifierV2()
    local_attempt = activate_governance_issuer_grant_v2(
        local_store,
        local_domain,
        local_grant,
        "transition:local:verifier",
        2,
        local_verifier,
    )
    if (
        not _has_failure(
            local_attempt,
            AuthorityDiagnosticCodeV2.AUTHORITY_PROFILE_UNSUPPORTED,
        )
        or local_verifier.calls
    ):
        problems.append("local_profile_verifier_rejected_without_call")


class _FakeSessionV2:
    """A shape-compatible object that must never become authority."""

    def __init__(self, session: GovernanceAuthoritySessionV2) -> None:
        self.domain_root = session.domain_root
        self.scope_ref = session.scope_ref
        self.run_ref = session.run_ref
        self.request_ref = session.request_ref
        self.request_root = session.request_root
        self.operation = session.operation


def _local_setup(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    label: str,
    *,
    expires_at_epoch: int = 20,
) -> tuple[
    AuthorityDomainV2,
    GovernanceStateStoreV2,
    GovernanceIssuerGrantV2,
]:
    domain = adapter.create_domain_v2(f"scope:authority-session:{label}")
    if type(domain) is not AuthorityDomainV2:
        raise TypeError("adapter returned a non-canonical authority domain")
    store = adapter.create_store_v2((domain,))
    if not isinstance(store, GovernanceStateStoreV2):
        raise TypeError("adapter returned a non-conforming StateStore v2")
    return domain, store, _grant(domain, expires_at_epoch=expires_at_epoch)


def _active_local_setup(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    label: str,
) -> tuple[
    AuthorityDomainV2,
    GovernanceStateStoreV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerCapabilityV2,
]:
    domain, store, grant = _local_setup(adapter, label)
    activated = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        f"transition:{label}:activate",
        2,
    )
    if not _is_committed(activated):
        raise ValueError("local conformance fixture grant activation failed")
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        _RUN_REF,
        3,
    )
    return domain, store, grant, capability


def _authenticated_domain(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    label: str,
) -> AuthorityDomainV2:
    local = adapter.create_domain_v2(f"scope:authority-session:{label}")
    if type(local) is not AuthorityDomainV2:
        raise TypeError("adapter returned a non-canonical authority domain")
    return AuthorityDomainV2(
        policy_version=local.policy_version,
        profile=AUTHORITY_AUTHENTICATED_PROFILE_V2,
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
    expires_at_epoch: int = 20,
) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:authority-session-v2",
        grant_ref="grant:authority-session-v2",
        grant_binding_ref=_root(f"grant-binding:{domain.scope_ref}"),
        operations=(
            GovernanceIssuerOperationV2.VERIFY_SIGNAL,
            GovernanceIssuerOperationV2.RETIRE_DOMAIN,
        ),
        target_refs=(_TARGET_REF,),
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=expires_at_epoch,
        revocation_generation=0,
    )


def _signal_request(
    domain: AuthorityDomainV2,
    *,
    request_ref: str,
    transition_id: str,
    observed_epoch: int,
    signal_ref: str = "signal:authority-session-v2",
    target_ref: str = _TARGET_REF,
    run_ref: str = _RUN_REF,
    status: str = "verified",
) -> GovernanceVerifiedSignalRequestV2:
    return GovernanceVerifiedSignalRequestV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        run_ref=run_ref,
        request_ref=request_ref,
        transition_id=transition_id,
        signal_ref=signal_ref,
        target_ref=target_ref,
        signal_root=_root(f"signal:{request_ref}"),
        evidence_root=_root(f"evidence:{request_ref}"),
        status=status,
        observed_epoch=observed_epoch,
    )


def _retirement_request(
    domain: AuthorityDomainV2,
    *,
    stream_refs: tuple[str, ...],
    request_ref: str,
    transition_id: str,
    observed_epoch: int,
) -> GovernanceDomainRetirementRequestV2:
    return GovernanceDomainRetirementRequestV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        run_ref=_RUN_REF,
        request_ref=request_ref,
        transition_id=transition_id,
        stream_refs=stream_refs,
        reason_ref="reason:authority-session-v2-retirement",
        observed_epoch=observed_epoch,
    )


def _immutable_projection(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _immutable_projection(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_immutable_projection(item) for item in value)
    return value


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _sorted_refs(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(values, key=lambda item: item.encode("utf-8")))


def _session_read_set_matches(
    batch: GovernanceCommitBatchV2,
    session: GovernanceAuthoritySessionV2,
    expected_streams: set[str],
) -> bool:
    by_stream = {entry.stream_ref: entry for entry in batch.read_set.entries}
    grant_stream = governance_issuer_grant_stream_ref_v2(
        session.scope_ref,
        session.grant_ref,
    )
    grant = by_stream.get(grant_stream)
    lifecycle = by_stream.get(GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2)
    return (
        set(by_stream) == expected_streams
        and grant is not None
        and grant.expected_revision == session.grant_expected_revision
        and grant.expected_root == session.grant_expected_root
        and lifecycle is not None
        and lifecycle.expected_revision == session.lifecycle_expected_revision
        and lifecycle.expected_root == session.lifecycle_expected_root
    )


def _is_committed(attempt: GovernanceCommitAttemptV2) -> bool:
    return bool(
        type(attempt) is GovernanceCommitAttemptV2
        and attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        and attempt.failure is None
        and attempt.committed_transition is not None
        and attempt.position_observation is not None
    )


def _same_commit(
    first: GovernanceCommitAttemptV2,
    second: GovernanceCommitAttemptV2,
) -> bool:
    if not _is_committed(first) or not _is_committed(second):
        return False
    assert first.committed_transition is not None
    assert second.committed_transition is not None
    return (
        first.committed_transition.committed_transition_root
        == second.committed_transition.committed_transition_root
        and first.committed_transition.receipt.receipt_root
        == second.committed_transition.receipt.receipt_root
    )


def _has_failure(
    attempt: GovernanceCommitAttemptV2,
    code: AuthorityDiagnosticCodeV2,
) -> bool:
    return bool(
        type(attempt) is GovernanceCommitAttemptV2
        and attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED
        and attempt.failure is not None
        and attempt.failure.code is code
        and attempt.committed_transition is None
        and attempt.position_observation is None
    )


def _binding_rejected(
    operation: Any,
    code: AuthorityDiagnosticCodeV2,
) -> bool:
    try:
        cast(Any, operation)()
    except GovernanceAuthorityBindingErrorV2 as exc:
        return exc.code is code
    return False


def _pickle_rejected(handle: object) -> bool:
    try:
        pickle.dumps(handle)
    except TypeError:
        return True
    return False


run_governance_authority_session_conformance_v2.__module__ = "pheroos.conformance"


__all__ = [
    "GOVERNANCE_AUTHORITY_SESSION_CONFORMANCE_VERSION_V2",
    "run_governance_authority_session_conformance_v2",
]
