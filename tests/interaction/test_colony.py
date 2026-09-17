"""Colony sweep conformance over local mock sources; no provider calls, no network."""

from functools import partial
from hashlib import sha256
import json

import pytest

from pheroos_interaction import runner
from pheroos_interaction.commitment import CommitmentConfig, cross_inhibition_rule, optimal_stopping_rule
from pheroos_interaction.inspection import FAMILY, Losses, ModelAssumptions
from pheroos_interaction.leases import lease_ttl
from pheroos_interaction.records import StateError
from pheroos_interaction.runner.colony import run_colony
from pheroos_interaction.runner.driver import SessionDriver
from pheroos_interaction.runner.evidence import CoordinationSession
from pheroos_interaction.runner.platform import PlatformMixin, PlatformSession
from pheroos_interaction.runner.policies import pick_threshold
from pheroos_interaction.runner.session import _wire
from pheroos_interaction.runner.worker import run_worker
from pheroos_interaction.sequential import apply_sequential, plan_sequential, tree_digest


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class ScopedPlatform(PlatformMixin, CoordinationSession):
    pass


LOSSES = Losses(8, 4, 1)
QUERY_COST = .2


def work(name="w", dependencies=()):
    return dict(id=name, version=1, dependencies=list(dependencies), agents=["a", "b"],
                actions=["tool.evaluate"])


def make(tmp_path, *, cls=PlatformSession, platform_options=None, clock=None, items=None, **kwargs):
    options = dict(agents=["a", "b"], work=items or [work()], token_cap=100, max_calls=10, clock=clock,
                   platform=platform_options or {})
    options.update(kwargs)
    return cls.create(tmp_path / "session.sqlite", "run", **options)


def assumptions(q=.9, rho=0.):
    return ModelAssumptions(FAMILY, "v1", "declared", "test", .5, q, q, rho, rho)


def sequential(horizon=2, losses=LOSSES):
    return plan_sequential(assumptions(), losses, QUERY_COST, horizon)


READS = [{"tool_ref": "src0", "arguments": {"k": 0}}, {"tool_ref": "src1", "arguments": {"k": 1}}]


def outcome(artifact):
    return artifact["verdict"]


def planner_for(plan=None, reads=READS, abstain_loss=1., **extra):
    plan = plan or sequential()
    return lambda item: dict(plan=plan, reads=[dict(read) for read in reads], outcome=outcome,
                             abstain_loss=abstain_loss, **extra)


def sources(session, verdicts, reads=None, hooks=None):
    """Mock tools returning declared verdicts; ``reads`` collects (tool_ref, arguments)."""
    reads = [] if reads is None else reads
    tools = {}
    for index, verdict in enumerate(verdicts):
        def tool(args, index=index, verdict=verdict):
            reads.append(("src%d" % index, args))
            if hooks and index in hooks:
                hooks[index](args)
            return {"verdict": verdict}
        tools["src%d" % index] = tool
    return SessionDriver(session, tools=tools)


def colony_id(plan, depth, work_id="w", version=1, attempt=0):
    key = [work_id, version, tree_digest(plan), depth] + ([attempt] if attempt else [])
    return "colony:" + sha256(_wire(key).encode()).hexdigest()


class ExpiringDriver(SessionDriver):
    """Reserves, then lets the lease expire before dispatch: nothing is ever sent."""

    def __init__(self, session, clock, tools):
        super().__init__(session, tools=tools)
        self.clock = clock

    def evaluate(self, lease, call_id, tool_ref, arguments):
        payload = {"task_id": lease.task_id, "version": lease.version, "tool_ref": tool_ref,
                   "arguments": dict(arguments)}
        self.session.reserve(lease, call_id, "tool.evaluate", payload, prompt_tokens=0, max_new_tokens=0)
        self.clock.now += 100
        return self.session.dispatch(lease, call_id)


def rejected_receipt(session):
    """A rejected response under an unrelated call id: the artifact exceeds the declared byte bound."""
    lease = session.claim("a", "w")
    with pytest.raises(StateError):
        SessionDriver(session, tools={"big": lambda args: {"pad": "x" * 400}}).evaluate(lease, "earlier", "big", {"k": 9})
    assert session.call("earlier")["state"] == "response_rejected"
    return lease


def leaf(plan, outcomes):
    node = plan.tree
    for value in outcomes:
        node = node.children[int(value)]
    return node


def first(ready):
    return ready[0]["id"] if ready else None


def verify(_work, artifact):
    return type(artifact) is dict


def run(session, driver, planner=None, agent="a", **kwargs):
    kwargs.setdefault("policy", first)
    return run_colony(session, agent, driver=driver, planner=planner or planner_for(), verify=verify, **kwargs)


def propose(session, agent, call_id, loss):
    """The conformance-test helper: a second proposer settles its own receipt by hand."""
    lease = session.claim(agent, "w")
    SessionDriver(session, tools={"mock": lambda args: {"value": agent}}).evaluate(lease, call_id, "mock", {"k": 1})
    session.propose(lease, call_id, loss)
    session.release(lease)


def test_module_docstring_states_bounded_claims():
    text = runner.colony.__doc__.lower()
    for phrase in ("llm", "message", "retr", "optimal"):
        assert phrase in text
    assert "no" in text and "never" in text


def test_two_positive_reads_bind_tree_propose_leaf_loss_and_publish(tmp_path):
    session = make(tmp_path)
    plan = sequential()
    assert apply_sequential(plan, [True]) == ("query", 1) and apply_sequential(plan, [True, True]) == ("stop", "accept")
    reads = []
    driver = sources(session, (True, True), reads)
    result = run(session, driver)[0]
    sha = tree_digest(plan)
    assert reads == [("src0", {"k": 0, "tree_sha256": sha, "depth": 0}),
                     ("src1", {"k": 1, "tree_sha256": sha, "depth": 1})]
    assert result["status"] == "publish" and result["call_id"] == colony_id(plan, 1)
    snapshot = session.snapshot()
    assert [row["id"] for row in snapshot["calls"]] == [colony_id(plan, 0), colony_id(plan, 1)]
    node = leaf(plan, [True, True])
    candidate = snapshot["platform"]["candidates"][0]
    assert candidate["call_id"] == colony_id(plan, 1)
    assert candidate["certified_loss"] == node.stop_risk / (node.mass_h + node.mass_n)
    assert snapshot["artifacts"][0]["call_id"] == colony_id(plan, 1)
    assert snapshot["work"][0]["status"] == "done"


def test_negative_first_read_stops_after_one_read_per_tree(tmp_path):
    session = make(tmp_path)
    plan = sequential()
    step, action = apply_sequential(plan, [False])
    assert step == "stop" and action in {"reject", "accept"}
    reads = []
    result = run(session, sources(session, (False, True), reads))[0]
    assert len(reads) == 1 and session.snapshot()["call_count"] == 1
    node = leaf(plan, [False])
    assert result["status"] == "publish" and result["call_id"] == colony_id(plan, 0)
    candidate = session.snapshot()["platform"]["candidates"][0]
    assert candidate["certified_loss"] == node.stop_risk / (node.mass_h + node.mass_n)


def test_tree_abstention_after_reads_is_terminal_with_plan_reason(tmp_path):
    session = make(tmp_path)
    plan = sequential()
    assert apply_sequential(plan, [True, False]) == ("stop", "abstain")
    reads = []
    result = run(session, sources(session, (True, False), reads))[0]
    assert result == {"work": "w", "status": "abstain", "call_id": colony_id(plan, 1), "reason": "plan_stop:abstain"}
    assert len(reads) == 2 and session.snapshot()["artifacts"] == []
    assert run(session, sources(session, (True, True), reads)) == [] and len(reads) == 2


def test_restart_replays_same_decision_without_new_calls(tmp_path):
    session = make(tmp_path)
    reads = []
    driver = sources(session, (True, True), reads)
    result = run(session, driver)[0]
    before = session.snapshot()
    reopened = PlatformSession(session.path)
    assert run(reopened, sources(reopened, (True, True), reads)) == []
    decision = reopened.commit("w", "a", verify=lambda *_: pytest.fail("reverified"), abstain_loss=1.)
    assert decision["decision"] == "publish" and decision["call_id"] == result["call_id"]
    assert reopened.snapshot() == before and len(reads) == 2


def test_driver_failure_after_dispatch_at_depth_one_stays_unknown_across_restart(tmp_path):
    session = make(tmp_path)
    plan = sequential()
    reads = []

    def lost(args):
        raise TimeoutError("outcome unknown after dispatch")

    driver = sources(session, (True, True), reads, hooks={1: lost})
    result = run(session, driver)[0]
    assert result["status"] == "unknown" and result["call_id"] == colony_id(plan, 1)
    assert result["call_state"] == "dispatched"
    snapshot = session.snapshot()
    assert snapshot["work"][0]["status"] == "uncertain" and snapshot["unknown_calls"] == 1
    reopened = PlatformSession(session.path)
    assert run(reopened, sources(reopened, (True, True), reads)) == []
    assert reopened.claim("b", "w") is None
    assert len(reads) == 2 and reopened.snapshot()["call_count"] == 2
    reopened.receive(colony_id(plan, 1), {"artifact": {"verdict": True}, "prompt_tokens": 0, "completion_tokens": 0})
    recovered = run(reopened, sources(reopened, (True, True), reads))[0]
    assert recovered["status"] == "publish" and recovered["call_id"] == colony_id(plan, 1)
    assert len(reads) == 2


def test_mismatched_receipt_refuses_another_read(tmp_path):
    session = make(tmp_path)
    reads = []
    driver = sources(session, (True, True), reads)
    lease = session.claim("a", "w")
    driver.evaluate(lease, "earlier", "src0", {"k": 0, "tree_sha256": "other", "depth": 0})
    session.release(lease)
    result = run(session, driver)[0]
    assert result["status"] == "commit_error" and result["reason"] == "StateError"
    assert len(reads) == 1 and session.snapshot()["call_count"] == 1
    assert session.snapshot()["artifacts"] == [] and session.snapshot()["work"][0]["status"] == "ready"


def test_matching_receipt_is_reused_before_reading_the_next_depth(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock=clock)
    plan = sequential()
    reads = []
    driver = sources(session, (True, True), reads)
    lease = session.claim("a", "w", lease_seconds=1)
    driver.evaluate(lease, "hand", "src0", {"k": 0, "tree_sha256": tree_digest(plan), "depth": 0})
    clock.now += 2
    result = run(session, driver)[0]
    assert result["status"] == "publish" and result["call_id"] == colony_id(plan, 1)
    assert [tool for tool, _ in reads] == ["src0", "src1"]
    assert [row["id"] for row in session.snapshot()["calls"]] == ["hand", colony_id(plan, 1)]


def test_unknown_outcome_at_depth_zero_terminally_abstains_without_replanning(tmp_path):
    session = make(tmp_path)
    plan = sequential()
    assert apply_sequential(plan, [True]) == ("query", 1)
    reads = []
    result = run(session, sources(session, (None, True), reads))[0]
    assert result == {"work": "w", "status": "abstain", "call_id": colony_id(plan, 0), "reason": "unknown_outcome"}
    assert len(reads) == 1 and session.snapshot()["work"][0]["status"] == "done"
    assert run(session, sources(session, (True, True), reads)) == [] and len(reads) == 1


def test_root_stop_abstains_with_zero_calls_and_survives_restart(tmp_path):
    session = make(tmp_path)
    plan = sequential(horizon=1, losses=Losses(8, 1, 4))
    assert not plan.purchase and plan.stop_action in {"accept", "reject"}
    reads = []
    result = run(session, sources(session, (True,), reads), planner_for(plan, reads=READS[:1]))[0]
    assert result == {"work": "w", "status": "abstain", "call_id": None, "reason": "plan_stop:" + plan.stop_action}
    assert reads == [] and session.snapshot()["calls"] == []
    decisions = session.snapshot()["platform"]["decisions"]
    assert json.loads(decisions[0]["value"])["reason"] == "plan_stop:" + plan.stop_action
    reopened = PlatformSession(session.path)
    assert run(reopened, sources(reopened, (True,), reads), planner_for(plan, reads=READS[:1])) == []
    assert reopened.snapshot()["calls"] == []


def test_planner_no_purchase_abstains_without_any_call(tmp_path):
    session = make(tmp_path)
    driver = sources(session, (True, True))
    assert run(session, driver, lambda item: {"purchase": False})[0]["reason"] == "plan_no_purchase"
    assert run(session, driver, lambda item: {"purchase": False}) == []
    assert session.snapshot()["calls"] == []


def test_candidate_is_committed_before_a_plan_that_declines_to_buy(tmp_path):
    session = make(tmp_path)
    propose(session, "b", "w:b", .01)
    reads = []
    driver = sources(session, (True, True), reads)
    # Without an abstain_loss the candidate cannot be committed and nothing is decided or discarded.
    refused = run(session, driver, lambda item: {"purchase": False})[0]
    assert refused["status"] == "plan_error" and refused["reason"] == "ValueError"
    assert [row["call_id"] for row in session.candidates("w")] == ["w:b"]
    assert session.snapshot()["work"][0]["status"] == "ready" and session.snapshot()["platform"]["decisions"] == []
    waiting = lambda item: {"purchase": False, "abstain_loss": 1., "rule": lambda rows, loss: {"decision": "wait"}}
    assert run(session, driver, waiting)[0]["status"] == "wait"
    result = run(session, driver, lambda item: {"purchase": False, "abstain_loss": 1.})[0]
    assert result["status"] == "publish" and result["call_id"] == "w:b"
    assert reads == [] and session.snapshot()["artifacts"][0]["call_id"] == "w:b"
    assert session.snapshot()["calls"][-1]["id"] == "w:b"


def test_unrelated_rejected_response_does_not_disturb_a_complete_matching_history(tmp_path):
    session = make(tmp_path, artifact_bytes=160)
    plan = sequential()
    assert apply_sequential(plan, [False]) == ("stop", "reject")
    reads = []
    driver = sources(session, (False, True), reads)
    lease = rejected_receipt(session)
    driver.evaluate(lease, colony_id(plan, 0), "src0", {"k": 0, "tree_sha256": tree_digest(plan), "depth": 0})
    session.release(lease)
    result = run(session, driver)[0]
    assert result["status"] == "publish" and result["call_id"] == colony_id(plan, 0)
    assert len(reads) == 1 and session.snapshot()["artifacts"][0]["call_id"] == colony_id(plan, 0)


def test_rejected_response_forbids_buying_another_read(tmp_path):
    session = make(tmp_path, artifact_bytes=160)
    plan = sequential()
    assert apply_sequential(plan, [True]) == ("query", 1)
    reads = []
    driver = sources(session, (True, True), reads)
    lease = rejected_receipt(session)
    driver.evaluate(lease, colony_id(plan, 0), "src0", {"k": 0, "tree_sha256": tree_digest(plan), "depth": 0})
    session.release(lease)
    result = run(session, driver)[0]
    assert result == {"work": "w", "status": "abstain", "call_id": colony_id(plan, 0), "reason": "response_rejected"}
    assert len(reads) == 1 and session.snapshot()["artifacts"] == [] and session.snapshot()["work"][0]["status"] == "done"
    (tmp_path / "fresh").mkdir()
    fresh = make(tmp_path / "fresh", artifact_bytes=160)
    fresh.release(rejected_receipt(fresh))
    bare = run(fresh, sources(fresh, (True, True), reads))[0]
    assert bare == {"work": "w", "status": "abstain", "call_id": None, "reason": "response_rejected"}
    assert len(reads) == 1 and fresh.snapshot()["calls"][-1]["id"] == "earlier"


def test_threshold_policy_claims_nothing_below_and_fifo_above_break_even(tmp_path):
    session = make(tmp_path, items=[work("w1"), work("w2")])
    reads = []
    driver = sources(session, (True, True), reads)
    costs = dict(worker_cost=3, cheapest_cost=1, latency_cost=1, service_time=1, cheaper_workers=2)
    assert run(session, driver, policy=partial(pick_threshold, **costs)) == []
    assert reads == [] and session.snapshot()["calls"] == []
    eager = partial(pick_threshold, **{**costs, "latency_cost": 3})
    outcomes = run_colony(session, "a", driver=driver, planner=planner_for(), verify=verify, policy=eager)
    # Backlog 2 justifies the extra cost (3*2 > 2*2); after w1 drains, backlog 1 does not (3 > 4 fails).
    assert [row["work"] for row in outcomes] == ["w1"] and outcomes[0]["status"] == "publish"
    assert [row["id"] for row in session.ready_work("a")] == ["w2"]
    assert pick_threshold(session.ready_work("a"), **{**costs, "latency_cost": 3}) is None


def test_lease_ttl_sets_expiry_and_renew_precedes_each_read(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock=clock)
    ttl = lease_ttl([5, 10, 20], .1, 1, 5)["ttl"]
    assert ttl == 20
    seen = []

    def observe(args):
        seen.append(session.snapshot()["work"][0]["expires"])
        clock.now += 3

    driver = sources(session, (True, True), hooks={0: observe, 1: observe})
    result = run(session, driver, lease_seconds=ttl)[0]
    assert result["status"] == "publish"
    assert seen == [1000 + ttl, 1003 + ttl]
    renewed = [event["details"]["expires"] for event in session.snapshot()["events"]
               if event["event_type"] == "interaction.session.platform.renewed"]
    assert renewed == [1003 + ttl]


def test_cross_inhibition_rule_publishes_the_better_candidate(tmp_path):
    session = make(tmp_path)
    plan = sequential()
    waiting = planner_for(plan, rule=lambda candidates, loss: {"decision": "wait"})
    assert run(session, sources(session, (True, True)), waiting)[0]["status"] == "wait"
    propose(session, "b", "w:b", .01)
    assert len(session.candidates("w")) == 2
    config = CommitmentConfig(abstain_loss=1., latency_cost=.1, decision_time=1.)
    reads = []
    result = run(session, sources(session, (True, True), reads), rule=cross_inhibition_rule(config))[0]
    assert result["status"] == "publish" and result["call_id"] == "w:b"
    assert reads == [] and session.snapshot()["artifacts"][0]["call_id"] == "w:b"


def test_cross_inhibition_rule_abstains_on_equal_poor_candidates(tmp_path):
    session = make(tmp_path)
    plan = sequential()
    waiting = planner_for(plan, rule=lambda candidates, loss: {"decision": "wait"})
    assert run(session, sources(session, (True, True)), waiting)[0]["status"] == "wait"
    node = leaf(plan, [True, True])
    propose(session, "b", "w:b", node.stop_risk / (node.mass_h + node.mass_n))
    config = CommitmentConfig(abstain_loss=1., latency_cost=1., decision_time=1.)
    result = run(session, sources(session, (True, True)), rule=cross_inhibition_rule(config))[0]
    assert result["status"] == "abstain"
    assert session.snapshot()["artifacts"] == [] and session.claim("b", "w") is None


def test_rule_config_must_agree_with_ledger_abstain_loss(tmp_path):
    session = make(tmp_path)
    config = CommitmentConfig(abstain_loss=2., latency_cost=.1, decision_time=1.)
    result = run(session, sources(session, (True, True)), rule=cross_inhibition_rule(config))[0]
    assert result["status"] == "commit_error" and result["reason"] == "ValueError"
    assert len(session.candidates("w")) == 1 and session.snapshot()["artifacts"] == []


def test_wait_hold_records_no_entry_until_clock_passes(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock=clock)
    rule = optimal_stopping_rule(1., .01, 10, .9, [.01], [1.], 0)
    result = run(session, sources(session, (True, True)), rule=rule, wait_hold_seconds=30)[0]
    assert result["status"] == "wait" and result["held"] is True
    no_entry = session.snapshot()["platform"]["no_entry"]
    assert no_entry == [{"work_id": "w", "until": 1030, "reason": "commitment wait"}]
    assert session.ready_work("a") == []
    clock.now += 31
    assert [row["id"] for row in session.ready_work("a")] == ["w"]
    later = optimal_stopping_rule(1., .01, 10, .9, [.01], [1.], 10)
    reads = []
    assert run(session, sources(session, (True, True), reads), rule=later)[0]["status"] == "publish"
    assert reads == []


def test_wait_without_hold_leaves_no_entry_empty(tmp_path):
    session = make(tmp_path)
    waiting = planner_for(rule=lambda candidates, loss: {"decision": "wait"})
    result = run(session, sources(session, (True, True)), waiting)[0]
    assert result["status"] == "wait" and "held" not in result
    assert session.snapshot()["platform"]["no_entry"] == []
    assert [row["id"] for row in session.ready_work("a")] == ["w"]


def test_tree_deeper_than_the_work_call_cap_is_refused_before_any_read(tmp_path):
    session = make(tmp_path, platform_options={"budgets": {"w": {"calls": 1, "tokens": 0}}})
    assert session.ready_work("a")[0]["remaining"]["calls"] == 1
    reads = []
    result = run(session, sources(session, (True, True), reads))[0]
    assert result == {"work": "w", "status": "budget_exhausted", "call_id": None, "call_state": None,
                      "reason": "BudgetExceeded"}
    assert reads == [] and session.snapshot()["calls"] == [] and session.snapshot()["work"][0]["status"] == "ready"
    assert run(session, sources(session, (True, True), reads))[0]["status"] == "budget_exhausted" and reads == []
    # One remaining call affords the horizon-1 tree of the same family.
    plan = sequential(horizon=1)
    result = run(session, sources(session, (True,), reads), planner_for(plan, reads=READS[:1]))[0]
    assert result["status"] == "publish" and result["call_id"] == colony_id(plan, 0) and len(reads) == 1


def test_remaining_reads_of_the_subtree_are_checked_against_the_cap_after_reuse(tmp_path):
    plan = sequential()
    for calls, expected in ((1, "budget_exhausted"), (2, "publish")):
        (tmp_path / str(calls)).mkdir()
        session = make(tmp_path / str(calls), platform_options={"budgets": {"w": {"calls": calls, "tokens": 0}}})
        reads = []
        driver = sources(session, (True, True), reads)
        lease = session.claim("a", "w")
        driver.evaluate(lease, "hand", "src0", {"k": 0, "tree_sha256": tree_digest(plan), "depth": 0})
        session.release(lease)
        assert session.ready_work("a")[0]["remaining"]["calls"] == calls - 1
        result = run(session, driver)[0]
        assert result["status"] == expected
        if expected == "budget_exhausted":
            # The reused depth-0 receipt is current and the depth-1 read was never reserved.
            assert result["call_id"] == "hand" and result["call_state"] == "received"
            assert len(reads) == 1 and [row["id"] for row in session.snapshot()["calls"]] == ["hand"]
        else:
            assert result["call_id"] == colony_id(plan, 1) and [tool for tool, _ in reads] == ["src0", "src1"]


@pytest.mark.parametrize("kind", ["unknown", "response_rejected", "plan_error", "budget_exhausted"])
def test_exception_classification_matches_run_worker(tmp_path, kind):
    def build(name):
        options = {}
        if kind == "response_rejected":
            options["artifact_bytes"] = 64
        if kind == "budget_exhausted":
            options["platform_options"] = {"budgets": {"w": {"calls": 0, "tokens": 0}}}
        (tmp_path / name).mkdir()
        return make(tmp_path / name, **options)

    def tool(args):
        if kind == "unknown":
            raise TimeoutError("lost after dispatch")
        return {"verdict": True, "pad": "x" * 200 if kind == "response_rejected" else ""}

    worker_session, colony_session = build("worker"), build("colony")
    worker_plan = lambda item: dict(tool_ref="src0", arguments={"k": 0}, decide=lambda a: "publish",
                                    certified_loss=lambda a: .1, abstain_loss=1.)
    colony_plan = planner_for(sequential(horizon=1), reads=READS[:1])
    if kind == "plan_error":
        worker_plan = colony_plan = lambda item: (_ for _ in ()).throw(ValueError("planner failed"))
    from_worker = run_worker(worker_session, "a", driver=SessionDriver(worker_session, tools={"src0": tool}),
                             planner=worker_plan, verify=verify, policy=first)[0]
    from_colony = run(colony_session, SessionDriver(colony_session, tools={"src0": tool}), colony_plan)[0]
    assert from_colony["status"] == from_worker["status"] == kind
    assert from_colony.get("call_state") == from_worker.get("call_state")
    assert from_colony.get("reason") == from_worker.get("reason")
    assert colony_session.snapshot()["call_count"] == worker_session.snapshot()["call_count"]


def test_expired_lease_during_read_is_classified_lost(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock=clock)
    plan = sequential()

    def expire(args):
        clock.now += 100

    result = run(session, sources(session, (True, True), hooks={0: expire}), lease_seconds=10)[0]
    # The renewal before the depth-1 read is what fails, so that read's id is current.
    assert result["status"] == "lost" and result["call_id"] == colony_id(plan, 1)
    assert result["call_state"] is None and session.snapshot()["artifacts"] == []
    assert [row["state"] for row in session.snapshot()["calls"]] == ["received"]


def test_invalid_outcome_is_decision_error_and_receipt_is_reused(tmp_path):
    session = make(tmp_path)
    plan = sequential()
    reads = []
    driver = sources(session, (True, True), reads)
    typo = lambda item: {**planner_for()(item), "outcome": lambda artifact: "yes"}
    result = run(session, driver, typo)[0]
    assert result["status"] == "decision_error" and result["call_state"] == "received"
    assert result["call_id"] == colony_id(plan, 0) and session.snapshot()["artifacts"] == []
    assert run(session, driver)[0]["status"] == "publish"
    assert [tool for tool, _ in reads] == ["src0", "src1"]


@pytest.mark.parametrize("change", [
    {"reads": READS[:1]},
    {"reads": [READS[0], READS[0]]},
    {"reads": [READS[0], {"tool_ref": "src1", "arguments": {"depth": 1}}]},
    {"reads": [READS[0], {"tool_ref": "src1", "arguments": {"tree_sha256": "x"}}]},
    {"plan": "not a plan"},
    {"abstain_loss": True},
    {"outcome": "not callable"},
    {"rule": 1},
])
def test_invalid_colony_plan_is_rejected_before_any_read(tmp_path, change):
    session = make(tmp_path)
    reads = []
    driver = sources(session, (True, True), reads)
    result = run(session, driver, lambda item: {**planner_for()(item), **change})[0]
    assert result["status"] == "plan_error" and result["reason"] == "ValueError"
    assert reads == [] and session.snapshot()["calls"] == []
    assert session.snapshot()["work"][0]["status"] == "ready"


def test_horizon_one_plan_reads_once_and_publishes_leaf_loss(tmp_path):
    session = make(tmp_path)
    plan = sequential(horizon=1)
    reads = []
    result = run(session, sources(session, (True,), reads), planner_for(plan, reads=READS[:1]))[0]
    assert result["status"] == "publish" and len(reads) == 1
    node = leaf(plan, [True])
    assert session.snapshot()["platform"]["candidates"][0]["certified_loss"] == node.stop_risk / (node.mass_h + node.mass_n)


def scope_options(plan, arguments):
    return {"sources": [{"id": "source", "version": 1, "readers": ["a"], "state_fingerprint": "fp-1"}],
            "inspections": [{"work_id": "w", "source_id": "source", "source_version": 1, "tool_ref": "src0",
                             "tool_version": "tool-v1", "state_fingerprint": "fp-1", "readers": ["a"],
                             "arguments": {**arguments, "tree_sha256": tree_digest(plan), "depth": 0}}]}


def test_scoped_platform_declaration_binds_the_tree_digest(tmp_path):
    plan = sequential(horizon=1)
    session = make(tmp_path, cls=ScopedPlatform, **scope_options(plan, {"source_id": "source"}))
    reads = []
    declared = [{"tool_ref": "src0", "arguments": {"source_id": "source"}}]
    assert run(session, sources(session, (True,), reads), planner_for(plan, reads=declared), agent="b") == []
    result = run(session, sources(session, (True,), reads), planner_for(plan, reads=declared))[0]
    assert result["status"] == "publish" and result["call_id"] == colony_id(plan, 0)
    assert reads == [("src0", {"source_id": "source", "tree_sha256": tree_digest(plan), "depth": 0})]
    assert session.artifacts("a")[0]["work_id"] == "w" and session.artifacts("b") == []


def test_scoped_platform_refuses_undeclared_tree_and_abandoned_id_is_never_reused(tmp_path):
    declared = sequential(horizon=1)
    other = sequential(horizon=1, losses=Losses(4, 8, 1))
    assert tree_digest(other) != tree_digest(declared)
    session = make(tmp_path, cls=ScopedPlatform, **scope_options(declared, {"source_id": "source"}))
    reads = []
    planner = planner_for(other, reads=[{"tool_ref": "src0", "arguments": {"source_id": "source"}}])
    result = run(session, sources(session, (True,), reads), planner)[0]
    assert result["status"] == "read_error" and result["call_state"] == "reserved"
    assert result["call_id"] == colony_id(other, 0)
    assert reads == [] and session.call(colony_id(other, 0))["state"] == "abandoned"
    # The abandoned reservation was never dispatched: the next attempt takes its own id and fails the same way.
    again = run(session, sources(session, (True,), reads), planner)[0]
    assert again["status"] == "read_error" and again["call_state"] == "reserved"
    assert again["call_id"] == colony_id(other, 0, attempt=1) != colony_id(other, 0)
    assert reads == [] and [row["state"] for row in session.snapshot()["calls"]] == ["abandoned", "abandoned"]
    assert session.snapshot()["call_count"] == 2


def test_expiry_between_reserve_and_dispatch_requeues_under_the_next_attempt_id(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock=clock)
    plan = sequential()
    lost = run(session, ExpiringDriver(session, clock, {}), lease_seconds=10)[0]
    assert lost["status"] == "lost" and lost["call_id"] == colony_id(plan, 0) and lost["call_state"] == "reserved"
    assert session.call(colony_id(plan, 0))["state"] == "abandoned"
    assert session.snapshot()["work"][0]["status"] == "ready" and session.snapshot()["platform"]["decisions"] == []
    reads = []
    result = run(session, sources(session, (True, True), reads), lease_seconds=10)[0]
    assert result["status"] == "publish" and result["call_id"] == colony_id(plan, 1)
    assert [(tool, args["depth"]) for tool, args in reads] == [("src0", 0), ("src1", 1)]
    snapshot = session.snapshot()
    assert [(row["id"], row["state"]) for row in snapshot["calls"]] == [
        (colony_id(plan, 0), "abandoned"), (colony_id(plan, 0, attempt=1), "received"), (colony_id(plan, 1), "received")]
    assert snapshot["work"][0]["status"] == "done"
    reopened = PlatformSession(session.path)
    assert run(reopened, sources(reopened, (True, True), reads), lease_seconds=10) == [] and len(reads) == 2


def test_abandoned_attempts_count_against_the_work_call_cap(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock=clock, platform_options={"budgets": {"w": {"calls": 3, "tokens": 0}}})
    plan = sequential()
    for attempt in (0, 1):
        lost = run(session, ExpiringDriver(session, clock, {}), lease_seconds=10)[0]
        assert lost["status"] == "lost" and lost["call_id"] == colony_id(plan, 0, attempt=attempt)
    assert session.ready_work("a")[0]["remaining"]["calls"] == 1
    reads = []
    result = run(session, sources(session, (True, True), reads), lease_seconds=10)[0]
    assert result["status"] == "budget_exhausted" and result["call_id"] is None and reads == []
    assert [row["state"] for row in session.snapshot()["calls"]] == ["abandoned", "abandoned"]


def test_max_items_bounds_the_sweep(tmp_path):
    session = make(tmp_path, items=[work("w1"), work("w2")])
    outcomes = run(session, sources(session, (True, True)), max_items=1)
    assert [row["work"] for row in outcomes] == ["w1"]
    assert [row["id"] for row in session.ready_work("a")] == ["w2"]


@pytest.mark.parametrize("kwargs", [{"lease_seconds": 0}, {"wait_hold_seconds": True}, {"max_items": -1},
                                    {"rule": "x"}, {"policy": None}])
def test_invalid_sweep_arguments_are_rejected(tmp_path, kwargs):
    session = make(tmp_path)
    arguments = dict(driver=sources(session, (True, True)), planner=planner_for(), verify=verify, policy=first)
    arguments.update(kwargs)
    with pytest.raises(ValueError):
        run_colony(session, "a", **arguments)
    assert session.snapshot()["calls"] == []


def test_policy_outside_enumerated_set_is_rejected(tmp_path):
    session = make(tmp_path)
    with pytest.raises(ValueError):
        run(session, sources(session, (True, True)), policy=lambda ready: "other")
    assert session.snapshot()["calls"] == []


def test_call_ids_are_stable_across_reclaims_unlike_the_epoch_id(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock=clock)
    plan = sequential()
    first_lease = session.claim("a", "w", lease_seconds=1)
    clock.now += 2
    reads = []
    result = run(session, sources(session, (True, True), reads))[0]
    assert result["status"] == "publish"
    ids = [row["id"] for row in session.snapshot()["calls"]]
    assert ids == [colony_id(plan, 0), colony_id(plan, 1)]
    assert session.snapshot()["work"][0]["epoch"] == first_lease.epoch + 1
    assert all(row["epoch"] == first_lease.epoch + 1 for row in session.snapshot()["calls"])


def test_run_colony_rejects_policy_that_returns_non_string(tmp_path):
    session = make(tmp_path)
    with pytest.raises(ValueError):
        run(session, sources(session, (True, True)), policy=lambda ready: 1)


def test_worker_helpers_are_reused_not_copied():
    assert runner.colony._release is runner.worker._release
    assert runner.colony._call_status is runner.worker._call_status
