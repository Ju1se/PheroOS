from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
from math import isfinite
from numbers import Real
from typing import Any

from pheroos._digest import is_canonical_sha256_fingerprint
from pheroos.trace._lineage_types import PHEROMONE_CLIP_PAYLOAD_VERSION


def canonical_pheromone_clip_payload(payload: Mapping[str, Any]) -> str:
    """Return the versioned canonical JSON used to bind rejected clip inputs.

    The receipt is an integrity and replay-lineage binding, not evidence or
    authority.  Only provider-neutral JSON values are accepted, and all
    numeric leaves must be finite so the digest has one deterministic ABI
    interpretation.
    """

    normalized = _canonical_clip_payload_value(payload, path="causal_payload")
    if not isinstance(normalized, dict):
        raise TypeError("pheromone clip causal payload must be an object")
    envelope = {
        "payload": normalized,
        "version": PHEROMONE_CLIP_PAYLOAD_VERSION,
    }
    return json.dumps(
        envelope,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def pheromone_clip_payload_fingerprint(payload: Mapping[str, Any]) -> str:
    """Return the canonical SHA-256 receipt for one clip causal payload."""

    canonical = canonical_pheromone_clip_payload(payload)
    return "sha256:" + sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_clip_payload_value(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, Real):
        if not isfinite(float(value)):
            raise ValueError(f"{path} must contain only finite numbers")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise TypeError(f"{path} keys must be non-empty strings")
            if key in normalized:
                raise ValueError(f"{path} contains duplicate keys")
            normalized[key] = _canonical_clip_payload_value(
                item,
                path=f"{path}.{key}",
            )
        return normalized
    if isinstance(value, (list, tuple)):
        return [
            _canonical_clip_payload_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise TypeError(f"{path} contains unsupported value type: {type(value).__name__}")


def validate_processed_replay_receipts(event_type: str, value: Any) -> None:
    lifecycles = {"deposit", "diffusion", "feedback", "adjustment"}
    if not isinstance(value, dict) or set(value) != lifecycles:
        raise ValueError(
            f"{event_type} trace processed_replay_receipts must contain exactly "
            "deposit, diffusion, feedback, and adjustment"
        )
    seen_ids: set[str] = set()
    for lifecycle, receipts in value.items():
        if not isinstance(receipts, dict):
            raise ValueError(
                f"{event_type} trace processed_replay_receipts.{lifecycle} must be an object"
            )
        for trace_event_id, fingerprint in receipts.items():
            if not isinstance(trace_event_id, str) or not trace_event_id:
                raise ValueError(
                    f"{event_type} trace replay receipt ids must be non-empty strings"
                )
            if trace_event_id in seen_ids:
                raise ValueError(
                    f"{event_type} trace replay receipt ids must be unique across lifecycles"
                )
            seen_ids.add(trace_event_id)
            require_receipt_fingerprint(
                event_type,
                f"processed_replay_receipts.{lifecycle}.{trace_event_id}",
                fingerprint,
            )


def require_matching_replay_fingerprints(
    event_type: str,
    lineage: dict[str, Any],
) -> None:
    replay_payload = lineage.get("replay_payload")
    if not isinstance(replay_payload, (list, tuple)) or not replay_payload:
        raise ValueError(
            f"{event_type} replay lineage replay_payload must be a non-empty array"
        )
    for field_name in (
        "replay_payload_fingerprint",
        "processed_payload_fingerprint",
    ):
        if field_name not in lineage:
            raise ValueError(
                f"{event_type} replay lineage missing required field: {field_name}"
            )
        require_receipt_fingerprint(event_type, field_name, lineage[field_name])
    expected_fingerprint = pheromone_clip_payload_fingerprint(
        {
            "lifecycle": "replay_receipt",
            "receipt": replay_payload,
        }
    )
    if lineage["replay_payload_fingerprint"] != expected_fingerprint:
        raise ValueError(
            f"{event_type} replay payload fingerprint does not match replay_payload"
        )
    if (
        lineage["replay_payload_fingerprint"]
        != lineage["processed_payload_fingerprint"]
    ):
        raise ValueError(
            f"{event_type} replay payload does not match processed receipt"
        )


def require_receipt_fingerprint(
    event_type: str,
    field_name: str,
    value: Any,
) -> None:
    if not is_canonical_sha256_fingerprint(value):
        raise ValueError(
            f"{event_type} trace lineage {field_name} must be a sha256 fingerprint"
        )


# Public aliases keep their historical root identity even though implementation
# details are now split by rule family.
canonical_pheromone_clip_payload.__module__ = "pheroos.trace"
pheromone_clip_payload_fingerprint.__module__ = "pheroos.trace"


__all__: tuple[str, ...] = ()
