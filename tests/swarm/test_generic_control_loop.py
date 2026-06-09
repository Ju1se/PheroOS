from __future__ import annotations

from runtime.swarm.control_loop import run_generic_swarm_control_loop, state_with_recovery_trace
from runtime.tool_registry import ToolRegistry
from tools.safe_tools import ToolResult


def test_swarm_loop_recruits_agents_from_target_pressure() -> None:
    report = run_generic_swarm_control_loop(toy_loop_state(full_text_count=0))

    assert report["target_pressure"]["by_target"]["gate:toy_evidence_gate"]["pressure"] >= 0.95
    assert report["activated_agents"] == ["toy_scout"]
    assert report["agent_allocation"]["selected"][0]["allocation_source"] == "target_pressure"
    assert report["agent_allocation"]["suppressed"][0]["agent"] == "toy_reviewer"


def test_swarm_loop_agent_allocation_honors_trust_and_maturity_requirements() -> None:
    state = toy_loop_state(full_text_count=0)
    state["metadata"]["agent_registry"]["agents"].append(
        {
            "key": "trusted_specialist",
            "name": "Trusted Specialist",
            "agent_type": "toy_review_member",
            "committee_role": "source_scout",
            "tags": ["toy-evidence"],
            "required_tools": ["approved_source_fetch"],
        }
    )
    state["metadata"]["os_plan"]["swarm_plan"]["agent_selection_policy"]["trust_requirements"] = {
        "allowed_trust_levels": ["trusted_first_party"]
    }
    state["metadata"]["os_plan"]["swarm_plan"]["agent_selection_policy"]["maturity_requirements"] = {
        "min_maturity": "specialist",
        "required_actions": ["participate_quorum"],
    }
    state["metadata"]["os_plan"]["swarm_plan"]["agent_allocation"].append(
        {
            "agent": "trusted_specialist",
            "name": "Trusted Specialist",
            "committee_role": "source_scout",
            "tags": ["toy-evidence"],
            "activated": False,
            "utility": 0.2,
            "matched_targets": [{"canonical_target": "gate:toy_evidence_gate", "score": 0.7}],
        }
    )
    state["metadata"]["trust_badges"] = [
        {"agent": "toy_scout", "trust_level": "trusted_first_party"},
        {"agent": "toy_reviewer", "trust_level": "trusted_first_party"},
        {"agent": "trusted_specialist", "trust_level": "trusted_first_party"},
    ]
    state["metadata"]["maturity_report"] = {
        "agents": [
            {"agent": "toy_scout", "maturity": "worker", "allowed_actions": ["perform_low_risk_task"]},
            {"agent": "toy_reviewer", "maturity": "specialist", "allowed_actions": ["participate_quorum"]},
            {"agent": "trusted_specialist", "maturity": "specialist", "allowed_actions": ["participate_quorum"]},
        ]
    }

    report = run_generic_swarm_control_loop(state)
    suppressed = {item["agent"]: item for item in report["agent_allocation"]["suppressed"]}

    assert report["activated_agents"] == ["trusted_specialist"]
    assert "trust_requirement" in report["agent_allocation"]["selected"][0]["activation_reason"]
    assert "maturity_requirement" in report["agent_allocation"]["selected"][0]["activation_reason"]
    assert suppressed["toy_scout"]["activation_reason"] == "below_min_maturity"


def test_swarm_loop_runs_recovery_before_blocking_when_recovery_declared() -> None:
    report = run_generic_swarm_control_loop(toy_loop_state(full_text_count=0))
    event_types = [event["event_type"] for event in report["events"]]

    assert report["recovery_traces"][0]["status"] == "recovery_failed"
    assert report["status"] == "blocked"
    assert event_types.index("recovery.started") < event_types.index("recovery.failed")
    assert event_types.index("recovery.protocol_selected") < event_types.index("recovery.failed")
    assert event_types.index("recovery.agents_selected") < event_types.index("recovery.failed")
    assert event_types.index("recovery.failed") < event_types.index("candidate.blocked")


def test_swarm_loop_commits_after_recovery_success() -> None:
    report = run_generic_swarm_control_loop(toy_loop_state(full_text_count=1, evidence_ready=True))

    assert report["status"] == "committed"
    assert report["recovery_traces"][0]["status"] == "recovery_succeeded"
    assert report["quorum_trace"]["committed_candidate"]["id"] == "candidate:toy:approve"
    assert report["state_updates"]["signal_resolution_report"]["status"] == "resolved_some"


def test_swarm_loop_blocks_after_recovery_failure() -> None:
    report = run_generic_swarm_control_loop(toy_loop_state(full_text_count=0))

    assert report["status"] == "blocked"
    assert report["recovery_traces"][0]["fallback_candidate"] == "candidate:toy:insufficient_evidence"
    assert report["quorum_trace"]["committed_candidate"]["id"] == "candidate:toy:insufficient_evidence"


def test_recovery_failure_writes_generic_agent_decision_without_legacy_state() -> None:
    state = {"agent_decision": {}}
    updated = state_with_recovery_trace(
        state,
        [
            {
                "status": "recovery_failed",
                "fallback_candidate": "candidate:toy:insufficient_evidence",
            }
        ],
    )

    assert updated["agent_decision"]["final_decision"] == "candidate:toy:insufficient_evidence"
    assert "committee_decision" not in updated


def test_recovery_failure_mirrors_legacy_committee_decision_only_when_present() -> None:
    state = {"committee_decision": {}}
    updated = state_with_recovery_trace(
        state,
        [
            {
                "status": "recovery_failed",
                "fallback_candidate": "candidate:toy:insufficient_evidence",
            }
        ],
    )

    assert updated["agent_decision"]["final_decision"] == "candidate:toy:insufficient_evidence"
    assert updated["committee_decision"]["final_decision"] == "candidate:toy:insufficient_evidence"


def test_swarm_loop_does_not_hardcode_investment_agents() -> None:
    report = run_generic_swarm_control_loop(toy_loop_state(full_text_count=0))
    selected = report["activated_agents"]
    recruited = [
        agent["agent"]
        for item in report["recruitment_reports"]
        for agent in item["selected_agents"]
    ]

    assert selected == ["toy_scout"]
    assert recruited == ["toy_scout"]
    assert "data_auditor_agent" not in selected + recruited
    assert "risk_manager_agent" not in selected + recruited


def test_swarm_loop_recovery_recruitment_marks_protocol_capability_lineage() -> None:
    state = toy_loop_state(full_text_count=0)
    swarm_plan = state["metadata"]["os_plan"]["swarm_plan"]
    protocol = dict(swarm_plan["recovery_protocols"][0])
    swarm_plan["capability_protocols"] = [
        {
            "capability_id": "toy-review",
            "targets": [{"canonical_target": "gate:toy_evidence_gate"}],
            "recovery_protocols": [{**protocol, "capability_id": "toy-review"}],
        }
    ]

    report = run_generic_swarm_control_loop(state)
    recruitment = report["recruitment_reports"][0]
    recruited = recruitment["selected_agents"][0]

    assert recruitment["protocol_source"] == "capability_manifest"
    assert recruitment["protocol_lineage"][0]["protocol_id"] == "toy_recovery"
    assert recruitment["protocol_lineage"][0]["capability_id"] == "toy-review"
    assert recruited["agent"] == "toy_scout"
    assert recruited["protocol_id"] == "toy_recovery"
    assert recruited["capability_id"] == "toy-review"
    assert recruited["source"] == "capability_protocol"


def test_swarm_loop_executes_declared_recovery_tools_through_registry(tmp_path) -> None:
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
    state = toy_loop_state(full_text_count=0, evidence_ready=True)
    protocol = state["metadata"]["os_plan"]["swarm_plan"]["recovery_protocols"][0]
    protocol["required_tools"] = ["toy_recover"]
    protocol["recovery_success_condition"] = "recovery.tool_success_count >= 1"
    state["recovery_context"]["tool_args_by_name"] = {"toy_recover": {"marker": "loop"}}

    report = run_generic_swarm_control_loop(state, tool_registry=registry)
    trace = report["recovery_traces"][0]
    event_types = [event["event_type"] for event in report["events"]]

    assert trace["status"] == "recovery_succeeded"
    assert trace["tool_results"] == [
        {"name": "toy_recover", "args": {"marker": "loop"}, "ok": True, "data": {"marker": "loop"}, "error": None}
    ]
    assert any(
        event["event_type"] == "recovery.tools_executed" and event["succeeded"] == ["toy_recover"]
        for event in trace["trace"]
    )
    assert "recovery.tools_executed" in event_types
    assert event_types.index("recovery.tools_executed") < event_types.index("recovery.succeeded")
    assert event_types.count("recovery.succeeded") == 1
    tool_event = next(event for event in report["events"] if event["event_type"] == "recovery.tools_executed")
    assert tool_event["payload"]["succeeded"] == ["toy_recover"]
    assert tool_event["payload"]["recovery_trace"]["selected_protocol"]["id"] == "toy_recovery"


def test_swarm_loop_uses_protocol_max_rounds() -> None:
    report = run_generic_swarm_control_loop(toy_loop_state(full_text_count=0))

    assert report["max_rounds"] == 3
    assert report["execution_loop"]["max_rounds"] == 3


def test_swarm_loop_updates_outcome_feedback_without_storing_domain_conclusion() -> None:
    report = run_generic_swarm_control_loop(toy_loop_state(full_text_count=1, evidence_ready=True))
    feedback = report["outcome_feedback"]

    assert feedback["domain_conclusion_stored"] is False
    assert "committed_candidate_label" in feedback["excluded_fields"]
    assert "agent_decision" in feedback["excluded_fields"]
    assert "committee_decision" in feedback["excluded_fields"]
    assert "investment_decision" not in feedback["excluded_fields"]
    assert "candidate:toy:approve" not in str(feedback)
    assert "Approve" not in str(feedback)


def toy_loop_state(*, full_text_count: int, evidence_ready: bool = False) -> dict:
    return {
        "run_id": "run-toy-loop",
        "task": "toy_review this artifact",
        "metadata": {
            "tenant_id": "tenant-toy",
            "agent_registry": {
                "agents": [
                    {
                        "key": "toy_scout",
                        "name": "Toy Scout",
                        "agent_type": "toy_review_member",
                        "committee_role": "source_scout",
                        "tags": ["toy-evidence"],
                        "required_tools": ["approved_source_fetch"],
                        "swarm": {"signal_emit_permissions": ["risk", "evidence"], "can_block": False},
                    },
                    {
                        "key": "toy_reviewer",
                        "name": "Toy Reviewer",
                        "agent_type": "toy_review_member",
                        "committee_role": "reviewer",
                        "tags": ["toy-review"],
                        "swarm": {"signal_emit_permissions": ["progress"], "can_block": False},
                    },
                ]
            },
            "os_plan": {
                "intent": "toy_review",
                "swarm_plan": {
                    "protocol_source": "capability_manifest",
                    "swarm_loop_policy": {"max_rounds": 3, "target_pressure_threshold": 0.7},
                    "target_signals": [
                        {
                            "target": "gate:toy_evidence_gate",
                            "canonical_target": "gate:toy_evidence_gate",
                            "demand_strength": 0.9,
                        }
                    ],
                    "agent_selection_policy": {
                        "required_roles": ["source_scout"],
                        "activation_threshold": 0.6,
                    },
                    "agent_allocation": [
                        {
                            "agent": "toy_scout",
                            "name": "Toy Scout",
                            "committee_role": "source_scout",
                            "tags": ["toy-evidence"],
                            "activated": True,
                            "utility": 0.4,
                            "matched_targets": [{"canonical_target": "gate:toy_evidence_gate", "score": 0.8}],
                        },
                        {
                            "agent": "toy_reviewer",
                            "name": "Toy Reviewer",
                            "committee_role": "reviewer",
                            "tags": ["toy-review"],
                            "activated": False,
                            "utility": 0.1,
                            "matched_targets": [{"canonical_target": "gate:toy_evidence_gate", "score": 0.1}],
                        },
                    ],
                    "candidate_policy": {
                        "candidates": [
                            {
                                "id": "candidate:toy:approve",
                                "label": "Approve",
                                "blocked_by_targets": ["gate:toy_evidence_gate"],
                            },
                            {
                                "id": "candidate:toy:reject",
                                "label": "Reject",
                                "blocked_by_targets": ["gate:toy_evidence_gate"],
                            },
                            {
                                "id": "candidate:toy:insufficient_evidence",
                                "label": "Insufficient Evidence",
                                "safe_fallback": True,
                            },
                        ],
                    },
                    "quorum_policy": {
                        "candidate_fallback": "candidate:toy:insufficient_evidence",
                        "force_fallback_when_blocked": True,
                    },
                    "stop_signal_policy": {
                        "resolution_policy": {
                            "rules": [
                                {
                                    "targets": ["gate:toy_evidence_gate"],
                                    "resolution_authority": ["toy_recovery"],
                                    "resolution_condition": {"path": "toy.evidence_ready", "equals": True},
                                    "reason": "Toy evidence recovered.",
                                }
                            ]
                        }
                    },
                    "recovery_protocols": [
                        {
                            "id": "toy_recovery",
                            "targets": [{"target": "gate:toy_evidence_gate", "demand_strength": 0.92}],
                            "allowed_agent_roles": ["source_scout"],
                            "allowed_capability_tags": ["toy-evidence"],
                            "required_tools": ["approved_source_fetch"],
                            "recovery_success_condition": "context.full_text_count > 0",
                            "recovery_failure_candidate": "candidate:toy:insufficient_evidence",
                            "max_rounds": 3,
                        }
                    ],
                },
            },
        },
        "stop_signals": [
            {
                "id": "toy-stop",
                "type": "stop_signal",
                "target": "gate:toy_evidence_gate",
                "content": "Toy evidence is missing.",
                "blocking": True,
                "verification_state": "blocking",
                "lifecycle_state": "active",
                "source_module": "toy_evidence_gate",
            }
        ],
        "agent_decision": {"final_decision": "candidate:toy:approve"} if evidence_ready else {},
        "recovery_context": {"candidate_count": 1, "full_text_count": full_text_count},
        "toy": {"evidence_ready": evidence_ready},
    }
