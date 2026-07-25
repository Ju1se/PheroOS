from __future__ import annotations

from dataclasses import fields, replace
from copy import copy

import pytest

from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.certificate import (
    issue_outcome_certificate,
    local_commit_receipt_fingerprint,
    local_commit_receipt_is_authoritative,
    outcome_certificate_fingerprint,
    outcome_certificate_body_root,
    outcome_certificate_is_authoritative,
    outcome_certificate_payload,
    output_payload_fingerprint,
    verify_local_commit_finality,
    verify_evidence_commit_certificate,
    verify_outcome_certificate,
    OutcomeCertificate,
)
from pheroos.governance.commit_state import (
    CommitFinalityStatus,
    DecisionOutcome,
    DecisionOutcomeKind,
    initialize_commit_window_state,
    issue_commit_liveness_input,
    reduce_commit_liveness,
    decision_outcome_fingerprint,
    decision_outcome_is_authoritative,
)
from pheroos.governance.output import (
    CommitOutputAction,
    authorize_terminal_execution,
    authorize_terminal_publication,
    commit_output_authorization_fingerprint,
    commit_output_authorization_is_authoritative,
    deliver_terminal_outcome,
    _certificate_lineage_matches_outcome,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.permission import issue_action_permission
from pheroos.governance.stop_signal import (
    StopResolution,
    verify_stop_resolution,
)
from pheroos.protocol.commit_models import CommitAction
from tests.governance import test_commit_engine as engine_fixture
from tests.governance.test_commit_certificate import (
    _certified_scenario,
    _receipt,
    _stable_scenario,
    _mutated_leaf,
)


def _liveness_input(
    scenario,
    window,
    *,
    assessment,
    current_step: int,
    finality_status: CommitFinalityStatus,
    invalid: tuple[str, ...] = (),
    safety: tuple[str, ...] = (),
    blocked: tuple[str, ...] = (),
    finality: tuple[str, ...] = (),
    finality_verification=None,
    previous_progress=None,
):
    return issue_commit_liveness_input(
        window,
        assessment=assessment,
        replay_state=scenario.replay_state,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        support_replay_state=scenario.support_replay_state,
        commit_policy=scenario.policy,
        previous_progress=previous_progress,
        current_step=current_step,
        finality_status=finality_status,
        finality_verification=finality_verification,
        invalid_reason_codes=invalid,
        safety_violation_reason_codes=safety,
        blocked_reason_codes=blocked,
        finality_reason_codes=finality,
        next_required_inputs=("additional_evidence",),
        input_id=f"liveness:{scenario.run_id}:{current_step}:{finality_status.value}",
        issuer_id="governance:liveness",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:test:liveness:{scenario.run_id}",
        trace_event_id=f"trace:liveness:{scenario.run_id}:{current_step}",
    )


def _evidence_commit_outcome():
    scenario, assessment, window, output_ref = _stable_scenario()
    receipt = _receipt(scenario, assessment, window, output_ref)
    verification = verify_local_commit_finality(
        receipt,
        scenario.context,
        assessment,
        window,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=scenario.replay_state,
        support_replay_state=scenario.support_replay_state,
        current_step=6,
        verifier_id="governance:local-finality",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:test:local-finality:{scenario.run_id}",
        trace_event_id=f"trace:local-finality:{scenario.run_id}",
    )
    liveness = _liveness_input(
        scenario,
        window,
        assessment=assessment,
        current_step=6,
        finality_status=CommitFinalityStatus.VERIFIED,
        finality_verification=verification,
    )
    outcome = reduce_commit_liveness(
        window,
        commit_policy=scenario.policy,
        liveness_input=liveness,
    )
    assert type(outcome) is DecisionOutcome
    assert outcome.kind is DecisionOutcomeKind.EVIDENCE_COMMIT
    return scenario, assessment, window, output_ref, receipt, outcome


def _initial_window(scenario):
    return initialize_commit_window_state(
        commit_policy=scenario.policy,
        profile=scenario.context.profile,
        assurance=scenario.context.assurance,
        manifest_root=scenario.context.manifest_root,
        commit_policy_root=scenario.context.commit_policy_root,
        protocol_id=scenario.context.protocol_id,
        run_id=scenario.context.run_id,
        target=scenario.context.target,
        epoch=scenario.context.epoch,
        risk_assessment_root=scenario.context.risk_assessment_fingerprint,
        membership_root=scenario.context.membership_root,
        threshold_snapshot=scenario.threshold,
        current_step=4,
        issuer_id="governance:window",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:test:window:{scenario.run_id}",
        trace_event_id=f"trace:window:{scenario.run_id}",
    )


def _nonready_outcome(
    kind: DecisionOutcomeKind,
    *,
    monkeypatch: pytest.MonkeyPatch | None = None,
):
    if kind is DecisionOutcomeKind.ADVISORY:
        assert monkeypatch is not None
        original = engine_fixture._policy

        def advisory_deadline_policy(**kwargs):
            policy = original(**kwargs)
            return replace(
                policy,
                terminal_outcome=replace(
                    policy.terminal_outcome,
                    deadline_outcome="advisory",
                ),
            )

        monkeypatch.setattr(engine_fixture, "_policy", advisory_deadline_policy)
    scenario = engine_fixture._scenario()
    window = _initial_window(scenario)
    current = 6
    finality_status = CommitFinalityStatus.PENDING
    kwargs: dict[str, tuple[str, ...]] = {}
    if kind is DecisionOutcomeKind.INVALID:
        kwargs["invalid"] = ("invalid_protocol_instance",)
    elif kind is DecisionOutcomeKind.SAFETY_VIOLATION:
        kwargs["safety"] = ("conflicting_authority_head",)
    elif kind is DecisionOutcomeKind.BLOCKED:
        kwargs["blocked"] = ("hard_policy_denial",)
    elif kind is DecisionOutcomeKind.FINALITY_UNAVAILABLE:
        finality_status = CommitFinalityStatus.UNAVAILABLE
        kwargs["finality"] = ("verified_finality_unavailable",)
        current = window.absolute_deadline_step
    elif kind in {DecisionOutcomeKind.SAFE_FALLBACK, DecisionOutcomeKind.ADVISORY}:
        current = window.absolute_deadline_step
    else:
        raise AssertionError(kind)
    liveness = _liveness_input(
        scenario,
        window,
        assessment=None,
        current_step=current,
        finality_status=finality_status,
        **kwargs,
    )
    outcome = reduce_commit_liveness(
        window,
        commit_policy=scenario.policy,
        liveness_input=liveness,
    )
    assert type(outcome) is DecisionOutcome
    assert outcome.kind is kind
    return scenario, window, outcome


def _certified_finality_unavailable_outcome(
    monkeypatch: pytest.MonkeyPatch,
):
    scenario, assessment, window, output_ref = _certified_scenario(monkeypatch)
    _receipt(scenario, assessment, window, output_ref)
    outcome = _reduce_certified_finality_unavailable(
        scenario,
        assessment,
        window,
    )
    return outcome


def _reduce_certified_finality_unavailable(
    scenario,
    assessment,
    window,
):
    progress = reduce_commit_liveness(
        window,
        commit_policy=scenario.policy,
        liveness_input=_liveness_input(
            scenario,
            window,
            assessment=assessment,
            current_step=window.last_evaluated_step,
            finality_status=CommitFinalityStatus.PENDING,
        ),
    )
    for step in range(
        window.last_evaluated_step + 1,
        window.absolute_deadline_step,
    ):
        progress = reduce_commit_liveness(
            window,
            commit_policy=scenario.policy,
            liveness_input=_liveness_input(
                scenario,
                window,
                assessment=assessment,
                previous_progress=progress,
                current_step=step,
                finality_status=CommitFinalityStatus.PENDING,
            ),
        )
    liveness = _liveness_input(
        scenario,
        window,
        assessment=assessment,
        previous_progress=progress,
        current_step=window.absolute_deadline_step,
        finality_status=CommitFinalityStatus.UNAVAILABLE,
        finality=("verified_finality_unavailable",),
    )
    outcome = reduce_commit_liveness(
        window,
        commit_policy=scenario.policy,
        liveness_input=liveness,
    )
    assert type(outcome) is DecisionOutcome
    assert outcome.kind is DecisionOutcomeKind.FINALITY_UNAVAILABLE
    return outcome


def _action_authorities(
    scenario,
    outcome: DecisionOutcome,
    *,
    action: CommitAction,
    certificate_ref: str,
    issued_at_step: int,
    expires_at_step: int,
):
    decision_ref = decision_outcome_fingerprint(outcome)
    stop = verify_stop_resolution(
        StopResolution(
            target=outcome.target,
            action=action.value,
            blocked=False,
            reason=f"{action.value}_stops_resolved",
        ),
        resolution_id=f"stop:{scenario.run_id}:{action.value}",
        profile=outcome.profile,
        assurance=outcome.assurance,
        manifest_root=outcome.manifest_root,
        commit_policy_root=outcome.commit_policy_root,
        protocol_id=outcome.protocol_id,
        run_id=outcome.run_id,
        epoch=outcome.epoch,
        decision_ref=decision_ref,
        certificate_ref=certificate_ref,
        resolved_stop_root=engine_fixture._fingerprint(
            f"stop-root:{scenario.run_id}:{action.value}"
        ),
        verifier_id="governance:output-stop",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=issued_at_step,
        expires_at_step=expires_at_step,
        provenance=f"urn:test:output-stop:{scenario.run_id}:{action.value}",
        trace_event_id=f"trace:output-stop:{scenario.run_id}:{action.value}",
    )
    permission = issue_action_permission(
        permission_id=f"permission:{scenario.run_id}:{action.value}",
        profile=outcome.profile,
        assurance=outcome.assurance,
        manifest_root=outcome.manifest_root,
        commit_policy_root=outcome.commit_policy_root,
        protocol_id=outcome.protocol_id,
        run_id=outcome.run_id,
        target=outcome.target,
        action=action,
        epoch=outcome.epoch,
        decision_ref=decision_ref,
        certificate_ref=certificate_ref,
        allowed=True,
        reason_codes=(f"{action.value}_authorized",),
        issuer_id="governance:output-permission",
        policy_ref="policy:output-actions-v1",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=issued_at_step,
        expires_at_step=expires_at_step,
        provenance=f"urn:test:output-permission:{scenario.run_id}:{action.value}",
        trace_event_id=f"trace:output-permission:{scenario.run_id}:{action.value}",
    )
    return stop, permission


def test_every_terminal_kind_is_deliverable_and_result_is_tamper_evident(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcomes = [_evidence_commit_outcome()[-1]]
    for kind in (
        DecisionOutcomeKind.SAFE_FALLBACK,
        DecisionOutcomeKind.ADVISORY,
        DecisionOutcomeKind.BLOCKED,
        DecisionOutcomeKind.INVALID,
        DecisionOutcomeKind.FINALITY_UNAVAILABLE,
        DecisionOutcomeKind.SAFETY_VIOLATION,
    ):
        # Advisory modifies only its own scenario and pytest restores after test;
        # reset the helper before producing later scenarios in this test.
        if kind is DecisionOutcomeKind.ADVISORY:
            with monkeypatch.context() as scoped:
                outcomes.append(_nonready_outcome(kind, monkeypatch=scoped)[-1])
        elif kind is DecisionOutcomeKind.FINALITY_UNAVAILABLE:
            with monkeypatch.context() as scoped:
                outcomes.append(_certified_finality_unavailable_outcome(scoped))
        else:
            outcomes.append(_nonready_outcome(kind)[-1])

    assert {item.kind for item in outcomes} == set(DecisionOutcomeKind)
    for outcome in outcomes:
        output_ref = output_payload_fingerprint(
            {"kind": outcome.kind.value, "terminal": True},
            profile=outcome.profile,
        )
        result = deliver_terminal_outcome(
            outcome,
            output_payload_fingerprint=output_ref,
        )
        assert result.authorized
        assert result.action is CommitOutputAction.DELIVER
        assert commit_output_authorization_is_authoritative(result)
        assert commit_output_authorization_fingerprint(result).startswith("sha256:")
        forged = replace(result)
        assert not commit_output_authorization_is_authoritative(forged)
        object.__setattr__(
            result,
            "output_payload_fingerprint",
            engine_fixture._fingerprint("tampered"),
        )
        assert not commit_output_authorization_is_authoritative(result)


def test_publish_requires_current_publish_stop_permission_and_certificate() -> None:
    scenario, assessment, window, output_ref, receipt, outcome = (
        _evidence_commit_outcome()
    )
    assert _receipt(scenario, assessment, window, output_ref) is receipt
    receipt_ref = local_commit_receipt_fingerprint(receipt)
    publish_stop, publish_permission = _action_authorities(
        scenario,
        outcome,
        action=CommitAction.PUBLISH,
        certificate_ref=receipt_ref,
        issued_at_step=6,
        expires_at_step=8,
    )
    result = authorize_terminal_publication(
        outcome,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        certificate=receipt,
        output_payload_fingerprint=output_ref,
        stop_resolution=publish_stop,
        permission=publish_permission,
        current_step=7,
    )
    assert result.authorized
    assert commit_output_authorization_is_authoritative(result)
    assert all(
        (
            result.outcome_ref,
            result.certificate_ref,
            result.output_payload_fingerprint,
            result.policy_ref,
            result.threshold_ref,
            result.stop_resolution_ref,
            result.permission_ref,
        )
    )
    for record in fields(type(result)):
        if not record.init:
            continue
        forged_result = copy(result)
        if record.name == "gates":
            mutated = dict(result.gates)
            first = next(iter(mutated))
            mutated[first] = not mutated[first]
        elif record.name == "reason_codes":
            mutated = (*result.reason_codes, "tampered_authorization")
        else:
            mutated = _mutated_leaf(
                record.name,
                getattr(result, record.name),
            )
        object.__setattr__(forged_result, record.name, mutated)
        assert not commit_output_authorization_is_authoritative(forged_result), (
            record.name
        )

    # A historical commit stays valid; only the current publication is denied.
    expired = authorize_terminal_publication(
        outcome,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        certificate=receipt,
        output_payload_fingerprint=output_ref,
        stop_resolution=publish_stop,
        permission=publish_permission,
        current_step=8,
    )
    assert not expired.authorized
    assert not expired.gates["publish_permission_allowed"]
    assert local_commit_receipt_is_authoritative(receipt)
    assert decision_outcome_is_authoritative(outcome)

    forged_certificate = replace(receipt)
    forged = authorize_terminal_publication(
        outcome,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        certificate=forged_certificate,
        output_payload_fingerprint=output_ref,
        stop_resolution=publish_stop,
        permission=publish_permission,
        current_step=7,
    )
    assert not forged.authorized
    assert not forged.gates["certificate_valid"]


def test_commit_output_certificate_matches_every_authority_lineage_root() -> None:
    _, _, _, output_ref, receipt, outcome = _evidence_commit_outcome()
    assert _certificate_lineage_matches_outcome(
        receipt,
        outcome,
        output_payload_fingerprint=output_ref,
    )
    lineage_names = (
        "risk_chain_state_root",
        "risk_assessment_root",
        "risk_policy_root",
        "membership_snapshot_root",
        "membership_epoch_state_root",
        "membership_root",
        "threshold_root",
        "replay_root",
        "support_replay_state_root",
        "support_replay_root",
        "collective_evidence_root",
        "collective_challenge_root",
        "collective_lease_root",
        "candidate_evidence_root",
        "candidate_challenge_root",
        "candidate_lease_root",
        "window_root",
        "stop_resolution_root",
        "permission_root",
    )
    for name in lineage_names:
        forged = replace(
            outcome,
            **{name: engine_fixture._fingerprint(f"forged:{name}")},
        )
        assert not _certificate_lineage_matches_outcome(
            receipt,
            forged,
            output_payload_fingerprint=output_ref,
        ), name


def test_commit_stop_cannot_substitute_for_publish_or_execute_stop() -> None:
    scenario, _, _, output_ref, receipt, outcome = _evidence_commit_outcome()
    receipt_ref = local_commit_receipt_fingerprint(receipt)
    _, publish_permission = _action_authorities(
        scenario,
        outcome,
        action=CommitAction.PUBLISH,
        certificate_ref=receipt_ref,
        issued_at_step=6,
        expires_at_step=9,
    )
    denied = authorize_terminal_publication(
        outcome,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        certificate=receipt,
        output_payload_fingerprint=output_ref,
        stop_resolution=scenario.stop_resolution,
        permission=publish_permission,
        current_step=7,
    )
    assert not denied.authorized
    assert not denied.gates["publish_stop_resolved"]

    execute_stop, execute_permission = _action_authorities(
        scenario,
        outcome,
        action=CommitAction.EXECUTE,
        certificate_ref=receipt_ref,
        issued_at_step=6,
        expires_at_step=9,
    )
    execute = authorize_terminal_execution(
        outcome,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        certificate=receipt,
        output_payload_fingerprint=output_ref,
        stop_resolution=execute_stop,
        permission=execute_permission,
        current_step=7,
    )
    assert not execute.authorized
    assert not execute.gates["policy_outcome_allowed"]
    assert not execute.gates["threshold_outcome_allowed"]


def test_execute_requires_separate_explicit_policy_stop_and_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = engine_fixture._policy

    def executable_commit_policy(**kwargs):
        policy = original(**kwargs)
        return replace(
            policy,
            risk_bands={
                name: replace(band, executable_outcomes=["evidence_commit"])
                for name, band in policy.risk_bands.items()
            },
            terminal_outcome=replace(
                policy.terminal_outcome,
                executable_outcomes=["evidence_commit"],
            ),
        )

    monkeypatch.setattr(engine_fixture, "_policy", executable_commit_policy)
    scenario, _, _, output_ref, receipt, outcome = _evidence_commit_outcome()
    receipt_ref = local_commit_receipt_fingerprint(receipt)
    execute_stop, execute_permission = _action_authorities(
        scenario,
        outcome,
        action=CommitAction.EXECUTE,
        certificate_ref=receipt_ref,
        issued_at_step=6,
        expires_at_step=9,
    )
    allowed = authorize_terminal_execution(
        outcome,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        certificate=receipt,
        output_payload_fingerprint=output_ref,
        stop_resolution=execute_stop,
        permission=execute_permission,
        current_step=7,
    )
    assert allowed.authorized
    assert commit_output_authorization_is_authoritative(allowed)

    publish_stop, _ = _action_authorities(
        scenario,
        outcome,
        action=CommitAction.PUBLISH,
        certificate_ref=receipt_ref,
        issued_at_step=6,
        expires_at_step=9,
    )
    denied = authorize_terminal_execution(
        outcome,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        certificate=receipt,
        output_payload_fingerprint=output_ref,
        stop_resolution=publish_stop,
        permission=execute_permission,
        current_step=7,
    )
    assert not denied.authorized
    assert not denied.gates["execute_stop_resolved"]


def test_safe_fallback_can_publish_only_when_explicitly_allowed_and_never_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = engine_fixture._policy

    def fallback_publish_policy(**kwargs):
        policy = original(**kwargs)
        return replace(
            policy,
            risk_bands={
                name: replace(
                    band,
                    publishable_outcomes=["evidence_commit", "safe_fallback"],
                )
                for name, band in policy.risk_bands.items()
            },
        )

    monkeypatch.setattr(engine_fixture, "_policy", fallback_publish_policy)
    scenario, window, outcome = _nonready_outcome(DecisionOutcomeKind.SAFE_FALLBACK)
    output_ref = output_payload_fingerprint(
        {"kind": "safe_fallback", "epistemic_commit": False},
        profile=outcome.profile,
    )
    certificate = issue_outcome_certificate(
        outcome,
        window,
        commit_policy=scenario.policy,
        output_payload_fingerprint=output_ref,
        certificate_id=f"outcome-certificate:{scenario.run_id}",
        context=scenario.context,
        assessment=None,
        issuer_id="governance:outcome-certificate",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=outcome.current_step,
        provenance=f"urn:test:outcome-certificate:{scenario.run_id}",
        trace_event_id=f"trace:outcome-certificate:{scenario.run_id}",
    )
    certificate_ref = outcome_certificate_fingerprint(certificate)
    publish_stop, publish_permission = _action_authorities(
        scenario,
        outcome,
        action=CommitAction.PUBLISH,
        certificate_ref=certificate_ref,
        issued_at_step=outcome.current_step,
        expires_at_step=outcome.current_step + 3,
    )
    publish = authorize_terminal_publication(
        outcome,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        certificate=certificate,
        output_payload_fingerprint=output_ref,
        stop_resolution=publish_stop,
        permission=publish_permission,
        current_step=outcome.current_step,
    )
    assert publish.authorized
    assert outcome.epistemically_committed is False
    assert outcome.authoritative_commit is False
    assert outcome_certificate_is_authoritative(certificate)
    assert verify_outcome_certificate(
        certificate,
        expected_certificate_ref=certificate_ref,
        expected_output_payload_fingerprint=output_ref,
    )

    assert (
        issue_outcome_certificate(
            outcome,
            window,
            commit_policy=scenario.policy,
            output_payload_fingerprint=output_ref,
            certificate_id=f"outcome-certificate:{scenario.run_id}",
            context=scenario.context,
            assessment=None,
            issuer_id="governance:outcome-certificate",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=outcome.current_step,
            provenance=f"urn:test:outcome-certificate:{scenario.run_id}",
            trace_event_id=f"trace:outcome-certificate:{scenario.run_id}",
        )
        is certificate
    )
    with pytest.raises(GovernanceError, match="different body"):
        issue_outcome_certificate(
            outcome,
            window,
            commit_policy=scenario.policy,
            output_payload_fingerprint=output_payload_fingerprint(
                {"kind": "safe_fallback", "conflicting": True},
                profile=outcome.profile,
            ),
            certificate_id=f"outcome-certificate:{scenario.run_id}",
            context=scenario.context,
            assessment=None,
            issuer_id="governance:outcome-certificate",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=outcome.current_step,
            provenance=f"urn:test:outcome-certificate:{scenario.run_id}",
            trace_event_id=f"trace:outcome-certificate:{scenario.run_id}",
        )

    for record in fields(OutcomeCertificate):
        if not record.init:
            continue
        try:
            forged_leaf = replace(
                certificate,
                **{
                    record.name: _mutated_leaf(
                        record.name,
                        getattr(certificate, record.name),
                    )
                },
            )
        except (GovernanceError, TypeError, ValueError):
            continue
        assert not outcome_certificate_is_authoritative(forged_leaf), record.name
        assert not verify_outcome_certificate(forged_leaf), record.name

    execute_stop, execute_permission = _action_authorities(
        scenario,
        outcome,
        action=CommitAction.EXECUTE,
        certificate_ref=certificate_ref,
        issued_at_step=outcome.current_step,
        expires_at_step=outcome.current_step + 3,
    )
    execute = authorize_terminal_execution(
        outcome,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        certificate=certificate,
        output_payload_fingerprint=output_ref,
        stop_resolution=execute_stop,
        permission=execute_permission,
        current_step=outcome.current_step,
    )
    assert not execute.authorized
    assert not execute.gates["hard_kind_allowed"]

    # Schema/type separation is strict in both directions.
    assert not verify_evidence_commit_certificate(
        outcome_certificate_payload(certificate),
        trusted_issuer_attestations={},
    )
    forged = replace(certificate)
    assert not outcome_certificate_is_authoritative(forged)
    with pytest.raises(GovernanceError, match="cannot carry a commit proof"):
        replace(
            certificate,
            commit_certificate_ref=engine_fixture._fingerprint(
                "forged-safe-fallback-commit-proof"
            ),
        )
    with pytest.raises(GovernanceError, match="cannot claim portable attestations"):
        replace(
            certificate,
            issuer_attestation_refs=("attestation:forged-portability",),
        )

    (
        commit_scenario,
        _,
        _,
        commit_output_ref,
        commit_receipt,
        commit_outcome,
    ) = _evidence_commit_outcome()
    commit_receipt_ref = local_commit_receipt_fingerprint(commit_receipt)
    commit_stop, commit_permission = _action_authorities(
        commit_scenario,
        commit_outcome,
        action=CommitAction.PUBLISH,
        certificate_ref=commit_receipt_ref,
        issued_at_step=commit_outcome.current_step,
        expires_at_step=commit_outcome.current_step + 3,
    )
    fallback_as_commit = authorize_terminal_publication(
        commit_outcome,
        commit_policy=commit_scenario.policy,
        threshold_snapshot=commit_scenario.threshold,
        certificate=certificate,
        output_payload_fingerprint=commit_output_ref,
        stop_resolution=commit_stop,
        permission=commit_permission,
        current_step=commit_outcome.current_step,
    )
    assert not fallback_as_commit.authorized
    assert not fallback_as_commit.gates["certificate_valid"]


def test_certified_noncommit_outcome_certificate_verifies_from_wire_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario, assessment, window, sealed_output_ref = _certified_scenario(monkeypatch)
    _receipt(scenario, assessment, window, sealed_output_ref)
    outcome = _reduce_certified_finality_unavailable(
        scenario,
        assessment,
        window,
    )
    assert type(outcome) is DecisionOutcome
    assert outcome.kind is DecisionOutcomeKind.FINALITY_UNAVAILABLE
    output_ref = output_payload_fingerprint(
        {"kind": outcome.kind.value, "final_commit": False},
        profile=outcome.profile,
    )
    metadata = {
        "certificate_id": f"outcome-certificate:{scenario.run_id}",
        "issuer_id": "governance:portable-outcome",
        "authority": AuthorityLevel.GOVERNANCE,
        "issued_at_step": outcome.current_step,
        "provenance": f"urn:test:portable-outcome:{scenario.run_id}",
        "trace_event_id": f"trace:portable-outcome:{scenario.run_id}",
    }
    body_root = outcome_certificate_body_root(
        outcome,
        window,
        commit_policy=scenario.policy,
        output_payload_fingerprint=output_ref,
        context=scenario.context,
        assessment=assessment,
        **metadata,
    )
    trusted = {"attestation:portable-outcome": body_root}
    certificate = issue_outcome_certificate(
        outcome,
        window,
        commit_policy=scenario.policy,
        output_payload_fingerprint=output_ref,
        context=scenario.context,
        assessment=assessment,
        issuer_attestation_refs=tuple(trusted),
        trusted_issuer_attestations=trusted,
        **metadata,
    )
    ref = outcome_certificate_fingerprint(certificate)
    payload = outcome_certificate_payload(certificate)
    assert verify_outcome_certificate(
        dict(reversed(tuple(payload.items()))),
        trusted_issuer_attestations=trusted,
        expected_certificate_ref=ref,
        expected_output_payload_fingerprint=output_ref,
    )
    assert not verify_evidence_commit_certificate(
        payload,
        trusted_issuer_attestations=trusted,
    )
    for record in fields(OutcomeCertificate):
        if not record.init:
            continue
        mutated = dict(payload)
        mutated[record.name] = _mutated_leaf(
            record.name,
            mutated[record.name],
        )
        assert not verify_outcome_certificate(
            mutated,
            trusted_issuer_attestations=trusted,
        ), record.name
    for boolean_name in ("authoritative_commit", "epistemically_committed"):
        integer_boolean = dict(payload)
        integer_boolean[boolean_name] = 0
        assert not verify_outcome_certificate(
            integer_boolean,
            trusted_issuer_attestations=trusted,
        ), boolean_name


def test_distributed_publish_requires_current_final_state_and_freeze_denies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pheroos.governance.distributed_commit import (
        distributed_commit_certificate_fingerprint,
        register_distributed_commit_certificate,
        verify_distributed_commit_finality,
    )
    from tests.governance import test_distributed_commit as distributed_fixture

    bundle = distributed_fixture._distributed_scenario(monkeypatch)
    certificate = distributed_fixture._certificate(
        bundle,
        bundle.verifications[:3],
        suffix="output-current-final",
    )
    registered = register_distributed_commit_certificate(
        bundle.state,
        certificate,
        commit_policy=bundle.scenario.policy,
        portable_certificate=bundle.portable_certificate,
        trusted_issuer_attestations=bundle.issuer_trust,
        trusted_witness_attestations=bundle.witness_trust,
        current_step=6,
    )
    finality = verify_distributed_commit_finality(
        certificate,
        registered,
        bundle.receipt,
        current_step=6,
        verifier_id="governance:distributed-output-finality",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:distributed-output-finality",
        trace_event_id="trace:distributed-output-finality",
    )
    liveness = issue_commit_liveness_input(
        bundle.window,
        assessment=bundle.assessment,
        replay_state=bundle.scenario.replay_state,
        risk_chain_state=bundle.scenario.risk_chain_state,
        risk_assessment=bundle.scenario.risk_assessment,
        threshold_snapshot=bundle.scenario.threshold,
        membership_snapshot=bundle.scenario.membership_snapshot,
        membership_epoch_state=bundle.scenario.membership_state,
        support_replay_state=bundle.scenario.support_replay_state,
        commit_policy=bundle.scenario.policy,
        current_step=6,
        finality_status=CommitFinalityStatus.VERIFIED,
        finality_verification=finality,
        input_id=f"liveness:{bundle.scenario.run_id}:distributed-output",
        issuer_id="governance:liveness",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:liveness:distributed-output",
        trace_event_id="trace:liveness:distributed-output",
    )
    outcome = reduce_commit_liveness(
        bundle.window,
        commit_policy=bundle.scenario.policy,
        liveness_input=liveness,
    )
    assert type(outcome) is DecisionOutcome
    certificate_ref = distributed_commit_certificate_fingerprint(certificate)
    assert outcome.certificate_ref == certificate_ref
    output_ref = certificate.proposal.output_payload_fingerprint
    publish_stop, publish_permission = _action_authorities(
        bundle.scenario,
        outcome,
        action=CommitAction.PUBLISH,
        certificate_ref=certificate_ref,
        issued_at_step=6,
        expires_at_step=9,
    )
    allowed = authorize_terminal_publication(
        outcome,
        commit_policy=bundle.scenario.policy,
        threshold_snapshot=bundle.scenario.threshold,
        certificate=certificate,
        output_payload_fingerprint=output_ref,
        stop_resolution=publish_stop,
        permission=publish_permission,
        current_step=6,
        trusted_issuer_attestations=bundle.issuer_trust,
        distributed_state=registered,
        portable_certificate=bundle.portable_certificate,
        trusted_witness_attestations=bundle.witness_trust,
    )
    assert allowed.authorized
    assert allowed.distributed_state_ref
    assert allowed.distributed_conflict_root
    assert commit_output_authorization_is_authoritative(allowed)

    (
        _,
        conflict_portable,
        conflict_issuer_trust,
        conflict_witness_trust,
        second_certificate,
    ) = distributed_fixture._portable_semantic_conflict(
        bundle,
        field_name="output_payload_fingerprint",
        field_value=engine_fixture._fingerprint(
            f"distributed-output-conflict:{bundle.scenario.run_id}"
        ),
        suffix="output-semantic-conflict",
    )
    frozen = register_distributed_commit_certificate(
        registered,
        second_certificate,
        commit_policy=bundle.scenario.policy,
        portable_certificate=conflict_portable,
        trusted_issuer_attestations=conflict_issuer_trust,
        trusted_witness_attestations=conflict_witness_trust,
        current_step=6,
    )
    assert frozen.frozen
    denied = authorize_terminal_publication(
        outcome,
        commit_policy=bundle.scenario.policy,
        threshold_snapshot=bundle.scenario.threshold,
        certificate=certificate,
        output_payload_fingerprint=output_ref,
        stop_resolution=publish_stop,
        permission=publish_permission,
        current_step=6,
        trusted_issuer_attestations=bundle.issuer_trust,
        distributed_state=frozen,
        portable_certificate=bundle.portable_certificate,
        trusted_witness_attestations=bundle.witness_trust,
    )
    assert not denied.authorized
    assert not denied.gates["certificate_valid"]
    assert denied.distributed_state_ref != allowed.distributed_state_ref
    assert denied.distributed_conflict_root != allowed.distributed_conflict_root
    assert commit_output_authorization_fingerprint(denied) != (
        commit_output_authorization_fingerprint(allowed)
    )
