"""Messages API adapter conformance: frozen requests, strict extraction, one send.

Every send in this module goes to an injected opener or to an in-process loopback
server; no test reaches a provider and no test carries a real credential.
"""

import io
import json
import socket
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
import urllib.error
import urllib.request

import pytest

from pheroos_interaction.runner import anthropic, contracts

KEY = "test-key-value-not-a-credential"
MODEL = {"provider": "fake", "model": "fake-model", "max_new_tokens": 512,
         "prompt_token_bound": 8192, "prompt_overhead_tokens": 600}
SYSTEM = anthropic.HEADER_PREFIX + "task=producer version=1 step=0\n\nProduce the category totals."
TOTALS_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["totals", "total_cents"],
    "properties": {
        "totals": {"type": "array", "maxItems": 64,
                   "items": {"type": "object", "additionalProperties": False,
                             "required": ["category", "cents"],
                             "properties": {"category": {"type": "string", "maxLength": 32, "minLength": 1},
                                            "cents": {"type": "integer", "minimum": 0}}}},
        "total_cents": {"type": "integer", "minimum": 0}}}
READ_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["fixture"],
               "properties": {"fixture": {"type": "string", "maxLength": 64, "minLength": 1}}}


def text(body):
    return {"type": "text", "text": body}


def use(identifier, name="fixture.read", arguments=None):
    return {"type": "tool_use", "id": identifier, "name": name,
            "input": {"fixture": "orders"} if arguments is None else arguments}


def result(identifier, body='{"rows":1}'):
    return {"type": "tool_result", "tool_use_id": identifier, "content": body, "is_error": False}


def message(role, *blocks):
    return {"role": role, "content": list(blocks)}


def conversation():
    return [message("user", text("Compute the category totals.")),
            message("assistant", text("Reading the fixture."), use("toolu_1")),
            message("user", result("toolu_1"))]


def tools():
    return [{"name": "fixture.read", "description": "Read a declared fixture.", "input_schema": READ_SCHEMA},
            {"name": "submit_output", "description": "Submit the task output.", "input_schema": TOTALS_SCHEMA}]


def freeze(**changes):
    arguments = {"system": SYSTEM, "messages": conversation(), "tools": tools(),
                 "tool_choice": {"type": "any"}}
    model = changes.pop("model", MODEL)
    arguments.update(changes)
    return anthropic.freeze_request(model, **arguments)


def response(**changes):
    raw = {"id": "msg_01", "type": "message", "role": "assistant", "model": "fake-model",
           "content": [text("Here are the totals."),
                       use("toolu_2", "submit_output",
                           {"totals": [{"category": "book", "cents": 500}], "total_cents": 500})],
           "stop_reason": "tool_use", "usage": {"input_tokens": 120, "output_tokens": 30}}
    raw.update(changes)
    return raw


class Key:
    def __init__(self, value=KEY):
        self.value, self.calls = value, 0

    def __call__(self):
        self.calls += 1
        return self.value


class Body:
    def __init__(self, payload, status=200):
        self.status = status
        self.payload = payload if type(payload) is bytes else payload.encode()
        self.closed = False

    def read(self, amount=None):
        return self.payload if amount is None else self.payload[:amount]

    def close(self):
        self.closed = True


class Opener:
    def __init__(self, outcome=None):
        self.outcome, self.requests, self.timeouts = outcome, [], []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        self.timeouts.append(timeout)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def transport(outcome=None, **changes):
    opener = Opener(outcome)
    key = Key()
    options = {"api_key": key, "opener": opener}
    options.update(changes)
    return anthropic.AnthropicTransport(**options), opener, key


def serve(payload, status=200, extra=None):
    received = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            length = int(self.headers.get("content-length", "0"))
            received.append({"path": self.path, "body": self.rfile.read(length),
                             "headers": {name.lower(): value for name, value in self.headers.items()}})
            body = payload if type(payload) is bytes else payload.encode()
            self.send_response(status)
            for name, value in (extra or {}).items():
                self.send_header(name, value)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, received


def loopback_transport(server, **changes):
    return anthropic.AnthropicTransport(api_key=Key(), timeout=5.0,
                                        base_url="http://127.0.0.1:%d" % server.server_address[1], **changes)


# ---------------------------------------------------------------- freeze_request

def test_freeze_request_freezes_a_two_turn_tool_conversation():
    request = freeze()
    assert request == {
        "model": "fake-model", "max_tokens": 512, "system": SYSTEM,
        "messages": [{"role": "user", "content": [{"type": "text", "text": "Compute the category totals."}]},
                     {"role": "assistant", "content": [{"type": "text", "text": "Reading the fixture."},
                                                       {"type": "tool_use", "id": "toolu_1",
                                                        "name": "fixture.read",
                                                        "input": {"fixture": "orders"}}]},
                     {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_1",
                                                   "content": '{"rows":1}', "is_error": False}]}],
        "tools": [{"name": "fixture.read", "description": "Read a declared fixture.",
                   "input_schema": contracts.validate_schema(READ_SCHEMA)},
                  {"name": "submit_output", "description": "Submit the task output.",
                   "input_schema": contracts.validate_schema(TOTALS_SCHEMA)}],
        "tool_choice": {"type": "any"}}
    assert json.loads(contracts.wire(request)) == request
    assert anthropic.request_digest(request) == contracts.digest(request)


def test_freeze_request_reads_only_the_declared_model_configuration():
    assert set(freeze()) == {"model", "max_tokens", "system", "messages", "tools", "tool_choice"}
    declared = freeze(model=dict(MODEL, temperature=0.25, stop_sequences=["</done>"]))
    assert declared["temperature"] == 0.25 and declared["stop_sequences"] == ["</done>"]
    assert freeze(model=dict(MODEL, provider="anthropic")) == freeze()


def test_freeze_request_does_not_alias_its_arguments():
    messages, declared, choice = conversation(), tools(), {"type": "tool", "name": "submit_output"}
    first = anthropic.freeze_request(MODEL, system=SYSTEM, messages=messages, tools=declared,
                                     tool_choice=choice)
    frozen = contracts.wire(first)
    messages[1]["content"][1]["input"]["fixture"] = "other"
    messages.append(message("assistant", text("late")))
    declared[0]["description"] = "changed"
    choice["name"] = "fixture.read"
    assert contracts.wire(first) == frozen
    first["messages"][0]["content"][0]["text"] = "mutated"
    first["tools"].clear()
    second = anthropic.freeze_request(MODEL, system=SYSTEM, messages=conversation(), tools=tools(),
                                      tool_choice={"type": "tool", "name": "submit_output"})
    assert contracts.wire(second) == frozen


DOCUMENTED = ("stream", "thinking", "metadata", "output_config", "service_tier", "container",
              "cache_control", "top_k", "top_p", "mcp_servers", "betas")


@pytest.mark.parametrize("field", sorted(anthropic.UNSUPPORTED))
def test_freeze_request_refuses_each_unsupported_mode(field):
    assert set(DOCUMENTED) <= anthropic.UNSUPPORTED
    turn = dict(message("user", text("go")))
    turn[field] = True
    with pytest.raises(ValueError, match=field):
        freeze(messages=[turn])
    with pytest.raises(ValueError, match=field):
        freeze(messages=[message("user", dict(text("go"), **{field: {"type": "ephemeral"}}))])


@pytest.mark.parametrize("system", [[{"type": "text", "text": "go"}], "", "   ", 7, None],
                         ids=["list", "empty", "blank", "integer", "null"])
def test_freeze_request_refuses_a_system_that_is_not_bounded_text(system):
    with pytest.raises(ValueError, match="system"):
        freeze(system=system)


BAD_CONVERSATIONS = {
    "empty": [],
    "not-a-list": {"role": "user", "content": [text("go")]},
    "first-assistant": [message("assistant", text("go"))],
    "non-alternating": [message("user", text("a")), message("user", text("b"))],
    "ends-assistant": [message("user", text("a")), message("assistant", text("b"))],
    "unknown-message-key": [dict(message("user", text("a")), name="agent")],
    "unknown-role": [message("system", text("a"))],
    "empty-content": [message("user")],
    "block-not-an-object": [{"role": "user", "content": ["go"]}],
    "unknown-block-type": [message("user", {"type": "image", "source": {"data": "x"}})],
    "empty-text": [message("user", {"type": "text", "text": ""})],
    "tool-use-in-a-user-turn": [message("user", use("toolu_1"))],
    "tool-result-in-an-assistant-turn": [message("user", text("a")),
                                         message("assistant", result("toolu_1")),
                                         message("user", text("b"))],
    "tool-use-missing-id": [message("user", text("a")),
                            message("assistant", {"type": "tool_use", "name": "fixture.read", "input": {}}),
                            message("user", text("b"))],
    "tool-use-non-object-input": [message("user", text("a")),
                                  message("assistant", use("toolu_1", "fixture.read", [])),
                                  message("user", text("b"))],
    "tool-result-non-bool-is-error": [message("user", dict(result("toolu_1"), is_error="yes"))],
}


@pytest.mark.parametrize("messages", list(BAD_CONVERSATIONS.values()), ids=list(BAD_CONVERSATIONS))
def test_freeze_request_refuses_malformed_conversations(messages):
    with pytest.raises(ValueError):
        freeze(messages=messages)


BAD_TOOLS = {
    "missing-description": [{"name": "fixture.read", "input_schema": READ_SCHEMA}],
    "unknown-key": [{"name": "fixture.read", "description": "d", "input_schema": READ_SCHEMA, "type": "custom"}],
    "open-object-schema": [{"name": "fixture.read", "description": "d",
                            "input_schema": {"type": "object", "properties": {}, "additionalProperties": True}}],
    "non-object-schema": [{"name": "fixture.read", "description": "d",
                           "input_schema": {"type": "string", "maxLength": 8}}],
    "unsupported-keyword": [{"name": "fixture.read", "description": "d",
                             "input_schema": {"type": "object", "properties": {}, "patternProperties": {}}}],
    "duplicate-names": [{"name": "fixture.read", "description": "d", "input_schema": READ_SCHEMA},
                        {"name": "fixture.read", "description": "e", "input_schema": READ_SCHEMA}],
    "bad-name": [{"name": "Fixture Read", "description": "d", "input_schema": READ_SCHEMA}],
    "empty-description": [{"name": "fixture.read", "description": "", "input_schema": READ_SCHEMA}],
    "not-a-list": {"fixture.read": READ_SCHEMA},
}


@pytest.mark.parametrize("declared", list(BAD_TOOLS.values()), ids=list(BAD_TOOLS))
def test_freeze_request_refuses_malformed_tool_declarations(declared):
    with pytest.raises(ValueError):
        freeze(tools=declared, tool_choice={"type": "auto"})


BAD_CHOICES = {
    "not-an-object": "auto",
    "unknown-type": {"type": "always"},
    "missing-type": {"disable_parallel_tool_use": True},
    "tool-without-name": {"type": "tool"},
    "undeclared-tool": {"type": "tool", "name": "checker.category_totals"},
    "extra-key": {"type": "auto", "name": "fixture.read"},
    "non-bool-parallel-flag": {"type": "any", "disable_parallel_tool_use": "yes"},
    "unsupported-mode": {"type": "auto", "cache_control": {"type": "ephemeral"}},
}


@pytest.mark.parametrize("choice", list(BAD_CHOICES.values()), ids=list(BAD_CHOICES))
def test_freeze_request_refuses_malformed_tool_choices(choice):
    with pytest.raises(ValueError):
        freeze(tool_choice=choice)


def test_freeze_request_accepts_the_reserved_actions_as_declared_tools():
    reserved = [{"name": name, "description": f"The {name} action.", "input_schema": TOTALS_SCHEMA}
                for name in contracts.RESERVED_TOOLS]
    request = freeze(tools=reserved, tool_choice={"type": "tool", "name": "submit_output",
                                                  "disable_parallel_tool_use": True})
    assert [tool["name"] for tool in request["tools"]] == list(contracts.RESERVED_TOOLS)
    assert request["tool_choice"] == {"type": "tool", "name": "submit_output", "disable_parallel_tool_use": True}


@pytest.mark.parametrize("temperature", [-0.1, 1.5])
def test_model_config_already_refuses_a_temperature_outside_the_unit_interval(temperature):
    with pytest.raises(contracts.ContractError, match="temperature"):
        contracts.model_config(dict(MODEL, temperature=temperature))
    with pytest.raises(ValueError):
        freeze(model=dict(MODEL, temperature=temperature))


def workflow(tmp_path):
    fixtures = {}
    for name, payload in (("orders", {"rows": [{"category": "book", "cents": 500}]}),
                          ("expected", {"totals": [{"category": "book", "cents": 500}], "total_cents": 500})):
        path = tmp_path / "fixtures" / f"{name}.json"
        path.parent.mkdir(exist_ok=True)
        raw = contracts.wire(payload).encode()
        path.write_bytes(raw)
        fixtures[name] = {"path": f"fixtures/{name}.json", "sha256": sha256(raw).hexdigest(), "bytes": len(raw)}
    limits = {"model_steps": 4, "tool_calls": 4, "rejections": 2, "calls": 8, "tokens": 20000}
    return {"format": contracts.SPEC_FORMAT, "run_id": "example",
            "agents": [{"id": "producer", "model": MODEL, "capabilities": {"tools": ["fixture.read"]}},
                       {"id": "reviewer", "model": MODEL,
                        "capabilities": {"tools": ["checker.category_totals"]}}],
            "tools": [{"name": "fixture.read", "version": "fixture-read-v1", "config": {"fixtures": ["orders"]}},
                      {"name": "checker.category_totals", "version": "category-totals-v1",
                       "config": {"fixture": "orders"}},
                      {"name": "checker.expected_json", "version": "expected-json-v1",
                       "config": {"fixture": "expected"}}],
            "fixtures": fixtures,
            "tasks": [{"id": "producer", "kind": "model", "agent": "producer",
                       "instructions": "Total the orders by category.", "dependencies": [], "reads": [],
                       "tools": ["fixture.read"], "output_schema": TOTALS_SCHEMA, "limits": limits},
                      {"id": "reviewer", "kind": "model", "agent": "reviewer",
                       "instructions": "Check the candidate totals.", "dependencies": ["producer"],
                       "reads": ["producer"], "tools": ["checker.category_totals"],
                       "output_schema": TOTALS_SCHEMA, "limits": limits},
                      {"id": "decide", "kind": "host", "agent": contracts.HOST_AGENT,
                       "dependencies": ["producer", "reviewer"], "reads": ["producer", "reviewer"],
                       "rule": {"type": "checker_pass", "candidate": "producer", "review": "reviewer",
                                "checker": "checker.category_totals"}}],
            "limits": {"max_calls": 32, "token_cap": 100000, "context_bytes": 65536,
                       "artifact_bytes": 65536, "max_work_items": 8, "max_children": 4,
                       "max_depth": 2, "max_platform_operations": 64}}


def test_a_frozen_request_carries_the_tools_the_workflow_declared(tmp_path):
    spec = contracts.workflow_spec(workflow(tmp_path))
    declaration = spec["fixtures"]["orders"]
    assert declaration == contracts.fixture_spec(declaration)
    assert declaration["sha256"] == sha256((tmp_path / declaration["path"]).read_bytes()).hexdigest()
    capability = spec["agents"][1]["capabilities"]["tools"]
    request = freeze(tools=[{"name": name, "description": f"Declared tool {name}.",
                             "input_schema": TOTALS_SCHEMA} for name in capability],
                     tool_choice={"type": "tool", "name": capability[0]})
    assert [tool["name"] for tool in request["tools"]] == capability
    assert request["max_tokens"] == spec["agents"][1]["model"]["max_new_tokens"]


# ---------------------------------------------------------------- extract

def test_extract_returns_the_artifact_and_the_reported_usage():
    raw = response()
    artifact, prompt, completion = anthropic.extract(raw)
    assert artifact == {"id": "msg_01", "model": "fake-model", "stop_reason": "tool_use",
                        "stop_sequence": None,
                        "content": [{"type": "text", "text": "Here are the totals."},
                                    {"type": "tool_use", "id": "toolu_2", "name": "submit_output",
                                     "input": {"totals": [{"category": "book", "cents": 500}],
                                               "total_cents": 500}}],
                        "usage": {"input_tokens": 120, "output_tokens": 30,
                                  "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}
    assert (prompt, completion) == (120, 30)
    assert json.loads(contracts.wire(artifact)) == artifact
    frozen = contracts.wire(artifact)
    raw["content"][1]["input"]["total_cents"] = 1
    raw["usage"]["input_tokens"] = 9
    assert contracts.wire(artifact) == frozen


VARIANTS = {
    "cache-tokens-are-prompt-tokens": (
        response(usage={"input_tokens": 120, "output_tokens": 30, "cache_creation_input_tokens": 400,
                        "cache_read_input_tokens": 1000},
                 stop_reason="stop_sequence", stop_sequence="</done>"), 1520, 30, "</done>"),
    "null-cache-fields-count-as-zero": (
        response(usage={"input_tokens": 120, "output_tokens": 30, "cache_creation_input_tokens": None,
                        "cache_read_input_tokens": None}), 120, 30, None),
    "one-cache-field-only": (
        response(usage={"input_tokens": 7, "output_tokens": 1, "cache_read_input_tokens": 93}), 100, 1, None),
    "truncation-leaves-no-content": (
        response(content=[], stop_reason="max_tokens",
                 usage={"input_tokens": 5, "output_tokens": 512}), 5, 512, None),
}


@pytest.mark.parametrize("raw,prompt,completion,sequence", list(VARIANTS.values()), ids=list(VARIANTS))
def test_extract_accepts_the_documented_usage_and_stop_variants(raw, prompt, completion, sequence):
    artifact, reported_prompt, reported_completion = anthropic.extract(raw)
    assert (reported_prompt, reported_completion) == (prompt, completion)
    assert artifact["stop_sequence"] == sequence
    assert set(artifact["usage"]) == {"input_tokens", "output_tokens", "cache_creation_input_tokens",
                                      "cache_read_input_tokens"}


def test_the_extracted_tool_input_conforms_to_the_declared_output_schema():
    artifact, _, _ = anthropic.extract(response())
    schema = contracts.validate_schema(TOTALS_SCHEMA)
    assert contracts.conforms(schema, artifact["content"][1]["input"]) is None
    assert contracts.conforms(schema, {"totals": [], "total_cents": "500"}) is not None


BAD_RESPONSES = {
    "not-an-object": [response()],
    "wrong-type": response(type="completion"),
    "wrong-role": response(role="user"),
    "content-not-a-list": response(content={"type": "text", "text": "hi"}),
    "unknown-block-type": response(content=[{"type": "thinking", "thinking": "..."}]),
    "block-not-an-object": response(content=["hi"]),
    "tool-use-missing-id": response(content=[{"type": "tool_use", "name": "submit_output", "input": {}}]),
    "tool-use-non-object-input": response(content=[{"type": "tool_use", "id": "toolu_2",
                                                    "name": "submit_output", "input": []}]),
    "text-block-extra-key": response(content=[{"type": "text", "text": "hi", "citations": None}]),
    "missing-usage": {key: value for key, value in response().items() if key != "usage"},
    "unknown-response-field": response(container=None),
    "negative-token": response(usage={"input_tokens": -1, "output_tokens": 2}),
    "bool-token": response(usage={"input_tokens": True, "output_tokens": 2}),
    "float-token": response(usage={"input_tokens": 1.0, "output_tokens": 2}),
    "unknown-usage-field": response(usage={"input_tokens": 1, "output_tokens": 2, "invented_tokens": 3}),
    "unknown-stop-reason": response(stop_reason="refusal"),
    "stop-sequence-not-a-string": response(stop_sequence=7),
    "empty-id": response(id=""),
}


@pytest.mark.parametrize("raw", list(BAD_RESPONSES.values()), ids=list(BAD_RESPONSES))
def test_extract_refuses_malformed_responses(raw):
    with pytest.raises(ValueError):
        anthropic.extract(raw)


# ---------------------------------------------------------------- AnthropicTransport

def test_the_transport_sends_the_frozen_request_exactly_once():
    body = Body(contracts.wire(response()))
    sender, opener, key = transport(body)
    assert key.calls == 0
    assert sender(freeze()) == response()
    assert len(opener.requests) == 1 and key.calls == 1
    sent = opener.requests[0]
    assert sent.data == contracts.wire(freeze()).encode()
    assert sent.get_method() == "POST"
    assert sent.full_url == "https://api.anthropic.com" + anthropic.ENDPOINT
    assert {name.lower(): value for name, value in sent.header_items()} == {
        "x-api-key": KEY, "anthropic-version": anthropic.API_VERSION,
        "content-type": "application/json", "accept": "application/json"}
    assert opener.timeouts == [60.0] and body.closed


def test_the_transport_never_stores_or_echoes_the_key():
    error = urllib.error.HTTPError("https://api.anthropic.com" + anthropic.ENDPOINT, 401, "Unauthorized", {},
                                   io.BytesIO(contracts.wire(
                                       {"type": "error",
                                        "error": {"type": "authentication_error",
                                                  "message": "invalid x-api-key"}}).encode()))
    sender, opener, key = transport(error)
    assert all(KEY not in repr(value) for value in vars(sender).values())
    assert KEY not in repr(sender)
    with pytest.raises(anthropic.TransportError) as raised:
        sender(freeze())
    assert KEY not in str(raised.value)
    assert "authentication_error" in str(raised.value)
    assert len(opener.requests) == 1 and key.calls == 1


HTTP_ERRORS = {
    "reported-error-type": (400, contracts.wire({"type": "error",
                                                 "error": {"type": "invalid_request_error",
                                                           "message": "max_tokens too large"}}).encode(),
                            "^http 400: invalid_request_error: max_tokens too large$"),
    "html-body": (529, b"<html>overloaded</html>", "^http 529$"),
    "error-object-without-a-type": (500, b'{"error":{"message":"boom"}}', "^http 500$"),
}


@pytest.mark.parametrize("status,body,expected", list(HTTP_ERRORS.values()), ids=list(HTTP_ERRORS))
def test_an_http_error_reports_the_status_and_the_provider_error_type(status, body, expected):
    sender, opener, _ = transport(urllib.error.HTTPError(
        "https://api.anthropic.com" + anthropic.ENDPOINT, status, "Error", {}, io.BytesIO(body)))
    with pytest.raises(anthropic.TransportError, match=expected):
        sender(freeze())
    assert len(opener.requests) == 1


@pytest.mark.parametrize("failure", [urllib.error.URLError("connection refused"), socket.timeout("timed out"),
                                     ConnectionResetError("reset")],
                         ids=["urlerror", "timeout", "reset"])
def test_socket_failures_become_transport_errors_without_a_second_send(failure):
    sender, opener, key = transport(failure)
    with pytest.raises(anthropic.TransportError, match="transport failure"):
        sender(freeze())
    assert len(opener.requests) == 1 and key.calls == 1


BAD_BODIES = {"not-json": b"<html>", "duplicate-keys": b'{"id":"a","id":"b"}', "a-list": b"[]",
              "nonfinite": b'{"usage":NaN}', "truncated": b'{"id":'}


@pytest.mark.parametrize("payload", list(BAD_BODIES.values()), ids=list(BAD_BODIES))
def test_a_200_body_that_is_not_one_strict_json_object_is_a_transport_error(payload):
    sender, opener, _ = transport(Body(payload))
    with pytest.raises(anthropic.TransportError):
        sender(freeze())
    assert len(opener.requests) == 1


@pytest.mark.parametrize("status", [204, 302, 500, None])
def test_a_status_other_than_200_is_a_transport_error(status):
    sender, _, _ = transport(Body(contracts.wire(response()), status=status))
    with pytest.raises(anthropic.TransportError, match="unexpected status"):
        sender(freeze())


BAD_URLS = ["http://api.anthropic.com", "https://api.anthropic.com/", "https://api.anthropic.com/v1",
            "https://api.anthropic.com?beta=1", "ftp://api.anthropic.com", "api.anthropic.com",
            "https://user:pass@api.anthropic.com", ""]


@pytest.mark.parametrize("base_url", BAD_URLS)
def test_the_transport_refuses_an_unusable_base_url(base_url):
    with pytest.raises(ValueError, match="base_url"):
        transport(base_url=base_url)


@pytest.mark.parametrize("base_url", ["http://127.0.0.1:8931", "http://localhost:8931", "http://[::1]:8931",
                                      "https://api.anthropic.com"])
def test_the_transport_accepts_https_and_loopback_http(base_url):
    sender, _, _ = transport(Body(contracts.wire(response())), base_url=base_url)
    assert sender.base_url == base_url
    assert sender(freeze()) == response()


@pytest.mark.parametrize("options", [{"api_key": KEY}, {"timeout": 0}, {"timeout": float("inf")},
                                     {"timeout": "60"}, {"opener": "urlopen"}],
                         ids=["key-not-callable", "zero-timeout", "infinite-timeout", "text-timeout",
                              "opener-not-callable"])
def test_the_transport_refuses_unusable_construction_arguments(options):
    with pytest.raises(ValueError):
        transport(**options)


def test_the_default_opener_follows_no_redirect_and_reads_no_proxy():
    sender = anthropic.AnthropicTransport(api_key=Key())
    handlers = sender.opener.__self__.handlers
    assert not any(isinstance(handler, (urllib.request.HTTPRedirectHandler, urllib.request.ProxyHandler))
                   for handler in handlers)


def test_a_loopback_server_receives_the_frozen_bytes_and_the_declared_headers(loopback):
    server, thread, received = serve(contracts.wire(response()))
    try:
        request = freeze()
        assert loopback_transport(server)(request) == response()
        assert len(received) == 1
        assert received[0]["path"] == anthropic.ENDPOINT
        assert received[0]["body"] == contracts.wire(request).encode()
        assert received[0]["headers"]["x-api-key"] == KEY
        assert received[0]["headers"]["anthropic-version"] == anthropic.API_VERSION
        assert received[0]["headers"]["content-type"] == "application/json"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_a_loopback_error_status_is_a_transport_error_with_one_request(loopback):
    server, thread, received = serve(contracts.wire({"type": "error",
                                                     "error": {"type": "api_error", "message": "overloaded"}}),
                                     status=500)
    try:
        with pytest.raises(anthropic.TransportError, match="http 500: api_error: overloaded"):
            loopback_transport(server)(freeze())
        assert len(received) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_a_loopback_redirect_is_never_followed(loopback):
    server, thread, received = serve(contracts.wire({"type": "error", "error": {"type": "moved", "message": "go"}}),
                                     status=302, extra={"location": "/v1/messages?followed=1"})
    try:
        with pytest.raises(anthropic.TransportError, match="http 302"):
            loopback_transport(server)(freeze())
        assert len(received) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_a_loopback_body_that_is_not_json_is_a_transport_error(loopback):
    server, thread, received = serve(b'{"id": "msg_01", "id": "msg_02"}')
    try:
        with pytest.raises(anthropic.TransportError, match="strict JSON"):
            loopback_transport(server)(freeze())
        assert len(received) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------- FakeTransport

def script(*entries):
    return {"format": anthropic.SCRIPT_FORMAT,
            "responses": [{"task": task, "step": step, "response": payload} for task, step, payload in entries]}


def header(task="producer", version=1, step=0):
    return anthropic.HEADER_PREFIX + f"task={task} version={version} step={step}\n\nInstructions."


def test_the_fake_transport_dispatches_by_header_and_isolates_every_response():
    calls = []
    fake = anthropic.FakeTransport(script(("producer", 0, response()),
                                          ("producer", 1, response(id="msg_02")),
                                          ("reviewer", 0, response(id="msg_03"))), calls=calls)
    first = fake(freeze(system=header()))
    first["content"].clear()
    first["usage"]["input_tokens"] = 0
    assert fake(freeze(system=header())) == response()
    assert fake(freeze(system=header(step=1)))["id"] == "msg_02"
    assert fake(freeze(system=header(task="reviewer")))["id"] == "msg_03"
    assert len(calls) == 4 and calls[0]["system"] == header()
    calls[0]["system"] = "mutated"
    artifact, prompt, completion = anthropic.extract(fake(freeze(system=header())))
    assert artifact["id"] == "msg_01" and (prompt, completion) == (120, 30)


UNKNOWN_DISPATCHES = {
    "unknown-task": header(task="checker"),
    "unknown-step": header(step=4),
    "missing-header": "You are a helpful assistant.\nDo the work.",
    "prefix-only": anthropic.HEADER_PREFIX + "task=producer step=0",
    "trailing-text": anthropic.HEADER_PREFIX + "task=producer version=1 step=0 extra",
    "spaced-task": anthropic.HEADER_PREFIX + "task=produ cer version=1 step=0",
    "non-numeric-step": anthropic.HEADER_PREFIX + "task=producer version=1 step=first",
    "header-on-the-second-line": "Instructions.\n" + header(),
}


@pytest.mark.parametrize("system", list(UNKNOWN_DISPATCHES.values()), ids=list(UNKNOWN_DISPATCHES))
def test_the_fake_transport_refuses_an_unmatched_or_malformed_header(system):
    calls = []
    fake = anthropic.FakeTransport(script(("producer", 0, response())), calls=calls)
    with pytest.raises(anthropic.TransportError):
        fake(freeze(system=system))
    assert calls == []


def test_the_fake_transport_refuses_a_request_without_a_system_string():
    fake = anthropic.FakeTransport(script(("producer", 0, response())))
    with pytest.raises(anthropic.TransportError, match="system header"):
        fake({"messages": []})


BAD_SCRIPTS = {
    "wrong-format": {"format": "other-v1", "responses": []},
    "missing-responses": {"format": anthropic.SCRIPT_FORMAT},
    "extra-key": {"format": anthropic.SCRIPT_FORMAT, "responses": [], "default": {}},
    "responses-not-a-list": {"format": anthropic.SCRIPT_FORMAT, "responses": {}},
    "entry-missing-step": {"format": anthropic.SCRIPT_FORMAT, "responses": [{"task": "producer", "response": {}}]},
    "duplicate-pair": {"format": anthropic.SCRIPT_FORMAT,
                       "responses": [{"task": "producer", "step": 0, "response": {}},
                                     {"task": "producer", "step": 0, "response": {"id": "other"}}]},
    "negative-step": {"format": anthropic.SCRIPT_FORMAT,
                      "responses": [{"task": "producer", "step": -1, "response": {}}]},
    "bool-step": {"format": anthropic.SCRIPT_FORMAT,
                  "responses": [{"task": "producer", "step": True, "response": {}}]},
    "non-object-response": {"format": anthropic.SCRIPT_FORMAT,
                            "responses": [{"task": "producer", "step": 0, "response": []}]},
    "bad-task-name": {"format": anthropic.SCRIPT_FORMAT,
                      "responses": [{"task": "Producer 1", "step": 0, "response": {}}]},
    "non-finite-value": {"format": anthropic.SCRIPT_FORMAT,
                         "responses": [{"task": "producer", "step": 0,
                                        "response": {"usage": float("nan")}}]},
    "not-an-object": [],
}


@pytest.mark.parametrize("value", list(BAD_SCRIPTS.values()), ids=list(BAD_SCRIPTS))
def test_validate_script_refuses_a_malformed_script(value):
    with pytest.raises(ValueError):
        anthropic.validate_script(value)


def test_validate_script_keeps_unvalidated_responses_verbatim():
    malformed = {"type": "message", "usage": {"input_tokens": -5}}
    validated = anthropic.validate_script(script(("producer", 0, malformed)))
    assert validated == {"format": anthropic.SCRIPT_FORMAT,
                         "responses": [{"task": "producer", "step": 0, "response": malformed}]}
    with pytest.raises(ValueError):
        anthropic.extract(anthropic.FakeTransport(validated)(freeze(system=header())))


def test_load_script_reads_a_strict_bounded_script(tmp_path):
    path = tmp_path / "script.json"
    path.write_text(json.dumps(script(("producer", 0, response()))))
    assert anthropic.load_script(path)["responses"][0]["response"] == response()
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"format": "%s", "responses": [], "responses": []}' % anthropic.SCRIPT_FORMAT)
    with pytest.raises(ValueError, match="duplicate JSON field"):
        anthropic.load_script(duplicate)
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (anthropic.MAX_BODY_BYTES + 1) + b"{}")
    with pytest.raises(ValueError, match="byte bound"):
        anthropic.load_script(oversized)
