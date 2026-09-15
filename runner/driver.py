"""Concrete local dispatch extracted from runtime/session_driver_v1.py (MIT).

No provider import, model loading or old authority adapter. Model/tool registries
are explicit and the Session checks each current lease and declared action.
"""

from __future__ import annotations

import json
from hashlib import sha256
from time import monotonic_ns
from pheroos_interaction.ports import ModelAdapter


def _copy(value):
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


class SessionDriver:
    """Concrete model/tool dispatch for a declared session work item.

    Registry keys identify available adapters, not permissions. Session checks
    the work/lease/action and current local permissions again at actual dispatch.
    An exception after dispatch retains the reservation as unknown; this driver
    never retries it. Committed receipt replay is explicit and has no authority.
    """

    def __init__(self, session, *, models: dict[str, ModelAdapter] | None = None, tools=None,
                 context_tokens=2048):
        if type(context_tokens) is not int or context_tokens < 1:
            raise ValueError("positive context bound required")
        self.session = session
        self.models, self.tools = dict(models or {}), dict(tools or {})
        self.context_tokens = context_tokens

    def generate(self, lease, call_id, model_ref, messages, *, max_new_tokens, seed):
        model = self.models[model_ref]
        messages = _copy(messages)
        prompt_tokens = model.count_tokens(messages)
        if (type(prompt_tokens) is not int or prompt_tokens < 1
                or type(max_new_tokens) is not int or max_new_tokens < 1
                or type(seed) is not int or seed < 0):
            raise ValueError("invalid generation bounds")
        if prompt_tokens + max_new_tokens > self.context_tokens:
            raise ValueError("model context bound exceeded")
        payload = {"task_id": lease.task_id, "version": lease.version,
                   "model_ref": model_ref, "model_identity": _copy(model.identity),
                   "messages": messages, "max_new_tokens": max_new_tokens, "seed": seed}
        remote_bound = payload["model_identity"].get("token_reservation_contract") == "remote_input_upper_bound_v1"
        if remote_bound:
            run_id = self.session.snapshot()["run"]["run_id"]
            adapter_call_id = sha256(json.dumps(["interaction-v1", run_id, call_id],
                separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
            payload["adapter_call_id"] = adapter_call_id
        self.session.reserve(lease, call_id, "model.generate", payload,
                             prompt_tokens=prompt_tokens, max_new_tokens=max_new_tokens,
                             prompt_token_contract="upper_bound_v1" if remote_bound else "exact_v1")
        self.session.dispatch(lease, call_id)
        started = monotonic_ns()
        if remote_bound:
            response = _copy(model.generate(messages, max_new_tokens, seed, call_id=adapter_call_id))
        else:
            response = _copy(model.generate(messages, max_new_tokens, seed))
        response["model_ref"] = model_ref
        response["adapter_elapsed_ns"] = monotonic_ns() - started
        self.session.receive(call_id, response)
        return response

    def evaluate(self, lease, call_id, tool_ref, arguments):
        tool = self.tools[tool_ref]
        arguments = _copy(arguments)
        payload = {"task_id": lease.task_id, "version": lease.version,
                   "tool_ref": tool_ref, "arguments": arguments}
        self.session.reserve(lease, call_id, "tool.evaluate", payload,
                             prompt_tokens=0, max_new_tokens=0)
        self.session.dispatch(lease, call_id)
        started = monotonic_ns()
        artifact = _copy(tool(arguments))
        response = {"artifact": artifact, "tool_ref": tool_ref,
                    "prompt_tokens": 0, "completion_tokens": 0,
                    "adapter_elapsed_ns": monotonic_ns() - started}
        self.session.receive(call_id, response)
        return response

    def replay(self, call_id):
        """Retrieve a settled receipt without executing, charging, or authorizing."""
        record = self.session.call(call_id)
        if record["state"] != "received":
            raise ValueError("unresolved call cannot be replayed or redispatched")
        return _copy(record["response"])
