from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
import json
import pickle
from copy import copy, deepcopy
from typing import cast

import pytest

from tests.governance import test_support_v2_operations as support_fixture

from pheroos.governance._authority_v2 import (
    FAILURE_STAGE_AFTER_TRACE_STAGING_V2,
    InMemoryGovernanceStateStoreV2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceDomainRetirementRequestV2,
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    governance_issuer_grant_stream_ref_v2,
    open_governance_authority_session_v2,
    retire_governance_domain_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)
from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.commit_gate_v2 import (
    CommitPermissionRequestV2,
    CommitStopRequestV2,
    VerifiedCommitPermissionSourceV2,
    VerifiedCommitPermissionStateV2,
    VerifiedCommitStopSourceV2,
    VerifiedCommitStopStateV2,
    commit_permission_allows_v2,
    commit_permission_state_is_current_v2,
    commit_permission_stream_ref_v2,
    commit_stop_blocks_v2,
    commit_stop_state_is_current_v2,
    commit_stop_stream_ref_v2,
    issue_commit_permission_v2,
    open_commit_permission_authority_session_v2,
    open_commit_stop_authority_session_v2,
    prepare_commit_permission_issue_v2,
    prepare_commit_stop_resolution_v2,
    rehydrate_commit_permission_state_v2,
    rehydrate_commit_stop_state_v2,
    require_current_commit_permission_state_v2,
    require_current_commit_stop_state_v2,
    resolve_commit_stop_v2,
)
from pheroos.governance.commit_state_v2 import (
    CommitReplayReceiptV2,
    ReplayNamespace,
    VerifiedCommitReplayStateV2,
    advance_commit_replay_state_v2,
    open_commit_replay_authority_session_v2,
    prepare_commit_replay_advance_v2,
    rehydrate_commit_replay_state_v2,
)
from pheroos.governance.permission import issue_action_permission
from pheroos.governance.risk_v2 import (
    RiskBand,
    VerifiedRiskStateV2,
    advance_risk_state_v2,
    open_risk_authority_session_v2,
    prepare_risk_state_advance_v2,
    rehydrate_risk_state_v2,
)
from pheroos.governance.support_v2 import (
    VerifiedMembershipStateV2,
    VerifiedPrincipalVerificationSetStateV2,
    VerifiedSupportStateV2,
    advance_principal_verification_set_v2,
    advance_support_state_v2,
    open_principal_verification_authority_session_v2,
    open_support_authority_session_v2,
    rehydrate_support_state_v2,
)
from pheroos.governance.stop_signal import StopSignal, resolve_stop_signal
from pheroos.protocol import COMMIT_INTEGRITY_PROFILE_VERSION
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    AuthorityDiagnosticCodeV2,
)
from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.commit_models import CommitAction, CommitAssurance
from pheroos.protocol.commit_wire import commit_policy_fingerprint


TARGET = support_fixture.TARGET
RUN_REF = support_fixture.RUN_REF
PROFILE = COMMIT_INTEGRITY_PROFILE_VERSION
GATE_EPOCH = 50
GATE_STEP = 6


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class _Environment:
    domain: AuthorityDomainV2
    store: InMemoryGovernanceStateStoreV2
    grant: GovernanceIssuerGrantV2
    manifest: ScopedProtocolManifestV2
    verification_state: VerifiedPrincipalVerificationSetStateV2
    replay_state: VerifiedCommitReplayStateV2
    risk_state: VerifiedRiskStateV2
    membership_state: VerifiedMembershipStateV2
    support_state: VerifiedSupportStateV2

    def capability(
        self,
        *,
        grant: GovernanceIssuerGrantV2 | None = None,
        epoch: int = GATE_EPOCH,
    ) -> GovernanceIssuerCapabilityV2:
        selected = self.grant if grant is None else grant
        return bind_governance_issuer_capability_v2(
            self.store, self.domain, selected, RUN_REF, epoch
        )


def _grant(
    domain: AuthorityDomainV2,
    *,
    issuer_ref: str = "issuer:gate:a",
    grant_ref: str = "grant:gate:a",
) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref=issuer_ref,
        grant_ref=grant_ref,
        grant_binding_ref=_root(f"binding:{grant_ref}"),
        operations=(
            GovernanceIssuerOperationV2.EVALUATE_QUORUM,
            GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
            GovernanceIssuerOperationV2.RESOLVE_STOP,
            GovernanceIssuerOperationV2.ADVANCE_REPLAY,
            GovernanceIssuerOperationV2.ISSUE_ACTION_PERMISSION,
            GovernanceIssuerOperationV2.RETIRE_DOMAIN,
        ),
        target_refs=(TARGET,),
        action_refs=("commit",),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100_000,
        revocation_generation=0,
    )


def _environment(
    scope: str = "scope:commit-gate-v2", *, failure_injector=None
) -> _Environment:
    domain = AuthorityDomainV2(
        policy_version=AUTHORITY_POLICY_VERSION_V2,
        profile=AUTHORITY_LOCAL_PROFILE_V2,
        wire_version=AUTHORITY_WIRE_VERSION_V2,
        canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref=scope,
    )
    store = InMemoryGovernanceStateStoreV2((domain,), failure_injector=failure_injector)
    grant = _grant(domain)
    activated = activate_governance_issuer_grant_v2(
        store, domain, grant, f"transition:{scope}:grant:a", 1
    )
    assert activated.disposition is GovernanceCommitDispositionV2.COMMITTED
    manifest = support_fixture._manifest()
    context = support_fixture._Context(domain, store, store, grant, manifest)
    upstreams = support_fixture._commit_upstreams(context)
    membership_state = upstreams.membership_state

    support_request, support_source = support_fixture._initialize_request(
        context, label="gate", current_step=3
    )
    support_session = open_support_authority_session_v2(
        bind_governance_issuer_capability_v2(
            store, domain, grant, RUN_REF, support_request.observed_epoch
        ),
        support_request,
    )
    support_attempt = advance_support_state_v2(
        support_request,
        source=support_source,
        authority_session=support_session,
    )
    assert support_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    support_state = rehydrate_support_state_v2(
        support_request.to_dict(), domain=domain, state_reader=store
    )

    policy = manifest.collective_commit_policy
    assert policy is not None
    replay_request, replay_source = prepare_commit_replay_advance_v2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        manifest_root=manifest.manifest_root,
        commit_policy_root=commit_policy_fingerprint(policy, profile=PROFILE),
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        protocol_ref=manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=5,
        advance_ref="advance:gate:replay",
        current_step=4,
        receipt_additions=(),
    )
    replay_session = open_commit_replay_authority_session_v2(
        bind_governance_issuer_capability_v2(store, domain, grant, RUN_REF, 5),
        replay_request,
    )
    replay_attempt = advance_commit_replay_state_v2(
        replay_request,
        source=replay_source,
        authority_session=replay_session,
    )
    assert replay_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    replay_state = rehydrate_commit_replay_state_v2(
        replay_request.to_dict(), domain=domain, state_reader=store
    )

    risk_request, risk_source = prepare_risk_state_advance_v2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        manifest=manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        epoch=1,
        advance_ref="advance:gate:risk",
        current_step=4,
        assessment_ref="assessment:gate:risk",
        risk_band=RiskBand.LOW,
        risk_input_roots=(_root("risk-input"),),
        rationale_codes=("risk:low",),
        assessment_method="deterministic-test-v2",
        issuer_ref=grant.issuer_ref,
        issued_at_step=4,
        expires_at_step=90_000,
        provenance_ref="urn:test:risk:gate",
        source_trace_roots=(_root("risk-trace"),),
    )
    risk_session = open_risk_authority_session_v2(
        bind_governance_issuer_capability_v2(store, domain, grant, RUN_REF, 1),
        risk_request,
    )
    risk_attempt = advance_risk_state_v2(
        risk_request, source=risk_source, authority_session=risk_session
    )
    assert risk_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    risk_state = rehydrate_risk_state_v2(
        risk_request.to_dict(), domain=domain, state_reader=store
    )
    return _Environment(
        domain,
        store,
        grant,
        manifest,
        upstreams.verification_state,
        replay_state,
        risk_state,
        membership_state,
        support_state,
    )


def _prepare_stop(
    environment: _Environment,
    *,
    label: str,
    blocked: bool = False,
    issuer_ref: str | None = None,
    parent=None,
):
    return prepare_commit_stop_resolution_v2(
        domain_root=environment.domain.domain_root,
        scope_ref=environment.domain.scope_ref,
        manifest=environment.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=GATE_EPOCH,
        resolution_ref=f"resolution:{label}",
        current_step=GATE_STEP,
        mutation_issuer_ref=(
            environment.grant.issuer_ref if issuer_ref is None else issuer_ref
        ),
        blocked=blocked,
        reason_codes=("stop:blocked",) if blocked else ("stop:clear",),
        issued_at_step=GATE_STEP,
        expires_at_step=GATE_STEP + 10,
        commit_replay_state=environment.replay_state,
        risk_state=environment.risk_state,
        membership_state=environment.membership_state,
        support_state=environment.support_state,
        parent_snapshot=parent,
    )


def _prepare_permission(
    environment: _Environment,
    *,
    label: str,
    allowed: bool = True,
    issuer_ref: str | None = None,
    parent=None,
):
    return prepare_commit_permission_issue_v2(
        domain_root=environment.domain.domain_root,
        scope_ref=environment.domain.scope_ref,
        manifest=environment.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=GATE_EPOCH,
        permission_ref=f"permission:{label}",
        current_step=GATE_STEP,
        mutation_issuer_ref=(
            environment.grant.issuer_ref if issuer_ref is None else issuer_ref
        ),
        allowed=allowed,
        claim_roots=(_root(f"claim:{label}"),) if allowed else (),
        issued_at_step=GATE_STEP,
        expires_at_step=GATE_STEP + 10,
        commit_replay_state=environment.replay_state,
        risk_state=environment.risk_state,
        membership_state=environment.membership_state,
        support_state=environment.support_state,
        parent_snapshot=parent,
    )


def test_genesis_atomic_trace_restart_lost_response_and_expiry() -> None:
    environment = _environment()
    stop_request, stop_source = _prepare_stop(environment, label="genesis")
    permission_request, permission_source = _prepare_permission(
        environment, label="genesis"
    )
    stop_session = open_commit_stop_authority_session_v2(
        environment.capability(), stop_request
    )
    permission_session = open_commit_permission_authority_session_v2(
        environment.capability(), permission_request
    )
    stop_attempt = resolve_commit_stop_v2(
        stop_request, source=stop_source, authority_session=stop_session
    )
    permission_attempt = issue_commit_permission_v2(
        permission_request,
        source=permission_source,
        authority_session=permission_session,
    )
    assert stop_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert permission_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    for attempt, event_type in (
        (stop_attempt, "commit_stop_resolved_v2"),
        (permission_attempt, "commit_permission_issued_v2"),
    ):
        assert attempt.committed_transition is not None
        batch = attempt.committed_transition.batch
        assert len(batch.read_set.entries) == 8
        assert batch.trace_batch.events[0].event_type == event_type
        assert (
            batch.trace_batch.events[0].lineage["read_set_root"]
            == batch.read_set.root()
        )

    restarted = InMemoryGovernanceStateStoreV2.from_snapshot_v2(
        environment.store.snapshot_v2()
    )
    restarted_permission_session = open_commit_permission_authority_session_v2(
        bind_governance_issuer_capability_v2(
            restarted,
            environment.domain,
            environment.grant,
            RUN_REF,
            permission_request.observed_epoch,
        ),
        permission_request,
    )
    lost_response_retry = issue_commit_permission_v2(
        permission_request,
        source=None,
        authority_session=restarted_permission_session,
    )
    assert lost_response_retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert lost_response_retry.committed_transition is not None
    assert permission_attempt.committed_transition is not None
    assert lost_response_retry.committed_transition.receipt.receipt_root == (
        permission_attempt.committed_transition.receipt.receipt_root
    )
    stop_state = rehydrate_commit_stop_state_v2(
        json.loads(stop_request.canonical_bytes()),
        domain=environment.domain,
        state_reader=restarted,
    )
    permission_state = rehydrate_commit_permission_state_v2(
        permission_request.to_dict(),
        domain=environment.domain,
        state_reader=restarted,
    )
    assert type(stop_state) is VerifiedCommitStopStateV2
    assert type(permission_state) is VerifiedCommitPermissionStateV2
    assert stop_state.position is GovernanceCommitPositionV2.CURRENT
    assert permission_state.position is GovernanceCommitPositionV2.CURRENT
    assert commit_stop_state_is_current_v2(stop_state)
    assert commit_permission_state_is_current_v2(permission_state)
    assert require_current_commit_stop_state_v2(stop_state) == stop_request.snapshot
    assert (
        require_current_commit_permission_state_v2(permission_state)
        == permission_request.snapshot
    )
    assert not commit_stop_blocks_v2(stop_state, current_step=GATE_STEP)
    assert commit_permission_allows_v2(
        permission_state,
        current_step=GATE_STEP,
        candidate_ref=permission_request.snapshot.candidate_refs[0],
    )
    assert not commit_permission_allows_v2(
        permission_state,
        current_step=permission_request.snapshot.expires_at_step,
        candidate_ref=permission_request.snapshot.candidate_refs[0],
    )
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(stop_state)
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(permission_state)


def test_atomic_failure_publishes_neither_gate_head_state_nor_trace_view() -> None:
    armed = False

    def fail_after_trace(stage, _batch):  # type: ignore[no-untyped-def]
        if armed and stage == FAILURE_STAGE_AFTER_TRACE_STAGING_V2:
            raise OSError("injected trace staging failure")

    environment = _environment(
        "scope:commit-gate:atomic-failure", failure_injector=fail_after_trace
    )
    request, source = _prepare_permission(environment, label="atomic-failure")
    session = open_commit_permission_authority_session_v2(
        environment.capability(), request
    )
    before = environment.store.snapshot_v2()
    armed = True
    unavailable = issue_commit_permission_v2(
        request, source=source, authority_session=session
    )
    assert unavailable.disposition is GovernanceCommitDispositionV2.FINALITY_UNAVAILABLE
    assert environment.store.snapshot_v2() == before
    assert (
        environment.store.load_head_v2(request.scope_ref, request.stream_ref).revision
        == 0
    )
    view = environment.store.load_commit_view_v2(
        request.scope_ref, request.stream_ref, request.transition_id
    )
    assert view.disposition is not GovernanceCommitDispositionV2.COMMITTED
    assert view.committed_transition is None


def test_fixed_streams_exclude_mutable_policy_epoch_issuer_and_candidates() -> None:
    environment = _environment("scope:commit-gate:selector")
    stop, _ = _prepare_stop(environment, label="selector")
    permission, _ = _prepare_permission(environment, label="selector")
    assert stop.stream_ref == commit_stop_stream_ref_v2(
        environment.domain.scope_ref,
        environment.manifest.id,
        RUN_REF,
        TARGET,
    )
    assert permission.stream_ref == commit_permission_stream_ref_v2(
        environment.domain.scope_ref,
        environment.manifest.id,
        RUN_REF,
        TARGET,
    )
    assert stop.stream_ref != permission.stream_ref
    assert "issuer" not in stop.stream_ref
    assert "candidate" not in permission.stream_ref


@pytest.mark.parametrize(("blocked", "allowed"), ((False, True), (True, False)))
def test_v1_gate_decision_meaning_is_preserved_without_v1_authority_reuse(
    blocked: bool, allowed: bool
) -> None:
    environment = _environment(f"scope:commit-gate:differential:{blocked}")
    v1_stop = resolve_stop_signal(
        StopSignal(
            target=TARGET,
            action=CommitAction.PUBLISH.value,
            reason="stop:blocked" if blocked else "stop:clear",
            blocking=blocked,
        )
    )
    stop, stop_source = _prepare_stop(
        environment, label="differential", blocked=blocked
    )
    stop_attempt = resolve_commit_stop_v2(
        stop,
        source=stop_source,
        authority_session=open_commit_stop_authority_session_v2(
            environment.capability(), stop
        ),
    )
    assert stop_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    stop_state = rehydrate_commit_stop_state_v2(
        stop.to_dict(), domain=environment.domain, state_reader=environment.store
    )
    assert commit_stop_blocks_v2(stop_state, current_step=GATE_STEP) is v1_stop.blocked

    permission, permission_source = _prepare_permission(
        environment, label="differential", allowed=allowed
    )
    permission_attempt = issue_commit_permission_v2(
        permission,
        source=permission_source,
        authority_session=open_commit_permission_authority_session_v2(
            environment.capability(), permission
        ),
    )
    assert permission_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    permission_state = rehydrate_commit_permission_state_v2(
        permission.to_dict(), domain=environment.domain, state_reader=environment.store
    )
    v1_permission = issue_action_permission(
        permission_id="permission:v1:differential",
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=permission.snapshot.manifest_root,
        commit_policy_root=permission.snapshot.commit_policy_root,
        protocol_id=environment.manifest.id,
        run_id=RUN_REF,
        target=TARGET,
        action=CommitAction.PUBLISH,
        epoch=GATE_EPOCH,
        decision_ref=_root("decision:differential"),
        certificate_ref=_root("certificate:differential"),
        allowed=allowed,
        reason_codes=("permission:allowed" if allowed else "permission:denied",),
        issuer_id=environment.grant.issuer_ref,
        policy_ref="policy:differential",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=GATE_STEP,
        expires_at_step=GATE_STEP + 10,
        provenance="urn:test:commit-gate:differential",
        trace_event_id="trace:commit-gate:differential",
    )
    assert (
        commit_permission_allows_v2(
            permission_state,
            current_step=GATE_STEP,
            candidate_ref=permission.snapshot.candidate_refs[0],
        )
        is v1_permission.allowed
    )


def test_canonical_wire_and_resource_bounds_fail_closed_without_store_io() -> None:
    environment = _environment("scope:commit-gate:wire")
    stop, _ = _prepare_stop(environment, label="wire", blocked=True)
    permission, _ = _prepare_permission(environment, label="wire")
    assert CommitStopRequestV2.from_dict(stop.to_dict()) == stop
    assert CommitPermissionRequestV2.from_dict(permission.to_dict()) == permission
    malformed_stop = stop.to_dict()
    malformed_stop["snapshot"] = dict(cast(dict, malformed_stop["snapshot"]))
    malformed_stop["snapshot"]["reason_codes"] = tuple(
        malformed_stop["snapshot"]["reason_codes"]
    )
    with pytest.raises(TypeError, match="exact array"):
        CommitStopRequestV2.from_dict(malformed_stop)
    malformed_permission = permission.to_dict()
    malformed_permission["snapshot"] = dict(
        cast(dict, malformed_permission["snapshot"])
    )
    malformed_permission["snapshot"]["allowed"] = 1
    with pytest.raises(TypeError, match="exact bool"):
        CommitPermissionRequestV2.from_dict(malformed_permission)
    boolean_epoch = stop.to_dict()
    boolean_epoch["observed_epoch"] = True
    cast(dict, boolean_epoch["snapshot"])["observed_epoch"] = True
    with pytest.raises(ValueError, match="integer bound"):
        CommitStopRequestV2.from_dict(boolean_epoch)
    substituted_root = permission.to_dict()
    substituted_snapshot = cast(dict, substituted_root["snapshot"])
    substituted_snapshot["candidate_set_root"] = _root("substituted-candidates")
    with pytest.raises(ValueError, match="candidate_set_root is mismatched"):
        CommitPermissionRequestV2.from_dict(substituted_root)
    oversized = "界" * 4097
    with pytest.raises(ValueError, match="text bound"):
        prepare_commit_stop_resolution_v2(
            domain_root=environment.domain.domain_root,
            scope_ref=environment.domain.scope_ref,
            manifest=environment.manifest,
            profile=PROFILE,
            run_ref=RUN_REF,
            target_ref=TARGET,
            observed_epoch=GATE_EPOCH,
            resolution_ref=oversized,
            current_step=GATE_STEP,
            mutation_issuer_ref=environment.grant.issuer_ref,
            blocked=False,
            reason_codes=(),
            issued_at_step=GATE_STEP,
            expires_at_step=GATE_STEP + 1,
            commit_replay_state=environment.replay_state,
            risk_state=environment.risk_state,
            membership_state=environment.membership_state,
            support_state=environment.support_state,
        )


def test_sources_and_states_are_opaque_nonportable_and_unforgeable() -> None:
    environment = _environment("scope:commit-gate:opaque")
    request, source = _prepare_stop(environment, label="opaque")
    for transport in (copy, deepcopy, pickle.dumps):
        with pytest.raises(TypeError, match="not portable"):
            transport(source)
    with pytest.raises(TypeError, match="cannot be constructed directly"):
        VerifiedCommitStopSourceV2()
    forged_source = object.__new__(VerifiedCommitStopSourceV2)
    rejected = resolve_commit_stop_v2(
        request,
        source=forged_source,
        authority_session=open_commit_stop_authority_session_v2(
            environment.capability(), request
        ),
    )
    assert rejected.disposition is GovernanceCommitDispositionV2.INVALID
    assert rejected.failure is not None
    assert rejected.failure.code is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH

    accepted = resolve_commit_stop_v2(
        request,
        source=source,
        authority_session=open_commit_stop_authority_session_v2(
            environment.capability(), request
        ),
    )
    assert accepted.disposition is GovernanceCommitDispositionV2.COMMITTED
    state = rehydrate_commit_stop_state_v2(
        request.to_dict(),
        domain=environment.domain,
        state_reader=environment.store,
    )
    assert copy(state) is state
    assert deepcopy(state) is state
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(state)
    with pytest.raises(TypeError, match="cannot be constructed directly"):
        VerifiedCommitStopStateV2()
    forged_state = object.__new__(VerifiedCommitStopStateV2)
    assert not commit_stop_state_is_current_v2(forged_state)
    with pytest.raises(Exception):
        _ = forged_state.snapshot

    with pytest.raises(TypeError, match="cannot be constructed directly"):
        VerifiedCommitPermissionSourceV2()
    with pytest.raises(TypeError, match="cannot be constructed directly"):
        VerifiedCommitPermissionStateV2()


def test_stale_dependency_requires_retry_without_publishing_a_gate_head() -> None:
    environment = _environment("scope:commit-gate:stale-dependency")
    request, source = _prepare_stop(environment, label="stale")
    session = open_commit_stop_authority_session_v2(environment.capability(), request)

    replay_receipt = CommitReplayReceiptV2(
        namespace=ReplayNamespace.OBSERVATION,
        record_id="record:gate:stale",
        nonce="nonce:gate:stale",
        payload_fingerprint=_root("payload:gate:stale"),
        target_ref=TARGET,
        candidate_ref=environment.manifest.candidates[0].id,
        epoch=2,
        principal_ref="principal:gate:stale",
    )
    policy = environment.manifest.collective_commit_policy
    assert policy is not None
    successor, successor_source = prepare_commit_replay_advance_v2(
        domain_root=environment.domain.domain_root,
        scope_ref=environment.domain.scope_ref,
        manifest_root=environment.manifest.manifest_root,
        commit_policy_root=commit_policy_fingerprint(policy, profile=PROFILE),
        profile=PROFILE,
        assurance=CommitAssurance.EVIDENCE_BOUND,
        protocol_ref=environment.manifest.id,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=GATE_EPOCH,
        advance_ref="advance:gate:stale",
        current_step=GATE_STEP - 1,
        receipt_additions=(replay_receipt,),
        parent_snapshot=environment.replay_state.snapshot,
    )
    replay_attempt = advance_commit_replay_state_v2(
        successor,
        source=successor_source,
        authority_session=open_commit_replay_authority_session_v2(
            environment.capability(), successor
        ),
    )
    assert replay_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED

    stale = resolve_commit_stop_v2(request, source=source, authority_session=session)
    assert stale.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert stale.failure is not None
    assert stale.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    assert (
        environment.store.load_head_v2(
            environment.domain.scope_ref, request.stream_ref
        ).revision
        == 0
    )


def test_principal_verification_advance_after_prepare_requires_retry() -> None:
    environment = _environment("scope:commit-gate:stale-verification")
    request, source = _prepare_permission(environment, label="stale-verification")
    session = open_commit_permission_authority_session_v2(
        environment.capability(), request
    )
    context = support_fixture._Context(
        environment.domain,
        environment.store,
        environment.store,
        environment.grant,
        environment.manifest,
    )
    successor, successor_source = support_fixture._prepare_verification(
        context,
        epoch=2,
        label="gate-stale-verification",
        issuer_ref=environment.grant.issuer_ref,
        parent=environment.verification_state.snapshot,
    )
    verification_attempt = advance_principal_verification_set_v2(
        successor,
        source=successor_source,
        authority_session=open_principal_verification_authority_session_v2(
            support_fixture._capability(
                context, environment.grant, successor.observed_epoch
            ),
            successor,
        ),
    )
    assert verification_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED

    stale = issue_commit_permission_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert stale.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert stale.failure is not None
    assert stale.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    assert (
        environment.store.load_head_v2(
            environment.domain.scope_ref, request.stream_ref
        ).revision
        == 0
    )


def test_32_identical_workers_reconcile_one_stop_and_permission_receipt() -> None:
    environment = _environment("scope:commit-gate:race-identical")
    stop, stop_source = _prepare_stop(environment, label="identical")
    stop_session = open_commit_stop_authority_session_v2(environment.capability(), stop)
    with ThreadPoolExecutor(max_workers=32) as pool:
        stop_attempts = tuple(
            pool.map(
                lambda _: resolve_commit_stop_v2(
                    stop, source=stop_source, authority_session=stop_session
                ),
                range(32),
            )
        )
    assert all(
        item.disposition is GovernanceCommitDispositionV2.COMMITTED
        for item in stop_attempts
    )
    assert (
        len(
            {
                item.committed_transition.receipt.receipt_root
                for item in stop_attempts
                if item.committed_transition is not None
            }
        )
        == 1
    )
    assert (
        environment.store.load_head_v2(
            environment.domain.scope_ref, stop.stream_ref
        ).revision
        == 1
    )

    permission, permission_source = _prepare_permission(environment, label="identical")
    permission_session = open_commit_permission_authority_session_v2(
        environment.capability(), permission
    )
    with ThreadPoolExecutor(max_workers=32) as pool:
        permission_attempts = tuple(
            pool.map(
                lambda _: issue_commit_permission_v2(
                    permission,
                    source=permission_source,
                    authority_session=permission_session,
                ),
                range(32),
            )
        )
    assert all(
        item.disposition is GovernanceCommitDispositionV2.COMMITTED
        for item in permission_attempts
    )
    assert (
        len(
            {
                item.committed_transition.receipt.receipt_root
                for item in permission_attempts
                if item.committed_transition is not None
            }
        )
        == 1
    )
    assert (
        environment.store.load_head_v2(
            environment.domain.scope_ref, permission.stream_ref
        ).revision
        == 1
    )


def test_stale_parent_successors_race_to_one_current_head() -> None:
    environment = _environment("scope:commit-gate:stale-parent")
    initial, initial_source = _prepare_stop(environment, label="parent")
    accepted = resolve_commit_stop_v2(
        initial,
        source=initial_source,
        authority_session=open_commit_stop_authority_session_v2(
            environment.capability(), initial
        ),
    )
    assert accepted.disposition is GovernanceCommitDispositionV2.COMMITTED
    children = tuple(
        _prepare_stop(
            environment,
            label=f"child:{index}",
            parent=initial.snapshot,
        )
        for index in range(32)
    )

    def commit_child(item):  # type: ignore[no-untyped-def]
        request, source = item
        return resolve_commit_stop_v2(
            request,
            source=source,
            authority_session=open_commit_stop_authority_session_v2(
                environment.capability(), request
            ),
        )

    with ThreadPoolExecutor(max_workers=32) as pool:
        outcomes = tuple(pool.map(commit_child, children))
    assert (
        sum(
            item.disposition is GovernanceCommitDispositionV2.COMMITTED
            for item in outcomes
        )
        == 1
    )
    assert all(
        item.disposition
        in (
            GovernanceCommitDispositionV2.COMMITTED,
            GovernanceCommitDispositionV2.RETRY_REQUIRED,
        )
        for item in outcomes
    )
    assert (
        environment.store.load_head_v2(
            environment.domain.scope_ref, initial.stream_ref
        ).revision
        == 2
    )


def test_32_way_gate_races_have_one_winner() -> None:
    environment = _environment("scope:commit-gate:races")
    stop_requests = [
        _prepare_stop(environment, label=f"race:{index}") for index in range(32)
    ]

    def commit_stop(item):  # type: ignore[no-untyped-def]
        request, source = item
        return resolve_commit_stop_v2(
            request,
            source=source,
            authority_session=open_commit_stop_authority_session_v2(
                environment.capability(), request
            ),
        )

    with ThreadPoolExecutor(max_workers=16) as pool:
        attempts = list(pool.map(commit_stop, stop_requests))
    dispositions = [item.disposition for item in attempts]
    assert dispositions.count(GovernanceCommitDispositionV2.COMMITTED) == 1
    assert dispositions.count(GovernanceCommitDispositionV2.RETRY_REQUIRED) == 31

    permission_requests = [
        _prepare_permission(environment, label=f"race:{index}") for index in range(32)
    ]

    def commit_permission(item):  # type: ignore[no-untyped-def]
        request, source = item
        return issue_commit_permission_v2(
            request,
            source=source,
            authority_session=open_commit_permission_authority_session_v2(
                environment.capability(), request
            ),
        )

    with ThreadPoolExecutor(max_workers=16) as pool:
        permission_attempts = list(pool.map(commit_permission, permission_requests))
    permission_dispositions = [item.disposition for item in permission_attempts]
    assert permission_dispositions.count(GovernanceCommitDispositionV2.COMMITTED) == 1
    assert (
        permission_dispositions.count(GovernanceCommitDispositionV2.RETRY_REQUIRED)
        == 31
    )


def test_issuer_rotation_and_exact_retry_precede_revocation() -> None:
    environment = _environment("scope:commit-gate:rotation")
    first, first_source = _prepare_stop(environment, label="first")
    first_session = open_commit_stop_authority_session_v2(
        environment.capability(), first
    )
    first_attempt = resolve_commit_stop_v2(
        first, source=first_source, authority_session=first_session
    )
    assert first_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    first_state = rehydrate_commit_stop_state_v2(
        first.to_dict(), domain=environment.domain, state_reader=environment.store
    )
    rotated = _grant(
        environment.domain,
        issuer_ref="issuer:gate:b",
        grant_ref="grant:gate:b",
    )
    assert (
        activate_governance_issuer_grant_v2(
            environment.store,
            environment.domain,
            rotated,
            "transition:gate:grant:b",
            2,
        ).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    successor, successor_source = _prepare_stop(
        environment,
        label="rotated",
        issuer_ref=rotated.issuer_ref,
        parent=first.snapshot,
    )
    successor_session = open_commit_stop_authority_session_v2(
        environment.capability(grant=rotated), successor
    )
    successor_attempt = resolve_commit_stop_v2(
        successor,
        source=successor_source,
        authority_session=successor_session,
    )
    assert successor_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert not commit_stop_state_is_current_v2(first_state)
    revoked = revoke_governance_issuer_grant_v2(
        environment.store,
        environment.domain,
        rotated.grant_ref,
        "transition:gate:grant:b:revoke",
        GATE_EPOCH + 1,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED
    retry = resolve_commit_stop_v2(
        successor, source=None, authority_session=successor_session
    )
    assert retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert retry.committed_transition is not None
    assert successor_attempt.committed_transition is not None
    assert (
        retry.committed_transition.receipt.receipt_root
        == successor_attempt.committed_transition.receipt.receipt_root
    )


def test_sealed_domain_denies_new_gate_write_but_preserves_exact_retry() -> None:
    environment = _environment("scope:commit-gate:sealed")
    committed, committed_source = _prepare_stop(environment, label="sealed:accepted")
    committed_session = open_commit_stop_authority_session_v2(
        environment.capability(), committed
    )
    accepted = resolve_commit_stop_v2(
        committed,
        source=committed_source,
        authority_session=committed_session,
    )
    assert accepted.disposition is GovernanceCommitDispositionV2.COMMITTED

    pending, pending_source = _prepare_permission(environment, label="sealed:pending")
    pending_session = open_commit_permission_authority_session_v2(
        environment.capability(), pending
    )
    stream_refs = tuple(
        sorted(
            {
                governance_issuer_grant_stream_ref_v2(
                    environment.domain.scope_ref, environment.grant.grant_ref
                ),
                environment.replay_state.snapshot.stream_ref,
                environment.risk_state.snapshot.stream_ref,
                environment.membership_state.snapshot.verification_stream_ref,
                environment.membership_state.snapshot.stream_ref,
                environment.support_state.snapshot.stream_ref,
                committed.stream_ref,
            },
            key=lambda item: item.encode("utf-8"),
        )
    )
    retirement = GovernanceDomainRetirementRequestV2(
        domain_root=environment.domain.domain_root,
        scope_ref=environment.domain.scope_ref,
        run_ref=RUN_REF,
        request_ref="request:commit-gate-v2:retire",
        transition_id="transition:commit-gate-v2:retire",
        stream_refs=stream_refs,
        reason_ref="reason:test-complete",
        observed_epoch=GATE_EPOCH + 1,
    )
    retirement_session = open_governance_authority_session_v2(
        environment.capability(epoch=retirement.observed_epoch), retirement
    )
    retired = retire_governance_domain_v2(
        retirement, authority_session=retirement_session
    )
    assert retired.disposition is GovernanceCommitDispositionV2.COMMITTED

    exact_retry = resolve_commit_stop_v2(
        committed,
        source=None,
        authority_session=committed_session,
    )
    assert exact_retry.disposition is GovernanceCommitDispositionV2.COMMITTED
    assert exact_retry.committed_transition is not None
    assert accepted.committed_transition is not None
    assert exact_retry.committed_transition.receipt.receipt_root == (
        accepted.committed_transition.receipt.receipt_root
    )
    denied = issue_commit_permission_v2(
        pending,
        source=pending_source,
        authority_session=pending_session,
    )
    assert denied.disposition is GovernanceCommitDispositionV2.DENIED
    assert denied.failure is not None
    assert denied.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED


def test_trace_or_committed_state_tamper_and_finality_fail_closed() -> None:
    environment = _environment("scope:commit-gate:tamper")
    request, source = _prepare_permission(environment, label="tamper")
    attempt = issue_commit_permission_v2(
        request,
        source=source,
        authority_session=open_commit_permission_authority_session_v2(
            environment.capability(), request
        ),
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    wrapper = support_fixture._AdversarialStore(
        environment.store, environment.domain.domain_root
    )
    wrapper.finality_transition_ids.add(request.transition_id)
    with pytest.raises(Exception, match="governance_finality_unavailable"):
        rehydrate_commit_permission_state_v2(
            request.to_dict(),
            domain=environment.domain,
            state_reader=wrapper,
        )
    wrapper.finality_transition_ids.clear()

    def tamper(view):  # type: ignore[no-untyped-def]
        assert view.committed_transition is not None
        transition = view.committed_transition.batch.transition
        assert transition is not None
        records = cast(dict, transition.to_dict()["state_records"])
        records["source_context_root"] = _root("tampered-source")
        object.__setattr__(transition, "state_records", records)

    wrapper.view_mutator = tamper
    with pytest.raises(Exception, match="governance_committed_transition_invalid"):
        rehydrate_commit_permission_state_v2(
            request.to_dict(),
            domain=environment.domain,
            state_reader=wrapper,
        )


@pytest.mark.parametrize(
    "mutation",
    ("receipt", "inclusion", "position", "trace"),
)
def test_receipt_inclusion_position_and_trace_tamper_fail_closed(
    mutation: str,
) -> None:
    environment = _environment(f"scope:commit-gate:commit-view:{mutation}")
    request, source = _prepare_permission(environment, label=mutation)
    attempt = issue_commit_permission_v2(
        request,
        source=source,
        authority_session=open_commit_permission_authority_session_v2(
            environment.capability(), request
        ),
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    wrapper = support_fixture._AdversarialStore(
        environment.store, environment.domain.domain_root
    )
    state = rehydrate_commit_permission_state_v2(
        request.to_dict(), domain=environment.domain, state_reader=wrapper
    )

    def tamper(view):  # type: ignore[no-untyped-def]
        assert view.committed_transition is not None
        if mutation == "receipt":
            object.__setattr__(
                view.committed_transition.receipt,
                "receipt_root",
                _root("forged:receipt"),
            )
        elif mutation == "inclusion":
            object.__setattr__(view.committed_transition, "inclusion_proof", None)
        elif mutation == "position":
            assert view.position_observation is not None
            object.__setattr__(
                view.position_observation,
                "observed_head_root",
                _root("forged:position"),
            )
        else:
            trace_batch = view.committed_transition.batch.trace_batch
            trace_wire = trace_batch.to_dict()
            events = cast(list[dict], trace_wire["events"])
            cast(dict, events[0]["lineage"])["snapshot_root"] = _root("forged:trace")
            object.__setattr__(trace_batch, "_event_snapshots", tuple(events))

    wrapper.view_mutator = tamper
    assert not commit_permission_state_is_current_v2(state)
    with pytest.raises(Exception, match="governance_committed_transition_invalid"):
        require_current_commit_permission_state_v2(state)
    with pytest.raises(Exception, match="governance_committed_transition_invalid"):
        rehydrate_commit_permission_state_v2(
            request.to_dict(), domain=environment.domain, state_reader=wrapper
        )


def test_static_owner_has_no_legacy_authority_or_runtime_registry() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "pheroos/governance/_commit_gate_v2"
    source = "\n".join(path.read_text() for path in root.glob("*.py"))
    for forbidden in (
        "_ISSUANCE",
        "authority_registry",
        "cursor",
        "pheroos.governance._commit.",
        "pheroos.governance._commit_state.",
        "pheroos.governance._baseline_output_v2",
    ):
        assert forbidden not in source
    assert max(len(path.read_text().splitlines()) for path in root.glob("*.py")) < 600
