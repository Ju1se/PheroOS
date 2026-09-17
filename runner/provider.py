"""Opt-in transport adapter; dispatch failures remain unknown and are never retried.

There is no configured provider, credential lookup, network transport or CLI here.
The caller supplies an authorized transport and an extractor. A request field is
not an idempotency guarantee: this adapter sends a reserved call at most once.
"""

from __future__ import annotations

import json
import math
import os
from time import monotonic_ns

from pheroos_interaction.records import StateError
from .session import _id, _integer


def _freeze(value):
    """Copy a finite JSON value without silently coercing dictionary keys."""
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError("JSON object keys must be strings")
        for item in value.values():
            _freeze(item)
    elif type(value) is list:
        for item in value:
            _freeze(item)
    elif type(value) is float:
        if not math.isfinite(value):
            raise ValueError("finite JSON numbers required")
    elif value is not None and type(value) not in (str, int, bool):
        raise ValueError("JSON values required")
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))


class ProviderDriver:
    """Reserve, dispatch, invoke once, then settle exact token usage.

    ``extract(response)`` returns ``(artifact_dict, prompt_tokens, completion_tokens)``.
    The provider request must use ``max_tokens`` as its completion bound; the
    adapter adds that field before freezing and rejects a conflicting value.
    Exact prompt usage must equal the caller's declaration. Invalid extraction,
    usage or transport exceptions after dispatch leave the call ``dispatched``.
    A byte-rejected receipt is different: Session settles its valid usage as
    ``response_rejected`` before raising. Inspect the ledger to distinguish them.
    """

    def __init__(self, session, *, transport, extract, tool_ref="provider.chat", enabled=None):
        if enabled is not None and type(enabled) is not bool:
            raise ValueError("enabled must be a bool or None")
        if not callable(transport) or not callable(extract):
            raise ValueError("callable transport and extract required")
        self.session, self.transport, self.extract = session, transport, extract
        self.tool_ref = _id(tool_ref)
        self.enabled = os.environ.get("PHEROOS_PROVIDER") == "1" if enabled is None else enabled

    def evaluate(self, lease, call_id, request, *, prompt_tokens, max_new_tokens):
        if not self.enabled:
            raise StateError("provider calls are disabled")
        _integer(prompt_tokens, "prompt_tokens")
        _integer(max_new_tokens, "max_new_tokens")
        if type(request) is not dict:
            raise ValueError("dictionary provider request required")
        outbound = _freeze(request)
        if "max_tokens" in outbound and (type(outbound["max_tokens"]) is not int
                                            or outbound["max_tokens"] != max_new_tokens):
            raise ValueError("request max_tokens must equal the reserved completion bound")
        outbound["max_tokens"] = max_new_tokens
        payload = {"task_id": lease.task_id, "version": lease.version,
                   "tool_ref": self.tool_ref, "arguments": {"request": outbound}}
        self.session.reserve(lease, call_id, "tool.evaluate", payload,
                             prompt_tokens=prompt_tokens, max_new_tokens=max_new_tokens)
        # Dispatch returns the durable request. The outbound body is a fresh
        # decode of exactly that request, never the mutable caller's object.
        dispatched = self.session.dispatch(lease, call_id)
        started = monotonic_ns()
        raw = self.transport(dispatched["arguments"]["request"])
        extracted = self.extract(raw)
        if type(extracted) not in (tuple, list) or len(extracted) != 3:
            raise ValueError("extract must return artifact, prompt_tokens, completion_tokens")
        artifact, used_prompt, used_completion = extracted
        if type(artifact) is not dict:
            raise ValueError("extracted artifact must be a dictionary")
        _integer(used_prompt, "provider prompt_tokens")
        _integer(used_completion, "provider completion_tokens")
        if used_prompt != prompt_tokens or used_completion > max_new_tokens:
            raise StateError("provider usage violates the exact reserved token contract")
        response = {"artifact": _freeze(artifact), "tool_ref": self.tool_ref,
                    "prompt_tokens": used_prompt, "completion_tokens": used_completion,
                    "adapter_elapsed_ns": monotonic_ns() - started}
        self.session.receive(call_id, response)
        return response

    def replay(self, call_id):
        """Return a settled receipt without transport, charging or authority."""
        record = self.session.call(call_id)
        if record["state"] != "received":
            raise StateError("replay requires a settled, accepted receipt")
        return _freeze(record["response"])
