from __future__ import annotations

from types import MappingProxyType

import pheroos.governance as governance
import pheroos.protocol as protocol
import pheroos.trace as trace
from pheroos.conformance.report import CheckResult
from pheroos.drivers import DriverDescriptor, DriverRegistry
from pheroos.governance.candidate import Candidate, CandidateSet
from pheroos.governance.evidence import EvidenceGraph, EvidenceNode
from pheroos.governance.layer_coordination import LayerProposal
from pheroos.governance.pheromone import PheromoneTrail
from pheroos.governance.policy_adjustment import PolicyAdjustmentProposal
from pheroos.kernel import InputEnvelope


def check() -> CheckResult:
    """Prove the small public ownership and snapshot boundary contract."""

    problems: list[str] = []
    problems.extend(public_type_ownership_problems())
    problems.extend(registry_snapshot_problems())
    problems.extend(representative_snapshot_problems())
    return CheckResult("public_abi_boundary", not problems, ", ".join(problems))


def public_type_ownership_problems() -> list[str]:
    expected = (
        (
            governance.PheromoneKindProfile,
            protocol.PheromoneKindProfile,
            "pheroos.protocol.models",
            "pheromone_kind_profile",
        ),
        (
            governance.TraceEvent,
            trace.TraceEvent,
            "pheroos.trace",
            "trace_event",
        ),
        (
            governance.PheromoneTrail,
            PheromoneTrail,
            "pheroos.governance.pheromone",
            "pheromone_trail",
        ),
        (
            governance.LayerProposal,
            LayerProposal,
            "pheroos.governance.layer_coordination",
            "layer_proposal",
        ),
        (
            governance.PolicyAdjustmentProposal,
            PolicyAdjustmentProposal,
            "pheroos.governance.policy_adjustment",
            "policy_adjustment",
        ),
    )
    problems = [
        f"ownership:{label}"
        for exported, canonical, owner, label in expected
        if exported is not canonical or canonical.__module__ != owner
    ]
    kind_profile_exports = [
        name for name in governance.__all__ if "KindProfile" in name
    ]
    if kind_profile_exports != ["PheromoneKindProfile"]:
        problems.append("ownership:normalized_kind_profile_export")
    return problems


def registry_snapshot_problems() -> list[str]:
    registry = DriverRegistry()
    registry.register(
        DriverDescriptor(
            id="driver:conformance",
            kind="tool",
            version="1",
            capabilities=["invoke"],
        )
    )
    view = registry.descriptors
    problems: list[str] = []
    if not isinstance(view, MappingProxyType):
        problems.append("registry:view_type")
    try:
        view["driver:forged"] = DriverDescriptor(  # type: ignore[index]
            id="driver:forged",
            kind="tool",
            version="1",
        )
    except TypeError:
        pass
    else:
        problems.append("registry:mutable_view")
    inspected = view["driver:conformance"]
    object.__setattr__(inspected, "id", "driver:forged")
    if registry.get("driver:conformance").id != "driver:conformance":
        problems.append("registry:aliased_descriptor")
    return problems


def representative_snapshot_problems() -> list[str]:
    profile_subjects = ["candidate"]
    profile_extensions = {"x-profile": {"values": ["original"]}}
    kind_profile = protocol.PheromoneKindProfile(
        scored_subject_types=profile_subjects,
        extensions=profile_extensions,
    )
    policy_profiles = {"positive": kind_profile}
    layer_bounds = {"learned": [0.0, 1.0]}
    policy = protocol.CollectiveDecisionPolicy(
        pheromone_kind_profiles=policy_profiles,
        layer_weight_bounds=layer_bounds,
    )
    candidate_inputs = [Candidate("candidate:one", "decision:one")]
    evidence_inputs = [EvidenceNode("evidence:one", "content", "driver:one")]
    candidate_set = CandidateSet(candidate_inputs)
    evidence = EvidenceGraph(evidence_inputs)
    metadata = {"nested": {"values": ["original"]}}
    envelope = InputEnvelope("snapshot", metadata=metadata)
    trace_store = trace.InMemoryTraceStore()
    trace_store.append(
        trace.TraceEvent(
            event_type="plan",
            protocol_id="conformance.snapshot",
            target="decision:snapshot",
            reason="append-only snapshot proof",
            lineage={"nested": {"values": ["original"]}},
        )
    )

    profile_subjects.append("route")
    profile_extensions["x-profile"]["values"].append("mutated")
    policy_profiles.clear()
    layer_bounds["learned"][1] = 10.0
    candidate_inputs.append(Candidate("candidate:forged", "decision:one"))
    evidence_inputs.clear()
    metadata["nested"]["values"].append("mutated")
    trace_store._records[0].event.lineage["nested"]["values"].append("mutated")

    problems: list[str] = []
    if kind_profile.scored_subject_types != ("candidate",):
        problems.append("snapshot:kind_subjects")
    if kind_profile.extensions["x-profile"]["values"] != ("original",):
        problems.append("snapshot:kind_extensions")
    if tuple(policy.pheromone_kind_profiles) != ("positive",):
        problems.append("snapshot:policy_profiles")
    if policy.layer_weight_bounds["learned"] != (0.0, 1.0):
        problems.append("snapshot:policy_bounds")
    if tuple(candidate.id for candidate in candidate_set.candidates) != ("candidate:one",):
        problems.append("snapshot:candidates")
    if tuple(node.id for node in evidence.nodes) != ("evidence:one",):
        problems.append("snapshot:evidence")
    if envelope.metadata["nested"]["values"] != ("original",):
        problems.append("snapshot:kernel_metadata")
    if trace_store.records[0].event.lineage["nested"]["values"] != ["original"]:
        problems.append("snapshot:trace_store")
    return problems


__all__ = ["check"]
