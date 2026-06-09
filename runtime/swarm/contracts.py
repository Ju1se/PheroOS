from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Any
from uuid import uuid4

from runtime.swarm.authority import signal_authority_level
from runtime.swarm.lifecycle import blocking_status_for_signal, lifecycle_state_for_signal
from runtime.swarm.target_registry import canonical_target, target_kind


SWARM_SIGNAL_SCHEMA_VERSION = "pheroos.signal.v1"
SWARM_EVENT_SCHEMA_VERSION = "pheroos.event.v1"


@dataclass(frozen=True)
class SignalContract:
    signal_id: str
    signal_type: str
    target: str
    canonical_target: str
    target_kind: str
    lifecycle_state: str
    blocking_status: str
    authority_level: int
    source_agent: str | None = None
    source_module: str | None = None
    schema_version: str = SWARM_SIGNAL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "signal_id": self.signal_id,
            "signal_type": self.signal_type,
            "target": self.target,
            "canonical_target": self.canonical_target,
            "target_kind": self.target_kind,
            "lifecycle_state": self.lifecycle_state,
            "blocking_status": self.blocking_status,
            "authority_level": self.authority_level,
            "source_agent": self.source_agent,
            "source_module": self.source_module,
        }


@dataclass(frozen=True)
class SwarmEventContract:
    event_type: str
    run_id: str
    actor: str
    tenant_id: str = "default"
    event_id: str = field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")
    timestamp: float = field(default_factory=time)
    target: str = "run"
    canonical_target: str = "run"
    lifecycle_state: str | None = None
    summary: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    redaction_status: str = "redacted"
    schema_version: str = SWARM_EVENT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "actor": self.actor,
            "target": self.target,
            "canonical_target": self.canonical_target,
            "lifecycle_state": self.lifecycle_state,
            "summary": self.summary,
            "payload": self.payload,
            "redaction_status": self.redaction_status,
        }


def signal_contract(signal: dict[str, Any]) -> dict[str, Any]:
    raw_target = str(signal.get("target") or "")
    canonical = canonical_target(raw_target)
    return SignalContract(
        signal_id=str(signal.get("id") or ""),
        signal_type=str(signal.get("type") or ""),
        target=raw_target,
        canonical_target=canonical,
        target_kind=target_kind(canonical),
        lifecycle_state=lifecycle_state_for_signal(signal).value,
        blocking_status=blocking_status_for_signal(signal).value,
        authority_level=signal_authority_level(signal),
        source_agent=empty_to_none(signal.get("source_agent")),
        source_module=empty_to_none(signal.get("source_module")),
    ).to_dict()


def event_contract(
    *,
    event_type: str,
    run_id: str,
    actor: str,
    tenant_id: str = "default",
    target: Any = "run",
    lifecycle_state: str | None = None,
    summary: str = "",
    payload: dict[str, Any] | None = None,
    redaction_status: str = "redacted",
) -> dict[str, Any]:
    raw_target = str(target or "run")
    return SwarmEventContract(
        event_type=event_type,
        run_id=run_id,
        tenant_id=str(tenant_id or "default"),
        actor=actor,
        target=raw_target,
        canonical_target=canonical_target(raw_target),
        lifecycle_state=lifecycle_state,
        summary=summary,
        payload=payload or {},
        redaction_status=redaction_status,
    ).to_dict()


def empty_to_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
