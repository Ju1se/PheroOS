from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse


ConnectionKind = Literal["model_provider", "financial_data_source"]

URL_RE = re.compile(r"https?://[^\s,;]+", re.IGNORECASE)
OPENAI_STYLE_KEY_RE = re.compile(r"sk-[A-Za-z0-9_-]{16,}")
GOOGLE_KEY_RE = re.compile(r"AIza[A-Za-z0-9_-]{20,}")
JWT_STYLE_KEY_RE = re.compile(r"[A-Za-z0-9_-]{16,}\.[A-Za-z0-9._-]{16,}")
TOKEN_RE = re.compile(r"[A-Za-z0-9_.:/+=@-]{4,}")


@dataclass(frozen=True)
class InferredConnection:
    kind: ConnectionKind
    connection_id: str
    payload: dict[str, Any]
    confidence: Literal["high", "medium", "low"]
    reason: str
    warnings: list[str]


def infer_connection(raw_value: str) -> InferredConnection:
    text = str(raw_value or "").strip()
    if not text:
        raise ValueError("credential input must not be empty")

    json_connection = _infer_from_json(text)
    if json_connection:
        return json_connection

    lower = text.lower()
    key_values = _parse_key_values(text)
    url = _extract_url(text)
    provider = _provider_from_text(lower, url)

    if _looks_like_wrds(lower, key_values):
        return _infer_wrds(text, key_values)
    if _looks_like_fred(lower, key_values):
        return _infer_fred(text, key_values)

    api_key = _extract_api_key(text)
    if not api_key and provider not in {"ollama", "lmstudio"}:
        raise ValueError("could not identify an API key or supported credential")

    if provider is None:
        provider = _provider_from_key(api_key)

    if provider is None:
        raise ValueError("could not identify provider from this key")

    return _build_model_connection(provider, api_key, url, config=_config_from_key_values(key_values))


def _infer_from_json(text: str) -> InferredConnection | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    provider = str(payload.get("provider") or payload.get("id") or "").lower()
    if provider == "wrds" or payload.get("username") and payload.get("password"):
        return _infer_wrds(text, {str(key).lower(): str(value) for key, value in payload.items()})
    if provider == "fred":
        return _infer_fred(text, {str(key).lower(): str(value) for key, value in payload.items()})

    api_key = str(payload.get("api_key") or payload.get("key") or payload.get("token") or "").strip()
    url = str(payload.get("base_url") or payload.get("url") or "").strip() or None
    provider = _provider_from_text(provider, url) or _provider_from_key(api_key)
    if not provider:
        return None
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    for key in ("agent_scope", "model_overrides", "preferred_model", "scope_reason"):
        if key in payload and key not in config:
            config[key] = payload[key]
    return _build_model_connection(provider, api_key, url, config=config)


def _parse_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line and "=" not in line:
            continue
        separator = ":" if ":" in line else "="
        key, value = line.split(separator, 1)
        clean_key = key.strip().lower().replace(" ", "_")
        clean_value = value.strip().strip('"').strip("'")
        if clean_key and clean_value:
            values[clean_key] = clean_value
    return values


def _extract_url(text: str) -> str | None:
    match = URL_RE.search(text)
    return match.group(0).rstrip("/") if match else None


def _extract_api_key(text: str) -> str | None:
    for pattern in (OPENAI_STYLE_KEY_RE, GOOGLE_KEY_RE, JWT_STYLE_KEY_RE):
        match = pattern.search(text)
        if match:
            return match.group(0)
    tokens = [token for token in TOKEN_RE.findall(text) if len(token) >= 24 and "://" not in token]
    return tokens[0] if tokens else None


def _provider_from_text(lower_text: str, url: str | None) -> str | None:
    host = urlparse(url).netloc.lower() if url else ""
    haystack = f"{lower_text} {host}"
    if "wrds" in haystack:
        return "wrds"
    if "fred" in haystack or "api.stlouisfed.org" in haystack:
        return "fred"
    if "minimax" in haystack or "sk-cp-" in haystack:
        return "minimax"
    if "kimi" in haystack or "moonshot" in haystack or "api.moonshot.cn" in haystack:
        return "moonshot"
    if "bigmodel" in haystack or "zhipu" in haystack or "glm" in haystack:
        return "zhipu"
    if "openrouter" in haystack or "sk-or-" in haystack:
        return "openrouter"
    if "deepseek" in haystack:
        return "deepseek"
    if "generativelanguage" in haystack or "gemini" in haystack or "google" in haystack:
        return "gemini"
    if "anthropic" in haystack or "claude" in haystack:
        return "anthropic"
    if "ollama" in haystack or "11434" in host:
        return "ollama"
    if "lmstudio" in haystack or "lm studio" in haystack or "1234" in host:
        return "lmstudio"
    if "openai" in haystack or "api.openai.com" in haystack:
        return "openai"
    return None


def _provider_from_key(api_key: str | None) -> str | None:
    if not api_key:
        return None
    if api_key.startswith("sk-cp-"):
        return "minimax"
    if api_key.startswith("sk-or-"):
        return "openrouter"
    if api_key.startswith("sk-ant-"):
        return "anthropic"
    if api_key.startswith("AIza"):
        return "gemini"
    if api_key.startswith("sk-"):
        return "openai"
    if "." in api_key and len(api_key) >= 40:
        return "zhipu"
    return "openai-compatible" if len(api_key) >= 40 else None


def _build_model_connection(
    provider: str,
    api_key: str | None,
    url: str | None,
    *,
    config: dict[str, Any] | None = None,
) -> InferredConnection:
    catalog = {
        "openai": ("openai", "OpenAI", "openai", "https://api.openai.com/v1", "OpenAI-style key"),
        "minimax": ("minimax", "MiniMax", "minimax-openai-compatible", "https://api.minimaxi.com/v1", "MiniMax key prefix"),
        "moonshot": ("moonshot", "Kimi / Moonshot", "moonshot-openai-compatible", "https://api.moonshot.cn/v1", "Kimi/Moonshot endpoint or context hint"),
        "zhipu": ("zhipu", "Zhipu GLM", "zhipu-openai-compatible", "https://open.bigmodel.cn/api/paas/v4", "Zhipu/GLM endpoint or key shape"),
        "openrouter": ("openrouter", "OpenRouter", "openrouter", "https://openrouter.ai/api/v1", "OpenRouter key or endpoint"),
        "deepseek": ("deepseek", "DeepSeek", "deepseek-openai-compatible", "https://api.deepseek.com/v1", "DeepSeek endpoint hint"),
        "gemini": ("gemini", "Google Gemini", "gemini-openai-compatible", "https://generativelanguage.googleapis.com/v1beta/openai", "Google API key or endpoint"),
        "anthropic": ("anthropic", "Anthropic", "anthropic", "https://api.anthropic.com/v1", "Anthropic key or endpoint"),
        "ollama": ("ollama", "Ollama", "ollama-openai-compatible", "http://localhost:11434/v1", "local Ollama endpoint"),
        "lmstudio": ("lmstudio", "LM Studio", "lmstudio-openai-compatible", "http://localhost:1234/v1", "local LM Studio endpoint"),
        "openai-compatible": ("openai-compatible", "OpenAI-compatible", "openai-compatible", url or "", "generic long API key"),
    }
    connection_id, name, provider_name, default_url, reason = catalog[provider]
    warnings = []
    confidence: Literal["high", "medium", "low"] = "high"
    if provider in {"openai", "openai-compatible"} and api_key and api_key.startswith("sk-") and not url:
        confidence = "medium"
        warnings.append("OpenAI-style keys are shared by several providers; add an endpoint if this is not OpenAI.")
    if provider == "moonshot" and api_key and api_key.startswith("sk-") and not url:
        warnings.append("Kimi/Moonshot was inferred from context; endpoint defaults to https://api.moonshot.cn/v1.")
    if provider in {"ollama", "lmstudio"} and not api_key:
        warnings.append("Local OpenAI-compatible endpoint configured without an API key.")
    merged_config = {
        "auto_configured": True,
        "detection_reason": reason,
        "validation": "not_validated",
    }
    merged_config.update(_sanitize_user_config(config or {}))
    payload = {
        "name": name,
        "provider": provider_name,
        "base_url": url or default_url or None,
        "api_key": api_key,
        "enabled": True,
        "config": merged_config,
    }
    return InferredConnection(
        kind="model_provider",
        connection_id=connection_id,
        payload=payload,
        confidence=confidence,
        reason=reason,
        warnings=warnings,
    )


def _config_from_key_values(key_values: dict[str, str]) -> dict[str, Any]:
    config: dict[str, Any] = {}
    scope = key_values.get("agent_scope") or key_values.get("agent") or key_values.get("agents")
    if scope:
        config["agent_scope"] = [item.strip() for item in scope.split(",") if item.strip()]
    preferred_model = key_values.get("preferred_model") or key_values.get("model")
    if preferred_model:
        config["preferred_model"] = preferred_model
    scope_reason = key_values.get("scope_reason")
    if scope_reason:
        config["scope_reason"] = scope_reason
    return config


def _sanitize_user_config(config: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    if not isinstance(config, dict):
        return output
    agent_scope = config.get("agent_scope")
    if isinstance(agent_scope, str):
        output["agent_scope"] = [item.strip() for item in agent_scope.split(",") if item.strip()]
    elif isinstance(agent_scope, list):
        output["agent_scope"] = [str(item).strip() for item in agent_scope if str(item).strip()]
    preferred_model = config.get("preferred_model")
    if preferred_model:
        output["preferred_model"] = str(preferred_model).strip()
    model_overrides = config.get("model_overrides")
    if isinstance(model_overrides, dict):
        output["model_overrides"] = {
            str(key).strip(): str(value).strip()
            for key, value in model_overrides.items()
            if str(key).strip() and str(value).strip()
        }
    scope_reason = config.get("scope_reason")
    if scope_reason:
        output["scope_reason"] = str(scope_reason).strip()
    return output


def _looks_like_wrds(lower_text: str, key_values: dict[str, str]) -> bool:
    if "wrds" in lower_text:
        return True
    return bool(key_values.get("username") and key_values.get("password") and "api_key" not in key_values)


def _looks_like_fred(lower_text: str, key_values: dict[str, str]) -> bool:
    provider = str(key_values.get("provider") or key_values.get("source") or "").lower()
    return "fred" in lower_text or provider == "fred"


def _infer_wrds(text: str, key_values: dict[str, str]) -> InferredConnection:
    username = key_values.get("username") or key_values.get("user") or key_values.get("account")
    password = key_values.get("password") or key_values.get("pass")
    api_key = key_values.get("api_key") or key_values.get("token") or key_values.get("key")
    if not username or not password:
        tokens = [token for token in TOKEN_RE.findall(text) if token.lower() != "wrds" and "://" not in token]
        if len(tokens) >= 2:
            username = username or tokens[-2]
            password = password or tokens[-1]
    payload = {
        "name": "WRDS",
        "provider": "wrds",
        "base_url": key_values.get("base_url") or key_values.get("host") or "wrds-pgdata.wharton.upenn.edu",
        "api_key": api_key,
        "username": username,
        "password": password,
        "enabled": True,
        "config": {
            "auto_configured": True,
            "detection_reason": "WRDS credential pattern",
            "validation": "not_validated",
        },
    }
    warnings = []
    confidence: Literal["high", "medium", "low"] = "high"
    if not username or not password:
        confidence = "low"
        warnings.append("WRDS was detected, but username/password were incomplete.")
    return InferredConnection(
        kind="financial_data_source",
        connection_id="wrds",
        payload=payload,
        confidence=confidence,
        reason="WRDS credential pattern",
        warnings=warnings,
    )


def _infer_fred(text: str, key_values: dict[str, str]) -> InferredConnection:
    api_key = (
        key_values.get("api_key")
        or key_values.get("key")
        or key_values.get("token")
        or key_values.get("fred_api_key")
        or _extract_api_key(text)
    )
    payload = {
        "name": "FRED",
        "provider": "fred",
        "base_url": key_values.get("base_url") or key_values.get("url") or "https://api.stlouisfed.org/fred",
        "api_key": api_key,
        "enabled": True,
        "config": {
            "auto_configured": True,
            "detection_reason": "FRED credential pattern",
            "validation": "not_validated",
        },
    }
    warnings = []
    confidence: Literal["high", "medium", "low"] = "high"
    if not api_key:
        confidence = "low"
        warnings.append("FRED was detected, but no API key was found.")
    return InferredConnection(
        kind="financial_data_source",
        connection_id="fred",
        payload=payload,
        confidence=confidence,
        reason="FRED credential pattern",
        warnings=warnings,
    )
