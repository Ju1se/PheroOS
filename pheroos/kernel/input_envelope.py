from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class InputEnvelope:
    request: str
    tenant_id: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized_request(self) -> str:
        return " ".join(self.request.split())
