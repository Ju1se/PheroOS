from __future__ import annotations

from collections.abc import Mapping

from dataclasses import dataclass, field

from enum import StrEnum

from pheroos.governance._distributed._certificate_contract import (
    _validate_receipt_state_binding,
    _validate_certificate_state_binding,
)


from pheroos.governance._distributed._finality_contract import (
    _validate_outcome_state_binding,
)

from pheroos.governance._distributed.invariants import (
    _coerce_assurance,
    _public_dataclass_payload,
    _require_sequence,
    _strict_dataclass_payload,
)


from pheroos.governance._distributed.records import (
    _FINALITY_DECISION_ISSUANCE,
)


from pheroos.governance._commit_validation import (
    require_commit_bool,
    require_commit_fingerprint,
    require_commit_labels,
    require_commit_step,
    require_commit_text,
)


from pheroos.governance.certificate import (
    LocalCommitReceipt,
    local_commit_receipt_fingerprint,
    local_commit_receipt_is_authoritative,
)

from pheroos.governance.commit_numeric import commit_payload_fingerprint

from pheroos.governance.errors import GovernanceError


from pheroos.protocol.commit_models import (
    DISTRIBUTED_COMMIT_PROFILE_VERSION,
    CommitAssurance,
)


from pheroos.governance._distributed.constants import (
    DISTRIBUTED_FINALITY_DECISION_VERSION,
)
from pheroos.governance._commit_state.records import (
    DecisionOutcome,
    DecisionOutcomeKind,
    decision_outcome_fingerprint,
    decision_outcome_is_authoritative,
)
from pheroos.governance._distributed.state import (
    DistributedCommitState,
    distributed_commit_state_fingerprint,
    distributed_commit_state_is_current,
)
from pheroos.governance._distributed.certificate import (
    DistributedCertificateStatus,
    DistributedCommitCertificate,
    distributed_commit_certificate_fingerprint,
    distributed_commit_certificate_is_current_final,
)


class DistributedFinalityKind(StrEnum):
    PENDING = "pending"
    PROVISIONAL = "provisional"
    FINAL = "final"
    NON_COMMIT_TERMINAL = "non_commit_terminal"
    FINALITY_UNAVAILABLE = "finality_unavailable"
    SAFETY_VIOLATION = "safety_violation"


@dataclass(frozen=True)
class DistributedFinalityDecision:
    decision_version: str
    kind: DistributedFinalityKind
    terminal: bool
    authoritative_commit: bool
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    protocol_id: str
    run_id: str
    target: str
    epoch: int
    candidate_id: str
    state_ref: str
    local_receipt_ref: str
    distributed_certificate_ref: str
    outcome_ref: str
    reason_codes: tuple[str, ...]
    current_step: int
    _issuance: object | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reason_codes",
            require_commit_labels(
                self.reason_codes,
                "distributed finality reason codes",
            ),
        )
        _validate_distributed_finality_decision(self)


def evaluate_distributed_finality(
    state: DistributedCommitState,
    receipt: LocalCommitReceipt,
    *,
    certificate: DistributedCommitCertificate | None,
    current_step: int,
    outcome: DecisionOutcome | None = None,
) -> DistributedFinalityDecision:
    """Bridge distributed proof ordering into bounded liveness without a truth cycle.

    Pre-terminal ordering is receipt -> distributed certificate -> liveness
    input. A later authoritative outcome can be supplied to verify that liveness
    used the exact final certificate, or that a deadline terminal remained a
    non-commit.
    """

    if not distributed_commit_state_is_current(state):
        raise GovernanceError("distributed finality requires current state")
    if not local_commit_receipt_is_authoritative(receipt):
        raise GovernanceError("distributed finality requires local receipt")
    _validate_receipt_state_binding(receipt, state)
    current = require_commit_step(
        current_step,
        "distributed finality current_step",
    )
    if current < state.current_step:
        raise GovernanceError("distributed finality cannot move backwards")
    receipt_ref = local_commit_receipt_fingerprint(receipt)
    certificate_ref = ""
    candidate_id = receipt.candidate_id
    reasons: tuple[str, ...]
    if state.frozen:
        kind = DistributedFinalityKind.SAFETY_VIOLATION
        terminal = outcome is not None
        authoritative_commit = False
        reasons = ("distributed_epoch_frozen",)
    elif certificate is None:
        kind = DistributedFinalityKind.PENDING
        terminal = False
        authoritative_commit = False
        reasons = ("distributed_witness_quorum_pending",)
    else:
        certificate_ref = distributed_commit_certificate_fingerprint(certificate)
        _validate_certificate_state_binding(certificate, state)
        if certificate.proposal.local_receipt_ref != receipt_ref:
            raise GovernanceError(
                "distributed certificate does not bind the supplied local receipt"
            )
        if certificate.status is DistributedCertificateStatus.PROVISIONAL:
            kind = DistributedFinalityKind.PROVISIONAL
            terminal = False
            authoritative_commit = False
            reasons = ("distributed_certificate_provisional",)
        elif distributed_commit_certificate_is_current_final(certificate, state):
            kind = DistributedFinalityKind.FINAL
            terminal = False
            authoritative_commit = True
            reasons = ("distributed_finality_verified",)
        else:
            raise GovernanceError(
                "distributed final certificate is not registered/current"
            )

    outcome_ref = ""
    if outcome is not None:
        if not decision_outcome_is_authoritative(outcome):
            raise GovernanceError(
                "distributed finality outcome is not governance-issued"
            )
        _validate_outcome_state_binding(outcome, state)
        outcome_ref = decision_outcome_fingerprint(outcome)
        terminal = True
        if outcome.kind is DecisionOutcomeKind.EVIDENCE_COMMIT:
            if (
                kind is not DistributedFinalityKind.FINAL
                or not certificate_ref
                or outcome.certificate_ref != certificate_ref
                or outcome.candidate_id != candidate_id
                or not outcome.authoritative_commit
                or not outcome.epistemically_committed
            ):
                raise GovernanceError(
                    "distributed evidence outcome lacks exact final certificate lineage"
                )
            authoritative_commit = True
            reasons = ("distributed_evidence_outcome_verified",)
        elif outcome.kind is DecisionOutcomeKind.FINALITY_UNAVAILABLE:
            if current < min(
                outcome.absolute_deadline_step,
                outcome.absolute_run_deadline_step,
            ):
                raise GovernanceError(
                    "finality_unavailable cannot be terminal before the deadline"
                )
            if certificate is not None and (
                certificate.status is DistributedCertificateStatus.FINAL
            ):
                raise GovernanceError(
                    "finality_unavailable cannot hide a final certificate"
                )
            if outcome.authoritative_commit or outcome.epistemically_committed:
                raise GovernanceError(
                    "finality_unavailable cannot claim commit authority"
                )
            kind = DistributedFinalityKind.FINALITY_UNAVAILABLE
            authoritative_commit = False
            certificate_ref = ""
            reasons = ("distributed_finality_deadline_unavailable",)
        elif outcome.kind is DecisionOutcomeKind.SAFETY_VIOLATION:
            kind = DistributedFinalityKind.SAFETY_VIOLATION
            authoritative_commit = False
            reasons = ("distributed_safety_outcome_verified",)
        else:
            if outcome.authoritative_commit or outcome.epistemically_committed:
                raise GovernanceError(
                    "non-evidence distributed outcome cannot claim commit"
                )
            kind = DistributedFinalityKind.NON_COMMIT_TERMINAL
            authoritative_commit = False
            certificate_ref = ""
            reasons = (f"distributed_non_commit_{outcome.kind.value}",)

    decision = DistributedFinalityDecision(
        decision_version=DISTRIBUTED_FINALITY_DECISION_VERSION,
        kind=kind,
        terminal=terminal,
        authoritative_commit=authoritative_commit,
        profile=state.profile,
        assurance=state.assurance,
        manifest_root=state.manifest_root,
        commit_policy_root=state.commit_policy_root,
        protocol_id=state.protocol_id,
        run_id=state.run_id,
        target=state.target,
        epoch=state.epoch,
        candidate_id=candidate_id,
        state_ref=distributed_commit_state_fingerprint(state),
        local_receipt_ref=receipt_ref,
        distributed_certificate_ref=certificate_ref,
        outcome_ref=outcome_ref,
        reason_codes=reasons,
        current_step=current,
    )
    object.__setattr__(
        decision,
        "_issuance",
        (
            _FINALITY_DECISION_ISSUANCE,
            distributed_finality_decision_fingerprint(decision),
        ),
    )
    return decision


def distributed_finality_decision_payload(
    decision: DistributedFinalityDecision,
) -> dict[str, object]:
    if type(decision) is not DistributedFinalityDecision:
        raise GovernanceError("distributed finality decision must be canonical")
    _validate_distributed_finality_decision(decision)
    return _public_dataclass_payload(decision)


def distributed_finality_decision_fingerprint(
    decision: DistributedFinalityDecision,
) -> str:
    return commit_payload_fingerprint(
        distributed_finality_decision_payload(decision),
        schema=DISTRIBUTED_FINALITY_DECISION_VERSION,
        profile=decision.profile,
    )


def distributed_finality_decision_from_payload(
    payload: Mapping[str, object],
) -> DistributedFinalityDecision:
    values = _strict_dataclass_payload(
        payload,
        DistributedFinalityDecision,
        "distributed finality decision payload",
    )
    values["kind"] = _coerce_finality_kind(values["kind"])
    values["assurance"] = _coerce_assurance(values["assurance"])
    values["reason_codes"] = tuple(
        _require_sequence(
            values["reason_codes"],
            "distributed finality reason codes",
        )
    )
    try:
        return DistributedFinalityDecision(**values)
    except (TypeError, ValueError, GovernanceError) as exc:
        raise GovernanceError(
            f"distributed finality decision payload is invalid: {exc}"
        ) from exc


def distributed_finality_decision_is_authoritative(decision: object) -> bool:
    if type(decision) is not DistributedFinalityDecision:
        return False
    try:
        issuance = decision._issuance
        return bool(
            isinstance(issuance, tuple)
            and len(issuance) == 2
            and issuance[0] is _FINALITY_DECISION_ISSUANCE
            and issuance[1] == distributed_finality_decision_fingerprint(decision)
        )
    except Exception:
        return False


def _validate_distributed_finality_decision(
    decision: DistributedFinalityDecision,
) -> None:
    if decision.decision_version != DISTRIBUTED_FINALITY_DECISION_VERSION:
        raise GovernanceError("distributed finality decision version is unsupported")
    if type(decision.kind) is not DistributedFinalityKind:
        raise GovernanceError("distributed finality decision kind is invalid")
    require_commit_bool(decision.terminal, "distributed finality terminal")
    require_commit_bool(
        decision.authoritative_commit,
        "distributed finality authoritative_commit",
    )
    if decision.profile != DISTRIBUTED_COMMIT_PROFILE_VERSION:
        raise GovernanceError("distributed finality profile is invalid")
    if decision.assurance is not CommitAssurance.DISTRIBUTED:
        raise GovernanceError("distributed finality assurance is invalid")
    for name in ("protocol_id", "run_id", "target", "candidate_id"):
        require_commit_text(
            getattr(decision, name),
            f"distributed finality {name}",
        )
    for name in (
        "manifest_root",
        "commit_policy_root",
        "state_ref",
        "local_receipt_ref",
    ):
        require_commit_fingerprint(
            getattr(decision, name),
            f"distributed finality {name}",
        )
    if decision.distributed_certificate_ref:
        require_commit_fingerprint(
            decision.distributed_certificate_ref,
            "distributed finality certificate ref",
        )
    if decision.outcome_ref:
        require_commit_fingerprint(
            decision.outcome_ref,
            "distributed finality outcome ref",
        )
    require_commit_step(decision.epoch, "distributed finality epoch")
    require_commit_step(
        decision.current_step,
        "distributed finality current_step",
    )
    if decision.kind in {
        DistributedFinalityKind.PENDING,
        DistributedFinalityKind.PROVISIONAL,
    }:
        if decision.terminal or decision.authoritative_commit or decision.outcome_ref:
            raise GovernanceError("pending/provisional finality cannot be terminal")
    if decision.kind is DistributedFinalityKind.PENDING and (
        decision.distributed_certificate_ref
    ):
        raise GovernanceError("pending finality cannot carry a certificate")
    if decision.kind is DistributedFinalityKind.PROVISIONAL and not (
        decision.distributed_certificate_ref
    ):
        raise GovernanceError("provisional finality requires its proof reference")
    if decision.kind is DistributedFinalityKind.FINAL:
        if not decision.authoritative_commit or not (
            decision.distributed_certificate_ref
        ):
            raise GovernanceError("final distributed decision lacks authority")
    elif decision.authoritative_commit:
        raise GovernanceError("non-final distributed decision claims commit")
    if decision.terminal is not bool(decision.outcome_ref):
        raise GovernanceError("terminal distributed finality must bind an outcome")
    if (
        decision.kind
        in {
            DistributedFinalityKind.FINALITY_UNAVAILABLE,
            DistributedFinalityKind.NON_COMMIT_TERMINAL,
        }
        and not decision.terminal
    ):
        raise GovernanceError("non-commit terminal finality requires an outcome")


def _coerce_finality_kind(value: object) -> DistributedFinalityKind:
    if type(value) is DistributedFinalityKind:
        return value
    try:
        return DistributedFinalityKind(value)
    except (TypeError, ValueError) as exc:
        raise GovernanceError("distributed finality kind is invalid") from exc


for _name in (
    "DistributedFinalityKind",
    "DistributedFinalityDecision",
    "evaluate_distributed_finality",
    "distributed_finality_decision_payload",
    "distributed_finality_decision_fingerprint",
    "distributed_finality_decision_from_payload",
    "distributed_finality_decision_is_authoritative",
    "_validate_distributed_finality_decision",
    "_coerce_finality_kind",
):
    globals()[_name].__module__ = "pheroos.governance.distributed_commit"
del _name
