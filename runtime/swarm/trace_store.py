from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from runtime.redaction import redact_sensitive
from runtime.swarm.contracts import signal_contract
from runtime.swarm.event_log import normalize_event
from runtime.swarm.events import explicit_runtime_events_from_run, governance_events_from_run
from runtime.swarm.lifecycle import is_active_blocker
from runtime.swarm.snapshot_builder import build_governance_snapshot
from runtime.swarm.target_registry import canonical_target
from runtime.swarm.tool_policy_resolver import tool_policy_event_type


DEFAULT_SWARM_TRACE_DB_PATH = ".local/swarm_trace.sqlite3"


class SwarmTraceStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.getenv("SWARM_TRACE_DB_PATH", DEFAULT_SWARM_TRACE_DB_PATH))

    def persist_run_trace(self, run: dict[str, Any]) -> None:
        run_id = str(run.get("run_id") or "")
        if not run_id:
            return
        tenant_id = trace_tenant_id(run)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            ensure_schema(conn)
            persist_run_metadata(conn, run_id, tenant_id, run)
            persist_events(conn, run_id, os_routing_events(run))
            persist_events(conn, run_id, run.get("pheromone_trace") or [])
            persist_events(conn, run_id, explicit_runtime_events_from_run(run))
            persist_events(conn, run_id, governance_events_from_run(run))
            persist_signals(conn, run_id, (run.get("pheromone_field_snapshot") or {}).get("signals") or [])
            persist_quorum(conn, run_id, run.get("quorum_trace") if isinstance(run.get("quorum_trace"), dict) else {})
            persist_evidence_graph(
                conn,
                run_id,
                run.get("evidence_graph") if isinstance(run.get("evidence_graph"), dict) else {},
            )
            persist_agent_allocation(conn, run_id, run.get("agent_allocation_trace") or [])
            persist_tool_events(conn, run_id, run.get("execution_log") or [])
            persist_permission_events(
                conn,
                run_id,
                (run.get("metadata") or {}).get("permission_grants") if isinstance(run.get("metadata"), dict) else [],
            )

    def timeline(self, *, run_id: str, limit: int = 500, tenant_id: str | None = None) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            ensure_schema(conn)
            if not run_visible_to_tenant(conn, run_id, tenant_id):
                return []
            rows = conn.execute(
                """
                select 'event' as record_type, timestamp, event_type as type, actor, target,
                       canonical_target, lifecycle_state, summary, payload_json
                  from swarm_events
                 where run_id = ?
                union all
                select 'signal' as record_type, created_at as timestamp, type, source_module as actor,
                       target, canonical_target, lifecycle_state, content as summary, payload_json
                  from pheromone_signals
                 where run_id = ?
                 order by timestamp asc
                 limit ?
                """,
                (run_id, run_id, limit),
            ).fetchall()
        return timeline_records_prefer_events([row_to_payload(row) for row in rows])

    def why_blocked(self, *, run_id: str, target: str, tenant_id: str | None = None) -> dict[str, Any]:
        canonical = canonical_target(target)
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            ensure_schema(conn)
            if not run_visible_to_tenant(conn, run_id, tenant_id):
                return {
                    "run_id": run_id,
                    "target": target,
                    "canonical_target": canonical,
                    "blocked": False,
                    "source": "missing",
                    "blocking_signals": [],
                    "related_nodes": [],
                    "protocol_lineage": {},
                }
            run_payload = fetch_run_payload(conn, run_id)
            signal_event_rows = blocking_signal_event_rows(conn, run_id, canonical)
            signal_rows = conn.execute(
                """
                select * from pheromone_signals
                 where run_id = ? and canonical_target = ? and blocking = 1
                 order by created_at asc
                """,
                (run_id, canonical),
            ).fetchall()
            node_rows = conn.execute(
                """
                select * from evidence_nodes
                 where run_id = ? and canonical_target = ? and kind in ('signal', 'output_permission')
                 order by id asc
                """,
                (run_id, canonical),
            ).fetchall()
            swarm_plan = swarm_plan_with_event_protocols(conn, run_id, run_payload)
        event_signals = [blocking_signal_record_from_event(row_to_payload(row)) for row in signal_event_rows]
        table_signals = [row_to_payload(row) for row in signal_rows]
        blocking_signals = event_signals if event_signals else table_signals
        source = "swarm_events" if event_signals else "pheromone_signals" if table_signals else "none"
        return {
            "run_id": run_id,
            "target": target,
            "canonical_target": canonical,
            "blocked": bool(blocking_signals),
            "source": source,
            "blocking_signals": blocking_signals,
            "related_nodes": [row_to_payload(row) for row in node_rows],
            "protocol_lineage": target_protocol_lineage(swarm_plan, canonical),
        }

    def why_committed(self, *, run_id: str, tenant_id: str | None = None) -> dict[str, Any]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            ensure_schema(conn)
            if not run_visible_to_tenant(conn, run_id, tenant_id):
                return {"run_id": run_id, "status": "missing"}
            run_payload = fetch_run_payload(conn, run_id)
            swarm_plan = swarm_plan_with_event_protocols(conn, run_id, run_payload)
            event_row = conn.execute(
                """
                select * from swarm_events
                 where run_id = ? and event_type = 'candidate.committed'
                 order by id desc
                 limit 1
                """,
                (run_id,),
            ).fetchone()
            if event_row is not None:
                event = row_to_payload(event_row)
                payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                quorum_trace = payload.get("quorum_trace") if isinstance(payload.get("quorum_trace"), dict) else {}
                if not quorum_trace:
                    quorum_trace = {
                        "status": payload.get("quorum_status") or "committed",
                        "committed_candidate": payload.get("candidate") if isinstance(payload.get("candidate"), dict) else {},
                        "candidate_source": payload.get("candidate_source"),
                    }
                lineage = candidate_protocol_lineage(swarm_plan, quorum_trace)
                return {
                    "run_id": run_id,
                    "status": "found",
                    "source": "candidate_event",
                    "event": event,
                    "quorum_trace": quorum_trace,
                    "protocol_lineage": lineage,
                }
            row = conn.execute(
                "select * from quorum_decisions where run_id = ? order by id desc limit 1",
                (run_id,),
            ).fetchone()
        if row is None:
            return {"run_id": run_id, "status": "missing"}
        row_payload = row_to_payload(row)
        quorum_trace = row_payload.get("payload", {})
        return {
            "run_id": run_id,
            "status": "found",
            "source": "quorum_table",
            "quorum_trace": quorum_trace,
            "protocol_lineage": candidate_protocol_lineage(swarm_plan, quorum_trace),
        }

    def evidence_graph(self, *, run_id: str, tenant_id: str | None = None) -> dict[str, Any]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            ensure_schema(conn)
            if not run_visible_to_tenant(conn, run_id, tenant_id):
                return {"run_id": run_id, "nodes": [], "edges": []}
            nodes = conn.execute(
                "select * from evidence_nodes where run_id = ? order by id asc",
                (run_id,),
            ).fetchall()
            edges = conn.execute(
                "select * from evidence_edges where run_id = ? order by id asc",
                (run_id,),
            ).fetchall()
            event_rows = conn.execute(
                """
                select * from swarm_events
                 where run_id = ?
                   and (
                        event_type like 'claim.%'
                     or event_type = 'artifact.quarantined'
                     or event_type like 'signal.%'
                   )
                 order by id asc
                """,
                (run_id,),
            ).fetchall()
        node_payloads = [row_to_payload(row) for row in nodes]
        edge_payloads = [row_to_payload(row) for row in edges]
        event_graph = evidence_graph_from_events([row_to_payload(row) for row in event_rows])
        merged_nodes = merge_evidence_nodes(event_graph["nodes"], node_payloads)
        return {
            "run_id": run_id,
            "source": evidence_graph_source(event_graph, node_payloads, edge_payloads),
            "nodes": merged_nodes,
            "edges": edge_payloads if edge_payloads else event_graph["edges"],
        }

    def agent_allocation(self, *, run_id: str, tenant_id: str | None = None) -> dict[str, Any]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            ensure_schema(conn)
            if not run_visible_to_tenant(conn, run_id, tenant_id):
                return {"run_id": run_id, "data": []}
            event_rows = event_rows_with_prefix(conn, run_id, "agent.")
            if event_rows:
                return {
                    "run_id": run_id,
                    "source": "swarm_events",
                    "data": [agent_allocation_record_from_event(row_to_payload(row)) for row in event_rows],
                }
            rows = conn.execute(
                "select * from agent_profile_events where run_id = ? order by id asc",
                (run_id,),
            ).fetchall()
        return {"run_id": run_id, "source": "agent_profile_events", "data": [row_to_payload(row) for row in rows]}

    def why_agent(self, *, run_id: str, agent_id: str, tenant_id: str | None = None) -> dict[str, Any]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            ensure_schema(conn)
            if not run_visible_to_tenant(conn, run_id, tenant_id):
                return {
                    "run_id": run_id,
                    "agent_id": agent_id,
                    "status": "missing",
                    "allocation": {},
                    "allocation_events": [],
                    "target_pressure": [],
                    "agent_selection_policy": {},
                    "routing_trace": [],
                    "protocol_lineage": {},
                }
            payload = fetch_run_payload(conn, run_id)
            swarm_plan = swarm_plan_with_event_protocols(conn, run_id, payload)
            event_rows = event_rows_with_prefix(conn, run_id, "agent.")
            rows = conn.execute(
                "select * from agent_profile_events where run_id = ? order by id asc",
                (run_id,),
            ).fetchall()
        event_records = [agent_allocation_record_from_event(row_to_payload(row)) for row in event_rows]
        table_records = [row_to_payload(row) for row in rows]
        events = event_records if event_records else table_records
        matching_events = [event for event in events if agent_identifier_matches(event.get("agent"), agent_id)]
        allocations = [allocation_from_agent_event(event) for event in matching_events]
        allocations.extend(find_agent_allocations(payload, agent_id))
        allocation = allocations[0] if allocations else {}
        return {
            "run_id": run_id,
            "agent_id": agent_id,
            "status": "found" if allocation else "missing",
            "activated": allocation.get("activated") if isinstance(allocation, dict) else None,
            "activation_reason": agent_activation_reason(allocation),
            "allocation": allocation,
            "allocation_events": matching_events,
            "target_pressure": agent_target_pressure(allocation),
            "agent_selection_policy": swarm_plan.get("agent_selection_policy") if isinstance(swarm_plan.get("agent_selection_policy"), dict) else {},
            "routing_trace": swarm_plan.get("routing_trace") if isinstance(swarm_plan.get("routing_trace"), list) else [],
            "os_routing_trace": os_routing_trace_from_payload(payload),
            "protocol_source": swarm_plan.get("protocol_source"),
            "selection_mode": swarm_plan.get("selection_mode"),
            "activated_agents": swarm_plan.get("activated_agents") if isinstance(swarm_plan.get("activated_agents"), list) else [],
            "protocol_lineage": agent_protocol_lineage(swarm_plan, allocation),
        }

    def tool_events(self, *, run_id: str, tenant_id: str | None = None) -> dict[str, Any]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            ensure_schema(conn)
            if not run_visible_to_tenant(conn, run_id, tenant_id):
                return {"run_id": run_id, "data": []}
            event_rows = event_rows_with_prefix(conn, run_id, "tool.")
            if event_rows:
                return {
                    "run_id": run_id,
                    "source": "swarm_events",
                    "data": [tool_record_from_event(row_to_payload(row)) for row in event_rows],
                }
            rows = conn.execute(
                "select * from tool_events where run_id = ? order by id asc",
                (run_id,),
            ).fetchall()
        return {"run_id": run_id, "source": "tool_events", "data": [row_to_payload(row) for row in rows]}

    def permission_events(self, *, run_id: str, tenant_id: str | None = None) -> dict[str, Any]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            ensure_schema(conn)
            if not run_visible_to_tenant(conn, run_id, tenant_id):
                return {"run_id": run_id, "data": []}
            event_rows = event_rows_with_prefix(conn, run_id, "permission.")
            if event_rows:
                return {
                    "run_id": run_id,
                    "source": "swarm_events",
                    "data": [permission_record_from_event(row_to_payload(row)) for row in event_rows],
                }
            rows = conn.execute(
                "select * from permission_events where run_id = ? order by id asc",
                (run_id,),
            ).fetchall()
        return {"run_id": run_id, "source": "permission_events", "data": [row_to_payload(row) for row in rows]}

    def reconstruct_pheromone_snapshot(self, *, run_id: str, tenant_id: str | None = None) -> dict[str, Any]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            ensure_schema(conn)
            if not run_visible_to_tenant(conn, run_id, tenant_id):
                return {
                    "run_id": run_id,
                    "signal_count": 0,
                    "type_counts": {},
                    "blocking_targets": [],
                    "signals": [],
                    "stop_signals": [],
                    "constraint_signals": [],
                    "evidence_signals": [],
                    "governance_snapshot": build_governance_snapshot([]),
                }
            rows = conn.execute(
                "select payload_json from pheromone_signals where run_id = ? order by id asc",
                (run_id,),
            ).fetchall()
            signal_event_rows = event_rows_with_prefix(conn, run_id, "signal.")
        event_signals = signal_records_from_events([row_to_payload(row) for row in signal_event_rows])
        table_signals = signal_records_from_table_rows(rows)
        signals = event_signals if event_signals else table_signals
        counts = Counter(str(signal.get("type") or "") for signal in signals)
        blockers = [signal for signal in signals if is_active_blocker(signal)]
        snapshot = {
            "run_id": run_id,
            "source": "swarm_events" if event_signals else "pheromone_signals" if table_signals else "none",
            "signal_count": len(signals),
            "type_counts": dict(sorted(counts.items())),
            "blocking_targets": sorted({canonical_target(signal.get("target")) for signal in blockers}),
            "signals": signals,
            "stop_signals": [signal for signal in signals if signal.get("type") == "stop_signal"],
            "constraint_signals": [signal for signal in signals if signal.get("type") == "constraint"],
            "evidence_signals": [signal for signal in signals if signal.get("type") == "evidence"],
        }
        snapshot["governance_snapshot"] = build_governance_snapshot(
            self.timeline(run_id=run_id, tenant_id=tenant_id, limit=5_000)
        )
        return snapshot

    def recovery_lineage(self, *, run_id: str, target: str, tenant_id: str | None = None) -> dict[str, Any]:
        canonical = canonical_target(target)
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            ensure_schema(conn)
            if not run_visible_to_tenant(conn, run_id, tenant_id):
                return {
                    "run_id": run_id,
                    "target": target,
                    "canonical_target": canonical,
                    "status": "missing",
                    "recovery_trace": {},
                    "recovery_events": [],
                    "protocol_lineage": {},
                }
            payload = fetch_run_payload(conn, run_id)
            swarm_plan = swarm_plan_with_event_protocols(conn, run_id, payload)
            rows = conn.execute(
                "select * from swarm_events where run_id = ? order by id asc",
                (run_id,),
            ).fetchall()
        events = [
            event
            for event in (row_to_payload(row) for row in rows)
            if recovery_event_matches(event, canonical)
        ]
        traces = find_recovery_traces(payload, canonical)
        stored_trace = traces[0] if traces else {}
        event_trace = recovery_trace_from_events(events, canonical)
        trace = preferred_recovery_trace(event_trace, stored_trace)
        trace_source = "swarm_events" if trace is event_trace and event_trace else "stored_recovery_trace" if stored_trace else "none"
        status = str(trace.get("status") or ("event_only" if events else "missing"))
        return {
            "run_id": run_id,
            "target": target,
            "canonical_target": canonical,
            "status": status,
            "source": trace_source,
            "recovery_trace": trace,
            "recovery_events": events,
            "target_pressure": trace.get("target_pressure") if isinstance(trace.get("target_pressure"), dict) else {},
            "selected_protocol": trace.get("selected_protocol") if isinstance(trace.get("selected_protocol"), dict) else {},
            "selected_agents": trace.get("selected_agents") if isinstance(trace.get("selected_agents"), list) else [],
            "fallback_candidate": trace.get("fallback_candidate"),
            "signal_resolution_report": find_signal_resolution_report(payload),
            "protocol_lineage": target_protocol_lineage(swarm_plan, canonical),
        }

    def capability_protocol(self, *, run_id: str, tenant_id: str | None = None) -> dict[str, Any]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            ensure_schema(conn)
            if not run_visible_to_tenant(conn, run_id, tenant_id):
                return {"run_id": run_id, "status": "missing", "protocol_bundle": {}}
            payload = fetch_run_payload(conn, run_id)
            swarm_plan = swarm_plan_with_event_protocols(conn, run_id, payload)
        bundle = capability_protocol_bundle(swarm_plan)
        status = "found" if bundle.get("capability_protocols") or bundle.get("target_signals") else "missing"
        return {
            "run_id": run_id,
            "status": status,
            "protocol_bundle": bundle,
            "os_routing_trace": os_routing_trace_from_payload(payload),
            **bundle,
        }


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists swarm_events (
            id integer primary key autoincrement,
            event_id text,
            run_id text not null,
            timestamp real,
            event_type text,
            actor text,
            target text,
            canonical_target text,
            lifecycle_state text,
            summary text,
            payload_json text
        );
        create table if not exists pheromone_signals (
            id integer primary key autoincrement,
            signal_id text,
            run_id text not null,
            tenant_id text,
            type text,
            target text,
            canonical_target text,
            lifecycle_state text,
            verification_state text,
            blocking integer,
            source_agent text,
            source_module text,
            content text,
            created_at real,
            payload_json text
        );
        create table if not exists quorum_decisions (
            id integer primary key autoincrement,
            run_id text not null,
            committed_candidate text,
            status text,
            payload_json text
        );
        create table if not exists evidence_nodes (
            id integer primary key autoincrement,
            run_id text not null,
            node_id text,
            kind text,
            canonical_target text,
            payload_json text
        );
        create table if not exists evidence_edges (
            id integer primary key autoincrement,
            run_id text not null,
            source text,
            target text,
            relation text,
            payload_json text
        );
        create table if not exists agent_profile_events (
            id integer primary key autoincrement,
            run_id text not null,
            agent text,
            event_type text,
            payload_json text
        );
        create table if not exists tool_events (
            id integer primary key autoincrement,
            run_id text not null,
            tool text,
            event_type text,
            payload_json text
        );
        create table if not exists permission_events (
            id integer primary key autoincrement,
            run_id text not null,
            permission text,
            event_type text,
            payload_json text
        );
        create table if not exists run_traces (
            run_id text primary key,
            tenant_id text not null,
            created_at text,
            payload_json text
        );
        """
    )


def trace_tenant_id(run: dict[str, Any]) -> str:
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    return str(metadata.get("tenant_id") or os_plan.get("tenant_id") or "default")


def persist_run_metadata(conn: sqlite3.Connection, run_id: str, tenant_id: str, run: dict[str, Any]) -> None:
    payload = {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "task": run.get("task"),
        "route": run.get("route"),
        "status": run.get("run_status") or ("failed" if run.get("error") else "completed"),
        **run_debug_bundle(run),
    }
    conn.execute(
        """
        insert into run_traces (run_id, tenant_id, created_at, payload_json)
        values (?, ?, datetime('now'), ?)
        on conflict(run_id) do update set
            tenant_id = excluded.tenant_id,
            created_at = excluded.created_at,
            payload_json = excluded.payload_json
        """,
        (run_id, tenant_id, json_dumps(payload)),
    )


def run_visible_to_tenant(conn: sqlite3.Connection, run_id: str, tenant_id: str | None) -> bool:
    if tenant_id is None:
        return True
    row = conn.execute("select tenant_id from run_traces where run_id = ?", (run_id,)).fetchone()
    if row is None:
        return tenant_id == "default"
    return str(row["tenant_id"]) == str(tenant_id)


def fetch_run_payload(conn: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    row = conn.execute("select payload_json from run_traces where run_id = ?", (run_id,)).fetchone()
    if row is None:
        return {}
    payload = json_loads(row["payload_json"])
    return payload if isinstance(payload, dict) else {}


def run_debug_bundle(run: dict[str, Any]) -> dict[str, Any]:
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    swarm_plan = os_plan.get("swarm_plan") if isinstance(os_plan.get("swarm_plan"), dict) else {}
    domain_workflow = run.get("domain_workflow") if isinstance(run.get("domain_workflow"), dict) else {}
    return {
        "metadata": metadata,
        "os_plan": os_plan,
        "os_routing_trace": os_routing_trace_from_payload({"os_plan": os_plan, "metadata": metadata}),
        "swarm_plan": swarm_plan,
        "domain_workflow": workflow_trace_bundle(domain_workflow),
        "agent_allocation_trace": run.get("agent_allocation_trace") if isinstance(run.get("agent_allocation_trace"), list) else [],
        "recovery_trace": first_recovery_trace(run),
        "signal_resolution_report": first_signal_resolution_report(run),
        "bottleneck_report": run.get("bottleneck_report") if isinstance(run.get("bottleneck_report"), dict) else {},
    }


def workflow_trace_bundle(workflow: dict[str, Any]) -> dict[str, Any]:
    if not workflow:
        return {}
    return {
        "workflow_id": workflow.get("workflow_id"),
        "graph_mode": workflow.get("graph_mode"),
        "gate_status": workflow.get("gate_status"),
        "node_outputs": workflow.get("node_outputs") if isinstance(workflow.get("node_outputs"), dict) else {},
    }


def swarm_plan_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    direct = payload.get("swarm_plan")
    if isinstance(direct, dict) and direct:
        return direct
    os_plan = payload.get("os_plan") if isinstance(payload.get("os_plan"), dict) else {}
    nested = os_plan.get("swarm_plan")
    if isinstance(nested, dict):
        return nested
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata_os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    metadata_swarm = metadata_os_plan.get("swarm_plan")
    return metadata_swarm if isinstance(metadata_swarm, dict) else {}


def swarm_plan_with_event_protocols(
    conn: sqlite3.Connection,
    run_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    payload_plan = swarm_plan_from_payload(payload)
    event_plan = swarm_plan_from_protocol_events(protocol_loaded_events(conn, run_id))
    if not event_plan:
        return payload_plan
    if not payload_plan:
        return event_plan
    merged = {**event_plan, **payload_plan}
    merged["capability_protocols"] = dedupe_protocols(
        [
            *(payload_plan.get("capability_protocols") if isinstance(payload_plan.get("capability_protocols"), list) else []),
            *(event_plan.get("capability_protocols") if isinstance(event_plan.get("capability_protocols"), list) else []),
        ]
    )
    merged["target_signals"] = dedupe_dicts(
        [
            *(payload_plan.get("target_signals") if isinstance(payload_plan.get("target_signals"), list) else []),
            *(event_plan.get("target_signals") if isinstance(event_plan.get("target_signals"), list) else []),
        ]
    )
    for key in ("protocol_source", "intent"):
        if not merged.get(key):
            merged[key] = event_plan.get(key)
    return merged


def protocol_loaded_events(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "select * from swarm_events where run_id = ? and event_type = 'capability.protocol.loaded' order by id asc",
        (run_id,),
    ).fetchall()
    return [row_to_payload(row) for row in rows]


def swarm_plan_from_protocol_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    protocols = []
    protocol_source = None
    intent = None
    for event in events:
        payload = event_payload(event)
        protocol = payload.get("protocol") if isinstance(payload.get("protocol"), dict) else {}
        if not protocol:
            continue
        capability_id = payload.get("capability_id") or protocol.get("capability_id") or protocol.get("id")
        protocol = {**protocol}
        if capability_id and not protocol.get("capability_id"):
            protocol["capability_id"] = capability_id
        protocols.append(protocol)
        protocol_source = protocol_source or payload.get("protocol_source")
        intent = intent or payload.get("intent")
    protocols = dedupe_protocols(protocols)
    if not protocols:
        return {}
    return {
        "protocol_source": protocol_source or "capability_protocol_event",
        "intent": intent,
        "capability_protocols": protocols,
        "target_signals": target_signals_from_protocols(protocols),
        "recovery_protocols": recovery_protocols_from_protocols(protocols),
        "candidate_policy": candidate_policy_from_protocols(protocols),
        "quorum_policy": policy_from_protocols(protocols, "quorum_policy"),
        "stop_signal_policy": policy_from_protocols(protocols, "stop_signal_policy"),
        "evidence_policy": policy_from_protocols(protocols, "evidence_policy"),
        "tool_policy": policy_from_protocols(protocols, "tool_policy"),
        "output_policy": policy_from_protocols(protocols, "output_policy"),
        "agent_selection_policy": policy_from_protocols(protocols, "agent_selection_policy"),
        "swarm_loop_policy": policy_from_protocols(protocols, "swarm_loop_policy"),
    }


def recovery_protocols_from_protocols(protocols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for protocol in protocols:
        capability_id = protocol.get("capability_id") or protocol.get("id")
        for recovery in protocol.get("recovery_protocols") or []:
            if isinstance(recovery, dict):
                output.append({**recovery, "capability_id": recovery.get("capability_id") or capability_id})
    return dedupe_dicts(output)


def candidate_policy_from_protocols(protocols: list[dict[str, Any]]) -> dict[str, Any]:
    policy = policy_from_protocols(protocols, "candidate_policy")
    candidates = []
    for protocol in protocols:
        capability_id = protocol.get("capability_id") or protocol.get("id")
        for candidate in protocol.get("candidates") or []:
            if isinstance(candidate, dict):
                candidates.append({**candidate, "capability_id": candidate.get("capability_id") or capability_id})
    existing = policy.get("candidates") if isinstance(policy.get("candidates"), list) else []
    if candidates or existing:
        policy["candidates"] = dedupe_values([*existing, *candidates])
    return policy


def policy_from_protocols(protocols: list[dict[str, Any]], key: str) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for protocol in protocols:
        policy = protocol.get(key) if isinstance(protocol.get(key), dict) else {}
        if not policy:
            continue
        capability_id = protocol.get("capability_id") or protocol.get("id")
        merged = merge_debug_policy(merged, policy_with_capability(policy, capability_id))
    return merged


def policy_with_capability(policy: dict[str, Any], capability_id: Any) -> dict[str, Any]:
    if not capability_id:
        return dict(policy)
    output = dict(policy)
    output.setdefault("capability_id", capability_id)
    for key in ("rules", "action_markers", "action_cues"):
        values = output.get(key)
        if isinstance(values, list):
            output[key] = [
                {**item, "capability_id": item.get("capability_id") or capability_id}
                if isinstance(item, dict)
                else item
                for item in values
            ]
    return output


def merge_debug_policy(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        current = merged.get(key)
        if isinstance(current, list) or isinstance(value, list):
            merged[key] = dedupe_values([*merge_list_values(current), *merge_list_values(value)])
        elif isinstance(current, dict) and isinstance(value, dict):
            merged[key] = merge_debug_policy(current, value)
        elif key not in merged or current in (None, "", [], {}):
            merged[key] = value
    return merged


def merge_list_values(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, {}, ""):
        return []
    return [value]


def dedupe_values(items: list[Any]) -> list[Any]:
    output = []
    seen = set()
    for item in items:
        marker = json_dumps(item)
        if marker in seen:
            continue
        seen.add(marker)
        output.append(item)
    return output


def target_signals_from_protocols(protocols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signals = []
    for protocol in protocols:
        capability_id = protocol.get("capability_id") or protocol.get("id")
        for target in protocol.get("targets") or []:
            if not isinstance(target, dict):
                continue
            signals.append({**target, "capability_id": capability_id})
    return dedupe_dicts(signals)


def dedupe_protocols(protocols: list[Any]) -> list[dict[str, Any]]:
    return dedupe_dicts([dict(protocol) for protocol in protocols if isinstance(protocol, dict)])


def os_routing_trace_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    direct = payload.get("os_routing_trace")
    if isinstance(direct, list):
        return [dict(item) for item in direct if isinstance(item, dict)]
    os_plan = payload.get("os_plan") if isinstance(payload.get("os_plan"), dict) else {}
    trace = os_plan.get("os_routing_trace")
    if isinstance(trace, list):
        return [dict(item) for item in trace if isinstance(item, dict)]
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata_os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    metadata_trace = metadata_os_plan.get("os_routing_trace")
    if isinstance(metadata_trace, list):
        return [dict(item) for item in metadata_trace if isinstance(item, dict)]
    return []


def os_routing_events(run: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
    os_plan = run.get("os_plan") if isinstance(run.get("os_plan"), dict) else {}
    if not os_plan:
        os_plan = metadata.get("os_plan") if isinstance(metadata.get("os_plan"), dict) else {}
    trace = os_routing_trace_from_payload(
        {
            "os_routing_trace": run.get("os_routing_trace"),
            "os_plan": os_plan,
            "metadata": metadata,
        }
    )
    events = []
    for item in trace:
        event_type = str(item.get("event_type") or "").strip()
        if not event_type:
            continue
        events.append(
            {
                **item,
                "event_type": event_type,
                "actor": item.get("actor") or "os_kernel",
                "target": item.get("target") or "run",
                "summary": item.get("summary") or event_type,
                "payload": item,
            }
        )
    return events


def capability_protocol_bundle(swarm_plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(swarm_plan, dict):
        return {}
    list_defaults = {
        "target_signals",
        "agent_allocation",
        "activated_agents",
        "capability_protocols",
        "recovery_protocols",
        "validation_diagnostics",
        "workflow_entrypoints",
        "routing_trace",
    }
    dict_defaults = {
        "candidate_policy",
        "evidence_policy",
        "quorum_policy",
        "stop_signal_policy",
        "swarm_loop_policy",
        "tool_policy",
        "output_policy",
        "agent_selection_policy",
        "target_aliases",
    }
    scalar_keys = {
        "schema_version",
        "intent",
        "target_count",
        "activated_agent_count",
        "protocol_source",
        "generated_legacy_protocol_count",
        "legacy_goal_router_fallback",
        "needs_capability",
        "selection_mode",
        "max_rounds",
    }
    bundle: dict[str, Any] = {}
    for key in sorted(list_defaults):
        bundle[key] = swarm_plan.get(key) if isinstance(swarm_plan.get(key), list) else []
    for key in sorted(dict_defaults):
        bundle[key] = swarm_plan.get(key) if isinstance(swarm_plan.get(key), dict) else {}
    for key in sorted(scalar_keys):
        bundle[key] = swarm_plan.get(key)
    safe = redact_sensitive(bundle)
    return safe if isinstance(safe, dict) else bundle


def target_protocol_lineage(swarm_plan: dict[str, Any], canonical: str) -> dict[str, Any]:
    if not isinstance(swarm_plan, dict) or not canonical:
        return {}
    target_signals = [
        dict(item)
        for item in swarm_plan.get("target_signals") or []
        if isinstance(item, dict) and target_ref_matches(item, canonical)
    ]
    protocols = []
    for protocol in swarm_plan.get("capability_protocols") or []:
        if not isinstance(protocol, dict):
            continue
        targets = [dict(item) for item in protocol.get("targets") or [] if isinstance(item, dict) and target_ref_matches(item, canonical)]
        stop_policy = protocol.get("stop_signal_policy") if isinstance(protocol.get("stop_signal_policy"), dict) else {}
        stop_rules = matching_policy_rules(stop_policy, canonical)
        recovery_protocols = [
            dict(item)
            for item in protocol.get("recovery_protocols") or []
            if isinstance(item, dict) and policy_rule_matches_target(item, canonical)
        ]
        if targets or stop_rules or recovery_protocols:
            protocols.append(
                {
                    "capability_id": protocol.get("capability_id") or protocol.get("id"),
                    "targets": targets,
                    "stop_signal_rules": stop_rules,
                    "recovery_protocols": recovery_protocols,
                }
            )
    stop_signal_policy = (
        swarm_plan.get("stop_signal_policy") if isinstance(swarm_plan.get("stop_signal_policy"), dict) else {}
    )
    recovery_protocols = [
        dict(item)
        for item in swarm_plan.get("recovery_protocols") or []
        if isinstance(item, dict) and policy_rule_matches_target(item, canonical)
    ]
    lineage = {
        "protocol_source": swarm_plan.get("protocol_source"),
        "intent": swarm_plan.get("intent"),
        "target_signals": target_signals,
        "capability_protocols": protocols,
        "stop_signal_policy": {
            "rules": matching_policy_rules(stop_signal_policy, canonical),
        },
        "recovery_protocols": recovery_protocols,
    }
    safe = redact_sensitive(lineage)
    return safe if isinstance(safe, dict) else lineage


def candidate_protocol_lineage(swarm_plan: dict[str, Any], quorum_trace: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(swarm_plan, dict) or not isinstance(quorum_trace, dict):
        return {}
    committed = quorum_trace.get("committed_candidate") if isinstance(quorum_trace.get("committed_candidate"), dict) else {}
    if not committed:
        return {}
    candidate_keys = candidate_reference_keys(committed)
    candidate_policy = swarm_plan.get("candidate_policy") if isinstance(swarm_plan.get("candidate_policy"), dict) else {}
    quorum_policy = swarm_plan.get("quorum_policy") if isinstance(swarm_plan.get("quorum_policy"), dict) else {}
    top_level_candidates = matching_candidates(candidate_policy.get("candidates"), candidate_keys)
    if not top_level_candidates:
        top_level_candidates = matching_candidates(quorum_policy.get("candidates"), candidate_keys)
    fallback_candidate = quorum_trace.get("fallback_candidate") if isinstance(quorum_trace.get("fallback_candidate"), dict) else {}
    lineage = {
        "protocol_source": swarm_plan.get("protocol_source"),
        "intent": swarm_plan.get("intent"),
        "candidate_source": quorum_trace.get("candidate_source"),
        "committed_candidate": committed,
        "candidate_policy": {"candidates": top_level_candidates},
        "quorum_policy": matching_quorum_policy(quorum_policy, candidate_keys),
        "fallback_candidate": fallback_candidate if candidate_ref_matches(fallback_candidate, candidate_keys) else {},
        "capability_protocols": matching_candidate_protocols(
            swarm_plan.get("capability_protocols"),
            candidate_keys,
        ),
    }
    safe = redact_sensitive(lineage)
    return safe if isinstance(safe, dict) else lineage


def matching_candidate_protocols(value: Any, candidate_keys: set[str]) -> list[dict[str, Any]]:
    protocols = []
    for protocol in value if isinstance(value, list) else []:
        if not isinstance(protocol, dict):
            continue
        candidates = matching_candidates(protocol.get("candidates"), candidate_keys)
        quorum_policy = protocol.get("quorum_policy") if isinstance(protocol.get("quorum_policy"), dict) else {}
        matched_quorum = matching_quorum_policy(quorum_policy, candidate_keys)
        if candidates or matched_quorum:
            protocols.append(
                {
                    "capability_id": protocol.get("capability_id") or protocol.get("id"),
                    "candidates": candidates,
                    "quorum_policy": matched_quorum,
                }
            )
    return protocols


def matching_candidates(value: Any, candidate_keys: set[str]) -> list[dict[str, Any]]:
    output = []
    for item in value if isinstance(value, list) else []:
        if candidate_ref_matches(item, candidate_keys):
            output.append(dict(item) if isinstance(item, dict) else {"candidate": str(item)})
    return output


def matching_quorum_policy(policy: dict[str, Any], candidate_keys: set[str]) -> dict[str, Any]:
    if not isinstance(policy, dict):
        return {}
    matched: dict[str, Any] = {}
    candidates = matching_candidates(policy.get("candidates"), candidate_keys)
    if candidates:
        matched["candidates"] = candidates
    fallback = policy.get("candidate_fallback") or policy.get("fallback_candidate")
    if candidate_ref_matches(fallback, candidate_keys):
        matched["candidate_fallback"] = fallback
    for key in (
        "quorum_threshold",
        "commit_rule",
        "force_fallback_when_blocked",
        "source_independence_weight",
        "source_quality_weight",
        "evidence_coverage_weight",
        "unresolved_risk_penalty",
        "stop_signal_penalty",
    ):
        if key in policy:
            matched[key] = policy[key]
    return matched


def candidate_ref_matches(value: Any, candidate_keys: set[str]) -> bool:
    if not candidate_keys:
        return False
    return bool(candidate_reference_keys(value) & candidate_keys)


def candidate_reference_keys(value: Any) -> set[str]:
    raw_values: list[Any] = []
    if isinstance(value, dict):
        raw_values.extend(value.get(key) for key in ("id", "candidate", "label", "target", "canonical_target"))
    elif value is not None:
        raw_values.append(value)
    keys = set()
    for raw in raw_values:
        text = str(raw or "").strip()
        if not text:
            continue
        keys.add(normalized_candidate_ref(text))
        keys.add(normalized_candidate_ref(canonical_target(text)))
        short = candidate_short_ref(text)
        if short:
            keys.add(normalized_candidate_ref(short))
    return {key for key in keys if key}


def candidate_short_ref(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    tail = text.split(":")[-1]
    return " ".join(tail.replace("-", "_").split("_"))


def normalized_candidate_ref(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def agent_protocol_lineage(swarm_plan: dict[str, Any], allocation: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(swarm_plan, dict) or not isinstance(allocation, dict):
        return {}
    target_pressure = agent_target_pressure(allocation)
    target_keys = {
        canonical_target(item.get("canonical_target") or item.get("target"))
        for item in target_pressure
        if isinstance(item, dict) and (item.get("canonical_target") or item.get("target"))
    }
    target_signals = [
        dict(item)
        for item in swarm_plan.get("target_signals") or []
        if isinstance(item, dict) and (not target_keys or any(target_ref_matches(item, target) for target in target_keys))
    ]
    protocols = []
    for protocol in swarm_plan.get("capability_protocols") or []:
        if not isinstance(protocol, dict):
            continue
        targets = [
            dict(item)
            for item in protocol.get("targets") or []
            if isinstance(item, dict) and (not target_keys or any(target_ref_matches(item, target) for target in target_keys))
        ]
        agent_policy = protocol.get("agent_selection_policy") if isinstance(protocol.get("agent_selection_policy"), dict) else {}
        matched_agent_policy = (
            agent_policy
            if agent_policy and (not target_keys or targets or agent_selection_policy_matches_targets(agent_policy, target_keys))
            else {}
        )
        if targets or matched_agent_policy:
            protocols.append(
                {
                    "capability_id": protocol.get("capability_id") or protocol.get("id"),
                    "targets": targets,
                    "agent_selection_policy": matched_agent_policy,
                }
            )
    lineage = {
        "protocol_source": swarm_plan.get("protocol_source"),
        "intent": swarm_plan.get("intent"),
        "selection_mode": swarm_plan.get("selection_mode"),
        "target_pressure": target_pressure,
        "target_signals": target_signals,
        "agent_selection_policy": swarm_plan.get("agent_selection_policy")
        if isinstance(swarm_plan.get("agent_selection_policy"), dict)
        else {},
        "capability_protocols": protocols,
    }
    safe = redact_sensitive(lineage)
    return safe if isinstance(safe, dict) else lineage


def agent_selection_policy_matches_targets(policy: dict[str, Any], target_keys: set[str]) -> bool:
    if not target_keys:
        return bool(policy)
    affinity = policy.get("target_affinity_weights") if isinstance(policy.get("target_affinity_weights"), dict) else {}
    if any(canonical_target(target) in target_keys for target in affinity):
        return True
    for key in ("required_targets", "optional_targets", "targets"):
        value = policy.get(key)
        if target_collection_any_matches(value, target_keys):
            return True
    return False


def target_collection_any_matches(value: Any, target_keys: set[str]) -> bool:
    return any(target_collection_matches(value, target) for target in target_keys)


def target_ref_matches(value: Any, canonical: str) -> bool:
    if isinstance(value, dict):
        for key in ("canonical_target", "target", "id", "name"):
            raw = value.get(key)
            if raw and canonical_target(raw) == canonical:
                return True
        return False
    return bool(str(value or "").strip()) and canonical_target(value) == canonical


def matching_policy_rules(policy: dict[str, Any], canonical: str) -> list[dict[str, Any]]:
    rules = policy.get("rules") if isinstance(policy.get("rules"), list) else []
    output = [dict(rule) for rule in rules if isinstance(rule, dict) and policy_rule_matches_target(rule, canonical)]
    if not output and policy_rule_matches_target(policy, canonical):
        output.append(dict(policy))
    return output


def policy_rule_matches_target(rule: dict[str, Any], canonical: str) -> bool:
    for key in (
        "target",
        "canonical_target",
        "targets",
        "trigger_targets",
        "blocked_targets",
        "applies_to_targets",
        "recovery_targets",
    ):
        value = rule.get(key)
        if target_collection_matches(value, canonical):
            return True
    return False


def target_collection_matches(value: Any, canonical: str) -> bool:
    if isinstance(value, list):
        return any(target_ref_matches(item, canonical) for item in value)
    return target_ref_matches(value, canonical)


def find_agent_allocations(payload: dict[str, Any], agent_id: str) -> list[dict[str, Any]]:
    allocations: list[dict[str, Any]] = []
    allocation_trace = payload.get("agent_allocation_trace") if isinstance(payload.get("agent_allocation_trace"), list) else []
    for item in allocation_trace:
        if isinstance(item, dict) and agent_identifier_matches(allocation_agent_id(item), agent_id):
            allocations.append(item)
    swarm_plan = swarm_plan_from_payload(payload)
    swarm_allocation = swarm_plan.get("agent_allocation") if isinstance(swarm_plan.get("agent_allocation"), list) else []
    for item in swarm_allocation:
        if isinstance(item, dict) and agent_identifier_matches(allocation_agent_id(item), agent_id):
            allocations.append(item)
    os_plan = payload.get("os_plan") if isinstance(payload.get("os_plan"), dict) else {}
    agent_plan = os_plan.get("agent_plan") if isinstance(os_plan.get("agent_plan"), dict) else {}
    agent_plan_allocation = agent_plan.get("swarm_allocation") if isinstance(agent_plan.get("swarm_allocation"), list) else []
    for item in agent_plan_allocation:
        if isinstance(item, dict) and agent_identifier_matches(allocation_agent_id(item), agent_id):
            allocations.append(item)
    return dedupe_dicts(allocations)


def allocation_agent_id(allocation: dict[str, Any]) -> str:
    return str(allocation.get("agent") or allocation.get("key") or allocation.get("agent_id") or "")


def agent_identifier_matches(value: Any, agent_id: str) -> bool:
    return str(value or "").strip().lower() == str(agent_id or "").strip().lower()


def agent_activation_reason(allocation: dict[str, Any]) -> str | None:
    if not isinstance(allocation, dict):
        return None
    return allocation.get("activation_reason") or allocation.get("reason")


def agent_target_pressure(allocation: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(allocation, dict):
        return []
    raw_targets = allocation.get("matched_targets")
    if not isinstance(raw_targets, list):
        raw_targets = allocation.get("target_pressure") if isinstance(allocation.get("target_pressure"), list) else []
    output = []
    for item in raw_targets:
        if isinstance(item, dict):
            target = canonical_target(item.get("canonical_target") or item.get("target"))
            output.append(
                {
                    **item,
                    "canonical_target": target,
                    "target": item.get("target") or target,
                }
            )
        elif str(item or "").strip():
            target = canonical_target(item)
            output.append({"target": str(item), "canonical_target": target})
    if output:
        return output
    if allocation.get("task_type"):
        return [
            {
                "target": allocation.get("task_type"),
                "canonical_target": canonical_target(allocation.get("task_type")),
                "demand_strength": allocation.get("demand_strength"),
                "utility": allocation.get("utility"),
            }
        ]
    return []


def first_recovery_trace(run: dict[str, Any]) -> dict[str, Any]:
    traces = find_recovery_traces(run)
    return traces[0] if traces else {}


def find_recovery_traces(payload: dict[str, Any], target: str | None = None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    canonical = canonical_target(target) if target else None
    traces: list[dict[str, Any]] = []
    direct = payload.get("recovery_trace")
    if isinstance(direct, dict):
        traces.append(direct)
    elif isinstance(direct, list):
        traces.extend(item for item in direct if isinstance(item, dict))
    traces.extend(item for item in payload.get("recovery_traces") or [] if isinstance(item, dict))
    domain_workflow = payload.get("domain_workflow") if isinstance(payload.get("domain_workflow"), dict) else {}
    node_outputs = domain_workflow.get("node_outputs") if isinstance(domain_workflow.get("node_outputs"), dict) else {}
    for node_output in node_outputs.values():
        if not isinstance(node_output, dict):
            continue
        nested = node_output.get("recovery_trace")
        if isinstance(nested, dict):
            traces.append(nested)
        if str(node_output.get("schema_version") or "").startswith("pheroos.recovery_trace"):
            traces.append(node_output)
    traces = [trace for trace in dedupe_dicts(traces) if is_recovery_trace(trace)]
    if canonical is None:
        return traces
    matched = [trace for trace in traces if canonical_target(trace.get("target")) == canonical]
    return matched or traces


def recovery_trace_from_events(events: list[dict[str, Any]], canonical: str) -> dict[str, Any]:
    if not events:
        return {}
    payload_traces = []
    for event in events:
        payload = event_payload(event)
        trace = payload.get("recovery_trace") if isinstance(payload.get("recovery_trace"), dict) else {}
        if trace:
            payload_traces.append(trace)
    if payload_traces:
        matched = [trace for trace in payload_traces if canonical_target(trace.get("target")) == canonical]
        trace = dict(matched[0] if matched else payload_traces[0])
        trace["source"] = "swarm_events"
        trace["event_payload_trace"] = True
        return trace

    payloads = [event_payload(event) for event in events]
    last_event = events[-1]
    last_payload = payloads[-1] if payloads else {}
    return {
        "schema_version": "pheroos.recovery_trace.event_derived.v1",
        "status": recovery_status_from_events(events),
        "target": canonical,
        "target_pressure": first_dict_field(payloads, "target_pressure"),
        "selected_protocol": selected_recovery_protocol_from_event_payloads(payloads),
        "selected_agents": first_list_field(payloads, "selected_agents"),
        "fallback_candidate": first_non_empty_field(payloads, "fallback_candidate"),
        "trace": [recovery_trace_item_from_event(event) for event in events],
        "source": "swarm_events",
        "last_event_type": last_event.get("event_type") or last_event.get("type"),
        "last_event_summary": last_event.get("summary"),
        "last_event_payload": last_payload,
    }


def preferred_recovery_trace(event_trace: dict[str, Any], stored_trace: dict[str, Any]) -> dict[str, Any]:
    if event_trace and (not stored_trace or recovery_trace_has_event_details(event_trace)):
        return event_trace
    return stored_trace if stored_trace else event_trace


def recovery_trace_has_event_details(trace: dict[str, Any]) -> bool:
    if not trace or trace.get("source") != "swarm_events":
        return False
    return any(
        bool(trace.get(key))
        for key in (
            "event_payload_trace",
            "target_pressure",
            "selected_protocol",
            "selected_agents",
        )
    )


def selected_recovery_protocol_from_event_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    selected = dict(first_dict_field(payloads, "selected_protocol"))
    protocol_id = selected.get("id") or first_non_empty_field(payloads, "protocol_id")
    if protocol_id and not selected.get("id"):
        selected["id"] = protocol_id
    for key in ("capability_id", "source", "protocol_source"):
        value = selected.get(key) or first_non_empty_field(payloads, key)
        if value and not selected.get(key):
            selected[key] = value
    return selected


def recovery_status_from_events(events: list[dict[str, Any]]) -> str:
    event_types = [str(event.get("event_type") or event.get("type") or "") for event in events]
    for event_type in reversed(event_types):
        if event_type == "recovery.succeeded":
            return "recovery_succeeded"
        if event_type == "recovery.failed":
            return "recovery_failed"
        if event_type == "recovery.started":
            return "recovery_started"
    return "event_only"


def recovery_trace_item_from_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = event_payload(event)
    return {
        "event_type": event.get("event_type") or event.get("type"),
        "actor": event.get("actor"),
        "target": event.get("target"),
        "canonical_target": event.get("canonical_target"),
        "summary": event.get("summary"),
        "payload": payload,
    }


def first_dict_field(payloads: list[dict[str, Any]], key: str) -> dict[str, Any]:
    for payload in payloads:
        value = payload.get(key)
        if isinstance(value, dict) and value:
            return value
    return {}


def first_list_field(payloads: list[dict[str, Any]], key: str) -> list[Any]:
    for payload in payloads:
        value = payload.get(key)
        if isinstance(value, list) and value:
            return value
    return []


def first_non_empty_field(payloads: list[dict[str, Any]], key: str) -> Any:
    for payload in payloads:
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def is_recovery_trace(value: dict[str, Any]) -> bool:
    if not isinstance(value, dict):
        return False
    if str(value.get("schema_version") or "").startswith("pheroos.recovery_trace"):
        return True
    return any(key in value for key in ("selected_protocol", "selected_agents", "fallback_candidate", "target_pressure")) and (
        str(value.get("status") or "").startswith("recovery_") or bool(value.get("trace"))
    )


def first_signal_resolution_report(run: dict[str, Any]) -> dict[str, Any]:
    report = find_signal_resolution_report(run)
    return report if isinstance(report, dict) else {}


def find_signal_resolution_report(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    direct = payload.get("signal_resolution_report")
    if isinstance(direct, dict):
        return direct
    domain_workflow = payload.get("domain_workflow") if isinstance(payload.get("domain_workflow"), dict) else {}
    node_outputs = domain_workflow.get("node_outputs") if isinstance(domain_workflow.get("node_outputs"), dict) else {}
    for node_output in node_outputs.values():
        if not isinstance(node_output, dict):
            continue
        nested = node_output.get("signal_resolution_report")
        if isinstance(nested, dict):
                return nested
    return {}


def timeline_records_prefer_events(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    event_signal_keys = {
        key
        for key in (timeline_event_signal_key(record) for record in records)
        if key
    }
    if not event_signal_keys:
        return records
    output = []
    for record in records:
        if record.get("record_type") == "signal" and timeline_signal_row_key(record) in event_signal_keys:
            continue
        output.append(record)
    return output


def timeline_event_signal_key(record: dict[str, Any]) -> str:
    if record.get("record_type") != "event":
        return ""
    event_type = str(record.get("type") or record.get("event_type") or "")
    if not event_type.startswith("signal."):
        return ""
    return timeline_signal_key(signal_record_from_event(record))


def timeline_signal_row_key(record: dict[str, Any]) -> str:
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    signal = dict(payload)
    signal.setdefault("type", record.get("type"))
    signal.setdefault("target", record.get("target"))
    signal.setdefault("canonical_target", record.get("canonical_target"))
    signal.setdefault("content", record.get("summary"))
    return timeline_signal_key(signal)


def timeline_signal_key(signal: dict[str, Any]) -> str:
    contract = signal.get("contract") if isinstance(signal.get("contract"), dict) else {}
    signal_id = str(signal.get("id") or signal.get("signal_id") or contract.get("signal_id") or "").strip()
    if signal_id:
        return f"id:{signal_id}"
    target = canonical_target(signal.get("canonical_target") or signal.get("target") or "")
    content = str(signal.get("content") or signal.get("summary") or "").strip()[:120]
    signal_type = str(signal.get("type") or "signal").strip()
    if target or content:
        return f"anon:{signal_type}:{target}:{content}"
    return ""


def recovery_event_matches(event: dict[str, Any], target: str) -> bool:
    event_type = str(event.get("type") or event.get("event_type") or "")
    if not event_type.startswith("recovery."):
        return False
    canonical = canonical_target(target)
    event_target = canonical_target(event.get("canonical_target") or event.get("target"))
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    payload_target = canonical_target(payload.get("canonical_target") or payload.get("target"))
    if event_target == canonical or payload_target == canonical:
        return True
    return event_target == "run" and payload_target == "run"


def evidence_graph_from_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    for event in events:
        node = evidence_node_from_event(event)
        if node:
            nodes.append(node)
    nodes = dedupe_dicts(nodes)
    return {"nodes": nodes, "edges": []}


def evidence_graph_source(
    event_graph: dict[str, Any],
    table_nodes: list[dict[str, Any]],
    table_edges: list[dict[str, Any]],
) -> str:
    has_events = bool(event_graph.get("nodes") or event_graph.get("edges"))
    has_tables = bool(table_nodes or table_edges)
    if has_events and has_tables:
        return "swarm_events+evidence_tables"
    if has_events:
        return "swarm_events"
    if has_tables:
        return "evidence_tables"
    return "none"


def merge_evidence_nodes(event_nodes: list[dict[str, Any]], table_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes_by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for index, node in enumerate(table_nodes):
        record = evidence_node_with_source(node, "evidence_tables")
        key = evidence_node_key(record, index)
        if key not in nodes_by_key:
            nodes_by_key[key] = record
            order.append(key)
            continue
        nodes_by_key[key] = merge_evidence_node_records(nodes_by_key[key], record)
    for index, node in enumerate(event_nodes, start=len(order)):
        record = evidence_node_with_source(node, "swarm_events")
        key = evidence_node_key(record, index)
        if key not in nodes_by_key:
            order.append(key)
            nodes_by_key[key] = record
            continue
        nodes_by_key[key] = merge_evidence_node_records(nodes_by_key[key], record)
    return [nodes_by_key[key] for key in order]


def evidence_node_with_source(node: dict[str, Any], source: str) -> dict[str, Any]:
    record = dict(node)
    record["source"] = source
    return record


def evidence_node_key(node: dict[str, Any], index: int) -> str:
    payload = node.get("payload") if isinstance(node.get("payload"), dict) else {}
    node_id = str(node.get("node_id") or node.get("id") or payload.get("node_id") or payload.get("id") or "").strip()
    if node_id:
        return f"id:{node_id}"
    target = canonical_target(
        node.get("canonical_target")
        or node.get("target")
        or payload.get("canonical_target")
        or payload.get("target")
        or ""
    )
    kind = str(node.get("kind") or payload.get("kind") or "node").strip()
    event_type = str(node.get("event_type") or payload.get("event_type") or "").strip()
    if target or event_type:
        return f"{kind}:{target}:{event_type}"
    return f"anon:{index}"


def merge_evidence_node_records(base: dict[str, Any], event_record: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    sources = [source for source in (base.get("source"), event_record.get("source")) if source]
    for key, value in event_record.items():
        if key == "payload" and isinstance(value, dict) and isinstance(merged.get("payload"), dict):
            merged[key] = {**merged[key], **value}
            continue
        if value not in (None, "", [], {}):
            merged[key] = value
    merged["trace_sources"] = sorted(set(str(source) for source in sources))
    return merged


def evidence_node_from_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("event_type") or event.get("type") or "")
    payload = event_payload(event)
    if event_type.startswith("claim."):
        claim = payload.get("claim") if isinstance(payload.get("claim"), dict) else {}
        node_id = str(payload.get("claim_id") or claim.get("claim_id") or claim.get("id") or event.get("target") or "").strip()
        return {
            "source": "swarm_events",
            "node_id": node_id or event.get("target") or event_type,
            "kind": "claim",
            "canonical_target": event.get("canonical_target") or canonical_target(event.get("target")),
            "event_type": event_type,
            "verification_state": claim_verification_state(event_type, payload),
            "payload": payload,
        }
    if event_type == "artifact.quarantined":
        artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
        node_id = str(artifact.get("artifact_id") or artifact.get("id") or event.get("target") or "artifact").strip()
        return {
            "source": "swarm_events",
            "node_id": node_id,
            "kind": "artifact",
            "canonical_target": event.get("canonical_target") or canonical_target(event.get("target")),
            "event_type": event_type,
            "verification_state": "quarantined",
            "blocking": True,
            "payload": payload,
        }
    if event_type.startswith("signal.") and blocking_signal_event_matches(event):
        signal = blocking_signal_record_from_event(event)
        return {
            "source": "swarm_events",
            "node_id": signal.get("signal_id") or event.get("target") or event_type,
            "kind": "signal",
            "canonical_target": signal.get("canonical_target") or event.get("canonical_target"),
            "event_type": event_type,
            "verification_state": signal.get("lifecycle_state") or "blocking",
            "blocking": True,
            "payload": signal.get("payload") if isinstance(signal.get("payload"), dict) else {},
        }
    return {}


def claim_verification_state(event_type: str, payload: dict[str, Any]) -> str:
    if event_type == "claim.verified":
        return "verified"
    if event_type == "claim.blocked":
        status = str(payload.get("support_status") or "")
        return "blocking" if status.startswith("blocked") else status or "blocked"
    return "created"


def event_rows_with_prefix(conn: sqlite3.Connection, run_id: str, prefix: str) -> list[sqlite3.Row]:
    return conn.execute(
        "select * from swarm_events where run_id = ? and event_type like ? order by id asc",
        (run_id, f"{prefix}%"),
    ).fetchall()


def blocking_signal_event_rows(conn: sqlite3.Connection, run_id: str, canonical: str) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        select * from swarm_events
         where run_id = ?
           and event_type like 'signal.%'
           and (canonical_target = ? or target = ?)
         order by id asc
        """,
        (run_id, canonical, canonical),
    ).fetchall()
    return [row for row in rows if blocking_signal_event_matches(row_to_payload(row))]


def blocking_signal_event_matches(event: dict[str, Any]) -> bool:
    event_type = str(event.get("event_type") or event.get("type") or "")
    if event_type == "signal.promoted_to_blocking":
        return True
    if str(event.get("lifecycle_state") or "") == "blocking":
        return True
    payload = event_payload(event)
    if payload.get("blocking_status") == "blocking" or payload.get("blocking") is True:
        return True
    signal = payload.get("signal") if isinstance(payload.get("signal"), dict) else {}
    if signal.get("blocking") is True or signal.get("blocking_status") == "blocking":
        return True
    contract = payload.get("contract") if isinstance(payload.get("contract"), dict) else {}
    if not contract and isinstance(signal.get("contract"), dict):
        contract = signal.get("contract")
    return contract.get("blocking_status") == "blocking"


def blocking_signal_record_from_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = event_payload(event)
    signal = payload.get("signal") if isinstance(payload.get("signal"), dict) else {}
    contract = payload.get("contract") if isinstance(payload.get("contract"), dict) else {}
    if not contract and isinstance(signal.get("contract"), dict):
        contract = signal.get("contract")
    target = signal.get("target") or event.get("target")
    return {
        "run_id": event.get("run_id"),
        "source": "swarm_events",
        "event_type": event.get("event_type") or event.get("type"),
        "signal_id": payload.get("signal_id") or signal.get("id") or contract.get("signal_id"),
        "type": payload.get("signal_type") or signal.get("type") or contract.get("signal_type") or "signal",
        "target": target,
        "canonical_target": event.get("canonical_target") or canonical_target(target),
        "lifecycle_state": event.get("lifecycle_state") or payload.get("lifecycle_state") or contract.get("lifecycle_state"),
        "blocking": True,
        "source_agent": signal.get("source_agent") or contract.get("source_agent"),
        "source_module": signal.get("source_module") or contract.get("source_module") or event.get("actor"),
        "content": signal.get("content") or event.get("summary"),
        "payload": payload,
    }


def signal_records_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records_by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for index, event in enumerate(events):
        record = signal_record_from_event(event)
        if not record:
            continue
        key = signal_record_key(record, index)
        if key not in records_by_key:
            order.append(key)
            records_by_key[key] = record
            continue
        records_by_key[key] = merge_signal_records(records_by_key[key], record)
    return [records_by_key[key] for key in order]


def signal_record_from_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("event_type") or event.get("type") or "")
    if not event_type.startswith("signal."):
        return {}
    payload = event_payload(event)
    signal = payload.get("signal") if isinstance(payload.get("signal"), dict) else {}
    contract = payload.get("contract") if isinstance(payload.get("contract"), dict) else {}
    if not contract and isinstance(signal.get("contract"), dict):
        contract = signal.get("contract")
    target = signal.get("target") or event.get("target")
    record = dict(signal)
    signal_id = payload.get("signal_id") or signal.get("id") or contract.get("signal_id")
    signal_type = payload.get("signal_type") or signal.get("type") or contract.get("signal_type")
    lifecycle = event.get("lifecycle_state") or payload.get("lifecycle_state") or contract.get("lifecycle_state")
    if signal_id:
        record["id"] = signal_id
    if signal_type:
        record["type"] = signal_type
    if target:
        record["target"] = target
    if event.get("canonical_target") or target:
        record["canonical_target"] = event.get("canonical_target") or canonical_target(target)
    if lifecycle:
        record["lifecycle_state"] = lifecycle
    if signal.get("source_agent") or contract.get("source_agent"):
        record["source_agent"] = signal.get("source_agent") or contract.get("source_agent")
    if signal.get("source_module") or contract.get("source_module") or event.get("actor"):
        record["source_module"] = signal.get("source_module") or contract.get("source_module") or event.get("actor")
    if signal.get("content") or event.get("summary"):
        record["content"] = signal.get("content") or event.get("summary")
    if contract:
        record["contract"] = contract
    if terminal_lifecycle(lifecycle):
        record["blocking"] = False
    elif blocking_signal_event_matches(event):
        record["blocking"] = True
    elif payload.get("blocking") is not None:
        record["blocking"] = bool(payload.get("blocking"))
    record["trace_source"] = "swarm_events"
    return redact_sensitive(record) if isinstance(record, dict) else {}


def signal_records_from_table_rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    signals = []
    seen = set()
    for row in rows:
        payload = json_loads(row["payload_json"])
        if not isinstance(payload, dict):
            continue
        signal_id = signal_record_key(payload, len(signals))
        if signal_id in seen:
            continue
        seen.add(signal_id)
        signals.append(payload)
    return signals


def signal_record_key(record: dict[str, Any], index: int) -> str:
    signal_id = str(record.get("id") or record.get("signal_id") or "").strip()
    if signal_id:
        return f"id:{signal_id}"
    return "anon:{type}:{target}:{content}:{index}".format(
        type=record.get("type") or "signal",
        target=canonical_target(record.get("target") or ""),
        content=str(record.get("content") or "")[:120],
        index=index,
    )


def merge_signal_records(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in update.items():
        if key == "blocking":
            if value is True or terminal_lifecycle(update.get("lifecycle_state")):
                merged[key] = value
            elif key not in merged:
                merged[key] = value
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
            continue
        if value not in (None, "", [], {}):
            merged[key] = value
    return merged


def terminal_lifecycle(value: Any) -> bool:
    return str(value or "").strip().lower() in {"resolved", "accepted_patch", "rejected", "rejected_by_gate", "expired"}


def agent_allocation_record_from_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = event_payload(event)
    allocation = payload.get("allocation") if isinstance(payload.get("allocation"), dict) else {}
    agent = payload.get("agent") or allocation.get("agent") or allocation.get("agent_id") or allocation.get("key")
    if not agent:
        agent = prefixed_target_identifier(event, "agent")
    return {
        "run_id": event.get("run_id"),
        "agent": agent,
        "event_type": event.get("event_type") or event.get("type"),
        "source": "swarm_events",
        "actor": event.get("actor"),
        "target": event.get("target"),
        "canonical_target": event.get("canonical_target"),
        "summary": event.get("summary"),
        "payload": payload,
    }


def allocation_from_agent_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = event_payload(event)
    allocation = payload.get("allocation") if isinstance(payload.get("allocation"), dict) else {}
    if allocation:
        return allocation
    event_type = str(event.get("event_type") or event.get("type") or "")
    return {
        **payload,
        "agent": event.get("agent") or payload.get("agent"),
        "activated": True
        if event_type == "agent.allocated"
        else False
        if event_type == "agent.suppressed"
        else payload.get("activated"),
    }


def tool_record_from_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = event_payload(event)
    tool = payload.get("tool") or prefixed_target_identifier(event, "tool")
    return {
        "run_id": event.get("run_id"),
        "tool": tool,
        "event_type": event.get("event_type") or event.get("type"),
        "source": "swarm_events",
        "actor": event.get("actor"),
        "target": event.get("target"),
        "canonical_target": event.get("canonical_target"),
        "summary": event.get("summary"),
        "payload": payload,
    }


def permission_record_from_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = event_payload(event)
    permission = payload.get("permission") or event.get("target")
    return {
        "run_id": event.get("run_id"),
        "permission": permission,
        "event_type": event.get("event_type") or event.get("type"),
        "source": "swarm_events",
        "actor": event.get("actor"),
        "target": event.get("target"),
        "canonical_target": event.get("canonical_target"),
        "summary": event.get("summary"),
        "payload": payload,
    }


def event_payload(event: dict[str, Any]) -> dict[str, Any]:
    return event.get("payload") if isinstance(event.get("payload"), dict) else {}


def prefixed_target_identifier(event: dict[str, Any], prefix: str) -> str:
    text = str(event.get("target") or "")
    marker = f"{prefix}:"
    if text.startswith(marker):
        return text[len(marker) :]
    return text


def dedupe_dicts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for item in items:
        marker = json_dumps(item)
        if marker in seen:
            continue
        seen.add(marker)
        output.append(item)
    return output


def persist_events(conn: sqlite3.Connection, run_id: str, events: list[Any]) -> None:
    for event in events:
        if not isinstance(event, dict):
            continue
        safe = normalize_event({"run_id": run_id, **event})
        conn.execute(
            """
            insert into swarm_events (
                event_id, run_id, timestamp, event_type, actor, target,
                canonical_target, lifecycle_state, summary, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                safe.get("event_id"),
                run_id,
                safe.get("timestamp"),
                safe.get("event_type"),
                safe.get("actor"),
                safe.get("target"),
                safe.get("canonical_target"),
                safe.get("lifecycle_state"),
                safe.get("summary"),
                json_dumps(safe.get("payload", {})),
            ),
        )


def persist_signals(conn: sqlite3.Connection, run_id: str, signals: list[Any]) -> None:
    for signal in signals:
        if not isinstance(signal, dict):
            continue
        safe = redact_sensitive({"run_id": run_id, **signal})
        if not isinstance(safe, dict):
            continue
        contract = signal_contract(safe)
        conn.execute(
            """
            insert into pheromone_signals (
                signal_id, run_id, tenant_id, type, target, canonical_target,
                lifecycle_state, verification_state, blocking, source_agent,
                source_module, content, created_at, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                safe.get("id"),
                run_id,
                safe.get("tenant_id"),
                safe.get("type"),
                safe.get("target"),
                contract.get("canonical_target"),
                contract.get("lifecycle_state"),
                safe.get("verification_state"),
                1 if safe.get("blocking") else 0,
                safe.get("source_agent"),
                safe.get("source_module"),
                safe.get("content"),
                safe.get("created_at"),
                json_dumps({**safe, "contract": contract}),
            ),
        )


def persist_quorum(conn: sqlite3.Connection, run_id: str, quorum: dict[str, Any]) -> None:
    if not quorum:
        return
    committed = quorum.get("committed_candidate") if isinstance(quorum.get("committed_candidate"), dict) else {}
    conn.execute(
        "insert into quorum_decisions (run_id, committed_candidate, status, payload_json) values (?, ?, ?, ?)",
        (run_id, committed.get("label"), quorum.get("status"), json_dumps(redact_sensitive(quorum))),
    )


def persist_evidence_graph(conn: sqlite3.Connection, run_id: str, graph: dict[str, Any]) -> None:
    for section in ("facts", "proposals", "blockers", "metrics", "output_permissions", "candidate_decisions", "decision_claims", "review_findings"):
        for node in graph.get(section) or []:
            if not isinstance(node, dict):
                continue
            conn.execute(
                "insert into evidence_nodes (run_id, node_id, kind, canonical_target, payload_json) values (?, ?, ?, ?, ?)",
                (
                    run_id,
                    node.get("id"),
                    node.get("kind") or section,
                    node.get("canonical_target"),
                    json_dumps(redact_sensitive(node)),
                ),
            )
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        conn.execute(
            "insert into evidence_edges (run_id, source, target, relation, payload_json) values (?, ?, ?, ?, ?)",
            (run_id, edge.get("source"), edge.get("target"), edge.get("relation"), json_dumps(redact_sensitive(edge))),
        )


def persist_agent_allocation(conn: sqlite3.Connection, run_id: str, allocation: list[Any]) -> None:
    for item in allocation:
        if not isinstance(item, dict):
            continue
        conn.execute(
            "insert into agent_profile_events (run_id, agent, event_type, payload_json) values (?, ?, ?, ?)",
            (run_id, item.get("agent"), "agent.allocation", json_dumps(redact_sensitive(item))),
        )


def persist_tool_events(conn: sqlite3.Connection, run_id: str, execution_log: list[Any]) -> None:
    for step in execution_log:
        if not isinstance(step, dict):
            continue
        step_id = step.get("step_id") or step.get("id")
        step_title = step.get("title")
        for call in step.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            tool = str(call.get("name") or "unknown")
            result = call.get("result") if isinstance(call.get("result"), dict) else {}
            ok = result.get("ok") if isinstance(result, dict) else None
            decision = result.get("tool_policy_decision") if isinstance(result.get("tool_policy_decision"), dict) else {}
            payload = {
                "run_id": run_id,
                "step_id": step_id,
                "step_title": step_title,
                "tool": tool,
                "args": call.get("args"),
                "tool_policy_decision": decision,
                "result": result,
                "ok": ok,
            }
            event_type = str(call.get("event_type") or "").strip()
            if not event_type and decision:
                event_type = tool_policy_event_type(decision)
            if not event_type:
                event_type = "tool.call.completed" if ok is not False else "tool.call.failed"
            conn.execute(
                "insert into tool_events (run_id, tool, event_type, payload_json) values (?, ?, ?, ?)",
                (run_id, tool, event_type, json_dumps(redact_sensitive(payload))),
            )


def persist_permission_events(conn: sqlite3.Connection, run_id: str, permission_grants: Any) -> None:
    for decision in normalize_permission_decisions(permission_grants):
        capability_id = str(decision.get("capability_id") or "")
        for permission in decision.get("permission_grants") or []:
            payload = {"run_id": run_id, "capability_id": capability_id, "permission": permission, "status": "granted"}
            conn.execute(
                "insert into permission_events (run_id, permission, event_type, payload_json) values (?, ?, ?, ?)",
                (run_id, str(permission), "permission.granted", json_dumps(redact_sensitive(payload))),
            )
        for permission in decision.get("blocked_permissions") or []:
            payload = {"run_id": run_id, "capability_id": capability_id, "permission": permission, "status": "pending_confirmation"}
            conn.execute(
                "insert into permission_events (run_id, permission, event_type, payload_json) values (?, ?, ?, ?)",
                (run_id, str(permission), "permission.pending_confirmation", json_dumps(redact_sensitive(payload))),
            )


def normalize_permission_decisions(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def row_to_payload(row: sqlite3.Row) -> dict[str, Any]:
    output = dict(row)
    for key in ("payload_json",):
        if key in output:
            output["payload"] = json_loads(output.pop(key))
    return output


def json_dumps(value: Any) -> str:
    return json.dumps(redact_sensitive(value), ensure_ascii=False, sort_keys=True, default=str)


def json_loads(value: Any) -> Any:
    try:
        return json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
