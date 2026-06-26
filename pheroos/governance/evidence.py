from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvidenceNode:
    id: str
    content: str
    provenance: str


@dataclass(frozen=True)
class EvidenceEdge:
    source: str
    target: str
    relation: str


@dataclass(frozen=True)
class EvidenceGraph:
    nodes: list[EvidenceNode] = field(default_factory=list)
    edges: list[EvidenceEdge] = field(default_factory=list)

    def has_evidence(self) -> bool:
        return bool(self.nodes)

    def has_provenance(self) -> bool:
        return all(bool(node.provenance) for node in self.nodes)
