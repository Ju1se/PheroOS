from __future__ import annotations

from runtime.swarm.trace_store import SwarmTraceStore


def debugger_run(run_id: str = "run-debug", *, tenant_id: str = "tenant-debug") -> dict:
    swarm_plan = {
        "schema_version": "pheroos.goal_router.v1",
        "intent": "toy_review",
        "target_signals": [
            {
                "target": "gate:toy_evidence_gate",
                "canonical_target": "gate:toy_evidence_gate",
                "demand_strength": 0.91,
            }
        ],
        "agent_allocation": [
            {
                "agent": "toy_evidence_agent",
                "name": "Toy Evidence Agent",
                "matched_targets": [
                    {
                        "target": "gate:toy_evidence_gate",
                        "canonical_target": "gate:toy_evidence_gate",
                        "demand_strength": 0.91,
                        "score": 0.73,
                    }
                ],
                "utility": 0.88,
                "threshold": 0.46,
                "activated": True,
                "activation_reason": "manifest focus matches pheromone targets",
            }
        ],
        "activated_agents": ["toy_evidence_agent"],
        "capability_protocols": [
            {
                "capability_id": "toy-review",
                "intents": ["toy_review"],
                "targets": [{"canonical_target": "gate:toy_evidence_gate"}],
                "candidates": [
                    {"candidate": "candidate:toy:approve", "label": "Approve"},
                    {
                        "candidate": "candidate:toy:insufficient_evidence",
                        "label": "Insufficient Evidence",
                        "safe_fallback": True,
                    },
                ],
                "quorum_policy": {
                    "candidate_fallback": "candidate:toy:insufficient_evidence",
                    "commit_rule": "simple_majority",
                },
                "recovery_protocols": [
                    {
                        "id": "toy_recovery",
                        "targets": ["gate:toy_evidence_gate"],
                        "recovery_failure_candidate": "candidate:toy:insufficient_evidence",
                    }
                ],
                "agent_selection_policy": {
                    "required_roles": ["evidence_verifier"],
                    "target_affinity_weights": {"gate:toy_evidence_gate": 0.5},
                },
            }
        ],
        "protocol_source": "capability_manifest",
        "candidate_policy": {
            "candidates": [
                {"id": "candidate:toy:approve", "label": "Approve"},
                {"id": "candidate:toy:insufficient_evidence", "label": "Insufficient Evidence", "safe_fallback": True},
            ]
        },
        "quorum_policy": {
            "candidate_fallback": "candidate:toy:insufficient_evidence",
            "commit_rule": "simple_majority",
        },
        "stop_signal_policy": {"targets": ["gate:toy_evidence_gate"]},
        "evidence_policy": {"citation_required": True, "raw_data_allowed_in_final": False},
        "tool_policy": {"allowed_tools": ["toy_lookup"]},
        "output_policy": {"blocked_phrases": ["unsupported toy conclusion"]},
        "agent_selection_policy": {
            "required_roles": ["evidence_verifier"],
            "target_affinity_weights": {"gate:toy_evidence_gate": 0.5},
        },
        "recovery_protocols": [
            {
                "id": "toy_recovery",
                "targets": ["gate:toy_evidence_gate"],
                "recovery_failure_candidate": "candidate:toy:insufficient_evidence",
            }
        ],
        "routing_trace": [{"event_type": "protocol_targets_loaded", "target_count": 1}],
        "generated_legacy_protocol_count": 0,
        "validation_diagnostics": [],
    }
    recovery_trace = {
        "schema_version": "pheroos.recovery_trace.v1",
        "status": "recovery_failed",
        "target": "gate:toy_evidence_gate",
        "target_pressure": {"blocking_signals": 1, "target": "gate:toy_evidence_gate"},
        "selected_protocol": {"id": "toy_recovery", "max_rounds": 1},
        "selected_agents": [{"agent": "toy_evidence_agent", "score": 0.9}],
        "fallback_candidate": "candidate:toy:insufficient_evidence",
        "trace": [
            {"event_type": "recovery.protocol_selected", "protocol_id": "toy_recovery"},
            {
                "event_type": "recovery.failed",
                "protocol_id": "toy_recovery",
                "fallback_candidate": "candidate:toy:insufficient_evidence",
            },
        ],
    }
    os_routing_trace = [
        {
            "event_type": "os.intent.legacy_inferred",
            "intent": "toy_review",
            "used": False,
        },
        {
            "event_type": "os.required_capabilities.selected",
            "source": "capability_protocol",
            "legacy_fallback": False,
        },
    ]
    return {
        "run_id": run_id,
        "metadata": {"tenant_id": tenant_id, "os_plan": {"swarm_plan": swarm_plan, "os_routing_trace": os_routing_trace}},
        "pheromone_trace": [
            {
                "event_type": "recovery.started",
                "actor": "recovery_engine",
                "target": "gate:toy_evidence_gate",
                "summary": "Toy recovery started.",
            },
            {
                "event_type": "recovery.failed",
                "actor": "recovery_engine",
                "target": "gate:toy_evidence_gate",
                "payload": {"fallback_candidate": "candidate:toy:insufficient_evidence"},
            },
        ],
        "pheromone_field_snapshot": {
            "signals": [
                {
                    "id": "toy-block",
                    "type": "stop_signal",
                    "target": "gate:toy_evidence_gate",
                    "content": "Toy evidence blocked.",
                    "verification_state": "blocking",
                    "blocking": True,
                }
            ]
        },
        "agent_allocation_trace": swarm_plan["agent_allocation"],
        "quorum_trace": {
            "status": "committed",
            "candidate_source": "capability_protocol",
            "committed_candidate": {
                "id": "candidate:toy:insufficient_evidence",
                "label": "Insufficient Evidence",
                "safe_fallback": True,
            },
            "fallback_candidate": {
                "id": "candidate:toy:insufficient_evidence",
                "label": "Insufficient Evidence",
            },
        },
        "domain_workflow": {
            "workflow_id": "toy-review",
            "node_outputs": {
                "evidence_recovery": {
                    "recovery_trace": recovery_trace,
                    "signal_resolution_report": {"status": "not_applicable", "open_blockers": ["toy-block"]},
                }
            },
        },
    }


def test_swarm_trace_store_persists_timeline_blockers_and_quorum(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    run = {
        "run_id": "run-sqlite",
        "pheromone_trace": [
            {
                "event_type": "data_gate.completed",
                "actor": "data_gate",
                "target": "formal_valuation",
                "summary": "Data Gate blocked formal valuation.",
                "payload": {"api_key": "sk-should-not-leak-123456"},
            }
        ],
        "pheromone_field_snapshot": {
            "signals": [
                {
                    "id": "sig-block",
                    "type": "stop_signal",
                    "target": "formal_valuation",
                    "content": "Formal valuation blocked.",
                    "verification_state": "blocking",
                    "blocking": True,
                    "source_module": "data_gate",
                }
            ]
        },
        "quorum_trace": {
            "status": "committed",
            "committed_candidate": {"label": "Insufficient Data"},
        },
        "evidence_graph": {
            "blockers": [
                {
                    "id": "sig-block",
                    "kind": "signal",
                    "canonical_target": "decision:formal_valuation",
                    "content": "Formal valuation blocked.",
                }
            ],
            "edges": [{"source": "sig-block", "target": "permission:decision:formal_valuation", "relation": "blocks"}],
        },
        "agent_allocation_trace": [{"agent": "data_auditor_agent", "activated": True, "reason": "data gaps"}],
        "metadata": {
            "os_plan": {
                "os_routing_trace": [
                    {
                        "event_type": "os.intent.legacy_inferred",
                        "intent": "investment_analysis",
                        "used": False,
                    },
                    {
                        "event_type": "os.required_capabilities.selected",
                        "source": "capability_protocol",
                        "legacy_fallback": False,
                    },
                ]
            },
            "permission_grants": [
                {
                    "capability_id": "wrds-financial-data",
                    "permission_grants": ["network:wrds"],
                    "blocked_permissions": ["trade:execute"],
                }
            ]
        },
        "execution_log": [
            {
                "step_id": "wrds",
                "title": "Fetch WRDS financials",
                "tool_calls": [
                    {
                        "name": "wrds_company_financials",
                        "args": {"query": "AAPL", "api_key": "sk-should-not-leak"},
                        "result": {
                            "ok": True,
                            "data": {"rows": 1},
                            "tool_policy_decision": {
                                "tool_name": "wrds_company_financials",
                                "canonical_tool": "tool:wrds_company_financials",
                                "status": "allowed",
                                "reason": "allowed_by_global_and_capability_policy",
                            },
                        },
                    }
                ],
            }
        ],
    }

    store.persist_run_trace(run)

    timeline = store.timeline(run_id="run-sqlite")
    blocked = store.why_blocked(run_id="run-sqlite", target="valuation")
    committed = store.why_committed(run_id="run-sqlite")
    graph = store.evidence_graph(run_id="run-sqlite")
    allocation = store.agent_allocation(run_id="run-sqlite")
    tool_events = store.tool_events(run_id="run-sqlite")
    permission_events = store.permission_events(run_id="run-sqlite")
    snapshot = store.reconstruct_pheromone_snapshot(run_id="run-sqlite")

    event = next(item for item in timeline if item["type"] == "data_gate.completed")
    signal_event = next(item for item in timeline if item["type"] == "signal.created")
    blocking_signal_event = next(item for item in timeline if item["type"] == "signal.promoted_to_blocking")
    target_pressure_event = next(item for item in timeline if item["type"] == "target.pressure.updated")
    os_event = next(item for item in timeline if item["type"] == "os.required_capabilities.selected")
    commit_event = next(item for item in timeline if item["type"] == "candidate.committed")
    agent_event = next(item for item in timeline if item["type"] == "agent.allocated")
    tool_event = next(item for item in timeline if item["type"] == "tool.allowed")
    permission_event = next(item for item in timeline if item["type"] == "permission.pending_confirmation")
    assert event["canonical_target"] == "decision:formal_valuation"
    assert event["payload"]["api_key"] == "[redacted]"
    assert signal_event["actor"] == "data_gate"
    assert signal_event["payload"]["signal"]["content"] == "Formal valuation blocked."
    assert blocking_signal_event["lifecycle_state"] == "blocking"
    assert blocking_signal_event["payload"]["contract"]["canonical_target"] == "decision:formal_valuation"
    assert target_pressure_event["canonical_target"] == "decision:formal_valuation"
    assert target_pressure_event["payload"]["pressure"] == 0.95
    assert target_pressure_event["payload"]["reasons"][0]["source"] == "active_stop_signal"
    assert os_event["actor"] == "os_kernel"
    assert os_event["payload"]["source"] == "capability_protocol"
    assert commit_event["actor"] == "quorum_marshal"
    assert commit_event["payload"]["candidate"]["label"] == "Insufficient Data"
    assert agent_event["payload"]["agent"] == "data_auditor_agent"
    assert tool_event["payload"]["args"]["api_key"] == "[redacted]"
    assert permission_event["payload"]["permission"] == "trade:execute"
    assert blocked["blocked"] is True
    assert blocked["canonical_target"] == "decision:formal_valuation"
    assert committed["source"] == "candidate_event"
    assert committed["quorum_trace"]["committed_candidate"]["label"] == "Insufficient Data"
    assert graph["nodes"][0]["canonical_target"] == "decision:formal_valuation"
    assert graph["edges"][0]["relation"] == "blocks"
    assert allocation["data"][0]["agent"] == "data_auditor_agent"
    assert tool_events["data"][0]["tool"] == "wrds_company_financials"
    assert tool_events["data"][0]["event_type"] == "tool.allowed"
    assert tool_events["data"][0]["payload"]["args"]["api_key"] == "[redacted]"
    assert permission_events["data"][0]["event_type"] == "permission.granted"
    assert permission_events["data"][1]["event_type"] == "permission.pending_confirmation"
    assert snapshot["signal_count"] == 1
    assert snapshot["blocking_targets"] == ["decision:formal_valuation"]
    assert snapshot["stop_signals"][0]["content"] == "Formal valuation blocked."
    governance = snapshot["governance_snapshot"]
    assert governance["event_type_counts"]["signal.created"] == 1
    assert governance["event_type_counts"]["signal.promoted_to_blocking"] == 1
    assert governance["event_type_counts"]["target.pressure.updated"] == 1
    assert governance["event_type_counts"]["candidate.committed"] == 1
    assert governance["target_pressure_updates"][0]["target"] == "decision:formal_valuation"
    assert governance["committed_candidates"][0]["label"] == "Insufficient Data"
    assert governance["allocated_agents"][0]["agent"] == "data_auditor_agent"
    assert governance["tool_decisions"][0]["event_type"] == "tool.allowed"
    assert governance["permission_decisions"][1]["event_type"] == "permission.pending_confirmation"


def test_timeline_prefers_signal_events_over_stale_signal_rows(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(
        {
            "run_id": "run-timeline-event-signal",
            "metadata": {"tenant_id": "tenant-timeline"},
            "swarm_protocol_trace": [
                {
                    "event_type": "signal.created",
                    "actor": "event_gate",
                    "target": "gate:event_signal_gate",
                    "summary": "Event signal created.",
                    "payload": {
                        "signal": {
                            "id": "sig-event-timeline",
                            "type": "stop_signal",
                            "target": "gate:event_signal_gate",
                            "content": "Event-authored signal row.",
                        },
                        "signal_id": "sig-event-timeline",
                    },
                }
            ],
            "pheromone_field_snapshot": {
                "signals": [
                    {
                        "id": "sig-event-timeline",
                        "type": "stop_signal",
                        "target": "gate:stale_signal_gate",
                        "content": "Stale compatibility signal row.",
                        "blocking": True,
                    }
                ]
            },
        }
    )

    timeline = store.timeline(run_id="run-timeline-event-signal", tenant_id="tenant-timeline")

    signal_events = [item for item in timeline if item["record_type"] == "event" and item["type"].startswith("signal.")]
    signal_rows = [item for item in timeline if item["record_type"] == "signal"]
    assert [item["type"] for item in signal_events] == ["signal.created"]
    assert signal_events[0]["payload"]["signal"]["target"] == "gate:event_signal_gate"
    assert signal_rows == []


def test_swarm_trace_store_reconstructs_pheromone_snapshot_without_secret_leak(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(
        {
            "run_id": "run-replay",
            "pheromone_field_snapshot": {
                "signals": [
                    {
                        "id": "sig-secret",
                        "type": "constraint",
                        "target": "source_mode",
                        "content": "WRDS-only",
                        "metadata": {"api_key": "sk-should-not-leak-123456"},
                    },
                    {
                        "id": "sig-block",
                        "type": "stop_signal",
                        "target": "report_publication",
                        "content": "Publication blocked.",
                        "blocking": True,
                        "verification_state": "blocking",
                        "source_module": "data_gate",
                    },
                ]
            },
        }
    )

    snapshot = store.reconstruct_pheromone_snapshot(run_id="run-replay")
    timeline = store.timeline(run_id="run-replay")
    signal_event = next(item for item in timeline if item["type"] == "signal.created")

    assert snapshot["type_counts"]["constraint"] == 1
    assert snapshot["type_counts"]["stop_signal"] == 1
    assert snapshot["blocking_targets"] == ["decision:report_publication"]
    assert snapshot["signals"][0]["metadata"]["api_key"] == "[redacted]"
    assert signal_event["payload"]["signal"]["metadata"]["api_key"] == "[redacted]"
    assert snapshot["governance_snapshot"]["event_type_counts"]["signal.created"] == 2
    assert snapshot["governance_snapshot"]["event_type_counts"]["signal.promoted_to_blocking"] == 1


def test_swarm_trace_store_derives_target_pressure_events_from_control_loop_report(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(
        {
            "run_id": "run-pressure",
            "metadata": {"tenant_id": "tenant-pressure"},
            "swarm_control_loop": {
                "target_pressure": {
                    "schema_version": "pheroos.target_pressure.v1",
                    "threshold": 0.7,
                    "targets": [
                        {
                            "target": "gate:toy_evidence_gate",
                            "pressure": 0.88,
                            "reasons": [
                                {
                                    "source": "evidence_gap",
                                    "gap_count": 2,
                                    "api_key": "sk-should-not-leak-123456",
                                }
                            ],
                        }
                    ],
                }
            },
        }
    )

    timeline = store.timeline(run_id="run-pressure", tenant_id="tenant-pressure")
    event = next(item for item in timeline if item["type"] == "target.pressure.updated")
    snapshot = store.reconstruct_pheromone_snapshot(run_id="run-pressure", tenant_id="tenant-pressure")

    assert event["actor"] == "pheroos.target_pressure"
    assert event["canonical_target"] == "gate:toy_evidence_gate"
    assert event["payload"]["pressure"] == 0.88
    assert event["payload"]["source"] == "generic_swarm_control_loop"
    assert event["payload"]["target_pressure"]["reasons"][0]["api_key"] == "[redacted]"
    assert snapshot["governance_snapshot"]["event_type_counts"]["target.pressure.updated"] == 1
    assert snapshot["governance_snapshot"]["target_pressure_updates"][0]["pressure"] == 0.88


def test_swarm_trace_store_derives_candidate_block_and_outcome_feedback_events(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(
        {
            "run_id": "run-candidate-block",
            "metadata": {"tenant_id": "tenant-candidate"},
            "quorum_trace": {
                "status": "blocked",
                "candidate_source": "capability_protocol",
                "candidates": [
                    {
                        "id": "candidate:toy:approve",
                        "label": "Approve",
                        "blocked": True,
                        "blocked_by_targets": ["gate:toy_evidence_gate"],
                    }
                ],
            },
            "outcome_feedback": {
                "schema_version": "pheroos.outcome_feedback.v1",
                "process_metrics": {
                    "status": "blocked",
                    "round_count": 2,
                    "recovery_failure_count": 1,
                },
                "domain_conclusion_stored": False,
                "stored_fields": ["round_count", "status"],
                "excluded_fields": ["committed_candidate_label"],
            },
        }
    )

    timeline = store.timeline(run_id="run-candidate-block", tenant_id="tenant-candidate")
    candidate_event = next(item for item in timeline if item["type"] == "candidate.blocked")
    feedback_event = next(item for item in timeline if item["type"] == "outcome_feedback.updated")
    snapshot = store.reconstruct_pheromone_snapshot(run_id="run-candidate-block", tenant_id="tenant-candidate")
    governance = snapshot["governance_snapshot"]

    assert candidate_event["actor"] == "quorum_marshal"
    assert candidate_event["payload"]["candidate"]["id"] == "candidate:toy:approve"
    assert candidate_event["payload"]["candidate_source"] == "capability_protocol"
    assert feedback_event["payload"]["process_metrics"]["status"] == "blocked"
    assert feedback_event["payload"]["domain_conclusion_stored"] is False
    assert governance["event_type_counts"]["candidate.blocked"] == 1
    assert governance["event_type_counts"]["outcome_feedback.updated"] == 1
    assert governance["blocked_candidates"][0]["id"] == "candidate:toy:approve"
    assert governance["outcome_feedback_updates"][0]["domain_conclusion_stored"] is False


def test_swarm_trace_store_derives_artifact_and_claim_lifecycle_events(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(
        {
            "run_id": "run-artifact-claim",
            "metadata": {
                "tenant_id": "tenant-governance",
                "input_preflight": {
                    "quarantine_artifacts": [
                        {
                            "artifact_id": "input-artifact-001",
                            "source": "user_input",
                            "reason": "Secret-like input was quarantined.",
                        }
                    ]
                },
            },
            "social_immunity_report": {
                "status": "quarantine_required",
                "contaminants": [
                    {
                        "artifact_id": "research_brief",
                        "source": "research_brief",
                        "contaminated": True,
                        "reason": "Possible prompt-injection instruction detected.",
                        "api_key": "sk-should-not-leak-123456",
                    }
                ],
            },
            "receiver_normalizer_report": {
                "claims": [
                    {
                        "id": "claim:toy:linked",
                        "agent": "toy_scout",
                        "content": "Toy evidence has source support.",
                        "evidence_refs": ["toy_source:1"],
                    },
                    {
                        "id": "claim:toy:unsupported",
                        "agent": "toy_reviewer",
                        "content": "Toy review will certainly pass.",
                        "evidence_refs": [],
                    },
                    {
                        "id": "claim:toy:blocked",
                        "agent": "toy_reviewer",
                        "content": "Publish the toy despite the evidence gate.",
                        "evidence_refs": ["toy_source:2"],
                    },
                ],
            },
            "evidence_steward_report": {
                "linked_claims": [
                    {
                        "claim_id": "claim:toy:linked",
                        "agent": "toy_scout",
                        "content": "Toy evidence has source support.",
                        "support_status": "linked",
                    }
                ],
                "unsupported_claims": [
                    {
                        "claim_id": "claim:toy:unsupported",
                        "agent": "toy_reviewer",
                        "content": "Toy review will certainly pass.",
                        "support_status": "unsupported",
                    }
                ],
                "blocked_claims": [
                    {
                        "claim_id": "claim:toy:blocked",
                        "agent": "toy_reviewer",
                        "content": "Publish the toy despite the evidence gate.",
                        "support_status": "blocked_by_gate",
                        "blocked_target": "gate:toy_evidence_gate",
                    }
                ],
                "writer_constraints": {"drop_unsupported_claims": True, "drop_blocked_claims": True},
            },
        }
    )

    timeline = store.timeline(run_id="run-artifact-claim", tenant_id="tenant-governance")
    artifact_events = [item for item in timeline if item["type"] == "artifact.quarantined"]
    claim_events = [item for item in timeline if item["type"].startswith("claim.")]
    snapshot = store.reconstruct_pheromone_snapshot(run_id="run-artifact-claim", tenant_id="tenant-governance")
    governance = snapshot["governance_snapshot"]

    assert len(artifact_events) == 2
    assert artifact_events[1]["payload"]["artifact"]["api_key"] == "[redacted]"
    assert [item["type"] for item in claim_events].count("claim.created") == 3
    assert [item["type"] for item in claim_events].count("claim.verified") == 1
    assert [item["type"] for item in claim_events].count("claim.blocked") == 2
    assert governance["event_type_counts"]["artifact.quarantined"] == 2
    assert governance["event_type_counts"]["claim.created"] == 3
    assert governance["event_type_counts"]["claim.verified"] == 1
    assert governance["event_type_counts"]["claim.blocked"] == 2
    assert governance["quarantined_artifacts"][1]["api_key"] == "[redacted]"
    assert governance["created_claims"][0]["id"] == "claim:toy:linked"
    assert governance["verified_claims"][0]["claim_id"] == "claim:toy:linked"
    assert {claim["claim_id"] for claim in governance["blocked_claims"]} == {
        "claim:toy:blocked",
        "claim:toy:unsupported",
    }


def test_swarm_trace_store_derives_output_lifecycle_events(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(
        {
            "run_id": "run-output-block",
            "metadata": {"tenant_id": "tenant-output"},
            "draft_final": "# Evidence Graph Contract Guardrail Report\n\nBlocked sk-should-not-leak-123456.",
            "final": "# Output Policy Guardrail Report\n\nFinal Judge rejected the draft.",
            "agent_metrics": [{"agent": "writer"}, {"agent": "final_judge"}],
            "run_status": "completed",
        }
    )
    store.persist_run_trace(
        {
            "run_id": "run-output-published",
            "metadata": {"tenant_id": "tenant-output"},
            "draft_final": "Toy evidence is limited.",
            "final": "Toy evidence is limited. Final answer is caveated.",
            "agent_metrics": [{"agent": "writer"}, {"agent": "final_judge"}],
            "run_status": "completed",
        }
    )

    blocked_timeline = store.timeline(run_id="run-output-block", tenant_id="tenant-output")
    writer_event = next(item for item in blocked_timeline if item["type"] == "writer.blocked")
    judge_event = next(item for item in blocked_timeline if item["type"] == "final_judge.rejected")
    blocked_snapshot = store.reconstruct_pheromone_snapshot(run_id="run-output-block", tenant_id="tenant-output")
    published_timeline = store.timeline(run_id="run-output-published", tenant_id="tenant-output")
    output_event = next(item for item in published_timeline if item["type"] == "output.published")
    published_snapshot = store.reconstruct_pheromone_snapshot(run_id="run-output-published", tenant_id="tenant-output")

    assert writer_event["payload"]["guardrail_report"] == "# Evidence Graph Contract Guardrail Report"
    assert writer_event["payload"]["draft_preview"].endswith("Blocked [redacted]")
    assert judge_event["actor"] == "final_judge"
    assert judge_event["payload"]["guardrail_report"] == "# Output Policy Guardrail Report"
    assert blocked_snapshot["governance_snapshot"]["event_type_counts"]["writer.blocked"] == 1
    assert blocked_snapshot["governance_snapshot"]["event_type_counts"]["final_judge.rejected"] == 1
    assert blocked_snapshot["governance_snapshot"]["writer_blocks"][0]["draft_preview"].endswith("Blocked [redacted]")
    assert output_event["actor"] == "final_judge"
    assert output_event["payload"]["final_preview"] == "Toy evidence is limited. Final answer is caveated."
    assert published_snapshot["governance_snapshot"]["event_type_counts"]["output.published"] == 1
    assert published_snapshot["governance_snapshot"]["published_outputs"][0]["run_status"] == "completed"


def test_swarm_trace_store_derives_core_lifecycle_and_candidate_created_events(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(
        {
            "run_id": "run-core-events",
            "task": "Review toy input with api_key=sk-should-not-leak-123456",
            "metadata": {
                "tenant_id": "tenant-core",
                "_runtime_materialized": True,
                "input_envelope": {
                    "schema_version": "ai_os.input_envelope.v1",
                    "user_input_redacted": "Review toy input with api_key=[redacted]",
                    "requested_output_format": "memo",
                    "risk_mode": "normal",
                },
                "enabled_capabilities": ["toy-review"],
                "permission_grants": [{"capability_id": "toy-review", "permission_grants": ["network:approved-provider"]}],
                "os_plan": {
                    "intent": "toy_review",
                    "runtime_ready": True,
                    "required_capabilities": ["toy.review"],
                    "swarm_plan": {
                        "intent": "toy_review",
                        "candidate_policy": {
                            "candidates": [
                                {"id": "candidate:toy:approve", "label": "Approve"},
                                {"id": "candidate:toy:insufficient_evidence", "label": "Insufficient Evidence"},
                            ]
                        },
                    },
                },
            },
        }
    )

    timeline = store.timeline(run_id="run-core-events", tenant_id="tenant-core")
    input_event = next(item for item in timeline if item["type"] == "input.received")
    os_event = next(item for item in timeline if item["type"] == "os.plan.created")
    runtime_event = next(item for item in timeline if item["type"] == "runtime.materialized")
    candidate_events = [item for item in timeline if item["type"] == "candidate.created"]
    snapshot = store.reconstruct_pheromone_snapshot(run_id="run-core-events", tenant_id="tenant-core")
    governance = snapshot["governance_snapshot"]

    assert "[redacted]" in input_event["payload"]["task_preview"]
    assert "sk-should-not-leak" not in input_event["payload"]["task_preview"]
    assert os_event["payload"]["intent"] == "toy_review"
    assert os_event["payload"]["runtime_ready"] is True
    assert runtime_event["payload"]["enabled_capabilities"] == ["toy-review"]
    assert {item["payload"]["candidate_id"] for item in candidate_events} == {
        "candidate:toy:approve",
        "candidate:toy:insufficient_evidence",
    }
    assert governance["event_type_counts"]["input.received"] == 1
    assert governance["event_type_counts"]["os.plan.created"] == 1
    assert governance["event_type_counts"]["runtime.materialized"] == 1
    assert governance["event_type_counts"]["candidate.created"] == 2
    assert "[redacted]" in governance["input_events"][0]["task_preview"]
    assert "sk-should-not-leak" not in governance["input_events"][0]["task_preview"]
    assert governance["os_plan_events"][0]["required_capabilities"] == ["toy.review"]
    assert governance["runtime_materializations"][0]["enabled_capabilities"] == ["toy-review"]
    assert {item["id"] for item in governance["registered_candidates"]} == {
        "candidate:toy:approve",
        "candidate:toy:insufficient_evidence",
    }


def test_swarm_trace_store_persists_explicit_runtime_events_before_deriving_fallbacks(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(
        {
            "run_id": "run-explicit-runtime-events",
            "metadata": {"tenant_id": "tenant-explicit"},
            "swarm_protocol_trace": [
                {
                    "event_type": "swarm.execution.round_completed",
                    "actor": "pheroos.execution_loop",
                    "target": "round:1",
                    "summary": "Completed round 1.",
                    "payload": {"round": 1, "api_key": "sk-should-not-leak-123456"},
                },
                {
                    "event_type": "claim.created",
                    "actor": "receiver_normalizer",
                    "target": "claim:explicit",
                    "summary": "Explicit claim event.",
                    "payload": {"claim": {"id": "claim:explicit", "content": "Explicit runtime claim."}},
                },
            ],
            "swarm_control_loop": {
                "events": [
                    {
                        "event_type": "target.pressure.updated",
                        "actor": "pheroos.target_pressure",
                        "target": "gate:toy_evidence_gate",
                        "summary": "Explicit target pressure event.",
                        "payload": {
                            "pressure": 0.77,
                            "reasons": [{"source": "explicit_control_loop"}],
                            "source": "explicit_control_loop",
                        },
                    },
                    {
                        "event_type": "candidate.committed",
                        "actor": "pheroos.control_loop",
                        "target": "candidate:toy:approve",
                        "summary": "Explicit candidate commit.",
                        "payload": {
                            "candidate": {"id": "candidate:toy:approve", "label": "Approve"},
                            "candidate_source": "generic_control_loop",
                        },
                    },
                    {
                        "event_type": "outcome_feedback.updated",
                        "actor": "pheroos.outcome_feedback",
                        "summary": "Explicit outcome feedback.",
                        "payload": {
                            "process_metrics": {"status": "explicit"},
                            "domain_conclusion_stored": False,
                            "stored_fields": ["status"],
                            "excluded_fields": ["domain_conclusion"],
                        },
                    },
                ],
                "target_pressure": {
                    "targets": [
                        {
                            "target": "gate:toy_evidence_gate",
                            "pressure": 0.99,
                            "reasons": [{"source": "derived_should_not_duplicate"}],
                        }
                    ]
                },
                "quorum_trace": {
                    "status": "committed",
                    "candidate_source": "capability_protocol",
                    "committed_candidate": {"id": "candidate:toy:approve", "label": "Approve"},
                },
                "outcome_feedback": {
                    "process_metrics": {"status": "derived_should_not_duplicate"},
                    "domain_conclusion_stored": False,
                },
            },
            "receiver_normalizer_report": {
                "claims": [
                    {
                        "id": "claim:derived_should_not_duplicate",
                        "content": "Derived claim should not duplicate explicit claim timeline.",
                    }
                ]
            },
        }
    )

    timeline = store.timeline(run_id="run-explicit-runtime-events", tenant_id="tenant-explicit")
    snapshot = store.reconstruct_pheromone_snapshot(run_id="run-explicit-runtime-events", tenant_id="tenant-explicit")
    governance = snapshot["governance_snapshot"]

    round_event = next(item for item in timeline if item["type"] == "swarm.execution.round_completed")
    pressure_events = [item for item in timeline if item["type"] == "target.pressure.updated"]
    commit_events = [item for item in timeline if item["type"] == "candidate.committed"]
    claim_events = [item for item in timeline if item["type"].startswith("claim.")]
    feedback_events = [item for item in timeline if item["type"] == "outcome_feedback.updated"]

    assert round_event["payload"]["api_key"] == "[redacted]"
    assert len(pressure_events) == 1
    assert pressure_events[0]["payload"]["pressure"] == 0.77
    assert pressure_events[0]["payload"]["source"] == "explicit_control_loop"
    assert len(commit_events) == 1
    assert commit_events[0]["actor"] == "pheroos.control_loop"
    assert len(claim_events) == 1
    assert claim_events[0]["payload"]["claim"]["id"] == "claim:explicit"
    assert len(feedback_events) == 1
    assert feedback_events[0]["payload"]["process_metrics"]["status"] == "explicit"
    assert governance["event_type_counts"]["swarm.execution.round_completed"] == 1
    assert governance["event_type_counts"]["target.pressure.updated"] == 1
    assert governance["event_type_counts"]["candidate.committed"] == 1
    assert governance["event_type_counts"]["claim.created"] == 1
    assert governance["event_type_counts"]["outcome_feedback.updated"] == 1
    assert governance["target_pressure_updates"][0]["pressure"] == 0.77
    assert governance["committed_candidates"][0]["id"] == "candidate:toy:approve"
    assert governance["created_claims"][0]["id"] == "claim:explicit"
    assert governance["outcome_feedback_updates"][0]["process_metrics"]["status"] == "explicit"


def test_swarm_trace_store_debugger_readers_prefer_event_sourced_policy_records(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(
        {
            "run_id": "run-event-first-debugger",
            "metadata": {
                "tenant_id": "tenant-event-first",
                "permission_grants": [{"capability_id": "table-capability", "permission_grants": ["network:table"]}],
            },
            "swarm_protocol_trace": [
                {
                    "event_type": "agent.allocated",
                    "actor": "pheroos.agent_allocator",
                    "target": "agent:event_agent",
                    "summary": "Allocated event agent from target pressure.",
                    "payload": {
                        "agent": "event_agent",
                        "allocation": {
                            "agent": "event_agent",
                            "activated": True,
                            "activation_reason": "explicit runtime event",
                            "matched_targets": [
                                {
                                    "target": "gate:event_policy_gate",
                                    "canonical_target": "gate:event_policy_gate",
                                    "pressure": 0.82,
                                }
                            ],
                        },
                    },
                },
                {
                    "event_type": "tool.blocked",
                    "actor": "tool_registry",
                    "target": "tool:event_tool",
                    "summary": "Tool was blocked by explicit policy event.",
                    "payload": {
                        "tool": "event_tool",
                        "args": {"api_key": "sk-should-not-leak-123456"},
                        "tool_policy_decision": {"status": "blocked", "reason": "explicit_event_policy"},
                    },
                },
                {
                    "event_type": "permission.pending_confirmation",
                    "actor": "permission_policy",
                    "target": "network:event",
                    "summary": "Permission requires confirmation.",
                    "payload": {
                        "capability_id": "event-capability",
                        "permission": "network:event",
                        "status": "pending_confirmation",
                    },
                },
            ],
            "agent_allocation_trace": [{"agent": "table_agent", "activated": True}],
            "execution_log": [{"tool_calls": [{"name": "table_tool", "result": {"ok": True}}]}],
        }
    )

    timeline = store.timeline(run_id="run-event-first-debugger", tenant_id="tenant-event-first")
    allocation = store.agent_allocation(run_id="run-event-first-debugger", tenant_id="tenant-event-first")
    why_agent = store.why_agent(run_id="run-event-first-debugger", agent_id="event_agent", tenant_id="tenant-event-first")
    tool_events = store.tool_events(run_id="run-event-first-debugger", tenant_id="tenant-event-first")
    permission_events = store.permission_events(run_id="run-event-first-debugger", tenant_id="tenant-event-first")

    assert [item["type"] for item in timeline if item["type"].startswith("tool.")] == ["tool.blocked"]
    assert [item["type"] for item in timeline if item["type"].startswith("permission.")] == [
        "permission.pending_confirmation"
    ]
    assert allocation["source"] == "swarm_events"
    assert allocation["data"][0]["agent"] == "event_agent"
    assert why_agent["status"] == "found"
    assert why_agent["activated"] is True
    assert why_agent["activation_reason"] == "explicit runtime event"
    assert why_agent["target_pressure"][0]["canonical_target"] == "gate:event_policy_gate"
    assert why_agent["allocation_events"][0]["source"] == "swarm_events"
    assert tool_events["source"] == "swarm_events"
    assert tool_events["data"][0]["tool"] == "event_tool"
    assert tool_events["data"][0]["payload"]["args"]["api_key"] == "[redacted]"
    assert permission_events["source"] == "swarm_events"
    assert permission_events["data"][0]["permission"] == "network:event"


def test_why_blocked_prefers_event_sourced_blocking_signals(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(
        {
            "run_id": "run-event-blocked",
            "metadata": {
                "tenant_id": "tenant-event-blocked",
                "os_plan": {
                    "swarm_plan": {
                        "protocol_source": "capability_manifest",
                        "intent": "toy_review",
                        "target_signals": [{"canonical_target": "gate:event_block_gate"}],
                        "stop_signal_policy": {"rules": [{"targets": ["gate:event_block_gate"]}]},
                        "capability_protocols": [
                            {
                                "capability_id": "event-block-capability",
                                "targets": [{"canonical_target": "gate:event_block_gate"}],
                                "stop_signal_policy": {"rules": [{"targets": ["gate:event_block_gate"]}]},
                            }
                        ],
                    }
                },
            },
            "swarm_protocol_trace": [
                {
                    "event_type": "signal.promoted_to_blocking",
                    "actor": "event_gate",
                    "target": "gate:event_block_gate",
                    "lifecycle_state": "blocking",
                    "summary": "Event-sourced gate blocked the target.",
                    "payload": {
                        "signal": {
                            "id": "sig-event-block",
                            "type": "stop_signal",
                            "target": "gate:event_block_gate",
                            "content": "Blocked by explicit event with api_key=sk-should-not-leak-123456",
                            "blocking": True,
                            "source_module": "event_gate",
                        },
                        "signal_id": "sig-event-block",
                        "signal_type": "stop_signal",
                        "blocking_status": "blocking",
                    },
                }
            ],
        }
    )

    blocked = store.why_blocked(
        run_id="run-event-blocked",
        target="gate:event_block_gate",
        tenant_id="tenant-event-blocked",
    )
    snapshot = store.reconstruct_pheromone_snapshot(run_id="run-event-blocked", tenant_id="tenant-event-blocked")

    assert blocked["blocked"] is True
    assert blocked["source"] == "swarm_events"
    assert blocked["blocking_signals"][0]["signal_id"] == "sig-event-block"
    assert blocked["blocking_signals"][0]["source_module"] == "event_gate"
    assert "sk-should-not-leak" not in blocked["blocking_signals"][0]["payload"]["signal"]["content"]
    assert "[redacted]" in blocked["blocking_signals"][0]["payload"]["signal"]["content"]
    assert blocked["protocol_lineage"]["capability_protocols"][0]["capability_id"] == "event-block-capability"
    assert snapshot["source"] == "swarm_events"
    assert snapshot["signal_count"] == 1
    assert snapshot["blocking_targets"] == ["gate:event_block_gate"]
    assert snapshot["stop_signals"][0]["id"] == "sig-event-block"
    assert snapshot["stop_signals"][0]["trace_source"] == "swarm_events"
    assert snapshot["governance_snapshot"]["event_type_counts"]["signal.promoted_to_blocking"] == 1


def test_swarm_trace_store_scopes_queries_by_tenant(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(
        {
            "run_id": "run-tenant",
            "metadata": {"tenant_id": "tenant-a"},
            "pheromone_trace": [{"event_type": "data_gate.completed", "actor": "data_gate"}],
            "pheromone_field_snapshot": {
                "signals": [
                    {
                        "id": "sig-tenant",
                        "type": "stop_signal",
                        "target": "formal_valuation",
                        "content": "Blocked.",
                        "blocking": True,
                        "verification_state": "blocking",
                        "source_module": "data_gate",
                    }
                ]
            },
            "quorum_trace": {"status": "committed", "committed_candidate": {"label": "Insufficient Data"}},
            "evidence_graph": {"blockers": [{"id": "sig-tenant", "kind": "signal", "canonical_target": "decision:formal_valuation"}]},
            "agent_allocation_trace": [{"agent": "data_auditor_agent"}],
            "execution_log": [{"tool_calls": [{"name": "wrds_status", "result": {"ok": True}}]}],
            "metadata": {
                "tenant_id": "tenant-a",
                "permission_grants": [{"capability_id": "wrds", "permission_grants": ["network:wrds"]}],
            },
        }
    )

    assert store.timeline(run_id="run-tenant", tenant_id="tenant-a")
    assert store.why_blocked(run_id="run-tenant", target="formal_valuation", tenant_id="tenant-a")["blocked"] is True
    assert store.why_committed(run_id="run-tenant", tenant_id="tenant-a")["status"] == "found"
    assert store.evidence_graph(run_id="run-tenant", tenant_id="tenant-a")["nodes"]
    assert store.agent_allocation(run_id="run-tenant", tenant_id="tenant-a")["data"]
    assert store.tool_events(run_id="run-tenant", tenant_id="tenant-a")["data"]
    assert store.permission_events(run_id="run-tenant", tenant_id="tenant-a")["data"]
    assert store.reconstruct_pheromone_snapshot(run_id="run-tenant", tenant_id="tenant-a")["signal_count"] == 1

    assert store.timeline(run_id="run-tenant", tenant_id="tenant-b") == []
    assert store.why_blocked(run_id="run-tenant", target="formal_valuation", tenant_id="tenant-b")["blocked"] is False
    assert store.why_committed(run_id="run-tenant", tenant_id="tenant-b")["status"] == "missing"
    assert store.evidence_graph(run_id="run-tenant", tenant_id="tenant-b")["nodes"] == []
    assert store.agent_allocation(run_id="run-tenant", tenant_id="tenant-b")["data"] == []
    assert store.tool_events(run_id="run-tenant", tenant_id="tenant-b")["data"] == []
    assert store.permission_events(run_id="run-tenant", tenant_id="tenant-b")["data"] == []
    assert store.reconstruct_pheromone_snapshot(run_id="run-tenant", tenant_id="tenant-b")["signal_count"] == 0


def test_event_log_reconstructs_swarm_snapshot(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(debugger_run("run-snapshot"))

    snapshot = store.reconstruct_pheromone_snapshot(run_id="run-snapshot", tenant_id="tenant-debug")

    assert snapshot["signal_count"] == 1
    assert snapshot["blocking_targets"] == ["gate:toy_evidence_gate"]
    assert snapshot["stop_signals"][0]["id"] == "toy-block"
    assert snapshot["governance_snapshot"]["capability_protocols"][0]["capability_id"] == "toy-review"
    assert snapshot["governance_snapshot"]["allocated_agents"][0]["agent"] == "toy_evidence_agent"
    assert "recovery.failed" in snapshot["governance_snapshot"]["event_type_counts"]


def test_why_blocked_returns_capability_protocol_lineage(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(debugger_run("run-blocked"))

    result = store.why_blocked(run_id="run-blocked", target="gate:toy_evidence_gate", tenant_id="tenant-debug")

    assert result["blocked"] is True
    lineage = result["protocol_lineage"]
    assert lineage["protocol_source"] == "capability_manifest"
    assert lineage["target_signals"][0]["canonical_target"] == "gate:toy_evidence_gate"
    assert lineage["capability_protocols"][0]["capability_id"] == "toy-review"
    assert lineage["capability_protocols"][0]["targets"][0]["canonical_target"] == "gate:toy_evidence_gate"
    assert lineage["stop_signal_policy"]["rules"][0]["targets"] == ["gate:toy_evidence_gate"]
    assert lineage["recovery_protocols"][0]["id"] == "toy_recovery"


def test_why_committed_returns_candidate_protocol_lineage(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(debugger_run("run-committed"))

    result = store.why_committed(run_id="run-committed", tenant_id="tenant-debug")

    assert result["status"] == "found"
    assert result["source"] == "candidate_event"
    assert result["quorum_trace"]["committed_candidate"]["label"] == "Insufficient Evidence"
    lineage = result["protocol_lineage"]
    assert lineage["protocol_source"] == "capability_manifest"
    assert lineage["candidate_source"] == "capability_protocol"
    assert lineage["candidate_policy"]["candidates"][0]["id"] == "candidate:toy:insufficient_evidence"
    assert lineage["quorum_policy"]["candidate_fallback"] == "candidate:toy:insufficient_evidence"
    assert lineage["fallback_candidate"]["label"] == "Insufficient Evidence"
    assert lineage["capability_protocols"][0]["capability_id"] == "toy-review"
    assert lineage["capability_protocols"][0]["candidates"][0]["candidate"] == "candidate:toy:insufficient_evidence"
    assert lineage["capability_protocols"][0]["quorum_policy"]["candidate_fallback"] == "candidate:toy:insufficient_evidence"


def test_why_agent_returns_target_pressure_and_policy(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(debugger_run("run-agent"))

    result = store.why_agent(run_id="run-agent", agent_id="toy_evidence_agent", tenant_id="tenant-debug")

    assert result["status"] == "found"
    assert result["activated"] is True
    assert result["target_pressure"][0]["canonical_target"] == "gate:toy_evidence_gate"
    assert result["agent_selection_policy"]["required_roles"] == ["evidence_verifier"]
    assert result["routing_trace"][0]["event_type"] == "protocol_targets_loaded"
    assert result["os_routing_trace"][0]["event_type"] == "os.intent.legacy_inferred"
    lineage = result["protocol_lineage"]
    assert lineage["protocol_source"] == "capability_manifest"
    assert lineage["target_signals"][0]["canonical_target"] == "gate:toy_evidence_gate"
    assert lineage["agent_selection_policy"]["required_roles"] == ["evidence_verifier"]
    assert lineage["capability_protocols"][0]["capability_id"] == "toy-review"
    assert lineage["capability_protocols"][0]["targets"][0]["canonical_target"] == "gate:toy_evidence_gate"
    assert lineage["capability_protocols"][0]["agent_selection_policy"]["required_roles"] == ["evidence_verifier"]


def test_recovery_lineage_explains_success_or_failure(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(debugger_run("run-recovery"))

    result = store.recovery_lineage(run_id="run-recovery", target="gate:toy_evidence_gate", tenant_id="tenant-debug")

    assert result["status"] == "recovery_failed"
    assert result["source"] == "stored_recovery_trace"
    assert result["selected_protocol"]["id"] == "toy_recovery"
    assert result["selected_agents"][0]["agent"] == "toy_evidence_agent"
    assert result["fallback_candidate"] == "candidate:toy:insufficient_evidence"
    assert [event["event_type"] for event in result["recovery_events"]] == ["recovery.started", "recovery.failed"]
    lineage = result["protocol_lineage"]
    assert lineage["protocol_source"] == "capability_manifest"
    assert lineage["recovery_protocols"][0]["id"] == "toy_recovery"
    assert lineage["capability_protocols"][0]["capability_id"] == "toy-review"
    assert lineage["capability_protocols"][0]["recovery_protocols"][0]["id"] == "toy_recovery"


def test_recovery_lineage_derives_trace_from_recovery_events(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(
        {
            "run_id": "run-event-recovery",
            "metadata": {
                "tenant_id": "tenant-event-recovery",
                "os_plan": {
                    "swarm_plan": {
                        "protocol_source": "capability_manifest",
                        "intent": "toy_review",
                        "target_signals": [{"canonical_target": "gate:event_recovery_gate"}],
                        "recovery_protocols": [
                            {
                                "id": "event_recovery",
                                "targets": ["gate:event_recovery_gate"],
                                "recovery_failure_candidate": "candidate:event:blocked",
                            }
                        ],
                        "capability_protocols": [
                            {
                                "capability_id": "event-recovery-capability",
                                "targets": [{"canonical_target": "gate:event_recovery_gate"}],
                                "recovery_protocols": [
                                    {
                                        "id": "event_recovery",
                                        "targets": ["gate:event_recovery_gate"],
                                        "recovery_failure_candidate": "candidate:event:blocked",
                                    }
                                ],
                            }
                        ],
                    }
                },
            },
            "swarm_protocol_trace": [
                {
                    "event_type": "recovery.started",
                    "actor": "pheroos.control_loop",
                    "target": "gate:event_recovery_gate",
                    "summary": "Started declared event recovery.",
                    "payload": {
                        "target_pressure": {"target": "gate:event_recovery_gate", "pressure": 0.91},
                        "selected_protocol": {"id": "event_recovery", "max_rounds": 2},
                        "capability_id": "event-recovery-capability",
                        "source": "capability_protocol",
                        "protocol_source": "capability_manifest",
                        "selected_agents": [{"agent": "event_recovery_agent", "score": 0.88}],
                    },
                },
                {
                    "event_type": "recovery.failed",
                    "actor": "pheroos.control_loop",
                    "target": "gate:event_recovery_gate",
                    "summary": "Declared event recovery failed.",
                    "payload": {
                        "fallback_candidate": "candidate:event:blocked",
                        "api_key": "sk-should-not-leak-123456",
                    },
                },
            ],
        }
    )

    result = store.recovery_lineage(
        run_id="run-event-recovery",
        target="gate:event_recovery_gate",
        tenant_id="tenant-event-recovery",
    )

    assert result["status"] == "recovery_failed"
    assert result["source"] == "swarm_events"
    assert result["recovery_trace"]["source"] == "swarm_events"
    assert result["recovery_trace"]["schema_version"] == "pheroos.recovery_trace.event_derived.v1"
    assert result["target_pressure"]["pressure"] == 0.91
    assert result["selected_protocol"]["id"] == "event_recovery"
    assert result["selected_protocol"]["capability_id"] == "event-recovery-capability"
    assert result["selected_protocol"]["source"] == "capability_protocol"
    assert result["selected_agents"][0]["agent"] == "event_recovery_agent"
    assert result["fallback_candidate"] == "candidate:event:blocked"
    assert [event["event_type"] for event in result["recovery_events"]] == ["recovery.started", "recovery.failed"]
    assert result["recovery_events"][1]["payload"]["api_key"] == "[redacted]"


def test_recovery_lineage_prefers_detailed_recovery_events_over_stored_trace(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(
        {
            "run_id": "run-event-recovery-wins",
            "metadata": {
                "tenant_id": "tenant-event-recovery",
                "os_plan": {
                        "swarm_plan": {
                            "protocol_source": "capability_manifest",
                            "target_signals": [{"canonical_target": "gate:event_recovery_gate"}],
                            "recovery_protocols": [{"id": "event_recovery", "targets": ["gate:event_recovery_gate"]}],
                            "capability_protocols": [
                                {
                                    "capability_id": "event-recovery-capability",
                                    "targets": [{"canonical_target": "gate:event_recovery_gate"}],
                                    "recovery_protocols": [
                                        {"id": "event_recovery", "targets": ["gate:event_recovery_gate"]}
                                    ],
                                }
                            ],
                        }
                    },
                },
            "recovery_trace": {
                "schema_version": "pheroos.recovery_trace.v1",
                "status": "recovery_failed",
                "target": "gate:event_recovery_gate",
                "selected_protocol": {"id": "stale_recovery"},
                "selected_agents": [{"agent": "stale_agent"}],
            },
            "swarm_protocol_trace": [
                {
                    "event_type": "recovery.started",
                    "actor": "pheroos.control_loop",
                    "target": "gate:event_recovery_gate",
                    "summary": "Started event-authoritative recovery.",
                    "payload": {
                        "target_pressure": {"target": "gate:event_recovery_gate", "pressure": 0.93},
                        "selected_protocol": {"id": "event_recovery", "max_rounds": 2},
                        "selected_agents": [{"agent": "event_recovery_agent", "score": 0.91}],
                    },
                },
                {
                    "event_type": "recovery.failed",
                    "actor": "pheroos.control_loop",
                    "target": "gate:event_recovery_gate",
                    "summary": "Event-authoritative recovery failed.",
                    "payload": {"fallback_candidate": "candidate:event:blocked"},
                },
            ],
        }
    )

    result = store.recovery_lineage(
        run_id="run-event-recovery-wins",
        target="gate:event_recovery_gate",
        tenant_id="tenant-event-recovery",
    )

    assert result["source"] == "swarm_events"
    assert result["selected_protocol"]["id"] == "event_recovery"
    assert result["selected_agents"][0]["agent"] == "event_recovery_agent"
    assert result["target_pressure"]["pressure"] == 0.93
    assert result["fallback_candidate"] == "candidate:event:blocked"
    assert result["protocol_lineage"]["recovery_protocols"][0]["id"] == "event_recovery"
    assert result["protocol_lineage"]["capability_protocols"][0]["capability_id"] == "event-recovery-capability"


def test_protocol_lineage_can_be_reconstructed_from_protocol_loaded_events(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    protocol = {
        "capability_id": "event-protocol-capability",
        "targets": [{"canonical_target": "gate:event_protocol_gate"}],
        "candidates": [{"candidate": "candidate:event:blocked", "label": "Event Blocked"}],
        "quorum_policy": {"candidate_fallback": "candidate:event:blocked"},
        "stop_signal_policy": {"rules": [{"targets": ["gate:event_protocol_gate"]}]},
        "recovery_protocols": [{"id": "event_protocol_recovery", "targets": ["gate:event_protocol_gate"]}],
        "agent_selection_policy": {"required_roles": ["event_reviewer"]},
    }
    store.persist_run_trace(
        {
            "run_id": "run-event-protocol-lineage",
            "metadata": {"tenant_id": "tenant-event-protocol"},
            "swarm_protocol_trace": [
                {
                    "event_type": "capability.protocol.loaded",
                    "actor": "runtime.materializer",
                    "target": "capability:event-protocol-capability",
                    "summary": "Loaded event-only protocol.",
                    "payload": {
                        "capability_id": "event-protocol-capability",
                        "protocol": protocol,
                        "protocol_source": "capability_manifest",
                        "intent": "event_protocol_review",
                    },
                },
                {
                    "event_type": "signal.promoted_to_blocking",
                    "actor": "event_gate",
                    "target": "gate:event_protocol_gate",
                    "lifecycle_state": "blocking",
                    "summary": "Event protocol gate blocked.",
                    "payload": {
                        "signal": {
                            "id": "sig-event-protocol",
                            "type": "stop_signal",
                            "target": "gate:event_protocol_gate",
                            "blocking": True,
                        },
                        "blocking_status": "blocking",
                    },
                },
                {
                    "event_type": "candidate.committed",
                    "actor": "pheroos.control_loop",
                    "target": "candidate:event:blocked",
                    "summary": "Committed event protocol fallback.",
                    "payload": {
                        "candidate": {"id": "candidate:event:blocked", "label": "Event Blocked"},
                        "candidate_source": "capability_protocol",
                    },
                },
            ],
        }
    )

    protocol_bundle = store.capability_protocol(run_id="run-event-protocol-lineage", tenant_id="tenant-event-protocol")
    blocked = store.why_blocked(
        run_id="run-event-protocol-lineage",
        target="gate:event_protocol_gate",
        tenant_id="tenant-event-protocol",
    )
    committed = store.why_committed(run_id="run-event-protocol-lineage", tenant_id="tenant-event-protocol")

    assert protocol_bundle["status"] == "found"
    assert protocol_bundle["protocol_source"] == "capability_manifest"
    assert protocol_bundle["intent"] == "event_protocol_review"
    assert protocol_bundle["capability_protocols"][0]["capability_id"] == "event-protocol-capability"
    assert protocol_bundle["target_signals"][0]["canonical_target"] == "gate:event_protocol_gate"
    assert protocol_bundle["recovery_protocols"][0]["id"] == "event_protocol_recovery"
    assert protocol_bundle["recovery_protocols"][0]["capability_id"] == "event-protocol-capability"
    assert protocol_bundle["candidate_policy"]["candidates"][0]["candidate"] == "candidate:event:blocked"
    assert protocol_bundle["quorum_policy"]["candidate_fallback"] == "candidate:event:blocked"
    assert protocol_bundle["stop_signal_policy"]["rules"][0]["targets"] == ["gate:event_protocol_gate"]
    assert protocol_bundle["agent_selection_policy"]["required_roles"] == ["event_reviewer"]
    assert blocked["blocked"] is True
    assert blocked["protocol_lineage"]["capability_protocols"][0]["capability_id"] == "event-protocol-capability"
    assert blocked["protocol_lineage"]["stop_signal_policy"]["rules"][0]["targets"] == ["gate:event_protocol_gate"]
    assert blocked["protocol_lineage"]["capability_protocols"][0]["stop_signal_rules"][0]["targets"] == [
        "gate:event_protocol_gate"
    ]
    assert committed["status"] == "found"
    assert committed["protocol_lineage"]["capability_protocols"][0]["capability_id"] == "event-protocol-capability"
    assert committed["protocol_lineage"]["capability_protocols"][0]["quorum_policy"]["candidate_fallback"] == (
        "candidate:event:blocked"
    )


def test_evidence_graph_derives_nodes_from_governance_events_when_table_empty(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(
        {
            "run_id": "run-event-evidence-graph",
            "metadata": {"tenant_id": "tenant-event-graph"},
            "swarm_protocol_trace": [
                {
                    "event_type": "claim.created",
                    "actor": "receiver_normalizer",
                    "target": "claim:event-created",
                    "summary": "Created event claim.",
                    "payload": {
                        "claim": {"id": "claim:event-created", "content": "Event claim with api_key=sk-should-not-leak-123456"},
                        "claim_id": "claim:event-created",
                    },
                },
                {
                    "event_type": "claim.verified",
                    "actor": "evidence_steward",
                    "target": "claim:event-verified",
                    "lifecycle_state": "verified",
                    "summary": "Verified event claim.",
                    "payload": {
                        "claim": {"claim_id": "claim:event-verified", "content": "Supported event claim."},
                        "claim_id": "claim:event-verified",
                        "support_status": "linked",
                    },
                },
                {
                    "event_type": "artifact.quarantined",
                    "actor": "social_immunity",
                    "target": "artifact:event-contaminant",
                    "lifecycle_state": "blocking",
                    "summary": "Quarantined event artifact.",
                    "payload": {
                        "artifact": {
                            "artifact_id": "event-contaminant",
                            "reason": "Prompt-injection artifact was quarantined.",
                        }
                    },
                },
                {
                    "event_type": "signal.promoted_to_blocking",
                    "actor": "event_gate",
                    "target": "gate:event_evidence_gate",
                    "lifecycle_state": "blocking",
                    "summary": "Event evidence gate blocked.",
                    "payload": {
                        "signal": {
                            "id": "sig-event-evidence",
                            "type": "stop_signal",
                            "target": "gate:event_evidence_gate",
                            "blocking": True,
                        },
                        "blocking_status": "blocking",
                    },
                },
            ],
        }
    )

    graph = store.evidence_graph(run_id="run-event-evidence-graph", tenant_id="tenant-event-graph")

    assert graph["source"] == "swarm_events"
    assert graph["edges"] == []
    assert {node["kind"] for node in graph["nodes"]} == {"claim", "artifact", "signal"}
    created = next(node for node in graph["nodes"] if node["event_type"] == "claim.created")
    verified = next(node for node in graph["nodes"] if node["event_type"] == "claim.verified")
    artifact = next(node for node in graph["nodes"] if node["event_type"] == "artifact.quarantined")
    signal = next(node for node in graph["nodes"] if node["event_type"] == "signal.promoted_to_blocking")
    assert created["verification_state"] == "created"
    assert "sk-should-not-leak" not in created["payload"]["claim"]["content"]
    assert verified["verification_state"] == "verified"
    assert artifact["blocking"] is True
    assert signal["canonical_target"] == "gate:event_evidence_gate"


def test_evidence_graph_prefers_governance_events_over_stale_table_nodes(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(
        {
            "run_id": "run-event-evidence-graph-table",
            "metadata": {"tenant_id": "tenant-event-graph"},
            "evidence_graph": {
                "blockers": [
                    {
                        "id": "sig-event-evidence",
                        "kind": "signal",
                        "canonical_target": "gate:stale_evidence_gate",
                        "verification_state": "stale",
                        "content": "Stale table blocker.",
                    }
                ],
                "edges": [
                    {
                        "source": "sig-event-evidence",
                        "target": "claim:stale",
                        "relation": "blocks",
                    }
                ],
            },
            "swarm_protocol_trace": [
                {
                    "event_type": "signal.promoted_to_blocking",
                    "actor": "event_gate",
                    "target": "gate:event_evidence_gate",
                    "lifecycle_state": "blocking",
                    "summary": "Event evidence gate blocked.",
                    "payload": {
                        "signal": {
                            "id": "sig-event-evidence",
                            "type": "stop_signal",
                            "target": "gate:event_evidence_gate",
                            "blocking": True,
                            "content": "Event blocker with api_key=sk-should-not-leak-123456",
                        },
                        "blocking_status": "blocking",
                    },
                }
            ],
        }
    )

    graph = store.evidence_graph(run_id="run-event-evidence-graph-table", tenant_id="tenant-event-graph")

    assert graph["source"] == "swarm_events+evidence_tables"
    assert graph["edges"][0]["relation"] == "blocks"
    signal = next(node for node in graph["nodes"] if node["node_id"] == "sig-event-evidence")
    assert signal["source"] == "swarm_events"
    assert signal["trace_sources"] == ["evidence_tables", "swarm_events"]
    assert signal["canonical_target"] == "gate:event_evidence_gate"
    assert signal["event_type"] == "signal.promoted_to_blocking"
    assert signal["verification_state"] == "blocking"
    assert "should-not-leak" not in signal["payload"]["signal"]["content"]
    assert "[redacted]" in signal["payload"]["signal"]["content"]


def test_capability_protocol_returns_protocol_bundle(tmp_path) -> None:
    store = SwarmTraceStore(tmp_path / "trace.sqlite3")
    store.persist_run_trace(debugger_run("run-protocol"))

    result = store.capability_protocol(run_id="run-protocol", tenant_id="tenant-debug")
    timeline = store.timeline(run_id="run-protocol", tenant_id="tenant-debug")
    protocol_event = next(item for item in timeline if item["type"] == "capability.protocol.loaded")

    assert result["status"] == "found"
    assert result["intent"] == "toy_review"
    assert result["protocol_source"] == "capability_manifest"
    assert result["os_routing_trace"][1]["source"] == "capability_protocol"
    assert result["capability_protocols"][0]["capability_id"] == "toy-review"
    assert result["target_signals"][0]["canonical_target"] == "gate:toy_evidence_gate"
    assert result["evidence_policy"]["citation_required"] is True
    assert protocol_event["actor"] == "runtime.materializer"
    assert protocol_event["payload"]["capability_id"] == "toy-review"
