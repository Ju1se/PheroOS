from __future__ import annotations

from runtime.audit_log import safe_tool_args
from runtime.connection_control import sanitize_remote_error
from runtime.model_gateway import model_fallback_chain, provider_error_message, resolve_upstream_model, should_fallback_model_error


def test_safe_tool_args_recursively_redacts_nested_secrets() -> None:
    safe = safe_tool_args(
        {
            "headers": {
                "Authorization": "Bearer sk-cp-supersecretvalue123456",
                "x-api-key": "sk-secretvalue123456",
            },
            "payload": [{"password": "hidden"}, {"text": "public"}],
        }
    )

    assert safe["headers"]["Authorization"] == "[redacted]"
    assert safe["headers"]["x-api-key"] == "[redacted]"
    assert safe["payload"][0]["password"] == "[redacted]"
    assert safe["payload"][1]["text"] == "public"


def test_remote_error_sanitizers_remove_secret_like_values() -> None:
    detail = "upstream rejected Authorization: Bearer sk-cp-supersecretvalue123456"

    assert "sk-cp" not in sanitize_remote_error(detail)
    assert "sk-cp" not in provider_error_message(record={"provider": "demo"}, status_code=401, detail=detail)


def test_model_gateway_cross_provider_fallback_chain(monkeypatch) -> None:
    monkeypatch.setenv("GLM_FALLBACK_MODELS", "glm-5.1-standard,minimax-m2.7")
    monkeypatch.setenv("MINIMAX_FALLBACK_MODELS", "glm-5.1-standard,glm-5.1")

    assert model_fallback_chain("glm-5.1") == ["glm-5.1", "glm-5.1-standard", "minimax-m2.7"]
    assert model_fallback_chain("minimax-m2.7") == ["minimax-m2.7", "glm-5.1-standard", "glm-5.1"]
    assert should_fallback_model_error(RuntimeError("HTTP 400: context window exceeds limit (2013)"))
    assert should_fallback_model_error(RuntimeError("HTTP 429: 余额不足或无可用资源包"))


def test_kimi_model_fallback_and_upstream_resolution(monkeypatch) -> None:
    monkeypatch.setenv("KIMI_FALLBACK_MODELS", "kimi-k2.5,moonshot-v1-128k")
    record = {
        "provider": "moonshot",
        "capabilities": [{"models": ["kimi-k2.6", "kimi-k2.5", "moonshot-v1-128k"]}],
    }

    assert model_fallback_chain("kimi-k2.6") == ["kimi-k2.6", "kimi-k2.5", "moonshot-v1-128k"]
    assert resolve_upstream_model(record, "minimax-m2.7") == "kimi-k2.6"
