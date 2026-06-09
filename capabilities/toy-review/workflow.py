from __future__ import annotations


def build_workflow_descriptor() -> dict:
    return {
        "id": "toy-review",
        "graph_mode": "toy_review",
        "ordered_nodes": [
            "toy_scout",
            "toy_evidence_gate",
            "toy_reviewer",
            "quorum",
            "writer",
            "final_judge",
        ],
        "required_protocols": ["recovery", "quorum", "stop_signal", "output_policy"],
        "writer_contract": "Writer must preserve required toy caveats and the committed candidate.",
        "node_policy": {
            "toy_scout": {"required": True},
            "toy_evidence_gate": {"required": True},
            "toy_reviewer": {"required": True},
        },
        "node_entrypoints": {
            "toy_scout": "workflow.py:toy_scout_node",
            "toy_evidence_gate": "workflow.py:toy_evidence_gate_node",
            "toy_reviewer": "workflow.py:toy_reviewer_node",
        },
    }


def toy_scout_node(state: dict, result: dict, workflow: dict, node: str) -> dict:
    evidence = toy_evidence_state(state)
    return {
        "status": "completed",
        "evidence_available": evidence["available"],
        "candidate_count": evidence["candidate_count"],
        "full_text_count": evidence["full_text_count"],
        "claim_type": "toy_claim",
    }


def toy_evidence_gate_node(state: dict, result: dict, workflow: dict, node: str) -> dict:
    evidence = toy_evidence_state(state)
    passed = evidence["available"] or bool(state.get("toy_review", {}).get("evidence_gate_passed"))
    return {
        "status": "passed" if passed else "blocked",
        "blocking": not passed,
        "target": "gate:toy_evidence_gate",
        "reason": "Toy evidence available." if passed else "Toy evidence is missing.",
    }


def toy_reviewer_node(state: dict, result: dict, workflow: dict, node: str) -> dict:
    evidence = toy_evidence_state(state)
    return {
        "status": "reviewed",
        "recommended_candidate": "candidate:toy:approve" if evidence["available"] else "candidate:toy:insufficient_evidence",
        "required_caveats": ["Toy evidence is limited."],
    }


async def toy_async_reviewer_node(state: dict, result: dict, workflow: dict, node: str) -> dict:
    evidence = toy_evidence_state(state)
    return {
        "status": "async_reviewed",
        "recommended_candidate": "candidate:toy:approve" if evidence["available"] else "candidate:toy:insufficient_evidence",
        "required_caveats": ["Toy async evidence is limited."],
    }


def toy_evidence_state(state: dict) -> dict:
    context = state.get("recovery_context") if isinstance(state.get("recovery_context"), dict) else {}
    candidate_count = int(context.get("candidate_count") or 0)
    full_text_count = int(context.get("full_text_count") or 0)
    return {
        "candidate_count": candidate_count,
        "full_text_count": full_text_count,
        "available": full_text_count > 0 or bool(state.get("toy_review", {}).get("evidence_gate_passed")),
    }
