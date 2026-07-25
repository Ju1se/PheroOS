from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Protocol

from pheroos.governance._commit_validation import (
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_step,
    require_commit_text,
)
from pheroos.governance.errors import GovernanceError
from pheroos.protocol.commit_models import (
    DISTRIBUTED_COMMIT_PROFILE_VERSION,
    CommitAssurance,
)


if TYPE_CHECKING:

    class _QuorumWitnessView(Protocol):
        @property
        def witness_version(self) -> str: ...

        @property
        def profile(self) -> str: ...

        @property
        def assurance(self) -> CommitAssurance: ...

        @property
        def epoch(self) -> int: ...

        @property
        def witnessed_at_step(self) -> int: ...

        @property
        def expires_at_step(self) -> int: ...

        @property
        def membership_root(self) -> str: ...

        @property
        def commit_value_root(self) -> str: ...

        @property
        def proposal_digest(self) -> str: ...

    class _DistributedProposalView(Protocol):
        @property
        def membership_root(self) -> str: ...

        @property
        def commit_value_root(self) -> str: ...

        @property
        def proposal_digest(self) -> str: ...
else:

    class _QuorumWitnessView(Protocol):
        pass

    class _DistributedProposalView(Protocol):
        pass


def validate_quorum_witness(
    witness: _QuorumWitnessView,
    *,
    witness_version: str,
) -> None:
    if witness.witness_version != witness_version:
        raise GovernanceError("quorum witness version is unsupported")
    if witness.profile != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("quorum witness profile is invalid")
    if witness.assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("quorum witness assurance is invalid")
    for name in (
        "witness_id",
        "protocol_id",
        "run_id",
        "target",
        "candidate_id",
        "principal_id",
        "principal_cluster_id",
        "failure_domain",
        "nonce",
        "provenance",
        "trace_event_id",
        "attestation_ref",
    ):
        require_commit_text(getattr(witness, name), f"quorum witness {name}")
    for name in (
        "membership_root",
        "commit_value_root",
        "proposal_digest",
    ):
        require_commit_fingerprint(
            getattr(witness, name),
            f"quorum witness {name}",
        )
    require_commit_step(witness.epoch, "quorum witness epoch")
    witnessed = require_commit_step(
        witness.witnessed_at_step,
        "quorum witness witnessed_at_step",
    )
    expires = require_commit_step(
        witness.expires_at_step,
        "quorum witness expires_at_step",
    )
    if expires <= witnessed:
        raise GovernanceError("quorum witness expiry must follow signing")


def _validate_witness_proposal_binding(
    witness: _QuorumWitnessView,
    proposal: _DistributedProposalView,
) -> None:
    for name in (
        "profile",
        "assurance",
        "protocol_id",
        "run_id",
        "target",
        "epoch",
        "candidate_id",
    ):
        if getattr(witness, name) != getattr(proposal, name):
            raise GovernanceError(f"quorum witness {name} binding mismatch")
    if (
        witness.membership_root != proposal.membership_root
        or witness.commit_value_root != proposal.commit_value_root
        or witness.proposal_digest != proposal.proposal_digest
    ):
        raise GovernanceError("quorum witness proposal/root binding mismatch")


def _attestation_matches(
    attestation_ref: str,
    trusted_attestations: Mapping[str, str],
    body_root: str,
) -> bool:
    if not isinstance(trusted_attestations, Mapping):
        return False
    return trusted_attestations.get(attestation_ref) == body_root


def _require_attestation_bindings(
    references: Sequence[str],
    trusted_attestations: Mapping[str, str],
    body_root: str,
    *,
    field_name: str,
) -> tuple[str, ...]:
    normalized = require_commit_labels(references, f"{field_name} attestations")
    if not all(
        _attestation_matches(reference, trusted_attestations, body_root)
        for reference in normalized
    ):
        raise GovernanceError(f"{field_name} attestation verification failed")
    return normalized
