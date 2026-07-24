from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / "docs/protocol/commit-state-v2.md"


def test_commit_replay_v2_document_freezes_authority_and_legacy_boundaries() -> None:
    text = DOCUMENT.read_text(encoding="utf-8")

    for required in (
        "Status: public Draft ABI",
        "does **not** verify the upstream evidence",
        "explicit zero-receipt genesis transition is valid",
        "a non-genesis transition must add at least one new receipt",
        "replay, issuer-grant, and domain-lifecycle heads",
        "commit_replay_advanced",
        "32-way exact-request",
        "8 MiB snapshot bounds",
        "does not use Conformance\nadapter tamper/observation hooks",
        "does not copy an application evaluator",
        "Legacy-exit status",
        "dependency-leaf module shared by the\nv1 compatibility owner and v2",
        "v1 issuance-token\ndependency have been removed",
        "does not make the full Commit authority production-complete",
    ):
        assert required in text


def test_commit_replay_v2_owner_has_no_legacy_commit_dependency() -> None:
    owner = ROOT / "pheroos/governance/_commit_state_v2"
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(owner.glob("*.py"))
    )

    assert "pheroos.governance._commit_state." not in source
    assert "pheroos.governance._commit_state import" not in source
    assert "_COMMIT_REPLAY_STATE_ISSUANCE" not in source
    assert "LEGACY_AUTHORITY_REGISTRY" not in source
