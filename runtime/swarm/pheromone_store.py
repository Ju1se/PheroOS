from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from runtime.redaction import redact_sensitive
from runtime.swarm.contracts import signal_contract
from runtime.swarm.event_log import append_swarm_events, read_swarm_events
from runtime.swarm.events import explicit_runtime_events_from_run
from runtime.swarm.trace_store import SwarmTraceStore

DEFAULT_SWARM_EVENT_LOG_PATH = "logs/swarm_events.jsonl"
DEFAULT_PHEROMONE_SIGNAL_LOG_PATH = "logs/pheromone_signals.jsonl"


def swarm_trace_enabled() -> bool:
    value = os.getenv("SWARM_TRACE_LOG_ENABLED", os.getenv("AGENT_AUDIT_LOG_ENABLED", "true")).strip().lower()
    return value in {"1", "true", "yes", "on"}


def append_swarm_trace(run: dict[str, Any]) -> None:
    if not swarm_trace_enabled():
        return
    run_id = str(run.get("run_id") or "")
    if not run_id:
        return
    tenant_id = trace_tenant_id(run)
    append_events(run_id=run_id, tenant_id=tenant_id, events=run.get("pheromone_trace") or [])
    append_events(run_id=run_id, tenant_id=tenant_id, events=explicit_runtime_events_from_run(run))
    append_signals(run_id=run_id, tenant_id=tenant_id, signals=(run.get("pheromone_field_snapshot") or {}).get("signals") or [])
    if sqlite_trace_enabled():
        SwarmTraceStore().persist_run_trace(run)


def sqlite_trace_enabled() -> bool:
    value = os.getenv("SWARM_TRACE_SQLITE_ENABLED", "true").strip().lower()
    return value in {"1", "true", "yes", "on"}


def append_events(*, run_id: str, events: list[Any], tenant_id: str = "default") -> None:
    path = Path(os.getenv("SWARM_EVENT_LOG_PATH", DEFAULT_SWARM_EVENT_LOG_PATH))
    records = []
    for event in events:
        if not isinstance(event, dict):
            continue
        records.append({"run_id": run_id, "tenant_id": tenant_id, **event})
    append_swarm_events(records, path=path)


def append_signals(*, run_id: str, signals: list[Any], tenant_id: str = "default") -> None:
    path = Path(os.getenv("PHEROMONE_SIGNAL_LOG_PATH", DEFAULT_PHEROMONE_SIGNAL_LOG_PATH))
    records = []
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        safe_signal = redact_sensitive({"run_id": run_id, "tenant_id": tenant_id, **signal})
        if isinstance(safe_signal, dict):
            safe_signal.setdefault("tenant_id", tenant_id)
            safe_signal["contract"] = signal_contract(safe_signal)
            records.append(safe_signal)
    append_jsonl(path, records)


def read_signals(*, run_id: str | None = None, tenant_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    path = Path(os.getenv("PHEROMONE_SIGNAL_LOG_PATH", DEFAULT_PHEROMONE_SIGNAL_LOG_PATH))
    return read_jsonl(path=path, run_id=run_id, tenant_id=tenant_id, limit=limit)


def read_events(*, run_id: str | None = None, tenant_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    path = Path(os.getenv("SWARM_EVENT_LOG_PATH", DEFAULT_SWARM_EVENT_LOG_PATH))
    return read_swarm_events(path=path, run_id=run_id, tenant_id=tenant_id, limit=limit)


def append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(*, path: Path, run_id: str | None, tenant_id: str | None, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if run_id and item.get("run_id") != run_id:
            continue
        if tenant_id is not None and str(item.get("tenant_id") or "default") != str(tenant_id):
            continue
        records.append(item)
        if len(records) >= limit:
            break
    return list(reversed(records))


def sanitize_swarm_payload(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = redact_sensitive(payload)
    return redacted if isinstance(redacted, dict) else {}


def trace_tenant_id(run: dict[str, Any]) -> str:
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    return str(run.get("tenant_id") or metadata.get("tenant_id") or os_plan.get("tenant_id") or "default")
