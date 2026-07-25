from __future__ import annotations

import pytest

from pheroos.governance import AuthorityLevel, Candidate, CandidateSet, StopResolution
from pheroos.governance._commit_terminal import select_terminal_outcome_kind
from pheroos.governance._validation import require_nonblank_string
from pheroos.governance.errors import GovernanceError
from pheroos.governance.quorum import _fallback_decision, _validate_quorum_policy
from pheroos.governance.stop_signal import verify_stop_resolution
from pheroos.protocol import QuorumPolicy
from pheroos.protocol.commit_models import CommitAssurance


def test_terminal_and_text_validators_fail_closed() -> None:
    with pytest.raises(GovernanceError, match="deadline outcome is unsupported"):
        select_terminal_outcome_kind(
            invalid=False,
            safety_violation=False,
            blocked=False,
            evidence_commit_ready=False,
            finality_unavailable=False,
            deadline_reached=False,
            deadline_outcome="unsupported",
        )
    with pytest.raises(GovernanceError, match="non-blank string"):
        require_nonblank_string(None, "value")
    assert require_nonblank_string("value", "value") == "value"


def test_quorum_rejects_noncanonical_policy_and_unsafe_fallback() -> None:
    with pytest.raises(GovernanceError, match="canonical protocol declaration"):
        _validate_quorum_policy(object())  # type: ignore[arg-type]

    candidates = CandidateSet(
        [Candidate(id="candidate:fallback", target="decision:review")]
    )
    policy = QuorumPolicy(
        target="decision:review",
        fallback_candidate="candidate:fallback",
        commit_threshold=1,
    )
    with pytest.raises(GovernanceError, match="not marked safe"):
        _fallback_decision(
            candidates,
            policy,
            stop_resolutions=None,
            fallback_candidate_id=None,
        )


def test_stop_verification_requires_a_strictly_later_expiry() -> None:
    root = "sha256:" + "1" * 64
    with pytest.raises(GovernanceError, match="expiry must be after issuance"):
        verify_stop_resolution(
            StopResolution(
                target="decision:review",
                action="publish",
                blocked=True,
                reason="blocked",
            ),
            resolution_id="resolution:one",
            profile="pheroos-certified-commit-v1",
            assurance=CommitAssurance.CERTIFIED,
            manifest_root=root,
            commit_policy_root=root,
            protocol_id="protocol:test",
            run_id="run:test",
            epoch=1,
            decision_ref="decision:test",
            certificate_ref="certificate:test",
            resolved_stop_root=root,
            verifier_id="governance:test",
            authority=AuthorityLevel.GOVERNANCE,
            issued_at_step=10,
            expires_at_step=10,
            provenance="urn:test:stop",
            trace_event_id="trace:test",
        )
