from __future__ import annotations

from copy import deepcopy
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(deepcopy(self.nodes)))
        object.__setattr__(self, "edges", tuple(deepcopy(self.edges)))

    def has_evidence(self) -> bool:
        if not self.nodes or any(
            not isinstance(node, EvidenceNode) for node in self.nodes
        ):
            return False
        identifiers = [node.id for node in self.nodes]
        return all(
            isinstance(node.id, str)
            and bool(node.id.strip())
            and isinstance(node.content, str)
            and bool(node.content.strip())
            for node in self.nodes
        ) and len(set(identifiers)) == len(identifiers)

    def has_provenance(self) -> bool:
        return bool(self.nodes) and all(
            isinstance(node, EvidenceNode)
            and isinstance(node.provenance, str)
            and bool(node.provenance.strip())
            for node in self.nodes
        )
