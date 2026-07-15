from __future__ import annotations

from hashlib import sha256
from importlib import import_module

import pheroos.governance as governance
import pheroos.conformance as conformance
import pheroos.protocol as protocol
import pheroos.trace as trace


EXPECTED_PUBLIC_API = {
    "pheroos.protocol": (64, "844b9d33022ae16dba67552541f5ebb9af23fb04a13c2c061629824e8ed6ff8c"),
    "pheroos.governance": (507, "667cc811791387860abb8a8f68cd25accc4afd233236229142362c45a2376caf"),
    "pheroos.kernel": (14, "f195fda8c36d48bb30c4fdbc6eb69ffe38db26958f60925eb5c7f9952cb500d1"),
    "pheroos.drivers": (20, "b3c27fe18c2a1a9c8ddcbbb30f8fe2ad5a8a2b32606eaedd168b690823fc0da4"),
    "pheroos.trace": (20, "dbe97b0f5d49e7d849cd13a06f2ec1eac4572678b90757ec2ebf66df8695620e"),
    "pheroos.conformance": (17, "28d225ee3f8e05586ad87a3f313d9e0c31d8f27f9b2d34555a2ef34fc53045ec"),
}


def test_public_package_exports_match_the_intentional_abi_snapshot() -> None:
    for module_name, (expected_count, expected_digest) in EXPECTED_PUBLIC_API.items():
        module = import_module(module_name)
        exported = tuple(module.__all__)

        assert len(exported) == expected_count
        assert len(exported) == len(set(exported))
        assert all(hasattr(module, name) for name in exported)
        observed = sha256("\n".join(sorted(exported)).encode()).hexdigest()
        assert observed == expected_digest, f"undeclared public ABI drift in {module_name}"


def test_canonical_public_types_are_owned_by_their_declared_surfaces() -> None:
    assert governance.CommitAssurance is protocol.CommitAssurance
    assert governance.CommitAction is protocol.CommitAction
    assert protocol.CommitAssurance.__module__ == "pheroos.protocol.commit_models"
    assert protocol.CommitAction.__module__ == "pheroos.protocol.commit_models"
    assert governance.PheromoneKindProfile is protocol.PheromoneKindProfile
    assert protocol.PheromoneKindProfile.__module__ == "pheroos.protocol.models"
    assert governance.TraceEvent is trace.TraceEvent
    assert trace.TraceEvent.__module__ == "pheroos.trace"
    assert governance.PheromoneTrail.__module__ == "pheroos.governance.pheromone"
    assert governance.LayerProposal.__module__ == "pheroos.governance.layer_coordination"
    assert governance.PolicyAdjustmentProposal.__module__ == "pheroos.governance.policy_adjustment"
    assert governance.HybridCollectiveStep.__module__ == "pheroos.governance.collective"
    assert governance.HybridReplayState.__module__ == "pheroos.governance.collective"
    assert governance.CommitAssessment.__module__ == "pheroos.governance.commit"
    assert governance.CommitWindowSeal.__module__ == "pheroos.governance.commit_state"
    assert governance.DecisionOutcome.__module__ == "pheroos.governance.commit_state"
    assert governance.LocalCommitReceipt.__module__ == "pheroos.governance.certificate"
    assert governance.EvidenceCommitCertificate.__module__ == (
        "pheroos.governance.certificate"
    )
    assert governance.OutcomeCertificate.__module__ == (
        "pheroos.governance.certificate"
    )
    assert governance.DistributedCommitCertificate.__module__ == (
        "pheroos.governance.distributed_commit"
    )
    assert governance.HybridCommitEvaluation.__module__ == (
        "pheroos.governance.hybrid_commit_evaluation"
    )
    assert governance.HybridCommitAttentionStatus.__module__ == (
        "pheroos.governance.hybrid_commit_evaluation"
    )
    assert governance.distributed_commit_value_payload.__module__ == (
        "pheroos.governance.distributed_commit"
    )
    assert governance.distributed_commit_value_root.__module__ == (
        "pheroos.governance.distributed_commit"
    )
    assert conformance.CommitTckVector.__module__ == "pheroos.conformance.commit_tck"
