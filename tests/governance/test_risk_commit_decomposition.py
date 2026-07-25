from __future__ import annotations

import ast
import inspect
from pathlib import Path

from pheroos.governance import commit, risk
from pheroos.governance._commit import (
    assessment,
    context,
    evaluation,
    records as commit_records,
    replay,
)
from pheroos.governance._risk import (
    chain,
    invariants as risk_invariants,
    payloads as risk_payloads,
    records as risk_records,
    thresholds,
)


ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE = ROOT / "pheroos" / "governance"


def _private_edges(package: str) -> dict[str, set[str]]:
    root = GOVERNANCE / package
    prefix = f"pheroos.governance.{package}."
    public_facade = f"pheroos.governance.{package.removeprefix('_')}"
    graph: dict[str, set[str]] = {}
    for path in sorted(root.glob("*.py")):
        graph[path.stem] = set()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(prefix):
                    graph[path.stem].add(node.module.removeprefix(prefix))
                assert node.module != public_facade
            elif isinstance(node, ast.Import):
                assert all(alias.name != public_facade for alias in node.names)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "__import__"
    return graph


def test_risk_private_modules_form_the_declared_static_dag() -> None:
    assert _private_edges("_risk") == {
        "__init__": set(),
        "chain": {"invariants", "payloads", "records"},
        "invariants": set(),
        "payloads": {"records"},
        "records": set(),
        "thresholds": {"chain", "invariants", "payloads", "records"},
    }


def test_commit_private_modules_form_the_declared_static_dag() -> None:
    assert _private_edges("_commit") == {
        "__init__": set(),
        "assessment": set(),
        "certificate_contracts": set(),
        "common": set(),
        "context": {"invariants", "records"},
        "evaluation": {
            "assessment",
            "evaluation_engine",
            "records",
        },
        "evaluation_engine": {
            "assessment",
            "context",
            "evaluation_metrics",
            "invariants",
            "records",
            "replay",
        },
        "evaluation_metrics": {
            "assessment",
            "context",
            "invariants",
            "records",
        },
        "invariants": {"records"},
        "local_receipt": {"certificate_contracts", "common"},
        "records": set(),
        "replay": {"records"},
    }


def test_risk_facade_exports_type_identical_private_owners() -> None:
    owners = {
        "CommitThresholdSnapshot": risk_records,
        "RiskAssessment": risk_records,
        "RiskAssessmentChainState": risk_records,
        "RiskBand": risk_records,
        "commit_threshold_snapshot_fingerprint": risk_payloads,
        "commit_threshold_snapshot_is_authoritative": thresholds,
        "commit_threshold_snapshot_matches": thresholds,
        "commit_threshold_snapshot_payload": risk_payloads,
        "commit_threshold_transition_requires_reset": thresholds,
        "initialize_risk_assessment_chain": chain,
        "issue_commit_threshold_snapshot": thresholds,
        "issue_risk_assessment": chain,
        "risk_assessment_chain_state_fingerprint": risk_payloads,
        "risk_assessment_chain_state_is_authoritative": chain,
        "risk_assessment_chain_state_is_current": chain,
        "risk_assessment_chain_state_payload": risk_payloads,
        "risk_assessment_fingerprint": risk_payloads,
        "risk_assessment_is_authoritative": chain,
        "risk_assessment_is_latest": chain,
        "risk_assessment_matches": chain,
        "risk_assessment_payload": risk_payloads,
        "risk_policy_root": risk_invariants,
        "risk_transition_is_monotonic": thresholds,
    }
    assert set(owners) == set(risk.__all__)
    for name, owner in owners.items():
        public = getattr(risk, name)
        private = getattr(owner, name)
        assert public is private
        assert public.__module__ == "pheroos.governance.risk"
        assert inspect.signature(public) == inspect.signature(private)


def test_commit_facade_exports_type_identical_private_owners() -> None:
    owners = {
        "CandidateClaimBinding": commit_records,
        "CandidateCommitInput": commit_records,
        "CandidateCommitMetrics": assessment,
        "CommitAssessment": assessment,
        "CommitAssessmentStatus": assessment,
        "CommitEvaluationContext": commit_records,
        "CommitEvaluationError": commit_records,
        "CommitEvaluationFailureKind": commit_records,
        "CommitReasonCode": commit_records,
        "assess_optimal_commit": evaluation,
        "build_commit_replay_receipts": replay,
        "candidate_commit_metrics_fingerprint": assessment,
        "candidate_commit_metrics_payload": assessment,
        "commit_assessment_fingerprint": assessment,
        "commit_assessment_is_authoritative": assessment,
        "commit_assessment_payload": assessment,
        "commit_evaluation_context_fingerprint": context,
        "commit_evaluation_context_is_authoritative": context,
        "commit_evaluation_context_payload": context,
        "issue_commit_evaluation_context": context,
        "rebuild_commit_assessment_roots": assessment,
    }
    assert set(owners) == set(commit.__all__)
    for name, owner in owners.items():
        public = getattr(commit, name)
        private = getattr(owner, name)
        assert public is private
        assert public.__module__ == "pheroos.governance.commit"
        assert inspect.signature(public) == inspect.signature(private)


def test_risk_and_commit_algorithms_have_one_source_owner() -> None:
    expected = {
        "assess_optimal_commit": "_commit/evaluation.py",
        "build_commit_replay_receipts": "_commit/replay.py",
        "initialize_risk_assessment_chain": "_risk/chain.py",
        "issue_commit_evaluation_context": "_commit/context.py",
        "issue_commit_threshold_snapshot": "_risk/thresholds.py",
        "issue_risk_assessment": "_risk/chain.py",
    }
    paths = (
        GOVERNANCE / "commit.py",
        GOVERNANCE / "risk.py",
        *sorted((GOVERNANCE / "_commit").glob("*.py")),
        *sorted((GOVERNANCE / "_risk").glob("*.py")),
    )
    owners: dict[str, list[str]] = {name: [] for name in expected}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in owners:
                    owners[node.name].append(str(path.relative_to(GOVERNANCE)))
    assert owners == {name: [owner] for name, owner in expected.items()}


def test_risk_and_commit_public_facades_remain_thin() -> None:
    risk_source = (GOVERNANCE / "risk.py").read_text(encoding="utf-8")
    commit_source = (GOVERNANCE / "commit.py").read_text(encoding="utf-8")
    assert len(risk_source.splitlines()) < 110
    assert len(commit_source.splitlines()) < 100
    assert "LEGACY_AUTHORITY_REGISTRY" not in risk_source
    assert "LEGACY_AUTHORITY_REGISTRY" not in commit_source
    assert "@dataclass" not in risk_source
    assert "@dataclass" not in commit_source
