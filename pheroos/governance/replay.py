from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from pheroos.governance._commit_validation import require_commit_step
from pheroos.governance.challenge import (
    VerifiedChallenge,
    verified_challenge_fingerprint,
    verified_challenge_is_authoritative,
)
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.commit_state import (
    CommitReplayState,
    ReplayNamespace,
    ReplayReceipt,
    commit_replay_state_is_current,
    record_commit_replay_receipts,
    replay_receipt_fingerprint,
)
from pheroos.governance.errors import GovernanceError
from pheroos.governance.observation import (
    CounterevidenceDisposition,
    VerifiedObservation,
    counterevidence_disposition_fingerprint,
    counterevidence_disposition_is_authoritative,
    verified_observation_fingerprint,
    verified_observation_is_authoritative,
)

_ReplayInputT = TypeVar("_ReplayInputT")


def observation_replay_receipt(
    observation: VerifiedObservation,
) -> ReplayReceipt:
    """Project one governance-issued observation into the central replay ABI."""
    if not verified_observation_is_authoritative(observation):
        raise GovernanceError(
            "observation replay receipt requires authoritative, tamper-evident input"
        )
    return ReplayReceipt(
        namespace=ReplayNamespace.OBSERVATION,
        record_id=observation.observation_id,
        nonce=observation.nonce,
        payload_fingerprint=verified_observation_fingerprint(observation),
        target=observation.target,
        candidate_id=observation.candidate_id,
        epoch=observation.epoch,
        principal_id=observation.principal_id,
    )


def challenge_replay_receipt(challenge: VerifiedChallenge) -> ReplayReceipt:
    """Project one governance-issued challenge into the central replay ABI."""
    if not verified_challenge_is_authoritative(challenge):
        raise GovernanceError(
            "challenge replay receipt requires authoritative, tamper-evident input"
        )
    return ReplayReceipt(
        namespace=ReplayNamespace.CHALLENGE,
        record_id=challenge.challenge_id,
        nonce=challenge.nonce,
        payload_fingerprint=verified_challenge_fingerprint(challenge),
        target=challenge.target,
        candidate_id=challenge.candidate_id,
        epoch=challenge.epoch,
        principal_id=challenge.principal_id,
    )


def counterevidence_disposition_replay_receipt(
    disposition: CounterevidenceDisposition,
) -> ReplayReceipt:
    """Project a disposition using an ID-derived nonce it does not carry itself."""
    if not counterevidence_disposition_is_authoritative(disposition):
        raise GovernanceError(
            "counterevidence disposition replay receipt requires authoritative, "
            "tamper-evident input"
        )
    return ReplayReceipt(
        namespace=ReplayNamespace.COUNTEREVIDENCE_DISPOSITION,
        record_id=disposition.disposition_id,
        nonce=_disposition_replay_nonce(disposition.disposition_id),
        payload_fingerprint=counterevidence_disposition_fingerprint(disposition),
        target=disposition.target,
        candidate_id=disposition.candidate_id,
        epoch=disposition.epoch,
        principal_id=disposition.verifier_id,
    )


def record_evidence_replay_inputs(
    state: CommitReplayState,
    *,
    observations: Sequence[VerifiedObservation],
    challenges: Sequence[VerifiedChallenge],
    dispositions: Sequence[CounterevidenceDisposition],
    current_step: int,
) -> CommitReplayState:
    """Atomically append canonical evidence receipts to the authoritative replay head."""
    current = _require_current_state(state, current_step=current_step)
    receipts = _evidence_replay_receipts(
        state,
        observations=observations,
        challenges=challenges,
        dispositions=dispositions,
        current_step=current,
    )
    return record_commit_replay_receipts(
        state,
        current_step=current,
        receipts=receipts,
    )


def missing_evidence_replay_input_refs(
    state: CommitReplayState,
    *,
    observations: Sequence[VerifiedObservation],
    challenges: Sequence[VerifiedChallenge],
    dispositions: Sequence[CounterevidenceDisposition],
    current_step: int,
) -> tuple[str, ...]:
    """Return canonical record fingerprints absent from the current replay head."""
    current = _require_current_state(state, current_step=current_step)
    receipts = _evidence_replay_receipts(
        state,
        observations=observations,
        challenges=challenges,
        dispositions=dispositions,
        current_step=current,
    )
    recorded = set(state.receipts)
    return tuple(
        sorted(
            receipt.payload_fingerprint
            for receipt in receipts
            if receipt not in recorded
        )
    )


def evidence_replay_inputs_are_recorded(
    state: CommitReplayState,
    *,
    observations: Sequence[VerifiedObservation],
    challenges: Sequence[VerifiedChallenge],
    dispositions: Sequence[CounterevidenceDisposition],
    current_step: int,
) -> bool:
    """Prove that every supplied evidence authority record is in the current head."""
    return not missing_evidence_replay_input_refs(
        state,
        observations=observations,
        challenges=challenges,
        dispositions=dispositions,
        current_step=current_step,
    )


def _evidence_replay_receipts(
    state: CommitReplayState,
    *,
    observations: Sequence[VerifiedObservation],
    challenges: Sequence[VerifiedChallenge],
    dispositions: Sequence[CounterevidenceDisposition],
    current_step: int,
) -> tuple[ReplayReceipt, ...]:
    normalized_observations = _require_sequence(observations, "observations")
    normalized_challenges = _require_sequence(challenges, "challenges")
    normalized_dispositions = _require_sequence(dispositions, "dispositions")

    receipts: list[ReplayReceipt] = []
    for observation in normalized_observations:
        receipt = observation_replay_receipt(observation)
        _require_record_binding(
            state,
            record=observation,
            receipt=receipt,
            principal_id=observation.principal_id,
            issued_at_step=observation.verified_at_step,
            expires_at_step=observation.expires_at_step,
            current_step=current_step,
            field_name="observation",
        )
        receipts.append(receipt)
    for challenge in normalized_challenges:
        receipt = challenge_replay_receipt(challenge)
        _require_record_binding(
            state,
            record=challenge,
            receipt=receipt,
            principal_id=challenge.principal_id,
            issued_at_step=challenge.verified_at_step,
            expires_at_step=challenge.expires_at_step,
            current_step=current_step,
            field_name="challenge",
        )
        receipts.append(receipt)
    for disposition in normalized_dispositions:
        receipt = counterevidence_disposition_replay_receipt(disposition)
        _require_record_binding(
            state,
            record=disposition,
            receipt=receipt,
            principal_id=disposition.verifier_id,
            issued_at_step=disposition.issued_at_step,
            expires_at_step=disposition.expires_at_step,
            current_step=current_step,
            field_name="counterevidence disposition",
        )
        receipts.append(receipt)

    return _canonical_safe_receipts(
        receipts,
        profile=state.profile,
    )


def _require_current_state(state: object, *, current_step: object) -> int:
    if not commit_replay_state_is_current(state):
        raise GovernanceError("evidence replay requires the current authoritative head")
    assert type(state) is CommitReplayState
    current = require_commit_step(current_step, "evidence replay current_step")
    if current < state.current_step:
        raise GovernanceError("evidence replay step cannot move backwards")
    return current


def _require_record_binding(
    state: CommitReplayState,
    *,
    record: object,
    receipt: ReplayReceipt,
    principal_id: str,
    issued_at_step: int,
    expires_at_step: int,
    current_step: int,
    field_name: str,
) -> None:
    if not (
        getattr(record, "profile", None) == state.profile
        and getattr(record, "assurance", None) is state.assurance
        and getattr(record, "manifest_root", None) == state.manifest_root
        and getattr(record, "commit_policy_root", None) == state.commit_policy_root
        and getattr(record, "protocol_id", None) == state.protocol_id
        and getattr(record, "run_id", None) == state.run_id
    ):
        raise GovernanceError(
            f"{field_name} replay binding does not match the authoritative head"
        )
    if not (
        receipt.target == getattr(record, "target", None)
        and receipt.candidate_id == getattr(record, "candidate_id", None)
        and receipt.epoch == getattr(record, "epoch", None)
        and receipt.principal_id == principal_id
    ):
        raise GovernanceError(f"{field_name} replay receipt binding is incomplete")
    if not issued_at_step <= current_step < expires_at_step:
        raise GovernanceError(f"{field_name} replay input is not fresh")


def _require_sequence(
    values: Sequence[_ReplayInputT],
    field_name: str,
) -> tuple[_ReplayInputT, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(
        values,
        Sequence,
    ):
        raise GovernanceError(f"evidence replay {field_name} must be a sequence")
    return tuple(values)


def _canonical_safe_receipts(
    receipts: Sequence[ReplayReceipt],
    *,
    profile: str,
) -> tuple[ReplayReceipt, ...]:
    canonical = tuple(
        sorted(
            set(receipts),
            key=lambda receipt: replay_receipt_fingerprint(
                receipt,
                profile=profile,
            ),
        )
    )
    by_nonce: dict[str, ReplayReceipt] = {}
    by_id: dict[tuple[ReplayNamespace, str], ReplayReceipt] = {}
    by_payload: dict[str, ReplayReceipt] = {}
    for receipt in canonical:
        for existing in (
            by_nonce.get(receipt.nonce),
            by_id.get((receipt.namespace, receipt.record_id)),
            by_payload.get(receipt.payload_fingerprint),
        ):
            if existing is not None and existing != receipt:
                raise GovernanceError(
                    "evidence replay input collision is a safety violation"
                )
        by_nonce[receipt.nonce] = receipt
        by_id[(receipt.namespace, receipt.record_id)] = receipt
        by_payload[receipt.payload_fingerprint] = receipt
    return canonical


def _disposition_replay_nonce(disposition_id: str) -> str:
    return commit_payload_fingerprint(
        {
            "namespace": ReplayNamespace.COUNTEREVIDENCE_DISPOSITION,
            "record_id": disposition_id,
        },
        schema="pheroos-counterevidence-disposition-replay-nonce-v1",
        profile="pheroos-commit-integrity-v1",
    )


__all__ = [
    "challenge_replay_receipt",
    "counterevidence_disposition_replay_receipt",
    "evidence_replay_inputs_are_recorded",
    "missing_evidence_replay_input_refs",
    "observation_replay_receipt",
    "record_evidence_replay_inputs",
]
