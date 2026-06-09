from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class WorkflowDescriptor:
    id: str
    graph_mode: str
    ordered_nodes: list[str]
    required_protocols: list[str]
    capability_id: str | None = None
    entrypoint: str | None = None
    writer_contract: str | None = None
    orchestration_entrypoint: str | None = None
    execution_entrypoint: str | None = None
    metric_registry_entrypoint: str | None = None
    node_policy: dict[str, dict[str, Any]] | None = None
    node_entrypoints: dict[str, str] | None = None
    plan_entrypoints: dict[str, str] | None = None
    data_contract: dict[str, Any] | None = None
    evidence_adapter: dict[str, Any] | None = None
    output_contract: dict[str, Any] | None = None
    runtime_support: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkflowDescriptor":
        return cls(
            id=str(payload.get("id") or ""),
            graph_mode=str(payload.get("graph_mode") or ""),
            ordered_nodes=[str(item) for item in payload.get("ordered_nodes") or []],
            required_protocols=[str(item) for item in payload.get("required_protocols") or []],
            capability_id=str(payload.get("capability_id") or "") or None,
            entrypoint=str(payload.get("entrypoint") or "") or None,
            writer_contract=str(payload.get("writer_contract") or "") or None,
            orchestration_entrypoint=str(payload.get("orchestration_entrypoint") or "") or None,
            execution_entrypoint=str(payload.get("execution_entrypoint") or "") or None,
            metric_registry_entrypoint=str(payload.get("metric_registry_entrypoint") or "") or None,
            node_policy=normalize_node_policy(payload.get("node_policy")),
            node_entrypoints=normalize_node_entrypoints(payload.get("node_entrypoints")),
            plan_entrypoints=normalize_node_entrypoints(payload.get("plan_entrypoints")),
            data_contract=normalize_descriptor(payload.get("data_contract")),
            evidence_adapter=normalize_descriptor(payload.get("evidence_adapter")),
            output_contract=normalize_descriptor(payload.get("output_contract")),
            runtime_support=normalize_descriptor(payload.get("runtime_support")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "graph_mode": self.graph_mode,
            "ordered_nodes": self.ordered_nodes,
            "required_protocols": self.required_protocols,
            "capability_id": self.capability_id,
            "entrypoint": self.entrypoint,
            "writer_contract": self.writer_contract,
            "orchestration_entrypoint": self.orchestration_entrypoint,
            "execution_entrypoint": self.execution_entrypoint,
            "metric_registry_entrypoint": self.metric_registry_entrypoint,
            "node_policy": self.node_policy or {},
            "node_entrypoints": self.node_entrypoints or {},
            "plan_entrypoints": self.plan_entrypoints or {},
            "data_contract": self.data_contract or {},
            "evidence_adapter": self.evidence_adapter or {},
            "output_contract": self.output_contract or {},
            "runtime_support": self.runtime_support or {},
        }


def normalize_node_policy(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, dict[str, Any]] = {}
    for key, item in value.items():
        if not isinstance(item, dict):
            continue
        output[str(key)] = {str(item_key): item_value for item_key, item_value in item.items()}
    return output


def normalize_node_entrypoints(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, str] = {}
    for key, item in value.items():
        node = str(key).strip()
        entrypoint = str(item).strip()
        if node and entrypoint:
            output[node] = entrypoint
    return output


def normalize_descriptor(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


class CapabilityWorkflow(Protocol):
    capability_id: str

    def build_nodes(self, runtime_context: Any, protocol_manifest: Any) -> list[dict[str, Any]]:
        ...

    def initial_artifacts(self, input_envelope: Any, runtime_context: Any) -> dict[str, Any]:
        ...

    def data_contract(self) -> dict[str, Any]:
        ...

    def evidence_adapter(self) -> dict[str, Any]:
        ...

    def output_contract(self) -> dict[str, Any]:
        ...

    def declared_candidates(self) -> list[dict[str, Any]]:
        ...

    def declared_recovery_protocols(self) -> list[dict[str, Any]]:
        ...
