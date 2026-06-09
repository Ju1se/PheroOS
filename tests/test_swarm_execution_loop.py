from __future__ import annotations

from runtime.swarm.execution_loop import agent_manifest_index, public_execution_loop_report, run_swarm_execution_loop
from runtime.swarm.signal_extractor import initial_signals_from_state, update_state_with_signals
from runtime.swarm_pipeline import attach_swarm_execution_loop


def test_swarm_execution_loop_runs_observe_propose_verify_schedule() -> None:
    state = evidence_research_state()
    seed = update_state_with_signals(state, initial_signals_from_state(state))
    loop = run_swarm_execution_loop({**state, **seed})
    report = public_execution_loop_report(loop)

    assert report["status"] == "completed"
    assert report["round_count"] >= 1
    assert report["accepted_signal_count"] >= 2
    assert report["rounds"][0]["observe"]
    assert report["rounds"][0]["proposals"]
    assert report["rounds"][0]["verification"]
    assert "claim_decomposition_agent" in report["activated_agents"]
    assert any(signal["target"] == "research:claim_decomposition" for signal in report["accepted_signals"])


def test_swarm_execution_loop_keeps_agent_stop_signal_contested_and_nonblocking() -> None:
    state = {
        "run_id": "run-loop-stop",
        "metadata": {
            "tenant_id": "tenant-a",
            "os_plan": {
                "intent": "evidence_research",
                "swarm_plan": {
                    "target_signals": [
                        {
                            "canonical_target": "gate:research_evidence_gate",
                            "demand_strength": 0.9,
                            "content": "Gate evidence before synthesis.",
                        }
                    ],
                    "agent_allocation": [
                        {
                            "agent": "gatekeeper_agent",
                            "name": "Gatekeeper",
                            "activated": True,
                            "utility": 0.9,
                            "matched_targets": [
                                {
                                    "canonical_target": "gate:research_evidence_gate",
                                    "score": 0.8,
                                }
                            ],
                        }
                    ],
                },
            },
            "agent_registry": {
                "agents": [
                    {
                        "key": "gatekeeper_agent",
                        "name": "Gatekeeper",
                        "agent_type": "evidence_research_member",
                        "committee_role": "gatekeeper",
                        "swarm": {
                            "signal_emit_permissions": ["stop_signal"],
                            "can_block": True,
                        },
                    }
                ]
            },
        },
    }

    loop = run_swarm_execution_loop(state)
    report = public_execution_loop_report(loop)

    assert report["accepted_signals"]
    signal = report["accepted_signals"][0]
    assert signal["type"] == "stop_signal"
    assert signal["verification_state"] == "contested"
    assert signal["blocking"] is False
    verification = report["rounds"][0]["verification"][0]
    assert verification["status"] == "retained_contested"


def test_swarm_execution_loop_agent_manifest_index_reads_generic_agent_catalog() -> None:
    index = agent_manifest_index(
        {
            "agent_catalog": [
                {
                    "key": "capability_agent",
                    "name": "Capability Agent",
                    "committee_role": "source_scout",
                }
            ],
            "committee_agent_catalog": [
                {
                    "key": "legacy_agent",
                    "name": "Legacy Agent",
                    "committee_role": "legacy_source",
                }
            ],
        }
    )

    assert index["capability_agent"]["committee_role"] == "source_scout"
    assert index["legacy_agent"]["committee_role"] == "legacy_source"


def test_attach_swarm_execution_loop_updates_field_and_protocol_trace() -> None:
    state = evidence_research_state()
    seed = update_state_with_signals(state, initial_signals_from_state(state))
    result = attach_swarm_execution_loop(state, seed)

    assert result["swarm_execution_loop"]["status"] == "completed"
    assert result["pheromone_field_snapshot"]["type_counts"]["evidence"] >= 1
    assert any(
        event["event_type"] == "swarm.execution.round_completed"
        for event in result["swarm_protocol_trace"]
    )


def test_swarm_execution_loop_uses_capability_protocol_rounds_and_recovery() -> None:
    state = {
        "run_id": "run-loop-protocol",
        "metadata": {
            "tenant_id": "tenant-a",
            "os_plan": {
                "intent": "evidence_research",
                "swarm_plan": {
                    "protocol_source": "capability_manifest",
                    "max_rounds": 3,
                    "recovery_protocols": [
                        {
                            "id": "declared_recovery",
                            "targets": [{"canonical_target": "gate:research_evidence_gate"}],
                            "max_rounds": 3,
                        }
                    ],
                    "candidate_policy": {"candidate_type": "research_synthesis"},
                    "quorum_policy": {"max_swarm_rounds": 3},
                    "stop_signal_policy": {"authority_level_required": 3},
                    "target_signals": [
                        {
                            "canonical_target": "gate:research_evidence_gate",
                            "demand_strength": 0.9,
                            "content": "Gate evidence before synthesis.",
                        }
                    ],
                    "agent_allocation": [
                        {
                            "agent": "evidence_gate_agent",
                            "name": "Evidence Gate Agent",
                            "activated": True,
                            "utility": 0.91,
                            "matched_targets": [{"canonical_target": "gate:research_evidence_gate", "score": 0.8}],
                        }
                    ],
                },
            },
            "agent_registry": {
                "agents": [
                    {
                        "key": "evidence_gate_agent",
                        "name": "Evidence Gate Agent",
                        "agent_type": "evidence_research_member",
                        "committee_role": "evidence_gate",
                        "swarm": {"signal_emit_permissions": ["risk"], "can_block": False},
                    }
                ]
            },
        },
    }

    report = public_execution_loop_report(run_swarm_execution_loop(state))

    assert report["protocol_source"] == "capability_manifest"
    assert report["max_rounds"] == 3
    assert report["recovery_protocols"][0]["id"] == "declared_recovery"
    assert report["candidate_policy"]["candidate_type"] == "research_synthesis"
    assert report["round_count"] >= 2
    assert report["rounds"][0]["scheduled_next_wave"] == ["evidence_gate_agent"]


def evidence_research_state() -> dict:
    return {
        "run_id": "run-loop",
        "task": "研究蚁群以及蜂群的群体决策机制可以对 multi-agent 系统的借鉴",
        "metadata": {
            "tenant_id": "tenant-a",
            "os_plan": {
                "intent": "evidence_research",
                "swarm_plan": {
                    "target_signals": [
                        {
                            "canonical_target": "research:claim_decomposition",
                            "demand_strength": 0.9,
                            "content": "Decompose biological swarm mechanisms into claims.",
                        },
                        {
                            "canonical_target": "gate:research_citation_audit",
                            "demand_strength": 0.74,
                            "content": "Audit citation support.",
                        },
                    ],
                    "agent_allocation": [
                        {
                            "agent": "claim_decomposition_agent",
                            "name": "Claim Decomposition Agent",
                            "activated": True,
                            "utility": 0.82,
                            "matched_targets": [
                                {
                                    "canonical_target": "research:claim_decomposition",
                                    "score": 0.7,
                                }
                            ],
                        },
                        {
                            "agent": "citation_auditor_agent",
                            "name": "Citation Auditor Agent",
                            "activated": True,
                            "utility": 0.78,
                            "matched_targets": [
                                {
                                    "canonical_target": "gate:research_citation_audit",
                                    "score": 0.7,
                                }
                            ],
                        },
                    ],
                },
            },
            "agent_registry": {
                "agents": [
                    {
                        "key": "claim_decomposition_agent",
                        "name": "Claim Decomposition Agent",
                        "agent_type": "evidence_research_member",
                        "committee_role": "claim_decomposer",
                        "swarm": {
                            "signal_emit_permissions": ["evidence", "risk"],
                            "can_block": False,
                        },
                    },
                    {
                        "key": "citation_auditor_agent",
                        "name": "Citation Auditor Agent",
                        "agent_type": "evidence_research_member",
                        "committee_role": "citation_auditor",
                        "swarm": {
                            "signal_emit_permissions": ["risk", "stop_signal", "negative"],
                            "can_block": True,
                        },
                    },
                ]
            },
        },
    }
