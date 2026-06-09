from __future__ import annotations

from pathlib import Path

import pytest

from runtime.agent_registry import AgentRegistry
from runtime.capability_registry import CapabilityRegistry, CapabilityStateStore
from runtime.connection_control import ConnectionControlPlane
from runtime.final_judge_guardrails import apply_final_judge_guardrails
from runtime.graph import AgentRuntime
from runtime.llm import ModelConfig
from runtime.os_kernel import OSKernel
from runtime.secret_store import LocalEncryptedSecretStore
from runtime.skill_loader import SkillLoader
from runtime.swarm.stop_policy import action_blocked_by_stop_policy
from runtime.swarm.quorum import build_quorum_trace
from runtime.swarm.recovery_engine import build_recovery_trace
from runtime.tool_registry import ToolRegistry
from runtime.workflows.domain_execution import apply_domain_workflow_plan
from runtime.workflows.loader import load_workflow_descriptors
from runtime.writer_guardrails import apply_writer_guardrails


class ToyPlannerLLM:
    async def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        return (
            '{"translated_task":"toy_review this artifact","english_search_query":"toy_review this artifact",'
            '"task_type":"toy_review","depth":"standard",'
            '"required_agents":{"memory":false,"wrds":false,"research":false,"quant":false,'
            '"domain":false,"critic":false,"writer":false,"final_judge":false},'
            '"rationale":"toy workflow descriptor owns execution","steps":[]}'
        )


class CapturingToyPlannerLLM(ToyPlannerLLM):
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def chat(self, *, model: str, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        self.messages = messages
        return await super().chat(model=model, messages=messages, temperature=temperature)


def test_toy_capability_declares_targets_and_candidates() -> None:
    manifest = CapabilityRegistry().get("toy-review")

    assert manifest is not None
    protocol = manifest.to_public_dict()["protocol"]
    assert protocol["intents"] == ["toy_review"]
    assert {target["target"] for target in protocol["targets"]} == {
        "gate:toy_evidence_gate",
        "decision:toy_publish",
    }
    assert [candidate["candidate"] for candidate in protocol["candidates"]] == [
        "candidate:toy:approve",
        "candidate:toy:reject",
        "candidate:toy:insufficient_evidence",
    ]
    assert protocol["output_policy"]["required_caveats"] == ["Toy evidence is limited."]


def test_toy_capability_runs_without_graph_py_changes(tmp_path: Path) -> None:
    kernel = toy_kernel(tmp_path)

    plan = kernel.plan(task="toy_review this artifact", tenant_id="tenant-toy")
    graph_text = Path("runtime/graph.py").read_text(encoding="utf-8")

    assert "toy_review" not in graph_text
    assert plan["intent"] == "toy_review"
    assert plan["intent_source"] == "capability_protocol_intent"
    assert plan["runtime_ready"] is True
    assert "toy-review" in plan["auto_enabled"]
    assert plan["swarm_plan"]["protocol_source"] == "capability_manifest"
    assert plan["swarm_plan"]["legacy_goal_router_fallback"] is False
    assert {signal["canonical_target"] for signal in plan["swarm_plan"]["target_signals"]} == {
        "gate:toy_evidence_gate",
        "decision:toy_publish",
    }


def test_toy_capability_evidence_recovery_generic(tmp_path: Path) -> None:
    state = toy_state(tmp_path)
    trace = build_recovery_trace(
        state,
        target="gate:toy_evidence_gate",
        context={"candidate_count": 1, "full_text_count": 0, "needs_recovery": True},
    )

    assert trace["selected_protocol"]["id"] == "toy_evidence_recovery"
    assert trace["selected_agents"][0]["agent"] == "toy_scout_agent"
    assert trace["fallback_candidate"] == "candidate:toy:insufficient_evidence"
    assert trace["status"] == "recovery_failed"


def test_toy_capability_quorum_generic(tmp_path: Path) -> None:
    state = toy_state(tmp_path)
    quorum = build_quorum_trace({**state, "committee_decision": {"decision": "Approve"}})

    assert [candidate["label"] for candidate in quorum["candidates"]] == [
        "Approve",
        "Reject",
        "Insufficient evidence",
    ]
    assert quorum["committed_candidate"]["label"] == "Insufficient evidence"
    assert quorum["candidate_source"] == "capability_protocol"


def test_toy_capability_stop_signal_generic(tmp_path: Path) -> None:
    state = toy_state(tmp_path)

    blocker = action_blocked_by_stop_policy(state, "writer:publish_toy_review")

    assert blocker is not None
    assert blocker["target"] == "gate:toy_evidence_gate"


def test_toy_capability_output_policy_generic(tmp_path: Path) -> None:
    state = toy_state(tmp_path)

    blocked = apply_writer_guardrails("unsupported toy claim. Toy evidence is limited.", state)
    allowed = apply_final_judge_guardrails("Approve with caveats. Toy evidence is limited.", state)

    assert "Output Policy Guardrail Report" in blocked
    assert "Guardrail Report" not in allowed


def test_toy_workflow_descriptor_loads() -> None:
    manifest = CapabilityRegistry().get("toy-review")
    assert manifest is not None

    workflows = load_workflow_descriptors([manifest])

    workflow = workflows["workflows"]["toy-review"]
    assert workflow["graph_mode"] == "toy_review"
    assert workflow["ordered_nodes"][0] == "toy_scout"
    assert workflow["capability_id"] == "toy-review"
    assert workflow["node_entrypoints"]["toy_scout"] == "workflow.py:toy_scout_node"


def test_toy_capability_workflow_runs_through_generic_host(tmp_path: Path) -> None:
    manifest = CapabilityRegistry().get("toy-review")
    assert manifest is not None
    workflow = load_workflow_descriptors([manifest])["workflows"]["toy-review"]
    state = toy_state(tmp_path)
    state["metadata"]["capability_runtime"] = {
        "capabilities": {"toy-review": {"entrypoints": {"workflow": workflow}}}
    }
    result = {"metadata": state["metadata"], "plan": []}

    updated = apply_domain_workflow_plan(state, result)
    graph_text = Path("runtime/graph.py").read_text(encoding="utf-8")

    assert "toy_review" not in graph_text
    assert updated["domain_workflow"]["graph_mode"] == "toy_review"
    assert updated["domain_workflow"]["source"] == "generic_capability_workflow"
    assert updated["swarm_control_loop"]["schema_version"] == "pheroos.generic_control_loop.v1"
    assert updated["domain_workflow"]["entrypoint_diagnostics"][0]["status"] == "executed"
    assert updated["domain_workflow"]["node_outputs"]["toy_scout"]["status"] == "completed"
    assert updated["domain_workflow"]["node_outputs"]["toy_evidence_gate"]["status"] == "blocked"
    assert updated["domain_workflow"]["node_outputs"]["toy_reviewer"]["recommended_candidate"] == "candidate:toy:insufficient_evidence"
    assert updated["domain_workflow"]["node_outputs"]["generic_swarm_control_loop"]["status"] == "blocked"
    assert updated["quorum_trace"]["committed_candidate"]["id"] == "candidate:toy:insufficient_evidence"


@pytest.mark.anyio
async def test_toy_capability_orchestrator_runs_generic_workflow_host(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    manifest = CapabilityRegistry().get("toy-review")
    assert manifest is not None
    workflow = load_workflow_descriptors([manifest])["workflows"]["toy-review"]
    os_plan = toy_kernel(tmp_path).plan(task="toy_review this artifact", tenant_id="tenant-toy")
    runtime = AgentRuntime(
        llm=ToyPlannerLLM(),
        skill_loader=SkillLoader(tmp_path),
        model_config=ModelConfig(orchestrator="orchestrator"),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )
    state = {
        "task": "toy_review this artifact",
        "metadata": {
            "tenant_id": "tenant-toy",
            "os_plan": os_plan,
            "capability_runtime": {"capabilities": {"toy-review": {"entrypoints": {"workflow": workflow}}}},
            "agent_registry": AgentRegistry().catalog(enabled_capability_ids={"toy-review"}),
        },
    }

    updated = await runtime._orchestrator(state)

    assert updated["domain_workflow"]["graph_mode"] == "toy_review"
    assert updated["domain_workflow"]["source"] == "generic_capability_workflow"
    assert updated["domain_workflow"]["status"] == "deferred"
    assert updated["domain_workflow"]["deferred_to_graph_node"] == "workflow_host"
    assert updated["domain_workflow"]["node_outputs"]["toy_scout"]["status"] == "planned"
    assert updated["workflow_host_trace"][0]["status"] == "deferred"

    hosted = await runtime._workflow_host({**state, **updated})

    assert hosted["domain_workflow"]["graph_mode"] == "toy_review"
    assert hosted["domain_workflow"]["source"] == "generic_capability_workflow"
    assert hosted["domain_workflow"]["graph_host_node"] == "workflow_host"
    assert hosted["domain_workflow"]["node_outputs"]["toy_scout"]["status"] == "completed"
    assert hosted["domain_workflow"]["node_outputs"]["toy_evidence_gate"]["status"] == "blocked"
    assert hosted["domain_workflow"]["node_outputs"]["toy_reviewer"]["recommended_candidate"] == "candidate:toy:insufficient_evidence"
    assert hosted["swarm_control_loop"]["schema_version"] == "pheroos.generic_control_loop.v1"
    assert hosted["quorum_trace"]["candidate_source"] == "capability_protocol"
    assert hosted["workflow_host_trace"][0]["status"] == "executed"


@pytest.mark.anyio
async def test_toy_capability_orchestrator_prompt_avoids_legacy_investment_guidance(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_AUDIT_LOG_ENABLED", "false")
    manifest = CapabilityRegistry().get("toy-review")
    assert manifest is not None
    workflow = load_workflow_descriptors([manifest])["workflows"]["toy-review"]
    os_plan = toy_kernel(tmp_path).plan(task="toy_review this artifact", tenant_id="tenant-toy")
    llm = CapturingToyPlannerLLM()
    runtime = AgentRuntime(
        llm=llm,
        skill_loader=SkillLoader(tmp_path),
        model_config=ModelConfig(orchestrator="orchestrator"),
        tool_registry=ToolRegistry(workspace_root=tmp_path),
    )
    state = {
        "task": "toy_review this artifact",
        "metadata": {
            "tenant_id": "tenant-toy",
            "os_plan": os_plan,
            "capability_runtime": {"capabilities": {"toy-review": {"entrypoints": {"workflow": workflow}}}},
            "agent_registry": AgentRegistry().catalog(enabled_capability_ids={"toy-review"}),
        },
    }

    updated = await runtime._orchestrator(state)

    prompt_text = "\n".join(str(message.get("content") or "") for message in llm.messages)
    assert "For investment tasks" not in prompt_text
    assert "A dedicated WRDS Planner" not in prompt_text
    assert "public company name, stock ticker" not in prompt_text
    assert "Use GLM-style reasoning roles" not in prompt_text
    assert updated["orchestration_guidance_trace"] == []
    assert updated["domain_workflow"]["graph_mode"] == "toy_review"


def toy_kernel(tmp_path: Path) -> OSKernel:
    control = ConnectionControlPlane(
        path=tmp_path / "connections.json",
        secret_store=LocalEncryptedSecretStore(
            path=tmp_path / "secrets.json",
            key_path=tmp_path / "secret.key",
        ),
    )
    control.confirm(
        raw="sk-toy-abcdefghijklmnopqrstuvwxyz1234567890",
        tenant_id="tenant-toy",
        validate=False,
        discover=True,
    )
    return OSKernel(
        registry=CapabilityRegistry(),
        state_store=CapabilityStateStore(tmp_path / "capabilities.json"),
        control_plane=control,
        agent_registry=AgentRegistry(),
    )


def toy_state(tmp_path: Path) -> dict:
    plan = toy_kernel(tmp_path).plan(task="toy_review this artifact", tenant_id="tenant-toy")["swarm_plan"]
    return {
        "metadata": {
            "os_plan": {"swarm_plan": plan},
            "agent_registry": AgentRegistry().catalog(enabled_capability_ids={"toy-review"}),
        },
        "stop_signals": [
            {
                "id": "sig-toy-evidence",
                "target": "gate:toy_evidence_gate",
                "blocking": True,
                "verification_state": "blocking",
            }
        ],
    }
