from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / "docs/protocol/support-v2.md"


def test_support_v2_document_freezes_complete_authority_chain() -> None:
    text = DOCUMENT.read_text(encoding="utf-8")
    for required in (
        "Status: Draft ABI",
        "PrincipalVerificationSet v2",
        "Membership v2",
        "Support v2",
        "Portable records, snapshots, requests, evaluations, roots",
        "Verified*SourceV2",
        "Verified*StateV2",
        "QUALIFY_EVIDENCE",
        "EVALUATE_QUORUM",
        "complete replacement set",
        "Store-current",
        "initialize",
        "issue",
        "revoke",
        "switch",
        "RETRY_REQUIRED/GOVERNANCE_READ_SET_STALE",
        "principal_verification_set_advanced",
        "membership_epoch_committed",
        "support_state_advanced",
        "support_lease_issued_v2",
        "support_lease_revoked_v2",
        "GOVERNANCE_DOMAIN_SEALED",
        "32-worker identical",
        "imports no private Governance owner",
        "exposes no v1-to-v2 authority projection",
    ):
        assert required in text


def test_support_v2_facade_has_no_legacy_owner_dependency() -> None:
    source = (ROOT / "pheroos/governance/support_v2.py").read_text(encoding="utf-8")
    assert "pheroos.governance.support import" not in source
    assert "pheroos.governance._support." not in source
    assert "LEGACY_AUTHORITY_REGISTRY" not in source
