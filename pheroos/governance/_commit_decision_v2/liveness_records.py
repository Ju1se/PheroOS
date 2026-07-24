"""Window, seal, progress, and terminal Commit Decision v2 records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from pheroos.governance._commit_decision_v2.common import (
    COMMIT_DECISION_OUTCOME_SCHEMA_V2,
    COMMIT_DECISION_PROGRESS_SCHEMA_V2,
    COMMIT_DECISION_SEAL_SCHEMA_V2,
    COMMIT_DECISION_WINDOW_SCHEMA_V2,
    _canonical_texts,
    _exact_array,
    _exact_mapping,
    _freeze_json,
    _install_root,
    _portable_json,
    _require_bool,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
)
from pheroos.governance._commit_decision_v2.enums import (
    CommitDecisionOutcomeKindV2,
    CommitDecisionPhaseV2,
)
from pheroos.governance._commit_decision_v2.liveness_validation import (
    _validate_outcome_authority_fields_impl_v2,
)


@dataclass(frozen=True, slots=True)
class CommitDecisionWindowV2:
    required_stability_steps: int
    streak_count: int
    streak_started_at_step: int | None
    leader_candidate_ref: str
    last_ready: bool
    last_assessment_root: str
    rolling_streak_root: str
    rolling_history_root: str
    reset_reason: str
    remaining_reset_budget: int
    reset_budget_exhausted: bool
    remaining_epoch_restart_budget: int
    schema: str = COMMIT_DECISION_WINDOW_SCHEMA_V2
    window_root: str = ""

    def __post_init__(self) -> None:
        if self.schema != COMMIT_DECISION_WINDOW_SCHEMA_V2:
            raise ValueError("commit decision window schema is unsupported")
        _require_count(
            self.required_stability_steps, "commit window required stability", minimum=1
        )
        _require_count(self.streak_count, "commit window streak_count")
        if self.streak_started_at_step is not None:
            _require_count(self.streak_started_at_step, "commit window streak start")
        _require_text(
            self.leader_candidate_ref, "commit window leader", allow_empty=True
        )
        _require_bool(self.last_ready, "commit window last_ready")
        _require_root(
            self.last_assessment_root, "commit window last assessment", allow_empty=True
        )
        for field in ("rolling_streak_root", "rolling_history_root"):
            _require_root(getattr(self, field), f"commit window {field}")
        _require_text(self.reset_reason, "commit window reset_reason")
        _require_bool(
            self.reset_budget_exhausted,
            "commit window reset_budget_exhausted",
        )
        for field in ("remaining_reset_budget", "remaining_epoch_restart_budget"):
            _require_count(getattr(self, field), f"commit window {field}")
        if self.streak_count == 0:
            if (
                self.streak_started_at_step is not None
                or self.leader_candidate_ref
                or self.last_ready
            ):
                raise ValueError("empty commit streak has active readiness state")
        elif (
            self.streak_started_at_step is None
            or not self.leader_candidate_ref
            or not self.last_ready
        ):
            raise ValueError("active commit streak is incomplete")
        _install_root(self, "window_root", self.window_root, "window", self._body())

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "required_stability_steps": self.required_stability_steps,
            "streak_count": self.streak_count,
            "streak_started_at_step": self.streak_started_at_step,
            "leader_candidate_ref": self.leader_candidate_ref,
            "last_ready": self.last_ready,
            "last_assessment_root": self.last_assessment_root,
            "rolling_streak_root": self.rolling_streak_root,
            "rolling_history_root": self.rolling_history_root,
            "reset_reason": self.reset_reason,
            "remaining_reset_budget": self.remaining_reset_budget,
            "reset_budget_exhausted": self.reset_budget_exhausted,
            "remaining_epoch_restart_budget": self.remaining_epoch_restart_budget,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "window_root": self.window_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitDecisionWindowV2:
        fields = frozenset(
            {
                "schema",
                "required_stability_steps",
                "streak_count",
                "streak_started_at_step",
                "leader_candidate_ref",
                "last_ready",
                "last_assessment_root",
                "rolling_streak_root",
                "rolling_history_root",
                "reset_reason",
                "remaining_reset_budget",
                "reset_budget_exhausted",
                "remaining_epoch_restart_budget",
                "window_root",
            }
        )
        value = _exact_mapping(payload, fields, "commit decision window v2")
        decoded = cls(
            required_stability_steps=cast(
                int,
                value["required_stability_steps"],
            ),
            streak_count=cast(int, value["streak_count"]),
            streak_started_at_step=cast(int | None, value["streak_started_at_step"]),
            leader_candidate_ref=cast(str, value["leader_candidate_ref"]),
            last_ready=cast(bool, value["last_ready"]),
            last_assessment_root=cast(str, value["last_assessment_root"]),
            rolling_streak_root=cast(str, value["rolling_streak_root"]),
            rolling_history_root=cast(str, value["rolling_history_root"]),
            reset_reason=cast(str, value["reset_reason"]),
            remaining_reset_budget=cast(int, value["remaining_reset_budget"]),
            reset_budget_exhausted=cast(
                bool,
                value["reset_budget_exhausted"],
            ),
            remaining_epoch_restart_budget=cast(
                int,
                value["remaining_epoch_restart_budget"],
            ),
            schema=cast(str, value["schema"]),
            window_root=cast(str, value["window_root"]),
        )
        _require_canonical_wire(payload, decoded.to_dict(), "commit decision window v2")
        return decoded


@dataclass(frozen=True, slots=True)
class CommitDecisionWindowSealV2:
    parent_transition_id: str
    parent_snapshot_root: str
    window_root: str
    frozen_dependency_root: str
    sealed_at_step: int
    candidate_ref: str
    claim_root: str
    output_contract_root: str
    output_payload_root: str
    output_payload: Mapping[str, object]
    schema: str = COMMIT_DECISION_SEAL_SCHEMA_V2
    seal_root: str = ""

    def __post_init__(self) -> None:
        if self.schema != COMMIT_DECISION_SEAL_SCHEMA_V2:
            raise ValueError("commit decision seal schema is unsupported")
        _require_text(self.parent_transition_id, "commit seal parent transition")
        for field in (
            "parent_snapshot_root",
            "window_root",
            "frozen_dependency_root",
            "claim_root",
            "output_contract_root",
            "output_payload_root",
        ):
            _require_root(getattr(self, field), f"commit seal {field}")
        _require_count(self.sealed_at_step, "commit seal step")
        _require_text(self.candidate_ref, "commit seal candidate")
        if not isinstance(self.output_payload, Mapping):
            raise TypeError("commit seal output payload must be an object")
        frozen = _freeze_json(dict(self.output_payload))
        if not isinstance(frozen, MappingProxyType):
            raise TypeError("commit seal output payload must be an object")
        object.__setattr__(self, "output_payload", frozen)
        _install_root(self, "seal_root", self.seal_root, "window-seal", self._body())

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "parent_transition_id": self.parent_transition_id,
            "parent_snapshot_root": self.parent_snapshot_root,
            "window_root": self.window_root,
            "frozen_dependency_root": self.frozen_dependency_root,
            "sealed_at_step": self.sealed_at_step,
            "candidate_ref": self.candidate_ref,
            "claim_root": self.claim_root,
            "output_contract_root": self.output_contract_root,
            "output_payload_root": self.output_payload_root,
            "output_payload": _portable_json(self.output_payload),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "seal_root": self.seal_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitDecisionWindowSealV2:
        fields = frozenset(
            {
                "schema",
                "parent_transition_id",
                "parent_snapshot_root",
                "window_root",
                "frozen_dependency_root",
                "sealed_at_step",
                "candidate_ref",
                "claim_root",
                "output_contract_root",
                "output_payload_root",
                "output_payload",
                "seal_root",
            }
        )
        value = _exact_mapping(payload, fields, "commit decision seal v2")
        if type(value["output_payload"]) is not dict:
            raise TypeError("commit seal output payload must be an exact object")
        decoded = cls(
            parent_transition_id=cast(str, value["parent_transition_id"]),
            parent_snapshot_root=cast(str, value["parent_snapshot_root"]),
            window_root=cast(str, value["window_root"]),
            frozen_dependency_root=cast(str, value["frozen_dependency_root"]),
            sealed_at_step=cast(int, value["sealed_at_step"]),
            candidate_ref=cast(str, value["candidate_ref"]),
            claim_root=cast(str, value["claim_root"]),
            output_contract_root=cast(str, value["output_contract_root"]),
            output_payload_root=cast(str, value["output_payload_root"]),
            output_payload=cast(dict[str, object], value["output_payload"]),
            schema=cast(str, value["schema"]),
            seal_root=cast(str, value["seal_root"]),
        )
        _require_canonical_wire(payload, decoded.to_dict(), "commit decision seal v2")
        return decoded


@dataclass(frozen=True, slots=True)
class CommitDecisionProgressV2:
    phase: CommitDecisionPhaseV2
    current_step: int
    evidence_deadline_step: int
    finality_deadline_step: int
    assessment_root: str
    window_root: str
    seal_root: str
    dependency_set_root: str
    heartbeat_sequence: int
    previous_progress_root: str
    remaining_reset_budget: int
    remaining_epoch_restart_budget: int
    leader_candidate_ref: str
    streak_count: int
    next_required_inputs: Sequence[str]
    unmet_gates: Sequence[str]
    schema: str = COMMIT_DECISION_PROGRESS_SCHEMA_V2
    terminal: bool = False
    progress_root: str = ""

    def __post_init__(self) -> None:
        if (
            self.schema != COMMIT_DECISION_PROGRESS_SCHEMA_V2
            or type(self.phase) is not CommitDecisionPhaseV2
        ):
            raise ValueError("commit decision progress schema or phase is unsupported")
        if self.terminal is not False:
            raise ValueError("commit decision progress cannot be terminal")
        for field in (
            "current_step",
            "evidence_deadline_step",
            "finality_deadline_step",
            "heartbeat_sequence",
            "remaining_reset_budget",
            "remaining_epoch_restart_budget",
            "streak_count",
        ):
            _require_count(getattr(self, field), f"commit progress {field}")
        for field in ("assessment_root", "seal_root", "previous_progress_root"):
            _require_root(
                getattr(self, field), f"commit progress {field}", allow_empty=True
            )
        for field in ("window_root", "dependency_set_root"):
            _require_root(getattr(self, field), f"commit progress {field}")
        _require_text(
            self.leader_candidate_ref, "commit progress leader", allow_empty=True
        )
        object.__setattr__(
            self,
            "next_required_inputs",
            _canonical_texts(self.next_required_inputs, "commit next inputs"),
        )
        object.__setattr__(
            self,
            "unmet_gates",
            _canonical_texts(self.unmet_gates, "commit unmet gates"),
        )
        _install_root(
            self, "progress_root", self.progress_root, "progress", self._body()
        )

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "phase": self.phase.value,
            "current_step": self.current_step,
            "evidence_deadline_step": self.evidence_deadline_step,
            "finality_deadline_step": self.finality_deadline_step,
            "assessment_root": self.assessment_root,
            "window_root": self.window_root,
            "seal_root": self.seal_root,
            "dependency_set_root": self.dependency_set_root,
            "heartbeat_sequence": self.heartbeat_sequence,
            "previous_progress_root": self.previous_progress_root,
            "remaining_reset_budget": self.remaining_reset_budget,
            "remaining_epoch_restart_budget": self.remaining_epoch_restart_budget,
            "leader_candidate_ref": self.leader_candidate_ref,
            "streak_count": self.streak_count,
            "next_required_inputs": list(self.next_required_inputs),
            "unmet_gates": list(self.unmet_gates),
            "terminal": self.terminal,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "progress_root": self.progress_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitDecisionProgressV2:
        fields = frozenset(
            {
                "schema",
                "phase",
                "current_step",
                "evidence_deadline_step",
                "finality_deadline_step",
                "assessment_root",
                "window_root",
                "seal_root",
                "dependency_set_root",
                "heartbeat_sequence",
                "previous_progress_root",
                "remaining_reset_budget",
                "remaining_epoch_restart_budget",
                "leader_candidate_ref",
                "streak_count",
                "next_required_inputs",
                "unmet_gates",
                "terminal",
                "progress_root",
            }
        )
        value = _exact_mapping(payload, fields, "commit decision progress v2")
        try:
            value["phase"] = CommitDecisionPhaseV2(cast(str, value["phase"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("commit decision progress phase is unsupported") from exc
        next_required_inputs = tuple(
            cast(str, item)
            for item in _exact_array(
                value["next_required_inputs"],
                "commit progress next_required_inputs",
            )
        )
        unmet_gates = tuple(
            cast(str, item)
            for item in _exact_array(
                value["unmet_gates"],
                "commit progress unmet_gates",
            )
        )
        decoded = cls(
            phase=cast(CommitDecisionPhaseV2, value["phase"]),
            current_step=cast(int, value["current_step"]),
            evidence_deadline_step=cast(int, value["evidence_deadline_step"]),
            finality_deadline_step=cast(int, value["finality_deadline_step"]),
            assessment_root=cast(str, value["assessment_root"]),
            window_root=cast(str, value["window_root"]),
            seal_root=cast(str, value["seal_root"]),
            dependency_set_root=cast(str, value["dependency_set_root"]),
            heartbeat_sequence=cast(int, value["heartbeat_sequence"]),
            previous_progress_root=cast(str, value["previous_progress_root"]),
            remaining_reset_budget=cast(int, value["remaining_reset_budget"]),
            remaining_epoch_restart_budget=cast(
                int,
                value["remaining_epoch_restart_budget"],
            ),
            leader_candidate_ref=cast(str, value["leader_candidate_ref"]),
            streak_count=cast(int, value["streak_count"]),
            next_required_inputs=next_required_inputs,
            unmet_gates=unmet_gates,
            schema=cast(str, value["schema"]),
            terminal=cast(bool, value["terminal"]),
            progress_root=cast(str, value["progress_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "commit decision progress v2"
        )
        return decoded


@dataclass(frozen=True, slots=True)
class CommitDecisionOutcomeV2:
    kind: CommitDecisionOutcomeKindV2
    candidate_ref: str
    claim_root: str
    output_contract_root: str
    output_payload_root: str
    finality_root: str
    epistemically_committed: bool
    delivery_eligible: bool
    publication_eligible: bool
    execution_eligible: bool
    reason_codes: Sequence[str]
    current_step: int
    evidence_deadline_step: int
    finality_deadline_step: int
    window_root: str
    seal_root: str
    frozen_dependency_root: str
    schema: str = COMMIT_DECISION_OUTCOME_SCHEMA_V2
    terminal: bool = True
    outcome_root: str = ""

    def __post_init__(self) -> None:
        if (
            self.schema != COMMIT_DECISION_OUTCOME_SCHEMA_V2
            or type(self.kind) is not CommitDecisionOutcomeKindV2
        ):
            raise ValueError("commit decision outcome schema or kind is unsupported")
        if self.terminal is not True:
            raise ValueError("commit decision outcome must be terminal")
        _validate_outcome_authority_fields(self)
        object.__setattr__(
            self,
            "reason_codes",
            _canonical_texts(
                self.reason_codes, "commit outcome reason codes", allow_empty=False
            ),
        )
        for field in (
            "current_step",
            "evidence_deadline_step",
            "finality_deadline_step",
        ):
            _require_count(getattr(self, field), f"commit outcome {field}")
        for field in ("window_root", "frozen_dependency_root"):
            _require_root(getattr(self, field), f"commit outcome {field}")
        _require_root(self.seal_root, "commit outcome seal_root", allow_empty=True)
        if self.kind is CommitDecisionOutcomeKindV2.EVIDENCE_COMMIT:
            if not all(
                (
                    self.candidate_ref,
                    self.claim_root,
                    self.output_contract_root,
                    self.output_payload_root,
                    self.seal_root,
                    self.finality_root,
                )
            ):
                raise ValueError(
                    "evidence commit outcome is missing frozen output bindings"
                )
            if not self.epistemically_committed:
                raise ValueError("evidence commit must be epistemically committed")
        elif self.epistemically_committed:
            raise ValueError("non-commit outcome cannot be epistemically committed")
        _install_root(self, "outcome_root", self.outcome_root, "outcome", self._body())

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "kind": self.kind.value,
            "candidate_ref": self.candidate_ref,
            "claim_root": self.claim_root,
            "output_contract_root": self.output_contract_root,
            "output_payload_root": self.output_payload_root,
            "finality_root": self.finality_root,
            "epistemically_committed": self.epistemically_committed,
            "delivery_eligible": self.delivery_eligible,
            "publication_eligible": self.publication_eligible,
            "execution_eligible": self.execution_eligible,
            "reason_codes": list(self.reason_codes),
            "current_step": self.current_step,
            "evidence_deadline_step": self.evidence_deadline_step,
            "finality_deadline_step": self.finality_deadline_step,
            "window_root": self.window_root,
            "seal_root": self.seal_root,
            "frozen_dependency_root": self.frozen_dependency_root,
            "terminal": self.terminal,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "outcome_root": self.outcome_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitDecisionOutcomeV2:
        fields = frozenset(
            {
                "schema",
                "kind",
                "candidate_ref",
                "claim_root",
                "output_contract_root",
                "output_payload_root",
                "finality_root",
                "epistemically_committed",
                "delivery_eligible",
                "publication_eligible",
                "execution_eligible",
                "reason_codes",
                "current_step",
                "evidence_deadline_step",
                "finality_deadline_step",
                "window_root",
                "seal_root",
                "frozen_dependency_root",
                "terminal",
                "outcome_root",
            }
        )
        value = _exact_mapping(payload, fields, "commit decision outcome v2")
        try:
            value["kind"] = CommitDecisionOutcomeKindV2(cast(str, value["kind"]))
        except (TypeError, ValueError) as exc:
            raise ValueError("commit decision outcome kind is unsupported") from exc
        reason_codes = tuple(
            cast(str, item)
            for item in _exact_array(
                value["reason_codes"],
                "commit outcome reasons",
            )
        )
        decoded = cls(
            kind=cast(CommitDecisionOutcomeKindV2, value["kind"]),
            candidate_ref=cast(str, value["candidate_ref"]),
            claim_root=cast(str, value["claim_root"]),
            output_contract_root=cast(str, value["output_contract_root"]),
            output_payload_root=cast(str, value["output_payload_root"]),
            finality_root=cast(str, value["finality_root"]),
            epistemically_committed=cast(
                bool,
                value["epistemically_committed"],
            ),
            delivery_eligible=cast(bool, value["delivery_eligible"]),
            publication_eligible=cast(bool, value["publication_eligible"]),
            execution_eligible=cast(bool, value["execution_eligible"]),
            reason_codes=reason_codes,
            current_step=cast(int, value["current_step"]),
            evidence_deadline_step=cast(int, value["evidence_deadline_step"]),
            finality_deadline_step=cast(int, value["finality_deadline_step"]),
            window_root=cast(str, value["window_root"]),
            seal_root=cast(str, value["seal_root"]),
            frozen_dependency_root=cast(str, value["frozen_dependency_root"]),
            schema=cast(str, value["schema"]),
            terminal=cast(bool, value["terminal"]),
            outcome_root=cast(str, value["outcome_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "commit decision outcome v2"
        )
        return decoded


def _validate_outcome_authority_fields(value: CommitDecisionOutcomeV2) -> None:
    _validate_outcome_authority_fields_impl_v2(value)


__all__ = (
    "CommitDecisionOutcomeV2",
    "CommitDecisionProgressV2",
    "CommitDecisionWindowSealV2",
    "CommitDecisionWindowV2",
)
