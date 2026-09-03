from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import cast

import pheroos.governance as governance
import pheroos.protocol as protocol
import pheroos.trace as trace
from pheroos.conformance.public_api_inventory import (
    build_public_api_inventory,
    load_public_api_inventory,
    public_api_inventory_differences,
)
from pheroos.conformance.public_api_lifecycle import (
    build_public_api_lifecycle,
    load_public_api_lifecycle,
    public_api_lifecycle_differences,
    public_api_lifecycle_problems,
)
from pheroos.conformance.report import CheckResult
from pheroos.drivers import DriverDescriptor, DriverRegistry
from pheroos.governance.candidate import Candidate, CandidateSet
from pheroos.governance.certificate import (
    EvidenceCommitCertificate,
    LocalCommitReceipt,
    OutcomeCertificate,
)
from pheroos.governance.commit import CommitAssessment
from pheroos.governance.distributed_commit import DistributedCommitCertificate
from pheroos.governance.evidence import EvidenceGraph, EvidenceNode
from pheroos.governance.hybrid_commit_evaluation import HybridCommitEvaluation
from pheroos.governance.layer_coordination import LayerProposal
from pheroos.governance.policy_adjustment import PolicyAdjustmentProposal
from pheroos.kernel import InputEnvelope
from pheroos.protocol.models import PheromoneKindProfile


def check(root: str | Path | None = None) -> CheckResult:
    """Prove canonical public ownership and defensive snapshot boundaries."""

    source_root = (
        Path(root).resolve()
        if root is not None
        else Path(__file__).resolve().parents[3]
    )
    problems: list[str] = []
    problems.extend(public_type_ownership_problems())
    problems.extend(registry_snapshot_problems())
    problems.extend(representative_snapshot_problems())
    problems.extend(public_inventory_problems(source_root))
    problems.extend(public_lifecycle_problems(source_root))
    return CheckResult("public_abi_boundary", not problems, ", ".join(problems))


def public_inventory_problems(root: str | Path) -> list[str]:
    try:
        expected = load_public_api_inventory(root)
    except FileNotFoundError:
        return ["inventory:artifact_missing"]
    except (OSError, ValueError) as exc:
        return [f"inventory:artifact_invalid:{type(exc).__name__}"]
    try:
        observed = build_public_api_inventory()
    except Exception as exc:  # total conformance boundary
        return [f"inventory:inspection_failed:{type(exc).__name__}"]
    return [
        f"inventory:{path}"
        for path in public_api_inventory_differences(expected, observed)
    ]


def public_lifecycle_problems(root: str | Path) -> list[str]:
    try:
        expected = load_public_api_lifecycle(root)
    except FileNotFoundError:
        return ["lifecycle:artifact_missing"]
    except (OSError, ValueError) as exc:
        return [f"lifecycle:artifact_invalid:{type(exc).__name__}"]
    try:
        structural = public_api_lifecycle_problems(expected)
    except Exception as exc:  # total conformance boundary
        return [f"lifecycle:inspection_failed:{type(exc).__name__}"]
    problems = [f"lifecycle:{item}" for item in structural]
    try:
        observed = build_public_api_lifecycle(root)
    except Exception as exc:  # total conformance boundary
        problems.append(f"lifecycle:inspection_failed:{type(exc).__name__}")
        return problems
    problems.extend(
        f"lifecycle:{path}"
        for path in public_api_lifecycle_differences(expected, observed)
    )
    return problems


def public_type_ownership_problems() -> list[str]:
    expected = (
        (
            governance.CommitAssurance,
            protocol.CommitAssurance,
            "pheroos.protocol.commit_models",
            "commit_assurance",
        ),
        (
            governance.CommitAction,
            protocol.CommitAction,
            "pheroos.protocol.commit_models",
            "commit_action",
        ),
        (
            governance.TraceEvent,
            trace.TraceEvent,
            "pheroos.trace",
            "trace_event",
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
        (
            governance.CommitAssessment,
            CommitAssessment,
            "pheroos.governance.commit",
            "commit_assessment",
        ),
        (
            governance.LocalCommitReceipt,
            LocalCommitReceipt,
            "pheroos.governance.certificate",
            "local_commit_receipt",
        ),
        (
            governance.EvidenceCommitCertificate,
            EvidenceCommitCertificate,
            "pheroos.governance.certificate",
            "evidence_commit_certificate",
        ),
        (
            governance.OutcomeCertificate,
            OutcomeCertificate,
            "pheroos.governance.certificate",
            "outcome_certificate",
        ),
        (
            governance.DistributedCommitCertificate,
            DistributedCommitCertificate,
            "pheroos.governance.distributed_commit",
            "distributed_commit_certificate",
        ),
        (
            governance.HybridCommitEvaluation,
            HybridCommitEvaluation,
            "pheroos.governance.hybrid_commit_evaluation",
            "hybrid_commit_evaluation",
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
    if kind_profile_exports:
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
    kind_profile = PheromoneKindProfile(
        scored_subject_types=profile_subjects,
        extensions=profile_extensions,
    )
    policy_profiles = {"positive": kind_profile}
    layer_bounds = {"learned": [0.0, 1.0]}
    policy = protocol.CollectiveDecisionPolicy(
        pheromone_kind_profiles=policy_profiles,
        layer_weight_bounds=cast(dict[str, tuple[float, float]], layer_bounds),
    )
    candidate_inputs = [Candidate("candidate:one", "decision:one")]
    evidence_inputs = [EvidenceNode("evidence:one", "content", "driver:one")]
    candidate_set = CandidateSet(tuple(candidate_inputs))
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
    trace_store.records[0].event.lineage["nested"]["values"].append("mutated")

    problems: list[str] = []
    if tuple(kind_profile.scored_subject_types) != ("candidate",):
        problems.append("snapshot:kind_subjects")
    if kind_profile.extensions["x-profile"]["values"] != ("original",):
        problems.append("snapshot:kind_extensions")
    if tuple(policy.pheromone_kind_profiles) != ("positive",):
        problems.append("snapshot:policy_profiles")
    if policy.layer_weight_bounds["learned"] != (0.0, 1.0):
        problems.append("snapshot:policy_bounds")
    if tuple(candidate.id for candidate in candidate_set.candidates) != (
        "candidate:one",
    ):
        problems.append("snapshot:candidates")
    if tuple(node.id for node in evidence.nodes) != ("evidence:one",):
        problems.append("snapshot:evidence")
    if envelope.metadata["nested"]["values"] != ("original",):
        problems.append("snapshot:kernel_metadata")
    if trace_store.records[0].event.lineage["nested"]["values"] != ["original"]:
        problems.append("snapshot:trace_store")
    return problems


__all__ = ["check"]
