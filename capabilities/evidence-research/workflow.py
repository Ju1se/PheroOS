from __future__ import annotations


def build_workflow_descriptor() -> dict:
    return {
        "workflow_id": "evidence-research",
        "graph_mode": "evidence_research",
        "graph_nodes": ["executor", "research_agent", "critic", "writer", "final_judge"],
        "orchestration_entrypoint": "workflow.py:augment_orchestration_result",
        "execution_entrypoint": "workflow.py:augment_execution_result",
        "node_entrypoints": {
            "research_agent": "workflow.py:research_agent_node",
        },
        "ordered_nodes": [
            "claim_decomposition",
            "source_retrieval",
            "source_quality_rater",
            "literature_evidence_steward",
            "citation_auditor",
            "contradiction_mapper",
            "evidence_gate",
            "synthesis_writer",
        ],
        "node_policy": {
            "executor": {"required": True},
            "research_agent": {"required": True},
            "critic": {"required": True},
            "final_judge": {"required": True},
        },
        "required_gates": ["citation_gate", "claim_support_gate", "contradiction_gate"],
        "writer_policy": "Writer must separate facts, interpretations, estimates, and unresolved evidence gaps.",
    }


def augment_orchestration_result(state: dict, result: dict, workflow: dict) -> dict:
    from runtime.workflows.evidence_research import augment_orchestration_result as augment

    return augment(state, result, workflow=workflow)


def augment_execution_result(state: dict, result: dict, workflow: dict) -> dict:
    from runtime.workflows.evidence_research import augment_execution_result as augment

    return augment(state, result)


async def research_agent_node(runtime, state: dict, workflow: dict | None = None, node: str = "research_agent") -> dict:
    from runtime.workflows.evidence_research import research_agent_node as delegate

    result = await delegate(runtime, state)
    return {
        **result,
        "workflow_node_trace": [
            *list(result.get("workflow_node_trace") or []),
            {
                "capability_id": "evidence-research",
                "node": node,
                "source": "capability_workflow_node_entrypoint",
                "entrypoint": "workflow.py:research_agent_node",
            },
        ],
    }
