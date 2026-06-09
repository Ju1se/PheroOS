from __future__ import annotations

from runtime.capability_registry import CapabilityRegistry
from runtime.final_judge_guardrails import apply_final_judge_guardrails
from runtime.output_contract import candidate_labels, raw_data_policy_violation
from runtime.swarm.goal_router import build_goal_routed_swarm_plan
from runtime.writer_guardrails import apply_writer_guardrails, inferred_actions, inferred_writer_actions, writer_system_prompt


def test_writer_uses_capability_output_policy() -> None:
    state = {"metadata": {"os_plan": {"swarm_plan": toy_output_plan()}}}

    blocked = apply_writer_guardrails("This toy review is ready.", state)
    allowed = apply_writer_guardrails("This toy review is ready. Toy evidence is limited.", state)

    assert "Output Policy Guardrail Report" in blocked
    assert "missing_required_caveat" in blocked
    assert "Guardrail Report" not in allowed


def test_writer_prompt_uses_capability_policy_summary_without_investment_hardcode() -> None:
    prompt = writer_system_prompt({"metadata": {"os_plan": {"swarm_plan": toy_output_plan()}}})

    assert "Toy evidence is limited." in prompt
    assert "Toy evidence blocked" in prompt
    assert "writer:publish_report" in prompt
    assert "WRDS" not in prompt
    assert "investment" not in prompt.lower()
    assert "committee outputs" not in prompt
    assert "report publication" not in prompt.lower()
    assert "blocks publication" in prompt


def test_writer_cannot_create_unsupported_claim() -> None:
    state = {"metadata": {"os_plan": {"swarm_plan": toy_output_plan()}}}

    guarded = apply_writer_guardrails("This includes unsupported toy claim. Toy evidence is limited.", state)

    assert "Output Policy Guardrail Report" in guarded
    assert "blocked_phrase" in guarded


def test_capability_cannot_allow_writer_to_create_facts() -> None:
    state = {"metadata": {"os_plan": {"swarm_plan": toy_output_plan(writer_can_create_facts=True)}}}

    guarded = apply_writer_guardrails("Revenue will double next year. Toy evidence is limited.", state)

    assert "Output Policy Guardrail Report" in guarded
    assert "unsupported_strong_claim" in guarded


def test_final_judge_rejects_output_inconsistent_with_committed_candidate() -> None:
    guarded = apply_final_judge_guardrails(
        "Buy with a target price of 100.",
        investment_output_state(),
    )

    assert "Output Policy Guardrail Report" in guarded
    assert "committed_candidate_conflict_phrase" in guarded


def test_investment_formal_valuation_block_still_works() -> None:
    guarded = apply_writer_guardrails(
        "正式估值：买入，目标价 100。",
        {
            "stop_signals": [
                {
                    "target": "decision:formal_valuation",
                    "blocking": True,
                    "verification_state": "blocking",
                    "content": "Data Gate blocked formal valuation.",
                }
            ]
        },
    )

    assert "Swarm Stop-Signal Guardrail Report" in guarded


def test_investment_final_judge_recommendation_marker_comes_from_protocol() -> None:
    state = investment_plan_state()
    state["stop_signals"] = [
        {
            "target": "decision:formal_valuation",
            "blocking": True,
            "verification_state": "blocking",
            "content": "Data Gate blocked formal valuation.",
        }
    ]

    actions = inferred_actions("Approve Buy with target price 100. WRDS-only preliminary view.", state=state, actor="final_judge")
    guarded = apply_final_judge_guardrails("Approve Buy with target price 100. WRDS-only preliminary view.", state)

    assert actions == ["final_judge:investment_recommendation"]
    assert "Stop-Signal Action Policy Guardrail Report" in guarded
    assert "final_judge:investment_recommendation" in guarded


def test_writer_action_markers_come_from_stop_signal_policy() -> None:
    state = {
        "metadata": {"os_plan": {"swarm_plan": toy_output_plan()}},
        "stop_signals": [
            {
                "target": "decision:toy_accept",
                "blocking": True,
                "verification_state": "blocking",
                "content": "Toy publication is blocked.",
            }
        ],
    }

    actions = inferred_writer_actions("Ship toy report. Toy evidence is limited.", state=state)
    guarded = apply_writer_guardrails("Ship toy report. Toy evidence is limited.", state)

    assert actions == ["writer:publish_report"]
    assert "Stop-Signal Action Policy Guardrail Report" in guarded
    assert "writer:publish_report" in guarded


def test_legacy_writer_recommendation_fallback_action_is_preserved() -> None:
    assert inferred_writer_actions("Buy with target price 100.", state={}) == ["writer:formal_valuation"]


def test_declared_action_markers_disable_unrelated_legacy_writer_cues() -> None:
    state = {
        "metadata": {
            "os_plan": {
                "swarm_plan": {
                    "stop_signal_policy": {
                        "action_markers": [
                            {
                                "action": "writer:publish_report",
                                "phrases": ["ship toy report"],
                            }
                        ],
                    }
                }
            }
        }
    }

    assert inferred_actions("successfully fixed; tests passed", state=state, actor="writer") == []


def test_final_judge_action_markers_come_from_stop_signal_policy() -> None:
    state = {
        "metadata": {
            "os_plan": {
                "swarm_plan": {
                    "stop_signal_policy": {
                        "action_markers": [
                            {
                                "action": "final_judge:approve_publish",
                                "phrases": ["approve toy publication"],
                            }
                        ],
                        "rules": [
                            {
                                "id": "toy_gate_blocks_final_approval",
                                "trigger_targets": ["decision:toy_accept"],
                                "blocked_actions": ["final_judge:approve_publish"],
                            }
                        ],
                    }
                }
            }
        },
        "stop_signals": [
            {
                "target": "decision:toy_accept",
                "blocking": True,
                "verification_state": "blocking",
                "content": "Toy final approval is blocked.",
            }
        ],
    }

    actions = inferred_actions("Approve toy publication.", state=state, actor="final_judge")
    guarded = apply_final_judge_guardrails("Approve toy publication.", state)

    assert actions == ["final_judge:approve_publish"]
    assert "Stop-Signal Action Policy Guardrail Report" in guarded
    assert "final_judge:approve_publish" in guarded


def test_toy_capability_output_policy_blocks_custom_phrase() -> None:
    state = {"metadata": {"os_plan": {"swarm_plan": toy_output_plan()}}}

    guarded = apply_final_judge_guardrails("unsupported toy claim. Toy evidence is limited.", state)

    assert "Output Policy Guardrail Report" in guarded
    assert "unsupported toy claim" in guarded


def test_writer_uses_capability_evidence_policy_for_raw_data() -> None:
    state = {"metadata": {"os_plan": {"swarm_plan": toy_output_plan()}}}

    guarded = apply_writer_guardrails("Toy evidence raw_rows=[secret sample]. Toy evidence is limited.", state)

    assert "Output Policy Guardrail Report" in guarded
    assert "raw_data_not_allowed_in_final" in guarded


def test_writer_raw_data_markers_come_from_capability_evidence_policy() -> None:
    state = {"metadata": {"os_plan": {"swarm_plan": toy_output_plan(raw_data_markers=["toy-secret-row="])}}}

    violation = raw_data_policy_violation("Toy evidence toy-secret-row=abc. Toy evidence is limited.", state)
    guarded = apply_writer_guardrails("Toy evidence toy-secret-row=abc. Toy evidence is limited.", state)

    assert violation is not None
    assert violation["policy_source"] == "capability_evidence_policy"
    assert violation["matched_markers"] == ["toy-secret-row="]
    assert "Output Policy Guardrail Report" in guarded
    assert "raw_data_not_allowed_in_final" in guarded


def test_capability_cannot_allow_raw_data_in_final_output() -> None:
    state = {
        "metadata": {
            "os_plan": {
                "swarm_plan": toy_output_plan(
                    raw_data_allowed_in_final=True,
                    raw_data_markers=["toy-secret-row="],
                )
            }
        }
    }

    violation = raw_data_policy_violation("Toy evidence toy-secret-row=abc. Toy evidence is limited.", state)
    guarded = apply_writer_guardrails("Toy evidence toy-secret-row=abc. Toy evidence is limited.", state)
    prompt = writer_system_prompt(state)

    assert violation is not None
    assert violation["code"] == "raw_data_not_allowed_in_final"
    assert violation["policy_source"] == "capability_evidence_policy"
    assert violation["declared_raw_data_allowed_in_final"] is True
    assert "Output Policy Guardrail Report" in guarded
    assert "Raw data is not allowed in final output." in prompt


def test_final_judge_requires_citation_when_evidence_policy_says_so() -> None:
    state = {
        "metadata": {"os_plan": {"swarm_plan": toy_output_plan(citation_required=True)}},
        "evidence_graph": {
            "decision_claims": [
                {
                    "id": "claim:toy",
                    "content": "Toy sample passed review.",
                    "claim_type": "toy_claim",
                    "output_allowed": True,
                }
            ],
            "edges": [{"source": "toy_evidence:1", "target": "claim:toy", "relation": "supports"}],
            "metrics": [],
        },
    }

    guarded = apply_final_judge_guardrails("Toy sample passed review. Toy evidence is limited.", state)
    allowed = apply_final_judge_guardrails(
        "Toy sample passed review. Source: toy_evidence:1. Toy evidence is limited.",
        state,
    )

    assert "Output Policy Guardrail Report" in guarded
    assert "`final_judge` output" in guarded
    assert "missing_citation" in guarded
    assert "Guardrail Report" not in allowed


def test_writer_blocks_caveated_claim_when_evidence_policy_requires_evidence() -> None:
    state = {
        "metadata": {"os_plan": {"swarm_plan": toy_output_plan(allow_caveated_claim_without_evidence=False)}},
        "evidence_graph": {
            "decision_claims": [
                {
                    "id": "claim:toy",
                    "content": "Toy sample passed review.",
                    "claim_type": "toy_claim",
                    "output_allowed": True,
                }
            ],
            "edges": [],
            "metrics": [],
        },
    }

    guarded = apply_writer_guardrails("初步看，Toy sample passed review. Toy evidence is limited.", state)

    assert "Output Policy Guardrail Report" in guarded
    assert "missing_required_evidence" in guarded


def test_final_judge_uses_generic_committed_candidate_check() -> None:
    state = {
        "metadata": {"os_plan": {"swarm_plan": toy_output_plan()}},
        "quorum_trace": {
            "committed_candidate": {"id": "candidate:toy:approve", "label": "Approve"},
            "candidates": [
                {"id": "candidate:toy:approve", "label": "Approve"},
                {"id": "candidate:toy:reject", "label": "Reject"},
            ],
        },
    }

    guarded = apply_final_judge_guardrails("Reject. Toy evidence is limited.", state)

    assert "Output Policy Guardrail Report" in guarded
    assert "committed_candidate_conflict" in guarded


def test_candidate_labels_do_not_invent_defaults_without_policy() -> None:
    assert candidate_labels({}) == []


def test_investment_candidate_labels_come_from_capability_policy() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    plan = build_goal_routed_swarm_plan(
        task="Analyze AAPL as an investment",
        intent="investment_analysis",
        required_capability_types=["investment.research"],
        agents=[],
        capabilities=[manifest.to_public_dict()],
    )

    labels = candidate_labels({"metadata": {"os_plan": {"swarm_plan": plan}}})

    assert {"Buy", "Watch", "Avoid", "Sell", "Insufficient Data"} <= set(labels)


def test_investment_committed_candidate_conflict_comes_from_output_policy() -> None:
    state = investment_output_state()

    guarded = apply_writer_guardrails("Final Decision: Buy with target price 100.", state)

    assert "Output Policy Guardrail Report" in guarded
    assert "committed_candidate_conflict_phrase" in guarded


def test_output_policy_requires_defect_memo_when_publish_report_is_blocked() -> None:
    state = {
        "metadata": {"os_plan": {"swarm_plan": toy_output_plan()}},
        "stop_signals": [
            {
                "type": "stop_signal",
                "target": "decision:toy_accept",
                "blocking": True,
                "verification_state": "blocking",
                "content": "Toy evidence gate blocked publication.",
            }
        ],
    }

    blocked = apply_writer_guardrails("Toy review is ready. Toy evidence is limited.", state)
    allowed = apply_final_judge_guardrails("# Toy Defect Report\n\nPublication blocked. Toy evidence is limited.", state)
    declared_marker_allowed = apply_final_judge_guardrails("Toy evidence blocked. Toy evidence is limited.", state)

    assert "Output Policy Guardrail Report" in blocked
    assert "defect_memo_required_on_block" in blocked
    assert "Guardrail Report" not in allowed
    assert "Guardrail Report" not in declared_marker_allowed


def toy_output_plan(
    *,
    citation_required: bool = False,
    allow_caveated_claim_without_evidence: bool = True,
    raw_data_allowed_in_final: bool = False,
    raw_data_markers: list[str] | None = None,
    writer_can_create_facts: bool = False,
) -> dict:
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
                    "targets": [{"target": "decision:toy_accept"}],
                    "stop_signal_policy": {
                        "action_markers": [
                            {
                                "action": "writer:publish_report",
                                "phrases": ["ship toy report"],
                            }
                        ],
                        "rules": [
                            {
                                "id": "toy_gate_blocks_publication",
                                "trigger_targets": ["decision:toy_accept"],
                                "blocked_actions": ["writer:publish_report", "final_judge:publish_report"],
                            }
                        ]
                    },
                    "output_policy": {
                        "blocked_phrases": ["unsupported toy claim"],
                        "required_caveats": ["Toy evidence is limited."],
                        "defect_memo_markers": ["Toy evidence blocked"],
                        "defect_memo_on_block": True,
                        "writer_can_create_facts": writer_can_create_facts,
                        "final_judge_required_checks": ["committed_candidate", "required_caveats"],
                    },
                    "evidence_policy": {
                        "claim_types": ["toy_claim"],
                        "evidence_node_types": ["toy_evidence"],
                        "required_evidence_for_final_claims": ["toy_evidence"],
                        "allow_caveated_claim_without_evidence": allow_caveated_claim_without_evidence,
                        "citation_required": citation_required,
                        "raw_data_allowed_in_final": raw_data_allowed_in_final,
                        "raw_data_markers": raw_data_markers or [],
                        "unsupported_claim_action": "block",
                    },
                },
            }
        ],
    )
    assert plan["output_policy"]["blocked_phrases"] == ["unsupported toy claim"]
    assert plan["evidence_policy"]["raw_data_allowed_in_final"] is raw_data_allowed_in_final
    assert plan["stop_signal_policy"]["action_markers"][0]["action"] == "writer:publish_report"
    return plan


def investment_output_state() -> dict:
    state = investment_plan_state()
    state["quorum_trace"] = {"committed_candidate": {"id": "candidate:investment:insufficient_data", "label": "Insufficient Data"}}
    return state


def investment_plan_state() -> dict:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    plan = build_goal_routed_swarm_plan(
        task="Analyze AAPL as an investment",
        intent="investment_analysis",
        required_capability_types=["investment.research"],
        agents=[],
        capabilities=[manifest.to_public_dict()],
    )
    return {
        "metadata": {"os_plan": {"swarm_plan": plan}},
    }
