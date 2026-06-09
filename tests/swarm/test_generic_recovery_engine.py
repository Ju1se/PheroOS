from __future__ import annotations

from runtime.swarm.bottleneck_recruitment import build_bottleneck_report
from runtime.swarm.goal_router import build_goal_routed_swarm_plan
from runtime.swarm.recovery_engine import apply_recovery_resolution, build_recovery_trace
from runtime.tool_registry import ToolRegistry
from tools.safe_tools import ToolResult


def test_evidence_recovery_selects_agents_by_declared_roles_not_names() -> None:
    trace = build_recovery_trace(
        recovery_state(
            agents=[
                {
                    "key": "alpha",
                    "name": "Alpha",
                    "committee_role": "source_scout",
                    "tags": ["toy-evidence"],
                    "required_tools": ["approved_source_fetch"],
                },
                {
                    "key": "beta",
                    "name": "Beta",
                    "committee_role": "generalist",
                    "tags": ["toy"],
                },
            ],
            allowed_agent_roles=["source_scout"],
            allowed_capability_tags=["toy-evidence"],
        ),
        target="gate:toy_evidence_gate",
        context={"candidate_count": 2, "full_text_count": 0, "needs_recovery": True},
    )

    assert [agent["agent"] for agent in trace["selected_agents"]] == ["alpha"]
    assert "source_retrieval_agent" not in [agent["agent"] for agent in trace["selected_agents"]]
    assert trace["selected_agents"][0]["reasons"] == [
        "allowed_role",
        "allowed_capability_tag",
        "required_tool_match",
        "target_affinity",
        "activated",
    ]


def test_evidence_recovery_works_for_toy_capability() -> None:
    trace = build_recovery_trace(
        recovery_state(),
        target="gate:toy_evidence_gate",
        context={"candidate_count": 1, "full_text_count": 1, "needs_recovery": False},
    )

    assert trace["status"] == "recovery_succeeded"
    assert trace["selected_protocol"]["id"] == "toy_evidence_recovery"
    assert trace["selected_agents"][0]["agent"] == "toy_scout"
    assert trace["target_pressure"] >= 0.9


def test_evidence_recovery_resolves_blocking_signal_after_success() -> None:
    state = recovery_state(
        stop_signal_policy={
            "resolution_policy": {
                "rules": [
                    {
                        "targets": ["gate:toy_evidence_gate"],
                        "resolution_authority": ["toy_evidence_recovery"],
                        "resolution_condition": {"path": "toy.evidence_ready", "equals": True},
                        "reason": "Toy evidence recovered.",
                    }
                ]
            }
        },
        extra={"toy": {"evidence_ready": True}},
    )
    trace = build_recovery_trace(
        state,
        target="gate:toy_evidence_gate",
        context={"candidate_count": 1, "full_text_count": 1},
    )
    update = apply_recovery_resolution(state, trace)

    assert trace["status"] == "recovery_succeeded"
    assert update["signal_resolution_report"]["status"] == "resolved_some"
    assert update["stop_signals"][0]["lifecycle_state"] == "resolved"


def test_evidence_recovery_commits_fallback_after_failure() -> None:
    trace = build_recovery_trace(
        recovery_state(),
        target="gate:toy_evidence_gate",
        context={"candidate_count": 1, "full_text_count": 0, "needs_recovery": True},
    )

    assert trace["status"] == "recovery_failed"
    assert trace["fallback_candidate"] == "candidate:toy:insufficient_evidence"


def test_evidence_recovery_trace_shows_target_pressure_agent_selection_and_outcome() -> None:
    trace = build_recovery_trace(
        recovery_state(),
        target="gate:toy_evidence_gate",
        context={"candidate_count": 1, "full_text_count": 0, "needs_recovery": True},
    )
    event_types = [item["event_type"] for item in trace["trace"]]

    assert "recovery.target_pressure_computed" in event_types
    assert "recovery.protocol_selected" in event_types
    assert "recovery.agents_selected" in event_types
    assert "recovery.failed" in event_types
    assert trace["target_pressure"] >= 0.86
    assert trace["selected_agents"][0]["agent"] == "toy_scout"
    selected_event = next(item for item in trace["trace"] if item["event_type"] == "recovery.agents_selected")
    assert selected_event["selected_agents"][0]["agent"] == "toy_scout"
    assert "allowed_role" in selected_event["selected_agents"][0]["reasons"]
    assert selected_event["protocol_id"] == "toy_evidence_recovery"


def test_evidence_recovery_trace_marks_selected_protocol_capability_lineage() -> None:
    state = recovery_state()
    swarm_plan = state["metadata"]["os_plan"]["swarm_plan"]
    protocol = dict(swarm_plan["recovery_protocols"][0])
    swarm_plan["protocol_source"] = "capability_manifest"
    swarm_plan["capability_protocols"] = [
        {
            "capability_id": "toy-review",
            "targets": [{"canonical_target": "gate:toy_evidence_gate"}],
            "recovery_protocols": [{**protocol, "capability_id": "toy-review"}],
        }
    ]

    trace = build_recovery_trace(
        state,
        target="gate:toy_evidence_gate",
        context={"candidate_count": 1, "full_text_count": 0, "needs_recovery": True},
    )
    protocol_selected = next(item for item in trace["trace"] if item["event_type"] == "recovery.protocol_selected")
    agents_selected = next(item for item in trace["trace"] if item["event_type"] == "recovery.agents_selected")
    recovery_failed = next(item for item in trace["trace"] if item["event_type"] == "recovery.failed")

    assert trace["selected_protocol"]["id"] == "toy_evidence_recovery"
    assert trace["selected_protocol"]["capability_id"] == "toy-review"
    assert trace["selected_protocol"]["source"] == "capability_protocol"
    assert trace["selected_protocol"]["protocol_source"] == "capability_manifest"
    assert protocol_selected["capability_id"] == "toy-review"
    assert agents_selected["capability_id"] == "toy-review"
    assert agents_selected["source"] == "capability_protocol"
    assert recovery_failed["capability_id"] == "toy-review"


def test_recovery_selection_honors_protocol_trust_and_maturity_requirements() -> None:
    state = recovery_state(
        agents=[
            {
                "key": "trusted_worker",
                "name": "Trusted Worker",
                "committee_role": "source_scout",
                "tags": ["toy-evidence"],
                "required_tools": ["approved_source_fetch"],
            },
            {
                "key": "untrusted_specialist",
                "name": "Untrusted Specialist",
                "committee_role": "source_scout",
                "tags": ["toy-evidence"],
                "required_tools": ["approved_source_fetch"],
            },
            {
                "key": "trusted_specialist",
                "name": "Trusted Specialist",
                "committee_role": "source_scout",
                "tags": ["toy-evidence"],
                "required_tools": ["approved_source_fetch"],
            },
        ]
    )
    protocol = state["metadata"]["os_plan"]["swarm_plan"]["recovery_protocols"][0]
    protocol["trust_requirements"] = {"allowed_trust_levels": ["trusted_first_party"]}
    protocol["maturity_requirements"] = {
        "min_maturity": "specialist",
        "required_actions": ["participate_quorum"],
    }
    state["trust_badges"] = [
        {"agent": "trusted_worker", "trust_level": "trusted_first_party"},
        {"agent": "untrusted_specialist", "trust_level": "third_party_untrusted"},
        {"agent": "trusted_specialist", "trust_level": "trusted_first_party"},
    ]
    state["maturity_report"] = {
        "agents": [
            {"agent": "trusted_worker", "maturity": "worker", "allowed_actions": ["perform_low_risk_task"]},
            {"agent": "untrusted_specialist", "maturity": "specialist", "allowed_actions": ["participate_quorum"]},
            {"agent": "trusted_specialist", "maturity": "specialist", "allowed_actions": ["participate_quorum"]},
        ]
    }

    trace = build_recovery_trace(
        state,
        target="gate:toy_evidence_gate",
        context={"candidate_count": 1, "full_text_count": 0, "needs_recovery": True},
    )

    assert [agent["agent"] for agent in trace["selected_agents"]] == ["trusted_specialist"]
    assert {"trust_requirement", "maturity_requirement"} <= set(trace["selected_agents"][0]["reasons"])
    assert trace["selected_protocol"]["trust_requirements"] == {"allowed_trust_levels": ["trusted_first_party"]}
    assert trace["selected_protocol"]["maturity_requirements"]["min_maturity"] == "specialist"
    assert trace["trace"][2]["selection_basis"] == "protocol_roles_tags_target_affinity_trust_maturity"


def test_recovery_executes_declared_tools_through_tool_registry(tmp_path) -> None:
    registry = ToolRegistry(
        workspace_root=tmp_path,
        extra_tools={"toy_recover": lambda marker=None: ToolResult(True, {"marker": marker or "ok"})},
        extra_tool_manifest=[
            {
                "name": "toy_recover",
                "description": "Recover toy evidence.",
                "required_permissions": [],
                "required_connections": [],
            }
        ],
    )

    trace = build_recovery_trace(
        recovery_state(
            required_tools=["toy_recover"],
            recovery_success_condition="recovery.tool_success_count >= 1",
        ),
        target="gate:toy_evidence_gate",
        context={"tool_args_by_name": {"toy_recover": {"marker": "retrieved"}}},
        tool_registry=registry,
    )

    assert trace["status"] == "recovery_succeeded"
    assert trace["tool_results"] == [
        {"name": "toy_recover", "args": {"marker": "retrieved"}, "ok": True, "data": {"marker": "retrieved"}, "error": None}
    ]
    assert any(
        event["event_type"] == "recovery.tools_executed" and event["succeeded"] == ["toy_recover"]
        for event in trace["trace"]
    )


def test_recovery_tool_failure_keeps_declared_fallback(tmp_path) -> None:
    registry = ToolRegistry(workspace_root=tmp_path)

    trace = build_recovery_trace(
        recovery_state(
            required_tools=["missing_recovery_tool"],
            recovery_success_condition="recovery.tool_success_count >= 1",
        ),
        target="gate:toy_evidence_gate",
        context={},
        tool_registry=registry,
    )

    assert trace["status"] == "recovery_failed"
    assert trace["fallback_candidate"] == "candidate:toy:insufficient_evidence"
    assert trace["tool_results"][0]["ok"] is False
    assert "unknown tool" in trace["tool_results"][0]["error"]


def test_bottleneck_recruitment_uses_agent_selection_policy_roles_not_names() -> None:
    plan = build_goal_routed_swarm_plan(
        task="Run a toy review",
        intent="toy_review",
        required_capability_types=["toy.review"],
        agents=[],
        capabilities=[
            {
                "id": "toy-review",
                "trust_level": "first_party_reviewed",
                "protocol": {
                    "intents": ["toy_review"],
                    "targets": [{"target": "gate:toy_evidence_gate"}],
                    "agent_selection_policy": {
                        "required_roles": ["toy_verifier"],
                        "optional_roles": ["evidence_audit"],
                        "target_affinity_weights": {"handoff:evidence_verification": 0.2},
                    },
                },
            }
        ],
    )
    report = build_bottleneck_report(
        {
            "metadata": {
                "os_plan": {"swarm_plan": plan},
                "agent_registry": {
                    "agents": [
                        {
                            "key": "custom_toy_verifier",
                            "committee_role": "toy_verifier",
                            "tags": ["evidence_audit"],
                        },
                        {
                            "key": "custom_generalist",
                            "committee_role": "generalist",
                            "tags": ["toy"],
                        },
                    ]
                },
            },
            "data_gate": {"evidence_gaps": [{"code": "missing_toy_source"}]},
            "metric_registry": {"metrics": []},
        }
    )

    bottleneck = report["bottlenecks"][0]

    assert bottleneck["recruit"] == ["custom_toy_verifier"]
    assert bottleneck["recruitment_source"] == "agent_selection_policy"
    assert "data_auditor_agent" not in bottleneck["recruit"]


def test_bottleneck_recruitment_uses_enabled_capability_agent_catalog() -> None:
    plan = build_goal_routed_swarm_plan(
        task="Run a toy review",
        intent="toy_review",
        required_capability_types=["toy.review"],
        agents=[],
        capabilities=[
            {
                "id": "toy-review",
                "trust_level": "first_party_reviewed",
                "protocol": {
                    "intents": ["toy_review"],
                    "targets": [{"target": "gate:toy_evidence_gate"}],
                    "agent_selection_policy": {
                        "required_roles": ["toy_evidence"],
                        "target_affinity_weights": {"handoff:evidence_verification": 0.2},
                    },
                },
            }
        ],
    )

    report = build_bottleneck_report(
        {
            "metadata": {
                "enabled_capabilities": [{"id": "toy-review"}],
                "os_plan": {"swarm_plan": plan},
            },
            "data_gate": {"evidence_gaps": [{"code": "missing_toy_source"}]},
            "metric_registry": {"metrics": []},
        }
    )
    bottleneck = report["bottlenecks"][0]

    assert "toy_evidence_agent" in bottleneck["recruit"]
    assert bottleneck["recruitment_source"] == "agent_selection_policy"
    assert "data_auditor_agent" not in bottleneck["recruit"]


def recovery_state(
    *,
    agents: list[dict] | None = None,
    allowed_agent_roles: list[str] | None = None,
    allowed_capability_tags: list[str] | None = None,
    required_tools: list[str] | None = None,
    recovery_success_condition: str = "context.full_text_count > 0",
    stop_signal_policy: dict | None = None,
    extra: dict | None = None,
) -> dict:
    agents = agents or [
        {
            "key": "toy_scout",
            "name": "Toy Scout",
            "committee_role": "source_scout",
            "agent_type": "toy_review_member",
            "focus": ["toy evidence", "source retrieval"],
            "tags": ["toy-evidence", "retrieval"],
            "required_tools": ["approved_source_fetch"],
        },
        {
            "key": "toy_reviewer",
            "name": "Toy Reviewer",
            "committee_role": "reviewer",
            "tags": ["toy-review"],
        },
    ]
    allowed_agent_roles = allowed_agent_roles or ["source_scout"]
    allowed_capability_tags = allowed_capability_tags or ["toy-evidence"]
    required_tools = required_tools or ["approved_source_fetch"]
    base = {
        "metadata": {
            "agent_registry": {"agents": agents},
            "os_plan": {
                "swarm_plan": {
                    "target_signals": [
                        {
                            "canonical_target": "gate:toy_evidence_gate",
                            "demand_strength": 0.91,
                        }
                    ],
                    "agent_allocation": [
                        {
                            "agent": agents[0]["key"],
                            "name": agents[0]["name"],
                            "activated": True,
                            "utility": 0.94,
                            "matched_targets": [{"canonical_target": "gate:toy_evidence_gate"}],
                        }
                    ],
                    "recovery_protocols": [
                        {
                            "id": "toy_evidence_recovery",
                            "targets": [{"target": "gate:toy_evidence_gate", "demand_strength": 0.92}],
                            "required_tools": required_tools,
                            "allowed_agent_roles": allowed_agent_roles,
                            "allowed_capability_tags": allowed_capability_tags,
                            "recovery_success_condition": recovery_success_condition,
                            "recovery_failure_candidate": "candidate:toy:insufficient_evidence",
                        }
                    ],
                    "stop_signal_policy": stop_signal_policy or {},
                }
            },
        },
        "stop_signals": [
            {
                "id": "sig-toy",
                "target": "gate:toy_evidence_gate",
                "blocking": True,
                "verification_state": "blocking",
            }
        ],
    }
    if extra:
        base.update(extra)
    return base
