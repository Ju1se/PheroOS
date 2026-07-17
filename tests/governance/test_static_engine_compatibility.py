from __future__ import annotations

import ast
import inspect
from pathlib import Path

from pheroos.governance import certificate, commit, commit_state, hybrid_commit
from pheroos.governance._commit import assessment, common, local_receipt
from pheroos.governance._hybrid import binding


ROOT = Path(__file__).resolve().parents[2]


def test_extracted_records_preserve_exact_public_identity() -> None:
    pairs = (
        (commit.CandidateCommitMetrics, assessment.CandidateCommitMetrics),
        (commit.CommitAssessment, assessment.CommitAssessment),
        (commit.CommitAssessmentStatus, assessment.CommitAssessmentStatus),
        (commit_state.AuthorityScope, common.AuthorityScope),
        (certificate.LocalCommitReceipt, local_receipt.LocalCommitReceipt),
        (hybrid_commit.HybridCommitStep, binding.HybridCommitStep),
    )

    for public, private in pairs:
        assert public is private
        assert public.__module__.startswith("pheroos.governance.")
        assert "._" not in public.__module__
        assert inspect.signature(public) == inspect.signature(private)


def test_extracted_public_functions_preserve_owner_and_identity() -> None:
    pairs = (
        (
            commit.candidate_commit_metrics_fingerprint,
            assessment.candidate_commit_metrics_fingerprint,
        ),
        (
            commit.commit_assessment_fingerprint,
            assessment.commit_assessment_fingerprint,
        ),
        (
            commit.commit_assessment_is_authoritative,
            assessment.commit_assessment_is_authoritative,
        ),
        (
            certificate.local_commit_receipt_fingerprint,
            local_receipt.local_commit_receipt_fingerprint,
        ),
        (
            certificate.local_commit_receipt_is_authoritative,
            local_receipt.local_commit_receipt_is_authoritative,
        ),
        (
            hybrid_commit.bind_hybrid_commit_channels,
            binding.bind_hybrid_commit_channels,
        ),
        (
            hybrid_commit.hybrid_commit_step_fingerprint,
            binding.hybrid_commit_step_fingerprint,
        ),
    )

    for public, private in pairs:
        assert public is private
        assert public.__module__.startswith("pheroos.governance.")
        assert "._" not in public.__module__
        assert inspect.signature(public) == inspect.signature(private)


def test_scc_owners_contain_no_hidden_dynamic_import_path() -> None:
    paths = (
        "pheroos/governance/certificate.py",
        "pheroos/governance/commit.py",
        "pheroos/governance/commit_state.py",
        "pheroos/governance/replay.py",
        "pheroos/governance/hybrid_commit.py",
        "pheroos/governance/hybrid_commit_evaluation.py",
        "pheroos/governance/_commit/assessment.py",
        "pheroos/governance/_commit/local_receipt.py",
        "pheroos/governance/_hybrid/binding.py",
    )

    offenders: list[str] = []
    for relative in paths:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                if any(
                    name == "importlib" or name.startswith("importlib.")
                    for name in names
                ):
                    offenders.append(relative)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "__import__":
                    offenders.append(relative)

    assert offenders == []
