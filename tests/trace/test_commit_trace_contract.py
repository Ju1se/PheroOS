from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

import pytest
from jsonschema import Draft202012Validator

from pheroos.protocol.commit_wire import commit_payload_fingerprint

from pheroos.trace import (
    COMMIT_EVENT_TYPES,
    EVENT_LINEAGE_CONTRACTS,
    InMemoryTraceStore,
    TraceEvent,
    make_commit_trace_event,
    replay_commit_trace,
)
from pheroos.trace.commit_contracts import commit_trace_lineage_schema


PROFILE = "pheroos-certified-commit-v1"
ASSURANCE = "certified"
PROTOCOL = "protocol:commit-trace"
RUN = "run:commit-trace"
TARGET = "decision:commit-trace"
EPOCH = 1


def root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


_DETAILS: dict[str, dict[str, object]] = {
    "principal_attested": {
        "principal_id": "principal:a",
        "nonce": "nonce:principal:a",
    },
    "principal_verified": {
        "principal_id": "principal:a",
        "cluster_id": "cluster:a",
        "attestation_ref": root("attestation:a"),
    },
    "risk_assessed": {
        "risk_band": "HIGH",
        "threshold_ref": root("threshold:high"),
        "risk_chain_revision": 1,
    },
    "membership_snapshot": {
        "snapshot_id": "membership:1",
        "membership_root": root("membership:1"),
        "cluster_count": 4,
        "expires_at_step": 20,
    },
    "observation_recorded": {
        "observation_id": "observation:a",
        "candidate_id": "candidate:alpha",
        "polarity": "support",
        "principal_id": "principal:a",
        "nonce": "nonce:observation:a",
    },
    "observation_verified": {
        "observation_id": "observation:a",
        "candidate_id": "candidate:alpha",
        "polarity": "support",
        "principal_cluster_id": "cluster:a",
        "principal_verification_ref": root("principal-verification:a"),
    },
    "counterevidence_disposed": {
        "disposition_id": "disposition:a",
        "candidate_id": "candidate:alpha",
        "counter_observation_ref": root("observation:counter:a"),
        "disposition": "rebutted",
        "rebuttal_refs": [root("observation:rebuttal:a")],
        "resolution_ref": "resolution:a",
    },
    "challenge_recorded": {
        "challenge_id": "challenge:a",
        "candidate_id": "candidate:alpha",
        "category": "independent_reproduction",
        "result": "no_counterevidence",
        "principal_verification_ref": root("principal-verification:a"),
    },
    "evidence_bound": {
        "candidate_id": "candidate:alpha",
        "claim_fingerprint": root("claim:alpha"),
        "positive_root": root("positive:alpha"),
        "counter_root": root("counter:alpha"),
        "disposition_root": root("dispositions:alpha"),
        "challenge_root": root("challenges:alpha"),
        "evidence_root": root("evidence:alpha"),
    },
    "support_lease_issued": {
        "lease_id": "lease:a",
        "candidate_id": "candidate:alpha",
        "principal_cluster_id": "cluster:a",
        "evidence_refs": [root("observation:a")],
        "expires_at_step": 10,
    },
    "support_lease_revoked": {
        "revocation_id": "revocation:a",
        "candidate_id": "candidate:alpha",
        "principal_cluster_id": "cluster:a",
        "lease_ref": root("lease:a"),
        "reason_codes": ["support_switched"],
    },
    "support_lease_expired": {
        "lease_ref": root("lease:a"),
        "expired_at_step": 10,
    },
    "support_equivocation": {
        "finding_id": "equivocation:a",
        "principal_cluster_id": "cluster:a",
        "conflicting_candidates": ["candidate:alpha", "candidate:beta"],
        "conflicting_lease_refs": [root("lease:a"), root("lease:b")],
    },
    "commit_metrics": {
        "assessment_ref": root("assessment:1"),
        "candidate_id": "candidate:alpha",
        "net_evidence": 900_000,
        "support_clusters": 3,
        "source_diversity": 2,
        "margin": 250_000,
        "ready_for_stability": True,
    },
    "commit_window_advanced": {
        "assessment_ref": root("assessment:1"),
        "leader_candidate_id": "candidate:alpha",
        "stability_count": 2,
        "required_stability_steps": 2,
        "window_root": root("window:1"),
        "reset_count": 0,
    },
    "commit_window_reset": {
        "assessment_ref": root("assessment:2"),
        "prior_window_ref": root("window:prior"),
        "reset_count": 1,
        "remaining_reset_budget": 1,
        "reason_codes": ["leader_changed"],
    },
    "quorum_pending": {
        "assessment_ref": root("assessment:1"),
        "phase": "quorum_pending",
        "unmet_gates": ["stability_window"],
        "absolute_deadline_step": 8,
    },
    "decision_outcome": {
        "kind": "safe_fallback",
        "authoritative_commit": False,
        "epistemically_committed": False,
        "candidate_id": "candidate:safe",
        "reason_codes": ["deadline_reached"],
    },
    "stop_resolution_verified": {
        "action": "commit",
        "blocked": False,
        "expires_at_step": 10,
    },
    "action_permission_issued": {
        "action": "commit",
        "allowed": True,
        "expires_at_step": 10,
    },
    "commit_certificate_issued": {
        "certificate_kind": "evidence_commit",
        "candidate_id": "candidate:alpha",
        "claim_fingerprint": root("claim:alpha"),
        "output_fingerprint": root("output:alpha"),
        "final": True,
    },
    "quorum_witness": {
        "commit_value_root": root("commit-value:alpha"),
        "proposal_digest": root("proposal:alpha"),
        "principal_cluster_id": "cluster:a",
        "failure_domain": "domain:a",
        "verified": True,
        "expires_at_step": 10,
    },
    "epoch_certificate": {
        "prior_epoch": 1,
        "new_epoch": 2,
        "new_membership_root": root("membership:2"),
        "recovery_ref": "recovery:epoch:2",
    },
    "commit_provisional": {
        "portable_certificate_ref": root("certificate:portable"),
        "commit_value_root": root("commit-value:alpha"),
        "proposal_digest": root("proposal:alpha"),
        "candidate_id": "candidate:alpha",
        "witness_count": 2,
        "witness_quorum": 3,
        "final": False,
    },
    "certificate_conflict": {
        "finding_id": "conflict:1",
        "commit_value_roots": sorted(
            [root("commit-value:left"), root("commit-value:right")]
        ),
        "left_certificate_ref": root("certificate:left"),
        "right_certificate_ref": root("certificate:right"),
        "distributed_state_ref": root("distributed:frozen"),
        "frozen": True,
    },
    "output_decided": {
        "outcome_ref": root("outcome:safe"),
        "deliver": True,
        "publish": False,
        "execute": False,
        "reason_codes": ["delivered_terminal_outcome"],
    },
}


def make_event(
    event_type: str,
    *,
    previous: tuple[TraceEvent, ...] = (),
    step: int = 1,
    details: dict[str, object] | None = None,
    assurance: str = ASSURANCE,
    profile: str = PROFILE,
) -> TraceEvent:
    event_details = deepcopy(_DETAILS[event_type] if details is None else details)
    record_payload = {
        "assurance": assurance,
        "commit_policy_root": root("policy"),
        "epoch": EPOCH,
        "event_record_kind": event_type,
        "manifest_root": root("manifest"),
        "profile": profile,
        "protocol_id": PROTOCOL,
        "run_id": RUN,
        "target": TARGET,
    }
    return make_commit_trace_event(
        event_type=event_type,
        protocol_id=PROTOCOL,
        target=TARGET,
        reason=f"recorded {event_type}",
        profile=profile,
        assurance=assurance,
        manifest_root=root("manifest"),
        commit_policy_root=root("policy"),
        run_id=RUN,
        epoch=EPOCH,
        step=step,
        record_schema=f"pheroos-test-{event_type}-v1",
        record_payload=record_payload,
        previous_event_ids=tuple(item.lineage["event_id"] for item in previous),
        details=event_details,
    )


@pytest.mark.parametrize("event_type", sorted(COMMIT_EVENT_TYPES))
def test_each_commit_event_has_runtime_and_conditional_schema_contract(
    event_type: str,
) -> None:
    event = make_event(event_type)

    event.validate()
    Draft202012Validator(commit_trace_lineage_schema(event_type)).validate(
        event.lineage
    )
    assert set(EVENT_LINEAGE_CONTRACTS[event_type]).issubset(event.lineage)


@pytest.mark.parametrize("event_type", sorted(COMMIT_EVENT_TYPES))
def test_each_commit_event_rejects_every_missing_required_lineage_field(
    event_type: str,
) -> None:
    event = make_event(event_type)

    for field_name in EVENT_LINEAGE_CONTRACTS[event_type]:
        lineage = deepcopy(event.lineage)
        del lineage[field_name]
        with pytest.raises(ValueError, match="missing required fields"):
            TraceEvent(
                event_type=event.event_type,
                protocol_id=event.protocol_id,
                target=event.target,
                reason=event.reason,
                lineage=lineage,
            ).validate()


def test_commit_trace_event_binds_record_and_full_lineage_and_is_idempotent() -> None:
    event = make_event("risk_assessed")
    store = InMemoryTraceStore()

    first = store.append(event)
    replay = store.append(deepcopy(event))

    assert first == replay
    assert len(store.records) == 1
    assert event.lineage["record_ref"] == commit_payload_fingerprint(
        event.lineage["record_payload"],
        schema=event.lineage["record_schema"],
        profile=event.lineage["profile"],
    )

    record_mutation = deepcopy(event.lineage)
    record_mutation["record_payload"]["risk_input"] = 1
    with pytest.raises(ValueError, match="record_ref"):
        TraceEvent(
            event_type=event.event_type,
            protocol_id=event.protocol_id,
            target=event.target,
            reason=event.reason,
            lineage=record_mutation,
        ).validate()

    lineage_mutation = deepcopy(event.lineage)
    lineage_mutation["risk_chain_revision"] = 2
    with pytest.raises(ValueError, match="run_id|event_id"):
        TraceEvent(
            event_type=event.event_type,
            protocol_id=event.protocol_id,
            target=event.target,
            reason=event.reason,
            lineage=lineage_mutation,
        ).validate()


def test_commit_trace_unknown_fields_and_critical_extensions_fail_closed() -> None:
    event = make_event("risk_assessed")
    unknown = deepcopy(event.lineage)
    unknown["silent_default"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        TraceEvent(
            event_type=event.event_type,
            protocol_id=event.protocol_id,
            target=event.target,
            reason=event.reason,
            lineage=unknown,
        ).validate()

    with pytest.raises(ValueError, match="critical extension"):
        make_commit_trace_event(
            event_type="risk_assessed",
            protocol_id=PROTOCOL,
            target=TARGET,
            reason="critical extension must fail",
            profile=PROFILE,
            assurance=ASSURANCE,
            manifest_root=root("manifest"),
            commit_policy_root=root("policy"),
            run_id=RUN,
            epoch=EPOCH,
            step=1,
            record_schema="pheroos-test-risk-v1",
            record_payload={"risk_band": "HIGH"},
            details=deepcopy(_DETAILS["risk_assessed"]),
            extensions={"x-critical-new-authority": True},
        )

    extensible = make_commit_trace_event(
        event_type="risk_assessed",
        protocol_id=PROTOCOL,
        target=TARGET,
        reason="non-critical metadata remains open",
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=root("manifest"),
        commit_policy_root=root("policy"),
        run_id=RUN,
        epoch=EPOCH,
        step=1,
        record_schema="pheroos-test-risk-v1",
        record_payload={"risk_band": "HIGH"},
        details=deepcopy(_DETAILS["risk_assessed"]),
        extensions={"x-acme-debug": {"label": "open metadata"}},
    )
    extensible.validate()
    without_metadata = make_commit_trace_event(
        event_type="risk_assessed",
        protocol_id=PROTOCOL,
        target=TARGET,
        reason="different human-readable reason",
        profile=PROFILE,
        assurance=ASSURANCE,
        manifest_root=root("manifest"),
        commit_policy_root=root("policy"),
        run_id=RUN,
        epoch=EPOCH,
        step=1,
        record_schema="pheroos-test-risk-v1",
        record_payload={"risk_band": "HIGH"},
        details=deepcopy(_DETAILS["risk_assessed"]),
    )
    assert extensible.lineage["event_id"] == without_metadata.lineage["event_id"]
    assert extensible.lineage["record_ref"] == without_metadata.lineage["record_ref"]


def test_window_trace_represents_non_ready_zero_count_without_faking_a_leader() -> None:
    non_ready = deepcopy(_DETAILS["commit_window_advanced"])
    non_ready["leader_candidate_id"] = ""
    non_ready["stability_count"] = 0
    event = make_event("commit_window_advanced", details=non_ready)
    event.validate()

    inconsistent = dict(non_ready, stability_count=1)
    with pytest.raises(ValueError, match="non-ready.*zero"):
        make_event("commit_window_advanced", details=inconsistent)

    ready_zero = dict(
        deepcopy(_DETAILS["commit_window_advanced"]),
        stability_count=0,
    )
    with pytest.raises(ValueError, match="ready.*positive"):
        make_event("commit_window_advanced", details=ready_zero)


def test_quorum_pending_phase_is_exact_canonical_decision_phase_value() -> None:
    make_event("quorum_pending").validate()
    uppercase = dict(deepcopy(_DETAILS["quorum_pending"]), phase="QUORUM_PENDING")
    with pytest.raises(ValueError, match="unsupported value"):
        make_event("quorum_pending", details=uppercase)


def test_only_outcome_certificate_trace_may_have_no_candidate() -> None:
    outcome = dict(
        deepcopy(_DETAILS["commit_certificate_issued"]),
        certificate_kind="outcome",
        candidate_id="",
        claim_fingerprint="",
    )
    make_event("commit_certificate_issued", details=outcome).validate()

    for certificate_kind in (
        "local_receipt",
        "evidence_commit",
        "distributed_commit",
    ):
        malformed = dict(outcome, certificate_kind=certificate_kind)
        with pytest.raises(ValueError, match="substantive candidate and claim"):
            make_event("commit_certificate_issued", details=malformed)

    malformed_claim = dict(
        deepcopy(_DETAILS["commit_certificate_issued"]),
        claim_fingerprint="not-a-root",
    )
    with pytest.raises(ValueError, match="canonical root"):
        make_event("commit_certificate_issued", details=malformed_claim)


def test_candidate_metric_trace_preserves_negative_nonleader_margin() -> None:
    nonleader = dict(deepcopy(_DETAILS["commit_metrics"]), margin=-250_000)
    make_event("commit_metrics", details=nonleader).validate()


def test_provisional_trace_binds_proposal_presence_to_witness_count() -> None:
    validator = Draft202012Validator(
        commit_trace_lineage_schema("commit_provisional")
    )
    zero_witness = dict(deepcopy(_DETAILS["commit_provisional"]), witness_count=0)
    zero_witness.pop("commit_value_root")
    zero_witness.pop("proposal_digest")
    event = make_event("commit_provisional", details=zero_witness)
    event.validate()
    validator.validate(event.lineage)

    schema_rejects_fake_zero = deepcopy(event.lineage)
    schema_rejects_fake_zero["proposal_digest"] = root("proposal:fake-zero")
    assert not validator.is_valid(schema_rejects_fake_zero)

    schema_rejects_missing_positive = deepcopy(
        make_event("commit_provisional").lineage
    )
    del schema_rejects_missing_positive["proposal_digest"]
    assert not validator.is_valid(schema_rejects_missing_positive)

    zero_with_fake_proposal = dict(
        deepcopy(_DETAILS["commit_provisional"]), witness_count=0
    )
    with pytest.raises(ValueError, match="zero-witness.*proposal/value"):
        make_event("commit_provisional", details=zero_with_fake_proposal)

    witnessed_without_proposal = deepcopy(_DETAILS["commit_provisional"])
    witnessed_without_proposal.pop("proposal_digest")
    with pytest.raises(ValueError, match="witness-bearing.*proposal/value"):
        make_event("commit_provisional", details=witnessed_without_proposal)


def test_distributed_trace_records_semantic_value_without_weakening_other_kinds() -> None:
    distributed = dict(
        deepcopy(_DETAILS["commit_certificate_issued"]),
        certificate_kind="distributed_commit",
        commit_value_root=root("commit-value:distributed"),
    )
    make_event("commit_certificate_issued", details=distributed).validate()

    missing = dict(distributed)
    missing.pop("commit_value_root")
    with pytest.raises(ValueError, match="distributed certificate.*value root"):
        make_event("commit_certificate_issued", details=missing)

    evidence_with_value = dict(
        deepcopy(_DETAILS["commit_certificate_issued"]),
        commit_value_root=root("commit-value:not-distributed"),
    )
    with pytest.raises(ValueError, match="exclusively bind"):
        make_event("commit_certificate_issued", details=evidence_with_value)

    one_value_conflict = dict(
        deepcopy(_DETAILS["certificate_conflict"]),
        commit_value_roots=[root("commit-value:only")],
    )
    with pytest.raises(ValueError, match="distinct commit values"):
        make_event("certificate_conflict", details=one_value_conflict)


def test_observation_to_output_trace_replays_without_governance_private_objects() -> None:
    attested = make_event("principal_attested")
    verified = make_event("principal_verified", previous=(attested,))
    risk = make_event("risk_assessed")
    membership = make_event("membership_snapshot", previous=(verified,))
    recorded = make_event("observation_recorded", previous=(attested,))
    observation = make_event(
        "observation_verified", previous=(recorded, verified)
    )
    challenge = make_event("challenge_recorded", previous=(verified,))
    evidence = make_event(
        "evidence_bound", previous=(observation, challenge)
    )
    lease = make_event(
        "support_lease_issued", previous=(evidence, verified, membership)
    )
    stop = make_event("stop_resolution_verified")
    permission = make_event("action_permission_issued")
    metrics = make_event(
        "commit_metrics",
        previous=(evidence, lease, risk, membership, stop, permission),
    )
    window = make_event("commit_window_advanced", previous=(metrics,), step=2)
    certificate = make_event(
        "commit_certificate_issued", previous=(window,), step=2
    )
    outcome_details = {
        "kind": "evidence_commit",
        "authoritative_commit": True,
        "epistemically_committed": True,
        "candidate_id": "candidate:alpha",
        "reason_codes": ["stable_evidence_commit"],
        "assessment_ref": metrics.lineage["assessment_ref"],
        "certificate_ref": certificate.lineage["certificate_ref"],
    }
    outcome = make_event(
        "decision_outcome",
        previous=(window, certificate),
        step=2,
        details=outcome_details,
    )
    output_details = {
        "outcome_ref": outcome.lineage["outcome_ref"],
        "deliver": True,
        "publish": True,
        "execute": False,
        "reason_codes": ["publish_authorized"],
        "certificate_ref": certificate.lineage["certificate_ref"],
    }
    output = make_event(
        "output_decided", previous=(outcome,), step=2, details=output_details
    )
    events = (
        attested,
        verified,
        risk,
        membership,
        recorded,
        observation,
        challenge,
        evidence,
        lease,
        stop,
        permission,
        metrics,
        window,
        certificate,
        outcome,
        output,
    )

    replay = replay_commit_trace(events)

    assert replay.complete is True
    assert replay.outcome_kind == "evidence_commit"
    assert replay.outcome_ref == outcome.lineage["outcome_ref"]
    assert replay.certificate_refs == (certificate.lineage["certificate_ref"],)
    assert replay.output_ref == output.lineage["authorization_ref"]
    assert replay.event_types[0] == "principal_attested"
    assert replay.event_types[-1] == "output_decided"


def test_commit_trace_replay_rejects_gap_cross_run_and_incomplete_terminal_chain() -> None:
    attested = make_event("principal_attested")
    verified = make_event("principal_verified", previous=(attested,))

    with pytest.raises(ValueError, match="unseen predecessor"):
        replay_commit_trace((verified,), require_complete=False)

    other_run_lineage = deepcopy(verified.lineage)
    other_run_lineage["run_id"] = "run:other"
    with pytest.raises(ValueError, match="run_id|event_id"):
        TraceEvent(
            event_type=verified.event_type,
            protocol_id=verified.protocol_id,
            target=verified.target,
            reason=verified.reason,
            lineage=other_run_lineage,
        ).validate()

    partial = replay_commit_trace((attested,), require_complete=False)
    assert partial.complete is False
    with pytest.raises(ValueError, match="terminally complete"):
        replay_commit_trace((attested,))
