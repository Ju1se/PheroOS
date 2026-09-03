from __future__ import annotations

import ast
import inspect
from pathlib import Path

from pheroos.governance import certificate, hybrid_commit
from pheroos.governance import hybrid_commit_evaluation as evaluation_facade
from pheroos.governance._certificate import (
    invariants,
    local,
    outcome,
    portable,
    records,
)
from pheroos.governance._hybrid import commit, evaluation_records, request


ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE = ROOT / "pheroos" / "governance"


def _private_edges(package: str) -> dict[str, set[str]]:
    root = GOVERNANCE / package
    prefix = f"pheroos.governance.{package}."
    graph: dict[str, set[str]] = {}
    for path in sorted(root.glob("*.py")):
        graph[path.stem] = set()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(prefix):
                    graph[path.stem].add(node.module.removeprefix(prefix))
                assert node.module not in {
                    "pheroos.governance.certificate",
                    "pheroos.governance.hybrid_commit",
                    "pheroos.governance.hybrid_commit_evaluation",
                }
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name not in {
                        "pheroos.governance.certificate",
                        "pheroos.governance.hybrid_commit",
                        "pheroos.governance.hybrid_commit_evaluation",
                    }
    return graph


def test_certificate_private_modules_have_one_way_static_ownership() -> None:
    assert _private_edges("_certificate") == {
        "__init__": set(),
        "historical": {"invariants", "records"},
        "invariants": set(),
        "local": {"invariants"},
        "outcome": {"invariants", "records"},
        "portable": {"historical", "invariants", "local", "records"},
        "records": {"invariants"},
    }


def test_hybrid_private_modules_have_one_way_static_ownership() -> None:
    assert _private_edges("_hybrid") == {
        "__init__": set(),
        "attention": {"binding", "evaluation_records", "request"},
        "binding": set(),
        "commit": {"binding", "evaluation_records", "request"},
        "evaluation_records": set(),
        "finality": {"request"},
        "output": set(),
        "pipeline": {
            "attention",
            "binding",
            "commit",
            "evaluation_records",
            "finality",
            "output",
            "preflight",
            "request",
            "trace",
        },
        "preflight": {"request"},
        "request": {"evaluation_records"},
        "trace": {"output", "request"},
    }


def test_certificate_facade_exports_type_identical_private_owners() -> None:
    pairs = (
        (certificate.EvidenceCommitCertificate, records.EvidenceCommitCertificate),
        (certificate.LocalCommitReceipt, local.LocalCommitReceipt),
        (certificate.OutcomeCertificate, records.OutcomeCertificate),
        (certificate.output_payload_fingerprint, invariants.output_payload_fingerprint),
        (certificate.issue_local_commit_receipt, local.issue_local_commit_receipt),
        (certificate.local_commit_receipt_matches, local.local_commit_receipt_matches),
        (certificate.verify_local_commit_finality, local.verify_local_commit_finality),
        (
            certificate.issue_evidence_commit_certificate,
            portable.issue_evidence_commit_certificate,
        ),
        (
            certificate.verify_evidence_commit_certificate,
            portable.verify_evidence_commit_certificate,
        ),
        (certificate.issue_outcome_certificate, outcome.issue_outcome_certificate),
        (certificate.verify_outcome_certificate, outcome.verify_outcome_certificate),
    )
    for public, private in pairs:
        assert public is private
        assert public.__module__ == "pheroos.governance.certificate"
        assert inspect.signature(public) == inspect.signature(private)


def test_hybrid_facades_export_type_identical_private_owners() -> None:
    pairs = (
        (
            evaluation_facade.HybridCommitDiagnostic,
            evaluation_records.HybridCommitDiagnostic,
        ),
        (
            evaluation_facade.HybridCommitEvaluation,
            evaluation_records.HybridCommitEvaluation,
        ),
        (
            evaluation_facade.HybridCommitEvaluationRequest,
            request.HybridCommitEvaluationRequest,
        ),
        (
            evaluation_facade.hybrid_commit_evaluation_payload,
            evaluation_records.hybrid_commit_evaluation_payload,
        ),
        (
            evaluation_facade.hybrid_commit_evaluation_is_authoritative,
            commit.hybrid_commit_evaluation_is_authoritative,
        ),
        (
            evaluation_facade.hybrid_commit_evaluation_request_payload,
            request.hybrid_commit_evaluation_request_payload,
        ),
    )
    for public, private in pairs:
        assert public is private
        assert public.__module__ == "pheroos.governance.hybrid_commit_evaluation"
        assert inspect.signature(public) == inspect.signature(private)

    assert hybrid_commit.HybridCommitEvaluation is (
        evaluation_facade.HybridCommitEvaluation
    )
    assert hybrid_commit.HybridCommitEvaluationRequest is (
        evaluation_facade.HybridCommitEvaluationRequest
    )


def test_hybrid_pipeline_contains_the_only_total_algorithm() -> None:
    pipeline_tree = ast.parse(
        (GOVERNANCE / "_hybrid" / "pipeline.py").read_text(encoding="utf-8")
    )
    engines = [
        node
        for node in pipeline_tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "evaluate_hybrid_commit_step"
    ]
    assert len(engines) == 1
    assert len(engines[0].body) > 20

    public_tree = ast.parse(
        (GOVERNANCE / "hybrid_commit.py").read_text(encoding="utf-8")
    )
    public_entry = next(
        node
        for node in public_tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "evaluate_hybrid_commit_step"
    )
    assert len(public_entry.body) == 2
    assert isinstance(public_entry.body[-1], ast.Return)


def test_certificate_and_evaluation_facades_are_thin() -> None:
    certificate_source = (GOVERNANCE / "certificate.py").read_text(encoding="utf-8")
    evaluation_source = (GOVERNANCE / "hybrid_commit_evaluation.py").read_text(
        encoding="utf-8"
    )

    assert len(certificate_source.splitlines()) < 160
    assert len(evaluation_source.splitlines()) < 140
    assert "LEGACY_AUTHORITY_REGISTRY" not in certificate_source
    assert "reduce_commit_liveness" not in evaluation_source
    assert "make_commit_trace_event" not in evaluation_source
