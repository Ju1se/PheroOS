from __future__ import annotations

from runtime.swarm.evidence_contract import build_writer_evidence_contract, validate_writer_evidence_contract
from runtime.swarm.evidence_graph import build_evidence_graph
from runtime.writer_guardrails import apply_writer_guardrails


def test_evidence_graph_writer_contract_exposes_verified_claims_and_allowed_metrics() -> None:
    graph = build_evidence_graph(
        {
            "run_id": "run-contract",
            "metric_registry": {"metrics": [{"name": "free_cash_flow", "value": 120, "period": "FY2025"}]},
            "data_gate": {"status": "PASS_WRDS_ONLY", "formal_valuation_allowed": True, "report_publication_allowed": True},
            "committee_decision": {"core_thesis": "Free cash flow supports a preliminary quality view."},
            "quorum_trace": {"committed_candidate": {"label": "Watch"}},
        }
    )
    contract = graph["writer_contract"]

    assert contract["schema_version"] == "pheroos.writer_evidence_contract.v1"
    assert contract["verified_claims"][0]["content"] == "Free cash flow supports a preliminary quality view."
    assert contract["verified_claims"][0]["evidence_sources"] == ["metric:free_cash_flow:FY2025"]
    assert contract["allowed_metrics"][0]["name"] == "free_cash_flow"
    assert "agent proposals" in contract["unverified_signal_policy"]
    assert "committee proposals" not in contract["unverified_signal_policy"]


def test_evidence_graph_outputs_all_declared_conclusion_permissions() -> None:
    graph = build_evidence_graph(
        {
            "run_id": "run-permissions",
            "data_gate": {
                "status": "PASS_WITH_LIMITS",
                "conclusion_permissions": {
                    "peer_valuation_allowed": False,
                    "ev_ebitda_allowed": True,
                    "decision:toy_publish": {"allowed": False, "label": "toy publish"},
                },
            },
        }
    )

    by_target = {node["canonical_target"]: node for node in graph["output_permissions"]}

    assert by_target["decision:peer_valuation"]["allowed"] is False
    assert by_target["decision:peer_valuation"]["label"] == "peer valuation"
    assert by_target["decision:ev_ebitda"]["allowed"] is True
    assert by_target["decision:toy_publish"]["allowed"] is False
    assert by_target["decision:toy_publish"]["label"] == "toy publish"
    assert {"decision:peer_valuation", "decision:toy_publish"} <= set(
        graph["writer_contract"]["blocked_outputs"]
    )


def test_evidence_graph_does_not_invent_legacy_output_permissions_without_declarations() -> None:
    graph = build_evidence_graph(
        {
            "run_id": "run-no-default-permissions",
            "metadata": {
                "os_plan": {
                    "selected_capability_id": "toy-review",
                    "swarm_plan": {
                        "protocol_source": "capability_manifest",
                        "capability_protocols": [{"capability_id": "toy-review"}],
                    },
                }
            },
            "data_gate": {"status": "PASS_TOY_ONLY"},
        }
    )

    assert graph["output_permissions"] == []
    assert graph["summary"]["blocked_outputs"] == []
    assert graph["writer_contract"]["blocked_outputs"] == []


def test_protocol_decision_claim_does_not_inherit_legacy_publication_default() -> None:
    graph = build_evidence_graph(
        {
            "run_id": "run-no-default-claim-permission",
            "metadata": {
                "os_plan": {
                    "selected_capability_id": "toy-review",
                    "swarm_plan": {
                        "protocol_source": "capability_manifest",
                        "capability_protocols": [{"capability_id": "toy-review"}],
                    },
                }
            },
            "data_gate": {"status": "PASS_TOY_ONLY"},
            "committee_decision": {
                "final_decision": "Approve toy publication.",
                "key_evidence": ["Toy citation packet is available."],
            },
            "quorum_trace": {"committed_candidate": {"label": "Approve", "target": "decision:toy_publish"}},
        }
    )

    by_type = {claim["claim_type"]: claim for claim in graph["decision_claims"]}

    assert by_type["final_decision"]["canonical_target"] == "decision:toy_publish"
    assert by_type["final_decision"]["output_allowed"] is False
    assert by_type["final_decision"]["verification_state"] == "unverified"
    assert by_type["key_evidence"]["output_allowed"] is False


def test_evidence_graph_prefers_generic_agent_decision_over_legacy_committee_decision() -> None:
    graph = build_evidence_graph(
        {
            "run_id": "run-generic-agent-decision",
            "agent_decision": {"final_decision": "Approve toy publication."},
            "committee_decision": {"final_decision": "Reject legacy publication."},
            "data_gate": {
                "status": "PASS_TOY_ONLY",
                "conclusion_permissions": {"decision:toy_publish": True},
            },
            "quorum_trace": {
                "committed_candidate": {"label": "Approve", "target": "decision:toy_publish"}
            },
        }
    )

    claim = graph["decision_claims"][0]

    assert claim["content"] == "Approve toy publication."
    assert claim["decision_source"] == "agent_decision"
    assert claim["source_module"] == "agent_decision"
    assert claim["output_allowed"] is True


def test_declared_target_permission_allows_protocol_decision_claim_without_report_default() -> None:
    graph = build_evidence_graph(
        {
            "run_id": "run-target-claim-permission",
            "metadata": {
                "os_plan": {
                    "selected_capability_id": "toy-review",
                    "swarm_plan": {
                        "protocol_source": "capability_manifest",
                        "capability_protocols": [{"capability_id": "toy-review"}],
                    },
                }
            },
            "data_gate": {
                "status": "PASS_TOY_ONLY",
                "conclusion_permissions": {
                    "decision:toy_publish": {"allowed": True, "label": "toy publish"},
                },
            },
            "committee_decision": {"final_decision": "Approve toy publication."},
            "quorum_trace": {"committed_candidate": {"label": "Approve", "target": "decision:toy_publish"}},
        }
    )

    claim = graph["decision_claims"][0]

    assert claim["canonical_target"] == "decision:toy_publish"
    assert claim["output_allowed"] is True
    assert claim["verification_state"] == "contested"


def test_key_evidence_uses_declared_publish_permission_without_report_default() -> None:
    graph = build_evidence_graph(
        {
            "run_id": "run-key-evidence-publish-target",
            "metadata": {
                "os_plan": {
                    "selected_capability_id": "toy-review",
                    "swarm_plan": {
                        "protocol_source": "capability_manifest",
                        "capability_protocols": [{"capability_id": "toy-review"}],
                    },
                }
            },
            "data_gate": {
                "status": "PASS_TOY_ONLY",
                "conclusion_permissions": {
                    "decision:toy_publish": {"allowed": True, "label": "toy publish"},
                },
            },
            "committee_decision": {"key_evidence": ["Toy citation packet is available."]},
        }
    )

    claim = graph["decision_claims"][0]

    assert claim["claim_type"] == "key_evidence"
    assert claim["canonical_target"] == "decision:toy_publish"
    assert claim["output_allowed"] is True


def test_decision_claim_output_permission_uses_committed_candidate_target() -> None:
    graph = build_evidence_graph(
        {
            "run_id": "run-toy-blocked-decision",
            "data_gate": {
                "status": "PASS_WITH_LIMITS",
                "conclusion_permissions": {
                    "decision:toy_publish": {"allowed": False, "label": "toy publish"},
                    "report_publication_allowed": True,
                },
            },
            "committee_decision": {"final_decision": "Approve toy publication."},
            "quorum_trace": {
                "committed_candidate": {
                    "label": "Approve",
                    "target": "decision:toy_publish",
                }
            },
        }
    )

    claim = graph["decision_claims"][0]

    assert claim["claim_type"] == "final_decision"
    assert claim["canonical_target"] == "decision:toy_publish"
    assert claim["output_allowed"] is False
    assert graph["writer_contract"]["blocked_outputs"] == ["decision:toy_publish"]


def test_evidence_graph_links_gate_blocker_to_declared_output_permission() -> None:
    graph = build_evidence_graph(
        {
            "run_id": "run-toy-output-edge",
            "data_gate": {
                "status": "PASS_WITH_LIMITS",
                "conclusion_permissions": {
                    "decision:toy_publish": {"allowed": False, "label": "toy publish"},
                },
            },
            "stop_signals": [
                {
                    "id": "sig-toy-gate",
                    "type": "stop_signal",
                    "target": "gate:toy_evidence_gate",
                    "content": "Toy evidence gate blocks publication.",
                    "verification_state": "blocking",
                    "blocking": True,
                    "source_module": "data_gate",
                }
            ],
        }
    )

    assert {
        "source": "sig-toy-gate",
        "target": "permission:decision:toy_publish",
        "relation": "blocks",
    } in graph["edges"]


def test_decision_claim_source_comes_from_declared_capability_protocol() -> None:
    graph = build_evidence_graph(
        {
            "run_id": "run-toy-claims",
            "metadata": {
                "os_plan": {
                    "selected_capability_id": "toy-review",
                    "swarm_plan": {
                        "protocol_source": "capability_manifest",
                        "workflow_entrypoints": [{"capability_id": "toy-review", "workflow": "workflow.py:build"}],
                        "capability_protocols": [{"capability_id": "toy-review"}],
                    },
                }
            },
            "data_gate": {"status": "PASS_TOY_ONLY", "formal_valuation_allowed": True, "report_publication_allowed": True},
            "committee_decision": {
                "final_decision": "Approve",
                "key_evidence": ["Toy citation packet is available."],
            },
            "quorum_trace": {"committed_candidate": {"label": "Approve"}},
        }
    )

    assert {claim["source_module"] for claim in graph["decision_claims"]} == {"capability:toy-review"}
    assert graph["writer_contract"]["caveated_claims"][0]["source_module"] == "capability:toy-review"


def test_decision_claim_source_marks_legacy_committee_fallback() -> None:
    graph = build_evidence_graph(
        {
            "run_id": "run-legacy-claims",
            "data_gate": {"status": "PASS", "formal_valuation_allowed": True, "report_publication_allowed": True},
            "committee_decision": {"final_decision": "Watch"},
            "quorum_trace": {"committed_candidate": {"label": "Watch"}},
        }
    )

    assert {claim["source_module"] for claim in graph["decision_claims"]} == {"legacy:investment_committee"}
    assert {claim["decision_source"] for claim in graph["decision_claims"]} == {"legacy_committee_decision"}


def test_evidence_graph_does_not_mechanically_link_unrelated_metrics_to_claims() -> None:
    graph = build_evidence_graph(
        {
            "run_id": "run-unrelated",
            "metric_registry": {"metrics": [{"name": "revenue", "value": 100, "period": "FY2025"}]},
            "data_gate": {"status": "PASS_WRDS_ONLY", "formal_valuation_allowed": True, "report_publication_allowed": True},
            "committee_decision": {"core_thesis": "The company has durable pricing power."},
            "quorum_trace": {"committed_candidate": {"label": "Watch"}},
        }
    )

    assert graph["writer_contract"]["verified_claims"] == []
    assert graph["writer_contract"]["caveated_claims"][0]["content"] == "The company has durable pricing power."
    assert graph["writer_contract"]["caveated_claims"][0]["evidence_sources"] == []


def test_writer_contract_marks_unlinked_claims_as_caveated() -> None:
    graph = build_evidence_graph(
        {
            "run_id": "run-caveat",
            "metric_registry": {"metrics": []},
            "data_gate": {"status": "PASS_WRDS_ONLY", "formal_valuation_allowed": True, "report_publication_allowed": True},
            "committee_decision": {"core_thesis": "The company has durable pricing power."},
            "quorum_trace": {"committed_candidate": {"label": "Watch"}},
        }
    )

    assert graph["writer_contract"]["verified_claims"] == []
    assert graph["writer_contract"]["caveated_claims"][0]["content"] == "The company has durable pricing power."


def test_writer_guardrail_blocks_caveated_claim_without_caveat_language() -> None:
    state = {
        "evidence_graph": build_evidence_graph(
            {
                "metric_registry": {"metrics": []},
                "data_gate": {
                    "status": "PASS_WRDS_ONLY",
                    "formal_valuation_allowed": True,
                    "report_publication_allowed": True,
                },
                "committee_decision": {"core_thesis": "The company has durable pricing power."},
                "quorum_trace": {"committed_candidate": {"label": "Watch"}},
            }
        )
    }

    guarded = apply_writer_guardrails("The company has durable pricing power.", state)

    assert "Evidence Graph Contract Guardrail Report" in guarded
    assert "caveated_claim_without_caveat" in guarded


def test_writer_guardrail_allows_caveated_claim_with_caveat_language() -> None:
    state = {
        "evidence_graph": build_evidence_graph(
            {
                "metric_registry": {"metrics": []},
                "data_gate": {
                    "status": "PASS_WRDS_ONLY",
                    "formal_valuation_allowed": True,
                    "report_publication_allowed": True,
                },
                "committee_decision": {"core_thesis": "The company has durable pricing power."},
                "quorum_trace": {"committed_candidate": {"label": "Watch"}},
            }
        )
    }

    guarded = apply_writer_guardrails("初步看，The company has durable pricing power，但该判断仍需补充证据。", state)

    assert "Guardrail Report" not in guarded


def test_writer_guardrail_requires_evidence_graph_caveats() -> None:
    state = {
        "data_gate": {"required_caveats": ["WRDS-only preliminary view"]},
        "evidence_graph": build_evidence_graph(
            {
                "metric_registry": {"metrics": [{"name": "revenue", "value": 100}]},
                "data_gate": {
                    "status": "PASS_WRDS_ONLY",
                    "formal_valuation_allowed": True,
                    "report_publication_allowed": True,
                    "required_caveats": ["WRDS-only preliminary view"],
                },
                "committee_decision": {"core_thesis": "Revenue supports a preliminary view."},
            }
        ),
    }

    violations = validate_writer_evidence_contract("Revenue supports a preliminary view.", state)
    guarded = apply_writer_guardrails("Revenue supports a preliminary view.", state)

    assert any(item["code"] == "missing_required_caveat" for item in violations)
    assert "Evidence Graph Contract Guardrail Report" in guarded


def test_build_writer_evidence_contract_includes_evidence_steward_blocked_claims() -> None:
    contract = build_writer_evidence_contract(
        {
            "evidence_steward_report": {
                "blocked_claims": [{"claim_id": "claim:buy", "content": "Buy with target price 100."}],
                "unsupported_claims": [{"claim_id": "claim:unsupported", "content": "Revenue will double next year."}],
            }
        }
    )

    assert contract["blocked_claims"][0]["content"] == "Buy with target price 100."
    assert contract["unsupported_claims"][0]["content"] == "Revenue will double next year."


def test_writer_contract_formal_block_uses_declared_action_markers() -> None:
    state = {
        "metadata": {
            "os_plan": {
                "swarm_plan": {
                    "stop_signal_policy": {
                        "action_markers": [
                            {
                                "action": "writer:formal_valuation",
                                "phrases": ["formal toy approval"],
                            }
                        ]
                    }
                }
            }
        },
        "data_gate": {"formal_valuation_allowed": False},
    }

    contract = build_writer_evidence_contract(state)
    legacy_violations = validate_writer_evidence_contract("Buy with target price 100.", state)
    declared_violations = validate_writer_evidence_contract("Formal toy approval.", state)

    assert contract["forbidden_phrases"] == ["formal toy approval"]
    assert not legacy_violations
    assert declared_violations == [{"code": "forbidden_phrase", "message": "formal toy approval"}]


def test_writer_contract_uses_generic_blocked_conclusion_action_markers() -> None:
    state = {
        "metadata": {
            "os_plan": {
                "swarm_plan": {
                    "stop_signal_policy": {
                        "action_markers": [
                            {
                                "action": "writer:peer_valuation",
                                "phrases": ["peer toy approval"],
                            }
                        ]
                    }
                }
            }
        },
        "data_gate": {"conclusion_permissions": {"peer_valuation_allowed": False}},
    }

    contract = build_writer_evidence_contract(state)
    violations = validate_writer_evidence_contract("Peer toy approval.", state)

    assert contract["forbidden_phrases"] == ["peer toy approval"]
    assert violations == [{"code": "forbidden_phrase", "message": "peer toy approval"}]


def test_writer_contract_candidate_conflicts_come_from_output_policy() -> None:
    state = {
        "metadata": {
            "os_plan": {
                "swarm_plan": {
                    "output_policy": {
                        "committed_candidate_conflicts": [
                            {
                                "candidate": "candidate:toy:reject",
                                "blocked_phrases": ["Approve"],
                            }
                        ]
                    }
                }
            }
        },
        "data_gate": {"formal_valuation_allowed": False},
        "quorum_trace": {"committed_candidate": {"id": "candidate:toy:reject", "label": "Reject"}},
    }

    contract = build_writer_evidence_contract(state)
    legacy_violations = validate_writer_evidence_contract("Buy with target price 100.", state)
    declared_violations = validate_writer_evidence_contract("Approve this toy review.", state)

    assert contract["forbidden_phrases"] == ["Approve"]
    assert not legacy_violations
    assert declared_violations == [{"code": "forbidden_phrase", "message": "Approve"}]


def test_writer_contract_raw_data_policy_cannot_be_weakened() -> None:
    state = {
        "metadata": {
            "os_plan": {
                "swarm_plan": {
                    "evidence_policy": {
                        "raw_data_allowed_in_final": True,
                        "raw_data_markers": ["toy-secret-row="],
                    }
                }
            }
        }
    }

    contract = build_writer_evidence_contract(state)

    assert contract["policy"]["raw_data_allowed_in_final"] is False
    assert contract["policy"]["declared_raw_data_allowed_in_final"] is True


def test_writer_contract_fact_creation_policy_cannot_be_weakened() -> None:
    state = {
        "metadata": {
            "os_plan": {
                "swarm_plan": {
                    "output_policy": {
                        "writer_can_create_facts": True,
                    },
                    "evidence_policy": {
                        "unsupported_claim_action": "block",
                    },
                }
            }
        }
    }

    contract = build_writer_evidence_contract(state)
    violations = validate_writer_evidence_contract("Revenue will double next year.", state)

    assert contract["policy"]["writer_can_create_facts"] is False
    assert contract["policy"]["declared_writer_can_create_facts"] is True
    assert violations == [{"code": "unsupported_strong_claim", "message": "will double"}]


def test_writer_contract_legacy_mismatch_uses_fallback_candidate_identity() -> None:
    state = {
        "quorum_trace": {
            "committed_candidate": {
                "id": "candidate:toy:escalate",
                "label": "Escalate",
                "safe_fallback": True,
            }
        }
    }

    violations = validate_writer_evidence_contract("Buy with target price 100.", state)
    mismatch = next(item for item in violations if item["code"] == "committed_candidate_mismatch")

    assert mismatch["message"] == "Escalate"
    assert all(item["message"] != "Insufficient Data" for item in violations)


def test_writer_contract_does_not_infer_protocol_fallback_from_insufficient_label() -> None:
    state = {
        "quorum_trace": {
            "candidate_source": "capability_protocol",
            "candidate_registry_trace": [{"event_type": "candidate_registry.loaded_declared_candidates"}],
            "committed_candidate": {
                "id": "candidate:toy:insufficient_evidence",
                "label": "Insufficient Evidence",
            },
        }
    }

    contract = build_writer_evidence_contract(state)
    violations = validate_writer_evidence_contract("Buy with target price 100.", state)

    assert contract["forbidden_phrases"] == []
    assert not any(item["code"] == "committed_candidate_mismatch" for item in violations)


def test_writer_contract_uses_declared_fallback_candidate_identity() -> None:
    state = {
        "quorum_trace": {
            "candidate_source": "capability_protocol",
            "candidate_registry_trace": [{"event_type": "candidate_registry.loaded_declared_candidates"}],
            "fallback_candidate": {
                "id": "candidate:toy:insufficient_evidence",
                "label": "Insufficient Evidence",
            },
            "committed_candidate": {
                "id": "candidate:toy:insufficient_evidence",
                "label": "Insufficient Evidence",
            },
        }
    }

    contract = build_writer_evidence_contract(state)
    violations = validate_writer_evidence_contract("Buy with target price 100.", state)
    mismatch = next(item for item in violations if item["code"] == "committed_candidate_mismatch")

    assert "Buy" in contract["forbidden_phrases"]
    assert mismatch["message"] == "Insufficient Evidence"
