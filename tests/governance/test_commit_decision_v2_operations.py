from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace

import pytest

from tests.governance._commit_certificate_v2_race_support import (
    DependencyRaceStoreV2,
)
from tests.governance import test_commit_evidence_v2_operations as evidence_fixture
from tests.governance import test_commit_gate_v2_operations as gate_fixture
from tests.governance import test_support_v2_operations as support_fixture

from pheroos.governance._commit_decision_v2.enums import (
    CommitDecisionCommandV2,
    CommitDecisionDependencyRoleV2,
)
from pheroos.governance._commit_decision_v2.dependencies import (
    commit_decision_frozen_dependency_root_v2,
)
from pheroos.governance._commit_decision_v2.liveness_records import (
    CommitDecisionWindowV2,
)
from pheroos.governance._commit_decision_v2.operations import (
    advance_commit_decision_v2,
    open_commit_decision_authority_session_v2,
)
from pheroos.governance._commit_decision_v2.proposals import (
    CommitDecisionCandidateProposalV2,
    CommitDecisionOutputProposalV2,
)
from pheroos.governance._commit_decision_v2.reducer import (
    _advance_window,
    _window_semantics_continuous,
)
from pheroos.governance._commit_decision_v2.source import (
    prepare_commit_decision_initialize_v2,
    prepare_commit_decision_missing_inputs_v2,
    prepare_commit_decision_successor_v2,
)
from pheroos.governance._commit_decision_v2.source_proof import (
    VerifiedCommitDecisionSourceV2,
)
from pheroos.governance._commit_decision_v2.state_handle import (
    rehydrate_commit_decision_state_v2,
)
from pheroos.governance.authority_session_v2 import (
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    revoke_governance_issuer_grant_v2,
)
from pheroos.governance.authority_store_v2 import GovernanceCommitDispositionV2
from pheroos.governance.commit_evidence_v2 import (
    advance_commit_evidence_state_v2,
    open_commit_evidence_authority_session_v2,
    rehydrate_commit_evidence_state_v2,
)
from pheroos.governance.commit_gate_v2 import (
    issue_commit_permission_v2,
    open_commit_permission_authority_session_v2,
    open_commit_stop_authority_session_v2,
    prepare_commit_permission_issue_v2,
    prepare_commit_stop_resolution_v2,
    rehydrate_commit_permission_state_v2,
    rehydrate_commit_stop_state_v2,
    resolve_commit_stop_v2,
)
from pheroos.governance.risk_v2 import (
    RiskBand,
    advance_risk_state_v2,
    open_risk_authority_session_v2,
    prepare_risk_state_advance_v2,
    rehydrate_risk_state_v2,
)
from pheroos.governance.support_v2 import (
    advance_principal_verification_set_v2,
    advance_support_state_v2,
    open_principal_verification_authority_session_v2,
    open_support_authority_session_v2,
)
from pheroos.protocol.authority_v2 import (
    MAX_AUTHORITY_REVISION_V2,
    AuthorityDiagnosticCodeV2,
)

PROFILE = support_fixture.PROFILE
RUN_REF = support_fixture.RUN_REF
TARGET = support_fixture.TARGET


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _decision_context(
    scope: str,
    *,
    stability_steps: int = 2,
    deliberation_deadline_steps: int | None = None,
):
    context = support_fixture._context(scope_ref=scope)
    grant = gate_fixture._grant(context.domain)
    attempt = activate_governance_issuer_grant_v2(
        context.store,
        context.domain,
        grant,
        f"transition:{scope}:decision-grant",
        1,
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    policy = context.manifest.collective_commit_policy
    assert policy is not None
    low = replace(
        policy.risk_bands["LOW"],
        minimum_positive_evidence=1,
        minimum_support_clusters=1,
        minimum_support_ratio_ppm=1,
        minimum_source_diversity=1,
        minimum_margin=1,
        stability_steps=stability_steps,
    )
    evidence_policy = replace(
        policy.evidence_qualification,
        minimum_positive_evidence=1,
        minimum_source_diversity=1,
    )
    support_policy = replace(
        policy.support_lease,
        minimum_support_clusters=1,
        support_ratio_ppm=1,
    )
    policy = replace(
        policy,
        evidence_qualification=evidence_policy,
        support_lease=support_policy,
        risk_bands={**policy.risk_bands, "LOW": low},
        commit_window=replace(
            policy.commit_window,
            minimum_stability_steps=stability_steps,
            deliberation_deadline_steps=(
                policy.commit_window.deliberation_deadline_steps
                if deliberation_deadline_steps is None
                else deliberation_deadline_steps
            ),
        ),
    )
    manifest = replace(context.manifest, collective_commit_policy=policy)
    return replace(context, grant=grant, manifest=manifest)


def _capability(context, epoch: int):
    return bind_governance_issuer_capability_v2(
        context.store,
        context.domain,
        context.grant,
        RUN_REF,
        epoch,
    )


def _commit_decision(context, request, source):
    session = open_commit_decision_authority_session_v2(
        _capability(context, request.observed_epoch),
        request,
    )
    attempt = advance_commit_decision_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED, (
        None if attempt.failure is None else attempt.failure.to_dict()
    )
    return rehydrate_commit_decision_state_v2(
        request,
        domain=context.domain,
        state_reader=context.store,
    )


def test_initialization_to_zero_upstream_deadline_commits_safe_fallback() -> None:
    context = _decision_context("scope:decision-v2:missing-inputs")
    initialize, source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:decision:initialize",
        current_step=4,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    state = _commit_decision(context, initialize, source)
    deadline, deadline_source = prepare_commit_decision_missing_inputs_v2(
        parent_state=state,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:decision:deadline",
        current_step=state.snapshot.evidence_deadline_step,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    terminal = _commit_decision(context, deadline, deadline_source).snapshot
    assert terminal.outcome is not None
    assert terminal.outcome.kind.value == "safe_fallback"
    assert terminal.outcome.delivery_eligible
    assert terminal.progress is None


def test_exact_retry_survives_revocation_and_stale_parent_is_retryable() -> None:
    context = _decision_context("scope:decision-v2:retry-parent-race")
    initialize, source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:decision:retry:initialize",
        current_step=4,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    session = open_commit_decision_authority_session_v2(
        _capability(context, 1), initialize
    )
    first = advance_commit_decision_v2(
        initialize,
        source=source,
        authority_session=session,
    )
    assert first.disposition is GovernanceCommitDispositionV2.COMMITTED
    revoked = revoke_governance_issuer_grant_v2(
        context.store,
        context.domain,
        context.grant.grant_ref,
        "transition:decision:retry:revoke",
        2,
    )
    assert revoked.disposition is GovernanceCommitDispositionV2.COMMITTED
    retry = advance_commit_decision_v2(
        initialize,
        source=source,
        authority_session=session,
    )
    assert retry.to_dict() == first.to_dict()

    race_context = _decision_context("scope:decision-v2:parent-race")
    initial_request, initial_source = prepare_commit_decision_initialize_v2(
        domain=race_context.domain,
        manifest=race_context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:decision:parent-race:initialize",
        current_step=4,
        mutation_issuer_ref=race_context.grant.issuer_ref,
    )
    parent = _commit_decision(race_context, initial_request, initial_source)
    first_child, first_child_source = prepare_commit_decision_missing_inputs_v2(
        parent_state=parent,
        manifest=race_context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:decision:parent-race:first",
        current_step=5,
        mutation_issuer_ref=race_context.grant.issuer_ref,
    )
    stale_child, stale_child_source = prepare_commit_decision_missing_inputs_v2(
        parent_state=parent,
        manifest=race_context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:decision:parent-race:stale",
        current_step=5,
        mutation_issuer_ref=race_context.grant.issuer_ref,
    )
    _commit_decision(race_context, first_child, first_child_source)
    stale = advance_commit_decision_v2(
        stale_child,
        source=stale_child_source,
        authority_session=open_commit_decision_authority_session_v2(
            _capability(race_context, stale_child.observed_epoch), stale_child
        ),
    )
    assert stale.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert stale.failure is not None
    assert stale.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    assert stale.failure.path == "/parent"


def test_same_shape_source_forged_token_and_copied_payload_have_no_authority() -> None:
    context = _decision_context("scope:decision-v2:source-forgery")
    request, source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:decision:source-forgery:initialize",
        current_step=4,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    session = open_commit_decision_authority_session_v2(
        _capability(context, request.observed_epoch), request
    )
    copied_payload = {
        name: object.__getattribute__(source, name)
        for name in VerifiedCommitDecisionSourceV2.__slots__
        if name != "_token"
    }
    forged_exact = object.__new__(VerifiedCommitDecisionSourceV2)
    object.__setattr__(forged_exact, "_token", object())
    for name, value in copied_payload.items():
        object.__setattr__(forged_exact, name, value)
    for forged in (SimpleNamespace(**copied_payload), forged_exact):
        rejected = advance_commit_decision_v2(
            request,
            source=forged,
            authority_session=session,
        )
        assert rejected.disposition is GovernanceCommitDispositionV2.INVALID
        assert rejected.failure is not None
        assert (
            rejected.failure.code
            is AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
        )
    assert (
        context.store.load_head_v2(request.scope_ref, request.stream_ref).revision == 0
    )
    committed = advance_commit_decision_v2(
        request,
        source=source,
        authority_session=session,
    )
    assert committed.disposition is GovernanceCommitDispositionV2.COMMITTED


def test_partial_missing_inputs_bind_committed_and_genesis_heads_atomically() -> None:
    context = _decision_context("scope:decision-v2:partial-inputs")
    initialize, initialize_source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:decision:partial:initialize",
        current_step=4,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    state = _commit_decision(context, initialize, initialize_source)
    support_fixture._commit_upstreams(context, label="decision-partial")
    partial, partial_source = prepare_commit_decision_missing_inputs_v2(
        parent_state=state,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:decision:partial:heartbeat",
        current_step=5,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    snapshot = _commit_decision(context, partial, partial_source).snapshot
    revisions = {item.role: item.revision for item in snapshot.dependencies}
    assert revisions[CommitDecisionDependencyRoleV2.MEMBERSHIP] == 1
    assert revisions[CommitDecisionDependencyRoleV2.PRINCIPAL_VERIFICATION] == 1
    for role in {
        CommitDecisionDependencyRoleV2.REPLAY,
        CommitDecisionDependencyRoleV2.RISK,
        CommitDecisionDependencyRoleV2.SUPPORT,
        CommitDecisionDependencyRoleV2.EVIDENCE,
        CommitDecisionDependencyRoleV2.STOP,
        CommitDecisionDependencyRoleV2.PERMISSION,
    }:
        assert revisions[role] == 0
    assert snapshot.progress is not None
    assert set(snapshot.progress.next_required_inputs) == {
        "replay",
        "risk",
        "support",
        "evidence",
        "stop",
        "permission",
    }
    deadline, deadline_source = prepare_commit_decision_missing_inputs_v2(
        parent_state=rehydrate_commit_decision_state_v2(
            partial,
            domain=context.domain,
            state_reader=context.store,
        ),
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:decision:partial:deadline",
        current_step=snapshot.evidence_deadline_step,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    terminal = _commit_decision(context, deadline, deadline_source).snapshot
    assert terminal.outcome is not None
    assert terminal.outcome.kind.value == "safe_fallback"
    assert terminal.outcome.frozen_dependency_root == (
        commit_decision_frozen_dependency_root_v2(terminal.dependencies)
    )


@pytest.mark.parametrize(
    ("omitted_gate", "missing_role"),
    (
        ("stop", CommitDecisionDependencyRoleV2.STOP),
        ("permission", CommitDecisionDependencyRoleV2.PERMISSION),
    ),
)
def test_single_missing_gate_rehydrates_every_other_committed_owner(
    omitted_gate: str,
    missing_role: CommitDecisionDependencyRoleV2,
) -> None:
    context = _decision_context(f"scope:decision-v2:partial-{omitted_gate}")
    _fresh_inputs(
        context,
        _root(f"claim:decision:partial-{omitted_gate}"),
        omit_gate=omitted_gate,
    )
    initialize, initialize_source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref=f"mutation:decision:partial-{omitted_gate}:initialize",
        current_step=6,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    state = _commit_decision(context, initialize, initialize_source)
    partial, partial_source = prepare_commit_decision_missing_inputs_v2(
        parent_state=state,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref=f"mutation:decision:partial-{omitted_gate}:heartbeat",
        current_step=7,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    snapshot = _commit_decision(context, partial, partial_source).snapshot
    revisions = {
        item.role: item.revision
        for item in snapshot.dependencies
        if item.role is not CommitDecisionDependencyRoleV2.PARENT
    }
    assert revisions[missing_role] == 0
    assert all(
        revision > 0 for role, revision in revisions.items() if role is not missing_role
    )
    assert snapshot.progress is not None
    assert snapshot.progress.next_required_inputs == (missing_role.value,)


def test_public_initialization_saturates_deadlines_before_state_construction() -> None:
    context = _decision_context("scope:decision-v2:saturating-deadlines")
    policy = context.manifest.collective_commit_policy
    assert policy is not None
    maximum = MAX_AUTHORITY_REVISION_V2
    window = replace(
        policy.commit_window,
        deliberation_deadline_steps=maximum,
        run_deadline_steps=maximum,
    )
    manifest = replace(
        context.manifest,
        collective_commit_policy=replace(policy, commit_window=window),
    )
    request, source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:decision:saturating:initialize",
        current_step=maximum - 1,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    snapshot = _commit_decision(
        replace(context, manifest=manifest), request, source
    ).snapshot
    assert snapshot.evidence_deadline_step == maximum
    assert snapshot.finality_deadline_step == maximum

    with pytest.raises(ValueError, match="no representable future step"):
        prepare_commit_decision_initialize_v2(
            domain=context.domain,
            manifest=manifest,
            profile=PROFILE,
            run_ref=RUN_REF,
            target_ref=TARGET,
            observed_epoch=1,
            mutation_ref="mutation:decision:saturating:terminal-step",
            current_step=maximum,
            mutation_issuer_ref=context.grant.issuer_ref,
        )
    bool_window = replace(
        policy.commit_window,
        deliberation_deadline_steps=True,
    )
    bool_manifest = replace(
        context.manifest,
        collective_commit_policy=replace(policy, commit_window=bool_window),
    )
    with pytest.raises(ValueError, match="integer"):
        prepare_commit_decision_initialize_v2(
            domain=context.domain,
            manifest=bool_manifest,
            profile=PROFILE,
            run_ref=RUN_REF,
            target_ref=TARGET,
            observed_epoch=1,
            mutation_ref="mutation:decision:saturating:bool",
            current_step=1,
            mutation_issuer_ref=context.grant.issuer_ref,
        )


def _fresh_inputs(
    context,
    claim_root: str,
    *,
    gate_expires_at_step: int = 30,
    omit_gate: str = "",
):
    if omit_gate not in {"", "stop", "permission"}:
        raise ValueError("unsupported omitted gate")
    upstreams = support_fixture._commit_upstreams(context)
    attestations = evidence_fixture._attestations(claim_root=claim_root)
    _, replay_state = evidence_fixture._commit_replay(context, attestations)
    evidence_request, evidence_source = evidence_fixture._prepare_evidence(
        context,
        upstreams,
        replay_state,
        attestations,
        advance="advance:evidence:decision",
    )
    evidence_session = open_commit_evidence_authority_session_v2(
        _capability(context, evidence_request.observed_epoch),
        evidence_request,
    )
    evidence_attempt = advance_commit_evidence_state_v2(
        evidence_request,
        source=evidence_source,
        authority_session=evidence_session,
    )
    assert evidence_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    evidence_state = rehydrate_commit_evidence_state_v2(
        evidence_request,
        domain=context.domain,
        state_reader=context.store,
    )
    support_request, support_source = support_fixture._initialize_request(
        context,
        label="decision",
        current_step=3,
    )
    support_session = open_support_authority_session_v2(
        _capability(context, support_request.observed_epoch),
        support_request,
    )
    support_attempt = advance_support_state_v2(
        support_request,
        source=support_source,
        authority_session=support_session,
    )
    assert support_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    support_state = support_fixture._support_state(context, support_request)
    issue, issue_source = support_fixture._prepare_issue(
        context,
        support_state,
        upstreams.membership_state,
        label="decision",
        current_step=4,
        candidate_ref="candidate:accept",
        claim_root=claim_root,
    )
    issue_session = open_support_authority_session_v2(
        _capability(context, issue.observed_epoch),
        issue,
    )
    issue_attempt = advance_support_state_v2(
        issue,
        source=issue_source,
        authority_session=issue_session,
    )
    assert issue_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    support_state = support_fixture._support_state(context, issue)
    risk_request, risk_source = prepare_risk_state_advance_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        epoch=1,
        advance_ref="advance:risk:decision",
        current_step=4,
        assessment_ref="assessment:risk:decision",
        risk_band=RiskBand.LOW,
        risk_input_roots=(_root("risk-input:decision"),),
        rationale_codes=("risk:low",),
        assessment_method="deterministic-test-v2",
        issuer_ref=context.grant.issuer_ref,
        issued_at_step=4,
        expires_at_step=100,
        provenance_ref="urn:test:risk:decision",
        source_trace_roots=(_root("risk-trace:decision"),),
    )
    risk_session = open_risk_authority_session_v2(
        _capability(context, 1),
        risk_request,
    )
    risk_attempt = advance_risk_state_v2(
        risk_request,
        source=risk_source,
        authority_session=risk_session,
    )
    assert risk_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    risk_state = rehydrate_risk_state_v2(
        risk_request,
        domain=context.domain,
        state_reader=context.store,
    )
    stop_state = None
    if omit_gate != "stop":
        stop, stop_source = prepare_commit_stop_resolution_v2(
            domain_root=context.domain.domain_root,
            scope_ref=context.domain.scope_ref,
            manifest=context.manifest,
            profile=PROFILE,
            run_ref=RUN_REF,
            target_ref=TARGET,
            observed_epoch=50,
            resolution_ref="resolution:decision",
            current_step=6,
            mutation_issuer_ref=context.grant.issuer_ref,
            blocked=False,
            reason_codes=("stop:clear",),
            issued_at_step=6,
            expires_at_step=gate_expires_at_step,
            commit_replay_state=replay_state,
            risk_state=risk_state,
            membership_state=upstreams.membership_state,
            support_state=support_state,
            parent_snapshot=None,
        )
        stop_session = open_commit_stop_authority_session_v2(
            _capability(context, 50), stop
        )
        assert (
            resolve_commit_stop_v2(
                stop, source=stop_source, authority_session=stop_session
            ).disposition
            is GovernanceCommitDispositionV2.COMMITTED
        )
        stop_state = rehydrate_commit_stop_state_v2(
            stop,
            domain=context.domain,
            state_reader=context.store,
        )
    permission_state = None
    if omit_gate != "permission":
        permission, permission_source = prepare_commit_permission_issue_v2(
            domain_root=context.domain.domain_root,
            scope_ref=context.domain.scope_ref,
            manifest=context.manifest,
            profile=PROFILE,
            run_ref=RUN_REF,
            target_ref=TARGET,
            observed_epoch=50,
            permission_ref="permission:decision",
            current_step=6,
            mutation_issuer_ref=context.grant.issuer_ref,
            allowed=True,
            claim_roots=(claim_root,),
            issued_at_step=6,
            expires_at_step=gate_expires_at_step,
            commit_replay_state=replay_state,
            risk_state=risk_state,
            membership_state=upstreams.membership_state,
            support_state=support_state,
            parent_snapshot=None,
        )
        permission_session = open_commit_permission_authority_session_v2(
            _capability(context, 50), permission
        )
        assert (
            issue_commit_permission_v2(
                permission,
                source=permission_source,
                authority_session=permission_session,
            ).disposition
            is GovernanceCommitDispositionV2.COMMITTED
        )
        permission_state = rehydrate_commit_permission_state_v2(
            permission,
            domain=context.domain,
            state_reader=context.store,
        )
    return (
        replay_state,
        risk_state,
        upstreams.membership_state,
        support_state,
        evidence_state,
        stop_state,
        permission_state,
        upstreams.verification_state,
    )


def test_epoch_restart_is_exact_next_on_the_public_store_path() -> None:
    context = _decision_context("scope:decision-v2:epoch-restart")
    claim_root = _root("claim:decision:epoch-restart")
    inputs = _fresh_inputs(context, claim_root)
    initialize, initialize_source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:decision:epoch-restart:initialize",
        current_step=6,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    state = _commit_decision(context, initialize, initialize_source)
    successor_arguments = dict(
        parent_state=state,
        manifest=context.manifest,
        profile=PROFILE,
        current_step=7,
        mutation_issuer_ref=context.grant.issuer_ref,
        command=CommitDecisionCommandV2.EPOCH_RESTART,
        commit_replay_state=inputs[0],
        risk_state=inputs[1],
        membership_state=inputs[2],
        support_state=inputs[3],
        evidence_state=inputs[4],
        stop_state=inputs[5],
        permission_state=inputs[6],
    )
    for label, invalid_epoch in (
        ("rollback", 1),
        ("zero", 0),
        ("skip", 3),
        ("bool", True),
    ):
        with pytest.raises(ValueError):
            prepare_commit_decision_successor_v2(
                **successor_arguments,
                mutation_ref=f"mutation:decision:epoch-restart:{label}",
                restart_epoch=invalid_epoch,
            )
    restart, restart_source = prepare_commit_decision_successor_v2(
        **successor_arguments,
        mutation_ref="mutation:decision:epoch-restart:next",
        restart_epoch=2,
    )
    restarted = _commit_decision(context, restart, restart_source).snapshot
    assert restarted.epoch == 2
    assert restarted.mutation_kind.value == "epoch_restarted"
    assert (
        restarted.window.remaining_epoch_restart_budget
        == state.snapshot.window.remaining_epoch_restart_budget - 1
    )


def test_principal_verification_cas_race_is_retry_required() -> None:
    context = _decision_context("scope:decision-v2:verification-race")
    claim_root = _root("claim:decision:verification-race")
    inputs = _fresh_inputs(context, claim_root)
    initialize, initialize_source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:decision:verification-race:initialize",
        current_step=6,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    state = _commit_decision(context, initialize, initialize_source)
    proposal = CommitDecisionCandidateProposalV2(
        candidate_ref="candidate:accept",
        claim_root=claim_root,
        evidence=(),
    )
    request, source = prepare_commit_decision_successor_v2(
        parent_state=state,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:decision:verification-race:evaluate",
        current_step=7,
        mutation_issuer_ref=context.grant.issuer_ref,
        command=CommitDecisionCommandV2.EVALUATE,
        candidate_proposals=(proposal,),
        commit_replay_state=inputs[0],
        risk_state=inputs[1],
        membership_state=inputs[2],
        support_state=inputs[3],
        evidence_state=inputs[4],
        stop_state=inputs[5],
        permission_state=inputs[6],
    )
    race_store = DependencyRaceStoreV2(context.store)
    raced_context = replace(context, store=race_store)
    verification, verification_source = support_fixture._prepare_verification(
        context,
        epoch=2,
        label="decision-verification-race",
        issuer_ref=context.grant.issuer_ref,
        parent=inputs[7].snapshot,
    )

    def advance_verification() -> None:
        attempt = advance_principal_verification_set_v2(
            verification,
            source=verification_source,
            authority_session=open_principal_verification_authority_session_v2(
                _capability(context, verification.observed_epoch), verification
            ),
        )
        assert attempt.disposition is GovernanceCommitDispositionV2.COMMITTED

    race_store.armed_stream_ref = request.stream_ref
    race_store.before_atomic = advance_verification
    raced = advance_commit_decision_v2(
        request,
        source=source,
        authority_session=open_commit_decision_authority_session_v2(
            _capability(raced_context, request.observed_epoch), request
        ),
    )
    assert raced.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert raced.failure is not None
    assert raced.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    assert (
        context.store.load_head_v2(request.scope_ref, request.stream_ref).revision == 1
    )


def test_finality_owner_absence_is_cas_bound_at_deadline() -> None:
    from tests.governance._commit_certificate_v2_decision_support import (
        sealed_certified_decision,
    )
    from tests.governance._commit_certificate_v2_store_support import (
        PROFILE as CERTIFIED_PROFILE,
        _root as certificate_root,
        certified_context,
    )
    from tests.governance.test_commit_certificate_v2_operations import (
        _commit_certificate,
        _prepared_certificate,
    )

    def context_for(scope_ref: str):
        base = certified_context(scope_ref)
        policy = base.manifest.collective_commit_policy
        assert policy is not None
        manifest = replace(
            base.manifest,
            collective_commit_policy=replace(
                policy,
                risk_bands={
                    name: replace(band, stability_steps=min(band.stability_steps, 3))
                    for name, band in policy.risk_bands.items()
                },
                commit_window=replace(
                    policy.commit_window,
                    deliberation_deadline_steps=3,
                    run_deadline_steps=4,
                ),
            ),
        )
        return replace(base, manifest=manifest)

    def prepare_deadline(context, state, inputs, label: str):
        seal = state.snapshot.seal
        assert seal is not None
        proposal = CommitDecisionCandidateProposalV2(
            candidate_ref=seal.candidate_ref,
            claim_root=seal.claim_root,
            evidence=(),
        )
        return prepare_commit_decision_successor_v2(
            parent_state=state,
            manifest=context.manifest,
            profile=CERTIFIED_PROFILE,
            mutation_ref=f"mutation:decision:finality-absence:{label}",
            current_step=state.snapshot.current_step + 1,
            mutation_issuer_ref=context.grant.issuer_ref,
            command=CommitDecisionCommandV2.EVALUATE,
            candidate_proposals=(proposal,),
            commit_replay_state=inputs.replay,
            risk_state=inputs.risk,
            membership_state=inputs.membership,
            support_state=inputs.support,
            evidence_state=inputs.evidence,
            stop_state=inputs.stop,
            permission_state=inputs.permission,
        )

    no_race = context_for("scope:decision-v2:finality-absence")
    no_race_state, no_race_inputs = sealed_certified_decision(
        no_race,
        certificate_root("claim:decision:finality-absence"),
    )
    assert no_race_state.snapshot.current_step + 1 == (
        no_race_state.snapshot.finality_deadline_step
    )
    deadline, deadline_source = prepare_deadline(
        no_race, no_race_state, no_race_inputs, "no-race"
    )
    terminal = _commit_decision(no_race, deadline, deadline_source).snapshot
    assert terminal.outcome is not None
    assert terminal.outcome.kind.value == "finality_unavailable"
    finality_dependency = next(
        item
        for item in terminal.dependencies
        if item.role is CommitDecisionDependencyRoleV2.CERTIFICATE
    )
    assert finality_dependency.revision == 0

    raced_context = context_for("scope:decision-v2:finality-race")
    raced_state, raced_inputs = sealed_certified_decision(
        raced_context,
        certificate_root("claim:decision:finality-race"),
    )
    raced_deadline, raced_source = prepare_deadline(
        raced_context, raced_state, raced_inputs, "race"
    )
    certificate, certificate_source = _prepared_certificate(
        raced_context,
        raced_state,
        mutation_ref="mutation:decision:finality-race:certificate",
    )
    certificate_attempt, _ = _commit_certificate(
        raced_context, certificate, certificate_source
    )
    assert certificate_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    raced = advance_commit_decision_v2(
        raced_deadline,
        source=raced_source,
        authority_session=open_commit_decision_authority_session_v2(
            _capability(raced_context, raced_deadline.observed_epoch),
            raced_deadline,
        ),
    )
    assert raced.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert raced.failure is not None
    assert raced.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    observed, observed_source = prepare_deadline(
        raced_context, raced_state, raced_inputs, "omitted-handle"
    )
    observed_terminal = _commit_decision(
        raced_context, observed, observed_source
    ).snapshot
    assert observed_terminal.outcome is not None
    assert observed_terminal.outcome.kind.value == "finality_unavailable"
    assert observed_terminal.outcome.reason_codes == (
        "finality:verified_owner_handle_missing_at_deadline",
    )
    observed_dependency = next(
        item
        for item in observed_terminal.dependencies
        if item.role is CommitDecisionDependencyRoleV2.CERTIFICATE
    )
    assert observed_dependency.revision == 1
    assert observed_dependency.transition_id == certificate.transition_id
    assert (
        observed_dependency.snapshot_root
        == (
            certificate_attempt.committed_transition.batch.transition.state_records[
                "snapshot_root"
            ]
        )
    )


def test_non_genesis_finality_owner_can_be_observed_without_being_consumed() -> None:
    from tests.governance._commit_certificate_v2_decision_support import (
        heartbeat_certified_decision,
        sealed_certified_decision,
    )
    from tests.governance._commit_certificate_v2_store_support import (
        _root as certificate_root,
        certified_context,
    )
    from tests.governance.test_commit_certificate_v2_operations import (
        _commit_certificate,
        _prepared_certificate,
    )

    context = certified_context("scope:decision-v2:observed-finality-owner")
    decision, inputs = sealed_certified_decision(
        context,
        certificate_root("claim:decision:observed-finality-owner"),
    )
    certificate, certificate_source = _prepared_certificate(
        context,
        decision,
        mutation_ref="mutation:decision:observed-owner:certificate",
    )
    certificate_attempt, _ = _commit_certificate(
        context, certificate, certificate_source
    )
    assert certificate_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED

    heartbeat = heartbeat_certified_decision(
        context,
        decision,
        inputs,
        mutation_ref="mutation:decision:observed-owner:heartbeat",
    )
    dependency = next(
        item
        for item in heartbeat.snapshot.dependencies
        if item.role is CommitDecisionDependencyRoleV2.CERTIFICATE
    )
    assert dependency.revision == 1
    assert dependency.transition_id == certificate.transition_id
    assert dependency.receipt_root == (
        certificate_attempt.committed_transition.receipt.receipt_root
    )
    assert heartbeat.snapshot.outcome is None
    assert heartbeat.snapshot.progress is not None
    assert heartbeat.snapshot.progress.unmet_gates == (
        "finality:verified_owner_handle_missing",
    )


def test_unconsumed_finality_owner_successor_invalidates_prepared_decision() -> None:
    from tests.governance._commit_certificate_v2_decision_support import (
        sealed_certified_decision,
    )
    from tests.governance._commit_certificate_v2_store_support import (
        PROFILE as CERTIFIED_PROFILE,
        _root as certificate_root,
        certified_context,
    )
    from tests.governance.test_commit_certificate_v2_operations import (
        _commit_certificate,
        _prepared_certificate,
    )
    from pheroos.governance.commit_certificate_v2 import (
        rehydrate_commit_certificate_state_v2,
    )

    context = certified_context("scope:decision-v2:observed-owner-race")
    decision, inputs = sealed_certified_decision(
        context,
        certificate_root("claim:decision:observed-owner-race"),
    )
    first, first_source = _prepared_certificate(
        context,
        decision,
        mutation_ref="mutation:decision:owner-race:first",
    )
    first_attempt, _ = _commit_certificate(context, first, first_source)
    assert first_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
    first_state = rehydrate_commit_certificate_state_v2(
        first,
        domain=context.domain,
        state_reader=context.store,
    )
    seal = decision.snapshot.seal
    assert seal is not None
    proposal = CommitDecisionCandidateProposalV2(
        candidate_ref=seal.candidate_ref,
        claim_root=seal.claim_root,
        evidence=(),
    )
    prepared, prepared_source = prepare_commit_decision_successor_v2(
        parent_state=decision,
        manifest=context.manifest,
        profile=CERTIFIED_PROFILE,
        mutation_ref="mutation:decision:owner-race:prepared",
        current_step=decision.snapshot.current_step + 1,
        mutation_issuer_ref=context.grant.issuer_ref,
        command=CommitDecisionCommandV2.EVALUATE,
        candidate_proposals=(proposal,),
        commit_replay_state=inputs.replay,
        risk_state=inputs.risk,
        membership_state=inputs.membership,
        support_state=inputs.support,
        evidence_state=inputs.evidence,
        stop_state=inputs.stop,
        permission_state=inputs.permission,
    )
    second, second_source = _prepared_certificate(
        context,
        decision,
        mutation_ref="mutation:decision:owner-race:second",
        certificate_id="certificate:decision-owner-race:second",
        envelope_nonce="nonce:decision-owner-race:second",
        parent_state=first_state,
    )
    second_attempt, _ = _commit_certificate(context, second, second_source)
    assert second_attempt.disposition is GovernanceCommitDispositionV2.COMMITTED

    raced = advance_commit_decision_v2(
        prepared,
        source=prepared_source,
        authority_session=open_commit_decision_authority_session_v2(
            _capability(context, prepared.observed_epoch), prepared
        ),
    )
    assert raced.disposition is GovernanceCommitDispositionV2.RETRY_REQUIRED
    assert raced.failure is not None
    assert raced.failure.code is AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE


def test_fresh_store_inputs_reach_same_step_evidence_commit() -> None:
    context = _decision_context("scope:decision-v2:evidence-commit")
    claim_root = _root("claim:decision")
    inputs = _fresh_inputs(context, claim_root)
    initialize, initialize_source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:decision:initialize",
        current_step=6,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    state = _commit_decision(context, initialize, initialize_source)
    proposal = CommitDecisionCandidateProposalV2(
        candidate_ref="candidate:accept",
        claim_root=claim_root,
        evidence=(),
    )
    for step in (7, 8):
        request, source = prepare_commit_decision_successor_v2(
            parent_state=state,
            manifest=context.manifest,
            profile=PROFILE,
            mutation_ref=f"mutation:decision:evaluate:{step}",
            current_step=step,
            mutation_issuer_ref=context.grant.issuer_ref,
            command=CommitDecisionCommandV2.EVALUATE,
            candidate_proposals=(proposal,),
            commit_replay_state=inputs[0],
            risk_state=inputs[1],
            membership_state=inputs[2],
            support_state=inputs[3],
            evidence_state=inputs[4],
            stop_state=inputs[5],
            permission_state=inputs[6],
        )
        state = _commit_decision(context, request, source)
    assert state.snapshot.window.streak_count == 2
    output = CommitDecisionOutputProposalV2(
        candidate_ref="candidate:accept",
        claim_root=claim_root,
        output_contract_root=_root("output-contract:decision"),
        payload={"answer": "accepted"},
    )
    seal, seal_source = prepare_commit_decision_successor_v2(
        parent_state=state,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:decision:seal",
        current_step=8,
        mutation_issuer_ref=context.grant.issuer_ref,
        command=CommitDecisionCommandV2.SEAL,
        output_proposal=output,
        commit_replay_state=inputs[0],
        risk_state=inputs[1],
        membership_state=inputs[2],
        support_state=inputs[3],
        evidence_state=inputs[4],
        stop_state=inputs[5],
        permission_state=inputs[6],
    )
    state = _commit_decision(context, seal, seal_source)
    final, final_source = prepare_commit_decision_successor_v2(
        parent_state=state,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:decision:finalize",
        current_step=8,
        mutation_issuer_ref=context.grant.issuer_ref,
        command=CommitDecisionCommandV2.EVALUATE,
        candidate_proposals=(proposal,),
        commit_replay_state=inputs[0],
        risk_state=inputs[1],
        membership_state=inputs[2],
        support_state=inputs[3],
        evidence_state=inputs[4],
        stop_state=inputs[5],
        permission_state=inputs[6],
    )
    terminal = _commit_decision(context, final, final_source).snapshot
    assert terminal.outcome is not None
    assert terminal.outcome.kind.value == "evidence_commit"
    assert terminal.outcome.finality_root
    assert terminal.outcome.delivery_eligible


def test_gate_expiry_at_seal_step_resets_instead_of_using_stale_readiness() -> None:
    context = _decision_context(
        "scope:decision-v2:seal-expiry",
        stability_steps=1,
    )
    claim_root = _root("claim:decision:seal-expiry")
    inputs = _fresh_inputs(
        context,
        claim_root,
        gate_expires_at_step=8,
    )
    initialize, initialize_source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:decision:seal-expiry:initialize",
        current_step=6,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    state = _commit_decision(context, initialize, initialize_source)
    proposal = CommitDecisionCandidateProposalV2(
        candidate_ref="candidate:accept",
        claim_root=claim_root,
        evidence=(),
    )
    evaluate, evaluate_source = prepare_commit_decision_successor_v2(
        parent_state=state,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:decision:seal-expiry:evaluate",
        current_step=7,
        mutation_issuer_ref=context.grant.issuer_ref,
        command=CommitDecisionCommandV2.EVALUATE,
        candidate_proposals=(proposal,),
        commit_replay_state=inputs[0],
        risk_state=inputs[1],
        membership_state=inputs[2],
        support_state=inputs[3],
        evidence_state=inputs[4],
        stop_state=inputs[5],
        permission_state=inputs[6],
    )
    state = _commit_decision(context, evaluate, evaluate_source)
    assert state.snapshot.window.streak_count == 1
    output = CommitDecisionOutputProposalV2(
        candidate_ref="candidate:accept",
        claim_root=claim_root,
        output_contract_root=_root("output-contract:decision:seal-expiry"),
        payload={"answer": "must-not-seal"},
    )
    seal, seal_source = prepare_commit_decision_successor_v2(
        parent_state=state,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:decision:seal-expiry:seal",
        current_step=8,
        mutation_issuer_ref=context.grant.issuer_ref,
        command=CommitDecisionCommandV2.SEAL,
        output_proposal=output,
        commit_replay_state=inputs[0],
        risk_state=inputs[1],
        membership_state=inputs[2],
        support_state=inputs[3],
        evidence_state=inputs[4],
        stop_state=inputs[5],
        permission_state=inputs[6],
    )
    reset = _commit_decision(context, seal, seal_source).snapshot
    assert reset.seal is None
    assert reset.outcome is None
    assert reset.progress is not None
    assert reset.mutation_kind.value == "window_reset"
    assert reset.assessment is not None
    assert not reset.assessment.stop_clear
    assert not reset.assessment.permission_allowed


def test_future_step_seal_resets_even_when_all_current_gates_are_fresh() -> None:
    context = _decision_context(
        "scope:decision-v2:seal-step-gap",
        stability_steps=1,
    )
    claim_root = _root("claim:decision:seal-step-gap")
    inputs = _fresh_inputs(context, claim_root, gate_expires_at_step=30)
    initialize, initialize_source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:decision:seal-step-gap:initialize",
        current_step=6,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    state = _commit_decision(context, initialize, initialize_source)
    proposal = CommitDecisionCandidateProposalV2(
        candidate_ref="candidate:accept",
        claim_root=claim_root,
        evidence=(),
    )
    evaluate, evaluate_source = prepare_commit_decision_successor_v2(
        parent_state=state,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:decision:seal-step-gap:evaluate",
        current_step=7,
        mutation_issuer_ref=context.grant.issuer_ref,
        command=CommitDecisionCommandV2.EVALUATE,
        candidate_proposals=(proposal,),
        commit_replay_state=inputs[0],
        risk_state=inputs[1],
        membership_state=inputs[2],
        support_state=inputs[3],
        evidence_state=inputs[4],
        stop_state=inputs[5],
        permission_state=inputs[6],
    )
    state = _commit_decision(context, evaluate, evaluate_source)
    output = CommitDecisionOutputProposalV2(
        candidate_ref="candidate:accept",
        claim_root=claim_root,
        output_contract_root=_root("output-contract:decision:seal-step-gap"),
        payload={"answer": "must-not-seal-across-step-gap"},
    )
    seal, seal_source = prepare_commit_decision_successor_v2(
        parent_state=state,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:decision:seal-step-gap:seal",
        current_step=8,
        mutation_issuer_ref=context.grant.issuer_ref,
        command=CommitDecisionCommandV2.SEAL,
        output_proposal=output,
        commit_replay_state=inputs[0],
        risk_state=inputs[1],
        membership_state=inputs[2],
        support_state=inputs[3],
        evidence_state=inputs[4],
        stop_state=inputs[5],
        permission_state=inputs[6],
    )
    reset = _commit_decision(context, seal, seal_source).snapshot
    assert reset.seal is None
    assert reset.mutation_kind.value == "window_reset"
    assert reset.assessment is not None
    assert reset.assessment.stop_clear
    assert reset.assessment.permission_allowed


def test_window_continuity_is_semantic_and_reset_exhaustion_is_sticky() -> None:
    context = _decision_context("scope:decision-v2:window-semantics")
    claim_root = _root("claim:decision:window-semantics")
    inputs = _fresh_inputs(context, claim_root)
    initialize, initialize_source = prepare_commit_decision_initialize_v2(
        domain=context.domain,
        manifest=context.manifest,
        profile=PROFILE,
        run_ref=RUN_REF,
        target_ref=TARGET,
        observed_epoch=1,
        mutation_ref="mutation:decision:window-semantics:initialize",
        current_step=6,
        mutation_issuer_ref=context.grant.issuer_ref,
    )
    state = _commit_decision(context, initialize, initialize_source)
    proposal = CommitDecisionCandidateProposalV2(
        candidate_ref="candidate:accept",
        claim_root=claim_root,
        evidence=(),
    )
    evaluate, evaluate_source = prepare_commit_decision_successor_v2(
        parent_state=state,
        manifest=context.manifest,
        profile=PROFILE,
        mutation_ref="mutation:decision:window-semantics:evaluate",
        current_step=7,
        mutation_issuer_ref=context.grant.issuer_ref,
        command=CommitDecisionCommandV2.EVALUATE,
        candidate_proposals=(proposal,),
        commit_replay_state=inputs[0],
        risk_state=inputs[1],
        membership_state=inputs[2],
        support_state=inputs[3],
        evidence_state=inputs[4],
        stop_state=inputs[5],
        permission_state=inputs[6],
    )
    parent = _commit_decision(context, evaluate, evaluate_source).snapshot
    assert parent.assessment is not None
    current = replace(
        parent.assessment,
        current_step=8,
        evaluation_context_root=_root("evaluation:window-semantics:8"),
        assessment_root="",
    )
    benign_roles = {
        CommitDecisionDependencyRoleV2.EVIDENCE,
        CommitDecisionDependencyRoleV2.REPLAY,
        CommitDecisionDependencyRoleV2.SUPPORT,
        CommitDecisionDependencyRoleV2.STOP,
        CommitDecisionDependencyRoleV2.PERMISSION,
    }
    hard_roles = {
        CommitDecisionDependencyRoleV2.RISK,
        CommitDecisionDependencyRoleV2.MEMBERSHIP,
        CommitDecisionDependencyRoleV2.PRINCIPAL_VERIFICATION,
    }
    for role in benign_roles | hard_roles:
        changed = tuple(
            replace(
                item,
                head_root=_root(f"window-semantics:changed:{role.value}"),
                dependency_root="",
            )
            if item.role is role
            else item
            for item in parent.dependencies
        )
        assert _window_semantics_continuous(parent, current, changed) is (
            role in benign_roles
        )
    changed_claim = replace(
        current.candidate_metrics[0],
        claim_root=_root("claim:decision:window-semantics:changed"),
        metrics_root="",
    )
    claim_substitution = replace(
        current,
        candidate_metrics=(changed_claim,),
        collective_claim_root=_root("collective-claim:changed"),
        assessment_root="",
    )
    assert not _window_semantics_continuous(
        parent,
        claim_substitution,
        parent.dependencies,
    )
    assert not _window_semantics_continuous(
        parent,
        replace(current, current_step=9, assessment_root=""),
        parent.dependencies,
    )

    one_reset = replace(
        parent.window,
        remaining_reset_budget=1,
        reset_budget_exhausted=False,
        window_root="",
    )
    parent_proxy = SimpleNamespace(
        window=one_reset,
        current_step=parent.current_step,
        assessment=parent.assessment,
        dependencies=parent.dependencies,
    )
    not_ready = replace(
        current,
        leader_ready_for_stability=False,
        reason_codes=("leader:not_ready",),
        assessment_root="",
    )
    reset, _ = _advance_window(
        parent_proxy,
        not_ready,
        required_stability_steps=one_reset.required_stability_steps,
        dependencies=parent.dependencies,
    )
    assert reset.remaining_reset_budget == 0
    assert not reset.reset_budget_exhausted
    ready_proxy = SimpleNamespace(
        window=reset,
        current_step=8,
        assessment=not_ready,
        dependencies=parent.dependencies,
    )
    restarted, _ = _advance_window(
        ready_proxy,
        replace(current, current_step=9, assessment_root=""),
        required_stability_steps=reset.required_stability_steps,
        dependencies=parent.dependencies,
    )
    assert restarted.streak_count == 1
    exhausted_proxy = SimpleNamespace(
        window=restarted,
        current_step=9,
        assessment=replace(current, current_step=9, assessment_root=""),
        dependencies=parent.dependencies,
    )
    exhausted, _ = _advance_window(
        exhausted_proxy,
        replace(not_ready, current_step=10, assessment_root=""),
        required_stability_steps=restarted.required_stability_steps,
        dependencies=parent.dependencies,
    )
    assert exhausted.remaining_reset_budget == 0
    assert exhausted.reset_budget_exhausted
    assert exhausted.streak_count == 0
    restored = CommitDecisionWindowV2.from_dict(exhausted.to_dict())
    assert restored.reset_budget_exhausted
