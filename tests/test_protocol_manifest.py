from __future__ import annotations

import json

from runtime.capability_registry import CapabilityRegistry
from runtime.swarm.protocol import capability_protocol_bundle
from runtime.swarm.legacy_protocol_intents import LEGACY_CAPABILITY_TYPE_INTENTS
from runtime.swarm.protocol_loader import load_protocol_from_capability


def test_legacy_swarm_protocol_loads_with_compatibility_marker() -> None:
    protocol = load_protocol_from_capability(
        {
            "id": "toy-review",
            "version": "0.1.0",
            "capability_types": ["toy.review"],
            "risk_level": "low",
            "trust_level": "first_party_reviewed",
            "tools": ["read_file"],
            "swarm": {
                "targets": [
                    {
                        "target": "gate:toy_evidence_gate",
                        "demand_strength": 0.91,
                        "keywords": ["toy", "evidence"],
                        "summary": "Gate toy evidence.",
                    }
                ],
                "candidate_policy": {
                    "candidate_type": "toy_decision",
                    "candidates": [
                        {"id": "candidate:toy:approve", "label": "Approve"},
                        {"id": "candidate:toy:insufficient_evidence", "label": "Insufficient evidence"},
                    ],
                },
                "quorum_policy": {"candidate_type": "toy_decision", "max_swarm_rounds": 4},
                "stop_signal_policy": {"authority_level_required": 3},
            },
        }
    )

    payload = protocol.to_dict()

    assert payload["generated_legacy_protocol"] is True
    assert payload["targets"][0]["canonical_target"] == "gate:toy_evidence_gate"
    assert payload["targets"][0]["demand_strength"] == 0.91
    assert payload["candidates"][0]["id"] == "candidate:toy:approve"
    assert payload["candidates"][1]["safe_fallback"] is True
    assert payload["evidence_policy"]["raw_data_allowed_in_final"] is False
    assert payload["swarm_loop_policy"]["max_rounds"] == 4
    assert protocol.validation_diagnostics == []


def test_generated_legacy_intents_are_explicit_compatibility_map_only() -> None:
    assert LEGACY_CAPABILITY_TYPE_INTENTS["skill:code-development"] == "code_development"

    generated = load_protocol_from_capability(
        {
            "id": "legacy-code",
            "version": "0.1.0",
            "capability_types": ["skill:code-development"],
            "risk_level": "low",
        }
    )
    explicit = load_protocol_from_capability(
        {
            "id": "explicit-code",
            "version": "0.1.0",
            "capability_types": ["skill:code-development"],
            "risk_level": "low",
            "protocol": {
                "intents": ["explicit_code_review"],
                "targets": [{"target": "gate:explicit_code_review"}],
            },
        }
    )

    assert generated.generated_legacy_protocol is True
    assert generated.source == "generated_legacy_protocol"
    assert generated.intents == ["code_development"]
    assert explicit.generated_legacy_protocol is False
    assert explicit.intents == ["explicit_code_review"]


def test_explicit_protocol_does_not_infer_safe_fallback_from_candidate_label() -> None:
    protocol = load_protocol_from_capability(
        {
            "id": "explicit-toy",
            "version": "0.1.0",
            "capability_types": ["toy.review"],
            "risk_level": "low",
            "trust_level": "first_party_reviewed",
            "protocol": {
                "intents": ["toy_review"],
                "targets": [{"target": "gate:toy_evidence_gate"}],
                "candidates": [
                    {
                        "candidate": "candidate:toy:insufficient_evidence",
                        "label": "Insufficient evidence",
                    }
                ],
            },
        }
    )

    payload = protocol.to_dict()

    assert payload["generated_legacy_protocol"] is False
    assert payload["candidates"][0]["safe_fallback"] is False


def test_value_investing_target_aliases_are_protocol_declared() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None

    bundle = capability_protocol_bundle([manifest.to_public_dict()])

    assert bundle["target_aliases"]["target price"] == "decision:formal_valuation"
    assert bundle["target_aliases"]["investment recommendation"] == "decision:formal_valuation"
    assert bundle["target_aliases"]["recommendation"] == "decision:formal_valuation"
    formal_target = next(
        target for target in bundle["targets"]
        if target["canonical_target"] == "decision:formal_valuation"
    )
    assert "target price" in formal_target["aliases"]


def test_value_investing_source_mode_guidance_is_tool_policy_declared() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")
    assert manifest is not None

    bundle = capability_protocol_bundle([manifest.to_public_dict()])

    assert bundle["tool_policy"]["source_mode"] == "WRDS_ONLY"
    assert bundle["tool_policy"]["source_mode_guidance"].startswith("Source mode is {source_mode}")
    assert bundle["tool_policy"]["source_policy_block_message"] == (
        "{action} is blocked by declared {source_mode} source policy."
    )
    assert bundle["tool_policy"]["source_policy_constraint_message"].startswith("Declared {source_mode} source policy")
    assert bundle["swarm_loop_policy"]["arousal_signal_template"].startswith("Declared arousal level")
    assert bundle["swarm_loop_policy"]["social_immunity_arousal_signal_template"].startswith(
        "Declared social-immunity status"
    )
    assert bundle["swarm_loop_policy"]["social_immunity_recommendations"]["quarantine_required"].startswith(
        "Quarantine contaminated"
    )
    assert bundle["swarm_loop_policy"]["homeostasis_signal_template"].startswith("Declared homeostasis status")
    assert bundle["swarm_loop_policy"]["homeostasis_recommendations"]["token_heat"].startswith("Compress agent")
    assert bundle["swarm_loop_policy"]["lane_policy"]["preferred_lanes"]["writer"] == "synthesis"
    assert bundle["swarm_loop_policy"]["lane_policy"]["assignment_signal_template"].startswith("Declared lane")
    assert bundle["swarm_loop_policy"]["maturity_policy"]["maturity_order"] == [
        "observer",
        "worker",
        "specialist",
        "verifier",
        "blocker",
    ]
    assert bundle["swarm_loop_policy"]["maturity_policy"]["signal_template"].startswith("Declared maturity")
    assert bundle["swarm_loop_policy"]["independent_scout_policy"]["signal_template"].startswith(
        "Declared independent scout"
    )
    assert bundle["swarm_loop_policy"]["independent_scout_policy"]["source_family_rules"][0]["family"] == "risk"
    assert bundle["swarm_loop_policy"]["controller_action_policy"]["runtime_budget_target"] == "swarm:runtime_budget"
    assert bundle["swarm_loop_policy"]["controller_action_policy"]["quorum_policy_signal_template"].startswith(
        "Declared swarm controller"
    )
    assert bundle["swarm_loop_policy"]["tool_health_recommendations"]["failing"].startswith("Block or reroute")
    assert bundle["swarm_loop_policy"]["encounter_rate_recommendations"]["healthy"].startswith("Maintain or expand")


def test_code_development_target_aliases_are_protocol_declared() -> None:
    manifest = CapabilityRegistry().get("code-development")
    assert manifest is not None

    bundle = capability_protocol_bundle([manifest.to_public_dict()])

    assert bundle["target_aliases"]["tests_failed"] == "gate:code_test_gate"
    assert bundle["target_aliases"]["public_api_changed"] == "constraint:code_public_api"
    assert bundle["target_aliases"]["accept_patch"] == "decision:code_patch_acceptance"
    test_gate = next(
        target for target in bundle["targets"]
        if target["canonical_target"] == "gate:code_test_gate"
    )
    assert "tests_failed" in test_gate["aliases"]


def test_compliance_target_aliases_are_protocol_declared() -> None:
    manifest = CapabilityRegistry().get("compliance-workflow")
    assert manifest is not None

    bundle = capability_protocol_bundle([manifest.to_public_dict()])

    assert bundle["target_aliases"]["approval_required"] == "decision:compliance_approval"
    assert bundle["target_aliases"]["email_send"] == "constraint:compliance_external_action"
    assert bundle["target_aliases"]["records_retention"] == "constraint:compliance_retention"
    approval_target = next(
        target for target in bundle["targets"]
        if target["canonical_target"] == "decision:compliance_approval"
    )
    assert "approval_required" in approval_target["aliases"]


def test_research_target_aliases_are_protocol_declared() -> None:
    registry = CapabilityRegistry()
    evidence = registry.get("evidence-research")
    web = registry.get("web-research")
    assert evidence is not None
    assert web is not None

    evidence_bundle = capability_protocol_bundle([evidence.to_public_dict()])
    web_bundle = capability_protocol_bundle([web.to_public_dict()])

    assert evidence_bundle["target_aliases"]["fake_citation"] == "gate:research_citation_audit"
    assert evidence_bundle["target_aliases"]["claim_support"] == "gate:research_evidence_gate"
    assert evidence_bundle["target_aliases"]["source_quality"] == "metric:research_source_quality"
    assert evidence_bundle["target_aliases"]["atomic_claims"] == "research:claim_decomposition"
    citation_target = next(
        target for target in evidence_bundle["targets"]
        if target["canonical_target"] == "gate:research_citation_audit"
    )
    assert "fake_citation" in citation_target["aliases"]
    assert web_bundle["target_aliases"]["source_candidates"] == "research:source_retrieval"
    assert web_bundle["target_aliases"]["claim_support"] == "gate:research_evidence_gate"
    assert web_bundle["target_aliases"]["source_quality"] == "metric:research_source_quality"


def test_explicit_protocol_validates_references_and_defaults() -> None:
    protocol = load_protocol_from_capability(
        {
            "id": "toy-review",
            "trust_level": "first_party_reviewed",
            "protocol": {
                "version": "1.0.0",
                "intents": ["toy_review"],
                "intent_keywords": {
                    "toy_review": ["toy artifact", "toy evidence"],
                },
                "required_capability_types": ["toy.evidence_store"],
                "required_capability_types_by_intent": {
                    "toy_review": ["toy.review"],
                },
                "targets": [
                    {
                        "target": "gate:toy_evidence_gate",
                        "target_type": "gate",
                        "aliases": ["toy evidence gate"],
                        "compatible_intents": ["toy_review"],
                    }
                ],
                "candidates": [
                    {
                        "candidate": "candidate:toy:approve",
                        "target": "gate:toy_evidence_gate",
                        "blocked_by_targets": ["gate:toy_evidence_gate"],
                    },
                    {
                        "candidate": "candidate:toy:insufficient_evidence",
                        "target": "gate:toy_evidence_gate",
                        "safe_fallback": True,
                    }
                ],
                "recovery_protocols": [
                    {
                        "recovery_id": "toy_recovery",
                        "trigger_targets": ["gate:toy_evidence_gate"],
                        "max_rounds": 2,
                        "allowed_agent_roles": ["evidence_scout"],
                    }
                ],
                "quorum_policy": {
                    "candidates": ["candidate:toy:approve"],
                    "candidate_fallback": "candidate:toy:insufficient_evidence",
                },
                "tool_policy": {
                    "source_mode": "WRDS_ONLY",
                    "source_policy_blocked_tool_targets": ["tool:custom_news_api"],
                    "source_mode_guidance": "Use {source_mode} sources; block {blocked_tools}.",
                    "source_policy_block_message": "{action} blocked by {source_mode}.",
                    "source_policy_constraint_message": "{source_mode} constraint active.",
                },
                "evidence_policy": {
                    "raw_data_allowed_in_final": False,
                    "raw_data_markers": ["toy-secret-row="],
                },
                "output_policy": {
                    "blocked_phrases": ["unsupported toy claim"],
                    "committed_candidate_conflicts": [
                        {
                            "candidate": "candidate:toy:insufficient_evidence",
                            "blocked_phrases": ["Approve"],
                        }
                    ],
                },
            },
        }
    )

    payload = protocol.to_dict()

    assert payload["generated_legacy_protocol"] is False
    assert payload["intents"] == ["toy_review"]
    assert payload["intent_keywords"] == {"toy_review": ["toy artifact", "toy evidence"]}
    assert payload["required_capability_types"] == ["toy.evidence_store"]
    assert payload["required_capability_types_by_intent"] == {
        "toy_review": ["toy.review"],
    }
    assert payload["targets"][0]["compatible_intents"] == ["toy_review"]
    assert payload["recovery_protocols"][0]["allowed_agent_roles"] == ["evidence_scout"]
    assert payload["tool_policy"]["source_mode"] == "WRDS_ONLY"
    assert payload["tool_policy"]["source_policy_blocked_tool_targets"] == ["tool:custom_news_api"]
    assert payload["tool_policy"]["source_mode_guidance"] == "Use {source_mode} sources; block {blocked_tools}."
    assert payload["tool_policy"]["source_policy_block_message"] == "{action} blocked by {source_mode}."
    assert payload["tool_policy"]["source_policy_constraint_message"] == "{source_mode} constraint active."
    assert payload["evidence_policy"]["raw_data_markers"] == ["toy-secret-row="]
    assert payload["output_policy"]["writer_can_create_facts"] is False
    assert payload["output_policy"]["committed_candidate_conflicts"][0]["blocked_phrases"] == ["Approve"]
    assert protocol.validation_diagnostics == []


def test_legacy_quorum_force_fallback_field_loads_as_compatibility_alias() -> None:
    protocol = load_protocol_from_capability(
        {
            "id": "legacy-quorum-field",
            "trust_level": "first_party_reviewed",
            "protocol": {
                "intents": ["toy_review"],
                "targets": [{"target": "gate:toy_evidence_gate"}],
                "candidates": [
                    {"candidate": "candidate:toy:approve", "target": "gate:toy_evidence_gate"},
                    {"candidate": "candidate:toy:insufficient_evidence", "safe_fallback": True},
                ],
                "quorum_policy": {
                    "candidates": ["candidate:toy:approve", "candidate:toy:insufficient_evidence"],
                    "candidate_fallback": "candidate:toy:insufficient_evidence",
                    "force_insufficient_data_when_formal_valuation_blocked": True,
                },
            },
        }
    )

    quorum_policy = protocol.to_dict()["quorum_policy"]

    assert quorum_policy["force_fallback_when_blocked"] is True
    assert "force_insufficient_data_when_formal_valuation_blocked" not in quorum_policy


def test_legacy_tool_policy_blocked_target_field_loads_as_compatibility_alias() -> None:
    protocol = load_protocol_from_capability(
        {
            "id": "legacy-tool-field",
            "trust_level": "first_party_reviewed",
            "protocol": {
                "intents": ["toy_review"],
                "targets": [{"target": "gate:toy_evidence_gate"}],
                "tool_policy": {
                    "web_research_tool_targets": ["custom_news_api"],
                },
            },
        }
    )

    tool_policy = protocol.to_dict()["tool_policy"]

    assert tool_policy["source_policy_blocked_tool_targets"] == ["custom_news_api"]
    assert "web_research_tool_targets" not in tool_policy


def test_swarm_declared_intents_load_as_explicit_protocol() -> None:
    protocol = load_protocol_from_capability(
        {
            "id": "compliance-workflow",
            "version": "0.1.0",
            "capability_types": ["compliance.workflow"],
            "risk_level": "low",
            "trust_level": "first_party_reviewed",
            "tools": ["read_file"],
            "swarm": {
                "intents": ["compliance_workflow"],
                "targets": [
                    {
                        "target": "constraint:compliance_pii",
                        "demand_strength": 0.86,
                        "keywords": ["pii", "privacy"],
                    }
                ],
                "candidate_policy": {
                    "candidate_type": "compliance_decision",
                    "candidates": [{"id": "candidate:compliance:mask", "label": "Mask"}],
                },
                "stop_signal_policy": {"authority_level_required": 3},
            },
        }
    )

    payload = protocol.to_dict()

    assert payload["generated_legacy_protocol"] is False
    assert payload["source"] == "capability_swarm_protocol"
    assert payload["intents"] == ["compliance_workflow"]
    assert payload["targets"][0]["canonical_target"] == "constraint:compliance_pii"
    assert payload["targets"][0]["keywords"] == ["pii", "privacy"]
    assert payload["candidates"][0]["id"] == "candidate:compliance:mask"
    assert payload["tool_policy"]["allowed_tool_targets"] == ["tool:read_file"]


def test_empty_protocol_field_does_not_mask_swarm_declared_intents() -> None:
    protocol = load_protocol_from_capability(
        {
            "id": "empty-protocol-wrapper",
            "trust_level": "first_party_reviewed",
            "protocol": {},
            "swarm": {
                "intents": ["wrapped_review"],
                "targets": [{"target": "gate:wrapped_quality", "keywords": ["quality"]}],
            },
        }
    )

    assert protocol.generated_legacy_protocol is False
    assert protocol.source == "capability_swarm_protocol"
    assert protocol.intents == ["wrapped_review"]
    assert protocol.targets[0].target == "gate:wrapped_quality"


def test_document_and_data_capabilities_declare_first_class_protocol_targets() -> None:
    registry = CapabilityRegistry()
    document = registry.get("document-writing")
    data = registry.get("data-analysis")

    assert document is not None
    assert data is not None
    document_protocol = load_protocol_from_capability(document.to_public_dict())
    data_protocol = load_protocol_from_capability(data.to_public_dict())

    assert document_protocol.generated_legacy_protocol is False
    assert document_protocol.intents == ["document_writing"]
    assert {"document", "proposal", "撰写"} <= set(document_protocol.intent_keywords["document_writing"])
    assert {"document_writing", "skill:document-writing"} <= set(document_protocol.required_capability_types)
    assert {target.target for target in document_protocol.targets} == {
        "artifact:document_draft",
        "gate:document_quality",
    }
    assert data_protocol.generated_legacy_protocol is False
    assert data_protocol.intents == ["data_analysis"]
    assert {"csv", "dataset", "summary statistics"} <= set(data_protocol.intent_keywords["data_analysis"])
    assert {"data_analysis", "skill:data-analysis"} <= set(data_protocol.required_capability_types)
    assert {target.target for target in data_protocol.targets} == {
        "metric:data_quality",
        "artifact:data_summary",
        "gate:analysis_reproducibility",
    }
    assert data_protocol.tool_policy.allowed_tool_targets == ["tool:list_files", "tool:read_file"]


def test_value_protocol_declares_portfolio_intent_without_wrds_dependency() -> None:
    manifest = CapabilityRegistry().get("value-investing-research")

    assert manifest is not None
    protocol = load_protocol_from_capability(manifest.to_public_dict())

    assert "portfolio_review" in protocol.intents
    assert {"value investing", "valuation", "现金流"} <= set(protocol.intent_keywords["investment_analysis"])
    assert {"wrds", "metric registry", "财务数据"} <= set(protocol.intent_keywords["financial_data_retrieval"])
    assert {"portfolio", "allocation", "仓位"} <= set(protocol.intent_keywords["portfolio_review"])
    assert {"gvkey", "datadate", "sale="} <= set(protocol.evidence_policy.raw_data_markers)
    assert protocol.required_capability_types_by_intent["portfolio_review"] == []
    portfolio_targets = {
        target.target
        for target in protocol.targets
        if "portfolio_review" in target.compatible_intents
    }
    assert portfolio_targets == {"decision:portfolio_review", "constraint:portfolio_risk"}


def test_protocol_validation_rejects_untrusted_hard_blocking_authority() -> None:
    protocol = load_protocol_from_capability(
        {
            "id": "third-party-review",
            "trust_level": "third_party",
            "protocol": {
                "targets": [{"target": "gate:external_gate"}],
                "stop_signal_policy": {"blocking_authority_required": 3},
            },
        }
    )

    codes = {item["code"] for item in protocol.validation_diagnostics}

    assert "untrusted_blocking_authority" in codes
    assert "third_party_nonblocking_default" in codes


def test_protocol_validation_rejects_unknown_compatible_intents() -> None:
    protocol = load_protocol_from_capability(
        {
            "id": "bad-intent-review",
            "trust_level": "first_party_reviewed",
            "protocol": {
                "intents": ["known_review"],
                "intent_keywords": {"missing_review": ["missing marker"]},
                "required_capability_types_by_intent": {"missing_review": ["missing.review"]},
                "targets": [
                    {
                        "target": "gate:known_review",
                        "compatible_intents": ["missing_review"],
                    }
                ],
            },
        }
    )

    codes = {item["code"] for item in protocol.validation_diagnostics}

    assert "required_capability_intent_unknown" in codes
    assert "intent_keywords_intent_unknown" in codes
    assert "target_compatible_intent_unknown" in codes


def test_protocol_validation_rejects_unknown_candidate_target() -> None:
    protocol = load_protocol_from_capability(
        {
            "id": "bad-review",
            "trust_level": "first_party_reviewed",
            "protocol": {
                "targets": [{"target": "gate:declared"}],
                "candidates": [
                    {
                        "candidate": "candidate:bad:approve",
                        "blocked_by_targets": ["gate:missing"],
                    }
                ],
            },
        }
    )

    assert any(item["code"] == "candidate_references_unknown_target" for item in protocol.validation_diagnostics)


def test_protocol_validation_rejects_unknown_candidate_destination() -> None:
    protocol = load_protocol_from_capability(
        {
            "id": "bad-review",
            "trust_level": "first_party_reviewed",
            "protocol": {
                "targets": [{"target": "gate:declared"}],
                "candidates": [
                    {
                        "candidate": "candidate:bad:approve",
                        "target": "decision:missing",
                    }
                ],
            },
        }
    )

    assert any(item["code"] == "candidate_target_unknown" for item in protocol.validation_diagnostics)


def test_protocol_validation_rejects_unknown_quorum_and_recovery_candidates() -> None:
    protocol = load_protocol_from_capability(
        {
            "id": "bad-review",
            "trust_level": "first_party_reviewed",
            "protocol": {
                "targets": [{"target": "gate:declared"}],
                "candidates": [{"candidate": "candidate:bad:approve", "target": "gate:declared"}],
                "quorum_policy": {
                    "candidates": ["candidate:bad:approve", "candidate:bad:missing"],
                    "candidate_fallback": "candidate:bad:fallback",
                },
                "recovery_protocols": [
                    {
                        "recovery_id": "bad_recovery",
                        "trigger_targets": ["gate:declared"],
                        "recovery_failure_candidate": "candidate:bad:missing",
                    }
                ],
            },
        }
    )

    codes = {item["code"] for item in protocol.validation_diagnostics}

    assert "quorum_references_unknown_candidate" in codes
    assert "quorum_fallback_unknown_candidate" in codes
    assert "recovery_failure_unknown_candidate" in codes


def test_protocol_validation_rejects_unknown_stop_signal_trigger_target() -> None:
    protocol = load_protocol_from_capability(
        {
            "id": "bad-review",
            "trust_level": "first_party_reviewed",
            "protocol": {
                "targets": [{"target": "gate:declared"}],
                "stop_signal_policy": {
                    "rules": [
                        {
                            "id": "missing_trigger",
                            "trigger_targets": ["gate:missing"],
                            "blocked_actions": ["writer:publish"],
                        }
                    ]
                },
            },
        }
    )

    assert any(
        item["code"] == "stop_signal_references_unknown_target"
        for item in protocol.validation_diagnostics
    )


def test_capability_protocol_bundle_preserves_shape_and_marks_legacy() -> None:
    bundle = capability_protocol_bundle(
        [
            {
                "id": "toy-review",
                "trust_level": "first_party_reviewed",
                "entrypoints": {"workflow": "workflow.py:build_workflow_descriptor"},
                "swarm": {
                    "targets": [{"target": "decision:toy_publish", "demand_strength": 0.88}],
                    "candidate_policy": {
                        "candidate_type": "toy_decision",
                        "candidates": [{"id": "candidate:toy:approve", "label": "Approve"}],
                    },
                    "recovery_protocols": [
                        {"id": "toy_recovery", "targets": [{"target": "decision:toy_publish"}], "max_rounds": 2}
                    ],
                    "evidence_policy": {"citation_required": True, "raw_data_allowed_in_final": False},
                },
            }
        ]
    )

    assert bundle["protocol_source"] == "capability_manifest"
    assert bundle["generated_legacy_protocol_count"] == 1
    assert bundle["targets"][0]["canonical_target"] == "decision:toy_publish"
    assert bundle["candidate_policy"]["candidate_type"] == "toy_decision"
    assert bundle["candidate_policy"]["candidates"][0]["id"] == "candidate:toy:approve"
    assert bundle["evidence_policy"]["citation_required"] is True
    assert bundle["recovery_protocols"][0]["id"] == "toy_recovery"
    assert bundle["workflow_entrypoints"] == [{"capability_id": "toy-review", "workflow": "workflow.py:build_workflow_descriptor"}]


def test_builtin_workflow_capabilities_use_first_class_protocols() -> None:
    registry = CapabilityRegistry()

    for capability_id, expected_candidate_count in {
        "code-development": 3,
        "compliance-workflow": 4,
        "evidence-research": 3,
        "web-research": 3,
    }.items():
        manifest = registry.get(capability_id)
        assert manifest is not None

        protocol = load_protocol_from_capability(manifest.to_public_dict())

        assert manifest.swarm == {}
        assert protocol.source == "capability_protocol"
        assert protocol.generated_legacy_protocol is False
        assert len(protocol.targets) > 0
        assert len(protocol.candidates) == expected_candidate_count
        assert protocol.validation_diagnostics == []


def test_builtin_workflow_capabilities_declare_intent_keywords_and_requirements() -> None:
    registry = CapabilityRegistry()
    expected = {
        "code-development": {
            "intent": "code_development",
            "keywords": {"source code", "patch", "pytest", "修复"},
            "required": {"code_development", "skill:code-development"},
        },
        "compliance-workflow": {
            "intent": "compliance_workflow",
            "keywords": {"policy", "pii", "approval", "访问控制"},
            "required": {"compliance.workflow", "skill:compliance-workflow"},
        },
        "web-research": {
            "intent": "web_research",
            "keywords": {"web research", "latest", "official", "来源"},
            "required": {"public_web_research", "skill:web-research"},
        },
        "evidence-research": {
            "intent": "evidence_research",
            "keywords": {"citation", "source quality", "contradiction", "群体决策"},
            "required": {"evidence.research", "skill:evidence-research"},
        },
    }

    for capability_id, assertions in expected.items():
        manifest = registry.get(capability_id)
        assert manifest is not None

        protocol = load_protocol_from_capability(manifest.to_public_dict())
        intent = assertions["intent"]

        assert protocol.generated_legacy_protocol is False
        assert intent in protocol.intents
        assert assertions["keywords"] <= set(protocol.intent_keywords[intent])
        assert assertions["required"] <= set(protocol.required_capability_types)


def test_builtin_workflow_capabilities_declare_stop_action_markers() -> None:
    registry = CapabilityRegistry()
    expected_actions = {
        "value-investing-research": {"writer:formal_valuation", "final_judge:investment_recommendation"},
        "code-development": {"writer:claim_tests_passed", "final_judge:accept_patch"},
        "compliance-workflow": {"writer:approval_claim", "final_judge:external_action"},
        "evidence-research": {"writer:confirmed_claim", "final_judge:publish_without_citation_audit"},
    }

    for capability_id, actions in expected_actions.items():
        manifest = registry.get(capability_id)
        assert manifest is not None
        protocol = load_protocol_from_capability(manifest.to_public_dict())
        markers = protocol.stop_signal_policy.action_markers

        assert actions <= {str(marker.get("action")) for marker in markers if isinstance(marker, dict)}


def test_loader_reads_adjacent_pheroos_protocol_json(tmp_path) -> None:
    capability_dir = tmp_path / "capabilities" / "toy-review"
    capability_dir.mkdir(parents=True)
    manifest_path = capability_dir / "capability.json"
    manifest_path.write_text("{}", encoding="utf-8")
    (capability_dir / "pheroos_protocol.json").write_text(
        json.dumps(
            {
                "intents": ["toy_review"],
                "targets": [{"target": "decision:toy_publish"}],
                "candidates": [{"candidate": "candidate:toy:approve"}],
            }
        ),
        encoding="utf-8",
    )

    protocol = load_protocol_from_capability(
        {
            "id": "toy-review",
            "path": str(manifest_path),
            "trust_level": "first_party_reviewed",
        }
    )

    assert protocol.generated_legacy_protocol is False
    assert protocol.intents == ["toy_review"]
    assert protocol.targets[0].target == "decision:toy_publish"
