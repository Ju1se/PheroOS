from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping
from hashlib import sha256
import json
from pathlib import Path
from typing import cast

from pheroos.governance import (
    AuthorityLevel,
    InhibitionSignal,
    LayerPerformanceSnapshot,
    LayerProposal,
    PheromoneEdge,
    PheromoneFeedback,
    PheromoneNeighborhood,
    PheromoneSubject,
    PheromoneTrail,
    PolicyAdjustmentProposal,
    RecruitmentSignal,
    ScoutReport,
    StrategyBias,
    verify_signal_input,
)
from pheroos.governance._authority_v2 import InMemoryGovernanceStateStoreV2
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
)
from pheroos.governance.authority_store_v2 import (
    AuthorityDomainV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
)
from pheroos.governance.hybrid_replay_v2 import (
    HybridReplayAdvanceRequestV2,
    VerifiedHybridSourceStepV2,
    advance_hybrid_replay_state_v2,
    build_hybrid_replay_advance_request_v2,
    evaluate_hybrid_collective_step_v2,
    open_hybrid_replay_authority_session_v2,
    rehydrate_hybrid_replay_state_v2,
)
from pheroos.protocol import (
    CAPABILITY_SCHEMA_V3,
    ScopedCapabilityManifestV2,
    ScopedProtocolManifestV2,
    read_capability_manifest,
)


# This is intentionally the provider-free reference StateStore used by tests.
# It is not a production database, persistence recommendation, or runtime API.
REFERENCE_STORE_IMPLEMENTATION = "InMemoryGovernanceStateStoreV2:test-reference-only"
RESULT_SCHEMA = "pheroos-hybrid-replay-example-result-v1"
CHECKPOINT_SCHEMA = "pheroos-hybrid-replay-reference-checkpoint-v1"
PREPARE_RESULT_SCHEMA = "pheroos-hybrid-replay-prepare-result-v1"
RUN_REF = "run:hybrid-replay-example"
SCOPE_REF = "scope:hybrid-replay-example"
TARGET_REF = "decision:collective"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


def _payload_root(payload: bytes) -> str:
    return "sha256:" + sha256(payload).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _load_manifest() -> ScopedProtocolManifestV2:
    payload = json.loads(
        Path(__file__).with_name("capability.json").read_text(encoding="utf-8")
    )
    capability = read_capability_manifest(
        payload,
        schema_version=CAPABILITY_SCHEMA_V3,
    )
    _require(
        type(capability) is ScopedCapabilityManifestV2,
        "capability-v3 did not produce the exact scoped capability type",
    )
    manifest = capability.protocol
    _require(
        type(manifest) is ScopedProtocolManifestV2,
        "capability-v3 did not produce the exact scoped protocol type",
    )
    return cast(ScopedProtocolManifestV2, manifest)


def _domain(manifest: ScopedProtocolManifestV2) -> AuthorityDomainV2:
    policy = manifest.authority_policy
    return AuthorityDomainV2(
        policy_version=policy.policy_version,
        profile=policy.profile,
        wire_version=policy.wire_version,
        canonical_version=policy.canonical_version,
        ledger_version=policy.ledger_version,
        state_store_version=policy.state_store_version,
        trace_batch_version=policy.trace_batch_version,
        read_set_version=policy.read_set_version,
        scope_ref=SCOPE_REF,
    )


def _grant(
    domain: AuthorityDomainV2,
    manifest: ScopedProtocolManifestV2,
) -> GovernanceIssuerGrantV2:
    return GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:hybrid-replay-example",
        grant_ref="grant:hybrid-replay-example",
        grant_binding_ref=_root("hybrid-replay-example-grant-binding"),
        operations=(GovernanceIssuerOperationV2.ADVANCE_REPLAY,),
        target_refs=(manifest.quorum_policy.target,),
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100,
        revocation_generation=0,
    )


def _new_store(
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
) -> InMemoryGovernanceStateStoreV2:
    store = InMemoryGovernanceStateStoreV2((domain,))
    activation = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:hybrid-replay-example:grant-activation",
        1,
    )
    _require(
        activation.disposition is GovernanceCommitDispositionV2.COMMITTED,
        "Hybrid Replay grant activation failed",
    )
    return store


def _capability(
    store: InMemoryGovernanceStateStoreV2,
    domain: AuthorityDomainV2,
    grant: GovernanceIssuerGrantV2,
):
    return bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        RUN_REF,
        3,
    )


def _verification(
    source_ref: str,
    candidate_ref: str,
    trace_ref: str,
):
    return verify_signal_input(
        target=TARGET_REF,
        source_id=source_ref,
        subject_id=candidate_ref,
        verifier_id="governance:hybrid-replay-example",
        authority=AuthorityLevel.GOVERNANCE,
        provenance="governance:hybrid-replay-example",
        trace_event_id=f"{trace_ref}:verified",
    )


def _scouts(step: int) -> list[ScoutReport]:
    result: list[ScoutReport] = []
    for suffix in ("a", "b"):
        source_ref = f"scout:{step}:{suffix}"
        trace_ref = f"trace:scout:{step}:{suffix}"
        result.append(
            ScoutReport(
                scout_id=source_ref,
                candidate_id="candidate:alpha",
                evidence_id=f"evidence:scout:{step}:{suffix}",
                provenance=f"driver:scout:{step}:{suffix}",
                target=TARGET_REF,
                trace_event_id=trace_ref,
                verification=_verification(
                    source_ref,
                    "candidate:alpha",
                    trace_ref,
                ),
            )
        )
    return result


def _recruitment(step: int) -> list[RecruitmentSignal]:
    source_ref = f"recruit:{step}:alpha"
    trace_ref = f"trace:recruit:{step}:alpha"
    return [
        RecruitmentSignal(
            source_id=source_ref,
            candidate_id="candidate:alpha",
            strength=1.0,
            target=TARGET_REF,
            provenance=f"governance:recruit:{step}",
            trace_event_id=trace_ref,
            verification=_verification(source_ref, "candidate:alpha", trace_ref),
        )
    ]


def _inhibition(step: int) -> list[InhibitionSignal]:
    source_ref = f"inhibit:{step}:beta"
    trace_ref = f"trace:inhibit:{step}:beta"
    return [
        InhibitionSignal(
            source_id=source_ref,
            candidate_id="candidate:beta",
            strength=0.5,
            target=TARGET_REF,
            provenance=f"governance:inhibit:{step}",
            trace_event_id=trace_ref,
            verification=_verification(source_ref, "candidate:beta", trace_ref),
        )
    ]


def _topology() -> PheromoneNeighborhood:
    return PheromoneNeighborhood(
        subjects=[
            PheromoneSubject(
                "candidate", "candidate:alpha", "candidate:alpha", TARGET_REF
            ),
            PheromoneSubject(
                "candidate", "candidate:beta", "candidate:beta", TARGET_REF
            ),
            PheromoneSubject("route", "route:alpha", "candidate:alpha", TARGET_REF),
            PheromoneSubject("route", "route:beta", "candidate:beta", TARGET_REF),
        ],
        edges=[
            PheromoneEdge("route", "route:alpha", "candidate", "candidate:alpha", 1.0),
            PheromoneEdge("route", "route:beta", "candidate", "candidate:beta", 1.0),
        ],
    )


def _trail(
    *,
    step: int,
    candidate_ref: str,
    route_ref: str,
    kind: str,
    strength: float,
) -> PheromoneTrail:
    suffix = route_ref.removeprefix("route:")
    return PheromoneTrail(
        candidate_id=candidate_ref,
        strength=strength,
        subject_type="route",
        subject_id=route_ref,
        target=TARGET_REF,
        kind=kind,
        source_id=f"source:{suffix}:{step}",
        evidence_id=f"evidence:{route_ref}:{step}",
        provenance=f"driver:{route_ref}:{step}",
        trace_event_id=f"trace:deposit:{suffix}:{step}",
        deposited_at_step=step,
        updated_at_step=step,
    )


def _deposits(step: int) -> list[PheromoneTrail]:
    return [
        _trail(
            step=step,
            candidate_ref="candidate:alpha",
            route_ref="route:alpha",
            kind="positive",
            strength=1.0,
        ),
        _trail(
            step=step,
            candidate_ref="candidate:beta",
            route_ref="route:beta",
            kind="cautionary",
            strength=0.5,
        ),
    ]


def _feedback(step: int) -> list[PheromoneFeedback]:
    return [
        PheromoneFeedback(
            source_id=f"source:alpha:{step}",
            subject_type="route",
            subject_id="route:alpha",
            candidate_id="candidate:alpha",
            target=TARGET_REF,
            outcome="success",
            reward=1.0,
            strength_delta=1.0,
            evidence_id=f"evidence:route:alpha:{step}",
            provenance=f"driver:route:alpha:{step}",
            trace_event_id=f"trace:feedback:alpha:{step}",
            step=step,
        ),
        PheromoneFeedback(
            source_id=f"source:beta:{step}",
            subject_type="route",
            subject_id="route:beta",
            candidate_id="candidate:beta",
            target=TARGET_REF,
            outcome="congested",
            reward=-0.5,
            strength_delta=0.5,
            evidence_id=f"evidence:route:beta:{step}",
            provenance=f"driver:route:beta:{step}",
            trace_event_id=f"trace:feedback:beta:{step}",
            step=step,
        ),
    ]


def _layer_proposals(step: int) -> list[LayerProposal]:
    return [
        LayerProposal(
            layer_id="learned",
            source_id=f"layer:learned:{step}",
            target=TARGET_REF,
            candidate_id="candidate:alpha",
            action="support",
            confidence=0.9,
            support=1.5,
            evidence_id=f"evidence:layer:learned:{step}",
            provenance=f"runtime:learned:{step}",
            trace_event_id=f"trace:layer:learned:{step}",
        ),
        LayerProposal(
            layer_id="metacognitive",
            source_id=f"layer:metacognitive:{step}",
            target=TARGET_REF,
            candidate_id="candidate:alpha",
            action="confirm_trace_coverage",
            confidence=0.8,
            support=0.2,
            evidence_id=f"evidence:layer:metacognitive:{step}",
            provenance=f"runtime:metacognitive:{step}",
            trace_event_id=f"trace:layer:metacognitive:{step}",
        ),
    ]


def _performance() -> list[LayerPerformanceSnapshot]:
    return [
        LayerPerformanceSnapshot(
            layer_id="learned",
            recent_success_rate=0.8,
            recent_conflict_rate=0.1,
            recent_fallback_rate=0.1,
            mean_confidence=0.8,
            evidence_coverage=1.0,
            trace_coverage=1.0,
        )
    ]


def _strategy_biases(step: int) -> list[StrategyBias]:
    return [
        StrategyBias(
            layer_id="evolutionary",
            candidate_id="candidate:alpha",
            support=0.4,
            provenance=f"runtime:evolutionary:{step}",
            trace_event_id=f"trace:bias:evolutionary:{step}",
            target=TARGET_REF,
            source_id=f"layer:evolutionary:bias:{step}",
            confidence=0.8,
            evidence_id=f"evidence:evolutionary:bias:{step}",
        )
    ]


def _adjustments(step: int) -> list[PolicyAdjustmentProposal]:
    field, value = (
        ("pheromone_positive_weight", 1.2)
        if step == 1
        else ("pheromone_exploration_floor", 0.25)
    )
    return [
        PolicyAdjustmentProposal(
            layer_id="evolutionary",
            source_id=f"layer:evolutionary:adjustment:{step}",
            adjustments={field: value},
            provenance=f"runtime:evolutionary:adjustment:{step}",
            trace_event_id=f"trace:adjustment:evolutionary:{step}",
        )
    ]


def _evaluate(
    manifest: ScopedProtocolManifestV2,
    domain: AuthorityDomainV2,
    *,
    step: int,
    verified_replay_state=None,
) -> VerifiedHybridSourceStepV2:
    return evaluate_hybrid_collective_step_v2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        run_ref=RUN_REF,
        observed_epoch=3,
        manifest=manifest,
        current_step=step,
        scout_reports=_scouts(step),
        topology=_topology(),
        verified_replay_state=verified_replay_state,
        recruitment_signals=_recruitment(step),
        inhibition_signals=_inhibition(step),
        deposits=_deposits(step),
        feedback=_feedback(step),
        layer_proposals=_layer_proposals(step),
        performance_snapshots=_performance(),
        strategy_biases=_strategy_biases(step),
        adjustment_proposals=_adjustments(step),
    )


def _request(
    domain: AuthorityDomainV2,
    *,
    step: int,
    source: VerifiedHybridSourceStepV2,
) -> HybridReplayAdvanceRequestV2:
    return build_hybrid_replay_advance_request_v2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        run_ref=RUN_REF,
        observed_epoch=3,
        advance_ref=f"advance:hybrid-replay-example:{step}",
        source=source,
    )


def _commit(capability, request, source):
    session = open_hybrid_replay_authority_session_v2(capability, request)
    attempt = advance_hybrid_replay_state_v2(
        request,
        source=source,
        authority_session=session,
    )
    _require(
        attempt.disposition is GovernanceCommitDispositionV2.COMMITTED
        and attempt.position_observation is not None
        and attempt.position_observation.position is GovernanceCommitPositionV2.CURRENT
        and attempt.committed_transition is not None,
        "Hybrid Replay state did not commit currently",
    )
    return attempt


def _source_observation(source: VerifiedHybridSourceStepV2) -> dict[str, object]:
    step = source.source_step
    return {
        "context_root": source.context_root,
        "decision": {
            "candidate_ref": step.decision.candidate_id,
            "reason": step.decision.reason,
        },
        "event_types": [event.event_type for event in step.trace_events],
    }


def _step_summary(
    store: InMemoryGovernanceStateStoreV2,
    request: HybridReplayAdvanceRequestV2,
    source_observation: Mapping[str, object],
) -> dict[str, object]:
    view = store.load_commit_view_v2(
        request.scope_ref,
        request.stream_ref,
        request.transition_id,
    )
    _require(
        view.disposition is GovernanceCommitDispositionV2.COMMITTED
        and view.position_observation is not None
        and view.committed_transition is not None,
        "Hybrid Replay committed view is unavailable",
    )
    assert view.position_observation is not None
    assert view.committed_transition is not None
    event = view.committed_transition.batch.trace_batch.events[0]
    event.validate()
    snapshot = request.snapshot
    receipt_counts = Counter(
        cast(str, item["kind"]) for item in snapshot.replay_receipts
    )
    overlay = snapshot.to_dict()["overlay"]
    assert isinstance(overlay, dict)
    values = cast(list[dict[str, object]], overlay["values"])
    return {
        "revision": snapshot.revision,
        "current_step": snapshot.current_step,
        "request_root": request.request_root,
        "snapshot_root": snapshot.snapshot_root,
        "source_step_root": snapshot.source_step_root,
        "source_trace_root": snapshot.source_trace_set_root,
        "state_root": snapshot.state_root,
        "trace_root": view.committed_transition.batch.trace_batch.trace_root,
        "receipt_root": view.committed_transition.receipt.receipt_root,
        "position": view.position_observation.position.value,
        "receipt_kinds": dict(sorted(receipt_counts.items())),
        "overlay_fields": sorted(cast(str, item["field_ref"]) for item in values),
        "authority_event": event.event_type,
        "source": dict(source_observation),
    }


def _checkpoint_payload(
    *,
    manifest: ScopedProtocolManifestV2,
    store: InMemoryGovernanceStateStoreV2,
    first_request: HybridReplayAdvanceRequestV2,
    first_observation: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema": CHECKPOINT_SCHEMA,
        "purpose": "deterministic-reference-test-data-not-authority",
        "reference_store_implementation": REFERENCE_STORE_IMPLEMENTATION,
        "manifest_root": manifest.manifest_root,
        "first_request": first_request.to_dict(),
        "first_source_observation": dict(first_observation),
        "reference_store_snapshot": json.loads(store.snapshot_v2()),
    }


def _restore_checkpoint(
    checkpoint: Path,
    *,
    manifest: ScopedProtocolManifestV2,
    domain: AuthorityDomainV2,
) -> tuple[
    InMemoryGovernanceStateStoreV2,
    HybridReplayAdvanceRequestV2,
    dict[str, object],
]:
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    expected_fields = {
        "schema",
        "purpose",
        "reference_store_implementation",
        "manifest_root",
        "first_request",
        "first_source_observation",
        "reference_store_snapshot",
    }
    _require(
        type(payload) is dict and set(payload) == expected_fields,
        "reference checkpoint fields are invalid",
    )
    _require(
        payload["schema"] == CHECKPOINT_SCHEMA
        and payload["purpose"] == "deterministic-reference-test-data-not-authority"
        and payload["reference_store_implementation"] == REFERENCE_STORE_IMPLEMENTATION
        and payload["manifest_root"] == manifest.manifest_root,
        "reference checkpoint binding is invalid",
    )
    store = InMemoryGovernanceStateStoreV2.from_snapshot_v2(
        _canonical_bytes(payload["reference_store_snapshot"])
    )
    request = HybridReplayAdvanceRequestV2.from_dict(payload["first_request"])
    _require(
        request.domain_root == domain.domain_root
        and request.scope_ref == domain.scope_ref
        and request.snapshot.manifest_root == manifest.manifest_root,
        "reference checkpoint request is outside the selected authority domain",
    )
    observation = payload["first_source_observation"]
    _require(type(observation) is dict, "checkpoint source observation is invalid")
    return store, request, cast(dict[str, object], observation)


def _final_summary(
    *,
    mode: str,
    restarted: bool,
    manifest: ScopedProtocolManifestV2,
    store: InMemoryGovernanceStateStoreV2,
    first_request: HybridReplayAdvanceRequestV2,
    first_observation: Mapping[str, object],
    second_request: HybridReplayAdvanceRequestV2,
    second_observation: Mapping[str, object],
) -> dict[str, object]:
    first = _step_summary(store, first_request, first_observation)
    second = _step_summary(store, second_request, second_observation)
    first_source = cast(dict[str, object], first["source"])
    second_source = cast(dict[str, object], second["source"])
    all_event_types = sorted(
        {
            *cast(list[str], first_source["event_types"]),
            *cast(list[str], second_source["event_types"]),
        }
    )
    return {
        "schema": RESULT_SCHEMA,
        "mode": mode,
        "capability": {
            "schema_version": CAPABILITY_SCHEMA_V3,
            "protocol_version": manifest.protocol_version,
            "protocol_id": manifest.id,
            "manifest_root": manifest.manifest_root,
        },
        "reference_store": {
            "implementation": REFERENCE_STORE_IMPLEMENTATION,
            "restart_between_steps": restarted,
            "production_persistence": False,
        },
        "steps": [first, second],
        "next_roots": {
            "request_root": second_request.request_root,
            "snapshot_root": second_request.snapshot.snapshot_root,
            "trace_root": second["trace_root"],
        },
        "feature_path": {
            "event_types": all_event_types,
            "receipt_kinds": sorted(cast(dict[str, int], second["receipt_kinds"])),
            "overlay_fields": second["overlay_fields"],
        },
    }


def run_example(*, restart_between_steps: bool = True) -> dict[str, object]:
    manifest = _load_manifest()
    domain = _domain(manifest)
    grant = _grant(domain, manifest)
    store = _new_store(domain, grant)
    capability = _capability(store, domain, grant)

    first_source = _evaluate(manifest, domain, step=1)
    first_request = _request(domain, step=1, source=first_source)
    _commit(capability, first_request, first_source)
    first_observation = _source_observation(first_source)

    if restart_between_steps:
        store = InMemoryGovernanceStateStoreV2.from_snapshot_v2(store.snapshot_v2())
        capability = _capability(store, domain, grant)
    first_state = rehydrate_hybrid_replay_state_v2(
        first_request.to_dict(),
        domain=domain,
        state_reader=store,
    )
    second_source = _evaluate(
        manifest,
        domain,
        step=2,
        verified_replay_state=first_state,
    )
    second_request = _request(domain, step=2, source=second_source)
    _commit(capability, second_request, second_source)
    return _final_summary(
        mode="restart" if restart_between_steps else "uninterrupted",
        restarted=restart_between_steps,
        manifest=manifest,
        store=store,
        first_request=first_request,
        first_observation=first_observation,
        second_request=second_request,
        second_observation=_source_observation(second_source),
    )


def prepare_checkpoint(checkpoint: Path) -> dict[str, object]:
    manifest = _load_manifest()
    domain = _domain(manifest)
    grant = _grant(domain, manifest)
    store = _new_store(domain, grant)
    capability = _capability(store, domain, grant)
    source = _evaluate(manifest, domain, step=1)
    request = _request(domain, step=1, source=source)
    _commit(capability, request, source)
    observation = _source_observation(source)
    payload = _checkpoint_payload(
        manifest=manifest,
        store=store,
        first_request=request,
        first_observation=observation,
    )
    checkpoint_bytes = _canonical_bytes(payload)
    checkpoint.write_bytes(checkpoint_bytes)
    return {
        "schema": PREPARE_RESULT_SCHEMA,
        "checkpoint_schema": CHECKPOINT_SCHEMA,
        "checkpoint_root": _payload_root(checkpoint_bytes),
        "manifest_root": manifest.manifest_root,
        "first": _step_summary(store, request, observation),
    }


def resume_checkpoint(checkpoint: Path) -> dict[str, object]:
    manifest = _load_manifest()
    domain = _domain(manifest)
    grant = _grant(domain, manifest)
    store, first_request, first_observation = _restore_checkpoint(
        checkpoint,
        manifest=manifest,
        domain=domain,
    )
    capability = _capability(store, domain, grant)
    first_state = rehydrate_hybrid_replay_state_v2(
        first_request.to_dict(),
        domain=domain,
        state_reader=store,
    )
    second_source = _evaluate(
        manifest,
        domain,
        step=2,
        verified_replay_state=first_state,
    )
    second_request = _request(domain, step=2, source=second_source)
    _commit(capability, second_request, second_source)
    return _final_summary(
        mode="resumed",
        restarted=True,
        manifest=manifest,
        store=store,
        first_request=first_request,
        first_observation=first_observation,
        second_request=second_request,
        second_observation=_source_observation(second_source),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        nargs="?",
        choices=("restart", "uninterrupted", "prepare", "resume"),
        default="restart",
    )
    parser.add_argument("--checkpoint", type=Path)
    args = parser.parse_args(argv)
    if args.mode in {"prepare", "resume"} and args.checkpoint is None:
        parser.error(f"{args.mode} requires --checkpoint")
    if args.mode == "prepare":
        result = prepare_checkpoint(args.checkpoint)
    elif args.mode == "resume":
        result = resume_checkpoint(args.checkpoint)
    else:
        result = run_example(restart_between_steps=args.mode == "restart")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
