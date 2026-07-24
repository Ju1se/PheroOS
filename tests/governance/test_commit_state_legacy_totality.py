from __future__ import annotations

from copy import copy
from dataclasses import replace
from typing import Any, cast

import pytest

from pheroos.governance._commit_state._liveness_contract import (
    _validate_assessment_lineage_roots,
    _validate_sealed_heartbeat_lineage,
)
from pheroos.governance._commit_state._replay_contract import (
    canonical_replay_receipts,
)
from pheroos.governance._commit_state._window_contract import (
    _authoritative_commit_assessment_view,
    _threshold_snapshot_bindings,
    _validate_assessment_matches_window_head,
    _validate_window_chain_scope,
    _validate_window_threshold_snapshot,
)
from pheroos.governance._commit_state.invariants import (
    _normalized_window_bindings,
    _validate_bound_commit_policy,
    _validate_commit_binding_values,
)
from pheroos.governance._commit_state.liveness_authority import (
    _assessment_heads_are_current,
    _liveness_authority_heads_are_current,
    _require_bound_policy,
    _validate_seal_lineage,
    _validate_bound_snapshot_roots,
    _validate_current_chain_heads,
    _validate_fresh_membership_snapshot,
    _validate_fresh_risk_snapshot,
    liveness_authority_heads_are_current_impl,
    validate_finality_verification_matches_window_impl,
    validate_liveness_input_matches_window_impl,
)
from pheroos.governance._commit_state.liveness_input import (
    CommitLivenessInputRequest,
    commit_liveness_input_payload_impl,
    commit_liveness_input_was_issued_impl,
    issue_commit_liveness_input_impl,
)
from pheroos.governance._commit_state.liveness_reduction import (
    _progress_phase,
    _progress_requirements,
    _require_live_authority_and_open_window,
    finality_satisfied_impl,
    progress_from_liveness_impl,
    reduce_commit_liveness_impl,
)
from pheroos.governance._commit_state.records import (
    _CommitReplayCursor,
    _CommitWindowCursor,
    _validate_replay_receipt,
)
from pheroos.governance._commit_state.replay import (
    _require_commit_replay_cursor,
)
from pheroos.governance._commit_state.window import (
    _cached_commit_window_epoch_restart,
    _cached_commit_window_transition,
    _commit_window_epoch_restart_inputs,
    _commit_window_transition_inputs,
    _require_commit_window_transition_cursor,
    _validated_commit_window_seal_receipt,
    commit_window_ready,
    commit_window_seal_payload,
    commit_window_state_fingerprint,
    initialize_commit_window_state,
)
from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.commit_state import (
    CommitFinalityStatus,
    ReplayNamespace,
    ReplayReceipt,
    commit_liveness_input_is_authoritative,
    commit_replay_state_is_authoritative,
    initialize_commit_replay_state,
    record_commit_replay_receipts,
    replay_receipt_fingerprint,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import CommitAssurance
from pheroos.protocol.commit_wire import commit_policy_fingerprint
from tests.governance.test_commit_engine import _fingerprint
from tests.governance.test_commit_liveness import (
    _liveness,
    _local_receipt,
    _one_ready_step,
    _stable_step,
    _verified_local_finality,
)
from tests.governance.test_commit_window import (
    _assessment,
    _epoch_threshold,
    _receipt,
    _replay,
    _scenario,
    _window,
)


def _mutated(value: Any, **changes: object) -> Any:
    clone = copy(value)
    for name, replacement in changes.items():
        object.__setattr__(clone, name, replacement)
    return clone


def _window_bindings(state: Any) -> dict[str, object]:
    return {
        "profile": state.profile,
        "assurance": state.assurance,
        "manifest_root": state.manifest_root,
        "commit_policy_root": state.commit_policy_root,
        "protocol_id": state.protocol_id,
        "run_id": state.run_id,
        "target": state.target,
        "epoch": state.epoch,
    }


def _liveness_request(
    scenario: Any,
    base_assessment: Any,
    base_state: Any,
    **changes: object,
) -> CommitLivenessInputRequest:
    request = CommitLivenessInputRequest(
        state=base_state,
        assessment=base_assessment,
        replay_state=scenario.replay_state,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        support_replay_state=scenario.support_replay_state,
        commit_policy=scenario.policy,
        previous_progress=None,
        current_step=base_state.last_evaluated_step,
        finality_status=CommitFinalityStatus.NOT_REQUIRED,
        finality_verification=None,
        certificate_ref="",
        invalid_reason_codes=(),
        safety_violation_reason_codes=(),
        blocked_reason_codes=(),
        finality_reason_codes=(),
        next_required_inputs=(),
        input_id=f"liveness:legacy-totality:{scenario.run_id}",
        issuer_id="governance:liveness",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:test:legacy-totality:{scenario.run_id}",
        trace_event_id=f"trace:legacy-totality:{scenario.run_id}",
    )
    return replace(request, **changes)


@pytest.fixture(scope="module")
def ready_case() -> tuple[Any, Any, Any, Any]:
    scenario, assessment, state = _one_ready_step()
    value = _liveness(
        state,
        scenario,
        assessment=assessment,
        current_step=state.last_evaluated_step,
    )
    return scenario, assessment, state, value


def test_assessment_lineage_contract_rejects_partial_and_orphaned_roots(
    ready_case: tuple[Any, Any, Any, Any],
) -> None:
    _, _, _, value = ready_case
    partial = _mutated(value, candidate_evidence_root="")
    with pytest.raises(GovernanceError, match="candidate lineage roots"):
        _validate_assessment_lineage_roots(
            partial,
            has_assessment=True,
            field_name="commit liveness",
        )
    with pytest.raises(GovernanceError, match="without an assessment"):
        _validate_assessment_lineage_roots(
            value,
            has_assessment=False,
            field_name="commit liveness",
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"sealed_window": 1}, "must be boolean"),
        (
            {
                "sealed_window": True,
                "seal_ref": _fingerprint("future-seal"),
                "sealed_at_step": 10,
            },
            "from the future",
        ),
        ({"seal_ref": _fingerprint("orphaned-seal")}, "carries seal lineage"),
        (
            {
                "sealed_window": True,
                "seal_ref": _fingerprint("predecessor-seal"),
                "previous_progress_ref": _fingerprint("predecessor"),
            },
            "predecessor requires",
        ),
        (
            {
                "sealed_window": True,
                "seal_ref": _fingerprint("sequence-seal"),
                "heartbeat_sequence": 1,
            },
            "initial heartbeat sequence",
        ),
    ),
)
def test_heartbeat_lineage_contract_totality(
    ready_case: tuple[Any, Any, Any, Any],
    changes: dict[str, object],
    message: str,
) -> None:
    _, _, _, value = ready_case
    candidate = _mutated(value, **changes)
    with pytest.raises(GovernanceError, match=message):
        _validate_sealed_heartbeat_lineage(
            candidate,
            field_name="commit liveness",
        )


def test_replay_contract_rejects_nonsequences_and_noncanonical_items() -> None:
    with pytest.raises(GovernanceError, match="must be a sequence"):
        canonical_replay_receipts(
            "receipt",
            receipt_type=ReplayReceipt,
            validate_receipt=_validate_replay_receipt,
            receipt_fingerprint=replay_receipt_fingerprint,
        )
    with pytest.raises(GovernanceError, match="non-canonical"):
        canonical_replay_receipts(
            (object(),),
            receipt_type=ReplayReceipt,
            validate_receipt=_validate_replay_receipt,
            receipt_fingerprint=replay_receipt_fingerprint,
        )


def test_replay_contract_deduplicates_and_rejects_safety_collisions() -> None:
    first = _receipt(
        ReplayNamespace.OBSERVATION,
        "observation:totality:first",
        "nonce:totality:shared",
        _fingerprint("replay-totality:first"),
    )
    assert canonical_replay_receipts(
        (first, first),
        receipt_type=ReplayReceipt,
        validate_receipt=_validate_replay_receipt,
        receipt_fingerprint=replay_receipt_fingerprint,
    ) == (first,)

    collision = _receipt(
        ReplayNamespace.CHALLENGE,
        "challenge:totality:collision",
        first.nonce,
        _fingerprint("replay-totality:collision"),
    )
    with pytest.raises(GovernanceError, match="safety collision"):
        canonical_replay_receipts(
            (first, collision),
            receipt_type=ReplayReceipt,
            validate_receipt=_validate_replay_receipt,
            receipt_fingerprint=replay_receipt_fingerprint,
        )


def test_bound_policy_rejects_noncanonical_and_invalid_binding_types(
    ready_case: tuple[Any, Any, Any, Any],
) -> None:
    scenario, _, state, _ = ready_case
    bindings = _window_bindings(state)
    with pytest.raises(GovernanceError, match="canonical CollectiveCommitPolicy"):
        _validate_bound_commit_policy(
            cast(Any, object()),
            cast(Any, bindings),
        )
    invalid_assurance = {**bindings, "assurance": "evidence_bound"}
    with pytest.raises(GovernanceError, match="assurance binding is invalid"):
        _validate_bound_commit_policy(
            scenario.policy,
            cast(Any, invalid_assurance),
        )
    with pytest.raises(GovernanceError, match="assurance is invalid"):
        _validate_commit_binding_values(
            profile=state.profile,
            assurance=cast(Any, "evidence_bound"),
            manifest_root=state.manifest_root,
            commit_policy_root=state.commit_policy_root,
            protocol_id=state.protocol_id,
            run_id=state.run_id,
            target=state.target,
            epoch=state.epoch,
            field_name="commit totality",
        )


@pytest.mark.parametrize(
    ("policy_change", "binding_change", "message"),
    (
        ({"policy_version": "unsupported"}, {}, "version or model"),
        ({"assurance": CommitAssurance.ADVISORY.value}, {}, "assurance binding"),
        ({"target": "decision:other"}, {}, "target binding"),
        ({}, {"commit_policy_root": _fingerprint("wrong-policy")}, "root binding"),
    ),
)
def test_bound_policy_identity_totality(
    ready_case: tuple[Any, Any, Any, Any],
    policy_change: dict[str, object],
    binding_change: dict[str, object],
    message: str,
) -> None:
    scenario, _, state, _ = ready_case
    policy = replace(scenario.policy, **policy_change)
    bindings = {**_window_bindings(state), **binding_change}
    with pytest.raises(GovernanceError, match=message):
        _validate_bound_commit_policy(policy, cast(Any, bindings))


def test_bound_policy_reports_declared_policy_diagnostics(
    ready_case: tuple[Any, Any, Any, Any],
) -> None:
    scenario, _, state, _ = ready_case
    invalid_window = replace(
        scenario.policy.commit_window,
        minimum_stability_steps=0,
    )
    invalid_policy = replace(scenario.policy, commit_window=invalid_window)
    bindings = _window_bindings(state)
    bindings["commit_policy_root"] = commit_policy_fingerprint(
        invalid_policy,
        profile=state.profile,
    )
    with pytest.raises(GovernanceError, match="policy is invalid"):
        _validate_bound_commit_policy(invalid_policy, cast(Any, bindings))


def test_threshold_contract_rejects_non_authoritative_snapshot() -> None:
    with pytest.raises(GovernanceError, match="authoritative threshold snapshot"):
        _threshold_snapshot_bindings(object())


@pytest.mark.parametrize(
    ("kind", "message"),
    (
        ("binding", "profile binding mismatch"),
        ("risk", "risk assessment binding mismatch"),
        ("freshness", "snapshot is not fresh"),
        ("band", "risk band is not declared"),
        ("value", "values do not match"),
        ("labels", "required_challenge_categories does not match"),
    ),
)
def test_threshold_snapshot_validation_totality(
    ready_case: tuple[Any, Any, Any, Any],
    kind: str,
    message: str,
) -> None:
    scenario, _, state, _ = ready_case
    bindings = _window_bindings(state)
    policy = scenario.policy
    risk_root = state.risk_assessment_root
    current_step = state.last_evaluated_step
    if kind == "binding":
        bindings["profile"] = "pheroos-other-profile-v1"
    elif kind == "risk":
        risk_root = _fingerprint("wrong-risk")
    elif kind == "freshness":
        current_step = scenario.threshold.expires_at_step
    elif kind == "band":
        policy = replace(policy, risk_bands={})
    elif kind == "value":
        band = policy.risk_bands[scenario.threshold.risk_band.value]
        policy = replace(
            policy,
            risk_bands={
                **policy.risk_bands,
                scenario.threshold.risk_band.value: replace(
                    band,
                    minimum_margin=band.minimum_margin + 1,
                ),
            },
        )
    else:
        band = policy.risk_bands[scenario.threshold.risk_band.value]
        policy = replace(
            policy,
            risk_bands={
                **policy.risk_bands,
                scenario.threshold.risk_band.value: replace(
                    band,
                    required_challenge_categories=("totality:other",),
                ),
            },
        )
    with pytest.raises(GovernanceError, match=message):
        _validate_window_threshold_snapshot(
            scenario.threshold,
            commit_policy=policy,
            bindings=cast(Any, bindings),
            risk_assessment_root=risk_root,
            current_step=current_step,
        )


def test_window_chain_scope_rejects_identity_and_epoch_substitution(
    ready_case: tuple[Any, Any, Any, Any],
) -> None:
    _, _, state, _ = ready_case
    bindings = _window_bindings(state)
    with pytest.raises(GovernanceError, match="profile scope mismatch"):
        _validate_window_chain_scope(
            state,
            cast(Any, {**bindings, "profile": "pheroos-other-profile-v1"}),
        )
    with pytest.raises(GovernanceError, match="epoch scope mismatch"):
        _validate_window_chain_scope(
            state,
            cast(Any, {**bindings, "epoch": state.epoch + 1}),
        )


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    (
        ("profile", "pheroos-other-profile-v1", "profile binding mismatch"),
        ("last_assessment_ref", _fingerprint("other-assessment"), "assessment_ref"),
        ("last_evaluated_step", 0, "step is not current"),
    ),
)
def test_assessment_window_head_contract_totality(
    ready_case: tuple[Any, Any, Any, Any],
    field: str,
    replacement: object,
    message: str,
) -> None:
    _, assessment, state, _ = ready_case
    view = _authoritative_commit_assessment_view(assessment)
    with pytest.raises(GovernanceError, match=message):
        _validate_assessment_matches_window_head(
            _mutated(state, **{field: replacement}),
            view,
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"window_state_ref": _fingerprint("other-window")}, "window head"),
        ({"current_step": 0}, "predates"),
        ({"deadline_reached": True}, "deadline state"),
        ({"assessment_ref": _fingerprint("other-assessment")}, "assessment head"),
        ({"context_ref": _fingerprint("other-context")}, "context head"),
        ({"assessment_status": "blocked"}, "status"),
        ({"assessment_reason_codes": ("other",)}, "reasons"),
        ({"risk_assessment_root": _fingerprint("other-risk")}, "risk_assessment_root"),
        ({"leader_candidate_id": "candidate:other"}, "leader candidate"),
        ({"sealed_window": True}, "sealed-window"),
        ({"heartbeat_continuous": False}, "heartbeat loss"),
    ),
)
def test_liveness_window_binding_totality(
    ready_case: tuple[Any, Any, Any, Any],
    changes: dict[str, object],
    message: str,
) -> None:
    _, _, state, value = ready_case
    with pytest.raises(GovernanceError, match=message):
        validate_liveness_input_matches_window_impl(
            state,
            _mutated(value, **changes),
        )


@pytest.mark.parametrize("head_index", (1, 5, 6))
def test_current_chain_heads_reject_each_stale_authority(
    ready_case: tuple[Any, Any, Any, Any],
    head_index: int,
) -> None:
    _, _, state, value = ready_case
    heads = value._authority_heads
    message = (
        "support replay head changed" if head_index == 6 else "authority head changed"
    )
    with pytest.raises(GovernanceError, match=message):
        _validate_current_chain_heads(
            state,
            risk_state=copy(heads[1]) if head_index == 1 else heads[1],
            membership_state=copy(heads[5]) if head_index == 5 else heads[5],
            support_state=copy(heads[6]) if head_index == 6 else heads[6],
        )


def test_liveness_authority_requires_bound_policy(
    ready_case: tuple[Any, Any, Any, Any],
) -> None:
    _, _, state, _ = ready_case
    with pytest.raises(GovernanceError, match="requires the bound commit policy"):
        _require_bound_policy(state, None)


def test_bound_snapshot_roots_reject_risk_and_membership_substitution(
    ready_case: tuple[Any, Any, Any, Any],
) -> None:
    _, _, state, value = ready_case
    heads = value._authority_heads
    with pytest.raises(GovernanceError, match="risk or threshold root"):
        _validate_bound_snapshot_roots(
            _mutated(state, risk_assessment_root=_fingerprint("other-risk")),
            risk_assessment=heads[2],
            threshold_snapshot=heads[3],
            membership_snapshot=heads[4],
        )
    with pytest.raises(GovernanceError, match="membership root"):
        _validate_bound_snapshot_roots(
            _mutated(state, membership_root=_fingerprint("other-membership")),
            risk_assessment=heads[2],
            threshold_snapshot=heads[3],
            membership_snapshot=heads[4],
        )


def test_fresh_snapshot_checks_reject_staleness_and_rebinding(
    ready_case: tuple[Any, Any, Any, Any],
) -> None:
    scenario, _, state, value = ready_case
    heads = value._authority_heads
    with pytest.raises(GovernanceError, match="risk assessment or threshold is stale"):
        _validate_fresh_risk_snapshot(
            state,
            risk_state=heads[1],
            risk_assessment=heads[2],
            threshold_snapshot=heads[3],
            commit_policy=scenario.policy,
            current_step=10_000,
        )
    with pytest.raises(GovernanceError, match="risk or threshold root changed"):
        _validate_fresh_risk_snapshot(
            _mutated(state, risk_assessment_root=_fingerprint("changed-risk")),
            risk_state=heads[1],
            risk_assessment=heads[2],
            threshold_snapshot=heads[3],
            commit_policy=scenario.policy,
            current_step=state.last_evaluated_step,
        )
    with pytest.raises(GovernanceError, match="snapshot is stale"):
        _validate_fresh_membership_snapshot(
            state,
            membership_snapshot=heads[4],
            membership_state=heads[5],
            current_step=10_000,
        )
    with pytest.raises(GovernanceError, match="membership root changed"):
        _validate_fresh_membership_snapshot(
            _mutated(state, membership_root=_fingerprint("changed-membership")),
            membership_snapshot=heads[4],
            membership_state=heads[5],
            current_step=state.last_evaluated_step,
        )


def test_liveness_authority_currentness_is_total_over_malformed_heads(
    ready_case: tuple[Any, Any, Any, Any],
) -> None:
    _, _, _, value = ready_case
    malformed = _mutated(value)
    object.__delattr__(malformed, "_authority_heads")
    assert not liveness_authority_heads_are_current_impl(malformed)
    assert not _liveness_authority_heads_are_current(
        _mutated(value, _authority_heads=(object(),))
    )


def test_assessment_currentness_rejects_base_and_snapshot_head_changes(
    ready_case: tuple[Any, Any, Any, Any],
) -> None:
    _, _, _, value = ready_case
    heads = value._authority_heads
    stale_base = (*heads[:1], copy(heads[1]), *heads[2:])
    assert not _assessment_heads_are_current(value, stale_base)
    changed_roots = _mutated(
        value,
        risk_assessment_root=_fingerprint("assessment-currentness:risk"),
    )
    assert not _assessment_heads_are_current(changed_roots, heads)


def test_replay_initialization_and_transition_totality() -> None:
    with pytest.raises(GovernanceError, match="governance authority"):
        initialize_commit_replay_state(
            profile="pheroos-commit-integrity-v1",
            assurance=CommitAssurance.EVIDENCE_BOUND,
            manifest_root=_fingerprint("manifest:authority"),
            commit_policy_root=_fingerprint("policy:authority"),
            protocol_id="protocol:totality",
            run_id="run:totality:authority",
            current_step=0,
            issuer_id="governance:replay",
            authority=AuthorityLevel.AGENT,
            provenance="urn:test:totality",
            trace_event_id="trace:totality:authority",
        )
    with pytest.raises(GovernanceError, match="assurance is invalid"):
        initialize_commit_replay_state(
            profile="pheroos-commit-integrity-v1",
            assurance=cast(Any, "evidence_bound"),
            manifest_root=_fingerprint("manifest:assurance"),
            commit_policy_root=_fingerprint("policy:assurance"),
            protocol_id="protocol:totality",
            run_id="run:totality:assurance",
            current_step=0,
            issuer_id="governance:replay",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="urn:test:totality",
            trace_event_id="trace:totality:assurance",
        )

    state = _replay(run_id="run:totality:replay-transition")
    with pytest.raises(GovernanceError, match="not governance-issued"):
        record_commit_replay_receipts(
            replace(state),
            current_step=1,
            receipts=(),
        )
    receipt = _receipt(
        ReplayNamespace.OBSERVATION,
        "observation:totality:backwards",
        "nonce:totality:backwards",
        _fingerprint("payload:totality:backwards"),
    )
    advanced = record_commit_replay_receipts(
        state,
        current_step=1,
        receipts=(receipt,),
    )
    with pytest.raises(GovernanceError, match="move backwards"):
        record_commit_replay_receipts(
            advanced,
            current_step=0,
            receipts=(),
        )
    assert (
        record_commit_replay_receipts(advanced, current_step=1, receipts=()) is advanced
    )


def test_replay_registry_rejects_base_fork_and_unavailable_head() -> None:
    run_id = "run:totality:replay-registry"
    state = _replay(run_id=run_id)
    with pytest.raises(GovernanceError, match="different base"):
        initialize_commit_replay_state(
            profile=state.profile,
            assurance=state.assurance,
            manifest_root=state.manifest_root,
            commit_policy_root=state.commit_policy_root,
            protocol_id=state.protocol_id,
            run_id=state.run_id,
            current_step=state.current_step,
            issuer_id=state.issuer_id,
            authority=state.authority,
            provenance="urn:test:totality:different-base",
            trace_event_id=state.trace_event_id,
        )

    unavailable_run = "run:totality:replay-unavailable"
    unavailable = _replay(run_id=unavailable_run)
    unavailable._cursor.current_state = replace(unavailable)
    with pytest.raises(GovernanceError, match="current state is unavailable"):
        _replay(run_id=unavailable_run)


def test_replay_transition_cache_and_cursor_guard() -> None:
    state = _replay(run_id="run:totality:replay-cache")
    receipt = _receipt(
        ReplayNamespace.OBSERVATION,
        "observation:totality:cache",
        "nonce:totality:cache",
        _fingerprint("payload:totality:cache"),
    )
    first = record_commit_replay_receipts(
        state,
        current_step=1,
        receipts=(receipt,),
    )
    assert (
        record_commit_replay_receipts(
            state,
            current_step=1,
            receipts=(receipt,),
        )
        is first
    )
    assert commit_replay_state_is_authoritative(first)

    broken = _mutated(first, _cursor=object())
    with pytest.raises(GovernanceError, match="cursor is invalid"):
        _require_commit_replay_cursor(broken)


def test_isolated_cursor_constructors_support_totality_checks() -> None:
    replay_cursor = _CommitReplayCursor(
        authority_key="authority:replay:totality",
        base_fingerprint=_fingerprint("base:replay:totality"),
    )
    window_cursor = _CommitWindowCursor(
        authority_key="authority:window:totality",
        base_fingerprint=_fingerprint("base:window:totality"),
        chain_id=_fingerprint("chain:window:totality"),
    )
    assert replay_cursor.current_state is None
    assert window_cursor.current_state is None
    assert window_cursor.terminal_result is None


def test_normalized_bindings_accept_valid_legacy_authority(
    ready_case: tuple[Any, Any, Any, Any],
) -> None:
    _, _, state, _ = ready_case
    assert _normalized_window_bindings(
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        field_name="commit totality",
    ) == _window_bindings(state)


def test_liveness_issuance_rejects_noncurrent_authority_and_old_steps() -> None:
    scenario, assessment, state = _one_ready_step()
    with pytest.raises(GovernanceError, match="current window head"):
        issue_commit_liveness_input_impl(
            _liveness_request(
                scenario,
                assessment,
                state,
                state=replace(state),
            )
        )
    with pytest.raises(GovernanceError, match="governance authority"):
        issue_commit_liveness_input_impl(
            _liveness_request(
                scenario,
                assessment,
                state,
                authority=AuthorityLevel.AGENT,
            )
        )
    with pytest.raises(GovernanceError, match="precede the window head"):
        issue_commit_liveness_input_impl(
            _liveness_request(
                scenario,
                assessment,
                state,
                current_step=state.last_evaluated_step - 1,
            )
        )


def test_liveness_heartbeat_guards_cover_unsealed_and_sealed_paths() -> None:
    scenario, assessment, state = _one_ready_step()
    with pytest.raises(GovernanceError, match="initial liveness step"):
        issue_commit_liveness_input_impl(
            _liveness_request(
                scenario,
                assessment,
                state,
                previous_progress=cast(Any, object()),
            )
        )
    with pytest.raises(GovernanceError, match="unsealed liveness"):
        issue_commit_liveness_input_impl(
            _liveness_request(
                scenario,
                assessment,
                state,
                current_step=state.last_evaluated_step + 1,
                previous_progress=cast(Any, object()),
            )
        )

    stable_scenario, stable_assessment, stable = _stable_step()
    with pytest.raises(GovernanceError, match="same-step local receipt seal"):
        issue_commit_liveness_input_impl(
            _liveness_request(
                stable_scenario,
                stable_assessment,
                stable,
                current_step=stable.last_evaluated_step + 1,
            )
        )
    _local_receipt(
        stable,
        stable_scenario,
        stable_assessment,
        current_step=stable.last_evaluated_step,
    )
    with pytest.raises(GovernanceError, match="authoritative previous heartbeat"):
        issue_commit_liveness_input_impl(
            _liveness_request(
                stable_scenario,
                stable_assessment,
                stable,
                current_step=stable.last_evaluated_step + 1,
            )
        )


def test_liveness_rejects_unissued_previous_heartbeat() -> None:
    source_scenario, source_assessment, source_state = _one_ready_step()
    source_input = _liveness(
        source_state,
        source_scenario,
        assessment=source_assessment,
        current_step=source_state.last_evaluated_step,
    )
    progress = reduce_commit_liveness_impl(
        source_state,
        commit_policy=source_scenario.policy,
        liveness_input=source_input,
    )

    scenario, assessment, state = _stable_step()
    _local_receipt(
        state,
        scenario,
        assessment,
        current_step=state.last_evaluated_step,
    )
    with pytest.raises(GovernanceError, match="not authoritative"):
        issue_commit_liveness_input_impl(
            _liveness_request(
                scenario,
                assessment,
                state,
                current_step=state.last_evaluated_step + 1,
                previous_progress=replace(progress),
            )
        )


def test_liveness_replay_assessment_and_finality_guards() -> None:
    scenario, assessment, state = _one_ready_step()
    with pytest.raises(GovernanceError, match="replay head is not authoritative"):
        issue_commit_liveness_input_impl(
            _liveness_request(
                scenario,
                assessment,
                state,
                replay_state=replace(scenario.replay_state),
            )
        )
    with pytest.raises(GovernanceError, match="window head assessment"):
        issue_commit_liveness_input_impl(
            _liveness_request(scenario, assessment, state, assessment=None)
        )
    with pytest.raises(GovernanceError, match="finality status is invalid"):
        issue_commit_liveness_input_impl(
            _liveness_request(
                scenario,
                assessment,
                state,
                finality_status=cast(Any, "not-required"),
            )
        )
    with pytest.raises(GovernanceError, match="non-verified finality"):
        issue_commit_liveness_input_impl(
            _liveness_request(
                scenario,
                assessment,
                state,
                finality_verification=cast(Any, object()),
            )
        )
    with pytest.raises(GovernanceError, match="bare certificate reference"):
        issue_commit_liveness_input_impl(
            _liveness_request(
                scenario,
                assessment,
                state,
                certificate_ref=_fingerprint("bare-certificate"),
            )
        )
    with pytest.raises(GovernanceError, match="authoritative typed verification"):
        issue_commit_liveness_input_impl(
            _liveness_request(
                scenario,
                assessment,
                state,
                finality_status=CommitFinalityStatus.VERIFIED,
                finality_verification=cast(Any, object()),
            )
        )


def test_liveness_input_cache_and_record_totality() -> None:
    scenario, assessment, state = _one_ready_step()
    request = _liveness_request(scenario, assessment, state)
    value = issue_commit_liveness_input_impl(request)
    assert issue_commit_liveness_input_impl(request) is value
    with pytest.raises(GovernanceError, match="input id would fork"):
        issue_commit_liveness_input_impl(
            replace(request, trace_event_id=f"{request.trace_event_id}:fork")
        )
    assert not commit_liveness_input_was_issued_impl(object())
    assert not commit_liveness_input_was_issued_impl(_mutated(value, input_id=""))
    assert not commit_liveness_input_is_authoritative(object())
    with pytest.raises(GovernanceError, match="canonical record"):
        commit_liveness_input_payload_impl(cast(Any, object()))


def test_verified_finality_and_seal_lineage_validators_are_total() -> None:
    scenario, assessment, state = _stable_step()
    verification = _verified_local_finality(
        state,
        scenario,
        assessment,
        current_step=state.last_evaluated_step,
    )
    seal = state._cursor.current_seal
    assert seal is not None

    with pytest.raises(GovernanceError, match="current receipt-backed seal"):
        validate_finality_verification_matches_window_impl(
            verification,
            state=state,
            seal=None,
            current_step=state.last_evaluated_step,
        )
    deadline = min(state.absolute_deadline_step, state.absolute_run_deadline_step)
    with pytest.raises(GovernanceError, match="at its deadline"):
        validate_finality_verification_matches_window_impl(
            replace(verification, verified_at_step=deadline),
            state=state,
            seal=seal,
            current_step=deadline,
        )
    with pytest.raises(GovernanceError, match="binding mismatch"):
        validate_finality_verification_matches_window_impl(
            replace(verification, run_id=f"{verification.run_id}:other"),
            state=state,
            seal=seal,
            current_step=state.last_evaluated_step,
        )
    with pytest.raises(GovernanceError, match="lineage mismatch"):
        validate_finality_verification_matches_window_impl(
            replace(verification, candidate_id="candidate:other"),
            state=state,
            seal=seal,
            current_step=state.last_evaluated_step,
        )

    value = _liveness(
        state,
        scenario,
        assessment=assessment,
        current_step=state.last_evaluated_step,
        finality_status=CommitFinalityStatus.VERIFIED,
        finality_verification=verification,
    )
    with pytest.raises(GovernanceError, match="seal lineage mismatch"):
        _validate_seal_lineage(state, _mutated(value, seal_ref="sha256:" + "0" * 64))
    assert not liveness_authority_heads_are_current_impl(cast(Any, object()))


def test_verified_finality_rejects_bare_certificate_reference() -> None:
    scenario, assessment, state = _stable_step()
    verification = _verified_local_finality(
        state,
        scenario,
        assessment,
        current_step=state.last_evaluated_step,
    )
    with pytest.raises(GovernanceError, match="bare certificate reference"):
        issue_commit_liveness_input_impl(
            _liveness_request(
                scenario,
                assessment,
                state,
                finality_status=CommitFinalityStatus.VERIFIED,
                finality_verification=verification,
                certificate_ref=verification.certificate_ref,
            )
        )


def test_window_initialization_and_transition_input_guards() -> None:
    scenario = _scenario()
    state = _window(scenario)
    with pytest.raises(GovernanceError, match="governance authority"):
        initialize_commit_window_state(
            commit_policy=scenario.policy,
            profile=state.profile,
            assurance=state.assurance,
            manifest_root=state.manifest_root,
            commit_policy_root=state.commit_policy_root,
            protocol_id=state.protocol_id,
            run_id=f"{state.run_id}:agent",
            target=state.target,
            epoch=state.epoch,
            risk_assessment_root=state.risk_assessment_root,
            membership_root=state.membership_root,
            threshold_snapshot=scenario.threshold,
            current_step=state.last_evaluated_step,
            issuer_id=state.issuer_id,
            authority=AuthorityLevel.AGENT,
            provenance=state.provenance,
            trace_event_id=state.trace_event_id,
        )

    assessment = _assessment(scenario, step=state.last_evaluated_step + 1)
    with pytest.raises(GovernanceError, match="not governance-issued"):
        _commit_window_transition_inputs(
            replace(state),
            assessment=assessment,
            commit_policy=scenario.policy,
            threshold_snapshot=scenario.threshold,
            current_step=state.last_evaluated_step + 1,
        )
    with pytest.raises(GovernanceError, match="advance monotonically"):
        _commit_window_transition_inputs(
            state,
            assessment=assessment,
            commit_policy=scenario.policy,
            threshold_snapshot=scenario.threshold,
            current_step=state.last_evaluated_step,
        )
    with pytest.raises(GovernanceError, match="at or after its deadline"):
        _commit_window_transition_inputs(
            state,
            assessment=assessment,
            commit_policy=scenario.policy,
            threshold_snapshot=scenario.threshold,
            current_step=state.absolute_deadline_step,
        )


def test_window_transition_cursor_and_cache_guards() -> None:
    scenario = _scenario()
    state = _window(scenario)
    with pytest.raises(GovernanceError, match="cursor is invalid"):
        _require_commit_window_transition_cursor(
            _mutated(state, _cursor=object()),
            explicit_unseal=False,
        )
    with pytest.raises(GovernanceError, match="requires a current sealed window"):
        _require_commit_window_transition_cursor(state, explicit_unseal=True)

    parent = commit_window_state_fingerprint(state)
    with pytest.raises(GovernanceError, match="lost its current seal authority"):
        _cached_commit_window_transition(
            state._cursor,
            parent_fingerprint=parent,
            request_fingerprint=_fingerprint("window:unsealed-request"),
            explicit_unseal=True,
        )

    terminal_cursor = _CommitWindowCursor(
        authority_key="authority:window:terminal",
        base_fingerprint=_fingerprint("base:window:terminal"),
        chain_id=_fingerprint("chain:window:terminal"),
    )
    terminal_cursor.terminal_result = object()
    with pytest.raises(GovernanceError, match="already terminal"):
        _cached_commit_window_transition(
            terminal_cursor,
            parent_fingerprint=_fingerprint("window:terminal-parent"),
            request_fingerprint=_fingerprint("window:terminal-request"),
            explicit_unseal=False,
        )

    stable_scenario, stable_assessment, stable = _stable_step()
    _local_receipt(
        stable,
        stable_scenario,
        stable_assessment,
        current_step=stable.last_evaluated_step,
    )
    with pytest.raises(GovernanceError, match="requires an explicit reset"):
        _cached_commit_window_transition(
            stable._cursor,
            parent_fingerprint=commit_window_state_fingerprint(stable),
            request_fingerprint=_fingerprint("window:sealed-request"),
            explicit_unseal=False,
        )


def test_window_epoch_restart_input_and_cache_guards() -> None:
    scenario = _scenario()
    state = _window(scenario)
    with pytest.raises(GovernanceError, match="not governance-issued"):
        _commit_window_epoch_restart_inputs(
            replace(state),
            new_epoch=state.epoch + 1,
            current_step=state.last_evaluated_step + 1,
            commit_policy=scenario.policy,
            threshold_snapshot=scenario.threshold,
            membership_root=state.membership_root,
        )
    with pytest.raises(GovernanceError, match="advance the epoch"):
        _commit_window_epoch_restart_inputs(
            state,
            new_epoch=state.epoch,
            current_step=state.last_evaluated_step + 1,
            commit_policy=scenario.policy,
            threshold_snapshot=scenario.threshold,
            membership_root=state.membership_root,
        )
    with pytest.raises(GovernanceError, match="step must advance"):
        _commit_window_epoch_restart_inputs(
            state,
            new_epoch=state.epoch + 1,
            current_step=state.last_evaluated_step,
            commit_policy=scenario.policy,
            threshold_snapshot=scenario.threshold,
            membership_root=state.membership_root,
        )
    with pytest.raises(GovernanceError, match="cannot extend"):
        _commit_window_epoch_restart_inputs(
            state,
            new_epoch=state.epoch + 1,
            current_step=state.absolute_deadline_step,
            commit_policy=scenario.policy,
            threshold_snapshot=scenario.threshold,
            membership_root=state.membership_root,
        )

    mismatched = _epoch_threshold(
        scenario,
        epoch=state.epoch + 2,
        step=state.last_evaluated_step + 1,
    )
    with pytest.raises(GovernanceError, match="threshold epoch mismatch"):
        _commit_window_epoch_restart_inputs(
            state,
            new_epoch=state.epoch + 1,
            current_step=state.last_evaluated_step + 1,
            commit_policy=scenario.policy,
            threshold_snapshot=mismatched,
            membership_root=state.membership_root,
        )

    next_threshold = _epoch_threshold(
        scenario,
        epoch=state.epoch + 1,
        step=state.last_evaluated_step + 1,
    )
    inputs = _commit_window_epoch_restart_inputs(
        state,
        new_epoch=state.epoch + 1,
        current_step=state.last_evaluated_step + 1,
        commit_policy=scenario.policy,
        threshold_snapshot=next_threshold,
        membership_root=state.membership_root,
    )
    state._cursor.terminal_result = object()
    with pytest.raises(GovernanceError, match="already terminal"):
        _cached_commit_window_epoch_restart(state._cursor, inputs=inputs)


def test_window_readiness_and_seal_record_guards() -> None:
    scenario, assessment, state = _stable_step()
    assert not commit_window_ready(replace(state))
    receipt = _local_receipt(
        state,
        scenario,
        assessment,
        current_step=state.last_evaluated_step,
    )
    with pytest.raises(GovernanceError, match="current window head"):
        _validated_commit_window_seal_receipt(replace(state), receipt)
    with pytest.raises(GovernanceError, match="authoritative receipt"):
        _validated_commit_window_seal_receipt(state, object())
    with pytest.raises(GovernanceError, match="authoritative receipt"):
        _validated_commit_window_seal_receipt(state, replace(receipt))

    unready_scenario, unready_assessment, unready = _one_ready_step()
    with pytest.raises(GovernanceError, match="stable ready window"):
        _validated_commit_window_seal_receipt(unready, object())

    other_scenario, other_assessment, other = _stable_step()
    other_receipt = _local_receipt(
        other,
        other_scenario,
        other_assessment,
        current_step=other.last_evaluated_step,
    )
    with pytest.raises(GovernanceError, match="mismatch"):
        _validated_commit_window_seal_receipt(state, other_receipt)
    with pytest.raises(GovernanceError, match="canonical record"):
        commit_window_seal_payload(cast(Any, object()))


def test_reduction_entry_and_authority_guards(
    ready_case: tuple[Any, Any, Any, Any],
) -> None:
    scenario, _, state, value = ready_case
    with pytest.raises(GovernanceError, match="current window head"):
        reduce_commit_liveness_impl(
            replace(state),
            commit_policy=scenario.policy,
            liveness_input=value,
        )
    with pytest.raises(GovernanceError, match="not governance-issued"):
        reduce_commit_liveness_impl(
            state,
            commit_policy=scenario.policy,
            liveness_input=replace(value),
        )
    with pytest.raises(GovernanceError, match="no longer current"):
        _require_live_authority_and_open_window(
            _mutated(value, _authority_heads=(object(),)),
            state._cursor,
        )
    terminal_cursor = _CommitWindowCursor(
        authority_key="authority:reduction:terminal",
        base_fingerprint=_fingerprint("base:reduction:terminal"),
        chain_id=_fingerprint("chain:reduction:terminal"),
    )
    terminal_cursor.terminal_result = object()
    with pytest.raises(GovernanceError, match="terminal outcome"):
        _require_live_authority_and_open_window(value, terminal_cursor)


def test_reduction_progress_helpers_cover_each_phase_and_requirement(
    ready_case: tuple[Any, Any, Any, Any],
) -> None:
    _, _, state, value = ready_case
    assert not finality_satisfied_impl(
        _mutated(value, assurance=CommitAssurance.ADVISORY)
    )
    with pytest.raises(GovernanceError, match="cannot survive a deadline"):
        progress_from_liveness_impl(
            state,
            _mutated(value, current_step=state.absolute_deadline_step),
        )
    assert _progress_phase(state, _mutated(value, assessment_ref="")).value == "search"
    assert (
        _progress_phase(_mutated(state, last_ready=False), value).value == "deliberate"
    )

    requirements, _ = _progress_requirements(
        state,
        _mutated(value, assessment_ref=""),
    )
    assert "commit_assessment" in requirements
    requirements, _ = _progress_requirements(
        _mutated(state, last_ready=False),
        _mutated(value, assessment_reason_codes=()),
    )
    assert requirements == {"next_commit_assessment"}

    scenario, assessment, stable = _stable_step()
    unsealed = _liveness(
        stable,
        scenario,
        assessment=assessment,
        current_step=stable.last_evaluated_step,
    )
    requirements, _ = _progress_requirements(stable, unsealed)
    assert "local_commit_receipt" in requirements
    _local_receipt(
        stable,
        scenario,
        assessment,
        current_step=stable.last_evaluated_step,
    )
    sealed = _liveness(
        stable,
        scenario,
        assessment=assessment,
        current_step=stable.last_evaluated_step,
    )
    requirements, _ = _progress_requirements(stable, sealed)
    assert "verified_finality" in requirements
