from __future__ import annotations

import pytest

from runtime.capability_registry import CapabilityRegistry
from runtime.final_judge_guardrails import apply_final_judge_guardrails
from runtime.swarm.policing import build_policing_trace
from runtime.swarm.protocol_loader import load_protocol_from_capability
from runtime.writer_guardrails import apply_writer_guardrails


def swarm_plan_for_capability(capability_id: str) -> dict:
    manifest = CapabilityRegistry().get(capability_id)
    assert manifest is not None
    protocol = load_protocol_from_capability(manifest.to_public_dict()).to_dict()
    return {
        "protocol_source": "capability_manifest",
        "stop_signal_policy": protocol["stop_signal_policy"],
        "capability_protocols": [protocol],
    }


def test_code_workflow_writer_cannot_claim_success_when_tests_fail() -> None:
    state = {
        "domain_workflow": {"graph_mode": "code_development"},
        "execution_log": [
            {
                "step_id": "test-runner",
                "status": "failed",
                "tool_calls": [{"result": {"ok": False, "error": "1 failed"}}],
            }
        ],
    }

    guarded = apply_writer_guardrails("已经修复完成，通过测试。", state)

    assert guarded.startswith("# Code Workflow Guardrail Report")
    assert "Test Gate" in guarded
    assert "legacy_graph_mode_writer_fallback" in guarded


def test_protocol_code_workflow_gate_uses_declared_stop_policy() -> None:
    state = {
        "domain_workflow": {
            "workflow_id": "code-development",
            "graph_mode": "code_development",
            "gate_status": {"blocked": True, "status": "reject_patch", "blocking_gates": ["test_runner"]},
        },
        "metadata": {
            "os_plan": {
                "swarm_plan": {
                    "stop_signal_policy": {
                        "action_markers": [
                            {
                                "action": "writer:claim_tests_passed",
                                "phrases": ["successfully fixed", "tests passed"],
                            }
                        ],
                        "rules": [
                            {
                                "id": "test_gate_blocks_patch_acceptance_claims",
                                "trigger_targets": ["gate:code_test_gate"],
                                "blocked_actions": ["writer:claim_tests_passed"],
                            }
                        ]
                    }
                }
            }
        },
    }

    guarded = apply_writer_guardrails("successfully fixed; tests passed", state)

    assert guarded.startswith("# Stop-Signal Action Policy Guardrail Report")
    assert "Code Workflow Guardrail Report" not in guarded
    assert "legacy_graph_mode_writer_fallback" not in guarded
    assert "writer:claim_tests_passed" in guarded


@pytest.mark.parametrize(
    ("capability_id", "graph_mode", "target", "draft"),
    [
        ("code-development", "code_development", "gate:code_test_gate", "successfully fixed; tests passed"),
        ("compliance-workflow", "compliance_workflow", "decision:compliance_approval", "send the email"),
        ("evidence-research", "evidence_research", "gate:research_evidence_gate", "This definitively proves that the claim is true."),
    ],
)
def test_builtin_workflow_guardrails_use_manifest_declared_stop_policy_before_legacy_fallback(
    capability_id: str,
    graph_mode: str,
    target: str,
    draft: str,
) -> None:
    state = {
        "domain_workflow": {
            "workflow_id": capability_id,
            "graph_mode": graph_mode,
            "gate_status": {"blocked": True, "status": "blocked", "blocking_gates": ["declared_gate"]},
        },
        "metadata": {"os_plan": {"swarm_plan": swarm_plan_for_capability(capability_id)}},
        "final": draft,
    }

    guarded = apply_writer_guardrails(draft, state)
    trace = build_policing_trace(state, [])

    assert guarded.startswith("# Stop-Signal Action Policy Guardrail Report")
    assert "legacy_graph_mode_writer_fallback" not in guarded
    assert "Workflow Guardrail Report" not in guarded
    assert trace["violations"][0]["type"] == "domain_workflow_violation"
    assert trace["violations"][0]["target"] == target
    assert "source" not in trace["violations"][0]


def test_compliance_workflow_blocks_external_action_without_approval() -> None:
    state = {"domain_workflow": {"graph_mode": "compliance_workflow"}}

    guarded = apply_writer_guardrails("可以发送给外部客户。", state)

    assert guarded.startswith("# Compliance Workflow Guardrail Report")
    assert "human approval" in guarded
    assert "legacy_graph_mode_writer_fallback" in guarded


def test_compliance_workflow_allows_external_action_when_approval_recorded() -> None:
    state = {"domain_workflow": {"graph_mode": "compliance_workflow", "approval": {"status": "approved"}}}

    guarded = apply_writer_guardrails("可以发送给外部客户。", state)

    assert guarded == "可以发送给外部客户。"


def test_evidence_research_blocks_strong_claim_with_evidence_gaps() -> None:
    state = {
        "domain_workflow": {"graph_mode": "evidence_research"},
        "research_brief": {"evidence_gaps": ["missing primary source"]},
    }

    guarded = apply_writer_guardrails("This definitively proves that the claim is true.", state)

    assert guarded.startswith("# Evidence Research Guardrail Report")
    assert "missing primary source" in guarded
    assert "legacy_graph_mode_writer_fallback" in guarded


def test_final_judge_uses_same_domain_workflow_guardrails() -> None:
    state = {
        "domain_workflow": {"graph_mode": "code_development"},
        "execution_log": [
            {
                "step_id": "test-runner",
                "status": "failed",
                "tool_calls": [{"result": {"ok": False}}],
            }
        ],
    }

    guarded = apply_final_judge_guardrails("successfully fixed; tests passed", state)

    assert guarded.startswith("# Code Workflow Guardrail Report")
