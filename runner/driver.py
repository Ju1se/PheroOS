"""Declared local tool dispatch with durable reservations and no retries."""

from __future__ import annotations

import json
from time import monotonic_ns


def _copy(value):
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


class SessionDriver:
    """Concrete local tool dispatch for a declared session work item.

    Registry keys identify available tools, not permissions. Session checks
    the work/lease/action and current local permissions again at actual dispatch.
    An exception after dispatch retains the reservation as unknown; this driver
    never retries it. Committed receipt replay is explicit and has no authority.
    """

    def __init__(self, session, *, tools=None):
        self.session = session
        self.tools = dict(tools or {})

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
