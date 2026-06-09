from __future__ import annotations


def build_workflow_descriptor() -> dict:
    return {
        "workflow_id": "code-development",
        "graph_mode": "code_development",
        "graph_nodes": ["memory_agent", "executor", "critic", "writer", "final_judge"],
        "orchestration_entrypoint": "workflow.py:augment_orchestration_result",
        "execution_entrypoint": "workflow.py:augment_execution_result",
        "ordered_nodes": [
            "repo_scout",
            "architecture_mapper",
            "patch_planner",
            "coder",
            "diff_gate",
            "test_runner",
            "interface_guard",
            "security_scanner",
            "dependency_auditor",
            "code_reviewer",
            "regression_judge",
            "docs_changelog",
        ],
        "node_policy": {
            "executor": {"required": True},
            "critic": {"required": True},
            "final_judge": {"required": True},
        },
        "required_gates": ["diff_gate", "test_gate", "interface_gate", "security_gate", "dependency_gate"],
        "committed_candidates": ["accept_patch", "revise_patch", "reject_patch", "insufficient_context"],
        "writer_policy": "Writer may summarize only patch, diff, and test evidence accepted by regression_judge.",
    }


def augment_orchestration_result(state: dict, result: dict, workflow: dict) -> dict:
    from runtime.workflows.code_development import augment_orchestration_result as augment

    return augment(state, result, workflow=workflow)


def augment_execution_result(state: dict, result: dict, workflow: dict) -> dict:
    from runtime.workflows.code_development import augment_execution_result as augment

    return augment(state, result)
