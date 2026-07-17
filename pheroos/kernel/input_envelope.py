from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pheroos._immutable import freeze_abi_value


@dataclass(frozen=True)
class InputEnvelope:
    request: str
    tenant_id: str = "default"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", freeze_abi_value(self.metadata))

    def normalized_request(self) -> str:
        return " ".join(self.request.split())
