from __future__ import annotations

import importlib
from typing import Any


LEGACY_ORCHESTRATION_FALLBACKS = {
    "code_development": ("runtime.workflows.code_development", "augment_orchestration_result"),
    "compliance_workflow": ("runtime.workflows.compliance_workflow", "augment_orchestration_result"),
    "evidence_research": ("runtime.workflows.evidence_research", "augment_orchestration_result"),
}

LEGACY_EXECUTION_FALLBACKS = {
    "code_development": ("runtime.workflows.code_development", "augment_execution_result"),
    "evidence_research": ("runtime.workflows.evidence_research", "augment_execution_result"),
}
LEGACY_BUILTIN_GRAPH_MODES = {"investment_committee"}


def legacy_workflow_handler(graph_mode: str, *, kind: str) -> Any | None:
    fallbacks = LEGACY_ORCHESTRATION_FALLBACKS if kind == "orchestration" else LEGACY_EXECUTION_FALLBACKS
    spec = fallbacks.get(graph_mode)
    if spec is None:
        return None
    module_name, function_name = spec
    return getattr(importlib.import_module(module_name), function_name)


def legacy_builtin_graph_mode(graph_mode: str) -> bool:
    return graph_mode in LEGACY_BUILTIN_GRAPH_MODES
