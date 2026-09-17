"""Durability scenarios for platform transitions; local mocks, no provider calls."""

from concurrent.futures import ThreadPoolExecutor
import json
from random import Random
import sqlite3
from threading import Barrier

import pytest

from pheroos_interaction.records import BudgetExceeded, LeaseLost, StateError
from pheroos_interaction.runner.driver import SessionDriver
from pheroos_interaction.runner.platform import PlatformSession


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def work(key, deps=(), agents=("a", "b")):
    return {"id": key, "version": 1, "dependencies": list(deps),
            "agents": list(agents), "actions": ["tool.evaluate"]}


def child(key, *, calls=1, tokens=10, deps=(), agents=("a", "b")):
    return {**work(key, deps, agents), "budget": {"calls": calls, "tokens": tokens}}


def make(tmp_path, clock, items, budgets=None, **platform):
    return PlatformSession.create(tmp_path / "s.sqlite", "run-1", agents=["a", "b", "host"],
                                  work=items, token_cap=10_000, max_calls=50, clock=clock,
                                  platform={"budgets": budgets or {}, **platform})


def verify_ok(task_id, artifact):
    return True


def read_ok(session, lease, call_id, value="x"):
    driver = SessionDriver(session, tools={"mock": lambda args: {"value": value, "arg": args}})
    return driver.evaluate(lease, call_id, "mock", {"k": 1})


def reserve(session, lease, call_id, *, tokens=0):
    return session.reserve(lease, call_id, "tool.evaluate", {"tool_ref": "mock", "arguments": {}},
                           prompt_tokens=0, max_new_tokens=tokens)


def propose(session, agent, call_id, loss):
    lease = session.claim(agent, "w")
    read_ok(session, lease, call_id, agent)
    session.propose(lease, call_id, loss)
    session.release(lease)


def test_ready_work_access_dependencies_order_ages_and_no_content(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("w1"), work("w2", deps=["w1"]), work("w3", agents=["b"])])
    ready = session.ready_work("a")
    assert [row["id"] for row in ready] == ["w1"]
    assert set(ready[0]) == {"id", "version", "age", "depth", "parent", "remaining"}
    clock.now += 5
    assert session.ready_work("a")[0]["age"] == 5
    session.mark_no_entry("w1", clock.now + 100, "operator hold")
    assert session.ready_work("a") == []
    clock.now += 100
    assert [row["id"] for row in session.ready_work("a")] == ["w1"]
    with pytest.raises(StateError):
        session.ready_work("undeclared")


def test_decompose_transfers_caps_and_parent_waits_for_all_children(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("root")], budgets={"root": {"calls": 4, "tokens": 1000}})
    lease = session.claim("a", "root")
    before = session.snapshot()
    with pytest.raises(BudgetExceeded):
        session.decompose(lease, [child("too-large", calls=5)])
    assert session.snapshot() == before
    ids = session.decompose(lease, [child("c1", tokens=300), child("c2", tokens=300, deps=["c1"])])
    assert ids == ["c1", "c2"]
    with pytest.raises(LeaseLost):
        session.check_current(lease)
    ready = session.ready_work("a")
    assert [row["id"] for row in ready] == ["c1"]
    assert ready[0]["depth"] == 1 and ready[0]["parent"] == "root"
    assert ready[0]["remaining"] == {"calls": 1, "tokens": 300}
    assert session.claim("a", "root") is None
    for key in ("c1", "c2"):
        current = session.claim("a", key)
        read_ok(session, current, key + ":1")
        with pytest.raises(BudgetExceeded):
            reserve(session, current, key + ":2")
        assert not [row for row in session.snapshot()["calls"] if row["state"] == "reserved"]
        session.publish(current, key + ":1", {"value": "x", "arg": {"k": 1}}, verify=verify_ok)
    root = session.ready_work("a")[0]
    assert root["id"] == "root" and root["remaining"] == {"calls": 2, "tokens": 400}
    current = session.claim("a", "root")
    with pytest.raises(ValueError):
        session.decompose(current, [child("c3")], parent_depends=False)
    session.check_current(current)
    session.decompose(current, [child("c3", tokens=1)])
    assert [row["id"] for row in session.ready_work("a")] == ["c3"]


@pytest.mark.parametrize("dispatch", [False, True])
def test_decompose_refuses_open_or_unknown_calls_without_mutation(tmp_path, dispatch):
    clock = Clock()
    session = make(tmp_path, clock, [work("root")])
    lease = session.claim("a", "root")
    reserve(session, lease, "root:1", tokens=5)
    if dispatch:
        session.dispatch(lease, "root:1")
    before = session.snapshot()
    with pytest.raises(StateError):
        session.decompose(lease, [child("c")])
    assert session.snapshot() == before


@pytest.mark.parametrize("kind", ["sibling", "full_graph", "self"])
def test_decompose_rejects_all_dependency_cycles_atomically(tmp_path, kind):
    clock = Clock()
    session = make(tmp_path, clock, [work("root"), work("after-root", deps=["root"])])
    lease = session.claim("a", "root")
    children = {"sibling": [child("c1", deps=["c2"]), child("c2", deps=["c1"])],
                "full_graph": [child("c1", deps=["after-root"])],
                "self": [child("c1", deps=["c1"])]}[kind]
    before = session.snapshot()
    with pytest.raises(ValueError):
        session.decompose(lease, children)
    assert session.snapshot() == before
    session.check_current(lease)


def test_decompose_cannot_expand_parent_readers_and_depth_is_bounded(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("root", agents=["a"])], max_depth=1)
    lease = session.claim("a", "root")
    with pytest.raises(ValueError):
        session.decompose(lease, [child("foreign", agents=["b"])])
    session.decompose(lease, [child("c1", agents=["a"])])
    child_lease = session.claim("a", "c1")
    with pytest.raises(BudgetExceeded):
        session.decompose(child_lease, [child("grandchild", agents=["a"])])


def test_cap_transfer_accounts_for_actual_parent_spend_and_reserved_maximum(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("root")], budgets={"root": {"calls": 3, "tokens": 10}})
    lease = session.claim("a", "root")
    reserve(session, lease, "root:1", tokens=8)
    session.dispatch(lease, "root:1")
    session.receive("root:1", {"artifact": {}, "prompt_tokens": 0, "completion_tokens": 3})
    with pytest.raises(BudgetExceeded):
        session.decompose(lease, [child("c", calls=2, tokens=8)])
    session.decompose(lease, [child("c", calls=2, tokens=7)])
    current = session.claim("a", "c")
    with pytest.raises(BudgetExceeded):
        reserve(session, current, "c:oversized", tokens=8)
    reserve(session, current, "c:1", tokens=7)
    assert session.snapshot()["actual_tokens"] + session.snapshot()["reserved_tokens"] == 10
    assert session.snapshot()["call_count"] == 2


def assert_subtree_caps(session):
    """Audit the durable economic invariant, including every ancestor's subtree."""
    with sqlite3.connect(session.path) as db:
        db.row_factory = sqlite3.Row
        budgets = {row["work_id"]: dict(row) for row in db.execute("SELECT * FROM platform_work_v1")}
    calls = session.snapshot()["calls"]
    charged = {}
    for key, budget in budgets.items():
        local = [call for call in calls if call["work_id"] == key]
        tokens = sum(call["reserved"] if call["state"] in ("reserved", "dispatched")
                     else call["actual"] or 0 for call in local)
        charged[key] = len(local), tokens
        assert len(local) <= budget["calls_cap"]
        assert tokens <= budget["tokens_cap"]
    for ancestor, original in budgets.items():
        subtree = set()
        for key in budgets:
            node = key
            while node is not None:
                if node == ancestor:
                    subtree.add(key)
                    break
                node = budgets[node]["parent"]
        assert sum(budgets[key]["calls_cap"] for key in subtree) == original["original_calls"]
        assert sum(budgets[key]["tokens_cap"] for key in subtree) == original["original_tokens"]
        assert sum(charged[key][0] for key in subtree) <= original["original_calls"]
        assert sum(charged[key][1] for key in subtree) <= original["original_tokens"]


@pytest.mark.parametrize("seed", range(8))
def test_multilevel_caps_conserved_with_settlement_abandonment_and_unknowns(tmp_path, seed):
    rng = Random(seed)
    clock = Clock()
    session = make(tmp_path, clock, [work("root")],
                   budgets={"root": {"calls": rng.randint(15, 20), "tokens": 100}})

    def settle(lease, call_id, cap, actual):
        reserve(session, lease, call_id, tokens=cap)
        assert_subtree_caps(session)
        session.dispatch(lease, call_id)
        assert_subtree_caps(session)
        session.receive(call_id, {"artifact": {}, "prompt_tokens": 0, "completion_tokens": actual})
        assert_subtree_caps(session)

    root = session.claim("a", "root")
    settle(root, "root:1", 10, rng.randint(0, 5))
    session.decompose(root, [child("a", calls=6, tokens=40), child("b", calls=4, tokens=25)])
    assert_subtree_caps(session)
    branch_a = session.claim("a", "a")
    settle(branch_a, "a:1", 10, rng.randint(0, 8))
    session.decompose(branch_a, [child("a1", calls=2, tokens=12), child("a2", calls=2, tokens=15)])
    assert_subtree_caps(session)

    branch_b = session.claim("b", "b")
    reserve(session, branch_b, "b:unused", tokens=25)
    assert_subtree_caps(session)
    session.release(branch_b)
    assert_subtree_caps(session)
    branch_b = session.claim("b", "b")
    settle(branch_b, "b:1", 25, 25)
    with pytest.raises(BudgetExceeded):
        reserve(session, branch_b, "b:over", tokens=1)
    assert_subtree_caps(session)
    session.publish(branch_b, "b:1", {}, verify=verify_ok)

    leaf_a1 = session.claim("a", "a1")
    reserve(session, leaf_a1, "a1:unknown", tokens=12)
    session.dispatch(leaf_a1, "a1:unknown")
    assert session.release(leaf_a1) == "uncertain"
    leaf_a2 = session.claim("a", "a2")
    settle(leaf_a2, "a2:1", 15, rng.randint(0, 15))
    session.publish(leaf_a2, "a2:1", {}, verify=verify_ok)
    assert_subtree_caps(session)
    assert session.claim("a", "a") is None
    assert session.claim("a", "root") is None
    assert session.snapshot()["unknown_tokens"] == 12


@pytest.mark.parametrize("cap,tokens", [({"calls": 1, "tokens": 10}, 0),
                                      ({"calls": 2, "tokens": 5}, 3)])
def test_two_writers_cannot_overshoot_work_cap_or_leave_failed_reservation(tmp_path, cap, tokens):
    clock = Clock()
    session = make(tmp_path, clock, [work("w")], budgets={"w": cap})
    lease = session.claim("a", "w")
    start = Barrier(2)

    def writer(call_id):
        connection = PlatformSession(session.path, clock=clock)
        start.wait()
        try:
            return reserve(connection, lease, call_id, tokens=tokens)
        except BudgetExceeded:
            return "exhausted"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs = list(pool.map(writer, ["w:1", "w:2"]))
    assert outputs.count("exhausted") == 1
    snapshot = session.snapshot()
    assert snapshot["call_count"] == 1
    assert snapshot["reserved_tokens"] <= cap["tokens"]
    assert len(snapshot["calls"]) <= cap["calls"]
    assert all(row["state"] == "reserved" for row in snapshot["calls"])
    session.release(lease)
    assert session.snapshot()["reserved_tokens"] == 0


def test_release_renew_preserve_epoch_and_fence_prior_owner(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("w")])
    lease = session.claim("a", "w", lease_seconds=10)
    assert session.renew(lease, 100) == clock.now + 100
    assert session.renew(lease, 5) >= clock.now + 100
    clock.now += 50
    session.check_current(lease)
    assert session.snapshot()["work"][0]["epoch"] == lease.epoch
    assert session.release(lease) == "ready"
    with pytest.raises(LeaseLost):
        session.renew(lease, 5)
    assert session.claim("b", "w").epoch == lease.epoch + 1


def test_release_abandons_only_undispatched_reservations(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("w")])
    lease = session.claim("a", "w")
    reserve(session, lease, "w:pending", tokens=2)
    reserve(session, lease, "w:unknown", tokens=3)
    session.dispatch(lease, "w:unknown")
    assert session.release(lease) == "uncertain"
    states = {row["id"]: row["state"] for row in session.snapshot()["calls"]}
    assert states == {"w:pending": "abandoned", "w:unknown": "dispatched"}
    assert session.claim("b", "w") is None


def test_no_entry_expiry_cannot_clear_unresolved_dispatch(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("w")])
    lease = session.claim("a", "w")
    reserve(session, lease, "w:1")
    session.dispatch(lease, "w:1")
    session.release(lease)
    before = session.call("w:1")
    session.mark_no_entry("w", clock.now + 10, "await late receipt")
    clock.now += 11
    assert session.ready_work("b") == []
    assert session.claim("b", "w") is None
    assert session.call("w:1") == before
    session.receive("w:1", {"artifact": {}, "prompt_tokens": 0, "completion_tokens": 0})
    assert [row["id"] for row in session.ready_work("b")] == ["w"]


def test_no_entry_blocks_claim_but_existing_receipt_recovery_is_allowed(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("w")])
    lease = session.claim("a", "w")
    read_ok(session, lease, "w:1")
    session.release(lease)
    session.mark_no_entry("w", clock.now + 100, "do not dispatch more work")
    assert session.ready_work("a") == []
    assert session.claim("b", "w") is None
    assert session.publish_received("b", "w:1", verify=verify_ok).startswith("sha256:")
    assert session.snapshot()["call_count"] == 1


def test_platform_operation_exhaustion_cannot_prevent_safe_release(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("w")], max_platform_operations=1)
    lease = session.claim("a", "w")
    with pytest.raises(BudgetExceeded):
        session.renew(lease, 100)
    with pytest.raises(BudgetExceeded):
        session.mark_no_entry("w", clock.now + 100, "hold")
    assert session.release(lease) == "ready"
    with pytest.raises(BudgetExceeded):
        session.claim("b", "w")


@pytest.mark.parametrize("budgets", [{"missing": {"calls": 1, "tokens": 1}},
                                     {"w": {"calls": -1, "tokens": 1}},
                                     {"w": {"calls": True, "tokens": 1}},
                                     {"w": {"calls": 1, "tokens": -1}},
                                     {"w": {"calls": 51, "tokens": 1}}])
def test_invalid_work_budgets_fail_before_creating_ledger(tmp_path, budgets):
    with pytest.raises(ValueError):
        make(tmp_path, Clock(), [work("w")], budgets=budgets)
    assert not (tmp_path / "s.sqlite").exists()


def test_commit_argmin_defaults_to_winning_proposer_and_replays_no_call(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("w")])
    propose(session, "a", "w:a", .8)
    propose(session, "b", "w:b", .3)
    assert [row["call_id"] for row in session.candidates("w")] == ["w:b", "w:a"]
    with pytest.raises(PermissionError):
        session.commit("w", "host", verify=verify_ok, abstain_loss=1)
    result = session.commit("w", verify=verify_ok, abstain_loss=1)
    assert result["decision"] == "publish" and result["call_id"] == "w:b" and result["publisher"] == "b"
    snapshot = session.snapshot()
    assert snapshot["artifacts"][0]["call_id"] == "w:b"
    assert snapshot["call_count"] == 2
    assert session.commit("w", verify=lambda *args: pytest.fail("replayed verification"), abstain_loss=0) == result
    assert session.snapshot() == snapshot


def test_commit_loss_tie_breaks_by_call_id_and_equal_abstention_is_terminal(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("w")])
    propose(session, "a", "w:z", .3)
    propose(session, "b", "w:a", .3)
    assert [row["call_id"] for row in session.candidates("w")] == ["w:a", "w:z"]
    result = session.commit("w", verify=verify_ok, abstain_loss=.3)
    assert result["decision"] == "abstain"
    assert session.ready_work("a") == [] and session.claim("a", "w") is None
    snapshot = session.snapshot()
    assert session.commit("w", verify=verify_ok, abstain_loss=1) == result
    assert session.snapshot() == snapshot
    assert not snapshot["artifacts"]


def test_empty_candidate_and_wait_are_nonterminal_and_cannot_choose_foreign_receipt(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("w")])
    assert session.commit("w", verify=verify_ok, abstain_loss=1)["decision"] == "no_candidate"
    propose(session, "a", "w:1", .1)
    result = session.commit("w", verify=verify_ok, abstain_loss=1,
                            rule=lambda candidates, loss: {"decision": "wait"})
    assert result["decision"] == "wait"
    assert [row["id"] for row in session.ready_work("a")] == ["w"]
    with pytest.raises(StateError):
        session.commit("w", verify=verify_ok, abstain_loss=1, rule=lambda rows, loss: "foreign:1")
    assert session.commit("w", verify=verify_ok, abstain_loss=1)["decision"] == "publish"


def test_rule_none_is_explicit_terminal_abstention(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("w")])
    propose(session, "a", "w:1", .1)
    result = session.commit("w", verify=verify_ok, abstain_loss=1, rule=lambda rows, loss: None)
    assert result["decision"] == "abstain"
    assert session.claim("b", "w") is None


def test_proposal_is_settled_bounded_and_idempotent(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("w")], max_candidates=1)
    lease = session.claim("a", "w")
    reserve(session, lease, "w:1")
    with pytest.raises(StateError):
        session.propose(lease, "w:1", .1)
    session.dispatch(lease, "w:1")
    with pytest.raises(StateError):
        session.propose(lease, "w:1", .1)
    session.receive("w:1", {"artifact": {}, "prompt_tokens": 0, "completion_tokens": 0})
    session.propose(lease, "w:1", .1)
    before = session.snapshot()
    session.propose(lease, "w:1", .1)
    assert session.snapshot() == before
    with pytest.raises(StateError):
        session.propose(lease, "w:1", .2)
    read_ok(session, lease, "w:2")
    with pytest.raises(BudgetExceeded):
        session.propose(lease, "w:2", .05)


def test_crash_after_dispatch_recovers_late_receipt_without_retry(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("w")])
    lease = session.claim("a", "w", lease_seconds=10)
    reserve(session, lease, "w:1")
    session.dispatch(lease, "w:1")
    del session
    clock.now += 11
    recovered = PlatformSession(tmp_path / "s.sqlite", clock=clock)
    assert recovered.claim("b", "w") is None
    assert recovered.snapshot()["work"][0]["status"] == "uncertain"
    with pytest.raises((StateError, LeaseLost)):
        reserve(recovered, lease, "w:1")
    recovered.receive("w:1", {"artifact": {"v": 1}, "prompt_tokens": 0, "completion_tokens": 0})
    ref = recovered.publish_received("b", "w:1", verify=verify_ok)
    assert ref.startswith("sha256:") and recovered.snapshot()["call_count"] == 1
    snapshot = recovered.snapshot()
    again = PlatformSession(tmp_path / "s.sqlite", clock=clock)
    assert again.publish_received("b", "w:1", verify=verify_ok) == ref
    assert again.snapshot() == snapshot


def test_duplicate_receipt_replay_matches_original_and_conflict_rejected(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("w")])
    lease = session.claim("a", "w")
    response = read_ok(session, lease, "w:1")
    before = session.snapshot()
    session.receive("w:1", response)
    assert session.snapshot() == before
    with pytest.raises(StateError):
        session.receive("w:1", {**response, "artifact": {"value": "changed"}})
    assert SessionDriver(session).replay("w:1") == response
    assert json.dumps(session.snapshot(), sort_keys=True) == json.dumps(before, sort_keys=True)


def test_every_lease_transition_rejects_expired_superseded_owner(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("w")])
    old = session.claim("a", "w", lease_seconds=10)
    read_ok(session, old, "w:receipt")
    clock.now += 11
    new = session.claim("b", "w")
    assert new.epoch == old.epoch + 1
    operations = [lambda: reserve(session, old, "w:x"), lambda: session.renew(old, 5),
                  lambda: session.release(old), lambda: session.propose(old, "w:receipt", .1),
                  lambda: session.decompose(old, [child("c")])]
    for operation in operations:
        with pytest.raises(LeaseLost):
            operation()


def test_cancel_mid_call_settles_usage_but_blocks_all_publication(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock, [work("w")])
    lease = session.claim("a", "w")
    reserve(session, lease, "w:1", tokens=3)
    session.dispatch(lease, "w:1")
    session.cancel()
    session.receive("w:1", {"artifact": {"v": 1}, "prompt_tokens": 0, "completion_tokens": 2})
    assert session.snapshot()["actual_tokens"] == 2
    assert session.claim("b") is None and session.ready_work("b") == []
    with pytest.raises(LeaseLost):
        session.publish(lease, "w:1", {"v": 1}, verify=verify_ok)
    with pytest.raises(PermissionError):
        session.publish_received("a", "w:1", verify=verify_ok)
    with pytest.raises((LeaseLost, PermissionError, StateError)):
        session.commit("w", verify=verify_ok, abstain_loss=1)
