"""Bounded thin worker for platform transitions, with durable receipt recovery.

Callbacks are trusted local code. No durable worker state or retry queue exists;
reopening a session uses its receipts and candidates instead of reading again.
"""

from __future__ import annotations

from hashlib import sha256

from pheroos_interaction.records import BudgetExceeded, LeaseLost, StateError
from .provider import _freeze
from .session import _duration, _integer, _wire


def _plan(value):
    required = {"tool_ref", "arguments", "decide", "certified_loss", "abstain_loss"}
    if type(value) is not dict or set(value) - required - {"rule", "purchase"}:
        raise ValueError("worker plan requires tool_ref, arguments, decide, certified_loss and abstain_loss")
    if type(value.get("purchase", True)) is not bool:
        raise ValueError("purchase must be a bool")
    if value.get("purchase") is False:
        return {"purchase": False}
    if not required <= value.keys():
        raise ValueError("read plan requires tool_ref, arguments, decide, certified_loss and abstain_loss")
    from .platform import _loss
    if type(value["tool_ref"]) is not str or not value["tool_ref"].strip():
        raise ValueError("nonempty tool_ref required")
    if type(value["arguments"]) is not dict:
        raise ValueError("dictionary arguments required")
    if not callable(value["decide"]) or not callable(value["certified_loss"]):
        raise ValueError("decision and certified-loss callbacks required")
    if value.get("rule") is not None and not callable(value["rule"]):
        raise ValueError("rule must be callable")
    return {**value, "arguments": _freeze(value["arguments"]),
            "abstain_loss": _loss(value["abstain_loss"], "abstain_loss")}


def _release(session, lease):
    try:
        return session.release(lease)
    except LeaseLost:
        # Expired reservations can be abandoned; dispatched calls remain
        # unknown. Cancellation has already performed this reconciliation.
        session.recover()
        return None
    except (StateError, BudgetExceeded):
        # The original call state remains durable if a control cap is exhausted.
        return None


def _call_status(session, call_id):
    try:
        return session.call(call_id)["state"]
    except StateError:
        return None


def run_worker(session, agent, *, driver, planner, verify, policy, renew_seconds=60, max_items=None):
    """Run one bounded sweep, visiting a work identity at most once.

    A plan has ``tool_ref``, JSON ``arguments``, pure ``decide(artifact)`` returning
    exactly ``publish`` or ``abstain``, ``certified_loss(artifact)``, ``abstain_loss``
    and an optional commit ``rule``. The driver follows SessionDriver's evaluate
    signature; ProviderDriver can be wrapped by an explicit request/token adapter.
    ``{'purchase': False}`` terminally abstains without reserving a call.
    ``wait`` from commit releases the lease but preserves candidates for the next
    sweep. Abstention is terminal, so it survives a new worker or process restart.
    """
    _duration(renew_seconds)
    for callback in (planner, verify, policy):
        if not callable(callback):
            raise ValueError("callable planner, verifier and policy required")
    if max_items is not None:
        _integer(max_items, "max_items")
    limit = len(session.ready_work(agent)) if max_items is None else max_items
    outcomes, visited = [], set()
    while len(visited) < limit:
        ready = [row for row in session.ready_work(agent) if row["id"] not in visited]
        if not ready:
            break
        work_id = policy(_freeze(ready))
        if work_id is None:
            break
        if type(work_id) is not str or work_id not in {row["id"] for row in ready}:
            raise ValueError("policy selected work outside the enumerated set")
        visited.add(work_id)
        item = next(row for row in ready if row["id"] == work_id)
        lease = session.claim(agent, work_id, lease_seconds=renew_seconds)
        if lease is None:
            outcomes.append({"work": work_id, "status": "unavailable"})
            continue
        call_id = None
        phase = "plan"
        try:
            plan = _plan(planner(_freeze(item)))
            records = session.work_calls(lease)
            unresolved = next((row for row in records if row["state"] == "dispatched"), None)
            if unresolved:
                call_id = unresolved["id"]
                _release(session, lease)
                outcomes.append({"work": work_id, "status": "unknown", "call_id": call_id})
                continue
            if any(row["state"] == "reserved" for row in records):
                _release(session, lease)
                outcomes.append({"work": work_id, "status": "reservation_abandoned"})
                continue
            if plan.get("purchase") is False:
                session.abstain(lease, reason="plan_no_purchase")
                outcomes.append({"work": work_id, "status": "abstain", "call_id": None})
                continue
            phase = "commit"
            candidates = session.candidates(work_id, agent=agent)
            if not candidates:
                received = [row for row in records if row["state"] == "received"]
                if received:
                    matching = [row for row in received
                                if row["request"].get("tool_ref") == plan["tool_ref"]
                                and _wire(row["request"].get("arguments")) == _wire(plan["arguments"])]
                    if not matching:
                        raise StateError("existing receipt does not match this read plan; another read is refused")
                    call_id = matching[-1]["id"]
                    response = matching[-1]["response"]
                elif any(row["state"] == "response_rejected" for row in records):
                    session.abstain(lease, reason="response_rejected")
                    outcomes.append({"work": work_id, "status": "response_rejected"})
                    continue
                else:
                    phase = "read"
                    call_id = "worker:" + sha256(_wire([work_id, lease.version, lease.epoch]).encode()).hexdigest()
                    session.renew(lease, renew_seconds)
                    response = driver.evaluate(lease, call_id, plan["tool_ref"], plan["arguments"])
                phase = "decision"
                artifact = _freeze(response["artifact"])
                action = plan["decide"](_freeze(artifact))
                if type(action) is not str or action not in {"publish", "abstain"}:
                    raise ValueError("decide must return publish or abstain")
                if action == "abstain":
                    session.abstain(lease, reason="worker_abstain")
                    outcomes.append({"work": work_id, "status": "abstain", "call_id": call_id})
                    continue
                session.propose(lease, call_id, plan["certified_loss"](_freeze(artifact)))
            phase = "commit"
            result = session.commit(work_id, agent, verify=verify, abstain_loss=plan["abstain_loss"],
                                    rule=plan.get("rule"), lease_seconds=renew_seconds)
            if result["decision"] == "wait":
                _release(session, lease)
            outcomes.append({"work": work_id, "status": result["decision"],
                             "call_id": result.get("call_id", call_id), "ref": result.get("artifact_ref")})
        except Exception as exc:
            state = _call_status(session, call_id) if call_id is not None else None
            if state == "dispatched":
                status = "unknown"
            elif state == "response_rejected":
                status = "response_rejected"
                try:
                    session.abstain(lease, reason="response_rejected")
                except (StateError, BudgetExceeded):
                    pass
            elif isinstance(exc, LeaseLost):
                status = "lost"
            elif isinstance(exc, BudgetExceeded):
                status = "budget_exhausted"
            else:
                status = phase + "_error"
            _release(session, lease)
            outcomes.append({"work": work_id, "status": status, "call_id": call_id,
                             "call_state": state, "reason": type(exc).__name__})
    return outcomes
