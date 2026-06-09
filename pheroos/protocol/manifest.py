from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.capability_registry import load_manifest
from runtime.swarm.protocol_loader import load_protocol_from_capability


@dataclass(frozen=True)
class LoadedProtocol:
    capability_id: str
    protocol: dict[str, Any]
    diagnostics: list[dict[str, Any]]
    source_path: str | None = None

    @property
    def ok(self) -> bool:
        return not any(item.get("severity") == "error" for item in self.diagnostics)


def load_capability_protocol(path: str | Path) -> LoadedProtocol:
    manifest_path = Path(path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / "capability.json"
    manifest = load_manifest(manifest_path)
    protocol = load_protocol_from_capability(manifest.to_public_dict())
    return LoadedProtocol(
        capability_id=manifest.id,
        protocol=protocol.to_dict(),
        diagnostics=[dict(item) for item in protocol.validation_diagnostics],
        source_path=str(manifest_path),
    )
