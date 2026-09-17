"""Colony agent layer: one bounded sweep composing the frozen tree walk (L0), a
commitment rule (L1), a claim policy (L2) and a lease TTL (L3) over a
PlatformSession-compatible session.

The tree is planned and frozen before the first receipt; every read at depth d
carries the tree digest in its arguments and a call id derived from
(work, version, tree digest, depth), so receipts bind to the plan and survive
re-claims. Recovery comes first: existing candidates go straight to commit even
when the planner declines to buy, a matching settled receipt is reused instead
of read again, and a settled receipt that does not match the plan refuses
another read. An unknown dispatch stays unknown and is never retried; a
rejected response for the work forbids buying another read but does not disturb
a complete matching history; an unknown observation terminates as abstention
without replanning; a root stop with no read is a terminal abstention labelled
``plan_stop:<action>`` because no receipt exists to publish. A reservation
abandoned before dispatch (a pre-dispatch expiry or crash: nothing was sent) is
a known non-dispatch, not an unknown: the abandoned id is never reused and the
next attempt at that depth takes the id of attempt n, where n counts the
abandoned attempts already in the ledger, so the work is re-queued as the L3
false-expiry model assumes; abandoned rows count against the work's call cap,
which bounds the attempts. A tree whose worst-case remaining read count
exceeds the work's remaining calls is refused before anything is bought.

Nothing here is an LLM, sends a message, retries a call, or claims statistical
optimality: the tree bounds expected loss only within the declared family and
box, the certified loss is the leaf's conditional expected loss under that
declaration and is never calibrated here, the commitment rule is a declared
local choice among candidate metadata, the claim policy is a heuristic and the
lease TTL bounds no stall time. Callbacks are trusted local code.
"""

from __future__ import annotations

from hashlib import sha256

from pheroos_interaction.records import BudgetExceeded, LeaseLost, StateError
from pheroos_interaction.sequential import SequentialPlan, apply_sequential, tree_digest
from .provider import _freeze
from .session import _duration, _integer, _wire
from .worker import _call_status, _release

BOUND_KEYS = ("tree_sha256", "depth")


def _query_depths(node):
    if not node.query:
        return ()
    return (node.depth,) + tuple(depth for child in node.children for depth in _query_depths(child))


def _leaf(node, outcomes):
    for outcome in outcomes:
        if not node.query:
            break
        node = node.children[int(outcome)]
    return node


def _call_id(work_id, version, tree_sha, depth, attempt=0):
    """Attempt 0 is ``colony:sha256(wire([work, version, tree, depth]))``; attempt n appends n."""
    key = [work_id, version, tree_sha, depth] + ([attempt] if attempt else [])
    return "colony:" + sha256(_wire(key).encode()).hexdigest()


def _plan(value):
    required = {"plan", "reads", "outcome", "abstain_loss"}
    if type(value) is not dict or set(value) - required - {"rule", "purchase"}:
        raise ValueError("colony plan requires plan, reads, outcome and abstain_loss")
    if type(value.get("purchase", True)) is not bool:
        raise ValueError("purchase must be a bool")
    if value.get("rule") is not None and not callable(value["rule"]):
        raise ValueError("rule must be callable")
    from .platform import _loss
    if value.get("purchase") is False:
        declined = {"purchase": False}
        if "abstain_loss" in value:
            declined["abstain_loss"] = _loss(value["abstain_loss"], "abstain_loss")
        if value.get("rule") is not None:
            declined["rule"] = value["rule"]
        return declined
    if not required <= value.keys():
        raise ValueError("read plan requires plan, reads, outcome and abstain_loss")
    plan = value["plan"]
    if not isinstance(plan, SequentialPlan):
        raise ValueError("a validated SequentialPlan is required")
    reads = value["reads"]
    if type(reads) is not list or any(type(read) is not dict or set(read) != {"tool_ref", "arguments"}
                                      for read in reads):
        raise ValueError("reads must be a list of {tool_ref, arguments} dictionaries")
    frozen = []
    for read in reads:
        if type(read["tool_ref"]) is not str or not read["tool_ref"].strip():
            raise ValueError("nonempty tool_ref required")
        if type(read["arguments"]) is not dict or set(read["arguments"]) & set(BOUND_KEYS):
            raise ValueError("dictionary arguments without the runner-bound keys required")
        frozen.append({"tool_ref": read["tool_ref"], "arguments": _freeze(read["arguments"])})
    if len({(read["tool_ref"], _wire(read["arguments"])) for read in frozen}) != len(frozen):
        raise ValueError("each depth must declare a distinct source")
    if len(frozen) <= max(_query_depths(plan.tree), default=-1):
        raise ValueError("one declared read per query depth of the tree required")
    if not callable(value["outcome"]):
        raise ValueError("outcome callback required")
    return {**value, "reads": frozen, "abstain_loss": _loss(value["abstain_loss"], "abstain_loss")}


def run_colony(session, agent, *, driver, planner, verify, policy, rule=None, lease_seconds=60,
               wait_hold_seconds=None, max_items=None):
    """Run one bounded sweep, visiting a work identity at most once.

    ``policy(frozen_ready_rows)`` chooses work (L2). ``planner(item)`` returns
    ``{'purchase': False}`` or ``plan`` (a frozen SequentialPlan), ``reads`` (one
    ``{tool_ref, arguments}`` per query depth, each a DISTINCT declared source;
    the runner binds ``tree_sha256`` and ``depth`` into the arguments),
    ``outcome(artifact)`` returning exactly True, False or None (unknown),
    ``abstain_loss`` and an optional commit ``rule`` overriding ``rule`` (L1).
    Existing candidates are committed before a purchase decision is honoured, so
    a purchase-False plan may carry ``abstain_loss`` (and ``rule``) for that
    commit; without one, candidates make it a plan error and nothing changes.
    ``lease_seconds`` (L3, e.g. ``lease_ttl(...)['ttl']``) is used at claim and
    renewed before every read; a ``wait`` from commit releases the lease and,
    only when ``wait_hold_seconds`` is set, records a no-entry scheduling hint.

    The call id of depth d is ``colony:sha256(wire([work, version, tree, d]))``,
    stable across re-claims. A reservation abandoned under it before dispatch
    is a known non-dispatch: the next attempt at that depth uses attempt n
    (``[..., d, n]``, n = abandoned attempts in the ledger), never the abandoned
    id; every attempt counts against the work's call cap. Before a fresh read
    the worst-case remaining read count of the tree is compared with
    ``item['remaining']['calls']`` and a shortfall raises BudgetExceeded without
    buying anything (``choose_horizon`` picks a K within the cap). The certified
    loss proposed with the last receipt is the leaf's conditional expected loss
    ``stop_risk / (mass_h + mass_n)``; a zero mass abstains. This is a
    declaration for the commit rule, not a calibrated probability.
    """
    _duration(lease_seconds)
    if wait_hold_seconds is not None:
        _duration(wait_hold_seconds)
    for callback in (planner, verify, policy):
        if not callable(callback):
            raise ValueError("callable planner, verifier and policy required")
    if rule is not None and not callable(rule):
        raise ValueError("rule must be callable")
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
        lease = session.claim(agent, work_id, lease_seconds=lease_seconds)
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
            phase = "commit"
            candidates = session.candidates(work_id, agent=agent)
            if plan.get("purchase") is False:
                if not candidates:
                    session.abstain(lease, reason="plan_no_purchase")
                    outcomes.append({"work": work_id, "status": "abstain", "call_id": None,
                                     "reason": "plan_no_purchase"})
                    continue
                if "abstain_loss" not in plan:
                    phase = "plan"
                    raise ValueError("candidates exist; a purchase-False plan must declare abstain_loss to commit them")
            if not candidates:
                tree_sha = tree_digest(plan["plan"])
                received = [row for row in records if row["state"] == "received"]
                states = {row["id"]: row["state"] for row in records}
                reused, observed, bought, reason = set(), [], 0, None
                while True:
                    step, value = apply_sequential(plan["plan"], observed)
                    if step == "stop":
                        break
                    phase = "commit"
                    read = plan["reads"][value]
                    arguments = {**read["arguments"], "tree_sha256": tree_sha, "depth": value}
                    matching = [row for row in received
                                if row["request"].get("tool_ref") == read["tool_ref"]
                                and _wire(row["request"].get("arguments")) == _wire(arguments)]
                    if matching:
                        call_id = matching[-1]["id"]
                        reused.add(call_id)
                        response = matching[-1]["response"]
                    else:
                        if any(row["id"] not in reused for row in received):
                            raise StateError("existing receipt does not match this read plan; another read is refused")
                        if "response_rejected" in states.values():
                            # A rejected response for this work forbids buying again (run_worker parity).
                            reason = "response_rejected"
                            break
                        node = _leaf(plan["plan"].tree, observed)
                        needed = max(_query_depths(node)) - node.depth + 1
                        remaining = item.get("remaining", {}).get("calls")
                        if type(remaining) is int and needed > remaining - bought:
                            raise BudgetExceeded("the tree needs up to %d more reads but the work has %d calls left"
                                                 % (needed, remaining - bought))
                        phase = "read"
                        attempt = 0
                        while states.get(_call_id(work_id, lease.version, tree_sha, value, attempt)) == "abandoned":
                            attempt += 1
                        call_id = _call_id(work_id, lease.version, tree_sha, value, attempt)
                        if call_id in states:
                            raise StateError("call id already used in a state this walk cannot reuse")
                        session.renew(lease, lease_seconds)
                        bought += 1
                        response = driver.evaluate(lease, call_id, read["tool_ref"], arguments)
                    phase = "decision"
                    outcome = plan["outcome"](_freeze(response["artifact"]))
                    if outcome is not None and type(outcome) is not bool:
                        raise ValueError("outcome must return True, False or None")
                    observed.append(outcome)
                if reason is None:
                    action = value
                    if observed and observed[-1] is None:
                        reason = "unknown_outcome"
                    elif action == "abstain" or not observed:
                        reason = "plan_stop:" + action
                    else:
                        leaf = _leaf(plan["plan"].tree, observed)
                        mass = leaf.mass_h + leaf.mass_n
                        reason = None if mass > 0 else "zero_mass"
                if reason is not None:
                    session.abstain(lease, reason=reason)
                    outcomes.append({"work": work_id, "status": "abstain", "call_id": call_id,
                                     "reason": reason})
                    continue
                session.propose(lease, call_id, leaf.stop_risk / mass)
            phase = "commit"
            result = session.commit(work_id, agent, verify=verify, abstain_loss=plan["abstain_loss"],
                                    rule=plan["rule"] if "rule" in plan else rule,
                                    lease_seconds=lease_seconds)
            record = {"work": work_id, "status": result["decision"],
                      "call_id": result.get("call_id", call_id), "ref": result.get("artifact_ref")}
            if result["decision"] == "wait":
                _release(session, lease)
                if wait_hold_seconds is not None:
                    try:
                        session.mark_no_entry(work_id, session.clock() + wait_hold_seconds, "commitment wait")
                        record["held"] = True
                    except (StateError, BudgetExceeded):
                        # A scheduling hint at the control cap changes no decision.
                        record["held"] = False
            outcomes.append(record)
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
