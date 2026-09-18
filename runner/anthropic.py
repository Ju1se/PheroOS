"""Messages API adapter: a frozen request, a strict extractor, exactly one send.

``freeze_request`` turns a validated model configuration and an authorized
conversation into the exact body that will be sent, ``request_digest`` binds that
body to a ledger call, and ``extract`` turns a provider response into a receipt
artifact plus the usage the provider reported. Only the documented subset of the
Messages API is expressible: every other mode is refused, because a silently
dropped or translated field would make the recorded request a different request
from the one the provider answered.

What this module does not claim: reported usage is not a cost (a cache write is
billed above the base input rate, so a token count bounds no bill); a request
field is not an idempotency guarantee, so a failure at or after the send stays
unknown and is never retried; the frozen conversation is checked for shape only,
not for whether a ``tool_result`` answers the ``tool_use`` before it; and the
scripted transport replays recorded bytes without simulating a model.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from . import contracts

API_VERSION = "2023-06-01"
ENDPOINT = "/v1/messages"
SCRIPT_FORMAT = "fake-model-script-v1"
HEADER_PREFIX = "pheroos-orchestration "
HEADER = re.compile(r"^pheroos-orchestration task=(\S+) version=(\d+) step=(\d+)$")
UNSUPPORTED = frozenset({"stream", "thinking", "metadata", "output_config", "service_tier",
                         "container", "cache_control", "top_k", "top_p", "mcp_servers", "betas",
                         "context_management"})
STOP_REASONS = ("end_turn", "max_tokens", "stop_sequence", "tool_use")
TOOL_CHOICES = ("auto", "any", "none", "tool")
LOOPBACK = ("127.0.0.1", "::1", "localhost")
MAX_SYSTEM_BYTES = 65536
MAX_DESCRIPTION_BYTES = 4096
MAX_IDENTIFIER_BYTES = 256
MAX_BODY_BYTES = 1 << 20
MAX_DETAIL = 512
MAX_RESPONSES = 1024


class TransportError(RuntimeError):
    """A send failed at or after dispatch: the call stays unknown and is never retried."""


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _parse(raw):
    return json.loads(raw, object_pairs_hook=_unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def _read(path, limit):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("input exceeds byte bound")
    return raw


def _string(value, name, maximum=None):
    if type(value) is not str or not value:
        raise ValueError(f"{name} must be a nonempty string")
    if maximum is not None and len(value.encode()) > maximum:
        raise ValueError(f"{name} must be at most {maximum} bytes")
    return value


def _tool_name(value, name):
    if type(value) is not str or not contracts.NAME.match(value):
        raise ValueError(f"{name} must match {contracts.NAME.pattern}")
    return value


def _tokens(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be an exact non-negative integer")
    return value


def _exact(value, name, required, optional=()):
    if type(value) is not dict:
        raise ValueError(f"{name} must be an object")
    keys = set(value)
    if not set(required) <= keys or keys - set(required) - set(optional):
        raise ValueError(f"{name} requires exactly {sorted(required)} plus optional {sorted(optional)}")
    return value


def _envelope(value, name, required, optional=()):
    if type(value) is not dict:
        raise ValueError(f"{name} must be an object")
    refused = sorted(set(value) & UNSUPPORTED)
    if refused:
        raise ValueError(f"{name} uses unsupported Messages API fields: " + ", ".join(refused))
    return _exact(value, name, required, optional)


# ---------------------------------------------------------------- request

def _system(value):
    if type(value) is not str or not value.strip() or len(value.encode()) > MAX_SYSTEM_BYTES:
        raise ValueError(f"system must be nonempty text of at most {MAX_SYSTEM_BYTES} bytes")
    return value


def _blocks(value, role, where):
    if type(value) is not list or not value:
        raise ValueError(f"{where} content must be a nonempty list of blocks")
    out = []
    for index, block in enumerate(value):
        name = f"{where}.content[{index}]"
        if type(block) is not dict:
            raise ValueError(f"{name} must be an object")
        kind = block.get("type")
        if kind == "text":
            _envelope(block, name, ("type", "text"))
            out.append({"type": "text", "text": _string(block["text"], f"{name}.text")})
        elif kind == "tool_use":
            if role != "assistant":
                raise ValueError(f"{name}: a tool_use block belongs to an assistant turn")
            _envelope(block, name, ("type", "id", "name", "input"))
            if type(block["input"]) is not dict:
                raise ValueError(f"{name}.input must be an object")
            out.append({"type": "tool_use", "id": _string(block["id"], f"{name}.id", MAX_IDENTIFIER_BYTES),
                        "name": _tool_name(block["name"], f"{name}.name"),
                        "input": contracts.finite_json(block["input"])})
        elif kind == "tool_result":
            if role != "user":
                raise ValueError(f"{name}: a tool_result block belongs to a user turn")
            _envelope(block, name, ("type", "tool_use_id", "content"), ("is_error",))
            result = {"type": "tool_result",
                      "tool_use_id": _string(block["tool_use_id"], f"{name}.tool_use_id", MAX_IDENTIFIER_BYTES),
                      "content": _string(block["content"], f"{name}.content")}
            if "is_error" in block:
                if type(block["is_error"]) is not bool:
                    raise ValueError(f"{name}.is_error must be a bool")
                result["is_error"] = block["is_error"]
            out.append(result)
        else:
            raise ValueError(f"{name}: unsupported block type {kind!r}")
    return out


def _messages(value):
    if type(value) is not list or not value:
        raise ValueError("messages must be a nonempty list")
    out = []
    for index, message in enumerate(value):
        name = f"messages[{index}]"
        _envelope(message, name, ("role", "content"))
        expected = "user" if index % 2 == 0 else "assistant"
        if message["role"] != expected:
            raise ValueError(f"{name} must have role {expected!r}: roles alternate from user")
        out.append({"role": expected, "content": _blocks(message["content"], expected, name)})
    if out[-1]["role"] != "user":
        raise ValueError("the last message must be a user message")
    return out


def _tools(value):
    if type(value) is not list or len(value) > 64:
        raise ValueError("tools must be a bounded list")
    out = []
    for index, tool in enumerate(value):
        name = f"tools[{index}]"
        _envelope(tool, name, ("name", "description", "input_schema"))
        schema = contracts.validate_schema(tool["input_schema"])
        if schema["type"] != "object":
            raise ValueError(f"{name}.input_schema must be an object schema")
        out.append({"name": _tool_name(tool["name"], f"{name}.name"),
                    "description": _string(tool["description"], f"{name}.description", MAX_DESCRIPTION_BYTES),
                    "input_schema": schema})
    names = [tool["name"] for tool in out]
    if len(set(names)) != len(names):
        raise ValueError("tool names must be unique")
    return out


def _tool_choice(value, names):
    if type(value) is not dict:
        raise ValueError("tool_choice must be an object")
    kind = value.get("type")
    if kind not in TOOL_CHOICES:
        raise ValueError("tool_choice type must be one of " + ", ".join(TOOL_CHOICES))
    required = ("type", "name") if kind == "tool" else ("type",)
    _envelope(value, "tool_choice", required, ("disable_parallel_tool_use",))
    out = {"type": kind}
    if kind == "tool":
        out["name"] = _tool_name(value["name"], "tool_choice name")
        if out["name"] not in names:
            raise ValueError("tool_choice names an undeclared tool")
    if "disable_parallel_tool_use" in value:
        if type(value["disable_parallel_tool_use"]) is not bool:
            raise ValueError("disable_parallel_tool_use must be a bool")
        out["disable_parallel_tool_use"] = value["disable_parallel_tool_use"]
    return out


def freeze_request(model, *, system, messages, tools, tool_choice):
    """Return the canonical Messages API body for one authorized model step.

    ``model`` is a ``contracts.model_config`` record; the provider name selects the
    transport, not the wire shape, so ``fake`` and ``anthropic`` freeze identically.
    The result shares no object with any argument in either direction and contains
    only the documented fields; the total request size is bounded by the caller's
    prompt-token contract, not here.
    """
    model = contracts.model_config(model)
    frozen = _tools(tools)
    request = {"model": model["model"], "max_tokens": model["max_new_tokens"],
               "system": _system(system), "messages": _messages(messages), "tools": frozen,
               "tool_choice": _tool_choice(tool_choice, {tool["name"] for tool in frozen})}
    for field in ("temperature", "stop_sequences"):
        if field in model:
            request[field] = model[field]
    return request


def request_digest(request):
    """The digest of the canonical request bytes, which identifies a body, not a call."""
    return contracts.digest(request)


# ---------------------------------------------------------------- response

def _response_blocks(value):
    if type(value) is not list:
        raise ValueError("response content must be a list of blocks")
    out = []
    for index, block in enumerate(value):
        name = f"content[{index}]"
        if type(block) is not dict:
            raise ValueError(f"{name} must be an object")
        kind = block.get("type")
        if kind == "text":
            _exact(block, name, ("type", "text"))
            if type(block["text"]) is not str:
                raise ValueError(f"{name}.text must be a string")
            out.append({"type": "text", "text": block["text"]})
        elif kind == "tool_use":
            _exact(block, name, ("type", "id", "name", "input"))
            if type(block["input"]) is not dict:
                raise ValueError(f"{name}.input must be an object")
            out.append({"type": "tool_use", "id": _string(block["id"], f"{name}.id", MAX_IDENTIFIER_BYTES),
                        "name": _string(block["name"], f"{name}.name", MAX_IDENTIFIER_BYTES),
                        "input": contracts.finite_json(block["input"])})
        else:
            raise ValueError(f"{name}: unsupported response block type {kind!r}")
    return out


REPORTED_TOKENS = ("cache_creation_input_tokens", "cache_read_input_tokens")
REPORTED_DETAIL = ("service_tier", "cache_creation", "server_tool_use")


def _usage(value):
    """Normalize the reported usage: the four token counters plus recorded detail.

    ``REPORTED_DETAIL`` names members the Messages API reports alongside the counters
    that are not prompt tokens. They are copied into the receipt unchanged and never
    added to the prompt sum, so recording them cannot hide usage; a member that is
    neither a known counter nor known detail is still refused, because an ignored
    usage field could hide prompt tokens from the bounded contract.
    """
    _exact(value, "usage", ("input_tokens", "output_tokens"), REPORTED_TOKENS + REPORTED_DETAIL)
    out = {"input_tokens": _tokens(value["input_tokens"], "input_tokens"),
           "output_tokens": _tokens(value["output_tokens"], "output_tokens")}
    for field in REPORTED_TOKENS:
        reported = value.get(field)
        out[field] = 0 if reported is None else _tokens(reported, field)
    for field in REPORTED_DETAIL:
        if field in value:
            out[field] = contracts.finite_json(value[field])
    return out


def extract(raw):
    """Return ``(artifact, prompt_tokens, completion_tokens)`` for a provider response.

    Prompt usage is ``input_tokens`` plus both cache counters, which the provider
    reports separately; the sum is what the provider says it read, not what it
    charges for reading it. An unrecognized field is refused rather than ignored,
    because an ignored usage field could hide prompt tokens from the ledger. Every
    malformation raises ``ValueError``, leaving the caller's call dispatched.
    """
    _exact(raw, "response", ("id", "type", "role", "model", "content", "stop_reason", "usage"),
           ("stop_sequence",))
    if raw["type"] != "message" or raw["role"] != "assistant":
        raise ValueError("response must be an assistant message")
    if raw["stop_reason"] not in STOP_REASONS:
        raise ValueError("stop_reason must be one of " + ", ".join(STOP_REASONS))
    sequence = raw.get("stop_sequence")
    if sequence is not None and type(sequence) is not str:
        raise ValueError("stop_sequence must be a string or null")
    usage = _usage(raw["usage"])
    artifact = {"id": _string(raw["id"], "response id", MAX_IDENTIFIER_BYTES),
                "model": _string(raw["model"], "response model", MAX_IDENTIFIER_BYTES),
                "stop_reason": raw["stop_reason"], "stop_sequence": sequence,
                "content": _response_blocks(raw["content"]), "usage": usage}
    prompt = usage["input_tokens"] + usage["cache_creation_input_tokens"] + usage["cache_read_input_tokens"]
    return contracts.finite_json(artifact), prompt, usage["output_tokens"]


# ---------------------------------------------------------------- transports

def _opener():
    director = urllib.request.OpenerDirector()
    for handler in (urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(),
                    urllib.request.HTTPDefaultErrorHandler(), urllib.request.HTTPErrorProcessor(),
                    urllib.request.UnknownHandler()):
        director.add_handler(handler)
    return director.open


def _base_url(value):
    if type(value) is not str or not value:
        raise ValueError("base_url must be a nonempty string")
    parts = urllib.parse.urlsplit(value)
    if not parts.netloc or parts.path or parts.query or parts.fragment:
        raise ValueError("base_url must be a scheme and host with no path, query or fragment")
    if parts.username or parts.password:
        raise ValueError("base_url must not carry credentials")
    if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in LOOPBACK):
        raise ValueError("base_url must use https unless the host is loopback")
    return value


def _detail(error):
    try:
        raw = error.read(MAX_BODY_BYTES + 1)
        body = _parse(raw) if len(raw) <= MAX_BODY_BYTES else None
    except (OSError, ValueError, AttributeError):
        return ""
    reported = body.get("error") if type(body) is dict else None
    if type(reported) is not dict or type(reported.get("type")) is not str or type(reported.get("message")) is not str:
        return ""
    return f": {reported['type']}: {reported['message'][:MAX_DETAIL]}"


def _decode(response):
    try:
        status = getattr(response, "status", None)
        if status != 200:
            raise TransportError(f"http {status}: unexpected status")
        raw = response.read(MAX_BODY_BYTES + 1)
    except OSError as error:
        raise TransportError("transport failure: " + type(error).__name__) from None
    finally:
        closer = getattr(response, "close", None)
        if callable(closer):
            closer()
    if type(raw) is not bytes or len(raw) > MAX_BODY_BYTES:
        raise TransportError("response body exceeds the byte bound")
    try:
        body = _parse(raw)
    except ValueError:
        raise TransportError("response body is not strict JSON") from None
    if type(body) is not dict:
        raise TransportError("response body must be a JSON object")
    return body


class AnthropicTransport:
    """Send one frozen request to the Messages API and return the decoded body.

    ``api_key`` is a zero-argument callable read at send time: the key reaches the
    request headers and nothing else, so it is on no attribute of this object and in
    no exception message. There is no retry, no redirect following and no proxy: a
    non-200 status, a failure before the body is decoded, or a body that is not one
    strict JSON object raises ``TransportError``, and the caller's call stays
    dispatched because the provider may have answered a request we did not read.
    """

    def __init__(self, *, api_key, base_url="https://api.anthropic.com", timeout=60.0, opener=None):
        if not callable(api_key):
            raise ValueError("api_key must be a zero-argument callable returning the key")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive finite number")
        if opener is not None and not callable(opener):
            raise ValueError("opener must be a urlopen-compatible callable")
        self.api_key = api_key
        self.base_url = _base_url(base_url)
        self.timeout = timeout
        self.opener = _opener() if opener is None else opener

    def __call__(self, request):
        if type(request) is not dict:
            raise ValueError("dictionary request required")
        body = contracts.wire(request).encode()
        key = self.api_key()
        if type(key) is not str or not key:
            raise ValueError("api_key callable must return a nonempty string")
        message = urllib.request.Request(
            self.base_url + ENDPOINT, data=body, method="POST",
            headers={"x-api-key": key, "anthropic-version": API_VERSION,
                     "content-type": "application/json", "accept": "application/json"})
        try:
            response = self.opener(message, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            raise TransportError(f"http {error.code}{_detail(error)}") from None
        except OSError as error:
            raise TransportError("transport failure: " + type(error).__name__) from None
        return _decode(response)


def validate_script(value):
    """Validate a scripted-response file: a canonical record, never a claim about content.

    The ``response`` objects are deliberately not validated here, so a script can
    carry a malformed or bound-violating response for the extractor and the
    accounting contract to reject.
    """
    value = contracts.finite_json(value)
    _exact(value, "script", ("format", "responses"))
    if value["format"] != SCRIPT_FORMAT:
        raise ValueError("unsupported script format")
    responses = value["responses"]
    if type(responses) is not list or len(responses) > MAX_RESPONSES:
        raise ValueError("responses must be a bounded list")
    out, seen = [], set()
    for index, entry in enumerate(responses):
        _exact(entry, f"responses[{index}]", ("task", "step", "response"))
        task = _tool_name(entry["task"], f"responses[{index}].task")
        step = entry["step"]
        if type(step) is not int or step < 0 or step > MAX_RESPONSES:
            raise ValueError(f"responses[{index}].step must be an exact integer >= 0")
        if type(entry["response"]) is not dict:
            raise ValueError(f"responses[{index}].response must be an object")
        if (task, step) in seen:
            raise ValueError("duplicate scripted (task, step)")
        seen.add((task, step))
        out.append({"task": task, "step": step, "response": entry["response"]})
    return {"format": SCRIPT_FORMAT, "responses": out}


def load_script(path):
    """Read a bounded script file with duplicate keys and non-finite constants refused."""
    return validate_script(_parse(_read(path, MAX_BODY_BYTES)))


class FakeTransport:
    """Return the scripted response for the step named in the request's first line.

    Dispatch is by ``(task, step)`` from the request's own header line, so a request
    the script does not cover takes the same unknown-dispatch path as an unreachable
    provider: there is no default response. Replaying recorded bytes is not a model.
    """

    def __init__(self, script, *, calls=None):
        if calls is not None and type(calls) is not list:
            raise ValueError("calls must be a list or None")
        self.script = validate_script(script)
        self.calls = calls

    def __call__(self, request):
        if type(request) is not dict or type(request.get("system")) is not str:
            raise TransportError("request lacks a system header line")
        line = request["system"].split("\n", 1)[0]
        header = HEADER.match(line)
        if not header:
            raise TransportError("first system line is not a " + HEADER_PREFIX.strip() + " header")
        task, step = header.group(1), int(header.group(3))
        matches = [entry for entry in self.script["responses"]
                   if entry["task"] == task and entry["step"] == step]
        if len(matches) != 1:
            raise TransportError(f"script has {len(matches)} responses for task={task} step={step}")
        if self.calls is not None:
            self.calls.append(contracts.finite_json(request))
        return contracts.finite_json(matches[0]["response"])
