from __future__ import annotations

from runtime.capability_registry import CapabilityRegistry
from runtime.swarm.goal_router import build_goal_routed_swarm_plan
from runtime.swarm.protocol_loader import load_protocol_from_capability
from runtime.swarm.quorum import build_quorum_trace


def test_quorum_uses_declared_candidates() -> None:
    quorum = build_quorum_trace(
        {
            "committee_decision": {"decision": "Approve"},
            "metadata": {
                "os_plan": {
                    "swarm_plan": {
                        "candidate_policy": {
                            "candidate_type": "toy_decision",
                            "candidates": [
                                {"id": "candidate:toy:approve", "label": "Approve"},
                                {"id": "candidate:toy:reject", "label": "Reject"},
                                {"id": "candidate:toy:escalate", "label": "Escalate"},
                            ],
                        }
                    }
                }
            },
        }
    )

    assert [candidate["label"] for candidate in quorum["candidates"]] == ["Approve", "Reject", "Escalate"]
    assert quorum["committed_candidate"]["label"] == "Approve"
    assert quorum["candidate_source"] == "capability_protocol"
    assert quorum["generated_legacy_candidate_fallback"] is False
    assert "Buy" not in {candidate["label"] for candidate in quorum["candidates"]}


def test_quorum_prefers_generic_agent_decision_over_legacy_committee_decision() -> None:
    quorum = build_quorum_trace(
        {
            "agent_decision": {"decision": "Approve"},
            "committee_decision": {"decision": "Reject"},
            "metadata": {
                "os_plan": {
                    "swarm_plan": {
                        "candidate_policy": {
                            "candidate_type": "toy_decision",
                            "candidates": [
                                {"id": "candidate:toy:approve", "label": "Approve"},
                                {"id": "candidate:toy:reject", "label": "Reject"},
                            ],
                        }
                    }
                }
            },
        }
    )

    assert quorum["committed_candidate"]["label"] == "Approve"
    assert quorum["decision_source"] == "agent_decision"


def test_quorum_toy_capability_accept_reject_insufficient_evidence() -> None:
    plan = toy_review_plan(
        candidates=[
            {
                "candidate": "candidate:toy:accept",
                "target": "decision:toy_accept",
                "blocked_by_targets": ["gate:toy_evidence_gate"],
            },
            {"candidate": "candidate:toy:reject", "target": "decision:toy_accept"},
            {
                "candidate": "candidate:toy:insufficient_evidence",
                "target": "decision:toy_accept",
                "safe_fallback": True,
            },
        ],
        quorum_policy={
            "candidate_fallback": "candidate:toy:insufficient_evidence",
            "candidates": [
                "candidate:toy:accept",
                "candidate:toy:reject",
                "candidate:toy:insufficient_evidence",
            ],
        },
    )

    accepted = build_quorum_trace(
        {
            "committee_decision": {"decision": "accept"},
            "metadata": {"os_plan": {"swarm_plan": plan}},
        }
    )
    blocked = build_quorum_trace(
        {
            "committee_decision": {"decision": "accept"},
            "metadata": {"os_plan": {"swarm_plan": plan}},
            "stop_signals": [
                {
                    "target": "gate:toy_evidence_gate",
                    "blocking": True,
                    "verification_state": "blocking",
                }
            ],
        }
    )

    assert accepted["committed_candidate"]["label"] == "Accept"
    assert blocked["committed_candidate"]["label"] == "Insufficient Evidence"
    assert next(candidate for candidate in blocked["candidates"] if candidate["label"] == "Accept")["blocked"] is True
    assert blocked["candidate_source"] == "capability_protocol"


def test_investment_protocol_still_supports_buy_watch_avoid_sell_insufficient_data() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None
    plan = build_goal_routed_swarm_plan(
        task="Analyze AAPL as an investment",
        intent="investment_analysis",
        required_capability_types=["investment.research"],
        agents=[],
        capabilities=[manifest.to_public_dict()],
    )

    quorum = build_quorum_trace(
        {
            "committee_decision": {"decision": "Sell"},
            "metadata": {"os_plan": {"intent": "investment_analysis", "swarm_plan": plan}},
        }
    )

    assert [candidate["label"] for candidate in quorum["candidates"]] == [
        "Buy",
        "Watch",
        "Avoid",
        "Sell",
        "Insufficient Data",
    ]
    assert quorum["committed_candidate"]["label"] == "Sell"
    assert quorum["candidate_source"] == "capability_protocol"
    assert quorum["generated_legacy_candidate_fallback"] is False


def test_investment_capability_uses_explicit_protocol_not_legacy_swarm() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None

    protocol = load_protocol_from_capability(manifest.to_public_dict())
    plan = build_goal_routed_swarm_plan(
        task="Analyze AAPL as an investment",
        intent="investment_analysis",
        required_capability_types=["investment.research"],
        agents=[],
        capabilities=[manifest.to_public_dict()],
    )

    assert protocol.generated_legacy_protocol is False
    assert protocol.validation_diagnostics == []
    assert plan["generated_legacy_protocol_count"] == 0
    assert plan["evidence_policy"]["raw_data_allowed_in_final"] is False
    assert plan["tool_policy"]["blocked_tool_targets"] == [
        "tool:web_search",
        "tool:provider_web_search",
        "tool:fetch_url",
        "tool:approved_source_fetch",
    ]
    assert plan["tool_policy"]["source_mode"] == "WRDS_ONLY"
    assert "WRDS-only preliminary view" in plan["output_policy"]["required_caveats"]


def test_blocking_target_forces_declared_fallback_candidate() -> None:
    plan = toy_review_plan(
        candidates=[
            {
                "candidate": "candidate:toy:approve",
                "label": "Approve",
                "target": "decision:toy_accept",
                "blocked_by_targets": ["gate:toy_evidence_gate"],
            },
            {"candidate": "candidate:toy:reject", "label": "Reject", "target": "decision:toy_accept"},
            {"candidate": "candidate:toy:escalate", "label": "Escalate", "target": "decision:toy_accept"},
        ],
        quorum_policy={
            "candidate_fallback": "candidate:toy:escalate",
            "candidates": ["candidate:toy:approve", "candidate:toy:reject", "candidate:toy:escalate"],
        },
    )

    quorum = build_quorum_trace(
        {
            "committee_decision": {"decision": "Approve"},
            "metadata": {"os_plan": {"swarm_plan": plan}},
            "stop_signals": [
                {
                    "target": "gate:toy_evidence_gate",
                    "blocking": True,
                    "verification_state": "blocking",
                }
            ],
        }
    )

    assert quorum["committed_candidate"]["label"] == "Escalate"
    assert quorum["fallback_candidate"] == {"id": "candidate:toy:escalate", "label": "Escalate"}
    assert next(candidate for candidate in quorum["candidates"] if candidate["label"] == "Approve")["blocked"] is True


def test_blocking_target_without_declared_fallback_does_not_infer_insufficient_label() -> None:
    plan = toy_review_plan(
        candidates=[
            {
                "candidate": "candidate:toy:approve",
                "label": "Approve",
                "target": "decision:toy_accept",
                "blocked_by_targets": ["gate:toy_evidence_gate"],
            },
            {
                "candidate": "candidate:toy:insufficient_evidence",
                "label": "Insufficient Evidence",
                "target": "decision:toy_accept",
            },
        ],
        quorum_policy={
            "candidates": ["candidate:toy:approve", "candidate:toy:insufficient_evidence"],
            "force_fallback_when_blocked": True,
        },
    )

    quorum = build_quorum_trace(
        {
            "committee_decision": {"decision": "Approve"},
            "metadata": {"os_plan": {"swarm_plan": plan}},
            "stop_signals": [
                {
                    "target": "gate:toy_evidence_gate",
                    "blocking": True,
                    "verification_state": "blocking",
                }
            ],
        }
    )

    approve = next(candidate for candidate in quorum["candidates"] if candidate["label"] == "Approve")
    insufficient = next(candidate for candidate in quorum["candidates"] if candidate["label"] == "Insufficient Evidence")

    assert quorum["status"] == "blocked"
    assert quorum["committed_candidate"] is None
    assert quorum["fallback_candidate"] is None
    assert approve["blocked"] is True
    assert approve["committed"] is False
    assert insufficient["committed"] is False


def test_quorum_scores_use_declared_policy_weights_and_state_inputs() -> None:
    plan = toy_review_plan(
        candidates=[
            {"candidate": "candidate:toy:approve", "label": "Approve", "target": "decision:toy_accept"},
            {"candidate": "candidate:toy:reject", "label": "Reject", "target": "decision:toy_accept"},
        ],
        quorum_policy={
            "candidates": ["candidate:toy:approve", "candidate:toy:reject"],
            "evidence_coverage_weight": 0.5,
            "source_independence_weight": 0.4,
            "unresolved_risk_penalty": 0.3,
        },
    )
    strong = build_quorum_trace(
        {
            "committee_decision": {"decision": "Approve"},
            "metadata": {"os_plan": {"swarm_plan": plan}},
            "data_gate": {"evidence_coverage": 0.9, "evidence_gaps": []},
            "independence_report": {"source_diversity": 0.9},
        }
    )
    weak = build_quorum_trace(
        {
            "committee_decision": {"decision": "Approve"},
            "metadata": {"os_plan": {"swarm_plan": plan}},
            "data_gate": {"evidence_coverage": 0.2, "evidence_gaps": [{"code": "missing"}]},
            "independence_report": {"source_diversity": 0.25},
        }
    )

    strong_approve = next(candidate for candidate in strong["candidates"] if candidate["label"] == "Approve")
    weak_approve = next(candidate for candidate in weak["candidates"] if candidate["label"] == "Approve")

    assert strong["scoring_inputs"]["weights"]["evidence_coverage_weight"] == 0.5
    assert weak["scoring_inputs"]["evidence_coverage"] == 0.2
    assert weak["scoring_inputs"]["source_independence"] == 0.25
    assert weak_approve["support_score"] < strong_approve["support_score"]
    assert weak_approve["risk_score"] > strong_approve["risk_score"]


def test_quorum_scores_prefer_generic_agent_outputs_for_source_independence() -> None:
    plan = toy_review_plan(
        candidates=[
            {"candidate": "candidate:toy:approve", "label": "Approve", "target": "decision:toy_accept"},
            {"candidate": "candidate:toy:reject", "label": "Reject", "target": "decision:toy_accept"},
        ],
        quorum_policy={
            "candidates": ["candidate:toy:approve", "candidate:toy:reject"],
            "source_independence_weight": 0.4,
        },
    )

    quorum = build_quorum_trace(
        {
            "committee_decision": {"decision": "Approve"},
            "metadata": {"os_plan": {"swarm_plan": plan}},
            "agent_outputs": {
                "toy_reviewer_a": {"evidence_used": ["same-source"]},
                "toy_reviewer_b": {"evidence_used": ["same-source"]},
            },
            "committee_outputs": {
                "legacy_reviewer_a": {"evidence_used": ["source-a"]},
                "legacy_reviewer_b": {"evidence_used": ["source-b"]},
            },
        }
    )

    assert quorum["scoring_inputs"]["source_independence"] == 0.5
    assert all(candidate["source_independence_score"] == 0.5 for candidate in quorum["candidates"])


def test_quorum_risk_prefers_generic_agent_outputs_for_hard_veto() -> None:
    plan = toy_review_plan(
        candidates=[
            {"candidate": "candidate:toy:approve", "label": "Approve", "target": "decision:toy_accept"},
            {"candidate": "candidate:toy:reject", "label": "Reject", "target": "decision:toy_accept"},
        ],
        quorum_policy={
            "candidates": ["candidate:toy:approve", "candidate:toy:reject"],
            "unresolved_risk_penalty": 0.3,
        },
    )

    quorum = build_quorum_trace(
        {
            "committee_decision": {"decision": "Approve"},
            "metadata": {"os_plan": {"swarm_plan": plan}},
            "agent_outputs": {
                "toy_reviewer": {"status": "completed", "hard_veto": False},
            },
            "committee_outputs": {
                "legacy_reviewer": {"status": "completed", "hard_veto": True},
            },
        }
    )

    assert quorum["scoring_inputs"]["unresolved_risk"] == 0.0
    assert all(candidate["unresolved_risk_score"] == 0.0 for candidate in quorum["candidates"])


def test_quorum_scores_use_candidate_specific_verified_evidence_graph_edges() -> None:
    plan = toy_review_plan(
        candidates=[
            {"candidate": "candidate:toy:approve", "label": "Approve", "target": "decision:toy_accept"},
            {"candidate": "candidate:toy:reject", "label": "Reject", "target": "decision:toy_accept"},
        ],
        quorum_policy={
            "candidates": ["candidate:toy:approve", "candidate:toy:reject"],
            "evidence_coverage_weight": 1.0,
            "source_quality_weight": 1.0,
        },
    )
    quorum = build_quorum_trace(
        {
            "committee_decision": {"decision": "Reject"},
            "metadata": {"os_plan": {"swarm_plan": plan}},
            "evidence_graph": {
                "facts": [
                    {
                        "id": "evidence:trusted_toy_source",
                        "canonical_target": "evidence:toy_review",
                        "verification_state": "verified",
                        "source": "trusted-source",
                        "source_quality_score": 0.95,
                    },
                    {
                        "id": "evidence:weak_toy_source",
                        "canonical_target": "evidence:toy_review",
                        "verification_state": "verified",
                        "source": "weak-source",
                        "source_quality_score": 0.2,
                    },
                ],
                "edges": [
                    {
                        "source": "evidence:trusted_toy_source",
                        "target": "candidate:toy:approve",
                        "relation": "supports_candidate",
                    },
                    {
                        "source": "evidence:weak_toy_source",
                        "target": "candidate:toy:reject",
                        "relation": "supports_candidate",
                    },
                ],
            },
        }
    )

    approve = next(candidate for candidate in quorum["candidates"] if candidate["label"] == "Approve")
    reject = next(candidate for candidate in quorum["candidates"] if candidate["label"] == "Reject")

    assert quorum["scoring_inputs"]["weights"]["source_quality_weight"] == 1.0
    assert approve["evidence_graph_edge_count"] == 1
    assert approve["source_quality_score"] > reject["source_quality_score"]
    assert approve["evidence_score"] > reject["evidence_score"]
    assert approve["support_score"] > reject["support_score"]


def test_quorum_scores_use_explicit_support_signals_and_agent_reliability() -> None:
    plan = toy_review_plan(
        candidates=[
            {"candidate": "candidate:toy:approve", "label": "Approve", "target": "decision:toy_accept"},
            {"candidate": "candidate:toy:reject", "label": "Reject", "target": "decision:toy_accept"},
        ],
        quorum_policy={"candidates": ["candidate:toy:approve", "candidate:toy:reject"]},
    )
    state = {
        "run_id": "run-quorum-signals",
        "committee_decision": {"decision": "Approve"},
        "metadata": {"os_plan": {"swarm_plan": plan}},
        "agent_profiles": {
            "trusted_agent": {"reliability": 0.95},
            "weak_agent": {"reliability": 0.25},
        },
        "pheromone_field_snapshot": {
            "signals": [
                {
                    "id": "sig-approve",
                    "run_id": "run-quorum-signals",
                    "type": "quorum",
                    "target": "candidate:toy:approve",
                    "content": "Approve is supported by verified toy evidence.",
                    "strength": 0.9,
                    "confidence": 0.9,
                    "verification_state": "verified",
                    "source_agent": "trusted_agent",
                },
                {
                    "id": "sig-reject",
                    "run_id": "run-quorum-signals",
                    "type": "quorum",
                    "target": "candidate:toy:reject",
                    "content": "Reject has weak support.",
                    "strength": 0.9,
                    "confidence": 0.9,
                    "verification_state": "verified",
                    "source_agent": "weak_agent",
                },
                {
                    "id": "sig-oppose",
                    "run_id": "run-quorum-signals",
                    "type": "negative",
                    "target": "candidate:toy:approve",
                    "content": "Approve has an unresolved objection.",
                    "strength": 0.3,
                    "confidence": 0.8,
                    "verification_state": "verified",
                    "source_agent": "weak_agent",
                    "metadata": {"stance": "oppose"},
                },
            ]
        },
    }

    quorum = build_quorum_trace(state)
    approve = next(candidate for candidate in quorum["candidates"] if candidate["label"] == "Approve")
    reject = next(candidate for candidate in quorum["candidates"] if candidate["label"] == "Reject")

    assert approve["support_signal_count"] == 2
    assert approve["agent_reliability_score"] > reject["agent_reliability_score"]
    assert approve["support_signal_score"] > 0
    assert approve["risk_score"] > 0.25
    assert approve["support_score"] > reject["support_score"]


def test_formal_valuation_signal_does_not_block_undeclared_candidate_targets() -> None:
    plan = toy_review_plan(
        candidates=[
            {"candidate": "candidate:toy:approve", "label": "Approve", "target": "decision:toy_accept"},
            {"candidate": "candidate:toy:escalate", "label": "Escalate", "target": "decision:toy_accept", "safe_fallback": True},
        ],
        quorum_policy={
            "candidate_fallback": "candidate:toy:escalate",
            "candidates": ["candidate:toy:approve", "candidate:toy:escalate"],
            "force_fallback_when_blocked": True,
        },
    )

    quorum = build_quorum_trace(
        {
            "committee_decision": {"decision": "Approve"},
            "metadata": {"os_plan": {"swarm_plan": plan}},
            "stop_signals": [
                {
                    "target": "decision:formal_valuation",
                    "blocking": True,
                    "verification_state": "blocking",
                }
            ],
        }
    )

    assert quorum["formal_valuation_blocked"] is True
    assert quorum["committed_candidate"]["label"] == "Approve"
    assert next(candidate for candidate in quorum["candidates"] if candidate["label"] == "Approve")["blocked"] is False


def test_investment_label_without_declared_candidates_does_not_create_candidates() -> None:
    quorum = build_quorum_trace({"committee_decision": {"decision": "Buy"}})

    assert quorum["status"] == "pending"
    assert quorum["committed_candidate"] is None
    assert quorum["candidates"] == []
    assert quorum["candidate_source"] == "missing_candidate_declaration"
    assert quorum["generated_legacy_candidate_fallback"] is False


def test_non_investment_without_declared_candidates_does_not_use_investment_defaults() -> None:
    quorum = build_quorum_trace({"committee_decision": {"decision": "Publish synthesis"}})

    assert quorum["status"] == "pending"
    assert quorum["committed_candidate"] is None
    assert quorum["candidates"] == []
    assert quorum["candidate_source"] == "missing_candidate_declaration"
    assert quorum["generated_legacy_candidate_fallback"] is False


def toy_review_plan(*, candidates: list[dict], quorum_policy: dict) -> dict:
    return build_goal_routed_swarm_plan(
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
                    "targets": [
                        {"target": "decision:toy_accept"},
                        {"target": "gate:toy_evidence_gate"},
                    ],
                    "candidates": candidates,
                    "quorum_policy": quorum_policy,
                },
            }
        ],
    )
