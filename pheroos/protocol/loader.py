from __future__ import annotations

import json
import math
from pathlib import Path

from pheroos.protocol.manifest import capability_manifest_from_dict
from pheroos.protocol.models import CapabilityManifest


def load_capability_manifest(path: str | Path) -> CapabilityManifest:
    manifest_path = Path(path)
    payload = json.loads(
        manifest_path.read_text(encoding="utf-8"),
        parse_constant=reject_non_finite_json_constant,
        parse_float=parse_finite_json_float,
        object_pairs_hook=reject_duplicate_json_object_keys,
    )
    if not isinstance(payload, dict):
        raise ValueError("capability manifest must be a JSON object")
    return capability_manifest_from_dict(payload)


def reject_non_finite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def parse_finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON number is not allowed: {value}")
    return parsed


def reject_duplicate_json_object_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"duplicate JSON object key is not allowed: {key}")
        payload[key] = value
    return payload
