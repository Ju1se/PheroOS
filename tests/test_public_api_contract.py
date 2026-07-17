from __future__ import annotations

from hashlib import sha256
from importlib import import_module

import pheroos.governance as governance
import pheroos.conformance as conformance
import pheroos.protocol as protocol
import pheroos.trace as trace


EXPECTED_PUBLIC_API = {
    "pheroos.protocol": (77, "96e546b5f54892c8251268b41b1214586f578826f3b44b7262547d13787005b4"),
    "pheroos.governance": (527, "c59888cc742fb0dbf2eb5bf9ab62fa216e127a897ac0d675dc4ac9002b4f3ad4"),
    "pheroos.kernel": (28, "52523a670adbde14b3bd0c3c8872095d4f08c8bc4903faa5c08a743c6f2de907"),
    "pheroos.drivers": (37, "b551bfec64fc9fd0d5dee669897edad6045a197145e3dab9deaab44478887bde"),
    "pheroos.trace": (25, "ebe198475258c7dc4719e0eb9c4c3d2eb1dd70bcc1fb64bd525a36d125668a68"),
    "pheroos.conformance": (33, "0253154cabb5bcb029f1f84be01d332e37083af0fcee6e0b989fcba7d9bb1091"),
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
