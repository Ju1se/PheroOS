from __future__ import annotations

from runtime.swarm.goal_router import build_goal_routed_swarm_plan
from runtime.swarm.quorum import build_quorum_trace
from runtime.swarm.resolution import apply_stop_signal_resolution
from runtime.swarm.stop_policy import action_blocked_by_stop_policy, stop_signal_policy_from_state
from runtime.swarm.stop_signal import tool_blocked_by_signal


def test_stop_signal_policy_loaded_from_capability() -> None:
    plan = toy_review_plan()

    assert plan["stop_signal_policy"]["rules"][0]["id"] == "toy_gate_blocks_publish"

    blocked = action_blocked_by_stop_policy(
        {
            "metadata": {"os_plan": {"swarm_plan": plan}},
            "stop_signals": [
                {
                    "target": "gate:toy_evidence_gate",
                    "blocking": True,
                    "verification_state": "blocking",
                }
            ],
        },
        "tool:toy_publish",
    )

    assert blocked is not None
    assert blocked["target"] == "gate:toy_evidence_gate"


def test_untrusted_hard_blocking_stop_policy_is_diagnosed_but_not_enforced() -> None:
    plan = hard_blocking_external_publish_plan(
        capability_id="third-party-hard-block",
        trust_level="third_party",
    )
    state = external_gate_state(plan)

    assert "untrusted_blocking_authority" in {item["code"] for item in plan["validation_diagnostics"]}
    assert plan["stop_signal_policy"]["rules"][0]["capability_id"] == "third-party-hard-block"

    policy = stop_signal_policy_from_state(state)
    blocked = action_blocked_by_stop_policy(state, "writer:publish_external")

    assert policy["policy_sanitized"] is True
    assert policy["blocked_policy_sources"] == ["third-party-hard-block"]
    assert policy["rules"] == []
    assert blocked is None


def test_trusted_hard_blocking_stop_policy_still_blocks_declared_actions() -> None:
    plan = hard_blocking_external_publish_plan(
        capability_id="first-party-hard-block",
        trust_level="first_party_reviewed",
    )
    state = external_gate_state(plan)

    assert plan["validation_diagnostics"] == []

    policy = stop_signal_policy_from_state(state)
    blocked = action_blocked_by_stop_policy(state, "writer:publish_external")

    assert "policy_sanitized" not in policy
    assert blocked is not None
    assert blocked["target"] == "gate:external_gate"


def test_untrusted_top_level_stop_policy_is_filtered_in_mixed_policy() -> None:
    plan = build_goal_routed_swarm_plan(
        task="Publish external and safe actions",
        intent="mixed_publish_review",
        required_capability_types=["mixed.publish"],
        agents=[],
        capabilities=[
            top_level_blocking_capability(
                capability_id="third-party-top-level-block",
                trust_level="third_party",
                target="gate:unsafe_gate",
                action="writer:publish_external",
            ),
            top_level_blocking_capability(
                capability_id="first-party-top-level-block",
                trust_level="first_party_reviewed",
                target="gate:safe_gate",
                action="writer:publish_safe",
            ),
        ],
    )
    state = {
        "metadata": {"os_plan": {"swarm_plan": plan}},
        "stop_signals": [
            {"target": "gate:unsafe_gate", "blocking": True, "verification_state": "blocking"},
            {"target": "gate:safe_gate", "blocking": True, "verification_state": "blocking"},
        ],
    }

    policy = stop_signal_policy_from_state(state)
    unsafe_block = action_blocked_by_stop_policy(state, "writer:publish_external")
    safe_block = action_blocked_by_stop_policy(state, "writer:publish_safe")

    assert "untrusted_blocking_authority" in {item["code"] for item in plan["validation_diagnostics"]}
    assert policy["blocked_actions"] == []
    assert [rule["blocked_actions"] for rule in policy["rules"]] == [["writer:publish_safe"]]
    assert unsafe_block is None
    assert safe_block is not None
    assert safe_block["target"] == "gate:safe_gate"


def test_web_search_block_in_investment_comes_from_protocol_or_global_source_policy() -> None:
    blocked = tool_blocked_by_signal(
        {"metadata": {"source_mode": "WRDS_ONLY"}},
        "provider_web_search",
    )

    assert blocked is not None
    assert blocked["source_module"] == "source_policy"
    assert blocked["target"] == "constraint:data_source_policy"
    assert "WRDS_ONLY" in blocked["content"]


def test_web_search_block_does_not_infer_from_investment_task_type() -> None:
    blocked = tool_blocked_by_signal(
        {"orchestration": {"task_type": "investment", "committee": True}},
        "provider_web_search",
    )

    assert blocked is None


def test_web_search_block_can_use_capability_tool_policy_source_mode() -> None:
    blocked = tool_blocked_by_signal(
        {
            "metadata": {
                "os_plan": {
                    "swarm_plan": {
                        "tool_policy": {"source_mode": "WRDS_ONLY"},
                    }
                }
            }
        },
        "provider_web_search",
    )

    assert blocked is not None
    assert blocked["source_module"] == "source_policy"


def test_web_search_block_uses_declared_source_policy_message() -> None:
    blocked = tool_blocked_by_signal(
        {
            "metadata": {
                "os_plan": {
                    "swarm_plan": {
                        "tool_policy": {
                            "source_mode": "WRDS_ONLY",
                            "source_policy_block_message": "{action} blocked by declared {source_mode} mode.",
                        },
                    }
                }
            }
        },
        "provider_web_search",
    )

    assert blocked is not None
    assert blocked["content"] == "tool:provider_web_search blocked by declared WRDS_ONLY mode."


def test_web_tool_resolution_uses_capability_tool_policy_source_mode() -> None:
    resolution = apply_stop_signal_resolution(
        {
            "metadata": {
                "os_plan": {
                    "swarm_plan": {
                        "tool_policy": {"source_mode": "WRDS_ONLY"},
                    }
                }
            },
            "stop_signals": [
                {
                    "id": "sig-web",
                    "target": "tool:web_search",
                    "blocking": True,
                    "lifecycle_state": "blocking",
                }
            ],
        }
    )

    assert resolution["signal_resolution_report"]["status"] == "open_blockers"
    assert resolution["stop_signals"][0]["blocking"] is True


def test_new_capability_blocks_declared_tool_without_editing_stop_signal_py() -> None:
    plan = toy_review_plan()
    blocked = tool_blocked_by_signal(
        {
            "metadata": {"os_plan": {"swarm_plan": plan}},
            "stop_signals": [
                {
                    "target": "gate:toy_evidence_gate",
                    "blocking": True,
                    "verification_state": "blocking",
                }
            ],
        },
        "toy_publish",
    )

    assert blocked is not None
    assert blocked["target"] == "gate:toy_evidence_gate"


def test_global_security_cannot_be_weakened_by_capability() -> None:
    blocked = tool_blocked_by_signal(
        {
            "metadata": {
                "source_mode": "WRDS_ONLY",
                "os_plan": {
                    "swarm_plan": {
                        "stop_signal_policy": {
                            "allowed_actions": ["tool:provider_web_search"],
                            "rules": [],
                        }
                    }
                },
            }
        },
        "provider_web_search",
    )

    assert blocked is not None
    assert blocked["source_module"] == "source_policy"


def test_blocking_signal_resolves_only_with_declared_authority() -> None:
    state = toy_resolution_state(resolution_authority="wrong_agent")
    unresolved = apply_stop_signal_resolution(state)

    assert unresolved["signal_resolution_report"]["status"] == "open_blockers"
    assert unresolved["stop_signals"][0]["blocking"] is True

    resolved = apply_stop_signal_resolution(toy_resolution_state(resolution_authority="toy_recovery_agent"))

    assert resolved["signal_resolution_report"]["status"] == "resolved_some"
    assert resolved["stop_signals"][0]["lifecycle_state"] == "resolved"
    assert resolved["signal_resolution_report"]["resolved"][0]["reason"] == "Toy evidence gate passed."


def test_declared_resolution_policy_prevents_data_gate_auto_clear_without_authority() -> None:
    state = declared_resolution_state(
        target="decision:toy_publish",
        resolution_authority="wrong_agent",
        data_gate={"conclusion_permissions": {"toy_publish_allowed": True}},
    )
    unresolved = apply_stop_signal_resolution(state)

    assert unresolved["signal_resolution_report"]["status"] == "open_blockers"
    assert unresolved["stop_signals"][0]["blocking"] is True

    resolved = apply_stop_signal_resolution(
        declared_resolution_state(
            target="decision:toy_publish",
            resolution_authority="toy_recovery_agent",
            data_gate={"conclusion_permissions": {"toy_publish_allowed": True}},
        )
    )

    assert resolved["signal_resolution_report"]["status"] == "resolved_some"
    assert resolved["stop_signals"][0]["lifecycle_state"] == "resolved"
    assert resolved["signal_resolution_report"]["resolved"][0]["reason"] == "Declared toy recovery cleared the blocker."


def test_declared_resolution_policy_prevents_web_tool_auto_clear_without_authority() -> None:
    state = declared_resolution_state(
        target="tool:web_search",
        resolution_authority="wrong_agent",
        metadata={"source_mode": "PUBLIC_WEB"},
    )
    unresolved = apply_stop_signal_resolution(state)

    assert unresolved["signal_resolution_report"]["status"] == "open_blockers"
    assert unresolved["stop_signals"][0]["blocking"] is True

    resolved = apply_stop_signal_resolution(
        declared_resolution_state(
            target="tool:web_search",
            resolution_authority="toy_recovery_agent",
            metadata={"source_mode": "PUBLIC_WEB"},
        )
    )

    assert resolved["signal_resolution_report"]["status"] == "resolved_some"
    assert resolved["stop_signals"][0]["lifecycle_state"] == "resolved"
    assert resolved["signal_resolution_report"]["resolved"][0]["reason"] == "Declared toy recovery cleared the blocker."


def test_source_policy_resolution_supports_declared_blocked_tool_targets() -> None:
    unresolved = apply_stop_signal_resolution(
        {
            "metadata": {
                "os_plan": {
                    "swarm_plan": {
                        "tool_policy": {
                            "source_mode": "WRDS_ONLY",
                            "source_policy_blocked_tool_targets": ["tool:custom_news_api"],
                        }
                    }
                }
            },
            "stop_signals": [
                {
                    "id": "sig-custom-source-policy",
                    "target": "tool:custom_news_api",
                    "blocking": True,
                    "verification_state": "blocking",
                    "metadata": {"source_policy_blocked_tool_targets": ["tool:custom_news_api"]},
                }
            ],
        }
    )
    resolved = apply_stop_signal_resolution(
        {
            "metadata": {"source_mode": "PUBLIC_WEB"},
            "stop_signals": [
                {
                    "id": "sig-custom-source-policy",
                    "target": "tool:custom_news_api",
                    "blocking": True,
                    "verification_state": "blocking",
                    "metadata": {"source_policy_blocked_tool_targets": ["tool:custom_news_api"]},
                }
            ],
        }
    )

    assert unresolved["signal_resolution_report"]["status"] == "open_blockers"
    assert resolved["signal_resolution_report"]["status"] == "resolved_some"
    assert resolved["stop_signals"][0]["lifecycle_state"] == "resolved"


def test_resolved_stop_signal_reopens_candidate() -> None:
    state = toy_resolution_state(resolution_authority="toy_recovery_agent")
    blocked_quorum = build_quorum_trace(state)
    resolution = apply_stop_signal_resolution(state)
    reopened_quorum = build_quorum_trace({**state, **resolution})

    assert blocked_quorum["committed_candidate"]["label"] == "Escalate"
    assert reopened_quorum["committed_candidate"]["label"] == "Approve"
    assert reopened_quorum["blocking_stop_signal_count"] == 0


def toy_review_plan() -> dict:
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
                    "candidates": [
                        {
                            "candidate": "candidate:toy:approve",
                            "label": "Approve",
                            "target": "decision:toy_accept",
                            "blocked_by_targets": ["gate:toy_evidence_gate"],
                        },
                        {"candidate": "candidate:toy:reject", "label": "Reject", "target": "decision:toy_accept"},
                        {"candidate": "candidate:toy:escalate", "label": "Escalate", "target": "decision:toy_accept"},
                    ],
                    "quorum_policy": {
                        "candidate_fallback": "candidate:toy:escalate",
                        "candidates": [
                            "candidate:toy:approve",
                            "candidate:toy:reject",
                            "candidate:toy:escalate",
                        ],
                    },
                    "stop_signal_policy": {
                        "rules": [
                            {
                                "id": "toy_gate_blocks_publish",
                                "trigger_targets": ["gate:toy_evidence_gate"],
                                "blocked_actions": ["tool:toy_publish"],
                            }
                        ],
                        "resolution_policy": {
                            "rules": [
                                {
                                    "targets": ["gate:toy_evidence_gate"],
                                    "resolution_authority": ["toy_recovery_agent"],
                                    "resolution_condition": {
                                        "path": "toy_review.evidence_gate_passed",
                                        "equals": True,
                                    },
                                    "reason": "Toy evidence gate passed.",
                                }
                            ]
                        },
                    },
                },
            }
        ],
    )


def hard_blocking_external_publish_plan(*, capability_id: str, trust_level: str) -> dict:
    return build_goal_routed_swarm_plan(
        task="Publish an external action",
        intent="external_publish_review",
        required_capability_types=["external.publish"],
        agents=[],
        capabilities=[
            {
                "id": capability_id,
                "trust_level": trust_level,
                "protocol": {
                    "intents": ["external_publish_review"],
                    "targets": [
                        {"target": "gate:external_gate"},
                        {"target": "decision:external_publish"},
                    ],
                    "stop_signal_policy": {
                        "blocking_authority_required": 3,
                        "rules": [
                            {
                                "id": "external_gate_blocks_publish",
                                "trigger_targets": ["gate:external_gate"],
                                "blocked_actions": ["writer:publish_external"],
                            }
                        ],
                    },
                },
            }
        ],
    )


def top_level_blocking_capability(
    *,
    capability_id: str,
    trust_level: str,
    target: str,
    action: str,
) -> dict:
    return {
        "id": capability_id,
        "trust_level": trust_level,
        "protocol": {
            "intents": ["mixed_publish_review"],
            "targets": [{"target": target}],
            "stop_signal_policy": {
                "blocking_authority_required": 3,
                "trigger_targets": [target],
                "blocked_actions": [action],
            },
        },
    }


def external_gate_state(plan: dict) -> dict:
    return {
        "metadata": {"os_plan": {"swarm_plan": plan}},
        "stop_signals": [
            {
                "target": "gate:external_gate",
                "blocking": True,
                "verification_state": "blocking",
                "content": "External publication gate is closed.",
            }
        ],
    }


def toy_resolution_state(*, resolution_authority: str) -> dict:
    return {
        "committee_decision": {"decision": "Approve"},
        "toy_review": {"evidence_gate_passed": True},
        "metadata": {
            "resolution_authority": resolution_authority,
            "os_plan": {"swarm_plan": toy_review_plan()},
        },
        "stop_signals": [
            {
                "id": "sig-toy-evidence",
                "target": "gate:toy_evidence_gate",
                "blocking": True,
                "verification_state": "blocking",
                "content": "Toy evidence gate is still closed.",
            }
        ],
    }


def declared_resolution_state(
    *,
    target: str,
    resolution_authority: str,
    data_gate: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    base_metadata = dict(metadata or {})
    base_metadata["resolution_authority"] = resolution_authority
    base_metadata["os_plan"] = {
        "swarm_plan": {
            "stop_signal_policy": {
                "resolution_policy": {
                    "rules": [
                        {
                            "targets": [target],
                            "resolution_authority": ["toy_recovery_agent"],
                            "resolution_condition": {
                                "path": "toy_review.recovered",
                                "equals": True,
                            },
                            "reason": "Declared toy recovery cleared the blocker.",
                        }
                    ]
                }
            }
        }
    }
    return {
        "toy_review": {"recovered": True},
        "metadata": base_metadata,
        "data_gate": data_gate or {},
        "stop_signals": [
            {
                "id": "sig-declared-resolution",
                "target": target,
                "blocking": True,
                "verification_state": "blocking",
                "content": "Declared resolution policy has not cleared this blocker.",
            }
        ],
    }
