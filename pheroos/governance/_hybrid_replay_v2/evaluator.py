"""High-level Hybrid evaluator backed by scoped manifest and replay v2."""

from __future__ import annotations

from pheroos.governance._authority_store_v2_contracts.foundation import _compute_root
from pheroos.governance._hybrid_replay_v2.contracts import HybridReplaySnapshotV2
from pheroos.governance._hybrid_replay_v2.operations import (
    VerifiedHybridReplayStateV2,
    require_current_hybrid_replay_state_v2,
)
from pheroos.governance._hybrid_replay_v2.projection import (
    _candidate_projection,
    project_collective_policy_v2,
    project_topology_v2,
    restore_hybrid_replay_inputs_v2,
)
from pheroos.governance._hybrid_replay_v2.source import (
    VerifiedHybridSourceStepV2,
    _issue_verified_hybrid_source_step_v2,
    _validate_hybrid_source_authority_context_v2,
)
from pheroos.governance._pheromone.records import (
    PheromoneNeighborhood,
    PheromoneTrail,
)
from pheroos.governance._swarm.pipeline import _evaluate_hybrid_collective_step_v2
from pheroos.governance._swarm.records import HybridReplayState
from pheroos.governance._swarm.signals import (
    InhibitionSignal,
    RecruitmentSignal,
    ScoutReport,
)
from pheroos.governance.candidate import Candidate, CandidateSet
from pheroos.governance.errors import GovernanceError
from pheroos.governance.layer_coordination import (
    LayerPerformanceSnapshot,
    LayerProposal,
    StrategyBias,
)
from pheroos.governance.pheromone_feedback import PheromoneFeedback
from pheroos.governance.policy_adjustment import PolicyAdjustmentProposal
from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2
from pheroos.protocol.models import CollectiveDecisionPolicy


def evaluate_hybrid_collective_step_v2(
    *,
    domain_root: str,
    scope_ref: str,
    run_ref: str,
    observed_epoch: int,
    manifest: ScopedProtocolManifestV2,
    current_step: int,
    scout_reports: list[ScoutReport],
    topology: PheromoneNeighborhood,
    verified_replay_state: VerifiedHybridReplayStateV2 | None = None,
    recruitment_signals: list[RecruitmentSignal] | None = None,
    inhibition_signals: list[InhibitionSignal] | None = None,
    deposits: list[PheromoneTrail] | None = None,
    feedback: list[PheromoneFeedback] | None = None,
    layer_proposals: list[LayerProposal] | None = None,
    performance_snapshots: list[LayerPerformanceSnapshot] | None = None,
    strategy_biases: list[StrategyBias] | None = None,
    adjustment_proposals: list[PolicyAdjustmentProposal] | None = None,
    attention_only: bool = False,
) -> VerifiedHybridSourceStepV2:
    """Evaluate a context-bound source step from genesis or a current parent.

    The exact authority domain, scope, run, and observed epoch bind the source
    proof before it can be projected into a request.  The exact scoped manifest
    owns protocol, target, candidates, base policy, and safe fallback. Portable
    snapshots, caller-supplied declaration fragments, and legacy replay records
    are not accepted. A concurrent successor may still race this pure
    evaluation; the later Store advance closes that race with its authoritative
    compare-and-swap read set.
    """

    domain_root, scope_ref, run_ref, observed_epoch = (
        _validate_hybrid_source_authority_context_v2(
            domain_root=domain_root,
            scope_ref=scope_ref,
            run_ref=run_ref,
            observed_epoch=observed_epoch,
        )
    )
    parent = _current_parent_snapshot(verified_replay_state)
    base_policy, candidate_set, target = _manifest_context(manifest)
    candidate_projection = _candidate_projection(
        candidate_set,
        target,
        manifest.quorum_policy.fallback_candidate,
    )
    base_policy_projection = project_collective_policy_v2(base_policy)
    topology_projection = project_topology_v2(topology)
    input_policy = base_policy
    evaluation_topology = topology
    replay_state: HybridReplayState | None = None
    if parent is not None:
        _require_parent_authority_context(
            parent,
            domain_root=domain_root,
            scope_ref=scope_ref,
            run_ref=run_ref,
            observed_epoch=observed_epoch,
        )
        _require_parent_declarations(
            parent,
            manifest=manifest,
            candidate_projection=candidate_projection,
            base_policy_projection=base_policy_projection,
            topology_projection=topology_projection,
        )
        if type(current_step) is not int or current_step <= parent.current_step:
            raise GovernanceError(
                "Hybrid replay v2 current_step must advance its verified parent"
            )
        restored = restore_hybrid_replay_inputs_v2(parent)
        input_policy = restored.effective_policy
        evaluation_topology = restored.topology
        replay_state = restored.replay_state

    input_policy_projection = project_collective_policy_v2(input_policy)
    step = _evaluate_hybrid_collective_step_v2(
        protocol_id=manifest.id,
        candidate_set=candidate_set,
        policy=input_policy,
        target=target,
        current_step=current_step,
        scout_reports=scout_reports,
        recruitment_signals=recruitment_signals,
        inhibition_signals=inhibition_signals,
        deposits=deposits,
        topology=evaluation_topology,
        feedback=feedback,
        layer_proposals=layer_proposals,
        performance_snapshots=performance_snapshots,
        strategy_biases=strategy_biases,
        adjustment_proposals=adjustment_proposals,
        replay_state=replay_state,
        fallback_candidate_id=manifest.quorum_policy.fallback_candidate,
        attention_only=attention_only,
    )
    return _issue_verified_hybrid_source_step_v2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        observed_epoch=observed_epoch,
        step=step,
        manifest=manifest,
        topology=topology,
        input_policy_projection=input_policy_projection,
        candidate_projection_root=_compute_root(
            "hybrid-replay-candidate-projection", candidate_projection
        ),
        base_policy_projection_root=_compute_root(
            "hybrid-replay-policy-projection", base_policy_projection
        ),
        topology_projection_root=_compute_root(
            "hybrid-replay-topology-projection", topology_projection
        ),
        parent_snapshot=parent,
        current_step=current_step,
    )


def _require_parent_authority_context(
    parent: HybridReplaySnapshotV2,
    *,
    domain_root: str,
    scope_ref: str,
    run_ref: str,
    observed_epoch: int,
) -> None:
    for field, expected in (
        ("domain_root", domain_root),
        ("scope_ref", scope_ref),
        ("run_ref", run_ref),
    ):
        if getattr(parent, field) != expected:
            raise GovernanceError(f"Hybrid replay v2 parent {field} is cross-bound")
    if observed_epoch < parent.observed_epoch:
        raise GovernanceError("Hybrid replay v2 observed_epoch cannot roll back")


def _current_parent_snapshot(
    state: VerifiedHybridReplayStateV2 | None,
) -> HybridReplaySnapshotV2 | None:
    if state is None:
        return None
    # Exact-type, Store-inclusion, receipt, and current-position verification
    # belongs to the operations owner.  A snapshot property read is weaker.
    return require_current_hybrid_replay_state_v2(state)


def _manifest_context(
    manifest: ScopedProtocolManifestV2,
) -> tuple[CollectiveDecisionPolicy, CandidateSet, str]:
    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("Hybrid Replay v2 requires exact ScopedProtocolManifestV2")
    policy = manifest.collective_decision_policy
    if type(policy) is not CollectiveDecisionPolicy or policy.mode != "hybrid":
        raise GovernanceError("Hybrid Replay v2 requires a declared Hybrid policy")
    target = manifest.quorum_policy.target
    if policy.fallback_candidate != manifest.quorum_policy.fallback_candidate:
        raise GovernanceError(
            "Hybrid Replay v2 collective and quorum fallbacks must match"
        )
    return (
        policy,
        CandidateSet(
            tuple(
                Candidate(item.id, item.target, item.safe_fallback)
                for item in manifest.candidates
            )
        ),
        target,
    )


def _require_parent_declarations(
    parent: HybridReplaySnapshotV2,
    *,
    manifest: ScopedProtocolManifestV2,
    candidate_projection: dict[str, object],
    base_policy_projection: dict[str, object],
    topology_projection: dict[str, object],
) -> None:
    if parent.manifest_root != manifest.manifest_root:
        raise GovernanceError("Hybrid replay v2 parent manifest is mismatched")
    if parent.protocol_ref != manifest.id:
        raise GovernanceError("Hybrid replay v2 parent protocol is mismatched")
    if parent.target_ref != manifest.quorum_policy.target:
        raise GovernanceError("Hybrid replay v2 parent target is mismatched")
    payload = parent.to_dict()
    expected = (
        ("candidate_projection", candidate_projection, "candidate set"),
        ("policy_projection", base_policy_projection, "manifest base policy"),
        ("topology_projection", topology_projection, "topology"),
    )
    for field, value, label in expected:
        if payload[field] != value:
            raise GovernanceError(f"Hybrid replay v2 parent {label} is mismatched")


__all__ = ["evaluate_hybrid_collective_step_v2"]
