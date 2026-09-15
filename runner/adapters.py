"""Opt-in Kimi transport extracted from runtime/remote_kimi_v1.py (MIT).

Import/construction/dry-run never read credentials or send requests. Live use
requires separate authorization; this cleanup authorizes no provider calls.
"""
import json
import os
from pathlib import Path
import ssl
import sys
from time import monotonic_ns
import urllib.error
import urllib.request

from .accounting import (MoneyLedger, RemoteKimiError, _integer, _wire,
    BASE_URL, MODEL, INPUT_UPPER_BOUND, MAX_OUTPUT_TOKENS, PRICE_VERSION)

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _credential():
    key = os.environ.get("MOONSHOT_API_KEY")
    if not key:
        path = os.environ.get("MOONSHOT_API_KEY_FILE", "~/.config/pheroos/credentials/moonshot-cn.key")
        try:
            key = Path(path).expanduser().read_text().strip()
        except (OSError, UnicodeError):
            raise RemoteKimiError("credential_unavailable") from None
    if not key or len(key) > 4096 or any(c.isspace() for c in key) or not key.isascii():
        raise RemoteKimiError("credential_invalid")
    return key


def _safe_string(value, key, maximum=240):
    if type(value) is not str or not value or len(value) > maximum:
        raise ValueError("invalid response string")
    return value.replace(key, "[REDACTED]")


def _optional_string(value, key):
    return _safe_string(value, key) if type(value) is str and 0 < len(value) <= 240 else None


class KimiCNAdapter:
    def __init__(self, ledger=None, *, disable_proxy=True, timeout_seconds=90, max_request_bytes=32768):
        if (ledger is not None and not isinstance(ledger, MoneyLedger)) or type(disable_proxy) is not bool:
            raise ValueError("invalid adapter configuration")
        if (type(timeout_seconds) not in {int, float} or not 0 < timeout_seconds <= 300
                or type(max_request_bytes) is not int or not 256 <= max_request_bytes <= 32768):
            raise ValueError("invalid transport bounds")
        self.ledger = ledger
        self.disable_proxy, self.timeout_seconds = disable_proxy, timeout_seconds
        self.max_request_bytes = max_request_bytes
        self.identity = {"adapter": "remote_kimi_cn_v1", "model_id": MODEL, "paid": True,
                         "base_url": BASE_URL, "thinking": "disabled", "stream": False,
                         "token_reservation_contract": "remote_input_upper_bound_v1",
                         "input_token_upper_bound": INPUT_UPPER_BOUND,
                         "max_output_tokens": MAX_OUTPUT_TOKENS, "price_version": PRICE_VERSION,
                         "seed_contract": "recorded_locally_not_sent_no_provider_reproducibility_guarantee"}

    def _payload(self, messages, maximum):
        if type(messages) is not list or not messages or len(messages) > 128:
            raise ValueError("nonempty bounded message list required")
        for item in messages:
            if (type(item) is not dict or set(item) != {"role", "content"}
                    or item["role"] not in {"system", "user", "assistant"}
                    or type(item["content"]) is not str):
                raise ValueError("only text role/content messages are supported")
        data = _wire({"model": MODEL, "messages": messages, "thinking": {"type": "disabled"},
                      "max_completion_tokens": maximum, "stream": False}).encode()
        if len(data) > self.max_request_bytes:
            raise ValueError("request byte bound exceeded")
        return data

    def count_tokens(self, messages):
        """Declared full context upper bound, never represented as a token estimate."""
        self._payload(messages, MAX_OUTPUT_TOKENS)
        return INPUT_UPPER_BOUND

    def _http(self, endpoint, data, key):
        if endpoint not in {"/chat/completions", "/models"}:
            raise ValueError("unsupported endpoint")
        handlers = [_NoRedirect()]
        if self.disable_proxy:
            handlers.append(urllib.request.ProxyHandler({}))
        cafile = os.environ.get("SSL_CERT_FILE")
        if not cafile and sys.platform == "darwin" and Path("/etc/ssl/cert.pem").is_file():
            cafile = "/etc/ssl/cert.pem"
        handlers.append(urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=cafile)))
        opener = urllib.request.build_opener(*handlers)
        request = urllib.request.Request(BASE_URL + endpoint, data=data,
                    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                    method="POST" if data is not None else "GET")
        with opener.open(request, timeout=self.timeout_seconds) as response:
            if response.status != 200 or response.geturl() != BASE_URL + endpoint:
                raise RemoteKimiError("http_error")
            body = response.read(131073)
            if len(body) > 131072:
                raise RemoteKimiError("response_too_large")
            request_id = response.headers.get("x-request-id")
            return json.loads(body), request_id

    def _invoke(self, call_id, kind, data, maximum):
        if self.ledger is None:
            raise RemoteKimiError("live_ledger_required")
        key = _credential()
        # Credential access and local validation precede reservation; network follows commit.
        self.ledger.reserve(call_id, prompt_bound=INPUT_UPPER_BOUND if kind == "generation" else 0,
                            output_bound=maximum, kind=kind)
        started = monotonic_ns()
        try:
            body, request_id = self._http("/chat/completions" if kind == "generation" else "/models",
                                           data, key)
            elapsed = monotonic_ns() - started
            if type(body) is not dict:
                raise ValueError("invalid response object")
            metadata = {"elapsed_ns": elapsed, "request_id": _optional_string(request_id, key)}
            if kind == "models":
                rows = body["data"]
                if type(rows) is not list:
                    raise ValueError("invalid model list")
                result = {**metadata, "models": [_safe_string(row["id"], key) for row in rows]}
                self.ledger.settle(call_id, result)
                return result
            usage = body["usage"]
            if type(usage) is not dict:
                raise ValueError("invalid usage")
            clean_usage = {name: usage[name] for name in
                           ("prompt_tokens", "completion_tokens", "total_tokens")}
            if "cached_tokens" in usage:
                clean_usage["cached_tokens"] = usage["cached_tokens"]
            choices = body.get("choices")
            choice = choices[0] if type(choices) is list and len(choices) == 1 else None
            finish = choice.get("finish_reason") if type(choice) is dict else None
            receipt = {**metadata, "response_id": _optional_string(body.get("id"), key),
                       "returned_model": _optional_string(body.get("model"), key),
                       "finish_reason": _optional_string(finish, key), "usage": clean_usage,
                       "cost_basis": "actual_usage" if "cached_tokens" in clean_usage else
                                     "actual_tokens_uncached_price_upper_bound"}
            # Known token usage remains known even if the proposal is unusable.
            # Prices always follow the requested model's recorded price version.
            cost_cny = self.ledger.settle(call_id, receipt)
            if type(choices) is not list or len(choices) != 1:
                raise ValueError("invalid choices")
            if choice["message"].get("role") != "assistant":
                raise ValueError("invalid assistant message")
            text = choice["message"]["content"]
            if type(text) is not str:
                raise ValueError("invalid text content")
            model = _safe_string(body["model"], key)
            if model != MODEL:
                raise ValueError("unexpected returned model")
            _safe_string(body["id"], key)
            _safe_string(choice["finish_reason"], key)
            return {**receipt, "cost_cny": cost_cny, "text": text.replace(key, "[REDACTED]"),
                    "prompt_tokens": clean_usage["prompt_tokens"],
                    "completion_tokens": clean_usage["completion_tokens"]}
        except Exception as exc:
            if isinstance(exc, (TimeoutError,)):
                code = "timeout"
            elif isinstance(exc, urllib.error.HTTPError):
                code = "http_error"
            elif isinstance(exc, urllib.error.URLError):
                code = "timeout" if isinstance(exc.reason, TimeoutError) else "transport_error"
            elif isinstance(exc, RemoteKimiError) and str(exc) in {"http_error", "response_too_large"}:
                code = str(exc)
            elif isinstance(exc, (ValueError, KeyError, TypeError, IndexError, UnicodeError)):
                code = "invalid_response"
            else:
                code = "unexpected_failure"
            status = exc.code if isinstance(exc, urllib.error.HTTPError) else None
            self.ledger.unknown(call_id, code, http_status=status)
            error = RemoteKimiError(code)
            error.http_status = status
            raise error from None

    def generate(self, messages, max_new_tokens, seed, *, call_id):
        _integer(max_new_tokens, "output bound", MAX_OUTPUT_TOKENS)
        if not max_new_tokens:
            raise ValueError("positive output bound required")
        if type(seed) is not int or seed < 0:
            raise ValueError("nonnegative local seed required")
        data = self._payload(messages, max_new_tokens)
        return self._invoke(call_id, "generation", data, max_new_tokens)

    def probe(self, *, call_id):
        """Read the model list; consumes one globally budgeted HTTP request."""
        return self._invoke(call_id, "models", None, 0)
