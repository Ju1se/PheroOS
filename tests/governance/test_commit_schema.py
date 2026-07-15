from __future__ import annotations

import json

from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.commit_state import (
    AuthorityScope,
    CommitAssurance,
    DecisionOutcome,
    DecisionOutcomeKind,
    ReplayNamespace,
    ReplayReceipt,
    commit_replay_state_payload,
    commit_window_state_payload,
    decision_outcome_payload,
    initialize_commit_replay_state,
    initialize_commit_window_state,
    record_commit_replay_receipts,
    replay_receipt_payload,
)
from pheroos.governance.permission import (
    action_permission_payload,
    issue_action_permission,
)
from pheroos.governance.schema import commit_schema, validate_commit_wire_record
from pheroos.protocol import CommitAction, canonical_commit_payload
from tests.governance.test_commit_engine import _scenario


MANIFEST_ROOT = "sha256:" + ("1" * 64)
COMMIT_POLICY_ROOT = "sha256:" + ("2" * 64)
ASSESSMENT_REF = "sha256:" + ("3" * 64)
CERTIFICATE_REF = "sha256:" + ("4" * 64)
PROFILE = "pheroos-certified-commit-v1"


def envelope(
    payload: dict[str, object],
    *,
    schema: str,
    profile: str = PROFILE,
) -> dict[str, object]:
    return json.loads(
        canonical_commit_payload(
            payload,
            schema=schema,
            profile=profile,
        )
    )


def permission_payload() -> dict[str, object]:
    permission = issue_action_permission(
        permission_id="permission:publish:1",
        profile=PROFILE,
        assurance=CommitAssurance.CERTIFIED,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        action=CommitAction.PUBLISH,
        epoch=3,
        decision_ref=ASSESSMENT_REF,
        certificate_ref=CERTIFICATE_REF,
        allowed=True,
        reason_codes=("certificate_verified", "policy_allowed"),
        issuer_id="governance:policy",
        policy_ref="policy:publish:v1",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=4,
        expires_at_step=8,
        provenance="urn:test:permission",
        trace_event_id="trace:permission:publish",
    )
    return action_permission_payload(permission)


def outcome_payload() -> dict[str, object]:
    outcome = DecisionOutcome(
        kind=DecisionOutcomeKind.EVIDENCE_COMMIT,
        profile=PROFILE,
        assurance=CommitAssurance.CERTIFIED,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        target="decision:collective",
        epoch=3,
        current_step=5,
        absolute_deadline_step=8,
        absolute_run_deadline_step=12,
        authority_scope=AuthorityScope.CERTIFIED,
        authoritative_commit=True,
        epistemically_committed=True,
        context_ref="sha256:" + ("5" * 64),
        risk_assessment_root="sha256:" + ("6" * 64),
        risk_chain_state_root="sha256:" + ("7" * 64),
        risk_policy_root="sha256:" + ("8" * 64),
        membership_root="sha256:" + ("9" * 64),
        membership_snapshot_root="sha256:" + ("a" * 64),
        membership_epoch_state_root="sha256:" + ("b" * 64),
        threshold_root="sha256:" + ("c" * 64),
        replay_state_ref="sha256:" + ("d" * 64),
        replay_root="sha256:" + ("e" * 64),
        support_replay_state_root="sha256:" + ("f" * 64),
        support_replay_root="sha256:" + ("0" * 64),
        collective_evidence_root="sha256:" + ("1" * 64),
        collective_challenge_root="sha256:" + ("2" * 64),
        collective_lease_root="sha256:" + ("3" * 64),
        candidate_evidence_root="sha256:" + ("4" * 64),
        candidate_challenge_root="sha256:" + ("5" * 64),
        candidate_lease_root="sha256:" + ("6" * 64),
        stop_resolution_root="sha256:" + ("7" * 64),
        permission_root="sha256:" + ("8" * 64),
        window_state_ref="sha256:" + ("9" * 64),
        window_root="sha256:" + ("a" * 64),
        sealed_window=True,
        seal_ref="sha256:" + ("b" * 64),
        sealed_at_step=5,
        heartbeat_continuous=True,
        heartbeat_sequence=0,
        previous_progress_ref="",
        candidate_id="candidate:alpha",
        reason_codes=("evidence_gates_satisfied",),
        assessment_ref=ASSESSMENT_REF,
        certificate_ref=CERTIFICATE_REF,
        delivery_eligible=True,
        publication_eligible=True,
        execution_eligible=False,
    )
    return decision_outcome_payload(outcome)


def replay_receipt() -> ReplayReceipt:
    return ReplayReceipt(
        namespace=ReplayNamespace.OBSERVATION,
        record_id="observation:alpha",
        nonce="nonce:observation:alpha",
        payload_fingerprint="sha256:" + ("8" * 64),
        target="decision:collective",
        candidate_id="candidate:alpha",
        epoch=3,
        principal_id="principal:alpha",
    )


def test_commit_schema_validates_actual_authority_payloads() -> None:
    scenario = _scenario()
    permission = envelope(
        permission_payload(),
        schema="pheroos-action-permission-v1",
    )
    outcome = envelope(
        outcome_payload(),
        schema="pheroos-decision-outcome-v1",
    )
    window = initialize_commit_window_state(
        commit_policy=scenario.policy,
        profile=scenario.context.profile,
        assurance=scenario.context.assurance,
        manifest_root=scenario.context.manifest_root,
        commit_policy_root=scenario.context.commit_policy_root,
        protocol_id=scenario.context.protocol_id,
        run_id=scenario.run_id,
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
    replay = initialize_commit_replay_state(
        profile=PROFILE,
        assurance=CommitAssurance.CERTIFIED,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal",
        run_id="run:1",
        current_step=0,
        issuer_id="governance:replay",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:replay",
        trace_event_id="trace:replay",
    )
    replay = record_commit_replay_receipts(
        replay,
        current_step=1,
        receipts=(replay_receipt(),),
    )
    window_record = envelope(
        commit_window_state_payload(window),
        schema="pheroos-commit-window-state-v1",
        profile=window.profile,
    )
    replay_record = envelope(
        commit_replay_state_payload(replay),
        schema="pheroos-commit-replay-state-v1",
    )
    replay_receipt_record = envelope(
        replay_receipt_payload(replay_receipt()),
        schema="pheroos-commit-replay-receipt-v1",
    )

    assert validate_commit_wire_record(permission) == []
    assert validate_commit_wire_record(outcome) == []
    assert validate_commit_wire_record(window_record) == []
    assert validate_commit_wire_record(replay_record) == []
    assert validate_commit_wire_record(replay_receipt_record) == []
    assert commit_schema()["$id"] == "https://pheroos.dev/schemas/commit.schema.json"


def test_commit_wire_rejects_unknown_critical_profile_and_numeric_coercion() -> None:
    unknown = envelope(
        permission_payload(),
        schema="pheroos-action-permission-v1",
    )
    unknown["payload"]["unexpected_authority"] = True
    assert validate_commit_wire_record(unknown)

    mismatched = envelope(
        outcome_payload(),
        schema="pheroos-decision-outcome-v1",
    )
    mismatched["payload"]["profile"] = "pheroos-distributed-commit-v1"
    assert any(
        "profile" in error for error in validate_commit_wire_record(mismatched)
    )

    coerced = envelope(
        permission_payload(),
        schema="pheroos-action-permission-v1",
    )
    coerced["payload"]["epoch"] = 3.0
    assert validate_commit_wire_record(coerced)


def test_commit_wire_rejects_noncanonical_sets_and_missing_publish_certificate() -> None:
    noncanonical = envelope(
        permission_payload(),
        schema="pheroos-action-permission-v1",
    )
    noncanonical["payload"]["reason_codes"] = list(
        reversed(noncanonical["payload"]["reason_codes"])
    )
    assert any(
        "not canonical" in error
        for error in validate_commit_wire_record(noncanonical)
    )

    missing_certificate = envelope(
        permission_payload(),
        schema="pheroos-action-permission-v1",
    )
    missing_certificate["payload"]["certificate_ref"] = ""
    assert any(
        "requires certificate" in error
        for error in validate_commit_wire_record(missing_certificate)
    )


def test_commit_replay_wire_rejects_root_mutation_and_typed_receipt_collision() -> None:
    replay = initialize_commit_replay_state(
        profile=PROFILE,
        assurance=CommitAssurance.CERTIFIED,
        manifest_root=MANIFEST_ROOT,
        commit_policy_root=COMMIT_POLICY_ROOT,
        protocol_id="protocol:optimal:schema-collision",
        run_id="run:schema-collision",
        current_step=0,
        issuer_id="governance:replay",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="urn:test:replay:collision",
        trace_event_id="trace:replay:collision",
    )
    replay = record_commit_replay_receipts(
        replay,
        current_step=1,
        receipts=(replay_receipt(),),
    )
    record = envelope(
        commit_replay_state_payload(replay),
        schema="pheroos-commit-replay-state-v1",
    )

    mutated_root = json.loads(json.dumps(record))
    mutated_root["payload"]["receipt_root"] = "sha256:" + ("0" * 64)
    assert any(
        "root mismatch" in error
        for error in validate_commit_wire_record(mutated_root)
    )

    collision = json.loads(json.dumps(record))
    conflicting = dict(collision["payload"]["receipts"][0])
    conflicting["record_id"] = "observation:beta"
    conflicting["payload_fingerprint"] = "sha256:" + ("9" * 64)
    collision["payload"]["receipts"].append(conflicting)
    assert any(
        "safety collision" in error
        for error in validate_commit_wire_record(collision)
    )
