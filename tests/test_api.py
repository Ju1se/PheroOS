from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from app.routes.dependencies import get_agent_runtime
from runtime.audit_log import append_run_audit
from runtime.swarm.agent_profile import AgentProfile, AgentProfileStore
from runtime.swarm.pheromone_store import append_events, append_signals
from runtime.swarm.trace_store import SwarmTraceStore


class FakeRuntime:
    async def run(
        self,
        *,
        task: str,
        skill_names: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "run_id": "test-run",
            "task": task,
            "metadata": {"os_plan": {"runtime_ready": True}, "secret": None},
            "route": "planned",
            "orchestration": {"task_type": "coding", "required_agents": {"critic": True, "writer": True}},
            "selected_skills": [{"name": name, "description": "", "path": ""} for name in (skill_names or ["fastapi-api"])],
            "plan": [{"id": "1", "title": "Plan", "action": "Do the thing"}],
            "execution_log": [{"step_id": "1", "status": "completed"}],
            "memory_context": {"status": "empty", "items": []},
            "research_brief": {"status": "skipped"},
            "quant_analysis": {"status": "skipped"},
            "domain_analysis": {"status": "completed", "domain": "coding", "judgment": "ok"},
            "agent_outputs": {"generic_reviewer": {"status": "completed", "thesis": "generic response field"}},
            "committee_outputs": {},
            "discussion_transcript": [],
            "agent_decision": {"status": "completed", "decision": "Approve generic response."},
            "committee_decision": {"status": "skipped"},
            "review": {"status": "pass", "issues": [], "summary": "ok"},
            "final": "done",
        }


def test_health_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_frontend_index() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "AI OS" in response.text


def test_agent_run_endpoint() -> None:
    app.dependency_overrides[get_agent_runtime] = lambda: FakeRuntime()
    client = TestClient(app)
    try:
        response = client.post("/agents/run", json={"task": "Build a FastAPI endpoint"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["run_id"] == "test-run"
    assert response.json()["metadata"]["os_plan"]["runtime_ready"] is True
    assert response.json()["domain_analysis"]["domain"] == "coding"
    assert response.json()["agent_outputs"]["generic_reviewer"]["thesis"] == "generic response field"
    assert response.json()["agent_decision"]["decision"] == "Approve generic response."
    assert response.json()["committee_outputs"] == {}
    assert response.json()["committee_decision"]["status"] == "skipped"
    assert response.json()["discussion_transcript"] == []
    assert response.json()["final"] == "done"


def test_tools_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/tools")

    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()["data"]}
    assert {"list_files", "read_file", "write_file", "run_pytest", "web_search", "fetch_url"} <= names
    tools = {tool["name"]: tool for tool in response.json()["data"]}
    assert tools["write_file"]["required_permissions"] == ["filesystem:write"]
    assert tools["write_file"]["granted"] is False


def test_swarm_platform_endpoints_are_safe(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PHEROMONE_SIGNAL_LOG_PATH", str(tmp_path / "signals.jsonl"))
    monkeypatch.setenv("SWARM_EVENT_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("SWARM_AGENT_PROFILE_PATH", str(tmp_path / "profiles.json"))
    client = TestClient(app)

    signals = client.get("/platform/swarm/signals")
    events = client.get("/platform/swarm/events")
    profiles = client.get("/platform/swarm/agent-profiles")

    assert signals.status_code == 200
    assert events.status_code == 200
    assert profiles.status_code == 200
    assert signals.json() == {"tenant_id": "default", "data": []}
    assert events.json() == {"tenant_id": "default", "data": []}
    assert profiles.json() == {"tenant_id": "default", "data": []}


def test_swarm_jsonl_and_profiles_are_tenant_scoped(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PHEROMONE_SIGNAL_LOG_PATH", str(tmp_path / "signals.jsonl"))
    monkeypatch.setenv("SWARM_EVENT_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("SWARM_AGENT_PROFILE_PATH", str(tmp_path / "profiles.json"))

    append_signals(
        run_id="run-a",
        tenant_id="tenant-a",
        signals=[{"id": "sig-a", "type": "progress", "target": "run", "content": "tenant a"}],
    )
    append_signals(
        run_id="run-b",
        tenant_id="tenant-b",
        signals=[{"id": "sig-b", "type": "progress", "target": "run", "content": "tenant b"}],
    )
    append_events(
        run_id="run-a",
        tenant_id="tenant-a",
        events=[{"event_type": "agent.opening", "actor": "agent-a", "summary": "tenant a"}],
    )
    append_events(
        run_id="run-b",
        tenant_id="tenant-b",
        events=[{"event_type": "agent.opening", "actor": "agent-b", "summary": "tenant b"}],
    )
    store = AgentProfileStore()
    store.update_many({"agent-a": AgentProfile(agent_id="agent-a", tenant_id="tenant-a", reliability=0.9)}, tenant_id="tenant-a")
    store.update_many({"agent-b": AgentProfile(agent_id="agent-b", tenant_id="tenant-b", reliability=0.4)}, tenant_id="tenant-b")

    client = TestClient(app)
    signals_a = client.get("/platform/swarm/signals", params={"tenant_id": "tenant-a"})
    events_a = client.get("/platform/swarm/events", params={"tenant_id": "tenant-a"})
    profiles_a = client.get("/platform/swarm/agent-profiles", params={"tenant_id": "tenant-a"})

    assert signals_a.status_code == 200
    assert [item["id"] for item in signals_a.json()["data"]] == ["sig-a"]
    assert [item["actor"] for item in events_a.json()["data"]] == ["agent-a"]
    assert [item["agent_id"] for item in profiles_a.json()["data"]] == ["agent-a"]
    assert profiles_a.json()["data"][0]["tenant_id"] == "tenant-a"


def test_swarm_run_decision_debugger_endpoints(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "trace.sqlite3"
    monkeypatch.setenv("SWARM_TRACE_DB_PATH", str(db_path))
    swarm_plan = {
        "schema_version": "pheroos.goal_router.v1",
        "intent": "investment_analysis",
        "target_signals": [{"target": "formal_valuation", "canonical_target": "decision:formal_valuation", "demand_strength": 0.9}],
        "agent_allocation": [
            {
                "agent": "risk_manager_agent",
                "activated": True,
                "matched_targets": [{"target": "formal_valuation", "canonical_target": "decision:formal_valuation", "score": 0.7}],
                "activation_reason": "manifest focus matches pheromone targets",
            }
        ],
        "activated_agents": ["risk_manager_agent"],
        "capability_protocols": [
            {
                "capability_id": "value-investing-research",
                "intents": ["investment_analysis"],
                "candidates": [
                    {
                        "candidate": "candidate:investment:insufficient_data",
                        "label": "Insufficient Data",
                        "safe_fallback": True,
                    }
                ],
                "quorum_policy": {"candidate_fallback": "candidate:investment:insufficient_data"},
                "recovery_protocols": [{"id": "valuation_recovery", "targets": ["decision:formal_valuation"]}],
                "agent_selection_policy": {
                    "required_roles": ["risk_review"],
                    "target_affinity_weights": {"decision:formal_valuation": 0.7},
                },
            }
        ],
        "protocol_source": "capability_manifest",
        "candidate_policy": {
            "candidates": [
                {"id": "candidate:investment:insufficient_data", "label": "Insufficient Data", "safe_fallback": True}
            ]
        },
        "quorum_policy": {
            "commit_rule": "stop_signal_override",
            "candidate_fallback": "candidate:investment:insufficient_data",
        },
        "stop_signal_policy": {"targets": ["decision:formal_valuation"]},
        "tool_policy": {"allowed_tools": ["wrds_status"]},
        "output_policy": {"blocked_phrases": ["unsupported valuation"]},
        "agent_selection_policy": {"required_roles": ["risk_review"]},
        "recovery_protocols": [{"id": "valuation_recovery", "targets": ["decision:formal_valuation"]}],
        "routing_trace": [{"event_type": "protocol_targets_loaded"}],
    }
    recovery_trace = {
        "schema_version": "pheroos.recovery_trace.v1",
        "status": "recovery_failed",
        "target": "decision:formal_valuation",
        "target_pressure": {"blocking_signals": 1},
        "selected_protocol": {"id": "valuation_recovery"},
        "selected_agents": [{"agent": "risk_manager_agent"}],
        "fallback_candidate": "candidate:investment:insufficient_data",
        "trace": [{"event_type": "recovery.failed"}],
    }
    SwarmTraceStore(db_path).persist_run_trace(
        {
            "run_id": "run-api",
            "pheromone_trace": [
                {"event_type": "data_gate.completed", "actor": "data_gate", "target": "formal_valuation"},
                {"event_type": "recovery.failed", "actor": "recovery_engine", "target": "formal_valuation"},
            ],
            "pheromone_field_snapshot": {
                "signals": [
                    {
                        "id": "sig-api",
                        "type": "stop_signal",
                        "target": "formal_valuation",
                        "content": "Blocked.",
                        "verification_state": "blocking",
                        "blocking": True,
                        "source_module": "data_gate",
                    }
                ]
            },
            "quorum_trace": {
                "status": "committed",
                "candidate_source": "capability_protocol",
                "committed_candidate": {"label": "Insufficient Data"},
                "fallback_candidate": {"id": "candidate:investment:insufficient_data", "label": "Insufficient Data"},
            },
            "evidence_graph": {
                "blockers": [{"id": "sig-api", "kind": "signal", "canonical_target": "decision:formal_valuation"}],
                "edges": [],
            },
            "agent_allocation_trace": swarm_plan["agent_allocation"],
            "execution_log": [{"tool_calls": [{"name": "wrds_status", "result": {"ok": True}}]}],
            "domain_workflow": {"node_outputs": {"evidence_recovery": {"recovery_trace": recovery_trace}}},
            "metadata": {
                "os_plan": {"swarm_plan": swarm_plan},
                "permission_grants": [{"capability_id": "wrds", "permission_grants": ["network:wrds"]}],
            },
        }
    )
    client = TestClient(app)

    timeline = client.get("/platform/swarm/runs/run-api/timeline")
    blocked = client.get("/platform/swarm/runs/run-api/why-blocked/formal_valuation")
    committed = client.get("/platform/swarm/runs/run-api/why-committed")
    graph = client.get("/platform/swarm/runs/run-api/evidence-graph")
    allocation = client.get("/platform/swarm/runs/run-api/agent-allocation")
    why_agent = client.get("/platform/swarm/runs/run-api/why-agent/risk_manager_agent")
    tool_events = client.get("/platform/swarm/runs/run-api/tool-events")
    permission_events = client.get("/platform/swarm/runs/run-api/permission-events")
    recovery = client.get("/platform/swarm/runs/run-api/recovery-lineage/formal_valuation")
    protocol = client.get("/platform/swarm/runs/run-api/capability-protocol")

    assert timeline.status_code == 200
    assert blocked.json()["blocked"] is True
    assert committed.json()["quorum_trace"]["committed_candidate"]["label"] == "Insufficient Data"
    assert committed.json()["protocol_lineage"]["candidate_policy"]["candidates"][0]["id"] == "candidate:investment:insufficient_data"
    assert committed.json()["protocol_lineage"]["capability_protocols"][0]["capability_id"] == "value-investing-research"
    assert graph.json()["nodes"][0]["canonical_target"] == "decision:formal_valuation"
    assert allocation.json()["data"][0]["agent"] == "risk_manager_agent"
    assert why_agent.json()["target_pressure"][0]["canonical_target"] == "decision:formal_valuation"
    assert why_agent.json()["protocol_lineage"]["capability_protocols"][0]["capability_id"] == "value-investing-research"
    assert why_agent.json()["protocol_lineage"]["agent_selection_policy"]["required_roles"] == ["risk_review"]
    assert tool_events.json()["data"][0]["tool"] == "wrds_status"
    assert permission_events.json()["data"][0]["permission"] == "network:wrds"
    assert recovery.json()["fallback_candidate"] == "candidate:investment:insufficient_data"
    assert recovery.json()["protocol_lineage"]["recovery_protocols"][0]["id"] == "valuation_recovery"
    assert recovery.json()["protocol_lineage"]["capability_protocols"][0]["capability_id"] == "value-investing-research"
    assert protocol.json()["protocol_source"] == "capability_manifest"
    assert protocol.json()["capability_protocols"][0]["capability_id"] == "value-investing-research"


def test_run_trace_endpoint_assembles_safe_trace(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "trace.sqlite3"
    audit_path = tmp_path / "agent_runs.jsonl"
    secret = "sk-cp-T145hjOnntfujsz_n4wWcbgf4-dFpRZGx_UZZHooKoPSDqkNQGcQY5O91Ep1-a5Gjr_5alc0lSmS2Tmap3thhXU7yuz16-5ZwjI3YYAQ2yoBePlU1BDsn3s"
    monkeypatch.setenv("SWARM_TRACE_DB_PATH", str(db_path))
    monkeypatch.setenv("AGENT_AUDIT_LOG_PATH", str(audit_path))
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "true")
    append_run_audit(
        {
            "run_id": "run-trace",
            "task": "Analyze AAPL",
            "route": "investment",
            "metadata": {"os_plan": {"runtime_ready": True}},
            "review": {"status": "pass", "issues": [f"secret copied {secret}"]},
            "final": f"Final preview {secret}",
        }
    )
    SwarmTraceStore(db_path).persist_run_trace(
        {
            "run_id": "run-trace",
            "pheromone_trace": [{"event_type": "writer.blocked", "actor": "writer", "summary": f"blocked {secret}"}],
            "pheromone_field_snapshot": {
                "signals": [
                    {
                        "id": "sig-trace",
                        "type": "stop_signal",
                        "target": "formal_valuation",
                        "content": f"blocked {secret}",
                        "verification_state": "blocking",
                        "blocking": True,
                        "source_module": "data_gate",
                    }
                ]
            },
            "quorum_trace": {"status": "committed", "committed_candidate": {"label": "Insufficient Data"}},
            "evidence_graph": {"nodes": [{"id": "claim-1", "kind": "claim", "canonical_target": "claim:valuation"}], "edges": []},
            "agent_allocation_trace": [{"agent": "data_auditor_agent", "activated": True}],
            "execution_log": [{"tool_calls": [{"name": "wrds_status", "args": {"api_key": secret}, "result": {"ok": True}}]}],
            "metadata": {"permission_grants": [{"capability_id": "wrds", "permission_grants": ["network:wrds"]}]},
        }
    )
    client = TestClient(app)

    response = client.get("/runs/run-trace/trace")

    assert response.status_code == 200
    payload = response.json()
    text = response.text
    assert secret not in text
    assert payload["run_id"] == "run-trace"
    assert payload["summary"]["runtime_ready"] is True
    assert payload["summary"]["committed_candidate"] == "Insufficient Data"
    assert payload["trace"]["pheromone_snapshot"]["signal_count"] == 1
    assert payload["trace"]["tool_events"]["data"][0]["tool"] == "wrds_status"
    assert payload["redaction_status"] == "redacted"


def test_run_trace_endpoint_returns_404_for_unknown_run(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SWARM_TRACE_DB_PATH", str(tmp_path / "trace.sqlite3"))
    monkeypatch.setenv("AGENT_AUDIT_LOG_PATH", str(tmp_path / "agent_runs.jsonl"))
    client = TestClient(app)

    response = client.get("/runs/missing-run/trace")

    assert response.status_code == 404


def test_run_trace_and_swarm_debugger_are_tenant_scoped(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "trace.sqlite3"
    audit_path = tmp_path / "agent_runs.jsonl"
    monkeypatch.setenv("SWARM_TRACE_DB_PATH", str(db_path))
    monkeypatch.setenv("AGENT_AUDIT_LOG_PATH", str(audit_path))
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "true")
    append_run_audit(
        {
            "run_id": "run-tenant-api",
            "metadata": {"tenant_id": "tenant-a"},
            "task": "Analyze AAPL",
            "final": "done",
        }
    )
    SwarmTraceStore(db_path).persist_run_trace(
        {
            "run_id": "run-tenant-api",
            "metadata": {"tenant_id": "tenant-a"},
            "pheromone_trace": [{"event_type": "data_gate.completed", "actor": "data_gate"}],
            "pheromone_field_snapshot": {
                "signals": [
                    {
                        "id": "sig-tenant-api",
                        "type": "stop_signal",
                        "target": "formal_valuation",
                        "content": "Blocked.",
                        "verification_state": "blocking",
                        "blocking": True,
                        "source_module": "data_gate",
                    }
                ]
            },
            "quorum_trace": {"status": "committed", "committed_candidate": {"label": "Insufficient Data"}},
        }
    )
    client = TestClient(app)

    allowed_trace = client.get("/runs/run-tenant-api/trace", params={"tenant_id": "tenant-a"})
    denied_trace = client.get("/runs/run-tenant-api/trace", params={"tenant_id": "tenant-b"})
    allowed_timeline = client.get("/platform/swarm/runs/run-tenant-api/timeline", params={"tenant_id": "tenant-a"})
    denied_timeline = client.get("/platform/swarm/runs/run-tenant-api/timeline", params={"tenant_id": "tenant-b"})
    denied_committed = client.get("/platform/swarm/runs/run-tenant-api/why-committed", params={"tenant_id": "tenant-b"})
    denied_agent = client.get("/platform/swarm/runs/run-tenant-api/why-agent/data_auditor_agent", params={"tenant_id": "tenant-b"})
    denied_recovery = client.get("/platform/swarm/runs/run-tenant-api/recovery-lineage/formal_valuation", params={"tenant_id": "tenant-b"})
    denied_protocol = client.get("/platform/swarm/runs/run-tenant-api/capability-protocol", params={"tenant_id": "tenant-b"})

    assert allowed_trace.status_code == 200
    assert allowed_trace.json()["tenant_id"] == "tenant-a"
    assert denied_trace.status_code == 404
    assert allowed_timeline.json()["data"]
    assert denied_timeline.json()["data"] == []
    assert denied_committed.json()["status"] == "missing"
    assert denied_agent.json()["status"] == "missing"
    assert denied_recovery.json()["status"] == "missing"
    assert denied_protocol.json()["status"] == "missing"


def test_wrds_endpoint_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("WRDS_API_ENABLED", raising=False)
    monkeypatch.delenv("WRDS_API_TOKEN", raising=False)
    client = TestClient(app)

    response = client.get("/wrds/status")

    assert response.status_code == 404


def test_wrds_status_endpoint_requires_configured_token(monkeypatch) -> None:
    monkeypatch.setenv("WRDS_API_ENABLED", "true")
    monkeypatch.delenv("WRDS_API_TOKEN", raising=False)
    client = TestClient(app)

    response = client.get("/wrds/status")

    assert response.status_code == 401
    assert "token" in response.json()["detail"].lower()


def test_wrds_endpoint_requires_token_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("WRDS_API_ENABLED", "true")
    monkeypatch.setenv("WRDS_API_TOKEN", "test-secret")
    client = TestClient(app)

    denied = client.get("/wrds/status")
    allowed = client.get("/wrds/status", headers={"x-wrds-api-key": "test-secret"})

    assert denied.status_code == 401
    assert allowed.status_code == 200
