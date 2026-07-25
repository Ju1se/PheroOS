from __future__ import annotations

from dataclasses import FrozenInstanceError
import json

import pytest

from pheroos.governance.commit_numeric import (
    MAX_AUTHORITY_INTEGER,
    WEIGHT_SCALE,
    canonical_commit_payload,
    canonical_commit_set,
    checked_add,
    checked_multiply,
    checked_subtract,
    ceil_scaled_count,
    commit_payload_fingerprint,
    multiply_scaled,
    require_authority_integer,
    require_scaled_integer,
    scaled_ratio,
)
from pheroos.governance.commit_state import (
    AuthorityScope,
    CommitAssurance,
    DecisionOutcome,
    DecisionOutcomeKind,
    DecisionPhase,
    DecisionProgress,
    _issue_decision_outcome,
    _issue_decision_progress,
    decision_outcome_fingerprint,
    decision_outcome_is_authoritative,
    decision_progress_fingerprint,
    decision_progress_is_authoritative,
    select_terminal_outcome_kind,
)
from pheroos.governance.errors import GovernanceError


MANIFEST_ROOT = "sha256:" + ("1" * 64)
COMMIT_POLICY_ROOT = "sha256:" + ("2" * 64)
ASSESSMENT_REF = "sha256:" + ("3" * 64)
CERTIFICATE_REF = "sha256:" + ("4" * 64)
SEAL_REF = "sha256:" + ("b" * 64)


def root(marker: str) -> str:
    return "sha256:" + (marker * 64)


LINEAGE: dict[str, object] = {
    "minimum_stability_steps": 2,
    "context_ref": root("5"),
    "risk_assessment_root": root("6"),
    "risk_chain_state_root": root("7"),
    "risk_policy_root": root("8"),
    "membership_root": root("9"),
    "membership_snapshot_root": root("a"),
    "membership_epoch_state_root": root("b"),
    "threshold_root": root("c"),
    "replay_state_ref": root("d"),
    "replay_root": root("e"),
    "support_replay_state_root": root("f"),
    "support_replay_root": root("0"),
    "collective_evidence_root": root("1"),
    "collective_challenge_root": root("2"),
    "collective_lease_root": root("3"),
    "candidate_evidence_root": root("4"),
    "candidate_challenge_root": root("5"),
    "candidate_lease_root": root("6"),
    "stop_resolution_root": root("7"),
    "permission_root": root("8"),
    "window_state_ref": root("9"),
    "window_root": root("a"),
}


def progress(**overrides: object) -> DecisionProgress:
    values: dict[str, object] = {
        "phase": DecisionPhase.SEARCH,
        "profile": "pheroos-commit-integrity-v1",
        "assurance": CommitAssurance.EVIDENCE_BOUND,
        "manifest_root": MANIFEST_ROOT,
        "commit_policy_root": COMMIT_POLICY_ROOT,
        "protocol_id": "protocol:optimal",
        "run_id": "run:1",
        "target": "decision:collective",
        "epoch": 1,
        "current_step": 2,
        "absolute_deadline_step": 5,
        "absolute_run_deadline_step": 8,
        "remaining_reset_budget": 2,
        "remaining_epoch_restart_budget": 1,
        **LINEAGE,
        "assessment_ref": ASSESSMENT_REF,
        "sealed_window": False,
        "seal_ref": "",
        "sealed_at_step": 0,
        "heartbeat_continuous": True,
        "heartbeat_sequence": 0,
        "previous_progress_ref": "",
        "next_required_inputs": ("observation",),
        "unmet_gates": ("evidence",),
    }
    values.update(overrides)
    return DecisionProgress(**values)  # type: ignore[arg-type]


def outcome(**overrides: object) -> DecisionOutcome:
    values: dict[str, object] = {
        "kind": DecisionOutcomeKind.SAFE_FALLBACK,
        "profile": "pheroos-commit-integrity-v1",
        "assurance": CommitAssurance.EVIDENCE_BOUND,
        "manifest_root": MANIFEST_ROOT,
        "commit_policy_root": COMMIT_POLICY_ROOT,
        "protocol_id": "protocol:optimal",
        "run_id": "run:1",
        "target": "decision:collective",
        "epoch": 1,
        "current_step": 5,
        "absolute_deadline_step": 5,
        "absolute_run_deadline_step": 8,
        "authority_scope": AuthorityScope.NONE,
        "authoritative_commit": False,
        "epistemically_committed": False,
        **{
            name: value
            for name, value in LINEAGE.items()
            if name != "minimum_stability_steps"
        },
        "candidate_id": "candidate:safe",
        "assessment_ref": ASSESSMENT_REF,
        "sealed_window": False,
        "seal_ref": "",
        "sealed_at_step": 0,
        "heartbeat_continuous": True,
        "heartbeat_sequence": 0,
        "previous_progress_ref": "",
        "reason_codes": ("deadline_reached",),
    }
    values.update(overrides)
    if values["kind"] is DecisionOutcomeKind.EVIDENCE_COMMIT:
        values.update(
            {
                "sealed_window": overrides.get("sealed_window", True),
                "seal_ref": overrides.get("seal_ref", SEAL_REF),
                "sealed_at_step": overrides.get(
                    "sealed_at_step",
                    values["current_step"],
                ),
                "heartbeat_continuous": overrides.get(
                    "heartbeat_continuous",
                    True,
                ),
            }
        )
    return DecisionOutcome(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [True, 1.0, "1", -1])
def test_scaled_integer_rejects_non_integer_or_negative_values(value: object) -> None:
    with pytest.raises(GovernanceError):
        require_scaled_integer(value, "weight")


def test_fixed_point_reference_operations_are_integer_only() -> None:
    assert multiply_scaled(900_000, 800_000) == 720_000
    assert multiply_scaled(MAX_AUTHORITY_INTEGER, WEIGHT_SCALE) == (
        MAX_AUTHORITY_INTEGER
    )
    assert ceil_scaled_count(7, 500_000) == 4
    assert scaled_ratio(1, 4) == 250_000
    assert scaled_ratio(0, 0) == WEIGHT_SCALE
    assert checked_add(1, 2, -1) == 2
    assert checked_add(MAX_AUTHORITY_INTEGER, 1, -1) == MAX_AUTHORITY_INTEGER
    assert checked_add(MAX_AUTHORITY_INTEGER, -1, 1) == MAX_AUTHORITY_INTEGER
    assert (
        scaled_ratio(
            MAX_AUTHORITY_INTEGER,
            MAX_AUTHORITY_INTEGER * 2,
        )
        == 500_000
    )
    assert checked_multiply(-3, 2) == -6
    assert checked_subtract(1, 2) == -1
    assert require_authority_integer(-1, "net evidence", allow_negative=True) == -1
    with pytest.raises(GovernanceError, match="maximum"):
        require_scaled_integer(MAX_AUTHORITY_INTEGER + 1, "weight")
    with pytest.raises(GovernanceError, match="bound"):
        checked_add(MAX_AUTHORITY_INTEGER, 1)
    with pytest.raises(GovernanceError, match="bound"):
        checked_multiply(MAX_AUTHORITY_INTEGER, 2)


def test_canonical_commit_payload_is_order_independent_and_versioned() -> None:
    first = {"target": "decision:collective", "values": [1, 2], "ready": True}
    second = {"ready": True, "values": [1, 2], "target": "decision:collective"}

    canonical_args = {
        "schema": "pheroos-test-record-v1",
        "profile": "pheroos-commit-integrity-v1",
    }
    assert canonical_commit_payload(
        first, **canonical_args
    ) == canonical_commit_payload(
        second,
        **canonical_args,
    )
    assert json.loads(canonical_commit_payload(first, **canonical_args))["version"] == (
        "pheroos-commit-wire-v1"
    )
    assert commit_payload_fingerprint(
        first, **canonical_args
    ) == commit_payload_fingerprint(
        second,
        **canonical_args,
    )
    assert commit_payload_fingerprint(first, **canonical_args).startswith("sha256:")
    assert canonical_commit_set(("beta", "alpha")) == ("alpha", "beta")
    with pytest.raises(GovernanceError, match="duplicate"):
        canonical_commit_set(("alpha", "alpha"))


@pytest.mark.parametrize(
    "payload",
    [
        {"value": 0.5},
        {"": "blank-key"},
        {"value": object()},
        {"value": MAX_AUTHORITY_INTEGER + 1},
    ],
)
def test_canonical_commit_payload_rejects_non_wire_values(
    payload: dict[str, object],
) -> None:
    with pytest.raises(GovernanceError):
        canonical_commit_payload(
            payload,
            schema="pheroos-test-record-v1",
            profile="pheroos-commit-integrity-v1",
        )


def test_decision_progress_is_non_terminal_and_deadline_bounded() -> None:
    record = progress()

    assert record.terminal is False
    assert record.next_required_inputs == ("observation",)
    with pytest.raises(FrozenInstanceError):
        record.current_step = 3  # type: ignore[misc]
    with pytest.raises(GovernanceError, match="at or after"):
        progress(current_step=5)
    with pytest.raises(GovernanceError, match="run deadline"):
        progress(absolute_deadline_step=9)


def test_only_governance_issued_progress_is_authoritative() -> None:
    forged = progress()
    issued = _issue_decision_progress(
        phase=DecisionPhase.SEARCH,
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        epoch=1,
        current_step=2,
        absolute_deadline_step=5,
        absolute_run_deadline_step=8,
        remaining_reset_budget=2,
        remaining_epoch_restart_budget=1,
        **LINEAGE,
        assessment_ref=ASSESSMENT_REF,
        sealed_window=False,
        seal_ref="",
        sealed_at_step=0,
        heartbeat_continuous=True,
        heartbeat_sequence=0,
        previous_progress_ref="",
        next_required_inputs=("observation",),
        unmet_gates=("evidence",),
    )

    assert decision_progress_is_authoritative(forged) is False
    assert decision_progress_is_authoritative(issued) is True
    object.__setattr__(issued, "window_count", 3)
    assert decision_progress_is_authoritative(issued) is False


def test_evidence_commit_requires_candidate_and_epistemic_authority() -> None:
    with pytest.raises(GovernanceError, match="epistemic commit authority"):
        outcome(kind=DecisionOutcomeKind.EVIDENCE_COMMIT)
    with pytest.raises(GovernanceError, match="candidate is required"):
        outcome(
            kind=DecisionOutcomeKind.EVIDENCE_COMMIT,
            authority_scope=AuthorityScope.GOVERNANCE_LOCAL,
            authoritative_commit=True,
            epistemically_committed=True,
            candidate_id="",
        )

    committed = outcome(
        kind=DecisionOutcomeKind.EVIDENCE_COMMIT,
        authority_scope=AuthorityScope.GOVERNANCE_LOCAL,
        authoritative_commit=True,
        epistemically_committed=True,
        candidate_id="candidate:alpha",
        assessment_ref=ASSESSMENT_REF,
        certificate_ref=CERTIFICATE_REF,
        publication_eligible=True,
        execution_eligible=True,
        reason_codes=("evidence_gates_satisfied",),
    )
    assert committed.terminal is True


def test_non_commit_outcome_cannot_authorize_execution_or_claim_commit() -> None:
    with pytest.raises(GovernanceError, match="epistemic commit authority"):
        outcome(authoritative_commit=True, epistemically_committed=True)
    with pytest.raises(GovernanceError, match="authorize execution"):
        outcome(execution_eligible=True)
    with pytest.raises(GovernanceError, match="cannot authorize publication"):
        outcome(
            kind=DecisionOutcomeKind.FINALITY_UNAVAILABLE,
            authority_scope=AuthorityScope.GOVERNANCE_LOCAL,
            publication_eligible=True,
        )


def test_blocked_outcome_requires_denial_scope() -> None:
    with pytest.raises(GovernanceError, match="denial authority scope"):
        outcome(kind=DecisionOutcomeKind.BLOCKED)

    blocked = outcome(
        kind=DecisionOutcomeKind.BLOCKED,
        authority_scope=AuthorityScope.DENIAL,
        candidate_id="",
        reason_codes=("commit_stop_blocked",),
    )
    assert blocked.delivery_eligible is True
    assert blocked.authoritative_commit is False


def test_only_governance_issued_outcome_is_authoritative_and_tamper_evident() -> None:
    forged = outcome()
    issued = _issue_decision_outcome(
        kind=DecisionOutcomeKind.SAFE_FALLBACK,
        profile="pheroos-commit-integrity-v1",
        assurance=CommitAssurance.EVIDENCE_BOUND,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        epoch=1,
        current_step=5,
        absolute_deadline_step=5,
        absolute_run_deadline_step=8,
        authority_scope=AuthorityScope.NONE,
        authoritative_commit=False,
        epistemically_committed=False,
        **{
            name: value
            for name, value in LINEAGE.items()
            if name != "minimum_stability_steps"
        },
        sealed_window=False,
        seal_ref="",
        sealed_at_step=0,
        heartbeat_continuous=True,
        heartbeat_sequence=0,
        previous_progress_ref="",
        candidate_id="candidate:safe",
        assessment_ref=ASSESSMENT_REF,
        reason_codes=("deadline_reached",),
    )

    assert decision_outcome_is_authoritative(forged) is False
    assert decision_outcome_is_authoritative(issued) is True
    object.__setattr__(issued, "candidate_id", "candidate:alpha")
    assert decision_outcome_is_authoritative(issued) is False


def test_evidence_commit_assurance_profile_scope_and_certificate_are_exact() -> None:
    commit_fields = {
        "kind": DecisionOutcomeKind.EVIDENCE_COMMIT,
        "authoritative_commit": True,
        "epistemically_committed": True,
        "candidate_id": "candidate:alpha",
        "assessment_ref": ASSESSMENT_REF,
        "reason_codes": ("evidence_gates_satisfied",),
    }
    with pytest.raises(GovernanceError, match="advisory assurance"):
        outcome(
            **commit_fields,
            assurance=CommitAssurance.ADVISORY,
            authority_scope=AuthorityScope.GOVERNANCE_LOCAL,
        )
    with pytest.raises(GovernanceError, match="scope does not match"):
        outcome(
            **commit_fields,
            profile="pheroos-certified-commit-v1",
            assurance=CommitAssurance.CERTIFIED,
            authority_scope=AuthorityScope.GOVERNANCE_LOCAL,
        )
    with pytest.raises(GovernanceError, match="requires.*commit proof"):
        outcome(
            **commit_fields,
            profile="pheroos-certified-commit-v1",
            assurance=CommitAssurance.CERTIFIED,
            authority_scope=AuthorityScope.CERTIFIED,
        )
    with pytest.raises(GovernanceError, match="profile/assurance mismatch"):
        outcome(
            **commit_fields,
            profile="pheroos-distributed-commit-v1",
            assurance=CommitAssurance.CERTIFIED,
            authority_scope=AuthorityScope.CERTIFIED,
            certificate_ref=CERTIFICATE_REF,
        )


def test_set_like_decision_fields_have_permutation_stable_roots() -> None:
    first_progress = progress(
        next_required_inputs=("observation", "challenge"),
        unmet_gates=("support", "evidence"),
    )
    second_progress = progress(
        next_required_inputs=("challenge", "observation"),
        unmet_gates=("evidence", "support"),
    )
    first_outcome = outcome(reason_codes=("deadline_reached", "insufficient_evidence"))
    second_outcome = outcome(reason_codes=("insufficient_evidence", "deadline_reached"))

    assert decision_progress_fingerprint(
        first_progress
    ) == decision_progress_fingerprint(second_progress)
    assert decision_outcome_fingerprint(first_outcome) == decision_outcome_fingerprint(
        second_outcome
    )


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {
                "invalid": True,
                "safety_violation": True,
                "blocked": True,
                "evidence_commit_ready": True,
                "finality_unavailable": True,
                "deadline_reached": True,
            },
            DecisionOutcomeKind.INVALID,
        ),
        (
            {"safety_violation": True, "evidence_commit_ready": True},
            DecisionOutcomeKind.SAFETY_VIOLATION,
        ),
        (
            {"blocked": True, "evidence_commit_ready": True},
            DecisionOutcomeKind.BLOCKED,
        ),
        (
            {"evidence_commit_ready": True, "finality_unavailable": True},
            DecisionOutcomeKind.EVIDENCE_COMMIT,
        ),
        (
            {"finality_unavailable": True, "deadline_reached": True},
            DecisionOutcomeKind.FINALITY_UNAVAILABLE,
        ),
        (
            {"deadline_reached": True},
            DecisionOutcomeKind.SAFE_FALLBACK,
        ),
        ({}, None),
    ],
)
def test_terminal_priority_is_total_and_does_not_lower_commit_gates(
    overrides: dict[str, bool],
    expected: DecisionOutcomeKind | None,
) -> None:
    conditions = {
        "invalid": False,
        "safety_violation": False,
        "blocked": False,
        "evidence_commit_ready": False,
        "finality_unavailable": False,
        "deadline_reached": False,
    }
    conditions.update(overrides)

    assert (
        select_terminal_outcome_kind(
            **conditions,
            deadline_outcome="safe_fallback",
        )
        is expected
    )


def test_deadline_always_selects_declared_noncommit_when_commit_is_not_ready() -> None:
    assert (
        select_terminal_outcome_kind(
            invalid=False,
            safety_violation=False,
            blocked=False,
            evidence_commit_ready=False,
            finality_unavailable=False,
            deadline_reached=True,
            deadline_outcome="advisory",
        )
        is DecisionOutcomeKind.ADVISORY
    )
    with pytest.raises(GovernanceError, match="must be boolean"):
        select_terminal_outcome_kind(
            invalid=1,  # type: ignore[arg-type]
            safety_violation=False,
            blocked=False,
            evidence_commit_ready=False,
            finality_unavailable=False,
            deadline_reached=False,
            deadline_outcome="safe_fallback",
        )
