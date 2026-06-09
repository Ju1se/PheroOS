from __future__ import annotations


def build_workflow_descriptor() -> dict:
    return {
        "workflow_id": "compliance-workflow",
        "graph_mode": "compliance_workflow",
        "graph_nodes": ["memory_agent", "executor", "research_agent", "critic", "writer", "final_judge"],
        "orchestration_entrypoint": "workflow.py:augment_orchestration_result",
        "execution_entrypoint": "workflow.py:augment_execution_result",
        "node_entrypoints": {
            "research_agent": "workflow.py:research_agent_node",
        },
        "ordered_nodes": [
            "policy_interpreter",
            "clause_obligation_extractor",
            "dlp_privacy_auditor",
            "rbac_access_control",
            "approval_coordinator",
            "case_evidence_steward",
            "risk_escalation",
            "records_retention",
            "human_in_loop",
        ],
        "node_policy": {
            "executor": {"required": True},
            "research_agent": {"required": True},
            "critic": {"required": True},
            "final_judge": {"required": True},
        },
        "required_gates": ["dlp_gate", "rbac_gate", "approval_gate", "policy_evidence_gate"],
        "writer_policy": "Final memo must link each compliance finding to policy or evidence and redact sensitive spans.",
    }


def augment_orchestration_result(state: dict, result: dict, workflow: dict) -> dict:
    from runtime.workflows.compliance_workflow import augment_orchestration_result as augment

    return augment(state, result, workflow=workflow)


def augment_execution_result(state: dict, result: dict, workflow: dict) -> dict:
    from runtime.workflows.compliance_workflow import attach_compliance_node_outputs

    return attach_compliance_node_outputs(state, result)


async def research_agent_node(runtime, state: dict, workflow: dict | None = None, node: str = "research_agent") -> dict:
    from runtime.workflows.compliance_workflow import research_agent_node as delegate

    result = await delegate(runtime, state)
    return {
        **result,
        "workflow_node_trace": [
            *list(result.get("workflow_node_trace") or []),
            {
                "capability_id": "compliance-workflow",
                "node": node,
                "source": "capability_workflow_node_entrypoint",
                "entrypoint": "workflow.py:research_agent_node",
            },
        ],
    }
