from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs" / "protocol" / "commit-certificate-v2.md"
EXAMPLE = ROOT / "examples" / "commit-certificate-v2-protocol" / "README.md"


def test_commit_certificate_v2_document_declares_the_complete_owner_contract() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    assert text.startswith("# Commit Certificate v2 Draft ABI\n")
    for section in (
        "## Fixed authority stream",
        "## Portable certificate",
        "## Decision and seal lineage",
        "## Closed authority-leaf set",
        "## Atomic issuance",
        "## Retry, restart, and history",
        "## Semantic retry and conflicts",
        "## Finality adapter",
        "## Trace",
        "## Conformance and activation status",
        "## Failure model",
    ):
        assert text.count(section) == 1
    for binding in ("scope_ref", "protocol_ref", "run_ref", "target_ref"):
        assert binding in text
    for leaf in (
        "Replay",
        "Risk",
        "Membership",
        "Principal Verification",
        "Evidence",
        "Support",
        "Stop",
        "Permission",
    ):
        assert leaf in text
    assert "exactly twelve streams" in text
    assert "actual historical `SEALED` transition" in text
    assert "VerifiedCommitFinalityInputV2" in text
    assert "Decision + Certificate + Distributed activation gate" in text


def test_portable_example_does_not_claim_durable_owner_conformance() -> None:
    text = EXAMPLE.read_text(encoding="utf-8")
    assert "portable-verification examples" in text
    assert "does not claim durable StateStore-owner portability" in text
    assert "model provider" in text
    assert "API key" in text
