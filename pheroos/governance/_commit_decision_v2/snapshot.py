"""Complete-replacement Commit Decision v2 snapshot contract."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import ClassVar, cast

from pheroos.protocol.authority_v2 import AUTHORITY_CANONICAL_VERSION_V2
from pheroos.protocol.commit_models import COMMIT_PROFILES_BY_ASSURANCE, CommitAssurance

from pheroos.governance._commit_decision_v2.assessment_records import CommitAssessmentV2
from pheroos.governance._commit_decision_v2.common import (
    COMMIT_DECISION_SNAPSHOT_SCHEMA_V2,
    COMMIT_DECISION_STATE_SCHEMA_V2,
    MAX_COMMIT_DECISION_SNAPSHOT_BYTES_V2,
    _canonical_bytes,
    _exact_array,
    _exact_mapping,
    _install_root,
    _require_canonical_wire,
    _require_count,
    _require_root,
    _require_text,
    _root,
)
from pheroos.governance._commit_decision_v2.dependencies import (
    CommitDecisionDependencyV2,
    canonical_commit_decision_dependencies_v2,
    commit_decision_dependency_set_root_v2,
)
from pheroos.governance._commit_decision_v2.enums import CommitDecisionMutationKindV2
from pheroos.governance._commit_decision_v2.liveness_records import (
    CommitDecisionOutcomeV2,
    CommitDecisionProgressV2,
    CommitDecisionWindowSealV2,
    CommitDecisionWindowV2,
)


def commit_decision_stream_ref_v2(
    scope_ref: str, protocol_ref: str, run_ref: str, target_ref: str
) -> str:
    values = tuple(
        _require_text(value, f"commit decision stream {label}")
        for label, value in (
            ("scope_ref", scope_ref),
            ("protocol_ref", protocol_ref),
            ("run_ref", run_ref),
            ("target_ref", target_ref),
        )
    )
    material = b"\x00".join(item.encode("utf-8") for item in values)
    return "authority:commit-decision-v2:" + sha256(material).hexdigest()


def commit_decision_transition_id_v2(stream_ref: str, mutation_ref: str) -> str:
    stream = _require_text(stream_ref, "commit decision transition stream_ref")
    mutation = _require_text(mutation_ref, "commit decision transition mutation_ref")
    digest = sha256(stream.encode("utf-8") + b"\x00" + mutation.encode("utf-8"))
    return "transition:commit-decision-v2:" + digest.hexdigest()


COMMIT_DECISION_GENESIS_TRANSITION_ID_V2 = "genesis"
COMMIT_DECISION_GENESIS_SNAPSHOT_ROOT_V2 = _root(
    "genesis-snapshot", {"schema": COMMIT_DECISION_SNAPSHOT_SCHEMA_V2}
)
COMMIT_DECISION_GENESIS_HISTORY_ROOT_V2 = _root(
    "genesis-history", {"schema": COMMIT_DECISION_STATE_SCHEMA_V2}
)


def commit_decision_history_advance_v2(
    parent_history_root: str,
    parent_history_count: int,
    transition_id: str,
    mutation_kind: CommitDecisionMutationKindV2,
    state_root: str,
) -> str:
    _require_root(parent_history_root, "commit decision parent history root")
    _require_count(parent_history_count, "commit decision parent history count")
    _require_text(transition_id, "commit decision history transition")
    if type(mutation_kind) is not CommitDecisionMutationKindV2:
        raise TypeError("commit decision history mutation kind is invalid")
    _require_root(state_root, "commit decision history state root")
    return _root(
        "history",
        {
            "parent_history_root": parent_history_root,
            "parent_history_count": parent_history_count,
            "transition_id": transition_id,
            "mutation_kind": mutation_kind.value,
            "state_root": state_root,
        },
    )


@dataclass(frozen=True, slots=True)
class CommitDecisionSnapshotV2:
    domain_root: str
    scope_ref: str
    protocol_ref: str
    run_ref: str
    target_ref: str
    profile: str
    assurance: CommitAssurance
    manifest_root: str
    commit_policy_root: str
    epoch: int
    stream_ref: str
    mutation_ref: str
    transition_id: str
    mutation_kind: CommitDecisionMutationKindV2
    mutation_issuer_ref: str
    revision: int
    parent_revision: int
    parent_transition_id: str
    parent_snapshot_root: str
    initialized_at_step: int
    current_step: int
    evidence_deadline_step: int
    finality_deadline_step: int
    parent_history_root: str
    parent_history_count: int
    history_root: str
    history_count: int
    dependencies: Sequence[CommitDecisionDependencyV2]
    dependency_set_root: str
    assessment: CommitAssessmentV2 | None
    window: CommitDecisionWindowV2
    seal: CommitDecisionWindowSealV2 | None
    progress: CommitDecisionProgressV2 | None
    outcome: CommitDecisionOutcomeV2 | None
    source_context_root: str
    schema: str = COMMIT_DECISION_SNAPSHOT_SCHEMA_V2
    state_schema: str = COMMIT_DECISION_STATE_SCHEMA_V2
    canonical_version: str = AUTHORITY_CANONICAL_VERSION_V2
    state_root: str = ""
    snapshot_root: str = ""

    _root_field: ClassVar[str] = "snapshot_root"

    def __post_init__(self) -> None:
        self._validate_context()
        self._validate_continuity()
        dependencies = canonical_commit_decision_dependencies_v2(self.dependencies)
        object.__setattr__(self, "dependencies", dependencies)
        expected_dependencies = commit_decision_dependency_set_root_v2(dependencies)
        if self.dependency_set_root not in ("", expected_dependencies):
            raise ValueError("commit decision dependency_set_root is mismatched")
        object.__setattr__(self, "dependency_set_root", expected_dependencies)
        self._validate_records()
        state_body = self._state_body()
        _install_root(self, "state_root", self.state_root, "state", state_body)
        expected_history = commit_decision_history_advance_v2(
            self.parent_history_root,
            self.parent_history_count,
            self.transition_id,
            self.mutation_kind,
            self.state_root,
        )
        if self.history_root not in ("", expected_history):
            raise ValueError("commit decision history_root is mismatched")
        object.__setattr__(self, "history_root", expected_history)
        _install_root(
            self, "snapshot_root", self.snapshot_root, "snapshot", self._body()
        )
        if (
            len(_canonical_bytes(self.to_dict()))
            > MAX_COMMIT_DECISION_SNAPSHOT_BYTES_V2
        ):
            raise ValueError("commit decision snapshot exceeds its byte bound")

    def _validate_context(self) -> None:
        if (
            self.schema != COMMIT_DECISION_SNAPSHOT_SCHEMA_V2
            or self.state_schema != COMMIT_DECISION_STATE_SCHEMA_V2
        ):
            raise ValueError("commit decision snapshot schema is unsupported")
        if self.canonical_version != AUTHORITY_CANONICAL_VERSION_V2:
            raise ValueError("commit decision canonical version is unsupported")
        for field in (
            "domain_root",
            "manifest_root",
            "commit_policy_root",
            "source_context_root",
            "parent_snapshot_root",
            "parent_history_root",
        ):
            _require_root(getattr(self, field), f"commit decision {field}")
        for field in (
            "scope_ref",
            "protocol_ref",
            "run_ref",
            "target_ref",
            "profile",
            "stream_ref",
            "mutation_ref",
            "transition_id",
            "mutation_issuer_ref",
            "parent_transition_id",
        ):
            _require_text(getattr(self, field), f"commit decision {field}")
        if (
            type(self.assurance) is not CommitAssurance
            or self.profile
            not in COMMIT_PROFILES_BY_ASSURANCE.get(self.assurance.value, frozenset())
        ):
            raise ValueError("commit decision profile and assurance are mismatched")
        if type(self.mutation_kind) is not CommitDecisionMutationKindV2:
            raise TypeError("commit decision mutation kind is invalid")
        for field in (
            "epoch",
            "revision",
            "parent_revision",
            "initialized_at_step",
            "current_step",
            "evidence_deadline_step",
            "finality_deadline_step",
            "parent_history_count",
            "history_count",
        ):
            _require_count(getattr(self, field), f"commit decision {field}")

    def _validate_continuity(self) -> None:
        if self.stream_ref != commit_decision_stream_ref_v2(
            self.scope_ref, self.protocol_ref, self.run_ref, self.target_ref
        ):
            raise ValueError("commit decision stream identity is mismatched")
        if self.transition_id != commit_decision_transition_id_v2(
            self.stream_ref, self.mutation_ref
        ):
            raise ValueError("commit decision transition identity is mismatched")
        if self.revision < 1 or self.parent_revision != self.revision - 1:
            raise ValueError("commit decision revision is not contiguous")
        if self.revision == 1 and (
            self.parent_transition_id != COMMIT_DECISION_GENESIS_TRANSITION_ID_V2
            or self.parent_snapshot_root != COMMIT_DECISION_GENESIS_SNAPSHOT_ROOT_V2
            or self.parent_history_root != COMMIT_DECISION_GENESIS_HISTORY_ROOT_V2
            or self.parent_history_count != 0
        ):
            raise ValueError("commit decision genesis lineage is mismatched")
        if self.history_count != self.parent_history_count + 1:
            raise ValueError("commit decision history count is not contiguous")
        if self.current_step < self.initialized_at_step:
            raise ValueError("commit decision current step predates initialization")
        if (
            not self.initialized_at_step
            < self.evidence_deadline_step
            <= self.finality_deadline_step
        ):
            raise ValueError("commit decision deadlines are invalid")

    def _validate_records(self) -> None:
        if type(self.window) is not CommitDecisionWindowV2:
            raise TypeError("commit decision snapshot requires an exact window")
        for value, expected, label in (
            (self.assessment, CommitAssessmentV2, "assessment"),
            (self.seal, CommitDecisionWindowSealV2, "seal"),
            (self.progress, CommitDecisionProgressV2, "progress"),
            (self.outcome, CommitDecisionOutcomeV2, "outcome"),
        ):
            if value is not None and type(value) is not expected:
                raise TypeError(f"commit decision {label} has an invalid type")
        if (self.progress is None) == (self.outcome is None):
            raise ValueError(
                "commit decision snapshot requires exactly progress or outcome"
            )
        if self.outcome is not None and self.mutation_kind not in {
            CommitDecisionMutationKindV2.FINALIZED,
            CommitDecisionMutationKindV2.DEADLINE_TERMINATED,
        }:
            raise ValueError(
                "commit decision terminal snapshot has a nonterminal mutation"
            )
        if (
            self.progress is not None
            and self.progress.current_step != self.current_step
        ):
            raise ValueError("commit decision progress step is mismatched")

    def _state_body(self) -> dict[str, object]:
        return {
            "mutation_kind": self.mutation_kind.value,
            "epoch": self.epoch,
            "current_step": self.current_step,
            "dependency_set_root": self.dependency_set_root,
            "assessment_root": ""
            if self.assessment is None
            else self.assessment.assessment_root,
            "window_root": self.window.window_root,
            "seal_root": "" if self.seal is None else self.seal.seal_root,
            "progress_root": ""
            if self.progress is None
            else self.progress.progress_root,
            "outcome_root": "" if self.outcome is None else self.outcome.outcome_root,
            "source_context_root": self.source_context_root,
        }

    def _body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "state_schema": self.state_schema,
            "canonical_version": self.canonical_version,
            "domain_root": self.domain_root,
            "scope_ref": self.scope_ref,
            "protocol_ref": self.protocol_ref,
            "run_ref": self.run_ref,
            "target_ref": self.target_ref,
            "profile": self.profile,
            "assurance": self.assurance.value,
            "manifest_root": self.manifest_root,
            "commit_policy_root": self.commit_policy_root,
            "epoch": self.epoch,
            "stream_ref": self.stream_ref,
            "mutation_ref": self.mutation_ref,
            "transition_id": self.transition_id,
            "mutation_kind": self.mutation_kind.value,
            "mutation_issuer_ref": self.mutation_issuer_ref,
            "revision": self.revision,
            "parent_revision": self.parent_revision,
            "parent_transition_id": self.parent_transition_id,
            "parent_snapshot_root": self.parent_snapshot_root,
            "initialized_at_step": self.initialized_at_step,
            "current_step": self.current_step,
            "evidence_deadline_step": self.evidence_deadline_step,
            "finality_deadline_step": self.finality_deadline_step,
            "parent_history_root": self.parent_history_root,
            "parent_history_count": self.parent_history_count,
            "history_root": self.history_root,
            "history_count": self.history_count,
            "dependencies": [item.to_dict() for item in self.dependencies],
            "dependency_set_root": self.dependency_set_root,
            "assessment": None
            if self.assessment is None
            else self.assessment.to_dict(),
            "window": self.window.to_dict(),
            "seal": None if self.seal is None else self.seal.to_dict(),
            "progress": None if self.progress is None else self.progress.to_dict(),
            "outcome": None if self.outcome is None else self.outcome.to_dict(),
            "source_context_root": self.source_context_root,
            "state_root": self.state_root,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._body(), "snapshot_root": self.snapshot_root}

    @classmethod
    def from_dict(cls, payload: object) -> CommitDecisionSnapshotV2:
        value = _exact_mapping(payload, _SNAPSHOT_FIELDS, "commit decision snapshot v2")
        try:
            value["assurance"] = CommitAssurance(cast(str, value["assurance"]))
            value["mutation_kind"] = CommitDecisionMutationKindV2(
                cast(str, value["mutation_kind"])
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("commit decision snapshot enum is unsupported") from exc
        dependencies = tuple(
            CommitDecisionDependencyV2.from_dict(item)
            for item in _exact_array(
                value["dependencies"], "commit decision dependencies"
            )
        )
        assessment = (
            None
            if value["assessment"] is None
            else CommitAssessmentV2.from_dict(value["assessment"])
        )
        window = CommitDecisionWindowV2.from_dict(value["window"])
        seal = (
            None
            if value["seal"] is None
            else CommitDecisionWindowSealV2.from_dict(value["seal"])
        )
        progress = (
            None
            if value["progress"] is None
            else CommitDecisionProgressV2.from_dict(value["progress"])
        )
        outcome = (
            None
            if value["outcome"] is None
            else CommitDecisionOutcomeV2.from_dict(value["outcome"])
        )
        decoded = cls(
            domain_root=cast(str, value["domain_root"]),
            scope_ref=cast(str, value["scope_ref"]),
            protocol_ref=cast(str, value["protocol_ref"]),
            run_ref=cast(str, value["run_ref"]),
            target_ref=cast(str, value["target_ref"]),
            profile=cast(str, value["profile"]),
            assurance=cast(CommitAssurance, value["assurance"]),
            manifest_root=cast(str, value["manifest_root"]),
            commit_policy_root=cast(str, value["commit_policy_root"]),
            epoch=cast(int, value["epoch"]),
            stream_ref=cast(str, value["stream_ref"]),
            mutation_ref=cast(str, value["mutation_ref"]),
            transition_id=cast(str, value["transition_id"]),
            mutation_kind=cast(CommitDecisionMutationKindV2, value["mutation_kind"]),
            mutation_issuer_ref=cast(str, value["mutation_issuer_ref"]),
            revision=cast(int, value["revision"]),
            parent_revision=cast(int, value["parent_revision"]),
            parent_transition_id=cast(str, value["parent_transition_id"]),
            parent_snapshot_root=cast(str, value["parent_snapshot_root"]),
            initialized_at_step=cast(int, value["initialized_at_step"]),
            current_step=cast(int, value["current_step"]),
            evidence_deadline_step=cast(int, value["evidence_deadline_step"]),
            finality_deadline_step=cast(int, value["finality_deadline_step"]),
            parent_history_root=cast(str, value["parent_history_root"]),
            parent_history_count=cast(int, value["parent_history_count"]),
            history_root=cast(str, value["history_root"]),
            history_count=cast(int, value["history_count"]),
            dependencies=dependencies,
            dependency_set_root=cast(str, value["dependency_set_root"]),
            assessment=assessment,
            window=window,
            seal=seal,
            progress=progress,
            outcome=outcome,
            source_context_root=cast(str, value["source_context_root"]),
            schema=cast(str, value["schema"]),
            state_schema=cast(str, value["state_schema"]),
            canonical_version=cast(str, value["canonical_version"]),
            state_root=cast(str, value["state_root"]),
            snapshot_root=cast(str, value["snapshot_root"]),
        )
        _require_canonical_wire(
            payload, decoded.to_dict(), "commit decision snapshot v2"
        )
        return decoded


_SNAPSHOT_FIELDS = frozenset(
    {
        "schema",
        "state_schema",
        "canonical_version",
        "domain_root",
        "scope_ref",
        "protocol_ref",
        "run_ref",
        "target_ref",
        "profile",
        "assurance",
        "manifest_root",
        "commit_policy_root",
        "epoch",
        "stream_ref",
        "mutation_ref",
        "transition_id",
        "mutation_kind",
        "mutation_issuer_ref",
        "revision",
        "parent_revision",
        "parent_transition_id",
        "parent_snapshot_root",
        "initialized_at_step",
        "current_step",
        "evidence_deadline_step",
        "finality_deadline_step",
        "parent_history_root",
        "parent_history_count",
        "history_root",
        "history_count",
        "dependencies",
        "dependency_set_root",
        "assessment",
        "window",
        "seal",
        "progress",
        "outcome",
        "source_context_root",
        "state_root",
        "snapshot_root",
    }
)


__all__ = (
    "COMMIT_DECISION_GENESIS_HISTORY_ROOT_V2",
    "COMMIT_DECISION_GENESIS_SNAPSHOT_ROOT_V2",
    "COMMIT_DECISION_GENESIS_TRANSITION_ID_V2",
    "CommitDecisionSnapshotV2",
    "commit_decision_history_advance_v2",
    "commit_decision_stream_ref_v2",
    "commit_decision_transition_id_v2",
)
