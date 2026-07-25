"""Opaque source proof for one context-bound Hybrid Replay v2 evaluation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, NoReturn, SupportsIndex, cast, final

from pheroos.governance._authority_store_v2_contracts.foundation import (
    _compute_root,
    _require_root,
)
from pheroos.governance._hybrid_replay_v2.canonical import (
    _canonical_hybrid_value_v2,
)
from pheroos.governance._hybrid_replay_v2.contracts import (
    HYBRID_REPLAY_GENESIS_SNAPSHOT_ROOT_V2,
    HybridReplaySnapshotV2,
    _require_bounded_text,
    _require_count,
)
from pheroos.governance._hybrid_replay_v2.numeric import encode_binary64_v1
from pheroos.governance._pheromone.records import (
    PheromoneEdge,
    PheromoneNeighborhood,
    PheromoneSubject,
)
from pheroos.governance._swarm.records import HybridCollectiveStep
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.authority_manifest_v2 import ScopedProtocolManifestV2


_SOURCE_PROOF_VERSION_V2 = "pheroos-hybrid-replay-source-proof-v2"


@dataclass(frozen=True, slots=True)
class _HybridSourceBindingV2:
    domain_root: str
    scope_ref: str
    run_ref: str
    observed_epoch: int
    manifest_root: str
    protocol_ref: str
    target_ref: str
    current_step: int
    candidate_projection_root: str
    base_policy_projection_root: str
    input_policy_projection_root: str
    topology_projection_root: str
    parent_snapshot_root: str
    source_step_root: str
    context_root: str

    def body(self) -> dict[str, object]:
        return {
            "version": _SOURCE_PROOF_VERSION_V2,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "run_ref": self.run_ref,
            "observed_epoch": self.observed_epoch,
            "manifest_root": self.manifest_root,
            "protocol_ref": self.protocol_ref,
            "target_ref": self.target_ref,
            "current_step": self.current_step,
            "candidate_projection_root": self.candidate_projection_root,
            "base_policy_projection_root": self.base_policy_projection_root,
            "input_policy_projection_root": self.input_policy_projection_root,
            "topology_projection_root": self.topology_projection_root,
            "parent_snapshot_root": self.parent_snapshot_root,
            "source_step_root": self.source_step_root,
        }


@dataclass(frozen=True, slots=True)
class _VerifiedHybridSourceMaterialV2:
    step: HybridCollectiveStep
    manifest: ScopedProtocolManifestV2
    topology: PheromoneNeighborhood
    input_policy_projection: dict[str, object]
    parent_snapshot: HybridReplaySnapshotV2 | None
    binding: _HybridSourceBindingV2


@final
class VerifiedHybridSourceStepV2:
    """Non-portable proof that a Hybrid step was evaluated in one v2 context."""

    __slots__ = (
        "_binding",
        "_input_policy_projection",
        "_manifest",
        "_parent_snapshot",
        "_step",
        "_topology",
    )

    def __new__(cls, *_args: object, **_kwargs: object) -> VerifiedHybridSourceStepV2:
        raise TypeError("VerifiedHybridSourceStepV2 cannot be constructed directly")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("VerifiedHybridSourceStepV2 is final")

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("VerifiedHybridSourceStepV2 is immutable")

    def __copy__(self) -> VerifiedHybridSourceStepV2:
        _verified_hybrid_source_material_v2(self)
        return self

    def __deepcopy__(self, _memo: dict[int, object]) -> VerifiedHybridSourceStepV2:
        _verified_hybrid_source_material_v2(self)
        return self

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedHybridSourceStepV2 is not portable")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedHybridSourceStepV2 is not portable")

    def __getstate__(self) -> NoReturn:
        raise TypeError("VerifiedHybridSourceStepV2 is not portable")

    def __repr__(self) -> str:
        return "<VerifiedHybridSourceStepV2 redacted>"

    @property
    def source_step(self) -> HybridCollectiveStep:
        return _verified_hybrid_source_material_v2(self).step

    @property
    def context_root(self) -> str:
        return _verified_hybrid_source_material_v2(self).binding.context_root


def _issue_verified_hybrid_source_step_v2(
    *,
    domain_root: str,
    scope_ref: str,
    run_ref: str,
    observed_epoch: int,
    step: HybridCollectiveStep,
    manifest: ScopedProtocolManifestV2,
    topology: PheromoneNeighborhood,
    input_policy_projection: dict[str, object],
    candidate_projection_root: str,
    base_policy_projection_root: str,
    topology_projection_root: str,
    parent_snapshot: HybridReplaySnapshotV2 | None,
    current_step: int,
) -> VerifiedHybridSourceStepV2:
    domain_root, scope_ref, run_ref, observed_epoch = (
        _validate_hybrid_source_authority_context_v2(
            domain_root=domain_root,
            scope_ref=scope_ref,
            run_ref=run_ref,
            observed_epoch=observed_epoch,
        )
    )
    if type(manifest) is not ScopedProtocolManifestV2:
        raise TypeError("Hybrid source proof requires exact ScopedProtocolManifestV2")
    if type(topology) is not PheromoneNeighborhood:
        raise TypeError("Hybrid source proof requires exact PheromoneNeighborhood")
    _validate_source_step_v2(step, manifest.id, manifest.quorum_policy.target)
    if _source_current_step(step) != current_step:
        raise GovernanceError("Hybrid source proof current_step is mismatched")
    target_ref = manifest.quorum_policy.target
    if any(
        event.protocol_id != manifest.id or event.target != target_ref
        for event in step.trace_events
    ):
        raise GovernanceError("Hybrid source proof protocol or target is mismatched")
    detached_manifest = ScopedProtocolManifestV2.from_dict(manifest.to_dict())
    detached_topology = _detach_topology(topology)
    detached_input = cast(
        dict[str, object],
        _detach_json(input_policy_projection),
    )
    detached_parent = (
        None
        if parent_snapshot is None
        else HybridReplaySnapshotV2.from_dict(parent_snapshot.to_dict())
    )
    source_step_root = _compute_root(
        "hybrid-replay-source-step", _canonical_hybrid_value_v2(step)
    )
    input_policy_root = _compute_root(
        "hybrid-replay-input-policy-projection", detached_input
    )
    binding = _HybridSourceBindingV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        observed_epoch=observed_epoch,
        manifest_root=detached_manifest.manifest_root,
        protocol_ref=detached_manifest.id,
        target_ref=target_ref,
        current_step=current_step,
        candidate_projection_root=candidate_projection_root,
        base_policy_projection_root=base_policy_projection_root,
        input_policy_projection_root=input_policy_root,
        topology_projection_root=topology_projection_root,
        parent_snapshot_root=(
            HYBRID_REPLAY_GENESIS_SNAPSHOT_ROOT_V2
            if detached_parent is None
            else detached_parent.snapshot_root
        ),
        source_step_root=source_step_root,
        context_root="",
    )
    binding = replace(
        binding,
        context_root=_compute_root("hybrid-replay-source-context-v2", binding.body()),
    )
    handle = object.__new__(VerifiedHybridSourceStepV2)
    object.__setattr__(handle, "_step", step)
    object.__setattr__(handle, "_manifest", detached_manifest)
    object.__setattr__(handle, "_topology", detached_topology)
    object.__setattr__(handle, "_input_policy_projection", detached_input)
    object.__setattr__(handle, "_parent_snapshot", detached_parent)
    object.__setattr__(handle, "_binding", binding)
    _verified_hybrid_source_material_v2(handle)
    return handle


def _verified_hybrid_source_material_v2(
    source: object,
) -> _VerifiedHybridSourceMaterialV2:
    if type(source) is not VerifiedHybridSourceStepV2:
        raise TypeError("Hybrid Replay v2 requires exact VerifiedHybridSourceStepV2")
    try:
        step = object.__getattribute__(source, "_step")
        manifest = object.__getattribute__(source, "_manifest")
        topology = object.__getattribute__(source, "_topology")
        input_policy = object.__getattribute__(source, "_input_policy_projection")
        parent = object.__getattribute__(source, "_parent_snapshot")
        binding = object.__getattribute__(source, "_binding")
    except AttributeError as exc:
        raise GovernanceError("Hybrid source proof is malformed") from exc
    if (
        type(step) is not HybridCollectiveStep
        or type(manifest) is not ScopedProtocolManifestV2
        or type(topology) is not PheromoneNeighborhood
        or type(input_policy) is not dict
        or (parent is not None and type(parent) is not HybridReplaySnapshotV2)
        or type(binding) is not _HybridSourceBindingV2
    ):
        raise GovernanceError("Hybrid source proof material is malformed")
    expected = _source_binding(
        step=step,
        manifest=manifest,
        topology=topology,
        input_policy_projection=input_policy,
        parent_snapshot=parent,
        binding=binding,
    )
    if binding != expected:
        raise GovernanceError("Hybrid source proof authority binding is invalid")
    return _VerifiedHybridSourceMaterialV2(
        step=step,
        manifest=ScopedProtocolManifestV2.from_dict(manifest.to_dict()),
        topology=_detach_topology(topology),
        input_policy_projection=cast(dict[str, object], _detach_json(input_policy)),
        parent_snapshot=(
            None
            if parent is None
            else HybridReplaySnapshotV2.from_dict(parent.to_dict())
        ),
        binding=expected,
    )


def _verified_hybrid_source_manifest_v2(
    source: object,
) -> ScopedProtocolManifestV2:
    """Return the exact detached manifest carried by a valid source proof."""

    return _verified_hybrid_source_material_v2(source).manifest


def _source_binding(
    *,
    step: HybridCollectiveStep,
    manifest: ScopedProtocolManifestV2,
    topology: PheromoneNeighborhood,
    input_policy_projection: dict[str, object],
    parent_snapshot: HybridReplaySnapshotV2 | None,
    binding: _HybridSourceBindingV2,
) -> _HybridSourceBindingV2:
    domain_root, scope_ref, run_ref, observed_epoch = (
        _validate_hybrid_source_authority_context_v2(
            domain_root=binding.domain_root,
            scope_ref=binding.scope_ref,
            run_ref=binding.run_ref,
            observed_epoch=binding.observed_epoch,
        )
    )
    _validate_source_step_v2(step, manifest.id, manifest.quorum_policy.target)
    if _source_current_step(step) != binding.current_step:
        raise GovernanceError("Hybrid source proof current_step changed")
    target_ref = manifest.quorum_policy.target
    if any(
        event.protocol_id != manifest.id or event.target != target_ref
        for event in step.trace_events
    ):
        raise GovernanceError("Hybrid source proof trace binding changed")
    source_root = _compute_root(
        "hybrid-replay-source-step", _canonical_hybrid_value_v2(step)
    )
    candidate = _HybridSourceBindingV2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        observed_epoch=observed_epoch,
        manifest_root=manifest.manifest_root,
        protocol_ref=manifest.id,
        target_ref=target_ref,
        current_step=binding.current_step,
        candidate_projection_root=binding.candidate_projection_root,
        base_policy_projection_root=binding.base_policy_projection_root,
        input_policy_projection_root=_compute_root(
            "hybrid-replay-input-policy-projection", input_policy_projection
        ),
        topology_projection_root=_compute_root(
            "hybrid-replay-topology-projection", _topology_projection(topology)
        ),
        parent_snapshot_root=(
            HYBRID_REPLAY_GENESIS_SNAPSHOT_ROOT_V2
            if parent_snapshot is None
            else parent_snapshot.snapshot_root
        ),
        source_step_root=source_root,
        context_root="",
    )
    return replace(
        candidate,
        context_root=_compute_root("hybrid-replay-source-context-v2", candidate.body()),
    )


def _validate_hybrid_source_authority_context_v2(
    *,
    domain_root: object,
    scope_ref: object,
    run_ref: object,
    observed_epoch: object,
) -> tuple[str, str, str, int]:
    """Validate the authority context that one source evaluation belongs to."""

    return (
        _require_root(domain_root, "Hybrid source proof domain_root"),
        _require_bounded_text(scope_ref, "Hybrid source proof scope_ref"),
        _require_bounded_text(run_ref, "Hybrid source proof run_ref"),
        _require_count(observed_epoch, "Hybrid source proof observed_epoch"),
    )


def _require_hybrid_source_authority_context_v2(
    material: _VerifiedHybridSourceMaterialV2,
    *,
    domain_root: object,
    scope_ref: object,
    run_ref: object,
    observed_epoch: object,
) -> None:
    """Reject re-stamping one evaluated source into another authority context."""

    expected = _validate_hybrid_source_authority_context_v2(
        domain_root=domain_root,
        scope_ref=scope_ref,
        run_ref=run_ref,
        observed_epoch=observed_epoch,
    )
    binding = material.binding
    actual = (
        binding.domain_root,
        binding.scope_ref,
        binding.run_ref,
        binding.observed_epoch,
    )
    if actual != expected:
        labels = ("domain_root", "scope_ref", "run_ref", "observed_epoch")
        changed = next(
            label
            for label, actual_value, expected_value in zip(
                labels, actual, expected, strict=True
            )
            if actual_value != expected_value
        )
        raise GovernanceError(
            f"Hybrid source proof authority context {changed} is mismatched"
        )


def _source_current_step(step: HybridCollectiveStep) -> int:
    events = [
        event for event in step.trace_events if event.event_type == "pheromone_score"
    ]
    if len(events) != 1:
        raise GovernanceError("Hybrid source proof requires one pheromone_score event")
    value = events[0].lineage.get("current_step")
    if type(value) is not int or value < 0:
        raise GovernanceError("Hybrid source proof current_step is malformed")
    return value


def _validate_source_step_v2(
    step: object,
    protocol_ref: str,
    target_ref: str,
) -> None:
    """Validate complete v2 evaluation content without a process-local token."""

    if type(step) is not HybridCollectiveStep:
        raise GovernanceError("Hybrid source proof step is not evaluation-complete")
    if not step.trace_events or any(
        event.protocol_id != protocol_ref or event.target != target_ref
        for event in step.trace_events
    ):
        raise GovernanceError("Hybrid source proof step is not evaluation-complete")
    receipt_sets = (
        set(step.deposit_replay_receipts),
        set(step.diffusion_replay_receipts),
        set(step.feedback_replay_receipts),
        set(step.adjustment_replay_receipts),
    )
    all_receipt_ids = set().union(*receipt_sets)
    if (
        sum(len(item) for item in receipt_sets) != len(all_receipt_ids)
        or (receipt_sets[0] | receipt_sets[1])
        != set(step.processed_pheromone_event_ids)
        or receipt_sets[2] != set(step.processed_feedback_ids)
        or receipt_sets[3] != set(step.processed_adjustment_ids)
    ):
        raise GovernanceError("Hybrid source proof step is not evaluation-complete")
    event_receipt_kinds = {
        "pheromone_deposit": (step.processed_pheromone_event_ids, "trace_event_id"),
        "pheromone_diffuse": (step.processed_pheromone_event_ids, "trace_event_id"),
        "pheromone_reinforce": (step.processed_feedback_ids, "trace_event_id"),
        "policy_adjustment": (step.processed_adjustment_ids, "source_trace_event_id"),
    }
    for event in step.trace_events:
        expected = event_receipt_kinds.get(event.event_type)
        if expected is None:
            continue
        processed_ids, lineage_field = expected
        event_id = event.lineage.get(lineage_field)
        if type(event_id) is not str or event_id not in processed_ids:
            raise GovernanceError("Hybrid source proof step is not evaluation-complete")
    # Canonicalization traverses every durable output field and rejects unknown
    # mutable/runtime objects. The root is re-derived on every handle access.
    _canonical_hybrid_value_v2(step)


def _detach_topology(value: PheromoneNeighborhood) -> PheromoneNeighborhood:
    return PheromoneNeighborhood(
        subjects=[
            PheromoneSubject(
                subject_type=item.subject_type,
                subject_id=item.subject_id,
                candidate_id=item.candidate_id,
                target=item.target,
            )
            for item in value.subjects
        ],
        edges=[
            PheromoneEdge(
                source_subject_type=item.source_subject_type,
                source_subject_id=item.source_subject_id,
                target_subject_type=item.target_subject_type,
                target_subject_id=item.target_subject_id,
                attenuation=item.attenuation,
            )
            for item in value.edges
        ],
    )


def _topology_projection(value: PheromoneNeighborhood) -> dict[str, object]:
    return {
        "subjects": [
            {
                "subject_type": item.subject_type,
                "subject_ref": item.subject_id,
                "candidate_ref": item.candidate_id,
                "target_ref": item.target,
            }
            for item in sorted(
                value.subjects,
                key=lambda item: (item.subject_type, item.subject_id),
            )
        ],
        "edges": [
            {
                "source_subject_type": item.source_subject_type,
                "source_subject_ref": item.source_subject_id,
                "target_subject_type": item.target_subject_type,
                "target_subject_ref": item.target_subject_id,
                "attenuation": _topology_attenuation(item.attenuation),
            }
            for item in sorted(
                value.edges,
                key=lambda item: (
                    item.source_subject_type,
                    item.source_subject_id,
                    item.target_subject_type,
                    item.target_subject_id,
                ),
            )
        ],
    }


def _topology_attenuation(value: object) -> str:
    if type(value) not in (int, float):
        raise TypeError("Hybrid source topology attenuation must be numeric")
    return encode_binary64_v1(
        float(cast(int | float, value)), "Hybrid source topology attenuation"
    )


def _detach_json(value: object) -> object:
    if type(value) is dict:
        return {key: _detach_json(item) for key, item in value.items()}
    if type(value) in (tuple, list):
        return [_detach_json(item) for item in cast(tuple[Any, ...] | list[Any], value)]
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise TypeError("Hybrid source proof projection is not canonical JSON")


__all__ = ["VerifiedHybridSourceStepV2"]
