from __future__ import annotations

from hashlib import sha256
from importlib import import_module
from pathlib import Path
import subprocess
import sys

import pheroos.governance as governance
import pheroos.conformance as conformance
import pheroos.protocol as protocol
import pheroos.trace as trace


EXPECTED_PUBLIC_API = {
    "pheroos.protocol": (
        89,
        "6ae86e1295fe5fbde7101cbbe735e7dba0df6d54bf887b3bb7629ff0388fab57",
    ),
    "pheroos.governance": (
        911,
        "f5a405d147f99a7ee7148776cac8220ad09fda24f8e10f9bc1e412263160a919",
    ),
    "pheroos.kernel": (
        31,
        "54505137a3a46f76e0268f760996df7ed2f296abaaf99644c98b0be1ca547be3",
    ),
    "pheroos.drivers": (
        48,
        "153545c0217d2d1ab1b13cf9a8ed8437817fcf50b2cdefab2c73ec9cc31ad1bb",
    ),
    "pheroos.trace": (
        35,
        "a5f9e202ac1296e5d73fe2064b4d1a66555d424988c29eb7fd5b0ebc44ec303b",
    ),
    "pheroos.conformance": (
        118,
        "95d24961d4a00badc9fba7a452532bd2af2f45c85af269267b5d2a3165b0c20b",
    ),
}

ROOT = Path(__file__).resolve().parents[1]


def test_public_package_exports_match_the_intentional_abi_snapshot() -> None:
    for module_name, (expected_count, expected_digest) in EXPECTED_PUBLIC_API.items():
        module = import_module(module_name)
        exported = tuple(module.__all__)

        assert len(exported) == expected_count
        assert len(exported) == len(set(exported))
        assert all(hasattr(module, name) for name in exported)
        observed = sha256("\n".join(sorted(exported)).encode()).hexdigest()
        assert observed == expected_digest, (
            f"undeclared public ABI drift in {module_name}"
        )


def test_conformance_compatibility_module_uses_the_lazy_facade_branch() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import importlib; import pheroos.conformance as facade; "
                "assert 'runner' not in facade.__dict__; "
                "assert facade.runner is "
                "importlib.import_module('pheroos.conformance.runner')"
            ),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_canonical_public_types_are_owned_by_their_declared_surfaces() -> None:
    assert governance.AuthorityDiagnosticCodeV2 is (protocol.AuthorityDiagnosticCodeV2)
    assert governance.GovernanceAuthorityReadSetV2 is (
        protocol.GovernanceAuthorityReadSetV2
    )
    assert protocol.AuthorityDiagnosticCodeV2.__module__ == (
        "pheroos.protocol.authority_v2"
    )
    assert governance.AuthorityDomainV2.__module__ == (
        "pheroos.governance.authority_store_v2"
    )
    assert governance.GovernanceIssuerGrantV2.__module__ == (
        "pheroos.governance.authority_session_v2"
    )
    assert governance.GovernanceIssuerCapabilityV2.__module__ == (
        "pheroos.governance.authority_session_v2"
    )
    assert governance.GovernanceAuthoritySessionV2.__module__ == (
        "pheroos.governance.authority_session_v2"
    )
    assert governance.commit_verified_signal_v2.__module__ == (
        "pheroos.governance.authority_session_v2"
    )
    assert conformance.GovernanceStateStoreConformanceAdapterV2.__module__ == (
        "pheroos.conformance"
    )
    assert conformance.run_governance_authority_session_conformance_v2.__module__ == (
        "pheroos.conformance"
    )
    assert conformance.run_governance_baseline_output_conformance_v2.__module__ == (
        "pheroos.conformance"
    )
    assert governance.CommitAssurance is protocol.CommitAssurance
    assert governance.CommitAction is protocol.CommitAction
    assert protocol.CommitAssurance.__module__ == "pheroos.protocol.commit_models"
    assert protocol.CommitAction.__module__ == "pheroos.protocol.commit_models"
    assert governance.TraceEvent is trace.TraceEvent
    assert trace.TraceEvent.__module__ == "pheroos.trace"
    assert (
        governance.LayerProposal.__module__ == "pheroos.governance.layer_coordination"
    )
    assert (
        governance.PolicyAdjustmentProposal.__module__
        == "pheroos.governance.policy_adjustment"
    )
    assert governance.CommitAssessment.__module__ == "pheroos.governance.commit"
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
