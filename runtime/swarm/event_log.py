from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from runtime.redaction import redact_sensitive
from runtime.swarm.contracts import event_contract
from runtime.swarm.target_registry import canonical_target


DEFAULT_SWARM_EVENT_LOG_PATH = "logs/swarm_events.jsonl"
DOMAIN_WORKFLOW_EVENT_TYPES = {
    "code.repo_scout.completed",
    "code.patch_plan.created",
    "code.test_gate.completed",
    "code.regression_judge.completed",
    "compliance.policy_interpreted",
    "compliance.dlp.completed",
    "compliance.rbac.completed",
    "compliance.approval.requested",
    "compliance.approval.resolved",
    "compliance.evidence_mapped",
    "compliance.escalation.created",
    "compliance.retention.decided",
    "research.claims.decomposed",
    "research.sources.retrieved",
    "research.source_quality.rated",
    "research.citation_audit.completed",
    "research.contradictions.mapped",
    "research.evidence_gate.completed",
}


def swarm_event(
    *,
    event_type: str,
    run_id: str,
    actor: str,
    tenant_id: str = "default",
    target: Any = "run",
    lifecycle_state: str | None = None,
    summary: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return event_contract(
        event_type=event_type,
        run_id=run_id,
        tenant_id=tenant_id,
        actor=actor,
        target=target,
        lifecycle_state=lifecycle_state,
        summary=summary,
        payload=redact_sensitive(payload or {}),
        redaction_status="redacted",
    )


def domain_workflow_event(
    *,
    workflow: str,
    phase: str,
    run_id: str,
    actor: str,
    tenant_id: str = "default",
    target: Any = "run",
    lifecycle_state: str | None = None,
    summary: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a typed event for capability-owned code/compliance/research workflows."""

    event_type = f"{str(workflow).strip()}.{str(phase).strip()}"
    resolved_target, alias_source = resolve_protocol_target_alias(target)
    return swarm_event(
        event_type=event_type,
        run_id=run_id,
        tenant_id=tenant_id,
        actor=actor,
        target=resolved_target,
        lifecycle_state=lifecycle_state,
        summary=summary or event_type,
        payload={
            **(payload or {}),
            "domain_workflow_event": event_type in DOMAIN_WORKFLOW_EVENT_TYPES,
            "target_alias_source": alias_source,
            "known_domain_event_types": sorted(DOMAIN_WORKFLOW_EVENT_TYPES)
            if event_type not in DOMAIN_WORKFLOW_EVENT_TYPES
            else [],
        },
    )


def resolve_protocol_target_alias(target: Any) -> tuple[str, str]:
    raw = str(target or "").strip()
    if not raw:
        return "run", "empty"
    canonical = canonical_target(raw)
    if canonical != raw:
        return canonical, "global_target_registry"
    try:
        from runtime.capability_registry import CapabilityRegistry
        from runtime.swarm.protocol import capability_protocol_bundle

        manifests, _diagnostics = CapabilityRegistry().load()
        capabilities = [manifest.to_public_dict() for manifest in manifests]
        aliases = capability_protocol_bundle(capabilities).get("target_aliases", {})
    except Exception:  # noqa: BLE001
        aliases = {}
    for key in (raw, raw.lower()):
        resolved = aliases.get(key) if isinstance(aliases, dict) else None
        if resolved:
            return str(resolved), "capability_protocol_target_alias"
    return canonical, "unresolved"


def append_swarm_events(events: Iterable[dict[str, Any]], *, path: Path | None = None) -> None:
    records = [normalize_event(event) for event in events if isinstance(event, dict)]
    if not records:
        return
    output_path = path or Path(os.getenv("SWARM_EVENT_LOG_PATH", DEFAULT_SWARM_EVENT_LOG_PATH))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_swarm_events(
    *,
    run_id: str | None = None,
    tenant_id: str | None = None,
    limit: int = 200,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    input_path = path or Path(os.getenv("SWARM_EVENT_LOG_PATH", DEFAULT_SWARM_EVENT_LOG_PATH))
    if not input_path.exists():
        return []
    try:
        lines = input_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: list[dict[str, Any]] = []
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if run_id and item.get("run_id") != run_id:
            continue
        normalized = normalize_event(item)
        if not visible_to_tenant(normalized, tenant_id):
            continue
        records.append(normalized)
        if len(records) >= limit:
            break
    return list(reversed(records))


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    if "schema_version" in event and "event_type" in event:
        redacted = redact_sensitive(event)
        if isinstance(redacted, dict):
            redacted.setdefault("tenant_id", str(event.get("tenant_id") or "default"))
            return redacted
        return {}
    event_type = str(event.get("event_type") or event.get("event") or "swarm.event")
    known = {
        "event_type",
        "event",
        "run_id",
        "tenant_id",
        "actor",
        "source_module",
        "source_agent",
        "target",
        "lifecycle_state",
        "summary",
    }
    payload = {key: value for key, value in event.items() if key not in known and key != "payload"}
    if isinstance(event.get("payload"), dict):
        payload.update(event["payload"])
    signal = event.get("signal") if isinstance(event.get("signal"), dict) else {}
    target = event.get("target") or signal.get("target") or "run"
    return swarm_event(
        event_type=event_type,
        run_id=str(event.get("run_id") or payload.get("run_id") or "unknown"),
        tenant_id=str(event.get("tenant_id") or payload.get("tenant_id") or "default"),
        actor=str(event.get("actor") or event.get("source_module") or event.get("source_agent") or "swarm"),
        target=target,
        lifecycle_state=event.get("lifecycle_state"),
        summary=str(event.get("summary") or event_type),
        payload=payload,
    )


def visible_to_tenant(record: dict[str, Any], tenant_id: str | None) -> bool:
    if tenant_id is None:
        return True
    return str(record.get("tenant_id") or "default") == str(tenant_id)
