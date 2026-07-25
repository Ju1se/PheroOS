"""Private Commit TCK reference authority handlers."""

from __future__ import annotations

from collections.abc import Mapping

from typing import Any

from pheroos.conformance._commit_reference import (
    ReferenceScenario,
)

from pheroos.governance.attention import evaluate_hybrid_attention_step

from pheroos.governance.candidate import Candidate, CandidateSet

from pheroos.governance.evidence_binding import (
    evidence_binding_fingerprint,
    evidence_binding_payload,
)

from pheroos.governance.observation import (
    verified_observation_payload,
    verified_observation_fingerprint,
)

from pheroos.governance.permission import (
    action_permission_payload,
)

from pheroos.governance.pheromone import (
    PheromoneNeighborhood,
    PheromoneSubject,
)

from pheroos.governance.principal import (
    principal_verification_payload,
)

from pheroos.governance.risk import (
    commit_threshold_snapshot_fingerprint,
    risk_assessment_payload,
)

from pheroos.governance.stop_signal import (
    stop_resolution_verification_payload,
)

from pheroos.governance.support_lease import (
    eligible_principal_snapshot_payload,
    support_lease_fingerprint,
    support_lease_payload,
)

from pheroos.trace import (
    TraceEvent,
    make_commit_trace_event,
    replay_commit_trace,
)

from pheroos.conformance._commit_tck_reference.liveness import (
    _verified_scout,
)


def _authority_trace_events(
    scenario: ReferenceScenario,
) -> tuple[TraceEvent, ...]:
    """Materialize complete pre-decision authority lineage through Trace ABI."""

    events: list[TraceEvent] = []

    def append(
        event_type: str,
        *,
        step: int,
        schema: str,
        payload: Mapping[str, Any],
        details: Mapping[str, Any],
    ) -> TraceEvent:
        event = make_commit_trace_event(
            event_type=event_type,
            protocol_id=scenario.protocol_id,
            target=scenario.target,
            reason=f"tck_{event_type}",
            profile=scenario.profile,
            assurance=scenario.assurance.value,
            manifest_root=scenario.manifest_root,
            commit_policy_root=scenario.commit_policy_root,
            run_id=scenario.run_id,
            epoch=scenario.epoch,
            step=step,
            record_schema=schema,
            record_payload=payload,
            previous_event_ids=tuple(event.lineage["event_id"] for event in events),
            details=details,
        )
        events.append(event)
        return event

    for principal in scenario.principals:
        append(
            "principal_attested",
            step=0,
            schema="pheroos-tck-principal-attestation-trace-v1",
            payload={
                "principal_id": principal.principal_id,
                "nonce": f"nonce:trace:{principal.principal_id}",
            },
            details={
                "principal_id": principal.principal_id,
                "attestation_fingerprint": "",
                "nonce": f"nonce:trace:{principal.principal_id}",
            },
        )
    for principal in scenario.principals:
        append(
            "principal_verified",
            step=0,
            schema="pheroos-principal-verification-v1",
            payload=principal_verification_payload(principal),
            details={
                "principal_id": principal.principal_id,
                "cluster_id": principal.cluster_id,
                "attestation_ref": principal.attestation_fingerprint,
                "verification_ref": "",
            },
        )
    append(
        "risk_assessed",
        step=1,
        schema="pheroos-risk-assessment-v1",
        payload=risk_assessment_payload(scenario.risk_assessment),
        details={
            "risk_band": scenario.risk_assessment.risk_band.value,
            "risk_ref": "",
            "threshold_ref": commit_threshold_snapshot_fingerprint(scenario.threshold),
            "risk_chain_revision": (scenario.risk_assessment.risk_chain_revision),
        },
    )
    append(
        "membership_snapshot",
        step=1,
        schema="pheroos-eligible-principal-snapshot-v1",
        payload=eligible_principal_snapshot_payload(scenario.membership_snapshot),
        details={
            "snapshot_id": scenario.membership_snapshot.snapshot_id,
            "membership_root": scenario.membership_snapshot.membership_root,
            "snapshot_ref": "",
            "cluster_count": len(scenario.membership_snapshot.eligible_clusters),
            "expires_at_step": scenario.membership_snapshot.expires_at_step,
        },
    )
    observations = {
        verified_observation_fingerprint(item): item
        for records in scenario.observations.values()
        for item in records
    }
    for observation_ref, observation in sorted(observations.items()):
        append(
            "observation_recorded",
            step=2,
            schema="pheroos-tck-observation-attestation-trace-v1",
            payload={
                "candidate_id": observation.candidate_id,
                "observation_id": observation.observation_id,
                "polarity": observation.polarity.value,
                "principal_id": observation.principal_id,
                "nonce": observation.nonce,
            },
            details={
                "observation_id": observation.observation_id,
                "candidate_id": observation.candidate_id,
                "polarity": observation.polarity.value,
                "principal_id": observation.principal_id,
                "nonce": observation.nonce,
                "attestation_fingerprint": "",
            },
        )
        append(
            "observation_verified",
            step=2,
            schema="pheroos-verified-observation-v1",
            payload=verified_observation_payload(observation),
            details={
                "observation_id": observation.observation_id,
                "candidate_id": observation.candidate_id,
                "polarity": observation.polarity.value,
                "principal_cluster_id": observation.principal_cluster_id,
                "observation_ref": "",
                "principal_verification_ref": (
                    observation.principal_verification_fingerprint
                ),
            },
        )
        if observation_ref != events[-1].lineage["record_ref"]:
            raise ValueError("verified observation trace root drift")
    for candidate_id, binding in sorted(scenario.bindings.items()):
        append(
            "evidence_bound",
            step=3,
            schema="pheroos-evidence-binding-authority-v1",
            payload=evidence_binding_payload(binding),
            details={
                "candidate_id": candidate_id,
                "claim_fingerprint": binding.claim_fingerprint,
                "binding_ref": "",
                "positive_root": binding.positive_root,
                "counter_root": binding.counter_root,
                "disposition_root": binding.disposition_root,
                "challenge_root": binding.challenge_root,
                "evidence_root": binding.evidence_root,
            },
        )
        if evidence_binding_fingerprint(binding) != events[-1].lineage["record_ref"]:
            raise ValueError("evidence binding trace root drift")
    for lease in scenario.leases:
        append(
            "support_lease_issued",
            step=4,
            schema="pheroos-support-lease-v1",
            payload=support_lease_payload(lease),
            details={
                "lease_id": lease.lease_id,
                "candidate_id": lease.candidate_id,
                "principal_cluster_id": lease.principal_cluster_id,
                "lease_ref": "",
                "evidence_refs": list(lease.positive_observation_fingerprints),
                "expires_at_step": lease.expires_at_step,
            },
        )
        if support_lease_fingerprint(lease) != events[-1].lineage["record_ref"]:
            raise ValueError("support lease trace root drift")
    append(
        "stop_resolution_verified",
        step=4,
        schema="pheroos-stop-resolution-verification-v1",
        payload=stop_resolution_verification_payload(scenario.stop_resolution),
        details={
            "action": scenario.stop_resolution.action.value,
            "resolution_ref": "",
            "blocked": scenario.stop_resolution.blocked,
            "expires_at_step": scenario.stop_resolution.expires_at_step,
        },
    )
    append(
        "action_permission_issued",
        step=4,
        schema="pheroos-action-permission-v1",
        payload=action_permission_payload(scenario.permission),
        details={
            "action": scenario.permission.action.value,
            "permission_ref": "",
            "allowed": scenario.permission.allowed,
            "expires_at_step": scenario.permission.expires_at_step,
        },
    )
    replay_commit_trace(events, require_complete=False)
    return tuple(events)


def _hybrid_attention_for_scenario(
    scenario: ReferenceScenario,
    *,
    current_step: int,
    candidate_id: str,
) -> tuple[Any, Any]:
    policy = scenario.manifest.protocol.collective_decision_policy
    if policy is None:
        raise ValueError("Hybrid Commit TCK requires an attention policy")
    candidates = CandidateSet(
        tuple(
            Candidate(item.id, item.target, item.safe_fallback)
            for item in scenario.manifest.protocol.candidates
        )
    )
    scouts = [
        _verified_scout(
            scenario,
            source_id=f"scout:total:{candidate_id}:{index}",
            candidate_id=candidate_id,
        )
        for index in range(1, 3)
    ]
    return evaluate_hybrid_attention_step(
        protocol_id=scenario.protocol_id,
        candidate_set=candidates,
        policy=policy,
        target=scenario.target,
        current_step=current_step,
        scout_reports=scouts,
        topology=_candidate_topology(scenario),
        fallback_candidate_id=scenario.fallback_id,
    )


def _candidate_topology(
    scenario: ReferenceScenario,
) -> PheromoneNeighborhood:
    return PheromoneNeighborhood(
        subjects=[
            PheromoneSubject(
                "candidate",
                item.id,
                item.id,
                scenario.target,
            )
            for item in scenario.manifest.protocol.candidates
            if item.target == scenario.target
        ],
        edges=[],
    )
