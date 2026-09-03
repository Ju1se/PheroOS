"""Active provider-free Conformance matrix for durable Hybrid Replay v2.

The matrix composes only public Protocol, Governance, StateStore, and Trace
contracts.  It does not contain a second Hybrid evaluator.  Independent
expectations are limited to declared bindings, Store positions, exact read-set
membership, receipt coverage, restart continuity, and fail-closed outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json

from pheroos.conformance.checks._hybrid_replay_v2_public_support import (
    run_public_hybrid_replay_adversarial_matrix_v2,
)
from pheroos.conformance.checks.authority_store_v2_contract import (
    GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2,
    GovernanceStateStoreConformanceAdapterV2,
)
from pheroos.conformance.report import CheckResult
from pheroos.governance import (
    AuthorityLevel,
    PolicyAdjustmentProposal,
    ScoutReport,
    HybridReplayAdvanceRequestV2,
    VerifiedHybridReplayStateV2,
    VerifiedHybridSourceStepV2,
    advance_hybrid_replay_state_v2,
    build_hybrid_replay_advance_request_v2,
    evaluate_hybrid_collective_step_v2,
    hybrid_replay_state_is_current_v2,
    open_hybrid_replay_authority_session_v2,
    rehydrate_hybrid_replay_state_v2,
    verify_signal_input,
)
from pheroos.governance.pheromone import (
    PheromoneEdge,
    PheromoneNeighborhood,
    PheromoneSubject,
    PheromoneTrail,
)
from pheroos.governance.pheromone_feedback import PheromoneFeedback
from pheroos.governance.authority_session_v2 import (
    GovernanceIssuerCapabilityV2,
    GovernanceIssuerGrantV2,
    GovernanceIssuerOperationV2,
    activate_governance_issuer_grant_v2,
    bind_governance_issuer_capability_v2,
    governance_issuer_grant_stream_ref_v2,
)
from pheroos.governance.authority_store_v2 import (
    GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    AuthorityDomainV2,
    GovernanceCommitAttemptV2,
    GovernanceCommitDispositionV2,
    GovernanceCommitPositionV2,
    GovernanceStateStoreV2,
)
from pheroos.governance.layer_coordination import LayerProposal
from pheroos.protocol import (
    BASELINE_OUTPUT_POLICY_VERSION_V2,
    PROTOCOL_VERSION_V2,
    BaselineOutputActionPolicyV2,
    BaselineOutputPolicyV2,
    CandidateSpec,
    CollectiveDecisionPolicy,
    EvidencePolicy,
    QuorumPolicy,
    ScopedAuthorityPolicyV2,
    ScopedProtocolManifestV2,
    TargetSpec,
    TracePolicy,
    required_swarm_trace_events,
)
from pheroos.protocol.models import PheromoneKindProfile
from pheroos.protocol.authority_v2 import AuthorityDiagnosticCodeV2


GOVERNANCE_HYBRID_REPLAY_CONFORMANCE_VERSION_V2 = (
    "pheroos-governance-hybrid-replay-conformance-v2"
)

_CHECK_NAME = "hybrid_replay_v2_contract"
_RUN_REF = "run:hybrid-replay-v2"
_TARGET_REF = "target:collective"
_CANDIDATE_REF = "candidate:alpha"
_FALLBACK_REF = "candidate:safe"
_ACTION_REF = "action:publish"
_BASELINE_TRACE_EVENTS = frozenset(
    {
        "baseline_action_permission_issued",
        "baseline_decision_evaluated",
        "baseline_evidence_qualified",
        "baseline_manifest_activated",
        "baseline_output_committed",
        "baseline_stop_resolved",
    }
)


@dataclass(frozen=True, slots=True)
class _Context:
    domain: AuthorityDomainV2
    store: GovernanceStateStoreV2
    grant: GovernanceIssuerGrantV2
    capability: GovernanceIssuerCapabilityV2
    manifest: ScopedProtocolManifestV2
    topology: PheromoneNeighborhood


def run_governance_hybrid_replay_conformance_v2(
    adapter: GovernanceStateStoreConformanceAdapterV2,
) -> CheckResult:
    """Run every active durable Hybrid Replay v2 invariant without skips."""

    try:
        if not isinstance(adapter, GovernanceStateStoreConformanceAdapterV2):
            return CheckResult(_CHECK_NAME, False, "adapter_protocol")
        implementation_id = adapter.implementation_id
        conformance_version = adapter.conformance_version
    except Exception as exc:
        return CheckResult(
            _CHECK_NAME,
            False,
            f"adapter_exception:{type(exc).__name__}:{exc}",
        )
    if (
        type(implementation_id) is not str
        or not implementation_id
        or implementation_id != implementation_id.strip()
    ):
        return CheckResult(_CHECK_NAME, False, "adapter_implementation_id")
    if conformance_version != GOVERNANCE_STATE_STORE_CONFORMANCE_VERSION_V2:
        return CheckResult(_CHECK_NAME, False, "adapter_version")

    problems: list[str] = []
    try:
        _evaluate_vertical_restart_and_fork(adapter, problems)
        _evaluate_source_context_substitution(adapter, problems)
        problems.extend(
            run_public_hybrid_replay_adversarial_matrix_v2(
                adapter,
                context_factory=_context,
                source_factory=_source,
                request_factory=_request,
                advance_factory=_advance,
            )
        )
        _evaluate_deterministic_transcript(adapter, problems)
    except Exception as exc:  # total boundary for third-party adapters
        problems.append(f"adapter_exception:{type(exc).__name__}:{exc}")
    return CheckResult(_CHECK_NAME, not problems, ", ".join(problems))


def _evaluate_vertical_restart_and_fork(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = _context(adapter, "vertical")
    source = _source(context, current_step=1)
    request = _request(context, source, "advance:genesis", observed_epoch=3)
    attempt = _advance(context, request, source)
    if (
        attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or attempt.committed_transition is None
    ):
        problems.append("genesis_commit")
        return
    committed = attempt.committed_transition
    batch = committed.batch
    expected_streams = {
        request.stream_ref,
        governance_issuer_grant_stream_ref_v2(
            context.domain.scope_ref, context.grant.grant_ref
        ),
        GOVERNANCE_DOMAIN_LIFECYCLE_STREAM_REF_V2,
    }
    if {item.stream_ref for item in batch.read_set.entries} != expected_streams:
        problems.append("complete_authority_read_set")
    events = batch.trace_batch.events
    if (
        len(events) != 1
        or events[0].event_type != "hybrid_replay_advanced"
        or events[0].lineage.get("snapshot_root") != request.snapshot.snapshot_root
        or events[0].lineage.get("read_set_root") != batch.read_set.root()
    ):
        problems.append("atomic_trace_lineage")
    receipt_kinds = {item["kind"] for item in request.snapshot.replay_receipts}
    if receipt_kinds != {"adjustment", "deposit", "diffusion", "feedback"}:
        problems.append("complete_hybrid_receipts")

    portable = json.loads(request.canonical_bytes())
    verified = rehydrate_hybrid_replay_state_v2(
        portable,
        domain=context.domain,
        state_reader=context.store,
    )
    if (
        type(verified) is not VerifiedHybridReplayStateV2
        or verified.position is not GovernanceCommitPositionV2.CURRENT
        or not hybrid_replay_state_is_current_v2(verified)
        or verified.snapshot.snapshot_root != request.snapshot.snapshot_root
    ):
        problems.append("current_rehydration")

    restarted = adapter.restart_store_v2(context.store)
    restarted_parent = rehydrate_hybrid_replay_state_v2(
        portable,
        domain=context.domain,
        state_reader=restarted,
    )
    restarted_context = _rebind_context(context, restarted, observed_epoch=4)
    source_a = _source(
        restarted_context,
        current_step=2,
        observed_epoch=4,
        verified_state=restarted_parent,
        event_suffix="child-a",
    )
    source_b = _source(
        restarted_context,
        current_step=2,
        observed_epoch=4,
        verified_state=restarted_parent,
        event_suffix="child-b",
    )
    request_a = _request(
        restarted_context,
        source_a,
        "advance:child-a",
        observed_epoch=4,
    )
    request_b = _request(
        restarted_context,
        source_b,
        "advance:child-b",
        observed_epoch=4,
    )
    committed_a = _advance(restarted_context, request_a, source_a)
    stale_b = _advance(restarted_context, request_b, source_b)
    if (
        committed_a.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or committed_a.committed_transition is None
    ):
        problems.append("restart_child_commit")
    if (
        stale_b.disposition is not GovernanceCommitDispositionV2.RETRY_REQUIRED
        or stale_b.failure is None
        or stale_b.failure.code
        is not AuthorityDiagnosticCodeV2.GOVERNANCE_READ_SET_STALE
    ):
        problems.append("concurrent_fork_is_retry")
    if hybrid_replay_state_is_current_v2(restarted_parent):
        problems.append("successor_supersedes_parent")
    exact_retry = _advance(restarted_context, request_a, source_a)
    if (
        exact_retry.disposition is not GovernanceCommitDispositionV2.COMMITTED
        or exact_retry.committed_transition is None
        or committed_a.committed_transition is None
        or exact_retry.committed_transition.receipt.receipt_root
        != committed_a.committed_transition.receipt.receipt_root
    ):
        problems.append("exact_retry_reconciliation")


def _evaluate_source_context_substitution(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    context = _context(adapter, "source-binding")
    source = _source(context, current_step=1)
    request = _request(context, source, "advance:source-binding", observed_epoch=3)
    session = open_hybrid_replay_authority_session_v2(context.capability, request)

    raw_attempt = advance_hybrid_replay_state_v2(
        request,
        source=source.source_step,
        authority_session=session,
    )
    _expect_binding_rejection(raw_attempt, "raw_v1_source", problems)

    variants = (
        (
            "manifest",
            replace(context.manifest, targets=(TargetSpec(_TARGET_REF, "changed"),)),
            context.topology,
        ),
        ("candidate", _expanded_candidate_manifest(context.manifest), context.topology),
        ("base_policy", _adjusted_manifest(context.manifest), context.topology),
        ("topology", context.manifest, _expanded_topology()),
    )
    for label, manifest, topology in variants:
        substituted_context = replace(context, manifest=manifest, topology=topology)
        substituted = _source(substituted_context, current_step=1)
        attempt = advance_hybrid_replay_state_v2(
            request,
            source=substituted,
            authority_session=session,
        )
        _expect_binding_rejection(attempt, f"{label}_substitution", problems)

    if (
        context.store.load_head_v2(
            context.domain.scope_ref, request.stream_ref
        ).revision
        != 0
    ):
        problems.append("source_rejection_before_mutation")


def _evaluate_deterministic_transcript(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    problems: list[str],
) -> None:
    roots: list[tuple[str, str, str]] = []
    for _ in range(2):
        context = _context(adapter, "deterministic")
        source = _source(context, current_step=1)
        request = _request(context, source, "advance:deterministic", observed_epoch=3)
        attempt = _advance(context, request, source)
        if (
            attempt.disposition is not GovernanceCommitDispositionV2.COMMITTED
            or attempt.committed_transition is None
        ):
            problems.append("deterministic_commit")
            return
        roots.append(
            (
                request.request_root,
                attempt.committed_transition.batch.batch_root,
                attempt.committed_transition.batch.trace_root,
            )
        )
    if roots[0] != roots[1]:
        problems.append("deterministic_roots")


def _expect_binding_rejection(
    attempt: GovernanceCommitAttemptV2,
    label: str,
    problems: list[str],
) -> None:
    if (
        not hasattr(attempt, "disposition")
        or attempt.disposition is not GovernanceCommitDispositionV2.INVALID
        or attempt.failure is None
        or attempt.failure.code
        is not AuthorityDiagnosticCodeV2.AUTHORITY_BINDING_MISMATCH
        or attempt.committed_transition is not None
    ):
        problems.append(label)


def _context(
    adapter: GovernanceStateStoreConformanceAdapterV2,
    label: str,
) -> _Context:
    domain = adapter.create_domain_v2(f"scope:hybrid-replay-v2:{label}")
    store = adapter.create_store_v2((domain,))
    manifest = _manifest()
    grant = GovernanceIssuerGrantV2(
        domain_root=domain.domain_root,
        scope_ref=domain.scope_ref,
        issuer_ref="issuer:hybrid-replay-v2",
        grant_ref="grant:hybrid-replay-v2",
        grant_binding_ref=_root(f"grant-binding:{label}"),
        operations=(GovernanceIssuerOperationV2.ADVANCE_REPLAY,),
        target_refs=(_TARGET_REF,),
        action_refs=(),
        issued_epoch=1,
        not_before_epoch=1,
        expires_at_epoch=100,
        revocation_generation=0,
    )
    activation = activate_governance_issuer_grant_v2(
        store,
        domain,
        grant,
        "transition:grant-activation",
        1,
    )
    if activation.disposition is not GovernanceCommitDispositionV2.COMMITTED:
        raise ValueError("Hybrid Replay conformance grant activation failed")
    capability = bind_governance_issuer_capability_v2(
        store,
        domain,
        grant,
        _RUN_REF,
        3,
    )
    return _Context(domain, store, grant, capability, manifest, _topology())


def _rebind_context(
    context: _Context,
    store: GovernanceStateStoreV2,
    *,
    observed_epoch: int,
) -> _Context:
    capability = bind_governance_issuer_capability_v2(
        store,
        context.domain,
        context.grant,
        _RUN_REF,
        observed_epoch,
    )
    return replace(context, store=store, capability=capability)


def _source(
    context: _Context,
    *,
    current_step: int,
    observed_epoch: int = 3,
    verified_state: VerifiedHybridReplayStateV2 | None = None,
    event_suffix: str = "genesis",
) -> VerifiedHybridSourceStepV2:
    return evaluate_hybrid_collective_step_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref=_RUN_REF,
        observed_epoch=observed_epoch,
        manifest=context.manifest,
        current_step=current_step,
        scout_reports=[
            _scout(f"scout:{event_suffix}:a", current_step),
            _scout(f"scout:{event_suffix}:b", current_step),
        ],
        topology=context.topology,
        verified_replay_state=verified_state,
        deposits=(
            [_deposit(current_step, event_suffix)] if verified_state is None else []
        ),
        feedback=(
            [_feedback(current_step, event_suffix)] if verified_state is None else []
        ),
        layer_proposals=(
            [
                _learned_proposal(current_step, event_suffix),
                _metacognitive_proposal(current_step, event_suffix),
            ]
            if verified_state is None
            else []
        ),
        adjustment_proposals=[
            PolicyAdjustmentProposal(
                layer_id="evolutionary",
                source_id=f"layer:evolutionary:{event_suffix}",
                adjustments={"pheromone_positive_weight": 1.2},
                provenance="runtime:provider-free",
                trace_event_id=f"trace:adjustment:{event_suffix}",
            )
        ],
    )


def _request(
    context: _Context,
    source: VerifiedHybridSourceStepV2,
    advance_ref: str,
    *,
    observed_epoch: int,
) -> HybridReplayAdvanceRequestV2:
    return build_hybrid_replay_advance_request_v2(
        domain_root=context.domain.domain_root,
        scope_ref=context.domain.scope_ref,
        run_ref=_RUN_REF,
        observed_epoch=observed_epoch,
        advance_ref=advance_ref,
        source=source,
    )


def _advance(
    context: _Context,
    request: HybridReplayAdvanceRequestV2,
    source: VerifiedHybridSourceStepV2,
) -> GovernanceCommitAttemptV2:
    session = open_hybrid_replay_authority_session_v2(context.capability, request)
    return advance_hybrid_replay_state_v2(
        request,
        source=source,
        authority_session=session,
    )


def _manifest() -> ScopedProtocolManifestV2:
    policy = CollectiveDecisionPolicy(
        mode="hybrid",
        min_independent_scouts=2,
        quorum_threshold=2,
        pheromone_enabled=True,
        pheromone_evaporation_rate=0.2,
        pheromone_positive_weight=1.0,
        pheromone_negative_weight=1.0,
        pheromone_cautionary_weight=1.0,
        pheromone_cautionary_override_threshold=1.0,
        pheromone_novelty_weight=0.5,
        pheromone_per_source_cap=4.0,
        pheromone_per_round_deposit_cap=5.0,
        pheromone_scored_subject_types=["candidate", "route"],
        pheromone_kind_profiles={
            "positive": PheromoneKindProfile(
                weight=1.0,
                evaporation_rate=0.2,
                ttl_steps=6,
                response_model="saturating",
                priority=1,
                scored_subject_types=["candidate", "route"],
            )
        },
        pheromone_response_model="saturating",
        pheromone_activation_threshold=0.1,
        pheromone_saturation_threshold=4.0,
        pheromone_competition_mode="normalize",
        pheromone_exploration_floor=0.1,
        pheromone_diffusion_enabled=True,
        pheromone_diffusion_max_hops=1,
        pheromone_diffusion_attenuation=0.5,
        pheromone_feedback_enabled=True,
        exploration_enabled=True,
        exploration_floor=0.1,
        novelty_decay_rate=0.5,
        stale_route_reopen_threshold=0.2,
        layer_coordination_enabled=True,
        layer_weight_bounds={
            "reactive": (0.0, 1.5),
            "learned": (0.0, 1.5),
            "evolutionary": (0.0, 1.0),
            "metacognitive": (0.0, 1.0),
        },
        layer_default_weights={
            "reactive": 1.0,
            "learned": 1.0,
            "evolutionary": 0.5,
            "metacognitive": 0.5,
        },
        layer_confidence_thresholds={
            "reactive": 0.5,
            "learned": 0.5,
            "evolutionary": 0.5,
            "metacognitive": 0.5,
        },
        layer_conflict_threshold=0.1,
        layer_emergency_override_threshold=0.8,
        layer_min_provenance=1,
        policy_adjustment_bounds={"pheromone_positive_weight": (0.5, 2.0)},
        fallback_candidate=_FALLBACK_REF,
    )
    required_events = sorted(
        _BASELINE_TRACE_EVENTS | required_swarm_trace_events(policy)
    )
    return ScopedProtocolManifestV2(
        protocol_version=PROTOCOL_VERSION_V2,
        id="protocol:hybrid-replay-v2",
        targets=(TargetSpec(_TARGET_REF, "durable Hybrid replay target"),),
        candidates=(
            CandidateSpec(_CANDIDATE_REF, _TARGET_REF),
            CandidateSpec(_FALLBACK_REF, _TARGET_REF, True),
        ),
        quorum_policy=QuorumPolicy(_TARGET_REF, _FALLBACK_REF, 2),
        authority_policy=ScopedAuthorityPolicyV2(
            policy_version="pheroos-scoped-authority-policy-v2",
            profile="pheroos-scoped-authority-local-v2",
            wire_version="pheroos-authority-wire-v2",
            canonical_version="pheroos-authority-canonical-v2",
            ledger_version="pheroos-governance-authority-ledger-v2",
            state_store_version="pheroos-governance-state-store-v2",
            trace_batch_version="pheroos-governance-trace-batch-v2",
            read_set_version="pheroos-governance-authority-read-set-v2",
        ),
        output_policy=BaselineOutputPolicyV2(
            BASELINE_OUTPUT_POLICY_VERSION_V2,
            "quorum",
            (
                BaselineOutputActionPolicyV2(
                    _ACTION_REF,
                    "publish",
                    _TARGET_REF,
                    ("evidence_commit", "safe_fallback"),
                ),
            ),
        ),
        trace_policy=TracePolicy(required_events),
        evidence_policy=EvidencePolicy(),
        collective_decision_policy=policy,
    )


def _expanded_candidate_manifest(
    manifest: ScopedProtocolManifestV2,
) -> ScopedProtocolManifestV2:
    return replace(
        manifest,
        candidates=(
            CandidateSpec(_CANDIDATE_REF, _TARGET_REF),
            CandidateSpec("candidate:beta", _TARGET_REF),
            CandidateSpec(_FALLBACK_REF, _TARGET_REF, True),
        ),
    )


def _adjusted_manifest(
    manifest: ScopedProtocolManifestV2,
) -> ScopedProtocolManifestV2:
    assert manifest.collective_decision_policy is not None
    return replace(
        manifest,
        collective_decision_policy=replace(
            manifest.collective_decision_policy,
            pheromone_positive_weight=1.1,
        ),
    )


def _topology() -> PheromoneNeighborhood:
    return PheromoneNeighborhood(
        subjects=[
            PheromoneSubject("candidate", _CANDIDATE_REF, _CANDIDATE_REF, _TARGET_REF),
            PheromoneSubject("route", "route:alpha", _CANDIDATE_REF, _TARGET_REF),
        ],
        edges=[
            PheromoneEdge(
                "route",
                "route:alpha",
                "candidate",
                _CANDIDATE_REF,
                1.0,
            )
        ],
    )


def _expanded_topology() -> PheromoneNeighborhood:
    value = _topology()
    return PheromoneNeighborhood(
        subjects=[
            *value.subjects,
            PheromoneSubject("route", "route:extra", _CANDIDATE_REF, _TARGET_REF),
        ],
        edges=list(value.edges),
    )


def _scout(source_ref: str, current_step: int) -> ScoutReport:
    return ScoutReport(
        source_ref,
        _CANDIDATE_REF,
        f"evidence:{source_ref}",
        "runtime:provider-free",
        target=_TARGET_REF,
        trace_event_id=f"trace:{source_ref}:{current_step}",
        verification=verify_signal_input(
            target=_TARGET_REF,
            source_id=source_ref,
            subject_id=_CANDIDATE_REF,
            verifier_id="governance:hybrid-replay-conformance",
            authority=AuthorityLevel.GOVERNANCE,
            provenance="governance:hybrid-replay-conformance",
            trace_event_id=f"trace:{source_ref}:{current_step}:verified",
        ),
    )


def _deposit(current_step: int, suffix: str) -> PheromoneTrail:
    return PheromoneTrail(
        candidate_id=_CANDIDATE_REF,
        strength=1.0,
        subject_type="route",
        subject_id="route:alpha",
        target=_TARGET_REF,
        kind="positive",
        source_id=f"runtime:{suffix}",
        evidence_id=f"evidence:deposit:{suffix}",
        provenance="runtime:provider-free",
        trace_event_id=f"trace:deposit:{suffix}",
        deposited_at_step=current_step,
        updated_at_step=current_step,
    )


def _feedback(current_step: int, suffix: str) -> PheromoneFeedback:
    return PheromoneFeedback(
        source_id=f"runtime:{suffix}",
        subject_type="route",
        subject_id="route:alpha",
        candidate_id=_CANDIDATE_REF,
        target=_TARGET_REF,
        outcome="success",
        reward=1.0,
        strength_delta=0.5,
        evidence_id=f"evidence:feedback:{suffix}",
        provenance="runtime:provider-free",
        trace_event_id=f"trace:feedback:{suffix}",
        step=current_step,
    )


def _learned_proposal(current_step: int, suffix: str) -> LayerProposal:
    return LayerProposal(
        "learned",
        f"layer:learned:{suffix}",
        _TARGET_REF,
        _CANDIDATE_REF,
        "support",
        0.9,
        support=1.0,
        evidence_id=f"evidence:layer:{suffix}",
        provenance="runtime:provider-free",
        trace_event_id=f"trace:layer:{suffix}:{current_step}",
    )


def _metacognitive_proposal(current_step: int, suffix: str) -> LayerProposal:
    return LayerProposal(
        "metacognitive",
        f"layer:metacognitive:{suffix}",
        _TARGET_REF,
        _CANDIDATE_REF,
        "confirm_trace_coverage",
        0.8,
        evidence_id=f"evidence:metacognitive:{suffix}",
        provenance="runtime:provider-free",
        trace_event_id=f"trace:metacognitive:{suffix}:{current_step}",
    )


def _root(label: str) -> str:
    return "sha256:" + sha256(label.encode("utf-8")).hexdigest()


run_governance_hybrid_replay_conformance_v2.__module__ = "pheroos.conformance"


__all__ = [
    "GOVERNANCE_HYBRID_REPLAY_CONFORMANCE_VERSION_V2",
    "run_governance_hybrid_replay_conformance_v2",
]
