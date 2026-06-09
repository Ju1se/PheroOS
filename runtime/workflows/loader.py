from __future__ import annotations

from typing import Any

from runtime.capability_runtime import load_capability_runtime_descriptors
from runtime.capability_registry import CapabilityManifest
from runtime.workflows.base import WorkflowDescriptor


def load_workflow_descriptors(manifests: list[CapabilityManifest]) -> dict[str, Any]:
    runtime = load_capability_runtime_descriptors(manifests)
    workflows: dict[str, dict[str, Any]] = {}
    for capability_id, descriptor in runtime.get("capabilities", {}).items():
        entrypoints = descriptor.get("entrypoints") if isinstance(descriptor, dict) else {}
        workflow_payload = entrypoints.get("workflow") if isinstance(entrypoints, dict) else None
        if isinstance(workflow_payload, dict):
            workflows[capability_id] = WorkflowDescriptor.from_dict(workflow_payload).to_dict()
    return {"workflows": workflows, "diagnostics": runtime.get("diagnostics", [])}
