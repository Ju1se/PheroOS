from __future__ import annotations

import json
from pathlib import Path

from pheroos.protocol.manifest import capability_manifest_from_dict
from pheroos.protocol.models import CapabilityManifest


def load_capability_manifest(path: str | Path) -> CapabilityManifest:
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("capability manifest must be a JSON object")
    return capability_manifest_from_dict(payload)
