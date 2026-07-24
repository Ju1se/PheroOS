from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import pickle
from typing import Any, cast

import pytest

from pheroos.governance._authority_session_v2.contracts import (
    GovernanceAuthorityBindingErrorV2,
    GovernanceDomainRetirementRequestV2,
)
from pheroos.governance._authority_session_v2.operations import (
    open_governance_authority_session_v2,
    retire_governance_domain_v2,
)
from pheroos.governance._authority_v2 import InMemoryGovernanceStateStoreV2
from pheroos.governance._support_v2.common import (
    MAX_SUPPORT_RESOURCE_DEPTH_V2,
    MAX_SUPPORT_RESOURCE_NODES_V2,
    MAX_SUPPORT_RESOURCE_TEXT_BYTES_V2,
    _preflight_support_resources_v2,
)
from pheroos.governance._support_v2.membership_contracts import (
    MAX_MEMBERSHIP_CLUSTERS_V2,
    MembershipCommitRequestV2,
    MembershipSnapshotV2,
    membership_transition_id_v2,
)
from pheroos.governance._support_v2.membership_operations import (
    VerifiedMembershipStateV2,
    commit_membership_epoch_v2,
    membership_state_is_current_v2,
    open_membership_authority_session_v2,
    rehydrate_membership_state_v2,
    require_current_membership_state_v2,
)
from pheroos.governance._support_v2.membership_source import (
    VerifiedMembershipSourceV2,
    _issue_source as _issue_membership_source,
    prepare_membership_commit_v2,
)
from pheroos.governance._support_v2.principal_verification_contracts import (
    PrincipalVerificationSetAdvanceRequestV2,
    PrincipalVerificationSetSnapshotV2,
)
from pheroos.governance._support_v2.principal_verification_operations import (
    VerifiedPrincipalVerificationSetStateV2,
    advance_principal_verification_set_v2,
    open_principal_verification_authority_session_v2,
    principal_verification_set_is_current_v2,
    rehydrate_principal_verification_set_state_v2,
    require_current_principal_verification_set_v2,
)
from pheroos.governance._support_v2.principal_verification_records import (
    MAX_PRINCIPAL_VERIFICATIONS_V2,
    PrincipalVerificationRecordV2,
)
from pheroos.governance._support_v2.principal_verification_source import (
    VerifiedPrincipalVerificationSourceV2,
    prepare_principal_verification_set_v2,
)
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    governance_issuer_grant_stream_ref_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance.authority_store_v2 import (
    AUTHORITY_LEDGER_VERSION_V2,
    AUTHORITY_LOCAL_PROFILE_V2,
    AUTHORITY_POLICY_VERSION_V2,
    AUTHORITY_WIRE_VERSION_V2,
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    GOVERNANCE_STATE_STORE_VERSION_V2,
    GOVERNANCE_TRACE_BATCH_VERSION_V2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitViewV2,
    GovernanceFailureStageV2,
    GovernanceFailureV2,
    GovernanceHeadV2,
    GovernanceStateStoreV2,
)
from pheroos.protocol import COMMIT_INTEGRITY_PROFILE_VERSION
from pheroos.protocol.authority_v2 import (
    AUTHORITY_CANONICAL_VERSION_V2,
    GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
    AuthorityDiagnosticCodeV2,
    GovernanceAuthorityReadSetV2,
)
from pheroos.protocol.authority_manifest_v2 import (
    ScopedProtocolManifestV2,
    scoped_capability_manifest_v2_from_dict,
)
from pheroos.protocol.commit_models import (
    CollectiveCommitPolicy,
    CommitAssurance,
)
from pheroos.protocol.loader import load_capability_manifest


ROOT = Path(__file__).resolve().parents[2]
PROFILE = COMMIT_INTEGRITY_PROFILE_VERSION
TARGET = "decision:review"
RUN_REF = "run:membership-v2-operations"


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _manifest() -> ScopedProtocolManifestV2:
    payload = json.loads(
        (ROOT / "examples/scoped-output-protocol/capability.json").read_text()
    )
    scoped = scoped_capability_manifest_v2_from_dict(payload).protocol
    legacy = load_capability_manifest(
        ROOT / "examples/hybrid-commit-protocol/capability.json"
    )
    policy = legacy.protocol.collective_commit_policy
    assert type(policy) is CollectiveCommitPolicy
    return replace(scoped, collective_commit_policy=replace(policy, target=TARGET))


@dataclass(frozen=True, slots=True)
class _Context:
    domain: AuthorityDomainV2
    store: GovernanceStateStoreV2
    base_store: InMemoryGovernanceStateStoreV2
    grant: GovernanceIssuerGrantV2


def _grant(
    domain: AuthorityDomainV2,
    *,
    issuer_ref: str,
    grant_ref: str,
    operations: tuple[GovernanceIssuerOperationV2, ...] = (
        GovernanceIssuerOperationV2.EVALUATE_QUORUM,
        GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
    ),
) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref=issuer_ref,
        grant_ref=grant_ref,
        grant_binding_ref=_root(f"binding:{domain.scope_ref}:{grant_ref}"),
        operations=operations,
        target_refs=(TARGET,),
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=10_000,
        revocation_generation=0,
    )


def _context(
    *,
    scope_ref: str,
    operations: tuple[GovernanceIssuerOperationV2, ...] = (
        GovernanceIssuerOperationV2.EVALUATE_QUORUM,
        GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
    ),
    store_wrapper: Callable[[GovernanceStateStoreV2, str], GovernanceStateStoreV2]
    | None = None,
) -> _Context:
    domain = AuthorityDomainV2(
        policy_version=AUTHORITY_POLICY_VERSION_V2,
        profile=AUTHORITY_LOCAL_PROFILE_V2,
        wire_version=AUTHORITY_WIRE_VERSION_V2,
        canonical_version=AUTHORITY_CANONICAL_VERSION_V2,
        ledger_version=AUTHORITY_LEDGER_VERSION_V2,
        state_store_version=GOVERNANCE_STATE_STORE_VERSION_V2,
        trace_batch_version=GOVERNANCE_TRACE_BATCH_VERSION_V2,
        read_set_version=GOVERNANCE_AUTHORITY_READ_SET_VERSION_V2,
        scope_ref=scope_ref,
    )
    base = InMemoryGovernanceStateStoreV2((domain,))
    grant = _grant(
        domain,
        issuer_ref="issuer:membership:a",
        grant_ref="grant:membership:a",
        operations=operations,
    )
    activated = activate_governance_issuer_grant_v2(
        base, domain, grant, f"transition:{scope_ref}:grant:a", 1
    )
    assert activated.disposition is GovernanceCommitDispositionV2.COMMITTED
    store: GovernanceStateStoreV2 = (
        base if store_wrapper is None else store_wrapper(base, domain.domain_root)
    )
    return _Context(domain, store, base, grant)


def _capability(
    context: _Context,
    grant: GovernanceIssuerGrantV2,
    observed_epoch: int,
) -> GovernanceIssuerCapabilityV2:
    return bind_governance_issuer_capability_v2(
        context.store,
        context.domain,
        grant,
        RUN_REF,
        observed_epoch,
    )


def _activate_rotated_grant(
    context: _Context,
    *,
    issuer_ref: str = "issuer:membership:b",
    grant_ref: str = "grant:membership:b",
) -> GovernanceIssuerGrantV2:
    grant = _grant(
        context.domain,
        issuer_ref=issuer_ref,
        grant_ref=grant_ref,
    )
    result = activate_governance_issuer_grant_v2(
        context.store,
        context.domain,
        grant,
        f"transition:{context.domain.scope_ref}:{grant_ref}",
        2,
    )
    assert result.disposition is GovernanceCommitDispositionV2.COMMITTED
    return grant


def _record(
    index: int,
    *,
    cluster_ref: str | None = None,
) -> PrincipalVerificationRecordV2:
    return PrincipalVerificationRecordV2(
        principal_ref=f"principal:{index}",
        cluster_ref=cluster_ref or f"cluster:{index}",
        failure_domain_ref=f"failure-domain:{index % 2}",
        verification_method="external-attestation-v2",
        verification_issuer_ref="identity:verifier",
        attestation_root=_root(f"attestation:{index}"),
        evidence_roots=(_root(f"evidence:{index}"),),
        issued_at_step=1,
        expires_at_step=10_000,
        provenance_ref=f"urn:test:verification:{index}",
        source_trace_roots=(_root(f"trace:verification:{index}"),),
    )


def _prepare_verification(
    context: _Context,
    *,
    epoch: int,
    label: str,
    issuer_ref: str = "issuer:membership:a",
    parent: PrincipalVerificationSetSnapshotV2 | None = None,
    records: tuple[PrincipalVerificationRecordV2, ...] | None = None,
) -> tuple[
    PrincipalVerificationSetAdvanceRequestV2,
    VerifiedPrincipalVerificationSourceV2,
]:
    return cast(
        tuple[
            PrincipalVerificationSetAdvanceRequestV2,
            VerifiedPrincipalVerificationSourceV2,
        ],
        prepare_principal_verification_set_v2(
            domain_root=context.domain.domain_root,
            scope_ref=context.domain.scope_ref,
            manifest=_manifest(),
            profile=PROFILE,
            assurance=CommitAssurance.EVIDENCE_BOUND,
            run_ref=RUN_REF,
            target_ref=TARGET,
            epoch=epoch,
            observed_epoch=100 + epoch,
            advance_ref=f"advance:verification:{label}",
            snapshot_ref=f"snapshot:verification:{label}",
            current_step=epoch * 10,
            expires_at_step=9_000,
            mutation_issuer_ref=issuer_ref,
            records=(_record(1, cluster_ref="cluster:shared"),)
            if records is None
            else records,
            parent_snapshot=parent,
        ),
    )


def _advance_verification(
    context: _Context,
    request: PrincipalVerificationSetAdvanceRequestV2,
    source: VerifiedPrincipalVerificationSourceV2,
    *,
    grant: GovernanceIssuerGrantV2 | None = None,
) -> tuple[GovernanceCommitAttemptV2, object]:
    selected = context.grant if grant is None else grant
    session = open_principal_verification_authority_session_v2(
        _capability(context, selected, request.observed_epoch), request
    )
    return (
        advance_principal_verification_set_v2(
            request, source=source, authority_session=session
        ),
        session,
    )


def _verification_state(
    context: _Context,
    request: PrincipalVerificationSetAdvanceRequestV2,
) -> VerifiedPrincipalVerificationSetStateV2:
    return rehydrate_principal_verification_set_state_v2(
        request.to_dict(), domain=context.domain, state_reader=context.store
    )


def _prepare_membership(
    context: _Context,
    verification_state: VerifiedPrincipalVerificationSetStateV2,
    *,
    epoch: int,
    label: str,
    issuer_ref: str = "issuer:membership:a",
    parent: MembershipSnapshotV2 | None = None,
) -> tuple[MembershipCommitRequestV2, VerifiedMembershipSourceV2]:
    return cast(
        tuple[MembershipCommitRequestV2, VerifiedMembershipSourceV2],
        prepare_membership_commit_v2(
            domain_root=context.domain.domain_root,
            scope_ref=context.domain.scope_ref,
            manifest=_manifest(),
            profile=PROFILE,
            assurance=CommitAssurance.EVIDENCE_BOUND,
            run_ref=RUN_REF,
            target_ref=TARGET,
            epoch=epoch,
            observed_epoch=100 + epoch,
            request_ref=f"request:membership:{label}",
            snapshot_ref=f"snapshot:membership:{label}",
            current_step=epoch * 10 + 1,
            expires_at_step=8_000,
            mutation_issuer_ref=issuer_ref,
            membership_method="store-current-verification-set-v2",
            provenance_ref=f"urn:test:membership:{label}",
            source_trace_roots=(_root(f"trace:membership:{label}"),),
            verification_state=verification_state,
            parent_snapshot=parent,
        ),
    )


def _commit_membership(
    context: _Context,
    request: MembershipCommitRequestV2,
    source: VerifiedMembershipSourceV2,
    *,
    grant: GovernanceIssuerGrantV2 | None = None,
) -> tuple[GovernanceCommitAttemptV2, object]:
    selected = context.grant if grant is None else grant
    session = open_membership_authority_session_v2(
        _capability(context, selected, request.observed_epoch), request
    )
    return (
        commit_membership_epoch_v2(request, source=source, authority_session=session),
        session,
    )


def _membership_state(
    context: _Context,
    request: MembershipCommitRequestV2,
) -> VerifiedMembershipStateV2:
    return rehydrate_membership_state_v2(
        request.to_dict(), domain=context.domain, state_reader=context.store
    )


def _committed_pair(
    context: _Context,
    *,
    label: str = "genesis",
) -> tuple[
    PrincipalVerificationSetAdvanceRequestV2,
    VerifiedPrincipalVerificationSetStateV2,
    MembershipCommitRequestV2,
    VerifiedMembershipStateV2,
]:
    verification, verification_source = _prepare_verification(
        context, epoch=1, label=label
    )
    verification_attempt, _ = _advance_verification(
        context, verification, verification_source
    )
    assert verification_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    verification_state = _verification_state(context, verification)
    membership, membership_source = _prepare_membership(
        context, verification_state, epoch=1, label=label
    )
    membership_attempt, _ = _commit_membership(context, membership, membership_source)
    assert membership_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    return (
        verification,
        verification_state,
        membership,
        _membership_state(context, membership),
    )


def _assert_code(
    attempt: GovernanceCommitAttemptV2,
    disposition: GovernanceCommitDispositionV2,
    code: AuthorityDiagnosticCodeV2,
) -> None:
    assert attempt.disposition is disposition
    assert attempt.failure is not None
    assert attempt.failure.code is code


def test_real_store_success_restart_read_sets_trace_and_opaque_states() -> None:
    context = _context(scope_ref="scope:membership-v2:success")
    verification, _, membership, _ = _committed_pair(context)

    verification_view = context.store.load_commit_view_v2(
        context.domain.scope_ref,
        verification.stream_ref,
        verification.transition_id,
    )
    membership_view = context.store.load_commit_view_v2(
        context.domain.scope_ref,
        membership.stream_ref,
        membership.transition_id,
    )
    assert verification_view.committed_transition is not None
    assert membership_view.committed_transition is not None
    verification_batch = verification_view.committed_transition.batch
    membership_batch = membership_view.committed_transition.batch
    assert {entry.stream_ref for entry in verification_batch.read_set.entries} == {
        verification.stream_ref,
        governance_issuer_grant_stream_ref_v2(
            context.domain.scope_ref, context.grant.grant_ref
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    assert {entry.stream_ref for entry in membership_batch.read_set.entries} == {
        membership.stream_ref,
        verification.stream_ref,
        governance_issuer_grant_stream_ref_v2(
            context.domain.scope_ref, context.grant.grant_ref
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    assert verification_batch.trace_batch.events[0].event_type == (
        "principal_verification_set_advanced"
    )
    assert membership_batch.trace_batch.events[0].event_type == (
        "membership_epoch_committed"
    )
    assert (
        membership_batch.trace_batch.events[0].lineage["verification_head_root"]
        == verification_view.committed_transition.receipt.head_root
    )

    restarted = InMemoryGovernanceStateStoreV2.from_snapshot_v2(
        context.base_store.snapshot_v2()
    )
    verification_state = rehydrate_principal_verification_set_state_v2(
        json.loads(verification.canonical_bytes()),
        domain=context.domain,
        state_reader=restarted,
    )
    membership_state = rehydrate_membership_state_v2(
        json.loads(membership.canonical_bytes()),
        domain=context.domain,
        state_reader=restarted,
    )
    assert require_current_principal_verification_set_v2(verification_state) == (
        verification.snapshot
    )
    assert require_current_membership_state_v2(membership_state) == membership.snapshot
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(verification_state)
    with pytest.raises(TypeError, match="not portable"):
        pickle.dumps(membership_state)


def test_lost_responses_exact_retry_after_revocation_return_same_receipts() -> None:
    context = _context(scope_ref="scope:membership-v2:lost-response")
    verification, verification_source = _prepare_verification(
        context, epoch=1, label="lost"
    )
    verification_attempt, verification_session = _advance_verification(
        context, verification, verification_source
    )
    assert verification_attempt.committed_transition is not None
    verification_state = _verification_state(context, verification)
    membership, membership_source = _prepare_membership(
        context, verification_state, epoch=1, label="lost"
    )
    membership_attempt, membership_session = _commit_membership(
        context, membership, membership_source
    )
    assert membership_attempt.committed_transition is not None

    revoked = revoke_governance_issuer_grant_v2(
        context.store,
        context.domain,
        context.grant.grant_ref,
        "transition:membership-v2:revoke-after-lost-response",
        102,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED
    verification_retry = advance_principal_verification_set_v2(
        verification, source=None, authority_session=verification_session
    )
    membership_retry = commit_membership_epoch_v2(
        membership, source=None, authority_session=membership_session
    )
    for retry, accepted in (
        (verification_retry, verification_attempt),
        (membership_retry, membership_attempt),
    ):
        assert retry.disposition is GovernanceCommitDispositionV2.COMMITTED
        assert retry.committed_transition is not None
        assert accepted.committed_transition is not None
        assert retry.committed_transition.receipt.receipt_root == (
            accepted.committed_transition.receipt.receipt_root
        )


def test_stale_forks_currentness_and_transitive_history_survive_restart() -> None:
    context = _context(scope_ref="scope:membership-v2:history")
    verification1, verification_state1, membership1, membership_state1 = (
        _committed_pair(context)
    )
    verification2, source2 = _prepare_verification(
        context,
        epoch=2,
        label="child",
        parent=verification1.snapshot,
        records=(
            _record(1, cluster_ref="cluster:shared"),
            _record(2, cluster_ref="cluster:shared"),
        ),
    )
    verification_fork, fork_source = _prepare_verification(
        context,
        epoch=2,
        label="fork",
        parent=verification1.snapshot,
        records=(_record(3),),
    )
    assert _advance_verification(context, verification2, source2)[0].disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    stale_verification = _advance_verification(context, verification_fork, fork_source)[
        0
    ]
    _assert_code(
        stale_verification,
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
    )
    assert not principal_verification_set_is_current_v2(verification_state1)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as stale_verification_state:
        require_current_principal_verification_set_v2(verification_state1)
    assert stale_verification_state.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    )

    verification_state2 = _verification_state(context, verification2)
    membership2, membership_source2 = _prepare_membership(
        context,
        verification_state2,
        epoch=2,
        label="child",
        parent=membership1.snapshot,
    )
    membership_fork, membership_fork_source = _prepare_membership(
        context,
        verification_state2,
        epoch=2,
        label="fork",
        parent=membership1.snapshot,
    )
    assert (
        _commit_membership(context, membership2, membership_source2)[0].disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    stale_membership = _commit_membership(
        context, membership_fork, membership_fork_source
    )[0]
    _assert_code(
        stale_membership,
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
    )
    assert not membership_state_is_current_v2(membership_state1)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as stale_membership_state:
        require_current_membership_state_v2(membership_state1)
    assert stale_membership_state.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    )

    restarted = InMemoryGovernanceStateStoreV2.from_snapshot_v2(
        context.base_store.snapshot_v2()
    )
    recovered = rehydrate_membership_state_v2(
        membership2.to_dict(), domain=context.domain, state_reader=restarted
    )
    assert recovered.snapshot == membership2.snapshot
    assert recovered.snapshot.principal_count == 2


def test_membership_rejects_stale_verification_dependency_without_write() -> None:
    context = _context(scope_ref="scope:membership-v2:verification-stale")
    verification1, verification_state1, _, _ = _committed_pair(context)
    pending, pending_source = _prepare_membership(
        context, verification_state1, epoch=1, label="pending-old-verification"
    )
    pending_session = open_membership_authority_session_v2(
        _capability(context, context.grant, pending.observed_epoch), pending
    )

    verification2, source2 = _prepare_verification(
        context,
        epoch=2,
        label="supersede-before-membership",
        parent=verification1.snapshot,
    )
    assert _advance_verification(context, verification2, source2)[0].disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    before = context.store.load_head_v2(
        context.domain.scope_ref, pending.stream_ref
    ).revision
    rejected = commit_membership_epoch_v2(
        pending, source=pending_source, authority_session=pending_session
    )
    _assert_code(
        rejected,
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
    )
    assert (
        context.store.load_head_v2(
            context.domain.scope_ref, pending.stream_ref
        ).revision
        == before
    )


def test_issuer_rotation_preserves_fixed_lineages_and_historical_verifiability() -> (
    None
):
    context = _context(scope_ref="scope:membership-v2:issuer-rotation")
    verification1, _, membership1, _ = _committed_pair(context)
    rotated = _activate_rotated_grant(context)

    verification2, source2 = _prepare_verification(
        context,
        epoch=2,
        label="rotated",
        issuer_ref=rotated.issuer_ref,
        parent=verification1.snapshot,
    )
    assert (
        _advance_verification(context, verification2, source2, grant=rotated)[
            0
        ].disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    membership2, membership_source2 = _prepare_membership(
        context,
        _verification_state(context, verification2),
        epoch=2,
        label="rotated",
        issuer_ref=rotated.issuer_ref,
        parent=membership1.snapshot,
    )
    assert (
        _commit_membership(context, membership2, membership_source2, grant=rotated)[
            0
        ].disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    assert verification1.stream_ref == verification2.stream_ref
    assert membership1.stream_ref == membership2.stream_ref

    assert (
        revoke_governance_issuer_grant_v2(
            context.store,
            context.domain,
            context.grant.grant_ref,
            "transition:membership-v2:revoke-old-issuer",
            103,
        ).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    restarted = InMemoryGovernanceStateStoreV2.from_snapshot_v2(
        context.base_store.snapshot_v2()
    )
    recovered = rehydrate_membership_state_v2(
        membership2.to_dict(), domain=context.domain, state_reader=restarted
    )
    assert recovered.snapshot.mutation_issuer_ref == rotated.issuer_ref


def _forge_membership_request(
    request: MembershipCommitRequestV2,
    *,
    label: str,
    **snapshot_changes: object,
) -> MembershipCommitRequestV2:
    request_ref = f"request:membership:forged:{label}"
    transition_id = membership_transition_id_v2(request.stream_ref, request_ref)
    snapshot = replace(
        request.snapshot,
        request_ref=request_ref,
        transition_id=transition_id,
        snapshot_ref=f"snapshot:membership:forged:{label}",
        membership_root="",
        snapshot_root="",
        **snapshot_changes,
    )
    return replace(
        request,
        request_ref=request_ref,
        transition_id=transition_id,
        snapshot=snapshot,
        request_root="",
    )


@pytest.mark.parametrize(  # type: ignore[misc]
    "violation", ("projection", "future", "expiry")
)
def test_store_recomputes_projection_and_verification_timeline(
    violation: str,
) -> None:
    context = _context(scope_ref=f"scope:membership-v2:semantic:{violation}")
    verification, verification_source = _prepare_verification(
        context,
        epoch=1,
        label=violation,
        records=(
            _record(1, cluster_ref="cluster:shared"),
            _record(2, cluster_ref="cluster:shared"),
        ),
    )
    assert (
        _advance_verification(context, verification, verification_source)[0].disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    membership, _ = _prepare_membership(
        context,
        _verification_state(context, verification),
        epoch=1,
        label=violation,
    )
    changes: dict[str, object]
    if violation == "projection":
        cluster = membership.snapshot.clusters[0]
        principal = replace(
            cluster.principals[0],
            verification_method="forged-verification-method",
            principal_root="",
        )
        changes = {
            "clusters": (
                replace(
                    cluster,
                    principals=(principal, *cluster.principals[1:]),
                    cluster_root="",
                ),
            )
        }
    elif violation == "future":
        changes = {
            "issued_at_step": verification.snapshot.current_step - 1,
            "verification_current_step": verification.snapshot.current_step - 1,
        }
    else:
        changes = {
            "expires_at_step": verification.snapshot.expires_at_step + 1,
            "verification_expires_at_step": verification.snapshot.expires_at_step + 1,
        }
    forged = _forge_membership_request(membership, label=violation, **changes)
    forged_source = _issue_membership_source(forged, _manifest())
    session = open_membership_authority_session_v2(
        _capability(context, context.grant, forged.observed_epoch), forged
    )
    attempt = commit_membership_epoch_v2(
        forged, source=forged_source, authority_session=session
    )
    _assert_code(
        attempt,
        GovernanceCommitDispositionV2.RETRY_REQUIRED,
        AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE,
    )
    assert (
        context.store.load_head_v2(context.domain.scope_ref, forged.stream_ref).revision
        == 0
    )


class _AdversarialReader:
    def __init__(self, store: GovernanceStateStoreV2, domain_root: str) -> None:
        self.store = store
        self.domain_root = domain_root
        self.finality_transition_ids: set[str] = set()
        self.hidden_transition_ids: set[str] = set()
        self.view_mutator: Callable[[GovernanceCommitViewV2], None] | None = None
        self.atomic_commits = 0
        self.load_view_calls = 0

    @property
    def state_store_version(self) -> str:
        return cast(str, self.store.state_store_version)

    def load_head_v2(self, scope_ref: str, stream_ref: str) -> GovernanceHeadV2:
        return self.store.load_head_v2(scope_ref, stream_ref)

    def load_state_v2(self, scope_ref: str, stream_ref: str):  # type: ignore[no-untyped-def]
        return self.store.load_state_v2(scope_ref, stream_ref)

    def load_commit_view_v2(
        self,
        scope_ref: str,
        stream_ref: str,
        transition_id: str,
        *,
        expected_receipt_root: str | None = None,
    ) -> GovernanceCommitViewV2:
        self.load_view_calls += 1
        if transition_id in self.hidden_transition_ids:
            raise KeyError(transition_id)
        if transition_id in self.finality_transition_ids:
            return GovernanceCommitViewV2(
                domain_root=self.domain_root,
                scope_ref=scope_ref,
                stream_ref=stream_ref,
                transition_id=transition_id,
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
        view = self.store.load_commit_view_v2(
            scope_ref,
            stream_ref,
            transition_id,
            expected_receipt_root=expected_receipt_root,
        )
        if self.view_mutator is not None:
            self.view_mutator(view)
        return view

    def atomic_commit_v2(self, batch: Any) -> GovernanceCommitAttemptV2:
        self.atomic_commits += 1
        return self.store.atomic_commit_v2(batch)


def _adversarial_context(scope_ref: str) -> tuple[_Context, _AdversarialReader]:
    wrapper: _AdversarialReader | None = None

    def wrap(store: GovernanceStateStoreV2, domain_root: str) -> GovernanceStateStoreV2:
        nonlocal wrapper
        wrapper = _AdversarialReader(store, domain_root)
        return cast(GovernanceStateStoreV2, wrapper)

    context = _context(scope_ref=scope_ref, store_wrapper=wrap)
    assert wrapper is not None
    return context, wrapper


@pytest.mark.parametrize(  # type: ignore[misc]
    "mutation",
    ("missing_inclusion", "forged_position", "read_set", "state_record"),
)
def test_malicious_state_reader_fails_closed_without_new_write(
    mutation: str,
) -> None:
    context, reader = _adversarial_context(f"scope:membership-v2:malicious:{mutation}")
    _, _, membership, state = _committed_pair(context, label=mutation)

    def mutate(view: GovernanceCommitViewV2) -> None:
        if view.transition_id != membership.transition_id:
            return
        assert view.committed_transition is not None
        committed = view.committed_transition
        if mutation == "missing_inclusion":
            object.__setattr__(committed, "inclusion_proof", None)
        elif mutation == "forged_position":
            assert view.position_observation is not None
            object.__setattr__(
                view.position_observation,
                "observed_head_root",
                _root("forged-observed-head"),
            )
        elif mutation == "read_set":
            entries = list(committed.batch.read_set.entries)
            entries[0] = replace(entries[0], expected_root=_root("forged-read-root"))
            object.__setattr__(
                committed.batch,
                "read_set",
                GovernanceAuthorityReadSetV2(entries=tuple(entries)),
            )
        else:
            assert committed.batch.transition is not None
            records = cast(
                dict[str, Any],
                dict(committed.batch.transition.state_records),
            )
            records["membership_root"] = _root("forged-membership-root")
            object.__setattr__(committed.batch.transition, "state_records", records)

    reader.view_mutator = mutate
    reader.atomic_commits = 0
    assert not membership_state_is_current_v2(state)
    with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
        require_current_membership_state_v2(state)
    assert caught.value.code is (
        AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
    )
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        rehydrate_membership_state_v2(
            membership.to_dict(), domain=context.domain, state_reader=reader
        )
    assert reader.atomic_commits == 0


def test_missing_historical_parent_or_verification_proof_fails_rehydrate() -> None:
    context, reader = _adversarial_context("scope:membership-v2:missing-history")
    verification1, _, membership1, _ = _committed_pair(context)
    verification2, source2 = _prepare_verification(
        context,
        epoch=2,
        label="history-child",
        parent=verification1.snapshot,
    )
    assert _advance_verification(context, verification2, source2)[0].disposition is (
        GovernanceCommitDispositionV2.COMMITTED
    )
    membership2, membership_source2 = _prepare_membership(
        context,
        _verification_state(context, verification2),
        epoch=2,
        label="history-child",
        parent=membership1.snapshot,
    )
    assert (
        _commit_membership(context, membership2, membership_source2)[0].disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )

    for hidden in (membership1.transition_id, verification1.transition_id):
        reader.hidden_transition_ids = {hidden}
        with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
            rehydrate_membership_state_v2(
                membership2.to_dict(), domain=context.domain, state_reader=reader
            )
        assert caught.value.code is (
            AuthorityDiagnosticCodeV2.GOVERNANCE_COMMITTED_TRANSITION_INVALID
        )
    reader.hidden_transition_ids.clear()


def test_finality_and_sealed_domain_fail_closed_but_exact_retries_survive() -> None:
    context, reader = _adversarial_context("scope:membership-v2:finality")
    verification, _, membership, _ = _committed_pair(context)
    reader.finality_transition_ids = {
        verification.transition_id,
        membership.transition_id,
    }
    for payload, rehydrate in (
        (verification.to_dict(), rehydrate_principal_verification_set_state_v2),
        (membership.to_dict(), rehydrate_membership_state_v2),
    ):
        with pytest.raises(GovernanceAuthorityBindingErrorV2) as caught:
            rehydrate(
                payload,
                domain=context.domain,
                state_reader=reader,
            )
        assert caught.value.code is (
            AuthorityDiagnosticCodeV2.GOVERNANCE_FINALITY_UNAVAILABLE
        )

    sealed = _context(
        scope_ref="scope:membership-v2:sealed",
        operations=(
            GovernanceIssuerOperationV2.EVALUATE_QUORUM,
            GovernanceIssuerOperationV2.QUALIFY_EVIDENCE,
            GovernanceIssuerOperationV2.RETIRE_DOMAIN,
        ),
    )
    verification, verification_state, membership, _ = _committed_pair(sealed)
    verification_retry_session = open_principal_verification_authority_session_v2(
        _capability(sealed, sealed.grant, verification.observed_epoch), verification
    )
    membership_retry_session = open_membership_authority_session_v2(
        _capability(sealed, sealed.grant, membership.observed_epoch), membership
    )
    child, child_source = _prepare_verification(
        sealed,
        epoch=2,
        label="post-seal",
        parent=verification.snapshot,
    )
    post_membership, post_membership_source = _prepare_membership(
        sealed,
        verification_state,
        epoch=1,
        label="post-seal",
    )
    child_session = open_principal_verification_authority_session_v2(
        _capability(sealed, sealed.grant, child.observed_epoch), child
    )
    membership_session = open_membership_authority_session_v2(
        _capability(sealed, sealed.grant, post_membership.observed_epoch),
        post_membership,
    )
    grant_stream = governance_issuer_grant_stream_ref_v2(
        sealed.domain.scope_ref, sealed.grant.grant_ref
    )
    retirement = GovernanceDomainRetirementRequestV2(
        domain_root=sealed.domain.domain_root,
        scope_ref=sealed.domain.scope_ref,
        run_ref=RUN_REF,
        request_ref="request:membership-v2:retire",
        transition_id="transition:membership-v2:retire",
        stream_refs=tuple(
            sorted((grant_stream, verification.stream_ref, membership.stream_ref))
        ),
        reason_ref="reason:test-complete",
        observed_epoch=101,
    )
    retirement_session = open_governance_authority_session_v2(
        _capability(sealed, sealed.grant, retirement.observed_epoch), retirement
    )
    assert (
        retire_governance_domain_v2(
            retirement, authority_session=retirement_session
        ).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    assert (
        advance_principal_verification_set_v2(
            verification,
            source=None,
            authority_session=verification_retry_session,
        ).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    assert (
        commit_membership_epoch_v2(
            membership,
            source=None,
            authority_session=membership_retry_session,
        ).disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    for rejected in (
        advance_principal_verification_set_v2(
            child, source=child_source, authority_session=child_session
        ),
        commit_membership_epoch_v2(
            post_membership,
            source=post_membership_source,
            authority_session=membership_session,
        ),
    ):
        assert rejected.disposition is GovernanceCommitDispositionV2.DENIED
        assert rejected.failure is not None
        assert rejected.failure.code is (
            AuthorityDiagnosticCodeV2.GOVERNANCE_DOMAIN_SEALED
        )


def test_32_identical_and_conflicting_workers_have_one_linearized_state() -> None:
    identical = _context(scope_ref="scope:membership-v2:race-identical")
    verification, source = _prepare_verification(
        identical, epoch=1, label="race-identical"
    )
    session = open_principal_verification_authority_session_v2(
        _capability(identical, identical.grant, verification.observed_epoch),
        verification,
    )
    with ThreadPoolExecutor(max_workers=32) as executor:
        results = tuple(
            executor.map(
                lambda _: advance_principal_verification_set_v2(
                    verification, source=source, authority_session=session
                ),
                range(32),
            )
        )
    assert all(
        result.disposition is GovernanceCommitDispositionV2.COMMITTED
        for result in results
    )
    receipts = {
        result.committed_transition.receipt.receipt_root
        for result in results
        if result.committed_transition is not None
    }
    assert len(receipts) == 1
    assert (
        identical.store.load_head_v2(
            identical.domain.scope_ref, verification.stream_ref
        ).revision
        == 1
    )

    conflicting = _context(scope_ref="scope:membership-v2:race-conflicting")
    verification, verification_source = _prepare_verification(
        conflicting, epoch=1, label="race-dependency"
    )
    assert (
        _advance_verification(conflicting, verification, verification_source)[
            0
        ].disposition
        is GovernanceCommitDispositionV2.COMMITTED
    )
    verification_state = _verification_state(conflicting, verification)
    candidates = tuple(
        _prepare_membership(
            conflicting,
            verification_state,
            epoch=1,
            label=f"race:{index}",
        )
        for index in range(32)
    )
    sessions = tuple(
        open_membership_authority_session_v2(
            _capability(conflicting, conflicting.grant, request.observed_epoch),
            request,
        )
        for request, _ in candidates
    )
    with ThreadPoolExecutor(max_workers=32) as executor:
        outcomes = tuple(
            executor.map(
                lambda item: commit_membership_epoch_v2(
                    item[0][0],
                    source=item[0][1],
                    authority_session=item[1],
                ),
                zip(candidates, sessions, strict=True),
            )
        )
    assert (
        sum(
            outcome.disposition is GovernanceCommitDispositionV2.COMMITTED
            for outcome in outcomes
        )
        == 1
    )
    assert all(
        outcome.disposition
        in (
            GovernanceCommitDispositionV2.COMMITTED,
            GovernanceCommitDispositionV2.RETRY_REQUIRED,
        )
        for outcome in outcomes
    )


def test_noncanonical_rehydrate_and_resource_exhaustion_do_no_store_io() -> None:
    context, reader = _adversarial_context("scope:membership-v2:wire-resources")
    verification, _, membership, _ = _committed_pair(context)
    reader.load_view_calls = 0
    reader.atomic_commits = 0

    missing_verification_root = verification.to_dict()
    missing_verification_root["request_root"] = ""
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        rehydrate_principal_verification_set_state_v2(
            missing_verification_root,
            domain=context.domain,
            state_reader=reader,
        )
    missing_membership_root = membership.to_dict()
    membership_snapshot = cast(dict[str, Any], missing_membership_root["snapshot"])
    membership_snapshot["membership_root"] = ""
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        rehydrate_membership_state_v2(
            missing_membership_root,
            domain=context.domain,
            state_reader=reader,
        )

    too_many_records = verification.to_dict()
    verification_snapshot = cast(dict[str, Any], too_many_records["snapshot"])
    records = cast(list[object], verification_snapshot["records"])
    record = records[0]
    verification_snapshot["records"] = [record] * (MAX_PRINCIPAL_VERIFICATIONS_V2 + 1)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        rehydrate_principal_verification_set_state_v2(
            too_many_records, domain=context.domain, state_reader=reader
        )
    too_many_clusters = membership.to_dict()
    membership_snapshot = cast(dict[str, Any], too_many_clusters["snapshot"])
    clusters = cast(list[object], membership_snapshot["clusters"])
    cluster = clusters[0]
    membership_snapshot["clusters"] = [cluster] * (MAX_MEMBERSHIP_CLUSTERS_V2 + 1)
    with pytest.raises(GovernanceAuthorityBindingErrorV2):
        rehydrate_membership_state_v2(
            too_many_clusters, domain=context.domain, state_reader=reader
        )
    assert reader.load_view_calls == 0
    assert reader.atomic_commits == 0

    exact_depth: object = None
    for _ in range(MAX_SUPPORT_RESOURCE_DEPTH_V2):
        exact_depth = [exact_depth]
    _preflight_support_resources_v2(exact_depth)
    with pytest.raises(ValueError, match="depth bound"):
        _preflight_support_resources_v2([exact_depth])
    _preflight_support_resources_v2([None] * (MAX_SUPPORT_RESOURCE_NODES_V2 - 1))
    with pytest.raises(ValueError, match="node bound"):
        _preflight_support_resources_v2([None] * MAX_SUPPORT_RESOURCE_NODES_V2)
    _preflight_support_resources_v2("x" * MAX_SUPPORT_RESOURCE_TEXT_BYTES_V2)
    with pytest.raises(ValueError, match="aggregate text"):
        _preflight_support_resources_v2("x" * (MAX_SUPPORT_RESOURCE_TEXT_BYTES_V2 + 1))
