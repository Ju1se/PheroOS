"""The bounded step loop: one reference runtime over the orchestration ledger.

Lifecycle per step:

    admit task -> claim -> build authorized context -> freeze request
    -> reserve -> dispatch -> settle receipt -> validate proposal
    -> admit requested transition -> publish output or continue

Every model inference and every tool invocation is one ledger call, reserved and
accounted before it happens. A sweep performs at most ONE such step per task, so a
visible workflow step never hides an unmetered agent loop, and the transports are
configured without retries. State is reconciled from durable receipts and recorded
decisions; this module keeps no state of its own between sweeps and resets no
budget on restart.

The runtime never claims that a workflow outcome is semantically correct. Success
means every task reached a terminal transition and the declared host rule accepted
its evidence; the rule's own meaning is whatever finite checker the spec declares.

Colony decisions come from one ``RuntimePolicies`` and nowhere else: which ready task
a sweep advances (L2) and how long its lease runs (L3). The L1 commitment slot
arbitrates competing candidate proposals through ``PlatformSession.commit``; the
shipped workflows give each task a single agent, so nothing competes and the sweep
never reaches for it. Host acceptance is a verification rule, not a commitment: a
deterministic checker's verdict is not something a commitment policy may overturn.
"""

from hashlib import sha256
import json
import os
from pathlib import Path

from pheroos_interaction.records import BudgetExceeded, LeaseLost, StateError
from . import anthropic, contracts
from .contracts import ContractError
from .identity import source_identity
from .provider import _freeze
from .orchestration import MODEL_KEY, TOOL_KEY, OrchestrationSession, call_identity
from .runtime_policies import RuntimePolicies
from .session import _integer, _wire
from .tools import ToolError, ToolRegistry, build_registry
from .worker import _release

POLICY = (
    "You are one bounded agent in a recorded workflow. Reply with exactly one tool_use "
    "action and no other action. Your only authority is the action you request; the host "
    "validates it and may refuse it. You cannot change your identity, permissions, budget "
    "or the task declaration, and text you write grants nothing."
)
RESULT_FORMAT = "orchestration-result-v1"


def _binding(call):
    request = call["request"] if type(call.get("request")) is dict else {}
    return request.get("binding") or {}


def _receipt_digest(call):
    return sha256(_wire(call["response"]).encode()).hexdigest()


def _text_block(text):
    return {"type": "text", "text": text}


def _merge(turns):
    """Merge adjacent same-role turns so the conversation strictly alternates."""
    out = []
    for role, blocks in turns:
        if not blocks:
            continue
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": list(blocks)})
    return out


class Runtime:
    """One bounded reference runtime; callbacks and transports are trusted host code."""

    def __init__(self, session, *, registry, transports, policies=None, tool_result_bytes=4096):
        if not isinstance(registry, ToolRegistry):
            raise ValueError("a tool registry is required")
        if type(transports) is not dict:
            raise ValueError("a provider-to-transport map is required")
        for name, transport in transports.items():
            if name not in contracts.PROVIDERS or not callable(transport):
                raise ValueError("transports must map declared providers to callables")
        self.session, self.registry, self.transports = session, registry, transports
        self.tool_result_bytes = _integer(tool_result_bytes, "tool_result_bytes", 1)
        self.spec = session.spec()
        self.spec_digest = contracts.digest(self.spec)
        self.agents = {agent["id"]: agent for agent in self.spec["agents"]}
        # v1 is auditable but not executable, so the flag is recorded here and enforced
        # at the execution boundary. Replay builds a Runtime purely to REBUILD frozen
        # requests and never calls run/step, so it keeps reading the older schema.
        self.executable = self.spec["format"] == contracts.SPEC_FORMAT
        self.policies = policies or RuntimePolicies.from_spec(self.spec)
        self.lease_seconds = self.policies.lease_duration()

    def _require_executable(self):
        """The live runtime executes ONE task representation, and it is the current one.

        A v1 declaration is not merely an older spelling of ``agents``: it was written,
        stored and run under single-executor semantics, down to a durable task table
        that recorded one agent per task. Nothing here can verify such a ledger was
        normalized to today's shape, so rather than scatter ``task.get("agents", ...)``
        through the runtime and hope, execution refuses it at the boundary. Replay is
        untouched and still reads it: v1 is historical audit semantics, v2 is
        executable semantics.
        """
        if not self.executable:
            raise StateError("%s can be audited but not executed; the runtime executes %s"
                             % (self.spec["format"], contracts.SPEC_FORMAT))

    # ------------------------------------------------------------ allocation (L2)

    def _select_work(self, stalled=()):
        """Ask the policy plane which (agent, work) PAIR this sweep advances.

        The decision object is the pair, not the work. One task can legally sit in
        several workers' ready queues at once, so the queues are never deduplicated by
        work id: doing that would erase the second worker's legal opportunity, which
        is exactly the thing a shared-capacity workload exists to expose.

        Workers are enumerated in DECLARED order (``contracts.worker_order``), which
        is part of workload identity and frozen in the spec digest, and the first
        whose policy claims wins. A host finalizer is not a worker: it has no model
        configuration, no price and no cheaper alternative, so it takes ready order
        directly rather than a fabricated cost. Each candidate row carries its own
        task's eligible set, so the plane weighs every row against the agents that
        may actually execute THAT row.
        """
        ready = {}
        order = contracts.worker_order(self.spec) + [contracts.HOST_AGENT]
        for agent in order:
            rows = [row for row in self.session.ready_work(agent) if row["id"] not in stalled]
            if not rows:
                continue
            for row in rows:
                row["eligible"] = contracts.eligible_agents(self.session.task(row["id"]))
            ready[agent] = _freeze(rows)
        if not ready:
            return None
        index = len(self.session.snapshot()["calls"])
        for agent in order:
            if agent not in ready:
                continue
            if agent == contracts.HOST_AGENT:
                chosen = self.policies.select_host_work(ready[agent])
            else:
                chosen = self.policies.select_work(
                    ready[agent], {"agent": agent, "spec_digest": self.spec_digest,
                                   "ledger_index": index})
            if chosen is not None:
                return {"agent": agent, "work": chosen}
        return None

    # ------------------------------------------------------------ context

    def _resolver(self, inputs):
        """Resolve only this task's authorized inputs, by artifact reference or producer id.

        A producer id is accepted because a declared workflow names its producers while
        an artifact reference is minted at run time; both resolve to the same authorized
        artifact, and a name that is not an authorized input resolves to nothing.
        """
        view = {}
        for item in inputs:
            record = {key: item[key] for key in ("ref", "work_id", "version", "kind", "value", "digest")}
            view[item["ref"]] = record
            view.setdefault(item["work_id"], record)

        class Resolver:
            def read_artifact(self, ref):
                found = view.get(ref)
                return json.loads(_wire(found)) if found else None
        return Resolver()

    def _brief(self, declaration, inputs, remaining):
        """The user brief; every part is reconstructible from durable rows, so replay can rebuild it."""
        lines = ["Task: " + declaration["id"], "Instructions:", declaration["instructions"]]
        if inputs:
            lines.append("Authorized inputs (read-only, already resolved):")
            for item in inputs:
                lines.append("- producer=%s ref=%s digest=%s value=%s"
                             % (item["work_id"], item["ref"], item["digest"], _wire(item["value"])))
        else:
            lines.append("Authorized inputs: none.")
        lines.append("Remaining budget: " + _wire(remaining))
        lines.append("Submit your answer with submit_output, or abstain with a reason.")
        return "\n".join(lines)

    def _conversation(self, declaration, history, decisions, inputs, remaining, step):
        """Build the frozen conversation from durable receipts only; no hidden state."""
        turns = [("user", [_text_block(self._brief(declaration, inputs, remaining))])]
        by_call = {row["call_id"]: row for row in decisions}
        tools_by_source = {}
        for call in history:
            binding = _binding(call)
            if binding.get("kind") == "tool":
                tools_by_source[binding.get("model_call_id")] = call
        for call in history:
            binding = _binding(call)
            if binding.get("kind") != "model" or binding.get("step", -1) >= step:
                continue
            decision = by_call.get(call["id"])
            if call["state"] == "response_rejected":
                turns.append(("user", [_text_block(
                    "Your previous response was refused: it exceeded the recorded response bound. "
                    "Answer again, more briefly.")]))
                continue
            if call["state"] != "received" or decision is None:
                continue
            content = call["response"][MODEL_KEY]["content"]
            uses = [block for block in content if block.get("type") == "tool_use"]
            turns.append(("assistant", content))
            if decision["decision"] == "tool":
                consumed = tools_by_source.get(call["id"])
                turns.append(("user", [self._tool_result(uses[0]["id"], consumed)]))
            elif decision["decision"] == "decompose":
                # An admitted decomposition answers the propose_children action. Without
                # this the assistant's tool_use would go unanswered and the next request
                # would be a malformed conversation.
                turns.append(("user", [{"type": "tool_result", "tool_use_id": uses[0]["id"],
                                        "content": decision["reason"]}]))
            elif decision["decision"] == "rejected":
                reason = decision["reason"]
                blocks = [{"type": "tool_result", "tool_use_id": use["id"], "content": reason, "is_error": True}
                          for use in uses]
                turns.append(("user", blocks or [_text_block("Your previous action was refused: " + reason)]))
        turns.append(("user", [_text_block("Continue. Reply with exactly one tool_use action.")]))
        return _merge(turns)

    def _tool_result(self, use_id, call):
        if call is None or call["state"] != "received":
            return {"type": "tool_result", "tool_use_id": use_id, "is_error": True,
                    "content": "The tool call did not settle; no result is available."}
        result = call["response"][TOOL_KEY]
        body = _wire(result)
        if len(body.encode()) > self.tool_result_bytes:
            return {"type": "tool_result", "tool_use_id": use_id, "is_error": True,
                    "content": "The tool result exceeded the recorded bound and was not delivered."}
        return {"type": "tool_result", "tool_use_id": use_id, "content": body,
                "is_error": result.get("ok") is False}

    def _offered(self, declaration):
        names = list(declaration["tools"]) + ["submit_output", "abstain"]
        if declaration.get("decomposition"):
            names.append("propose_children")
        return names

    def _tool_schemas(self, declaration):
        schemas = {name: self.registry.schema(name) for name in declaration["tools"]}
        if declaration.get("decomposition"):
            schemas["propose_children"] = contracts.children_schema(
                declaration["decomposition"], declaration["tools"], declaration["decomposition"]["max_children"])
        return schemas

    def _declarations(self, declaration):
        out = [self.registry.declaration(name) for name in declaration["tools"]]
        out.append({"name": "submit_output", "description": "Submit the task's final structured answer.",
                    "input_schema": declaration["output_schema"]})
        out.append({"name": "abstain", "description": "Decline to answer, with a short reason.",
                    "input_schema": contracts.ABSTAIN_SCHEMA})
        if declaration.get("decomposition"):
            out.append({"name": "propose_children",
                        "description": "Propose narrower child tasks; the host validates and may refuse them.",
                        "input_schema": self._tool_schemas(declaration)["propose_children"]})
        return out

    def frozen_model_request(self, declaration, work_id, version, history, decisions, inputs,
                             remaining, step, attempt, spec_digest, claimant):
        """Build the frozen request and its binding from durable state only.

        Every argument is derivable from records with a lower row id than the call
        being reserved, so an offline audit rebuilds exactly this request without a
        transport, a tool or a clock. ``budget`` is added by the caller because it is
        an observation of the platform caps rather than part of the context.
        """
        model = self.agents[claimant]["model"]
        system = ("%stask=%s version=%d step=%d\n%s"
                  % (anthropic.HEADER_PREFIX, work_id, version, step, POLICY))
        request = anthropic.freeze_request(
            model, system=system,
            messages=self._conversation(declaration, history, decisions, inputs, remaining, step),
            tools=self._declarations(declaration), tool_choice={"type": "any", "disable_parallel_tool_use": True})
        tools = [{"name": name, "version": self.registry.version(name) if name in self.registry.names()
                  else "builtin-v1", "schema_digest": contracts.digest(schema)}
                 for name, schema in self._tool_schemas(declaration).items()]
        tools += [{"name": "submit_output", "version": "builtin-v1",
                   "schema_digest": contracts.digest(declaration["output_schema"])},
                  {"name": "abstain", "version": "builtin-v1",
                   "schema_digest": contracts.digest(contracts.ABSTAIN_SCHEMA)}]
        binding = {"kind": "model", "step": step, "attempt": attempt, "spec_digest": spec_digest,
                   "template_version": contracts.TEMPLATE_VERSION, "task_version": version,
                   "agent": claimant, "model_digest": contracts.digest(model),
                   "request_digest": anthropic.request_digest(request),
                   "output_schema_digest": contracts.digest(declaration["output_schema"]),
                   "tools": sorted(tools, key=lambda item: item["name"]),
                   "inputs": [{"producer": item["work_id"], "ref": item["ref"],
                               "digest": item["digest"], "version": item["version"]} for item in inputs],
                   "history": [{"call_id": call["id"], "digest": _receipt_digest(call)}
                               for call in history if call["state"] == "received"],
                   "remaining": remaining,
                   "prompt": {"bound": model["prompt_token_bound"],
                              "overhead": model["prompt_overhead_tokens"]}}
        return request, binding

    # ------------------------------------------------------------ reconciliation

    def _state(self, declaration, history, decisions):
        """Derive the task's position from durable rows; never from remembered state."""
        by_call = {row["call_id"] for row in decisions}
        model, tool, rejected, steps = [], [], 0, set()
        pending = unresolved = abandoned = None
        for call in history:
            binding = _binding(call)
            kind = binding.get("kind")
            if call["state"] == "dispatched":
                unresolved = call
            if kind == "model":
                if call["state"] in ("received", "dispatched", "response_rejected"):
                    model.append(call)
                    steps.add(binding.get("step"))
                if call["state"] == "abandoned":
                    abandoned = call
                if call["state"] in ("received", "response_rejected") and call["id"] not in by_call:
                    pending = call
            elif kind == "tool" and call["state"] in ("received", "dispatched", "response_rejected"):
                tool.append(call)
        for row in decisions:
            rejected += row["decision"] == "rejected"
        limits = declaration["limits"]
        return {"step": (max(steps) + 1) if steps else 0, "pending": pending, "unresolved": unresolved,
                "abandoned": abandoned, "model_calls": len(model), "tool_calls": len(tool),
                "rejections": rejected,
                "remaining": {"model_steps": limits["model_steps"] - len(model),
                              "tool_calls": limits["tool_calls"] - len(tool),
                              "rejections": limits["rejections"] - rejected}}

    def _attempt(self, history, work_id, version, kind, step):
        run_id = self.spec["run_id"]
        states = {call["id"]: call["state"] for call in history}
        attempt = 0
        while states.get(call_identity(run_id, work_id, version, kind, step, attempt)) == "abandoned":
            attempt += 1
        return attempt, call_identity(run_id, work_id, version, kind, step, attempt)

    # ------------------------------------------------------------ one step

    def step(self, work_id, agent=None):
        """Perform at most one bounded step for one task; returns a status record.

        ``agent`` is the eligible agent the allocation policy chose. Where a task
        declares several, which one claims is the allocation decision, so it is passed
        in rather than read back from the declaration.
        """
        self._require_executable()
        session = self.session
        declaration = session.task(work_id)
        eligible = contracts.eligible_agents(declaration)
        if agent is not None and agent not in eligible:
            raise ValueError("the chosen agent is not eligible for this task")
        agent_id = agent or eligible[0]
        if declaration["kind"] == "host":
            try:
                return self._finalize(work_id, declaration)
            except Exception as exc:
                return self._classify(None, work_id, exc)
        lease = session.claim(agent_id, work_id, lease_seconds=self.lease_seconds)
        if lease is None:
            return {"work": work_id, "status": "unavailable"}
        try:
            history = session.work_calls(lease)
            decisions = [row for row in session.decisions(work_id) if row["version"] == lease.version]
            state = self._state(declaration, history, decisions)
            if state["unresolved"] is not None:
                _release(session, lease)
                return {"work": work_id, "status": "blocked_unknown", "call_id": state["unresolved"]["id"]}
            if any(call["state"] == "reserved" for call in history):
                _release(session, lease)
                return {"work": work_id, "status": "reservation_abandoned"}
            if state["pending"] is not None:
                return self._consume(lease, declaration, state, history)
            return self._infer(lease, declaration, state, history, decisions)
        except Exception as exc:
            return self._classify(lease, work_id, exc)
        finally:
            _release(session, lease)

    def _classify(self, lease, work_id, exc):
        """Classify a failed step from the ledger's own state, never from the exception alone."""
        state = None
        try:
            calls = self.session.work_calls(lease) if lease is not None else self.session.work_calls_of(work_id)
            unresolved = [call for call in calls if call["state"] == "dispatched"]
            state = unresolved[0]["id"] if unresolved else None
        except (StateError, LeaseLost):
            pass
        if state is not None:
            return {"work": work_id, "status": "blocked_unknown", "call_id": state}
        if isinstance(exc, LeaseLost):
            return {"work": work_id, "status": "lost", "reason": str(exc)}
        if isinstance(exc, BudgetExceeded):
            return {"work": work_id, "status": "budget_exhausted", "reason": str(exc)}
        return {"work": work_id, "status": "error", "reason": type(exc).__name__ + ": " + str(exc)}

    # ------------------------------------------------------------ inference

    def _infer(self, lease, declaration, state, history, decisions):
        session, work_id = self.session, lease.task_id
        if state["remaining"]["model_steps"] <= 0:
            session.abstain_task(lease, reason="model_step_limit")
            return {"work": work_id, "status": "abstained", "reason": "model_step_limit"}
        budget = session.work_budget(work_id)
        model = self.agents[lease.owner]["model"]
        if budget["calls"] < 1 or budget["tokens"] < model["prompt_token_bound"] + model["max_new_tokens"]:
            raise BudgetExceeded("task budget cannot admit another model step")
        step = state["step"]
        inputs = session.readable_artifacts(work_id, lease.owner, step)
        attempt, call_id = self._attempt(history, work_id, lease.version, "model", step)
        request, binding = self.frozen_model_request(
            declaration, work_id, lease.version, history, decisions, inputs, state["remaining"], step, attempt,
            session.snapshot()["orchestration"]["spec_digest"], lease.owner)
        binding["budget"] = {"calls": budget["calls"], "tokens": budget["tokens"],
                             "calls_cap": budget["calls_cap"], "tokens_cap": budget["tokens_cap"]}
        payload = {"tool_ref": contracts.MODEL_TOOL_REF, "arguments": {"request": request}, "binding": binding}
        declared = len(_wire(request).encode()) + model["prompt_overhead_tokens"]
        if declared > model["prompt_token_bound"]:
            session.abstain_task(lease, reason="prompt_bound_exceeded")
            return {"work": work_id, "status": "abstained", "reason": "prompt_bound_exceeded"}
        existing = next((call for call in history if call["id"] == call_id), None)
        if existing is not None and existing["state"] in ("received", "response_rejected"):
            # Defence in depth: the step index is derived from recorded bindings, so the
            # loop never recomputes an occupied key. A collision means the ledger's own
            # bindings disagree with its rows, which is a corruption, not a new operation.
            stored = {key: value for key, value in existing["request"].items()
                      if key not in ("task_id", "version")}
            if _wire(stored) != _wire(payload):
                raise StateError("the logical operation key is already bound to a different request")
        if model["provider"] not in self.transports:
            raise StateError("no transport is configured for provider " + model["provider"])
        session.reserve_bounded(lease, call_id, "tool.evaluate", payload,
                                prompt_token_bound=model["prompt_token_bound"],
                                max_new_tokens=model["max_new_tokens"])
        dispatched = session.dispatch(lease, call_id)
        raw = self.transports[model["provider"]](dispatched["arguments"]["request"])
        artifact, prompt_tokens, completion_tokens = anthropic.extract(raw)
        if prompt_tokens > model["prompt_token_bound"] or completion_tokens > model["max_new_tokens"]:
            session.record_accounting_violation(
                call_id, {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                          "usage": artifact["usage"]},
                contracts.digest(artifact))
            return {"work": work_id, "status": "blocked_unknown", "call_id": call_id,
                    "reason": "accounting_violation"}
        try:
            session.receive(call_id, {MODEL_KEY: artifact, "tool_ref": contracts.MODEL_TOOL_REF,
                                      "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens})
        except StateError:
            # A response over the artifact bound is settled as response_rejected with its
            # valid usage before receive raises. That is a settled step, not an unknown:
            # the next sweep consumes it as a rejection and tells the model to be briefer.
            if session.call(call_id)["state"] != "response_rejected":
                raise
            return {"work": work_id, "status": "response_rejected", "call_id": call_id, "step": step}
        return {"work": work_id, "status": "inferred", "call_id": call_id, "step": step}

    # ------------------------------------------------------------ consumption

    def _consume(self, lease, declaration, state, history):
        session, work_id = self.session, lease.task_id
        call = state["pending"]
        step = _binding(call).get("step")
        if call["state"] == "response_rejected":
            session.record_rejection(lease, call["id"], "response exceeded the recorded byte bound")
            return {"work": work_id, "status": "rejected", "call_id": call["id"],
                    "reason": "response_bytes_exceeded"}
        try:
            proposal = contracts.parse_proposal(
                call["response"][MODEL_KEY], tools=self._tool_schemas(declaration),
                output_schema=declaration["output_schema"],
                decomposition=(self._tool_schemas(declaration).get("propose_children")))
        except (ContractError, KeyError, TypeError) as exc:
            # A receipt that does not parse is a data failure of this step, not an
            # instruction and not a reason to infer again outside the step budget.
            return self._reject(lease, call, "%s: %s" % (type(exc).__name__, exc))
        if proposal["kind"] == "submit":
            ref = session.publish_derived(
                lease.owner, work_id, kind="output", value=proposal["output"],
                source_call_id=call["id"], lineage=[{"call_id": call["id"], "digest": _receipt_digest(call),
                                                     "role": "proposal"}],
                binding={"step": step, "proposal_digest": contracts.proposal_digest(proposal)},
                lease_seconds=self.lease_seconds)
            return {"work": work_id, "status": "published", "call_id": call["id"], "ref": ref}
        if proposal["kind"] == "abstain":
            session.abstain_task(lease, source_call_id=call["id"], step=step, reason="agent_abstain")
            return {"work": work_id, "status": "abstained", "call_id": call["id"], "reason": "agent_abstain"}
        if proposal["kind"] == "decompose":
            try:
                ids = session.admit_children(lease, call["id"], proposal["children"],
                                             lease_seconds=self.lease_seconds)
            except (ValueError, BudgetExceeded, StateError) as exc:
                # The platform transition refuses a cyclic, duplicate or widening graph
                # with a plain ValueError. That is still a refused proposal, not a crash:
                # recording it consumes the rejection slot and lets the task continue.
                if isinstance(exc, LeaseLost):
                    raise
                return self._reject(lease, call, "decomposition refused: " + str(exc))
            return {"work": work_id, "status": "decomposed", "call_id": call["id"], "children": ids}
        return self._execute_tool(lease, declaration, state, history, call, proposal, step)

    def _reject(self, lease, call, reason):
        try:
            self.session.record_rejection(lease, call["id"], reason[:1024])
        except BudgetExceeded:
            self.session.abstain_task(lease, reason="rejection_limit")
            return {"work": lease.task_id, "status": "abstained", "reason": "rejection_limit"}
        return {"work": lease.task_id, "status": "rejected", "call_id": call["id"], "reason": reason}

    def _execute_tool(self, lease, declaration, state, history, call, proposal, step):
        session, work_id = self.session, lease.task_id
        if state["remaining"]["tool_calls"] <= 0:
            return self._reject(lease, call, "tool call limit exhausted")
        if session.work_budget(work_id)["calls"] < 1:
            raise BudgetExceeded("task call budget cannot admit a tool call")
        inputs = session.readable_artifacts(work_id, lease.owner, step + 1)
        attempt, call_id = self._attempt(history, work_id, lease.version, "tool", step)
        binding = {"kind": "tool", "step": step, "attempt": attempt,
                   "spec_digest": session.snapshot()["orchestration"]["spec_digest"],
                   "task_version": lease.version, "tool": proposal["tool"],
                   "tool_version": self.registry.version(proposal["tool"]),
                   "schema_digest": contracts.digest(self.registry.schema(proposal["tool"])),
                   "arguments_digest": contracts.digest(proposal["arguments"]),
                   "proposal_digest": contracts.proposal_digest(proposal),
                   "model_call_id": call["id"], "receipt_digest": _receipt_digest(call),
                   "inputs": [{"producer": item["work_id"], "ref": item["ref"],
                               "digest": item["digest"], "version": item["version"]} for item in inputs]}
        payload = {"tool_ref": proposal["tool"], "arguments": proposal["arguments"], "binding": binding}
        session.reserve_tool_call(lease, call_id, payload, source_call_id=call["id"], step=step)
        dispatched = session.dispatch(lease, call_id)
        try:
            result = {"ok": True, "value": self.registry.execute(
                proposal["tool"], dispatched["arguments"], self._resolver(inputs))}
        except ToolError as exc:
            result = {"ok": False, "error": str(exc)[:512]}
        session.receive(call_id, {TOOL_KEY: result, "tool_ref": proposal["tool"],
                                  "prompt_tokens": 0, "completion_tokens": 0})
        return {"work": work_id, "status": "tool", "call_id": call_id, "tool": proposal["tool"],
                "ok": result["ok"]}

    # ------------------------------------------------------------ host finalization

    def evaluate_rule(self, work_id, declaration):
        """Apply the declared host rule to ledger evidence; deterministic and side-effect free.

        The candidate reference and its digest come from the ledger, never from model
        output, and the evidence must be a settled receipt of the declared checker
        tool, taken on a dependency of this task, whose recorded ``candidate_digest``
        equals the digest of the resolved candidate artifact. Acceptance means that
        finite checker passed; it is not a claim of semantic correctness.
        """
        session, rule = self.session, declaration["rule"]
        inputs = {item["work_id"]: item for item in session.readable_artifacts(work_id, contracts.HOST_AGENT)}
        candidate, review = inputs.get(rule["candidate"]), inputs.get(rule["review"])
        if candidate is None or review is None:
            return None, None, "rule inputs are unavailable"
        evidence = None
        for call in session.work_calls_of(rule["review"]):
            binding = _binding(call)
            named = call["request"].get("arguments", {}).get("candidate_ref")
            if (binding.get("kind") != "tool" or binding.get("tool") != rule["checker"]
                    or call["state"] != "received"
                    or named not in (candidate["ref"], candidate["work_id"])):
                continue
            result = call["response"][TOOL_KEY]
            if result.get("ok") is not True or result["value"].get("candidate_digest") != candidate["digest"]:
                continue
            evidence = call
        if evidence is None:
            return None, None, "no_checker_evidence"
        checker = evidence["response"][TOOL_KEY]["value"]
        accepted = checker.get("pass") is True
        value = {"format": RESULT_FORMAT, "rule": rule["type"], "accepted": accepted,
                 "candidate": {"ref": candidate["ref"], "digest": candidate["digest"],
                               "work": candidate["work_id"], "value": candidate["value"]},
                 "checker": {"tool": rule["checker"], "version": self.registry.version(rule["checker"]),
                             "call_id": evidence["id"], "result": checker},
                 "review": {"ref": review["ref"], "digest": review["digest"], "value": review["value"]},
                 "decision": {"by": contracts.HOST_AGENT,
                              "reason": "checker pass" if accepted else "checker fail",
                              "spec_digest": session.snapshot()["orchestration"]["spec_digest"]}}
        lineage = [{"call_id": evidence["id"], "digest": _receipt_digest(evidence), "role": "checker"},
                   {"call_id": candidate["call_id"],
                    "digest": sha256(_wire(session.call(candidate["call_id"])["response"]).encode()).hexdigest(),
                    "role": "candidate"}]
        return value, lineage, evidence["id"]

    def _finalize(self, work_id, declaration):
        """Apply the declared verification rule and publish its result.

        This is a truth condition, not a commitment: the declared finite checker's
        verdict on the exact candidate digest decides ``accepted``. No commitment
        policy may overturn it, which is why this path does not go through candidate
        arbitration. Publishing a negative decision is still publishing a result.
        """
        session = self.session
        value, lineage, evidence = self.evaluate_rule(work_id, declaration)
        if value is None:
            if evidence == "rule inputs are unavailable":
                return {"work": work_id, "status": "dependency_failed", "reason": evidence}
            lease = session.claim(contracts.HOST_AGENT, work_id, lease_seconds=self.lease_seconds)
            if lease is None:
                return {"work": work_id, "status": "unavailable"}
            try:
                session.abstain_task(lease, reason=evidence)
            finally:
                _release(session, lease)
            return {"work": work_id, "status": "abstained", "reason": evidence}
        ref = session.publish_derived(contracts.HOST_AGENT, work_id, kind="result", value=value,
                                      source_call_id=evidence, lineage=lineage,
                                      binding={"rule": declaration["rule"]["type"],
                                               "accepted": value["accepted"]},
                                      lease_seconds=self.lease_seconds)
        return {"work": work_id, "status": "published", "ref": ref, "accepted": value["accepted"]}

    # ------------------------------------------------------------ sweep

    def metrics(self):
        snapshot = self.session.snapshot()
        calls = snapshot["calls"]
        kinds = {call["id"]: json.loads(call["request"]).get("binding", {}).get("kind") for call in calls}
        decisions = snapshot["orchestration"]["decisions"]
        accounting = snapshot["orchestration"]["accounting"]
        return {"model_calls": sum(kinds.get(call["id"]) == "model" for call in calls),
                "tool_calls": sum(kinds.get(call["id"]) == "tool" for call in calls),
                "known_tokens": snapshot["actual_tokens"],
                "outstanding_reservations": sum(call["state"] == "reserved" for call in calls),
                "unknown_calls": snapshot["unknown_calls"],
                "unknown_tokens": snapshot["unknown_tokens"],
                "accounting_violations": sum(row["violation"] is not None for row in accounting),
                "proposal_rejections": sum(row["decision"] == "rejected" for row in decisions),
                "decisions": len(decisions),
                # Two different reuse events. A late reconciliation is a previously unknown
                # dispatch settling; a consumed receipt is one the runtime validated and
                # admitted without new inference, which is what a restart reuses.
                "late_reconciliations": sum(event["event_type"] == "interaction.session.reconciled"
                                            for event in snapshot["events"]),
                "consumed_receipts": len(decisions),
                "artifacts": len(snapshot["artifacts"]),
                "blocked_dependencies": len(self.session.blocked_work()),
                "policies": self.policies.describe(len(snapshot["platform"]["decisions"]))}

    def run(self, *, max_sweeps=None):
        """Sweep until no task can take another step; at most one step per task per sweep."""
        self._require_executable()
        if max_sweeps is None:
            budget = len(self.spec["tasks"]) + 2
            for task in self.spec["tasks"]:
                if task["kind"] != "model":
                    continue
                steps = task["limits"]["model_steps"] + task["limits"]["tool_calls"] + 2
                children = task["decomposition"]["max_children"] if task["decomposition"] else 0
                budget += steps * (1 + children)
            max_sweeps = budget
        _integer(max_sweeps, "max_sweeps", 1)
        history, sweeps, stalled, deferred = [], 0, set(), False
        while sweeps < max_sweeps:
            sweeps += 1
            selected = self._select_work(stalled)
            if selected is None:
                # Distinguish "nothing is ready" from "the declared allocation policy
                # refused everything that is". The declaration is a COUNT of cheaper
                # workers, never an identification, so all that can honestly be
                # reported is that nothing claimed - not that nobody exists.
                deferred = any(self.session.ready_work(agent) for agent in
                               list(self.agents) + [contracts.HOST_AGENT])
                break
            record = self.step(selected["work"], selected["agent"])
            record["sweep"] = sweeps
            history.append(record)
            if record["status"] in ("unavailable", "blocked_unknown", "budget_exhausted",
                                    "lost", "error", "dependency_failed"):
                # This task cannot advance; never select it again, and stop when it is
                # the only thing the allocation policy can still hand back.
                stalled.add(selected["work"])
        return self._outcome(history, sweeps, max_sweeps, deferred)

    def _outcome(self, history, sweeps, max_sweeps, deferred=False):
        snapshot = self.session.snapshot()
        # Task status and reference come from the durable ledger, not from this
        # process's step history, so a resumed run reports what actually exists.
        published = {row["work_id"]: row["ref"] for row in snapshot["artifacts"]}
        decided = {row["work_id"] for row in snapshot["platform"]["decisions"]}
        unresolved = {row["work_id"] for row in snapshot["calls"] if row["state"] == "dispatched"}
        stalled = {item["work"]: item["dependency"] for item in self.session.blocked_work()}
        tasks, statuses = {}, []
        for row in snapshot["work"]:
            last = next((item for item in reversed(history) if item["work"] == row["id"]), None)
            reason = (last or {}).get("reason")
            if row["id"] in published:
                status = "published"
            elif row["id"] in decided:
                status = "abstained"
            elif snapshot["run"]["status"] in ("cancelled", "revoked"):
                # Cancellation is the run's terminal state. It does not resolve a
                # dispatched call, which stays unknown and is reported in the metrics.
                status = "cancelled"
            elif row["id"] in unresolved or row["status"] == "uncertain":
                # An unresolved dispatch blocks the work whether or not its lease has
                # expired yet; it is never retried and never silently relabelled.
                status, reason = "blocked_unknown", "a dispatched call is unresolved"
            elif row["id"] in stalled:
                status, reason = "dependency_failed", "dependency %s ended without an artifact" % stalled[row["id"]]
            else:
                status = (last or {}).get("status", "pending")
            tasks[row["id"]] = {"status": status, "reason": reason,
                                "ref": published.get(row["id"], (last or {}).get("ref"))}
            statuses.append(status)
        metrics = dict(self.metrics(), sweeps=sweeps, max_sweeps=max_sweeps)
        if snapshot["run"]["status"] in ("cancelled", "revoked"):
            return contracts.outcome("cancelled", "the run was cancelled", tasks, metrics)
        if "blocked_unknown" in statuses:
            return contracts.outcome("blocked_unknown", "a dispatched call is unresolved and is never retried",
                                     tasks, metrics)
        if "budget_exhausted" in statuses:
            return contracts.outcome("budget_exhausted", "a task could not admit another step", tasks, metrics)
        if stalled:
            return contracts.outcome("dependency_failed",
                                     "a dependency ended without an artifact: " + _wire(stalled), tasks, metrics)
        if any(item["status"] == "error" for item in history):
            return contracts.outcome("error", "a step failed; see the task records", tasks, metrics)
        if deferred:
            return contracts.outcome(
                "error", "the allocation policy deferred every ready task and no declared "
                         "cheaper capacity produced progress", tasks, metrics)
        if "pending" in statuses:
            return contracts.outcome("error", "a task made no progress within the sweep bound", tasks, metrics)
        if "abstained" in statuses:
            return contracts.outcome("abstained", "a task ended without publishing an artifact", tasks, metrics)
        rejected = [row["work_id"] for row in snapshot["artifacts"]
                    if json.loads(row["value"]).get("format") == RESULT_FORMAT
                    and json.loads(row["value"]).get("accepted") is False]
        if rejected:
            # Every task is terminal and every artifact published, but the declared
            # acceptance rule rejected the candidate. Reporting that as success would
            # be a false success.
            return contracts.outcome("rejected", "a declared acceptance rule rejected its candidate: "
                                     + ", ".join(rejected), tasks, metrics)
        return contracts.outcome("success", "every task published its declared artifact", tasks, metrics)


def run_workflow(session, *, registry, transports, policies=None, max_sweeps=None):
    """Run one bounded workflow to a terminal outcome and return the outcome record."""
    return Runtime(session, registry=registry, transports=transports,
                   policies=policies).run(max_sweeps=max_sweeps)


# ---------------------------------------------------------------- host entry points

FROZEN = "orchestration-run-v1"


def _read(path, limit=1 << 20):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("input exceeds byte bound")
    return raw


def _load(path, limit=1 << 20):
    return json.loads(_read(path, limit), object_pairs_hook=_unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON field")
        out[key] = value
    return out


def _save(path, value):
    with Path(path).open("xb") as stream:
        stream.write(_wire(value).encode() + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    handle = os.open(Path(path).parent, os.O_RDONLY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)


def build_transports(spec, *, script=None, api_key=None, base_url=None):
    """Build only the transports the spec's agents declare.

    A provider transport is built only when an agent declares that provider. The
    Anthropic transport additionally requires ``PHEROOS_PROVIDER=1`` and a key in
    ``ANTHROPIC_API_KEY``: the flag records that the host configured a real service,
    and it is not an authorization to spend money. No transport is created for a
    provider no agent declares, so an offline run never builds a network client.
    """
    providers = {agent["model"]["provider"] for agent in spec["agents"]}
    transports = {}
    if "fake" in providers:
        if script is None:
            raise ValueError("the workflow declares the fake provider but no script was supplied")
        transports["fake"] = anthropic.FakeTransport(script)
    if "anthropic" in providers:
        if os.environ.get("PHEROOS_PROVIDER") != "1":
            raise StateError("provider calls are disabled; set PHEROOS_PROVIDER=1 to enable the adapter")
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise StateError("the Anthropic adapter needs a key in ANTHROPIC_API_KEY")
        url = base_url or os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
        transports["anthropic"] = anthropic.AnthropicTransport(api_key=lambda: key, base_url=url)
    return transports


def _executable(spec):
    """Only the current schema may EXECUTE; the previous one remains auditable.

    A v1 declaration is not merely an older spelling of ``agents``. It was written,
    stored and run under single-executor semantics, down to the durable task table
    that recorded one agent per task. Nothing here can know that such a ledger was
    normalized to today's shape, so rather than scatter ``task.get("agents", ...)``
    through the runtime and hope, execution refuses it outright. Offline replay still
    reads it: v1 is historical audit semantics, v2 is executable semantics.
    """
    if spec["format"] != contracts.SPEC_FORMAT:
        raise ValueError("%s can be audited but not executed; the runtime executes %s"
                         % (spec["format"], contracts.SPEC_FORMAT))
    return spec


def start_run(workflow_path, output_dir, *, script_path=None, max_sweeps=None):
    """Freeze the workflow into a new output directory, then run it to a terminal outcome."""
    workflow_path, output_dir = Path(workflow_path), Path(output_dir)
    spec = _executable(contracts.workflow_spec(_load(workflow_path)))
    script = anthropic.load_script(script_path) if script_path else None
    output_dir.mkdir(parents=True, exist_ok=False)
    frozen = {"format": FROZEN, "spec": spec, "spec_digest": contracts.digest(spec),
              "spec_dir": str(workflow_path.resolve().parent),
              "script_digest": contracts.digest(script) if script else None,
              "source_identity": source_identity()}
    _save(output_dir / "frozen.json", frozen)
    session = OrchestrationSession.create(output_dir / "session.sqlite", spec=spec)
    registry = build_registry(spec, workflow_path.resolve().parent)
    outcome = Runtime(session, registry=registry,
                      transports=build_transports(spec, script=script)).run(max_sweeps=max_sweeps)
    _save(output_dir / "outcome.json", outcome)
    return outcome


def resume_run(output_dir, *, script_path=None, max_sweeps=None):
    """Continue only the legally executable unfinished work of a recorded run.

    Resume re-opens the same ledger: budgets are not reset, an unresolved dispatch
    stays unresolved and is never re-sent, and a settled receipt is consumed rather
    than repeated. It is not a replay and not a new experiment.
    """
    output_dir = Path(output_dir)
    frozen = _load(output_dir / "frozen.json")
    if frozen.get("format") != FROZEN:
        raise ValueError("unsupported run record")
    spec = _executable(contracts.workflow_spec(frozen["spec"]))
    if contracts.digest(spec) != frozen["spec_digest"]:
        raise ValueError("frozen workflow digest mismatch")
    script = anthropic.load_script(script_path) if script_path else None
    if frozen["script_digest"] is not None and (script is None or contracts.digest(script) != frozen["script_digest"]):
        raise ValueError("the resumed run was recorded with a different model script")
    session = OrchestrationSession(output_dir / "session.sqlite")
    recorded = session.snapshot()["orchestration"]["spec_digest"]
    if recorded != frozen["spec_digest"]:
        raise ValueError("the frozen record does not describe this ledger: spec digest %s vs %s"
                         % (frozen["spec_digest"], recorded))
    registry = build_registry(spec, Path(frozen["spec_dir"]))
    outcome = Runtime(session, registry=registry,
                      transports=build_transports(spec, script=script)).run(max_sweeps=max_sweeps)
    index = 1
    while (output_dir / ("outcome-resume-%d.json" % index)).exists():
        index += 1
    _save(output_dir / ("outcome-resume-%d.json" % index), outcome)
    return outcome
