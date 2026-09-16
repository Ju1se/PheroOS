"""Bound control growth without blocking settlement or cancellation."""
from hashlib import sha256

import pytest

from pheroos_interaction.records import BudgetExceeded, StateError
from pheroos_interaction.runner.evidence import CoordinationSession
from pheroos_interaction.runner.session import _wire


BODY = {"value": 7}
ARGS = {"source_id": "x"}
FINGERPRINT = sha256(_wire(BODY).encode()).hexdigest()


def make_session(tmp_path, cap, *, clock=None, works=("read",), artifact_bytes=8192):
    readers = ["a", "b"]
    return CoordinationSession.create(
        tmp_path / "session.sqlite", "control-limits", agents=readers,
        work=[{"id": work, "version": 1, "dependencies": [],
               "agents": readers, "actions": ["tool.evaluate"]} for work in works],
        sources=[{"id": "x", "version": 1, "readers": readers,
                  "state_fingerprint": FINGERPRINT}],
        inspections=[{"work_id": work, "source_id": "x", "source_version": 1,
                      "tool_ref": "inspect", "tool_version": "v1", "arguments": ARGS,
                      "state_fingerprint": FINGERPRINT} for work in works],
        token_cap=20, max_calls=4, max_control_operations=cap,
        clock=clock, artifact_bytes=artifact_bytes)


def reserve(session, lease, call_id, *, prompt=0, maximum=0):
    session.reserve(lease, call_id, "tool.evaluate",
                    {"tool_ref": "inspect", "arguments": ARGS},
                    prompt_tokens=prompt, max_new_tokens=maximum)


def settle(session, lease, call_id="received"):
    reserve(session, lease, call_id)
    session.dispatch(lease, call_id)
    session.receive(call_id, {"artifact": BODY, "prompt_tokens": 0, "completion_tokens": 0})


def verify(work, value):
    return work == "read" and value == BODY


def test_repeated_accepted_source_updates_share_the_claim_budget(tmp_path):
    session = make_session(tmp_path, 2)
    assert len(session.snapshot()["events"]) == 2
    for _ in range(2):
        session.source_update("x", 1, ["a", "b"], FINGERPRINT)
    before = session.snapshot()
    assert len(before["events"]) == 4
    with pytest.raises(BudgetExceeded):
        session.source_update("x", 1, ["a", "b"], FINGERPRINT)
    with pytest.raises(BudgetExceeded):
        session.claim("a", "read")
    assert session.snapshot() == before


def test_claim_and_source_update_budget_persists_after_reopen(tmp_path):
    session = make_session(tmp_path, 2, works=("read", "second"))
    session.claim("a", "read")
    session.source_update("x", 1, ["a", "b"], FINGERPRINT)
    before = session.snapshot()
    reopened = CoordinationSession(session.path)
    with pytest.raises(BudgetExceeded):
        reopened.claim("b", "second")
    with pytest.raises(BudgetExceeded):
        reopened.source_update("x", 2, ["b"], "new-content")
    assert reopened.snapshot() == before


def test_reads_invalid_operations_and_unmatched_claims_have_no_effect_at_cap(tmp_path):
    session = make_session(tmp_path, 1)
    lease = session.claim("a", "read")
    before = session.snapshot()
    assert session.claim("b", "read") is None
    assert session.claim("a", "missing") is None
    assert session.artifacts("a") == []
    assert session.read_artifact("b", "sha256:missing") is None
    session.check_current(lease)
    session.recover()
    with pytest.raises(StateError):
        session.claim("outsider")
    with pytest.raises(StateError):
        session.source_update("missing", 1, ["a"], FINGERPRINT)
    with pytest.raises(StateError):
        session.source_update("x", 1, ["a", "b"], "unversioned-change")
    with pytest.raises(ValueError):
        session.source_update("x", 0, ["a", "b"], FINGERPRINT)
    with pytest.raises(PermissionError):
        session.artifacts("outsider")
    assert session.snapshot() == before


def test_exhausted_source_update_rolls_back_version_access_and_abandonment(tmp_path):
    session = make_session(tmp_path, 1)
    lease = session.claim("a", "read")
    reserve(session, lease, "pending")
    before = session.snapshot()
    with pytest.raises(BudgetExceeded):
        session.source_update("x", 2, ["b"], "new-content")
    assert session.snapshot() == before
    session.check_current(lease)
    session.dispatch(lease, "pending")
    session.receive("pending", {"artifact": BODY, "prompt_tokens": 0, "completion_tokens": 0})
    ref = session.publish(lease, "pending", BODY, verify=verify)
    assert session.read_artifact("a", ref) == BODY


def test_expiry_reclaim_loop_stops_and_explicit_recovery_remains_available(tmp_path):
    now = [100.]
    session = make_session(tmp_path, 2, clock=lambda: now[0])
    session.claim("a", "read", lease_seconds=1)
    now[0] = 102.
    session.recover()
    second = session.claim("b", "read", lease_seconds=1)
    assert second.epoch == 2
    now[0] = 104.
    before = session.snapshot()
    with pytest.raises(BudgetExceeded):
        session.claim("a", "read")
    assert session.snapshot() == before  # Implicit recovery rolls back with the failed claim.
    session.recover()
    recovered = session.snapshot()
    assert recovered["work"][0]["status"] == "ready"
    assert len(recovered["events"]) == 6
    for _ in range(3):
        session.recover()
        with pytest.raises(BudgetExceeded):
            session.claim("a", "read")
    assert session.snapshot() == recovered


def test_unknown_call_still_reconciles_after_expiry_at_control_cap(tmp_path):
    now = [100.]
    session = make_session(tmp_path, 1, clock=lambda: now[0])
    lease = session.claim("a", "read", lease_seconds=1)
    reserve(session, lease, "unknown", prompt=3, maximum=4)
    session.dispatch(lease, "unknown")
    now[0] = 102.
    session.recover()
    assert session.claim("a", "read") is None
    before = session.snapshot()
    assert before["unknown_tokens"] == 7
    with pytest.raises(StateError):
        session.publish_received("a", "unknown", verify=verify)
    assert session.snapshot() == before
    session.receive("unknown", {"artifact": BODY, "prompt_tokens": 3, "completion_tokens": 1})
    after = session.snapshot()
    assert after["unknown_calls"] == after["unknown_tokens"] == 0
    assert after["actual_tokens"] == 4
    assert after["work"][0]["status"] == "ready"
    with pytest.raises(BudgetExceeded):
        session.claim("a", "read")
    assert session.snapshot() == after


@pytest.mark.parametrize("oversized", [False, True])
def test_cancellation_and_late_settlement_remain_available_at_cap(tmp_path, oversized):
    session = make_session(tmp_path, 1, artifact_bytes=128)
    lease = session.claim("a", "read")
    reserve(session, lease, "unused", prompt=2, maximum=3)
    reserve(session, lease, "late", prompt=3, maximum=4)
    session.dispatch(lease, "late")
    session.cancel()
    cancelled = session.snapshot()
    assert session.call("unused")["state"] == "abandoned"
    assert cancelled["reserved_tokens"] == 0 and cancelled["unknown_tokens"] == 7
    reply = {"artifact": {"large": "x" * 256} if oversized else BODY,
             "prompt_tokens": 3, "completion_tokens": 1}
    if oversized:
        with pytest.raises(StateError, match="response rejected"):
            session.receive("late", reply)
    else:
        session.receive("late", reply)
    settled = session.snapshot()
    assert settled["actual_tokens"] == 4 and settled["unknown_tokens"] == 0
    assert session.call("late")["state"] == ("response_rejected" if oversized else "received")
    session.cancel()
    if oversized:
        with pytest.raises(StateError, match="response rejected"):
            session.receive("late", reply)
    else:
        session.receive("late", reply)
    assert session.claim("a", "read") is None
    assert session.snapshot() == settled


def test_active_and_idempotent_publication_do_not_need_another_control_slot(tmp_path):
    session = make_session(tmp_path, 1)
    lease = session.claim("a", "read")
    settle(session, lease)
    ref = session.publish_received("a", "received", verify=verify)
    before = session.snapshot()
    assert before["run"]["status"] == "completed"
    assert before["work"][0]["epoch"] == 1

    def must_not_verify(*args):
        raise AssertionError("already published receipt must not be verified again")

    assert session.publish_received("b", "received", verify=must_not_verify) == ref
    assert session.read_artifact("b", ref) == BODY
    with pytest.raises(BudgetExceeded):
        session.source_update("x", 1, ["a", "b"], FINGERPRINT)
    assert session.snapshot() == before


@pytest.mark.parametrize("cap", [1, 2])
def test_publication_reclaim_requires_one_remaining_control_slot(tmp_path, cap):
    now = [100.]
    session = make_session(tmp_path, cap, clock=lambda: now[0])
    lease = session.claim("a", "read", lease_seconds=1)
    settle(session, lease)
    now[0] = 102.
    before = session.snapshot()
    if cap == 1:
        with pytest.raises(BudgetExceeded):
            session.publish_received("b", "received", verify=verify)
        assert session.snapshot() == before
    else:
        ref = session.publish_received("b", "received", verify=verify)
        after = session.snapshot()
        assert after["calls"] == before["calls"]
        assert after["work"][0]["epoch"] == 2
        assert session.read_artifact("a", ref) == BODY
        with pytest.raises(BudgetExceeded):
            session.source_update("x", 1, ["a", "b"], FINGERPRINT)
        assert session.snapshot() == after


def test_failed_reclaimed_publication_does_not_spend_the_last_control_slot(tmp_path):
    now = [100.]
    session = make_session(tmp_path, 2, clock=lambda: now[0])
    lease = session.claim("a", "read", lease_seconds=1)
    settle(session, lease)
    reserve(session, lease, "unused", maximum=5)
    now[0] = 102.
    before = session.snapshot()
    verified = []
    with pytest.raises(StateError):
        session.publish_received("b", "received",
                                 verify=lambda *args: verified.append(args) or False)
    assert len(verified) == 1
    assert session.snapshot() == before
    ref = session.publish_received("b", "received", verify=verify)
    after = session.snapshot()
    assert after["work"][0]["epoch"] == 2
    assert session.call("unused")["state"] == "abandoned"
    assert after["reserved_tokens"] == 0
    assert session.read_artifact("a", ref) == BODY
    with pytest.raises(BudgetExceeded):
        session.source_update("x", 1, ["a", "b"], FINGERPRINT)
    assert session.snapshot() == after
