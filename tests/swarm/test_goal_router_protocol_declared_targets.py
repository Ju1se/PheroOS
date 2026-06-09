from __future__ import annotations

from runtime.swarm.goal_router import build_goal_routed_swarm_plan
from runtime.swarm.legacy_goal_targets import LEGACY_DEFAULT_TARGETS_BY_INTENT
from runtime.swarm.stop_policy import action_blocked_by_stop_policy
from runtime.agent_registry import AgentRegistry
from runtime.capability_registry import CapabilityRegistry


def test_goal_router_uses_capability_declared_targets() -> None:
    plan = build_goal_routed_swarm_plan(
        task="Run a toy review",
        intent="toy_review",
        required_capability_types=["toy.review"],
        agents=[
            {
                "key": "toy_evidence_agent",
                "name": "Toy Evidence Agent",
                "agent_type": "toy_review_member",
                "committee_role": "toy_evidence",
                "focus": ["toy", "evidence", "accept"],
                "tags": ["toy", "evidence"],
                "default_enabled": True,
            }
        ],
        capabilities=[
            {
                "id": "toy-review",
                "trust_level": "first_party_reviewed",
                "protocol": {
                    "intents": ["toy_review"],
                    "targets": [
                        {
                            "target": "decision:toy_accept",
                            "default_pressure": 0.86,
                            "keywords": ["toy", "accept"],
                            "description": "Decide whether the toy review is accepted.",
                        },
                        {
                            "target": "gate:toy_evidence_gate",
                            "default_pressure": 0.92,
                            "keywords": ["toy", "evidence"],
                            "description": "Gate toy evidence before acceptance.",
                        },
                    ],
                    "candidates": [
                        {"candidate": "candidate:toy:accept", "target": "decision:toy_accept"},
                        {"candidate": "candidate:toy:reject", "target": "decision:toy_accept"},
                        {
                            "candidate": "candidate:toy:insufficient_evidence",
                            "target": "decision:toy_accept",
                            "safe_fallback": True,
                        },
                    ],
                    "quorum_policy": {
                        "candidates": [
                            "candidate:toy:accept",
                            "candidate:toy:reject",
                            "candidate:toy:insufficient_evidence",
                        ],
                        "candidate_fallback": "candidate:toy:insufficient_evidence",
                    },
                },
            }
        ],
    )

    targets = {signal["canonical_target"] for signal in plan["target_signals"]}

    assert targets == {"decision:toy_accept", "gate:toy_evidence_gate"}
    assert plan["protocol_source"] == "capability_manifest"
    assert plan["legacy_goal_router_fallback"] is False
    assert plan["needs_capability"] is False
    assert plan["candidate_policy"]["candidates"][0]["id"] == "candidate:toy:accept"
    assert "toy_evidence_agent" in plan["activated_agents"]


def test_goal_router_does_not_require_legacy_default_targets_for_new_capability() -> None:
    assert "toy_review" not in LEGACY_DEFAULT_TARGETS_BY_INTENT

    plan = build_goal_routed_swarm_plan(
        task="Run a toy review",
        intent="toy_review",
        required_capability_types=["toy.review"],
        agents=[],
        capabilities=[
            {
                "id": "toy-review",
                "protocol": {
                    "intents": ["toy_review"],
                    "targets": [{"target": "decision:toy_accept"}],
                },
            }
        ],
    )

    assert [signal["canonical_target"] for signal in plan["target_signals"]] == ["decision:toy_accept"]
    assert plan["legacy_goal_router_fallback"] is False


def test_goal_router_filters_protocol_targets_by_compatible_intents() -> None:
    plan = build_goal_routed_swarm_plan(
        task="Review portfolio allocation",
        intent="portfolio_review",
        required_capability_types=["portfolio.review"],
        agents=[],
        capabilities=[
            {
                "id": "multi-intent-review",
                "protocol": {
                    "intents": ["investment_analysis", "portfolio_review"],
                    "targets": [
                        {
                            "target": "decision:formal_valuation",
                            "compatible_intents": ["investment_analysis"],
                        },
                        {
                            "target": "decision:portfolio_review",
                            "compatible_intents": ["portfolio_review"],
                        },
                    ],
                },
            }
        ],
    )

    assert [signal["canonical_target"] for signal in plan["target_signals"]] == ["decision:portfolio_review"]
    assert plan["legacy_goal_router_fallback"] is False


def test_goal_router_uses_protocol_agent_selection_policy_roles() -> None:
    plan = build_goal_routed_swarm_plan(
        task="Run a new review",
        intent="novel_review",
        required_capability_types=["novel.review"],
        agents=[
            {
                "key": "policy_selected_agent",
                "name": "Policy Selected",
                "agent_type": "unmapped_member",
                "committee_role": "novel_specialist",
                "tags": [],
                "default_enabled": True,
            },
            {
                "key": "generic_agent",
                "name": "Generic",
                "agent_type": "unmapped_member",
                "committee_role": "generalist",
                "tags": [],
                "default_enabled": True,
            },
            {
                "key": "legacy_preferred_agent",
                "name": "Legacy Preferred",
                "agent_type": "evidence_research_member",
                "committee_role": "legacy_research",
                "tags": [],
                "default_enabled": True,
            },
        ],
        capabilities=[
            {
                "id": "novel-review",
                "protocol": {
                    "intents": ["novel_review"],
                    "targets": [{"target": "gate:novel_quality", "keywords": ["nomatch"]}],
                    "agent_selection_policy": {"required_roles": ["novel_specialist"]},
                },
            }
        ],
    )

    by_agent = {item["agent"]: item for item in plan["agent_allocation"]}

    assert plan["legacy_goal_router_fallback"] is False
    assert plan["activated_agents"] == ["policy_selected_agent"]
    assert by_agent["policy_selected_agent"]["matched_targets"][0]["matched_keywords"] == []
    assert "protocol selection policy" in by_agent["policy_selected_agent"]["activation_reason"]
    assert by_agent["generic_agent"]["activated"] is False
    assert by_agent["legacy_preferred_agent"]["activated"] is False


def test_builtin_evidence_research_uses_declared_agent_selection_policy() -> None:
    manifest = CapabilityRegistry().get("evidence-research")
    assert manifest is not None
    agents = AgentRegistry().catalog(enabled_capability_ids={"evidence-research"})["agents"]
    agents.append(
        {
            "key": "legacy_only_agent",
            "name": "Legacy Only",
            "agent_type": "evidence_research_member",
            "committee_role": "legacy_only",
            "tags": [],
            "default_enabled": True,
        }
    )

    plan = build_goal_routed_swarm_plan(
        task="Verify source quality for this claim",
        intent="evidence_research",
        required_capability_types=["evidence.research"],
        agents=agents,
        capabilities=[manifest.to_public_dict()],
    )
    allocation = {item["agent"]: item for item in plan["agent_allocation"]}

    assert plan["agent_selection_policy"]["required_roles"] == [
        "claim_decomposer",
        "source_retriever",
        "source_quality_rater",
        "evidence_steward",
    ]
    assert "source_retrieval_agent" in plan["activated_agents"]
    assert "legacy_only_agent" not in plan["activated_agents"]
    assert allocation["legacy_only_agent"]["activated"] is False


def test_legacy_goal_router_allocation_does_not_use_intent_agent_type_map() -> None:
    plan = build_goal_routed_swarm_plan(
        task="Fix the failing tests",
        intent="code_development",
        required_capability_types=["code_development"],
        agents=[
            {
                "key": "type_only_agent",
                "name": "Type Only",
                "agent_type": "code_development_member",
                "committee_role": "generalist",
                "tags": [],
                "focus": [],
                "default_enabled": True,
            },
            {
                "key": "target_matched_agent",
                "name": "Target Matched",
                "agent_type": "unmapped_member",
                "committee_role": "quality",
                "tags": ["tests"],
                "focus": ["pytest regression tests"],
                "default_enabled": True,
            },
        ],
        capabilities=[],
    )
    allocation = {item["agent"]: item for item in plan["agent_allocation"]}

    assert plan["legacy_goal_router_fallback"] is True
    assert "target_matched_agent" in plan["activated_agents"]
    assert "type_only_agent" not in plan["activated_agents"]
    assert "task intent" not in allocation["type_only_agent"]["activation_reason"]


def test_builtin_web_research_uses_explicit_protocol_not_legacy_swarm() -> None:
    manifest = CapabilityRegistry().get("web-research")
    assert manifest is not None

    plan = build_goal_routed_swarm_plan(
        task="Research the latest release notes and cite the sources",
        intent="web_research",
        required_capability_types=["public_web_research", "skill:web-research"],
        agents=[],
        capabilities=[manifest.to_public_dict()],
    )
    web_protocol = next(
        item for item in plan["capability_protocols"] if item["capability_id"] == "web-research"
    )

    assert plan["protocol_source"] == "capability_manifest"
    assert plan["legacy_goal_router_fallback"] is False
    assert plan["generated_legacy_protocol_count"] == 0
    assert web_protocol["source"] == "capability_protocol"
    assert web_protocol["generated_legacy_protocol"] is False
    assert plan["evidence_policy"]["citation_required"] is True
    assert plan["tool_policy"]["allowed_tool_targets"] == [
        "tool:web_search",
        "tool:fetch_url",
        "tool:approved_source_fetch",
        "tool:provider_web_search",
    ]
    assert {signal["canonical_target"] for signal in plan["target_signals"]} == {
        "research:source_retrieval",
        "metric:research_source_quality",
        "gate:research_evidence_gate",
    }


def test_builtin_core_workflows_use_explicit_protocol_targets_without_fallback() -> None:
    registry = CapabilityRegistry()

    for capability_id, intent, required_types in [
        ("code-development", "code_development", ["code_development", "skill:code-development"]),
        ("compliance-workflow", "compliance_workflow", ["compliance.workflow", "skill:compliance-workflow"]),
        ("evidence-research", "evidence_research", ["evidence.research", "skill:evidence-research"]),
    ]:
        manifest = registry.get(capability_id)
        assert manifest is not None

        plan = build_goal_routed_swarm_plan(
            task=f"Run {intent}",
            intent=intent,
            required_capability_types=required_types,
            agents=[],
            capabilities=[manifest.to_public_dict()],
        )
        protocol = next(item for item in plan["capability_protocols"] if item["capability_id"] == capability_id)

        assert plan["legacy_goal_router_fallback"] is False
        assert plan["generated_legacy_protocol_count"] == 0
        assert protocol["source"] == "capability_protocol"
        assert protocol["generated_legacy_protocol"] is False
        assert plan["target_signals"]


def test_goal_router_marks_legacy_fallback_when_protocol_missing() -> None:
    plan = build_goal_routed_swarm_plan(
        task="Verify source quality for this claim",
        intent="evidence_research",
        required_capability_types=["evidence.research"],
        agents=[],
        capabilities=[],
    )

    assert plan["legacy_goal_router_fallback"] is True
    assert plan["protocol_source"] == "intent_default"
    assert any(
        item["event_type"] == "legacy_goal_router_fallback"
        and item["fallback_type"] == "legacy_default_targets_by_intent"
        for item in plan["routing_trace"]
    )
    assert {signal["canonical_target"] for signal in plan["target_signals"]} >= {
        "research:claim_decomposition",
        "gate:research_evidence_gate",
    }


def test_legacy_goal_router_fallback_does_not_emit_investment_candidate_targets() -> None:
    plan = build_goal_routed_swarm_plan(
        task="Analyze AAPL as an investment",
        intent="investment_analysis",
        required_capability_types=["investment.research"],
        agents=[],
        capabilities=[],
    )

    targets = {signal["canonical_target"] for signal in plan["target_signals"]}

    assert plan["legacy_goal_router_fallback"] is True
    assert targets == {"decision:formal_valuation"}
    assert not any(target.startswith("candidate:investment:") for target in targets)


def test_explicit_protocol_without_targets_does_not_use_legacy_defaults() -> None:
    plan = build_goal_routed_swarm_plan(
        task="Verify source quality for this claim",
        intent="evidence_research",
        required_capability_types=["evidence.research"],
        agents=[],
        capabilities=[
            {
                "id": "targetless-evidence",
                "trust_level": "first_party_reviewed",
                "protocol": {
                    "intents": ["evidence_research"],
                    "candidates": [{"candidate": "candidate:targetless:defer"}],
                },
            }
        ],
    )

    assert plan["target_signals"] == []
    assert plan["needs_capability"] is True
    assert plan["legacy_goal_router_fallback"] is False
    assert plan["routing_trace"] == [
        {
            "event_type": "goal_router.protocol_targets_missing",
            "intent": "evidence_research",
            "reason": "explicit capability protocol was present but declared no goal targets",
            "required_capability_types": ["evidence.research"],
        }
    ]


def test_goal_router_no_longer_uses_swarm_research_keyword_special_case() -> None:
    plan = build_goal_routed_swarm_plan(
        task="Research ant swarm pheromone decision making",
        intent="evidence_research",
        required_capability_types=["evidence.research"],
        agents=[],
        capabilities=[],
    )

    assert plan["legacy_goal_router_fallback"] is True
    assert {
        item.get("fallback_type")
        for item in plan["routing_trace"]
        if item.get("event_type") == "legacy_goal_router_fallback"
    } == {"legacy_default_targets_by_intent"}


def test_goal_router_does_not_supplement_public_web_targets_without_protocol() -> None:
    plan = build_goal_routed_swarm_plan(
        task="Research release notes",
        intent="unknown_public_web_task",
        required_capability_types=["public_web_research"],
        agents=[],
        capabilities=[],
    )

    assert plan["target_signals"] == []
    assert plan["needs_capability"] is True
    assert plan["legacy_goal_router_fallback"] is False
    assert not any(
        item.get("fallback_type") == "public_web_research_supplement"
        for item in plan["routing_trace"]
    )


def test_target_aliases_canonicalize_before_stop_signal() -> None:
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
                    "targets": [
                        {
                            "target": "gate:toy_evidence_gate",
                            "aliases": ["toy evidence gate"],
                        }
                    ],
                    "stop_signal_policy": {
                        "rules": [
                            {
                                "id": "toy_gate_blocks_publish",
                                "trigger_targets": ["toy evidence gate"],
                                "blocked_actions": ["writer:publish_toy_review"],
                            }
                        ]
                    },
                },
            }
        ],
    )
    state = {
        "metadata": {"os_plan": {"swarm_plan": plan}},
        "stop_signals": [
            {
                "id": "sig-toy-gate",
                "type": "stop_signal",
                "target": "toy evidence gate",
                "blocking": True,
                "verification_state": "blocking",
                "content": "Toy evidence gate remains blocked.",
            }
        ],
    }

    blocker = action_blocked_by_stop_policy(state, "writer:publish_toy_review")

    assert blocker is not None
    assert blocker["id"] == "sig-toy-gate"


def test_unknown_intent_requests_capability_not_random_defaults() -> None:
    plan = build_goal_routed_swarm_plan(
        task="Run a new domain-specific workflow",
        intent="unknown_domain_workflow",
        required_capability_types=["unknown.domain"],
        agents=[],
        capabilities=[],
    )

    assert plan["target_signals"] == []
    assert plan["target_count"] == 0
    assert plan["legacy_goal_router_fallback"] is False
    assert plan["needs_capability"] is True
    assert plan["routing_trace"] == [
        {
            "event_type": "goal_router.needs_capability",
            "intent": "unknown_domain_workflow",
            "reason": "no capability-declared protocol targets and no legacy default targets",
            "required_capability_types": ["unknown.domain"],
        }
    ]
