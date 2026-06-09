from __future__ import annotations

import json
import os
import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx


Message = dict[str, str]


class LLMClient(Protocol):
    async def chat(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float = 0.0,
    ) -> str:
        """Return assistant text from an OpenAI-compatible chat completion."""


@dataclass(frozen=True)
class ModelConfig:
    orchestrator: str = "glm-5.1"
    memory_agent: str = "glm-5.1"
    executor: str = "minimax-m2.7"
    wrds_agent: str = "glm-5.1"
    research_agent: str = "glm-5.1"
    research_agent_fallback: str = "minimax-m2.7"
    quant_agent: str = "glm-5.1"
    quant_agent_fallback: str = "minimax-m2.7"
    domain_expert: str = "glm-5.1"
    cio_agent: str = "glm-5.1"
    data_auditor_agent: str = "glm-5.1"
    fundamental_analyst_agent: str = "glm-5.1"
    quant_research_agent: str = "glm-5.1"
    industry_strategy_agent: str = "glm-5.1"
    market_execution_agent: str = "minimax-m2.7"
    risk_manager_agent: str = "glm-5.1"
    red_team_agent: str = "minimax-m2.7"
    committee_member_fallback: str = "minimax-m2.7"
    committee_challenge: str = "minimax-m2.7"
    investment_committee: str = "glm-5.1"
    investment_committee_fallback: str = "minimax-m2.7"
    critic: str = "minimax-m2.7"
    writer: str = "minimax-m2.7"
    final_judge: str = "glm-5.1"
    glm_fallback_models: str = "glm-5.1-standard,minimax-m2.7"
    minimax_fallback_models: str = "glm-5.1-standard,glm-5.1"
    default_fallback_models: str = ""
    agent_model_overrides: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "ModelConfig":
        return cls(
            orchestrator=os.getenv("ORCHESTRATOR_MODEL", cls.orchestrator),
            memory_agent=os.getenv("MEMORY_AGENT_MODEL", cls.memory_agent),
            executor=os.getenv("EXECUTOR_MODEL", cls.executor),
            wrds_agent=os.getenv("WRDS_AGENT_MODEL", cls.wrds_agent),
            research_agent=os.getenv("RESEARCH_AGENT_MODEL", cls.research_agent),
            research_agent_fallback=os.getenv("RESEARCH_AGENT_FALLBACK_MODEL", cls.research_agent_fallback),
            quant_agent=os.getenv("QUANT_AGENT_MODEL", cls.quant_agent),
            quant_agent_fallback=os.getenv("QUANT_AGENT_FALLBACK_MODEL", cls.quant_agent_fallback),
            domain_expert=os.getenv("DOMAIN_EXPERT_MODEL", cls.domain_expert),
            cio_agent=os.getenv("CIO_AGENT_MODEL", cls.cio_agent),
            data_auditor_agent=os.getenv("DATA_AUDITOR_AGENT_MODEL", cls.data_auditor_agent),
            fundamental_analyst_agent=os.getenv("FUNDAMENTAL_ANALYST_AGENT_MODEL", cls.fundamental_analyst_agent),
            quant_research_agent=os.getenv("QUANT_RESEARCH_AGENT_MODEL", cls.quant_research_agent),
            industry_strategy_agent=os.getenv("INDUSTRY_STRATEGY_AGENT_MODEL", cls.industry_strategy_agent),
            market_execution_agent=os.getenv("MARKET_EXECUTION_AGENT_MODEL", cls.market_execution_agent),
            risk_manager_agent=os.getenv("RISK_MANAGER_AGENT_MODEL", cls.risk_manager_agent),
            red_team_agent=os.getenv("RED_TEAM_AGENT_MODEL", cls.red_team_agent),
            committee_member_fallback=os.getenv("COMMITTEE_MEMBER_FALLBACK_MODEL", cls.committee_member_fallback),
            committee_challenge=os.getenv("COMMITTEE_CHALLENGE_MODEL", cls.committee_challenge),
            investment_committee=os.getenv("INVESTMENT_COMMITTEE_MODEL", cls.investment_committee),
            investment_committee_fallback=os.getenv("INVESTMENT_COMMITTEE_FALLBACK_MODEL", cls.investment_committee_fallback),
            critic=os.getenv("CRITIC_MODEL", cls.critic),
            writer=os.getenv("WRITER_MODEL", cls.writer),
            final_judge=os.getenv("FINAL_JUDGE_MODEL", cls.final_judge),
            glm_fallback_models=os.getenv("GLM_FALLBACK_MODELS", cls.glm_fallback_models),
            minimax_fallback_models=os.getenv("MINIMAX_FALLBACK_MODELS", cls.minimax_fallback_models),
            default_fallback_models=os.getenv("DEFAULT_FALLBACK_MODELS", cls.default_fallback_models),
        )

    def model_for(self, model_attr: Any, *, fallback_attr: str = "committee_member_fallback") -> str:
        key = str(model_attr or "").strip()
        if key and key in self.agent_model_overrides:
            return self.agent_model_overrides[key]
        if key and hasattr(self, key):
            return str(getattr(self, key))
        if fallback_attr and hasattr(self, fallback_attr):
            return str(getattr(self, fallback_attr))
        return self.committee_member_fallback


@dataclass(frozen=True)
class ProviderWebSearchConfig:
    enabled: bool = True
    model: str = "glm-5.1-standard"
    search_engine: str = "search-prime"
    search_recency_filter: str = "noLimit"
    content_size: str = "medium"
    max_results: int = 5

    @classmethod
    def from_env(cls) -> "ProviderWebSearchConfig":
        return cls(
            enabled=parse_bool(os.getenv("PROVIDER_WEB_SEARCH_ENABLED"), default=cls.enabled),
            model=os.getenv("PROVIDER_WEB_SEARCH_MODEL", cls.model),
            search_engine=os.getenv("PROVIDER_WEB_SEARCH_ENGINE", cls.search_engine),
            search_recency_filter=os.getenv("PROVIDER_WEB_SEARCH_RECENCY_FILTER", cls.search_recency_filter),
            content_size=os.getenv("PROVIDER_WEB_SEARCH_CONTENT_SIZE", cls.content_size),
            max_results=clamp_int(os.getenv("PROVIDER_WEB_SEARCH_MAX_RESULTS"), minimum=1, maximum=10, default=cls.max_results),
        )


class LiteLLMClient:
    """OpenAI-compatible client pointed at LiteLLM Proxy."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("LITELLM_BASE_URL") or "http://127.0.0.1:4000/v1").rstrip("/")
        self.api_key = api_key or os.getenv("LITELLM_MASTER_KEY") or "sk-local-master-key"
        self.timeout = timeout or float(os.getenv("LITELLM_TIMEOUT", "2000"))
        self.web_search_config = ProviderWebSearchConfig.from_env()
        self._glm_semaphore = asyncio.Semaphore(
            clamp_int(os.getenv("GLM_MAX_CONCURRENCY"), minimum=1, maximum=16, default=2)
        )
        self.max_retries = clamp_int(os.getenv("LITELLM_CLIENT_MAX_RETRIES"), minimum=0, maximum=6, default=3)
        self.retry_base_seconds = float(os.getenv("LITELLM_RETRY_BASE_SECONDS", "2.0"))

    async def chat(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float = 0.0,
    ) -> str:
        data = await self.chat_completion(model=model, messages=messages, temperature=temperature)
        return extract_assistant_content(data)

    async def chat_completion(
        self,
        *,
        model: str,
        messages: list[Message],
        temperature: float = 0.0,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with model_semaphore(model, glm_semaphore=self._glm_semaphore):
                    async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                        response = await client.post(
                            f"{self.base_url}/chat/completions",
                            headers=headers,
                            json=payload,
                        )
                        response.raise_for_status()
                        data = response.json()
                break
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                detail = exc.response.text[:1_000]
                if not should_retry_http_status(exc.response.status_code) or attempt >= self.max_retries:
                    raise RuntimeError(f"LiteLLM returned HTTP {exc.response.status_code}: {detail}") from exc
                await asyncio.sleep(retry_delay(self.retry_base_seconds, attempt=attempt))
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise RuntimeError(f"LiteLLM request timed out after {self.timeout:g}s ({type(exc).__name__})") from exc
                await asyncio.sleep(retry_delay(self.retry_base_seconds, attempt=attempt))
            except httpx.HTTPError as exc:
                last_exc = exc
                detail = str(exc) or repr(exc)
                if attempt >= self.max_retries:
                    raise RuntimeError(f"LiteLLM request failed ({type(exc).__name__}): {detail}") from exc
                await asyncio.sleep(retry_delay(self.retry_base_seconds, attempt=attempt))
        else:  # pragma: no cover - defensive; loop either breaks or raises above.
            raise RuntimeError(f"LiteLLM request failed after retries: {last_exc}")

        return data

    async def provider_web_search(
        self,
        *,
        query: str,
        max_results: int = 5,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Use provider-native web search through LiteLLM Chat Completions."""

        query = str(query or "").strip()
        if not query:
            raise ValueError("query must be a non-empty string")

        config = self.web_search_config
        max_results = clamp_int(max_results, minimum=1, maximum=10, default=config.max_results)
        search_prompt = (
            "Summarize {{ search_result }} as JSON with keys: summary, results, limitations. "
            "Each result must include title, url or link, publish_date or date, source, key_fact, evidence, reliability. "
            "Do not add facts that are not supported by the search results."
        )
        tools = [
            {
                "type": "web_search",
                "web_search": {
                    "enable": "True",
                    "search_engine": config.search_engine,
                    "search_result": "True",
                    "search_prompt": search_prompt,
                    "count": str(max_results),
                    "search_recency_filter": config.search_recency_filter,
                    "content_size": config.content_size,
                },
            }
        ]
        data = await self.chat_completion(
            model=model or config.model,
            temperature=0.0,
            tools=tools,
            messages=[
                {
                    "role": "user",
                    "content": f"Search the web for {query} and return JSON with sources.",
                },
            ],
        )
        content = extract_assistant_content(data)
        parsed = parse_json_object_loose(content)
        return normalize_provider_web_search_payload(
            parsed,
            raw_content=content,
            query=query,
            model=model or config.model,
            max_results=max_results,
        )


def extract_assistant_content(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LiteLLM returned no choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise RuntimeError("LiteLLM returned an invalid assistant message")
    return content


def parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None or not str(value).strip():
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def clamp_int(value: Any, *, minimum: int, maximum: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))


def parse_json_object_loose(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].lstrip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].rstrip().endswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            payload = json_loads(candidate)
        except ValueError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def json_loads(value: str) -> Any:
    return json.loads(value)


def should_retry_http_status(status_code: int) -> bool:
    return status_code in {429, 500, 502, 503, 504}


def retry_delay(base_seconds: float, *, attempt: int) -> float:
    base = max(float(base_seconds), 0.0)
    return min(base * (2**attempt), 30.0)


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


def normalize_provider_web_search_payload(
    payload: dict[str, Any] | None,
    *,
    raw_content: str,
    query: str,
    model: str,
    max_results: int,
) -> dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    raw_results = first_list(payload, "results", "sources", "search_results", "search_result")
    results = []
    for item in raw_results[:max_results]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("link") or "").strip()
        title = str(item.get("title") or item.get("source") or url or "Untitled source").strip()
        snippet = str(item.get("evidence") or item.get("summary") or item.get("content") or item.get("key_fact") or "").strip()
        results.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
                "publish_date": item.get("publish_date") or item.get("date"),
                "source": item.get("source") or item.get("media"),
                "key_fact": item.get("key_fact"),
                "evidence": item.get("evidence") or snippet,
                "reliability": item.get("reliability") or "provider_native_search",
            }
        )

    return {
        "query": query,
        "searched_query": query,
        "engine": "provider_native_web_search",
        "provider_model": model,
        "summary": payload.get("summary") or raw_content,
        "results": results,
        "limitations": first_list(payload, "limitations", "evidence_gaps"),
        "raw_content": raw_content,
        "source_grounding": "provider_native_web_search",
    }


def first_list(payload: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []
