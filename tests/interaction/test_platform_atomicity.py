"""Independent regression checks for composite platform transaction boundaries."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from pheroos_interaction.records import BudgetExceeded, LeaseLost, StateError
from pheroos_interaction.runner.evidence import CoordinationSession
from pheroos_interaction.runner.platform import PlatformMixin, PlatformSession


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class ScopedPlatform(PlatformMixin, CoordinationSession):
    pass


def work(key, *, dependencies=(), agents=("a", "b")):
    return {"id": key, "version": 1, "dependencies": list(dependencies),
            "agents": list(agents), "actions": ["tool.evaluate"]}


def make(tmp_path, *, cls=PlatformSession, items=None, clock=None, platform=None,
         **extra):
    return cls.create(
        tmp_path / "session.sqlite", "platform-atomicity", agents=["a", "b"],
        work=items or [work("w")], token_cap=100, max_calls=10, clock=clock,
        platform=platform or {}, **extra)


def settle(session, lease, call_id="receipt", *, tool="inspect", arguments=None):
    session.reserve(lease, call_id, "tool.evaluate",
                    {"tool_ref": tool, "arguments": arguments or {}},
                    prompt_tokens=0, max_new_tokens=0)
    session.dispatch(lease, call_id)
    session.receive(call_id, {"artifact": {"value": 7},
                              "prompt_tokens": 0, "completion_tokens": 0})


def verify(_work, value):
    return value == {"value": 7}


def scope_options():
    return {"sources": [{"id": "source", "version": 1, "readers": ["a"],
                          "state_fingerprint": "fingerprint-1"}],
            "inspections": [{"work_id": "w", "source_id": "source",
                             "source_version": 1, "tool_ref": "inspect",
                             "tool_version": "tool-v1", "arguments": {"source_id": "source"},
                             "state_fingerprint": "fingerprint-1", "readers": ["a"]}]}


@pytest.mark.parametrize("failure_event", ["published", "platform.committed"])
def test_composite_commit_failure_rolls_back_publication_and_decision(tmp_path, failure_event):
    class CrashSession(PlatformSession):
        def _event(self, db, kind, task, payload):
            super()._event(db, kind, task, payload)
            if kind == failure_event:
                raise RuntimeError("simulated process boundary failure")

    session = make(tmp_path, cls=CrashSession)
    lease = session.claim("a", "w")
    settle(session, lease)
    session.propose(lease, "receipt", 0.1)
    before = session.snapshot()
    with pytest.raises(RuntimeError, match="simulated"):
        session.commit("w", verify=verify, abstain_loss=1)
    reopened = PlatformSession(session.path)
    assert reopened.snapshot() == before
    assert reopened.snapshot()["artifacts"] == []
    assert reopened.snapshot()["platform"]["decisions"] == []
    result = reopened.commit("w", verify=verify, abstain_loss=1)
    assert result["decision"] == "publish"
    assert reopened.snapshot()["call_count"] == 1


def test_failed_reclaimed_commit_restores_expiry_reservations_and_control_slots(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock=clock, platform={"max_platform_operations": 4})
    lease = session.claim("a", "w", lease_seconds=1)
    settle(session, lease)
    session.propose(lease, "receipt", 0.1)
    session.reserve(lease, "unused", "tool.evaluate", {}, prompt_tokens=0, max_new_tokens=5)
    clock.now += 2
    before = session.snapshot()
    with pytest.raises(StateError, match="verification"):
        session.commit("w", verify=lambda *_: False, abstain_loss=1)
    assert session.snapshot() == before
    assert session.call("unused")["state"] == "reserved"
    result = session.commit("w", verify=verify, abstain_loss=1)
    assert result["decision"] == "publish"
    assert session.call("unused")["state"] == "abandoned"
    assert session.snapshot()["work"][0]["epoch"] == lease.epoch + 1


def test_platform_metadata_survives_independent_reopen_and_receipt_replay(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock=clock, items=[work("w"), work("other")])
    lease = session.claim("a", "w")
    settle(session, lease)
    proposal = session.propose(lease, "receipt", 0.1)
    session.mark_no_entry("other", clock.now + 20, "host scheduling hold")
    result = session.commit("w", verify=verify, abstain_loss=1)
    before = session.snapshot()
    reopened = PlatformSession(session.path, clock=clock)
    assert reopened.snapshot() == before
    assert reopened.candidates("w", "a") == [proposal]
    assert reopened.call("receipt")["response"] == {"artifact": {"value": 7},
        "prompt_tokens": 0, "completion_tokens": 0}
    assert reopened.commit("w", verify=lambda *_: pytest.fail("repeat reverified"),
                           abstain_loss=1) == result
    assert reopened.snapshot() == before
    assert set(before["platform"]) == {"limits", "work", "candidates", "no_entry", "decisions"}


def test_atomic_work_budget_admits_only_one_concurrent_reservation(tmp_path):
    session = make(tmp_path, platform={"budgets": {"w": {"calls": 1, "tokens": 5}}})
    lease = session.claim("a", "w")
    barrier = Barrier(2)

    def reserve(index):
        contender = PlatformSession(session.path)
        barrier.wait(timeout=5)
        try:
            contender.reserve(lease, f"call-{index}", "tool.evaluate", {},
                              prompt_tokens=1, max_new_tokens=4)
        except BudgetExceeded:
            return "refused"
        return "reserved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, range(2)))
    assert sorted(outcomes) == ["refused", "reserved"]
    snapshot = PlatformSession(session.path).snapshot()
    assert snapshot["call_count"] == 1
    assert snapshot["reserved_tokens"] == 5
    assert [row["state"] for row in snapshot["calls"]] == ["reserved"]


def test_existing_work_cycle_refused_without_transferring_caps(tmp_path):
    session = make(tmp_path, items=[work("w"), work("waiting", dependencies=["w"])])
    lease = session.claim("a", "w")
    before = session.snapshot()
    with pytest.raises(ValueError, match="cyclic"):
        session.decompose(lease, [{**work("child", dependencies=["waiting"]),
                                   "budget": {"calls": 1, "tokens": 10}}])
    assert session.snapshot() == before


def test_scoped_enumeration_and_candidates_hide_private_source_work(tmp_path):
    session = make(tmp_path, cls=ScopedPlatform, **scope_options())
    assert session.ready_work("b") == []
    assert session.claim("b", "w") is None
    lease = session.claim("a", "w")
    settle(session, lease, arguments={"source_id": "source"})
    session.propose(lease, "receipt", 0.1)
    assert len(session.candidates("w", "a")) == 1
    with pytest.raises(PermissionError):
        session.candidates("w", "b")
    before = session.snapshot()
    with pytest.raises(PermissionError):
        session.decompose(lease, [{**work("child", agents=["b"]),
                                   "budget": {"calls": 1, "tokens": 0}}])
    assert session.snapshot() == before


def test_scoped_child_inherits_tool_arguments_readers_and_source_update_fences(tmp_path):
    session = make(tmp_path, cls=ScopedPlatform, **scope_options())
    parent = session.claim("a", "w")
    session.decompose(parent, [{**work("child", agents=["a"]),
                               "budget": {"calls": 3, "tokens": 10}}])
    assert session.ready_work("b") == []
    assert [row["id"] for row in session.ready_work("a")] == ["child"]
    lease = session.claim("a", "child")
    session.reserve(lease, "wrong-tool", "tool.evaluate", {"tool_ref": "other", "arguments": {}},
                    prompt_tokens=0, max_new_tokens=0)
    before = session.snapshot()
    with pytest.raises(StateError, match="declaration"):
        session.dispatch(lease, "wrong-tool")
    assert session.snapshot() == before
    session.release(lease)
    lease = session.claim("a", "child")
    settle(session, lease, arguments={"source_id": "source"})
    session.propose(lease, "receipt", 0.1)
    session.source_update("source", 2, ["a"], "fingerprint-2")
    assert session.ready_work("a") == []
    assert session.claim("a", "child") is None
    with pytest.raises(LeaseLost):
        session.candidates("child", "a")
    with pytest.raises(LeaseLost):
        session.commit("child", "a", verify=verify, abstain_loss=1)
    with pytest.raises(LeaseLost):
        session.publish_received("a", "receipt", verify=verify)
    assert {r["status"] for r in session.snapshot()["work"]} == {"superseded"}


def test_committed_scoped_decision_rechecks_current_readers(tmp_path):
    session = make(tmp_path, cls=ScopedPlatform, **scope_options())
    lease = session.claim("a", "w")
    settle(session, lease, arguments={"source_id": "source"})
    session.propose(lease, "receipt", 0.1)
    session.commit("w", verify=verify, abstain_loss=1)
    session.source_update("source", 1, [], "fingerprint-1")
    before = session.snapshot()
    with pytest.raises(PermissionError):
        session.commit("w", verify=lambda *_: pytest.fail("repeat reverified"), abstain_loss=1)
    with pytest.raises(PermissionError):
        session.candidates("w", "a")
    assert session.snapshot() == before


def test_renew_no_entry_and_claim_share_bound_but_release_drains(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock=clock, platform={"max_platform_operations": 3})
    lease = session.claim("a", "w", lease_seconds=100)
    before = session.snapshot()
    assert session.renew(lease, 1) == 1100
    assert session.snapshot() == before  # Shorter renewal is a true no-op.
    assert session.renew(lease, 120) == 1120
    session.mark_no_entry("w", 900, "expired mark")
    at_cap = session.snapshot()
    session.mark_no_entry("w", 900, "expired mark")
    assert session.snapshot() == at_cap
    for mutation in (lambda: session.renew(lease, 150),
                     lambda: session.mark_no_entry("w", 1200, "new mark")):
        with pytest.raises(BudgetExceeded):
            mutation()
        assert session.snapshot() == at_cap
    assert session.release(lease) == "ready"
    drained = session.snapshot()
    with pytest.raises(BudgetExceeded):
        session.claim("b", "w")
    assert session.snapshot() == drained
    session.cancel()
    cancelled = session.snapshot()
    with pytest.raises(StateError):
        session.mark_no_entry("w", 1300, "post-cancel mutation")
    assert session.snapshot() == cancelled


def test_commit_operation_at_cap_rolls_back_artifact_and_abandonment(tmp_path):
    session = make(tmp_path, platform={"max_platform_operations": 2})
    lease = session.claim("a", "w")
    settle(session, lease)
    session.propose(lease, "receipt", 0.1)
    session.reserve(lease, "unused", "tool.evaluate", {}, prompt_tokens=0, max_new_tokens=5)
    before = session.snapshot()
    with pytest.raises(BudgetExceeded):
        session.commit("w", verify=verify, abstain_loss=1)
    assert session.snapshot() == before
    assert session.call("unused")["state"] == "reserved"
    assert session.snapshot()["artifacts"] == []


def test_commit_at_last_slot_repeats_without_another_control_operation(tmp_path):
    session = make(tmp_path, platform={"max_platform_operations": 3})
    lease = session.claim("a", "w")
    settle(session, lease)
    session.propose(lease, "receipt", 0.1)
    result = session.commit("w", verify=verify, abstain_loss=1)
    before = session.snapshot()
    assert session.commit("w", "b", verify=lambda *_: pytest.fail("repeat reverified"),
                          abstain_loss=0) == result
    assert session.snapshot() == before


def test_concurrent_commit_returns_one_durable_decision(tmp_path):
    session = make(tmp_path)
    lease = session.claim("a", "w")
    settle(session, lease)
    session.propose(lease, "receipt", 0.1)
    session.release(lease)
    barrier = Barrier(2)

    def commit(_index):
        contender = PlatformSession(session.path)
        barrier.wait(timeout=5)
        return contender.commit("w", verify=verify, abstain_loss=1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(commit, range(2)))
    assert outcomes[0] == outcomes[1]
    snapshot = session.snapshot()
    assert snapshot["call_count"] == 1
    assert len(snapshot["artifacts"]) == len(snapshot["platform"]["decisions"]) == 1
    assert sum(event["event_type"] == "interaction.session.platform.committed"
               for event in snapshot["events"]) == 1


@pytest.mark.parametrize("failure", ["budget", "coordination"])
def test_failed_layer_configuration_never_publishes_partial_session(tmp_path, failure):
    target = tmp_path / "session.sqlite"
    if failure == "budget":
        kwargs = {"platform": {"budgets": {"w": {"tokens": 101}}}}
    else:
        kwargs = {"cls": ScopedPlatform, **scope_options()}
        kwargs["inspections"][0]["source_id"] = "undeclared"
    with pytest.raises(ValueError):
        make(tmp_path, **kwargs)
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_platform_create_never_overwrites_existing_target(tmp_path):
    target = tmp_path / "session.sqlite"
    target.write_bytes(b"existing unrelated contents")
    with pytest.raises(FileExistsError):
        make(tmp_path)
    assert target.read_bytes() == b"existing unrelated contents"
    assert list(tmp_path.iterdir()) == [target]


def test_ready_enumeration_projects_expiry_without_mutating_ledger(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock=clock)
    lease = session.claim("a", "w", lease_seconds=1)
    session.reserve(lease, "pending", "tool.evaluate", {}, prompt_tokens=0, max_new_tokens=5)
    clock.now += 2
    before = session.snapshot()
    assert [row["id"] for row in session.ready_work("b")] == ["w"]
    assert session.snapshot() == before
    assert session.call("pending")["state"] == "reserved"
    current = session.claim("b", "w")
    assert current.epoch == lease.epoch + 1
    assert session.call("pending")["state"] == "abandoned"
