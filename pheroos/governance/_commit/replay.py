from __future__ import annotations

from collections.abc import Sequence

from pheroos.governance._commit.records import (
    CandidateCommitInput,
    CommitEvaluationContext,
)
from pheroos.governance._commit_state.records import ReplayNamespace, ReplayReceipt
from pheroos.governance._support.lease import (
    support_lease_is_authoritative,
    support_lease_revocation_is_authoritative,
)
from pheroos.governance._support.records import (
    SupportLease,
    SupportLeaseRevocation,
    support_lease_fingerprint,
    support_lease_revocation_fingerprint,
)
from pheroos.governance.challenge import verified_challenge_fingerprint
from pheroos.governance.commit_numeric import commit_payload_fingerprint
from pheroos.governance.errors import GovernanceError
from pheroos.governance.replay import (
    challenge_replay_receipt,
    counterevidence_disposition_replay_receipt,
    observation_replay_receipt,
)


_COMMIT_INPUT_REPLAY_NAMESPACES = frozenset(
    {
        ReplayNamespace.OBSERVATION,
        ReplayNamespace.CHALLENGE,
        ReplayNamespace.COUNTEREVIDENCE_DISPOSITION,
        ReplayNamespace.SUPPORT_LEASE,
        ReplayNamespace.SUPPORT_REVOCATION,
    }
)


def build_commit_replay_receipts(
    candidate_inputs: Sequence[CandidateCommitInput],
    leases: Sequence[SupportLease],
    revocations: Sequence[SupportLeaseRevocation] = (),
) -> tuple[ReplayReceipt, ...]:
    receipts: list[ReplayReceipt] = []
    for candidate_input in tuple(candidate_inputs):
        if type(candidate_input) is not CandidateCommitInput:
            raise GovernanceError(
                "commit replay receipt construction requires candidate inputs"
            )
        for observation in (
            *candidate_input.positive_observations,
            *candidate_input.counter_observations,
        ):
            receipts.append(observation_replay_receipt(observation))
        for challenge in candidate_input.challenges:
            receipts.append(challenge_replay_receipt(challenge))
        for disposition in candidate_input.dispositions:
            receipts.append(counterevidence_disposition_replay_receipt(disposition))
    for lease in tuple(leases):
        if type(lease) is not SupportLease:
            raise GovernanceError(
                "commit replay receipt construction requires canonical leases"
            )
        receipts.append(_support_lease_commit_replay_receipt(lease))
    for revocation in tuple(revocations):
        receipts.append(_support_revocation_commit_replay_receipt(revocation))
    return tuple(
        sorted(
            receipts,
            key=lambda item: (
                item.namespace.value,
                item.record_id,
                item.nonce,
                item.payload_fingerprint,
            ),
        )
    )


def _support_lease_commit_replay_receipt(
    lease: SupportLease,
) -> ReplayReceipt:
    if not support_lease_is_authoritative(lease):
        raise GovernanceError(
            "support lease replay receipt requires authoritative input"
        )
    return ReplayReceipt(
        namespace=ReplayNamespace.SUPPORT_LEASE,
        record_id=lease.lease_id,
        nonce=lease.nonce,
        payload_fingerprint=support_lease_fingerprint(lease),
        target=lease.target,
        candidate_id=lease.candidate_id,
        epoch=lease.epoch,
        principal_id=lease.principal_id,
    )


def _scoped_commit_input_receipts(
    context: CommitEvaluationContext,
    receipts: Sequence[ReplayReceipt],
) -> tuple[ReplayReceipt, ...]:
    substantive = set(context.substantive_candidate_ids)
    scoped = tuple(
        receipt
        for receipt in receipts
        if receipt.namespace in _COMMIT_INPUT_REPLAY_NAMESPACES
        and receipt.target == context.target
        and receipt.epoch == context.epoch
        and receipt.candidate_id in substantive
    )
    return tuple(
        sorted(
            set(scoped),
            key=lambda receipt: (
                receipt.namespace.value,
                receipt.record_id,
                receipt.nonce,
                receipt.payload_fingerprint,
            ),
        )
    )


def _support_revocation_commit_replay_receipt(
    revocation: SupportLeaseRevocation,
) -> ReplayReceipt:
    if not support_lease_revocation_is_authoritative(revocation):
        raise GovernanceError(
            "support revocation replay receipt requires authoritative input"
        )
    return ReplayReceipt(
        namespace=ReplayNamespace.SUPPORT_REVOCATION,
        record_id=revocation.revocation_id,
        nonce=commit_payload_fingerprint(
            {
                "namespace": ReplayNamespace.SUPPORT_REVOCATION,
                "record_id": revocation.revocation_id,
            },
            schema="pheroos-support-revocation-replay-nonce-v1",
            profile=revocation.profile,
        ),
        payload_fingerprint=support_lease_revocation_fingerprint(revocation),
        target=revocation.target,
        candidate_id=revocation.candidate_id,
        epoch=revocation.epoch,
        principal_id=revocation.principal_id,
    )


def _cross_record_replay_conflicts(
    candidate_inputs: Sequence[CandidateCommitInput],
    receipts: Sequence[ReplayReceipt],
) -> tuple[str, ...]:
    challenge_executions: list[tuple[str, str, str]] = []
    for item in candidate_inputs:
        for challenge in item.challenges:
            fingerprint = verified_challenge_fingerprint(challenge)
            challenge_executions.append(
                (
                    challenge.execution_attestation_ref,
                    challenge.execution_fingerprint,
                    fingerprint,
                )
            )
    conflicts: set[str] = set()
    by_nonce: dict[str, ReplayReceipt] = {}
    by_id: dict[tuple[ReplayNamespace, str], ReplayReceipt] = {}
    by_payload: dict[str, ReplayReceipt] = {}
    for receipt in receipts:
        receipt_collisions = tuple(
            prior
            for prior in (
                by_nonce.get(receipt.nonce),
                by_id.get((receipt.namespace, receipt.record_id)),
                by_payload.get(receipt.payload_fingerprint),
            )
            if prior is not None and prior != receipt
        )
        for prior in receipt_collisions:
            conflicts.add(
                _replay_conflict_fingerprint(
                    "record_collision",
                    prior,
                    receipt,
                )
            )
        by_nonce[receipt.nonce] = receipt
        by_id[(receipt.namespace, receipt.record_id)] = receipt
        by_payload[receipt.payload_fingerprint] = receipt
    by_execution_ref: dict[str, tuple[str, str, str]] = {}
    by_execution_fingerprint: dict[str, tuple[str, str, str]] = {}
    for execution in challenge_executions:
        ref, fingerprint, challenge_fingerprint = execution
        execution_collisions = tuple(
            prior
            for prior in (
                by_execution_ref.get(ref),
                by_execution_fingerprint.get(fingerprint),
            )
            if prior is not None and prior != execution
        )
        for prior_execution in execution_collisions:
            conflicts.add(
                commit_payload_fingerprint(
                    {
                        "conflict_kind": "challenge_execution_reuse",
                        "left": prior_execution,
                        "right": execution,
                    },
                    schema="pheroos-commit-replay-conflict-v1",
                    profile="pheroos-commit-authority-v1",
                )
            )
        by_execution_ref[ref] = execution
        by_execution_fingerprint[fingerprint] = execution
    return tuple(sorted(conflicts))


def _replay_conflict_fingerprint(
    conflict_kind: str,
    left: ReplayReceipt,
    right: ReplayReceipt,
) -> str:
    def payload(receipt: ReplayReceipt) -> tuple[str, str, str, str, str]:
        return (
            receipt.namespace.value,
            receipt.record_id,
            receipt.nonce,
            receipt.payload_fingerprint,
            receipt.candidate_id,
        )

    return commit_payload_fingerprint(
        {
            "conflict_kind": conflict_kind,
            "records": tuple(sorted((payload(left), payload(right)))),
        },
        schema="pheroos-commit-replay-conflict-v1",
        profile="pheroos-commit-authority-v1",
    )


build_commit_replay_receipts.__module__ = "pheroos.governance.commit"
