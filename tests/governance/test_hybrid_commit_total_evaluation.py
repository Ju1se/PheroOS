from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from itertools import count
import json
from pathlib import Path

import pytest

from pheroos.conformance._commit_reference import (
    assess_reference_scenario,
    build_reference_distributed_commit,
    build_reference_portable_commit,
    build_reference_scenario,
    build_reference_stable_commit,
    issue_reference_action_gates,
    issue_reference_distributed_certificate,
    issue_reference_observation,
    issue_reference_semantic_conflict_certificate,
    issue_reference_witness,
)
import pheroos.governance._hybrid.commit as commit_module
import pheroos.governance.hybrid_commit_evaluation as evaluation_module
from pheroos.governance.attention import evaluate_hybrid_attention_step
from pheroos.governance.authority import AuthorityLevel
from pheroos.governance.candidate import Candidate, CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.challenge import (
    verified_challenge_payload,
)
from pheroos.governance.commit import (
    CandidateCommitInput,
    build_commit_replay_receipts,
    issue_commit_evaluation_context,
)
from pheroos.governance.evidence_binding import evidence_binding_payload
from pheroos.governance.evidence_binding import bind_evidence
from pheroos.governance.collective import ScoutReport
from pheroos.governance.commit_state import (
    advance_commit_window_state,
    decision_outcome_fingerprint,
    initialize_commit_window_state,
    record_commit_replay_receipts,
)
from pheroos.governance.distributed_commit import (
    DISTRIBUTED_COMMIT_CERTIFICATE_VERSION,
    WITNESS_VERIFICATION_VERSION,
    assemble_portable_distributed_commit_certificate,
    distributed_commit_certificate_fingerprint,
    distributed_commit_certificate_payload,
    distributed_commit_state_fingerprint,
    issue_distributed_commit_proposal,
    portable_membership_snapshot_from_eligible,
    record_witness_verifications,
    register_distributed_commit_certificate,
    witness_verification_payload,
)
from pheroos.governance.hybrid_commit import (
    HYBRID_COMMIT_EVALUATION_REQUEST_VERSION,
    HybridCommitAttentionStatus,
    HybridCommitEvaluationRequest,
    HybridCommitEvaluationStatus,
    evaluate_hybrid_commit_evaluation,
    evaluate_hybrid_commit_step,
    hybrid_commit_evaluation_is_authoritative,
    hybrid_commit_evaluation_payload,
    hybrid_commit_evaluation_request_fingerprint,
)
from pheroos.governance.observation import verified_observation_payload
from pheroos.governance.output import authorize_terminal_publication
from pheroos.governance.permission import (
    action_permission_fingerprint,
    action_permission_payload,
    issue_action_permission,
)
from pheroos.governance.pheromone import (
    PheromoneNeighborhood,
    PheromoneSubject,
)
from pheroos.governance.principal import principal_verification_payload
from pheroos.governance.risk import risk_assessment_payload
from pheroos.governance.schema import validate_commit_wire_record
from pheroos.governance.stop_signal import (
    StopResolution,
    stop_resolution_verification_fingerprint,
    stop_resolution_verification_payload,
    verify_stop_resolution,
)
from pheroos.governance.signal import verify_signal_input
from pheroos.governance.support_lease import (
    eligible_principal_snapshot_payload,
    support_lease_payload,
)
from pheroos.protocol import canonical_commit_payload
from pheroos.protocol.commit_models import (
    COMMIT_CANONICAL_VERSION,
    COMMIT_MODEL,
    COMMIT_POLICY_VERSION,
    COMMIT_WIRE_VERSION,
    CERTIFIED_COMMIT_PROFILE_VERSION,
    DISTRIBUTED_COMMIT_PROFILE_VERSION,
    HYBRID_COMMIT_PROFILE_VERSION,
    REQUIRED_COMMIT_RESET_RULES,
    CertificatePolicy,
    CollectiveCommitPolicy,
    CommitAction,
    CommitAssurance,
    CommitWindowPolicy,
    DistributedCommitPolicy,
    EvidenceQualificationPolicy,
    RiskBandPolicy,
    SupportLeasePolicy,
    TerminalOutcomePolicy,
)
from pheroos.protocol.commit_wire import (
    commit_payload_fingerprint,
    commit_policy_authority_payload,
)
from pheroos.trace import TraceEvent, make_commit_trace_event, replay_commit_trace


_REQUEST_IDS = count(1)


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _risk_band() -> RiskBandPolicy:
    return RiskBandPolicy(
        minimum_positive_evidence=1_000_000,
        maximum_counterevidence=0,
        maximum_counterevidence_ratio_ppm=0,
        minimum_support_clusters=1,
        minimum_support_ratio_ppm=500_000,
        minimum_source_diversity=1,
        minimum_margin=500_000,
        stability_steps=2,
        required_challenge_categories=["independent_replication"],
        minimum_assurance="evidence_bound",
        publishable_outcomes=["evidence_commit"],
        executable_outcomes=[],
    )


def _commit_policy() -> CollectiveCommitPolicy:
    return CollectiveCommitPolicy(
        policy_version=COMMIT_POLICY_VERSION,
        model=COMMIT_MODEL,
        assurance="evidence_bound",
        target="decision:optimal",
        evidence_qualification=EvidenceQualificationPolicy(
            numeric_scale=1_000_000,
            minimum_quality_ppm=500_000,
            minimum_relevance_ppm=500_000,
            positive_group_cap=1_000_000,
            counter_group_cap=1_000_000,
            counter_weight_ppm=1_000_000,
            minimum_positive_evidence=1_000_000,
            maximum_counterevidence=0,
            maximum_counterevidence_ratio_ppm=0,
            domain_contribution_floor=500_000,
            minimum_source_diversity=1,
            required_challenge_categories=["independent_replication"],
            observation_ttl_steps=20,
            require_provenance=True,
            require_trace=True,
        ),
        support_lease=SupportLeasePolicy(
            minimum_support_clusters=1,
            support_ratio_ppm=500_000,
            lease_ttl_steps=5,
            membership_mode="verified_snapshot_v1",
            switch_mode="revoke_then_issue_v1",
            equivocation_mode="exclude_conflicts_v1",
            evidence_reference_required=True,
            cluster_verification_required=True,
        ),
        risk_bands={name: _risk_band() for name in ("LOW", "MODERATE", "HIGH", "CRITICAL")},
        commit_window=CommitWindowPolicy(
            minimum_stability_steps=2,
            deliberation_deadline_steps=8,
            maximum_leader_resets=2,
            maximum_epoch_restarts=1,
            run_deadline_steps=12,
            reset_rules=sorted(REQUIRED_COMMIT_RESET_RULES),
        ),
        terminal_outcome=TerminalOutcomePolicy(
            safe_fallback_candidate="candidate:fallback",
            deadline_outcome="safe_fallback",
            policy_incomplete_outcome="invalid",
            finality_unavailable_outcome="finality_unavailable",
            deliverable_outcomes=[
                "evidence_commit",
                "safe_fallback",
                "advisory",
                "blocked",
                "invalid",
                "finality_unavailable",
                "safety_violation",
            ],
            publishable_outcomes=["evidence_commit", "safe_fallback"],
            executable_outcomes=[],
        ),
        certificate=CertificatePolicy(
            mode="local_receipt",
            wire_version=COMMIT_WIRE_VERSION,
            canonicalization=COMMIT_CANONICAL_VERSION,
            hash_algorithm="sha256",
            issuer_attestation_required=False,
            independent_verification_required=False,
        ),
        distributed=None,
    )


def _higher_assurance_policy(
    assurance: CommitAssurance,
) -> CollectiveCommitPolicy:
    base = _commit_policy()
    support_ratio = (
        250_000
        if assurance is CommitAssurance.DISTRIBUTED
        else base.support_lease.support_ratio_ppm
    )
    bands = {
        name: replace(
            band,
            minimum_assurance=assurance.value,
            minimum_support_ratio_ppm=support_ratio,
        )
        for name, band in base.risk_bands.items()
    }
    distributed = (
        DistributedCommitPolicy(
            fault_model="byzantine_static_v1",
            membership_mode="static_epoch_verified_clusters_v1",
            membership_size=4,
            max_byzantine_faults=1,
            witness_quorum=3,
            witness_ttl_steps=4,
            minimum_failure_domain_diversity=3,
            epoch_transition_rule="governed_new_epoch_v1",
            conflict_rule="freeze_v1",
        )
        if assurance is CommitAssurance.DISTRIBUTED
        else None
    )
    return replace(
        base,
        assurance=assurance.value,
        support_lease=replace(base.support_lease, support_ratio_ppm=support_ratio),
        risk_bands=bands,
        certificate=CertificatePolicy(
            mode=(
                "distributed"
                if assurance is CommitAssurance.DISTRIBUTED
                else "portable"
            ),
            wire_version=COMMIT_WIRE_VERSION,
            canonicalization=COMMIT_CANONICAL_VERSION,
            hash_algorithm="sha256",
            issuer_attestation_required=True,
            independent_verification_required=True,
        ),
        distributed=distributed,
    )


def _json_value(value: object) -> object:
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def _manifest_payload(
    commit_policy: CollectiveCommitPolicy | None = None,
) -> dict[str, object]:
    hybrid_example = json.loads(
        Path("examples/hybrid-pheromone-protocol/capability.json").read_text(
            encoding="utf-8"
        )
    )["protocol"]
    decision_policy = dict(hybrid_example["collective_decision_policy"])
    decision_policy.update(
        {
            "min_independent_scouts": 1,
            "quorum_threshold": 1,
            "fallback_candidate": "candidate:fallback",
        }
    )
    return {
        "id": "capability:hybrid-total-evaluation",
        "name": "Hybrid Total Evaluation Reference",
        "version": "1.0.0",
        "protocol": {
            "protocol_version": "pheroos.protocol.v1",
            "id": "protocol:tck:optimal-commit",
            "targets": [{"id": "decision:optimal"}],
            "candidates": [
                {"id": "candidate:alpha", "target": "decision:optimal"},
                {"id": "candidate:beta", "target": "decision:optimal"},
                {
                    "id": "candidate:fallback",
                    "target": "decision:optimal",
                    "safe_fallback": True,
                },
            ],
            "quorum_policy": {
                "target": "decision:optimal",
                "fallback_candidate": "candidate:fallback",
            },
            "output_policy": {
                "requires_committed_candidate": True,
                "requires_evidence_contract": True,
                "requires_stop_resolution": True,
                "requires_publication_permission": True,
            },
            "trace_policy": hybrid_example["trace_policy"],
            "signals": [
                {
                    **item,
                    "target": "decision:optimal",
                }
                for item in hybrid_example["signals"]
            ],
            "collective_decision_policy": decision_policy,
            "collective_commit_policy": _json_value(
                commit_policy_authority_payload(commit_policy or _commit_policy())
            ),
        },
    }


def _scenario(
    *,
    commit_policy: CollectiveCommitPolicy | None = None,
    profile: str = HYBRID_COMMIT_PROFILE_VERSION,
):
    index = next(_REQUEST_IDS)
    return build_reference_scenario(
        f"hybrid-total-evaluation-{index}",
        _manifest_payload(commit_policy),
        profile=profile,
        variant=f"request-{index}",
    )


def _common(scenario, *, step: int) -> dict[str, object]:
    return {
        "profile": scenario.context.profile,
        "assurance": scenario.context.assurance.value,
        "manifest_root": scenario.context.manifest_root,
        "commit_policy_root": scenario.context.commit_policy_root,
        "protocol_id": scenario.context.protocol_id,
        "run_id": scenario.run_id,
        "target": scenario.context.target,
        "epoch": scenario.context.epoch,
        "step": step,
    }


def _event(
    scenario,
    event_type: str,
    *,
    step: int,
    record_schema: str,
    record_payload: dict[str, object],
    details: dict[str, object],
    previous: tuple[TraceEvent, ...] = (),
) -> TraceEvent:
    common = _common(scenario, step=step)
    return make_commit_trace_event(
        event_type=event_type,
        protocol_id=common["protocol_id"],
        target=common["target"],
        reason=f"fixture recorded {event_type}",
        profile=common["profile"],
        assurance=common["assurance"],
        manifest_root=common["manifest_root"],
        commit_policy_root=common["commit_policy_root"],
        run_id=common["run_id"],
        epoch=common["epoch"],
        step=step,
        record_schema=record_schema,
        record_payload=record_payload,
        previous_event_ids=tuple(item.lineage["event_id"] for item in previous),
        details=details,
    )


def _authority_trace(
    scenario,
    *,
    stop=None,
    permission=None,
) -> tuple[TraceEvent, ...]:
    principal = scenario.principals[0]
    attested = _event(
        scenario,
        "principal_attested",
        step=1,
        record_schema="pheroos-test-principal-attestation-v1",
        record_payload={"principal_id": principal.principal_id, "nonce": "nonce:trace"},
        details={"principal_id": principal.principal_id, "nonce": "nonce:trace"},
    )
    verified = _event(
        scenario,
        "principal_verified",
        step=2,
        record_schema="pheroos-principal-verification-v1",
        record_payload=principal_verification_payload(principal),
        details={
            "principal_id": principal.principal_id,
            "cluster_id": principal.cluster_id,
            "attestation_ref": principal.attestation_fingerprint,
        },
        previous=(attested,),
    )
    risk = scenario.risk_assessment
    risk_event = _event(
        scenario,
        "risk_assessed",
        step=2,
        record_schema="pheroos-risk-assessment-v1",
        record_payload=risk_assessment_payload(risk),
        details={
            "risk_band": risk.risk_band.value,
            "threshold_ref": scenario.context.threshold_fingerprint,
            "risk_chain_revision": risk.risk_chain_revision,
        },
    )
    membership = scenario.membership_snapshot
    membership_event = _event(
        scenario,
        "membership_snapshot",
        step=2,
        record_schema="pheroos-eligible-principal-snapshot-v1",
        record_payload=eligible_principal_snapshot_payload(membership),
        details={
            "snapshot_id": membership.snapshot_id,
            "membership_root": membership.membership_root,
            "cluster_count": len(membership.eligible_clusters),
            "expires_at_step": membership.expires_at_step,
        },
        previous=(verified,),
    )
    observation_events: list[TraceEvent] = []
    challenge_events: list[TraceEvent] = []
    evidence_events: list[TraceEvent] = []
    for candidate in scenario.candidate_inputs:
        verified_for_candidate: list[TraceEvent] = []
        for observation in (
            *candidate.positive_observations,
            *candidate.counter_observations,
        ):
            recorded = _event(
                scenario,
                "observation_recorded",
                step=3,
                record_schema="pheroos-test-observation-attestation-v1",
                record_payload={
                    "observation_id": observation.observation_id,
                    "candidate_id": observation.candidate_id,
                    "nonce": observation.nonce,
                },
                details={
                    "observation_id": observation.observation_id,
                    "candidate_id": observation.candidate_id,
                    "polarity": observation.polarity.value,
                    "principal_id": observation.principal_id,
                    "nonce": observation.nonce,
                },
                previous=(attested,),
            )
            checked = _event(
                scenario,
                "observation_verified",
                step=3,
                record_schema="pheroos-verified-observation-v1",
                record_payload=verified_observation_payload(observation),
                details={
                    "observation_id": observation.observation_id,
                    "candidate_id": observation.candidate_id,
                    "polarity": observation.polarity.value,
                    "principal_cluster_id": observation.principal_cluster_id,
                    "principal_verification_ref": (
                        observation.principal_verification_fingerprint
                    ),
                },
                previous=(recorded, verified),
            )
            observation_events.extend((recorded, checked))
            verified_for_candidate.append(checked)
        for challenge in candidate.challenges:
            challenge_event = _event(
                scenario,
                "challenge_recorded",
                step=3,
                record_schema="pheroos-verified-challenge-v1",
                record_payload=verified_challenge_payload(challenge),
                details={
                    "challenge_id": challenge.challenge_id,
                    "candidate_id": challenge.candidate_id,
                    "category": challenge.category,
                    "result": challenge.result.value,
                    "principal_verification_ref": (
                        challenge.principal_verification_fingerprint
                    ),
                },
                previous=(verified,),
            )
            challenge_events.append(challenge_event)
        binding = candidate.evidence_binding
        evidence_event = _event(
            scenario,
            "evidence_bound",
            step=3,
            record_schema="pheroos-evidence-binding-authority-v1",
            record_payload=evidence_binding_payload(binding),
            details={
                "candidate_id": binding.candidate_id,
                "claim_fingerprint": binding.claim_fingerprint,
                "positive_root": binding.positive_root,
                "counter_root": binding.counter_root,
                "disposition_root": binding.disposition_root,
                "challenge_root": binding.challenge_root,
                "evidence_root": binding.evidence_root,
            },
            previous=tuple((*verified_for_candidate, *challenge_events[-1:])),
        )
        evidence_events.append(evidence_event)
    lease_events: list[TraceEvent] = []
    by_candidate = {event.lineage["candidate_id"]: event for event in evidence_events}
    for lease in scenario.leases:
        event = _event(
            scenario,
            "support_lease_issued",
            step=4,
            record_schema="pheroos-support-lease-v1",
            record_payload=support_lease_payload(lease),
            details={
                "lease_id": lease.lease_id,
                "candidate_id": lease.candidate_id,
                "principal_cluster_id": lease.principal_cluster_id,
                "evidence_refs": list(lease.positive_observation_fingerprints),
                "expires_at_step": lease.expires_at_step,
            },
            previous=(by_candidate[lease.candidate_id], verified, membership_event),
        )
        lease_events.append(event)
    stop = stop or scenario.stop_resolution
    stop_event = _event(
        scenario,
        "stop_resolution_verified",
        step=max(4, stop.issued_at_step),
        record_schema="pheroos-stop-resolution-verification-v1",
        record_payload=stop_resolution_verification_payload(stop),
        details={
            "action": stop.action.value,
            "blocked": stop.blocked,
            "expires_at_step": stop.expires_at_step,
        },
    )
    permission = permission or scenario.permission
    permission_event = _event(
        scenario,
        "action_permission_issued",
        step=max(4, permission.issued_at_step),
        record_schema="pheroos-action-permission-v1",
        record_payload=action_permission_payload(permission),
        details={
            "action": permission.action.value,
            "allowed": permission.allowed,
            "expires_at_step": permission.expires_at_step,
        },
    )
    result = (
        attested,
        verified,
        risk_event,
        membership_event,
        *observation_events,
        *challenge_events,
        *evidence_events,
        *lease_events,
        stop_event,
        permission_event,
    )
    replay_commit_trace(result, require_complete=False)
    return result


def _attention(
    scenario,
    *,
    step: int,
    candidate_id: str | None = None,
    candidate_ids: set[str] | None = None,
):
    policy = scenario.manifest.protocol.collective_decision_policy
    assert policy is not None
    declared_candidates = tuple(
        item
        for item in scenario.manifest.protocol.candidates
        if candidate_ids is None or item.id in candidate_ids
    )
    candidates = CandidateSet(
        [
            Candidate(item.id, item.target, item.safe_fallback)
            for item in declared_candidates
        ]
    )
    target = scenario.context.target
    selected_candidate = candidate_id or scenario.leader_id
    source_id = f"scout:{scenario.namespace}:attention:{selected_candidate}"
    trace_id = f"trace:{scenario.namespace}:attention"
    scout = ScoutReport(
        source_id,
        selected_candidate,
        f"evidence:{scenario.namespace}:attention",
        f"runtime:{scenario.namespace}:attention",
        target=target,
        trace_event_id=trace_id,
        verification=verify_signal_input(
            target=target,
            source_id=source_id,
            subject_id=selected_candidate,
            verifier_id="governance:hybrid-total-evaluation",
            authority=AuthorityLevel.GOVERNANCE,
            provenance=f"urn:pheroos:{scenario.namespace}:attention-verification",
            trace_event_id=f"{trace_id}:verified",
        ),
    )
    inputs = {
        "protocol_id": scenario.manifest.protocol.id,
        "candidate_set": candidates,
        "policy": policy,
        "target": target,
        "current_step": step,
        "scout_reports": [scout],
        "topology": PheromoneNeighborhood(
            subjects=[
                PheromoneSubject("candidate", item.id, item.id, target)
                for item in declared_candidates
            ],
            edges=[],
        ),
        "fallback_candidate_id": scenario.fallback_id,
    }
    return evaluate_hybrid_attention_step(**inputs)


def _total_request(
    *,
    stable: bool,
    scenario=None,
    attention_candidate: str | None = None,
) -> HybridCommitEvaluationRequest:
    scenario = scenario or _scenario()
    state = initialize_commit_window_state(
        commit_policy=scenario.policy,
        profile=scenario.profile,
        assurance=scenario.assurance,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        protocol_id=scenario.protocol_id,
        run_id=scenario.run_id,
        target=scenario.target,
        epoch=scenario.epoch,
        risk_assessment_root=scenario.context.risk_assessment_fingerprint,
        membership_root=scenario.context.membership_root,
        threshold_snapshot=scenario.threshold,
        current_step=4,
        issuer_id="governance:hybrid-total-window",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:pheroos:{scenario.namespace}:window",
        trace_event_id=f"trace:{scenario.namespace}:window",
    )
    first = assess_reference_scenario(
        scenario,
        step=5,
        suffix="total:first",
    )
    state = advance_commit_window_state(
        state,
        assessment=first,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        current_step=5,
    )
    if stable:
        assessment = assess_reference_scenario(
            scenario,
            step=6,
            suffix="total:stable",
        )
        state = advance_commit_window_state(
            state,
            assessment=assessment,
            commit_policy=scenario.policy,
            threshold_snapshot=scenario.threshold,
            current_step=6,
        )
        step = 6
    else:
        assessment = first
        step = 5
    attention, directive = _attention(
        scenario,
        step=step,
        candidate_id=attention_candidate,
    )
    return HybridCommitEvaluationRequest(
        request_version=HYBRID_COMMIT_EVALUATION_REQUEST_VERSION,
        request_id=f"total-evaluation:{scenario.run_id}:{step}",
        attention=attention,
        exploration_directive=directive,
        commit_assessment=assessment,
        context=scenario.context,
        window_state=state,
        replay_state=scenario.replay_state,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        support_replay_state=scenario.support_replay_state,
        current_step=step,
        output_payload_fingerprint=commit_payload_fingerprint(
            {"candidate_id": scenario.leader_id, "run_id": scenario.run_id},
            schema="pheroos-test-total-output-v1",
            profile=assessment.profile,
        ),
        issuer_id="governance:total-evaluator",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:test:total-evaluator:{scenario.run_id}",
        trace_event_id=f"trace:total-evaluator:{scenario.run_id}",
        publish_stop_resolution=scenario.stop_resolution,
        prior_trace_events=_authority_trace(scenario),
    )


def _scenario_with_resigned_replay_descendant(scenario):
    leader = next(
        item
        for item in scenario.candidate_inputs
        if item.candidate_id == scenario.leader_id
    )
    extra = issue_reference_observation(
        scenario.namespace,
        index=91,
        principal=scenario.principals[0],
        candidate_id=scenario.leader_id,
        claim_fingerprint=scenario.claims[scenario.leader_id],
        profile=scenario.profile,
        assurance=scenario.assurance,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        protocol_id=scenario.protocol_id,
        run_id=scenario.run_id,
        target=scenario.target,
        epoch=scenario.epoch,
        evidence_policy=scenario.policy.evidence_qualification,
    )
    positives = (*leader.positive_observations, extra)
    binding = bind_evidence(
        evidence_id=f"evidence:{scenario.namespace}:replay-descendant",
        profile=scenario.profile,
        assurance=scenario.assurance,
        manifest_root=scenario.manifest_root,
        commit_policy_root=scenario.commit_policy_root,
        protocol_id=scenario.protocol_id,
        run_id=scenario.run_id,
        target=scenario.target,
        candidate_id=scenario.leader_id,
        claim_fingerprint=leader.claim_fingerprint,
        epoch=scenario.epoch,
        positive_observations=positives,
        counter_observations=leader.counter_observations,
        dispositions=leader.dispositions,
        challenges=leader.challenges,
        issuer_id="governance:hybrid-total-evidence-binding",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=5,
        provenance=f"urn:pheroos:{scenario.namespace}:replay-descendant-binding",
        trace_event_id=f"trace:{scenario.namespace}:replay-descendant-binding",
    )
    expanded_leader = CandidateCommitInput(
        candidate_id=leader.candidate_id,
        claim_fingerprint=leader.claim_fingerprint,
        evidence_binding=binding,
        positive_observations=positives,
        counter_observations=leader.counter_observations,
        dispositions=leader.dispositions,
        challenges=leader.challenges,
    )
    inputs = tuple(
        expanded_leader if item.candidate_id == scenario.leader_id else item
        for item in scenario.candidate_inputs
    )
    replay = record_commit_replay_receipts(
        scenario.replay_state,
        current_step=5,
        receipts=build_commit_replay_receipts(inputs, scenario.leases),
    )
    context = issue_commit_evaluation_context(
        scenario.manifest,
        context_id=f"context:{scenario.namespace}:replay-descendant",
        profile=scenario.profile,
        assurance=scenario.assurance,
        run_id=scenario.run_id,
        target=scenario.target,
        epoch=scenario.epoch,
        candidate_claims=scenario.claims,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        replay_state=replay,
        support_replay_state=scenario.support_replay_state,
        issuer_id="governance:hybrid-total-context",
        authority=AuthorityLevel.GOVERNANCE,
        current_step=5,
        provenance=f"urn:pheroos:{scenario.namespace}:replay-descendant-context",
        trace_event_id=f"trace:{scenario.namespace}:replay-descendant-context",
    )
    stop, permission = issue_reference_action_gates(
        scenario.namespace,
        context=context,
        action=CommitAction.COMMIT,
        blocked=False,
        current_step=5,
        expires_at_step=20,
        suffix="replay-descendant",
    )
    observations = dict(scenario.observations)
    observations[scenario.leader_id] = positives
    bindings = dict(scenario.bindings)
    bindings[scenario.leader_id] = binding
    return replace(
        scenario,
        observations=observations,
        bindings=bindings,
        candidate_inputs=inputs,
        replay_state=replay,
        context=context,
        stop_resolution=stop,
        permission=permission,
    )


def _distributed_fixture(*, witness_count: int, variant: str):
    policy = _higher_assurance_policy(CommitAssurance.DISTRIBUTED)
    scenario = _scenario(
        commit_policy=policy,
        profile=DISTRIBUTED_COMMIT_PROFILE_VERSION,
    )
    stable = build_reference_stable_commit(scenario, variant=variant)
    portable = build_reference_portable_commit(stable, variant=variant)
    bundle = build_reference_distributed_commit(
        portable,
        witness_count=witness_count,
        variant=variant,
    )
    return bundle


def _distributed_request(
    bundle,
    *,
    distributed_state=None,
    distributed_certificate=None,
    prior_trace_events=None,
    suffix: str,
    current_step: int | None = None,
) -> HybridCommitEvaluationRequest:
    portable = bundle.portable
    stable = portable.stable
    scenario = stable.scenario
    step = (
        stable.window.last_evaluated_step
        if current_step is None
        else current_step
    )
    attention, directive = _attention(
        scenario,
        step=stable.window.last_evaluated_step,
    )
    return HybridCommitEvaluationRequest(
        request_version=HYBRID_COMMIT_EVALUATION_REQUEST_VERSION,
        request_id=f"distributed-total:{scenario.run_id}:{suffix}",
        attention=attention,
        exploration_directive=directive,
        commit_assessment=stable.assessments[-1],
        context=scenario.context,
        window_state=stable.window,
        replay_state=scenario.replay_state,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        support_replay_state=scenario.support_replay_state,
        current_step=step,
        output_payload_fingerprint=stable.output_fingerprint,
        issuer_id="governance:distributed-total-evaluator",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:test:distributed-total:{scenario.run_id}:{suffix}",
        trace_event_id=f"trace:distributed-total:{scenario.run_id}:{suffix}",
        local_receipt=stable.receipt,
        evidence_certificate=portable.certificate,
        distributed_state=(
            bundle.state if distributed_state is None else distributed_state
        ),
        distributed_certificate=distributed_certificate,
        issuer_attestation_refs=portable.certificate.issuer_attestation_refs,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        trusted_witness_attestations=bundle.trusted_witness_attestations,
        prior_trace_events=(
            _authority_trace(scenario)
            if prior_trace_events is None
            else tuple(prior_trace_events)
        ),
    )


def _distributed_witness_event(
    scenario,
    verification,
    *,
    portable_event: TraceEvent,
) -> TraceEvent:
    witness = verification.witness
    return _event(
        scenario,
        "quorum_witness",
        step=verification.verified_at_step,
        record_schema=WITNESS_VERIFICATION_VERSION,
        record_payload=witness_verification_payload(verification),
        details={
            "proposal_digest": witness.proposal_digest,
            "commit_value_root": witness.commit_value_root,
            "principal_cluster_id": witness.principal_cluster_id,
            "failure_domain": witness.failure_domain,
            "verified": True,
            "expires_at_step": verification.expires_at_step,
        },
        previous=(portable_event,),
    )


def _distributed_certificate_event(
    scenario,
    certificate,
    *,
    window_event: TraceEvent,
    witness_events: tuple[TraceEvent, ...],
) -> TraceEvent:
    return _event(
        scenario,
        "commit_certificate_issued",
        step=certificate.issued_at_step,
        record_schema=DISTRIBUTED_COMMIT_CERTIFICATE_VERSION,
        record_payload=distributed_commit_certificate_payload(certificate),
        details={
            "certificate_kind": "distributed_commit",
            "candidate_id": certificate.candidate_id,
            "claim_fingerprint": certificate.proposal.claim_fingerprint,
            "output_fingerprint": certificate.proposal.output_payload_fingerprint,
            "commit_value_root": certificate.commit_value_root,
            "final": True,
        },
        previous=(window_event, *witness_events),
    )


def _action_facts(
    result,
    *,
    action: CommitAction,
    suffix: str,
    target: str | None = None,
    run_id: str | None = None,
    issued_at_step: int | None = None,
    expires_at_step: int | None = None,
    blocked: bool = False,
):
    outcome = result.decision_outcome
    selected_target = target or outcome.target
    selected_run = run_id or outcome.run_id
    issued = result.current_step if issued_at_step is None else issued_at_step
    expires = issued + 5 if expires_at_step is None else expires_at_step
    stop = verify_stop_resolution(
        StopResolution(
            target=selected_target,
            action=action,
            blocked=blocked,
            reason="blocked" if blocked else "all_hard_stops_resolved",
        ),
        resolution_id=f"stop:{outcome.run_id}:{suffix}",
        profile=outcome.profile,
        assurance=outcome.assurance,
        manifest_root=outcome.manifest_root,
        commit_policy_root=outcome.commit_policy_root,
        protocol_id=outcome.protocol_id,
        run_id=selected_run,
        epoch=outcome.epoch,
        decision_ref=decision_outcome_fingerprint(outcome),
        certificate_ref=outcome.certificate_ref,
        resolved_stop_root=_root(f"stop-root:{outcome.run_id}:{suffix}"),
        verifier_id="governance:hybrid-total-action",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=issued,
        expires_at_step=expires,
        provenance=f"urn:pheroos:{outcome.run_id}:stop:{suffix}",
        trace_event_id=f"trace:{outcome.run_id}:stop:{suffix}",
    )
    permission = issue_action_permission(
        permission_id=f"permission:{outcome.run_id}:{suffix}",
        profile=outcome.profile,
        assurance=outcome.assurance,
        manifest_root=outcome.manifest_root,
        commit_policy_root=outcome.commit_policy_root,
        protocol_id=outcome.protocol_id,
        run_id=selected_run,
        target=selected_target,
        action=action,
        epoch=outcome.epoch,
        decision_ref=decision_outcome_fingerprint(outcome),
        certificate_ref=outcome.certificate_ref,
        allowed=not blocked,
        reason_codes=("denied",) if blocked else ("policy_authorized",),
        issuer_id="governance:hybrid-total-action",
        policy_ref="policy:hybrid-total-action-v1",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=issued,
        expires_at_step=expires,
        provenance=f"urn:pheroos:{outcome.run_id}:permission:{suffix}",
        trace_event_id=f"trace:{outcome.run_id}:permission:{suffix}",
    )
    return stop, permission


def test_deprecated_total_entry_is_only_a_warning_alias() -> None:
    request = object()

    with pytest.warns(DeprecationWarning, match="evaluate_hybrid_commit_step"):
        legacy = evaluate_hybrid_commit_evaluation(request)
    canonical = evaluate_hybrid_commit_step(request=request)

    assert hybrid_commit_evaluation_payload(legacy) == hybrid_commit_evaluation_payload(
        canonical
    )


def test_total_entry_returns_authoritative_progress_without_assurance_downgrade() -> None:
    request = _total_request(stable=False)
    result = evaluate_hybrid_commit_step(request=request)

    assert result.status is HybridCommitEvaluationStatus.PROGRESS
    assert result.authoritative and not result.terminal
    assert not result.assurance_downgraded
    assert result.decision_progress is not None
    assert result.decision_outcome is None
    assert not result.local_receipt_ref
    assert hybrid_commit_evaluation_is_authoritative(result)
    replay = replay_commit_trace(result.trace_events, require_complete=False)
    assert replay.event_types[-1] == "quorum_pending"


def test_authority_verifier_checks_verified_attention_channel_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = evaluate_hybrid_commit_step(request=_total_request(stable=False))
    calls = {"attention": 0, "directive": 0}
    original_attention = commit_module.attention_breakdown_is_authoritative
    original_directive = commit_module.exploration_directive_is_authoritative

    def check_attention(value: object) -> bool:
        calls["attention"] += 1
        return original_attention(value)

    def check_directive(value: object, **kwargs: object) -> bool:
        calls["directive"] += 1
        assert kwargs == {}
        return original_directive(value, **kwargs)

    monkeypatch.setattr(
        commit_module,
        "attention_breakdown_is_authoritative",
        check_attention,
    )
    monkeypatch.setattr(
        commit_module,
        "exploration_directive_is_authoritative",
        check_directive,
    )

    assert hybrid_commit_evaluation_is_authoritative(result)
    assert calls == {"attention": 1, "directive": 1}


def test_total_entry_consumes_resigned_current_replay_snapshot_only() -> None:
    original = _scenario()
    evolved = _scenario_with_resigned_replay_descendant(original)
    request = _total_request(stable=False, scenario=evolved)

    result = evaluate_hybrid_commit_step(request=request)

    assert result.status is HybridCommitEvaluationStatus.PROGRESS
    assert result.authoritative and not result.terminal
    assert result.context_ref == result.commit_assessment.context_fingerprint
    assert result.replay_state_ref == result.commit_assessment.replay_state_fingerprint
    assert result.replay_root == result.commit_assessment.replay_receipt_root
    assert hybrid_commit_evaluation_is_authoritative(result)

    stale_context = evaluate_hybrid_commit_step(
        request=replace(
            request,
            request_id=f"{request.request_id}:stale-context",
            context=original.context,
        )
    )
    assert stale_context.status is HybridCommitEvaluationStatus.INVALID
    assert stale_context.terminal and not stale_context.authoritative

    stale_replay = evaluate_hybrid_commit_step(
        request=replace(
            request,
            request_id=f"{request.request_id}:stale-replay",
            replay_state=original.replay_state,
        )
    )
    assert stale_replay.status is HybridCommitEvaluationStatus.INVALID
    assert stale_replay.terminal and not stale_replay.authoritative

    cross_run = _scenario()
    cross_run_replay = evaluate_hybrid_commit_step(
        request=replace(
            request,
            request_id=f"{request.request_id}:cross-run-replay",
            replay_state=cross_run.replay_state,
        )
    )
    assert cross_run_replay.status is HybridCommitEvaluationStatus.INVALID
    assert cross_run_replay.terminal and not cross_run_replay.authoritative


def test_total_entry_issues_local_commit_delivers_and_denies_unscoped_actions() -> None:
    request = _total_request(stable=True)
    result = evaluate_hybrid_commit_step(request=request)

    assert result.status is HybridCommitEvaluationStatus.OUTCOME
    assert result.authoritative and result.terminal
    assert result.decision_outcome.kind.value == "evidence_commit"
    assert result.local_receipt_ref == result.decision_outcome.certificate_ref
    assert result.deliver_authorization.authorized
    assert not result.publish_authorization.authorized
    assert not result.execute_authorization.authorized
    assert hybrid_commit_evaluation_is_authoritative(result)
    replay = replay_commit_trace(result.trace_events, require_complete=True)
    assert replay.outcome_ref == result.outcome_ref
    assert replay.event_types[-1] == "output_decided"


def test_noncanonical_request_returns_explicit_non_authoritative_invalid_envelope() -> None:
    result = evaluate_hybrid_commit_step(request={"malformed": True})
    assert result.status is HybridCommitEvaluationStatus.INVALID
    assert result.terminal and not result.authoritative
    assert result.decision_outcome is None
    assert not hybrid_commit_evaluation_is_authoritative(result)
    assert hybrid_commit_evaluation_payload(result)["evaluation_root"]


def test_malformed_runtime_record_with_valid_authority_issues_invalid_and_delivers() -> None:
    request = replace(
        _total_request(stable=True),
        evidence_certificate=object(),
    )
    result = evaluate_hybrid_commit_step(request=request)

    assert result.status is HybridCommitEvaluationStatus.INVALID
    assert result.authoritative and result.terminal
    assert result.decision_outcome.kind.value == "invalid"
    assert "invalid_finality_record" in result.decision_outcome.reason_codes
    assert result.deliver_authorization.authorized
    assert not result.publish_authorization.authorized
    assert not result.execute_authorization.authorized
    assert hybrid_commit_evaluation_is_authoritative(result)
    replay = replay_commit_trace(result.trace_events, require_complete=True)
    assert replay.outcome_kind == "invalid"


def test_request_ref_binds_every_trust_map_value_and_action_authority_leaf() -> None:
    request = _total_request(stable=False)
    base = hybrid_commit_evaluation_request_fingerprint(request)
    changed_trust = replace(
        request,
        trusted_issuer_attestations={"attestation:a": _root("body:a")},
    )
    changed_action = replace(
        request,
        publish_stop_resolution=None,
    )
    assert hybrid_commit_evaluation_request_fingerprint(changed_trust) != base
    assert hybrid_commit_evaluation_request_fingerprint(changed_action) != base


def test_deadline_total_entry_returns_deliverable_declared_safe_fallback() -> None:
    request = _total_request(stable=False)
    deadline = request.window_state.absolute_deadline_step
    result = evaluate_hybrid_commit_step(
        request=replace(request, current_step=deadline)
    )

    assert result.status is HybridCommitEvaluationStatus.OUTCOME
    assert result.authoritative and result.terminal
    assert result.decision_outcome.kind.value == "safe_fallback"
    assert result.decision_outcome.candidate_id == "candidate:fallback"
    assert "deadline_reached" in result.decision_outcome.reason_codes
    assert result.deliver_authorization.authorized
    assert not result.publish_authorization.authorized
    assert not result.execute_authorization.authorized
    assert result.attention.source_step is request.attention.source_step
    assert result.commit_assessment is request.commit_assessment
    assert result.commit_window_state is request.window_state
    assert hybrid_commit_evaluation_is_authoritative(result)
    replay_commit_trace(result.trace_events, require_complete=True)


@pytest.mark.parametrize(
    ("field_name", "invalid_commit_input"),
    (
        ("attention", False),
        ("exploration_directive", False),
        ("evidence_certificate", True),
        ("publish_stop_resolution", False),
        ("publish_permission", False),
        ("execute_stop_resolution", False),
        ("execute_permission", False),
    ),
)
def test_malformed_runtime_leaves_never_escape_and_terminal_delivery_is_total(
    field_name: str,
    invalid_commit_input: bool,
) -> None:
    request = _total_request(stable=True)
    baseline = (
        evaluate_hybrid_commit_step(request=request)
        if field_name in {"attention", "exploration_directive"}
        else None
    )
    result = evaluate_hybrid_commit_step(
        request=replace(request, **{field_name: object()})
    )

    assert result.authoritative and result.terminal
    assert result.deliver_authorization.authorized
    assert not result.publish_authorization.authorized
    assert not result.execute_authorization.authorized
    if invalid_commit_input:
        assert result.status is HybridCommitEvaluationStatus.INVALID
        assert result.decision_outcome.kind.value == "invalid"
    else:
        assert result.status is HybridCommitEvaluationStatus.OUTCOME
        assert result.decision_outcome.kind.value == "evidence_commit"
    if field_name in {"attention", "exploration_directive"}:
        assert baseline is not None
        assert result.attention_status is HybridCommitAttentionStatus.UNAVAILABLE
        assert not result.binding_step_ref
        assert result.binding_step is None
        assert not result.attention_ref
        assert not result.exploration_directive_ref
        channel_diagnostics = tuple(
            item
            for item in result.diagnostics
            if item.code == "attention_channel_unavailable"
        )
        assert len(channel_diagnostics) == 1
        assert channel_diagnostics[0].fatal is False
        assert channel_diagnostics[0].stage == field_name
        assert result.outcome_ref == baseline.outcome_ref
        assert result.local_receipt_ref == baseline.local_receipt_ref
        assert result.finality_verification_ref == baseline.finality_verification_ref
        assert result.deliver_authorization_ref == baseline.deliver_authorization_ref
        assert result.trace_root == baseline.trace_root
        assert result.request_ref != baseline.request_ref
        assert result.evaluation_root != baseline.evaluation_root
    assert hybrid_commit_evaluation_is_authoritative(result)


@pytest.mark.parametrize(
    ("variant", "expected_stage"),
    (
        ("missing_attention", "attention"),
        ("malformed_attention", "attention"),
        ("missing_directive", "exploration_directive"),
        ("malformed_directive", "exploration_directive"),
        ("cross_step", "channel_binding"),
        ("candidate_coverage", "channel_binding"),
    ),
)
def test_attention_unavailability_is_audited_without_commit_sensitivity(
    variant: str,
    expected_stage: str,
) -> None:
    scenario = _scenario()
    request = _total_request(stable=False, scenario=scenario)
    baseline = evaluate_hybrid_commit_step(request=request)
    changes: dict[str, object]
    if variant == "missing_attention":
        changes = {"attention": None}
    elif variant == "malformed_attention":
        changes = {"attention": object()}
    elif variant == "missing_directive":
        changes = {"exploration_directive": None}
    elif variant == "malformed_directive":
        changes = {"exploration_directive": object()}
    elif variant == "cross_step":
        attention, directive = _attention(
            scenario,
            step=request.current_step - 1,
        )
        changes = {
            "attention": attention,
            "exploration_directive": directive,
        }
    else:
        attention, directive = _attention(
            scenario,
            step=request.current_step,
            candidate_ids={scenario.leader_id, scenario.fallback_id},
        )
        changes = {
            "attention": attention,
            "exploration_directive": directive,
        }

    result = evaluate_hybrid_commit_step(request=replace(request, **changes))

    assert baseline.attention_status is HybridCommitAttentionStatus.VERIFIED
    assert baseline.binding_step_ref
    assert result.attention_status is HybridCommitAttentionStatus.UNAVAILABLE
    assert result.authoritative and not result.terminal
    assert result.status is HybridCommitEvaluationStatus.PROGRESS
    assert not result.binding_step_ref
    assert not result.attention_ref
    assert not result.exploration_directive_ref
    channel = tuple(
        item
        for item in result.diagnostics
        if item.code == "attention_channel_unavailable"
    )
    assert len(channel) == 1
    assert channel[0].stage == expected_stage
    assert channel[0].severity.value == "warning"
    assert channel[0].fatal is False
    assert result.progress_ref == baseline.progress_ref
    assert result.outcome_ref == baseline.outcome_ref == ""
    assert result.window_state_ref == baseline.window_state_ref
    assert result.local_receipt_ref == baseline.local_receipt_ref
    assert result.evidence_certificate_ref == baseline.evidence_certificate_ref
    assert result.finality_verification_ref == baseline.finality_verification_ref
    assert result.trace_event_ids == baseline.trace_event_ids
    assert result.trace_root == baseline.trace_root
    assert result.request_ref != baseline.request_ref
    assert result.evaluation_root != baseline.evaluation_root
    assert hybrid_commit_evaluation_is_authoritative(result)
    replay_commit_trace(result.trace_events, require_complete=False)


def test_missing_and_malformed_attention_have_distinct_safe_request_roots() -> None:
    request = _total_request(stable=False)
    missing = replace(request, attention=None)
    malformed = replace(request, attention=object())

    assert hybrid_commit_evaluation_request_fingerprint(missing) != (
        hybrid_commit_evaluation_request_fingerprint(malformed)
    )


def test_unavailable_attention_does_not_change_deadline_outcome_or_output() -> None:
    request = _total_request(stable=False)
    deadline_request = replace(
        request,
        current_step=request.window_state.absolute_deadline_step,
    )
    baseline = evaluate_hybrid_commit_step(request=deadline_request)
    unavailable = evaluate_hybrid_commit_step(
        request=replace(
            deadline_request,
            attention=None,
            exploration_directive=None,
        )
    )

    assert unavailable.attention_status is HybridCommitAttentionStatus.UNAVAILABLE
    assert unavailable.status is HybridCommitEvaluationStatus.OUTCOME
    assert unavailable.decision_outcome.kind.value == "safe_fallback"
    assert unavailable.outcome_ref == baseline.outcome_ref
    assert unavailable.outcome_certificate_ref == baseline.outcome_certificate_ref
    assert unavailable.deliver_authorization_ref == baseline.deliver_authorization_ref
    assert unavailable.publish_authorization_ref == baseline.publish_authorization_ref
    assert unavailable.execute_authorization_ref == baseline.execute_authorization_ref
    assert unavailable.trace_root == baseline.trace_root
    assert hybrid_commit_evaluation_is_authoritative(unavailable)


def test_certified_late_finality_ignores_unavailable_attention() -> None:
    policy = _higher_assurance_policy(CommitAssurance.CERTIFIED)
    scenario = _scenario(
        commit_policy=policy,
        profile=CERTIFIED_COMMIT_PROFILE_VERSION,
    )
    stable = build_reference_stable_commit(scenario, variant="attention-late")
    portable = build_reference_portable_commit(stable, variant="attention-late")
    sealed_step = stable.window.last_evaluated_step
    attention, directive = _attention(scenario, step=sealed_step)
    first_request = HybridCommitEvaluationRequest(
        request_version=HYBRID_COMMIT_EVALUATION_REQUEST_VERSION,
        request_id=f"attention-late:{scenario.run_id}:{sealed_step}",
        attention=attention,
        exploration_directive=directive,
        commit_assessment=stable.assessments[-1],
        context=scenario.context,
        window_state=stable.window,
        replay_state=scenario.replay_state,
        commit_policy=scenario.policy,
        risk_chain_state=scenario.risk_chain_state,
        risk_assessment=scenario.risk_assessment,
        threshold_snapshot=scenario.threshold,
        membership_snapshot=scenario.membership_snapshot,
        membership_epoch_state=scenario.membership_state,
        support_replay_state=scenario.support_replay_state,
        current_step=sealed_step,
        output_payload_fingerprint=stable.output_fingerprint,
        issuer_id="governance:attention-late",
        authority=AuthorityLevel.GOVERNANCE,
        provenance=f"urn:test:attention-late:{scenario.run_id}",
        trace_event_id=f"trace:attention-late:{scenario.run_id}:{sealed_step}",
        local_receipt=stable.receipt,
        prior_trace_events=_authority_trace(scenario),
    )
    pending = evaluate_hybrid_commit_step(request=first_request)
    assert pending.status is HybridCommitEvaluationStatus.PROGRESS

    final = evaluate_hybrid_commit_step(
        request=replace(
            first_request,
            request_id=f"attention-late:{scenario.run_id}:{sealed_step + 1}",
            attention=None,
            exploration_directive=None,
            current_step=sealed_step + 1,
            previous_progress=pending.decision_progress,
            evidence_certificate=portable.certificate,
            issuer_attestation_refs=portable.certificate.issuer_attestation_refs,
            trusted_issuer_attestations=portable.trusted_issuer_attestations,
            prior_trace_events=pending.trace_events,
            trace_event_id=f"trace:attention-late:{scenario.run_id}:{sealed_step + 1}",
        )
    )

    assert final.attention_status is HybridCommitAttentionStatus.UNAVAILABLE
    assert final.status is HybridCommitEvaluationStatus.OUTCOME
    assert final.decision_outcome.kind.value == "evidence_commit"
    assert final.evidence_certificate_ref
    assert final.finality_verification_ref
    assert final.deliver_authorization.authorized
    assert final.trace_events
    assert hybrid_commit_evaluation_is_authoritative(final)
    replay_commit_trace(final.trace_events, require_complete=True)


def test_attention_status_shape_rejects_missing_diagnostic_and_injected_refs() -> None:
    request = _total_request(stable=False)
    unavailable = evaluate_hybrid_commit_step(
        request=replace(request, attention=None)
    )

    with pytest.raises(
        GovernanceError,
        match="requires one canonical diagnostic",
    ):
        replace(unavailable, diagnostics=())
    with pytest.raises(GovernanceError, match="cannot expose refs"):
        replace(unavailable, attention_ref=request.attention.attention_root)


def test_forged_missing_attention_binding_is_not_authoritative() -> None:
    request = _total_request(stable=False)
    verified = evaluate_hybrid_commit_step(request=request)
    unavailable = evaluate_hybrid_commit_step(
        request=replace(request, attention=None)
    )
    channel_diagnostic = next(
        item
        for item in unavailable.diagnostics
        if item.code == "attention_channel_unavailable"
    )

    object.__setattr__(
        verified,
        "attention_status",
        HybridCommitAttentionStatus.UNAVAILABLE,
    )
    object.__setattr__(verified, "binding_step", None)
    object.__setattr__(verified, "binding_step_ref", "")
    object.__setattr__(verified, "attention", None)
    object.__setattr__(verified, "attention_ref", "")
    object.__setattr__(verified, "exploration_directive", None)
    object.__setattr__(verified, "exploration_directive_ref", "")
    object.__setattr__(verified, "diagnostics", (channel_diagnostic,))

    assert not hybrid_commit_evaluation_is_authoritative(verified)


def test_malformed_prior_trace_uses_bound_fail_closed_request_ref() -> None:
    request = _total_request(stable=True)
    strict_ref = hybrid_commit_evaluation_request_fingerprint(request)
    object.__setattr__(request, "prior_trace_events", (object(),))

    result = evaluate_hybrid_commit_step(request=request)

    assert result.status is HybridCommitEvaluationStatus.INVALID
    assert result.authoritative and result.terminal
    assert result.request_ref != strict_ref
    assert result.deliver_authorization.authorized
    assert tuple(item.event_type for item in result.trace_events) == (
        "decision_outcome",
        "output_decided",
    )
    assert hybrid_commit_evaluation_is_authoritative(result)


def test_trace_generation_fault_returns_explicit_non_authoritative_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = replace(
        _total_request(stable=True),
        evidence_certificate=object(),
    )

    def fail_trace(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("injected trace failure")

    monkeypatch.setattr(evaluation_module, "_build_evaluation_trace", fail_trace)
    result = evaluate_hybrid_commit_step(request=request)

    assert result.status is HybridCommitEvaluationStatus.INVALID
    assert result.terminal and not result.authoritative
    assert result.decision_outcome is None
    assert any(
        item.code == "commit_trace_generation_failed"
        for item in result.diagnostics
    )
    assert not hybrid_commit_evaluation_is_authoritative(result)


def test_exact_request_replay_is_idempotent() -> None:
    request = _total_request(stable=True)
    first = evaluate_hybrid_commit_step(request=request)
    second = evaluate_hybrid_commit_step(request=request)

    assert hybrid_commit_evaluation_payload(second) == (
        hybrid_commit_evaluation_payload(first)
    )
    assert second.evaluation_root == first.evaluation_root
    assert second.trace_event_ids == first.trace_event_ids
    assert hybrid_commit_evaluation_is_authoritative(second)


def test_attention_changes_do_not_change_commit_progress_or_trace_truth() -> None:
    scenario = _scenario()
    request = _total_request(
        stable=False,
        scenario=scenario,
        attention_candidate=scenario.leader_id,
    )
    changed_attention, changed_directive = _attention(
        scenario,
        step=request.current_step,
        candidate_id=scenario.other_id,
    )
    changed_request = replace(
        request,
        attention=changed_attention,
        exploration_directive=changed_directive,
    )

    base = evaluate_hybrid_commit_step(request=request)
    changed = evaluate_hybrid_commit_step(request=changed_request)

    assert base.attention_ref != changed.attention_ref
    assert base.binding_step_ref != changed.binding_step_ref
    assert base.progress_ref == changed.progress_ref
    assert base.outcome_ref == changed.outcome_ref == ""
    assert base.window_state_ref == changed.window_state_ref
    assert base.trace_event_ids == changed.trace_event_ids
    assert base.trace_root == changed.trace_root
    assert base.request_ref != changed.request_ref
    assert hybrid_commit_evaluation_is_authoritative(base)
    assert hybrid_commit_evaluation_is_authoritative(changed)


def test_request_mapping_permutations_are_canonical() -> None:
    first = _root("attestation:first")
    second = _root("attestation:second")
    request = _total_request(stable=False)
    left = replace(
        request,
        trusted_issuer_attestations={"attestation:a": first, "attestation:b": second},
        trusted_witness_attestations={"witness:a": first, "witness:b": second},
    )
    right = replace(
        request,
        trusted_issuer_attestations={"attestation:b": second, "attestation:a": first},
        trusted_witness_attestations={"witness:b": second, "witness:a": first},
    )
    assert hybrid_commit_evaluation_request_fingerprint(left) == (
        hybrid_commit_evaluation_request_fingerprint(right)
    )


@pytest.mark.parametrize(
    "field_name",
    (
        "binding_step",
        "attention",
        "exploration_directive",
        "commit_assessment",
        "commit_window_state",
        "commit_replay_state",
        "decision_progress",
        "decision_outcome",
        "local_receipt",
        "evidence_certificate",
        "distributed_state",
        "distributed_certificate",
        "outcome_certificate",
        "finality_verification",
        "deliver_authorization",
        "publish_authorization",
        "execute_authorization",
        "trace_events",
    ),
)
def test_embedded_runtime_substitution_breaks_evaluation_authority(
    field_name: str,
) -> None:
    result = evaluate_hybrid_commit_step(request=_total_request(stable=True))
    object.__setattr__(result, field_name, () if field_name == "trace_events" else object())
    assert not hybrid_commit_evaluation_is_authoritative(result)


def test_gate_failure_reset_trace_has_unique_complete_predecessors() -> None:
    scenario = _scenario()
    request = _total_request(stable=False, scenario=scenario)
    prior = evaluate_hybrid_commit_step(request=request)
    assert prior.status is HybridCommitEvaluationStatus.PROGRESS
    stop, permission = issue_reference_action_gates(
        scenario.namespace,
        context=scenario.context,
        action=CommitAction.COMMIT,
        blocked=True,
        current_step=6,
        expires_at_step=20,
        suffix="total-reset",
    )
    assessment = assess_reference_scenario(
        scenario,
        step=6,
        suffix="total:gate-reset",
        stop_resolution=stop,
        permission=permission,
    )
    attention, directive = _attention(scenario, step=6)
    stop_event = _event(
        scenario,
        "stop_resolution_verified",
        step=6,
        record_schema="pheroos-stop-resolution-verification-v1",
        record_payload=stop_resolution_verification_payload(stop),
        details={
            "action": stop.action.value,
            "blocked": stop.blocked,
            "expires_at_step": stop.expires_at_step,
        },
    )
    permission_event = _event(
        scenario,
        "action_permission_issued",
        step=6,
        record_schema="pheroos-action-permission-v1",
        record_payload=action_permission_payload(permission),
        details={
            "action": permission.action.value,
            "allowed": permission.allowed,
            "expires_at_step": permission.expires_at_step,
        },
    )
    reset_request = replace(
        request,
        request_id=f"{request.request_id}:gate-reset",
        attention=attention,
        exploration_directive=directive,
        commit_assessment=assessment,
        current_step=6,
        prior_trace_events=tuple(
            (*prior.trace_events, stop_event, permission_event)
        ),
    )

    result = evaluate_hybrid_commit_step(request=reset_request)

    reset_event = next(
        item for item in result.trace_events if item.event_type == "commit_window_reset"
    )
    predecessors = tuple(reset_event.lineage["previous_event_ids"])
    assert len(predecessors) == len(set(predecessors))
    assert reset_event.lineage["prior_window_ref"] == (
        evaluation_module.commit_window_state_fingerprint(request.window_state)
    )
    assert result.commit_window_state.reset_reason == "gate_failure"
    assert hybrid_commit_evaluation_is_authoritative(result)
    replay_commit_trace(result.trace_events, require_complete=True)


def test_exact_publish_action_facts_are_certificate_bound_and_trace_replayable() -> None:
    request = _total_request(stable=True)
    base = evaluate_hybrid_commit_step(request=request)
    stop, permission = _action_facts(
        base,
        action=CommitAction.PUBLISH,
        suffix="publish-exact",
    )
    published = evaluate_hybrid_commit_step(
        request=replace(
            request,
            publish_stop_resolution=stop,
            publish_permission=permission,
        )
    )

    assert published.deliver_authorization.authorized
    assert published.publish_authorization.authorized
    assert not published.execute_authorization.authorized
    stop_ref = stop_resolution_verification_fingerprint(stop)
    permission_ref = action_permission_fingerprint(permission)
    stop_event = next(
        item
        for item in published.trace_events
        if item.event_type == "stop_resolution_verified"
        and item.lineage["record_ref"] == stop_ref
    )
    permission_event = next(
        item
        for item in published.trace_events
        if item.event_type == "action_permission_issued"
        and item.lineage["record_ref"] == permission_ref
    )
    output_event = published.trace_events[-1]
    assert {stop_event.lineage["event_id"], permission_event.lineage["event_id"]}.issubset(
        output_event.lineage["previous_event_ids"]
    )
    assert output_event.lineage["publish"] is True
    assert hybrid_commit_evaluation_is_authoritative(published)
    replay_commit_trace(published.trace_events, require_complete=True)


@pytest.mark.parametrize(
    "variant",
    ("cross_target", "cross_action", "future", "expired"),
)
def test_invalid_current_action_scope_denies_only_action_and_preserves_commit_trace(
    variant: str,
) -> None:
    request = _total_request(stable=True)
    base = evaluate_hybrid_commit_step(request=request)
    kwargs: dict[str, object] = {
        "action": CommitAction.PUBLISH,
        "suffix": f"publish-{variant}",
    }
    if variant == "cross_target":
        kwargs["target"] = "decision:other"
    elif variant == "cross_action":
        kwargs["action"] = CommitAction.COMMIT
    elif variant == "future":
        kwargs["issued_at_step"] = base.current_step + 1
        kwargs["expires_at_step"] = base.current_step + 5
    elif variant == "expired":
        kwargs["issued_at_step"] = base.current_step - 2
        kwargs["expires_at_step"] = base.current_step
    stop, permission = _action_facts(base, **kwargs)
    result = evaluate_hybrid_commit_step(
        request=replace(
            request,
            publish_stop_resolution=stop,
            publish_permission=permission,
        )
    )

    assert result.status is HybridCommitEvaluationStatus.OUTCOME
    assert result.decision_outcome.kind.value == "evidence_commit"
    assert result.deliver_authorization.authorized
    assert not result.publish_authorization.authorized
    assert hybrid_commit_evaluation_is_authoritative(result)
    replay_commit_trace(result.trace_events, require_complete=True)
    observed_refs = {item.lineage["record_ref"] for item in result.trace_events}
    if variant in {"cross_target", "future"}:
        assert stop_resolution_verification_fingerprint(stop) not in observed_refs
        assert action_permission_fingerprint(permission) not in observed_refs
    else:
        assert stop_resolution_verification_fingerprint(stop) in observed_refs
        assert action_permission_fingerprint(permission) in observed_refs


def test_distributed_zero_witness_state_is_provisional_with_portable_lineage() -> None:
    bundle = _distributed_fixture(witness_count=0, variant="zero-witness")
    result = evaluate_hybrid_commit_step(
        request=_distributed_request(bundle, suffix="zero-witness")
    )

    assert result.status is HybridCommitEvaluationStatus.PROGRESS
    assert result.authoritative and not result.terminal
    assert result.assurance is CommitAssurance.DISTRIBUTED
    assert not result.assurance_downgraded
    assert result.distributed_state_ref == distributed_commit_state_fingerprint(
        bundle.state
    )
    assert not result.distributed_certificate_ref
    assert "distributed_commit_certificate" in (
        result.decision_progress.next_required_inputs
    )
    provisional = next(
        item for item in result.trace_events if item.event_type == "commit_provisional"
    )
    portable = next(
        item
        for item in result.trace_events
        if item.event_type == "commit_certificate_issued"
        and item.lineage["certificate_kind"] == "evidence_commit"
    )
    assert provisional.lineage["witness_count"] == 0
    assert "proposal_digest" not in provisional.lineage
    assert provisional.lineage["portable_certificate_ref"] == (
        portable.lineage["certificate_ref"]
    )
    assert tuple(provisional.lineage["previous_event_ids"]) == (
        portable.lineage["event_id"],
    )
    assert hybrid_commit_evaluation_is_authoritative(result)
    replay_commit_trace(result.trace_events, require_complete=False)


def test_distributed_insufficient_quorum_keeps_exact_witness_proposal_lineage() -> None:
    bundle = _distributed_fixture(witness_count=1, variant="one-witness")
    result = evaluate_hybrid_commit_step(
        request=_distributed_request(bundle, suffix="one-witness")
    )

    assert result.status is HybridCommitEvaluationStatus.PROGRESS
    assert result.authoritative and not result.terminal
    provisional = next(
        item for item in result.trace_events if item.event_type == "commit_provisional"
    )
    witnesses = tuple(
        item for item in result.trace_events if item.event_type == "quorum_witness"
    )
    assert len(witnesses) == 1
    assert provisional.lineage["witness_count"] == 1
    assert provisional.lineage["proposal_digest"] == bundle.proposal.proposal_digest
    assert tuple(provisional.lineage["previous_event_ids"]) == tuple(
        item.lineage["event_id"] for item in witnesses
    )
    assert result.decision_progress.phase.value == "provisional"
    assert not result.assurance_downgraded
    assert hybrid_commit_evaluation_is_authoritative(result)
    replay_commit_trace(result.trace_events, require_complete=False)


def test_distributed_quorum_returns_terminal_commit_with_closed_lineage() -> None:
    bundle = _distributed_fixture(witness_count=3, variant="final-quorum")
    scenario = bundle.portable.stable.scenario
    certificate = issue_reference_distributed_certificate(
        bundle,
        witness_count=scenario.policy.distributed.witness_quorum,
        variant="final-quorum",
    )
    registered = register_distributed_commit_certificate(
        bundle.state,
        certificate,
        commit_policy=scenario.policy,
        portable_certificate=bundle.portable.certificate,
        trusted_issuer_attestations=bundle.portable.trusted_issuer_attestations,
        trusted_witness_attestations=bundle.trusted_witness_attestations,
        current_step=bundle.portable.stable.window.last_evaluated_step,
    )
    result = evaluate_hybrid_commit_step(
        request=_distributed_request(
            bundle,
            distributed_state=registered,
            distributed_certificate=certificate,
            suffix="final-quorum",
        )
    )

    certificate_ref = distributed_commit_certificate_fingerprint(certificate)
    assert result.status is HybridCommitEvaluationStatus.OUTCOME
    assert result.authoritative and result.terminal
    assert result.decision_outcome.kind.value == "evidence_commit"
    assert result.decision_outcome.certificate_ref == certificate_ref
    assert result.distributed_certificate_ref == certificate_ref
    assert result.deliver_authorization.authorized
    assert not result.publish_authorization.authorized
    distributed_event = next(
        item
        for item in result.trace_events
        if item.event_type == "commit_certificate_issued"
        and item.lineage["certificate_ref"] == certificate_ref
    )
    witness_ids = {
        item.lineage["event_id"]
        for item in result.trace_events
        if item.event_type == "quorum_witness"
    }
    assert len(witness_ids) == scenario.policy.distributed.witness_quorum
    assert witness_ids.issubset(distributed_event.lineage["previous_event_ids"])
    outcome_event = next(
        item for item in result.trace_events if item.event_type == "decision_outcome"
    )
    assert distributed_event.lineage["event_id"] in (
        outcome_event.lineage["previous_event_ids"]
    )
    assert hybrid_commit_evaluation_is_authoritative(result)
    replay_commit_trace(result.trace_events, require_complete=True)


def test_historical_distributed_evaluation_stays_verifiable_but_stale_state_cannot_publish() -> None:
    bundle = _distributed_fixture(witness_count=3, variant="historical-final")
    stable = bundle.portable.stable
    scenario = stable.scenario
    certificate = issue_reference_distributed_certificate(
        bundle,
        witness_count=scenario.policy.distributed.witness_quorum,
        variant="historical-final",
    )
    registered = register_distributed_commit_certificate(
        bundle.state,
        certificate,
        commit_policy=scenario.policy,
        portable_certificate=bundle.portable.certificate,
        trusted_issuer_attestations=bundle.portable.trusted_issuer_attestations,
        trusted_witness_attestations=bundle.trusted_witness_attestations,
        current_step=stable.window.last_evaluated_step,
    )
    result = evaluate_hybrid_commit_step(
        request=_distributed_request(
            bundle,
            distributed_state=registered,
            distributed_certificate=certificate,
            suffix="historical-final",
        )
    )
    record_witness_verifications(
        registered,
        (bundle.verifications[3],),
        current_step=stable.window.last_evaluated_step + 1,
    )

    assert hybrid_commit_evaluation_is_authoritative(result)
    stop, permission = _action_facts(
        result,
        action=CommitAction.PUBLISH,
        suffix="historical-stale-publish",
    )
    publication = authorize_terminal_publication(
        result.decision_outcome,
        commit_policy=scenario.policy,
        threshold_snapshot=scenario.threshold,
        certificate=certificate,
        output_payload_fingerprint=stable.output_fingerprint,
        stop_resolution=stop,
        permission=permission,
        current_step=result.current_step,
        trusted_issuer_attestations=bundle.portable.trusted_issuer_attestations,
        distributed_state=registered,
        portable_certificate=bundle.portable.certificate,
        trusted_witness_attestations=bundle.trusted_witness_attestations,
    )
    assert not publication.authorized
    assert publication.gates["certificate_valid"] is False


def test_same_value_distributed_retry_never_freezes_or_combines_proposal_quorums() -> None:
    bundle = _distributed_fixture(witness_count=3, variant="same-value-first")
    portable = bundle.portable
    stable = portable.stable
    scenario = stable.scenario
    quorum = scenario.policy.distributed.witness_quorum
    first = issue_reference_distributed_certificate(
        bundle,
        witness_count=quorum,
        variant="same-value-first",
    )
    first_state = register_distributed_commit_certificate(
        bundle.state,
        first,
        commit_policy=scenario.policy,
        portable_certificate=portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        trusted_witness_attestations=bundle.trusted_witness_attestations,
        current_step=stable.window.last_evaluated_step,
    )
    retry_proposal = issue_distributed_commit_proposal(
        stable.receipt,
        portable.certificate,
        scenario.membership_snapshot,
        scenario.membership_state,
        commit_policy=scenario.policy,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        proposal_id=f"proposal:{scenario.namespace}:same-value-retry",
        proposed_at_step=stable.window.last_evaluated_step,
    )
    retry_trust = dict(bundle.trusted_witness_attestations)
    retry_verifications = tuple(
        issue_reference_witness(
            scenario,
            retry_proposal,
            principal,
            index=200 + index,
            variant="same-value-retry",
            trusted_witness_attestations=retry_trust,
        )
        for index, principal in enumerate(scenario.principals[:quorum], start=1)
    )
    retry_state = record_witness_verifications(
        first_state,
        retry_verifications,
        current_step=stable.window.last_evaluated_step,
    )
    retry_certificate = assemble_portable_distributed_commit_certificate(
        retry_proposal,
        portable_membership_snapshot_from_eligible(scenario.membership_snapshot),
        tuple(reversed(retry_verifications)),
        commit_policy=scenario.policy,
        portable_certificate=portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        trusted_witness_attestations=retry_trust,
        certificate_id=f"distributed-certificate:{scenario.namespace}:same-value-retry",
        issuer_id="governance:distributed-same-value-peer",
        authority=AuthorityLevel.GOVERNANCE,
        issued_at_step=stable.window.last_evaluated_step,
        provenance=f"urn:test:{scenario.namespace}:same-value-retry",
        trace_event_id=f"trace:{scenario.namespace}:same-value-retry",
    )
    coexist = register_distributed_commit_certificate(
        retry_state,
        retry_certificate,
        commit_policy=scenario.policy,
        portable_certificate=portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        trusted_witness_attestations=retry_trust,
        current_step=stable.window.last_evaluated_step,
    )

    assert first.proposal_digest != retry_certificate.proposal_digest
    assert first.commit_value_root == retry_certificate.commit_value_root
    assert not coexist.frozen
    assert len(coexist.final_registrations) == 2
    assert not coexist.conflict_findings

    result = evaluate_hybrid_commit_step(
        request=_distributed_request(
            bundle,
            distributed_state=coexist,
            suffix="same-value-retry",
        )
    )
    witness_events = tuple(
        item for item in result.trace_events if item.event_type == "quorum_witness"
    )
    assert result.status is HybridCommitEvaluationStatus.PROGRESS
    assert result.authoritative and not result.terminal
    assert {
        item.lineage["proposal_digest"] for item in witness_events
    } == {first.proposal_digest, retry_certificate.proposal_digest}
    assert {
        item.lineage["commit_value_root"] for item in witness_events
    } == {first.commit_value_root}
    assert not any(
        item.event_type == "certificate_conflict" for item in result.trace_events
    )
    assert hybrid_commit_evaluation_is_authoritative(result)
    replay_commit_trace(result.trace_events, require_complete=False)


def test_distributed_conflict_freezes_commit_and_closes_both_certificate_lineages() -> None:
    bundle = _distributed_fixture(witness_count=3, variant="conflict-first")
    portable = bundle.portable
    stable = portable.stable
    scenario = stable.scenario
    quorum = scenario.policy.distributed.witness_quorum
    first = issue_reference_distributed_certificate(
        bundle,
        witness_count=quorum,
        variant="conflict-first",
    )
    first_state = register_distributed_commit_certificate(
        bundle.state,
        first,
        commit_policy=scenario.policy,
        portable_certificate=portable.certificate,
        trusted_issuer_attestations=portable.trusted_issuer_attestations,
        trusted_witness_attestations=bundle.trusted_witness_attestations,
        current_step=stable.window.last_evaluated_step,
    )
    first_result = evaluate_hybrid_commit_step(
        request=_distributed_request(
            bundle,
            distributed_state=first_state,
            suffix="conflict-first",
        )
    )
    assert first_result.status is HybridCommitEvaluationStatus.PROGRESS
    prior = first_result.trace_events

    (
        second_proposal,
        second_portable,
        second_issuer_trust,
        second_trust,
        second,
    ) = issue_reference_semantic_conflict_certificate(
        bundle,
        field_name="output_payload_fingerprint",
        field_value=_root(f"semantic-conflict:{scenario.run_id}"),
        variant="conflict-second",
    )
    second_verifications = second.witnesses
    assert second_proposal.commit_value_root != first.commit_value_root
    frozen = register_distributed_commit_certificate(
        first_state,
        second,
        commit_policy=scenario.policy,
        portable_certificate=second_portable,
        trusted_issuer_attestations=second_issuer_trust,
        trusted_witness_attestations=second_trust,
        current_step=stable.window.last_evaluated_step,
    )
    window_event = next(
        item for item in prior if item.event_type == "commit_window_advanced"
    )
    portable_event = next(
        item
        for item in prior
        if item.event_type == "commit_certificate_issued"
        and item.lineage["certificate_kind"] == "evidence_commit"
    )
    second_witness_events = tuple(
        _distributed_witness_event(
            scenario,
            verification,
            portable_event=portable_event,
        )
        for verification in second_verifications
    )
    second_event = _distributed_certificate_event(
        scenario,
        second,
        window_event=window_event,
        witness_events=second_witness_events,
    )
    first_witness_events = tuple(
        item for item in prior if item.event_type == "quorum_witness"
    )
    first_event = _distributed_certificate_event(
        scenario,
        first,
        window_event=window_event,
        witness_events=first_witness_events,
    )
    conflict_prior = tuple(
        (*prior, first_event, *second_witness_events, second_event)
    )
    replay_commit_trace(conflict_prior, require_complete=False)

    result = evaluate_hybrid_commit_step(
        request=replace(
            _distributed_request(
                bundle,
                distributed_state=frozen,
                prior_trace_events=conflict_prior,
                suffix="conflict-frozen",
                current_step=stable.window.last_evaluated_step + 1,
            ),
            previous_progress=first_result.decision_progress,
        )
    )

    first_ref = distributed_commit_certificate_fingerprint(first)
    second_ref = distributed_commit_certificate_fingerprint(second)
    assert result.status is HybridCommitEvaluationStatus.OUTCOME
    assert result.authoritative and result.terminal
    assert result.decision_outcome.kind.value == "safety_violation"
    assert not result.decision_outcome.authoritative_commit
    assert result.distributed_state_ref == distributed_commit_state_fingerprint(frozen)
    assert not result.distributed_certificate_ref
    assert result.deliver_authorization.authorized
    assert not result.publish_authorization.authorized
    assert not result.execute_authorization.authorized
    conflict = next(
        item for item in result.trace_events if item.event_type == "certificate_conflict"
    )
    assert {conflict.lineage["left_certificate_ref"], conflict.lineage["right_certificate_ref"]} == {
        first_ref,
        second_ref,
    }
    certificate_event_ids = {
        item.lineage["certificate_ref"]: item.lineage["event_id"]
        for item in result.trace_events
        if item.event_type == "commit_certificate_issued"
    }
    assert {
        certificate_event_ids[first_ref],
        certificate_event_ids[second_ref],
    }.issubset(conflict.lineage["previous_event_ids"])
    assert hybrid_commit_evaluation_is_authoritative(result)
    replay_commit_trace(result.trace_events, require_complete=True)


@pytest.mark.parametrize(
    ("assurance", "profile"),
    (
        (CommitAssurance.CERTIFIED, CERTIFIED_COMMIT_PROFILE_VERSION),
        (CommitAssurance.DISTRIBUTED, DISTRIBUTED_COMMIT_PROFILE_VERSION),
    ),
)
def test_missing_high_assurance_proof_waits_without_downgrade(
    assurance: CommitAssurance,
    profile: str,
) -> None:
    policy = _higher_assurance_policy(assurance)
    scenario = _scenario(commit_policy=policy, profile=profile)
    request = _total_request(stable=True, scenario=scenario)
    result = evaluate_hybrid_commit_step(request=request)

    assert result.status is HybridCommitEvaluationStatus.PROGRESS
    assert result.authoritative and not result.terminal
    assert result.assurance is assurance
    assert result.profile == profile
    assert not result.assurance_downgraded
    assert result.local_receipt_ref
    assert not result.evidence_certificate_ref
    assert "evidence_commit_certificate" in (
        result.decision_progress.next_required_inputs
    )
    assert hybrid_commit_evaluation_is_authoritative(result)
    replay_commit_trace(result.trace_events, require_complete=False)


@pytest.mark.parametrize(
    ("assurance", "expected_profile"),
    (
        (CommitAssurance.CERTIFIED, CERTIFIED_COMMIT_PROFILE_VERSION),
        (CommitAssurance.DISTRIBUTED, DISTRIBUTED_COMMIT_PROFILE_VERSION),
    ),
)
def test_non_authoritative_diagnostic_preserves_declared_assurance(
    assurance: CommitAssurance,
    expected_profile: str,
) -> None:
    request = replace(
        _total_request(stable=False),
        commit_policy=_higher_assurance_policy(assurance),
        context=object(),
    )
    result = evaluate_hybrid_commit_step(request=request)

    assert result.status is HybridCommitEvaluationStatus.INVALID
    assert result.terminal and not result.authoritative
    assert result.assurance is assurance
    assert result.profile == expected_profile
    assert not result.assurance_downgraded


@pytest.mark.parametrize("tamper", ("assessment_identity", "policy_assurance"))
def test_tampered_diagnostic_identity_never_escapes(tamper: str) -> None:
    request = _total_request(stable=False)
    if tamper == "assessment_identity":
        object.__setattr__(request.commit_assessment, "protocol_id", "")
        object.__setattr__(request.commit_assessment, "epoch", object())
    else:
        object.__setattr__(request.commit_policy, "assurance", object())

    result = evaluate_hybrid_commit_step(request=request)

    assert result.status is HybridCommitEvaluationStatus.INVALID
    assert result.terminal and not result.authoritative
    assert not result.assurance_downgraded
    assert result.evaluation_root


@pytest.mark.parametrize("stable", (False, True))
def test_total_evaluation_payload_round_trips_strict_commit_wire_and_roots(
    stable: bool,
) -> None:
    result = evaluate_hybrid_commit_step(request=_total_request(stable=stable))
    payload = hybrid_commit_evaluation_payload(result)
    record = json.loads(
        canonical_commit_payload(
            payload,
            schema="pheroos-hybrid-commit-evaluation-v1",
            profile=result.profile,
        )
    )

    assert result.authoritative
    assert result.assurance_downgraded is False
    assert result.trace_event_ids == tuple(
        event.lineage["event_id"] for event in result.trace_events
    )
    assert result.trace_root == commit_payload_fingerprint(
        {"event_ids": result.trace_event_ids},
        schema="pheroos-hybrid-commit-evaluation-trace-root-v1",
        profile=result.profile,
    )
    assert result.evaluation_root == commit_payload_fingerprint(
        {key: value for key, value in payload.items() if key != "evaluation_root"},
        schema="pheroos-hybrid-commit-evaluation-v1",
        profile=result.profile,
    )
    if stable:
        assert result.status is HybridCommitEvaluationStatus.OUTCOME
        assert result.terminal and not result.progress_ref and result.outcome_ref
        assert result.local_receipt_ref
        assert not result.evidence_certificate_ref
        assert not result.distributed_certificate_ref
        assert not result.outcome_certificate_ref
        assert result.finality_verification_ref
        assert result.deliver_authorization_ref
        assert result.publish_authorization_ref
        assert result.execute_authorization_ref
    else:
        assert result.status is HybridCommitEvaluationStatus.PROGRESS
        assert not result.terminal and result.progress_ref and not result.outcome_ref
        assert not result.local_receipt_ref
        assert not result.finality_verification_ref
        assert not result.deliver_authorization_ref
        assert not result.publish_authorization_ref
        assert not result.execute_authorization_ref
    assert validate_commit_wire_record(record) == []

    for leaf in tuple(record["payload"]):
        missing = deepcopy(record)
        del missing["payload"][leaf]
        assert validate_commit_wire_record(missing), leaf
    unknown = deepcopy(record)
    unknown["payload"]["legacy_blended_score_commit"] = True
    assert validate_commit_wire_record(unknown)

    trace_mutation = deepcopy(record)
    trace_mutation["payload"]["trace_root"] = _root("mutated-trace-root")
    trace_mutation["payload"]["evaluation_root"] = commit_payload_fingerprint(
        {
            key: value
            for key, value in trace_mutation["payload"].items()
            if key != "evaluation_root"
        },
        schema="pheroos-hybrid-commit-evaluation-v1",
        profile=result.profile,
    )
    assert validate_commit_wire_record(trace_mutation)

    evaluation_mutation = deepcopy(record)
    evaluation_mutation["payload"]["evaluation_root"] = _root(
        "mutated-evaluation-root"
    )
    assert validate_commit_wire_record(evaluation_mutation)
