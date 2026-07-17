from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pheroos.governance._legacy.authority_registry import LegacyAuthorityRegistry


ROOT = Path(__file__).resolve().parents[2]
MIGRATED_MODULES = (
    "commit.py",
    "commit_state.py",
    "risk.py",
    "support_lease.py",
    "certificate.py",
    "distributed_commit.py",
)


def test_legacy_identity_state_has_one_quarantined_owner() -> None:
    forbidden_names = {
        "_COMMIT_CONTEXT_AUTHORITIES",
        "_COMMIT_CONTEXT_CLAIM_AUTHORITIES",
        "_COMMIT_WINDOW_CURSORS",
        "_COMMIT_REPLAY_CURSORS",
        "_RISK_CHAIN_CURSORS",
        "_MEMBERSHIP_EPOCH_CURSORS",
        "_SUPPORT_REPLAY_CURSORS",
        "_DISTRIBUTED_STATE_CURSORS",
        "_WITNESS_VERIFICATIONS_BY_ID",
        "_WITNESS_VERIFICATIONS_BY_NONCE",
        "_PROPOSALS_BY_ID",
        "_DISTRIBUTED_CERTIFICATES_BY_ID",
        "_EPOCH_CERTIFICATES_BY_ID",
        "_CERTIFICATE_ID_AUTHORITIES",
    }
    for filename in MIGRATED_MODULES:
        path = ROOT / "pheroos/governance" / filename
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assigned = {
            target.id
            for node in tree.body
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (
                node.targets if isinstance(node, ast.Assign) else (node.target,)
            )
            if isinstance(target, ast.Name)
        }
        assert forbidden_names.isdisjoint(assigned), filename


def test_new_durable_authority_path_does_not_import_legacy_adapter() -> None:
    for relative in (
        "pheroos/governance/authority_domain.py",
        "pheroos/governance/_authority/ledger.py",
        "pheroos/governance/atomic_evaluation.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "pheroos.governance._legacy" not in source
        assert "LEGACY_AUTHORITY_REGISTRY" not in source


def test_frozen_blended_selector_cannot_acquire_modern_authority_surfaces() -> None:
    path = ROOT / "pheroos/governance/_legacy/hybrid_v1.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert imported <= {
        "__future__",
        "collections.abc",
        "pheroos.governance.candidate",
        "pheroos.governance.errors",
        "pheroos.governance.runtime_policy",
        "pheroos.protocol.models",
    }
    assert all(
        forbidden not in path.read_text(encoding="utf-8")
        for forbidden in (
            "GovernanceStateStore",
            "AtomicHybridCommitResult",
            "CommitCertificate",
            "OutputAuthorization",
            "TraceEvent",
        )
    )


def test_private_legacy_adapter_serializes_claim_installation() -> None:
    registry = LegacyAuthorityRegistry()

    def install(index: int) -> object:
        with registry.transaction() as transaction:
            existing = transaction.get("legacy.test.claims", "claim")
            if existing is not None:
                return existing
            value = ("canonical", index)
            transaction.set("legacy.test.claims", "claim", value)
            return value

    with ThreadPoolExecutor(max_workers=32) as pool:
        observed = tuple(pool.map(install, range(64)))

    assert len(set(observed)) == 1
    assert registry.cardinalities() == {"legacy.test.claims": 1}
    assert registry.total_record_count() == 1


def test_private_legacy_adapter_cardinality_is_observable_and_resettable() -> None:
    registry = LegacyAuthorityRegistry()
    with registry.transaction() as transaction:
        transaction.set("legacy.test.first", "a", object())
        transaction.set("legacy.test.first", "b", object())
        transaction.set("legacy.test.second", "c", object())

    assert registry.cardinalities() == {
        "legacy.test.first": 2,
        "legacy.test.second": 1,
    }
    assert registry.total_record_count() == 3

    registry.clear_for_conformance()

    assert registry.cardinalities() == {}
    assert registry.total_record_count() == 0
