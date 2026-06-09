from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx

from runtime.connection_control import DEFAULT_TENANT_ID, ConnectionControlPlane, extract_model_ids
from runtime.llm import (
    LiteLLMClient,
    Message,
    extract_assistant_content,
    normalize_provider_web_search_payload,
    parse_json_object_loose,
    retry_delay,
    should_retry_http_status,
)
from runtime.redaction import redact_secret_text


class ConnectionAwareModelGateway:
    """OpenAI-compatible model gateway backed by active tenant connections."""

    def __init__(
        self,
        *,
        control_plane: ConnectionControlPlane,
        tenant_id: str = DEFAULT_TENANT_ID,
        fallback: LiteLLMClient | None = None,
        timeout: float = 300.0,
        max_retries: int = 2,
        enable_internal_fallback: bool | None = None,
    ) -> None:
        self.control_plane = control_plane
        self.tenant_id = tenant_id
        self.fallback = fallback or LiteLLMClient()
        self.timeout = timeout
        self.max_retries = max_retries
        self.enable_internal_fallback = (
            str(os.getenv("MODEL_GATEWAY_INTERNAL_FALLBACK", "")).strip().lower() in {"1", "true", "yes", "on"}
            if enable_internal_fallback is None
            else enable_internal_fallback
        )
        self._glm_semaphore = asyncio.Semaphore(2)

    async def chat(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float = 0.0,
    ) -> str:
        if not self.enable_internal_fallback:
            record = self.select_model_connection(model)
            if not record:
                return await self.fallback.chat(model=model, messages=messages, temperature=temperature)
            data = await self.chat_completion(record=record, model=model, messages=messages, temperature=temperature)
            return extract_assistant_content(data)

        failures: list[tuple[str, Exception]] = []
        chain = model_fallback_chain(model)
        for index, candidate in enumerate(chain):
            try:
                record = self.select_model_connection(candidate)
                if not record:
                    return await self.fallback.chat(model=candidate, messages=messages, temperature=temperature)
                data = await self.chat_completion(record=record, model=candidate, messages=messages, temperature=temperature)
                return extract_assistant_content(data)
            except Exception as exc:
                failures.append((candidate, exc))
                next_model = chain[index + 1] if index + 1 < len(chain) else None
                if not next_model or not should_fallback_model_error(exc):
                    raise RuntimeError(format_gateway_fallback_failure(failures)) from exc
        raise RuntimeError(format_gateway_fallback_failure(failures))

    async def chat_completion(
        self,
        *,
        record: dict[str, Any],
        model: str,
        messages: list[Message],
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        if record.get("provider") == "anthropic":
            return await self.anthropic_chat_completion(
                record=record,
                model=model,
                messages=messages,
                temperature=temperature,
            )
        endpoint = str(record.get("endpoint") or "").rstrip("/")
        api_key = self.control_plane.secret_value(record, "api_key") or ""
        upstream_model = resolve_upstream_model(record, model)
        payload = {
            "model": upstream_model,
            "messages": messages,
            "temperature": provider_temperature(record=record, model=upstream_model, requested=temperature),
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with model_semaphore(model, glm_semaphore=self._glm_semaphore):
                    async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                        response = await client.post(f"{endpoint}/chat/completions", headers=headers, json=payload)
                        response.raise_for_status()
                        return response.json()
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if not should_retry_http_status(exc.response.status_code) or attempt >= self.max_retries:
                    raise RuntimeError(
                        provider_error_message(record=record, status_code=exc.response.status_code, detail=exc.response.text)
                    ) from exc
                await asyncio.sleep(retry_delay(2.0, attempt=attempt))
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        f"Model provider {record.get('provider')} timed out after {self.timeout:g}s"
                    ) from exc
                await asyncio.sleep(retry_delay(2.0, attempt=attempt))
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise RuntimeError(f"Model provider {record.get('provider')} request failed: {exc}") from exc
                await asyncio.sleep(retry_delay(2.0, attempt=attempt))
        raise RuntimeError(f"Model provider request failed after retries: {last_exc}")

    async def anthropic_chat_completion(
        self,
        *,
        record: dict[str, Any],
        model: str,
        messages: list[Message],
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        endpoint = str(record.get("endpoint") or "").rstrip("/")
        api_key = self.control_plane.secret_value(record, "api_key") or ""
        upstream_model = resolve_upstream_model(record, model)
        system_prompt, anthropic_messages = to_anthropic_messages(messages)
        payload: dict[str, Any] = {
            "model": upstream_model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": int(os.getenv("ANTHROPIC_MAX_TOKENS", "4096")),
        }
        if system_prompt:
            payload["system"] = system_prompt
        headers = {
            "x-api-key": api_key,
            "anthropic-version": os.getenv("ANTHROPIC_VERSION", "2023-06-01"),
            "content-type": "application/json",
        }
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                    response = await client.post(f"{endpoint}/messages", headers=headers, json=payload)
                    response.raise_for_status()
                    return anthropic_response_to_openai_shape(response.json(), model=upstream_model)
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if not should_retry_http_status(exc.response.status_code) or attempt >= self.max_retries:
                    raise RuntimeError(
                        provider_error_message(record=record, status_code=exc.response.status_code, detail=exc.response.text)
                    ) from exc
                await asyncio.sleep(retry_delay(2.0, attempt=attempt))
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        f"Model provider {record.get('provider')} timed out after {self.timeout:g}s"
                    ) from exc
                await asyncio.sleep(retry_delay(2.0, attempt=attempt))
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise RuntimeError(f"Model provider {record.get('provider')} request failed: {exc}") from exc
                await asyncio.sleep(retry_delay(2.0, attempt=attempt))
        raise RuntimeError(f"Model provider request failed after retries: {last_exc}")

    def select_model_connection(self, model: str) -> dict[str, Any] | None:
        records = [
            record
            for record in self.control_plane.list_active_connections(tenant_id=self.tenant_id)
            if record.get("kind") == "model_provider"
        ]
        if not records:
            return None

        model_lower = str(model or "").lower()
        if "glm" in model_lower:
            for record in records:
                if record.get("provider") == "zhipu":
                    return record
        if "minimax" in model_lower:
            for record in records:
                if record.get("provider") == "minimax":
                    return record
        if "kimi" in model_lower or "moonshot" in model_lower:
            for record in records:
                if record.get("provider") == "moonshot":
                    return record
        if model_lower.startswith("gpt-") or model_lower.startswith("o"):
            for record in records:
                if record.get("provider") == "openai":
                    return record
        if model_lower.startswith("claude"):
            for record in records:
                if record.get("provider") == "anthropic":
                    return record

        for record in records:
            capability_models = capability_model_names(record)
            if str(model) in capability_models:
                return record

        if len(records) == 1:
            return records[0]
        return records[0]

    async def list_models(self, *, connection_id: str) -> list[str]:
        record = self.control_plane.get_connection(connection_id=connection_id, tenant_id=self.tenant_id)
        if not record:
            raise ValueError("connection not found")
        endpoint = str(record.get("endpoint") or "").rstrip("/")
        api_key = self.control_plane.secret_value(record, "api_key") or ""
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.get(f"{endpoint}/models", headers=headers)
            response.raise_for_status()
            return extract_model_ids(response.json())

    async def provider_web_search(
        self,
        *,
        query: str,
        max_results: int = 5,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Expose provider-native web search through the tenant-scoped gateway.

        The ToolRegistry should not hold provider secrets directly. It calls
        this gateway handle, and the gateway resolves tenant-scoped connection
        records before falling back to the legacy LiteLLM web-search adapter.
        """

        query = str(query or "").strip()
        if not query:
            raise ValueError("query must be a non-empty string")
        record = self.select_provider_web_search_connection(model)
        if record and record.get("provider") == "moonshot":
            return await self.moonshot_web_search(record=record, query=query, max_results=max_results, model=model)
        provider_search = getattr(self.fallback, "provider_web_search", None)
        if provider_search is None:
            raise RuntimeError("provider-native web search is not configured")
        return await provider_search(query=query, max_results=max_results, model=model)

    def select_provider_web_search_connection(self, model: str | None = None) -> dict[str, Any] | None:
        if model:
            record = self.select_model_connection(model)
            if record:
                return record
        records = [
            record
            for record in self.control_plane.list_active_connections(tenant_id=self.tenant_id)
            if record.get("kind") == "model_provider"
        ]
        for provider in ("moonshot",):
            for record in records:
                if record.get("provider") == provider:
                    return record
        return records[0] if records else None

    async def moonshot_web_search(
        self,
        *,
        record: dict[str, Any],
        query: str,
        max_results: int,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Run Kimi/Moonshot builtin `$web_search` using the active tenant key."""

        endpoint = str(record.get("endpoint") or "").rstrip("/")
        api_key = self.control_plane.secret_value(record, "api_key") or ""
        upstream_model = resolve_upstream_model(record, model or "kimi-k2.6")
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "Use web search when needed, then return strict JSON with keys: summary, results, limitations. "
                    "Each result must include title, url, publish_date, source, key_fact, evidence, reliability. "
                    "Do not add facts that are not supported by search results."
                ),
            },
            {"role": "user", "content": f"Search the web for: {query}. Return at most {max_results} high-quality sources."},
        ]
        tools = [{"type": "builtin_function", "function": {"name": "$web_search"}}]
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                    for _round in range(4):
                        payload = {
                            "model": upstream_model,
                            "messages": messages,
                            "tools": tools,
                            "temperature": 0.6,
                            "stream": False,
                            "thinking": {"type": "disabled"},
                        }
                        response = await client.post(f"{endpoint}/chat/completions", headers=headers, json=payload)
                        response.raise_for_status()
                        data = response.json()
                        choice = first_choice(data)
                        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
                        tool_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
                        if choice.get("finish_reason") == "tool_calls" and tool_calls:
                            messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls})
                            for tool_call in tool_calls:
                                function = tool_call.get("function") if isinstance(tool_call, dict) else {}
                                arguments = function.get("arguments") if isinstance(function, dict) else "{}"
                                messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tool_call.get("id"),
                                        "name": function.get("name") or "$web_search",
                                        "content": arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False),
                                    }
                                )
                            continue
                        content = str(message.get("content") or extract_assistant_content(data))
                        parsed = parse_json_object_loose(content)
                        return normalize_provider_web_search_payload(
                            parsed,
                            raw_content=content,
                            query=query,
                            model=upstream_model,
                            max_results=max_results,
                        )
                    raise RuntimeError("Moonshot web search did not produce a final assistant response")
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if not should_retry_http_status(exc.response.status_code) or attempt >= self.max_retries:
                    raise RuntimeError(
                        provider_error_message(record=record, status_code=exc.response.status_code, detail=exc.response.text)
                    ) from exc
                await asyncio.sleep(retry_delay(2.0, attempt=attempt))
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise RuntimeError(f"Model provider {record.get('provider')} web search timed out after {self.timeout:g}s") from exc
                await asyncio.sleep(retry_delay(2.0, attempt=attempt))
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise RuntimeError(f"Model provider {record.get('provider')} web search failed: {exc}") from exc
                await asyncio.sleep(retry_delay(2.0, attempt=attempt))
        raise RuntimeError(f"Moonshot web search failed after retries: {last_exc}")


def resolve_upstream_model(record: dict[str, Any], requested_model: str) -> str:
    provider = str(record.get("provider") or "")
    requested = str(requested_model or "")
    if provider == "zhipu" and "glm" in requested.lower():
        return "glm-5.1"
    if provider == "minimax" and "minimax" in requested.lower():
        return "MiniMax-M2.7"
    if provider == "moonshot" and not ("kimi" in requested.lower() or "moonshot" in requested.lower()):
        models = capability_model_names(record)
        return first_matching_model(models, ("kimi-k2.6", "kimi-k2.5", "kimi-k2", "kimi", "moonshot")) or "kimi-k2.6"
    if provider == "anthropic" and not requested.lower().startswith("claude"):
        models = capability_model_names(record)
        return first_matching_model(models, ("claude-sonnet", "claude-opus", "claude-3")) or "claude-sonnet-4-5"
    if provider == "openai" and not (requested.lower().startswith("gpt-") or requested.lower().startswith("o")):
        models = capability_model_names(record)
        return first_matching_model(models, ("gpt-5", "gpt-4.1", "gpt-4o", "o3", "o4")) or "gpt-4.1-mini"
    models = capability_model_names(record)
    return models[0] if models and requested not in models else requested


def first_choice(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices") if isinstance(data, dict) else []
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise RuntimeError("Model provider returned no choices")
    return choices[0]


def provider_temperature(*, record: dict[str, Any], model: str, requested: float) -> float:
    """Normalize provider-specific temperature quirks at the gateway boundary."""

    provider = str(record.get("provider") or "").lower()
    model_lower = str(model or "").lower()
    if provider == "moonshot" or "kimi" in model_lower or "moonshot" in model_lower:
        return 1.0
    return float(requested)


def capability_model_names(record: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for capability in record.get("capabilities") or []:
        if not isinstance(capability, dict):
            continue
        for model in capability.get("models") or []:
            names.append(str(model))
    return names


def first_matching_model(models: list[str], prefixes: tuple[str, ...]) -> str | None:
    lowered = [(model, model.lower()) for model in models]
    for prefix in prefixes:
        for original, lower in lowered:
            if lower.startswith(prefix):
                return original
    return models[0] if models else None


def to_anthropic_messages(messages: list[Message]) -> tuple[str, list[dict[str, str]]]:
    system_parts: list[str] = []
    output: list[dict[str, str]] = []
    for message in messages:
        role = str(message.get("role") or "user")
        content = str(message.get("content") or "")
        if role == "system":
            system_parts.append(content)
            continue
        if role not in {"user", "assistant"}:
            role = "user"
        if output and output[-1]["role"] == role:
            output[-1]["content"] += "\n\n" + content
        else:
            output.append({"role": role, "content": content})
    if not output:
        output.append({"role": "user", "content": "Continue."})
    return "\n\n".join(part for part in system_parts if part.strip()), output


def anthropic_response_to_openai_shape(payload: dict[str, Any], *, model: str) -> dict[str, Any]:
    parts = []
    for block in payload.get("content") or []:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    content = "\n".join(parts).strip()
    return {
        "id": payload.get("id"),
        "model": payload.get("model") or model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": payload.get("stop_reason"),
            }
        ],
    }


def model_fallback_chain(model: str) -> list[str]:
    chain = [str(model or "")]
    model_lower = chain[0].lower()
    if "glm" in model_lower:
        chain.extend(split_model_list(os.getenv("GLM_FALLBACK_MODELS", "glm-5.1-standard,minimax-m2.7")))
    elif "minimax" in model_lower:
        chain.extend(split_model_list(os.getenv("MINIMAX_FALLBACK_MODELS", "glm-5.1-standard,glm-5.1")))
    elif "kimi" in model_lower or "moonshot" in model_lower:
        chain.extend(split_model_list(os.getenv("KIMI_FALLBACK_MODELS", "kimi-k2.5,kimi-k2-turbo-preview,moonshot-v1-128k")))
    chain.extend(split_model_list(os.getenv("DEFAULT_FALLBACK_MODELS", "")))
    return unique_model_chain(chain)


def split_model_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def unique_model_chain(models: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for model in models:
        key = model.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(model)
    return result


def should_fallback_model_error(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "contentfilter",
        "content filter",
        "1301",
        "timed out",
        "timeout",
        "temporarily unavailable",
        "insufficient balance",
        "insufficient quota",
        "quota",
        "resource pack",
        "余额不足",
        "无可用资源包",
        "rate limit",
        "429",
        "context window exceeds limit",
        "context length",
        "context window",
        "maximum context",
        "token limit",
        "too many tokens",
        "bad_request_error",
        "500",
        "502",
        "503",
        "504",
        "connection error",
    )
    return any(marker in text for marker in markers)


def format_gateway_fallback_failure(failures: list[tuple[str, Exception]]) -> str:
    return "; ".join(f"{model}: {redact_secret_text(str(exc), limit=300)}" for model, exc in failures)


def provider_error_message(*, record: dict[str, Any], status_code: int, detail: str) -> str:
    provider = record.get("provider") or record.get("id") or "model provider"
    clean = redact_secret_text(detail, limit=700)
    return f"Model provider {provider} returned HTTP {status_code}: {clean}"


class model_semaphore:
    def __init__(self, model: str, *, glm_semaphore: asyncio.Semaphore) -> None:
        self.model = model
        self.glm_semaphore = glm_semaphore
        self._semaphore: asyncio.Semaphore | None = None

    async def __aenter__(self) -> None:
        if "glm" in str(self.model or "").lower():
            self._semaphore = self.glm_semaphore
            await self._semaphore.acquire()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._semaphore is not None:
            self._semaphore.release()
