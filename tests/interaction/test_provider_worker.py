"""Opt-in adapter and thin worker conformance, using fake transports only."""

import json

import pytest

from pheroos_interaction.records import BudgetExceeded, StateError
from pheroos_interaction.runner.driver import SessionDriver
from pheroos_interaction.runner.provider import ProviderDriver
from pheroos_interaction.runner.session import Session
from pheroos_interaction.runner.worker import run_worker


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def work(name="w", dependencies=()):
    return dict(id=name, version=1, dependencies=list(dependencies), agents=["a", "b"],
                actions=["tool.evaluate"])


def make(tmp_path, *, platform=False, platform_options=None, clock=None, **kwargs):
    kind = Session
    if platform:
        from pheroos_interaction.runner.platform import PlatformSession
        kind = PlatformSession
    options = dict(agents=["a", "b"], work=[work()], token_cap=100, max_calls=10,
                   clock=clock)
    if platform_options is not None:
        options["platform"] = platform_options
    options.update(kwargs)
    return kind.create(tmp_path / "session.sqlite", "run", **options)


def extract(raw):
    return raw["artifact"], raw["prompt_tokens"], raw["completion_tokens"]


def receipt(**changes):
    return dict(artifact={"verdict": True}, prompt_tokens=3, completion_tokens=1) | changes


def provider(session, transport=None, **kwargs):
    return ProviderDriver(session, transport=transport or (lambda request: receipt()),
                          extract=extract, **kwargs)


def plan(_item):
    return dict(tool_ref="mock", arguments={"value": True}, decide=lambda artifact: "publish",
                certified_loss=lambda artifact: 0.1, abstain_loss=1.0)


def first(ready):
    return ready[0]["id"] if ready else None


def run(session, driver, planner=plan, **kwargs):
    return run_worker(session, "a", driver=driver, planner=planner,
                      verify=lambda _, artifact: type(artifact) is dict,
                      policy=first, **kwargs)


@pytest.mark.parametrize("enabled", [0, 1, "1", [], {}])
def test_provider_enable_is_exact_bool(tmp_path, enabled):
    session = make(tmp_path)
    with pytest.raises(ValueError):
        provider(session, enabled=enabled)
    assert session.snapshot()["calls"] == []


@pytest.mark.parametrize("flag", [None, "0", "true", "01"])
def test_provider_disabled_creates_no_call_rows(tmp_path, monkeypatch, flag):
    if flag is None:
        monkeypatch.delenv("PHEROOS_PROVIDER", raising=False)
    else:
        monkeypatch.setenv("PHEROOS_PROVIDER", flag)
    session = make(tmp_path)
    invoked = []
    adapter = provider(session, transport=lambda request: invoked.append(request))
    with pytest.raises(StateError, match="disabled"):
        adapter.evaluate(session.claim("a"), "c", {}, prompt_tokens=3, max_new_tokens=5)
    assert session.snapshot()["calls"] == [] and invoked == []


@pytest.mark.parametrize("kwargs", [{"prompt_tokens": True, "max_new_tokens": 5},
                                    {"prompt_tokens": 3, "max_new_tokens": False}])
def test_invalid_reserved_usage_has_no_side_effect(tmp_path, kwargs):
    session = make(tmp_path)
    with pytest.raises(ValueError):
        provider(session, enabled=True).evaluate(session.claim("a"), "c", {}, **kwargs)
    assert session.snapshot()["calls"] == []


def test_provider_transports_exact_frozen_durable_request(tmp_path, monkeypatch):
    session = make(tmp_path)
    original = {"messages": [{"role": "user", "content": "original"}]}
    reserve = session.reserve

    def changing_caller(*args, **kwargs):
        result = reserve(*args, **kwargs)
        original["messages"][0]["content"] = "changed after reservation"
        return result

    monkeypatch.setattr(session, "reserve", changing_caller)
    sent = []

    def transport(request):
        sent.append(json.loads(json.dumps(request)))
        request["messages"][0]["content"] = "transport mutation"
        return receipt()

    adapter = provider(session, transport=transport, enabled=True)
    lease = session.claim("a")
    response = adapter.evaluate(lease, "c", original, prompt_tokens=3, max_new_tokens=5)
    expected = {"messages": [{"role": "user", "content": "original"}], "max_tokens": 5}
    assert sent == [expected]
    assert session.call("c")["request"]["arguments"]["request"] == expected
    assert "idempotency_key" not in expected
    assert adapter.replay("c") == response
    with pytest.raises(StateError):
        adapter.evaluate(lease, "c", original, prompt_tokens=3, max_new_tokens=5)
    assert len(sent) == 1


@pytest.mark.parametrize("body", [{"max_tokens": 99}, {"max_tokens": True},
                                     {1: "silently coerced"}, {"x": float("nan")}])
def test_bad_request_rejected_before_reserve(tmp_path, body):
    session = make(tmp_path)
    with pytest.raises(ValueError):
        provider(session, enabled=True).evaluate(session.claim("a"), "c", body,
                                                 prompt_tokens=3, max_new_tokens=5)
    assert session.snapshot()["calls"] == []


@pytest.mark.parametrize("changes", [{"prompt_tokens": True}, {"completion_tokens": True},
                                     {"prompt_tokens": 2}, {"completion_tokens": 6},
                                     {"artifact": []}, {"artifact": {"x": float("nan")}}])
def test_invalid_extracted_receipt_stays_unknown(tmp_path, changes):
    session = make(tmp_path)
    adapter = provider(session, transport=lambda request: receipt(**changes), enabled=True)
    lease = session.claim("a")
    with pytest.raises((ValueError, StateError)):
        adapter.evaluate(lease, "c", {}, prompt_tokens=3, max_new_tokens=5)
    assert session.call("c")["state"] == "dispatched"
    assert session.snapshot()["unknown_tokens"] == 8


def test_transport_exception_crash_reopen_and_late_receipt(tmp_path):
    clock = Clock()
    session = make(tmp_path, clock=clock)
    sends = []

    def transport(request):
        sends.append(request)
        raise TimeoutError("outcome unknown")

    adapter = provider(session, transport=transport, enabled=True)
    with pytest.raises(TimeoutError):
        adapter.evaluate(session.claim("a", lease_seconds=1), "c", {}, prompt_tokens=3, max_new_tokens=5)
    clock.now += 2
    reopened = Session(session.path, clock=clock)
    assert reopened.claim("b") is None
    assert reopened.snapshot()["work"][0]["status"] == "uncertain"
    reopened.receive("c", receipt())
    ref = reopened.publish_received("b", "c", verify=lambda _, value: value == {"verdict": True})
    assert ref == reopened.publish_received("b", "c", verify=lambda *_: False)
    assert len(sends) == 1 and reopened.snapshot()["actual_tokens"] == 4
    reopened.receive("c", receipt())
    with pytest.raises(StateError):
        reopened.receive("c", receipt(artifact={"verdict": False}))


def test_byte_rejected_receipt_settles_usage_and_is_not_unknown(tmp_path):
    session = make(tmp_path, artifact_bytes=64)
    adapter = provider(session, enabled=True)
    with pytest.raises(StateError, match="durably settled"):
        adapter.evaluate(session.claim("a"), "c", {}, prompt_tokens=3, max_new_tokens=5)
    assert session.call("c")["state"] == "response_rejected"
    snapshot = session.snapshot()
    assert snapshot["actual_tokens"] == 4 and snapshot["unknown_tokens"] == 0


def test_worker_abstention_is_terminal_across_restarts(tmp_path):
    session = make(tmp_path, platform=True)
    reads = []
    driver = SessionDriver(session, tools={"mock": lambda args: reads.append(args) or {"verdict": False}})
    abstaining = lambda item: plan(item) | {"decide": lambda artifact: "abstain"}
    assert run(session, driver, abstaining)[0]["status"] == "abstain"
    reopened = type(session)(session.path)
    assert run(reopened, driver, abstaining) == []
    assert len(reads) == 1 and session.snapshot()["calls"][0]["state"] == "received"


def test_worker_recovers_received_receipt_without_another_read(tmp_path):
    clock = Clock()
    session = make(tmp_path, platform=True, clock=clock)
    reads = []
    driver = SessionDriver(session, tools={"mock": lambda args: reads.append(args) or {"verdict": None}})
    lease = session.claim("a", lease_seconds=1)
    response = driver.evaluate(lease, "before-crash", "mock", {"value": True})
    clock.now += 2
    reopened = type(session)(session.path, clock=clock)
    outcome = run(reopened, driver)[0]
    assert outcome["status"] == "publish" and outcome["call_id"] == "before-crash"
    assert driver.replay("before-crash") == response and len(reads) == 1
    assert json.loads(reopened.snapshot()["artifacts"][0]["value"]) == {"verdict": None}


def test_invalid_decision_is_not_silent_abstention_or_another_read(tmp_path):
    session = make(tmp_path, platform=True)
    reads = []
    driver = SessionDriver(session, tools={"mock": lambda args: reads.append(args) or {"verdict": False}})
    invalid = lambda item: plan(item) | {"decide": lambda artifact: "typo"}
    outcome = run(session, driver, invalid)[0]
    assert outcome["status"] == "decision_error" and outcome["call_state"] == "received"
    assert session.snapshot()["artifacts"] == []
    assert run(session, driver)[0]["status"] == "publish"
    assert len(reads) == 1


def test_worker_unknown_exception_is_classified_from_durable_state(tmp_path):
    session = make(tmp_path, platform=True)

    def raises_after_dispatch(args):
        raise BudgetExceeded("tool side effect may already have happened")

    driver = SessionDriver(session, tools={"mock": raises_after_dispatch})
    outcome = run(session, driver)[0]
    assert outcome["status"] == "unknown" and outcome["call_state"] == "dispatched"
    assert run(session, driver) == []
    assert session.snapshot()["call_count"] == 1


def test_worker_cancel_mid_call_retains_unknown_and_never_retries(tmp_path):
    session = make(tmp_path, platform=True)

    def cancel_then_timeout(args):
        session.cancel()
        raise TimeoutError("cancelled after dispatch")

    driver = SessionDriver(session, tools={"mock": cancel_then_timeout})
    assert run(session, driver)[0]["status"] == "unknown"
    assert run(session, driver) == []
    assert session.snapshot()["unknown_calls"] == 1


def test_worker_budget_exhaustion_leaves_no_reservation(tmp_path):
    session = make(tmp_path, platform=True, platform_options={"budgets": {"w": {"calls": 0, "tokens": 0}}})
    driver = SessionDriver(session, tools={"mock": lambda args: {}})
    outcome = run(session, driver)[0]
    assert outcome["status"] == "budget_exhausted"
    assert session.snapshot()["calls"] == []


def test_worker_wait_keeps_candidate_and_does_not_read_twice(tmp_path):
    session = make(tmp_path, platform=True)
    reads = []
    driver = SessionDriver(session, tools={"mock": lambda args: reads.append(args) or {"verdict": True}})
    waiting = lambda item: plan(item) | {"rule": lambda candidates, loss: {"decision": "wait"}}
    assert run(session, driver, waiting)[0]["status"] == "wait"
    assert run(session, driver)[0]["status"] == "publish"
    assert len(reads) == 1


def test_worker_rejects_bad_plan_before_read(tmp_path):
    session = make(tmp_path, platform=True)
    reads = []
    driver = SessionDriver(session, tools={"mock": lambda args: reads.append(args) or {}})
    outcome = run(session, driver, lambda item: plan(item) | {"abstain_loss": True})[0]
    assert outcome["status"] == "plan_error"
    assert reads == [] and session.snapshot()["calls"] == []


def test_worker_no_purchase_abstains_without_any_call(tmp_path):
    session = make(tmp_path, platform=True)
    driver = SessionDriver(session, tools={})
    assert run(session, driver, lambda item: {"purchase": False})[0]["status"] == "abstain"
    assert run(session, driver, lambda item: {"purchase": False}) == []
    assert session.snapshot()["calls"] == []


def test_worker_changed_read_plan_cannot_reinterpret_receipt_or_read_again(tmp_path):
    session = make(tmp_path, platform=True)
    reads = []
    driver = SessionDriver(session, tools={"mock": lambda args: reads.append(args) or {"verdict": True}})
    lease = session.claim("a")
    driver.evaluate(lease, "earlier", "mock", {"value": False})
    session.release(lease)
    outcome = run(session, driver)[0]
    assert outcome["status"] == "commit_error"
    assert len(reads) == 1 and session.snapshot()["artifacts"] == []


def test_worker_byte_rejection_is_settled_and_terminal(tmp_path):
    session = make(tmp_path, platform=True, artifact_bytes=64)
    driver = SessionDriver(session, tools={"mock": lambda args: {"large": "x" * 200}})
    outcome = run(session, driver)[0]
    assert outcome["status"] == "response_rejected"
    assert outcome["call_state"] == "response_rejected"
    assert session.snapshot()["unknown_calls"] == 0
    assert run(session, driver) == []
    assert session.snapshot()["call_count"] == 1


def test_worker_argmin_abstention_is_terminal(tmp_path):
    session = make(tmp_path, platform=True)
    driver = SessionDriver(session, tools={"mock": lambda args: {"verdict": True}})
    equal_loss = lambda item: plan(item) | {"certified_loss": lambda artifact: 1.0}
    assert run(session, driver, equal_loss)[0]["status"] == "abstain"
    assert run(session, driver, equal_loss) == []
    assert session.snapshot()["call_count"] == 1 and session.snapshot()["artifacts"] == []


def test_worker_late_recovery_uses_same_receipt_after_unknown(tmp_path):
    session = make(tmp_path, platform=True)
    invokes = []

    def timeout(args):
        invokes.append(args)
        raise TimeoutError("lost response")

    driver = SessionDriver(session, tools={"mock": timeout})
    first_outcome = run(session, driver)[0]
    assert first_outcome["status"] == "unknown"
    reopened = type(session)(session.path)
    reopened.receive(first_outcome["call_id"],
                     dict(artifact={"verdict": False}, prompt_tokens=0, completion_tokens=0))
    second = run(reopened, driver)[0]
    assert second["status"] == "publish" and second["call_id"] == first_outcome["call_id"]
    assert len(invokes) == 1
    assert json.loads(reopened.snapshot()["artifacts"][0]["value"]) == {"verdict": False}


def test_explicit_provider_worker_adapter_preserves_request_on_recovery(tmp_path):
    clock = Clock()
    session = make(tmp_path, platform=True, clock=clock)
    sends = []
    remote = provider(session, transport=lambda body: sends.append(body) or receipt(), enabled=True)

    class Adapter:
        def evaluate(self, lease, call_id, tool_ref, arguments):
            assert tool_ref == remote.tool_ref
            return remote.evaluate(lease, call_id, arguments["request"], prompt_tokens=3, max_new_tokens=5)

    provider_plan = lambda item: plan(item) | {
        "tool_ref": "provider.chat", "arguments": {"request": {"prompt": "x", "max_tokens": 5}}}
    lease = session.claim("a", lease_seconds=1)
    response = Adapter().evaluate(lease, "provider-crash", "provider.chat", provider_plan({})["arguments"])
    clock.now += 2
    reopened = type(session)(session.path, clock=clock)
    assert run(reopened, Adapter(), provider_plan)[0]["status"] == "publish"
    assert len(sends) == 1 and remote.replay("provider-crash") == response
