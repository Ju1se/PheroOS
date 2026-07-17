from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from pheroos.governance.errors import GovernanceError


def canonical_replay_receipts(
    receipts: Sequence[Any],
    *,
    receipt_type: type,
    validate_receipt: Callable[[Any], None],
    receipt_fingerprint: Callable[..., str],
) -> tuple[Any, ...]:
    if isinstance(receipts, (str, bytes, bytearray)):
        raise GovernanceError("replay receipts must be a sequence")
    normalized = tuple(receipts)
    if any(type(item) is not receipt_type for item in normalized):
        raise GovernanceError("replay receipts contain a non-canonical record")
    for item in normalized:
        validate_receipt(item)
    canonical = tuple(
        sorted(
            normalized,
            key=lambda item: receipt_fingerprint(
                item,
                profile="pheroos-commit-integrity-v1",
            ),
        )
    )
    if len(set(canonical)) != len(canonical):
        deduplicated: list[Any] = []
        seen: set[Any] = set()
        for item in canonical:
            if item not in seen:
                seen.add(item)
                deduplicated.append(item)
        canonical = tuple(deduplicated)
    by_nonce: dict[str, Any] = {}
    by_id: dict[tuple[Any, str], Any] = {}
    by_payload: dict[str, Any] = {}
    for item in canonical:
        for existing in (
            by_nonce.get(item.nonce),
            by_id.get((item.namespace, item.record_id)),
            by_payload.get(item.payload_fingerprint),
        ):
            if existing is not None and existing != item:
                raise GovernanceError("replay receipt set contains a safety collision")
        by_nonce[item.nonce] = item
        by_id[(item.namespace, item.record_id)] = item
        by_payload[item.payload_fingerprint] = item
    return canonical
