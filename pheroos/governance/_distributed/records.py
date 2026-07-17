from __future__ import annotations

from threading import RLock


_PROPOSAL_ISSUANCE = object()
_WITNESS_VERIFICATION_ISSUANCE = object()
_DISTRIBUTED_STATE_ISSUANCE = object()
_FINALITY_DECISION_ISSUANCE = object()

_LEGACY_DISTRIBUTED_STATE_CURSORS = "legacy.distributed.state_cursors"
_LEGACY_WITNESS_VERIFICATIONS_BY_ID = "legacy.distributed.witness_by_id"
_LEGACY_WITNESS_VERIFICATIONS_BY_NONCE = "legacy.distributed.witness_by_nonce"
_LEGACY_PROPOSALS_BY_ID = "legacy.distributed.proposals_by_id"
_LEGACY_DISTRIBUTED_CERTIFICATES_BY_ID = "legacy.distributed.certificates_by_id"
_LEGACY_EPOCH_CERTIFICATES_BY_ID = "legacy.distributed.epoch_certificates_by_id"


class _DistributedStateCursor:
    __slots__ = (
        "authority_key",
        "base_fingerprint",
        "current_state",
        "current_state_fingerprint",
        "transitions",
        "lock",
    )

    def __init__(self, *, authority_key: str, base_fingerprint: str) -> None:
        self.authority_key = authority_key
        self.base_fingerprint = base_fingerprint
        self.current_state: object | None = None
        self.current_state_fingerprint = ""
        self.transitions: dict[
            str,
            tuple[str, object],
        ] = {}
        self.lock = RLock()
