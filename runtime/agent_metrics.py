from __future__ import annotations

from contextvars import ContextVar, Token
from time import perf_counter
from typing import Any


_AGENT_METRICS: ContextVar[list[dict[str, Any]] | None] = ContextVar("agent_metrics", default=None)


def start_agent_metrics() -> Token:
    return _AGENT_METRICS.set([])


def reset_agent_metrics(token: Token) -> None:
    _AGENT_METRICS.reset(token)


def current_agent_metrics() -> list[dict[str, Any]]:
    metrics = _AGENT_METRICS.get()
    return list(metrics or [])


def metric_started_at() -> float:
    return perf_counter()


def record_agent_metric(
    *,
    agent: str,
    model: str | None,
    started_at: float,
    status: str,
    failure_reason: Any = None,
    model_used: bool = True,
) -> None:
    metrics = _AGENT_METRICS.get()
    if metrics is None:
        return

    metrics.append(
        {
            "agent": agent,
            "model": model,
            "model_used": model_used,
            "duration_ms": round(max(perf_counter() - started_at, 0.0) * 1000, 2),
            "status": status,
            "failure_reason": truncate_failure_reason(failure_reason),
        }
    )


def truncate_failure_reason(value: Any, *, limit: int = 500) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "..."
